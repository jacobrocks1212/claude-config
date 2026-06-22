# Scoped `--bug-id` query loses a deferred bug's identity (renders as "unknown" in LAZY_QUEUE.md) — Investigation Spec

> `bug-state.py --bug-id <deferred-bug>` ignores the scope and returns the GLOBAL `all-remaining-deferred` terminal with `feature_id: null`, and `curated_stage.py` has no mapping for that terminal. So the `pipeline_visualizer.probe` (and `lazy-queue-doc.py` on top of it) gets no id/stage for an operator-deferred bug, and renders it as a broken `[unknown](docs/bugs/unknown/SPEC.md)` row instead of the intended `⏸ Deferred` row with a working SPEC link.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-22
**Fixed:** 2026-06-22
**Fix commit:** 4da82a8
**Placement:** docs/bugs/bug-state-scoped-query-loses-deferred-bug-identity
**Related:** `docs/features/mobile-queue-control` (the feature whose generated `LAZY_QUEUE.md` surfaced this); `docs/bugs/feature-queue-lacks-on-disk-autodiscovery` (sibling defect discovered the same session, also via mobile-queue-control); `user/scripts/bug-state.py` (`compute_state` scoped-query loop, ~601–911); `user/scripts/pipeline_visualizer/curated_stage.py` (`_SIDE_STATE_BY_TERMINAL`); `user/scripts/pipeline_visualizer/probe.py` (`probe_state` bug loop, ~190–205); `user/scripts/lazy-queue-doc.py` (`_item_id`, `_render_table`); `user/scripts/lazy_parity_audit.py` (coupled-pair parity — the latent feature-side twin)

---

## Verified Symptoms

<!-- All VERIFIED by direct reproduction this session (commands run, output observed), not by user report. -->

1. **[VERIFIED]** In a repo with operator-deferred bugs (AlgoBooth: `golden-manifest-missing-baselines`, `non-windows-audio-output-unvalidated`, `pattern-bank-localstorage-quota`, each carrying a `DEFERRED.md`), `python user/scripts/lazy-queue-doc.py --repo-root <AlgoBooth> --stdout` renders those three bug rows as `[unknown](docs/bugs/unknown/SPEC.md)` with state `Pending` — broken SPEC links on the GitHub-mobile read surface. Non-deferred bugs and all features render correctly. — directly reproduced.
2. **[VERIFIED]** The underlying cause: `python user/scripts/bug-state.py --repo-root <AlgoBooth> --bug-id golden-manifest-missing-baselines` returns `{"feature_id": null, ..., "current_step": "All remaining bugs are operator-deferred", "terminal_reason": "all-remaining-deferred"}` — i.e. the scoped query returns the GLOBAL deferred terminal, not a per-bug state. A non-deferred scoped query (`--bug-id mcp-corpus-synth-pseudo-method-false-green`) correctly returns `feature_id` + a real `current_step`. — directly reproduced.
3. **[VERIFIED]** The generator already anticipates the correct render: `lazy-queue-doc.py` defines `_STAGE_GLYPH["Deferred"] = "⏸"` and `_NEXT_ACTION["Deferred"]`, but the `Deferred` stage never arrives for these bugs — the wiring is effectively dead code for the operator-deferred case. — confirmed in source.

## Reproduction Steps

1. In a repo whose `docs/bugs/` contains at least one bug with a `DEFERRED.md` sentinel (operator-parked), e.g. AlgoBooth.
2. `python ~/.claude/scripts/bug-state.py --repo-root <repo> --bug-id <deferred-bug-id>` → observe `feature_id: null`, `terminal_reason: all-remaining-deferred`.
3. `python ~/.claude/scripts/lazy-queue-doc.py --repo-root <repo> --stdout` → observe the deferred bug rendered as `[unknown](docs/bugs/unknown/SPEC.md)`, state `Pending`.

**Expected:** the deferred bug renders as its own row — `[<bug-id>](docs/bugs/<bug-id>/SPEC.md)` with state `⏸ Deferred` and a working SPEC link, and appears appropriately in triage.
**Actual:** rendered as `[unknown](docs/bugs/unknown/SPEC.md)`, state `Pending`, broken link.
**Consistency:** Always, for any bug carrying `DEFERRED.md` when queried with `--bug-id`.

## Evidence Collected

### Source Code

