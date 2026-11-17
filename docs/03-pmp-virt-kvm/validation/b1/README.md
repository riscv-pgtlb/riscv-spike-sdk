# B1 历史验证

对应 2026-11-04 的受保护 host 与普通 KVM guest 联合实验。
原始材料在本次整理前已从工作区删除；本目录当前仅有此说明，没有可直接核验的原始日志。

历史文件用途：

| 原文件 | 用途 |
| --- | --- |
| `README.md` | 对应版本、运行范围和结果解释 |
| `b1-console.log` | 当时的串口输出 |
| `post-repack-manifest.json` | 持久修正后重打包的产物清单，不等同于运行前清单 |
| `SHA256SUMS` | 归档日志与清单的校验值 |

在项目根目录查询历史说明：

```sh
git show HEAD:docs/pmp-virt/validation/b1/README.md
```

其他原始文件也可按其历史路径查询；不要用文字摘要生成“原始日志”。
