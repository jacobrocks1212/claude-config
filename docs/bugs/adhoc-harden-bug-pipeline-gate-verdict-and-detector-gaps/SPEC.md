# Bug — bug-pipeline gate-verdict authoring seam + fixed/spec-path/emit detector gaps

**Status:** Concluded
**Severity:** High (GAP 1 blocked a bug this run) · Medium/Low (GAPs 2–4)
**Discovered:** 2026-07-19 (during a `/lazy-bug-batch` run over claude-config)
**Fixed:** 2026-07-19 - implemented out-of-pipeline via `/harden-harness` (see FIXED.md)

/ harden-harness Step-2.5 investigation spec. Batch of four real, reproducible
bug-pipeline defects observed during a `/lazy-bug-batch` run. The mechanical fix for each
landed OUT-OF-PIPELINE under `harden(…)` commits; this SPEC is the durable audit trail.

## GAP 1 (HIGH — BLOCKING) — bug pipeline provides no seam to author `GATE_VERDICT.md`

**Symptom (verified).** `lazy_core.gate_verdict_ok` (`user/scripts/lazy_core/gates.py:108`) is
LIVE and BLOCKING inside `apply_pseudo`'s `__mark_fixed__`/`__mark_complete__` branch
(`user/scripts/lazy_core/pseudo.py`): any item whose shipped commits touch a
`docs/gate/control-surfaces.json` glob is refused unless a `GATE_VERDICT.md` exists in the item
dir. But `harness-change-gate.md` says the verdict is authored "at the planning seam", and
neither `/plan-bug`, `/spec-phases`, nor `/spec` actually injected it — so the plan never carried
a `GATE_VERDICT.md` deliverable and `/execute-plan` never authored it. There was ALSO no
registered completion-time authoring dispatch class (`coherence-recovery` is PHASES-scoped;
`hardening`'s emit-context is guard-deny-shaped), and the orchestrator may not improvise the
adversarial answers (HARD CONSTRAINT 1). Net: an in-scope harness-change bug is refused at
completion with NO recovery path. This run parked
`docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs/` on exactly this.

**Root cause (classification: missing-contract).** The ship seam (`gate_verdict_ok`) was wired
live-blocking before any authoring seam existed. The verdict is inherently a POST-diff artifact
(the adversarial questions key on the actual shipped diff shapes), so a completion-time authoring
dispatch is the timing-correct seam.

**Fix scope.** Add a registered completion-time `gate-verdict` dispatch class
(`DISPATCH_CLASSES`/`DISPATCH_MODELS`=opus/`DISPATCH_STEP_NAMES`) + template
`dispatch-gate-verdict.md` (runs `harness-gate.py` over `origin/main..HEAD`, works the adversarial
questions per `harness-change-gate.md`, authors `GATE_VERDICT.md`; a `gate_weakening` hit escalates
to `NEEDS_INPUT.md` for operator sign-off, never self-approved). Route it in `/lazy-batch` +
`/lazy-bug-batch` on a `__mark_*__` refusal naming the harness-change design gate (distinct from
the coherence-recovery route). Reconcile the stale "SEAM-DEFERRED" claims (root `CLAUDE.md` ×2,
`user/scripts/CLAUDE.md`, the `pseudo.py` comment) to "WIRED + live-blocking".

## GAP 2 (MEDIUM) — `is_fixed_unreconciled` only keys on `**Fixed:**`, misses `## Fix (implemented …)`

**Symptom (verified).** `is_fixed_unreconciled` (`gates.py`) / `spec_fixed_annotation`
(`docmodel.py`) key ONLY on the inline `**Fixed:**` annotation. A SPEC that records an
out-of-pipeline fix under a `## Fix (implemented <date>)` heading instead (e.g.
`docs/bugs/build-queue-timeout-kill-reaps-detached-runner/SPEC.md`, fix landed 2026-07-10, Pester
8/8, still `Status: Concluded`) is neither diverted nor reconciled → it burns a full plan-bug round.

**Root cause (extension gap).** The detector recognizes only one of two in-use out-of-pipeline-fix
conventions. **Fix:** add `docmodel.spec_fix_implemented_heading` and treat
`spec_fixed_annotation(...) or spec_fix_implemented_heading(...)` as the fixed signal; the Step-4
divert branch shape is unchanged (no routing-parity allowlist change).

## GAP 3 (LOW — usability) — `spec_path` positional is polymorphic and rejects the wrong shape

**Symptom (verified).** `--apply-pseudo __mark_fixed__/__grant_skip…/__write_validated_from_skip__`
and `--archive-fixed` treat the positional as the item DIRECTORY (`spec_path / "FIXED.md"`,
`bug_id = spec_path.name`), while `--verify-ledger`/`--gate-coverage` treat it as the `SPEC.md`
FILE — all named `<spec_path>` in `--help`. Passing `SPEC.md` to a dir-expecting subcommand yields
a confusing precondition refusal that is really a path-shape mismatch (and `gate_coverage(SPEC.md)`
computes `<dir>/SPEC.md/SPEC.md`).

**Root cause (usability).** No normalization at the dir-expecting sites (the `--verify-ledger`
precedent already normalizes). **Fix:** add `docmodel.normalize_item_dir` (a `SPEC.md` file →
parent; conservative — keys on the exact `SPEC.md` basename) and apply it in `apply_pseudo`,
`archive_fixed`, and `gate_coverage` so every `spec_path`-taking subcommand accepts EITHER shape.

## GAP 4 (LOW — cosmetic) — audit-obligation emit pairs the wrong `item_name`

**Symptom (verified).** On the `route_overridden_by: audit-obligation` withhold path, the
`input_audit_emit_command` (`lazy-state.py` / `bug-state.py`) sets `item_name=state.feature_name`
unconditionally — the NEXT queued item's name — while `item_id`/`spec_path` correctly point at the
pending-audit item. The audit reads the right SPEC (harmless functionally), but the cycle_header
label is wrong.

**Root cause (missed conditional).** `item_name` did not mirror the `_aud_spec_path` guard.
**Fix:** use `feature_name` only when `feature_id == obligation.item_id`, else fall back to the
pending-audit item's own slug. Coupled-pair mirror on both scripts.

## Reproduction Steps
- GAP 1: drive a bug whose fix touches `user/scripts/**` through `__mark_fixed__` → refused
  `harness-change design gate: … GATE_VERDICT.md` with no route to author it.
- GAP 2: a `Concluded` bug SPEC with a `## Fix (implemented …)` heading (no `**Fixed:**`) →
  routed to `/plan-bug` instead of reconciliation.
- GAP 3: `bug-state.py --archive-fixed docs/bugs/<id>/SPEC.md` → refusal about a missing
  `FIXED.md` receipt (path-shape mismatch, not a real gate failure).
- GAP 4: arm an audit obligation for item A, probe while the head is item B → the emit command's
  `item_name` is B's name.

## Fix (implemented 2026-07-19)
Landed OUT-OF-PIPELINE under `harden(…)` commits (see FIXED.md for the receipt + green gate
evidence). Tests added: `test_gates.py` (GAP 2/3), `test_ledgers.py` (GAP 4), `test_dispatch.py`
(GAP 1). Follow-up note: the parked bug
`adhoc-plan-bug-no-guard-for-fixed-annotated-specs` is now completable — on its next drive, the
`__mark_fixed__` refusal routes `--emit-dispatch gate-verdict`, which authors its clean verdict.
