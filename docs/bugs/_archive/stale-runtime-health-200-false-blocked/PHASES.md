# Implementation Phases — Stale runtime behind health=200 mints false BLOCKED verdicts

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this fix lives entirely inside claude-config's shared
`user/scripts/lazy_core.py` (the `ensure_runtime` helper consumed by AlgoBooth's `/lazy-batch`
runs via `lazy-state.py --ensure-runtime`), not in an app claude-config itself ships.
claude-config has no Tauri/MCP app surface. Verification is the repo's own deterministic gates
(`pytest user/scripts/test_lazy_core.py`, `lazy-state.py --test`, `bug-state.py --test`) plus a
read-back confirming the STALE verdict is now reachable from a bound, real freshness signal. The
fix's real-world effect (fewer stale-confound false BLOCKED mints, fewer hand-invented
`dev:restart` rituals) is only observable in a live AlgoBooth `/lazy-batch` run — the
"Manual live cold-boot smoke" convention documented in `user/scripts/CLAUDE.md` is the sanctioned
operator-side confirmation, out of scope for claude-config's own CI.

## Validated Assumptions

- **`stale_check` is ALREADY on the production-binding test-discipline guard's allowed-injection
  list** (`test_lazy_core.py::_PRODUCTION_BINDING_ALLOWED_KWARGS`) — unlike `boot_alive`/`restart`,
  which a `test_ensure_runtime_production_*`-named test MUST derive, `stale_check` may legitimately
  be injected OR derived. No change to that guard was needed; new tests proving the real default
  binding simply avoid the `test_ensure_runtime_production_*` name prefix when they inject
  `restart=` for hermeticity (verified — see Phase 1 Implementation Notes).
- **Fix Scope item 2 ("Stale ⇒ orchestrator-owned rebuild step, never mcp-test") requires NO
  additional code once item 1's predicate is bound.** Read `ensure_runtime`'s existing STALE
  handling (legacy mode's `elif stale_check(): restart(); code, payload = probe(); ...`; M4 mode's
  `_route_non_serving("STALE", ...)` → `_recover_runtime`/`_await_compile_serving`): a True
  `stale_check()` ALREADY triggers `restart()` + a re-probe INSIDE the same `--ensure-runtime` call
  (which runs in the orchestrator process, never inside an `/mcp-test` subagent) before the verdict
  is returned — resolving to a healthy re-probe or `BLOCKED` (`mcp-runtime-unready`), never handing
  a stale runtime to `/mcp-test`. This machinery predates this bug (built for the M4 ownership work)
  and was simply unreachable because nothing bound a real `stale_check`. Wiring the predicate
  (Phase 1) therefore satisfies Fix Scope items 1 AND 2 together with no new state machine, exactly
  as the SPEC's Fix Scope item 1 promises ("no new state machine").
- **`stale_binary.py`'s own predicate needed no changes** — `test_stale_binary.py`'s existing
  hermetic git-fixture coverage (boot-before/after, non-native-only commits, bogus repo root,
  unparseable timestamp, custom globs, equal-timestamp boundary) was already complete; the gap was
  exclusively the missing production caller. Confirmed via grep: before this fix, the only
  references to `stale_binary` anywhere under `user/` were two **prose** lines in
  `user/skills/lazy-batch/SKILL.md` (~608, ~658) — zero code callers.

## Cross-feature Integration Notes

- **`docs/bugs/_archive/mcp-validation-peels-one-seam-per-loop/`** (sibling, Fixed + archived):
  that bug's SPEC explicitly flagged this one — "stale-runtime confounds inflate its `retry_count`
  escalation on non-defects" — and its own PHASES.md Cross-feature note says "Not touched by this
  fix — no file overlap; flagged here per the SPEC's own cross-reference, no action needed in this
  lane." Confirmed: no file overlap here either (that bug touched `user/skills/**` prose only; this
  bug touches `user/scripts/lazy_core.py` + tests only).
- **`docs/features/long-build-and-runtime-ownership/`** (Complete) owns `ensure_runtime`'s M4
  ownership-verdict contract and the Persistent-Service/Transient-Build split this fix routes
  rebuilds through unchanged — this bug adds a default binding for an existing injectable
  parameter (`stale_check`), no M4 contract change, no new verdict state.
- **SKILLS-lane items (Fix Scope items 3-4)** are OUT of this STATE-lane bug-fix pass's
  file-ownership grant (`user/skills/**` not owned here) — see "Deferred Follow-Up" below.

---

### Phase 1: Wire the F7 freshness predicate into `ensure_runtime`'s default `stale_check` binding

