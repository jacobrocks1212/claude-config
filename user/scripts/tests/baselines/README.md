# Baselines for lazy-state.py characterization tests

## Files

### `lazy-state-test-baseline.txt`
Verbatim stdout+stderr from `python3 lazy-state.py --test` captured at the time
the characterization test suite was written (WU-1.1). This is a stable contract:
the smoke harness tests built-in fixture scenarios, so this output should NOT
change across refactors — if it does, the refactor introduced a behavior change.

**Volatile-path normalization:** `lazy-state.py --test` uses
`tempfile.TemporaryDirectory()` internally, which generates a random suffix on
every run (e.g. `lazy-state-fixtures-prt8wzde`).  The baseline replaces that
suffix with the stable placeholder `lazy-state-fixtures-XXXXXXXX`.  The test
`test_lazy_state_test_output_matches_baseline` in `test_lazy_core.py` applies
the same substitution (`re.sub(r"lazy-state-fixtures-[A-Za-z0-9_]+", ...)`) to
the live output before diffing, ensuring the comparison is deterministic across
runs even though the actual temp-dir name varies.

### `lazy-state-algobooth.json`
Stdout JSON from `python3 lazy-state.py --repo-root /home/jacob/repos/AlgoBooth`
captured at session time. This is a **same-session safety net**, not a permanent
contract. The AlgoBooth feature tree evolves (features complete, new features
queue), so this JSON will legitimately drift. Regenerate by running:

    python3 user/scripts/lazy-state.py --repo-root /home/jacob/repos/AlgoBooth \
        > user/scripts/tests/baselines/lazy-state-algobooth.json

after any AlgoBooth state change that shifts the current step. The
`test_lazy_core.py` harness deliberately does NOT use this file in assertions
(pure-function inputs only) — it is kept here as a human-readable reference
snapshot only.
