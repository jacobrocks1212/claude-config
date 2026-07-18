# Implementation Phases — Input-audit obligation fires (mis-targeted) after a zero-commit failed spec cycle

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress — both phases implemented, validation pending (routes to the `__mark_fixed__` completion gate).

**MCP runtime:** not-required — claude-config is a pure-Python harness repo (state-machine scripts); validation is the in-file `--test` smoke harness + `pytest tests/test_lazy_core/` + `lazy_parity_audit.py`. No Tauri/MCP runtime surface exists (cross-checked: this repo has no `.claude/skill-config/mcp-tool-catalog.md`, so the MCP tool-existence audit no-ops).

## Validated Assumptions

Every load-bearing assumption in this fix is **code-provable** — pure Python logic verified by reading source and asserted by hermetic `--test` fixtures. There is NO runtime-coupled assumption and NO user-facing surface (this is an internal orchestrator state-machine fix), so the reachability axiom does not apply and the Runtime Assumption Validation gate is skipped with that reason.

- **The zero-commit signal is available at the arming point.** `record_audit_obligation` is called (`lazy-state.py:12784-12788`, `bug-state.py:8640-8644`) with the live cycle marker still readable — the marker carries `begin_head_sha` (snapshotted at `--cycle-begin`; see `user/scripts/CLAUDE.md` → `--cycle-begin`), and current HEAD is resolvable, so `begin_head_sha != HEAD` is the exact zero-commit delta signal. Confirmed by reading `record_cycle_commit_bracket` (`ledgers.py:391-434`), which computes the identical `begin_sha == end_sha → None` skip six lines later at the same handler point.
- **The obligation dict is the natural carrier for the correct end sha.** `record_audit_obligation` writes `marker["audit_obligation"] = {"item_id", "cycle_kind"}` (`markers.py:3410`); the withhold branch reads it back via `pending_audit_obligation()` (`lazy-state.py:14140`, `bug-state.py:9759`). Adding a `cycle_commit_sha` (+ `cycle_summary`) key at arm-time — when begin/end are both known — makes the correct sha available to the emit command without re-derivation or a positional `HEAD~1` guess. Verified: nothing else reads the obligation dict shape (only these two withhold branches).
- **These are coupled-pair edits.** `record_audit_obligation` and `build_input_audit_emit_command` live in shared `lazy_core` and are called identically from both state scripts. `lazy_parity_audit.py` must stay exit 0 after the changes; both in-file `--test` harnesses and `pytest tests/test_lazy_core/` are the regression net.

## Cross-feature Integration Notes

No hard dependency on any incomplete upstream. The obligation mechanism this fix corrects was introduced by **`mechanize-prose-only-orchestrator-contracts` (b) / D2-A** (the §1d.5 prose→mechanical-withhold promotion) — a completed harness feature; the commit-delta gate was simply never part of its arming logic. This fix closes that omission on the same code path (see SPEC `## Evidence Collected → Git History`).

---

### Phase 1: Gate obligation arming on a non-empty commit delta (Fix Site A)

**Status:** Complete

**Scope:** A zero-commit (failed / no-op) cycle close of an `AUDITED_CYCLE_KIND` cycle arms **no** audit obligation — there is no authored SPEC/PHASES delta to audit. On a real-commit close, arming proceeds AND the obligation records the bracket's **actual end commit** (current HEAD) and its subject line, so Phase 2 can bind the correct sha instead of a positional `HEAD~1`. Coupled-pair edit across shared `lazy_core` + both state-script call sites.

