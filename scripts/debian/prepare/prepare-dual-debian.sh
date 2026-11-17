#!/usr/bin/env bash
set -euo pipefail
umask 077

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$project_dir"

for tool in qemu-img sha512sum tar openssl python3 flock; do
    command -v "$tool" >/dev/null || {
        echo "Missing command: $tool" >&2
        exit 1
    }
done

base_dir="$project_dir/images/debian"
base_name=debian-13-nocloud-riscv64.qcow2
base_image="$base_dir/$base_name"

mkdir -p "$project_dir/build"
exec 8>"$project_dir/build/debian-operation.lock"
flock -n 8 || { echo 'Another Debian prepare, update or VM run is active' >&2; exit 1; }
recreate="${DEBIAN_RECREATE:-0}"
python3 -B scripts/debian/prepare/disk-targets.py check --base "$base_dir" --recreate "$recreate"

test -r "$base_image"
test -r "$base_dir/SHA512SUMS"

# 明确提取目标镜像的校验条目，避免“没有文件被验证”。
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

bash scripts/debian/install/pack-tools.sh

# 先在临时目录完成初始化，成功后才替换固定路径。
deploy_dir=$(mktemp -d "$base_dir/prepared-XXXXXX")
trap 'echo "Preparation failed; partial files retained at: $deploy_dir" >&2' ERR

stage_dir="$deploy_dir/setup"
mkdir "$stage_dir"

install -m 0755 \
    scripts/debian/prepare/init-system.sh \
    scripts/debian/prepare/provision-system.sh \
    "$stage_dir/"

install -m 0644 \
    build/debian-host-transfer/dual-debian-tools.tar.gz \
    build/debian-host-transfer/debian-guest-tools.tar.gz \
    build/debian-host-transfer/HOST-VERSION \
    build/debian-host-transfer/GUEST-VERSION \
    build/debian-host-transfer/SHA256SUMS \
    "$stage_dir/"

# 交互读取密码，只将密码哈希写入权限受限的文件。
echo "Set the root password for BOTH new Debian systems."
echo "The following prompts are handled by openssl."
openssl passwd -6 > "$stage_dir/root-password.hash"
test -s "$stage_dir/root-password.hash"

qemu-img convert -p -f qcow2 -O raw \
    "$base_image" "$deploy_dir/debian-host.raw"
qemu-img convert -p -f qcow2 -O raw \
    "$base_image" "$deploy_dir/debian-guest.raw"

tar -C "$stage_dir" -cf "$deploy_dir/setup.tar" .

printf '%s  %s\n' "$checksum" "$base_name" \
    > "$deploy_dir/BASE-SHA512SUM"

python3 "$project_dir/scripts/debian/prepare/provision-dual-debian.py" "$deploy_dir"
python3 -B scripts/debian/prepare/disk-targets.py publish \
    --base "$base_dir" --staged "$deploy_dir" --recreate "$recreate"

echo "DEBIAN DEPLOYMENT PASS"
echo "Deployment logs and materials: $deploy_dir"
echo "Start this environment with:"
echo 'make run-virt-dual-debian'
