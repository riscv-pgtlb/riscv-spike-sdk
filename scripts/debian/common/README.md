# 共用维护逻辑

共用维护模块由准备和更新程序导入；工具检查脚本同时用于安装、更新和测试。

| 文件或目录 | 用途 |
| --- | --- |
| [maintenance.py](maintenance.py) | 生成维护 QEMU 参数、通过串口执行脚本、检查退出码和成功标记、处理超时、校验传输盘与系统盘独立、检查磁盘占用。 |
| [check-virt-tools.sh](check-virt-tools.sh) | 检查工具角色、版本、文件内容和权限；安装为 check-virt-tools 命令。 |
