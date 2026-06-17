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
python3 lazy-state.py --enqueue-adhoc …     # prepend an ad-hoc item to the queue. --type {feature,bug} (default feature; unified-pipeline-orchestrator Phase 3) selects the destination pipeline: feature → docs/features/queue.json (unchanged); bug → docs/bugs/queue.json via the EXISTING bug-state.py enqueue (enqueue_adhoc_bug() seeds docs/bugs/<slug>/ around the subprocess — NOT a reimplementation). bug-state.py --enqueue-adhoc accepts a benign --type bug so the documented unified form parses.
python3 lazy-state.py --next-merged          # unified-pipeline-orchestrator Phase 1: print the head of the MERGED feature+bug work-list as JSON {item_id, type, repo_root} (or null when both queues empty). Read-only ORDERING ONLY — reuses load_queue (features) + bug-state.load_bug_queue (bugs, via importlib) and the lazy_core ordering helper; NEVER re-infers per-item state (the unified driver still calls --probe/--emit-prompt per item). Normalizes the two queues' divergent ordering fields (feature `tier` int / bug `severity` P0..Low) to one effective-priority scale (lower = higher priority); equal priority → bug before feature; stable within each queue. Binds the active repo before reading. Shared impl: lazy_core.merged_priority/merged_worklist/next_merged.
python3 lazy-state.py --backfill-receipts   # grandfather pre-gate completions
python3 lazy-state.py --test                # run the in-file fixture smoke tests
# --- Phase 5 orchestrator-loop subcommands (shared impl in lazy_core.py; same flags on bug-state.py) ---
python3 lazy-state.py --verify-ledger <spec_path> [--plan <plan_part>]  # completion-ledger gate as JSON {ok, failing_check, checks:{clean_tree, head_matches_origin, plan_complete, deliverables_done}, deliverables_source}; exit 1 iff not ok. Replaces the 5 duplicated prose ledger blocks. deliverables_done exempts verification-only rows. SOURCE OF TRUTH (2026-06-15, d8-effect-chains review): with --plan, deliverables_done reads the PLAN PART's own `- [ ] WU-N` checkboxes (machine record since write-plan ISSUE-6), NOT PHASES.md phase-level rows — eliminating cross-part + cross-phase-attribution false-fails. A legacy plan with no per-WU rows falls back to PHASES-phase-level and reports deliverables_source: "phases-fallback …". Without --plan: whole-feature PHASES.md (deliverables_source: "phases-feature-level").
python3 lazy-state.py --apply-pseudo <name> <spec_path>    # SINGLE author of the deterministic pseudo-skill writes: __write_validated_from_{skip,results}__, __write_deferred_non_cloud__, __flip_plan_complete_cloud_saturated__ (pass --plan), __mark_complete__/__mark_fixed__ (receipt + SPEC/PHASES status flip + sentinel cleanup). Idempotent; refuses when gate inputs absent. __write_validated_from_results__ additionally gates on kind: mcp-test-results + result: all-passing + pass_count == total_count + validated_commit == current HEAD (legacy field-less files pass with a warnings[] entry) — NEVER hand-write VALIDATED.md. Optional: --plan/--apply-date/--reason/--deferred-step. (ROADMAP strikethrough + __flip_plan_complete_stale__ stay orchestrator-inline.)
python3 lazy-state.py --neutralize-sentinel <path>         # rename a resolved sentinel to <stem>_RESOLVED_<date><ext>, collision-safe (numeric suffix, never clobbers)
python3 lazy-state.py --repeat-count                       # fold a repeat_count field (consecutive identical-probe count, per-repo OS-temp signature file) into the probe JSON for mechanical loop detection; byte-identical default without the flag; folds/advances marker-persisted forward_cycles/meta_cycles counters when a run marker is present
python3 lazy-state.py --probe --forward-cycles N --meta-cycles M --max-cycles K  # fold git_guards (clean_tree/head_matches_origin/unpushed) + a pre-formatted cycle_header line into the probe JSON; byte-identical default without the flag; --repeat-count-peek reads marker-persisted counters without advancing them
python3 lazy-state.py --run-start                          # write the run marker to the state dir (pipeline=feature); gates registry writes and counter advances for this run; uses --cloud, --repo-root, --max-cycles when present; prints marker JSON and exits
python3 lazy-state.py --run-end                            # delete the run marker and the prompt registry from the state dir; call on every terminal run path; prints {"run_marker_deleted": true|false} and exits
# --- lazy-cycle-containment C1/C3 (cycle-subagent marker; same flags on bug-state.py, which uses --bug-id) ---
python3 lazy-state.py --cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]  # write the cycle-subagent marker (lazy-cycle-active.json, sibling of the run marker) immediately BEFORE every Agent dispatch; self-healing (overwrites a stale marker + logs); prints marker JSON. The marker carries feature_id/nonce/kind/started_at/session_id/commit_tally + (hardening-blind-to-process-friction Phase 2, additive) run_started_at (the live run marker's started_at snapshot — the stable run identity; null when no run is live) and begin_head_sha (git rev-parse HEAD snapshot; null on a non-git tree). These two power the --cycle-end process-friction detector. GUARDED (cycle-subagent-runs-orchestrator-work Phase 2): refuse_cycle_marker_mutation_if_subagent("--cycle-begin") runs FIRST — a subagent (no LAZY_ORCHESTRATOR export, marker present) is refused exit 3 with zero side effects; the orchestrator (LAZY_ORCHESTRATOR=1) is allowed its self-healing overwrite.
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
  second `--run-start` (exit 3, zero side effects, naming the in-flight run). A different repo is a
  different subdir → never refuses. Age-staleness (24h) makes a presumed-dead marker reclaimable.
- **Legacy migration.** On the first production `claude_state_dir()` resolution (env unset),
  `migrate_legacy_state_dir()` moves any legacy un-keyed base-dir files (`lazy-run-marker.json`,
  `lazy-prompt-registry.json`, `lazy-deny-ledger.jsonl`, `lazy-cycle-active.json`,
  `lazy-run-checkpoint.json`) into the keyed subdir for the marker's recorded `repo_root`, then
  removes the base copies. Idempotent (once-per-process guard); a marker with no resolvable
  `repo_root` is treated as stale and removed. It NEVER touches a `LAZY_STATE_DIR`-overridden dir.
- **Hooks gate via `--marker-present`.** The three enforcement hooks
  (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`, `lazy-cycle-containment.sh`) no longer read
  the base-dir marker file directly. They call `lazy-state.py --marker-present --repo-root <cwd>`
  (read-only; exit 0 present / 1 absent) so Python owns ALL repo-key derivation. A marker for a
  *different* repo resolves to a different subdir → absent → the hook is a no-op. Fail-OPEN: a
  query error falls back to current behavior. The `pipeline_visualizer` likewise binds the
  visualized repo before reading the marker so it shows that repo's live run.

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
