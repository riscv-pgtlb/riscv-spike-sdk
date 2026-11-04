# PMP.Virt 与 KVM 联合构建：B1

本入口在第三分支中构建带 A5 保护的 host 和普通 KVM guest。2026-11-04 的服务器控制台输出确认：联合构建、host 保护回归、普通 guest 启动及关机、返回 host 后同页保护复测通过。具体证据和验证边界见 [validation-b1.md](validation-b1.md)。它不实现 G-stage.Virt，也不能替代 VS/VU 真值表及缓存回归。

原 A5 交付文件及 KVM 构建入口保持原样。本入口不调用旧 `setup-build.sh`，不依赖已移除的 `baseline-a1/linux.config`，不修改旧实验目录或原组件源码。生成物全部在当前 checkout 的 `build/virt-kvm/`，不提交 Git。

## 布局和版本

- Linux host/guest 均固定于 `449d48b1b99fdaa076166e200132705ac2bee711`。host 应用完整 `linux-protected.patch`；guest 保持上游源码，两者独立源码与输出目录。
- host 使用 A5 已保存配置，经 `olddefconfig` 后强制检查 KVM=y、MODULES=n、静态代码限制与必要设备配置。guest 关闭 KVM，不调用 host 的封存 SBI。
- QEMU 使用本次从上游 `v10.1.0` 标签获取并核对的提交 `f8b2f64e2336a28bf0d50b6ef8a7d8c013e9bcf3`，应用 A5 补丁；W 文档中另记的 `562020f` 不作为该标签的校验值。OpenSBI 固定于 `a32a91069119e7a5aa31e6bc51d5e00860be3d80`，应用 A5 完整 guard 补丁。
- kvmtool 固定于 `eb915c763e4b95dd4a9d32763fd449459742e053`；dtc 固定于 `f99e3af0ecb67a9085478a9b8ddbcc25aa64931d`。均使用原版代码。
- 固定一个 hart、host RAM 2 GiB、guest RAM 256 MiB；关闭 Smepmp，启用 H 与 `x-pmp-virt`。第一轮不提供网络或可写磁盘。
- 在 OpenSBI 的私有源码副本中，将原 256 MiB RAM 的两处 NAPOT 编码和 preflight 上界统一替换为固定 2 GiB 配置。原 SBI 白名单、调用者校验、代码 RX/Virt0、rodata R/Virt0 和 MMIO RW/Virt0 保留。初始域/PMP 布局不匹配时固件仍拒绝封存，不放松 preflight。
- 最终 host Image 与 System.map 生成新的编译期固件布局；每次构建固件重新生成。启动前检查镜像、固件、QEMU、配置、rootfs、布局头等校验值，拒绝过期组合。Image hash 用于构建与启动配对，不表示固件在运行时执行了镜像密码学认证。

## 服务器终端：准备与构建

只在第三分支的独立目录执行：

```bash
cd /home/czy/work/riscv-spike-sdk-virt-kvm-integration
python3 integration/virt-kvm.py check
python3 -u integration/virt-kvm.py prepare
mkdir -p build/virt-kvm/logs
set -o pipefail
python3 -u integration/virt-kvm.py build -j 4 2>&1 | tee build/virt-kvm/logs/build.log
python3 integration/virt-kvm.py run --dry-run
```

默认从 `/home/czy/work/riscv-spike-sdk` 和 A5 组件目录只读复用 Git 对象，私有克隆以固定提交 detached checkout，绝不沿用这些目录中的未提交修改。本地没有所需提交时，prepare 会在新的私有目录中联网获取固定上游版本；不会递归下载整个工具链。

可通过环境变量指定 `SOURCE_SDK`、`CROSS_COMPILE`、`BASE_ROOTFS`、`LINUX_REPO`、`QEMU_REPO`、`OPENSBI_REPO`、`DTC_REPO`、`KVMTOOL_REPO`。显式源码路径必须含对应固定提交。交叉编译器依次探测 SDK、已有 Buildroot、PATH 中的 `riscv64-linux-gnu-` 工具链；无法运行的候选会显示原因并跳过。显式设置 `CROSS_COMPILE` 时严格使用该前缀，失败则停止，不自动切换。基础 rootfs 默认优先 SDK `images/base/rootfs.cpio.gz`，其次 Buildroot 产物及原 A5 `rootfs-devtmpfs.cpio.gz`。

