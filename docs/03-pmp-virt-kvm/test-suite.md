# 统一 PMP.Virt 测试入口

在服务器项目根目录执行：

```sh
make pmpvirt-test
```

默认运行双 Debian。先关闭已有的双 Debian，准备好两块已初始化且已安装测试工具的磁盘。

入口先执行现有单元测试和真实产物校验，再检查磁盘并提示输入外层 Debian 的 root 密码。

> 密码仅用于串口登录，不作为命令参数，也不保存到日志。

## 集成范围

1. 运行现有 `tests/pmp-virt/unit/`，等价于 `make virt-test-static`。
2. 执行 `virt-kvm.py verify`，等价于 `make virt-verify`，归档产物清单与源码版本锁。
3. 启动**外层**，读取本次启动的封存、HS 探针和 SBI guard 结果。
4. 自动登录外层，调用已安装的 `test-virt-debian-all /dev/vdb`。
   Debian 模式会先验证安装文件及服务器预期版本，并要求内层版本配套，见 [工具版本校验](../04-dual-debian/tool-versions.md)。
5. 检查 guest 前后的同页 U → HS → U、guest 启动期间的 VS → HS → VS、内层基本检查、关机、返回及完整套件结果。
6. 检查测试命令退出码，正常关闭外层并等待 QEMU 退出。

> 输出格式
>
> 1. 每项显示 PASS、FAIL 或 SKIP；前置检查失败时，未执行的后续项目保持 SKIP。
> 2. 17 个汇总测试点固定编号为 `[TEST 01]` 至 `[TEST 17]`，终端和 `summary.txt` 使用相同编号，`result.json` 的每项也保存 `number`。
> 3. RUN 进度缩进显示；最终 PASS/FAIL/SKIP 使用两位编号。成功项只显示名称，详细证据保存在 result.json；失败及跳过项保留原因。
> 4. 交互终端中 PASS 为绿色、FAIL 为红色、SKIP 为黄色、RUN 为青色；重定向输出自动关闭颜色，汇总文件保持纯文本。
> 5. 设置 `NO_COLOR=1` 可禁用颜色，例如 `NO_COLOR=1 make pmpvirt-test`。

HS 三组前后对照和 SBI guard 来自启动探针；guest 返回后重新执行的是同页探针，没有重跑全部启动测试。

成功退出必须同时满足输出证据、测试命令退出码和 QEMU 退出状态，不能只凭 `ALL PASS` 字符串。

失败时另外显示失败阶段、原因、建议操作和日志位置，并写入 `result.json` 的 `diagnostics` 及 `summary.txt`。

> 例如登录被拒绝时，后续项目说明为“外层登录被拒绝，未启动此项”，不把它们误报为保护测试失败。

## 选择系统和磁盘

复用原有 Buildroot 自动回归，不需要 Debian 密码：

```sh
make pmpvirt-test PMPVIRT_SYSTEM=buildroot
```

该模式调用原 `run-regression.py`，再按相同的测试点汇总其控制台结果。
两种模式各自运行一套系统，不会默认同时运行两个完整回归。

指定非默认 Debian 磁盘和超时：

```sh
make pmpvirt-test \
  DEBIAN_HOST_DISK=/path/to/debian-host.raw \
  DEBIAN_GUEST_DISK=/path/to/debian-guest.raw \
  PMPVIRT_TIMEOUT=900
```

超时单位为秒，默认 600。正常结束会关机；超时或致命错误时会终止本入口启动的进程，此时应查看日志，不能把异常中止当作正常关机。

入口不创建、重建或更新磁盘。旧磁盘没有完整套件时先关闭两层并执行 `make debian-update`。

无人值守时，可通过受限权限的密码文件提供外层 root 密码：

```sh
chmod 600 /path/to/private-password-file
make pmpvirt-test PMPVIRT_PASSWORD_FILE=/path/to/private-password-file
```

文件仅包含密码一行，放在源码仓库外，不提交。没有终端且没有密码文件时，Debian 模式明确报错，不跳过运行测试并假报成功。

## 调用链

