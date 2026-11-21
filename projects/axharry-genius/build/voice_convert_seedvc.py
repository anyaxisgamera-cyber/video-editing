"""Convert narration to the AXHARRY reference voice locally with Seed-VC (zero-shot VC).

Usage:
  SEEDVC_DIR=/path/to/seed-vc python build/voice_convert_seedvc.py SRC.wav OUT.wav
      [--ref "brand/voice/(256k)_vocals_mixed.m4a"] [--ref-start 0] [--steps 30] [--cfg 0.7]

- Seed-VC code: official Hugging Face Space "Plachta/Seed-VC" (GPL-3.0); models are
  downloaded from Hugging Face by its own loader. A CPU-adjusted copy of its wrapper
  (seed_vc_wrapper_cpu.py: float32, autocast off, no Spaces GPU decorator) is used.
- The reference file is read only. A 25 s excerpt (Seed-VC's prompt limit) is
  decoded to a temporary WAV; nothing is uploaded anywhere.
- Output is trimmed/padded to the exact source length so measured word timings hold.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
REF_DEFAULT = ROOT / "brand" / "voice" / "(256k)_vocals_mixed.m4a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--ref", default=str(REF_DEFAULT))
    ap.add_argument("--ref-start", type=float, default=0.0)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=0.7)
    a = ap.parse_args()

    seed_dir = os.environ.get("SEEDVC_DIR")
    if not seed_dir:
        sys.exit("Set SEEDVC_DIR to the Seed-VC code directory")
    os.chdir(seed_dir)  # its loaders use relative config paths
    sys.path.insert(0, seed_dir)
    from seed_vc_wrapper_cpu import SeedVCWrapper  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        ref_wav = Path(tmp) / "ref.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a.ref_start), "-t", "25", "-i", a.ref,
                        "-ac", "1", "-ar", "22050", str(ref_wav)], check=True)
        src_wav = Path(tmp) / "src.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-ac", "1", "-ar", "22050", str(src_wav)], check=True)
        src_len = sf.info(src_wav).frames

        vc = SeedVCWrapper(device=__import__("torch").device("cpu"))
        gen = vc.convert_voice(str(src_wav), str(ref_wav), diffusion_steps=a.steps, length_adjust=1.0,
                               inference_cfg_rate=a.cfg, f0_condition=False, stream_output=False)
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            audio = stop.value
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        audio = audio[:src_len] if len(audio) >= src_len else np.pad(audio, (0, src_len - len(audio)))
        tmp_out = Path(tmp) / "out.wav"
        sf.write(tmp_out, audio, 22050)
        out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp_out), "-ar", "48000", "-ac", "1",
                        "-c:a", "pcm_s24le", str(out)], check=True)
    print(f"{a.out}: {src_len / 22050:.2f}s converted with Seed-VC (steps={a.steps}, cfg={a.cfg})")


if __name__ == "__main__":
    main()
