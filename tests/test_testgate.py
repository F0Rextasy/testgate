"""Contract tests for testgate. Run: python -m unittest discover -s tests -v

Every test drives the real CLI against fixture projects and asserts the exit
code and reported findings a consumer would observe -- nothing internal.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "testgate.py")
EXAMPLES = os.path.join(ROOT, "examples")


def run_cli(*args):
    proc = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestgateContract(unittest.TestCase):
    def test_vacuous_fixture_fails_with_named_rules(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "vacuous"), "--no-color")
        self.assertEqual(code, 1, out)
        for rule in ("tautology", "empty-test", "no-assertion", "test-off",
                     "conditional-assert"):
            self.assertIn(rule, out)
        self.assertIn("4 failures, 1 warning", out)
        self.assertIn("5 tests", out)

    def test_clean_fixture_passes(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "clean"), "--no-color")
        self.assertEqual(code, 0, out)
        self.assertIn("clean", out)
        self.assertIn("2 tests", out)

    def test_json_reports_structure(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "vacuous"), "--format", "json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["counts"], {"fail": 4, "warn": 1, "suppressed": 0})
        self.assertEqual(data["scanned"]["tests"], 5)
        lines = sorted(f["line"] for f in data["findings"])
        self.assertEqual(lines, [2, 5, 9, 13, 18])
        for f in data["findings"]:
            self.assertIn("suggestion", f)

    def test_escape_hatch_suppresses_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test_x.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("def test_truth():\n"
                         "    assert True  # testgate: allow -- demo fixture\n")
            code, out, _ = run_cli(tmp, "--no-color")
        self.assertEqual(code, 0, out)
        self.assertIn("clean", out)
        self.assertIn("1 exempt by 'testgate: allow'", out)

    def test_warn_only_passes_default_and_fails_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test_gated.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("def test_gated():\n"
                         "    if CI_ENABLED:\n"
                         "        assert compute() == 1\n")
            code, out, _ = run_cli(tmp, "--no-color")
            self.assertEqual(code, 0, out)
            self.assertIn("conditional-assert", out)
            code, out, _ = run_cli(tmp, "--no-color", "--strict")
            self.assertEqual(code, 1, out)

    def test_no_tests_found_warns_and_strict_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli(tmp, "--no-color")
            self.assertEqual(code, 0, out)
            self.assertIn("no-tests-found", out)
            code, out, _ = run_cli(tmp, "--no-color", "--strict")
            self.assertEqual(code, 1, out)

    def test_single_file_argument_works(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "vacuous",
                                            "test_theater.py"), "--no-color")
        self.assertEqual(code, 1, out)
        self.assertIn("4 failures", out)

    def test_discovery_skips_virtualenvs(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "venv", "lib"))
            with open(os.path.join(tmp, "venv", "lib", "test_bad.py"), "w",
                      encoding="utf-8") as fh:
                fh.write("def test_bad():\n    assert True\n")
            with open(os.path.join(tmp, "test_root.py"), "w",
                      encoding="utf-8") as fh:
                fh.write("def test_root():\n    assert compute() == 1\n")
            code, out, _ = run_cli(tmp, "--no-color")
        self.assertEqual(code, 0, out)  # the venv copy must not be scanned
        self.assertIn("clean", out)


if __name__ == "__main__":
    unittest.main()
