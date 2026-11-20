#!/usr/bin/env bash
# One driver for every bare-metal node (docs/handoff/NODE_PLAN.md). Every node runs the same stages in the same order
# with the same harness, assets and sample counts, and logs how long each step took.
#
#   bash tools/calibrate/node_run.sh spec   <label> <tier>=<dir> ...   # Part A (~15 min)
#   bash tools/calibrate/node_run.sh setup  <label>                    # assets, guest images (~40-75 min)
#   bash tools/calibrate/node_run.sh quick  <label> <tier>=<dir> ...   # 10% smoke pass (~20-60 min; never ingested)
#   bash tools/calibrate/node_run.sh full   <label> <tier>=<dir> ...   # Part B (~3-8 h, +30-60 min per extra disk)
#   bash tools/calibrate/node_run.sh ingest <label> <tier> ...         # Part D: one bundle per disk tier (~15 min)
#   bash tools/calibrate/node_run.sh ml     <label> <tier>=<dir> ...   # only for nodes measured before the ML image
#                                         existed: builds it and measures image-recognition alone (~1-1.5 h)
#   bash tools/calibrate/node_run.sh inputs <label> <tier>=<dir> ...   # only for nodes whose topup ran on 82e4f794
#   bash tools/calibrate/node_run.sh topup  <label> <tier>=<dir> ...   # only for nodes measured on lock 1de5d147:
#                                         the probes added since (NODE_PLAN.md §5a), nothing else (~1-2 h)
#
# <tier> is nvme, sata or hdd: one scratch directory on EVERY disk class the node has (NODE_PLAN.md §2). The measuring
# stages (quick, full, ml, topup, inputs) refuse to start if a disk class in the node's spec has no scratch directory, if the
# CPU governor is not 'performance', or if the 1-minute load average does not fall below 0.5 within 30 minutes
# (NODE_PLAN.md §4 rule 4; exit 6).
#
# Part C (reboots) is never run by this script: it needs the human's approval in the session (AGENTS.md rule 14). The
# tme suite runs here only in the phase the firmware is already in, and only when TME is enabled; the other phase
# needs a BIOS change, by the human.
# Writes calibration/specs/<label>/timeline.csv (stage, suite, start, end, seconds, exit), env-<stage>.txt and
# fingerprint.txt (the raw-log folder of this node under calibration/raw, which ingest reads).
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
cd "$REPO"
STAGE=${1:?usage: node_run.sh <spec|setup|quick|full|ml|topup|inputs|ingest> <label> ...}
LABEL=${2:?label required (NODE_PLAN.md §3)}
shift 2
[[ "$LABEL" =~ ^node[0-9]{2}-[a-z0-9.-]+$ ]] || { echo "label must look like node03-i5-8250u-8g-ssd" >&2; exit 2; }
OUT="calibration/specs/$LABEL"
ASSETS=${VOSS_ASSETS:-$HOME/voss-calib/assets}
PY="$REPO/.venv/bin/python"
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
    echo "governor=$(sort -u /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | tr '\n' ' ' || echo n/a)"
    echo "intel_no_turbo=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo n/a)"
    echo "boost=$(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo n/a)"
    echo "on_mains=$(cat /sys/class/power_supply/A*/online 2>/dev/null | head -1 || echo n/a)"
    echo "loadavg=$(cut -d' ' -f1-3 /proc/loadavg) nproc=$(nproc)"
    echo "thermal_msgs=$(dmesg 2>/dev/null | grep -ci 'throttl' || true)"
  } > "$OUT/env-$1.txt"
  cat "$OUT/env-$1.txt"
}

other_users_check() {  # NODE_PLAN.md §4 rule 7: no process of another login user (node01: another user's daemon)
  local me allow procs units
  me=${SUDO_USER:-$(id -un)}
  allow=" $me ${VOSS_ALLOW_USERS:-} "  # users the human approved in this session; recorded in env-<stage>.txt
  procs=$(ps -eo uid=,user=,pid=,comm= | awk -v allow="$allow" '$1 >= 1000 && $1 < 60000 && index(allow, " " $2 " ") == 0')
  units=$(systemctl list-units --type=service --state=active --no-legend 'user@*.service' 2>/dev/null \
    | awk '{print $1}' | grep -v -E "^user@($(id -u "$me"))\.service$" || true)
  if [ -n "$procs" ] || [ -n "$units" ]; then
    echo "STOP: processes or service managers of other login users are running (NODE_PLAN.md §4 rule 7):" >&2
    [ -n "$procs" ] && printf '%s\n' "$procs" | head -40 >&2
    [ -n "$units" ] && printf '%s\n' "$units" >&2
    echo "Ask the human to stop them (or to approve a user with VOSS_ALLOW_USERS=\"name ...\")." >&2
    exit 6
  fi
}

