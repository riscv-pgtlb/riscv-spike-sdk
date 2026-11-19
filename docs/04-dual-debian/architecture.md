# 双 Debian 架构与实现

## 正常运行链

```text
服务器 Linux
└─ 修改版 QEMU：TCG 模拟 RISC-V，启用 H 和 PMP.Virt
   └─ 修改版 OpenSBI：M 态，配合 host 配置和封存保护
      └─ 受保护 Linux host：HS 态，提供 KVM
         └─ Debian 外层用户空间
            └─ lkvm → /dev/kvm
               └─ 普通 Linux guest：VS 态
                  └─ Debian 内层用户空间
```

两层使用项目编译的内核，磁盘提供 Debian 用户空间，不经过磁盘上的 GRUB/EFI。
Buildroot 的 host/guest initramfs 仍由构建生成，但双 Debian 正常启动不使用它们。

## 磁盘与运行位置

| 文件或程序 | 外层看到的位置 | 用途 |
| --- | --- | --- |
| `images/debian/debian-host.raw` | `/dev/vda`，第 1 分区挂载 `/` | 外层系统盘 |
| `images/debian/debian-guest.raw` | `/dev/vdb`；交给内层后成为内层 `/dev/vda` | 内层系统盘 |
| `build/virt-kvm/out/linux-host/arch/riscv/boot/Image` | 由服务器 QEMU 加载 | 外层受保护内核 |
| `build/virt-kvm/out/linux-guest/arch/riscv/boot/Image` | 安装为外层 `/opt/guest/Image`，由 lkvm 加载 | 内层普通内核 |
| `build/debian-tools/*.tar.gz` | 安装时解包 | 工具包，不是系统盘 |

guest 运行时，外层不能挂载其磁盘或分区，也不能把自己的根磁盘交给 lkvm。
通过 `uname -r` 判断所在层：外层包含 `pmpvirt-kvm-host`，内层包含 `virt-kvm-guest`。

## 功能目录

| 目录 | 职责 |
| --- | --- |
| `scripts/build/` | 编译和产物校验 |
| `scripts/debian/prepare/` | 创建、初始化并发布固定磁盘 |
| `scripts/debian/install/` | 工具打包与两层安装器 |
| `scripts/debian/run/` | 服务器启动外层，外层启动内层 |
| `scripts/debian/update/` | 更新已有磁盘工具 |
| `scripts/debian/common/` | 准备和更新共用的维护 QEMU、串口及占用检查 |
| `tests/pmp-virt/runtime/` | 两层检查及同页权限探针 |
| `tests/pmp-virt/regression/debian/` | 完整回归和内层测试服务 |

## 准备和更新调用关系

```text
make debian-prepare
└─ prepare-dual-debian.sh
   ├─ 检查正式目标及重建参数
   ├─ 校验基础镜像 → pack-tools.sh → virt-kvm.py verify
   ├─ 收集脚本和工具包、交互生成密码哈希
   ├─ 创建两块临时 raw 磁盘与只读 setup.tar
   ├─ provision-dual-debian.py → common/maintenance.py
   │  ├─ 维护启动 host → provision-system.sh host
   │  │  └─ init-system.sh host → install-host.sh → 设置密码
   │  └─ 维护启动 guest → provision-system.sh guest
   │     └─ init-system.sh guest → install-guest.sh --maintenance → 设置密码
   └─ 两层均成功 → 备份旧盘 → 发布到正式固定路径

make debian-update
└─ update-dual-debian.py
   ├─ 检查两盘、互斥和写入占用 → 打包工具
   └─ common/maintenance.py 依次维护启动两盘
      └─ update-system.sh host|guest → 对应安装器
```

维护启动是配置或更新文件的临时环境，两次都使用 host 内核与 `init=/bin/sh debian_provision=1`。
当前系统盘成为 `/dev/vda`，只读 tar 传输盘成为 `/dev/vdb`，直接解包而非挂载。
这不是正常的双层 KVM 运行；正常内层仍由 lkvm 加载 guest 内核。
准备会设置基础配置和新密码，更新只安装包内文件，不重设账号和基础配置。
维护程序检查脚本退出码、成功标记及 QEMU 退出状态，并设置超时。

## 工具包与更新命令

`make debian-tools` 生成外层完整包、内层小包和 `SHA256SUMS`。
新安装器同时安装 `run-debian-guest`（外层）以及对应的 `update-host-tools`、`update-guest-tools`。
两种 Debian 内更新命令支持 `--from-dir DIRECTORY`，目录中需包含对应工具包和同批次校验清单。
服务器 `make debian-update` 自动传入工具包，不依赖这两个命令预先安装，也不需要下载服务。
`make serve-debian-tools` 是可选的手动传输辅助，不是自动更新的前置条件。

`virt-verify` 校验构建产物，不覆盖整块 Debian 磁盘或安装后文件版本。
磁盘会随系统运行变化，不能把整盘摘要恒定作为日常版本校验要求。
文件级版本检查已接入安装和双 Debian 回归，流程见 [工具版本校验](tool-versions.md)；它补充而不替代构建与功能检查。
