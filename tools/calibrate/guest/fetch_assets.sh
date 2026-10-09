#!/bin/sh
# Download a pinned Firecracker release (firecracker + jailer) and the matching Firecracker CI guest kernel.
# Usage: fetch_assets.sh <out_dir>   Environment: FC_VERSION (default v1.10.1), CI_VERSION (default v1.10)
set -eu
OUT=$(realpath "${1:?usage: fetch_assets.sh <out_dir>}")
FC_VERSION=${FC_VERSION:-v1.10.1}
CI_VERSION=${CI_VERSION:-v1.10}
ARCH=$(uname -m)
mkdir -p "$OUT" && cd "$OUT"
curl -fsSL "https://github.com/firecracker-microvm/firecracker/releases/download/$FC_VERSION/firecracker-$FC_VERSION-$ARCH.tgz" | tar -xz
cp "release-$FC_VERSION-$ARCH/firecracker-$FC_VERSION-$ARCH" firecracker
cp "release-$FC_VERSION-$ARCH/jailer-$FC_VERSION-$ARCH" jailer
key=$(curl -fsSL "http://spec.ccfc.min.s3.amazonaws.com/?prefix=firecracker-ci/$CI_VERSION/$ARCH/vmlinux-&list-type=2" \
  | grep -oE "firecracker-ci/$CI_VERSION/$ARCH/vmlinux-[0-9]+\.[0-9]+\.[0-9]{1,3}" | sort -V | tail -1)
curl -fsSL -o vmlinux "https://s3.amazonaws.com/spec.ccfc.min/$key"
echo "firecracker $FC_VERSION, kernel $key" | tee versions.txt
sha256sum firecracker jailer vmlinux | tee assets.sha256
