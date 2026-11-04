#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
IMAGE="$HOME/work/linux-build-pmp-virt-user/arch/riscv/boot/Image"
EXPECTED=$(tr -d '\r\n' < expected-image.sha256)
ACTUAL=$(sha256sum "$IMAGE")
if [[ "${ACTUAL%% *}" != "$EXPECTED" ]]; then
    echo 'Image/firmware layout mismatch. Stop and inspect.' >&2
    exit 1
fi
exec "$HOME/work/qemu/build-pmp-virt/qemu-system-riscv64" \
    -M virt -m 256M -smp 1 -nographic -accel tcg \
    -cpu rv64,smepmp=off,x-pmp-virt=on \
    -bios "$HOME/work/opensbi-build-pmp-virt-user/platform/generic/firmware/fw_jump.bin" \
    -kernel "$IMAGE" -initrd "$PWD/build/rootfs-user-test.cpio.gz" \
    -append 'console=ttyS0 earlycon=sbi rdinit=/sbin/init maxcpus=1'
