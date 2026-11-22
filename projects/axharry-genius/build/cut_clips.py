"""Cut the footage clips that a props file uses into motion/public/clips (video only, 30 fps, 1080 px tall).

Usage: python -I build/cut_clips.py FOOTAGE_ROOT motion/props/en-footage.json [more props ...]

FOOTAGE_ROOT holds the downloaded sources at the relative paths listed in footage/manifest.json.
Each (source, in-point) clip is cut once, long enough for its longest use plus 0.5 s, and only
sources whose manifest licence is marked "ok" may be used.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "motion" / "public" / "clips"


def main() -> None:
    root = Path(sys.argv[1])
    manifest = {m["id"]: m for m in json.loads((ROOT / "footage" / "manifest.json").read_text())["sources"]}
    need: dict[str, tuple[str, float, float]] = {}
    for props_path in sys.argv[2:]:
        props = json.loads(Path(props_path).read_text(encoding="utf-8"))
        for s in props["scenes"]:
            for sh in s["shots"]:
                if "video" not in sh:
                    continue
                c = sh["clip"]
                m = manifest.get(c["src"])
                if not m or m["use"] != "ok":
                    sys.exit(f"source {c['src']} is not cleared for use")
                # source seconds needed at this shot's playback rate, never past the source shot's own cut
                dur = min((sh["end"] - sh["start"]) * sh.get("rate", 1.0) + 0.5, c.get("max", 99) + 0.05)
                prev = need.get(sh["video"])
                need[sh["video"]] = (c["src"], c["in"], max(dur, prev[2] if prev else 0))
    OUT.mkdir(parents=True, exist_ok=True)
    for rel, (src, t_in, dur) in sorted(need.items()):
        dst = ROOT / "motion" / "public" / rel
        if dst.exists():
            got = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        str(dst)], capture_output=True, text=True).stdout or 0)
            if got >= dur - 0.05:
                continue
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}",
                        "-i", str(root / manifest[src]["file"]), "-an",
                        "-vf", (f"crop={manifest[src]['crop']}," if manifest[src].get("crop") else "") +
                        "scale=-2:1080:flags=lanczos,fps=30,setsar=1,format=yuv420p",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "15", str(dst)], check=True)
        print(f"cut {rel} ({dur:.2f}s)")
    print(f"{len(need)} clips ready")


if __name__ == "__main__":
    main()
