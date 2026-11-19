# syscall 触发的固定目标保护测试

在 Ubuntu 实验服务器运行：

```sh
cd /home/czy/work/riscv-spike-sdk-dual-syscall
make virt-verify
make virt-test-static
make pmpvirt-test PMPVIRT_SYSTEM=buildroot
```

如果已登录外层受保护的 RISC-V host，可单独运行 `pv-syscall-attack`。
不要在 Ubuntu 服务器本机或内层 Debian 中运行这个二进制。

用户程序用 `syscall(SYS_ioctl, ...)` 调用 `/dev/pvtest` 的专用命令
`PV_SYSCALL_PROBE`。内核在该系统调用处理期间依次执行以下固定操作：

| 操作 | 映射与目标 | 预期 |
|---|---|---|
| 普通数据页同值写入对照 | 内核临时分配的普通 RAM | 无异常，cause=0 |
| HS 执行数据页 | 临时普通 RAM 中的固定 `return 42` 指令，S-stage RX、U=0 | instruction access fault，cause=1 |
| 写内核代码页 | `_text` 所在物理页的 S-stage RW、NX、U=0 别名 | store access fault，cause=7 |
| 写只读数据页 | `__start_rodata` 所在物理页的 S-stage RW、NX、U=0 别名 | store access fault，cause=7 |

写入采用现有启动探针的同值单字节 store，不修改活跃内核代码或只读数据。
判定依据是实际 store 的异常原因，并同时核对该字节操作前后的值；不能仅凭
“内容未改变”判断写入被拦截。内核在探测前验证写别名确实可写、执行别名确实
可执行、物理页匹配。页表拒绝产生的 cause=12/15 不满足本测试的 PASS 条件。

异常恢复只接受当前任务、固定指令地址、固定目标地址和相应异常类别的匹配，
不放宽通用异常处理。接口仅允许 CAP_SYS_ADMIN、启动探针完成、单 CPU；
不接受用户传入目标地址、指令或写入内容。所有探测共用原接口的互斥锁，
临时分配和映射在每次调用结束前释放。

程序先检查新命令的空输出指针和降权后继承 fd 两项拒绝行为，再重复三轮
四项内核操作。每次运行的预期结尾是：

```text
SYSCALL-ATTACK API: PASS 2/2 rejection checks
...
SYSCALL-ATTACK SUMMARY: PASS 12/12 checks (3 rounds x 4 cases)
```

`check-virt-host` 保留原来的同页 U → HS → U 和 12 项旧接口拒绝测试，并运行
新程序。自动回归分别在普通 KVM guest 运行前、退出后执行一次。
统一入口和 Buildroot 回归都要求两个阶段各有完整的接口汇总、两项拒绝检查、三轮四项操作和保护汇总。缺失、命令回显、错误异常原因、重复结果或明确 FAIL 都不能得到完整回归 PASS。

该测试覆盖 syscall 处理期间的上述 HS 访问行为，不表示 VS/VU 完整读写执行、
Virt 开关对照、G-stage.Virt 或联网/APT 已验证。

本次修改包含内核源码变化，因此首次需要重编译 host 和匹配布局的固件，不能
仅更新磁盘内的工具。从锁定源码完整重建可使用：

```sh
export CROSS_COMPILE=/home/czy/work/riscv-spike-sdk/rootfs/buildroot_initramfs/host/bin/riscv64-linux-
make virt-build
make virt-test
```

## 双 Debian 分支的迁移

源码位于 `tests/pmp-virt/runtime/syscall-api.c` 和 `syscall-attack.c`。
`make virt-build` 同时编译三个 host 测试程序，产物校验涵盖源码和二进制；
Buildroot initramfs 与 Debian host 工具包均安装两个 syscall 程序。
Debian 文件清单及版本摘要包含这两个程序，旧工具包不能冒充新版。

首次迁移需要完整重编译 host/匹配固件，再关闭两层并更新同一组磁盘：

```sh
make virt-build
make debian-update
make pmpvirt-test
```

`make debian-update` 保留原有账号和磁盘，只更新工具及 guest 内核；它不会编译 host 内核。
已有磁盘无需重新执行 `debian-prepare`。首次使用双 Debian 时遵循 README 的准备流程。
统一报告仍为 16 个汇总测试点，`host_before` 与 `host_after` 各自要求完整 syscall 结果。
新增的静态判定测试专门检查缺失、重复、回显、错误异常原因和两个阶段互相冒充。

另提供非登录模式的 Debian 13 快照冒烟测试：

```sh
python3 tests/pmp-virt/regression/debian/run-debian-smoke.py --sdk "$PWD" --disk /path/to/debian-guest.raw
```

它使用 `init=/bin/sh` 和 QEMU `snapshot=on`，原磁盘不接收写入。
该检查不能替代正常 systemd 双 Debian 回归，也不验证网络/APT。

本地源码锁引用 Linux 提交 `9870eb7fbafbba214684de20425a9635422a47c7`；
发布 SDK 前应先发布对应 Linux 提交，避免子模块固定版本无法获取。
