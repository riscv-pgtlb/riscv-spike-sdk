# PMP.Virt 原理、代码改动与测试调用链

本文解释本仓库实际实现的 PMP.Virt，而不是完整的通用权限隔离方案。日常双 Debian 操作见 [第四阶段](../04-dual-debian/README.md)，构建入口见 [本阶段 README](README.md)。

## 1. PMP.Virt 是什么

PMP 用物理地址范围和读、写、执行权限约束内存访问。本项目在修改版 QEMU 中增加实验性的 `PMP_VIRT` 标志，让同一物理区域的权限可以根据有效执行身份有所区别。

实验要解决的具体问题是：host 内核不应在普通 RAM 中任意执行代码，也不应改写内核代码和只读数据；与此同时，外层用户程序和普通 guest 仍需要运行。

例如，某页中存放用户程序的指令：

```text
外层用户态 U 执行该页 → 允许
外层内核 HS 执行同一物理页 → 拒绝
外层用户态 U 再次执行该页 → 仍允许
```

这是本项目同页测试要验证的差异。**这里的 U 是外层 Linux 的用户态，不是“内层 Debian”。** 内层运行属于另一条 KVM 虚拟化链。

当前实现是本地实验扩展：`PMP_VIRT = 1 << 6`，QEMU CPU 参数为 `x-pmp-virt=on`；封存接口也是自定义 SBI 扩展。不要把这些编码和接口当作通用平台都支持的功能。

### 执行身份

| 身份 | 在本实验中对应什么 |
| --- | --- |
| M | OpenSBI 固件，负责设置物理保护规则 |
| HS | 外层 Linux 内核，提供 KVM |
| U | 外层 Linux 上的用户程序，例如 `pv-user-test` 和 lkvm |
| VS / VU | 内层虚拟机的内核态 / 用户态 |

QEMU 当前代码在匹配到带 `PMP_VIRT` 的区域时，对非 M 模式且满足 `mode == PRV_U || virt` 的访问补足 PMP 层的 RWX 权限；普通 HS 不获得这次补足，M 模式保留原有 PMP 语义。页表检查仍然存在，PMP 层允许并不代表页表也允许。

这描述的是代码规则；现有同页实测主要覆盖外层 U 与 HS，不能据此声称已完成 VS/VU 的完整权限配对验证。

## 2. 在哪些组件上改了什么

三个核心组件通过团队子模块维护，具体提交固定在 [sources.json](../../conf/pmp-virt/sources.json)，SDK 不在每次构建时动态套用补丁。

### 2.1 QEMU：实现实验性的权限语义

| 代码 | 改动 |
| --- | --- |
| [pmp.h](../../repo/qemu/target/riscv/pmp.h) | 定义实验位 `PMP_VIRT` |
| [pmp.c](../../repo/qemu/target/riscv/pmp.c) | 在物理权限检查中根据有效身份决定是否补足 RWX，并将对应权限用于 TLB 填充 |
| [cpu_cfg.h](../../repo/qemu/target/riscv/cpu_cfg.h)、[cpu.c](../../repo/qemu/target/riscv/cpu.c) | 增加默认关闭的 `x-pmp-virt` 选项；限制为 TCG、PMP 开启、Smepmp 关闭的组合 |

当前启动参数包含：

```text
-machine virt -accel tcg
-cpu rv64,h=true,smepmp=off,x-pmp-virt=on
-m 2048M -smp 1
```

QEMU 在这里模拟具备该扩展的硬件。本仓库中的运行结果不能直接证明某块真实 RISC-V 芯片也支持同样规则。

### 2.2 OpenSBI：设置和封存保护规则

核心代码是 [sbi_ecall_pvseal.c](../../repo/opensbi/lib/sbi/sbi_ecall_pvseal.c)，主要完成：

