#!/usr/bin/env python3
"""Validate a finished Telugu cinematic render against its timeline, script and voice — evidence, not assumptions.

    /opt/cws-venv/bin/python validate_output.py PROJECT --video renders/x.mp4 [--timeline timeline.json]
        [--script script/script.json] [--voice voice] [--no-asr] [--no-ocr]

Checks (each PASS/FAIL with the measurement):
  container     file exists, H.264 + AAC, expected resolution / fps / frame count / duration, full decode without errors
  picture       blackdetect: every black stretch ≥ 0.25 s lies inside an intended dip/fade; freezedetect: no frozen
                picture ≥ 2.5 s (title cards over moving footage still move); one frame per shot is not black
  sound         silencedetect: no silence ≥ 1.0 s inside the programme; EBU R128 −16 ±0.5 LUFS, ≤ −1.5 dBTP
  sync          every voice segment is located in the final mix by cross-correlation: |offset| ≤ 20 ms
  script        every subtitle cue is exact text of the validated Telugu script (scripture = exact corpus text);
                every spoken segment has voice + subtitles; scripture verses re-checked against the corpus
  subtitles     Tesseract (tel) on the rendered frame at each cue's midpoint: Telugu text present in the subtitle band,
                CER reported (Tesseract's Telugu model is imperfect — presence + timing are the pass criteria)
  speech        Telugu ASR of the final mix in each voice window: CER vs the script (music + ducking included)
  provenance    every shot's clip is a catalogued library asset; licences and commercial-use flags listed
Writes PROJECT/renders/<video>.validation.json and .VALIDATION.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bible  # noqa: E402
from telugu_text import cer  # noqa: E402

LIB = Path("/home/user/creative-studio/media-library")


def run(cmd, text: bool = True, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=text, **kw)


def ffprobe(p: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-count_packets", "-show_streams", "-show_format", "-of", "json", p], check=True).stdout)


def intervals(stderr: str, a: str, b: str) -> list[tuple[float, float]]:
    st = [float(x) for x in re.findall(rf"{a}:\s*([\d.]+)", stderr)]
    en = [float(x) for x in re.findall(rf"{b}:\s*([\d.]+)", stderr)]
    return list(zip(st, en + [None] * (len(st) - len(en))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--timeline", default="timeline.json")
    ap.add_argument("--script", default="script/script.json")
    ap.add_argument("--voice", default="voice")
    ap.add_argument("--no-asr", action="store_true")
    ap.add_argument("--no-ocr", action="store_true")
    a = ap.parse_args(argv)
    P = a.project.resolve()
    V = a.video if a.video.is_absolute() else P / a.video
    tl = json.loads((P / a.timeline).read_text())
    sc = json.loads((P / a.script).read_text())
    voice = json.loads((P / a.voice / "voice.json").read_text())
    rec = json.loads((P / f"{Path(a.timeline).stem}.recreation.json").read_text())
    fps = tl["meta"]["fps"]
    checks: list[dict] = []

    def check(group, name, ok, detail):
        checks.append({"group": group, "check": name, "passed": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + f"[{group}] {name}: {detail}", flush=True)

    # ---------------- container
    check("container", "file exists", V.exists() and V.stat().st_size > 0, f"{V} ({V.stat().st_size if V.exists() else 0} bytes)")
    pr = ffprobe(V)
    v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    au = next((s for s in pr["streams"] if s["codec_type"] == "audio"), None)
    n, d = v["r_frame_rate"].split("/")
    frames = int(v.get("nb_read_packets") or 0)
    dur = float(pr["format"]["duration"])
    exp_frames = tl["meta"]["durationInFrames"]
    check("container", "codecs", v["codec_name"] == "h264" and au and au["codec_name"] == "aac", f"{v['codec_name']} / {au and au['codec_name']}")
    check("container", "geometry", (v["width"], v["height"]) == (tl["meta"]["width"], tl["meta"]["height"]), f"{v['width']}×{v['height']}")
    check("container", "frame rate", abs(float(n) / float(d) - fps) < 0.01, f"{float(n) / float(d):.3f}")
    check("container", "frame count", frames == exp_frames, f"{frames} vs {exp_frames}")
    check("container", "duration", abs(dur - exp_frames / fps) < 0.1, f"{dur:.3f}s vs {exp_frames / fps:.3f}s")
    check("container", "audio duration", au and abs(float(au.get("duration", 0)) - dur) < 0.1, au and au.get("duration"))
    dec = run(["ffmpeg", "-v", "error", "-i", V, "-f", "null", "-"])
    check("container", "full decode", not dec.stderr.strip(), dec.stderr.strip()[:300] or "no errors")

    # ---------------- picture
    intended = []
    for s in tl["shots"]:
        t = s.get("transitionIn")
        if t and t["type"] in ("dip_to_black", "flash", "dip_to_white"):
            intended.append(((s["from"] - 2) / fps, (s["from"] + t["durationInFrames"] + 2) / fps))
    intended.append((0, 0.6))                                   # possible fade-in
    intended.append((dur - 3.0, dur + 1))                       # end fade-out
    bd = run(["ffmpeg", "-hide_banner", "-nostats", "-i", V, "-vf", "blackdetect=d=0.25:pix_th=0.08", "-an", "-f", "null", "-"]).stderr
    blacks = [(float(x), float(y)) for x, y in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd)]
    stray = [b for b in blacks if not any(b[0] >= i0 - 0.05 and b[1] <= i1 + 0.05 for i0, i1 in intended)]
    check("picture", "no unintended black", not stray, f"black stretches {blacks}; outside intended dips: {stray}")
    fz = run(["ffmpeg", "-hide_banner", "-nostats", "-i", V, "-vf", "freezedetect=n=0.002:d=2.5", "-an", "-f", "null", "-"]).stderr
    freezes = intervals(fz, "freeze_start", "freeze_end")
    check("picture", "no frozen picture ≥ 2.5 s", not freezes, freezes or "none")
    dark = []
    for s in tl["shots"]:
        mid = (s["from"] + s["durationInFrames"] / 2) / fps
        raw = run(["ffmpeg", "-v", "error", "-ss", f"{mid:.3f}", "-i", V, "-frames:v", "1", "-vf", "scale=64:36", "-pix_fmt", "gray",
                   "-f", "rawvideo", "-"], text=False).stdout
        lum = np.frombuffer(raw, np.uint8)
        if lum.size and lum.mean() < 8:
            dark.append(s["id"])
    check("picture", "every shot shows picture at its midpoint", not dark, dark or "all shots visible")

    # ---------------- sound
    sd = run(["ffmpeg", "-hide_banner", "-nostats", "-i", V, "-af", "silencedetect=n=-50dB:d=1.0", "-vn", "-f", "null", "-"]).stderr
    sil = [(float(x), float(y) if y else dur) for x, y in intervals(sd, "silence_start", "silence_end")]
    sil_in = [s for s in sil if s[0] > 0.5 and s[1] < dur - 1.0]
    check("sound", "no silent sections ≥ 1 s", not sil_in, sil or "none")
    eb = run(["ffmpeg", "-hide_banner", "-nostats", "-i", V, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    summ = eb[eb.rfind("Summary:"):]
    I = float(summ.split("I:")[1].split("LUFS")[0]); TP = float(summ.split("Peak:")[1].split("dBFS")[0])
    check("sound", "loudness −16 ±0.5 LUFS, ≤ −1.5 dBTP", abs(I + 16) <= 0.5 and TP <= -1.5, f"I={I} LUFS, TP={TP} dBTP")

    # ---------------- sync: locate each voice segment in the final mix
    import soundfile as sf
    import librosa
    mix = run(["ffmpeg", "-v", "error", "-i", V, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], text=False)
    mixs = np.frombuffer(mix.stdout, np.float32)
    offs = {}
    for c in tl["audio"]["voice"]:
        x, sr = sf.read(str(P / "public" / c["src"]), dtype="float32", always_2d=True)
        x = librosa.resample(x.mean(axis=1), orig_sr=sr, target_sr=16000)
        a0 = int((c["at"] - 0.3) * 16000)
        seg = mixs[max(0, a0): a0 + len(x) + int(0.6 * 16000)]
        if len(seg) < len(x):
            offs[c["segment"]] = None
            continue
        from scipy.signal import correlate
        cc = correlate(seg, x, mode="valid", method="fft")
        lag = int(np.argmax(cc)) + max(0, a0) - int(c["at"] * 16000)
        offs[c["segment"]] = round(lag / 16, 2)  # ms
    worst = max((abs(v) for v in offs.values() if v is not None), default=None)
    check("sync", "voice segments within ±20 ms of plan", worst is not None and worst <= 20 and None not in offs.values(),
          f"offsets ms {offs}")

    # ---------------- script / subtitles text integrity
    by_id = {s["id"]: s for s in sc["segments"]}
    bad, missing = [], []
    for cap in tl["captions"]:
        txt = cap["lines"].replace("\n", " ")
        if not any(txt in (s.get("te") or "") or txt == (s.get("ref") or {}).get("local") for s in sc["segments"]):
            bad.append(txt)
    for s in sc["segments"]:
        if s.get("speak", True):
            if s["id"] not in voice["segments"]:
                missing.append(f"{s['id']}: no voice")
            joined = " ".join(c["lines"].replace("\n", " ") for c in tl["captions"])
            if s["te"] not in joined and not all(part in joined for part in re.split(r"(?<=[.,!?])\s+", s["te"]) if part):
                missing.append(f"{s['id']}: subtitles do not contain the full segment text")
    check("script", "every subtitle is exact script text", not bad, bad or f"{len(tl['captions'])} cues verified")
    check("script", "every spoken segment has voice + complete subtitles", not missing, missing or "all segments covered")
    vers = []
    for s in sc["segments"]:
        if s["kind"] == "scripture":
            v_ = bible.lookup(s["ref"]["usfm"], s["ref"]["version"])
            vers.append((s["ref"]["usfm"], s["te"] == v_["text"]))
    check("script", "scripture = exact corpus text", all(ok for _, ok in vers), vers)
    check("script", "script validation passed", sc.get("validation", {}).get("passed"), sc.get("validation", {}).get("errors"))

    # ---------------- rendered subtitles (OCR)
    if not a.no_ocr:
        import cv2
        import tempfile
        cers, absent = [], []
        H = tl["meta"]["height"]
        with tempfile.TemporaryDirectory() as td:
            for i, cap in enumerate(tl["captions"]):
                mid = (cap["from"] + cap["durationInFrames"] / 2) / fps
                png = Path(td) / f"c{i}.png"
                run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", V, "-frames:v", "1", png], check=True)
                g = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
                band = g[int(H * 0.68):, :]
                m = 255 - ((band > 205).astype(np.uint8) * 255)
                m = cv2.resize(m, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
                cv2.imwrite(str(Path(td) / "b.png"), m)
                txt = run(["tesseract", Path(td) / "b.png", "stdout", "-l", "tel", "--psm", "6"]).stdout
                te_chars = len(re.findall(r"[ఀ-౿]", txt))
                if te_chars < 3:
                    absent.append(round(mid, 2))
                cers.append(round(cer(cap["lines"], txt), 3))
        check("subtitles", "Telugu subtitle visible at every cue", not absent, f"missing at {absent}" if absent else f"{len(cers)} cues")
        check("subtitles", "OCR character error (informational)", True, f"mean CER {np.mean(cers):.3f}, per cue {cers}")

    # ---------------- speech in the final mix (ASR)
    if not a.no_asr:
        from telugu_tts import TeluguASR, ASR_SECOND
        asr = TeluguASR()
        asr2 = None
        res = {}
        for c in tl["audio"]["voice"]:
            vd = voice["segments"][c["segment"]]["duration"]
            a0 = int(c["at"] * 16000); a1 = int((c["at"] + vd) * 16000)
            hyp = asr.transcribe(mixs[a0:a1], 16000)
            ref = voice["segments"][c["segment"]]["spoken_text"]
            e = cer(ref, hyp)
            if e > 0.15:
                asr2 = asr2 or TeluguASR(ASR_SECOND)
                e = min(e, cer(ref, asr2.transcribe(mixs[a0:a1], 16000)))
            res[c["segment"]] = round(e, 3)
        check("speech", "voice intelligible in the final mix (CER ≤ 0.15 per segment)", all(v <= 0.15 for v in res.values()), res)

    # ---------------- provenance
    cat = json.loads((LIB / "catalog.json").read_text())["assets"]
    by_path = {e["local_path"]: e for e in cat}
    prov, unknown = {}, []
    for s in rec["shots"]:
        e = by_path.get(s["clip"])
        if not e:
            unknown.append(s["clip"])
        else:
            prov[s["clip"]] = {"license": e["license"], "commercial_use": e.get("commercial_use"), "source": e.get("source_page")}
    music = tl["audio"].get("music")
    check("provenance", "every clip is a catalogued, licence-checked asset", not unknown, unknown or f"{len(prov)} clips")
    vlic = {"licence": voice.get("licence"), "commercial_use": voice.get("commercial_use")}
    check("provenance", "voice licence recorded", vlic["licence"] is not None, vlic)
    passed = all(c["passed"] for c in checks)
    out = {"video": str(V), "passed": passed, "checks": checks, "clips": prov, "voice": vlic, "music": music,
           "sfx": [c["src"] for c in tl["audio"].get("cues", [])]}
    vj = V.with_suffix(".validation.json")
    vj.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    md = [f"# Validation — {V.name}", "", f"**Result: {'PASSED' if passed else 'FAILED'}** ({sum(c['passed'] for c in checks)}/{len(checks)} checks)", "",
          "| Group | Check | Result | Measurement |", "|---|---|---|---|"]
    for c in checks:
        md.append(f"| {c['group']} | {c['check']} | {'PASS' if c['passed'] else 'FAIL'} | {str(c['detail'])[:220].replace('|', '/')} |")
    md += ["", "## Assets", ""] + [f"- `{k}` — {v['license']} (commercial use: {v['commercial_use']}) — {v['source']}" for k, v in prov.items()]
    md += [f"- Voice: {vlic['licence']} (commercial use: {vlic['commercial_use']})", f"- Music: {music}",
           f"- SFX: {out['sfx']}"]
    V.with_suffix(".VALIDATION.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n{'PASSED' if passed else 'FAILED'}: {sum(c['passed'] for c in checks)}/{len(checks)} → {vj}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
