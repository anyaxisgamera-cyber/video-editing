#!/usr/bin/env bash
# Phase B launcher: run convert_offline.py with NO network, a scrubbed environment, and
# sensitive directories hidden. Usage: build/seedvc/run_isolated.sh RUN_DIR SEEDVC_DIR VENV_DIR [SCRIPT]
# SCRIPT defaults to convert_offline.py; sandbox_probe.py tests the restrictions themselves.
#
#  * unshare -rnm : new user + network + mount namespace. The network namespace has no
#    interfaces except a down loopback, so no outbound (or inbound) traffic is possible.
#  * env -i       : no inherited variables (no API keys, tokens, proxy settings).
#  * tmpfs mounts hide /home/user (projects, repos), /mnt (user data), and /root
#    credential/config directories; only RUN_DIR, the Seed-VC code and the venv are used.
#  * A write audit lists every file modified outside RUN_DIR during the run.
set -euo pipefail
RUN="$(realpath "$1")"; SEED="$(realpath "$2")"; VENV="$(realpath "$3")"
SCRIPT="$(realpath "${4:-$(dirname "$(realpath "$0")")/convert_offline.py}")"
mkdir -p "$RUN/out" "$RUN/home" "$RUN/bin"
# /home/user is hidden inside the sandbox, so the script runs from a copy in RUN/bin
cp "$SCRIPT" "$RUN/bin/"; SCRIPT="$RUN/bin/$(basename "$SCRIPT")"
MARK="$RUN/.start-marker"; : > "$MARK"

env -i PATH="$VENV/bin:/usr/bin:/bin" HOME="$RUN/home" SEEDVC_DIR="$SEED" \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME="$RUN/home/hf" \
    NUMBA_CACHE_DIR="$RUN/home/numba" MPLCONFIGDIR="$RUN/home/mpl" OMP_NUM_THREADS=4 \
  unshare -rnm bash -c '
    set -e
    for d in /home/user /mnt /root/.ccr /root/.claude /root/.aws /root/.ssh /root/.config /root/.cache /root/.gradle /root/.npm; do
      [ -d "$d" ] && mount -t tmpfs -o size=1m,mode=0700 none "$d"
    done
    [ -f /root/.claude.json ] && mount --bind /dev/null /root/.claude.json
    [ -f /root/.gitconfig ] && mount --bind /dev/null /root/.gitconfig
    if ip link 2>/dev/null | grep -q "state UP"; then echo "network unexpectedly up; aborting"; exit 3; fi
    python -I "$0" "$1"
  ' "$SCRIPT" "$RUN"

echo "--- files modified outside RUN_DIR during the run (expect only Python bytecode caches in the Seed-VC dir):"
find / -xdev -newer "$MARK" -type f \
  -not -path "$RUN/*" -not -path "/proc/*" -not -path "/sys/*" -not -path "/dev/*" \
  -not -path "/tmp/claude-0/*/tasks/*" 2>/dev/null | head -50
