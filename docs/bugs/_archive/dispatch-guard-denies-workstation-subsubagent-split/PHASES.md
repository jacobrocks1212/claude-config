# Implementation Phases — Dispatch Guard Denies Workstation Sub-Subagent Split

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface. This fix spans a
state-script decision function (`lazy_guard.py`, owned by the STATE lane) and ten skill-frontmatter
capability flags (owned by the SKILLS lane); the HOOKS-lane slice verified in this pass is the
`test_hooks.py` end-to-end guard pipe-tests (the hook wrapper `lazy-dispatch-guard.sh` itself is
unchanged — "Entry path; unchanged by fix" per the SPEC's Affected Area table).

## Validated Assumptions

- **The fix was already landed** (commit `821896b2`, 2026-07-10, "fix(dispatch-guard): workstation
  sub-subagent exemption — decision 4 resolved") per the SPEC's own "Resolution" section, which
  documents the operator's decision-4 disposition and the shipped predicate (branch 2b) in full.
  This PHASES.md is authored **retroactively** as the receipt this bug's lifecycle was missing
  (Status was left at `Concluded` with no `PHASES.md`/`FIXED.md` despite the Resolution reading as
  a completed fix) — confirmed by reading the current `user/scripts/lazy_guard.py` and
  `user/scripts/test_hooks.py` against the Resolution's description and finding every element
  present.
- **Cross-lane scope, not touched in this pass:** the fix's substantive code lives in
  `user/scripts/lazy_guard.py` (branch 2b) and `user/scripts/lazy_core.py`
  (`skill_declares_subagent_model`, `emission_consumed_by_nonce`,
  `append_worker_subdispatch_event`, `write_cycle_marker` stamping) plus ten `SKILL.md` frontmatter
  flags — all STATE-lane / SKILLS-lane owned files, active in other lanes this session and
  therefore not re-verified here. This bug-fix pass's HOOKS-lane responsibility is the receipt
  itself plus the `test_hooks.py` guard pipe-tests, which were already present and green.

---

### Phase 1: Guard exemption for workstation cycle-worker sub-subagent dispatch

**Status:** Complete (landed pre-existing, commit `821896b2`, 2026-07-10)

**Scope:** Per the SPEC's Resolution — add `lazy_guard.py` `guard()` branch 2b: ALLOW an
unregistered `Agent`/`Task` prompt iff (1) workstation-only (marker `cloud` flag falsy), (2) bound
marker (`session_id` non-None), (3) the active cycle marker's `subagent_model` field is `True`
(general skill-frontmatter capability, not a hardcoded skill list), and (4) the cycle marker's own
registered emission is already consumed (the operator-owned "consumed fence" safety proof). Every
exempted allow is audited as a pre-acked `worker_subdispatch: true` deny-ledger event (no hardening
debt booked).

**TDD:** yes (per the SPEC Resolution: "4 unit tests (`test_lazy_core.py`) + 5 end-to-end guard
pipe-tests (`test_hooks.py`) — allow + audit + zero debt; deny on pre-consume / no-capability /
cloud / unbound").

**Deliverables:**
- [x] `lazy_guard.py` branch 2b (verified present: `:824-868` region — `subagent_model` check
  `:854`, `append_worker_subdispatch_event` call `:857`), fail-closed on every degraded read.
- [x] `lazy_core.py` — `skill_declares_subagent_model`, `emission_consumed_by_nonce`,
  `append_worker_subdispatch_event`, `write_cycle_marker` `subagent_model` stamping (additive
  field; legacy markers read falsy → no exemption). **STATE lane — not re-verified this pass**
  (active lane; SPEC's own Resolution cites `test_lazy_core.py` 939/939 as the landing-time gate).
- [x] Ten `user/skills/*/SKILL.md` frontmatter flags (`execute-plan`, `spec-phases`,
  `spec-phases-batch`, `plan-feature`, `plan-bug`, `spec`, `spec-bug`, `retro-feature`,
  `implement-phase`, `implement-phase-batch`). **SKILLS lane — not re-verified this pass** (active
  lane).
- [x] `test_hooks.py` guard pipe-tests (verified present and green, this session):
  `test_guard_worker_subdispatch_exemption_allows`,
  `test_guard_worker_subdispatch_denied_before_consume`,
  `test_guard_worker_subdispatch_denied_without_capability`,
  `test_guard_worker_subdispatch_denied_on_cloud`,
  `test_guard_worker_subdispatch_denied_unbound_marker`,
  `test_guard_worker_subdispatch_exemption_allows_fresh_cycle_nonce`.
- [x] Cloud path unaffected — `lazy-batch-cloud`'s inline-override model is unchanged (SPEC
  Resolution + `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, out of this repo's HOOKS
  lane scope entirely).

**Implementation Notes (retroactive receipt, 2026-07-12/13):** Verified on disk against the SPEC's
Resolution section — the branch-2b markers (`worker_subdispatch`, `subagent_model`,
`skill_declares_subagent_model`) are present in `lazy_guard.py` at the cited region, and all six
named `test_hooks.py` pipe-tests exist and pass in isolation
(`python -m pytest user/scripts/test_hooks.py -k "worker_subdispatch" -q` → **6 passed**) and as
part of the full suite (`python -m pytest user/scripts/test_hooks.py -q` → **217 passed**). No code
changed in this pass — this phase's Status reflects the pre-existing landed state. `lazy_core.py`
and the ten SKILL.md frontmatter flags were confirmed present by targeted grep (not independently
re-executed — those test suites belong to lanes active elsewhere this session).

**Minimum Verifiable Behavior:** An unregistered `Agent` prompt from a workstation cycle worker,
dispatched after its cycle's own emission is consumed, under a bound non-cloud marker whose
`sub_skill` declares `subagent_model: true`, is ALLOWED and logged as a pre-acked
`worker_subdispatch` event (no hardening debt); the same dispatch before consumption, without the
capability flag, on a cloud marker, or on an unbound marker is DENIED.

**Runtime Verification** *(checked by the pipe tests — the guard's runtime IS the subprocess
pipe):*
- [x] <!-- verification-only --> Exemption allows (post-consume, capable, workstation, bound).
  **Verified:** `test_guard_worker_subdispatch_exemption_allows` GREEN.
- [x] <!-- verification-only --> Deny before consume. **Verified:**
  `test_guard_worker_subdispatch_denied_before_consume` GREEN.
- [x] <!-- verification-only --> Deny without capability flag. **Verified:**
  `test_guard_worker_subdispatch_denied_without_capability` GREEN.
- [x] <!-- verification-only --> Deny on cloud marker. **Verified:**
  `test_guard_worker_subdispatch_denied_on_cloud` GREEN.
- [x] <!-- verification-only --> Deny on unbound marker. **Verified:**
  `test_guard_worker_subdispatch_denied_unbound_marker` GREEN.
- [x] <!-- verification-only --> Exemption allows on a fresh cycle nonce (rebinding edge case).
  **Verified:** `test_guard_worker_subdispatch_exemption_allows_fresh_cycle_nonce` GREEN.

**MCP Integration Test Assertions:** N/A — no app runtime surface; the guard's runtime observable
is the subprocess pipe decision, asserted directly by the pipe tests above.

**Prerequisites:** None (first and only phase; already landed).

**Files likely modified:**
- `user/scripts/lazy_guard.py` (STATE lane — branch 2b, verified present).
- `user/scripts/lazy_core.py` (STATE lane — supporting predicates, verified present by grep, not
  re-executed).
- Ten `user/skills/*/SKILL.md` (SKILLS lane — frontmatter flags, verified present by grep, not
  re-executed).
- `user/scripts/test_hooks.py` (HOOKS lane — 6 pipe-tests, verified present and green this
  session).
- `user/hooks/lazy-dispatch-guard.sh` — unchanged (entry path only; the decision logic lives in
  `lazy_guard.py`).

**Testing Strategy:** Pure pipe testing at the HOOKS-lane boundary (`test_hooks.py` drives the
guard hook end-to-end via subprocess with crafted stdin JSON + marker fixtures); unit-level
coverage of the underlying predicates lives in `test_lazy_core.py` (STATE lane, not re-run here).

**Integration Notes for Next Phase:** N/A — terminal phase. Decision 4 in
`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` is resolved per the SPEC's own Resolution
section; no further hardening rounds are expected against this specific denial signature.
