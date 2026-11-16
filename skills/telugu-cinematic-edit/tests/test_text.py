#!/usr/bin/env python3
"""Dependency-free unit tests for the Telugu text layer (numbers, clauses, CER, subtitle cue building).

    python3 skills/telugu-cinematic-edit/tests/test_text.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from telugu_text import aksharas, cardinal, cer, clauses, latin_words, ordinal, spoken_reference, telugu_ratio, tts_clean  # noqa: E402
from telugu_script import subtitle_cues, _two_lines, LINE_AKSHARAS  # noqa: E402
import bible  # noqa: E402

FAILS = []


def eq(name, got, want):
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")


eq("cardinal 23", cardinal(23), "ఇరవై మూడు")
eq("cardinal 119", cardinal(119), "నూట పందొమ్మిది")
eq("cardinal 150", cardinal(150), "నూట యాభై")
eq("ordinal 1", ordinal(1), "ఒకటవ")
eq("ordinal 20", ordinal(20), "ఇరవయ్యవ")
eq("ordinal 23", ordinal(23), "ఇరవై మూడవ")
eq("ordinal 100", ordinal(100), "వందవ")
eq("spoken ref", spoken_reference("కీర్తనలు", 23, 1), "కీర్తనలు ఇరవై మూడవ అధ్యాయం ఒకటవ వచనం")
eq("clauses", [c["pause"] for c in clauses("యెహోవా నా కాపరి. నాకు ఏ లోటూ లేదు.")], ["sentence", "end"])
eq("clauses comma", [c["pause"] for c in clauses("దారి సుదీర్ఘంగా ఉన్నప్పుడు, మనం ఒంటరివాళ్లం కాదు.")], ["clause", "end"])
eq("cer identical", cer("నేను గొర్రెలకు", "నేను గొర్రెలకు"), 0.0)
eq("cer spelling variant", cer("యేసు ఇలా అన్నారు", "ఏసు ఇలా అన్నారు"), 0.0)
eq("cer ye/e length", cer("యెహోవా నా కాపరి", "ఏహోవా నా కాపరి"), 0.0)
eq("telugu ratio", round(telugu_ratio("యెహోవా నా కాపరి"), 3), 1.0)
eq("latin words", latin_words("యెహోవా Lord నా"), ["Lord"])
eq("aksharas", aksharas("యెహోవా"), 3)
eq("tts clean", tts_clean("“నేను లోకానికి వెలుగును.”", {c for c in "నేలోకానికివెలుగును"} | {" ", "్", "ే", "ో", "ా", "ి", "ె", "ు"})[0],
   "నేను లోకానికి వెలుగును")
# references in English text
eq("find refs", [r["usfm"] for r in bible.find_refs("as Psalm 23:1 and John 10:11-12 say")], ["PSA 23:1", "JHN 10:11-12"])
eq("parse ref", bible.parse_ref("1 Corinthians 13:4"), ("1CO", 13, 4, 4))

# subtitle cues from exact clause timings
sc = {"segments": [
    {"id": "s01", "kind": "narration", "te": "జీవితంలోని ప్రతి దశలోనూ మనం సరైన దారి కోసం వెతుకుతూనే ఉంటాం."},
    {"id": "s02", "kind": "scripture", "te": "యెహోవా నా కాపరి. నాకు ఏ లోటూ లేదు.",
     "ref": {"local": "కీర్తన 23:1", "spoken": "కీర్తనలు ఇరవై మూడవ అధ్యాయం ఒకటవ వచనం"}, "speak_reference": False},
]}
voice = {"segments": {
    "s01": {"clauses": [{"text": sc["segments"][0]["te"], "start": 0.0, "end": 6.4}]},
    "s02": {"clauses": [{"text": "యెహోవా నా కాపరి.", "start": 0.0, "end": 1.4}, {"text": "నాకు ఏ లోటూ లేదు.", "start": 1.85, "end": 3.2}]},
}}
cues = subtitle_cues(sc, voice, {"s01": 1.0, "s02": 8.0})
eq("cue count", len(cues), 3)
eq("cue 1 start", cues[0]["start"], 1.0)
eq("cue 2 text", cues[1]["text"], "యెహోవా నా కాపరి.")
eq("cue 3 start", cues[2]["start"], 9.85)
eq("no overlaps", all(a["end"] <= b["start"] for a, b in zip(cues, cues[1:])), True)
two = _two_lines("దారి సుదీర్ఘంగా ఉన్నప్పుడు, ముందున్న మార్గం అస్పష్టంగా ఉన్నప్పుడు కూడా, మనం ఒంటరివాళ్లం కాదు.")
eq("two lines", two.count("\n"), 1)
eq("line length", all(aksharas(x) <= LINE_AKSHARAS + 4 for x in two.split("\n")), True)

if FAILS:
    print("\n".join("FAIL " + f for f in FAILS))
    sys.exit(1)
print("telugu text tests: all passed")
