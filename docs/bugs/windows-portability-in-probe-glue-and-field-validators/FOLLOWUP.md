# Out-of-repo follow-up — AlgoBooth `check-docs-consistency.ts` CRLF tolerance (Symptom B primary)

> **Origin:** this bug — `docs/bugs/windows-portability-in-probe-glue-and-field-validators/`
> (SPEC.md Symptom B; PHASES.md Phase 3). The fix below CANNOT land in claude-config —
> it lives in the **AlgoBooth** repo. This record is the doc-only disposition (b) of the
> Phase-3 spin-off contract; the reverse-reference back to this record lives in this bug's
> `PHASES.md` → Implementation Notes.

## What

Make AlgoBooth's docs-consistency field validators tolerant of a trailing carriage
return (`\r`) on frontmatter values, so legitimately-correct CRLF-authored
sentinel / plan values stop being rejected.

## Where (out-of-repo — AlgoBooth)

- **Target file:** `scripts/check-docs-consistency.ts` (AlgoBooth repo root — the gate behind
  the `qg:docs-consistency` quality gate; see
  `repos/algobooth/.claude/skill-config/docs-consistency-rules-pending.md`).
- **Root cause:** the validator parses frontmatter by splitting on `\n` only, leaving a
  trailing `\r` on each value when the file was authored/edited with CRLF line endings.
  The date / enum / integer field-type checks then compare a `\r`-suffixed string against
  their pattern and reject it.

## The fix

`.trim()` (or explicitly strip a trailing `\r`) from EACH frontmatter value BEFORE the
date / enum / integer field-type validation runs. This converges the TS validator onto
claude-config's already-correct CRLF-safe behavior.

- **Convergence target:** claude-config's `user/scripts/lazy_core.py::parse_sentinel` already
  uses `raw.splitlines()`, which strips BOTH `\r\n` and `\n` terminators, so a trailing `\r`
  is gone before any field-type check. The AlgoBooth TS validator should mirror this.

## Evidence (the three field-validator rejections — from this bug's SPEC, session `f2437fdb` 2026-06-08)

| Field type | Rejected value | Validator message |
|-----------|----------------|-------------------|
| date      | `"2026-05-18\r"` | `plan 'created' must match YYYY-MM-DD, got "2026-05-18\r"` |
| enum      | `"lazy\r"`       | `field 'skipped_by' must be one of {lazy \| lazy-cloud}, got "lazy\r"` |
| integer   | `"11\r"` / `"13\r"` | `total_count must be an integer, got "11\r" / "13\r"` |

## Why it cannot land here

claude-config's own readers are already CRLF-safe (`splitlines()`); there is nothing to fix
on the claude-config side beyond the Symptom-A probe-glue hardening (Phase 1) and the
`fix-line-endings.ps1` hook-wiring doc reconcile (Phase 2), both of which DID land in this bug.
The validator change is an AlgoBooth-repo edit + PR.

## Enqueue note

No AlgoBooth `docs/bugs/queue.json` is reachable from this repo's bug pipeline at execution
time (checked 2026-06-19 — `~/source/repos/algobooth/docs/bugs/queue.json` absent), so the
doc-only record is the baseline that lands. A future session WITH a reachable AlgoBooth bug
queue may `--enqueue-adhoc --type bug` this item into that queue and cross-reference it back
here — but this record always stands.
