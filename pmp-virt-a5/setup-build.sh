#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
PACKAGE="$PWD"
LINUX_PARENT="$HOME/work/linux-pmp-virt-test-src"
FW_PARENT="$HOME/work/opensbi-pmp-virt-test-src"
LINUX_SRC="$HOME/work/linux-pmp-virt-user-src"
LINUX_OUT="$HOME/work/linux-build-pmp-virt-user"
FW_SRC="$HOME/work/opensbi-pmp-virt-user-src"
FW_OUT="$HOME/work/opensbi-build-pmp-virt-user"
CROSS="$HOME/work/riscv-spike-sdk/rootfs/buildroot_initramfs/host/bin/riscv64-linux-"
for directory in "$LINUX_SRC" "$LINUX_OUT" "$FW_SRC" "$FW_OUT"; do
    if [[ -e "$directory" ]]; then
        echo "Already exists; stop and inspect: $directory" >&2
        exit 1
    fi
done
git -C "$LINUX_PARENT" diff --quiet
git -C "$LINUX_PARENT" diff --cached --quiet
git -C "$FW_PARENT" diff --quiet
git -C "$FW_PARENT" diff --cached --quiet
{
    git -C "$LINUX_PARENT" rev-parse HEAD
    git -C "$FW_PARENT" rev-parse HEAD
} > parents.txt
git -C "$LINUX_PARENT" worktree add -b pmp-virt-user-test "$LINUX_SRC" HEAD
python3 prepare.py linux
LINUX_SRC="$LINUX_SRC" LINUX_OUT="$LINUX_OUT" bash build-linux.sh
git -C "$FW_PARENT" worktree add -b pmp-virt-user-test "$FW_SRC" HEAD
python3 prepare.py firmware
git -C "$LINUX_SRC" diff --check
git -C "$FW_SRC" diff --check
make -C "$FW_SRC" O="$FW_OUT" PLATFORM=generic PLATFORM_RISCV_XLEN=64 \
    PLATFORM_DEFCONFIG=pmp_virt_seal_defconfig CROSS_COMPILE="$CROSS" \
    FW_TEXT_START=0x80000000 FW_JUMP_ADDR=0x80200000 -j8
grep -q '^CONFIG_PMP_VIRT_SEAL=y$' "$FW_OUT/platform/generic/kconfig/.config"
mkdir -p build
"${CROSS}gcc" -O2 -Wall -Wextra -static user.c -o build/pv-user-test
STAGE=$(mktemp -d "$PACKAGE/build/overlay.XXXXXX")
trap 'rm -f -- "$STAGE/pv-user-test"; rmdir -- "$STAGE"' EXIT
cp build/pv-user-test "$STAGE/pv-user-test"
chmod 755 "$STAGE/pv-user-test"
(
    cd "$STAGE"
    printf './pv-user-test\0' | cpio --null -o -H newc --owner=0:0 | gzip -n
) > build/user-overlay.cpio.gz
# Initramfs supports concatenated gzip/newc archives; baseline is unchanged.
cat "$HOME/work/my_core_files/rootfs-devtmpfs.cpio.gz" \
    build/user-overlay.cpio.gz > build/rootfs-user-test.cpio.gz
gzip -t build/rootfs-user-test.cpio.gz
sha256sum "$LINUX_OUT/arch/riscv/boot/Image" "$LINUX_OUT/.config" \
    "$FW_OUT/platform/generic/firmware/fw_jump.bin" \
    build/pv-user-test build/rootfs-user-test.cpio.gz | tee artifacts.sha256
echo 'Build completed. Boot separately with: bash run.sh'