```text
make pmpvirt-test
└─ tests/pmp-virt/regression/run-suite.py
   ├─ unittest discover → 现有 unit/ 测试
   ├─ scripts/build/virt-kvm.py verify
   ├─ Debian 模式
   │  └─ run-dual-debian.sh → QEMU → 外层登录
   │     └─ test-virt-debian-all /dev/vdb
   │        ├─ check-virt-host → pv-user-test → /dev/pvtest
   │        ├─ lkvm → 内层测试服务 → check-virt-guest → 关机
   │        └─ check-virt-host → ALL PASS → 外层关机
   └─ Buildroot 模式
      └─ 原 run-regression.py → test-virt-all → 原有完整回归
改之后：
make pmpvirt-test
└─ tests/pmp-virt/regression/run-suite.py
   ├─ unittest discover → unit/ 测试
   ├─ scripts/build/virt-kvm.py verify
   ├─ Debian 模式
   │  └─ run-dual-debian.sh → QEMU → 外层登录
   │     └─ test-virt-debian-all /dev/vdb
   │        ├─ check-virt-host
   │        │  └─ pv-user-test → /dev/pvtest
   │        │     └─ HU → HS → HU
   │        ├─ lkvm --pmp-virt-test → 内层启动
   │        │  ├─ guest 内核 pv_guest_test
   │        │  │  └─ VS → SBI → lkvm → host /dev/pvtest → VS
   │        │  └─ virt-guest-test.service
   │        │     └─ check-virt-tools → check-virt-guest → 关机
   │        ├─ check-virt-vs-hs → 检查五阶段日志与地址
   │        └─ check-virt-host → ALL PASS → 外层关机
   └─ Buildroot 模式
      └─ run-regression.py → test-virt-all
         ├─ check-virt-host
         │  └─ pv-user-test → /dev/pvtest
         │     └─ HU → HS → HU
         ├─ run-virt-guest --regression
         │  └─ lkvm --pmp-virt-test → 内层启动
         │     ├─ guest 内核 pv_guest_test
         │     │  └─ VS → SBI → lkvm → host /dev/pvtest → VS
         │     └─ virt-guest-autorun
         │        └─ check-virt-guest → 关机
         ├─ check-virt-vs-hs → 检查五阶段日志与地址
         └─ check-virt-host → ALL PASS
```

> pv-user-test：实际执行**同页 HU → HS → HU 测试**。
>
> guest 内核 pv_guest_test：与 lkvm、host /dev/pvtest 配合执行 **VS → HS → VS 测试**。
>
> check-virt-vs-hs：检查日志证据，本身不执行权限探针。

原有 `make virt-test-static`、`make virt-test` 和手动外层完整套件仍可单独使用。
原理与更细的内核调用关系见 [PMP.Virt 讲解](pmp-virt-explained.md)。

| 编号 | 测试内容 | 主要检查什么 |
|---|---|---|
| 1 | 逻辑与部署测试 | **make virt-test-static** 运行 `unit/` 中的自动测试 |
| 2 | 构建产物及配对 | **make virt-verify** 校验构建产物，以及 host 内核与固件是否配套 |
| 3 | 运行环境检查 | 检查本轮运行所需环境 |
| 4 | 启动封存 | 固件完成封存，Linux 确认封存状态 |
| 5 | HS RAM 执行 | 封存前允许执行，封存后拒绝执行 |
| 6 | text 可写别名 | 封存前后对照，确认封存后写入被拒绝 |
| 7 | rodata 可写别名 | 封存前后对照，确认封存后写入被拒绝 |
| 8 | 封存前 SBI guard | 9 项 SBI 接口保护检查 |
| 9 | 封存后 SBI guard | 封存后再次检查上述 9 项 |
| 10 | guest 启动前 host 检查 | 同一物理页的 U → HS → U 测试及 host 检查 |
| 11 | VS–HS–VS 同物理页权限对照 | 五阶段证据按序出现，GPA/HPA 对应一致；使用共用 check-virt-vs-hs 检查器 |
| 12 | guest 内部检查 | guest 内核、内存和时间检查；Debian 模式还核对工具版本 |
| 13 | guest 自动关机 | 确认 guest 检查通过后发出关机请求 |
| 14 | guest 正常返回 | 确认内层执行结束，外层套件接收到结果 |
| 15 | guest 返回后 host 检查 | 再做同页测试，并复核已有启动检查结果 |
| 16 | 完整套件结果 | **Debian 的 test-virt-debian-all /dev/vdb；Buildroot 的 test-virt-all** （检查 `ALL PASS` 及关键结果出现顺序） |
| 17 | 命令退出和 QEMU 结束 | 测试命令成功退出，外层 QEMU 正常结束 |

