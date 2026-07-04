---
kind: research-summary
feature_id: queue-dependency-dag
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — queue-dependency-dag

Codebase survey verifying every surface the SPEC names, at the lane's baseline commit
(`b5c1021`). All line anchors re-verified; two SPEC assumptions needed refinement (below).

## Surface verification (SPEC anchors vs. live code)

| SPEC claim | Verified location | Status |
|---|---|---|
| `parse_dep_block` at `lazy-state.py` ~line 1158 | `lazy-state.py:1168` | drifted +10 lines; signature/behavior exactly as described (returns `[{feature_id, kind, reason}]`, `(none)`/malformed → `[]`) |
| Walk-loop dep-gate insertion region ~line 2254 | skip-ahead branch `lazy-state.py:2243–2325`; the dep-gate slots after the budget-guard block (ends ~2242) and before `if not strict_research_halt:` | accurate |
| `skip_ahead_ready` two-key predicate | `lazy_core.py:12214` — key 1 iterates caller-parsed deps, `kind == "hard"` ∩ `gated_ids`; key 2 `independent` | accurate; queue-deps union is a pure caller-side input extension (no helper change needed) |
| `load_queue` / `load_bug_queue` hybrid loaders | `lazy-state.py:488` (raw-entry shape + opt-in `autodiscover` merge), `bug-state.py:362` (normalized `spec_path` shape + always-on disk merge) | accurate; the two return shapes legitimately differ — dep reads must be shape-tolerant (feature: raw entry; bug: `entry["queue_entry"]`) |
| Receipt-gated completion | `lazy_core.has_completion_receipt` (`lazy_core.py:610`, content-validated; `filename="FIXED.md"` for bugs); `spec_status` (`lazy_core.py:586`) | accurate |
| `SANCTIONED_STOP_TERMINAL` | `lazy_core.py:9268` — flat frozenset, shared by both scripts | accurate; `queue-exhausted-dependency-gated` is a one-line additive member |
| `--strict-research-halt` parity-only on bug side | `bug-state.py:581` docstring + `_ = strict_research_halt` (~line 639; SPEC said ~631) | accurate in substance — bug pipeline has NO skip-ahead, so D7 is feature-only (justified divergence, documented) |
| `unknown-host-capability` fail-fast precedent | `lazy-state.py:1875–1919` + `bug-state.py:829–861`, shared `lazy_core.format_unknown_host_capability_blocker` (`lazy_core.py:12121`) + `_write_yaml_blocked_sentinel` in both scripts | accurate — `blocker_kind: unknown-dependency` reuses this exact shape (canonical BLOCKED.md, `terminal_reason="blocked"`, Step 3 wording) |
| `reorder_queue` / `enqueue_adhoc` script-owned mutation chokepoints | `lazy_core.reorder_queue` (`lazy_core.py:131`, load → mutate → `_atomic_write`, `noop: true`), `enqueue_adhoc` (`lazy-state.py:582`, `bug-state.py:1482`) | accurate — `sync_deps` mirrors this shape |
| `refuse_if_cycle_active` orchestrator-only gate | `lazy_core.py:10581`; wired at `--enqueue-adhoc`/`--reorder-queue`/`--reassert-owner` entry in BOTH scripts (exit 3, zero side effects) | accurate — `--sync-deps` gets the identical first-line guard |
| Skip-ahead smoke fixtures ~line 7100 | `lazy-state.py:7106–7305` (`feat-sa-*` suite: default skip, no-ready-alt fallback, strict-halt) | accurate; Phase-3 fixture extends this suite |
| Parity audit surface list | `lazy_parity_audit.py:340 audit_state_script_parity` — currently FIVE regex surfaces (`set_active_repo_root`, `--reorder-queue`, `--reassert-owner`, host-capability fail-fast pair, `cycle_prompt_ref`); `test_lazy_parity.py:623–739` stubs enumerate the same set and say "ALL FIVE" | accurate — adding `--sync-deps` as the SIXTH surface requires lockstep stub updates (the SPEC/approval note about "stale fixtures" is exactly this) |
| `--test` baselines byte-pinned | `tests/baselines/lazy-state-test-baseline.txt` + `bug-state-test-baseline.txt`, compared via `test_lazy_core._normalize_smoke_output`; README forbids hand-edits | accurate — new smoke fixtures print new `ok` lines ⇒ regenerate ONLY through the helper |

## Integration points enumerated

1. **`lazy_core.py`** — new shared helpers: relocated `parse_dep_block`; `dep_ids` (shape-tolerant
   queue read); `validate_queue_deps` (shape/regex/reserved-prefix/cycle at load, `_die` exit 2);
   `detect_dep_cycle` (Kahn's over queued-id edges); `dep_completion_status` (receipt-gated
   classifier: `complete | incomplete | unsatisfiable-superseded | unsatisfiable-wont-fix |
   missing`; bug pipeline additionally consults `docs/bugs/_archive/`);
   `format_unknown_dependency_blocker`; `sync_deps` (load → parse SPEC → filter hard → mutate →
   `_atomic_write`, `noop: true`); `SANCTIONED_STOP_TERMINAL` member.
