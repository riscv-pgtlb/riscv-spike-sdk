# G-stage Virt / Stage2Virt 实验文档

本目录记录 RISC-V G-stage Virt（代码中统一命名为 Stage2Virt）**从 QEMU 权限语义、Host KVM 接口、kvmtool 配置，到 Linux Guest `VU → VS → VU` 真实运行**验证的完整实现过程。

## 1. 这次完成了什么工作

本次工作的重点不是单独增加一个测试脚本，而是把 Stage2Virt 从模拟器一直贯通到 Guest 用户态，形成可以真实运行、自动判定和重复验证的完整系统。

### 1.1 实现 QEMU 的 G-stage Virt 权限功能

> [cpu_bits.h](../../repo/qemu/target/riscv/cpu_bits.h): 定义 G-stage PTE 中使用的 Stage2Virt 属性位。
> [cpu_cfg.h](../../repo/qemu/target/riscv/cpu_cfg.h): 在 QEMU CPU 配置中保存 Stage2Virt 是否启用。
> [cpu.c](../../repo/qemu/target/riscv/cpu.c): 定义 x-stage2-virt CPU 参数，使启动命令可以开启或关闭该功能。
> [cpu_helper.c](../../repo/qemu/target/riscv/cpu_helper.c): 根据VS/VU真实身份执行权限判断
> [stage2-virt.S](../../repo/qemu/tests/tcg/riscv64/stage2-virt.S): QEMU 裸机语义测试，验证开启和关闭 Stage2Virt 时的权限结果是否符合预期。

在 QEMU 中完成 **G-stage Virt 的硬件语义模拟**：

1. 为 G-stage PTE 定义 Stage2Virt 属性位，增加 **x-stage2-virt** CPU 开关
2. 在两阶段地址转换过程中保留访问最初来自 VS 还是 VU，并限制该属性只能出现在合法的 G-stage 叶子 PTE 中；
3. 权限检查时，**根据处理器内部真实的 priv/V 身份决定是否应用 Stage2Virt**
   1. 其中 VU 可以在基础权限上获得 Stage2Virt 委托的 R/W/X 权限
   2. VS 则忽略该位、仍然只能使用基础权限。

QEMU 运行时启用

```bash
-cpu rv64,h=true,x-stage2-virt=on
```

并由 Host 将目标 G-stage PTE 配置为 `R=1、W=0、X=0、Stage2Virt=1` 后，同一 GPA 页面表现为“VU 获得补充的 R/W/X 权限，而 VS 仍只有基础 R 权限”，因此 VU 写入或执行成功，VS 写入或执行触发 G-stage page fault。

### 1.2 实现 Host Linux/KVM 控制接口

> [kvm.h](../../repo/linux/include/uapi/linux/kvm.h): 定义 Stage2Virt capability 和 ioctl，使 kvmtool 能够调用 Host KVM。
> [kvm_host.h](../../repo/linux/arch/riscv/include/asm/kvm_host.h): 保存每个虚拟机的 Stage2Virt 开关和 GPA 范围。
> [vm.c](../../repo/linux/arch/riscv/kvm/vm.c): 接收 kvmtool 的 ioctl，检查参数、保存配置并删除旧映射，是主要控制入口。
> [mmu.c](../../repo/linux/arch/riscv/kvm/mmu.c): Guest 发生缺页时，判断目标 GPA 是否需要应用 Stage2Virt。
> [gstage.c](../../repo/linux/arch/riscv/kvm/gstage.c): 根据判断结果生成真正带有 Stage2Virt 权限的 G-stage PTE。

在 Host Linux/KVM 中**实现 Stage2Virt 的可信控制接口**：

1. 在 KVM 中**增加 Stage2Virt 能力查询和控制接口**，使 kvmtool 可以告诉 Host：为哪个 Guest GPA 范围开启或关闭 Stage2Virt，并由每个虚拟机单独保存自己的配置。

2. KVM 收到请求后，会检查地址和大小是否合法、是否越界或与 dirty logging 冲突

