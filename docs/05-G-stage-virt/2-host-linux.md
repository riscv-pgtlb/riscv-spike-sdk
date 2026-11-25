# Host Linux: G-stage Virt 实现


创建 Host Linux 分支:

```bash
git -C repo/linux switch -c G-stage-virt-host
```

QEMU 已经负责“**解释**”G-stage PTE 的 bit 8：

```
普通 G-stage PTE：
VS 和 VU 使用相同权限

带 STAGE2_VIRT 的 G-stage叶 PTE：
VS → 保留基础权限
VU → 在 G-stage层补足 RWX
```

Host Linux/KVM 接下来负责：

```
kvmtool指定某段 guest GPA
        ↓
Host KVM找到对应G-stage映射
        ↓
基础权限改成R，并设置STAGE2_VIRT
        ↓
刷新G-stage TLB
        ↓
VS只能读；VU在G-stage层获得RWX
```

不能把所有 Guest RAM 都加这个位，**只能处理 kvmtool 明确指定的 GPA 范围**。

## 1 修改 Host Linux/KVM

| 顺序 | 文件 | 作用 |
|---|---|---|
| 1 | [kvm_gstage.h](../../repo/linux/arch/riscv/include/asm/kvm_gstage.h) | 定义 Stage2Virt PTE 位和内部接口 |
| 2 | [kvm_host.h](../../repo/linux/arch/riscv/include/asm/kvm_host.h) | 保存每个 VM 的 GPA 范围状态 |
| 3 | [RISC-V kvm.h](../../repo/linux/arch/riscv/include/uapi/asm/kvm.h) | 定义 Stage2Virt 请求结构 |
| 4 | [通用 kvm.h](../../repo/linux/include/uapi/linux/kvm.h) | 定义 capability 和 ioctl |
| 5 | [vm.c](../../repo/linux/arch/riscv/kvm/vm.c) | 校验请求、更新状态并清除旧映射 |
| 6 | [gstage.c](../../repo/linux/arch/riscv/kvm/gstage.c) | 生成 Stage2Virt PTE |
| 7 | [mmu.c](../../repo/linux/arch/riscv/kvm/mmu.c) | 选择映射大小并处理部分重叠 |
| 8 | [vcpu_exit.c](../../repo/linux/arch/riscv/kvm/vcpu_exit.c) | 处理 VS 写/执行故障 |

### 1.1 定义 G-stage 专用 bit 和内部接口
QEMU 已经把 G-stage PTE 的 bit 8 定义成：
```c
#define PTE_STAGE2_VIRT 0x100
```
Host Linux 建立 G-stage PTE 时，也必须设置同一个 bit。否则 QEMU 看不到 Stage2Virt 标记。

修改：[kvm_gstage.h](../../repo/linux/arch/riscv/include/asm/kvm_gstage.h)

让 Host Linux/KVM 能够**识别、设置和清除** G-stage PTE 中的 Stage2Virt 标志位

```c
#define _PAGE_STAGE2_VIRT   _PAGE_SPECIAL
static inline bool gstage_pte_stage2_virt(pte_t pte) {
    return pte_val(pte) & _PAGE_STAGE2_VIRT;
}
static inline pte_t gstage_pte_mkstage2_virt(pte_t pte) {
    return __pte(pte_val(pte) | _PAGE_STAGE2_VIRT);
}
static inline pte_t gstage_pte_clear_stage2_virt(pte_t pte) {
    return __pte(pte_val(pte) & ~_PAGE_STAGE2_VIRT);
}
```

## 1.2 确定最终用户态接口

这一步的目的，是让未来的 **kvmtool** 能告诉 Host Linux： “请把这个虚拟机的某段GPA范围**启用**Stage2Virt”
```txt
kvmtool构造struct kvm_riscv_stage2_virt
        ↓
调用KVM_RISCV_SET_STAGE2_VIRT
        ↓
Host Linux复制并校验结构体
        ↓
保存GPA范围
        ↓
修改对应G-stage叶PTE
        ↓
刷新G-stage TLB
```

### 1.2.1 定义用户态请求格式
**作用**：规定 kvmtool 传给 Host Linux 的数据长什么样。

修改：[arch/riscv/include/uapi/asm/kvm.h](../../repo/linux/arch/riscv/include/uapi/asm/kvm.h) ：

```c
/*
 * Configure a guest physical address range for the local experimental
 * Stage2Virt G-stage attribute.
 */
#define KVM_RISCV_STAGE2_VIRT_ENABLE	(1ULL << 0)

struct kvm_riscv_stage2_virt {
	__u64 guest_phys_addr;		// GPA 起点
	__u64 memory_size;			// 范围长度、按页对齐
	__u64 flags;
	__u64 reserved[5];
};
```

