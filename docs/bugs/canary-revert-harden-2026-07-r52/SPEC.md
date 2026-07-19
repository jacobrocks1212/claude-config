# Canary trip triage: harden-2026-07-r52 — Investigation Spec

> The harness-change canary for intervention `harden-2026-07-r52` (mid-run budget + park controls) tripped on a band-only rise of `event:gate-refusal`; triage whether to revert, redesign, or close-as-noise.

**Status:** Won't-fix
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/canary-revert-harden-2026-07-r52
**Related:** docs/interventions/harden-2026-07-r52.md · docs/bugs/lazy-batch-no-mid-run-budget-or-park-controls/ · `harness-change-canary-rollback` · `efficacy-signal-integrity` (D1 sub-signals)

<!-- Status lifecycle:
  - Investigating → active investigation; bug-state.py routes to /spec-bug.
  - Concluded     → root cause proven + disposition chosen; bug-state.py routes to /plan-bug.
  This SPEC stays Investigating: the trip's root cause is proven (below), but the
  DISPOSITION (revert / redesign / close-as-noise) is a product-class operator call —
  reverting removes a shipped operator-facing feature — parked in NEEDS_INPUT.md.
-->

---

## Verified Symptoms

1. **[VERIFIED]** The `harden-2026-07-r52` canary is in `status: tripped` (`docs/interventions/harden-2026-07-r52.md` frontmatter, `canary_revert_enqueued: '2026-07-18'`). This ad-hoc bug is the flag-and-enqueue product of that trip (D4 — nothing was reverted automatically).
2. **[VERIFIED]** Trip reason is a **band-only** movement: targeted signal `event:gate-refusal` regressed **+57.9%** vs the frozen baseline 4.75 ev/run (→ 7.5 ev/run), band ±25%, 30 post-ship occurrences over 4 window runs. **Zero** attributable fresh incidents (`EVIDENCE.md`: "(none — band-only trip)").
3. **[VERIFIED]** The observed movement is an **increase**, but the intervention's declared `expected_direction` is **decrease** (`docs/interventions/harden-2026-07-r52.md:10`). The trip is not "the hypothesis failed to help" — it is the aggregate moving the wrong way.

## Reproduction Steps

1. `python3 user/scripts/efficacy-eval.py --repo-root . --canary --dry-run --id harden-2026-07-r52` — inspect the canary trip verdict for this intervention.
2. Read `docs/bugs/canary-revert-harden-2026-07-r52/EVIDENCE.md` — the frozen trip evidence (band numbers, commit set, coupled-pair scope).
3. `git show --stat bc03240e065cb8ad8ac7bdbe203b7d555c09580c` — the revert-target commit set.

**Expected:** A canary trip identifies a shipped change that measurably worsened its targeted friction signal, attributable to the change.
**Actual:** The trip fired on a coarse aggregate signal (`event:gate-refusal`) the shipped change is mechanically incapable of emitting into, with no attributed incidents (see Proven Findings).
**Consistency:** Deterministic — the trip is frozen in the record; the evidence numbers are fixed.

## Evidence Collected

### Source Code

Commit `bc03240e` (`harden(script): add operator-authorized mid-run budget + park controls`) touched: `user/scripts/{lazy-state.py,bug-state.py}`, `user/scripts/lazy_core/{__init__.py,markers.py}`, `user/skills/lazy-batch/SKILL.md`, plus `docs/cli/cli-surface.json` + tests. It added three orchestrator-only CLI actions — `--set-max-cycles`, `--set-park`, `--set-park-provisional` — and the `set_marker_max_cycles` / `set_marker_park` in-place marker mutators + `fold_max_cycles` / `fold_park_flags` folding.

Each new CLI action guards with `lazy_core.refuse_if_cycle_active(...)` and `_die(...)`:
- `refuse_if_cycle_active` (`user/scripts/lazy_core/markers.py:2397`) emits a **`containment-refusal`** telemetry event (`markers.py:~2470`, `append_telemetry_event("containment-refusal", ...)`) then `sys.exit(3)`. It does **not** emit `gate-refusal`.
- `_die` (`lazy-state.py`) prints to stderr and exits with **no telemetry emission at all** (grep for `append_telemetry` inside `_die` → empty).

The `gate-refusal` telemetry emitters (`ledgers.py:2414` closed set; `_GATE_REFUSAL_SIGNATURES` = `gate-coverage`, `unacked-hardening`, `efficacy-coverage-missing`, `checkpoint-auth`, `apply-pseudo`, `verify-ledger`) live on the completion-gate / verify-ledger paths — none of which this commit modifies.

### Runtime Evidence

Band-only trip: `EVIDENCE.md` records **zero** attributed fresh incidents. The +57.9% is a movement in the aggregate `event:gate-refusal` count (baseline 4.75 → post 7.5 ev/run) over a small window (4 runs, 30 occurrences).

### Git History

Revert target: `bc03240e065cb8ad8ac7bdbe203b7d555c09580c` (single commit; `degraded_revert_note: null` — a plain `git revert` is expected to back it out).

### Related Documentation

