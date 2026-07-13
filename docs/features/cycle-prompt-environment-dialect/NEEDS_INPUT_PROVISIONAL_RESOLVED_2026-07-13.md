---
kind: needs-input
feature_id: cycle-prompt-environment-dialect
written_by: spec
decisions:
  - "D1: Delivery surface for the environment-dialect binding — prompt section only (v1) vs. also a PreToolUse Bash hook lint"
date: 2026-07-12
class: product
divergence: isolated
audit_divergence: isolated
next_skill: spec-phases
---

# NEEDS_INPUT — Provisionally Accepted (park-provisional protocol)

This feature's SPEC names D1 as `product-behavior (open — recommendation below)` rather than
`mechanical-internal`: whether the environment-dialect binding lives in the emitted cycle
prompt only, or is backed by a PreToolUse Bash hook that denies/warns on the known-fatal shapes
(trailing `\"` before a closing quote, `ls /mnt/c`, an `open('/tmp/…')` in a `python -c` on
win32). The SPEC carries a single, strongly-justified recommended option. Per the overnight
park-provisional protocol, this session adopted the recommendation and proceeded — this file
records that choice for ratify-or-redirect review rather than halting the run.

## Decision Context

### D1: Delivery surface — prompt section vs. hook vs. both

**Problem:** Six error clusters (267 + ~119 + ~36 + ~25 + 94 + 114 mined incidents) come from
cycle subagents never receiving environment lessons that live in MEMORY.md / mid-session
operator corrections (subagents are spawned fresh with the emitted prompt as ~their entire
standing context). Where should the binding live?

**Options:**
- **A — prompt section only (Recommended, v1)** — a new `@section env-dialect` block in
  `cycle-base-prompt.md`, selected host-conditionally. Reaches every cycle subagent by
  construction, zero runtime machinery, testable as emitter fixtures. Advisory only — a model
  can still type the error; measured value is prevention-RATE, not a guarantee.
- **B — PreToolUse Bash hook lint** — deny/warn on the known-fatal shapes directly. Stronger
  (mechanically prevents the mistake rather than teaching around it), but each pattern needs
  careful false-positive engineering (a legitimate `/mnt/c` reference inside a string literal,
  a deliberate trailing-backslash Windows path in a comment, etc.), and a deny converts a typo
  into a retry loop rather than a silent correct-first-try.
- **C — both** — ship A now, layer B in later for whichever clusters the KPI shows the prompt
  failing to kill.

**Recommendation:** A for v1, with B as the evidence-driven escalation path (the SPEC's D1
open question: "which residual cluster rate justifies a PreToolUse lint" is explicitly
deferred to post-Phase-4 KPI evidence, not speculated now). This matches the house sequence
elsewhere in this harness: teach in the prompt first, mechanize only what recurs after
measurement (the same escalation shape as `phases-slice-scoped-reads`, which this feature's
own Phase 3 finishes wiring into the cycle prompt).

## Resolution

resolved_by: auto-provisional
decision_commit: a547c716d1dfae64cf5f344cb7cabfce13f4bac5

**Choice (D1):** A — prompt section only for v1. Implemented as the `env-dialect-core` +
`env-dialect-windows` sections in
`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (this feature's Phase 2).
No new hook was authored.

This is `isolated` divergence on both keys — a later redirect to option C is strictly additive
(author one new PreToolUse hook script + a `settings.json` registration + its own test file);
nothing in the prompt-section implementation would need to be un-done or reworked. Ratify (stay
at A pending KPI evidence) or redirect (commission the hook now) before this feature's Phase 4
measurement-hookup phase closes it out.


## Ratification

ratified_by: operator (Jacob)
ratified_date: 2026-07-13
mode: blanket ratification (operator directive, /lazy-batch run 2026-07-13 — "ratify all remaining provisional accepted decisions, and complete all the features")

All provisionally-accepted decisions recorded in the Resolution / provisional-acceptance section(s)
above are **RATIFIED AS-IS** to their provisionally-accepted (recommended) option — no redirect. The
operator issued a blanket ratification of every outstanding `--park-provisional` decision in this run.
The on-disk implementations stand unchanged; completion is unblocked. This provisional sentinel is
neutralized (renamed to `NEEDS_INPUT_PROVISIONAL_RESOLVED_2026-07-13.md`).
