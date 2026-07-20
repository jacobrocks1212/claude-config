---
kind: needs-input
feature_id: adhoc-incident-hook-deny-19343d-r3
written_by: spec-bug
next_skill: spec-bug
class: product
divergence: contained
stub_origin: true
decisions:
  - How to handle the THIRD working-as-designed recurrence — fix the incident-scan collector churn (and by which mechanism) vs. Won't-fix again
date: 2026-07-19
---

## Decision Context

### 1. How to handle the THIRD working-as-designed recurrence — fix the incident-scan collector churn (and by which mechanism) vs. Won't-fix again

**Problem:** The incident collector (`user/scripts/incident-scan.py`) has now auto-enqueued this
same `lazy-cycle-containment | loop-formation-flag` deny signature as a bug THREE times (r1
`19343d`, r2 `19343d-r2`, this r3). The containment deny itself is provably **correct-by-design** —
it fires only when a dispatched subagent invokes an orchestrator-only state-script routing flag,
which no sanctioned path does; relaxing it would re-open the runaway-loop hole the C2/C3 lockstep
closes. So the deny is NOT the fix site (r1 + r2 both closed **Won't-fix / working-as-designed**,
no code change). The genuine, newly-traced defect is that the collector re-enqueues a fresh `-rN`
stub on EVERY post-archive recurrence **without reading the archived incident's disposition**
(`scan_incident_keys` at `incident-scan.py:323` reads only `incident_key`, never the sibling
`SPEC.md` `**Status:** Won't-fix`; the D5-A branch at `:668` mints `-r{N+1}` unconditionally). A
correct-by-design signal therefore churns the bug queue indefinitely (r1→r2→r3→…) — each recurrence
costs a full `/spec-bug` investigation cycle, the exact "redone work" the harness mission targets.
Both r1 (Affected Area) and r2 (Proven Finding #2) already named this collector gap and deferred it
to "a future harden pass"; the third recurrence is the signal that the deferral should end. What is
undecided is a **product-class harness-behavior + safety-trade-off** call the operator must own on a
machine-generated stub they have not shaped: do we fix the churn now, and via which suppression
mechanism? (Glossary: "signature" = the `(hook, deny-reason)` cluster key the collector groups by;
"disposition" = whether an archived investigation concluded fix vs. Won't-fix.)

**Options:**
- **Fix now via an explicit opt-in "expected-signature" suppression (Recommended)** — Conclude this
  investigation and add, at the `incident-scan.py:668` recurrence branch (or the `:663` dedup), a
  read of a durable "this signature is expected / working-as-designed — do not re-enqueue"
  declaration. A Won't-fix disposition that concludes "working-as-designed" would set that marker
  (e.g. a small frontmatter field on the archived SPEC, or a committed
  `incident-scan-suppressions` list keyed by `incident_key`); the collector treats a later
  recurrence of a SO-DECLARED signature as deduped (no new stub) while any signature NOT declared
  still re-surfaces normally. Cost: a bounded change to one script plus a one-line marker
  convention; low complexity, fully reversible. Benefit: it stops the churn for THIS class WITHOUT
  blinding the collector to a genuinely-new cause that happens to reuse the same signature (a
  future real bug that trips the same hook+reason is still surfaced unless explicitly suppressed).
- **Fix now via automatic archived-Won't-fix status read** — Same fix site, but the collector
  auto-suppresses ANY recurrence whose most-recent archived incident is `**Status:** Won't-fix`, with
  no explicit opt-in. Simpler (no new marker surface). Risk: a signature Won't-fixed once for a
  *transient* reason (e.g. a one-off environment blip) that later recurs with a *real* standing cause
  would be silently masked — the collector would never re-surface it. This trades the churn for a
  blind spot; the explicit-marker option avoids that trade.
- **Won't-fix again (status quo)** — Accept that the deny is working-as-designed and that r4/r5… will
  keep being auto-enqueued (each a cheap Won't-fix cycle); leave the collector untouched, or spin the
  collector fix off as a separate lower-priority item later. Lowest immediate effort, but the churn
  (and its per-recurrence investigation cost) persists indefinitely — contrary to the harness
  efficiency mission, and this is already the third occurrence.

**Recommendation:** Fix now via an explicit opt-in "expected-signature" suppression — it ends the
provably-correct-by-design churn while preserving the collector's ability to catch a genuinely-new
cause reusing the signature, and it is a bounded, reversible change to one collector script. On
selection, this SPEC flips `Investigating → Concluded` and `/plan-bug` scopes the collector change;
the containment hook is explicitly out of scope (never relaxed).
