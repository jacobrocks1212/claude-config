# Implementation Phases — Anti-Overfit + Tautology Design Gate for Harness Changes

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress
<!-- Cannot reach Complete: the four product decisions (D1/D3/D4/D7) are provisionally accepted
     under the park-provisional directive (NEEDS_INPUT_PROVISIONAL.md, divergence: structural).
     Completion is mechanically blocked (lazy_core.apply_pseudo refuses on the provisional
     sentinel) until the operator ratifies-or-redirects. -->

**MCP runtime:** not-required — pure claude-config harness mechanics (a committed JSON manifest,
a stdlib Python checker/linter, a `_components/` adversarial protocol + verdict schema, and a
completion-gate ship seam in `lazy_core`). No Tauri app, no MCP-reachable surface; validation is
`pytest` on the new `test_harness_gate.py`, the existing `test_lazy_core.py` gate suite, and
`lint-skills.py` + `project-skills.py` after the skill/component edits. This is the
`standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Provisional-acceptance status (park-provisional-acceptance)

The four PRODUCT decisions were held for the operator by `/spec` Phase 3 and PROVISIONALLY
accepted 2026-07-12 (recommended option A each): **D1** committed glob manifest, **D3** two
pipeline seams + harden-harness delegation (blocking only at the completion gate), **D4**
NEEDS_INPUT.md sign-off transcribed to the verdict `override:` field, **D7** tiered blocking.
File-level divergence honestly graded `structural` (each forks product behavior) — ratification is
loud. The three mechanical decisions (D2 detector split, D5 verdict residency, D6 self-audit
KPI/record) auto-accept per their SPEC resolutions.

## Cross-feature Integration Notes

- **`intervention-efficacy-tracking` (Complete) — composes.** Efficacy REFUTED verdicts are the
  gate's ground truth (D6: a gate that passes changes later REFUTED is mis-tuned). The tautology
  detector reads the SAME `signal_independence` vocabulary
  (`lazy_core.parse_intervention_hypothesis`). The gate's own `## Intervention Hypothesis` declares
  `signal_independence: independent` over a signal efficacy/retro produce, not the gate.
- **`friction-kpi-registry` (Complete) — composes.** The `harness-gate` signal source + its four
  self-audit selectors are registered in `kpi-scorecard.py`'s `_SOURCES` at spec-finalization (the
  `canary-trip-precision` precedent); the drafted `## KPI Declaration` rows lint clean via
  `--lint --spec`. Registry-row residency + compute land at ratification (registry concurrently
  owned tonight — one-writer rule).
- **`park-provisional-acceptance` (Complete) — consumes.** The completion gate's existing
  `NEEDS_INPUT_PROVISIONAL.md` refusal (`lazy_core.apply_pseudo`, line ~5110) already blocks this
  feature's completion — the ship seam (D3) composes with that same refusal block.

---

### Phase 1: Manifest + mechanical checker

**Phase kind:** design

**Scope:** The committed control-surface manifest (D1 option A) and the stdlib mechanical checker
with all four detectors (D2) + `--json`. Detectors are structural (diff-shape), not incident-literal
— the checker's own files are on the manifest, so it must pass its own overfit check.

**Deliverables:**
- [x] `docs/gate/control-surfaces.json` — the glob manifest (initial set per D1) + a self-included
  `gate_own` block (checker, manifest, component). Schema-versioned; documents fnmatch/`**` semantics.
- [x] `user/scripts/harness-gate.py` — stdlib, read-only (`git diff` / `--name-only`); `--repo-root`,
  `--range A..B` / `--staged`, `--feature-dir`, `--json`. Detectors: overfit (alternation/list-element
  append + incident-shaped literal), gate_weakening (test-deletion, numeric-literal change,
  exemption-set add, `*_BYPASS` env-var, deny-branch removal), tautology (`## Intervention Hypothesis`
  presence + `signal_independence` substance), complexity (declaration-required in scope). Exit 0
  pass/out-of-scope, 1 verdict-required, 2 malformed.
- [x] `user/scripts/test_harness_gate.py` — 22 pytest fixtures incl. the two NAMED historical
  regression fixtures (`_VERIFICATION_SECTION_RE` phrase-append → overfit flag; GAP-2 exemption-add +
  gate-test deletion → gate_weakening hit), scope in/out, self-inclusion, malformed-manifest.