1. 提供自定义 SBI 扩展 `0x0a000056`、功能号 0，供 host 请求封存。
2. 检查单 hart、PMP 数量和原始区域布局等条件，不满足就拒绝。
3. 使用编译时生成的可信布局设置规则，不接收 host 任意传来的地址或权限。
4. 保存 `sealed` 状态，重复封存请求返回已封存；在固件的相关重新配置路径重施规则，避免正常 PMP 初始化覆盖保护。
5. 规则写入后回读检查并刷新相关地址转换和指令缓存；致命失败停留在 M 态。

主要区域策略如下。PMP 条目有匹配优先级，表中的 RAM 规则不覆盖先匹配到的 text/rodata 规则。

| 区域 | 规则 |
| --- | --- |
| host text | RX，禁止写 |
| host rodata | R，禁止写和执行 |
| 其他受该 RAM 条目覆盖的内存 | 普通 HS 为 RW；带 `PMP_VIRT`，较低执行上下文可获得 PMP 层 RWX |
| 兜底未知地址 / MMIO | RW，不允许执行，也不委派 |

固件已有的前部 PMP 条目保留，不任意覆盖 OpenSBI 自身保护区域。

[sbi_ecall.c](../../repo/opensbi/lib/sbi/sbi_ecall.c) 还加入 SBI 扩展白名单。这样不能仅保护 HS 的直接访问，却放任它通过其他固件服务进行未允许的操作。该白名单在启用封存配置的固件中生效，测试会在封存前后分别检查它。

[sbi_hart.c](../../repo/opensbi/lib/sbi/sbi_hart.c) 中接入封存规则重施；配置入口见 [Kconfig](../../repo/opensbi/lib/sbi/Kconfig)。这里的“封存”是该实验固件实现的策略和状态管理，不等于宣称所有区域都设置了硬件 `PMP_L` 锁定位。

### 2.3 Linux host：请求封存并检查保护效果

| 代码 | 职责 |
| --- | --- |
| [arch/riscv/mm/init.c](../../repo/linux/arch/riscv/mm/init.c) | 在 `mark_rodata_ro()` 阶段执行封存前检查，调用 SBI 封存，再执行封存后检查 |
| [pv_access.c](../../repo/linux/arch/riscv/kernel/pv_access.c) | 实现 HS 访问探针、预期异常处理和同页用户测试的 `/dev/pvtest` 接口 |
| [pv_access_asm.S](../../repo/linux/arch/riscv/kernel/pv_access_asm.S) | 探针访问和异常恢复相关汇编，配合 C 代码记录访问结果 |
| [kernel/Makefile](../../repo/linux/arch/riscv/kernel/Makefile) | 将探针代码编入 host 内核 |

host 使用修改后的 Linux；普通 guest 使用另一个锁定的 Linux 提交，不执行 host 封存逻辑。构建脚本生成独立配置和输出，host 内建 KVM、关闭模块及动态代码相关选项，guest 不启用 KVM。

`/dev/pvtest` 是研究测试接口，不是通用业务接口：权限为 0600，ioctl 还要求 `CAP_SYS_ADMIN`、单在线 CPU，并只接受固定测试指令内容等条件。

### 2.4 SDK：将内核、固件和测试工具配起来

[virt-kvm.py](../../scripts/build/virt-kvm.py) 从最终 host `Image` 和 `System.map` 提取 text/rodata 的物理边界，检查对齐、范围和布局，生成：

```text
build/virt-kvm/generated/pmp_virt_layout.h
```

随后通过 `PMP_VIRT_LAYOUT_HEADER` 将布局编入 OpenSBI。`make virt-verify` 检查产物摘要、布局和固件中的 host Image 摘要，避免旧固件配新内核。这个摘要用于构建配对，不表示固件正在对运行时内存做密码学认证。

Debian 只替换用户空间和根磁盘；PMP.Virt 的核心规则仍在 QEMU、OpenSBI 和 host Linux 中。lkvm/KVM 用于运行普通内层，不能把“Debian 成功登录”单独当作保护验证成功。

## 3. 实际测试了什么

### 3.1 封存前后 HS 访问：6 项

探针保留相同的别名映射和测试指令，对比封存前后的行为：

