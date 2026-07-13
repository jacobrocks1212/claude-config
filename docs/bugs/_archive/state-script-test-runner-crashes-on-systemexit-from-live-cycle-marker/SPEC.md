---
kind: investigation-spec
bug_id: state-script-test-runner-crashes-on-systemexit-from-live-cycle-marker
---

# The state-scripts' in-file `--test` runner crashes partway when run from inside a live cycle marker (SystemExit(3) escapes `except Exception`) — Investigation Spec

> Spun off from the harden-harness round that fixed `lazy-cycle-containment-false-denies-reference-only-routing-mentions` (2026-07-12). SECONDARY-1: a cycle subagent cannot run the documented quality gate `python lazy-state.py --test` / `bug-state.py --test` mid-run — the suite aborts partway.

**Status:** Fixed
**Severity:** Low (downgraded from Medium — see Root Cause; the originally-reported crash does not reproduce at HEAD)
**Discovered:** 2026-07-12
**Concluded:** 2026-07-12
**Last updated:** 2026-07-12
**Placement:** docs/bugs/state-script-test-runner-crashes-on-systemexit-from-live-cycle-marker
**Related:** `docs/bugs/lazy-cycle-containment-false-denies-reference-only-routing-mentions` (the round that observed this); `lazy_core.refuse_if_cycle_active` (raises SystemExit(3)); the in-file `--test` harness in `user/scripts/lazy-state.py` + `user/scripts/bug-state.py` (coupled pair)

---

## Observed Symptom (verified this round)

Running `python user/scripts/lazy-state.py --test` from a session with a LIVE cycle marker in the production keyed state dir aborts at:

```
FAILURES:
  - [apply-pseudo-provisional-refusal] SystemExit: 3
```

The `[apply-pseudo-provisional-refusal]` fixture reaches a code path that calls `refuse_if_cycle_active`, which raises `SystemExit(3)` (the C3 cycle-containment refusal, exit-code 3). `SystemExit` is a `BaseException`, not an `Exception`, so the `--test` runner's per-fixture `except Exception` does NOT catch it — it escapes and crashes the suite partway. Confirmed environmental, not a code regression: the SAME `--test` passes fully under a hermetic `LAZY_STATE_DIR` (empty temp dir, no cycle marker).

## Impact

A cycle subagent (agent_id present, or a live cycle marker) cannot run the two documented state-script quality gates mid-run without the hermetic `LAZY_STATE_DIR=<empty>` workaround. This silently undermines gate-runnability for every future cycle/hardening subagent.

## Candidate Fixes (to be decided by /spec-bug)

1. **Catch `BaseException`/`SystemExit` per-fixture** in the `--test` runner so a `SystemExit(3)` from a fixture is reported as a normal handled result (or asserted), not a suite crash. Lowest-scope; makes the runner robust to any guarded op a fixture legitimately exercises.
2. **Hermetically isolate the offending fixture(s)** — ensure `[apply-pseudo-provisional-refusal]` (and any sibling that calls a `refuse_if_cycle_active`-guarded op) always sets its own `LAZY_STATE_DIR` so it never reads the ambient production cycle marker.

Prefer (1) as a defense-in-depth backstop and (2) for correctness, possibly both. Coupled pair — apply to BOTH `lazy-state.py` and `bug-state.py` test harnesses.

## Reconstructed Route (surface → source, HEAD-cited)

Serving-path trace for the ONE call in the entire in-process `--test` suite that can
trip `refuse_if_cycle_active` (verified by grep — see Verification below):

```
CLI surface: `python user/scripts/lazy-state.py --test` stdout, under a live
cycle marker, prints a "FAILURES:" summary block including one line:
  - [apply-pseudo-provisional-refusal] SystemExit: 3
    ↑ lazy-state.py:9808-9825 (sub-fixture 10, "apply-pseudo-provisional-refusal")
      wraps its ONE direct in-process call in `try: ... except SystemExit as exc:
      failures.append(...)` (HEAD, added commit 239a1a951, 2026-07-09 — BEFORE
      this bug's 2026-07-12 discovery date)
    → calls lazy_core.apply_pseudo(pp_root, "__mark_complete__", pp_prov_dir)
      lazy-state.py:9810-9812
    → lazy_core.py:4274 (HEAD) `refuse_if_cycle_active("apply_pseudo")` — an
      UNCONDITIONAL call at the top of `apply_pseudo()` itself (added commit
      847f47e35, 2026-07-03 — also BEFORE discovery), per the code comment at
      lazy_core.py:4254-4273 explaining this closes a "direct-import side-door"
      so ANY caller (CLI or in-process test) is guarded, not just the CLI.
    → lazy_core.py:12481-12508 `refuse_if_cycle_active`: reads
      `read_cycle_marker()` → `claude_state_dir(create=False)`, which honors the
      AMBIENT `LAZY_STATE_DIR` env var (or the real per-repo keyed
      `~/.claude/state/<repo_key>/` when unset) — NOT scoped to the fixture's
      own `pp_root` temp dir. A live marker there → `sys.exit(3)`.
```

## Root Cause

**Cause label: `traced`.** The bug's ORIGINAL claimed mechanism — "`SystemExit`
is a `BaseException`… the `--test` runner's per-fixture `except Exception` does
NOT catch it — it escapes and crashes the suite partway" — is **FALSE at HEAD**,
and was already false at the 2026-07-12 discovery date:

1. **The runner already uses `except SystemExit as exc:`, not `except Exception`,**
   at every in-process call site that can raise it, including the exact named
   fixture (lazy-state.py:9823-9825, landed 2026-07-09).
