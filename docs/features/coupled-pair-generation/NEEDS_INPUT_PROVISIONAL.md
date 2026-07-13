---
kind: needs-input
feature_id: coupled-pair-generation
decisions:
  - id: D-PREMISE
    summary: Derived skills are independently-authored variants, not token-copies — the SPEC's "collapse 112 restatements into ~11 divergences" efficiency headline is not achievable; how far to invest.
divergence: product
audit_divergence: SPEC premise (derived = canonical × token map × ~11 overlays) refuted by byte-level measurement; efficiency claim reframed, mechanism delivered byte-faithful.
written_by: coupled-pair-generation-implementer
---

# Provisional decision — coupled-pair-generation

Recorded under the overnight park-provisional protocol (never halt). The mechanism is fully
implemented and gate-green (Phases 1–3); this feature is NOT marked Complete pending the operator
decision below.

## Decision Context

### D-PREMISE — the SPEC's efficiency premise is empirically refuted

The SPEC's Executive Summary and D5 assume the 112 `restated` manifest headings are
"manually-duplicated prose ... a token-substituted copy of the canonical," so generation would
"collapse 112 restatements into ~11 authored divergences." I measured this directly (see
`RESEARCH_SUMMARY.md`): splitting each pair into heading-blocks, token-substituting the canonical,
and byte-comparing against the derived shows **0–3 of N blocks reproduce**, with per-block
line-diff ratios of **0.30–0.83**. Even the cloud axis (`lazy-cloud`, zero token subs) reproduces
only 3/20 blocks. The `restated` classification is a *regex-presence* claim (the heading exists and
its evidence matches), NOT a byte-level copy claim.

Consequence: there is no ~11-divergence substrate under a token map. The divergence surface is the
near-entirety of each derived body, so most blocks extract as `verbatim`. The byte-faithful
generator + freshness gate (the "effective / drift-proof by construction" mission win) IS delivered
and real. But the "efficient" headline (one-file edit; 87% of the ledger machine-owned) does NOT
land today — editing a `verbatim` block in the overlay is byte-for-byte the same work as editing the
derived file. The generator is a **substrate for incremental re-canonicalization**, not a day-one
3-way→1-way collapse.

**Options considered.**
- **(a) Adopt the byte-faithful substrate now [CHOSEN provisionally].** Ship the generator, the
  5 extracted overlays, the `--check` drift gate, and the tests. Keep `lazy_parity_audit.py` C1–C6
  green and unchanged (do NOT demote yet — it still provides value and its removal buys nothing
  while the verbatim surface is large). Keep derived files byte-identical (no provenance headers
  yet). This delivers the drift-proof audit substrate and makes the true divergence surface
  visible/measured, with zero runtime risk. Re-canonicalization (converting `verbatim`→`canonical`,
  porting one-file bug-fixes to the canonical) is the actual efficiency work and is deferred as
  Phase 4 editorial judgment.
- **(b) Reframe to audit-only.** Drop the generator; only add a content-drift audit. Rejected —
  a content-drift audit needs a byte-faithful regeneration source, which is exactly what the
  generator + overlays provide; (b) is a strict subset of (a).
- **(c) Abandon.** Rejected — the drift-proofing win is real and low-risk.

**Recommendation:** (a). It satisfies the "effective / drift-proof" mission criterion immediately
and honestly, defers the "efficient" claim to the re-canonicalization campaign, and takes zero
runtime risk (derived files byte-identical; audit untouched).

Also fold into the resolution: (i) the KPI reframe — the `parity-restated-heading-entries` row's
"target 0 restated" is not the day-one outcome; retarget it to the measurable
`generate-coupled-skills.py --report` verbatim-block count and treat re-canonicalization as the
KPI-moving work; (ii) whether to invest in the Phase-4 audit demotion (SPEC D3/D4) + provenance
headers (SPEC D2) at all, given they only pay off after the verbatim surface shrinks.

## Resolution

resolved_by: auto-provisional
decision_commit: 7a503f808eb9c0c7ef135078e03e9064b0a7ef9c

- **D-PREMISE — Choice:** (a) adopt the byte-faithful substrate now; keep C1–C6 green/unchanged;
  keep derived files byte-identical; defer audit demotion, provenance headers, and the
  re-canonicalization campaign to Phase 4 pending operator ratification. Implemented in full this
  session (generator + 5 overlays + `--check` drift gate + 34 tests, all gates green).
