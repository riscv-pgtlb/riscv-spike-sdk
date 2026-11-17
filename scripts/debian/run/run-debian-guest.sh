#!/bin/bash
set -euo pipefail

# 确认运行在受保护的外层。
/usr/bin/check-virt-host

# 当前双磁盘布局中，第二块磁盘属于内层。
disk=/dev/vdb
test -b "$disk" || {
    echo "Guest disk not found: $disk" >&2
    exit 1
}

# 内层磁盘不能同时被外层挂载。
mounts=$(lsblk -nr -o MOUNTPOINTS "$disk")
if printf '%s\n' "$mounts" | grep -q '[^[:space:]]'; then
    echo "Guest disk has mounted filesystems: $disk" >&2
    exit 1
fi

test -r /opt/guest/Image

# 不传 virt_regression=1，进入正常登录模式，不自动测试关机。
exec /usr/bin/lkvm run \
    --name debian-inner \
    -k /opt/guest/Image \
    -d "$disk" \
    -m 768 \
    -c 1 \
    --console serial \
    -n mode=user \
    -p "console=ttyS0 root=/dev/vda1 rw rootwait maxcpus=1"
