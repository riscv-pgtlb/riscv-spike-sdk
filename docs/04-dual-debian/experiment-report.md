# 双 Debian PMP.Virt 系统实验报告

**实验日期：2026-11-16 至 2026-11-17。**

**实验目标：** 在已有 PMP.Virt + KVM 平台上，将外层和内层用户空间都替换为 Debian，保留受保护 host 内核与普通 guest 内核，实现环境准备、工具更新、安装后版本核对及完整回归。

**当前结果：** 正式两块磁盘已完成“自动更新 → 两层文件与版本校验 → 完整运行回归 → 正常关机”的验收。最新一轮包含 **84 项自动测试、16 个汇总测试点，全部通过**。

本文依据当前源码、操作者运行输出及服务器实际保存的结果文件整理，编写报告时没有重新执行虚拟机测试。代码仍包含未提交的工作区修改，不能仅用 SDK HEAD 代表本次所有源文件。

## 1. 实验基础与本轮改动范围

项目原有保护链已经在修改版 QEMU、OpenSBI 和 Linux 中实现。本轮双 Debian 工作主要发生在 **SDK 脚本、安装与更新工具、测试驱动和文档**，没有重新设计 PMP.Virt 的底层权限语义。

| 组件 | 在实验中的作用 | 本轮处理 |
| --- | --- | --- |
| 修改版 QEMU | TCG 模拟 RV64、H 扩展及实验性 PMP.Virt | 复用固定版本，增加双磁盘启动组织 |
| 修改版 OpenSBI | M 态配置、封存 PMP 规则及 SBI 服务限制 | 复用，根据 host 内核实际布局构建配对固件 |
| 修改版 Linux host | 提供 KVM，发起封存并执行保护探针 | 复用，根文件系统换成 Debian |
| 普通 Linux guest | 内层内核，不执行 host 的封存逻辑 | 复用独立源码及输出，加载 Debian 根磁盘 |
| lkvm/kvmtool | 外层用户程序，通过 `/dev/kvm` 运行内层 | 复用静态程序，自动打包安装 |
| Debian 13 | 两层 systemd、shell、工具与持久文件系统 | 分别配置独立磁盘和安装内容 |

版本依据是 [sources.json](../../conf/virt/sources.json)。本次配置固定的核心提交为：

| 组件 | 固定提交 |
| --- | --- |
| Linux host | `ab598939034057e7fdc2a4beb483a10ef4c67077` |
| Linux guest | `449d48b1b99fdaa076166e200132705ac2bee711` |
| OpenSBI | `0e1a39f96b50c09978aa190a830b713a51c014c2` |
| QEMU | `0ec20439ca845573db2a52e85aa34c0dca9c1731` |
| kvmtool | `eb915c763e4b95dd4a9d32763fd449459742e053` |
| dtc | `f99e3af0ecb67a9085478a9b8ddbcc25aa64931d` |

PMP.Virt 是本项目的实验扩展；机制、底层代码和异常含义见 [PMP.Virt 原理与测试调用链](../03-pmp-virt-kvm/pmp-virt-explained.md)。

## 2. 系统结构和磁盘关系

### 2.1 正常运行链

```text
服务器 Linux：构建、打包、启动和自动驱动测试
└─ 修改版 QEMU：TCG，RV64，H=true，Smepmp=off，PMP.Virt=on
   └─ OpenSBI：M 态
      └─ 受 PMP.Virt 保护的 Linux host：HS 态
         └─ 外层 Debian
            └─ lkvm → /dev/kvm
               └─ 普通 Linux guest：VS 态
                  └─ 内层 Debian
```

当前固定 **1 个 hart、外层 2 GiB 内存**。内层使用 **1 个 vCPU、768 MiB 内存**。
两层都直接加载项目编译的内核，不经过磁盘中的 GRUB/EFI，也不使用 Debian 发行版自带内核。

### 2.2 磁盘与设备映射

| 服务器文件 | 外层看到的设备 | 内层看到的设备 | 用途 |
| --- | --- | --- | --- |
| `images/debian/debian-host.raw` | `/dev/vda` | 不传入 | `/dev/vda1` 作为外层根文件系统 |
| `images/debian/debian-guest.raw` | `/dev/vdb` | `/dev/vda` | 内层 `/dev/vda1` 作为根文件系统 |

本实验基础镜像的虚拟容量为 3 GiB，第 1 分区是 ext4 根分区，第 15 分区为 EFI 分区。
初始化脚本按实际根分区 UUID 生成 fstab，不要求直接加载内核的启动方式挂载 EFI 分区。

**两块磁盘必须独立。内层运行期间，外层不得挂载内层盘，也不能将自己的根盘交给 lkvm。**

