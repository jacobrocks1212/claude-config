# Baselines for lazy-state.py / bug-state.py characterization tests

## Cross-platform normalization (shared)

Both `*-test-baseline.txt` files are compared via the shared
`_normalize_smoke_output()` helper in `test_lazy_core.py`. The `--test` harnesses use
`tempfile.TemporaryDirectory()` (random suffix per run) and emit OS-specific absolute
temp paths (`/tmp/claude-1000/…` on Linux/WSL, `C:\Users\…\Temp\…` on Windows). The
helper canonicalizes all three platform-volatile elements — the random `…-fixtures-<suffix>`
suffix → `…-fixtures-XXXXXXXX`, the temp-root prefix → `<TMP>/`, and `\`-vs-`/` separators →
`/` — so a single committed baseline is **platform-neutral across Windows and WSL**.
`test_normalize_smoke_output_is_platform_neutral` pins that property. **Regenerate a baseline
ONLY by piping live `--test` output through `_normalize_smoke_output` — never hand-edit it**,
or byte-identity breaks subtly on the temp-path line.

## Files

### `lazy-state-test-baseline.txt`
Normalized stdout+stderr from `python3 lazy-state.py --test`. This is a stable contract:
the smoke harness tests built-in fixture scenarios, so this output should NOT change across
refactors — if it does (`test_lazy_state_test_output_matches_baseline` fails with a unified
diff), the refactor introduced a behavior change. See the cross-platform normalization note
above.

### `bug-state-test-baseline.txt`
Normalized stdout+stderr from `python3 bug-state.py --test` — the bug-pipeline twin of
`lazy-state-test-baseline.txt`. `test_bug_state_test_output_matches_baseline` pins it
byte-for-byte (after `_normalize_smoke_output`), so any change to `bug-state.py`'s computed
state that shifts a fixture outcome is caught as a behavior change. The bug harness emits no
temp paths in practice, so its normalized output is naturally platform-neutral. Regenerate via
the shared helper after intentionally adding/changing a smoke fixture.

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

### `bug-state-algobooth.json`
Stdout JSON from `python3 bug-state.py --repo-root C:\Users\Jacob\repos\AlgoBooth`
captured at session time on a **Windows host** (host-specific absolute paths; the
`--repo-root` value will differ on Linux/WSL). This is a **same-session reference
snapshot**, not a permanent contract. The AlgoBooth bug tree evolves (bugs fixed,
new bugs queued), so this JSON will legitimately drift as bugs are triaged,
archived, or added. Regenerate by running:

    python3 user/scripts/bug-state.py --repo-root "C:\Users\Jacob\repos\AlgoBooth" \
        > user/scripts/tests/baselines/bug-state-algobooth.json

after any AlgoBooth state change that shifts the active bug or queue. The
`test_bug_state_algobooth_baseline_wellformed` test in `test_lazy_core.py`
asserts **structural well-formedness only** (JSON parses + core keys present:
`feature_id`, `current_step`, `sub_skill`, `terminal_reason`, `diagnostics`,
`operator_deferred`) — it does NOT assert exact values, so it stays green as the
AlgoBooth bug tree drifts.
