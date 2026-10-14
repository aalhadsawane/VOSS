#!/usr/bin/env bash
# VOSS calibration on a local Linux machine (doc 10, ROADMAP P9). Read README.md next to this file first.
#
#   voss-calib.sh check                 look only: is this machine ready? (changes nothing)
#   voss-calib.sh setup [--with-ml] [--yes]   install packages, download Firecracker, build the guest image
#   voss-calib.sh smoke                 every suite with 10% of the repetitions (shake-down, then fix problems)
#   voss-calib.sh full                  every suite, full repetitions
#   voss-calib.sh run SUITE...          only the named suites (e.g. after a failure)
#   voss-calib.sh summary               status of every suite's newest run
#   voss-calib.sh pack                  one .tar.gz with the results (user and host names removed)
#   voss-calib.sh cleanup [--all]       remove scratch files (--all: also the downloaded assets)
#
# It never reboots, never changes BIOS/UEFI settings, partitions, boot entries or other users' files. It writes only
# under $VOSS_WORK (default ~/voss-calib-work), except for installing packages in `setup` and for the kernel's
# page-cache drop and the temporary loop/dm devices of the disk suite (both undone by the suite itself).
set -Eeuo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
WORK=${VOSS_WORK:-$HOME/voss-calib-work}
ASSETS=$WORK/assets
RAW=$WORK/raw
SCRATCH=$WORK/scratch
DRY=${VOSS_DRY:-0}           # 1: pass --dry-run to the harness, no sudo, no checks (tests of this script)
NO_SUDO=${NO_SUDO:-0}        # 1: never use sudo (cold-cache and dm-crypt/dm-verity measurements are then skipped)
NEED_FREE_MB=15000           # peak scratch use: guest image copies, snapshots, the 3 GB dm-crypt image
NEED_FREE_ML_MB=25000        # ... with the PyTorch image
NEED_DOCKER_MB=6000          # docker keeps the base image and the build layers under /var/lib/docker (system disk)
NEED_DOCKER_ML_MB=14000

