# Implementation Phases — Non-canonical blocker filenames invisible to the state machine

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness state-machine + hook change with no AlgoBooth app surface; validated entirely by the in-file `--test` smoke harnesses and `test_lazy_core.py`, which are the canonical gate for this layer (per `user/scripts/CLAUDE.md` → Testing). No Tauri/MCP-reachable behavior is introduced.

## Cross-feature Integration Notes

No hard deps on Complete upstreams — this is a self-contained harness defect fix in `user/scripts/`. (Omit upstream reality-check.)

## Validated Assumptions

All load-bearing assumptions for this plan are **code-provable** (verified inline at planning time via Read/Grep — there is no running system to observe; the harness scripts ARE the system and their `--test` harnesses are the ground truth):

- `lazy-state.py:1504-1505` Step 3 keys halt detection on the literal `spec_path / "BLOCKED.md"` (`.exists()`). Confirmed by Read.
- `bug-state.py:835-836` is an exact mirror using `spec_dir / "BLOCKED.md"`. Confirmed by Read.
- `lazy_core.neutralize_sentinel` (line 3312) renames resolved sentinels to `<stem>_RESOLVED_<date><ext>` and uses the literal substring `_RESOLVED_` (line 3357) as its idempotency guard. The new detector MUST exclude any name containing `_RESOLVED_` so a neutralized blocker never re-halts — reuse the same literal-substring convention. Confirmed by Read.
- Park-mode parks a feature-local `BLOCKED.md` via `lazy_core.build_parked_entry(feature_id, spec_path / "BLOCKED.md")` under `park_blocked` (`lazy-state.py:1384-1390`). A detected stray must park the same way. Confirmed by Read.
- Both `--test` baselines are byte-pinned and compared through `_normalize_smoke_output` (`test_lazy_core.py:38`); regenerate ONLY by piping live `--test` output through that helper. Confirmed by Read + dir listing (`tests/baselines/lazy-state-test-baseline.txt`, `bug-state-test-baseline.txt`).

**SPEC-example capability audit:** the SPEC contains no consuming code examples against an external API — the only constructs are Python stdlib (`pathlib`, glob) and the existing `lazy_core` helpers, all confirmed present. No rejected-capability risk. Gate satisfied.

⚖ policy: add write-time PreToolUse hook too → included in-cycle (Phase 4)

> **Completeness note (D7 — SPEC Open Question 1, line 74/88).** The SPEC defers a sizing/completeness call: read-time detector ALONE (Phases 1–3) closes the loop risk, OR ALSO add a write-time PreToolUse hook (defense-in-depth, prevents the stray ever landing). The SPEC itself states "Both converge on the same end-state ... so this is a sizing/completeness call for the planning cycle, not a product-behavior fork." Per the completeness-first standing policy this is scope-class (same product end-state, differs only in completeness), so the MOST COMPLETE path is taken in-cycle: the write-time hook is authored as **Phase 4**. SPEC Open Question 2 (extend the detector to mis-named `NEEDS_INPUT*` strays) is a genuine SCOPE boundary the SPEC author already decided AGAINST here ("scope to `BLOCKED`; file a follow-up") — it is left out of scope and not expanded.

### Phase 1: Shared `detect_noncanonical_blocker` helper in `lazy_core.py`

**Scope:** Add a single-writer read-time detector to the shared layer so both state machines inherit it from one place. The helper scans an item directory for a blocker-shaped stray — a filename matching `BLOCKED*` with a `.md` extension (case-insensitive) that is NEITHER the canonical `BLOCKED.md` NOR an already-neutralized `*_RESOLVED_*.md`. Returns the first offending `Path`, or `None`.

