#!/bin/sh
# Shared evidence parser: Debian, Buildroot and the server use identical rules.
set -eu
awk '
function address(s) {
    sub(/^[^=]*=/, "", s); s=tolower(s); sub(/^0x/, "", s)
    sub(/^0+/, "", s); return s == "" ? "0" : s
}
# Host printk can interrupt an in-flight guest serial line. Only these known
# host probe records may be removed from the middle of a pending result.
function host_record(s) {
    sub(/^\[[[:space:]]*[0-9]+([.][0-9]+)?\][[:space:]]*/, "", s)
    return s ~ /^PMP[.]Virt USER PTE: flags=[0-9a-fA-F]+ required=[0-9a-fA-F]+ user=0 write=0$/ ||
           s ~ /^PMP[.]Virt TEST PASS guest (BEGIN|COMPLETE) same-page HS RX\/U0 execute cause=1 pc=[0-9a-fA-F]+ tval=[0-9a-fA-F]+$/ ||
           s ~ /^PMP[.]Virt GUEST HOST CHECK: phase=[01] HPA=[0-9a-fA-F]+ cause=1$/
}
function complete_result(s) {
    return s ~ /^PMP[.]Virt VS (BEFORE|AFTER) PASS: GPA=(0x)?[0-9a-fA-F]+ result=42$/ ||
           s ~ /^PMP[.]Virt VS\/HS BEGIN: GPA=0x[0-9a-fA-F]+ HPA=0x[0-9a-fA-F]+ cause=1$/ ||
           s ~ /^PMP[.]Virt VS\/HS COMPLETE: GPA=0x[0-9a-fA-F]+ HPA=0x[0-9a-fA-F]+ guest_report=42$/ ||
           s ~ /^PMP[.]Virt VS-HS-VS SAME-PAGE PASS: GPA=(0x)?[0-9a-fA-F]+$/
}
function advance(want) { if (stage != want-1) bad=1; stage=want }
{
    gsub(/\r/, "")
    sub(/^\[[[:space:]]*[0-9]+([.][0-9]+)?\][[:space:]]*/, "")
    sub(/^[[:space:]]*Info: /, "")
    if ($0 ~ /PMP[.]Virt .*FAIL|VIRT-REGRESSION FAIL|Kernel panic|Oops:/) bad=1
    if (pending != "") {
        if (host_record($0) || $0 ~ /^[[:space:]]*$/) {
            if (++interruptions > 16) bad=1
            next
        }
        $0=pending $0
        pending=""
    }
    # A timestamp followed by a known host record may interrupt a guest line.
    if (match($0, /\[[[:space:]]*[0-9]+([.][0-9]+)?\][[:space:]]+PMP[.]Virt /)) {
        prefix=substr($0, 1, RSTART-1)
        injected=substr($0, RSTART)
        if (prefix ~ /^PMP[.]Virt (VS |VS-HS-VS |VS\/HS )/ && host_record(injected)) {
            if (complete_result(prefix)) {
                # A bare CR may separate a complete guest result from printk.
                # Parse that complete record now; do not await a continuation.
                $0=prefix
            } else {
                pending=prefix
                interruptions=0
                if (length(pending)>256) bad=1
                next
            }
        }
    }
    if ($0 ~ /VIRT-REGRESSION GUEST (PASS|SHUTDOWN)/ && stage != 5) bad=1
    if ($0 ~ /^PMP[.]Virt VS BEFORE PASS: GPA=(0x)?[0-9a-fA-F]+ result=42$/) {
        advance(1); gpa=address($5); if (gpa=="0") bad=1
    } else if ($0 ~ /^PMP[.]Virt VS\/HS BEGIN: GPA=0x[0-9a-fA-F]+ HPA=0x[0-9a-fA-F]+ cause=1$/) {
        advance(2); if (address($4)!=gpa) bad=1
        hpa=address($5); if (hpa=="0") bad=1
    } else if ($0 ~ /^PMP[.]Virt VS AFTER PASS: GPA=(0x)?[0-9a-fA-F]+ result=42$/) {
        advance(3); if (address($5)!=gpa) bad=1
    } else if ($0 ~ /^PMP[.]Virt VS\/HS COMPLETE: GPA=0x[0-9a-fA-F]+ HPA=0x[0-9a-fA-F]+ guest_report=42$/) {
        advance(4); if (address($4)!=gpa || address($5)!=hpa) bad=1
    } else if ($0 ~ /^PMP[.]Virt VS-HS-VS SAME-PAGE PASS: GPA=(0x)?[0-9a-fA-F]+$/) {
        advance(5); if (address($5)!=gpa) bad=1
    } else if ($0 ~ /^PMP[.]Virt (VS BEFORE|VS AFTER|VS\/HS BEGIN|VS\/HS COMPLETE|VS-HS-VS SAME-PAGE)/) {
        bad=1
    }
}
END { exit (bad || pending != "" || stage != 5) }
' "$@"
