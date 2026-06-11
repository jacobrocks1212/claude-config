# On-Demand Investigation Step (`/investigate`) — Feature Specification

> A dispatched, on-demand root-cause investigation cycle for the lazy pipeline: full live-runtime access, a no-production-fixes contract, and a durable evidence artifact (`INVESTIGATION.md`) that downstream skills consume instead of orchestrator-authored causal narratives.

**Status:** Ready
**Priority:** P1
**Last updated:** 2026-06-11

**Depends on:** (none)

> Formally no dep-block entries (the dep schema resolves against feature SPEC.md
> directories; the related work below has none). Substantive relationships:
> - **lazy-hardening Phase 11** (`docs/specs/lazy-hardening/PHASES.md`) shipped the
>   `validation_escalation` signal (`blocker_kind: mcp-validation` + `retry_count >= 2`),
>   the `## Seam Enumeration` BLOCKED.md contract, and the corrective-phase seam-audit
>   requirement. This feature gives that seam audit an OWNER — today nothing executes it
>   except the orchestrator inline or an execute-plan cycle moonlighting as a debugger.
> - **`user/skills/systematic-debugging/`** is the in-context debugging *methodology*
>   (root-cause-before-fix discipline). `/investigate` is the pipeline *dispatch shape*
>   around that methodology: a cycle with runtime access, an artifact contract, and
>   consumers. The skill references systematic-debugging rather than restating it.

---

## Executive Summary

The 2026-06-11 d8-live-looping live run exposed a structural vacuum in the lazy pipeline: **no pipeline step owns root-cause diagnosis.** `/mcp-test` characterizes symptoms, `/execute-plan` implements fixes (and structurally cannot run live diagnostics — backgrounded diagnostics die at turn end), and `/add-phase`/`/write-plan` consume whatever causal narrative they are handed. Diagnosis therefore defaults to the orchestrator: in the measured window, **~60% of the orchestrator's non-dispatch tool calls were inline diagnostic work**, the orchestrator's context exhausted and compacted mid-live-check, and three orchestrator-authored hypotheses leaked into dispatch prompts as fact — one of which produced a wrong-variant fix (~266k tokens including recovery) that is now the lead suspect for the still-unresolved residual bug. A fix and its validating diagnostic also shipped in one commit, making the fix's causal attribution permanently unfalsifiable.

`/investigate` closes the vacuum with a **dispatched, on-demand investigation cycle**: a subagent with full live-runtime access, bound by an mcp-test-style no-fire-and-forget turn-end contract, **forbidden from fixing production code** (instrumentation-only commits allowed), whose sole deliverable is an evidence-backed `INVESTIGATION.md` — symptom statement, seam table, a hypothesis ledger in which every hypothesis is explicitly `confirmed` / `refuted` / `unproven` with a cited evidence artifact, a repro recipe, and a recommended fix scope. Downstream skills (`blocked-resolution`, `/add-phase`, `/write-plan`, fix-cycle dispatch prompts) consume the artifact instead of orchestrator narrative, making root-cause claims falsifiable, durable across compaction, and separated from the fixes they motivate.

The step is **on-demand, not a state-machine step**: the state scripts are untouched. Orchestrators dispatch it under three triggers — (1) `validation_escalation` is flagged and no current `INVESTIGATION.md` covers the symptom (this is how the Phase-11 seam audit actually gets executed); (2) a fix cycle's post-fix live check fails (fix landed, symptom unchanged); (3) the orchestrator's own inline diagnosis would exceed a small tool-call budget. Cost calibration from the live evidence: an investigation cycle (~150–250k tokens in disposable context) versus the measured alternative (~60% of orchestrator activity + one mid-task compaction + a ~266k-token wrong-variant fix cycle).

## User Experience

The "user" is the operator supervising a `/lazy-batch` run, plus the orchestrator and downstream skills as machine consumers.

**Operator-visible workflow:**

1. A feature fails validation twice → `BLOCKED.md` carries `validation_escalation`. At the blocked-resolution gate the orchestrator now reports: *"Dispatching `/investigate` to confirm root cause before drafting the corrective phase"* — instead of presenting its own inferred diagnosis as the basis for an `AskUserQuestion`.
2. The investigation cycle runs (live probes, instrumentation, real-component tests). It commits `INVESTIGATION.md` (and any `diag(...)`-prefixed instrumentation commits).
3. The operator gate that follows (blocked-resolution / add-phase approval) presents the **artifact's** findings: hypotheses with their confirmed/refuted/unproven status and evidence — so operator decisions are made on falsifiable claims, not on a confident narrative that may self-refute minutes later (the WU-12.1 incident: a "precise" diagnosis was presented to the operator, approved, and then refuted by the orchestrator before dispatch).
4. Standalone use: a human (or any session) can invoke `/investigate <spec-or-bug-dir> [symptom...]` directly to produce the same artifact outside batch runs.

