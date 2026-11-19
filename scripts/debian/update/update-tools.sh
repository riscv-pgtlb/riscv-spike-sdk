#!/bin/bash
set -euo pipefail

role=${1:-}
shift || true
case "$role" in
    host) package=debian-host-tools.tar.gz ;;
    guest) package=debian-guest-tools.tar.gz ;;
    *) echo 'Expected host or guest' >&2; exit 2 ;;
esac
if [ "$#" -ne 2 ] || [ "$1" != --from-dir ]; then
    echo "Usage: update-$([ "$role" = host ] && echo host || echo guest)-tools --from-dir DIRECTORY" >&2
    exit 2
fi

test "$(id -u)" -eq 0
test "$(uname -m)" = riscv64
. /etc/os-release
test "$ID" = debian
kernel=$(uname -r)
case "$role:$kernel" in
    host:*-pmpvirt-kvm-host|host:*-pmpvirt-kvm-host+|host:*-pmpvirt-kvm-host-*) ;;
    guest:*-virt-kvm-guest|guest:*-virt-kvm-guest+|guest:*-virt-kvm-guest-*) ;;
    *) echo "Wrong kernel for $role update: $kernel" >&2; exit 1 ;;
esac

for command in flock sha256sum tar mktemp awk install; do
    command -v "$command" >/dev/null
done
exec 9>"/run/lock/virt-tools-update.lock"
flock -n 9 || { echo 'Another tool update is running' >&2; exit 1; }
if [ "$role" = host ]; then
    command -v pgrep >/dev/null
    if pgrep -x 'lkvm|lkvm-static' >/dev/null; then
        echo 'Stop the guest before updating host tools' >&2
        exit 1
    else
        status=$?
        test "$status" -eq 1
    fi
fi

input_dir=$(cd -- "$2" && pwd)
work_dir=$(mktemp -d /var/tmp/virt-tools-update.XXXXXX)
trap 'rm -rf -- "$work_dir"' EXIT

# Snapshot both inputs before checking; only the selected package is required.
cp -- "$input_dir/$package" "$work_dir/$package"
cp -- "$input_dir/SHA256SUMS" "$work_dir/SHA256SUMS"
checksum=$(awk -v name="$package" \
    '$2 == name || $2 == "*" name { print $1 }' "$work_dir/SHA256SUMS")
[[ "$checksum" =~ ^[[:xdigit:]]{64}$ ]] || {
    echo "Missing or ambiguous checksum: $package" >&2; exit 1
}
cd "$work_dir"
printf '%s  %s\n' "$checksum" "$package" | sha256sum -c -
mkdir unpacked
tar -xzf "$package" -C unpacked
installer="$work_dir/unpacked/scripts/debian/install/install-$role.sh"
test -r "$installer"
if [ "$role" = host ]; then
    bash "$installer"
else
    sh "$installer"
fi
echo "VIRT TOOLS UPDATE PASS: $role"
