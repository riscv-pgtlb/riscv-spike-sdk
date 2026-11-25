# QEMU: G-stage Virt 实现

```text
最终权限 =
第一阶段权限
∩ 修改后的 G-stage权限
∩ PMP权限
```

例如：

```text
G-stage PTE = V | U | R | A | D | STAGE2_VIRT

VS：只能读
VU：G-stage层获得 RWX
```

> 但如果 VU第一阶段页表只有 RX，最终仍然只有 RX，Stage2Virt不能绕过第一阶段页表。

## 1 修改 QEMU

```text
repo/qemu/target/riscv/cpu_bits.h    // 定义 PTE_STAGE2_VIRT
repo/qemu/target/riscv/cpu_cfg.h     // 增加 x_stage2_virt
repo/qemu/target/riscv/cpu.c         // 注册 x_stage2_virt
repo/qemu/target/riscv/cpu_helper.c  // 拒绝非叶 G-stage PTE设置该位
                                     // 只在 G-stage解释该位
                                     // VU获得 G-stage层的 RWX，VS保留基础权限
```

### 1.1 定义最终 G-stage PTE位

Host KVM在建立或修改 G-stage PTE时写入，QEMU在第二阶段地址翻译时读取。

修改：[cpu_bits.h](../../repo/qemu/target/riscv/cpu_bits.h) 727行

增加：

```c
/*
 * Local experimental G-stage attribute.
 * Uses RSW[0] and is interpreted only for G-stage leaf PTEs when
 * x-stage2-virt is enabled.
 */
#define PTE_STAGE2_VIRT     0x100
```

作用：

- **占用 RSW[0] 作为实验位**。
- Host KVM通过该位标记需要 VU 权限补足的 G-stage 页。
- 第一阶段页表仍忽略这个位。
- CPU开关关闭时，QEMU也按普通 RSW位忽略它。

> 不要使用 PTE高位，因为可能与 PBMT、NAPOT及保留位检查冲突。

### 1.2 增加最终 CPU开关

**为了让 QEMU明确知道：是否把 G-stage PTE的 RSW[0]解释成 STAGE2_VIRT。**

修改：[cpu_cfg.h](../../repo/qemu/target/riscv/cpu_cfg.h) 24

增加：

```c
bool x_stage2_virt;
```

修改：[cpu.c](../../repo/qemu/target/riscv/cpu.c) 2613

增加：

```c
DEFINE_PROP_BOOL("x-stage2-virt", RISCVCPU, cfg.x_stage2_virt, false),
```

通过 `-cpu ...,x-stage2-virt=on` 显式开启；默认关闭，保持标准 QEMU行为。

**最终启动参数将类似**：

```bash
-cpu rv64,h=true,smepmp=off,x-pmp-virt=on,x-stage2-virt=on
```

### 1.3 限制合法运行环境

在 QEMU启动 CPU时检查：用户打开 x-stage2-virt 后，**当前环境是否具备运行条件**。

修改：[cpu.c](../../repo/qemu/target/riscv/cpu.c) 940

增加：

```c
if (cpu->cfg.x_stage2_virt && 
    (!tcg_enabled() || !riscv_has_ext(&cpu->env, RVH) || !cpu->cfg.mmu)) {
    error_setg(errp, "x-stage2-virt requires TCG, H extension and MMU");
    return;
}
```

条件：

1. 启用 x_stage2_virt
2. **如果没有使用TCG，或没有H扩展，或没有MMU，报错**

### 1.4 保留访问最初来自 VS还是 VU

当前第二阶段翻译固定传入 `MMUIdx_U`：[cpu_helper.c](../../repo/qemu/target/riscv/cpu_helper.c) 1810

因此第二阶段 walker内部的：

```c
mode = mmuidx_priv(mmu_idx);
```

**永远得到 `PRV_U`，无法判断原访问来自 VS还是 VU**。

1. **修改函数签名**

修改：[cpu_helper.c](../../repo/qemu/target/riscv/cpu_helper.c) 1187

```c
static int get_physical_address(...
                                int mmu_idx,
                                int guest_priv,   // 新增
                                bool first_stage,
                                ...)
```

其中：

```text
guest_priv == PRV_S → 原访问来自 VS
guest_priv == PRV_U → 原访问来自 VU
```

2. **修改函数全部调用点**: [cpu_helper.c](../../repo/qemu/target/riscv/cpu_helper.c) 


### 1.5 增加统一的 Stage2Virt 判定

**判定当前 PTE是否应该启用 Stage2Virt语义**。

在 [cpu_helper.c](../../repo/qemu/target/riscv/cpu_helper.c) 附近增加内部辅助函数：

