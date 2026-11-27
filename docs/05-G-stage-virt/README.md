# G-stage Virt / Stage2Virt 实验文档

本目录记录 RISC-V G-stage Virt（代码中统一命名为 Stage2Virt）从 QEMU 权限语义、Host KVM 接口、kvmtool 配置，到 Linux Guest `VU → VS → VU` 真实运行验证的完整实现过程。

## 1. 这次完成了什么工作

本次工作的重点不是单独增加一个测试脚本，而是把 Stage2Virt 从模拟器一直贯通到 Guest 用户态，形成可以真实运行、自动判定和重复验证的完整系统。

### 1.1 实现 QEMU 的 G-stage Virt 权限功能

完成以下功能：

- 在 G-stage PTE 中定义 Stage2Virt 属性位；
- 增加 x-stage2-virt CPU 开关；
- 在两阶段地址转换中保留访问最初来自 VS 还是 VU；
- 限制 Stage2Virt 只能出现在合法 G-stage 叶子 PTE；
- 在 G-stage 权限检查中，Stage2Virt 只给 VU 补足 R/W/X，VS 忽略该位；
- 增加开关正向、反向语义测试。

最终效果：

    同一 G-stage 页面
    VU 可以获得 Stage2Virt 委托权限
    VS 仍然只能使用基础 R/W/X 权限

### 1.2 实现 Host Linux/KVM 控制接口

完成以下功能：

- 增加 KVM_CAP_RISCV_STAGE2_VIRT capability；
- 增加 KVM_RISCV_SET_STAGE2_VIRT VM ioctl；
- 定义用户态请求结构，包含 GPA、size、flags 和保留字段；
- 为每个 VM 保存独立的 Stage2Virt 范围和启用状态；
- 校验对齐、范围溢出、GPA 空间和 dirty logging 冲突；
- 配置改变时清除旧 G-stage 映射；
- 缺页重建时根据 VM 状态重新生成 Stage2Virt PTE；
- 增加 Host KVM 真实 selftest。

最终效果：Host 用户态可以通过 /dev/kvm 为指定 Guest GPA 范围启用或关闭 Stage2Virt。

### 1.3 实现 kvmtool 静态和动态配置

完成两个相互独立的运行模式：

    --stage2-virt
        启动前由命令行指定 GPA 和 size

    --stage2-virt-test
        Guest 启动后通过 SBI 动态报告 GPA 和 size

动态测试模式实现三个操作：

- BEGIN：检查会话、GPA 和 size，然后调用 Host KVM ioctl 启用范围；
- COMPLETE：核对 GPA/size，关闭 Host 范围并重置会话；
- ABORT：清除活动范围和本地状态；
- vCPU 退出时自动清理没有结束的会话。

### 1.4 实现 Linux Guest 内核测试设备

新增设备：

    /dev/stage2_virt_test

设备提供 mmap 和五个 ioctl：

| ioctl | 功能 |
| --- | --- |
| GET_INFO | 向 VU 返回测试页 GPA 和大小 |
| BEGIN | 通过 SBI 请求 kvmtool 启用该 GPA 的 Stage2Virt |
| VS_PROBE | 由 Guest 内核 VS 探测同一页面，要求出现预期访问失败 |
| COMPLETE | 检查 VU 最终值并通过 SBI 清除范围 |
| ABORT | 异常路径清理活动会话 |

设备还实现单实例打开、会话状态机、无故障内核访问、mmap 限制和关闭时自动清理。

### 1.5 实现 Guest VU 用户态测试程序

新增静态用户程序，通过 mmap 和 ioctl 完成以下过程：

    1. 获取测试页 GPA
    2. 将内核测试页映射到 VU
    3. BEGIN 启用 Stage2Virt
    4. VU 写入 0x5a 并确认成功
    5. VS_PROBE 访问同一 GPA，确认被拒绝
    6. VU 再写入 0xa5 并确认成功
    7. COMPLETE 清除 Stage2Virt

