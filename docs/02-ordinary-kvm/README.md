# 第二阶段：普通 KVM

目标是从 Buildroot 外层通过 KVM/lkvm 启动 Buildroot 或 Debian 内层，补齐磁盘和网络。
本目录保留该阶段的操作和验证记录；其中“当前状态”指编写时，不是今天的项目状态。
当前受保护内核下没有重新验证旧入口，日常双 Debian 请看 [第四阶段](../04-dual-debian/README.md)。

| 文件 | 用途 |
| --- | --- |
| [kvm-guide.md](kvm-guide.md) | 普通 KVM 构建、模块加载和两种内层启动 |
| [kvm-log.md](kvm-log.md) | 组件集成、故障处理和各阶段改动记录 |
| [debian-guest.md](debian-guest.md) | Debian 镜像来源、校验、旧手动初始化和联网检查 |
| [qemu-network.md](qemu-network.md) | QEMU 用户态网络及 libslirp 构建 |

下一阶段在这条虚拟化链中加入 [PMP.Virt 保护](../03-pmp-virt-kvm/README.md)。
