# Kvmtool: G-stage Virt 实现

新建一个分支 `stage2-virt`
## 1 实验目标
本阶段让 kvmtool 能够告诉 Host Linux/KVM：
为当前虚拟机的一段 Guest Physical Address（GPA）范围启用 Stage2Virt。

完整调用链如下：
```txt
用户启动 lkvm
  --stage2-virt
  --stage2-virt-gpa 0x90000000
  --stage2-virt-size 0x1000
              │
              ▼
kvmtool 检查 KVM_CAP_RISCV_STAGE2_VIRT
              │
              ▼
构造 struct kvm_riscv_stage2_virt
              │
              ▼
ioctl(vm_fd, KVM_RISCV_SET_STAGE2_VIRT, &request)
              │
              ▼
Host Linux/KVM 保存 GPA 范围并清除旧 G-stage 映射
              │
              ▼
Guest 第一次访问该 GPA 时重新建立 G-stage PTE
              │
              ▼
PTE 设置 STAGE2_VIRT 位
```
本实验采用三个显式参数：
```bash
--stage2-virt
--stage2-virt-gpa <address>
--stage2-virt-size <bytes>
```
Stage2Virt 默认关闭，避免影响普通 kvmtool 使用。

## 2 修改 kvmtool

### 2.1 同步 KVM UAPI
> kvmtool 自带了一份 Linux KVM 用户态头文件，不会自动使用 repo/linux 中的新接口

1. **RISC-V 请求结构**

修改：[repo/kvmtool/riscv/include/asm/kvm.h](../../repo/kvmtool/riscv/include/asm/kvm.h)

加入：
```c
#define KVM_RISCV_STAGE2_VIRT_ENABLE	(1ULL << 0)

struct kvm_riscv_stage2_virt {
	__u64 guest_phys_addr;
	__u64 memory_size;
	__u64 flags;            // 是否启用 Stage2Virt
	__u64 reserved[5];
};
```

2. **capability 和 ioctl**

修改：[repo/kvmtool/include/linux/kvm.h](../../repo/kvmtool/include/linux/kvm.h)

加入 capability：
```c
#define KVM_CAP_RISCV_STAGE2_VIRT 247
```
加入 ioctl：
```c
#define KVM_RISCV_SET_STAGE2_VIRT \
	_IOW(KVMIO, 0xb8, struct kvm_riscv_stage2_virt)
```

### 2.2 给 lkvm run 增加 Stage2Virt 命令行参数
目的：让用户启动 Guest 时能明确指定是否启用 Stage2Virt，以及作用于哪段 GPA：
```bash
lkvm run \
  --stage2-virt \
  --stage2-virt-gpa 0x90000000 \
  --stage2-virt-size 0x1000 \
  ...
```

修改 [repo/kvmtool/riscv/include/kvm/kvm-config-arch.h](../../repo/kvmtool/riscv/include/kvm/kvm-config-arch.h)

在 `struct kvm_config_arch` 中增加：
```c
bool stage2_virt;
u64 stage2_virt_gpa;
u64 stage2_virt_size;
```

分别保存：
- stage2_virt：是否启用；
- stage2_virt_gpa：GPA 起点；
- stage2_virt_size：范围长度。

然后在 `OPT_ARCH_RUN` 中注册三个参数：
```c
OPT_BOOLEAN('\0', "stage2-virt", &(cfg)->stage2_virt,		\
        "Enable experimental Stage2Virt"),			\
OPT_U64('\0', "stage2-virt-gpa",				\
    &(cfg)->stage2_virt_gpa,					\
    "Stage2Virt guest physical start address"),		\
OPT_U64('\0', "stage2-virt-size",				\
    &(cfg)->stage2_virt_size,				\
    "Stage2Virt guest physical range size"),		\
```

### 2.3 参数基础校验
**目的**：在打开 /dev/kvm、分配 Guest 内存之前，尽早拒绝错误参数

修改文件：[kvm.c (line 20)](../../repo/kvmtool/riscv/kvm.c)

修改函数：
```c
void kvm__arch_validate_cfg(struct kvm *kvm)
```
**检查**：
1. `--stage2-virt-gpa` 和 `--stage2-virt-size` 不能脱离 `--stage2-virt` 使用。
2. 启用 Stage2Virt 时，size 不能为零。
3. GPA 必须按 4 KiB 对齐。
4. size 必须按 4 KiB 对齐。
5. GPA + size 不能产生 u64 溢出。

