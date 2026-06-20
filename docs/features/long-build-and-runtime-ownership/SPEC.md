# Long-Build + Runtime Ownership — Feature Specification

> Long-running builds and the dev/MCP runtime are owned at a level that survives the subagent turn boundary, so `/mcp-test` never meets a reaped runtime and no production edit is orphaned by a build dying mid-cycle.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-20

**Depends on:**

- unified-pipeline-orchestrator — composes — this feature extends that feature's `lazy-state.py --ensure-runtime` subcommand and the orchestrator-loop / cycle-subagent (Step 1d.0) model it owns.

---

## Executive Summary

A long-running build (`tauri build`) or the dev/MCP runtime (`tauri dev` + the MCP HTTP server on TCP 3333) is a **process**. A process started from inside a cycle subagent's turn lives in that subagent's process tree, and Claude Code reaps that tree when the subagent's turn ends. The result is three recurring failure modes observed in the AlgoBooth `/lazy-batch` corpus (2026-06-19 session audit):

1. **Reaped runtime** — `/mcp-test` runs in a later cycle and finds a dead runtime, because the runtime was booted inside an earlier subagent's subprocess (session `18e1d3d7`: `--ensure-runtime` booted + asserted tools *within its own Bash subprocess*, whose process tree was torn down on return — `health_code: 0` was the tell).
2. **Orphaned production edits** — a `tauri build` backgrounded inside a cycle subagent dies with that subagent's turn, leaving real production edits uncommitted and the cycle orphaned (session `5c33b6ba`).
3. **Hand-rolled poll loops** — the orchestrator compensates by hand-building repeated rebuild → health-poll → inspect-telemetry until-loops, each the same shape (~6+ times in one session), boilerplate that should be a single deterministic primitive.

The harness already has the *two halves* of the answer in partial form: the long-build half is a **prose rule** (`repos/algobooth/.claude/skill-config/long-build-ownership.md` — "orchestrator owns long builds, run them `run_in_background` from the main session, never from inside a cycle subagent"), and the runtime half is a **deterministic subcommand** (`lazy-state.py --ensure-runtime` → `lazy_core.ensure_runtime`, the probe → stale-check → `dev:restart` bg → curl-until-200 → assert-MCP-tool dance collapsed into one call). The friction is that (a) the prose rule is **advisory** — a subagent can and does violate it, with no enforcement; (b) `--ensure-runtime`'s background process is **only survival-correct when invoked from the orchestrator session** — invoked from inside a subagent's subprocess it is reaped exactly like any other; and (c) there is **no harness-tracked liveness/recovery primitive** that lets the orchestrator stop hand-rolling poll loops and lets `/mcp-test` cheaply assert "the runtime I need is up, current, and mine."

This feature mechanizes process ownership so a build/runtime started during a feature cycle is provably owned by a session that outlives the cycle subagent's turn — turning the advisory prose rule into an enforced, deterministic harness primitive, covering both the long-build path and the persistent-runtime path, and giving the orchestrator a single liveness/recovery call instead of hand-rolled loops.

## User Experience

