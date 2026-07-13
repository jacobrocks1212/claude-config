---
kind: implemented
feature_id: skill-config-schema-and-reference-lint
date: 2026-07-12
provenance: operator-directed-interactive
derivation: message-grep
commits: []
decisions: [D1, D2, D3, D4]
---

# Implementation Ledger

**What shipped:** A declaration surface for `repos/<name>/.claude/skill-config/` — a
per-repo `MANIFEST.json` (`provides[]` + `intended_absent[{file,reason}]` +
`json_schemas{}`) authored for algobooth (22 files) and cognito-forms (16 files); a new
stdlib sibling script `user/scripts/lint-skill-config.py` that validates each manifest
bidirectionally, structurally validates `build-queue-ops.json` (the fail-open
`build-queue-enforce.sh` config), and sweeps every `.claude/skill-config/<file>` mention
across every skill source (`!cat` fallback forms + prose) against every repo's on-disk files,
honoring `intended_absent` markers and refusing a fallback-less bare pointer even when
declared absent; the Phase 0 quick win authoring
`repos/algobooth/.claude/skill-config/commit-policy.md` (killing the 377-failed-Read
`commit-policy.md` cluster at the source); a small additive `--check-skill-config` flag on
the existing `lint-skills.py` (default off, byte-identical without it); 29 pytest cases
(`test_lint_skill_config.py`, including a live self-check that the real tree lints clean);
and a `docs/kpi/registry.json` row (`skill-config-broken-reference-reads`) tracking the
friction class this feature targets.

**Decisions that drove it:** D1 (per-repo `MANIFEST.json` as the declaration surface, not a
central registry — provisionally accepted, ratification outstanding) · D2 (stdlib structural
JSON-schema checkers dispatched via the manifest's `json_schemas` map — auto-accepted) · D3
(the reference sweep covers both `!cat` primary paths and prose mentions, per repo, honoring
`intended_absent`; implemented as a NEW sibling script with a small additive hook-in on
`lint-skills.py` rather than a deep rewrite, and a script-owned `SUPPRESSIONS` allowlist
instead of an inline skill-file comment, for file-ownership reasons — auto-accepted with a
documented implementation-time deviation) · D4 (author the AlgoBooth `commit-policy.md`
pointer-adoption file as the quick win, independent of the manifest machinery — provisionally
accepted, ratification outstanding).

**Receipt: COMPLETED.md (provenance: operator-directed-interactive).**
