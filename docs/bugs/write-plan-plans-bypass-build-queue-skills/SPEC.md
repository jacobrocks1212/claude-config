# `/write-plan` (Cognito Forms) generates plans that bypass the build-queue skills — Investigation Spec

> The Cognito Forms variant of `/write-plan` bakes **raw** `dotnet build` / `dotnet test` / `npx nx test` commands into the plans it generates (both the orchestrator's in-loop gate steps and the dispatched lane agents' verification commands). Those raw commands do **not** route through the machine-global build-queue serializer (`build-queue.ps1`), so generated plans reintroduce exactly the cross-worktree/cross-session DLL-lock contention the queue exists to prevent — and forgo the output filtering that keeps build/test noise out of context. The four wrapper skills (`/msbuild` `/mstest` `/nxbuild` `/nxtest`) are the only queue entry points; the generated plans must use them.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-24
**Placement:** docs/bugs/write-plan-plans-bypass-build-queue-skills
**Related:** `docs/specs/build-queue/` (build-queue feature spec + plans); `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/SPEC.md` (sibling queue defect); `repos/cognito-forms/.claude/skills/write-plan/{SKILL.md,lane-agent-briefing.md}`; `repos/cognito-forms/.claude/skill-config/quality-gates.md`; `user/scripts/build-queue.ps1`; `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md`
**Branch:** `build-queue`

<!-- Status lifecycle:
  - Investigating → root cause not yet proven.
  - Concluded     → root cause proven, affected area + fix scope understood; ready for /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** The generated-plan **template** emits raw build/test commands the executing orchestrator runs directly. The typegen seam step writes a raw `dotnet build …Cognito.Services.csproj` and the type-regen script (`SKILL.md` 300-302), and the in-loop Tier-1 verification is described in terms of raw `dotnet test --no-build --filter` (`SKILL.md` 312, 318-320). None of these route through `build-queue.ps1`. Confirmed by reading the skill source this session.
2. **[VERIFIED]** The **lane-agent briefing** that ships verbatim inside every dispatched lane agent's prompt instructs raw commands as the agent's Tier-1 verification: raw `dotnet build …Cognito.UnitTests.csproj` + `dotnet test --no-build --filter` for backend, raw `npx nx test <project> -- --testPathPattern=…` for frontend (`lane-agent-briefing.md` 31-49). Lane agents therefore build/test outside the queue.
3. **[VERIFIED]** Lane agents are dispatched with tools `Edit, Write, Read, Bash, Grep, Glob` — **no `Skill` tool** (`SKILL.md` 172). As written they *cannot* invoke `/mstest` / `/nxtest` even if instructed to. The established pattern across the generic `_components/` (subagent/implementation/tdd briefings) is that subagents never invoke wrapper skills — confirmed by grep returning no skill references in those components.
4. **[VERIFIED]** The wrapper skills are the only queue entry points. `build-queue.ps1` is a machine-global FIFO serializer accepting exactly four ops — `msbuild, mstest, nxbuild, nxtest` — each routed to its filtered script via `-Exec` (`build-queue.ps1` synopsis + `ValidateSet`). A hook blocks invoking the `*-filtered.ps1` scripts directly ("BUILD QUEUE ENFORCED — use `/mstest` or `/nxtest`"), so raw `dotnet`/`nx` commands are the *only* way to build/test off-queue — which is precisely what the generated plans do.
5. **[VERIFIED — partial mitigation already present]** The Tier-2 part-end gate already uses the skills correctly (`/msbuild` → `/mstest`, `/nxbuild` → `/nxtest`; `SKILL.md` 332-336, `quality-gates.md` Tier-2 section), and the frontend Tier-1 row in `quality-gates.md` already *offers* `/nxtest` as an option. The gap is the in-loop **backend** test, **all lane-agent** commands, and the explicit instruction in `quality-gates.md` to hand agents the raw Tier-1 commands ("give them the Tier 1 commands above … not `/msbuild`").

## Reproduction Steps

