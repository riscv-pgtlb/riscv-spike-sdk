#!/bin/sh
set -eu

mode=live
case "$#:$*" in
    0:) ;;
    1:--offline) mode=offline ;;
    *) echo "Usage: $0 [--offline]" >&2; exit 2 ;;
esac

test "$(id -u)" -eq 0 || {
    echo 'Run as root inside the Debian guest' >&2
    exit 1
}

test "$(uname -m)" = riscv64 || {
    echo 'RISC-V system required' >&2
    exit 1
}

if [ "$mode" = live ]; then
    case "$(uname -r)" in
        *-virt-kvm-guest|*-virt-kvm-guest+|*-virt-kvm-guest-*) ;;
        *) echo 'Debian guest kernel required' >&2; exit 1 ;;
    esac
else
    # 离线模式仅供带显式启动标记的初始化虚拟机使用。
    grep -Eq '(^|[[:space:]])debian_provision=1([[:space:]]|$)' /proc/cmdline || {
        echo 'Offline installation requires debian_provision=1' >&2
        exit 1
    }
fi

. /etc/os-release
test "$ID" = debian

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bundle_dir=$(CDPATH= cd -- "$source_dir/../../.." && pwd)

for command in bash flock sha256sum tar mktemp awk stat; do
    command -v "$command" >/dev/null
done

sh "$source_dir/install-tools.sh" guest "$bundle_dir"

if [ "$mode" = live ]; then
    systemctl daemon-reload
    systemctl enable virt-guest-test.service
    systemctl is-enabled virt-guest-test.service
else
    systemctl --root="${DESTDIR:-/}" enable virt-guest-test.service
    systemctl --root="${DESTDIR:-/}" is-enabled virt-guest-test.service
fi
