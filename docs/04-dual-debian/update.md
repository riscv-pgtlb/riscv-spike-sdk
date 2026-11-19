# 自动更新双 Debian 工具

先正常关闭内层和外层 Debian，退出运行它们的 QEMU。在服务器执行：

```sh
make debian-update
```

默认更新 `images/debian/debian-host.raw`、`images/debian/debian-guest.raw`。
其他磁盘需要明确指定路径，例如：

```sh
make debian-update \
  DEBIAN_HOST_DISK="/path/to/debian-host.raw" \
  DEBIAN_GUEST_DISK="/path/to/debian-guest.raw"
```

执行步骤：

1. 检查两盘存在、可读写、相互独立，并阻止更新命令同时操作同一磁盘。
2. 用暂停 CPU 的 QEMU 接入两盘，检查写入占用；磁盘被其他 QEMU 占用则停止。
3. 校验构建产物并**重新打包**外层、内层工具。
4. 依次**启动两次维护虚拟机**，安装外层和内层工具；安装前校验工具包。
5. 检查安装成功标记、脚本退出码和 QEMU 退出状态，完成后输出 `DUAL DEBIAN UPDATE PASS`。

> 1. 维护启动均使用 host 内核；guest 安装器使用 `--maintenance`。
> 2. 无需登录 Debian、提供密码、启动下载服务或预装更新命令。
> 3. 操作期间不要启动使用这两块磁盘的其他虚拟机。
> 4. 更新保留账号、密码、主机名、时区和 fstab，只安装工具包覆盖的文件，包括外层磁盘中的 guest 内核。
> 5. 不编译组件，不更新服务器上的 host 内核、固件或 QEMU，不自动运行完整回归。

每次日志保存在独立的 `build/debian-updates/update-*/`：

- `status.json`：磁盘路径、已完成的层及失败原因。
- `update-host.log`、`update-guest.log`：维护虚拟机的串口输出。
- `setup.tar`、`setup/`：本次更新使用的脚本、工具包和校验清单。

两盘不是事务式更新。中途失败会停止并报告已完成的层，不自动回滚。
更新后用相同磁盘参数启动双 Debian，再执行 `test-virt-debian-all /dev/vdb` 验证。

新版安装器会保存文件清单和内容版本，更新状态中记录两层版本。

推荐更新后运行 `make pmpvirt-test`，自动核对服务器当前预期版本及磁盘内实际文件；详见 [安装后工具版本校验](tool-versions.md)。
