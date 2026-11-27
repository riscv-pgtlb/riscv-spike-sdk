# Guest Linux: G-stage Virt 实现

新建一个分支 `stage2-virt`
## 1 实验目标

本阶段在 Guest Linux 中实现一个 **VU–VS–VU 同页权限探针**，用于真实验证 Stage2Virt 的核心语义：
```txt
同一个 Guest Physical Page
        │
        ├─ VU 第一次访问：成功
        ├─ VS 访问同页：产生预期的 G-stage 权限异常
        └─ VU 再次访问：仍然成功
```
预期结果为：VU-success → VS-access-fault → VU-success

> 测试页是**动态分配**的，GPA 启动后才知道，而目前 kvmtool 在启动 Guest 前配置 Stage2Virt GPA
> 
> 因此需要增加 Guest→kvmtool 的运行时握手，在 Guest 报告 GPA 后调用 Stage2Virt ioctl，同步修改kvmtool

## 2 修改

### 2.1 重构 kvmtool 的 Stage2Virt 接口
**目标是让 Stage2Virt 不仅能读取命令行里的固定 GPA，也能接收 Guest 运行时报告的 GPA。**

#### 修改头文件
打开：[stage2-virt.h](../../repo/kvmtool/riscv/include/kvm/stage2-virt.h)

保留原接口，同时增加：
```c
#include <linux/types.h>
struct kvm;
int stage2_virt__check_capability(struct kvm *kvm);
int stage2_virt__set_range(struct kvm *kvm, u64 gpa, u64 size);
int stage2_virt__clear_range(struct kvm *kvm, u64 gpa, u64 size);
int stage2_virt__configure(struct kvm *kvm);
```

#### 拆分当前实现
修改：[stage2-virt.c](../../repo/kvmtool/riscv/stage2-virt.c)

把 capability 查询抽成：
```c
int stage2_virt__check_capability(struct kvm *kvm)
{
	int ret;
	ret = ioctl(kvm->sys_fd, KVM_CHECK_EXTENSION, KVM_CAP_RISCV_STAGE2_VIRT);
	if (ret < 0)
		return -errno;
	if (!ret)
		return -EOPNOTSUPP; 
	return 0;
}
```
增加统一的范围校验：
```c
static int stage2_virt__validate_range(struct kvm *kvm, u64 gpa, u64 size)
```

#### 实现动态启用
```c
int stage2_virt__set_range(struct kvm *kvm, u64 gpa, u64 size)
{
	struct kvm_riscv_stage2_virt request = {
		.guest_phys_addr = gpa,
		.memory_size = size,
		.flags = KVM_RISCV_STAGE2_VIRT_ENABLE,
	};
	int ret;
	ret = stage2_virt__validate_range(kvm, gpa, size);
	if (ret)
		return ret;
	ret = stage2_virt__check_capability(kvm);
	if (ret)
		return ret;
	ret = ioctl(kvm->vm_fd, KVM_RISCV_SET_STAGE2_VIRT, &request);
	if (ret < 0)
		return -errno;
	pr_info("Stage2Virt enabled for GPA [0x%llx, 0x%llx)",
		(unsigned long long)gpa,
		(unsigned long long)(gpa + size));
	return 0;
}
```

#### 实现关闭
```c
int stage2_virt__clear_range(struct kvm *kvm, u64 gpa, u64 size)
{
	struct kvm_riscv_stage2_virt request = {
		.guest_phys_addr = gpa,
		.memory_size = size,
		.flags = 0,
	};
	int ret;
	ret = stage2_virt__validate_range(kvm, gpa, size);
	if (ret)
		return ret;
	ret = ioctl(kvm->vm_fd, KVM_RISCV_SET_STAGE2_VIRT, &request);
	if (ret < 0)
		return -errno;
	pr_info("Stage2Virt disabled for GPA [0x%llx, 0x%llx)",
		(unsigned long long)gpa,
		(unsigned long long)(gpa + size));
	return 0;
}
```
#### 保持原命令行行为
把原来的 `stage2_virt__configure()` 简化成：
```c
int stage2_virt__configure(struct kvm *kvm)
{
	if (!kvm->cfg.arch.stage2_virt)
		return 0;

	return stage2_virt__set_range(
		kvm,
		kvm->cfg.arch.stage2_virt_gpa,
		kvm->cfg.arch.stage2_virt_size);
}
```
这样现有静态启动参数仍然有效：
```bash
--stage2-virt \
--stage2-virt-gpa 0x90000000 \
--stage2-virt-size 0x1000
```
同时，后续 SBI 握手也能直接调用：
```c
stage2_virt__set_range(kvm, guest_gpa, PAGE_SIZE);
```

