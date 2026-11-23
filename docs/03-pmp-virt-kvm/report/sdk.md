# SDK 主仓库与其他子模块改动报告

本文件按功能列出当前集成文件。核心机制在三个子模块中；这里的“功能文件”表示为实验提供的实现，不代表本轮全部新建。最近重命名另列于末尾。

## 构建及配置

| 文件 | 类型与用途 |
| --- | --- |
| [Makefile](../../../Makefile) | 修改集成入口：构建/校验、静态测试、统一回归、Debian 准备/启动/更新及工具包服务。 |
| [.gitmodules](../../../.gitmodules) | 子模块来源配置，Linux、OpenSBI、QEMU 指向团队实现仓库及对应分支。 |
| [conf/virt/sources.json](../../../conf/virt/sources.json) | 版本锁，区分 host/guest Linux，固定 QEMU、固件和构建依赖。 |
| [conf/virt/linux.config](../../../conf/virt/linux.config) | 实验内核配置输入，与构建脚本生成的角色配置共同使用。 |
| [scripts/build/virt-kvm.py](../../../scripts/build/virt-kvm.py) | 工具链和源码检查、隔离构建、布局生成、固件编译、rootfs 打包、产物清单校验、重打包及启动。最近同步了测试源文件的新名称。 |
| [scripts/buildroot/run-virt-guest.sh](../../../scripts/buildroot/run-virt-guest.sh) | Buildroot host 内通过 lkvm 启动普通 guest，支持回归模式。 |
| [scripts/buildroot/run-virt-debian.sh](../../../scripts/buildroot/run-virt-debian.sh) | Buildroot host 内启动 Debian guest。 |

构建产物集中在 `build/virt-kvm/`。布局头、Image、固件、rootfs、manifest 和 source lock 快照是生成材料，不应列成上游新增源码。

## 运行测试文件

| 文件 | 用途与运行时间 |
| --- | --- |
| [tests/pmp-virt/runtime/pv-user-test.c](../../../tests/pmp-virt/runtime/pv-user-test.c) | 编译成 `pv-user-test`，由 host 检查调用，验证同页 U → HS → U。 |
| [tests/pmp-virt/runtime/check-virt-host.sh](../../../tests/pmp-virt/runtime/check-virt-host.sh) | guest 启动前和返回后执行，核对启动日志、设备及同页探针结果。 |
| [tests/pmp-virt/runtime/check-virt-guest.sh](../../../tests/pmp-virt/runtime/check-virt-guest.sh) | guest 内检查内核、可用内存和时间推进。 |
| [tests/pmp-virt/regression/run-suite.py](../../../tests/pmp-virt/regression/run-suite.py) | `make pmpvirt-test` 总入口，先跑单元和产物检查，再组织实际运行，汇总 17 项并记录诊断与证据。 |
| [tests/pmp-virt/regression/buildroot/run-regression.py](../../../tests/pmp-virt/regression/buildroot/run-regression.py) | 服务器驱动原 Buildroot 回归的串口、结果顺序和退出检查。 |
| [tests/pmp-virt/regression/buildroot/test-virt-all.sh](../../../tests/pmp-virt/regression/buildroot/test-virt-all.sh) | 安装为 Buildroot host 的 `test-virt-all`，组织 host → guest → host。 |
| [tests/pmp-virt/regression/buildroot/virt-guest-autorun.sh](../../../tests/pmp-virt/regression/buildroot/virt-guest-autorun.sh) | Buildroot guest 回归启动标记存在时执行检查并关机。 |
| [tests/pmp-virt/regression/debian/test-virt-debian-all.sh](../../../tests/pmp-virt/regression/debian/test-virt-debian-all.sh) | Debian host 完整套件：版本检查、内层启动及串口取证、关机返回和 host 复测。 |
| [tests/pmp-virt/regression/debian/virt-guest-test.service](../../../tests/pmp-virt/regression/debian/virt-guest-test.service) | Debian guest 在回归启动标记下自动检查工具和系统，然后请求关机。 |

17 项及原命令对应见 [统一测试说明](../test-suite.md)。它们是汇总点，不是 17 个独立脚本。

## 单元测试文件

路径均位于 `tests/pmp-virt/unit/`，由 `make virt-test-static` 或统一测试入口先行执行。

| 文件 | 保护的行为 |
| --- | --- |
| `test_build.py` | 工具链、布局、版本锁、产物摘要、重打包与日志解析。 |
| `test_debian_deploy.py` | 维护启动、超时、成功/失败标记和 guest 安装模式。 |
| `test_debian_targets.py` | 正式磁盘目标保护、备份、发布与失败恢复。 |
| `test_debian_server_update.py` | 两盘更新的检查顺序、状态记录及部分失败。 |
| `test_debian_update.py` | 系统内更新包校验、环境限制、进程检查和失败处理。 |
| `test_directory_layout.py` | 实际打包并隔离安装两种工具包，验证目录和安装路径。 |
| `test_pmpvirt_suite.py` | 17 项解析、防回显误判、登录与脱敏、失败诊断和返回后新探针要求。 |
| `test_tool_versions.py` | 内容版本、host/guest 配套、文件损坏/缺失、权限变化及安装源校验。 |

## Debian 共用与准备文件

下表路径相对于 `scripts/debian/`。

