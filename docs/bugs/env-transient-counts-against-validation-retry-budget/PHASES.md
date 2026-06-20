# Implementation Phases — Self-inflicted env transients counted against validation-retry budget

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this fix lives entirely in the claude-config harness (`lazy_core.py` Python + a prompt component + SKILL/doc prose). claude-config has **no MCP-reachable app surface** (it is the harness itself, not an app); the fix is validated by the hermetic injected-probe smoke harnesses (`lazy_core` characterization tests + `lazy-state.py --test` / `bug-state.py --test`), which ARE the runtime-equivalent verification surface. This is the structural "no app integration / tooling" untestable class per `docs/features/mcp-testing/SPEC.md`, not an audio claim.

**Status:** In-progress

## Validated Assumptions

All load-bearing assumptions for this fix are **code-provable** from the harness source (read at planning time) — there is no live cross-boundary runtime behavior to spike, because the verification surface is the hermetic injected-probe test harness, not a running Tauri/MCP process. The Step 2.7 runtime-spike gate is therefore SKIPPED with that reason. Ground truth confirmed during the touchpoint audit:

- **`lazy_core.ensure_runtime` (`user/scripts/lazy_core.py:6206`)** — the orchestrator readiness gate. Its M4 **Phase 3: Health** block (`:6506-6518`) returns `READY` the instant `code == 200` for an owned, current runtime — there is NO sidecar-pipe (`is_connected`) assertion between `code == 200` and the READY verdict. Confirmed: the only readiness dimensions are HTTP `/health` (`health_code`) and the OPTIONAL `_mcp_tool_in_payload` (`:6156`, vacuously true when `mcp_tool_name == ""`, the default at `:6119`). This is the discriminator gap (SPEC Finding 1).
- **`_ENSURE_RUNTIME_DEFAULT_CONFIG` (`:6116-6128`)** — the parameterization seam. AlgoBooth specifics (`health_url`, `restart_command`, `port`, `lock_filename`, `mcp_tool_name`) are already config keys, repo-agnostic-default. A new `sidecar_status_url` / `assert_sidecar_connected` key follows the exact same pattern (default = check skipped, repo-agnostic).
- **`ensure_runtime` injection surface (`:6206-6220`)** — already takes injected `probe`/`restart`/`stale_check`/`read_lock`/`sleep`/`write_lock`/etc. callables so `--test` is hermetic. A new injected `sidecar_check` callable (default no-op = check skipped) follows the established pattern; `_ensure_runtime_m4` threads it the same way it threads `stale_check`.
- **`validation_escalation` (`:328-359`)** — the predicate is `blocker_kind == "mcp-validation" AND retry_count >= 2`. Confirmed CORRECT (SPEC Finding 3) — it is NOT touched. The fix prevents an env-transient from REACHING it wearing the `mcp-validation` label.
- **`mcp-runtime-unready`** — the existing escalation-immune `blocker_kind`. Confirmed wired at `lazy-batch/SKILL.md:599` (HIJACKED route) — the correct destination class. The fix routes the pipe-dead-but-HTTP-healthy case into it.
- **`mcp-test-runtime` prompt variants (`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md:257-288`)** — confirmed: the `runtime-up` variant (`:257-268`) has NO `NEEDS_RUNTIME` escape; that escape (`:284-287`) lives ONLY in the `no-runtime` variant. The runtime-up cycle's only non-pass terminals are the `mcp-validation`-flavored `BLOCKED.md` enumerated in `skill-mcp-test-common` (`:230, :246-255`). This is SPEC Finding 2.
- **`mcp-test/SKILL.md` Step 2 (`repos/algobooth/.claude/skills/mcp-test/SKILL.md:146-201`)** — confirmed: line 162 already says "If the runtime appears dead mid-cycle … surface `NEEDS_RUNTIME`", and the standalone path at `:186` already probes `get_sidecar_status` → `is_connected: true`. The orchestrated path inherits neither as a writable terminal. The mirror brings the orchestrated runtime-up prose into agreement.
- **Test harness** — `ensure_runtime`/M4 fixtures live in `user/scripts/test_lazy_core.py` (`:18053-18560+`) using injected `probe`/`stale_check`/`read_lock`/`sleep` callables. A new `sidecar_check`-disconnected fixture follows that exact pattern. `lazy-state.py --test` / `bug-state.py --test` byte-pinned baselines must stay green (they do not exercise sidecar readiness, so they should be unaffected — verified as part of the gate).