#### 补单元测试
修改：[stage2-virt-test.py](../../repo/kvmtool/tests/stage2-virt-test.py)，新增测试：

- capability 成功、失败和不支持
- 动态 set_range 和动态 clear_range
- GPA、size 对齐检查、零长度、溢出、RAM 范围检查
- enable/disable 请求的 flags 和保留字段
- ioctl 错误传播
- 静态 configure 兼容性

### 2.2 增加 Guest→kvmtool 的 SBI 握手

**目标流程：**
```txt
Guest SBI BEGIN(gpa, size)
→ kvmtool set_range()
→ Guest 执行测试
→ Guest SBI COMPLETE(gpa, size)
→ kvmtool clear_range()
```

在 [kvm-config-arch.h](../../repo/kvmtool/riscv/include/kvm/kvm-config-arch.h) 加入状态字段、注册命令行参数

```c
bool stage2_virt_test;
OPT_BOOLEAN('\0', "stage2-virt-test",				\
		    &(cfg)->stage2_virt_test,				\
		    "Enable experimental single-vCPU VU/VS page test"),	\
```

修改 [kvm.c](../../repo/kvmtool/riscv/kvm.c) 的 `kvm__arch_validate_cfg()`：**让两种模式保持独立**：
```txt
--stage2-virt
    静态模式，启动前必须指定 GPA 和 size
--stage2-virt-test
    动态测试模式，启动后由 Guest 通过 SBI 报告 GPA 和 size
```

修改 [kvm-cpu-arch.h](../../repo/kvmtool/riscv/include/kvm/kvm-cpu-arch.h)，记录运行时状态：
```c
bool stage2_virt_test_active;
u64 stage2_virt_test_gpa;
u64 stage2_virt_test_size;
```

新增头文件 [stage2-virt-test.h](../../repo/kvmtool/riscv/include/kvm/stage2-virt-test.h)

定义：
```c
#define STAGE2_VIRT_TEST_EXT      0x08000058UL
#define STAGE2_VIRT_TEST_BEGIN    0
#define STAGE2_VIRT_TEST_COMPLETE 1
#define STAGE2_VIRT_TEST_ABORT    2
```

新增 [stage2-virt-test.c](../../repo/kvmtool/riscv/stage2-virt-test.c)

实现 **SBI** 三个操作：
- **BEGIN**：校验 GPA/size，然后调用 stage2_virt__set_range()。
- **COMPLETE**：检查 GPA/size 与 BEGIN 一致，然后调用 stage2_virt__clear_range()。
- **ABORT**：清理当前范围和会话状态。


**修改 [kvm-cpu.c](../../repo/kvmtool/riscv/kvm-cpu.c)，把刚实现的处理器真正接入运行路径**

1. 引入头文件

	```c
	#include "kvm/stage2-virt-test.h"
	```

2. **分发 Stage2Virt SBI**：在处理 SBI extension ID 的 switch 中，放在 PMP.Virt 后面：
	
	```c
	case PMP_VIRT_TEST_EXT:
		return pmp_virt_test__sbi(vcpu);

	case STAGE2_VIRT_TEST_EXT:
		return stage2_virt_test__sbi(vcpu);
	```
	
	> 这样 Guest 调用 0x08000058 时，才会进入刚新增的 stage2_virt_test__sbi()。