环境检查会实际运行 GCC 和 binutils、核对 RISC-V Linux 目标，并在本 checkout 的专用临时目录链接一个静态 RISC-V 测试程序、检查其 ELF。该测试程序不会在服务器执行，测试结束清理临时文件。这用于提前发现失效的 Buildroot wrapper、缺少的 `gcc.br_real`、错误架构、缺失的 binutils 或静态 libc；不重建或修改已有工具链。

libfdt 构建显式设置固定版本 Makefile 支持的 `NO_VALGRIND=1 NO_YAML=1`，避免宿主 pkg-config 把 `/usr/include/valgrind` 等服务器依赖带入 RISC-V 编译。使用 `make -B ... libfdt` 重新生成先前失败产生的依赖文件及库文件；该操作只涉及本 checkout 的私有 dtc 副本。保留 Buildroot wrapper 的不安全路径拒绝检查，不通过关闭该检查来继续。

构建使用已有基础 rootfs；这不等同于从零重建 Buildroot 和工具链。host/guest 额外覆盖已保存的 devtmpfs inittab，host 不打包内核模块。未完成的准备目录仅在目录内只有私有 `.git`、尚无 HEAD 且 FETCH_HEAD 精确匹配固定提交时允许继续 checkout。其他中断状态保留现场并停止，不自动删除或重置。构建输出使用本 checkout 的专用目录，不支持指向原实验目录的输出覆盖。若使用本地 Git 对象共享克隆，在完成构建前避免清理源仓库的 Git 对象。

准备、构建报错时保存完整日志，不通过关闭 guard、去掉封存、改回通用 RWX 或忽略校验值来继续。

## 服务器终端：启动外层 QEMU

```bash
python3 integration/virt-kvm.py run
```

外层启动后检查 `PMP.Virt SEALED`、HS `PASS 6/6`、封存前后 SBI guard 各 9 条，以及 `/dev/kvm`。

`PMP.Virt SEALED` 由 OpenSBI 写入串口，应在服务器保存的完整 QEMU 控制台记录中核对；Linux 的 dmesg 检查使用 `PMP.Virt seal acknowledged`、HS 6/6 和 SBI guard 18/18，不要求固件串口行进入内核日志。

仅更新启动检查脚本时可执行 `python3 integration/virt-kvm.py repack`。该入口先核对旧清单中的已有产物及 host/固件配对，只允许将要重新打包的三个脚本源文件更新；同时核对原始基础 rootfs 的校验值。之后重新打包 rootfs、更新清单并执行完整校验。原内核、固件、QEMU 二进制保持不变，已有编译产物不匹配时停止。

## 外层 QEMU 的 host 终端

```sh
uname -r
check-virt-host
run-virt-guest
```

host 内核版本含 `-pmpvirt-kvm-host` 标记，允许 Git 版本信息附带的 `+`、`-dirty` 或其他以短横线连接的版本后缀。`check-virt-host` 检查启动日志、guard、设备，并重新运行同页 U→HS→U 实验。这里的版本判断只用于区分操作终端，不作为安全认证。`run-virt-guest` 先执行该检查，再调用 lkvm。这里不需要 modprobe。

## 内层 guest 终端

```sh
uname -r
cat /proc/meminfo | head
echo 'GUEST USERSPACE PASS'
poweroff
```

guest 启动应出现 `VIRT-KVM GUEST BOOTED`，内核后缀应为 `-virt-kvm-guest`。记录到达用户 shell、内存、定时器和关机情况。guest 关闭回到 host 后，再执行 `check-virt-host`，确认 guest 运行前后保护未退化。随后在 host 按 Ctrl+A，再按 X 退出外层 QEMU。

本轮验收只覆盖：A5 host 回归、普通 guest 启动、guest 关闭后 host 回归。这为 M–HS–VS 的联合验证提供基础，但尚未包含同一客户机物理页的 VS 成功/HS 拒绝配对实验。HS–VS–VU 的保护还需要独立实现与验证 G-stage.Virt，不能由本轮 guest 启动成功推导。

新增入口及实际运行记录应作为第三分支上的独立适配提交。不要提交 Image、fw_jump.bin、rootfs、构建目录；不要自动推送或更新原分支。启动期间临时修正过内存 rootfs 的版本检查脚本，随后已将相同修正写入持久源码并 repack、verify 通过；重打包后的 rootfs 尚未再次启动验证。
