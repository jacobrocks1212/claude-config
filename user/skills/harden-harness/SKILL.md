---
name: harden-harness
description: Harness-hardening stage: USE WHEN a marked orchestrator run hits a misroute, no-route condition, inject-hook error, or process-friction ledger entry — root-causes the broken route, fixes mechanically under full gates, and resolves design forks park-provisionally (selects the recommended option and IMPLEMENTS it, recording a ratification-pending NEEDS_INPUT_PROVISIONAL.md) — hard-parking only gate-weakening or structural forks.
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

**Confirm Claude Code platform behavior before relying on it — SELF-RESOLVE via `claude-code-guide`, then provisionally accept.**
When the root cause OR the proposed fix hinges on how the Claude Code PLATFORM itself behaves —
hook firing rules (which of `Stop` / `SubagentStop` / `PreToolUse` / … fires, and exactly when),
the subagent / tool lifecycle, the fields a hook receives on stdin, the `settings.json` hook
schema, or any SDK/runtime field — and that behavior is NOT authoritatively documented in this
repo, do NOT ship load-bearing logic on an UNCONFIRMED assumption. But an unconfirmed platform
assumption is a blocker to RESOLVE, **not** an automatic hard-park.

**The self-resolve-then-provisional-accept flow (operator-authorized 2026-07-19, replaces the
Round-81 blanket prohibition):** when the ONLY blocker to an otherwise-recommendable harden
decision is an unconfirmed platform / Claude-Code capability, the harden agent MUST attempt to
RESOLVE it by consulting the **`claude-code-guide`** agent ITSELF (`subagent_type: claude-code-guide`)
— *even during a marked lazy run*. This consultation is now SANCTIONED at the enforcement plane:
`lazy_guard.py` admits an unregistered `subagent_type == "claude-code-guide"` Agent dispatch under a
bound workstation marker (a read-only agent that cannot advance the pipeline — not a gate-weakening),
and `lazy-cycle-containment.sh` already allows a foreground Agent dispatch from a subagent. So the
old "the marked-run harden agent is prohibited from dispatching `claude-code-guide`" rule is RETIRED
— the agent self-checks. CITE the guide's finding in the Step-4 round (and the Step-2.5 bug spec).

Then decide by what the consultation returned:
- **Resolved → provisionally accept (the common case).** If the guide confirms the recommended
  option is NON-platform-dependent (e.g. a self-managed substitute that uses only documented
  fields), OR confirms the platform capability the option needs IS present, the blocker is cleared:
  proceed with the recommended option as a PROVISIONAL auto-accept per Step 3 (`--park-provisional`).
  Operator scope is "non-platform-dependent only" — once the check resolves the assumption, auto-accept.
- **Genuinely unresolvable → hard-park.** ONLY when the guide reports the behavior as UNDOCUMENTED /
  unconfirmable AND the recommended option cannot avoid depending on it does the decision still
  hard-park for the operator per Step 3. Prefer a design that does not depend on the undocumented
  behavior (a self-managed substitute) over one that does; a self-managed substitute is
  non-platform-dependent by construction and takes the provisional-accept path.

(Origin: harden Round 81 — the `SubagentStop` wedge-backstop leaned on the undocumented
`stop_hook_active`; the guide's caution against shipping load-bearing logic on an UNCONFIRMED field
is preserved. Round 109 replaced the Round-81 blanket hard-park + consultation-prohibition with this
self-resolve flow: consulting the guide is exactly how the field stops being unconfirmed —
`docs/bugs/harden-hard-parks-on-unconfirmed-platform-assumptions/`.)

State your classification and cite the evidence (file path + line or field, transcript
artifact, probe JSON field, or registry entry).

**Triage before dispatching a full round:**
- **A completion-gate refusal is self-diagnosing — do not launch a second discovery probe.**
  `verify_ledger`'s refusal payload (`lazy_core.py`) carries a `failing_detail` object naming the
  offending items directly for every failing check — `clean_tree` (the dirty-file list),
  `head_matches_origin` (shas + ahead/behind), `plan_complete` (the non-Complete plan filenames +
  statuses), `deliverables_done` (the first N unchecked row texts with line numbers). Root-cause
  from that field first; re-running `git status`/re-reading PHASES.md by hand to rediscover what
  the payload already names is the deviation this fixed (`completion-gate-refusal-opacity`).
