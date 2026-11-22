"""Contact sheets for picking footage: one thumbnail every STEP seconds, timecode burned in.

Usage: python -I build/footage_sheets.py VIDEO OUT_DIR [--step 4] [--start 0] [--end 0] [--cols 8] [--rows 6]
Writes OUT_DIR/<stem>_NN.jpg; each tile is labelled with its source time in seconds.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--step", type=float, default=4.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0)
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=6)
    a = ap.parse_args()
    src, out = Path(a.video), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    end = a.end or duration(src)
    per = a.cols * a.rows
    t, n = a.start, 0
    while t < end:
        span = min(per * a.step, end - t)
        vf = (f"fps=1/{a.step},scale=240:-2,"
              "drawtext=text='%{pts\\:hms}':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black@0.6,"
              f"tile={a.cols}x{a.rows}:padding=2")
        # pts of the sampled frames are relative to -ss; add the offset via setpts so labels show source time
        vf = f"setpts=PTS+{t}/TB," + vf
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-t", str(span), "-i", str(src), "-vf", vf,
                        "-frames:v", "1", "-q:v", "4", str(out / f"{src.stem}_{n:02d}.jpg")], check=True)
        t += per * a.step
        n += 1
    print(f"{src.name}: {n} sheets, step {a.step}s, {a.start:.0f}-{end:.0f}s")


if __name__ == "__main__":
    main()
