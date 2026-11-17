import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("debian_targets_tests", ROOT / "scripts/debian/prepare/disk-targets.py")
targets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(targets)


class DebianTargetChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.stage = self.base / "prepared-test"
        self.stage.mkdir()
        for name in targets.NAMES:
            (self.stage / name).write_text("new " + name)

    def old_pair(self):
        for name in targets.NAMES:
            (self.base / name).write_text("old " + name)

    def test_existing_pair_rejected_by_default_without_changes(self):
        self.old_pair()
        with self.assertRaisesRegex(RuntimeError, "DEBIAN_RECREATE=1"):
            targets.publish(self.base, self.stage, False)
        self.assertEqual((self.base / targets.NAMES[0]).read_text(), "old " + targets.NAMES[0])
        self.assertEqual(list(self.base.glob("backup-*")), [])

    def test_first_creation_uses_fixed_paths(self):
        targets.publish(self.base, self.stage, False)
        for name in targets.NAMES:
            self.assertEqual((self.base / name).read_text(), "new " + name)
        self.assertEqual(list(self.base.glob("backup-*")), [])

    def test_recreation_backs_up_both_old_disks(self):
        self.old_pair()
        targets.publish(self.base, self.stage, True)
        backup, = self.base.glob("backup-*")
        for name in targets.NAMES:
            self.assertEqual((backup / name).read_text(), "old " + name)
            self.assertEqual((self.base / name).read_text(), "new " + name)

    def test_incomplete_staging_preserves_old_pair(self):
        self.old_pair()
        (self.stage / targets.NAMES[1]).unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing staged"):
            targets.publish(self.base, self.stage, True)
        self.assertEqual(list(self.base.glob("backup-*")), [])
        for name in targets.NAMES:
            self.assertEqual((self.base / name).read_text(), "old " + name)

    def test_second_publish_failure_restores_original_pair(self):
        self.old_pair()
        replace = targets.os.replace

        def fail_second(source, destination):
            if source == self.stage / targets.NAMES[1]:
                raise OSError("simulated replacement failure")
            return replace(source, destination)

        with patch.object(targets.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "replacement failed"):
                targets.publish(self.base, self.stage, True)
        for name in targets.NAMES:
            self.assertEqual((self.base / name).read_text(), "old " + name)
            self.assertEqual((self.stage / name).read_text(), "new " + name)

    def test_single_existing_disk_is_backed_up(self):
        (self.base / targets.NAMES[0]).write_text("old host")
        targets.publish(self.base, self.stage, True)
        backup, = self.base.glob("backup-*")
        self.assertEqual((backup / targets.NAMES[0]).read_text(), "old host")

    def test_symlink_target_rejected(self):
        (self.base / targets.NAMES[0]).symlink_to(self.stage / targets.NAMES[0])
        with self.assertRaisesRegex(RuntimeError, "regular disk"):
            targets.validate(self.base, True)


if __name__ == "__main__":
    unittest.main()
