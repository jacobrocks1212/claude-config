# Generalized Build/Test Runner Skills — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 0 — Runner-outcome contract

#### Implementation Notes (Phase 0)
**Completed:** 2026-07-14 (commit cd0efba1)

- **Work completed:** authored `user/skills/_components/runner-outcome-contract.md` — the ONE
  documented contract (SPEC D1/L1): Leg 1 banner grammar with the three conforming instances
  (`build-queue:` existing / `QG_VERDICT:` grandfathered verbatim / `gate-battery:` new, quoted
  from SPEC D1), Leg 2 followable-await 124/125 semantics (mirrors `build-queue-await.ps1` —
  124 @ line 99, 125 @ lines 69/96/122), Leg 3 turn-end gate BY REFERENCE (one pointer sentence,
  zero copied gate text, zero `!cat` inside the component), Leg 4 never-pipe-through-tail
  (generalized from AlgoBooth `quality-gates.md:10-16`), the seam statement (documented grammar,
  not shared code — D4), and the D8 AlgoBooth path note with the `lazy-repos.json` pin recipe
  (documented only). Plus the `user/scripts/CLAUDE.md` prose-pointer paragraph (a new
  `## Runner-outcome contract` section above Contributor conventions — deliberately NOT a
  script-table row, so `doc-drift-lint.py` doc→disk mapping stays clean).
- **MVB verified:** `lint-skills.py` exit 0; `grep -c "turn-end"` = 3;
  `grep "may not end while work"` = 0 hits (referenced, not copied).
- **Gates:** full 7-command battery green pre-commit (pytest 2243 passed in 416s; both `--test`
  smoke suites; parity exit 0; cli-surface `--check` OK; doc-drift 0 findings; lint-skills OK).
  Cognito byte-untouched guard: commit touches nothing under `repos/cognito-forms/` or
  `build-queue*`.
- **Integration notes for Phase 1:** the `gate-battery:` grammar string in the component is the
  SSOT — WU-2/WU-3 tests must quote it verbatim from
  `user/skills/_components/runner-outcome-contract.md` (cite the path in test docstrings). If
  implementation forces a grammar change, change the component in the SAME commit (plan note 6).
- **Pitfalls:** none — docs-only phase. Components carry no YAML frontmatter (house style
  confirmed against `_components/` siblings).

## Phase 1 — Battery runner + manifest + pytest

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-14

- **Work completed (WU-2..WU-4):** `user/scripts/gate-battery.py` (stdlib-only, manifest-driven,
  contract-conformant) + `user/scripts/tests/test_gate_battery.py` (17 hermetic tests, tmp state
  roots + fixture manifests). WU-2 = runner core (git-toplevel manifest load, sequential gates
  with streamed output, last-line banner via try/finally, results JSON, private `_repo_key` copy
  of `lazy_core/statedir.py::repo_key` with keep-in-sync comment, manifest-less exit-2 clean
  refusal, state-root-unwritable graceful degrade, no-PowerShell source-scan proxy). WU-3 =
  `--await <run-id>` with 124 (not-yet, NEVER success) / 125 (malformed) semantics mirroring
  `build-queue-await.ps1`. WU-4 = seeded `.claude/skill-config/gate-battery.json` (7-command
  invariant battery AS COMMANDS, `python3` interpreter), CLI-surface roster addition
  (`DidYouMeanArgumentParser` + `--dump-cli-surface`, `docs/cli/cli-surface.json` regenerated
  same commit), `user/scripts/CLAUDE.md` script-table row.
- **MVB / dogfood (WU-4):** `python3 user/scripts/gate-battery.py --repo-root .` ran all 7 gates,
  last stdout line `gate-battery: run=20260714-1336 op=battery RESULT=PASS cmds=7 failed=0
  (elapsed=417s)`, exit 0. `--await 20260714-1336` re-emitted the same banner as its last line,
  exit 0. `cli_surface_gen.py --check` green (8 roster scripts).
- **Sequencing gate (SPEC L7):** verified `lazy-core-package-decomposition` Status=Complete with
  `COMPLETED.md` before any edit — dep satisfied.
- **Cognito byte-untouched guard (SPEC L6):** WU-4 commit touches nothing under
  `repos/cognito-forms/` or `build-queue*` / `build-queue-enforce.sh`.