### 2.3 初始化和更新的维护环境

自动准备与自动更新会先后启动两次维护 QEMU。两次均使用 host 内核：

- 第一次处理 host 磁盘，第二次处理 guest 磁盘。
- 当前待处理磁盘是 `/dev/vda`，只读 tar 传输盘是 `/dev/vdb`。
- 使用 `init=/bin/sh debian_provision=1` 进入维护 shell，自动传入脚本并检查结果。
- guest 磁盘由 `install-guest.sh --maintenance` 安装工具，不依赖运行中的 guest 内核或 systemd。

**维护时使用 host 内核，不代表正式内层也使用 host 内核。** 正式内层仍由 lkvm 加载 guest Image。

## 3. 本轮完成了哪些改动

1. **双磁盘正常启动。** QEMU 从 host 磁盘启动外层，将第二块磁盘留给 lkvm。
2. **自动创建与初始化。** 校验原始 qcow2，生成独立 raw 磁盘，配置挂载、主机名、时区、语言、root 密码和两层工具。
3. **固定路径与备份重建。** 已有正式磁盘默认不覆盖；显式重建先在临时目录初始化成功，再备份旧盘并替换。
4. **两层统一安装。** 文件映射与权限只在一处定义，正常安装和离线初始化复用同一安装逻辑。
5. **自动更新。** 服务器一条命令更新两层已有磁盘，不重设账号、密码或基础配置，也不依赖磁盘预装更新命令。
6. **安装后版本核对。** 检查实际文件、执行权限、内容版本与 host/guest 配套关系；统一回归额外与服务器当前预期版本比对。
7. **统一测试。** 整合逻辑测试、产物校验和真实运行回归，支持 Debian、Buildroot 两种模式，输出固定编号及颜色。
8. **证据与诊断。** 保存控制台、版本快照、逐项结果、摘要和校验值；区分登录、超时、中断、工具版本、保护等失败原因。
9. **目录整理。** 实际功能与测试分开，文档按四个实验阶段组织，各功能目录配 README。

## 4. 新增、修改和迁移文件的功能

以下按**实际职责**列出文件。“新增”指双 Debian 集成引入的功能；“迁移/复用”不表示重新实现底层保护。
Git 中旧路径显示删除、新路径显示未跟踪，包含目录迁移的结果，不能简单将其理解为功能删除。

### 4.1 项目入口与构建脚本

| 文件 | 类型 | 功能与改动 |
| --- | --- | --- |
| [Makefile](../../Makefile) | 修改 | 增加 `debian-tools`、`serve-debian-tools`、`debian-prepare`、`debian-update`、`run-virt-dual-debian`、`pmpvirt-test`；提供磁盘、重建和超时参数；同步迁移路径并拆分长命令 |
| [.gitignore](../../.gitignore) | 修改 | 将构建产物忽略规则限定为根目录 `/build/`，避免误忽略源码目录 `scripts/build/` |
| [README.md](../../README.md) | 修改 | 增加阶段、脚本和测试导航，更新迁移后的操作链接 |
| [scripts/build/virt-kvm.py](../../scripts/build/virt-kvm.py) | 迁移并修改 | 复用构建/校验能力；补齐浅克隆缺少固定提交时的 fetch；保留单 host Debian 磁盘分支；同步源码、测试和清单路径。正式双盘启动走独立启动器，不依赖其单盘分支 |

### 4.2 双 Debian 准备、安装、启动和更新

下面所有路径相对于 `scripts/debian/`。

#### prepare：首次创建和显式重建

| 文件 | 功能 |
| --- | --- |
| [prepare/prepare-dual-debian.sh](../../scripts/debian/prepare/prepare-dual-debian.sh) | 服务器总入口：检查正式目标和操作锁、校验镜像、打包、交互生成密码哈希、创建临时磁盘与传输盘、初始化后发布。 |
| [prepare/provision-dual-debian.py](../../scripts/debian/prepare/provision-dual-debian.py) | 校验构建产物及临时磁盘，调用共用维护逻辑依次初始化两层。 |
| [prepare/disk-targets.py](../../scripts/debian/prepare/disk-targets.py) | 检查固定路径与重建参数；备份旧盘、发布新盘，普通替换错误时尝试恢复原盘。 |
| [prepare/init-system.sh](../../scripts/debian/prepare/init-system.sh) | 维护虚拟机内按 UUID 配置 fstab，设置主机名、hosts、Asia/Shanghai 时区和 C.UTF-8。 |
| [prepare/provision-system.sh](../../scripts/debian/prepare/provision-system.sh) | 维护虚拟机内校验工具包，调用基础初始化与对应安装器，设置 root 密码并输出成功标记。 |

#### install：打包与统一安装

