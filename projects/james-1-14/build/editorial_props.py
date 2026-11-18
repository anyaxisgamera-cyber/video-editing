"""Build EditorialShort props (v3 Telugu cut) from content + ElevenLabs word timings.

Usage: python build/editorial_props.py content/te-editorial.json work/te-editorial motion/props/te-editorial.json

Same word-assignment contract as kinetic_props.py: every narration word is shown
exactly once, in order, at its spoken time. Adds the closing card and the AX logo
end card, and stages the fonts the editorial look needs.
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
PRE_ROLL = 0.12
FINAL_GAP = 0.5
FINAL_HOLD = 3.0
LOGO_HOLD = 3.4

FONT_FILES = {
    "sans": ("Noto Sans Telugu", "noto-sans-telugu", [("telugu", "600", "normal"), ("telugu", "800", "normal"),
                                                     ("latin", "600", "normal"), ("latin", "800", "normal")]),
    "serif": ("Noto Serif Telugu", "noto-serif-telugu", [("telugu", "700", "normal"), ("latin", "700", "normal"),
                                                        ("telugu", "500", "normal"), ("latin", "500", "normal")]),
    "label": ("Inter Tight", "inter-tight", [("latin", "600", "normal"), ("latin", "800", "normal")]),
    "elegant": ("Cormorant Garamond", "cormorant-garamond", [("latin", "600", "italic"), ("latin", "600", "normal")]),
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def stage_fonts() -> dict:
    target = MOTION / "public" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    out = {}
    for role, (family, package, files) in FONT_FILES.items():
        staged = []
        for subset, weight, style in files:
            name = f"{package}-{subset}-{weight}-{style}.woff2"
            src = MOTION / "node_modules" / "@fontsource" / package / "files" / name
            if not src.exists():
                sys.exit(f"Missing font {src}; run npm install in motion/")
            shutil.copy2(src, target / name)
            staged.append({"weight": weight, "style": style, "src": f"fonts/{name}"})
        out[role] = {"family": family, "files": staged}
    return out


def main() -> None:
    content_path, work_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    content = json.loads(content_path.read_text(encoding="utf-8"))
    words = json.loads((work_dir / "words.json").read_text(encoding="utf-8"))
    plan = content["editorial"]

    scenes, wi = [], 0
    for spec in plan["scenes"]:
        target = norm(spec["text"])
        taken = []
        while wi < len(words) and len(norm(" ".join(w["display"] for w in taken))) < len(target):
            taken.append(words[wi])
            wi += 1
        got = norm(" ".join(w["display"] for w in taken))
        if got != target:
            sys.exit(f"Scene text mismatch:\n  plan: {target}\n  words: {got}")
        keys = spec.get("key", [])
        scene = {**{k: v for k, v in spec.items() if k not in ("text", "key", "items")},
                 "words": [{"text": w["display"], "start": w["start"], "end": w["end"], "key": False} for w in taken],
                 "start": round(max(0.0, taken[0]["start"] - PRE_ROLL), 3),
                 "line": " ".join(w["display"] for w in taken)}
        for phrase in keys:
            parts = phrase.split()
            for i in range(len(scene["words"]) - len(parts) + 1):
                if [w["text"] for w in scene["words"][i:i + len(parts)]] == parts:
                    for w in scene["words"][i:i + len(parts)]:
                        w["key"] = True
        if "items" in spec:
            items, k = [], 0
            for item in spec["items"]:
                items.append({"text": item, "start": scene["words"][k]["start"]})
                k += len(item.split())
            scene["items"] = items
        scenes.append(scene)
    if wi != len(words):
        sys.exit(f"{len(words) - wi} narration words are not assigned to any scene")
    scenes[0]["start"] = 0.0

    final_start = round(words[-1]["end"] + FINAL_GAP, 3)
    logo_start = round(final_start + FINAL_HOLD, 3)
    total = logo_start + LOGO_HOLD
    for a, b in zip(scenes, scenes[1:]):
        a["end"] = b["start"]
    scenes[-1]["end"] = final_start
    frames = math.ceil(total * FPS)

    props = {
        "canvas": {"width": 1080, "height": 1920, "fps": FPS, "durationInFrames": frames},
        "fonts": stage_fonts(),
        "sideLabel": plan["sideLabel"],
        "header": plan["header"],
        "cardTitle": plan["cardTitle"],
        "watermark": plan["watermark"],
        "logo": {"src": plan["logo"], "start": logo_start},
        "verse": content["verse"],
        "scenes": scenes,
        "final": {**plan["final"], "start": final_start},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out_path}: {frames} frames ({frames / FPS:.2f}s), {len(scenes)} scenes, {len(words)} words, "
          f"final {final_start}s, logo {logo_start}s")


if __name__ == "__main__":
    main()
