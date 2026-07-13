# Implementation Phases — Bug-Queue Aging Backpressure

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
D1 provisionally accepted per `NEEDS_INPUT_PROVISIONAL.md` — completion is mechanically blocked
until ratified)

**MCP runtime:** not-required — pure claude-config harness mechanics (state-script functions, CLI
subcommand, KPI selectors, queue-doc rendering). No Tauri app, no MCP-reachable surface.
Validation is `pytest` (`user/scripts/test_lazy_core.py`, `user/scripts/test_lazy_queue_doc.py`,
`user/scripts/test_kpi_scorecard.py`), both state scripts' in-file `--test` smoke harnesses,
`lazy_parity_audit.py`, `kpi-scorecard.py --lint`, `doc-drift-lint.py`, and `cli_surface_gen.py
--check`. Same untestable-by-MCP class as `friction-kpi-registry` → `SKIP_MCP_TEST.md` at the MCP
gate.

---

### Phase 1 — Age-escalation + severity-default aging

**Phase kind:** implementation

- [x] `lazy_core.age_escalated_rank(base_rank, discovered, today=None)` — pure escalation formula:
  one notch toward 0 per 7-day quantum since `discovered`, floored at rank 1 (P1-equivalent — a
  genuine P0 is never escalated past). Fail-open on absent/unparseable `discovered`, a
  future-dated discovery, or a `base_rank` already at/past the floor. `<!-- verification-only -->`
- [x] `lazy_core.merged_priority`'s bug branch age-escalates an explicit recognized severity
  always; a `severity: null` entry with an ACTIVE pin (`pinned_at` set, `lazy_core.pin_is_active`)
  stays suppressed at `MERGED_PRIORITY_DEFAULT`; past pin expiry (or no `pinned_at` at all — the
  legacy byte-identical case), see Phase 2.
- [x] `bug-state.py::_find_open_bug_dirs`'s sort key mirrors the same age term
  (`lazy_core.age_escalated_rank`) so autodiscovered-dir ordering agrees with the merged view —
  the "Bug-side mirror" touch point.
- [x] `today` threaded as an optional keyword through `load_bug_queue`, `_find_open_bug_dirs`,
  `merged_priority`, `merged_worklist`, `next_merged` — additive, backward-compatible (production
  omits it; tests inject a fixed date).

**Evidence:** `test_age_escalated_rank_*` (quantum math, floor cap, P0 no-op, absent/malformed/
future-dated discovered fail-open), `test_merged_priority_bug_*` (explicit-severity escalation,
tier-2-feature-beaten-but-not-P0 fixture) in `user/scripts/test_lazy_core.py`.
`<!-- verification-only -->`

**Locked decision:** D1 (comparator escalation vs. run quota) is `product-behavior` —
implemented against recommendation A, **provisionally accepted** pending operator ratification
(`NEEDS_INPUT_PROVISIONAL.md`). D3 (Discovered wall-clock age signal) is `mechanical-internal`,
locked as recommended.

---

### Phase 2 — Pin lifecycle + queue-doc surfacing

**Phase kind:** implementation

- [x] `lazy_core.pin_is_active(pinned_at, pinned_until, today=None)` — true iff a pin is still
  suppressing (unexpired `pinned_until`, or within the 90-day default max pin age from
  `pinned_at` when `pinned_until` is absent); false when never pinned or expired.
- [x] `bug-state.py::pin_bug_severity(repo_root, bug_id, *, until=None, reason=None, today=None)` —
  the sanctioned mutation: sets `severity: null` + `pinned_at` (script-stamped) +
  `pinned_until`/`pin_reason` on an existing or newly-created (appended) `docs/bugs/queue.json`
  entry. Validates `until` (ISO date, `_die` on malformed); refuses on an unknown bug id. Wired as
  CLI `--pin --id <id> [--until YYYY-MM-DD] [--reason TEXT]`, gated by
  `refuse_if_cycle_active("--pin")` (orchestrator-only, exit 3 for a cycle subagent).
- [x] `load_bug_queue` (both queued + on-disk entries) now populates `discovered`/`spec_severity`/
  `pinned_at`/`pinned_until` on every returned bug item, so `merged_priority`'s fallback-past-
  expired-pin branch has what it needs without re-reading files.
- [x] `lazy_core.bug_priority_marker(...)` — renders `"📌 pinned <date>"` (active pin) /
  `"⏫ escalated"` (effective priority below the declared severity) / `""` for the queue-doc.