| 文件 | 功能 |
| --- | --- |
| [install/pack-tools.sh](../../scripts/debian/install/pack-tools.sh) | 校验已有产物，生成两层工具包、HOST-VERSION、GUEST-VERSION 和顶层 SHA256SUMS。 |
| [install/tool-manifest.py](../../scripts/debian/install/tool-manifest.py) | 唯一维护源文件、目标路径和权限映射；生成文件清单、输入校验值、确定性内容版本及配套 guest 版本。服务器回归复用其版本计算。 |
| [install/install-tools.sh](../../scripts/debian/install/install-tools.sh) | 两层共用安装器：安装前核对所有输入，按清单复制文件、保存元数据并验证安装结果；DESTDIR 用于隔离安装验证。 |
| [install/install-host.sh](../../scripts/debian/install/install-host.sh) | 检查外层 root、Debian 和 host 内核身份及依赖，然后调用共用安装器。 |
| [install/install-guest.sh](../../scripts/debian/install/install-guest.sh) | 默认检查 guest 内核并重新加载 systemd；--maintenance 检查部署标记并离线启用服务；两种模式共用安装逻辑。 |

#### run：正常启动

| 文件 | 功能 |
| --- | --- |
| [run/run-dual-debian.sh](../../scripts/debian/run/run-dual-debian.sh) | 服务器检查两盘、构建产物及操作锁，组织 QEMU、固件、内核、两盘和网络参数。 |
| [run/run-debian-guest.sh](../../scripts/debian/run/run-debian-guest.sh) | 外层检查保护、内层盘存在且未挂载，再以正常登录模式调用 lkvm，不带自动测试参数。 |

#### update：保留现有系统的工具更新

| 文件 | 功能 |
| --- | --- |
| [update/update-dual-debian.py](../../scripts/debian/update/update-dual-debian.py) | 服务器检查两盘独立、读写权限和占用，重新打包，依次维护启动两盘更新；保存已完成层、工具版本和日志。 |
| [update/update-system.sh](../../scripts/debian/update/update-system.sh) | 维护虚拟机内检查部署环境与工具包，调用 host 或 guest 离线安装器，不修改基础配置和密码。 |
| [update/update-tools.sh](../../scripts/debian/update/update-tools.sh) | Debian 内两个本地更新命令的共用实现：检查身份、阻止并发、校验选定包并调用安装器。 |
| [update/update-host-tools.sh](../../scripts/debian/update/update-host-tools.sh) | 外层 update-host-tools 命令入口，转交共用更新程序。 |
| [update/update-guest-tools.sh](../../scripts/debian/update/update-guest-tools.sh) | 内层 update-guest-tools 命令入口，转交共用更新程序。 |
| [common/check-virt-tools.sh](../../scripts/debian/common/check-virt-tools.sh) | 校验已安装元数据、文件存在、内容、模式与指定版本；guest 测试时读取内核参数中的预期版本。 |

#### common：共用维护逻辑

| 文件 | 功能 |
| --- | --- |
| [common/maintenance.py](../../scripts/debian/common/maintenance.py) | 供准备和更新导入：校验磁盘/传输盘独立，检查 QEMU 写入占用，驱动维护串口，核对退出码和成功标记并处理超时。 |

### 4.3 运行检查与回归文件

| 文件 | 类型 | 功能 |
| --- | --- | --- |
| [tests/pmp-virt/runtime/check-virt-host.sh](../../tests/pmp-virt/runtime/check-virt-host.sh) | 迁移/复用 | 检查 host 身份、设备、封存和启动探针日志，再实际运行同页探针 |
| [tests/pmp-virt/runtime/check-virt-guest.sh](../../tests/pmp-virt/runtime/check-virt-guest.sh) | 迁移/复用 | 检查 guest 内核、可用内存与时间推进；同时保留 Buildroot 兼容性 |
| [tests/pmp-virt/runtime/pv-user-test.c](../../tests/pmp-virt/runtime/pv-user-test.c) | 迁移/复用 | 编译成 pv-user-test，执行同页 U → HS → U；内核侧探针仍在 Linux 子模块 |
| [tests/pmp-virt/regression/debian/test-virt-debian-all.sh](../../tests/pmp-virt/regression/debian/test-virt-debian-all.sh) | 新增/完善 | 串联版本核对、host 检查、lkvm 内层测试与关机、返回后的 host 复测；保存内层串口日志 |
| [tests/pmp-virt/regression/debian/virt-guest-test.service](../../tests/pmp-virt/regression/debian/virt-guest-test.service) | 新增/完善 | 仅测试启动参数下执行文件版本及 guest 检查，成功后输出关机标记；失败也请求关机，但不假报成功 |
| [tests/pmp-virt/regression/run-suite.py](../../tests/pmp-virt/regression/run-suite.py) | 新增 | 统一现有测试，自动登录 Debian 或复用 Buildroot 驱动，逐项核对证据、检查退出状态、归档并提供错误诊断 |

