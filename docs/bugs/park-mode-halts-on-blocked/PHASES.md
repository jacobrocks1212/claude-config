# Implementation Phases — Park mode halts on BLOCKED instead of parking it

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness-internal Python state machines + skill prose; no AlgoBooth app surface, no Tauri/MCP HTTP server. Verification is the in-file `--test` smoke harnesses (`lazy-state.py --test`, `bug-state.py --test`) + `test_lazy_core.py`, which are the canonical regression net per `user/scripts/CLAUDE.md`.

## Validated Assumptions

All load-bearing assumptions here are **code-provable** — they were verified by reading the cited source during planning (the Touchpoint Audit below), not inferred. No runtime spike is required:

- The Step-2 selection loop and the Step-3 BLOCKED gate are structurally identical in shape between `lazy-state.py` (`:1248–1271` / `:1345–1370`) and `bug-state.py` (`:678–701` / `:794–813`). Mirroring is mechanical.
- `lazy_core.build_parked_entry(item_id, sentinel_path)` (`lazy_core.py:463`) already accepts ANY sentinel path and parses its frontmatter via `parse_sentinel`; a `BLOCKED.md` path is already a valid input. It currently records `id` / `sentinel` / `decision_count` / `parked_since` but **no sentinel-kind field** — the flush cannot today tell a blocked-parked entry from a needs-input one.
- `_PARK_MODE` / `_PARKED` and the `_state()`/`_bug_state()` "parked key only when park mode" invariant (`lazy-state.py:142–147`, `bug-state.py:239–244`) are identical between the two scripts.
- Both scripts pin `--test` output to a committed baseline (`tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt`) normalized by `test_lazy_core.py::_normalize_smoke_output`. Adding fixtures changes these baselines; regenerate ONLY by piping live `--test` through that helper.

## Completeness-policy resolutions applied at planning time (D7)

These were the SPEC's open/recommended-flag decisions. None diverge in user-visible product behavior (D1–D5 already lock the behavior), so per the standing completeness-first policy each took the most-complete in-cycle path rather than a NEEDS_INPUT halt:

- ⚖ policy: park-blocked flag shape → companion flag `--park-blocked` (SPEC D4 recommendation; keeps `--park-needs-input` byte-identical for existing callers).
- ⚖ policy: mirror park-blocked to bug pipeline → yes (SPEC Open-Q1; `/lazy-bug-batch` parity is completeness, same behavior).
- ⚖ policy: blocked-parked flush UX → reuse existing flush, tag sentinel-kind (SPEC Open-Q2; add a `sentinel_kind` field to `build_parked_entry` so the flush can surface a blocked item distinctly without a new prompt shape).
- ⚖ policy: park all blocker kinds in park mode → yes (SPEC D5; park mode defers everything parkable — escalation/mcp-validation blocks included — surfaced at flush, not resolved inline).

