# Lazy Validation-Readiness (post-e076ed30 retro hardening) — Feature Specification

> Five harness changes that stop the lazy pipeline from *wasting* validation/dispatch cycles, distilled from the `/lazy-batch-retro` of AlgoBooth session `e076ed30` (focus: avoidable rework & harness hardening). Two close false-signal/recovery-cost classes in the dispatch loop (false `LOOP DETECTED`; transcription-slip denials); three move readiness checks *earlier* so a cycle is never spent validating against an unready feature, runtime, or scenario.

**Status:** Complete — all 6 phases implemented + unit-verified (412 harness tests + 58 AlgoBooth docs-consistency tests). Two live runtime smokes (F2a `updatedInput`, F7 Step-1d.0 restart) are certified on the next marked `/lazy-batch` run; see PHASES.md Runtime Verification.
**Priority:** P1
**Last updated:** 2026-06-13

**Depends on:** (none)

> Formally no dep-block entries (this repo's specs have no queue.json). Substantive relationships:
> - **turn-routing-enforcement** (`docs/specs/turn-routing-enforcement/SPEC.md`, Complete) is the substrate for F1 + F2: it built the run marker, the prompt registry (`register_emission`/`lookup_emission`/`prompt_sha256`), the validate-deny guard (`lazy_guard.py`, `_CORRECTIVE_RECIPE`), the deny ledger + routed hardening debt (Phase 7/8), and the persisted streak counters. F2 (dispatch-by-reference) extends the registry/guard dispatch contract; F1 extends the persisted streaks.
> - **lazy-pipeline-ergonomics** (`docs/specs/lazy-pipeline-ergonomics/SPEC.md`, implemented this session) is the **adjacent prior pass** — and this spec is deliberately scoped to its *gaps*. Ergonomics debounced `step_repeat_count` only (its Phase 2); F1 here debounces the **dispatch-tuple `repeat_count`**, the counter ergonomics left untouched. Ergonomics made validate-deny *recovery* cheaper (deny-reason + pure-suffix auto-readmit, its Phase 1); F2 here *eliminates the retype that causes the denial in the first place* (dispatch-by-reference) and decouples the residual slip class from the hardening-debt gate. The two specs compose; neither duplicates the other.
> - **lazy-hardening Phase 10** (`docs/specs/lazy-hardening/PHASES.md`, Complete) introduced `step_repeat_count`/`update_repeat_counts` — the function F1 extends.
> - Evidence base: AlgoBooth `docs/features/_index/LAZY_BATCH_REVIEW_2026-06-14_overview.md` §2 (findings) + §5 (ranked recommendations), and the four per-feature `LAZY_BATCH_REVIEW_2026-06-14.md` artifacts.

---

## Evidence base

All five findings are from the read-only skill-compliance audit recorded in AlgoBooth
`docs/features/_index/LAZY_BATCH_REVIEW_2026-06-14_overview.md` (session `e076ed30`,
`/lazy-batch 50 --park`, real-device Windows host, checkpointed at 25 forward cycles). The run was
**not clean** in the way the prior ergonomics-source run was: it spent ~4 cycles recovering false
`LOOP DETECTED` blocks (F1), 2 cycles draining self-inflicted transcription-slip hardening debt (F2),
and 3 of 4 front-loaded "almost-done" features turned out to need deep work that only surfaced at the
Step-9 mcp-test cycle — after a full ~150–300k-token cycle plus a BLOCKED plus a resolution each
(F5/F7/F8). These are the **avoidable-rework** classes the retro's focus targeted.

Excluded from this spec by design (stated so the scope boundary is auditable):
- **Retro F3** (`parse_phases` counted `## Phase Summary`) and **F4** (`update_repeat_counts`
  non-hermetic to `repo_root`) were **fixed live this run** (hardening Rounds 10 and 8 respectively).
- **Retro F6** (shared-runtime tx-counter / staged-swap mcp-test fidelity) is the AlgoBooth
  `mcp-test-fidelity` *feature*, not a claude-config harness change.

## Decisions resolved at authoring (operator, 2026-06-13)

- **F2 depth = "both"** — ship dispatch-by-reference (structural) **and** the lighter mitigations
  (Unicode-normalize before hashing; decouple shape-(a) slips from the debt gate) as defense-in-depth.
- **Research skipped** — internal harness mechanisms with root causes already diagnosed in the retro;
  no Gemini prior-art phase.
- **Single combined spec** (completeness-first / D7 sequencing auto-resolution) rather than five
  micro-specs; the five findings share one substrate and one verification harness.

---

## Findings → mechanisms

### F1 — Debounce the dispatch-tuple `repeat_count` (HIGH · harness)

**Recurred ~4× this run** (polyphonic write-plan p10 + execute-plan p10; d8-session-format realign;
the stale-retro re-probes). A second *advancing* (`--repeat-count`) probe of the same dispatch tuple
with **no dispatch between** increments `repeat_count` to 2, which appends the loop block and flips
`cycle_model` to sonnet — downgrading a genuinely-fresh forward cycle and costing a strip-loop-block
recovery each time.

- **Root cause:** ergonomics' Phase-2 consume-count debounce holds `step_repeat_count` when no
  dispatch landed between two identical-tuple probes, but the **dispatch-tuple `repeat_count` is not
  debounced** — it increments on any second advancing probe regardless of whether a dispatch (and
  registry consume) occurred. The orchestrator triggered it two mechanical ways: (a) filtering the
  probe output to summary fields lost the verbatim `cycle_prompt`, forcing a re-probe; (b) a
  `> /tmp/probe.json` redirect silently failed under git-bash, having already run the probe once.
- **Mechanism:** in `lazy_core.update_repeat_counts`, extend the existing consume-count debounce to
  guard `repeat_count` exactly as it already guards `step_repeat_count`: do **not** increment the
  dispatch-tuple streak when the consumed-emission count is unchanged between two identical-tuple
  probes (a re-read, not a re-attempt). Reuse the same "did a dispatch happen" oracle — the registry
  consume-count delta when a run marker is present (the guard consumes a nonce on every allow);
  marker-gated so unmarked runs and `--test` baselines are byte-identical. A genuine stall still trips
  because it involves a real dispatch (and consume) between repeats.
- **Why not rely on orchestrator discipline:** "probe once / capture full `cycle_prompt` / never
  redirect to `/tmp`" is the documented behavioral complement (already in the SKILLs), but it failed
  ~4× this run. Closing the class at the script makes it independent of orchestrator discipline.

### F2 — Dispatch-by-reference + decouple the transcription-slip debt (HIGH · harness)

**2 denials this run**, each converting a trivial Unicode typo into an expensive recovery: a single
`—`→`-` normalization in a hand-copied prompt failed the guard's raw-byte hash → a `pending_hardening`
debt entry → a full `/harden-harness` run to ack it — and the drain itself could be (and once was)
denied for the same reason, compounding. Rounds 8 and 9 were partly self-inflicted drains of this
class.

- **Root cause:** the orchestrator must reproduce large script-emitted prompts **byte-exact** by
  retyping them; the model trivially normalizes Unicode (em-dash, smart quotes); the guard hashes raw
  bytes with no normalization; and the `pending_hardening` debt gate then treats a transcription slip
  the same as a genuine harness gap.
- **Mechanism (resolved depth = "both"):**
  - **F2a — dispatch-by-reference (structural; eliminates the class).** `--emit-dispatch` /
    `--emit-prompt` already register the prompt under a nonce. Add a sanctioned dispatch form in which
    the `Agent` call references the registered prompt **by nonce/id** instead of pasting the full text;
    the guard resolves the nonce → registered bytes and ALLOWS without a hash comparison against
    orchestrator-typed text. No retyping ⇒ no transcription-failure class, for cycle prompts **and**
    meta dispatches. The reference path consumes the nonce exactly as the verbatim path does (one
    allow = one consume), so F1's consume-count oracle is unaffected.
  - **F2b — guard Unicode-normalizes before hashing (defense-in-depth for residual verbatim paths).**
    Extend `normalize_prompt_for_hash` to fold Unicode dashes/quotes (em-dash↔hyphen, smart↔straight
    quotes, NBSP↔space) before the hash, so any remaining hand-composed/verbatim path is robust to the
    exact slip class that bit this run. Mirror the same normalization into ergonomics' F1b auto-readmit
    near-match so a normalized near-match (not only a trailing-suffix superset) auto-readmits.
  - **F2c — decouple shape-(a) transcription-slip denials from the hardening-debt gate.** A shape-(a)
    denial (hash mismatch on an otherwise registered-class prompt — i.e. the dispatched text resolves
    to a known nonce-class but the bytes differ only by normalization-equivalent characters) must be a
    **cheap re-emit + verbatim/by-reference re-dispatch**, NOT a `pending_hardening` debt entry that
    demands a `/harden-harness` drain. Reserve the debt gate strictly for genuine no-route / harness-gap
    denials. The denial telemetry/ledger records the shape so the retro can distinguish "cheap slip"
    from "real gap."
- **Integrity guardrail (carried from ergonomics' F1b tradeoff discipline):** dispatch-by-reference
  must NOT weaken turn-routing's "hand-composed prompts are unexecutable" guarantee — a *reference*
  carries no hand-composed body to smuggle clauses through, so the guarantee is preserved by
  construction (the bytes are the registered bytes). F2b/F2c only relax the *byte-equality* check to a
  *normalization-equivalence* check; any in-body semantic edit still denies. State this explicitly in
  the guard's deny telemetry so the relaxation is auditable, not silent.

### F5 — Validation-readiness pre-screen before front-loading (HIGH · harness/operator-lever)

**3 of 4 front-loaded "almost-done DEFERRED_NON_CLOUD" features needed deep work**, not quick
verification — and the gap (unwired production surface / missing test infrastructure / non-existent
asserted tool) only surfaced at the workstation Step-9 mcp-test, after a full cycle + BLOCKED +
resolution each. Only `sidecar-watchdog` validated cleanly, and only because its blocker bug had been
fixed+archived *before* the run.

- **Root cause:** cloud-built features carry `DEFERRED_NON_CLOUD`, but a cloud run never exercises the
  workstation MCP path, so unwired surfaces only manifest when the workstation finally runs mcp-test.
- **Mechanism:** a cheap **docs-only validation-readiness pre-screen**, runnable at queue-curation
  time and again at the top of a `--park`/front-loaded `/lazy-batch` run, that for each candidate
  feature carrying `DEFERRED_NON_CLOUD` greps:
  - every MCP tool name asserted by the feature's `mcp-tests/` scenarios resolves in
    `src-tauri/src/ipc/mcp/registrations/`;
  - every production emitter/wiring the scenario asserts exists in source (the event is published, the
    API is bound into its call scope).
  Emit a per-feature `ready | needs-work` verdict with the specific missing surface. Front-load only
  the passers; route the rest to focused implementation sessions. This shares its grep core with F8
  (same "does the asserted surface exist?" check) — F8 runs it at *authoring* time per-scenario, F5
  runs it at *curation* time per-feature; factor the resolver once and call it from both.
- **Surface:** a reusable script (`scripts/` in this repo, callable standalone) + a `/lazy-batch`
  pre-loop advisory step that prints the verdict table; **advisory, not a hard gate** (the operator may
  still front-load a `needs-work` feature deliberately) — but the verdict is logged so a deep blocker
  surfacing later is traceable to an ignored pre-screen.

### F7 — Stale-binary detection in Step 1d.0 (MEDIUM · harness)

After polyphonic Phase 10 added a Rust MCP tool, the running runtime was **stale**, but Step 1d.0 only
probes `GET /health == 200` — which a stale binary passes. Only the orchestrator's manual judgment
forced the `dev:restart` that picked up the new tool; a future run without that judgment would dispatch
mcp-test against a stale binary and BLOCK on a 404 for a tool that actually exists.

- **Mechanism:** Step 1d.0's pre-mcp-test readiness check compares the running runtime's **boot time**
  against the latest commit timestamp touching `src-tauri/` + `crates/`; if Rust advanced since the
  runtime booted, **force a `dev:restart`** before the mcp-test cycle instead of trusting health=200.
  Boot time is read from the runtime/session metadata already available to Step 1d.0 (no new runtime
  endpoint required if the session-log boot stamp suffices; otherwise add a `boot_commit`/`boot_time`
  field to the health payload as the minimal extension).
- **Scope note:** this is an AlgoBooth-runtime-shaped check, so the *mechanism* lives in the AlgoBooth
  `lazy-batch` Step 1d.0 prose / `mcp-test` precheck; this spec owns the **policy** (the rule and its
  rationale) and the shared boot-time-vs-commit predicate. Keep the predicate generic (compare runtime
  boot stamp vs newest commit under a configured set of native-source globs) so it is not AlgoBooth-only.

### F8 — Scenario-surface existence lint at authoring time (LOW→MEDIUM · harness/scenario-authoring)

write-plan/execute-plan authored MCP scenarios asserting tools/emitters that **don't exist**
(d8-session-format's `evaluate_code`; polyphonic's live diagnostic counters), so the gap was only
discovered at the Step-9 mcp-test cycle (full boot + BLOCKED + corrective phase) — ~3 cycles later than
it could have been.

- **Mechanism:** a **scenario-surface existence lint** that, for every MCP scenario authored under a
  feature's `mcp-tests/`, verifies each asserted MCP tool name resolves in
  `src-tauri/src/ipc/mcp/registrations/` and each asserted production event has an emitter in source.
  Run it (a) at scenario-authoring time inside the write-plan/execute-plan cycle (fail-fast, ~1 cheap
  cycle) **and** (b) as a `qg:docs-consistency` rule so it is enforced project-wide, not only when a
  pipeline cycle happens to author a scenario. Shares the grep/resolver core with F5 (factor once).
- **Verdict shape:** error when a referenced tool/emitter cannot be resolved; the message names the
  missing surface and the scenario file + line, so the author fixes it before the plan lands.

---

## Non-goals

- **No change to what the guard enforces or to the stall threshold (`≥3`).** F1 only removes a
  *false-positive* increment; a genuine stall (real dispatch between repeats) still trips. F2 only
  relaxes byte-equality to normalization-equivalence and adds a reference path; any semantic in-body
  edit still denies.
- **No change to the park feature, the cloud/workstation split, or the device axis.**
- **F6 (mcp-test-fidelity) is out of scope** — that is the AlgoBooth feature's charter.
- **F3/F4 are already fixed** (Rounds 10/8) and are not re-implemented here; they are listed only to
  fix the scope boundary.
- **F5 is advisory, not a hard front-load gate** — it informs curation; it does not block the operator
  from deliberately front-loading a `needs-work` feature.
- **No new subsystem.** Every change extends existing surfaces: `lazy_core` (F1), `lazy_guard` +
  the registry dispatch contract (F2), a shared surface-existence resolver + `lazy-batch` pre-loop step
  (F5), AlgoBooth Step 1d.0 precheck + a generic boot-time predicate (F7), and
  write-plan/execute-plan + `qg:docs-consistency` (F8).

## Verification posture

`**MCP runtime:** not-required` for the claude-config-owned mechanisms (F1, F2, and the F5/F8 shared
resolver) — they target the harness (scripts, guard, registry contract, lint), not an AlgoBooth app
surface. Verified via:

- `test_lazy_core.py` — F1 dispatch-tuple debounce: a second advancing probe with no consume between
  does not increment `repeat_count`; a real dispatch+consume between repeats still does; marker-gated
  so `--test` baselines are byte-identical.
- `test_hooks.py` / guard tests — F2a by-reference dispatch resolves a nonce → ALLOW + consume; F2b
  Unicode-normalized near-match auto-readmits; F2c shape-(a) denial does NOT write a `pending_hardening`
  entry while a genuine no-route denial still does.
- The shared surface-existence resolver — unit-tested against a fixture registrations tree (resolves a
  present tool; flags an absent tool/emitter) so F5 and F8 share proven logic.
- `lint-skills.py --check-projected --check-capabilities` after any SKILL prose change (F5 pre-loop
  step, F7 Step 1d.0 policy, F8 authoring-time lint).
- Both state-script `--test` smokes (baselines byte-identical) and a next-marked-run live check.

F7's stale-binary check and F8's `qg:docs-consistency` rule have an AlgoBooth-side surface; they are
exercised on the next workstation `/lazy-batch` run (F7: a stale Rust binary forces a restart; F8: an
mcp-test scenario asserting a non-existent tool fails the docs-consistency gate at authoring time).
