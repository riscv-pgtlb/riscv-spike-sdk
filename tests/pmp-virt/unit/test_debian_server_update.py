import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("server_update_tests", ROOT / "scripts/debian/update/update-dual-debian.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class ServerUpdateChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.host = self.root / "host.raw"
        self.guest = self.root / "guest.raw"
        self.host.write_bytes(b"host contents")
        self.guest.write_bytes(b"guest contents")
        tools = self.root / "build/debian-host-transfer"
        tools.mkdir(parents=True)
        for name in ("dual-debian-tools.tar.gz", "debian-guest-tools.tar.gz", "SHA256SUMS",
                     "HOST-VERSION", "GUEST-VERSION"):
            (tools / name).write_text("fixture")
        bootstrap = self.root / "scripts/debian/update/update-system.sh"
        bootstrap.parent.mkdir(parents=True)
        bootstrap.write_text("fixture")
        self.addCleanup(patch.stopall)
        patch.object(update, "ROOT", self.root).start()
        self.preflight = patch.object(update, "check_stopped").start()
        self.pack = patch.object(update.subprocess, "run").start()
        self.boot = patch.object(update.maintenance, "provision").start()

    def test_missing_guest_stops_before_any_update(self):
        self.guest.unlink()
        with self.assertRaisesRegex(RuntimeError, "missing"):
            update.update(self.host, self.guest)
        self.boot.assert_not_called()
        self.pack.assert_not_called()

    def test_same_disk_stops_before_any_update(self):
        with self.assertRaisesRegex(RuntimeError, "separate files"):
            update.update(self.host, self.host)
        self.boot.assert_not_called()

    def test_busy_disk_stops_before_packaging(self):
        self.preflight.side_effect = RuntimeError("disk busy")
        with self.assertRaisesRegex(RuntimeError, "disk busy"):
            update.update(self.host, self.guest)
        self.pack.assert_not_called()
        self.boot.assert_not_called()

    def test_updates_both_without_initializing_disks(self):
        update.update(self.host, self.guest)
        calls = self.boot.call_args_list
        self.assertEqual([call.args[1] for call in calls], ["host", "guest"])
        self.assertTrue(all(call.kwargs == {"action": "update"} for call in calls))
        work = calls[0].args[0]
        self.assertTrue((work / "debian-host.raw").samefile(self.host))
        self.assertEqual(json.loads((work / "status.json").read_text())["completed"], ["host", "guest"])
        self.assertEqual(self.host.read_bytes(), b"host contents")
        self.assertFalse((work / "setup/root-password.hash").exists())

    def test_partial_failure_records_completed_role(self):
        self.boot.side_effect = [None, RuntimeError("guest failed")]
        with self.assertRaisesRegex(RuntimeError, "No rollback"):
            update.update(self.host, self.guest)
        work = self.boot.call_args_list[0].args[0]
        state = json.loads((work / "status.json").read_text())
        self.assertEqual(state["completed"], ["host"])
        self.assertIn("guest failed", state["error"])


if __name__ == "__main__":
    unittest.main()