**Deliverables:**
- [x] `detect_noncanonical_blocker(spec_dir: Path) -> Optional[Path]` in `user/scripts/lazy_core.py`, placed near `neutralize_sentinel` (the other sentinel-name helper).
- [x] Match rule: case-insensitive `name.upper().startswith("BLOCKED")` AND `name.lower().endswith(".md")`; EXCLUDE the canonical `BLOCKED.md` (exact, case-sensitive — canonical is precise) and EXCLUDE any name containing the literal substring `_RESOLVED_` (reuse the `neutralize_sentinel` convention so a neutralized `BLOCKED_RESOLVED_<date>.md` never re-halts).
- [x] Deterministic ordering: iterate `sorted(spec_dir.iterdir())` so the "first offending path" is stable across platforms (the byte-pinned baselines depend on determinism).
- [x] Returns `None` when `spec_dir` does not exist or contains no stray (never raises on a missing dir).
- [x] Tests: `test_lazy_core.py` unit cases — (a) a stray `BLOCKED_2026-06-09-foo.md` alone → returns that path; (b) `BLOCKED_RESOLVED_2026-06-09.md` alone → returns `None` (excluded); (c) canonical `BLOCKED.md` alone → returns `None` (canonical is not a stray); (d) both canonical + stray present → returns `None` (canonical present means the canonical Step-3 check owns it — see Phase 2 precedence); (e) `blocked.md` lowercase variant → returns that path (case-insensitive match); (f) empty/missing dir → `None`.

#### Implementation Notes (Phase 1 — In-progress)

- Added `detect_noncanonical_blocker(spec_dir: Path) -> Path | None` to `lazy_core.py` (immediately before `neutralize_sentinel`). Uses `Path | None` to match the local annotation convention (`neutralize_sentinel(path, date: str | None)`), not `Optional[Path]` — equivalent under `from __future__ import annotations`.
- **Canonical precedence is case-SENSITIVE.** Implemented via `"BLOCKED.md" in [e.name for e in entries]` over the sorted dir listing, NOT `(spec_dir / "BLOCKED.md").exists()`. On Windows/macOS `.exists()` is case-INSENSITIVE, so a lowercase `blocked.md` stray would have falsely matched the canonical guard and returned `None` (test (e) caught this — RED→GREEN). The listing-membership check is genuinely case-sensitive on every platform.
- 6 unit tests added to `test_lazy_core.py` (`test_detect_noncanonical_blocker_*`), registered in `_TESTS`. Gate `python test_lazy_core.py` → 574/574 pass.
- **Review verdict:** PASS (inline review — single helper + tests, ≤2 files; test (d)/(e) precedence corrections applied during the cycle).

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` (or the targeted `TestDetectNoncanonicalBlocker` class) runs and the new unit cases pass — the helper returns the offending path for a stray and `None` for canonical / resolved / empty inputs.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `detect_noncanonical_blocker`.
- `user/scripts/test_lazy_core.py` — add the unit test cases above.

**Testing Strategy:** Pure-function unit tests over temp dirs (the helper has no I/O beyond `iterdir`). No state-machine wiring yet — fully isolated.

**Integration Notes for Next Phase:**
- Decision (d) above establishes **canonical precedence**: when both `BLOCKED.md` and a stray exist, the detector returns `None` so the existing literal `BLOCKED.md` check (which runs first in Step 3) owns the halt and no spurious `blocked-misnamed` terminal fires. Phases 2/3 rely on this — wire the detector AFTER the canonical check and only when canonical is absent.
- The helper is the SINGLE writer of the detection logic; Phases 2 and 3 only CALL it. Do not duplicate the match rule into the state machines.

---

### Phase 2: Wire the detector into `lazy-state.py` Step 3 (feature pipeline)

**Scope:** In `lazy-state.py` Step 3, immediately AFTER the canonical `BLOCKED.md` check returns (the `if blocked_file.exists(): ... return state` block ending ~line 1529) and BEFORE the `NEEDS_INPUT.md` check, call `lazy_core.detect_noncanonical_blocker(spec_path)`. When it returns a path, return a distinct terminal (`current_step="Step 3: mis-named blocker"`, `terminal_reason="blocked-misnamed"`) whose `notify_message` names the offending filename and instructs the human to rename it to `BLOCKED.md` or neutralize it. Also add park-mode parity: under `--park-blocked`, a detected stray parks the same way a canonical `BLOCKED.md` does.

**Deliverables:**
- [ ] After the canonical Step-3 BLOCKED return block, add: `stray = lazy_core.detect_noncanonical_blocker(spec_path)` and, when non-None, return a `_state(..., current_step="Step 3: mis-named blocker", terminal_reason="blocked-misnamed", notify_message=...)` naming the offending file (basename) and the corrective action.
- [ ] Park-mode parity: in the park loop near line 1384 (the `park_blocked` BLOCKED park branch), add a sibling branch that, when `park_blocked` is active and `detect_noncanonical_blocker(spec_path)` returns a stray (canonical `BLOCKED.md` absent), appends `lazy_core.build_parked_entry(feature_id, <stray-path>)` and `continue`s — keeping `--park-blocked` semantics aligned with the canonical blocker. Emit a `_diag` line mirroring the canonical park diag.
- [ ] Define the new terminal-reason string as a module constant if neighboring terminals use constants (match the existing `TR_*` / `STEP_*` style in the file); otherwise inline-literal to match the canonical-BLOCKED block's style. Keep it consistent with the local convention.
- [ ] Tests: in `lazy-state.py`'s in-file `--test` harness, add fixtures — (a) a feature dir with a stray `BLOCKED_<date>-foo.md` and no canonical file → `blocked-misnamed` terminal; (b) a `BLOCKED_RESOLVED_<date>.md` present alone → does NOT halt (falls through to normal routing); (c) canonical `BLOCKED.md` AND a stray both present → canonical `blocked` terminal precedence (no `blocked-misnamed`).

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` passes including the three new fixtures; a temp feature dir containing only `BLOCKED_2026-06-09-foo.md` yields `terminal_reason: "blocked-misnamed"` naming the file.