该程序证明的不是两个不同页面，而是同一个 GPA 上 VU 成功、VS 受限、VU 再次成功。

### 1.6 接入 SDK 构建和统一回归

完成以下集成：

- SDK 自动启用 Guest 内核配置；
- 使用 Guest 安装后的 UAPI header 编译静态 VU 程序；
- 将内核、程序和检查器打包到 Buildroot 与 Debian Guest；
- 回归启动时自动传入 --stage2-virt-test 和 stage2virt_guest_test=1；
- 将 Stage2Virt Guest 测试加入统一24项回归；
- 统一解析器检查日志顺序、唯一性、同 GPA 和 Guest 生命周期；
- 内层 Guest 日志通过 FIFO 和 tee 实时显示并保存；
- 静态测试统一为逐项 TEST/PASS 输出。

## 2. 交付的功能

完成后的系统具备以下可直接使用的能力：

| 功能 | 使用入口 | 结果 |
| --- | --- | --- |
| QEMU Stage2Virt 模拟 | x-stage2-virt=on | 区分 VS/VU 权限 |
| Host KVM 范围配置 | KVM_RISCV_SET_STAGE2_VIRT | 动态更新 G-stage 策略 |
| kvmtool 静态模式 | --stage2-virt GPA,size | 启动前配置固定范围 |
| kvmtool动态模式 | --stage2-virt-test | 接收 Guest SBI 会话 |
| Guest 内核接口 | /dev/stage2_virt_test | mmap 与五个 ioctl |
| Guest 用户程序 | stage2-virt-guest-test | 执行 VU→VS→VU 测试 |
| 自动回归 | make virt-test | Buildroot/Debian 统一验收 |

第一版单 hart、单页 Stage2Virt 软件原型已经完成，最终验证日期为2026-11-27。

## 3. 功能如何串联

```txt
VU 用户程序
    │ mmap + ioctl
    ▼
Linux Guest /dev/stage2_virt_test
    │ SBI BEGIN / COMPLETE / ABORT
    ▼
kvmtool Stage2Virt SBI handler
    │ KVM_RISCV_SET_STAGE2_VIRT
    ▼
Host Linux KVM
    │ 更新范围状态、清除旧映射、重建 G-stage PTE
    ▼
QEMU G-stage 权限检查
    │ 根据真实 priv/V 区分 VS 与 VU
    ▼
VU 允许访问，VS 对同一 GPA 的目标访问被拒绝
```

运行时测试顺序：

```txt
VU BEFORE（写入 0x5a）
→ SBI BEGIN（报告 GPA/size）
→ VS PROBE（同一 GPA 预期访问失败）
→ VU AFTER（写入 0xa5）
→ SBI COMPLETE（清除 Stage2Virt 范围）
→ SAME-PAGE PASS
```

统一结果解析器要求各阶段顺序固定、只出现一次且 GPA 完全相同。

## 4. 具体修改的代码

### QEMU

```txt
repo/qemu/target/riscv/
repo/qemu/tests/tcg/riscv64/stage2-virt.S
tests/G-stage-virt/check-stage2-virt-qemu.sh
```

### Host Linux/KVM

```txt
repo/linux/arch/riscv/kvm/
repo/linux/arch/riscv/include/uapi/asm/kvm.h
tests/G-stage-virt/check-stage2-virt-host.sh
```

### kvmtool

```txt
repo/kvmtool/riscv/stage2-virt.c
repo/kvmtool/riscv/stage2-virt-test.c
repo/kvmtool/riscv/include/kvm/stage2-virt.h
repo/kvmtool/riscv/include/kvm/stage2-virt-test.h
repo/kvmtool/tests/stage2-virt-test.py
repo/kvmtool/tests/stage2-virt-runtime-test.py
```

### Linux Guest