### 1.2.2 定义 capability 和 ioctl
   
> 注意：ioctl 宏不能放进 RISC-V 的 asm/kvm.h，因为该文件被包含时，`KVMIO` 还没有定义。因此它们要放在通用的 [include/uapi/linux/kvm.h](../../repo/linux/include/uapi/linux/kvm.h)

在 capability 编号末尾、`243` 后面加入：
```c
#define KVM_CAP_RISCV_STAGE2_VIRT 244
```

**作用**：kvmtool 可以先调用：

```c
ioctl(kvm_fd, KVM_CHECK_EXTENSION, KVM_CAP_RISCV_STAGE2_VIRT)
```
**查询能力**，返回 1 才表示 Host Linux 支持该实验接口。

在 VM fd ioctl 定义附近、`KVM_CREATE_DEVICE` 前面加入：

```c
#define KVM_RISCV_SET_STAGE2_VIRT \
	_IOW(KVMIO, 0xb8, struct kvm_riscv_stage2_virt)
```
用户态向内核传入 `struct kvm_riscv_stage2_virt`。

> `ioctl`：发送实际命令
> 确认内核支持后，kvmtool 再通过 ioctl 发送配置：
> ```c
> struct kvm_riscv_stage2_virt request = {
> 	.guest_phys_addr = 0x90000000,
> 	.memory_size = 0x1000,
> 	.flags = KVM_RISCV_STAGE2_VIRT_ENABLE,
> };
> ret = ioctl(vm_fd, KVM_RISCV_SET_STAGE2_VIRT, &request);
> ```
> 相当于告诉内核：“请给这个虚拟机的GPA范围 [0x90000000, 0x90001000) 配置Stage2Virt。”

### 1.2.3 每个VM保存独立状态
每个 KVM 虚拟机拥有独立的 Stage2Virt 范围，不能使用全局变量，否则两个 Guest 会互相影响。

在 [kvm_host.h](../../repo/linux/arch/riscv/include/asm/kvm_host.h) 的 `struct kvm_arch` 前加入：

```c
struct kvm_riscv_stage2_virt_state {
	gpa_t start;
	gpa_t end;
	bool enabled;
};
```

然后在 `struct kvm_arch` 中，加入：

```c
	/*
	 * Local experimental Stage2Virt GPA range.
	 * Protected by kvm->mmu_lock.
	 */
	struct kvm_riscv_stage2_virt_state stage2_virt;
```

### 1.2.4 让指定 GPA 范围的旧 PTE 失效

> **为什么必须做**
> 假设 Guest 已经访问过 GPA 0x90000000，KVM 已经建立普通 G-stage PTE：
> ```txt
> GPA 0x90000000 → 普通 RWX G-stage PTE
> ```
> 然后 kvmtool 调用 ioctl 启用 Stage2Virt。即使内核保存了：
> ```c
> stage2_virt.enabled = true
> ```
> CPU 仍会继续使用原来的普通 PTE。新状态不会自动改变旧页表。
> **因此启用或关闭 Stage2Virt 时，必须清除相关旧 PTE**
> 
> **为什么不直接使用现有 `unmap` 函数**
> 现有：`kvm_riscv_gstage_unmap_range()` 只会在请求范围完整覆盖叶 PTE 时清除它。
> 如果目标是一个 4 KiB 页面，但旧映射是 2 MiB 大页，现有代码可能不会清除这个大页。Stage2Virt 就无法生效。

**所以为 Stage2Virt 增加一个专用 `zap` 函数**：只要叶PTE与目标范围相交，就清除整个叶PTE；多清除的页面之后可以通过缺页重新建立，功能上安全。

1. **增加函数声明**
	
修改：[kvm_gstage.h](../../repo/linux/arch/riscv/include/asm/kvm_gstage.h)

```c
void kvm_riscv_gstage_zap_range(struct kvm_gstage *gstage,
				gpa_t start, gpa_t size, bool may_block);
```
	
2.**增加实现**
	
修改：[gstage.c](../../repo/linux/arch/riscv/kvm/gstage.c)

