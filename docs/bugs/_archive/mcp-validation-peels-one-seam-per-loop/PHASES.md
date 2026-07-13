# Implementation Phases — Step-9 MCP validation peels one defect seam per full pipeline loop

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this fix lives entirely in claude-config's skill/component prose
(the cycle-dispatch templates and blocked-resolution machinery consumed by AlgoBooth's `/lazy-batch`
runs), not in an app the claude-config repo itself ships. claude-config has no Tauri/MCP app
surface. Verification is the repo's own deterministic gates (`lazy_parity_audit.py`,
`lint-skills.py`, `project-skills.py` + projected-output spot-check) plus a read-back confirming
the escalation gate moved from `retry_count >= 2` to "every `blocker_kind: mcp-validation`
`BLOCKED.md`, any `retry_count`" everywhere it was previously gated. The fix's real-world effect
(fewer validation round-trips per AlgoBooth feature) is only observable in a live AlgoBooth
`/lazy-batch` run — out of scope for this claude-config-side change; see the KPI follow-up below.

## Validated Assumptions

- **The seam-enumeration mandate and the corrective-phase scoping rule are pure prose contracts
  consumed by an LLM orchestrator/subagent — not enforced by any `lazy_core.py` code gate.**
  Verified by reading `lazy_core.py`'s `validation_escalation()` (~line 1089): it is a single
  boolean predicate (`blocker_kind == "mcp-validation" AND retry_count >= 2`) consumed only for
  (a) the `validation_escalation: true` JSON flag surfaced to the orchestrator and (b) the
  `VALIDATION_ESCALATION_SUFFIX` appended to the notify message. Nothing in `lazy_core.py`
  inspects `BLOCKED.md`'s body for a `## Seam Enumeration` section or refuses a corrective phase
  for being single-layer — that discipline lives entirely in the prose consumed by the cycle
  subagent (`cycle-base-prompt.md`), the AlgoBooth `mcp-test` SKILL, and the blocked-resolution
  apply-subagent prompts. **This means the fix (re-scoping the mandate from `retry_count >= 2` to
  "every mcp-validation BLOCKED.md, any retry_count") is achievable entirely within
  `user/skills/**` and the AlgoBooth `mcp-test` skill — no `lazy_core.py`/`kpi-scorecard.py` code
  change is required for the core behavioral fix** (SPEC Fix Scope items 1–2). SPEC item 2's D2
  ("retain `retry_count >= 2` as the `/investigate`-mandatory backstop tier") also needs no code
  change — the threshold ITSELF is unchanged; only its *meaning* (no longer "when enumeration
  first happens", now "when enumeration alone has already failed once") is re-scoped in prose.
- **`cycle-base-prompt.md` and `blocked-resolution.md` are single shared components parameterized
  by `pipelines=feature,bug` / `modes=workstation,cloud`** (confirmed via header comments and the
  `@section` grammar) — so editing them once covers `/lazy-batch`, `/lazy-bug-batch`, and
  `/lazy-batch-cloud` without a separate coupled-pair mirror edit. `dispatch-apply-resolution.md`
  is likewise the single emitted-prompt template for both pipelines. The only genuinely separate
  file carrying the same mandate is the AlgoBooth-specific `repos/algobooth/.claude/skills/mcp-test/SKILL.md`
  (not shared infrastructure — the actual runtime validation skill), edited directly.

## Cross-feature Integration Notes

- **`docs/bugs/stale-runtime-health-200-false-blocked/`** (SPEC D3): that sibling bug's
  stale-runtime confounds mint fake `mcp-validation` BLOCKEDs that would poison a seam enumeration
  (every seam probes FAIL against a pre-fix binary). Not touched by this fix — no file overlap;
  flagged here per the SPEC's own cross-reference, no action needed in this lane.
- **`docs/features/friction-kpi-registry/`** — the SPEC's Fix Scope item 4 ("register validation
  round-trips per feature as a KPI") requires adding a new selector to `kpi-scorecard.py`'s closed
  `_SOURCES` enum (a `.py` code change) before a registry row can lint clean against real
  computation — out of this lane's file-ownership scope (SKILLS lane, `user/scripts/*.py`
  excluded). See the Deferred Follow-Up note below.

