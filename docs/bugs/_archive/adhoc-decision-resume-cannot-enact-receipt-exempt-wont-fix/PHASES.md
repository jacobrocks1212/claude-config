# Implementation Phases — decision-resume apply-resolution cannot enact an operator-chosen receipt-exempt Won't-fix close

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a skills-lane
prose-contract fix (dispatch-template wording + a shared token-binding helper) verified via the
`test_lazy_core.py` pytest suite (`emit_dispatch_prompt` template-rendering assertions) and the
skill-projection/lint/parity gates. There is no `mcp-tool-catalog.md` in this repo, so the
planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The fix for this bug's Root Cause was ALREADY LANDED before this bug-subagent pass started** —
  discovered on inspection (per this run's standing instruction to check for a pre-landed fix
  before implementing). `git log --oneline -- user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`
  shows commit `fc5f5371` ("harden(dispatch-template): let apply-resolution enact operator-chosen
  receipt-exempt Won't-fix close"), authored during the SAME Round-31 hardening pass that produced
  this bug's own SPEC.md, and its diff implements this SPEC's Fix Scope items 1–4 **verbatim** (the
  commit message cites the identical root cause, the identical split-token design, and the identical
  first-instance target `adhoc-incident-hook-deny-19343d`). This bug's SPEC and the landed fix are
  two artifacts of the same hardening discovery — the fix was dispatched and committed under the
  triggering bug's context before this bug's own tracking doc reached its terminal state.
- **Fix Scope item 5 (regression tests) is ALSO already landed**, in the SAME commit:
  `test_standard_bindings_split_terminal_statuses` and
  `test_apply_resolution_emits_terminal_disposition_close` in `user/scripts/test_lazy_core.py`
  (lines ~33546–33589), both passing, covering both pipelines (bug `Won't-fix` / feature
  `Superseded`).
- **Fix Scope item 4 (first-instance enactment) is verified on disk**:
  `docs/bugs/_archive/adhoc-incident-hook-deny-19343d/SPEC.md` shows `**Status:** Won't-fix` with
  its `## Resolution` intact, confirming the terminal-disposition step 2b actually fired in the
  field (not just unit-tested) — this is the field evidence for symptom reproduction below.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC (only a `**Related:**` line naming
`adhoc-incident-hook-deny-19343d`, `hardening-log Round 14`, and the two consumed components). No
upstream PHASES.md look-back applies — this bug has no sibling PHASES.md in flight referencing the
same files beyond the already-landed commit inspected above.

**Scope boundary checked and confirmed NOT expanded:** the orchestrator's dispatch brief asked to
also check `blocked-resolution.md` / `parked-flush.md` for the identical defect. Both route BLOCKED
items through the SAME `dispatch-apply-resolution.md` "blocked" resolution-kind section (lines
83–141), but that section's own option menu (Add-a-phase / Defer / Halt / Other) has no "close
without a fix" affordance — Won't-fix/Superseded closes are a needs-input-only concept in this
codebase (an operator resolves a `NEEDS_INPUT.md` decision toward a terminal close; a `BLOCKED.md`
represents "how do we proceed with work," not "should this item still be worked at all"). The
shared CONSTRAINTS section's receipt-exempt permission (line 215) is deliberately scoped to
"the needs-input terminal-disposition step 2b above" — narrower than the blocked path, matching
that path never offering the close. This is a real, narrower structural asymmetry (an operator
could theoretically direct a close via the blocked path's "Other" catch-all and hit an equivalent
gap), but it is **out of THIS SPEC's Fix Scope** (which named `dispatch-apply-resolution.md`'s
needs-input path and `decision-resume.md` only, and stated "Scope is narrow" deliberately). Flagged
in the final report as a discovered-but-unscoped observation for a future hardening item, not
folded into this bug's fix.

---

### Phase 1: Verify the pre-landed fix satisfies every Fix Scope item; close out the tracking doc

