# CLAUDE.md — user/scripts/ (the `/lazy` autonomous pipeline)

This directory holds the **state machine that drives the `/lazy` family** of autonomous
orchestration skills. `lazy-state.py` is the source of truth; the skills are thin LLM
wrappers around it. When the pipeline's behavior needs to change, change the script —
not the wrappers — and keep the wrappers + smoke tests in lockstep (see Coupling Rule).

## What the lazy system is

A **file-driven** autonomous pipeline that walks a queue of work items (features via
`lazy-state.py`; bugs via `bug-state.py` — the lazy-bug family, see
`plans/lazy-bug-family.md`) through a fixed lifecycle, inferring "what to do next"
*purely from on-disk files* — never from
conversational memory. State lives in `**Status:**` lines, plan frontmatter, and
sentinel files. This is why the file contracts are load-bearing, not bureaucracy: a
malformed sentinel or a hand-flipped status corrupts the machine's view of the world.

```
queue.json + per-item SPEC/PHASES/plans/sentinels
        │
        ▼
  lazy-state.py  ──►  JSON { sub_skill, sub_skill_args, terminal_reason, … }
        │
        ▼
  thin skill wrapper  ──►  dispatch ONE sub-skill (or perform a __special_action__) ──► STOP
```

## Files in this directory

| File | Role |
|------|------|
| `lazy-state.py` | **Source of truth** for the feature state machine. Computes the next `/lazy` / `/lazy-cloud` action from `docs/features/`. ~2500 lines incl. an in-file smoke-test harness. Imports `lazy_core`. |
| `lazy_core.py` | Shared, domain-agnostic helpers (sentinel/plan parsing, deliverable counting, receipt writers, diagnostics infra) imported by both `lazy-state.py` and `bug-state.py`. Owns the per-invocation `_DIAGNOSTICS` list. `write_completed_receipt(..., kind=)`/`has_completion_receipt(..., filename=)` are parameterized so the bug pipeline can write `FIXED.md` (`kind: fixed`). |
| `bug-state.py` | Bug-lifecycle state machine over `docs/bugs/`. Same JSON contract as `lazy-state.py`; research/Gemini/stub steps dropped; terminal action is **archive-on-fix** (`__mark_fixed__`). Hybrid ordering (`queue.json` overrides, then severity + Discovered date). In-file `--test` smoke harness. Imports `lazy_core`. |
| `lazy_coord.py` | **Concurrency plane** (Phase 4) — net-new, **kept separate from `lazy_core.py`**. Stdlib-only `os.mkdir` global lock + fencing-token leases (`leases.json`), heartbeat, expiry reclamation, and worktree-pool provisioning + scrub-to-clean. Imported by the `lazy-worker` skill (and available to the state machines). In-file `--test` smoke harness (5 concurrency fixtures). See "Concurrency plane" below. |
| `toolify-miner.py` | **Offline toolification miner** (unified-pipeline-orchestrator Phase 4) — stdlib-only, **READ-ONLY over logs**. Parses `~/.claude/projects/**/*.jsonl` (+ `subagents/agent-*.jsonl`), normalizes orchestrator tool-call sequences into argument-shape signatures (values elided), ranks by `occurrences × est_tokens_per_occurrence`, and applies the **deterministic-only bar** (above-bar iff deterministic AND repeated ≥2 runs AND token-heavy). Emits markdown + JSON. NEVER mutates logs (every test hashes the fixture log dir before/after). The miner *proposes* — promotion to a real subcommand is deliberate. Tests: `test_toolify_miner.py`. Doc/schema/checklist: `docs/features/unified-pipeline-orchestrator/toolify-bar.md`. Not part of the lazy state machine — a standalone analysis tool. |
| `claude-bash-env.sh` | Restores `node`/`cargo` onto PATH for Claude Code's non-login Bash (sourced via `BASH_ENV`). Unrelated to the pipeline. |

## The skill family (thin wrappers)

All wrappers run `lazy-state.py`, dispatch the one named sub-skill (or perform a
`__special_action__`), and stop. They carry **no state-machine logic** of their own.

| Skill | Scope | Wraps | Purpose |
|-------|-------|-------|---------|
| `lazy` | user-level (`user/skills/`) | `lazy-state.py` | One sub-skill per invocation — manual stepping. |
| `lazy-batch` | user-level | `lazy-state.py` | Autonomous loop; spawns one Opus subagent per cycle. |
| `lazy-status` | user-level | `lazy-state.py` (read-only) | Progress dashboard; never acts. |
| `lazy-cloud` | repo (algobooth) | `lazy-state.py --cloud` | Cloud variant; defers Tauri/MCP/device steps. |
| `lazy-batch-cloud` | repo (algobooth) | `lazy-state.py --cloud` | Autonomous cloud loop. |
| `lazy-batch-retro` | repo (algobooth) | — | Audits/grades a completed batch run for skill-compliance. |
| `lazy-bug` | user-level (`user/skills/`) | `bug-state.py` | One sub-skill per invocation over `docs/bugs/`; `__mark_fixed__` archive-on-fix terminal. |
| `lazy-bug-batch` | user-level | `bug-state.py` | Autonomous bug loop; spawns one Opus subagent per cycle. |
| `lazy-bug-status` | user-level | `bug-state.py` (read-only) | Bug dashboard; never acts. |
| `lazy-worker` | user-level | `lazy_coord.py` + `lazy-state.py --feature-id` / `bug-state.py --bug-id` | One concurrent worker session: claims a leased item (+ worktree slot), implements → opens a GH PR, finalizes under the lock. Bounded by `pool_size`. |

> **Why some are repo-scoped:** `lazy`/`-batch`/`-status` are user-level but are in
> practice AlgoBooth-flavored (they read `$ALGOBOOTH_REAL_AUDIO_DEVICE`, dispatch
> AlgoBooth skills). The cloud + retro variants were added repo-scoped. The
> **lazy-bug family** (`lazy-bug`, `lazy-bug-batch`, `lazy-bug-status`) is **user-level**,
> mirroring the base trio, and drives `bug-state.py` over `docs/bugs/`. Its archive-on-fix
> terminal is documented in `_components/mark-fixed-archive.md`.

## The per-item lifecycle (features)

```
spec → research → phases → plan → implement (execute-plan)
     → retro (RETRO_DONE.md) → MCP validation (VALIDATED.md / skip / device-defer)
     → mark-complete (writes COMPLETED.md receipt, flips Status → Complete)
```

Step-by-step dispatch (see the `compute_state()` docstring + body for the authoritative
table): Step 2 find current item → Step 3 BLOCKED/NEEDS_INPUT → Step 4 SPEC → Step 4.5
stub-spec → Step 4.6 upstream realign → Step 5 research gate → Step 6 PHASES → Step 7
plan/execute → **Step 8 retro → Step 9 MCP gate → Step 10 mark-complete**.

> **Step-4.5 clear-owner (`stub-spec-route-loops-until-queue-stub-cleared`, 2026-06-20).** At the
> Step-4.5 branch, `_stub_is_queue_flag_only(spec_text, queue_entry)` detects the post-baseline
> state where the `queue.json` `"stub": true` flag is the LONE surviving stub marker (the `/spec`
> Phase-1 rewrite already dropped the SPEC-text markers — `_spec_text_has_stub_marker`, factored
> out of `is_stub_spec`). When it fires, `lazy-state.py` clears the flag via
> `lazy_core.clear_queue_stub(queue_path, feature_id)` (script-owned, never an orchestrator
> hand-edit) and FALLS THROUGH to Step 5 — closing the commit-masked Step-4.5 loop (HEAD advanced
> each cycle while the route never left Step 4.5). A true pre-baseline stub (SPEC-text marker still
> present) is byte-identical to before: dispatch `/spec` at Step 4.5. Feature-pipeline only —
> `bug-state.py` has no stub step, so `clear_queue_stub` (shared `lazy_core`) is invoked solely by
> `lazy-state.py` (correct divergence, no parity mirror).

## Three environments + the device axis

