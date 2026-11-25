
1. **Host Linux**：增加页表位定义
   repo/linux/arch/riscv/include/asm/
   1. **Host Linux/KVM**：生成 G-stage PTE、刷新 TLB、处理预期故障
   repo/linux/arch/riscv/kvm/
   2. **Host Linux**：增加实验接口或公共数据结构
   repo/linux/include/uapi/linux/
   repo/linux/include/linux/
2. **Guest Linux**：实现 VU–VS–VU 同页探针
   repo/linux-guest/arch/riscv/kernel/
   repo/linux-guest/arch/riscv/include/asm/
   1. Guest Linux：增加测试配置和编译入口
   repo/linux-guest/arch/riscv/
3. **kvmtool**：实现 Stage2Virt 协调和 KVM ioctl 调用
   repo/kvmtool/riscv/
   repo/kvmtool/riscv/include/kvm/
   1. kvmtool：加入对象编译和本地测试
   repo/kvmtool/
   repo/kvmtool/tests/
   repo/kvmtool/Documentation/
4. SDK版本锁和内核配置
   /conf/virt/
   1.  SDK构建和 QEMU启动参数
    /scripts/build/
   2.  Buildroot双层启动入口
    /home/wsh/riscv-spike-sdk/scripts/buildroot/
   3.  双 Debian启动入口
    /home/wsh/riscv-spike-sdk/scripts/debian/run/
   4.  双 Debian工具打包、安装和更新
    /home/wsh/riscv-spike-sdk/scripts/debian/install/
    /home/wsh/riscv-spike-sdk/scripts/debian/common/
   5.  Guest/Host运行时测试程序和证据检查器
    /home/wsh/riscv-spike-sdk/tests/pmp-virt/runtime/
   6.  双 Debian完整回归
    /home/wsh/riscv-spike-sdk/tests/pmp-virt/regression/debian/
   7.  Buildroot完整回归
    /home/wsh/riscv-spike-sdk/tests/pmp-virt/regression/buildroot/
   8.  统一测试编排与结果汇总
    /home/wsh/riscv-spike-sdk/tests/pmp-virt/regression/
   9.  SDK静态单元测试
    /home/wsh/riscv-spike-sdk/tests/pmp-virt/unit/
   10. 实现与验证文档
    /home/wsh/riscv-spike-sdk/docs/03-pmp-virt-kvm/
    /home/wsh/riscv-spike-sdk/docs/04-dual-debian/