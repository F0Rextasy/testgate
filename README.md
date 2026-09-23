# testgate

**A test that cannot fail is worse than no test.** testgate finds the tests
that can't fail: empty bodies, missing assertions, tautologies (`assert
True`, `assert x == x`), skip-disabled tests, and assertions hiding behind
an `if`. One command per gate — run it before every release.

## Why this exists

CI is green, the badge is green, everyone stops looking. But nobody checked
whether the tests could *ever* go red. testgate is a four-part quality-gate
family for agent and human work:

| Gate | Catches |
| --- | --- |
| **preflight** | `prod` in debug, `example.com` URLs, wildcard CORS, flat `requirements` |
| **prove-it** | claims (`all tests pass`) with no executed command + exit code behind them |
| **testgate** | tests that can never fail - the green that proves nothing |
| testgate: finds the tests that cannot fail *(this repo)* |

Copies the family contract: one Python script, zero dependencies, exit 0 =
clean, 1 = theater found, 2 = usage error, `--strict` also fails warnings.

## Install

Single script, stdlib only (Python 3.8+). Vendor it or run in place:

```bash
cp scripts/testgate.py your-repo/scripts/
python scripts/testgate.py tests/
```

Or as an Agent Skill:

```
/testgate  # in Claude Code, Codex, Cursor, or any Agent Skills client
```

## Usage

```console
$ python scripts/testgate.py tests/
app/test_api.py
  L41   FAIL  no-assertion        executes code but never checks a result
  L87   WARN  conditional-assert  every assertion sits under an if -- ...

testgate: 1 failure, 1 warning across 42 tests in 3 files (0 exempt by 'testgate: allow')
testgate: fix the test -- or justify one line with:  # testgate: allow -- <reason>
[exit 1]
```

Point it at a project root or a single file. A single-file invocation
bypasses the `test_*` name filter. Recursive discovery skips `.git`,
`venv`, `node_modules`, `build`, `dist`, `site-packages` and friends.
`--format json` emits the machine-readable findings; `--strict` also fails
on warnings.

## The rules

| Rule | Severity | Finds |
| --- | --- | --- |
| `empty-test` | fail | body is only `pass`/docstring |
| `no-assertion` | fail | runs code, checks nothing |
| `tautology` | fail | assertion that cannot be false (`assert True`, `assert x == x`) |
| `test-off` | fail | unconditionally skip-disabled (`@skip`, `@skipIf(True)`) |
| `conditional-assert` | warn | every check sits under an `if` - the unguarded path passes silently |
| `expected-fail` | warn | non-strict `@xfail`, which can never go red |
| `unparseable` | warn | file does not parse - the runner will error on it |
| `no-tests-found` | warn | no test files under the path at all |

Full catalogue with trade-offs: [references/RULES.md](references/RULES.md).

One finding chain per test: empty > off > tautologies > no-assertion. A
skip-disabled test reports the skip, not the missing assertion — the skip
is the actionable truth.

Detection is syntactic: an `ast.Assert`, a call whose name starts with
`assert`, or a known verification call (`raises`, `warns`, `fail`, mock's
`assert_called*` family). Nothing is imported, nothing runs.

An intentionally vacuous test (smoke checks, tracing stubs) is justified on
the line the rule points at:

```python
def test_boot():  # testgate: allow -- smoke check; full suite in test_boot_full
    run_boot()
```

Exemptions stay visible: `(1 exempt by 'testgate: allow')` in every
summary.

## Evidence (real outputs)

Vacuous fixture, five theater patterns:

```console
$ python scripts/testgate.py examples/vacuous --no-color
testgate/examples/vacuous\test_theater.py
  L2    FAIL  tautology            asserts a constant
  L5    FAIL  empty-test           test body is empty
  L9    FAIL  no-assertion         executes code but never checks a result
  L13   FAIL  test-off             disabled by a skip decorator
  L18   WARN  conditional-assert   every assertion sits under an if -- the unguarded path can pass silently

testgate: 4 failures, 1 warning across 5 tests in 1 file (0 exempt by 'testgate: allow')
testgate: fix the test -- or justify one line with:  # testgate: allow -- <reason>
[exit 1]
```

Clean fixture:

```console
$ python scripts/testgate.py examples/clean --no-color
testgate: clean -- 2 tests across 1 file checked, 0 findings (0 exempt by 'testgate: allow')
[exit 0]
```

Contract tests, 8 for 8:

```console
$ python -m unittest discover -s tests
........
----------------------------------------------------------------------
Ran 8 tests in 0.756s

OK
[exit 0]
```

Each test drives the real CLI against fixture projects and asserts the
observable exit code, findings, and summary — nothing internal.

## Layout

```text
testgate/
+-- scripts/testgate.py   # the gate (stdlib only, ~400 lines)
+-- SKILL.md              # Agent Skill (Claude Code / Codex / Cursor)
+-- examples/vacuous/     # fixture: all five theater patterns
+-- examples/clean/       # fixture: real tests, gates clean
+-- references/RULES.md   # rule catalogue, scope, escape hatch
+-- tests/test_testgate.py # contract tests driving the real CLI
```

## License

[MIT](LICENSE)
