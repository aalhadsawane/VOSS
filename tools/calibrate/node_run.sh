#!/usr/bin/env bash
# One driver for every bare-metal node (docs/handoff/NODE_PLAN.md). Every node runs the same stages in the same order
# with the same harness, assets and sample counts, and logs how long each step took.
#
#   bash tools/calibrate/node_run.sh spec   <label> <tier>=<dir> ...   # Part A (~15 min)
#   bash tools/calibrate/node_run.sh setup  <label>                    # assets, guest image (~30-60 min)
#   bash tools/calibrate/node_run.sh quick  <label> <tier>=<dir> ...   # 10% smoke pass (~20-60 min)
#   bash tools/calibrate/node_run.sh full   <label> <tier>=<dir> ...   # Part B (~3-8 h, +30-60 min per extra disk)
#   bash tools/calibrate/node_run.sh ingest <label> <tier> ...         # Part D: one bundle per disk tier (~15 min)
#
# <tier> is nvme, sata or hdd: one scratch directory on EVERY disk class the node has (NODE_PLAN.md §2). quick and full
# refuse to start if a disk class in the node's spec has no scratch directory.
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
    echo "thermal_msgs=$(dmesg 2>/dev/null | grep -ci 'throttl' || true)"
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

parse_tiers() {  # <tier>=<dir> ... → TIERS (names) and DIRS (paths), in the order given
  TIERS=() DIRS=()
  local kv t d
  for kv in "$@"; do
    t=${kv%%=*} d=${kv#*=}
    [[ "$kv" == *=* && "$t" =~ ^(nvme|sata|hdd)$ && -n "$d" ]] || { echo "bad scratch '$kv': use nvme=/path, sata=/path or hdd=/path" >&2; exit 2; }
    TIERS+=("$t") DIRS+=("$d")
  done
  [ "${#TIERS[@]}" -ge 1 ] || { echo "give one <tier>=<dir> per disk class" >&2; exit 2; }
}

all_classes_covered() {  # every disk class in the spec has a scratch directory (NODE_PLAN.md §2)
  local want c
  want=$(uv run python -m tools.calibrate.nodes classes "$LABEL")
  for c in $want; do
    [[ " ${TIERS[*]} " == *" $c "* ]] || { echo "STOP: the node has a $c disk but no $c=<dir> was given" >&2; exit 2; }
  done
}

suite_args() {  # common arguments: pinned assets and one scratch directory per disk tier
  ARGS=(--set "firecracker=$ASSETS/firecracker" --set "kernel=$ASSETS/vmlinux"
        --set "rootfs=$ASSETS/voss-guest.ext4" --set "sebs_rootfs=$ASSETS/voss-guest.ext4")
  local i
  for i in "${!TIERS[@]}"; do ARGS+=(--set "${TIERS[$i]}_dir=${DIRS[$i]}"); done
}

measure() {  # measure <quick|full> <tier>=<dir> ...: every suite of Part B, one at a time, in the fixed order
  local stage=$1
  shift
  parse_tiers "$@"
  all_classes_covered
  suite_args
  sudo -v || { echo "sudo needed (run 'sudo -v' first, with the human's approval)" >&2; exit 2; }
  ( while sleep 60; do sudo -n true || exit; done ) &  # keep the sudo timestamp fresh for the hours of Part B
  local keep=$!
  trap 'kill $keep 2>/dev/null || true' RETURN
  local extra=()
  [ "$stage" = quick ] && extra=(--quick)
  env_snapshot "$stage"
  local failed=0
  for s in caps disk tpm attest_local tls keys fc_boot fc_snapshot sebs; do
    # as root (cold page cache, loop devices), with the project's own interpreter so the harness is the locked one
    timed "$stage" "$s" sudo -n "$REPO/.venv/bin/python" -m tools.calibrate.run --suite "$s" --out calibration/raw \
      "${ARGS[@]}" "${extra[@]}" || failed=1
  done
  sudo -n chown -R "$(id -u):$(id -g)" calibration/raw
  env_snapshot "$stage-end"
  [ "$failed" = 0 ] || { echo "one or more suites failed: see $OUT/log-$stage.txt (NODE_PLAN.md §6)" >&2; exit 5; }
}

lock_ok
[ -x "$REPO/.venv/bin/python" ] || uv sync --frozen
case "$STAGE" in
  spec)
    parse_tiers "$@"
    env_snapshot spec
    timed spec spec bash tools/calibrate/spec.sh "$LABEL" "${DIRS[@]}"
    timed spec caps uv run python -m tools.calibrate.run --suite caps --out calibration/raw
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
    [ "$#" -ge 1 ] || { echo "ingest needs the tiers measured: nvme, sata and/or hdd" >&2; exit 2; }
    for tier in "$@"; do  # one bundle per disk tier: configs/calibration/measured/<label>_<tier>
      [[ "$tier" =~ ^(nvme|sata|hdd)$ ]] || { echo "bad tier $tier" >&2; exit 2; }
      timed ingest "ingest_$tier" uv run python -m tools.calibrate.ingest --raw calibration/raw \
        --label "${LABEL}_$tier" --tier "$tier"
      timed ingest "check_$tier" uv run python -m tools.calibrate.check_bundle \
        "configs/calibration/measured/${LABEL}_$tier" --spec "$OUT"
    done
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
