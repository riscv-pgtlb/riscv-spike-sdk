#!/bin/sh
set -eu

# 先确认 host 保护有效。
/usr/bin/check-virt-host

DISK="${1:-/dev/vda}"
test -b "$DISK" || {
    echo "Debian disk not found: $DISK" >&2
    exit 1
}

# 外层 rootfs 位于内存，每次启动 guest 前先配置 host 网络。
NET_IFACE="${NET_IFACE:-eth0}"
if ! udhcpc -i "$NET_IFACE" -n -q -t 5 -T 3; then
    echo "Failed to configure host network: $NET_IFACE" >&2
    exit 1
fi

# 磁盘直接交给 guest，外层 host 不挂载。
exec /usr/bin/lkvm run \
    --name virt-debian \
    -k /opt/guest/Image \
    -d "$DISK" \
    -m 768 \
    -c 1 \
    --console serial \
    -n mode=user \
    -p "console=ttyS0 root=/dev/vda1 rw rootwait maxcpus=1"