## Touchpoint Audit (verified during planning — read-only)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy-state.py` | yes | `compute_state(..., park_needs_input=False)` `:1063`; `global _PARK_MODE, _PARKED` `:1085`; Step-2 park skip `:1253–1263` (`:1256` BLOCKED exclusion); `current is None` terminals `:1273–1323`; Step-3 blocked `:1345–1370`; arg parser `:4994`; main wiring `:5692` | refactor | Add `park_blocked` param symmetric with `park_needs_input`; add BLOCKED park branch in Step-2 loop; add honest all-parked terminal in the `current is None` block; add `--park-blocked` CLI flag + wire to `compute_state` |
| `user/scripts/bug-state.py` | yes | `compute_state(..., park_needs_input=False)` `:507`; `global _PARK_MODE, _PARKED` `:539`; Step-2 park skip `:683–693`; `current is None` terminals `:706+`; Step-3 blocked `:794–813`; arg parser `:3516`; main wiring `:4090` | refactor | Mirror lazy-state.py changes (D7 parity) |
| `user/scripts/lazy_core.py` | yes | `build_parked_entry(item_id, sentinel_path)` `:463–502` (returns `id`/`sentinel`/`decision_count`/`parked_since`) | refactor | Add a `sentinel_kind` field (`"needs-input"` \| `"blocked"`) derived from the sentinel filename; default keeps existing four keys so NEEDS_INPUT parked entries stay shape-compatible |
| `user/scripts/test_lazy_core.py` | yes | `build_parked_entry` characterization tests; `_normalize_smoke_output` | refactor | Add a test asserting `sentinel_kind` is set for a BLOCKED.md path and for a NEEDS_INPUT.md path |
| `user/skills/lazy-batch/SKILL.md` | yes | Step-1a park-mode probe flag `:360`; Step-1b `blocked` terminal `:370`; terminals `:380–382`; §1c.6 park notification `:402` | refactor | In `--park`, append `--park-blocked` alongside `--park-needs-input`; ensure Step-1h does NOT fire for a park-mode blocked feature (it is parked at the script, never returns `blocked`); add the all-parked terminal to Step-1b; route blocked-parked items into the flush + §1c.6 notification |
| `user/skills/lazy-bug-batch/SKILL.md` | yes | park-mode probe flag `:248`; flush `:695` | refactor | Mirror lazy-batch changes |
| `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | yes | park-mode probe flag; `1g-flush` `:567`; terminals | refactor | Mirror per coupled-pair rule; record divergence (if any) in its "Differences from /lazy-batch" block |
| `user/skills/_components/parked-flush.md` | yes | flush triggers `(a)/(b)/(c)`; Step-1 collect; Step-2 schema check | refactor | Teach the flush to recognize a blocked-parked entry (`sentinel_kind: blocked` / sentinel file named `BLOCKED.md`): a BLOCKED.md body is NOT the `## Decision Context` rich body, so it must be surfaced via a blocked-specific affordance (re-print BLOCKED.md body + offer add-phase/defer/spin-off/halt), NOT silently dropped by the Step-2 `## Decision Context` schema check |
| `user/scripts/CLAUDE.md` | yes | `--park-needs-input` CLI-surface doc line | refactor | Document `--park-blocked` next to `--park-needs-input`; update the park-mode prose |

No path is net-new — every change extends an existing, symmetric structure. No genuine design fork surfaced (all forks were scope/mechanical, resolved by D7 above).

## Cross-feature Integration Notes

No hard upstream deps (`**Depends on:**` is effectively none — this is a self-contained harness bug). The only cross-artifact coupling is the **coupled-pair rule** from the repo `CLAUDE.md`: `/lazy-batch` ↔ `/lazy-batch-cloud` and the bug-pipeline analog must stay in lockstep, and `lazy-state.py` ↔ `bug-state.py` share `lazy_core.py`. These are addressed by Phases 1–4 keeping the two scripts and the three orchestrators symmetric.

---

### Phase 1: Core script park-blocked support (lazy-state.py) — TDD

**Scope:** Teach `lazy-state.py` to park a feature-local `BLOCKED.md` under a new `--park-blocked` flag, symmetric with the existing `--park-needs-input` branch, and emit an honest all-parked terminal. This is the root-cause fix (SPEC Theory 1 / D1 / D3).

**Deliverables:**
- [x] `compute_state(...)` gains a `park_blocked: bool = False` parameter, appended after `park_needs_input` (positional callers unbroken — same pattern as the WU-1 Phase-4 `park_needs_input` add).
- [x] In the Step-2 selection loop, a new park branch parks a feature carrying `BLOCKED.md` when `park_blocked` is active: `_PARKED.append(lazy_core.build_parked_entry(feature_id, spec_path / "BLOCKED.md"))` + `_diag(...)` + `continue`. Symmetric with the NEEDS_INPUT branch at `:1253–1263`. Ordering: a feature carrying BOTH BLOCKED.md and NEEDS_INPUT.md parks once (no double-append) — the BLOCKED park branch is evaluated and `continue`s, so the NEEDS_INPUT branch is not reached for the same feature.
- [x] `_PARK_MODE` is set true when EITHER `park_needs_input` OR `park_blocked` is active (so the `parked[]` key is emitted), preserving the "parked key absent unless park mode" invariant when both are false.
- [x] New honest all-parked terminal: when `current is None` AND `_PARKED` is non-empty (and no more-specific terminal — cloud/device/research/scoped-id — fired), return `terminal_reason="queue-exhausted-all-parked"` instead of `all-features-complete` (SPEC D3 — this also fixes the latent NEEDS_INPUT-only all-parked false-completion). D2: the global terminals computed when `current is None` (`cloud-queue-exhausted`, `device-queue-exhausted`, `queue-blocked-on-research`, `scoped-id-not-found`) keep their existing precedence — the all-parked terminal is the new fallback BEFORE `all-features-complete`.
- [x] `--park-blocked` CLI arg added (`action="store_true"`) and wired into the `compute_state(...)` call in `main`.
- [x] Tests: new `--test` fixtures (see Testing Strategy) — BLOCKED feature under `--park-blocked` is parked + next feature dispatched; all-parked → `queue-exhausted-all-parked`; default (no flag) byte-identical; BLOCKED+NEEDS_INPUT under both flags parks once.

