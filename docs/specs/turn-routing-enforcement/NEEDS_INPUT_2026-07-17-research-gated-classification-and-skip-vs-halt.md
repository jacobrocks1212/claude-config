---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
class: product
divergence: structural
next_skill: harden-harness
decisions:
  - "Gated-head classifier: reclassify a head whose ACTUAL resolved route is an actionable non-research route (realign-spec) as NOT research-gated — which makes it DISPATCH (realign-spec) as the queue head instead of being skipped, contradicting the operator's stated 'hydra-overlay next' expectation? (harden Round <N>, 2026-07-17)"
  - "Truly-research-gated skip-vs-halt: un-gate the research-halt surfacing (research_halt_head) from its current park-mode-only condition so a TRULY research-gated merged/queue head HALTS with needs-research on DEFAULT (non-park) runs too — no live instance exists in the current AlgoBooth queue? (harden Round <N>, 2026-07-17)"
date: 2026-07-17
---

## Decision Context

These two coupled decisions arose from the same observed-friction dispatch that produced the
Round-`<N>` mechanical fix (`docs/bugs/merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone`).
That fix closed the immediate no-route blocker (a merged-head-diverged withhold pointing at a
non-dispatchable dep-unready milestone) and — under the CURRENT classifier — the default probe now
dispatches `hydra-overlay`, matching the operator's stated expectation. What remains are two
routing-SEMANTICS forks the operator must own, because the operator's own signals CONFLICT:
they directed a classifier fix (defect 2) whose consequence contradicts their stated expectation
that `hydra-overlay` is next (defect 4).

**File-level divergence: `structural`** — the options fork a user-visible workflow (WHICH item the
pipeline dispatches next, and WHETHER a run halts vs. proceeds). A wrong provisional pick is
expensive to redirect (it changes what work the pipeline performs), so per the park-provisional
carve-out this is hard-parked: nothing is implemented for these two decisions until the operator
ratifies. The mechanical no-route fix already shipped and unblocks the run regardless.

**Verified facts (reproduced live 2026-07-17 against the AlgoBooth queue):**
- `inspector-sample-clip-view` and `inspector-track-dashboard` are in `research_gated_heads`
  (each carries `RESEARCH_PROMPT.md` + `SPEC.md`, no `RESEARCH.md`) — the coarse `_gated_head_kind`
  classifier keys on sentinel PRESENCE.
- BUT under `--strict-research-halt` BOTH resolve to `sub_skill=realign-spec`,
  `current_step='Step 4.6: upstream realign needed'`, `terminal_reason=None` — an ACTIONABLE
  non-research route, NOT `needs-research`.
- The other three "gated heads" (`cross-platform-distribution`, `inspector-effect-chain-editor`,
  `agpl-sidecar-publication`) resolve to `terminal_reason=blocked` (Step 3).
- There is therefore NO truly-research-gated head (actual route `needs-research`) anywhere in the
  current queue — so decision 2 has no live instance to validate against here.
- The existing `research_halt_head` surfacing (`lazy-state.py` ~13601) is gated on
  `_park_marker is not None` — it fires only in PARK mode, never on a default run.

### 1. Gated-head classifier: reclassify realign-routable heads out of research-gated (and let them dispatch as queue head)?

**Problem:** `_gated_head_kind` classifies `inspector-sample-clip-view` as `research`-gated purely
because `RESEARCH_PROMPT.md` is present and `RESEARCH.md` is absent. Its ACTUAL state-machine route
is `realign-spec` (an actionable, read-only drift check that writes `plans/realign-<date>.md`). The
operator (defect 2) directed: "a head with a higher-priority actionable route (realign-spec, or any
non-research route) must NOT be labeled research-gated." Implementing that directive literally means
`inspector-sample-clip-view` STOPS being a skippable gated head and DISPATCHES to `realign-spec` as
the queue head (priority 0) — ahead of `hydra-overlay`. That directly contradicts the operator's
defect-4 expectation that `hydra-overlay` is the natural next item. The two operator signals cannot
both hold; the operator must choose the intended semantics.

**Options:**
- **Adopt route-based classification — realign-routable heads dispatch as queue head (Recommended)** —
  Define "truly research-gated" = the head's actual resolved route is `terminal_reason=needs-research`
  (Step 5), per the operator's own defect-2 definition. A head resolving to `realign-spec` (or any
  actionable non-research route) is NOT research-gated, so skip-ahead does not skip it — it dispatches
  it. Consequence: `inspector-sample-clip-view` → `realign-spec` runs BEFORE `hydra-overlay`.
  Rationale: this is the state-machine-correct behavior and honors defect 2 exactly; realign-spec is a
  cheap read-only step. The operator's `hydra-overlay` expectation was formed while these heads
  appeared as research-gated dead-ends. **This option requires the operator to confirm they accept
  realign-spec dispatching ahead of `hydra-overlay`.** Cost: contradicts the literal defect-4
  expectation; needs a route-computing classifier (a scoped `compute_state` per candidate) rather than
  a sentinel-presence check — more expensive per probe.