| 文件 | 用途 |
| --- | --- |
| `common/maintenance.py` | 共用 QEMU 维护启动，挂载系统盘和只读 setup.tar，串口下发操作，检查退出状态并处理超时；也提供磁盘占用检查。 |
| `common/check-virt-tools.sh` | 从 update 目录迁入；安装和回归共用的角色、版本、文件哈希及权限检查。 |
| `prepare/prepare-dual-debian.sh` | 校验基础镜像、持有操作锁、生成密码哈希、转换两盘、准备传输材料并组织初始化与发布。 |
| `prepare/provision-dual-debian.py` | 验证暂存目录及构建产物，依次维护启动 host 和 guest。 |
| `prepare/provision-system.sh` | 维护环境内校验包、运行基础初始化与角色安装器、设置 root 密码并输出成功标记。 |
| `prepare/init-system.sh` | 检查 Debian 根设备，配置 fstab、主机名、时区和语言环境。 |
| `prepare/disk-targets.py` | 检查固定目标，默认拒绝覆盖；允许重建时先备份旧磁盘，再发布新磁盘并尽力恢复移动失败。 |

`setup.tar` 由 QEMU 作为只读 `/dev/vdb` 提供给维护虚拟机，直接以 tar 解包；不是网络传输。

## Debian 打包、安装、更新和运行文件

路径仍相对于 `scripts/debian/`。

| 文件 | 用途 |
| --- | --- |
| `install/tool-manifest.py` | 定义每角色的源文件、包内路径、权限和安装目标；生成 FILES.tsv、输入校验、内容版本及 host 配套 guest 版本。 |
| `install/pack-tools.sh` | 生成两套工具包、版本文件和 SHA256SUMS，输出到 `build/debian-tools/`。 |
| `install/install-tools.sh` | 安装前校验源文件与清单，按清单复制文件和权限，保存元数据并检查安装结果。 |
| `install/install-host.sh` | host 安装入口，检查权限、Debian 和内核名称。 |
| `install/install-guest.sh` | guest 安装入口，正常运行或 `--maintenance` 模式下启用测试服务；不等于立即启动服务。 |
| `update/update-dual-debian.py` | 服务器两盘更新入口，持锁、打包、依次维护启动，保存状态及日志；没有自动回滚。 |
| `update/update-system.sh` | 维护环境校验工具包并调用角色安装器，不重新配置账号密码和基础系统。 |
| `update/update-tools.sh` | Debian 内更新的共用实现，支持 `--from-dir`，校验本地包、加锁、解包后调用安装器。 |
| `update/update-host-tools.sh` | 安装为 host 的 `update-host-tools` 命令，转调共用更新实现。 |
| `update/update-guest-tools.sh` | 安装为 guest 的 `update-guest-tools` 命令。 |
| `run/run-dual-debian.sh` | 服务器检查磁盘、产物及操作锁，然后启动外层 Debian。 |
| `run/run-debian-guest.sh` | host 内正常启动 guest，区别于带自动测试参数的完整回归。 |

各目录 README、`docs/03-pmp-virt-kvm/` 和 `docs/04-dual-debian/` 分别说明原理、运行、版本和部署。本报告同步反映新命名，不把此前用户的注释修改或历史证据删除算成本轮功能修改。

## 最近完成的名称整理

| 原名称或路径 | 当前名称或路径 |
| --- | --- |
| `check-host.sh` | `check-virt-host.sh` |
| `check-guest.sh` | `check-virt-guest.sh` |
| `user-exec.c` | `pv-user-test.c` |
| `run-host-suite.sh` | `test-virt-all.sh` |
| `guest-autorun.sh` | `virt-guest-autorun.sh` |
| `update-virt-tools.sh` / `update-virt-tools` | `update-host-tools.sh` / `update-host-tools` |
| `dual-debian-tools.tar.gz` | `debian-host-tools.tar.gz` |
| `build/debian-host-transfer/` | `build/debian-tools/` |
| `install-guest.sh --offline` | `install-guest.sh --maintenance` |
| `scripts/debian/update/check-virt-tools.sh` | `scripts/debian/common/check-virt-tools.sh` |

构建、安装清单、调用者、测试和文档已同步；现有磁盘中的旧安装不会因源文件改名自动更新。报告中的旧名称只用于说明迁移关系。

## 其他子模块分别承担什么

| 子模块 | 在本实验中的用途与改动说明 |
| --- | --- |
| `repo/kvmtool` | 构建静态 lkvm，加载 guest 内核及磁盘；版本锁固定依赖，未识别为 PMP.Virt 定制核心实现。 |
| `repo/dtc` | 提供 libfdt 等构建依赖；不负责权限或封存策略。 |
| `repo/buildroot` | 提供基础用户空间；实验脚本由 SDK 打入派生 rootfs，而非把脚本视为 Buildroot 上游新增文件。 |
| `repo/riscv-gnu-toolchain` | 提供交叉工具链来源；工作区已有脏状态，不能据此归因于 PMP.Virt 改造。 |
| `repo/riscv-isa-sim`、`repo/riscv-pk` | SDK 其他流程的 Spike/代理内核依赖，不在这里的 QEMU + OpenSBI + Linux KVM 核心调用链中。 |
| `repo/riscv-openocd` | 调试相关依赖，不在本次虚拟机回归核心调用链中。 |

以上“未识别为核心改动”不代表逐一审计过这些依赖全部上游历史，也不代表它们都需要修改。

新增的 VS–HS–VS 由第 11 项汇总，五步集成及本轮修改文件见 [SDK 集成记录](../vs-hs-sdk-integration.md)。当前仅完成单元验证，尚未运行真实回归。
