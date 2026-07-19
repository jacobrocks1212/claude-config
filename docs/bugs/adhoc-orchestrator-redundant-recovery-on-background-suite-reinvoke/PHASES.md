# Implementation Phases — Orchestrator Redundant-Recovery on Background-Suite Re-invoke

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — the entire deliverable is claude-config harness surface (orchestrator skill prose, a stdlib-Python `lazy_core` discriminator + its two state-script CLI flags, one new PreToolUse shell hook + its settings registration, and unit tests). No app integration, audio, UI, or MCP-reachable surface exists in this repo — structurally outside MCP reach per `docs/features/mcp-testing/SPEC.md`'s untestable classes (build/tooling/docs-only). Verification is the repo's own deterministic gate battery (pytest + lint/projection + doc-drift-lint + parity audit).

## Fix summary (Locked Decision 1 — "Both")

Two coupled defects, both `traced` in the SPEC; the operator locked **both** fixes (not either alone):

- **Gap 2 (load-bearing) — orchestrator pause-vs-terminal discriminator.** `lazy-batch`/`lazy-bug-batch` Step 1e/4a runs `--verify-ledger` after every `/execute-plan` cycle and, on a `clean_tree`/`head_matches_origin` failure, unconditionally emits `--emit-dispatch recovery`. It has NO check for whether the just-returned `/execute-plan` cycle is *paused and about to be re-invoked* (a backgrounded suite) versus genuinely terminal. Fix: consult the authoritative signal `dispatched-agent-liveness.md` already prescribes — the `/execute-plan` run marker + plan `status:` — BEFORE the recovery emit, and suppress recovery while the returned cycle is paused.
- **Gap 1 — mechanical foreground enforcement.** The "never background a long gate inside a cycle subagent" mandate is prose-only (`cycle-base-prompt.md` turn-end §1, `turn-end-gate.md`), and is violated because backgrounding empirically "works" (the harness re-invokes the agent). Fix: a `user/hooks/` PreToolUse guard that DENIES a `run_in_background` long-gate/test-suite launch from inside an armed cycle subagent, so the ambiguous "holding, will re-invoke" return is never produced in the first place.

The two gaps compose: Gap 1 produces the ambiguous return; Gap 2 mishandles it into an active dual-writer collision. Shipping only one leaves the failure reachable (Gap-2-only: a subagent can still stall on a genuinely-unreliable re-invocation; Gap-1-only: any other paused-cycle return still races recovery). Both are required.

## Validated Assumptions

- **Harness re-invocation of dispatched cycle subagents is UNCERTAIN — and the fix is deliberately correct under both truths (SPEC Open Question 2).** `turn-end-gate.md` L13–18 documents that dispatched agents do NOT get background-completion re-invocation; `ADHOC_BRIEF.md` observed a dispatched `/execute-plan` cycle BEING re-invoked twice in one run. This is a **runtime-coupled** claim (SPEC "Runtime-coupled note") that cannot be cheaply validated in a harness-authoring context (it requires reproducing a full `/lazy-batch` run with an over-cap aggregate suite). **No runtime spike is scheduled because the two-gap design removes the dependency on the answer**, which is the correct handling per the runtime-assumption gate (a load-bearing runtime assumption is neutralized, not planned-over):
  - If re-invocation IS reliable for cycle subagents → Gap 2's discriminator correctly WAITS for it instead of racing recovery; Gap 1 prevents the ambiguous return up front.
  - If re-invocation is UNreliable → Gap 1's mechanical prevention is even MORE important (a backgrounded suite would otherwise genuinely stall), and Gap 2 falls through to `dispatched-agent-liveness.md`'s existing **genuine-wedge** branch (marker present + NO live descendant after a bounded wait ⇒ recovery IS appropriate). Recovery is suppressed only during a true pause, never during a genuine wedge.
  - **Therefore the discriminator must reuse `dispatched-agent-liveness.md`'s FULL decision procedure (pause vs. genuine-wedge), not a bare "marker present ⇒ never recover" check.** This is baked into Phase 1's deliverables.
