# Implementation Phases — Sanctioned CLI for queue/state mutations

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a stdlib Python harness repo (state
scripts + tests); no Tauri desktop / MCP HTTP surface. The entire fix is CLI + library
code verified by pytest + the deterministic CLI-surface/parity gates (build/tooling class
per `docs/features/mcp-testing/SPEC.md` — no app integration to observe via MCP).

## Grounding note — implementation already landed out-of-pipeline

This bug's investigation concluded (`SPEC **Status:** Concluded`) and the **entire fix
scope shipped in a single out-of-pipeline `harden-harness` commit** —
`8a7bc738 harden(script): add sanctioned CLI for in-place queue priority/dep mutations` —
but the SPEC was left `Concluded` (never reconciled via receipt + `--archive-fixed`), so
`bug-state.py` routed the item into planning. Per `docs/bugs/CLAUDE.md`, a `Concluded`
(Status-untouched) out-of-pipeline fix is the "let the bug pipeline drive completion
normally" path — so this PHASES documents the landed work and schedules the SPEC's
**verification tail** as the genuinely-remaining pipeline work. Every implementation
deliverable below was verified present on disk during this planning cycle (`file:symbol`
citations in the touchpoint table); the executor **VERIFIES, it does not re-implement**.

## Validated Assumptions

- **All 7 SPEC fix-scope items are present on disk** (verified by grep/read this cycle,
  landed in `8a7bc738`):
  1. `lazy_core/depdag.py`: `reposition_by_priority` (L1023), `set_queue_priority`
     (L1139), `mutate_queue_deps` (L1230), `_coerce_set_tier_value` (L1062) — all present.
  2. `bug-state.py`: `unpin_bug_severity` (L2412) — present.
  3. CLI (both scripts): `--set-tier`/`--add-deps`/`--remove-deps` (lazy-state.py),
     `--set-severity`/`--unpin`/`--add-deps`/`--remove-deps` (bug-state.py), each
     `refuse_if_cycle_active` FIRST + `--operator-authorized`-gated — present.
  4. `cli_surface.py`: `--list-ops` / `--search-ops` + `search_ops()` (L251) + handler
     (L283) — present.
  5. Regression tests: `tests/test_lazy_core/test_depdag.py` — **28/28 pass** this cycle
     (set-priority reorder, pin-clear, feature tier + enum, invalid-dies-zero-mutation,
     deps add/remove/empty-drops-key, cycle refusal, reposition-not-found, `--set-severity`
     CLI operator-auth gate + reorder, `--unpin` CLI restore+reposition, `--search-ops`).
  6. `user/skills/lazy-batch/SKILL.md`: operator-authorized-mutator prose — present
     (L99–102).
  7. `docs/cli/cli-surface.json`: all new flags present (`--set-severity`, `--set-tier`,
     `--add-deps`, `--remove-deps`, `--unpin`, `--list-ops`, `--search-ops`).
- **Runtime-coupled assumptions: NONE.** Every deliverable is code-provable (pure Python
  queue-mutation logic + argparse + pytest). This gate's skip is recorded here: no
  user-facing runtime surface, so the reachability axiom is inapplicable (a CLI flag's
  reachability IS its argparse registration, asserted by the subprocess-invoking tests in
  item 5, not a runtime observation).