**Implementation Notes (2026-06-16):**
- Done. Actual final symbols (post-edit line numbers): `compute_state` signature `park_blocked` param at `:1064`; `_PARK_MODE = park_needs_input or park_blocked` at `:1087`; Step-2 BLOCKED park branch added ABOVE the NEEDS_INPUT branch (~`:1248–1262`); `queue-exhausted-all-parked` terminal inserted before `all-features-complete` (~`:1334`); `--park-blocked` CLI arg after `--park-needs-input` (~`:5015`); main wiring `park_blocked=args.park_blocked` (~`:5707`).
- Tests: four new sub-fixtures under a fresh `park-blocked` temp root (`park-blocked-mode-skip`, `park-blocked-default-halt`, `park-blocked-all-parked-terminal`, `park-blocked-and-needs-input-single-park`), modeled on the existing `WU-1-park` fixture. Written RED-first (confirmed `TypeError: unexpected keyword argument 'park_blocked'` before implementing), now all PASS.
- Baseline: `tests/baselines/lazy-state-test-baseline.txt` regenerated via `test_lazy_core._normalize_smoke_output` with an isolated `LAZY_STATE_DIR` (NOT hand-edited). The default no-flag path stays byte-identical; only the new fixtures add lines.
- **Test-harness gotcha (carry to Phase 2):** `lazy-state.py --test` shells out to `bug-state.py --enqueue-adhoc` in the `materialize-bug` fixture. Under a LIVE cycle marker (`~/.claude/state/lazy-cycle-active.json`) the C3 refusal (exit 3) crashes that fixture. Run the suite hermetically with `LAZY_STATE_DIR=<empty temp dir>` (what `test_lazy_core.py` does) — do NOT delete the orchestrator's live marker. `python user/scripts/test_lazy_core.py` (387/387) is the authoritative gate and is already hermetic.
- Gate: `python user/scripts/test_lazy_core.py` → 387/387 passed.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` passes, including the new fixtures, and the no-flag output is byte-identical to the regenerated baseline. Concretely: a temp-dir queue with `[blocked-feat, workable-feat]` under `park_blocked=True` returns `feature_id="workable-feat"` with `parked[]` containing `blocked-feat` (kind `blocked`); the same queue with no flag returns `terminal_reason="blocked"` and no `parked` key.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — `compute_state` signature + Step-2 BLOCKED park branch + `_PARK_MODE` gating + all-parked terminal + CLI flag + main wiring (verified symbols above).
- `user/scripts/lazy_core.py` — IF the `sentinel_kind` field (Phase 3) is needed by this phase's parked-entry assertions, this phase MAY consume it; otherwise the kind field lands in Phase 3 and Phase 1 asserts only id/sentinel. (Sequencing note: to keep Phase 1 self-contained, Phase 1 asserts the parked entry's `id` + `sentinel` path ends in `BLOCKED.md`; the `sentinel_kind` assertion is Phase 3's.)
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated via `_normalize_smoke_output`.

**Testing Strategy:**
TDD against the in-file `--test` harness — the canonical hermetic check per `user/scripts/CLAUDE.md`. Add fixtures modeled on the existing `WU-1-park` fixture (`lazy-state.py:~4718`):
1. **`park-blocked-mode-skip`** — queue `[blocked-feat (BLOCKED.md), workable-feat]`, `park_blocked=True` → dispatched `feature_id == workable-feat`, `parked[]` has one entry id `blocked-feat`.
2. **`park-blocked-default-halt`** — same queue, no flag → `terminal_reason == "blocked"`, no `parked` key (byte-identical to today).
3. **`park-blocked-all-parked-terminal`** — queue where every remaining feature is parked (blocked and/or needs-input) → `terminal_reason == "queue-exhausted-all-parked"`, NOT `all-features-complete`, `parked[]` non-empty.
4. **`park-blocked-and-needs-input-single-park`** — a feature carrying BOTH sentinels under `park_needs_input=True, park_blocked=True` → parked exactly once (one `parked[]` entry, not two).
Write each fixture's assertions FIRST (they must fail RED against the unmodified script for the right reason: the new param/flag/terminal does not yet exist), then implement.

**Integration Notes for Next Phase:**
- The Step-2 BLOCKED park branch MUST be ordered so a BLOCKED.md feature is parked before the existing NEEDS_INPUT branch and before `current` is assigned — symmetric placement to `:1253`.
- The all-parked terminal string `queue-exhausted-all-parked` is the contract the orchestrator (Phase 4) and bug pipeline (Phase 2) consume — keep it identical across both scripts.
- `_PARK_MODE` now reflects EITHER flag; Phase 2 mirrors this `OR` in bug-state.py.

---

### Phase 2: Mirror park-blocked into the bug pipeline (bug-state.py) — TDD

**Scope:** Apply the exact Phase-1 changes to `bug-state.py` so `/lazy-bug-batch --park` parks blocked bugs and advances (SPEC Open-Q1, resolved yes by D7). The two scripts share `lazy_core.py`; this keeps them symmetric per the Coupling Rule.

**Deliverables:**
- [x] `bug-state.py compute_state(...)` gains `park_blocked: bool = False` (appended after `park_needs_input` at `:507`).
- [x] Step-2 selection loop gains a BLOCKED park branch symmetric with the NEEDS_INPUT branch at `:683–693`: parks a bug carrying `BLOCKED.md` under `park_blocked`, using `build_parked_entry(bug_id, spec_dir / "BLOCKED.md")`. Same single-park ordering for a bug carrying both sentinels.
- [x] `_PARK_MODE` set true when EITHER flag active (`:539`–`:540`).
- [x] Honest all-parked terminal in the `current is None` block (`:706+`): `terminal_reason="queue-exhausted-all-parked"` when `_PARKED` is non-empty, placed AFTER the existing specific terminals (`cloud-queue-exhausted`, `device-queue-exhausted`, `all-deferred`) and BEFORE `all-bugs-fixed`. The existing `TR_ALL_DEFERRED` (DEFERRED.md operator-parked) stays distinct from the new park terminal.
- [x] `--park-blocked` CLI arg added (`:3516` neighborhood) and wired into the `compute_state(...)` call in main (`:4090`).
- [x] Tests: bug-side `--test` fixtures mirroring Phase 1 (modeled on `bug-state.py:~3219` `WU-1-park (bug)` fixture).

**Implementation Notes (2026-06-16):**
- Done — byte-for-byte symmetric mirror of Phase 1. Added `TR_QUEUE_EXHAUSTED_ALL_PARKED = "queue-exhausted-all-parked"` constant (`:119`, the bug pipeline uses TR_ constants where lazy-state uses literals — same string value). `park_blocked` param `:509`; `_PARK_MODE = park_needs_input or park_blocked` `:541`; Step-2 BLOCKED park branch added ABOVE the NEEDS_INPUT branch (~`:688`); all-parked terminal inserted before `all-bugs-fixed` and after the operator-DEFERRED terminal (~`:780`); `--park-blocked` CLI arg after `--park-needs-input` (~`:3805`); main wiring `park_blocked=args.park_blocked` (~`:4370`).
- Tests: five new sub-fixtures under a fresh `bug-park-blocked` temp root — the four Phase-1 shapes plus sub-fixture E (BLOCKED-only bug IS parked under `park_blocked=True`, the affirmative mirror of the existing sub-fixture D which proves NOT-parked WITHOUT the flag). RED-first confirmed (`TypeError` before impl), all PASS.
- Sub-fixture D (`bug-park-needs-input-blocked-precedence`) still passes unchanged — it now means "blocked NOT parked because `park_blocked` was NOT set," which is correct.
- Baseline `tests/baselines/bug-state-test-baseline.txt` regenerated via `_normalize_smoke_output` (isolated `LAZY_STATE_DIR`). Both suites + `test_lazy_core.py` green (387/387). Shared `lazy_core` import surface unchanged.

**Minimum Verifiable Behavior:** `python3 user/scripts/bug-state.py --test` passes including new fixtures; no-flag output byte-identical to the regenerated `bug-state-test-baseline.txt`. A temp queue `[blocked-bug, workable-bug]` under `park_blocked=True` dispatches `workable-bug` with `blocked-bug` in `parked[]`.

**Prerequisites:** Phase 1 (the contract strings `queue-exhausted-all-parked` and the `park_blocked` shape are defined there; Phase 2 reuses them verbatim).

**Files likely modified:**
- `user/scripts/bug-state.py` — mirror of Phase-1 changes (verified symbols above).
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerated via `_normalize_smoke_output`.

**Testing Strategy:**
Same four fixture shapes as Phase 1, bug-flavored (ids `blocked-bug`/`workable-bug`), modeled on the existing bug park fixture and its sub-fixtures A–D (default-halt, mode-skip, resolved-reenter, blocked-precedence). Sub-fixture D (BLOCKED precedence under `park_needs_input` only) MUST still pass unchanged — it now means "blocked NOT parked because `park_blocked` was NOT set", which is correct. Add a new sub-fixture E asserting that under `park_blocked=True` the same blocked bug IS parked. Write RED first.

**Integration Notes for Next Phase:**
- Both state scripts now expose identical `park_blocked` semantics and the same all-parked terminal string. Phase 3's `lazy_core` change (sentinel_kind) is consumed by BOTH scripts' parked entries automatically (shared helper).
- Run BOTH `--test` suites + `test_lazy_core.py` after this phase (the shared-import gate from `user/scripts/CLAUDE.md`).

---

### Phase 3: Sentinel-kind on parked entries (lazy_core.build_parked_entry) — TDD

**Scope:** Add a `sentinel_kind` field to the parked-entry record so the flush (Phase 5) can distinguish a blocked-parked item from a needs-input one without inspecting the filesystem (SPEC Open-Q2 / D4 sentinel-kind field). Shared helper → benefits both pipelines at once.

**Deliverables:**
- [x] `build_parked_entry(item_id, sentinel_path)` returns an additional key `"sentinel_kind"`: `"blocked"` when `sentinel_path.name == "BLOCKED.md"`, `"needs-input"` when `sentinel_path.name == "NEEDS_INPUT.md"`, else `"unknown"` (defensive — never raises). The existing four keys (`id`, `sentinel`, `decision_count`, `parked_since`) are unchanged and keep their positions; this is purely additive.
- [x] `decision_count` semantics for a BLOCKED.md sentinel: a BLOCKED.md has no `decisions:` list, so `decision_count` is `0` (the existing "absent/empty/not-a-list → 0" path already handles this — verified, not special-cased).
- [x] Update the `build_parked_entry` docstring contract block (`:471–485`) to document `sentinel_kind`.
- [x] Tests: `test_lazy_core.py` characterization — `sentinel_kind == "blocked"` for a BLOCKED.md path, `"needs-input"` for a NEEDS_INPUT.md path, `"unknown"` for an unrecognized name; existing keys still present and correct.

**Implementation Notes (2026-06-16):**
- Done. `sentinel_kind` derived from `sentinel_path.name` immediately before the return dict in `build_parked_entry` (`lazy_core.py` ~`:495–510`); docstring contract block updated to document the new key + the BLOCKED.md→decision_count 0 path. Purely additive; the four existing keys are unchanged and keep their positions.
- Tests: three new RED-first characterization tests in `test_lazy_core.py` (`..._sentinel_kind_blocked`, `..._needs_input`, `..._unknown`), registered in the runner list. Confirmed RED (`KeyError: 'sentinel_kind'`) before impl; now PASS. Total `test_lazy_core.py` 387→390.
- **Baseline note (plan deviation, documented):** the plan expected both `--test` baselines to regenerate in P3. They did NOT change — `sentinel_kind` lands in the returned dict but the `--test` harness print lines only emit `id`/`decision_count`/dispatched-id, never the full parked record, so the byte-pinned baselines are unaffected. Confirmed by `git status` showing only `lazy_core.py` + `test_lazy_core.py` modified, and both smoke suites + the baseline-comparison tests green. No hand-edit needed.
- Gates: `test_lazy_core.py` 390/390; `lazy_coord.py --test` green; `lazy-state.py --test` + `bug-state.py --test` green (hermetic, isolated `LAZY_STATE_DIR`).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` (or the project's test runner for it) passes including the new `sentinel_kind` assertions. Re-running `lazy-state.py --test` and `bug-state.py --test` still passes — the additive field appears in their parked fixtures' output (baselines updated to include it).

**Prerequisites:** Phases 1–2 (the parked entries that carry `sentinel_kind` are produced by the BLOCKED park branches added there). Ordering rationale: keeping the kind field in its own phase isolates the shared-helper change and its baseline impact from the state-machine routing changes.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `build_parked_entry` field + docstring (verified `:463–502`).
- `user/scripts/test_lazy_core.py` — new characterization assertions.
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt`, `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerated (parked entries now carry `sentinel_kind`).

**Testing Strategy:**
Pure unit characterization in `test_lazy_core.py` (the helper is domain-agnostic and directly testable). Write the three RED assertions first; confirm they fail because the key is absent (KeyError / missing), not due to a typo. Then add the field. Re-baseline both smoke suites ONLY via `_normalize_smoke_output`.

**Integration Notes for Next Phase:**
- Phase 4/5 read `entry["sentinel_kind"]` to decide notification wording and flush affordance — this is the contract this phase locks.

---

### Phase 4: Orchestrator wiring — lazy-batch + lazy-bug-batch + lazy-batch-cloud (skill prose)

**Scope:** Make the three batch orchestrators pass `--park-blocked` in `--park` mode, stop firing Step-1h blocked-resolution for park-mode blocked features (they are parked at the script and never return `blocked`), handle the new `queue-exhausted-all-parked` terminal, and fire the §1c.6 park notification for blocked-parked items. Honors the coupled-pair rule (D7 mirror = yes).

**Deliverables:**
- [x] `lazy-batch/SKILL.md` Step-1a park-mode probe flag (`:360`): in `--park` mode, append BOTH `--park-needs-input` AND `--park-blocked` to every probe. When `park_mode == false`, neither flag is passed (byte-identical default).
- [x] `lazy-batch/SKILL.md` Step-1b: add a `queue-exhausted-all-parked` terminal entry — run `--run-end`, fire the parked-flush (trigger (b)/(c) per `parked-flush.md`), then PushNotification + final report + STOP. It is NOT `all-features-complete` (honest distinct terminal).
- [x] `lazy-batch/SKILL.md` Step-1b `blocked` entry + Step-1h: clarify that in `--park` mode a feature-local block is parked by the script and never surfaces as `terminal_reason: blocked`, so Step-1h does not fire for it; the block is deferred to the flush. (Global/escalation terminals are unaffected — D2/D5: even escalation/mcp-validation per-feature blocks are parked in park mode.)
- [x] `lazy-batch/SKILL.md` §1c.6: the park notification (point 1) already fires per non-empty `parked[]`; add wording so a blocked-parked entry (`sentinel_kind == "blocked"`) reads as a parked BLOCK, e.g. `⏸ parked {feature_name} — BLOCKED ({phase}) · notified`, distinct from the decision-count wording for needs-input.
- [x] `lazy-bug-batch/SKILL.md`: mirror all of the above (probe flag `:248`, terminal handling, §1c.6 wording, flush binding `:695`).
- [x] `lazy-batch-cloud/SKILL.md`: mirror; if any cloud-specific divergence exists (it should not — park is environment-agnostic), record it in the "Differences from /lazy-batch" block.
- [x] Update each skill's State Machine Summary / terminal table at the bottom to list `queue-exhausted-all-parked`.

**Implementation Notes (2026-06-16):**
- Done across all three orchestrators, kept mirrored per the coupled-pair rule. In each: (1) Step-1a park flag now appends BOTH `--park-needs-input` AND `--park-blocked`, documents the `sentinel_kind` tag + the new terminal; (2) Step-1b `blocked` entry gained a "Park-mode exception" clause (script parks it, Step-1h does not fire, deferred to flush, D5 escalation blocks included); (3) new `queue-exhausted-all-parked` terminal entry (flush-first → run-end → notify → STOP, NOT success); (4) §1c.6 point-1 park wording now branches on `sentinel_kind` (needs-input decision-count vs blocked-with-phase), point-2 halt enumeration adds the new terminal.
- **State Machine Summary / terminal table:** lazy-batch + lazy-bug-batch have NO compact terminal table (terminals are documented inline in §1b + the COUPLED-PAIR DIFF comments); the inline §1b additions ARE the summary update. lazy-batch-cloud's "Differences from /lazy-batch" table gained an explicit park-mode row recording NO cloud divergence (park is environment-agnostic) per the coupled-pair rule. lazy-bug-batch's intro terminal table at `:37` already lists `all-remaining-deferred` as "all parked"; the new park terminal is distinct (advance-and-park vs operator DEFERRED.md) and documented in §1b.
- Gates: `lint-skills.py` clean (no broken `!cat`); `project-skills.py` clean (79 skills / 90 components, zero errors). No runtime surface — the behavioral net is the P1–P3 fixtures.

**Minimum Verifiable Behavior:** This is documentation/prose work; there is no runtime surface. Verification is structural: `python3 ~/.claude/scripts/lint-skills.py` passes (no broken injections), and a grep confirms all three orchestrators (a) append `--park-blocked` in park mode and (b) handle `queue-exhausted-all-parked`. The behavioral proof lives in Phases 1–3's `--test` fixtures (the orchestrator is a thin wrapper around the script per `user/scripts/CLAUDE.md` — the script's fixtures ARE the behavior).

