#!/usr/bin/env python3
"""Colour grading with hand-written .cube LUTs (the fable-video-edit method), applied once via ffmpeg.

    python3 grade.py luts  /path/luts                       # write candidate looks
    python3 grade.py grid  clip.mp4 /path/luts out.png --at 3.0   # labelled comparison grid
    python3 grade.py apply /path/luts/lavender_noir.cube clips... --out graded/ --library LIB \
        --max-seconds 16 --size 1920x1080 --fps 30           # mezzanine + grade, catalogued

The grade is plain text: edit the numbers in LOOKS, re-run `luts` and `grid` until it's right.
Derivatives inherit the source asset's licence entry in the catalogue.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import Catalog  # noqa: E402


def luma(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def s_curve(x, amount):
    return np.clip(x + amount * (x - 0.5) * (1 - np.abs(2 * x - 1)) * 2, 0, 1)


def look_neutral(rgb):
    return rgb


def look_lavender_noir(rgb):
    y = luma(rgb)[..., None]
    rgb = y + (rgb - y) * 0.78                      # restrain saturation
    shadows = np.clip(1 - y * 2.2, 0, 1)            # tint lows violet
    rgb = rgb + shadows * np.array([0.045, 0.0, 0.085])
    highs = np.clip((y - 0.6) * 2.5, 0, 1)          # cool, slightly lilac highlights
    rgb = rgb + highs * np.array([0.02, -0.01, 0.04])
    rgb = s_curve(np.clip(rgb, 0, 1), 0.22)
    return rgb * 0.97 + 0.012                       # gentle black lift


def look_lilac_fade(rgb):
    y = luma(rgb)[..., None]
    rgb = y + (rgb - y) * 0.6
    rgb = rgb * 0.86 + np.array([0.09, 0.06, 0.12])
    return s_curve(np.clip(rgb, 0, 1), -0.08)


def look_violet_punch(rgb):
    y = luma(rgb)[..., None]
    rgb = y + (rgb - y) * 1.15
    rgb = rgb + np.clip(0.5 - y, 0, 1) * np.array([0.05, -0.02, 0.10])
    return s_curve(np.clip(rgb, 0, 1), 0.35)


LOOKS = {"neutral": look_neutral, "lavender_noir": look_lavender_noir, "lilac_fade": look_lilac_fade,
         "violet_punch": look_violet_punch}


def write_luts(folder: Path, n: int = 33) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    g = np.linspace(0, 1, n)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")  # red fastest
    grid = np.stack([r, gg, b], -1).reshape(-1, 3)
    out = []
    for name, fn in LOOKS.items():
        vals = np.clip(fn(grid.copy()), 0, 1)
        p = folder / f"{name}.cube"
        with p.open("w") as fh:
            fh.write(f'TITLE "{name}"\nLUT_3D_SIZE {n}\n')
            fh.writelines(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n" for v in vals)
        out.append(p)
    return out


def grid(clip: Path, luts: Path, out: Path, at: float):
    cubes = sorted(luts.glob("*.cube"))
    inputs, filters = [], []
    for i, c in enumerate(cubes):
        inputs += ["-ss", str(at), "-i", str(clip)]
        filters.append(f"[{i}:v]scale=640:-2,lut3d='{c}',drawtext=text='{c.stem}':x=16:y=16:fontsize=28:"
                       f"fontcolor=white:box=1:boxcolor=black@0.5[v{i}]")
    cols = 2
    layout = "|".join(f"{(i % cols) and 'w0' or '0'}_{(i // cols) and 'h0' or '0'}" for i in range(len(cubes)))
    fc = ";".join(filters) + ";" + "".join(f"[v{i}]" for i in range(len(cubes))) + f"xstack=inputs={len(cubes)}:layout={layout}[o]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", fc,
                    "-map", "[o]", "-frames:v", "1", str(out)], check=True)
    return out


def apply(lut: Path, clips: list[Path], out_dir: Path, library: Path | None, max_s: float, size: str, fps: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = size.split("x")
    cat = Catalog(library) if library else None
    results = []
    for c in clips:
        dst = out_dir / c.name
        # keep the source aspect (portrait clips stay portrait); panels crop with object-fit at render time
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,fps={fps},"
              f"lut3d='{lut}',format=yuv420p")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(c), "-t", str(max_s), "-vf", vf,
               "-an", "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-g", str(fps), "-movflags", "+faststart", str(dst)]
        subprocess.run(cmd, check=True)
        if cat:
            src_rel = str(c.resolve().relative_to(cat.root))
            src = cat.by_path(src_rel) or {}
            cat.add(dst, "video-clips", src.get("source_url", f"derived://{src_rel}"), src.get("license", "UNVERIFIED"),
                    (src.get("usage_restrictions", "") + " | Graded derivative").strip(" |"),
                    title=f"{src.get('title', c.stem)} (graded {lut.stem})", tags=["graded", lut.stem],
                    source_page=src.get("source_page", ""),
                    extra={"derived_from": src_rel, "lut": lut.name, "ffmpeg": " ".join(cmd)})
        results.append(str(dst))
    if cat:
        cat.save()
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("luts"); s.add_argument("folder", type=Path)
    s = sub.add_parser("grid"); s.add_argument("clip", type=Path); s.add_argument("luts", type=Path); s.add_argument("out", type=Path)
    s.add_argument("--at", type=float, default=2.0)
    s = sub.add_parser("apply"); s.add_argument("lut", type=Path); s.add_argument("clips", type=Path, nargs="+")
    s.add_argument("--out", type=Path, required=True); s.add_argument("--library", type=Path)
    s.add_argument("--max-seconds", type=float, default=16); s.add_argument("--size", default="1920x1080"); s.add_argument("--fps", type=int, default=30)
    a = ap.parse_args(argv)
    if a.cmd == "luts":
        print("\n".join(map(str, write_luts(a.folder))))
    elif a.cmd == "grid":
        print(grid(a.clip, a.luts, a.out, a.at))
    else:
        print(json.dumps(apply(a.lut, a.clips, a.out, a.library, a.max_seconds, a.size, a.fps), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
