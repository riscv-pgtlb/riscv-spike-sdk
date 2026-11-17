# PMP.Virt Buildroot 启动命令

由构建脚本安装到 Buildroot 外层系统，运行前检查 host 保护。

| 文件或目录 | 用途 |
| --- | --- |
| [run-virt-guest.sh](run-virt-guest.sh) | 启动 Buildroot 内层；--regression 开启自动回归。 |
| [run-virt-debian.sh](run-virt-debian.sh) | 从 Buildroot 外层启动 Debian 内层，配置外层 DHCP。 |