**Prerequisites:** Phases 1–3 (the `--park-blocked` flag, the `queue-exhausted-all-parked` terminal, and the `sentinel_kind` field must exist before the orchestrators reference them).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (verified line anchors above).

**Testing Strategy:**
No code execution. Cross-check: (1) `lint-skills.py` clean; (2) `project-skills.py` re-projects cleanly (no broken `!cat`); (3) diff the three orchestrators to confirm the park-flag append + terminal handling are mirrored (coupled-pair rule). The behavioral regression net is the Phase 1–3 fixtures.

**Integration Notes for Next Phase:**
- The flush component (Phase 5) is referenced by all three orchestrators; its blocked-parked affordance must be authored consistently with the §1c.6 wording added here.

---

### Phase 5: Flush handles blocked-parked items (parked-flush.md component) — skill prose

**Scope:** Teach the shared `parked-flush.md` component to surface a blocked-parked item (`sentinel_kind: blocked`) without dropping it. Today the flush's Step-2 schema check requires a `## Decision Context` rich body — a `BLOCKED.md` body has none and would be silently skipped as "malformed". The flush must route blocked-parked items to a blocked-specific resolution affordance (re-print the BLOCKED.md body + offer add-phase / defer / spin-off / halt), reusing the existing Step-1h blocked-resolution machinery rather than the decision `AskUserQuestion` flow.

