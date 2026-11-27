make virt-test
  └─ PMP.Virt ON 下的非破坏性攻击回归，默认必跑

make virt-test-security
  └─ ON/OFF 对照、破坏性载荷、压力与边界攻击


| 步骤 | 改动范围 | 结果 |
|---|---|---|
| 1 | Guest Linux UAPI与内核探针 | 增加VS写入、执行、页表别名攻击ioctl，安全捕获异常 |
| 2 | Guest用户态攻击程序 | 完成Stage2Virt OFF攻击成功、ON攻击失败的对照流程 |
| 3 | kvmtool协调 | 扩展BEGIN/COMPLETE状态机、ON/OFF切换、错误输入和异常清理 |
| 4 | Host KVM与QEMU测试 | 增加Host selftest和QEMU底层攻击语义矩阵；发现缺陷再改实现 |
| 5 | SDK统一集成 | 编译、安装、版本摘要、`run-suite.py`独立测试点和失败判定 |
| 6 | 完整验证与文档 | 运行静态、Buildroot、双Debian回归，更新版本锁和实验说明 |

如果要做“完整的 Stage2Virt syscall 攻击测试”，包括 VS 内核攻击、VU 驱动、kvmtool 协调、Stage2Virt ON/OFF 对照和 `virt-test` 自动判定，建议涉及三个子模块：

```text
repo/linux
repo/kvmtool
repo/qemu
```

其中 guest Linux 是 `repo/linux` 仓库的另一个 worktree：`repo/linux-guest`，不是单独登记的子模块。

## 一、Linux 子模块

### 1. Guest Linux：攻击 syscall/ioctl 的核心

必须修改：

- [stage2_virt_guest_test.c](/home/wsh/riscv-spike-sdk/repo/linux-guest/arch/riscv/kernel/stage2_virt_guest_test.c)
- [stage2_virt_test.h](/home/wsh/riscv-spike-sdk/repo/linux-guest/arch/riscv/include/uapi/asm/stage2_virt_test.h)

建议增加以下接口：

```c
STAGE2_VIRT_ATTACK_BEGIN
STAGE2_VIRT_ATTACK_VS_WRITE
STAGE2_VIRT_ATTACK_VS_EXEC
STAGE2_VIRT_ATTACK_COMPLETE
```

或者在现有 BEGIN/COMPLETE 之间增加：

```c
STAGE2_VIRT_TEST_VS_WRITE_ATTACK
STAGE2_VIRT_TEST_VS_EXEC_ATTACK
STAGE2_VIRT_TEST_VS_PTE_ALIAS_ATTACK
```

`stage2_virt_guest_test.c` 需要实现：

- 分配一张固定测试页。
- 返回该页 GPA。
- 允许 VU 写入固定攻击载荷。
- VS 建立明确的页表权限或别名。
- VS 尝试不同值写入。
- VS 尝试执行注入代码。
- 使用异常表捕获预期 guest page fault。
- 返回 fault 类型、攻击前后内容和执行结果。
- 限制固定目标、固定载荷、单次状态机和并发访问。
- 测试异常退出时自动清理。

如果增加新的内核源文件，还要修改：

- `/home/wsh/riscv-spike-sdk/repo/linux-guest/arch/riscv/Kconfig.debug`
- `/home/wsh/riscv-spike-sdk/repo/linux-guest/arch/riscv/kernel/Makefile`

如果直接扩展现有设备，则不用修改这两个文件。

### 2. Host Linux KVM：接口与恶意输入验证

Stage2Virt 基本权限机制已经存在。普通单页攻击可以复用现有接口，但完整实验建议补充 Host KVM 自测：

- [stage2_virt_test.c](/home/wsh/riscv-spike-sdk/repo/linux/tools/testing/selftests/kvm/riscv/stage2_virt_test.c)

覆盖：

- 启用、关闭和重复启用。
- 非对齐 GPA、零长度和整数溢出。
- RAM 范围之外的 GPA。
- 多页、跨大页边界和部分重叠。
- ON → OFF → ON 后旧 PTE/TLB 不得残留。
- 两个 VM 的范围不能互相污染。
- dirty logging 冲突不能被绕过。

如果现有 Host KVM 实现不能满足这些实验，才修改：

