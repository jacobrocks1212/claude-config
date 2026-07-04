# Research — Scheduled Autonomous Runs (Overnight Builder)

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **The harness pre-built for this feature.** `lazy-state.py` carries `--unattended` on
  `--run-start` (~line 9164) with in-source comments naming the exact use case: "pass at
  --run-start for scheduled/cron invocations"; `lazy_core.write_run_marker` records
  `attended: bool` (~line 9297) and the `--run-end` stop-authorization gate reads it (an attended
  run cannot checkpoint-stop without operator auth; an unattended one can). `/lazy-batch-cloud`
  Step 0 ALREADY passes `--cloud --run-start --unattended --max-cycles {max_cycles}` (SKILL.md
  ~line 227). The scheduled-run half of the contract has been sitting armed with no scheduler
  attached — which is why the SPEC's technical design expects zero state-script changes.
- **Arbitration (verified, the stub's "verify don't rebuild"):**
  `lazy_core.refuse_run_start_clobber` (~line 10694) — raw marker read; cross-pipeline live+fresh
  marker ⇒ always refuse (exit 3, zero side effects, stderr names the in-flight run);
  same-pipeline ⇒ refuse unless `lazy-run-checkpoint.json` sanctions a resume (non-destructive
  existence check); >24h markers (`_MARKER_STALE_SECONDS = 24*3600`, ~line 6459) are presumed-dead
  and freely overwritten; corrupt/unreadable markers fail-open. Per-repo keyed state dirs
  (`claude_state_dir()` → `~/.claude/state/<repo_key>/`) isolate repos
  (`multi-repo-concurrent-runs`); markers are born owner-bound
  (`single-slot-marker-ownership-race-disarms-owning-run`). The one interaction worth documenting
  (SPEC D6): a hard-crashed overnight run's marker is <24h old at the next nightly fire, so the
  next night refuses too — one lost night per hard crash, recovered by a morning `--run-end`.
- **The orchestrator's own unattended affordances:** `--park`
  (`--park-needs-input --park-blocked`) parks halted items into `parked[]` and advances the queue,
  flushing at run end (WU-4 flush; `queue-exhausted-all-parked` is the honest all-parked
  terminal); `meta_cycles` uncapped / `forward_cycles` capped at `max_cycles` (operator decision
  2026-06-14); dependency-aware research skip-ahead is default-on with the gated head surfaced in
  `gated_heads`; `--run-end` is MANDATORY on every terminal path (§1c.6 point 2) with 24h
  self-healing for misses; checkpoint-resume counter semantics distinguish operator-authorized
  (fresh budget) from automatic reliability resume (monotonic carry — cannot exceed the
  authorized budget).
- **Cloud terminal set + deferral:** `cloud-queue-exhausted` is the NORMAL cloud stop (every
  remaining feature awaits workstation MCP); `__write_deferred_non_cloud__` writes
  `DEFERRED_NON_CLOUD.md` per feature via `--apply-pseudo` (script-owned single author); the
  workstation pipeline re-opens deferred items with no special handling and completion stays
  receipt-gated (`COMPLETED.md` only via `__mark_complete__`). This bounds what "overnight
  builder" can honestly claim — the SPEC's D7 names the morning workstation flush as part of the
  contract rather than hiding it.
- **The morning read surface:** `LAZY_QUEUE.md` (mobile-queue-control, Complete) is regenerated
  by `lazy-queue-doc.py` at each cycle commit and rides the existing push to `main` in exactly the
  two repos that qualify (claude-config + AlgoBooth, Decision 6) — which is also the SPEC D2
  qualifying-repo set for nightly runs.
- **Platform trigger contract (verified platform facts, treated as implemented):** scheduled
  triggers with 5-field `cron_expression` (minimum interval hourly), one-shot `run_once_at`,
  three targeting modes (resume-this-session / fire-into-named-persistent-session /
  `create_new_session_on_fire` fresh session per fire), per-routine completion notifications
  (push and/or email — fresh-session-per-fire routines only), on-demand `fire_trigger` with
  appendable run-specific text, plus list/update/delete management ops. Fresh-session prompts
  must be complete standalone instructions.

## External prior art & concepts

(Training-knowledge, not live research — stated honestly.)

- **Nightly CI / scheduled workflows** (GitHub Actions `schedule:`, Jenkins nightly builds):
  long-standing convention that unattended runs get (a) a bounded budget/timeout, (b) a morning
  artifact/notification rather than interactive prompts, and (c) concurrency controls
  (`concurrency:` groups / build locks) so a scheduled run never races a manual one. The SPEC maps
  these onto `max_cycles`, the composed morning report, and `refuse_run_start_clobber`
  respectively.
- **"Don't page on success" / notification hygiene:** scheduled-job practice distinguishes
  completion notices (quiet channels — email/digest) from actionable alerts (pages). Mirrored in
  SPEC D5: completion push per fire, halt PAGES only via the sibling feature's attention set.
- **Cron + lock-file arbitration** (`flock`-guarded cron jobs): the standard pattern where a
  still-held lock makes the next scheduled invocation exit honestly rather than force-start. The
  run marker is exactly this lock, with a 24h presumed-dead reclaim — the SPEC documents rather
  than re-derives the trade-off (a conservative lock loses at most one cadence interval after a
  crash).
- **Fresh-environment-per-run** (ephemeral CI runners, "pets vs cattle"): starting each scheduled
  run from a clean session avoids state accumulation and wedged-worker poisoning — the reasoning
  behind preferring `create_new_session_on_fire` over a persistent nightly session, and consistent
  with the harness's own "state lives on disk, never in the transcript" doctrine.

## Alternatives analysis

- **Trigger mechanism (D1).** Platform trigger vs persistent-session fire vs OS cron + headless
  CLI. The platform trigger wins on composition: it exists, it carries completion notifications
  ONLY in fresh-session mode, and it inherits the cloud environment's credentials. OS cron on the
  workstation would unlock overnight MCP validation but means building a second scheduling stack
  (Task Scheduler, wake policy, headless auth) and maximizes collision likelihood with the
  operator's own interactive machine — kept as a documented vN path, not v1.
- **Registry shape (D2).** Trigger-per-repo vs iterating list. The decisive point: the trigger
  store already IS a registry (named, enumerable, individually enable/disable-able, per-cadence),
  and per-repo triggers keep the per-repo marker model trivially correct. An iterating single
  session would serialize repos (overrun starvation), mix repo state in one session, and require
  inventing a config file — three costs for one convenience.
- **Budget (D3).** 10 matches the orchestrator's own default and bounds the morning review
  burden, which — not compute — is the real constraint on unattended throughput. Research skip is
  deliberately NOT enabled: research is a human-priority decision, and the default strict halt +
  skip-ahead already lets the rest of the queue proceed.
- **Unattended halts (D4).** `--park` vs default vs a new unattended-flush prose variant. Default
  mode burns the night on the first ambiguous decision. `--park` is the existing, specified
  unattended posture (with the D2 two-key auto-accept already governing what may self-resolve).
  The only open mechanics question is whether the end-of-run flush's `AskUserQuestion` survives
  overnight in a trigger-fired session — an empirical pilot check, with the prose-variant fallback
  (skip the ask, leave sentinels, page) deliberately NOT pre-built to avoid speculative coupled-
  skill divergence.
- **Morning report (D5).** Compose vs new artifact. Every candidate element of a run-summary
  artifact already exists somewhere (final batch report in the transcript, state in
  `LAZY_QUEUE.md`, events in notifications); a committed nightly artifact would add a retention
  and lint surface before demonstrating incremental value. Deferred, not rejected.
- **Crashed-run staleness (D6).** Keeping 24h vs shortening for unattended markers: shortening
  touches every marker consumer for a failure mode whose observed frequency is currently zero and
  whose cost is one lost night, honestly notified. Data before surgery.

## Pitfalls & risks

- **The held-open flush question may not survive to morning** (session reclaim in fresh-fire
  cloud sessions). If Phase 1 shows this, D4 falls back to its option C (unattended flush variant)
  — a real coupled-skills change that must go through its own needs-input round; the SPEC scopes
  it out rather than smuggling it in.
- **Unreviewed-change accumulation.** Ten cycles/night × N repos can outrun morning review. The
  budget default (D3) is the throttle; the friction-KPI/retro machinery — not this spec — is where
  a sustained mismatch should surface. If mornings become rubber-stamping, lower the budget: the
  feature's value claim is progress the operator actually absorbs.
- **Silent no-op nights.** A refused `--run-start` (live/crashed marker) that nobody notices
  would quietly turn the feature off. Mitigated: completion notifications fire per-fire regardless
  (D5), and the trigger prompt instructs the session to report a refusal verbatim; Phase 2 drills
  both refusal paths.
- **Marker leakage cadence trap.** Nightly cadence sits just inside the 24h staleness window —
  the one-lost-night behavior is acceptable but MUST stay documented, or a future "why didn't it
  run twice?" investigation re-derives it expensively. The SPEC's D6 + UX failure table carry it.
- **Cloud push failure.** The whole morning-report loop assumes push-to-`main` works from a
  trigger-fired session; if the environment's credentials rot, cycles still run but nothing
  publishes. Phase 1 verifies; the orchestrator's own commit-policy failure handling halts
  honestly otherwise.
- **Scope creep toward full automation.** The deferred-non-cloud flush, auto-answering parked
  decisions, and workstation scheduling are each one step away. All three are explicitly deferred
  (D7, D4, D1-C) — the falsifiable v1 claim is narrow: "queues drain overnight within budget, and
  the operator learns everything material by breakfast." Measure it by comparing queue-state
  deltas per night (git history of `LAZY_QUEUE.md`) against operator time spent; if nights
  produce mostly parked items and refusals, the feature is dead weight and the retro should say
  so.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 trigger mechanism | platform scheduled trigger, fresh session per fire | high (OPEN — operator call) |
| D2 opt-in shape | one named trigger per opted-in repo; staggered cron slots | high (OPEN — operator call) |
| D3 nightly budget | `max_cycles=10`, no research skip, per-feature guard un-armed | medium-high (OPEN — operator call) |
| D4 unattended halts | `--park`; flush waits for morning; prose variant only if pilot forces it | medium (OPEN — operator call; pilot-informed) |
| D5 morning report | compose push/email + LAZY_QUEUE.md + halt pages + transcript; no new artifact | high (OPEN — operator call) |
| D6 collision safety | rely on `refuse_run_start_clobber` + 24h staleness; document crash interaction | high (auto-accepted) |
| D7 deferred-non-cloud | no automation; workstation flush named in the morning contract | high (auto-accepted) |
| D8 credentials/env | reuse each repo's existing cloud environment; verify push at pilot | high (auto-accepted) |
| D9 trigger management | platform ops via chat + documented recipes; no wrapper script | high (auto-accepted) |