say() { printf '%s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

confirm() { # confirm "question": yes only on an explicit y (or VOSS_YES=1)
  [ "${VOSS_YES:-0}" = 1 ] && return 0
  local a
  read -r -p "$1 [y/N] " a </dev/tty || return 1
  [ "$a" = y ] || [ "$a" = Y ]
}

# --- guards ----------------------------------------------------------------------------------------------------
case "$WORK" in
  /*) ;;
  *) die "VOSS_WORK must be an absolute path (got '$WORK')" ;;
esac
case "$WORK" in
  / | "$HOME" | "$HOME"/) die "VOSS_WORK must be a dedicated directory, not '$WORK'" ;;
esac
case "$(basename "$WORK")" in
  *voss*) ;;
  *) die "the last part of VOSS_WORK must contain 'voss' (a safety check before any rm), got '$WORK'" ;;
esac
SUDO=sudo
if [ "$(id -u)" -eq 0 ]; then
  [ "${VOSS_ALLOW_ROOT:-0}" = 1 ] || die "run as a normal user; the script calls sudo itself where it is needed"
  SUDO=""
fi
PRIV=()
if [ "$DRY" != 1 ] && [ "$NO_SUDO" != 1 ] && [ -n "$SUDO" ]; then PRIV=(sudo); fi

nearest_existing() { local p=$1; while [ ! -e "$p" ] && [ "$p" != / ]; do p=$(dirname "$p"); done; echo "$p"; }
free_mb() { df -Pm "$(nearest_existing "$1")" | awk 'NR==2 {print $4}'; }
mem_total_mb() { awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo; }
mem_avail_mb() { awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo; }
governor() { cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown; }

on_battery() { # true when a battery exists and no mains supply is online
  local d type online has_bat=0
  for d in /sys/class/power_supply/*; do
    [ -r "$d/type" ] || continue
    type=$(<"$d/type")
    if [ "$type" = Battery ]; then has_bat=1; continue; fi
    online=$(cat "$d/online" 2>/dev/null || echo 0)
    [ "$online" = 1 ] && return 1
  done
  [ "$has_bat" = 1 ]
}

tier_of() { # ssd | hdd | unknown, for the disk that holds the given path
  local src rota
  src=$(findmnt -no SOURCE -T "$1" 2>/dev/null | head -n1) || true
  src=${src%%\[*}
  [ -b "$src" ] || { echo unknown; return; }
  rota=$(lsblk -sno ROTA "$src" 2>/dev/null | tail -n1 | tr -d ' ') || true
  case "$rota" in 0) echo ssd ;; 1) echo hdd ;; *) echo unknown ;; esac
}

python_ok() { python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; }

# --- check -----------------------------------------------------------------------------------------------------
row() { printf '%-5s %-26s %s\n' "$1" "$2" "$3"; }

cmd_check() {
  local fails=0 need=$NEED_FREE_MB t tool note
  [ -f "$ASSETS/with-ml" ] && need=$NEED_FREE_ML_MB
  say "VOSS calibration check (changes nothing). Work directory: $WORK"; say
  if [ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ]; then row OK "Linux x86_64" "$(uname -sr)"
  else row FAIL "Linux x86_64" "this harness needs x86-64 Linux (found $(uname -sm))"; fails=$((fails + 1)); fi
  if have python3 && python_ok; then row OK "python3 >= 3.10" "$(python3 --version 2>&1)"
  else row FAIL "python3 >= 3.10" "install Python 3.10 or newer (found: $(python3 --version 2>&1 || echo none))"; fails=$((fails + 1)); fi
  t=$(free_mb "$WORK")
  if [ "$t" -ge "$need" ]; then row OK "free disk" "${t} MB free (need ${need})"
  else row FAIL "free disk" "${t} MB free, need ${need}: free space or set VOSS_WORK to a bigger disk"; fails=$((fails + 1)); fi
  t=$(free_mb /var/lib/docker)
  need=$NEED_DOCKER_MB; [ -f "$ASSETS/with-ml" ] && need=$NEED_DOCKER_ML_MB
  if [ "$t" -ge "$need" ]; then row OK "docker storage" "${t} MB free for /var/lib/docker (need ${need})"
  else row FAIL "docker storage" "${t} MB free for /var/lib/docker (need ${need}): free space on the system disk"; fails=$((fails + 1)); fi
  t=$(mem_total_mb)
  if [ "$t" -ge 3500 ]; then row OK "memory" "${t} MB total, $(mem_avail_mb) MB available"
  else row WARN "memory" "${t} MB: the larger guest sizes are skipped automatically"; fi
  if [ -e /dev/kvm ]; then row OK "/dev/kvm" "present (Firecracker/QEMU suites can run)"
  elif grep -qE '\b(vmx|svm)\b' /proc/cpuinfo; then
    row WARN "/dev/kvm" "missing but the CPU supports it: enable VT-x/AMD-V in the BIOS, or: sudo modprobe kvm_intel (or kvm_amd)"
  else row WARN "/dev/kvm" "no hardware virtualisation: fc_boot, fc_snapshot, qemu_vm and sebs will be skipped"; fi
  if [ -e /dev/tpmrm0 ] || [ -e /dev/tpm0 ]; then
    t=$(cat /sys/class/tpm/tpm0/tpm_version_major 2>/dev/null || echo "?")
    if [ "$t" = 2 ]; then row OK "TPM" "TPM 2.0 present"; else row WARN "TPM" "version '$t': tpm and attest_local need TPM 2.0 and will be skipped"; fi
  else row WARN "TPM" "none found: tpm and attest_local will be skipped"; fi
  for t in "fio:disk speed tests" "tpm2_getcap:tpm, attest_local (package tpm2-tools)" "openssl:attest_local, tls" \
    "cryptsetup:disk dm-crypt timings" "veritysetup:disk dm-verity timings (package cryptsetup)" "losetup:disk dm-crypt timings" \
    "qemu-system-x86_64:qemu_vm" "docker:building the guest image (setup only)" "curl:downloading Firecracker (setup only)" \
    "mkfs.ext4:building the guest image (setup only)" "lsblk:disk detection"; do
    tool=${t%%:*}; note=${t#*:}
    if have "$tool"; then row OK "$tool" "found"; else row WARN "$tool" "missing: needed for $note (setup installs it)"; fi
  done
  if [ "$NO_SUDO" = 1 ]; then row OK "sudo" "not used (NO_SUDO=1)"
  elif sudo -n true 2>/dev/null; then row OK "sudo" "works without a password right now"
  elif have sudo; then row OK "sudo" "present; you will be asked for your password once"
  else row WARN "sudo" "missing: setup cannot install packages; cold-cache and dm-crypt timings are skipped"; fi
  if on_battery; then row WARN "power" "on battery: plug in the charger before a run"; else row OK "power" "mains power"; fi
  t=$(governor)
  if [ "$t" = performance ] || [ "$t" = unknown ]; then row OK "cpu governor" "$t"
  else row OK "cpu governor" "$t (optional for steadier numbers: sudo cpupower frequency-set -g performance)"; fi
  t=$(tier_of "$(nearest_existing "$WORK")")
  row OK "work disk type" "${VOSS_TIER:-$t}${VOSS_TIER:+ (set by VOSS_TIER)}"
  [ "$t" = unknown ] && [ -z "${VOSS_TIER:-}" ] && warn "cannot tell SSD from HDD; set VOSS_TIER=ssd or VOSS_TIER=hdd before running"
  say
  if [ "$fails" -eq 0 ]; then say "No blocking problems. Next: $0 setup"; else say "$fails blocking problem(s) above."; fi
}

# --- setup -----------------------------------------------------------------------------------------------------
packages_for() { # package-manager name -> package list
  case "$1" in
    apt-get) echo "python3 fio tpm2-tools openssl cryptsetup qemu-system-x86 e2fsprogs curl tar util-linux docker.io" ;;
    dnf) echo "python3 fio tpm2-tools openssl cryptsetup qemu-system-x86-core e2fsprogs curl tar util-linux moby-engine" ;;
    pacman) echo "python fio tpm2-tools openssl cryptsetup qemu-system-x86 e2fsprogs curl tar util-linux docker" ;;
    *) echo "" ;;
  esac
}

cmd_setup() {
  local ml="" mgr pkgs need=$NEED_FREE_MB
  for a in "$@"; do
    case "$a" in
      --with-ml) ml=--with-ml; need=$NEED_FREE_ML_MB ;;
      --yes) export VOSS_YES=1 ;;
      *) die "setup: unknown option '$a'" ;;
    esac
  done
  python_ok || die "python3 >= 3.10 is required (found: $(python3 --version 2>&1 || echo none))"
  [ "$(free_mb "$WORK")" -ge "$need" ] || die "need ${need} MB free under $WORK (have $(free_mb "$WORK"))"
  local dneed=$NEED_DOCKER_MB
  [ -z "$ml" ] || dneed=$NEED_DOCKER_ML_MB
  [ "$(free_mb /var/lib/docker)" -ge "$dneed" ] || die "need ${dneed} MB free for docker under /var/lib/docker (have $(free_mb /var/lib/docker))"
  mkdir -p "$WORK" "$ASSETS"
  for mgr in apt-get dnf pacman; do have "$mgr" && break || mgr=none; done
  pkgs=$(packages_for "$mgr")
  if [ "$mgr" = none ]; then
    warn "no apt-get, dnf or pacman found: install these yourself (names vary by distribution):"
    say "  python3>=3.10 fio tpm2-tools openssl cryptsetup qemu-system-x86 e2fsprogs curl tar util-linux docker"
  else
    say "This will install packages with $mgr (already installed ones are left alone):"
    case "$mgr" in
      apt-get) say "  sudo apt-get update && sudo apt-get install -y $pkgs" ;;
      dnf) say "  sudo dnf install -y $pkgs" ;;
      pacman) say "  sudo pacman -S --needed --noconfirm $pkgs" ;;
    esac
    confirm "Install now?" || die "stopped before installing anything"
    # shellcheck disable=SC2086  # the package list is meant to be split into words
    case "$mgr" in
      apt-get) $SUDO apt-get update && $SUDO apt-get install -y $pkgs ;;
      dnf) $SUDO dnf install -y $pkgs ;;
      pacman) $SUDO pacman -S --needed --noconfirm $pkgs ;;
    esac
  fi
  if ! $SUDO docker info >/dev/null 2>&1; then
    say "Starting the docker service (only for this boot; it is not enabled permanently)."
    $SUDO systemctl start docker || die "could not start docker; start it yourself and rerun setup"
  fi
  say "Downloading Firecracker and its kernel into $ASSETS (pinned versions, checksums in assets.sha256)"
  sh "$REPO/tools/calibrate/guest/fetch_assets.sh" "$ASSETS"
  say "Building the guest image with docker ${ml:+(with PyTorch; this takes a while)}"
  $SUDO sh "$REPO/tools/calibrate/guest/build_rootfs.sh" "$ASSETS" ${ml:+"$ml"}
  if [ -n "$SUDO" ]; then $SUDO chown -R "$(id -un):$(id -gn)" "$ASSETS"; fi
  if [ -n "$ml" ]; then touch "$ASSETS/with-ml"; else rm -f "$ASSETS/with-ml"; fi
  [ -f "$ASSETS/voss-guest.ext4" ] && [ -f "$ASSETS/vmlinux" ] && [ -x "$ASSETS/firecracker" ] \
    || die "setup did not produce firecracker, vmlinux and voss-guest.ext4 in $ASSETS"
  say; say "Setup done. Next: $0 check, then $0 smoke"
}

# --- run -------------------------------------------------------------------------------------------------------
KEEP_PID=""
INHIBIT_PID=""
ARGS=()

stop_keepalive() {
  if [ -n "$KEEP_PID" ]; then pkill -P "$KEEP_PID" 2>/dev/null || true; kill "$KEEP_PID" 2>/dev/null || true; fi
  KEEP_PID=""
}
start_inhibit() { # block suspend, idle and lid-close sleep while the run lasts (the lock lives as long as `sleep`)
  have systemd-inhibit || return 1
  systemd-inhibit --what=sleep:idle:handle-lid-switch --who=voss-calib --why="calibration timing run" \
    sleep 86400 >/dev/null 2>&1 &
  INHIBIT_PID=$!
  sleep 0.5
  if kill -0 "$INHIBIT_PID" 2>/dev/null; then return 0; fi
  INHIBIT_PID=""
  return 1
}
stop_inhibit() {
  if [ -n "$INHIBIT_PID" ]; then pkill -P "$INHIBIT_PID" 2>/dev/null || true; kill "$INHIBIT_PID" 2>/dev/null || true; fi
  INHIBIT_PID=""
}
on_exit() {
  stop_keepalive
  stop_inhibit
  if [ "${#PRIV[@]}" -gt 0 ] && [ -d "$RAW" ]; then sudo -n chown -R "$(id -un):$(id -gn)" "$RAW" 2>/dev/null || true; fi
}
trap on_exit EXIT
trap 'echo; warn "interrupted. If a suite was mid-way, run: $0 cleanup"; exit 130' INT TERM

pick_dirs() { # the scratch directories handed to the harness (one per disk tier)
  if [ -n "${VOSS_SSD_DIR:-}${VOSS_HDD_DIR:-}" ]; then
    [ -z "${VOSS_SSD_DIR:-}" ] || ARGS+=(--set "ssd_dir=$VOSS_SSD_DIR")
    [ -z "${VOSS_HDD_DIR:-}" ] || ARGS+=(--set "hdd_dir=$VOSS_HDD_DIR")
    return
  fi
  local tier=${VOSS_TIER:-$(tier_of "$(nearest_existing "$SCRATCH")")}
  case "$tier" in
    ssd | hdd) mkdir -p "$SCRATCH/$tier"; ARGS+=(--set "${tier}_dir=$SCRATCH/$tier") ;;
    *) die "cannot tell whether $WORK is on an SSD or a hard disk: rerun with VOSS_TIER=ssd or VOSS_TIER=hdd" ;;
  esac
}

build_args() {
  ARGS=(--out "$RAW")
  if [ "$DRY" != 1 ]; then
    [ -x "$ASSETS/firecracker" ] && [ -f "$ASSETS/vmlinux" ] && [ -f "$ASSETS/voss-guest.ext4" ] \
      || die "assets missing in $ASSETS: run  $0 setup  first"
  fi
  ARGS+=(--set "firecracker=$ASSETS/firecracker" --set "kernel=$ASSETS/vmlinux")
  ARGS+=(--set "rootfs=$ASSETS/voss-guest.ext4" --set "sebs_rootfs=$ASSETS/voss-guest.ext4")
  pick_dirs
  local fns=${VOSS_FUNCTIONS:-}
  if [ -z "$fns" ] && [ ! -f "$ASSETS/with-ml" ]; then # the image-recognition function needs the PyTorch image
    fns=$(cd "$REPO" && python3 -c 'from tools.calibrate.suites.sebs import SIZES; print(",".join(k for k in SIZES if k != "image-recognition"))')
  fi
  [ -z "$fns" ] || ARGS+=(--set "functions=$fns")
  [ -z "${VOSS_MAX_CONC:-}" ] || ARGS+=(--set "max_concurrency=$VOSS_MAX_CONC")
  [ -z "${VOSS_MEM_BUDGET_MB:-}" ] || ARGS+=(--set "mem_budget_mb=$VOSS_MEM_BUDGET_MB")
  if [ "$DRY" = 1 ]; then ARGS+=(--dry-run); fi
}

write_env() {
  mkdir -p "$RAW"
  {
    printf 'date_utc: %s\n' "$(date -u +%FT%TZ)"
    printf 'kernel: %s\n' "$(uname -srvmo)"
    printf 'os: %s\n' "$( (. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}") || echo unknown)"
    printf 'python: %s\n' "$(python3 --version 2>&1)"
    printf 'cpu_governor: %s\n' "$(governor)"
    printf 'on_battery: %s\n' "$(if on_battery; then echo yes; else echo no; fi)"
    printf 'mem_total_mb: %s\nmem_available_mb: %s\n' "$(mem_total_mb)" "$(mem_avail_mb)"
    printf 'work_disk_tier: %s\n' "${VOSS_TIER:-$(tier_of "$(nearest_existing "$WORK")")}"
    printf 'sudo_used: %s\n' "$(if [ "${#PRIV[@]}" -gt 0 ]; then echo yes; else echo no; fi)"
    printf -- '--- lscpu\n'; lscpu 2>/dev/null | grep -E '^(Model name|CPU\(s\)|Thread|Core|Socket|CPU max|CPU min|Virtualization|L2|L3)' || true
    printf -- '--- free -m\n'; free -m || true
    printf -- '--- lsblk\n'; lsblk -o NAME,ROTA,SIZE,TYPE,MODEL 2>/dev/null || true
    printf -- '--- df\n'; df -h "$WORK" || true
  } >"$RAW/env.txt"
}

harness() { # the node-side harness, as root when sudo is in use
  (cd "$REPO" && "${PRIV[@]+"${PRIV[@]}"}" env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.calibrate.run "$@")
}

cmd_run() {
  local mode=$1; shift
  local quick=() names=() all s skip=" ${VOSS_SKIP:-} "
  case "$mode" in
    smoke) quick=(--quick) ;;
    full) ;;
    run) [ "$#" -gt 0 ] || die "run: name at least one suite (see: python3 -m tools.calibrate.run --list)"; names=("$@") ;;
  esac
  python_ok || die "python3 >= 3.10 is required"
  if [ "${#names[@]}" -eq 0 ]; then
    all=$(cd "$REPO" && python3 -c 'from tools.calibrate.run import SAFE_DEFAULT; print(*SAFE_DEFAULT)')
    for s in $all; do case "$skip" in *" $s "*) say "skipping $s (VOSS_SKIP)" ;; *) names+=("$s") ;; esac; done
  fi
  if [ "$DRY" != 1 ]; then
    if on_battery && [ "${VOSS_FORCE:-0}" != 1 ]; then die "on battery: plug in the charger (or VOSS_FORCE=1 to ignore)"; fi
    start_inhibit || warn "cannot block suspend: keep the lid open and disable sleep in your power settings"
  fi
  build_args
  write_env
  if [ "${#PRIV[@]}" -gt 0 ]; then
    sudo -v || die "sudo failed; rerun with NO_SUDO=1 to skip the measurements that need root"
    ( while true; do sudo -n true 2>/dev/null || exit; sleep 50; done ) &
    KEEP_PID=$!
  fi
  say "Suites: ${names[*]}   (started $(date +%T); results in $RAW)"
  say "Do not use the laptop meanwhile: other load distorts the timings."
  for s in "${names[@]}"; do
    say; say "=== $s"
    harness --suite "$s" ${quick[@]+"${quick[@]}"} "${ARGS[@]}" || warn "$s: harness exit code $? (the other suites continue)"
  done
  stop_keepalive
  stop_inhibit
  say; say "Finished at $(date +%T)."
  (cd "$REPO" && python3 -m tools.calibrate.report summary "$RAW") || true
  say; say "Next: $0 pack   (or rerun a failed suite: $0 run SUITE)"
}

# --- pack, summary, cleanup ------------------------------------------------------------------------------------
cmd_pack() {
  [ -d "$RAW" ] || die "nothing to pack: $RAW does not exist (run smoke or full first)"
  local fp out
  fp=$(find "$RAW" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | head -n1)
  out="$WORK/voss-calib-${fp:-unknown}-$(date -u +%Y%m%d-%H%M).tar.gz"
  (cd "$REPO" && python3 -m tools.calibrate.report pack "$RAW" "$out")
  say; say "Archive: $out"; printf 'Size:    %s bytes\n' "$(wc -c <"$out")"
  say "SHA-256: $(sha256sum "$out" | cut -d' ' -f1)"
  say "It contains only result files; user name, home directory and host name are replaced. Send it as the README says."
}

cmd_cleanup() {
  local all=0
  [ "${1:-}" = --all ] && all=1
  [ "$SCRATCH" = "$WORK/scratch" ] || die "internal error: unexpected scratch path"
  say "Closing leftover test devices (only ours: voss-crypt, voss-verity, loop devices backed by $SCRATCH)"
  $SUDO cryptsetup close voss-crypt 2>/dev/null || true
  $SUDO veritysetup close voss-verity 2>/dev/null || true
  { $SUDO losetup -a 2>/dev/null || true; } | grep -F "$SCRATCH/" | cut -d: -f1 | while read -r dev; do
    $SUDO losetup -d "$dev" || true
  done || true
  if [ -d "$SCRATCH" ]; then say "Removing $SCRATCH"; $SUDO rm -rf -- "$SCRATCH"; fi
  if [ "$all" = 1 ] && [ -d "$ASSETS" ]; then say "Removing $ASSETS"; $SUDO rm -rf -- "$ASSETS"; fi
  say "Done. Results in $RAW are kept."
  say "Docker keeps its images; to free that space: sudo docker rmi voss-guest   (and: sudo docker image prune)"
}

case "${1:-help}" in
  check) cmd_check ;;
  setup) shift; cmd_setup "$@" ;;
  smoke) cmd_run smoke ;;
  full) cmd_run full ;;
  run) shift; cmd_run run "$@" ;;
  summary) (cd "$REPO" && python3 -m tools.calibrate.report summary "$RAW") ;;
  pack) cmd_pack ;;
  cleanup) shift; cmd_cleanup "$@" ;;
  *) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
