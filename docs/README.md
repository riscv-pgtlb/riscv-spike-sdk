# 项目文档导航

按项目发展阶段阅读。当前双 Debian 使用第四阶段；其构建基础见第三阶段。

| 阶段 | 目标 | 状态与入口 |
| --- | --- | --- |
| [01：基础启动](01-boot-baseline/README.md) | OpenSBI → Linux → root shell | A1 历史记录 |
| [02：普通 KVM](02-ordinary-kvm/README.md) | Buildroot 外层运行 Buildroot/Debian 内层 | 历史流程，当前受保护内核下未重新验证 |
| [03：PMP.Virt + KVM](03-pmp-virt-kvm/README.md) | 受保护 host、普通 guest、保护回归 | 当前构建基础及 Buildroot 回归 |
| [04：双 Debian](04-dual-debian/README.md) | 两层 Debian、自动创建和工具更新 | 当前日常使用入口 |

每阶段 README 说明目标、文件用途及验证边界。历史结果只代表对应版本和运行，不代表当前磁盘已经重新通过测试。

想先了解保护机制与测试代码，阅读 [PMP.Virt 原理与测试调用链](03-pmp-virt-kvm/pmp-virt-explained.md)。
执行整合后的已有测试，阅读 [统一测试入口](03-pmp-virt-kvm/test-suite.md)。
整体了解本轮双 Debian 改动和实验结果，阅读 [双 Debian 实验报告](04-dual-debian/experiment-report.md)。
