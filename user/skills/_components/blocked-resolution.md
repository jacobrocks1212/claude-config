## Blocked-resolution mode (shared — `terminal_reason == "blocked"`)

**Why this component exists.** The blocked-resolution handler (Step 1h of the batch
orchestrators) is identical across the feature and bug pipelines except for pipeline
vocabulary. This is the single source; each consumer binds the pipeline tokens below,
then `!cat`s this file (the sibling of `decision-resume.md`).

### Pipeline binding (the consuming skill sets these immediately before the include)

| token | feature pipeline | bug pipeline |
|-------|------------------|--------------|
| `{SKILL}` | `/lazy-batch` (or `/lazy-batch-cloud`) | `/lazy-bug-batch` |
| `{STATE_SCRIPT}` | `lazy-state.py` | `bug-state.py` |
| `{ITEM}` | feature | bug |
| `{SPEC_ROOT}` | `docs/features` | `docs/bugs` |
| `{ADD_PHASE}` | `/add-phase` | `/add-phase` (or `/plan-bug` if `PHASES.md` is absent) |
| `{PUSH_RULE}` (apply subagent) | workstation: standard push · **cloud: push IMMEDIATELY after each commit (container-reclaim durability)** | workstation: standard push |

Runtime placeholders (`{feature_id}`, `{feature_name}`, `{spec_path}`, `{cwd}`, `{phase}`,
`{retry_count}`, `{blocker_kind}`, `{cycle}`, `{max_cycles}`) are filled from the
state-script JSON — **both** pipelines use the JSON field `feature_id` (the bug id rides in it).

Triggered when `{STATE_SCRIPT}` reports `blocked` — a cycle subagent (or a hand edit) wrote `BLOCKED.md` because it hit a genuine blocker it could not resolve autonomously (a missing upstream surface, an ambiguous failure, a real bug needing a planning decision). **`blocked` is no longer a terminal halt — and most blockers no longer ask.** STEP ONE is the blocker classification per `~/.claude/skills/_components/completeness-policy.md` §3 (step 1b below): a **sequencing-only** blocker — every resolution path converges on the same product behavior — is auto-resolved by standing policy (add-phase + fix now, or spin-off + dependency-gate + requeue), logged + push-notified, and the loop continues with NO question. Only a blocker embedding a **genuine product fork** takes the operator path: the orchestrator surfaces it via `AskUserQuestion`, captures the chosen resolution path, records it, dispatches an Opus apply-resolution subagent to ENACT that path (neutralizing `BLOCKED.md`), and **continues the loop**. The sole stopping exception is the explicit **Halt for manual fix** choice, which preserves the legacy stop-for-human behavior.

This replaces the old **zero-context halt** (a bare `PushNotification` + STOP that handed the operator a one-line `notify_message` and nothing actionable). The operator now sees the full blocker context in chat and directs how the pipeline proceeds.

**Algorithm:**

1. **Read the sentinel.** `{spec_path}/BLOCKED.md`. Parse the YAML frontmatter (`kind`, `feature_id`, `phase`, `blocked_at`, `retry_count`, and `blocker_kind` if present) and read the markdown body. Unlike `NEEDS_INPUT.md`, `BLOCKED.md` has no mandated rich-body schema — a thin body is NOT a malformation halt; proceed, noting in chat if the blocker context is sparse.