| 操作 | 封存前 | 封存后 |
| --- | --- | --- |
| HS 执行普通 RAM 中的代码 | 成功 | 指令访问异常，cause=1 |
| 通过可写别名写 text | 成功 | 写访问异常，cause=7 |
| 通过可写别名写 rodata | 成功 | 写访问异常，cause=7 |

“可写别名”用于排除只是普通只读页表阻止了写入的解释。预期异常由探针恢复代码捕获；这里出现 access fault 正是成功条件，不是要求内核崩溃。

成功时输出 `PMP.Virt ACCESS SUMMARY: PASS 6/6`。这组测试发生在 host 启动时。

### 3.2 SBI guard：封存前后共 18 项

每个阶段检查 9 个接口：DBCN READ、PMU、DBTR、SSE、MPXY、HSM STATUS、SUSP、FWFT、CPPC。每项检查扩展探测返回不可用、直接调用返回 `SBI_ERR_NOT_SUPPORTED`、缓冲区内容未改变。

这组检查验证的是当前固件白名单针对所选接口的行为，不是所有 SBI 功能的完整安全审计。

### 3.3 同一物理页的 U → HS → U

[pv-user-test.c](../../tests/pmp-virt/runtime/pv-user-test.c) 编译为 `pv-user-test`，步骤是：

1. 用户态申请 RW/NX 匿名页，写入固定指令，再改成 RX。
2. 用户态执行，确认返回值为 42。
3. 通过 `/dev/pvtest` ioctl 请求 HS 探针。
4. 内核固定同一物理页，为其建立 RX、U=0 的内核别名，并检查页表属性。
5. HS 尝试执行该别名，预期得到 cause=1。
6. 返回用户态，再执行原页，确认仍返回 42。

建立 U=0、RX 的内核别名，是为了避免把“HS 不能直接执行用户映射”误认为本实验物理保护的效果。测试输出物理地址和异常原因用于配对。

成功标记是 `PMP.Virt USER SUMMARY: PASS U-success / HS-access-fault / U-success`。

### 3.4 guest 启停与返回后的复测

guest 检查确认普通内核、内存和时间推进正常，随后正常关机。返回 host 后重新运行同页测试，验证该保护行为在一次 guest 生命周期后仍成立。

**返回后不会重新执行全部启动探针。** `check-virt-host` 核对本次启动日志中的 HS 6/6、SBI guard 18/18 和封存确认，再实际执行一次 `pv-user-test`。

## 4. 怎么运行

推荐统一入口 `make pmpvirt-test`，默认自动驱动双 Debian；`make pmpvirt-test PMPVIRT_SYSTEM=buildroot` 选择 Buildroot。
它整合下面的逻辑检查、产物校验和完整运行测试，详见 [统一测试说明](test-suite.md)。以下入口也可分别运行。

### 4.1 先区分运行位置

| 位置 | 应执行的命令 |
| --- | --- |
| 服务器项目根目录 | `make virt-test-static`、`make virt-verify`、构建和 QEMU 启动命令 |
| 受保护外层 Linux | `check-virt-host`、`test-virt-debian-all /dev/vdb` |
| 普通内层 Linux | `check-virt-guest`；双 Debian 安装后路径为 `/usr/local/bin/check-virt-guest` |

服务器是运行 QEMU 的宿主机器，不是本文中的“受保护 host”。不要在服务器上直接运行外层检查脚本。

### 4.2 不启动虚拟机的测试

在服务器执行：

```sh
make virt-test-static
make virt-verify
```

前者运行 `tests/pmp-virt/unit/`，包括布局、配对、日志解析及部署更新测试；后者检查真实构建产物。这两者都不能代替 PMP.Virt 的实际访问测试。没有构建产物时，先按 [构建指南](README.md) 完成构建。

### 4.3 当前双 Debian 完整测试

已有初始化磁盘和工具时，在服务器执行：

```sh
make run-virt-dual-debian
```

登录外层后执行：

