# Scheduled Autonomous Runs (Overnight Builder) — Feature Specification

> Wire `/lazy-batch-cloud` to the platform's scheduled triggers so opted-in repos drain their lazy
> queues nightly in fresh cloud sessions, with a bounded budget per fire. All of the safety
> machinery already exists — `refuse_run_start_clobber` arbitration, the `--unattended` run marker,
> `--park` halt-parking, per-cycle `LAZY_QUEUE.md` commits — so this feature is scheduling glue plus
> an honest morning-report contract: the operator wakes to a routine completion notification, a
> `LAZY_QUEUE.md` diff on GitHub mobile, halt pages for anything needing a decision (sibling
> `operator-halt-notifications`), and a workstation flush of the cloud run's `DEFERRED_NON_CLOUD.md`
> items. Verify, don't rebuild: no new arbitration, budget, or containment code.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:**
- operator-halt-notifications — soft — the morning-report story leans on halt paging for anything needing a decision, but scheduled runs function without it (halts surface in LAZY_QUEUE.md and the session transcript).

> Substantive (non-block) dependencies are **implemented contracts, not sibling specs**:
> - `/lazy-batch-cloud` (`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`) — the
>   autonomous cloud orchestrator this feature invokes verbatim: `max-cycles` budget arg,
>   `--park` mode, the cloud terminal set (`cloud-queue-exhausted` as the normal stop), the
>   §1c.6 notification policy, and the mandatory `--run-end` on every terminal path.
> - `--run-start --unattended` (`lazy-state.py` ~line 9164; `write_run_marker(attended=False)`,
>   `lazy_core.py` ~line 9297) — the marker field the harness ALREADY carries "for scheduled/cron
>   invocations"; `/lazy-batch-cloud` Step 0 already passes it.
> - `lazy_core.refuse_run_start_clobber` (+ per-repo keyed markers, 24h `_MARKER_STALE_SECONDS`)
>   — the arbitration that keeps a scheduled fire from clobbering a live run. Verified, not
>   rebuilt (see D6).
> - `LAZY_QUEUE.md` per-cycle commits (`mobile-queue-control`, Complete) — the morning read.
> - **Platform trigger contract (implemented, composed with — not built):** scheduled triggers
>   with 5-field `cron_expression` (minimum interval hourly), one-shot `run_once_at`, three
>   targeting modes (resume-this-session / fire-into-named-persistent-session /
>   `create_new_session_on_fire` fresh session per fire), per-routine completion notifications
>   (push and/or email — fresh-session routines only), and on-demand `fire_trigger` with
>   appendable run-specific text.

---

## Executive Summary

