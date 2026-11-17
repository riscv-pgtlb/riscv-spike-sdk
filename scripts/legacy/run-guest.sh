#!/bin/sh
set -eu

# 在外层 RISC-V Linux 中加载 KVM。
if [ ! -c /dev/kvm ]; then
    modprobe kvm
fi

# 检查运行 guest 所需的设备和镜像。
for path in /dev/kvm /opt/guest/Image /opt/guest/rootfs.cpio.gz; do
    if [ ! -r "$path" ]; then
        echo "Required file or device not readable: $path" >&2
        exit 1
    fi
done

# 创建 1 个 vCPU、256 MiB 内存的 guest，并连接串口控制台。
exec /usr/bin/lkvm run \
    --name guest-test \
    -k /opt/guest/Image \
    -i /opt/guest/rootfs.cpio.gz \
    -m 256 \
    -c 1 \
    --console serial \
    -n mode=none \
    -p "console=ttyS0 earlycon=sbi rdinit=/sbin/init"
