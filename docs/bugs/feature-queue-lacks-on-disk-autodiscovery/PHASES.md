# Implementation Phases — Feature queue on-disk auto-discovery

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress

**MCP runtime:** not-required — this is a harness state-script change (`user/scripts/lazy-state.py`). It has no app/Tauri/MCP-reachable surface; it is verified entirely by the in-file `--test` smoke harness + `test_lazy_core.py`, not by the live dev runtime. (claude-config has no Tauri runtime at all.)

## Cross-feature Integration Notes

(No hard deps on Complete upstreams — this is a self-contained state-script enhancement.)

---

### Phase 1: Opt-in on-disk feature auto-discovery in `load_queue`

**Scope:** Extend `lazy-state.py::load_queue` so that, when `docs/features/queue.json` carries a top-level `"autodiscover": true` flag (sibling of `"queue"`), the in-memory work-list is merged with on-disk open feature dirs — exactly mirroring how `bug-state.py::load_bug_queue` merges `_find_open_bug_dirs`. Flag absent/false ⇒ byte-identical to today (every other repo, incl. AlgoBooth, unaffected). The merge is a **probe-time, in-memory** operation: nothing is ever written into `queue.json`. A new `_find_open_feature_dirs` helper performs the disk scan with the completed-feature exclusion filter, and a `feature_tier` helper reads `**Priority:**` for discovered-entry ordering. The `queue-missing` terminal is reconciled so an empty explicit queue plus non-empty disk discovery is NOT `queue-missing` (mirroring the bug loader's "queue is OPTIONAL" contract). Finally, enable the flag in claude-config's own `docs/features/queue.json` so claude-config opts into feature auto-discovery, and verify the additive mirror passes `lazy_parity_audit.py`.

**Deliverables:**
- [x] `feature_tier(spec_path: Path) -> int` helper in `lazy-state.py` — reads the discovered feature SPEC.md's `**Priority:**` header (`P0`→0 … `P3`→3, absent/unparseable → a default-last rank), mirroring `bug-state.py::bug_severity` shape. Used only for discovered-entry ordering. [VERIFY: grep -n "def bug_severity" user/scripts/bug-state.py]
- [x] `_find_open_feature_dirs(features_dir: Path, queued_ids: set[str]) -> list[Path]` helper in `lazy-state.py`, structurally mirroring `bug-state.py::_find_open_feature_dirs`'s analog `_find_open_bug_dirs`: scans `features_dir` one level deep; skips `_archive/` + any underscore-prefixed dir; skips dirs already in `queued_ids`; requires a `SPEC.md`; **excludes** dirs whose `**Status:**` is `Superseded` OR (`Complete` AND a valid `COMPLETED.md` receipt via `has_completion_receipt`); a `Complete`-WITHOUT-receipt dir is NOT silently skipped (surfaced for the completion gate, with a `_diag`). Sorts by `feature_tier` rank then directory name (stable). [VERIFY: grep -n "def _find_open_bug_dirs" user/scripts/bug-state.py] [VERIFY: grep -n "def has_completion_receipt" user/scripts/lazy_core.py]
- [x] `load_queue` extended: after reading `queue.json`, if `data.get("autodiscover") is True`, dedupe the explicit-entry ids and append discovered on-disk open feature dirs (NOT already queued) as discovered entries of shape `{id: <dirname>, name: <SPEC '# ' title or dirname>, spec_dir: <dirname>, tier: <feature_tier rank>, queue_entry: None}` — the SAME raw-queue-item key shape the `compute_state` walk loop consumes (`id`/`name`/`spec_dir`/`tier`). Flag absent/falsy ⇒ return the raw queue list unchanged (byte-identical). [VERIFY: grep -n "def load_queue" user/scripts/lazy-state.py] [VERIFY: grep -n "entry.get(\"spec_dir\")" user/scripts/lazy-state.py]
- [x] `queue-missing` terminal reconciliation in `compute_state` (~1350): the `if not queue:` → `queue-missing` early-return must treat the post-`load_queue` merged list as the queue, so an empty explicit `queue.json` queue + non-empty disk discovery does NOT return `queue-missing`. (Because discovery is folded INTO `load_queue`, the existing `if not queue:` check already sees the merged list — confirm no separate `queue.json`-existence short-circuit fires first; adjust the `queue-missing` notify path if the file exists but `"queue": []` + autodiscover yields a non-empty merged list.) [VERIFY: grep -n "queue-missing" user/scripts/lazy-state.py]
- [x] Enablement: set `"autodiscover": true` in `docs/features/queue.json` (claude-config repo root) so this repo opts in. [VERIFY: ls docs/features/queue.json]
- [x] Tests (`lazy-state.py --test` new fixtures): (a) **flag-off regression** — a `Draft`-SPEC feature dir present on disk but NOT in `queue.json` and NO `autodiscover` flag ⇒ invisible (byte-identical to today); (b) **flag-on discovery** — same dir WITH `autodiscover: true` ⇒ discovered and dispatched (e.g. routes to `/spec`); (c) **excludes Complete+receipt** — a `Complete` dir with a valid `COMPLETED.md` is NOT re-enqueued; (d) **surfaces Complete-without-receipt** — a `Complete` dir with NO receipt IS surfaced (→ `completion-unverified`), with a diag; (e) **dedupes explicit-entry twin** — a feature both explicitly queued AND on disk appears once (explicit entry wins, listed first); (f) **ordering** — multiple discovered dirs sort by `**Priority:**` rank then directory name; (g) **empty-explicit-queue + autodiscover** — `"queue": []` + `autodiscover: true` + one open disk dir ⇒ NOT `queue-missing`.
- [x] Re-pin both `--test` baselines: regenerate `tests/baselines/lazy-state-test-baseline.txt` (new fixtures shift output) and confirm `tests/baselines/bug-state-test-baseline.txt` is unchanged (bug-state.py untouched). Regenerate ONLY by piping live `--test` through `_normalize_smoke_output` per `user/scripts/CLAUDE.md` → Testing — never by hand.
- [x] Verify `bug-state.py` is **unchanged** and `python user/scripts/lazy_parity_audit.py` passes. The feature-only loader extension is a JUSTIFIED, additive divergence (the parity audit checks only the specific mirrored surfaces — `set_active_repo_root`, `--reorder-queue`, `--reassert-owner`, the host-capability fail-fast — none of which this change touches; it does NOT audit `load_queue`/`load_bug_queue` symmetry). Confirm the audit stays green; if it newly flags this loader, that is a finding to surface, not silently suppress.

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` is green (incl. the seven new fixtures above), and `python user/scripts/lazy_parity_audit.py` exits 0. Plus the manual repro from the SPEC: with `autodiscover: true` set in claude-config's `docs/features/queue.json`, `python user/scripts/lazy-state.py` surfaces an on-disk `docs/features/<slug>/SPEC.md` that has no `queue.json` entry (where today it returns only explicit entries / `queue-missing`).

**Runtime Verification** *(checked by integration test or manual testing):*
- [ ] (none — there is no live runtime for this repo; the `--test` smoke harness + parity audit + manual `lazy-state.py` repro above are the complete verification surface. This row is intentionally empty so no Step-9 MCP gate is implied.)

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — `load_queue` extension, new `_find_open_feature_dirs` + `feature_tier` helpers, `queue-missing` reconciliation, new `--test` fixtures + assertions.
- `docs/features/queue.json` — add `"autodiscover": true`.
- `tests/baselines/lazy-state-test-baseline.txt` — re-pinned for the new fixtures.
- (Read-only reference, NOT modified: `user/scripts/bug-state.py`, `user/scripts/lazy_core.py`, `user/scripts/lazy_parity_audit.py`.)

**Testing Strategy:**
In-file hermetic `--test` fixtures (the only fast regression net for the state machine; a refactor that keeps `--test` green has preserved behavior). Each new fixture is a temp-dir repo built by `_build_fixture` exercising one discovery branch (flag-off / flag-on / Complete-exclusion / receipt-surface / dedupe / ordering / empty-queue-non-missing). `lazy_core.has_completion_receipt` and `spec_status` are reused for the exclusion filter rather than re-implemented. Cross-script invariant: because the change is feature-only, `bug-state.py --test` and `test_lazy_core.py` must stay green untouched, and `lazy_parity_audit.py` must remain green (additive divergence, no mirrored surface removed).

**Integration Notes for Next Phase:**
- (No next phase.) Coupling Rule reminder for any follow-on: the `autodiscover` flag is **repo-local by construction** — only claude-config sets it; AlgoBooth and all other repos omit it and are byte-identical to today. Do NOT promote it to a global default without a separate decision (SPEC Open Question 2 explicitly defers that).
- The discovered-entry shape (`queue_entry: None`, raw-queue-item keys) is the integration seam: the `compute_state` walk loop reads `entry.get("spec_dir")` / `entry.get("tier")` directly, so discovered entries MUST carry those raw keys (NOT the bug loader's normalized `spec_path` key — the two loaders' return shapes legitimately differ: `load_queue` returns raw queue items, `load_bug_queue` returns normalized dicts).

---

#### Implementation Notes (2026-06-22 — Phase 1 landed; executed inline as a bug-pipeline cycle subagent)

**What shipped** (all in `user/scripts/lazy-state.py`, the single source of truth — `bug-state.py` UNCHANGED):

- `_FEATURE_TIER_DEFAULT = 99` module constant (the discovered-feature default-last rank; mirrors bug-state's `_SEVERITY_DEFAULT`).
- `feature_tier(spec_path: Path) -> int` (~line 307) — scans the SPEC.md FILE for `**Priority:** P0..P3`, maps to `0..3`, absent/unparseable → `99`. Regex `^\*\*Priority:\*\*\s*[Pp]([0-3])\b`. The signature takes the SPEC.md file path (consistent with how `_find_open_feature_dirs` calls `feature_tier(spec_md)` — mirrors `bug_severity(spec_md)`).
- `_find_open_feature_dirs(features_dir, queued_ids) -> list[Path]` (~line 333) — structural mirror of `bug-state.py::_find_open_bug_dirs`: one-level scan, skips non-dirs / `_`-prefixed dirs / already-queued ids; requires `SPEC.md`; excludes `Superseded` always and `Complete` WITH a valid `COMPLETED.md` receipt (`has_completion_receipt`); a `Complete`-WITHOUT-receipt dir is surfaced (with a `_diag`) for the downstream `completion-unverified` gate. Sorts by `(feature_tier(SPEC.md), dir name)`.
- `_queue_autodiscover_enabled(repo_root) -> bool` (~line 410) — defensive read-only check for the top-level `"autodiscover": true` flag (added for the `queue-missing` reconciliation, see below).
- `load_queue` extended (~line 425) — when `data.get("autodiscover") is True`, builds `queued_ids` from the explicit entries, calls `_find_open_feature_dirs`, and APPENDS one discovered entry per open dir of shape `{id, name (SPEC '# ' title or dirname), spec_dir, tier, queue_entry: None}` — the raw-queue-item key shape the `compute_state` walk loop reads. Flag absent/falsy ⇒ returns `items` UNCHANGED (byte-identical — the `autodiscover-off` fixture + the unchanged bug-state baseline are the proof).
- `queue-missing` reconciliation in `compute_state` (~line 1486) — the `if not queue:` early-return now short-circuits to `queue-missing` ONLY when `_queue_autodiscover_enabled` is False. With the flag on and an empty merged list (all on-disk dirs Complete+receipt / Superseded), it falls through to the normal exhaustion logic → `all-features-complete` (the bug loader's "queue is OPTIONAL" contract).

**Tests (test-first):** seven `--test` fixtures authored FIRST and confirmed RED, then implemented to GREEN — `autodiscover-off` (flag-off byte-identical), `-on`, `-excludes-complete`, `-surfaces-receiptless-complete` (→ completion-unverified), `-dedupes-explicit-twin` (+ direct `load_queue` dedup/first-position assertion), `-orders-by-priority` (+ direct P1-before-P3 ordering assertion), `-empty-queue-not-missing`. The `lazy-state` baseline was re-pinned via the `_normalize_smoke_output` pipe; the `bug-state` baseline is unchanged.

**Enablement:** `docs/features/queue.json` gained `"autodiscover": true`. Live SPEC repro confirmed: a fresh `docs/features/<slug>/SPEC.md` with no queue entry is now surfaced and dispatched to `/spec` (verified with a throwaway dir, then removed); with all real dirs Complete+receipt the probe correctly returns `all-features-complete` (no false re-enqueue — Proven Finding 2).

**Divergence from plan:** none material. The plan named the helper `feature_priority` in one SPEC table row but `feature_tier` in the deliverables/Fix-Scope; shipped as `feature_tier` (the deliverable name, and the int-tier the feature pipeline uses). Added `_queue_autodiscover_enabled` (not separately enumerated) because the `queue-missing` reconciliation needs to distinguish flag-on-empty (→ all-complete) from flag-off-empty (→ queue-missing); the plan anticipated "adjust the `queue-missing` notify path" — this is that adjustment.

**Gates:** `lazy-state.py --test` green (incl. 7 new fixtures); `bug-state.py --test` green (baseline unchanged); `test_lazy_core.py` 770 passed / 0 failed; `lazy_parity_audit.py --repo-root .` exit 0 (additive feature-only loader extension is a JUSTIFIED divergence — the audit does not mirror `load_queue`/`load_bug_queue` symmetry).

**Review verdict:** PASS — inline review (single-file change, test-first RED→GREEN confirmed, flag-off byte-identical proven, discovered-entry key shape matches the walk loop, no `queue.json` written by the discovery path).
