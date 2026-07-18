# no-sanctioned-cli-for-queue-state-mutations — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Sanctioned queue/state-mutation CLI — verify landed fix & complete

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-18
**Work completed:**
- The entire fix scope (sanctioned CLI mutators for in-place queue priority/dep changes)
  had already landed out-of-pipeline in commit `8a7bc738`. This phase's only remaining
  work was the SPEC's verification tail — no source/test code was authored or modified.
- Ran the five verification gates from the SPEC's `## Verification` section, all green:
  1. `python3 user/scripts/cli_surface_gen.py --repo-root .` — regenerated
     `docs/cli/cli-surface.json` (`OK — wrote ... (8 script(s), 245 flag(s))`).
  2. `python3 user/scripts/cli_surface_gen.py --check` — exit 0 clean.
  3. `python -m pytest user/scripts/tests/test_lazy_core/test_depdag.py -q` — 28/28 passed.
  4. `python user/scripts/lazy-state.py --test` — all smoke tests passed, exit 0.
  5. `python user/scripts/bug-state.py --test` — all smoke tests passed, exit 0.
  6. `python3 user/scripts/lazy_parity_audit.py --repo-root .` — exit 0.
**Integration notes:**
- The `docs/cli/cli-surface.json` regen swept in one unrelated, pre-existing drift as
  expected/disclosed in the plan and PHASES.md: the `lazy-state.py --set-independent`
  flag (a separate feature's flag whose owner never regenerated the registry). Diff
  confirmed: a single 16-line insertion adding that flag's entry — nothing else changed.
  This is NOT part of this bug's fix scope.
- No PRODUCT-class decisions arose this cycle; nothing routed to NEEDS_INPUT.md.
**Pitfalls & guidance:**
- None — this was a pure verify-and-regenerate cycle with no surprises. All gates passed
  on the first run.
**Files modified:**
- `docs/cli/cli-surface.json` — regenerated via `cli_surface_gen.py` (the only file this
  phase rewrites).
