#!/usr/bin/env python3
"""End-to-end test of the installed fable-video-edit workflow on synthetic spoken takes.

transcripts (Whisper word timestamps, via the skill's scripts/transcribe.sh) → scene casting against a script →
take selection (disqualify incomplete, fewest fillers, on-script) → final-edit.json (fable schema, with rationale)
→ frame-accurate mezzanine cuts → concat → RE-TRANSCRIBE + verify (zero ums, order, duration) → LUT grade + loudnorm
applied exactly once (fable ffmpeg-recipes §6) → ffprobe verification.

    /opt/cws-venv/bin/python fable_workflow_test.py WORKDIR LUT.cube
WORKDIR must contain takes/*.mp4 and work/transcripts/*.json (run transcribe.sh first).
"""

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = {1: "Every move matters, and every decision counts.", 2: "Strategy is the art of seeing the whole board."}
FILLERS = {"um", "uh", "erm", "uhm"}
TRANSCRIBE = Path.home() / ".claude/skills/fable-video-edit/scripts/transcribe.sh"


def norm(t):
    return re.sub(r"[^a-z ]", "", t.lower()).split()


def words(js):
    return [w for seg in js["segments"] for w in seg.get("words", [])]


def run(cmd):
    subprocess.run([str(c) for c in cmd], check=True, stdout=sys.stderr)  # keep stdout = the JSON report


def main() -> int:
    root, lut = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    tdir = root / "work" / "transcripts"
    takes = {}
    for p in sorted(tdir.glob("*.json")):
        js = json.loads(p.read_text())
        takes[p.stem] = {"text": js["text"].strip(), "words": words(js)}
    edl = {"project": "fable-workflow-test", "source_dir": str(root / "takes"), "target": {"width": 1280, "height": 720, "fps": 30}, "scenes": []}
    for n, line in SCRIPT.items():
        cands = []
        for name, t in takes.items():
            spoken = [w for w in norm(t["text"]) if w not in FILLERS]
            sim = difflib.SequenceMatcher(None, spoken, norm(line)).ratio()
            if sim > 0.45:
                fill = sum(1 for w in norm(t["text"]) if w in FILLERS)
                restarts = max(0, len(spoken) - len(set(spoken)) - (len(norm(line)) - len(set(norm(line)))))
                # coverage, not exact match: Whisper mishears proper nouns/synthetic voices ("seeing" → "seeking")
                sm = difflib.SequenceMatcher(None, spoken, norm(line))
                coverage = sum(b.size for b in sm.get_matching_blocks()) / len(norm(line))
                complete = coverage >= 0.8
                cands.append({"take": name, "similarity": round(sim, 3), "coverage": round(coverage, 2), "fillers": fill, "restarts": restarts, "complete": complete})
        ok = [c for c in cands if c["complete"]]
        best = sorted(ok, key=lambda c: (c["fillers"] + c["restarts"], -c["similarity"]))[0]
        losers = [f"{c['take']}: {f"incomplete (covers {c['coverage']:.0%} of the line)" if not c['complete'] else f'{c['fillers']} fillers, {c['restarts']} repeats'}"
                  for c in cands if c is not best]
        w = takes[best["take"]]["words"]
        first = next(x for x in w if norm(x["word"]) and norm(x["word"])[0] not in FILLERS)
        start = max(0.0, first["start"] - 0.08)
        end = w[-1]["end"] + 0.25
        edl["scenes"].append({
            "scene": n, "title": line, "candidate_takes": [c["take"] for c in cands],
            "selection_rationale": f"{best['take']} picked: complete, {best['fillers']} fillers, similarity {best['similarity']}. "
                                   f"Rejected — " + "; ".join(losers),
            "clips": [{"clip": best["take"], "start": round(start, 3), "end": round(end, 3), "first_words": first["word"].strip()}],
        })
    (root / "final-edit.json").write_text(json.dumps(edl, indent=2))
    cuts = root / "work" / "cuts"
    cuts.mkdir(parents=True, exist_ok=True)
    segs = []
    for sc in edl["scenes"]:
        for c in sc["clips"]:
            out = cuts / f"seg{sc['scene']:02d}.mp4"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", c["start"], "-to", c["end"], "-i", root / "takes" / f"{c['clip']}.mp4",
                 "-vf", "fps=30,scale=1280:720:flags=lanczos", "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "256k", "-ar", "48000", out])
            segs.append(out)
    (cuts / "concat.txt").write_text("".join(f"file '{s}'\n" for s in segs))
    asm_dir = root / "assembly"
    asm_dir.mkdir(exist_ok=True)
    asm = asm_dir / "assembly.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", cuts / "concat.txt", "-c", "copy", asm])
    # verify like code: re-transcribe the assembly with the skill's own script
    run([TRANSCRIBE, asm_dir, root / "verify", "base"])
    vjs = json.loads((root / "verify" / "transcripts" / "assembly.json").read_text())
    vt = norm(vjs["text"])
    ums = sum(1 for w in vt if w in FILLERS)
    order_ok = vt[:3] == norm(SCRIPT[1])[:3] and "strategy" in vt and vt.index("strategy") > vt.index("every")
    expected = sum(c["end"] - c["start"] for sc in edl["scenes"] for c in sc["clips"])
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(asm)],
                               capture_output=True, text=True).stdout)
    # grade exactly once at final encode + loudnorm (fable ffmpeg-recipes §6)
    final = root / "final.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", asm, "-vf", f"lut3d='{lut}'", "-c:v", "libx264", "-crf", "17",
         "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ar", "48000", "-movflags", "+faststart", final])
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(final)],
                                   capture_output=True, text=True).stdout)
    edl["verification"] = {"retranscribed_text": vjs["text"].strip(), "retranscribed_ums": ums, "scene_order_ok": order_ok,
                           "assembly_duration": round(dur, 3), "expected_duration": round(expected, 3),
                           "final": {s["codec_type"]: {k: s.get(k) for k in ("codec_name", "width", "height", "r_frame_rate", "sample_rate")}
                                     for s in pr["streams"]}}
    edl["verification"]["passed"] = bool(ums == 0 and order_ok and abs(dur - expected) < 0.15)
    (root / "final-edit.json").write_text(json.dumps(edl, indent=2))
    print(json.dumps(edl, indent=2))
    return 0 if edl["verification"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
