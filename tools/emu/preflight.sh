#!/bin/bash
# V13 multi-worker emulation (docs/REVISION_PLAN.md V13; docs/handoff/CALIBRATION_HANDOFF.md Part E): read-only audit of
# the machine before `tools.emu.run`. Changes nothing: no package installs, no sysctl, no namespaces, no cgroups, no
# VMs. `sudo -n true` only tests privileges; `ip netns list` and `tc qdisc show` only read.
# Usage: bash tools/emu/preflight.sh | tee ~/voss-calib/preflight.txt        (paste the output back; no secrets in it)
# The run itself repeats these checks and refuses to start (`uv run python -m tools.emu.preflight <scenario>`).
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
[ "$mem_gb" -ge 32 ] && ok "RAM >= 32 GB (6 workers x 4 GB cgroup limit plus the provider roles)" || warn "RAM < 32 GB: lower emu.mem_mb_per_worker or emu.workers"
[ "$(nproc)" -ge 16 ] && ok "$(nproc) hardware threads" || warn "only $(nproc) threads: 6 workers + 2 provider cores need 8 physical cores"

sec "Core kinds (one kind only for the workers, handoff Part E)"
if [ -r /sys/devices/cpu_core/cpus ] || [ -r /sys/devices/cpu_atom/cpus ]; then
  echo "  performance cores: $(cat /sys/devices/cpu_core/cpus 2>/dev/null || echo '?')"
  echo "  efficiency cores:  $(cat /sys/devices/cpu_atom/cpus 2>/dev/null || echo '?')"
  pcores=$(cat /sys/devices/cpu_core/cpus 2>/dev/null)
  [ -n "$pcores" ] && ok "hybrid CPU: the plan uses P-cores only" || warn "no P-core cpumask: the plan falls back to every core"
else
  warn "no hybrid PMU cpumasks (not a hybrid CPU, or an old kernel): the plan uses every core as one kind"
fi
echo "  topology (core_type 1 = performance, 2 = efficiency):"
for c in /sys/devices/system/cpu/cpu[0-9]*/topology; do
  d=$(dirname "$c"); printf '    %s core=%s core_type=%s\n' "$(basename "$d")" "$(cat "$c/core_id" 2>/dev/null)" "$(cat "$c/core_type" 2>/dev/null || echo '-')"
done | head -24

sec "Virtualisation (Firecracker needs KVM)"
grep -qE 'vmx|svm' /proc/cpuinfo && ok "CPU virtualisation flag present" || bad "no vmx/svm flag"
if [ -e /dev/kvm ]; then
  ls -l /dev/kvm | sed 's/^/  /'
  [ -r /dev/kvm ] && [ -w /dev/kvm ] && ok "/dev/kvm usable by this user" || warn "/dev/kvm exists but this user cannot open it (run as root or join the kvm group)"
else bad "/dev/kvm missing (BIOS VT-x off, or inside a VM without nested virtualisation)"; fi
for f in /sys/module/kvm_intel/parameters/nested /sys/module/kvm_amd/parameters/nested; do [ -r "$f" ] && echo "  nested ($f): $(cat "$f")"; done
v=$(systemd-detect-virt 2>/dev/null || echo none)
echo "  virt: $v"
[ "$v" = "none" ] && ok "bare metal" || bad "inside $v: the emulation must run on bare metal (handoff §2)"

sec "Multi-worker isolation (plan V13: namespaces, tc, cgroups, pinning)"
[ "$(id -u)" -eq 0 ] && ok "running as root" || warn "not root: netns, tc and cgroups need sudo (the run refuses to start)"
for t in ip tc taskset ping modprobe; do p=$(command -v $t 2>/dev/null) && ok "$t: $p" || bad "$t not found"; done
ip netns list >/dev/null 2>&1 && ok "ip netns works" || bad "ip netns does not work (iproute2 missing, or not root)"
tc qdisc show dev lo >/dev/null 2>&1 && ok "tc reads qdiscs" || bad "tc does not work (iproute2 missing, or not root)"
if modprobe -n sch_netem 2>/dev/null; then ok "sch_netem available"; else bad "sch_netem missing: install linux-modules-extra"; fi
if [ -r /sys/fs/cgroup/cgroup.controllers ]; then
  echo "  cgroup v2 controllers: $(cat /sys/fs/cgroup/cgroup.controllers)"
  grep -qw memory /sys/fs/cgroup/cgroup.controllers && ok "memory controller available" || bad "no memory controller: cgroup v2 needed"
  [ -w /sys/fs/cgroup ] && ok "cgroup tree writable" || bad "/sys/fs/cgroup not writable: run as root"
else bad "no /sys/fs/cgroup/cgroup.controllers: cgroup v2 is not mounted"; fi
echo "  open files limit: $(ulimit -n)"

sec "TPM (a real quote at every session start, handoff Part E)"
ls /dev/tpm* /dev/tpmrm* 2>/dev/null | sed 's/^/  /' || true
[ -e /dev/tpmrm0 ] && ok "TPM resource manager present" || bad "no /dev/tpmrm0: enable the firmware TPM (Intel PTT) in the firmware"
for t in tpm2_quote tpm2_createek tpm2_createak; do p=$(command -v $t 2>/dev/null) && ok "$t: $p" || bad "$t not found (tpm2-tools)"; done

sec "Assets and storage"
A=${VOSS_ASSETS:-$HOME/voss-calib/assets}
for f in firecracker vmlinux voss-guest.ext4; do
  [ -e "$A/$f" ] && ok "$A/$f" || bad "$A/$f missing (tools/calibrate/guest/fetch_assets.sh, build_rootfs.sh)"
done
lsblk -d -o NAME,SIZE,ROTA,TYPE,MODEL 2>/dev/null | sed 's/^/  /'
df -h / "$HOME" /var/tmp 2>/dev/null | sed 's/^/  /'
free_g=$(df -BG --output=avail /var/tmp 2>/dev/null | tail -1 | tr -dc 0-9)
[ "${free_g:-0}" -ge 50 ] && ok "${free_g} GB free under /var/tmp (emu.workdir)" || warn "only ${free_g:-0} GB free under /var/tmp: snapshots and VM memory files need 50 GB"

sec "Load now (is the machine idle? the run needs a quiet box)"
uptime | sed 's/^/  /'
ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -6 | sed 's/^/  /'
echo "  logged-in sessions: $(who 2>/dev/null | wc -l) (names and addresses not printed: the log is committed)"

sec "Next commands (handoff Part E)"
cat <<'EOF'
  # 0. fill in the scenario's emu: block if the assets or workdir live elsewhere
  uv run python -m tools.emu.preflight configs/emu/s1_central.yaml
  uv run python -m tools.emu.run configs/emu/s1_central.yaml --system voss --rep 1 --dry-run
  # 1. three repetitions per system, 2 h each
  for s in voss fixed_keepalive; do for r in 1 2 3; do
    sudo -E .venv/bin/python -m tools.emu.run configs/emu/s1_central.yaml \
      --system $s --rep $r --out runs-emu/<host_label>/ || break 2
  done; done
  # 2. compare with the simulator runs the builder provides
  uv run python -m tools.emu.compare --emu runs-emu/<host_label> --sim <simulator runs>
EOF
echo; echo "done (nothing was modified)"
