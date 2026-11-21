"""Build AnimeShort props from content, ElevenLabs word timings, and the art selection.

Usage: python build/anime_props.py content/en.json work/en art.selection.json motion/props/en.json

- Every narration word appears exactly once, inside caption chunks of 1-4 words
  (the reference's caption grammar), timed to the voice.
- Each script line is one scene; scenes longer than ~2.4 s are cut into several
  shots at chunk boundaries, alternating the line's two art variants and framings.
- The last line (the added message) triggers the warm "gold" grade.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path

FPS = 30
ROOT = Path(__file__).resolve().parent.parent
MOTION = ROOT / "motion"
PRE_ROLL = 0.08
SHOT_MAX = 2.4
END_GAP = 0.7
END_CARD = 2.6

FONTS = {
    "en": {"caption": ("Inter Tight", "inter-tight", [("latin", "800", "normal"), ("latin", "600", "normal")])},
    "te": {"caption": ("Noto Sans Telugu", "noto-sans-telugu", [("telugu", "800", "normal"), ("latin", "800", "normal"),
                                                              ("telugu", "600", "normal"), ("latin", "600", "normal")])},
}
COMMON = {
    "label": ("Inter Tight", "inter-tight", [("latin", "600", "normal"), ("latin", "800", "normal")]),
    "labelTe": ("Noto Sans Telugu", "noto-sans-telugu", [("telugu", "600", "normal")]),
}


def stage(role_specs: dict) -> dict:
    out = {}
    target = MOTION / "public" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    for role, (family, pkg, files) in role_specs.items():
        staged = []
        for subset, weight, style in files:
            name = f"{pkg}-{subset}-{weight}-{style}.woff2"
            src = MOTION / "node_modules" / "@fontsource" / pkg / "files" / name
            if not src.exists():
                sys.exit(f"missing font {src}")
            shutil.copy2(src, target / name)
            staged.append({"weight": weight, "style": style, "src": f"fonts/{name}"})
        out[role] = {"family": family, "files": staged}
    return out


def chunk_words(words: list[dict], max_chars: int) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        text = " ".join(x["text"] for x in cur + [w])
        if cur and (len(text) > max_chars or len(cur) >= 4):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?,:]$", w["text"]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def main() -> None:
    content_path, work, sel_path, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    content = json.loads(content_path.read_text(encoding="utf-8"))
    words = json.loads((work / "words.json").read_text(encoding="utf-8"))
    selection = json.loads(sel_path.read_text(encoding="utf-8"))
    lang = content["language"]

    scenes = []
    for li, line in enumerate(content["lines"]):
        lw = [w for w in words if w["line"] == li]
        keys = set(line.get("key", []))
        ws = [{"text": w["display"], "start": w["start"], "end": w["end"], "key": w["display"] in keys} for w in lw]
        chunks = chunk_words(ws, content["subtitleMaxChars"])
        scenes.append({"id": line["scene"], "line": li, "words": ws,
                       "chunks": [{"start": c[0]["start"], "words": c} for c in chunks],
                       "start": round(max(0.0, ws[0]["start"] - PRE_ROLL), 3)})
    scenes[0]["start"] = 0.0
    end_start = round(words[-1]["end"] + END_GAP, 3)
    for a, b in zip(scenes, scenes[1:]):
        a["end"] = b["start"]
    scenes[-1]["end"] = end_start

    # chunk display windows: until the next chunk starts (or the scene ends)
    all_chunks = [c for s in scenes for c in s["chunks"]]
    for a, b in zip(all_chunks, all_chunks[1:]):
        a["end"] = round(min(b["start"], a["words"][-1]["end"] + 0.6), 3)
    all_chunks[-1]["end"] = round(all_chunks[-1]["words"][-1]["end"] + 0.6, 3)

    # shots: cut long scenes at chunk boundaries, alternate art variants and framings
    media = MOTION / "public" / "art"
    for si, s in enumerate(scenes):
        variants = selection[s["id"]]
        for v in variants:
            if not (media / f"{s['id']}_{v}.jpg").exists():
                sys.exit(f"missing art {s['id']}_{v}.jpg; run build/art.py finish")
        cuts, last = [s["start"]], s["start"]
        for c in s["chunks"][1:]:
            if c["start"] - last >= SHOT_MAX and s["end"] - c["start"] >= 0.9:
                cuts.append(round(c["start"] - 0.04, 3))
                last = c["start"]
        shots = []
        for k, start in enumerate(cuts):
            end = cuts[k + 1] if k + 1 < len(cuts) else s["end"]
            shots.append({"start": start, "end": end, "image": f"art/{s['id']}_{variants[k % len(variants)]}.jpg",
                          "framing": (si * 3 + k) % 4})
        s["shots"] = shots

    total = end_start + END_CARD
    frames = math.ceil(total * FPS)
    fonts = stage(FONTS[lang])
    fonts.update(stage(COMMON))
    props = {
        "canvas": {"width": 1080, "height": 1920, "fps": FPS, "durationInFrames": frames},
        "language": lang,
        "fonts": fonts,
        "hook": content["hook"],
        "logo": "brand/axharry-logo-original.jpg",
        "goldFrom": scenes[-1]["start"],
        "endCard": end_start,
        "intense": ["a03_genius", "a11_button", "a12_control", "a15_richest"],
        "scenes": scenes,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    nshots = sum(len(s["shots"]) for s in scenes)
    print(f"{out_path}: {frames} frames ({frames / FPS:.2f}s), {len(scenes)} scenes, {nshots} shots, "
          f"{len(all_chunks)} caption chunks, {len(words)} words")


if __name__ == "__main__":
    main()
