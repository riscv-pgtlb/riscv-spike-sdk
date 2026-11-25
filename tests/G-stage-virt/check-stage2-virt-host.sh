#!/bin/sh
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
TEST_BIN=${STAGE2_VIRT_HOST_TEST:-${1:-}}

if [ -z "$TEST_BIN" ]; then
	for candidate in \
		"$ROOT/repo/linux/tools/testing/selftests/kvm/riscv/stage2_virt_test" \
		"/usr/bin/stage2_virt_test"; do
		if [ -x "$candidate" ]; then
			TEST_BIN=$candidate
			break
		fi
	done
fi

if [ -z "$TEST_BIN" ] || [ ! -x "$TEST_BIN" ]; then
	echo "missing stage2_virt_test; build it and copy it to Host Linux first" >&2
	exit 1
fi

echo "Host Linux Stage2Virt runtime test: $TEST_BIN"
if "$TEST_BIN"; then
	echo "Host Linux Stage2Virt selftest PASS"
	exit 0
else
	rc=$?
fi

if [ "$rc" -eq 4 ]; then
	echo "Host Linux Stage2Virt selftest SKIP"
else
	echo "Host Linux Stage2Virt selftest FAIL (rc=$rc)" >&2
fi
exit "$rc"
