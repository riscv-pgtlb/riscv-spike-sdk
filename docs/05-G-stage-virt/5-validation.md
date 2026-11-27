# Stage2Virt Linux Guest 最终验证报告

## 1. 验证目标

本报告记录 Stage2Virt Linux Guest 实验的最终回归结果。验证范围覆盖：

- Host Linux KVM Stage2Virt ioctl；
- kvmtool 静态配置与 Guest 运行时 SBI 握手；
- Linux Guest 内核测试设备 `/dev/stage2_virt_test`；
- Guest VU 用户程序；
- `VU → VS → VU` 同一 GPA 权限切换；
- 原有 PMP.Virt `HU → HS → HU` 与 `VS → HS → VS` 回归；
- Buildroot 和双 Debian 两种完整运行环境。

最终验收要求不是只出现一条 PASS，而是 BEGIN、VS 探测、VU 恢复访问、COMPLETE、Guest 退出和 Host 返回后复测全部成功。

## 2. 验证版本

验证日期：2026-11-27。

关键组件版本：

```txt
kvmtool
100131a46d9b852f29370ff18d07204c47d1a3a0
riscv: zero Stage2Virt range when disabling

linux-guest
eb0b925e4e4e4faf625089dc9ce445d9f9ba2685
riscv: fix Stage2Virt guest test Kconfig dependency
```

SDK 使用 `conf/virt/sources.json` 锁定上述组件版本。构建产物通过 manifest 哈希、Host 内核与 OpenSBI 布局配对检查。

## 3. 静态测试结果

执行：

```bash
make virt-test-static
```

结果：5/5 组通过。

| 测试组 | 数量 | 结果 | 验证内容 |
| --- | ---: | --- | --- |
| SDK Python 单元测试 | 117 | PASS | 构建、打包、版本锁、日志解析、回归判定及失败反例 |
| QEMU Stage2Virt 语义测试 | 2 | PASS | `x-stage2-virt=on/off` 权限差异 |
| PMP.Virt kvmtool mock | 19 | PASS | BEGIN、COMPLETE、ABORT、GPA 与会话清理 |
| Stage2Virt 配置接口 mock | 22 | PASS | capability、范围校验、enable/disable 与错误传播 |
| Stage2Virt 运行时 SBI mock | 20 | PASS | Guest 握手、状态机、错误码及 vCPU 退出清理 |

其中关闭 Stage2Virt 范围的请求验证为：

```txt
guest_phys_addr = 0
memory_size     = 0
flags           = 0
```

这与 Host KVM ioctl ABI 一致。

## 4. Buildroot 完整回归

执行：

```bash
make virt-test VIRT_SYSTEM=buildroot VIRT_TIMEOUT=600
```

结果：

```txt
结果：PASS（24/24）
耗时：30.46 秒
证据目录：build/virt-kvm/logs/suite-20261127-163138-796894
```

Buildroot 回归使用服务器本次构建的 Host 内核、Guest 内核、OpenSBI、QEMU、kvmtool 和 rootfs，完成两层虚拟化真实运行，不是 mock 测试。

## 5. 双 Debian 完整回归

更新两块 Debian 磁盘中的工具后执行：

```bash
make virt-test VIRT_SYSTEM=debian VIRT_TIMEOUT=600
```

结果：

```txt
结果：PASS（24/24）
耗时：139.65 秒
证据目录：build/virt-kvm/logs/suite-20261127-163909-886689
```

双 Debian 回归首先校验服务器期望版本与磁盘已安装版本一致，然后启动外层 Debian、内层 Debian并完成同一套保护测试。外层和内层均正常关机，QEMU 以成功状态退出。

## 6. 24 项统一回归结果

