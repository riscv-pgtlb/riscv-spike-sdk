# PMP.Virt 团队子模块构建与回归

核心代码直接在团队仓库中维护，SDK 不再自动应用 QEMU/Linux/OpenSBI 补丁。
配置在 `conf/pmp-virt/`，构建和启动脚本在 `scripts/`，回归在 `tests/pmp-virt/`。
旧的 `pmp-virt/` 和更早的 `pmp-virt-a5/` 内容可从历史提交恢复；历史 B1 日志移入本目录的 `validation/b1/`，原始日志和清单字节不变。

## 源码和版本

| 组件 | 团队源码 | 本轮固定提交 |
| --- | --- | --- |
| QEMU | `repo/qemu/target/riscv/` | `0ec20439ca845573db2a52e85aa34c0dca9c1731` |
| Linux host | `repo/linux/arch/riscv/` | `ab598939034057e7fdc2a4beb483a10ef4c67077` |
| OpenSBI | `repo/opensbi/lib/sbi/` 等 | `0e1a39f96b50c09978aa190a830b713a51c014c2` |

三个组件均为 `https://github.com/riscv-pgtlb/<组件名>.git` 的 `pmp-virt-b1` 分支。
子模块 gitlink 固定具体提交；`branch` 配置仅说明协作分支，构建不使用浮动的 `--remote`。
`conf/pmp-virt/sources.json` 记录源版本并与 SDK 暂存区/提交中的 gitlink 校验。
变更组件时先在组件仓库提交和推送，再更新 SDK 的 gitlink 和锁定文件，重新构建验证。

普通 guest 使用 Linux `449d48b1b99fdaa076166e200132705ac2bee711`，在 `build/virt-kvm/src/linux-guest/` 准备独立源码，不执行 host 的封存调用。它与 host 不共享输出目录。
dtc 和 kvmtool 沿用原固定子模块版本，在私有副本构建，以免交叉编译污染工作源码。
这些私有克隆借用子模块 Git 对象，在完成构建前不要清理子模块对象。
未修改的其他组件仍保持原仓库地址；后续如果确实需要修改，再迁入团队 fork。

## Ubuntu 服务器：初始化与编译

```bash
cd /home/czy/work/riscv-spike-sdk-submodules
git submodule sync -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
git submodule update --init --depth=1 -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
export CROSS_COMPILE=/home/czy/work/riscv-spike-sdk/rootfs/buildroot_initramfs/host/bin/riscv64-linux-
export BASE_ROOTFS=/home/czy/work/my_core_files/rootfs-devtmpfs.cpio.gz
make virt-test-static
make virt-check
make virt-prepare
mkdir -p build/virt-kvm/logs
set -o pipefail
make virt-build VIRT_JOBS=4 2>&1 | tee build/virt-kvm/logs/build.log
make virt-verify
```

工具链和基础 rootfs 可按本机路径指定，不要求修改原工具链。`check` 会实际验证静态 RISC-V 链接；无法运行的自动候选会被跳过，显式 CROSS_COMPILE 失效则停止。
`prepare` 不修改已初始化子模块的工作树、分支或本地修改；不匹配则保留并报错。
新克隆的浅 Linux 子模块若没有普通 guest 基线，prepare 会从团队 Linux 仓库按固定 SHA 获取该提交，不移动 host 的 HEAD。

所有产物保存在当前 checkout 的 `build/virt-kvm/`。请使用这次新工作树的独立输出，不复制旧版 build/state/manifest；schema 2 拒绝混用旧布局。
编译 QEMU 时启用 slirp，可能需下载固定子项目或安装系统开发依赖；失败时保留日志检查。
dtc 使用 `NO_VALGRIND=1 NO_YAML=1`，保留交叉编译器的不安全系统路径拒绝检查。

