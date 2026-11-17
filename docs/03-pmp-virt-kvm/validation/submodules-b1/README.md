# 子模块集成后的 B1 历史验证

对应 2026-11-12 的团队子模块构建与 Buildroot 联合回归。
原始材料在本次整理前已从工作区删除；本目录当前仅有此说明。

| 原文件 | 用途 |
| --- | --- |
| `README.md` | 验证范围、已知问题与结果 |
| `console.log` | 当时的串口输出 |
| `manifest.json` | 当次产物清单 |
| `result.json` | 当时 HEAD、工作区状态及回归结果 |
| `SHA256SUMS` | 归档文件校验值 |

在项目根目录查询：

```sh
git show HEAD:docs/pmp-virt/validation/submodules-b1/README.md
```

这些历史结果不替代当前双 Debian 的运行验收。