1. Run `/write-plan <PHASES.md>` in the Cognito Forms repo and open the generated plan + the referenced `lane-agent-briefing.md`.
2. Execute the plan: the orchestrator dispatches lane agents whose briefing tells them to run raw `dotnet build`/`dotnet test`/`npx nx test`; the orchestrator's own Tier-1 ground-truth re-run mirrors those raw commands.
3. Run two such plans concurrently (or one alongside any other session/worktree building), as the build-queue is explicitly designed to handle.

**Expected:** Every build/test the generated plan causes to run — orchestrator and lane agents alike — routes through `build-queue.ps1` (via `/msbuild` `/mstest` `/nxbuild` `/nxtest`), so they serialize machine-globally and emit filtered output.
**Actual:** Raw `dotnet`/`nx` commands run off-queue, reintroducing DLL-lock contention across worktrees/sessions (MSB3027/MSB3021) and dumping unfiltered build/test output into context.
**Consistency:** Deterministic — it is baked into the skill's plan template and lane-agent briefing.

## Evidence Collected

### Source Code

- **Generated-plan template — `repos/cognito-forms/.claude/skills/write-plan/SKILL.md`:**
  - Typegen seam (Step L.2): raw `dotnet build …Cognito.Services.csproj …` (300) + `generate-server-types.ps1 -UpdateInPlace` (301-302). The incremental Services build is intentionally **not** a full-solution build.
  - Step L.3 ground-truth re-run: "re-run the lane's test command **exactly as pasted**" (312) — couples the orchestrator's re-run command to whatever the lane agent used. Fixing one side without the other breaks the falsified-report check.
  - Step L.5 Tier-1 (318-320) and the part-end Tier-2 gate (332-336): Tier-2 already calls `/msbuild`/`/mstest`/`/nxbuild`/`/nxtest`; Tier-1 is described via raw `--no-build` filtered tests.
  - Lane-agent tool grant (172): `Edit, Write, Read, Bash, Grep, Glob` — no `Skill`.
- **Lane-agent briefing — `…/write-plan/lane-agent-briefing.md`:**
  - "Verification Commands (Tier 1)" (31-49): raw backend `dotnet build`/`dotnet test --no-build --filter`; raw frontend `npx nx test`.
  - Hard Boundaries (56): "Do NOT run `/msbuild`, full `Cognito.sln` builds, or unfiltered test runs" — correctly forbids the *full* build but, combined with the raw commands above, currently steers agents entirely off-queue.
  - Report format (64-68): the `GROUND-TRUTH OUTPUT` block pastes "your Tier 1 test command and its full pass/fail summary," which the orchestrator re-runs verbatim.
- **Quality gates — `repos/cognito-forms/.claude/skill-config/quality-gates.md`:**
  - Tier-1 backend: raw incremental `dotnet build …csproj` + `dotnet test --no-build --filter`.
  - Tier-1 frontend: already offers `/nxtest -Project … -Pattern … -NoCoverage` (or raw `npx nx test`).
  - Explicit instruction: "When you compose implementation/test agent prompts, give them the **Tier 1 commands above** … not `/msbuild` or a full `Cognito.sln` build." — this is the line that propagates raw commands into lane agents.
  - Typegen section: raw incremental `dotnet build …Cognito.Services.csproj` + "Do NOT run `/msbuild` just to regenerate types."
- **Queue + enforcement:**
  - `user/scripts/build-queue.ps1` — machine-global FIFO serializer; `-Op` ∈ {`msbuild`,`mstest`,`nxbuild`,`nxtest`} only; forwards remaining args to the `-Exec` filtered script.
  - Hook output observed this session when reading a `*-filtered.ps1` via shell: "BUILD QUEUE ENFORCED — use `/mstest` or `/nxtest` … The skills route through the queue automatically." Confirms the skills are the sanctioned entry points and direct script use is blocked.

### Git History

- Current branch `build-queue` is the active build-queue hardening effort; the sibling `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/SPEC.md` is part of the same push. This defect is the "producers that don't use the queue" companion to that "queue robustness" work.