## Touchpoint Audit Table

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `ensure_runtime` (:6206), `_ensure_runtime_m4` (:6426), `_ENSURE_RUNTIME_DEFAULT_CONFIG` (:6116), `_runtime_verdict` (:6377), `_recover_runtime` (:6521), `_default_runtime_probe` (:6131), `validation_escalation` (:328) | refactor | Add a new config key + injected `sidecar_check` callable + a `_default_sidecar_probe`; thread `sidecar_check` through `ensure_runtime` → `_ensure_runtime_m4` Phase 3 Health (after `code == 200`, before READY). REUSE the `stale_check` plumbing as the template (same default-no-op + injection shape). Do NOT touch `validation_escalation` — it is correct. Do NOT add a sidecar dimension to legacy mode (legacy callers never run mcp-test). |
| `user/scripts/test_lazy_core.py` | yes | `test_ensure_runtime_m4_*` fixtures (:18225-18560+) using injected probes | refactor (add fixtures) | Add fixtures: (a) owned+current+health-200 but sidecar disconnected → recovery → READY-or-BLOCKED; (b) sidecar-check default-skipped preserves the existing READY verdict (regression guard); (c) repo-agnostic default = no sidecar assertion. REUSE the injected-callable fixture pattern from the adjacent M4 tests. |
| `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` | yes | `@section mcp-test-runtime variant=runtime-up` (:257), `variant=no-runtime` (:270, carries `NEEDS_RUNTIME`), `@section skill-mcp-test-common` (:206) | refactor | Add a sidecar-dead-mid-cycle runtime-readiness terminal to the `runtime-up` variant so a cycle that detects `is_connected: false` returns `NEEDS_RUNTIME` (or writes `BLOCKED.md` `blocker_kind: mcp-runtime-unready`) instead of an `mcp-validation` BLOCKED. Re-run `project-skills.py` after editing. |
| `repos/algobooth/.claude/skills/mcp-test/SKILL.md` | yes | Step 2 (:146-201, "appears dead → NEEDS_RUNTIME" :162, `is_connected` probe :186), Step 5 sentinel writer | refactor | Mirror the runtime-readiness-vs-validation distinction into the orchestrated runtime-up prose so standalone and orchestrated paths agree on "HTTP-healthy but pipe-dead ⇒ runtime-unready, NOT mcp-validation". Picked up by per-repo `project-skills.py`. |
| `user/skills/lazy-batch/SKILL.md` | yes | Step 1d.0 readiness prose (:583-608), `--ensure-runtime` routing on `state`, `mcp-runtime-unready` route (:599) | refactor | Document the sidecar-pipe dimension of `--ensure-runtime` and that a pipe-dead-but-HTTP-healthy runtime now routes to `mcp-runtime-unready` (escalation-immune), not a dispatch. SECONDARY (prose only). |
| `user/scripts/lazy_core.py` `validation_escalation` (:328) | yes | predicate `blocker_kind=="mcp-validation" AND retry_count>=2` | **NO CHANGE** | Verified correct (SPEC Finding 3). The fix keeps env-transients from reaching it with the `mcp-validation` label. |
| AlgoBooth `package.json` `dev:kill`/`dev:restart` | n/a (NOT in this repo) | — | spin-off | Leg C (zombie-reaping) is an AlgoBooth change, NOT a claude-config change. See "Spin-off (Leg C)" below — `--enqueue-adhoc --type bug` into AlgoBooth if the operator wants the reaping hardening. |

**Drift correction (Step D):** No mechanical drift — every SPEC-named path/symbol verified to exist at the cited location. No genuine design fork: the HARD-vs-soft gate question (Open Question 1) is a scope-class sizing decision, resolved in-cycle below under D7, not a NEEDS_INPUT product fork.

## ⚖ Policy disclosures (D7 — completeness-first)

- ⚖ policy: sidecar gate HARD vs soft → HARD when mcp-test about to run (config-gated)
- ⚖ policy: Leg C zombie-reaping → spin off to AlgoBooth (out of this repo)

**Rationale (HARD gate, Open Question 1):** The SPEC's own recommendation is HARD (assert `is_connected` when a sidecar is configured, only at mcp-test time — the only moment MCP-functional readiness is load-bearing), parameterized so non-AlgoBooth repos opt in via config (default = check skipped). A soft "warn + dispatch" gate would NOT fix the accounting defect — it would still dispatch against a pipe-dead runtime, leaving the `mcp-validation` mislabel in place. The end-state PRODUCT behavior differs only by completeness here (HARD is the option that actually closes the defect), so this is scope-class: take the complete path in-cycle. The HARD gate is config-gated (repo-agnostic default off) so it is non-breaking for every other repo.

