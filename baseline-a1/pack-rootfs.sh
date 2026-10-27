#!/bin/bash
set -euo pipefail

TARGET_DIR="${1:-$HOME/work/riscv-spike-sdk/rootfs/buildroot_initramfs/target}"
OUT_IMG="${2:-$HOME/work/my_core_files/rootfs-devtmpfs.cpio.gz}"

# 解析绝对路径
TARGET_ABS=$(realpath "$TARGET_DIR")
OUT_ABS=$(realpath -m "$OUT_IMG")

# 防止输出在 target 内（修正了同级路径误判的问题）
if [[ "$OUT_ABS" == "$TARGET_ABS" || "$OUT_ABS" == "$TARGET_ABS/"* ]]; then
  echo "Error: Output image ($OUT_ABS) cannot be inside target directory ($TARGET_ABS)."
  exit 1
fi

# 检查目录结构
for d in bin sbin etc; do
  if [ ! -d "$TARGET_ABS/$d" ]; then
    echo "Error: Target directory missing required folder: $d"
    exit 1
  fi
done

# 应用 inittab 修复
cp -f "$(dirname "$0")/inittab" "$TARGET_ABS/etc/inittab"

# 打包到临时文件并验证（防止冲突并在失败时自动清理）
TMP_IMG=$(mktemp "${OUT_ABS}.tmp.XXXXXX")
trap 'rm -f -- "$TMP_IMG"' EXIT

cd "$TARGET_ABS"
(
  set -o pipefail
  find . -print0 | cpio --null -o -H newc --owner=0:0 | gzip -n > "$TMP_IMG"
)

if ! gzip -t "$TMP_IMG"; then
  echo "Error: gzip validation failed."
  exit 1
fi

mv "$TMP_IMG" "$OUT_ABS"
# 取消 trap，防止移走后把最终文件误删
trap - EXIT
echo "Successfully packed rootfs to $OUT_ABS"
