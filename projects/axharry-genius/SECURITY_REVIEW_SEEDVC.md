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

## 11. Addendum: final confirmations (supersedes sections 3, 7 and 9 where they differ)

### 11.1 All 8 files: exact URL, size and full SHA-256

Single source of truth: `build/seedvc/approved.py` (used by both the downloader and the runtime guard).

| # | URL | Bytes | SHA-256 | Pickle? |
|---|---|---:|---|---|
| 1 | https://huggingface.co/Plachta/Seed-VC/resolve/257283f9f41585055e8f858fba4fd044e5caed6e/DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth | 440,312,082 | 8ec8841b20bb46df9f7e8e570a6946a4b87b940133c7f0e778487ff33841f720 | yes |
| 2 | https://huggingface.co/Plachta/Seed-VC/resolve/257283f9f41585055e8f858fba4fd044e5caed6e/config_dit_mel_seed_uvit_whisper_small_wavenet.yml | 2,289 | 27a91ac41bdb41d0b6951c63642d791b4a70d60b9fc5550eb645f9ddcb3c94da | no (YAML) |
| 3 | https://huggingface.co/openai/whisper-small/resolve/973afd24965f72e36ca33b3055d56a652f456b4d/model.safetensors | 966,995,080 | 1d7734884874f1a1513ed9aa760a4f8e97aaa02fd6d93a3a85d27b2ae9ca596b | no (safetensors) |
| 4 | https://huggingface.co/openai/whisper-small/resolve/973afd24965f72e36ca33b3055d56a652f456b4d/config.json | 1,967 | e6a2b489da1b5aed65a8eb8d1e7466fa867ad5643a8bc138ba708bd56b2875c4 | no (JSON) |
| 5 | https://huggingface.co/openai/whisper-small/resolve/973afd24965f72e36ca33b3055d56a652f456b4d/preprocessor_config.json | 184,990 | 9b5cd03a36fbb8a627c64d98a5b5b126ead95a77720723944487311f0110b666 | no (JSON) |
| 6 | https://huggingface.co/funasr/campplus/resolve/e4b6ede7ce16997aff4ae69fbca1f0175e2afede/campplus_cn_common.bin | 28,036,335 | 3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8 | yes |
| 7 | https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x/resolve/633ff708ed5b74903e86ff1298cf4a98e921c513/bigvgan_generator.pt | 449,228,171 | e95ba25972d3de0628d99cd156e9315a9c018899bf739988959ebe3544080ced | yes |
| 8 | https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x/resolve/633ff708ed5b74903e86ff1298cf4a98e921c513/config.json | 1,405 | 88a1f47acf747db0b21e97a389d838566147f7a5464583ff5c8d819d870f03ee | no (JSON) |

Total 1,884,762,319 bytes. SHA-256 values for files 1, 3, 6 and 7 are Hugging Face's published Git LFS hashes. For the four
text files (2, 4, 5, 8), Hugging Face publishes only Git blob SHA-1 values, so they were fetched into an isolated quarantine
folder: each matched its full blob SHA-1 at the pinned commit (fddb287b1ac6039bbfe71448a64c79a837a1ecd8,
113bb3efe3a7396f2ea629eef12637bd8085238d, c2048dfa9fd94a052e62e908d2c4dfb18534b4d2, 635bd8975629bd6d4b51c409986944a281cfe7be),
parsed as plain data with no executable YAML tags, and the SHA-256 values above were computed from them. No model weights
were downloaded.

Correction: there are **three** pickle-format files (1, 6, 7), not two. Whisper weights are safetensors.

### 11.2 Model-loading audit (every deserialization path)

| Call site | Loads | Reached? | Control |
|---|---|---|---|
| `modules/commons.py:421` `load_checkpoint` | file 1 | yes | guarded `torch.load` |
| `modules/bigvgan/bigvgan.py:481` `_from_pretrained` | file 7 | yes (local directory branch) | guarded `torch.load` |
| `convert_offline.py` (replaces wrapper line 131) | file 6 | yes | guarded `torch.load` |
| `transformers` WhisperModel / feature extractor | files 3, 4, 5 | yes | safetensors and JSON; `local_files_only`, `use_safetensors=True`; no `.bin` present to fall back to |
| `modules/commons.py:220` `load_F0_models` | F0 models | no (F0 pipeline excluded) | would hit the guard |
| `modules/bigvgan/utils.py:64` `load_checkpoint` | training checkpoints | no | would hit the guard |
| `modules/bigvgan/meldataset.py:308` `np.load` | training data | no | `allow_pickle` is False by default |

Three independent layers, all fail-closed:
1. `TORCH_FORCE_WEIGHTS_ONLY_LOAD=1` (set by the launcher): torch's own loader forces weights-only mode even when a caller
   passes `weights_only=False` (verified in torch 2.4.1 `serialization.py`, around line 1031).
2. `guard.py` replaces both `torch.load` and `torch.serialization.load`: only the 3 approved pickle paths are accepted, each is
   re-hashed immediately before loading, and weights-only mode is forced. Any other path terminates the process (exit 24);
   any refusal terminates it (exit 25).
3. An audit hook (cannot be uninstalled) terminates on any standard-library unpickling (exit 22), network activity (20),
   process execution (21), or file write, create, delete or rename outside `RUN/out` and `RUN/home` (23).
   At start, the guard verifies the size and SHA-256 of all 8 files (exit 10 on any mismatch or missing file).

### 11.3 Guard self-test inside the real sandbox (`guard_selftest.py`, synthetic tensors only): 15/15 PASS

Approved checkpoint loads (with `weights_only` forced) · approved-hash malicious pickle refused (25) · unapproved file (24) ·
attempt to modify an approved model (23) · direct `torch.serialization.load` bypass (25) · `pickle.loads` (22) · TCP (20) ·
DNS (20) · subprocess (21) · `os.system` (21) · write to /tmp (23) · write into models (23) · delete outside (23) ·
write into RUN/out allowed · `/home/user` empty. The booby-trap payload never executed. Launcher audit: protected originals
unchanged (6 re-hashed); no writes outside RUN.

During testing the first run caught one gap, which is now fixed: a direct `torch.serialization.load` was refused by torch
(layer 1) but raised a catchable error instead of terminating. It is now routed through the guard (exit 25).

### 11.4 The actual conversion program under the actual sandbox

`run_isolated.sh` has one code path; its default script is `convert_offline.py`. Running the real script in `--preflight`
mode (guard installed; Seed-VC code never imported) reported all of the following as PASS: `TORCH_FORCE_WEIGHTS_ONLY_LOAD`,
`HF_HUB_OFFLINE`, no secret-like environment variables, `/home/user` hidden, `/root/.ccr` hidden, `/root/.claude` hidden,
`/mnt/user-data` absent, only the loopback interface, **0 IPv4 routes**, no IPv6 addresses. A deliberate connection to
huggingface.co was then **terminated by the guard (exit 20)**. In normal mode with no models present, the real converter
**failed closed at hash verification (exit 10)**.

Two issues were found and fixed while preparing this proof: the guard was not importable under `python -I` (it failed
closed); and a loopback check read the host's `/sys` view, so the check now uses this namespace's `/proc/net` routing table.

### 11.5 Write-audit exclusions (verified)

`/tmp/claude-code.log` and `/tmp/claude-code-*.diag.log` are the agent harness's own logs. Verified: the content is Claude
Code diagnostic JSON (`cc_version 2.1.330`), and it kept growing while no sandbox process existed. No other exclusions.
