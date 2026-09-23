#!/usr/bin/env python3
"""testgate -- find the tests that cannot fail.

A test suite that cannot fail is theater: it runs, it prints green, and it
proves nothing. testgate parses Python test files with the standard ast
module and reports tests that are empty, unasserted, tautological,
skip-disabled, or whose every assertion hides behind an `if`.

Exit codes: 0 clean, 1 findings fail (warnings only with --strict), 2 usage.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass

RULES = {
    # rule: (severity, suggestion)
    "empty-test": ("fail",
        "give the test a real body, or delete it"),
    "no-assertion": ("fail",
        "assert something about the result -- executing code is not checking it"),
    "tautology": ("fail",
        "compare against the value that should be produced, not against "
        "itself or a constant"),
    "test-off": ("fail",
        "remove the skip and fix what it hides, or delete the test"),
    "conditional-assert": ("warn",
        "assert on the unguarded path too -- an if can silently take the "
        "passing branch in CI"),
    "expected-fail": ("warn",
        "a non-strict xfail can never go red; use strict=True or fix the bug"),
    "unparseable": ("warn",
        "the runner will error on this file -- fix the syntax"),
    "no-tests-found": ("warn",
        "no test_*.py or *_test.py under this path"),
}

ESCAPE_RE = re.compile(r"#\s*testgate\s*:\s*allow")
TEST_NAME_RE = re.compile(r"^test_|_test$")
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", "venv",
             ".venv", "build", "dist", "site-packages", ".tox", ".eggs",
             "htmlcov", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".eggs"}
CHECK_NAMES = {"raises", "warns", "fail", "ok_", "eq_", "assert_called",
               "assert_called_once", "assert_called_with",
               "assert_called_once_with", "assert_any_call",
               "assert_not_called", "assert_awaited", "assert_awaited_once",
               "assert_not_awaited"}
TRUE_SKIP = {"skip"}
FALSE_SKIP_UNLESS = {"skipUnless"}


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    code: str
    message: str

    @property
    def severity(self) -> str:
        return RULES[self.rule][0]


def dotted(node) -> str:
    if isinstance(node, ast.Call):
        return dotted(node.func)
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return ("%s.%s" % (base, node.attr)).strip(".")
    if isinstance(node, ast.Name):
        return node.id
    return ""


def call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def is_check_call(node: ast.Call) -> bool:
    name = call_name(node)
    return name.startswith("assert") or name in CHECK_NAMES


def is_const_true(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def tautology_reason(node):
    """Return a reason string when this expression asserts nothing real."""
    if isinstance(node, ast.Constant):
        if node.value:
            return "asserts a constant"
        return None
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, right = node.left, node.comparators[0]
        if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
            return "compares two constants"
        if ast.dump(left) == ast.dump(right):
            return "compares a value with itself"
    return None


def tautology_call_reason(node: ast.Call):
    name = call_name(node)
    if not name.startswith("assert") or not node.args:
        return None
    if name == "assertTrue":
        return tautology_reason(node.args[0])
    if len(node.args) >= 2:
        a, b = node.args[0], node.args[1]
        if isinstance(a, ast.Constant) and isinstance(b, ast.Constant):
            return "compares two constants"
        if ast.dump(a) == ast.dump(b):
            return "compares a value with itself"
    return None


def is_empty_body(body) -> bool:
    meaningful = []
    for stmt in body:
        if (isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)):
            continue  # docstring
        meaningful.append(stmt)
    if not meaningful:
        return True
    return all(isinstance(s, ast.Pass) for s in meaningful)


def decorator_kind(dec):
    """Return (kind, line) for skip/xfail decorators, else (None, 0)."""
    name = dotted(dec)
    line = getattr(dec, "lineno", 0)
    if name.endswith(".skipIf") or name.endswith(".skip_if"):
        args = dec.args if isinstance(dec, ast.Call) else []
        if args and is_const_true(args[0]):
            return "off", line
        return None, 0
    if name.endswith(".skipUnless"):
        args = dec.args if isinstance(dec, ast.Call) else []
        if args and isinstance(args[0], ast.Constant) and args[0].value is False:
            return "off", line
        return None, 0
    if name in TRUE_SKIP or name.endswith(".skip"):
        return "off", line
    if name.endswith(".xfail") or name in {"xfail"}:
        return "xfail", line
    return None, 0


def analyze_test(fn, path):
    """One finding chain per test: empty > disabled > tautologies/assertion
    presence, plus independent warns."""
    findings = []

    if is_empty_body(fn.body):
        findings.append(Finding(path, fn.lineno, "empty-test",
                                "def %s" % fn.name, "test body is empty"))
        return findings

    off_line = None
    xfail_lines = []
    for dec in getattr(fn, "decorator_list", []):
        kind, line = decorator_kind(dec)
        if kind == "off":
            off_line = line
        elif kind == "xfail":
            xfail_lines.append(line)

    if off_line is not None:
        findings.append(Finding(path, off_line, "test-off",
                                dotted_call_text(fn),
                                "disabled by a skip decorator"))
        return findings

    tauts = []
    checks_total = 0
    checks_unguarded = 0

    def walk(node, if_depth):
        nonlocal checks_total, checks_unguarded
        if isinstance(node, ast.If):
            walk(node.test, if_depth)
            for child in node.body:
                walk(child, if_depth + 1)
            for child in node.orelse:
                walk(child, if_depth + 1)
            return
        if isinstance(node, ast.Assert):
            checks_total += 1
            if if_depth == 0:
                checks_unguarded += 1
            reason = tautology_reason(node.test)
            if reason:
                tauts.append((node.lineno, reason))
            elif isinstance(node.test, ast.Call):
                reason = tautology_call_reason(node.test)
                if reason:
                    tauts.append((node.lineno, reason))
        elif isinstance(node, ast.Call) and is_check_call(node):
            checks_total += 1
            if if_depth == 0:
                checks_unguarded += 1
            reason = tautology_call_reason(node)
            if reason:
                tauts.append((node.lineno, reason))
        for child in ast.iter_child_nodes(node):
            walk(child, if_depth)

    for stmt in fn.body:
        walk(stmt, 0)

    for line_no, reason in tauts:
        findings.append(Finding(path, line_no, "tautology",
                                "line %d" % line_no, reason))

    if not tauts and checks_total == 0:
        findings.append(Finding(path, fn.lineno, "no-assertion",
                                "def %s" % fn.name,
                                "executes code but never checks a result"))

    if checks_total and checks_unguarded == 0:
        findings.append(Finding(path, fn.lineno, "conditional-assert",
                                "def %s" % fn.name,
                                "every assertion sits under an if -- the "
                                "unguarded path can pass silently"))

    for line_no in xfail_lines:
        findings.append(Finding(path, line_no, "expected-fail",
                                dotted_call_text(fn),
                                "non-strict xfail can never go red"))

    return findings


def dotted_call_text(fn) -> str:
    decs = [dotted(d) for d in getattr(fn, "decorator_list", [])]
    return "@%s" % (decs[0] if decs else "test")[:100]


def discover(path):
    """Test files under path (or the single file itself)."""
    if os.path.isfile(path):
        return [path]
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if TEST_NAME_RE.match(name) is None and not name.startswith("test_"):
                continue
            if name.endswith(".py"):
                found.append(os.path.join(root, name))
    return found


def scan_with_suppression(path):
    files = discover(path)
    if not files:
        return [Finding(path, 0, "no-tests-found", path,
                        "no test_*.py or *_test.py under this path")], \
               {"files": [], "tests": 0, "suppressed": 0}
    all_findings = []
    tests = 0
    suppressed = 0
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            tree = ast.parse(source, filename=f)
        except SyntaxError as exc:
            line_no = exc.lineno or 1
            if ESCAPE_RE.search(source.splitlines()[line_no - 1]
                                if source and line_no <= len(source.splitlines())
                                else ""):
                suppressed += 1
            else:
                all_findings.append(Finding(
                    f, line_no, "unparseable", "line %d" % line_no,
                    (exc.msg or "syntax error")[:80]))
            continue
        except OSError:
            continue
        lines = source.splitlines()
        escaped = {i for i, raw in enumerate(lines, 1) if ESCAPE_RE.search(raw)}
        file_findings = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    tests += 1
                    file_findings.extend(analyze_test(node, f))
        for finding in file_findings:
            if finding.line in escaped:
                suppressed += 1
            else:
                all_findings.append(finding)
    stats = {"files": files, "tests": tests, "suppressed": suppressed}
    return all_findings, stats


def render_text(findings, stats, strict, color):
    red, yellow, bold, reset = "", "", "", ""
    if color:
        red, yellow, bold, reset = "\033[31m", "\033[33m", "\033[1m", "\033[0m"

    counts = {"fail": 0, "warn": 0}
    for f in findings:
        counts[f.severity] += 1

    out = []
    by_file = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)
    for group_file, group in by_file.items():
        out.append(bold + group_file + reset)
        for f in group:
            sev = "FAIL" if f.severity == "fail" else "WARN"
            sev_col = red if sev == "FAIL" else yellow
            out.append("  L%-4d %s%-5s%s %-20s %s"
                       % (f.line, sev_col, sev, reset, f.rule, f.message))
        out.append("")

    nf = "%d failure%s" % (counts["fail"], "" if counts["fail"] == 1 else "s")
    nw = "%d warning%s" % (counts["warn"], "" if counts["warn"] == 1 else "s")
    exempt = " (%d exempt by 'testgate: allow')" % stats["suppressed"]
    nfiles = len(stats["files"])

    if not findings:
        out.append("testgate: clean -- %d test%s across %d file%s checked, "
                   "0 findings%s"
                   % (stats["tests"], "" if stats["tests"] == 1 else "s",
                      nfiles, "" if nfiles == 1 else "s", exempt))
        return "\n".join(out)

    out.append("testgate: %s, %s across %d test%s in %d file%s%s"
               % (nf, nw, stats["tests"], "" if stats["tests"] == 1 else "s",
                  nfiles, "" if nfiles == 1 else "s", exempt))
    if counts["fail"] > 0 or (strict and counts["warn"] > 0):
        out.append(red + "testgate: fix the test -- or justify one line with:"
                     "  # testgate: allow -- <reason>" + reset)
    else:
        out.append("testgate: warnings pass by default; use --strict to "
                   "fail on them too")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="testgate",
        description="Find tests that cannot fail: empty bodies, missing "
                    "assertions, tautologies, skip-disabled tests, "
                    "if-guarded assertions. Exit 1 when findings fail.")
    ap.add_argument("path", nargs="?", default=".",
                    help="project root or a single test file (default: .)")
    ap.add_argument("--strict", action="store_true",
                    help="also fail on warnings")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        ap.error("path not found: %s" % args.path)

    findings, stats = scan_with_suppression(args.path)
    counts = {"fail": 0, "warn": 0}
    for f in findings:
        counts[f.severity] += 1
    failing = counts["fail"] > 0 or (args.strict and counts["warn"] > 0)

    if args.format == "json":
        payload = {
            "ok": not failing,
            "counts": dict(counts, suppressed=stats["suppressed"]),
            "scanned": {"files": stats["files"], "tests": stats["tests"]},
            "findings": [
                {"file": f.file, "line": f.line, "rule": f.rule,
                 "severity": f.severity, "code": f.code,
                 "message": f.message, "suggestion": RULES[f.rule][1]}
                for f in findings
            ],
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        color = (not args.no_color and sys.stdout.isatty()
                 and not os.environ.get("NO_COLOR"))
        print(render_text(findings, stats, args.strict, color))

    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