**Orchestrator-visible workflow:** the orchestrator's job shrinks to trigger-detection and dispatch. A hard rule accompanies the skill: **orchestrators MUST NOT author causal narratives as fact in dispatch prompts** — dispatch prompts cite `INVESTIGATION.md` (or say "cause unknown — investigation pending"). A small inline-diagnosis budget (~8 diagnostic tool calls per issue) bounds how much probing the orchestrator may do itself before it must dispatch.

## Technical Design

### Components

| Piece | Location | What it is |
|-------|----------|------------|
| `/investigate` skill | `user/skills/investigate/SKILL.md` (NEW) | The investigation cycle contract: inputs, method, runtime access, prohibitions, artifact schema, turn-end rules |
| Dispatch template | `user/skills/_components/investigation-dispatch.md` (NEW) | The orchestrator-side dispatch prompt (ad-hoc dispatch class, like `blocked-resolution`'s apply subagent — NOT a `lazy-state` cycle emission; the state scripts are untouched) |
| Artifact schema | `user/skills/_components/sentinel-frontmatter.md` (+ AlgoBooth `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS`, lockstep) | `INVESTIGATION.md` — `kind: investigation`; permanent audit artifact (MCP_TEST_RESULTS-class, NOT a halt sentinel) |
| Trigger + consumption hooks | `blocked-resolution.md`, `halt-resolution.md`, the three batch orchestrator SKILLs, `add-phase`, `write-plan` | When to dispatch; how downstream consumes the artifact; the no-narrative-as-fact rule |
| Repo runtime hook | `<repo>/.claude/skill-config/investigation-runtime.md` (optional, per-repo) | How to boot/drive/observe the live runtime in this repo (AlgoBooth's seeded with the dev-app lifecycle + MCP tool guidance; absent file = generic guidance only) |

### `INVESTIGATION.md` artifact contract

Frontmatter (`kind: investigation`): `feature_id`, `date`, `trigger` (`validation-escalation` | `failed-fix-live-check` | `orchestrator-budget` | `manual`), `status` (`root-cause-confirmed` | `partially-localized` | `inconclusive`), `investigated_commit` (HEAD sha when the investigation ran — the freshness anchor, mirroring `validated_commit`).

Body (load-bearing sections):
- `## Symptom` — the observable failure, with the exact observation (tool call / log line), not a paraphrase.
- `## Seam Table` — the full chain user-surface → final observable, one row per seam, each `probed-OK` / `probed-FAIL` / `unprobed` with one line of evidence. Same format as the Phase-11 `## Seam Enumeration` BLOCKED.md contract; when a BLOCKED.md enumeration exists it is the starting checklist.
- `## Hypothesis Ledger` — every hypothesis considered (including inherited ones from BLOCKED.md or orchestrator notes), each marked **confirmed** / **refuted** / **unproven** with a cited evidence artifact (test name driving the REAL component, MCP tool result, session-log line). A hypothesis without an evidence citation may not be marked confirmed or refuted. "Plausible code-read" is not evidence (same rule as the Phase-11 runtime-spike discipline).
- `## Repro Recipe` — the minimal steps that reproduce the symptom (or a statement of why no deterministic repro was reached).
- `## Recommended Fix Scope` — files/seams the fix should touch, what it must NOT touch, and the post-fix verification the fix cycle owes.

Lifetime: permanent (audit). Multiple investigations append `## Investigation N (date, commit)` rounds to one file rather than proliferating files. The artifact is consumed by freshness: a consumer treats it as current when `investigated_commit` is HEAD or the only commits since are the investigation's own `diag(...)` commits; otherwise it is labeled `(stale — re-verify)` when cited.

### The cycle contract (skill rules)

1. **No production fixes.** The investigation MUST NOT modify production code paths. Allowed commits: `INVESTIGATION.md` itself, off-hot-path diagnostic instrumentation (`diag(<feature_id>): ...` commit prefix; NEVER the audio-callback hot path in AlgoBooth), and test files that drive REAL components to localize behavior (these are assets, committed normally). Instrumentation is either reverted before the cycle ends or explicitly disclosed in the artifact as retained. *Rationale: separating confirm-the-cause from apply-the-fix kills the attribution confound (fix + diagnostic in one commit ⇒ causal credit unfalsifiable) and mirrors the D5 never-self-certify principle.*
2. **No fire-and-forget** (inherited verbatim from the mcp-test contract): drive every probe to a definitive observation with blocking foreground waits; the owed `INVESTIGATION.md` is on disk before the turn ends. This is the structural fix for "backgrounded diagnostics die at turn end."
3. **Runtime ownership:** the cycle may rebuild the runtime and manage readiness gates per the repo's dev lifecycle docs (and `investigation-runtime.md` hook when present). It must verify the fix-under-test/instrumentation is actually live (binary freshness) before trusting observations — the live run lost a full verdict to a half-linked binary.
4. **Method:** `systematic-debugging` discipline (root cause before any fix proposal), four-attempt-trap rules (no code-read confirmation of runtime-coupled claims), control runs when attributing causality to a change (the reclaim-seam confound).
5. **Honest terminal states:** `inconclusive` is a legal status — with the seam table showing exactly which seams remain `unprobed` and why. An inconclusive investigation that narrows the seam set is a success, not a failure; the next round starts from its ledger.
6. **WORK-BRANCH-ONLY** commits, standard push rules (cloud immediate-push where applicable).

### Triggers and consumption (the wiring)

- **`blocked-resolution.md` / `halt-resolution.md` escalation path (extends Phase 11 WU-1b):** when `validation_escalation` is flagged AND no `INVESTIGATION.md` current for the symptom exists, the resolution flow dispatches `/investigate` FIRST; the corrective `/add-phase` then consumes the artifact (its seam table + confirmed hypotheses become the phase's Validated Assumptions ledger rows, citable as runtime evidence). The Phase-11 "corrective phase must carry a seam audit" requirement is thereby *executed by* the investigation rather than smuggled into execute-plan.
- **Failed-fix trigger (batch orchestrator SKILLs):** when a fix cycle lands and the post-fix live check shows the symptom unchanged, the next dispatch for that issue is `/investigate`, not another fix cycle. (The cycle-20 lesson: a headless-green fix built to an unverified hypothesis burned ~266k tokens and possibly introduced the current bug.)
- **Orchestrator inline-diagnosis budget (batch orchestrator probe-hygiene sections):** more than ~8 inline diagnostic tool calls on one issue → STOP and dispatch `/investigate`. Quick checks stay inline (the counter-evidence: inline self-correction was faster than a cycle round-trip for small questions — the budget keeps that property).
- **No-narrative-as-fact rule (dispatch-template + orchestrator SKILLs):** dispatch prompts reference the artifact; inherited unproven hypotheses are passed to the investigation AS hypotheses-to-test, labeled unproven, never as "solid evidence" headers.

### Explicitly out of scope (v1)

- **State-script changes.** No new `lazy-state.py`/`bug-state.py` step, no routing, no `--emit-prompt` section. On-demand dispatch is orchestrator judgment plus the three trigger rules. (A future mechanical gate — the state script refusing a corrective-phase route when `validation_escalation` is set and no fresh artifact exists — is a follow-up candidate once live runs prove the artifact's value.)
- **Post-fix re-verification mode.** Verification of a landed fix stays with the corrective phase's seam-audit rows and `/mcp-test`. `/investigate` is pre-fix root-causing.
- **Retro grading rules** for investigation cycles (note for `lazy-batch-retro` as a follow-up).

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown (2 phases: artifact/skill/schema, then trigger/consumption wiring).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Skill + components lint clean | `python user/scripts/lint-skills.py` | rc 0 | claude-config |
| Existing script gates unaffected (v1 touches no scripts) | all three regression gates | `test_lazy_core.py` green; both `--test` suites byte-identical | claude-config |
| `INVESTIGATION.md` schema recognized | AlgoBooth checker vitest + `qg:docs-consistency` | new schema tests green; a well-formed artifact produces zero warnings; malformed frontmatter flagged | AlgoBooth |
| Escalation path requires the artifact | read-through of blocked-resolution/halt-resolution escalation text | dispatch-investigate-first wording present in both; add-phase consumption wording references the ledger | claude-config |
| Dispatch template completeness | dry-read of `investigation-dispatch.md` with tokens bound | all placeholders resolvable from state-script JSON + orchestrator context; no `{unknown_token}` residue | claude-config |
| Repo hook optionality | grep | generic skill text contains no AlgoBooth-specific runtime instructions; AlgoBooth hook file exists and is referenced via the established `!cat`-with-fallback pattern | both |

## Open Questions

- Whether the state script should eventually *enforce* investigate-before-corrective-phase at `validation_escalation` (mechanical gate) — deferred until the artifact proves its value in live runs.
- Retro grading anchors for investigation cycles (`lazy-batch-retro`) — follow-up.
- Whether `plan-bug`/`fix` (out-of-band bug flow) should also consume `INVESTIGATION.md` — likely yes, cheap to add later; v1 wires the lazy-family paths that produced the evidence.

## Research References

None — research phase skipped by operator instruction ("no research"). The evidence base is the 2026-06-11 live-run transcript analysis (session `5c33b6ba`, lines 771–1263): diagnostic-load measurements, three hypothesis-leak incidents, the attribution confound, and the mid-diagnosis compaction, as reported in the analyst session and summarized in the Executive Summary.