**Minimum Verifiable Behavior:** `harness-gate.py --range HEAD` over the working tree returns
`in_scope: true` with `scope_hit` naming the touched manifest paths; a diff touching only non-manifest
paths returns `in_scope: false`, exit 0. The GAP-2 fixture classifies `gate_weakening: hit`.

**Runtime Verification** *(checked by integration test — NOT by the implementation agent):*
- [x] Every detector classifies its fixture diffs correctly incl. the two named historical instances.
  *(Evidence: `SKIP_MCP_TEST.md` — `test_harness_gate.py` 22/22 + a live `--range HEAD` run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface. Verification is `pytest`.

**Prerequisites:** None.

**Files likely modified:** `docs/gate/control-surfaces.json` (new), `user/scripts/harness-gate.py`
(new), `user/scripts/test_harness_gate.py` (new).

**Testing Strategy:** Hermetic — fixtures feed synthetic unified-diff text directly to the pure
detector functions (no real git repo). The manifest self-inclusion test reads the real committed
manifest.

**Integration Notes for Next Phase:** Phase 2's component consumes the checker's JSON shape
(`in_scope`, `scope_hit`, `checks.<name>.result`, `verdict_required`, `gate_weakening_hit`).

---

### Phase 2: Verdict artifact + adversarial component

**Phase kind:** design

**Scope:** The `GATE_VERDICT.md` schema (D5) and the adversarial protocol component (D3 design seam
+ D4/D7 recording), plus the projection/lint pass.

**Deliverables:**
- [x] `GATE_VERDICT.md` schema in `_components/sentinel-frontmatter.md` (`kind: gate-verdict`,
  frontmatter `scope_hit`/`checks`/`retires`/`override`, load-bearing `## Adversarial answers` body;
  AlgoBooth `check-docs-consistency.ts` lockstep note). Permanent audit artifact, NOT a halt sentinel.
- [x] `user/skills/_components/harness-change-gate.md` — the adversarial questions per check, the
  tiered blocking semantics (D7), the D4 sign-off flow, and the `GATE_VERDICT.md` template. Names the
  checker invocation.
- [x] Projection + lint green after the component/schema edits (`project-skills.py`, `lint-skills.py`).
- [ ] **Planning-seam injection wiring (DEFERRED — SPEC Open Question).** The design-seam injection of
  `harness-change-gate.md` into the pipeline planning stage for claude-config items needs a
  claude-config `skill-config/` scaffold that does not exist yet. The component is authored and
  referenced by `/harden-harness` Step 3 (a concrete consumer that exists today); the pipeline-planning
  injection is recorded here as follow-up wiring (see Implementation Notes).

**Minimum Verifiable Behavior:** A scoped fixture item with a written `GATE_VERDICT.md` validates
against the schema; `project-skills.py` expands the component with no unresolved `!cat`; `lint-skills.py`
is clean.

**Runtime Verification** *(checked by lint/projection — NOT by the implementation agent):*
- [x] Component projects + lints clean; the schema is well-formed. *(Evidence: `SKIP_MCP_TEST.md` —
  `project-skills.py` + `lint-skills.py --check-projected --check-capabilities` clean.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (checker JSON shape).

**Files likely modified:** `user/skills/_components/sentinel-frontmatter.md`,
`user/skills/_components/harness-change-gate.md` (new).

**Testing Strategy:** Projection + skill lint. Schema validity by inspection against the sibling
sentinel schemas.

**Integration Notes for Next Phase:** Phase 3's ship seam reads `GATE_VERDICT.md` via the same
schema; the `gate_verdict_ok` helper re-derives scope from the item's commit set against the manifest.

---

### Phase 3: Ship seam + override round  *(SEAM APPLIED — STATE lane, state-batch-5)*

**Phase kind:** integration

**Scope:** The completion-gate ship seam (`lazy_core.gate_verdict_ok`) refusing a scoped item with a
missing/failing/unsigned-weakening `GATE_VERDICT.md`, mirrored in both completion handlers
(parity-audited); the NEEDS_INPUT.md flow for gate-weakening hits and unjustified flags (D7).

> **APPLIED by the STATE lane (state-batch-5), verbatim per the recorded diff below.** The
> checker, manifest, component, schema, and tests (Phases 1–2, 4) were already landed and
> self-contained; this seam adds `lazy_core.gate_verdict_ok` + its `apply_pseudo` wiring exactly
> as recorded, with ONE implementation delta from the literal snippet (documented below):
> `parse_sentinel`'s `_die()`-on-malformed path is caught (`SystemExit`) and degraded to an
> honest `ok: False` refusal instead of letting the JSON-then-`sys.exit(2)` propagate through
> `apply_pseudo` — consistent with this repo's "gates refuse, they don't crash" convention and
> with every other branch of this same function. **The feature is STILL NOT marked Complete** —
> `NEEDS_INPUT_PROVISIONAL.md` remains unratified (structural divergence), so this seam is LIVE
> but the feature's own completion stays gated on operator ratification. Per its own honesty
> rail, the whole seam only ever enforces when `docs/gate/control-surfaces.json` exists (it does,
> today) — a ratification redirect that removes the manifest disarms the seam with zero code
> changes.

**Deliverables:**
- [x] `lazy_core.gate_verdict_ok(spec_path, repo_root) -> dict` — pure read: re-derive scope from the
  item's commit set against the manifest (deterministic, NOT trusted from the verdict); if in scope,
  require a `GATE_VERDICT.md` whose every `checks.<name>` is not `fail` and whose any `gate_weakening`
  hit carries an `override:` field. Returns `{ok, reason, in_scope}`.
- [x] Wired into `apply_pseudo`'s `__mark_complete__` / `__mark_fixed__` block, right after the
  existing `NEEDS_INPUT_PROVISIONAL.md` refusal, refusing with zero writes and naming the
  missing/failing check.
- [x] Parity: single shared `apply_pseudo` function, invoked identically by both `lazy-state.py` and
  `bug-state.py` — mirrored by construction, not a separate per-script edit; `lazy_parity_audit.py`
  exit 0. `test_lazy_core.py` fixtures: scoped item without verdict refuses; signed override
  completes; out-of-scope byte-identical; failing check named; unsigned gate_weakening refuses;
  malformed verdict degrades to refuse (not a crash); end-to-end `__mark_complete__`/`__mark_fixed__`
  fixtures (11 tests total, `test_gate_verdict_ok_*` + `test_apply_pseudo_mark_{complete,fixed}_*`).
- [ ] The NEEDS_INPUT.md gate-weakening round (`written_by: harness-change-gate`) authored by the
  cycle agent per the component (D4/D7) — prose, no state-machine change. Not exercised this pass
  (no live gate-weakening hit occurred); the wiring is in place and covered by the unsigned/signed
  override fixtures above.

**Runtime Verification** *(NOT by the implementation agent):*
- [x] Scoped item without a verdict refuses; a signed override completes; out-of-scope byte-identical.
  *(Evidence: `test_lazy_core.py -k "gate_verdict_ok or mark_complete_refuses_scoped_change_missing_gate_verdict or mark_complete_succeeds_with_clean_gate_verdict or mark_fixed_refuses_scoped_change_missing_gate_verdict"` — 11 passed.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2 (checker + verdict schema).

**Files likely modified (STATE lane):** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`,
possibly `user/skills/_components/completion-integrity-gate.md` (prose precondition mirror).

**Testing Strategy (STATE lane):** Hermetic `test_lazy_core.py` fixtures with a temp item dir + a fake
manifest + a written/absent/failing `GATE_VERDICT.md`; parity audit after the coupled-pair edit.

**Integration Notes for Next Phase — EXACT WANTED SHIP-SEAM DIFF:**

```python
# lazy_core.py — new helper (place near evaluate_completion_evidence, ~line 3121)
def gate_verdict_ok(spec_path: Path, repo_root: Path) -> dict:
    """anti-overfit-design-gate D3 ship seam. Pure read. Refuse a scoped item whose
    GATE_VERDICT.md is missing, has any `fail` check, or has an unsigned gate_weakening hit.
    Scope is re-derived from the item's commit set against the manifest (NOT trusted from the
    verdict). Out-of-scope / no-manifest → {ok: True, in_scope: False}."""
    manifest = _load_control_surface_globs(repo_root)          # reads docs/gate/control-surfaces.json
    if manifest is None:
        return {"ok": True, "in_scope": False, "reason": "no control-surface manifest"}
    changed = _item_commit_touched_files(spec_path, repo_root) # bracket ledger ∪ message-grep fallback
    hits = [f for f in changed if any(_manifest_glob_match(f, g) for g in manifest)]
    if not hits:
        return {"ok": True, "in_scope": False, "reason": "out of scope"}
    verdict = spec_path / "GATE_VERDICT.md"
    if not verdict.exists():
        return {"ok": False, "in_scope": True, "reason": "scoped change missing GATE_VERDICT.md"}
    fm = parse_sentinel(verdict)                               # existing reader; kind: gate-verdict
    checks = (fm.get("checks") or {})
    if any(v == "fail" for v in checks.values()):
        bad = [k for k, v in checks.items() if v == "fail"]
        return {"ok": False, "in_scope": True, "reason": f"GATE_VERDICT.md failing check(s): {bad}"}
    if checks.get("gate_weakening") == "hit-signed" and not fm.get("override"):
        return {"ok": False, "in_scope": True, "reason": "gate_weakening hit lacks operator override"}
    return {"ok": True, "in_scope": True, "reason": "gate verdict clean"}

# apply_pseudo __mark_complete__/__mark_fixed__ block — insert AFTER the existing
# NEEDS_INPUT_PROVISIONAL.md refusal (~line 5115), BEFORE the evidence-gated auto-tick:
        if not resuming:
            _gv = gate_verdict_ok(spec_path, repo_root)
            if not _gv["ok"]:
                return _refused(
                    f"harness-change design gate: {_gv['reason']} — author/repair "
                    "GATE_VERDICT.md (see _components/harness-change-gate.md) before completion"
                )
```

Helpers `_load_control_surface_globs` / `_manifest_glob_match` port `harness-gate.py`'s
`load_manifest` / `_glob_match` (or import them). `_item_commit_touched_files` reuses the existing
`lazy-commit-brackets.jsonl` union already used by `write_provenance` (derivation `commit-brackets`
primary, `message-grep` fallback). Mirror the insertion in BOTH the `__mark_complete__` and
`__mark_fixed__` arms (they share the block) — parity-audited.

---

### Phase 4: Delegation + self-audit

**Phase kind:** integration

**Scope:** `/harden-harness` Step 3 delegates smell detection to the checker (spin-off + never-block
protocol unchanged); the gate's own KPI rows + intervention record (D6); doc rows.

**Deliverables:**
- [x] `/harden-harness` Step 3 over-fit detector delegates to `harness-gate.py` (single source), citing
  its output in the round; the mechanical-fix-first + never-block + spin-off protocol is UNCHANGED.
- [x] The gate's `## Intervention Hypothesis` block (D6) in SPEC.md (`signal_independence: independent`
  over a signal efficacy/retro produce) + the `## KPI Declaration` (four self-audit rows, `harness-gate`
  source registered in `kpi-scorecard.py`).
- [x] Docs: root `CLAUDE.md` (scripts-table row + key-components bullet), `user/scripts/CLAUDE.md`
  (script-table row).
- [x] **KPI registry-row residency (state-batch-5).** The four drafted rows are inserted into
  `docs/kpi/registry.json` (`kpi-scorecard.py --lint` exit 0; `test_kpi_scorecard.py`'s row-count
  pin updated 12 → 16). The `harness-gate` selector COMPUTE itself is still not wired (no collector
  reads `hit-rate`/`override-rate`/`false-positive-rate`/`verdict-efficacy-disagreement` yet) —
  the rows render honest NO-DATA (`no computation registered for 'harness-gate'/...`), never a
  fabricated zero, exactly as this row's own `notes` field records. Wiring the collector remains a
  follow-up.

**Minimum Verifiable Behavior:** `/harden-harness` Step 3 names the checker; `--lint --spec` on this
SPEC exits 0; `lint-skills.py` clean after the harden-harness prose edit.

**Runtime Verification** *(NOT by the implementation agent):*
- [x] Harden-harness cites the checker; the SPEC KPI declaration lints clean. *(Evidence:
  `SKIP_MCP_TEST.md` — `kpi-scorecard.py --lint --spec` exit 0 + `lint-skills.py` clean.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2 (checker + component).

**Files likely modified:** `user/skills/harden-harness/SKILL.md`,
`docs/features/anti-overfit-design-gate/SPEC.md`, `user/scripts/kpi-scorecard.py`, `CLAUDE.md`,
`user/scripts/CLAUDE.md`.

**Testing Strategy:** Projection + skill lint; `--lint --spec` for the KPI declaration.