- `/home/wsh/riscv-spike-sdk/repo/linux/arch/riscv/kvm/vm.c`
- [mmu.c](/home/wsh/riscv-spike-sdk/repo/linux/arch/riscv/kvm/mmu.c)
- [gstage.c](/home/wsh/riscv-spike-sdk/repo/linux/arch/riscv/kvm/gstage.c)
- [kvm_gstage.h](/home/wsh/riscv-spike-sdk/repo/linux/arch/riscv/include/asm/kvm_gstage.h)
- `/home/wsh/riscv-spike-sdk/repo/linux/arch/riscv/include/uapi/asm/kvm.h`
- `/home/wsh/riscv-spike-sdk/repo/linux/include/uapi/linux/kvm.h`

原则是先写测试，只有测试暴露接口或实现缺口时再改生产逻辑。

## 二、kvmtool 子模块

完整攻击实验建议修改 kvmtool，使其明确协调攻击阶段和 ON/OFF 对照。

主要文件：

- [stage2-virt-test.c](/home/wsh/riscv-spike-sdk/repo/kvmtool/riscv/stage2-virt-test.c)
- [stage2-virt.c](/home/wsh/riscv-spike-sdk/repo/kvmtool/riscv/stage2-virt.c)
- [stage2-virt-test.h](/home/wsh/riscv-spike-sdk/repo/kvmtool/riscv/include/kvm/stage2-virt-test.h)
- [stage2-virt.h](/home/wsh/riscv-spike-sdk/repo/kvmtool/riscv/include/kvm/stage2-virt.h)

需要实现或扩展：

- 接收 guest 上报的 GPA 和长度。
- 开启 Stage2Virt 后确认配置成功。
- 支持攻击阶段开始、完成和失败清理。
- 支持保护开启和关闭两种模式。
- 检查 BEGIN/COMPLETE 的 GPA一致。
- 拒绝跨 RAM、零长度、溢出和重复状态请求。
- vCPU 或 guest 异常退出后清除 Stage2Virt 范围。

相应 mock 测试：

- [stage2-virt-runtime-test.py](/home/wsh/riscv-spike-sdk/repo/kvmtool/tests/stage2-virt-runtime-test.py)
- [stage2-virt-test.py](/home/wsh/riscv-spike-sdk/repo/kvmtool/tests/stage2-virt-test.py)

需要增加攻击状态机、ON/OFF切换、错误 GPA和异常清理测试。

## 三、QEMU 子模块

正常情况下不应为了攻击实验修改 Stage2Virt 权限实现，但完整实验应补充底层语义测试。

主要文件：

- [stage2-virt.S](/home/wsh/riscv-spike-sdk/repo/qemu/tests/tcg/riscv64/stage2-virt.S)
- `/home/wsh/riscv-spike-sdk/repo/qemu/target/riscv/cpu_helper.c`
- `/home/wsh/riscv-spike-sdk/repo/qemu/target/riscv/cpu_bits.h`

优先只扩展 `stage2-virt.S`，覆盖：

- Stage2Virt OFF：VS 写/执行按普通 G-stage 权限工作。
- Stage2Virt ON：VU 获得委派权限，VS 仍被拒绝。
- 第一阶段 PTE 拒绝时，Stage2Virt不能绕过。
- Stage2Virt 位设置在非叶 PTE 时被拒绝。
- 非法叶 PTE 权限组合。
- 读、写、执行三种访问。
- 4 KiB页与大页边界。

只有测试发现 QEMU权限判断错误，才修改 `cpu_helper.c` 等实现。

Stage2Virt 不依赖 OpenSBI，因此这个攻击实验通常不修改 `repo/opensbi`。

## 四、SDK主仓库

### 1. Guest 用户态攻击程序

必须修改：

- [stage2-virt-guest-test.c](/home/wsh/riscv-spike-sdk/tests/G-stage-virt/stage2-virt-guest-test.c)

建议实现两轮对照：

```text
Stage2Virt OFF
  VS写入应成功
  VS执行载荷应成功

Stage2Virt ON
  VS写入应产生预期故障
  VS执行载荷应产生预期故障
  页面内容保持不变
```

如果不希望同一进程同时承担功能和攻击测试，可以新增：

```text
tests/G-stage-virt/stage2-virt-attack.c
```

### 2. Guest检查入口

修改：

- [check-stage2-virt-guest.sh](/home/wsh/riscv-spike-sdk/tests/G-stage-virt/check-stage2-virt-guest.sh)

要求完整输出，例如：

```text
Stage2Virt ATTACK CONTROL VS-WRITE SUCCESS
Stage2Virt ATTACK CONTROL VS-EXEC SUCCESS
Stage2Virt ATTACK PROTECTED VS-WRITE PASS
Stage2Virt ATTACK PROTECTED VS-EXEC PASS
Stage2Virt ATTACK BYTES UNCHANGED
Stage2Virt ATTACK SUMMARY: PASS
```

