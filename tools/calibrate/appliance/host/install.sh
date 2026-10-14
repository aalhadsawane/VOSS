#!/bin/sh
# Install / remove the host-mode appliance probe and its bounded reboot-loop driver (doc 10 §6, D-60).
#   install.sh install [N]   copy units + scripts, save the current default target, enable the driver
#   install.sh uninstall     disable, restore the default target, remove units and scripts (data is kept)
# DESTDIR=/some/dir installs into a staging tree without calling systemctl (used by tests).
# Refuses an encrypted (LUKS) root unless VOSS_FORCE=1: an unattended reboot would wait for a passphrase.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
DESTDIR=${DESTDIR:-}
UNITS=$DESTDIR/etc/systemd/system
SBIN=$DESTDIR/usr/local/sbin
STATE=$DESTDIR/var/lib/voss-calib
LIST_SCRIPTS="voss-calib-restore voss-calib-arm voss-calib-driver voss-calib-probe"
LIST_UNITS="voss-calib.target voss-calib-restore.service voss-calib-probe.service voss-calib-driver.service"

die() { echo "install.sh: $*" >&2; exit 1; }
sysctl_() { [ -n "$DESTDIR" ] || systemctl "$@"; }

check_root_fs() {
    [ -n "$DESTDIR" ] && return 0
    command -v lsblk >/dev/null 2>&1 || return 0
    src=$(findmnt -no SOURCE / 2>/dev/null || true)
    if lsblk -s -no TYPE "$src" 2>/dev/null | grep -q crypt && [ "${VOSS_FORCE:-0}" != 1 ]; then
        die "the root filesystem is encrypted (LUKS): a reboot loop would stop at the passphrase prompt. VOSS_FORCE=1 overrides."
    fi
}

install_all() {
    n=${1:-20}
    check_root_fs
    mkdir -p "$UNITS" "$SBIN" "$STATE/appliance"
    for s in $LIST_SCRIPTS; do install -m 0755 "$HERE/$s" "$SBIN/$s"; done
    for u in $LIST_UNITS; do install -m 0644 "$HERE/$u" "$UNITS/$u"; done
    orig=graphical.target
    [ -n "$DESTDIR" ] || orig=$(systemctl get-default)
    [ "$orig" != voss-calib.target ] || die "default target is already voss-calib.target; run uninstall first"
    printf 'ORIG_TARGET=%s\nN=%s\nSETTLE=%s\n' "$orig" "$n" "${SETTLE:-60}" >"$STATE/config"
    rm -f "$STATE/appliance/STOP" "$STATE/appliance/DONE"
    sysctl_ daemon-reload
    sysctl_ enable voss-calib-driver.service
    echo "installed: $n measured reboots, original default target '$orig' saved in $STATE/config"
}

uninstall_all() {
    if [ -r "$STATE/config" ]; then
        # shellcheck disable=SC1091
        . "$STATE/config"
        sysctl_ disable voss-calib-driver.service || true
        [ "$(sysctl_ get-default 2>/dev/null || echo "$ORIG_TARGET")" != voss-calib.target ] || sysctl_ set-default "$ORIG_TARGET"
    fi
    for u in $LIST_UNITS; do rm -f "$UNITS/$u"; done
    for s in $LIST_SCRIPTS; do rm -f "$SBIN/$s"; done
    rm -f "$STATE/config"
    sysctl_ daemon-reload
    echo "uninstalled (logs in $STATE/appliance are kept)"
}

case "${1:-}" in
    install) install_all "${2:-20}" ;;
    uninstall) uninstall_all ;;
    *) die "usage: install.sh install [N] | uninstall" ;;
esac
