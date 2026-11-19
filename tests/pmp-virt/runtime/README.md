# 运行时检查

脚本由安装器或 rootfs 打包流程安装到虚拟机；这里不存放部署实现。

| 文件或目录 | 用途 |
| --- | --- |
| [check-virt-host.sh](check-virt-host.sh) | 检查外层封存、HS/SBI 探针、用户态/HS 同页权限和 /dev/kvm。 |
| [check-virt-guest.sh](check-virt-guest.sh) | 检查内层内核、内存和时间推进。 |
| [pv-user-test.c](pv-user-test.c) | 编译为 pv-user-test，执行 U 成功、HS 同页访问拒绝、U 再次成功的探针。 |

| [check-virt-vs-hs.sh](check-virt-vs-hs.sh) | Debian、Buildroot 与服务器共用的 VS–HS–VS 五阶段日志检查，要求地址及顺序一致。 |