### Related Documentation

- `docs/bugs/CLAUDE.md` — harness-defect convention (descriptive slug, no work-item, Investigating→Concluded lifecycle). Followed here.
- `repos/cognito-forms/CLAUDE.local.md` — documents the four skills as the filtered build/test entry points and the DLL-copy-lock contention failure mode (MSB3027/MSB3021) the queue prevents.

## Theories

### Theory 1: Generated plans were authored around raw commands predating queue enforcement — CONFIRMED
- **Hypothesis:** The variant's Tier-1 design (cheap incremental builds + filtered `--no-build` tests) was expressed as literal `dotnet`/`nx` commands before/independent of the build-queue, and only the Tier-2 gate was later migrated to the wrapper skills. The in-loop path and lane briefing were never migrated.
- **Supporting evidence:** Tier-2 already uses all four skills (`SKILL.md` 332-336) while Tier-1 and the lane briefing use raw commands; `quality-gates.md` explicitly tells agents to use raw Tier-1 commands "not `/msbuild`."
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

1. The wrapper skills are the **only** queue entry points; any raw `dotnet`/`nx` command runs off-queue. Generated plans run many such commands, per loop iteration and per lane agent.
2. There is a real **capability gap for builds**: `/msbuild` is **full-`Cognito.sln`-only** — it has no incremental/single-project mode (`msbuild/SKILL.md` usage + args). The variant's whole purpose is to *avoid* full builds in-loop, so the Tier-1 incremental `Cognito.UnitTests.csproj` build and the typegen `Cognito.Services.csproj` build **cannot** be replaced by `/msbuild` as it exists today. Tests have no such gap — `/mstest` is `--no-build` + filtered (exactly Tier-1) and `/nxtest` is filtered.
3. Lane agents have no `Skill` tool, but they do have `Bash`. They can route through the queue **either** by being granted the `Skill` tool **or** by invoking the queue entry point directly: `build-queue.ps1 -Op mstest -Exec <test-filtered.ps1> -Filter …`. Both paths serialize; the choice is a fix-design decision.
4. The orchestrator ground-truth re-run is coupled to the lane agent's command ("exactly as pasted," `SKILL.md` 312). Both sides must change together, or the re-run can be decoupled to "run the equivalent `/mstest -Filter <same filter>`" since pass/fail (not byte-identical output) is what the falsified-report check needs.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Generated-plan template (orchestrator steps) | `repos/cognito-forms/.claude/skills/write-plan/SKILL.md` (172, 300-302, 312, 318-320, 332-336) | In-loop Tier-1 + ground-truth re-run emit raw commands; lane-agent tool grant omits `Skill` |
| Lane-agent briefing (shipped in every lane prompt) | `repos/cognito-forms/.claude/skills/write-plan/lane-agent-briefing.md` (31-49, 56, 64-68) | Lane agents build/test off-queue with raw commands |
| Quality-gates config | `repos/cognito-forms/.claude/skill-config/quality-gates.md` (Tier-1 backend/frontend, typegen, "give agents the Tier-1 commands" line) | Propagates raw Tier-1 commands; only Tier-2 + frontend row use skills |
| Build-queue (unchanged; the system being bypassed) | `user/scripts/build-queue.ps1`; `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` | The queue + skills that generated plans must route through |

## Proposed Fix Direction

Decided with Jacob this session: **both** the orchestrator **and** the dispatched lane agents must route every build/test that has a wrapper-skill equivalent through the queue, because the skills are the only path onto `build-queue.ps1`. Sketch for `/plan-bug` to refine:

