"""Phase A (network ON, no Seed-VC code runs): download ONLY the approved files at pinned
revisions into RUN_DIR/models and verify them.

Usage: python build/seedvc/fetch_models.py RUN_DIR

Only huggingface_hub.hf_hub_download is used. Large weights are verified against the
SHA-256 published in each repository's Git LFS metadata; small text files against the
Git blob SHA-1 of the pinned revision. Any mismatch deletes the file and aborts.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
from huggingface_hub import hf_hub_download  # noqa: E402

# (repo, revision, filename, kind, expected) -- kind: sha256 (LFS) or blob (git blob sha1 prefix)
APPROVED = [
    ("Plachta/Seed-VC", "257283f9f415", "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth", "sha256",
     "8ec8841b20bb46df9f7e8e570a6946a4b87b940133c7f0e778487ff33841f720"),
    ("Plachta/Seed-VC", "257283f9f415", "config_dit_mel_seed_uvit_whisper_small_wavenet.yml", "blob", "fddb287b1ac6"),
    ("openai/whisper-small", "973afd24965f", "model.safetensors", "sha256",
     "1d7734884874f1a1513ed9aa760a4f8e97aaa02fd6d93a3a85d27b2ae9ca596b"),
    ("openai/whisper-small", "973afd24965f", "config.json", "blob", "113bb3efe3a7"),
    ("openai/whisper-small", "973afd24965f", "preprocessor_config.json", "blob", "c2048dfa9fd9"),
    ("funasr/campplus", "e4b6ede7ce16", "campplus_cn_common.bin", "sha256",
     "3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8"),
    ("nvidia/bigvgan_v2_22khz_80band_256x", "633ff708ed5b", "bigvgan_generator.pt", "sha256",
     "e95ba25972d3de0628d99cd156e9315a9c018899bf739988959ebe3544080ced"),
    ("nvidia/bigvgan_v2_22khz_80band_256x", "633ff708ed5b", "config.json", "blob", "635bd8975629"),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def blob(p: Path) -> str:
    b = p.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def main() -> None:
    run = Path(sys.argv[1]).resolve()
    out = run / "models"
    for repo, rev, name, kind, expected in APPROVED:
        dest = out / repo.replace("/", "__") / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            src = hf_hub_download(repo_id=repo, filename=name, revision=rev, cache_dir=str(run / "hf-download-cache"))
            shutil.copyfile(src, dest)
        got = sha256(dest) if kind == "sha256" else blob(dest)
        ok = got == expected if kind == "sha256" else got.startswith(expected)
        print(f"{'OK  ' if ok else 'FAIL'} {repo}@{rev} {name} {kind}={got[:16]}")
        if not ok:
            dest.unlink()
            sys.exit(f"Hash mismatch for {repo}/{name}; aborting.")
    shutil.rmtree(run / "hf-download-cache", ignore_errors=True)
    print("all approved files present and verified")


if __name__ == "__main__":
    main()
