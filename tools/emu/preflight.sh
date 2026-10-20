#!/bin/bash
# P9b / E01 (doc 10 §4): read-only audit of a machine for the single-box emulation testbed.
# Changes nothing: no package installs, no sysctl, no network namespaces, no VMs. `sudo -n true` only tests privileges.
# Usage: bash tools/emu/preflight.sh | tee preflight.txt        (paste the output back; it contains no secrets)
set -u
ok()   { printf '  [ok]   %s\n' "$*"; }
warn() { printf '  [WARN] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; }
sec()  { printf '\n== %s\n' "$*"; }

sec "Machine"
echo "host: $(hostname)   date: $(date -u +%FT%TZ)"
echo "os:   $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")   kernel: $(uname -r)   arch: $(uname -m)"
lscpu 2>/dev/null | grep -E "Model name|^CPU\(s\)|Thread|Core|Socket|MHz|L3" | sed 's/^/  /'
mem_gb=$(awk '/MemTotal/{printf "%.0f", $2/1048576}' /proc/meminfo); avail_gb=$(awk '/MemAvailable/{printf "%.0f", $2/1048576}' /proc/meminfo)
echo "  RAM: ${mem_gb} GB total, ${avail_gb} GB available   swap: $(awk '/SwapTotal/{printf "%.0f", $2/1048576}' /proc/meminfo) GB"
[ "$mem_gb" -ge 64 ] && ok "RAM >= 64 GB (20-40 microVMs of 512 MB-2 GB fit)" || warn "RAM < 64 GB: plan fewer workers or smaller VMs"
[ "$(nproc)" -ge 8 ] && ok "$(nproc) hardware threads" || warn "only $(nproc) threads: emulated workers will contend for CPU, which biases the comparison"

sec "Virtualisation (Firecracker needs KVM)"
grep -qE 'vmx|svm' /proc/cpuinfo && ok "CPU virtualisation flag present" || bad "no vmx/svm flag"
if [ -e /dev/kvm ]; then
  ls -l /dev/kvm | sed 's/^/  /'
  [ -r /dev/kvm ] && [ -w /dev/kvm ] && ok "/dev/kvm usable by this user" || warn "/dev/kvm exists but this user cannot open it (kvm group or sudo needed)"
else bad "/dev/kvm missing (BIOS VT-x off, or inside a VM without nested virtualisation)"; fi
for f in /sys/module/kvm_intel/parameters/nested /sys/module/kvm_amd/parameters/nested; do [ -r "$f" ] && echo "  nested ($f): $(cat "$f")"; done
systemd-detect-virt 2>/dev/null | sed 's/^/  virt: /'

sec "Storage"
lsblk -d -o NAME,SIZE,ROTA,TYPE,MODEL 2>/dev/null | sed 's/^/  /'
df -h / /tmp "$HOME" 2>/dev/null | sed 's/^/  /'
avail_g=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9)
[ "${avail_g:-0}" -ge 100 ] && ok "$avail_g GB free in \$HOME" || warn "only ${avail_g} GB free in \$HOME (microVM images, snapshots and raw logs need about 100 GB)"

sec "Privileges and tools"
if sudo -n true 2>/dev/null; then ok "passwordless sudo"; else warn "sudo needs a password (netns, tc and mounts need root)"; fi
for t in ip tc nft iptables jq curl git make python3 uv firecracker jailer qemu-system-x86_64 tpm2_getcap tpm2_quote; do
  p=$(command -v $t 2>/dev/null) && ok "$t: $p" || warn "$t not found"; done
python3 --version 2>&1 | sed 's/^/  /'
ip netns list >/dev/null 2>&1 && ok "ip netns works" || warn "ip netns needs root or is unavailable"
tc qdisc show dev lo >/dev/null 2>&1 && ok "tc available" || warn "tc unavailable"
modprobe -n sch_netem 2>/dev/null && ok "sch_netem module available" || warn "sch_netem module not confirmed (needs linux-modules-extra on Ubuntu)"
stat -fc '%T' /sys/fs/cgroup 2>/dev/null | sed 's/^/  cgroup fs: /'
ulimit -n | sed 's/^/  open files limit: /'

sec "TPM (optional: real quotes)"
ls /dev/tpm* /dev/tpmrm* 2>/dev/null | sed 's/^/  /' || true
[ -e /dev/tpmrm0 ] && ok "TPM resource manager present" || warn "no /dev/tpmrm0 (calibrated attestation delays are used instead)"

sec "Load now (is the machine idle? E01 timings need a quiet box)"
uptime | sed 's/^/  /'
ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -6 | sed 's/^/  /'
who 2>/dev/null | sed 's/^/  logged in: /'

sec "Outbound network (curl, not ping)"
for u in https://pypi.org https://github.com https://files.pythonhosted.org https://github.com/firecracker-microvm/firecracker/releases; do
  printf '  %s -> ' "$u"; curl -sS -m 8 -o /dev/null -w '%{http_code}\n' "$u" 2>&1 | tail -1; done
echo; echo "done (nothing was modified)"
