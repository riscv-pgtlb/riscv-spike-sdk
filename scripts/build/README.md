# 构建与产物校验

服务器运行；对应 make virt-check、virt-prepare、virt-build、virt-verify 和 run-virt-host。

| 文件或目录 | 用途 |
| --- | --- |
| [virt-kvm.py](virt-kvm.py) | 准备锁定源码，编译 host/guest 内核、固件、QEMU 和工具，打包 Buildroot rootfs，校验产物并启动 host。 |
