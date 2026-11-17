# 正常启动

对应 make run-virt-dual-debian；启动沿用固定路径磁盘，也支持 Makefile 磁盘参数。

| 文件或目录 | 用途 |
| --- | --- |
| [run-dual-debian.sh](run-dual-debian.sh) | 服务器检查产物及两盘，启动受保护 host 内核和外层 Debian。 |
| [run-debian-guest.sh](run-debian-guest.sh) | 外层确认保护和 guest 磁盘未挂载，通过 lkvm/KVM 启动正常登录的内层。 |
