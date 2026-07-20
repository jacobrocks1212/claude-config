# Bug: harness Python crashes on Windows under the default cp1252 codec

**Status:** Fixed
**Fixed:** 2026-07-20
**Fix commit:** 050e8426
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage; discovered Round 48, fixed Round 49); `docs/features/anti-overfit-design-gate/` (`harness-gate.py` is the mechanical over-fit floor)

## Symptom (verified)

On a stock Windows Python (no `PYTHONUTF8` / `PYTHONIOENCODING` set), `sys.stdout.encoding`
and `locale.getpreferredencoding()` are both `cp1252`. Three harness surfaces crash:

1. **`harness-gate.py`** — the anti-overfit / gate-weakening mechanical gate. Over a `git diff`
   whose output contains a byte undefined in cp1252 (e.g. `Í` = UTF-8 `C3 8D`; `0x8D` is
   unmapped in cp1252), it raises `UnicodeDecodeError` **inside the subprocess reader thread**,
   which leaves `proc.stdout is None` while git's own returncode is `0`. `_run_git` therefore
   returns `(0, None, "")`, and `parse_diff(None)` crashes with
   `AttributeError: 'NoneType' object has no attribute 'splitlines'`. The gate silently cannot
   run natively on Windows — the harden pipeline's OWN over-fit floor is dark on this workstation.

2. **`lazy-state.py --test`** and **`bug-state.py --test`** — the smoke-test harnesses print a
   step description containing `→` (U+2192) to stdout; encoding it to cp1252 raises
   `UnicodeEncodeError: 'charmap' codec can't encode character '→'`.

All three run clean under `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`. Pre-existing; orthogonal to
any recent change (discovered incidentally during Round 48).

## Reproduction

- `harness-gate.py`: staged diff containing `printf 'Í arrow \xe2\x86\x92'` in an in-scope file →
  `UnicodeDecodeError (byte 0x8d)` in the reader thread + downstream `NoneType.splitlines()`.
- `python user/scripts/lazy-state.py --test` → `UnicodeEncodeError '→'` in `run_smoke_tests`.
- `python user/scripts/bug-state.py --test` → same.

## Root cause (proven)

**script-defect** — reliance on the ambient locale codec (`cp1252` on Windows) instead of an
explicit UTF-8 contract, in two distinct sub-classes:

- **subprocess reads:** `subprocess.run(..., text=True)` with no `encoding=` decodes child stdout
  with `locale.getpreferredencoding()`. Git emits UTF-8; cp1252 cannot decode ~5 undefined byte
  slots (`0x81/0x8D/0x8F/0x90/0x9D`), so any git output carrying such a byte (filenames, commit
  subjects, diff bodies) raises in the reader thread. Because the decode happens off-thread,
  `capture_output`/`text` returns `None` for the failed stream with `returncode` still `0` —
  callers that don't guard `None` crash downstream (`harness-gate.py: parse_diff(None)`).
- **stdout writes:** printing a non-ASCII literal (`→`, and other markers like `✓ ✗ ⚠ …`) to a
  cp1252-backed `sys.stdout` raises `UnicodeEncodeError`.

## Fix scope

At the source, robustly and consistently — do NOT rely on the ambient locale codec:

- **`harness-gate.py`** `_run_git`: pass `encoding="utf-8", errors="replace"`; return
  `proc.stdout or ""` / `proc.stderr or ""` so a failed/empty read degrades to `""` instead of
  crashing `parse_diff` (kills the `NoneType.splitlines()` class permanently). Keep the script
  dependency-free (stdlib only) — its JSON output is already ASCII (`json.dumps` default
  `ensure_ascii=True`), so it needs no stdout reconfigure.
- **`lazy-state.py` / `bug-state.py`**: reconfigure `sys.stdout`/`sys.stderr` to UTF-8
  (`errors="replace"`) once at the top of `main()` via a shared stdlib helper. One call fixes
  ALL non-ASCII prints in each script, not just the `→` in `--test` (over an ad-hoc per-print
  guard).
