---
kind: implementation-plan
feature_id: anti-overfit-design-gate
status: In-progress
created: 2026-07-12
complexity: complex
phases: [1, 2, 4]
---

> **Plan** — single self-contained part. Phases 1, 2, 4 worked INLINE this session
> (park-provisional implementation batch, 2026-07-12). Phase 3 (the `lazy_core` ship seam) is
> SEAM-DEFERRED to the STATE lane with the exact wanted diff in PHASES.md → Phase 3 Implementation
> Notes. The feature is provisional-blocked (`NEEDS_INPUT_PROVISIONAL.md`) and cannot complete until
> the operator ratifies D1/D3/D4/D7 — so deferring the seam costs no completion.

# Implementation Plan — anti-overfit-design-gate (Phases 1, 2, 4; Phase 3 seam-deferred)

**PHASES.md:** `docs/features/anti-overfit-design-gate/PHASES.md`
**SPEC.md:** `docs/features/anti-overfit-design-gate/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** executed INLINE with `Read`/`Edit`/`Write` (no `Agent` delegation),
> test-first for the checker. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run before marking done):**
```
python3 -m pytest user/scripts/test_harness_gate.py -q
python3 user/scripts/kpi-scorecard.py --lint --spec docs/features/anti-overfit-design-gate/SPEC.md
python3 user/scripts/project-skills.py
python3 user/scripts/lint-skills.py --check-projected --check-capabilities
python3 user/scripts/generate-coupled-skills.py --check
python3 user/scripts/lazy_parity_audit.py --repo-root .
```

## Key design contract (read before implementing)

- **Structural detectors, self-included.** `harness-gate.py` keys detectors on diff SHAPES
  (append-to-alternation, list/set membership add, deny-branch removal, `*_BYPASS` env-var,
  numeric-literal-only change, test-deletion) — never incident literals — so the checker passes its
  OWN overfit standard. The checker + manifest + component are on the manifest's `gate_own` block.
- **A flag is not a verdict.** The mechanical checker reports; the adversarial half
  (`_components/harness-change-gate.md`) records the judgment in `GATE_VERDICT.md`. Blocking
  authority lives ONLY at the completion gate (D3) — never a hook (hooks stay fail-OPEN).
- **Gate-weakening is never judgment-passable** — it always routes to the D4 operator sign-off,
  transcribed to the verdict `override:` field (per-change, never standing).

## Work units

### WU-1 — Manifest + checker (Phase 1) — DONE
- [x] WU-1.1 `docs/gate/control-surfaces.json` — glob manifest (D1) + self-included `gate_own`.
- [x] WU-1.2 `user/scripts/harness-gate.py` — 4 structural detectors, `--json`, exit 0/1/2, read-only git.
- [x] WU-1.3 `user/scripts/test_harness_gate.py` — 22 fixtures incl. the two named historical instances.

### WU-2 — Verdict schema + adversarial component (Phase 2) — DONE (injection wiring deferred)
- [x] WU-2.1 `GATE_VERDICT.md` schema (`kind: gate-verdict`) in `sentinel-frontmatter.md` (D5).
- [x] WU-2.2 `_components/harness-change-gate.md` — adversarial protocol, tiered D7 semantics, D4 flow, verdict template.
- [x] WU-2.3 Projection + `lint-skills.py` clean.
- [ ] WU-2.4 **DEFERRED** — pipeline-planning-seam injection needs a claude-config `skill-config/` scaffold that doesn't exist (SPEC Open Question). Component is referenced by `/harden-harness` Step 3 today.

### WU-3 — Ship seam (Phase 3) — SEAM-DEFERRED to STATE lane
- [ ] WU-3.1 `lazy_core.gate_verdict_ok` + `apply_pseudo` wiring — EXACT diff in PHASES.md Phase 3 Implementation Notes.
- [ ] WU-3.2 `test_lazy_core.py` gate-verdict fixtures + parity audit.

### WU-4 — Delegation + self-audit (Phase 4) — DONE (registry residency deferred)
- [x] WU-4.1 `/harden-harness` Step 3 delegates smell detection to `harness-gate.py` (protocol unchanged).
- [x] WU-4.2 SPEC `## Intervention Hypothesis` (D6, `signal_independence: independent`) + `## KPI Declaration` (4 rows; `harness-gate` source registered in `kpi-scorecard.py`).
- [x] WU-4.3 Doc rows — root `CLAUDE.md` + `user/scripts/CLAUDE.md`.
- [ ] WU-4.4 **DEFERRED** — insert the 4 drafted KPI rows into `docs/kpi/registry.json` (concurrently owned tonight; land at ratification).
