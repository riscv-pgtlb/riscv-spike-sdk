# PMP.Virt 实现与文件改动报告

编写日期：2026-11-18。对象为当前工作区实现，包含最近的文件和命令重命名。

## 报告范围与依据

本报告说明 PMP.Virt 功能在各仓库中的职责，以及关键新增、修改和集成文件的用途；不是只列本次未提交的重命名差异。

核心源码在 `repo/qemu`、`repo/opensbi`、`repo/linux`；SDK 主仓库负责构建配对、系统部署和验证。文件表中的路径相对于各自仓库根目录。

| 分报告 | 主要内容 |
| --- | --- |
| [QEMU](qemu.md) | 实验配置位、CPU 开关和物理权限判断 |
| [OpenSBI](opensbi.md) | 固件区域策略、封存 SBI 接口和服务白名单 |
| [Linux](linux.md) | 封存请求、HS 访问探针、异常恢复和用户测试接口 |
| [SDK 与其余子模块](sdk.md) | 构建、Buildroot/Debian 部署、测试、重命名及依赖职责 |

| 模块 | 一句话职责 |
|---|---|
| QEMU | 让实验机器具备这条权限规则 |
| OpenSBI | 决定并维护内存保护规则 |
| Linux | 在合适时机请求保护，并提供测试接口 |
| SDK | 构建配套组件、部署系统、组织验证 |

### 新增和修改的判定

Linux 使用锁定的普通 guest 提交与 host 提交直接比较，可确认新增/修改状态。QEMU、OpenSBI 本地为浅历史，无法把当前提交直接当成上游差异：`git show` 会把浅边界提交的整个源码树展示为新增。其表格按当前源码与组件职责识别实验新增文件和现有文件改造，不声称已完成相对上游基线的完整逐文件审计。

SDK 表格按功能引入和本次重命名分类，不把已存在功能都说成本轮新增；也不包含用户先前删除的历史验证材料。

## 版本基准

下表保留初稿的旧基线，当前集成提交以 [sources.json](../../../conf/virt/sources.json) 为准；新的 host/guest/kvmtool 版本及第 11 项见 [SDK 集成记录](../vs-hs-sdk-integration.md)：

| 组件 | 锁定提交 |
| --- | --- |
| Linux host | `ab598939034057e7fdc2a4beb483a10ef4c67077` |
| Linux guest | `449d48b1b99fdaa076166e200132705ac2bee711` |
| OpenSBI | `0e1a39f96b50c09978aa190a830b713a51c014c2` |
| QEMU | `0ec20439ca845573db2a52e85aa34c0dca9c1731` |
| kvmtool | `eb915c763e4b95dd4a9d32763fd449459742e053` |
| dtc | `f99e3af0ecb67a9085478a9b8ddbcc25aa64931d` |

## 联合工作流程

```text
SDK 构建 host Image + System.map
    → 提取 text、rodata、RAM 布局及 Image 摘要
    → 生成布局头文件并编入 OpenSBI
    → QEMU 开启 x-pmp-virt，启动固件与 host
    → Linux 在 mark_rodata_ro() 请求固件封存
    → 固件写入并核验 PMP 规则
    → QEMU 根据有效执行身份执行权限判定
    → host 用户探针 → KVM guest → 返回 host 再测
```

QEMU 提供实验硬件语义；OpenSBI 管理规则；Linux 请求规则生效并提供测试探针；SDK 负责把配套产物组织起来。Debian 和 Buildroot 是运行这些组件的用户空间环境。

## 当前验证结论与边界

最近命名整理后已运行 84 个 SDK 单元测试，全部通过；相关 Shell 脚本语法检查通过。单元测试使用隔离目录、模拟命令或串口进程，不能等同于真实虚拟机保护验证。本次报告编写没有重新构建内核/固件，也没有重新运行双层虚拟机回归。

当前实验面向单 hart、2 GiB host RAM、H 开启、Smepmp 关闭和 TCG 模拟。启动探针包括 HS 6 项与 SBI guard 前后共 18 项；guest 返回后重新执行的是同页 U → HS → U 探针，不是所有启动测试。

不据此宣称真实芯片支持、完整 G-stage.Virt 实现、VS/VU 配对验证、多核安全或完整 SBI 服务防绕过审计。历史证据缺失情况见 [验证材料说明](../validation/README.md)。
