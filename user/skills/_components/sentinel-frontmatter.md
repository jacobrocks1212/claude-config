## Sentinel File Frontmatter Schema

All sentinel files the `/lazy` and `/lazy-cloud` state machine reads or writes carry a YAML frontmatter block as their canonical contract. The markdown body that follows the frontmatter remains human-readable documentation; **only the frontmatter is parsed by consumers**. Tools (`lazy-state.py`, future lints, batch orchestrators) read the frontmatter strictly and ignore the body.

### Parsing protocol

1. Read the file as UTF-8.
2. First non-blank line MUST be exactly `---`. Otherwise the file is not a structured sentinel — treat as legacy/freeform and skip.
3. Read lines until the next line that is exactly `---` (the closing fence). Everything between the fences is YAML.
4. Parse the YAML with a standard library parser (e.g. `yaml.safe_load`). If parsing fails, surface the file path and the parser's line/column rather than silently treating the file as missing.
5. Anything after the closing `---` is the markdown body. Consumers SHOULD NOT parse the body. Producers SHOULD keep the body informative for humans reading the file directly.

The shared sentinel writer in lazy-state.py — and the skill prose that writes these files inline — both follow this contract. If you read sentinel files ad-hoc from skill prose, prefer dispatching to `python3 ~/.claude/scripts/lazy-state.py` instead of re-implementing the parse.

### Required `kind` field

Every sentinel MUST carry a `kind` field whose value identifies the sentinel type. Consumers dispatch on `kind`. Unknown kinds are treated as parse errors.

### Schemas

#### `BLOCKED.md` — `kind: blocked`

Required:

```yaml
---
kind: blocked
feature_id: <id>
phase: <human description of the phase or step that hit the blocker>
blocked_at: <ISO 8601 timestamp>
retry_count: <int>
---
```

Optional:
- `blocker_kind: <one-line classifier>` — e.g., `mcp-validation`, `upstream-realign`, `quality-gate`, `cloud-limitation`, `execute-plan`.
- `recovery_suggestion: <one-line>` — short hint surfaced in the dispatch summary.

The markdown body that follows MUST keep the existing `## Details` / `## What was tried` / `## Recovery Suggestion` sections so a human reading the file directly still sees the full context. Frontmatter values may duplicate the body content; that's fine — frontmatter is the parser's source of truth, body is the human's.

#### `DEFERRED_NON_CLOUD.md` — `kind: deferred-non-cloud`

Required:

```yaml
---
kind: deferred-non-cloud
feature_id: <id>
deferred_step: <step number, e.g. 8>
reason: <one-line>
deferred_by: lazy-cloud
date: <YYYY-MM-DD>
---
```

Optional:
- `cloud_session_id: <id-or-n/a>`
- `testability_assessment: <"clearly-testable" | "ambiguous">`

Body keeps the existing detailed `## State at deferral` / `## How to resume` sections.

#### `DEFERRED_REQUIRES_DEVICE.md` — `kind: deferred-requires-device`  *(new — real-device deferral)*

Records that specific MCP audio assertions **ran (or were attempted) but can only
be CERTIFIED on a host with a real audio output device** — they are deferred to a
real-device `/lazy` host, NOT skipped. Written by `/mcp-test` (Step 4.5) on a
no-real-device host (e.g. WSL2/CI, where AlgoBooth's `classify_audio_backend`
selects the `HeadlessPumpDriver` — a normal OS-scheduled thread whose preemption
makes sustained-timing metrics like zero-dropout non-deterministic). On a
real-device host the cpal device callback drives the audio clock from the
hardware interrupt and these same assertions are trustworthy.

This is the device-axis sibling of `DEFERRED_NON_CLOUD.md` and is **distinct from
both** of its neighbors:

