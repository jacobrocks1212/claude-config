# Completion-gate refusal names the failing check but not the failing items — Investigation Spec

> `__mark_complete__`'s precondition gate (`--verify-ledger`) refuses with only a boolean
> `failing_check` name — `deliverables_done` without the unchecked rows, `clean_tree` without
> the dirty files, `head_matches_origin` without the shas — so agents use the gate itself as
> discovery, probing repeatedly per feature (184 gate-refusal tool errors across 48+ mined
> sessions). The 2026-07-11 `62fdba2` hardening made the OTHER refusal surface (the
> `apply_pseudo` coherence gate) partially actionable; the `verify_ledger` surface — where the
> 146/29/9 refusals actually occur — still computes the diagnostic data and throws it away.

**Status:** Fixed
**Priority:** P2
**Last updated:** 2026-07-12
**Related:** commit `62fdba2` (2026-07-11, "actionable completion-refusal — split shim vs genuine unchecked rows" — the coherence-gate advisory this spec scopes AROUND) + `b9dfab2` (Round 22 docs); `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` #5 (per-row host-deferral — the design fork `62fdba2`'s advisory defers to); `docs/specs/lazy-validation-readiness/` Phase 9 WU-3 (plan-scoped `verify_ledger`); `docs/bugs/meta-dispatch-not-by-reference-and-ack-overpriced/` + `docs/bugs/loop-detector-false-positives-probes-and-cross-run-state/` (sibling specs mined from the same runs — repeated gate probes also feed the loop counters).

## Verified Symptom

Transcript mining across 48+ sessions (2026-06/07): **184 gate-refusal tool errors** where the `__mark_complete__` completion path returns `ok: false` with only a `failing_check` name:

- `failing_check: deliverables_done` — **146×** (no listing of WHICH unchecked rows block; agents re-open PHASES.md / plan parts and diff by hand),
- `failing_check: clean_tree` — **29×** (no listing of the dirty files),
- `failing_check: head_matches_origin` — **9×** (no head/upstream shas, no ahead/behind, no "no upstream configured" distinction).

Because the verdict is not predictable from the payload, agents use the gate itself as discovery — often **multiple probes per feature** (sessions `13484aa5`, `17fe2d37`, `180f2a40`): probe → refusal → guess → edit → re-probe. Each wasted probe is also a same-step re-read that interacts with the loop-detector counters (sibling spec).

## Root Cause

**Classification: `missing-diagnostic-payload`.** There are TWO refusal surfaces; the July-11 work improved one axis of one of them. Current-code characterization (verified 2026-07-11):

### Surface A — `verify_ledger` (`user/scripts/lazy_core.py` ~3592–3868): **still opaque on all four axes**

Invoked via `--verify-ledger` (both `lazy-state.py` ~12490 and `bug-state.py`) as the completion-ledger precondition the orchestrator runs before `__mark_complete__` / `__mark_fixed__`; exit-1 refusals emit a `gate-refusal` telemetry event carrying ONLY `{gate, failing_check}`. The return shape is `{ok, failing_check, checks:{4 booleans}, deliverables_source}`. The function already COMPUTES every missing diagnostic and discards it:

- **`clean_tree`** (~3688): runs `git status --short`, tests `result.stdout.strip() == ""`, then throws the stdout away — the dirty-file list is in hand and not returned.
- **`head_matches_origin`** (~3701): computes `head_sha` and `upstream_sha`, returns only the equality boolean — no shas, and the "no upstream configured" branch is indistinguishable from a genuine divergence.
- **`plan_complete`** (~3731): feature-level mode computes `incomplete_plans = find_implementation_plans(spec_path)` — the exact list of non-Complete plans — and returns only the boolean.
- **`deliverables_done`** (~3767): all three source branches (plan-WU checkboxes / phases-fallback / feature-level) count or collect the unchecked rows, then reduce to a boolean. `deliverables_source` (which SURFACE decided) is the only diagnostic — the ROWS are absent.

### Surface B — `apply_pseudo __mark_complete__` coherence gate (`lazy_core.py` ~4834–4885): **partially actionable since `62fdba2`**

The residual-incoherence refusal has always named each offending PHASE with its unchecked count (`_phase_completion_plan`, ~2872: `"{heading}: N unchecked box(es)"` / `'status "X" not Complete/Superseded'`). `62fdba2` (2026-07-11) added `classify_blocking_unchecked_rows` (~2395) and an advisory that splits blocking rows into un-migrated verification-SHIM rows vs GENUINE incomplete deliverables — **with row excerpts for the shim class only**. Still opaque on this surface: the `genuine` rows are reported as a COUNT (`cls["genuine"]` excerpts are collected at ~2475 but never printed at ~4866–4879), and no refusal on either surface carries line numbers.

### Adjacent boolean-only mirrors

`git_guard_status` (~6431, the probe's `git_guards` fold) intentionally mirrors the same three booleans — acceptable for the advisory probe fold, but it means NO surface anywhere in the pipeline ever shows the dirty files or the divergence. `evaluate_completion_evidence` (~2963) already returns a human-readable `reason` and is NOT part of this defect.

## Fix Scope (Concluded)

Every refusal payload carries the first N offending items so ONE probe is diagnostic. All additions are DIAGNOSTIC-ONLY — no gate decision changes, matching `62fdba2`'s discipline.

1. **`verify_ledger` payload enrichment** (the primary fix — covers 184/184 mined refusals). Add a `failing_detail` object populated for whichever checks are False:
   - `clean_tree` → first N lines of the already-captured `git status --short` stdout (+ total count),
   - `head_matches_origin` → `{head_sha, upstream_sha}` short shas, ahead/behind counts (`git rev-list --left-right --count @{u}...HEAD`), and an explicit `no_upstream: true` discriminator for the unconfigured-upstream branch,
   - `plan_complete` → the already-computed non-Complete plan filenames + their parsed statuses (plan-scoped mode: this plan's status literal),
   - `deliverables_done` → the first N unchecked row texts **with line numbers**, from whichever surface `deliverables_source` names (plan-WU rows or PHASES rows), reusing the existing collectors.
   Cap N (~10) and truncate row excerpts (mirror `classify_blocking_unchecked_rows`'s 80-char excerpt convention) so the JSON stays probe-sized.
2. **Surface B completion:** print the `genuine` row excerpts (not just the count) in the `62fdba2` advisory — the list is already collected; add line numbers to both classes while touching it.
3. **Telemetry parity:** the `gate-refusal` event gains a compact `detail_head` so incident mining can distinguish "dirty tree: 1 stray log file" from "dirty tree: 14 uncommitted source files" without transcript access.
4. **Coupled-pair mirroring** (`bug-state.py` shares `lazy_core.verify_ledger` — verify its `--verify-ledger` handler forwards the enriched payload) + `test_lazy_core.py` fixtures per axis (each failing check carries its items; `ok: true` payload shape unchanged) + SKILL prose: the refusal is now self-diagnosing — a second discovery probe is a deviation.

## Decisions

- **D1 — Payload shape (fix-planning):** a single `failing_detail` object keyed by check name (recommended — additive, `ok`/`failing_check`/`checks` untouched for existing consumers) vs per-check sibling keys. Mechanical-internal; resolve at `/plan-bug`.
- **D2 — N and truncation caps (fix-planning):** default N=10 items / 80-char excerpts, matching the existing classifier convention. Mechanical-internal.
- **D3 — Scope boundary (RESOLVED):** the shim-row migration semantics and per-row host-deferral remain owned by `turn-routing-enforcement` NEEDS_INPUT #5 — this spec adds visibility only, never a new tick/migration path.
