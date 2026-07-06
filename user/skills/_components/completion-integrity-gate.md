## Completion-Integrity Gate (inline, docs-only — gate for `__mark_complete__`)

**Why this component exists.** Three real failures showed that `__mark_complete__`'s
completion was trustworthy only by *convention*, not by *construction*:

1. A feature reached `Complete` while `PHASES.md` still had unchecked deliverables (SPEC/PHASES status incoherence).
2. A feature was flipped `Complete` on an ordinary implementation commit — bypassing `/mcp-test` entirely (and previously `/retro` before it was unwired in 2026-06) — and `is_workstation_complete()` happily skipped it forever, with **no durable evidence** that it ever passed a gate.
3. After a legitimate completion, `__mark_complete__` *deleted* `VALIDATED.md` / `RETRO_DONE.md`, so a real completion and an un-gated one became indistinguishable on disk.

This gate is the structural fix. It runs INSIDE `__mark_complete__`, AFTER the
`mcp-coverage-audit` returns `clean`, and BEFORE the ROADMAP strikethrough. It
does two things: (a) **verifies** completion preconditions, refusing the flip if
they don't hold; and (b) on pass, **delegates the receipt write, SPEC/PHASES
status flip, and sentinel cleanup** to the script (`--apply-pseudo __mark_complete__`),
which is the sole author of those writes — so completion is provable forever after.
`lazy-state.py` Step 2 keys on that receipt — a `Complete` claim without a receipt
is a `completion-unverified` hard-halt, which is what makes failure (2) impossible
to repeat.

The gate is docs-only — it reads `SPEC.md`, `PHASES.md`, and the validation
sentinels and runs no Tauri / no MCP server / no shell beyond `git`. It runs
identically in cloud and workstation.

### Inputs

- `{spec_path}` — the feature directory.
- `{feature_id}` — the feature directory basename.
- `{cloud}` — whether this is a cloud orchestrator (`/lazy-cloud`, `/lazy-batch-cloud`). Cloud has an extra rule below.

### Algorithm (run AFTER mcp-coverage-audit returns `clean`, BEFORE the flip)

1. **Phase-coherence check.** Read `{spec_path}/PHASES.md`. Count unchecked
   deliverables (`- [ ]` lines). The flip requires ZERO unchecked deliverables,
   EXCEPT rows under a Runtime-Verification / MCP-assertion subsection (the same
   verification-only carve-out `lazy-state.py::remaining_unchecked_are_verification_only`
   applies — those are ticked at MCP-test time and may legitimately remain if
   the validation sentinel attests they ran). Also confirm the top-level
   `PHASES.md **Status:**` is not still `Draft`/`Ready` (it should be
   `In-progress` or `Complete` by now). If a non-verification deliverable is
   still `- [ ]`, the feature is NOT done → **refuse** (Step 4 below).

2. **Validation-sentinel check.** Confirm at least one of these attests the MCP
   gate was satisfied:
   - `{spec_path}/VALIDATED.md` (full pass), OR
   - `{spec_path}/SKIP_MCP_TEST.md` (justified skip), OR
   - (`{cloud}` only) `{spec_path}/DEFERRED_NON_CLOUD.md` — cloud legitimately
     defers MCP to workstation. **Workstation must NOT accept a bare deferral as
     completion** — a workstation flip requires `VALIDATED.md` or
     `SKIP_MCP_TEST.md`.

   If no validation sentinel is present → **refuse** (Step 4).

   > **RETRO_DONE.md is NOT required (retro unwired, operator decision 2026-06).**
   > The /retro step was removed from the lazy pipeline — the state machine never
   > routes to `retro-feature`, so RETRO_DONE.md is never written for new
   > features/bugs. This gate therefore must NOT require it; requiring it would
   > block mark-complete forever (retro never runs to write it). Git history is
   > the restore path.

