#!/usr/bin/env bash
set -euo pipefail
umask 077

# 1. 检查环境和镜像
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$project_dir"

# 提前检查主要依赖命令
for tool in qemu-img sha512sum tar openssl python3 flock; do
    command -v "$tool" >/dev/null || {
        echo "Missing command: $tool" >&2
        exit 1
    }
done

# 基础镜像目录、文件名和完整路径
base_dir="$project_dir/images/debian"
base_name=debian-13-nocloud-riscv64.qcow2
base_image="$base_dir/$base_name"

# 加锁，防止并发操作
mkdir -p "$project_dir/build"
exec 8>"$project_dir/build/debian-operation.lock"   # 锁
flock -n 8 || { echo 'Another Debian prepare, update or VM run is active' >&2; exit 1; }

# make debian-prepare DEBIAN_RECREATE=1 是否重建
recreate="${DEBIAN_RECREATE:-0}"

# 在生成新磁盘前检查目标状态。
# 已有文件如何处理、哪些状态被拒绝，由 disk-targets.py 实现
python3 -B scripts/debian/prepare/disk-targets.py check --base "$base_dir" --recreate "$recreate"

# 确认基础镜像和校验清单可读
test -r "$base_image"
test -r "$base_dir/SHA512SUMS"

# 校验基础镜像
checksum=$(awk -v name="$base_name" \
    '$2 == name || $2 == "*" name { print $1 }' \
    "$base_dir/SHA512SUMS")
[[ "$checksum" =~ ^[[:xdigit:]]{128}$ ]] || {
    echo "Missing or ambiguous base image checksum" >&2
    exit 1
}
(
    cd "$base_dir"
    printf '%s  %s\n' "$checksum" "$base_name" | sha512sum -c -
)

# 2. 打包后续部署需要的工具及版本、校验信息
# 预期输出位于 build/debian-tools/
bash scripts/debian/install/pack-tools.sh

# 3. 创建两套磁盘
# 先在临时目录完成初始化，成功后才替换固定路径。
deploy_dir=$(mktemp -d "$base_dir/prepared-XXXXXX")
trap 'echo "Preparation failed; partial files retained at: $deploy_dir" >&2' ERR

# 收集初始化材料：两个初始化脚本、工具包、版本记录和校验清单
stage_dir="$deploy_dir/setup"
mkdir "$stage_dir"

install -m 0755 \
    scripts/debian/prepare/init-system.sh \
    scripts/debian/prepare/provision-system.sh \
    "$stage_dir/"

install -m 0644 \
    build/debian-tools/debian-host-tools.tar.gz \
    build/debian-tools/debian-guest-tools.tar.gz \
    build/debian-tools/HOST-VERSION \
    build/debian-tools/GUEST-VERSION \
    build/debian-tools/SHA256SUMS \
    "$stage_dir/"

# 交互读取密码，只将密码哈希写入权限受限的文件。
echo "Set the root password for BOTH new Debian systems."
echo "The following prompts are handled by openssl."
openssl passwd -6 > "$stage_dir/root-password.hash"
test -s "$stage_dir/root-password.hash"

# 生成两套独立磁盘
qemu-img convert -p -f qcow2 -O raw \
    "$base_image" "$deploy_dir/debian-host.raw"
qemu-img convert -p -f qcow2 -O raw \
    "$base_image" "$deploy_dir/debian-guest.raw"

tar -C "$stage_dir" -cf "$deploy_dir/setup.tar" .

printf '%s  %s\n' "$checksum" "$base_name" \
    > "$deploy_dir/BASE-SHA512SUM"

# 初始化磁盘；成功后，将暂存结果发布到正式目标位置
python3 "$project_dir/scripts/debian/prepare/provision-dual-debian.py" "$deploy_dir"
python3 -B scripts/debian/prepare/disk-targets.py publish \
    --base "$base_dir" --staged "$deploy_dir" --recreate "$recreate"

echo "DEBIAN DEPLOYMENT PASS"
echo "Deployment logs and materials: $deploy_dir"
echo "Start this environment with:"
echo 'make run-virt-dual-debian'
