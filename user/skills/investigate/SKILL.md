---
name: investigate
description: USE WHEN a root cause must be CONFIRMED before fixing — validation failed twice, a landed fix didn't change the symptom, or inline diagnosis is ballooning. Produces INVESTIGATION.md; NEVER fixes production code.
argument-hint: <spec-or-bug-dir> [symptom...]
---

# /investigate — On-Demand Root-Cause Investigation Cycle

## Overview

A dispatched investigation cycle with full live-runtime access whose ONLY deliverable is an evidence-backed `INVESTIGATION.md`. It exists because no other pipeline step owns diagnosis: `/mcp-test` characterizes symptoms, `/execute-plan` implements (and cannot run live diagnostics — backgrounded probes die at turn end), and planning skills consume whatever causal narrative they are handed. Without this step, diagnosis defaults to the orchestrator — measured at ~60% of orchestrator activity in the 2026-06-11 d8-live-looping run, with three orchestrator hypotheses leaking into dispatch prompts as fact and one wrong-variant fix costing ~266k tokens.

**Announce at start:** "I'm using the /investigate skill to confirm root cause for {feature_id} — no production fixes this cycle."

The separation is the point: **confirm-the-cause and apply-the-fix never share a cycle.** A fix cycle that also authors the diagnostic that validates it makes its own causal attribution unfalsifiable (the d8 reclaim-seam confound); an investigation that also fixes self-certifies. This mirrors the D5 mcp-test principle.

## Arguments

- `<spec-or-bug-dir>` (required): the feature/bug directory (`docs/features/.../<id>/` or `docs/bugs/<id>/`).
- `[symptom...]` (optional): one-line symptom statement; when absent, derive it from BLOCKED.md / MCP_TEST_RESULTS.md.
- `--batch` is accepted and is a NO-OP: this skill is already non-interactive by design. It never calls `AskUserQuestion` — honest terminal states (`inconclusive` with the unprobed seams named) replace questions.

## Inputs to read (in order)

1. `<dir>/BLOCKED.md` — symptom, `blocker_kind`, `retry_count`, and the `## Seam Enumeration` section (written by mcp-test into EVERY `blocker_kind: mcp-validation` BLOCKED.md, starting at the FIRST failure — not only at escalation): that section is your **starting checklist**, not something to re-derive.
2. `<dir>/MCP_TEST_RESULTS.md`, the feature's `PHASES.md` Validated Assumptions ledgers, and any prior `INVESTIGATION.md` rounds (start from the previous round's ledger — never re-litigate a `refuted` hypothesis without new evidence).
3. Hypotheses passed in the dispatch prompt. **Inherited hypotheses arrive labeled `unproven` and are treated as hypotheses-to-test, never as evidence** — regardless of how confident the orchestrator's framing sounds. (Live incident: a "strong hypothesis" header produced a wrong-variant fix now suspected as the residual bug.)

## Method

Apply the `systematic-debugging` skill's discipline: root cause before any fix proposal; the Iron Law (`NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST`) is structurally enforced here by the no-production-fix contract below. Additional rules layered on top:

- **Four-attempt-trap rule:** a runtime-coupled claim (data shape at a boundary, whether a path fires, live process output, rendered/observable result, cross-thread timing) is NEVER confirmed or refuted by reading source. Observe the running system, or drive the REAL component with a test (the actual ring/transport/process — not a mock).
- **Control runs for causal attribution:** before crediting a change (yours or a prior fix) with an observed difference, run the without-the-change control where feasible. A diagnostic and the change it validates must not be conflated.
- **Seam-first localization:** walk the chain user surface → sidecar/serialization → IPC/queue → engine apply → state machine → final observable. Probe to bisect: find the deepest seam where the signal is still correct and the shallowest where it is wrong.

## The cycle contract (HARD RULES)

