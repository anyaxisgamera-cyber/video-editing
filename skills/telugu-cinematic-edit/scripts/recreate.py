#!/usr/bin/env python3
"""Recreate a reference video's edit with new footage and a Telugu voice-over → Cinematic timeline for render.py.

    /opt/cws-venv/bin/python recreate.py PROJECT --breakdown ref/breakdown.json --script script/script.json \
        --voice voice/ --plan plan.json [--width 1920 --height 1080] [--fps REF] [--timeline timeline.json]

What is taken from the reference breakdown (measured, see reference_breakdown.py):
  pacing       shot-duration pattern (cycled in order) → shots per script segment = span / average shot length;
               cut offset relative to speech (J-cut lead) when the reference has speech
  transitions  type + length in frames, in the reference's order (cut / dissolve / dip to black|white / flash)
  camera       per reference shot: push-in / pull-out / pan / tilt with its measured rate → same move and speed
  grade        per reference shot Lab mean/std → a 33³ 3D LUT per clip (Reinhard transfer, limited strength) baked
               with ffmpeg; letterbox if the reference has bars
  text         centre/top text events → title card with the measured entrance (fade/blur ramp vs cut-in); bottom text
               → subtitle style; subtitles are always the verified Telugu script (telugu_script.py cues)
  audio        hits/whooshes at transitions where the reference has them; music bed ducked under the voice;
               loudness target −16 LUFS (render.py masters and verifies)

What comes from the plan (the agent's asset research — every clip is a licence-checked library asset):
  {"segments": {"s01": [{"clip": "video-clips/….mp4", "in": 2.0, "rate": 1.0}, …], …},
   "title_clips": [{"clip": …, "in": …}], "title": "programme name", "music": {"src": "music/….mp3", "volume": 0.35},
   "sfx": {"whoosh": "sound-effects/….mp3", "hit": "sound-effects/….wav"}, "credits": "…"}
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telugu_script import subtitle_cues, write_ass, write_srt  # noqa: E402

LIB = Path("/home/user/creative-studio/media-library")
MOVE_LIMITS = {"zoom": (0.03, 0.10), "pan": (0.04, 0.12)}   # beyond this a digital move visibly softens 1080p footage


def sh(cmd):
    subprocess.run([str(c) for c in cmd], check=True)


def probe_duration(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout.strip())


# ------------------------------------------------------------------ grade matching


def clip_lab_stats(src: Path, t0: float, dur: float) -> dict:
    import cv2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-vf",
                          f"fps={8 / max(dur, 0.5):.4f},scale=64:36", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    px = np.frombuffer(raw, np.uint8).reshape(-1, 1, 3)
    lab = cv2.cvtColor(px, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    return {"mean": lab.mean(axis=0).tolist(), "std": lab.std(axis=0).tolist()}


def write_lut(src: dict, tgt: dict, path: Path, strength: float = 0.7, n: int = 33) -> dict:
    """Reinhard colour transfer in Lab, limited: σ ratio L∈[0.75,1.35], a/b∈[0.6,1.5]; mean shift L ±22, a/b ±9."""
    import cv2
    ms, ss = np.array(src["mean"]), np.maximum(np.array(src["std"]), 1.0)
    mt, st = np.array(tgt["mean"]), np.maximum(np.array(tgt["std"]), 1.0)
    ratio = np.clip(st / ss, [0.75, 0.6, 0.6], [1.35, 1.5, 1.5])
    shift = np.clip(mt - ms, [-16, -9, -9], [16, 9, 9])
    ratio = 1 + strength * (ratio - 1)
    shift = strength * shift
    g = np.linspace(0, 1, n, dtype=np.float32)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")  # .cube: red varies fastest
    rgb = np.stack([r, gg, b], axis=-1).reshape(-1, 1, 3)
    lab = cv2.cvtColor((rgb * 255).round().astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    lab = (lab - ms) * ratio + ms + shift
    out = cv2.cvtColor(np.clip(lab, 0, 255).round().astype(np.uint8).reshape(-1, 1, 3), cv2.COLOR_LAB2RGB).reshape(-1, 3) / 255.0
    with open(path, "w") as fh:
        fh.write(f"TITLE \"reference match\"\nLUT_3D_SIZE {n}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n")
        for row in out:
            fh.write(f"{row[0]:.5f} {row[1]:.5f} {row[2]:.5f}\n")
    return {"ratio": [round(float(x), 3) for x in ratio], "shift": [round(float(x), 2) for x in shift], "strength": strength}


def render_clip(src: Path, t0: float, dur: float, lut: Path, out: Path, w: int, h: int, fps: float, rate: float) -> None:
    """Graded, conformed intermediate: LUT → cover-scale/crop → output fps (speed change by setpts for rate ≠ 1)."""
    vf = (f"lut3d=file='{lut}':interp=tetrahedral,setpts=PTS/{rate:.4f},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={w}:{h},fps={fps:.6f},setsar=1,format=yuv420p")
    sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{dur * rate + 0.5:.3f}", "-i", src, "-vf", vf, "-an",
        "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-g", str(int(round(fps))), "-bf", "0",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", out])


def clip_motion(src: Path, t0: float, dur: float, stride: int = 3) -> dict:
    """The clip's own camera motion over the used range: zoom and pan per second (ORB + RANSAC similarity)."""
    import cv2
    w, h = 320, 180
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-vf",
                          f"scale={w}:{h}", "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
    fps_src = len(fr) / max(dur, 1e-3)
    orb = cv2.ORB_create(nfeatures=500, fastThreshold=12)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    zoom, panx, pany, steps = 1.0, 0.0, 0.0, 0
    prev = orb.detectAndCompute(fr[0], None) if len(fr) else (None, None)
    for i in range(stride, len(fr), stride):
        kp, des = orb.detectAndCompute(fr[i], None)
        if prev[1] is not None and des is not None and len(kp) >= 12 and len(prev[0]) >= 12:
            m = bf.match(prev[1], des)
            if len(m) >= 12:
                a = np.float32([prev[0][x.queryIdx].pt for x in m]); b = np.float32([kp[x.trainIdx].pt for x in m])
                M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                if M is not None and inl is not None and inl.sum() >= 10:
                    sc = math.hypot(M[0, 0], M[1, 0])
                    tx = M[0, 0] * w / 2 + M[0, 1] * h / 2 + M[0, 2] - w / 2
                    ty = M[1, 0] * w / 2 + M[1, 1] * h / 2 + M[1, 2] - h / 2
                    zoom *= sc; panx += tx / w; pany += ty / h; steps += 1
        prev = (kp, des)
    secs = max(1e-3, steps * stride / max(fps_src, 1))
    return {"zoom_per_s": (zoom ** (1 / secs) - 1) if steps else 0.0, "panx_per_s": panx / secs if steps else 0.0,
            "pany_per_s": pany / secs if steps else 0.0, "tracked_steps": steps}