- **Near-neighbor content reads** (git output that can carry non-ASCII bytes → same decode
  crash): the shared git helpers `lazy_core/runtimeplane.py::_git` and
  `lazy_core/ledgers.py::_git_capture_lines`, plus the inline reads in `lazy_core/gates.py`
  (`_git_diff_name_only`, `git status --short`) and `lazy_core/ledgers.py` (`git log --format=%s`
  commit subject) — add `encoding="utf-8", errors="replace"`.
- **Deliberately left** (cannot crash — output is format-constrained ASCII: hex SHAs from
  `rev-parse`, integer counts from `rev-list`, ISO/short dates from `%cI`/`%cs`, remote/config
  URLs, branch names from `--abbrev-ref`) and the `run_smoke_tests` test-fixture git spawns that
  read child ASCII. Logged in the Round 49 near-neighbor sweep. The durable, class-level guard
  (a mechanical lint that FLAGS any text-mode `subprocess` read without an explicit `encoding=`,
  and requires CLI entrypoints to reconfigure stdio) is the over-fit spin-off of Round 49.

## Sweep completion (Round 128 — 2026-07-20)

Round 49 (commit d35a4e64) fixed the three crashing surfaces + the production git readers +
13 `write_text` calls, and DEFERRED both (a) the test-fixture `subprocess` captures it judged
"read child ASCII" and (b) "the durable, class-level guard" as its over-fit spin-off. The
merge of origin/main (629 commits) then landed MANY new fixtures/captures with the same latent
bug — some of which DO compare non-ASCII child output — so the deferred (a) judgment was
partially wrong and the deferred (b) guard was never built. Round 128 completes BOTH:

- **Systematic AST sweep (mode 2):** a call-graph-scoped AST audit (whole-file for dedicated
  pytest modules; functions transitively reachable from `run_smoke_tests` / `test_*` / `_smoke*`
  for the in-file `--test` harnesses) found **252** test/fixture-context `subprocess.*` text
  captures (`text=True` / `universal_newlines=True`) lacking `encoding=` across **31 files**
  (`lazy-state.py` 43, `bug-state.py` 38, `lazy_coord.py` 10, and 28 `test_*.py` / `tests/**`
  modules). All 252 now carry `encoding="utf-8", errors="replace"` (matching the Round-49
  exemplar and the just-merged `resolve-ref-cli` fix). On this cp1252 machine, an unencoded
  capture decodes the child's UTF-8 stdout with the locale default → mojibake mismatch (common)
  or a hard `UnicodeDecodeError` crash (an undefined-cp1252 byte).
- **Mode 1 (`write_text` non-ASCII no-encoding):** the AST audit found **0** remaining — the
  merge fix and Round 49's 13-call sweep already closed this leg.
- **The durable class-level guard (Round 49's deferred spin-off):** now built as
  `_collect_cp1252_fragile_captures(source, filename)` (pure AST collector in
  `tests/test_lazy_core/_util.py`) + the self-checking meta-test
  `test_no_cp1252_fragile_captures_in_scripts` (scans the whole `user/scripts/` tree, FAILS
  naming file:line on any new offender) + a negative-fixture non-vacuity proof
  `test_cp1252_fragile_capture_guard_detects_planted_violation`, both registered in
  `test_misc.py`'s `_TESTS`. This mirrors the established `test_no_bare_production_sentinel_writes`
  / `test_no_duplicate_top_level_defs_in_state_scripts` AST-collector precedent, so a future
  fixture that reintroduces the class is a hard test failure — the whack-a-mole is closed
  structurally, not by another per-instance patch.

**Verified (this cp1252 machine, `locale.getpreferredencoding()` == `cp1252`):**
`lazy-state.py --test` + `bug-state.py --test` = "All smoke tests passed"; `lazy_parity_audit.py`
exit 0; the guard + orphan-guard tests pass; the full `pytest tests/test_lazy_core/` (run with
`-s` to sidestep an unrelated, pre-existing pytest-Windows stdin-handle `WinError 6` in ~224
subprocess tests) = **2 failed / 1337 passed**, the 2 failures pre-existing on origin
(environmental: a git-clean staging assertion + a cascade artifact) and unrelated to encoding.