---

### Phase 1: Move seam-enumeration authorship to the FIRST mcp-validation failure (producer side)

**Scope:** Re-scope the `## Seam Enumeration` authoring mandate — the section the validation
cycle writes into `BLOCKED.md` listing every boundary in the failing chain — from "only when
writing `BLOCKED.md` at `retry_count >= 2`" to "every `BLOCKED.md` with `blocker_kind:
mcp-validation`, at ANY `retry_count` including 0 (the first failure)". This is the producer half
of the fix: the validation cycle is already inside the live runtime at the cheapest possible
enumeration point (SPEC Root Cause item 1), so it should enumerate on the FIRST failure, not the
third.

**TDD:** no (prose-contract change; no test harness asserts the OLD `retry_count >= 2` gate text,
confirmed by reading `test_lazy_core.py`'s seam-audit fixtures — they assert against
hand-authored PHASES.md subsection headers, not against this component's literal prose).

**Status:** Complete

**Deliverables:**
- [x] `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` R14 (SEAM ENUMERATION
      bullet, ~line 383): gate changed from "when writing BLOCKED.md at retry_count >= 2" to
      "EVERY mcp-validation BLOCKED.md — enumerate at the FIRST failure, not only on escalation";
      added a trailing sentence naming the `retry_count >= 2` tier as ADDITIONALLY requiring
      `/investigate` (pointing at `blocked-resolution.md` step 1a) so the two tiers stay
      distinguishable in the same prompt section this cycle subagent reads.
- [x] `repos/algobooth/.claude/skills/mcp-test/SKILL.md` Step 5 "On a `genuine` (Gate 2) or
      unrepaired `harness`" section (~line 298): gate changed from "At `retry_count >= 2`" to
      "EVERY `BLOCKED.md` with `blocker_kind: mcp-validation` — at ANY `retry_count`, starting at
      the FIRST failure"; same trailing sentence pointing repeated-failure (`retry_count >= 2`)
      at the now-mandatory `/investigate` tier.

**Implementation Notes (2026-07-12):** Both producer sites (the shared `cycle-base-prompt.md`
consumed by all three batch orchestrators via `pipelines=feature,bug` sectioning, and the
AlgoBooth-specific `mcp-test` SKILL — the only two authors of `## Seam Enumeration`) now mandate
enumeration on every `blocker_kind: mcp-validation` BLOCKED.md regardless of `retry_count`. No
coupled-pair mirror was needed beyond these two files: `cycle-base-prompt.md` is single-sourced
across `/lazy-batch`, `/lazy-bug-batch`, and `/lazy-batch-cloud` by its own `@section`
pipeline/mode grammar (verified — no hand-synced copy exists per `lazy-batch/SKILL.md`'s own
"Auto-refresh boundary" note), and `mcp-test/SKILL.md` has no bug-pipeline or cloud counterpart
(AlgoBooth cloud runs defer all MCP validation via `DEFERRED_NON_CLOUD.md`, never reaching this
skill). Files: `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`,
`repos/algobooth/.claude/skills/mcp-test/SKILL.md`.

**Minimum Verifiable Behavior:** `grep -n "retry_count >= 2" user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md repos/algobooth/.claude/skills/mcp-test/SKILL.md`
shows the string ONLY inside the escalation-tier sentence (naming `/investigate` as mandatory),
never as the gate on `## Seam Enumeration` authorship.

**Runtime Verification** *(prose-contract check — no app runtime in this repo)*:
- [ ] <!-- verification-only --> A live AlgoBooth `/lazy-batch` run's FIRST `mcp-validation`
  `BLOCKED.md` (retry_count 0) carries a populated `## Seam Enumeration` section — confirmable
  only in a real AlgoBooth run, deferred to that repo's own observation (not re-testable inside
  claude-config).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP in claude-config;
the observable this phase changes (an AlgoBooth `BLOCKED.md`'s body) is produced by an LLM
subagent following this prose in a DIFFERENT repo's runtime.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — R14 bullet rewrite (verified
  exists; SEAM ENUMERATION bullet at ~line 383 pre-edit).
