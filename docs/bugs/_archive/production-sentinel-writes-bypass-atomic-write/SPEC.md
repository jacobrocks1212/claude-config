# Production sentinel writes bypass _atomic_write, violating the repo's own contract — Investigation Spec

> `user/scripts/CLAUDE.md` states all queue/marker/sentinel writes go through
> `lazy_core._atomic_write` — but both state scripts write production BLOCKED.md /
> NEEDS_INPUT.md / brief / ROADMAP files via bare `path.write_text()`. A kill mid-write
> yields exactly the "half-written sentinel corrupts the machine's view" failure the
> contract exists to prevent. The contract is prose-only: nothing mechanical enforces it,
> and `user/scripts/` has no Python lint gate at all (proven by an undetected duplicate
> function definition in `lazy_core.py`).

**Status:** Fixed
**Priority:** P2
**Last updated:** 2026-07-12
**Related:** `docs/bugs/mark-complete-partial-apply-noop-unrecoverable/` + `docs/bugs/coord-lock-no-stale-reclaim/` (siblings — shared theme: crash-consistency of script-owned state); `user/scripts/CLAUDE.md` (the violated contract, lines ~53–54); `docs/features/host-capability-declaration-for-gated-features/` (introduced the two `_write_yaml_blocked_sentinel` production writers, Phases 4/6); `docs/features/doc-drift-linter/` (precedent for a mechanical prose-to-code enforcement gate in this repo).

## Verified Defect

**Code-proven, not field-observed** — no corrupted sentinel has been caught in the wild;
the trace below is a line-level read of the live tree (2026-07-11, uncommitted working
copy — cited line numbers are what the current files actually show).

**The contract.** `user/scripts/CLAUDE.md` lines ~53–54, under "High-signal invariants":

> **All queue/marker/sentinel writes go through `lazy_core._atomic_write`** — never a bare
> `open().write()`. Atomicity is the contract; a half-written `queue.json` corrupts the machine.

`_atomic_write` itself (`lazy_core.py:105–118`) is sound: `tempfile.mkstemp` in the target
dir → write → `os.replace`.

**The violations (production paths, all `path.write_text()`):**

| Writer | Defined | Bare write | Production caller(s) |
|--------|---------|-----------|----------------------|
| `lazy-state.py _write_yaml_blocked_sentinel` | 3670 | 3698 | `compute_state` fail-fasts: 1995 (unknown-host-capability), 2488 (unknown-dependency) — each writes a real `BLOCKED.md` that the state machine immediately routes `terminal_reason="blocked"` on |
| `lazy-state.py _write_yaml_sentinel` | 3664 | 3667 | fixture-only today, but defined as the sibling of the above under the same section |
| `bug-state.py _write_yaml_blocked_sentinel` | 1864 | 1911 | 887 (unknown-host-capability), 1163 (unknown-dependency) — same fail-fast pair, bug pipeline |
| `bug-state.py _write_yaml_sentinel` | 1844 | 1861 | fixture-only sibling |
| `lazy-state.py _write_step10_needs_input` | 1512 | 1576 | 3605 — a production `NEEDS_INPUT.md` (Step-10 unexpected-state branch) |
| `lazy-state.py enqueue_adhoc` ROADMAP.md append | — | 735 / 737 | `--enqueue-adhoc` production path (note the queue.json write two paragraphs earlier at 709 IS `_atomic_write` — the same function honors the contract for one file and violates it for the next) |
| `lazy-state.py enqueue_adhoc*` brief/spec writes | — | 716, 813, 909, 915, 952, 957 | `ADHOC_BRIEF.md` / seeded `SPEC.md` production writes |

An aggravating placement detail: `lazy-state.py`'s two sentinel writers sit BELOW the
`# Fixture smoke tests` section banner (lines 3660–3662) while being called from
`compute_state` production code 1700 lines earlier — the file's own layout misclassifies
them as test helpers.

**Why it matters.** `BLOCKED.md` is a machine-parsed routing sentinel: frontmatter is "the
parser's source of truth" (the writer's own docstring, `lazy-state.py:3674–3682`). A
truncated write (crash/kill/disk-full between `open` and `close` inside `write_text`)
leaves a file that EXISTS (so every `BLOCKED.md`-exists check routes blocked) but whose
frontmatter may be half-emitted garbage — the exact "malformed sentinel corrupts the
machine's view" failure the CLAUDE.md invariant names. Same class as the sibling bug
`mark-complete-partial-apply-noop-unrecoverable`, one level down (intra-file instead of
inter-file).

