# Buildroot 回归

服务器执行 make virt-test。内核内部 HS 探针仍位于 Linux 子模块，不在这里复制。

| 文件或目录 | 用途 |
| --- | --- |
| [run-regression.py](run-regression.py) | 服务器驱动 QEMU 控制台，检查结果顺序并归档证据。 |
| [test-virt-all.sh](test-virt-all.sh) | 外层先检查保护，启动内层自动测试，返回后再次检查保护。 |
| [virt-guest-autorun.sh](virt-guest-autorun.sh) | 内层仅在 virt_regression=1 时执行检查并关机。 |
