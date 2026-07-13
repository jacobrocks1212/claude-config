# Implementation Phases — Checkpoint-resume false LOOP DETECTED + complex-part sonnet flip

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a pure-Python
state-machine defect verified via `test_lazy_core.py` (pytest) and the in-file `--test` smoke
harnesses of both state scripts.

**Close-out note (2026-07-12):** both Fix-Scope gaps were found ALREADY LANDED at HEAD, prior to
this close-out pass — batch state-hardening work (`719c98aa harden(script): fix checkpoint-resume
false-loop + complex-part sonnet flip`, plus continuity-restore follow-ups `9b60fb1f`/`821628e0`)
implemented both Gap 1 and Gap 2 exactly as this SPEC's Fix Scope specifies, including the two
test renames/additions the SPEC calls for. This PHASES.md documents the pre-landed state and
verifies it against the SPEC's own Fix Scope + Minimum Verifiable Behavior; no new code was written
in this pass.

---

### Phase 1: Gap 1 — `rebaseline_loop_signature_after_registry_reset` (stale registry-relative debounce baseline)

**Status:** Complete (pre-landed, `719c98aa`)

**Scope:** A new `lazy_core.rebaseline_loop_signature_after_registry_reset(repo_root, *, pipeline)`
helper rewrites ONLY the loop-debounce signature file's `consume_count` to the current
(freshly-cleared) `consumed_emission_count()`, preserving `signature`/`count`/`step_signature`/
`step_count` untouched — so a genuine pre-pause loop streak still survives while a never-re-attempted
route no longer inflates on the first post-resume probe. Called from the checkpoint-resume block of
BOTH state scripts' `--run-start` handlers.

**Deliverables:**
- [x] `lazy_core.rebaseline_loop_signature_after_registry_reset` implemented (`user/scripts/lazy_core.py:18526` at time of this audit) — no-op (returns False, never raises) when no signature file exists, it is unreadable/corrupt, or no run marker is present.
- [x] Defensive `Path(repo_root)` coercion present (a documented follow-on fix, `checkpoint-resume-rebaseline-crashes-on-str-repo-root`, closing a str/Path production crash — confirmed landed in `9e0f749d`).
- [x] Called from `lazy-state.py`'s checkpoint-resume `--run-start` block (`user/scripts/lazy-state.py:12179`) and `bug-state.py`'s mirror (`user/scripts/bug-state.py:7795`) — coupled-pair call sites present in both scripts.
- [x] Regression tests: `test_rebaseline_loop_signature_prevents_false_loop_on_checkpoint_resume` (`user/scripts/test_lazy_core.py:8178`) and `test_rebaseline_loop_signature_noop_when_absent_or_no_marker` (`:8237`) — both registered and green.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k rebaseline_loop_signature -q` is green; both state scripts' `--test` smoke harnesses pass.

**Runtime Verification:**
- [x] <!-- verification-only --> A checkpoint-resume re-probe of an unchanged route no longer inflates `repeat_count` to 2 on the first post-resume probe. **Verified (pre-landed):** `test_rebaseline_loop_signature_prevents_false_loop_on_checkpoint_resume` — GREEN.
- [x] <!-- verification-only --> The helper is a no-op (never raises) with no signature file / unreadable file / no run marker. **Verified (pre-landed):** `test_rebaseline_loop_signature_noop_when_absent_or_no_marker` — GREEN.

**MCP Integration Test Assertions:** N/A — no app runtime surface; pytest is the verification tier.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py` (all pre-landed; no edits made in this pass).

---

### Phase 2: Gap 2 — complexity floor on the loop-flip in `emit_cycle_prompt`

**Status:** Complete (pre-landed, `719c98aa`)

**Scope:** For an `/execute-plan` cycle, resolve the plan part's `plan_complexity` once:
`mechanical` → `model = "sonnet"` (unchanged); anything else (`complex` or the untagged/unknown
SAFE default) → mark the cycle `complexity_pinned_opus`. The loop-block downgrade then sets
`model = "sonnet"` ONLY when NOT `complexity_pinned_opus` — matching the subagent's
`model-tier-mismatch` refusal condition exactly.

**Deliverables:**
- [x] `complexity_pinned_opus` computed in `emit_cycle_prompt` (`user/scripts/lazy_core.py:7863-7886` at time of this audit) from `plan_complexity(Path(plan_token))`, defaulting to the SAFE `complex` for any uncertain case.
- [x] Loop-block downgrade guarded: `if not complexity_pinned_opus: model = "sonnet"` (`:7904`).
- [x] Stale comment block at the old `lazy_core.py:7168-7174` location replaced with the current docstring explaining the floor (confirmed present at `:7826-7833`, citing this bug by slug).
- [x] Test rename/addition per Fix Scope: `test_emit_cycle_prompt_loop_append_and_model_flip` (`:9245`) retargeted to a non-pinned (mechanical) cycle; `test_emit_cycle_prompt_complex_part_loop_stays_opus` (`:9462`) is the renamed assertion (opus retained on loop for a complex part); `test_emit_cycle_prompt_complex_part_cycle_model_opus` (`:9432`) covers the baseline (non-loop) complex-part opus tiering.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "emit_cycle_prompt" -q` is green.

**Runtime Verification:**
- [x] <!-- verification-only --> A `complexity: complex` (or untagged) `/execute-plan` part that loops (`repeat_count >= 2`) keeps `model = "opus"`. **Verified (pre-landed):** `test_emit_cycle_prompt_complex_part_loop_stays_opus` — GREEN.
- [x] <!-- verification-only --> A `mechanical` `/execute-plan` part, and every non-execute-plan cycle, still downgrades to `sonnet` on loop exactly as before. **Verified (pre-landed):** `test_emit_cycle_prompt_loop_append_and_model_flip` — GREEN.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1 (shares the checkpoint-resume boundary context; independently testable).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py` (pre-landed; no edits made in this pass).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to
`Fixed`, writes the `FIXED.md` receipt, and archives the bug. Not a checkbox in either phase — done
out-of-pipeline this round per `docs/bugs/CLAUDE.md` ("Fixing a bug OUT-OF-PIPELINE").

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

Close-out audit (2026-07-12): both gaps confirmed landed at HEAD via direct code read
(`lazy_core.rebaseline_loop_signature_after_registry_reset`, `emit_cycle_prompt`'s
`complexity_pinned_opus`) and both state scripts' checkpoint-resume call sites. Full suite:
`python -m pytest user/scripts/test_lazy_core.py -q` → 1063 passed (see FIXED.md for the exact
run this close-out cites).
