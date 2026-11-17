# 第四阶段：双 Debian 与自动化

目标是保留第三阶段的受保护 host 内核和普通 guest 内核，将两层用户空间都换为 Debian，并自动创建、初始化和更新磁盘。
这是当前日常操作入口，组件编译方法见 [第三阶段](../03-pmp-virt-kvm/README.md)。

| 文件 | 用途 |
| --- | --- |
| [experiment-report.md](experiment-report.md) | 完整实验报告：目标、逐文件改动、运行命令、调用链和最新验收结果 |
| [architecture.md](architecture.md) | 两层启动链、磁盘关系、脚本职责和维护启动 |
| [prepare.md](prepare.md) | 首次创建、固定路径、备份重建及失败恢复 |
| [run.md](run.md) | 正常启动、登录识别、关机和完整回归 |
| [update.md](update.md) | 服务器自动更新两层工具，保留磁盘配置 |
| [tool-versions.md](tool-versions.md) | 安装后文件、权限、版本和两层配套关系的自动校验 |
| [validation.md](validation.md) | 已有验证结果、证据位置和待完成事项 |

在服务器项目根目录操作：

```sh
make virt-verify
make debian-prepare
make run-virt-dual-debian
```

逐条确认成功后继续。磁盘已存在时跳过准备，日常只启动；关机后执行 `make debian-update` 更新工具。
显式重建使用 `make debian-prepare DEBIAN_RECREATE=1`，会备份并替换正式系统盘。
