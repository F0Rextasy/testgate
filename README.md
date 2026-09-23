# testgate

**Find tests that cannot fail.** Empty bodies, assertions on constants, skip-disabled tests, checks hidden under `if` - green runs that prove nothing. `testgate` statically scans your test tree and fails the build while the test theater is still in the script: milliseconds, offline, no coverage dashboard required.

[![tests](https://img.shields.io/github/actions/workflow/status/F0Rextasy/testgate/test.yml?branch=master&label=tests&style=flat-square&color=3fb950)](https://github.com/F0Rextasy/testgate/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org/)
[![skills](https://skills.sh/b/F0Rextasy/testgate?style=flat-square)](https://skills.sh/F0Rextasy/testgate)
[![license](https://img.shields.io/badge/license-MIT-3fb950?style=flat-square)](LICENSE)

![testgate finding vacuous tests](assets/demo.svg)

## Why this exists

Coverage went up, the suite stayed green, and the bug shipped anyway - the new test asserted a constant, the "disabled" one skipped on every machine, and the real check sat under `if DEBUG:` where CI never goes. Vacuous tests are worse than no tests: they buy false confidence and hide the gap behind a checkmark. `testgate` reads the AST, finds tests that have no path to red, and makes that a build failure - the same way a linter makes a syntax error one.

## Quick start

```bash
# install the skill into any agent (Claude Code, Codex, Cursor, OpenCode, ...):
npx skills add F0Rextasy/testgate

# or run it directly:
git clone https://github.com/F0Rextasy/testgate
cd myproject
python /path/to/testgate/scripts/testgate.py tests/ --strict
```

| Exit | Meaning |
| --- | --- |
| `0` | every test can fail (warnings allowed unless `--strict`) |
| `1` | findings fail the gate |
| `2` | usage error |

Point it at a project root (default `.`) or a single test file. Works on pytest/unittest-style Python out of the box; `--format json` for machines.

## How it decides

```mermaid
flowchart TD
    A["test file"] --> B["parse the AST"]
    B --> C{function is a test?}
    C -- no --> N[ignore]
    C -- yes --> R{detector rules}
    R --> F1["FAIL empty-test: body is empty"]
    R --> F2["FAIL tautology: asserts a constant"]
    R --> F3["FAIL no-assertion: runs code, checks nothing"]
    R --> F4["FAIL test-off: skip decorator disables it"]
    R --> F5["WARN conditional-assert:<br/>every assertion sits under an if"]
    F1 & F2 & F3 & F4 --> X["exit 1: blocks"]
    F5 --> S["warn only (fail with --strict)"]
```

Full rule catalogue with per-rule severity: [references/RULES.md](references/RULES.md).

## What it catches (real output)

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

A deliberate exception gets an in-place exemption that travels with the line:

```python
def test_version_constant():
    assert __version__  # testgate: allow -- version is compile-time fixed
```

## Wire it into CI

```yaml
- uses: actions/checkout@v4
- name: test theater gate
  run: python testgate/scripts/testgate.py tests/ --strict
```

Run it next to the suite: the suite says *did the tests pass?*, testgate says *could they have failed?*

## What it will never do

- Execute your tests - findings come from the AST, so a slow or side-effecting suite is scanned safely.
- Flag a test for style - only for having no path to a red result.
- Fail on a line you explicitly justified with `# testgate: allow -- <reason>`.

## One path, many gates — the family

Deterministic gates - one Python script each, stdlib, same exit contract:

| Repo | What its verdict means |
| --- | ---|
| [dsh-gate](https://github.com/F0Rextasy/dsh-gate) | the shell session actually ran - real commands, real files, real log |
| [sessionaudit](https://github.com/F0Rextasy/sessionaudit) | the session behaved - scope, secrets, destructive acts, self-contradicted claims |
| [cigate](https://github.com/F0Rextasy/cigate) | the workflows burn each minute once - pins, path filters, dedup, budget |
| [ci-triage](https://github.com/F0Rextasy/ci-triage) | one log, one verdict: regression / flaky / infra / pass |
| [docproof](https://github.com/F0Rextasy/docproof) | every README doc snippet is runnable, parsed, and verified in CI |
| [preflight](https://github.com/F0Rextasy/preflight) | the config is safe to ship - semantics, not syntax |
| [prove-it](https://github.com/F0Rextasy/prove-it) | every claim in this README is backed by real, captured output |
| [shipcheck](https://github.com/F0Rextasy/shipcheck) | the artifacts in `dist/` match `src/` - nothing stale ships |
| [testgate](https://github.com/F0Rextasy/testgate) | the tests that ran are the tests that exist - gaps, dupes, skips |
| [bandaid](https://github.com/F0Rextasy/bandaid) | the diff doesn't hide a silent failure - swallowed errors, dead guards |
| [wincompat](https://github.com/F0Rextasy/wincompat) | every path in the tree survives a Windows checkout |
| [compressproof](https://github.com/F0Rextasy/compressproof) | the context shrank without losing an answer - reversible compression, byte proof, answer-equivalence oracle |
| [uigate](https://github.com/F0Rextasy/uigate) | the UI stops looking like the same AI slop - measurable design-slop lint, WCAG + template tells |
| [aitell](https://github.com/F0Rextasy/aitell) | the prose stops reading as AI - deterministic AI-tell detection with a published confusion matrix |
| [route-drift](https://github.com/F0Rextasy/route-drift) | OpenAPI spec vs code routes drift gate |

## License

[MIT](LICENSE)
