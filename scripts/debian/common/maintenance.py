"""Shared maintenance boots and disk checks for Debian preparation and updates."""
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]

# 启动一套临时维护虚拟机，在其中初始化或更新系统盘
def provision(deploy, role, timeout=900, action="provision"):
    if role not in ("host", "guest"):
        raise RuntimeError("Role must be host or guest")
    if action not in ("provision", "update"):
        raise RuntimeError("Action must be provision or update")
    label = action.upper()
    log_path = deploy / f"{action}-{role}.log"
    # 构造 QEMU 启动命令
    # 一次只启动一块系统盘；另一块设备是只读传输盘 setup.tar
    command = [
        str(ROOT / "build/virt-kvm/out/qemu/qemu-system-riscv64"),
        "-machine", "virt", "-accel", "tcg",
        "-cpu", "rv64,h=true,smepmp=off,x-pmp-virt=on,x-stage2-virt=on",
        "-m", "2048M", "-smp", "1", "-nographic",
        "-bios", str(ROOT / "build/virt-kvm/out/opensbi/platform/generic/firmware/fw_jump.bin"),
        "-kernel", str(ROOT / "build/virt-kvm/out/linux-host/arch/riscv/boot/Image"),
        "-drive", f"file={str(deploy / f'debian-{role}.raw').replace(',', ',,')},format=raw,if=none,id=rootdisk",
        "-device", "virtio-blk-device,drive=rootdisk",
        "-drive", f"file={str(deploy / 'setup.tar').replace(',', ',,')},format=raw,readonly=on,if=none,id=transfer",
        "-device", "virtio-blk-device,drive=transfer",
        "-append",
        "console=ttyS0 earlycon=sbi root=/dev/vda1 rw rootwait maxcpus=1 init=/bin/sh debian_provision=1",
    ]

    # 准备发送给虚拟机的命令
    # - 从 /dev/vdb 解压 setup.tar
    # - 执行对应的配置脚本 update-system.sh 或 provision-system.sh
    setup = (
        "mount -t proc proc /proc && "
        "mount -t sysfs sysfs /sys && "
        "mkdir -p /run/debian-init && "     
        "tar -xf /dev/vdb -C /run/debian-init && "      
        f"sh /run/debian-init/{action}-system.sh {role}; "
        f"rc=$?; printf '\\nDEBIAN {label} EXIT {role}: %s\\n' \"$rc\"; "
        "sync; poweroff -f\n"
    )

    print(f"{action}: {role}; log: {log_path}", flush=True)
    # 启动 QEMU
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    sent = False
    tail = b""
    deadline = time.monotonic() + timeout

    try:
        with log_path.open("wb") as log:  # 持续保存日志，等待 shell 出现
            while True:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"{role}: initialization timed out")
                events = selector.select(timeout=1)
                if not events:
                    if process.poll() is not None:
                        break
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                log.write(chunk)
                log.flush()
                tail = (tail + chunk)[-8192:]
                # 发现 root shell 后发送命令 setup
                if not sent and re.search(rb"(?:^|[\r\n])# $", tail):
                    process.stdin.write(setup.encode())
                    process.stdin.flush()
                    sent = True
            result = process.wait(timeout=30)
    finally:        # 无论成功失败，都清理进程
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdin.close()
        process.stdout.close()

    # 检查操作是否真正成功
    lines = log_path.read_bytes().replace(b"\r", b"").splitlines()
    marker = f"DEBIAN {label} PASS: {role}".encode()
    exit_marker = f"DEBIAN {label} EXIT {role}: 0".encode()
    if result != 0 or marker not in lines or exit_marker not in lines:
        raise RuntimeError(f"{role}: initialization failed; inspect {log_path}")
    print(f"DEBIAN {label} VERIFIED: {role}", flush=True)

# 检查部署文件是否齐全，以及文件是否彼此独立
def validate_deploy(deploy):
    for name in ("debian-host.raw", "debian-guest.raw", "setup.tar"):
        if not (deploy / name).is_file():
            raise RuntimeError(f"Missing file: {deploy / name}")
    if (deploy / "debian-host.raw").samefile(deploy / "debian-guest.raw"):
        raise RuntimeError("Host and guest disks must be separate files")
    transfer = deploy / "setup.tar"
    if any(transfer.samefile(deploy / f"debian-{role}.raw") for role in ("host", "guest")):
        raise RuntimeError("Transfer archive must be separate from system disks")

# 尝试获取磁盘写入权限，检查是否存在使用冲突
def check_stopped(host, guest=None):
    # Open BOTH disks writable without running a CPU. QEMU rejects disks already
    # held by another writer, including an active dual-Debian VM.
    command = [str(ROOT / "build/virt-kvm/out/qemu/qemu-system-riscv64"),
               "-machine", "virt", "-bios", "none", "-m", "128M",
               "-display", "none", "-nodefaults", "-S", "-qmp", "stdio"]
    for index, disk in enumerate(disk for disk in (host, guest) if disk is not None):
        command += ["-drive", f"file={str(disk).replace(',', ',,')},format=raw,if=none,id=check{index}"]
        command += ["-device", f"virtio-blk-device,drive=check{index}"]
    result = subprocess.run(command, input='{"execute":"qmp_capabilities"}\n{"execute":"quit"}\n',
                            text=True, capture_output=True, timeout=30)
    if result.returncode or '"error"' in result.stdout:
        raise RuntimeError("Disk check failed; shut down both Debian systems first.\n" + result.stderr + result.stdout)

