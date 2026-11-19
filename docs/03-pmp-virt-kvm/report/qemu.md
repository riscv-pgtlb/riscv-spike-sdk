# QEMU 子模块改动报告

仓库：`repo/qemu`。锁定版本：`0ec20439ca845573db2a52e85aa34c0dca9c1731`。

## 职责

QEMU 模拟实验性 PMP.Virt 权限语义。普通 HS 访问保持 PMP 权限约束；命中带实验位的区域时，符合条件的有效低权限执行上下文获得 PMP 层 RWX。页表等其他权限检查仍然存在。

## 修改文件

| 文件 | 类别 | 改动及用途 |
| --- | --- | --- |
| [target/riscv/pmp.h](../../../repo/qemu/target/riscv/pmp.h) | 修改既有文件 | **定义实验位** `PMP_VIRT = 1 << 6`，供权限判断使用；是本地实验编码。 |
| [target/riscv/pmp.c](../../../repo/qemu/target/riscv/pmp.c) | 修改既有文件 | 在普通 PMP 判定中加入委派条件：开关开启、非 M、有效 U 或虚拟化上下文、条目带 `PMP_VIRT` 时补足 RWX；将同一结果返回给后续 TLB 权限处理。 |
| [target/riscv/cpu_cfg.h](../../../repo/qemu/target/riscv/cpu_cfg.h) | 修改既有文件 | 增加 `x_pmp_virt` 配置字段。 |
| [target/riscv/cpu.c](../../../repo/qemu/target/riscv/cpu.c) | 修改既有文件 | **注册默认关闭的 `x-pmp-virt` 属性**，拒绝非 TCG、PMP 关闭或 Smepmp 开启的组合。 |

当前识别到的核心 QEMU 实验实现集中在以上四个既有文件，未识别出独立新增的 PMP.Virt 源文件。分类依据和浅历史限制见 [总报告](README.md)。

## 如何触发

SDK 启动 QEMU 时使用：

```text
-machine virt -accel tcg
-cpu rv64,h=true,smepmp=off,x-pmp-virt=on
-m 2048M -smp 1
```

执行访存或取指时进入 QEMU PMP 检查。普通 HS 不满足低上下文委派条件；M 态保留原语义。最终权限必须同时符合其他适用的地址转换与访问检查。

## 与其他模块的关系

OpenSBI 写入含 `PMP_VIRT` 的 PMP 条目，QEMU 解释这些条目。Linux 探针通过同一物理页在不同上下文中的执行结果验证区别；QEMU 本身不负责生成 Linux 保护布局或安装 Debian 工具。

本报告未重新运行 QEMU 或芯片级测试，源码条件也不等于已覆盖所有身份、TLB 和虚拟化组合。
