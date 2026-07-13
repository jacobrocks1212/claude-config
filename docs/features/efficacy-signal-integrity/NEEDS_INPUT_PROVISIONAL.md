---
kind: needs-input
feature_id: efficacy-signal-integrity
written_by: spec
decisions:
  - "D2: Canary staleness alarm channel"
  - "D4: Scorecard regeneration point"
date: 2026-07-12
class: product
divergence: isolated
audit_divergence: isolated
next_skill: spec-phases
---

# NEEDS_INPUT — Provisionally Accepted (park-provisional protocol)

This feature's SPEC named two decisions as `product-behavior (needs operator ratification at
finalization)` (D2 and D4) rather than `mechanical-internal`. Both carry a single, strongly-
justified recommended option in the SPEC itself and are low-divergence (rendering/orchestrator-
prose surface only; no architecture or persistent-data fork). Per the overnight park-provisional
protocol, this session adopted both recommendations and implemented the feature fully —
this file records that choice for ratify-or-redirect review rather than halting the run. The
feature is NOT flipped to Complete pending this ratification (see the report for exact status).

## Decision Context

### 1. D2: Canary staleness alarm channel

**Problem:** 19+ canaries are open with zero closes/trips ever observed (the split-brain bug's
symptom); the 30-day wall-clock ceiling will eventually mature ALL of them into `closed-clean
(no-data)` — a mass laundering of unwatched harness changes into "observed, clean" unless the
operator hears about it BEFORE the ceiling fires.

**Options (from SPEC D2):**
- **A — committed-channel scorecard section + run-end flush notify line (Recommended)** — a
  `## Canary health` section in `docs/kpi/SCORECARD.md` (open count / oldest age / projected
  no-data-close count) mirrors a one-line `⚠ N canaries open, oldest Xd, M will no-data-close
  within Yd` in the `efficacy-eval.py --canary` flush output (JSON `staleness`/`staleness_notify`
  keys + plain-text line). No new notification machinery; never blocks a run; a `closed-clean
  (no-data)` close stays a distinct, separately-counted signal from a genuine clean close
  everywhere the operator reads.
- **B — a new sentinel-style halt** — would page the operator via the existing halt-notification
  channel, but canary staleness is informational/continuous, not a per-item blocking condition;
  turning it into a halt would create a false urgency and interrupt otherwise-clean runs.
- **C — do nothing until the ceiling fires** — the status quo this feature exists to fix.

**Recommendation:** A — reuses two existing committed/JSON channels (the scorecard, the
`--canary` JSON payload) rather than inventing new machinery; purely additive, fail-open.

### 2. D4: Scorecard regeneration point

**Problem:** `docs/kpi/SCORECARD.md`'s per-cycle regen is registry-gated to the repo the RUN
happens in ("only when `<repo_root>/docs/kpi/registry.json` exists" — `lazy-batch/SKILL.md`),
i.e. it never fires where runs actually happen (AlgoBooth today has no registry), and nothing
regenerates it on the claude-config commit path where the registry actually lives.

**Options (from SPEC D4):**
- **A — regenerate on the claude-config commit path (Recommended)** — the run-end flush already
  commits `docs/interventions/` updates to claude-config (SKILL §1c.6, the split-brain fix's
  cross-repo commit step); the scorecard regen joins that SAME commit step, so it is
  registry-gated TRUE exactly where the registry lives, regardless of which repo the run
  happened in. The AlgoBooth-side per-cycle regen prose stays as-is (correctly a no-op until
  AlgoBooth grows a registry — byte-identical, no regression).
- **B — regenerate per-repo unconditionally, every cycle** — would need a registry write path in
  every repo, duplicating the registry or requiring cross-repo reads mid-cycle; heavier and
  contradicts the "one registry, in claude-config" design.
- **C — leave the gap; regenerate only on manual `/lazy-batch-retro` or on-demand invocation** —
  leaves the scorecard stale between operator-triggered runs, the exact symptom SPEC section 3
  documents (`b3698b1` predating the registry's own last update).

**Recommendation:** A — rides an EXISTING commit step, is registry-gated correctly by
construction, and requires zero new cross-repo machinery.

**Cross-lane note:** implementing D4's chosen option is a `user/skills/lazy-batch/SKILL.md`
(+ `lazy-batch-cloud`) §1c.6 orchestrator-prose edit — the SKILLS lane, not this feature's file
ownership under the current concurrent-agent split. This session could not land it directly;
the exact wanted prose edit is named in the feature's completion report for the SKILLS-lane
owner to apply.

## Resolution

resolved_by: auto-provisional
decision_commit: a547c716d1dfae64cf5f344cb7cabfce13f4bac5

**Choice (D2):** A — implemented as `efficacy-eval.py`'s `run_canary` staleness computation
(`CANARY_STALENESS_LOOKAHEAD_DAYS = 7`, `staleness`/`staleness_notify` JSON keys + plain-text
flush line) and `kpi-scorecard.py`'s `## Canary health` section (`_canary_health_summary`).
Both shipped and tested this session.

**Choice (D4):** A — the code side (`kpi-scorecard.py`'s render/write path) is unconditionally
ready to regenerate wherever invoked against a repo carrying `docs/kpi/registry.json`; the
orchestrator-prose wiring to invoke it on the claude-config commit path (rather than only the
per-repo-run-happens-in gate) is a SKILLS-lane follow-up — reported, not implemented here.

Both choices are rendering/orchestrator-prose-surface-only (isolated divergence on both keys) —
a redirect at ratification means editing a section-render function and a flush-output line (D2)
or an orchestrator SKILL.md paragraph (D4), with no downstream architectural coupling. Ratify-or-
redirect before this feature completes.
