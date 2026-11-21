"""Fail-closed runtime guard for the isolated Seed-VC process. Install BEFORE importing Seed-VC.

Layers (any violation prints GUARD VIOLATION and terminates the process with os._exit):
  1. Every approved file is checked for exact size and full SHA-256 at start   -> exit 10
  2. torch.load and torch.serialization.load are replaced: only the 3 approved pickle files may be loaded; each
     is re-hashed immediately before loading; weights_only=True is forced       -> exit 24 / 25
     (in addition, the launcher sets TORCH_FORCE_WEIGHTS_ONLY_LOAD=1 so torch's own
     loader refuses unsafe loads even if called directly)
  3. sys.addaudithook (cannot be removed once installed) terminates on:
       - any standard-library unpickling (pickle.find_class)                      -> exit 22
       - any socket / URL / HTTP activity                                         -> exit 20
       - any subprocess, os.system, exec, spawn, fork                             -> exit 21
       - any file write/create/delete/rename/chmod outside RUN/out and RUN/home   -> exit 23
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from approved import APPROVED, local_path

_STATE: dict = {}


def _die(code: int, msg: str) -> None:
    try:
        sys.stderr.write(f"GUARD VIOLATION [{code}]: {msg}\n")
        sys.stderr.flush()
    finally:
        os._exit(code)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(path, roots) -> bool:
    if isinstance(path, int):
        return True  # operations on already-open descriptors were checked at open time
    try:
        p = os.path.realpath(os.fsdecode(path))
    except Exception:
        return False
    return any(p == r or p.startswith(r + os.sep) for r in roots)


_NET = ("socket.", "urllib.", "http.", "ftplib.", "smtplib.", "telnetlib.", "imaplib.", "poplib.", "nntplib.")
_PROC = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
         "pty.spawn", "os.startfile")
_FS = ("os.remove", "os.unlink", "os.rename", "os.replace", "os.rmdir", "os.mkdir", "os.chmod", "os.chown",
       "os.symlink", "os.link", "os.truncate", "shutil.rmtree", "shutil.move", "shutil.copyfile", "shutil.copytree",
       "os.utime")


def _hook(event: str, args: tuple) -> None:
    writable = _STATE.get("writable")
    if writable is None:
        return
    if event == "pickle.find_class":
        _die(22, f"standard unpickling attempted: {args}")
    if event.startswith(_NET):
        _die(20, f"network activity: {event} {args!r:.200}")
    if event.startswith(_PROC):
        _die(21, f"process execution: {event} {args!r:.200}")
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        wants_write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if wants_write and not _inside(path, writable):
            _die(23, f"write outside allowed dirs: {path!r} mode={mode} flags={flags}")
    elif event.startswith(_FS):
        for a in args[:2]:
            if isinstance(a, (str, bytes, os.PathLike)) and not _inside(a, writable):
                _die(23, f"filesystem change outside allowed dirs: {event} {a!r}")


def install(run_dir, table=APPROVED, verify_files: bool = True) -> dict:
    run = Path(run_dir).resolve()
    models = run / "models"
    approved_pickles = {}
    if verify_files:
        for repo, rev, name, size, sha, _blob, is_pickle in table:
            p = local_path(models, repo, name)
            if not p.is_file():
                _die(10, f"approved file missing: {p}")
            if p.stat().st_size != size:
                _die(10, f"size mismatch {p}: {p.stat().st_size} != {size}")
            got = _sha256(p)
            if got != sha:
                _die(10, f"sha256 mismatch {p}: {got} != {sha}")
            print(f"guard: verified {repo}/{name} size={size} sha256={got}", flush=True)
            if is_pickle:
                approved_pickles[os.path.realpath(p)] = sha

    import torch  # imported here so the torch.load replacement precedes any Seed-VC import

    if os.environ.get("TORCH_FORCE_WEIGHTS_ONLY_LOAD") != "1":
        _die(25, "TORCH_FORCE_WEIGHTS_ONLY_LOAD is not set to 1")
    original_load = torch.load

    def guarded_load(f, *a, **kw):
        path = os.path.realpath(os.fsdecode(f)) if isinstance(f, (str, bytes, os.PathLike)) else None
        if path is None or path not in approved_pickles:
            _die(24, f"torch.load of unapproved source: {f!r}")
        if _sha256(Path(path)) != approved_pickles[path]:
            _die(24, f"file changed since verification: {path}")
        kw["weights_only"] = True
        kw.pop("pickle_module", None)
        try:
            obj = original_load(path, *a, **kw)
        except Exception as e:  # refusal by the weights-only unpickler = unsafe content
            _die(25, f"weights-only load refused {path}: {type(e).__name__}: {e}")
        print(f"guard: torch.load OK (weights_only=True, sha256 re-verified) {path}", flush=True)
        return obj

    torch.load = guarded_load
    torch.serialization.load = guarded_load  # direct calls to torch's loader take the same guarded path
    _STATE["writable"] = [str(run / "out"), str(run / "home")]
    _STATE["approved_pickles"] = approved_pickles
    sys.addaudithook(_hook)
    print(f"guard: installed (writable: {_STATE['writable']}; approved pickles: {len(approved_pickles)})", flush=True)
    return _STATE