**Deliverables:**
- [ ] `parked-flush.md` Step-1 (collect): the `pending_flush` set now includes items whose sentinel is `BLOCKED.md` (still named — not yet resolved), partitioned by `sentinel_kind` into needs-input vs blocked.
- [ ] `parked-flush.md` Step-2 (schema check): a blocked-parked item is NOT run through the `## Decision Context` rich-body schema check (that check is needs-input-only). A blocked item is validated against the BLOCKED.md frontmatter schema (`blocker_kind`, `phase`) instead, and never dropped as "malformed `## Decision Context`".
- [ ] New flush sub-step (or branch in Steps 3–4) for blocked-parked items: re-print the BLOCKED.md body verbatim, then run the SAME resolution affordance as `lazy-batch` Step-1h (auto-resolve sequencing-only per `completeness-policy.md` §3; product-fork → `AskUserQuestion` add-phase / defer-to-tail / spin-off / halt-for-manual). After resolution, neutralize the sentinel via `--neutralize-sentinel {spec_path}/BLOCKED.md` (canonical `BLOCKED_RESOLVED_<date>.md` rename) so the next probe re-enters the item. Reuse `decision-resume.md`/Step-1h machinery — do NOT invent a new resolution path.
- [ ] Update the component's pipeline-binding table / coupling note if a new token is needed; otherwise leave the existing `{SKILL}`/`{STATE_SCRIPT}` bindings.
- [ ] Run-end digest (Step 5/6 of the flush): blocked-parked resolutions are logged alongside decision flushes (one meta-cycle each), and the PushNotification wording covers blocked items.

