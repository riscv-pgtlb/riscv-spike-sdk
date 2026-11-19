# VS–HS–VS：SDK 五步集成记录

日期：2026-11-19。范围为 SDK 集成和单元测试，尚未执行正式构建及虚拟机运行。VS–HS–VS 放在执行顺序对应的第 11 项；共 17 项，原 11～16 项顺延。

## 第 1 步：固定配套组件提交

| 文件/记录 | 作用 |
| --- | --- |
| `conf/pmp-virt/sources.json` | host=`f71c60d7b3e8ca338ac99463aaa70df744b37063`；guest=`b17be9459b581c2e6e090082b3a164e34731c061`；kvmtool=`3010d50f699b7f62aea63d49bbed2242959d23d3`。guest 路径为 repo/linux-guest。 |
| SDK 的 `repo/linux`、`repo/kvmtool` gitlink | 在暂存区同步已推送的子模块提交，满足与版本锁一致的检查；尚未提交 SDK。 |
| `.gitmodules` 与版本锁中的 kvmtool URL | 核对使用团队 fork https://github.com/riscv-pgtlb/kvmtool.git；该地址在本轮开始前已设置，本轮未重复修改。 |

不改 OpenSBI 源码提交；后续仍必须根据新的 host Image 布局重新构建固件。

## 第 2 步：构建配置和产物打包

| 文件 | 作用 |
| --- | --- |
| `scripts/build/virt-kvm.py` | guest 显式启用并核验 CONFIG_RISCV_PMP_VIRT_GUEST_TEST=y，host 不启用此 guest 专用选项。新增日志检查脚本进入构建输入校验和 Buildroot host rootfs。 |
| 同一构建文件中的 prepare_source | 显式执行 prepare 时，旧 kvmtool 源码若干净且 HEAD 对应旧状态，先移入 build/virt-kvm/src/archive-kvmtool-*/source，再按新锁准备副本；有修改或状态不符就拒绝，保留现场。 |
| `scripts/debian/install/tool-manifest.py` | host 包增加 check-virt-vs-hs；既有 lkvm、guest Image 条目自动纳入新内容版本。 |

本次没有实际执行 prepare，也没有移动当前真实构建源码副本；测试只操作临时目录。guest 开发源码仍直接使用 repo/linux-guest。

## 第 3 步：两种系统的回归启动入口

| 文件 | 作用 |
| --- | --- |
| `tests/pmp-virt/regression/debian/test-virt-debian-all.sh` | 测试用 lkvm 加 --pmp-virt-test，guest 加 pmpvirt_guest_test=1；guest 返回后先检查保存的串口日志，再允许完整套件通过。 |
| `scripts/buildroot/run-virt-guest.sh` | 仅 --regression 模式传入上述开关；普通登录模式不启用。 |
| `tests/pmp-virt/regression/buildroot/test-virt-all.sh` | 保存内层输出和退出结果，再输出日志并调用同一检查器；失败或缺证据时停止。 |

Buildroot 的内层输出会先写入临时日志，内层退出后打印；服务器运行中可能暂时看不到该阶段逐行输出，超时仍由外层入口控制。

## 第 4 步：统一证据判定和第 11 项

| 文件 | 作用 |
| --- | --- |
| 新增 `tests/pmp-virt/runtime/check-virt-vs-hs.sh` | 用 POSIX awk 检查五阶段、地址一致性和失败记录，可在精简 Buildroot、Debian 和服务器运行，避免三份规则漂移。 |
| `tests/pmp-virt/regression/buildroot/run-regression.py` | 原 Buildroot 自动回归也要求新证据，不能仅凭旧 ALL PASS 成功。 |
| `tests/pmp-virt/regression/run-suite.py` | 在 guest 基本检查前插入 vs_hs 项；只在本轮 HOST BEFORE 与 GUEST RETURNED 之间判定，复用同一检查器。 |

五阶段：VS BEFORE → lkvm BEGIN（GPA/HPA/cause=1）→ VS AFTER → lkvm COMPLETE（同 GPA/HPA、guest_report=42）→ guest 最终 SAME-PAGE PASS。GPA 的补零与 0x 表示差异会被规范化。完整成功仍要求其他项目及命令/QEMU 退出状态通过。

## 第 5 步：单元测试及文档