3. **支持 SBI probe-extension**：Guest 会先通过标准 SBI BASE extension 查询扩展是否存在。
	
	扩展现有返回表达式：
	```c
	vcpu->kvm_run->riscv_sbi.ret[1] =
			(vcpu->kvm_run->riscv_sbi.args[0] == PMP_VIRT_TEST_EXT &&
			vcpu->kvm->cfg.arch.pmp_virt_test) ||
			(vcpu->kvm_run->riscv_sbi.args[0] == STAGE2_VIRT_TEST_EXT &&
			vcpu->kvm->cfg.arch.stage2_virt_test);
	```
	> 只有使用 `--stage2-virt-test` 启动时，Guest 才会看到该扩展可用。

4. **vCPU 销毁时清理**
	
	```c
	stage2_virt_test__cleanup(vcpu);
	```
	
	> 这样 Guest 未发送 COMPLETE、异常关机或 kvmtool 提前退出时，也会尝试关闭 Stage2Virt 范围。

完成后的调用链是：
```txt
Guest sbi_ecall(0x08000058, BEGIN, gpa, size)
→ KVM SBI exit
→ kvm-cpu.c
→ stage2_virt_test__sbi()
→ stage2_virt__set_range()
→ Host KVM ioctl
```

修改 [Makefile](../../repo/kvmtool/Makefile)：
```makefile
OBJS += riscv/stage2-virt-test.o
```
#### 测试

新增 [stage2-virt-runtime-test.py](../../repo/kvmtool/tests/stage2-virt-runtime-test.py)。

它直接编译并测试真实的 [stage2-virt-test.c](../../repo/kvmtool/riscv/stage2-virt-test.c)，mock set_range() 和 clear_range()，共覆盖 20 项：
- 扩展未启用
- 多 vCPU 拒绝
- 未知 function ID
- SBI 保留参数检查
- BEGIN 成功并保存 GPA/size
- 重复 BEGIN
- COMPLETE 的 GPA/size 不匹配
- COMPLETE 成功并清理状态
- Host capability 和 ioctl 错误映射
- ABORT 参数检查及幂等性
- ABORT 清理活动会话
- COMPLETE 清理失败后的本地状态重置
- vCPU 退出清理
- 无活动会话时退出清理不产生 ioctl

> 将测试接入总的回归测试

### 2.3 增加 Linux Guest 内核测试设备

**目标：由 Guest Linux 分配一张动态测试页，同时向 VU 用户态和 VS 内核提供同页访问入口，并通过 SBI 把该页 GPA 交给 kvmtool。**

完整设备调用链：
```txt
VU 打开 /dev/stage2_virt_test
        ↓
mmap 同一张 Guest 物理页
        ↓
ioctl BEGIN → SBI BEGIN(gpa, PAGE_SIZE)
        ↓
kvmtool 为该 GPA 启用 Stage2Virt
        ↓
VU 写成功 → ioctl VS_PROBE → VS 写产生预期 fault
        ↓
VU 再次写成功 → ioctl COMPLETE
        ↓
SBI COMPLETE → kvmtool 清除 Stage2Virt 范围
```

#### 增加 Kconfig

修改：[Kconfig.debug](../../repo/linux-guest/arch/riscv/Kconfig.debug)

新增：
```kconfig
config RISCV_STAGE2_VIRT_GUEST_TEST
	bool "Stage2Virt guest VU/VS same-page test"
	depends on 64BIT && MMU && RISCV_SBI && MISC_DEVICES
	default n
```

该配置默认关闭，只有实验 Guest 内核启用；普通 Linux Guest 不注册测试设备。

#### 增加编译入口

修改：[kernel/Makefile](../../repo/linux-guest/arch/riscv/kernel/Makefile)

加入：
```makefile
obj-$(CONFIG_RISCV_STAGE2_VIRT_GUEST_TEST) += stage2_virt_guest_test.o
```

#### 定义用户态接口

新增：[stage2_virt_test.h](../../repo/linux-guest/arch/riscv/include/uapi/asm/stage2_virt_test.h)

定义两个固定大小结构：
```c
struct stage2_virt_test_info {
	__u64 gpa;
	__u64 size;
};

struct stage2_virt_test_value {
	__u8 expected;
	__u8 reserved[7];
};
```

设备提供五个 ioctl：

