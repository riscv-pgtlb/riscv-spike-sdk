#!/bin/bash
set -euo pipefail

disk="${1:-/dev/vdb}"
host_version=${2:-}
guest_version=${3:-}
trap 'echo "VIRT-REGRESSION FAIL dual Debian suite" >&2' EXIT

case "$disk" in
    /dev/vdb) ;;
    *) echo 'This suite currently requires /dev/vdb' >&2; exit 1 ;;
esac

# Local metadata checks detect damaged files; explicit versions supplied by the
# server also reject a self-consistent but stale installation.
set -- --role host
if [ -n "$host_version" ]; then
    set -- "$@" --expect-version "$host_version"
fi
/usr/local/bin/check-virt-tools "$@"
paired_guest=$(cat /var/lib/virt-tools/EXPECTED-GUEST-VERSION)
if [ -n "$guest_version" ] && [ "$guest_version" != "$paired_guest" ]; then
    echo 'VIRT TOOLS VERSION MISMATCH: host expects a different guest package' >&2
    exit 1
fi
guest_version=$paired_guest
case "$guest_version" in *[!0-9a-f]*|'') echo 'Invalid guest tool version' >&2; exit 1 ;; esac
test "${#guest_version}" -eq 64
/usr/local/bin/check-stage2-virt-host
/usr/bin/check-virt-host
test -b "$disk"

mounts=$(lsblk -nr -o MOUNTPOINTS "$disk")
if printf '%s\n' "$mounts" | grep -q '[^[:space:]]'; then
    echo "Guest disk has mounted filesystems: $disk" >&2
    exit 1
fi
echo 'VIRT-REGRESSION HOST BEFORE PASS'

mkdir -p /var/log/virt-regression
log_dir=$(mktemp -d /var/log/virt-regression/debian-XXXXXX)
echo "Evidence: $log_dir"

script -q -e -c \
  "/usr/bin/lkvm run --pmp-virt-test --name debian-inner \
  -k /opt/guest/Image -d '$disk' \
  -m 768 -c 1 --console serial -n mode=none \
  -p 'console=ttyS0 root=/dev/vda1 rw rootwait maxcpus=1 virt_regression=1 pmpvirt_guest_test=1 virt_tools_version=$guest_version'" \
  "$log_dir/guest-console.log"

tr -d '\r' < "$log_dir/guest-console.log" \
    > "$log_dir/guest-console-clean.log"

grep -Eq '(^|check-virt-guest\[[0-9]+\]: )VIRT-REGRESSION GUEST PASS$' \
    "$log_dir/guest-console-clean.log"

grep -Eq '(^|echo\[[0-9]+\]: )VIRT-REGRESSION GUEST SHUTDOWN$' \
    "$log_dir/guest-console-clean.log"
grep -Eq "(^|check-virt-tools\[[0-9]+\]: )VIRT TOOLS VERSION PASS role=guest version=$guest_version$" \
    "$log_dir/guest-console-clean.log"

if grep -Eq 'Kernel panic|VIRT-REGRESSION FAIL|PMP\.Virt .*FAIL' \
    "$log_dir/guest-console-clean.log"; then
    echo 'Guest failure found in console log' >&2
    exit 1
fi

/usr/local/bin/check-virt-vs-hs "$log_dir/guest-console-clean.log"
echo 'VIRT-REGRESSION GUEST RETURNED'
/usr/local/bin/check-virt-tools "$@"
/usr/bin/check-virt-host
echo 'VIRT-REGRESSION HOST AFTER PASS'
echo 'VIRT-REGRESSION ALL PASS'
trap - EXIT