## Spin-off (Leg C — out of scope, AlgoBooth)

`dev:kill`/`dev:restart` zombie-reaping (force-kill the node process holding the `\\.\pipe\…:3333` handle so the transient self-clears) is an **AlgoBooth `package.json` change, NOT a claude-config change** (SPEC Fix scope C). Phases A+B here fix the harness accounting defect WITHOUT it — the enriched gate catches the pipe-dead state and re-boots until clean (accepting at most one extra boot cycle). Leg C is a reliability optimization, not a correctness requirement.

**Reverse-reference contract:** if/when Leg C is wanted, enqueue it as an AlgoBooth bug via `lazy-state.py --enqueue-adhoc --type bug` (targeting the AlgoBooth repo) and add the spun-off id back into this section. As of this planning cycle Leg C is **deferred, not spun off** — A+B alone resolve the P2 accounting defect, so no spin-off was enqueued this cycle (no operator request, and the deferral is documented rather than silently dropped). A future operator decision can enqueue it.

## Cross-feature Integration Notes

(No `**Depends on:**` block in the SPEC — `(none)`. This is a self-contained harness fix; no upstream PHASES.md to integrate against.)

---

### Phase 1: Enrich the orchestrator readiness gate with a sidecar-pipe dimension (PRIMARY — Leg A)

**Scope:** Add a sidecar-pipe (`is_connected`) readiness assertion to `lazy_core.ensure_runtime`'s M4 **Phase 3: Health** evaluation, so a runtime that is HTTP-healthy (`/health == 200`) but MCP-functionally dead (zombie-held named pipe → sidecar disconnected) routes to runtime RECOVERY (a `dev:restart` to reap the zombie) and, if it stays disconnected, to a `mcp-runtime-unready`-bound verdict — instead of returning READY and letting the orchestrator dispatch an mcp-test cycle against a dead runtime. Repo-agnostic: parameterized in `_ENSURE_RUNTIME_DEFAULT_CONFIG` (default = check skipped) + an injected `sidecar_check` callable (default no-op) so `--test` stays hermetic and non-AlgoBooth repos are unaffected.