- **The turn-end-gate.md L13–18 vs. observed-behavior contradiction is documented, not silently resolved.** Phase 3 records it as a known undocumented/inconsistent harness behavior and points the (now-mechanically-enforced) mandate at the new guard rather than at the contradicted "your process tree is torn down" deterrent.

## Touchpoint Audit (verified: inline — dispatch available; small, well-traced set; cycle-subagent context)

| Planned file | Exists? | Real symbols / anchors (verified) | Action | Reuse / refactor directive |
|--------------|---------|-----------------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | shared helpers imported by both state scripts (`_atomic_write`, `read_run_marker`, marker/statedir helpers) | create (net-new fn) | Add `execute_plan_liveness(repo_root, plan_path)` returning `{marker_present, plan_status, verdict: paused\|terminal\|wedge-candidate}`. REUSE the existing `~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json` recipe (see `execute-plan/SKILL.md:108/190`) — do NOT re-derive the hash inline; read the marker NON-destructively (raw read, never `read_run_marker` which is delete-on-read). Encode `dispatched-agent-liveness.md`'s decision procedure (§43–62) verbatim: marker absent OR plan `Complete` ⇒ `terminal`; marker present + plan not `Complete` ⇒ `paused`; the `wedge-candidate` distinction (no live descendant) is orchestrator-observed, so the helper returns `paused` and the orchestrator prose owns the bounded-wait wedge escalation. |
| `user/scripts/lazy-state.py` | yes | argparse roster + `--verify-ledger` handler | refactor | Add a `--execute-plan-liveness --plan <p> --repo-root <cwd>` CLI flag shelling `lazy_core.execute_plan_liveness`, printing the JSON verdict; always exit 0 (a probe never gates). Register on the CLI-surface roster (`--dump-cli-surface`). |
| `user/scripts/bug-state.py` | yes | mirror roster (parity-audited) | refactor | Mirror the identical `--execute-plan-liveness` flag (the execute-plan marker is pipeline-agnostic — same helper, same output). Keep parity green. |
| `user/scripts/lazy-parity-manifest.json` | yes | `pairs` / `mechanic_sets` | refactor | Register the new shared flag as a parity-audited mechanic so `lazy_parity_audit.py --repo-root .` stays exit 0. |
| `user/skills/lazy-batch/SKILL.md` | yes | Step 1e §4a recovery region (verified L982–1024): `--verify-ledger` → on `clean_tree`/`head_matches_origin` failure → `--emit-dispatch recovery` | refactor | Insert the pause-vs-terminal check BEFORE the recovery emit, scoped to a just-returned `/execute-plan` cycle. Do NOT hand-compose a new dispatch — only GATE the existing sanctioned `--emit-dispatch recovery`. |
| `user/skills/lazy-bug-batch/SKILL.md` | yes | guardrail-D reference block (verified L756–789), inherits Step 1e by reference, restated with `bug-state.py` | refactor | Mirror the discriminator gate in the bug-pipeline guardrail-D block (`bug-state.py --execute-plan-liveness`). Coupled pair — parity-audited. |
| `user/hooks/cycle-subagent-bg-gate-guard.sh` | **NO (net-new)** | — | create | New PreToolUse (Bash\|PowerShell) guard. SOURCE `hook-prelude.sh` + import `hook_lib` (same shape as `long-build-ownership-guard.sh` / `lazy-cycle-containment.sh`). Deny-via-JSON `permissionDecision: deny`, fail-OPEN (no-python breadcrumb + catch-all `hook-error.json`/`hook-events.jsonl`). |
| `user/hooks/hook-prelude.sh` + `hook_lib` (in `user/scripts/`) | yes | `HOOK_PYTHON`/`HOOK_SCRIPTS_DIR`/`HOOK_NAME`, allow/deny emitters, `_CMD_START`/`ENV_PREFIX` anchors, `COMMAND_TOOL_NAMES` | reuse | REUSE the shared prelude + hook_lib — do NOT re-implement python resolution, breadcrumbs, or the command-segment anchor. |
| `user/settings.json` | yes | `hooks.PreToolUse` — the `Bash\|PowerShell` chain (`lazy-cycle-containment` → `long-build-ownership-guard` → `build-queue-enforce`) | refactor | Register the new guard in the `Bash\|PowerShell` chain. |
| `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` | yes | turn-end §1 (verified L648–657): "Never background a long gate…process tree is torn down" | refactor | Point the mandate at the new mechanical guard (backstop now exists); keep the foreground-await instruction. |
| `user/skills/_components/turn-end-gate.md` | yes | L13–18 (re-invocation deterrent) + L23–30 (over-cap prevention) | refactor | Add the mechanical-enforcement reference; annotate the L13–18 contradiction per Validated Assumptions. |
| `CLAUDE.md` (root) | yes | Hooks table | refactor | Add the new hook's row (trigger, purpose, fail-open note). doc-drift-lint cross-checks the table ↔ `settings.json` — keep them consistent. |
| `user/skills/_components/dispatched-agent-liveness.md` | yes | §29–62 authoritative-signal + decision procedure | reuse (no behavior change) | REUSE target — the discriminator encodes this component's recipe. Optionally add a one-line cross-ref noting the discriminator now wires it into the awaited-`Agent`-result path (was notification-path only). |
| `user/skills/execute-plan/SKILL.md` | yes | L108 (marker write) / L190 (marker remove) | no edit (reference) | The marker recipe the helper reads — read-only anchor, unchanged. |
| `user/scripts/test_hooks.py` | yes | `test_wedge_*` / existing hook-payload harness | refactor | Add Gap-1 guard tests (synthetic PreToolUse payloads — no live subagent). |
| `user/scripts/test_execute_plan_liveness.py` | **NO (net-new)** | — | create | New pytest module for the discriminator helper (real marker files in a tmp state dir). |