- **A deny-ledger entry whose cause is already handled doesn't need a full round.** If the
  offending entry's root cause was already fixed by an earlier round THIS run (a redundant
  re-dispatch of the same cause), or warrants an explicit, recorded no-fix classification, retire
  it cheaply via `lazy-state.py --ack-deny <selector> --resolution "<audit note>"` instead of a
  full hardening round — it acks the target entry AND every other unacked entry sharing the same
  cause key in one pass (`ack_method: manual-ack-dedup`), so one oscillating cause never costs
  more than one unit of retirement effort (`meta-dispatch-not-by-reference-and-ack-overpriced`).
  This is not reachable from a cycle subagent (orchestrator-only); it still leaves an audited
  trail for `/lazy-batch-retro` to grade.

### Step 2.5: Bug-spec FIRST — investigate + audit trail before implementing (HARD, operator-directed 2026-07-11)

**Before ANY implementation in Step 3, author a bug investigation spec in claude-config.**
Operator directive (Jacob, 2026-07-11): "every /harden-harness invocation [must] /spec-bug a
bug spec (or /spec if scope warrants, but unlikely) in claude-config before implementation
begins. This ensures the fix is well investigated beforehand, and serves as an audit trail."

- **Where (choose the directory by SCOPE — land it where the pipeline can manage it):**
  - **Defect / regression / friction (the common case)** → `docs/bugs/<slug>/SPEC.md` in the
    claude-config repo (descriptive kebab slug; same investigation-spec contract as `/spec-bug`
    — see `docs/bugs/CLAUDE.md`). `docs/bugs/` is lazy-managed (drained by the bug pipeline).
  - **Genuine new feature / capability (rare — most harness friction is a defect)** → author it
    under **`docs/features/<slug>/`** (the lazy-managed home) via `/spec`, **AND enqueue it**:
    add a `queue.json` entry **and** a `ROADMAP.md` row so `/lazy-batch` can drive it. A
    feature-scope deliverable that is not both in `docs/features/` AND enqueued is invisible to
    the pipeline.
  - **NEVER land a feature-scope deliverable under `docs/specs/`.** That directory is the
    historical / manually-authored spec ARCHIVE and is explicitly NOT under pipeline management
    (per `docs/features/ROADMAP.md`; `depdag.py` resolves a queue `spec_dir` only under
    `docs/features/`). A spec left in `docs/specs/` cannot be driven and must be relocated +
    enqueued by hand later (observed 2026-07-17: the `spike-pipeline-role` feature spec landed
    in `docs/specs/` and had to be manually `git mv`'d to `docs/features/` + given a queue.json
    tier-1 entry + ROADMAP row before `/lazy-batch` could pick it up — commit `be8acba4`).
  - **The ONE sanctioned `docs/specs/` use for this skill** is the harness's own
    manually-maintained contract/audit area under `docs/specs/turn-routing-enforcement/` — the
    Step-4 hardening-log and the Step-3 design-fork `NEEDS_INPUT(_PROVISIONAL).md` sentinels.
    Those are NOT pipeline-driven deliverables and correctly stay there.
- **Contents:** the reconstructed route (Step 1) + the root-cause classification (Step 2) +
  the verified symptom + the proposed fix scope. `**Status:** Investigating` while root cause
  is unproven; `**Status:** Concluded` once proven and the fix scope is understood. This is
  the durable investigation record; the Step-4 HARDENING.md round CITES its slug.
- **How to produce it:** for a **defect**, in a dispatched/subagent harden invoke `/spec-bug`
  (batch) so the investigation is a real skill pass; when running inline with the investigation
  already done this session, author the equivalent `docs/bugs/<slug>/SPEC.md` directly (the
  artifact is the deliverable, not the interactive pass). For a **feature-scope** change, invoke
  `/spec` and enqueue (queue.json + ROADMAP.md), or — inline — author `docs/features/<slug>/`
  directly and add the queue.json + ROADMAP entries yourself. Commit the deliverable under
  `harden(docs):` BEFORE the fix commit, so the audit trail predates the change.
- **Proportionality:** even a trivial one-line fix gets a SHORT bug spec (verified symptom +
  root cause + fix scope in a few lines) — "every invocation" is literal, but the spec scales
  to the fix. A design-fork round still authors the bug spec (Status: Investigating /
  Concluded) documenting the fork; under the park-provisional default (Step 3) it ALSO
  implements the recommended option and records a provisional sentinel — only the
  gate-weakening / structural carve-outs remain pure operator-owned parks that ship nothing.