**Scope:** Add a production default binding — `_default_stale_check(repo_root, cfg)` — that derives
a real staleness signal from the boot-spawn stamp (`read_boot_stamp`, falling back to the
`.runtime.lock.json` recorded kernel `start_time` when no stamp exists) compared via
`stale_binary.native_source_newer_than` against the newest commit touching the repo's configured
`native_globs`. Replace `ensure_runtime`'s `if stale_check is None: stale_check = lambda: False`
default with this real binding. Fail-safe direction preserved throughout (no signal / any error ⇒
not stale). This makes the already-built, already-routed STALE verdict reachable — no new state
machine (SPEC D1).

**TDD:** yes. Unit tests of `_default_stale_check` (boot-before/after a native commit, the
no-boot-stamp lock fallback, no signal at all, custom `native_globs`, a bogus non-git repo root)
plus two integration tests calling `ensure_runtime` WITHOUT injecting `stale_check` (proving the
production default actually derives, not just the unit-level helper) were authored to prove the
wiring, not merely to characterize it — before this phase, `ensure_runtime`'s default was
`lambda: False` unconditionally, so a stale-and-derived-True scenario would have (falsely) resolved
`READY` with no `restart()` call; these tests fail against that prior default (verified by reading
the prior code path — `stale_check` was never reachable there at all) and pass against the fix.

**Status:** Complete

**Deliverables:**
- [x] `import stale_binary` added to `lazy_core.py` (previously orphaned — zero non-test callers
      anywhere under `user/`).
- [x] `_default_stale_check(repo_root, cfg)` added to `lazy_core.py` (sibling of
      `_default_frontend_probe`/`_default_sidecar_probe`'s config-driven-default pattern): reads
      `read_boot_stamp(repo_root)`, falls back to `read_runtime_lock(repo_root, config=cfg)`'s
      recorded `start_time` when absent, converts the epoch to ISO-8601 UTC, and calls
      `stale_binary.native_source_newer_than(boot_iso, Path(repo_root), globs=cfg["native_globs"])`.
      Any missing signal or predicate error reports `False` (fail-safe, D2) — never raises.
- [x] `ensure_runtime`'s `if stale_check is None:` default changed from `lambda: False` to
      `lambda: _default_stale_check(repo_root, cfg)`.
- [x] `ensure_runtime`'s docstring "Staleness" bullet corrected (previously claimed a
      `stale_check(artifact_hash)` signature that never matched the real zero-arg `stale_check()`
      callable — a pre-existing, unrelated inaccuracy fixed in passing since it directly documents
      the seam this bug wires).
- [x] Tests: 6 unit tests of `_default_stale_check` (native-commit-after-boot stale,
      native-commit-before-boot fresh, no-boot-stamp lock fallback, no signal at all, configured
      `native_globs` respected, bogus repo root never raises) + 2 tests calling `ensure_runtime`
      with NO `stale_check=` kwarg (proving the real production default derives from a real git
      repo + a real boot stamp, routing STALE→`restart()` when stale, and skipping `restart()`
      entirely when fresh).

**Implementation Notes (2026-07-12):** The two `ensure_runtime`-level tests deliberately do NOT use
the `test_ensure_runtime_production_*` name prefix reserved for the OS-signal-derivation guard
(`_PRODUCTION_BINDING_SIGNAL_KWARGS = {"boot_alive", "restart"}`) — they inject `restart=` for
hermeticity (asserting call *count*, not real process spawning), which that guard forbids under the
reserved prefix; `stale_check` itself is on the separate, always-allowed injection list, and here it
is genuinely NOT injected (proving the real default binds). One test-authoring correction along the
way: legacy-mode `ensure_runtime` maps a resolved "stale-rebuilt" status to `state: "STALE"` (per
`_LEGACY_STATUS_TO_STATE`), NOT `"READY"` — that is the correct, pre-existing legacy-mode contract
(M4 mode's `_recover_runtime` resolves all the way to `READY` after a stale rebuild; legacy mode's
verdict superset intentionally still reports `STALE` to signal that a rebuild occurred) — the test
asserts `state == "STALE"` + `health_code == 200` + `restart()` having fired, which together prove
the previously-unreachable verdict is now reachable and drove a real rebuild. Gate:
`python -m pytest user/scripts/test_lazy_core.py -q` → 1030 passed (0 failed), incl. all 8 new
stale_check tests. Files: `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "stale_check" -q`
is GREEN, and reading the pre-fix `ensure_runtime` default (`stale_check = lambda: False`,
unconditional) confirms the new tests would have failed against it (a real boot-stamp-derived stale
signal would never have reached `restart()`).