| 文件 | 作用 |
| --- | --- |
| `tests/pmp-virt/unit/test_pmpvirt_suite.py` | 成功日志样本加入新阶段；新增缺失、重复、错顺序、GPA/HPA 错配、错误返回、失败覆盖、窗口外证据、关机顺序及编号检查。 |
| `tests/pmp-virt/unit/test_build.py` | 检查 guest 配置、Buildroot 检查器安装、干净旧 kvmtool 归档和脏副本保留；原日志解析测试同步。 |
| `tests/pmp-virt/unit/test_directory_layout.py` | 实际创建并隔离安装 host 包，要求新检查器存在。 |
| `docs/03-pmp-virt-kvm/test-suite.md` | 更新 17 项及第 11 项判据和未验证边界。 |
| `docs/03-pmp-virt-kvm/README.md` | 增加本记录入口。 |
| `tests/pmp-virt/runtime/README.md`、`tests/pmp-virt/unit/README.md` | 补充检查器和测试覆盖说明。 |
| `scripts/debian/install/README.md` | 更新工具包树与新安装命令。 |
| `docs/03-pmp-virt-kvm/pmp-virt-explained.md`、`report/README.md`、`report/sdk.md` | 同步新增测试、17 项数量及旧报告基线与当前集成的区别。 |
| 本文件 | 记录分步文件用途和待执行操作。 |

测试命令：`python3 -B -m unittest discover -s tests/pmp-virt/unit -p 'test_*.py'`。本轮共 97 个单元测试全部通过；另外检查了源码版本与 gitlink 一致及相关 Shell 语法。测试使用临时源码、模拟命令/串口及隔离安装，不等于真实 VS/HS 权限测试通过。

## 后续工作（本轮不执行）

1. 运行构建前检查和 prepare，处理新版本源码；构建新版 host、guest、lkvm 及与 host 配套的 OpenSBI/rootfs。
2. 校验新产物后，关闭两套 Debian 并更新工具；通常不需要重建 Debian 根磁盘。
3. 分别运行 Debian 和 Buildroot 回归，要求第 11 项及全部 17 项通过，并保留日志、地址与版本证据。
4. 若运行暴露探针、页表、页固定或 SBI 通信问题，修复组件、重新提交并更新版本锁，不以单元测试替代真实验证。
5. 验证后提交 SDK 的版本锁、gitlink、测试、脚本与文档。现有历史报告中的旧测试数量/提交属于先前基线，本记录说明新集成状态。


## 首轮 Debian 运行发现的问题

suite-20261119-172755-881115 已通过 host 的前置保护检查，guest 在第一次调用测试页时发生 cause=12 的指令页故障。日志 PTE 不含执行位，尚未进入 VS BEFORE 或 host BEGIN。原因是通用 vmap 路径主动应用 pgprot_nx，单传 PAGE_KERNEL_READ_EXEC 不足以得到可执行映射。

guest 修复显式核对页表 PFN、读权限及 U0/no-W，设置执行位、刷新 TLB 并再次核验；该修复需要提交新 guest 版本并更新版本锁后重新构建。SDK 同时收紧 HOST_SUITE_MISSING 的诊断匹配，避免将不相关的 No such file 与命令回显组合成错误结论。修复后目标文件编译及 98 个 SDK 单元测试通过，尚未进行修复后的真实运行。


## 第二轮：串口混排导致的判定失败

suite-20261119-173449-521476 中 guest、host 和 lkvm 的五阶段都完成，GPA/HPA 对应一致，但 host printk 插入了 guest VS BEFORE 的 result=42 中间，形成 re + host 多条记录 + sult=42。内层串口文件未混入外层 printk，所以磁盘内检查通过，而服务器的混合 console.log 原先无法匹配。

共用检查器现在仅允许重组插入了已知 host PTE、成功探针和帧检查记录的结果行；保留阶段、地址、返回值和失败判据，未知插入或缺失后半行仍失败。新增了该真实输出形态及坏结果/缺片段/未知插入/错误异常码反例。99 个单元测试通过；重新解析保存的第二轮控制台时，全部运行检查点证据齐全。原 result.json/summary.txt 保持原样，未把旧失败记录改写为新成功，也尚未执行修复后的新一轮回归。


## 第三轮：原始回车与文件读取的差异

suite-20261119-181304-523184 的实时输入中，完整 guest result=42 后存在单独回车，接着是 host printk。terminal_text 删除回车后两条记录粘连，旧重组逻辑错误等待后续片段。此前 read_text 的通用换行转换将该回车变成换行，掩盖了问题；仅重读文本不能代表实时字节输入。

检查器现在区分完整结果与未完成片段：完整前缀立即进入原有严格阶段/地址判定，只有真正不完整的前缀才等待续行。新测试直接构造原始回车，覆盖三种 guest 记录及错误返回/地址。102 个 SDK 单元测试通过；173449 和 181304 两轮原始日志均以 read_bytes().decode() 重放，运行检查点证据齐全。旧结果文件未修改，修复后仍需新一轮真实回归。


## 最终真实验证

2026-11-19 修复后 Debian 与 Buildroot 均通过 17/17，分别耗时 108.45 秒和 19.98 秒。验证摘要及来源提交见 [双环境验证记录](validation/vs-hs-20261119/README.md)。该结果更新前述“尚未重跑”的阶段状态；不代表多核或任意虚拟化场景验证。
