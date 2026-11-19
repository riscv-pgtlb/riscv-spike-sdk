#!/bin/sh
set -eu

# 1. 检查角色和元数据
role=${1:-}
bundle=${2:-}
case "$role" in host|guest) ;; *) exit 2 ;; esac
test "$(id -u)" -eq 0
root=${DESTDIR:-}
root=${root%/}
metadata="$bundle/metadata/$role"
for file in ROLE VERSION FILES.tsv INPUTS.SHA256SUMS; do
    test -r "$metadata/$file" || { echo "Missing tool metadata: $metadata/$file" >&2; exit 1; }
done
test "$(cat "$metadata/ROLE")" = "$role"
# 验证元数据的版本标识
version=$(cat "$metadata/VERSION")
actual=$(cat "$metadata/ROLE" "$metadata/FILES.tsv" "$metadata/INPUTS.SHA256SUMS" | sha256sum)
test "${actual%% *}" = "$version" || { echo 'Tool metadata checksum mismatch' >&2; exit 1; }

# 校验输入文件: Check every source before installing any file.
(cd "$bundle" && sha256sum --check --strict "$metadata/INPUTS.SHA256SUMS")
awk -F '\t' '
    NF != 4 || length($1) != 64 || $1 ~ /[^0-9a-f]/ ||
    ($2 != "0755" && $2 != "0644") ||
    $3 !~ /^[A-Za-z0-9_.\/-]+$/ || $3 ~ /(^|\/)\.\.(\/|$)/ || $3 ~ /^\// ||
    $4 !~ /^\/(usr\/bin\/|usr\/local\/bin\/|usr\/local\/libexec\/virt-tools\/|opt\/guest\/|etc\/systemd\/system\/|var\/lib\/virt-tools\/)/ ||
    $4 ~ /(^|\/)\.\.(\/|$)/ { bad=1 }
    END { exit (bad || NR == 0) }
' "$metadata/FILES.tsv" || { echo 'Invalid installed-file manifest' >&2; exit 1; }
tab=$(printf '\t')
while IFS="$tab" read -r expected mode source destination; do
    actual=$(sha256sum "$bundle/$source")
    test "${actual%% *}" = "$expected" || { echo "Input mismatch: $source" >&2; exit 1; }
done < "$metadata/FILES.tsv"

# 安装
while IFS="$tab" read -r expected mode source destination; do
    install -d "$(dirname -- "$root$destination")"
    install -m "$mode" "$bundle/$source" "$root$destination"
done < "$metadata/FILES.tsv"

install -d "$root/var/lib/virt-tools"
for file in ROLE VERSION FILES.tsv INPUTS.SHA256SUMS; do
    install -m 0644 "$metadata/$file" "$root/var/lib/virt-tools/$file"
done

# 检查安装结果
sh "$bundle/scripts/debian/common/check-virt-tools.sh" \
    --root "${root:-/}" --role "$role" --expect-version "$version"