Root cause is a **two-part** interaction, both in claude-config tooling:

**Part 1 — `bug-state.py` scoped query falls through to a global terminal (the primary cause).**
`compute_state`'s queue loop (`user/scripts/bug-state.py` ~601–832) honors `--bug-id` scoping at ~620–623 (`scope_id_seen = True` on match), but the operator-deferred skip at ~766–775 does `continue` on the matched-and-deferred entry:

```python
deferred_md = spec_dir / "DEFERRED.md"
if deferred_md.exists():
    _OPERATOR_DEFERRED.append(bug_name)
    ...
    continue
```

The loop then ends with `current is None`, and the no-actionable-bug block (~837–911) returns the **global** terminal at ~859–871:

```python
if _OPERATOR_DEFERRED:
    return _bug_state(
        terminal_reason=TR_ALL_DEFERRED,
        current_step="All remaining bugs are operator-deferred",
        ...   # NOTE: no feature_id / feature_name / spec_path
    )
```

Contrast the **completion-unverified** branch at ~642–654, which DOES return a *scoped* `_bug_state(feature_id=bug_id, feature_name=bug_name, spec_path=...)`. The deferred/cloud-saturated/device-saturated/parked skip branches do not — so a scoped query against any of those states loses the bug's identity. For the probe's per-item use case (one `--bug-id` call per queue entry), this collapses the bug to a null-identity global terminal.

**Part 2 — `curated_stage.py` has no mapping for `all-remaining-deferred`.**
`_SIDE_STATE_BY_TERMINAL` (`user/scripts/pipeline_visualizer/curated_stage.py` ~25–32) maps `cloud-queue-exhausted` and `device-queue-exhausted` → `Deferred`, but **not** `all-remaining-deferred`. So even if Part 1 emitted a scoped state for a deferred bug, the curated stage would still roll up to `Pending` (Rule 3 default) rather than `Deferred`.

**Downstream (correct, no change needed) — `probe.py` + `lazy-queue-doc.py`.**
`probe.probe_state` (~190–205) faithfully relays whatever `bug-state.py` emits; with `feature_id: null` it has no id to attach. `lazy-queue-doc.py::_item_id` then falls back to the literal `"unknown"` and `_rel_spec_path` builds `docs/bugs/unknown/SPEC.md`. These are doing the right thing given bad upstream data — the fix belongs in Parts 1 + 2, not here.

### Runtime Evidence

Direct command output captured this session (AlgoBooth as the target repo): the three `DEFERRED.md`-carrying bugs each return `feature_id: null` + `current_step: "All remaining bugs are operator-deferred"`; the generated `LAZY_QUEUE.md` shows them as `unknown` rows. (No app/session-log runtime involved — this is a pure CLI/tooling defect.)

### Git History

Discovered 2026-06-22 while generating AlgoBooth's `LAZY_QUEUE.md` for the just-completed `mobile-queue-control` feature. Same session as the sibling `feature-queue-lacks-on-disk-autodiscovery` bug — both are integration gaps surfaced by exercising the new mobile read surface against a real repo.

### Related Documentation

- `docs/features/mobile-queue-control/SPEC.md` — the feature; its layout sketch explicitly wants per-item rows linking to each `SPEC.md`, and the generator carries `Deferred` glyph/next-action wiring, confirming `⏸ Deferred` is the intended render.
- `docs/bugs/CLAUDE.md` — harness-defect investigation contract (Investigating → Concluded → /plan-bug).

## Theories

### Theory 1: Scoped skip-branches that don't return a scoped state (CONFIRMED)
- **Hypothesis:** Any `compute_state` skip branch that `continue`s on a `--bug-id`-matched entry (operator-deferred, cloud-saturated, device-saturated, parked) loses the bug identity by falling through to a global, null-identity terminal.
- **Supporting evidence:** Direct repro for the operator-deferred case; source shows completion-unverified is the only matched-entry branch that returns a scoped `_bug_state`.
- **Status:** Confirmed (operator-deferred path). The cloud/device/parked variants are structurally identical and **suspected** to share the defect (not separately reproduced).

### Theory 2: Missing `all-remaining-deferred` curated-stage mapping (CONFIRMED)
- **Hypothesis:** `curated_stage` does not roll `all-remaining-deferred` up to `Deferred`.
- **Supporting evidence:** `_SIDE_STATE_BY_TERMINAL` omits it (only cloud/device-queue-exhausted present).
- **Status:** Confirmed in source.