### 4.4 自动测试文件

这些文件位于 `tests/pmp-virt/unit/`。**它们使用临时文件或模拟进程验证逻辑，不等于每个用例都启动真实 Debian。**

| 文件 | 类型 | 覆盖内容 |
| --- | --- | --- |
| [test_build.py](../../tests/pmp-virt/unit/test_build.py) | 迁移并适配路径 | 布局、对齐、RAM 范围、版本锁、工具链选择、内核/固件配对、rootfs 重打包与日志解析 |
| [test_debian_deploy.py](../../tests/pmp-virt/unit/test_debian_deploy.py) | 新增 | 维护启动、缺失输入、超时、误判防护，以及 guest 安装器正常/离线模式 |
| [test_debian_targets.py](../../tests/pmp-virt/unit/test_debian_targets.py) | 新增 | 固定路径保护、已有磁盘拒绝覆盖、备份与替换失败恢复 |
| [test_debian_server_update.py](../../tests/pmp-virt/unit/test_debian_server_update.py) | 新增 | 两盘更新前置检查、执行顺序、版本记录和部分失败状态 |
| [test_debian_update.py](../../tests/pmp-virt/unit/test_debian_update.py) | 新增 | 本地目录更新的包校验、运行环境、内层占用和安装失败处理 |
| [test_directory_layout.py](../../tests/pmp-virt/unit/test_directory_layout.py) | 新增 | 实际打包及隔离目录安装，确保新路径可用且工具包不含单元测试 |
| [test_pmpvirt_suite.py](../../tests/pmp-virt/unit/test_pmpvirt_suite.py) | 新增 | 逐项结果解析、终端控制字符、自动登录、密码脱敏、超时、错误分类及服务器版本传递 |
| [test_tool_versions.py](../../tests/pmp-virt/unit/test_tool_versions.py) | 新增 | 确定性版本、两层配对、源包损坏、文件缺失/修改/权限变化、元数据和旧版混用 |

### 4.5 原流程迁移与复用

| 当前文件 | 原位置/职责 | 本轮处理 |
| --- | --- | --- |
| `scripts/buildroot/run-virt-guest.sh` | 原 `scripts/run-virt-guest.sh` | 迁移，保留受保护 Buildroot 外层启动内层的能力 |
| `scripts/buildroot/run-virt-debian.sh` | 原 `scripts/run-virt-debian.sh` | 迁移，保留 Buildroot 外层加 Debian 内层 |
| `tests/pmp-virt/regression/buildroot/run-regression.py` | 原测试根目录 | 调整根目录和导入路径，仍驱动原 Buildroot 回归，统一入口可复用 |
| `tests/pmp-virt/regression/buildroot/test-virt-all.sh` | 原测试根目录 | 迁移，保留 host → guest → host 测试序列 |
| `tests/pmp-virt/regression/buildroot/virt-guest-autorun.sh` | 原测试根目录 | 迁移，保留 Buildroot guest 的测试模式检查及关机 |
| `scripts/legacy/pack-kvm-rootfs.sh` | 原 scripts 根目录 | 调整项目根目录和脚本路径，保留旧普通 KVM 打包 |
| `scripts/legacy/run-guest.sh` | 原 scripts 根目录 | 迁移，普通 KVM 的 Buildroot guest 启动 |
| `scripts/legacy/run-debian.sh` | 原 scripts 根目录 | 迁移，普通 KVM 的 Debian guest 启动 |
| `scripts/setup/quickstart.sh` | 原 scripts 根目录 | 调整根目录定位，保留子模块初始化 |
| `scripts/setup/retry-linux.sh` | 原 scripts 根目录 | 按脚本位置定位项目，保留 Linux 子模块下载重试 |

旧普通 KVM 入口未在当前受保护内核下重新验证，不能作为双 Debian 验收依据。

### 4.6 文档与目录 README

- **脚本说明：**`scripts/README.md` 及 `build/`、`buildroot/`、`setup/`、`legacy/` 的 README 分别说明整体入口、构建、现有 Buildroot 启动和历史流程。
- **双 Debian 说明：**`scripts/debian/README.md` 及 `prepare/`、`install/`、`run/`、`update/`、`common/` 的 README 逐项说明功能脚本。
- **测试说明：**`tests/README.md`、`tests/pmp-virt/README.md` 及 `unit/`、`runtime/`、`regression/`、`regression/buildroot/`、`regression/debian/` 的 README 区分单元测试、运行检查和完整回归。
- **阶段导航：**`docs/README.md` 与四个阶段及历史验证子目录的 README 说明阶段目标、文件用途和证据可用性；此前已经删除的历史原始日志没有重建。