### 2.4 实现 Stage2Virt 配置模块

这一步负责真正连接 kvmtool 和 Host KVM：
```txt
读取命令行中的 GPA 和 size
        ↓
确认整个范围位于 Guest RAM
        ↓
查询 KVM_CAP_RISCV_STAGE2_VIRT
        ↓
构造 struct kvm_riscv_stage2_virt
        ↓
调用 KVM_RISCV_SET_STAGE2_VIRT
```

1. **新增接口头文件**

新增 [stage2-virt.h (line 1)](../../repo/kvmtool/riscv/include/kvm/stage2-virt.h)：
```c
struct kvm;
int stage2_virt__configure(struct kvm *kvm);
```
使用前置声明避免引入不必要的头文件依赖。

2. **新增配置实现**

新增 [stage2-virt.c (line 1)](../../repo/kvmtool/riscv/stage2-virt.c)

> **内部辅助函数**：检查 Stage2Virt 请求的整个 GPA 范围是否完整落在某个 RAM bank 内，不能落入设备区域，也不能跨越两个 bank。
>
> ```c
> static bool stage2_virt__range_is_ram(struct kvm *kvm,
> 			u64 start, u64 size)
> ```

```c
int stage2_virt__configure(struct kvm *kvm)
```

作用：把命令行保存的 Stage2Virt 配置发送给 Host KVM。

```txt
stage2_virt__configure()
  ├─ 确认整个 GPA 范围位于 RAM
  ├─ 查询 KVM_CAP_RISCV_STAGE2_VIRT
  └─ 调用 KVM_RISCV_SET_STAGE2_VIRT
```

3. **修改构建系统**

修改 [Makefile (line 208)](../../repo/kvmtool/Makefile:208)，加入：

```makefile
OBJS		+= riscv/stage2-virt.o
```

新增模块会参与 RISC-V kvmtool 构建。

### 2.5 接入虚拟机初始化流程

修改文件：[repo/kvmtool/riscv/kvm.c](../../repo/kvmtool/riscv/kvm.c)

1. 加入头文件：

```c
#include "kvm/stage2-virt.h"
#include <string.h>
```

2. 在 `kvm__init_ram()` 中，Guest RAM 注册成功并设置起始地址后调用：

```c
kvm->arch.memory_guest_start = phys_start;

err = stage2_virt__configure(kvm);
if (err)
	die("Failed to configure Stage2Virt: %s", strerror(-err));
```

调用顺序变成：
```txt
kvm__register_ram()
        ↓
Guest RAM 加入 kvm->mem_banks
        ↓
设置 memory_guest_start
        ↓
stage2_virt__configure()
        ├─ 检查 GPA 是否属于 RAM
        ├─ 查询 capability
        └─ 调用配置 ioctl
        ↓
继续加载 Guest 内核
```

## 3 测试

### 3.1 Kvmtool
mock 单元测试的作用是：

不启动 QEMU、不运行 RISC-V Host、不访问真实 /dev/kvm，先验证 kvmtool 的 Stage2Virt 配置逻辑是否正确。

新增文件：[stage2-virt-test.py](../../repo/kvmtool/tests/stage2-virt-test.py)

加入 make virt-test-static
### 3.2 SDK

**新增真实 kvmtool ioctl 冒烟脚本**：tests/G-stage-virt/check-stage2-virt-kvmtool.sh
作用是在真实 RISC-V Host 中验证：
```txt
lkvm
  → 注册 Guest RAM
  → KVM_CHECK_EXTENSION
  → KVM_RISCV_SET_STAGE2_VIRT
```

**新增项目集成单元测试**：tests/pmp-virt/unit/test_stage2_virt_integration.py
作用：
- 检查主 Buildroot QEMU 启动入口包含 x-stage2-virt=on；
- 检查双 Debian 启动入口包含 x-stage2-virt=on；
- 检查 Debian 准备/更新维护入口包含 x-stage2-virt=on；
- 检查两个运行回归都调用 kvmtool 冒烟脚本；
  -检查 Buildroot 和 Debian 打包清单都包含该脚本；
  -防止以后新增或重构入口时漏掉 Stage2Virt。

**接入回归测试**：PMP.Virt kvmtool mock 和 Stage2Virt kvmtool mock 分别作为第 2、3 项，
真实 kvmtool ioctl 冒烟测试作为第 8 项。统一测试共 22 项，三个检查都有独立结果和日志。
