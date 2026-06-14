## Plan File Frontmatter Schema

All plan files written by `/write-plan`, `/implement-phase`, `/implement-phase-batch`, `/fix`, `/fix-mobile`, `/retro`, `/realign-spec --apply`, and `/plan-feature` carry a YAML frontmatter block as their canonical contract. The markdown body that follows the frontmatter remains human-readable documentation; **only the frontmatter is parsed by consumers** (today: `lazy-state.py`'s `find_implementation_plans()` / `find_retro_plans()`; tomorrow: AlgoBooth's `check-docs-consistency.ts` lint).

This schema is the plan-file analogue of `sentinel-frontmatter.md` — same parsing protocol, separate schema namespace. Plan files are NOT sentinels and MUST NOT use sentinel `kind` values.

### Parsing protocol

1. Read the file as UTF-8.
2. First non-blank line MUST be exactly `---`. Otherwise the file is **legacy** — consumers MAY include it in their plan list as if `status: Ready`, but SHOULD surface a diagnostics warning so the backlog gets backfilled.
3. Read lines until the next line that is exactly `---` (the closing fence). Everything between the fences is YAML.
4. Parse the YAML with a standard library parser (e.g. `yaml.safe_load`). If parsing fails, surface the file path and the parser's line/column rather than silently treating the file as missing.
5. Anything after the closing `---` is the markdown body. Consumers SHOULD NOT parse the body. Producers MUST keep the body informative for humans reading the file directly — including the existing `> **Mobile plan** — ...` preamble.

### Required fields

Every plan file MUST carry the following keys:

```yaml
---
kind: implementation-plan | retro-plan | fix-plan | realign-plan
feature_id: <id>                          # MUST match the parent feature directory name (or the bug directory name for standalone fixes)
status: Draft | Ready | In-progress | Complete
created: <YYYY-MM-DD>
---
```

Optional:

- `complexity: mechanical | complex` — the per-plan-part cost tier (Phase 9, `lazy-validation-readiness`). Selects the `/execute-plan` cycle's dispatch model: `mechanical → sonnet`, `complex → opus`. **Defaults to `complex` (Opus) when absent** — the safe tier, so every legacy/untagged plan keeps dispatching on Opus. `/write-plan` assigns it when it partitions (see `write-plan/SKILL.md` Step 2.5). `mechanical` is reserved for a part whose WUs are **ALL** genuinely mechanical — boilerplate/scaffolding, test-fixture authoring, codegen, pure doc edits, snapshot-covered mechanical refactors — with **no novel design decision, no algorithm/DSP, no cross-boundary wiring**. Anything uncertain stays `complex`. `lazy-state.py` / `bug-state.py` read it via `lazy_core.plan_complexity()`; the tier composes with the loop-block Sonnet downgrade (`repeat_count >= 2`) — a looping `complex` part still downgrades. The dispatch NEVER auto-guesses the tier; it trusts only this explicit tag.
- `phases: [<phase-number-or-letter>, ...]` — which PHASES.md phases this plan implements. Used by `lazy-state.py` to pick the lowest-phase-numbered plan first instead of sorting alphabetically. Always include this when the plan covers one or more specific phases.
- `deliverables: [<phase-N-WU-A>, ...]` — explicit list of PHASES.md deliverable IDs the plan covers. Reserved for a future deterministic completion check (§5 stretch goal). Not currently parsed by `lazy-state.py`.
- `superseded_by: <plan-filename>` — when a plan was abandoned in favor of another. Treat as Complete for state-machine purposes.
- `source_branch: <git branch the plan was authored against>` — advisory provenance. NOT parsed by `lazy-state.py`; used by `/execute-plan` to detect plan/branch drift (when the executing branch differs, file:line anchors and named producers may no longer exist). Producers SHOULD populate it.
- `source_commit: <short SHA at authoring time>` — advisory provenance, paired with `source_branch`. NOT parsed by `lazy-state.py`; lets `/execute-plan` gauge how far the working tree has moved since the plan was authored. Producers SHOULD populate it.

### `kind` → writer-skill mapping

Each producer skill writes exactly one `kind` value. When you author a new plan-file producer, add it here.

| `kind` | Written by |
|--------|-----------|
| `implementation-plan` | `/write-plan`, `/implement-phase`, `/implement-phase-batch`, `/plan-feature` (which dispatches `/write-plan`) |
| `fix-plan` | `/fix`, `/fix-mobile` |
| `retro-plan` | `/retro` (with or without `--auto` / `--batch`) |
| `realign-plan` | `/realign-spec` (always — the read-only path also writes this kind) |

### Lifecycle