第四阶段文档职责如下：

| 文档 | 用途 |
| --- | --- |
| [README.md](README.md) | 双 Debian 的阅读和操作入口 |
| [architecture.md](architecture.md) | 系统结构、磁盘和脚本调用关系 |
| [prepare.md](prepare.md) | 创建、固定路径和备份重建 |
| [run.md](run.md) | 正常启动、关机及手动/统一测试 |
| [update.md](update.md) | 更新两层已有工具 |
| [tool-versions.md](tool-versions.md) | 文件清单、内容版本及配套关系 |
| [validation.md](validation.md) | 已有结果、证据位置和未完成事项 |
| 本报告 | 综合记录目标、改动文件、运行方法和验收结论 |

第三阶段新增的 [pmp-virt-explained.md](../03-pmp-virt-kvm/pmp-virt-explained.md) 解释底层保护机制，
[test-suite.md](../03-pmp-virt-kvm/test-suite.md) 说明统一测试入口与输出。

## 5. 运行前提和产物

所有 `make` 命令在**服务器项目根目录**执行。本机目录为 `/home/wsh/riscv-spike-sdk`。
运行安装器、`check-virt-host`、`run-debian-guest` 等命令的位置不同，后文会分别标注。

前提条件：

- 已准备锁定的子模块、可用交叉工具链和基础 Buildroot rootfs。
- 已提供 `images/debian/debian-13-nocloud-riscv64.qcow2` 及同批次 `SHA512SUMS`；镜像下载与校验来源记录见 [第二阶段镜像说明](../02-ordinary-kvm/debian-guest.md)。
- 服务器具备 Python 3、qemu-img、openssl、tar、cpio、flock、校验工具及构建依赖。
- Debian 镜像可运行 shell、coreutils、systemd 等安装与测试依赖。
- 创建/重建/更新时不运行占用目标磁盘的其他虚拟机。

**本轮采用 QEMU 维护环境初始化磁盘，不要求使用 guestfish，也不需要通过服务器 sudo 挂载磁盘。**
初始化不是任意发行版/分区布局的通用安装器，当前检查根分区为 `/dev/vda1`。

主要构建产物：

| 路径 | 用途 |
| --- | --- |
| `build/virt-kvm/out/linux-host/arch/riscv/boot/Image` | 外层受保护内核 |
| `build/virt-kvm/out/linux-guest/arch/riscv/boot/Image` | 内层普通内核 |
| `build/virt-kvm/out/opensbi/platform/generic/firmware/fw_jump.bin` | 与 host 布局配对的固件 |
| `build/virt-kvm/out/qemu/qemu-system-riscv64` | 修改版 QEMU |
| `build/virt-kvm/src/kvmtool/lkvm-static` | 静态内层启动工具 |
| `build/virt-kvm/out/pv-user-test` | 同页权限测试程序 |
| `build/virt-kvm/manifest.json` | 构建产物摘要和版本记录 |

构建仍会生成 `build/virt-kvm/images/host-rootfs.cpio.gz` 和 `guest-rootfs.cpio.gz`，供 Buildroot 流程使用。
**双 Debian 正常启动使用 raw 根磁盘，不使用这两份 initramfs。**

## 6. 操作步骤与每个命令的工作

### 6.1 准备源码与构建：服务器执行

已有产物先执行 `make virt-verify`，通过时不必每次重新构建。需要重建时：

```sh
cd /home/wsh/riscv-spike-sdk
git submodule sync -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
git submodule update --init --depth=1 -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
export BASE_ROOTFS="$PWD/images/base/rootfs.cpio.gz"
make virt-check && make virt-prepare && make virt-build VIRT_JOBS=4
make virt-verify
```

| 命令 | 做的工作 |
| --- | --- |
| `git submodule sync` | 同步子模块 URL 配置 |
| `git submodule update --init ...` | 初始化并检出 SDK 固定的组件版本，不自动选择远端最新提交 |
| `export BASE_ROOTFS=...` | 指定已有基础根文件系统路径，不负责生成该文件 |
| `make virt-check` | 检查构建输入、源码和可用工具链，包括静态链接能力 |
| `make virt-prepare` | 准备固定版本的独立源码副本与状态，不编译组件 |
| `make virt-build VIRT_JOBS=4` | 构建两套内核、配对固件、QEMU、lkvm 和探针，打包 rootfs 并生成清单；不代表已做运行回归 |
| `make virt-verify` | 检查实际产物摘要和 host/固件布局配对；不检查 Debian 整盘 |

