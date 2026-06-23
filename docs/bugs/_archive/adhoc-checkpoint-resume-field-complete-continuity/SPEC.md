# Checkpoint resume continuity is field-by-field, not field-complete — Investigation Spec

> A sanctioned same-run checkpoint resume re-mints ALL run-scoped marker state on the resuming `--run-start`; every continuity field must be carried back individually by `restore_checkpoint_counters`. Each missing field has been patched reactively (whack-a-mole). Durable fix: make resume continuity field-complete BY CONSTRUCTION via an enumerated allow-list of carry vs. reset marker fields.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-23
**Fixed:** 2026-06-23
**Fix commit:** 67e48c4
**Placement:** docs/bugs/adhoc-checkpoint-resume-field-complete-continuity
**Related:** docs/bugs/single-slot-marker-ownership-race-disarms-owning-run · hardening Round 35 (commit `821628e`) · the 2026-06-14 `operator-checkpoint-resume-counter-reset` round · `refuse_run_start_clobber` (Round 19) · `user/scripts/CLAUDE.md` → "Checkpoint resume is provenance-branched"

---

## Verified Symptoms

<!-- This is a harness self-investigation in --batch. "Verified" here = proven directly from source + git history (the authoritative evidence for a deterministic state script), not via interactive AskUserQuestion. -->

1. **[VERIFIED]** `write_run_marker` (`lazy_core.py:8861`) UNCONDITIONALLY mints a fresh value for every run-scoped marker field on the resuming `--run-start` — `started_at`, `forward_cycles: 0`, `meta_cycles: 0`, `last_advance_consume_count: 0`, `per_feature_forward_cycles: {}`, `per_feature_corrective_cycles: {}`, `last_advance_state_key` (absent), `nonce_seed`. There is no notion of "this field must survive a same-run resume" at the mint site. — read of the marker dict literal at `lazy_core.py:8861-8907`.
2. **[VERIFIED]** Continuity is reconstructed AFTER the mint, field-by-field, in `restore_checkpoint_counters` (`lazy_core.py:12584`). Today it explicitly carries back exactly four values in the non-operator-authorized branch: `forward_cycles`, `meta_cycles` (`:12679-12680`), `started_at` (`:12693-12705`), and `last_advance_consume_count = 0` (`:12708`). Any run-scoped field NOT named here silently keeps `write_run_marker`'s freshly-minted reset value. — read of `restore_checkpoint_counters:12653-12711`.
3. **[VERIFIED]** This has been patched reactively TWICE after a field was found un-restored: (a) the 2026-06-14 / 2026-06-17 `operator-checkpoint-resume-counter-reset` round added `forward_cycles`/`meta_cycles`/`last_advance_consume_count`; (b) hardening Round 35 (commit `821628e`, 2026-06-23) added `started_at` (the run identity) after a minted identity false-tripped `detect_cycle_bracket_friction` signal (a) — observed begin `03:15:38Z` != end `05:41:28Z`. — `git show 821628e` + the two dated comment blocks at `:12513-12531` and `:12597-12624`.
4. **[VERIFIED]** The defect is structural: a NEWLY-ADDED run-scoped marker field defaults to the RESET side by construction (it is born in the `write_run_marker` literal, and `restore_checkpoint_counters` does not know about it), so the next continuity field is a latent third whack-a-mole waiting to false-trip a friction/budget signal. — inferred directly from the two-site mint/restore split (symptoms 1+2).

## Reproduction Steps

1. A `/lazy-batch` run hits a sanctioned automatic reliability pause (e.g. cloud ≥2 guard denials, overnight unattended pause). `--run-end --reason checkpoint` writes `lazy-run-checkpoint.json` (`operator_authorized: false`), snapshotting `counters` + `run_started_at`.
2. The run resumes. The resuming `--run-start` calls `write_run_marker` → ALL run-scoped fields minted fresh (counters 0/0, fresh `started_at`, empty per-feature maps).
3. `restore_checkpoint_counters(checkpoint)` runs and carries back ONLY the four enumerated fields.
4. **Observed result:** any run-scoped field the checkpoint did NOT snapshot + the restore does NOT re-apply silently resets mid-run. Before Round 35, `started_at` reset and false-tripped `cycle-bracket-break`; before the 2026-06-14 round, the counters reset and risked exceeding `max_cycles` (HARD CONSTRAINT 8 violation).