- **Then** proceed to Step 3 and implement the fix the concluded spec describes.

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
python ~/.claude/scripts/bug-state.py --repo-root . --fsck   # docs/bugs/ invariant check — surfaces unarchived-fixed / fixed-without-receipt / stale-queue-entry debt (read-only; runs for a cycle subagent)
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

Commit under the `harden(<area>):` prefix (see §Commit discipline below), then **`git push`** —
claude-config's remote is always kept in sync with local (see the Push rule in
`.claude/skill-config/commit-policy.md`); never leave a `harden(...)` commit unpushed.

#### Reconcile the round's own `docs/bugs/` spec (the `docs/bugs/CLAUDE.md` OUT-OF-PIPELINE contract — MANDATORY)

Your Step-2.5 bug spec lives in the **lazy-managed** `docs/bugs/<slug>/` tree — `bug-state.py`
auto-discovers it, so the bug pipeline WILL re-drive it. When this round's Step-3 fix FULLY
resolves that spec's scope, the fix has shipped OUT-OF-PIPELINE (a `harden(...)` commit, never the
bug pipeline's gated `__mark_fixed__` path), so `docs/bugs/CLAUDE.md` → "Fixing a bug
OUT-OF-PIPELINE" applies: you MUST do ONE of {finish the contract, explicit deferral} — **NEVER a
silent `**Status:** Concluded` exit with the fix already committed.** Leaving it at `Concluded`
is exactly the burned-cycle state this contract closes: the merged-head driver dispatches a full
`/plan-bug` that discovers the whole fix already landed (observed 2026-07-18 — THREE consecutive
cycles burned this way; the origin of this very step). Note `bug-state.py --fsck` does NOT catch a
`Concluded`-with-fix-shipped spec (its checks key on `**Status:** Fixed`) — the `--fsck` gate above
is the defence-in-depth complement, this step owns the `Concluded`-limbo state.

Choose by fix completeness, then by run mode:

- **Partial fix, or mid-pipeline** (the fix is incomplete, OR a `PHASES.md` already exists so the
  bug is progressing through the normal tail): **leave `**Status:**` UNTOUCHED** (explicit
  deferral). Record `reconcile: deferred (<reason>)` in the round + Return. Never archive a bug
  another writer / the pipeline tail owns.
- **Full fix, inline manual `/harden-harness`** (no cycle marker): reconcile DIRECTLY — write the
  hand `FIXED.md` receipt (`kind: fixed`, `provenance: backfilled-unverified`, citing the fix
  commit + green regression evidence), flip `**Status:** Concluded → Fixed`, then
  `python3 user/scripts/bug-state.py --repo-root . --archive-fixed docs/bugs/<slug>` and
  `python3 user/scripts/lazy-state.py --link-provenance --id <slug> --commits <fix-sha>`.