- **Tests → skills, everywhere.** Replace raw `dotnet test --no-build --filter` with `/mstest -Filter "ClassName~…"` and raw `npx nx test` with `/nxtest -Project … -Pattern … -NoCoverage`, in the plan template (Tier-1 + ground-truth re-run), the lane-agent briefing, and `quality-gates.md`. `/mstest` is already `--no-build` + filtered, so it is Tier-1-faithful.
- **Lane agents must reach the queue.** Either (a) grant lane agents the `Skill` tool (update the `SKILL.md` tool grant + dispatch note + briefing) and have them call `/mstest`/`/nxtest`, or (b) have them invoke the queue entry point directly via Bash (`build-queue.ps1 -Op … -Exec …`). Pick one in `/plan-bug`; (a) is cleaner if subagents can invoke wrapper skills, (b) is the zero-dependency fallback.
- **Keep the ground-truth check consistent.** Either change both lane agent and orchestrator to the same skill command, or relax `SKILL.md` 312 to "re-run the equivalent `/mstest -Filter <same filter>`" (pass/fail comparison, not byte-identical output).
- **Builds: resolve the `/msbuild` full-solution gap explicitly.** The incremental Tier-1 build and the typegen `Cognito.Services` build cannot use `/msbuild` today. Options: (i) leave those two incremental builds raw and document *why* (no incremental queue op exists) so the "use the skills" rule isn't silently contradicted — accepting that builds stay off-queue; (ii) add an incremental/single-project op to the queue + a skill (e.g. `/msbuild -Project …` backed by a `-Project` arg in `build-filtered.ps1`, or a new op) so builds serialize too. (ii) fully closes the contention hole the user cares about; (i) is the minimal doc-only change. **Open decision for `/plan-bug`.**

## Open Questions

- **Can a dispatched Sonnet subagent invoke a wrapper skill (`Skill` tool), including one with `model: haiku` frontmatter?** If not, lane agents must use the direct `build-queue.ps1` Bash invocation (fix option b). Needs a quick runtime check before committing to fix option (a).
- **Do we close the build-side contention hole now (add an incremental queue op/skill) or defer it** and only route tests + full builds through the queue? This is the main scope fork for `/plan-bug`.
- **Should the typegen incremental `Cognito.Services` build stay raw** (it has no skill equivalent and is explicitly excluded from `/msbuild` by `quality-gates.md`), with an inline justification comment, or also move behind a new incremental op?

## Resolution (2026-07-09)

The three fix-scope decisions above were resolved as follows (orchestrator-chosen during the interactive bug-fix orchestration; surfaced to Jacob for review):

- **D1 — gates use the skills, everywhere: DONE (largely pre-landed).** The skill was rewritten (write-plan-cognito v3, uncommitted at fix time) so the plan template, Tier-1/Tier-2 gates, and `quality-gates.md` all mandate `/msbuild [-Project]` / `/mstest -Filter` / `/nxbuild` / `/nxtest` and explicitly forbid raw `dotnet`/`npx nx`. Verified by grep: zero raw build/test commands remain in `write-plan-cognito/` (SKILL.md, lane-agent-briefing.md, execution-contract-cognito-lanes.md) or `skill-config/quality-gates.md`.
- **D2 — lane agents reach the queue: option (a) primary, option (b) fallback.** The lane execution contract grants lane agents the `Skill` tool for `/msbuild`/`/mstest`/`/nxtest` (resolving Verified Symptom 3's missing tool grant). Because the "can a Sonnet subagent invoke a wrapper skill" runtime check remains unverified, `lane-agent-briefing.md` now also carries the zero-dependency fallback: direct `build-queue.ps1 -Op <op> -Exec <filtered-script>` invocation via Bash (hook-allowed, same queue entry point), plus the "trust the final `build-queue:` RESULT banner" instruction. Raw `dotnet`/`npx nx` remains forbidden on every path.
- **D3 — build-side contention hole: CLOSED by `/msbuild -Project` (not deferred).** Since this SPEC was written, `build-filtered.ps1`/`/msbuild` gained a `-Project` single-project incremental op (queue-serialized, filtered), so Proven Finding 2's "full-solution-only" gap no longer exists. The Tier-1 incremental build and the typegen `Cognito.Services` build now route through `/msbuild -Project "…"` — no new queue op needed, and the typegen build is no longer raw (third open question mooted).