**Deliverables:**
- [x] Add `assert_sidecar_connected: false` (default off) + `sidecar_status_url` (default `http://localhost:3333/tools/get_sidecar_status`) to `_ENSURE_RUNTIME_DEFAULT_CONFIG` (`:6116`), following the existing config-key pattern. Repo-agnostic default = sidecar assertion skipped.
- [x] Add a `_default_sidecar_probe(sidecar_status_url) -> bool` helper (stdlib `urllib`, best-effort, never raises — mirrors `_default_runtime_probe` at `:6131`) returning `is_connected` from the `get_sidecar_status` payload (False on any error / missing field). Factored the payload-parsing into a pure `_sidecar_is_connected(payload)` helper (directly unit-tested).
- [x] Add a `sidecar_check=None` injected parameter to `ensure_runtime` (`:6206`); when `None` AND `cfg["assert_sidecar_connected"]` is truthy, bind `_default_sidecar_probe`; when the config flag is falsy, bind a no-op `lambda: True` (skip = treated as connected). Thread `sidecar_check` into `_ensure_runtime_m4`.
- [x] In `_ensure_runtime_m4` **Phase 3: Health**: after `code == 200` and BEFORE the `READY` verdict, call `sidecar_check()`. If it returns False (pipe dead despite HTTP 200), route to `_recover_runtime(cfg, "DEAD", ownership_verified=True, …, sidecar_check=sidecar_check)` (the existing bounded-recovery path — forces a `dev:restart` that reaps the stale pipe). `_recover_runtime` re-asserts the pipe on each healthy HTTP re-probe, so a restart that fixes HTTP but not the pipe does NOT count as recovered → on exhaustion `BLOCKED` with a `terminal_blocker` → the orchestrator writes `blocker_kind: mcp-runtime-unready` (escalation-immune), NOT a dispatch.
- [x] Confirm `validation_escalation` (`:328`) is UNCHANGED (predicate is correct — SPEC Finding 3). Verified untouched.
- [x] Tests: hermetic `test_lazy_core.py` fixtures (see Runtime Verification below — these are real unit tests of the gate, the verification surface for this docs/script-only repo).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` (or the pytest selection for the new fixtures) passes a new test asserting that an owned+current+`health==200` runtime with an injected `sidecar_check` returning False routes through `_recover_runtime` (restart attempted) rather than returning a bare `READY` — and that with `assert_sidecar_connected` defaulted off (no injected `sidecar_check`), the verdict is byte-identical to the current READY path (regression guard).

**Runtime Verification** *(checked by the hermetic smoke harness — NOT by the implementation step):*
- [ ] <!-- verification-only --> Sidecar-disconnected-despite-200 fixture: `ensure_runtime(..., probe=200, sidecar_check=lambda: False, ...)` for an owned+current runtime yields `state != "READY"` on the first pass and enters recovery; on persistent disconnect the terminal verdict is `BLOCKED` with a non-null `terminal_blocker` (routable to `mcp-runtime-unready`).
- [ ] <!-- verification-only --> Default-skip regression fixture: `assert_sidecar_connected` falsy (default) ⇒ no sidecar assertion ⇒ the owned+current+200 verdict is exactly `READY` (existing `test_ensure_runtime_m4_ready_when_owned_current_healthy` behavior preserved).
- [ ] <!-- verification-only --> Repo-agnostic default fixture: a config WITHOUT `assert_sidecar_connected` (legacy config dict) does not crash and treats the sidecar as connected (skipped).
- [ ] <!-- verification-only --> `lazy-state.py --test` AND `bug-state.py --test` byte-pinned baselines stay green (the sidecar dimension is gated off in those fixtures → no baseline drift).

**MCP Integration Test Assertions:**
N/A — no MCP-reachable runtime surface in claude-config (the harness repo). The hermetic injected-probe fixtures above ARE the runtime-equivalent verification for this repo, per the `**MCP runtime:** not-required` header.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `_ENSURE_RUNTIME_DEFAULT_CONFIG` (:6116), new `_default_sidecar_probe`, `ensure_runtime` signature + `sidecar_check` binding (:6206-6349), `_ensure_runtime_m4` Phase 3 Health (:6506-6518). REUSE the `stale_check` injection pattern; do NOT touch `validation_escalation`.
- `user/scripts/test_lazy_core.py` — new sidecar-readiness fixtures adjacent to the M4 block (:18225+).

**Testing Strategy:**
Hermetic — all probes/restart/sidecar callables injected (no real runtime, network, or sleep). Assert the routing (READY vs recovery vs BLOCKED) and the never-regress default-off path. Run the full state-script gate: `lazy_core` characterization tests + `lazy-state.py --test` + `bug-state.py --test` (Coupling Rule: a `lazy_core` change must keep BOTH state suites green).

**Integration Notes for Next Phase:**
- The gate now produces a `BLOCKED`/recovery verdict for the pipe-dead case; Phase 2 gives the *mid-cycle* (cycle-subagent-detected) pipe-dead case a matching runtime-readiness terminal so BOTH the upstream-gate path AND the in-cycle path avoid the `mcp-validation` mislabel.
- `assert_sidecar_connected` is OFF by default; AlgoBooth opts in via its config override. The cycle prose in Phase 2 must NOT assume the gate always asserts sidecar — it is the SECOND line of defense for repos that enable it, AND the only defense the cycle itself owns when the gate is off.

**Implementation Notes (2026-06-20 — Phase 1 complete, executed INLINE, test-first):**
- **Work completed:** Added two config keys (`assert_sidecar_connected: False`, `sidecar_status_url`) to `_ENSURE_RUNTIME_DEFAULT_CONFIG`; a pure `_sidecar_is_connected(payload)` parser + a `_default_sidecar_probe(url)` urllib probe (both never-raise, mirroring `_default_runtime_probe`); a `sidecar_check=None` injected param on `ensure_runtime` (bound to the real probe only when the config flag is truthy, else `lambda: True`); threaded `sidecar_check` into `_ensure_runtime_m4` and its `_recover_runtime` calls; the Phase-3 Health block now routes a `code==200`-but-`sidecar_check()==False` runtime into recovery instead of a bare READY, and `_recover_runtime` re-asserts the pipe on each healthy re-probe so a persistent zombie ends BLOCKED.
- **TDD:** 5 hermetic fixtures written FIRST and confirmed RED (TypeError on unknown kwarg / AttributeError on missing helper) for the right reason, then GREEN after impl: disconnected-routes-to-recovery→BLOCKED, default-off-preserves-READY (byte-identical regression guard), legacy-config-no-KeyError, connected-yields-READY, default-probe-parses-is_connected.
- **Integration notes:** `sidecar_check is None`/`lambda: True` (default-off) preserves the existing READY path byte-for-byte — verified by the regression fixture and by all three smoke suites staying green (lazy_core 683/683, `lazy-state.py --test`, `bug-state.py --test`). `validation_escalation` was NOT touched.
- **Pitfalls:** the strict `is_connected is True` check (not truthy) means a payload carrying the string `"true"` is treated as disconnected (fail-safe toward recovery) — asserted directly.
- **Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

---

### Phase 2: Give the runtime-up cycle a runtime-readiness terminal (PRIMARY — Leg B)

**Scope:** Add a sidecar-dead-mid-cycle runtime-readiness escape to the `mcp-test-runtime` **runtime-up** prompt variant so a cycle that detects the dead pipe (`get_sidecar_status` → `is_connected: false`) returns `NEEDS_RUNTIME` (or writes `BLOCKED.md` `blocker_kind: mcp-runtime-unready`) instead of an `mcp-validation` `BLOCKED.md`. Mirror the runtime-readiness-vs-validation distinction into `mcp-test/SKILL.md` (orchestrated path) so standalone and orchestrated agree, and document the new dimension in `lazy-batch/SKILL.md` Step 1d.0 prose. Re-run `project-skills.py` after editing the component.

**Workstation-only (no cloud divergence):** the `mcp-test-runtime` sections are `modes=workstation`; `/lazy-batch-cloud` defers MCP and never reaches an mcp-test cycle. Verified: no `/lazy-batch-cloud` coupled-pair edit is needed for this leg (SPEC Leg B note). The prompt component is shared, so the single edit projects to both pipelines via `project-skills.py`.

**Deliverables:**
- [x] In `cycle-base-prompt.md` `@section mcp-test-runtime variant=runtime-up`: added an explicit sidecar-readiness check + terminal — `get_sidecar_status.is_connected: false` (HTTP-healthy but pipe dead — a self-inflicted env transient, NOT a code failure) ⇒ do NOT run the engine, do NOT write an `mcp-validation` BLOCKED, return the single line `NEEDS_RUNTIME`. Wording parallels the `no-runtime` variant's `NEEDS_RUNTIME` escape.
- [x] In `cycle-base-prompt.md` `@section skill-mcp-test-common`: added a "VALIDATION-BLOCKED IS FOR CODE/ENGINE FAILURES ONLY" clause clarifying the `mcp-validation` BLOCKED terminal is for code/engine failures and a sidecar-pipe-dead state is EXPLICITLY EXCLUDED (routes to the runtime-readiness terminal), so the escalation budget is never charged an env transient.
- [x] In `mcp-test/SKILL.md` Step 2 orchestrated path: made "appears dead mid-cycle → NEEDS_RUNTIME" explicitly cover the HTTP-healthy-but-`is_connected: false` case, referencing the standalone path's `get_sidecar_status` probe as the discriminator.
- [x] In `lazy-batch/SKILL.md` Step 1d.0 prose: documented the sidecar-pipe dimension of `--ensure-runtime` and that a pipe-dead-but-HTTP-healthy runtime routes to `mcp-runtime-unready` (escalation-immune), not a dispatch. Also extended the `--ensure-runtime` CLI doc in `user/scripts/CLAUDE.md` (Mandatory Rule 8).
- [x] Ran `python ~/.claude/scripts/project-skills.py` (80 skills, 0 errors) and `lint-skills.py --check-projected --check-capabilities` (clean). NOTE: the `mcp-test-runtime` runtime-up section of `cycle-base-prompt.md` is parsed at RUNTIME by `lazy_core.emit_cycle_prompt`'s `@section` grammar — it is NOT a `!cat` injection, so it does NOT appear in `skills-projected/` SKILL output; its correctness is asserted by the `test_emit_cycle_prompt_*` suite (all green) + the source `@section` placement check. The discoverable per-repo projection here is `claude-config` (the `algobooth` repo's skill-config is not present in this projection root); the edit is to the shared component, so it reaches every consumer via the runtime parser regardless.

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/lint-skills.py` (and `--check-projected`) passes with no broken-injection / embedded-pattern errors after the edits, and the projected `cycle-base-prompt` runtime-up section contains the new `NEEDS_RUNTIME`-for-pipe-dead terminal (grep-verifiable in `skills-projected/`).

