# Implementation Phases — Scheduled Autonomous Runs (Overnight Builder)

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
<!-- Phases 1-4 (documentation) implemented + validated 2026-07-04 (pytest 1202 passed / 2
     sanctioned skips; --test smokes green ×3; parity audit exit 0; lint-skills exit 0; every
     doc citation contract-verified at file+line in RESEARCH_SUMMARY.md). Phase 5 (live pilot,
     drills, weeklong cron rollout) is OPERATOR-DEFERRED by design — requires live platform
     triggers + phone + wall-clock; RECIPES.md is its copy-paste input. NOT Complete on the
     SPEC — the __mark_complete__ integrity gate owns the SPEC Complete flip + COMPLETED.md
     receipt. -->

**MCP runtime:** not-required — this feature is docs/configuration glue ONLY (trigger prompt
template + platform-trigger recipes + failure/recovery playbook + a `workspace/CLAUDE.md`
pointer). Zero state-script changes, zero skill changes, no Tauri app, no MCP-reachable surface.
Validation is doc-completeness cross-checks against the real contracts (every flag/behavior cited
verified at file+line in `RESEARCH_SUMMARY.md`) plus the full harness gate suite (confirming no
accidental breakage). This is the `standalone — no app integration` untestable class →
`SKIP_MCP_TEST.md` at the MCP gate.

> **Phase mapping vs the SPEC.** The SPEC's own Phases 1–3 (one-shot pilot, collision & recovery
> drills, nightly cron rollout week) require LIVE platform triggers, the operator's phone, and
> real overnight wall-clock — they are OPERATOR-deferred here (Phase 5 below, explicitly marked).
> The SPEC's Phase 4 (documentation) is what this lane ships, expanded into Phases 1–4 below so a
> later agent can recreate a repo's nightly trigger from docs alone BEFORE the pilot fires.

## Cross-feature Integration Notes

`**Depends on:** operator-halt-notifications (soft)`. All substantive dependencies are
**implemented contracts, not sibling specs** (verified in `RESEARCH_SUMMARY.md`):

- **`/lazy-batch-cloud`** (`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`) — invoked
  verbatim; this feature adds NO orchestration. Its Step 0 already passes
  `--cloud --run-start --unattended --max-cycles {max_cycles}` (SKILL.md:227); `--park`,
  the cloud terminal set, §1c.6 notifications, and the mandatory `--run-end` are all pre-existing.
- **Arbitration** — `lazy_core.refuse_run_start_clobber` (lazy_core.py:10694; exit 3, zero side
  effects) + 24h `_MARKER_STALE_SECONDS` (lazy_core.py:6459) + per-repo keyed state dirs
  (`multi-repo-concurrent-runs`). Verified, not rebuilt (D6 locked).
- **`LAZY_QUEUE.md`** per-cycle regen (`mobile-queue-control`, Complete) — the morning read;
  wired in `user/skills/lazy-batch/SKILL.md:489-497` (see RESEARCH_SUMMARY finding 2 for the
  cloud-skill wiring caveat).
- **`operator-halt-notifications`** (soft) — halt paging half of the morning report; until it
  lands, halts surface via `LAZY_QUEUE.md` + the fired session's transcript (documented as such
  in `PLAYBOOK.md`).

---

### Phase 1: TRIGGER_TEMPLATE.md — the canonical self-contained trigger prompt

**Phase kind:** design

**Scope:** Author the canonical nightly-trigger prompt as a fresh-session-safe standalone
instruction (D1: `create_new_session_on_fire` means the prompt carries ALL context), plus the
per-repo parameterization table and the preconditions a repo must satisfy to opt in.

**Deliverables:**
- [x] `TRIGGER_TEMPLATE.md`: the canonical prompt body — repo identity, clone/session
  expectations, the exact invocation `/lazy-batch-cloud 10 --park` (D3), explicit conduct rules
  (no budget extension, no research-halt skipping, `--run-end` on every terminal, refusal =
  report verbatim + STOP, never delete/work around a marker), and what to do on each terminal
  class (`cloud-queue-exhausted`, `queue-exhausted-all-parked`, `needs-research` /
  `queue-blocked-on-research`, `max-cycles`, `all-features-complete`, refusal).
- [x] Per-repo parameterization: the `{repo}` / `{budget}` / `{cron-slot}` substitution table for
  the two qualifying repos (claude-config 01:00 UTC, AlgoBooth 03:00 UTC — D2), each row carrying
  its skill-availability note (RESEARCH_SUMMARY finding 1).
- [x] Preconditions section: cloud environment exists (D8 — reuse, no new environment),
  push-to-`main` rights, the invoked skill reachable in the fired session, notify-channel env var
  when `operator-halt-notifications` lands.

