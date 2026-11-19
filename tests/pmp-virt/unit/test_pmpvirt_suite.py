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
from unittest.mock import patch

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


VS_HS_EVIDENCE = (
    "PMP.Virt VS BEFORE PASS: GPA=0000000081000000 result=42",
    " Info: PMP.Virt VS/HS BEGIN: GPA=0x81000000 HPA=0x90001000 cause=1",
    "PMP.Virt VS AFTER PASS: GPA=0000000081000000 result=42",
    " Info: PMP.Virt VS/HS COMPLETE: GPA=0x81000000 HPA=0x90001000 guest_report=42",
    "PMP.Virt VS-HS-VS SAME-PAGE PASS: GPA=0000000081000000",
)

def transcript():
    lines = ["PMP.Virt SEALED: text=[0x80202000,0x81000000)", "PMP.Virt seal acknowledged"]
    for name, cause in (("HS RAM execute", 1), ("text writable alias", 7), ("rodata writable alias", 7)):
        lines += [f"PMP.Virt TEST PASS before {name} cause=0 pc=123",
                  f"PMP.Virt TEST PASS after {name} cause={cause} pc=123"]
    for phase in ("before seal", "after seal"):
        lines += [f"PMP.Virt SBI GUARD PASS {phase} {name} probe=0 error=-2 buffer=unchanged"
                  for name in suite.GUARDS]
    lines += [same_page(), "VIRT-REGRESSION HOST BEFORE PASS",
              *VS_HS_EVIDENCE, "VIRT-REGRESSION GUEST PASS", "VIRT-REGRESSION GUEST SHUTDOWN",
              "VIRT-REGRESSION GUEST RETURNED", same_page(),
              "VIRT-REGRESSION HOST AFTER PASS", "VIRT-REGRESSION ALL PASS"]
    return "\n".join(lines) + "\n"