### 6.2 首次创建双 Debian：服务器执行

```sh
make debian-prepare
```

它依次完成镜像校验、工具打包、交互设置 root 密码、创建两盘、维护初始化和结果检查。
成功后发布到固定路径 `images/debian/debian-host.raw`、`debian-guest.raw`。

**已有任一正式磁盘时，默认停止，不覆盖。** 日常使用不要反复执行准备命令。
明确要创建全新系统时，先关机，再执行：

```sh
make debian-prepare DEBIAN_RECREATE=1
```

新盘先在 `prepared-*` 暂存目录完成初始化，成功后旧正式盘移入 `backup-*`，再发布新盘。
新密码取自本次交互输入；原数据仍在备份盘中。普通文件替换错误会尝试恢复，但两次重命名不是断电安全事务。

### 6.3 打包与更新：服务器执行

```sh
make debian-tools
```

只生成工具安装材料，不更新磁盘。输出在 `build/debian-tools/`：

- `debian-host-tools.tar.gz`：外层完整工具包。
- `debian-guest-tools.tar.gz`：内层小包。
- `HOST-VERSION`、`GUEST-VERSION`：两层内容版本。
- `SHA256SUMS`：上述包和版本文件的校验值。

两层均关闭后执行：

```sh
make debian-update
```

它检查两盘、操作锁和写入占用，重新打包，再依次维护启动并更新两层。
**更新保留账号、密码、主机名、时区和 fstab，不重新生成系统盘。** 更新状态和日志在 `build/debian-updates/update-*/`。
中途失败会停止、记录已完成的层，不自动回滚；不能把只更新成功一层视为全部成功。

可选的手动传输入口：

| 命令 | 工作 |
| --- | --- |
| `make serve-debian-tools` | 先打包，再在服务器 `127.0.0.1:8000` 提供下载服务；不是自动更新必需条件 |
| `update-host-tools --from-dir DIRECTORY` | 在外层对本地目录中的外层包做校验并更新；更新前停止内层 |
| `update-guest-tools --from-dir DIRECTORY` | 在内层对本地目录中的内层包做校验并更新 |

本地更新目录需同时包含对应压缩包及同批次 `SHA256SUMS`。这两个命令当前不负责 URL 下载。

### 6.4 正常启动与关机

服务器执行：

```sh
make run-virt-dual-debian
```

该命令检查产物和两盘，启动外层，不自动启动内层，也不自动执行整套回归。
登录外层后：

```sh
uname -r
findmnt -n -o SOURCE /
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
run-debian-guest
```

前三条分别核对内核身份、根分区与磁盘挂载。第四条先检查 host 保护和内层盘状态，再启动可登录的内层。
内层应显示 `6.17.2-virt-kvm-guest+`，自动初始化后的主机名为 `debian-guest`。

关机顺序是：**内层执行 `poweroff` → 返回外层 → 外层执行 `poweroff` → 等待 QEMU 退出。**

### 6.5 一条命令运行完整测试：服务器执行

```sh
make pmpvirt-test
```

该命令先运行逻辑测试和产物校验，再检查磁盘、交互读取外层 root 密码，自动登录并调用已安装的完整套件。
测试后正常关闭外层，保存逐项结果和原始控制台。

输出固定为 **TEST 1～16**，每个编号只在首次出现时显示；后续状态缩进对齐。
PASS 绿色、FAIL 红色、SKIP 黄色、RUN 青色；非交互输出不加颜色，`NO_COLOR=1` 可禁用。
密码不进入命令参数或结果文件，控制台日志会做密码脱敏。

常用参数：

```sh
make pmpvirt-test PMPVIRT_TIMEOUT=900

make pmpvirt-test   DEBIAN_HOST_DISK=/path/to/debian-host.raw   DEBIAN_GUEST_DISK=/path/to/debian-guest.raw

make pmpvirt-test PMPVIRT_SYSTEM=buildroot
```

- `PMPVIRT_TIMEOUT`：运行阶段超时秒数，默认 600。
- 两个 `DEBIAN_*_DISK`：明确使用指定磁盘；准备默认固定盘，启动、更新和测试应保持使用同一对磁盘。
- `PMPVIRT_SYSTEM=buildroot`：改用原有 Buildroot 回归，不运行双 Debian，也不需要 Debian 密码。
- 无人值守可以用 `PMPVIRT_PASSWORD_FILE=/path/to/file`，该文件只能由所有者读写，内容为单行密码，不能提交到仓库。

前置检查失败时后续项目为 SKIP，失败返回非零状态。正常结束与被中断/超时强制结束有区别；后者不能算关机测试通过。

### 6.6 分别运行已有检查