**Minimum Verifiable Behavior:** A later agent given ONLY `TRIGGER_TEMPLATE.md` + `RECIPES.md`
can compose a complete, correct `create_trigger` call for a named repo with zero other context.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Every flag/terminal the template cites exists in the invoked skill/scripts at the cited
  location (cross-checked against `RESEARCH_SUMMARY.md` anchor table). *(Evidence:
  `RESEARCH_SUMMARY.md` — verified-anchors table; `SKIP_MCP_TEST.md`.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (first phase).

**Files likely modified:** `docs/features/scheduled-autonomous-runs/TRIGGER_TEMPLATE.md` (new).

**Testing Strategy:** Docs-only. Cross-check every cited flag (`--park`, budget default,
`--run-start --unattended`, terminal names) against the skill/scripts; full gate suite at the end
of the lane confirms no accidental harness breakage.

**Integration Notes for Next Phase:** Phase 2's recipes embed this template as the
`create_trigger` `prompt` parameter — keep the template's substitution tokens (`{repo}`,
`{budget}`) stable.

---

### Phase 2: RECIPES.md — copy-paste trigger management recipes

**Phase kind:** design

**Scope:** Ready-to-run create/update/list/delete/fire-now recipes against the platform trigger
API surface (D9: managed via chat ops, NO wrapper script), parameterized per repo.

**Deliverables:**
- [x] Create recipe: `create_trigger` with `cron_expression` (staggered slots `0 1 * * *` /
  `0 3 * * *` — D2), `create_new_session_on_fire: true` (D1), `notifications: {push: true}`
  (D5; email per taste), the Phase-1 template as `prompt`, and the environment note (fires into
  the repo's existing cloud environment — D8; `environment_id` required only outside a session,
  discovered via `list_environments`).
- [x] Pilot recipe: one-shot `run_once_at` variant (SPEC Phase 1 pilot) + `fire_trigger` for
  run-tonight's-job-now (optionally with appended run-specific `text`).
- [x] Registry/inspection recipes: `list_triggers` as the registry view (D2 — the trigger list IS
  the registry), `update_trigger` enable/disable/cron-move, `delete_trigger` teardown.
- [x] Constraint notes carried from the live schemas: cron minimum interval hourly;
  `run_once_at` RFC3339 + self-disables after firing (`ended_reason=run_once_fired`);
  `notifications` valid ONLY for fresh-session routines; cron is 5-field UTC.

