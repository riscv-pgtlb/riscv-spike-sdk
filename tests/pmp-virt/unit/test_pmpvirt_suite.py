import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("pmpvirt_suite_tests", ROOT / "tests/pmp-virt/regression/run-suite.py")
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)


def syscall_output():
    lines = list(suite.SYSCALL_SUMMARIES[:2])
    for round in range(1, 4):
        for name, cause in (("ordinary-data-store-control", 0), ("HS-data-page-execute", 1),
                            ("kernel-text-store", 7), ("kernel-rodata-store", 7)):
            lines.append(f"SYSCALL-ATTACK PASS {name} round={round} cause={cause} bytes=unchanged")
    lines.append(suite.SYSCALL_SUMMARIES[2])
    return "\n".join(lines)


def same_page():
    return "\n".join((
        "PASS U execute before HS probe: value=42 VA=0x1234",
        "PASS HS denied same physical page: PA=0x90001000 cause=1",
        "PASS U execute after HS probe: value=42", suite.USER_PASS, syscall_output(), suite.HOST_PASS))


def transcript():
    lines = ["PMP.Virt SEALED: text=[0x80202000,0x81000000)", "PMP.Virt seal acknowledged"]
    for name, cause in (("HS RAM execute", 1), ("text writable alias", 7), ("rodata writable alias", 7)):
        lines += [f"PMP.Virt TEST PASS before {name} cause=0 pc=123",
                  f"PMP.Virt TEST PASS after {name} cause={cause} pc=123"]
    for phase in ("before seal", "after seal"):
        lines += [f"PMP.Virt SBI GUARD PASS {phase} {name} probe=0 error=-2 buffer=unchanged"
                  for name in suite.GUARDS]
    lines += [same_page(), "VIRT-REGRESSION HOST BEFORE PASS",
              "VIRT-REGRESSION GUEST PASS", "VIRT-REGRESSION GUEST SHUTDOWN",
              "VIRT-REGRESSION GUEST RETURNED", same_page(),
              "VIRT-REGRESSION HOST AFTER PASS", "VIRT-REGRESSION ALL PASS"]
    return "\n".join(lines) + "\n"


class SuiteResultChecks(unittest.TestCase):
    def test_syscalls_require_all_operations_correct_causes_and_both_phases(self):
        original = transcript()
        for phase in (0, 1):
            parts = original.split(syscall_output())
            for line in syscall_output().splitlines():
                for changed in ("", "# echo " + line, line + "\n" + line,
                                line.replace("cause=7", "cause=15")):
                    if changed == line:
                        continue
                    with self.subTest(phase=phase, line=line, changed=changed):
                        changed_output = syscall_output().replace(line, changed)
                        text = (parts[0] + (changed_output if phase == 0 else syscall_output())
                                + parts[1] + (changed_output if phase == 1 else syscall_output()) + parts[2])
                        results = suite.runtime_results(text)
                        self.assertFalse(results["host_before" if phase == 0 else "host_after"])
                        self.assertTrue(results["host_after" if phase == 0 else "host_before"])

    def test_syscall_failure_overrides_final_success(self):
        for marker in ("SYSCALL-API FAIL", "SYSCALL-ATTACK FAIL"):
            self.assertFalse(suite.runtime_results(transcript() + marker + "\n")["runtime"])

    def test_server_versions_are_required_on_both_host_checks_and_guest(self):
        versions = {"host": "a" * 64, "guest": "b" * 64}
        results = suite.runtime_results(transcript(), expected_versions=versions)
        self.assertFalse(results["host_before"])
        self.assertFalse(results["host_after"])
        self.assertFalse(results["guest"])
        text = transcript().replace(same_page(), f"VIRT TOOLS VERSION PASS role=host version={versions['host']}\n" + same_page())
        text = text.replace("VIRT-REGRESSION GUEST PASS",
                            f"check-virt-tools[145]: VIRT TOOLS VERSION PASS role=guest version={versions['guest']}\nVIRT-REGRESSION GUEST PASS")
        self.assertTrue(all(suite.runtime_results(text, expected_versions=versions).values()))
        self.assertFalse(suite.runtime_results(text.replace("version=" + "b" * 64, "version=" + "c" * 64),
                                              expected_versions=versions)["guest"])

    def test_authentication_failure_explains_unstarted_guest_tests(self):
        info = suite.failure_info("Debian root authentication failed")
        self.assertEqual(info["code"], "AUTH_REJECTED")
        self.assertIn("未执行", info["reason"])
        self.assertIn("登录被拒绝", info["blocked"])
        self.assertTrue(any("同一组磁盘" in action for action in info["actions"]))

    def test_interrupt_and_protection_failure_have_distinct_diagnostics(self):
        self.assertEqual(suite.failure_info("Interrupted")["code"], "INTERRUPTED")
        self.assertEqual(suite.failure_info("runtime failed", "PMP.Virt TEST FAIL")["code"], "RUNTIME_FAILURE")

    def test_missing_suite_suggests_updating_tools(self):
        info = suite.failure_info("Runtime did not finish", "/usr/local/bin/test-virt-debian-all: No such file or directory")
        self.assertEqual(info["code"], "HOST_SUITE_MISSING")
        self.assertTrue(any("make debian-update" in action for action in info["actions"]))

    def test_existing_results_are_split_into_cases(self):
        self.assertTrue(all(suite.runtime_results(transcript()).values()))

    def test_kernel_timestamps_and_nested_service_prefixes(self):
        text = transcript().replace("VIRT-REGRESSION GUEST PASS", "check-virt-guest[154]: VIRT-REGRESSION GUEST PASS")
        text = text.replace("VIRT-REGRESSION GUEST SHUTDOWN", "echo[187]: VIRT-REGRESSION GUEST SHUTDOWN")
        text = "\r\r\n".join("[   30.123456] " + line for line in text.splitlines())
        self.assertTrue(all(suite.runtime_results(text).values()))

    def test_echoes_do_not_count_as_results(self):
        text = "\n".join("# echo " + line for line in transcript().splitlines())
        self.assertFalse(any(suite.runtime_results(text).values()))

    def test_wrong_exception_cause_fails_individual_case(self):
        text = transcript().replace("after text writable alias cause=7", "after text writable alias cause=15")
        self.assertFalse(suite.runtime_results(text)["hs_text"])

    def test_duplicate_guard_does_not_replace_missing_interface(self):
        text = transcript().replace("before seal PMU ", "before seal CPPC ")
        self.assertFalse(suite.runtime_results(text)["sbi_before"])

    def test_post_guest_requires_fresh_same_page_probe(self):
        text = transcript()
        start = text.index("VIRT-REGRESSION GUEST RETURNED")
        text = text[:start] + text[start:].replace(same_page(), "")
        results = suite.runtime_results(text)
        self.assertTrue(results["host_before"])
        self.assertFalse(results["host_after"])

    def test_failure_marker_overrides_all_pass(self):
        self.assertFalse(suite.runtime_results(transcript() + "PMP.Virt TEST FAIL\n")["runtime"])

    def test_missing_checks_are_skipped_in_failed_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            report = suite.Suite(Path(directory), "debian")
            with contextlib.redirect_stdout(io.StringIO()):
                report.mark("static", "FAIL", "test failure")
                report.error = "test failure"
                self.assertFalse(report.finish())
            result = json.loads((Path(directory) / "result.json").read_text())
            self.assertEqual(next(case for case in result["cases"] if case["id"] == "host_after")["status"], "SKIP")
            self.assertEqual(result["diagnostics"]["code"], "STATIC_FAILURE")


