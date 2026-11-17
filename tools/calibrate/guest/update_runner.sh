#!/bin/sh
# Copy this harness's guest/fnrunner.py into guest images built by an older harness (NODE_PLAN.md §5a, topup), so a
# node measured on lock 1de5d147 gets the vsock listener and the input-generation timer without rebuilding its images:
# nothing else in the images changes (same Python, packages, functions and model weights as the images it measured
# with). Usage (as root): update_runner.sh <assets_dir>. Prints the SHA-256 of each image before and after.
set -eu
ASSETS=$(realpath "${1:?usage: update_runner.sh <assets_dir>}")
HERE=$(cd "$(dirname "$0")" && pwd)
MNT=$(mktemp -d)
trap 'umount "$MNT" 2>/dev/null || true; rmdir "$MNT"' EXIT
for img in voss-guest.ext4 voss-guest-ml.ext4; do
  [ -f "$ASSETS/$img" ] || { echo "missing $ASSETS/$img (run node_run.sh setup)" >&2; exit 2; }
  echo "before $(sha256sum "$ASSETS/$img")"
  mount -o loop "$ASSETS/$img" "$MNT"
  if cmp -s "$HERE/fnrunner.py" "$MNT/voss/fnrunner.py"; then
    echo "$img: fnrunner.py already current"
  else
    cp "$HERE/fnrunner.py" "$MNT/voss/fnrunner.py"
  fi
  umount "$MNT"
  sha256sum "$ASSETS/$img" | tee "$ASSETS/$img.sha256"
done