Batch runs start only when the operator starts them; overnight hours are unused even though the
pipeline was built for unattended operation — honest halts, receipt-gated completion, cycle budgets,
containment hooks, and a run-marker arbitration layer that already distinguishes attended from
unattended runs (`write_run_marker(attended=...)` exists precisely "for scheduled/cron
invocations"). The missing piece is purely the scheduler and the operating contract around it:
what fires, with what budget, how collisions with live interactive runs resolve, and what the
operator reads in the morning.

The recommended shape: one platform scheduled trigger per opted-in repo, `create_new_session_on_fire`
so each night starts from a clean slate, whose prompt invokes `/lazy-batch-cloud <N> --park` (the
cloud orchestrator is the one designed for exactly this environment — it defers MCP/device work via
`DEFERRED_NON_CLOUD.md` and treats `cloud-queue-exhausted` as a normal stop). `--park` keeps one
ambiguous decision from stalling the whole night: needs-input and blocked items are parked, the
queue advances, and the parked set is flushed at run end. The morning report is compositional, not
new machinery: the routine's completion notification (push/email), the `LAZY_QUEUE.md` diff the
run's per-cycle commits already push to `main`, halt pages from the sibling feature, and the fresh
session's transcript for drill-in. A morning workstation `/lazy-batch` remains the flush path for
whatever the cloud deferred.

This serves the **efficient** mission criterion (idle hours become queue progress at zero operator
cost) while leaning on **effective** guarantees that already exist — every safety property cited
here is verified against current code, and the one genuine gap found (a crashed overnight run's
<24h marker refusing the next night's fire) is documented and handled honestly rather than papered
over with new arbitration.

## Design Decisions

### D1. Trigger mechanism

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04)`
- **Question:** What actually starts the nightly run? This determines where credentials live,
  what survives a crash, and what the operator manages.
- **Options:**
  - **A — platform scheduled trigger, fresh session per fire (Recommended):** a cron-expression
    trigger with `create_new_session_on_fire: true` in the repo's cloud environment; each firing
    spawns a clean session whose prompt is a complete standalone instruction invoking
    `/lazy-batch-cloud <N> --park`. Pros: exists today (verified platform contract — cron min
    hourly, one-shot `run_once_at`, on-demand `fire_trigger` for reruns); fresh sessions match the
    orchestrator's own "restart from a fresh session" advice at max-cycles; per-routine completion
    notifications (push/email) come free and ONLY exist in this mode; credentials are the cloud
    environment's existing repo access. Cons: cloud-only execution (MCP work defers — but that is
    `/lazy-batch-cloud`'s designed behavior); prompt must be self-contained.
  - **B — fire into a named persistent session:** trigger resumes one long-lived session nightly.
    Pros: accumulated context. Cons: exactly what the harness distrusts — state must live on disk,
    not in a transcript; context bloat/compaction across nights; no completion notifications in
    this mode; a wedged session poisons every subsequent night.
  - **C — OS cron / Windows Task Scheduler invoking headless CLI on the workstation:** e.g. a
    scheduled `claude -p "/lazy-batch <N> --park"`. Pros: workstation capabilities (MCP
    validation) overnight. Cons: builds and maintains a second scheduling stack (Task Scheduler
    XML, wake-from-sleep, headless-auth); the workstation is also the operator's interactive
    machine, so collision with a left-open session is likeliest exactly here; nothing about it is
    "verify don't rebuild".
- **Recommendation:** A — it is the only option that is pure composition with implemented
  contracts (trigger + `/lazy-batch-cloud` + completion notifications). C remains a documented vN
  path if overnight MCP validation ever matters more than simplicity.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Platform
  scheduled trigger, fresh session per fire. OS cron (option C) is documented as REJECTED for v1
  and remains only a vN path if overnight MCP validation ever outweighs simplicity.

### D2. Per-repo opt-in shape

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04)`
- **Question:** Which repos get nightly runs, and where is that declared — one trigger per repo,
  or one trigger iterating a repo list?
- **Options:**
  - **A — one trigger per opted-in repo (Recommended):** each repo that qualifies (cloud
    environment exists; works on and pushes to `main` so `LAZY_QUEUE.md` publishes — today
    claude-config and AlgoBooth, per mobile-queue-control Decision 6) gets its own named trigger
    (`nightly-lazy-<repo>`), its own cron slot, its own budget. The trigger list IS the registry
    (`list_triggers` enumerates it; enable/disable per repo via `update_trigger`). Pros: per-repo
    marker arbitration stays trivially correct (one run per repo per night, staggered slots);
    per-repo budgets; disabling one repo touches nothing else. Cons: N triggers to manage — at
    the current N=2, negligible.
  - **B — one trigger iterating a repo list:** a single nightly session walks
    `~/.claude/lazy-repos.json`-style config sequentially. Pros: one thing to manage. Cons: a
    serial chain where repo 1's overrun eats repo 2's night; one session mixing repos fights the
    per-repo keyed state-dir and marker model; a mid-chain crash silently skips the tail; and a
    new registry file must be invented — against verify-don't-rebuild.
- **Recommendation:** A — the trigger store already provides naming, enable/disable, cadence, and
  enumeration; a config-file registry would duplicate it. Stagger cron slots (e.g. 01:00 / 03:00)
  so two repos' pushes and notifications don't interleave confusingly.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). One named
  trigger per opted-in repo (`nightly-lazy-<repo>`), staggered cron slots (01:00 / 03:00 UTC),
  the trigger list IS the registry (`list_triggers`).