**Scope:** No new code or prose changes to `dispatch-apply-resolution.md`, `decision-resume.md`, or
`lazy_core.py` — commit `fc5f5371` already implements all five Fix Scope items. This phase is
verification-only: confirm each item against the current file/test state, run the mandated gates,
and flip this bug's own SPEC.md to its terminal status (the one artifact this bug's SPEC still
owned that the triggering commit did not touch).

**TDD:** N/A — no new implementation; the regression tests already exist and are already green
(landed in the same pre-existing commit).

**Status:** Complete (verification-only; the fix itself pre-landed in `fc5f5371`)

**Deliverables:**
- [x] Fix Scope item 1 (`lazy_core._standard_dispatch_bindings` split into additive
  `receipt_gated_status` / `receipt_exempt_status`, `forbidden_status` left UNCHANGED) — confirmed
  landed: `user/scripts/lazy_core.py` (`_standard_dispatch_bindings`) returns both new keys per
  pipeline (`Fixed`/`Won't-fix` for bug, `Complete`/`Superseded` for feature) alongside the
  unchanged compound `forbidden_status`. Verified by reading the function body and by
  `test_standard_bindings_split_terminal_statuses` (GREEN).
- [x] Fix Scope item 2 (`dispatch-apply-resolution.md` needs-input step 2b TERMINAL DISPOSITION +
  reworded constraint) — confirmed landed: the needs-input section (lines 42–53) carries the
  `2b. TERMINAL DISPOSITION` step, and the shared CONSTRAINTS section (line 215) reads "The
  receipt-GATED terminal status ... must NOT be set ... unless a valid receipt already exists ...
  The receipt-EXEMPT terminal status ... is DIFFERENT ... you MAY set it, but ONLY when the
  operator's chosen resolution directs closing" — i.e. the blanket ban is narrowed exactly as
  specified, never weakening the receipt-gated (Fixed/Complete) side.
- [x] Fix Scope item 3 (`decision-resume.md` mirrors the terminal-disposition note) — confirmed
  landed: `user/skills/_components/decision-resume.md` step 2b (added between the existing steps 2
  and 3) carries the same TERMINAL DISPOSITION note, keeping the reference contract and the emitted
  prompt in lockstep.
- [x] Fix Scope item 4 (first instance — `adhoc-incident-hook-deny-19343d` enacted to
  `Status: Won't-fix`) — confirmed landed AND field-verified: `docs/bugs/_archive/adhoc-incident-hook-deny-19343d/SPEC.md`
  reads `**Status:** Won't-fix` with its `## Resolution` (`resolved_by` disposition trace) intact,
  and the bug is present under `_archive/` (i.e. the pipeline's archive-on-fix/archive-on-terminal
  path picked it up cleanly after the status flip — no loop re-formed).
- [x] Fix Scope item 5 (regression tests in `test_lazy_core.py`, split-token bindings + emitted
  terminal-disposition step for both pipelines) — confirmed landed and GREEN:
  `test_standard_bindings_split_terminal_statuses` and
  `test_apply_resolution_emits_terminal_disposition_close` (`user/scripts/test_lazy_core.py`
  ~L33546–33589); both assert on the REAL rendered template via `emit_dispatch_prompt(...,
  template_dir=_REAL_TEMPLATE_DIR)`, not a mock, so they are lockstepped to the actual prose file.
- [x] Ran the mandated gates this pass (see Runtime Verification below) — all green, confirming no
  regression and no dangling `!cat`/token residue from the prior commit's edits.
- [x] This bug's own `SPEC.md` `**Status:**` flipped `Concluded` → `Fixed` (the one remaining
  artifact this bug's own tracking doc owned that the triggering-bug commit did not touch — that
  commit updated `adhoc-incident-hook-deny-19343d/SPEC.md`, not this bug's SPEC.md).