- **Keep sentinel-presence classification; treat realign-needed-but-research-prompt-present heads as
  skippable** — Leave `_gated_head_kind` as-is (RESEARCH_PROMPT present + no RESEARCH.md → research-gated,
  skipped). `hydra-overlay` dispatches next, matching defect-4. Cost: contradicts defect 2 — a
  realign-routable head is mislabeled research-gated and silently skipped; its realign work is deferred
  until every independent item ahead is exhausted. The confusing `research_gated_heads` label persists.
- **Hybrid: reclassify for LABELLING only, keep skipping** — Correct the `research_gated_heads` label
  (route-based) for observability, but still SKIP realign-routable heads in favor of independent ready
  work. Cost: the cleanest label/behavior split, but arguably the least honest — a head correctly
  labelled "realign-needed, actionable" is still skipped, which is the opposite of "actionable routes
  take priority."

**Recommendation:** Adopt route-based classification (option A) — it honors the operator's explicit
defect-2 definition and is state-machine-correct — BUT it must be operator-ratified because it
overrides the operator's defect-4 expectation that `hydra-overlay` is next. Do not bake this in
silently.

### 2. Truly-research-gated skip-vs-halt: un-gate research-halt surfacing to fire on default (non-park) runs?

**Problem:** Operator (defect 3): "truly-research-gated features must HALT and present the research
prompt (Step 4 needs-research), NOT be silently skipped by the default skip-ahead." The
`research_halt_head` surfacing that would do this EXISTS but is gated on `_park_marker is not None`
(park-mode only). On a default (non-park) run a truly-research-gated queue head is therefore SKIPPED,
never surfacing needs-research. However, there is NO truly-research-gated head in the current queue
(all resolve to realign-spec or blocked), so this policy change has no live instance to validate here
and interacts with decision 1 (which heads even COUNT as truly-research-gated depends on decision 1's
classifier).

**Options:**
- **Un-gate research-halt surfacing to fire on default runs (Recommended)** — Remove the
  `_park_marker is not None` restriction so a truly-research-gated head (actual route
  `terminal_reason=needs-research`) that is the merged/queue head — or outranks the skip-ahead target —
  re-emits as its scoped `needs-research` terminal on default runs, surfacing its `RESEARCH_PROMPT.md`.
  Only a truly-research-gated head genuinely LOWER priority than independent ready work is skipped
  (`research_halt_head` already keys on relative merged priority, so no over-halt). Rationale: honors
  defect 3; a research gap is operator-resolvable in seconds and burying it defeats the needs-research
  halt. Depends on decision 1's route-based definition of "truly research-gated." Cost: a run can now
  halt on a research head where it previously skipped — a behavior change with no live instance to
  regression-test against in this queue.
- **Keep park-mode-only surfacing** — Leave the `_park_marker` gate. Cost: contradicts defect 3 on
  default runs — a truly-research-gated queue head is silently skipped, exactly the burial the operator
  wants eliminated.

**Recommendation:** Un-gate to fire on default runs (option A), CONTINGENT on decision 1 adopting the
route-based "truly research-gated" definition (otherwise the two definitions of "research-gated"
diverge). Ratify decisions 1 and 2 together.

## Out of scope (verified, not a decision)

- **Queue ordering (defect 4 hypothesis):** the 5 gated + `prerelease-complete-milestone` (unmet deps)
  + 2 host-deferred sitting ahead of `hydra-overlay` are all higher-priority-but-currently-undispatchable
  pre-release items; skip-ahead correctly advances past them. The ordering is not a defect — the
  no-route was (now fixed). `docs/features/queue.json` is AlgoBooth target-repo DATA, outside the
  harness's edit scope regardless.

## Resolution

resolved_by: operator (ratified out-of-band via AlgoBooth /lazy-batch session, 2026-07-18)

- **Decision 1 — Gated-head classifier:** Option A — **route-based classification**. "Truly
  research-gated" = the head's ACTUAL resolved route is `terminal_reason=needs-research` (Step 5). A
  head resolving to `realign-spec` (or any actionable non-research route) is NOT research-gated, so
  skip-ahead does not skip it — it dispatches as queue head. **Operator explicitly accepts** that
  `inspector-sample-clip-view` → `realign-spec` (and `inspector-track-dashboard`) dispatch BEFORE
  `hydra-overlay` (the earlier defect-4 "hydra-overlay next" expectation was formed while these heads
  appeared as research-gated dead-ends and is superseded by defect-2's route-based definition).
- **Decision 2 — Truly-research-gated skip-vs-halt:** Option A — **un-gate research-halt surfacing to
  fire on default (non-park) runs**. Remove the `_park_marker is not None` restriction so a
  truly-research-gated head (actual route `needs-research`) that is the merged/queue head — or
  outranks the skip-ahead target — re-emits `needs-research` and surfaces its `RESEARCH_PROMPT.md` on
  default runs. `research_halt_head` still keys on relative merged priority, so a research head
  genuinely lower-priority than independent ready work is still skipped (no over-halt). Contingent on
  and consistent with decision-1's route-based definition.

**Implementation authorized.** Ratify/implement decisions 1 and 2 together. Pick up via the
claude-config pipeline / a follow-up `/harden-harness` round.