1a. **Seam-batched corrective-phase policy (mcp-validation blockers — standing policy at EVERY retry level, not gated by escalation).** If the frontmatter shows `blocker_kind: mcp-validation`, at ANY `retry_count` (including 0 — the FIRST validation failure for this {ITEM}), the validation cycle that wrote this `BLOCKED.md` already enumerated every boundary in the failing chain into a `## Seam Enumeration` section (mandated in `cycle-base-prompt.md` R14 / the AlgoBooth `mcp-test` SKILL's Step 5 — enumeration happens at validation time, the cheapest point, not two loops later). **Every resolution path that enacts a corrective phase MUST scope that phase to the FULL enumerated seam set** (every `probed-FAIL` + `unprobed` row), never the single observed failure — consume the `## Seam Enumeration` section verbatim as the phase's checklist, and live-probe each seam post-fix BEFORE re-dispatching full validation. A single-layer corrective phase for an `mcp-validation` blocker is a drafting error at ANY retry level (not just at escalation) — include this requirement verbatim in the `{ADD_PHASE}` description and the apply-subagent prompt (step 6 carries the clause). This is what closes the "one seam discovered per full pipeline loop" pattern (d8-live-looping burned three ~1M-token rounds peeling one layer per round back when enumeration + batched scoping were gated behind two prior loops — the round-trip cost this policy now eliminates from round 1).

   **Escalation tier (`retry_count >= 2` — the state script also signals this mechanically via `validation_escalation: true` in its JSON).** Repeated failure DESPITE an already-batched seam fix means the enumeration itself missed something, or the root cause is not what it looked like: `/investigate` is now MANDATORY before the next corrective phase, ON TOP OF (not instead of) the batched-seam-set requirement above.

   **Investigate FIRST at the escalation tier (the seam audit's executor):** before enacting ANY corrective-phase path once `retry_count >= 2`, check `{spec_path}/INVESTIGATION.md`. If absent or stale (freshness: `investigated_commit` == HEAD, or only that investigation's own `diag(...)` commits since), dispatch an `/investigate` cycle per `~/.claude/skills/_components/investigation-dispatch.md` (workstation runs dispatch now; cloud runs record the trigger and defer to a workstation run) and WAIT for its artifact before proceeding. The subsequent `{ADD_PHASE}` description then cites the artifact — its confirmed Hypothesis-Ledger rows and `## Recommended Fix Scope` — instead of restating the blocker narrative or the orchestrator's own inference. Do NOT pass orchestrator hypotheses to the corrective phase as fact; unproven hunches go to the investigation, labeled `unproven` (the no-narrative-as-fact rule lives in the dispatch component).

1a-research. **Research-blocked carve-out (surface the research prompt, do NOT run the blocked-resolution `AskUserQuestion`) — STEP ZERO, before classification.** A `blocked` terminal whose *real* unmet prerequisite is a missing round-N Gemini deep research is NOT a product-fork blocker and MUST NOT be routed into the steps 2–7 `AskUserQuestion` resolution menu — that menu (add-a-phase / defer / halt / custom) is the WRONG affordance for a research gap and strands the operator with an abstract choice instead of the one artifact they need: the pastable research prompt. This carve-out fires FIRST (before step 1b classification) and short-circuits to the consumer's own needs-research handler.

   **Detection signature (ALL must hold — read at trip time from `{spec_path}`):**
   - `{spec_path}/BLOCKED.md` is present (this handler is running), AND
   - a **live** `{spec_path}/NEEDS_RESEARCH.md` sentinel is on disk (`kind: needs-research`, not a neutralized `*_RESOLVED_*` rename), AND
   - `{spec_path}/RESEARCH_PROMPT.md` is present, AND
   - `{spec_path}/RESEARCH.md` is **absent** (the round-N research has not landed; a prior round may have been archived to `RESEARCH_ROUND1.md` / `RESEARCH_PROMPT_ROUND1.md` — those archived names do NOT satisfy the present-RESEARCH.md check).

   The `BLOCKED.md` `recovery_suggestion` pointing at `RESEARCH_PROMPT.md` (e.g. "Run round-2 Gemini deep research (RESEARCH_PROMPT.md), ingest as RESEARCH.md, then resume") is a confirming signal, not a required one — the four filesystem facts above ARE the trigger. `blocker_kind: prerequisite-part-incomplete` is the common originating kind (an `/execute-plan` part whose unmet prerequisite is the research), but the carve-out keys on the research-sentinel signature, NOT on `blocker_kind` (any blocker carrying the live-needs-research signature is research-blocked).

   **When the signature matches:** do NOT run steps 2–7. Instead, route to the consuming pipeline's **needs-research surfacing behavior** — for `/lazy-batch` and `/lazy-batch-cloud` this is **Step 4 (Research Halt)**: read `RESEARCH_PROMPT.md` (applying the one-level pointer resolution if it is a legacy pointer), print the fenced ` ```text ` prompt block + FASTEST-RESUME upload instructions per `~/.claude/skills/_components/lazy-batch-prompts/research-halt-announcement.md` (Variant A), then `--run-end` + `PushNotification` + T7 report and STOP (the strict-halt default) — exactly as if the state script had returned `needs-research` for this feature. The operator pastes the prompt into Gemini; the resume signal is their next message / re-invocation. The `BLOCKED.md` is left in place (the research gap is the real blocker; surfacing the prompt does not neutralize it — when `RESEARCH.md` lands the operator/ingest path clears both the research gap and the stale block). **Do NOT** dispatch the apply-resolution subagent, **do NOT** call `AskUserQuestion`, **do NOT** add-a-phase: a research gap is filled by Gemini research, not by a corrective phase.

   **Pipelines with no research concept (the bug pipeline, `/lazy-bug-batch`):** the signature can NEVER match — a `docs/bugs/` item carries no `NEEDS_RESEARCH.md` / `RESEARCH_PROMPT.md` (bugs do not undergo Gemini deep research). This step is therefore an inert no-op there; the bug orchestrator falls straight through to step 1b exactly as before. (Stated explicitly so a future reader does not bind a needs-research route into the bug pipeline.)

   *Burned on `clap-plugin-host-chain-slot`, 2026-06-24:* a feature blocked with `blocker_kind: prerequisite-part-incomplete` and co-located live `NEEDS_RESEARCH.md` + `RESEARCH_PROMPT.md` (`RESEARCH.md` intentionally absent, round-1 archived to `RESEARCH_ROUND1.md`) was routed into the Step 1h blocked-resolution `AskUserQuestion` menu. The operator-correct response was to surface the round-2 research prompt (Step 4 needs-research behavior) so it could be pasted into Gemini — the abstract resolution menu was the wrong affordance for a research gap. (Mirror of the `d8-effect-chains` ANTI-EXEMPTION lesson: a research gap is cleared only by THIS feature's `RESEARCH.md`, never by a down-grade or a substitute corrective path.)

1b. **Classify the blocker FIRST (completeness-policy §3 — STEP ONE, before any re-print or question).** Apply the scope test from `~/.claude/skills/_components/completeness-policy.md`: does every resolution path converge on the same product behavior (the standard "fix now / defer / halt" shape)? If **YES — sequencing-only** — auto-resolve per the policy, NO `AskUserQuestion`. Pick the matching resolution:

   - **In-scope defect** (missing / under-scoped work within this {ITEM} — the common case) → the complete path: `{ADD_PHASE}` + fix now. Append the `## Resolution` block to `BLOCKED.md` (step 5 shape, with `**Chosen path:** Add a phase to resolve the blocker` and a `resolved_by: completeness-policy` line), then dispatch the apply-resolution subagent (step 6) with that path — the same machinery, minus the question.
   - **Discovered defect beyond this {ITEM}'s scope** → spin off `/spec-bug`: the apply subagent authors the bug doc directly (per the established dispatched-subagent pattern), cross-references BOTH docs (the new doc names its origin; the origin names the spin-off), dependency-gates the current {ITEM} if it cannot proceed without the fix, and requeues it to the END of `{SPEC_ROOT}/queue.json` (the Defer mechanics from step 3's option list). Record the chosen path in the `## Resolution` block (`resolved_by: completeness-policy`) before dispatch.
   - **Feature-scope growth** (the blocker reveals work that is a new feature, not a defect) → spin off a new {ITEM} via the `--enqueue-adhoc` bootstrap + a brief, cross-reference both ways, dependency-gate as needed. Same `## Resolution` + apply-subagent machinery.

   For every auto-resolution: emit one chat line — `⚖ policy: {blocker, ≤8 words} → {chosen path}[ · spun off {id}]` — fire `PushNotification` (`"spun off {id} — {reason}"` for spin-offs; the resolution one-liner otherwise), record a D7-digest entry, then record-and-continue per step 7. Spin-offs are pre-authorized (notify + log, no cap — never ask permission to spin off). Neutralization rules are unchanged: every path except a pure requeue-to-tail neutralizes `BLOCKED.md` by rename (see step 6); a dependency-gated requeue leaves `BLOCKED.md` in place exactly like the operator "Defer" path.

   If **NO** — the resolution paths embed a **genuine product fork** (two complete-but-different end states, a conflict with a SPEC Locked Decision, or a destructive / outward-facing operation) — fall through to steps 2–7: the existing verbatim re-print + `AskUserQuestion` flow, unchanged.

2. **Re-print the blocker context to chat VERBATIM** (HARD CONSTRAINT 6 applies here too — the load-bearing context BEFORE the truncated `AskUserQuestion` UI; this is the antidote to the old zero-context halt):

   ```
   🚧 {SKILL} — Blocked (loop resumes after you choose a resolution path)

   Feature: {feature_name} ({feature_id})
   Phase:   {phase}   ·   retry_count: {retry_count}   ·   blocker_kind: {blocker_kind or "—"}
   File:    {spec_path}/BLOCKED.md

   ─── BLOCKED.md body (verbatim) ──────────────────────────────────────────

   {entire markdown body — blocker description, evidence, and any recovery
   suggestion the cycle subagent recorded — copy/paste as-is, no summarization.}

   ─────────────────────────────────────────────────────────────────────────

   Choose how the pipeline should proceed. After you answer, I dispatch an Opus
   subagent to enact your choice (and neutralize BLOCKED.md), then resume the
   loop — unless you choose "Halt for manual fix".
   ```

3. **Call `AskUserQuestion` with ONE question — the resolution path.** `header`: "Resolution". Where the `BLOCKED.md` body names a concrete recovery (e.g. "add an `{ADD_PHASE}` Phase N for X"), adapt the matching option's `description` to reference it so the recommended path is specific to this blocker. The archetype options:

   - **Add a phase to resolve the blocker** — dispatch `{ADD_PHASE}` against this {ITEM} with the blocker as the new phase's motivation, then neutralize `BLOCKED.md`. The pipeline re-plans → implements → re-validates the {ITEM}. *Recommended when the blocker is missing / under-scoped work (the common case — e.g. a missing MCP surface a validation step needs).*
   - **Defer this {ITEM}; continue the rest of the queue** — move this {ITEM}'s `{SPEC_ROOT}/queue.json` entry to the END of the queue (`BLOCKED.md` kept in place) so the next actionable {ITEM} becomes current. The blocked {ITEM} resurfaces only after the rest of the queue is worked.
   - **Halt for manual fix** — keep `BLOCKED.md` untouched, `PushNotification`, print the final batch report, STOP. The legacy escape hatch for blockers you want to handle by hand.

   The auto-provided **Other** lets the operator type a custom directive, enacted verbatim by the apply subagent. Capture the choice + any free-text note. (`multiSelect: false` — the paths are mutually exclusive.)

4. **If the choice is "Halt for manual fix":** do NOT modify `BLOCKED.md`. Append `{cycle+1, feature_name, "🛑 blocked (operator chose manual halt)", "{phase}"}` to `cycle_log`, `PushNotification` with `notify_message`, print the final batch report (Step 2), and **STOP**. This is the ONLY path here that halts.

5. **Otherwise, append a `## Resolution` section to `BLOCKED.md`** recording the chosen path, the operator's note (if any), and a timestamp — same `Edit`-append pattern as decision-resume step 4 (HARD CONSTRAINT 1 permits appending `## Resolution` to `BLOCKED.md`):

   ```markdown

   ## Resolution

   *Recorded on <YYYY-MM-DD HH:MM:SS UTC>.*

   **Chosen path:** <option label>
   **Notes:** <operator's free-text note, or empty>
   ```

   Commit `BLOCKED.md` with message `docs({feature_id}): record blocker resolution path`. Do NOT push (consistent with other orchestrator-inline commits; the apply subagent pushes).

6. **Dispatch the apply-resolution subagent to ENACT the chosen path — via `{STATE_SCRIPT} --emit-dispatch apply-resolution`, NOT by hand-composing the prompt below.** During a marked run the dispatch guard (`lazy-dispatch-guard.sh`) DENIES any `Agent` dispatch whose prompt was not script-emitted this turn. The ONLY sanctioned route is the consuming skill's **Step 1h apply-resolution wiring**: run `{STATE_SCRIPT} --emit-dispatch apply-resolution` (binding `resolution_kind=blocked`, the chosen option into `chosen_path`, and the other `@requires` context keys), then dispatch the returned `dispatch_prompt` **VERBATIM** using the returned `dispatch_model` (by-reference). The prompt block below is the apply-resolution subagent's CONTRACT — what the emitted prompt covers — and is shown for REFERENCE ONLY; it is NOT the orchestrator's composition source. Do not paste, hand-compose, or hand-edit it into an `Agent` call (that hand-composed-prompt-reaching-the-guard path is exactly the divergence the guard exists to catch). For reference, the emitted prompt directs the subagent to:

   ```
   You are enacting an operator-chosen resolution for a BLOCKED {ITEM} in the
   autonomous pipeline, then neutralizing the blocker so the loop can resume.

   Feature: {feature_name} ({feature_id})
   Working directory: {cwd}
   Sentinel:          {spec_path}/BLOCKED.md  (read its body + the appended
                      `## Resolution` for the chosen path + operator notes)

   CHOSEN PATH: {option label}   NOTES: {operator note or "—"}

   Enact EXACTLY the chosen path:

   • "Add a phase to resolve the blocker":
       Invoke the {ADD_PHASE} skill (via the Skill tool — you MAY use it; you may
       NOT use Agent) against {feature_id}, authoring a new phase whose scope is
       the blocker described in BLOCKED.md (and any recovery the cycle subagent
       suggested). It appends the phase to PHASES.md (In-progress, with
       unchecked deliverables) per its own contract.
       PHASE KIND (HARD REQUIREMENT): a blocker-resolution phase whose scope is
       making the impl satisfy the EXISTING spec — i.e. `blocker_kind:
       mcp-validation` or `execute-plan-scope` — is a CORRECTIVE phase. Instruct
       {ADD_PHASE} to tag it `**Phase kind:** corrective` (pass this in the phase
       description). A corrective phase does NOT re-trigger `/retro` (no design
       surface changed), so the re-validation cycle runs without a wasteful retro
       round in front of it. Only tag `design` if the resolution genuinely
       expands the design surface (rare for a blocker resolution).
       RECONCILE THE ORIGINATING PLAN (HARD — when the new corrective phase
       SUPERSEDES deliverables belonging to an originating In-progress plan): if
       the new phase makes prior deliverables architecturally impossible /
       obsolete and those deliverables were struck in PHASES.md, you MUST also
       reconcile any originating implementation plan under {spec_path}/plans/
       whose per-WU checkboxes track those SAME superseded deliverables. The
       router (Step 7a) prioritizes finishing any plan whose frontmatter
       `status:` is `In-progress` with unchecked `- [ ] WU-N` rows; an
       unreconciled originating plan re-routes /execute-plan back to the
       superseded, now-impossible WUs and re-blocks (an infinite loop). For EACH
       such originating plan (`plans/*.md`, `status: In-progress`):
         (a) strike each superseded WU row in its `## Work Units` checklist with
             the canonical descoped marker — turn `- [ ] WU-N — <title>` into
             `- [ ] ~~WU-N — <title>~~ **SUPERSEDED** <!-- descoped -->` (SSOT
             `lazy_core:_DESCOPED_MARKER`; the strikethrough + marker is what drops
             the row from the router's unchecked-WU count), citing the new phase;
         (b) if EVERY remaining WU row is then either `[x]` landed or struck
             `~~...~~ **SUPERSEDED**`, flip the plan's frontmatter `status:` to
             `Complete` so the router filters it out; else leave it In-progress.
       Do NOT touch plans whose deliverables the new phase does NOT supersede.
       Then NEUTRALIZE BLOCKED.md
       (see below). The next loop cycle's {STATE_SCRIPT} routes the {ITEM} to
       plan/implement the new phase.
       SEAM-BATCHED SCOPE (HARD, mcp-validation blockers at ANY retry_count):
       the new phase MUST carry a full-chain seam-audit deliverable scoped to
       the FULL `## Seam Enumeration` section BLOCKED.md's validation cycle
       already wrote (every `probed-FAIL` + `unprobed` row) — live-probe each
       seam post-fix to the final observable BEFORE full re-validation. Do NOT
       author a single-layer fix phase scoped to only the one failure named in
       the blocker body.
       ESCALATION (ADDITIONALLY, only when the orchestrator flagged
       validation-escalation — blocker_kind mcp-validation + retry_count >= 2):
       the phase must ALSO consume {spec_path}/INVESTIGATION.md (the
       investigation cycle's artifact — its Seam Table and confirmed
       Hypothesis-Ledger rows are citable runtime evidence; its Recommended Fix
       Scope seeds the phase's file list). Do NOT bake unproven narrative into
       the phase as fact — unproven hunches are the investigation's job, not
       the corrective phase's.
       CANONICAL MARKER (harness-hardening-retro-fixes Phase 2): every
       runtime-verification / full-chain-seam-audit `- [ ]` checkbox the
       corrective phase authors (the seam-audit re-probe rows, the
       Runtime-Verification rows) MUST be marker-exempt via the canonical marker
       `<!-- verification-only -->`. Emit it on the seam-audit / Runtime-
       Verification SUBSECTION HEADER line (header-scope — it exempts every row
       beneath, is authored ONCE on the fixed header string, and SURVIVES the
       freehand row authoring that drops per-row HTML comments — the live gap in
       `docs/bugs/verification-only-marker-dropped-on-freehand-rows`), AND on
       each row where practical, e.g. `**Full-chain seam audit**
       <!-- verification-only -->` on the header and
       `- [ ] <!-- verification-only --> seam: user-surface → IPC live-probe
       returns a non-error response` on the rows. The state-script detector
       `remaining_unchecked_are_verification_only()` keys off this marker
       structurally (independent of the header free text — see the
       full-chain-seam-audit header convention), so these intentionally-unticked
       rows are recognized as Step-9 mcp-test-owned and never misread as remaining
       implementation work. The marker string is the SSOT
       `lazy_core:_VERIFICATION_ONLY_MARKER` — do NOT re-hardcode a divergent
       string (the lockstep test asserts producer prose == that constant).

   • "Defer this {ITEM}; continue the rest of the queue":
       Run the deterministic, operator-only / out-of-cycle reorder subcommand —
       do NOT hand-edit queue.json (the orchestrator calls the script; HARD
       CONSTRAINT 1's no-direct-queue.json-edit rule holds):
         python3 ~/.claude/scripts/{STATE_SCRIPT} --repo-root {repo_root} \
             --reorder-queue --id <this-{ITEM}-id> --to tail
       This moves this {ITEM}'s entry to the END of the `queue` array atomically
       (the script reuses lazy_core.reorder_queue / `_atomic_write`; the
       queue.topo-order rule may emit an advisory warning for a deferred
       hard-upstream — acceptable for an operator-chosen defer). It is gated by
       refuse_if_cycle_active, so it runs only from the orchestrator session
       (out-of-cycle), never a cycle subagent. LEAVE BLOCKED.md IN PLACE (the
       {ITEM} stays blocked; it simply no longer heads the queue). Do NOT
       neutralize.

   • "Other" (custom directive): enact the operator's NOTES as faithfully as you
     can with Edit/Write/Read/Bash and (if a skill fits) the Skill tool. If the
     directive resolves the blocker, neutralize BLOCKED.md; if it only changes
     course, follow the note's intent and say so in your summary.

   NEUTRALIZING BLOCKED.md (for every path EXCEPT "Defer"): {STATE_SCRIPT} keys the
   `blocked` halt on the FILENAME `BLOCKED.md` (NOT a frontmatter field), so a
   `kind:` edit does NOT clear the halt. Run:
     python3 ~/.claude/scripts/{STATE_SCRIPT} --neutralize-sentinel {spec_path}/BLOCKED.md
   The script performs the canonical rename to BLOCKED_RESOLVED_<YYYY-MM-DD>.md
   (git-mv-aware, collision-safe — it appends a numeric suffix if the target
   name already exists), preserving the audit trail including the `## Resolution`.
   Manual fallback (only if the script is unavailable):
   `git mv {spec_path}/BLOCKED.md {spec_path}/BLOCKED_RESOLVED_<YYYY-MM-DD>.md`.
   NEVER just flip a frontmatter field (this is a real bug that was hit in
   practice — the rename is mandatory).

   Then commit per .claude/skill-config/commit-policy.md (or the standard
   pattern); message `docs({feature_id}): enact blocker resolution (<path>)`.
   {PUSH_RULE}
   WORK-BRANCH-ONLY: commit and push to the CURRENT branch only
   (`git rev-parse --abbrev-ref HEAD` at start); NEVER create a new branch,
   NEVER --force.

   Report a one-paragraph summary (≤ 8 lines): what you enacted (the new phase
   title / the queue move / the custom edits), whether BLOCKED.md was neutralized
   (and to what filename) or deliberately kept, files touched, and the commit hash.

   You may NOT spawn further subagents (no Agent). You MAY use the Skill tool for
   {ADD_PHASE}, and Edit/Write/Read/Bash for everything else.
   ```

   Dispatch (by-reference — NOT a hand-composed prompt): dispatch the `dispatch_prompt`
   returned by `{STATE_SCRIPT} --emit-dispatch apply-resolution` (the consuming skill's Step 1h
   wiring) **VERBATIM** as an `Agent` call, using the returned `dispatch_model`. Do NOT paste the
   reference prompt block above into an `Agent` call — a hand-composed prompt reaching the
   dispatch guard is DENIED and routes a hardening stage. The reference block above is the
   emitted prompt's contract, shown so you can verify the emitted text, not compose it:

   ```
   Agent({
     description: "{SKILL} blocked-resolve: {feature_name}",
     subagent_type: "general-purpose",
     model: <dispatch_model from the --emit-dispatch apply-resolution output>,
     prompt: <dispatch_prompt from the --emit-dispatch apply-resolution output — VERBATIM>
   })
   ```

7. **Record and continue the loop.**
   - Append to `cycle_log`: `{cycle+1, feature_name, "▶ blocked (resolved + enacted: <path>)", "<one-line subagent summary>"}`.
   - Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · blocked`, `**Result:**` = "<path> enacted — {first line of subagent summary}". No other prose.
   - Update `prev_cycle_signature = (feature_id, "__resolve_blocked__", sub_skill_args, current_step)` — the **4-tuple**. The synthetic sub_skill token distinguishes a blocked-resolution cycle from any real-skill cycle for the Step 1d loop-guard.
   - Increment `cycle`. Return to Step 1a. **DO NOT halt, DO NOT print the final batch report** (except the "Halt for manual fix" path at step 4). The next state-script call sees `BLOCKED.md` neutralized (Add-a-phase / Other) and routes the {ITEM} onward, or — for "Defer" — selects the next actionable {ITEM} now that the blocked one sits at the queue tail.

**Re-prompt note (Defer path).** If "Defer" is chosen and the blocked {ITEM} is the ONLY remaining actionable entry, the next probe returns `blocked` for it again and this handler re-prompts immediately — that is correct (there is nothing else to work). The operator breaks the cycle by choosing Add-a-phase, Other, or Halt. `max_cycles` bounds it regardless.

This eliminates the legacy zero-context blocked halt: sequencing-only blockers are auto-resolved under the completeness-first standing policy (logged + notified, never asked), and for genuine product forks the operator gets the full blocker context in chat and directs the pipeline (add a phase / defer / hand off) — the orchestrator enacts the choice and keeps going either way.

### Coupling note

Consumed (as Step 1h) by the batch orchestrators: `user/skills/lazy-batch/SKILL.md`,
`user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.
The single-dispatch wrappers route `blocked` through `_components/halt-resolution.md` (Step 2a).
When editing this component, run `grep -rl "blocked-resolution.md" ~/.claude/skills/` to confirm
the consumer set.