```c
void kvm_riscv_gstage_zap_range(struct kvm_gstage *gstage,
				gpa_t start, gpa_t size, bool may_block)
{
	pte_t *ptep;
	u32 ptep_level;
	bool found_leaf;
	unsigned long page_size;
	gpa_t addr = start;
	gpa_t end = start + size;
	gpa_t leaf_addr;
	int ret;
	while (addr < end) {
		// 查找当前 GPA 对应的叶 PTE
		found_leaf = kvm_riscv_gstage_get_leaf(gstage, addr,
							&ptep, &ptep_level);
		// 计算叶 PTE 覆盖范围
		ret = gstage_level_to_page_size(ptep_level, &page_size);
		if (ret) break;
		leaf_addr = addr & ~(page_size - 1);		// 起点
		if (found_leaf)				// 清除 PTE
			kvm_riscv_gstage_op_pte(gstage, leaf_addr, ptep,
						ptep_level, GSTAGE_OP_CLEAR);
		addr = leaf_addr + page_size;
		if (!(gstage->flags & KVM_GSTAGE_FLAGS_LOCAL) &&
			may_block && addr < end)
			cond_resched_lock(&gstage->kvm->mmu_lock);
	}
}
```

### 1.2.5 ioctl 更新状态并清除旧映射

#### 增加内部辅助函数

在已经持有 mmu_lock 的情况下，删除指定GPA范围内现有的 G-stage 页表映射，让Guest下一次访问时重新触发缺页并建立新映射。

修改：[vm.c](../../repo/linux/arch/riscv/kvm/vm.c)

在当前 kvm_riscv_set_stage2_virt() 前面增加：
```c
static void kvm_riscv_stage2_virt_zap_locked(struct kvm *kvm,
					      gpa_t start, gpa_t end)
{
	struct kvm_gstage gstage = {
		.kvm = kvm,
		.flags = 0,
		.vmid = READ_ONCE(kvm->arch.vmid.vmid),
		.pgd = kvm->arch.pgd,
	};
	lockdep_assert_held(&kvm->mmu_lock);
	if (start >= end)
		return;
	kvm_riscv_gstage_zap_range(&gstage, start, end - start, true);
}
```

#### KVM虚拟机ioctl命令的内部处理函数

调用路径：
```txt
kvmtool
  ↓ ioctl(vm_fd, KVM_RISCV_SET_STAGE2_VIRT, &request)
Linux通用KVM ioctl入口
  ↓
kvm_arch_vm_ioctl()
  ↓
kvm_riscv_set_stage2_virt()
```

1. 从 kvmtool 接收请求
2. 校验请求
3. 计算新 Stage2Virt 范围
4. 保存旧范围
5. 更新当前VM状态
6. 删除**旧范围和新范围**中的G-stage映射

```c
static int kvm_riscv_set_stage2_virt(struct kvm *kvm, void __user *argp)
{
	struct kvm_riscv_stage2_virt request;
	gpa_t old_start, old_end;
	gpa_t start = 0, end = 0;
	bool old_enabled;
	bool enable;
	if (copy_from_user(&request, argp, sizeof(request)))
		return -EFAULT;
	if (memchr_inv(request.reserved, 0, sizeof(request.reserved)))
		return -EINVAL;
	if (request.flags & ~KVM_RISCV_STAGE2_VIRT_ENABLE)
		return -EINVAL;
	enable = request.flags & KVM_RISCV_STAGE2_VIRT_ENABLE;
	if (!enable) {			// 关闭请求
		if (request.guest_phys_addr || request.memory_size)
			return -EINVAL;
	} else {
		if (!request.memory_size)
			return -EINVAL;
		start = request.guest_phys_addr;
		if (!PAGE_ALIGNED(start) || !PAGE_ALIGNED(request.memory_size))
			return -EINVAL;
		if (start >= kvm_riscv_gstage_gpa_size)
			return -EINVAL;
		if (request.memory_size > kvm_riscv_gstage_gpa_size - start)
			return -EINVAL;
		end = start + request.memory_size;
	}
	// 原子地完成：读取旧状态 → 写入新状态 → 删除相关旧PTE
	spin_lock(&kvm->mmu_lock);
	old_start = kvm->arch.stage2_virt.start;
	old_end = kvm->arch.stage2_virt.end;
	old_enabled = kvm->arch.stage2_virt.enabled;
	kvm->arch.stage2_virt.start = start;
	kvm->arch.stage2_virt.end = end;
	kvm->arch.stage2_virt.enabled = enable;
	if (old_enabled)
		kvm_riscv_stage2_virt_zap_locked(kvm, old_start, old_end);
	if (enable && (!old_enabled || start != old_start || end != old_end))
		kvm_riscv_stage2_virt_zap_locked(kvm, start, end);
	spin_unlock(&kvm->mmu_lock);
	return 0;
}
```

### 1.2.6 生成 Stage2Virt 叶 PTE

#### 给建图函数增加参数
当前：
```c
kvm_riscv_gstage_map_page(...)
```
只知道：页面是否只读；页面是否可执行。**它不知道当前 GPA 是否属于 Stage2Virt 范围。**