## 输出和证据

每次创建独立目录 `build/virt-kvm/logs/suite-<时间>/`：

| 文件 | 用途 |
| --- | --- |
| `static.log` | 现有单元测试完整输出 |
| `verify.log` | 构建产物校验输出 |
| `console.log` | 运行控制台；Debian 模式对密码做脱敏 |
| `inputs.json` | SDK HEAD、工作区状态、超时和磁盘路径 |
| `expected-tools.json` | Debian 模式中服务器当前预期的 host/guest 工具内容版本 |
| `manifest.json`、`sources.json` | 本轮产物清单和源版本锁快照 |
| `result.json` | 逐测试点的状态、错误及耗时 |
| `summary.txt` | 简要结果表 |
| `SHA256SUMS` | 已生成证据文件的校验值 |

前置失败时只保存已经产生的文件。Debian 完整套件也仍会在外层磁盘内保存 `Evidence:` 指向的 guest 串口日志。

结尾统一显示“结果：PASS（17/17）”、实际耗时和证据目录；失败显示实际通过数并返回非零状态。这里仅整合现有测试，不新增扩展开关对照、VS/VU 配对、多核或压力测试。


## M–HS–VS 目前对应的是 guest 运行检查

| 组合 | 代码是否支持 | 当前验证情况 |
| --- | --- | --- |
| M–HS–HU | **支持** | 已有专门的同页 HU → HS → HU 测试 |
| M–HS–VS | **支持其 PMP 层权限语义** | 已加入专门的 VS–HS–VS 同页探针与 SDK 判定；尚未完成真实虚拟机验证 |
| HS–VS–VU | 不属于这次 PMP.Virt 实现 | 不能据当前结果认定实现了 G-stage.Virt |

```txt
第 11 项
    └── guest 内执行 check-virt-guest
          ├── 检查 guest 内核名称
          ├── 检查内存数量
          └── 检查时间推进
```

源码是 [check-virt-guest.sh](/home/wsh/riscv-spike-sdk/tests/pmp-virt/runtime/check-virt-guest.sh)。

第 11 项没有执行“VS 成功、HS 对同一物理页执行失败”的比较，所以它不是第二种组合的直接权限验证。

| 文件或模块 | 需要增加什么 |
|---|---|
| guest Linux | 专用测试页、VS 执行探针，以及与 host 同步的接口 |
| `lkvm` / kvmtool | 接收 guest 报告的 GPA，将其转换为对应的 host 用户空间地址，并协调测试 |
| host `pv_access.c` | 新增受限测试接口，固定目标页，建立可执行别名，再进行 HS 执行探针 |
| host `pv_access_asm.S` | 尽量复用现有受控调用和异常恢复逻辑 |
| SDK 构建与版本锁 | 纳入新增的 guest 和 kvmtool 改动 |
| 回归脚本 | 收集三阶段结果，任何阶段失败就判定失败 |


| 步骤 | 执行者 | 操作 | 预期 |
|---|---|---|---|
| 1 | guest 内核，VS 态 | 在**专用测试页**放入固定指令并执行 | 成功 |
| 2 | guest → host | 报告测试页 **GPA**，并暂停等待 | 测试页保持不变 |
| 3 | host | 根据 GPA 找到对应 guest 内存映射，固定该页，取得 **HPA** | 确认目标页 |
| 4 | host 内核，HS 态 | 建立允许执行的内核映射，尝试执行同一页 | **被 PMP 拒绝** |
| 5 | host → guest | 通知继续执行 | — |
| 6 | guest 内核，VS 态 | 再次执行原测试页 | 成功 |


在 同一个 GitHub Linux 仓库中建立两个分支：
```
riscv-pgtlb/linux
├── pmp-virt-host     ← 从现有 host 提交开始
└── pmp-virt-guest    ← 从现有 guest 提交开始
```

