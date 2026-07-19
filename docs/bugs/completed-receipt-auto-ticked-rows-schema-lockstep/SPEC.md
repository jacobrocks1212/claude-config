# Bug: `auto_ticked_rows` on COMPLETED.md receipts is undocumented in the canonical sentinel schema

> The `__mark_complete__` completion gate writes an `auto_ticked_rows` frontmatter
> field onto every gated `COMPLETED.md` receipt, but the canonical schema doc
> `user/skills/_components/sentinel-frontmatter.md` never listed it as an optional
> key. Downstream strict validators that mirror the schema flag the field as an
> unknown key.

**Status:** Concluded

**Discovered:** 2026-07-19 (manual `/harden-harness`, operator-directed)
**Kind:** doc/schema-lockstep defect (harness)
**Root-cause class:** missing-contract

## Symptom

AlgoBooth's `scripts/check-docs-consistency.ts` — which mirrors the canonical
`SENTINEL_SCHEMAS` and enforces strict `sentinel-unknown-keys` validation — fired
`sentinel-unknown-keys` warnings on ~54 gated `COMPLETED.md` receipts under
`docs/features/**/`, one per receipt carrying `auto_ticked_rows`.

## Root cause (confirmed)

The receipt writer `write_completed_receipt` (`user/scripts/lazy_core/gates.py:1932`)
emits `auto_ticked_rows: <int>` whenever the caller passes a non-`None` value. The
completion pseudo-skill `apply_pseudo` (`user/scripts/lazy_core/pseudo.py`) always
passes it on the gated path: `auto_ticked_rows` is initialized to `0`
(`pseudo.py:1210`), set from the auto-tick result (`pseudo.py:1226`), and passed to
the writer (`pseudo.py:1400`). It is therefore present (value ≥ 0) on **every**
`provenance: gated` receipt, and omitted only on `--backfill-receipts` (which never
passes it).

The canonical schema section `#### COMPLETED.md — kind: completed`
(`sentinel-frontmatter.md`) documented four required keys plus the optional
`completed_commit` / `validated_via` / `mcp_pass_count` / `mcp_total_count`, but NOT
`auto_ticked_rows`. The field was added to the writer during
`completion-coherence-gate-reconciliation` Phase 3 without a lockstep update to the
canonical schema doc — so the doc and the writer diverged, and any strict mirror of
the schema treats the emitted field as unknown.

### Writer/schema contract audit (holistic — every emitted key)

`write_completed_receipt` emits exactly these frontmatter keys; all but the last are
already in the canonical schema:

| Key | Canonical schema | Status |
|-----|------------------|--------|
| `kind` | required | documented |
| `feature_id` | required | documented |
| `date` | required | documented |
| `provenance` | required | documented |
| `completed_commit` | optional | documented |
| `validated_via` | optional | documented |
| `mcp_pass_count` | optional | documented |
| `mcp_total_count` | optional | documented |
| `auto_ticked_rows` | optional | **MISSING — this bug** |

`auto_ticked_rows` is the ONLY emitted-but-undocumented field. No other gap.

## Fix scope

1. Add `auto_ticked_rows` (optional, integer) to the `COMPLETED.md` schema's
   optional-keys list in the canonical `sentinel-frontmatter.md`, matching how
   AlgoBooth's already-fixed `check-docs-consistency.ts` documents it (`optional` +
   `intFields`).

## Notes / adjacent surfaces (out of scope, recorded)

- The AlgoBooth-side fix (adding `auto_ticked_rows` to `optional` + `intFields` of
  `SENTINEL_SCHEMAS['COMPLETED.md']` in `scripts/check-docs-consistency.ts`) is
  already committed in the AlgoBooth repo — NOT re-done here (Prohibition #1).
- `write_completed_receipt` is shared: `bug-state.py` calls it with `kind="fixed"`
  to write `FIXED.md` receipts, so a `FIXED.md` receipt can ALSO carry
  `auto_ticked_rows`. But (a) the canonical `sentinel-frontmatter.md` documents no
  `FIXED.md` field schema, and (b) AlgoBooth's `scripts/check-bugs-consistency.ts`
  does NOT perform a strict `sentinel-unknown-keys` check on `FIXED.md` (it only
  asserts `kind === 'fixed'`), so no unknown-key warning fires there. No cross-repo
  obligation created.
- `AlgoBooth-lanes/wt-00|01|02` are git worktrees of the AlgoBooth project, not
  independent repos; they inherit the AlgoBooth fix on merge/rebase and are out of
  harness scope.
