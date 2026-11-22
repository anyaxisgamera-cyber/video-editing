"""Per-line Telugu intelligibility of a narration: Whisper large-v3-turbo transcript vs script.

Usage: python build/line_clarity.py content/te.json work/te-brian
Writes WORK/line_clarity.json {mean, lines[], heard[]}.
"""
import difflib, json, re, subprocess, sys, unicodedata
from pathlib import Path
import numpy as np

def norm(t): return re.sub(r"[^\wఀ-౿]", "", unicodedata.normalize("NFC", t.lower()))

content, work = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path(sys.argv[2])
words = json.loads((work / "words.json").read_text(encoding="utf-8"))
x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", str(work / "narration.wav"), "-ac", "1", "-ar", "16000",
                                  "-f", "f32le", "-"], capture_output=True, check=True).stdout, dtype="<f4").copy()
from faster_whisper import WhisperModel
m = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
scores, heard = [], []
for li, line in enumerate(content["lines"]):
    lw = [w for w in words if w["line"] == li]
    s0, s1 = max(0, lw[0]["start"] - 0.15), lw[-1]["end"] + 0.2
    txt = " ".join(s.text for s in m.transcribe(x[int(s0 * 16000):int(s1 * 16000)], language="te", beam_size=5)[0]).strip()
    scores.append(difflib.SequenceMatcher(None, norm(line["text"]), norm(txt), autojunk=False).ratio()); heard.append(txt)
    print(f"{li + 1:2d} {scores[-1]:.2f} | {txt}")
out = {"mean": float(np.mean(scores)), "lines": scores, "heard": heard}
(work / "line_clarity.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("mean", round(out["mean"], 3))