3. 配置发生变化时删除旧的 G-stage 映射，之后重新映射页面时自动带上新的 Stage2Virt 权限，最后通过真实 KVM selftest 验证接口能够正常工作。

完成后，**Host 用户态能够通过 `/dev/kvm` 为指定 Guest GPA 范围动态启用或关闭 Stage2Virt**，而 Guest 不能直接修改这份 Host 策略。

### 1.3 实现 kvmtool 静态和动态配置

> [stage2-virt.c](../../repo/kvmtool/riscv/stage2-virt.c): 面向 Host KVM，负责向下调用 /dev/kvm ioctl，真正开启或关闭 Stage2Virt
> [stage2-virt-test.c](../../repo/kvmtool/riscv/stage2-virt-test.c): 面向 Guest 请求，接收 Guest 发出的 SBI BEGIN、`COMPLETE`、`ABORT`，维护测试状态，再调用 stage2-virt.c 操作 Host KVM。
> [stage2-virt-test.h](../../repo/kvmtool/riscv/include/kvm/stage2-virt-test.h): 定义 SBI 扩展编号和 BEGIN、`COMPLETE`、`ABORT` 操作编号。

**在 kvmtool 中提供两种使用方式**：

```bash
--stage2-virt       # 启动虚拟机前，手动指定要保护的 GPA 和大小
--stage2-virt-test  # 虚拟机启动后，由 Guest 自动报告测试页的 GPA 和大小
```

动态测试模式只允许一个 vCPU 使用，并通过三个操作管理一次测试：

- BEGIN：Guest 报告测试页，kvmtool 通知 Host KVM 开启 Stage2Virt。
- COMPLETE：测试完成后，kvmtool 检查地址是否一致并关闭 Stage2Virt。
- ABORT：测试异常时清理配置；如果虚拟机提前退出，也会自动清理。

**简单来说，kvmtool 负责把 Guest 发来的请求转换成 Host KVM 能理解的控制命令。**


### 1.4 实现 Linux Guest 内核测试设备

> 内核设备实现：[stage2_virt_guest_test.c](../../repo/linux-guest/arch/riscv/kernel/stage2_virt_guest_test.c)
> 用户态接口定义：[stage2_virt_test.h](../../repo/linux-guest/arch/riscv/include/uapi/asm/stage2_virt_test.h)

在 Linux Guest 内核中**新增 `/dev/stage2_virt_test` 测试设备，并准备一张由 VS 内核和 VU 程序共同访问的测试页**。

VU 通过 mmap 映射该页面，再使用五个 ioctl 完成测试：

- GET_INFO：获取测试页的 GPA 和大小。
- BEGIN：通知 kvmtool 为该页面开启 Stage2Virt。
- VS_PROBE：让 Guest 内核以 VS 身份访问该页，确认访问被拒绝。
- COMPLETE：检查 VU 最终写入结果并关闭 Stage2Virt。
- ABORT：测试异常时清理状态。

简单来说，这个设备负责提供同一张测试页，并协调 VU、VS 和 kvmtool 完成一次完整的 Stage2Virt 权限测试；即使测试中途失败或程序退出，也会自动清理。

### 1.5 实现 Guest VU 用户态测试程序

> [stage2-virt-guest-test.c](../../tests/G-stage-virt/stage2-virt-guest-test.c): 调用 Guest 内核提供的设备接口，进行同一 GPA 页面上的 VU → VS → VU 权限对照测试
> 运行结果检查器：[check-stage2-virt-guest.sh](../../tests/G-stage-virt/check-stage2-virt-guest.sh)

在 Guest 用户空间**新增 VU 测试程序**，用同一张测试页完成以下过程：

1. 获取测试页的 GPA 和大小，并通过 mmap 映射。
2. 调用 BEGIN 开启 Stage2Virt。
3. VU 写入 0x5a，确认 VU 可以访问。
4. 调用 VS_PROBE，确认 VS 访问同一页面时被拒绝。
5. VU 再写入 0xa5，确认测试后仍可正常访问。
6. 调用 COMPLETE 关闭 Stage2Virt。

