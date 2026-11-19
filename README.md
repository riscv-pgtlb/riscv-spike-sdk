![项目标志](conf/logo.png)

# 双 Debian PMP.Virt 实验平台

本分支基于原 **RISC-V Spike Simulator SDK**，集成修改版 QEMU、OpenSBI 和 Linux，
在单核 RISC-V 虚拟环境中运行**受 PMP.Virt 保护的外层 Debian，以及普通内层 Debian**。
提供磁盘自动准备、两层工具更新、安装后版本校验和统一回归测试。

- 想了解实现与改动：[双 Debian 实验报告](docs/04-dual-debian/experiment-report.md)。
- 想开始使用：[双 Debian 操作入口](docs/04-dual-debian/README.md)。
- 想理解保护与测试：[PMP.Virt 原理和调用链](docs/03-pmp-virt-kvm/pmp-virt-explained.md)。

## 系统结构

```text
Linux 服务器
└─ 修改版 QEMU：TCG 模拟 RV64，开启 H 和 PMP.Virt
   └─ OpenSBI：M 态配置并封存保护规则
      └─ 受保护 Linux host + 外层 Debian
         └─ lkvm → /dev/kvm
            └─ 普通 Linux guest + 内层 Debian
```

两层使用项目编译的内核，Debian 磁盘提供用户空间，不经过磁盘内的 GRUB/EFI。
当前使用 **1 个 hart、外层 2 GiB 内存，内层 1 个 vCPU、768 MiB 内存**。
PMP.Virt 是本项目在模拟器中实现的实验扩展，不代表任意真实 RISC-V 硬件都支持该功能。

## 使用前准备

以下 `make` 命令均在**服务器项目根目录**执行。当前流程需要：

- Linux 服务器及构建依赖，可用的 RISC-V 交叉工具链。
- `conf/pmp-virt/sources.json` 锁定的组件源码，以及可用的基础 Buildroot rootfs。
- Debian riscv64 基础镜像 `images/debian/debian-13-nocloud-riscv64.qcow2` 和同批次 `SHA512SUMS`。
- Python 3、qemu-img、openssl、tar、cpio、flock、校验工具及相关系统依赖。

仓库不包含构建产物、工具链和 Debian 磁盘。镜像来源见 [镜像准备记录](docs/02-ordinary-kvm/debian-guest.md)，
构建依赖与流程见 [PMP.Virt 构建指南](docs/03-pmp-virt-kvm/README.md)。
磁盘初始化使用 QEMU 维护环境，不要求用服务器 sudo 挂载磁盘或运行 guestfish。

## 快速开始

### 1. 构建或检查已有产物

已有产物先运行：

```sh
make virt-verify
```

需要首次构建时，先准备上述依赖和基础 rootfs，再逐条执行：

```sh
git submodule sync -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
git submodule update --init --depth=1 -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
export BASE_ROOTFS="$PWD/images/base/rootfs.cpio.gz"
make virt-check
make virt-prepare
make virt-build VIRT_JOBS=4
make virt-verify
```

每一步成功后再继续。`BASE_ROOTFS` 要指向已存在的文件；显式选择工具链时，按本机路径设置 `CROSS_COMPILE`。
构建产物位于 `build/virt-kvm/`，host 内核和固件必须配对。

### 2. 首次准备两块磁盘

```sh
make debian-prepare
```

按提示设置两层 root 密码。成功后生成固定路径：

| 磁盘 | 外层设备 | 用途 |
| --- | --- | --- |
| `images/debian/debian-host.raw` | `/dev/vda` | 第 1 分区作为外层根目录 |
| `images/debian/debian-guest.raw` | `/dev/vdb` | 交给内层后成为其 `/dev/vda` |

**已有磁盘时跳过这一步，准备命令默认拒绝覆盖。** 明确要重建系统时，先关闭两层，再执行
`make debian-prepare DEBIAN_RECREATE=1`；新盘初始化成功后备份并替换旧盘。详见 [准备说明](docs/04-dual-debian/prepare.md)。

### 3. 运行统一测试

确认没有其他虚拟机使用这两块磁盘，然后执行：

```sh
make pmpvirt-test
```

输入当前外层 root 密码。命令自动执行逻辑测试、产物校验、外层登录、两层文件/版本核对及完整回归，
最后正常关闭外层，输出 `PMPVIRT TEST PASS` 或非零失败状态。

终端显示 **TEST 1～16**，状态包括 PASS、FAIL、SKIP 和 RUN；每个编号只显示一次，后续状态缩进对齐。
交互终端使用颜色，密码不写入命令参数或测试日志。
证据位于 `build/virt-kvm/logs/suite-<时间>/`。
参数、超时和错误诊断见 [统一测试说明](docs/03-pmp-virt-kvm/test-suite.md)。

### 4. 日常更新已有磁盘的工具

两层均正常关闭后，依次执行：

```sh
make debian-update
make pmpvirt-test
```

更新命令保留账号、密码和基础系统配置，更新包内工具及外层保存的 guest 内核，
不重建磁盘、不重新编译服务器组件。更新失败会报告已经完成的层，不自动回滚。
详见 [更新说明](docs/04-dual-debian/update.md) 与 [文件和版本校验](docs/04-dual-debian/tool-versions.md)。

## 正常使用与命令速查

