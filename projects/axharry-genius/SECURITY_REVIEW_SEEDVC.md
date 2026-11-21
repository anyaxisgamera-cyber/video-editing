# Security review: Seed-VC voice conversion (AXHARRY)

Status: **inspection complete, nothing from Seed-VC has been executed.** Execution awaits owner approval.

## 1. `build/voice_convert_seedvc.py` (earlier runner): do not use

Written before this review and never executed (the environment blocked it). It used the stock
wrapper, which downloads **all** models (including unneeded F0/44 kHz models and RMVPE) without hash
checks, loads pickle checkpoints unrestricted, runs with network access and the full environment
(including credential-bearing variables). It is superseded by `build/seedvc/` below.

## 2. Code provenance

| Item | Source | License | Integrity |
|---|---|---|---|
| Seed-VC code (65 .py files) | Hugging Face Space `Plachta/Seed-VC` @ `84a789170310` | GPL-3.0 | `seed_vc_wrapper.py` and `hf_utils.py` git-blob hashes match the Space (`14caf0cfd3a1`, `4ae986c1d88d`) |
| Local edits (`seed_vc_wrapper_cpu.py`) | copy of the wrapper | GPL-3.0 | removed HF `spaces` GPU decorator; float16 to float32; autocast disabled (CPU) |
| Python deps | PyPI wheels already installed in an isolated venv | various OSS | torch 2.4.1 (CPU), torchaudio 2.4.1, transformers 4.46.3, librosa 0.10.2, munch, einops, pydub, scipy, pyyaml, soundfile, huggingface_hub < 0.26 |

Code paths reached by inference (traced): `seed_vc_wrapper_cpu.py`, `hf_utils.py`, `modules/{audio,commons,diffusion_transformer,encodec,flow_matching,length_regulator,wavenet,rmvpe}.py`, `modules/campplus/*`, `modules/bigvgan/*`, `dac/nn/{layers,quantize}.py`.

Static scan of those paths: **no** `subprocess`, `os.system`, `eval`, `exec`, sockets, `requests`/`urllib`, telemetry, or upload code.
Network calls exist only in Hugging Face loaders (`hf_hub_download`, `from_pretrained`). File writes are
limited to creating `./checkpoints` (download cache) and BigVGAN save helpers that inference never calls.

## 3. Model files (only the base speaking-voice pipeline)

| Repo @ revision | File | Size | SHA-256 (LFS) / git blob | License |
|---|---|---|---|---|
| `Plachta/Seed-VC` @ 257283f9f415 | DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth | 440.3 MB | 8ec8841b20bb46df9f7e8e570a6946a4b87b940133c7f0e778487ff33841f720 | GPL-3.0 |
| `Plachta/Seed-VC` @ 257283f9f415 | config_dit_mel_seed_uvit_whisper_small_wavenet.yml | small | blob fddb287b1ac6 | GPL-3.0 |
| `openai/whisper-small` @ 973afd24965f | model.safetensors | 967.0 MB | 1d7734884874f1a1513ed9aa760a4f8e97aaa02fd6d93a3a85d27b2ae9ca596b | Apache-2.0 |
| `openai/whisper-small` @ 973afd24965f | config.json, preprocessor_config.json | small | blobs 113bb3efe3a7, c2048dfa9fd9 | Apache-2.0 |
| `funasr/campplus` @ e4b6ede7ce16 | campplus_cn_common.bin | 28.0 MB | 3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8 | Apache-2.0 |
| `nvidia/bigvgan_v2_22khz_80band_256x` @ 633ff708ed5b | bigvgan_generator.pt | 449.2 MB | e95ba25972d3de0628d99cd156e9315a9c018899bf739988959ebe3544080ced | MIT |
| `nvidia/bigvgan_v2_22khz_80band_256x` @ 633ff708ed5b | config.json | small | blob 635bd8975629 | MIT |

Not downloaded (stock wrapper would): `DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema.pth`,
`nvidia/bigvgan_v2_44khz_128band_512x`, `lj1995/VoiceConversionWebUI/rmvpe.pt`.

## 4. Findings and risks

1. **Pickle checkpoints (high).** The `.pth`/`.pt`/`.bin` files are pickles, and the code calls `torch.load` without
   `weights_only=True` (torch 2.4 default is unsafe). **Mitigation:** `torch.load` is forced to `weights_only=True`
   in the runner, so non-tensor payloads are refused (fail closed). Whisper uses `.safetensors` (no code).
2. **Third-party code execution (medium).** Seed-VC's Python runs with this machine's privileges. **Mitigation:** network
   namespace with no interfaces; scrubbed environment; tmpfs over `/home/user`, `/mnt`, and `/root` credential and
   config directories; post-run write audit.
3. **Supply chain (low to medium).** Files are pinned to exact revisions and verified by hash before use; a mismatch aborts.
4. **Reference audio (privacy).** Read locally only. A 25 s excerpt is copied into the run directory; the original file is
   never modified and nothing is uploaded (the conversion has no network).