class SuiteResultChecks(unittest.TestCase):
    def test_success_output_has_padded_numbers_counts_duration_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(suite.time, "monotonic", return_value=10):
                report = suite.Suite(folder, "debian")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch.object(suite.time, "monotonic", return_value=22.5):
                report.report_case(report.cases[0], "RUN", report.cases[0]["name"])
                for case in report.cases:
                    report.mark(case["id"], "PASS", "internal evidence.log")
                self.assertTrue(report.finish())
            text = output.getvalue()
            self.assertIn("[TEST 01] [PASS] SDK 单元测试", text)
            self.assertIn("[TEST 11] [PASS] VS–HS–VS 同物理页执行权限对照", text)
            self.assertIn("[TEST 17] [PASS] 测试命令与 QEMU 正常退出", text)
            self.assertNotIn("internal evidence.log", text)
            footer = f"结果：PASS（17/17）\n耗时：12.50 秒\n证据目录：{folder}\n"
            self.assertTrue(text.endswith(footer))
            self.assertTrue((folder / "summary.txt").read_text().endswith(footer))
            state = json.loads((folder / "result.json").read_text())
            self.assertEqual(state["counts"], {"total": 17, "passed": 17, "failed": 0, "skipped": 0})
            self.assertEqual(state["cases"][0]["detail"], "internal evidence.log")

    def test_failure_footer_keeps_actual_counts_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            report = suite.Suite(Path(directory), "debian")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                report.mark("static", "FAIL", "unit failure")
                report.error = "unit failure"
                self.assertFalse(report.finish())
            text = output.getvalue()
            self.assertIn("失败阶段：", text)
            self.assertIn("结果：FAIL（0/17）", text)
            state = json.loads((Path(directory) / "result.json").read_text())
            self.assertEqual(state["counts"]["failed"], 1)
            self.assertEqual(state["counts"]["skipped"], 16)
            self.assertEqual(len(re.findall(r"\[TEST \d{2}\]", text)), 17)

    def test_vs_hs_raw_carriage_return_between_result_and_host_printk(self):
        host = ("[   40.193687] PMP.Virt USER PTE: flags=247168eb required=b user=0 write=0\n"
                "[   40.194100] PMP.Virt TEST PASS guest BEGIN same-page HS RX/U0 execute cause=1 pc=ff2000000008d000 tval=ff2000000008d000\n"
                "[   40.194386] PMP.Virt GUEST HOST CHECK: phase=0 HPA=90001000 cause=1")
        for stage in (0, 2, 4):
            original = VS_HS_EVIDENCE[stage]
            raw = transcript().replace(original, original + "\r" + host)
            with self.subTest(stage=stage):
                self.assertTrue(suite.runtime_results(raw)["vs_hs"])
                bad = raw.replace("result=42", "result=0") if stage != 4 else raw.replace(
                    VS_HS_EVIDENCE[4], VS_HS_EVIDENCE[4].replace("81000000", "82000000"))
                self.assertFalse(suite.runtime_results(bad)["vs_hs"])

    def test_vs_hs_known_host_printk_interleaving_is_reassembled(self):
        original = VS_HS_EVIDENCE[0]
        injected = (original[:original.index("result")] + "re"
                    "[   35.146279] PMP.Virt USER PTE: flags=2491a0eb required=b user=0 write=0\n"
                    "[   35.146563] PMP.Virt TEST PASS guest BEGIN same-page HS RX/U0 execute cause=1 pc=ff2000000008d000 tval=ff2000000008d000\n"
                    "[   35.146833] PMP.Virt GUEST HOST CHECK: phase=0 HPA=90001000 cause=1\n"
                    "sult=42")
        text = transcript().replace(original, injected)
        self.assertTrue(suite.runtime_results(text)["vs_hs"])
        for bad in (injected.replace("sult=42", "sult=0"),
                    injected.replace("sult=42", ""),
                    injected.replace("PMP.Virt USER PTE:", "unknown output:"),
                    injected.replace("cause=1 pc=", "cause=12 pc=")):
            with self.subTest(bad=bad):
                self.assertFalse(suite.runtime_results(transcript().replace(original, bad))["vs_hs"])

    def test_vs_hs_missing_each_phase_is_rejected(self):
        for line in VS_HS_EVIDENCE:
            with self.subTest(line=line):
                self.assertFalse(suite.runtime_results(transcript().replace(line, ""))["vs_hs"])

    def test_vs_hs_wrong_addresses_and_results_are_rejected(self):
        for old, new in (
            (VS_HS_EVIDENCE[1], VS_HS_EVIDENCE[1].replace("81000000", "82000000")),
            (VS_HS_EVIDENCE[2], VS_HS_EVIDENCE[2].replace("81000000", "82000000")),
            (VS_HS_EVIDENCE[3], VS_HS_EVIDENCE[3].replace("90001000", "90002000")),
            (VS_HS_EVIDENCE[4], VS_HS_EVIDENCE[4].replace("81000000", "82000000")),
            ("cause=1", "cause=12"), ("guest_report=42", "guest_report=0"),
        ):
            with self.subTest(new=new):
                self.assertFalse(suite.runtime_results(transcript().replace(old, new))["vs_hs"])

    def test_vs_hs_duplicates_and_wrong_order_are_rejected(self):
        text = transcript()
        self.assertFalse(suite.runtime_results(text.replace(VS_HS_EVIDENCE[1],
                         VS_HS_EVIDENCE[1] + "\n" + VS_HS_EVIDENCE[1]))["vs_hs"])
        text = text.replace(VS_HS_EVIDENCE[0], "PLACEHOLDER").replace(
            VS_HS_EVIDENCE[2], VS_HS_EVIDENCE[0]).replace("PLACEHOLDER", VS_HS_EVIDENCE[2])
        self.assertFalse(suite.runtime_results(text)["vs_hs"])

    def test_vs_hs_failure_and_unavailable_host_override_pass(self):
        for failure in ("PMP.Virt VS-HS-VS FAIL: BEGIN error=-2 value=0",
                        "Kernel panic - not syncing", "PMP.Virt TEST FAIL host probe"):
            self.assertFalse(suite.runtime_results(transcript() + failure + "\n")["vs_hs"])
        old = transcript()
        for line in VS_HS_EVIDENCE:
            old = old.replace(line, "")
        self.assertFalse(suite.runtime_results(old)["vs_hs"])

    def test_vs_hs_evidence_outside_guest_window_is_rejected(self):
        text = transcript()
        for line in VS_HS_EVIDENCE:
            text = text.replace(line, "")
        text = "\n".join(VS_HS_EVIDENCE) + "\n" + text
        self.assertFalse(suite.runtime_results(text)["vs_hs"])

    def test_vs_hs_must_finish_before_guest_success(self):
        text = transcript().replace(VS_HS_EVIDENCE[4], "")
        text = text.replace("VIRT-REGRESSION GUEST PASS",
                            "VIRT-REGRESSION GUEST PASS\n" + VS_HS_EVIDENCE[4])
        self.assertFalse(suite.runtime_results(text)["vs_hs"])

    def test_vs_hs_follows_host_before_and_precedes_guest_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            cases = suite.Suite(Path(directory), "debian").cases
        self.assertEqual(len(cases), 17)
        self.assertEqual(next(c["number"] for c in cases if c["id"] == "shutdown"), 17)
        self.assertEqual(next(c["number"] for c in cases if c["id"] == "vs_hs"), 11)

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

    def test_guest_panic_is_not_misclassified_by_unrelated_missing_file(self):
        text = ("# test-virt-debian-all /dev/vdb\n"
                "systemd: optional.conf: No such file or directory\n"
                "PMP.Virt GUEST PROBE PAGE: GPA=0x82eeb000\n"
                "Oops [#1]\nKernel panic - not syncing\n")
        info = suite.failure_info("Protection failure or kernel panic", text)
        self.assertEqual(info["code"], "RUNTIME_FAILURE")
        self.assertNotIn("套件不可用", info["blocked"])

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
