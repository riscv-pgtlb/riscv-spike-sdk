#!/bin/sh
set -eu
trap 'echo "VIRT-REGRESSION FAIL host suite"' EXIT
/usr/bin/check-virt-host
echo 'VIRT-REGRESSION HOST BEFORE PASS'
log=$(mktemp)
trap 'rm -f "$log"; echo "VIRT-REGRESSION FAIL host suite"' EXIT
if /usr/bin/run-virt-guest --regression > "$log" 2>&1; then
    cat "$log"
else
    cat "$log"
    exit 1
fi
/usr/bin/check-virt-vs-hs "$log"
rm -f "$log"
echo 'VIRT-REGRESSION GUEST RETURNED'
/usr/bin/check-virt-host
echo 'VIRT-REGRESSION HOST AFTER PASS'
echo 'VIRT-REGRESSION ALL PASS'
trap - EXIT
