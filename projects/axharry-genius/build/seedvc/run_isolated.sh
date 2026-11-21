#!/usr/bin/env bash
# Phase B launcher. The SAME code path runs the real conversion, the preflight, and the self-tests:
#   build/seedvc/run_isolated.sh RUN_DIR SEEDVC_DIR VENV_DIR [SCRIPT] [SCRIPT_ARGS...]
#   SCRIPT defaults to convert_offline.py.
#
#  * unshare -rnm : new user + network + mount namespace; no network interfaces except a down loopback.
#  * env -i       : no inherited variables (no API keys, tokens or proxy settings); only the listed ones.
#  * TORCH_FORCE_WEIGHTS_ONLY_LOAD=1 : torch itself refuses unsafe (non-weights) unpickling.
#  * tmpfs mounts hide /home/user (projects, originals, approved masters), /mnt (user data) and
#    /root credential/config/upload directories; Python runs with -I -B (isolated, no bytecode writes).
#  * guard.py (imported first by the script) enforces hashes, safe loading, and an audit-hook tripwire.
#  * Afterwards: protected originals are re-hashed and every file written outside RUN_DIR is listed;
#    any change fails the run. Extra protected paths: one per line in RUN_DIR/protected.txt.
set -uo pipefail
RUN="$(realpath "$1")"; SEED="$(realpath "$2")"; VENV="$(realpath "$3")"; shift 3
HERE="$(dirname "$(realpath "$0")")"
PROJECT="$(realpath "$HERE/../..")"
SCRIPT="$(basename "${1:-convert_offline.py}")"; [ $# -gt 0 ] && shift
mkdir -p "$RUN/out" "$RUN/home/tmp" "$RUN/bin"
chmod -R u+w "$RUN/bin" 2>/dev/null; cp "$HERE"/*.py "$RUN/bin/"   # /home/user is hidden inside the sandbox
chmod -R a-w "$RUN/bin"
[ -d "$RUN/models" ] && chmod -R a-w "$RUN/models"

PROTECTED=("$PROJECT/brand/voice/(256k)_vocals_mixed.m4a" "$PROJECT/output/AXHARRY_ENGLISH.mp4" "$PROJECT/output/AXHARRY_TELUGU.mp4")
if [ -f "$RUN/protected.txt" ]; then while IFS= read -r p; do [ -n "$p" ] && PROTECTED+=("$p"); done < "$RUN/protected.txt"; fi
hash_protected() { for f in "${PROTECTED[@]}"; do [ -f "$f" ] && sha256sum "$f"; done; }
BEFORE="$(hash_protected)"
MARK="$RUN/.start-marker"; : > "$MARK"

env -i PATH="$VENV/bin:/usr/bin:/bin" HOME="$RUN/home" TMPDIR="$RUN/home/tmp" SEEDVC_DIR="$SEED" \
    TORCH_FORCE_WEIGHTS_ONLY_LOAD=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HOME="$RUN/home/hf" NUMBA_CACHE_DIR="$RUN/home/numba" MPLCONFIGDIR="$RUN/home/mpl" OMP_NUM_THREADS=4 \
  unshare -rnm bash -c '
    set -e
    for d in /home/user /mnt /root/.ccr /root/.claude /root/.aws /root/.ssh /root/.config /root/.cache /root/.gradle /root/.npm; do
      [ -d "$d" ] && mount -t tmpfs -o size=1m,mode=0700 none "$d"
    done
    [ -f /root/.claude.json ] && mount --bind /dev/null /root/.claude.json
    [ -f /root/.gitconfig ] && mount --bind /dev/null /root/.gitconfig
    cd "$0" && exec python -I -B "$0/$1" "${@:2}"
  ' "$RUN/bin" "$SCRIPT" "$RUN" "$@"
STATUS=$?

AFTER="$(hash_protected)"
if [ "$BEFORE" != "$AFTER" ]; then echo "AUDIT FAIL: a protected original changed"; STATUS=90; else
  echo "audit: protected originals unchanged ($(echo "$BEFORE" | grep -c .) files re-hashed)"; fi
CHANGED="$(find / -xdev -newer "$MARK" -type f -not -path "$RUN/*" -not -path "/proc/*" -not -path "/sys/*" \
  -not -path "/dev/*" -not -path "/tmp/claude-code.log" -not -path "/tmp/claude-code-*.diag.log" -not -path "/tmp/claude-0/*/tasks/*" 2>/dev/null | head -50)"
if [ -n "$CHANGED" ]; then echo "AUDIT FAIL: files written outside RUN_DIR:"; echo "$CHANGED"; STATUS=91; else
  echo "audit: no files written outside RUN_DIR (agent harness logs /tmp/claude-code.log and /tmp/claude-code-*.diag.log excluded; verified written by the agent outside the sandbox)"; fi
exit $STATUS
