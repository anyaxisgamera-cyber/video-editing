#!/usr/bin/env python3
"""Measure audio/picture sync of a rendered master against its compiled timeline.

    /opt/cws-venv/bin/python sync_check.py MASTER.mp4 timeline.json [--max-scenes 40]

Audio: every SFX cue is located in the master by cross-correlating the effect's own waveform against the mix
(template matching, sample-accurate even under music) and compared with its planned start.
Picture: for every transition, the centroid of its excess frame-to-frame change (above the scenes' own animation
baseline) is compared with the planned boundary the transition is centred on. (A crossover/"closer to scene B"
metric is biased by design: the entering layer is drawn on top, so it dominates before p=0.5.)
Pass: median |audio offset| <= 25 ms and median |picture offset| <= 1.5 frames.
"""

import argparse
import json
import subprocess
import sys

import numpy as np

SR = 22050


def audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def frames_gray(path, t0, t1, w=160):
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t0):.3f}", "-to", f"{t1:.3f}", "-i", path, "-vf", f"scale={w}:-2,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
                           capture_output=True, text=True).stdout.strip().split(",")
    W, H = int(probe[0]), int(probe[1])
    h = int(round(H * w / W / 2) * 2)
    n = len(out) // (w * h)
    return np.frombuffer(out[: n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("master")
    ap.add_argument("timeline")
    ap.add_argument("--max-scenes", type=int, default=40)
    a = ap.parse_args(argv)
    from pathlib import Path
    from scipy.signal import correlate
    tl = json.load(open(a.timeline))
    fps = tl["meta"]["fps"]
    y = audio(a.master)
    public = Path(a.timeline).resolve().parent / "public"
    cache = {}
    a_off = []
    for c in tl["audio"]["cues"]:
        src = public / c["src"]
        if not src.exists():
            continue
        if c["src"] not in cache:
            cache[c["src"]] = audio(str(src))
        clip = cache[c["src"]]
        n = int(0.5 * SR)
        # lock onto the effect's loudest 0.5 s (a reversed swell is near-silent at its start);
        # O(N) moving sum via cumsum, computed once per effect file
        if ("w0", c["src"]) not in cache:
            if len(clip) > n:
                cs = np.concatenate([[0.0], np.cumsum(clip.astype(np.float64) ** 2)])
                cache[("w0", c["src"])] = int(np.argmax(cs[n:] - cs[:-n]))
            else:
                cache[("w0", c["src"])] = 0
        w0 = cache[("w0", c["src"])]
        tpl = clip[w0: w0 + n]
        lo = int((c["at"] - 0.25) * SR) + w0
        if lo < 0 or lo + int(0.5 * SR) + len(tpl) > len(y):
            continue
        win = y[lo: lo + int(0.5 * SR) + len(tpl)]
        cc = correlate(win, tpl, mode="valid", method="fft")
        k = int(np.argmax(cc))
        norm = float(np.max(cc) / (np.linalg.norm(tpl) * np.linalg.norm(win[k:k + len(tpl)]) + 1e-9))
        meas = (lo + k - w0) / SR
        a_off.append({"kind": c.get("kind", "manual"), "planned_at": c["at"], "measured_at": round(meas, 4),
                      "offset_ms": round((meas - c["at"]) * 1000, 2), "match": round(norm, 3)})
    v_off = []
    for s in tl["scenes"][1: a.max_scenes]:
        B = s["slot"]["start"] / fps
        prev = next(p for p in tl["scenes"] if p["slot"]["end"] == s["slot"]["start"])
        tr = prev.get("transition", {})
        T = tr.get("durationInFrames", 0) if tr else 0
        if T == 0:
            continue
        half = T / 2 / fps
        pad = 0.8  # seconds of context on both sides to estimate the scenes' own animation baseline
        t0 = B - half - pad
        fr = frames_gray(a.master, t0, B + half + pad)
        if len(fr) < 8:
            continue
        d = np.r_[0.0, [np.mean(np.abs(fr[i] - fr[i - 1])) for i in range(1, len(fr))]]
        i0, i1 = int(round(pad * fps)), int(round((pad + 2 * half) * fps)) + 1
        base = np.median(np.r_[d[1:i0], d[i1:]])
        w = np.clip(d[i0:i1 + 1] - base, 0, None)  # excess change during the transition window
        if w.sum() <= 0:
            continue
        # frame i holds the change between i-1 and i → its time is the midpoint (i - 0.5)/fps
        x = float((w * (np.arange(i0, i0 + len(w)) - 0.5)).sum() / w.sum())
        meas = t0 + x / fps
        v_off.append({"scene": s["id"], "transition": tr["type"], "planned": round(B, 3), "measured_change_centroid": round(float(meas), 3),
                      "offset_frames": round(float((meas - B) * fps), 2)})
    am = float(np.median([abs(o["offset_ms"]) for o in a_off])) if a_off else None
    vm = float(np.median([abs(o["offset_frames"]) for o in v_off])) if v_off else None
    rep = {"audio_events": len(a_off), "audio_median_abs_offset_ms": am,
           "audio_max_abs_offset_ms": max((abs(o["offset_ms"]) for o in a_off), default=None),
           "picture_transitions": len(v_off), "picture_median_abs_offset_frames": vm,
           "picture_max_abs_offset_frames": max((abs(o["offset_frames"]) for o in v_off), default=None),
           "passed": bool(am is not None and am <= 25 and vm is not None and vm <= 1.5),
           "audio": a_off, "picture": v_off}
    print(json.dumps(rep, indent=2))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
