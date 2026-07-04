---
kind: implemented
feature_id: stub-spec-route-loops-until-queue-stub-cleared
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [bffdae0, 380c57e, c138fc7, bf208c9, 55980db, 189083f]
decisions: []
---

# Implementation Ledger

**What shipped:** When a feature is marked a stub via `queue.json` `"stub": true`, `lazy-state.py` routes it to `Step 4.5: stub-spec detected` and dispatches `/spec` to shape the baseline. But `/spec`'s Phase-1 `--batch` contract only drafts/locks the baseline SPEC — it does not clear the `queue.json` `stub` flag. So a stub-shaping cycle that drafts the baseline, commits, and returns leaves `is_stub_spec()` still true (it keys on `queue_entry.get("stub") is True`), and the next probe re-routes to Step 4.5 again. The loop is *commit-masked*: HEAD advances each cycle (`repeat_count` resets to 1) while routing never leaves the step (`step_repeat_count` climbs) — the exact "productive-looking oscillation" signature the step counter exists to catch.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
