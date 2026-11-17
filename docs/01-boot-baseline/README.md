# 第一阶段：基础启动

目标是验证 OpenSBI → Linux → initramfs → root shell，不包含 KVM 内层和 PMP.Virt 保护验收。

| 文件 | 用途 |
| --- | --- |
| [boot-baseline.md](boot-baseline.md) | A1 交付时的启动结果、组件版本和范围 |

原 `docs/baseline-a1-inputs.sha256` 在本次整理前已从工作区删除，未恢复，不将其列为当前存在的文件。
需要查询原记录时，在项目根目录执行：

```sh
git show HEAD:docs/baseline-a1-inputs.sha256
```

原路径记录的是当时输入，不适用于当前构建产物。后续普通 KVM 见 [第二阶段](../02-ordinary-kvm/README.md)。
