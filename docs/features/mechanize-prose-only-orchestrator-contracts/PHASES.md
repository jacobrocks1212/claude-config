# Implementation Phases — Mechanize Prose-Only Orchestrator Contracts

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
D1 provisionally accepted per `NEEDS_INPUT_PROVISIONAL.md` — completion is mechanically blocked
until ratified)

**MCP runtime:** not-required — pure claude-config harness mechanics (state-script functions,
CLI subcommands, guard logic, SKILL.md prose). No Tauri app, no MCP-reachable surface. Validation
is `pytest` (`user/scripts/test_lazy_core.py`), the state scripts' in-file `--test` smoke
harnesses, `lazy_parity_audit.py`, `doc-drift-lint.py`, `lint-skills.py`, `project-skills.py`,
`generate-coupled-skills.py`, and `cli_surface_gen.py`. Same untestable-by-MCP class as
`friction-kpi-registry` → `SKIP_MCP_TEST.md` at the MCP gate.

---

### Phase 1 — (a) Model-tier pinning

**Phase kind:** implementation

- [x] `lazy_core.register_emission` / `register_emission_if_marked` gain a `model` parameter,
  stored on the registry entry. `<!-- verification-only -->`
- [x] Every call site that registers a `cycle`/meta-dispatch emission passes `model=` (the two
  `--emit-prompt` sites in `lazy-state.py`/`bug-state.py`; the `--emit-dispatch` sites in both).
- [x] `lazy_guard.py` gains `_pinned_model_update(tool_input, entry)` and wires it into all four
  ALLOW paths that can carry a `model:` field: fresh-consumption, F2a by-reference, idempotent
  re-fire, and F1b auto-readmit (`_try_auto_readmit` now takes `tool_input`). Fail-open on a
  legacy entry with no `model` field.
- [x] SKILL.md prose demoted to a pointer at the mechanism (`lazy-batch`, `lazy-batch-cloud`,
  `lazy-bug-batch`).

**Evidence:** `test_guard_pins_model_on_fresh_allow` (mismatch / missing / already-correct /
legacy-fail-open — 4 sub-cases), `test_guard_pins_model_on_by_reference_and_auto_readmit_allows`
(by-ref + auto-readmit) in `user/scripts/test_lazy_core.py`; `lazy-state.py --test` /
`bug-state.py --test` unaffected (green). `<!-- verification-only -->`

**Locked decision:** D1 (rewrite-vs-deny) is `product-behavior` — implemented against
recommendation A, **provisionally accepted** pending operator ratification (`NEEDS_INPUT_PROVISIONAL.md`).

---

### Phase 2 — (b) Post-cycle input-audit obligation

**Phase kind:** implementation

- [x] `lazy_core.AUDITED_CYCLE_KINDS`, `record_audit_obligation`, `pending_audit_obligation`,
  `discharge_audit_obligation`, `build_input_audit_emit_command` (marker-field pattern mirroring
  `last_advance_state_key`/`last_resolution_step_key` — NOT part of `write_run_marker`'s initial
  literal, so no `RUN_CONTINUITY_FIELDS`/`RUN_FRESH_FIELDS` reclassification is owed).
- [x] `--cycle-end` (both state scripts) arms the obligation when the ending cycle's `sub_skill`
  is audited (feature: `spec`/`plan-feature`; bug: `spec-bug`/`spec-phases` — `plan-bug`
  deliberately excluded per existing `lazy-bug-batch/SKILL.md` Step 1d.5 prose, see
  RESEARCH_SUMMARY.md).
- [x] `--emit-prompt` (both scripts) withholds the forward route when an obligation is pending
  (checked AFTER the pending-hardening-debt withhold — mutually exclusive priority), surfacing
  `route_overridden_by: "audit-obligation"` + `input_audit_emit_command`.
- [x] `--emit-dispatch input-audit`'s success path (both scripts) discharges the obligation on a
  REGISTERED (marker-present) emission.
- [x] SKILL.md `lazy-batch` §1d.5 prose demoted to a pointer at the mechanism.

**Evidence:** `test_probe_withholds_forward_route_on_audit_obligation` (end-to-end subprocess:
arm → withhold → discharge via registered emit → forward route resumes),
`test_audit_obligation_helpers_no_marker_and_non_audited_kind` (no-marker no-op, non-audited
kind no-op, `plan-bug` explicitly NOT audited, `spec-bug` IS) in `test_lazy_core.py`.
`<!-- verification-only -->`

---

### Phase 3 — (c) Decision write-back

**Phase kind:** implementation

- [x] `lazy_core.record_decision` / `read_decision_record` — atomic sibling state-dir record
  (`lazy-decisions.json`), keyed by a normalized sentinel path; survives `--run-end` (not part of
  the run marker).
- [x] `lazy_core.bind_decision_record_context(cls, context, state_script_name)` — for
  `cls == "apply-resolution"` with a `sentinel_path` in context, replaces `chosen_path`/
  `resolution_summary` with the recorded values; refuses (`ValueError` naming the exact
  `--record-decision` command) when no record exists.
- [x] `--record-decision --sentinel <path> --chosen "<text>" [--summary "<text>"]` CLI subcommand
  on both state scripts, orchestrator-only (`refuse_if_cycle_active`).
- [x] `--emit-dispatch` handler on both scripts calls `bind_decision_record_context` before
  `emit_dispatch_prompt` for every class (no-op for non-apply-resolution / no-sentinel contexts).
