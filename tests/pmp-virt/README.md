# PMP.Virt 测试

Virt 总汇总入口：`make virt-test`，内部同时执行 PMP.Virt 与 Stage2Virt；默认使用双 Debian。
逐项显示结果并保存证据，使用方法见 [统一测试说明](../../docs/03-pmp-virt-kvm/test-suite.md)。

make virt-test-static 执行 unit/；
make virt-test 执行 Buildroot 完整回归
Debian 外层执行 test-virt-debian-all /dev/vdb

| 文件或目录 | 用途 |
| --- | --- |
| [unit/](unit) | 不启动真实 Debian 的自动测试。 |
| [runtime/](runtime) | 安装进虚拟机并执行的保护和 guest 检查，以及同页权限探针。 |
| [regression/](regression) | 按系统类型串联 host → guest → host 的完整运行回归。 |
