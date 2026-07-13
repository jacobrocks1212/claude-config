# Research Summary — Bug-Queue Aging Backpressure

Inline recon (no Gemini sprint — this repo has negligible research volume per
`docs/bugs/CLAUDE.md`), re-verified against HEAD at implementation time (2026-07-13).

## `bug-state.py` ordering, re-verified

- `_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "Low": 3}`, `_SEVERITY_DEFAULT = 99`
  (`bug-state.py:249-250`) — unchanged since the SPEC was drafted.
- `load_bug_queue(repo_root)` (`bug-state.py:442`): queue.json-listed entries appear FIRST in
  listed order (severity does **not** reorder them relative to each other); auto-discovered
  on-disk dirs are appended, sorted by `(severity_rank, discovered_date)` via
  `_find_open_bug_dirs`. This means: a queue.json entry's OWN severity never changes its position
  relative to other LISTED entries — age-escalation only matters for (a) the cross-pipeline
  merged view (`lazy_core.merged_priority`/`merged_worklist`/`next_merged`, used by
  `--next-merged`) and (b) the relative order of UNLISTED auto-discovered dirs.
- `docs/bugs/queue.json` (real, as of 2026-07-13): only 4 entries remain (down from the SPEC's
  "11 remaining" / "23 Concluded" snapshot — substantial drain happened between SPEC authoring
  and this implementation pass, per git log `fix(state-batch-2..5)` commits). 2 entries carry
  `severity: null` with **no** pin metadata (pre-dating this feature); 2 carry explicit `P2`.
  Real-time scan (`kpi-scorecard.py::_sel_*`) shows 13 days oldest-open-bug-age and 5
  Concluded-unfixed, both down from the SPEC's captured baselines (17d / 23) — confirms outflow
  DID occur even before this feature's backpressure mechanism landed (organic drain from a
  concurrent hardening push), but the underlying defect (no *forcing* function) is unchanged.

## The aging model — the key design resolution

The SPEC's own Phase-1 "Proven done" bullet ("a 3-week-old null-severity bug outranks a tier-2
feature but never a P0") is only satisfiable if age-escalation for a null/unrecognized severity
starts from the bug's **real declared severity** (its SPEC's own `**Severity:**` line), not from
the literal `MERGED_PRIORITY_DEFAULT = 99` sentinel — 99 minus a few weekly notches never gets
anywhere near a tier-2 feature's rank. This reframes D1+D2 as one mechanism:

- An EXPLICIT queue severity always age-escalates from its own rank.
- A `severity: null` entry: if a pin is ACTIVE (`pinned_at` present, not expired per D2-A), it
  stays fully suppressed (`MERGED_PRIORITY_DEFAULT`) — no escalation, honoring the pin's intent
  (e.g. "untestable off Windows, don't dispatch yet"). Once the pin EXPIRES, the merged view
  falls back to the bug's SPEC `**Severity:**` and resumes age-escalating from there.
- A `severity: null` entry with **no** `pinned_at` at all (every entry committed to the real repo
  before this feature shipped) is **byte-identical to today** — permanent `MERGED_PRIORITY_DEFAULT`,
  no fallback, no escalation. This is a deliberate v1 scope narrowing (recorded in SPEC.md's
  Locked Decisions): it avoids silently un-suppressing the two real Windows-only build-queue bugs
  the 2026-07-04 pin was protecting from dispatch on a non-Windows host, without requiring the
  full host-capability-registry integration the SPEC's Open Question flags as future work. Only
  bugs newly pinned via the sanctioned `bug-state.py --pin` mutation participate in the
  expiry/fallback/aging mechanism going forward.

## Verified formula (fixture-proven, see test_lazy_core.py)

`age_escalated_rank(base_rank, discovered, today)`: one notch toward 0 per 7 days since
`discovered`, floored at rank 1 (P1-equivalent — a genuine P0, rank 0, is `<=` the floor and
therefore never escalated-into by another bug). Example: a P2 bug (rank 2) discovered 21 days ago
→ 3 notches → 2-3=-1 → clamped to floor 1 → beats a tier-2 feature (rank 2) but never a P0.

## Locked Decisions

See `SPEC.md`'s `## Locked Decisions` section (D2/D3/D4 mechanical, auto-accepted per
recommendation; D1 product-behavior, provisionally accepted per the operator's park-provisional
protocol — `NEEDS_INPUT_PROVISIONAL.md`).