**Prerequisites:**
- Phase 1: `lazy_core.detect_noncanonical_blocker` must exist and honor canonical/resolved precedence.

**Files likely modified:**
- `user/scripts/lazy-state.py` — Step 3 wiring (~after line 1529) + park-mode branch (~line 1384).

**Testing Strategy:** In-file `--test` fixtures assert the computed state JSON for each of the three blocker arrangements. Re-baseline `tests/baselines/lazy-state-test-baseline.txt` in Phase 5 (deferred so the bug-state mirror lands first and both baselines regenerate together).

**Integration Notes for Next Phase:**
- The terminal-reason literal/constant chosen here (`blocked-misnamed`) MUST be reused VERBATIM in `bug-state.py` (Phase 3) so the two pipelines emit an identical contract — `lazy_parity_audit.py` and downstream readers expect parity.
- The new fixtures change `--test` output → the byte-pinned baseline WILL drift. Do NOT hand-edit the baseline; Phase 5 regenerates it through `_normalize_smoke_output`.

---

### Phase 3: Mirror the wiring into `bug-state.py` Step 3 (bug pipeline)

**Scope:** Exact mirror of Phase 2 in `bug-state.py` Step 3 (after the canonical `BLOCKED.md` return block ending ~line 859), using the bug pipeline's `STEP_*`/`TR_*` constant style. Add the same park-mode parity branch. The `blocked-misnamed` terminal-reason string MUST be identical to the feature pipeline's.

