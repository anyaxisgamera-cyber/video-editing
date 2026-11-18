"""Independent narration/subtitle QA on a rendered deliverable.

Usage: python build/qa.py LANG output/James_1_14_English.mp4 work/LANG/qa.json [--model small]

Checks, using only the delivered file's audio plus the cue list:
  1. speech activity (energy VAD on the decoded final audio)
     - every subtitle cue overlaps speech for most of its duration;
     - every speech run longer than 0.3 s is covered by a visible cue.
  2. Whisper ASR (faster-whisper) transcript vs. the script text
     - character-level similarity after normalization;
     - first-word onset of each script line vs. its first cue start.
ASR is a hypothesis: Telugu ASR in particular is weaker, so the VAD checks
carry the sync verdict and ASR similarity is reported with that caveat.
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
ROOT = Path(__file__).resolve().parent.parent


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    return re.sub(r"[^\wఀ-౿]", "", text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("lang")
    ap.add_argument("video")
    ap.add_argument("report")
    ap.add_argument("--model", default="small")
    args = ap.parse_args()

    timeline = json.loads((ROOT / "work" / args.lang / "timeline.json").read_text(encoding="utf-8"))
    content = json.loads((ROOT / "content" / f"{args.lang}.json").read_text(encoding="utf-8"))
    cues = timeline["cues"]
    audio = decode(Path(args.video))

    # The music bed is ducked well below speech; isolate the voice band and gate.
    hop = int(0.02 * SR)
    spec_frames = len(audio) // hop
    frames = audio[: spec_frames * hop].reshape(spec_frames, hop)
    band = np.fft.rfft(frames * np.hanning(hop), axis=1)
    freqs = np.fft.rfftfreq(hop, 1 / SR)
    voice_band = (freqs > 250) & (freqs < 3800)
    energy = 10 * np.log10(np.mean(np.abs(band[:, voice_band]) ** 2, axis=1) + 1e-12)
    music_only = energy[int((timeline["finalStart"] + 0.5) / 0.02): int((timeline["duration"] - 0.8) / 0.02)]
    threshold = float(np.percentile(music_only, 95) + 6.0)
    speech = energy > threshold
    # 150 ms hangover: inter-word gaps and unvoiced consonants are still speech.
    hang = 7
    speech = np.convolve(speech.astype(float), np.ones(2 * hang + 1), mode="same") > 0
    t = np.arange(len(speech)) * 0.02

    cue_results = []
    for cue in cues:
        mask = (t >= cue["start"]) & (t <= cue["end"])
        cover = float(speech[mask].mean()) if mask.any() else 0.0
        cue_results.append({"text": cue["text"], "start": cue["start"], "end": cue["end"], "speech_fraction": round(cover, 3),
                            "ok": cover >= 0.45})

    visible = np.zeros_like(speech)
    for cue in cues:
        visible |= (t >= cue["start"] - 0.12) & (t <= cue["end"] + 0.12)
    uncovered, run = [], 0
    for i, (s, v) in enumerate(zip(speech, visible)):
        run = run + 1 if (s and not v) else 0
        if run == 16:  # 0.32 s of speech with no subtitle on screen
            uncovered.append(round(float(t[i - 15]), 2))

    from faster_whisper import WhisperModel

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio, language=args.lang, word_timestamps=True, vad_filter=False,
                                   beam_size=5, condition_on_previous_text=False)
    words = [w for seg in segments for w in (seg.words or [])]
    asr_text = " ".join(w.word.strip() for w in words)
    script = " ".join(line["text"] for line in content["lines"])
    similarity = difflib.SequenceMatcher(None, norm(script), norm(asr_text)).ratio()

    onsets = []
    for li, line in enumerate(timeline["lines"]):
        first_cue = next(c for c in cues if c["line"] == li)
        nearest = min(words, key=lambda w: abs(w.start - first_cue["start"])) if words else None
        onsets.append({"line": li, "cue_start": first_cue["start"],
                       "asr_word": nearest.word.strip() if nearest else None,
                       "asr_start": round(nearest.start, 3) if nearest else None,
                       "delta": round(nearest.start - first_cue["start"], 3) if nearest else None})

    report = {
        "language": args.lang,
        "video": args.video,
        "vad_threshold_db": round(threshold, 2),
        "cues": cue_results,
        "cues_ok": all(c["ok"] for c in cue_results),
        "uncovered_speech_at": uncovered,
        "asr_model": f"faster-whisper {args.model}",
        "asr_text": asr_text,
        "script_similarity": round(similarity, 3),
        "line_onsets": onsets,
        "max_onset_delta": max((abs(o["delta"]) for o in onsets if o["delta"] is not None), default=None),
    }
    report["passed"] = bool(report["cues_ok"] and not uncovered)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("language", "cues_ok", "uncovered_speech_at", "script_similarity",
                                              "max_onset_delta", "passed")}, ensure_ascii=False))
    print("ASR:", asr_text)


if __name__ == "__main__":
    main()