### D3. Nightly budget default

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04)`
- **Question:** What `max-cycles` (and companion flags) does a nightly fire pass? The budget is a
  trigger-prompt parameter, so it is per-repo tunable — this decision sets the default.
- **Options:**
  - **A — `max_cycles=10`, no research skip, guard un-armed (Recommended):** matches
    `/lazy-batch-cloud`'s own default of 10; `forward_cycles` is capped, `meta_cycles` uncapped
    (existing operator decision 2026-06-14); `--allow-research-skip` NOT passed (a needs-research
    head halts honestly — research is a human step, and skipping it silently reorders the
    operator's priorities overnight); `--per-feature-cycle-cap` not armed (whole-run cap is the
    sole default budget, matching the flag's documented default-off). Pros: a bounded,
    predictable night that ends with `--run-end` on a known terminal. Cons: a deep queue may need
    several nights — acceptable; the cadence is nightly.
  - **B — high budget (e.g. 30):** more progress per night. Cons: more unreviewed change per
    morning; the morning review burden, not the compute, is the real constraint.
  - **C — small budget (e.g. 5):** minimal blast radius. Cons: fixed per-cycle overhead (run
    start, probes, report) becomes a large fraction of the night.
- **Recommendation:** A — start at the skill's own default; tune per repo by editing the trigger
  prompt once real morning-review data exists (the friction-KPI story, not this spec).
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Nightly budget
  is `/lazy-batch-cloud 10 --park`; `--allow-research-skip` NOT passed; per-feature cycle cap
  un-armed.

### D4. Unattended halt posture (`--park` and the end-of-run flush)

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04)`
- **Question:** With nobody awake to answer `AskUserQuestion`, what happens when a cycle hits
  `needs-input`/`BLOCKED`? Without `--park`, Step 1g/1h fire an interactive question on the FIRST
  ambiguous decision and the run effectively stops there for the night.
- **Options:**
  - **A — run with `--park`; the flush waits for morning (Recommended):** `--park` passes
    `--park-needs-input --park-blocked` to the probes, so halted items are parked into `parked[]`
    and the queue advances past them; at `queue-exhausted-all-parked` (or the run's normal
    terminal) the Step 1g-flush surfaces every parked decision via the batched `AskUserQuestion`.
    Unattended, that question simply sits in the fresh session until the operator opens it in the
    morning and answers — the honest caveat is that the session (and its pending question) must
    still be open/resumable then, and the D2 two-key auto-accept remains park-mode's existing,
    already-specified relaxation for genuinely mechanical decisions. Pros: one ambiguous decision
    no longer costs the whole night; the flush is the morning's single decision inbox; zero new
    prose. Cons: parked-item resolution latency is "next morning" by design.
  - **B — default mode (no `--park`):** the night ends at the first product decision, with the
    question pending. Pros: strictest human-in-the-loop. Cons: wastes the night's remaining
    budget on exactly the runs where the operator is guaranteed absent.
  - **C — a new unattended flush variant (skip `AskUserQuestion`; leave sentinels + page):** the
    run ends cleanly with parked sentinels on disk and pages via the sibling feature; morning
    resolution happens in a fresh session. Pros: no pending question held open overnight. Cons: a
    prose divergence across the coupled batch skills keyed on the marker's `attended` field —
    real design work, and redundant if A's held-open flush proves workable in the Phase 1 pilot.
- **Recommendation:** A, empirically validated in the pilot (does an unanswered flush survive to
  morning in a fresh-fire session?); C is the documented fallback if it does not.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Run with
  `--park`; the morning flush waits in the fired session. Option C (unattended-flush variant) is
  documented as the pilot-contingent fallback ONLY — it becomes its own coupled-skills change with
  a fresh needs-input round if the Phase-1 pilot shows the held-open flush does not survive.