**Deliverables:**
- [ ] After `bug-state.py`'s canonical Step-3 BLOCKED return (~line 859), call `lazy_core.detect_noncanonical_blocker(spec_dir)` and, when non-None, return a `_bug_state(..., current_step="Step 3: mis-named blocker", terminal_reason="blocked-misnamed", notify_message=...)` naming the offending file — using the same string the feature pipeline emits.
- [ ] Park-mode parity branch mirroring Phase 2's, using `spec_dir` and the bug pipeline's park loop / `build_parked_entry` call.
- [ ] If `bug-state.py` defines `STEP_BLOCKED`/`TR_BLOCKED` constants, define `STEP_BLOCKED_MISNAMED`/`TR_BLOCKED_MISNAMED` (or equivalent) alongside them; the `TR_*` VALUE must equal the feature pipeline's `blocked-misnamed` literal.
- [ ] Tests: mirror the three Phase-2 fixtures in `bug-state.py`'s in-file `--test` harness — stray-only → `blocked-misnamed`; `BLOCKED_RESOLVED_*` only → no halt; canonical + stray → canonical precedence.

**Minimum Verifiable Behavior:** `python user/scripts/bug-state.py --test` passes including the three mirrored fixtures; a temp bug dir with only a stray blocker yields `terminal_reason: "blocked-misnamed"`.

**Prerequisites:**
- Phase 2: the feature-pipeline wiring + the canonical `blocked-misnamed` terminal-reason string to mirror.
- Phase 1: the shared helper.

**Files likely modified:**
- `user/scripts/bug-state.py` — Step 3 wiring (~after line 859) + park-mode branch.

**Testing Strategy:** In-file `--test` fixtures, mirror of Phase 2. Re-baseline `tests/baselines/bug-state-test-baseline.txt` in Phase 5.

**Integration Notes for Next Phase:**
- After Phases 2+3, run `python user/scripts/lazy_parity_audit.py` (if it covers Step-3 terminals) to confirm the two pipelines stayed in lockstep — the SPEC's whole point is that the mirror does not drift.
- Both `--test` baselines are now stale; Phase 5 regenerates BOTH through `_normalize_smoke_output` in one pass.

---

### Phase 4: Write-time PreToolUse hook — reject a mis-named blocker before it lands (defense-in-depth)

**Scope:** (D7 completeness layer — see the Completeness note above.) Add a PreToolUse(Write/Edit) hook that DENIES a write whose target filename is blocker-shaped but non-canonical (matches `BLOCKED*.md` case-insensitively, is not exactly `BLOCKED.md`, and does not contain `_RESOLVED_`), instructing the agent to use the canonical `BLOCKED.md` name. This prevents the stray from ever reaching disk, complementing the read-time detector (which is the load-bearing backstop). Hook is fail-OPEN: any parse/match error allows the write (never blocks legitimate work).

