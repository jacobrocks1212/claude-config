---
kind: research-summary
feature_id: scheduled-autonomous-runs
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — Scheduled Autonomous Runs (Overnight Builder)

Codebase survey verifying every surface the SPEC cites, performed before authoring the
documentation deliverables (this feature is docs/configuration glue ONLY — zero state-script or
skill code changes). Line numbers are as of this lane's base commit (`a10e3f0`).

## Verified contract anchors (SPEC citation → actual location)

| SPEC claim | Verified location | Status |
|---|---|---|
| `--unattended` on `--run-start` "for scheduled/cron invocations" (~line 9164) | `user/scripts/lazy-state.py:9159-9177` (comment block + `parser.add_argument("--unattended", ...)` at 9174); threaded into the marker at 9485-9505 (`attended=not args.unattended`) | ✅ verified |
| `write_run_marker(attended=...)` (~line 9297) | `user/scripts/lazy_core.py:9289` (`def write_run_marker`), `attended: bool = True` param at 9297, written into the marker dict at 9386; `"max_cycles"` at 9356; `attended` in the marker field list at 6510 | ✅ verified |
| `refuse_run_start_clobber` semantics (~line 10694) | `user/scripts/lazy_core.py:10694` (exact). Cross-pipeline live+fresh marker → `sys.exit(3)` at 10819; same-pipeline without `lazy-run-checkpoint.json` → `sys.exit(3)` at 10808; checkpoint presence read NON-destructively (existence only); stderr names the in-flight run (`pipeline`, `session_id`, `started_at`, `forward_cycles`) and ends "refused with ZERO side effects" | ✅ verified |
| 24h staleness (`_MARKER_STALE_SECONDS`) | `user/scripts/lazy_core.py:6459` (`= 24 * 3600`); honored by the clobber refusal at 10774 (a >24h marker is presumed-dead and freely overwritten — no refusal) and by `read_run_marker` path A at 9476 | ✅ verified |
| Per-repo keyed markers (repo A never blocks repo B) | `user/scripts/lazy_core.py:9209` (`def claude_state_dir`) + `repo_key` at 6597 → `~/.claude/state/<repo_key>/lazy-run-marker.json` (`multi-repo-concurrent-runs`) | ✅ verified |
| `/lazy-batch-cloud` Step 0 already passes `--cloud --run-start --unattended --max-cycles {max_cycles}` | `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md:227` (verbatim command), attendedness note at :231 | ✅ verified |
| Default budget 10 | `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md:80` ("positive integer → `max_cycles` (default `10`)") | ✅ verified |
| `--allow-research-skip` default off; `--per-feature-cycle-cap` off-by-default | SKILL.md:81 (`allow_research_skip = true` only when passed, default `false`); :84 ("**OFF by default** — the guard never arms without this flag") | ✅ verified |
| `--park` → `--park-needs-input --park-blocked` probe flags, `parked[]`, `queue-exhausted-all-parked` terminal, Step 1g-flush | SKILL.md:83 (flag), :337 (both probe flags + `parked[]` + terminal), :360 (terminal handling: flush FIRST, then `--run-end`, PushNotification, STOP), :653-691 (1g-flush triggers (a)/(b)/(c) + shared `parked-flush.md` component). Script side: `user/scripts/lazy-state.py:230` (park-mode flags), :2532 (`terminal_reason="queue-exhausted-all-parked"`) | ✅ verified |
| `cloud-queue-exhausted` is the NORMAL cloud stop | SKILL.md:3 (description), :17, :352 (terminal handling) | ✅ verified |
| Mandatory `--run-end` on EVERY terminal path (§1c.6) | SKILL.md:389 (§1c.6 point 2: "**MANDATORY: run … `--run-end` on EVERY terminal/halt path, BEFORE firing the PushNotification**"; missed deletion self-heals via 24h staleness) | ✅ verified |
| `__write_deferred_non_cloud__` / `DEFERRED_NON_CLOUD.md` per feature | SKILL.md:16, :406 (`--apply-pseudo __write_deferred_non_cloud__` — script is single author) | ✅ verified |
| Unattended checkpoint-stop permitted without `--operator-authorized` | `user/scripts/lazy-state.py:9560-9636` (checkpoint gate reads marker `attended`; attended + unauthorized → refuse, marker kept; unattended falls through). `SANCTIONED_STOP_TERMINAL` at `lazy_core.py:9268` | ✅ verified |
| `LAZY_QUEUE.md` per-cycle regen + push to `main` | `user/skills/lazy-batch/SKILL.md:489-497` (regen block: `python user/scripts/lazy-queue-doc.py --repo-root <repo_root>` before the per-cycle `git add -A`); generator `user/scripts/lazy-queue-doc.py` (byte-stable, pure read) | ⚠️ verified with caveat (below) |
| Platform trigger contract (cron min hourly, `run_once_at`, `create_new_session_on_fire`, notifications push/email fresh-session-only, `fire_trigger` with appended text, `list_triggers`/`update_trigger`/`delete_trigger`) | Live platform tool schemas (`create_trigger`, `update_trigger`, `delete_trigger`, `fire_trigger`, `list_triggers`, `list_environments`, `send_later`) — parameter names and constraints match the SPEC's stated contract exactly, including "notifications … only apply to fresh-session-per-fire routines (`create_new_session_on_fire=true`); the server rejects this parameter for self-bind or persistent_session_id routines" | ✅ verified |

