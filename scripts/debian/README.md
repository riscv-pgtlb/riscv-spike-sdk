# 双 Debian 功能脚本

服务器入口：make debian-prepare、make run-virt-dual-debian、make debian-update。

| 文件或目录 | 用途 |
| --- | --- |
| [prepare/](prepare) | 首次创建和显式备份重建两块固定路径磁盘。 |
| [install/](install) | 工具包生成，以及 Debian 内工具安装。 |
| [run/](run) | 服务器启动外层及外层启动内层。 |
| [update/](update) | 更新已有磁盘或 Debian 内的工具。 |
| [common/](common) | 准备、更新共用的 QEMU 维护启动和占用检查。 |

```
make debian-prepare
    - prepare-dual-debian.sh
        - pack-tools.sh
            - tool-manifest.py
        - provision-dual-debian.py
            - maintenance.py
                - provision-system.sh
                    - init-system.sh
                    - host: install-host.sh / guest: install-guest.sh
                        - install-tools.sh
                            - check-virt-tools.sh
        - disk-targets.py

make run-virt-dual-debian
    - run-dual-debian.sh
    - run-debian-guest.sh 

make debian-update
    - update-dual-debian.py
        - pack-tools.sh
        - maintenance.py
                - update-system.sh
                    - host: install-host.sh / guest: install-guest.sh
                        - install-tools.sh
                            - check-virt-tools.sh
```