| State | Set by | Meaning |
|-------|--------|---------|
| `Draft` | Any `--batch` producer that hit `NEEDS_INPUT.md` mid-generation | Plan was partially authored; the feature is halted awaiting human input. Resuming the producer overwrites the plan and flips status forward. |
| `Ready` | Any producer on successful generation | Plan is fully authored and ready for `/execute-plan`. This is the default state after a clean producer run. |
| `In-progress` | `/execute-plan` when it commits a partial completion before halting on `BLOCKED.md` or `NEEDS_INPUT.md` | Some work units are ticked, but the plan is not complete. The next `/execute-plan` run resumes from the first unchecked WU. |
| `Complete` | `/execute-plan` after every WU checkbox is ticked AND quality gates pass | Audit trail. The plan file STAYS in `plans/` — Complete is not a deletion signal. `lazy-state.py` filters out Complete plans when picking the next implementation plan to execute. |

### Status transitions

- **Producers** (write-plan / fix / retro / realign-spec --apply / etc.) write `status: Ready` on a clean run, or `status: Draft` if `--batch` halted on `NEEDS_INPUT.md` mid-plan.
- **`/execute-plan`** is the only skill that flips `Ready` → `In-progress` → `Complete`. Producers MUST NOT write `Complete` directly.
- **Replanning** a Complete plan (rare): write a new plan file (typically `-v2.md` or a new informative slug) rather than mutating the existing one. The old Complete plan stays as audit trail.

### Producer rules

- Emit valid YAML frontmatter per the schema above, then a blank line, then the existing `> **Mobile plan** — generated by ...` preamble (or the equivalent retro/realign preamble), then the rest of the plan body. Do not omit the body.
- `created:` is the date the plan was first written (NOT the date of the last edit). Use `YYYY-MM-DD`.
- `feature_id:` MUST match the parent feature directory name. For standalone fixes targeting `docs/bugs/<slug>/plans/`, use the bug-directory slug.
- Include `phases:` whenever the plan corresponds to specific PHASES.md phases. Omitting it falls back to alphabetical plan-name sort in `lazy-state.py` — fine for single-plan features, costly for multi-plan features.
- Do not invent new top-level keys without updating this schema **and the downstream consumer lint in lockstep** (see "Consumer lockstep" below). AlgoBooth's `check-docs-consistency.ts` rejects unknown top-level plan keys TODAY (not "in the future") — an undeclared key fails the docs-consistency gate (exit 1) on every plan that carries it.

### Consumer lockstep (HARD — mirrors the `sentinel-frontmatter.md` ↔ `SENTINEL_SCHEMAS` rule)

This schema's optional/required key set is the **producer** half of a producer/consumer contract. The **consumer** half is AlgoBooth's `scripts/check-docs-consistency.ts`:

- `PLAN_REQUIRED` MUST list exactly the **Required fields** above: `kind`, `feature_id`, `status`, `created`.
- `PLAN_OPTIONAL` MUST list every key in the **Optional** block above: `complexity`, `phases`, `deliverables`, `superseded_by`, `source_branch`, `source_commit`.

**Whenever you add, rename, or remove a key here, you MUST update `check-docs-consistency.ts`'s `PLAN_OPTIONAL`/`PLAN_REQUIRED` in the same change** — otherwise a producer emitting the new key (e.g. `/write-plan` emitting `complexity` per `lazy-validation-readiness` Phase 9) trips the consumer's unknown-key rejection and blocks the pipeline gate on every future plan. This is the plan-file analogue of the sentinel-schema lockstep; treat a key present on exactly one side as drift. (A harness-hardening agent CANNOT make the AlgoBooth edit itself — prohibition #1, no target-repo source edits — so when this clause is updated, the AlgoBooth-side change is the operator's/orchestrator's to land in the target repo.)

### Consumer rules

- Prefer `python3 ~/.claude/scripts/lazy-state.py` to ad-hoc parsing — it implements this schema once and emits structured state JSON, including a `diagnostics` array surfacing any plan files missing frontmatter.
- If you must parse from skill prose, follow the parsing protocol above. Dispatch on `kind`. Never rely on the markdown body.
- Treat a plan file with broken/malformed frontmatter as a parse error, not a missing plan. Surface the path so the human can fix it.
- A plan file with NO frontmatter at all is **legacy** — include it in the list as if `status: Ready`, but surface a diagnostics warning so AlgoBooth's lint can flag the backlog.

### Relationship to `sentinel-frontmatter.md`

Plan files and sentinel files share the same YAML-frontmatter parsing protocol but have **disjoint** `kind` namespaces. A `kind: blocked` file in `plans/` is malformed (and vice versa). Consumers can route by file location: anything under `<feature-dir>/plans/*.md` is parsed against this schema; anything at `<feature-dir>/{BLOCKED,VALIDATED,DEFERRED_NON_CLOUD,...}.md` is parsed against `sentinel-frontmatter.md`.
