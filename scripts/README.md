# 功能脚本

优先从项目根目录使用 Makefile 入口。部署脚本不放在 tests 中；Debian 内安装的命令名保持不变。

| 文件或目录 | 用途 |
| --- | --- |
| [build/](build) | PMP.Virt 构建、产物校验和原有 host 启动。 |
| [buildroot/](buildroot) | 当前 PMP.Virt 的 Buildroot 外层内启动命令。 |
| [debian/](debian) | 双 Debian 的准备、安装、启动、更新与共用维护逻辑。 |
| [setup/](setup) | 源码子模块初始化及下载辅助。 |
| [legacy/](legacy) | 保留的普通 KVM 旧流程，当前受保护内核下未重新验证。 |
