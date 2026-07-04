# HANDOFF — harness-change-canary-rollback (barely started, session ended at spend limit 2026-07-04)

**Checkpoint branch:** `origin/lane/harness-change-canary-rollback` — contains only an initial
RESEARCH.md draft (WIP commit). Effectively a fresh start; the SPEC is the authoritative input.

**Decisions already approved (operator, 2026-07-04 — do not re-ask):** locked D1 (canary:
sub-map on the intervention record, armed by manifest-intersection; pair_scope over
lazy-parity-manifest.json), D5 (trip → evidence-bearing bug stub via `--enqueue-adhoc --type bug`,
slug `canary-revert-<intervention_id>`, EVIDENCE.md capsule, once-ever guard via
canary.status: tripped), D6 (watcher = `efficacy-eval.py --canary` at run boundaries, sole writer
of canary.* updates), D7 (close stamps + `## Canary <date>` section); recommendations taken:
D2→A (10 runs / 30-day ceiling / 25% relative or KPI band / 2 attributable incidents),
D3→A (surface-based attribution, unknown never attributes), D4→A (no auto-revert class in v1).

**All hard deps are LANDED on this branch:** intervention-efficacy-tracking
(`lazy_core.record_intervention`, `docs/interventions/`, `user/scripts/efficacy-eval.py`),
code-doc-provenance-linkage (commit brackets → commit_set), incident-auto-capture
(hook-events.jsonl clusters). `docs/gate/control-surfaces.json` does NOT exist yet
(anti-overfit-design-gate ships it — also not yet implemented): ship a canary-owned fallback
surface-glob constant and document that the manifest takes precedence when present.

**Everything remains to build** — follow the standard pipeline artifacts (RESEARCH_SUMMARY →
PHASES → plan → TDD) per the SPEC's 4 phases.
