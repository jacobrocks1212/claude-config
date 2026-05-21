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

Body keeps the human-readable summary of which scenarios ran.

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
---
```

Body keeps the per-round summary so humans can scan retro history.

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
- `skipped_by: <"lazy" | "lazy-cloud">` — who wrote the skip.

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
---
```

Body keeps the per-scenario pass/fail breakdown.

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

A `NEEDS_INPUT.md` that lacks the `## Decision Context` section is **malformed**. The orchestrator MUST refuse to call `AskUserQuestion` against a malformed file (see "Consumer rules" below).

##### Post-research halting rule (HARD REQUIREMENT)

Batch-mode skills (those invoked with `--batch` by `/lazy-batch` or `/lazy-batch-cloud`) MAY write `NEEDS_INPUT.md` ONLY when:

1. The current state machine step is **Step 5 (research integration) or later** (Steps 6, 7, 8, 9). That is: `RESEARCH.md` (or `RESEARCH_SUMMARY.md`) is on disk for the feature, AND the decision arises during finalization / phase decomposition / planning / implementation / retro.
2. The decision is a **genuine design choice** that requires human judgment — NOT an operational/mechanical choice that has a single defensible answer the skill could have auto-accepted.

**Pre-research steps MUST auto-accept the recommended option and proceed.** Specifically:

- Step 4.5 (stub-spec detection) — no halt; treat the stub as Phase 1 starting context.
- Step 4.6 (upstream realign) — no halt; the realign plan's recommendation is authoritative.
- Step 5 (research prompt generation, `/spec` Phase 2) — no halt; placeholder open questions go INTO `RESEARCH_PROMPT.md` to be answered by Gemini, not lifted to the human via `NEEDS_INPUT.md`.

Halting before research means asking the human to decide without the information needed to decide — which the user has explicitly flagged as the wrong shape of escalation. If a pre-research skill genuinely cannot proceed without input (e.g., the feature description is so ambiguous that even a placeholder research prompt cannot be drafted), it writes **`BLOCKED.md`** with `blocker_kind: pre-research-input-required`, NOT `NEEDS_INPUT.md`.

**The distinction:**

| File | Semantics | Auto-resume? |
|------|-----------|--------------|
| `NEEDS_INPUT.md` | "Human, choose between these well-defined options the research has clarified." | Yes — after the human appends `## Resolution`, the orchestrator re-runs and the writer skill consumes it. |
| `BLOCKED.md` | "This can't proceed at all in the current state." | No — requires a fundamental change (spec rewrite, queue reorder, missing input). |

If you're tempted to write `NEEDS_INPUT.md` from a pre-research step, you're either (a) writing `BLOCKED.md` instead, or (b) deferring the question into the research prompt.

##### Producer responsibilities (HARD REQUIREMENT)

A skill that writes `NEEDS_INPUT.md` MUST:

1. **Echo the full `## Decision Context` section to the skill's own chat output BEFORE returning.** The orchestrator re-prints this anyway when it halts, but echoing in the subagent's output also gives the user visibility during the batch loop without scrolling back through orchestrator state.
2. **Use the exact 1:1 mapping between `decisions[i]` titles and the H3 subsection titles in the body.** The orchestrator pairs them by index for the `AskUserQuestion` call — drift breaks the pairing.
3. **Cap to ≤ 4 decisions per file.** More than 4 means the cycle has too many uncoupled questions; split into sequential `NEEDS_INPUT.md` halts across cycles instead (resolve cycle 1's decisions, re-run, surface cycle 2's). Four also matches `AskUserQuestion`'s max questions per call.
4. **Cap to ≤ 4 options per decision.** Matches `AskUserQuestion`'s `options` cap (2-4 entries).
5. **Never write `NEEDS_INPUT.md` from a pre-research step** — see the post-research halting rule above. If a pre-research step truly cannot proceed, write `BLOCKED.md` instead.
6. **For `/spec` Phase 3 specifically — always halt on product-behavior decisions, even with strong recommendations.** Classify each Phase 3 decision as `product-behavior` (changes what the user sees / does / experiences: UX, scope, user-facing functionality, workflow, defaults, copy, error states) or `mechanical-internal` (invisible to the user: helper placement, internal naming, internal library choice with no behavioral implications). If **any** decision is `product-behavior`, write `NEEDS_INPUT.md` regardless of how strong your `**My recommendation:**` line is — the user retains final authority over product-behavior choices, and the orchestrator's `AskUserQuestion` surfaces your recommendation alongside the alternatives so the user can confirm or override. Auto-accept is permitted **only** when every decision is `mechanical-internal` with a single defensible recommendation. See `~/.claude/skills/spec/SKILL.md` "Phase 3 under `--batch`" for the full algorithm and rationale.

### Lifecycle summary

| File | Written when | Cleared when |
|------|-------------|--------------|
| BLOCKED.md | A skill hits an unrecoverable obstacle | Human resolves (delete or via /add-phase / /lazy skip) |
| DEFERRED_NON_CLOUD.md | /lazy-cloud cannot run a step in cloud | /lazy Step 10 (feature completion) |
| VALIDATED.md | /lazy after 100% MCP pass | /lazy Step 10 |
| RETRO_DONE.md | /lazy after retro plan executes | /lazy Step 10 |
| SKIP_MCP_TEST.md | /lazy assessment: not testable | Persists permanently |
| MCP_TEST_RESULTS.md | /lazy after mcp-test runs | Persists permanently (audit) |
| NEEDS_RESEARCH.md | /lazy-batch when RESEARCH.md absent | Human runs research, drops RESEARCH.md, deletes this file |
| NEEDS_INPUT.md | A `--batch` skill hits an ambiguous decision | Human resolves the decisions, deletes the file, re-runs |

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
