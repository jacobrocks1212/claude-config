---
name: harden-harness
description: USE WHEN a marked orchestrator run hits a misroute (validate-deny), a no-route condition (cycle_prompt_refused, marker/state divergence), an inject-hook error against a live marker, or manually for harness friction observed outside enforcement. The harness-hardening stage: root-causes why the route broke, implements mechanical fixes autonomously under full gates, and surfaces contract/policy forks via NEEDS_INPUT.md.
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

This skill fires in four situations (triggers 1–3 arrive via `--emit-dispatch hardening` dispatch from a marked run; trigger 4 is direct manual invocation):

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

4. **Manual invocation:** `/harden-harness <description>` from any session, for harness
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

Plus:
- **Coupled-pair mirroring:** changes to `lazy-batch/SKILL.md` must be mirrored in
  `lazy-bug-batch/SKILL.md` (and vice versa), and `lazy-batch-cloud/SKILL.md` kept
  consistent — per the CLAUDE.md pairs table.
- **Sentinel-schema lockstep:** when touching sentinel schemas
  (`sentinel-frontmatter.md`), keep in lockstep with AlgoBooth's
  `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS`.

Commit under the `harden(<area>):` prefix (see §Commit discipline below). Commits stay
local — do NOT `git push`; the orchestrator/operator owns pushes for claude-config.

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

**Gates run:**
  test_lazy_core.py: <N/N>
  test_hooks.py: <N/N>
  lint-skills.py: OK | <issue count>
  lazy-state.py --test: OK | FAIL
  bug-state.py --test: OK | FAIL
```

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
3. Return summary to the dispatching orchestrator (see §Return format below).

## Return format (to the dispatching orchestrator)

Structured summary:

- `trigger_kind`: one of validate-deny | no-route | inject-hook-error | manual
- `divergence_point`: one-line naming the step and dispatch class
- `root_cause_class`: one of missing-emit-section | unbound-token | ambiguous-prose | script-defect | missing-contract | hook-defect
- `action`: "mechanical-fix" (with commit hash) or "needs-input" (with path)
- `gates_run`: summary of counts (test_lazy_core.py N/N, test_hooks.py N/N, etc.)
- `log_path`: path to the hardening-log round (e.g. docs/specs/turn-routing-enforcement/hardening-log/2026-06.md)