class SuiteLoginChecks(unittest.TestCase):
    def test_redacts_secret_across_every_chunk_boundary(self):
        text = "prefix 密码secret suffix"
        for cut in range(len(text) + 1):
            redactor = suite.Redactor("密码secret")
            safe = redactor.feed(text[:cut]) + redactor.feed(text[cut:]) + redactor.feed("", final=True)
            self.assertEqual(safe, "prefix [REDACTED] suffix")

    def test_password_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "password"
            path.write_text("test-secret\n")
            path.chmod(0o600)
            self.assertEqual(suite.read_password(path), "test-secret")
            path.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "chmod 600"):
                suite.read_password(path)

    def run_fake_console(self, exit_code=0, terminal_controls=False, expected_versions=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        folder = Path(directory.name)
        fake = folder / "console.py"
        fake.write_text(
            "import re, sys\n"
            "print('debian-host login: ', end='', flush=True)\n"
            "assert input() == 'root'\n"
            "print('\\nPassword: ', end='', flush=True)\n"
            "password = input()\n"
            "print(password, flush=True)\n"
            f"print({(chr(27) + '[?2004h' if terminal_controls else '') + 'root@debian-host:~# '!r}, end='', flush=True)\n"
            "command = input()\n"
            "print()\n"
            "assert 'test-virt-debian-all /dev/vdb' in command\n"
            f"assert not {bool(expected_versions)!r} or 'check-virt-tools --role host --expect-version' in command\n"
            f"assert not {bool(expected_versions)!r} or {(' ' + expected_versions['host'] + ' ' + expected_versions['guest']) if expected_versions else ''!r} in command\n"
            "assert 'systemctl poweroff' in command\n"
            f"print({transcript()!r}, end='')\n"
            f"print(re.search(r'PMPVIRT-SUITE-EXIT-[a-f0-9]+', command).group() + ' {exit_code}')\n")
        log = folder / "console.log"
        text, error = suite.run_debian([sys.executable, "-u", str(fake)], dict(os.environ),
                                      "test-secret", log, 5, expected_versions=expected_versions)
        self.assertNotIn("test-secret", log.read_text())
        self.assertIn("[REDACTED]", log.read_text())
        return text, error

    def test_console_login_suite_exit_and_password_redaction(self):
        text, error = self.run_fake_console()
        self.assertIsNone(error)
        self.assertTrue(all(suite.runtime_results(text).values()))

    def test_all_pass_output_cannot_override_nonzero_exit(self):
        _, error = self.run_fake_console(exit_code=1)
        self.assertIsNotNone(error)

    def test_login_driver_passes_both_server_versions(self):
        _, error = self.run_fake_console(expected_versions={"host": "a" * 64, "guest": "b" * 64})
        self.assertIsNone(error)

    def test_debian_bracketed_paste_prompt_starts_suite(self):
        text, error = self.run_fake_console(terminal_controls=True)
        self.assertIsNone(error)
        self.assertTrue(all(suite.runtime_results(text).values()))

    def test_actual_interrupted_console_has_recognizable_root_prompt(self):
        # Bash enables bracketed paste immediately before printing its prompt.
        text = '\x1b[!p\x1b]104\x07\x1b[?7h\r\n\x1b[?2004hroot@debian-host:~# '
        self.assertRegex(suite.terminal_text(text), r'(?:^|\n)root@[^\n]*#\s*$')

    def test_timeout_stops_console_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "console.log"
            _, error = suite.run_debian([sys.executable, "-c", "import time; time.sleep(30)"],
                                        dict(os.environ), "test-secret", log, 0.1)
            self.assertIn("timed out", error)


if __name__ == "__main__":
    unittest.main()