- [x] SKILL.md prose (`lazy-batch`, `lazy-batch-cloud`, `lazy-bug-batch`, both needs-input and
  blocked apply-resolution dispatch sites) + `dispatch-apply-resolution.md` header demoted to
  "record then dispatch."

**Evidence:** `test_record_decision_and_read_round_trip` (write/read/overwrite/path-normalization),
`test_bind_decision_record_context_refuses_without_record_and_binds_when_present` (pass-through /
refusal / binding), `test_record_decision_cli_and_apply_resolution_binds_end_to_end` (full
subprocess: refuse without record → `--record-decision` → same emit succeeds, chosen text +
summary embedded VERBATIM in the emitted `dispatch_prompt`) in `test_lazy_core.py`.
`<!-- verification-only -->`

---

### Phase 4 — (d) Notification coverage

**Phase kind:** implementation

- [x] `lazy_core.notify_event(kind, message, repo_root, *, pipeline, item_id, detail, sender, now)`
  — generalizes the `notify_halt` seam (reuses `_load_notify_config`, `_load_notify_ledger`,
  `_record_notify_send`, `_write_notify_error`, `_github_remote_url`, `_ntfy_send`). Content-based
  exactly-once dedup identity (`event|{kind}|{pipeline}|{item_id}|{detail}`) — no timestamp
  component, so a repeated observation of the same event never double-pages.
- [x] Four call sites wired (both state scripts where applicable): each `_PARKED.append(...)`
  branch in the queue walk (`park`, 4 sites/script); the budget-guard trip block (`budget-trip`,
  feature-pipeline-only per the existing per-feature-ceiling justified divergence); the
  `--provisionalize-sentinel` success path (`provisional-accept`); `--run-end` immediately before
  the marker is deleted (`flush`).
- [x] SKILL.md §1c.6 prose (`lazy-batch`, `lazy-batch-cloud`) demoted to a pointer noting the
  script-side coverage; the orchestrator's own `PushNotification` calls are retained as a
  harmless backstop (not deleted — D4-A's stated intent is additive coverage, not removal of the
  existing orchestrator-side calls).

**Evidence:** `test_notify_event_inert_without_config`, `test_notify_event_dedup_exactly_once_and_distinguishes_events`,
`test_notify_event_fail_open_on_send_error` in `test_lazy_core.py`. `<!-- verification-only -->`

---

### Phase 5 — Gates + coupled-pair regeneration

**Phase kind:** verification

- [x] `python -m pytest user/scripts/test_lazy_core.py -q` — 1096/1108 pass; the 12 failures are
  PRE-EXISTING, unrelated to this feature (`efficacy-flush breadcrumb COVERING THE
  INTERVENTIONS-BEARING SCOPE` gate — confirmed reproducible on a clean `git stash` of this
  feature's changes, i.e. present at HEAD before this session; independently confirmed by a
  dispatched harden-harness diagnosis). `<!-- verification-only -->`
- [x] `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` —
  both exit 0, all smoke fixtures pass, baselines byte-identical (`test_lazy_core.py -k baseline`
  green). `<!-- verification-only -->`
- [x] `python user/scripts/lazy_parity_audit.py --repo-root .` — exit 0. `<!-- verification-only -->`
- [x] `python user/scripts/doc-drift-lint.py --repo-root .` — exit 0 (2 pre-existing exempted
  divergences, unrelated). `<!-- verification-only -->`
- [x] `python user/scripts/lint-skills.py --check-projected --check-capabilities --check-skill-size`
  — exit 0; the three grown SKILL.md files (`lazy-batch`, `lazy-batch-cloud`, `lazy-bug-batch`)
  were trimmed back under their pre-existing size-ratchet ceilings and the baseline was
  re-locked-in DOWNWARD (never raised) via `skill-size-ratchet.py --lock-in`.
  `<!-- verification-only -->`
- [x] `python user/scripts/project-skills.py` — clean regen, 0 errors. `<!-- verification-only -->`
- [x] `python user/scripts/generate-coupled-skills.py --extract` then `--check` — "all pairs
  byte-identical (fresh)". `<!-- verification-only -->`
- [x] `python user/scripts/cli_surface_gen.py --repo-root . --check` — regenerated
  `docs/cli/cli-surface.json` for the four new flags (`--record-decision`, `--sentinel`,
  `--chosen`, `--summary` on both state scripts); re-check green. `<!-- verification-only -->`

**Residual (out of scope, reported not fixed):** `cli-surface-lint.py --repo-root .` finds 20
PRE-EXISTING findings unrelated to this feature's new flags (all reference flags this feature did
not touch — `--park`, `--gate-coverage`, `--json`, `--force`, etc. — the tool's own documented
"Known v1 imprecision" cross-clause-attribution false positives). Not in this feature's Step-5
gate list; not caused by this session's edits.

## Cross-feature note

A concurrent `git stash` collision occurred mid-session when a dispatched `harden-harness`
sub-agent (investigating the pre-existing efficacy-breadcrumb test failures above) ran in the
SAME working directory rather than an isolated worktree, stashing this feature's in-flight
uncommitted work. Fully recovered (`git stash pop` + verification) with zero data loss — full
inventory + recovery steps are in the session transcript, not repeated here. No file ended up
duplicated, corrupted, or silently reverted; all gates above were re-run clean after recovery.
