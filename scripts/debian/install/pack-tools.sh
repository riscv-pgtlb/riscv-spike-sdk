#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$project_dir"

python3 scripts/build/virt-kvm.py verify

output_dir="$project_dir/build/debian-host-transfer"
mkdir -p "$output_dir"
stage_dir=$(mktemp -d "$project_dir/build/debian-tools.XXXXXX")
trap 'rm -rf -- "$stage_dir"' EXIT

python3 scripts/debian/install/tool-manifest.py --output "$stage_dir"
tar -C "$stage_dir/host" -czf "$stage_dir/dual-debian-tools.tar.gz" .
tar -C "$stage_dir/guest" -czf "$stage_dir/debian-guest-tools.tar.gz" .

(
    cd "$stage_dir"
    sha256sum dual-debian-tools.tar.gz debian-guest-tools.tar.gz \
        HOST-VERSION GUEST-VERSION > SHA256SUMS
)

for file in dual-debian-tools.tar.gz debian-guest-tools.tar.gz \
    HOST-VERSION GUEST-VERSION SHA256SUMS; do
    install -m 0644 "$stage_dir/$file" "$output_dir/"
done

echo "Packages created: $output_dir"
