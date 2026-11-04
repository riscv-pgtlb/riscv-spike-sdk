#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "virt-kvm"
PACKAGE = ROOT / "pmp-virt-a5"
SDK = Path(os.environ.get("SOURCE_SDK", str(Path.home() / "work/riscv-spike-sdk"))).resolve()
RAM_BASE = 0x80000000
RAM_SIZE = 2048 * 1024 * 1024
LOAD_ADDRESS = 0x80200000
SOURCES = {
    "linux-host": ("LINUX_REPO", "449d48b1b99fdaa076166e200132705ac2bee711", "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git", "v6.17.2", [SDK / "repo/linux", Path.home() / "work/linux-pmp-virt-user-src", Path.home() / "work/linux-pmp-virt-test-src"]),
    "linux-guest": ("LINUX_REPO", "449d48b1b99fdaa076166e200132705ac2bee711", "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git", "v6.17.2", [WORK / "src/linux-host", SDK / "repo/linux", Path.home() / "work/linux-pmp-virt-user-src"]),
    "opensbi": ("OPENSBI_REPO", "a32a91069119e7a5aa31e6bc51d5e00860be3d80", "https://github.com/riscv-software-src/opensbi.git", "v1.7", [SDK / "repo/opensbi", Path.home() / "work/opensbi-pmp-virt-user-src", Path.home() / "work/opensbi-pmp-virt-test-src"]),
    "qemu": ("QEMU_REPO", "f8b2f64e2336a28bf0d50b6ef8a7d8c013e9bcf3", "https://github.com/qemu/qemu.git", "v10.1.0", [SDK / "repo/riscv-gnu-toolchain/qemu", Path.home() / "work/qemu"]),
    "dtc": ("DTC_REPO", "f99e3af0ecb67a9085478a9b8ddbcc25aa64931d", "https://git.kernel.org/pub/scm/utils/dtc/dtc.git", "f99e3af0ecb67a9085478a9b8ddbcc25aa64931d", [SDK / "repo/dtc"]),
    "kvmtool": ("KVMTOOL_REPO", "eb915c763e4b95dd4a9d32763fd449459742e053", "https://github.com/kvmtool/kvmtool.git", "eb915c763e4b95dd4a9d32763fd449459742e053", [SDK / "repo/kvmtool"]),
}
DISABLED = ("MODULES", "JUMP_LABEL", "FUNCTION_TRACER", "FUNCTION_GRAPH_TRACER", "DYNAMIC_FTRACE", "FTRACE", "KPROBES", "LIVEPATCH", "BPF_JIT", "RANDOMIZE_BASE", "KEXEC", "KEXEC_FILE", "KGDB")


def fail(message):
    raise RuntimeError(message)


def run(arguments, cwd=None, capture=False, env=None):
    arguments = [str(argument) for argument in arguments]
    if not capture:
        print("+ " + shlex.join(arguments), flush=True)
    return subprocess.run(arguments, cwd=cwd, env=env, check=True,
                          stdout=subprocess.PIPE if capture else None,
                          text=True).stdout


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def private_path(path):
    path = Path(path).resolve()
    expected = ROOT / "build" / "virt-kvm"
    if not path.is_relative_to(expected):
        fail(f"Output must stay inside {expected}: {path}")
    return path


