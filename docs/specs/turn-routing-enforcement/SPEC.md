# Hook-Enforced Turn Routing (+ Harness-Hardening Stage) — Feature Specification

> Mechanical, hook-enforced routing for orchestrator runs: every turn's route is injected from a state-script probe, every `Agent` dispatch is validated against the script-emitted prompt registry and denied otherwise, and every misroute (or no-route) dispatches a new harness-hardening stage — an Opus subagent specialized in improving claude-config itself.

**Status:** Ready
**Priority:** P0
**Last updated:** 2026-06-11

**Depends on:** (none)

> Formally no dep-block entries (this repo's specs have no queue.json). Substantive relationships:
> - **lazy-hardening Phases 8–11** (`docs/specs/lazy-hardening/PHASES.md`) made cycle prompts script-emitted (`--emit-prompt`), counters script-persisted (streaks), and completion script-gated (`--apply-pseudo`). This feature is the enforcement layer those phases lacked: the contracts exist, but nothing *mechanical* stops the orchestrator from ignoring them.
> - **investigation-step** (`docs/specs/investigation-step/SPEC.md`) is the structural template: the hardening stage is to the HARNESS what `/investigate` is to the target repo — a dispatched owner of root-cause work that the orchestrator was doing badly inline.
> - **/lazy-batch-retro session 5c33b6ba findings** (AlgoBooth `docs/features/_index/LAZY_BATCH_REVIEW_2026-06-11_overview.md`) are the evidence base throughout.

---

## Mission alignment

Per the repo Mission (CLAUDE.md): this repo is the harness for an autonomous agentic development system whose end goal is the most efficient, effective, and best-practice-aligned software builder we can construct. This feature converts the harness's strongest empirical finding into mechanism: **determinism is bimodal on exactly one boundary — script-emitted prompt + same-turn probe vs hand-composed dispatch** (zero failures in 12 emitted cycles; every measured failure in hand-composed ones). Prose contracts decay under compaction and time pressure; hooks do not. Where prose said "MUST consume the emitted prompt," this feature makes the alternative *impossible to execute silently* — and turns every attempt into a self-improvement signal.

## Executive Summary

Three mechanisms, all gated on a **run marker** so ordinary interactive sessions are untouched:

1. **Inject (UserPromptSubmit + supplementary events):** while an orchestrator run is active, a hook runs the state-script probe and injects the route — probe JSON, `cycle_prompt`, `cycle_model`, `cycle_header`, and a one-time **nonce** — into the model's context via `hookSpecificOutput.additionalContext`. The orchestrator no longer has to *remember* to probe; the probe arrives with the turn.
2. **Validate-deny (PreToolUse on `Agent`):** every `Agent` dispatch during a marked run is checked against the script's **prompt registry** (hash + nonce recorded at emit time). A dispatch whose prompt was not script-emitted this turn is **denied** (`permissionDecision: deny`) with a reason that instructs the canonical recovery (re-probe; or route the gap to the hardening stage). Hand-composed dispatch prompts — the source of every measured protocol failure — become unexecutable.
3. **Harness-hardening stage:** any misroute (denied dispatch), no-route (probe cannot produce a route: `cycle_prompt_refused`, unknown state, marker/state divergence), or hook-detected contract gap dispatches an **Opus subagent → `/harden-harness` skill invocation**. The stage is specialized in hardening claude-config: it analyzes the route the orchestrator took, root-causes the gap (missing contract? ambiguous prose? missing emit section? script defect?), fixes mechanical issues autonomously under full gates, and surfaces genuine harness-design forks to the operator via the existing NEEDS_INPUT triage system. It is the lazy system's self-improvement loop, made a first-class pipeline citizen.

## Locked Decisions (operator-answered 2026-06-11)

| # | Decision | Choice | Notes |
|---|----------|--------|-------|
| 1 | Enforcement strength | **Full: inject + validate-deny** | Not advisory-inject-only; the PreToolUse deny is load-bearing |
| 2 | Scope | **Orchestrator runs only** | Marker-gated; interactive sessions never see these hooks fire |
| 3 | Hardening-stage authority | **Tiered by decision class** | Mechanical fixes autonomous with full gates; contracts/policy via NEEDS_INPUT triage |
| 4 | Hardening-stage cadence | **Inline, unbounded** | Operator explicitly overrode the once-per-signature recommendation: every misroute dispatches the stage inline, no dedup cap. Requires the self-recursion guard (below) |

## Technical Design

### Components

| Piece | Location | What it is |
|-------|----------|------------|
| Run marker | `~/.claude/state/lazy-run-marker.json` (NEW; state dir is untracked ephemeral) | Written by orchestrator SKILLs at Step 0, deleted on EVERY run-end path. Fields: `pipeline` (feature\|bug), `cloud` (bool), `repo_root`, `session_id`, `started_at`, `max_cycles`, `nonce_seed` |
| Prompt registry | same state dir, `lazy-prompt-registry.json` (NEW) | Written by the state scripts at every `--emit-prompt` / `--emit-dispatch`: `{nonce, sha256(prompt), emitted_at, class, item_id}` ring of recent emissions |
| Inject hook | `user/hooks/lazy-route-inject.(sh\|py)` (NEW) | UserPromptSubmit (+ PostCompact): marker present → run the full probe form, inject probe JSON + route + nonce via `additionalContext`; marker absent → exit 0 instantly |
| Validate hook | `user/hooks/lazy-dispatch-guard.(sh\|py)` (NEW) | PreToolUse matcher `Agent`: marker present → hash `tool_input.prompt`, look up registry; miss → deny with corrective reason; marker absent → allow instantly |
| `--emit-dispatch <class>` | `user/scripts/lazy_core.py` + both state scripts (EXTEND) | Closes the ad-hoc gap: apply-resolution, input-audit (1d.5), investigation-dispatch, recovery, coherence-recovery, and hardening dispatches become script-emitted + registered, same as cycle prompts |
| Script-persisted counters | `lazy_core.py` (EXTEND) | `forward_cycles`/`meta_cycles` move from orchestrator session memory into script-persisted run state (joining the persisted streaks), updated at probe/apply time — the inject hook can then run the FULL probe form with no session memory, and the post-compaction counter-loss class dies mechanically |
| `/harden-harness` skill | `user/skills/harden-harness/SKILL.md` (NEW) | The hardening stage contract (below) |
| Hardening dispatch template | `user/skills/_components/hardening-dispatch.md` (NEW) | Orchestrator-side dispatch prompt; emitted via `--emit-dispatch hardening` so it passes its own guard |
| Hook registration | live `~/.claude/settings.json` per machine | See "Settings placement" — the live settings file is per-machine and not currently claude-config-managed on this laptop |

### The run marker (scope = orchestrator runs only)

- **Written** by `/lazy-batch`, `/lazy-bug-batch`, `/lazy-batch-cloud` at Step 0 (after preflight passes), **deleted** on every terminal path — including error exits; each terminal's existing PushNotification point doubles as the deletion checklist (the 1c.6 policy enumerates them).
- **Stale-marker guard:** hooks ignore + delete a marker whose `started_at` is older than 24h or whose `session_id` does not match the current session — a crashed run must not haunt the next interactive session. A stale-marker cleanup is logged to the hook's stderr (visible in `claude --debug`), never injected.
- **Both hooks exit instantly when the marker is absent.** This is the entire interactive-session cost: one `test -f`.

### Inject (UserPromptSubmit + supplementary events)

When the marker is present, the inject hook:

1. Runs the **full probe form** (`--repeat-count --emit-prompt --probe` with counters read from script-persisted run state; `--cloud` per marker). The probe registers the emitted prompt (nonce + hash) in the registry as a side effect.
2. Injects via `hookSpecificOutput.additionalContext`: the probe JSON (route fields), `cycle_header`, `cycle_prompt` + `cycle_model` (or pseudo-skill/terminal routing), and the nonce — prefixed with a fixed banner (`LAZY-ROUTE (hook-injected, turn N): …`) so retro graders can distinguish injected routes from orchestrator-claimed ones.
3. **PostCompact registration (supplementary):** the same hook on `PostCompact` injects the post-compaction re-entry protocol (the Step 1d HARD rule) plus the script-persisted counters — the compaction cliff's "counters never recovered" failure mode is repaired by construction, because the counters never lived only in session memory.
4. **Known limitation (recorded, not hidden):** UserPromptSubmit fires on operator-submitted prompts; autonomous cycle returns arrive as task notifications, which UserPromptSubmit does not cover. The probe-presence guard + validate-deny still police those turns (a dispatch without a same-turn registered emission is denied regardless of how the turn began). If a future Claude Code hook event fires per-turn on task notifications, register the inject hook there too — design for it, do not block on it.

### Validate-deny (PreToolUse on `Agent`)

When the marker is present, for every `Agent` call:

1. Hash `tool_input.prompt` (sha256, after newline normalization — CRLF/LF must not defeat the match).
2. **Allow** iff the hash exists in the registry with `emitted_at` within the current turn window and the nonce unconsumed; consume the nonce (one dispatch per emission — a re-dispatch requires a re-probe, which is exactly the continuation-cycles-must-re-emit rule, now mechanical).
3. **Deny** otherwise: `permissionDecision: deny`, `permissionDecisionReason` = the corrective recipe (*"dispatch prompt not script-emitted this turn — re-run the Step 1a probe (`--emit-prompt`) and dispatch its `cycle_prompt` verbatim; if the probe refuses or no route exists, dispatch the hardening stage via `--emit-dispatch hardening`"*). The denial reason is itself the injected guidance for the next attempt.
4. The hardening dispatch class is registry-validated like everything else (`--emit-dispatch hardening`), so the guard never blocks its own escape hatch.

**Every legitimate dispatch class becomes script-emitted.** Real-skill cycles already are (`--emit-prompt`). The remaining hand-composed classes (apply-resolution Step 1g/1h, input-audit Step 1d.5, `/investigate` dispatch, recovery/coherence-recovery, NEEDS_RUNTIME re-dispatch) move to `--emit-dispatch <class>`, which binds the corresponding component template with the same token/section machinery (`cycle-base-prompt.md` grammar) and registers the result. This is the D7-complete option: no allowlist of "trusted hand prompts" — zero unregistered dispatches.

### The harness-hardening stage (`/harden-harness`)

**Identity:** to the HARNESS what `/investigate` is to the target repo — the dispatched owner of "why did the route break, and how do we make the harness better," replacing inline orchestrator improvisation.

**Triggers (inline, unbounded — locked decision 4):**
1. A validate-deny fired (misroute) — dispatched with the denied prompt, the denial reason, and the registry state.
2. No-route: the probe returned `cycle_prompt_refused`, an unknown/contradictory state, or marker/state divergence.
3. The inject hook itself errored against a live marker (hook bug = harness bug).
4. Manual: `/harden-harness <description>` from any session, for friction observed outside enforcement.

**The stage's job, per dispatch:**
1. **Reconstruct the route taken** — from the injected evidence (denied prompt, probe JSON, registry) plus the run's recent transcript artifacts; name the divergence point precisely.
2. **Root-cause against the harness, not the run** — classify the gap: missing emit section / unbound token; ambiguous or contradictory SKILL prose; script defect; missing contract for a legitimately novel situation; hook defect. "The orchestrator misbehaved" is never a terminal diagnosis — the question is always *what harness change makes that misbehavior impossible or self-announcing*.
3. **Act by decision class (tiered authority — locked decision 3):**
   - **Mechanical** (template/token gaps, missing section, prose clarification, lint fixes, test additions, doc lockstep repairs): implement autonomously. Full gates mandatory: `lint-skills.py` (+ `--check-projected --check-capabilities`), `test_lazy_core.py` (full suite, no baseline regeneration), `lazy-state.py --test`, `bug-state.py --test`, coupled-pair mirroring (the CLAUDE.md pairs table), sentinel-schema lockstep (sentinel-frontmatter.md ↔ AlgoBooth `SENTINEL_SCHEMAS`) when schemas are touched.
   - **Contract / policy / design forks** (new pipeline steps, authority changes, gate semantics, anything an operator would want to own): write `NEEDS_INPUT.md` into `docs/specs/turn-routing-enforcement/` (or the relevant spec dir) per the canonical sentinel schema + rich-body convention — the existing triage system surfaces it. Never bake a harness-design fork in silently.
4. **Deliverable:** a `HARDENING.md` round appended in `docs/specs/turn-routing-enforcement/hardening-log/` (one file per month, rounds appended — the harness's own hypothesis-ledger discipline: divergence, root cause with cited evidence, change made or NEEDS_INPUT raised, gates run with counts). Commits use `harden(<area>): …`.
5. **Prohibitions:** never edits the target repo's source; never weakens a gate to make a denial pass; never edits the registry/marker to retroactively legitimize a denied dispatch (that is the integrity side-door this whole feature exists to close).

**Self-recursion guard (required by inline-unbounded cadence):** the hardening dispatch is itself registry-emitted, so it passes the guard; a denial *of a hardening dispatch* must NOT dispatch another hardening stage — depth is hard-capped at 1 (the hook tags hardening-class registry entries; a deny at depth 1 halts with a T6 `⚠` + PushNotification instead of recursing). Unbounded refers to per-run dispatch count (no dedup-by-signature), not recursion depth.

### Settings placement (honest constraint, surfaced)

The live `~/.claude/settings.json` on this laptop is **not** the claude-config-tracked `user/settings.json` (that file currently carries the desktop machine's hook paths). Hook *scripts* live in claude-config (`user/hooks/`, symlinked); hook *registration* must be added to each machine's live settings.json. Phase planning must include: a `setup.ps1`-verifiable registration check (warn when the marker-gated hooks are absent from the live settings), and a documented per-machine registration snippet. Unifying settings management across machines is out of scope here (it is a candidate NEEDS_INPUT for the hardening stage's first month).

## Failure modes & containment

| Failure | Containment |
|---------|-------------|
| Hook errors during a marked run | Inject-hook error → trigger 3 (hardening dispatch); validate-hook error → Claude Code treats a non-zero PreToolUse ambiguously, so the validate hook must fail-OPEN (exit 0 allow) and write a `HOOK_ERROR` breadcrumb the next inject turn surfaces — a broken guard must not brick the run silently, but its breakage must be self-announcing |
| Marker leaks past run end | 24h staleness + session-id mismatch cleanup; run-end deletion is on every terminal path |
| Registry/marker hand-edited to launder a dispatch | The hardening stage's prohibition + retro grading (registry writes are script-owned; any other writer is an integrity finding) |
| Hook latency per probe | The probe is one python invocation (~1–2s observed); UserPromptSubmit timeout set ≥ 30s; acceptable against a multi-minute cycle |
| WSL/Windows divergence | Hook commands must run on both (bash entry points; python3 resolution per the BASH_ENV note in AlgoBooth CLAUDE.md); Phase planning includes a per-platform pipe-test |

## Out of scope

- Touching the target-repo pipeline semantics (state machine routing itself is unchanged — this enforces consumption of what the scripts already emit).
- Enforcement for interactive (non-marked) sessions.
- Cross-machine settings.json unification (surfaced as a follow-up decision, not solved here).
- Retro-grader automation changes beyond consuming the new injected-route banner and registry (graders get strictly better evidence for free).

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown (6 phases; hooks are built in Phase 2 but deliberately not armed until Phase 6). Planning-time runtime probes recorded there as a Validated Assumptions ledger; two findings of note: `additionalContext` is not documented for `PostCompact`, so compaction re-injection targets `SessionStart` matcher `compact` with PostCompact supplementary; and whether PreToolUse fires for nested subagents' `Agent` calls (and what discriminates depth) is doc-ambiguous — resolved by a mandatory Phase 2 spike with a NEEDS_INPUT halt if no discriminator exists.

## Success criteria

1. In the next graded batch run: **zero** hand-composed real-skill dispatches reach execution (denied count may be >0 — denials are the system working), zero probe-less probe-shaped headings, counters survive compaction.
2. Every denial/no-route produces either a merged mechanical hardening commit (gates green) or a triaged NEEDS_INPUT — none vanish.
3. Interactive sessions show no behavioral change and no measurable latency (marker-absent fast path).
4. `/lazy-batch-retro` R-O-1/R-O-4 grading becomes mechanical: heading ↔ `cycle_header` byte-match, dispatch ↔ registry lookup.
