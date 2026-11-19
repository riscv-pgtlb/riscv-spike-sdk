import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class DebianUpdateChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.input = self.root / "input"
        self.input.mkdir()
        self.log = self.root / "installed"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        TEST_KERNEL="6.17.2-virt-kvm-guest+", INSTALL_LOG=str(self.log),
                        INSTALL_EXIT="0", GUEST_RUNNING="1")
        for name, body in {
            "id": "echo 0",
            "uname": 'case "$1" in -m) echo riscv64;; -r) echo "$TEST_KERNEL";; esac',
            "pgrep": 'exit "$GUEST_RUNNING"',
        }.items():
            command = self.bin / name
            command.write_text("#!/bin/sh\n" + body + "\n")
            command.chmod(0o755)
        release = self.root / "os-release"
        release.write_text("ID=debian\n")
        text = (ROOT / "scripts/debian/update/update-tools.sh").read_text()
        text = text.replace("/etc/os-release", str(release))
        text = text.replace("/run/lock/virt-tools-update.lock", str(self.root / "lock"))
        text = text.replace("/var/tmp/virt-tools-update.XXXXXX", str(self.root / "work.XXXXXX"))
        self.script = self.root / "update-tools.sh"
        self.script.write_text(text)

    def package(self, role="guest"):
        name = "debian-guest-tools.tar.gz" if role == "guest" else "debian-host-tools.tar.gz"
        package = self.input / name
        body = b'echo installed >> "$INSTALL_LOG"\nexit "$INSTALL_EXIT"\n'
        with tarfile.open(package, "w:gz") as archive:
            entry = tarfile.TarInfo(f"scripts/debian/install/install-{role}.sh")
            entry.size = len(body)
            archive.addfile(entry, io.BytesIO(body))
        checksum = hashlib.sha256(package.read_bytes()).hexdigest()
        (self.input / "SHA256SUMS").write_text(
            f"{checksum}  {name}\n" + "0" * 64 + "  other-package.tar.gz\n")
        return package

    def run_update(self, role="guest"):
        return subprocess.run(["bash", str(self.script), role, "--from-dir", str(self.input)],
                              env=self.env, capture_output=True, text=True)

    def test_success_requires_only_selected_package_and_cleans_temp_files(self):
        self.package()
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VIRT TOOLS UPDATE PASS: guest", result.stdout)
        self.assertTrue(self.log.exists())
        self.assertEqual(list(self.root.glob("work.*")), [])

    def test_corrupt_package_never_runs_installer(self):
        self.package().write_bytes(b"corrupt")
        self.assertNotEqual(self.run_update().returncode, 0)
        self.assertFalse(self.log.exists())

    def test_missing_or_duplicate_checksum_never_runs_installer(self):
        self.package()
        sums = self.input / "SHA256SUMS"
        valid = sums.read_text()
        for contents in ("", valid + valid):
            sums.write_text(contents)
            self.assertNotEqual(self.run_update().returncode, 0)
            self.assertFalse(self.log.exists())

    def test_installer_failure_never_reports_success(self):
        self.package()
        self.env["INSTALL_EXIT"] = "1"
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.log.exists())
        self.assertNotIn("UPDATE PASS", result.stdout)

    def test_wrong_layer_never_runs_installer(self):
        self.package()
        self.env["TEST_KERNEL"] = "6.17.2-pmpvirt-kvm-host+"
        self.assertNotEqual(self.run_update().returncode, 0)
        self.assertFalse(self.log.exists())

    def test_host_rejects_running_guest_and_accepts_stopped_guest(self):
        self.package("host")
        self.env["TEST_KERNEL"] = "6.17.2-pmpvirt-kvm-host+"
        self.env["GUEST_RUNNING"] = "0"
        self.assertNotEqual(self.run_update("host").returncode, 0)
        self.assertFalse(self.log.exists())
        self.env["GUEST_RUNNING"] = "1"
        self.assertEqual(self.run_update("host").returncode, 0)


if __name__ == "__main__":
    unittest.main()
