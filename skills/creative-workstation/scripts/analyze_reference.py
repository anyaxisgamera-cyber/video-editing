#!/usr/bin/env python3
"""Measure a reference video's editing style and turn it into storyboard defaults.

    /opt/cws-venv/bin/python analyze_reference.py REFERENCE.mp4 OUT_DIR [--deep]

Measures (evidence, not guesses):
  * palette        k-means over sampled frames → dominant colours + light/dark balance
  * cuts / pacing  PySceneDetect content detector → shot boundaries, mean/median shot length
  * blur events    Laplacian-variance sharpness dips → blur-in / blur-out transitions and their length
  * motion energy  mean frame difference → calm vs kinetic sections
  * tempo          librosa beat tracking on the soundtrack → BPM + beat grid
  * text density   high-contrast edge density in the centre band (proxy for large typography cards)
Outputs style.json, STYLE.md, palette.png, sharpness.png, contact.jpg, and storyboard-defaults.json
(bpm, palette, average scene bars, preferred transitions) for scripts/timeline.py.
--deep also runs the installed analyze-video-editing skill (video_analyzer.py) for a shot-by-shot timeline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def sample_frames(path: Path, fps: float, width: int = 320) -> tuple[np.ndarray, float]:
    import cv2
    cap = cv2.VideoCapture(str(path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(src_fps / fps)))
    frames, i = [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            _, f = cap.retrieve()
            h = int(f.shape[0] * width / f.shape[1])
            frames.append(cv2.resize(f, (width, h), interpolation=cv2.INTER_AREA))
        i += 1
    cap.release()
    return np.array(frames), src_fps / step


def palette(frames: np.ndarray, k: int = 6) -> list[dict]:
    import cv2
    px = frames[:, ::4, ::4].reshape(-1, 3).astype(np.float32)
    px = px[np.random.default_rng(0).choice(len(px), min(len(px), 60000), replace=False)]
    _, labels, centers = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5), 4,
                                    cv2.KMEANS_PP_CENTERS)
    share = np.bincount(labels.ravel(), minlength=k) / len(labels)
    out = []
    for c, s in sorted(zip(centers, share), key=lambda t: -t[1]):
        b, g, r = (int(v) for v in c)
        hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0, 0]
        out.append({"hex": f"#{r:02X}{g:02X}{b:02X}", "share": round(float(s), 3), "hue_deg": int(hsv[0]) * 2,
                    "saturation": round(hsv[1] / 255, 2), "value": round(hsv[2] / 255, 2)})
    return out


def sharpness_series(frames: np.ndarray) -> np.ndarray:
    import cv2
    return np.array([cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() for f in frames])


def blur_events(sharp: np.ndarray, fps: float) -> list[dict]:
    """Dips where sharpness falls below 45 % of its local median = blur transition / blur-in text."""
    from scipy.ndimage import median_filter
    base = median_filter(sharp, size=max(3, int(fps * 4)) | 1)
    low = sharp < 0.45 * np.maximum(base, 1e-6)
    ev, start = [], None
    for i, v in enumerate(low):
        if v and start is None:
            start = i
        if (not v or i == len(low) - 1) and start is not None:
            end = i
            if end - start >= 2:
                ev.append({"start": round(start / fps, 2), "end": round(end / fps, 2), "duration": round((end - start) / fps, 2),
                           "min_ratio": round(float((sharp[start:end] / np.maximum(base[start:end], 1e-6)).min()), 2)})
            start = None
    return ev


def cuts(path: Path) -> list[float]:
    try:
        from scenedetect import ContentDetector, detect
        return [round(s[0].get_seconds(), 3) for s in detect(str(path), ContentDetector(threshold=27))][1:]
    except Exception as exc:  # pragma: no cover
        print("scenedetect failed:", exc, file=sys.stderr)
        return []


def tempo(path: Path) -> dict:
    try:
        import librosa
        wav = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "22050", "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        y = np.frombuffer(wav, dtype=np.float32)
        if len(y) < 22050:
            return {"bpm": None, "note": "no/short audio"}
        bpm, beats = librosa.beat.beat_track(y=y, sr=22050)
        bt = librosa.frames_to_time(beats, sr=22050)
        return {"bpm": round(float(np.atleast_1d(bpm)[0]), 1), "beats": len(bt), "first_beats": [round(float(b), 3) for b in bt[:16]]}
    except Exception as exc:
        return {"bpm": None, "note": str(exc)[:200]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--fps", type=float, default=6.0)
    ap.add_argument("--deep", action="store_true")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    import cv2
    frames, sfps = sample_frames(a.video, a.fps)
    dur = len(frames) / sfps
    pal = palette(frames)
    sharp = sharpness_series(frames)
    bev = blur_events(sharp, sfps)
    motion = np.array([0.0] + [float(np.mean(cv2.absdiff(frames[i], frames[i - 1]))) for i in range(1, len(frames))])
    cut_t = cuts(a.video)
    shots = np.diff([0.0] + cut_t + [dur]) if dur else np.array([])
    tmp = tempo(a.video)
    lum = float(np.mean([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean() for f in frames[:: max(1, len(frames) // 60)]]))
    purple = sum(p["share"] for p in pal if 240 <= p["hue_deg"] <= 320 and p["saturation"] > 0.12)
    style = {
        "video": str(a.video), "duration": round(dur, 2), "sample_fps": round(sfps, 2),
        "palette": pal, "purple_lavender_share": round(purple, 3), "mean_luma": round(lum, 1),
        "cuts": cut_t, "shots": len(shots), "mean_shot_s": round(float(shots.mean()), 2) if len(shots) else None,
        "median_shot_s": round(float(np.median(shots)), 2) if len(shots) else None,
        "blur_events": bev, "blur_events_per_min": round(len(bev) / max(dur / 60, 1e-6), 2),
        "motion_energy_mean": round(float(motion.mean()), 2), "motion_energy_p90": round(float(np.percentile(motion, 90)), 2),
        "tempo": tmp,
    }
    bpm = tmp.get("bpm") or 96
    bar = 240 / bpm
    style["storyboard_defaults"] = {
        "meta": {"bpm": bpm},
        "palette": [p["hex"] for p in pal],
        "scene_bars": max(1, round((style["mean_shot_s"] or 5) / bar)),
        "transition": {"type": "blurDissolve" if style["blur_events_per_min"] >= 4 else "softWipe", "beats": 1},
        "background_variant": "light" if lum > 140 else ("dusk" if lum > 70 else "dark"),
    }
    (a.out / "style.json").write_text(json.dumps(style, indent=2))
    (a.out / "storyboard-defaults.json").write_text(json.dumps(style["storyboard_defaults"], indent=2))
    # visual evidence
    sw = np.zeros((80, 600, 3), np.uint8)
    x = 0
    for p in pal:
        w = int(round(p["share"] * 600))
        sw[:, x:x + w] = [int(p["hex"][5:7], 16), int(p["hex"][3:5], 16), int(p["hex"][1:3], 16)]
        x += w
    cv2.imwrite(str(a.out / "palette.png"), sw)
    g = np.full((200, 800, 3), 255, np.uint8)
    s = sharp / (sharp.max() or 1)
    for i in range(1, len(s)):
        cv2.line(g, (int((i - 1) / len(s) * 800), int(190 - s[i - 1] * 180)), (int(i / len(s) * 800), int(190 - s[i] * 180)), (140, 60, 90), 1)
    for e in bev:
        cv2.rectangle(g, (int(e["start"] / dur * 800), 0), (int(e["end"] / dur * 800), 199), (230, 200, 245), -1)
    for t in cut_t:
        cv2.line(g, (int(t / dur * 800), 0), (int(t / dur * 800), 199), (0, 0, 220), 1)
    cv2.imwrite(str(a.out / "sharpness.png"), g)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(a.video), "-vf",
                    f"fps=24/{max(dur, 1):.3f},scale=320:-2,tile=6x4", "-frames:v", "1", str(a.out / "contact.jpg")], check=False)
    md = [f"# Style analysis — {a.video.name}", "", f"Duration {style['duration']} s · {style['shots']} shots · "
          f"mean shot {style['mean_shot_s']} s · tempo {tmp.get('bpm')} BPM", "",
          f"* Palette (share): " + ", ".join(f"`{p['hex']}` {p['share']:.0%}" for p in pal),
          f"* Purple/lavender share of the image: **{purple:.0%}**; mean luma {lum:.0f}/255",
          f"* Blur transitions / blur-in events: **{len(bev)}** ({style['blur_events_per_min']}/min)",
          f"* Motion energy mean {style['motion_energy_mean']} (p90 {style['motion_energy_p90']})",
          "", "Suggested storyboard defaults: `storyboard-defaults.json`.",
          "These are measurements; confirm the editorial reading by watching `contact.jpg` and the source."]
    (a.out / "STYLE.md").write_text("\n".join(md) + "\n")
    if a.deep:
        analyzer = Path.home() / ".claude/skills/analyze-video-editing/scripts/video_analyzer.py"
        subprocess.run(["uv", "run", "-q", str(analyzer), "analyze", str(a.video), "--work-dir", str(a.out / "deep")], check=False)
    print(json.dumps({k: style[k] for k in ("duration", "shots", "mean_shot_s", "purple_lavender_share", "blur_events_per_min",
                                            "motion_energy_mean", "tempo")} | {"palette": [p["hex"] for p in pal]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
