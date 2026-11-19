import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("build_sdk_tests", ROOT / "scripts/build/virt-kvm.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
spec = importlib.util.spec_from_file_location("regression_tests", ROOT / "tests/pmp-virt/regression/buildroot/run-regression.py")
regression = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regression)


VS_HS_EVIDENCE = (
    "PMP.Virt VS BEFORE PASS: GPA=0000000081000000 result=42",
    " Info: PMP.Virt VS/HS BEGIN: GPA=0x81000000 HPA=0x90001000 cause=1",
    "PMP.Virt VS AFTER PASS: GPA=0000000081000000 result=42",
    " Info: PMP.Virt VS/HS COMPLETE: GPA=0x81000000 HPA=0x90001000 guest_report=42",
    "PMP.Virt VS-HS-VS SAME-PAGE PASS: GPA=0000000081000000",
)

def runtime_lines():
    lines = ["PMP.Virt SEALED:", "VIRT-KVM GUEST BOOTED"]
    # Reuse the complete captured-format fixture, then mutate it in parser tests.
    from test_pmpvirt_suite import syscall_output
    for marker in regression.STEPS:
        if marker in (regression.STEPS[0], regression.STEPS[4]):
            lines += syscall_output().splitlines()
        lines.append(marker)
        if marker == regression.STEPS[0]:
            lines += list(VS_HS_EVIDENCE)
    return lines


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


class BuildChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.context = patch.multiple(build, ROOT=self.root, WORK=self.root / "build/virt-kvm",
                                      SOURCE_LOCK=self.root / "conf/pmp-virt/sources.json")
        self.context.start()
        self.image = self.root / "Image"
        header = bytearray(64)
        header[56:60] = b"RSC\x05"
        self.image.write_bytes(header)
        self.system_map = self.root / "System.map"
        self.symbols()

    def tearDown(self):
        self.context.stop()
        self.directory.cleanup()

    def symbols(self, **overrides):
        values = dict(_start=0xffffffff80000000, _text=0xffffffff80002000,
                      _etext=0xffffffff805ffff1, __start_rodata=0xffffffff80800000,
                      _data=0xffffffff80c00000)
        values.update(overrides)
        self.system_map.write_text("".join(f"{value:x} T {key}\n" for key, value in values.items()))

    def fixture(self):
        for path in build.artifact_paths():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        build.SOURCE_LOCK.write_text(json.dumps({"schema": 1, "sources": build.SOURCES}))
        host = build.WORK / "out/linux-host"
        (host / "arch/riscv/boot/Image").write_bytes(self.image.read_bytes())
        (host / "System.map").write_bytes(self.system_map.read_bytes())
        (build.WORK / "generated/pmp_virt_layout.h").write_text(build.layout_header(self.image, self.system_map))
        (build.WORK / "out/opensbi/platform/generic/firmware/fw_jump.bin").write_bytes(build.digest(self.image).encode())
        build.manifest()

    def test_layout_final_image_and_2g_ram(self):
        header = build.layout_header(self.image, self.system_map)
        self.assertIn("PV_TEXT_START 0x80202000UL", header)
        self.assertIn("PV_TEXT_LIMIT 0x80800000UL", header)
        self.assertIn("PV_RAM_LIMIT 0x100000000UL", header)
        self.assertIn("PV_RAM_NAPOT 0x2fffffffUL", header)
        self.assertIn(build.digest(self.image), header)

    def test_layout_rejects_overlap(self):
        self.symbols(__start_rodata=0xffffffff80400000)
        with self.assertRaises(RuntimeError):
            build.layout_header(self.image, self.system_map)

    def test_layout_rejects_alignment(self):
        self.symbols(__start_rodata=0xffffffff80800001)
        with self.assertRaises(RuntimeError):
            build.layout_header(self.image, self.system_map)

    def test_layout_rejects_missing_symbols(self):
        self.system_map.write_text("")
        with self.assertRaises(RuntimeError):
            build.layout_header(self.image, self.system_map)

    def test_layout_rejects_outside_ram(self):
        self.symbols(_data=0xffffffffffe00000)
        with self.assertRaises(RuntimeError):
            build.layout_header(self.image, self.system_map)

    def test_layout_rejects_invalid_image(self):
        self.image.write_bytes(bytes(64))
        with self.assertRaises(RuntimeError):
            build.layout_header(self.image, self.system_map)

    def test_output_cannot_escape(self):
        with self.assertRaises(RuntimeError):
            build.private_path(self.root / "repo/opensbi")

    def test_manifest_matching(self):
        self.fixture()
        build.verify()

    def test_manifest_rejects_old_schema(self):
        self.fixture()
        path = build.WORK / "manifest.json"
        state = json.loads(path.read_text())
        state["schema"] = 1
        path.write_text(json.dumps(state))
        with self.assertRaises(RuntimeError):
            build.verify()

    def test_manifest_rejects_changed_image(self):
        self.fixture()
        (build.WORK / "out/linux-host/arch/riscv/boot/Image").write_bytes(b"wrong")
        with self.assertRaises(RuntimeError):
            build.verify()

    def test_manifest_rejects_stale_firmware(self):
        self.fixture()
        (build.WORK / "out/opensbi/platform/generic/firmware/fw_jump.bin").write_bytes(b"stale")
        build.manifest()
        with self.assertRaisesRegex(RuntimeError, "Compiled firmware"):
            build.verify()

    def test_repack_rejects_changed_base(self):
        self.fixture()
        base = self.root / "base.cpio.gz"
        base.write_bytes(b"old")
        build.manifest(base)
        base.write_bytes(b"new")
        with patch.object(build, "package_rootfs") as pack:
            with self.assertRaisesRegex(RuntimeError, "base initramfs"):
                build.repack()
            pack.assert_not_called()

    def test_repack_keeps_compiled_artifacts(self):
        self.fixture()
        base = self.root / "base.cpio.gz"
        base.write_bytes(b"base")
        build.manifest(base, compiler_version="test GCC")
        (self.root / "tests/pmp-virt/runtime/check-virt-host.sh").write_bytes(b"script update")
        image = build.WORK / "out/linux-host/arch/riscv/boot/Image"
        before = build.digest(image)
        with patch.object(build, "validate_rootfs"), patch.object(build, "package_rootfs"):
            build.repack()
        self.assertEqual(before, build.digest(image))

    def test_generated_header_does_not_modify_firmware_source(self):
        source = self.root / "repo/opensbi"
        (source / "include/sbi").mkdir(parents=True)
        wrapper = source / "include/sbi/pmp_virt_layout.h"
        wrapper.write_bytes(b"#include PMP_VIRT_LAYOUT_HEADER\n")
        host = build.WORK / "out/linux-host"
        (host / "arch/riscv/boot").mkdir(parents=True)
        (host / "arch/riscv/boot/Image").write_bytes(self.image.read_bytes())
        (host / "System.map").write_bytes(self.system_map.read_bytes())
        config = build.WORK / "out/opensbi/platform/generic/kconfig/.config"
        config.parent.mkdir(parents=True)
        config.write_text("CONFIG_PMP_VIRT_SEAL=y\n")
        with patch.object(build, "verify_source", return_value=source), patch.object(build, "run") as commands:
            build.build_firmware("riscv64-linux-", 2)
        self.assertEqual(wrapper.read_bytes(), b"#include PMP_VIRT_LAYOUT_HEADER\n")
        self.assertTrue((build.WORK / "generated/pmp_virt_layout.h").is_file())
        self.assertIn(f"PMP_VIRT_LAYOUT_HEADER={(build.WORK / 'generated/pmp_virt_layout.h').as_posix()}", commands.call_args.args[0])

    def test_explicit_broken_compiler_does_not_fallback(self):
        with patch.dict(os.environ, {"CROSS_COMPILE": "chosen-"}), patch.object(build, "probe_toolchain", side_effect=RuntimeError("broken")) as probe:
            with self.assertRaisesRegex(RuntimeError, "Explicit"):
                build.cross_prefix()
            probe.assert_called_once_with("chosen-")

    def test_buildroot_automatic_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(build, "probe_toolchain", side_effect=[RuntimeError("broken"), "working-"]):
            self.assertEqual(build.cross_prefix(), "working-")

    def test_real_git_submodule_check_and_dirty_rejection(self):
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "test")
        git(self.root, "config", "user.email", "test@example.invalid")
        source = self.root / "repo/qemu"
        source.mkdir(parents=True)
        git(source, "init", "-q")
        git(source, "config", "user.name", "test")
        git(source, "config", "user.email", "test@example.invalid")
        (source / "pmp.c").write_bytes(b"source\n")
        git(source, "add", "pmp.c")
        git(source, "commit", "-qm", "base")
        revision = git(source, "rev-parse", "HEAD")
        git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{revision},repo/qemu")
        with patch.dict(build.SOURCES, {"qemu": {"path": "repo/qemu", "revision": revision}}):
            self.assertEqual(build.checked_submodule("qemu"), source)
            self.assertEqual(build.prepare_source("qemu"), source)
            (source / "pmp.c").write_bytes(b"changed\n")
            with self.assertRaisesRegex(RuntimeError, "local changes"):
                build.checked_submodule("qemu")

    def test_guest_worktree_preparation_revision_and_dirty_checks(self):
        host = self.root / "repo/linux"
        host.mkdir(parents=True)
        git(host, "init", "-q")
        git(host, "config", "user.name", "test")
        git(host, "config", "user.email", "test@example.invalid")
        (host / "source.c").write_text("guest base")
        git(host, "add", ".")
        git(host, "commit", "-qm", "guest")
        guest_revision = git(host, "rev-parse", "HEAD")
        (host / "source.c").write_text("host changes")
        git(host, "commit", "-qam", "host")
        host_revision = git(host, "rev-parse", "HEAD")
        locks = {
            "linux-host": {"path": "repo/linux", "revision": host_revision},
            "linux-guest": {"path": "repo/linux-guest", "revision": guest_revision},
        }
        with patch.dict(build.SOURCES, locks), patch.object(build, "prepare_source", return_value=host):
            guest = build.prepare_guest()
            self.assertEqual(guest, self.root / "repo/linux-guest")
            self.assertEqual(build.verify_source("linux-guest"), guest)
            self.assertEqual(build.prepare_guest(), guest)
            self.assertFalse((self.root / "build/virt-kvm/src/linux-guest").exists())
            (guest / "source.c").write_text("uncommitted guest")
            with self.assertRaisesRegex(RuntimeError, "local changes"):
                build.checked_guest()
            self.assertEqual((guest / "source.c").read_text(), "uncommitted guest")
            git(guest, "restore", "source.c")
            git(guest, "checkout", "--detach", host_revision)
            with self.assertRaisesRegex(RuntimeError, "revision mismatch"):
                build.checked_guest()

    def test_rootfs_installs_shared_vs_hs_checker(self):
        def fake_install(source, target, executable=False):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture")
        with patch.object(build, "install", side_effect=fake_install) as copier, \
             patch.object(build, "elf_machine"), patch.object(build, "append_archive"):
            build.package_rootfs(self.root / "base.cpio.gz")
        self.assertTrue(any(str(call.args[1]).endswith("/usr/bin/check-virt-vs-hs")
                            for call in copier.call_args_list))

    def test_buildroot_only_enables_vs_hs_in_regression_mode(self):
        script = (ROOT / "scripts/buildroot/run-virt-guest.sh").read_text()
        binary = self.root / "bin"
        binary.mkdir()
        (binary / "lkvm").write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        (binary / "check-virt-host").write_text("#!/bin/sh\nexit 0\n")
        for path in binary.iterdir():
            path.chmod(0o755)
        payload = self.root / "guest"
        payload.mkdir()
        for name in ("Image", "rootfs.cpio.gz"):
            (payload / name).write_text("fixture")
        script = script.replace("/usr/bin/", str(binary) + "/").replace("/opt/guest/", str(payload) + "/")
        wrapper = self.root / "launch.sh"
        wrapper.write_text(script)
        for args, enabled in (([], False), (["--regression"], True)):
            actual = subprocess.check_output(["sh", str(wrapper), *args], text=True).splitlines()
            self.assertEqual("--pmp-virt-test" in actual, enabled)
            cmdline = actual[actual.index("-p") + 1]
            self.assertEqual("pmpvirt_guest_test=1" in cmdline, enabled)

    def test_guest_config_requires_probe_but_not_kvm(self):
        source = self.root / "repo/linux-guest"
        config = self.root / "conf/pmp-virt/linux.config"
        config.parent.mkdir(parents=True)
        required = ("BLK_DEV_INITRD", "DEVTMPFS", "SERIAL_8250_CONSOLE", "VIRTIO_MMIO",
                    "STRICT_KERNEL_RWX", "VIRTIO_BLK", "VIRTIO_NET", "EXT4_FS", "NET", "INET")
        base = "".join(f"CONFIG_{symbol}=y\n" for symbol in required)
        config.write_text(base + "CONFIG_RISCV_PMP_VIRT_GUEST_TEST=y\n")
        with patch.object(build, "verify_source", return_value=source), patch.object(build, "run") as commands:
            build.configure_linux("linux-guest", "test-")
            self.assertTrue(any(call.args[0][-2:] == ["--enable", "RISCV_PMP_VIRT_GUEST_TEST"]
                                for call in commands.call_args_list))
            config.write_text(base)
            with self.assertRaisesRegex(RuntimeError, "RISCV_PMP_VIRT_GUEST_TEST"):
                build.configure_linux("linux-guest", "test-")

    def stale_kvmtool(self, dirty=False):
        original = self.root / "repo/kvmtool"
        original.mkdir(parents=True)
        git(original, "init", "-q")
        git(original, "config", "user.name", "test")
        git(original, "config", "user.email", "test@example.invalid")
        (original / "tool.c").write_text("old")
        git(original, "add", ".")
        git(original, "commit", "-qm", "old")
        old = git(original, "rev-parse", "HEAD")
        (original / "tool.c").write_text("new")
        git(original, "commit", "-qam", "new")
        new = git(original, "rev-parse", "HEAD")
        target = build.WORK / "src/kvmtool"
        target.parent.mkdir(parents=True)
        subprocess.run(["git", "clone", "-q", str(original), str(target)], check=True)
        git(target, "checkout", "-q", "--detach", old)
        build.write_json(build.WORK / "state/kvmtool.json", {"schema": 2, "revision": old})
        if dirty:
            (target / "tool.c").write_text("local changes")
        lock = {"path": "repo/kvmtool", "revision": new, "url": str(original)}
        return original, target, lock

    def test_prepare_archives_clean_old_kvmtool(self):
        original, target, lock = self.stale_kvmtool()
        with patch.dict(build.SOURCES, {"kvmtool": lock}), \
             patch.object(build, "checked_submodule", return_value=original):
            self.assertEqual(build.prepare_source("kvmtool"), target)
        self.assertEqual(git(target, "rev-parse", "HEAD"), lock["revision"])
        archived = list(target.parent.glob("archive-kvmtool-*/source/tool.c"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_text(), "old")

    def test_prepare_preserves_dirty_old_kvmtool(self):
        original, target, lock = self.stale_kvmtool(dirty=True)
        with patch.dict(build.SOURCES, {"kvmtool": lock}), \
             patch.object(build, "checked_submodule", return_value=original):
            with self.assertRaisesRegex(RuntimeError, "unexpected changes"):
                build.prepare_source("kvmtool")
        self.assertEqual((target / "tool.c").read_text(), "local changes")
        self.assertFalse(list(target.parent.glob("archive-kvmtool-*")))

    def test_source_lock_separates_host_and_guest(self):
        self.assertNotEqual(build.SOURCES["linux-host"]["revision"], build.SOURCES["linux-guest"]["revision"])
        source = (ROOT / "scripts/build/virt-kvm.py").read_text()
        self.assertNotIn('"apply"', source)
        self.assertNotIn("adapt_firmware", source)
        self.assertNotIn("pmp-virt/patches", source)

    def test_runtime_parser_accepts_nested_serial_carriage_returns(self):
        lines = runtime_lines()
        transcript = "".join(line + ("\r\r\n" if "GUEST PASS" in line or "GUEST SHUTDOWN" in line else "\r\n") for line in lines)
        regression.check_transcript(transcript)
        for marker in regression.STEPS:
            with self.subTest(marker=marker), self.assertRaises(RuntimeError):
                regression.check_transcript(transcript.replace(marker, "# echo '" + marker + "'"))
        with self.assertRaises(RuntimeError):
            regression.check_transcript(transcript + "VIRT-REGRESSION FAIL guest checks\r\r\n")

    def test_runtime_parser_rejects_echoed_or_missing_results(self):
        valid = "\n".join(runtime_lines()) + "\n"
        regression.check_transcript(valid)
        for invalid in (valid.replace(regression.STEPS[1], "# echo '" + regression.STEPS[1] + "'"),
                        valid.replace(regression.STEPS[3], ""),
                        valid + "PMP.Virt TEST FAIL\n"):
            with self.assertRaises(RuntimeError):
                regression.check_transcript(invalid)


if __name__ == "__main__":
    unittest.main()
