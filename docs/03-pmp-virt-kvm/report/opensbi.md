# OpenSBI 子模块改动报告

仓库：`repo/opensbi`。锁定版本：`0e1a39f96b50c09978aa190a830b713a51c014c2`。

## 职责

OpenSBI 在 M 态管理固定布局的保护策略，接收 host 的封存请求，同时限制可调用的 SBI 服务。host 不通过接口提供任意地址或权限。

## 新增的实验专用文件

| 文件 | 用途 |
| --- | --- |
| [lib/sbi/sbi_ecall_pvseal.c](../../../repo/opensbi/lib/sbi/sbi_ecall_pvseal.c) | 实现自定义 SBI 扩展 `0x0a000056`、功能号 0；检查调用身份、参数和平台条件，应用/回读规则，保存 sealed 状态并支持规则重施。 |
| [include/sbi/pmp_virt_layout.h](../../../repo/opensbi/include/sbi/pmp_virt_layout.h) | 布局接入头：要求传入 `PMP_VIRT_LAYOUT_HEADER`，包含 SDK 生成的布局并检查必要宏。它自身不保存本次 host 的实际地址。 |

此处“新增”按实验专用文件判断，未用完整上游父提交差异确认；浅历史限制见总报告。

## 修改的既有文件

| 文件 | 改动及用途 |
| --- | --- |
| [include/sbi/riscv_encoding.h](../../../repo/opensbi/include/sbi/riscv_encoding.h) | 定义本地实验 PMP 位 `PMP_VIRT`，与 QEMU 编码一致。 |
| [lib/sbi/Kconfig](../../../repo/opensbi/lib/sbi/Kconfig) | 增加封存策略及实验传输测试配置入口。传输测试开关不应与完整封存策略混为一谈。 |
| [lib/sbi/objects.mk](../../../repo/opensbi/lib/sbi/objects.mk) | 在启用封存配置时编译并注册 `ecall_pvseal`。 |
| [lib/sbi/sbi_ecall.c](../../../repo/opensbi/lib/sbi/sbi_ecall.c) | 增加 SBI 扩展白名单，在启用相关固件配置时限制探测和调用，降低通过固件服务绕开 HS 直接访问限制的风险。 |
| [lib/sbi/sbi_hart.c](../../../repo/opensbi/lib/sbi/sbi_hart.c) | 普通 PMP 初始化后接入封存规则重施；包含可选实验传输检查相关逻辑。 |

## 封存处理过程

1. 只允许非虚拟化的 host S 态调用；功能号为 0，六个参数必须为零。
2. 检查单 hart、16 个 PMP 条目、粒度、Smepmp 状态、下一阶段入口和原有 PMP 区域等前提。
3. 使用固件编译时固定的 host 布局，不采用 host 传入的保护范围。
4. 保留前部固件条目，设置 text、rodata、RAM 与未知/MMIO 兜底规则。
5. 回读关键寄存器，刷新相关地址转换及指令缓存。规则核验失败时停留在 M 态。
6. 标记已封存，重复请求返回已封存；相关重新初始化路径再次施加策略。

| 区域 | 策略 |
| --- | --- |
| host text | RX |
| host rodata | R |
| 后续 RAM 匹配区域 | RW + Virt；普通 HS 不获得执行权限，符合委派条件的低上下文由 QEMU 补足 PMP 层 RWX |
| 未知/MMIO 兜底区域 | RW，不执行、不委派 |

PMP 按条目优先级匹配，RAM 规则不会覆盖更早匹配的 text/rodata 规则。“封存”指实验策略管理，不代表全部条目设置硬件 `PMP_L`。

## 生成文件与源码的区别

实际布局在 SDK 的 `build/virt-kvm/generated/pmp_virt_layout.h` 中生成，含 text/rodata 边界、RAM 参数和 host Image 摘要。它通过编译参数进入固件，不应误记为需要手工维护的子模块源码。摘要用于构建配对，不是运行时内存认证。
