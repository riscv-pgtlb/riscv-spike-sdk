#!/bin/sh
set -eu

/usr/bin/check-virt-host
for input in /usr/bin/lkvm /opt/guest/Image /opt/guest/rootfs.cpio.gz; do
    test -r "$input" || { echo "Missing guest input: $input" >&2; exit 1; }
done
exec /usr/bin/lkvm run \
    --name virt-kvm-b1 \
    -k /opt/guest/Image \
    -i /opt/guest/rootfs.cpio.gz \
    -m 256 \
    -c 1 \
    --console serial \
    -n mode=none \
    -p 'console=ttyS0 earlycon=sbi rdinit=/sbin/init maxcpus=1'
