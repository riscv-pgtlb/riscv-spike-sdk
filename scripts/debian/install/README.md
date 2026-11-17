# 打包与安装

安装器在 Debian 内以 root 运行；包保留 scripts/、tests/ 的目录结构，只包含安装和运行需要的文件。

| 文件或目录 | 用途 |
| --- | --- |
| [pack-tools.sh](pack-tools.sh) | 服务器生成外层完整包、内层小包及 SHA256SUMS，输出到 build/debian-host-transfer/。 |
| [tool-manifest.py](tool-manifest.py) | 唯一定义两层的源文件、安装路径和权限，生成内容版本与配套 guest 版本；服务器测试复用相同计算。 |
| [install-tools.sh](install-tools.sh) | 共用安装实现：安装前校验所有输入，按清单安装并校验实际内容和权限，保存版本及清单。DESTDIR 支持隔离安装测试。 |
| [install-host.sh](install-host.sh) | 外层安装 lkvm、guest 内核、保护检查、启动、回归和更新命令。 |
| [install-guest.sh](install-guest.sh) | 内层安装检查程序、测试服务和更新命令；--offline 供带部署标记的维护环境使用。 |