**Minimum Verifiable Behavior:** Documentation/prose. Structural verification: `lint-skills.py` clean; `project-skills.py` re-projects the three flush consumers (`lazy-batch`, `lazy-bug-batch`, `lazy-batch-cloud`) without broken injections; `grep -rl "parked-flush.md" ~/.claude/skills/` confirms the consumer set is unchanged. A read-through confirms a blocked-parked item is no longer dropped by the Step-2 `## Decision Context` check.

**Prerequisites:** Phases 3 (sentinel_kind) and 4 (orchestrator §1c.6 wording + terminal handling).

**Files likely modified:**
- `user/skills/_components/parked-flush.md` (verified above — Steps 1, 2, 2.4/2.5, 3, 4, 5, 6).

**Testing Strategy:**
No code execution. Validate by: (1) `lint-skills.py` + `project-skills.py` clean; (2) trace each flush trigger (a)/(b)/(c) for a blocked-parked item by reading the revised component end-to-end and confirming it reaches a resolution affordance (never the "missing `## Decision Context`" skip path); (3) confirm the neutralize step targets `BLOCKED.md`, not `NEEDS_INPUT.md`.

**Integration Notes for Next Phase:**
- None — this is the terminal phase. After it, `--park` parks blocked features, advances the queue, and surfaces blocked-parked items honestly at the flush.

