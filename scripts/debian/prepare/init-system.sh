#!/bin/sh
set -eu

role=${1:-}
case "$role" in
    host|guest) ;;
    *) echo "Usage: $0 host|guest" >&2; exit 2 ;;
esac

test "$(id -u)" -eq 0
. /etc/os-release
test "$ID" = debian
test "$(uname -m)" = riscv64

# 仅用于直接从 virtio 根磁盘启动的实验系统。
root_device=$(findmnt -n -o SOURCE /)
test "$root_device" = /dev/vda1 || {
    echo "Unexpected root device: $root_device" >&2
    exit 1
}
root_uuid=$(blkid -s UUID -o value "$root_device")
test -n "$root_uuid"
test -r /usr/share/zoneinfo/Asia/Shanghai

mount -o remount,rw /
if [ ! -e /etc/fstab.before-dual-debian ]; then
    cp -a /etc/fstab /etc/fstab.before-dual-debian
fi

printf 'UUID=%s / ext4 defaults,errors=remount-ro 0 1\n' \
    "$root_uuid" > /etc/fstab

# 设置持久主机名
name="debian-$role"
printf '%s\n' "$name" > /etc/hostname

# 更新本机主机名解析，保留其他条目。
sed '/^[[:space:]]*127\.0\.1\.1[[:space:]]/d' /etc/hosts \
    > /etc/hosts.dual-debian.tmp
printf '127.0.1.1 %s\n' "$name" >> /etc/hosts.dual-debian.tmp
cat /etc/hosts.dual-debian.tmp > /etc/hosts
rm /etc/hosts.dual-debian.tmp

ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
printf 'Asia/Shanghai\n' > /etc/timezone
printf 'LANG=C.UTF-8\n' > /etc/locale.conf

sync
echo "DEBIAN BASE INIT PASS: $role"
