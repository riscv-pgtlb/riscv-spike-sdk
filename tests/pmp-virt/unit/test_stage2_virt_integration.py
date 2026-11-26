#!/usr/bin/env python3
"""Keep every supported Host path wired to the Stage2Virt integration."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
CPU = "rv64,h=true,smepmp=off,x-pmp-virt=on,x-stage2-virt=on"
SMOKE_SOURCE = "tests/G-stage-virt/check-stage2-virt-kvmtool.sh"
SMOKE_TARGET = "/usr/local/bin/check-stage2-virt-kvmtool"


def source(path):
    return (ROOT / path).read_text()


class Stage2VirtProjectIntegration(unittest.TestCase):
    def test_all_host_boot_paths_enable_stage2_virt(self):
        paths = (
            "scripts/build/virt-kvm.py",
            "scripts/debian/run/run-dual-debian.sh",
            "scripts/debian/common/maintenance.py",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(CPU, source(path))

    def test_both_runtime_regressions_run_real_kvmtool_smoke(self):
        paths = (
            "tests/pmp-virt/regression/buildroot/test-virt-all.sh",
            "tests/pmp-virt/regression/debian/test-virt-debian-all.sh",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(SMOKE_TARGET, source(path))

    def test_buildroot_packages_real_kvmtool_smoke(self):
        build = source("scripts/build/virt-kvm.py")
        self.assertGreaterEqual(build.count(SMOKE_SOURCE), 2)
        self.assertIn("staging / \"usr/local/bin/check-stage2-virt-kvmtool\"", build)

    def test_debian_host_package_contains_real_kvmtool_smoke(self):
        manifest = source("scripts/debian/install/tool-manifest.py")
        self.assertIn(SMOKE_SOURCE, manifest)
        self.assertIn(SMOKE_TARGET, manifest)


if __name__ == "__main__":
    unittest.main()
