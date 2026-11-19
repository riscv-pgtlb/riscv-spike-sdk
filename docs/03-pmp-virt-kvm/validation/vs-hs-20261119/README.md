# VS–HS–VS 双环境验证记录

2026-11-19 在 kc-server-1 完成真实虚拟机回归：

| 环境 | 结果 | 耗时 | 原始目录 |
| --- | --- | --- | --- |
| Debian | PASS，17/17 | 108.45 秒 | build/virt-kvm/logs/suite-20261119-182231-465495/ |
| Buildroot | PASS，17/17 | 19.98 秒 | build/virt-kvm/logs/suite-20261119-182504-321467/ |

本目录保存两轮原样复制的 result.json、summary.txt，以及来源提交和完整 console.log 的 SHA256。完整串口日志、产物清单及其他证据仍在上述服务器目录，未将编译产物、磁盘或密码材料纳入仓库。

两轮均通过 HU–HS–HU、VS–HS–VS 同物理页检查、guest 基本检查/关机/返回及 host 复测。仅代表当前单 vCPU 实验配置，不扩大为多核或所有 VS/VU 场景验证。

摘要反映当时运行，记录内的工作区路径和后续代码提交号可以不同；配套组件版本以 runs.json 为准。SHA256SUMS 校验本目录保存的文件。
