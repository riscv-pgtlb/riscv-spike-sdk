#!/bin/bash
set -euo pipefail
QEMU_BIN="${QEMU_BIN:-$HOME/work/qemu-install/bin/qemu-system-riscv64}"
IMG_DIR="${IMG_DIR:-$HOME/work/my_core_files}"

exec "$QEMU_BIN" \
  -M virt \
  -m 256M \
  -nographic \
  -accel tcg \
  -bios "$IMG_DIR/fw_jump.bin" \
  -kernel "$IMG_DIR/Image" \
  -initrd "$IMG_DIR/rootfs-devtmpfs.cpio.gz" \
  -append "console=ttyS0 earlycon=sbi rdinit=/sbin/init"