def digital_move(ref_move: dict, own: dict, seconds: float) -> dict:
    """The move to add so clip motion + digital move ≈ the reference shot's camera move."""
    t = ref_move["type"]
    if t == "static":
        return {"type": "static", "amount": 0.0, "own": own}
    if t in ("push_in", "pull_out"):
        own_rate = own["zoom_per_s"] if t == "push_in" else -own["zoom_per_s"]
        need = ref_move["rate"] - max(0.0, own_rate)
        lim = MOVE_LIMITS["zoom"]
    else:
        sign = {"pan_right": -1, "pan_left": 1, "tilt_up": 1, "tilt_down": -1}[t]   # content direction of the move
        own_rate = sign * (own["panx_per_s"] if t.startswith("pan") else own["pany_per_s"])
        need = ref_move["rate"] - max(0.0, own_rate)
        lim = MOVE_LIMITS["pan"]
    amount = need * seconds
    if amount < 0.5 * lim[0]:
        return {"type": "static", "amount": 0.0, "note": "clip already moves like the reference", "own": own}
    return {"type": t, "amount": round(float(np.clip(amount, *lim)), 4), "ease": "linear", "own": own}


# ------------------------------------------------------------------ layout


def reference_pattern(bd: dict, fps_out: float) -> list[dict]:
    fps_ref = bd["source"]["fps"]
    pat = []
    shots = bd["shots"]
    for i, s in enumerate(shots):
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        tr = nxt["transition_in"] if nxt else None
        cam = s["camera"]
        mv = {"type": "static", "amount": 0.0}
        dur_meas = max(0.5, cam.get("measured_seconds") or s["duration"])
        m = cam.get("move", "static")
        if "push_in" in m or "pull_out" in m:
            mv = {"type": "push_in" if "push_in" in m else "pull_out", "rate": abs(cam["zoom_total"] - 1) / dur_meas}
        elif "pan_" in m or "tilt_" in m:
            key = next(k for k in ("pan_right", "pan_left", "tilt_up", "tilt_down") if k in m)
            mv = {"type": key, "rate": abs(cam["pan_x_frames"] if key.startswith("pan") else cam["pan_y_frames"]) / dur_meas}
        pat.append({"ref": s["index"], "duration": s["duration"], "move": mv, "grade": s["grade"],
                    "out": None if not tr else {"type": tr["type"] if tr["type"] in ("cut", "dissolve", "dip_to_black", "dip_to_white", "flash") else "cut",
                                                "frames": max(0, int(round(tr["frames"] * fps_out / fps_ref))),
                                                "audio_event": tr.get("audio_event")}})
    return pat


