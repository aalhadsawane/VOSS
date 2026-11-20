#!/usr/bin/env bash
# Generate calibration/specs/<host_label>/SPEC.md and spec.yaml (doc 10 §2; CALIBRATION_DATA_CONTRACT.md §1).
# Usage: bash tools/calibrate/spec.sh <host_label> <scratch_dir> ...
# Read-only. Every value comes from a probe of this machine (tools/calibrate/spec.py); serials and MAC addresses are
# hashed, and MAC, UUID, WWN, private IP addresses, the hostname and user names are scrubbed (tools/calibrate/scrub.py).
set -Eeuo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
LABEL=${1:?usage: spec.sh <host_label> <scratch_dir> ...}
shift || true
[ "$#" -ge 1 ] || { echo "spec.sh: name the scratch directory of every disk class" >&2; exit 2; }

VIRT=$(systemd-detect-virt 2>/dev/null || true)
[ -n "$VIRT" ] || VIRT="none"
if [ "$VIRT" != "none" ]; then
  echo "ERROR: systemd-detect-virt returned '$VIRT' (expected 'none' for bare-metal calibration)." >&2
  exit 1
fi

PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
cd "$REPO"
"$PY" -m tools.calibrate.spec "$LABEL" "$REPO/calibration/specs/$LABEL" "$@"