| 执行位置 | 命令 | 工作 |
| --- | --- | --- |
| 服务器 | `make virt-test-static` | 单独运行自动逻辑测试，不启动真实 Debian |
| 服务器 | `make virt-test` | 原 Buildroot 完整自动回归，不是双 Debian |
| 外层 | `check-virt-host` | 核对本次启动探针和封存结果，重新执行同页 U → HS → U |
| 外层 | `test-virt-debian-all /dev/vdb` | 手动完整回归；使用本地保存的配套版本，服务器最新版本比对应使用统一入口 |
| 两层均可 | `check-virt-tools` | 检查本地安装清单、文件、权限和元数据；默认不等于检查服务器最新版本 |
| 内层 | `/usr/local/bin/check-virt-guest` | 单独检查内核、内存及时间推进 |

## 7. 调用链及版本校验原理

### 7.1 正常完整回归

```text
make pmpvirt-test
└─ run-suite.py
   ├─ unittest：自动逻辑测试
   ├─ virt-kvm.py verify：构建产物校验
   ├─ tool-manifest.py：计算服务器当前 host/guest 预期版本
   ├─ run-dual-debian.sh → QEMU → OpenSBI → host Linux → 外层 Debian
   │  └─ 自动 root 登录
   │     ├─ check-virt-tools：先核对服务器 host 预期版本
   │     └─ test-virt-debian-all /dev/vdb <host版本> <guest版本>
   │        ├─ 外层文件/版本检查 + check-virt-host
   │        ├─ lkvm → /dev/kvm → guest 内核 → 内层 Debian
   │        │  └─ virt-guest-test.service
   │        │     ├─ check-virt-tools：文件与传入的 guest 预期版本
   │        │     ├─ check-virt-guest
   │        │     └─ 关机，返回外层
   │        ├─ 核对内层成功、关机与版本标记
   │        └─ 外层再次文件/版本检查 + 同页保护复测
   └─ 检查套件退出码、结果顺序、正常关机并归档
```

### 7.2 文件版本校验

安装器保存 `/var/lib/virt-tools/` 下的 `ROLE`、`FILES.tsv`、`INPUTS.SHA256SUMS`、`VERSION`。
文件清单记录内容摘要、安装权限、包内源路径和目标路径；版本由这些确定性内容及安装输入组成，不依赖时间戳。
外层另外保存 `EXPECTED-GUEST-VERSION`，把两层版本配成一组。

校验分三层：

1. **包输入正确。** 安装前验证源文件，损坏时不开始复制。
2. **安装结果正确。** 检查实际文件存在、非符号链接、内容及权限匹配。
3. **与当前服务器一致。** 统一测试将磁盘内版本与服务器本轮计算的预期版本比对，避免整套旧文件自洽却被误认为最新。

内层通过 `virt_tools_version=<版本>` 启动参数接收预期版本。服务先检查版本再做 guest 功能检查。
检查失败时也会关机，但不会输出成功的 `GUEST SHUTDOWN`；外层据缺少成功结果判为失败。

**这是可信环境下的一致性检查，不是签名认证，也不能抵抗已控制内核或校验程序的攻击者。**

## 8. 16 个汇总测试点

| TEST | 检查内容 | 依据 |
| --- | --- | --- |
| 1 | 现有逻辑与部署测试 | unittest 返回值；本轮 84 项通过 |
| 2 | 构建产物与 host/固件配对 | 产物摘要及布局校验 |
| 3 | 运行环境 | 磁盘、占用及登录输入条件 |
| 4 | 启动封存及 Linux 确认 | 当前启动的固件/内核输出 |
| 5 | HS RAM 执行前后对照 | 封存前成功，封存后 cause=1 |
| 6 | text 可写别名写入前后对照 | 封存前成功，封存后 cause=7 |
| 7 | rodata 可写别名写入前后对照 | 封存前成功，封存后 cause=7 |
| 8 | 封存前 SBI guard 9/9 | 所选接口均拒绝且缓冲区未改变 |
| 9 | 封存后 SBI guard 9/9 | 同组接口再次核对 |
| 10 | guest 前同页与 host 检查 | U 成功 → HS 同页访问拒绝 → U 再成功；包含外层文件/版本 |
| 11 | guest 功能检查 | 内核、内存、时间及内层文件/版本 |
| 12 | guest 自动关机请求 | 成功检查后的关机标记 |
| 13 | guest 返回 | lkvm 正常结束，外层套件确认内层结果 |
| 14 | 返回后外层复测 | 重新执行同页测试，并再次核对外层文件/版本 |
| 15 | 完整套件结果与顺序 | 标记齐全、顺序正确，无失败结果 |
| 16 | 命令与 QEMU 退出 | 套件退出码为 0，外层正常关机，QEMU 正常退出 |

