# Subagent backgrounds build/test verification and ends its turn before GREEN — Investigation Spec

> An implementation/test subagent invokes a build-queue skill with `run_in_background: true`, gets an immediate `enqueued as seq=N` return, and ends its turn on the enqueue — never seeing the authoritative `RESULT=` banner. The orchestrator is notified "Agent finished" while verification is still incomplete.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-09
**Placement:** docs/bugs/subagent-backgrounds-verification-ends-turn-before-green
**Related:** `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/`, `docs/bugs/write-plan-plans-bypass-build-queue-skills/`, `docs/bugs/build-queue-outcome-opacity-and-inspect-deny/`

<!-- Status lifecycle: Investigating → Concluded. Root cause is traced (serving-path chain
     cited below, fix sites on-path). Ready for /plan-bug. -->

---

## Verified Symptoms

1. **[VERIFIED]** A subagent tasked with a backend change ends its turn without having confirmed build/tests GREEN; the orchestrator receives an "Agent finished" notification while verification is still incomplete. — confirmed by user + the incident screenshot (subagent "finished" after 26m10s, final message "truncated mid-verification").
2. **[VERIFIED]** The dominant mechanism is **Gap 1 — backgrounded, reported enqueue**: the subagent runs a build-queue skill with `run_in_background: true` and ends its turn on the `enqueued`/`started` output, never on the `RESULT=` banner. — user selected this mechanism directly.
3. **[VERIFIED]** This is a **recurring** pattern, not a one-off. — user: "This is a common occurrence."
4. **[REPORTED]** The orchestrator only caught the incident because it *noticed* the truncated final message and re-resumed the subagent — i.e. detection is opportunistic, not structural. — incident screenshot.

## Reproduction Steps

1. Dispatch an implementation/test subagent for a Cognito backend change (e.g. via `/write-plan-cognito` lanes, or any generic `implementation-agent` dispatch).
2. Have the subagent verify with a build-queue skill invoked in the background:
   `Bash(command: "pwsh … build-queue.ps1 -Op mstest -Exec …", run_in_background: true)`
