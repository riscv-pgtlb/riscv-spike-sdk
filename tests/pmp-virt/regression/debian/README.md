# 双 Debian 回归

外层执行 test-virt-debian-all /dev/vdb；测试脚本及服务由安装器安装。

服务器可用 `make pmpvirt-test` 自动登录并驱动本套件，入口是 [run-suite.py](../run-suite.py)。

| 文件或目录 | 用途 |
| --- | --- |
| [test-virt-debian-all.sh](test-virt-debian-all.sh) | 外层检查 → 内层测试和关机 → 返回外层复测，保存内层串口日志。 |
| [virt-guest-test.service](virt-guest-test.service) | 内层 systemd 服务，仅在 virt_regression=1 时检查并关机。 |
