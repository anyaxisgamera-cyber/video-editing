"""Phase B (network OFF, isolated): Seed-VC conversion from local, verified files only.

Usage (inside build/seedvc/run_isolated.sh only): python convert_offline.py RUN_DIR

RUN_DIR layout:
  models/            verified files from fetch_models.py
  in/ref.wav         25 s excerpt of the reference voice (22.05 kHz mono)
  in/jobs.json       [{"src": "in/<name>.wav", "out": "out/<name>.wav"}, ...]
  out/               converted audio (only writable output)

Safety measures:
  * torch.load is forced to weights_only=True (tensors/primitive containers only), so a
    tampered pickle checkpoint cannot execute code; a checkpoint that needs more than
    that fails loudly instead of being loaded unsafely.
  * Only the base speaking-voice pipeline is built (DiT whisper-small, CAM++, BigVGAN
    22 kHz). The F0/44 kHz models and RMVPE from the stock wrapper are never loaded.
  * Hugging Face loaders are pointed at local directories; HF_HUB_OFFLINE=1.
"""

from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

torch.load = functools.partial(torch.load, weights_only=True)  # refuse arbitrary pickles

RUN = Path(sys.argv[1]).resolve()
M = RUN / "models"
SEED = Path(os.environ["SEEDVC_DIR"])
sys.path.insert(0, str(SEED))
os.chdir(SEED)

import yaml  # noqa: E402
from modules.audio import mel_spectrogram  # noqa: E402
from modules.bigvgan import bigvgan  # noqa: E402
from modules.campplus.DTDNN import CAMPPlus  # noqa: E402
from modules.commons import build_model, load_checkpoint, recursive_munch  # noqa: E402
from seed_vc_wrapper_cpu import SeedVCWrapper  # noqa: E402
from transformers import AutoFeatureExtractor, WhisperModel  # noqa: E402


class BaseOnlyWrapper(SeedVCWrapper):
    def __init__(self):  # noqa: D401 - replaces the stock loader entirely
        self.device = torch.device("cpu")
        cfg_path = M / "Plachta__Seed-VC" / "config_dit_mel_seed_uvit_whisper_small_wavenet.yml"
        config = yaml.safe_load(open(cfg_path))
        params = recursive_munch(config["model_params"])
        self.model = build_model(params, stage="DiT")
        self.hop_length = config["preprocess_params"]["spect_params"]["hop_length"]
        self.sr = config["preprocess_params"]["sr"]
        self.model, _, _, _ = load_checkpoint(self.model, None,
                                              str(M / "Plachta__Seed-VC" / "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth"),
                                              load_only_params=True, ignore_modules=[], is_distributed=False)
        for k in self.model:
            self.model[k].eval()
        self.model.cfm.estimator.setup_caches(max_batch_size=1, max_seq_length=8192)
        sp = config["preprocess_params"]["spect_params"]
        args = dict(n_fft=sp["n_fft"], win_size=sp["win_length"], hop_size=sp["hop_length"], num_mels=sp["n_mels"],
                    sampling_rate=self.sr, fmin=0, fmax=None, center=False)
        self.to_mel = lambda x: mel_spectrogram(x, **args)
        whisper_dir = str(M / "openai__whisper-small")
        self.whisper_model = WhisperModel.from_pretrained(whisper_dir, torch_dtype=torch.float32, local_files_only=True)
        del self.whisper_model.decoder
        self.whisper_feature_extractor = AutoFeatureExtractor.from_pretrained(whisper_dir, local_files_only=True)
        self.campplus_model = CAMPPlus(feat_dim=80, embedding_size=192)
        self.campplus_model.load_state_dict(torch.load(str(M / "funasr__campplus" / "campplus_cn_common.bin"), map_location="cpu"))
        self.campplus_model.eval()
        self.bigvgan_model = bigvgan.BigVGAN.from_pretrained(str(M / "nvidia__bigvgan_v2_22khz_80band_256x"), use_cuda_kernel=False)
        self.bigvgan_model.remove_weight_norm()
        self.bigvgan_model = self.bigvgan_model.eval()
        self.overlap_frame_len = 16
        self.bitrate = "320k"


def main() -> None:
    vc = BaseOnlyWrapper()
    jobs = json.loads((RUN / "in" / "jobs.json").read_text())
    for job in jobs:
        src, out = RUN / job["src"], RUN / job["out"]
        n = sf.info(src).frames
        gen = vc.convert_voice(str(src), str(RUN / "in" / "ref.wav"), diffusion_steps=int(job.get("steps", 30)),
                               length_adjust=1.0, inference_cfg_rate=float(job.get("cfg", 0.7)),
                               f0_condition=False, stream_output=False)
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            audio = np.asarray(stop.value, dtype=np.float32).reshape(-1)
        audio = audio[:n] if len(audio) >= n else np.pad(audio, (0, n - len(audio)))
        sf.write(out, audio, 22050)
        print(f"converted {job['src']} -> {job['out']} ({n / 22050:.2f}s)", flush=True)


if __name__ == "__main__":
    main()
