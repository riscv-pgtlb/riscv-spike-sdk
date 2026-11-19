"""Deployment failure checks using a small serial-process substitute for QEMU."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "debian_deploy_tests", ROOT / "scripts/debian/common/maintenance.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DebianDeploymentChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.disks = self.root / "deployment"
        self.disks.mkdir()
        for name in ("debian-host.raw", "debian-guest.raw", "setup.tar"):
            (self.disks / name).write_bytes(b"test input")
        self.qemu = self.root / "build/virt-kvm/out/qemu/qemu-system-riscv64"
        self.qemu.parent.mkdir(parents=True)
        self.context = patch.object(deploy, "ROOT", self.root)
        self.context.start()

    def tearDown(self):
        self.context.stop()
        self.directory.cleanup()

    def serial_process(self, body):
        self.qemu.write_text(f"#!{sys.executable}\n" + body)
        self.qemu.chmod(0o755)

    def test_missing_input(self):
        (self.disks / "setup.tar").unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing file"):
            deploy.validate_deploy(self.disks)

    def test_same_system_disk(self):
        guest = self.disks / "debian-guest.raw"
        guest.unlink()
        guest.hardlink_to(self.disks / "debian-host.raw")
        with self.assertRaisesRegex(RuntimeError, "separate files"):
            deploy.validate_deploy(self.disks)

    def test_transfer_cannot_alias_system_disk(self):
        transfer = self.disks / "setup.tar"
        transfer.unlink()
        transfer.symlink_to(self.disks / "debian-host.raw")
        with self.assertRaisesRegex(RuntimeError, "Transfer archive"):
            deploy.validate_deploy(self.disks)

    def test_success_and_readonly_transfer(self):
        self.serial_process(
            "import sys\n"
            "assert any('readonly=on' in arg for arg in sys.argv)\n"
            "assert any('debian_provision=1' in arg for arg in sys.argv)\n"
            "print('# ', end='', flush=True)\n"
            "command = input()\n"
            "print()\n"
            "assert 'provision-system.sh host' in command\n"
            "assert 'rc=$?' in command\n"
            "print('DEBIAN PROVISION PASS: host')\n"
            "print('DEBIAN PROVISION EXIT host: 0')\n")
        deploy.provision(self.disks, "host", timeout=5)
        self.assertIn(b"DEBIAN PROVISION PASS", (self.disks / "provision-host.log").read_bytes())

    def test_echoed_success_is_rejected(self):
        self.serial_process(
            "print('# echo DEBIAN PROVISION PASS: host')\n"
            "print('DEBIAN PROVISION EXIT host: 0')\n")
        with self.assertRaisesRegex(RuntimeError, "initialization failed"):
            deploy.provision(self.disks, "host", timeout=5)

    def test_update_boot_uses_update_script_and_distinct_markers(self):
        self.serial_process(
            "print('# ', end='', flush=True)\n"
            "command = input()\n"
            "print()\n"
            "assert 'update-system.sh guest' in command\n"
            "assert 'provision-system.sh' not in command\n"
            "print('DEBIAN UPDATE PASS: guest')\n"
            "print('DEBIAN UPDATE EXIT guest: 0')\n")
        deploy.provision(self.disks, "guest", timeout=5, action="update")
        self.assertTrue((self.disks / "update-guest.log").is_file())

    def test_nonzero_script_exit_is_rejected(self):
        self.serial_process(
            "print('DEBIAN PROVISION PASS: host')\n"
            "print('DEBIAN PROVISION EXIT host: 1')\n")
        with self.assertRaisesRegex(RuntimeError, "initialization failed"):
            deploy.provision(self.disks, "host", timeout=5)

    def test_qemu_failure_is_rejected(self):
        self.serial_process(
            "print('DEBIAN PROVISION PASS: host')\n"
            "print('DEBIAN PROVISION EXIT host: 0')\n"
            "raise SystemExit(1)\n")
        with self.assertRaisesRegex(RuntimeError, "initialization failed"):
            deploy.provision(self.disks, "host", timeout=5)

    def test_timeout_stops_serial_process(self):
        self.serial_process("import time\ntime.sleep(60)\n")
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            deploy.provision(self.disks, "guest", timeout=0.1)


class GuestInstallerChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.release = self.root / "os-release"
        self.release.write_text("ID=debian\n")
        self.cmdline = self.root / "cmdline"
        self.cmdline.write_text("console=ttyS0 debian_provision=1 init=/bin/sh\n")
        spec = importlib.util.spec_from_file_location("guest_installer_manifest", ROOT / "scripts/debian/install/tool-manifest.py")
        manifest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manifest)
        sources = {entry[0] for entry in (*manifest.HOST, *manifest.GUEST, *manifest.COMMON)}
        sources.update((manifest.HELPER, "scripts/debian/install/install-host.sh", "scripts/debian/install/install-guest.sh"))
        for source in sources:
            target = self.root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            content = (ROOT / source).read_bytes() if source.startswith("scripts/") else b"test payload"
            if source.endswith("install-guest.sh"):
                content = content.decode().replace("/etc/os-release", str(self.release)).replace("/proc/cmdline", str(self.cmdline)).encode()
            target.write_bytes(content)
        manifest.write_bundles(self.root / "bundles", self.root)
        self.bundle = self.root / "bundles/guest"
        self.installer = self.bundle / "scripts/debian/install/install-guest.sh"
        self.installed = self.root / "installed"
        self.log = self.root / "commands"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        CALL_LOG=str(self.log), TEST_KERNEL="6.17.2-virt-kvm-guest+",
                        TEST_ARCH="riscv64", TEST_UID="0", DESTDIR=str(self.installed))
        self.command("id", 'echo "$TEST_UID"')
        self.command("uname", 'case "$1" in -r) echo "$TEST_KERNEL";; -m) echo "$TEST_ARCH";; esac')
        self.command("systemctl", 'printf "systemctl %s\\n" "$*" >> "$CALL_LOG"')

    def tearDown(self):
        self.directory.cleanup()

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_installer(self, *args):
        return subprocess.run(["sh", str(self.installer), *args], env=self.env,
                              capture_output=True, text=True)

    def test_live_rejects_host_kernel_before_installing(self):
        self.env["TEST_KERNEL"] = "6.17.2-pmpvirt-kvm-host+"
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("guest kernel required", result.stderr)
        self.assertFalse(self.log.exists())

    def test_modes_install_same_files_and_only_live_reloads(self):
        self.assertEqual(self.run_installer().returncode, 0)
        live = self.log.read_text().splitlines()
        self.log.unlink()
        self.env["TEST_KERNEL"] = "6.17.2-pmpvirt-kvm-host+"
        self.assertEqual(self.run_installer("--maintenance").returncode, 0)
        maintenance = self.log.read_text().splitlines()
        self.assertTrue((self.installed / "usr/local/bin/check-virt-tools").is_file())
        self.assertEqual((self.installed / "var/lib/virt-tools/VERSION").read_text(),
                         (self.bundle / "metadata/guest/VERSION").read_text())
        self.assertIn("systemctl daemon-reload", live)
        self.assertEqual([s for s in maintenance if s.startswith("systemctl ")], [
            f"systemctl --root={self.installed} enable virt-guest-test.service",
            f"systemctl --root={self.installed} is-enabled virt-guest-test.service"])

    def test_maintenance_requires_exact_boot_marker(self):
        for cmdline in ("console=ttyS0", "debian_provision=10", "x_debian_provision=1"):
            with self.subTest(cmdline=cmdline):
                self.cmdline.write_text(cmdline)
                self.assertNotEqual(self.run_installer("--maintenance").returncode, 0)
                self.assertFalse(self.log.exists())

    def test_unknown_arguments_rejected(self):
        for args in (("--force",), ("--maintenance", "extra")):
            self.assertEqual(self.run_installer(*args).returncode, 2)
        self.assertFalse(self.log.exists())

    def test_maintenance_checks_arch_root_and_debian(self):
        for variable, value in (("TEST_ARCH", "x86_64"), ("TEST_UID", "1000")):
            with patch.dict(self.env, {variable: value}):
                self.assertNotEqual(self.run_installer("--maintenance").returncode, 0)
        self.release.write_text("ID=other\n")
        self.assertNotEqual(self.run_installer("--maintenance").returncode, 0)
        self.assertFalse(self.log.exists())

    def test_missing_service_rejected_before_partial_install(self):
        (self.bundle / "tests/pmp-virt/regression/debian/virt-guest-test.service").unlink()
        self.assertNotEqual(self.run_installer("--maintenance").returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