- **Full fix, DISPATCHED harden** (the common case — you are a **meta-cycle subagent**, the run's
  `lazy-cycle-active.json` carries `sub_skill: harden-harness`): `--archive-fixed` and
  `--link-provenance` are ORCHESTRATOR-ONLY and are REFUSED for you (`refuse_if_cycle_active` →
  exit 3). Do NOT try to bypass that (exempting those queue-mutating / `git mv` ops for a subagent
  is gate-weakening — Prohibition #2). Instead: write the hand `FIXED.md` receipt + flip
  `**Status:** → Fixed` (ordinary Write/Edit — NOT cycle-refused; satisfies `--archive-fixed`'s
  precondition), then hand the two orchestrator-only ops back via the Return `reconcile:` field
  (name the slug + fix sha + the exact `--archive-fixed` / `--link-provenance` commands). The
  orchestrator honors it at the harden-return seam (`/lazy-batch` + `/lazy-bug-batch` §1d.1 — it is
  authorized for those ops, the same ones it runs on the normal archive-on-fix path).
  - **If you cannot rely on the orchestrator honoring the handback** (a bootstrap run predating the
    §1d.1 honor step, or any doubt): hand the WHOLE reconciliation back — receipt included — and
    leave `**Status:** Concluded` UNTOUCHED, so no `unarchived-fixed` debt is stranded. State this
    explicitly in the round.

#### Over-fit detector (anti-overfit reflex — runs AFTER the mechanical fix lands)

The mechanical fix ALWAYS lands first (the run is never left broken / never blocked). Then,
BEFORE writing the Step 4 round, run the over-fit detector to decide whether to ALSO spin off
a generalized `/spec` or `/spec-bug` for the broader *class* this fix is a symptom of. The
instance is already fixed, so a spin-off is queued work — it never blocks the current run.

**Why this exists.** Two consecutive hardening rounds once patched the same
verification-regex class back-to-back (each added another literal phrase to a matcher); the
durable fix was structural. The over-fit detector stops that whack-a-mole: it notices when a
fix is fitting to *observed data* rather than to *structure*, and spins off the generalization.

**Mechanical delegation to the shared checker (`anti-overfit-design-gate`, SPEC D3 option A).**
The smell detection below is now backed by the repo-wide mechanical checker
`user/scripts/harness-gate.py` (single source — the same checker the pipeline's ship seam and the
planning-seam `_components/harness-change-gate.md` component consume). After the mechanical fix
lands, run it over the round's diff to make the smell detection mechanical instead of eyeballed:

```
python3 user/scripts/harness-gate.py --repo-root . --range origin/main..HEAD --json
```

CITE its output in the Step-4 round (the `overfit`/`gate_weakening` findings + `scope_hit`).
`/harden-harness`'s own protocol is UNCHANGED by the delegation: the mechanical fix ALWAYS lands
first, the run is NEVER blocked, and a tripped smell spins off the generalization exactly as
below — the gate adds RECORDING here, not blocking (blocking authority lives only at the completion
gate). A `gate_weakening: hit` in a hardening round still means STOP and fix the underlying defect
(Prohibition #2) rather than shipping the weakening; a `flag` still triggers the spin-off decision.
The signals below are the human-readable expansion of what the checker keys on structurally.

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

**Default disposition: park-provisional — select the recommended option and IMPLEMENT it.**
`/harden-harness` runs as if `--park --park-provisional` is always active: a design fork is NOT a
blocking halt that ships nothing. For every design choice you:

1. **Author the decision** as a `NEEDS_INPUT.md` in the relevant spec dir (usually
   `docs/specs/turn-routing-enforcement/` or the spec whose contract is at issue), following the
   canonical schema + rich-body convention from `~/.claude/skills/_components/sentinel-frontmatter.md`
   — with a full `## Decision Context` body, **recommendation-first options** (each decision carries a
   `**Recommendation:**` block), and a file-level `divergence:` grade (`isolated | contained |
   structural`, most-severe across decisions):

   ```yaml
   ---
   kind: needs-input
   feature_id: turn-routing-enforcement
   written_by: harden-harness
   divergence: isolated | contained | structural
   decisions:
     - "<one-line description of the design fork>"
   date: <YYYY-MM-DD>
   ---
   ```

2. **Select the recommended option and implement it** under full gates (the mechanical path above),
   committing + pushing under `harden(<area>):`. The run ships a real change, not a park.

3. **Provisionally accept the decision** so it is ratification-pending (never silently baked in):
   run `python3 ~/.claude/scripts/lazy-state.py --provisionalize-sentinel <path-to-NEEDS_INPUT.md>`.
   This appends a `## Resolution` block (`resolved_by: auto-provisional`, `decision_commit: <HEAD sha>`)
   and RENAMES the file to `NEEDS_INPUT_PROVISIONAL.md` (keeps `kind: needs-input`; the filename is the
   state carrier). That sentinel is the ratification signal: a later operator ratify/redirect pass (the
   `provisional-ratification` affordance) closes it, and a redirect authors a `corrective` phase scoped
   by `git diff <decision_commit>..HEAD`. Commit + push the provisionalized sentinel with (or right
   after) the implementing commit.

**The two carve-outs that STILL hard-park** (write a blocking `NEEDS_INPUT.md`, implement nothing):

- **Gate-weakening (ALWAYS — Prohibition #2).** A fork whose recommended option would remove/soften a
  gate, threshold, denial, or validation is NEVER implemented provisionally — it halts for explicit
  operator sign-off. Weakening a gate to clear a denial is prohibited, not a "design choice."
- **`structural` divergence, or a baseline the operator has never ratified (`stub_origin`).** When the
  options fork architecture, persistent data, or a user-visible workflow — so a wrong provisional pick
  is expensive to redirect — grade it `divergence: structural` and park it for the operator, exactly as
  `--park-provisional` itself fails a structural/stub-origin decision closed. Bias toward
  provisional-implement for anything genuinely `isolated`/`contained`; reserve the hard park for these.

**An unconfirmed platform / Claude-Code capability is NOT a third carve-out.** It is a blocker to
SELF-RESOLVE via the Step-2 `claude-code-guide` consultation first (retired Round-81 blanket). Once
the guide confirms the recommended option is non-platform-dependent OR the capability is present, the
platform blocker is cleared and the decision takes the normal disposition (provisional-implement
unless it independently hits gate-weakening or `structural`/`stub_origin`). Only a GENUINELY
unconfirmable platform dependency the recommended option cannot avoid still hard-parks. (A decision
the operator has EXPLICITLY authorized to ship provisionally overrides the `structural` carve-out for
that instance — record the operator authorization in the `## Resolution` and the Step-4 round.)

Never bake a harness-design fork in silently — the provisional sentinel (or, for the two carve-outs,
the blocking `NEEDS_INPUT.md`) is the triage signal that surfaces it to the operator.

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
  - Mechanical fix applied: <description>. Gates run: test_lazy_core.py N/N, test_hooks.py N/N, lint-skills.py OK, lazy-state.py/bug-state.py --test suites OK. Commit + push: <hash>.
  - Provisional design-fork resolved: implemented recommended option for <decision titles>. Gates run: <as above>. Commit + push: <hash>. Provisional sentinel: <path to NEEDS_INPUT_PROVISIONAL.md> (decision_commit: <sha>).
  - NEEDS_INPUT.md written (hard-park carve-out — gate-weakening / structural, nothing implemented): <path>. Decisions: <decision titles>.

**Over-fit spin-off:** <one of:>
  - none — fix is structural / class has not recurred; no over-fit smell tripped.
  - harden(spinoff): <smell signal(s) that tripped — e.g. "literal-phrase-to-matcher (signal 1)"> → front-enqueued <`/spec`|`/spec-bug`> `<item_id>` for the class «<one-line class boundary>». Cited instance(s): <round#(s) / file:symbol / phrase>. PushNotification sent.

**Reconciliation:** <one of:>
  - none — this round shipped no `docs/bugs/` fix (pure hard-park, or the fix was not a bug spec).
  - done — inline manual reconciliation completed (receipt + `--archive-fixed` + `--link-provenance`).
  - deferred (<reason>) — partial fix / mid-pipeline; `**Status:**` left untouched.
  - handback → orchestrator: <slug(s)> — receipt written + Status flipped; `--archive-fixed` + `--link-provenance --commits <sha>` handed back via the Return `reconcile:` field.

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

### Intervention record for the round (intervention-efficacy-tracking, additive)

After appending a round that SHIPPED a change (the `Mechanical fix applied:` OR the
`Provisional design-fork resolved:` action form — a pure hard-park `NEEDS_INPUT.md` round records
no intervention; nothing shipped), ALSO capture the round as a hypothesis-ledger intervention
record so its efficacy is measured instead of assumed. This is
ADDITIVE to the HARDENING.md round above — it replaces nothing. From the claude-config root:

```bash
python3 ~/.claude/scripts/lazy-state.py --record-intervention   --id harden-<YYYY-MM>-r<N>   --pipeline hardening   --target-signal event:<ledger-event-type>   --expected-direction decrease   --signal-independence "<independent|self-emitted|mixed — one-line justification>"   --repo-root <claude-config-root>
```

The capture contract is **MECHANICALLY ENFORCED** on this CLI path (no longer prose-only
discipline — `hardening-intervention-records-unmeasurable-or-missing`). Three enforcement seams:

- **Vocabulary reject (exit 1).** `--target-signal event:<type>` is validated against the closed
  ledger-event vocabulary (`lazy_core._INTERVENTION_EVENT_VOCABULARY`, the D4-B SSOT): `run-start`,
  `run-end`, `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`, `sentinel-resolved`,
  `sentinel-provisionalized`, `gate-refusal`, `containment-refusal`. An unknown type is REJECTED at
  the CLI (exit 1, naming the valid set) — never silently accepted. (This is exactly what caught
  the old phantom `event:no-route` / `event:route-loop` records; a `no-route`/`route-loop` is a
  hardening *trigger kind*, not an emitted event.) A `kpi:<system>.<kpi-id>` target passes through.
- **Undeclared hardening refused (exit 1).** OMITTING `--target-signal` on `--pipeline hardening`
  now HARD-FAILS with exit 1 + the sibling-D2 guidance — you must declare the friction's own
  recurrence signal. For the genuinely-immeasurable diagnostic, pass an EXPLICIT
  `--target-signal undeclared` (typed, retro-visible, `baseline: not-computable`,
  INCONCLUSIVE-by-construction — surfaced for triage, never blocked). For a validate-deny /
  containment-trip round the measurable signal is usually `event:containment-refusal` or
  `event:gate-refusal`; a NEEDS_INPUT/no-friction halt round maps to `event:halt`.
- **Round↔record coverage lint.** `doc-drift-lint.py`'s `intervention-coverage` check parses the
  current month's `hardening-log/<YYYY-MM>.md`: every `Mechanical fix applied:` round must have a
  matching `docs/interventions/harden-<YYYY-MM>-r<N>.md` OR an explicit `**Intervention record:**
  none` exemption line — a missing record for a mechanical-fix round is FLAGGED. It runs standalone
  and at the `/lazy-batch(-cloud)` `--run-end` flush (fail-open there — a lint miss warns, never
  blocks `--run-end`). One undisciplined round no longer silently breaks coverage.

- `<YYYY-MM>-r<N>` matches the round you just appended (one record per round).
- The script freezes the baseline window from the telemetry ledger at capture and writes
  `docs/interventions/harden-<YYYY-MM>-r<N>.md` (`pipeline: hardening`); commit it with the
  round (same `harden(<area>):` commit). Idempotent — re-running never clobbers.
- NON-BLOCKING at completion: on the fail-open completion-gate path an unknown `event:` target
  degrades to `undeclared` with a loud diagnostic (never a frozen bogus zero) and a capture failure
  is a one-line warning; the round itself stands. The CLI path above is the STRICT path (exit 1 on
  reject/undeclared) — a hardening author is interactive and corrects immediately. Verdicts arrive
  later via `efficacy-eval.py` at the batch orchestrators' end-of-run flush.

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
2. One of:
   - A committed + pushed mechanical fix (under full gates, `harden(<area>):` prefix), OR
   - A committed + pushed provisional design-fork resolution (recommended option implemented under
     gates) PLUS a `NEEDS_INPUT_PROVISIONAL.md` (ratification-pending), OR
   - For a gate-weakening / structural carve-out only: a blocking `NEEDS_INPUT.md` written to the
     relevant spec dir (nothing implemented).
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
- `action`: "mechanical-fix" (with commit hash), "provisional-resolve" (with commit hash + NEEDS_INPUT_PROVISIONAL.md path + decision_commit), or "needs-input" (gate-weakening / structural hard-park carve-out, with path)
- `spinoff`: the over-fit spin-off, if any — `<item_id> (reason: <smell signal + one-line class>)`, or `none`. When non-`none`, the orchestrator fires a `PushNotification` ("spun off `<item_id>` — `<reason>`") and adds a D7 digest entry; the front-enqueued item is worked next.
- `reconcile`: the `docs/bugs/CLAUDE.md` OUT-OF-PIPELINE handback for the round's own bug spec — one of: `done` (inline manual: receipt + `--archive-fixed` + `--link-provenance` already run); `deferred (<reason>)` (partial / mid-pipeline: Status left untouched); `none` (this round shipped no docs/bugs fix — e.g. a pure hard-park); or an **orchestrator handback** naming the slug + fix sha + the exact `--archive-fixed` / `--link-provenance` commands to run at the harden-return seam (`/lazy-batch` + `/lazy-bug-batch` §1d.1). When a handback is present, the orchestrator runs those script-owned ops (it is authorized — same as the normal archive-on-fix path), then commits + pushes.
- `gates_run`: summary of counts (test_lazy_core.py N/N, test_hooks.py N/N, etc.)
- `log_path`: path to the hardening-log round (e.g. docs/specs/turn-routing-enforcement/hardening-log/2026-06.md)
