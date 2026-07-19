---
kind: needs-input
feature_id: adhoc-containment-hook-e2big-fails-open-windows-native
written_by: spec-bug
class: product
divergence: isolated
stub_origin: true
decisions:
  - "Disposition of this already-fixed duplicate bug — close as Won't-fix (duplicate of the archived containment-hook-inline-python-exceeds-windows-cmdline-limit), or re-open for a residual (none found)?"
date: 2026-07-19
next_skill: spec-bug
---

## Decision Context

### 1. Disposition of this already-fixed duplicate bug

**Problem.** This ad-hoc bug stub (`adhoc-containment-hook-e2big-fails-open-windows-native`,
enqueued 2026-07-18 00:27 from a Round 90 finding) describes exactly the defect that a SEPARATE
bug — `containment-hook-inline-python-exceeds-windows-cmdline-limit` — investigated, fixed, and
archived **later the same day** (`**Status:** Fixed`, commits P1 `53eb47e8` / P2 `74b8d26f` / P3
`82183884` / mark-Fixed `e1c5ed57`, all 2026-07-18 ~15:39). The stub was enqueued ~15h BEFORE that
fix landed, so it is now stale duplicate bookkeeping.

**Investigation is complete and the fix is verified live.** The containment hook already delivers
its ~32KB Python body via a `mktemp`'d temp file (`user/hooks/lazy-cycle-containment.sh:934-984`),
not `python3 -c "$_LCC_PY"`, so the command line stays short and the E2BIG silent-disarm is gone.
A plane-wide recurrence guard (`test_no_embedded_c_python_body_exceeds_cmdline_ceiling`) proves NO
hook remains on an over-limit `-c` body, and all E2BIG/temp-file/containment regression tests pass
on this Windows-native host (2026-07-19: the three targeted tests → 3 passed; the broader sweep →
63 passed). There is **no remaining code cause to fix** here.

**Why this is parked, not concluded.** The technical investigation converged cleanly, but the only
remaining action is a DISPOSITION that a cycle subagent has no authority to perform:

- Flipping `**Status:** Concluded` would route `bug-state.py` to `/plan-bug`, which would fabricate
  PHASES.md for a fix that already shipped — the exact "premature Concluded is worse than pausing"
  case the batch contract warns against.
- Closing the dir correctly means `**Status:** Won't-fix` + the archive/receipt path, both of which
  are **orchestrator-owned** (`__mark_fixed__` / Won't-fix flip) and cannot be written from a cycle
  subagent (status-honesty pipeline gate).

So the disposition is surfaced for the operator/orchestrator to own.

**Options (recommendation-first):**

- **(A — RECOMMENDED) Close as Won't-fix (duplicate).** Disposition this dir to `**Status:**
  Won't-fix` citing the archived `containment-hook-inline-python-exceeds-windows-cmdline-limit` as
  the resolving bug, then archive it via the sanctioned `bug-state.py --archive-fixed` /
  duplicate-close path. No code change — the fix already shipped. This removes stale duplicate noise
  from every open-backlog view (incident-scan dedup, reconsider/canary once-ever guards, future
  prior-art scans) without re-doing shipped work.
- **(B) Re-open for a residual.** Only if the operator believes a Windows-native E2BIG surface
  remains uncovered by the shipped fix. Investigation found none: the plane-wide ceiling test passes
  and both the containment hook and its near-limit sibling (`build-queue-enforce.sh`) were converted
  off `-c`. Choosing B would mean naming a specific uncovered surface for a fresh investigation.

**Recommendation:** Option A — close as Won't-fix (duplicate). The defect is provably already fixed
and regression-guarded; keeping this dir open is pure bookkeeping debt.

<!-- stub_origin: true — this dir carried only ADHOC_BRIEF.md before this cycle; the baseline SPEC
     is one the operator has never seen, so this decision is excluded from --park-provisional
     auto-acceptance and always parks for the operator. This dir has NO harness-auto-generated
     capsule (no INCIDENT.md/EVIDENCE.md with auto_generated: true — it was enqueued via lazy-adhoc,
     kind: adhoc-brief), so the auto_generated close-as-noise carve-out does NOT apply here. -->
