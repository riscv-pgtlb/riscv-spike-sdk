# 双 Debian 启动与回归

## 一条命令执行已有完整测试

已有磁盘和测试工具时，在服务器执行 

```sh
make pmpvirt-test
```

按提示输入外层 root 密码。

入口先做逻辑与产物检查，再启动、登录、调用完整套件、关机并汇总证据，不重建磁盘。

> 参数、日志及无人值守方式见 [统一测试说明](../03-pmp-virt-kvm/test-suite.md)。下面保留日常启动和手动测试步骤。

## 启动外层

在服务器项目根目录执行：

```sh
make virt-verify
make run-virt-dual-debian
```

默认使用 `images/debian/debian-host.raw` 和 `debian-guest.raw`。

如需其他磁盘，启动和更新都必须指定同一组 `DEBIAN_HOST_DISK`、`DEBIAN_GUEST_DISK`。

准备或更新正在运行时不要启动虚拟机。

使用准备阶段设置的 root 密码登录外层，检查：

```sh
hostname
uname -r
findmnt -n -o SOURCE /
systemctl is-system-running
systemctl --failed --no-pager
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
```

自动初始化后的外层主机名为 `debian-host`，内核包含 `pmpvirt-kvm-host`，根目录来自 `/dev/vda1`。
确认 `/dev/vdb` 及其分区未挂载。

## 正常启动内层

在外层执行：

```sh
run-debian-guest
```

内层使用准备时设置的 root 密码登录，主机名为 `debian-guest`，`uname -r` 包含 `virt-kvm-guest`。
正常模式不带测试参数，不会自动测试后关机。
内层执行 `poweroff`，看到 KVM 正常结束后返回外层。

## 完整回归

内层未运行时，在外层执行：

```sh
test-virt-debian-all /dev/vdb
```

流程为外层保护检查 → 带 `virt_regression=1` 启动内层 → systemd 服务自动检查并关机 → 返回外层复测。
最终应输出：

```text
VIRT-REGRESSION ALL PASS
```

`Evidence:` 显示的日志目录位于外层磁盘内的 `/var/log/virt-regression/debian-*/`，包含
`guest-console.log` 和去除回车的 `guest-console-clean.log`。这不是服务器上的初始化/更新日志。

## 关机

先在内层执行 `poweroff`，返回外层后再执行 `poweroff`，等待 QEMU 退出。
关闭两层后才执行服务器的 `make debian-update` 或显式重建命令。
