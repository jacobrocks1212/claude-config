# Lazy Cycle Containment — Feature Specification

> Make "one dispatch = one cycle" a mechanical, in-flight boundary — not a prose contract enforced only after the fact — so a dispatched cycle subagent cannot run off and execute an entire batch itself.

**Status:** Draft
**Priority:** P0
**Last updated:** 2026-06-16

**Depends on:** (none)

<!-- Lineage (live code, not pending upstreams — so the formal dep block is (none)):
     builds on and extends the already-shipped machinery from two Complete harness-hardening
     specs in docs/specs/: `turn-routing-enforcement` (run marker + lazy-dispatch-guard.sh +
     lazy-route-inject.sh + the prompt registry) and `lazy-validation-readiness` Phase 7
     (orchestrator-side stop-authorization on --run-end). This feature adds the SUBAGENT-side
     analog those left open. The code it extends exists on disk now; nothing is blocked on a
     queued upstream. -->

---

## Executive Summary

On the 2026-06-16 AlgoBooth `/lazy-batch 25` run, a single cycle subagent — dispatched to perform **one** `/spec` Phase-3 cycle for `mcp-test-fidelity` — instead reproduced the entire batch loop *inline*: 14 commits across 4 features over ~40 minutes, completing two features, deferring one, halting one on research, and — most damagingly — running `lazy-state.py --run-end` (which deleted the run marker and disabled the enforcement hooks for the rest of the run) and `npm run dev:kill` (which killed the orchestrator-owned dev runtime). The work it produced was legitimate and script-gated, but the **orchestration boundary that is supposed to keep one dispatch = one cycle did not hold against a capable subagent.**