quiet_check() {  # NODE_PLAN.md §4 rule 4: every measuring stage runs on a quiet machine with the performance governor
  local gov waited=0
  gov=$(sort -u /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | tr '\n' ' ')
  if [ "$gov" != "performance " ]; then
    echo "STOP: CPU governor is '${gov:-unknown}', not performance. Ask the human to set it (NODE_PLAN.md §4)." >&2
    exit 6
  fi
  other_users_check
  while awk '{ exit !($1 >= 0.5) }' /proc/loadavg; do  # e.g. the writeback of a guest image build just before
    if [ "$waited" -ge 1800 ]; then
      echo "STOP: load average $(cut -d' ' -f1-3 /proc/loadavg) did not fall below 0.5 in 30 min." >&2
      echo "Ask the human to stop the background services or other work (NODE_PLAN.md §4)." >&2
      exit 6
    fi
    [ $((waited % 300)) = 0 ] && echo "waiting for load average < 0.5 (now $(cut -d' ' -f1 /proc/loadavg))"
    sleep 30
    waited=$((waited + 30))
  done
}

timed() {  # timed <stage> <suite> <command...>
  local stage=$1 suite=$2 t0 t1 rc
  shift 2
  t0=$(date -u +%s)
  set +e
  # logs are committed: MAC, UUID, WWN, private IP addresses, hostname and user names are scrubbed (scrub.py)
  "$@" 2>&1 | python3 -u -m tools.calibrate.scrub | tee -a "$OUT/log-$stage.txt"
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
        --set "rootfs=$ASSETS/voss-guest.ext4" --set "sebs_rootfs=$ASSETS/voss-guest.ext4"
        --set "sebs_ml_rootfs=$ASSETS/voss-guest-ml.ext4")
  local i
  for i in "${!TIERS[@]}"; do ARGS+=(--set "${TIERS[$i]}_dir=${DIRS[$i]}"); done
}

plan_for() {  # the suites of a measuring stage, in the fixed order; "<suite> key=value ..." (phase= is --phase)
  case "$1" in
    quick | full) PLAN=(caps disk tpm attest_local tls keys fc_boot fc_snapshot fc_dispatch sebs fn_inputs fc_touched) ;;
    ml) PLAN=("sebs functions=image-recognition") ;;
    # what lock 1de5d147 did not measure (NODE_PLAN.md §5a); every other probe of that lock stays valid
    topup) PLAN=("tpm only=unseal" "disk only=hash" "keys only=kbs_check" fc_dispatch fn_inputs fc_touched) ;;
    # nodes whose topup ran on lock 82e4f794: fn_inputs recorded nothing there (fc.MARK missed VOSS_GEN lines)
    inputs) PLAN=(fn_inputs) ;;
  esac
  [ "$1" = ml ] || [ "$1" = inputs ] && return 0
  TME=$(sudo -n "$PY" -m tools.calibrate.suites.tme state || echo unknown)
  if [ "$TME" = on ]; then
    PLAN+=("tme phase=on")  # the firmware's current phase: no BIOS change; the off phase is the human's (§5a)
  else
    echo "TME is $TME in the firmware: tme suite not run (tme_cpu_factor, tme_mem_factor stay missing)"
  fi
}

