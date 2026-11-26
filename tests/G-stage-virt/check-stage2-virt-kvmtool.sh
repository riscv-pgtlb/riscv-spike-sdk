#!/bin/sh
set -eu

LKVM=${STAGE2_VIRT_LKVM:-/usr/bin/lkvm}
MISSING_KERNEL=/no-such-stage2-virt-smoke-kernel
GPA=0x80000000
SIZE=0x1000
RAM_MIB=16

case "$(uname -m)" in
	riscv64) ;;
	*) echo 'Run this test in the RISC-V Host Linux.' >&2; exit 1 ;;
esac

test -c /dev/kvm || { echo '/dev/kvm missing.' >&2; exit 1; }
test -x "$LKVM" || { echo "lkvm missing or not executable: $LKVM" >&2; exit 1; }
test ! -e "$MISSING_KERNEL" || {
	echo "Reserved missing-kernel path unexpectedly exists: $MISSING_KERNEL" >&2
	exit 1
}

log=$(mktemp "${TMPDIR:-/tmp}/stage2-virt-kvmtool.XXXXXX")
trap 'rm -f "$log"' EXIT HUP INT TERM

echo "Kvmtool Stage2Virt ioctl smoke: GPA=$GPA size=$SIZE"
if "$LKVM" run \
	--stage2-virt \
	--stage2-virt-gpa "$GPA" \
	--stage2-virt-size "$SIZE" \
	--name "stage2-virt-smoke-$$" \
	-m "$RAM_MIB" \
	-c 1 \
	-k "$MISSING_KERNEL" >"$log" 2>&1; then
	cat "$log"
	echo 'lkvm unexpectedly started without the deliberately missing kernel.' >&2
	exit 1
fi

cat "$log"
grep -Fq 'Stage2Virt enabled for GPA [0x80000000, 0x80001000)' "$log" || {
	echo 'Missing successful Stage2Virt ioctl result.' >&2
	exit 1
}
grep -Fq "Unable to open kernel $MISSING_KERNEL" "$log" || {
	echo 'lkvm did not reach the expected post-ioctl missing-kernel failure.' >&2
	exit 1
}

echo 'Kvmtool Stage2Virt ioctl smoke PASS'
