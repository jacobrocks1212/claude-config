---
kind: implementation-plan
feature_id: operator-halt-notifications
status: In Progress
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4]
---

> **Plan** — single self-contained part covering all 4 phases.
> To execute: `/execute-plan docs/features/operator-halt-notifications/plans/all-phases-operator-halt-notifications-part-1.md`

# Implementation Plan — operator-halt-notifications (Phases 1–4)

**PHASES.md:** `docs/features/operator-halt-notifications/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/operator-halt-notifications/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q
python3 test_toolify_miner.py
python3 lazy-state.py --test
python3 bug-state.py --test
python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <repo-root>
python3 lint-skills.py --skills-dir <repo-root>/user/skills --repos-dir <repo-root>/repos
```

## Key design contract (read before WU-1.1)

- **Fail-OPEN is absolute:** `notify_halt` may NEVER raise, NEVER print to stdout, NEVER change
  exit codes, NEVER mutate the state dict on the inert path. On send attempts it may append to
  `state["diagnostics"]` (the copy inside the dict — `lazy_core._diag` post-compute would be lost)
  and, on failure, overwrite `notify-error.json`.
- **`parse_sentinel` is NOT used inside the notifier** (it `_die()`s → stdout JSON + exit 2 —
  would corrupt the halt). A tolerant local frontmatter read of the same fence contract degrades
  malformed sentinels to "no decision lines".
- **Locked D3 attention set (11):** blocked, blocked-misnamed, needs-input, needs-spec-input,
  needs-research, queue-blocked-on-research, completion-unverified, stale_upstream,
  queue-exhausted-all-parked, queue-exhausted-budget-deferred, queue-missing.
  Clean stops (opt-in, 5): all-features-complete, all-bugs-fixed, cloud-queue-exhausted,
  device-queue-exhausted, host-capability-saturated.
- **Config precedence:** `LAZY_NOTIFY_DISABLE` truthy → None; else file (`~/.claude/notify.json`)
  ∪ env (`LAZY_NOTIFY_URL` wins on `url`); neither yields a url → None.
- **Ledger:** `notify-ledger.json` in `claude_state_dir()`, `_atomic_write`, entries pruned >30d
  on write, updated ONLY on successful send.
- **HARD:** all new pytest functions appended to `_TESTS` in `test_lazy_core.py`; baselines
  regenerated ONLY via `_normalize_smoke_output`.

---

## Phase 1 — Core helper (lazy_core)

- [x] WU-1.1 — TDD: config loader tests (absent → None; disable kill switch; env-url only; file
  only; env overrides file url; malformed file → None fail-open) → implement
  `_load_notify_config()` + `_NOTIFY_*` frozensets + module constants.
- [x] WU-1.2 — TDD: identity tests (sentinel-backed mtime/size key; rewrite → new identity;
  sentinel-less date key; blocked-misnamed stray key) → implement `_notify_identity()` +
  `_notify_sentinel_path()`.
- [x] WU-1.3 — TDD: ledger tests (round-trip, 30-day prune, `_atomic_write` spy, corrupt ledger
  → treated empty) → implement `_load_notify_ledger()` / `_record_notify_ledger()`.
- [x] WU-1.4 — TDD: payload tests (title verbatim; body lines incl. needs-input decisions ≤4;
  tolerant read of malformed sentinel; link from SSH/HTTPS/ssh:// remotes; no remote → None link)
  → implement `_compose_notify_payload()` + `_github_remote_url()` + `_notify_decisions()`.
- [x] WU-1.5 — TDD: notify_halt end-to-end (inert-without-config byte-identity + zero writes;
  attention-set gating; clean-stop opt-in both ways; dedup across 3 calls; fail-OPEN on sender
  raise → breadcrumb + no ledger + diagnostics line; success → ledger + diagnostics line) →
  implement `notify_halt()` wrapper + `_notify_halt_inner()` + `_write_notify_error()`.
- [x] WU-1.6 — TDD: `_ntfy_send` unit tests (POST body/headers via monkeypatched urlopen;
  RFC-2047 title encoding for non-latin-1; Click header only when link) → implement `_ntfy_send`
  + `_rfc2047_header()` + default-sender binding.
- [x] WU-1.7 — Register every new test in `_TESTS`; full pytest suite + `--test` smokes green
  (no baseline change expected — no script edits yet). Commit Phase 1.

## Phase 2 — Wire both scripts (parity-coupled)

- [x] WU-2.1 — TDD: `test_lazy_parity.py` seven-surface lockstep (update all stubs + docstrings;
  new fires-when-notify-halt-missing test; run → red against unwired scripts) → implement
  `_NOTIFY_HALT_RE` surface #7 in `lazy_parity_audit.py` + the two one-line call sites in
  `lazy-state.py` / `bug-state.py` `main()` → green.
- [x] WU-2.2 — In-file `--test` fixture (lazy-state.py): halt fixture repo + hermetic env +
  monkeypatched module sender; `main()` driven twice ⇒ exactly one send; disable-switch leg
  byte-identical output.
- [x] WU-2.3 — In-file `--test` fixture (bug-state.py): mirrored over a bug halt.
- [x] WU-2.4 — Re-pin both `--test` baselines via `_normalize_smoke_output` (fixture output lines
  legitimately added); `lazy_parity_audit.py --repo-root .` exit 0; full gate suite green.
  Commit Phase 2.

## Phase 3 — Live channel + environment verification

- [x] WU-3.1 — Confirm nothing code-side remains (production sender complete + unit-verified);
  record the three live legs as DEFERRED (workstation/phone/cloud-run) prose rows in PHASES.md.
  Commit Phase 3 (docs-only).

## Phase 4 — Opt-ins and docs

- [x] WU-4.1 — `user/scripts/CLAUDE.md` "Operator halt notifications" section (config schema, env
  overrides, sets, ledger/breadcrumb, fail-OPEN, §1c.6 coexistence, parity surface #7).
- [x] WU-4.2 — Root `CLAUDE.md`: `notify.json` in the untracked-secrets list.
- [ ] WU-4.3 — Final FULL gate suite (all suites + smokes + parity + lint) green; SKIP_MCP_TEST.md;
  finalize PHASES/plan statuses. Commit Phase 4 + finalization.
