"""Write an SRT that matches the on-screen caption chunks exactly.

Usage: python build/srt.py motion/props/en.json OUT.srt
"""
import json
import sys
from pathlib import Path


def ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


props = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
chunks = [c for s in props["scenes"] for c in s["chunks"]]
lines = []
for i, c in enumerate(chunks, 1):
    lines.append(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{' '.join(w['text'] for w in c['words'])}\n")
Path(sys.argv[2]).write_text("\n".join(lines), encoding="utf-8")
print(f"{sys.argv[2]}: {len(chunks)} cues")
