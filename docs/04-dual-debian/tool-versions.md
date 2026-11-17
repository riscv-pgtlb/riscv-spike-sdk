# 安装后工具版本校验

构建产物校验通过，不代表 Debian 磁盘中的工具已经更新。现在每层安装器都会保存文件清单与内容版本，
`make pmpvirt-test` 将两层的实际文件与服务器当前源文件和构建产物对应起来。
这项校验不读取整盘摘要，也不重设账号或系统配置。

## 使用

已有磁盘先关闭两层，安装这一版工具：

```sh
make debian-update
make pmpvirt-test
```

逐条确认成功后继续。旧磁盘没有清单或校验命令时会明确失败，需要更新工具，不需要重建磁盘。
首次 `make debian-prepare` 也会自动安装清单和检查命令。

在任一层 Debian 手动核对本地安装状态：

```sh
check-virt-tools
```

默认检查与本地保存的版本是否一致；这本身不证明是服务器最新版本。
`make pmpvirt-test` 会额外计算并传入服务器当前预期版本，拒绝整套自洽但过旧的工具。
不匹配时输出文件路径或 `expected=... installed=...`。

## 清单和版本如何生成

`scripts/debian/install/tool-manifest.py` 是文件列表的唯一来源，定义 SHA-256、安装模式、包内路径和安装目标。
外层覆盖 lkvm、pv-user-test、guest Image、保护检查、启动/回归/更新脚本和校验器；
内层覆盖 guest 检查、测试服务、更新脚本和校验器。

每个包包含 `metadata/host/` 或 `metadata/guest/`：

| 文件 | 用途 |
| --- | --- |
| `FILES.tsv` | 每行四列：文件摘要、安装权限、包内源路径、绝对安装路径 |
| `INPUTS.SHA256SUMS` | 包内输入的校验值，包含安装器与共用安装实现 |
| `ROLE` | host 或 guest |
| `VERSION` | ROLE、FILES.tsv、INPUTS.SHA256SUMS 内容组合的 SHA-256，不依赖打包时间 |
| `EXPECTED-GUEST-VERSION` | 仅外层包有，记录配套内层工具版本，并作为受检查文件安装 |

打包输出目录还会有 `HOST-VERSION`、`GUEST-VERSION`；顶层 `SHA256SUMS` 覆盖两个压缩包和这两个版本文件。
guest 工具变化会更新 guest 版本，也会通过配套版本使 host 版本变化。

## 安装和运行检查

安装前检查所有输入内容，源文件损坏时不开始复制。安装后清单保存到 `/var/lib/virt-tools/`，
`check-virt-tools` 校验元数据一致性、目标文件存在且非符号链接、实际内容和安装权限。
安装失败不自动回滚；应根据失败日志修复后重新更新。

完整双 Debian 回归中：

1. 服务器计算当前两层预期版本，记录到本轮 `expected-tools.json`。
2. 登录外层后先检查 host 版本，再调用完整套件并传入 host/guest 预期版本。
3. 外层检查配套 guest 版本，通过 `virt_tools_version=<版本>` 内核参数交给内层。
4. 内层测试服务先运行 `check-virt-tools --role guest`，验证版本和实际文件，再进行内核、内存和时间检查。
5. 外层核对内层版本成功标记，guest 返回后再检查 host 文件及版本。

内层检查失败时也会请求关机，但不会输出成功的 `GUEST SHUTDOWN` 标记；外层据缺少成功证据判为失败。
这样无需为了文件版本错误一直等待超时。

16 个汇总测试点不变：外层版本检查并入 TEST 10 和 TEST 14，内层版本检查并入 TEST 11。
Buildroot 模式不使用 Debian 文件清单，仍执行原有检查。
手动运行外层完整套件默认使用本地配套版本；要与当前服务器源文件配对，应使用 `make pmpvirt-test`。

这是可信服务器与磁盘工具之间的一致性检查，不是签名认证，也不保证能抵抗已控制内核或检查程序的攻击者。
