#!/usr/bin/env bash
# VOSS calibration, one command, fully unattended (doc 10, D-60). Run it once, as the normal user, with sudo:
#
#     sudo bash voss-calib-auto.sh            install, start, and follow the progress
#     sudo bash voss-calib-auto.sh status     where is it? (also works after a reboot)
#     sudo bash voss-calib-auto.sh stop       cancel everything and undo the reboot loop
#     sudo bash voss-calib-auto.sh again      a third round: rebuild the guest image, rerun sebs (3 missing functions) + qemu_vm
#     sudo bash voss-calib-auto.sh redo       a second round after a fix: rerun the failed suites + reboot test, pack
#
# It copies the tools to /opt/voss-calib and runs the stages as a systemd service, so closing the terminal does not
# stop it and the work resumes after every reboot (the reboot test restarts the laptop on its own):
#     setup -> full -> appliance (reboots, ~10 rounds) -> tme (skipped without CPU support) -> finish
# Result: ~/voss-calib-<user>-<date>.tar.gz in the home directory of the user who ran it, and ~/VOSS-CALIB-DONE.txt.
# For a throwaway machine only (AGENTS.md rule 14): it reboots the machine and installs packages without asking.
set -Eeuo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=${VOSS_AUTO_ROOT:-}          # tests stage everything under a temporary root
OPT=$ROOT/opt/voss-calib
CONF=$ROOT/etc/voss-calib/auto.env
CALIB=$ROOT/var/lib/voss-calib
STATE=$CALIB/auto
APP_LOGS=$CALIB/appliance
UNIT=voss-calib-auto.service
LOG=$STATE/auto.log
STAGES=(setup full appliance tme finish)
RERUN_SUITES="fc_snapshot qemu_vm sebs"
RERUN_FUNCTIONS=""                 # empty: the suites' own default list
MAX_ATTEMPTS=3

say() { printf '%s\n' "$*"; }
log() { printf '%s %s\n' "$(date '+%F %T')" "$*"; }  # inside the service stdout is the log file
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- launcher (the part the user runs) ---------------------------------------------------------------------------
launcher_user() { # the person who typed sudo, not root
  local u=${SUDO_USER:-${USER:-}}
  [ -n "$u" ] || die "cannot tell which user to run for: start it as  sudo bash $0  from your normal account"
  getent passwd "$u" >/dev/null || die "unknown user '$u'"
  printf '%s\n' "$u"
}