host 和 guest 各自生成配置，host 为 KVM=y、MODULES=n，关闭动态代码功能；guest 禁用 KVM。
QEMU 为 RV64、TCG、一个 hart、2 GiB RAM、H 开启、Smepmp 关闭、PMP.Virt 开启。
OpenSBI 的 2 GiB RAM 策略代码已提交；每次构建根据最终 host Image 和 System.map 在 `build/virt-kvm/generated/pmp_virt_layout.h` 生成布局。
通过 `PMP_VIRT_LAYOUT_HEADER` 传入 OpenSBI 构建，不再写入子模块源码中的布局头。
没有生成布局就构建 seal 固件会明确失败。封存检查、SBI 白名单、text RX 和 rodata R 不被放松。
镜像 digest 用于构建配对，不代表固件进行运行时密码学认证。

## Ubuntu 服务器：统一回归

完成编译后执行：

```bash
make virt-test
```

入口自动启动 QEMU、以 root 登录 Buildroot host、运行 host 检查、启动无磁盘无网络的普通 guest、检查内存和 sleep 时间推进、关机返回 host、重新执行同页 U→HS→U，然后退出 QEMU。
guest 只有接收到 `virt_regression=1` 内核参数才自动测试和关机，手动启动不受影响。
host 检查核对本次启动时的 HS 6/6 和 SBI guard 18/18 日志，并实际重新执行同页测试；guest 返回后不会重新执行所有启动探针。

每次测试在 `build/virt-kvm/logs/regression-<时间>/` 保存：

- `console.log`：真实控制台输出。
- `manifest.json`：该次运行前的产物清单快照。
- `result.json`：结果、SDK HEAD、工作树状态、耗时及错误原因。
- `SHA256SUMS`：上述文件的校验值。

任一探针报错、缺少结果、顺序不符、超时或 QEMU 异常退出均判为 FAIL。
默认超时 300 秒，可执行 `python3 tests/pmp-virt/run-regression.py --timeout 600` 调整。
控制台无需手工输入命令；不要与其他会话同时操作同一个 QEMU。

## 手动操作与 Debian

Ubuntu 服务器执行 `make run-virt-host`，登录外层 host 后执行：

```sh
uname -r
check-virt-host
run-virt-guest
```

内层 guest 执行 `check-virt-guest`，然后 `poweroff`。返回 host 再执行 `check-virt-host`。
最后 Ctrl+A，松开，再按 X 退出外层 QEMU。

Debian 入口保留 W 的实现；本次自动回归不含 Debian。
先按 [Debian 镜像准备](../debian-guest.md) 准备并初始化独立磁盘，使用原版 kvmtool 传入，外层不挂载磁盘：

```bash
make run-virt-debian-host DEBIAN_DISK=/path/to/debian-guest.raw
```

外层 host 执行 `run-virt-debian`，进入 Debian 后检查 `cat /etc/os-release`、`ip addr`、`ip route`、DNS 和 `apt-get update`；关机返回 host 后再次检查保护。
同一可写磁盘不能同时由普通 KVM 与本实验使用。网络和 apt 测试需要单独记录，不能从 Buildroot 启动成功推导。

## 验证范围与历史

历史 B1 的原始日志保存在 `validation/b1/`，保留当时旧目录路径，不伪装为本次迁移的运行证据。
历史实验已完成保护 host、普通 guest 启停和返回 host 后复测；后续操作者还确认了持久修正后重启检查通过。
2026-11-12，子模块迁移后的服务器构建、产物校验、20 项静态检查及自动运行回归均通过，证据见 validation/submodules-b1/。Debian 联网验证仍待执行。

本轮不实现 G-stage.Virt、VS/VU 权限配对、SMP、压力测试或完整服务防绕过审计。
旧 Spike/普通 KVM Makefile 入口面对本次受保护 Linux 子模块可能不再适用，不能把它们当成本轮已验证入口。
旧分支先保留，待团队验收和归档后再清理，不因目录整理而删除原实验成果。
