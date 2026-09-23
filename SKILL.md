---
name: testgate
description: Finds tests that cannot fail. Use when reviewing a test suite, after writing tests, or whenever a suite looks suspiciously green -- empty test bodies, missing assertions, assert True tautologies, skip-disabled tests, and assertions hidden behind if-guards all fail scripts/testgate.py so theater tests cannot land.
license: MIT
compatibility: Requires Python 3.8+. Runs in Claude Code, Codex, Cursor, and any Agent Skills compatible client.
metadata:
  author: F0Rextasy
  version: "1.0"
---

# testgate

A test that cannot fail is worse than no test: it produces the green check
that stops anyone from looking. Theater tests are how "all tests pass"
ends up meaning nothing.

## The one rule

You may not add a test until it can fail, and you may not report a green
suite over a non-zero gate:

```bash
python scripts/testgate.py path/to/tests
```

Exit 0 means every discovered test can actually go red. Exit 1 means the
suite contains theater: read each finding, fix or delete, re-run.

## Protocol

### 1. Write the assertion first

Decide what result would prove the behavior works. Then arrange the code
that produces it. A body that only calls the code under test is an
experiment, not a test — name it a smoke script or give it an assertion.

### 2. Common traps this gate rejects

| Trap | Why the suite stays green | Fix |
| --- | --- | --- |
| `assert True` / `assert x == x` | cannot fail under any input | assert the produced value |
| no assertion at all | wrong output that doesn't crash passes | check the result |
| `@pytest.mark.skip` | the test never runs | fix what it hides, or delete it |
| `if CI_ENABLED:` wrapping the only assert | CI takes the unguarded path | assert unconditionally |
| non-strict `@pytest.mark.xfail` | red or blue, never red | `strict=True` or fix the bug |

### 3. Gate your own tests

```bash
python scripts/testgate.py tests/ --strict
```

An intentional exception is justified on the line itself:

```python
def test_boot():  # testgate: allow -- smoke check, assertions live in test_boot_full
    run_boot()
```

### 4. Report back

1. **Suite** — how many test files and tests were scanned.
2. **Findings** — each rule, file:line, and the fix applied (or "clean").
3. **Evidence** — the exact command and its exit 0.

Never write "the tests pass" without those three lines — and never write it
about tests this gate would reject.
