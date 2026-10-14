# Calibration on a spare Linux laptop — runbook

This measures **one machine** (the laptop) and produces a folder of result files. Nobody connects to the laptop: you
run one script, wait, and send back one `.tar.gz`.

> **These numbers describe this laptop, not the i7 "C0" machine named in the design docs.** They are real
> measurements, and the simulator can use them as a measured bundle for this machine. The label "C0" for the i7
> node is decided later, when the results are ingested.

## What the script does to the laptop

| Does | Does not |
|---|---|
| Installs packages (`setup`, with a yes/no question first) | Reboot, power off, or touch BIOS/UEFI settings |
| Starts the docker service for this boot only (not enabled; it listens on a local socket only) | Partition or format any disk, or write boot entries |
| Downloads Firecracker + a test kernel (pinned versions) | Touch your files outside `~/voss-calib-work` |
| Builds a small Linux guest image with docker (docker's own copy takes 2–3 GB under `/var/lib/docker`) | Open network ports |
| Writes up to ~12 GB of temporary files under `~/voss-calib-work/scratch`, then deletes them | Send data anywhere (you copy the result file yourself) |
| Runs short tests: disk speed, TPM, TLS, Firecracker/QEMU micro-VMs, test functions | Run the two **manual** suites, `appliance` (reboots) and `tme` (BIOS toggle) |
| Briefly drops the kernel page cache and makes temporary loop/encrypted test devices (needs `sudo`) | |

**Left out on purpose:** the `appliance` (reboot-to-attested) and `tme` suites. The appliance image is still a draft
and untested, and an old laptop most likely has no memory-encryption (TME) to toggle. The `caps` suite reports
whether the laptop has either; we decide afterwards.

If the laptop freezes, hold the power button. Nothing the script writes is needed by the operating system, so the
worst case is a filesystem check at the next boot and leftover files that `cleanup` removes.

## Before you start (5 minutes)

- [ ] **x86-64 Linux** with `sudo`, **Python 3.10 or newer** (`python3 --version`), and internet during `setup`.
- [ ] **15 GB free** under your home directory and **6 GB free** on the system disk for docker (25 GB and 14 GB with
      `--with-ml`), and 4 GB RAM or more (less works; big tests are skipped).
- [ ] **Charger plugged in**, lid open, nothing else running (close browsers, stop updates, no downloads).
- [ ] **Hardware virtualisation on.** If `ls /dev/kvm` says "No such file", enable *Intel VT-x* / *AMD-V (SVM)* in the
      BIOS setup once. Without it the Firecracker, QEMU and test-function suites are skipped (the rest still runs).
- [ ] A **TPM 2.0** is nice to have (`ls /dev/tpmrm0`). Without it only the TPM and attestation suites are skipped.

## Steps

You need the `tools/` folder from this repository on the laptop. Either clone the repo and check out the branch
`p9-harness`, or unpack the tarball you were given (`tar -xzf voss-calib-tools.tar.gz`). Then, in the folder that
contains `tools/`:

```sh
S=tools/calibrate/laptop/voss-calib.sh

bash $S check            # 1. looks only, changes nothing. Fix anything marked FAIL.
bash $S setup            # 2. installs packages (asks first), downloads Firecracker, builds the guest image (10-30 min, mostly downloads)
bash $S smoke            # 3. every suite at 10% repetitions: finds problems early
bash $S full             # 4. the real run (use the smoke time as a guide: at most ~10x longer)
bash $S pack             # 5. makes one .tar.gz with the results
```

Notes:

- `setup --with-ml` also builds the PyTorch image so the `image-recognition` test function can run. It adds ~10 GB and
  a long download; skip it unless you are asked to.
- `setup` asks `Install now? [y/N]` and shows the exact command first. `--yes` answers for you.
- The script runs the measurements with `sudo` (it asks for your password once). `NO_SUDO=1 bash $S smoke` runs
  without root; cold-cache and encrypted-disk measurements are then skipped and recorded as skipped.
- **Do not use the laptop during `smoke` and `full`.** Other load changes the timings.
- Stop any time with `Ctrl-C`, then run `bash $S cleanup`.

### Reading the result of a run

At the end the script prints one line per suite, for example:

```
suite         records  status
caps                7  ok
disk               40  skipped: pass --set ssd_dir=...      <- tells you what to fix
fc_boot            90  ok
qemu_vm             0  error                                <- see error.txt next to meta.json
```

- `ok` — done. `skipped: …` — the suite decided it cannot run here (no KVM, no TPM, tool missing): fine, but note
  why. `error` — a bug or an unexpected failure; the other suites still ran. Rerun just that one:
  `bash $S run qemu_vm`.
- `qemu_vm` is the one most likely to fail: it boots the Firecracker kernel under QEMU, which not every kernel
  allows. A failure there is acceptable.
- Look at `~/voss-calib-work/raw/<id>/<suite>/<time>/error.txt` and paste its content into the chat if something fails.

## Sending the results back

`bash $S pack` prints the archive path, its size and SHA-256. The archive contains **only** result files
(`records.jsonl`, `meta.json`, `commands.txt`, `caps.json`, `error.txt`, `env.txt`). It never contains TPM keys, disk
images or private keys. The user name, home directory and host name are replaced by `USER` / `HOST`.

Get the file to the person running the coding session (USB stick, chat, mail), then from a clone of the repo on
**their** machine:

```sh
git fetch origin && git checkout -b calib-raw-laptop origin/p9-harness
mkdir -p calibration && tar -xzf voss-calib-*.tar.gz -C calibration/   # creates calibration/raw/...
git add -f calibration/raw && git commit -m "Raw calibration logs from the spare laptop"
git push -u origin calib-raw-laptop
```

Then tell the session "pushed `calib-raw-laptop`". The next steps (ingest into a measured bundle, the E-CS1 table,
validation notes) happen there; the laptop is not needed again unless a suite has to be rerun.

## Cleaning up

```sh
bash $S cleanup          # scratch files and leftover test devices (results are kept)
bash $S cleanup --all    # also the downloaded Firecracker/kernel and the guest image
sudo docker rmi voss-guest && sudo docker image prune   # docker's own copies (optional)
sudo apt-get remove docker.io                            # only if you want docker gone (use your distro's command)
```

`cleanup` only closes devices named `voss-crypt` / `voss-verity` and loop devices whose backing file is under
`~/voss-calib-work/scratch`. It never touches any other loop device (snap and AppImage use them).

## Knobs (environment variables)

| Variable | Effect |
|---|---|
| `VOSS_WORK=/path/with-voss-in-the-name` | Where everything lives (default `~/voss-calib-work`; the name must contain `voss`) |
| `VOSS_TIER=ssd` or `hdd` | Say which kind of disk `VOSS_WORK` is on when it cannot be detected |
| `VOSS_SSD_DIR`, `VOSS_HDD_DIR` | Use these directories (e.g. a second disk) as the SSD / HDD test locations |
| `VOSS_SKIP="sebs qemu_vm"` | Leave suites out of `smoke` / `full` (`sebs` is the longest) |
| `VOSS_MEM_BUDGET_MB=2000`, `VOSS_MAX_CONC=2` | Cap RAM use of the micro-VM tests / the number of guests at once |
| `VOSS_FORCE=1` | Run on battery anyway (not recommended) |
| `NO_SUDO=1` | Never use sudo |

The harness itself also refuses to use the last 2 GB of any disk and skips tests that would exceed 60% of the free
RAM (`skipped` records tell you which).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker storage` FAIL | Free space on the system disk (`sudo docker system prune -a` removes unused docker data) |
| `python3 >= 3.10` FAIL | Install a newer Python (`python3.11`), or use a newer distribution release |
| `/dev/kvm` missing | Enable VT-x/AMD-V in the BIOS; or `sudo modprobe kvm_intel` (`kvm_amd`) |
| `cannot tell … SSD or HDD` | `VOSS_TIER=ssd bash $S smoke` (or `hdd`) |
| `setup` cannot start docker | Start it yourself (`sudo systemctl start docker`) and rerun `setup` |
| Package names differ on your distribution | `setup` prints the list it wanted; install the equivalents and rerun |
| `on battery` | Plug the charger in |
| A suite hangs more than ~30 min | `Ctrl-C`, `bash $S cleanup`, then `bash $S run <the other suites>` and report which one hung |
