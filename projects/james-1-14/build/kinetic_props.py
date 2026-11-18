"""Build KineticShort props from a content file and ElevenLabs word timings.

Usage: python build/kinetic_props.py content/en.json work/en-kinetic motion/props/en-kinetic.json

Every narration word is assigned, in order, to exactly one scene, so the
on-screen kinetic text is a word-accurate caption track. Scene cuts land just
before each scene's first spoken word, as in the reference edit.
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
PRE_ROLL = 0.12      # cut this long before the first word of a scene
FINAL_GAP = 0.45     # after the last spoken word, before the closing card
FINAL_HOLD = 3.6     # closing card length

FONTS = {
    "en": {"family": "Inter Tight", "package": "inter-tight", "subsets": ["latin"], "scale": 1.0, "finalScale": 1.0},
    "te": {"family": "Noto Sans Telugu", "package": "noto-sans-telugu", "subsets": ["telugu", "latin"], "scale": 0.9, "finalScale": 0.66},
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def stage_font(lang: str) -> dict:
    spec = FONTS[lang]
    target = MOTION / "public" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    files = []
    for subset in spec["subsets"]:
        for weight in ("600", "800"):
            name = f"{spec['package']}-{subset}-{weight}-normal.woff2"
            src = MOTION / "node_modules" / "@fontsource" / spec["package"] / "files" / name
            if not src.exists():
                sys.exit(f"Missing font {src}; run npm install in motion/")
            shutil.copy2(src, target / name)
            files.append({"weight": weight, "style": "normal", "src": f"fonts/{name}"})
    return {"family": spec["family"], "files": files, "scale": spec["scale"], "finalScale": spec["finalScale"]}


def main() -> None:
    content_path, work_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    content = json.loads(content_path.read_text(encoding="utf-8"))
    words = json.loads((work_dir / "words.json").read_text(encoding="utf-8"))
    plan = content["kinetic"]
    lang = content["language"]

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
        keys = set(spec.get("key", []))
        scene = {
            **{k: v for k, v in spec.items() if k not in ("text", "key", "items")},
            "words": [{"text": w["display"], "start": w["start"], "end": w["end"], "key": w["display"] in keys} for w in taken],
            "start": round(max(0.0, taken[0]["start"] - PRE_ROLL), 3),
        }
        # A multi-word key (e.g. "James 1:14") marks every word it spans.
        for phrase in keys:
            parts = phrase.split()
            for i in range(len(scene["words"]) - len(parts) + 1):
                if [w["text"] for w in scene["words"][i:i + len(parts)]] == parts:
                    for w in scene["words"][i:i + len(parts)]:
                        w["key"] = True
        if "items" in spec:
            items, k = [], 0
            for item in spec["items"]:
                n = len(item.split())
                items.append({"text": item, "start": scene["words"][k]["start"]})
                k += n
            scene["items"] = items
        scenes.append(scene)
    if wi != len(words):
        sys.exit(f"{len(words) - wi} narration words are not assigned to any scene")
    scenes[0]["start"] = 0.0

    final_start = round(words[-1]["end"] + FINAL_GAP, 3)
    total = final_start + FINAL_HOLD
    for a, b in zip(scenes, scenes[1:]):
        a["end"] = b["start"]
    scenes[-1]["end"] = final_start
    frames = math.ceil(total * FPS)

    props = {
        "canvas": {"width": 1080, "height": 1920, "fps": FPS, "durationInFrames": frames},
        "language": lang,
        "font": stage_font(lang),
        "badge": plan["badge"],
        "cardTitle": plan["cardTitle"],
        "scenes": scenes,
        "final": {**plan["final"], "start": final_start, "verse": content["verse"]},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    timeline = {"duration": round(frames / FPS, 3), "finalStart": final_start,
                "scenes": [{"start": s["start"], "end": s["end"]} for s in scenes]}
    (work_dir / "kinetic-timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
    print(f"{out_path}: {frames} frames ({frames / FPS:.2f}s), {len(scenes)} scenes, {len(words)} words")


if __name__ == "__main__":
    main()
