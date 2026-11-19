# Linux 子模块改动报告

仓库：`repo/linux`。受保护 host 与普通 guest 使用不同提交、独立源码工作区及输出。

- host：`ab598939034057e7fdc2a4beb483a10ef4c67077`
- guest：`449d48b1b99fdaa076166e200132705ac2bee711`

以下新增/修改类别来自这两个提交的直接比较，比较范围不是“当前工作区相对 HEAD”。

## 新增文件

| 文件 | 用途 |
| --- | --- |
| [arch/riscv/kernel/pv_access.c](../../../repo/linux/arch/riscv/kernel/pv_access.c) | HS 访问探针、预期异常识别与恢复控制、封存前后结果统计，以及 `/dev/pvtest` 用户探针 ioctl。 |
| [arch/riscv/kernel/pv_access_asm.S](../../../repo/linux/arch/riscv/kernel/pv_access_asm.S) | 提供受控调用、写入探针和恢复位置，配合 C 代码识别故障指令并继续测试。 |

## 修改文件

| 文件 | 改动及用途 |
| --- | --- |
| [arch/riscv/kernel/Makefile](../../../repo/linux/arch/riscv/kernel/Makefile) | 将 C 和汇编探针编入 host 内核。 |
| [arch/riscv/kernel/traps.c](../../../repo/linux/arch/riscv/kernel/traps.c) | 在内核异常错误处理前调用 `pv_access_fixup()`，允许严格匹配的预期探针异常恢复；普通异常仍走原有处理。 |
| [arch/riscv/mm/init.c](../../../repo/linux/arch/riscv/mm/init.c) | 在 `mark_rodata_ro()` 中执行封存前 SBI guard 和 HS 探针，发起 SBI 封存请求并检查响应，再执行封存后探针与 SBI guard。 |

## 启动时运行的检查

```text
mark_rodata_ro()
  → SBI guard before seal：9 项
  → pv_access_before()：3 项 HS 探针
  → SBI seal：扩展 0x0a000056，功能号 0
  → 确认返回值
  → pv_access_after()：3 项 HS 探针
  → SBI guard after seal：9 项
```

HS 探针对照 RAM 执行、text 可写别名写入、rodata 可写别名写入的封存前后结果，合计 6 项。SBI guard 检查扩展探测、直接调用返回值，以及测试缓冲区未改变，合计前后 18 项。

## 用户空间触发的检查

SDK 的 `pv-user-test` 在 U 态执行测试代码，通过 `/dev/pvtest` 请求 HS 对同一物理页执行受控探针，再返回 U 态重试。接口检查管理员能力、单 CPU 等条件，并限制测试内容。它是实验测试接口，不是面向任意程序的执行服务。

`check-virt-host` 每次核对本次启动日志，再调用该用户探针。guest 启动前和返回后各执行一次；不会在 guest 返回后重新运行 `mark_rodata_ro()`。

## guest 与 KVM 的范围

普通 guest 使用锁定的普通 Linux 版本，不加入上述 host 封存逻辑。KVM 用于运行内层系统；两版本直接差异未显示 `arch/riscv/kvm/` 的定制修改，因此不能把此次实验描述为重写 KVM 核心。host/guest 的内核配置选择由 SDK 构建脚本负责。