### D5. Morning report & failure/no-op notification policy

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04)`
- **Question:** What does the operator read at breakfast, and what does a bad night (immediate
  halt, refused start, zero progress) look like — a page, an email, or just the queue doc?
- **Options:**
  - **A — compose existing surfaces; routine push notifications on (Recommended):** (1) the
    routine's per-fire completion notification (push; email optionally) — fires on EVERY fire
    including a no-op/refused one, so "no notification" cleanly means "the trigger didn't fire";
    (2) the `LAZY_QUEUE.md` diff on GitHub mobile (per-cycle commits pushed to `main`; GitHub's
    native last-commit time is the freshness signal); (3) halt pages from
    `operator-halt-notifications` for anything needing a decision (soft dep — until it lands,
    halts surface via 1 and 2); (4) the fired session's transcript for drill-in. A run that
    immediately halts (needs-research head, `--run-start` refusal) is therefore an ordinary
    completion notification whose summary says so — notified, not paged, unless the sibling
    feature's attention terminals fire. No new run-summary artifact in v1.
  - **B — add a committed per-run summary artifact (e.g. `docs/nightly/<date>.md`):** durable
    morning report in-repo. Cons: a new committed artifact class with retention/lint questions;
    largely duplicates the transcript + LAZY_QUEUE.md + the batch report the orchestrator already
    prints; defer until composition demonstrably falls short.
  - **C — email-only digest:** quiet mornings. Cons: loses the same-app tap-through flow the rest
    of the mobile story is built on.
- **Recommendation:** A — every element already exists; the only knob to set is the routine's
  notification channels (push on; email per operator taste).
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Morning report
  composes existing surfaces: completion push + `LAZY_QUEUE.md` diff + halt pages + transcript;
  NO new committed run-summary artifact in v1.

### D6. Collision safety — verify existing arbitration, don't rebuild

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Can a scheduled fire clobber a live interactive run, and what happens after a
  crashed overnight run? (Stub constraint: rely on existing arbitration; verify, don't rebuild.)
- **Options:**
  - **A — rely on `refuse_run_start_clobber` + 24h staleness as-is; document the crashed-run
    interaction (Recommended):** verified semantics (`lazy_core.py` ~line 10694): a live,
    age-fresh marker refuses a second `--run-start` — cross-pipeline always; same-pipeline unless
    a `lazy-run-checkpoint.json` sanctions a resume — with exit 3, zero side effects, and stderr
    naming the in-flight run. So a scheduled fire can never clobber a live evening run; it
    refuses, and D5's completion notification reports the refusal. The documented residual: a
    HARD-crashed overnight run (container reclaim before `--run-end`; the orchestrator otherwise
    runs `--run-end` on every terminal path per §1c.6) leaves a marker that is <24h old at the
    next nightly fire (`_MARKER_STALE_SECONDS = 24*3600` vs ~24h cadence, minus the crash-to-fire
    gap) — so the NEXT night also refuses, and the morning recovery is the operator ending the
    dead run (`lazy-state.py --run-end` in that repo) after confirming it is dead. At nightly
    cadence the worst case is one lost night per hard crash, surfaced by notification.
  - **B — shorten staleness for unattended markers (e.g. 12h):** auto-heals within one cadence.
    Cons: rebuilds arbitration semantics the stub says to trust; a 12h threshold starts reclaiming
    markers of legitimately long attended runs; touching `_MARKER_STALE_SECONDS` has blast radius
    across every consumer (`read_run_marker` path A, reclaim logic, hooks).
  - **C — pre-run force-clean (`--run-end` before `--run-start` in the trigger prompt):** always
    starts. Cons: deletes a LIVE run's marker — precisely the clobber the arbitration exists to
    refuse; disqualified.
- **Recommendation:** A — the arbitration is correct for the dangerous case (live run protected)
  and merely conservative for the crashed case (one lost night, honestly reported). Revisit B only
  with observed crash frequency data.
- **Resolution:** Auto-accepted A; this is verification + documentation of implemented behavior,
  not an operator-visible choice — the stub itself locks "verify, don't rebuild".
  **LOCKED by operator 2026-07-04:** rely on `refuse_run_start_clobber` + 24h staleness as-is;
  document the crashed-run interaction (see `PLAYBOOK.md`).

### D7. Deferred-non-cloud handoff (the honest half of "overnight builder")

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Cloud runs defer MCP/device steps per feature via `__write_deferred_non_cloud__`
  (`DEFERRED_NON_CLOUD.md`), ending at `cloud-queue-exhausted`. Does this feature automate the
  workstation flush?
- **Options:**
  - **A — no automation in v1; document the handoff (Recommended):** the morning contract states
    it plainly: the night produces spec/plan/implementation progress; MCP validation and
    completion (`VALIDATED.md` → `__mark_complete__`) still happen in a workstation
    `/lazy`/`/lazy-batch` session, which re-opens deferred items through the existing Step 9/10
    flow with zero special handling. The `LAZY_QUEUE.md` "Needs attention"/state columns make the
    deferred set visible. Pros: zero new machinery; the handoff path is the one every cloud run
    already uses. Cons: completion latency includes a workstation session — inherent to cloud
    capability, not to scheduling.
  - **B — schedule a workstation flush too:** requires D1 option C's whole stack; out of scope.
- **Recommendation:** A — misrepresenting nightly cloud runs as full completion would violate the
  receipt-gated completion invariant; the spec instead names the workstation flush as part of the
  morning routine.
- **Resolution:** Auto-accepted A; describes existing pipeline behavior rather than choosing new
  operator-visible behavior. **LOCKED by operator 2026-07-04:** no deferred-non-cloud automation
  in v1; the workstation flush path is documented (see `PLAYBOOK.md` morning triage).

### D8. Credentials & environment provisioning

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What must the cloud environment carry for a nightly fire to work?
- **Options:**
  - **A — reuse the repo's existing cloud environment (Recommended):** the trigger fires into the
    same environment interactive cloud sessions use, which already has repo access and push-to-
    `main` rights (the per-cycle commit + `LAZY_QUEUE.md` publish depend on push working — already
    true for the two target repos). Additions: the notify-channel env var
    (`operator-halt-notifications` D7) when that sibling lands. Verify at pilot: push actually
    succeeds from a trigger-fired fresh session, and the session start lands on `main` (Step 0
    preconditions of the orchestrator do their own branch/tree checks and halt honestly if not).
  - **B — dedicated scheduled-run environment:** isolation. Cons: a second credential surface to
    rot with no threat model requiring it.
- **Recommendation:** A — one environment per repo, shared between interactive and scheduled use;
  the run-marker arbitration (D6) is what serializes them, not environment separation.
- **Resolution:** Auto-accepted A; invisible provisioning detail. **LOCKED by operator
  2026-07-04:** reuse the repo's existing cloud environment.

### D9. Trigger management surface

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How are the triggers created/inspected/paused — new tooling or the platform CLI
  surface via chat?
- **Options:**
  - **A — manage via chat with the platform's trigger ops; document the recipes (Recommended):**
    create/update/list/delete/fire-on-demand are existing platform operations; this repo carries
    the canonical prompt template and recipes (in this SPEC + `workspace/CLAUDE.md` pointer), not
    a wrapper script. `fire_trigger` with appended text doubles as the "run tonight's job now,
    with this extra context" lever.
  - **B — a registry/wrapper script in `user/scripts/`:** deterministic listing. Cons: wraps a
    remote platform API from a stdlib-only pipeline script — new credential + API surface for
    what `list_triggers` already answers in chat.
- **Recommendation:** A — the trigger store is the source of truth (consistent with D2); scripts
  own on-disk state, not remote platform state.
- **Resolution:** Auto-accepted A; tooling-shape choice with no behavioral surface. **LOCKED by
  operator 2026-07-04:** manage triggers via chat platform ops; recipes documented in
  `RECIPES.md`; NO wrapper script.

## User Experience

Setup (once per opted-in repo, via chat):

```
Create trigger "nightly-lazy-claude-config" in the claude-config cloud environment:
  cron: 0 1 * * *            (01:00 UTC nightly; stagger per repo)
  create_new_session_on_fire: true
  notifications: push on (email per taste)
  prompt: |
    Nightly scheduled lazy run for claude-config (unattended — no operator present).
    Run /lazy-batch-cloud 10 --park and follow it exactly. Do not extend the budget,
    do not skip research halts, and run --run-end on every terminal path as the skill
    requires. If --run-start is refused because a run marker is live, STOP and report
    the refusal verbatim in your final summary — do not delete or work around the marker.