**16 项是汇总检查，不是 16 个独立硬件保护实验。** TEST 1 内含 84 个自动用例；HS 访问共有封存前后 6 项，SBI guard 共 18 项。
HS 6/6、SBI 18/18 在 host 启动时执行；guest 返回后读取这次启动结果，实际重跑的是同页探针，不是全部启动探针。
同页 U 指外层用户态，不能将其误写成内层 VS/VU 配对测试。

## 9. 实验结果与证据

### 9.1 最新正式验收

2026-11-17，操作者依次执行 `make debian-update`、`make pmpvirt-test`，得到：

```text
DEBIAN UPDATE VERIFIED: host
DEBIAN UPDATE VERIFIED: guest
DUAL DEBIAN UPDATE PASS
...
[TEST 16] [PASS] 测试命令成功退出且 QEMU 正常结束
PMPVIRT TEST PASS
```

结果文件确认：

- 自动测试：**84 项通过**。
- 统一运行汇总：**16 项全部 PASS**。
- 本轮统一入口总耗时记录为 **111.58 秒**；单次样本，不作性能结论。
- 外层内容版本检查 **3 次**，内层 **1 次**，均匹配服务器预期。
- 更新状态的 `tools_versions` 与回归 `expected-tools.json` 一致。

本轮工具内容版本：

| 层 | VERSION |
| --- | --- |
| host | `d2ab49cdb01241be336c9c19cd641a8c2de189c48bfc5e0426af785826f1b09c` |
| guest | `a3fb428502e963e11181b8ac66aba327bd01fa655e9f71fe4bb8fa38e857a4d5` |

### 9.2 证据位置

| 位置 | 内容 |
| --- | --- |
| `build/debian-updates/update-4kcj1zne/` | 两层更新控制台、输入材料、已完成层及版本状态 |
| `build/virt-kvm/logs/suite-20261117-202619-577118/` | 本轮完整测试证据 |
| 外层 `/var/log/virt-regression/debian-*/` | 完整套件记录的内层串口及去回车日志 |

服务器统一测试目录包含：

- `static.log`、`verify.log`：逻辑测试与产物校验输出。
- `console.log`：本轮真实控制台，覆盖启动保护、登录、两层检查和关机。
- `inputs.json`：SDK HEAD、工作区状态、磁盘路径与超时。
- `manifest.json`、`sources.json`：本轮构建与源版本快照。
- `expected-tools.json`：本轮服务器预期的两层工具版本。
- `result.json`、`summary.txt`：逐项结果、错误诊断和总耗时。
- `SHA256SUMS`：证据文件校验值。

之前还完成过 `suite-20261117-194902-819576` 的正式盘回归，以及更新 `update-0osktoec` 后的
`suite-20261117-195758-080605` 回归；它们发生在新增文件清单校验之前，不能替代本轮版本功能的验收。

**本报告没有从文字摘要重构原始日志。** 初始化日志、更新日志和保护回归日志用途不同，不能相互替代。

## 10. 已处理的问题与验证边界

### 已处理的问题

- **无服务器 sudo 密码：**不依赖 guestfish 辅助内核权限，改用 QEMU 维护环境配置磁盘。
- **准备命令重复产生测试盘：**改为固定正式路径、默认拒绝覆盖、显式备份重建。
- **安装逻辑重复：**两层安装器调用统一清单安装器，guest 正常/离线模式复用同一份实现。
- **Debian shell 提示符未识别：**处理 ANSI、OSC 和 bracketed-paste 控制字符，并增加回归用例。
- **等待阶段缺少反馈：**定期输出当前登录/运行阶段及日志路径。
- **失败信息不明确：**分别报告认证拒绝、中断、超时、工具缺失、版本不符、产物与保护失败；后续未执行项保持 SKIP。
- **旧工具也可能输出 PASS：**引入实际文件和服务器版本配对，不只依赖功能成功标记。

### 当前边界和后续工作

本实验已证明所测单核环境下，两层 Debian 能正常运行，选定保护行为生效，并在一次 guest 生命周期后保持同页测试结果。
目前不能据此宣称覆盖 G-stage.Virt、完整 VS/VU 同页权限配对、SMP、长期压力、所有 SBI 旁路或完整服务防绕过审计。

后续优先工作是：

1. 统一归档本轮原始证据并提交代码、文档；不将密码材料和磁盘提交到仓库。
2. 设计扩展开/关对照、物理边界和 TLB 相关实验。
3. 增加多轮 guest 生命周期及负载测试，再逐步扩展验证范围。

**结论：双 Debian 的准备、更新、文件/版本校验和完整功能回归已形成可重复执行的实验流程；安全结论限于已执行的测试和配置。**
