# 创建与初始化

make debian-prepare 创建固定路径磁盘；已有磁盘默认停止，DEBIAN_RECREATE=1 允许备份重建。

| 文件或目录 | 用途 |
| --- | --- |
| [prepare-dual-debian.sh](prepare-dual-debian.sh) | 服务器总入口：校验镜像、打包工具、设置新密码、创建临时磁盘、初始化并发布。 |
| [provision-dual-debian.py](provision-dual-debian.py) | 校验产物，调用共用维护逻辑依次初始化 host 和 guest。 |
| [disk-targets.py](disk-targets.py) | 检查正式目标，备份旧盘，发布新盘，替换异常时尝试恢复。 |
| [init-system.sh](init-system.sh) | 虚拟机内配置 fstab、主机名、解析、时区和语言。 |
| [provision-system.sh](provision-system.sh) | 虚拟机内校验工具包、配置基础系统、调用安装器并设置 root 密码。 |
