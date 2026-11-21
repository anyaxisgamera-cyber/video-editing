"""Harmless probe run with the exact restrictions of run_isolated.sh (no Seed-VC code)."""
import functools, os, pickle, socket, sys, tempfile
import torch
results = {}
for host, port in [("huggingface.co", 443), ("1.1.1.1", 443)]:
    try:
        socket.create_connection((host, port), timeout=3); results[f"net {host}"] = "REACHABLE (FAIL)"
    except Exception as e:
        results[f"net {host}"] = f"blocked ({type(e).__name__})"
for path in ["/home/user", "/mnt/user-data", "/root/.ccr", "/root/.claude", "/root/.cache"]:
    try:
        entries = os.listdir(path); results[f"list {path}"] = "hidden (empty)" if not entries else f"VISIBLE {len(entries)} entries (FAIL)"
    except Exception as e:
        results[f"list {path}"] = f"blocked ({type(e).__name__})"
for f in ["/root/.claude.json", "/root/.gitconfig"]:
    try:
        results[f"read {f}"] = "empty (masked)" if os.path.getsize(f) == 0 else "READABLE (FAIL)"
    except Exception as e:
        results[f"read {f}"] = f"blocked ({type(e).__name__})"
secretish = [k for k in os.environ if any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASS", "PROXY"))]
results["env secret-like vars"] = "none" if not secretish else f"PRESENT {secretish} (FAIL)"
class Trap:
    def __reduce__(self):
        return (print, ("TRAP EXECUTED (FAIL)",))
p = os.path.join(sys.argv[1], "trap.pt")
with open(p, "wb") as fh:
    pickle.dump({"net": Trap()}, fh)
torch.load = functools.partial(torch.load, weights_only=True)
try:
    torch.load(p); results["booby-trapped pickle"] = "LOADED (FAIL)"
except Exception as e:
    results["booby-trapped pickle"] = f"refused ({type(e).__name__})"
os.remove(p)
for k, v in results.items():
    print(f"{k:28s} {v}")
print("PROBE RESULT:", "ALL BLOCKED" if not any("FAIL" in v for v in results.values()) else "SOME CHECKS FAILED")