- **Known unrelated drift (out of this bug's scope).** `cli_surface_gen.py --check`
  currently reports ONE drift: `lazy-state.py: added flag(s) --set-independent` — a
  SEPARATE feature's flag (`set_independent_marker`, depdag L1336) whose owner never
  regenerated `cli-surface.json`. It is NOT part of this SPEC's fix scope. Because
  `cli_surface_gen.py` regenerates the WHOLE roster surface atomically (you cannot
  regenerate one flag), the verification-tail regen below will sweep `--set-independent`
  into the committed registry as a side effect — the correct, current registry state. See
  Implementation Notes.

## Touchpoint Audit (verified inline — dispatch not used; small, fully-specified surface)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core/depdag.py` | yes | `set_queue_priority`, `reposition_by_priority`, `mutate_queue_deps`, `_coerce_set_tier_value`, `merged_priority`, `detect_dep_cycle`, `reorder_queue` | verify | Landed — do NOT re-add; confirm via test_depdag.py |
| `user/scripts/bug-state.py` | yes | `unpin_bug_severity` (L2412); `--set-severity`/`--unpin`/`--add-deps`/`--remove-deps` CLI (L7898–7923, handlers L9206–9248) | verify | Landed; confirm gate refusals via tests |
| `user/scripts/lazy-state.py` | yes | `--set-tier`/`--add-deps`/`--remove-deps` CLI (L11789–11815, handlers L13638–13692) | verify | Landed |
| `user/scripts/cli_surface.py` | yes | `search_ops` (L251), `--list-ops`/`--search-ops` add (L182), handler (L283) | verify | Landed |
| `user/scripts/tests/test_lazy_core/test_depdag.py` | yes | 28 tests incl. `test_search_ops_finds_the_mutation_commands`, `test_unpin_cli_restores_severity_and_repositions` | verify | Landed; run as the primary gate |
| `user/skills/lazy-batch/SKILL.md` | yes | operator-authorized-mutator prose L99–102 | verify | Landed |
| `docs/cli/cli-surface.json` | yes | all 7 new flags present | regenerate | Regenerate to clear unrelated `--set-independent` drift → `--check` clean |

No path is unverified; no reuse directive is unnamed; no premise-grade contradiction (the
SPEC's premise — "these ops had no CLI" — was true at investigation and its fix has since
shipped; the SPEC is satisfied, not falsified).

---

### Phase 1: Sanctioned queue/state-mutation CLI — verify landed fix & complete

**Scope:** The full sanctioned-mutation CLI (in-place priority promote/demote with atomic
listed-order reposition, post-hoc arbitrary dep add/remove, bug un-pin, `--list-ops`/
`--search-ops` discoverability) landed atomically in `8a7bc738`. This phase VERIFIES the
landed implementation against the SPEC's Verification section and regenerates the CLI
surface so its freshness gate is clean — the remaining pipeline work before completion.

**Status:** Fixed

**Deliverables** *(implementation items already landed in `8a7bc738` — verified present on
disk this cycle; marked complete, NOT for re-implementation):*
- [x] `depdag.py`: `set_queue_priority` (validate + set field + clear pin on explicit bug
      severity + `reposition_by_priority` in ONE `_atomic_write`; returns old/new value +
      old/new position + `reordered`).
- [x] `depdag.py`: `reposition_by_priority` (stable FIFO-within-equal-priority listed-order
      re-slot per `merged_priority`) and `mutate_queue_deps` (union/difference `deps`,
      id-validate, post-mutation `detect_dep_cycle`, byte-stable no-op, drop-empty-key).
- [x] `bug-state.py`: `unpin_bug_severity` (clear `pinned_*`, restore `**Severity:**` from
      SPEC, reposition; no-op when already unpinned).
- [x] CLI (both scripts, coupled lockstep): `--set-tier` (feature) / `--set-severity`
      (bug) / `--add-deps` / `--remove-deps` / `--unpin` (bug) — each `refuse_if_cycle_active`
      FIRST (exit 3, zero side effects) + `--operator-authorized`-gated, no active-marker
      requirement.
- [x] `cli_surface.py`: `--list-ops` / `--search-ops <query>` introspecting the live
      `ArgumentParser`, ranked by token overlap.
- [x] Regression tests in `tests/test_lazy_core/test_depdag.py` (28 tests, all green).
- [x] `user/skills/lazy-batch/SKILL.md` operator-authorized-mutator prose (L99–102).

**Deliverables (remaining — the ONLY open work; executed & closed by `/execute-plan`, then
committed. claude-config has NO MCP/runtime gate, so these are ordinary in-session gate-run
+ regeneration deliverables, NOT deferred runtime-verification rows):**
- [x] Regenerate the CLI surface — `python3 user/scripts/cli_surface_gen.py --repo-root .` — then confirm `python3 user/scripts/cli_surface_gen.py --check` exits 0 clean, and commit the regenerated `docs/cli/cli-surface.json`. NOTE: the regen ALSO sweeps in the unrelated `--set-independent` flag (see Validated Assumptions) — expected; `cli_surface_gen.py` regenerates the whole roster surface atomically.
- [x] Confirm the landed fix's regression suite is green — `python -m pytest user/scripts/tests/test_lazy_core/test_depdag.py -q` (asserts priority mutation actually re-orders listed position — the load-bearing atomic reorder; deps add/remove + cycle refusal; `--unpin` restore+reposition; `--operator-authorized` gate + `refuse_if_cycle_active` refusal; `--search-ops` finds the command for a natural-language query).
- [x] Confirm `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` smoke suites are green, and `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0 (no new SKILL heading was added — bug-batch + cloud inherit the prose by reference).

**Minimum Verifiable Behavior:** `python -m pytest
user/scripts/tests/test_lazy_core/test_depdag.py` is green (28 passed) AND
`python3 user/scripts/cli_surface_gen.py --check` exits 0 after regeneration — the landed
mutators actually change listed order and the CLI surface registry is fresh.

**MCP Integration Test Assertions:** N/A — claude-config has no MCP/runtime surface. The
gate battery above (pytest + CLI-surface freshness + parity + `--test` smokes) IS the
complete verification.

**Completion (gate-owned):** the `__mark_fixed__` gate flips `SPEC.md` **Status:** to
`Fixed`, writes `FIXED.md`, records the intervention (measurable `target_signal` — the
SPEC's Verification item 6), and archives via `--archive-fixed` once the deliverables above
pass. NEVER authored as a checkbox here.

**Prerequisites:** None — implementation landed in `8a7bc738`.

**Files likely modified (this phase):**
- `docs/cli/cli-surface.json` — regenerate to clear the freshness gate (the only file the
  verification tail rewrites; all other touchpoints are verify-only).

**Testing Strategy:** Run the three remaining deliverable gates above from the repo root.
They are the SPEC's Verification section verbatim; a green result certifies the landed
fix. No new tests are authored — the 28-test suite already covers the fix scope.

**Integration Notes:**
- This is a single-phase plan because the fix shipped as one atomic commit; decomposing
  already-landed atomic work into synthetic sub-phases would misrepresent the change.
- The executor must treat every `[x]` deliverable as VERIFY-ONLY — the symbols exist; run
  the gates, do not re-author. Any "add function X" interpretation is a mis-read of this
  grounding note.
- The `--set-independent` drift is NOT this bug's defect; it is swept into the registry as
  a side effect of the mandatory atomic regen. Flagged to the orchestrator for awareness.

---

## Cross-feature Integration Notes

No hard deps on Complete upstreams (`SPEC` has no `**Depends on:**` block — `**Related:**`
lists precedent/substrate features, not hard deps). Nothing to integrate against.
