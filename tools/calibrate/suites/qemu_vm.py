"""QEMU VM boot (doc 10 §3 ``qemu_vm``) for the E-CS1 comparison: ``microvm`` and ``q35`` machines booting the same
guest rootfs to ``VOSS_MARK init`` on the serial console, timed from process spawn.
"""

from __future__ import annotations

from tools.calibrate.common import SuiteSkipped, time_to_marker
from tools.calibrate.suites import Ctx, Suite

APPEND = "console=ttyS0 root=/dev/vda ro init=/voss-init voss.mode=boot reboot=t panic=-1 quiet"


def argv(machine: str, kernel: str, rootfs: str, mem_mb: int) -> list[str]:
    base = ["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", str(mem_mb), "-smp", "1"]
    base += ["-nodefaults", "-no-user-config", "-nographic", "-serial", "stdio", "-no-reboot"]
    base += ["-kernel", kernel, "-append", APPEND]
    drive = ["-drive", f"id=root,file={rootfs},format=raw,if=none,readonly=on"]
    if machine == "microvm":
        return [*base, "-M", "microvm", *drive, "-device", "virtio-blk-device,drive=root"]
    return [*base, "-M", "q35", *drive, "-device", "virtio-blk-pci,drive=root"]


def run(ctx: Ctx) -> None:
    ctx.sh.need("qemu-system-x86_64")
    kernel, rootfs = ctx.opt("qemu_kernel") or ctx.opt("kernel"), ctx.opt("rootfs")
    if not kernel or not rootfs:
        raise SuiteSkipped("pass --set kernel=<vmlinux/bzImage> (or qemu_kernel=) --set rootfs=<ext4 image>")
    for machine in ("microvm", "q35"):
        for rep in range(ctx.reps(50)):
            cmd = argv(machine, kernel, rootfs, 256)
            if ctx.sh.dry_run:
                ctx.sh.run(cmd)
                break
            ctx.rec.add("qemu_boot", time_to_marker(cmd, "VOSS_MARK init", 60.0), rep=rep, machine=machine)


SUITE = Suite("qemu_vm", run, "QEMU microvm/q35 boot to init (E-CS1 comparison)")
