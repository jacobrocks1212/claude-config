# PLAYBOOK — Failure/Recovery & Morning Triage (Scheduled Autonomous Runs)

> The operating contract around the nightly triggers: what each night's outcome looks like, what
> (if anything) to do about it, and the morning routine. Companion docs:
> [`TRIGGER_TEMPLATE.md`](./TRIGGER_TEMPLATE.md) (the fired prompt),
> [`RECIPES.md`](./RECIPES.md) (trigger ops). Every mechanism cited here is verified at file+line
> in [`RESEARCH_SUMMARY.md`](./RESEARCH_SUMMARY.md).
>
> Golden rule (D6, locked): **the arbitration layer is trusted as-is.** A refusal is the system
> working; the only marker you ever delete is a CONFIRMED-dead run's, via `--run-end`, from that
> repo.

## 1. Live-run refusal collision (evening run still going at fire time)

**What happens:** the fired session's `/lazy-batch-cloud` Step 0 runs
`lazy-state.py --cloud --run-start --unattended ...`; `lazy_core.refuse_run_start_clobber`
(lazy_core.py:10694) sees a live, age-fresh marker and exits **3 with ZERO side effects** —
stderr names the in-flight run (`pipeline`, `session_id`, `started_at`, `forward_cycles`). Per
the trigger prompt, the session STOPs and reports the refusal verbatim. Your live evening run is
untouched.

**Morning read:** the routine's completion push still arrives (it fires on EVERY fire — D5);
the session summary contains the refusal stderr.

**Action:** none. Nothing was clobbered; the queue work simply waits for the next night (or
recipe 3's `fire_trigger` once your interactive run ends).

**Drill (SPEC Phase 2a, operator-deferred):** `fire_trigger` while an interactive run holds the
marker → expect exactly the above; verify the interactive run's marker is byte-unchanged.

## 2. Crashed-marker recovery (last night's run hard-crashed)

**What happens:** a container reclaim before `--run-end` leaves the marker on disk (the
orchestrator otherwise runs `--run-end` on every terminal path — §1c.6). At the next nightly
fire the marker is **<24h old** (`_MARKER_STALE_SECONDS = 24*3600`, lazy_core.py:6459, vs ~24h
cadence minus the crash-to-fire gap), so tonight's `--run-start` ALSO refuses. Worst case: one
lost night per hard crash, surfaced by the completion push whose summary reports the refusal.

**Morning recovery (in that repo):**

1. **Confirm dead.** The refusal stderr names `session_id` + `started_at`; open that session —
   no live orchestrator loop means dead. Optional read-only check:
   `python3 ~/.claude/scripts/lazy-state.py --marker-present --repo-root <repo>` (exit 0 =
   marker present).
2. **End the dead run:** `python3 ~/.claude/scripts/lazy-state.py --run-end --repo-root <repo>`
   (deletes the marker + prompt registry).
   - **If it REFUSES over unacked guard denials** ("N unacked guard denial(s) remain in the deny
     ledger… The marker was NOT deleted"): either discharge the debt as directed
     (`--emit-dispatch hardening` per pending denial) or, having confirmed the run is dead and
     you accept retiring the debt, re-run with `--ack-unhardened` (the override is recorded in
     the run-end output for retro grading).
3. **Optionally re-run tonight's job now:** `fire_trigger` (RECIPES.md §3), with a `text` note
   that the marker was recovered.

**Never:** pre-run force-clean (`--run-end` before `--run-start` in the trigger prompt) — that
deletes a LIVE run's marker, exactly the clobber the arbitration refuses (D6 option C,
disqualified). And if >24h HAVE passed, no recovery is needed — the staleness path reclaims the
marker automatically at the next `--run-start`.

**Drill (SPEC Phase 2b, operator-deferred):** hand-plant an age-fresh marker in
`~/.claude/state/<repo_key>/`, fire → expect refusal; run the recovery above; next fire proceeds.

## 3. Needs-research halt overnight

**What happens:** the queue head needs research → strict halt (`needs-research` or, when
everything is research-gated, `queue-blocked-on-research`); sentinel written; the run ends with
`--run-end` + push. `--allow-research-skip` is deliberately NOT passed (D3) — but the script's
dependency-aware skip-ahead still spends the night's remaining budget on independent,
skip-ahead-eligible items, so a research-gated head does not by itself waste the night.

**Morning action:** supply the research. In claude-config that is a **direct `RESEARCH.md`
drop** into `docs/features/<slug>/` (or `docs/bugs/<slug>/`) — picked up by `lazy-state.py`
Step 5 → `/spec` Phase 3 naturally (root CLAUDE.md "Research resume in claude-config"). Then
either wait for tonight or `fire_trigger` now.

## 4. Nothing-to-do night (clean, quiet stops)

Three distinct clean terminals — the completion push's summary tells you which:

| Terminal | Meaning | Morning action |
|---|---|---|
| `cloud-queue-exhausted` | Every remaining feature awaits **workstation MCP validation** (`DEFERRED_NON_CLOUD.md` written per feature — the normal cloud stop) | Workstation flush (§5 step 4) |
| `queue-exhausted-all-parked` (`--park`) | Queue advanced past every workable item; the rest are parked (needs-input/blocked). The run-end flush question is pending in the fired session | Answer the flush (§5 step 3) |
| `all-features-complete` | Roadmap genuinely finished | Enjoy breakfast |

`max-cycles` is the fourth normal end: budget spent mid-queue; nothing to fix — the next night
continues from disk state.

## 5. Morning triage flow (the D5 compositional report)

1. **Phone, passive:** the routine's completion push (one per fire, INCLUDING refused/no-op
   fires — "no notification" cleanly means "the trigger didn't fire": check `list_triggers` for
   `enabled`/`next_run_at`). Plus halt pages once `operator-halt-notifications` lands (soft dep —
   until then, halts surface in steps 2–3).
