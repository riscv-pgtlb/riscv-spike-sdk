# 准备固定路径的双 Debian 磁盘

首次创建环境：

```sh
make debian-prepare
```

完成后固定使用：

- `images/debian/debian-host.raw`：外层系统盘。
- `images/debian/debian-guest.raw`：内层系统盘。

任一目标已存在时，默认立即停止，不生成新磁盘、不提示设置密码。
日常更新工具使用 `make debian-update`，不需要重新准备系统。

要重建系统，先正常关闭双 Debian，然后显式执行：

```sh
make debian-prepare DEBIAN_RECREATE=1
```

该命令
1. 校验基础镜像和构建产物
2. 交互设置新 root 密码，在 `prepared-*` 暂存目录内生成两块磁盘，
3. 并通过 QEMU 自动初始化两层。
    - 两层全部成功后，才将原有正式磁盘移入 `images/debian/backup-*/`，再把新磁盘移到固定路径。备份保留原账号、数据和日志，新系统使用本次初始化的配置和密码。
    - 初始化失败时原正式磁盘保持原样；替换阶段发生普通文件操作错误时，尝试恢复原两块磁盘，
    - 并报告恢复错误及备份位置。两次重命名不是断电安全的事务，异常断电后应检查固定路径和备份目录。
不要在准备期间通过其他方式启动这些磁盘。

`prepared-*` 在成功后仅保留本次日志、校验记录和传输材料，不再保存两块新磁盘。
传输材料包含密码哈希，不应上传或提交。失败时保留暂存文件以便诊断。
`backup-*` 不自动清理，可在确认新环境可用后手动删除。

准备、更新和 Makefile 的双 Debian 启动入口通过共同的锁避免互相冲突，
已有磁盘还会执行 QEMU 占用检查。

完成后直接执行：

```sh
make run-virt-dual-debian
```

外层登录后执行 `test-virt-debian-all /dev/vdb` 完成实际运行验收。