- `docs/interventions/CLAUDE.md` → "The `canary:` sub-map": a bare, undivided `event:gate-refusal` declaration "conservatively confounds every sub-signal of its type" (`efficacy-signal-integrity` D1/D6). This intervention declared exactly that bare target (`target_signal: event:gate-refusal`, no `/<signature>` sub-signal).
- `docs/kpi/registry.json` → `canary-trip-precision` KPI measures the fraction of trips whose revert item was **not** closed-as-noise — a close-as-noise disposition here is itself the tracked signal for canary-band tuning.

## Theories

### Theory 1: Coarse-signal false-positive (attribution failure)
- **Hypothesis:** The trip is a false-positive: `event:gate-refusal` is a coarse aggregate of ≥6 unrelated gate signatures; the shipped change emits none of them, so the aggregate rise reflects other gates firing (co-shipped hardening rounds / normal pipeline activity), not this change.
- **Supporting evidence:** New refusal paths emit `containment-refusal`/nothing, not `gate-refusal` (traced, below). Band-only trip, zero attributed incidents. Small window (4 runs). Bare undivided target signal → conservatively confounded.
- **Contradicting evidence:** None mechanical. The only residual risk is an *indirect* effect (see Theory 2).
- **Status:** Likely.

### Theory 2: Indirect real regression via marker folding
- **Hypothesis:** The new `RUN_FRESH_FIELDS` (park_*) + `fold_max_cycles`/`fold_park_flags` changed marker folding in a way that made an *unrelated* gate (verify-ledger / apply-pseudo) refuse more often.
- **Supporting evidence:** The commit does change marker read/fold semantics that gates downstream consume.
- **Contradicting evidence:** No attributed incidents; 5 regression tests passed; no gate-refusal emitter was touched; no fresh-incident signature points at any of the six gate signatures.
- **Status:** Unverified (unevidenced — the reason the disposition is parked rather than auto-closed).

## Proven Findings

- **[traced] The shipped change is mechanically incapable of emitting the tripped signal.** Serving-path trace for the `gate-refusal` count:
  ```
  event:gate-refusal count (aggregate)
    → append_telemetry_event("gate-refusal", data={"gate": <sig>})   user/scripts/lazy-state.py:13176,13511,13577,13643,13996,14400 · bug-state.py:9021
    → closed signature set _GATE_REFUSAL_SIGNATURES                   user/scripts/lazy_core/ledgers.py:2420
       (gate-coverage | unacked-hardening | efficacy-coverage-missing | checkpoint-auth | apply-pseudo | verify-ledger)
  ```
  The shipped change's new refusal paths route to a DISJOINT surface:
  ```
  --set-max-cycles / --set-park / --set-park-provisional   lazy-state.py:14116-14153
    → lazy_core.refuse_if_cycle_active(...)                 user/scripts/lazy_core/markers.py:2397
       → append_telemetry_event("containment-refusal", ...) markers.py:~2470  → sys.exit(3)
    → _die(...)                                             (stderr print, NO telemetry)
  ```
  Neither path reads or writes any node on the `gate-refusal` serving path. The +57.9% cannot be produced by this change's code. (Fix-site-on-path rule: a revert would change nodes NOT on the tripped signal's path.)
- The intervention's target signal was a **bare, undivided `event:gate-refusal`** — the coarsest legitimate target, which the efficacy machinery treats as confounded by every co-shipped hardening round and all normal gate activity.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Intervention record | `docs/interventions/harden-2026-07-r52.md` | Canary `status: tripped`; disposition pending |
| Shipped change (revert target) | `user/scripts/{lazy-state.py,bug-state.py,lazy_core/__init__.py,lazy_core/markers.py}`, `user/skills/lazy-batch/SKILL.md` | The operator-facing mid-run budget/park controls a revert would remove |
| Coupled-pair scope (revert must cover whole pair) | `user/skills/{lazy-batch,lazy-bug-batch}/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | A revert MUST end with a green `lazy_parity_audit.py` |
| Canary signal design | `docs/interventions/harden-2026-07-r52.md` (`target_signal`), `efficacy-eval.py` sub-signal resolution | The coarse target that produced the false-positive; close-as-noise implies a sub-signal/band tuning follow-up |

## Open Questions

- Did any of the six `gate-refusal` signatures actually rise in the window, or is the aggregate driven entirely by co-shipped activity? (Theory 2 — would need per-signature ledger counting to fully rule out an indirect regression; not resolvable from the frozen band-only evidence alone.)
- Disposition — **revert / redesign / close-as-noise** — is a product-class operator decision (revert removes a shipped feature). Surfaced in `NEEDS_INPUT.md`.

## Resolution

Operator-accepted the recommended **close-as-noise** disposition (`NEEDS_INPUT.md`, recorded via
`bug-state.py --record-decision`). The shipped mid-run budget/park controls (`bc03240e`) are
correct and cause-traced as off the tripped `event:gate-refusal` signal's serving path — band-only
trip, zero attributed incidents; **retained, not reverted**. Canary/sub-signal band tuning is
tracked separately, not as a phase of this bug. Closed without a fix.
