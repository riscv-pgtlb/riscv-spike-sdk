#!/bin/sh
set -eu
# Only the dedicated regression boot flag opts into automatic testing/shutdown.
case " $(cat /proc/cmdline) " in
    *' virt_regression=1 '*) ;;
    *) exit 0 ;;
esac
if /usr/bin/check-virt-guest; then
    echo 'VIRT-REGRESSION GUEST SHUTDOWN'
    /sbin/poweroff
else
    echo 'VIRT-REGRESSION FAIL guest checks'
    exit 1
fi
