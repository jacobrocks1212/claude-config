---
kind: needs-input
feature_id: skill-config-schema-and-reference-lint
written_by: spec
decisions:
  - "D1: Declaration surface for per-repo skill-config file provenance"
  - "D4: Which variant ships the commit-policy.md quick win"
date: 2026-07-12
class: product
divergence: isolated
audit_divergence: isolated
next_skill: spec-phases
---

# NEEDS_INPUT — Provisionally Accepted (park-provisional protocol)

This feature's SPEC named two decisions as `product-behavior (needs operator confirmation)`
(D1 and D4) rather than `mechanical-internal`. Both carry a single, strongly-justified
recommended option in the SPEC itself and are low-divergence (config-surface-only; no
architecture, persistent-data, or user-visible-workflow fork). Per the overnight
park-provisional protocol, this session adopted both recommendations and is proceeding —
this file records that choice for ratify-or-redirect review rather than halting the run.

## Decision Context

### 1. D1: Declaration surface for per-repo skill-config file provenance

**Problem:** Nothing today declares which files a repo's `.claude/skill-config/` intends to
provide, so absence is ambiguous by construction (the 377-failed-Read `commit-policy.md`
cluster). The SPEC needs ONE place a repo declares its provided files + known
intended-absent references (each with a reason).

**Options:**
- **A — per-repo `repos/<name>/.claude/skill-config/MANIFEST.json` (Recommended)** — lives
  with what it describes, travels with the repo's `.claude/` symlink projection, one file
  per repo. `provides` is lint-checked bidirectionally (declared-but-missing /
  present-but-undeclared both error); `intended_absent` entries require a `reason`. Small,
  diffable, and matches the existing per-repo unit of projection (`project-skills.py`
  already discovers repos the same way).
- **B — central registry in `user/scripts/`** — one file for all repos, but inverts
  ownership (a repo's contract living outside the repo's own dir) and bit-rots like any
  central inventory.
- **C — infer from references (no manifest)** — lint computes the union of all
  `.claude/skill-config/` references and flags any repo missing a referenced file; cannot
  express intended-absent, which is the feature's core semantic (commit-policy.md being
  absent in AlgoBooth today is *correct*, not a lint finding to suppress).

**Recommendation:** A — the manifest is small, diffable, colocated with what it declares,
and the intended-absent marker is the whole point of this feature.

### 2. D4: Which variant ships the commit-policy.md quick win

**Problem:** The 377-error cluster (failed Reads of AlgoBooth's absent `commit-policy.md`)
has a two-line fix available today, independent of the manifest machinery. Which variant
ships it?

**Options:**
- **A — author `repos/algobooth/.claude/skill-config/commit-policy.md` (Recommended)** — an
  explicit adoption of the `_components/commit-and-push.md` default (a pointer file, not a
  fork — no policy duplication) plus any AlgoBooth-specific deltas (none exist today). Kills
  every 377-class failed Read at the source; the very next Read succeeds.
- **B — flip the 29 references from read-then-fallback to test-then-read** — no new file,
  but edits 17 skills (and their coupled pairs) outside this feature's ownership, and every
  future reference must remember the new ordering convention.
- **C — wait for the manifest (D1) + a smarter reference convention** — leaves the #1 error
  cluster burning for the length of the whole pipeline run.

**Recommendation:** A — independent of the manifest machinery, so the dominant cost dies
first; zero edits outside this feature's file ownership.

## Resolution

resolved_by: auto-provisional
decision_commit: a547c716d1dfae64cf5f344cb7cabfce13f4bac5

**Choice (D1):** A — per-repo `MANIFEST.json`. Implemented as
`repos/algobooth/.claude/skill-config/MANIFEST.json` and
`repos/cognito-forms/.claude/skill-config/MANIFEST.json`, validated by the new
`user/scripts/lint-skill-config.py`.

**Choice (D4):** A — authored `repos/algobooth/.claude/skill-config/commit-policy.md` as an
explicit pointer-adoption of the generic default. Shipped as this feature's Phase 0.

Both choices are config/doc-surface-only (isolated divergence on both keys) — a redirect at
ratification would mean deleting/renaming a JSON file and a markdown pointer file, with no
downstream architectural coupling. Ratify-or-redirect before this feature completes.