**Implementation Notes (2026-07-12):** Investigated whether the fix described in this bug's Root
Cause / Fix Scope was already implemented before starting (per the run's standing pre-landed-fix
check). It was — in full, including its own regression tests and its own first-instance field
application — landed in `fc5f5371f0992184f3d32374393a3296237f899e`, authored during the same Round-31
hardening pass that produced this bug's SPEC.md. No `dispatch-apply-resolution.md`,
`decision-resume.md`, or `lazy_core.py` edits were made in this pass; this phase exists to record
the verification trail and close out this bug's own tracking artifacts, which the triggering
commit's scope did not include (it flipped `adhoc-incident-hook-deny-19343d`'s status, not this
bug's). Files inspected (not modified): `user/scripts/lazy_core.py`,
`user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`,
`user/skills/_components/decision-resume.md`, `user/scripts/test_lazy_core.py`,
`docs/bugs/_archive/adhoc-incident-hook-deny-19343d/SPEC.md`. Files modified this pass:
`docs/bugs/adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix/SPEC.md` (Status flip),
`docs/bugs/adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix/PHASES.md` (this file, new),
`docs/bugs/adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix/FIXED.md` (receipt, new).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "terminal_disposition or split_terminal_statuses" -q` is GREEN against the current tree (both new since the same commit, no fresh RED-for-the-right-reason cycle needed — the fix was never absent during this pass).

**Runtime Verification** *(checked by the pytest suite + the skill-projection/lint/parity gates — no app runtime):*
- [x] <!-- verification-only --> `python user/scripts/lazy_parity_audit.py --repo-root .` → exit 0
  (no coupled-pair drift introduced; neither touched-in-this-pass file is a mirrored pair, and none
  was edited this pass).
- [x] <!-- verification-only --> `python user/scripts/lint-skills.py --check-projected --check-capabilities`
  → exit 0 ("no broken or embedded !cat patterns", "no unexpanded !cat patterns in projected
  output", "no capability namespace pollution detected").
- [x] <!-- verification-only --> `python user/scripts/project-skills.py` → clean re-projection
  (`Skills projected (_default): 88`, `Errors (_default): none`, all 3 discovered repos
  re-projected with 0 errors) — confirms `dispatch-apply-resolution.md`'s step 2b and the
  reworded constraint expand correctly through every consumer, including the per-repo AlgoBooth /
  Cognito Forms projections.
- [x] <!-- verification-only --> `python -m pytest user/scripts/test_lazy_core.py -k "terminal_disposition or split_terminal_statuses" -q` → both tests pass, asserting against the REAL on-disk template (`_REAL_TEMPLATE_DIR`), not a stub.

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; the fix is a
dispatch-prompt template + a shared token-binding helper, verified by template-rendering pytest
assertions and the field evidence of the already-archived triggering bug's successful Won't-fix
close.

**Prerequisites:** None (first and only phase).

**Files likely modified:** none in this pass beyond this bug's own tracking docs (see
Implementation Notes). The fix files (`user/scripts/lazy_core.py`,
`user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`,
`user/skills/_components/decision-resume.md`, `user/scripts/test_lazy_core.py`) were inspected only
— already correct from `fc5f5371`.

**Testing Strategy:** Read-and-confirm against the already-landed commit's diff + the already-green
test suite; re-run the three mandated gates to prove no regression was introduced by anything since
that commit. No new tests authored (the existing pair is a faithful, non-mocked characterization of
the exact defect this bug's SPEC describes).

**Integration Notes for Next Phase:** None — final phase. This bug closes with `**Status:** Fixed`
+ `FIXED.md`, written directly by this bug-subagent pass (operator-directed-interactive provenance,
per the run's standing protocol for a verification-only close) — NOT by the pipeline's
`__mark_fixed__` gate (this bug never entered `/plan-bug` → `/execute-plan`; its fix landed via a
sibling hardening dispatch before this bug's own pipeline cycle ran).

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews. Not
applicable here — this bug bypassed `/plan-bug`/`/execute-plan` per the bug-subagent
verification-only protocol.)_
