#!/bin/sh
set -eu

role=${1:-}
case "$role" in
    host|guest) ;;
    *) echo "Usage: $0 host|guest" >&2; exit 2 ;;
esac

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$source_dir"

# 此脚本在 QEMU 内的维护环境中运行。
test "$(id -u)" -eq 0
test "$(uname -m)" = riscv64

# 在修改系统前检查密码配置。
test -r root-password.hash || {
    echo "Missing root-password.hash" >&2
    exit 1
}
password_hash=$(cat root-password.hash)
case "$password_hash" in
    '$6$'*) ;;
    *) echo "Expected a SHA-512 crypt password hash" >&2; exit 1 ;;
esac
case "$password_hash" in
    *:*|*'
'*) echo "Invalid password hash" >&2; exit 1 ;;
esac

sha256sum -c SHA256SUMS
sh ./init-system.sh "$role"

work_dir=$(mktemp -d /run/debian-provision.XXXXXX)

case "$role" in
    host)
        tar -xzf dual-debian-tools.tar.gz -C "$work_dir"
        bash "$work_dir/scripts/debian/install/install-host.sh"
        ;;
    guest)
        tar -xzf debian-guest-tools.tar.gz -C "$work_dir"

        sh "$work_dir/scripts/debian/install/install-guest.sh" --offline
        ;;
esac

# chpasswd -e 接收密码哈希，不接收明文密码。
printf 'root:%s\n' "$password_hash" | chpasswd -e
unset password_hash

sync
echo "DEBIAN PROVISION PASS: $role"