**Minimum Verifiable Behavior:** Each recipe names a real platform op with real parameter names
(matching the live tool schemas verbatim) and is copy-paste executable by the operator in chat.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Parameter names/constraints in every recipe match the live platform tool schemas
  (`create_trigger`/`update_trigger`/`delete_trigger`/`fire_trigger`/`list_triggers`/
  `list_environments`). *(Evidence: `RESEARCH_SUMMARY.md` platform-contract row.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (the template the create recipe embeds).

**Files likely modified:** `docs/features/scheduled-autonomous-runs/RECIPES.md` (new).

**Testing Strategy:** Docs-only; schema cross-check as above. NO live trigger is created by this
lane — creation is an operator action (Phase 5).

**Integration Notes for Next Phase:** Phase 3's playbook references the recipes by anchor
(recovery paths reuse `fire_trigger` / `update_trigger`); keep recipe headings stable.

---

### Phase 3: PLAYBOOK.md — failure/recovery playbook + morning triage

**Phase kind:** design

**Scope:** The operating contract around the scheduler: what each bad (and good) night looks
like, how to recover, and the morning triage flow (D5 compositional report + D7 workstation
flush).

**Deliverables:**
- [x] Live-run refusal collision: scheduled fire while an interactive run holds the marker →
  exit-3 refusal semantics (stderr names the in-flight run; zero side effects), what the
  completion push reads like, and the non-action (nothing to fix — arbitration worked; D6).
- [x] Crashed-marker recovery: hard-crashed overnight run leaves a <24h marker → next night also
  refuses; morning recovery via `lazy-state.py --run-end` (confirm-dead first; including the
  unacked-hardening-debt refusal branch + `--ack-unhardened` override — RESEARCH_SUMMARY finding
  3), then optional `fire_trigger` to re-run immediately.
- [x] Needs-research halt overnight: strict halt (`needs-research` / `queue-blocked-on-research`),
  sentinel + `--run-end` + push; dependency-aware skip-ahead spends the rest of the budget on
  independent items; morning action = supply research (direct `RESEARCH.md` drop per repo
  convention).
- [x] Nothing-to-do night: `cloud-queue-exhausted` / `all-features-complete` /
  `queue-exhausted-all-parked` as clean quiet stops — what distinguishes them.
- [x] Morning triage flow: push/halt pages → `LAZY_QUEUE.md` diff on GitHub mobile (with the
  cloud-wiring caveat + git-log fallback) → open the fired session (answer the parked-decision
  flush — D4) → workstation `/lazy-batch` flushes `DEFERRED_NON_CLOUD.md` items through MCP
  validation → receipt-gated completion (D7).

**Minimum Verifiable Behavior:** Every failure mode in the SPEC's "Failure modes, honestly
surfaced" list has a playbook entry with a concrete recovery command or an explicit "no action
needed" verdict.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Every recovery command cited (`--run-end`, `--ack-unhardened`, `fire_trigger`,
  `--marker-present`) exists with the documented semantics. *(Evidence: `RESEARCH_SUMMARY.md`
  anchor table rows for run-end/marker ops.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2 (references both).

**Files likely modified:** `docs/features/scheduled-autonomous-runs/PLAYBOOK.md` (new).

**Testing Strategy:** Docs-only; contract cross-check per RESEARCH_SUMMARY. The two live drills
(refusal collision, planted-marker recovery) are operator-deferred (Phase 5) — the playbook
documents their expected transcripts so the drills can be graded against it.

**Integration Notes for Next Phase:** Phase 4's `workspace/CLAUDE.md` pointer names this file as
the entry point for "what happened overnight".

---

### Phase 4: workspace/CLAUDE.md pointer + validation pass

**Phase kind:** chore

**Scope:** One tightly-scoped pointer paragraph in `workspace/CLAUDE.md` (the SPEC's named final
home for discoverability) + the doc-completeness validation pass + full gate suite.

**Deliverables:**
- [x] `workspace/CLAUDE.md`: a "Scheduled Autonomous Runs (nightly lazy)" paragraph — what fires,
  where the template/recipes/playbook live, and the one-line morning-routine summary. Additive
  only (no reflow of surrounding text).
- [x] Doc cross-check pass: every flag/terminal/op cited across the three new docs traced to its
  contract (the RESEARCH_SUMMARY anchor table is the ledger).
- [x] Full harness gate suite run once, green (docs-only feature — confirms no accidental
  breakage).

**Minimum Verifiable Behavior:** `workspace/CLAUDE.md` points a fresh session at the feature dir;
gate suite green at the lane's final commit.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Gate suite green (pytest suites + `--test` smokes + parity audit + skill lint) at the final
  commit. *(Evidence: `SKIP_MCP_TEST.md` alternative_validation counts.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `workspace/CLAUDE.md`.

**Testing Strategy:** Full gate suite from `user/scripts` (pytest suites, `--test` smokes,
`lazy_parity_audit.py`, `lint-skills.py`).

**Integration Notes for Next Phase:** Phase 5 is operator-owned live rollout; docs are its
complete input.

---

### Phase 5: Live pilot, drills & nightly rollout — OPERATOR-DEFERRED

**Phase kind:** integration

**Scope:** The SPEC's Phases 1–3: one-shot pilot fire, collision & recovery drills, and the
weeklong nightly cron rollout.

> **DEFERRED — operator action required.** Reason: requires LIVE platform triggers firing into
> the repos' real cloud environments, the operator's phone (completion push / halt pages), real
> overnight wall-clock, and — for the drills — a live interactive run to collide with. None of
> these exist in this docs lane, and creating live triggers is explicitly an operator action (D9;
> lane constraint: "do NOT create any live triggers"). The recipes in `RECIPES.md` are the
> copy-paste input; the playbook defines the expected evidence for each drill.

**Deliverables:**
- **OPERATOR-DEFERRED (live platform + phone + overnight wall-clock; not a completion blocker):** One-shot pilot fire (claude-config): `run_once_at` trigger per `RECIPES.md` §Pilot; capture
  marker contents (`attended: false`, `pipeline: feature`, `max_cycles: 10`), per-cycle commits,
  terminal + `--run-end`, completion push, and flush-question survivability (feeds D4 A-vs-C).
  *(deferred — operator: requires live platform trigger + phone)*
- **OPERATOR-DEFERRED (live platform + phone + overnight wall-clock; not a completion blocker):** Collision & recovery drills: `fire_trigger` during a live interactive run → exit-3 refusal
  reported, nothing clobbered; planted <24h marker → refusal + morning `--run-end` recovery.
  *(deferred — operator: requires live trigger + a live interactive run to collide with)*
- **OPERATOR-DEFERRED (live platform + phone + overnight wall-clock; not a completion blocker):** Nightly cron rollout: convert to `cron_expression` per opted-in repo (staggered slots), one
  real week, morning routine exercised per surface incl. a workstation `DEFERRED_NON_CLOUD.md`
  flush. *(deferred — operator: requires a calendar week of live fires)*

**Minimum Verifiable Behavior:** (deferred) A week of fires with the morning routine exercised at
least once per surface; both drills captured with transcripts.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- **OPERATOR-DEFERRED (live platform + phone + overnight wall-clock; not a completion blocker):** SPEC Validation Criteria table rows (all nine) evidenced from live fires/drills.
  *(deferred — operator: live platform triggers + phone + wall-clock week)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–4 (the docs ARE the rollout input).

**Files likely modified:** none in-repo (live trigger store + state dirs + transcripts; any
harness friction observed feeds back as bug reports per the repo mission).

**Testing Strategy:** Operator-run per `PLAYBOOK.md` expected-evidence sections; graded against
the SPEC Validation Criteria table.
