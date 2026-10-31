#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

BASE_ROOTFS="images/base/rootfs.cpio.gz"
KERNEL="build/linux/arch/riscv/boot/Image"
LKVM="repo/kvmtool/lkvm-static"
MODULES="build/kvm-modules/lib/modules"
RELEASE="$(cat build/linux/include/config/kernel.release)"

# 检查输入，防止缺少文件时生成不完整镜像。
for path in "$BASE_ROOTFS" "$KERNEL" "$LKVM" \
    "$MODULES/$RELEASE/kernel/arch/riscv/kvm/kvm.ko"; do
    test -r "$path" || {
        echo "Missing input: $path" >&2
        exit 1
    }
done
gzip -t "$BASE_ROOTFS"

mkdir -p build images/kvm

# 每次使用全新的暂存目录，避免混入上次构建的文件。
STAGE="$(mktemp -d "$PROJECT_DIR/build/rootfs-pack.XXXXXX")"
trap 'rm -rf -- "$STAGE"' EXIT

mkdir -p "$STAGE/root/usr/bin" \
    "$STAGE/root/lib/modules" \
    "$STAGE/root/opt/guest"

cp "$LKVM" "$STAGE/root/usr/bin/lkvm"
# 将 guest 启动入口安装到外层系统。
install -m 0755 scripts/run-guest.sh "$STAGE/root/usr/bin/run-guest"
install -m 0755 scripts/run-debian.sh "$STAGE/root/usr/bin/run-debian"
cp -a "$MODULES/$RELEASE" "$STAGE/root/lib/modules/"
cp "$KERNEL" "$STAGE/root/opt/guest/Image"
cp "$BASE_ROOTFS" "$STAGE/root/opt/guest/rootfs.cpio.gz"

# 打包新增文件，归档中的文件属主统一为 root。
(
    cd "$STAGE/root"
    find . -print0 |
        cpio --null -o -H newc --owner=0:0 |
        gzip -n > "$STAGE/extra.cpio.gz"
)

# initramfs 支持连续的压缩归档：先加载基线，再加载新增文件。
cat "$BASE_ROOTFS" "$STAGE/extra.cpio.gz" > "$STAGE/rootfs.cpio.gz"
gzip -t "$STAGE/rootfs.cpio.gz"

# 输出候选镜像，保留默认启动镜像。
mv "$STAGE/rootfs.cpio.gz" images/kvm/rootfs-kvm-new.cpio.gz
echo "Created: images/kvm/rootfs-kvm-new.cpio.gz"
