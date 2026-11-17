#!/bin/sh
set -eu

root= expected= required_role=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --root|--role|--expect-version)
            test "$#" -ge 2 || { echo "Missing value: $1" >&2; exit 2; }
            case "$1" in --root) root=$2 ;; --role) required_role=$2 ;; --expect-version) expected=$2 ;; esac
            shift 2 ;;
        *) echo "Usage: $0 [--expect-version SHA256] [--role host|guest] [--root DIRECTORY]" >&2; exit 2 ;;
    esac
done
root=${root%/}
metadata="$root/var/lib/virt-tools"
for file in ROLE VERSION FILES.tsv INPUTS.SHA256SUMS; do
    test -r "$metadata/$file" || {
        echo "VIRT TOOLS CHECK FAIL: missing $metadata/$file; install the current tools package" >&2
        exit 1
    }
done
role=$(cat "$metadata/ROLE")
case "$role" in host|guest) ;; *) echo 'VIRT TOOLS CHECK FAIL: invalid installed role' >&2; exit 1 ;; esac
test -z "$required_role" || test "$required_role" = "$role" || { echo 'VIRT TOOLS CHECK FAIL: installed tool role mismatch' >&2; exit 1; }
version=$(cat "$metadata/VERSION")
actual=$(cat "$metadata/ROLE" "$metadata/FILES.tsv" "$metadata/INPUTS.SHA256SUMS" | sha256sum)
test "${actual%% *}" = "$version" || { echo 'VIRT TOOLS CHECK FAIL: installed metadata changed' >&2; exit 1; }

# Guest regressions receive the paired version through their kernel command line.
# --root checks a staged filesystem without using this boot's command line.
if [ "$role" = guest ] && [ -z "$root" ] && [ -z "$expected" ]; then
    for token in $(cat /proc/cmdline); do
        case "$token" in
            virt_tools_version=*)
                test -z "$expected" || { echo 'Duplicate expected tool version' >&2; exit 1; }
                expected=${token#virt_tools_version=} ;;
        esac
    done
fi
if [ -n "$expected" ] && [ "$expected" != "$version" ]; then
    echo "VIRT TOOLS VERSION MISMATCH role=$role expected=$expected installed=$version" >&2
    exit 1
fi

failed=0
tab=$(printf '\t')
while IFS="$tab" read -r hash mode source destination; do
    target="$root$destination"
    if [ ! -f "$target" ] || [ -L "$target" ]; then
        echo "VIRT TOOLS FILE FAIL: $destination missing or not a regular file" >&2
        failed=1
        continue
    fi
    actual=$(sha256sum "$target")
    if [ "${actual%% *}" != "$hash" ]; then
        echo "VIRT TOOLS FILE FAIL: $destination checksum mismatch" >&2
        failed=1
    fi
    if [ "$(stat -c %a "$target")" != "${mode#0}" ]; then
        echo "VIRT TOOLS FILE FAIL: $destination mode mismatch (expected $mode)" >&2
        failed=1
    fi
done < "$metadata/FILES.tsv"
test "$failed" -eq 0
echo "VIRT TOOLS VERSION PASS role=$role version=$version"
echo "VIRT TOOLS CHECK PASS: $role"
