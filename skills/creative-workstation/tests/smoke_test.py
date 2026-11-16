#!/usr/bin/env python3
"""Fast, dependency-light smoke test (CI): catalogue round-trip, timeline compiler maths, expand, SFX/music
synthesis (if numpy/scipy/soundfile are present; pass --require-audio to make their absence a failure).
No Blender, Remotion or network needed."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = HERE.parent / "scripts"
sys.path.insert(0, str(S))

import catalog  # noqa: E402
import timeline  # noqa: E402


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"ok  {msg}")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        lib = Path(td) / "lib"
        catalog.cmd_init(lib)
        check(all((lib / c).is_dir() for c in catalog.CATEGORIES), "library folders created")
        svg = lib / "icons" / "x.svg"
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>')
        cat = catalog.Catalog(lib)
        cat.add(svg, "icons", "https://example.com/x.svg", "ISC", "keep notice")
        cat.save()
        check(catalog.Catalog(lib).validate() == [], "catalogue validates with source + licence")
        e = catalog.Catalog(lib).by_path("icons/x.svg")
        check(e["probe"]["width"] == 24 and e["commercial_use"] == "yes", "SVG probed and licence classified")
        cat.add(svg, "icons", "https://example.com/x.svg", "Some Unknown License")
        check(any("UNVERIFIED" in p for p in cat.validate()), "unknown licence is flagged")

    sb = json.loads((HERE.parent / "examples" / "storyboard-minimal.json").read_text())
    tl = timeline.compile_storyboard(sb)
    fps = tl["meta"]["fps"]
    check(tl["meta"]["durationInFrames"] == round(sb["meta"]["targetDuration"] * fps), "duration is exactly the target")
    # TransitionSeries layout reproduces the compiled 'from' values
    pos = 0
    for i, s in enumerate(tl["scenes"]):
        check(s["from"] == pos, f"scene {s['id']} starts at frame {pos}")
        pos += s["durationInFrames"] - (s.get("transition", {}).get("durationInFrames", 0) if i < len(tl["scenes"]) - 1 else 0)
    check(pos == tl["meta"]["durationInFrames"], "scene durations minus overlaps == total")
    bar = 240 / sb["meta"]["bpm"]
    hits = [c["hit"] for c in tl["audio"]["cues"] if c["kind"] == "whoosh"]
    check(all(abs((h / bar) - round(h / bar)) < 1e-3 for h in hits), "every whoosh peak lands on a downbeat")
    long = timeline.compile_storyboard(timeline.expand(sb, 600))
    check(long["meta"]["durationInFrames"] == 600 * fps, "expand() → exactly 10:00")
    try:
        import audio_synth  # noqa: F401
        with tempfile.TemporaryDirectory() as td:
            grid = audio_synth.music(Path(td) / "m.wav", 12.5, bpm=96)
            import soundfile as sf
            info = sf.info(str(Path(td) / "m.wav"))
            check(abs(info.duration - 12.5) < 1e-3 and info.samplerate == 48000, "music synth exact length @48k")
            check(len(audio_synth.make_sfx(Path(td) / "sfx")) == 6, "6 SFX synthesised")
    except ImportError as exc:
        if "--require-audio" in sys.argv:
            raise SystemExit(f"FAIL: audio synthesis checks required but dependencies are missing ({exc})")
        print(f"skip audio synthesis ({exc})")
    print("creative-workstation smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
