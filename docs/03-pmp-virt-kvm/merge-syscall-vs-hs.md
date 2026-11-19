# 合并 syscall 与 VS–HS–VS 实验

本地 SDK 起点：3d236b79；远程分支起点：5a5745be。

## Linux 子模块

合并提交：ea10ef418cd7ca6359d2931d77ebca7269969091。
父提交分别为 f71c60d7b3e8ca338ac99463aaa70df744b37063（同页接口）和 9870eb7fbafbba214684de20425a9635422a47c7（syscall 保护接口）。

arch/riscv/kernel/pv_access.c 保留旧 HU ioctl 0x56、guest 会话 ioctl 0x57 和 syscall 固定目标 ioctl 0x58。三种入口共用原探针互斥锁；guest 页固定/关闭清理与 syscall 临时映射及结果返回分别保留。probe 返回结构体供 syscall 使用，其他调用者可忽略返回结构，不改变原异常码核验。

## SDK 冲突处理

| 文件 | 处理 |
| --- | --- |
| conf/pmp-virt/sources.json 与 repo/linux gitlink | 同步到上述合并提交；guest 和 kvmtool 版本不回退。 |
| scripts/build/virt-kvm.py | 保留 guest worktree、探针开关、重命名路径和共用日志检查器；增加两份 syscall 工具的输入校验、编译、产物校验与打包。 |
| tests/pmp-virt/regression/run-suite.py | 保留 17 项及新输出；host 前后检查要求同页和 syscall 完整证据，第 11 项仍单独核验 VS–HS–VS。 |
| tests/pmp-virt/unit/test_build.py | 两套构建/日志样本合并，不删除旧测试。 |
| tests/pmp-virt/unit/test_pmpvirt_suite.py | 保留串口、输出和 VS 测试，合入 syscall 缺失/重复/错误异常码反例。 |
| tests/pmp-virt/regression/buildroot/run-regression.py | 保留两套检查；修正自动合并中 evidence 模块名被字符串变量遮蔽的问题。 |

远程已自动合入的 syscall 工具、Debian 打包、host 检查及 smoke 入口同样保留。旧文档删除和工具链子模块内部改动未纳入合并提交。

## 验证边界

合并后的 104 个 SDK 单元测试通过；Linux pv_access.o 交叉编译通过。两份 syscall 用户工具也执行独立交叉编译检查。尚未重新构建全部产物或运行合并版本的 Debian/Buildroot 回归；此前 17/17 记录属于合并前的版本，不能当作本合并版本已通过的证明。

应先推送 Linux 合并提交，再推送 SDK 合并提交。之后重新构建 host 与配套固件、打包并更新工具，运行两种回归以确认联合版本。不得为推送而强制覆盖远程已有历史。
