# harden-harness gate battery names the relocated `test_lazy_core.py` standalone path — Investigation Spec

> The `/harden-harness` gate battery (and the `dispatch-hardening.md` component injected into
> dispatched hardening prompts) still names `python ~/.claude/scripts/test_lazy_core.py` as a
> mandatory gate. `lazy-core-package-decomposition` relocated that test module out of a single
> flat file into the per-seam pytest package `user/scripts/tests/test_lazy_core/`. The standalone
> `test_lazy_core.py` file no longer exists, so anyone following the documented gate battery
> literally runs a missing module (fails to invoke) or silently skips the most important harness
> gate. Surfaced during harden-harness Round 47 (the build-queue FORCE_COLOR fix): the runner
> noted the SKILL still named `test_lazy_core.py` and ran the effective pytest equivalent by hand.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-17
**Related:** `docs/features/lazy-core-package-decomposition/` (the decomposition that moved the flat `test_lazy_core.py` into the `user/scripts/tests/test_lazy_core/` pytest package behind the byte-compatible facade); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 47 (the round that first observed the drift) and the round appended by this fix.

## Verified Symptom

- `user/scripts/test_lazy_core.py` no longer exists (`ls` → No such file or directory). Tests now
  live in the package `user/scripts/tests/test_lazy_core/` (13 `test_<seam>.py` modules +
  `conftest.py` + `_util.py`), run via `python -m pytest tests/test_lazy_core/` (1159 tests
  collected in 0.31s; full suite green). `user/scripts/CLAUDE.md:118-120` documents the current
  invocation: "`lazy_core` is tested separately via the per-seam package `tests/test_lazy_core/`
  (pytest…)".
- Stale gate-command copies (name the nonexistent standalone file as a command to run):
  - `user/skills/harden-harness/SKILL.md:165` — `python ~/.claude/scripts/test_lazy_core.py`
  - `user/skills/_components/lazy-batch-prompts/dispatch-hardening.md:129` — same command,
    injected verbatim into dispatched hardening prompts (the enforcement-time copy).
  - `.claude/skill-config/quality-gates.md:15` — parenthetical `python user/scripts/test_lazy_core.py`.
- Stale prose references (name the old file, not a run command):
  - `user/skills/harden-harness/SKILL.md:171-175` — dead-coverage guard note.
  - `user/skills/_components/mark-fixed-archive.md:64` — "tested in `test_lazy_core.py`".
  - `user/hooks/lazy-dispatch-guard.sh:27` — comment naming the override user.
- `test_no_orphaned_test_functions` (the dead-coverage guard the SKILL prose cites) now lives at
  `tests/test_lazy_core/test_misc.py:3248`, collected under the pytest package — so it still runs,
  but only via the corrected invocation.
- Out of sweep (deliberately unchanged): historical audit records (PHASES.md, plans, prior
  hardening-log rounds, archived bug docs) that name `test_lazy_core.py` — these are point-in-time
  records, not live contracts, and rewriting them would falsify the audit trail.

## Root Cause

**Classification: `missing-contract` / doc-drift (lockstep repair).** The two gate-battery copies
are independent literal copies (the harden-harness SKILL.md carries no `!cat` include; the
`dispatch-hardening.md` component is a parallel copy), so the `lazy-core-package-decomposition`
module move updated neither. No mechanical pin ties the harden-harness gate command to the actual
on-disk test location, so the decomposition silently desynchronized the documented gate from
reality.

## Fix Scope

- Update both gate-command copies and the quality-gates parenthetical to the current invocation
  `python -m pytest ~/.claude/scripts/tests/test_lazy_core/` (repo-relative
  `python -m pytest user/scripts/tests/test_lazy_core/`).
- Update the dead-coverage-guard prose and near-neighbor references to name the pytest package
  (and, where a concrete home is cited, `tests/test_lazy_core/test_misc.py`).
- Re-project skills (`project-skills.py`) and run the full gate battery (via the corrected
  command) to confirm green.