2. **`apply_pseudo` is the ONLY function the in-process `--test` suite calls
   directly that can invoke `refuse_if_cycle_active`.** `enqueue_adhoc()` (the
   other function called in-process, e.g. lazy-state.py:904/8037/8049/8159)
   does NOT call the guard internally — `refuse_if_cycle_active("--enqueue-adhoc")`
   is invoked only in the CLI dispatch layer (lazy-state.py:12518), which the
   in-process test calls never traverse. So only ONE fixture is even capable of
   tripping the guard, and it already catches the resulting `SystemExit`.

**Mechanical, hermetic reproduction** (zero touches to real state — an isolated
`LAZY_STATE_DIR` scratch dir seeded with a fake `lazy-cycle-active.json`,
mirroring a genuinely-live cycle):

```
LAZY_STATE_DIR=<scratch>/repro-state-dir python3 user/scripts/lazy-state.py --test
```

Result: the suite runs to completion — 30+ fixtures execute and PASS *after* the
guarded fixture — ending in the normal `FAILURES:` summary block (exactly ONE
entry: `[apply-pseudo-provisional-refusal] SystemExit: 3`) and process exit code
`1` (a failed-assertion exit, not a crash). No Python traceback, no early
termination. The identical hermetic run against `bug-state.py --test` exits `0`
clean — that script's `--test` harness has NO in-process direct call to
`lazy_core.apply_pseudo` (its only exercise of `--apply-pseudo` is via
`subprocess.run` at bug-state.py:5875, whose child exit code is captured
normally and can never raise `SystemExit` in the parent).

**What the bug DID correctly diagnose (a smaller, real, `traced` finding):** the
`apply-pseudo-provisional-refusal` fixture (lazy-state.py:9808-9825) is the only
sub-fixture in the "park-provisional" group (lazy-state.py:9497-9845) that is
**not hermetically isolated** from the ambient `LAZY_STATE_DIR`/cycle marker —
unlike sibling fixture groups elsewhere in the same file (e.g. the
`LAZY_STATE_DIR` save/restore pattern at lazy-state.py:6952-7019, 7057-7255,
7300-7533, 10202-10212, 10730-10858) which explicitly point their own
`LAZY_STATE_DIR` at a private temp dir before exercising a guarded op. Because
this ONE fixture omits that isolation, running `--test` from inside any
genuinely-live cycle (exactly the scenario a hardening/cycle subagent is in)
deterministically produces this ONE spurious `FAIL` — masking the fixture's
real assertion (that a provisional sentinel refuses `__mark_complete__`) behind
an unrelated, expected, environment-coupled refusal. The suite as a whole is
unaffected (it completes and correctly reports "N failures"), but the single
`FAIL` line is legitimately confusing to a subagent that doesn't cross-check
whether the run otherwise completed.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| `apply-pseudo-provisional-refusal` fixture | `user/scripts/lazy-state.py:9805-9825` | Not isolated from the ambient `LAZY_STATE_DIR`; spuriously FAILs (but does not crash) when run under a genuinely-live cycle marker |
| (bug-state.py) | — | No equivalent in-process fixture exists; unaffected, no change needed |

## Fix Scope

1. **Isolate the `apply-pseudo-provisional-refusal` fixture's own `LAZY_STATE_DIR`**
   (lazy-state.py:9808-9825), mirroring the save/restore pattern already used by
   sibling fixture groups in the same file (e.g. lazy-state.py:7057-7058 /
   7253-7255): save the prior `LAZY_STATE_DIR` value, point it at a private
   `tempfile.TemporaryDirectory()` for the duration of the `apply_pseudo(...)`
   call (guaranteeing `refuse_if_cycle_active` sees no marker so the fixture
   exercises its INTENDED assertion — the provisional-sentinel refusal — instead
   of racing the ambient environment), then restore it in a `finally`.
2. No change needed to `bug-state.py` (no equivalent in-process fixture exists —
   the "coupled pair, apply to both" note in the original bug filing does not
   apply; verified by grep, no direct `lazy_core.apply_pseudo(` call in
   `bug-state.py`'s `--test` harness).
3. **Recommendation:** ship (1) as a small, low-severity test-hermeticity fix.
   Do NOT touch `refuse_if_cycle_active`, `apply_pseudo`, or the general
   `except SystemExit` pattern — both are already correct and predate this
   bug's filing.

Runtime residue: none — this bug required no runtime/device access; the
hermetic repro above IS the confirming evidence, captured entirely on this
machine.

## Notes

Not fixed inline in the originating round (scope discipline + coupled-pair change to both state-script test harnesses); the originating round certified its PRIMARY fix via the hermetic `LAZY_STATE_DIR` run, which is the legitimate/standard way these hermetic suites run.

**Verification commands used (read-only, hermetic; reproducible by any future reader):**

```bash
# Confirm which functions the in-process --test suite calls directly that can
# invoke refuse_if_cycle_active:
grep -n "\.apply_pseudo(\|\.enqueue_adhoc(\|\.emit_dispatch(" user/scripts/lazy-state.py

# Hermetic repro (safe — isolated temp state dir, never touches real state):
mkdir -p /tmp/repro-state-dir
printf '{"feature_id": "repro-feat", "started_at": "2026-07-12T00:00:00Z"}' \
  > /tmp/repro-state-dir/lazy-cycle-active.json
LAZY_STATE_DIR=/tmp/repro-state-dir python3 user/scripts/lazy-state.py --test
# → exits 1, exactly one FAIL (apply-pseudo-provisional-refusal), 30+ fixtures
#   PASS after it, "FAILURES:" summary prints normally. No traceback.
LAZY_STATE_DIR=/tmp/repro-state-dir python3 user/scripts/bug-state.py --test
# → exits 0, "All smoke tests passed."
```
