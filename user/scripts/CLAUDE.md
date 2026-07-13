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
| `lazy_coord.py` | **Concurrency plane** (Phase 4; generalized by `parallel-worktree-batch-execution`) — net-new, **kept separate from `lazy_core.py`** (stdlib-only; MUST NOT import `lazy_core` — its lanes.json writer carries its own temp+`os.replace` atomic write, a documented justified duplication of `_atomic_write`). `os.mkdir` global lock (**stale-holder reclamation, `coord-lock-no-stale-reclaim`:** a successful `mkdir` writes `owner.json` `{pid, kernel_start_time, acquired_at}` into the lock dir via write-temp-then-`os.replace` — the `_write_leases` pattern; a losing `mkdir` reclaims via atomic rename-then-`shutil.rmtree` ONLY on a CONFIRMED-dead holder (`_confirmed_dead_owner`: the recorded pid no longer exists, OR is alive but its live `kernel_start_time` mismatches the recorded one — pid reuse), mirroring the build-queue `active.lock` precedent (`Get-ActiveLockStatusFromText`/`Test-ShouldReclaimLock`: an unreadable pid is `'unknown'`, never `'dead'`). A metadata-less lock (crashed between `mkdir` and the metadata write) reclaims only past a bounded grace age (dir mtime, default 2.0s) — inside the grace window it is ambiguous, not stale. `kernel_start_time` is DUPLICATED from `lazy_core.py` (same policy as `_current_head`'s documented duplication) since this module must not import `lazy_core`. A genuinely live/ambiguous lock still raises `TimeoutError` within the unchanged timeout/backoff budget — no caller signature changes.) + fencing-token leases (`leases.json`, with a sibling `lease-token-watermarks.json` preserving per-item `term_token` monotonicity ACROSS reclamation/release — the zombie-lane fix), heartbeat, expiry reclamation, worktree-pool provisioning + scrub-to-clean (now repo-agnostic: `repo_root` param, `branch_template=`/`detach_target=` kwargs with byte-identical Cognito defaults), plus the **parallel-lane layer**: `claim_shardable` (conservative D3 predicate over caller-computed dep-ready/independent booleans + the live-lease rail), the `lanes.json` lane ledger (`ledger_record_claim/_lane_complete/_merge/_demotion/_park`, `read_lanes`), `merge_order` (deterministic queue-order), `merge_lane_branch` (abort-and-demote, lane branch preserved), `flush_summary`, `effective_lanes`/`lane_budget_slice` (D6 arithmetic), `lane_branch`/`lane_pool_dir` (lane conventions: `lane/<item-id>`, sibling `<repo_root>-lanes/wt-NN`). Consumed by the `lazy-worker` and `/lazy-batch-parallel` skills. In-file `--test` smoke harness (21 fixtures). See "Concurrency plane — sanctioned parallel worktree lanes" below. |
| `toolify-miner.py` | **Offline toolification miner** (unified-pipeline-orchestrator Phase 4) — stdlib-only, **READ-ONLY over logs**. Parses `~/.claude/projects/**/*.jsonl` (+ `subagents/agent-*.jsonl`), normalizes orchestrator tool-call sequences into argument-shape signatures (values elided), ranks by `occurrences × est_tokens_per_occurrence`, and applies the **deterministic-only bar** (above-bar iff deterministic AND repeated ≥2 runs AND token-heavy). Emits markdown + JSON. NEVER mutates logs (every test hashes the fixture log dir before/after). The miner *proposes* — promotion to a real subcommand is deliberate. Tests: `test_toolify_miner.py`. Doc/schema/checklist: `docs/features/unified-pipeline-orchestrator/toolify-bar.md`. Not part of the lazy state machine — a standalone analysis tool. Each candidate carries a stable `candidate_id` (= `sha256(signature)[:12]`, toolify-auto-promotion D2-A) in both renders — the promotion ledger's key. |
| `toolify-promote.py` | **Toolify materializer + promotion ledger** (toolify-auto-promotion) — stdlib-only sibling of the miner; ALL write paths of the toolification framework live here (the miner stays READ-ONLY, D1-B). `--promote <candidate_id> --id <slug> --name "<title>" [--repo-root PATH] [--from-json report.json] [--force --reason "…"]` verifies the candidate is above-bar (RECOMPUTED from the miner's constants, never trusted from a stale report; refusals name the failed predicate — judgment / run-count / score), dedups against the central git-tracked ledger `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` (D7-B: `promoted` is a hard refusal; `declined` re-promotes only with `--force --reason`, recorded `forced: true`; below-bar is refused unconditionally — `--force` never bypasses the bar), then materializes failure-safe: (1) shells `lazy-state.py --enqueue-adhoc … --tier 2 --stub --at tail` (single queue author — never hand-edits queue.json), (2) writes the stub SPEC.md whose template emits the canonical in-SPEC stub markers `_spec_text_has_stub_marker` matches (D5 — the item halts at `/spec` Step 4.5 interactive baseline-lock; auto-draft ≠ approval; round-trip-tested against the REAL detector), (3) appends the ledger entry LAST (a SPEC-write failure exits 1 leaving a routable ADHOC_BRIEF item and NO ledger entry; the re-run hits the loud duplicate-id enqueue refusal). `--decline <cid> --reason "…"` records a deliberate decline; `--status` marks each fresh above-bar candidate NEW / promoted → id / declined (reason) / `shipped` (DERIVED at read time from the target repo's `docs/features/<feature_id>/COMPLETED.md` receipt — never stored, so it can never contradict the receipt gate); `--acceptance-report` is REPORT-ONLY (D8-A: totals, acceptance rate, cohort score/run distributions, SAMPLE SIZES always named, undecided-NEW resurface — the bar's constants are tuned only by a deliberate human edit to `toolify-miner.py`). Naming stays human (D10): `--id`/`--name` are required operator inputs (a candidate the operator cannot name is a mining artifact). `/lazy-batch-retro` Step 6d resurfaces NEW rows report-only (D3-A) and NEVER invokes this script. Tests: `test_toolify_promote.py`. |
| `skill-usage-miner.py` | **Offline skill-usage miner + dead-weight audit** (skill-usage-miner feature) — stdlib-only, **READ-ONLY over logs AND both skills trees**. Sibling of `toolify-miner.py` (imports its `_iter_log_files` corpus walk; own value-preserving extractor). Joins the skill inventory (`user/skills/*/SKILL.md` + `repos/*/.claude/skills/*/SKILL.md`, keyed by DIR name — the invocation identity) against TWO detectors counted separately: assistant `tool_use` `name=="Skill"` (incl. `subagents/agent-*.jsonl`, attributed to the parent session) and the `<command-name>(/[\w:-]+)</command-name>` user-turn marker (regex verbatim from `mine-sessions/scripts/digest_sessions.py:125`). Report sections: ranked usage table (30d recency anchored to the NEWEST corpus timestamp — byte-stable), age-gated `## Never invoked` (git first-commit date vs the observation floor) with ready-to-review D8 archival proposal blocks (`git mv` + `archived/CLAUDE.md` row — NEVER executed), `## Hygiene` (stray files, dangling symlinks, case-variant `skill.md`, missing/mismatched frontmatter), annotate-only `## Toolify candidates` (cross-links `toolify-bar.md`; `TOOLIFY_CANDIDATE_THRESHOLD`), `## Unknown invocations`, standing `## Caveats` (component-injection / auto-invoke / cloud false negatives; zero = investigate, never proof of deadness). `--logs` / `--repo-root` / `--since` / `--markdown` / `--json` (both when neither) / `--out`. On-demand only (D6) — never on the state-script compute path. Tests: `test_skill_usage_miner.py` (two-tree read-only hash test). |
| `phases-slice.py` | **Deterministic scoped PHASES.md reader** (phases-slice-scoped-reads) — stdlib-only, pure read, UTF-8-safe. Prints phase index (heading, line range, `**Status:**`, checkbox tally) + the requested/active phase slice + the sibling `IMPLEMENTATION_NOTES.md` section index. `--phase <id>` (repeatable) / `--index-only` / `--checklist` / `--notes <id>\|all` / `--no-preamble` / `--preamble-line-chars`. Replaces the ignored-in-the-field grep-then-ranged-Read choreography in `source-reread.md` + `/execute-plan` (mined evidence: post-mandate sessions still read 43–65KB PHASES.md files whole). Phase boundary = `lazy_core._PHASE_HEADING_RE`, copied byte-identically — keep in sync if the canonical regex ever changes. Exit 0 ok / 1 file error / 2 phase-not-found. Tests: `test_phases_slice.py`. |
| `claude-bash-env.sh` | Restores `node`/`cargo` onto PATH for Claude Code's non-login Bash (sourced via `BASH_ENV`). Unrelated to the pipeline. |
| `doc-drift-lint.py` | **Doc-drift linter** (doc-drift-linter). Pure-read, stdlib-only sibling of `lint-skills.py`: cross-checks the root `CLAUDE.md` Hooks / Scripts / Coupled Skill Pairs tables and this file's table against `user/settings.json`, `user/scripts/` on disk, `lazy-parity-manifest.json`, and `manifest.psd1` ↔ `repos/<name>/` dirs. Deliberate divergences are annotated in place with the `doc-drift:deliberate-divergence` marker (module-constant SSOT). `--repo-root`; exit 0 clean / 1 drift findings / 2 malformed input. The `.psd1` reader is a minimal tolerant parser for THIS manifest's shape, not a general PowerShell parser (out-of-shape → exit 2). Not on any state-script path; never imports `lazy_core`. Tests: `test_doc_drift_lint.py` (hermetic fixtures + a self-check pinning this repo drift-clean). |
| `lazy-queue-doc.py` | **Pure-read GitHub-mobile queue-status doc generator** (mobile-queue-control). Sibling to `lazy-state.py`; reuses `pipeline_visualizer.probe.probe_state` + `curated_stage` (never re-infers state, never mutates `queue.json`). Renders a per-repo root-level `LAZY_QUEUE.md`: Features/Bugs tables (reorder index, SPEC.md link, curated state, tier/severity), an inline drill-in summary (status · phase N/M · next · one-line exec summary), a "Needs attention" triage section, and a run-active/idle freshness header. **Byte-stable** — embeds no wall-clock, so an unchanged-state regen is byte-identical (freshness is GitHub's native last-commit time). `--repo-root` / `--stdout` / `--link-mode {relative,absolute}`. Orchestrator-invoked at the per-cycle commit (rides the existing commit on `main`); NOT on the state-script compute path. Tests: `test_lazy_queue_doc.py`. |
| `kpi-scorecard.py` | **Friction KPI registry lint + pure-read scorecard renderer** (friction-kpi-registry). Stdlib-only sibling of `lazy-queue-doc.py`: the deterministic tooling for the committed friction-KPI registry `docs/kpi/registry.json` (each friction-reduction system declares signal source, direction, baseline+provenance, regression band, `review_by`). `--lint` (schema/closed-enum/band/rot), default/`--stdout` (render byte-stable `docs/kpi/SCORECARD.md` — pure function of registry+signals+today, no wall-clock embed), `--lint --spec <p> [--registry <p>]` (the `/spec` Step-8.5 measurability-gate backstop the `spec-friction-kpi-gate.md` component shells — validates the `**Friction-reduction feature:** yes\|no` line + `## KPI Declaration`), `--capture-baseline <id>` (the SOLE computed-field registry writer — `provenance: measured` from the current window via `lazy_core._atomic_write`; refuses on no-data, re-lints before write, never fabricates). Computation REUSED from `pipeline_visualizer.trends` + `lazy_core` (deny ledger) — one computation, two renderers; never re-infers pipeline state. Honesty ladder: NO-DATA (absent/unrecordable signal, never a zero) → PENDING-BASELINE (`pending`/null-band) → OK/WARN/BREACH honoring `direction`. Orchestrator-invoked at the per-cycle commit (registry-gated, fail-open); NOT on the state-script compute path. Tests: `test_kpi_scorecard.py`. |
| `test_setup_py.py` | Pytest suite for the repo-root `setup.py` (cross-platform-setup) — the stdlib-only Python port of `setup.ps1` (minimal tolerant psd1 parser over the real `manifest.psd1`, mapping expansion incl. alias repos + `--repos-root`, bootstrap/check/repair parity rows, mocked-platform Windows link selection, temp-HOME end-to-end self-host). The script under test deliberately lives at the repo ROOT, not here — it must run on a bare clone before any symlink layout exists and imports nothing from this directory. |
| `incident-scan.py` | **Deterministic incident collector → bug-stub enqueuer** (incident-auto-capture) — stdlib, **READ-ONLY over inputs** (the `toolify-miner.py` discipline; tests hash the input trees before/after). Scans the per-repo keyed state dir (`lazy-deny-ledger.jsonl` via `read_deny_ledger`, the D2 `hook-events.jsonl`, legacy `hook-error.json`), clusters by `(repo, signal_class, signature)` (classes: `deny` ≥3/24h · `friction` ≥2/any · `hook-error` ≥2/7d · `hook-deny` ≥3/24h — config block at the top; acked denies COUNT), dedups against every open + archived `docs/bugs/**/INCIDENT.md` `incident_key` (post-archive recurrence → NEW stub with `recurrence_of:`, archive never mutated), and enqueues ≤2 stubs/scan (highest recurrence first) via the sanctioned `lazy-state.py --enqueue-adhoc --type bug` subprocess + an `INCIDENT.md` evidence capsule (`kind: incident-capture`; its ONLY two writes). `--repo-root` / `--dry-run` (byte-inert). Idempotent — same inputs ⇒ same keys/slugs (`adhoc-incident-<class>-<hash>`); guard denies come from the deny ledger only (never double-counted from hook-events). Invoked once per `/lazy-batch(-cloud)` run at the end-of-run flush (§1c.6, before `--run-end`) + on-demand via `/incident-scan`. NOT on the state-script compute path. Tests: `test_incident_scan.py`. |
| `efficacy-eval.py` | **Intervention-efficacy evaluator** (intervention-efficacy-tracking) — stdlib, **READ-ONLY over the telemetry ledger**; the SOLE post-capture writer of `docs/interventions/<id>.md` hypothesis records (capture itself is script-owned inside `lazy_core.apply_pseudo` `__mark_complete__`/`__mark_fixed__` + the coupled-pair `--record-intervention` CLI on both state scripts; repo-opt-in via a top-level `"interventions": true` in `docs/features/queue.json`, or a present `## Intervention Hypothesis` SPEC block). Accrues each open record's post-ship run-count window off the FROZEN `baseline.last_run_id` (D5 defaults 20/20/5/±20%, per-record overridable), writes CONFIRMED / REFUTED / INCONCLUSIVE verdicts (`## Review <date>` sections + atomic frontmatter updates through the shared serializer), annotates confounders (same-signal overlap caps at `INCONCLUSIVE (confounded)`), escalates after 2 INCONCLUSIVE reviews (passive needs-triage), and — on REFUTED — auto-enqueues `reconsider-<id>` via the sanctioned `lazy-state.py --enqueue-adhoc --type bug` subprocess behind a two-layer recurrence guard (open/archived bug-dir check + the `reconsideration_enqueued` stamp — one reconsideration per intervention, EVER). `--repo-root` / `--json` / `--dry-run` (byte-inert) / `--id`; exit 0 even on REFUTED (verdicts are data). Invoked once per `/lazy-batch(-cloud)` run at the §1c.6 end-of-run flush (alongside incident-scan) + on-demand; `/lazy-batch-retro` Step 6e cites it `--dry-run`. NOT on the state-script compute path. Record schema + authoring surface: `docs/interventions/CLAUDE.md`. Tests: `test_efficacy_eval.py`. **Field-evidence blind window:** this machine's hook-derived signals (deny-ledger / `hook-events.jsonl`) UNDERCOUNT for 2026-06-11→2026-07-12 — the enforcement guards were unregistered in the live `settings.json` (`live-settings-split-brain-disarms-enforcement-plane`, D3). Treat a low count in that window as partially-blind, not zero friction; annotate-only, no backfill (see the documented `BLIND_WINDOW` constant in `incident-scan.py`). |

## Contributor conventions (read before editing the state scripts)

These recur in nearly every cycle — internalize them instead of re-deriving them from the source
each time (they are the most-re-read facts in this directory):

- **All queue/marker/sentinel writes go through `lazy_core._atomic_write`** — never a bare
  `open().write()`. Atomicity is the contract; a half-written `queue.json` corrupts the machine.
- **Diagnostics use `lazy_core._diag(msg)`** (appends to the per-invocation `_DIAGNOSTICS` list,
  reset once per `compute_state`). That's how the "why this route" breadcrumb reaches the
  orchestrator — don't `print()`.
- **Helper placement:** domain-agnostic helpers (sentinel/plan parsing, receipt writers,
  diagnostics) live in `lazy_core.py` (shared by both state scripts); script-specific logic stays
  in `lazy-state.py` / `bug-state.py`.
- **Arg-name divergence:** `lazy-state.py` uses `--feature-id`; `bug-state.py` uses `--bug-id`.
  Not interchangeable — a justified divergence, not a bug to "fix".
- **Coupled scripts are parity-gated.** A change to one state script usually must be mirrored to
  the other; run the parity audit (below) and consult the coupled-pairs table in the root `CLAUDE.md`.

### Adding a test to the in-file `--test` harness

Both `lazy-state.py` and `bug-state.py` carry their own smoke-test harness run with `--test`
(**not** pytest). To add a fixture: write `def test_<name>():` and register it in the script's
test-list block so the `--test` runner collects it. Mirror marker/queue setup from a recent
nearby test rather than inventing scaffolding. `lazy_core.py` is tested separately via
`test_lazy_core.py` (pytest).

### CLI quick reference — the easy-to-miss ones

```bash
# Parity audit — REQUIRED before committing a change to either half of a coupled pair.
python3 user/scripts/lazy_parity_audit.py --repo-root .                      # audit ALL pairs
python3 user/scripts/lazy_parity_audit.py --repo-root . --pair lazy-bug-batch
python3 user/scripts/lazy_parity_audit.py --repo-root . --merged-view
```

> **Gotcha (40+ misfires in session logs):** `--repo-root` is **required** and there is **no
> `--report` flag**. `... --report` fails with "unrecognized arguments"; bare `lazy_parity_audit.py`
> fails with "the following arguments are required: --repo-root".

### Shell dialect — don't mix tools

The **Bash tool is real bash** (`head`, `grep`, `dirname`, `stat`). The **PowerShell tool needs
cmdlets** (`Get-Content`, `Select-Object`, `Select-String`, `Get-ChildItem`). Crossing them fails:
`head`/`grep` are "not recognized" in PowerShell; `Select-Object`/`Get-Content` are "command not
found" in bash.

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
| `lazy-batch-parallel` | user-level | `lazy_coord.py` + `lazy-state.py` (per lane via `--repo-root <worktree> --feature-id`) | **Sanctioned parallel-worktree coordinator** (workstation-only v1: claude-config + AlgoBooth). Shards dep-ready `independent: true` items across worktree lanes (one lane branch + lane marker + fencing lease each); single writer of the contended trio; queue-order merge with demote-on-conflict; park-on-sentinel isolates lanes. Feature-pipeline only in v1 (justified divergence — no bug-pipeline mirror). |

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

## Three environments + the device axis + the host-capability axis

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

### The host-capability axis (`host-capability-declaration-for-gated-features`)

The device axis above is **hard-coded to ONE capability** — the real audio device, keyed on
the single `$ALGOBOOTH_REAL_AUDIO_DEVICE` env signal. The host-capability axis **generalizes
that device-saturated skip into an N-capability axis**: a feature whose runtime validation
needs an arbitrary named host capability (a C++ toolchain like Zimtohrli, a GPU, a specific CLI
binary) declares it on-disk in a `requires_host:` set, and `lazy-state.py` defers/skips it on a
host that lacks the capability — exactly as the device axis defers a real-device-only assertion.

- **Declaration (`requires_host:`).** A two-source read (`lazy_core.parse_requires_host` — SPEC
  frontmatter + the `queue.json` entry) returns the declared capability-id set; absent/legacy ⇒
  the EMPTY set (ungated, byte-identical to today). Ids match `^[a-z0-9][a-z0-9-]*$`, drawn from a
  **closed registry** (`lazy_core._HOST_CAPABILITY_REGISTRY` — a hardcoded `id → probe-callable`
  map). Composite requirements are a **flat AND-set**: `set(requires_host).issubset(host_present)`.
- **Probe (active invocation, NOT `which()`).** The host's present-capability set is resolved by
  `lazy_core.host_present_capabilities` with **injected probe callables** (hermetic `--test`). A
  binary probe MUST run the tool (`subprocess.run([tool, "--version"])`) and check the exit code —
  NEVER `shutil.which()` / `os.path.exists()`. This guards the Windows `\WindowsApps` zero-byte
  App-Execution-Alias false-positive (a `which()`-resolvable stub whose invocation opens a GUI
  Store prompt and hangs the pipeline). The result is cached per-run in the per-repo keyed state
  dir (re-probe on a new run marker).
- **Fail-fast on an unregistered id (`BLOCKED.md`).** An id with no registry probe could never be
  reported present on ANY host, so a silent defer would strand the feature in infinite queue
  starvation. `compute_state` fails fast FIRST: a canonical `BLOCKED.md`
  (`blocker_kind: unknown-host-capability`) naming the offending id + the registry's known ids
  (`lazy_core.format_unknown_host_capability_blocker`). **Mirrored into `bug-state.py` for parity**
  (parity-audited by `lazy_parity_audit.py::audit_state_script_parity`); the capability-miss DEFER
  below is feature-pipeline-shaped (justified divergence — bug-state.py does not expose it).
- **The `DEFERRED_REQUIRES_HOST.md` re-open contract (alongside `DEFERRED_REQUIRES_DEVICE.md`).**
  On a capability miss (`missing = requires_host − host.present` non-empty) for a feature past
  implementation with no `VALIDATED.md`, `compute_state` writes a re-openable
  `DEFERRED_REQUIRES_HOST.md` (`kind: deferred-requires-host`, `missing_capabilities: [...]`
  load-bearing non-empty), records the skip, and advances the queue via the existing skip-ahead
  plumbing — exactly the `DEFERRED_REQUIRES_DEVICE.md` shape. On a **capability-bearing host** the
  probe reports `missing` empty and the feature **re-opens** with no special case (it simply does
  not skip) and proceeds to runtime validation → `__mark_complete__`. The sentinel is in
  `lazy_core._FAIL_CLOSED_EVIDENCE_SENTINELS` so the completion gate treats it as defer-not-evidence
  (a host-deferred feature never reaches `Complete` on a host lacking the capability). When the
  queue exhausts to only capability-gated features, the terminal is **`host-capability-saturated`**
  (a clean stop in `lazy_core.SANCTIONED_STOP_TERMINAL`, the host-axis mirror of
  `device-queue-exhausted`); the notification names each feature + its missing id(s). The
  `host_deferred_features` probe key surfaces each deferred feature_id for the orchestrator's
  end-of-run flush (the device axis's `device_deferred_features` analog). **Skip ≠ defer** holds
  here too — `DEFERRED_REQUIRES_HOST.md` re-opens on a capability-host, it is never a permanent waiver.

> **Documented vN upgrade paths (OUT of v1 scope).** v1 is coarse named-presence + flat AND-set.
> Future axes are deliberately deferred, none requiring an engine change to the `requires_host:`
> array shape: **version matrices** via a namespaced-suffix taxonomy (`zimtohrli-v2`, `cuda-11` —
> Bazel `constraint_value` / Nix naming, NOT a semantic-version solver); **OR-groups / optional
> capabilities** via separate config profiles (Bazel `select()`-style); a **host-manifest probe
> override** (a state-init seam to override the deterministic probe with an operator-maintained
> manifest, for air-gapped hosts); and **fleet-wide deferral-starvation monitoring** (v1 surfaces
> each deferral; cross-host accumulation tracking is vN). See the feature's SPEC "Documented vN
> upgrade paths" block.

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

## Opt-in on-disk feature auto-discovery (`feature-queue-lacks-on-disk-autodiscovery`)

`bug-state.py::load_bug_queue` has always auto-discovered open `docs/bugs/<slug>/`
dirs (hybrid load over `docs/bugs/queue.json` — "the queue is OPTIONAL").
`lazy-state.py::load_queue` historically read features **only** from
`docs/features/queue.json`, so a new `docs/features/<slug>/SPEC.md` was inert until
explicitly `--enqueue-adhoc`'d. `load_queue` now mirrors the bug loader **opt-in**:

- **Flag:** a top-level `"autodiscover": true` in `docs/features/queue.json` (sibling of
  `"queue"`). **Repo-local by construction** — only claude-config sets it; AlgoBooth and
  every other repo omit it and are **byte-identical to today** (flag absent/falsy ⇒
  `load_queue` returns the raw queue list unchanged). Do NOT promote it to a global
  default without a separate decision (SPEC Open Question 2 defers that).
- **Merge is probe-time, in-memory** — discovered dirs are appended to the in-memory
  work-list when `lazy-state.py` runs; **nothing is ever written into `queue.json`**
  (identical to how `load_bug_queue` merges `_find_open_bug_dirs`).
- **New helpers in `lazy-state.py`:** `_find_open_feature_dirs(features_dir, queued_ids)`
  (structural mirror of `bug-state.py::_find_open_bug_dirs` — one-level scan; skips
  non-dirs / `_`-prefixed dirs / already-queued ids; requires `SPEC.md`; excludes
  `Superseded` and `Complete`+valid-`COMPLETED.md`-receipt; surfaces a
  `Complete`-without-receipt dir for the `completion-unverified` gate) and
  `feature_tier(spec_md)` (reads `**Priority:** P0..P3` → `0..3`, absent → `99` last;
  the feature pipeline orders by an **int tier** where the bug pipeline orders by a
  **severity string** — the JUSTIFIED feature/bug divergence). Discovered entries carry
  the **raw-queue-item key shape** (`id`/`name`/`spec_dir`/`tier`/`queue_entry: None`) the
  `compute_state` walk loop reads directly — NOT the bug loader's normalized `spec_path`
  shape (the two loaders' return shapes legitimately differ).
- **`queue-missing` reconciliation:** the `if not queue:` early-return short-circuits to
  `queue-missing` ONLY when autodiscover is OFF (`_queue_autodiscover_enabled`). With the
  flag on and an empty merged list (all on-disk dirs Complete+receipt / Superseded), it
  falls through to the normal exhaustion logic → `all-features-complete`.
- **Coupling:** feature-pipeline-only. `bug-state.py` is UNCHANGED; this additive
  loader extension is a JUSTIFIED divergence (`lazy_parity_audit.py` does not audit
  `load_queue`/`load_bug_queue` symmetry, and stays green). See
  `docs/bugs/feature-queue-lacks-on-disk-autodiscovery`.

## Queue dependency DAG (`queue-dependency-dag`)

Queue entries on BOTH pipelines accept an optional **`"deps": ["<id>", ...]`** field — a flat,
hard-only, machine-enforced dependency list (D1: the enforcement projection of the SPEC's prose
`**Depends on:**` block, which stays the SSOT for kinds/reasons). Same-pipeline bare ids only in
v1; `bug:`/`feature:` prefixes are reserved for cross-pipeline vN and refused (D6). Contracts:

- **Load-time validation (both loaders):** malformed shape / invalid id / reserved prefix /
  dependency **cycle** (Kahn's over queued-id edges) → `_die` exit 2, like every other
  queue-schema violation (`lazy_core.validate_queue_deps`).
- **The dep-gate (`compute_state` walk loop, D2):** an entry whose dep is not
  receipt-gated-complete (D3: `Complete`+`COMPLETED.md` / `Fixed`+`FIXED.md` via
  `lazy_core.dep_completion_status`; bug resolution is **archive-aware** — consults
  `docs/bugs/_archive/<id>/`) is HELD (`continue`) so the walk lands on the dependency first.
  Transitivity is emergent (a still-queued dep is incomplete by construction). Runs regardless of
  `--strict-research-halt`; sits after the completion/cloud/device/host/research/park/budget skips
  and before the feature skip-ahead branch. Entries without `deps` are byte-identical on every path.
- **Fail-fast (D4):** a dangling dep id, or a `Superseded` (feature) / `Won't-fix` (bug) upstream,
  writes canonical `BLOCKED.md` (`blocker_kind: unknown-dependency`,
  `lazy_core.format_unknown_dependency_blocker`) on the DEPENDENT — the `unknown-host-capability`
  shape, for the same starvation reason.
- **Probe surface (D10):** the `dep_gated` key — `[{id, missing: [...]}]` — present ONLY when the
  walk held ≥1 item this probe, plus a per-hold `_diag`. All-remaining-held →
  the clean sanctioned terminal **`queue-exhausted-dependency-gated`** (flush names each hold).
- **Feeder (D5):** `--sync-deps` (below) projects SPEC hard deps into the field at `/spec-phases`
  Step 1.6; a probe-time **drift `_diag`** (gated on the entry CARRYING a `deps` key) warns when
  the queue set diverges from the SPEC's hard set — lint-grade, never a halt. `--enqueue-adhoc`
  accepts `--deps a,b` for enqueue-time declaration.
- **Skip-ahead (D7, feature-only):** `skip_ahead_ready` key 1 evaluates SPEC hard deps ∪ queue
  deps (`_merged_skip_ahead_deps`, source-tagged audit line). Defense-in-depth — the dep-gate
  holds such candidates first. The bug pipeline has NO skip-ahead (justified divergence #1);
  archive-aware bug resolution is divergence #2. Everything else mirrors (parity audit surface #6).

## CLI surface

```bash
python3 lazy-state.py                       # next workstation action (JSON on stdout)
python3 lazy-state.py --cloud               # cloud variant
python3 lazy-state.py --real-device auto    # resolve host audio capability from env
python3 lazy-state.py --skip-needs-research # batch: skip research-pending items
python3 lazy-state.py --repo-root <path>    # operate on a specific repo
python3 lazy-state.py --park-needs-input    # batch --park mode: skip (park) NEEDS_INPUT items into parked[] instead of halting (BLOCKED still halts UNLESS --park-blocked is also active; output byte-identical without the flag)
python3 lazy-state.py --park-blocked        # batch --park mode companion: skip (park) a feature/bug-local BLOCKED.md into parked[] (sentinel_kind: blocked) instead of halting on terminal_reason=blocked; --park passes BOTH flags. Global/env terminals (cloud/device/research/scoped-id) still halt. Output byte-identical without the flag. Same flag on bug-state.py.
python3 lazy-state.py --per-feature-cycle-cap N  # feature-budget-guard: OFF by default — the guard never arms; `--per-feature-cycle-cap N` opt-in arms the per-feature budget guard with a fixed ceiling N. The whole-run `max_cycles` is the sole default budget. When the armed guard trips, the budget_guard probe field surfaces the ceiling in count_at_trip + computed_ceiling + action (defer|evict|grace) + next_id + sub_skill_phase + commit_hash. Terminal queue-exhausted-budget-deferred fires when all items are budget-deferred/evicted with no independent successor. Environment-agnostic — same flag on lazy-state.py --cloud. THREE COMPOSITE-SIGNAL BEHAVIORS (budget-guard-defers-near-complete-feature) refine the raw `count >= ceiling` trip under the opt-in flag so legitimate progress is not punished as monopolization: (1) NEAR-COMPLETION GRACE — a feature within one validation cycle of done (`lazy_core.feature_is_near_complete`: verification-only-unchecked PHASES via `remaining_unchecked_are_verification_only` + ≥1 plan part `status: Complete` + no `BLOCKED.md`) is granted ONE grace cycle past the ceiling (no defer) so it reaches `/mcp-test` → `__mark_complete__`; the probe carries `action: "grace"` + `near_complete_grace_granted: true` + `effective_count`/`corrective_count`. Grace is ONE-SHOT (a near-complete feature already budget-deferred this run, `prior_defers >= 1`, is treated as not-near-complete for the trip so it cannot exploit grace to monopolize). (2) CORRECTIVE-CYCLE DISCOUNT — `effective_count = max(0, forward_cycles − corrective_cycles)`; validation-driven corrective work is read from the run-marker sub-map `per_feature_corrective_cycles: {feature_id: int}` (seeded `{}` by `write_run_marker` in lockstep with `per_feature_forward_cycles`; incremented at the apply-resolution / corrective-dispatch bracket folded into the `--record-resolution-signal` handler via `lazy_core.record_corrective_cycle`, marker-gated + fail-open). The guard defers only when `effective_count >= ceiling` AND NOT near-complete (`lazy_core.budget_trip_signals`). (3) END-OF-RUN NEAR-COMPLETE RESUME FLUSH — before the `queue-exhausted-budget-deferred` terminal fires, the `current is None` block re-scans this-probe budget-deferred features IN QUEUE ORDER and AUTO-RESUMES the first that is now near-complete AND was NOT evicted (surfaced via the `budget_resumed_near_complete: <feature_id>` probe key), so a feature deferred BEFORE it became near-complete validates this run instead of being parked (and risking 2nd-trip eviction with a hot runtime idle). Evicted features are NEVER auto-resumed (terminal eviction is intentional dead-lettering); to keep the flush reachable, a NEAR-COMPLETE feature whose one-shot grace is spent is HELD AS DEFERRED (never escalated to evict) — monopoly eviction is unchanged for non-near-complete features. FEATURE-PIPELINE ONLY: `bug-state.py` has no per-feature ceiling, so none of this is mirrored (justified divergence — confirmed clean against `lazy_parity_audit.py`).
python3 lazy-state.py --strict-research-halt     # feature-budget-guard skip-ahead: disable the default-on dependency-aware skip-ahead (restores legacy halt-on-first-gated-head). Default (flag absent): when the queue head is research-gated or BLOCKED, lazy-state.py automatically advances to the next independent, independent:true-marked queue item (if one exists) instead of halting immediately. The gated head always surfaces in the probe's gated_heads key (list of gated feature_ids) regardless of whether skip-ahead advanced past it — used by the orchestrator for end-of-run flush. Environment-agnostic — same flag on lazy-state.py --cloud.
python3 lazy-state.py --enqueue-adhoc …     # prepend an ad-hoc item to the queue. --type {feature,bug} (default feature; unified-pipeline-orchestrator Phase 3) selects the destination pipeline: feature → docs/features/queue.json (unchanged); bug → docs/bugs/queue.json via the EXISTING bug-state.py enqueue (enqueue_adhoc_bug() seeds docs/bugs/<slug>/ around the subprocess — NOT a reimplementation). bug-state.py --enqueue-adhoc accepts a benign --type bug so the documented unified form parses. toolify-auto-promotion Phase 2 (D4-B) adds additive DEFAULT-OFF flags on the FEATURE path: `--stub` (writes `"stub": true` on the entry — the Step-4.5 baseline-lock cross-check flag; key omitted otherwise) and `--at {head,tail}` (default head = byte-identical prepend; tail appends so a toolify promotion rides roadmap order instead of jumping the curated queue); `--tier N` already existed. FEATURE-PIPELINE-ONLY: `--stub`/`--at tail` combined with `--type bug` are refused loudly (exit 2) — the bug pipeline has no stub step and orders by severity, so bug-state.py deliberately has NO mirror (justified divergence; lazy_parity_audit.py's state-script checks do not audit enqueue-flag symmetry and stay exit 0). Optional `--deps a,b` (queue-dependency-dag): comma-separated hard-dep ids stored on the prepended entry's `deps` field (validated — kebab-case ids; `bug:`/`feature:` prefixes are reserved for cross-pipeline vN and refused exit 2); forwarded to the bug-state subprocess on --type bug; omitted ⇒ byte-identical legacy entry shape.
python3 lazy-state.py --reorder-queue --id <id> --to {tail|head|remove|<index>}  # no-sanctioned-queue-reorder-command: OPERATOR-ONLY / OUT-OF-CYCLE queue-ordering mutation on docs/features/queue.json (the existing-entry counterpart to --enqueue-adhoc's insert-at-head). Gated by refuse_if_cycle_active("--reorder-queue") FIRST — a cycle subagent is refused exit 3 with ZERO side effects, exactly like --enqueue-adhoc. Requires --id (REUSES the existing --id flag; no second id flag) and --to. --to: `tail`/`head`/`remove`, or an integer index (out-of-range clamped). Folds all four operator queue mutations (defer-to-tail, move/reorder, remove/skip, reprioritize) into ONE primitive — calls the shared lazy_core.reorder_queue helper (load → mutate → _atomic_write, mirroring enqueue_adhoc). A missing id or malformed JSON _die()s (exit 2); moving an entry already at the target is a byte-stable no-op (returns noop: true). PRESENT ON BOTH SCRIPTS (coupled pair): bug-state.py --reorder-queue mutates docs/bugs/queue.json identically (parity-guarded by lazy_parity_audit.py::audit_state_script_parity). Replaces the legacy reorder-via-BLOCKED.md + dispatched apply-resolution subagent round-trip (the blocked-resolution.md Defer path now calls this command inline; HARD CONSTRAINT 1's no-hand-edit-queue.json rule is preserved — the orchestrator calls the script).
python3 lazy-state.py --sync-deps --id <id>   # queue-dependency-dag D5: ORCHESTRATOR-ONLY feeder (wired at /spec-phases Step 1.6) — projects the item's SPEC `**Depends on:**` block (HARD kinds only; the prose block stays the SSOT for kinds/reasons) into the queue entry's `deps` field via the shared lazy_core.sync_deps (load → parse_dep_block → filter hard → mutate → _atomic_write). Gated by refuse_if_cycle_active("--sync-deps") FIRST (cycle subagent → exit 3, zero side effects). Idempotent + byte-stable (noop: true when in sync; an empty hard set REMOVES the `deps` key). Fail-fast _die exit 2 (zero mutation) on: missing id, missing SPEC.md, a self-dep, or a projection that would create a queue cycle. PRESENT ON BOTH SCRIPTS (coupled pair; parity-guarded — audit surface #6): bug-state.py --sync-deps mutates docs/bugs/queue.json identically.
python3 lazy-state.py --next-merged          # unified-pipeline-orchestrator Phase 1: print the head of the MERGED feature+bug work-list as JSON {item_id, type, repo_root} (or null when both queues empty). Read-only ORDERING ONLY — reuses load_queue (features) + bug-state.load_bug_queue (bugs, via importlib) and the lazy_core ordering helper; NEVER re-infers per-item state (the unified driver still calls --probe/--emit-prompt per item). Normalizes the two queues' divergent ordering fields (feature `tier` int / bug `severity` P0..Low) to one effective-priority scale (lower = higher priority); equal priority → bug before feature; stable within each queue. Binds the active repo before reading. Shared impl: lazy_core.merged_priority/merged_worklist/next_merged.
python3 lazy-state.py --backfill-receipts   # grandfather pre-gate completions
# --- code-doc-provenance-linkage: the provenance ledger (same four flags on bug-state.py — shared lazy_core impl, no coupled-pair mirror owed). ONE WRITER, TWO TRIGGERS: lazy_core.write_provenance is the sole author of the per-item IMPLEMENTED.md distillate (kind: implemented — what shipped / Locked-Decision ids / validated-via) and the committed per-repo reverse index docs/provenance-index.json (repo-relative POSIX path → [{id, type, provenance}]). Trigger 1 is automatic: the __mark_complete__/__mark_fixed__ branch of apply_pseudo calls it AFTER the receipt+queue-trim+ROADMAP-strike (provenance: pipeline-gated; derivation commit-brackets primary — unioned from the lazy-commit-brackets.jsonl per-cycle bracket ledger both scripts append at --cycle-end, fail-open — with message-grep as the honestly-labeled fallback; result carries provenance_written, failures degrade to warnings[] and NEVER block the completion; the receipt now also stamps completed_commit). Trigger 2 is the manual CLI below. ---
python3 lazy-state.py --link-provenance --id <slug> --commits <A..B>  # manual link of out-of-pipeline work (teammate PR / hotfix) through the SAME producer: provenance: manual + linked_by + derivation: commit-range. --pr <n> is gh-resolved sugar (clean refusal names the --commits fallback when gh is absent); --body-file <path> carries the operator-APPROVED prose (the /link-provenance skill's draft-then-approve loop); --dry-run derives + previews, writes NOTHING. Item dir resolved docs/features/<id> → docs/bugs/<id> → docs/bugs/_archive/<id>; none → a minimal docs/features/<id>/ decision-record dir (no fake SPEC). Re-linking REPLACES the item's rows (idempotent). Cycle-guarded (exit 3) like --enqueue-adhoc.
python3 lazy-state.py --provenance-lookup <path>   # PURE READ (D6-A consumer step, wired into cycle-base-prompt/execute-plan cycles + /spec-phases Step 2.8 + the /lazy* wrappers): {path, governed_by: [{id, type, doc, decisions, provenance}]} — which decision records govern this file. Missing index → empty governed_by (no-op); never mutates, never creates dirs.
python3 lazy-state.py --lint-provenance      # PURE READ, report only (D10): dead index rows (path gone — D5 re-link-or-tombstone prompt), churn hotspots (≥5 authored commits/90d, no rows, docs/** excluded; thresholds are constants in lazy_core), cross-orphans (distillate↔index).
python3 lazy-state.py --backfill-provenance  # one-shot D7-A backfill: every receipted item (COMPLETED.md/FIXED.md incl. docs/bugs/_archive/) distilled via message-grep, provenance: backfilled; items with IMPLEMENTED.md skipped (idempotent); zero-hit slugs get an honest commits: [] distillate and no rows. Run for claude-config 2026-07-04: 50 items → 625 index keys.
python3 lazy-state.py --record-intervention --id <id> [--spec-dir <item-dir>] [--pipeline feature|bug|hardening] [--shipped-commit SHA --shipped-date YYYY-MM-DD] [--target-signal event:<type>|kpi:<sys>.<id> --expected-direction decrease|increase --signal-independence "..." --review-after-runs N]  # intervention-efficacy-tracking: hypothesis-ledger capture for the manual / hardening-round / D9-backfill paths (shipped-* overrides stamp provenance: backfilled). Orchestrator-only (refuse_if_cycle_active). PRESENT ON BOTH SCRIPTS (coupled pair; parity-audited); the completion-gate capture itself is shared lazy_core.apply_pseudo. Idempotent — an existing docs/interventions/<id>.md is never clobbered.
python3 lazy-state.py --test                # run the in-file fixture smoke tests
# --- Phase 5 orchestrator-loop subcommands (shared impl in lazy_core.py; same flags on bug-state.py) ---
python3 lazy-state.py --verify-ledger <spec_path> [--plan <plan_part>]  # completion-ledger gate as JSON {ok, failing_check, checks:{clean_tree, head_matches_origin, plan_complete, deliverables_done}, deliverables_source}; exit 1 iff not ok. Replaces the 5 duplicated prose ledger blocks. deliverables_done exempts verification-only rows. SOURCE OF TRUTH (2026-06-15, d8-effect-chains review): with --plan, deliverables_done reads the PLAN PART's own `- [ ] WU-N` checkboxes (machine record since write-plan ISSUE-6), NOT PHASES.md phase-level rows — eliminating cross-part + cross-phase-attribution false-fails. A legacy plan with no per-WU rows falls back to PHASES-phase-level and reports deliverables_source: "phases-fallback …". Without --plan: whole-feature PHASES.md (deliverables_source: "phases-feature-level").
python3 lazy-state.py --ensure-runtime               # unified-pipeline-orchestrator Phase 5 + long-build-and-runtime-ownership Phase 2 (LD2/LD3): ensure the dev runtime + MCP server are up, CURRENT, and VERIFIABLY OWNED; print the M4 liveness/recovery verdict JSON {state, ownership_verified, health_code, mcp_tools_present, terminal_blocker} with state ∈ {READY, STALE, HIJACKED, DEAD, BLOCKED}. (The legacy {status: ready|booted|stale-rebuilt} field is RETAINED in the dict — the verdict is a SUPERSET so the part-5 orchestrator migration is incremental.) The reworked-in-place ensure_runtime runs the M4 three-phase evaluation: Identity (read `.runtime.lock.json` → verify_runtime_ownership against the live kernel start_time + the run marker's session_id; divergent live owner answering /health ⇒ HIJACKED, missing/dead PID ⇒ DEAD) → Staleness (injected stale_check ⇒ STALE) → Health (probe /health; refused despite a live owned PID ⇒ DEAD). RECOVERY contract: STALE/DEAD auto-recover via restart() in a bounded exponential-backoff loop CAPPED AT 5 attempts (rewriting `.runtime.lock.json` on a healthy re-probe → READY); on exhaustion ⇒ BLOCKED + terminal_blocker. HIJACKED is a strict FAIL-SAFE — terminal_blocker set, the foreign process is NEVER SIGKILLed (security/stability, LD3). The handler threads the LIVE run marker's session_id as live_session_id (the controller_session_id recorded into the lock — NOT a second minted id); with no marker (interactive, no run) it falls back to the legacy boot/ready flow (still the verdict superset). AlgoBooth specifics (TCP 3333, npm run dev:restart, src-tauri/crates globs, asserted MCP tool, the `.runtime.lock.json` filename) are PARAMETERIZED in lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG (caller-overridable dict) — NOT hard-coded into the shared harness flow. lazy_core.ensure_runtime takes injected probe/restart/stale_check/read_lock/kernel_start_time_fn/sleep/write_lock/recover_identity callables so --test is hermetic (the ≤5 bound, the backoff schedule, and the never-SIGKILL invariant are asserted without a real runtime/network/clock/kill); production uses a real urllib probe + background dev:restart + the stale_binary predicate + the real kernel start_time extractor. CONSUMER ROUTING (long-build-and-runtime-ownership Phase 5): `/lazy-batch` Step 1d.0 (the sole consumer; `/lazy-batch-cloud` defers MCP and never reaches it — workstation-only) calls this ONCE per mcp-test cycle and routes on the FULL verdict's `state` — no hand-rolled rebuild→health-poll until-loop in the cycle prompt: READY / STALE→READY / DEAD→READY proceed to dispatch; `state ∈ {HIJACKED, BLOCKED}` (and any residual unrecoverable `mcp_tools_present: false`) ⇒ the orchestrator writes `BLOCKED.md` `blocker_kind: mcp-runtime-unready` (the verdict's `terminal_blocker` text VERBATIM as the body) and dispatches NO subagent against a dead/hijacked runtime. The mirrored guard-takeover path: when `long-build-ownership-guard.sh` denies a subagent long build (bubbling `LONG-BUILD-OWNERSHIP-TAKEOVER`), the orchestrator runs the build under the Transient Build contract (`run_transient_build` + `promote_artifact_atomically`) — distinct from this Persistent Service runtime (LD5: one spawn primitive, two contracts). SIDECAR-PIPE READINESS (env-transient-counts-against-validation-retry-budget Phase 1, Leg A — repo-agnostic default OFF): the dev HTTP server boots INDEPENDENTLY of the MCP sidecar named pipe, so health=200 does NOT prove the sidecar is connected — a zombie node process holding the :3333 pipe after a dev:restart leaves the runtime HTTP-healthy but MCP-functionally DEAD (a self-inflicted env transient). When a repo sets `assert_sidecar_connected: true` (+ optional `sidecar_status_url`, default `http://localhost:3333/tools/get_sidecar_status`) in its config override — AlgoBooth opts in; default OFF keeps every other repo unaffected — the M4 Health phase additionally asserts `get_sidecar_status.is_connected: true` AFTER code==200 and BEFORE the READY verdict: a disconnected pipe routes into the SAME bounded recovery (a dev:restart that reaps the stale pipe; `_recover_runtime` re-asserts the pipe on each healthy re-probe, so a restart that fixes HTTP but not the pipe does NOT count recovered) and, on persistent disconnect, to `state: BLOCKED` → `blocker_kind: mcp-runtime-unready` (escalation-immune) — NEVER an `mcp-validation` charge against the feature's validation-retry budget. Threaded via a new injected `sidecar_check` callable on `ensure_runtime` (bound to the real `_default_sidecar_probe` only when the config asserts it, else `lambda: True`) so --test stays hermetic; `validation_escalation` is UNCHANGED (the fix keeps env transients from reaching it with the `mcp-validation` label). TWO-PORT COLD-COMPILE PATIENT-WAIT (ensure-runtime-recovery-starves-cold-compile): the LD3 bounded-recovery contract above is RE-SCOPED to genuine crashes. A cold `tauri dev` brings Vite up on :1420 within seconds while :3333 /health refuses until the (multi-minute) cold Rust compile finishes — so a :3333-down/:1420-up observation means COMPILING (be patient), not dead. The M4 evaluation now consults `_classify_compile_state(backend_code, frontend_up)` (serving|compiling|dead) at every `_recover_runtime` entry point (+ STALE): a `compiling` runtime is PATIENTLY WAITED on via `_await_compile_serving` (a non-killing poll on the SAME `90 × 5s` ≈ 7.5-min ceiling the production restart-awaiter uses — NOT the ≤5×backoff ~31s crash budget; `restart()`/kill NEVER called while compiling) and reaches READY on `:3333` 200 (+ sidecar when asserted); only a genuinely `dead` runtime (both ports down) enters the bounded ≤5×backoff loop, and a `compiling→dead` transition mid-wait falls through to it. On cold-compile-ceiling exhaustion the verdict is BLOCKED with the DISTINCT `_cold_compile_timeout_blocker` text (still `blocker_kind: mcp-runtime-unready` downstream — verdict TEXT only, no new blocker_kind, no routing change). Repo-agnostic default: the `frontend_health_url`/`frontend_port` keys default to :1420 in `_ENSURE_RUNTIME_DEFAULT_CONFIG`; a repo without a :1420 frontend overrides the key off (empty `frontend_health_url`) so `frontend_probe` binds `lambda: False` → every non-serving runtime classifies `dead` ⇒ byte-identical to before. Threaded via a new injected `frontend_probe` callable on `ensure_runtime` (default-bound from the config like `sidecar_check`) so --test stays hermetic. PRE-VITE BOOT-LIVENESS PATIENT-WAIT (ensure-runtime-starves-pre-vite-sidecar-build): the TWO-PORT cold-compile wait above covers only the *Vite-up* window (its sole "still booting" signal is :1420 being up). A cold `tauri dev` ALSO spends its first ~1–2 min in the PRE-VITE `BeforeDevCommand` (`npm run sidecar:build && vite`) phase with BOTH ports down while the spawned boot process is alive — previously misclassified `dead` and kill-restarted into a false BLOCKED. This adds a SECOND "still booting" signal — boot-process liveness — via a back-compat 3rd param on `_classify_compile_state(backend_code, frontend_up, boot_alive=False)`: a both-ports-down-but-live-boot observation classifies `compiling` (reuse the patient-wait label, no new state) and is WAITED on the SAME `90 × 5s` ceiling, never kill-restarted; both routers (`_route_legacy_non_serving` + M4 `_route_non_serving`) consult it, and `_await_compile_serving`'s went-dead check is now an OR of BOTH signals (fall through to bounded recovery only when frontend AND boot are both down). Threaded via a new injected `boot_alive` callable on `ensure_runtime` (default-bound from a `boot_liveness` config key, base-default OFF) so --test stays hermetic; the production source is the in-process `restart()`-spawned `Popen` handle (`.poll()` None ⇒ alive — NO URL probe needed, so no `_default_*` helper). Repo-agnostic default: a repo that does not opt into `boot_liveness` sees a both-ports-down runtime classify `dead` ⇒ byte-identical to before; genuine-crash (both down, no live boot) recovery is UNCHANGED. Feature-pipeline-only coupling, same divergence as the prior cold-compile fix (next sentence). SOFT OWNED-UNVERIFIED READY (ensure-runtime-false-hijacked-on-owned-serving-runtime): a serving runtime that the orchestrator self-booted this single session can fail `verify_runtime_ownership` on the SESSION component alone — the lock's `controller_session_id` and the threaded `live_session_id` come from different sources and diverge for a Bash-driven single-session loop, even though the live PID is the run's OWN booted process. So in the `_ensure_runtime_m4` `not owned` branch, a runtime that is provably serving (`code == 200` + `mcp_tools_present`) AND whose live PID is the SAME process (kernel start_time MATCHES the recorded lock start_time) classifies a non-terminal `state: READY` with `ownership_verified: false` (proceed to dispatch) instead of the terminal HIJACKED fail-safe — and is NEVER SIGKILLed (no restart on this path; LD3). The classifier-level guard runs `stale_check()` FIRST, so a genuinely stale binary still routes through STALE/rebuild (not masked). The genuine-foreign HIJACKED — no matching lock PID (→ DEAD), or a live PID whose start_time DIVERGES from the recorded lock start_time (real PID reuse / a foreign port-holder) — stays the strict never-SIGKILL fail-safe. `verify_runtime_ownership` itself is UNCHANGED (the strict predicate stays strict; the relaxation is classifier-level, keyed on its exact sub-signals). COUPLING: `--ensure-runtime` is feature-pipeline-only (`lazy-state.py` CLI + shared `lazy_core` helper); `bug-state.py` has NO `--ensure-runtime` handler, so NO coupled-pair CLI mirror is owed (justified divergence — confirmed against `lazy_parity_audit.py`).
python3 lazy-state.py --gate-coverage <spec_path>    # unified-pipeline-orchestrator Phase 5: deterministic, symlink-resolving Gate-1 MCP-coverage verdict. Print JSON {ok, decisions:[{id,title,keywords,covered}], uncovered:[id], scenario_count}; exit 1 iff any decision uncovered. Reads SPEC.md's Locked-Decision surface (## Locked Decisions table / ## Resolved by Research checked bullets / ## Key|Design Decisions numbered block) and greps mcp-tests/*.md RESOLVING symlink + 64-byte-pointer targets (the Windows blindspot the prose grep missed). Promotes the mcp-coverage-audit.md algorithm to code (lazy_core.gate_coverage); the component points at this subcommand. Covered iff a scenario carries the decision id literal OR ≥2 keywords.
python3 lazy-state.py --apply-pseudo <name> <spec_path>    # SINGLE author of the deterministic pseudo-skill writes: __write_validated_from_{skip,results}__, __write_deferred_non_cloud__, __flip_plan_complete_cloud_saturated__ (pass --plan), __mark_complete__/__mark_fixed__ (receipt + SPEC/PHASES status flip + sentinel cleanup). Idempotent; refuses when gate inputs absent. __write_validated_from_results__ additionally gates on kind: mcp-test-results + result: all-passing + pass_count == total_count + validated_commit == current HEAD (legacy field-less files pass with a warnings[] entry) — NEVER hand-write VALIDATED.md. Optional: --plan/--apply-date/--reason/--deferred-step. unified-pipeline-orchestrator Phase 5: __mark_complete__ (feature path) now ALSO strikes the docs/features/ROADMAP.md row (moved IN from orchestrator-inline; returns roadmap_struck) and trims docs/features/queue.json by the RESOLVED spec_dir (returns queue_trimmed — kills the -followups queue.no-completed miss class). (__flip_plan_complete_stale__ stays orchestrator-inline.) COUNTER ADVANCE (lazy-batch-unified-driver-parity-and-accounting Phase 1, item 1): after a SUCCESSFUL forward-advancing pseudo-skill apply (name ∈ lazy_core._FORWARD_ADVANCING_PSEUDO_SKILLS = {__mark_complete__, __mark_fixed__, __write_validated_from_skip__, __write_validated_from_results__, __grant_skip_no_mcp_surface__, __flip_plan_complete_cloud_saturated__}), the handler calls lazy_core.advance_forward_cycle(...) so the inline pseudo-skill cycle advances forward_cycles — these cycles dispatch no Agent / no guard ALLOW / no registry consume, so the consume-gated advance_run_counters never advanced them. Marker-gated + fail-open (a breadcrumb, never blocks the apply).
python3 lazy-state.py --neutralize-sentinel <path>         # rename a resolved sentinel to <stem>_RESOLVED_<date><ext>, collision-safe (numeric suffix, never clobbers)
python3 lazy-state.py --repeat-count                       # fold a repeat_count field (consecutive identical-probe count, per-repo OS-temp signature file) into the probe JSON for mechanical loop detection; byte-identical default without the flag; folds/advances marker-persisted forward_cycles/meta_cycles counters when a run marker is present
python3 lazy-state.py --probe --forward-cycles N --meta-cycles M --max-cycles K  # fold git_guards (clean_tree/head_matches_origin/unpushed) + a pre-formatted cycle_header line into the probe JSON; byte-identical default without the flag; --repeat-count-peek reads marker-persisted counters without advancing them
python3 lazy-state.py --run-start                          # write the run marker to the state dir (pipeline=feature); gates registry writes and counter advances for this run; uses --cloud, --repo-root, --max-cycles when present; prints marker JSON and exits
python3 lazy-state.py --run-start --parent-run '{"repo_root": "<main>", "started_at": "<ts>"}'  # parallel-worktree-batch-execution (D2-A): stamp a LANE marker (written at a worktree root by the /lazy-batch-parallel coordinator) with the PARENT run's identity, so audits/--run-end sweeps can prove the lane marker sanctioned. Validated shape (JSON object with string repo_root + started_at; malformed → exit 2, zero side effects). Omitted → parent_run: null (serial runs byte-identical; the key is ALWAYS minted and classified RUN_FRESH_FIELDS). Mirrored on bug-state.py (coupled pair — the marker is shared).
python3 lazy-state.py --run-end                            # delete the run marker and the prompt registry from the state dir; call on every terminal run path; prints {"run_marker_deleted": true|false} and exits
# --- lazy-cycle-containment C1/C3 (cycle-subagent marker; same flags on bug-state.py, which uses --bug-id) ---
python3 lazy-state.py --cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]  # write the cycle-subagent marker (lazy-cycle-active.json, sibling of the run marker) immediately BEFORE every Agent dispatch; self-healing (overwrites a stale marker + logs); prints marker JSON. The marker carries feature_id/nonce/kind/started_at/session_id/commit_tally + (hardening-blind-to-process-friction Phase 2, additive) run_started_at (the live run marker's started_at snapshot — the stable run identity; null when no run is live) and begin_head_sha (git rev-parse HEAD snapshot; null on a non-git tree). These two power the --cycle-end process-friction detector. SIDE EFFECT (long-build-and-runtime-ownership Phase 4 / M5 Detect / LD4): BEFORE the marker write, runs lazy_core.reconcile_cycle_begin_git_consistency() — a pre-boot .git/index.lock (mtime older than the run marker's started_at boot stamp) ⇒ a previous op was torn ⇒ remove the stale lock + git clean -fdx the <repo_root>/target/release_staging dir; a fresh lock (mtime ≥ boot) is PRESERVED (live git op). Best-effort + FAIL-OPEN (no lock / non-git tree / no boot stamp / any error → no-op, never blocks the marker write). It makes NO commits and never touches the run marker, so it COMPOSES with the --cycle-end friction detector without false-tripping unexpected-commits/cycle-bracket-break. On a reconciliation the JSON carries git_consistency_reconciliation: {reconciled, removed_lock, staging_cleaned, reason}. Mirrored in bug-state.py (coupled pair; audited by lazy_parity_audit.py). GUARDED (cycle-subagent-runs-orchestrator-work Phase 2): refuse_cycle_marker_mutation_if_subagent("--cycle-begin") runs FIRST — a subagent (no LAZY_ORCHESTRATOR export, marker present) is refused exit 3 with zero side effects; the orchestrator (LAZY_ORCHESTRATOR=1) is allowed its self-healing overwrite. HARD ENFORCEMENT (adhoc-cycle-begin-real-requires-sub-skill, 2026-07-06): immediately after the id+nonce check, `--kind real` (the default) with a missing/blank `--sub-skill` now `_die()`s ("--cycle-begin --kind real requires --sub-skill") BEFORE any marker mutation — a real cycle marker can never be born `sub_skill=None`. `--kind meta` stays exempt (legitimately omits `--sub-skill`). This PROMOTES what used to be orchestrator-prose-only ("the /lazy-batch(-bug-batch) prose MANDATES --sub-skill", see `lazy_core.py:10990`) to a script-enforced write-side contract; the Round-3 read-side fail-open guard (`lazy_core.py:10972-10993`, `detect_cycle_bracket_friction` signal (b)) is RETAINED UNCHANGED as defense-in-depth for legacy/meta/degraded markers. Coupled-pair mirror on `bug-state.py` (`--bug-id`, same message text; parity-audited).
python3 lazy-state.py --cycle-end                          # clear the cycle marker immediately AFTER every Agent return (success/halt/error); idempotent; prints {"cycle_marker_cleared": true|false}. GUARDED (cycle-subagent-runs-orchestrator-work Phase 2): refuse_cycle_marker_mutation_if_subagent("--cycle-end") runs FIRST (before the friction check + clear) — a subagent cannot clear the marker (exit 3, zero side effects); the orchestrator clears its own bracket normally. SIDE EFFECT (hardening-blind-to-process-friction Phase 2 / D1): BEFORE clearing, runs cycle_end_friction_check() — resolves the CURRENT run identity + HEAD, calls detect_cycle_bracket_friction(), and on a torn bracket (run identity absent/changed since --cycle-begin → reason cycle-bracket-break) OR unexpected commits (HEAD advanced beyond the conservative per-sub_skill budget → reason unexpected-commits) appends a kind: process-friction entry to lazy-deny-ledger.jsonl. The runaway then self-announces as hardening debt: pending_hardening() counts it, the --emit-prompt probe withholds the forward route, and --run-end refuses — identical machinery to a guard deny. Fail-open: a degraded snapshot (no run marker / non-git tree) or a ledger-write error never blocks the clear, never false-positives. On a hit the JSON also carries process_friction: {reason, detail, ...}.
# C3 refuse-by-construction (agent_id-aware per hardening-blind-to-process-friction D4): --run-end/--run-start/--apply-pseudo/--enqueue-adhoc/--emit-dispatch REFUSE (exit 3, corrective stderr, ZERO side effects) for a SUBAGENT caller — they are orchestrator-only. refuse_if_cycle_active() decides in priority order: (1) LAZY_ORCHESTRATOR truthy → never refuse (structural immunity to a stale marker; fixes the orchestrator-self-deny defect), (2) LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal, no marker required), (3) else cycle marker present → refuse (legacy backstop carrier). The marker stays the fallback carrier because a Python subprocess cannot read the PreToolUse agent_id (hook-input-only); the C2 hook (lazy-cycle-containment.sh) uses agent_id directly. --neutralize-sentinel/--verify-ledger + all reads stay callable (a dispatched subagent needs them). The refused-op SCOPE is lockstep with the C2 PreToolUse hook deny-set (agent_id trip: /lazy* Skill invocations, nested /lazy-batch, LOOP_FORMATION_FLAGS routing, dev:kill/dev:restart; recursive Agent/Task was REMOVED from the C2 deny set 2026-07-09 — see docs/bugs/adhoc-containment-denies-mandated-explore-fanout).
# C3 marker-mutation guard (cycle-subagent-runs-orchestrator-work Phase 2, KEYSTONE): --cycle-begin/--cycle-end MUTATE the containment marker, so they CANNOT reuse refuse_if_cycle_active's marker-fallback (the orchestrator runs its OWN bracket while the marker is present — the marker can't protect itself). refuse_cycle_marker_mutation_if_subagent() guards them instead, keyed on the POSITIVE signal: (1) LAZY_ORCHESTRATOR truthy → allow (the orchestrator owns the bracket), (2) else LAZY_CYCLE_SUBAGENT truthy → refuse, (3) else cycle marker present without orchestrator env → refuse (the reachable subagent signal), (4) else (no marker, no subagent env) → allow (the genuinely-uncontained first --cycle-begin). REQUIRES the orchestrator to `export LAZY_ORCHESTRATOR=1` once per session (the three orchestrators do this at Step 0.55 before --run-start) — otherwise the orchestrator's own --cycle-end would be refused. These two ops are NOT in CYCLE_REFUSED_OPS; they ARE in the C2 hook LOOP_FORMATION_FLAGS (belt-and-suspenders) — C2/C3 deny scope stays lockstep (a subagent cannot clear/arm the marker at either layer).
```

Exit codes: `0` success (even if terminal), `2` malformed input (bad YAML/queue.json), `1` ledger/pseudo-skill failure (`--verify-ledger`/`--apply-pseudo`/`--neutralize-sentinel` not ok), `3` C3 cycle-containment refusal (an orchestrator-only op invoked while the cycle marker is present).

### Production-binding `ensure_runtime` test convention (mechanically guarded)

`ensure_runtime` is the load-bearing M4 runtime owner above, and its OS-signal
derivations (`restart`/`boot_alive`) have been re-derived round after round from
LIVE cold-boot incidents. A `test_ensure_runtime_production_*` test exists to
prove the PRODUCTION binding — so it MUST reach the signal under test exactly the
way production does, and is **mechanically guarded** against faking it:

- **Derive, never inject.** Reach the OS signal by swapping `lazy_core.subprocess`
  / `lazy_core.time` (and a `*_BOOT` config) and letting the DEFAULT `restart` /
  `boot_alive` closures derive it. The test MUST NOT pass `boot_alive=` or
  `restart=` to `ensure_runtime(...)` — injecting the derivation under test makes
  the test tautological (it asserts the value it handed in). The legitimate
  external-collaborator injections that ARE allowed (hermetic seams that do not
  short-circuit the signal): `probe`, `stale_check`, `sidecar_check`,
  `frontend_probe`, `read_lock`, `live_session_id`, `kernel_start_time_fn`,
  `sleep`, `write_lock`, `recover_identity`, `config`.
- **Spawn-binding tests use the faithful double.** A production test that
  exercises spawn RESOLUTION (asserts on `shell_spawns`) MUST drive
  `_WindowsSpawnSemanticsSubprocess` — the faithful double that raises for a
  bare-token no-shell argv and succeeds only for the `shell=True` string form
  (reproducing Windows `CreateProcess`/`npm.cmd`). It MUST NOT use the
  always-succeeds `_FakeSubprocess`, which succeeds for any argv and HIDES the
  real spawn defect (the false-green class that let two unit-green fixes ship a
  live-BLOCKED runtime). A liveness/timing test that only counts `.spawns`
  (not `shell_spawns`) may still use `_FakeSubprocess` — it is not spawn-binding.

**Enforcer:** the `--test` meta-tests in `test_lazy_core.py` —
`test_ensure_runtime_production_tests_derive_not_inject_signal` (signal-injection
guard) and `test_spawn_binding_production_tests_use_faithful_double` (faithful-double
guard), each with a negative-fixture twin proving non-vacuity. Pure AST collectors
(`_collect_production_binding_smells` / `_collect_spawn_double_smells`) mirroring the
`test_no_orphaned_test_functions` precedent — no standalone lint script. See
`docs/bugs/_archive/adhoc-ensure-runtime-test-injects-signal-under-test/`.

### Manual live cold-boot smoke (OPERATOR / NOT claude-config CI)

The `--test` guards above are hermetic AST discipline — they cannot prove the
production `restart()` actually launches a runtime, because that needs a real
checkout + a genuinely cold runtime. The ONLY thing that has ever caught the
spawn-invocation defect is a **live cold-boot smoke**, which is an
**operator/manual** step, NOT an in-repo CI assertion (environment-dependent):

```bash
# On a real AlgoBooth checkout with BOTH ports down and NO warm build (cold):
python3 user/scripts/lazy-state.py --ensure-runtime --repo-root <real-AlgoBooth-checkout>
# Confirm the verdict reaches state: READY (the cold compile is patiently waited
# on, NOT a false `mcp-runtime-unready` BLOCKED). This is the live verification
# Round 34 used to catch the platform-blind `npm` spawn.
```

Run this by hand against a cold runtime when changing `ensure_runtime`'s
spawn/boot-liveness path; do NOT wire it as a claude-config CI gate.

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
  - **Continuity is field-complete BY CONSTRUCTION** (adhoc-checkpoint-resume-field-complete-continuity,
    2026-06-23). The carry-vs-reset decision is no longer an implicit field-by-field list split
    across `write_run_checkpoint` (snapshot-set) and `restore_checkpoint_counters` (carry-set) —
    which made a newly-added run-scoped marker field default to RESET by construction (the
    whack-a-mole that reactively patched the counters, then `started_at`). Two enumerated frozensets
    in `lazy_core` are now the SSOT partition of the `write_run_marker` literal's run-scoped keys:
    **`RUN_CONTINUITY_FIELDS`** = `{forward_cycles, meta_cycles, started_at,
    per_feature_forward_cycles, per_feature_corrective_cycles}` (CARRIED across a sanctioned
    same-run pause) and **`RUN_FRESH_FIELDS`** = the rest (`last_advance_consume_count` deliberate
    reset + run-invariant identity/config re-derived at run-start). `write_run_checkpoint` snapshots
    the FULL continuity set as one nested `continuity: {field: value}` block (RAW marker read — never
    `read_run_marker`, whose age gate would delete a stale marker); `restore_checkpoint_counters`
    re-applies the whole block as one unit in the carry-forward branch, preserving every guard
    (operator-authorized no-op; `started_at` age gate; the two counters coerced non-negative; the two
    `per_feature_*` maps applied only when a well-formed dict; `last_advance_consume_count` forced 0).
    A **legacy fallback** (flat `run_started_at` + `counters`, no `continuity` block) still restores
    via the original path. A **`--test` completeness assertion**
    (`test_run_marker_continuity_partition_is_complete_and_disjoint`) pins `RUN_CONTINUITY_FIELDS |
    RUN_FRESH_FIELDS == _run_marker_scoped_keys()` (the live minted-marker key set) AND disjointness,
    so a new run-scoped marker key is a HARD test failure until explicitly classified — it can never
    silently default to reset. Shared `lazy_core`, so `bug-state.py` inherits it (parity-audited, not
    a script-mirror).
- **Hooks gate via `--marker-present`.** The three enforcement hooks
  (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`, `lazy-cycle-containment.sh`) no longer read
  the base-dir marker file directly. They call `lazy-state.py --marker-present --repo-root <cwd>`
  (read-only; exit 0 present / 1 absent) so Python owns ALL repo-key derivation. A marker for a
  *different* repo resolves to a different subdir → absent → the hook is a no-op. Fail-OPEN: a
  query error falls back to current behavior. The `pipeline_visualizer` likewise binds the
  visualized repo before reading the marker so it shows that repo's live run — SINGLE-REPO mode
  only.
  - **Fleet raw marker read (`cross-repo-fleet-view`).** `pipeline_visualizer --fleet` serves
    MANY repos from one `ThreadingHTTPServer`, where a per-request `set_active_repo_root` flip
    would be a data race and `read_run_marker` would DELETE a ≥24h marker as a side effect of
    *rendering* it. The fleet layer (`pipeline_visualizer/fleet.py`) therefore reads each
    marker RAW at the composed keyed path `~/.claude/state/<repo_key(root)>/lazy-run-marker.json`
    (the `write_run_checkpoint` precedent): never deletes, never writes, never creates state
    dirs (`claude_state_dir(create=True)` is banned on that path). Staleness is DISPLAYED
    (graded badge; `stale-marker` at the same `_MARKER_STALE_SECONDS` 24h boundary), never
    reclaimed — reclamation stays exclusively script-owned. Discovery unions the
    `~/source/repos/*/docs/{features,bugs}/queue.json` glob, `~/.claude/lazy-repos.json`
    (`{"pins": [...], "excludes": [...]}` — optional, user-local, fail-open on malformed; this
    is that file's first consumer, schema documented in `fleet.py`'s module docstring), and the
    `repo_root` fields recorded in live run markers.
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

## Concurrency plane — sanctioned parallel worktree lanes (`parallel-worktree-batch-execution`)

One repo = one lane was the rule; `/lazy-batch-parallel` (user-level skill) is the ONE
sanctioned exception — a coordinator that shards **dep-ready ∧ `independent: true`** feature
queue items across git worktree lanes while every existing arbitration rule applies verbatim
per lane. The machinery is the composition of `lazy_coord.py` (locks/leases/pool/ledger) with
`lazy_core`'s deterministic reads; the two modules never import each other.

- **Shard predicate (D3-A, conservative):** `lazy_coord.claim_shardable(candidates, leases_path)`
  over caller-computed booleans — dep-DAG readiness (`lazy_core.dep_completion_status` over the
  queue `deps` field, receipt-gated) ∧ the `independent: true` isolation marker
  (`lazy_core.parse_independent_marker`) ∧ no live lease. Missing/falsy ⇒ HELD, reason named
  (`dep-unready` / `no-independent-marker` / `live-lease`). NO file-overlap prediction — actual
  overlap is caught deterministically by git at merge time and demoted.
- **Lane identity (D2-A):** each worktree resolves its OWN `repo_key` state dir, so a lane
  marker is an ordinary run marker at the worktree root — born owner-bound to the coordinator
  session (`--session-id`), stamped `--parent-run '{repo_root, started_at}'` (the new marker key,
  ALWAYS minted, `null` on serial runs, classified `RUN_FRESH_FIELDS` — the continuity-partition
  completeness test enforces the classification), carrying its per-lane budget slice as
  `max_cycles`. `refuse_run_start_clobber`, the containment hooks, the sentinel-branch hook, and
  the `--cycle-end` friction detector all arm per lane with zero changes (the friction
  detector's HEAD snapshots are per state dir — fixture-proven no cross-trip).
- **Fencing (zombie-lane fail-safe):** one `lazy_coord` lease per claimed item; the coordinator
  heartbeats each lane cycle and calls `verify_fencing` before EVERY contended write. Fencing
  tokens are monotonic ACROSS reclamation/release via the sibling
  `lease-token-watermarks.json` (a defect fix — previously a reclaim deleted the entry and the
  re-claim minted `term_token 1` again, letting a zombie's stale token pass fencing;
  `leases.json`'s own schema is untouched so the visualizer keeps parsing).
- **Ledger (D7):** `lanes.json` (sibling of `leases.json`, coordinator-owned, written under the
  global lock via lazy_coord's own atomic write) records claims, lane branches, merge order,
  demotions (`demoted: serial`, branch PRESERVED), and parks (`sentinel_kind` +
  `sentinel_ported_to`). Read by `/lazy-status` lane rows and `/lazy-batch-retro` Step 6e (a
  demotion = a false-`independent`-marker audit finding).
- **Merge (D4):** queue-order only (`merge_order` — completion timing never changes history),
  coordinator-only, under the lock, after fencing; `merge_lane_branch` aborts on conflict (clean
  tree guaranteed) → demote to a serial re-run on the merged work branch, drawing from the SAME
  parent budget (D6: lanes = `min(requested, shardable, pool_size)`; per-lane slice =
  `min(remaining_parent, ceil(max_cycles/lanes))`; the operator-authorized `max_cycles` is the
  aggregate SSOT). The validation + completion tail (`--ensure-runtime`, `/mcp-test`,
  `__mark_complete__`, ROADMAP strike, queue trim, LAZY_QUEUE.md regen) is SERIAL at the main
  root — receipts land on the canonical tree.
- **Failure isolation (D5):** a lane halting on `NEEDS_INPUT.md`/`BLOCKED.md` parks (lease
  released, marker ended, branch + worktree kept) without touching siblings; its sentinel is
  ported VERBATIM to canonical `docs/features/<slug>/` at flush. Coordinator death recovers by
  construction: TTL reclaim scrubs slots, stale lane markers age out (24h), the ledger's audit
  trail survives — no manual `queue.json` repair.
- **Scope:** feature-pipeline only, workstation-only v1 (claude-config + AlgoBooth) — a
  documented justified divergence (no bug-pipeline mirror; `lazy_parity_audit.py` does not
  audit skill-family existence and stays exit 0). Heavy builds: existing machinery only (D8) —
  `build-queue.ps1` FIFO on Cognito-class repos, `long-build-ownership-guard.sh` takeover
  elsewhere.

> **Per-sub_skill commit budget is DERIVED, not a literal table
> (`adhoc-derive-cycle-commit-budget`, 2026-06-22).** `detect_cycle_bracket_friction`'s
> `unexpected-commits` budget (branch 3) is derived from the `lazy_core`-owned SSOT
> `_MULTI_COMMIT_DISPATCH_SKILLS` (a `frozenset` of the multi-commit dispatch identities)
> + the named ceiling `_CYCLE_COMMIT_MULTI = 3`: membership ⇒ the multi-commit ceiling, else
> `_CYCLE_COMMIT_BUDGET_DEFAULT = 1`. This REPLACED the reactive hand-maintained
> `_CYCLE_COMMIT_BUDGET` literal dict whose missing-row class false-positived `unexpected-commits`
> on every newly-dispatched multi-commit sub_skill (five reactive appends). Adding a new
> multi-commit dispatch skill now means adding its identity to the registry SSOT — co-located with
> the dispatch-skill set — NEVER a separate budget row. Single landing site in shared `lazy_core`;
> serves both pipelines; `budget_override` (Round 20) + `kind=="meta"` (Round 19) branches unchanged.

## Operator halt notifications (`operator-halt-notifications`)

Both state scripts page the operator's phone on attention-terminal halts via ONE shared,
script-owned notifier: `lazy_core.notify_halt(state, repo_root, pipeline=…)`, called as one line
in each script's `main()` immediately before the final state-JSON write (the terminal-emission
chokepoint — every halt from every producer passes through it). **Coupled-pair surface #7** in
`lazy_parity_audit.py::audit_state_script_parity` (the `lazy_core.notify_halt(` literal must be
present in BOTH scripts; `test_lazy_parity.py`'s lockstep stubs carry the token).

- **Config (opt-in; absent ⇒ the feature does not exist — byte-identical output, zero writes).**
  Untracked `~/.claude/notify.json` (NEVER symlinked into this repo; listed in the root
  `CLAUDE.md` untracked-secrets set): `{"channel": "ntfy", "url": "https://ntfy.sh/<topic>",
  "notify_on_clean_stop": false, "reping_hours": 6}`. `LAZY_NOTIFY_URL` env overrides the `url`
  (how cloud containers are provisioned); `LAZY_NOTIFY_DISABLE=1` is the kill switch (dominates
  everything). `reping_hours` is accepted but INERT in v1 — the ledger schema (`notified_at`) is
  re-ping-ready, so wiring it later is a pure additive change (D4-B).
- **Event scope (D3).** `lazy_core._NOTIFY_ATTENTION_TERMINALS` (the default paging set — the
  terminals where the operator's action is the unblocker): `blocked`, `blocked-misnamed`,
  `needs-input`, `needs-spec-input`, `needs-research`, `queue-blocked-on-research`,
  `completion-unverified`, `stale_upstream`, `queue-exhausted-all-parked`,
  `queue-exhausted-budget-deferred`, `queue-missing`. A SIBLING of `SANCTIONED_STOP_TERMINAL`,
  NOT its complement, and deliberately distinct from the 6-element telemetry
  `TELEMETRY_HALT_TERMINAL_REASONS` (different vocabularies: telemetry records halt-dwell, notify
  pages for action). Clean stops (`_NOTIFY_CLEAN_STOP_TERMINALS`: `all-features-complete`,
  `all-bugs-fixed`, `cloud-queue-exhausted`, `device-queue-exhausted`,
  `host-capability-saturated`) page only under `notify_on_clean_stop: true`. Terminals in neither
  set (e.g. `queue-exhausted-dependency-gated`, the scoped per-item terminals) never page. The
  orchestrator §1c.6 `PushNotification` prose policy is UNTOUCHED — additive channels.
- **Dedup (D4/D8).** Notify-once per sentinel identity — sentinel-backed terminals key on
  `(pipeline, item, reason, mtime_ns, size)`; sentinel-less terminals on the UTC date. Ledger:
  `notify-ledger.json` in the per-repo keyed `claude_state_dir()` (hermetic under
  `LAZY_STATE_DIR`), written via `_atomic_write`, entries >30 days dropped on write, updated ONLY
  on a successful send (a failed send retries on the next observation). `--neutralize-sentinel`'s
  rename retires the identity; a re-halt's fresh sentinel re-arms. Read-only probes
  (`/lazy-status`, `lazy-queue-doc.py`, `pipeline_visualizer`) re-observe halts every refresh —
  the ledger caps each halt at one page.
- **Payload (D5).** title = the state's `notify_message` verbatim; body = repo basename ·
  pipeline · item id · halt kind + (needs-input) the frontmatter `decisions:` one-liners via a
  TOLERANT frontmatter read (NOT `parse_sentinel`, which would `_die()` on a malformed file and
  corrupt the halt JSON) + the `LAZY_QUEUE.md`/answer-path pointer; link = normalized GitHub
  remote (`git config --get remote.origin.url`, SSH→HTTPS) + `/tree/main/<item dir>` — derivation
  failure ⇒ link omitted, still sends. v1 channel = ntfy (`_ntfy_send`: one stdlib urllib POST,
  `timeout=5`, RFC-2047-encoded Title/Click headers for non-latin-1) behind the injected
  `sender(title, body, link)` seam (tests inject fakes; a future Pushover/GitHub channel is a
  config value, not a rewrite).
- **Failure semantics (D9 — fail-OPEN, absolute).** `notify_halt` never raises, never prints to
  stdout, never changes the exit code, and never mutates the state dict on the inert path. A send
  failure overwrites the `notify-error.json` breadcrumb (state dir; the `hook-error.json`
  pattern) and appends a "why no page" line to `state["diagnostics"]` (the dict's own list — a
  post-compute `_diag()` never reaches the printed JSON). Environment-agnostic (D10): no
  `--cloud` branch.
- **Tests.** `test_lazy_core.py` notify suite (11 cases, `_TESTS`-registered) + a
  `[notify-halt-call-site]` in-file `--test` fixture in EACH script (drives `main()` in-process:
  one page, dedup on re-probe, kill switch byte-inert — the wiring itself, not a re-mock).

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
- **Gate:** `python lazy_coord.py --test` (21 fixtures). Because the scoping flags touch both state
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