---

### Phase 6: Documentation — user/scripts/CLAUDE.md CLI surface

**Scope:** Document the new `--park-blocked` flag and the `queue-exhausted-all-parked` terminal so the source-of-truth doc for the lazy pipeline matches the code (SPEC Affected Area: `user/scripts/CLAUDE.md` documents the current intent verbatim and must be revised).

**Deliverables:**
- [ ] `user/scripts/CLAUDE.md` CLI-surface block: add a `--park-blocked` line next to `--park-needs-input`, describing it as the companion flag that parks feature/bug-local `BLOCKED.md` items (both scripts), output byte-identical without the flag.
- [ ] Revise the existing `--park-needs-input` line's parenthetical — it currently reads "(BLOCKED still halts; …)", which is no longer true when `--park-blocked` is also passed. Clarify: BLOCKED still halts UNLESS `--park-blocked` is also active.
- [ ] Note the new `queue-exhausted-all-parked` terminal in the lifecycle/terminal documentation.

**Minimum Verifiable Behavior:** Documentation. Verification: a grep of `user/scripts/CLAUDE.md` shows `--park-blocked` documented and the stale "BLOCKED still halts" claim corrected.

**Prerequisites:** Phases 1–2 (the flag and terminal must exist).

**Files likely modified:**
- `user/scripts/CLAUDE.md`.

**Testing Strategy:**
Read-through; confirm the doc matches the implemented flag/terminal names exactly (no drift between doc and code).

**Integration Notes for Next Phase:**
- None — terminal documentation phase.

---

## Notes

- **No MCP/runtime phase.** Per the `**MCP runtime:** not-required` header, all behavioral verification is the Python `--test` harnesses + `test_lazy_core.py`, distributed across Phases 1–3 (each carries its own RED-first fixtures). Phases 4–6 are prose with structural (lint/projection) verification — this is correct for harness-internal skill/doc changes, not a terminal-MCP-stacking anti-pattern (there is no app surface to MCP-test).
- **Coupled-pair discipline.** Phases 1↔2 (scripts) and Phase 4 (three orchestrators) must land their mirrored changes together; do not commit one side of a pair without the other. Run the full gate set after Phases 1–3: `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py` (and `lazy_coord.py --test` for completeness, though untouched here).
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes FIXED.md once the validation tail passes — this PHASES.md never flips the top-level status.