- `GET_INFO`：返回测试页 GPA 和 `PAGE_SIZE`；
- `BEGIN`：向 kvmtool 发送 SBI BEGIN；
- `VS_PROBE`：由 VS 对 VU 已写入的同一页执行受控写探针；
- `COMPLETE`：核对 VU 第二次写入并发送 SBI COMPLETE；
- `ABORT`：测试失败或进程提前退出时清理活动会话。

#### 实现测试设备

新增：[stage2_virt_guest_test.c](../../repo/linux-guest/arch/riscv/kernel/stage2_virt_guest_test.c)

设备只在内核命令行包含以下参数时初始化：
```txt
stage2virt_guest_test=1
```

初始化时先通过 `sbi_probe_extension(0x08000058)` 确认 kvmtool 已启用动态测试扩展，然后分配一张零页并注册：
```txt
/dev/stage2_virt_test
```

设备限制为 `0600`，打开者必须具备 `CAP_SYS_ADMIN`，同一时间只允许一个测试进程，避免两个会话操作同一测试页。

#### 建立 VU 同页映射

`mmap()` 只接受一页、共享、可写且不可执行的映射，并使用：
```c
vm_insert_page(vma, vma->vm_start, test_page);
```

因此 VU 映射与 VS 的 `page_address(test_page)` 最终对应同一个 GPA，不使用设备 MMIO PFN，也不依赖固定物理地址。

#### 实现 VS 预期异常探针

VS 首先读取并核对 VU 写入的值，再通过：
```c
copy_to_kernel_nofault(address, &replacement, sizeof(replacement));
```

尝试修改同一页。Stage2Virt 生效时，VS 写入必须产生异常，并由现有 exception table 转换成 `-EFAULT`；不修改通用 `traps.c`，也不吞掉其他内核异常。

探针同时检查页面内容没有发生变化：
```txt
VU 写入 expected
→ VS 写入返回 -EFAULT
→ 页面仍等于 expected
```

如果 VS 写入成功，设备返回 `-EACCES`，表示 Stage2Virt 权限隔离没有生效。

#### 会话状态与清理

设备保存：
```c
session_active
vs_probe_passed
```

约束如下：

1. 重复 BEGIN 返回 `-EBUSY`；
2. 没有 BEGIN 时不能执行 VS_PROBE 或 COMPLETE；
3. VS_PROBE 只能成功一次；
4. COMPLETE 前必须已经取得预期 VS fault；
5. COMPLETE 必须看到 VU 第二次写入的最终值；
6. 文件关闭时如果会话仍活动，自动发送 SBI ABORT；
7. COMPLETE 或 ABORT 后清除本地会话状态，不能复用旧 GPA 会话。

预期内核日志：
```txt
Stage2Virt Guest device ready: /dev/stage2_virt_test GPA=... size=4096
Stage2Virt Guest BEGIN: GPA=... size=4096
Stage2Virt Guest VS PROBE PASS: GPA=... expected=... fault=-EFAULT
Stage2Virt Guest VU-VS-VU SAME-PAGE PASS: GPA=... final=...
```

### 2.4 增加 Guest VU 用户态程序

**目标：由真正的 VU 用户进程驱动 `/dev/stage2_virt_test`，完成两次 VU 写入和中间一次 VS 预期异常探针。**

新增：[stage2-virt-guest-test.c](../../tests/G-stage-virt/stage2-virt-guest-test.c)

程序执行顺序：
```txt
打开 /dev/stage2_virt_test
        ↓
GET_INFO：读取动态 GPA 和页面大小
        ↓
mmap(MAP_SHARED)：建立 VU 可写映射
        ↓
BEGIN：请求 kvmtool 为同一 GPA 启用 Stage2Virt
        ↓
VU 写入 0x5a，并立即读回验证
        ↓
VS_PROBE(expected=0x5a)：要求 VS 写产生 -EFAULT
        ↓
VU 确认页面仍为 0x5a
        ↓
VU 再写入 0xa5，并立即读回验证
        ↓
COMPLETE(expected=0xa5)：核对最终值并清除 Stage2Virt
```

#### 获取并校验测试页

程序先通过：
```c
ioctl(fd, STAGE2_VIRT_TEST_IOC_GET_INFO, &info);
```

