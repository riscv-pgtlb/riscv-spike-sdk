# 第三阶段：PMP.Virt + KVM

目标是让 OpenSBI 与 host Linux 配合封存 PMP.Virt 规则，运行普通 KVM guest，并在 guest 返回后复测 host 保护。
核心改动直接维护在 QEMU、Linux、OpenSBI 团队子模块，版本锁见项目根目录的 `conf/pmp-virt/sources.json`。
本阶段的构建产物也供 [双 Debian](../04-dual-debian/README.md) 使用。

## 文件与目录

| 文件或目录 | 用途 |
| --- | --- |
| 本 README | 组件构建、Buildroot 回归入口与验证边界 |
| [test-suite.md](test-suite.md) | 一条 make 命令集成已有检查，选择双 Debian 或 Buildroot，逐项汇总并归档 |
| [pmp-virt-explained.md](pmp-virt-explained.md) | PMP.Virt 原理、QEMU/OpenSBI/Linux 改动、运行步骤和测试调用链 |
| [validation/](validation/README.md) | 历史 B1 验证材料导航及当前缺失说明 |

## 构建

在项目根目录操作。可用交叉工具链和基础 Buildroot rootfs 需提前准备；按本机路径设置 `CROSS_COMPILE`（如有需要）和 `BASE_ROOTFS`。

```sh
git submodule sync -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
git submodule update --init --depth=1 -- repo/qemu repo/linux repo/opensbi repo/dtc repo/kvmtool
export BASE_ROOTFS="$PWD/images/base/rootfs.cpio.gz"
make virt-test-static
make virt-check
make virt-prepare
make virt-build VIRT_JOBS=4
make virt-verify
```

逐条确认成功后继续。工具链检查会实际验证静态 RISC-V 链接；显式指定的工具链失效会停止。
构建入口为 `scripts/build/virt-kvm.py`，产物统一位于 `build/virt-kvm/`。
普通 guest 使用独立源码和输出，不与受保护 host 共用内核输出。

host Image 和 System.map 决定生成的保护布局，OpenSBI 固件包含对应 Image 摘要；不能任意混用内核与固件。
`virt-verify` 检查产物摘要和布局配对，不检查 Debian 整盘及已安装工具版本。
镜像摘要用于构建配对，不表示运行时密码学认证。

## Buildroot 回归

```sh
make virt-test
```

服务器驱动 QEMU，串联 host 检查、普通 Buildroot guest 内存和时间推进检查、guest 关机和 host 同页复测。
日志在 `build/virt-kvm/logs/regression-*/`，包括控制台、产物清单、结果和校验值。
需调整超时时执行：

```sh
python3 tests/pmp-virt/regression/buildroot/run-regression.py --timeout 600
```

手动运行使用 `make run-virt-host`，外层执行 `check-virt-host`、`run-virt-guest`。
Buildroot 外层加 Debian 内层的入口为 `make run-virt-debian-host`，外层执行 `run-virt-debian`；旧镜像准备记录见 [第二阶段](../02-ordinary-kvm/debian-guest.md)。

## 范围

当前单 hart、2 GiB host RAM，H 扩展开启、Smepmp 关闭、PMP.Virt 开启。
HS 6/6 与 SBI guard 18/18 来自 host 启动检查，guest 返回后实际重新执行的是同页 U → HS → U 测试。
没有据此证明 G-stage.Virt、VS/VU 权限配对、多核、压力测试或完整服务防绕过审计。
本次目录整理没有重新执行虚拟机回归。