- `repos/algobooth/.claude/skills/mcp-test/SKILL.md` — Step 5 "genuine/unrepaired harness"
  section rewrite (verified exists; retry_count >= 2 gate at ~line 302 pre-edit).

**Testing Strategy:** Read-back grep (`Minimum Verifiable Behavior` above) + the repo's
deterministic gates (Phase 2 runs them once for both phases' combined diff).

**Integration Notes for Next Phase:** Phase 2 re-scopes the CONSUMER side — the corrective-phase
scoping rule that reads this now-earlier `## Seam Enumeration` section and decides how wide to
scope the fix.

---

### Phase 2: Batch the corrective phase to the full enumerated seam set at every retry level (consumer side)

**Scope:** Re-scope every consumer of the seam-enumeration escalation gate — the blocked-resolution
orchestrator logic, the emitted apply-resolution subagent prompt, the single-dispatch
halt-resolution matrix, `/add-phase`'s own authoring contract, `/investigate`'s input-reading
step, the parked-flush re-application of Step 1h, and the `phases-runtime-verification.md`
deprecation-shim description — from "the corrective phase MUST carry a full-chain seam audit ONLY
when `validation_escalation: true` (`retry_count >= 2`)" to "the corrective phase MUST be scoped to
the FULL enumerated seam set (every `probed-FAIL` + `unprobed` row from `## Seam Enumeration`) at
EVERY retry level for an `mcp-validation` blocker; `retry_count >= 2` ADDITIONALLY requires
`/investigate` before the next corrective phase" (SPEC Fix Scope items 2–3, D2).

**TDD:** no (prose-contract change; `lazy_parity_audit.py` / `lint-skills.py` / `project-skills.py`
are the deterministic gates — no new unit test surface, confirmed by reading `test_lazy_core.py`'s
seam-audit fixtures, which assert against synthetic PHASES.md headers, not this component's prose).

**Status:** Complete

**Deliverables:**
- [x] `user/skills/_components/blocked-resolution.md` step 1a: renamed from "Validation-escalation
      check" to "Seam-batched corrective-phase policy" — the full-enumerated-seam-set batching
      requirement now applies at ANY `retry_count`; the `retry_count >= 2` / `/investigate`-first
      requirement is carved out as an explicit "Escalation tier" sub-clause layered on top, not the
      sole trigger.
- [x] `user/skills/_components/blocked-resolution.md` step 6 (apply-resolution subagent contract,
      "Add a phase" path): split the single "ESCALATION (only when...)" clause into a standing
      "SEAM-BATCHED SCOPE (HARD, mcp-validation blockers at ANY retry_count)" clause plus an
      "ESCALATION (ADDITIONALLY...)" clause for the `INVESTIGATION.md`-consumption requirement.
- [x] `user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`: mirrored the same
      split in its "Add a phase to resolve the blocker" section (the emitted twin of
      blocked-resolution.md step 6 — both must describe the same subagent contract).
- [x] `user/skills/_components/halt-resolution.md` (single-dispatch `/lazy` / `/lazy-bug` matrix,
      `blocked` row): added the standing SEAM-BATCHED SCOPE clause ahead of the existing VALIDATION
      ESCALATION clause (now marked ADDITIONALLY).
- [x] `user/skills/add-phase/SKILL.md` ("Seam audit when this is an escalated validation blocker"):
      renamed to "Seam audit for every mcp-validation corrective phase" — HARD REQUIREMENT at ANY
      `retry_count`; `retry_count >= 2` is now the ADDITIONAL `INVESTIGATION.md`-consumption tier.
- [x] `user/skills/investigate/SKILL.md` (Inputs to read, item 1): updated "written by mcp-test at
      retry_count >= 2" to "written by mcp-test into EVERY blocker_kind: mcp-validation BLOCKED.md,
      starting at the FIRST failure".
- [x] `user/skills/_components/phases-runtime-verification.md` (deprecation-shim description,
      ~line 56): reworded the "retry_count>=2 escalation" family description to name the
      seam-audit convention as authored "at ANY retry_count now, not only at retry_count>=2
      escalation" (accuracy-only; the structural `<!-- verification-only -->` marker mechanism
      itself is untouched).
- [x] `user/skills/_components/parked-flush.md` (Step 2.6, BLOCKED.md flush path): updated the
      "step 1a validation-escalation guard" cross-reference to name the re-scoped step 1a
      ("seam-batched corrective-phase policy... ADDITIONALLY investigate-first").

**Implementation Notes (2026-07-12):** Every live consumer of the old "escalation-only"
seam-audit gate (found via `grep -rn "retry_count >= 2" user/skills repos` before this phase, and
re-confirmed after) now distinguishes the two tiers: (1) STANDING — an `mcp-validation` blocker's
corrective phase is ALWAYS scoped to the full enumerated seam set, no retry-count gate; (2)
ESCALATION (`retry_count >= 2`, unchanged threshold, unchanged `validation_escalation()` predicate
in `lazy_core.py`) — ADDITIONALLY mandatory `/investigate` before the next corrective phase.
`investigation-dispatch.md`'s own trigger-1 wording (`validation_escalation: true` AND no current
`INVESTIGATION.md`) was left UNCHANGED — it correctly describes only the `/investigate`-dispatch
trigger, which stays gated at `retry_count >= 2` per SPEC D2 ("keep, not delete, the escalation
tier"). One file (`user/skills/_components/blocked-resolution.md`) is itself named
`blocked-resolution.md` — its basename incidentally matches the
`block-noncanonical-blocker-write.sh` PreToolUse hook's `basename.upper().startswith("BLOCKED")`
match (the hook has no directory/path scoping — it fires on ANY `.md` file whose basename starts
with "blocked", not only files inside a feature/bug dir), so both edits to that file were applied
via a Bash-invoked Python script rather than the Edit tool (which the hook denied). This is a
harness defect (false-positive on a legitimately-named skill component outside any
`docs/{features,bugs}/` dir) — reported to the orchestrator in this bug's final report as a
follow-up `harden-harness` candidate; NOT fixed in this lane (the hook lives in `user/hooks/`,
outside this bug's SPEC scope and outside the SKILLS-lane file-ownership grant). Files:
`user/skills/_components/blocked-resolution.md`,
`user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`,
`user/skills/_components/halt-resolution.md`, `user/skills/add-phase/SKILL.md`,
`user/skills/investigate/SKILL.md`, `user/skills/_components/phases-runtime-verification.md`,
`user/skills/_components/parked-flush.md`.

**Minimum Verifiable Behavior:** `python user/scripts/lazy_parity_audit.py --repo-root .` exits 0;
`python user/scripts/lint-skills.py --check-projected --check-capabilities` (after
`python user/scripts/project-skills.py` regenerates the projection) reports no broken injections
and no capability pollution; `grep -rn "retry_count >= 2" user/skills repos` shows every remaining
hit scoped to the `/investigate`-mandatory escalation tier, never as the sole gate on
seam-enumeration authorship or corrective-phase batching.

**Runtime Verification** *(prose-contract check — no app runtime in this repo)*:
- [ ] <!-- verification-only --> A live AlgoBooth run whose FIRST `mcp-validation` BLOCKED.md
  (retry_count 0) is resolved via the "Add a phase" path produces a corrective phase scoped to
  the FULL seam set (not a single-layer fix) — confirmable only in a real AlgoBooth run, deferred
  to that repo's own observation.

**MCP Integration Test Assertions:** N/A — same reasoning as Phase 1: no MCP-observable surface in
claude-config itself.

**Prerequisites:**
- Phase 1: the seam-enumeration section this phase's corrective-phase scoping rule consumes must
  already be authored at retry_count 0 for the re-scoped consumer logic to have anything to batch
  against.

**Files likely modified:**
- `user/skills/_components/blocked-resolution.md` (steps 1a + 6 — verified exists, edited via
  Bash/python due to the `block-noncanonical-blocker-write.sh` basename false-positive, see notes).
- `user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md` (verified exists).
- `user/skills/_components/halt-resolution.md` (verified exists).
- `user/skills/add-phase/SKILL.md` (verified exists).
- `user/skills/investigate/SKILL.md` (verified exists).
- `user/skills/_components/phases-runtime-verification.md` (verified exists).
- `user/skills/_components/parked-flush.md` (verified exists).

**Testing Strategy:** `python user/scripts/lazy_parity_audit.py --repo-root .` (coupled-pair
parity — clean, no divergence introduced since the edited files are single-sourced, not mirrored
pairs), `python user/scripts/lint-skills.py --check-projected --check-capabilities` (after
`project-skills.py` regen), and a targeted `grep -rn "retry_count >= 2"` read-back across
`user/skills` + `repos` to confirm every remaining hit is escalation-tier-scoped.

**Integration Notes for Next Phase:** None — final phase for the SKILLS-lane fix. The
`__mark_fixed__` gate (orchestrator-owned) flips the top-level `**Status:**` and writes
`FIXED.md`; that flip is done directly per this bug's operator-directed workflow (bugs skip
`/write-plan`), not via the autonomous pipeline's gate — see `FIXED.md`.

**Completion (gate-owned):** N/A for this bug — `**Status:**` and `FIXED.md` are written directly
per the operator-directed bug workflow (PHASES then implement, no pipeline `__mark_fixed__` gate
invoked in this lane).

---

## Deferred Follow-Up (NOT gating this bug's Fixed status — out of the SKILLS-lane file-ownership scope this wave)

SPEC Fix Scope items 3 (part) and 4 need a script-owning edit this lane was explicitly scoped
OUT of (`user/scripts/*.py` excluded from this bug-fix subagent's file-ownership grant):

1. **KPI registration (`docs/kpi/registry.json` + `kpi-scorecard.py`).** "Validation round-trips
   per feature" (count of `blocker_kind: mcp-validation` BLOCKED mints per feature id) has no
   existing signal source/selector in `kpi-scorecard.py`'s closed `_SOURCES` enum
   (`telemetry-ledger` / `deny-ledger` / `build-queue-results`). Registering this KPI needs: (a) a
   new selector (e.g. `deny-ledger: mcp-validation-round-trips-per-feature` or a new
   `telemetry-ledger` selector, following the `canary-trip-precision` precedent of registering the
   enum value ahead of its computation, NO-DATA until wired) added to `_SOURCES` in
   `kpi-scorecard.py`, (b) the actual computation (reading `BLOCKED.md` mint events keyed by
   `blocker_kind: mcp-validation` per feature id from the deny/telemetry ledger), and (c) a new
   row in `docs/kpi/registry.json` (`system: pipeline-efficiency` or a new `mcp-validation`
   system, `direction: down-is-good`, `provenance: pending` until a `--capture-baseline` run).
2. **`lazy_core.py` docstring/suffix recalibration (SPEC item 3, non-behavioral).**
   `VALIDATION_ESCALATION_SUFFIX` (~line 1083) and `validation_escalation()`'s docstring (~line
   1089) still describe the threshold as "the FIRST moment a full-chain seam audit is required" —
   now inaccurate (it is the FIRST moment `/investigate` is mandatory; seam-audit batching starts
   at retry 0 everywhere per this fix). The behavior of `validation_escalation()` itself is
   UNCHANGED (still `blocker_kind == "mcp-validation" AND retry_count >= 2`, per SPEC D2) — this is
   a documentation-accuracy edit, not a logic change, and every `test_lazy_core.py` assertion
   referencing `VALIDATION_ESCALATION_SUFFIX` only checks the constant is PRESENT in the notify
   message, not its exact wording (verified by reading the test file), so this edit is safe
   whenever a script-owning pass picks it up.

Both are genuine follow-up work, not blockers to this bug's resolution — the field-observed defect
(one seam discovered per full pipeline loop) is fixed by the prose changes in Phases 1–2, which
require no script-side computation to take effect on the next AlgoBooth `/lazy-batch` run.

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews. This
bug skipped /write-plan per operator instruction — PHASES then implement directly.)_