def speech_cut_offset(bd: dict) -> float:
    """Median time from a cut to the next speech onset in the reference (J-cut lead), bounded to [0, 1] s."""
    au = bd.get("audio") or {}
    sp = [s["start"] for s in au.get("speech", [])]
    cuts = [t["time"] + (t["duration"] / 2 if t["type"] != "cut" else 0) for t in bd["transitions"]]
    d = [min((s - c for c in cuts if 0 <= s - c <= 2.0), default=None) for s in sp]
    d = [x for x in d if x is not None]
    return float(np.clip(np.median(d), 0, 1.0)) if d else 0.3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path)
    ap.add_argument("--breakdown", type=Path, required=True)
    ap.add_argument("--script", type=Path, required=True)
    ap.add_argument("--voice", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--width", type=int, default=1920); ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=float, help="output frame rate (default: the reference's)")
    ap.add_argument("--timeline", default="timeline.json")
    ap.add_argument("--grade-strength", type=float, default=0.7)
    ap.add_argument("--gap", type=float, help="pause between voice segments (default: from the reference speech)")
    a = ap.parse_args(argv)
    P = a.project.resolve()
    bd = json.loads(a.breakdown.read_text())
    sc = json.loads(a.script.read_text())
    voice = json.loads((a.voice / "voice.json").read_text())
    plan = json.loads(a.plan.read_text())
    fps = a.fps or round(bd["source"]["fps"], 3)
    W, H = a.width, a.height
    pub = P / "public"
    (pub / "graded").mkdir(parents=True, exist_ok=True)
    (pub / "voice").mkdir(parents=True, exist_ok=True)
    (pub / "audio").mkdir(parents=True, exist_ok=True)
    if not (pub / "lib").exists():
        (pub / "lib").symlink_to(LIB)
    work = P / "work" / "recreate"
    work.mkdir(parents=True, exist_ok=True)
    pat = reference_pattern(bd, fps)
    asl = float(np.mean([p["duration"] for p in pat]))
    wts = np.array([p["duration"] for p in pat])
    look = {k: (np.average([p["grade"]["lab"][k] for p in pat], axis=0, weights=wts)).tolist() for k in ("mean", "std")}
    au = bd.get("audio") or {}

    # ---- voice layout
    sp = au.get("speech", [])
    gaps = [b["start"] - x["end"] for x, b in zip(sp, sp[1:]) if b["start"] > x["end"]]
    gap = a.gap if a.gap is not None else (float(np.clip(np.median(gaps), 0.35, 1.2)) if gaps else 0.6)
    lead = float(np.clip(sp[0]["start"], 0.6, 3.0)) if sp else max(1.0, 0.4 * pat[0]["duration"])
    segs = [s for s in sc["segments"] if s.get("speak", True)]
    title_seg = next((s for s in sc["segments"] if s["kind"] == "title"), None)
    placements, t = {}, lead
    for i, s in enumerate(segs):
        v = voice["segments"][s["id"]]
        pre = 0.35 if s["kind"] == "scripture" else 0.0
        t += pre
        placements[s["id"]] = round(t, 3)
        t += v["duration"]
        post = 0.45 if s["kind"] == "scripture" else 0.0
        joined = i + 1 < len(segs) and s["kind"] == "narration" and segs[i + 1]["kind"] == "scripture" and s["en"].rstrip().endswith(("said", "said,", ":"))
        t += post + (0.25 if joined else gap)
    voice_end = t
    # title card: where the reference shows its centre/top text (start or end), with the measured on-screen time
    centre = [x for x in bd.get("text", []) if x["position"] in ("centre", "top")]
    title_at_end = not centre or centre[-1]["start"] > 0.5 * bd["source"]["duration"]
    title_dur = float(np.clip(centre[-1]["end"] - centre[-1]["start"], 2.0, 6.0)) if centre else 3.0
    title_entrance = centre[-1]["entrance"] if centre else {"style": "fade/blur-in", "ramp_s": 0.5}
    tail = (title_dur + 1.0) if (title_seg and title_at_end) else 1.5
    total = voice_end + tail
    if title_seg and not title_at_end:
        shift = title_dur + 0.5
        placements = {k: round(v + shift, 3) for k, v in placements.items()}
        total += shift
    nframes = int(round(total * fps))

    # ---- segment spans → shots (reference pattern, in order)
    offset = speech_cut_offset(bd)
    spans = []
    for i, s in enumerate(segs):
        st = max(0.0, placements[s["id"]] - offset)
        spans.append({"seg": s, "start": st})
    if title_seg:
        spans.append({"seg": title_seg, "start": voice_end - 0.2 if title_at_end else 0.0})
    spans.sort(key=lambda x: x["start"])
    spans[0]["start"] = 0.0
    for i, s in enumerate(spans):
        s["end"] = spans[i + 1]["start"] if i + 1 < len(spans) else total
    # merge a lead-in narration ("Jesus said,") into the following scripture span: one picture idea
    merged = []
    for s in spans:
        if merged and merged[-1]["seg"]["kind"] == "narration" and s["seg"]["kind"] == "scripture" and \
                (merged[-1]["end"] - merged[-1]["start"]) < 0.8 * asl:
            merged[-1]["end"] = s["end"]; merged[-1]["also"] = s["seg"]["id"]
            continue
        merged.append(s)
    shots, pi, k = [], 0, 0
    used_clip_time: dict = {}
    for span in merged:
        sid = span["seg"]["id"]
        pool = plan["segments"].get(sid) or plan["segments"].get(span.get("also", ""), []) or \
            (plan.get("title_clips") if span["seg"]["kind"] == "title" else None)
        if not pool:
            raise SystemExit(f"plan has no clips for segment {sid}")
        length = span["end"] - span["start"]
        nshot = max(1, min(len(pool) * 2, int(round(length / asl))))
        durs = [pat[(pi + j) % len(pat)]["duration"] for j in range(nshot)]
        scale = length / sum(durs)
        for j in range(nshot):
            p = pat[pi % len(pat)]
            pi += 1
            choice = pool[j % len(pool)]
            k += 1
            shots.append({"id": f"shot{k:02d}", "seg": sid, "pattern": p, "clip": choice,
                          "start": span["start"] + sum(durs[:j]) * scale, "dur": durs[j] * scale})

    # ---- transitions (frames) and overlap layout: a transition of T frames makes the incoming shot start T/2 earlier
    out_shots, captions, cards, cues = [], [], [], []
    report = []
    for i, s in enumerate(shots):
        tin = shots[i - 1]["pattern"]["out"] if i > 0 else None
        if tin and tin["type"] != "cut":
            tin = dict(tin)
            tin["frames"] = max(2, min(tin["frames"], int(0.45 * min(s["dur"], shots[i - 1]["dur"]) * fps)))
        s["tin"] = tin
    for i, s in enumerate(shots):
        b0 = int(round(s["start"] * fps))
        b1 = int(round((s["start"] + s["dur"]) * fps)) if i + 1 < len(shots) else nframes
        tin = s["tin"]; tout = shots[i + 1]["tin"] if i + 1 < len(shots) else None
        f0 = b0 - (tin["frames"] // 2 if tin and tin["type"] != "cut" else 0)
        f1 = b1 + ((tout["frames"] - tout["frames"] // 2) if tout and tout["type"] != "cut" else 0)
        f0 = max(0, f0); f1 = min(nframes, f1)
        dur_f = f1 - f0
        clip = s["clip"]
        src = LIB / clip["clip"]
        rate = float(clip.get("rate", 1.0))
        src_len = probe_duration(src)
        need = dur_f / fps * rate
        t_in = float(clip.get("in", 0.0))
        # reuse of the same clip in one video: continue after the part already used, when there is room
        key = clip["clip"]
        if key in used_clip_time:   # the same clip again: continue after the part already shown, never repeat it
            t_in = used_clip_time[key] + 0.2 if used_clip_time[key] + 0.2 + need <= src_len - 0.05 else \
                max(0.0, min(t_in, src_len - 0.05 - need) - need - 0.5) if t_in > need + 0.5 else t_in
        if t_in + need > src_len - 0.05:
            t_in = max(0.0, src_len - 0.05 - need)
        if need > src_len:
            rate = max(0.5, src_len / (dur_f / fps) * 0.98)  # slow the clip rather than freeze
            need = dur_f / fps * rate
            t_in = 0.0
        used_clip_time[key] = t_in + need
        p = s["pattern"]
        own = clip_motion(src, t_in, need) if p["move"]["type"] != "static" else {"zoom_per_s": 0, "panx_per_s": 0, "pany_per_s": 0}
        move = digital_move(p["move"], own, dur_f / fps)
        move_tl = {k: v for k, v in move.items() if k in ("type", "amount", "ease")}
        lut = work / f"{s['id']}.cube"
        src_stats = clip_lab_stats(src, t_in, need)
        # target: the reference's overall look (60 %) nudged toward the specific reference shot (40 %)
        tgt = {k: (0.6 * np.array(look[k]) + 0.4 * np.array(p["grade"]["lab"][k])).tolist() for k in ("mean", "std")}
        g = write_lut(src_stats, tgt, lut, a.grade_strength)
        dst = pub / "graded" / f"{s['id']}.mp4"
        render_clip(src, t_in, dur_f / fps, lut, dst, W, H, fps, rate)
        out_shots.append({"id": s["id"], "from": f0, "durationInFrames": dur_f, "src": f"graded/{s['id']}.mp4", "trimBefore": 0,
                          "playbackRate": 1, "move": move_tl, "refShot": p["ref"],
                          "transitionIn": {"type": tin["type"], "durationInFrames": tin["frames"]} if tin and tin["type"] != "cut" else
                          ({"type": "cut", "durationInFrames": 0} if tin else None),
                          "slot": {"start": b0, "end": b1}})
        if tin and tin.get("audio_event") and plan.get("sfx"):
            kind = "whoosh" if "whoosh" in tin["audio_event"] else "hit"
            sfx = plan["sfx"].get(kind)
            if sfx:
                mid = b0 / fps
                cues.append({"src": f"lib/{sfx}", "at": round(max(0.0, mid - (0.55 if kind == "whoosh" else 0.0)), 3),
                             "volume": 0.35, "reason": f"reference has a {tin['audio_event']} at this transition"})
        report.append({"shot": s["id"], "segment": s["seg"], "ref_shot": p["ref"], "frames": [f0, f1], "cut_at": round(b0 / fps, 3),
                       "transition_in": tin, "move": move, "clip": clip["clip"], "clip_in": round(t_in, 3), "rate": rate,
                       "grade_target": p["grade"]["labels"], "lut": g})

    # ---- voice, subtitles, cards
    vcues = []
    for s in segs:
        vsrc = a.voice / voice["segments"][s["id"]]["file"]
        link = pub / "voice" / vsrc.name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(vsrc.resolve())
        vcues.append({"src": f"voice/{vsrc.name}", "at": placements[s["id"]], "volume": 1.0, "segment": s["id"]})
    cue_list = subtitle_cues(sc, voice, placements)
    bottom_ref = [x for x in bd.get("text", []) if x["position"] in ("bottom", "lower-third")]
    cap_fade = 1 if (bottom_ref and bottom_ref[0]["entrance"]["style"] == "cut-in") else 4
    for c in cue_list:
        captions.append({"from": int(round(c["start"] * fps)), "durationInFrames": max(1, int(round((c["end"] - c["start"]) * fps))),
                         "lines": c["lines"], "kind": c["kind"]})
    for s in segs:
        if s["kind"] == "scripture":
            v = voice["segments"][s["id"]]
            st = placements[s["id"]]
            cards.append({"from": int(round(st * fps)), "durationInFrames": int(round((v["duration"] + 0.4) * fps)),
                          "text": s["ref"]["local"], "style": "reference", "position": "top", "entrance": "fade",
                          "fadeFrames": int(round(0.4 * fps))})
    if title_seg:
        t0 = (voice_end + 0.3) if title_at_end else 0.4
        ramp = title_entrance.get("ramp_s", 0.5)
        cards.append({"from": int(round(t0 * fps)), "durationInFrames": int(round(title_dur * fps)), "text": title_seg["te"],
                      "sub": plan.get("credits"), "style": "title", "position": "centre",
                      "entrance": "cut" if title_entrance["style"] == "cut-in" else "fade", "fadeFrames": max(1, int(round(max(ramp, 0.3) * fps)))})
    # music: loop/trim the planned track to the programme length (48 kHz WAV for render.py)
    music = None
    if plan.get("music"):
        msrc = LIB / plan["music"]["src"]
        mwav = pub / "audio" / "music.wav"
        sh(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", msrc, "-t", f"{total:.3f}", "-af",
            f"afade=t=in:d=1.5,afade=t=out:st={max(0, total - 3.5):.3f}:d=3.5", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", mwav])
        music = "audio/music.wav"
    bars = bd.get("letterbox") or {}
    tl = {"meta": {"title": plan.get("title", sc["meta"].get("source", "")), "width": W, "height": H, "fps": fps,
                   "durationInFrames": nframes, "composition": "Cinematic",
                   "letterbox": bars.get("aspect") if bars.get("present") else None,
                   "vignette": plan.get("vignette", 0.35), "grain": plan.get("grain", 0.12),
                   "captionStyle": {"size": 50, "bottom": 70, "font": "sans"}},
          "shots": out_shots, "captions": captions, "cards": cards,
          "audio": {"music": music, "musicVolume": plan.get("music", {}).get("volume", 0.35) if music else 0,
                    "voice": vcues, "cues": cues, "duck": {"db": -9, "attack": 0.25, "release": 0.7, "pad": 0.2},
                    "loudness": {"I": -16, "TP": -1.5}}}
    tl["meta"]["captionStyle"]["fade"] = cap_fade
    (P / a.timeline).write_text(json.dumps(tl, ensure_ascii=False, indent=2))
    stem = (P / a.timeline).stem
    write_srt(cue_list, P / f"{stem}.te.srt")
    write_ass(cue_list, P / f"{stem}.te.ass", W, H)
    rep = {"reference": bd["source"]["file"], "fps": fps, "duration": round(total, 3), "average_shot_length_ref": round(asl, 3),
           "average_shot_length_out": round(total / len(out_shots), 3), "speech_cut_offset": offset, "voice_gap": gap,
           "placements": placements, "shots": report, "captions": len(captions), "cards": cards, "sfx": cues,
           "music": plan.get("music"), "voice_licence": voice.get("licence"), "voice_commercial_use": voice.get("commercial_use")}
    (P / f"{stem}.recreation.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    print(json.dumps({"timeline": str(P / a.timeline), "duration": rep["duration"], "shots": len(out_shots), "captions": len(captions),
                      "cards": len(cards), "sfx": len(cues), "asl_ref": rep["average_shot_length_ref"], "asl_out": rep["average_shot_length_out"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
