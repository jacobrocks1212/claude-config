---
kind: bug-investigation
bug_id: harden-hard-parks-on-unconfirmed-platform-assumptions
severity: P2
discovered: 2026-07-19
status: Concluded
written_by: harden-harness
---

# Marked-run harden agent hard-parks on unconfirmed platform assumptions instead of self-resolving via claude-code-guide + provisional accept

**Status:** Concluded (root cause proven; fix scope understood and OPERATOR-AUTHORIZED —
see Fix scope below). This is the durable investigation record cited by hardening Round 109.

**Root-cause class:** ambiguous-prose (a stale skill/template rule) + hook-defect / missing-contract
(the enforcement plane has no sanctioned path for the consultation the corrected rule requires).

## Symptom (verified)

Round 108 (`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`) HARD-PARKED the
`wedge-backstop-integrator-vs-worker-identity` decision — writing a blocking `NEEDS_INPUT.md`
and shipping NOTHING — for a fix whose ONLY unresolved blocker was an *unconfirmed platform
capability* (whether `SubagentStop` exposes a parent/depth lineage field, which decides whether
Option B is viable). The round's own reasoning names the blocker explicitly:

> "confirming it requires dispatching the `claude-code-guide` agent — which the harness-hardening
> agent is **prohibited from doing during a marked run**. Per the skill's Step-2 platform-
> confirmation rule (whose ORIGIN is Round 81's `SubagentStop`/`stop_hook_active` incident),
> load-bearing discrimination logic must NOT be shipped on an unconfirmed platform field."

So the recommended Option A (self-managed integrator-`agent_id` breadcrumb — explicitly
NON-platform-dependent) was ALSO parked, even though it does not depend on the unconfirmed field
at all. The park was driven by the inability to CONFIRM that Option B was impossible (which would
green-light A), not by any genuine risk in A itself.

## Root cause (proven) — two coupled defects

**1. Stale rule (ambiguous-prose).** The Round-81 platform-confirmation rule in
`user/skills/harden-harness/SKILL.md` (Step 2, "Confirm Claude Code platform behavior before
relying on it") plus the `## Your mandate` / "Subagent policy" prose in
`user/skills/_components/lazy-batch-prompts/dispatch-hardening.md` jointly told a marked-run
harden agent it MUST NOT dispatch `claude-code-guide` ("you MAY NOT spawn further subagents via
the Agent tool"), forcing a HARD-PARK whenever a decision's only blocker was an unconfirmed
platform/Claude-Code capability. The rule conflated two different things: (a) shipping
load-bearing logic ON an unconfirmed field (genuinely unsafe — keep prohibited), and (b) merely
CONSULTING claude-code-guide to resolve the assumption (safe, read-only, and the very thing that
would unblock a provisional accept).

**2. Enforcement-plane gap (hook-defect / missing-contract).** Even had the prose permitted the
consultation, the enforcement plane would DENY it: a marked-run harden agent dispatching
`claude-code-guide` composes an UNREGISTERED Agent prompt, which `user/scripts/lazy_guard.py`
routes to the default validate-deny — UNLESS the workstation sub-subagent exemption (branch "2b")
happens to fire, which requires the active cycle marker to declare `subagent_model: true`. A
`harden-harness` cycle does not declare `subagent-model`, and an observed-friction *background*
harden runs under whatever cycle marker is live (often none of its own), so the consultation is
not reliably admitted. There was no SANCTIONED, harden-specific dispatch path for a
`claude-code-guide` consultation. (`lazy-cycle-containment.sh` already ALLOWS a foreground
Agent dispatch from a subagent, so containment is not the blocker — only the dispatch guard is.)

## Fix scope (OPERATOR-AUTHORIZED, 2026-07-19)

Operator (Jacob) explicitly authorized a protocol change plus a sanctioned enforcement path:

1. **Skill/template prose (ambiguous-prose fix).** Retire the Round-81 BLANKET prohibition.
   Replace it with a *self-resolve-then-provisional-accept* flow: when the ONLY blocker to an
   otherwise-recommendable harden decision is an unconfirmed platform/Claude-Code capability, the
   harden agent MUST attempt to RESOLVE it by consulting `claude-code-guide` ITSELF
   (`subagent_type: claude-code-guide`), then proceed with the recommended option as a PROVISIONAL
   auto-accept per the `--park-provisional` protocol. Only a GENUINELY unresolvable/unconfirmable
   platform dependency still hard-parks. The narrower "never ship LOAD-BEARING logic on an
   *unconfirmed* field" rule is preserved — the consultation is exactly how the field stops being
   unconfirmed. Edited: `harden-harness/SKILL.md` (Step 2 + Step 3 carve-out) and
   `dispatch-hardening.md` (Subagent policy carve-out).

2. **Sanctioned enforcement path (hook-defect fix).** Add a narrow guard exemption in
   `lazy_guard.py`: ALLOW an unregistered Agent dispatch whose `subagent_type == "claude-code-guide"`
   under a BOUND, non-cloud run marker. `claude-code-guide` is a read-only agent (Glob/Grep/Read/
   WebFetch/WebSearch) that cannot commit, route the pipeline, or advance state — so admitting it is
   NOT a gate-weakening (it cannot launder a pipeline-routing prompt); it is the direct analog of
   the existing 2026-07-09 decision to allow read-only Explore fan-outs and the branch-2b
   sub-subagent exemption. Every allow is audited to the deny ledger (pre-acked, no hardening debt)
   via a dedicated `append_claude_code_guide_consult_event`.

This is NOT a gate-weakening (Prohibition #2): the validate-deny gate exists to stop a runaway
subagent from IMPROVISING pipeline-advancing dispatches / routing ops. A read-only
`claude-code-guide` consultation advances nothing; the exemption is a sanctioned narrow path, not a
softened threshold, and it is scoped by `subagent_type` + a bound-workstation-marker fence so it
cannot fire pre-bind or from a bystander session.