因此增加：`bool stage2_virt`。由 `mmu.c` 判断范围，由 `gstage.c` 负责生成对应 PTE。

1. 在 [kvm_gstage.h](../../repo/linux/arch/riscv/include/asm/kvm_gstage.h) 中，修改声明
2. 在 [gstage.c](../../repo/linux/arch/riscv/kvm/gstage.c) 中，修改函数的实现
    1. 基础权限只能是 PAGE_READ
		> QEMU 的语义是：
		> VS → 使用PTE基础权限
		> VU → 如果存在STAGE2_VIRT，则补足RWX
	2. `gstage_pte_mkstage2_virt()` 加上 bit 8。

> 负责在 Host KVM 重新建立 G-stage 映射时，真正生成带 Stage2Virt 属性的叶 PTE。

#### 支持多种映射大小
**完整覆盖且正确对齐时可以直接使用Stage2Virt大页；只有部分重叠时必须拆分或退化成4 KiB映射。**

**mmu.c 增加三态范围判断**

判断“准备建立的一块 G-stage 映射”和“Stage2Virt GPA 范围”之间是什么关系。

```txt
NONE    完全不相交
FULL    整块映射都在Stage2Virt范围内
PARTIAL 只有一部分落在Stage2Virt范围内
```

修改 [mmu.c](../../repo/linux/arch/riscv/kvm/mmu.c) 

> 修改 mmu.c 中两个调用点

### 1.2.7 识别Stage2Virt预期故障

修改：[vcpu_exit.c](../../repo/linux/arch/riscv/kvm/vcpu_exit.c)

```
stage2_virt_fault()
→ 判断这次故障是不是Stage2Virt预期产生的

stage2_virt_redirect_fault()
→ 如果是，把G-stage故障转换成Guest Linux能处理的普通页故障
```

1. **增加故障识别函数** `stage2_virt_fault()`
2. **增加故障重定向函数** `stage2_virt_redirect_fault()`

> **Stage2Virt 与 dirty logging 都依赖 G-stage PTE 写权限，但语义存在冲突。**
> - Dirty logging 通过清除写权限并捕获首次写故障记录脏页；
> - Stage2Virt 则会为 VU 补足写权限，使写操作可能绕过脏页故障，导致 dirty bitmap 漏记。
> 
> 同时，二者产生的写故障处理方式不同，可能造成权限错误。于是添加限制：
> 通过双向冲突检查实现：启用 Stage2Virt 时检查重叠 memslot 是否开启 dirty logging；开启 dirty logging 时检查是否与 Stage2Virt 范围重叠，冲突则拒绝，并在缺页建图阶段增加兜底校验。

## 2 测试

### 2.1 Host Linux

新增 RISC-V KVM Stage2Virt 运行时自测试文件 [stage2_virt_test.c](../../repo/linux/tools/testing/selftests/kvm/riscv/stage2_virt_test.c)，主要验证：

- 内核是否报告 `KVM_CAP_RISCV_STAGE2_VIRT`；
- Stage2Virt ioctl 的启用、范围更新和关闭；
- 地址未对齐、长度非法、未知标志及保留字段非零等参数校验；
- Stage2Virt 与 dirty logging 重叠时的双向冲突限制。

修改 [Makefile.kvm](../../repo/linux/tools/testing/selftests/kvm/Makefile.kvm)，将该程序加入 RISC-V KVM selftest 构建。


### 2.2 SDK

新增 SDK 测试脚本 [check-stage2-virt-host.sh](../../tests/G-stage-virt/check-stage2-virt-host.sh)，用于在 Host Linux 中运行测试并输出 PASS、FAIL 或 SKIP。

修改 virt-kvm.py，实现：

- 自动导出 Host Linux 用户态头文件；
- 静态编译 stage2_virt_test；
- 将测试程序和检查脚本加入 Host Buildroot rootfs；
- 将测试程序纳入构建产物清单和完整性校验。

修改 tool-manifest.py，将测试程序安装到 Host Debian 的 /usr/bin/stage2_virt_test，并安装 /usr/local/bin/check-stage2-virt-host。

> Host Debian 同时安装 Stage2Virt selftest 二进制及其 SDK 检查入口：前者执行实际 KVM 接口测试，后者负责调用测试并统一处理结果。

修改双环境回归入口：

Buildroot test-virt-all.sh
Debian test-virt-debian-all.sh

两种环境均在启动内层 Guest 前执行 Host Stage2Virt 测试。

修改 run-suite.py，新增“Host Linux KVM Stage2Virt运行时测试”，统一测试由 18 项增加到 19 项。