获取内核动态分配的 GPA 和大小，并要求：

- `size` 等于当前系统页大小；
- GPA 按页对齐；
- mmap 长度严格等于一页。

用户态不假定固定 GPA，保证后续 BEGIN、VS_PROBE 和 COMPLETE 都针对内核实际分配的同一页。

#### 建立 VU 映射

```c
page = mmap(NULL, info.size, PROT_READ | PROT_WRITE,
	    MAP_SHARED, fd, 0);
```

这里必须使用 `MAP_SHARED`，使 VU 写入直接作用于驱动保存的测试页，而不是建立匿名副本。

#### 执行第一次 VU 写入

BEGIN 成功后，程序写入固定值 `0x5a`：
```c
__atomic_store_n(page, 0x5a, __ATOMIC_SEQ_CST);
```

随后立即读回，确认 VU 在 Stage2Virt G-stage 映射下获得写权限。成功日志：
```txt
Stage2Virt Guest VU BEFORE PASS: GPA=... value=0x5a
```

#### 请求 VS 同页探针

程序把第一次 VU 写入值作为 `expected` 传给：
```c
ioctl(fd, STAGE2_VIRT_TEST_IOC_VS_PROBE, &value);
```

驱动必须确认页面等于 `0x5a`，并确认 VS 写产生预期 `-EFAULT`。ioctl 返回后，VU 再次读取页面，确保 VS 没有改变内容。

成功日志：
```txt
Stage2Virt Guest VS PROBE PASS: GPA=... expected-access-fault
```

#### 执行第二次 VU 写入并完成会话

程序把同一页更新为 `0xa5` 并读回，然后通过 COMPLETE 把最终值交给驱动核对：
```c
value.expected = 0xa5;
ioctl(fd, STAGE2_VIRT_TEST_IOC_COMPLETE, &value);
```

COMPLETE 成功说明第二次 VU 写入仍然有效，同时 kvmtool 已收到清理请求。最终日志：
```txt
Stage2Virt Guest VU AFTER PASS: GPA=... value=0xa5
Stage2Virt Guest VU-VS-VU SAME-PAGE PASS: GPA=...
```

#### 失败与 ABORT 清理

程序从 BEGIN 成功后记录本地 `session_active`。任何中间步骤失败都会在退出前调用：
```c
ioctl(fd, STAGE2_VIRT_TEST_IOC_ABORT);
```

随后执行 `munmap()` 和 `close()`；即使用户程序来不及发送 ABORT，设备 `release()` 仍会执行第二层兜底清理。

完整成功证据为：
```txt
同一 GPA
VU BEFORE PASS: value=0x5a
→ VS PROBE PASS: expected-access-fault
→ VU AFTER PASS: value=0xa5
→ VU-VS-VU SAME-PAGE PASS
```

### 2.5 串联 VU → VS → VU

**目标：把用户程序产生的四阶段证据收敛成一个不可由缺阶段、错顺序或错误 GPA 通过的运行结果。**

新增：[check-stage2-virt-guest.sh](../../tests/G-stage-virt/check-stage2-virt-guest.sh)

检查器先确认以下两个输入真实存在：
```txt
/dev/stage2_virt_test
/usr/bin/stage2-virt-guest-test
```

随后运行用户程序并保存完整输出，只接受以下严格顺序：
```txt
Stage2Virt Guest VU BEFORE PASS: GPA=<same> value=0x5a
Stage2Virt Guest VS PROBE PASS: GPA=<same> expected-access-fault
Stage2Virt Guest VU AFTER PASS: GPA=<same> value=0xa5
Stage2Virt Guest VU-VS-VU SAME-PAGE PASS: GPA=<same>
```

四条证据必须各出现一次、顺序固定且 GPA 完全相同；缺失、重复、重排、错误值、错误 GPA 或用户程序非零退出都失败。

检查通过后输出统一标记：
```txt
Linux Guest Stage2Virt VU-VS-VU runtime test PASS
```

修改：[check-virt-guest.sh](../../tests/pmp-virt/runtime/check-virt-guest.sh)

在普通 Guest 内存和时钟推进检查之后调用：
```sh
/usr/local/bin/check-stage2-virt-guest
```

