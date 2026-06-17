---
name: harden-harness
description: USE WHEN a marked orchestrator run hits a misroute (validate-deny), a no-route condition (cycle_prompt_refused, marker/state divergence), an inject-hook error against a live marker, a process-friction ledger entry (torn cycle bracket or unexpected commits), or manually for harness friction observed outside enforcement. The harness-hardening stage: root-causes why the route broke, implements mechanical fixes autonomously under full gates, and surfaces contract/policy forks via NEEDS_INPUT.md.
argument-hint: [description of the observed friction or no-route condition]
---

# /harden-harness — Harness-Hardening Stage

## Identity

To the HARNESS what `/investigate` is to the target repo: the dispatched owner of "why did
the route break, and how do we make the harness better," replacing inline orchestrator
improvisation. The investigation skill confirms root cause for a target-repo bug; this skill
confirms root cause for a harness routing failure and implements the fix — both follow the
same discipline of hypothesis-ledger rigor, evidence citation, and honest terminal states.

The harness is `claude-config` (skills, scripts, hooks, templates). The hardening agent NEVER
touches the target repo's source code.

## Triggers

This skill fires in five situations (triggers 1–4 arrive via `--emit-dispatch hardening` dispatch from a marked run; trigger 5 is direct manual invocation):

1. **Validate-deny fired (misroute):** the `lazy-dispatch-guard.sh` PreToolUse hook denied an
   `Agent` dispatch because its prompt was not script-emitted this turn. Dispatched with the
   denied prompt summary, denial reason, probe JSON, and registry state.

2. **No-route:** the probe returned `cycle_prompt_refused`, an unknown or contradictory state,
   or there is marker/state divergence — the orchestrator cannot produce a valid route. Covers
   `cycle_prompt_refused` returns, missing marker when one is expected, and divergence between
   the marker's pipeline/cloud fields and the current run context.

3. **Inject-hook error against a live marker:** the `lazy-route-inject.sh` UserPromptSubmit
   hook errored while a run marker was present (a `HOOK_ERROR` breadcrumb was written to the
   state dir). A hook bug IS a harness bug and triggers this stage.

