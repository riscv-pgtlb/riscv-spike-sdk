# 普通 KVM 旧流程

保留供参考；不属于当前双 Debian 自动部署。对应旧 Makefile 入口仍保留。

| 文件或目录 | 用途 |
| --- | --- |
| [pack-kvm-rootfs.sh](pack-kvm-rootfs.sh) | 普通 KVM rootfs 打包，安装模块、lkvm 和旧启动脚本。 |
| [run-guest.sh](run-guest.sh) | 普通 KVM 外层中启动 Buildroot 内层。 |
| [run-debian.sh](run-debian.sh) | 普通 KVM 外层中配置网络并启动 Debian 内层。 |
