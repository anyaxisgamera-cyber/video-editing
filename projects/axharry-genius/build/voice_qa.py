"""Voice QA for the reference-voice conversion (run with networking disabled).

Usage: python build/voice_qa.py RUN_DIR OUT_JSON

Measures, with local models only:
  * speaker similarity (SpeechBrain ECAPA cosine) against the reference recording, with a
    same-speaker ceiling (reference half A vs half B) and the Adam baseline for comparison;
  * intelligibility: Whisper transcript per Telugu line (large-v3-turbo) and for the English line (small);
  * timing: length equality and speech-envelope correlation between source and conversion;
  * clipping: peak level and share of samples at or above -0.1 dBFS.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "brand" / "voice" / "(256k)_vocals_mixed.m4a"


def load(path, sr=16000) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


def norm(t: str) -> str:
    return re.sub(r"[^\wఀ-౿]", "", unicodedata.normalize("NFC", t.lower()))


def envelope(x: np.ndarray, sr=16000, hop=0.02) -> np.ndarray:
    h = int(sr * hop)
    n = len(x) // h
    return np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(1) + 1e-10)


def main() -> None:
    run, out_json = Path(sys.argv[1]), Path(sys.argv[2])
    from speechbrain.inference.speaker import EncoderClassifier

    ecapa = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                           savedir=str(ROOT / "work" / "voice" / "ecapa"), run_opts={"device": "cpu"})

    def emb(x):
        with torch.no_grad():
            e = ecapa.encode_batch(torch.from_numpy(x).unsqueeze(0)).squeeze()
        return e / e.norm()

    ref = load(REF)
    half = len(ref) // 2
    r_full = emb(ref)
    sim = {"ceiling_ref_halfA_vs_halfB": float(emb(ref[:half]) @ emb(ref[half:]))}
    items = {
        "telugu_adam_source": run / "in" / "te_narration.wav",
        "telugu_converted": run / "out" / "te_narration_ref.wav",
        "english_line16_adam_source": run / "in" / "en_line16.wav",
        "english_line16_converted": run / "out" / "en_line16_ref.wav",
    }
    audio = {k: load(v) for k, v in items.items()}
    for k, x in audio.items():
        sim[k] = float(emb(x) @ r_full)

    timing, clipping = {}, {}
    for src, dst in (("telugu_adam_source", "telugu_converted"), ("english_line16_adam_source", "english_line16_converted")):
        a, b = envelope(audio[src]), envelope(audio[dst])
        n = min(len(a), len(b))
        timing[dst] = {"source_s": round(len(audio[src]) / 16000, 3), "converted_s": round(len(audio[dst]) / 16000, 3),
                       "envelope_correlation": round(float(np.corrcoef(np.log(a[:n]), np.log(b[:n]))[0, 1]), 3)}
    for k in ("telugu_converted", "english_line16_converted"):
        x = load(items[k], 22050)
        clipping[k] = {"peak_dbfs": round(20 * np.log10(np.abs(x).max() + 1e-9), 2),
                       "share_at_or_above_-0.1dBFS": float((np.abs(x) >= 0.9886).mean())}

    from faster_whisper import WhisperModel

    words = json.loads((ROOT / "work" / "te" / "words.json").read_text(encoding="utf-8"))
    content = json.loads((ROOT / "content" / "te.json").read_text(encoding="utf-8"))
    te_audio = audio["telugu_converted"]
    big = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    lines = []
    for li, line in enumerate(content["lines"]):
        lw = [w for w in words if w["line"] == li]
        s0, s1 = max(0, lw[0]["start"] - 0.15), lw[-1]["end"] + 0.2
        seg = te_audio[int(s0 * 16000): int(s1 * 16000)]
        txt = " ".join(s.text for s in big.transcribe(seg, language="te", beam_size=5)[0]).strip()
        lines.append({"line": li + 1, "similarity": round(difflib.SequenceMatcher(None, norm(line["text"]), norm(txt),
                                                                                 autojunk=False).ratio(), 3), "heard": txt})
    small = WhisperModel("small", device="cpu", compute_type="int8")
    en_txt = " ".join(s.text for s in small.transcribe(audio["english_line16_converted"], language="en", beam_size=5)[0]).strip()
    en_ref = "From now on, I share my knowledge."
    report = {
        "speaker_similarity_vs_reference": {k: round(v, 3) for k, v in sim.items()},
        "telugu_lines": lines,
        "telugu_mean_line_similarity": round(float(np.mean([l["similarity"] for l in lines])), 3),
        "english_line16": {"heard": en_txt, "similarity": round(difflib.SequenceMatcher(None, norm(en_ref), norm(en_txt),
                                                                                         autojunk=False).ratio(), 3)},
        "timing": timing,
        "clipping": clipping,
    }
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("speaker_similarity_vs_reference", "telugu_mean_line_similarity",
                                              "english_line16", "timing", "clipping")}, ensure_ascii=False, indent=1))
    for l in lines:
        print(f"{l['line']:2d} {l['similarity']:.2f} | {l['heard']}")


if __name__ == "__main__":
    main()