```c
static bool stage2_virt_active(CPURISCVState *env,
                               bool first_stage,
                               bool two_stage,
                               target_ulong pte)
{
    return riscv_cpu_cfg(env)->x_stage2_virt &&
           !first_stage &&
           two_stage &&
           (pte & PTE_STAGE2_VIRT);
}
```

**四个条件必须同时满足**：

- CPU开关打开
- 并且不是第一阶段
- 并且属于两阶段翻译
- 并且PTE设置了Stage2Virt

### 1.6 限制该位只能出现在 G-stage叶子 PTE

当前叶子判断：[cpu_helper.c](../../repo/qemu/target/riscv/cpu_helper.c)

```c
if (pte & (PTE_R | PTE_W | PTE_X)) {
    goto leaf;
}
```

在继续下一级页表前增加：**如果不是叶子却设置了Stage2Virt，就立即拒绝**
> 只有“至少带一个基础R/W/X权限”的最终映射页才能使用Stage2Virt

```c
if (stage2_virt_active(env, first_stage, two_stage, pte)) {
    qemu_log_mask(LOG_GUEST_ERROR,
                  "stage2-virt set in non-leaf G-stage PTE: "
                  "addr: 0x%" HWADDR_PRIx
                  " pte: 0x" TARGET_FMT_lx "\n",
                  pte_addr, pte);
    return TRANSLATE_FAIL;
}
```

### 1.7 在 G-stage权限检查中给 VU补足 RWX

[cpu_helper.c](../../repo/qemu/target/riscv/cpu_helper.c:1477)

**同一个 G-stage页，对 VS和 VU提供不同权限**：

```txt
VS → 保持基础权限R
VU → 补足为RWX
```

```c
if (stage2_virt_active(env, first_stage, two_stage, pte) &&
    guest_priv == PRV_U) {
    prot |= PAGE_READ | PAGE_WRITE | PAGE_EXEC;
}
```

## 2 测试

### 2.1 QEMU

**增加最小 Stage2Virt测试**：

添加一个 bare-metal RV64 TCG测试，**不经过 Linux/KVM**。

用于在裸机环境下验证 QEMU 的 G-stage.Virt 是否正确区分 VS/VU 权限。

新增测试文件：[stage2-virt.S](../../repo/qemu/tests/tcg/riscv64/stage2-virt.S)

```text
repo/qemu/tests/tcg/riscv64/stage2-virt.S
```

修改：

```text
repo/qemu/tests/tcg/riscv64/Makefile.softmmu-target
```

**测试内容：**

- 建立 Sv39x4 G-stage页表；
- 目标页设置为 R|U|A|D|STAGE2_VIRT；
- VU 读、写、执行成功；
- VS 读成功；
- VS 写触发 STORE_GUEST_PAGE_FAULT；
- VS 执行触发 INST_GUEST_PAGE_FAULT；
- 通过 semihosting 返回测试结果。


### 2.2 增加 SDK包装脚本
为将 QEMU G-stage.Virt 语义测试接入 SDK 的统一测试流程，新增 Stage2Virt 包装脚本，并调整 Virt 汇总测试入口。

新增脚本：

```
tests/G-stage-virt/check-stage2-virt-qemu.sh
```

该脚本依次完成：


```
使用 RISC-V 工具链编译 stage2-virt.S；
链接生成裸机测试程序；
启用 x-stage2-virt 运行正向测试，要求返回码为 0;
关闭 x-stage2-virt 运行负向对照，要求返回非 0;
正负向测试均符合预期后输出：
QEMU Stage2Virt语义测试 PASS
```

统一汇总入口调整为：tests/run-suite.py

该入口同时包含：

- PMP.Virt 汇总测试；
- Stage2Virt QEMU 语义测试；
- 构建产物校验；
- 双 Debian 或 Buildroot 回归测试。

Makefile调整如下：

```makefile
make virt-test-static # 执行 SDK 单元测试和 Stage2Virt 静态语义测试。
make virt-test        # 执行 tests/run-suite.py，完成全部 Virt 汇总测试。
```

同时删除原有重复入口 virt-test-stage2 和 virt-test-buildroot，避免测试入口分散和命名重复。

> 构建校验脚本 scripts/build/virt-kvm.py 增加以下输入文件：
> ```
> tests/run-suite.py
> tests/G-stage-virt/check-stage2-virt-qemu.sh
> repo/qemu/tests/tcg/riscv64/stage2-virt.S
> ```
> 这样包装脚本、总汇总入口和 QEMU 测试源文件发生变化时，构建产物校验能够正确检测到变化。
