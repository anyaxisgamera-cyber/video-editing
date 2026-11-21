"""Self-test of guard.py inside the real sandbox (run via run_isolated.sh RUN SEED VENV guard_selftest.py).

Uses tiny synthetic tensors created here; no Seed-VC code or models are involved. Each case runs
in a fresh child process with the real guard installed, and must produce the expected outcome.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import subprocess
import sys
from pathlib import Path

import torch

RUN = Path(sys.argv[1]).resolve()
T = RUN / "home" / "tmp" / "selftest"
(T / "out").mkdir(parents=True, exist_ok=True)
(T / "home").mkdir(parents=True, exist_ok=True)
M = T / "models" / "test__repo"
M.mkdir(parents=True, exist_ok=True)


class Trap:
    def __reduce__(self):
        return (os.system, ("echo TRAP-EXECUTED",))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


good = M / "good.pt"
torch.save({"net": {"w": torch.zeros(3)}}, good)
trap = M / "trap.pt"
with open(trap, "wb") as fh:
    pickle.dump({"net": Trap()}, fh)
unlisted = M / "unlisted.pt"
torch.save({"w": torch.ones(1)}, unlisted)

table = [
    ("test/repo", "r", "good.pt", good.stat().st_size, sha(good), "", True),
    ("test/repo", "r", "trap.pt", trap.stat().st_size, sha(trap), "", True),  # "approved" yet malicious
]
PRE = (f"import sys,os,torch; sys.path.insert(0,{str(RUN / 'bin')!r}); import guard; "
       f"guard.install({str(T)!r}, table={table!r})\n")

CASES = [
    ("approved checkpoint loads (weights_only forced)", f"o=torch.load({str(good)!r}, weights_only=False); print('loaded', list(o['net']))", 0),
    ("approved-hash but malicious pickle, caller asks weights_only=False", f"torch.load({str(trap)!r}, weights_only=False)", 25),
    ("unapproved file via torch.load", f"torch.load({str(unlisted)!r})", 24),
    ("attempt to modify an approved model file", f"open({str(good)!r},'r+b').close()", 23),
    ("direct torch.serialization.load bypassing wrapper", f"torch.serialization.load({str(trap)!r}, weights_only=False)", 25),
    ("plain pickle.loads of malicious bytes", f"import pickle; pickle.loads(open({str(trap)!r},'rb').read())", 22),
    ("network connection", "import socket; socket.create_connection(('1.1.1.1', 443), timeout=2)", 20),
    ("DNS lookup", "import socket; socket.getaddrinfo('huggingface.co', 443)", 20),
    ("subprocess", "import subprocess; subprocess.run(['true'])", 21),
    ("os.system", "os.system('true')", 21),
    ("write outside allowed dirs (/tmp)", "open('/tmp/guard-test-escape.txt','w').write('x')", 23),
    ("write into models dir", f"open({str(M / 'x.txt')!r},'w').write('x')", 23),
    ("delete outside allowed dirs", f"os.remove({str(unlisted)!r})", 23),
    ("write into RUN/out is allowed", f"open({str(T / 'out' / 'ok.txt')!r},'w').write('ok'); print('wrote ok')", 0),
    ("read hidden original reference audio", "print(os.listdir('/home/user'))", 0),
]

rows, ok_all = [], True
for name, code, expected in CASES:
    p = subprocess.run([sys.executable, "-I", "-B", "-c", PRE + code], capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip().splitlines()
    detail = next((line for line in out if "GUARD VIOLATION" in line or "loaded" in line or "wrote ok" in line
                   or line.startswith("[") or "Error" in line), out[-1] if out else "")
    passed = p.returncode == expected and "TRAP-EXECUTED" not in (p.stdout + p.stderr)
    ok_all &= passed
    rows.append((passed, name, expected, p.returncode, detail[:110]))

for passed, name, expected, rc, detail in rows:
    print(f"{'PASS' if passed else 'FAIL'}  exit={rc:<3} expected={expected:<3} {name}\n        {detail}")
print("SELFTEST:", "ALL PASS" if ok_all else "FAILURES PRESENT")
print("escape file exists after test:", os.path.exists("/tmp/guard-test-escape.txt"))