2a. **Device-deferral check (NEW).** Confirm `{spec_path}/DEFERRED_REQUIRES_DEVICE.md`
   is **NOT present**. That sentinel means real-device-only MCP assertions are
   still outstanding — device-deferral BLOCKS completion until a real-device run
   certifies the deferred scenarios and DELETES the sentinel. Its presence at
   mark-complete time means either the feature is being flipped without clearing
   the deferral, or a real-device re-open wrote `VALIDATED.md` but failed to
   delete the sentinel. Either way the on-disk state is incoherent — completing
   now would leave `Complete` + a deferral sentinel (the
   `complete-not-device-deferred` repo-lint contradiction). If present →
   **refuse** (Step 4) with a decision describing the gap (e.g. "feature carries
   DEFERRED_REQUIRES_DEVICE.md at mark-complete — certify the deferred scenarios
   on a real-device host, or delete the stale sentinel if already certified").
   This is the gate-level enforcement of the same invariant `lazy-state.py`
   routes around (it re-opens rather than completing while the sentinel exists).

2b. **Symptom-reproduction check (BUG PATH ONLY — `__mark_fixed__`).** This
   precondition applies **only** when the caller is the bug pipeline's
   `__mark_fixed__` (a `docs/bugs/**` item); feature completion (`__mark_complete__`)
   is unchanged and MUST skip it. For a bug, the validation-sentinel check in Step 2
   is **not sufficient** — a bug may not flip `Fixed` without a symptom-reproduction
   attestation per `~/.claude/skills/_components/symptom-reproduction-gate.md`:

   !`cat ~/.claude/skills/_components/symptom-reproduction-gate.md`

   Concretely, confirm the SPEC/PHASES/plan record carries the REQUIRED rung — a
   serving-path regression test (red→green on the symptom's *actual serving path*,
   NOT the fix's internal target), or the STRONGER runtime/manual artifact — bound
   to the SPEC's `## Reproduction Steps`. **`SKIP_MCP_TEST.md` satisfies the MCP
   validation-sentinel requirement (Step 2) but does NOT satisfy symptom
   reproduction for bugs** — the serving-path regression test lives in ordinary
   unit-test land and needs no MCP surface, so a no-MCP repo does not get a bypass
   here. If no symptom-reproduction attestation is present → **refuse** (Step 4),
   with a decision naming the missing serving-path evidence (e.g. "bug flip to Fixed
   with only a unit test on the fix's internal target — no serving-path regression
   test or runtime artifact reproducing the original symptom gone at its reported
   surface").

3. **All preconditions pass → delegate the receipt write + status flip + sentinel
   cleanup to the script.** The gate's responsibility here is to VERIFY (steps 1–2a
   above, plus 2b on the bug path) and then, on pass, to call the script as the single author:

   ```
   python3 ~/.claude/scripts/lazy-state.py \
       --apply-pseudo __mark_complete__ {spec_path}
   ```

   (For bugs, use `bug-state.py --apply-pseudo __mark_fixed__ {spec_path}`.)

   **The script enforces per-phase coherence as a MECHANICAL THIRD GATE before any
   write.** `apply_pseudo __mark_complete__` / `__mark_fixed__` parses PHASES.md
   per-phase (fence-aware) and, BEFORE writing the receipt or flipping any status,
   (a) AUTO-FLIPS any phase that has ≥1 checkbox, zero unchecked, and a
   non-`Complete`/non-`Superseded` Status line → `Complete` (deterministic and
   safe), then (b) REFUSES the whole operation (`refused:<reason>`, **zero writes —
   no receipt, no status flip, sentinels untouched**) if any phase would remain
   incoherent: any unchecked checkbox in any phase (verification rows included — by
   completion time the verification-only carve-out's job is done), or any phase
   Status that is not `Complete`/`Superseded` (a zero-checkbox non-Complete phase
   refuses too — there is no mechanical signal to flip on). The refusal message
   names the offending phases/rows. This is the structural backstop for the steps-1–2a
   prose checks: even if the gate prose missed an incoherent phase, the script will
   not write an incoherent completion.

   **On `ok: false` + this script-level refusal, route a corrective coherence cycle.**
   Treat it exactly like a Gate-1 uncovered-decision halt: do NOT flip, do NOT retry
   the apply blindly — dispatch a cycle subagent to reconcile PHASES.md HONESTLY
   (tick each unchecked verification row WITH on-disk evidence, or re-scope rows it
   cannot prove — never blind-tick to satisfy the gate), then return to the loop so
   the next `__mark_complete__`/`__mark_fixed__` attempt re-runs against a coherent
   PHASES.md. A blind tick that makes the script pass without real verification is
   the exact incoherence this gate exists to prevent.

   The script (`apply_pseudo` in `lazy_core.py`) is the **sole author** of the
   following writes — the gate and the consumer skill prose must NOT duplicate them:

   - **Writes** `{spec_path}/COMPLETED.md` (`kind: completed`, `provenance: gated`),
     folding validation evidence in before the sentinel deletes:
     - `validated_via:` — `mcp` if `VALIDATED.md` present, `skip-mcp-test` if only
       `SKIP_MCP_TEST.md`.
     - `mcp_pass_count` / `mcp_total_count` — copied from `MCP_TEST_RESULTS.md`
       if present.
   - **Flips** `SPEC.md **Status:** Complete` (first occurrence) and
     `PHASES.md **Status:** Complete` (first occurrence) when those files exist.
   - **Deletes** `VALIDATED.md`, `RETRO_DONE.md` (if present — retro is unwired,
     so new features carry none; a stale one from an in-flight feature is still
     cleaned up), and `DEFERRED_NON_CLOUD.md` (content now lives in the receipt).
     Keeps `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`, `COMPLETED.md`, and `plans/`.

   The **ROADMAP strikethrough** (multi-line fuzzy edit) remains the orchestrator's
   responsibility — it is not a deterministic scripted write and stays in skill
   prose.

   Commit the resulting file changes per project policy after the script exits 0.

4. **Refuse path (any precondition in steps 1–2a fails, or the bug-path 2b symptom-reproduction check fails).** Do NOT flip. Do NOT
   write `COMPLETED.md`. This means the state script emitted `__mark_complete__`
   for a feature that isn't actually finishable — a genuine inconsistency. Write
   `{spec_path}/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`,
   `next_skill: lazy`) with one decision describing the gap (e.g. "PHASES.md has
   3 unchecked implementation deliverables but Step 10 was reached" or "no
   VALIDATED.md/SKIP_MCP_TEST.md present at mark-complete"), commit it, and
   return `refused:<reason>` to the consumer. The consumer halts this cycle
   exactly as it does for the mcp-coverage-audit `uncovered:N` case; the next
   state-script call surfaces `needs-input` and the operator reconciles.

### Return status to the consumer

- `gated` — preconditions met; the script has written `COMPLETED.md`, flipped
  `SPEC.md`/`PHASES.md` status to `Complete`, and deleted `VALIDATED.md` /
  `RETRO_DONE.md` (if present) / `DEFERRED_NON_CLOUD.md`. The consumer's only
  remaining step is the ROADMAP strikethrough (the single orchestrator-side
  write that the script does not perform).
- `refused:<reason>` — `NEEDS_INPUT.md` written; consumer MUST NOT flip this
  cycle. Print a one-line halt note (`🛑 completion-integrity gate: <reason> — NEEDS_INPUT.md written; mark-complete deferred.`) and return.

### Coupling note

Consumed by `__mark_complete__` in all four /lazy-family skills and by `__mark_fixed__` in the bug pipeline, ALWAYS as the second gate after `mcp-coverage-audit.md`:
- `user/skills/lazy/SKILL.md` Step 3 `__mark_complete__`
- `user/skills/lazy-batch/SKILL.md` Step 1c.5 `__mark_complete__`
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` Step 3 `__mark_complete__`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` Step 1c.5 `__mark_complete__`
- `user/skills/lazy-bug/SKILL.md` `__mark_fixed__` (Gate 2)
- `user/skills/lazy-bug-batch/SKILL.md` Step 1c.5 `__mark_fixed__` (Gate 2)

When editing this component, run `grep -rl "completion-integrity-gate.md" ~/.claude/skills/ ~/.claude/skills/_components/ --include="*.md"` to confirm the blast radius matches the six files above.