**Runtime Verification** *(the operator/manual live cold-boot smoke — NOT claude-config CI, per
`user/scripts/CLAUDE.md`'s documented convention)*:
- [ ] <!-- verification-only --> On a real AlgoBooth checkout with the dev runtime warm and a
  native-source (`src-tauri`/`crates`) commit landing AFTER the runtime's boot stamp,
  `python3 user/scripts/lazy-state.py --ensure-runtime --repo-root <real-AlgoBooth-checkout>`
  reports `state: STALE` → an automatic rebuild → `state: READY` on the re-probe, instead of a bare
  `READY` masking the staleness. Confirmable only in a real AlgoBooth checkout with a genuinely
  stale binary — deferred to that repo's own observation on the next live `/lazy-batch` run.

**MCP Integration Test Assertions:** N/A — no MCP-observable surface in claude-config itself; the
fix's real-world effect (fewer stale-confound `retry_count` burns, fewer hand-invented
`dev:restart` rituals) is only observable in a live AlgoBooth `/lazy-batch` run.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `_default_stale_check` + the `stale_check` default-binding swap +
  the `stale_binary` import + the docstring correction (verified exists; `ensure_runtime` at
  line ~8770 pre-edit).
- `user/scripts/test_lazy_core.py` — 8 new tests (verified exists).

**Testing Strategy:** Hermetic real-git-repo fixtures (mirroring `test_stale_binary.py`'s own
`_make_git_repo_with_origin`-style setup already established in this file) for the unit tests; two
`ensure_runtime`-level integration tests that derive (not inject) the signal, per this file's
documented production-binding test discipline.

**Integration Notes for Next Phase:** `stale_binary.py` needed no changes at all — only its missing
production caller. The remaining Fix Scope items (3: a BLOCKED.md freshness fingerprint guard; 4:
the `lazy-batch/SKILL.md` prose-accuracy line) live entirely in `user/skills/**`, out of this
STATE-lane bug-fix pass's file-ownership grant — see "Deferred Follow-Up" below. This bug has no
second STATE-lane phase.

**Completion (gate-owned):** N/A for this bug — `**Status:**` and `FIXED.md` are written directly
per this bug's operator-directed workflow (PHASES then implement, no pipeline `__mark_fixed__` gate
invoked in this lane) — see `FIXED.md`.

---

## Deferred Follow-Up (SKILLS-lane — NOT gating this bug's Fixed status)

Fix Scope items 3 and 4 require edits under `user/skills/**`, explicitly OUT of this STATE-lane
bug-fix subagent's file-ownership grant this pass. Both are genuine follow-up, not blockers: the
field-observed defect (a stale runtime minting a false `mcp-validation` BLOCKED against a pre-fix
binary) is fixed by Phase 1 alone — once `stale_check` is wired, `ensure_runtime` NEVER returns a
stale-and-serving verdict to the caller without first rebuilding (see "Validated Assumptions"
above), so `/mcp-test` can no longer be dispatched against a provably-stale binary via the
`--ensure-runtime` gate `/lazy-batch` Step 1d.0 already consults.

1. **Item 3 — BLOCKED.md freshness fingerprint guard.** `user/skills/_components/lazy-batch-prompts/
   cycle-base-prompt.md` R14 and `repos/algobooth/.claude/skills/mcp-test/SKILL.md`'s "On a genuine"
   BLOCKED-authoring contract should record the runtime fingerprint (boot stamp + HEAD sha) a
   `blocker_kind: mcp-validation` BLOCKED.md was observed against, and refuse minting one when the
   fingerprint would classify STALE per this bug's fix — a defense-in-depth guard against the
   residual race window between an `--ensure-runtime` READY-and-fresh verdict and a later native
   commit landing before `/mcp-test` actually runs. This is a genuinely separate (narrower, race-
   window-only) concern from the field-observed defect this bug fixes.
2. **Item 4 — prose-accuracy line.** `user/skills/lazy-batch/SKILL.md` ~line 658 previously narrated
   the STALE→`dev:restart` wiring as already working (aspirational, pre-fix). It is now TRUE as of
   Phase 1 above — the line needs no correction, only a cross-check at the next SKILLS-lane touch of
   that file to confirm it still accurately describes the (now real) behavior.

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews. This
bug's fix landed via a direct operator-directed bug-fix subagent pass — PHASES then implement, no
pipeline `__mark_fixed__` gate invoked in this lane.)_