## Findings — SPEC assumptions that need honest caveats

1. **`/lazy-batch-cloud` is a repo-scoped skill (AlgoBooth), not a user-level skill.** It lives at
   `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`; `manifest.psd1:25-29` deliberately
   carries NO live symlink entry for algobooth ("Do NOT re-add an entry while the live repo does
   not exist"). A trigger-fired fresh session in the **claude-config** cloud environment therefore
   does not naturally have `/lazy-batch-cloud` on its skill path — user-level skills carry
   `/lazy-batch` only. This is a **precondition**, not a blocker: `TRIGGER_TEMPLATE.md` documents
   the skill-availability precondition per repo, and notes the claude-config-specific reality that
   `/lazy-batch <N> --park` is the honest equivalent there (claude-config has no MCP surface — the
   workstation Step 9 structural skip `__grant_skip_no_mcp_surface__` applies, so nothing needs the
   cloud deferral machinery). The approved D3 invocation (`/lazy-batch-cloud 10 --park`) stands as
   the canonical template; the per-repo parameterization table carries the availability column.
2. **Per-cycle `LAZY_QUEUE.md` regen is wired in `/lazy-batch` only.** The regen block exists
   solely in `user/skills/lazy-batch/SKILL.md:489-497`; `repos/algobooth/.claude/skills/
   lazy-batch-cloud/SKILL.md` contains zero `LAZY_QUEUE`/`lazy-queue-doc` references (grep-clean).
   This matches `mobile-queue-control`'s own scope note ("For AlgoBooth, the equivalent invocation
   lands in that repo's `/lazy-batch`(-cloud) cycle commit … cross-repo wiring is documented for
   the operator, not authored from this repo's tree"). Consequence for the morning report: on an
   AlgoBooth `/lazy-batch-cloud` night the `LAZY_QUEUE.md` diff surface depends on that
   operator-side wiring being in place; the fallback morning read is the raw per-cycle commit log.
   Documented in `PLAYBOOK.md`; NOT fixed here (skill edits are out of this feature's locked
   scope, and the cloud skill is one half of a coupled pair).
3. **A dead run's plain `--run-end` can refuse over unacked hardening debt.** The `--run-end`
   handler (`user/scripts/lazy-state.py:9550-9570` region) refuses when unacked guard denials
   remain in the deny ledger ("The marker was NOT deleted"), with `--ack-unhardened` as the
   operator override (recorded in the run-end output for retro grading). The SPEC's crashed-run
   recovery one-liner (`--run-end` alone) is therefore best-effort; `PLAYBOOK.md` documents the
   full recovery including this branch.
4. **Line-anchor drift:** none material. Every "~line" the SPEC cites resolved within a few lines
   of the stated anchor (see table above).

## Integration points (all read-only for this feature)

- **Invoked orchestrator:** `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (budget
  args, terminal set, §1c.6 notification policy, mandatory `--run-end`, park/flush).
- **Arbitration layer:** `user/scripts/lazy_core.py` (`refuse_run_start_clobber`,
  `_MARKER_STALE_SECONDS`, `write_run_marker`, `claude_state_dir`/`repo_key`,
  `SANCTIONED_STOP_TERMINAL`).
- **State script:** `user/scripts/lazy-state.py` (`--run-start --unattended`, `--run-end`
  [+ `--ack-unhardened`], `--park-needs-input`/`--park-blocked`, `--marker-present`).
- **Morning read:** `user/scripts/lazy-queue-doc.py` + `user/skills/lazy-batch/SKILL.md` regen
  block; `docs/features/mobile-queue-control/SPEC.md` Decision 6 (qualifying repos =
  claude-config + AlgoBooth, push-to-`main`).
- **Soft dep:** `docs/features/operator-halt-notifications/SPEC.md` (halt paging — morning report
  leans on it when it lands; until then halts surface via `LAZY_QUEUE.md` + transcript).
- **Platform surface:** the trigger ops (`create_trigger` / `update_trigger` / `delete_trigger` /
  `fire_trigger` / `list_triggers` / `list_environments`) — managed via chat per D9; recipes in
  `RECIPES.md`.

## Conclusion

Every safety property the SPEC leans on exists and behaves as cited; zero code changes are needed
(confirming the SPEC's "zero state-script changes expected"). The deliverables are pure
documentation: `TRIGGER_TEMPLATE.md`, `RECIPES.md`, `PLAYBOOK.md`, and a `workspace/CLAUDE.md`
pointer. The two caveats above (skill availability per repo; cloud-side `LAZY_QUEUE.md` wiring)
are carried into those docs as explicit preconditions rather than silently assumed.