4. **Process-friction (a `kind: process-friction` deny-ledger entry):** `--cycle-end` detected
   a torn cycle bracket (a dispatched subagent ran `--run-end` / overwrote the run marker) or
   unexpected commits (HEAD advanced beyond the per-subskill budget), and appended a
   `kind: process-friction` entry to `lazy-deny-ledger.jsonl`. The probe withholds the forward
   route (`route_overridden_by: "pending-hardening-debt"`) exactly like a guard deny, and
   `build_hardening_emit_command` binds `trigger_kind=process-friction` with `friction_reason`
   and `friction_detail` context keys. **Fires even when the runaway's output was salvaged**
   (D2: signal, not noise — accepting the output and hardening the bypass are orthogonal).
   Root-cause class for this trigger: `missing-contract` + `hook-defect` (prevention gap and
   detection gap per Proven Finding #1 of `hardening-blind-to-process-friction`).

5. **Manual invocation:** `/harden-harness <description>` from any session, for harness
   friction observed outside enforcement (e.g., confusing skill prose, a missing dispatch
   class for a real scenario, a script edge case noticed during a non-marked run).

## Cadence

**Inline, unbounded per-run dispatch count. No dedup-by-signature cap** (locked decision 4).
Every misroute or no-route dispatches this stage inline — the operator explicitly overrode the
once-per-signature recommendation because each occurrence is signal, not noise.

**Self-recursion guard (depth hard-capped at 1):** the hardening dispatch is itself
registry-emitted and passes the validate-deny guard normally (depth-0). A denial OF a
hardening-class dispatch MUST NOT dispatch another hardening stage. The depth guard in
`lazy_guard.py` detects hardening-class registry entries and emits a halt reason (containing
"halt" and "PushNotification") instead of the recursive hardening recommendation. Unbounded
refers to per-run dispatch count; recursion depth stays at 1.

When the depth-1 case fires:
- Emit a T6 ⚠ warning to chat with the full depth-1 denial reason.
- Call `PushNotification` with a summary of the situation.
- Halt the run. Do not attempt to route further. The operator must investigate.

## The four-step job

### Step 1: Reconstruct the route

From the injected evidence (denied prompt, probe JSON, registry state at dispatch time) and
the run's recent transcript artifacts:

- Name the **exact divergence point**: which step in the orchestrator's procedure was
  attempted, what dispatch class was intended, what the hook denied (or what the probe
  refused), and where the orchestrator's actual path diverged from the scripted path.
- Quote the relevant evidence inline: the deny reason (verbatim from the guard), the probe
  JSON fields that matter, the registry entries present at the time.
- If the trigger is a no-route or inject-hook error, name the symptom precisely (the refused
  route field, the missing marker, the hook error breadcrumb content).

### Step 2: Root-cause against the harness

Classify the gap. "The orchestrator misbehaved" is NEVER a terminal diagnosis — the question
is always *what harness change makes that misbehavior impossible or self-announcing*.

Root-cause classes (pick the most specific that applies):

- **missing-emit-section:** a dispatch class or scenario exists in SKILL prose but has no
  `--emit-dispatch <class>` emit path; the orchestrator composed the prompt by hand because
  there was no scripted alternative.
- **unbound-token:** an `--emit-dispatch` call failed (or would fail) because a required
  `{token}` in the template has no binding in the supplied context.
- **ambiguous-prose:** the SKILL prose has two interpretations and the orchestrator took the
  wrong one (or the right one, but it led to an unregistered dispatch). Example: a step says
  "dispatch the subagent" without specifying `--emit-dispatch <class>`.
- **script-defect:** a defect in `lazy_core.py`, `lazy-state.py`, `bug-state.py`,
  `lazy_guard.py`, or a hook script produced an incorrect probe output, deny, or registration
  failure.
- **missing-contract:** a legitimately novel situation arose (a new state, a new pipeline
  step, a new dispatch pattern) that has no current emit path or contract. The harness was not
  designed for this case yet.
- **hook-defect:** a bug in `lazy-route-inject.sh` or `lazy-dispatch-guard.sh` produced an
  incorrect allow/deny/inject or an error breadcrumb on a run that should have proceeded.

State your classification and cite the evidence (file path + line or field, transcript
artifact, probe JSON field, or registry entry).

### Step 3: Act by decision class (tiered authority)

**Mechanical fixes** (template/token gaps, missing emit section, prose clarification, lint
fixes, test additions, doc lockstep repairs):

Implement autonomously. Full gates are mandatory before committing:

```
python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities
python ~/.claude/scripts/test_lazy_core.py   # full suite — NO baseline regeneration
python ~/.claude/scripts/lazy-state.py --test
python ~/.claude/scripts/bug-state.py --test
python ~/.claude/scripts/test_hooks.py
```

> **Dead-coverage guard (harness-hardening-retro-fixes Phase 5).** `test_lazy_core.py` above
> includes a self-checking guard (`test_no_orphaned_test_functions`) that FAILS if a round adds
> a zero-arg `def test_*` to `test_lazy_core.py` but forgets to register it in `_TESTS` — so a
> hardening round CANNOT land regression tests that never execute (the Round-24 dead-coverage
> class). If the guard names an orphan, append it to a `_TESTS` list before committing.

Plus:
- **Coupled-pair mirroring:** changes to `lazy-batch/SKILL.md` must be mirrored in
  `lazy-bug-batch/SKILL.md` (and vice versa), and `lazy-batch-cloud/SKILL.md` kept
  consistent — per the CLAUDE.md pairs table.
- **Sentinel-schema lockstep:** when touching sentinel schemas
  (`sentinel-frontmatter.md`), keep in lockstep with AlgoBooth's
  `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS`.

Commit under the `harden(<area>):` prefix (see §Commit discipline below). Commits stay
local — do NOT `git push`; the orchestrator/operator owns pushes for claude-config.

#### Over-fit detector (anti-overfit reflex — runs AFTER the mechanical fix lands)

The mechanical fix ALWAYS lands first (the run is never left broken / never blocked). Then,
BEFORE writing the Step 4 round, run the over-fit detector to decide whether to ALSO spin off
a generalized `/spec` or `/spec-bug` for the broader *class* this fix is a symptom of. The
instance is already fixed, so a spin-off is queued work — it never blocks the current run.

**Why this exists.** Two consecutive hardening rounds once patched the same
verification-regex class back-to-back (each added another literal phrase to a matcher); the
durable fix was structural. The over-fit detector stops that whack-a-mole: it notices when a
fix is fitting to *observed data* rather than to *structure*, and spins off the generalization.

**Over-fit smell signals (ANY ONE trips a spin-off):**

1. **Literal-phrase-to-matcher.** The fix adds a literal phrase/string to a matcher — a
   regex alternation, a header list, a keyword set, an allow-list. This is fitting to the
   observed instance, not to the structure that generates the class. (Canonical example: adding
   another `|seam\s+audit` alternative to `_VERIFICATION_SECTION_RE`.)
2. **Class recurred ≥2 in the hardening log.** The root-cause *class* (signature match against
   prior rounds in `hardening-log/YYYY-MM.md` — same root-cause class + same component/symbol)
   has now been hit at least twice. Grep the current and prior months' logs for the
   classification + the file/symbol touched before deciding.
3. **Agent self-flags the fix as narrow.** While implementing, you recognize "this will gap
   again on the next variant" — the fix handles this case but not the obvious near-neighbor
   cases the same structure will produce.
4. **Repeated deterministic dance (toolify candidate).** The friction is a repeated
   deterministic multi-step dance that meets the upstream framework's deterministic-only bar
   (deterministic AND repeated ≥2 runs AND token-heavy — see
   `docs/features/unified-pipeline-orchestrator/toolify-bar.md`). This is in-run
   dance-recurrence detection — do NOT shell `toolify-miner.py` mid-cycle (the offline miner
   *proposes*; harden-harness performs its own in-run detection and spins off the same
   `/spec-bug` the miner's promotion checklist step 7 describes).

**Recurrence threshold (resolved this cycle — SPEC Open Question 1).**
- A **phrase-match patch** (signal 1) spins off on the **FIRST occurrence** — a phrase-match
  fix is over-fit by construction, so it does not wait for a recurrence.
- A **non-phrase** recurrence (signals 2–4) needs **≥2** occurrences of the class before it
  spins off (one structural fix is not yet evidence of a pattern).

**Generalization bound ("most general within reason").** The spun-off spec targets the
**smallest class that subsumes the observed instance and its near neighbors** — NOT a
speculative rewrite. The problem statement MUST:
- cite the concrete instance(s) as evidence (the round number(s), the file/symbol, the
  literal phrase added);
- name the **class boundary** explicitly (what is in the class, what is deliberately out);
- propose no behavior beyond subsuming the cited instance + its near neighbors.
This keeps generalization honest and reviewable. When in doubt, draw the boundary tighter and
let a later round widen it.

**Spin-off action.** Compose the generalized problem statement (the *class*, not the
instance), then invoke the generalization skill via the `adhoc-enqueue` protocol,
**front-enqueued** so it is worked next:

- **Choice rule:** structural redesigns + new capabilities → **`/spec`**; defects /
  regressions + toolify-this-dance → **`/spec-bug`**.
- Use the `--type bug` front-enqueue path for the `/spec-bug` route (see
  `~/.claude/skills/_components/adhoc-enqueue.md` → routes to `bug-state.py --enqueue-adhoc`,
  seeding `docs/bugs/<id>/` + `ADHOC_BRIEF.md`). Use the default `--type feature` path for the
  `/spec` route. Do NOT re-implement enqueue logic — that path is upstream-owned and shipped.
- **Cross-reference both ways:** the spun-off doc names this hardening round + the instance as
  its origin; the Step 4 round names the spun-off item id.

**No double-blocking.** Because the instance is already fixed, the spin-off NEVER blocks the
current run — it is queued work, surfaced via the Step 4 round + a `PushNotification`. Do NOT
write `BLOCKED.md` for a spin-off.

**Self-recursion guard preserved.** A spin-off is a `/spec`/`/spec-bug` enqueue, NOT a
recursive hardening dispatch, so it does NOT trip the existing depth-1 hardening guard (see
§Cadence → "Self-recursion guard"). The depth guard only fires on a denied *hardening-class*
dispatch; an `adhoc-enqueue` of a spec/bug is a different class entirely.

**No over-fit smell → no spin-off.** A fix that changes *structure* (not a phrase) and whose
class has not recurred is the healthy case: land the mechanical fix, record `spinoff: none` in
the round + Return format, and continue. Do NOT manufacture a spurious spin-off.

**Contract / policy / design forks** (new pipeline steps, authority changes, gate semantics
changes, anything an operator would want to own):

Write `NEEDS_INPUT.md` into the relevant spec dir (usually
`docs/specs/turn-routing-enforcement/` or the spec whose contract is at issue), following the
canonical sentinel schema + rich-body convention from
`~/.claude/skills/_components/sentinel-frontmatter.md`:

```yaml
---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
decisions:
  - "<one-line description of the design fork>"
date: <YYYY-MM-DD>
---
```

With a full `## Decision Context` body per the rich-body convention. Never bake a
harness-design fork in silently — the NEEDS_INPUT.md is the triage signal that surfaces it to
the operator.

### Step 4: Deliverable — HARDENING.md round

Append a round to the CANONICAL log in the **claude-config repo** (NEVER under the target
repo's working tree — a dispatched agent's cwd is usually the TARGET repo, so a relative
path resolves into the wrong tree; this exact mistake produced a split-brain log on
2026-06-12). Resolve the claude-config root via the `~/.claude/scripts` symlink target
(`dirname` of `readlink -f ~/.claude/scripts` is `<claude-config>/user`), then append to:
`<claude-config>/docs/specs/turn-routing-enforcement/hardening-log/YYYY-MM.md`

One file per calendar month; rounds are APPENDED (never overwrite). Each round follows this
template (the harness's own hypothesis-ledger discipline):

```markdown
## Round <N> — <YYYY-MM-DD> — <trigger_kind>

**Item in flight:** <item_id>
**Divergence point:** <one-line naming the exact step and dispatch class>

**Root cause:** <classification> — <2-4 sentences citing evidence (file+line or field)>

**Action:**
<one of:>
  - Mechanical fix applied: <description>. Gates run: test_lazy_core.py N/N, test_hooks.py N/N, lint-skills.py OK, --test suites OK. Commit: <hash>.
  - NEEDS_INPUT.md written: <path>. Decisions: <decision titles>.

**Over-fit spin-off:** <one of:>
  - none — fix is structural / class has not recurred; no over-fit smell tripped.
  - harden(spinoff): <smell signal(s) that tripped — e.g. "literal-phrase-to-matcher (signal 1)"> → front-enqueued <`/spec`|`/spec-bug`> `<item_id>` for the class «<one-line class boundary>». Cited instance(s): <round#(s) / file:symbol / phrase>. PushNotification sent.

**Gates run:**
  test_lazy_core.py: <N/N>
  test_hooks.py: <N/N>
  lint-skills.py: OK | <issue count>
  lazy-state.py --test: OK | FAIL
  bug-state.py --test: OK | FAIL
```

When the over-fit detector trips, the round records BOTH the mechanical patch (the `**Action:**`
line) AND the spin-off (the `**Over-fit spin-off:**` line with the front-enqueued item id) — the
patch is never elided in favor of only the spin-off, nor vice-versa.

If the hardening log directory or the current month's file does not yet exist, create it.

## Commit discipline

All commits made by this skill use the prefix:

```
harden(<area>): <imperative description>
```

Where `<area>` names the harness component modified (e.g., `dispatch-template`,
`skill-prose`, `script`, `hook`, `test`, `docs`). Examples:

- `harden(dispatch-template): add {item_id} token to dispatch-investigation.md`
- `harden(skill-prose): clarify --emit-dispatch recovery trigger in lazy-batch Step 1e`
- `harden(script): guard emit_dispatch_prompt against empty context key`

The commit prefix is load-bearing for retro grading: the HARDENING.md log cites the hash.

## Prohibitions (HARD — never violates these, no exceptions)

1. **Never edits the target repo's source.** This agent works exclusively on `claude-config`
   (skills, scripts, hooks, templates, docs). Any path under the `repos/` symlinks or under
   the target repo's working tree is out of scope.

2. **Never weakens a gate** to make a denial pass. This means: never removing a gate, never
   softening a threshold, never bypassing a check, never commenting out a validation step to
   clear an error. If a gate is failing for a legitimate mechanical reason, fix the underlying
   defect — not the gate. The gates exist to ensure the harness is correct; weakening one to
   clear a denial makes the harness silently broken.

3. **Never edits the registry/marker** to retroactively legitimize a denied dispatch. The
   `lazy-prompt-registry.json` and `lazy-run-marker.json` are script-owned write surfaces —
   any other writer is an integrity finding. Editing the registry to launder a denied prompt is
   the integrity side-door this whole feature (`turn-routing-enforcement`) exists to close. If
   the registry entry is wrong, the script that wrote it is wrong — fix the script.

## Arguments

- `[description]` (optional): when invoked manually (`/harden-harness <description>`), the
  description is the observed friction. When dispatched via `--emit-dispatch hardening`, the
  evidence is injected into the prompt body and the arguments are not needed.

## Inputs to read (in order)

1. The dispatch prompt's injected evidence: denied prompt summary, denial reason, probe JSON,
   registry state, trigger kind, item ID, and working directory.
2. The run's recent transcript for context (orchestrator step headings, LAZY-ROUTE banners,
   any HOOK_ERROR breadcrumbs).
3. The relevant SKILL.md, dispatch template, or script file named by the root-cause
   classification.
4. `docs/specs/turn-routing-enforcement/hardening-log/YYYY-MM.md` (current month) — to
   understand prior rounds and not re-investigate the same root cause without new evidence.

## Outputs

1. A round APPENDED to `docs/specs/turn-routing-enforcement/hardening-log/YYYY-MM.md`.
2. Either:
   - A committed mechanical fix (under full gates, `harden(<area>):` prefix), OR
   - A `NEEDS_INPUT.md` written to the relevant spec dir.
   PLUS, when the over-fit detector trips: a front-enqueued `/spec`/`/spec-bug` for the
   generalized class (via `adhoc-enqueue`), recorded in the round's `**Over-fit spin-off:**`
   line and surfaced via `PushNotification`. The mechanical fix and the spin-off are both
   emitted — the spin-off never replaces the immediate fix.
3. Return summary to the dispatching orchestrator (see §Return format below).

## Return format (to the dispatching orchestrator)

Structured summary:

- `trigger_kind`: one of validate-deny | no-route | inject-hook-error | process-friction | manual
- `divergence_point`: one-line naming the step and dispatch class
- `root_cause_class`: one of missing-emit-section | unbound-token | ambiguous-prose | script-defect | missing-contract | hook-defect
- `action`: "mechanical-fix" (with commit hash) or "needs-input" (with path)
- `spinoff`: the over-fit spin-off, if any — `<item_id> (reason: <smell signal + one-line class>)`, or `none`. When non-`none`, the orchestrator fires a `PushNotification` ("spun off `<item_id>` — `<reason>`") and adds a D7 digest entry; the front-enqueued item is worked next.
- `gates_run`: summary of counts (test_lazy_core.py N/N, test_hooks.py N/N, etc.)
- `log_path`: path to the hardening-log round (e.g. docs/specs/turn-routing-enforcement/hardening-log/2026-06.md)
