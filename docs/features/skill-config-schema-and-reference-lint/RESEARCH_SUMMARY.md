---
kind: research-summary
feature_id: skill-config-schema-and-reference-lint
date: 2026-07-12
source: codebase-survey (inline recon; no Gemini research dispatched — docs-only harness
  tooling, no external-conventions question at stake)
---

# Research Summary — skill-config-schema-and-reference-lint

Inline recon against the working tree: every skill-config file kind, every consumer of the
`.claude/skill-config/<file>` convention, and the two existing scripts this feature extends
(`lint-skills.py`, `build-queue-enforce.sh`). Confirms the SPEC's field-cost claims and
enumerates the exact reference set the reference sweep (D3) needs to resolve.

## Inventory: every skill-config file kind on disk (2026-07-12)

| Repo | Files | Notable |
|------|-------|---------|
| `repos/algobooth/.claude/skill-config/` | 21 (→22 after this feature's Phase 0) | Most fully-configured repo; the only one with `long-build-ownership.md`, `cycle-prompt-addenda.md`, `investigation-runtime.md`, the `phases-runtime-*`/`spec-testing-guidance.md`/`retro-runtime-evidence.md` AlgoBooth-specific overrides |
| `repos/cognito-forms/.claude/skill-config/` | 16 | The only repo with `ado-doc-integration.yml`, `cog-doc-track-{open,close}.md`, `phases-reuse-ledger.md`, `phases-review-guardrails.md`, `post-phase-code-review-checkpoint.md`, `reuse-first-discovery.md`, `team-architect-stance.md`, `spec-bug-work-item-context.md`, `spec-evidence-gathering.md` |
| `repos/cognito-docs/.claude/` | no `skill-config/` dir | confirmed out of scope per the SPEC's Repo discovery rule (a repo without the dir stays out of scope until it grows one) |

Both repos already ship `capabilities.txt`, `build-queue-ops.json`, `quality-gates.md`,
`skill-catalog.md`, `onboarding-repo-map.md` (common); `commit-policy.md` was cognito-forms-only
before this feature's Phase 0.

## Reference census — every `.claude/skill-config/<file>` mention (2026-07-12)

`grep -rn '\.claude/skill-config/[A-Za-z0-9_.-]\+' user/skills/ repos/*/.claude/skills/` finds
**101 mentions** across 34 files resolving to **30 distinct target filenames** (after excluding
two malformed bare-directory matches with no filename, and one stray trailing-period capture
fixed in the sweep's regex). Classification:

- **20 filenames** appear in a `!`cat X 2>/dev/null || cat _components/Y`` or `|| echo "..."`
  line (the two existing fallback forms `lint-skills.py` already parses) — these are the
  "has fallback" class.
- **1 filename** (`mcp-tool-catalog.md`) appears only in prose, but the prose is a documented
  no-op statement ("Catalog absent → this audit is a no-op") — treated as fallback-bearing via
  a prose-hint heuristic (see Assumptions below), not a code-form fallback.
- **2 filenames** (`long-build-ownership.md`, `cycle-prompt-addenda.md`) appear ONLY as bare
  prose pointers with zero fallback language anywhere in the corpus — these are the exact
  "dead prose pointer, no fallback" class the SPEC names (`long-build-ownership.md` at
  `user/skills/lazy-batch/SKILL.md:596`, confirmed dead for every repo except AlgoBooth, which
  is the only repo that provides the file).
- **1 filename** (`gemini-sprint.md`) is aspirational future-tense prose ("parameterize the
  staging path via a per-repo `.claude/skill-config/gemini-sprint.md` **later**") — not a live
  reference to any repo today, confirmed by `user/skills/ingest-research/SKILL.md`'s own
  surrounding text.
- **6 filenames** are components documenting their OWN per-repo override path inside
  `_components/<name>.md` itself (e.g. `_components/phases-reuse-ledger.md` says "the
  project-specific version lives at `.claude/skill-config/phases-reuse-ledger.md`, which is
  cat'd in place of this file") — self-description of the fallback pattern, not an independent
  consumption site (the real reference is the SKILL.md `!cat` line elsewhere, already counted).

**Field-cost claim re-verified:** `commit-policy.md` is referenced 15 times across 15 distinct
skill/component files (spec-phases-batch, retro, lazy-batch, lazy-bug-batch,
lazy-batch-retro, realign-spec, ingest-research, fix-mobile ×3, implement-phase-batch ×3,
execution-contract ×2, decision-resume ×2, blocked-resolution, halt-resolution,
lazy-batch-prompts/{cycle-base-prompt,dispatch-apply-resolution} ×5 combined) — consistent with
the SPEC's "29x across 17 skill files" figure counting both the primary path AND fallback-target
mentions per line as the SPEC's own methodology did. Every mention resolves via a code-form
fallback (`|| cat ~/.claude/skills/_components/commit-and-push.md`), so once AlgoBooth's own
`commit-policy.md` exists (this feature's Phase 0), every one of these Reads succeeds on the
first try.

## Consumers of the existing `lint-skills.py` (surface this feature extends)

- `_SIMPLE_CAT` / `_FALLBACK_CAT` / `_FALLBACK_ECHO` regexes (lines 28-36) parse the three
  standalone-injection forms today, but only validate the **fallback component target**
  (`_components/<x>`), never the **skill-config primary path** against any repo — confirmed by
  reading `lint_skill` (L58-109): the `_FALLBACK_CAT`/`_FALLBACK_ECHO` branches check
  `_components/<comp>` existence only.
- `_read_capabilities` / `lint_capabilities` already resolve `repos/<name>/.claude/skill-config/
  capabilities.txt` per repo and are the existing seed of "per-repo awareness" the SPEC cites.
- `skill_repos.iter_config_repos` is the shared repo-discovery helper `lint-skills.py` and
  `project-skills.py` both already use (`marker=".claude/skills"` there); reused conceptually
  (not imported — this feature's own repo discovery is a plain `repos/<name>/.claude/
  skill-config` directory scan, since it operates only on the internal, git-tracked `repos/`
  tree, not the machine-variable `~/source/repos` sibling-checkout union `skill_repos` exists
  to handle).

## `build-queue-ops.json` shape (confirmed against `build-queue-enforce.sh`)

Read at `build-queue-enforce.sh` L336-342 (repo ops-manifest resolution) — confirms the SPEC's
claimed shape: `{version, ops: {<op>: {exec, kind, hygiene, skill, deny, lane?}}}`. Both real
files (algobooth: `tauri-build`, `cargo-release`; cognito-forms: `msbuild`, `mstest`, `nxbuild`,
`nxtest`) validate cleanly against the structural checker this feature ships.

## Assumptions that proved wrong/drifted from the SPEC's literal text

- **D3's literal "inline suppression comment"** convention was NOT implemented as originally
  illustrated. Every real suppression-needing finding lives in `user/skills/**` or
  `repos/*/.claude/skills/**`, which this feature does not own (concurrent SKILLS-lane
  coupled-pair-generation work is in flight on those trees per the pipeline's file-ownership
  partition for this run). A script-owned `SUPPRESSIONS` allowlist (in
  `lint-skill-config.py`) preserves the same "reason required, debt visible" invariant without
  an out-of-lane write. See the SPEC's Open Questions resolution.
- **Prose-fallback detection needed a heuristic**, not pure regex-on-`!cat`-forms: several
  legitimate no-op-on-absence statements (`mcp-tool-catalog.md`'s "Catalog absent → this audit
  is a no-op") are prose, not code. A keyword-hint regex (`if absent`, `no-op`, `fallback`,
  `instead`, `2>/dev/null`, …) classifies these correctly; verified against every real
  reference in the corpus — the only bare-prose survivors are the two genuinely-dead pointers
  named above.
- **The reference regex needed a real-extension anchor** (`\.(md|json|txt|yml)$`), not an
  open character class — an unanchored class captured a stray trailing period on one prose
  sentence (`commit-policy.md.`) as part of the filename, producing a false dangling-reference
  finding on first run.

## Design decision this recon confirms (feeds Locked Decisions)

Every one of the SPEC's four recommended options (D1 A, D2 auto-accept, D3 auto-accept, D4 A)
is directly executable against the real tree with no blocking surprise — D1/D4 were still
locked via the park-provisional protocol (`NEEDS_INPUT_PROVISIONAL.md`) since the SPEC itself
classified them as product-behavior forks needing operator confirmation, despite the strong,
uncontested recommendation.