Two orthogonal axes; three environments. See `docs/features/CLAUDE.md` (in AlgoBooth) for
the full table. In short:

- **cloud** (`--cloud`) — no Tauri/MCP/device; defers MCP steps via `DEFERRED_NON_CLOUD.md`.
- **no-real-device workstation** (`--real-device no`, the default; `auto` reads
  `$ALGOBOOTH_REAL_AUDIO_DEVICE`) — runs MCP under the HeadlessPumpDriver; sustained-timing
  assertions are **deferred** via `DEFERRED_REQUIRES_DEVICE.md`, not skipped.
- **real-device workstation** (`ALGOBOOTH_REAL_AUDIO_DEVICE=1`) — re-opens device-deferred
  assertions and certifies them.

**Skip ≠ defer.** `SKIP_MCP_TEST.md` = permanent waiver (untestable on any host).
`DEFERRED_*` = re-opened later on the right host. Faking one for the other is the
anti-pattern the lint warns on.

## Completion is receipt-gated

An item is genuinely done only when `**Status:** Complete` **and** a `COMPLETED.md` receipt
exists. The receipt is written **only** by the completion-integrity gate inside
`__mark_complete__`. A `Complete` claim with no receipt is a hard error
(`completion-unverified` halt; `spec-complete-requires-receipt` lint). `Superseded` is
exempt. `--backfill-receipts` grandfathers pre-gate completions as
`provenance: backfilled-unverified` (honest debt, not silenced).

## Sentinel / plan / receipt schemas

Canonical schema: `user/skills/_components/sentinel-frontmatter.md` (mirrored in
AlgoBooth's `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS` — keep the two in
lockstep). Every sentinel and plan file begins with a `---`-delimited YAML frontmatter
block; the markdown body is human context only (one exception: `NEEDS_INPUT.md`, whose
body is load-bearing). Plan files: `kind ∈ {implementation-plan, retro-plan, fix-plan,
realign-plan}`, `status` transitioned only by `/execute-plan`.

## CLI surface