**Runtime Verification** *(checked by lint + projection inspection — NOT by the implementation step):*
- [ ] <!-- verification-only --> `lint-skills.py --check-projected --check-capabilities` is clean after the component + SKILL edits (no broken `!cat` injection, no embedded-pattern regression).
- [ ] <!-- verification-only --> The projected `cycle-base-prompt` runtime-up variant (in both `skills-projected/_default/` and `skills-projected/algobooth/`) contains the sidecar-dead → `NEEDS_RUNTIME` terminal, and the `no-runtime` variant's existing `NEEDS_RUNTIME` escape is unchanged (no accidental cross-variant edit).

**MCP Integration Test Assertions:**
N/A — prompt/doc edits in the harness repo; verified by `lint-skills.py` + projection inspection, not a live MCP runtime (per the `**MCP runtime:** not-required` header).

**Prerequisites:**
- Phase 1: the enriched gate establishes `mcp-runtime-unready` as the canonical destination for a pipe-dead runtime; Phase 2's cycle terminal must name the SAME class so the upstream-gate path and the in-cycle path are consistent. (Phase 2 is doc-only and could land independently, but is sequenced second so its prose references the Phase 1 verdict semantics accurately.)

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — `mcp-test-runtime` runtime-up variant (:257-268) + `skill-mcp-test-common` BLOCKED-terminal scoping (:230, :246-255).
- `repos/algobooth/.claude/skills/mcp-test/SKILL.md` — Step 2 orchestrated runtime-readiness prose (:151-163).
- `user/skills/lazy-batch/SKILL.md` — Step 1d.0 `--ensure-runtime` sidecar-dimension prose (:583-608).
- `~/.claude/skills-projected/**` — regenerated by `project-skills.py` (generated output, not hand-edited; not git-tracked per CLAUDE.md "What's NOT Tracked").