measure() {  # measure <quick|full|ml|topup> <tier>=<dir> ...: the stage's suites, one at a time, in the fixed order
  local stage=$1
  shift
  parse_tiers "$@"
  all_classes_covered
  suite_args
  sudo -v || { echo "sudo needed (run 'sudo -v' first, with the human's approval)" >&2; exit 2; }
  ( while sleep 60; do sudo -n true || exit; done ) &  # keep the sudo timestamp fresh for the hours of Part B
  local keep=$!
  trap "kill $keep 2>/dev/null || true" RETURN EXIT
  quiet_check
  local scale=() item s rest kv opts failed=0
  [ "$stage" = quick ] && scale=(--quick)
  plan_for "$stage"
  env_snapshot "$stage"
  echo "tme_state=${TME:-not checked}" >> "$OUT/env-$stage.txt"
  echo "allowed_other_users=${VOSS_ALLOW_USERS:-none}" >> "$OUT/env-$stage.txt"
  for item in "${PLAN[@]}"; do
    read -r s rest <<< "$item"
    opts=()
    for kv in $rest; do
      case "$kv" in phase=*) opts+=(--phase "${kv#phase=}") ;; *) opts+=(--set "$kv") ;; esac
    done
    # as root (cold page cache, loop devices), with the project's own interpreter so the harness is the locked one
    timed "$stage" "$s" sudo -n "$PY" -m tools.calibrate.run --suite "$s" --out calibration/raw \
      "${ARGS[@]}" "${opts[@]}" "${scale[@]}" || failed=1
  done
  sudo -n chown -R "$(id -u):$(id -g)" calibration/raw
  sudo -n "$PY" -m tools.calibrate.run --fingerprint > "$OUT/fingerprint.txt"  # same environment as the suites
  env_snapshot "$stage-end"
  [ "$failed" = 0 ] || { echo "one or more suites failed: see $OUT/log-$stage.txt (NODE_PLAN.md §6)" >&2; exit 5; }
}

lock_ok
[ -x "$PY" ] || uv sync --frozen
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
    timed setup build_rootfs_ml sudo env DOCKER="sudo docker" SUDO="sudo" sh tools/calibrate/guest/build_rootfs.sh \
      "$ASSETS" --with-ml
    timed setup preflight bash tools/emu/preflight.sh
    (cd "$ASSETS" && sha256sum firecracker jailer vmlinux voss-guest.ext4 voss-guest-ml.ext4) > "$OUT/assets.sha256"
    cat "$ASSETS/versions.txt" >> "$OUT/assets.sha256"
    ;;
  quick | full)
    measure "$STAGE" "$@"
    ;;
  ml)  # nodes measured with harness 570e04bc (no ML image): image-recognition alone, then ingest again
    if [ ! -f "$ASSETS/voss-guest-ml.ext4" ]; then
      timed ml build_rootfs_ml sudo env DOCKER="sudo docker" SUDO="sudo" sh tools/calibrate/guest/build_rootfs.sh \
        "$ASSETS" --with-ml
    fi
    (cd "$ASSETS" && sha256sum voss-guest-ml.ext4) >> "$OUT/assets.sha256"
    measure ml "$@"  # waits for the image build's load to settle (quiet_check)
    ;;
  topup)  # nodes measured with harness 1de5d147: the new guest runner in the same images, then the new probes only
    timed topup update_runner sudo sh tools/calibrate/guest/update_runner.sh "$ASSETS"
    (cd "$ASSETS" && sha256sum voss-guest.ext4 voss-guest-ml.ext4) | sed 's/^/topup /' >> "$OUT/assets.sha256"
    measure topup "$@"
    ;;
  inputs)  # nodes whose topup ran on lock 82e4f794: input generation times only (NODE_PLAN.md §5a)
    measure inputs "$@"
    ;;
  ingest)
    [ "$#" -ge 1 ] || { echo "ingest needs the tiers measured: nvme, sata and/or hdd" >&2; exit 2; }
    # only this node's raw logs: calibration/raw also holds other hosts' folders (node01's report)
    FP=$(cat "$OUT/fingerprint.txt" 2>/dev/null || sudo -n "$PY" -m tools.calibrate.run --fingerprint)
    [ -d "calibration/raw/$FP" ] || { echo "STOP: no raw logs under calibration/raw/$FP" >&2; exit 2; }
    echo "ingesting calibration/raw/$FP"
    rc=0
    for tier in "$@"; do  # one bundle per disk tier: configs/calibration/measured/<label>_<tier>
      [[ "$tier" =~ ^(nvme|sata|hdd)$ ]] || { echo "bad tier $tier" >&2; exit 2; }
      timed ingest "ingest_$tier" uv run python -m tools.calibrate.ingest --raw calibration/raw --host "$FP" \
        --label "${LABEL}_$tier" --tier "$tier" || { rc=1; continue; }
      timed ingest "check_$tier" uv run python -m tools.calibrate.check_bundle \
        "configs/calibration/measured/${LABEL}_$tier" --spec "$OUT" || rc=1
    done
    [ "$rc" = 0 ] || echo "ingest or check_bundle reported errors: each goes into the report (NODE_PLAN.md §6)" >&2
    exit "$rc"
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
