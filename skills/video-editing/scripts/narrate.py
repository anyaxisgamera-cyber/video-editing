#!/usr/bin/env python3
"""Narration for a production: synthesize (or ingest) each scene, verify it by speech recognition, register it.

    PY narrate.py PROD --video v01 --language te --voice piper:te_IN-padmavathi-medium [--speed 1.0]
        [--candidates 3] [--max-error 0.12] [--scenes s01,s02] [--no-asr] [--asr-model small]
    PY narrate.py PROD --video v01 --language en --voice kokoro:bf_emma
    PY narrate.py PROD --video v01 --language en --voice files --recordings DIR --licence "…" [--licence-url …]
    PY narrate.py voices                      # built-in voice catalogue with licences

PY is a Python with numpy, soundfile, librosa and scipy, plus the engine you use (piper-tts for `piper:`,
openai-whisper / transformers for ASR). Kokoro may live in a separate interpreter: set KOKORO_PYTHON.

Licences (checked 18 Nov 2026 on the model cards):
  kokoro:*                     hexgrad/Kokoro-82M, Apache-2.0                                → commercial use OK
  piper:te_IN-padmavathi/venkatesh  Piper voices repo MIT; trained on AI4Bharat IndicVoices-R, CC BY 4.0
                                                                                            → commercial OK with attribution
  piper:en_GB-cori-high, en_US-ljspeech-high   public-domain training data                  → commercial OK
  piper:te_IN-maya-medium      dataset licence (IITM IndicTTS) could not be verified        → unknown: blocked commercially
  other piper voices           licence read from the voice's MODEL_CARD at download time
  mms:<iso3>                   facebook/mms-tts-*, CC-BY-NC-4.0                             → NON-commercial only
  espeak:<lang>                espeak-ng output is not restricted (robotic; scratch use)
  files                        human recordings; the licence you pass is recorded

Each output: narration/<video>/<lang>/<scene>.wav (48 kHz mono, trimmed, 80 Hz high-pass, speech RMS −20 dBFS,
peak ≤ −3 dBFS), a register entry (kind voice, licence, evidence, ASR result), narration/<video>/<lang>/voice.json,
and for English a Whisper `<scene>.words.json` when the recognized words match the script (real word timings for
captions). The pronunciation lexicon plan/lexicon.<lang>.json ({"word": "respelling"}) changes only what the voice
is given; captions keep the script text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import production as P  # noqa: E402

SR = 48000
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
VOICES = {
    "kokoro": {"licence": {"name": "Apache-2.0 (hexgrad/Kokoro-82M)", "url": "https://huggingface.co/hexgrad/Kokoro-82M",
                           "commercial_use": "yes", "attribution_required": "no"}},
    "piper:te_IN-padmavathi-medium": {"licence": {
        "name": "MIT (Piper voice) + CC BY 4.0 training data (AI4Bharat IndicVoices-R)",
        "url": "https://huggingface.co/rhasspy/piper-voices/blob/main/te/te_IN/padmavathi/medium/MODEL_CARD",
        "commercial_use": "yes", "attribution_required": "yes",
        "attribution": "Telugu voice: Piper te_IN-padmavathi-medium, trained on AI4Bharat IndicVoices-R (CC BY 4.0)"}},
    "piper:te_IN-venkatesh-medium": {"licence": {
        "name": "MIT (Piper voice) + CC BY 4.0 training data (AI4Bharat IndicVoices-R)",
        "url": "https://huggingface.co/rhasspy/piper-voices/blob/main/te/te_IN/venkatesh/medium/MODEL_CARD",
        "commercial_use": "yes", "attribution_required": "yes",
        "attribution": "Telugu voice: Piper te_IN-venkatesh-medium, trained on AI4Bharat IndicVoices-R (CC BY 4.0)"}},
    "piper:te_IN-maya-medium": {"licence": {
        "name": "IITM IndicTTS dataset licence (not verifiable: licence URL unreachable)",
        "url": "https://www.iitm.ac.in/donlab/indictts/downloads/license.pdf", "commercial_use": "unknown",
        "attribution_required": "yes"}},
    "piper:en_GB-cori-high": {"licence": {"name": "MIT (Piper voice) + public-domain training data (LibriVox)",
                                          "url": "https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/cori/high/MODEL_CARD",
                                          "commercial_use": "yes", "attribution_required": "no"}},
    "piper:en_US-ljspeech-high": {"licence": {"name": "MIT (Piper voice) + public-domain training data (LJ Speech)",
                                              "url": "https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/high/MODEL_CARD",
                                              "commercial_use": "yes", "attribution_required": "no"}},
    "mms": {"licence": {"name": "CC-BY-NC-4.0 (Meta MMS-TTS)", "url": "https://huggingface.co/facebook/mms-tts",
                        "commercial_use": "no", "attribution_required": "yes"}},
    "espeak": {"licence": {"name": "espeak-ng (GPL-3.0 program; generated audio unrestricted)",
                           "url": "https://github.com/espeak-ng/espeak-ng", "commercial_use": "yes", "attribution_required": "no"}},
}
ISO3 = {"en": "eng", "te": "tel", "hi": "hin", "ta": "tam", "kn": "kan", "ml": "mal", "bn": "ben", "mr": "mar"}


def voice_licence(voice: str, cache: Path) -> dict:
    if voice in VOICES:
        return dict(VOICES[voice]["licence"])
    engine = voice.split(":")[0]
    if engine in ("kokoro", "mms", "espeak"):
        return dict(VOICES[engine]["licence"])
    if engine == "piper":
        card = piper_files(voice.split(":", 1)[1], cache)["card"]
        text = card.read_text(errors="ignore")
        m = re.search(r"License:\s*(.+)", text)
        name = (m.group(1).strip() if m else "unknown")
        import providers
        lic = providers.classify_licence(None, name, name if name.startswith("http") else None)
        lic["name"] = f"MIT (Piper voice) + training data licence: {name}"
        if name.lower().startswith(("http", "see url")) and lic["commercial_use"] == "yes":
            lic["commercial_use"] = "unknown"
        return lic
    return {"name": "user-supplied recording", "commercial_use": "unknown", "attribution_required": "no"}


# ------------------------------------------------------------------ engines


def piper_files(name: str, cache: Path) -> dict:
    """Download a Piper voice (onnx + json + MODEL_CARD) once into the cache; path from voices.json."""
    cache.mkdir(parents=True, exist_ok=True)
    idx = cache / "voices.json"
    if not idx.exists():
        urllib.request.urlretrieve(PIPER_BASE + "voices.json", idx)
    meta = json.loads(idx.read_text()).get(name)
    if not meta:
        raise SystemExit(f"unknown Piper voice {name!r} (see {PIPER_BASE}voices.json)")
    out = {}
    for rel in meta["files"]:
        dst = cache / Path(rel).name
        if not dst.exists():
            urllib.request.urlretrieve(PIPER_BASE + rel, dst)
        out["onnx" if rel.endswith(".onnx") else "json" if rel.endswith(".onnx.json") else "card"] = dst
    return out


class Piper:
    def __init__(self, name: str, cache: Path, speed: float):
        from piper import PiperVoice
        files = piper_files(name, cache)
        self.voice = PiperVoice.load(str(files["onnx"]))
        self.sr = self.voice.config.sample_rate
        self.speed = speed

    def say(self, text: str, variant: int) -> np.ndarray:
        from piper import SynthesisConfig
        cfg = SynthesisConfig(length_scale=1.0 / self.speed, noise_scale=[0.667, 0.5, 0.8][variant % 3],
                              noise_w_scale=[0.8, 0.6, 1.0][variant % 3])
        return np.concatenate([c.audio_float_array for c in self.voice.synthesize(text, syn_config=cfg)])


KOKORO_HELPER = r"""
import sys, json, numpy as np, soundfile as sf
from kokoro import KPipeline
voice, speed, lang, out = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
text = sys.stdin.read()
pipe = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
audio = np.concatenate([np.asarray(a) for _, _, a in pipe(text, voice=voice, speed=speed)])
sf.write(out, audio, 24000)
"""


class Kokoro:
    sr = 24000

    def __init__(self, voice: str, speed: float):
        self.voice, self.speed = voice, speed
        self.lang = {"a": "a", "b": "b"}.get(voice[:1], "a")  # af_/am_ = US English, bf_/bm_ = British English
        self.py = os.environ.get("KOKORO_PYTHON", sys.executable)

    def say(self, text: str, variant: int) -> np.ndarray:
        import soundfile as sf
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "k.wav"
            speed = self.speed * [1.0, 0.97, 1.03][variant % 3]
            r = subprocess.run([self.py, "-c", KOKORO_HELPER, self.voice, str(speed), self.lang, str(out)], input=text,
                               capture_output=True, text=True)
            if r.returncode != 0 or not out.exists():
                raise SystemExit(f"kokoro failed: {r.stderr.strip()[-400:]}")
            x, _ = sf.read(str(out), dtype="float32")
        return x


class MMS:
    def __init__(self, lang: str, speed: float):
        import torch
        from transformers import AutoTokenizer, VitsModel
        name = f"facebook/mms-tts-{ISO3.get(lang, lang)}"
        self.torch, self.model, self.tok = torch, VitsModel.from_pretrained(name).eval(), AutoTokenizer.from_pretrained(name)
        self.model.speaking_rate = speed
        self.sr = self.model.config.sampling_rate

    def say(self, text: str, variant: int) -> np.ndarray:
        self.torch.manual_seed(variant)
        with self.torch.no_grad():
            return self.model(**self.tok(text, return_tensors="pt")).waveform[0].numpy().astype(np.float32)


class Espeak:
    sr = 22050

    def __init__(self, lang: str, speed: float):
        self.lang, self.wpm = lang, int(160 * speed)

    def say(self, text: str, variant: int) -> np.ndarray:
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            subprocess.run(["espeak-ng", "-v", self.lang, "-s", str(self.wpm), "-w", f.name, text], check=True)
            x, self.sr = sf.read(f.name, dtype="float32")
        return x


# ------------------------------------------------------------------ audio + ASR


def frame_db(x: np.ndarray, sr: int, win: float = 0.02) -> np.ndarray:
    n = max(1, int(win * sr))
    m = len(x) // n
    if m == 0:
        return np.array([-120.0])
    return 20 * np.log10(np.sqrt(np.mean(x[: m * n].reshape(m, n) ** 2, axis=1) + 1e-12))


def finish(x: np.ndarray, sr: int) -> np.ndarray:
    import librosa
    from scipy.signal import butter, sosfiltfilt
    x = x.astype(np.float32)
    db = frame_db(x, sr)
    on = np.where(db > max(-45, db.max() - 50))[0]
    if len(on):
        n = int(0.02 * sr)
        x = x[max(0, on[0] * n - int(0.04 * sr)):min(len(x), (on[-1] + 1) * n + int(0.06 * sr))]
    y = librosa.resample(x, orig_sr=sr, target_sr=SR) if sr != SR else x
    y = sosfiltfilt(butter(2, 80, "highpass", fs=SR, output="sos"), y).astype(np.float32)
    db = frame_db(y, SR)
    voiced = db[db > db.max() - 30]
    rms = 10 * np.log10(np.mean(10 ** (voiced / 10))) if len(voiced) else -60
    y *= 10 ** ((-20 - rms) / 20)
    pk = float(np.abs(y).max()) if len(y) else 0
    if pk > 10 ** (-3 / 20):
        y *= 10 ** (-3 / 20) / pk
    f = int(0.008 * SR)
    if len(y) > 2 * f:
        y[:f] *= np.linspace(0, 1, f)
        y[-f:] *= np.linspace(1, 0, f)
    return y


def norm_words(t: str) -> list[str]:
    t = unicodedata.normalize("NFC", t.lower())
    return [w for w in re.findall(r"[\w']+", t) if w]


def wer(ref: str, hyp: str) -> float:
    a, b = norm_words(ref), norm_words(hyp)
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1] / len(a)


def telugu_cer(ref: str, hyp: str) -> float:
    # word-initial ye/e and its vowel length are written inconsistently by ASR (యెహోవా ~ ఏహోవా); fold both sides
    def norm(t):
        t = unicodedata.normalize("NFC", t)
        t = re.sub(r"(^|\s)య[ేె]", r"\1ఏ", t)
        t = re.sub(r"(^|\s)ఎ", r"\1ఏ", t)
        return "".join(c for c in t if "ఀ" <= c <= "౿")
    a, b = norm(ref), norm(hyp)
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1] / len(a)


class ASR:
    """English/other: openai-whisper (word timestamps). Telugu: vasista22/whisper-telugu-small/medium (Apache-2.0)."""

    def __init__(self, lang: str, model: str):
        self.lang, self.model_name = lang, model
        self._m = None
        self._second = None

    def _te(self, name):
        import torch
        from transformers import GenerationConfig, WhisperForConditionalGeneration, WhisperProcessor
        proc = WhisperProcessor.from_pretrained(name)
        m = WhisperForConditionalGeneration.from_pretrained(name).eval()
        m.generation_config = GenerationConfig.from_pretrained("openai/whisper-small")
        return torch, proc, m

    def transcribe(self, y48: np.ndarray, second: bool = False) -> tuple[str, list | None]:
        import librosa
        y = librosa.resample(y48, orig_sr=SR, target_sr=16000).astype(np.float32)
        y = np.concatenate([np.zeros(6400, np.float32), y, np.zeros(4800, np.float32)])
        if self.lang == "te":
            attr = "_second" if second else "_m"
            if getattr(self, attr) is None:
                setattr(self, attr, self._te("vasista22/whisper-telugu-medium" if second else "vasista22/whisper-telugu-small"))
            torch, proc, m = getattr(self, attr)
            feats = proc(y[: 16000 * 29], sampling_rate=16000, return_tensors="pt").input_features
            with torch.no_grad():
                out = m.generate(feats, language="te", task="transcribe", max_new_tokens=440)  # Telugu needs many tokens
            return proc.batch_decode(out, skip_special_tokens=True)[0].strip(), None
        import whisper
        if self._m is None:
            self._m = whisper.load_model(self.model_name)
        r = self._m.transcribe(y, language=self.lang, word_timestamps=True, fp16=False, temperature=0,
                               condition_on_previous_text=False)
        words = [{"word": w["word"].strip(), "start": max(0.0, w["start"] - 0.4), "end": max(0.0, w["end"] - 0.4)}
                 for seg in r["segments"] for w in seg.get("words", [])]
        return r["text"].strip(), words

    def error(self, ref: str, hyp: str) -> float:
        if self.lang == "te":
            return telugu_cer(ref, hyp)
        if self.lang == "en":
            # Whisper writes numbers as digits ("2,000", "1820s"); compare with Whisper's own English normalizer on
            # both sides (the normalizer used for Whisper's published WER), so spelling style is not counted as error
            try:
                from whisper.normalizers import EnglishTextNormalizer
                n = EnglishTextNormalizer()
                hyp = re.sub(r"\b(\d+) and a half\b", r"\1.5", hyp)  # the normalizer maps only spelled-out halves
                return wer(n(ref), n(hyp))
            except ImportError:
                pass
        return wer(ref, hyp)


# ------------------------------------------------------------------ main


def apply_lexicon(text: str, lex: dict) -> str:
    for w, rep in sorted(lex.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<![\w]){re.escape(w)}(?![\w])", rep, text)
    return text


def cmd_narrate(a) -> int:
    import soundfile as sf
    prod = a.production.resolve()
    doc = P.load_prod(prod)
    plan = P.read_json(prod / "plan" / a.video / "scenes.json")
    lang = a.language
    out_dir = prod / "narration" / a.video / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = Path(os.environ.get("PIPER_VOICES_DIR", Path.home() / ".cache" / "piper-voices"))
    lexp = prod / "plan" / f"lexicon.{lang}.json"
    lex = P.read_json(lexp) if lexp.exists() else {}
    only = set(a.scenes.split(",")) if a.scenes else None
    engine_name = a.voice.split(":")[0]
    lic = voice_licence(a.voice, cache) if a.voice != "files" else {
        "name": a.licence or "user-supplied recording", "url": a.licence_url, "commercial_use": a.commercial_use,
        "attribution_required": "no"}
    if doc.get("commercial") and lic["commercial_use"] != "yes":
        print(f"WARNING: {a.voice} licence is {lic['name']} (commercial use: {lic['commercial_use']}). This production is "
              "commercial, so deliverables using this narration will be BLOCKED by audit/render.")
    engine = None
    if engine_name == "piper":
        engine = Piper(a.voice.split(":", 1)[1], cache, a.speed)
    elif engine_name == "kokoro":
        engine = Kokoro(a.voice.split(":", 1)[1], a.speed)
    elif engine_name == "mms":
        engine = MMS(lang, a.speed)
    elif engine_name == "espeak":
        engine = Espeak(a.voice.split(":", 1)[1] if ":" in a.voice else lang, a.speed)
    elif a.voice != "files":
        raise SystemExit(f"unknown voice {a.voice!r}")
    asr = None if a.no_asr else ASR(lang, a.asr_model)
    threshold = a.max_error if a.max_error is not None else (0.12 if lang == "te" else 0.15)
    report_p = out_dir / "voice.json"
    report = P.read_json(report_p) if (only and report_p.exists()) else {"segments": {}}
    report.update({"voice": a.voice, "licence": lic, "speed": a.speed, "lexicon": str(lexp.relative_to(prod)) if lex else None,
                   "asr": None if a.no_asr else ("vasista22/whisper-telugu-small (+medium second opinion)" if lang == "te"
                                                 else f"openai-whisper {a.asr_model}"), "threshold": threshold})
    reg = P.load_register(prod)
    by_id = {x["id"]: x for x in reg["assets"]}
    failures = 0
    narrated = []
    for s in plan.get("scenes", []):
        text = ((s.get("narration") or {}).get(lang) or "").strip()
        if not text or (only and s["id"] not in only):
            continue
        dst = out_dir / f"{s['id']}.wav"
        t0 = time.time()
        best = None
        if a.voice == "files":
            src = next((p for p in Path(a.recordings).glob(f"{s['id']}.*")), None)
            if not src:
                print(f"MISSING recording for {s['id']} in {a.recordings}")
                failures += 1
                continue
            x, sr = sf.read(str(src), dtype="float32", always_2d=True)
            y = finish(x.mean(axis=1), sr)
            best = {"audio": y, "variant": None}
        else:
            spoken = apply_lexicon(text, lex)
            for v in range(max(1, a.candidates)):
                y = finish(engine.say(spoken, v), engine.sr)
                cand = {"audio": y, "variant": v}
                if asr:
                    hyp, words = asr.transcribe(y)
                    cand.update(asr_text=hyp, words=words, error=asr.error(text, hyp))
                if best is None or (asr and cand["error"] < best["error"]):
                    best = cand
                if not asr or cand["error"] <= threshold / 2:
                    break
        if asr and "asr_text" not in best:
            hyp, words = asr.transcribe(best["audio"])
            best.update(asr_text=hyp, words=words, error=asr.error(text, hyp))
        if asr and lang == "te" and best["error"] > threshold:
            h2, _ = asr.transcribe(best["audio"], second=True)  # the small Telugu model drops rare words; ask the medium one
            e2 = asr.error(text, h2)
            best["second_opinion"] = {"text": h2, "error": round(e2, 4)}
            best["error"] = min(best["error"], e2)
        sf.write(str(dst), best["audio"], SR, subtype="PCM_24")
        passed = (not asr) or best["error"] <= threshold
        failures += 0 if passed else 1
        wj = out_dir / f"{s['id']}.words.json"
        aligned = False
        if best.get("words") and len(best["words"]) == len(text.split()):
            P.write_json(wj, {"segments": [{"words": best["words"]}], "source": "openai-whisper word timestamps"})
            aligned = True
        elif wj.exists():
            wj.unlink()
        dur = len(best["audio"]) / SR
        report["segments"][s["id"]] = {"file": dst.name, "duration": round(dur, 3), "text": text,
                                       "spoken_input": apply_lexicon(text, lex) if lex else None,
                                       "variant": best.get("variant"), "asr_text": best.get("asr_text"),
                                       "error": None if not asr else round(best["error"], 4),
                                       "second_opinion": best.get("second_opinion"), "word_timestamps": aligned,
                                       "passed": passed, "seconds": round(time.time() - t0, 1)}
        rid = f"vo-{a.video}-{lang}-{s['id']}"
        by_id[rid] = {"id": rid, "kind": "voice", "title": f"Narration {a.video} {lang} {s['id']}", "creator": a.voice,
                      "source_url": "generated" if a.voice != "files" else "user-supplied", "licence": lic,
                      "evidence": {"note": f"generated with {a.voice}" if a.voice != "files" else f"recording {a.recordings}",
                                   "checked_at": P.now(),
                                   "asr": None if not asr else f"{report['asr']}: error {best['error']:.3f} (threshold {threshold})"},
                      "status": "used", "local_path": str(dst.relative_to(prod)), "sha256": P.sha256(dst),
                      "bytes": dst.stat().st_size, "probe": P.media_facts(dst), "recorded_at": P.now()}
        narrated.append(by_id[rid])
        err = "" if not asr else f" error={best['error']:.3f}"
        print(f"[narrate] {a.video}/{lang}/{s['id']} {dur:5.2f}s{err} {'OK' if passed else 'CHECK'} "
              f"{'(word timings)' if aligned else ''}", flush=True)
    P.save_register_entries(prod, narrated)
    report["all_passed"] = failures == 0
    P.write_json(report_p, report)
    print(json.dumps({"video": a.video, "language": lang, "voice": a.voice, "licence": lic["name"],
                      "commercial_use": lic["commercial_use"], "all_passed": failures == 0}, ensure_ascii=False))
    return 0 if failures == 0 else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("voices", help="list the built-in voice catalogue with licences")
    n = sub.add_parser("run", help="narrate one video and language")
    for p in (n,):
        p.add_argument("production", type=Path); p.add_argument("--video", required=True); p.add_argument("--language", required=True)
        p.add_argument("--voice", required=True, help="piper:<voice>, kokoro:<voice>, mms, espeak[:<lang>], or files")
        p.add_argument("--speed", type=float, default=1.0); p.add_argument("--candidates", type=int, default=3)
        p.add_argument("--max-error", type=float); p.add_argument("--scenes"); p.add_argument("--no-asr", action="store_true")
        p.add_argument("--asr-model", default="small")
        p.add_argument("--recordings", help="folder of <scene>.<ext> recordings (voice=files)")
        p.add_argument("--licence"); p.add_argument("--licence-url")
        p.add_argument("--commercial-use", choices=["yes", "no", "unknown"], default="unknown")
    argv = sys.argv[1:]
    if argv and argv[0] not in ("voices", "run", "-h", "--help"):
        argv = ["run"] + argv  # `narrate.py PROD --video …` is the common form
    a = ap.parse_args(argv)
    if a.cmd == "voices":
        for k, v in VOICES.items():
            print(f"{k:32} commercial={v['licence']['commercial_use']:8} {v['licence']['name']}")
        return 0
    return cmd_narrate(a)


if __name__ == "__main__":
    sys.exit(main())