| 编号 | 测试内容 | Buildroot | 双 Debian |
| ---: | --- | --- | --- |
| 01 | SDK 单元测试 | PASS | PASS |
| 02 | PMP.Virt kvmtool mock | PASS | PASS |
| 03 | Stage2Virt 配置接口 mock | PASS | PASS |
| 04 | Stage2Virt 运行时握手 mock | PASS | PASS |
| 05 | QEMU Stage2Virt 语义测试 | PASS | PASS |
| 06 | 构建产物完整性与内核—固件配对 | PASS | PASS |
| 07 | 运行环境与磁盘可用性 | PASS | PASS |
| 08 | Host Linux KVM Stage2Virt 运行时测试 | PASS | PASS |
| 09 | kvmtool Stage2Virt 真实 ioctl 测试 | PASS | PASS |
| 10 | PMP.Virt 策略封存与内核确认 | PASS | PASS |
| 11 | HS RAM 封存前允许、封存后拒绝 | PASS | PASS |
| 12 | 内核 text 写保护 | PASS | PASS |
| 13 | 内核 rodata 写保护 | PASS | PASS |
| 14 | 封存前 SBI 接口限制检查 9/9 | PASS | PASS |
| 15 | 封存后 SBI 接口限制检查 9/9 | PASS | PASS |
| 16 | Guest 启动前 Host、HU–HS–HU 及 syscall 检查 | PASS | PASS |
| 17 | VS–HS–VS 同物理页权限对照 | PASS | PASS |
| 18 | Linux Guest Stage2Virt VU–VS–VU 同页测试 | PASS | PASS |
| 19 | Guest 内核、内存与时钟推进 | PASS | PASS |
| 20 | Guest 自动关机请求 | PASS | PASS |
| 21 | Guest 正常退出并返回 Host | PASS | PASS |
| 22 | Guest 返回后 Host、HU–HS–HU 及 syscall 复测 | PASS | PASS |
| 23 | 完整回归结果与事件顺序 | PASS | PASS |
| 24 | 测试命令与 QEMU 正常退出 | PASS | PASS |

## 7. VU → VS → VU 关键证据

真实 Guest 回归按以下顺序产生证据：

```txt
Stage2Virt Guest VU BEFORE PASS: GPA=<same-gpa> value=0x5a
Stage2Virt Guest VS PROBE PASS: GPA=<same-gpa> expected-access-fault
Stage2Virt Guest VU AFTER PASS: GPA=<same-gpa> value=0xa5
Stage2Virt Guest VU-VS-VU SAME-PAGE PASS: GPA=<same-gpa>
Linux Guest Stage2Virt VU-VS-VU runtime test PASS
```

统一结果解析器要求：

1. 五条证据位于同一次 Guest 生命周期内；
2. 每条证据只出现一次；
3. 顺序固定；
4. 四阶段 GPA 完全相同；
5. 日志中不存在 `Stage2Virt Guest ... FAIL`；
6. COMPLETE 成功清除运行时范围；
7. Guest 正常关机并返回 Host。

## 8. 验证中发现并修复的问题

### 8.1 Guest Kconfig 依赖

Guest 配置最初依赖当前内核不存在的 `MISC_DEVICES` 符号，导致 `olddefconfig` 删除：

```txt
CONFIG_RISCV_STAGE2_VIRT_GUEST_TEST=y
```

移除无效依赖后，Guest 内核配置能够稳定保留并完成构建。

### 8.2 kvmtool 清除请求

BEGIN、VS 探测和第二次 VU 写入成功后，COMPLETE 曾返回 `EIO`。根因是 kvmtool 在关闭 Stage2Virt 时仍向 Host 传递原 GPA 和 size，而 Host ABI 要求关闭请求的范围字段为零。

修复后，COMPLETE 成功，kvmtool 输出 Stage2Virt disabled，Guest 输出最终 SAME-PAGE PASS。

### 8.3 内层 Guest 日志实时输出

Buildroot 回归原来把内层 Guest 输出全部暂存到临时文件，运行期间容易误判为卡死。现在通过 FIFO 和 `tee` 同时实时显示并保存日志，同时独立保留 `run-virt-guest` 的真实退出码，避免管道状态掩盖 lkvm 失败。

## 9. 最终结论

Stage2Virt Linux Guest 实验已经完成端到端闭环：

```txt
VU 写入目标页
→ Guest 内核通过 SBI BEGIN 报告 GPA/size
→ kvmtool 调用 Host KVM Stage2Virt ioctl
→ VS 对同一 GPA 的写访问按预期失败
→ VU 对同一页再次写入成功
→ SBI COMPLETE 清除 Stage2Virt 范围
→ Guest 正常退出
→ Host 返回后保护状态复测通过
```

Buildroot 和双 Debian 均为 24/24 PASS，证明实现不仅通过单元测试和 mock，也在两种真实双层 Linux 环境中完成了相同的运行时权限验证。

## 10. 验证边界

本次结果覆盖单 vCPU、单页、4 KiB 对齐范围和一次完整会话。当前运行时测试模式明确拒绝多 vCPU。以下内容不在本次结论范围内：

- 多 vCPU 并发 BEGIN/COMPLETE；
- 多页或多个不连续 GPA 范围；
- 长时间压力与重复启停测试；
- 非实验接口的通用 ABI 稳定性承诺。

这些边界不影响本次 Linux Guest 单页 `VU → VS → VU` 实验目标已经完成的结论。
