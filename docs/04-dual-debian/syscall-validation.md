# 双 Debian syscall 测试迁移验证（2026-11-19）

迁移基线：`dual-debian-pmp-virt` 的 `f87a4a3`。
实现提交：`f9768407f89e6e3b987866b6c58cfb06e668ad3f`。
本地验证分支：`dual-debian-syscall-tests`，目录 `/home/czy/work/riscv-spike-sdk-dual-syscall`。
本轮未推送 SDK 或 Linux 提交；发布时需要先保证固定 Linux 提交可从对应远端获取。

## 实际执行结果

| 检查 | 结果 | 证据目录（相对 build/virt-kvm/logs） |
| --- | --- | --- |
| 全部逻辑、部署和结果判定测试 | 86 项通过 | 两个 suite 目录中的 static.log |
| 从固定源码构建及产物/host 固件布局校验 | PASS | build/port-validation/build-48.log（相对仓库根目录）及 suite 的 verify.log |
| Buildroot 完整回归 | 16/16 汇总点 PASS | suite-20261119-183240-061202 |
| 正常 systemd 双 Debian 完整回归 | 16/16 汇总点 PASS | suite-20261119-183319-614124 |
| Debian 13 维护 shell 快照冒烟测试 | PASS，磁盘前后 SHA256 一致 | debian-smoke-20261119-183546 |

每次完整回归都在 guest 运行前后分别取得：12/12 旧接口拒绝结果、
2/2 新接口拒绝结果、三轮四项固定目标操作的 12/12 结果。
四项操作为普通数据页同值写入对照（cause=0）、HS 执行普通数据页（cause=1）、
内核 text 与 rodata 别名同值写入拒绝（cause=7）。同时检查目标字节保持不变。
结果判定拒绝 cause=12/15，避免把页表拒绝当作 PMP 的保护结果。

双 Debian 测试从已校验的 Debian 13 基础 qcow2 创建两块独立 raw 磁盘，使用临时生成的验证账号密码。
外层正常登录，内层正常 systemd 启动、版本/内核/内存/时间检查并关机，外层复测保护后正常关机。
快照检查随后在独立 guest 测试盘上运行，完整磁盘 SHA256 前后一致；摘要保存在
`build/port-validation/snapshot-disk-sha256.txt`。快照检查不是正常登录测试。
临时明文密码、服务器端初始化密码哈希和传输 tar 已在验证后删除，均未提交。
原有 v2 工作区仍为干净的 `39a0d42`，原有 Debian 磁盘未用于本轮写入。

## 已适配的差异

- 将 v2 的测试文件迁移到新的 runtime/regression 目录，并接入完整构建、静态 ELF 检查与产物摘要。
- 更新 Linux gitlink 和源码锁到 `9870eb7fbafbba214684de20425a9635422a47c7`，提供测试接口及临时执行别名清理。
- 为 Buildroot host 和 Debian host 工具包安装两个 syscall 程序；Debian 的文件清单及配对版本涵盖新增程序。
- 统一入口与 Buildroot 入口要求两个 host 阶段各有完整、有序且不重复的 syscall 结果。
- 迁移 Debian 快照冒烟测试，并补充升级说明；已有磁盘应完整构建后执行 debian-update，无需重建磁盘。

本次测试覆盖受控 syscall 期间的上述 HS 行为；不表示完整 VS/VU、G-stage.Virt、Virt 开关对照、多核或联网/APT 已验证。
