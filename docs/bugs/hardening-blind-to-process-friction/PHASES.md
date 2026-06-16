# Implementation Phases — Hardening stage blind to process/behavioral friction

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a claude-config harness repo (no Tauri, no MCP server, no app surface; see `.claude/skill-config/capabilities.txt`). Validation is the repo's own pytest + lint-skills + project-skills + parity-audit suite per `.claude/skill-config/quality-gates.md`. The lazy Step-9 MCP gate is operator-exempt here.

## Scope summary

The SPEC concludes three distinct gaps (Proven Findings #4), driven by Locked Decisions D1–D4:

- **(c) prevention-targeting** — the C2 hook (`lazy-cycle-containment.sh`) and the C3 refusals (`refuse_if_cycle_active`) trip off a marker the orchestrator must remember to arm (`--cycle-begin`), and even when armed the hook denies *all* `Agent` calls including the orchestrator's own legitimate dispatch. **D4** replaces marker-armed containment with `agent_id`-targeted containment: deny recursion/lifecycle **when `agent_id` is present** (caller is a subagent), allow when absent (main-thread orchestrator). → **Phase 1**.
- **(a) detection** — nothing converts a torn-down cycle bracket or overstepped commits into hardening debt, so a runaway leaves valid-looking terminal state and no trigger fires. **D1/D3** add `--cycle-begin` run-identity + HEAD snapshot, and a `--cycle-end` check that appends a process-friction ledger entry on a cycle-bracket break or unexpected commits, so the probe withholds the forward route exactly like a guard deny. → **Phase 2**.
- **(b)/routing** — the orchestrator has no trigger class for the new ledger entry. **D2** ("always harden") wires a process-friction trigger into the hardening-routing prose (`lazy-batch`, `lazy-bug-batch`, `harden-harness`, dispatch template), keeping the coupled `lazy-batch-cloud` consistent. → **Phase 3**.

**Phase ordering rationale:** Phase 1 ships the prevention fix that addresses the literal incident (it would have denied the runaway's recursive `/lazy-batch` and `--run-end` directly) and is independently verifiable. Phase 2 adds the deterministic detector that self-announces any future bypass. Phase 3 is the prose layer that consumes Phase 2's ledger entry; it is last because it has nothing to route until the entry shape exists.

**D1-out (deferred, per SPEC):** runtime/background-task death heuristics (`dev:kill` exit-1 boot task) and hung/timeout detection are explicitly out of scope — they are non-deterministic and would weaken the "deterministic on loop" property. The literal incident is still covered: a runaway that runs `dev:kill` already trips Phase 2's cycle-bracket / unexpected-commit signals.

---

## Cross-feature Integration Notes

This bug builds directly on the just-shipped `lazy-cycle-containment` feature (C1/C2/C3), which is the prevention layer this bug repairs. Although not expressed as a `**Depends on:**` block (this is a bug doc, not a feature), the relevant prior-art contracts are:

- **`docs/features/lazy-cycle-containment/` (C1/C2/C3, Complete 2026-06-15):** the cycle-marker schema (`feature_id`/`nonce`/`kind`/`started_at`/`session_id`/`commit_tally`), the C2 hook deny-set, and the C3 `CYCLE_REFUSED_OPS` lockstep contract. Phase 1 supersedes the marker-armed *recursion/lifecycle* trip with `agent_id` targeting but **retains** the marker as the complementary carrier of `feature_id`/`commit_tally` for the 2nd-feature/commit-ceiling tripwires (per D4's final clause). Phase 2 extends the marker with run-identity + HEAD-snapshot fields for the detection signal — additive, must not break the C1/C3 `--test` fixtures.
- **`docs/specs/turn-routing-enforcement/` (hardening stage + deny-ledger):** the `lazy-deny-ledger.jsonl` shape, `pending_hardening()` / `oldest_unacked_deny()` / `build_hardening_emit_command()` / `ack_oldest_deny()` consumption chain, and the `--emit-prompt` probe's `route_overridden_by: "pending-hardening-debt"` withholding. Phase 2 reuses this ledger (a new `kind` discriminates process-friction entries) so the probe + `--run-end` gate consume it unchanged (resolving the SPEC's final Open Question in favor of reuse).

---

### Phase 1: `agent_id`-targeted containment (prevention — D4)

**Scope:** Replace the marker-armed *recursion/lifecycle* containment with `agent_id`-targeted containment in both the C2 PreToolUse hook (`lazy-cycle-containment.sh`) and the C3 script refusals (`lazy_core.refuse_if_cycle_active`). A subagent is exactly the context where the PreToolUse `agent_id` field is present, so the hook denies recursive `Agent`/`Task` dispatch, `/lazy-batch` invocation, `lazy-state.py`/`bug-state.py` routing+lifecycle flags, and `dev:kill`/`dev:restart` **whenever `agent_id` is present**, while allowing the orchestrator (`agent_id` absent). This removes the LLM-dependent `--cycle-begin` arming as the load-bearing trip and fixes the orchestrator-self-deny defect in one move. The cycle marker is **retained** as the complementary carrier of `feature_id`/`commit_tally` for the 2nd-feature and commit-ceiling tripwires (those stay marker-gated; only recursion/lifecycle moves to `agent_id`).

**`agent_id` confirmation (BLOCKING — SPEC Open Question, do FIRST):** Before re-targeting, confirm the exact PreToolUse payload field that marks a subagent against the installed Claude Code version. Author a `test_hooks.py` fixture that feeds a subagent-shaped payload (`agent_id` present) and asserts the hook denies a recursive `Agent` call, and a main-thread-shaped payload (`agent_id` absent) and asserts allow. If the installed version's field name differs from `agent_id`, this fixture is the single place the real name is pinned — author the hook to read the confirmed field. If the field genuinely cannot be confirmed from the installed version's hook payload (no subagent-marking field exists), write `NEEDS_INPUT.md` (product-class: the containment mechanism itself is undecided) rather than guessing.

**Deliverables:**
- [x] `test_hooks.py` fixture: subagent-shaped PreToolUse payload (`agent_id` present) + recursive `Agent` call → asserts `permissionDecision: deny`; main-thread-shaped payload (`agent_id` absent) + same call → asserts allow (no output). This fixture pins the confirmed field name. [VERIFY: `ls user/scripts/test_hooks.py`]
- [x] `user/hooks/lazy-cycle-containment.sh` — re-target the recursion/lifecycle deny logic on `agent_id` presence: deny `Agent`/`Task` dispatch, `_STATE_PY_RE` + `LOOP_FORMATION_FLAGS` routing, `/lazy-batch` invocation, and `LIFECYCLE_PATTERNS` (`dev:kill`/`dev:restart`) **when `payload.get("agent_id")` is present**; allow all of them when absent. Preserve the marker-gated 2nd-feature tripwire + commit-ceiling backstop (`feature_id`/`commit_tally` still read from the marker). Keep the fail-OPEN-via-empty-output contract and the bash fast-path (now: fast-allow when `agent_id` absent AND marker absent). [VERIFY: `grep -n 'tool_name in ("Agent", "Task")' user/hooks/lazy-cycle-containment.sh`]
- [x] `user/scripts/lazy_core.py` — `refuse_if_cycle_active()` gains an `agent_id`-aware path: refuse the `CYCLE_REFUSED_OPS` when the caller is a subagent (via the `LAZY_CYCLE_SUBAGENT` env var, or the marker as the fallback carrier — see the confirmed-mechanism note below). The orchestrator (main-thread) is never refused (`LAZY_ORCHESTRATOR` grants structural immunity even with a stale marker). Keep `CYCLE_REFUSED_OPS` and the hook deny-set in documented lockstep. [VERIFY: `grep -n "def refuse_if_cycle_active" user/scripts/lazy_core.py`]
- [x] Update the lockstep comment block above `CYCLE_REFUSED_OPS` and the hook header comment to describe the `agent_id` trip and the retained marker-gated tripwires, so the two stay auditable. [VERIFY: `grep -n "CYCLE_REFUSED_OPS MUST stay in lockstep" user/scripts/lazy_core.py`]
- [x] Tests: `test_hooks.py` covers deny-when-subagent / allow-when-main-thread for each op class (recursive Agent, `/lazy-batch`, routing flag, lifecycle pattern). `test_lazy_core.py` covers `refuse_if_cycle_active` allow-main-thread / refuse-subagent / orchestrator-immunity. No baseline change (refusal text unchanged).

**Implementation Notes (2026-06-16 — Phase 1 / plan part 1 complete):**
- **CONFIRMED `agent_id` field (resolves the BLOCKING Open Question — no NEEDS_INPUT):** the installed Claude Code **v2.1.170** hook-input base schema (zod object `xw`) is `{session_id, transcript_path, cwd, permission_mode?, agent_id?, agent_type?, effort, ...}`, with `agent_id` described verbatim as *"Subagent identifier. Present only when the hook fires from within a subagent (e.g., a tool called by an AgentTool worker). Absent for the main thread, even in [a `--agent` session]."* Extracted from the `claude.exe` binary string table. This is exactly D4's premise: `agent_id` present ⇒ subagent ⇒ deny recursion/lifecycle/routing; absent ⇒ main-thread orchestrator ⇒ allow.
- **C2 hook (`lazy-cycle-containment.sh`) trip is `agent_id`, arming-free.** The bash fast-path no longer exits on marker-absence (the `agent_id` trip must run with no marker); the inline Python fast-allows the common no-marker + no-`agent_id` case to preserve zero-overhead for interactive/main-thread events. Added `Task` to the recursive-dispatch deny and a `_LAZY_BATCH_RE` (`/lazy(-bug)?-batch(-cloud)?`) nested-batch deny. The 2nd-feature tripwire + commit-ceiling backstop stay marker-gated.
- **C3 (`refuse_if_cycle_active`) reachable-signal choice — env var, NOT `agent_id`.** A Python subprocess (lazy-state.py launched from a subagent's Bash) CANNOT read the PreToolUse `agent_id` (hook-input-only; not propagated to subprocess env — verified the `CLAUDE_CODE_AGENT`/`CLAUDE_CODE_FORK_SUBAGENT` env vars are `--agent`/config flags, not a general subagent marker). So C3 decides in priority order: (1) `LAZY_ORCHESTRATOR` truthy → never refuse (structural immunity to a stale marker — fixes Proven-Finding-#3); (2) `LAZY_CYCLE_SUBAGENT` truthy → refuse (explicit subagent signal); (3) else marker present → refuse (legacy backstop carrier, retained per D4's final clause). **Phase 2 reuses this same env-var mechanism** if its `--cycle-end` detector needs caller context.
- **Files modified:** `user/hooks/lazy-cycle-containment.sh`, `user/scripts/lazy_core.py`, `user/scripts/test_hooks.py` (+11 agent_id tests; 4 legacy marker-only deny tests updated to pass `agent_id`), `user/scripts/test_lazy_core.py` (+6 env-priority tests), `user/scripts/CLAUDE.md` (C3 description). Gates green: `test_hooks.py` 59/59, `test_lazy_core.py` 445→451 pass, both smoke baselines unchanged.
- **Pitfall for Phase 2/3:** the marker is RETAINED as the `feature_id`/`commit_tally` carrier (commit tripwires) — do NOT remove it. Phase 2 EXTENDS it additively with run-identity + HEAD-snapshot fields.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q` passes a fixture feeding a subagent-shaped payload (recursive `Agent`/`/lazy-batch`/`--run-end`) and asserting deny, plus a main-thread-shaped payload asserting allow — proving the orchestrator-self-deny defect is fixed and the runaway path is denied without any marker being armed.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh` — `agent_id`-targeted deny logic for recursion/lifecycle/routing.
- `user/scripts/lazy_core.py` — `refuse_if_cycle_active()` `agent_id`-awareness; lockstep comment.
- `user/scripts/test_hooks.py` — `agent_id` deny/allow fixtures.
- `user/scripts/test_lazy_core.py` — `refuse_if_cycle_active` subagent-vs-main-thread fixtures.
- `tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt` — only if refusal text changed (regenerate via the `_normalize_smoke_output` helper, never by hand).

**Testing Strategy:** Hermetic pytest fixtures drive the hook's inline Python with synthetic PreToolUse payloads (`agent_id` present/absent × op class) and assert the allow/deny JSON. `refuse_if_cycle_active` is unit-tested for both caller contexts. No live runtime needed — the hook and refusal are pure functions of their input payload/env.

**Integration Notes for Next Phase:**
- The cycle marker survives as the carrier of `feature_id`/`commit_tally` (2nd-feature + ceiling tripwires) — Phase 2 EXTENDS this same marker with run-identity + HEAD-snapshot fields; do not remove the marker.
- Whatever mechanism Phase 1 confirms for a Python subprocess to learn "am I a subagent?" (env var vs. marker fallback) is reused by Phase 2's `--cycle-end` detector if it needs caller context.
- Document the confirmed `agent_id` field name inline (in the hook + fixture) so Phase 3's prose can reference it accurately.

---

### Phase 2: Process-friction detector → deny ledger (detection — D1/D3)

**Scope:** Make `--cycle-begin` snapshot the run identity (the run marker's `started_at`, the stable run id) and the current HEAD SHA into the cycle marker, and make `--cycle-end` deterministically check the two D1 signals: **(a) cycle-bracket break** — the run identity present at `--cycle-begin` is absent or changed at `--cycle-end` (a dispatched cycle ran `--run-end` / overwrote the marker) — and **(b) unexpected commits** — HEAD at `--cycle-end` advanced beyond an expected one-cycle budget for the dispatched `sub_skill`. On either signal, append a **process-friction** entry to the existing `lazy-deny-ledger.jsonl` (a new `kind`/reason discriminates it) so `pending_hardening()` counts it, the `--emit-prompt` probe withholds the forward route (`route_overridden_by: pending-hardening-debt`), and `--run-end` refuses until the debt is acked — identical machinery to a guard deny. Reuses the deny ledger (resolves the SPEC's final Open Question: reuse, not a sibling file).

**Deliverables:**
- [x] `user/scripts/lazy-state.py` — `--cycle-begin` handler snapshots run identity (`read_run_marker().started_at`) and the current HEAD SHA into the cycle marker. Additive fields; absent run marker → snapshot null run-identity (degrade gracefully, no crash). Mirrored the same additive snapshot in `bug-state.py`'s `--cycle-begin`.
- [x] `user/scripts/lazy_core.py` — extended `write_cycle_marker()` signature/body to persist the new `run_started_at` + `begin_head_sha` fields (additive; default null so existing callers/fixtures are unbroken).
- [x] `user/scripts/lazy_core.py` — new `detect_cycle_bracket_friction(marker, current_run_started_at, current_head_sha, sub_skill, *, commits_since=None, now=None)` returning a friction descriptor (or None) implementing D1(a) cycle-bracket-break and D1(b) unexpected-commits. Conservative per-`sub_skill` commit budget (default 1; `execute-plan`/`retro-feature` 3); a torn bracket OR commits-beyond-budget trips it. Pure function, fully unit-testable.
- [x] `user/scripts/lazy_core.py` — new `append_friction_ledger_entry(reason_head, detail, now=None)` that appends to the SAME `lazy-deny-ledger.jsonl` with a `kind: "process-friction"` discriminator and `acked: false`, so `pending_hardening()`/`oldest_unacked_deny()`/`--run-end` gate consume it unchanged. (Plus a new I/O wiring helper `cycle_end_friction_check(repo_root)` + `head_sha_snapshot(repo_root)` so both state machines share identical `--cycle-end` resolution.)
- [x] `user/scripts/lazy-state.py` (+ `bug-state.py`) — `--cycle-end` handler calls `cycle_end_friction_check(...)` (→ `detect_cycle_bracket_friction`) BEFORE clearing the marker; on a non-None descriptor it appends the friction entry, then clears the marker as usual. `--cycle-end` stays idempotent and never crashes on a missing/partial marker (clean/degraded → no entry).
- [x] `user/scripts/lazy_core.py` — `build_hardening_emit_command()` handles a `process-friction` entry: binds `trigger_kind=process-friction` and surfaces `friction_reason`/`friction_detail` in the `--context` summary instead of `denied_prompt_summary`/`denial_reason`. `oldest_unacked_deny()` already returns any unacked entry (friction included) — unchanged.
- [x] Tests: `test_lazy_core.py` — `detect_cycle_bracket_friction` fixtures (clean bracket → None; torn bracket via changed identity AND via run-marker-now-absent → descriptor; over-budget commits → descriptor; within-budget → None; degraded null-snapshot → None, no crash); `append_friction_ledger_entry` round-trips into the deny ledger + co-exists with denies + bumps `pending_hardening()`; `build_hardening_emit_command` emits `trigger_kind=process-friction` (and validate-deny regression guard); `cycle_end_friction_check` no-marker/clean/torn fixtures. 16 net-new tests, all green. No baseline change (the additive marker fields do not appear in `--test` smoke output; both baselines byte-identical).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -q` proves a fixture that simulates `--cycle-begin` (snapshots run identity) → a torn cycle bracket (run identity cleared, mirroring the SPEC's runaway that ran `--run-end`) → `--cycle-end` appends a `kind: process-friction` ledger entry and `pending_hardening()` returns ≥1 — i.e. the runaway now self-announces as hardening debt.

**Prerequisites:** Phase 1 (the cycle marker is retained and any subagent-context mechanism is established).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `write_cycle_marker` additive fields; `detect_cycle_bracket_friction`; `append_friction_ledger_entry`; `build_hardening_emit_command` process-friction binding.
- `user/scripts/lazy-state.py` + `user/scripts/bug-state.py` — `--cycle-begin` snapshot; `--cycle-end` friction check.
- `user/scripts/test_lazy_core.py` — detector + ledger-entry + emit-command fixtures.
- `tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt` — regenerate for the additive marker fields + torn-bracket path.

**Testing Strategy:** All hermetic. The detector and ledger writer are pure/atomic functions tested directly. The `--cycle-begin` → tear → `--cycle-end` path is exercised in `--test` fixtures against temp state dirs (the existing cycle-marker suite ~`:14607` and deny-ledger suite ~`:8542` in `test_lazy_core.py` are the templates). No live runtime.

**Implementation Notes (2026-06-16 — Phase 2 / plan part 2 complete):**
- **`kind: process-friction` ledger reason strings (for Phase 3's prose):** the `reason_head` is one of exactly two values — **`cycle-bracket-break`** (D1(a): the run identity present at `--cycle-begin` is absent or changed at `--cycle-end` — a dispatched cycle ran `--run-end`, started a new run, or overwrote the run marker) and **`unexpected-commits`** (D1(b): HEAD advanced beyond the per-`sub_skill` commit budget). Phase 3 routes the `/harden-harness` dispatch on `trigger_kind=process-friction` (bound by `build_hardening_emit_command`) and may surface the `friction_reason`/`friction_detail` `--context` values.
- **Commit budget map chosen:** `_CYCLE_COMMIT_BUDGET_DEFAULT = 1`; overrides `{"execute-plan": 3, "retro-feature": 3}` (multi-batch plan execution legitimately commits once per batch). NOTE: the cycle marker does NOT carry the dispatched `sub_skill` name, so `cycle_end_friction_check` passes `sub_skill=None` → the DEFAULT budget (1) governs the live unexpected-commits signal. The bracket-break signal (the literal incident — a runaway that ran `--run-end`) is `sub_skill`-independent and fully covered regardless. If Phase 3 / a later phase wants per-`sub_skill` commit budgets to bite live, `--cycle-end` would need the dispatched sub_skill threaded in (additive). The detector ALREADY honors the map when a non-None `sub_skill` is passed (unit-tested), so this is a wiring-only follow-up, not a detector change. ⚖ policy: thread sub_skill into --cycle-end (live budget) → deferred as additive follow-up (not in Phase 2 scope; bracket-break covers the incident).
- **Degrade-to-off contract:** every signal is gated on a non-null begin snapshot. A `--cycle-begin` with no live run marker snapshots `run_started_at=None` → the bracket-break signal is OFF (never a false positive on an unmarked/manual cycle). A non-git tree snapshots `begin_head_sha=None` → the unexpected-commits signal is OFF. The `--cycle-end` clear ALWAYS proceeds (the friction append is fail-open, mirroring `append_deny_ledger_entry`).
- **Files modified:** `user/scripts/lazy_core.py` (`write_cycle_marker` additive fields; new `detect_cycle_bracket_friction`, `head_sha_snapshot`, `cycle_end_friction_check`, `append_friction_ledger_entry`; `build_hardening_emit_command` process-friction branch), `user/scripts/lazy-state.py` + `user/scripts/bug-state.py` (`--cycle-begin` snapshot + `--cycle-end` friction check — coupled-pair mirror), `user/scripts/test_lazy_core.py` (+16 tests), `user/scripts/CLAUDE.md` (`--cycle-begin`/`--cycle-end`/deny-ledger docs). Gates green: `test_lazy_core.py` 461/461, both `--test` smoke baselines byte-identical, `lazy_parity_audit.py` clean (no drift). End-to-end integration verified live: `--cycle-begin` → `--run-end` tear → `--cycle-end` appends `process-friction` → `pending_hardening()=1` → `--run-end` refuses (`run_marker_deleted: false`) → `build_hardening_emit_command` emits `trigger_kind=process-friction`.

**Integration Notes for Next Phase:**
- The ledger entry carries `kind: "process-friction"` and a `reason_head` summarizing the signal (bracket-break vs. over-budget-commits) — Phase 3's prose routes on exactly this `kind`/`trigger_kind`.
- Reusing `lazy-deny-ledger.jsonl` means the existing probe withholding + `--run-end` refusal already fire — Phase 3 only adds the trigger *prose*, not new routing machinery.

---

### Phase 3: Process-friction hardening trigger (routing — D2)

**Scope:** Wire the new process-friction ledger entry into the hardening-routing prose so the orchestrator deterministically routes a `/harden-harness` dispatch on it (D2: every occurrence is signal, fires even when the runaway's work was salvaged). Add a process-friction trigger class to `lazy-batch` §1d.1 and `harden-harness` Triggers, mirror into `lazy-bug-batch`, keep the coupled `lazy-batch-cloud` consistent, and add the `trigger_kind=process-friction` value + context bindings to the dispatch templates. No new routing machinery — the Phase-2 ledger entry already drives the probe's withholding; this phase is the prose that names the trigger and the dispatch context.

**Deliverables:**
- [ ] `user/skills/lazy-batch/SKILL.md` §1d.1 — add a fourth trigger class "process-friction" (a `kind: process-friction` deny-ledger entry from a torn cycle bracket / unexpected commits), routing the same hardening dispatch as the existing three. [VERIFY: `grep -rn "validate-deny" user/skills/lazy-batch/SKILL.md`]
- [ ] `user/skills/harden-harness/SKILL.md` — add the process-friction trigger to Triggers 1–4 (now 1–5) and to the Step-2 root-cause taxonomy guidance (this class is `missing-contract` + `hook-defect` per Proven Finding #1). [VERIFY: `grep -n "Triggers" user/skills/harden-harness/SKILL.md`]
- [ ] `user/skills/lazy-bug-batch/SKILL.md` — mirror the §1d.1 process-friction trigger (bug pipeline runs the same `bug-state.py` ledger). [VERIFY: `ls user/skills/lazy-bug-batch/SKILL.md`]
- [ ] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — keep consistent with `lazy-batch` per the coupled-pair rule; the process-friction trigger is shared (not a cloud divergence). Update its "Differences from /lazy-batch" block only if a genuine divergence arises (none expected). [VERIFY: `ls repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`]
- [ ] `user/skills/_components/lazy-batch-prompts/dispatch-hardening.md` + `user/skills/_components/hardening-dispatch.md` — add `trigger_kind=process-friction` as a valid value and document the friction-signal `--context` bindings (the cycle-bracket-break / unexpected-commit summary). [VERIFY: `ls user/skills/_components/hardening-dispatch.md`]
- [ ] Update `user/scripts/CLAUDE.md` and/or `CLAUDE.md` lazy-pipeline docs if the trigger surface description references "routing-layer only" (now process-friction is also a trigger). [VERIFY: `grep -rn "routing-layer" user/scripts/CLAUDE.md CLAUDE.md`]

**Minimum Verifiable Behavior:** `python user/scripts/project-skills.py` re-expands all four `/lazy*` + `harden-harness` skills with the new trigger prose and no broken `!cat` injections; `python user/scripts/lint-skills.py --check-projected --check-capabilities` passes clean; `python user/scripts/lazy_parity_audit.py --report` shows no unexplained drift between the coupled `lazy-batch` ↔ `lazy-batch-cloud` pair (the process-friction trigger is mirrored, not a registered divergence).

**Prerequisites:** Phase 2 (the `kind: process-friction` ledger entry must exist for the prose to route on).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `user/skills/harden-harness/SKILL.md` — process-friction trigger prose.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — coupled-pair consistency.
- `user/skills/_components/lazy-batch-prompts/dispatch-hardening.md`, `user/skills/_components/hardening-dispatch.md` — `trigger_kind=process-friction` + context bindings.
- `user/scripts/CLAUDE.md`, `CLAUDE.md` — trigger-surface doc update (if it asserts routing-layer-only).

**Testing Strategy:** Docs-layer validation: `project-skills.py` (component expansion), `lint-skills.py --check-projected --check-capabilities` (broken injections / embedded patterns / capabilities), and `lazy_parity_audit.py --report` (coupled-pair drift). These are the repo's authoritative gates for skill/prose changes per `quality-gates.md`.

**Integration Notes for Next Phase:**
- This is the terminal phase. After it lands, the full loop is closed: a runaway → Phase 2 ledger entry → Phase 1-style prevention would also have denied it → Phase 3 prose routes `/harden-harness` on the entry.

---

## Completion (gate-owned)

The top-level SPEC.md/PHASES.md `**Status:**` flip to Fixed, the `FIXED.md` receipt, and any archive move are owned EXCLUSIVELY by the orchestrator's `__mark_fixed__` gate (fired after the validation tail). They are NOT authored as deliverable checkboxes here. When the last phase's work lands, the implementer sets the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and lets the state machine route to the validation tail.
