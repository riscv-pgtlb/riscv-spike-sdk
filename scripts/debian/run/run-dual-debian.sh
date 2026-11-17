#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$project_dir"

mkdir -p "$project_dir/build"
exec 8>"$project_dir/build/debian-operation.lock"
flock -s -n 8 || { echo 'Debian preparation or update is active' >&2; exit 1; }

host_disk="${DEBIAN_HOST_DISK:-$project_dir/images/debian/debian-host.raw}"
guest_disk="${DEBIAN_GUEST_DISK:-$project_dir/images/debian/debian-guest.raw}"

for disk in "$host_disk" "$guest_disk"; do
    test -f "$disk" && test -r "$disk" && test -w "$disk" || {
        echo "Disk missing or not readable/writable: $disk" >&2
        exit 1
    }
done

if [ "$host_disk" -ef "$guest_disk" ]; then
    echo 'Host and guest must use separate disk files' >&2
    exit 1
fi

python3 scripts/build/virt-kvm.py verify

# QEMU 的磁盘参数用逗号分隔，文件路径中的逗号需要转义。
host_disk="${host_disk//,/,,}"
guest_disk="${guest_disk//,/,,}"

# -append：
#   console=ttyS0：串口控制台。
#   earlycon=sbi：输出早期启动日志。
#   root=/dev/vda1：从外层磁盘第 1 分区挂载根文件系统。
#   rw：根文件系统可读写。
#   rootwait：等待根磁盘设备出现。
#   maxcpus=1：保持单核实验范围。
exec ./build/virt-kvm/out/qemu/qemu-system-riscv64 \
    -machine virt \
    -accel tcg \
    -cpu rv64,h=true,smepmp=off,x-pmp-virt=on \
    -m 2048M -smp 1 -nographic \
    -bios build/virt-kvm/out/opensbi/platform/generic/firmware/fw_jump.bin \
    -kernel build/virt-kvm/out/linux-host/arch/riscv/boot/Image \
    -drive "file=$host_disk,format=raw,if=none,id=hostroot" \
    -device virtio-blk-device,drive=hostroot \
    -drive "file=$guest_disk,format=raw,if=none,id=guestroot" \
    -device virtio-blk-device,drive=guestroot \
    -netdev user,id=hostnet \
    -device virtio-net-device,netdev=hostnet \
    -append "console=ttyS0 earlycon=sbi root=/dev/vda1 rw rootwait maxcpus=1"