install_and_start() {
  [ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" "$@"
  command -v systemctl >/dev/null 2>&1 || die "systemd is required"
  local user home
  user=$(launcher_user)
  home=$(getent passwd "$user" | cut -d: -f6)
  [ -d "$home" ] || die "home directory of $user not found ($home)"
  if [ -e "$STATE/RUN" ] && [ ! -e "$STATE/DONE" ] && systemctl is-active --quiet "$UNIT"; then
    say "Already running. Following the log (Ctrl-C only stops watching)."; follow; return
  fi
  mkdir -p "$OPT" "$STATE" "$(dirname "$CONF")"
  if [ "$(cd "$HERE/../.." && pwd)" != "$OPT/tools" ]; then
    rm -rf "$OPT/tools"
    cp -a "$HERE/../.." "$OPT/tools"           # HERE = tools/calibrate/laptop, so HERE/../.. = tools/
  fi
  chmod -R a+rX "$OPT"
  printf 'TARGET_USER=%s\nTARGET_HOME=%s\nBOOTS=%s\nSTAGE_LIST="%s"\n' \
    "$user" "$home" "${VOSS_BOOTS:-10}" "${VOSS_AUTO_STAGES:-${STAGES[*]}}" >"$CONF"
  printf 'RERUN_SUITES="%s"\nRERUN_FUNCTIONS="%s"\n' "${VOSS_AUTO_SUITES:-$RERUN_SUITES}" "${VOSS_AUTO_FUNCTIONS:-}" >>"$CONF"
  rm -f "$STATE"/{STOP,DONE,stage,attempts}
  touch "$STATE/RUN" "$LOG"
  mkdir -p "$ROOT/etc/systemd/system"
  cat >"$ROOT/etc/systemd/system/$UNIT" <<EOF
[Unit]
Description=VOSS calibration (unattended; resumes after reboots; \`sudo bash voss-calib-auto.sh stop\` cancels)
After=network-online.target
Wants=network-online.target
ConditionPathExists=$STATE/RUN
ConditionPathExists=!$STATE/DONE
ConditionPathExists=!$STATE/STOP

[Service]
Type=simple
ExecStart=/usr/bin/env bash $OPT/tools/calibrate/laptop/voss-calib-auto.sh stages
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable $UNIT >/dev/null 2>&1
  if [ -r /sys/class/power_supply/AC/online ] && [ "$(cat /sys/class/power_supply/AC/online)" = 0 ]; then
    say "WARNING: running on battery. Plug the charger in now."
  fi
  say "Starting for user '$user' (results go to $home). The laptop will REBOOT by itself during the run."
  say "Safe to close this terminal. Check progress any time:  sudo bash $0 status"
  systemctl start --no-block $UNIT
  follow
}

follow() { # show the log until the run is over; Ctrl-C only stops watching
  trap 'echo; echo "(stopped watching; the run continues)"; exit 0' INT
  tail -n 20 -F "$LOG" 2>/dev/null &
  local t=$!
  while [ ! -e "$STATE/DONE" ] && [ ! -e "$STATE/STOP" ]; do sleep 5; done
  sleep 1; kill "$t" 2>/dev/null || true
  [ ! -e "$STATE/DONE" ] || say "Finished. See $(getent passwd "$(launcher_user)" | cut -d: -f6)/VOSS-CALIB-DONE.txt"
}

show_status() {
  [ -d "$STATE" ] || die "not installed"
  say "stage: $(cat "$STATE/stage" 2>/dev/null || echo setup)   attempts: $(cat "$STATE/attempts" 2>/dev/null || echo 0)"
  [ ! -e "$STATE/DONE" ] || say "DONE"
  [ ! -e "$STATE/STOP" ] || say "STOPPED"
  systemctl is-active $UNIT 2>/dev/null | sed 's/^/service: /' || true
  say "appliance boots armed: $(find "$APP_LOGS" -maxdepth 1 -name 'arm-*.epoch' 2>/dev/null | wc -l)  complete: $(find "$APP_LOGS" -maxdepth 1 -name 'complete-*' 2>/dev/null | wc -l)"
  say "--- last log lines"; tail -n 15 "$LOG" 2>/dev/null || true
}

stop_all() {
  [ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" "$@"
  mkdir -p "$STATE" "$APP_LOGS"
  touch "$STATE/STOP" "$APP_LOGS/STOP"
  systemctl disable --now $UNIT 2>/dev/null || true
  if [ -x "$OPT/tools/calibrate/appliance/host/install.sh" ]; then
    sh "$OPT/tools/calibrate/appliance/host/install.sh" uninstall || true
  fi
  say "Cancelled. Results so far stay in the work directory (voss-calib-work in your home)."
}

# --- the stage machine (runs as root inside the service, after every boot until DONE) --------------------------------
load_conf() {
  [ -r "$CONF" ] || die "$CONF missing: start with  sudo bash $0"
  # shellcheck disable=SC1090
  . "$CONF"
  read -ra STAGES <<<"${STAGE_LIST:-${STAGES[*]}}"
  export HOME=$TARGET_HOME USER=$TARGET_USER LOGNAME=$TARGET_USER SUDO_USER=$TARGET_USER
  export VOSS_ALLOW_ROOT=1 VOSS_YES=1 VOSS_FORCE=1 VOSS_NODE=$TARGET_USER VOSS_BOOTS=$BOOTS
  export DEBIAN_FRONTEND=noninteractive
  MAIN=${VOSS_AUTO_MAIN:-"bash $OPT/tools/calibrate/laptop/voss-calib.sh"}
  WORKDIR=$TARGET_HOME/voss-calib-work
}

stage_now() { cat "$STATE/stage" 2>/dev/null || echo "${STAGES[0]}"; }
advance() { # move to the stage after $1 and reset the attempt counter
  local i next=done
  for i in "${!STAGES[@]}"; do
    if [ "${STAGES[$i]}" = "$1" ]; then next=${STAGES[$((i + 1))]:-done}; fi
  done
  printf '%s\n' "$next" >"$STATE/stage"; echo 0 >"$STATE/attempts"
}
bump() { local n; n=$(($(cat "$STATE/attempts" 2>/dev/null || echo 0) + 1)); echo "$n" >"$STATE/attempts"; echo "$n"; }

stage_setup() { $MAIN setup --with-ml --yes || $MAIN setup --yes; }  # the ML image is optional: fall back without it
stage_rerun() { VOSS_FUNCTIONS=$RERUN_FUNCTIONS $MAIN run $RERUN_SUITES; }
stage_rootfs() { # rebuild the guest image (the guest functions live inside it)
  if [ -f "$WORKDIR/assets/with-ml" ]; then $MAIN setup --with-ml --yes; else $MAIN setup --yes; fi
}
stage_full() { timeout --signal=TERM 10h $MAIN full; }
stage_tme() {
  if grep -qw tme /proc/cpuinfo; then
    log "TME is reported by this CPU but needs two manual BIOS changes; not automated. Later: bash voss-calib.sh tme"
  else
    log "No TME on this CPU: tme suite skipped (expected)."
  fi
}
stage_finish() {
  [ ! -d "$APP_LOGS" ] || $MAIN appliance collect || log "appliance collect failed (continuing)"
  local dbg=$WORKDIR/raw/debug d
  mkdir -p "$dbg"  # plain-text logs for diagnosing a failed step (packed, scrubbed)
  cp "$LOG" "$dbg/auto.log" 2>/dev/null || true
  for d in "$APP_LOGS" "$APP_LOGS".prev-*; do
    [ -d "$d" ] && for f in "$d"/probe-*.log; do [ -e "$f" ] && cp "$f" "$dbg/$(basename "$d")-$(basename "$f")"; done
  done
  journalctl -u 'voss-calib-*' --no-pager -o short-iso >"$dbg/units.log" 2>&1 || true
  $MAIN cleanup || true
  $MAIN pack
  local tgz out sum
  tgz=$(find "$WORKDIR" -maxdepth 1 -name 'voss-calib-*.tar.gz' -printf '%T@ %p\n' | sort -n | tail -n1 | cut -d' ' -f2-)
  [ -n "$tgz" ] || die "pack produced no archive"
  out=$TARGET_HOME/voss-calib-$TARGET_USER-$(date -u +%Y%m%d-%H%M).tar.gz
  cp "$tgz" "$out"; chown "$TARGET_USER" "$out"
  sum=$(sha256sum "$out" | cut -d' ' -f1)
  printf 'Calibration finished %s\nResults: %s\nSHA-256: %s\nSend that one file. Cleanup: sudo bash %s stop (already done).\n' \
    "$(date '+%F %T')" "$out" "$sum" "$OPT/tools/calibrate/laptop/voss-calib-auto.sh" >"$TARGET_HOME/VOSS-CALIB-DONE.txt"
  chown "$TARGET_USER" "$TARGET_HOME/VOSS-CALIB-DONE.txt"
  chown -R "$TARGET_USER" "$WORKDIR" 2>/dev/null || true
  log "RESULT: $out"
}

stage_appliance() { # the bounded reboot loop is driven by voss-calib-driver.service; here: start it, then wait
  if [ ! -e "$CALIB/config" ]; then
    local n; n=$(bump)
    if [ -d "$APP_LOGS" ] && [ -n "$(ls -A "$APP_LOGS" 2>/dev/null)" ]; then  # logs of an earlier round: keep, restart numbering
      mv "$APP_LOGS" "$APP_LOGS.prev-$(date +%s)"
    fi
    [ "$n" -le "$MAX_ATTEMPTS" ] || { log "appliance: could not start after $MAX_ATTEMPTS tries, skipping"; return 0; }
    log "appliance: installing the reboot loop and rebooting now"
    $MAIN appliance run "$BOOTS" || { log "appliance: start failed"; return 0; }
    return 3
  fi
  log "appliance: waiting for the reboot loop to finish"
  local waited=0
  while [ ! -e "$APP_LOGS/DONE" ] && [ ! -e "$APP_LOGS/STOP" ] && [ "$waited" -lt 28800 ]; do sleep 20; waited=$((waited + 20)); done
  log "appliance: loop over ($(find "$APP_LOGS" -maxdepth 1 -name 'complete-*' | wc -l) complete boots)"
}

run_stages() {
  load_conf
  mkdir -p "$STATE"
  exec >>"$LOG" 2>&1
  local s n rc
  while [ "$(stage_now)" != done ] && [ ! -e "$STATE/STOP" ]; do
    s=$(stage_now)
    if [ "$s" != appliance ]; then
      n=$(bump)
      if [ "$n" -gt "$MAX_ATTEMPTS" ]; then log "$s: gave up after $MAX_ATTEMPTS attempts, moving on"; advance "$s"; continue; fi
    fi
    log "== stage $s (boot at $(uptime -s))"
    rc=0
    "stage_$s" || rc=$?
    if [ "$rc" -eq 3 ]; then sleep "${VOSS_AUTO_REBOOT_WAIT:-900}"; log "reboot did not happen, will retry"; break; fi  # the reboot ends this process
    if [ "$rc" -eq 0 ]; then log "stage $s ok"; else log "stage $s FAILED"; fi
    if [ "$rc" -ne 0 ] && [ "$s" = setup ] && [ "$(cat "$STATE/attempts")" -lt "$MAX_ATTEMPTS" ]; then sleep 30; continue; fi
    advance "$s"
  done
  if [ "$(stage_now)" = done ]; then
    touch "$STATE/DONE"
    systemctl disable $UNIT >/dev/null 2>&1 || true
    sh "$OPT/tools/calibrate/appliance/host/install.sh" uninstall >/dev/null 2>&1 || true
    log "ALL DONE"
    if command -v wall >/dev/null 2>&1; then wall "VOSS calibration finished: see $TARGET_HOME/VOSS-CALIB-DONE.txt" || true; fi
  fi
}

case "${1:-start}" in
  start) shift || true; install_and_start "$@" ;;
  status) show_status ;;
  stop) stop_all "$@" ;;
  stages) run_stages ;;
  again)
    [ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" again
    VOSS_AUTO_STAGES="rootfs rerun finish" VOSS_AUTO_SUITES="sebs qemu_vm" \
      VOSS_AUTO_FUNCTIONS="graph-mst,graph-bfs,dna-visualisation" install_and_start ;;
  redo)
    [ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" redo
    VOSS_AUTO_STAGES="rerun appliance finish" install_and_start ;;
  *) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
