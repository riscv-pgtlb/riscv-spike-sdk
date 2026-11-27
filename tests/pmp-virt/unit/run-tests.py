#!/usr/bin/env python3
"""Run SDK unit tests with the same itemized output as native mock tests."""
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = ROOT / "tests/pmp-virt/unit"


class ItemizedResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.item_number = 0
        self.passed = 0

    def item_description(self, test):
        parts = test.id().split(".")
        module = parts[-3].removeprefix("test_").replace("_", " ")
        case = parts[-2]
        method = parts[-1].removeprefix("test_").replace("_", " ")
        return f"{module}/{case}: {method}"

    def report(self, test, status):
        self.item_number += 1
        description = self.item_description(test)
        self.stream.writeln(
            f"[TEST {self.item_number:03d}] {description:<78} {status}")
        self.stream.flush()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed += 1
        self.report(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.report(test, "FAIL")

    def addError(self, test, err):
        super().addError(test, err)
        self.report(test, "ERROR")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.report(test, f"SKIP ({reason})")


def main():
    suite = unittest.defaultTestLoader.discover(
        str(TEST_ROOT), pattern="test_*.py")
    stream = unittest.runner._WritelnDecorator(sys.stdout)
    result = ItemizedResult(stream, descriptions=True, verbosity=0)
    result.buffer = True
    result.startTestRun()
    try:
        suite(result)
    finally:
        result.stopTestRun()
    if not result.wasSuccessful():
        result.printErrors()
    total = result.testsRun
    if result.wasSuccessful():
        print(f"[SUMMARY] {result.passed}/{total} SDK Python unit tests passed")
        return 0
    print(f"[SUMMARY] SDK Python unit tests failed: "
          f"passed={result.passed} failures={len(result.failures)} "
          f"errors={len(result.errors)} skipped={len(result.skipped)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
