"""One frame from the middle of every shot of a delivered video, tiled (visual QA).

Usage: python build/shot_sheet.py VIDEO PROPS OUT.jpg [--cols 8] [--width 240]
"""
import argparse, json, subprocess, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("props"); ap.add_argument("out")
ap.add_argument("--cols", type=int, default=8); ap.add_argument("--width", type=int, default=240)
a = ap.parse_args()
p = json.loads(Path(a.props).read_text(encoding="utf-8"))
times = [(sh["start"] + sh["end"]) / 2 for s in p["scenes"] for sh in s["shots"]] + [p["endCard"] + 1.6]
with tempfile.TemporaryDirectory() as d:
    for i, t in enumerate(times):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", a.video, "-frames:v", "1",
                        "-vf", f"scale={a.width}:-2,drawtext=text='{t:.1f}s':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black",
                        f"{d}/{i:03d}.png"], check=True)
    rows = -(-len(times) // a.cols)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{d}/%03d.png", "-vf", f"tile={a.cols}x{rows}:padding=2",
                    "-frames:v", "1", "-q:v", "3", a.out], check=True)
print(f"{a.out}: {len(times)} frames")
