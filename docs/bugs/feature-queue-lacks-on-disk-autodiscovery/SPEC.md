# Feature queue lacks bug-style on-disk auto-discovery — Investigation Spec

> `bug-state.py` auto-discovers open bug dirs on disk (hybrid load over `docs/bugs/queue.json`), but `lazy-state.py` reads features **only** from `docs/features/queue.json` — so a new `docs/features/<slug>/SPEC.md` is inert until explicitly `--enqueue-adhoc`'d. The operator wants claude-config opted into feature auto-discovery, mirroring bugs.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-22
**Placement:** docs/bugs/feature-queue-lacks-on-disk-autodiscovery
**Related:** `user/scripts/CLAUDE.md` → "What the lazy system is" / Coupling Rule; `bug-state.py::load_bug_queue` + `_find_open_bug_dirs` (the mirror target); `lazy-state.py::load_queue`; `lazy_parity_audit.py::audit_state_script_parity` (coupled-pair guard); `docs/features/mobile-queue-control` (the feature whose manual enqueue surfaced this)

---

## Verified Symptoms

1. **[VERIFIED]** A new `docs/features/<slug>/SPEC.md` does NOT enter the `/lazy-batch` work-list on its own — it must be explicitly added to `docs/features/queue.json` (e.g. via `--enqueue-adhoc`). Directly observed this session: `mobile-queue-control` had a finished SPEC on disk yet required a manual `lazy-state.py --enqueue-adhoc` to be picked up.
2. **[VERIFIED]** Bugs already behave the way the operator wants for features — `docs/bugs/<slug>/SPEC.md` is auto-discovered without a `queue.json` entry. (Operator's stated premise; confirmed in source — see Evidence.)
3. **[REPORTED]** The operator wants this auto-discovery for features **only in claude-config**, not globally — other repos (AlgoBooth) keep explicit feature enqueue.

## Reproduction Steps

1. In claude-config, create `docs/features/<slug>/SPEC.md` (no `queue.json` entry).
2. Run `python user/scripts/lazy-state.py` (or `/lazy-status`).

**Expected (desired):** the feature appears in the work-list and `/lazy-batch` processes it, exactly as a new `docs/bugs/<slug>/SPEC.md` would.
**Actual:** the feature is invisible to the pipeline; `load_queue` returns only `queue.json` entries (or `queue-missing` when the queue is empty).
**Consistency:** Always.

## Evidence Collected

### Source Code

The asymmetry is real and lives in two **separate, per-script** loaders (NOT shared in `lazy_core`):

- **Bugs auto-discover** — `bug-state.py::load_bug_queue` (~lines 291–383) merges `queue.json` entries with `_find_open_bug_dirs` (~422–479): any `docs/bugs/<slug>/` with a `SPEC.md` is included, sorted by `**Severity:**` rank (P0→P1→P2→Low) then `**Discovered:**` date. Excludes `_archive/` + underscore-prefixed dirs, `Status: Won't-fix`, and `Status: Fixed` **with** a `FIXED.md` receipt. A receiptless `Fixed` is NOT skipped (surfaces for the completion gate). Docstring states "The queue is OPTIONAL."
- **Features do not** — `lazy-state.py::load_queue` (~lines 307–320) reads **only** `docs/features/queue.json`; empty/absent ⇒ `terminal_reason: queue-missing` in `compute_state` (~1350–1355). The other `features_root.glob("**/SPEC.md")` calls are for upstream-dependency resolution (`resolve_upstream_dir`) and `backfill_receipts` — never for queue loading.

### Related Documentation

- No explicit rationale for the asymmetry exists in code/docs. It is an inferred-deliberate design choice: a half-drafted `docs/features/<slug>/` (created mid-`/spec`) shouldn't auto-start, whereas a bug doc on disk is by definition open work. This means the fix is an **enhancement** (opt-in), not a regression repair — hence the per-repo opt-in scoping.
- `.claude/skill-config/` exists in claude-config (`capabilities.txt`, `commit-policy.md`, `quality-gates.md`) but the state scripts do **not** read it today.

## Proven Findings

1. **Root cause:** `lazy-state.py::load_queue` has no on-disk discovery; only `bug-state.py` does. Confirmed at source.
2. **Load-bearing constraint — completed features must be excluded.** `docs/features/` holds ~9 dirs, almost all `Status: Complete` with a `COMPLETED.md` receipt (completed feature dirs are not archived; they stay on disk). Naïve "scan every `SPEC.md`" would re-enqueue finished work. Discovery MUST exclude `Complete`+receipt / `Superseded`, mirroring the bug loader's `Fixed`+receipt exclusion.
3. **Scoping mechanism (operator decision):** a **top-level `"autodiscover": true` flag in `docs/features/queue.json`** (sibling of `"queue"`). Repo-local by construction (only claude-config sets it), lightest hook (the loader already reads queue.json), no new dependency. Flag absent/false ⇒ byte-identical to today, so AlgoBooth and every other repo are unaffected.
4. **Discovery is probe-time merge, not literal queue.json insertion** — discovered features are included in the in-memory work-list when `lazy-state.py` runs, identical to how `load_bug_queue` merges on-disk bugs. Nothing is written into `queue.json`.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Feature queue loader | `user/scripts/lazy-state.py` (`load_queue`, ~307–320) | Extend: read `autodiscover` flag; when set, merge on-disk open feature dirs |
| New disk-scan helper | `user/scripts/lazy-state.py` (new `_find_open_feature_dirs` + `feature_priority`, mirroring `bug-state.py`) | Add: open-feature filter (has SPEC.md; NOT Complete+receipt / Superseded; skip `_archive`/underscore dirs) |
| `queue-missing` terminal | `lazy-state.py::compute_state` (~1350) | Reconcile: empty explicit queue + non-empty disk discovery is NOT `queue-missing` (mirror bug "queue is OPTIONAL") |
| Coupled-pair parity | `lazy_parity_audit.py`; `bug-state.py` (unchanged) | Verify the additive mirror passes the parity audit (sort-key divergence — feature `**Priority:**` vs bug `**Severity:**` — is justified) |
| Enablement | `docs/features/queue.json` (claude-config) | Set `"autodiscover": true` |
| Tests | `lazy-state.py --test` (+ new fixtures), `bug-state.py --test` | Flag-off byte-identical; flag-on discovers open dir; excludes Complete+receipt; dedupes explicit-entry twin; ordering by Priority then name |

## Fix Scope (for /plan-bug)

- **Ordering:** explicit `queue.json` entries first (listed order, deduped by id so an explicitly-queued feature isn't double-counted with its on-disk dir); discovered features follow, sorted by `**Priority:**` rank (P0→P3, absent last) then directory name (stable).
- **Discovered-entry shape:** `{id: <dirname>, name: <SPEC '# ' title or dirname>, spec_dir: <dirname>, tier: <from **Priority:** or 0>, queue_entry: None}` — mirrors the bug loader's discovered-entry shape.
- **Reuse:** lean on existing `lazy_core` parsers (`spec_status`, `has_completion_receipt`) for the exclusion filter rather than re-implementing; structurally mirror `bug-state.py::_find_open_bug_dirs`.
- **Coupling Rule (HARD):** change `lazy-state.py` only; keep both `--test` suites green; add a flag-off regression fixture; run `lazy_parity_audit.py`.

## Open Questions

- Discovered-feature `name` source: SPEC `# ` title (chosen) vs a dedicated field — minor, settle in planning.
- Whether feature auto-discovery should ever become a global default (currently scoped opt-in per "specifically for claude-config").