2. **`lazy-state.py`** — loader validation call; walk-loop dep-gate `continue` + `_DEP_GATED`
   module global + `dep_gated` probe key; `queue-exhausted-dependency-gated` terminal; skip-ahead
   key-1 union; probe-time drift `_diag`; `--sync-deps` CLI; `--enqueue-adhoc --deps`; smoke
   fixtures. `parse_dep_block` becomes a re-export from `lazy_core` (Step 4.6 + skip-ahead callers
   unchanged).
3. **`bug-state.py`** — mirrored loader validation, dep-gate, terminal, unknown-dependency
   fail-fast, `--sync-deps`, `--enqueue-adhoc --deps`, smoke fixtures. NO skip-ahead mirror
   (divergence 1); archive-aware dep resolution (divergence 2).
4. **`lazy_parity_audit.py` + `test_lazy_parity.py`** — sixth audited surface + lockstep stub
   fixtures.
5. **Docs/skills** — `user/skills/_components/dep-block-schema.md` queue-projection paragraph;
   `user/skills/_components/adhoc-enqueue.md` `--deps` note; `user/skills/spec-phases/SKILL.md`
   `--sync-deps` invocation step; `user/scripts/CLAUDE.md` CLI rows; root `CLAUDE.md` +
   `docs/features/CLAUDE.md` schema notes. Component/skill edits require lane-local projection +
   `lint-skills.py`.

## SPEC assumptions that needed refinement

1. **D3 "still-queued ⇒ incomplete, by construction" is implemented as the pure on-disk
   receipt-gated check** (`Complete` + valid receipt ⇒ complete, regardless of a lingering queue
   entry). A literal "queued ⇒ incomplete" reading would starve a dependent whenever a
   Complete+receipt entry lingers in `queue.json` (the walk skips such entries as genuinely done;
   `__mark_complete__`'s queue-trim makes lingering transient but not impossible). The on-disk
   check preserves D3's intent — a still-workable queued item never has Complete+receipt — with no
   starvation hazard.
2. **The probe-time drift diagnostic must be gated on the queue entry carrying a `deps` key**
   (`"deps" in entry`), not run unconditionally. The SPEC's "one extra in-memory comparison"
   framing is correct only for opted-in entries: 31 live SPECs in this repo alone carry
   `**Depends on:**` blocks (6 with hard deps) while zero queue entries carry `deps`, so an
   ungated comparison would emit new diagnostics on every probe of every legacy repo — breaking
   the byte-identity guarantee for entries without the field.
3. **Deferred empirical check "SPEC read reusable for drift" — CONFIRMED:** both walk loops
   already read the candidate's SPEC.md text per entry (`_hc_spec_text`, for
   `parse_requires_host`); the drift comparison and the dep-gate reuse that read with zero
   additional file I/O.
4. **Backfill sizing (deferred check):** 6 hard-dep lines across 4 feature SPECs in claude-config
   (`friction-kpi-registry`, `harness-change-canary-rollback` ×2, `harness-hardening-retro-fixes`,
   `intervention-efficacy-tracking`, `parallel-worktree-batch-execution`); zero bug SPECs; zero
   cross-pipeline references (confirms D6's premise). NOTE (observed schema drift, prose-side):
   several live dep-block lines backtick-quote the feature id (`` `harness-telemetry-ledger` ``);
   `parse_dep_block`'s id regex rejects those lines TODAY (they are silently skipped, per the
   schema's skip-with-warning rule), so `--sync-deps` will project only schema-conformant lines.
   Fixing those SPEC lines (or loosening the SSOT parser) is prose lint work outside this
   feature's scope — recorded here so the Phase-4 backfill isn't over-estimated.
5. **Live-repo caution:** claude-config's `docs/features/queue.json` has `autodiscover: true` and
   already queues both this feature and its downstream consumer. No live-queue backfill is
   performed by this lane (queue.json is orchestrator-owned); `--sync-deps` ships as the
   sanctioned tool for it.

## Precedents adopted

- Fail-fast blocker: `unknown-host-capability` (shared formatter + canonical BLOCKED.md +
  `terminal_reason="blocked"`).
- Clean terminal: `host-capability-saturated` / `queue-exhausted-all-parked` (distinct honest
  terminal + flush naming held items; `SANCTIONED_STOP_TERMINAL` membership).
- Probe key: `gated_heads` / `budget_guard` discipline — key present ONLY when non-empty this
  probe (byte-identity for default output).
- Queue mutation: `reorder_queue` (load → mutate → `_atomic_write`, `noop: true`,
  `refuse_if_cycle_active` first, `_die` exit 2 on malformed input).
- Cross-feature merge-hygiene note: a sibling lane (harness-telemetry-ledger) touches the same
  scripts' CLI handlers — `compute_state` edits kept tight (single contiguous dep-gate block),
  new CLI flags added at the end of the existing argparse groups, test fixtures fully hermetic
  (own temp roots, own fixture ids `feat-dg-*` / `bug-dg-*`).
