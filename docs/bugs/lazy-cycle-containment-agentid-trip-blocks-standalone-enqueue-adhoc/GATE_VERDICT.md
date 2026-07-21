---
kind: gate-verdict
feature_id: lazy-cycle-containment-agentid-trip-blocks-standalone-enqueue-adhoc
gate_version: 1
date: 2026-07-20
scope_hit: [user/hooks/lazy-cycle-containment.sh]
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: net-new — see complexity section
---

## Adversarial answers

### overfit

`harness-gate.py --staged --json` flagged: "literal element appended to a membership construct"
— the new `RUN_MARKER_GATED_FLAGS = frozenset({"--enqueue-adhoc"})` set.

**Nearest recurrence this rule does NOT catch:** if a future `LOOP_FORMATION_FLAGS` member
grows its own documented standalone-subagent obligation (analogous to `--enqueue-adhoc`'s
`/harden-harness` Step-3 contract), it will NOT automatically get the run-marker relaxation —
it requires a deliberate, reviewed addition to `RUN_MARKER_GATED_FLAGS`. This is INTENTIONAL,
not an oversight: the set is not auto-derived from "which flags happen to have been called by a
subagent" (that would be exactly the overfit-to-observed-data failure mode this gate exists to
catch). It is scoped by a structural eligibility test, applied by hand per flag:

  1. The flag has a **documented, sanctioned** standalone-subagent obligation (a skill's own
     contract instructs a dispatched-without-a-live-run subagent to call it directly) — not
     merely "came up once in an incident."
  2. The flag's worst-case effect, invoked with no live run, is **bounded to appending
     future-queued work under the SAME containment a later run will enforce** — it can never
     mutate the run marker/registry, bootstrap a new pipeline run, or itself advance/drive a
     cycle. `--enqueue-adhoc` satisfies this (it writes a queue entry + stub SPEC/`ADHOC_BRIEF.md`
     for a FUTURE run to pick up, subject to every existing gate); `--run-start` — the ONE
     LOOP_FORMATION_FLAGS member most tempting to lump in by the same "it also has zero live-run
     side effects yet" reasoning — deliberately FAILS this test, because relaxing it would let
     any bare dispatched subagent bootstrap a brand-new lazy run, which is categorically
     different from queuing future work.

Today `--enqueue-adhoc` is the **only** flag satisfying both prongs, so the one-member literal
genuinely is the whole class as of this change — not a fit to a single observed incident. A
future addition must re-argue both prongs explicitly in its own bug spec + GATE_VERDICT, not
silently accrete into the set.

### tautology

Not flagged (`result: pass` — no `feature_id` was supplied to the checker since this is a bug
fix with no `docs/features/` dir; the ship-seam SPEC lookup is N/A). Recorded anyway for rigor:
the target signal is `event:containment-refusal` with `signature: loop-formation-flag` and
`data.op == "--enqueue-adhoc"`, counted specifically for calls with **no live run marker** for
the repo. This is an INDEPENDENT, mechanically-derived signal (the deny-ledger append site,
`hook_lib.append_hook_event`) — not self-emitted by this fix and not something the fix itself
can silently zero out by suppressing detection (the ledger append happens on DENY, so an
undetected regression would show the count *staying nonzero*, the opposite of what "broken"
would produce if this were tautological). If the fix were broken (e.g. the run-marker read
always returned `True`), the count would stay unchanged from before the fix — a directly
falsifiable prediction, not "identical either way."

### gate_weakening

`harness-gate.py`: `result: pass` (no hit). Verified by inspection: no `def test_*` was
deleted, no numeric literal was changed on an existing gate line, no `*_BYPASS` env-var was
introduced, and no `permissionDecision: deny` / `refuse_*` / `exit 3` branch was removed — the
deny branch for every OTHER `LOOP_FORMATION_FLAGS` member is byte-identical, and the
`--enqueue-adhoc` deny branch itself still fires whenever a live run marker is present (which is
exactly the case the original design existed to catch — see the SPEC's "Fix scope" section for
the full arming-gap analysis of why the RUN marker, not the CYCLE marker, was chosen as the new
gate condition). No operator sign-off override is required.

### complexity

**`retires:` net-new.** This change adds one frozenset constant, one helper function
(`_run_marker_present`), and a conditional branch inside the existing loop-formation check — it
does not delete or subsume any prior rule. Justification for the added surface: it closes a
documented, reproduced gap where a shipped skill's own mandatory contract step
(`/harden-harness` §Step 3 over-fit spin-off) was structurally unreachable in its most common,
CLAUDE.md-prescribed invocation shape (a standalone dispatched subagent, no live lazy run). The
added surface is deliberately narrow (one flag, one new helper, fail-closed on any resolution
error) rather than a broader relaxation, keeping the blast radius to exactly the reported defect.
