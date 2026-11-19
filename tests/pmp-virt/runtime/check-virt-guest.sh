#!/bin/sh
set -eu
case "$(uname -r)" in
    *-virt-kvm-guest|*-virt-kvm-guest+|*-virt-kvm-guest-*) ;;
    *) echo 'Guest kernel required.' >&2; exit 1 ;;
esac
uname -r
head -n 5 /proc/meminfo
memory=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
test "$memory" -gt 131072
before=$(awk '{ print int($1) }' /proc/uptime)
sleep 2
after=$(awk '{ print int($1) }' /proc/uptime)
test "$after" -ge "$((before + 2))"
echo 'VIRT-REGRESSION GUEST PASS'