**Contradiction classification (severity ladder):** none premise-grade. Every finding is anchor-grade and already reflects reality (the SPEC's serving-path traces were verified against the live line numbers). No `NEEDS_INPUT.md` fork — the fix mechanism is settled by Locked Decision 1; the only judgment calls (discriminator lives in a script vs. prose; command-classification scope of the Gap-1 guard) are scope-class, not product-class (see per-phase notes).

## Cross-feature Integration Notes

No hard deps on completed upstream features (`**Depends on:**` is not declared in the SPEC; this is a self-contained harness fix). Section retained only to note the **reuse contract**: Gap 2 REUSES `dispatched-agent-liveness.md`'s authoritative-signal recipe rather than reinventing a liveness mechanism, and Gap 1 REUSES the shared `hook-prelude.sh`/`hook_lib` guard scaffold. Neither upstream is modified behaviorally (read-only reuse).

---

### Phase 1: Gap 2 — script-owned pause-vs-terminal discriminator + orchestrator wiring (LOAD-BEARING)

**Scope:** Add a deterministic `lazy_core.execute_plan_liveness` helper that reads the `/execute-plan` run marker + plan `status:` and returns a `paused | terminal | wedge-candidate` verdict (per `dispatched-agent-liveness.md`), expose it as an `--execute-plan-liveness` probe on both state scripts (parity-audited), and wire `lazy-batch`/`lazy-bug-batch` Step 1e/4a to consult it BEFORE emitting `--emit-dispatch recovery` after an `/execute-plan` cycle — suppressing recovery while the returned cycle is a live pause. This is the load-bearing half: it directly closes the traced serving path (`lazy-batch/SKILL.md:1006/1012` recovery dispatch had no upstream pause check).

⚖ policy: script-owned discriminator vs. prose-only orchestrator check → script-owned (deterministic, both pipelines). Scope-class (identical product behavior — recovery suppressed during a pause); the harness mission mandates deterministic script-owned state over LLM-inferred, so the discriminator is a `lazy_core` helper the orchestrator shells, not a prose "look at the marker yourself" instruction.

**Deliverables:**
- [ ] `lazy_core.execute_plan_liveness(repo_root, plan_path)` — reads `~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json` NON-destructively (raw read, never `read_run_marker`) + the plan frontmatter `status:`; returns `{"marker_present": bool, "plan_status": str|null, "verdict": "paused"|"terminal"|"wedge-candidate"}`. Decision rule (encodes `dispatched-agent-liveness.md` §43–62): marker absent OR plan `status: Complete` ⇒ `terminal`; marker present + plan not `Complete` ⇒ `paused`. Fail-safe: any read error ⇒ `terminal` (never suppress recovery on an unreadable signal — bias to the safe/legacy behavior).
- [ ] `lazy-state.py --execute-plan-liveness --plan <plan> --repo-root <cwd>` CLI flag — shells the helper, prints the JSON verdict, always exits 0; registered on the `--dump-cli-surface` roster.
- [ ] `bug-state.py --execute-plan-liveness …` — identical mirror (marker is pipeline-agnostic); parity-audited.
- [ ] Register the new shared flag in `user/scripts/lazy-parity-manifest.json` so `lazy_parity_audit.py --repo-root .` stays exit 0.
- [ ] `lazy-batch/SKILL.md` Step 1e/4a: BEFORE the `--emit-dispatch recovery` on a `clean_tree`/`head_matches_origin` failure FOLLOWING an `/execute-plan` cycle, call `--execute-plan-liveness --plan {plan_file}`. On `verdict == "paused"` → do NOT dispatch recovery; record a T6 line (`⚠ execute-plan cycle paused (backgrounded suite) — recovery suppressed, awaiting harness re-invocation`) and fall through to the next state probe. Only `terminal` (or the orchestrator-owned bounded-wait wedge escalation) proceeds to the existing recovery emit. Non-`/execute-plan` cycles (`/mcp-test`) are unaffected — the gate is scoped to execute-plan returns.
- [ ] `lazy-bug-batch/SKILL.md`: mirror the same discriminator gate in the guardrail-D reference block (`bug-state.py --execute-plan-liveness`), keeping the coupled pair in sync.
- [ ] Tests (`test_execute_plan_liveness.py`): marker present + `status: Ready`/`In-progress` ⇒ `paused`; marker present + `Complete` ⇒ `terminal`; marker absent ⇒ `terminal`; unreadable/missing plan ⇒ `terminal` (fail-safe). Drive the REAL helper against REAL marker files in a tmp state dir (not a mock) — this is the orchestrator↔script boundary slice.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --execute-plan-liveness --plan <p> --repo-root <r>` prints `{"verdict":"paused"}` when a marker exists for `<r>` and `<p>`'s status is not `Complete`, and `{"verdict":"terminal"}` when the marker is absent — asserted by the new pytest module against real on-disk marker files (deterministic, no runtime).

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; the discriminator is a pure function of on-disk marker + plan status, fully covered by unit tests.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `execute_plan_liveness` (reuse the `md5(repo_root)[:12]` marker recipe; non-destructive read).
- `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` — add the parity-mirrored `--execute-plan-liveness` flag.
- `user/scripts/lazy-parity-manifest.json` — register the shared flag.
- `user/skills/lazy-batch/SKILL.md` (Step 1e/4a), `user/skills/lazy-bug-batch/SKILL.md` (guardrail-D block) — gate the recovery emit.
- `user/scripts/test_execute_plan_liveness.py` — new helper tests.

**Testing Strategy:** Unit-test the helper against real marker files + plan frontmatter fixtures (paused/terminal/fail-safe). Run `lazy_parity_audit.py --repo-root .` (exit 0) to prove the two state scripts stayed in lockstep. `cli_surface_gen.py --check` proves the new flag is registered on the roster.

**Integration Notes for Next Phase:**
- The discriminator is scoped to `/execute-plan` cycle returns only — Gap 1's hook (Phase 2) prevents the backgrounded suite that *creates* the paused return, so the two fixes are complementary layers, not duplicates.
- The helper returns `paused` (not `wedge-candidate`) when the marker is present; the genuine-wedge escalation (no live descendant + bounded wait ⇒ recovery) is orchestrator-observed prose per `dispatched-agent-liveness.md` §57–62 — do not push liveness/`TaskList` inspection into the script (it cannot observe descendants).
- Fail-safe direction is `terminal` — an unreadable signal must never suppress a legitimate recovery.

---

### Phase 2: Gap 1 — mechanical foreground-enforcement guard (new PreToolUse hook)

**Scope:** A new `user/hooks/cycle-subagent-bg-gate-guard.sh` PreToolUse guard that DENIES a `run_in_background: true` long-gate/test-suite launch from INSIDE an armed cycle subagent (payload carries `agent_id` AND the cycle marker is present), redirecting to the foreground-await mandate. This prevents the ambiguous "holding, will re-invoke" return at its source. Registered in `settings.json`; fail-OPEN; deny-via-JSON.

⚖ policy: Gap-1 guard command-classification scope → conservative token set (gate/test-suite/aggregate invocations at segment start), documented false-negative bias. Scope-class (tuning which backgroundings are denied, not user-visible product semantics); a missed command falls back to the existing prose mandate + Gap-2 discriminator, so under-matching is safe while over-matching would false-deny legitimate work.

**Deliverables:**
- [ ] `user/hooks/cycle-subagent-bg-gate-guard.sh` — PreToolUse (Bash|PowerShell). Fires ONLY when: payload carries `agent_id` (dispatched subagent) AND the cycle marker is present (armed) AND `tool_input.run_in_background == true` AND the command's first real command-segment token (after an optional env prefix, using `hook_lib`'s `_CMD_START`/`ENV_PREFIX` anchors) matches the gate/test-suite token set (e.g. `npm run qg`, `npm run test`/`vitest`, `pytest`, `cargo test`, `dotnet test`, `gate-battery`, the aggregate gate battery). Deny via JSON `permissionDecision: deny` with a message naming the foreground-await mandate ("run the individual under-cap sub-components synchronously; never background a long gate inside a cycle subagent"). Main-thread (no `agent_id`) ⇒ ALLOW (the orchestrator legitimately backgrounds the build spine). `run_in_background != true` ⇒ ALLOW.
- [ ] SOURCE `hook-prelude.sh` + import `hook_lib` for python resolution, allow/deny emitters, the segment-start anchor, `COMMAND_TOOL_NAMES`, and the no-python + catch-all breadcrumb (mirror `long-build-ownership-guard.sh`). Fail-OPEN on every error path (malformed JSON / missing python / unresolvable state ⇒ allow + breadcrumb).
- [ ] Register the guard in `user/settings.json` `hooks.PreToolUse` on the `Bash|PowerShell` chain (after `long-build-ownership-guard.sh`, before/near `build-queue-enforce.sh` — order it so a raw long BUILD still surfaces the ownership-takeover signature first; this guard targets the gate/test-SUITE background class the ownership guard does not cover).
- [ ] Tests (`test_hooks.py`): armed cycle subagent (`agent_id` + marker) + `run_in_background:true` + a gate token ⇒ DENY; same but main-thread (no `agent_id`) ⇒ ALLOW; `run_in_background:false` ⇒ ALLOW; armed subagent + a non-gate background command (e.g. a short `sleep`/log tail) ⇒ ALLOW; no marker ⇒ ALLOW; malformed payload / no-python ⇒ ALLOW (fail-open) + breadcrumb asserted.

**Minimum Verifiable Behavior:** `test_hooks.py` drives the guard with a synthetic PreToolUse payload (`agent_id` present, cycle marker staged, `tool_input.run_in_background:true`, `command:"npm run qg"`) and asserts the emitted decision is `deny`; the same payload without `agent_id` asserts `allow`. Deterministic, no live subagent.

**MCP Integration Test Assertions:** N/A — a shell hook exercised by synthetic JSON payloads; no runtime-observable app behavior.

**Prerequisites:** None (independent of Phase 1 — file-disjoint; may be built in parallel).

**Files likely modified:**
- `user/hooks/cycle-subagent-bg-gate-guard.sh` — new guard (net-new).
- `user/settings.json` — register the guard on the `Bash|PowerShell` chain.
- `user/scripts/test_hooks.py` — guard payload tests.

**Testing Strategy:** Pure hook-payload unit tests in `test_hooks.py` (the established synthetic-JSON harness) — deny/allow across the armed/main-thread, background-flag, command-classification, and fail-open axes. No live dispatch needed.

**Integration Notes for Next Phase:**
- Scope delineation to document in Phase 3: this guard covers the backgrounded gate/test-SUITE class inside cycle subagents; `long-build-ownership-guard.sh` covers exact long-BUILD invocations (`tauri build`/`cargo build --release`/`npm run build`) request-time regardless of subagent; `lazy-cycle-containment.sh` covers routing/lifecycle ops. Three distinct concerns — the CLAUDE.md row must state the delineation so a future editor does not think it redundant.
- Fail-open + conservative command set means a missed background still falls back to the prose mandate + Phase-1 discriminator — under-matching is safe, over-matching (false-deny) is the risk to avoid.

---

### Phase 3: Contract hardening + docs (prose backstop, re-invocation contradiction, Hooks table)

**Scope:** Point the prose foreground-await mandate at the now-existing mechanical guard, resolve/annotate the `turn-end-gate.md` re-invocation contradiction, add the new hook's CLAUDE.md Hooks-table row, add the `dispatched-agent-liveness.md` cross-ref, and re-project + lint so all doc-drift/parity/CLI-surface gates stay green.

**Deliverables:**
- [ ] `cycle-base-prompt.md` turn-end §1 (both feature+bug and cloud variants — verified at L648–657 and L710–722): add that the ban is now mechanically enforced (a PreToolUse guard denies a backgrounded long gate inside a cycle subagent), keeping the foreground-await instruction as the positive path.
- [ ] `turn-end-gate.md`: reference the mechanical guard at L23–30 (over-cap prevention), and annotate the L13–18 deterrent — note that dispatched cycle subagents MAY in practice receive background-completion re-invocation (undocumented/inconsistent, per `ADHOC_BRIEF.md`), so the mandate no longer rests on the "process tree is torn down" premise alone; it is enforced by the guard AND backed by the Gap-2 discriminator.
- [ ] `CLAUDE.md` (root) Hooks table: add the `cycle-subagent-bg-gate-guard.sh` row (Trigger: PreToolUse Bash|PowerShell; Purpose: denies a `run_in_background` long-gate/test-suite launch inside an armed cycle subagent; fail-OPEN), and state the three-guard delineation from Phase 2's notes. Keep the table consistent with `settings.json` (doc-drift-lint cross-checks it).
- [ ] `dispatched-agent-liveness.md`: one-line cross-ref that the Gap-2 discriminator now wires the authoritative-signal recipe into the orchestrator's awaited-`Agent`-result path (previously notification-path only).
- [ ] Re-project + lint: `python ~/.claude/scripts/project-skills.py`, `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities`, `python3 user/scripts/doc-drift-lint.py --repo-root .`, `python3 user/scripts/cli_surface_gen.py --check`, `python3 user/scripts/lazy_parity_audit.py --repo-root .` — all clean.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed`, writes `FIXED.md`, and archives the bug dir once the validation tail passes — never authored as a checkbox row here.

**Minimum Verifiable Behavior:** `doc-drift-lint.py --repo-root .` exits 0 (the new Hooks-table row matches the new `settings.json` registration), and `lint-skills.py --check-projected` exits 0 (the hardened components re-project cleanly). Deterministic, no runtime.

**MCP Integration Test Assertions:** N/A — documentation + prose hardening; no runtime-observable behavior.

**Prerequisites:**
- Phase 1: the discriminator + its state-script flag must exist for the prose to reference.
- Phase 2: the guard + its `settings.json` registration must exist for the Hooks-table row and the mandate reference to be accurate (doc-drift-lint would fail on a row with no registration).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, `user/skills/_components/turn-end-gate.md` — prose hardening.
- `user/skills/_components/dispatched-agent-liveness.md` — cross-ref.
- `CLAUDE.md` (root) — Hooks-table row + delineation.

**Testing Strategy:** Run the repo's doc/lint gate battery (project-skills, lint-skills `--check-projected`, doc-drift-lint, cli_surface_gen `--check`, lazy_parity_audit) — all exit 0. These deterministically prove the docs match the shipped hook/flag and the coupled pairs stayed in sync.

**Integration Notes for Next Phase:** Terminal phase — when this lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route to the validation tail. The `__mark_fixed__` gate owns the terminal `Fixed` flip + `FIXED.md` + archive.
