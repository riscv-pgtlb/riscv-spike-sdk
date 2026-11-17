#!/bin/sh
set -eu
trap 'echo "VIRT-REGRESSION FAIL host suite"' EXIT
/usr/bin/check-virt-host
echo 'VIRT-REGRESSION HOST BEFORE PASS'
/usr/bin/run-virt-guest --regression
echo 'VIRT-REGRESSION GUEST RETURNED'
/usr/bin/check-virt-host
echo 'VIRT-REGRESSION HOST AFTER PASS'
echo 'VIRT-REGRESSION ALL PASS'
trap - EXIT