```

The trigger prompt is a complete standalone instruction (fresh-session mode requires it) and adds
no new orchestration — `/lazy-batch-cloud` already passes `--run-start --unattended`, already
notifies per §1c.6, and already commits `LAZY_QUEUE.md` per cycle.

Morning routine (the "report" is compositional — D5):

1. **Phone, passive:** the routine's completion push ("nightly-lazy-claude-config finished") plus
   any halt pages (sibling feature) for parked/blocking decisions.
2. **GitHub mobile:** open `LAZY_QUEUE.md` — state deltas, "Needs attention" triage, last-commit
   freshness. Tap through to SPEC.md / sentinel bodies as needed.
3. **Claude app / workstation:** open the fired session — answer the parked-decision flush if one
   is pending (D4), read the final batch report, then run a workstation `/lazy-batch` to flush any
   `DEFERRED_NON_CLOUD.md` items through MCP validation → completion (D7).

Failure modes, honestly surfaced:

- **Live evening run still going at 01:00:** the fire's `--run-start` is refused (exit 3, stderr
  names the in-flight run); the session reports the refusal; the completion push still arrives.
  Nothing is clobbered. (D6)
- **Last night's run hard-crashed:** tonight's fire is also refused (marker <24h old). Morning
  fix: confirm dead, run `python3 ~/.claude/scripts/lazy-state.py --run-end --repo-root <repo>`;
  optionally `fire_trigger` to run the job immediately rather than waiting a night. (D6)
- **Queue head needs research:** strict halt (`needs-research`), sentinel written, run ends with
  `--run-end` — the completion push + queue doc say so; the night's remaining budget goes to
  skip-ahead-eligible independent items where the dependency-aware skip-ahead applies.
- **Nothing to do:** `cloud-queue-exhausted` / `all-features-complete` — a clean, quiet stop.

## Technical Design

```
platform trigger (per repo, cron, fresh-session-per-fire, completion push)
      │  fires 01:00
      ▼