2. **GitHub mobile:** open the repo's root `LAZY_QUEUE.md` — state deltas, "Needs attention"
   triage, run-active/idle marker; GitHub's native last-commit time is the freshness signal.
   *Caveat (RESEARCH_SUMMARY finding 2):* the per-cycle regen is wired in `/lazy-batch`
   (`user/skills/lazy-batch/SKILL.md:489-497`); the AlgoBooth cloud skill does not itself carry
   the regen block, so on a `/lazy-batch-cloud` night the doc may lag — **fallback:** read the
   night's per-cycle commit log on `main` directly (every cycle commits + pushes regardless).
3. **Claude app — the fired session:** read the final batch report (terminal reason, cycle
   table); if a parked-decision flush question is pending (D4), answer it there — it is the
   night's single decision inbox. (Pilot empirically checks the held-open question survives to
   morning; if it does not, D4's option C is the documented fallback and becomes its own
   coupled-skills change.)
4. **Workstation flush (D7 — the honest half of "overnight builder"):** the night produced
   spec/plan/implementation progress; MCP validation and receipt-gated completion still happen on
   the workstation. Run `/lazy-batch` (or `/lazy`) there — deferred items re-open through the
   existing Step 9/10 flow with zero special handling (`DEFERRED_NON_CLOUD.md` → MCP test →
   `VALIDATED.md` → `__mark_complete__`). No automation in v1; this step IS the completion path.

## 6. Quick reference — commands

| Situation | Command |
|---|---|
| Is a marker present for repo X? | `python3 ~/.claude/scripts/lazy-state.py --marker-present --repo-root <repo>` (exit 0/1; read-only) |
| End a confirmed-dead run | `python3 ~/.claude/scripts/lazy-state.py --run-end --repo-root <repo>` |
| …when it refuses over hardening debt | add `--ack-unhardened` (recorded override) — only after confirming dead |
| Run tonight's job now | `fire_trigger` (RECIPES.md §3) |
| Pause a repo's nights | `update_trigger enabled:false` (RECIPES.md §5) |
| What's scheduled? | `list_triggers` (RECIPES.md §4) |