## Proven Findings

1. **Primary root cause:** `bug-state.py::compute_state`, when `--bug-id` is set and the matched bug carries `DEFERRED.md`, returns the global `TR_ALL_DEFERRED` terminal with no `feature_id`/`spec_path` instead of a per-bug deferred state.
2. **Secondary root cause:** `curated_stage._SIDE_STATE_BY_TERMINAL` lacks an `all-remaining-deferred → Deferred` entry.
3. **Downstream is correct:** the probe and generator faithfully render the bad upstream data; `unknown` is the honest fallback for a null id.
4. **Latent parity twin (feature side):** `lazy-state.py --feature-id` very likely exhibits the same scoped-query-loses-identity pattern for its global deferral terminals (`cloud-queue-exhausted`, `device-queue-exhausted`, host-capability-saturated). Not observed in the current AlgoBooth doc only because no feature is in those states on this host. Any fix must be checked against the coupled-pair parity audit and likely mirrored.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Scoped-query identity (primary) | `user/scripts/bug-state.py` (`compute_state` skip branches ~666–824 + no-actionable block ~837–911) | When `--bug-id` matches a skipped (deferred/cloud/device/parked) entry, return a **scoped** `_bug_state(feature_id=bug_id, spec_path=…, current_step=<per-bug deferred>, terminal_reason=<deferred>)` rather than the global null-identity terminal. |
| Curated stage rollup (secondary) | `user/scripts/pipeline_visualizer/curated_stage.py` (`_SIDE_STATE_BY_TERMINAL`) | Add `all-remaining-deferred → "Deferred"` (and any new per-bug deferred terminal introduced by the primary fix). |
| Coupled-pair parity | `user/scripts/lazy-state.py` (feature-side `--feature-id` scoped query); `user/scripts/lazy_parity_audit.py` | Verify/mirror the scoped-identity behavior on the feature side; keep the parity audit green. |
| Downstream (no change) | `pipeline_visualizer/probe.py`, `lazy-queue-doc.py` | Correct once upstream emits id + Deferred stage; `unknown` fallback retained as a defensive last resort. |
| Tests | `bug-state.py --test`, `lazy-queue-doc.py`/probe tests | Add: scoped `--bug-id` on a deferred bug returns its own id + a Deferred-mapping terminal; generator renders `⏸ Deferred` with a real SPEC link (no `unknown`). |

## Fix Scope (for /plan-bug)

- **Primary:** make scoped `--bug-id` queries identity-preserving for skipped-but-matched entries. Cleanest mechanism (settle in planning): when `scope_bug_id` is set and equals the current entry's id, the operator-deferred (and analogously cloud/device/parked) branch returns a scoped `_bug_state` carrying `feature_id`/`feature_name`/`spec_path` plus a per-bug deferred `current_step`/`terminal_reason`, instead of `continue`-ing into the global terminal. Preserve today's UNSCOPED behavior exactly (global `TR_ALL_DEFERRED` when no `--bug-id`) so `/lazy-bug-batch` queue-advance is unaffected.
- **Secondary:** add the `all-remaining-deferred → Deferred` curated-stage mapping (and any new per-bug deferred terminal name).
- **Parity (HARD):** check the feature-side twin in `lazy-state.py`; mirror if present; run `lazy_parity_audit.py`; keep both `--test` suites green.
- **Reuse:** model the scoped-return on the existing completion-unverified branch (~642), which already returns a scoped `_bug_state` from inside the loop.
- **Guard:** add a regression test asserting `lazy-queue-doc.py` emits no `docs/bugs/unknown/SPEC.md` link for a repo containing a `DEFERRED.md` bug.

## Open Questions

- Should the primary fix introduce a NEW per-bug terminal_reason (e.g. `operator-deferred`) for the scoped case, or reuse `all-remaining-deferred` with the scoped fields populated? (Affects how many curated-stage entries Part 2 needs.)
- Confirm whether the cloud-saturated / device-saturated / parked scoped branches need the identical treatment now, or only operator-deferred (the only one reproduced). Recommend fixing all four for consistency.
- Confirm the feature-side parity twin exists and whether it should be fixed in the same change (coupling rule) or filed separately.
