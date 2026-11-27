#!/bin/sh
set -eu
trap 'echo "VIRT-REGRESSION FAIL host suite"' EXIT
/usr/bin/check-stage2-virt-host
/usr/local/bin/check-stage2-virt-kvmtool
/usr/bin/check-virt-host
echo 'VIRT-REGRESSION HOST BEFORE PASS'
log=$(mktemp)
stream="${log}.stream"
mkfifo "$stream"
trap 'rm -f "$stream" "$log"; echo "VIRT-REGRESSION FAIL host suite"' EXIT

# Keep the inner guest console visible while retaining the complete transcript
# for the ordered VS-HS-VS evidence checker.  Do not use a plain pipeline here:
# POSIX sh would report tee's status instead of run-virt-guest's status.
tee "$log" < "$stream" &
tee_pid=$!
set +e
/usr/bin/run-virt-guest --regression > "$stream" 2>&1
guest_rc=$?
set -e
wait "$tee_pid"
rm -f "$stream"

if [ "$guest_rc" -ne 0 ]; then
    echo "VIRT-REGRESSION FAIL inner guest exited rc=$guest_rc" >&2
    exit 1
fi
/usr/bin/check-virt-vs-hs "$log"
rm -f "$log"
echo 'VIRT-REGRESSION GUEST RETURNED'
/usr/bin/check-virt-host
echo 'VIRT-REGRESSION HOST AFTER PASS'
echo 'VIRT-REGRESSION ALL PASS'
trap - EXIT