```sh
uname -r
test-virt-debian-all /dev/vdb
```

内核名应包含 `pmpvirt-kvm-host`。确保内层未运行，且 `/dev/vdb` 及其分区没有被外层挂载。
完整套件自动启动内层、检查并关机，最终应输出 `VIRT-REGRESSION ALL PASS`。
单独检查外层可执行 `check-virt-host`；正常登录内层使用 `run-debian-guest`，它不会自动执行整套回归。

新磁盘准备、已有磁盘工具更新分别见 [prepare.md](../04-dual-debian/prepare.md) 和 [update.md](../04-dual-debian/update.md)。不要为了测试反复重建已有磁盘。

### 4.4 Buildroot 全自动回归

在服务器执行：

```sh
make virt-test
```

它运行 Buildroot 外层与普通 Buildroot 内层，不是双 Debian 测试。服务器驱动登录、测试和 QEMU 退出；无需手动进入控制台。

## 5. 测试调用链

### 5.1 host 启动时：封存与启动探针

```text
服务器启动 QEMU（开启 x-pmp-virt）
└─ OpenSBI 启动 host Linux
   └─ Linux mark_rodata_ro()
      ├─ pv_sbi_guard_test("before seal")：9 项
      ├─ pv_access_before()：3 项封存前对照
      ├─ sbi_ecall(0x0a000056, 0, 全零参数)
      │  └─ OpenSBI pvseal handle()
      │     ├─ 检查调用身份、参数和 preflight 条件
      │     ├─ apply_policy()：配置 PMP、回读和刷新
      │     └─ sealed=true，返回成功
      ├─ pv_access_after()：3 项封存后权限检查
      └─ pv_sbi_guard_test("after seal")：9 项
```

**这些检查早于 Debian/Buildroot 用户空间登录**。QEMU 的 PMP 权限逻辑在探针实际访问内存时生效，不是脚本看到某个字符串后才启用保护。

### 5.2 用户空间：check-virt-host 到同页探针

```text
check-virt-host（源码 tests/pmp-virt/runtime/check-virt-host.sh）
├─ 核对 host 内核身份、/dev/kvm、/dev/pvtest
├─ dmesg 检查封存确认、HS 6/6、SBI guard 18/18，拒绝失败标记
└─ /usr/bin/pv-user-test（由 pv-user-test.c 编译）
   ├─ U 执行固定指令，返回 42
   ├─ ioctl(/dev/pvtest, PV_USER_PROBE)
   │  └─ 内核 pv_user_ioctl()
   │     ├─ 检查权限、单核、用户映射和固定指令
   │     ├─ 固定同一物理页，建立并检查 HS RX/U=0 别名
   │     └─ probe() 执行 → QEMU PMP 检查拒绝 → 捕获 cause=1
   └─ U 再执行原页，返回 42
```

安装后脚本名为 `/usr/bin/check-virt-host`，由 [install-host.sh](../../scripts/debian/install/install-host.sh) 或 Buildroot rootfs 打包流程安装。

### 5.3 双 Debian 完整回归

```text
服务器 make run-virt-dual-debian
└─ scripts/debian/run/run-dual-debian.sh
   ├─ 校验产物、两块磁盘和操作锁
   └─ QEMU → OpenSBI → host Linux → 外层 Debian
      └─ 外层执行 test-virt-debian-all /dev/vdb
         ├─ check-virt-host：启动结果核对 + 同页测试
         ├─ 检查内层盘没有挂载，建立 Evidence 日志目录
         ├─ script 记录 lkvm 控制台
         │  └─ lkvm → /dev/kvm → guest 内核 → 内层 Debian
         │     └─ virt-guest-test.service（要求 virt_regression=1）
         │        ├─ check-virt-guest：内核、内存和时间检查
         │        ├─ 输出 GUEST SHUTDOWN
         │        └─ systemctl poweroff
         ├─ lkvm 返回，检查内层 PASS、关机标记和错误输出
         ├─ check-virt-host：再次同页测试，核对原启动结果
         └─ VIRT-REGRESSION ALL PASS
```

