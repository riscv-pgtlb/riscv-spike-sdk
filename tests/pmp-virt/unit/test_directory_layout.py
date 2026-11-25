"""Exercise real package creation and installers after moving source directories."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class PackageLayoutChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for relative in ("scripts/debian/install", "scripts/debian/update", "scripts/debian/common", "scripts/debian/run",
                         "tests/pmp-virt/runtime", "tests/pmp-virt/regression/debian",
                         "tests/G-stage-virt"):
            shutil.copytree(ROOT / relative, self.root / relative)
        for relative in ("build/virt-kvm/src/kvmtool/lkvm-static", "build/virt-kvm/out/pv-user-test",
                         "build/virt-kvm/out/pv-syscall-api", "build/virt-kvm/out/pv-syscall-attack",
                         "build/virt-kvm/out/kvm-selftests/riscv/stage2_virt_test",
                         "build/virt-kvm/out/linux-guest/arch/riscv/boot/Image"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative)
        release = self.root / "os-release"
        release.write_text("ID=debian\n")
        for role in ("host", "guest"):
            path = self.root / f"scripts/debian/install/install-{role}.sh"
            path.write_text(path.read_text().replace("/etc/os-release", str(release)))
        self.bin = self.root / "bin"
        self.bin.mkdir()
        verify = self.bin / "python3"
        verify.write_text(f'#!/bin/sh\ncase "$1" in */virt-kvm.py) exit 0;; esac\nexec {sys.executable} "$@"\n')
        verify.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        subprocess.run(["bash", str(self.root / "scripts/debian/install/pack-tools.sh")],
                       env=self.env, check=True, capture_output=True)

    def install_package(self, role):
        name = "debian-host-tools.tar.gz" if role == "host" else "debian-guest-tools.tar.gz"
        package = self.root / "build/debian-tools" / name
        unpacked = self.root / "unpacked"
        unpacked.mkdir()
        with tarfile.open(package) as archive:
            names = archive.getnames()
            self.assertFalse(any("/unit/" in name or "__pycache__" in name for name in names))
            archive.extractall(unpacked, filter="data")
        release = self.root / "os-release"
        release.write_text("ID=debian\n")
        installer = unpacked / f"scripts/debian/install/install-{role}.sh"
        kernel = "6.17.2-pmpvirt-kvm-host+" if role == "host" else "6.17.2-virt-kvm-guest+"
        for command, body in {
            "id": "echo 0",
            "uname": f'case "$1" in -m) echo riscv64;; -r) echo {kernel};; esac',
            "systemctl": "exit 0",
        }.items():
            path = self.bin / command
            path.write_text("#!/bin/sh\n" + body + "\n")
            path.chmod(0o755)
        # Exercise the real installer with a staged destination; no privileged
        # writes are performed on the machine running these tests.
        installed = self.root / "installed"
        env = dict(self.env, DESTDIR=str(installed))
        subprocess.run(["bash" if role == "host" else "sh", str(installer)],
                       env=env, check=True, capture_output=True)
        self.assertTrue((installed / "usr/local/libexec/virt-tools/update-tools").is_file())
        if role == "host":
            for name in ("pv-syscall-api", "pv-syscall-attack"):
                self.assertTrue((installed / "usr/bin" / name).is_file())
            self.assertTrue((installed / "usr/local/bin/run-debian-guest").is_file())
            self.assertTrue((installed / "usr/local/bin/check-virt-vs-hs").is_file())
            self.assertTrue((installed / "usr/local/bin/check-stage2-virt-host").is_file())
            self.assertTrue((installed / "usr/bin/stage2_virt_test").is_file())
            self.assertTrue((installed / "usr/local/bin/update-host-tools").is_file())
            self.assertTrue((installed / "usr/local/bin/test-virt-debian-all").is_file())
            self.assertTrue((installed / "opt/guest/Image").is_file())
        else:
            self.assertTrue((installed / "usr/local/bin/update-guest-tools").is_file())
            self.assertTrue((installed / "usr/local/bin/check-virt-guest").is_file())
            self.assertTrue((installed / "etc/systemd/system/virt-guest-test.service").is_file())

    def test_host_package_installs_from_new_layout(self):
        self.install_package("host")

    def test_guest_package_installs_from_new_layout(self):
        self.install_package("guest")


if __name__ == "__main__":
    unittest.main()
