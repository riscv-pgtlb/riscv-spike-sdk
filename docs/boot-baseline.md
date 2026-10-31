# Baseline A1: 普通启动基线

本页保存同学交付 A1 时的历史验证状态，不代表当前 KVM 集成进度。
当前操作入口和验证结果见 [kvm.md](kvm.md)。

## 当前状态
- **已验证**：OpenSBI -> Linux 6.17.2 -> initramfs -> root shell 的启动链跑通。
- **已验证**：新 rootfs 的 devtmpfs 挂载和设备节点正常。
- **未验证**：PMP.Virt 模拟器扩展、KVM 模块加载与 guest 启动。

## 组件版本
- QEMU: v10.1.0 (独立于本 SDK 编译)
- Linux: v6.17.2 (Image.config 内嵌已确认，源码提交来源待核实)
- OpenSBI: v1.7
- 工具链: 编译内核与系统时的外部工具链 (GCC 版本待核实)
- Buildroot: 2025.08 (提交 3386677f0a4d1c0150e772eb07cede05e88a2d6d)

## 构建与启动
原脚本已移动至 `scripts/base/run-qemu-baseline.sh` 和
`scripts/base/pack-rootfs.sh`。其中可能仍有原机器路径，尚未重新验证，
请优先使用当前 KVM 操作指南中的 Makefile 入口。

*注：目前为已验证的启动基线，尚未完成从源码重建的验证。*



