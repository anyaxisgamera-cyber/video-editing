"""Single source of truth for the approved Seed-VC files (used by fetch_models.py and guard.py).

Every entry is pinned to a full commit hash and verified by exact size and full SHA-256.
LFS SHA-256 values are those published by Hugging Face; SHA-256 values of the four small
text files were computed from files whose Git blob SHA-1 matched the pinned commit.
"""

APPROVED = [
    # repo, full revision, filename, size_bytes, sha256, git_blob_sha1, is_pickle
    ("Plachta/Seed-VC", "257283f9f41585055e8f858fba4fd044e5caed6e",
     "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth", 440312082,
     "8ec8841b20bb46df9f7e8e570a6946a4b87b940133c7f0e778487ff33841f720",
     "fdb25c6ea09024806dbd2d572ea1810498d1475a", True),
    ("Plachta/Seed-VC", "257283f9f41585055e8f858fba4fd044e5caed6e",
     "config_dit_mel_seed_uvit_whisper_small_wavenet.yml", 2289,
     "27a91ac41bdb41d0b6951c63642d791b4a70d60b9fc5550eb645f9ddcb3c94da",
     "fddb287b1ac6039bbfe71448a64c79a837a1ecd8", False),
    ("openai/whisper-small", "973afd24965f72e36ca33b3055d56a652f456b4d",
     "model.safetensors", 966995080,
     "1d7734884874f1a1513ed9aa760a4f8e97aaa02fd6d93a3a85d27b2ae9ca596b",
     "b737d9fc4345d96e8f69b440ab742a269bf7e734", False),
    ("openai/whisper-small", "973afd24965f72e36ca33b3055d56a652f456b4d",
     "config.json", 1967,
     "e6a2b489da1b5aed65a8eb8d1e7466fa867ad5643a8bc138ba708bd56b2875c4",
     "113bb3efe3a7396f2ea629eef12637bd8085238d", False),
    ("openai/whisper-small", "973afd24965f72e36ca33b3055d56a652f456b4d",
     "preprocessor_config.json", 184990,
     "9b5cd03a36fbb8a627c64d98a5b5b126ead95a77720723944487311f0110b666",
     "c2048dfa9fd94a052e62e908d2c4dfb18534b4d2", False),
    ("funasr/campplus", "e4b6ede7ce16997aff4ae69fbca1f0175e2afede",
     "campplus_cn_common.bin", 28036335,
     "3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8",
     "ccc729ec7f373f8d2351be91c9efdc7b21c00384", True),
    ("nvidia/bigvgan_v2_22khz_80band_256x", "633ff708ed5b74903e86ff1298cf4a98e921c513",
     "bigvgan_generator.pt", 449228171,
     "e95ba25972d3de0628d99cd156e9315a9c018899bf739988959ebe3544080ced",
     "8d615250f07a44490d74033318fd330be67f4a86", True),
    ("nvidia/bigvgan_v2_22khz_80band_256x", "633ff708ed5b74903e86ff1298cf4a98e921c513",
     "config.json", 1405,
     "88a1f47acf747db0b21e97a389d838566147f7a5464583ff5c8d819d870f03ee",
     "635bd8975629bd6d4b51c409986944a281cfe7be", False),
]


def local_path(models_dir, repo: str, name: str):
    return models_dir / repo.replace("/", "__") / name


def url(repo: str, rev: str, name: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/{rev}/{name}"
