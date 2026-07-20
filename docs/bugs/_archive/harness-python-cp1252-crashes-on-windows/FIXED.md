---
kind: fixed
feature_id: harness-python-cp1252-crashes-on-windows
date: 2026-07-20
provenance: backfilled-unverified
validated_via: lazy-state.py --test + bug-state.py --test ("All smoke tests passed") on a cp1252 host; lazy_parity_audit.py exit 0; lint-skills.py + doc-drift-lint.py exit 0; pytest tests/test_lazy_core/ (-s) 2 failed / 1337 passed, both failures pre-existing on origin + unrelated to encoding; NOT pipeline-gated (harden-harness inline manual reconcile)
fix_commits:
  - d35a4e64  # Round 49 — console stdio + production git readers + 13 write_text
  - e80152b3  # Round 128 — 252 test/fixture subprocess captures + AST regression guard
auto_ticked_rows: 0
---

# Completion Receipt

`harness-python-cp1252-crashes-on-windows` marked Fixed on 2026-07-20 during an inline
manual `/harden-harness` round (Round 128). This receipt was written by the hardening
round, NOT the pipeline's `__mark_fixed__` gate — provenance is `backfilled-unverified`
(shipped OUT-OF-PIPELINE via `harden(...)` commits), though the fix carries real green
regression evidence recorded in `validated_via`.

## Scope closed

Round 49 (commit `d35a4e64`) fixed the three crashing surfaces (`harness-gate.py` `_run_git`,
`lazy-state.py`/`bug-state.py` stdio) + the production git readers + 13 `write_text` calls, and
DEFERRED (a) the test-fixture `subprocess` captures it judged as reading child ASCII and (b) "the
durable class-level guard" as its named over-fit spin-off. The origin/main merge (629 commits)
then landed many new fixtures/captures with the same latent bug, some comparing non-ASCII child
output — so (a) was partially wrong and (b) was never built.

Round 128 (commit `e80152b3`) completes both: a call-graph-scoped AST sweep encoded all 252
remaining test/fixture-context `subprocess.*` text captures (`encoding="utf-8", errors="replace"`)
across 31 files, and built the deferred durable guard (`_collect_cp1252_fragile_captures` +
`test_no_cp1252_fragile_captures_in_scripts` + a negative-fixture non-vacuity proof), so a future
fixture reintroducing the class is a hard test failure. Mode 1 (`write_text` non-ASCII no-encoding)
audited to 0 remaining.
