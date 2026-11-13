#!/usr/bin/env bash
# One driver for every bare-metal node (docs/handoff/NODE_PLAN.md). Every node runs the same stages in the same order
# with the same harness, assets and sample counts, and logs how long each step took.
#
#   bash tools/calibrate/node_run.sh spec   <label> <scratch_dir> [<scratch_dir> ...]   # Part A (~15 min)
#   bash tools/calibrate/node_run.sh setup  <label>                                     # assets, guest image (~30-60 min)
#   bash tools/calibrate/node_run.sh quick  <label> <ssd_scratch> [<hdd_scratch>]       # 10% smoke pass (~20-60 min)
#   bash tools/calibrate/node_run.sh full   <label> <ssd_scratch> [<hdd_scratch>]       # Part B (~3-8 h)
#   bash tools/calibrate/node_run.sh ingest <label> [hdd]                               # Part D (~15 min)
#
# Part C (reboots) is never run by this script: it needs the human's approval in the session (AGENTS.md rule 14).
# Writes calibration/specs/<label>/timeline.csv (stage, suite, start, end, seconds, exit) and env-<stage>.txt.
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
cd "$REPO"
STAGE=${1:?usage: node_run.sh <spec|setup|quick|full|ingest> <label> ...}
LABEL=${2:?label required (NODE_PLAN.md §3)}
shift 2
[[ "$LABEL" =~ ^node[0-9]{2}-[a-z0-9.-]+$ ]] || { echo "label must look like node03-i5-8250u-8g-ssd" >&2; exit 2; }
OUT="calibration/specs/$LABEL"
ASSETS=${VOSS_ASSETS:-$HOME/voss-calib/assets}
mkdir -p "$OUT"
[ -f "$OUT/timeline.csv" ] || echo "stage,suite,start_utc,end_utc,seconds,exit" > "$OUT/timeline.csv"

lock_ok() {  # the harness must be byte-identical on every node (NODE_PLAN.md §4)
  local want have
  want=$(cat calibration/HARNESS.lock)
  have=$(git rev-parse HEAD:tools/calibrate)
  if [ "$want" != "$have" ]; then
    echo "STOP: tools/calibrate tree $have differs from calibration/HARNESS.lock $want." >&2
    echo "Every node must run the same harness. Tell the human; do not edit the lock." >&2
    exit 4
  fi
  git diff --quiet HEAD -- tools/calibrate || { echo "STOP: local edits in tools/calibrate" >&2; exit 4; }
}

env_snapshot() {  # what can make timings differ between nodes
  {
    echo "stage=$1 utc=$(date -u +%FT%TZ) commit=$(git rev-parse HEAD)"
    echo "virt=$(systemd-detect-virt 2>/dev/null || true)"
    echo "governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/a)"
    echo "intel_no_turbo=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo n/a)"
    echo "boost=$(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo n/a)"
    echo "on_mains=$(cat /sys/class/power_supply/A*/online 2>/dev/null | head -1 || echo n/a)"
    echo "loadavg=$(cut -d' ' -f1-3 /proc/loadavg) nproc=$(nproc)"
    echo "thermal_msgs=$(dmesg 2>/dev/null | grep -ci 'throttl' || echo n/a)"
  } > "$OUT/env-$1.txt"
  cat "$OUT/env-$1.txt"
}

timed() {  # timed <stage> <suite> <command...>
  local stage=$1 suite=$2 t0 t1 rc
  shift 2
  t0=$(date -u +%s)
  set +e
  "$@" 2>&1 | tee -a "$OUT/log-$stage.txt"
  rc=${PIPESTATUS[0]}
  set -e
  t1=$(date -u +%s)
  echo "$stage,$suite,$(date -u -d @"$t0" +%FT%TZ),$(date -u -d @"$t1" +%FT%TZ),$((t1 - t0)),$rc" >> "$OUT/timeline.csv"
  return "$rc"
}

suite_args() {  # common arguments: pinned assets and scratch directories
  local ssd=$1 hdd=${2:-}
  ARGS=(--sudo --set "firecracker=$ASSETS/firecracker" --set "kernel=$ASSETS/vmlinux"
        --set "rootfs=$ASSETS/voss-guest.ext4" --set "sebs_rootfs=$ASSETS/voss-guest.ext4" --set "ssd_dir=$ssd")
  [ -z "$hdd" ] || ARGS+=(--set "hdd_dir=$hdd")
}

measure() {  # measure <quick|full> <ssd> [hdd]: every suite of Part B, one at a time, in the fixed order
  local stage=$1
  shift
  suite_args "$@"
  local extra=()
  [ "$stage" = quick ] && extra=(--quick)
  env_snapshot "$stage"
  local failed=0
  for s in caps disk tpm attest_local tls keys fc_boot fc_snapshot sebs; do
    timed "$stage" "$s" uv run python -m tools.calibrate.run --suite "$s" "${ARGS[@]}" "${extra[@]}" || failed=1
  done
  env_snapshot "$stage-end"
  [ "$failed" = 0 ] || { echo "one or more suites failed: see $OUT/log-$stage.txt (NODE_PLAN.md §6)" >&2; exit 5; }
}

lock_ok
case "$STAGE" in
  spec)
    [ "$#" -ge 1 ] || { echo "spec needs at least one scratch directory" >&2; exit 2; }
    env_snapshot spec
    timed spec spec bash tools/calibrate/spec.sh "$LABEL" "$@"
    timed spec caps uv run python -m tools.calibrate.run --suite caps
    set +e
    uv run python -m tools.calibrate.nodes check "$LABEL" --branches | tee "$OUT/class.yaml"
    rc=${PIPESTATUS[0]}
    set -e
    [ "$rc" = 0 ] || { echo "STOP: duplicate node (NODE_PLAN.md §3). Push the spec, tell the human." >&2; exit 3; }
    uv run python -m tools.calibrate.nodes table --branches > "$OUT/nodes-at-spec-time.md"
    echo "Part A done. Push branch calib/$LABEL now (NODE_PLAN.md §5 step 4)."
    ;;
  setup)
    env_snapshot setup
    timed setup fetch_assets sh tools/calibrate/guest/fetch_assets.sh "$ASSETS"
    timed setup build_rootfs sudo env DOCKER="sudo docker" SUDO="sudo" sh tools/calibrate/guest/build_rootfs.sh "$ASSETS"
    timed setup preflight bash tools/emu/preflight.sh
    (cd "$ASSETS" && sha256sum firecracker jailer vmlinux voss-guest.ext4) > "$OUT/assets.sha256"
    cat "$ASSETS/versions.txt" >> "$OUT/assets.sha256"
    ;;
  quick | full)
    measure "$STAGE" "$@"
    ;;
  ingest)
    tier=${1:-}
    name=$LABEL
    if [ "$tier" = hdd ]; then
      name=${LABEL}_hdd
      timed ingest ingest_hdd uv run python -m tools.calibrate.ingest --raw calibration/raw --label "$name" --tier hdd
    else
      timed ingest ingest uv run python -m tools.calibrate.ingest --raw calibration/raw --label "$name"
    fi
    timed ingest check_bundle uv run python -m tools.calibrate.check_bundle "configs/calibration/measured/$name" \
      --spec "$OUT"
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
