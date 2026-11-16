#!/usr/bin/env python3
"""One-command project workflow: reference video → analysed, scaffolded, editable project → verified master.

    /opt/cws-venv/bin/python project.py init NAME --reference REF.mp4 [--duration 60] [--from-example regalia-promo]
    /opt/cws-venv/bin/python project.py build NAME [--storyboard storyboard.json] [--width 1920 --height 1080]
                                                    [--chunk-seconds 60]

init:  creates <studio>/projects/NAME/{public/lib → media library, analysis/, luts/, storyboard.json};
       runs analyze_reference.py on the reference and seeds the storyboard from its measurements
       (BPM → meta.bpm, mean shot length → scene bars, blur-transition rate → default transition,
       luma → background variants, palette recorded in meta.referencePalette). Writes the LUT set.
       The storyboard is the editable project: change words, scenes, assets, timing, then `build`.
build: storyboard → timeline (frame-exact, beat-synced cue sheet) → render.py (chunked video, mastered audio,
       verification) → tests/sync_check.py. Exit code 0 only if every check passes.

Asset sourcing/cataloguing (collect_mixkit.py, synth_assets.py, blender_assets.py, grade.py) stays explicit:
licences have to be checked per item before an asset may enter a project.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
STUDIO = Path("/home/user/creative-studio")
PY = sys.executable


def sh(cmd, **kw):
    print("$", " ".join(map(str, cmd))[:300], flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def init(name: str, reference: Path | None, duration: float, example: str, library: Path, studio: Path) -> Path:
    proj = studio / "projects" / name
    (proj / "public").mkdir(parents=True, exist_ok=True)
    link = proj / "public" / "lib"
    if not link.exists():
        link.symlink_to(library.resolve())
    sb = json.loads((SKILL / "examples" / example / "storyboard.json").read_text())
    sb["meta"]["title"] = name
    sb["meta"]["targetDuration"] = duration
    if reference:
        sh([PY, HERE / "analyze_reference.py", reference, proj / "analysis"])
        style = json.loads((proj / "analysis" / "style.json").read_text())
        d = style["storyboard_defaults"]
        sb["meta"]["bpm"] = float(d["meta"]["bpm"])
        sb["meta"]["referencePalette"] = d["palette"]
        sb["meta"]["referenceAnalysis"] = str(proj / "analysis" / "style.json")
        sb.setdefault("defaults", {})["transition"] = d["transition"]
        for s in sb["scenes"]:
            if s["type"] not in ("EndCard",):
                s["bars"] = max(1, min(4, int(d["scene_bars"])))
        if d["background_variant"] == "dark":
            for s in sb["scenes"]:
                if s.get("background", {}).get("variant") == "light":
                    s["background"]["variant"] = "dusk"
    # keep only as many scenes as fit the duration (end card keeps the remainder)
    bar = 240 / float(sb["meta"]["bpm"])
    body, used = [], 0.0
    for s in sb["scenes"][:-1]:
        need = s.get("bars", 2) * bar
        if used + need > duration - 2 * bar:
            break
        body.append(s)
        used += need
    sb["scenes"] = body + sb["scenes"][-1:]
    (proj / "storyboard.json").write_text(json.dumps(sb, indent=2))
    sh([PY, HERE / "grade.py", "luts", proj / "luts"])
    print(json.dumps({"project": str(proj), "scenes": len(sb["scenes"]), "bpm": sb["meta"]["bpm"],
                      "target_seconds": duration, "storyboard": str(proj / "storyboard.json")}, indent=2))
    return proj


def build(name: str, storyboard: str, width: int | None, height: int | None, chunk: float, studio: Path) -> int:
    proj = studio / "projects" / name
    stem = Path(storyboard).stem.replace("storyboard", "timeline") or "timeline"
    tl = proj / f"{stem}.json"
    cmd = [PY, HERE / "timeline.py", "compile", proj / storyboard, "-o", tl]
    if width and height:
        cmd += ["--width", str(width), "--height", str(height)]
    sh(cmd)
    rc = subprocess.run([PY, HERE / "render.py", proj, "--timeline", tl.name, "--chunk-seconds", str(chunk)]).returncode
    master = proj / "renders" / f"{tl.stem}.mp4"
    if rc != 0 or not master.exists():
        print(f"[build] render failed (exit {rc})")
        return rc or 1
    out = subprocess.run([PY, SKILL / "tests" / "sync_check.py", master, tl], capture_output=True, text=True)
    (proj / "review" / tl.stem).mkdir(parents=True, exist_ok=True)
    (proj / "review" / tl.stem / "sync-check.json").write_text(out.stdout)
    sync = json.loads(out.stdout) if out.stdout.strip() else {"passed": False}
    verify = json.loads((proj / "renders" / f"{tl.stem}.render.json").read_text())["verify"]
    summary = {"master": str(master), "frames": verify["frames"], "expected_frames": verify["expected_frames"],
               "duration": verify["duration"], "size": f"{verify['width']}x{verify['height']}",
               "lufs": verify["integrated_lufs"], "true_peak": verify["true_peak_dbfs"], "verify_passed": verify["passed"],
               "sync_audio_median_ms": sync.get("audio_median_abs_offset_ms"),
               "sync_picture_median_frames": sync.get("picture_median_abs_offset_frames"), "sync_passed": sync.get("passed")}
    print(json.dumps(summary, indent=2))
    return 0 if verify["passed"] and sync.get("passed") else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--studio", type=Path, default=STUDIO)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("name"); i.add_argument("--reference", type=Path)
    i.add_argument("--duration", type=float, default=60); i.add_argument("--from-example", default="regalia-promo")
    i.add_argument("--library", type=Path)
    b = sub.add_parser("build"); b.add_argument("name"); b.add_argument("--storyboard", default="storyboard.json")
    b.add_argument("--width", type=int); b.add_argument("--height", type=int); b.add_argument("--chunk-seconds", type=float, default=60)
    a = ap.parse_args(argv)
    if a.cmd == "init":
        init(a.name, a.reference, a.duration, a.from_example, a.library or a.studio / "media-library", a.studio)
        return 0
    return build(a.name, a.storyboard, a.width, a.height, a.chunk_seconds, a.studio)


if __name__ == "__main__":
    sys.exit(main())