1. 先在 **guest 内核**里加第一阶段探针：分配专用页、以 VS 身份执行固定指令，并记录 GPA
2. 改 **repo/kvmtool/**，加入默认关闭的 VS–HS 测试协调入口
3. 补 host Linux 的同页探针接口，再让 guest 接入 kvmtool 的握手协议，连通 VS → HS → VS 三个阶段
4. 提交三个子模块的修改
5. check-virt-vs-hs.sh


## VS–HS–VS 集成（当前第 11 项）

该项位于 guest 启动前 host 检查之后、guest 基本检查之前。原 11～16 项顺延为 12～17 项。实际探针在 guest 内核、host 内核和 lkvm 中运行；服务器和两种 host 完整套件共用 `tests/pmp-virt/runtime/check-virt-vs-hs.sh` 判定证据。

只接受按顺序出现的一组 VS BEFORE、lkvm BEGIN、VS AFTER、lkvm COMPLETE、guest SAME-PAGE PASS。地址按十六进制规范化后比较：所有 GPA 相同、BEGIN/COMPLETE 的 HPA 相同，HS BEGIN 的 cause 为 1，guest 两次返回 42。guest 基本检查或关机不得先于同页测试完成。重复阶段、缺阶段、错顺序、错误地址、失败记录及单独回显 PASS 均不能通过。

lkvm 日志是 host ioctl 成功后的桥接记录，COMPLETE 只有 host 检查 cause=1 且 HPA 未变才输出；guest 日志记录 VS 执行。此为协作实验，不是对恶意 guest 的认证证明，也不能替代完整进程退出检查。

回归模式传入 `lkvm --pmp-virt-test` 和 guest 启动参数 `pmpvirt_guest_test=1`。普通 guest 登录模式不默认启用该开关。旧 guest 内核无探针、旧 lkvm 不识别开关或旧 host 不支持 ioctl 时，不得跳过后报告全通过。

本次只完成 SDK 集成及单元测试，尚未重建配套产物、更新 Debian 磁盘工具或运行真实回归。逐文件改动和下一阶段操作见 [SDK 集成记录](vs-hs-sdk-integration.md)。


## 终端与汇总格式

```text
[TEST 01] [PASS] SDK 单元测试
[TEST 02] [PASS] 构建产物完整性与内核—固件配对
[TEST 03] [PASS] 运行环境与磁盘可用性
[TEST 04] [PASS] PMP.Virt 策略封存与内核确认
[TEST 05] [PASS] HS RAM 执行权限：封存前允许，封存后拒绝
[TEST 06] [PASS] 内核 text 写保护：可写别名访问被拒绝
[TEST 07] [PASS] 内核 rodata 写保护：可写别名访问被拒绝
[TEST 08] [PASS] 封存前 SBI 接口限制检查（9/9）
[TEST 09] [PASS] 封存后 SBI 接口限制检查（9/9）
[TEST 10] [PASS] guest 启动前：host、HU–HS–HU 同页及 syscall 检查
[TEST 11] [PASS] VS–HS–VS 同物理页执行权限对照
[TEST 12] [PASS] guest 内核、内存与时钟推进
[TEST 13] [PASS] guest 自动关机请求
[TEST 14] [PASS] guest 正常退出并返回 host
[TEST 15] [PASS] guest 返回后：host、HU–HS–HU 同页及 syscall 复测
[TEST 16] [PASS] 完整回归结果与事件顺序
[TEST 17] [PASS] 测试命令与 QEMU 正常退出

结果：PASS（17/17）
耗时：<实际秒数> 秒
证据目录：<本轮日志目录>
```

summary.txt 使用相同编号、名称和三行汇总；result.json 新增 counts（total/passed/failed/skipped），保留各项 detail 和 elapsed_seconds。失败不会伪装成 17/17，诊断信息仍输出。


## 与远程 syscall 实验合并

主项目合并本地 VS–HS–VS 集成与远程 syscall 实验后，保留第 11 项及 17 项总数。第 10、15 项的 host 检查同时要求 syscall API 拒绝测试和三轮固定目标保护测试，不能用最终 HOST PASS 替代逐项证据。详细合并版本及验证边界见 [合并记录](merge-syscall-vs-hs.md)。
