#!/usr/bin/env python3
"""Storyboard → frame-exact timeline compiler (+ automatic, beat-synced SFX cue sheet).

Storyboard scenes are authored in musical BARS (or seconds). Every transition is centred on a
slot boundary, and slot boundaries sit on downbeats of the music grid, so cuts land on the beat.
The total length equals ``meta.targetDuration`` exactly (the last scene absorbs any remainder).

    python3 timeline.py compile storyboard.json -o timeline.json
    python3 timeline.py expand  storyboard.json --duration 600 -o storyboard-10min.json   # full-length
    python3 timeline.py describe timeline.json                                            # scene table

Scene slot math (T = transition frames centred on boundary B):
    scene_i.from = B_i - T_{i-1}/2;  scene_i.duration = slot_i + T_{i-1}/2 + T_i/2
which is exactly what Remotion's <TransitionSeries> computes, so audio cues (absolute seconds)
and picture stay locked.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

# SFX sync points (seconds into the file where the "hit" is) — must match audio_synth.py output.
SFX = {
    "whoosh": ("lib/sound-effects/synth-whoosh.wav", 0.72, 0.55),
    "impact": ("lib/sound-effects/synth-impact.wav", 0.0, 0.75),
    "shimmer": ("lib/sound-effects/synth-shimmer.wav", 0.0, 0.32),
    "swell": ("lib/sound-effects/synth-swell.wav", 2.6, 0.30),
    "riser": ("lib/sound-effects/synth-riser.wav", 2.0, 0.35),
    "tick": ("lib/sound-effects/synth-tick.wav", 0.0, 0.25),
}
TEXT_SCENES = {"TitleReveal", "Statement", "ChessHero", "Silhouette"}
LOGO_SCENES = {"LogoWall", "EndCard"}


def compile_storyboard(sb: dict) -> dict:
    meta = dict(sb["meta"])
    fps = int(meta.get("fps", 30))
    bpm = float(meta.get("bpm", 96))
    beat = 60.0 / bpm
    bar = 4 * beat
    target = meta.get("targetDuration")
    defaults = sb.get("defaults", {})
    dtr = defaults.get("transition", {"type": "blurDissolve", "beats": 1})

    scenes = sb["scenes"]
    slots = []
    for s in scenes:
        if "bars" in s:
            slots.append(s["bars"] * bar)
        elif "seconds" in s:
            slots.append(float(s["seconds"]))
        else:
            slots.append(2 * bar)
    if target:
        rest = float(target) - sum(slots[:-1])
        if rest < 1.0:
            raise SystemExit(f"storyboard is longer than targetDuration ({sum(slots):.2f}s > {target}s)")
        slots[-1] = rest
    total_s = sum(slots)
    total_f = round(total_s * fps)

    # boundaries in frames (rounded once, from absolute time — no drift on long videos)
    bounds = [0]
    acc = 0.0
    for sl in slots:
        acc += sl
        bounds.append(round(acc * fps))
    bounds[-1] = total_f

    trans = []
    for i, s in enumerate(scenes[:-1]):
        tr = {**dtr, **s.get("transition", {})}
        frames = round(tr.get("beats", 1) * beat * fps) if "beats" in tr else round(tr.get("seconds", 0.8) * fps)
        frames -= frames % 2  # even → centred exactly on the boundary
        if tr["type"] == "cut":
            frames = 0
        # a transition can never be longer than the shorter neighbouring slot
        frames = min(frames, (bounds[i + 1] - bounds[i]) - 2, (bounds[i + 2] - bounds[i + 1]) - 2)
        frames -= frames % 2
        trans.append({"type": tr["type"], "durationInFrames": max(0, frames)})

    out_scenes = []
    cues = []
    for i, s in enumerate(scenes):
        t_in = trans[i - 1]["durationInFrames"] if i > 0 else 0
        t_out = trans[i]["durationInFrames"] if i < len(trans) else 0
        start = bounds[i] - t_in // 2
        dur = (bounds[i + 1] - bounds[i]) + t_in // 2 + t_out // 2
        sc = {
            "id": s.get("id", f"s{i + 1:03d}"),
            "type": s["type"],
            "from": start,
            "durationInFrames": dur,
            "slot": {"start": bounds[i], "end": bounds[i + 1]},
            "background": s.get("background", {"variant": "light"}),
            "floating": s.get("floating", []),
            "props": s.get("props", {}),
        }
        if i < len(trans):
            sc["transition"] = trans[i]
        out_scenes.append(sc)

        # ---------- automatic sound design, all in absolute seconds
        if sb.get("audio", {}).get("autoSfx", True):
            B = bounds[i] / fps
            if i > 0 and trans[i - 1]["durationInFrames"] > 0:
                kind = trans[i - 1]["type"]
                cues.append(cue("whoosh", B, f"transition {kind} into {sc['id']}"))
                if kind in ("flash", "zoomBlur"):
                    cues.append(cue("impact", B, f"{kind} accent"))
            elif i > 0:
                cues.append(cue("impact", B, f"hard cut into {sc['id']}"))
            text_start = (start + round(12 * fps / 30)) / fps
            if s["type"] in TEXT_SCENES:
                cues.append(cue("swell", max(0.0, text_start + 0.25), f"blur-in title {sc['id']}"))
            if s["type"] in LOGO_SCENES:
                cues.append(cue("shimmer", (start + round(26 * fps / 30)) / fps, f"logo reveal {sc['id']}"))
            if s["type"] == "Stats":
                for k, _ in enumerate(s.get("props", {}).get("items", [])):
                    cues.append(cue("tick", (start + round((16 + k * 8) * fps / 30)) / fps, f"stat {k + 1}"))
        for extra in s.get("sfx", []):
            cues.append({"src": extra["src"], "at": round(bounds[i] / fps + extra.get("at", 0), 4),
                         "volume": extra.get("volume", 0.6), "reason": extra.get("reason", "manual")})
    if sb.get("audio", {}).get("autoSfx", True) and len(out_scenes) > 1:
        cues.append(cue("riser", out_scenes[-1]["slot"]["start"] / fps, "into end card"))
    cues = [c for c in cues if 0 <= c["at"] < total_s]
    cues.sort(key=lambda c: c["at"])

    meta.update({"fps": fps, "bpm": bpm, "durationInFrames": total_f, "durationSeconds": total_f / fps,
                 "beatSeconds": beat, "barSeconds": bar})
    audio = dict(sb.get("audio", {}))
    audio["cues"] = cues
    return {"schema": "creative-workstation/timeline@1", "meta": meta, "scenes": out_scenes, "audio": audio}


def cue(kind: str, hit_time: float, reason: str) -> dict:
    src, sync, vol = SFX[kind]
    return {"src": src, "at": round(hit_time - sync, 4), "hit": round(hit_time, 4), "volume": vol, "kind": kind, "reason": reason}


def expand(sb: dict, duration: float) -> dict:
    """Fill a full-length runtime: keep the opening + end card, cycle the middle chapters with
    rotated content (different footage, pieces, backgrounds, transitions) until the duration is met."""
    meta = sb["meta"]
    bar = 4 * 60.0 / float(meta.get("bpm", 96))
    scenes = sb["scenes"]
    head, body, tail = scenes[:1], scenes[1:-1], scenes[-1:]
    out = [copy.deepcopy(s) for s in head]
    used = sum(s.get("bars", 2) * bar for s in head) + sum(s.get("bars", 2) * bar for s in tail)
    pool = sb.get("variations", {})
    chapter = 0
    trans_cycle = ["blurDissolve", "zoomBlur", "softWipe", "blurDissolve", "flash", "slideLeft", "iris"]
    k = 0
    while True:
        chapter += 1
        for s in body:
            need = s.get("bars", 2) * bar
            if used + need > duration - 2 * bar:
                break
            c = copy.deepcopy(s)
            c["id"] = f"c{chapter:03d}-{s.get('id', s['type'])}"
            c.setdefault("transition", {})["type"] = trans_cycle[k % len(trans_cycle)]
            # rotate any list-valued variation pools (titles, footage, pieces, backgrounds)
            for key, values in pool.get(s.get("id", ""), {}).items():
                target = c
                parts = key.split(".")
                for p_ in parts[:-1]:
                    target = target.setdefault(p_, {})
                target[parts[-1]] = copy.deepcopy(values[(chapter - 1) % len(values)])
            if s["type"] in ("TitleReveal",) and "props" in c and pool.get("_chapterTitles"):
                titles = pool["_chapterTitles"]
                c["props"]["kicker"] = f"Chapter {chapter:02d}"
                c["props"]["title"] = titles[(chapter - 1) % len(titles)]
            out.append(c)
            used += need
            k += 1
        else:
            continue
        break
    out += [copy.deepcopy(s) for s in tail]
    res = copy.deepcopy(sb)
    res["scenes"] = out
    res["meta"]["targetDuration"] = duration
    res.pop("variations", None)
    return res


def describe(tl: dict) -> str:
    fps = tl["meta"]["fps"]
    rows = [f"{'id':<26} {'type':<13} {'slot start':>10} {'slot end':>9} {'len s':>7}  transition"]
    for s in tl["scenes"]:
        a, b = s["slot"]["start"] / fps, s["slot"]["end"] / fps
        tr = s.get("transition", {})
        rows.append(f"{s['id']:<26} {s['type']:<13} {a:>10.2f} {b:>9.2f} {b - a:>7.2f}  {tr.get('type', '-')}"
                    f"{'(' + str(tr.get('durationInFrames')) + 'f)' if tr else ''}")
    m = tl["meta"]
    rows.append(f"TOTAL {m['durationInFrames']} frames = {m['durationInFrames'] / fps:.3f}s @ {fps} fps, "
                f"{m['width']}x{m['height']}, {len(tl['scenes'])} scenes, {len(tl['audio']['cues'])} sfx cues")
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile"); c.add_argument("storyboard", type=Path); c.add_argument("-o", "--out", type=Path, required=True)
    c.add_argument("--width", type=int); c.add_argument("--height", type=int); c.add_argument("--fps", type=int)
    e = sub.add_parser("expand"); e.add_argument("storyboard", type=Path); e.add_argument("--duration", type=float, required=True)
    e.add_argument("-o", "--out", type=Path, required=True)
    d = sub.add_parser("describe"); d.add_argument("timeline", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "compile":
        sb = json.loads(a.storyboard.read_text())
        for k in ("width", "height", "fps"):
            if getattr(a, k):
                sb["meta"][k] = getattr(a, k)
        tl = compile_storyboard(sb)
        a.out.write_text(json.dumps(tl, indent=2))
        print(describe(tl))
    elif a.cmd == "expand":
        res = expand(json.loads(a.storyboard.read_text()), a.duration)
        a.out.write_text(json.dumps(res, indent=2))
        print(f"{len(res['scenes'])} scenes for {a.duration}s -> {a.out}")
    else:
        print(describe(json.loads(a.timeline.read_text())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
