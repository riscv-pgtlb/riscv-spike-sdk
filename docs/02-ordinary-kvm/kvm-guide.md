# RISC-V KVM 实验构建与启动

## 当前状态

已通过 SDK 默认工具链构建 Linux、KVM 模块、libfdt 和静态 lkvm，并验证 Buildroot guest、Debian guest 的启动。Debian 已验证 DNS、APT 索引更新、hello 软件包安装与运行。kvmtool 当前使用原始提交，不再自动应用 TCP 数据量限制补丁。

QEMU 网络构建已通过当前工作区验证，但尚未在全新目录执行完整下载、构建测试。
基础 rootfs 已通过 Buildroot 从源码构建，使用 Bootlin 外部工具链；OpenSBI 已使用 SDK 工具链构建。新固件、基础 rootfs、KVM 模块加载、guest 启动及 Debian DNS 已完成验证。尚未进行全新工作区的完整重建测试。

## 启动链与目录

```text
x86_64 Ubuntu 服务器
└── QEMU 10.1.0：TCG 模拟 RISC-V，启用 H 扩展
    └── OpenSBI → 外层 Linux → Buildroot 用户空间
        └── KVM + lkvm
            ├── Buildroot guest：initramfs
            └── Debian guest：独立可写磁盘
```

| 位置                              | 用途 |
| ---                               | --- |
| repo/linux                        | Linux 源码 |
| repo/kvmtool、repo/dtc            | lkvm 与设备树库源码 |
| repo/riscv-gnu-toolchain/qemu     | 统一使用的 QEMU 源码 |
| images/base/rootfs.cpio.gz	    | make rootfs-base 生成的基础 rootfs |
| images/kvm/fw_jump.bin	        | make opensbi-build 生成的固件 |
| conf/buildroot_base_defconfig	    | 当前基础 rootfs 的构建配置 |
| conf/rootfs-overlay/	            | 加入 rootfs 的初始化配置 |
| conf/linux_defconfig              | 实际用于内核构建的配置，含 CONFIG_KVM=m |
| conf/kvm                          | 原 A1 基线配置记录；Buildroot 配置目前不参与 KVM 打包 |
| build/linux                       | 新内核和模块编译输出 |
| build/kvm-modules                 | 按内核版本安装的模块暂存目录 |
| images/kvm/rootfs-kvm-new.cpio.gz | 自动生成的外层 initramfs |
| images/debian/debian-guest.raw    | 可写 Debian guest 磁盘 |
| scripts                           | 打包及 guest 启动脚本 |

原 work/linux-kvm 是使用 repo/linux 的独立构建输出目录，不是另一份Linux 源码。旧 work 已归档，当前流程不使用它。

## 前置输入和工具

需要本机 C/C++ 编译环境、Git、Make、Python、QEMU 的开发依赖，以及 cpio、gzip、设备树库构建所需工具。无 sudo 的构建依赖已安装的系统开发环境；并不表示一台空白服务器无需准备依赖。

基础 rootfs 和 OpenSBI 固件由后面的构建命令生成，不需要另外取得预构建镜像。images/ 保存生成产物，不提交 Git。历史基线校验值仅用于识别原始镜像，不用于校验重新构建的产物。

```text
images/base/rootfs.cpio.gz
images/kvm/fw_jump.bin
```


初始化子模块时按需下载，避免无条件递归下载整个工具链的所有组件：

```sh
git submodule update --init repo/linux repo/dtc repo/kvmtool repo/riscv-gnu-toolchain
git -C repo/riscv-gnu-toolchain submodule update --init -- qemu
```

## 构建

以下命令均在 Ubuntu 服务器的项目根目录执行：

```sh
make -j4 "$PWD/toolchain/bin/riscv64-unknown-linux-gnu-gcc"
# 构建模拟器
make -j4 qemu-build

# 构建并安装固件
make -j4 opensbi-build

# 构建基础 rootfs、内核、模块和 lkvm，并打包
make -j4 rootfs-kvm
```

工具链构建启用了 GDB。若 GCC 文件已存在但工具链未完整完成，可直接
继续内部构建：

```sh
make -C build/riscv-gnu-toolchain -j4 linux
```

若 Binutils/GDB 的 GitHub 镜像下载失败，本实验使用如下本地地址覆盖；
这些 Git 配置不会自动随主仓库提交：

```sh
git -C repo/riscv-gnu-toolchain config submodule.binutils.url https://sourceware.org/git/binutils-gdb.git
git -C repo/riscv-gnu-toolchain config submodule.gdb.url https://sourceware.org/git/binutils-gdb.git
```

rootfs-kvm 等待基础 rootfs、Linux 内核与模块、lkvm 构建完成后，再调用打包脚本。使用 -j 时，这些独立构建可以并行执行。

打包脚本使用新临时目录收集模块、lkvm、启动脚本和 guest 文件，生成新增 cpio.gz，并拼接基础归档。Linux 按顺序解包这些 initramfs 归档。脚本结束后删除临时目录，不使用旧 build/rootfs-extra。

QEMU 用户态网络构建细节见 [qemu-network.md](qemu-network.md)。

## 启动和关闭

| 系统 | Ubuntu 上启动外层 | 外层 root shell 中启动 guest |
| --- | --- | --- |
| Buildroot | make run-kvm-host | run-guest |
| Debian | make run-debian-host | run-debian |

Debian 首次下载、配置见 [debian-guest.md](debian-guest.md)。run-debian 先在外层执行 DHCP，再加载 KVM，以 mode=user 启动 guest。外层 IP、路由及 DNS 位于内存 rootfs，每次重启后需重新配置，脚本已包含该步骤。

Debian 内执行 poweroff 正常关闭 guest。回到外层后，Ctrl+A 再按 X退出 QEMU。同一块可写 Debian 磁盘不能同时用于两个虚拟机，也不要在外层挂载正交给 guest 使用的磁盘。

## 版本与验证范围

| 组件 | 已验证版本或提交 |
| --- | --- |
| Linux          | 6.17.2，449d48b1b99fdaa076166e200132705ac2bee711 |
| GCC / Binutils | 15.1.0 / 2.45 |
| GDB            | 16.3.90.20250610-git |
| QEMU           | VERSION=10.1.0，562020faa2ee9c531ce58434be01e3e42cfd94d6 |
| kvmtool        | eb915c763e4b95dd4a9d32763fd449459742e053，原版 |
| dtc            | f99e3af0ecb67a9085478a9b8ddbcc25aa64931d |
| Debian 用户空间 | 13 trixie，guest 内报告 13.7 |

原版 lkvm 已完成一次约 9 MB 索引文件下载，耗时约 64 秒，curl 退出码为 0；仍观察到 GRO 警告。曾测试的 1024 字节 TCP 限制已撤销，不能视为必需修复。恢复原版后的长期吞吐量、重复稳定性仍待评估。

未实现 Virt 保护；本实验也不验证物理 RISC-V 硬件的运行性能。