只有 Stage2Virt 同页测试也通过，才继续输出原有 `VIRT-REGRESSION GUEST PASS`。因此 Buildroot 与 Debian 共用同一真实探针和判定入口。

新增：[test_stage2_virt_guest.py](../../tests/pmp-virt/unit/test_stage2_virt_guest.py)

单元测试覆盖：

- 完整、同 GPA、顺序正确的证据通过；
- 缺阶段失败；
- 阶段重排失败；
- GPA 不一致失败；
- 重复证据失败；
- 用户程序自身失败时不能仅凭已打印的 PASS 行通过。

### 2.6  接入 SDK 构建和统一回归

**目标：让两种 Guest 环境都自动构建、安装、启用并验证 Stage2Virt VU–VS–VU 探针。**

#### Guest 内核配置与用户程序构建

修改：[virt-kvm.py](../../scripts/build/virt-kvm.py)

为 `linux-guest` 启用并验证：
```txt
CONFIG_RISCV_STAGE2_VIRT_GUEST_TEST=y
```

Host Linux 显式关闭该配置，避免把 Guest 实验设备带入外层内核。

新增 `build_guest_runtime_test()`：先从 Guest 内核输出树执行 `headers_install`，再使用同一 RISC-V 交叉工具链静态编译：
```txt
tests/G-stage-virt/stage2-virt-guest-test.c
→ build/virt-kvm/out/stage2-virt-guest-test
```

构建阶段检查 ELF 架构为 RISC-V，并拒绝带 `PT_INTERP` 的动态程序；产物和两份源码同时加入 manifest 校验。

#### Buildroot Guest 打包与启动

`package_rootfs()` 把以下文件装入内层 Buildroot：
```txt
/usr/bin/stage2-virt-guest-test
/usr/local/bin/check-stage2-virt-guest
```

修改：[run-virt-guest.sh](../../scripts/buildroot/run-virt-guest.sh)

只有 `--regression` 模式增加：
```txt
lkvm --stage2-virt-test
kernel stage2virt_guest_test=1
```

普通交互启动不启用实验 SBI 扩展和 Guest 测试设备。

#### Debian Guest 工具与启动

修改：[tool-manifest.py](../../scripts/debian/install/tool-manifest.py)

Guest 工具包新增：
```txt
/usr/bin/stage2-virt-guest-test
/usr/local/bin/check-stage2-virt-guest
```

修改：[test-virt-debian-all.sh](../../tests/pmp-virt/regression/debian/test-virt-debian-all.sh)

内层 Debian 回归启动同时传入：
```txt
--stage2-virt-test
stage2virt_guest_test=1
```

Debian 的 `virt-guest-test.service` 继续调用共用 `check-virt-guest`，因此无需再维护第二套探针顺序。

#### 统一结果解析

修改：[run-suite.py](../../tests/run-suite.py)

新增独立运行项：
```txt
Linux Guest Stage2Virt VU–VS–VU 同页测试
```

统一解析器不只接受最终 PASS，还要求四阶段证据位于 Guest 生命周期窗口内、各出现一次、顺序固定且 GPA 相同。任何 `Stage2Virt Guest ... FAIL` 同时使该项和完整回归失败。

修改以下 SDK 单元测试：

- [test_build.py](../../tests/pmp-virt/unit/test_build.py)：检查 Guest 配置、构建产物、打包路径及回归启动参数；
- [test_directory_layout.py](../../tests/pmp-virt/unit/test_directory_layout.py)：检查 Debian Guest 工具包安装布局；
- [test_pmpvirt_suite.py](../../tests/pmp-virt/unit/test_pmpvirt_suite.py)：检查同 GPA 四阶段证据、失败反例和统一测试编号。

接入后的真实链路：
```txt
SDK 构建 Guest 内核和静态用户程序
→ 打包 Buildroot / Debian Guest 工具
→ lkvm --stage2-virt-test
→ Guest stage2virt_guest_test=1
→ check-virt-guest
→ check-stage2-virt-guest
→ VU BEFORE → VS fault → VU AFTER → COMPLETE
→ run-suite 独立报告结果
```