5. **Disclosures of earlier steps (outside this review).** OpenVoice was installed from GitHub (its setup ran) and tested
   locally. The SpeechBrain ECAPA verifier (`speechbrain/spkrec-ecapa-voxceleb`, Apache-2.0) was downloaded and run
   locally, loading its checkpoint with torch's default (pickle) loader. No audio left the machine in either case.

## 5. Files read and written by the proposed run

- **Read:** `RUN/models/*` (verified copies), `RUN/in/ref.wav` (25 s reference excerpt), `RUN/in/<job>.wav` (narration to convert),
  `RUN/in/jobs.json`, Seed-VC code directory, the venv's packages.
- **Written:** `RUN/out/*.wav`, `RUN/home/*` (scratch caches); Python bytecode caches in the Seed-VC directory.
- **Never written:** the original reference `brand/voice/(256k)_vocals_mixed.m4a`, approved masters, the repository.
- `RUN` is a fresh directory in the session scratchpad; results are copied into the project by a separate step afterwards.

## 6. Execution protocol (after approval)

1. `fetch_models.py RUN`: network on, downloads only the table above, verifies hashes, aborts on mismatch. No Seed-VC code runs.
2. `run_isolated.sh RUN SEEDVC_DIR VENV`: network off, scrubbed environment, hidden directories, `weights_only` loads, write audit.
3. Verification: speaker similarity (ECAPA), per-line ASR intelligibility, timing, clipping and loudness, before any render.

## 7. Exact download URLs (pinned to full commit hashes)

Weights (4):
- https://huggingface.co/Plachta/Seed-VC/resolve/257283f9f41585055e8f858fba4fd044e5caed6e/DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth
- https://huggingface.co/openai/whisper-small/resolve/973afd24965f72e36ca33b3055d56a652f456b4d/model.safetensors
- https://huggingface.co/funasr/campplus/resolve/e4b6ede7ce16997aff4ae69fbca1f0175e2afede/campplus_cn_common.bin
- https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x/resolve/633ff708ed5b74903e86ff1298cf4a98e921c513/bigvgan_generator.pt

Configuration (4, small text):
- https://huggingface.co/Plachta/Seed-VC/resolve/257283f9f41585055e8f858fba4fd044e5caed6e/config_dit_mel_seed_uvit_whisper_small_wavenet.yml
- https://huggingface.co/openai/whisper-small/resolve/973afd24965f72e36ca33b3055d56a652f456b4d/config.json
- https://huggingface.co/openai/whisper-small/resolve/973afd24965f72e36ca33b3055d56a652f456b4d/preprocessor_config.json
- https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x/resolve/633ff708ed5b74903e86ff1298cf4a98e921c513/config.json

Total: 8 files, about 1.88 GB. (An earlier approval prompt said "5 files"; the correct count is 4 weight files
plus 4 small configuration files.) The CAM++ file is already present from the Space download and matches
the published SHA-256.

## 8. Installed dependency versions (isolated venv)

torch 2.4.1+cpu, torchaudio 2.4.1+cpu, transformers 4.46.3, tokenizers 0.20.3, safetensors 0.8.0,
huggingface-hub 0.25.2, librosa 0.10.2, numba 0.68.1, numpy 1.26.4, scipy 1.13.1, soundfile 0.14.0,
pydub 0.25.1, pyyaml 6.0.4, munch 4.0.0, einops 0.8.0. Also present from earlier, not used by Seed-VC:
speechbrain 1.0.2, myshell-openvoice 0.0.0 (GitHub).

## 9. Sandbox verification (harmless probe; no Seed-VC code executed)

`build/seedvc/sandbox_probe.py` was run through `run_isolated.sh` with the identical restrictions:

| Check | Result |
|---|---|
| DNS/TCP to huggingface.co:443 | blocked (gaierror) |
| TCP to 1.1.1.1:443 (raw IP) | blocked (OSError) |
| list /home/user | hidden (empty) |
| list /mnt/user-data | blocked (not found) |
| list /root/.ccr, /root/.claude, /root/.cache | hidden (empty) |
| read /root/.claude.json, /root/.gitconfig | masked (empty) |
| secret-like environment variables | none |
| booby-trapped pickle via guarded torch.load | refused (UnpicklingError) |

Write audit: only `/tmp/claude-code.log`, the agent's own session log written from outside the sandbox
(the audit is time-based and lists every write in the window).

## 10. Limits of this review

- The static scan covered the code paths inference reaches, plus a repository-wide grep. It is not a proof that the
  code is benign; the sandbox is the control for anything the scan could miss.
- The PyPI dependencies (torch, transformers, librosa and others) are mainstream packages and were not audited line by line.
- Inside the sandbox, Seed-VC can still read non-hidden system and scratch files (for example the OS and the venv), but it
  cannot send anything anywhere (no network) and cannot read the hidden directories.