只想进入系统而不是自动回归时，在服务器执行 `make run-virt-dual-debian`，登录外层后执行
`run-debian-guest` 启动正常登录模式的内层。
关机顺序为：**内层 `poweroff` → 返回外层 → 外层 `poweroff` → 等待 QEMU 退出**。
内层运行时，不要在外层挂载 `/dev/vdb` 及其分区。

| 命令 | 执行位置 | 工作 |
| --- | --- | --- |
| `make virt-check` | 服务器 | 检查构建输入和可用工具链 |
| `make virt-prepare` | 服务器 | 准备固定版本的独立源码 |
| `make virt-build` | 服务器 | 编译内核、固件、QEMU、lkvm 和测试程序 |
| `make virt-verify` | 服务器 | 校验构建产物摘要与 host/固件布局配对 |
| `make debian-prepare` | 服务器 | 首次创建并初始化两块磁盘 |
| `make debian-prepare DEBIAN_RECREATE=1` | 服务器 | 显式备份并重建正式磁盘 |
| `make debian-tools` | 服务器 | 生成两层工具包、版本和校验清单，不修改磁盘 |
| `make debian-update` | 服务器 | 自动更新已有的两层磁盘工具 |
| `make run-virt-dual-debian` | 服务器 | 启动外层，不自动启动内层或执行完整回归 |
| `make pmpvirt-test` | 服务器 | 统一逻辑、产物、版本和双 Debian 运行测试 |
| `make virt-test-static` | 服务器 | 单独运行逻辑测试，不启动真实 Debian |
| `make pmpvirt-test PMPVIRT_SYSTEM=buildroot` | 服务器 | 统一入口使用原有 Buildroot 回归 |
| `run-debian-guest` | 外层 Debian | 正常启动内层，不自动测试关机 |
| `check-virt-host` | 外层 Debian | 核对启动保护结果并执行同页 U → HS → U、syscall 接口及保护测试 |
| `test-virt-debian-all /dev/vdb` | 外层 Debian | 手动运行完整回归，默认使用本地配套工具版本 |
| `check-virt-tools` | 任一层 Debian | 检查本地安装文件和版本一致性 |

**服务器是运行 QEMU 的机器，外层/内层是 QEMU 内的 RISC-V 系统，不能混用命令位置。**

使用其他磁盘时，启动、更新和测试都应指定相同的两个参数，例如：

```sh
make pmpvirt-test   DEBIAN_HOST_DISK=/path/to/debian-host.raw   DEBIAN_GUEST_DISK=/path/to/debian-guest.raw   PMPVIRT_TIMEOUT=900
```

## 已验证范围

**2026-11-19 syscall 迁移验证：86 项自动测试通过，Buildroot 与正常双 Debian 回归各 16/16 通过，Debian 快照检查通过且磁盘内容不变。**
本轮详情见 [syscall 迁移验证记录](docs/04-dual-debian/syscall-validation.md)。

2026-11-17 历史归档：84 项自动测试通过，双 Debian 的 16 个汇总测试点全部通过。
已完成自动更新后的文件检查、服务器版本配对、保护回归和正常关机。
对应证据与结果见 [验证记录](docs/04-dual-debian/validation.md) 和 [实验报告](docs/04-dual-debian/experiment-report.md)。

保护检查包括：

- 封存前后的 HS RAM 执行、text/rodata 写入对照，共 6 项。
- 封存前后各 9 项 SBI guard 检查。
- 外层用户态执行成功、HS 执行同一物理页被拒绝、用户态再次执行成功。
- guest 启动前后分别执行 12 项 syscall 接口拒绝检查、2 项新命令拒绝检查及 3 轮 × 4 项固定目标 HS 访问检查。
- guest 启动、内核/内存/时间检查、关机返回及外层保护复测。

**返回外层后实际重跑同页探针、syscall 接口拒绝与固定目标保护测试；HS 6/6 与 SBI 18/18 核对本次启动的结果。**

新增 syscall 测试的范围、升级步骤和快照检查见 [syscall 保护测试](docs/03-pmp-virt-kvm/syscall-protection.md)。
目前不据此宣称覆盖 G-stage.Virt、完整 VS/VU 同页配对、多核、长期压力或完整安全审计。
文件摘要用于版本一致性和构建配对，不替代来源认证。

## 目录与文档

| 目录 | 内容 |
| --- | --- |
| `repo/` | 固定版本的组件子模块源码 |
| `conf/pmp-virt/` | 版本锁与受保护系统配置 |
| [scripts/](scripts/README.md) | 按构建、准备、安装、启动、更新等功能组织的脚本 |
| [tests/](tests/README.md) | 单元测试、运行时检查和完整回归 |
| [docs/](docs/README.md) | 基础启动、普通 KVM、PMP.Virt、双 Debian 四阶段文档 |
| `build/` | 本地生成的构建产物、工具包和测试日志 |
| `images/debian/` | 基础镜像、正式磁盘、备份及初始化材料 |

基础镜像和磁盘不提交；初始化传输材料含密码哈希，也不应提交或公开。

## 项目来源与历史流程

本项目沿用原 RISC-V Spike Simulator SDK 的工具链和组件组织基础。
原英文 Spike/JTAG 使用说明保存在 [历史文档](docs/01-boot-baseline/spike-sdk-legacy.md)。
旧 Spike、普通 KVM 入口保留作参考，尚未针对当前受保护内核重新验证；本分支按上面的 `virt-*`、`debian-*` 和 `pmpvirt-test` 入口操作。
