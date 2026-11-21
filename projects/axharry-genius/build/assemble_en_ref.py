"""Assemble the English reference-voice narration: original recording (lines 1-15) + converted line 16.

Usage: python build/assemble_en_ref.py RUN_DIR [--gap 0.6]

Reads (read-only): brand/voice/(256k)_vocals_mixed.m4a, content/en.json,
                   RUN_DIR/out/en_line16_ref.wav, RUN_DIR/in/en_line16.meta.json
Writes:            work/en-ref/narration.wav (48 kHz mono), work/en-ref/words.json, work/en-ref/alignment-report.json

Word timings for lines 1-15 come from faster-whisper word timestamps on the original recording,
matched in order to the exact script words (difflib). Unmatched script words are interpolated
between matched neighbours and reported. Line 16 keeps the timings measured on its source take
(voice conversion preserves timing), shifted to its new position.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
LEAD = 0.4


def decode(path: Path, sr: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9']", "", t.lower())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--gap", type=float, default=0.6)
    a = ap.parse_args()
    run = Path(a.run)
    content = json.loads((ROOT / "content" / "en.json").read_text())
    out = ROOT / "work" / "en-ref"
    out.mkdir(parents=True, exist_ok=True)

    stem = decode(ROOT / "brand" / "voice" / "(256k)_vocals_mixed.m4a", SR)
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(decode(ROOT / "brand" / "voice" / "(256k)_vocals_mixed.m4a", 16000), language="en",
                               word_timestamps=True, beam_size=5, condition_on_previous_text=False)
    asr = [w for s in segs for w in (s.words or [])]

    script = []
    for li, line in enumerate(content["lines"][:15]):
        for tok in line["text"].split():
            script.append({"display": tok, "line": li})
    sm = difflib.SequenceMatcher(None, [norm(w["display"]) for w in script], [norm(w.word) for w in asr], autojunk=False)
    times: list = [None] * len(script)
    for b in sm.get_matching_blocks():
        for k in range(b.size):
            times[b.a + k] = (asr[b.b + k].start, asr[b.b + k].end)
    matched = sum(t is not None for t in times)
    # interpolate unmatched words between known neighbours
    for i, t in enumerate(times):
        if t is None:
            prev = next((times[j][1] for j in range(i - 1, -1, -1) if times[j]), 0.0)
            nxt_i = next((j for j in range(i + 1, len(times)) if times[j]), None)
            nxt = times[nxt_i][0] if nxt_i is not None else prev + 0.3
            span = (nxt_i - i + 1) if nxt_i is not None else 1
            step = max(0.05, (nxt - prev) / span)
            times[i] = (prev, prev + step)
    words = [{"display": w["display"], "line": w["line"], "start": round(LEAD + t[0], 3), "end": round(LEAD + t[1], 3)}
             for w, t in zip(script, times)]

    # line 16: converted take, placed after the recording's last word + gap
    conv = decode(run / "out" / "en_line16_ref.wav", SR)
    meta = json.loads((run / "in" / "en_line16.meta.json").read_text())
    stem_speech_end = max(t[1] for t in times)
    place = LEAD + stem_speech_end + a.gap
    for w in meta["words"]:
        words.append({"display": w["display"], "line": 15,
                      "start": round(place + (w["start"] - meta["start"]), 3),
                      "end": round(place + (w["end"] - meta["start"]), 3)})

    # match the converted line's loudness to the original recording (EBU R128 integrated loudness)
    def lufs(path: Path) -> float:
        err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])
    stem_i = lufs(ROOT / "brand" / "voice" / "(256k)_vocals_mixed.m4a")
    conv_i = lufs(run / "out" / "en_line16_ref.wav")
    conv = conv * (10 ** ((stem_i - conv_i) / 20))

    total = int((place + len(conv) / SR + 0.2) * SR)
    track = np.zeros(total, dtype=np.float32)
    s0 = int(LEAD * SR)
    track[s0:s0 + len(stem)] += stem[: max(0, total - s0)]
    p0 = int(place * SR)
    track[p0:p0 + len(conv)] += conv[: max(0, total - p0)]
    # headroom: the AAC-decoded original peaks above 0 dBFS; mixing re-normalizes the voice anyway
    track *= 10 ** (-3.0 / 20)
    wav = out / "narration.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_s24le",
                    str(wav)], input=track.tobytes(), check=True)
    (out / "words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    report = {"script_words_lines_1_15": len(script), "matched_by_asr": matched,
              "interpolated": len(script) - matched, "line16_placed_at": round(place, 3),
              "narration_seconds": round(total / SR, 3), "stem_lufs": stem_i, "line16_lufs_before_match": conv_i,
              "line16_gain_db": round(stem_i - conv_i, 2), "headroom_db": -3.0,
              "peak_after": round(float(20 * np.log10(np.abs(track).max() + 1e-9)), 2)}
    (out / "alignment-report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
