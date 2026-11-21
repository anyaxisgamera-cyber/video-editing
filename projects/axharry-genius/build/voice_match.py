"""Objective voice-identity check against the AXHARRY reference (SpeechBrain ECAPA, local).

Usage: python build/voice_match.py CANDIDATE.wav [CANDIDATE2.wav ...] [--ref brand/voice/(256k)_vocals_mixed.m4a]

Prints cosine similarity (higher = closer; same-speaker pairs typically score > ~0.5,
different speakers < ~0.3 on this model). A ceiling is reported by comparing the
reference's first half with its second half (same speaker, same recording chain).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import torch
from speechbrain.inference.speaker import EncoderClassifier

ROOT = Path(__file__).resolve().parent.parent
REF_DEFAULT = ROOT / "brand" / "voice" / "(256k)_vocals_mixed.m4a"


def load(path: str) -> torch.Tensor:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return torch.from_numpy(np.frombuffer(raw, dtype="<f4").copy())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--ref", default=str(REF_DEFAULT))
    ap.add_argument("--savedir", default=str(ROOT / "work" / "voice" / "ecapa"))
    a = ap.parse_args()
    model = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir=a.savedir,
                                           run_opts={"device": "cpu"})

    def emb(x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            e = model.encode_batch(x.unsqueeze(0)).squeeze()
        return e / e.norm()

    ref = load(a.ref)
    half = len(ref) // 2
    r_full, r1, r2 = emb(ref), emb(ref[:half]), emb(ref[half:])
    print(f"ceiling  ref half A vs half B : {float(r1 @ r2):.3f}")
    for c in a.candidates:
        print(f"{Path(c).name:30s} vs reference : {float(emb(load(c)) @ r_full):.3f}")


if __name__ == "__main__":
    main()
