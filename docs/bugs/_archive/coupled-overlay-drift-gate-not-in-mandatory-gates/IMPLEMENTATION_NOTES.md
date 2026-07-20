# Wire the coupled-overlay drift gate into the mandatory gate battery — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Register the coupled-overlay drift gate in the mandatory battery (+ prose + count + recurrence guard)

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-19

**Work completed:**
- Added an 8th gate row to `.claude/skill-config/gate-battery.json` — `{ "id": "coupled-overlay-drift", "cmd": "python3 user/scripts/generate-coupled-skills.py --check --repo-root ." }`, inserted immediately after the existing `parity-audit` row (both are coupled-surface drift gates). All 7 pre-existing rows untouched byte-for-byte (pure append).
- Added a recurrence-guard test, `test_committed_manifest_registers_coupled_overlay_drift_gate`, to `user/scripts/tests/test_gate_battery.py`. Unlike the file's other 17 hermetic `tmp_path`-fixture tests, this one reads the REAL committed `.claude/skill-config/gate-battery.json` and asserts at least one gate's `cmd` contains both `"generate-coupled-skills.py"` and `"--check"` — the mechanical guard against a future silent removal of the row (the exact failure class this bug fixed). Confirmed RED (manifest had 7 gates, none matching) before the manifest edit, GREEN after (18/18 passing).
- Named the drift gate in the coupled-pair prose gate list in `.claude/skill-config/quality-gates.md`: added a bullet under "Lazy skill-family changes" (`python user/scripts/generate-coupled-skills.py --check --repo-root .`) and appended it to the "Mixed / feature completion" FULL-set enumeration.
- Corrected the stale "7-command invariant battery" claims: `CLAUDE.md` (repo root, `gate-battery.py` Scripts-table row) and `user/scripts/CLAUDE.md` (two occurrences — the `gate-battery.py` row citing "SPEC L5", and the Ruff-lint advisory-gate section). Chose the reword-to-drop-hardcoded-count approach (rather than bump 7→8) in both files so a future 9th gate can't re-stale the claim, and so the `user/scripts/CLAUDE.md` row's "SPEC L5" citation (which still says 7, for the historical `generalized-build-test-runner-skills` feature) is never contradicted by a bumped local count.
- Batch-review follow-up fix (PASS-WITH-FIXES): `user/scripts/CLAUDE.md:56`'s `gate-battery.py` row test-count parenthetical was stale after this batch's own test addition — bumped `Tests: tests/test_gate_battery.py (17, hermetic tmp state roots)` → `(18, mostly hermetic tmp state roots — one reads the committed repo manifest)`.

**Integration notes:**
- The battery now reports `cmds=8` (was `cmds=7`). Full `python3 user/scripts/gate-battery.py` run confirmed `RESULT=PASS cmds=8 failed=0` on the clean tree (elapsed=539s) — the new gate does not break the green baseline, it only starts catching FUTURE coupled-overlay drift.
- `python3 -m pytest user/scripts/tests/test_gate_battery.py -q` → 18 passed.
- `doc-drift-lint.py --repo-root .` and `cli-surface-lint.py --repo-root .` both exit 0 (only pre-existing, unrelated exempted divergences).

**Pitfalls & guidance:**
- The two mentions of the desired manifest placement in the plan/PHASES ("keep it a peer of `parity-audit`, placed after it" vs. a looser "append as last entry" elsewhere) were slightly inconsistent with each other — the more specific instruction (adjacent-after `parity-audit`) was followed, which is also the more semantically correct placement (both gates police coupled-surface drift).
- The **Runtime Verification** rows in PHASES.md (full-battery `cmds=8`/`RESULT=PASS` re-confirmation, and the deliberate drift-induce-then-revert spot check) are intentionally left UNCHECKED here — those are `<!-- verification-only -->` rows owned by the validation tail, not the implementation batch. The WU-1 implementation agent's own full `gate-battery.py` run (`RESULT=PASS cmds=8 failed=0`) already satisfies the first row's substance, but per the pipeline's own convention the checkbox itself stays for the gate/operator step to tick.

**Files modified:**
- `.claude/skill-config/gate-battery.json` — added the `coupled-overlay-drift` gate row.
- `user/scripts/tests/test_gate_battery.py` — added the recurrence-guard test.
- `.claude/skill-config/quality-gates.md` — named the new gate in the coupled-pair prose lists.
- `CLAUDE.md` — corrected the stale battery-count claim.
- `user/scripts/CLAUDE.md` — corrected two stale battery-count claims + the batch-review follow-up test-count fix.

**Review verdict:** PASS-WITH-FIXES — one cosmetic follow-up (stale test-count parenthetical on the same line WU-2 edited) applied directly in the orchestrating session per the review report's Actionable Items; no other issues found. Ground-truth verification (Step 1.5) was clean across all three dispatched subagents (test agent, doc agent, impl agent) — no mismatches.
