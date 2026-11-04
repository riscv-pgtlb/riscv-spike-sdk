#!/usr/bin/env bash
set -euo pipefail
SRC="${LINUX_SRC:-$HOME/work/linux-pmp-virt-src}"
OUT="${LINUX_OUT:-$HOME/work/linux-build-pmp-virt}"
SDK="${SDK_DIR:-$HOME/work/riscv-spike-sdk}"
CROSS="${CROSS_COMPILE:-$SDK/rootfs/buildroot_initramfs/host/bin/riscv64-linux-}"
test -f "$SRC/Makefile"
test -x "${CROSS}gcc"
mkdir -p "$OUT"
if [[ ! -e "$OUT/.config" ]]; then
    cp "$SDK/baseline-a1/linux.config" "$OUT/.config"
fi
# Research kernel: static code, one active hart. Never overwrite baseline Image.
for symbol in MODULES JUMP_LABEL FUNCTION_TRACER FUNCTION_GRAPH_TRACER \
    DYNAMIC_FTRACE FTRACE KPROBES LIVEPATCH BPF_JIT RANDOMIZE_BASE \
    KEXEC KEXEC_FILE KGDB; do
    "$SRC/scripts/config" --file "$OUT/.config" --disable "$symbol"
done
"$SRC/scripts/config" --file "$OUT/.config" --set-str LOCALVERSION '-pmpvirt-user'
"$SRC/scripts/config" --file "$OUT/.config" --disable LOCALVERSION_AUTO
"$SRC/scripts/config" --file "$OUT/.config" --set-str INITRAMFS_SOURCE ''
make -C "$SRC" O="$OUT" ARCH=riscv CROSS_COMPILE="$CROSS" olddefconfig
for symbol in MODULES JUMP_LABEL FTRACE KPROBES LIVEPATCH BPF_JIT RANDOMIZE_BASE; do
    if grep -Eq "^CONFIG_${symbol}=(y|m)$" "$OUT/.config"; then
        echo "Unexpected dynamic-code config remains: $symbol" >&2
        exit 1
    fi
done
make -C "$SRC" O="$OUT" ARCH=riscv CROSS_COMPILE="$CROSS" -j8 Image
"${CROSS}gcc" --version | head -1
sha256sum "$OUT/arch/riscv/boot/Image" "$OUT/.config"