**Parity asymmetry (secondary finding).** `bug-state.py`'s writers each carry a per-call
no-PyYAML `except ImportError` fallback (1846–1860, 1895–1910) routed through
`lazy_core._yaml_fallback_scalar`, while `lazy-state.py` hard-exits at import time without
PyYAML (`lazy-state.py:63–67`, `sys.exit(2)`) and its writers have no fallback — yet
`bug-state.py:1872–1874` claims its writer is "a byte-for-byte mirror of the lazy-state.py
helper of the same name". The mirrors have silently diverged; whichever posture is right,
the divergence is unexplained and un-audited.

**Bonus finding — proof there is no lint gate.** `lazy_core.py` defines `_current_head`
TWICE with identical bodies: lines 3875–3891 and 5661–5684 (both
`git -C <root> rev-parse HEAD`, same try/except, same timeout). The second definition
silently shadows the first at module level. The 5661 docstring even explains why
duplicating lazy-state.py's copy is deliberate — while not noticing the in-FILE duplicate.
`pyflakes`/`ruff` rule F811 flags exactly this; the repo has no `.github/workflows/`
directory and no ruff/pyflakes/flake8 configuration anywhere under `user/scripts/`, so
nothing ever ran it. A prose contract with no mechanical check decays — this file is the
evidence.

## Root Cause

**Classification: `unenforced-contract`.** The atomic-write invariant exists only as
CLAUDE.md prose. The helpers that violate it were added later (host-capability fail-fasts,
Step-10 needs-input, ad-hoc enqueue) by authors/agents who either never mapped "BLOCKED.md
/ NEEDS_INPUT.md" onto the contract's "queue/marker/sentinel" wording or copied the
fixture-writer pattern that lives in the same file. With zero mechanical enforcement (no
Python lint gate at all on `user/scripts/`), each new write path re-rolls the dice; the
`_current_head` duplicate shows the same enforcement vacuum catching a different defect
class in the same file.

## Fix Scope (Concluded)

1. **Route every production doc write through `lazy_core._atomic_write`:** the seven rows
   in the table above (`_write_yaml_sentinel` / `_write_yaml_blocked_sentinel` in BOTH
   state scripts, `_write_step10_needs_input`, the ROADMAP append, the ad-hoc brief/spec
   writes). Mechanical substitution — each already builds the full content string before
   writing, so `path.write_text(text)` → `_atomic_write(path, text)` with no behavior
   change. Move the two lazy-state writers above the fixture-section banner (or re-banner)
   so layout matches reality.
2. **Mechanical lint so the contract is enforced, not prose:** a check (grep- or AST-based,
   wired wherever this repo's existing self-checks run — the `--test` smoke harnesses
   and/or `doc-drift-lint.py`'s invocation path) that FAILS on `\.write_text\(` /
   `open(.*,\s*["']w` outside the designated test/fixture regions of `lazy-state.py`,
   `bug-state.py`, and `lazy_core.py`, with an explicit allowlist for genuinely-fixture
   call sites. The point is that the NEXT bare write cannot land silently.
3. **F811 / pyflakes-class gate on `user/scripts/`** (fix-scope row per the bonus finding):
   adopt `ruff check --select F` (or pyflakes) as part of the same self-check entry point,
   and resolve the existing `_current_head` duplicate (delete one definition; the bodies
   are identical so either survivor is correct — keep the WU-4-adjacent one at 5661 or
   hoist a single definition, implementer's choice).
4. **Reconcile the PyYAML-fallback asymmetry:** either delete bug-state's per-call
   ImportError fallbacks (dead code, since a harness that standardizes on lazy-state's
   hard-exit posture can never reach them) or give lazy-state the same fallback and drop
   its import-time exit — one posture, documented in `user/scripts/CLAUDE.md`, and fix the
   false "byte-for-byte mirror" docstring either way.
5. **Tests:** smoke-harness fixtures asserting the blocked/needs-input writers produce
   parseable sentinels via the atomic path, plus a lint-gate self-test (a deliberately
   planted bare write in a fixture string must be caught).

## Decisions

- **D1 — Scope of "production":** the two state scripts' non-fixture regions. `lazy_core.py`
  already complies (its writers use `_atomic_write`); the `--test` fixture builders'
  hundreds of `write_text` calls are out of scope by design (hermetic temp dirs, no machine
  routes on them mid-write) and form the lint allowlist.
- **D2 — Lint vehicle:** prefer `ruff --select F` + a small targeted bare-write check over
  a bespoke full parser; ruff also delivers fix-scope §3 for free. If adding a ruff
  dependency is unwanted, the grep-based check alone still closes the contract gap
  (surface as NEEDS_INPUT only if the implementer finds both unpalatable).
- **D3 — Fallback posture (fix-scope §4):** default to lazy-state's hard-exit posture
  (PyYAML is a declared prerequisite; per-call fallbacks are complexity that only executes
  on a misconfigured host). Genuine no-PyYAML hosts in the field would flip this — none are
  known.
