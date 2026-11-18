"""Build Remotion props for one language from its content file and narration timeline.

Usage: python build/props.py content/en.json work/en/timeline.json motion/props/en.json

Also stages the woff2 fonts the composition needs into motion/public/fonts.
Scene plates are expected at motion/public/media/<scene>.jpg (see build/plates.py).
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

FPS = 30
ROOT = Path(__file__).resolve().parent.parent
MOTION = ROOT / "motion"
FONTSOURCE = MOTION / "node_modules" / "@fontsource"

PALETTE = {
    "ink": "#F8F3FF",
    "lavender": "#B9A3E3",
    "lilac": "#DCCBF7",
    "plum": "#5B3A8C",
    "deep": "#1C1130",
    "glow": "#EFE6FF",
}

SERIES = {"en": "Understanding Temptation", "te": "శోధనను అర్థం చేసుకోవడం"}

FONTS = {
    "en": {
        "family": "Cormorant Garamond",
        "package": "cormorant-garamond",
        "files": [("latin", "500", "normal"), ("latin", "600", "normal"), ("latin", "500", "italic"), ("latin", "600", "italic")],
        "headlineSize": 96, "subtitleSize": 56, "verseSize": 64, "finalSize": 112,
        "lineHeight": 1.18, "letterSpacing": 0.5,
    },
    "te": {
        "family": "Noto Serif Telugu",
        "package": "noto-serif-telugu",
        "files": [("telugu", "500", "normal"), ("telugu", "600", "normal"), ("latin", "500", "normal"), ("latin", "600", "normal")],
        "headlineSize": 72, "subtitleSize": 48, "verseSize": 50, "finalSize": 78,
        "lineHeight": 1.55, "letterSpacing": 0,
    },
}


def stage_font(key: str) -> dict:
    spec = FONTS[key]
    files = []
    target = MOTION / "public" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    for subset, weight, style in spec["files"]:
        name = f"{spec['package']}-{subset}-{weight}-{style}.woff2"
        source = FONTSOURCE / spec["package"] / "files" / name
        if not source.exists():
            sys.exit(f"Missing font file {source}; run npm install in motion/")
        shutil.copy2(source, target / name)
        files.append({"weight": weight, "style": style, "src": f"fonts/{name}"})
    return {
        "family": spec["family"], "files": files,
        **{k: spec[k] for k in ("headlineSize", "subtitleSize", "verseSize", "finalSize", "lineHeight", "letterSpacing")},
    }


def main() -> None:
    content_path, timeline_path, out_path = map(Path, sys.argv[1:4])
    content = json.loads(content_path.read_text(encoding="utf-8"))
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    lang = content["language"]
    frames = math.ceil(timeline["duration"] * FPS)

    scenes = []
    for scene in timeline["scenes"]:
        image = MOTION / "public" / "media" / f"{scene['id']}.jpg"
        if not image.exists():
            sys.exit(f"Missing scene plate {image}; run build/plates.py")
        scenes.append({**{k: scene[k] for k in ("id", "start", "end", "headline")}, "image": f"media/{scene['id']}.jpg"})

    verse_scene = next(s for s in timeline["scenes"] if s["id"] == "s6_bible")
    props = {
        "canvas": {"width": 1080, "height": 1920, "fps": FPS, "durationInFrames": frames},
        "language": lang,
        "font": stage_font(lang),
        "accentFont": stage_font("en") if lang == "en" else stage_font("te"),
        "series": SERIES[lang],
        "scenes": scenes,
        "cues": timeline["cues"],
        "steps": timeline["steps"],
        "verse": {**content["verse"], "start": round(verse_scene["start"] + 0.3, 3)},
        "final": {"lines": content["final"]["lines"], "reference": content["final"]["reference"], "start": timeline["finalStart"]},
        "palette": PALETTE,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out_path}: {frames} frames, {len(scenes)} scenes, {len(props['cues'])} cues")


if __name__ == "__main__":
    main()
