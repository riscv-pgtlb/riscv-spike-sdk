#!/bin/bash
# 确认当前处于符合要求的 Debian host 环境，再调用 install-tools.sh 安装工具
set -euo pipefail

test "$(id -u)" -eq 0 || {
    echo 'Run as root inside the Debian host' >&2
    exit 1
}

case "$(uname -r)" in
    *-pmpvirt-kvm-host|*-pmpvirt-kvm-host+|*-pmpvirt-kvm-host-*) ;;
    *) echo 'Protected host kernel required' >&2; exit 1 ;;
esac

. /etc/os-release
test "$ID" = debian

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bundle_dir=$(cd -- "$source_dir/../../.." && pwd)

for command in script lsblk grep tr mktemp flock sha256sum tar awk pgrep stat; do
    command -v "$command" >/dev/null
done

sh "$source_dir/install-tools.sh" host "$bundle_dir"
echo 'Debian host test tools installed'
