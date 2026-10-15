#!/bin/sh
# Build the guest ext4 image used by fc_boot, fc_snapshot, qemu_vm and sebs (doc 10 §3), with Docker, on the node
# or any x86-64 build host. Usage: build_rootfs.sh <out_dir> [--with-ml]   (--with-ml adds PyTorch + ResNet-50)
set -eu
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
docker build -t voss-guest "$CTX"
cid=$(docker create voss-guest)
rm -rf "$OUT/rootdir" && mkdir -p "$OUT/rootdir"
docker export "$cid" | tar -x -C "$OUT/rootdir"
docker rm "$cid" >/dev/null
size_mb=$(( $(du -sm "$OUT/rootdir" | cut -f1) * 13 / 10 + 64 ))
mkfs.ext4 -q -F -L voss-root -d "$OUT/rootdir" "$OUT/voss-guest.ext4" "${size_mb}M"
rm -rf "$OUT/rootdir"
sha256sum "$OUT/voss-guest.ext4" | tee "$OUT/voss-guest.ext4.sha256"