3. Observe the Bash tool returns **immediately** with only:
   `build-queue: enqueued as seq=N` and `build-queue: build started` — **no `RESULT=` banner** (the banner prints only after the wrapper's blocking tail loop completes).
4. The subagent, having produced a GROUND-TRUTH block that satisfies the *report-format* requirement, ends its turn.

**Expected:** The subagent may not end its turn / return control until the build-queue op has *completed* and emitted its authoritative `RESULT=PASS` banner (or an equivalent read of `results/<seq>.json` showing success). A backgrounded verification must be polled to completion first.
**Actual:** The subagent ends its turn on the enqueue; the orchestrator is notified before GREEN is known. Whether the build later passed or failed is invisible unless the orchestrator independently reconciles it.
**Consistency:** Common / recurring; manifests whenever verification is backgrounded or otherwise outlives the subagent's turn.

## Evidence Collected

### Source Code — build-queue mechanics
- `build-queue.ps1` wrapper **blocks synchronously** on the runner (tail loop `build-queue.ps1:377-397`), then prints the authoritative banner as its **last** stdout line (`build-queue.ps1:497`, `Format-BuildQueueBanner`). The banner is emitted **only** after that loop.
- With `run_in_background: true`, the Bash tool returns immediately after the early wrapper stdout — `enqueued as seq=N` (`build-queue.ps1:133`) and `build started` (`:370`) — i.e. **before the banner exists**. The detached runner writes `results/<seq>.json` (`build-queue-runner.ps1:259`) but never prints a banner.
- The four queue skills tell the agent to *trust the banner* and offer a background fallback, but the "then poll `results/<seq>.json`" instruction is **unenforced prose** — no loop, no "don't end your turn until the result is present": `msbuild/SKILL.md:36`, `mstest/SKILL.md:39`, `nxbuild/SKILL.md:38`, `nxtest/SKILL.md:39`.
- Secondary latent gap (Gap 2, not the confirmed mechanism but same class): a **foreground** build exceeding the 10-min Bash timeout gets its wrapper killed *before* `build-queue.ps1:497`, so the banner never reaches the agent and no recovery instruction exists.

### Source Code — subagent completion contract
- The "confirm GREEN before ending your turn" obligation exists **only implicitly, as a report-format requirement** — paste a GROUND-TRUTH pass/fail block: generic `implementation-agent.md:29-59` (Verification MANDATORY + GROUND-TRUTH block), Cognito `write-plan-cognito/lane-agent-briefing.md:27,86` ("capture the GREEN state" + mandatory pass/fail paste).
- There is **no explicit turn-end gate** in either contract forbidding a subagent from ending its turn with a backgrounded/detached/incomplete build. A subagent that pastes a block satisfies the letter of the contract even if the block reflects an enqueue rather than a completed GREEN.
- Backgrounding is documented as an **orchestrator-only** privilege (`subagent-launch.md:33`, `execution-contract.md:167`), but no subagent contract *forbids* a subagent from backgrounding.

### Orchestrator back-check
- Generic pipeline: the orchestrator **trusts the subagent's pasted summary by default**, re-running the suite only on a cheap-integrity mismatch (`subagent-review.md:43-50`). A premature "finished" with a plausible block is not caught structurally.
- Cognito pipeline is stronger — Step L.3 re-runs the *filtered test* as ground truth (`write-plan-cognito/SKILL.md:339`) — but explicitly never re-runs a build, and this is deliberately cheap-by-default. (Per user, orchestrator-side tightening is **out of scope** for this fix.)

### Related Documentation
- Sibling build-queue defects confirm the "banner-not-emitted / result-in-file-only" seam is a known sharp edge: `build-queue-orphaned-result-on-wrapper-kill/`, `build-queue-outcome-opacity-and-inspect-deny/`.

## Root-Cause Trace (SEAM A — serving path, `traced`)

```
surface: orchestrator "Agent finished" notification while build/test incomplete
         (subagent final message truncated mid-verification)
  → subagent invokes /mstest|/msbuild with run_in_background: true      (subagent's own tool call)
  → Bash returns immediately: only "enqueued as seq=N" / "build started"  build-queue.ps1:133, :370
  → RESULT banner prints ONLY after the blocking tail loop               build-queue.ps1:377-397, :497
       (an immediate-return background call never reaches it)
  → skill's "then poll results/<seq>.json" is unenforced prose           msbuild/SKILL.md:36 (+ mstest/nxbuild/nxtest)
       (no loop, no turn-end gate)                                        ← FIX SITE 1 (queue-skill wait mechanism)
  → subagent contract requires only a GROUND-TRUTH *block* (report-format,
       not a turn-end gate)                                              implementation-agent.md:29-59;
                                                                          lane-agent-briefing.md:27,86  ← FIX SITE 2 (contract gate)
  → orchestrator trusts the pasted summary by default                    subagent-review.md:43-50 (out of scope per user)
  = subagent ends its turn on the enqueue; GREEN never confirmed; orchestrator notified prematurely
```

**Cause label: `traced`.** Both fix sites lie *on* the traced serving path: the un-enforced poll (queue skills, FIX SITE 1) and the missing turn-end gate (subagent contracts, FIX SITE 2). Runtime evidence: the incident screenshot (a real backgrounded verification that outlived the subagent turn) plus user confirmation of Gap 1.

## Proven Findings

- **PROVEN:** The subagent CAN end its turn on a backgrounded build-queue enqueue and still satisfy the (report-format-only) completion contract — no gate forbids it. Root cause is the *absence of a turn-end gate*, compounded by the *absence of a followable wait/poll mechanism* for a backgrounded queue op.
- **RULED OUT (as fix site):** `crud-skill` — it is the meta-framework for *authoring* skill updates, not a completion-contract site. (User clarified `/crud-skill` was mentioned as the authoring framework, not a fix target.)
- **DEFERRED (out of scope per user):** orchestrator-side re-verification (`subagent-review.md` / `write-plan-cognito` Step L.3) — the fix targets the subagent's own contract + the queue skills, not the orchestrator back-check.

## Affected Area

| Component | Files | Impact / Fix role |
|-----------|-------|--------|
| Queue-skill wait mechanism | `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` (background fallback, ~:36-39) | FIX SITE 1 — replace unenforced "then poll" prose with a followable poll-until-`results/<seq>.json`-present-and-`exit_code`-read loop; cover the >10-min foreground-timeout recovery (Gap 2) too |
| Generic subagent contract | `user/skills/_components/implementation-agent.md` (+ parallel wording in `tdd-test-agent.md` for the RED side) | FIX SITE 2a — explicit turn-end gate: build/tests **completed** (never left backgrounded) + GREEN, completed pass/fail summary pasted, before producing the report |
| Cognito subagent contract | `repos/cognito-forms/.claude/skills/write-plan-cognito/lane-agent-briefing.md` (~:27, :86) | FIX SITE 2b — same explicit turn-end gate for Cognito backend/frontend lanes |
| Build-queue runner (context only) | `user/scripts/build-queue.ps1`, `build-queue-runner.ps1` | No change needed — the `results/<seq>.json` record already exists; the fix is teaching the caller to wait for it |

## Open Questions

- **Poll-loop shape for FIX SITE 1:** does the queue skill instruct the agent to poll via repeated `Bash` reads of `results/<seq>.json`, or is a small wait/poll helper (e.g. a `build-queue-await.ps1 -Seq N` that blocks until the result row is present and echoes the banner) the cleaner primitive? (Decide in `/plan-bug`.)
- **Enforcement vs. instruction:** the contract gate is prose the subagent must honor. Is a *mechanical* backstop warranted (e.g. a hook that denies a subagent ending on a live queue seq it owns), or is the prose gate sufficient given this is a recurring but self-honesty-shaped failure? (Weigh in `/plan-bug`.)
