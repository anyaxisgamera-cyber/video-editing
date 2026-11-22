"""Find the source shot (between scene cuts) around each candidate time.

Usage: python -I build/shot_bounds.py FOOTAGE_ROOT CANDIDATES.json
CANDIDATES: {"label": ["src", seconds], ...}; prints the enclosing shot [start, end] per label.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def cuts(path: Path, t0: float, dur: float, thr: float) -> list[float]:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{t0:.2f}", "-t", f"{dur:.2f}", "-i", str(path), "-an",
                          "-vf", f"scale=320:-2,select='gt(scene,{thr})',showinfo", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return [t0 + float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]

def main() -> None:
    root = Path(sys.argv[1])
    manifest = {m["id"]: m for m in json.loads((ROOT / "footage" / "manifest.json").read_text())["sources"]}
    cands = json.loads(Path(sys.argv[2]).read_text())
    out = {}
    for label, (src, t) in cands.items():
        w0 = max(0.0, t - 8)
        cs = cuts(root / manifest[src]["file"], w0, 18, 0.32)
        before = max([c for c in cs if c <= t] or [w0])
        after = min([c for c in cs if c > t] or [w0 + 18])
        out[label] = [src, round(before, 2), round(after, 2)]
        print(f"{label:22s} {src:9s} t={t:7.1f}  shot {before:7.2f}-{after:7.2f}  ({after - before:4.1f}s)")
    Path(sys.argv[2]).with_suffix(".bounds.json").write_text(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
