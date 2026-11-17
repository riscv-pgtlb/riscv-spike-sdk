# 统一 PMP.Virt 测试入口

在服务器项目根目录执行：

```sh
make pmpvirt-test
```

默认运行双 Debian。先关闭已有的双 Debian，准备好两块已初始化且已安装测试工具的磁盘。
入口先执行现有单元测试和真实产物校验，再检查磁盘并提示输入外层 Debian 的 root 密码。
密码仅用于串口登录，不作为命令参数，也不保存到日志。

## 集成范围

1. 运行现有 `tests/pmp-virt/unit/`，等价于 `make virt-test-static`。
2. 执行 `virt-kvm.py verify`，等价于 `make virt-verify`，归档产物清单与源码版本锁。
3. 启动**外层**，读取本次启动的封存、HS 探针和 SBI guard 结果。
4. 自动登录外层，调用已安装的 `test-virt-debian-all /dev/vdb`。
   Debian 模式会先验证安装文件及服务器预期版本，并要求内层版本配套，见 [工具版本校验](../04-dual-debian/tool-versions.md)。
5. 检查 guest 前后的同页 U → HS → U、内层检查、关机、返回以及完整套件结果。
6. 检查测试命令退出码，正常关闭外层并等待 QEMU 退出。

每项显示 PASS、FAIL 或 SKIP；前置检查失败时，未执行的后续项目保持 SKIP。
16 个汇总测试点固定编号为 `[TEST 1]` 至 `[TEST 16]`，终端和 `summary.txt` 使用相同编号，`result.json` 的每项也保存 `number`。
终端中每个编号仅在该测试点首次输出时显示，后续状态和进度缩进，所有状态标签保持同列对齐。
交互终端中 PASS 为绿色、FAIL 为红色、SKIP 为黄色、RUN 为青色；重定向输出自动关闭颜色，汇总文件保持纯文本。
设置 `NO_COLOR=1` 可禁用颜色，例如 `NO_COLOR=1 make pmpvirt-test`。
HS 三组前后对照和 SBI guard 来自启动探针；guest 返回后重新执行的是同页探针，没有重跑全部启动测试。
成功退出必须同时满足输出证据、测试命令退出码和 QEMU 退出状态，不能只凭 `ALL PASS` 字符串。
失败时另外显示失败阶段、原因、建议操作和日志位置，并写入 `result.json` 的 `diagnostics` 及 `summary.txt`。
例如登录被拒绝时，后续项目说明为“外层登录被拒绝，未启动此项”，不把它们误报为保护测试失败。

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

超时单位为秒，默认 600。正常结束会关机；超时或致命错误时会终止本入口启动的进程，
此时应查看日志，不能把异常中止当作正常关机。
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
```

原有 `make virt-test-static`、`make virt-test` 和手动外层完整套件仍可单独使用。
原理与更细的内核调用关系见 [PMP.Virt 讲解](pmp-virt-explained.md)。

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
成功最终输出 `PMPVIRT TEST PASS`；失败返回非零状态。这里仅整合现有测试，不新增扩展开关对照、VS/VU 配对、多核或压力测试。
