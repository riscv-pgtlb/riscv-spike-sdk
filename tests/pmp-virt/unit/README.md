# 单元测试

从项目根目录执行 make virt-test-static。使用临时文件、模拟命令和串口进程，不能替代真实虚拟机回归。

| 文件或目录 | 用途 |
| --- | --- |
| [test_build.py](test_build.py) | 布局、源码版本锁、工具链选择、校验清单、重打包和回归日志解析。 |
| [test_debian_deploy.py](test_debian_deploy.py) | 维护启动、成功/失败判断、超时和 guest 安装器的正常及维护模式。 |
| [test_debian_targets.py](test_debian_targets.py) | 固定目标保护、备份、发布和替换失败恢复。 |
| [test_debian_server_update.py](test_debian_server_update.py) | 服务器两盘更新的前置检查、调用顺序和部分失败记录。 |
| [test_debian_update.py](test_debian_update.py) | Debian 内更新的包校验、环境和进程检查、安装失败处理。 |
| [test_directory_layout.py](test_directory_layout.py) | 实际打包并在隔离目录安装两种工具包，检查迁移后的路径及包内不包含单元测试。 |
| [test_pmpvirt_suite.py](test_pmpvirt_suite.py) | 统一入口的逐项解析、防回显误判、返回后新探针要求、密码脱敏、登录驱动和失败处理；新增 VS–HS–VS 缺阶段、错地址、错误顺序与编号检查。 |
| [test_tool_versions.py](test_tool_versions.py) | 两层安装后校验、确定性版本、文件缺失/修改/权限变化、旧版混用、元数据和安装源损坏。 |
