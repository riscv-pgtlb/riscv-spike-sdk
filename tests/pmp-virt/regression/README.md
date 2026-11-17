# 完整运行回归

需要实际构建产物和虚拟机环境；与 unit/ 的逻辑测试分开。

| 文件或目录 | 用途 |
| --- | --- |
| [run-suite.py](run-suite.py) | 统一静态、产物和真实运行测试；自动驱动 Debian 登录或复用 Buildroot 回归，输出逐项结果并归档。 |
| [buildroot/](buildroot) | Buildroot 外层及内层的自动运行回归。 |
| [debian/](debian) | 双 Debian 的完整回归脚本和内层自动测试服务。 |
