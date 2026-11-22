"""Build AnimeShort props from content, ElevenLabs word timings, and the art selection.

Usage: python build/anime_props.py content/en.json work/en art.selection.json motion/props/en.json
                                   [--footage footage.selection.json] [--landscape]

With --footage, each scene's shots cycle through that scene's footage list, whose entries are
{"src": ID, "in": SECONDS, "fx": 0-1, "fy": 0-1} (a clip of a licensed source, see footage/manifest.json)
or {"art": SEED} (one of the original art variants). build/cut_clips.py then cuts the clips.
--landscape makes a 1920x1080 canvas instead of 1080x1920.

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
SHOT_MAX = 1.8   # faster rhythm, per the reference reels (0.6-2 s shots)
END_GAP = 0.7
END_CARD = 2.6
MIN_RATE = 0.7  # slowest playback used to stretch a short source shot

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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("content")
    ap.add_argument("work")
    ap.add_argument("selection")
    ap.add_argument("out")
    ap.add_argument("--footage")
    ap.add_argument("--landscape", action="store_true")
    opt = ap.parse_args()
    content_path, work, sel_path, out_path = Path(opt.content), Path(opt.work), Path(opt.selection), Path(opt.out)
    footage = json.loads(Path(opt.footage).read_text(encoding="utf-8")) if opt.footage else {}
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
        plan = footage.get(s["id"]) or [{"art": v} for v in variants]
        ptr, prev, used = 0, None, set()
        for k, start in enumerate(cuts):
            end = cuts[k + 1] if k + 1 < len(cuts) else s["end"]
            # take the next planned entry that is long enough for this shot (art always fits)
            need = end - start + 0.1
            # a clip may be slowed to at most MIN_RATE speed to cover the shot; clips are not repeated in a scene
            entry = None
            for j in range(len(plan)):
                idx = (ptr + j) % len(plan)
                e = plan[idx]
                fits = "art" in e or e.get("max", 99) >= need * MIN_RATE
                if fits and e is not prev and ("art" in e or id(e) not in used):
                    entry, ptr = e, idx + 1
                    used.add(id(entry))
                    break
            if entry is None:
                entry = {"art": variants[k % len(variants)]}
            prev = entry
            shot = {"start": start, "end": end, "framing": (si * 3 + k) % 4}
            if "art" in entry:
                shot["image"] = f"art/{s['id']}_{entry['art']}.jpg"
                if not (media / f"{s['id']}_{entry['art']}.jpg").exists():
                    sys.exit(f"missing art {s['id']}_{entry['art']}.jpg")
            else:
                shot["clip"] = {"src": entry["src"], "in": entry["in"]}
                shot["video"] = f"clips/{entry['src']}_{entry['in']:07.2f}.mp4"
                shot["fx"], shot["fy"] = entry.get("fx", 0.5), entry.get("fy", 0.5)
                shot["rate"] = round(min(1.0, entry.get("max", 99) / need), 3)
                shot["clip"]["max"] = entry.get("max", 99)
            shots.append(shot)
        s["shots"] = shots

    total = end_start + END_CARD
    frames = math.ceil(total * FPS)
    fonts = stage(FONTS[lang])
    fonts.update(stage(COMMON))
    props = {
        "canvas": {"width": 1920 if opt.landscape else 1080, "height": 1080 if opt.landscape else 1920, "fps": FPS, "durationInFrames": frames},
        "language": lang,
        "fonts": fonts,
        "hook": content["hook"],
        "logo": "brand/axharry-logo-original.jpg",
        "goldFrom": scenes[-1]["start"],
        "endCard": end_start,
        "intense": ["a03_genius", "a11_button", "a12_control", "a15_richest"],
        "scenes": scenes,
        "credits": footage.get("_credits", []),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    nshots = sum(len(s["shots"]) for s in scenes)
    print(f"{out_path}: {frames} frames ({frames / FPS:.2f}s), {len(scenes)} scenes, {nshots} shots, "
          f"{len(all_chunks)} caption chunks, {len(words)} words")


if __name__ == "__main__":
    main()