**Deliverables:**
- [ ] New hook script `user/hooks/block-noncanonical-blocker-write.sh` (follow the existing PreToolUse hook conventions in `user/hooks/` — read tool input from stdin, emit the deny JSON/exit convention the other `block-*.sh` hooks use; match against the resolved target path's BASENAME).
- [ ] Match rule identical in spirit to the Phase-1 helper: basename matches `BLOCKED*` + `.md` (case-insensitive), is NOT exactly `BLOCKED.md`, and does NOT contain `_RESOLVED_`. On match → DENY with a message telling the agent to write `BLOCKED.md` (canonical) instead. Fail-OPEN on any error.
- [ ] Register the hook in `user/settings.json` under the PreToolUse hooks for `Write` (and `Edit` if the existing block-* hooks register both), matching the existing registration shape.
- [ ] Update `claude-config/CLAUDE.md`'s Hooks table with a one-row entry for the new hook (the table documents every hook).
- [ ] Tests: a hook smoke check — feed the hook a synthetic tool-input for a write to `docs/.../BLOCKED_2026-06-09-foo.md` → hook denies; a write to `docs/.../BLOCKED.md` → hook allows; a write to an unrelated `notes.md` → allows; a write to `BLOCKED_RESOLVED_2026-06-09.md` → allows. (Mirror the test style used for sibling `block-*.sh` hooks; if those have no automated test, document a manual stdin-fixture check in the plan and run it.)

**Minimum Verifiable Behavior:** running the hook script with a stdin fixture targeting `BLOCKED_<date>-foo.md` emits a deny; targeting canonical `BLOCKED.md` emits an allow (exit 0 / no deny). Demonstrated from the shell.

**Prerequisites:**
- Independent of Phases 1–3 in code, but authored AFTER them so the canonical match rule (Phase 1) is settled and reused verbatim. The read-time detector remains the primary fix; this hook is the second layer.

**Files likely modified:**
- `user/hooks/block-noncanonical-blocker-write.sh` — net-new hook.
- `user/settings.json` — register the PreToolUse hook.
- `CLAUDE.md` (repo root) — Hooks table row.

**Testing Strategy:** stdin-fixture smoke test of the hook (deny on stray, allow on canonical / resolved / unrelated). No state-machine baseline impact — hooks are independent of `--test`.

**Integration Notes for Next Phase:**
- This hook is a PREVENTION layer; it does NOT replace the read-time detector. If the hook is ever bypassed (a non-Write path drops a file, a future agent disables hooks), the Phase 1–3 detector still catches the stray at read time. Keep both.
- The deny message must name the canonical `BLOCKED.md` so the agent's retry writes the correct file — a deny without the corrective name just loops the agent.

---

### Phase 5: Re-baseline both `--test` suites + doc note

**Scope:** Regenerate both byte-pinned `--test` baselines through `_normalize_smoke_output` (NEVER by hand) so they absorb the new fixtures from Phases 2–3, confirm both suites + `test_lazy_core.py` green, and add the schema-doc note.

**Deliverables:**
- [ ] Regenerate `user/scripts/tests/baselines/lazy-state-test-baseline.txt` by piping live `python lazy-state.py --test` output through `_normalize_smoke_output` (use the same procedure `test_lazy_core.py` documents — never hand-edit).
- [ ] Regenerate `user/scripts/tests/baselines/bug-state-test-baseline.txt` the same way.
- [ ] Confirm green: `python lazy-state.py --test`, `python bug-state.py --test`, `python test_lazy_core.py`, and (if it covers this) `python lazy_coord.py --test` — the full set named in `user/scripts/CLAUDE.md` → Concurrency plane gate, since the shared `lazy_core` import surface changed.
- [ ] Add a note to `user/skills/_components/sentinel-frontmatter.md` documenting the read-time stray-blocker detector and the `BLOCKED_RESOLVED_` exclusion (so the canonical-name contract prose points at the mechanical backstop that now enforces it).
- [ ] Run `python ~/.claude/scripts/lint-skills.py` if the component edit could affect projection (the component is injected into skills); confirm no broken injections.

**Minimum Verifiable Behavior:** `python lazy-state.py --test`, `python bug-state.py --test`, and `python test_lazy_core.py` all exit 0 with the regenerated baselines committed; `git diff` shows the baseline drift is exactly the new fixtures' rows.

**Prerequisites:**
- Phases 2 and 3: both sets of new fixtures must exist before regenerating (otherwise the baseline regenerates without them and a later phase re-drifts it).

**Files likely modified:**
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated.
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerated.
- `user/skills/_components/sentinel-frontmatter.md` — detector + exclusion note.

**Testing Strategy:** The regenerated baselines ARE the regression net; the three (four) `--test` suites green is the acceptance gate. Doc note is prose-only.

**Integration Notes for Next Phase:**
- Terminal phase. Once green with regenerated baselines, implementation is done and the bug is ready for the validation tail (the state machine routes to `/mcp-test`; this fix is `MCP runtime: not-required`, so the mcp-test cycle owns the skip decision per `user/scripts/CLAUDE.md`).
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed`, writes the `FIXED.md` receipt, strikes the ROADMAP row, and archives — only after the validation tail. Do NOT flip status or write `FIXED.md` in any phase here.
