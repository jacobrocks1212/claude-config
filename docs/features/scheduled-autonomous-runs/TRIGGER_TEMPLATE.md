# TRIGGER_TEMPLATE — Canonical Nightly Trigger Prompt (Scheduled Autonomous Runs)

> The canonical `prompt` body for a `nightly-lazy-<repo>` platform trigger (D1/D2/D3, approved
> 2026-07-04). Written for **fresh-session mode** (`create_new_session_on_fire: true`): the fired
> session has ZERO prior context, so this prompt is a complete standalone instruction. Recipes
> that consume this template: [`RECIPES.md`](./RECIPES.md). Failure/recovery contract:
> [`PLAYBOOK.md`](./PLAYBOOK.md).

## Preconditions (per opted-in repo — verify ONCE before creating the trigger)

1. **Cloud environment exists and is the repo's normal one (D8).** The trigger fires into the
   same environment interactive cloud sessions use — no dedicated scheduled-run environment. The
   environment already carries repo access; nothing new is provisioned.
2. **Push-to-`main` rights from a fresh session.** The per-cycle commit + `LAZY_QUEUE.md`
   publish depend on `git push` succeeding, and the orchestrator's Step 0 preconditions do their
   own branch/tree checks and halt honestly if the session doesn't land on `main`. Empirically
   confirmed at the pilot (SPEC Phase 1 deferred check).
3. **The invoked skill is reachable in the fired session.** `/lazy-batch-cloud` is a
   **repo-scoped skill** (`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — the cloud
   half of the `/lazy-batch` coupled pair). It is on the skill path when the fired session's repo
   carries it in `.claude/skills/` (AlgoBooth). For **claude-config**, whose cloud sessions see
   user-level skills only via the in-tree `user/skills/` (no `~/.claude` symlinks in cloud), the
   honest equivalent is **`/lazy-batch {budget} --park`**: claude-config has no MCP surface
   (no `src-tauri/`, no `package.json`), so the workstation skill's structural MCP-skip
   (`__grant_skip_no_mcp_surface__`) applies and nothing needs the cloud deferral machinery.
   Park semantics are environment-agnostic (identical across the coupled pair). The
   parameterization table below carries this per-repo.
4. **Notify-channel env var** (`operator-halt-notifications` D7) — add to the environment when
   that sibling feature lands; until then halts surface via `LAZY_QUEUE.md` + the session
   transcript (soft dependency; scheduled runs function without it).
5. **No wrapper scripts, no new registry (D9/D2).** The trigger store is the registry
   (`list_triggers`); manage via chat ops per `RECIPES.md`.

## Canonical prompt body

Substitute `{repo}`, `{invocation}`, and `{budget}` from the parameterization table, then paste
verbatim as the trigger's `prompt`:

```
Nightly scheduled lazy run for {repo} (unattended — no operator present; this is a
fresh session created by the "nightly-lazy-{repo}" scheduled trigger).

Context you must assume, since this session starts from nothing:
- You are in the {repo} cloud environment; the repo is cloned at the session root.
  Confirm you are on `main` with a clean tree before starting (the orchestrator's
  own Step 0 preflight checks this and halts honestly if not).
- The lazy pipeline state is entirely on disk (docs/features/queue.json,
  docs/bugs/queue.json, sentinels, ROADMAP.md). Do not reconstruct state from
  memory — the state script owns routing.

Run:

  {invocation}

and follow that skill exactly. Non-negotiable conduct rules for this run:
- Do NOT extend the budget: {budget} forward cycles is the cap; meta cycles are
  uncapped by the skill's own design. Never re-invoke with a larger N.
- Do NOT pass --allow-research-skip and do NOT skip research halts: a
  needs-research head halts honestly (research is a human step). The skill's
  dependency-aware skip-ahead may still spend remaining budget on independent
  items — that is its default behavior, not yours to force.
- Run `python3 ~/.claude/scripts/lazy-state.py --run-end` on EVERY terminal path,
  as the skill requires (its §1c.6 notification policy makes this mandatory
  before the terminal PushNotification).
- If --run-start is REFUSED because a run marker is live (exit 3, stderr naming
  the in-flight run): STOP IMMEDIATELY and report the refusal stderr VERBATIM in
  your final summary. Do NOT delete the marker, do NOT run --run-end for a run
  you do not own, do NOT retry, do NOT work around it in any way. The refusal is
  the arbitration working as designed.

What to do at each terminal class (all of these are NORMAL ends — report, never
improvise past them):
- cloud-queue-exhausted: the normal cloud stop — every remaining feature awaits
  workstation MCP validation. Report how many features are deferred
  (DEFERRED_NON_CLOUD.md) for the morning workstation flush.
- queue-exhausted-all-parked (--park): every remaining item is parked
  (needs-input/blocked). The skill fires its parked-decision flush
  (AskUserQuestion) at run end — leave that question pending for the operator's
  morning answer; do not answer it yourself.
- needs-research / queue-blocked-on-research: strict halt; sentinel written;
  report which item needs research.
- max-cycles: budget spent; report the batch summary and stop (a fresh session
  continues another night).
- all-features-complete: clean success; report it.
- Any refusal or script error: report verbatim, --run-end only if YOU own the run
  marker (i.e. your --run-start succeeded), then stop.

End with the skill's final batch report. Your session summary is part of the
operator's morning report — make the terminal reason and any pending decisions
unmissable in it.
```

## Per-repo parameterization (D2 — one trigger per opted-in repo)

| Token | claude-config | AlgoBooth |
|---|---|---|
| Trigger `name` | `nightly-lazy-claude-config` | `nightly-lazy-algobooth` |
| `{repo}` | `claude-config` | `AlgoBooth` |
| `{invocation}` | `/lazy-batch 10 --park` *(see precondition 3 — `/lazy-batch-cloud` is AlgoBooth-repo-scoped; claude-config has no MCP surface, so the workstation skill's structural skip makes this the honest cloud invocation)* | `/lazy-batch-cloud 10 --park` *(canonical D3 shape)* |
| `{budget}` | `10` (D3 default — tune per repo by editing the trigger prompt later) | `10` |
| Cron slot (staggered, UTC) | `0 1 * * *` (01:00) | `0 3 * * *` (03:00) |
| `create_new_session_on_fire` | `true` | `true` |
| `notifications` | `{push: true}` (email per taste — D5) | `{push: true}` |
| Qualifies because | works on + pushes to `main`; cloud env exists (mobile-queue-control Decision 6) | same |

**Flags deliberately NOT passed (D3):** `--allow-research-skip` (research is a human step; a
skipped halt silently reorders priorities overnight) and `--per-feature-cycle-cap` (documented
default-off; the whole-run cap is the sole nightly budget).

## Why this shape (decision trace)

- Fresh session per fire (D1-A): matches the orchestrator's own "restart from a fresh session"
  advice at max-cycles; per-routine completion notifications exist ONLY in this mode; a wedged
  session can never poison the next night.
- `--park` (D4-A): one ambiguous decision no longer costs the whole night — needs-input/blocked
  items park into `parked[]`, the queue advances, and the run-end flush is the morning's single
  decision inbox. The pilot empirically checks whether the held-open flush survives to morning;
  the unattended-flush variant (D4 option C) is the documented fallback ONLY if it does not.
- The refusal rule (D6): `refuse_run_start_clobber` (exit 3, zero side effects) is the entire
  collision-safety story — the prompt's job is to make the fired session RELAY it, never fight it.
