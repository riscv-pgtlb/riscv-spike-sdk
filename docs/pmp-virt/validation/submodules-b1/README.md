# 子模块迁移后的联合回归

日期：2026-11-12。

团队 QEMU、Linux host、OpenSBI 子模块直接编译成功，产物及固件布局配对校验通过。
20 项静态检查和自动运行回归通过。

运行覆盖：host 启动保护结果检查、同页 U→HS→U、
普通 Buildroot guest 内存和时间推进检查、guest 正常关机、
返回 host 后重新执行同页保护测试。

HS 6/6 和 SBI guard 18/18 来自本次 host 启动日志。
Debian 联网、未封存对照、G-stage.Virt、VS/VU 配对及多核压力测试未包含在本次回归中。

首次自动回归因 guest 串口双回车导致解析误报；修正规则后重新运行通过。
原失败记录保留在 build/virt-kvm/logs/ 中。
源码仍在迁移分支工作区，result.json 中记录的是当时 HEAD 和工作区状态。