1. **No production fixes.** You MUST NOT modify production code paths. Allowed commits, exhaustively: (a) `INVESTIGATION.md` itself; (b) off-hot-path diagnostic instrumentation under commit prefix `diag(<feature_id>): ...` — reverted before the cycle ends, or explicitly disclosed as retained in the artifact (NEVER instrument an audio-callback hot path or equivalent RT-critical code; see the repo runtime hook); (c) tests that drive REAL components to localize behavior — these are assets, committed normally with the `diag(...)` prefix. If you discover the fix is a one-line obviosity, you still do not apply it — record it under `## Recommended Fix Scope` with the evidence; the fix cycle owns it.
2. **No fire-and-forget.** Drive every probe to a definitive observation WITH blocking foreground waits (readiness gates, rebuild completion, log flush). Never end the turn on a pending background job — backgrounded diagnostics die at turn end. The owed `INVESTIGATION.md` is on disk before you return, whatever the status.
3. **Runtime ownership + binary freshness.** You may rebuild the runtime and manage readiness per the repo's dev lifecycle docs (and the repo hook below). Before trusting ANY observation about code behavior, verify the code under observation is actually live in the running binary (a live run lost a full verdict to a half-linked build). State the verification in the evidence.
4. **Hypothesis-ledger discipline.** Every hypothesis you considered — including inherited ones — appears in the ledger marked **confirmed**, **refuted**, or **unproven**, each with a cited evidence artifact (test name driving the real component, MCP tool call + result, session-log line). A hypothesis without an evidence citation may not carry a confirmed/refuted verdict. A plausible code-read is not evidence for runtime-coupled claims.
5. **Honest terminal states.** `inconclusive` is a legal, useful outcome: the seam table must then show exactly which seams remain `unprobed` and why (missing device, time box, undriveable path). An inconclusive round that narrows the seam set is a success — the next round starts from your ledger instead of from zero.
6. **WORK-BRANCH-ONLY:** commit and push to the current branch only (`git rev-parse --abbrev-ref HEAD` at start); never create a branch, never force-push. Standard repo commit policy applies; cloud-dispatched runs push immediately after each commit.

## Authoring `INVESTIGATION.md`

Schema (frontmatter is machine-validated — keep in lockstep with `~/.claude/skills/_components/sentinel-frontmatter.md`, which is the canonical source):

```markdown
---
kind: investigation
feature_id: <id>
date: <YYYY-MM-DD>
trigger: <validation-escalation | failed-fix-live-check | orchestrator-budget | manual>
status: <root-cause-confirmed | partially-localized | inconclusive>
investigated_commit: <git rev-parse HEAD when the investigation ran>
---

# Investigation — <feature_id>

## Symptom
<the observable failure, with the EXACT observation (tool call + result / log line) — not a paraphrase>

## Seam Table
| seam (producer → consumer) | status | evidence |
|---|---|---|
| <e.g. sidecar lowering → capnp wire> | probed-OK \| probed-FAIL \| unprobed | <one line: the probe + what it showed> |

## Hypothesis Ledger
| hypothesis | origin | verdict | evidence |
|---|---|---|---|
| <claim> | inherited (orchestrator/BLOCKED.md) \| this round | confirmed \| refuted \| unproven | <cited artifact — test name, MCP call + value, log line> |

## Repro Recipe
<minimal deterministic steps to reproduce the symptom — or an explicit statement of why no deterministic repro was reached>

## Recommended Fix Scope
<files/seams the fix should touch; what it must NOT touch; the post-fix verification the fix cycle owes (which seam-table rows to re-probe)>
```

Rules:
- **One artifact per feature/bug dir.** Repeat investigations APPEND `## Investigation N (date, commit)` rounds to the same file (frontmatter is updated to the newest round's values).
- **Freshness semantics:** consumers treat the artifact as current when `investigated_commit` equals HEAD or the only commits since are this investigation's own `diag(<feature_id>):` commits. Anything else is cited as `(stale — re-verify)`. Stamp the sha at write time, after your last commit.
- Commit the artifact (message: `docs(<feature_id>): INVESTIGATION.md — <status>`), push per repo policy.

## Repo runtime hook (how to drive THIS repo's live system)

!`cat .claude/skill-config/investigation-runtime.md 2>/dev/null || echo "(no repo runtime hook — generic guidance: locate the repo's dev lifecycle docs (CLAUDE.md / docs/development/) for how to boot, observe, and instrument the running system; prefer the repo's existing observability surfaces over ad-hoc instrumentation)"`

## Return format (to the dispatching orchestrator)

A short structured summary — the artifact carries the detail:
- `status:` + one-line root-cause statement (or the narrowed seam set if not confirmed)
- Seam table delta vs the inherited Seam Enumeration (which rows you flipped)
- Hypothesis verdicts (one line each: verdict + evidence pointer)
- Instrumentation disposition (reverted / retained-and-disclosed)
- Files committed + artifact path

The orchestrator passes the ARTIFACT (not your summary prose) to downstream skills.
