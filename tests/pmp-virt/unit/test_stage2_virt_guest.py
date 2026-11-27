#!/usr/bin/env python3
"""Validate strict Stage2Virt Guest VU-VS-VU evidence checking."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "tests/G-stage-virt/check-stage2-virt-guest.sh"
GPA = "0x0000000082000000"
EVIDENCE = (
    f"Stage2Virt Guest VU BEFORE PASS: GPA={GPA} value=0x5a",
    f"Stage2Virt Guest VS PROBE PASS: GPA={GPA} expected-access-fault",
    f"Stage2Virt Guest VU AFTER PASS: GPA={GPA} value=0xa5",
    f"Stage2Virt Guest VU-VS-VU SAME-PAGE PASS: GPA={GPA}",
)


class Stage2VirtGuestChecker(unittest.TestCase):
    def run_checker(self, lines, exit_code=0):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "stage2-virt-guest-test"
            body = "#!/bin/sh\n" + "\n".join(
                "printf '%s\\n' " + repr(line) for line in lines)
            body += f"\nexit {exit_code}\n"
            binary.write_text(body)
            binary.chmod(0o755)
            environment = dict(os.environ,
                               STAGE2_VIRT_GUEST_TEST=str(binary),
                               STAGE2_VIRT_GUEST_DEVICE="/dev/null")
            return subprocess.run(["sh", str(CHECKER)], env=environment,
                                  text=True, capture_output=True)

    def test_complete_ordered_same_gpa_evidence_passes(self):
        result = self.run_checker(EVIDENCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Linux Guest Stage2Virt VU-VS-VU runtime test PASS",
                      result.stdout)

    def test_missing_reordered_mismatched_or_duplicate_evidence_fails(self):
        bad_cases = (
            EVIDENCE[:-1],
            (EVIDENCE[1], EVIDENCE[0], *EVIDENCE[2:]),
            (*EVIDENCE[:2], EVIDENCE[2].replace("82000000", "83000000"), EVIDENCE[3]),
            (EVIDENCE[0], EVIDENCE[0], *EVIDENCE[1:]),
        )
        for lines in bad_cases:
            with self.subTest(lines=lines):
                self.assertNotEqual(self.run_checker(lines).returncode, 0)

    def test_test_binary_failure_is_not_accepted(self):
        result = self.run_checker(EVIDENCE, exit_code=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("runtime test PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
