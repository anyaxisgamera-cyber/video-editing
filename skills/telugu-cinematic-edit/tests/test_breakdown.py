#!/usr/bin/env python3
"""Score reference_breakdown.py against the ground-truth reference from make_ground_truth.py.

    /opt/cws-venv/bin/python test_breakdown.py GT_DIR [--rebuild] [--reanalyse]

Tolerances: transition start ±2 frames, duration ±4 frames (dips into near-black shots ±8), correct type, shot
count exact, camera move class for the synthetic moves, text events found (fuzzy ≥ 0.6) with start ±0.35 s and
end ±0.5 s, tempo ±3 %, transcript words present, whoosh at the flash.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("gt", type=Path)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--reanalyse", action="store_true")
    a = ap.parse_args()
    if a.rebuild or not (a.gt / "truth.json").exists():
        subprocess.run([PY, HERE / "make_ground_truth.py", a.gt], check=True)
    bdp = a.gt / "breakdown" / "breakdown.json"
    if a.reanalyse or a.rebuild or not bdp.exists():
        subprocess.run([PY, HERE.parent / "scripts" / "reference_breakdown.py", a.gt / "reference.mp4", a.gt / "breakdown",
                        "--asr", "small", "--asr-lang", "en"], check=True)
    T = json.loads((a.gt / "truth.json").read_text())
    B = json.loads(bdp.read_text())
    checks = []

    def ok(name, cond, detail):
        checks.append({"check": name, "passed": bool(cond), "detail": detail})

    det = B["transitions"]
    for tt in T["transitions"]:
        m = min(det, key=lambda d: abs(d["start"] - tt["start"])) if det else None
        dstart = m and m["start"] - tt["start"]
        ok(f"transition {tt['type']} @ {tt['start']}: type", m and m["type"] == tt["type"], m and m["type"])
        ok(f"transition {tt['type']} @ {tt['start']}: start ±2f", m and abs(dstart) <= 2, f"Δ={dstart}")
        if tt.get("frames"):
            tol = 8 if tt["type"] == "dip_to_black" else 4
            ok(f"transition {tt['type']}: duration ±{tol}f", m and abs(m["frames"] - tt["frames"]) <= tol,
               f"{m and m['frames']} vs {tt['frames']}")
        if tt.get("audio_event"):
            ok(f"transition {tt['type']}: audio {tt['audio_event']}", m and tt["audio_event"] in (m.get("audio_event") or ""),
               m and m.get("audio_event"))
    ok("no false transitions", len(det) == len(T["transitions"]), f"{len(det)} detected vs {len(T['transitions'])}")
    ok("shot count", len(B["shots"]) == T["shots"], f"{len(B['shots'])} vs {T['shots']}")
    for idx, mv in T["camera"].items():
        s = B["shots"][int(idx) - 1] if len(B["shots"]) >= int(idx) else None
        ok(f"shot {idx} camera {mv}", s and s["camera"]["move"] == mv, s and s["camera"])
    for tx in T["text"]:
        # the event is found by place and time; the wording is scored separately (Tesseract's Telugu model is weak, so
        # Telugu wording only needs to be recognisably Telugu at the right place — confirm on the saved still)
        telugu = any("\u0C00" <= ch <= "\u0C7F" for ch in tx["text"])
        cands = [e for e in B["text"] if e["position"] == tx["position"] and e["start"] < tx["end"] and e["end"] > tx["start"]]
        best = max(cands, key=lambda e: difflib.SequenceMatcher(None, e["text"], tx["text"]).ratio(), default=None)
        r = best and difflib.SequenceMatcher(None, best["text"], tx["text"]).ratio()
        ok(f"text '{tx['text']}' event found (place+time)", best is not None, best and best["text"])
        if best and telugu:
            ok(f"text '{tx['text']}' read as Telugu", best["script"] == "telugu", f"{best['text']!r} ({r:.2f})")
        elif best:
            ok(f"text '{tx['text']}' wording ≥ 0.8", r >= 0.8, f"{best['text']!r} ({r:.2f})")
        if best:
            ok(f"text '{tx['text']}' start ±0.35s", abs(best["start"] - tx["start"]) <= 0.35, f"{best['start']} vs {tx['start']}")
            ok(f"text '{tx['text']}' end ±0.5s", abs(best["end"] - tx["end"]) <= 0.5, f"{best['end']} vs {tx['end']}")
            ok(f"text '{tx['text']}' position", best["position"] == tx["position"], best["position"])
            ok(f"text '{tx['text']}' entrance", best["entrance"]["style"] == tx["entrance"], best["entrance"])
    au = B.get("audio") or {}
    ok("tempo ±3%", au.get("tempo_bpm") and abs(au["tempo_bpm"] - T["tempo_bpm"]) / T["tempo_bpm"] <= 0.03, au.get("tempo_bpm"))
    words = " ".join(s["text"] for s in au.get("speech", [])).lower()
    ok("speech transcript", all(w in words for w in T["speech_contains"]), words)
    passed = sum(c["passed"] for c in checks)
    for c in checks:
        print(("PASS " if c["passed"] else "FAIL ") + c["check"] + f"  [{c['detail']}]")
    print(f"\n{passed}/{len(checks)} checks passed")
    (a.gt / "breakdown" / "score.json").write_text(json.dumps({"passed": passed, "total": len(checks), "checks": checks},
                                                              ensure_ascii=False, indent=2, default=str))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
