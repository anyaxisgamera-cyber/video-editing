"""Phase B (network OFF, isolated): Seed-VC conversion from local, verified files only.

Usage (only via build/seedvc/run_isolated.sh):
  python convert_offline.py RUN_DIR              # convert jobs
  python convert_offline.py RUN_DIR --preflight  # install guard + environment checks, then exit
                                                 # (Seed-VC code is never imported in preflight)
RUN_DIR layout:
  models/            verified files from fetch_models.py (read-only)
  in/ref.wav         25 s excerpt of the reference voice (22.05 kHz mono)
  in/jobs.json       [{"src": "in/<name>.wav", "out": "out/<name>.wav", "steps": 30, "cfg": 0.7}, ...]
  out/               converted audio (the only writable output; RUN/home holds caches/tmp)

The guard (guard.py) is installed before Seed-VC is imported: size and SHA-256 checks of all 8
approved files, a torch.load that accepts only the 3 approved pickles with weights_only=True and
re-hashing, and an audit hook that terminates on unpickling, network, subprocess, or writes
outside RUN/out and RUN/home. Only the base speaking-voice pipeline is built.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

RUN = Path(sys.argv[1]).resolve()
PREFLIGHT = "--preflight" in sys.argv[2:]

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I omits the script dir; guard.py sits beside this file
import guard  # noqa: E402  (first non-stdlib import; installs before Seed-VC exists in memory)

guard.install(RUN, verify_files=not PREFLIGHT)


def preflight() -> None:
    checks = {}
    checks["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = os.environ.get("TORCH_FORCE_WEIGHTS_ONLY_LOAD") == "1"
    checks["HF_HUB_OFFLINE"] = os.environ.get("HF_HUB_OFFLINE") == "1"
    checks["no secret-like env vars"] = not [k for k in os.environ if any(
        t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASS", "PROXY", "AUTH"))]
    checks["/home/user hidden"] = not os.listdir("/home/user")
    checks["/root/.ccr hidden"] = not os.path.isdir("/root/.ccr") or not os.listdir("/root/.ccr")
    checks["/root/.claude hidden"] = not os.path.isdir("/root/.claude") or not os.listdir("/root/.claude")
    checks["/mnt/user-data absent"] = not os.path.exists("/mnt/user-data")
    with open("/proc/net/dev") as fh:  # interfaces in this namespace, read without opening sockets
        ifaces = [line.split(":")[0].strip() for line in fh.readlines()[2:]]
    checks[f"only loopback interface ({ifaces})"] = ifaces == ["lo"]
    # /proc/net reflects THIS network namespace (/sys/class/net would show the host's view)
    with open("/proc/net/route") as fh:
        routes = [line for line in fh.read().splitlines()[1:] if line.strip()]
    checks[f"no IPv4 routes in namespace ({len(routes)})"] = not routes
    checks["no IPv6 addresses in namespace"] = (not os.path.exists("/proc/net/if_inet6")
                                                or not open("/proc/net/if_inet6").read().strip())
    for k, v in checks.items():
        print(f"preflight: {'PASS' if v else 'FAIL'}  {k}", flush=True)
    print("preflight: ALL PASS" if all(checks.values()) else "preflight: FAILED", flush=True)
    print("preflight: now attempting a network connection; the guard must terminate the process (exit 20)", flush=True)
    socket.create_connection(("huggingface.co", 443), timeout=2)
    print("preflight: ERROR - connection attempt returned")


def convert() -> None:
    import json

    import numpy as np
    import soundfile as sf
    import torch
    import yaml

    # Inert matplotlib stand-in: Seed-VC imports it only for training-time spectrogram plots.
    # The real package spawns `fc-list` on import (blocked by the guard); nothing here plots.
    import types
    mpl = types.ModuleType("matplotlib")
    mpl.use = lambda *a, **k: None
    pylab = types.ModuleType("matplotlib.pylab")
    mpl.pylab = mpl.pyplot = pylab
    sys.modules.update({"matplotlib": mpl, "matplotlib.pylab": pylab, "matplotlib.pyplot": pylab})

    # urllib3 (via huggingface_hub/transformers) probes IPv6 by creating a socket at import time.
    # The sandbox has no IPv6; declaring that skips the probe, so no socket is ever created.
    socket.has_ipv6 = False

    # numba: never read or write its on-disk cache (cache entries are pickles). librosa defines a
    # cached gufunc at import time; with these no-ops it compiles in memory and nothing is reloaded.
    import numba.core.caching as numba_caching
    numba_caching.Cache.load_overload = lambda self, *a, **k: None
    numba_caching.Cache.save_overload = lambda self, *a, **k: None

    # librosa.load calls audioread.available_backends() on every call (an isinstance check), which
    # shells out to `ldconfig`. Inputs here are WAV paths read by soundfile: report no backends.
    import audioread
    audioread.available_backends = lambda flush_cache=False: ()

    models = RUN / "models"
    seed = Path(os.environ["SEEDVC_DIR"])
    sys.path.insert(0, str(seed))
    os.chdir(seed)
    # Seed-VC needs only dac/nn/{quantize,layers}.py (VectorQuantize). Register bare package
    # shells so dac/__init__.py (full codec + audiotools) is never executed.
    for name, sub in (("dac", "dac"), ("dac.nn", "dac/nn")):
        shell = types.ModuleType(name)
        shell.__path__ = [str(seed / sub)]
        sys.modules[name] = shell
    from modules.audio import mel_spectrogram
    from modules.bigvgan import bigvgan
    from modules.campplus.DTDNN import CAMPPlus
    from modules.commons import build_model, load_checkpoint, recursive_munch
    from seed_vc_wrapper_cpu import SeedVCWrapper
    from transformers import AutoFeatureExtractor, WhisperModel

    class BaseOnlyWrapper(SeedVCWrapper):
        def __init__(self):  # replaces the stock loader (no F0/44 kHz/RMVPE models)
            self.device = torch.device("cpu")
            cfg_path = models / "Plachta__Seed-VC" / "config_dit_mel_seed_uvit_whisper_small_wavenet.yml"
            config = yaml.safe_load(open(cfg_path))
            params = recursive_munch(config["model_params"])
            self.model = build_model(params, stage="DiT")
            self.hop_length = config["preprocess_params"]["spect_params"]["hop_length"]
            self.sr = config["preprocess_params"]["sr"]
            self.model, _, _, _ = load_checkpoint(
                self.model, None, str(models / "Plachta__Seed-VC" / "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth"),
                load_only_params=True, ignore_modules=[], is_distributed=False)
            for k in self.model:
                self.model[k].eval()
            self.model.cfm.estimator.setup_caches(max_batch_size=1, max_seq_length=8192)
            sp = config["preprocess_params"]["spect_params"]
            args = dict(n_fft=sp["n_fft"], win_size=sp["win_length"], hop_size=sp["hop_length"], num_mels=sp["n_mels"],
                        sampling_rate=self.sr, fmin=0, fmax=None, center=False)
            self.to_mel = lambda x: mel_spectrogram(x, **args)
            whisper_dir = str(models / "openai__whisper-small")
            self.whisper_model = WhisperModel.from_pretrained(whisper_dir, torch_dtype=torch.float32,
                                                              local_files_only=True, use_safetensors=True)
            del self.whisper_model.decoder
            self.whisper_feature_extractor = AutoFeatureExtractor.from_pretrained(whisper_dir, local_files_only=True)
            self.campplus_model = CAMPPlus(feat_dim=80, embedding_size=192)
            self.campplus_model.load_state_dict(
                torch.load(str(models / "funasr__campplus" / "campplus_cn_common.bin"), map_location="cpu"))
            self.campplus_model.eval()
            self.bigvgan_model = bigvgan.BigVGAN.from_pretrained(str(models / "nvidia__bigvgan_v2_22khz_80band_256x"),
                                                                 use_cuda_kernel=False)
            self.bigvgan_model.remove_weight_norm()
            self.bigvgan_model = self.bigvgan_model.eval()
            self.overlap_frame_len = 16
            self.bitrate = "320k"

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
    preflight() if PREFLIGHT else convert()