### 3. Buildroot与Debian回归

如果继续通过现有 guest checker 运行，下面文件通常只需确认参数，不一定改：

- [virt-guest-autorun.sh](/home/wsh/riscv-spike-sdk/tests/pmp-virt/regression/buildroot/virt-guest-autorun.sh)
- [test-virt-debian-all.sh](/home/wsh/riscv-spike-sdk/tests/pmp-virt/regression/debian/test-virt-debian-all.sh)
- [virt-guest-test.service](/home/wsh/riscv-spike-sdk/tests/pmp-virt/regression/debian/virt-guest-test.service)

如果新增独立二进制或启动参数，就需要同步修改这些入口。

### 4. 构建和部署

修改或核对：

- [virt-kvm.py](/home/wsh/riscv-spike-sdk/scripts/build/virt-kvm.py)
- `/home/wsh/riscv-spike-sdk/scripts/debian/install/tool-manifest.py`
- `/home/wsh/riscv-spike-sdk/conf/virt/linux.config`

如果扩展现有二进制，构建规则可能无需变化；如果新增 `stage2-virt-attack`，必须增加编译、安装、摘要和产物校验。

### 5. 统一测试和单元测试

必须修改：

- [run-suite.py](/home/wsh/riscv-spike-sdk/tests/run-suite.py)
- [test_stage2_virt_guest.py](/home/wsh/riscv-spike-sdk/tests/pmp-virt/unit/test_stage2_virt_guest.py)
- [test_stage2_virt_integration.py](/home/wsh/riscv-spike-sdk/tests/pmp-virt/unit/test_stage2_virt_integration.py)
- [test_pmpvirt_suite.py](/home/wsh/riscv-spike-sdk/tests/pmp-virt/unit/test_pmpvirt_suite.py)
- [test_directory_layout.py](/home/wsh/riscv-spike-sdk/tests/pmp-virt/unit/test_directory_layout.py)
- [test_build.py](/home/wsh/riscv-spike-sdk/tests/pmp-virt/unit/test_build.py)

建议在 `virt-test` 中给攻击实验独立编号，不要只并入现有 Stage2Virt 功能测试。

解析器必须验证：

- ON/OFF 两组结果都存在。
- 对照组攻击确实成功。
- 保护组攻击确实失败。
- fault 类型正确。
- GPA从开始到完成一致。
- 攻击前后内容不变。
- 输出只出现一次且顺序正确。
- 任何 `FAIL` 都使完整回归失败。
- 命令回显不能冒充结果。

## 五、版本锁

必须更新：

- [sources.json](/home/wsh/riscv-spike-sdk/conf/virt/sources.json)

至少可能产生三个新 revision：

```json
{
  "linux-host":  "Host KVM/selftest 新提交",
  "linux-guest": "Guest 攻击设备新提交",
  "kvmtool":     "攻击协调新提交",
  "qemu":        "底层攻击语义测试新提交"
}
```

`repo/linux-guest` 是 Linux 仓库的 worktree，所以必须提交并更新 `linux-guest.revision`；只保留工作区修改会在重新准备源码时丢失。

## 推荐的完整改动范围

| 模块 | 是否必改 | 主要职责 |
|---|---:|---|
| Linux guest worktree | 是 | VS 攻击 ioctl、异常恢复、内容核对 |
| SDK guest程序 | 是 | VU驱动攻击和输出证据 |
| kvmtool | 是 | GPA协调、ON/OFF、失败清理 |
| Host Linux selftest | 是 | 配置接口、恶意范围和状态切换验证 |
| Host KVM实现 | 按测试结果 | 修复接口或权限缺口 |
| QEMU语义测试 | 是 | 底层VS/VU和ON/OFF对照 |
| QEMU实现 | 按测试结果 | 修复发现的语义问题 |
| OpenSBI | 否 | Stage2Virt路径不经过OpenSBI |
| SDK统一套件 | 是 | 构建、部署、严格判定和证据归档 |

最核心的实现链是：

```text
VU攻击程序
→ /dev/stage2_virt_test
→ Guest VS攻击探针
→ kvmtool运行时协调
→ Host KVM配置G-stage Stage2Virt
→ QEMU执行最终权限判断
→ virt-test核对ON/OFF证据
```

这条链全部跑通，才算与 PMP.Virt syscall attack 同等级的完整 Stage2Virt 攻击实验。