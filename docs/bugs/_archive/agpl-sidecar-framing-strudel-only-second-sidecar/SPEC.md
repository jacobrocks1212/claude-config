# Bug: AGPL public-sidecar framing + IP-placement preference is Strudel-only; a second public AGPL sidecar (hydra) has no covering contract

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** e4fd093d
**Reported via:** `/harden-harness` observed-friction dispatch (2026-07-16, item in flight `hydra-overlay`, AlgoBooth `/lazy-batch`, blocking=false). Operator-directed (Jacob, mid-run).
**Root-cause class:** `missing-contract`
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); AlgoBooth `docs/legal/AGPL_ISOLATION.md` + `docs/legal/AGPL_PUBLICATION_MANIFEST.md` (the legal source of truth these harness prose surfaces point at); the in-flight `hydra-overlay` feature (creates the second sidecar `hydra-sidecar/`, AGPL `hydra-synth`).

## Symptom (verified)

Every harness surface that encodes AlgoBooth's "public AGPL sidecar" boundary + the
"AlgoBooth business-differentiating IP lives in the proprietary app, NOT in the public
sidecar" placement preference names **only** the Strudel sidecar (`strudel-sidecar/`,
`@strudel/*`, `superdough`). AlgoBooth is now gaining a **second** public AGPL sidecar — the
hydra sidecar (`hydra-sidecar/`; `hydra-synth` is AGPL-3.0), authored for the `hydra-overlay`
feature. Under the current Strudel-only framing, a spec/plan author reasoning about placement
for hydra code has **no covering contract**: the standing rules, the required-SPEC-section
questions, the `/spec-phases` audit, and the `/write-plan` touchpoint gate all key literally
on `strudel-sidecar/` and would not recognize `hydra-sidecar/` as the same class of
publicly-disclosed AGPL code.

Verified surfaces (grep, 2026-07-16):

- **AlgoBooth repo `CLAUDE.md` → "AGPL Boundary Rules"** (lines 43-63): rule 1 names
  `@strudel/*`/`superdough` + `strudel-sidecar/`; rule 2 "`strudel-sidecar/` is public code";
  rules 3-4 Strudel-only. No mention of hydra or a generic "any public AGPL sidecar" class.
- **`repos/algobooth/.claude/skill-config/spec-testing-guidance.md` → "## AGPL / IP Placement"**
  (consumed by `/spec`): question (a) keys on `@strudel/*`/`superdough`/`Pattern`; (b) names
  `strudel-sidecar/` as "public AGPL code".
- **`repos/algobooth/.claude/skill-config/phases-runtime-validation.md` → "#### AGPL / IP
  Placement Audit"** (consumed by `/spec-phases`): "Why this gate exists" + Steps A/B key on
  `strudel-sidecar/`. (Step C already cites `hydra-synth` as an example of a new AGPL
  dependency — partial awareness, but the standing framing is still Strudel-only.)
- **`repos/algobooth/.claude/skill-config/touchpoint-audit-gate.md` → "### AGPL / IP placement
  gate (strudel-sidecar/)"** (consumed by `/write-plan`, `/implement-phase`, `/fix`): keys on
  "any new file under `strudel-sidecar/`".

Non-blocking: the operator caught the gap mid-run and dispatched this harden; no misroute or
denial occurred. The fix generalizes the framing so hydra + future sidecars are covered by
construction.

## Root cause

**`missing-contract`.** The harness's AGPL-sidecar contract was authored for the single
Strudel sidecar and hard-codes that instance (`strudel-sidecar/`, `@strudel/*`, `superdough`)
rather than the **class** it is an instance of: *any public AGPL sidecar AlgoBooth publishes
to satisfy AGPL disclosure*. A legitimately novel situation — a second sidecar (`hydra-sidecar/`,
`hydra-synth`) — arose that the contract does not cover. This is not ambiguous prose (the prose
is clear) and not a script defect; it is an under-general contract that never anticipated a
second instance of its own subject.

## Fix scope

Generalize the framing to "any public AGPL sidecar" (explicitly naming `strudel-sidecar/` +
`hydra-sidecar/` as the current instances, and calling out `@strudel/*`/`superdough` and
`hydra-synth` as the current AGPL dependencies), preserving every existing rule verbatim in
meaning. Edit EXACTLY four files, prose-only:

1. AlgoBooth repo `CLAUDE.md` — "AGPL Boundary Rules" section (operator-scoped exception to the
   never-edit-target-source prohibition; this is repo policy documentation, explicitly in scope
   per the dispatch).
2. `repos/algobooth/.claude/skill-config/spec-testing-guidance.md` (`/spec`).
3. `repos/algobooth/.claude/skill-config/phases-runtime-validation.md` (`/spec-phases`).
4. `repos/algobooth/.claude/skill-config/touchpoint-audit-gate.md` (`/write-plan`).

**Out of scope (HARD — owned by a separate in-flight `hydra-overlay` execute-plan task,
git-stashed):** `docs/legal/AGPL_ISOLATION.md`, `docs/legal/AGPL_PUBLICATION_MANIFEST.md`,
`eslint-rules/no-agpl-imports.cjs`, anything under `hydra-sidecar/` or `src-tauri/src/hydra/`.
These are read-only reference here.

## Verification

- `python3 user/scripts/lint-skills.py --check-projected --check-capabilities` (skill-config
  components must re-project cleanly).
- Full harness gate battery (test_lazy_core pytest package, test_hooks.py, lazy-state.py
  --test, bug-state.py --test) — no regression from a prose-only change.
- No schema touched → no sentinel-schema lockstep / coupled-pair mirroring required.
