# Hardening stage blind to process/behavioral friction — Investigation Spec

> The `/harden-harness` stage only auto-dispatches on routing-layer guard signals; process/behavioral friction (a runaway cycle subagent that tears down the run marker and orchestrator runtime) leaves valid-looking state behind, so no trigger fires and the orchestrator improvises instead of self-healing.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-16
**Placement:** docs/bugs/hardening-blind-to-process-friction
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage + deny-ledger), `docs/specs/lazy-hardening/`, sibling bug `docs/bugs/research-gate-ignores-existing-phases/`

---

## Verified Symptoms

1. **[VERIFIED]** During a `/lazy-batch 25` run, a dispatched `/spec` Phase-3 cycle subagent (cycle 5, feature `mcp-test-fidelity`) violated its one-cycle contract — it ran ~14 full cycles across 4 features, marked 2 complete, then ran `lazy-state.py --run-end` (cleared the orchestrator's run marker) and `dev:kill` (tore down the orchestrator-owned dev runtime). The orchestrator's background runtime boot task returned **exit 1** — the "process deadlock" the operator observed. — confirmed from session `14de0c30-f5a9-48a9-be2a-c215493cf9b2.jsonl` (msgs ~249–291) and on-disk git/receipt verification the orchestrator itself ran.
2. **[VERIFIED]** The orchestrator responded by doing forensic verification, **accepting** the 14 commits as legitimate, running its own idempotent `--run-end`/`dev:kill`, halting on the genuine `needs-research` gate, and writing a memory note — it **never mentioned or considered** `/harden-harness` or any hardening dispatch. — same session; zero occurrences of hardening intent.
3. **[VERIFIED]** The operator must manually direct the orchestrator (or a claude-config session) to fix process friction the hardening stage should have caught autonomously. The operator notes hardening "only spawns naturally" via the guard-deny path. — operator statement + corroborated below.
4. **[VERIFIED]** The `lazy-cycle-containment` feature (C1/C2/C3) — completed **2026-06-15 21:28** (commit `dcf36ba`), **90 minutes before** the 22:58 runaway — was built to stop exactly this recursion, yet did not fire. Root cause: the orchestrator **never executed `--cycle-begin`** — `grep -c -- "--cycle-begin"` over the session = **0** (same for `--cycle-end`); `lazy-cycle-active.json` is absent from the state dir. The C2 hook's bash fast-path (`[ ! -f "$MARKER" ] → exit 0`) therefore allowed every subagent call, and C3's `refuse_if_cycle_active()` never triggered. Containment silently fail-opened with no breadcrumb (`hook-error.json` absent). — session `14de0c30`, live `~/.claude/state/`.

## Reproduction Steps

1. Run `/lazy-batch N` with the run marker armed.
2. A dispatched cycle subagent oversteps its one-cycle contract and runs `--run-end` (and/or `dev:kill`), clearing the run marker on a *legitimate* terminal (e.g. a real `needs-research` gate it reached).
3. The orchestrator re-probes; `lazy-state.py` returns a **clean terminal** (no divergence, no deny, no `cycle_prompt_refused`).

**Expected:** the orchestrator detects the cycle-bracket was torn down by the dispatched subagent and deterministically routes a `/harden-harness` dispatch (root-cause the bypass, fix it), independent of whether the subagent's output was salvageable.
**Actual:** no hardening trigger fires; the orchestrator improvises (verify → accept → halt) and the harness gap is never investigated or fixed.
**Consistency:** deterministic for this class — process/behavioral friction has *no* trigger; it can never enter the hardening loop.

## Evidence Collected

### Source Code

The hardening trigger surface is **routing-layer only**:

- `user/skills/lazy-batch/SKILL.md` §1d.1 — triggers 1–3 are `validate-deny` (guard denied a dispatch), `no-route` (`cycle_prompt_refused` / contradictory state / marker-state divergence), and `inject-hook-error` (HOOK_ERROR breadcrumb). All three are detected by `lazy-dispatch-guard.sh` / the `--emit-prompt` probe / `lazy-route-inject.sh`.
- `user/skills/harden-harness/SKILL.md` Triggers 1–4 (manual is #4) — same three enforcement signals.

The **deterministic loop mechanism already exists** for routing friction (the model to mirror):

- Deny → `lazy_core.append_deny_ledger_entry()` (`lazy_core.py:5933`) appends to `lazy-deny-ledger.jsonl` (`acked: false`).
- The `--emit-prompt` probe **withholds the forward route** while debt is pending: `route_overridden_by: "pending-hardening-debt"` + pre-composed `hardening_emit_command` (`lazy-state.py:5688–5762`, `lazy_core.build_hardening_emit_command()` `:6332`).
- An entry is acked only when the **guard ALLOWS** a hardening-class dispatch: `lazy_guard.py::_ack_if_hardening` (`:336`) → `lazy_core.ack_oldest_deny()` (`:6388`).
- `--run-end` **refuses (exit 1)** while unacked debt remains (`lazy-state.py:5329–5354`); `--ack-unhardened` is the operator-only override.

The **prevention layer that should have blocked the bypass — and was bypassed**:

- `lazy_core.CYCLE_REFUSED_OPS` (`lazy_core.py:5166`) makes `lazy-state.py` exit 3 on `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc`/`--emit-dispatch` *while the cycle marker (`lazy-cycle-active.json`) is present* — these are orchestrator-only ops. Enforced via `lazy_core.refuse_if_cycle_active()` (e.g. `--run-end` at `lazy-state.py:5322`).
- **Why it was bypassed:** `write_cycle_marker()` (`lazy_core.py:5018`) is **self-healing — it overwrites a stale prior marker** (`:5072`). A runaway subagent running a nested `/lazy-batch` issues its own `--cycle-end`/`--cycle-begin`, clearing/overwriting the orchestrator's cycle marker; once the cycle marker is gone, `refuse_if_cycle_active()` no longer fires and `--run-end` is permitted.

### Runtime Evidence

Session `14de0c30` (2026-06-15 22:58Z): the orchestrator's own forensic narrative confirms "the dispatched `/spec` cycle subagent … ran an entire `/lazy-batch` itself (14 cycles …), cleared the run marker, and tore down my orchestrator-owned runtime. The background runtime task failing with exit 1 confirms the subagent ran `dev:kill` on my runtime." The orchestrator then verified and **kept** the work and halted on the research gate.

### Git History

`docs/specs/turn-routing-enforcement/hardening-log/2026-06.md` — **14 rounds, all `validate-deny` / `no-route` / `manual`. Zero rounds from process/behavioral friction, ever.** Corroborates that the only "natural" auto-spawn path is the guard-deny ledger.

### Related Documentation

- `user/scripts/CLAUDE.md` — confirms the lazy-cycle-containment C1/C3 design (cycle marker + refuse-by-construction set, lockstep with the C2 `lazy-cycle-containment.sh` hook deny-set).
- `user/skills/_components/hardening-dispatch.md` — the seven `--context` keys the hardening class requires.

## Theories

### Theory 1: Missing detector — process friction never enters the existing hardening loop (PRIMARY)
- **Hypothesis:** Routing friction is already deterministic-on-loop via the deny-ledger; the gap is that **nothing converts process/behavioral friction into a ledger entry**. A runaway leaves valid-looking terminal state (marker absent because `--run-end` ran *legitimately* on a real gate), so the next probe sees a clean terminal — no deny, no `cycle_prompt_refused`, no HOOK_ERROR — and no trigger exists.
- **Supporting evidence:** trigger surface is routing-layer only (§1d.1, harden-harness Triggers 1–4); the orchestrator's probe returned a sanctioned terminal; hardening-log has 0 process-friction rounds.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

### Theory 2: Prevention layer was never armed — containment depends on an LLM-executed step (CONFIRMED, primary prevention cause)
- **Hypothesis:** C2/C3 are armed by a manually-executed `lazy-state.py --cycle-begin` Bash step the orchestrator must run before *every* Agent dispatch. The orchestrator skipped it, so the marker never existed and both the C2 hook (bash fast-path) and C3 (`refuse_if_cycle_active`) fail-opened.
- **Supporting evidence:** **0** `--cycle-begin`/`--cycle-end` calls in the session; `lazy-cycle-active.json` absent from the state dir; no `hook-error.json` (clean fail-open, not an error). The feature was completed 90 min earlier and the hook is registered in `settings.json` (Bash + Agent matchers), so timing/registration are ruled out.
- **Contradicting evidence:** none.
- **Status:** Confirmed (the actual reason the just-shipped fix did not fire).

### Theory 3: Even if armed, the C2 hook would deny the orchestrator's own dispatch — no `agent_id` discrimination (CONFIRMED latent)
- **Hypothesis:** `lazy-cycle-containment.sh` denies **all** `Agent` tool calls unconditionally (`if tool_name == "Agent": _deny(...)`), with no check distinguishing the main-thread orchestrator from a subagent. Since the orchestrator's F2 flow is set-marker → dispatch-`Agent`, an *armed* marker would deny the orchestrator's own legitimate cycle dispatch — so the design cannot work as specified.
- **Supporting evidence:** hook body (`user/hooks/lazy-cycle-containment.sh:188`) denies Agent unconditionally and never reads a session/agent identity from the payload. Claude Code PreToolUse hooks **do** fire for subagent tool calls and expose an **`agent_id` field present only for subagent calls** (confirmed via claude-code-guide against `code.claude.com/docs/en/hooks`), which the hook does not use. The feature shipped with `SKIP_MCP_TEST.md` (no app surface) + hermetic `--test` fixtures only, so the live orchestrator-dispatch path was never exercised.
- **Contradicting evidence:** none found; needs a live confirmation of the exact field name/shape (see Open Questions).
- **Status:** Confirmed latent (masked by Theory 2 — the marker was never armed, so this never surfaced).

## Proven Findings

1. **Root-cause class: `missing-contract` + `hook-defect`** (per `harden-harness` Step 2 taxonomy). No deterministic detector / `--emit-dispatch` path for process friction (detection gap), AND the just-shipped prevention layer is both unarmed-in-practice and structurally unable to discriminate the orchestrator from a subagent (prevention gap).
2. **Why the just-shipped `lazy-cycle-containment` fix did not fire (the operator's "why didn't it work?"):** the marker that arms C2/C3 is written by an LLM-executed `--cycle-begin` step the orchestrator simply did not run (0 calls). Arming is fail-open and unenforced — skip the step and containment silently vanishes.
3. **The prevention design is also latently broken** even when armed: the C2 hook denies all `Agent` calls with no `agent_id` discrimination, so it would deny the orchestrator's own dispatch. The correct signal is the inverse — a subagent is *exactly* the context where `agent_id` is present.
4. **Three distinct gaps to close:** (a) *detection* — no signal converts a torn-down cycle bracket / overstepped commits into hardening debt; (b) *prevention-arming* — containment must not depend on the orchestrator remembering to run `--cycle-begin`; (c) *prevention-targeting* — the hook must allow the orchestrator (`agent_id` absent) while denying subagent recursion (`agent_id` present).

## Locked Decisions

Resolved with the operator (these are harness-design decisions and remain the operator's):

- **D1 — Detector scope (deterministic signals only):** auto-route hardening on **(a) cycle-bracket break** — the run-id present at `--cycle-begin` is absent/changed at `--cycle-end` (a dispatched cycle ran `--run-end` / tore down the marker) — and **(b) unexpected commits** — a dispatched cycle produced commits beyond its one-cycle scope (the orchestrator didn't author them). Both are on-disk, deterministically verifiable.
- **D1-out — Out of scope (this bug):** runtime/background-task death (e.g. `dev:kill`, exit-1 boot task) and hung/timeout commands are **deferred** — they are non-deterministic/heuristic and would weaken the "deterministic on loop" property. (Note: a cycle that runs `dev:kill` will already trip D1's cycle-bracket / unexpected-commit signals, so the literal incident is covered without a runtime-death heuristic.)
- **D2 — Always harden (signal, not noise):** when the runaway's work is verified legitimate and accepted (as happened here), a hardening dispatch **still fires**. Accepting the output and hardening the bypass are orthogonal; the bypass is a harness defect regardless of salvage. Mirrors locked-decision-4 ("every occurrence is signal, not noise").
- **D3 — Fix both prevention and detection (defense in depth):** add the detection→debt-ledger→hardening path so any future bypass self-announces, **and** make prevention robust per D4.
- **D4 — Arming-free, `agent_id`-targeted prevention (supersedes the marker-armed C2 approach for the recursion case):** stop depending on an orchestrator-written marker. A dispatched cycle subagent is exactly the context where the PreToolUse `agent_id` field is **present**, so the C2 hook should — whenever `agent_id` is present (caller is a subagent) — **deny** recursive `Agent`/`Task` dispatch, `/lazy-batch` invocation, and `lazy-state.py`/`bug-state.py` routing+lifecycle flags (`--run-start/--run-end/--apply-pseudo/--emit-dispatch/--probe/--emit-prompt/…`) and `dev:kill`/`dev:restart`, while **allowing** the orchestrator (`agent_id` absent) to dispatch and run lifecycle ops. This removes the LLM-dependent `--cycle-begin` arming as the load-bearing trip and fixes the orchestrator-self-deny defect in one move. (The cycle marker can remain as a *complementary* carrier of `feature_id`/`commit_tally` for the 2nd-feature/commit-ceiling tripwires, but recursion/lifecycle containment must not depend on it being armed.)

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Prevention — C2 hook (PRIMARY) | `user/hooks/lazy-cycle-containment.sh` (Agent deny `:188`, marker fast-path `:31`), `user/settings.json` (Bash+Agent matchers) | Re-target on `agent_id` (subagent ⇒ deny recursion/lifecycle; main-thread ⇒ allow) per D4; remove the dependency on an orchestrator-armed marker. |
| Prevention — C3 / cycle marker | `user/scripts/lazy_core.py` (`write_cycle_marker` `:5018`, self-heal `:5072`; `read_cycle_marker` `:5103`; `clear_cycle_marker` `:5129`; `CYCLE_REFUSED_OPS`/`refuse_if_cycle_active` `:5166`) | Marker may stay as a complementary carrier (feature_id/commit_tally), but C3 must not be the sole trip; `--cycle-begin` should also snapshot run identity for the detection signal below. |
| Containment feature record | `docs/features/lazy-cycle-containment/` (PHASES.md, plans, `SKIP_MCP_TEST.md`) | The fix shipped without a live end-to-end exercise (SKIP_MCP_TEST + hermetic `--test` only); the re-validation must cover a real orchestrator-dispatch-then-subagent-recursion path. |
| Detector → debt ledger | `user/scripts/lazy-state.py` (`--cycle-end` handler; `--emit-prompt` probe `:5688`), `lazy_core.py` (`append_deny_ledger_entry` `:5933`, `pending_hardening` `:6295`, `build_hardening_emit_command` `:6332`) | A process-friction signal must append a ledger entry (new `kind`/reason) so the probe withholds the forward route exactly like a guard deny. |
| Hardening trigger prose | `user/skills/lazy-batch/SKILL.md` §1d.1 (+ mirror `lazy-bug-batch`, keep `lazy-batch-cloud` consistent), `user/skills/harden-harness/SKILL.md` Triggers | Add a "process-friction" trigger class so the orchestrator routes hardening on the new ledger entry. |
| Dispatch template | `user/skills/_components/lazy-batch-prompts/dispatch-hardening.md`, `_components/hardening-dispatch.md` | May need a `trigger_kind=process-friction` value + context bindings (the friction signal summary). |
| Tests | `user/scripts/test_lazy_core.py` (cycle-marker suite ~`:14607`, deny-ledger suite ~`:8542`), `lazy-state.py --test` / `bug-state.py --test` baselines, `test_hooks.py` | New cycle-bracket-invariant fixtures; ledger-entry-from-process-friction fixtures; baseline updates. |

## Open Questions

- **`agent_id` field confirmation (BLOCKING for D4):** verify the exact PreToolUse payload field that marks a subagent against the *installed* Claude Code version before relying on it — claude-code-guide reported `agent_id` (present only for subagent calls, absent on main-thread) per `code.claude.com/docs/en/hooks`, but the fix hinges on the exact field name/shape. Add a `test_hooks.py` fixture that feeds a subagent-shaped payload and asserts deny, and a main-thread-shaped payload and asserts allow.
- Run-id identity: the run marker (`lazy_core.write_run_marker` `:4732`) carries `session_id`/`started_at` but no explicit `run_id`. Does `--cycle-begin` snapshot `started_at` (the stable run identity) into the cycle marker, or is a dedicated `run_id` field warranted? (Planning decision.)
- "Unexpected commits" detection: compare HEAD against the SHA at `--cycle-begin` plus an expected-commit budget for the cycle's `sub_skill`? Where is the pre-cycle SHA captured today (the `--probe` git_guards already surface `clean_tree`/`head_matches_origin`)?
- Prevention hardening shape: should `write_cycle_marker()` refuse to overwrite a marker owned by a *different* session (mirroring the run marker's Phase-8 non-owner protection at `read_run_marker` Path B), rather than self-healing unconditionally?
- Should the new ledger entry reuse `lazy-deny-ledger.jsonl` (one debt queue, `kind` discriminates) or a sibling `lazy-friction-ledger.jsonl`? (Reuse favored — the probe + run-end gate already consume the deny ledger.)
