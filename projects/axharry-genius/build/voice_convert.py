"""Convert narration to the AXHARRY reference voice locally (OpenVoice V2 tone-color converter).

Usage:
  python build/voice_convert.py SRC.wav OUT.wav [--ref brand/voice/(256k)_vocals_mixed.m4a] [--tau 0.3]

- The reference audio is read only; it is never modified or uploaded.
- The speaker embedding of the reference is computed from ~8 s windows across the
  whole file and cached in work/voice/ref_se.pt so every video uses the same identity.
- Conversion keeps timing sample-accurate (output length == input length), so word
  timestamps measured on SRC remain valid for OUT.
Requires: openvoice (MIT), checkpoint myshell-ai/OpenVoiceV2 (converter/) from Hugging Face.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from openvoice.api import OpenVoiceBaseClass, ToneColorConverter

ROOT = Path(__file__).resolve().parent.parent
REF_DEFAULT = ROOT / "brand" / "voice" / "(256k)_vocals_mixed.m4a"
CACHE = ROOT / "work" / "voice"


def decode(path: Path, sr: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


def windows(x: np.ndarray, sr: int, seconds: float = 8.0) -> list[np.ndarray]:
    n = int(seconds * sr)
    return [x[i:i + n] for i in range(0, len(x) - n // 2, n)]


def embed(conv: ToneColorConverter, audio: np.ndarray, sr: int) -> torch.Tensor:
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, w in enumerate(windows(audio, sr)):
            p = Path(tmp) / f"w{i}.wav"
            sf.write(p, w, sr)
            paths.append(str(p))
        return conv.extract_se(paths)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--ref", default=str(REF_DEFAULT))
    ap.add_argument("--tau", type=float, default=0.3)
    a = ap.parse_args()

    ckpt = Path(snapshot_download("myshell-ai/OpenVoiceV2", allow_patterns=["converter/*"])) / "converter"
    # Upstream passes enable_watermark through to a base class that rejects it; build the
    # converter the way enable_watermark=False would (no watermark model).
    conv = ToneColorConverter.__new__(ToneColorConverter)
    OpenVoiceBaseClass.__init__(conv, str(ckpt / "config.json"), device="cpu")
    conv.watermark_model = None
    conv.version = getattr(conv.hps, "_version_", "v1")
    conv.load_ckpt(str(ckpt / "checkpoint.pth"))
    sr = conv.hps.data.sampling_rate

    CACHE.mkdir(parents=True, exist_ok=True)
    ref_cache = CACHE / "ref_se.pt"
    if ref_cache.exists():
        tgt_se = torch.load(ref_cache)
    else:
        tgt_se = embed(conv, decode(Path(a.ref), sr), sr)
        torch.save(tgt_se, ref_cache)

    src_audio = decode(Path(a.src), sr)
    src_se = embed(conv, src_audio, sr)
    with tempfile.TemporaryDirectory() as tmp:
        src_wav = Path(tmp) / "src.wav"
        sf.write(src_wav, src_audio, sr)
        out_tmp = Path(tmp) / "out.wav"
        conv.convert(audio_src_path=str(src_wav), src_se=src_se, tgt_se=tgt_se, output_path=str(out_tmp), tau=a.tau)
        y, ysr = sf.read(out_tmp)
    # keep the exact source length so word timings stay valid; deliver 48 kHz mono
    y = y[: len(src_audio)] if len(y) >= len(src_audio) else np.pad(y, (0, len(src_audio) - len(y)))
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "y.wav"
        sf.write(p, y, ysr)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", a.out],
                       check=True)
    print(f"{a.out}: {len(src_audio) / sr:.2f}s converted (tau={a.tau})")


if __name__ == "__main__":
    main()
