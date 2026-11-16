#!/usr/bin/env python3
"""Conform a master to delivery colour: limited-range ('tv') BT.709, yuv420p, fully tagged — and prove the
picture did not change.

Remotion's default H.264 output from JPEG frames is full-range ('pc') BT.601 with untagged primaries/transfer
(yuvj420p), which some players/platforms show with shifted contrast. render.py now renders with
--color-space=bt709; this tool fixes masters made before that, or footage from elsewhere.

    python3 conform_color.py IN.mp4 OUT.mp4 [--crf 17]

Verification: decodes the same frames from input and output to RGB at full resolution and reports the mean absolute
difference. Measured against a PNG captured from the browser (ground truth), the original, this conform and Remotion's
native --color-space=bt709 all sit within ~1–1.5 code values.
"""

import argparse
import json
import subprocess
import sys

import numpy as np


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                          "stream=pix_fmt,color_range,color_space,color_transfer,color_primaries,width,height:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True)
    d = json.loads(out.stdout)
    return {**d["streams"][0], "duration": float(d["format"]["duration"])}


def rgb_at(path, t, w, h):
    # full resolution: a downscale in the comparison itself is range-dependent in swscale and fakes a ~2-code shift
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                          "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).astype(np.int16)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--crf", type=int, default=17)
    a = ap.parse_args(argv)
    p = probe(a.src)
    full = p.get("color_range") == "pc" or p.get("pix_fmt", "").startswith("yuvj")
    in_matrix = {"bt709": "709", "bt470bg": "470bg", "smpte170m": "170m"}.get(p.get("color_space"), "470bg")
    # zimg (zscale) — the same conversion Remotion uses for --color-space=bt709
    vf = (f"zscale=rangein={'full' if full else 'limited'}:matrixin={in_matrix}:range=limited:matrix=709:"
          f"primariesin=709:primaries=709:transferin=709:transfer=709,format=yuv420p")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", a.src, "-map", "0", "-vf", vf,
                    "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium",
                    "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-c:a", "copy", "-movflags", "+faststart", a.dst], check=True)
    q = probe(a.dst)
    diffs = []
    for frac in (0.1, 0.35, 0.6, 0.85):
        t = p["duration"] * frac
        x, y = rgb_at(a.src, t, p["width"], p["height"]), rgb_at(a.dst, t, q["width"], q["height"])
        n = min(len(x), len(y))
        diffs.append(float(np.mean(np.abs(x[:n] - y[:n]))))
    rep = {"in": {k: p.get(k) for k in ("pix_fmt", "color_range", "color_space", "color_transfer", "color_primaries")},
           "out": {k: q.get(k) for k in ("pix_fmt", "color_range", "color_space", "color_transfer", "color_primaries")},
           "duration_in": p["duration"], "duration_out": q["duration"],
           "mean_abs_rgb_diff": [round(d, 2) for d in diffs]}
    rep["passed"] = bool(q.get("color_range") == "tv" and q.get("color_space") == "bt709" and max(diffs) < 2.5
                         and abs(p["duration"] - q["duration"]) < 0.05)
    print(json.dumps(rep, indent=2))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
