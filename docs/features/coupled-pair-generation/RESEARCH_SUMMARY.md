# Research Summary — Coupled-Pair Generation

> Inline recon (in place of Gemini research — negligible external-research volume; this is a
> repo-internal mechanization feature). All numbers are live measurements against the working
> tree on 2026-07-12, produced by a throwaway recon script that reuses the audit's exact
> `apply_tokens` + `^#{2,3} .*$` heading model.

## The parity manifest's heading model (build-input inventory)

`user/scripts/lazy-parity-manifest.json` (753 lines) already carries, per pair:
`canonical` / `derived` / `token_substitutions` (ordered literal+regex-escaped subs) /
`mechanic_set` / `mechanic_overrides` / `headings[]` (per-heading `coverage ∈ {restated,
divergence, inherited}` + an `evidence` regex or a `reason`). `lazy_parity_audit.py` C1–C6 are
ALL regex-presence checks (its own docstring L4–10): C2 verifies a heading's `evidence` regex
still *matches* in the derived file — it never compares CONTENT. A restated section can rot
arbitrarily while its evidence regex still matches; the audit catches deletion, not drift.

`apply_tokens` (audit L45–70) is the one substitution implementation — ordered, applying both
the literal canonical token and its `re.escape()` form. The generator IMPORTS it (never
re-implements it).

## Per-pair divergence inventory (measured — the decisive finding)

For each pair I split canonical + derived into heading-blocks, applied the pair's
`token_substitutions` to each canonical block, and byte-compared against the derived block.

| Pair | canonical→derived sizes | derived blocks | byte-reproducible | divergent (verbatim) | canonical blocks deleted |
|------|------|------|------|------|------|
| `lazy-bug-batch` | 256KB → 101KB | 36 | **0** | 36 | 15 |
| `lazy-batch-cloud` | 256KB → 209KB | 41 | **0** | 41 | 12 |
| `lazy-bug` | 29KB → 20KB | 19 | 2 | 17 | 1 |
| `lazy-cloud` | 29KB → 29KB | 20 | 3 | 17 | 3 |
| `lazy-bug-status` | 10KB → 9KB | 8 | 1 | 7 | 1 |

**The SPEC's central premise is empirically refuted at the byte level.** The manifest's
"restated" classification (112 of 129 headings, ~87%) means only "the heading exists and its
evidence regex matches" — NOT "the body is a token-substituted copy of the canonical." A
per-block line-diff (`difflib.SequenceMatcher`) on the pairs that DO share vocabulary shows
ratios of **0.30–0.83** with many blocks rewriting 30–80% of their lines. Even the cloud axis
(`lazy-cloud`, `token_substitutions: []`) reproduces only 3 of 20 blocks byte-for-byte.

Conclusion: the derived skills are **substantially independently-authored variants that share
heading structure**, not mechanical restatements. The "collapse 112 restatements into ~11
authored divergences" headline is therefore **not achievable** — there is no ~11-divergence
substrate hiding under a token map; the divergence surface is the near-entirety of each derived
body. This is exactly the content rot the C1–C6 regex-presence audit "provably cannot see"
(SPEC Executive Summary) — surfaced here, as SPEC D5 anticipated ("surfacing that drift is
itself a win").

## What this means for the design

- The generation *mechanism* is still buildable and byte-faithful (canonical-restate for the
  blocks that DO reproduce; verbatim-store for everything else; deletion by omission), and the
  freshness gate (regen byte-diff) is strictly stronger than C2 regex-presence — those are the
  real, deliverable mission wins ("effective / drift-proof by construction").
- But the *efficiency* headline (one-file edit; 87% of the ledger becomes machine-owned) does
  NOT land today: most blocks are `verbatim`, so editing a divergent block in the overlay is
  byte-for-byte the same work as editing the derived file. The generator is a **substrate for
  incremental re-canonicalization**, not a day-one 3-way→1-way collapse.
- This is a genuine PRODUCT fork above the mechanical-auto-accept line → recorded in
  `NEEDS_INPUT_PROVISIONAL.md` (adopt the byte-faithful substrate now; operator decides whether
  to invest in re-canonicalization vs. reframe to audit-only).

## Reused mechanisms (implemented, not sibling specs)

- `lazy_parity_audit.apply_tokens` — imported as the one substitution contract.
- `lazy_parity_audit._enumerate_headings` model (`^#{2,3} .*$`) — the generator's `split_blocks`
  uses the same regex so section boundaries match the manifest byte-for-byte.
- `project-skills.py` — the house precedent for committed-source → deterministic-expansion →
  verified-output; the generator extends the same discipline to whole-file derivation.
- CRLF line endings across all skill files → the generator reads/writes with **no newline
  translation** (`open(..., newline="")`) and stores verbatim content as `"\n"`-split line
  arrays (`"\n".join(s.split("\n")) == s` is an exact inverse for any bytes), guaranteeing
  byte-faithful round-trip (proven: `--write` leaves all 5 derived files byte-identical).
