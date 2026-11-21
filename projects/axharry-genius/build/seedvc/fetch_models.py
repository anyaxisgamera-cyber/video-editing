"""Phase A (network ON, no Seed-VC code runs): download ONLY the 8 approved files at pinned
full revisions into RUN_DIR/models, verify exact size and full SHA-256, then make them read-only.

Usage: python build/seedvc/fetch_models.py RUN_DIR

Only huggingface_hub.hf_hub_download is used. Any size or hash mismatch deletes the file and
aborts with a non-zero exit code; nothing else is downloaded.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
from approved import APPROVED, local_path, url  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    run = Path(sys.argv[1]).resolve()
    models = run / "models"
    cache = run / "hf-download-cache"
    for repo, rev, name, size, sha, _blob, _pickle in APPROVED:
        dest = local_path(models, repo, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            print(f"download {url(repo, rev, name)}", flush=True)
            src = hf_hub_download(repo_id=repo, filename=name, revision=rev, cache_dir=str(cache))
            shutil.copyfile(src, dest)
        got_size, got = dest.stat().st_size, sha256(dest)
        ok = got_size == size and got == sha
        print(f"{'OK  ' if ok else 'FAIL'} {repo}/{name} size={got_size} sha256={got}", flush=True)
        if not ok:
            dest.unlink()
            shutil.rmtree(cache, ignore_errors=True)
            sys.exit(f"Size/hash mismatch for {repo}/{name} (expected size={size} sha256={sha}); aborting.")
        dest.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    shutil.rmtree(cache, ignore_errors=True)
    print("all 8 approved files present, verified, and read-only")


if __name__ == "__main__":
    main()
