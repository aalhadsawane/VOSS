#!/bin/sh
# Build the guest ext4 image used by fc_boot, fc_snapshot, qemu_vm and sebs (doc 10 §3), with Docker, on the node
# or any x86-64 build host. Usage: build_rootfs.sh <out_dir> [--with-ml]   (--with-ml adds PyTorch + ResNet-50)
# Shared hosts without docker-group access: DOCKER="sudo docker" SUDO=sudo VOSS_GUEST_IMAGE=voss-e01-guest ...
# (the image is removed again at the end; a base image that was already present is left alone).
set -eu
DOCKER=${DOCKER:-docker}
SUDO=${SUDO:-}
IMG=${VOSS_GUEST_IMAGE:-voss-guest}
HAD_BASE=$($DOCKER images -q python:3.11-slim-bookworm 2>/dev/null || true)
OUT=$(realpath "${1:?usage: build_rootfs.sh <out_dir> [--with-ml]}")
ML=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
CTX="$OUT/ctx"
rm -rf "$CTX" && mkdir -p "$CTX"
cp -r "$HERE/voss-init" "$HERE/fnrunner.py" "$HERE/functions" "$CTX/"
{
  echo "FROM python:3.11-slim-bookworm"
  echo "RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg busybox-static && rm -rf /var/lib/apt/lists/*"
  echo "RUN pip install --no-cache-dir jinja2==3.1.4 pillow==10.4.0 python-igraph==0.11.6 squiggle==0.3.1"
  if [ "$ML" = "--with-ml" ]; then
    echo "RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.4.1 torchvision==0.19.1"
    echo "RUN mkdir -p /voss/data && python3 -c \"import torch, torchvision; torch.save(torchvision.models.resnet50(weights='IMAGENET1K_V1').state_dict(), '/voss/data/resnet50.pth')\""
  fi
  echo "COPY voss-init /voss-init"
  echo "COPY fnrunner.py /voss/fnrunner.py"
  echo "COPY functions /voss/functions"
} > "$CTX/Dockerfile"
$DOCKER build -t "$IMG" "$CTX"
cid=$($DOCKER create "$IMG")
$SUDO rm -rf "$OUT/rootdir" && mkdir -p "$OUT/rootdir"
$DOCKER export "$cid" | $SUDO tar -x -C "$OUT/rootdir"
$DOCKER rm "$cid" >/dev/null
size_mb=$(( $($SUDO du -sm "$OUT/rootdir" | cut -f1) * 13 / 10 + 64 ))
$SUDO mkfs.ext4 -q -F -L voss-root -d "$OUT/rootdir" "$OUT/voss-guest.ext4" "${size_mb}M"
$SUDO chown "$(id -u):$(id -g)" "$OUT/voss-guest.ext4"
$SUDO rm -rf "$OUT/rootdir"
$DOCKER rmi "$IMG" >/dev/null 2>&1 || true
[ -n "$HAD_BASE" ] || $DOCKER rmi python:3.11-slim-bookworm >/dev/null 2>&1 || true
sha256sum "$OUT/voss-guest.ext4" | tee "$OUT/voss-guest.ext4.sha256"