- [x] `lazy-queue-doc.py`'s bug table gains an "aging" column: the SPEC's `**Discovered:**` date +
  the pin/escalation marker (`_bug_aging_cell`). Features table is unchanged (4 columns; no
  `**Discovered:**` analog). Byte-stability contract restated: byte-identical for unchanged
  (state, date) — the marker is itself a function of `today`.
- [x] No `--unpin` subcommand added — restore-by-removing-the-entry is already the sanctioned path
  (`bug-state.py --reorder-queue --id <id> --to remove`), unchanged by this feature.

**Evidence:** `test_pin_is_active_*` (active/expired-until/expired-default-age/never-pinned/
malformed-date fail-open), `test_pin_bug_severity_*` (update existing entry, create new entry,
malformed `--until` refuses with zero mutation, unknown bug id refuses) in
`user/scripts/test_lazy_core.py`; `test_bug_priority_marker_*` and the queue-doc "aging" column
tests in `user/scripts/test_lazy_queue_doc.py` (incl. a byte-stability regression: two same-day
renders of unchanged state are identical). `<!-- verification-only -->`

**Locked decision:** D2 (pin expiry + fallback to SPEC severity) and D4 (queue-age surfacing) are
`mechanical-internal`, both locked as recommended.

---

### Phase 3 — KPI selectors + registry rows

**Phase kind:** implementation

- [x] `kpi-scorecard.py`'s closed `_SOURCES["sentinel-scan"]` enum gains
  `oldest-open-bug-age-days` and `concluded-unfixed-count`.
- [x] `_iter_open_bug_dirs(repo_root)` — shared scan helper (non-`_archive` `docs/bugs/<slug>/`
  dirs with a `SPEC.md`; reads `**Status:**`/`**Discovered:**` header lines).
- [x] `_sel_oldest_open_bug_age_days(repo_root, *, today=None)` — max age (days) over open
  (non-Fixed/Won't-fix) dirs with a parseable `**Discovered:**`; honest NO-DATA when no open bugs
  exist or none carry a parseable date (never a fabricated age).
- [x] `_sel_concluded_unfixed_count(repo_root)` — count of dirs at `**Status:** Concluded`.
- [x] Both selectors wired into `compute_reading`'s dispatcher under `source == "sentinel-scan"`.
- [x] The two drafted `docs/kpi/registry.json` rows (`bug-backlog-oldest-open-age-days`,
  `bug-backlog-concluded-unfixed-count`) promoted from the SPEC's `jsonc` fences (now `json`);
  `--lint` and `--lint --spec docs/features/bug-queue-aging-backpressure/SPEC.md` both exit 0.
  `docs/kpi/SCORECARD.md` regenerated (renders both PENDING-BASELINE with live values — 13d /
  5, down from the 2026-07-11 captured baselines of 17d / 23, confirming organic drain already in
  progress).

**Evidence:** `test_sel_oldest_open_bug_age_days_*` / `test_sel_concluded_unfixed_count_*` (empty
tree, no-Discovered exclusion, Fixed/Won't-fix exclusion, Concluded counting) in
`user/scripts/test_kpi_scorecard.py`; live `--lint` + `--lint --spec` + `--stdout` runs against the
real committed registry. `<!-- verification-only -->`

---

## Cross-cutting gates (run once, cover all three phases)

- [x] `python -m pytest user/scripts/test_lazy_core.py user/scripts/test_lazy_queue_doc.py
  user/scripts/test_kpi_scorecard.py -q` — all green.
- [x] `python user/scripts/lazy-state.py --test` / `python user/scripts/bug-state.py --test` —
  both green, baselines unchanged (no new `--test` fixtures added by this feature — the new
  functions are covered by `test_lazy_core.py`/`test_kpi_scorecard.py`'s pytest suites instead,
  matching how sibling helper functions like `reorder_queue`/`sync_deps` are covered).
  `<!-- verification-only -->`
- [x] `python user/scripts/lazy_parity_audit.py --repo-root .` — exit 0 (`--pin` is a justified
  bug-pipeline-only divergence, like `--fsck`; no `lazy-state.py` mirror owed).
  `<!-- verification-only -->`
- [x] `python user/scripts/kpi-scorecard.py --lint` — exit 0. `<!-- verification-only -->`
- [x] `python user/scripts/doc-drift-lint.py --repo-root .` — exit 0. `<!-- verification-only -->`
- [x] `python user/scripts/cli_surface_gen.py --check` — exit 0 (regenerated after the `--pin`/
  `--until` CLI additions). `<!-- verification-only -->`
