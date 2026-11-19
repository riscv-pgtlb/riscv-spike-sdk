# 更新已有环境

服务器推荐 make debian-update；关闭两层后自动维护启动。Debian 内本地目录更新仅作为另一入口。

| 文件或目录 | 用途 |
| --- | --- |
| [update-dual-debian.py](update-dual-debian.py) | 服务器检查两盘、打包、依次维护更新并记录状态和日志。 |
| [update-system.sh](update-system.sh) | 维护虚拟机内校验包并调用安装器，保留原有账号和系统配置。 |
| [update-tools.sh](update-tools.sh) | 两个 Debian 内更新命令的共用实现，支持 --from-dir，校验包后安装。 |
| [update-host-tools.sh](update-host-tools.sh) | （手动更新）外层 update-host-tools 命令入口。 |
| [update-guest-tools.sh](update-guest-tools.sh) | （手动更新）内层 update-guest-tools 命令入口。 |
| [check-virt-tools.sh](../common/check-virt-tools.sh) | 检查已安装文件内容、权限及元数据；--expect-version 可核对服务器预期版本，--root 支持检查隔离根目录。 |