**Testing Strategy:**
`lint-skills.py` (basic + `--check-projected --check-capabilities`) is the gate for component/SKILL edits. Diff the projected `cycle-base-prompt` before/after to confirm the new terminal expanded into both the default and algobooth projections. No coupled-pair (`/lazy-batch-cloud`) mirror is required — verified workstation-only.

**Integration Notes for Next Phase:**
- This is the terminal phase. After both phases land, the self-inflicted env transient (zombie-held sidecar pipe) is caught upstream by the enriched gate (Phase 1, when AlgoBooth enables the config flag) AND has an escalation-immune mid-cycle terminal (Phase 2, when the cycle itself detects it) — closing both halves of the SPEC's two-part discriminator gap without weakening `validation_escalation`.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed` and writes `FIXED.md` once both phases' verification passes (the `/mcp-test` → coverage-audit tail). This plan never flips the top-level status itself.

**Implementation Notes (2026-06-20 — Phase 2 complete, executed INLINE):**
- **Work completed:** Edited the shared `cycle-base-prompt.md` `variant=runtime-up` section to add a SIDECAR-PIPE READINESS terminal (`is_connected: false` ⇒ `NEEDS_RUNTIME`, never an `mcp-validation` BLOCKED) and a "VALIDATION-BLOCKED IS FOR CODE/ENGINE FAILURES ONLY" scoping clause in `skill-mcp-test-common`. Mirrored the distinction into `mcp-test/SKILL.md` Step 2 (orchestrated "appears dead" now explicitly covers HTTP-healthy-but-pipe-dead, citing the `get_sidecar_status` discriminator) and documented the sidecar dimension in `lazy-batch/SKILL.md` Step 1d.0 + the `user/scripts/CLAUDE.md` `--ensure-runtime` CLI doc.
- **Verification:** `project-skills.py` (80 skills, 0 errors), `lint-skills.py --check-projected --check-capabilities` clean, and the full `test_lazy_core.py` suite green (683/683) incl. all `test_emit_cycle_prompt_*` (the runtime-parser is the real consumer of the runtime-up section — it is NOT a `!cat` projection, so the projected SKILLs do not carry it; the emission tests + source `@section` placement are the correctness surface).
- **Coupled-pair note:** the `mcp-test-runtime` sections are `modes=workstation`; `/lazy-batch-cloud` defers MCP and never reaches mcp-test → NO cloud coupled-pair edit needed (verified, matches the SPEC Leg B note).
- **Files modified:** `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, `repos/algobooth/.claude/skills/mcp-test/SKILL.md`, `user/skills/lazy-batch/SKILL.md`, `user/scripts/CLAUDE.md`.