**Deliverables:**
- [x] `record_audit_obligation` (`user/scripts/lazy_core/markers.py`) accepts the closing bracket's commit-delta signal (keyword params `begin_head_sha` + resolved `end_sha`) and is a **no-op on the obligation field** (arms nothing, clears nothing — preserves any prior obligation) when the delta is empty (`not end_sha or end_sha == begin_head_sha`). The kind check (`cycle_kind in AUDITED_CYCLE_KINDS`) is retained as the first gate; the commit-delta gate is added beneath it, reusing `record_cycle_commit_bracket`'s exact zero-commit oracle (NOT gated on its `None` return).
- [x] On a real-commit arm, the obligation dict additionally carries `cycle_commit_sha` (the resolved end commit / current HEAD) and `cycle_summary` (that commit's `%s` subject). The `{item_id, cycle_kind}` keys are unchanged; the two new keys are added.
- [x] The `--cycle-end` call site in `lazy-state.py` passes the commit-delta signal: resolves HEAD via `lazy_core.head_sha_snapshot`, reads `begin_head_sha` from `_tl_cycle`, and resolves the subject via the new `lazy_core.head_commit_subject` (skipped on the zero-commit path). Runs BEFORE `record_cycle_commit_bracket`; computes the delta directly.
- [x] The coupled-pair mirror at `bug-state.py` passes the identical signal (same shape; `bug-state.py` uses `feature_id`/`sub_skill` marker keys as it does today).
- [x] Tests: `record_audit_obligation`'s gate is covered directly in `test_markers.py` (3 cases — real-commit arm records the end sha + summary; zero-commit / missing-end-sha arms nothing and preserves a prior obligation; non-audited kind is a no-op regardless of delta); existing `test_ledgers.py` audit-obligation coverage updated for the new signature. `lazy_parity_audit.py --repo-root .` stays exit 0. (⚖ scope-class: the state-script arming path is covered via the pytest suite — including the existing real `lazy-state.py` subprocess arm→withhold e2e test — rather than new in-file `--test` fixtures, avoiding byte-pinned smoke-baseline regeneration; the bug-state.py mirror is guaranteed by the parity audit.)

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test && python3 user/scripts/bug-state.py --test && python3 -m pytest user/scripts/tests/test_lazy_core/ -q && python3 user/scripts/lazy_parity_audit.py --repo-root .` all pass, with the new zero-commit-no-arm fixture proving the obligation is unset after a zero-commit audited close (it fails RED before the gate is added: current code arms unconditionally on kind).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core/markers.py` — add the commit-delta gate + the two new obligation keys to `record_audit_obligation`.
- `user/scripts/lazy-state.py` — `--cycle-end` handler passes the delta signal (line ~12784).
- `user/scripts/bug-state.py` — coupled-pair mirror (line ~8640).
- `user/scripts/tests/test_lazy_core/test_markers.py` (or the seam's existing test module) — direct helper coverage.
- In-file `--test` fixtures registered in each state script's test-list block.

**Testing Strategy:**
Hermetic — the state scripts' `--test` fixtures build temp cycle/run markers and assert the on-disk `audit_obligation` field after a simulated `--cycle-end` at a fixed vs. advanced HEAD. `lazy_core` helper tested directly via pytest with injected begin/end shas. No network, no runtime. Baselines: if a `--test` fixture is added, regenerate the byte-pinned smoke baseline via the `_normalize_smoke_output` helper (never by hand) per `user/scripts/CLAUDE.md` → Testing.

**Integration Notes for Next Phase:**
- The obligation dict now carries `cycle_commit_sha` (real end commit) and `cycle_summary` — Phase 2 reads these from `pending_audit_obligation()` instead of the hardcoded `HEAD~1` / latest-commit-subject proxy.
- Because Fix A means a zero-commit cycle never arms, in practice Phase 2's emit path only ever runs for a real-commit obligation — but Phase 2 must still fail safe if the sha key is absent (legacy/partial obligation): fall back to the current `HEAD~1` proxy rather than crashing.
- `record_audit_obligation`'s signature changed — both call sites (features + bug) are updated in THIS phase, so no dangling caller crosses the phase boundary.

---

### Phase 2: Bind the emit command to the bracket's actual end commit (Fix Site B)

**Status:** Complete

**Scope:** When an audit legitimately fires, `build_input_audit_emit_command` binds `cycle_commit_sha` (and `cycle_summary`) to the cycle bracket's **actual end commit** — the value Phase 1 recorded on the obligation — never the positional `HEAD~1` (which after any intervening/absent commit resolves to the previous, often unrelated, item's commit). Coupled-pair edit across shared `lazy_core` + both withhold branches.

**Deliverables:**
- [x] `build_input_audit_emit_command` (`user/scripts/lazy_core/ledgers.py`) accepts `cycle_commit_sha` (and `cycle_summary`) as keyword parameters and emits them into the `--context` args, replacing the hardcoded `_ctx("cycle_commit_sha", "HEAD~1")` and the `git log -1 --format=%s`-derived latest-commit `cycle_summary`. **Fail-safe fallback:** when the caller passes no sha (a legacy/partial obligation lacking the key), it retains the `HEAD~1` + latest-commit-subject proxy so the command stays ready-to-run — the fallback is now the exception, not the default.
- [x] The feature withhold branch (`lazy-state.py`) passes `cycle_commit_sha=_obligation.get("cycle_commit_sha")` and `cycle_summary=_obligation.get("cycle_summary")` (both read from the `pending_audit_obligation()` dict Phase 1 populated).
- [x] The coupled-pair mirror withhold branch (`bug-state.py`) passes the identical values from its obligation dict.
- [x] The `build_input_audit_emit_command` docstring is updated: `cycle_commit_sha` is now the bracket's recorded end commit; the `HEAD~1` default is documented as the legacy/absent-sha fallback only.
- [x] Tests: `test_ledgers.py` cases assert the emitted command carries the passed sha (not `HEAD~1`) when a sha is supplied, and falls back to `HEAD~1` + the latest-commit subject when absent. The existing `test_probe_withholds_forward_route_on_audit_obligation` (real `lazy-state.py` subprocess) is extended to assert the withheld probe's `input_audit_emit_command` binds the recorded end sha, not `HEAD~1` — the arm→probe→withhold e2e path. `lazy_parity_audit.py --repo-root .` stays exit 0. (⚖ scope-class: in-file `--test` fixtures substituted by the real-subprocess pytest e2e above.)

**Minimum Verifiable Behavior:** `python3 -m pytest user/scripts/tests/test_lazy_core/test_ledgers.py -q && python3 user/scripts/lazy-state.py --test && python3 user/scripts/bug-state.py --test && python3 user/scripts/lazy_parity_audit.py --repo-root .` all pass, with the new fixture proving the emitted `input_audit_emit_command` binds the recorded end sha (it fails RED before this phase: current code always emits `cycle_commit_sha=HEAD~1`).

**Prerequisites:**
- Phase 1: the obligation dict must carry `cycle_commit_sha` + `cycle_summary` for the withhold branches to forward. (Phase 2's helper still works standalone via the fail-safe fallback, but the end-to-end "correct sha" assertion depends on Phase 1's recorded value.)

**Files likely modified:**
- `user/scripts/lazy_core/ledgers.py` — parameterize `build_input_audit_emit_command`; update its docstring.
- `user/scripts/lazy-state.py` — feature withhold branch forwards the recorded sha/summary (line ~14148).
- `user/scripts/bug-state.py` — coupled-pair mirror withhold branch (line ~9767).
- `user/scripts/tests/test_lazy_core/test_ledgers.py` — direct helper coverage (passed-sha vs. fallback).
- In-file `--test` fixtures (arm→withhold end-to-end) registered in each state script's test-list block.

**Testing Strategy:**
Direct pytest on the pure `build_input_audit_emit_command` (string composition — assert the `--context cycle_commit_sha=<sha>` token and the fallback), plus a hermetic in-file state-script fixture exercising the arm→probe→withhold sequence end-to-end against temp markers at a controlled HEAD. Regenerate the byte-pinned smoke baseline via `_normalize_smoke_output` if a `--test` fixture is added.

**Integration Notes for Next Phase:**
- None (final phase). After both phases land, set the top-level `PHASES.md` `**Status:**` to `In-progress` (implementation done, validation pending); the state machine routes to the completion gate.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed`, writes the `FIXED.md` receipt, trims the queue, and archives the bug dir once both phases' tests pass — this is NOT a checkbox deliverable.

---

## Implementation Notes

### Landed 2026-07-18 (P1 + P2)

- **Files modified:** `user/scripts/lazy_core/markers.py` (`record_audit_obligation` commit-delta gate + new `head_commit_subject` helper), `user/scripts/lazy_core/ledgers.py` (`build_input_audit_emit_command` sha/summary params + docstring), `user/scripts/lazy_core/__init__.py` (facade name map: `head_commit_subject` → `markers`), `user/scripts/lazy-state.py` + `user/scripts/bug-state.py` (coupled-pair `--cycle-end` arming call sites + withhold-branch forwarding), `user/scripts/tests/test_lazy_core/test_markers.py` (+3 P1 gate cases) and `test_ledgers.py` (+2 P2 emit cases; updated existing audit-obligation coverage for the new signature; extended the subprocess withhold e2e).
- **New public API:** `lazy_core.head_commit_subject(repo_root=None)` — best-effort `git log -1 --format=%s`, mirrors `head_sha_snapshot`'s fail-open shape; registered in the PEP-562 facade map.
- **Delta oracle reuse:** the P1 arming gate uses the same `not end_sha or end_sha == begin_head_sha` zero-commit test as `record_cycle_commit_bracket`, so the arming gate and the bracket recorder agree on "did this cycle commit anything." The summary git call is skipped on the zero-commit path (the hot failed-cycle path this bug targets).
- **Testing note (⚖ scope-class):** in-file `--test` fixtures on the state scripts were substituted by `pytest tests/test_lazy_core/` coverage — direct `lazy_core` helper tests plus the existing real-`lazy-state.py`-subprocess arm→withhold e2e (extended to assert the bound end sha). This avoids regenerating the two byte-pinned smoke baselines; the `bug-state.py` coupled-pair mirror is guaranteed exit-0 by `lazy_parity_audit.py`.
- **Spin-offs:** none. All work is in-scope for this bug.
- **Origin decision record:** the audit-obligation mechanism this fix corrects belongs to `docs/features/mechanize-prose-only-orchestrator-contracts/` (D2-A) — see SPEC `**Related:**`.
- **Coupled-pair discipline (HARD):** every edit to `record_audit_obligation` and `build_input_audit_emit_command` is shared `lazy_core`; both state-script call sites are updated in the SAME phase that changes the helper, and `lazy_parity_audit.py --repo-root .` must be exit 0 before either phase is considered done. Run the full gate set after each phase: `lazy-state.py --test`, `bug-state.py --test`, `pytest tests/test_lazy_core/`, `lazy_parity_audit.py --repo-root .`.
