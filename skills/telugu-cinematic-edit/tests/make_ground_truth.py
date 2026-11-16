#!/usr/bin/env python3
"""Build a reference video whose edit is known exactly, to measure reference_breakdown.py against.

    /opt/cws-venv/bin/python make_ground_truth.py OUT_DIR [--library /home/user/creative-studio/media-library]

30 fps, 1920×1080, 15.83 s, five shots from licensed Mixkit clips in the media library:
  shot 1  forest path (real footage)                          → hard CUT at frame 90
  shot 2  still of green hills, synthetic PUSH-IN +15 %        → DISSOLVE frames 175–194 (20 f, ffmpeg xfade=fade)
  shot 3  still of a wheat field, synthetic PAN RIGHT          → DIP TO BLACK frames 256–279 (24 f, xfade=fadeblack)
  shot 4  candles (real footage)                              → FLASH frames 355–360 (6 f, xfade=fadewhite) + whoosh
  shot 5  person praying (real footage) + text:
          "THE GOOD SHEPHERD" centre, fades in 12.6–13.1 s, out at 15.4 s
          "మంచి కాపరి" bottom, cuts in at 14.0 s, out at 15.5 s
Audio: 120 BPM click track + pad, English speech (espeak-ng) at 1.0 s, a noise whoosh rising into the flash.
Writes OUT_DIR/reference.mp4 and OUT_DIR/truth.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

FPS = 30
CLIPS = {
    "path": "video-clips/mixkit-41574-walking-a-path-that-crosses-a-dense-forest-1080.mp4",
    "hills": "video-clips/mixkit-101520-green-hills-bathed-in-dusk-light-1080.mp4",
    "wheat": "video-clips/mixkit-5010-immense-wheat-field-seen-from-the-air-1080.mp4",
    "candles": "video-clips/mixkit-3461-lighting-candles-in-the-dark-1080.mp4",
    "praying": "video-clips/mixkit-22708-person-praying-in-front-of-an-altar-inside-a-church-1080.mp4",
}
D = [3.0, 3.5, 3.5, 3.5, 4.0]
X_DISS, X_DIP, X_FLASH = 20 / FPS, 24 / FPS, 6 / FPS


def sh(cmd):
    subprocess.run([str(c) for c in cmd], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--library", type=Path, default=Path("/home/user/creative-studio/media-library"))
    a = ap.parse_args()
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    lib = a.library
    norm = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={FPS},format=yuv420p,setsar=1"
    enc = ["-c:v", "libx264", "-crf", "16", "-preset", "fast", "-an"]
    sh(["ffmpeg", "-v", "error", "-y", "-ss", "2", "-i", lib / CLIPS["path"], "-t", D[0], "-vf", norm, *enc, out / "v0.mp4"])
    # stills → exact synthetic camera moves
    sh(["ffmpeg", "-v", "error", "-y", "-ss", "3", "-i", lib / CLIPS["hills"], "-frames:v", "1", out / "hills.png"])
    sh(["ffmpeg", "-v", "error", "-y", "-ss", "5", "-i", lib / CLIPS["wheat"], "-frames:v", "1", out / "wheat.png"])
    push = (f"scale=w='trunc(1920*(1+0.15*t/{D[1]})/2)*2':h='trunc(1080*(1+0.15*t/{D[1]})/2)*2':eval=frame,"
            f"crop=1920:1080,fps={FPS},format=yuv420p,setsar=1")
    sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", FPS, "-i", out / "hills.png", "-t", D[1], "-vf", push, *enc, out / "v1.mp4"])
    pan = f"scale=2560:1440,crop=1920:1080:x='(iw-1920)*t/{D[2]}':y=180,fps={FPS},format=yuv420p,setsar=1"
    sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", FPS, "-i", out / "wheat.png", "-t", D[2], "-vf", pan, *enc, out / "v2.mp4"])
    sh(["ffmpeg", "-v", "error", "-y", "-ss", "4", "-i", lib / CLIPS["candles"], "-t", D[3], "-vf", norm, *enc, out / "v3.mp4"])
    sh(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", lib / CLIPS["praying"], "-t", D[4], "-vf", norm, *enc, out / "v4.mp4"])

    o1 = D[0] + D[1] - X_DISS            # dissolve offset (s)
    o2 = o1 + D[2] - X_DIP
    o3 = o2 + D[3] - X_FLASH
    total = o3 + D[4]
    serif = lib / "fonts" / "InstrumentSerif-Regular.ttf"
    telugu = lib / "fonts" / "NotoSansTelugu-Regular.ttf"
    if not telugu.exists():
        telugu = Path("/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf")
    fc = ("".join(f"[{i}]settb=AVTB[i{i}];" for i in range(5)) +
          f"[i0][i1]concat=n=2:v=1:a=0[c01];"
          f"[c01][i2]xfade=transition=fade:duration={X_DISS:.6f}:offset={o1:.6f}[x1];"
          f"[x1][i3]xfade=transition=fadeblack:duration={X_DIP:.6f}:offset={o2:.6f}[x2];"
          f"[x2][i4]xfade=transition=fadewhite:duration={X_FLASH:.6f}:offset={o3:.6f}[x3];"
          f"[x3]drawtext=fontfile='{serif}':text='THE GOOD SHEPHERD':fontsize=110:fontcolor=white:"
          f"x=(w-tw)/2:y=(h-th)/2-40:enable='between(t,12.6,15.4)':alpha='if(lt(t,13.1),(t-12.6)/0.5,1)',"
          f"drawtext=fontfile='{telugu}':text='మంచి కాపరి':fontsize=64:fontcolor=white:borderw=3:bordercolor=black:"
          f"x=(w-tw)/2:y=h*0.84:enable='between(t,14.0,15.5)'[v]")
    sh(["ffmpeg", "-v", "error", "-y", *sum((["-i", out / f"v{i}.mp4"] for i in range(5)), []), "-filter_complex", fc,
        "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", out / "video.mp4"])

    # audio
    sr = 48000
    n = int(round(total * sr))
    t = np.arange(n) / sr
    rng = np.random.default_rng(3)
    y = 0.03 * np.sin(2 * np.pi * 110 * t) + 0.02 * np.sin(2 * np.pi * 164.8 * t)
    beats = np.arange(0.25, total, 0.5)
    click = np.exp(-np.arange(int(0.03 * sr)) / (0.004 * sr)) * rng.standard_normal(int(0.03 * sr)) * 0.5
    for b in beats:
        i = int(b * sr)
        y[i:i + len(click)] += click[:max(0, min(len(click), n - i))]
    flash_t = o3 + X_FLASH / 2
    wl = int(0.6 * sr)
    ws = int(flash_t * sr) - wl
    whoosh = rng.standard_normal(wl) * np.linspace(0, 1, wl) ** 2 * 0.35
    y[ws:ws + wl] += whoosh
    sh(["espeak-ng", "-v", "en-us", "-s", "150", "-w", out / "speech.wav", "In every season of life, we search for direction."])
    import soundfile as sf
    sp, ssr = sf.read(str(out / "speech.wav"), dtype="float32")
    import librosa
    sp = librosa.resample(sp, orig_sr=ssr, target_sr=sr)
    i0 = int(1.0 * sr)
    y[i0:i0 + len(sp)] += 0.5 * sp[: n - i0]
    sf.write(str(out / "audio.wav"), np.clip(y, -1, 1).astype(np.float32), sr)
    sh(["ffmpeg", "-v", "error", "-y", "-i", out / "video.mp4", "-i", out / "audio.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out / "reference.mp4"])
    f = lambda s: int(round(s * FPS))  # noqa: E731
    truth = {
        "fps": FPS, "frames": f(total), "duration": round(total, 4),
        "transitions": [
            {"type": "cut", "start": f(D[0])},
            {"type": "dissolve", "start": f(o1), "frames": 20},
            {"type": "dip_to_black", "start": f(o2), "frames": 24},
            {"type": "flash", "start": f(o3), "frames": 6, "audio_event": "whoosh"},
        ],
        "shots": 5,
        "camera": {"2": "push_in", "3": "pan_right"},
        "text": [{"text": "THE GOOD SHEPHERD", "start": 12.6, "end": 15.4, "position": "centre", "entrance": "fade/blur-in"},
                 {"text": "మంచి కాపరి", "start": 14.0, "end": 15.5, "position": "bottom", "entrance": "cut-in"}],
        "tempo_bpm": 120, "speech_contains": ["season", "direction"],
    }
    (out / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2))
    print(json.dumps(truth, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
