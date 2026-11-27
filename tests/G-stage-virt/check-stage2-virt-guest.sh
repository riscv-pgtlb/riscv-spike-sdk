#!/bin/sh
set -eu

TEST_BIN=${STAGE2_VIRT_GUEST_TEST:-/usr/bin/stage2-virt-guest-test}
ATTACK_BIN=${STAGE2_VIRT_ATTACK_TEST:-/usr/bin/stage2-virt-syscall-attack}
DEVICE=${STAGE2_VIRT_GUEST_DEVICE:-/dev/stage2_virt_test}

test -c "$DEVICE" || {
	echo "Missing Stage2Virt Guest device: $DEVICE" >&2
	exit 1
}
test -x "$TEST_BIN" || {
	echo "Missing Stage2Virt Guest test: $TEST_BIN" >&2
	exit 1
}

log=$(mktemp "${TMPDIR:-/tmp}/stage2-virt-guest.XXXXXX")
trap 'rm -f "$log"' EXIT HUP INT TERM

if "$TEST_BIN" >"$log" 2>&1; then
	cat "$log"
else
	cat "$log" >&2
	exit 1
fi

awk '
function gpa() {
	if (match($0, /GPA=0x[0-9a-fA-F]+/))
		return tolower(substr($0, RSTART + 4, RLENGTH - 4))
	return ""
}
/Stage2Virt Guest .*FAIL/ { exit 1 }
/^Stage2Virt Guest VU BEFORE PASS: GPA=0x[0-9a-fA-F]+ value=0x5a$/ {
	if (stage != 0 || first != "") exit 1
	first = gpa(); stage = 1; next
}
/^Stage2Virt Guest VS PROBE PASS: GPA=0x[0-9a-fA-F]+ expected-access-fault$/ {
	if (stage != 1 || gpa() != first) exit 1
	stage = 2; next
}
/^Stage2Virt Guest VU AFTER PASS: GPA=0x[0-9a-fA-F]+ value=0xa5$/ {
	if (stage != 2 || gpa() != first) exit 1
	stage = 3; next
}
/^Stage2Virt Guest VU-VS-VU SAME-PAGE PASS: GPA=0x[0-9a-fA-F]+$/ {
	if (stage != 3 || gpa() != first) exit 1
	stage = 4; next
}
END { if (stage != 4) exit 1 }
' "$log" || {
	echo 'Invalid Stage2Virt Guest VU-VS-VU evidence' >&2
	exit 1
}

echo 'Linux Guest Stage2Virt VU-VS-VU runtime test PASS'

test -x "$ATTACK_BIN" || { echo "Missing Stage2Virt syscall attack test: $ATTACK_BIN" >&2; exit 1; }
attack_output=$($ATTACK_BIN)
printf '%s\n' "$attack_output"
printf '%s\n' "$attack_output" | grep -Fxq 'STAGE2-SYSCALL-ATTACK API: PASS 2/2 rejection checks'
test "$(printf '%s\n' "$attack_output" | grep -Ec '^STAGE2-SYSCALL-ATTACK PASS VS-store round=[123] cause=15 bytes=unchanged$')" -eq 3
printf '%s\n' "$attack_output" | grep -Fxq 'STAGE2-SYSCALL-ATTACK SUMMARY: PASS 3/3 checks (3 rounds x 1 case)'
echo 'Linux Guest Stage2Virt syscall attack test PASS'
