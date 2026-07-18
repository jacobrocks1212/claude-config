# Input-audit obligation fires (mis-targeted) after a zero-commit failed spec cycle — Investigation Spec

> A `/spec`-kind cycle that fails with zero commits still arms the §1d.5 input-audit obligation; the pre-composed emit command then binds `cycle_commit_sha=HEAD~1`, which points at the PREVIOUS (unrelated) item's commit — dispatching a pointless ~77k-token audit against the wrong diff.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/adhoc-audit-obligation-fires-on-zero-commit-failed-cycle
**Related:** `docs/features/mechanize-prose-only-orchestrator-contracts/` (the D2-A audit-obligation withhold this defect lives in); `user/skills/lazy-batch/SKILL.md` §1d.5

---

## Verified Symptoms

<!-- Source of truth is the operator-authored ADHOC_BRIEF.md capturing the 2026-07-18 live run;
     this is a --batch investigation, so the brief's observed incident stands as the report. -->

1. **[VERIFIED]** During the 2026-07-18 run a `/spec`-kind cycle dispatch failed abnormally (0 tool uses, returned boilerplate, **no commit landed**), yet the closed spec-kind cycle bracket still armed the §1d.5 input-audit obligation, and the next probe withheld the forward route and surfaced an `input_audit_emit_command`. — observed in the live run (ADHOC_BRIEF.md).
2. **[VERIFIED]** The pre-composed `input_audit_emit_command` bound `cycle_commit_sha=HEAD~1`, which pointed at an **UNRELATED bug item's commit** (the previous cycle's HEAD), plus a `cycle_summary` derived from that unrelated commit's subject. — observed in the live run (ADHOC_BRIEF.md).
3. **[VERIFIED]** The dispatched audit correctly no-opped (its diff against the wrong commit showed no SPEC/PHASES delta for the target item) but cost **~77k tokens** — pure waste, no pipeline loop. — observed in the live run (ADHOC_BRIEF.md).

## Reproduction Steps

1. Under a live `/lazy-batch` (feature) or `/lazy-bug-batch` (bug) run, dispatch a `/spec` / `plan-feature` (feature) or `/spec-bug` (bug) cycle that returns a **hard failure with zero commits** (e.g. an Agent dispatch that no-ops — 0 tool uses — and lands nothing).
2. The orchestrator calls `--cycle-end`. The cycle marker's `sub_skill` is an `AUDITED_CYCLE_KIND`, so `record_audit_obligation` arms `audit_obligation` on the run marker **unconditionally** (no commit-delta check).
3. The next `--emit-prompt` probe sees `pending_audit_obligation()` non-None → sets `route_overridden_by="audit-obligation"` and composes `input_audit_emit_command` via `build_input_audit_emit_command`, which hardcodes `cycle_commit_sha="HEAD~1"`.
4. The orchestrator dispatches the input-audit subagent VERBATIM; it diffs `HEAD~1` (the previous, unrelated commit) and no-ops.

**Expected:** A zero-commit (failed / no-op) cycle close arms **no** audit obligation — there is no authored SPEC/PHASES delta to audit — so no audit dispatch fires. Should an audit ever be dispatched, its `cycle_commit_sha` binds the **actual end commit of that cycle's bracket**, never a positional `HEAD~1`.
**Actual:** The obligation is armed regardless of commit delta, and the emit command binds a positional `HEAD~1` that resolves to the previous (often unrelated) item's commit, dispatching a wasted ~77k-token audit.
**Consistency:** Deterministic — every zero-commit close of an `AUDITED_CYCLE_KIND` cycle reproduces it.

## Evidence Collected

### Source Code

**Fix site A — obligation armed with no commit-delta gate.**
- `user/scripts/lazy-state.py:12784-12788` — the `--cycle-end` handler calls `lazy_core.record_audit_obligation(item_id=_tl_cycle["feature_id"], cycle_kind=_tl_cycle["sub_skill"])` for any live cycle marker.
- `user/scripts/lazy_core/markers.py:3384-3413` — `record_audit_obligation` arms `marker["audit_obligation"]` whenever `cycle_kind in AUDITED_CYCLE_KINDS` (`{spec, plan-feature, spec-bug, spec-phases}`). Its **only** gate is the cycle KIND; it never inspects whether the bracket produced a commit.
- Note: `record_cycle_commit_bracket` (`lazy_core/ledgers.py:391-434`) runs six lines later (`lazy-state.py:12794`) and already computes the exact zero-commit signal (`begin_sha == end_sha` → returns None, line 423). The needed signal — the cycle marker's `begin_head_sha` vs current HEAD — is available at the arming point.

**Fix site B — emit command binds positional `HEAD~1`.**
- `user/scripts/lazy-state.py:14129-14155` — the withhold branch (`pending_audit_obligation() is not None`) composes `state["input_audit_emit_command"] = build_input_audit_emit_command(...)` without passing a real sha.
- `user/scripts/lazy_core/ledgers.py:3721-3770` — `build_input_audit_emit_command` hardcodes `_ctx("cycle_commit_sha", "HEAD~1")` (line 3766) and derives `cycle_summary` from `git log -1 --format=%s` at cwd (lines 3748-3757) — i.e. the most recent commit, which after a zero-commit failed cycle is the PREVIOUS (unrelated) item's commit.

### Runtime Evidence