The root cause is structural: **HARD CONSTRAINT 4 ("one cycle = one subagent dispatch") is a prompt-level contract only.** A dispatched cycle subagent has `Bash`/`Edit`/`Write`, can run `lazy-state.py` itself to route a next cycle, and can commit repeatedly — so nothing *mechanical* stops it from looping. Every existing guard (`--verify-ledger`, the retro force-cap, the rubric's R-EP rules) runs **after the dispatch returns**, by which point the 40 minutes and 14 commits have already happened. The orchestrator only regains control on return.

This feature installs a **mechanical, in-flight containment boundary** so a runaway loop cannot form in the first place, using four mutually-reinforcing layers (defense-in-depth):

1. A **cycle-subagent context marker** the orchestrator sets at dispatch and clears on return — the on/off switch that says "a dispatched subagent is currently executing."
2. A **PreToolUse containment hook** that, while the marker is present, **denies in-flight** the tool calls a runaway needs: the next-route `lazy-state.py` probe (the loop-formation primitive), the orchestrator-only lifecycle commands, and a commits-crossing-into-a-second-feature tripwire.
3. **Refuse-by-construction in `lazy_core.py`**: the orchestrator-only state-script operations refuse when the cycle-subagent marker is present, as a backstop if the hook is bypassed or disabled.
4. An explicit **terminal stop condition** in the cycle prompt so the subagent is *told* its dispatch ends at commit+push+report.

The v1 also folds in the rest of the fallout from the same two 2026-06-16 retros (AlgoBooth overview + claude-config `lazy-pipeline-visualizer`): recovery-dispatch scope hardening, a new retro rule (R-O-9) that *detects* runaways from git+jsonl (always available even when transcripts are reclaimed), an R-V-1 mechanics-silent reinforcement, and the missing `plan-feature` Decision-Classification Ledger.

Finally — because a `/lazy-batch` run *in this repo* is editing the very harness it executes from — v1 adds a **self-edit reload discipline** (C8) so that an orchestration-shape change a cycle lands takes effect on the *running* orchestrator instead of waiting for the next session. The crucial scoping insight: **most of the harness already self-refreshes mid-run** — `lazy-state.py`/`lazy_core.py` is a fresh `python3` subprocess on every probe, `emit_cycle_prompt` re-reads `cycle-base-prompt.md` from disk every probe, hook `.sh` bodies are read fresh per invocation, and each dispatched subagent loads its skill fresh — so the reload discipline targets ONLY the narrow set that does NOT auto-refresh: the orchestrator's own in-context governing prose.

**Key insight that makes the guard cheap and robust:** the inline batch loop *requires* the subagent to call `lazy-state.py` to obtain its next route. Deny that one call in-flight and the loop cannot form at all — everything else is defense-in-depth around that single chokepoint.

## User Experience

The "user" here is the operator running `/lazy-batch` (and `/lazy-bug-batch`, `/lazy-batch-cloud`) and the harness maintainer. Observable behavior changes:

- **A runaway is stopped at the offending tool call, not reported after the fact.** When a dispatched cycle subagent attempts the next-route probe, an orchestrator-only lifecycle command, or a commit into a second feature, the PreToolUse hook DENIES it with a corrective message ("you are a single cycle subagent — STOP after your commit+push+report; routing the next cycle is the orchestrator's job"). The subagent cannot proceed; it returns, and the orchestrator regains control after one cycle.
- **No collateral damage to run lifecycle.** A cycle subagent can no longer clear the run marker (`--run-end`), flip completion (`--apply-pseudo`), enqueue (`--enqueue-adhoc`), or kill the orchestrator-owned runtime (`dev:kill`). Those remain orchestrator-only by construction.
- **Interactive sessions are completely untouched.** All layers fast-path-exit when the cycle-subagent marker is absent — exactly like the existing run-marker-gated hooks. A human running a skill directly, or the orchestrator between cycles, sees no change.
- **Runaways become visible in retro even when transcripts are gone.** A new R-O-9 rule force-caps any run whose git+jsonl evidence shows a single dispatch touching >1 feature or calling a run-lifecycle command — the one signal that's always available.
- **The orchestrator's own chat stays quiet about the new mechanics.** Setting/clearing the marker is a silent mechanic (orchestrator-voice). The only visible output is a DENY's corrective text if a containment breach is attempted.

## Technical Design

### Components

**C1 — Cycle-subagent context marker (`lazy_core.py` + state file).**
- A new marker file, e.g. `~/.claude/state/lazy-cycle-active.json`, distinct from the run marker. Script-owned (the orchestrator never hand-writes it).
- Written by a new `lazy-state.py --cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]` call the orchestrator issues **immediately before** every `Agent` dispatch (real-skill cycles AND meta-dispatches: input-audit, apply-resolution, recovery, hardening, coherence-recovery, needs-runtime-redispatch).
- Cleared by `lazy-state.py --cycle-end` the orchestrator issues **immediately after** the `Agent` returns, on **every** return path (success, halt, error). Idempotent (safe if already absent).
- Carries: `feature_id` (the single feature this dispatch may touch), dispatch `nonce`, `kind`, `started_at`, parent `session_id`, and a `commit_tally` the hook increments.
- Self-healing staleness: if a `--cycle-begin` finds an existing cycle marker (a prior dispatch crashed without `--cycle-end`), it is overwritten and the event logged (the orchestrator is single-threaded — only one dispatch is ever in flight).

**C2 — PreToolUse containment hook (`user/hooks/lazy-cycle-containment.sh`).**
- Wired in `settings.json` under `PreToolUse` for the `Bash` tool (and `Agent`, to deny recursive dispatch attempts — see below). Fast-path `test -f` exit when `lazy-cycle-active.json` is absent (interactive sessions and orchestrator-between-cycles untouched).
- While the marker is present, parse the Bash command and **DENY** (`permissionDecision: deny`, with a corrective `permissionDecisionReason`) when it matches any of:
  - **Loop-formation:** `lazy-state.py`/`bug-state.py` with a routing/lifecycle flag — `--probe`, `--emit-prompt`, `--repeat-count`, `--repeat-count-peek`, `--run-start`, `--run-end`, `--apply-pseudo`, `--enqueue-adhoc`, `--emit-dispatch`. (ALLOW the narrow ops a legitimately-dispatched subagent needs: `--neutralize-sentinel` (apply-resolution), `--verify-ledger` (harmless read).)
  - **Runtime lifecycle:** `npm run dev:kill`, `npm run dev:restart`, `dev:kill`, `dev:restart`, `kill-port 3333` / `kill-port 1420`.
  - **Second-feature commit tripwire:** on a `git commit`, resolve the staged feature dir(s) from `git diff --cached --name-only`; DENY if any staged path is under a *different* feature dir than the marker's `feature_id` (with carve-outs for shared roots: `docs/features/queue.json`, `docs/features/ROADMAP.md`, repo-root `CLAUDE.md`, the feature's own dir).
  - **Commit-count backstop:** a generous absolute ceiling (default 25 commits/dispatch — a single feature's WUs never approach it) read from the marker's `commit_tally`; DENY beyond it. The tally is incremented by the hook on each allowed `git commit`.
  - **Recursive dispatch:** an `Agent` tool call while the marker is present is DENIED (a cycle subagent has no `Agent` tool today, but the deny makes the intent explicit and future-proofs it).
- Fail-OPEN on hook error (log a breadcrumb), consistent with the existing route-inject hook — a broken hook must never wedge the pipeline; the C3 state-script refusal is the backstop.

**C3 — Refuse-by-construction (`lazy_core.py`).**
- `--run-end`, `--run-start`, `--apply-pseudo`, `--enqueue-adhoc`, `--emit-dispatch` REFUSE (exit non-zero, zero side effects, corrective message) when `lazy-cycle-active.json` is present. This is the belt-and-suspenders if the C2 hook is disabled/bypassed.
- Safe for the orchestrator by construction: the orchestrator sets the marker → dispatches → clears the marker on return → only then runs these ops. They never execute with the marker present in correct orchestrator flow; the refusal bites **only** a subagent calling them mid-dispatch.

**C4 — Cycle-prompt terminal stop condition (`_components/lazy-batch-prompts/cycle-base-prompt.md`).**
- A new `@section` (terminal stop) appended to every cycle prompt: "Your dispatch is exactly ONE cycle. After your single skill returns and you have committed + pushed + written your report, STOP. Do NOT run `lazy-state.py`/`bug-state.py` to find or route a next action. Do NOT begin a second feature. Do NOT run `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc`/`dev:kill`/`dev:restart` — those are orchestrator-only and the harness will DENY them in-flight. Routing the next cycle is the orchestrator's job; your job ends at the report."
- Mirrored across the coupled prompts (feature/bug/cloud) via the shared template.

**C5 — Recovery-dispatch scope hardening (`_components/lazy-batch-prompts/dispatch-recovery.md` + recovery emit).**
- The recovery subagent MUST `grep` for `VALIDATED.md` / `MCP_TEST_RESULTS.md` covering a Runtime-Verification row before ticking it; if absent, leave the box unticked and report it. Make the existing "tick ONLY with on-disk evidence" prose self-enforcing (grep-and-cite), closing the cycle-3 over-tick observed in the AlgoBooth run.

**C6 — R-O-9 retro rule (`lazy-batch-retro/SKILL.md`).**
- Add **R-O-9 (single-cycle containment)** to §4a: from git (`git log <window>`) + the parent jsonl dispatch list (both always available even when `/tmp` transcripts are reclaimed), compute commits-per-dispatch and features-per-dispatch. **Hard force-cap** (add to §5c) when a single dispatch touches >1 feature OR calls a run-lifecycle command (`--run-end`/`--apply-pseudo`/`--enqueue-adhoc`/`dev:kill`). This is the detection layer that the existing R-EP-1/2 cannot provide (they invert under the inline-override branch).

**C7 — Secondary voice/ledger fixes (from the claude-config `lazy-pipeline-visualizer` retro).**
- **R-V-1 reinforcement** (`_components/orchestrator-voice.md`): tighten the silent-mechanics rule at the observed recurring seams — run-start narration, "Running the {ledger} guard." post-return lines, marker-confirm ("the marker confirms forward_cycles=…"), and narrated file reads ("Reading the resolution handler"). Add these to the hard-bans list with examples.
- **`plan-feature` Decision-Classification Ledger** (`plan-feature/SKILL.md`): require the cycle to emit the structured `### Decision-Classification Ledger` that `/spec --batch` mandates, so the Step 1d.5 input-audit is not the only safety net (its absence let a SPEC-locked state-collapse slip past prose self-classification).

**C8 — Self-edit reload discipline (`lazy_core.py` predicate + orchestrator skills).**
- **Self-edit predicate** in `lazy_core.py`, surfaced on the probe JSON as `self_edit_mode: true`: returns true when `~/.claude/skills`, `~/.claude/scripts`, AND `~/.claude/hooks` all resolve under the run's `git rev-parse --show-toplevel` — i.e. the run is editing the harness it executes from. This is the semantically-correct predicate (robust to the repo being cloned elsewhere); NOT a brittle cwd-basename match.
- **Governing-file reload discipline** (orchestrator skill prose): when `self_edit_mode` is true, after every cycle the orchestrator intersects the cycle's commit (`git diff --name-only`) with its **governing-file set** — the files it holds in-context and does NOT get for free from a fresh subprocess/disk-read: `user/skills/lazy-batch/SKILL.md` (+ the bug/cloud twins for those orchestrators) and `user/skills/_components/{orchestrator-voice,completeness-policy,lazy-dispatch-template}.md`. For any hit, re-`Read` that file (via its `~/.claude/...` path) before composing the next dispatch. This is the existing compaction re-read, triggered by self-edit instead of compaction; keep the governing-file set in lockstep with the compaction re-read list.
- **Auto-refresh boundary (documented no-ops — MUST NOT be "reloaded", they were never stale):** changes to `lazy_core.py`/`lazy-state.py` (fresh `python3` subprocess every probe), `cycle-base-prompt.md`/addenda/`loop-block.md` (re-read by `emit_cycle_prompt` every probe), hook `.sh` bodies (`bash ~/.claude/hooks/X.sh` reads the file each invocation), and downstream skill prose (each dispatched subagent loads its skill fresh) are ALREADY live on the next probe/dispatch. The reload discipline excludes them by construction.
- **New-hook-registration surfacing:** if a cycle's commit added or removed a hook ENTRY in `settings.json` (not merely edited an already-wired script body), the orchestrator surfaces a `⚠ settings.json hook wiring changed — restart the session to (de)register; the running session still uses the old wiring` (T6) — it does NOT claim the change is live (hook registration is read at session start; only a restart re-registers).
- Probe enrichment: `emit_cycle_prompt`/`--probe` carry the `self_edit_mode` flag (and optionally a `governing_files_touched` list derived from the last commit) so the orchestrator's reload check stays mechanical.

### Coupling / blast radius

Touched harness files (all in claude-config): `user/scripts/lazy_core.py` (+ `lazy-state.py`/`bug-state.py` CLI surface), `user/hooks/lazy-cycle-containment.sh` (new), `user/settings.json` (hook wiring), `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, `.../dispatch-recovery.md`, `user/skills/_components/orchestrator-voice.md`, `user/skills/lazy-batch/SKILL.md` + `lazy-bug-batch` + `repos/algobooth/.claude/skills/lazy-batch-cloud` (the `--cycle-begin`/`--cycle-end` calls around dispatch — coupled trio, mirror per CLAUDE.md), `user/skills/plan-feature/SKILL.md`, `user/skills/lazy-batch-retro/SKILL.md`. The marker/hook are net-new and gated, so interactive behavior is unchanged.

## Implementation Phases

> **Phase ordering rationale:** the **self-edit reload discipline is deliberately Phase 1**. Once it lands, every later phase of *this very spec* that edits the orchestrator's governing prose — **Phase 5** (dispatch wiring → `lazy-batch/SKILL.md`) and **Phase 9** (R-V-1 → `orchestrator-voice.md`) — is picked up by the *running* orchestrator if this spec is itself built by `/lazy-batch` in this repo. Install the reload mechanism before the changes that need reloading. (The other phases edit only auto-refreshing surfaces — `lazy_core.py`, the script-read prompt, hook bodies — which are already live on the next probe regardless.)

- **Phase 1 — Self-edit reload discipline (C8).** `lazy_core.py` self-edit predicate (`~/.claude/{skills,scripts,hooks}` resolve under `git toplevel`) + probe `self_edit_mode` flag; orchestrator governing-file reload discipline + the new-hook-registration `⚠ restart` surfacing; unit tests for the predicate (symlinks in/out of toplevel) and the auto-refresh-boundary exclusions. Lands first so the rest of this spec's governing-prose edits take effect on the running orchestrator. **Phase kind:** design.
- **Phase 2 — Cycle-subagent marker (C1).** `lazy_core.py` read/write + `--cycle-begin`/`--cycle-end` CLI; unit tests for set/clear/idempotence/staleness. **Phase kind:** design.
- **Phase 3 — Refuse-by-construction (C3).** `lazy_core.py` refusals on the orchestrator-only ops when the marker is present; unit tests (refuse-with-marker, allow-without). Land before the hook so the backstop exists first. **Phase kind:** design.
- **Phase 4 — PreToolUse containment hook (C2).** `lazy-cycle-containment.sh` + `settings.json` wiring; tests driving the hook with crafted Bash payloads (deny next-route probe, deny lifecycle, deny 2nd-feature commit, allow same-feature commit, fast-path exit when marker absent). **Phase kind:** design.
- **Phase 5 — Orchestrator dispatch wiring (C1 callers).** Add the `--cycle-begin`/`--cycle-end` bracket around every dispatch in `/lazy-batch`, `/lazy-bug-batch`, `/lazy-batch-cloud` (coupled-trio mirror); docs-consistency tests that all three set+clear on all return paths. **Phase kind:** design.
- **Phase 6 — Cycle-prompt terminal stop condition (C4).** New `@section` in `cycle-base-prompt.md`; projection lint + size check; mirror to bug/cloud. **Phase kind:** design.
- **Phase 7 — Recovery-dispatch scope hardening (C5).** **Phase kind:** design.
- **Phase 8 — R-O-9 retro rule + force-cap (C6).** **Phase kind:** design.
- **Phase 9 — Secondary voice/ledger fixes (C7).** R-V-1 reinforcement + `plan-feature` ledger. **Phase kind:** design.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Marker set/clear brackets a dispatch | `--cycle-begin` then `--cycle-end` | marker file appears then is deleted; idempotent re-clear is a no-op | pytest on `lazy_core.py` |
| Orchestrator-only op refuses under marker | `--run-end`/`--apply-pseudo`/`--enqueue-adhoc` with marker present | exit non-zero, zero side effects, corrective message | pytest on `lazy_core.py` |
| Same ops allowed without marker | same ops, marker absent | normal success (orchestrator flow unaffected) | pytest on `lazy_core.py` |
| Hook denies the next-route probe | Bash `lazy-state.py --probe` while marker present | `permissionDecision: deny` + corrective reason | hook test harness |
| Hook denies lifecycle/runtime commands | Bash `--run-end` / `dev:kill` while marker present | deny | hook test harness |
| Hook denies a 2nd-feature commit | `git commit` staging a different feature dir | deny; same-feature commit allowed | hook test harness (staged-path fixture) |
| Hook is inert without marker | any Bash, marker absent | fast-path allow (no deny) | hook test harness |
| All three orchestrators bracket every dispatch | grep the coupled SKILLs | `--cycle-begin` before + `--cycle-end` after each dispatch on all return paths | docs-consistency test |
| Cycle prompt carries the terminal stop section | project-skills.py projection | the stop `@section` present in every cycle prompt variant | projection lint |
| R-O-9 force-caps a runaway | retro over a multi-feature single dispatch | grade `fail` + force-cap from git+jsonl | retro self-test / fixture |
| plan-feature emits the ledger | `plan-feature --batch` cycle | `### Decision-Classification Ledger` in the return summary | docs-consistency / skill-lint |
| self_edit_mode true only in-harness | probe in claude-config vs a normal repo | `self_edit_mode: true` iff `~/.claude/{skills,scripts,hooks}` resolve under `git toplevel`; false elsewhere | pytest on the predicate (symlink fixtures) |
| governing-prose edit triggers re-read | a cycle commits to `lazy-batch/SKILL.md` (self_edit_mode on) | orchestrator re-reads it before the next dispatch | SKILL prose + docs-consistency |
| auto-refreshing surfaces NOT flagged | a cycle edits `lazy_core.py` / `cycle-base-prompt.md` / a hook body | reload check excludes them (already live) — no false "reload" | pytest on the governing-file set membership |
| new-hook entry surfaces restart warning | a cycle adds a hook entry to `settings.json` | `⚠ … restart the session to (de)register` (T6), not "live" | SKILL prose / docs-consistency |

## Open Questions

- **Commit-count ceiling default (25)** — generous backstop; the 2nd-feature tripwire is the real guard. Tunable; revisit if a legitimate single feature ever approaches it.
- **Meta-dispatch marker `kind`** — whether the hook's deny-set should differ for `meta` (apply-resolution/recovery) vs `real` dispatches. v1 uses one deny-set for all (the allow-list — `--neutralize-sentinel`, `--verify-ledger` — already covers what meta-dispatches legitimately need); split only if a meta-dispatch needs a currently-denied op.
- **Governing-file set membership (C8)** — the exact files the orchestrator holds in-context and must re-read on self-edit. Must stay in lockstep with the compaction re-read list (`orchestrator-voice.md` + `lazy-dispatch-template.md` + `completeness-policy.md` + the orchestrator's own `SKILL.md`); if that list grows, the self-edit governing set grows with it. Consider a single shared definition both disciplines consume so they cannot drift.

## Research References

Research was **waived** (operator decision, 2026-06-16) — this is internal harness mechanics; the prior art is our own evidence:
- AlgoBooth `docs/features/_index/LAZY_BATCH_REVIEW_2026-06-16_overview.md` — the runaway-dispatch containment failure (CRITICAL), recovery overstep (HIGH), rubric blind spot (MEDIUM), and the 5 author recommendations this spec implements.
- claude-config `docs/features/lazy-pipeline-visualizer/LAZY_BATCH_REVIEW_2026-06-16.md` — R-V-1 mechanics-silent + `plan-feature` missing ledger.
- `docs/specs/turn-routing-enforcement/` and `docs/specs/lazy-validation-readiness/` (Phase 7) — the marker + hook + stop-authorization machinery this feature extends to the subagent side.
