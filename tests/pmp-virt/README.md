# 回归测试入口

在 Ubuntu 服务器的 SDK 根目录运行：

```bash
make virt-test-static   # 不启动 QEMU：脚本逻辑、布局、校验与版本检查
make virt-test          # 先完成 virt-build：host -> guest -> host 自动运行回归
```

`check-host.sh` 检查启动日志和设备，并运行 `user-exec.c` 编译出的同页探针。
`check-guest.sh` 检查普通 guest 内核、内存与时间推进。
`guest-autorun.sh` 只在专用回归启动参数下执行 guest 检查并关机。
`run-host-suite.sh` 在外层 host 执行全部运行阶段。
`run-regression.py` 在 Ubuntu 服务器驱动 QEMU 控制台、验证结果顺序并归档。

完整步骤、Debian 和验证边界见 [指南](../../docs/pmp-virt/README.md)。
内核中依赖异常处理的 HS 探针仍在 Linux 子模块 `arch/riscv/kernel/pv_access.c`，
测试目录集中用户程序、驱动入口和结果检查，不重复复制内核内部代码。
未封存对照程序和早期证据保留在历史 `b47454e`，尚未接入本次自动回归；不得宣称已覆盖。
