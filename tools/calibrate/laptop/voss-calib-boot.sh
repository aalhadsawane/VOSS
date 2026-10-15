#!/usr/bin/env bash
# Reboot- and BIOS-dependent steps of voss-calib.sh (sourced, not run): `appliance`, `tme`, `all`, `finish`.
# Doc 10 §3/§6, D-60. Only for the throwaway laptop whose owner approved reboots and data loss (AGENTS.md rule 14).
# The reboot loop itself lives in tools/calibrate/appliance/host/ and is bounded and killable (see README).

STATE_DIR=/var/lib/voss-calib
APP_LOGS=$STATE_DIR/appliance
HOST_DIR=$REPO/tools/calibrate/appliance/host
PHASE_ARGS=()

need_root_tools() {
  [ "$NO_SUDO" != 1 ] || die "this step needs sudo (NO_SUDO=1 is set)"
  have systemctl || die "systemd is required for the appliance steps"
}

app_counts() { # prints "armed complete"
  local a c
  a=$(find "$APP_LOGS" -maxdepth 1 -name 'arm-*.epoch' 2>/dev/null | wc -l) || true
  c=$(find "$APP_LOGS" -maxdepth 1 -name 'complete-*' 2>/dev/null | wc -l) || true
  printf '%s %s\n' "$a" "$c"
}

app_status() {
  local a c
  read -r a c < <(app_counts)
  if [ -e "$STATE_DIR/config" ]; then say "installed: yes ($(tr '\n' ' ' <"$STATE_DIR/config"))"; else say "installed: no"; fi
  say "boots armed: $a   completed: $c"
  [ -e "$APP_LOGS/STOP" ] && say "STOP file present: the loop will not continue"
  [ -e "$APP_LOGS/DONE" ] && say "DONE: the loop finished by itself"
  have systemctl && say "default target now: $(systemctl get-default)"
  return 0
}

app_install() {
  need_root_tools
  local n=${1:-${VOSS_BOOTS:-10}}
  case "$n" in '' | *[!0-9]*) die "number of boots must be a number" ;; esac
  [ "$n" -ge 1 ] && [ "$n" -le 40 ] || die "boots must be 1..40"
  $SUDO env VOSS_FORCE="${VOSS_FORCE:-0}" SETTLE="${VOSS_SETTLE:-60}" sh "$HOST_DIR/install.sh" install "$n"
}

app_uninstall() {
  need_root_tools
  $SUDO sh "$HOST_DIR/install.sh" uninstall
}

app_abort() {
  need_root_tools
  $SUDO mkdir -p "$APP_LOGS"
  $SUDO touch "$APP_LOGS/STOP"
  app_uninstall
  say "Aborted. Measured boots so far are kept; collect them with:  $0 appliance collect"
}

app_run() {
  need_root_tools
  local n=${1:-${VOSS_BOOTS:-10}}
  python_ok || die "python3 >= 3.10 is required"
  if on_battery && [ "${VOSS_FORCE:-0}" != 1 ]; then die "on battery: plug in the charger (a reboot loop must not die half-way)"; fi
  [ -e /dev/tpmrm0 ] || warn "no /dev/tpmrm0: boots are timed, but the TPM attestation part is skipped"
  say "This will REBOOT this laptop $((n + 0)) times, unattended, over roughly $((n * 4)) minutes:"
  say "  - it switches the default boot target to a minimal one for ONE boot at a time and back again;"
  say "  - each measured boot runs a TPM attestation round, then reboots into your normal system;"
  say "  - the normal system waits ${VOSS_SETTLE:-60} s after it has started, then arms the next boot."
  say "To stop at any time (from the normal system):  $0 appliance abort"
  say "If a boot hangs: hold the power button, switch on again; the original target is restored first thing in every boot."
  confirm "Save your work, close everything. Start the reboot loop now?" || die "cancelled"
  app_install "$n"
  say "Rebooting in 15 s (Ctrl-C cancels; then run  $0 appliance abort)."
  sleep 15
  $SUDO "/usr/local/sbin/voss-calib-arm"
}

app_collect() {
  local logs=$APP_LOGS
  [ -d "$logs" ] || die "no appliance logs in $logs: run  $0 appliance run  first"
  ARGS=(--out "$RAW" --set "appliance_log_dir=$logs" --set step=collect)
  [ "$DRY" != 1 ] || ARGS+=(--dry-run)
  mkdir -p "$RAW"
  harness --suite appliance "${ARGS[@]}"
  if [ "${#PRIV[@]}" -gt 0 ]; then sudo chown -R "$(id -u):$(id -g)" "$RAW" || true; fi
  (cd "$REPO" && python3 -m tools.calibrate.report summary "$RAW") || true
}

cmd_appliance() {
  local sub=${1:-status}
  [ "$#" -eq 0 ] || shift
  case "$sub" in
    status) app_status ;;
    install) app_install "$@" ;;
    run) app_run "$@" ;;
    abort) app_abort ;;
    collect) app_collect ;;
    uninstall) app_uninstall ;;
    *) die "appliance: status | install [N] | run [N] | abort | collect | uninstall" ;;
  esac
}

cmd_tme() {
  local phase=${1:-}
  if ! grep -qw tme /proc/cpuinfo 2>/dev/null; then
    say "This CPU does not report memory encryption (no 'tme' flag in /proc/cpuinfo), so there is nothing to compare."
    say "Skipping the tme suite; this is expected on an older i3."
    return 0
  fi
  case "$phase" in
    on | off) ;;
    *) say "TME is reported. Two runs are needed, each after changing the BIOS setting and booting:"
       say "  1. BIOS: Total Memory Encryption = Disabled.  Boot, then:  $0 tme off"
       say "  2. BIOS: Total Memory Encryption = Enabled.   Boot, then:  $0 tme on"
       say "(Setup key is usually F2, F10, F12 or Del at power-on. The script never edits the BIOS itself.)"
       return 0 ;;
  esac
  have gcc || die "gcc is missing: install your distribution's build tools (apt: build-essential libgomp1)"
  PHASE_ARGS=(--phase "$phase")
  cmd_run run tme
}

cmd_all() {
  python_ok || die "python3 >= 3.10 is required"
  if [ ! -x "$ASSETS/firecracker" ]; then cmd_setup --with-ml --yes; fi
  cmd_run smoke
  confirm "Smoke run finished (look for 'error' rows above). Continue with the full run?" || die "stopped after smoke"
  cmd_run full
  say; say "Next:  $0 appliance run   (reboots the laptop ~10 times)   then   $0 finish"
}

cmd_finish() {
  [ ! -d "$APP_LOGS" ] || app_collect
  cmd_cleanup
  cmd_pack
}