```bash
python3 lazy-state.py                       # next workstation action (JSON on stdout)
python3 lazy-state.py --cloud               # cloud variant
python3 lazy-state.py --real-device auto    # resolve host audio capability from env
python3 lazy-state.py --skip-needs-research # batch: skip research-pending items
python3 lazy-state.py --repo-root <path>    # operate on a specific repo
python3 lazy-state.py --park-needs-input    # batch --park mode: skip (park) NEEDS_INPUT items into parked[] instead of halting (BLOCKED still halts UNLESS --park-blocked is also active; output byte-identical without the flag)
python3 lazy-state.py --park-blocked        # batch --park mode companion: skip (park) a feature/bug-local BLOCKED.md into parked[] (sentinel_kind: blocked) instead of halting on terminal_reason=blocked; --park passes BOTH flags. Global/env terminals (cloud/device/research/scoped-id) still halt. Output byte-identical without the flag. Same flag on bug-state.py.
python3 lazy-state.py --per-feature-cycle-cap N  # feature-budget-guard: override the dynamically-computed per-feature ceiling L_task with a fixed integer N. Default (flag absent): L_task = max(6, min(floor(C_global * 0.4), floor((C_global / Q_depth) * 2))). When the guard trips, the budget_guard probe field surfaces the computed (or overridden) ceiling in count_at_trip + computed_ceiling + action (defer|evict) + next_id + sub_skill_phase + commit_hash. Terminal queue-exhausted-budget-deferred fires when all items are budget-deferred/evicted with no independent successor. Environment-agnostic — same flag on lazy-state.py --cloud.
python3 lazy-state.py --strict-research-halt     # feature-budget-guard skip-ahead: disable the default-on dependency-aware skip-ahead (restores legacy halt-on-first-gated-head). Default (flag absent): when the queue head is research-gated or BLOCKED, lazy-state.py automatically advances to the next independent, independent:true-marked queue item (if one exists) instead of halting immediately. The gated head always surfaces in the probe's gated_heads key (list of gated feature_ids) regardless of whether skip-ahead advanced past it — used by the orchestrator for end-of-run flush. Environment-agnostic — same flag on lazy-state.py --cloud.
python3 lazy-state.py --enqueue-adhoc …     # prepend an ad-hoc item to the queue. --type {feature,bug} (default feature; unified-pipeline-orchestrator Phase 3) selects the destination pipeline: feature → docs/features/queue.json (unchanged); bug → docs/bugs/queue.json via the EXISTING bug-state.py enqueue (enqueue_adhoc_bug() seeds docs/bugs/<slug>/ around the subprocess — NOT a reimplementation). bug-state.py --enqueue-adhoc accepts a benign --type bug so the documented unified form parses.
python3 lazy-state.py --reorder-queue --id <id> --to {tail|head|remove|<index>}  # no-sanctioned-queue-reorder-command: OPERATOR-ONLY / OUT-OF-CYCLE queue-ordering mutation on docs/features/queue.json (the existing-entry counterpart to --enqueue-adhoc's insert-at-head). Gated by refuse_if_cycle_active("--reorder-queue") FIRST — a cycle subagent is refused exit 3 with ZERO side effects, exactly like --enqueue-adhoc. Requires --id (REUSES the existing --id flag; no second id flag) and --to. --to: `tail`/`head`/`remove`, or an integer index (out-of-range clamped). Folds all four operator queue mutations (defer-to-tail, move/reorder, remove/skip, reprioritize) into ONE primitive — calls the shared lazy_core.reorder_queue helper (load → mutate → _atomic_write, mirroring enqueue_adhoc). A missing id or malformed JSON _die()s (exit 2); moving an entry already at the target is a byte-stable no-op (returns noop: true). PRESENT ON BOTH SCRIPTS (coupled pair): bug-state.py --reorder-queue mutates docs/bugs/queue.json identically (parity-guarded by lazy_parity_audit.py::audit_state_script_parity). Replaces the legacy reorder-via-BLOCKED.md + dispatched apply-resolution subagent round-trip (the blocked-resolution.md Defer path now calls this command inline; HARD CONSTRAINT 1's no-hand-edit-queue.json rule is preserved — the orchestrator calls the script).
python3 lazy-state.py --next-merged          # unified-pipeline-orchestrator Phase 1: print the head of the MERGED feature+bug work-list as JSON {item_id, type, repo_root} (or null when both queues empty). Read-only ORDERING ONLY — reuses load_queue (features) + bug-state.load_bug_queue (bugs, via importlib) and the lazy_core ordering helper; NEVER re-infers per-item state (the unified driver still calls --probe/--emit-prompt per item). Normalizes the two queues' divergent ordering fields (feature `tier` int / bug `severity` P0..Low) to one effective-priority scale (lower = higher priority); equal priority → bug before feature; stable within each queue. Binds the active repo before reading. Shared impl: lazy_core.merged_priority/merged_worklist/next_merged.
python3 lazy-state.py --backfill-receipts   # grandfather pre-gate completions
python3 lazy-state.py --test                # run the in-file fixture smoke tests
# --- Phase 5 orchestrator-loop subcommands (shared impl in lazy_core.py; same flags on bug-state.py) ---
python3 lazy-state.py --verify-ledger <spec_path> [--plan <plan_part>]  # completion-ledger gate as JSON {ok, failing_check, checks:{clean_tree, head_matches_origin, plan_complete, deliverables_done}, deliverables_source}; exit 1 iff not ok. Replaces the 5 duplicated prose ledger blocks. deliverables_done exempts verification-only rows. SOURCE OF TRUTH (2026-06-15, d8-effect-chains review): with --plan, deliverables_done reads the PLAN PART's own `- [ ] WU-N` checkboxes (machine record since write-plan ISSUE-6), NOT PHASES.md phase-level rows — eliminating cross-part + cross-phase-attribution false-fails. A legacy plan with no per-WU rows falls back to PHASES-phase-level and reports deliverables_source: "phases-fallback …". Without --plan: whole-feature PHASES.md (deliverables_source: "phases-feature-level").
python3 lazy-state.py --ensure-runtime               # unified-pipeline-orchestrator Phase 5 + long-build-and-runtime-ownership Phase 2 (LD2/LD3): ensure the dev runtime + MCP server are up, CURRENT, and VERIFIABLY OWNED; print the M4 liveness/recovery verdict JSON {state, ownership_verified, health_code, mcp_tools_present, terminal_blocker} with state ∈ {READY, STALE, HIJACKED, DEAD, BLOCKED}. (The legacy {status: ready|booted|stale-rebuilt} field is RETAINED in the dict — the verdict is a SUPERSET so the part-5 orchestrator migration is incremental.) The reworked-in-place ensure_runtime runs the M4 three-phase evaluation: Identity (read `.runtime.lock.json` → verify_runtime_ownership against the live kernel start_time + the run marker's session_id; divergent live owner answering /health ⇒ HIJACKED, missing/dead PID ⇒ DEAD) → Staleness (injected stale_check ⇒ STALE) → Health (probe /health; refused despite a live owned PID ⇒ DEAD). RECOVERY contract: STALE/DEAD auto-recover via restart() in a bounded exponential-backoff loop CAPPED AT 5 attempts (rewriting `.runtime.lock.json` on a healthy re-probe → READY); on exhaustion ⇒ BLOCKED + terminal_blocker. HIJACKED is a strict FAIL-SAFE — terminal_blocker set, the foreign process is NEVER SIGKILLed (security/stability, LD3). The handler threads the LIVE run marker's session_id as live_session_id (the controller_session_id recorded into the lock — NOT a second minted id); with no marker (interactive, no run) it falls back to the legacy boot/ready flow (still the verdict superset). AlgoBooth specifics (TCP 3333, npm run dev:restart, src-tauri/crates globs, asserted MCP tool, the `.runtime.lock.json` filename) are PARAMETERIZED in lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG (caller-overridable dict) — NOT hard-coded into the shared harness flow. lazy_core.ensure_runtime takes injected probe/restart/stale_check/read_lock/kernel_start_time_fn/sleep/write_lock/recover_identity callables so --test is hermetic (the ≤5 bound, the backoff schedule, and the never-SIGKILL invariant are asserted without a real runtime/network/clock/kill); production uses a real urllib probe + background dev:restart + the stale_binary predicate + the real kernel start_time extractor. CONSUMER ROUTING (long-build-and-runtime-ownership Phase 5): `/lazy-batch` Step 1d.0 (the sole consumer; `/lazy-batch-cloud` defers MCP and never reaches it — workstation-only) calls this ONCE per mcp-test cycle and routes on the FULL verdict's `state` — no hand-rolled rebuild→health-poll until-loop in the cycle prompt: READY / STALE→READY / DEAD→READY proceed to dispatch; `state ∈ {HIJACKED, BLOCKED}` (and any residual unrecoverable `mcp_tools_present: false`) ⇒ the orchestrator writes `BLOCKED.md` `blocker_kind: mcp-runtime-unready` (the verdict's `terminal_blocker` text VERBATIM as the body) and dispatches NO subagent against a dead/hijacked runtime. The mirrored guard-takeover path: when `long-build-ownership-guard.sh` denies a subagent long build (bubbling `LONG-BUILD-OWNERSHIP-TAKEOVER`), the orchestrator runs the build under the Transient Build contract (`run_transient_build` + `promote_artifact_atomically`) — distinct from this Persistent Service runtime (LD5: one spawn primitive, two contracts). SIDECAR-PIPE READINESS (env-transient-counts-against-validation-retry-budget Phase 1, Leg A — repo-agnostic default OFF): the dev HTTP server boots INDEPENDENTLY of the MCP sidecar named pipe, so health=200 does NOT prove the sidecar is connected — a zombie node process holding the :3333 pipe after a dev:restart leaves the runtime HTTP-healthy but MCP-functionally DEAD (a self-inflicted env transient). When a repo sets `assert_sidecar_connected: true` (+ optional `sidecar_status_url`, default `http://localhost:3333/tools/get_sidecar_status`) in its config override — AlgoBooth opts in; default OFF keeps every other repo unaffected — the M4 Health phase additionally asserts `get_sidecar_status.is_connected: true` AFTER code==200 and BEFORE the READY verdict: a disconnected pipe routes into the SAME bounded recovery (a dev:restart that reaps the stale pipe; `_recover_runtime` re-asserts the pipe on each healthy re-probe, so a restart that fixes HTTP but not the pipe does NOT count recovered) and, on persistent disconnect, to `state: BLOCKED` → `blocker_kind: mcp-runtime-unready` (escalation-immune) — NEVER an `mcp-validation` charge against the feature's validation-retry budget. Threaded via a new injected `sidecar_check` callable on `ensure_runtime` (bound to the real `_default_sidecar_probe` only when the config asserts it, else `lambda: True`) so --test stays hermetic; `validation_escalation` is UNCHANGED (the fix keeps env transients from reaching it with the `mcp-validation` label).
python3 lazy-state.py --gate-coverage <spec_path>    # unified-pipeline-orchestrator Phase 5: deterministic, symlink-resolving Gate-1 MCP-coverage verdict. Print JSON {ok, decisions:[{id,title,keywords,covered}], uncovered:[id], scenario_count}; exit 1 iff any decision uncovered. Reads SPEC.md's Locked-Decision surface (## Locked Decisions table / ## Resolved by Research checked bullets / ## Key|Design Decisions numbered block) and greps mcp-tests/*.md RESOLVING symlink + 64-byte-pointer targets (the Windows blindspot the prose grep missed). Promotes the mcp-coverage-audit.md algorithm to code (lazy_core.gate_coverage); the component points at this subcommand. Covered iff a scenario carries the decision id literal OR ≥2 keywords.
python3 lazy-state.py --apply-pseudo <name> <spec_path>    # SINGLE author of the deterministic pseudo-skill writes: __write_validated_from_{skip,results}__, __write_deferred_non_cloud__, __flip_plan_complete_cloud_saturated__ (pass --plan), __mark_complete__/__mark_fixed__ (receipt + SPEC/PHASES status flip + sentinel cleanup). Idempotent; refuses when gate inputs absent. __write_validated_from_results__ additionally gates on kind: mcp-test-results + result: all-passing + pass_count == total_count + validated_commit == current HEAD (legacy field-less files pass with a warnings[] entry) — NEVER hand-write VALIDATED.md. Optional: --plan/--apply-date/--reason/--deferred-step. unified-pipeline-orchestrator Phase 5: __mark_complete__ (feature path) now ALSO strikes the docs/features/ROADMAP.md row (moved IN from orchestrator-inline; returns roadmap_struck) and trims docs/features/queue.json by the RESOLVED spec_dir (returns queue_trimmed — kills the -followups queue.no-completed miss class). (__flip_plan_complete_stale__ stays orchestrator-inline.) COUNTER ADVANCE (lazy-batch-unified-driver-parity-and-accounting Phase 1, item 1): after a SUCCESSFUL forward-advancing pseudo-skill apply (name ∈ lazy_core._FORWARD_ADVANCING_PSEUDO_SKILLS = {__mark_complete__, __mark_fixed__, __write_validated_from_skip__, __write_validated_from_results__, __grant_skip_no_mcp_surface__, __flip_plan_complete_cloud_saturated__}), the handler calls lazy_core.advance_forward_cycle(...) so the inline pseudo-skill cycle advances forward_cycles — these cycles dispatch no Agent / no guard ALLOW / no registry consume, so the consume-gated advance_run_counters never advanced them. Marker-gated + fail-open (a breadcrumb, never blocks the apply).
python3 lazy-state.py --neutralize-sentinel <path>         # rename a resolved sentinel to <stem>_RESOLVED_<date><ext>, collision-safe (numeric suffix, never clobbers)
python3 lazy-state.py --repeat-count                       # fold a repeat_count field (consecutive identical-probe count, per-repo OS-temp signature file) into the probe JSON for mechanical loop detection; byte-identical default without the flag; folds/advances marker-persisted forward_cycles/meta_cycles counters when a run marker is present
python3 lazy-state.py --probe --forward-cycles N --meta-cycles M --max-cycles K  # fold git_guards (clean_tree/head_matches_origin/unpushed) + a pre-formatted cycle_header line into the probe JSON; byte-identical default without the flag; --repeat-count-peek reads marker-persisted counters without advancing them
python3 lazy-state.py --run-start                          # write the run marker to the state dir (pipeline=feature); gates registry writes and counter advances for this run; uses --cloud, --repo-root, --max-cycles when present; prints marker JSON and exits
python3 lazy-state.py --run-end                            # delete the run marker and the prompt registry from the state dir; call on every terminal run path; prints {"run_marker_deleted": true|false} and exits
# --- lazy-cycle-containment C1/C3 (cycle-subagent marker; same flags on bug-state.py, which uses --bug-id) ---
python3 lazy-state.py --cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]  # write the cycle-subagent marker (lazy-cycle-active.json, sibling of the run marker) immediately BEFORE every Agent dispatch; self-healing (overwrites a stale marker + logs); prints marker JSON. The marker carries feature_id/nonce/kind/started_at/session_id/commit_tally + (hardening-blind-to-process-friction Phase 2, additive) run_started_at (the live run marker's started_at snapshot — the stable run identity; null when no run is live) and begin_head_sha (git rev-parse HEAD snapshot; null on a non-git tree). These two power the --cycle-end process-friction detector. SIDE EFFECT (long-build-and-runtime-ownership Phase 4 / M5 Detect / LD4): BEFORE the marker write, runs lazy_core.reconcile_cycle_begin_git_consistency() — a pre-boot .git/index.lock (mtime older than the run marker's started_at boot stamp) ⇒ a previous op was torn ⇒ remove the stale lock + git clean -fdx the <repo_root>/target/release_staging dir; a fresh lock (mtime ≥ boot) is PRESERVED (live git op). Best-effort + FAIL-OPEN (no lock / non-git tree / no boot stamp / any error → no-op, never blocks the marker write). It makes NO commits and never touches the run marker, so it COMPOSES with the --cycle-end friction detector without false-tripping unexpected-commits/cycle-bracket-break. On a reconciliation the JSON carries git_consistency_reconciliation: {reconciled, removed_lock, staging_cleaned, reason}. Mirrored in bug-state.py (coupled pair; audited by lazy_parity_audit.py). GUARDED (cycle-subagent-runs-orchestrator-work Phase 2): refuse_cycle_marker_mutation_if_subagent("--cycle-begin") runs FIRST — a subagent (no LAZY_ORCHESTRATOR export, marker present) is refused exit 3 with zero side effects; the orchestrator (LAZY_ORCHESTRATOR=1) is allowed its self-healing overwrite.
python3 lazy-state.py --cycle-end                          # clear the cycle marker immediately AFTER every Agent return (success/halt/error); idempotent; prints {"cycle_marker_cleared": true|false}. GUARDED (cycle-subagent-runs-orchestrator-work Phase 2): refuse_cycle_marker_mutation_if_subagent("--cycle-end") runs FIRST (before the friction check + clear) — a subagent cannot clear the marker (exit 3, zero side effects); the orchestrator clears its own bracket normally. SIDE EFFECT (hardening-blind-to-process-friction Phase 2 / D1): BEFORE clearing, runs cycle_end_friction_check() — resolves the CURRENT run identity + HEAD, calls detect_cycle_bracket_friction(), and on a torn bracket (run identity absent/changed since --cycle-begin → reason cycle-bracket-break) OR unexpected commits (HEAD advanced beyond the conservative per-sub_skill budget → reason unexpected-commits) appends a kind: process-friction entry to lazy-deny-ledger.jsonl. The runaway then self-announces as hardening debt: pending_hardening() counts it, the --emit-prompt probe withholds the forward route, and --run-end refuses — identical machinery to a guard deny. Fail-open: a degraded snapshot (no run marker / non-git tree) or a ledger-write error never blocks the clear, never false-positives. On a hit the JSON also carries process_friction: {reason, detail, ...}.
# C3 refuse-by-construction (agent_id-aware per hardening-blind-to-process-friction D4): --run-end/--run-start/--apply-pseudo/--enqueue-adhoc/--emit-dispatch REFUSE (exit 3, corrective stderr, ZERO side effects) for a SUBAGENT caller — they are orchestrator-only. refuse_if_cycle_active() decides in priority order: (1) LAZY_ORCHESTRATOR truthy → never refuse (structural immunity to a stale marker; fixes the orchestrator-self-deny defect), (2) LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal, no marker required), (3) else cycle marker present → refuse (legacy backstop carrier). The marker stays the fallback carrier because a Python subprocess cannot read the PreToolUse agent_id (hook-input-only); the C2 hook (lazy-cycle-containment.sh) uses agent_id directly. --neutralize-sentinel/--verify-ledger + all reads stay callable (a dispatched subagent needs them). The refused-op SCOPE is lockstep with the C2 PreToolUse hook deny-set (agent_id trip: recursive Agent/Task, nested /lazy-batch, LOOP_FORMATION_FLAGS routing, dev:kill/dev:restart).
# C3 marker-mutation guard (cycle-subagent-runs-orchestrator-work Phase 2, KEYSTONE): --cycle-begin/--cycle-end MUTATE the containment marker, so they CANNOT reuse refuse_if_cycle_active's marker-fallback (the orchestrator runs its OWN bracket while the marker is present — the marker can't protect itself). refuse_cycle_marker_mutation_if_subagent() guards them instead, keyed on the POSITIVE signal: (1) LAZY_ORCHESTRATOR truthy → allow (the orchestrator owns the bracket), (2) else LAZY_CYCLE_SUBAGENT truthy → refuse, (3) else cycle marker present without orchestrator env → refuse (the reachable subagent signal), (4) else (no marker, no subagent env) → allow (the genuinely-uncontained first --cycle-begin). REQUIRES the orchestrator to `export LAZY_ORCHESTRATOR=1` once per session (the three orchestrators do this at Step 0.55 before --run-start) — otherwise the orchestrator's own --cycle-end would be refused. These two ops are NOT in CYCLE_REFUSED_OPS; they ARE in the C2 hook LOOP_FORMATION_FLAGS (belt-and-suspenders) — C2/C3 deny scope stays lockstep (a subagent cannot clear/arm the marker at either layer).
```

Exit codes: `0` success (even if terminal), `2` malformed input (bad YAML/queue.json), `1` ledger/pseudo-skill failure (`--verify-ledger`/`--apply-pseudo`/`--neutralize-sentinel` not ok), `3` C3 cycle-containment refusal (an orchestrator-only op invoked while the cycle marker is present).

**Park-mode terminal — `queue-exhausted-all-parked`.** Under `--park` (i.e. `--park-needs-input` and/or `--park-blocked`), when the queue advances past every workable item and ONLY parked items remain (`current is None` with a non-empty `parked[]`), `compute_state` returns the honest distinct terminal `queue-exhausted-all-parked` — NOT `all-features-complete` / `all-bugs-fixed` (which would be a false completion). It is the fallback AFTER the specific global terminals (`cloud-queue-exhausted`, `device-queue-exhausted`, `queue-blocked-on-research`/`all-remaining-deferred`, `scoped-id-not-found`) and BEFORE all-complete. The orchestrator flushes the parked items (needs-input + blocked) before stopping. Same terminal on both `lazy-state.py` and `bug-state.py`.

## Per-repo keyed state dir (multi-repo-concurrent-runs)

All run-scoped state — the run marker, the prompt registry, the deny-ledger, the cycle-subagent
marker, and the run checkpoint — resolves its path through **one chokepoint**,
`lazy_core.claude_state_dir()`. As of the `multi-repo-concurrent-runs` feature, that chokepoint
is **scoped per repo**, so a `/lazy-batch` run in one repo neither blocks nor is blocked by a run
in another repo (it also kills stale-marker contagion across repos).

- **Resolution rule.** `LAZY_STATE_DIR` **set** → `claude_state_dir()` returns it EXACTLY (no
  keying, no migration). This is the hermetic-test + hook-pipe-test path, preserving every
  fixture's path semantics byte-for-byte. `LAZY_STATE_DIR` **unset** (production) →
  `~/.claude/state/<repo_key>/`. The 24 internal callers are unchanged — they all inherit the
  per-repo subdir for free.
- **`repo_key(repo_root)`** is the ONE canonical derivation: `sha1` of the normalized real path
  (`os.path.realpath` → forward slashes → strip trailing slash → lowercase a Windows drive
  letter). It is normalization-invariant (trailing-slash / separator / drive-case variants of the
  same path collapse to one key) and lives ONLY in Python — the bash hooks never re-derive it.
- **Active-repo binding.** The active repo is bound ONCE at each script's `main()` via
  `lazy_core.set_active_repo_root(args.repo_root)` (immediately after `parse_args()` in BOTH
  `lazy-state.py` and `bug-state.py`). `active_repo_root()` returns that binding, falling back to
  the cwd git-toplevel. A single process operates on exactly one repo, so the module-level active
  repo is unambiguous; concurrent runs in different repos are different processes with different
  subdirs and never collide. `bug-state.py` inherits the keyed dir purely by importing
  `lazy_core` — it shares a repo's subdir with the feature pipeline (mutually exclusive within a
  repo, correct: same git tree; cross-repo isolated). `lazy_parity_audit.py` asserts both scripts
  carry this binding.
- **Same-repo refusal / cross-repo concurrency.** `refuse_run_start_clobber` reads the keyed
  dir's marker raw: a live, non-stale, DIFFERENT-pipeline marker in *this* repo's subdir refuses a
  second `--run-start` (exit 3, zero side effects, naming the in-flight run). A live, non-stale,
  **SAME-pipeline** marker is ALSO refused now (exit 3, zero side effects, naming the in-flight run's
  `started_at`/`forward_cycles`) — UNLESS a `lazy-run-checkpoint.json` is present, the
  sanctioned-resume discriminator. This closes the `multi-repo-concurrent-runs`
  **same-repo / same-branch / same-pipeline** residual gap: a genuinely-concurrent second `/lazy-batch`
  walker (no checkpoint waiting) no longer silently clobbers the first walker's marker. The checkpoint
  is read NON-destructively (existence only — never `consume_run_checkpoint`, which deletes the resume
  signal the `--run-start` handler consumes LATER). A different repo is a
  different subdir → never refuses. Age-staleness (24h) makes a presumed-dead marker reclaimable (the
  age gate runs before the pipeline check, so a stale same-pipeline marker reclaims without reaching the
  new refusal). Closed by `docs/bugs/concurrent-same-branch-walkers-no-arbitration`.
- **Legacy migration.** On the first production `claude_state_dir()` resolution (env unset),
  `migrate_legacy_state_dir()` moves any legacy un-keyed base-dir files (`lazy-run-marker.json`,
  `lazy-prompt-registry.json`, `lazy-deny-ledger.jsonl`, `lazy-cycle-active.json`,
  `lazy-run-checkpoint.json`) into the keyed subdir for the marker's recorded `repo_root`, then
  removes the base copies. Idempotent (once-per-process guard); a marker with no resolvable
  `repo_root` is treated as stale and removed. It NEVER touches a `LAZY_STATE_DIR`-overridden dir.
- **Checkpoint resume is provenance-branched** (operator-checkpoint-resume-counter-reset, 2026-06-17).
  `write_run_checkpoint` records an `operator_authorized` flag (threaded from
  `args.operator_authorized` at the `--run-end --reason checkpoint` site). On `--run-start`,
  `restore_checkpoint_counters` branches on it: an **operator-authorized** checkpoint (a deliberate
  `/lazy-batch <N>` re-invoke) NO-OPs the restore → the marker keeps its by-design `0/0` (fresh
  authorized budget); a **falsy/absent** flag (automatic reliability pause, or a pre-fix checkpoint
  file) carries the paused `forward_cycles`/`meta_cycles` forward monotonically (HARD CONSTRAINT 8 —
  an auto-resume cannot silently exceed the authorized `max_cycles`). The branch lives entirely in
  the shared `lazy_core` helper, so `bug-state.py` inherits it.
- **Hooks gate via `--marker-present`.** The three enforcement hooks
  (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`, `lazy-cycle-containment.sh`) no longer read
  the base-dir marker file directly. They call `lazy-state.py --marker-present --repo-root <cwd>`
  (read-only; exit 0 present / 1 absent) so Python owns ALL repo-key derivation. A marker for a
  *different* repo resolves to a different subdir → absent → the hook is a no-op. Fail-OPEN: a
  query error falls back to current behavior. The `pipeline_visualizer` likewise binds the
  visualized repo before reading the marker so it shows that repo's live run.
  - **Owner-scoping (`stale-marker-arms-validate-deny-on-unrelated-dispatches` D1, 2026-06-19).**
    `lazy-dispatch-guard.sh` now ALSO extracts the hook-input `session_id` and passes
    `--session-id "$SID"` ALONGSIDE `--repo-root` (never in place of it — repo keying preserved)
    when non-empty. The gate then resolves PRESENT only for the marker's BOUND owning session
    (`read_run_marker` staleness path B): a same-repo NON-owner dispatch sees exit 1 → fast-path
    allow, so the gate read AGREES with the guard's own session-aware read (which already
    self-allowed a non-owner). Fail-OPEN: an empty/failed `session_id` parse omits the flag and
    degrades to the session-blind gate. The parse splits the two-line python output with bash
    builtins (`read` / `${//}`), NOT `sed`/`head` (coreutils-on-PATH hazard), and strips trailing
    `\r` from BOTH `cwd` and `session_id` (Windows git-bash text-mode stdout — a stray `\r` on the
    repo-root mangles the repo key into a different keyed subdir → spurious fast-path allow).
    NOTE: for a BOUND marker this is defense-in-depth (the guard self-allows a non-owner before
    the registry read); the residual same-repo deny surface is the UNBOUND pre-bind window (D2).
  - **Pre-bind no-debt deny (`stale-marker-arms-validate-deny-on-unrelated-dispatches` D2, 2026-06-19).**
    While a marker is live but UNBOUND (`session_id: None` — bind-pending, no orchestrator ALLOW yet),
    the D1 gate cannot owner-scope (staleness path B needs BOTH the caller and marker non-None), so the
    guard runs and an unrelated same-repo dispatch is denied. `lazy_guard.py::_deny_default(marker, …)`
    routes that GENERIC default-deny through `_deny_no_ledger` (verdict preserved, ledger append
    suppressed → `pending_hardening()` does not rise) ONLY while the marker is unbound; a deny under a
    BOUND marker still `_deny_and_ledger`s (a genuine validate-deny accrues debt as before). Scope: the
    three generic `_default_deny_reason()` sites only — the depth-1 hardening cap and the bare-`@@lazy-ref`
    unresolved deny keep their ledger semantics. Fail-OPEN: any error reading `marker.get("session_id")`
    falls back to `_deny_and_ledger` (debt-preserving). This is why pre-D2 deny tests that used an unbound
    marker had to be re-pinned to a BOUND marker to keep asserting debt accrual.
  - **Marker `work_branch` + `--marker-work-branch` query (`cycle-subagent-fabricates-policy-or-stray-branch`,
    2026-06-20).** `write_run_marker` now stamps a `work_branch` field (resolved via the existing
    `_emit_work_branch(repo_root)` at run-start; a non-git root yields its fallback string, never raises).
    Legacy markers lacking the field read as `None` via the single read helper `lazy_core.marker_work_branch()`
    (back-compat, same pattern as `attended` / `per_feature_forward_cycles`). A new read-only CLI query
    `lazy-state.py --marker-work-branch --repo-root <cwd>` (mirrored on `bug-state.py` for parity — the marker
    is shared) prints the stored branch + exit 0 when a live marker carries one, exit 1 otherwise (absent /
    stale / legacy-no-branch); read-only, never creates the state dir. Consumed by the write-time hook
    `block-sentinel-write-on-stray-branch.sh`, which denies a pipeline-sentinel Write while HEAD != the
    marker's `work_branch` (fail-OPEN on exit 1 — no known branch to enforce against). Branch identity is
    owned in this ONE helper; bash never re-derives it (same contract as `--marker-present` owning presence).
  - **Run-start owner bind + owner-side detect/re-arm (`single-slot-marker-ownership-race-disarms-owning-run`,
    2026-06-20).** The run marker's owner is a SINGLE mutable `session_id` slot, first-writer-wins. Two
    layers now keep a WRONG-session bind from silently disarming the true owner's dispatch guard (the
    under-fire race — the owner reading `None` from staleness path B can't tell "no run" from "my run,
    foreign-stamped"):
    - **Born owner-bound (Phase 1 — the primary fix).** Both `--run-start` handlers now thread
      `session_id=args.session_id` into `write_run_marker`, so the marker is born stamped with the
      orchestrator's KNOWN owning session — never bind-pending. A foreign session can no longer be the
      first writer of the slot (it was never `None`), so `bind_marker_session`'s first-writer-wins
      protection now protects the CORRECT owner from run-start. This ELIMINATES the bind-pending window
      at its source — closing both Repro A (pre-allow bind race) and Repro B (checkpoint-resume re-bind;
      the resume is itself a `--run-start` carrying `--session-id`). Backward-compatible: a `--run-start`
      WITHOUT `--session-id` (legacy/manual) still writes `session_id: None` and falls back to the
      unchanged `_bind_marker_on_allow` anchor in `lazy_guard.py` (now a confirming idempotent no-op on
      the bound normal path, retained for the legacy path). Coupled-pair edit — `lazy-state.py` +
      `bug-state.py`, the marker is shared.
    - **Owner detect + re-arm backstop (Phase 2 — for the legacy/un-threaded paths).**
      `lazy_core.marker_owner_status(session_id, *, now=None) -> "absent" | "owned-by-me" | "foreign-stamped"`
      is a NON-DESTRUCTIVE three-way detect: it reuses `read_run_marker`'s age/corrupt rules for
      `absent` (delegating with NO session_id so path B never fires) but does NOT delete on a session
      mismatch — it reports `foreign-stamped` instead of collapsing to `None`, making "no run" and
      "wrong-stamped run" DISTINGUISHABLE. `owned-by-me` = bind-pending (`None`) OR equal session.
      HARD: `marker_owner_status` MUST stay non-destructive on `foreign-stamped` — deleting there
      re-introduces the 2026-06-12 ~14:53Z silent-disarm-by-delete. `lazy_core.reassert_marker_owner(session_id, *, now=None)`
      atomically re-stamps a `foreign-stamped` slot to the caller (returns True) and is a no-op on
      `absent` / `owned-by-me` (returns False, idempotent) — the owner re-claiming its own run's guard.
      It is exposed ONLY via the orchestrator-only `--reassert-owner` CLI action (requires `--session-id`,
      prints `{reasserted, prior_status}`), gated by `refuse_if_cycle_active("--reassert-owner")` FIRST
      (a cycle subagent → exit 3, zero side effects, the same contract as `--run-start` / `--reorder-queue`).
      Coupled pair on both scripts (the marker is shared; parity-guarded by
      `lazy_parity_audit.py::audit_state_script_parity`'s `--reassert-owner` check). See
      `docs/bugs/single-slot-marker-ownership-race-disarms-owning-run`.

## Cycle-counter advance: two orthogonal triggers (lazy-batch-unified-driver-parity-and-accounting Phase 1)

The run marker's `forward_cycles` / `meta_cycles` budget counters advance via **two
independent triggers**, both marker-gated:

1. **Consume-oracle advance — `advance_run_counters(state)`** (the pre-existing path). Advances
   ONLY when the registry consume-count rose since the marker's `last_advance_consume_count`
   watermark — i.e. a real Agent dispatch landed (one guard ALLOW = one consume). A bare
   probe/inject re-fire with no intervening dispatch is a no-op. This is the F2-debounce that
   fixed the ISSUE-5 forward-cycle inflation.
2. **State-change advance — `advance_forward_cycle(state)`** (Fix-A, item 1). Advances when the
   `[feature_id, current_step, sub_skill]` tuple DIFFERS from the marker's `last_advance_state_key`
   field — **independent of the consume oracle**. This covers the cycles trigger (1) misses:
   forward-advancing inline **pseudo-skills** (`--apply-pseudo __mark_*__` / `__write_validated_*`
   / `__grant_skip_no_mcp_surface__` / `__flip_plan_complete_cloud_saturated__`) dispatch no Agent
   and consume nothing, and a verbatim real-skill dispatch can miss its guard ALLOW (Theory-1b).
   A re-fire with the SAME tuple is a no-op (idempotent, same as trigger 1's consume gate).
   As of `byref-dispatch-undercounts-forward-cycles` Phase 1 this trigger is ALSO the authoritative
   forward-advance on the `--repeat-count` **real-skill probe path** — where it REPLACED the
   consume-gated `advance_run_counters` (form-1 reconciliation; `advance_run_counters` no longer
   runs there). That moves the real-skill forward COUNT off the non-monotonic `consumed_emission_count()`
   oracle entirely, so a by-ref dispatch whose consume the ring-capped census no longer reflects (the
   "stuck at 16 / frozen at 50" freeze) still advances. Do NOT re-introduce a forward-advance
   dependence on the consume oracle on this path.

**Classifier** (`_FORWARD_ADVANCING_PSEUDO_SKILLS`, the SSOT frozenset): a real (non-`__`)
sub_skill OR a `__`-prefixed pseudo-skill IN that set → `forward_cycles`; any other `__`-prefixed
or falsy sub_skill → `meta_cycles`. **Marker fields:** `last_advance_consume_count` (trigger 1
watermark) and `last_advance_state_key` (trigger 2 tuple, a JSON list; legacy markers lack it →
defaults to None → first state change always advances). The state-change advance is wired into BOTH
the `lazy-state.py --apply-pseudo` handler AND the `--repeat-count` real-skill probe path (both
fail-open); `bug-state.py` mirrors the `--repeat-count` site (audited by `lazy_parity_audit.py`).
Shared `lazy_core`, so `bug-state.py` inherits the helper too.

> **Watermark hardening (`byref-dispatch-undercounts-forward-cycles` Phase 2).** The residual
> consume-watermark consumers (`advance_run_counters`'s `last_advance_consume_count` gate,
> `advance_meta_cycle`'s `+1` over-absorb) are now CLAMPED against the non-monotonic oracle: when
> the live census steps DOWN below the persisted watermark (ring-cap eviction of consumed entries),
> the gate re-arms (advances once) instead of no-oping forever, so eviction can no longer permanently
> strand it. The clamp preserves the ISSUE-5 inflation no-op (a bare re-probe with no census change
> still no-ops). Since Phase 1 moved the forward COUNT off this oracle entirely, the clamp is
> defense-in-depth for any remaining watermark consumer.

## `step_repeat_count` reset paths: the resolution-aware reset (loop-detected-false-positives-from-probe-and-reboot-churn)

`update_repeat_counts`'s HEAD-blind `step_repeat_count` (the Phase-10 oscillation counter, keyed
on `(feature_id, current_step)`) resets to 1 on exactly **three** "genuine forward progress" paths
— never a HEAD/commit reset (that immunity is the d8 commit-masked-oscillation design constraint):

1. **Step-signature change** — `(feature_id, current_step)` differs from the prior probe.
2. **Ordered-advance exemption** — step signature unchanged but `sub_skill_args` advanced (a
   multi-part `/execute-plan` marching plan parts while staying on `Step 7a: execute plan`).
3. **Resolution-aware reset** (symptom 3) — the prior cycle was a needs-input RESOLUTION at this
   exact step signature. A resolution meta-cycle is itself an Agent dispatch (it consumes a nonce),
   which DEFEATS the F2 double-probe debounce's "no dispatch between the probes" precondition — so
   without this branch the counter would survive a *legitimately-resolved* blocker and false-trip
   LOOP-DETECTED. The discriminator is a **persisted, deterministic** marker field
   `last_resolution_step_key = [feature_id, current_step]` (⚖ D7: a recorded signal, NOT racy
   probe-time inference), written by `lazy_core.record_resolution_signal(state)` at the
   apply-resolution dispatch bracket and read-and-cleared by `lazy_core._consume_resolution_signal`
   inside `update_repeat_counts`. **ONE-SHOT** (consumed-and-cleared → fires once across the
   resolution, never latches), **repo-scoped** (a foreign-repo marker never matches, like the F2
   oracle), **marker-gated + legacy-tolerant** (a missing/legacy/foreign signal → no reset), and
   **`peek`-safe** (peek does a read-only check, never mutating the marker). It is
   `step_repeat_count`-ONLY: the HEAD-aware `repeat_count` already resets on its own when a
   resolution commits, and a non-committing resolution is correctly governed by its existing
   F1/HEAD logic — NO `repeat_count` reset was added (Open Question 2 resolved).

**Signal-production wiring:** the orchestrator-only CLI action `--record-resolution-signal
--feature-id <id> --current-step <step>` on `lazy-state.py` (mirrored as `--bug-id` on
`bug-state.py`) calls `record_resolution_signal`. `/lazy-batch` and `/lazy-bug-batch` Step 1g
(apply-resolution bracket) invoke it after the resolution subagent neutralizes the sentinel — a
COUPLED-PAIR lockstep edit (audited by `lazy_parity_audit.py`, NOT a divergence).

## Verification-only canonical marker (harness-hardening-retro-fixes Phase 2)

`remaining_unchecked_are_verification_only(phases_text)` decides whether the only remaining
unchecked `- [ ]` rows are runtime-verification rows owned by the Step-9 `/mcp-test` gate (so
`/lazy` falls through to the MCP gate instead of looping on write-plan). It used to detect
those rows by **matching the subsection header's free text** against `_VERIFICATION_SECTION_RE`
— a growing regex that gapped the gate every time a producer used a novel header phrasing (two
consecutive hardening rounds each grew it).

It now keys off a **structural canonical marker**, the SSOT constant
`lazy_core:_VERIFICATION_ONLY_MARKER = "<!-- verification-only -->"` (a per-row HTML comment,
invisible in rendered markdown; Open Question 2 resolved toward the per-row form for
header-text-independent robustness). A `- [ ]` row is verification-exempt when the row OR its
enclosing subsection header carries the marker — independent of the header free text, so a
never-before-seen verification header no longer gaps the gate.

- **Producers emit the marker.** `_components/phases-runtime-verification.md` (via `/spec-phases`)
  and `_components/blocked-resolution.md` (via `/blocked-resolution` seam-audit / RV rows) author
  the marker right after each verification checkbox, referencing the SSOT constant **by name** —
  never re-hardcoding a divergent string. A lockstep test
  (`test_ruvonly_marker_lockstep_producers_match_ssot`) asserts producer prose == the constant.
- **`_VERIFICATION_SECTION_RE` is now a deprecation shim.** It is retained ONLY so un-migrated
  PHASES.md (rows under a recognized header but WITHOUT the marker) keep exempting cleanly — no
  regression. But when the regex (and not a marker) is what exempts a row, the shim appends a
  `_DIAGNOSTICS` warning naming the un-migrated subsection, surfacing the migration gap (does NOT
  silently pass). A future cycle retires the regex once the shim stops firing across all live
  PHASES.md. New verification-subsection conventions should rely on the marker, NOT grow the regex.
- **check-docs-consistency.ts:** the marker is a ROW ANNOTATION, not a sentinel, so it does NOT
  enter that script's `SENTINEL_SCHEMAS`. If a future edit there cannot validate the HTML-comment
  form cleanly, fall back to a canonical subsection-header form and re-sync the constant + both
  producers (documented in the constant's docstring).

### Evidence-gated completion exemption + auto-tick (completion-coherence-gate-reconciliation)

The MID-feature gate (`remaining_unchecked_are_verification_only`) exempts verification rows so
`/lazy` falls through to `/mcp-test`. The COMPLETION-time gate (`_phase_completion_plan` inside
`__mark_complete__` / `__mark_fixed__`) historically did NOT — it counted verification rows as
blocking refusals, so a fully-validated feature was refused at the finish line over un-ticked
verification checkboxes, forcing a redundant coherence-recovery meta-cycle. This feature reconciled
the two by treating on-disk `/mcp-test` evidence as authoritative for ticking the rows it certifies.

- **`evaluate_completion_evidence(feature_dir, repo_root) -> {verdict, reason, pass_count,
  validated_commit}`** — pure, side-effect-free read of the on-disk receipts implementing the SPEC's
  authoritative-evidence decision table. `verdict ∈ {exempt-and-tick, warn-exempt, refuse}` (a LOCKED
  contract). Requires the UNION of `VALIDATED.md` (`kind: validated`) AND `MCP_TEST_RESULTS.md`
  (`result: all-passing`, `pass==total`, `pass>0`); `validated_commit == HEAD` exact. Forged
  attestation (VALIDATED.md without passing results), missing VSA (results without VALIDATED.md),
  `SKIP_MCP_TEST.md` / `DEFERRED_*` (fail-closed, no override path this cycle), zero-test
  (`pass==total==0`), and source/script HEAD-drift (`validated_commit != HEAD` with any non-`*.md`
  delta — TOCTOU) all **refuse**. Docs-only (`*.md`) HEAD-drift → **warn-exempt**.
- **`autotick_verification_rows(phases_path, validated_commit, pass_count) -> {ticked_count, ok,
  reason}`** — atomic (`_atomic_write`), line-anchored + code-fence-safe (`_UNCHECKED_ROW_RE` +
  `_VERIFICATION_ONLY_MARKER`, row- or header-scope), audited (each row gets a byte-stable
  `<!-- auto-ticked: validated_commit=<sha> -->` comment via `_AUTOTICK_COMMENT_PREFIX`), Superseded-
  aware, idempotent (a row already carrying the audit comment is skipped). **Cardinality lock**:
  `ticked_count > pass_count` ABORTS writing nothing (`ok: False`) — the over-tick guard then surfaces
  as a coherence refusal at the live gate.
- **Wiring (load-bearing ORDER — tick → re-check → receipt):** the `__mark_complete__` /
  `__mark_fixed__` handler consults `evaluate_completion_evidence` BEFORE the coherence gate; on an
  authorizing verdict it runs `autotick_verification_rows` FIRST, then re-parses PHASES.md, so the
  residual-incoherence check sees ZERO unchecked verification rows. A genuine unchecked
  *implementation* row (no marker) is NOT auto-ticked, so the gate still refuses naming its phase —
  evidence, not the checkbox, is the source of truth. The auto-ticked count is recorded as
  `auto_ticked_rows` in the `COMPLETED.md` / `FIXED.md` receipt AND surfaced in the `--apply-pseudo`
  JSON result alongside `flipped_phases`.
- **Kill-switch (`_evidence_gate_killed`):** when `LAZY_STRICT_EVIDENCE_GATE` OR
  `LAZY_DISABLE_AUTOTICK` is set to a truthy value (an explicitly-falsy `""`/`0`/`false`/`no`/`off`
  does NOT arm it), the auto-tick is skipped entirely and the coherence gate falls back to the legacy
  strict path (verification rows INCLUDED in refusals, zero PHASES.md mutation) — frictionless
  rollback without a code revert.
- **No sibling-repo edit:** the exhaustive auto-tick normalization leaves PHASES.md fully coherent
  (every box `- [x]` or under a Superseded phase), so AlgoBooth's `check-docs-consistency.ts` (which
  counts every checkbox with no carve-out, post-flip under a Complete SPEC) is satisfied with no
  edit — it evaluates physical `- [x]` state, not semantic intent.

## mcp-test model-tier routing (harness-hardening-retro-fixes Phase 4)

`surface_resolver.py` owns the **script-derived mcp-test model-tier signal** via
`route_mcp_test_tier(scenario_path, prior_verdict=None, yaml_exists=None) -> "haiku" | "sonnet"`
— a pure function (the only I/O is an optional existence check when `yaml_exists is None`). It
re-scopes the mcp-test haiku tier so haiku handles ONLY ready-to-run converted-YAML happy paths;
scenario authoring, first-run `.md`→YAML conversion, and diagnosis cycles route to **Sonnet by
default — not by a per-run orchestrator override**. Sonnet-forcing conditions (any one): (1) legacy
`.md` with no converted `corpus/live/*.yaml` counterpart; (2) non-definitive prior verdict (anything
outside the `_DEFINITIVE_MCP_VERDICTS` allow-list — an unknown label fails safe toward Sonnet);
(3) no scenario at all. `repos/algobooth/.claude/skills/mcp-test/SKILL.md`'s Model-tier section
consults this helper (repo-scoped prose — not a coupled pair, but picked up by `project-skills.py`
per-repo projection; re-run it after editing).

`emit_cycle_prompt` ALSO consults `route_mcp_test_tier` on the AUTONOMOUS cycle-model path
(docs/bugs/mcp-test-legacy-md-routes-to-haiku) — closing the SPEC's "wired into zero autonomous
paths" gap. The dispatch model is bound by the orchestrator BEFORE the cycle subagent resolves its
scenario, so a literal haiku here lands an unconverted legacy `.md` scenario on haiku, which BLOCKs
(can't author the `.md`→YAML conversion). The `_mcp_test_cycle_model(spec_path)` helper applies
**option-(b) conservative escalation**: it enumerates the item's candidate scenarios under the
resolved spec/bug dir (`mcp-tests/*.md` legacy + `corpus/live/*.yaml` converted, recursively) and
stays haiku ONLY when at least one candidate resolves AND every candidate is a ready converted YAML;
otherwise — including zero resolvable candidates or any enumeration error — it escalates to sonnet
(matching the router's own "unknown → Sonnet" bias, never a silent haiku fallback). This realizes
the Phase-4 intent (tier routing "by default — not by a per-run orchestrator override") on the batch
path; `bug-state.py` inherits it via the shared `lazy_core`. Tests:
`test_surface_resolver.py::TestRouteMcpTestTier`;
`test_lazy_core.py::test_emit_cycle_prompt_mcp_test_legacy_md_escalates_sonnet` +
`..._ready_yaml_stays_haiku` + `..._cycle_model_haiku` (reshaped to a ready-YAML happy path).

## Concurrency plane (Phase 4 — `lazy_coord.py` + scoping flags)

The concurrency plane lets multiple `lazy-worker` sessions run different queue items at once
without corrupting shared state. **All shared-state mutation goes through one writer under a
global lock** — this is the load-bearing invariant; violating it corrupts `leases.json` /
`queue.json` / `materialized.json`.

- **Global lock = `os.mkdir(<COG_DOCS>/docs/work/global.lock.d)`** — atomic on NTFS. Acquire =
  mkdir succeeds; `FileExistsError` = held → exponential backoff until timeout → `TimeoutError`.
  Release = `os.rmdir`. **Never `fcntl`/`flock`/`LockFileEx`/`msvcrt`.** The lock is **NOT
  re-entrant** — never call one public locked function from inside another (reclamation inside
  `acquire_lease` uses a private inline helper, not the public `reclaim_expired`).
- **Every `leases.json` write happens under the lock and via atomic temp-file `os.replace`**
  (`acquire_lease` / `heartbeat` / `reclaim_expired` / `release_lease`). `verify_fencing` is the
  only read-only op (no lock).
- **Fencing tokens prevent zombie writes.** `acquire_lease` increments `term_token` per claim and
  returns it; the worker carries that token and `verify_fencing(expected_token=term_token)` BEFORE
  every `queue.json` transition. A superseded worker raises `FencingError` and must abort.
- **`leases.json` LOCKED schema** (per entry, keyed `str(wi_id)`):
  `{worker_pid:int, worktree_slot:str, term_token:int, heartbeat_timestamp:<ISO-8601 UTC 'Z'>, ttl_seconds:int}`.
- **Time is injected** (`now` epoch float, default `time.time()`) so `--test` reclamation is deterministic.
- **Scoping flags:** `lazy-state.py --feature-id <slug>` and `bug-state.py --bug-id <id>` restrict
  `compute_state()` to a single queue item. Both are **opt-in and backward-compatible** — absent the
  flag, behavior is byte-identical to single-current (guarded by the `baseline-regression-default`
  smoke fixtures). The new params are **appended** to `compute_state()` (positional callers unbroken).
- **Worktree pool:** `provision_pool` adds `pool/wt-NN` worktrees on the cognito repo and applies
  `gc.auto 0` / `core.filemode false` / `core.autocrlf input`; `scrub_slot` runs the exact
  ordered reset (rm `index.lock` → `fetch` under lock → `checkout --detach origin/main` →
  `reset --hard` → `clean -fdx` → `checkout -b p/<wi_id>-<slug>`; **no submodule step**).
- **Gate:** `python lazy_coord.py --test` (5 fixtures). Because the scoping flags touch both state
  machines' shared import surface, run the FULL set after any change here: `lazy_coord.py --test`,
  `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`.

> **PR shepherding (Phase 5) is DEFERRED.** `lazy-worker` opens the PR and stops — it never polls
> CI, auto-replies to comments, or auto-merges.

## Coupling Rule (HARD REQUIREMENT)

When the state machine changes:

1. **Change `lazy-state.py` first** — it is the single source of truth.
2. **Keep the paired wrappers in sync** — at minimum `lazy` and `lazy-cloud` (they share a
   dispatch contract); update `lazy-batch`/`-cloud` if the terminal set changes.
3. **Keep `--test` green.** The in-file smoke harness (~30 fixtures) is the regression net.
   Run `python3 lazy-state.py --test` after every change; add a fixture for every new
   state branch.
4. **Keep schemas in lockstep** — `_components/sentinel-frontmatter.md` ↔
   `check-docs-consistency.ts` (features) / `check-bugs-consistency.ts` (bugs) ↔ these
   scripts' sentinel readers (`lazy_core.py`).

## Testing

`lazy-state.py --test` and `bug-state.py --test` build temp-dir fixtures and assert the
computed state. They are the only fast, hermetic check for state-machine correctness — **a
refactor that keeps `--test` green has preserved behavior.** Because both scripts share
`lazy_core.py`, any change there MUST keep BOTH suites green. Each `--test` output is
byte-pinned: `lazy-state.py --test` to `tests/baselines/lazy-state-test-baseline.txt` and
`bug-state.py --test` to `tests/baselines/bug-state-test-baseline.txt`, compared via the
shared **cross-platform** `_normalize_smoke_output` helper in `test_lazy_core.py` — it
canonicalizes the per-run `tempfile` suffix, the OS temp-root, and `\`-vs-`/` separators, so
the committed baselines are platform-neutral across Windows and WSL (regenerate a baseline ONLY
by piping live `--test` output through that helper, never by hand). `test_lazy_core.py`
characterizes the shared helpers directly. Green smoke tests are the acceptance gate before
touching anything downstream.

## Related

- `plans/lazy-bug-family.md` — implementation plan for the bug-side pipeline.
- AlgoBooth `docs/features/CLAUDE.md` — the file contracts the script consumes.
- AlgoBooth `docs/bugs/CLAUDE.md` — bug-doc conventions (being aligned to the above).
- `user/skills/lazy/SKILL.md` — the canonical wrapper, fully commented.