| Sentinel | Means | Resolution |
|----------|-------|------------|
| `SKIP_MCP_TEST.md` | Permanent waiver — un-testable on *any* host (e.g. raw-PCM injection). | Never re-opened. |
| `DEFERRED_NON_CLOUD.md` | Cloud can't run the step *at all* (no Tauri/MCP). | Workstation `/lazy` runs it. |
| `DEFERRED_REQUIRES_DEVICE.md` | Assertion is WSL2-untestable but **real-device-testable** — deferred on the device axis. | A real-device `/lazy` host re-opens it (`lazy-state.py` Step 9) and certifies the deferred scenarios. |

`lazy-state.py` keys on this file: a no-real-device host with `RETRO_DONE.md` +
this sentinel + no `VALIDATED.md` is **device-saturated** — Step 2 skips it so the
queue advances (terminal `device-queue-exhausted`), exactly mirroring the
cloud-saturated skip. The feature does NOT reach `Complete` on a no-device host
(no receipt is written): completion stays blocked until a real-device run clears
the deferral, so `Complete` always means fully validated.

Required:

```yaml
---
kind: deferred-requires-device
feature_id: <id>
deferred_scenarios: [<scenario-id>, ...]   # WHICH assertions are deferred — a real-device run re-opens exactly these
reason: <one-line — the real-device-specific cause, e.g. headless-pump preemption>
deferred_by: lazy   # one of: lazy | lazy-batch
date: <YYYY-MM-DD>
---
```

`deferred_scenarios` is **load-bearing and MUST be non-empty** — it is the
self-limiting scope a real-device run re-opens. A blanket whole-feature deferral
with no scenario IDs is malformed: every *other* scenario must have actually
passed via MCP on this host.

Optional:
- `proxy_validation: <one-line>` — the proxy that DOES cover the deferred metric here (e.g. `npm run qg:realtime` K=4 smoke + NIGHTLY 60s).
- `backend_observed: <"headless" | "cpal">` — the `get_audio_mode` backend at deferral (normally `headless`; pairs with the control-run evidence).

