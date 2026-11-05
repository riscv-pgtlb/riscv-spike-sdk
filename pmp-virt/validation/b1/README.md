# B1 联合运行验证记录

日期：2026-11-04。依据：操作者粘贴的服务器及 QEMU 控制台输出。

## 分支与范围

工作树为 `/home/czy/work/riscv-spike-sdk-virt-kvm-integration`，分支为 `pmp-virt-kvm-integration`，合并提交 `7dbfbae`，父提交为 A5 `b47454e` 和 KVM `746d4f0`。运行后的分支检查仍显示 `team/pmp-virt-a5=b47454e`、`team/kvm=746d4f0`、`team/master=635a4af`。原 A5 目录与 `team/pmp-virt-a5` 的 diff 为空。

本轮为一个 hart、QEMU TCG、H 扩展开启、host RAM 2 GiB、guest RAM 256 MiB 的固定布局实验。host 应用 A5 保护；guest 为普通 Linux，不实现 G-stage.Virt。

## 构建和封存

联合构建、产物 SHA-256 和 host Image/固件布局配对检查通过。

完整控制台位于服务器 `build/virt-kvm/logs/console-host-20261104-154546.log`。保存的关键固件输出为：

```text
PMP.Virt SEALED: text=[0x80202000,0x811a1000) rodata=[0x81600000,0x81e00000) RAM=RWVirt image=2a2fdeac70194dca05a6b8c8066ff98b8a4cf935709ef82c6928a35eaf7788fa
```

该 image 值用于构建配对记录，不表示固件对运行时内存执行密码学认证。

## Host 与 guest

host 为 `6.17.2-pmpvirt-kvm-host-dirty`。KVM 报告 H 扩展可用，使用 Sv57x4 G-stage 页表和 14 位 VMID。启动时确认封存、HS 访问测试 PASS 6/6，封存前后 SBI guard 各 9 项通过；同页实验观察到 U 执行返回 42、HS 执行 access fault cause=1、U 再执行返回 42。

guest 到达用户 shell，输出 `VIRT-KVM GUEST BOOTED`，并得到：

```text
# uname -r
6.17.2-virt-kvm-guest
MemTotal:         212468 kB
# cat /proc/uptime
74.39 68.04
# sleep 2
# cat /proc/uptime
76.49 70.03
GUEST USERSPACE PASS
```

这证明用户 shell 可用且 sleep 和运行时间推进正常，未做定时器或中断压力测试。MemTotal 是 guest 报告的可用物理内存总量，与配置的 256 MiB 存在内核保留等开销。

guest 关机日志包含 `reboot: Power down`，操作者随后返回 host shell，核对 host 版本并再次执行同页实验：

```text
PASS U execute before HS probe: value=42 VA=0x7fffa1905000
PASS HS denied same physical page: PA=0x86cb2000 cause=1
PASS U execute after HS probe: value=42
PMP.Virt USER SUMMARY: PASS U-success / HS-access-fault / U-success
VIRT-KVM HOST CHECK PASS: seal, HS 6/6, SBI guard 18/18, U/HS/U, /dev/kvm
```

返回 host 后实际重新执行的是同页 U→HS→U 实验；HS 6/6、guard 18/18 和封存确认来自同一次 host 启动日志，未在 guest 退出时重新执行全部启动探针。

## 持久修正与证据保存

初版辅助脚本误拒绝带 `-dirty` 的 host 内核版本。操作者在运行中临时修正内存 rootfs 的版本匹配后完成上述实验，随后将相同修正写入 `integration/check-host.sh`，执行 repack 和 verify 均通过，已有内核、固件和 QEMU 二进制保留。

重打包后的 rootfs 尚未再次启动。归档的 `validation/post-repack-manifest.json` 记录的是持久修正后产物，不能作为本次控制台运行时原始 rootfs 的精确校验清单。`validation/b1-console.log` 保存本次完整控制台；`validation/SHA256SUMS` 校验该日志和重打包后清单。归档文件须由服务器现有文件复制生成，不从文字摘要构造完整日志。

本轮结论限于 A5 host 与普通 KVM guest 的联合运行。未验证 VS/VU 保护真值表、同一客户机物理页的 VS 成功/HS 拒绝配对、G-stage.Virt、SMP、压力测试或完整服务防绕过审计。
