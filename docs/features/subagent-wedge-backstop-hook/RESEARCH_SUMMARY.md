# Research Summary — SubagentStop Wedge-Backstop Hook

> Deep (Gemini) research was **operator-waived** for this feature (see `RESEARCH.md`,
> 2026-07-18). No external findings exist. Per the waiver, this summary integrates the
> baseline SPEC against (a) the platform confirmation obtained from `claude-code-guide`
> (recorded in SPEC.md "Platform confirmation") and (b) the `RESEARCH_PROMPT.md` question
> inventory used as a **design checklist**, plus rich in-repo prior art. The finding is that
> the authorized baseline design already resolves every research area — no baseline decision
> is revisited.

## Key findings relevant to the baseline

The feature is an internal harness change with strong in-repo precedent for every mechanism it
uses. The design does not break new platform ground; it composes already-shipped patterns:

- **Fail-open guard discipline** is the house standard, not a novel invention. Every command
  guard in `user/hooks/` (`block-terminal-kill.sh`, `lazy-cycle-containment.sh`,
  `build-queue-enforce.sh`, `block-sentinel-write-on-stray-branch.sh`) exits 0 / allows on any
  parse error and writes a `hook-error.json` + `hook-events.jsonl` breadcrumb. The baseline's
  "any error → exit 0 (allow the stop)" clause is that same contract; the SPEC should reuse the
  existing breadcrumb pattern for the fail-open observability the research prompt (Q5) asks about.
- **Per-`agent_id` breadcrumb loop-guard is sound.** `agent_id` is a documented, stable,
  per-subagent, unique-at-every-nesting-level identifier (platform confirmation). A filesystem
  breadcrumb keyed on it — present ⇒ already blocked once ⇒ allow — is the correct single-shot
  bound given `stop_hook_active` is undocumented for `SubagentStop`. The atomic-write discipline
  (`lazy_core._atomic_write` / temp+rename) already used across the harness answers the
  race/atomicity concern (Q4) directly.
- **The wedge predicate reuses existing state readers.** "run marker present" (via
  `lazy-state.py --marker-present`), "active plan not Complete", and "dirty tree OR unchecked
  work-unit checkboxes" are all state the harness already computes deterministically — the hook
  reads them, it does not re-infer them. This keeps the predicate cheap and consistent with the
  state machine's own view.

## Ideas to adopt from prior art (in-repo)

- **Breadcrumb GC via a two-path strategy** (Q6): the harness already garbage-collects ephemeral
  keyed state with a combination of session-end cleanup and staleness sweeps (e.g. the notify
  ledger drops >30d entries on write; the per-repo keyed state dir migrates/prunes stale
  markers). Adopt the same shape for `subagent-stops/<agent_id>.json` — a `SessionEnd` cleanup
  path and/or a write-time staleness sweep, GC failure non-fatal. No new GC machinery is needed.
- **Actionable injected reason** (Q7): mirror the concrete, name-the-next-action phrasing the
  existing turn-end / blocked-resolution prose uses — "Commit your work and complete the plan, or
  write BLOCKED.md with the obstacle, then stop." Give the explicit BLOCKED escape hatch so a
  genuinely-stuck agent has an honest halt, not just a re-stop.
- **State-dir path convention**: write the breadcrumb through `lazy_core.claude_state_dir()`
  (the per-repo keyed chokepoint) rather than an ad-hoc path, so it inherits the same isolation
  and hermetic-test (`LAZY_STATE_DIR`) semantics as every other run-scoped file.

## Pitfalls / concerns to address (already covered by the baseline)

- **Single-block bound is the real safety property, not instruction efficacy** (Q3/Q7). A fully
  wedged agent may ignore the injected reason entirely; the load-bearing guarantee is that the
  breadcrumb caps intervention at exactly one block, so the agent stops on its second attempt.
  The baseline already treats the single-block bound as the safety property and the instruction
  as best-effort — correct.
- **False-positive on intentional dirty-tree hand-off** (Q2). A read-only Explore sub-subagent
  that never commits, or a child that intentionally leaves the tree dirty for a parent to
  integrate, must not be force-spun. The baseline's predicate gates on run-marker presence AND
  plan-not-Complete AND pending-work, and biases to false-negative (let a done agent stop) over
  false-positive — the operator-stated bias. Implementation should confirm the predicate does not
  fire for a subagent whose lineage has no active plan.
- **Never itself wedge the pipeline** (Q4/Q5/Q8). A backstop that deadlocks is worse than the
  wedge it prevents. The absolute fail-open clause plus breadcrumb-write-then-block ordering (so
  a breadcrumb I/O failure allows the stop) addresses this. Second-order risk of masking an
  upstream bug (Q8) is mitigated because the hook only ever blocks ONCE and always leaves the
  BLOCKED escape hatch — it delays a legitimate abort by at most one cycle, never indefinitely.

## Baseline decisions revisited

**None.** Research was waived and the platform mechanism was confirmed before authoring. The
authorized design (decision #14, operator-authorized 2026-07-17) stands unchanged. The only
finalization addition is the mandatory friction-KPI declaration (below in SPEC.md) — a
measurability requirement, not a design change.
