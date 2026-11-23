#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
QEMU=${QEMU:-}
RISCV=${RISCV:-"$ROOT/toolchain"}
CC=${CC:-"$RISCV/bin/riscv64-unknown-linux-gnu-gcc"}
LD=${LD:-"$RISCV/bin/riscv64-unknown-linux-gnu-ld"}
SOURCE=$ROOT/repo/qemu/tests/tcg/riscv64/stage2-virt.S
LINKER=$ROOT/repo/qemu/tests/tcg/riscv64/semihost.ld

if [ -z "$QEMU" ]; then
    for candidate in \
        "$ROOT/build/qemu/qemu-system-riscv64" \
        "$ROOT/build/virt-kvm/out/qemu/qemu-system-riscv64" \
        "$RISCV/bin/qemu-system-riscv64"; do
        if [ -x "$candidate" ]; then
            QEMU=$candidate
            break
        fi
    done
fi

test -x "$CC" || { echo "missing RISC-V compiler: $CC" >&2; exit 1; }
test -x "$LD" || { echo "missing RISC-V linker: $LD" >&2; exit 1; }
test -x "$QEMU" || { echo "missing qemu-system-riscv64; build QEMU first" >&2; exit 1; }
test -f "$SOURCE" || { echo "missing Stage2Virt source: $SOURCE" >&2; exit 1; }
test -f "$LINKER" || { echo "missing semihost linker script: $LINKER" >&2; exit 1; }

work=$(mktemp -d "${TMPDIR:-/tmp}/stage2-virt-qemu.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

"$CC" -march=rv64imah -mabi=lp64 -g -Og -c "$SOURCE" \
    -Wa,--noexecstack -o "$work/stage2-virt.o"
"$LD" -T "$LINKER" "$work/stage2-virt.o" -o "$work/stage2-virt"

echo "QEMU Stage2Virt positive test: x-stage2-virt=on"
timeout "${STAGE2_VIRT_TIMEOUT:-30}" "$QEMU" -M virt -display none -semihosting \
    -cpu "rv64,h=true,pmp=false,x-stage2-virt=on" \
    -device "loader,file=$work/stage2-virt"

echo "QEMU Stage2Virt negative test: x-stage2-virt=off"
set +e
timeout "${STAGE2_VIRT_TIMEOUT:-30}" "$QEMU" -M virt -display none -semihosting \
    -cpu "rv64,h=true,pmp=false,x-stage2-virt=off" \
    -device "loader,file=$work/stage2-virt"
negative_rc=$?
set -e
if [ "$negative_rc" -eq 0 ] || [ "$negative_rc" -eq 124 ] || [ "$negative_rc" -ge 128 ]; then
    echo "Stage2Virt negative control did not fail as expected (rc=$negative_rc)" >&2
    exit 1
fi

echo "QEMU Stage2Virt语义测试 PASS"