Body keeps a `## What was deferred and why` section: the control-run evidence
(the artifact reproduces with zero feature activity), the `get_audio_mode`
reading, and the re-enable path (*"re-run on a real-device MCP host to certify
these for real"*).

#### `VALIDATED.md` — `kind: validated`

Required:

```yaml
---
kind: validated
feature_id: <id>
date: <YYYY-MM-DD>
mcp_scenarios: [<scenario-name>, ...]
result: all-passing
---
```

Optional:
- `validated_commit: <git-sha>` — HEAD sha at the time the MCP validation run
  completed. The same sha-freshness anchor `MCP_TEST_RESULTS.md` carries; the
  `/mcp-test` orchestrator override mandates capturing it so the certification is
  matched to the exact code it ran against. Optional for back-compat with
  pre-anchor `VALIDATED.md` files.

Body keeps the human-readable summary of which scenarios ran.

#### `INVESTIGATION.md` — `kind: investigation`

The durable evidence artifact written by the `/investigate` skill (on-demand
root-cause investigation cycle). A **permanent audit artifact**
(MCP_TEST_RESULTS-class) — explicitly NOT a halt sentinel: the state scripts do
not key any routing or halt on it; it is consumed by `blocked-resolution`,
`/add-phase`, and `/write-plan` as the evidence-backed root-cause record that
replaces orchestrator-authored causal narratives.

Required:

```yaml
---
kind: investigation
feature_id: <id>
date: <YYYY-MM-DD>
trigger: validation-escalation   # one of: validation-escalation | failed-fix-live-check | orchestrator-budget | manual
status: root-cause-confirmed     # one of: root-cause-confirmed | partially-localized | inconclusive
investigated_commit: <git rev-parse HEAD when the investigation ran>
---
```

`investigated_commit` is the **freshness anchor** (mirrors `validated_commit`):
a consumer treats the artifact as current when it equals HEAD or the only
commits since are the investigation's own `diag(<feature_id>):`-prefixed
instrumentation commits; otherwise consumers cite it only as
`(stale — re-verify)`.

The body is LOAD-BEARING for human + downstream-skill consumption (the
`/investigate` skill owns the authoring rules): `## Symptom`, `## Seam Table`
(per-seam `probed-OK | probed-FAIL | unprobed` with one line of evidence),
`## Hypothesis Ledger` (every hypothesis **confirmed**/**refuted**/**unproven**
with a cited evidence artifact — no citation, no verdict), `## Repro Recipe`,
`## Recommended Fix Scope`. Repeat investigations APPEND `## Investigation N
(date, commit)` rounds to the same file — one artifact per feature/bug dir, not
one per round. Keep in lockstep with AlgoBooth
`scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS`.

#### `RETRO_DONE.md` — `kind: retro-done`

Required:

```yaml
---
kind: retro-done
feature_id: <id>
date: <YYYY-MM-DD>
rounds: <int>
retro_plans: [<filename>, ...]
mcp_validation_status: complete  # one of: complete | deferred-to-workstation
phase_count_at_retro: <int>      # optional but REQUIRED going forward — see below
---
```

`phase_count_at_retro` records the number of phase sections in the feature's
PHASES.md at the moment the retro concluded. Compute it with
`lazy-state.py --count-phases <PHASES.md>` (the canonical `parse_phases()`
counter) — **never** an ad-hoc `grep -c '^### Phase'`, which counts a different
set than the staleness comparator and silently false-positives on non-phase
headings like `## Phase Summary` (the d8-session-format permanent-stale loop,
hardening-log 2026-06). It is the **retro staleness anchor**: when later
corrective `/add-phase` rounds grow PHASES.md past this count, `lazy-state.py`
Step 8 routes another retro round (and the `__mark_complete__` gate refuses
completion) instead of letting a retro that
graded the pre-corrective code stand for phases it never saw — d8-live-looping
carried a RETRO_DONE.md written BEFORE three corrective validation rounds, so
retro had effectively graded a 0/16-functional feature. Legacy files without
the field are grandfathered (no staleness check). Keep in lockstep with
AlgoBooth's `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS`.

Body keeps the per-round summary so humans can scan retro history.

#### `COMPLETED.md` — `kind: completed`  *(new — completion receipt)*

The **durable proof** that a feature reached `Complete` THROUGH the pipeline's
completion-integrity gate (`__mark_complete__`), rather than via an out-of-band
SPEC/ROADMAP edit. `lazy-state.py` Step 2 treats a feature as genuinely done
ONLY when it claims completion (SPEC `**Status:** Complete` or the ROADMAP
strikethrough+COMPLETE fallback) **AND** this receipt is present. A `Complete`
claim WITHOUT a receipt is a `completion-unverified` hard-halt (it was flipped
outside the gate). `Superseded` features are exempt — a retired feature was
never validated and needs no receipt.

Unlike `VALIDATED.md` / `RETRO_DONE.md` (which `__mark_complete__` clears),
`COMPLETED.md` is **permanent** — it is the audit trail. The completion gate
FOLDS the validation evidence into the receipt body before deleting those
sentinels, so nothing is lost.

Required:

```yaml
---
kind: completed
feature_id: <id>
date: <YYYY-MM-DD>
provenance: gated  # one of: gated | backfilled-unverified
---
```

Optional (written by the gate at flip time; absent on backfill):
- `completed_commit: <sha>` — the commit that performed the Complete flip.
- `validated_via: <"mcp" | "skip-mcp-test" | "deferred-non-cloud">` — how the MCP gate was satisfied.
- `mcp_pass_count: <int>` / `mcp_total_count: <int>` — folded from `MCP_TEST_RESULTS.md` / `VALIDATED.md`.

`provenance: gated` is written by the completion-integrity gate after all
preconditions pass (phase coherence + validation sentinel present + MCP-coverage
audit clean). `provenance: backfilled-unverified` is written by
`lazy-state.py --backfill-receipts` to grandfather features completed before the
gate existed — it truthfully marks them as never gate-verified. Body keeps a
human-readable completion summary (folded validation evidence, or the
backfill grandfather note).

#### `SKIP_MCP_TEST.md` — `kind: skip-mcp-test`

Required:

```yaml
---
kind: skip-mcp-test
feature_id: <id>
reason: <one-line>
alternative_validation: <one-line>
date: <YYYY-MM-DD>
---
```

Optional:
- `skipped_by: <"lazy" | "lazy-cloud" | "operator" | "pipeline">` — who wrote the skip.
- `granted_by: <"operator" | "mcp-test" | "pipeline">` — **provenance of the waiver decision**. The gate is `lazy_core.skip_waiver_refusal()` (single source of truth — consulted by both state scripts' Step 9 and by `__write_validated_from_skip__`):
  - `operator` — a human reviewed the feature and approved the MCP skip. Accepted as a legitimate vacuous-pass → `__write_validated_from_skip__`.
  - `mcp-test` — an `/mcp-test` validation cycle verified structural untestability against `docs/features/mcp-testing/SPEC.md`. Accepted **ONLY when `spec_class` (below) is also present and non-empty** — the citation is what distinguishes a verified assessment from a convenience skip. Missing `spec_class` → refused (`needs-input`).
  - `pipeline` (or any unrecognized value) — a non-validation pipeline step self-granted the skip. **Refused**: a pipeline-self-granted skip cannot vacuously validate its own MCP requirement. Routes to `terminal_reason="needs-input"`; update `granted_by` to `operator` (after human review) to unblock.
  - Absent — legacy files are treated as `operator` for backward compatibility **UNLESS `skipped_by` identifies a pipeline author (`lazy` / `lazy-cloud` / `pipeline`)**, in which case the skip is refused: a pipeline-written skip that simply omits `granted_by` is the omission side-door this rule closes (observed 2026-06-10 — an mcp-test cycle omitted the field and its skip auto-validated unconfirmed). NEW pipeline-written skips MUST always carry an explicit `granted_by`.
- `spec_class: <one-line>` — the untestable class from `docs/features/mcp-testing/SPEC.md` that an `mcp-test` grant verified (e.g. `raw-PCM injection into the Rust callback thread`, or an observation-gap row, or `standalone crate — no app integration`). REQUIRED when `granted_by: mcp-test`; meaningless otherwise.

#### `MCP_TEST_RESULTS.md` — `kind: mcp-test-results`

Required:

```yaml
---
kind: mcp-test-results
feature_id: <id>
date: <YYYY-MM-DD>
scenarios: [<scenario-name>, ...]
result: all-passing  # one of: all-passing | partial
pass_count: <int>
total_count: <int>
validated_commit: <git-sha>  # HEAD sha at the time the MCP run completed; consumed by lazy-state Step-9 freshness gate
---
```

Body keeps the per-scenario pass/fail breakdown.

`validated_commit` is **required going forward** for every new `MCP_TEST_RESULTS.md`: producers (`/mcp-test`, and the inline `/mcp-test` cycle override in `lazy-batch-prompts/cycle-base-prompt.md`) MUST capture `git rev-parse HEAD` when the MCP run completes and write it here. The state scripts' Step-9 sha-freshness gate compares it to the current HEAD; legacy files without the field skip the check (lenient for backward compatibility), but a new results file written without it leaves the freshness gate inert for that feature.

#### `NEEDS_RESEARCH.md` — `kind: needs-research`  *(new)*

Written by `/lazy-batch` or `/lazy-batch-cloud` when a feature is missing `RESEARCH.md` and the orchestrator has just ensured a `RESEARCH_PROMPT.md` exists. Halts the autonomous tail and surfaces the prompt path so a human can run Gemini and drop the results in place.

Required:

```yaml
---
kind: needs-research
feature_id: <id>
research_prompt_path: <relative path to RESEARCH_PROMPT.md>
written_by: lazy-batch  # one of: lazy-batch | lazy-batch-cloud
date: <YYYY-MM-DD>
---
```

Body should explain how to resume: run Gemini deep research against the prompt file, drop the output as `RESEARCH.md` next to the prompt, then re-run `/lazy-batch` (or `/lazy-batch-cloud`).

#### `NEEDS_INPUT.md` — `kind: needs-input`  *(new)*

Written by any batch-mode skill (`--batch`) when a decision is genuinely ambiguous and no recommended option resolves cleanly. Halts the autonomous tail and surfaces the decisions a human must make.

Required:

```yaml
---
kind: needs-input
feature_id: <id>
written_by: <skill name>  # e.g., spec, spec-phases, add-phase, retro, execute-plan
decisions:
  - <one-line decision description>
  - <one-line decision description>
date: <YYYY-MM-DD>
---
```

Optional:
- `next_skill: <skill name>` — what to re-run after the human resolves the decision (defaults to the writer).
- `partial_artifacts: [<path>, ...]` — paths to any half-finished artifacts the human should review or discard.
- `class: mechanical | scope | product` — decision classification. **`scope`** means EVERY decision in this file differs only in effort / sizing / sequencing / completeness — all options converge on the same end-state product behavior — and is auto-resolved to the MOST COMPLETE option in BOTH modes (default and `--park`) per `~/.claude/skills/_components/completeness-policy.md` (D7), never asked. (Under D7, cycle subagents shouldn't write scope-class sentinels at all — apply the policy in-cycle and disclose; this value mainly serves the orchestrator's reclassification of scope-shaped files.) **`mechanical`** is **Key 1 of the D2 two-key auto-accept (`--park` mode only).** Authored by the cycle subagent that wrote this sentinel (or by the input-audit at Step 1d.5). FILE-LEVEL classification: `mechanical` means EVERY decision in this file is mechanical-internal with a single defensible recommended option; `product` means at least one decision requires human judgment on product behavior. If ANY decision touches user-visible behavior (in the divergent-end-state sense — not mere effort/sequencing), workflow, defaults, copy, or UX — the whole file is `product`. **Absent ⇒ treated as `product` (the conservative default).** The `mechanical` value is a `--park`-mode auto-accept signal ONLY — the non-park decision-resume path (Step 1g without `--park`) ignores it and asks the operator; `scope` is the exception: it is acted on in both modes (the D7 standing policy is itself the operator's authorization).
- `audit_concurs: true | false` — **Key 2 of the D2 two-key auto-accept (`--park` mode only).** Written by the Step 1d.5 input-audit subagent AFTER it independently re-classifies every decision in this file against the product-behavior smells checklist. `true` iff the audit concurs that ALL decisions are mechanical-internal and agrees with a `class: mechanical` self-classification. `false` (or absent) ⇒ treated as no-concurrence → the decision is parked and flushed to the operator via the normal WU-4 flush. Like `class`, this field is a `--park`-mode auto-accept signal ONLY — the non-park path ignores it.

**D2 two-key auto-accept rule (enforced in `parked-flush.md` — `--park` mode only):** A parked decision MAY be auto-accepted (recommended option taken, logged, sentinel resolved) ONLY when ALL three conditions hold simultaneously: (1) `class: mechanical` is set, (2) `audit_concurs: true` is set, AND (3) every decision in the file carries a `**Recommendation:**` block. A single-key classification (`class: mechanical` alone, without `audit_concurs: true`) is NOT sufficient — both keys must agree. On ANY disagreement, absence, or missing recommendation → the decision is treated as `product` → parked → flushed to the operator. **No decision is EVER two-key auto-accepted without `--park`** — this is a structural guarantee: the two-key auto-accept code path lives exclusively in `parked-flush.md` (a `--park`-only component) and cannot fire in the standard decision-resume path. (Scope-class decisions are the separate D7 case: resolved in BOTH modes by the completeness-first standing policy, whose authorization is the policy itself — see `completeness-policy.md`.) The two-key classifier is the controlled, park-mode-only relaxation that lets a both-keys-mechanical decision bypass the operator `AskUserQuestion` instead of being surfaced in the batched flush.

**`resolved_by` marker in `## Resolution` blocks:** When the auto-accept path resolves a decision, it appends a `## Resolution` block carrying `resolved_by: auto-two-key` so the sentinel is a self-describing audit trail. When the completeness-first standing policy (D7) resolves a scope-class decision (both modes — Step 1g or the parked-flush backstop), the block carries `resolved_by: completeness-policy`. Human-answered resolutions (from `AskUserQuestion` via the standard flush or decision-resume path) carry no `resolved_by` field (or may carry `resolved_by: operator` for clarity). Consumers that inspect resolution blocks can distinguish auto-accepted and policy-resolved decisions from operator-answered ones by this marker.

Body keeps the full decision context, options considered, and any chat-visible tradeoff notes the writer would have surfaced interactively.

##### Rich body convention (HARD REQUIREMENT)

Every `NEEDS_INPUT.md` MUST carry — under the closing `---` of the frontmatter — a `## Decision Context` section with one H3 subsection per item in `decisions:`. Each subsection follows this template:

```markdown
## Decision Context

### 1. <one-line decision title, matching decisions[0]>

**Problem:** <2-4 sentence framing of why this decision is needed and what's at stake. Cite the spec section, research finding, or constraint that surfaced it.>

**Options:**
- **<option A>** — <one-paragraph description of the option, including concrete tradeoffs (cost / complexity / risk / reversibility).>
- **<option B>** — <same shape.>
- **<option C>** — <same shape; optional, max 4 options.>

**Recommendation:** <option name> — <one-sentence justification.>

### 2. <next decision title, matching decisions[1]>

...
```

This body is the **source of truth** for what the orchestrator displays to the user. The orchestrator (`/lazy-batch` / `/lazy-batch-cloud`) re-prints the entire `## Decision Context` section verbatim to chat BEFORE calling `AskUserQuestion`, whose option descriptions are truncated by the UI. Without the rich body, the user sees only the truncated picker — uninformed choice. With it, the chat carries the full tradeoff context the writer would have surfaced interactively.

**Write for a zero-context reader.** The operator answering may have been away for hours and remembers nothing about the session. Each H3 must be self-contained: gloss jargon and internal names on first use, state which original requirement (SPEC section / prior operator decision) the choice affects, and make each option's tradeoffs explicit enough that the operator can decide from this text alone — including which option is architecturally strongest and which best satisfies the original requirements when those differ.

A `NEEDS_INPUT.md` that lacks the `## Decision Context` section is **malformed**. The orchestrator MUST refuse to call `AskUserQuestion` against a malformed file (see "Consumer rules" below).

##### Halting rule (HARD REQUIREMENT)

Batch-mode skills (those invoked with `--batch` by `/lazy-batch` or `/lazy-batch-cloud`) MAY write `NEEDS_INPUT.md` ONLY for a **genuine design choice that requires human judgment** — NOT an operational/mechanical choice that has a single defensible answer the skill could have auto-accepted. Two state-machine windows are eligible:

1. **`/spec` Phase 1 (Step 4 / 4.5 — baseline brainstorm), for product-behavior decisions that GATE the baseline only.** Scope (what's in v1), ownership (which subsystem owns this), core UX shape, and user-facing defaults are **user-authority calls research can never decide** — deferring them into the research prompt would ask Gemini to answer a question only the user can. These are surfaced via `NEEDS_INPUT.md` so the loop advances through `/spec` and pauses (via Step 1g `AskUserQuestion`) only for the choices the user must own. See `~/.claude/skills/spec/SKILL.md` "Phase 1 under `--batch`" for the full contract (draft-the-baseline-first requirement, ≤4-gating-decision cap, classification).
2. **Step 5 (research integration, `/spec` Phase 3) or later** (Steps 6, 7, 8, 9): `RESEARCH.md` (or `RESEARCH_SUMMARY.md`) is on disk and the decision arises during finalization / phase decomposition / planning / implementation / retro.

**Two classes of pre-research input are NOT `NEEDS_INPUT.md`:**

- **Research-*answerable* questions** (prior art, technical tradeoffs, industry conventions) — these go INTO `RESEARCH_PROMPT.md` to be answered by Gemini, NOT lifted to the human via `NEEDS_INPUT.md`. This is the load-bearing distinction in Phase 1: gating *product-behavior* decisions → `NEEDS_INPUT.md`; research-answerable questions → the research prompt.
- **Mechanical / operational choices with a single defensible answer** — auto-accept and proceed. Specifically:
  - Step 4.6 (upstream realign) — no halt; the realign plan's recommendation is authoritative.
  - Step 5 (research prompt generation, `/spec` Phase 2) — no halt; runs mechanically, writes `RESEARCH_PROMPT.md`, returns. The `needs-research` gate (not `NEEDS_INPUT.md`) pauses the loop.
  - Stub-spec detection (Step 4.5) — no halt for the detection itself; treat the stub as Phase 1 starting context (the Phase 1 product-behavior carve-out above still applies to genuinely gating decisions surfaced while brainstorming over the stub).

If a `/spec` Phase 1 (or other pre-research) skill genuinely cannot proceed at all (e.g., the brief is so ambiguous that even a placeholder baseline draft + research prompt cannot be drafted), it writes **`BLOCKED.md`** with `blocker_kind: pre-research-input-required`, NOT `NEEDS_INPUT.md`. `BLOCKED.md` means "can't proceed at all"; `NEEDS_INPUT.md` means "pick between these well-defined options and I'll continue."

**The distinction:**

| File | Semantics | Auto-resume? |
|------|-----------|--------------|
| `NEEDS_INPUT.md` | "Human, choose between these well-defined options" (Phase 1: a baseline-gating product-behavior call; Phase 3+: a choice the research has clarified). | Yes — after the human appends `## Resolution`, the orchestrator re-runs and the writer skill consumes it. |
| `BLOCKED.md` | "This can't proceed at all in the current state." | No — requires a fundamental change (spec rewrite, queue reorder, missing input). |

If you're tempted to write `NEEDS_INPUT.md` from a pre-research step, confirm it is a `/spec` Phase 1 product-behavior decision that GATES the baseline (the only eligible pre-research case). Otherwise you're either (a) writing `BLOCKED.md` instead (can't proceed at all), or (b) deferring a research-answerable question into the research prompt.

##### Producer responsibilities (HARD REQUIREMENT)

A skill that writes `NEEDS_INPUT.md` MUST:

1. **Echo the full `## Decision Context` section to the skill's own chat output BEFORE returning.** The orchestrator re-prints this anyway when it halts, but echoing in the subagent's output also gives the user visibility during the batch loop without scrolling back through orchestrator state.
2. **Use the exact 1:1 mapping between `decisions[i]` titles and the H3 subsection titles in the body.** The orchestrator pairs them by index for the `AskUserQuestion` call — drift breaks the pairing.
3. **Cap to ≤ 4 decisions per file.** More than 4 means the cycle has too many uncoupled questions; split into sequential `NEEDS_INPUT.md` halts across cycles instead (resolve cycle 1's decisions, re-run, surface cycle 2's). Four also matches `AskUserQuestion`'s max questions per call.
4. **Cap to ≤ 4 options per decision.** Matches `AskUserQuestion`'s `options` cap (2-4 entries).
5. **Only write `NEEDS_INPUT.md` from an eligible step** — see the halting rule above. The pre-research exception is narrow: `/spec` Phase 1 product-behavior decisions that GATE the baseline. Research-answerable questions go into `RESEARCH_PROMPT.md`; a step that truly cannot proceed writes `BLOCKED.md`.
6. **For `/spec` Phase 1 and Phase 3 — always halt on product-behavior decisions, even with strong recommendations.** Classify each decision as `product-behavior` (changes what the user sees / does / experiences: UX, scope, user-facing functionality, workflow, defaults, copy, error states) or `mechanical-internal` (invisible to the user: helper placement, internal naming, internal library choice with no behavioral implications). If **any** decision is `product-behavior`, write `NEEDS_INPUT.md` regardless of how strong your `**My recommendation:**` line is — the user retains final authority over product-behavior choices, and the orchestrator's `AskUserQuestion` surfaces your recommendation alongside the alternatives so the user can confirm or override. Auto-accept is permitted **only** when every decision is `mechanical-internal` with a single defensible recommendation. **Phase 1 additionally restricts its `NEEDS_INPUT.md` to product-behavior decisions that GATE the baseline (scope / ownership / core UX / defaults)** and routes research-answerable questions into `RESEARCH_PROMPT.md` instead. See `~/.claude/skills/spec/SKILL.md` "Phase 1 under `--batch`" and "Phase 3 under `--batch`" for the full algorithm and rationale.

### Lifecycle summary

| File | Written when | Cleared when |
|------|-------------|--------------|
| BLOCKED.md | A skill hits an unrecoverable obstacle | Human resolves (delete or human-manual fix); blocked-resolution mode neutralizes by **rename** → `BLOCKED_RESOLVED_<date>.md` (`--neutralize-sentinel`), preserving audit trail |
| DEFERRED_NON_CLOUD.md | /lazy-cloud cannot run a step in cloud | /lazy Step 10 (feature completion) |
| DEFERRED_REQUIRES_DEVICE.md | /mcp-test on a no-real-device host can't certify a real-device-only assertion | A real-device /lazy host re-opens (Step 9), certifies the deferred scenarios, then deletes it + writes VALIDATED.md |
| VALIDATED.md | /lazy after 100% MCP pass | /lazy Step 10 (folded into COMPLETED.md) |
| RETRO_DONE.md | /lazy after retro plan executes | /lazy Step 10 (folded into COMPLETED.md) |
| COMPLETED.md | /lazy Step 10 `__mark_complete__` integrity gate (or --backfill-receipts) | Persists permanently (completion audit trail) |
| SKIP_MCP_TEST.md | /lazy assessment: not testable | Persists permanently |
| MCP_TEST_RESULTS.md | /lazy after mcp-test runs | Persists permanently (audit) |
| NEEDS_RESEARCH.md | `/lazy-batch` or `/lazy-batch-cloud` Step 4 (research halt), fired when the state machine's Step 5 returns `needs-research` (RESEARCH.md absent) — `written_by` is the writing orchestrator per the schema enum above | Human drops RESEARCH.md, then next `/lazy-batch` (or `/lazy-batch-cloud`) run ingests it and proceeds; file may be left stale or overwritten on ingestion |
| NEEDS_INPUT.md | A `--batch` skill hits an ambiguous decision | Resolution-mode neutralizes by **rename** → `NEEDS_INPUT_RESOLVED_<date>.md` (`--neutralize-sentinel`), not deleted; resolved sentinel persists as audit trail |

### Producer rules

- A skill that writes a sentinel MUST emit valid YAML frontmatter per the schema above, then a blank line, then the existing human-readable body content. Do not omit the body — humans read these files directly when /lazy-batch halts.
- All keys are lowercase with underscores. Date format is `YYYY-MM-DD` for `date` fields and ISO 8601 for `blocked_at` (which carries a time component).
- Lists use YAML inline form (`[a, b]`) or block form, parser handles both.
- Do not invent new top-level keys without updating this schema. Tools may reject unknown keys in the future.

### Consumer rules

- Prefer `python3 ~/.claude/scripts/lazy-state.py` to ad-hoc parsing — it implements this schema once and emits structured state JSON.
- If you must parse from skill prose, follow the parsing protocol above and dispatch on `kind`. Never rely on the markdown body.
- Treat a sentinel with a present file but missing or malformed frontmatter as a parse error, not a missing sentinel. Surface the path so the human can fix it.
- **`NEEDS_INPUT.md` exception — body IS load-bearing.** Unlike the other sentinel kinds, the `## Decision Context` body section of `NEEDS_INPUT.md` is the source of truth the orchestrator re-prints to chat. A `NEEDS_INPUT.md` whose body is missing the `## Decision Context` H2 (with H3 subsections matching `decisions:` 1:1) is **malformed**. The orchestrator MUST surface the malformation as a quality issue, name the writing skill, and refuse to call `AskUserQuestion` against the file. The fix is to update the writing skill so it emits the rich body — patching the malformed file by hand defeats the purpose of the schema.