完整套件直接调用 lkvm，不经正常登录用的 `run-debian-guest`，因为需要添加测试启动参数和记录日志。
源码入口是 [test-virt-debian-all.sh](../../tests/pmp-virt/regression/debian/test-virt-debian-all.sh)，内层服务是 [virt-guest-test.service](../../tests/pmp-virt/regression/debian/virt-guest-test.service)。

### 5.4 Buildroot 完整回归

```text
make virt-test
└─ tests/pmp-virt/regression/buildroot/run-regression.py
   ├─ 校验产物和源码版本，启动 virt-kvm.py run
   ├─ 驱动外层登录，执行 /usr/bin/test-virt-all
   │  └─ test-virt-all.sh
   │     ├─ check-virt-host
   │     ├─ run-virt-guest --regression
   │     │  ├─ 再检查 host 保护
   │     │  └─ lkvm → guest → virt-guest-autorun.sh
   │     │     └─ check-virt-guest → 关机
   │     └─ 返回 host，再执行 check-virt-host
   └─ 检查结果顺序、退出 QEMU、归档控制台和结果
```

## 6. 看哪些输出和日志

| 输出 | 含义 |
| --- | --- |
| `PMP.Virt SEALED:` | OpenSBI 报告已设置封存规则及布局 |
| `PMP.Virt seal acknowledged` | Linux 收到 SBI 成功回应 |
| `PMP.Virt ACCESS SUMMARY: PASS 6/6` | 封存前后 HS 探针通过 |
| `PMP.Virt SBI GUARD PASS before seal ...` / `after seal ...` | 各阶段所选 SBI 接口检查通过 |
| `PMP.Virt USER SUMMARY: PASS U-success / HS-access-fault / U-success` | 同页 U/HS 区别通过 |
| `VIRT-REGRESSION GUEST PASS` | guest 基本检查通过，不单独证明 host 保护 |
| `VIRT-REGRESSION ALL PASS` | 对应完整套件的所有检查通过 |

双 Debian 的内层日志位于外层磁盘内 `/var/log/virt-regression/debian-*/`，路径由 `Evidence:` 输出。
如需完整保留外层启动和复测输出，可在服务器用 `script` 录制 `make run-virt-dual-debian` 的控制台。
Buildroot 自动回归在服务器 `build/virt-kvm/logs/regression-*/` 保存控制台、产物快照、结果和校验值。
不要把 `prepared-*/provision-*.log` 或更新日志当作完整保护回归证据；它们只记录维护部署。

## 7. 当前能证明和不能证明什么

现有测试验证固定单 hart 环境中：封存前后选定的 HS 访问行为发生变化，所选 SBI 服务被拒绝，同一物理页上外层 U 可执行但 HS 执行被拒绝，以及该行为在一次普通 guest 启停后仍存在。

它不能替代 G-stage.Virt、VS/VU 同页配对、SMP、长期压力或完整攻击面审计。QEMU 模拟、固件和测试接口均是实验的一部分；OpenSBI 处于可信位置，摘要配对也不等同于安全启动或运行时完整性认证。
本文依据当前源码解释机制与调用关系，编写文档本身不代表重新执行测试；已有结果与待验收事项见 [双 Debian 验证记录](../04-dual-debian/validation.md)。


## 新增 VS–HS–VS 协作测试

SDK 已接入 guest 内核探针、lkvm 实验 SBI 协调和 host 固定页接口，作为统一套件的第 11 项。guest 使用启动开关 pmpvirt_guest_test=1，lkvm 使用 --pmp-virt-test；HU–HS–HU 的 pv-user-test 保留原用途。完整阶段、配套提交和逐文件改动见 [SDK 集成记录](vs-hs-sdk-integration.md)。

当前只通过单元测试和先前的组件编译检查，尚未验证真实虚拟机中的 VS–HS–VS 结果，因此前文对已完成运行验证的边界仍然成立。