**Expected:** A non-operator-authorized resume is the SAME run continuing — its complete run-continuity state survives the pause by construction.
**Actual:** Continuity is reconstructed field-by-field; an un-enumerated field defaults to reset.
**Consistency:** Deterministic — fires on every non-operator-authorized resume for any continuity field not explicitly carried.

## Evidence Collected

### Source Code

- **`write_run_marker` (`lazy_core.py:8800-8910`)** — the single mint site. The marker dict literal (`:8861-8907`) hardcodes the reset value of every run-scoped field. `now` defaults to `time.time()`, so `started_at` is always fresh.
- **`write_run_checkpoint` (`lazy_core.py:12487-12551`)** — checkpoint write. Snapshots `counters` (passed in by the `--run-end` caller) + a RAW-read `run_started_at` (`:12532-12540`, read raw to avoid `read_run_marker`'s destructive path-A age gate). These two are the ONLY continuity values the checkpoint persists — so even a field-complete restore is bounded by what the checkpoint captured. Both the carry-set AND the checkpoint-snapshot-set are reactive.
- **`restore_checkpoint_counters` (`lazy_core.py:12584-12711`)** — the field-by-field reconstruction. Operator-authorized branch returns `None` (intentional fresh 0/0 — OUT of scope, see Affected Area). Carry-forward branch re-applies the four fields named in symptom 2, age-guarded for `started_at` (`:12702`, `_MARKER_STALE_SECONDS`) and fail-safe on a missing/unparseable value.
- **Call sites (parity):** `lazy-state.py:9475-9512` (feature) and `bug-state.py:5516-5535` (bug) BOTH `write_run_marker` → `consume_run_checkpoint` → `restore_checkpoint_counters`. The continuity logic lives ENTIRELY in the shared `lazy_core` helper, so a durable fix lands once and both pipelines inherit it.

### Runtime Evidence

- Round 35's regression record names the live observation: `detect_cycle_bracket_friction` signal (a) compares the `--cycle-begin` `run_started_at` snapshot against the live `started_at` at `--cycle-end`; the minted identity made begin `03:15:38Z` != end `05:41:28Z` and false-tripped `cycle-bracket-break` (jog-wheel-nudging Step 9). This is the concrete cost of one missing continuity field.

### Git History

- `821628e` (2026-06-23, "carry forward run identity across sanctioned checkpoint resume") — added `run_started_at` snapshot + `started_at` restore. Regression test `test_restore_checkpoint_counters_carries_forward_run_identity` (`test_lazy_core.py:9973`, 5 cases incl. a negative control proving the old minted-identity path trips).
- The 2026-06-14 / 2026-06-17 `operator-checkpoint-resume-counter-reset` round — added the counter carry-forward + the `operator_authorized` provenance branch.

### Related Documentation

- `user/scripts/CLAUDE.md` → "Checkpoint resume is provenance-branched" — documents the two resume classes (operator-authorized fresh-budget vs. automatic carry-forward). The carry-forward class is exactly the class that must be field-complete.
- HARD CONSTRAINT 8 (counters monotonic for the life of a run) is the invariant the counter reset violated; the run-identity continuity is the invariant the `started_at` reset violated. Both are instances of one super-invariant: **run-scoped continuity state survives a same-run pause**.

## Theories

### Theory 1: Two-site split (mint resets, restore re-applies) with no enumerated contract
- **Hypothesis:** The reset/carry decision is implicit and split across two functions. `write_run_marker` resets every field by writing a literal; `restore_checkpoint_counters` re-applies a hand-maintained subset. No single place enumerates which run-scoped fields are "fresh on resume" (reset) vs. "continuous across a same-run pause" (carry), so a new field silently lands on the reset side.
- **Supporting evidence:** Symptoms 1+2; two reactive patch rounds (symptom 3); the carry-set is a literal list of four `marker[...] =` lines.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

### Theory 2: Checkpoint snapshot-set is ALSO reactive (second seam)
- **Hypothesis:** Even a field-complete restore is bounded by what `write_run_checkpoint` snapshotted into `lazy-run-checkpoint.json` — currently `counters` (caller-supplied) + `run_started_at`. A field that must carry forward but is never snapshotted cannot be restored.
- **Supporting evidence:** `write_run_checkpoint:12541-12548` writes a fixed dict; `run_started_at` was added in the same Round 35 patch as the restore — i.e. the snapshot-set grew reactively in lockstep with the carry-set.
- **Contradicting evidence:** None — this is the upstream half of the same defect; a durable fix must snapshot the full continuity set at checkpoint-write time AND restore it as one unit.
- **Status:** Confirmed.

## Proven Findings

1. **Root cause:** run-resume continuity is reconstructed field-by-field across TWO reactive seams — `write_run_checkpoint`'s snapshot-set and `restore_checkpoint_counters`'s carry-set — with no enumerated allow-list partitioning run-scoped marker fields into RESET (fresh on resume) vs. CARRY (continuous across a sanctioned same-run pause). A newly-added run-scoped field defaults to RESET by construction and becomes the next whack-a-mole.
2. **Durable fix shape (the SPEC's recommended direction):** introduce an explicit, enumerated SSOT in `lazy_core` partitioning every run-scoped marker field into `RUN_CONTINUITY_FIELDS` (carried) vs. `RUN_FRESH_FIELDS` (reset on resume). `write_run_checkpoint` snapshots the full continuity set as one unit (a `continuity` block) rather than a fixed ad-hoc dict; `restore_checkpoint_counters` re-applies the entire continuity block in the carry-forward branch as one operation, preserving the existing guards (operator-authorized no-op; `started_at` age gate; `last_advance_consume_count` deliberate reset; fail-safe on missing/unparseable values). A new run-scoped marker field is then a SINGLE edit (add it to one of the two sets) and CANNOT silently default to the wrong side — a completeness assertion (the union of the two sets == the marker's run-scoped key set) can be enforced in `--test`.
3. **Lands once, both pipelines inherit:** the entire mechanism is in shared `lazy_core`; `lazy-state.py` and `bug-state.py` call it unchanged. Parity-audited but not a script-mirror.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Marker mint | `user/scripts/lazy_core.py` → `write_run_marker` (`:8800`) | Source of every reset-by-construction default; the partition's `RUN_FRESH_FIELDS` side must agree with this literal. |
| Checkpoint snapshot | `user/scripts/lazy_core.py` → `write_run_checkpoint` (`:12487`) | Reactive snapshot-set (Theory 2); must capture the full continuity set as one unit. |
| Resume restore | `user/scripts/lazy_core.py` → `restore_checkpoint_counters` (`:12584`) | Reactive carry-set (Theory 1); must re-apply the full continuity block, guards preserved. |
| Call sites (parity) | `lazy-state.py:9475-9512`, `bug-state.py:5516-5535` | Unchanged — both inherit the shared helper. |
| Regression net | `user/scripts/test_lazy_core.py` (e.g. near `:9973`) | New completeness assertion (sets partition the run-scoped key space) + a "new field defaults to continuity, not reset" guard test. |

## Out of Scope

- **The operator-authorized resume path** (`operator_authorized` truthy) — genuinely a NEW run wanting a fresh `0/0` budget and fresh identity. Left intact; `restore_checkpoint_counters` returns `None` for it (no carry). The continuity contract applies ONLY to the non-operator-authorized (automatic reliability pause / legacy) branch.
- **The cross-pipeline clobber refusal** (`refuse_run_start_clobber`, Round 19) and the same-pipeline concurrent-walker refusal — these gate WHETHER a `--run-start` proceeds, not which fields carry across a sanctioned resume.
- **`last_advance_consume_count` semantics** — it deliberately resets to 0 on resume (the registry is freshly cleared; carrying a stale watermark would suppress the first post-resume advance). It belongs to the RESET side and must stay there; this is documented behavior, not a continuity field.

## Open Questions

- None blocking. The fix is design-complete for `/plan-bug`. One implementation decision (the form of the continuity snapshot — a nested `continuity` block in the checkpoint vs. flat top-level keys) is a mechanical-internal choice with no product-behavior divergence; `/plan-bug` may pick the nested-block form (cleaner one-unit restore) without operator input.
