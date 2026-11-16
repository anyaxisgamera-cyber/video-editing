#!/usr/bin/env python3
"""Telugu voice-over: synthesize every script segment, verify it by ASR round-trip, and record exact clause timings.

    /opt/cws-venv/bin/python telugu_tts.py synth SCRIPT.json OUT_DIR [--engine mms|espeak|files] [--voice-dir DIR]
        [--rate 0.92] [--candidates 4] [--max-cer 0.12] [--only s03,s05]
    /opt/cws-venv/bin/python telugu_tts.py asr AUDIO [--ref "తెలుగు వాక్యం"]

Engines (licences verified on the model cards / packages):
  mms     facebook/mms-tts-tel (Meta MMS, VITS, 16 kHz). Licence CC-BY-NC-4.0 → output is NON-COMMERCIAL ONLY.
          Every output written by this engine is flagged `commercial_use: false` in voice.json.
  espeak  espeak-ng Telugu voice (GPL-3 program; synthesized audio is not restricted). Robotic — scratch/timing only.
  files   human recordings: VOICE_DIR/<segment id>.wav (preferred for commercial delivery). Timed and verified the
          same way. Clause timings come from pauses detected in the recording.
  Gated / not usable from here without the account owner accepting the model terms: ai4bharat/indic-parler-tts
  (Apache-2.0), ai4bharat/IndicF5 (MIT) — see references/sources.md.

How a segment is made (mms/espeak): the MMS tokenizer has no punctuation, so each clause is synthesized separately
and joined with measured pauses (0.22 s after a comma, 0.45 s after a full stop). N candidates (different noise
seeds) are generated; each is transcribed by a Telugu ASR (vasista22/whisper-telugu-small, Apache-2.0) and the one with
the lowest character error rate (CER) against the script is kept. Output: OUT_DIR/<id>.wav (48 kHz mono 24-bit,
trimmed, 80 Hz high-pass, speech RMS −20 dBFS, peak ≤ −3 dBFS) + OUT_DIR/voice.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telugu_text import cer, clauses, tts_clean  # noqa: E402

SR_OUT = 48000
PAUSE = {"clause": 0.22, "sentence": 0.45, "end": 0.0}
ASR_MODEL = "vasista22/whisper-telugu-small"
ASR_SECOND = "vasista22/whisper-telugu-medium"   # second opinion, only for segments the small model rejects
MMS_MODEL = "facebook/mms-tts-tel"


# ------------------------------------------------------------------ voices


class MMSVoice:
    name, sr, commercial = "mms", 16000, False
    licence = "CC-BY-NC-4.0 (facebook/mms-tts-tel) — non-commercial use only"

    def __init__(self, rate: float = 1.0):
        import torch
        from transformers import AutoTokenizer, VitsModel
        self.torch = torch
        self.model = VitsModel.from_pretrained(MMS_MODEL).eval()
        self.tok = AutoTokenizer.from_pretrained(MMS_MODEL)
        self.vocab = set(self.tok.get_vocab())
        self.model.speaking_rate = rate  # length_scale = 1 / speaking_rate
        self.sr = self.model.config.sampling_rate

    def say(self, text: str, seed: int) -> tuple[np.ndarray, list[str]]:
        clean, dropped = tts_clean(text, self.vocab)
        ids = self.tok(clean, return_tensors="pt")
        self.torch.manual_seed(seed)
        with self.torch.no_grad():
            wav = self.model(**ids).waveform[0].numpy().astype(np.float32)
        return wav, dropped


class EspeakVoice:
    name, sr, commercial = "espeak", 22050, True
    licence = "espeak-ng (GPL-3.0 program; generated audio unrestricted)"

    def __init__(self, rate: float = 1.0):
        self.wpm = int(150 * rate)

    def say(self, text: str, seed: int) -> tuple[np.ndarray, list[str]]:
        import soundfile as sf
        clean, dropped = tts_clean(text)
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            subprocess.run(["espeak-ng", "-v", "te", "-s", str(self.wpm), "-w", f.name, clean], check=True)
            x, sr = sf.read(f.name, dtype="float32")
        self.sr = sr
        return x, dropped


# ------------------------------------------------------------------ ASR


class TeluguASR:
    def __init__(self, model: str = ASR_MODEL):
        import torch
        from transformers import GenerationConfig, WhisperForConditionalGeneration, WhisperProcessor
        self.torch = torch
        self.name = model
        self.proc = WhisperProcessor.from_pretrained(model)
        self.model = WhisperForConditionalGeneration.from_pretrained(model).eval()
        # the fine-tuned checkpoint ships an outdated generation config; use the base model's (same tokenizer)
        self.model.generation_config = GenerationConfig.from_pretrained("openai/whisper-small")

    def transcribe(self, audio: np.ndarray, sr: int) -> str:
        import librosa
        y = librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=16000) if sr != 16000 else audio
        y = np.concatenate([np.zeros(int(0.4 * 16000), np.float32), y, np.zeros(int(0.3 * 16000), np.float32)])
        texts = []
        for a in range(0, len(y), 16000 * 28):  # Whisper window is 30 s
            feats = self.proc(y[a:a + 16000 * 28], sampling_rate=16000, return_tensors="pt").input_features
            with self.torch.no_grad():
                out = self.model.generate(feats, language="te", task="transcribe", max_new_tokens=220)
            texts.append(self.proc.batch_decode(out, skip_special_tokens=True)[0].strip())
        return " ".join(texts)


# ------------------------------------------------------------------ audio helpers


def frame_db(x: np.ndarray, sr: int, win: float = 0.02) -> np.ndarray:
    n = max(1, int(win * sr))
    m = len(x) // n
    if m == 0:
        return np.array([-120.0])
    r = np.sqrt(np.mean(x[: m * n].reshape(m, n) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(r)


def trim(x: np.ndarray, sr: int, thresh_db: float = -45, margin: float = 0.03) -> np.ndarray:
    db = frame_db(x, sr)
    on = np.where(db > max(thresh_db, db.max() - 50))[0]
    if len(on) == 0:
        return x[:0]
    n = int(0.02 * sr)
    a = max(0, on[0] * n - int(margin * sr))
    b = min(len(x), (on[-1] + 1) * n + int(margin * sr))
    return x[a:b]


def finish(x: np.ndarray, sr: int) -> np.ndarray:
    """Resample to 48 kHz, 80 Hz high-pass, speech RMS → −20 dBFS, peak ≤ −3 dBFS, 8 ms fades."""
    import librosa
    from scipy.signal import butter, sosfiltfilt
    y = librosa.resample(x.astype(np.float32), orig_sr=sr, target_sr=SR_OUT) if sr != SR_OUT else x.astype(np.float32)
    y = sosfiltfilt(butter(2, 80, "highpass", fs=SR_OUT, output="sos"), y).astype(np.float32)
    db = frame_db(y, SR_OUT)
    voiced = db[db > db.max() - 30]
    rms_db = 10 * np.log10(np.mean(10 ** (voiced / 10))) if len(voiced) else -60
    y *= 10 ** ((-20 - rms_db) / 20)
    pk = float(np.abs(y).max()) if len(y) else 0
    if pk > 10 ** (-3 / 20):
        y *= 10 ** (-3 / 20) / pk
    f = int(0.008 * SR_OUT)
    if len(y) > 2 * f:
        y[:f] *= np.linspace(0, 1, f)
        y[-f:] *= np.linspace(1, 0, f)
    return y


def pauses_in(x: np.ndarray, sr: int, min_len: float = 0.15) -> list[tuple[float, float]]:
    """Silent stretches inside a recording (for clause timing of human recordings)."""
    db = frame_db(x, sr)
    quiet = db < max(-45, db.max() - 35)
    out, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        if (not q or i == len(quiet) - 1) and start is not None:
            if (i - start) * 0.02 >= min_len and start > 0 and i < len(quiet) - 1:
                out.append((start * 0.02, i * 0.02))
            start = None
    return out


# ------------------------------------------------------------------ segments


def speech_text(seg: dict) -> str:
    """What is spoken: the Telugu text, plus the spoken reference for scripture when requested."""
    t = seg["te"].strip()
    if seg.get("kind") == "scripture" and seg.get("speak_reference") and seg.get("ref", {}).get("spoken"):
        t = t.rstrip() + " " + seg["ref"]["spoken"] + "."
    return t


_second: dict = {}


def second_asr() -> TeluguASR:
    if "m" not in _second:
        _second["m"] = TeluguASR(ASR_SECOND)
    return _second["m"]


def synth_segment(seg: dict, voice, asr: TeluguASR | None, n_cand: int, max_cer: float, rate: float | None = None) -> dict:
    text = speech_text(seg)
    if rate is not None and hasattr(voice, "model"):
        voice.model.speaking_rate = rate
    cls = clauses(text)
    best = None
    cands = []
    for seed in range(n_cand):
        pieces, timing, t, dropped = [], [], 0.0, set()
        for c in cls:
            wav, d = voice.say(c["text"], seed)
            dropped |= set(d)
            wav = trim(wav, voice.sr)
            dur = len(wav) / voice.sr
            timing.append({"text": c["text"], "start": round(t, 3), "end": round(t + dur, 3)})
            pieces.append(wav)
            gap = PAUSE[c["pause"]]
            pieces.append(np.zeros(int(gap * voice.sr), np.float32))
            t += dur + gap
        audio = np.concatenate(pieces) if pieces else np.zeros(1, np.float32)
        hyp = asr.transcribe(audio, voice.sr) if asr else ""
        score = cer(text, hyp) if asr else None
        cand = {"seed": seed, "audio": audio, "clauses": timing, "asr": hyp, "cer": score, "dropped": sorted(dropped)}
        cands.append(cand)
        if best is None or (score is not None and score < best["cer"]):
            best = cand
        if score is not None and score <= 0.04:
            break
    best["tried"] = seed + 1
    if asr and best["cer"] > max_cer:
        # second opinion: the small Telugu ASR drops rare words (e.g. sentence-initial యెహోవా). Re-score the three
        # best candidates with the medium model and keep the candidate with the lowest CER under either model.
        sec = second_asr()
        for c in sorted(cands, key=lambda c: c["cer"])[:3]:
            h2 = sec.transcribe(c["audio"], voice.sr)
            c["second"] = {"model": ASR_SECOND, "text": h2, "cer": round(cer(text, h2), 4)}
            if min(c["cer"], c["second"]["cer"]) < min(best["cer"], best.get("second", {}).get("cer", 9)):
                best = c | {"tried": best["tried"]}
    eff = min(best["cer"], best.get("second", {}).get("cer", 9)) if best["cer"] is not None else None
    best["passed"] = eff is None or eff <= max_cer
    best["effective_cer"] = eff
    return best


def recorded_segment(seg: dict, path: Path, asr: TeluguASR | None, max_cer: float) -> dict:
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = trim(x.mean(axis=1), sr)
    text = speech_text(seg)
    cls = clauses(text)
    gaps = pauses_in(x, sr)
    # assign the clause boundaries to the longest pauses, in order (needs len(cls)-1 pauses)
    k = len(cls) - 1
    chosen = sorted(sorted(gaps, key=lambda g: g[1] - g[0], reverse=True)[:k]) if k > 0 else []
    bounds = [0.0] + [g[0] for g in chosen] + [len(x) / sr]
    starts = [0.0] + [g[1] for g in chosen]
    timing = [{"text": c["text"], "start": round(starts[i], 3), "end": round(bounds[i + 1], 3)}
              for i, c in enumerate(cls)] if len(chosen) == k else \
             [{"text": text, "start": 0.0, "end": round(len(x) / sr, 3)}]
    hyp = asr.transcribe(x, sr) if asr else ""
    score = cer(text, hyp) if asr else None
    return {"seed": None, "audio": x, "sr": sr, "clauses": timing, "asr": hyp, "cer": score, "dropped": [],
            "passed": score is None or score <= max_cer, "tried": 1, "clause_timing": "pauses" if len(chosen) == k else "whole"}


def cmd_synth(a) -> int:
    import soundfile as sf
    script = json.loads(Path(a.script).read_text())
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    asr = None if a.no_asr else TeluguASR()
    voice = None
    if a.engine == "mms":
        voice = MMSVoice(a.rate)
    elif a.engine == "espeak":
        voice = EspeakVoice(a.rate)
    only = set(a.only.split(",")) if a.only else None
    report_path = out / "voice.json"
    report = json.loads(report_path.read_text()) if (only and report_path.exists()) else {"segments": {}}
    report.update({"engine": a.engine, "rate": a.rate, "asr_model": None if a.no_asr else ASR_MODEL,
                   "licence": voice.licence if voice else "human recordings supplied by the user",
                   "commercial_use": voice.commercial if voice else True, "sample_rate": SR_OUT})
    for seg in script["segments"]:
        if not seg.get("speak", True) or (only and seg["id"] not in only):
            continue
        if not seg.get("te"):
            raise SystemExit(f"segment {seg['id']} has no Telugu text — run telugu_script.py validate first")
        t0 = time.time()
        if a.engine == "files":
            r = recorded_segment(seg, Path(a.voice_dir) / f"{seg['id']}.wav", asr, a.max_cer)
            sr, rate = r["sr"], None
        else:
            rate = a.scripture_rate if seg.get("kind") == "scripture" else a.rate
            r = synth_segment(seg, voice, asr, a.candidates, a.max_cer, rate)
            sr = voice.sr
        y = finish(r["audio"], sr)
        dst = out / f"{seg['id']}.wav"
        sf.write(str(dst), y, SR_OUT, subtype="PCM_24")
        dur = len(y) / SR_OUT
        report["segments"][seg["id"]] = {
            "file": dst.name, "duration": round(dur, 3), "spoken_text": speech_text(seg),
            "clauses": r["clauses"],
            "rate": None if a.engine == "files" else rate, "seed": r["seed"], "candidates_tried": r["tried"], "asr_text": r["asr"], "cer": None if r["cer"] is None else round(r["cer"], 4),
            "asr_second": r.get("second"),
            "effective_cer": None if r.get("effective_cer", r["cer"]) is None else round(r.get("effective_cer", r["cer"]), 4),
            "passed": r["passed"], "dropped_chars": r["dropped"], "seconds": round(time.time() - t0, 1)}
        print(f"[tts] {seg['id']} {dur:5.2f}s cer={r['cer'] if r['cer'] is None else round(r['cer'], 3)} "
              f"{'2nd=' + str(r['second']['cer']) + ' ' if r.get('second') else ''}"
              f"seed={r['seed']} tries={r['tried']} {'OK' if r['passed'] else 'CHECK'}", flush=True)
    segs = report["segments"].values()
    report["all_passed"] = all(s["passed"] for s in segs)
    report["mean_cer"] = round(float(np.mean([s.get("effective_cer", s["cer"]) for s in segs if s.get("effective_cer", s["cer"]) is not None])), 4) if asr else None
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"segments": len(report["segments"]), "all_passed": report["all_passed"], "mean_cer": report["mean_cer"],
                      "commercial_use": report["commercial_use"]}, ensure_ascii=False))
    return 0 if report["all_passed"] else 2


def cmd_asr(a) -> int:
    import soundfile as sf
    x, sr = sf.read(a.audio, dtype="float32", always_2d=True)
    hyp = TeluguASR().transcribe(x.mean(axis=1), sr)
    res = {"text": hyp}
    if a.ref:
        res["cer"] = round(cer(a.ref, hyp), 4)
    print(json.dumps(res, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("synth")
    s.add_argument("script"); s.add_argument("out_dir")
    s.add_argument("--engine", default="mms", choices=["mms", "espeak", "files"])
    s.add_argument("--voice-dir", help="folder of <segment id>.wav human recordings (engine=files)")
    s.add_argument("--rate", type=float, default=0.92, help="speaking rate (1 = model default; <1 slower)")
    s.add_argument("--scripture-rate", type=float, default=0.85, help="speaking rate for scripture segments")
    s.add_argument("--candidates", type=int, default=4, help="noise seeds tried per segment (best CER kept)")
    s.add_argument("--max-cer", type=float, default=0.12)
    s.add_argument("--only", help="comma-separated segment ids to (re)make")
    s.add_argument("--no-asr", action="store_true")
    s = sub.add_parser("asr"); s.add_argument("audio"); s.add_argument("--ref")
    a = ap.parse_args(argv)
    return cmd_synth(a) if a.cmd == "synth" else cmd_asr(a)


if __name__ == "__main__":
    sys.exit(main())