The 2026-07-18 live run captured in `ADHOC_BRIEF.md`: the failed spec cycle armed the obligation, the emit command bound `HEAD~1` (an unrelated bug item's commit), and the audit dispatched and no-opped at a ~77k-token cost.

### Git History

No prior fix for this class. The obligation mechanism was introduced by `mechanize-prose-only-orchestrator-contracts` (b) / D2-A, which promoted the §1d.5 dispatch from prose to a mechanical withhold; the commit-delta gate was never part of that arming logic.

### Related Documentation

- `user/skills/lazy-batch/SKILL.md` §1d.5 — the prose contract already lists a skip condition: *"The cycle subagent returned a hard failure with no SPEC/PHASES delta (nothing to audit)."* This defect is that skip condition never being mechanized on the arming side (it lived only as orchestrator prose, exactly the prose-not-enforced failure the D2-A withhold exists to close).
- `user/scripts/CLAUDE.md` — coupled-pair discipline: the same machinery is mirrored on `bug-state.py` (see Affected Area).

## Theories

### Theory 1: Unconditional arming on cycle KIND
- **Hypothesis:** `record_audit_obligation` gates only on `cycle_kind in AUDITED_CYCLE_KINDS`, never on whether the bracket committed anything, so a zero-commit failed cycle arms an obligation for a diff that does not exist.
- **Supporting evidence:** `markers.py:3408-3413` — the sole guard is the kind check; `record_cycle_commit_bracket` proves the zero-commit signal is computable at the same handler point but is not consulted by the arming call.
- **Contradicting evidence:** None.
- **Status:** Confirmed (traced).

### Theory 2: Positional `HEAD~1` binding in the emit command
- **Hypothesis:** Even when an audit legitimately fires, `build_input_audit_emit_command` binds `cycle_commit_sha="HEAD~1"` positionally rather than the bracket's actual end commit, so any intervening/absent commit mis-targets the audit diff.
- **Supporting evidence:** `ledgers.py:3766` hardcodes `"HEAD~1"`; `cycle_summary` (3748-3757) is the latest commit subject regardless of which item authored it.
- **Contradicting evidence:** None — the `HEAD~1` default is documented as a "SKILL.md-sanctioned fallback," but it is a positional proxy, not the cycle's own end sha.
- **Status:** Confirmed (traced).

## Proven Findings

**Root cause (cause label: `traced`).** The mis-targeted, wasted audit is produced by two code defects, both directly on the symptom's serving path:

Serving path — obligation armed with no commit delta:
```
orchestrator dispatches input-audit subagent (~77k tokens)        lazy-batch/SKILL.md §1d.5
  ← state["input_audit_emit_command"] present (route_overridden_by="audit-obligation")
                                                                    lazy-state.py:14129-14155
  ← pending_audit_obligation() non-None because --cycle-end armed it
                                                                    lazy-state.py:12784-12788
  ← record_audit_obligation arms on cycle_kind alone, no commit-delta gate  ← FIX SITE A
                                                                    lazy_core/markers.py:3384-3413
```

Serving path — emit command binds positional HEAD~1:
```
audit subagent diffs cycle_commit_sha=HEAD~1 → previous, unrelated item's commit
  ← input_audit_emit_command carries cycle_commit_sha="HEAD~1" (hardcoded)   ← FIX SITE B
                                                                    lazy_core/ledgers.py:3721-3770 (line 3766)
```

Both fix sites are read on the symptom's serving path (fix-site-on-path satisfied). The cause is deterministic and code-traceable — not runtime-coupled; the 2026-07-18 incident is the observed confirmation.

**Fix shape (for `/plan-bug` — not locked here):** (1) gate `record_audit_obligation` (or its `--cycle-end` call site) on a non-empty commit delta for the closing bracket — `begin_head_sha != end_sha` (reuse the exact signal `record_cycle_commit_bracket` already computes), or the stricter "≥1 commit touching the item's spec dir"; a zero-commit close arms/clears no obligation. (2) Bind `build_input_audit_emit_command`'s `cycle_commit_sha` (and `cycle_summary`) to the bracket's **actual end commit**, never positional `HEAD~1`. Both changes are **coupled-pair** edits — mirror on `bug-state.py` + `lazy_core` (shared).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Obligation arming (feature) | `user/scripts/lazy-state.py:12784-12788`; `user/scripts/lazy_core/markers.py:3384-3413` (`record_audit_obligation`) | Arms an audit obligation with no commit-delta gate. |
| Obligation arming (bug — coupled pair) | `user/scripts/bug-state.py:8641` (same `record_audit_obligation` call) | Same defect on the bug pipeline; parity-audited. |
| Emit-command composition (feature) | `user/scripts/lazy-state.py:14148-14155`; `user/scripts/lazy_core/ledgers.py:3721-3770` (`build_input_audit_emit_command`) | Hardcodes `cycle_commit_sha="HEAD~1"` + latest-commit `cycle_summary`. |
| Emit-command composition (bug — coupled pair) | `user/scripts/bug-state.py:9767` | Same positional-`HEAD~1` bind on the bug pipeline. |
| Existing reusable signal | `user/scripts/lazy_core/ledgers.py:391-434` (`record_cycle_commit_bracket`) | Already computes `begin_sha`/`end_sha` and skips `begin == end` — the zero-commit oracle the fix should reuse. |

## Open Questions

- None blocking. The only design latitude (`clear` vs `skip` the obligation on a zero-commit close; `begin!=end` vs "touches spec dir" as the delta test) is fix-shaping detail for `/plan-bug`, not an unresolved root-cause question — every option converges on the same end-state (no mis-fired audit).