The "user" of this harness-internals feature is the orchestrator (and, by extension, Jacob reading a `/lazy-batch` run's behavior). There is no end-user-facing AlgoBooth product surface. The observable behaviors:

- **A cycle subagent never owns a turn-crossing process.** When a cycle needs a long build or the dev/MCP runtime, the *orchestrator* owns the process (started in the main session), and the subagent interacts with it through a harness-tracked handle — never by backgrounding it inside its own turn. An attempt by a subagent to background a turn-crossing build/runtime is prevented or redirected, not silently reaped.
- **`/mcp-test` cheaply asserts a live, current, owned runtime.** The mcp-test cycle calls one primitive that returns a structured verdict (`ready | booted | stale-rebuilt`, `mcp_tools_present`, `health_code`) and never meets a reaped runtime. If the runtime cannot be brought up MCP-ready, the orchestrator surfaces a `BLOCKED.md` (`blocker_kind: mcp-runtime-unready`) rather than dispatching a subagent against a dead runtime.
- **The orchestrator stops hand-rolling poll loops.** The rebuild → health-poll → inspect-telemetry shape is a single deterministic subcommand the orchestrator calls; it does not hand-compose the loop per cycle.
- **A torn-mid-build cycle does not orphan production edits.** When a cycle is torn down while a build it depends on is in flight, the harness either prevents the build from being subagent-owned in the first place (so it survives), or detects the orphan and recovers/surfaces it (no silent uncommitted production delta). The exact recovery contract is an Open Question for research.

## Technical Design

> This is the baseline design surface. The load-bearing *mechanism* choices below are flagged as Open Questions — they are research-answerable (industry conventions for daemonizing/supervising build processes across ephemeral-agent boundaries, prior art in CI/agent harnesses) and are deliberately NOT pre-baked here; Phase 2 harvests them into the Gemini research prompt.

### Current state (what exists today)

- **Long-build prose rule** — `repos/algobooth/.claude/skill-config/long-build-ownership.md`: orchestrator owns long builds, runs them `Bash run_in_background: true` from the main session, `cargo check --release` before a packaged `tauri build`. Advisory; no enforcement.
- **`--ensure-runtime` subcommand** — `lazy_core.ensure_runtime(repo_root, *, config, probe, restart, stale_check)` (`user/scripts/lazy_core.py` ~L6166), surfaced as `lazy-state.py --ensure-runtime`. Probe `/health` → `stale_check` (native source newer than boot stamp) → `restart()` (background `dev:restart`, bounded curl-until-200) → assert MCP tool present. Returns `{status, mcp_tools_present, health_code}`. AlgoBooth specifics parameterized in `_ENSURE_RUNTIME_DEFAULT_CONFIG`; injectable callables keep `--test` hermetic. Called from `/lazy-batch` Step 1d.0 (orchestrator session).
- **Cycle-subagent containment** — `lazy-cycle-containment.sh` + `lazy-state.py --cycle-begin/--cycle-end` already deny a subagent a defined set of orchestrator-only ops (recursive dispatch, `dev:kill`/`dev:restart`, etc.). This is the existing enforcement seam the long-build/runtime ownership rule can extend.

### Proposed surface (baseline — mechanism TBD pending research)

1. **Ownership boundary made enforceable, not advisory.** The "orchestrator owns turn-crossing processes" rule becomes a deterministic, enforced contract rather than prose a subagent may ignore. The existing `lazy-cycle-containment` deny-set already blocks `dev:kill`/`dev:restart` from a subagent; the long-build path (`tauri build` / `cargo build --release` backgrounded from inside a subagent) is the gap to close the same way. *(Mechanism — extend the containment hook deny-set vs. a new ownership primitive — is an Open Question.)*

2. **Runtime ownership survives the subagent boundary by construction.** `--ensure-runtime` already produces an orchestrator-owned background process *when called from the orchestrator session*. The defect (session `18e1d3d7`) is when its survival guarantee is silently lost because it was invoked from inside a subagent's subprocess. The baseline requires that the ownership level be explicit and verifiable — the caller/owner of the runtime process is recorded (a harness-tracked handle/sentinel) so a later cycle can assert "this runtime is owned by the live orchestrator session," not merely "something answers `/health`." *(Mechanism — orchestrator-process ownership + a tracked handle, a detached/daemonized supervisor, or an OS-service-level runtime — is the central Open Question.)*

3. **A single liveness/recovery primitive replaces hand-rolled loops.** The rebuild → health-poll → inspect-telemetry shape becomes one deterministic call (an extension of `--ensure-runtime` or a sibling subcommand) that the orchestrator invokes instead of hand-composing the until-loop. It returns a structured verdict and, on un-recoverable failure, the `mcp-runtime-unready` blocker signal. Shared impl in `lazy_core` (repo-agnostic, parameterized config), hermetic under `--test` via injected callables — same shape as the existing `ensure_runtime`.

4. **Torn-build orphan handling.** When a cycle is torn down mid-build, the harness must guarantee no silent uncommitted production delta. The baseline asserts the *outcome* (no orphaned production edits); the *contract* (prevent-by-ownership so the build survives the tear, vs. detect-and-recover the orphan after the tear, vs. both) is an Open Question for research, informed by the existing `--cycle-end` process-friction detector (`detect_cycle_bracket_friction` / `unexpected-commits` / `cycle-bracket-break`) which already records torn-bracket friction to the deny-ledger.

5. **Unified vs. separate ownership for builds and the runtime.** A long packaged build and the persistent dev/MCP runtime are both turn-crossing processes, but they differ (a build terminates and produces an artifact; the runtime is long-lived and health-polled). Whether one ownership mechanism covers both or they are owned separately is an Open Question — the baseline keeps the *contract* (both survive the boundary) uniform while leaving the *mechanism* open.

### Determinism / harness principles (non-negotiable, not open)

- Ownership/liveness state is **script-owned and read from on-disk signals** (a handle/sentinel + the existing run marker), never LLM-inferred — consistent with the harness's deterministic-state-script-owns-state principle.
- Any new subcommand lives in `lazy_core` (shared, repo-agnostic) with AlgoBooth specifics in a parameterized config dict, and is hermetic under `--test` via injected `probe`/`restart`/`stale_check`-style callables — mirroring `ensure_runtime`.
- Enforcement is **fail-OPEN** where it gates a subagent op (consistent with the existing `lazy-cycle-containment` hooks), and the existing `--cycle-begin/--cycle-end` bracket + deny-ledger is the friction-recording seam, not a new parallel mechanism.

## Implementation Phases

*(Indicative phasing — finalized by `/spec-phases` after research locks the ownership mechanism.)*

- **Phase 1 — Enforce the long-build ownership boundary.** Close the gap the prose rule leaves: a subagent backgrounding a turn-crossing build is prevented/redirected (extend the `lazy-cycle-containment` deny-set or equivalent). Tests in the containment harness.
- **Phase 2 — Explicit, verifiable runtime ownership.** Record the runtime's owner (handle/sentinel keyed to the live orchestrator session); make `--ensure-runtime` (or a sibling) assert owned-by-live-orchestrator, not merely health=200. Hermetic `lazy_core` tests.
- **Phase 3 — Single liveness/recovery primitive.** Collapse the hand-rolled rebuild→poll→inspect loop into one deterministic subcommand; wire `/lazy-batch` Step 1d.0 (and the cloud/no-cloud variants per their coupling rules) to call it.
- **Phase 4 — Torn-build orphan handling.** Per the research-locked contract (prevent vs. detect-and-recover), guarantee no silent uncommitted production delta on a mid-build tear; integrate with the existing `--cycle-end` friction detector.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Subagent cannot own a turn-crossing build | Cycle subagent backgrounds `tauri build` / `cargo build --release` | Op is denied/redirected; no reaped-mid-build orphan | `lazy-cycle-containment` test fixtures; deny-ledger |
| Runtime survives the subagent boundary | Boot runtime in one cycle, run `/mcp-test` in a later cycle | `/mcp-test` finds a live, current runtime (`status ∈ ready\|stale-rebuilt`, `mcp_tools_present: true`) | `lazy-state.py --ensure-runtime` JSON; live mcp-test cycle |
| Ownership is verifiable, not just health=200 | Query runtime ownership when booted from orchestrator vs. (simulated) subagent subprocess | Verdict distinguishes orchestrator-owned (survives) from subagent-owned (does not) | `lazy_core` hermetic `--test` |
| Orchestrator stops hand-rolling poll loops | mcp-test cycle in `/lazy-batch` | One subcommand call returns the structured verdict; no hand-composed until-loop in the cycle prompt | `/lazy-batch` Step 1d.0 prose; cycle transcript |
| Un-recoverable runtime surfaces a blocker | `--ensure-runtime` cannot reach MCP-ready | `BLOCKED.md` (`blocker_kind: mcp-runtime-unready`) written; no subagent dispatched against a dead runtime | `lazy-state.py` probe; BLOCKED.md sentinel |
| No orphaned production edits on a mid-build tear | Cycle torn down while its build is in flight | No silent uncommitted production delta; friction recorded or build survived | `git status`; `--cycle-end` process-friction ledger entry |

## Open Questions

> These are **research-answerable** design forks (prior art / industry conventions / technical tradeoffs), deferred to the Gemini research prompt (Phase 2) — NOT product-behavior decisions for the operator. They do not gate a baseline draft.

1. **Ownership mechanism (central fork).** What level owns a turn-crossing process so it provably outlives a subagent turn — (a) the orchestrator process + a harness-tracked handle/sentinel (extends what exists today), (b) a detached/daemonized supervisor process the orchestrator spawns and tracks, or (c) an OS-service-level runtime? Tradeoffs: complexity, cross-platform behavior (Windows Developer Mode is on; the harness runs on Windows + WSL), recoverability, and how cleanly each integrates with the existing `--ensure-runtime` + cycle-marker machinery.
2. **`--ensure-runtime` rework vs. replace.** Should `--ensure-runtime` be reworked to record/assert explicit ownership, or replaced by a distinct ownership primitive with `--ensure-runtime` retained as a thin liveness probe?
3. **Liveness/recovery without hand-rolled loops.** What is the right structured-verdict + recovery contract for the single liveness primitive (beyond today's `{status, mcp_tools_present, health_code}`), and what does "recover" mean for a stale/dead runtime vs. a blocked one?
4. **Torn-build orphan contract.** Prevent-by-ownership (the build survives the tear), detect-and-recover (the orphan is detected post-tear and reconciled/surfaced), or both? What does the existing `--cycle-end` friction detector already give us toward this, and what is the minimal addition?
5. **One mechanism or two.** Does a single ownership mechanism cover both long builds (terminating, artifact-producing) and the persistent dev/MCP runtime (long-lived, health-polled), or are they owned separately? Prior art in CI / ephemeral-agent harnesses for supervising both shapes.
6. **Cross-platform process supervision.** Industry-standard patterns for owning a long-lived child process that must survive an ephemeral controller's lifecycle on Windows (job objects / detached processes) and POSIX (process groups / setsid / nohup / a supervisor like a tmux/systemd-user equivalent), and which is cleanest for a stdlib-only Python harness.

## Research References

Pending — Phase 2 generates `RESEARCH_PROMPT.md` from the Open Questions above; Phase 3 integrates `RESEARCH.md` and finalizes the ownership mechanism.

Grounding context already in-repo:

- `repos/algobooth/.claude/skill-config/long-build-ownership.md` — the existing advisory long-build prose rule.
- `user/scripts/lazy_core.py` (`ensure_runtime`, `_ENSURE_RUNTIME_DEFAULT_CONFIG`, ~L6166) — the existing runtime-ensure subcommand impl.
- `user/skills/lazy-batch/SKILL.md` Step 1d.0 — where `--ensure-runtime` is called from the orchestrator session.
- `user/scripts/CLAUDE.md` — `--cycle-begin/--cycle-end` bracket + `detect_cycle_bracket_friction` (torn-bracket / unexpected-commits friction recording).
- Session-log evidence: `8ae22371` (runtime dies at turn boundary), `18e1d3d7` (`--ensure-runtime` reaped in subagent subprocess; `health_code: 0` tell), `5c33b6ba` (orphaned `tauri build` + hand-rolled poll loops).
