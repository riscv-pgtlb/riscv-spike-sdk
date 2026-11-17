#!/bin/sh
set -eu

role=${1:-}
case "$role" in
    host|guest) ;;
    *) echo "Usage: $0 host|guest" >&2; exit 2 ;;
esac
test "$(id -u)" -eq 0
test "$(uname -m)" = riscv64
. /etc/os-release
test "$ID" = debian
grep -Eq '(^|[[:space:]])debian_provision=1([[:space:]]|$)' /proc/cmdline

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$source_dir"
sha256sum -c SHA256SUMS
mount -o remount,rw /
work_dir=$(mktemp -d /run/debian-update.XXXXXX)
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
sync
echo "DEBIAN UPDATE PASS: $role"
