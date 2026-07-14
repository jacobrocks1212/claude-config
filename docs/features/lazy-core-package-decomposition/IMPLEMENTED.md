---
kind: implemented
feature_id: lazy-core-package-decomposition
date: 2026-07-14
provenance: pipeline-gated
derivation: message-grep
commits: [f00ceaf, fdbe299, 21e4e80, 2b45e39, 57645f0, 9888ecf, 733b21f, '4222398', 2bd9152,
  5bc648b, c0124ff, 3411b45, 54b8859, 7678b5f, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** `lazy_core.py` is a 17,686-line single-module monolith with 169 commits since 2026-05-01 — the hottest file in the repo — so every intervention, however local, canaries against one file, and the PreToolUse hooks (`lazy_guard.py`/`lazy_inject.py`) pay a full-module import (~107 ms warm, ~705 ms cold) on every fire. Its test twin `test_lazy_core.py` is 32,675 lines / 973 tests in one flat file (8.6 s collection, 726 hand-rolled `TemporaryDirectory` sites, zero parametrize/fixtures). Decompose it into a `lazy_core/` package behind a byte-compatible facade — cleanest seams first (docmodel, dep DAG, host capabilities, notify), the marker/ownership plane last — with three locked constraints: mutable module globals hoist into a shared `_ctx` first; the facade keeps all 20 importers and the regex-over-source auditors working unmodified; and no write-path module moves while the two open write-path bugs are unfixed (hard deps). In scope alongside: the test-file split with conftest fixtures, a fast-import path for hooks, and a ruff/pyflakes gate on `user/scripts/` (F811 would already catch `lazy_core.py`'s duplicate `_current_head` at lines 3875/5661).

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