简单来说，该程序验证了同一个 GPA 页面能够实现：**VU 访问成功 → VS 访问失败 → VU 再次访问成功**。

### 1.6 接入 SDK 构建和统一回归

在 SDK 中**把 Stage2Virt 测试接入自动构建和统一回归**：

1. 构建时**自动开启 Guest 内核测试配置**，并编译 VU 测试程序。
2. 将 Guest 内核、VU 程序和检查脚本打包到 Buildroot 与 Debian。
3. 启动测试时，自动为 kvmtool 添加 `--stage2-virt-test`，并为 Guest 内核添加 stage2virt_guest_test=1。
4. 将 VU → VS → VU 测试加入24项统一回归。
5. 检查各阶段是否顺序正确、使用同一 GPA，并且没有重复或失败日志。
6. 实时显示并保存内层 Guest 日志，方便定位问题。

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
   │ 通过 mmap 映射测试页，使用 ioctl 发起测试
   ▼
Linux Guest /dev/stage2_virt_test
   │ 提供共享测试页，并通过 SBI 发送 BEGIN / COMPLETE / ABORT
   ▼
kvmtool Stage2Virt SBI handler
   │ 接收 Guest 请求，并转换为 KVM_RISCV_SET_STAGE2_VIRT ioctl
   ▼
Host Linux KVM
   │ 保存目标 GPA 范围、清除旧映射并重建 G-stage PTE
   ▼
QEMU G-stage 权限检查
   │ 根据处理器内部真实的 priv/V 区分 VS 与 VU
   ▼
最终结果
   └─ VU 可以访问，VS 对同一 GPA 的目标访问被拒绝
```

运行时测试顺序：

```txt
VU 先向测试页写入 0x5a，确认可以正常访问
→ Guest 报告这张测试页的 GPA 和大小，开启 Stage2Virt
→ VS 尝试访问同一张页面，确认访问被拒绝
→ VU 再次向同一张页面写入 0xa5，确认仍可正常访问
→ 测试完成后关闭 Stage2Virt 并清理配置
→ 同一页面上的“VU 成功、VS 失败、VU 再次成功”测试通过
```

统一结果解析器要求各阶段顺序固定、只出现一次且 GPA 完全相同。


当前回归测试：

```txt
make virt-test VIRT_SYSTEM=debian
└─ tests/run-suite.py
   ├─ 静态与接口测试
   │  ├─ SDK unit 测试
   │  ├─ PMP.Virt kvmtool mock
   │  ├─ Stage2Virt 配置接口 mock
   │  ├─ Stage2Virt SBI 握手 mock
   │  └─ QEMU Stage2Virt 语义测试
   │
   ├─ 构建产物检查
   │
   └─ 双 Debian 真实运行测试
      └─ run-dual-debian.sh → QEMU → 外层 Debian Host
         │
         ├─ Host Stage2Virt 测试
         │  ├─ Host KVM Stage2Virt selftest
         │  └─ kvmtool Stage2Virt 真实 ioctl 测试
         │
         ├─ Host PMP.Virt 测试
         │  ├─ 策略封存
         │  ├─ HS RAM、text、rodata 保护
         │  ├─ SBI guard
         │  └─ HU → HS → HU
         │
         ├─ 启动内层 Debian Guest
         │  └─ lkvm --pmp-virt-test --stage2-virt-test
         │     │
         │     ├─ PMP.Virt Guest 测试
         │     │  └─ VS → HS → VS
         │     │
         │     ├─ Stage2Virt Guest 测试
         │     │  └─ stage2-virt-guest-test
         │     │     └─ VU成功 → VS失败 → VU再次成功
         │     │
         │     └─ Guest 自动关机
         │
         ├─ Guest 返回后 Host 复测
         │  └─ HU → HS → HU
         │
         └─ 外层 Debian 关机
            └─ QEMU 正常退出 → 24/24 PASS
```

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

## 8. 结论

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