def write_json(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_a5():
    for record in (PACKAGE / "SHA256SUMS").read_text().splitlines():
        expected, filename = record.split(maxsplit=1)
        path = (PACKAGE / filename.removeprefix("*")).resolve()
        if not path.is_relative_to(PACKAGE.resolve()) or digest(path) != expected:
            fail(f"A5 checksum mismatch: {filename}")


def require_checkout():
    top = Path(run(["git", "-C", ROOT, "rev-parse", "--show-toplevel"], capture=True).strip()).resolve()
    branch = run(["git", "-C", ROOT, "branch", "--show-current"], capture=True).strip()
    if top != ROOT or branch != "pmp-virt-kvm-integration":
        fail("Use the separate pmp-virt-kvm-integration checkout")
    for revision in ("b47454ec6f067deb660432a2aaf1bc34f294aa65", "746d4f0911901bc4b5d539583841b94b61059821"):
        run(["git", "-C", ROOT, "merge-base", "--is-ancestor", revision, "HEAD"])


def local_repository(name):
    variable, revision, _, _, candidates = SOURCES[name]
    if variable in os.environ:
        candidates = [Path(os.environ[variable])]
    for candidate in candidates:
        candidate = candidate.resolve()
        if not (candidate / ".git").exists():
            continue
        try:
            top = Path(run(["git", "-C", candidate, "rev-parse", "--show-toplevel"], capture=True).strip()).resolve()
            if top != candidate:
                continue
            subprocess.run(["git", "-C", str(candidate), "cat-file", "-e", revision + "^{commit}"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return candidate
        except subprocess.CalledProcessError:
            continue
    if variable in os.environ:
        fail(f"{variable} is not a repository containing {revision}")
    return None


def toolchain_command(arguments, input_text=None):
    try:
        result = subprocess.run(arguments, input=input_text, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        fail(f"Cannot run {arguments[0]}: {error}")
    if result.returncode:
        fail(f"{arguments[0]} failed: {result.stdout.strip()[-1200:]}")
    return result.stdout.strip()


def probe_toolchain(candidate):
    compiler = shutil.which(candidate + "gcc")
    if not compiler:
        fail(f"Compiler entry not found: {candidate}gcc")
    prefix = str(Path(compiler).absolute())[:-3]
    toolchain_command([prefix + "gcc", "--version"])
    target = toolchain_command([prefix + "gcc", "-dumpmachine"])
    if not target.startswith("riscv64-") or "linux" not in target.split("-"):
        fail(f"Expected a RISC-V 64-bit Linux compiler, found {target}")
    for tool in ("as", "ld", "ar", "nm", "objcopy", "objdump", "readelf", "strip"):
        toolchain_command([prefix + tool, "--version"])
    private_path(WORK).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="toolchain-probe-", dir=WORK) as temporary:
        executable = Path(temporary) / "probe"
        program = '#include <stdio.h>\nint main(void) { return puts("virt-kvm toolchain probe") < 0; }\n'
        toolchain_command([prefix + "gcc", "-x", "c", "-", "-static", "-o", str(executable)], program)
        try:
            elf_machine(executable, 243)
        except OSError as error:
            fail(f"Compiler did not produce a readable executable: {error}")
    print(f"Cross compiler, binutils and static RISC-V link: PASS ({prefix})", flush=True)
    return prefix


def cross_prefix():
    explicit = os.environ.get("CROSS_COMPILE")
    if explicit is not None:
        if not explicit:
            fail("CROSS_COMPILE is empty; unset it or specify an installed tool prefix")
        try:
            return probe_toolchain(explicit)
        except RuntimeError as error:
            fail(f"Explicit CROSS_COMPILE is unusable: {error}")
    candidates = [str(SDK / "toolchain/bin/riscv64-unknown-linux-gnu-"),
                  str(SDK / "rootfs/buildroot_initramfs/host/bin/riscv64-linux-"),
                  "riscv64-linux-gnu-"]
    errors = []
    for candidate in candidates:
        try:
            return probe_toolchain(candidate)
        except RuntimeError as error:
            errors.append(f"{candidate}: {error}")
            print(f"Skipping unusable toolchain: {errors[-1]}", flush=True)
    fail("No usable cross compiler. Set CROSS_COMPILE to an installed RISC-V Linux tool prefix.\n" + "\n".join(errors))


def base_rootfs():
    candidates = [Path(os.environ["BASE_ROOTFS"])] if "BASE_ROOTFS" in os.environ else [
        SDK / "images/base/rootfs.cpio.gz",
        SDK / "rootfs/buildroot_initramfs/images/rootfs.cpio.gz",
        Path.home() / "work/my_core_files/rootfs-devtmpfs.cpio.gz"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    fail("No base initramfs. Set BASE_ROOTFS to an existing rootfs.cpio.gz.")


def validate_rootfs(base):
    decompressor = subprocess.Popen(["gzip", "-cd", str(base)], stdout=subprocess.PIPE)
    try:
        listing = subprocess.run(["cpio", "-it", "--quiet"], stdin=decompressor.stdout,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    finally:
        decompressor.stdout.close()
        status = decompressor.wait()
    if status or listing.returncode:
        fail(f"Invalid gzip/newc base initramfs: {base}")
    names = {name.removeprefix("./").rstrip("/") for name in listing.stdout.splitlines()}
    for required in ("sbin/init", "bin/sh", "bin/mount", "bin/echo", "sbin/getty"):
        if required not in names:
            fail(f"Base initramfs lacks {required}")
    print(f"Base initramfs archive and init tools: PASS ({base})", flush=True)


def source_inputs(name):
    paths = []
    if name == "linux-host":
        paths.append(PACKAGE / "linux-protected.patch")
    elif name == "opensbi":
        paths.append(PACKAGE / "opensbi.patch")
    elif name == "qemu":
        paths.append(PACKAGE / "qemu.patch")
    result = {str(path.relative_to(ROOT)): digest(path) for path in paths}
    if name == "opensbi":
        result["ram-policy"] = "2048MiB-v1"
    return result


def verify_source(name):
    source = private_path(WORK / "src" / name)
    marker = WORK / "state" / (name + ".json")
    if not marker.is_file():
        fail(f"Incomplete source preparation: {source}. Preserve it and inspect before retrying.")
    state = json.loads(marker.read_text())
    if state["inputs"] != source_inputs(name):
        fail(f"Prepared {name} uses different patches; inspect before rebuilding.")
    revision = run(["git", "-C", source, "rev-parse", "HEAD"], capture=True).strip()
    if revision != SOURCES[name][1]:
        fail(f"Unexpected source revision: {source}")
    changed = run(["git", "-C", source, "diff", "--name-only", "HEAD"], capture=True).splitlines()
    untracked = run(["git", "-C", source, "ls-files", "--others", "--exclude-standard"], capture=True).splitlines()
    if (set(changed) | set(untracked)) - set(state["files"]):
        fail(f"Unexpected source changes: {source}")
    for filename, expected in state["files"].items():
        if digest(source / filename) != expected:
            fail(f"Prepared source changed: {source / filename}")
    return source


def adapt_firmware(source):
    path = source / "lib/sbi/sbi_ecall_pvseal.c"
    content = path.read_text()
    replacements = [
        ("(0x80000000UL >> 2) | 0x1ffffffUL", "PV_RAM_NAPOT", 2),
        ("base < 0x90000000UL && limit > 0x80200000UL", "base < PV_RAM_LIMIT && limit > 0x80200000UL", 1),
        ("\t/* RAM: 0x80000000..0x8fffffff, naturally aligned 256 MiB. */\n", "", 1),
    ]
    for old, new, count in replacements:
        if content.count(old) != count:
            fail(f"Unexpected OpenSBI policy source: {old}")
        content = content.replace(old, new)
    path.write_text(content)
    header = source / "include/sbi/pmp_virt_layout.h"
    header.write_text(header.read_text() + ram_header())


def ram_header():
    if RAM_SIZE < 8 or RAM_SIZE & (RAM_SIZE - 1) or RAM_BASE % RAM_SIZE:
        fail("RAM must be a naturally aligned NAPOT region")
    napot = (RAM_BASE >> 2) | ((RAM_SIZE >> 3) - 1)
    return (f"#define PV_RAM_BASE 0x{RAM_BASE:x}UL\n"
            f"#define PV_RAM_LIMIT 0x{RAM_BASE + RAM_SIZE:x}UL\n"
            f"#define PV_RAM_NAPOT 0x{napot:x}UL\n")


def resume_pristine_fetch(name, source):
    source = private_path(source)
    git_directory = source / ".git"
    if not git_directory.is_dir() or not git_directory.resolve().is_relative_to(source):
        fail(f"Incomplete {name} preparation is not a private Git repository: {source}")
    if any(path.name != ".git" for path in source.iterdir()):
        fail(f"Incomplete {name} preparation contains files; preserve and inspect: {source}")
    top = Path(run(["git", "-C", source, "rev-parse", "--show-toplevel"], capture=True).strip()).resolve()
    if top != source:
        fail(f"Unexpected Git worktree while resuming {name}: {source}")
    head = subprocess.run(["git", "-C", str(source), "rev-parse", "--verify", "HEAD"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if head.returncode == 0:
        fail(f"Incomplete {name} preparation already has a checkout; preserve and inspect: {source}")
    fetched = run(["git", "-C", source, "rev-parse", "FETCH_HEAD^{commit}"], capture=True).strip()
    if fetched != SOURCES[name][1]:
        fail(f"Cannot resume {name}: downloaded {fetched}, expected {SOURCES[name][1]}")
    print(f"Resuming verified download without resetting or deleting files: {name}", flush=True)


def prepare_source(name):
    source = private_path(WORK / "src" / name)
    _, revision, url, ref, _ = SOURCES[name]
    if source.exists():
        if (WORK / "state" / (name + ".json")).is_file():
            return verify_source(name)
        resume_pristine_fetch(name, source)
    else:
        origin = local_repository(name)
        source.parent.mkdir(parents=True, exist_ok=True)
        if origin:
            run(["git", "clone", "--shared", "--no-checkout", "--", origin, source])
        else:
            run(["git", "init", source])
            run(["git", "-C", source, "fetch", "--depth=1", url, ref])
            fetched = run(["git", "-C", source, "rev-parse", "FETCH_HEAD^{commit}"], capture=True).strip()
            if fetched != revision:
                fail(f"Fetched {name} revision mismatch: {fetched}, expected {revision}")
    run(["git", "-C", source, "checkout", "--detach", revision])
    files = []
    for filename in source_inputs(name):
        if filename == "ram-policy":
            continue
        patch = ROOT / filename
        run(["git", "-C", source, "apply", "--check", patch])
        run(["git", "-C", source, "apply", patch])
        files.extend(line[6:] for line in patch.read_text().splitlines() if line.startswith("+++ b/"))
    if name == "opensbi":
        adapt_firmware(source)
    state = {"revision": revision, "inputs": source_inputs(name),
             "files": {filename: digest(source / filename) for filename in files}}
    write_json(WORK / "state" / (name + ".json"), state)
    return verify_source(name)


def check():
    verify_a5()
    print(f"SDK: {ROOT}\nOutputs: {WORK}\nSource cache: {SDK}")
    errors = []
    for executable in ("git", "make", "gcc", "g++", "python3", "cpio", "gzip", "pkg-config"):
        print(f"{executable}: {shutil.which(executable) or 'MISSING'}")
        if not shutil.which(executable):
            errors.append(f"Missing build tool: {executable}")
    for name in SOURCES:
        print(f"{name}: {local_repository(name) or 'not cached; prepare will fetch the pinned revision'}")
    for label, lookup in (("CROSS_COMPILE", cross_prefix), ("BASE_ROOTFS", base_rootfs)):
        try:
            print(f"{label}: {lookup()}")
        except RuntimeError as error:
            errors.append(str(error))
    print(f"Free disk: {shutil.disk_usage(ROOT).free // (1024 ** 3)} GiB")
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        fail("Preflight needs the inputs listed above; no sources were modified.")


def configure_linux(name, cross):
    source = verify_source(name)
    output = private_path(WORK / "out" / name)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PACKAGE / "linux-protected.config", output / ".config")
    config = [source / "scripts/config", "--file", output / ".config"]
    for symbol in DISABLED:
        run(config + ["--disable", symbol])
    for symbol in ("VIRTUALIZATION", "KVM"):
        run(config + ["--enable" if name == "linux-host" else "--disable", symbol])
    run(config + ["--set-str", "LOCALVERSION", "-pmpvirt-kvm-host" if name == "linux-host" else "-virt-kvm-guest"])
    run(config + ["--disable", "LOCALVERSION_AUTO"])
    run(config + ["--set-str", "INITRAMFS_SOURCE", ""])
    run(["make", "-C", source, f"O={output}", "ARCH=riscv", f"CROSS_COMPILE={cross}", "olddefconfig"])
    content = (output / ".config").read_text()
    for symbol in DISABLED:
        if f"CONFIG_{symbol}=y\n" in content or f"CONFIG_{symbol}=m\n" in content:
            fail(f"Dynamic-code option remains enabled: {symbol}")
    expected = ["CONFIG_BLK_DEV_INITRD=y", "CONFIG_DEVTMPFS=y", "CONFIG_SERIAL_8250_CONSOLE=y", "CONFIG_VIRTIO_MMIO=y", "CONFIG_STRICT_KERNEL_RWX=y"]
    if name == "linux-host":
        expected.append("CONFIG_KVM=y")
    elif "CONFIG_KVM=y" in content.splitlines() or "CONFIG_KVM=m" in content.splitlines():
        fail("The ordinary guest must not enable KVM")
    for setting in expected:
        if setting not in content.splitlines():
            fail(f"Required {name} config missing: {setting}")
    return source, output


def layout_header(image, system_map):
    symbols = {}
    for line in Path(system_map).read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    required = ("_start", "_text", "_etext", "__start_rodata", "_data")
    if any(symbol not in symbols for symbol in required):
        fail("System.map lacks required layout symbols")
    offset = LOAD_ADDRESS - symbols["_start"]
    text_start = symbols["_text"] + offset
    text_limit = (symbols["_etext"] + offset + 4095) & ~4095
    ro_start = symbols["__start_rodata"] + offset
    ro_limit = symbols["_data"] + offset
    if not LOAD_ADDRESS <= text_start < text_limit <= ro_start < ro_limit < RAM_BASE + RAM_SIZE:
        fail("Host layout is outside the trusted RAM range")
    if any(value % 4096 for value in (text_start, text_limit, ro_start, ro_limit)):
        fail("Host layout is not page aligned")
    with Path(image).open("rb") as stream:
        image_header = stream.read(64)
    if len(image_header) != 64 or image_header[56:60] != b"RSC\x05":
        fail("Expected an uncompressed RISC-V Linux Image")
    header = ""
    for name, value in (("TEXT_START", text_start), ("TEXT_LIMIT", text_limit), ("RO_START", ro_start), ("RO_LIMIT", ro_limit)):
        header += f"#define PV_{name} 0x{value:x}UL\n"
    return header + f'#define PV_IMAGE_SHA "{digest(image)}"\n' + ram_header()


def build_firmware(cross, jobs):
    source = verify_source("opensbi")
    host = WORK / "out/linux-host"
    header_path = source / "include/sbi/pmp_virt_layout.h"
    header_path.write_text(layout_header(host / "arch/riscv/boot/Image", host / "System.map"))
    marker = WORK / "state/opensbi.json"
    state = json.loads(marker.read_text())
    state["files"]["include/sbi/pmp_virt_layout.h"] = digest(header_path)
    write_json(marker, state)
    output = private_path(WORK / "out/opensbi")
    run(["make", "-C", source, f"O={output}", "PLATFORM=generic", "PLATFORM_RISCV_XLEN=64",
         "PLATFORM_DEFCONFIG=pmp_virt_seal_defconfig", f"CROSS_COMPILE={cross}",
         "FW_TEXT_START=0x80000000", "FW_JUMP_ADDR=0x80200000", f"-j{jobs}"])
    config = (output / "platform/generic/kconfig/.config").read_text().splitlines()
    if "CONFIG_PMP_VIRT_SEAL=y" not in config or "CONFIG_PMP_VIRT_TRANSPORT_TEST=y" in config:
        fail("OpenSBI seal configuration mismatch")


def append_archive(base, staging, destination):
    with gzip.open(base, "rb") as stream:
        while stream.read(1024 * 1024):
            pass
    listing = ["."] + ["./" + str(path.relative_to(staging)).replace(os.sep, "/")
                       for path in sorted(staging.rglob("*"))]
    archive = subprocess.run(["cpio", "--null", "-o", "-H", "newc", "--owner=0:0"],
                             cwd=staging, input=("\0".join(listing) + "\0").encode(),
                             stdout=subprocess.PIPE, check=True).stdout
    destination = private_path(destination)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("wb") as stream:
        with Path(base).open("rb") as input_stream:
            shutil.copyfileobj(input_stream, stream)
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressor:
            compressor.write(archive)
    temporary.replace(destination)


def install(source, target, executable=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o755 if executable else 0o644)


def elf_machine(path, expected):
    with Path(path).open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != expected:
            fail(f"Unexpected ELF architecture: {path}")
        table_offset = int.from_bytes(header[32:40], "little")
        entry_size = int.from_bytes(header[54:56], "little")
        entry_count = int.from_bytes(header[56:58], "little")
        if not entry_count or entry_count > 1024 or entry_size < 56 or table_offset + entry_count * entry_size > Path(path).stat().st_size:
            fail(f"Invalid ELF program headers: {path}")
        for index in range(entry_count):
            stream.seek(table_offset + index * entry_size)
            if int.from_bytes(stream.read(4), "little") == 3:
                fail(f"Expected a static RISC-V executable, found PT_INTERP: {path}")


def package_rootfs(base):
    images = private_path(WORK / "images")
    images.mkdir(parents=True, exist_ok=True)
    elf_machine(WORK / "src/kvmtool/lkvm-static", 243)
    elf_machine(WORK / "out/pv-user-test", 243)
    with tempfile.TemporaryDirectory(prefix="pack-", dir=WORK) as temporary:
        staging = Path(temporary)
        install(ROOT / "conf/rootfs-overlay/etc/inittab", staging / "etc/inittab")
        with (staging / "etc/inittab").open("a") as stream:
            stream.write("\n::sysinit:/bin/echo VIRT-KVM GUEST BOOTED\n")
        append_archive(base, staging, images / "guest-rootfs.cpio.gz")
    with tempfile.TemporaryDirectory(prefix="pack-", dir=WORK) as temporary:
        staging = Path(temporary)
        install(ROOT / "conf/rootfs-overlay/etc/inittab", staging / "etc/inittab")
        install(WORK / "src/kvmtool/lkvm-static", staging / "usr/bin/lkvm", True)
        install(WORK / "out/pv-user-test", staging / "usr/bin/pv-user-test", True)
        install(ROOT / "integration/check-host.sh", staging / "usr/bin/check-virt-host", True)
        install(ROOT / "integration/run-guest.sh", staging / "usr/bin/run-virt-guest", True)
        install(WORK / "out/linux-guest/arch/riscv/boot/Image", staging / "opt/guest/Image")
        install(images / "guest-rootfs.cpio.gz", staging / "opt/guest/rootfs.cpio.gz")
        append_archive(base, staging, images / "host-rootfs.cpio.gz")


def artifact_paths():
    return [WORK / path for path in (
        "out/linux-host/arch/riscv/boot/Image", "out/linux-host/.config", "out/linux-host/System.map",
        "out/linux-guest/arch/riscv/boot/Image", "out/linux-guest/.config",
        "out/opensbi/platform/generic/firmware/fw_jump.bin", "out/opensbi/platform/generic/kconfig/.config",
        "out/qemu/qemu-system-riscv64", "out/pv-user-test", "src/kvmtool/lkvm-static",
        "src/opensbi/include/sbi/pmp_virt_layout.h", "images/host-rootfs.cpio.gz", "images/guest-rootfs.cpio.gz"
    )] + [PACKAGE / "linux-protected.config", ROOT / "integration/virt-kvm.py",
          ROOT / "integration/run-guest.sh", ROOT / "integration/check-host.sh"]


def manifest(base=None, cross=None, compiler_version=None):
    files = {str(path.relative_to(ROOT)): digest(path) for path in artifact_paths()}
    state = {"schema": 1, "ram_mib": RAM_SIZE // (1024 * 1024),
             "sources": {name: details[1] for name, details in SOURCES.items()}, "files": files}
    if base:
        state["base_rootfs"] = {"path": str(base), "sha256": digest(base)}
    if cross:
        state["compiler"] = run([cross + "gcc", "--version"], capture=True).splitlines()[0]
    elif compiler_version is not None:
        state["compiler"] = compiler_version
    write_json(WORK / "manifest.json", state)


def verify(allow_script_updates=False):
    verify_a5()
    state = json.loads((WORK / "manifest.json").read_text())
    expected_paths = {str(path.relative_to(ROOT)) for path in artifact_paths()}
    if state.get("schema") != 1 or state.get("ram_mib") != 2048 or set(state["files"]) != expected_paths:
        fail("Artifact manifest format, RAM size, or file list mismatch")
    if state["sources"] != {name: details[1] for name, details in SOURCES.items()}:
        fail("Artifact source revision mismatch")
    script_inputs = {str((ROOT / "integration" / name).relative_to(ROOT))
                     for name in ("virt-kvm.py", "check-host.sh", "run-guest.sh")}
    for filename, expected in state["files"].items():
        if allow_script_updates and filename in script_inputs:
            continue
        if digest(ROOT / filename) != expected:
            fail(f"Artifact checksum mismatch: {filename}. Rebuild before booting.")
    host = WORK / "out/linux-host"
    expected_header = layout_header(host / "arch/riscv/boot/Image", host / "System.map")
    if (WORK / "src/opensbi/include/sbi/pmp_virt_layout.h").read_text() != expected_header:
        fail("Firmware layout does not match the host Image")
    firmware = WORK / "out/opensbi/platform/generic/firmware/fw_jump.bin"
    if digest(host / "arch/riscv/boot/Image").encode() not in firmware.read_bytes():
        fail("Compiled firmware does not contain the current host Image digest")
    label = "Existing artifacts and host/firmware layout" if allow_script_updates else "Artifact hashes and host/firmware layout"
    print(label + ": PASS", flush=True)


def repack():
    verify(allow_script_updates=True)
    previous = json.loads((WORK / "manifest.json").read_text())
    base = Path(previous["base_rootfs"]["path"])
    if digest(base) != previous["base_rootfs"]["sha256"]:
        fail("The original base initramfs has changed; inspect before repacking")
    validate_rootfs(base)
    package_rootfs(base)
    manifest(base, compiler_version=previous.get("compiler"))
    verify()
    print("Rootfs repacked. Existing kernel, firmware and QEMU binaries were preserved.")


def build(jobs):
    verify_a5()
    cross = cross_prefix()
    base = base_rootfs()
    validate_rootfs(base)
    run([cross + "gcc", "--version"])
    for name in SOURCES:
        prepare_source(name)
    for name in ("linux-host", "linux-guest"):
        source, output = configure_linux(name, cross)
        run(["make", "-C", source, f"O={output}", "ARCH=riscv", f"CROSS_COMPILE={cross}", f"-j{jobs}", "Image"])
    build_firmware(cross, jobs)
    qemu_source = verify_source("qemu")
    qemu_output = private_path(WORK / "out/qemu")
    qemu_output.mkdir(parents=True, exist_ok=True)
    run([qemu_source / "configure", "--target-list=riscv64-softmmu", "--disable-docs", "--disable-slirp", "--enable-download"], cwd=qemu_output)
    run(["make", f"-j{jobs}"], cwd=qemu_output)
    dtc = verify_source("dtc")
    run(["make", "-C", dtc, "-B", f"CC={cross}gcc", f"AR={cross}ar",
         "NO_VALGRIND=1", "NO_YAML=1", f"-j{jobs}", "libfdt"])
    lkvm = verify_source("kvmtool")
    run(["make", "-C", lkvm, "ARCH=riscv", f"CROSS_COMPILE={cross}", f"LIBFDT_DIR={dtc / 'libfdt'}", f"-j{jobs}", "lkvm-static"])
    run([cross + "gcc", "-O2", "-Wall", "-Wextra", "-static", PACKAGE / "user.c", "-o", WORK / "out/pv-user-test"])
    package_rootfs(base)
    manifest(base, cross)
    verify()
    print("Build complete. Runtime validation has NOT been performed.")


def launch(dry_run):
    verify()
    command = [WORK / "out/qemu/qemu-system-riscv64", "-machine", "virt", "-accel", "tcg",
               "-cpu", "rv64,h=true,smepmp=off,x-pmp-virt=on", "-m", "2048M", "-smp", "1", "-nographic",
               "-bios", WORK / "out/opensbi/platform/generic/firmware/fw_jump.bin",
               "-kernel", WORK / "out/linux-host/arch/riscv/boot/Image",
               "-initrd", WORK / "images/host-rootfs.cpio.gz",
               "-append", "console=ttyS0 earlycon=sbi rdinit=/sbin/init maxcpus=1"]
    print(shlex.join([str(argument) for argument in command]), flush=True)
    if not dry_run:
        os.execv(str(command[0]), [str(argument) for argument in command])


def main():
    parser = argparse.ArgumentParser(description="Isolated PMP.Virt host + ordinary KVM guest, B1 integration")
    parser.add_argument("action", choices=("check", "prepare", "build", "repack", "verify", "run"))
    parser.add_argument("-j", "--jobs", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("jobs must be positive")
    if args.dry_run and args.action != "run":
        parser.error("--dry-run is only supported for run")
    private_path(WORK)
    require_checkout()
    if args.action in ("prepare", "build", "repack", "run") and platform.system() != "Linux" and not args.dry_run:
        fail("Build and run these steps in the Ubuntu server terminal")
    if args.action == "check":
        check()
    elif args.action == "prepare":
        verify_a5()
        for name in SOURCES:
            prepare_source(name)
    elif args.action == "build":
        build(args.jobs)
    elif args.action == "repack":
        repack()
    elif args.action == "verify":
        verify()
    else:
        launch(args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        sys.exit(1)
