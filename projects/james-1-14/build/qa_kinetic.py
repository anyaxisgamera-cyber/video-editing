"""Word-level sync QA for the kinetic cut, on the delivered MP4.

Usage: python build/qa_kinetic.py LANG output/X.mp4 motion/props/LANG-kinetic.json work/LANG-kinetic/qa.json [--model small]

1. Speech activity: every revealed word's spoken interval must contain speech.
2. Whisper ASR word onsets are aligned to the planned words (sequence match on
   normalized text); onset deltas show whether reveals land on the voice.
3. Script similarity of the full transcript (Telugu ASR is weak: the VAD check
   and per-word onsets carry the verdict; similarity is informational).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np

SR = 16000


def norm(t: str) -> str:
    return re.sub(r"[^\wఀ-౿]", "", unicodedata.normalize("NFC", t.lower()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("lang")
    ap.add_argument("video")
    ap.add_argument("props")
    ap.add_argument("report")
    ap.add_argument("--model", default="small")
    a = ap.parse_args()

    props = json.loads(Path(a.props).read_text(encoding="utf-8"))
    words = [w for s in props["scenes"] for w in s["words"]]
    audio = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", a.video, "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
                                          "-f", "f32le", "-"], capture_output=True, check=True).stdout, dtype="<f4")

    hop = int(0.02 * SR)
    n = len(audio) // hop
    fr = audio[: n * hop].reshape(n, hop)
    spec = np.abs(np.fft.rfft(fr * np.hanning(hop), axis=1)) ** 2
    f = np.fft.rfftfreq(hop, 1 / SR)
    e = 10 * np.log10(spec[:, (f > 250) & (f < 3800)].mean(axis=1) + 1e-12)
    t = np.arange(n) * 0.02
    # Reference level: the music + effects in the gap before the first word.
    first = words[0]["start"]
    noise = e[(t > 0.05) & (t < max(0.1, first - 0.05))]
    thr = float(np.percentile(noise, 95) + 6.0) if noise.size else float(np.percentile(e, 30))
    speech = np.convolve((e > thr).astype(float), np.ones(15), mode="same") > 0

    word_rows = []
    for w in words:
        m = (t >= w["start"]) & (t <= w["end"])
        frac = float(speech[m].mean()) if m.any() else 0.0
        word_rows.append({"text": w["text"], "start": w["start"], "speech_fraction": round(frac, 2)})
    vad_ok = sum(r["speech_fraction"] >= 0.5 for r in word_rows) / len(word_rows)

    from faster_whisper import WhisperModel

    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language=a.lang, word_timestamps=True, beam_size=5, condition_on_previous_text=False)
    asr = [w for s in segs for w in (s.words or [])]
    asr_norm = [norm(w.word) for w in asr]
    plan_norm = [norm(w["text"]) for w in words]
    sm = difflib.SequenceMatcher(None, plan_norm, asr_norm, autojunk=False)
    deltas = []
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            deltas.append(asr[block.b + k].start - words[block.a + k]["start"])
    d = np.abs(np.array(deltas)) if deltas else np.array([np.nan])
    similarity = difflib.SequenceMatcher(None, "".join(plan_norm), "".join(asr_norm), autojunk=False).ratio()

    report = {
        "language": a.lang,
        "video": a.video,
        "words_planned": len(words),
        "vad_words_with_speech": round(vad_ok, 3),
        "asr_words_matched": len(deltas),
        "onset_delta_median_s": round(float(np.nanmedian(d)), 3),
        "onset_delta_p90_s": round(float(np.nanpercentile(d, 90)), 3),
        "script_similarity": round(similarity, 3),
        "asr_text": " ".join(w.word.strip() for w in asr),
        "words": word_rows,
    }
    report["passed"] = bool(vad_ok >= 0.95 and (a.lang != "en" or (report["onset_delta_p90_s"] <= 0.25 and similarity >= 0.9)))
    Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("language", "words_planned", "vad_words_with_speech", "asr_words_matched",
                                              "onset_delta_median_s", "onset_delta_p90_s", "script_similarity", "passed")},
                     ensure_ascii=False))
    print("ASR:", report["asr_text"])


if __name__ == "__main__":
    main()
