import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("tool_versions_tests", ROOT / "scripts/debian/install/tool-manifest.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class InstalledVersionChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        paths = {row[0] for row in (*tools.HOST, *tools.GUEST, *tools.COMMON)}
        paths.update((tools.HELPER, "scripts/debian/install/install-host.sh", "scripts/debian/install/install-guest.sh"))
        for name in paths:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes() if not name.startswith("build/") else b"compiled fixture")
        self.bundles = self.root / "bundles"
        tools.write_bundles(self.bundles, self.root)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake_id = self.bin / "id"
        fake_id.write_text("#!/bin/sh\necho 0\n")
        fake_id.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")

    def install(self, role="guest"):
        installed = self.root / f"installed-{role}"
        bundle = self.bundles / role
        result = subprocess.run(["sh", str(bundle / tools.HELPER), role, str(bundle)],
                                env=dict(self.env, DESTDIR=str(installed)), capture_output=True, text=True)
        return installed, result

    def check(self, installed, expected=None):
        command = ["sh", str(ROOT / tools.CHECKER), "--root", str(installed)]
        if expected is not None:
            command += ["--expect-version", expected]
        return subprocess.run(command, capture_output=True, text=True)

    def test_both_roles_install_and_match_server_versions(self):
        expected = tools.expected_versions(self.root)
        for role in ("host", "guest"):
            with self.subTest(role=role):
                installed, result = self.install(role)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.check(installed, expected[role]).returncode, 0)
                self.assertTrue((installed / "usr/local/bin/check-virt-tools").is_file())
        self.assertEqual((self.root / "installed-host/var/lib/virt-tools/EXPECTED-GUEST-VERSION").read_text().strip(), expected["guest"])

    def test_changed_installed_file_is_reported(self):
        installed, result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        (installed / "usr/local/bin/check-virt-guest").write_text("changed")
        result = self.check(installed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/usr/local/bin/check-virt-guest checksum mismatch", result.stderr)

    def test_missing_installed_file_is_reported(self):
        installed, _ = self.install()
        (installed / "etc/systemd/system/virt-guest-test.service").unlink()
        result = self.check(installed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("virt-guest-test.service missing", result.stderr)

    def test_permission_changes_are_detected(self):
        installed, _ = self.install()
        (installed / "usr/local/bin/check-virt-guest").chmod(0o644)
        result = self.check(installed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode mismatch", result.stderr)

    def test_stale_but_consistent_installation_rejects_server_version(self):
        installed, _ = self.install()
        self.assertEqual(self.check(installed).returncode, 0)
        path = self.root / "tests/pmp-virt/runtime/check-virt-guest.sh"
        path.write_bytes(path.read_bytes() + b"\n# updated\n")
        result = self.check(installed, tools.expected_versions(self.root)["guest"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VERSION MISMATCH", result.stderr)

    def test_package_corruption_stops_before_any_install(self):
        (self.bundles / "host/payload/lkvm").write_bytes(b"corrupt")
        installed, result = self.install("host")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(installed.exists())

    def test_metadata_damage_is_rejected(self):
        installed, _ = self.install()
        (installed / "var/lib/virt-tools/FILES.tsv").write_text("")
        self.assertNotEqual(self.check(installed).returncode, 0)

    def test_versions_deterministic_and_guest_change_updates_host_pair(self):
        first = tools.expected_versions(self.root)
        self.assertEqual(first, tools.expected_versions(self.root))
        path = self.root / "scripts/debian/update/update-guest-tools.sh"
        path.write_bytes(path.read_bytes() + b"\n# new version\n")
        second = tools.expected_versions(self.root)
        self.assertNotEqual(first["guest"], second["guest"])
        self.assertNotEqual(first["host"], second["host"])

    def test_old_environment_without_metadata_fails_clearly(self):
        result = self.check(self.root / "uninitialized")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("install the current tools package", result.stderr)


if __name__ == "__main__":
    unittest.main()
