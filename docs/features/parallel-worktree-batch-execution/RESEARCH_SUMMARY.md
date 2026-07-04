---
kind: research-summary
feature_id: parallel-worktree-batch-execution
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — parallel-worktree-batch-execution

Honest codebase survey verifying every surface the SPEC names, at the lane branch's base
(post `queue-dependency-dag` + `harness-telemetry-ledger` landing). All paths repo-relative.

## Surfaces verified (present, as the SPEC assumes)

| SPEC-named surface | Verified location | Notes |
|---|---|---|
| `lazy_coord.py` global lock (`acquire_lock`/`release_lock`, `os.mkdir`) | `user/scripts/lazy_coord.py:86-114` | Exponential backoff, `TimeoutError`; no fcntl/flock. |
| Fencing leases (`acquire_lease`/`heartbeat`/`verify_fencing`/`reclaim_expired`/`release_lease`, `FencingError`) | `lazy_coord.py:117-288` | Entry shape `{worker_pid, worktree_slot, term_token, heartbeat_timestamp, ttl_seconds}`; term_token monotonic (`prev+1`). |
| `provision_pool(cognito_root, pool_dir, k)` | `lazy_coord.py:291` | Cognito-parameterized root arg — D10's rename target. Slots `wt-NN`. |
| `scrub_slot(cognito_root, pool_dir, slot, wi_id, slug, *, lock_dir=None)` | `lazy_coord.py:339` | Hard-coded `origin/main` detach target + `p/{wi_id}-{slug}` branch literal at :393 — D10's parameterization targets. |
| `lazy_coord.py --test` (5 fixtures) | `lazy_coord.py:404-642` | Inline PASS/FAIL harness; green at baseline. |
| Stdlib-only / MUST NOT import `lazy_core` | `lazy_coord.py:13` docstring | Confirmed: no `lazy_core` import. The lanes.json ledger therefore needs lazy_coord's OWN atomic-write (`_write_leases` pattern, temp + `os.replace`) — a justified duplication of `lazy_core._atomic_write` to preserve the no-import contract. |
| `dep_ids` / `detect_dep_cycle` / `validate_queue_deps` | `lazy_core.py:398 / 416 / 493` | queue-dependency-dag landed on base. |
| `dep_completion_status` (receipt-gated, archive-aware) | `lazy_core.py:660` | Returns `complete / incomplete / unsatisfiable-* / missing`. |
| `parse_independent_marker(spec_text, queue_entry)` | `lazy_core.py:12219` | Two-source (`independent: true` / `no_shared_state: true`); absent ⇒ False (conservative). |
| `dep_gated` probe key + `--sync-deps` | `lazy-state.py:182,2324` + CLI | As documented in `user/scripts/CLAUDE.md` "Queue dependency DAG". |
| `repo_key(repo_root)` / `claude_state_dir()` | `lazy_core.py:7051 / 9663` | sha1 of normalized realpath — each worktree resolves to its OWN keyed state dir with zero changes (D2-A's isolation primitive). `LAZY_STATE_DIR` set ⇒ returned exactly (hermetic tests). |
| `write_run_marker(...)` | `lazy_core.py:9750` | Born owner-bound via `session_id=args.session_id` threading in BOTH `--run-start` handlers (`lazy-state.py:10556`, `bug-state.py:6247`). |
| `RUN_CONTINUITY_FIELDS` / `RUN_FRESH_FIELDS` partition + completeness tripwire | `lazy_core.py:6949-6983`; `test_lazy_core.py:10744-10830` | `test_run_marker_continuity_partition_is_complete_and_disjoint` pins union == `_run_marker_scoped_keys()` — a new marker key (our `parent_run`) is a HARD failure until classified. Confirmed this is the designed tripwire. |
| `refuse_run_start_clobber` (checkpoint-discriminated) | `lazy_core.py:11172` | Evaluated against the ACTIVE repo's keyed dir — applies verbatim per lane root. |
| `marker_owner_status` / `reassert_marker_owner` | `lazy_core.py:10030 / 10083` | Untouched by this feature. |
| Containment hooks armed via `--marker-present --repo-root <cwd>` | `user/hooks/lazy-*.sh` | Per-repo keying means per-LANE arming for free (D9). |
| `--cycle-end` friction detector (per-repo state dir + `begin_head_sha`) | `lazy-state.py --cycle-begin/--cycle-end` | Snapshots per state dir ⇒ per lane; D9's new fixture obligation covered in Phase 5. |
| Telemetry chokepoints (`append_telemetry_event`) | `lazy_core.py:13702`; emission at `--run-start/--run-end/--cycle-begin/--cycle-end/--emit-prompt` | harness-telemetry-ledger landed — lane markers emit run/cycle events for free (each lane's ledger lives in its own keyed state dir). |
| `lazy-worker` SKILL | `user/skills/lazy-worker/SKILL.md` | References `provision_pool`-era primitives by prose + keyword args only — the positional `cognito_root`→`repo_root` rename does not break the skill text; scrub sequence + `p/<wi_id>-<slug>` branch convention restated there and PRESERVED as defaults. |
| Parity audit | `lazy_parity_audit.py:347` (`audit_state_script_parity`) | Pattern-presence checks over BOTH scripts; adding `--parent-run` to both keeps it green. Exit 0 at baseline. |
| `--test` baselines | `user/scripts/tests/baselines/*.txt` + README | Regeneration ONLY via `_normalize_smoke_output` (test_lazy_core.py). |

## Drift / corrections found (SPEC assumptions vs reality)

1. **Stale line anchor inside `lazy_core.py`'s own partition comment** — the SSOT comment at
   `lazy_core.py:6919-6948` says the `write_run_marker` literal is at ":8861-8907"; it is at
   :9750-9860 today. Pre-existing cosmetic drift, not introduced or relied on here (the
   completeness test reads the LIVE literal via `_run_marker_scoped_keys()`, so nothing breaks).
2. **`lazy-batch-retro` location** — the SPEC-adjacent docs describe it as repo-scoped
   (algobooth); it now lives at `user/skills/lazy-batch-retro/SKILL.md` (user-level). The Phase-6
   retro audit-feed edit targets the user-level file.
3. **`pool_size`** is prose-config in `lazy-worker` (read from config), not a lazy_coord constant —
   the D6 `effective_lanes` helper takes it as an argument rather than reading config itself.
4. **No existing `lanes.json`** anywhere — greenfield ledger, sibling of `leases.json` per D7.

## Integration points enumerated

- `lazy_coord.py` — new: `claim_shardable`, lanes-ledger writers/readers (`read_lanes`,
  `ledger_record_*`, `merge_order`, `flush_summary`), `effective_lanes`, `lane_budget_slice`,
  `lane_branch`, `lane_pool_dir`, `merge_lane_branch`; generalized: `provision_pool`,
  `scrub_slot` (defaults byte-compatible for Cognito/`lazy-worker`).
- `lazy_core.py` — `write_run_marker(parent_run=...)` + `RUN_FRESH_FIELDS` classification.
- `lazy-state.py` / `bug-state.py` — `--parent-run <json>` threading on `--run-start`
  (coupled pair; marker is shared).
- `user/skills/lazy-batch-parallel/SKILL.md` — new coordinator skill (D1-A), composing
  `adhoc-enqueue.md` and the batch-family bookends.
- `user/skills/lazy-status/SKILL.md` — lane rows (read `lanes.json` + per-worktree probes).
- `user/skills/lazy-batch-retro/SKILL.md` — demotion + false-`independent` audit feed.
- Docs: `user/scripts/CLAUDE.md` (concurrency-plane section) + root `CLAUDE.md`.

## Environment constraints observed (this implementation session)

Linux container: no PowerShell (PS files read-only), no live multi-lane workstation run possible,
git + python3.11 + pytest available (real temp git repos ARE possible, so worktree/merge fixtures
run for real). Multi-lane live-run validation rows are deferred to workstation per protocol.
