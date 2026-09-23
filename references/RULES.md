# Rule catalogue

`scripts/testgate.py` parses Python test files with the standard `ast`
module. Every rule answers one question: *can this test still go red?* If
not, the suite's green check is theater.

Two severities:

- **fail** - the test cannot fail as written. Fails the gate (exit 1).
- **warn** - the test can fail, but a path to a false pass exists. Fails
  only with `--strict`.

## Fail rules

| Rule | Fires when | Example |
| --- | --- | --- |
| `empty-test` | body is only `pass`/docstring | `def test_x(): pass` |
| `no-assertion` | statements run, no check exists anywhere | `def test_x(): compute()` |
| `tautology` | the assertion cannot be false under any input | `assert True`, `assert x == x`, `assertEqual(1, 1)` |
| `test-off` | a skip decorator disables the test unconditionally | `@pytest.mark.skip`, `@skip`, `@skipIf(True, ...)` |

A check counts as: an `ast.Assert`, a call whose name starts with `assert`,
or a known verification call (`raises`, `warns`, `fail`, mock's
`assert_called*` family). One chain per test: empty > off > tautology >
no-assertion - a disabled test reports the skip, not the missing assertion.

## Warn rules

| Rule | Fires when | Why it is not fatal |
| --- | --- | --- |
| `conditional-assert` | every check sits under an `if` | platform guards exist, but CI may take the passing branch |
| `expected-fail` | `@xfail` (non-strict) | declared intent, but it can never go red |
| `unparseable` | file does not parse | the runner errors anyway; visibility only |
| `no-tests-found` | no `test_*.py` / `*_test.py` under path | an empty gate must not crash |

## Scope

- **Files**: `test_*.py` and `*_test.py`, recursive; `.git`, `venv`,
  `.venv`, `node_modules`, `build`, `dist`, `site-packages` skipped. A
  single-file argument bypasses the name filter.
- **Tests**: functions named `test_*`, module or class level, sync/async.
- **Static only**: names are never resolved, nothing is imported or run.

## Escape hatch

One justified exception, on the line the rule points at:

```python
def test_boot():  # testgate: allow -- smoke check; full suite in test_boot_full
    run_boot()
```

Counted as `suppressed` in every summary - visible, not fatal.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | clean, or only warnings without `--strict` |
| `1` | at least one fail (or any warning with `--strict`) |
| `2` | usage error - path not found or bad flags |