```txt
repo/linux-guest/arch/riscv/kernel/stage2_virt_guest_test.c
repo/linux-guest/arch/riscv/include/uapi/asm/stage2_virt_test.h
tests/G-stage-virt/stage2-virt-guest-test.c
tests/G-stage-virt/check-stage2-virt-guest.sh
```

### SDK 构建与回归

```txt
scripts/build/virt-kvm.py
tests/run-suite.py
tests/pmp-virt/regression/buildroot/test-virt-all.sh
tests/pmp-virt/regression/debian/test-virt-debian-all.sh
```

## 5. 完成的验证工作

检查源码、版本锁和构建环境：

```bash
make virt-check
```

完整构建并校验产物：

```bash
make virt-build
make virt-verify
```

运行静态测试：

```bash
make virt-test-static
```

运行 Buildroot 完整回归：

```bash
make virt-test VIRT_SYSTEM=buildroot VIRT_TIMEOUT=600
```

运行双 Debian 完整回归：

```bash
make virt-test VIRT_SYSTEM=debian VIRT_TIMEOUT=600
```

最终结果：

```txt
静态测试：5/5 组 PASS
Buildroot：24/24 PASS，30.46 秒
双 Debian：24/24 PASS，139.65 秒
```

详细证据和结果解释见 [最终验证报告](5-validation.md)。

## 6. 分支与版本

```txt
riscv-spike-sdk
branch: dual-debian-G-stage-virt
commit: 6db3c335d2ec668278d1d03f5d08377920bc40de

kvmtool
branch: stage2-virt
commit: 100131a46d9b852f29370ff18d07204c47d1a3a0

linux-guest
branch: G-stage-virt-guest
commit: eb0b925e4e4e4faf625089dc9ce445d9f9ba2685
```

SDK 的 `conf/virt/sources.json` 使用提交哈希锁定组件，不依赖远端分支名称。

## 7. 验证边界

当前结论覆盖单 vCPU、单页、4 KiB 对齐范围及完整 BEGIN/COMPLETE 会话。以下内容属于后续扩展：

- 多 vCPU 与多 hart 并发；
- 多页、不连续范围和大页拆分；
- KVM dirty logging 等高级功能兼容；
- DMA/IOMMU 隔离；
- Spike 独立参考实现；
- 性能、形式化和真实硬件验证。

这些边界不影响第一版 Linux Guest Stage2Virt 端到端实验已经完成的结论。

## 8. 组会汇报结论

本次工作完成了从 QEMU、Host KVM、kvmtool、Guest 内核到 VU 程序的跨层实现，并建立了真实运行测试和自动回归，而不是只完成接口定义或 mock。

最终形成的闭环是：

    Guest 动态报告 GPA
    → kvmtool 建立运行时会话
    → Host KVM 更新 G-stage 策略
    → QEMU 按真实 VS/VU 身份执行权限判断
    → VU 成功、VS 受限、VU 再次成功
    → COMPLETE 清除范围
    → Guest 退出后 Host 复测通过

实验结果：

    静态测试：5/5 组 PASS
    Buildroot：24/24 PASS
    双 Debian：24/24 PASS

## 9. 详细文档

| 顺序 | 文档 | 内容 |
| ---: | --- | --- |
| 1 | [QEMU: G-stage Virt 实现](1-qemu.md) | QEMU 权限位、身份传递和权限检查 |
| 2 | [Host Linux: G-stage Virt 实现](2-host-linux.md) | KVM UAPI、VM 状态和 G-stage 映射 |
| 3 | [kvmtool: G-stage Virt 实现](3-kvmtool.md) | 命令行、配置模块和 VM 初始化 |
| 4 | [Guest Linux: G-stage Virt 实现](4-guest-linux.md) | SBI 握手、内核设备、VU 程序和回归 |
| 5 | [Stage2Virt Linux Guest 最终验证报告](5-validation.md) | 完整测试结果、问题修复和验证边界 |
