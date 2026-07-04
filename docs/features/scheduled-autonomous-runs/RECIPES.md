# RECIPES — Platform Trigger Management (Scheduled Autonomous Runs)

> Copy-paste-ready recipes for creating/inspecting/pausing/firing the `nightly-lazy-<repo>`
> triggers via the platform's trigger ops in chat (D9: NO wrapper script — the trigger store is
> the source of truth, `list_triggers` is the registry). Prompt body: substitute from
> [`TRIGGER_TEMPLATE.md`](./TRIGGER_TEMPLATE.md). Failure/recovery: [`PLAYBOOK.md`](./PLAYBOOK.md).
>
> **These are operator actions.** This feature ships the recipes only; no live trigger is created
> by the pipeline. Run each recipe by asking a Claude session (in the target repo's cloud
> environment, or any session with the trigger tools) to perform the named op with the given
> parameters.

## Platform constraints (from the live tool schemas — verify against RESEARCH_SUMMARY.md)

- `cron_expression`: standard **5-field** cron, **UTC**, minimum interval **hourly**.
- `run_once_at`: RFC3339 timestamp, must be future; mutually exclusive with `cron_expression`;
  after firing, the trigger disables itself with `ended_reason=run_once_fired`.
- `create_new_session_on_fire: true` (D1): each fire spawns a fresh session; mutually exclusive
  with `persistent_session_id`. The prompt must be a complete standalone instruction.
- `notifications` (`{push, email}`): **only valid for fresh-session routines**
  (`create_new_session_on_fire: true`) — the server rejects it for self-bind/persistent-session
  routines. Specify every channel you want on (e.g. `{push: true}` = push only).
- `environment_id`: defaults to the calling session's environment when run from a session in the
  target repo (the D8 path — reuse the repo's existing cloud environment). Required only when
  creating from outside a session; discover via `list_environments`.
- Scheduler granularity is one minute; sub-minute precision does not exist.

---

## 1. Create — nightly cron trigger (one per opted-in repo; D2)

**claude-config** (01:00 UTC slot):

```
create_trigger:
  name: "nightly-lazy-claude-config"
  cron_expression: "0 1 * * *"
  create_new_session_on_fire: true
  notifications: { push: true }        # email: true additionally, per taste (D5)
  prompt: |
    <TRIGGER_TEMPLATE.md canonical prompt body, with
     {repo}=claude-config, {invocation}=/lazy-batch 10 --park, {budget}=10>
```

**AlgoBooth** (03:00 UTC slot — staggered so pushes/notifications don't interleave):

```
create_trigger:
  name: "nightly-lazy-algobooth"
  cron_expression: "0 3 * * *"
  create_new_session_on_fire: true
  notifications: { push: true }
  prompt: |
    <TRIGGER_TEMPLATE.md canonical prompt body, with
     {repo}=AlgoBooth, {invocation}=/lazy-batch-cloud 10 --park, {budget}=10>
```

Run each from a session in that repo's cloud environment so `environment_id` defaults correctly
(D8). From outside a session, first `list_environments` and pass the repo's `environment_id`
explicitly. The response's `trigger.id` (`trig_...`) is worth noting but never required later —
`list_triggers` re-discovers it.

## 2. Pilot — one-shot fire (SPEC Phase 1)

A single test fire tonight, without committing to a cadence:

```
create_trigger:
  name: "pilot-lazy-claude-config"
  run_once_at: "2026-07-05T01:00:00Z"    # any future RFC3339 instant
  create_new_session_on_fire: true
  notifications: { push: true }
  prompt: <same TRIGGER_TEMPLATE.md body as the nightly recipe>
```

After it fires it self-disables (`ended_reason=run_once_fired`) — no cleanup needed, though
`delete_trigger` keeps the registry tidy. Pilot evidence to capture is listed in PHASES.md
Phase 5 / SPEC Phase 1 (marker `attended: false`, per-cycle commits, terminal + `--run-end`,
completion push, flush-question survivability).

## 3. Fire now — run tonight's job immediately

On-demand fire of an existing trigger (e.g. after a morning crashed-marker recovery, rather than
waiting a night — see PLAYBOOK.md §2):

```
fire_trigger:
  trigger_id: "<trig_... from list_triggers>"
```

With run-specific context appended as an extra user turn after the trigger's prompt:

```
fire_trigger:
  trigger_id: "<trig_...>"
  text: "Context for this run only: last night's run crashed and its marker was
         cleared this morning via --run-end; expect a clean --run-start."
```

## 4. Registry view — what's scheduled where

The trigger list IS the registry (D2 — no config file to maintain):

```
list_triggers
```

Each entry carries `id`, `name`, `cron_expression`/`run_once_at`, `enabled`, `ended_reason`,
`next_run_at` — i.e. the full nightly roster and its next fire times. An empty `ended_reason` on
a disabled trigger means operator-paused; `run_once_fired` means a spent one-shot.

## 5. Pause / resume / re-slot a repo

Disable one repo's nights (touches nothing else — D2's per-repo isolation):

```
update_trigger:
  trigger_id: "<trig_...>"
  enabled: false
```

Re-enable: same with `enabled: true`. Move its slot (e.g. de-conflict with a new repo):

```
update_trigger:
  trigger_id: "<trig_...>"
  cron_expression: "0 2 * * *"
```

Note: setting `cron_expression` clears any `run_once_at` (and vice versa).

## 6. Teardown

```
delete_trigger:
  trigger_id: "<trig_...>"
```

Permanent; recreate from recipe 1 if needed. Prefer recipe 5's `enabled: false` for anything
temporary.

## 7. Budget/prompt tuning (D3)

The budget is a trigger-prompt parameter. To tune a repo's nightly budget once morning-review
data exists: recreate the trigger with the edited prompt (recipes 6 then 1 — the platform ops
update name/cadence/enabled state, while the prompt is fixed at creation), keeping the same
`name` so the registry stays legible.