fresh cloud session ──► /lazy-batch-cloud 10 --park
      │ Step 0: lazy-state.py --cloud --run-start --unattended --max-cycles 10
      │         └─ refuse_run_start_clobber: live+fresh marker ⇒ exit 3, report, stop
      │ loop: probe (--park flags) → dispatch cycle subagent → commit+push per cycle
      │         └─ LAZY_QUEUE.md regenerated, rides each cycle commit on main
      │ halts: needs-input/BLOCKED parked into parked[]; queue advances
      │ MCP steps: __write_deferred_non_cloud__ per feature (workstation re-opens later)
      │ terminal: cloud-queue-exhausted | queue-exhausted-all-parked | needs-research | …
      │         └─ MANDATORY --run-end + §1c.6 PushNotification + final batch report
      ▼
morning: completion push/email · LAZY_QUEUE.md diff · halt pages (sibling) ·
         flush parked decisions in the fired session · workstation /lazy-batch drains
         DEFERRED_NON_CLOUD.md → VALIDATED.md → __mark_complete__ (receipt-gated)
```

- **Zero state-script changes expected.** The scheduling layer composes: the trigger platform
  (management via D9), the orchestrator skill verbatim, and the marker/arbitration layer as-is.
  The only candidate code change is none-by-default; if the D4 pilot forces option C (unattended
  flush variant), that becomes its own coupled-skills change with a fresh needs-input round.
- **Arbitration invariants (verified):** markers are per-repo keyed
  (`claude_state_dir()` → `~/.claude/state/<repo_key>/lazy-run-marker.json`), so repo A's nightly
  run never arms/blocks repo B (`multi-repo-concurrent-runs`); `refuse_run_start_clobber` refuses
  cross-pipeline always and same-pipeline without a checkpoint (exit 3, zero side effects);
  markers are born owner-bound (`--run-start --session-id` threading); staleness is 24h
  (`_MARKER_STALE_SECONDS`), interacting with nightly cadence as documented in D6.
- **Unattended semantics (verified):** `/lazy-batch-cloud` Step 0 already passes `--unattended`;
  the marker records `attended: false`; the stop-authorization gate
  (`lazy_core.SANCTIONED_STOP_TERMINAL`) permits an unattended checkpoint-stop without
  `--operator-authorized`, and checkpoint-resume counter semantics (fresh budget on
  operator-authorized resume; monotonic carry on automatic reliability resume) are already
  specified in `/lazy-batch` Step 0.7.
- **Budget flags:** `max_cycles` caps `forward_cycles` only (`meta_cycles` uncapped, existing
  operator decision); `--per-feature-cycle-cap` stays un-armed by default; `--allow-research-skip`
  deliberately NOT passed (D3).
- **House invariants honored:** no LLM-inferred state anywhere in the chain (trigger → skill →
  script-owned marker/queue/sentinels); receipt-gated completion untouched (cloud cannot mint
  `VALIDATED.md`/`COMPLETED.md` — D7 keeps that honest); containment hooks
  (`lazy-cycle-containment.sh` etc.) arm per-repo exactly as in interactive runs since the
  marker/env mechanics are identical; `LAZY_QUEUE.md` generation stays byte-stable pure-read.

## Implementation Phases

- **Phase 1 — One-shot pilot (claude-config).** Create a `run_once_at` trigger (fresh-session,
  push notification on) with the D3/D4 arg shape; let it fire; capture: `--run-start --unattended`
  marker contents, per-cycle `LAZY_QUEUE.md` commits arriving on `main`, terminal + `--run-end`,
  the completion push, and — key empirical check — whether a parked-decision flush question
  survives to a morning answer (D4 A-vs-C evidence). Proves done: the fired session's transcript +
  git log show the full contract held.
- **Phase 2 — Collision & recovery drills.** (a) Fire via `fire_trigger` while an interactive run
  holds the marker → verify exit-3 refusal is reported, nothing clobbered; (b) simulate a dead
  marker (hand-plant an aged/fresh marker in the state dir) → verify the refusal + documented
  morning recovery (`--run-end`) works; record both as evidence. Proves done: both drills
  captured with transcripts.
- **Phase 3 — Nightly cron rollout.** Convert to `cron_expression` per opted-in repo (staggered
  slots per D2), notifications per D5; run one real week; verify the morning-report loop end to
  end including a workstation `DEFERRED_NON_CLOUD.md` flush. Proves done: a week of fires with
  the morning routine exercised at least once per surface.
- **Phase 4 — Documentation.** Trigger recipes + prompt template + failure/recovery playbook
  recorded (this SPEC's UX section is the draft; final home: this feature dir +
  `workspace/CLAUDE.md` pointer). Proves done: a later agent can recreate a repo's nightly
  trigger from docs alone.

Estimate: ~3 sessions (Phases 1–2 one, 3 spans a calendar week but ~1 session of attention, 4
folds in).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Scheduled fire runs the loop | `run_once_at` pilot fire | Fresh session invokes `/lazy-batch-cloud 10 --park`; cycles dispatch | fired session transcript |
| Unattended marker honest | Pilot fire, mid-run | Marker has `attended: false`, `pipeline: feature`, `max_cycles: 10` | `~/.claude/state/<repo_key>/lazy-run-marker.json` |
| Queue doc publishes | ≥1 forward cycle | Per-cycle commits on `main` include regenerated `LAZY_QUEUE.md` | git log / GitHub mobile |
| Live run never clobbered | `fire_trigger` during an interactive run | `--run-start` exit 3; stderr names in-flight run; interactive run unaffected | drill transcript + marker |
| Crashed-run interaction as documented | Planted <24h marker, then fire | Refusal; morning `--run-end` recovery unblocks; next fire proceeds | drill transcript |
| Parked halts don't stall the night | Queue with a needs-input item mid-queue | Item parked, queue advanced, flush at run end | probe `parked[]` + transcript |
| Run always ends `--run-end` | Every pilot/weekly fire | Marker absent after terminal; no orphaned markers across the week | state dir inspection |
| Morning notification on every fire | Nightly week incl. a refused fire | Completion push per fire; refused fire's summary states the refusal | phone + session summary |
| Deferred handoff completes | Morning workstation `/lazy-batch` after a cloud night | Deferred items re-open → MCP → `VALIDATED.md` → receipt-gated complete | sentinel/receipt files |

## Open Questions

**None remain open — all five product-behavior decisions were operator-approved at their
recommended options on 2026-07-04** (D1→A, D2→A, D3→A, D4→A, D5→A; D6–D9 auto-accepted and
operator-locked the same day). See each decision's `Resolution` line under Design Decisions.

- Deferred empirical checks (implementation, not decisions — owned by the operator-run pilot
  phases): flush-question survivability in a trigger-fired session overnight (Phase 1, feeds
  D4's A-vs-C fallback); push-to-`main` rights from a trigger-fired fresh session (Phase 1); the
  exact stderr surfacing of an exit-3 refusal in a fresh session's final summary (Phase 2);
  whether cron minimum granularity/timezone needs a repo-local note (Phase 3).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the pre-existing `--unattended`/`attended` marker
  contract; `refuse_run_start_clobber` + 24h staleness semantics; nightly-CI/scheduled-workflow
  conventions.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — the invoked orchestrator (budget
  args, terminal set, §1c.6 notifications, mandatory `--run-end`).
- `docs/features/mobile-queue-control/SPEC.md` — `LAZY_QUEUE.md` per-cycle commit + push-to-`main`
  scope (claude-config + AlgoBooth), the basis of D2's qualifying-repo set.
- `docs/features/operator-halt-notifications/SPEC.md` — soft dep; the halt-paging half of the
  morning report.
- `user/scripts/CLAUDE.md` — marker/state-dir/arbitration authority this spec verifies against.
