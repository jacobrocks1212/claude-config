# A lingering/same-repo run-marker arms validate-deny against unrelated (non-pipeline) dispatches → hardening debt gates run-end — Investigation Spec

> A run marker that is still live for THIS repo arms the validate-deny guard against every Agent dispatch in the session — including ordinary, unrelated design/spec dispatches. Those denials accrue as hardening debt that gates `--run-end`; the inverse (a foreign session's marker) silently disarms a live run's guard. Per-repo keying closed the cross-repo leak but left the same-repo / cross-session / stale dimension open because the guard gate is **session-blind** and the deny-ledger has **no pipeline-vs-unrelated discriminator**.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/stale-marker-arms-validate-deny-on-unrelated-dispatches
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/CLAUDE.md` "Per-repo keyed state dir"; `user/hooks/lazy-dispatch-guard.sh`; `user/scripts/lazy_guard.py`; `user/scripts/lazy_core.py` (`read_run_marker` / `append_deny_ledger_entry` / `pending_hardening`); `docs/features/multi-repo-concurrent-runs/` (per-repo marker keying, COMPLETE 2026-06-16 — fixed cross-REPO leakage; this is the residual SAME-repo / cross-session / stale class)

---

## Verified Symptoms

1. **[OBSERVED in logs]** A lingering checkpoint/run marker armed validate-deny against two unrelated dispatches, accruing hardening debt that gates `--run-end` — session `5d4b6c93` @ `2026-06-17T04:23:23Z`: "`pending_hardening: 2` — stray debt, not from this pipeline. The two unacked deny-ledger entries are from earlier Agent dispatches in this conversation (prompt heads: 'unified lazy-batch orchestrator spec' and 'toolification framework spec') that the validate-deny guard denied while a checkpoint-run marker was lingering — not pipeline cycle failures… they will gate `--run-end`. `--ack-unhardened` is operator-only…".
2. **[OBSERVED in logs]** A second session's marker silently DISARMED a live run's dispatch guard (fast-path allow, lost counters) — session `2899da98` @ `2026-06-12T15:01:49`: "a real design flaw that this conversation triggered against your live run… from ~8:53 it is silently unenforced — the guard fast-paths every dispatch (no marker → allow), probe registration stops, counters are lost."
3. **[OBSERVED in logs]** The disarm is driven by marker OWNERSHIP mismatch, not absence — session `2899da98` @ `2026-06-12T19:34:57`: "Your batch run's dispatch guard is silently disarmed — its hooks pass its session id, see a marker owned by someone else, and fast-path allow."

## Reproduction Steps

**Over-fire (Symptom 1) — a same-repo live marker arms deny against unrelated work:**
1. Start a `/lazy-batch` run in repo R (writes `lazy-run-marker.json` to `~/.claude/state/<repo_key(R)>/`).
2. In the SAME session (or a later session in the same repo while the marker is still live / not yet 24h-stale), dispatch an ordinary, NON-pipeline Agent (e.g. a hand-composed "spec this feature" prompt).
3. The dispatch-guard hook fires, sees a live marker for this repo (`--marker-present` exit 0), runs `lazy_guard.py`. The prompt is not in the run's prompt registry → **DENY** + a `lazy-deny-ledger.jsonl` append.

**Expected:** an unrelated, non-pipeline dispatch is not policed by a pipeline run's validate-deny guard, and never accrues hardening debt.
**Actual:** the dispatch is denied; the deny is charged as hardening debt; `pending_hardening()` rises; `--run-end` refuses until `--ack-unhardened` (operator-only) is run — gating an otherwise clean run-end on debt the pipeline never created.
**Consistency:** deterministic whenever an unregistered-prompt Agent dispatch occurs in a session while a same-repo run marker is live.

**Under-fire (Symptom 2) — a foreign session's marker disarms a live run's guard:**
1. Run A's `/lazy-batch` is live in repo R; its marker is bound to session_A.
2. A second session B (interactive, same repo) makes a dispatch. The guard reads the marker WITH `session_id=B`; the marker is bound to session_A ≠ B → `read_run_marker` returns `None` (staleness path B) → guard fast-path **ALLOW**.
3. For run A itself the guard still works (it passes session_A), BUT the underlying defect is that marker ownership is a single `session_id` slot: a marker rebound/overwritten by a competing run, or a marker whose bind raced to the wrong session, leaves run A's own dispatches reading "owned by someone else → allow", so probe registration stops and counters are lost.

**Expected:** a live run's guard stays armed for its own owning session regardless of concurrent sessions; a foreign session is invisible to it but cannot disarm it.
**Actual:** under a bind race / marker overwrite the owning run's guard silently fast-paths allow (no marker for me) — enforcement is off mid-run with no signal.
**Consistency:** intermittent — depends on the timing of a competing session's bind/overwrite versus run A's bind.

## Evidence Collected

### Source Code

**The guard gate is session-blind (the core over-fire mechanism).**
`user/hooks/lazy-dispatch-guard.sh` (lines 81-90) calls `lazy-state.py --marker-present --repo-root "$CWD"` with **no `--session-id`**. The handler (`lazy-state.py` lines 6210-6212) therefore calls `lazy_core.read_run_marker(session_id=None)`, which DISABLES staleness path B (`lazy_core.py` lines 6204-6206: the mismatch check only fires when BOTH the caller AND the marker carry a non-None session_id). So the *gate* that decides "run the guard at all" treats ANY non-stale, same-repo marker as present, for ANY dispatch in ANY session in that repo — there is no owning-session scoping at the gate. Per-repo keying (`multi-repo-concurrent-runs`) only narrows this to the repo dimension; within a repo, every in-session dispatch is policed.

**The guard has no pipeline-vs-unrelated discriminator.**
Once the gate passes, `lazy_guard.py::guard()` decides allow/deny PURELY by prompt-registry membership: a prompt is allowed only if its sha256 matches a script-emitted, fresh, unconsumed registry entry (lines 658-783). An unrelated hand-composed spec/design prompt is by construction absent from the registry → it lands on the default-deny path (`_deny_and_ledger`, lines 780-783). There is no check for "is this dispatch even part of the pipeline?" — the guard assumes every dispatch under a live marker is a pipeline cycle attempt.

**Every deny is charged identically as hardening debt.**
`lazy_guard.py::_deny_and_ledger` (lines 486-514) appends to `lazy-deny-ledger.jsonl` via `lazy_core.append_deny_ledger_entry`. The entry shape (`lazy_core.py` lines 8012-8019) is `{ts, tool_use_id, denied_sha12, reason_head, prompt_head, acked:false}` — it records NOTHING about whether the denied dispatch was a pipeline cycle or unrelated session work. `pending_hardening()` (lines 8397-8403) counts every `acked == false` entry. The `--run-end` gate refuses while any unacked entry remains unless `--ack-unhardened` (operator-only) is passed. So an unrelated dispatch's deny is indistinguishable from a real validate-deny and gates run-end exactly the same. (Two existing event kinds — `auto_readmit` and `dispatch_by_reference` — are explicitly EXCLUDED from the debt count; an "unrelated dispatch" carries no such exclusion.)

**The transcription-slip path proves the precedent for a no-debt deny.**
`lazy_guard.py` already has a deny path that does NOT accrue debt: `_deny_no_ledger` for a transcription slip (lines 252-267, 769-776). This establishes the in-codebase pattern for "deny this dispatch but do not charge hardening debt" — the unrelated-dispatch case is a second member of that class.

**Marker ownership is a single mutable slot (the under-fire mechanism).**
`read_run_marker` staleness path B (`lazy_core.py` lines 6195-6206) is NON-destructive and asymmetric by design (Phase 8 WU-8.1, to fix the 2026-06-12 ~14:53Z destructive-disarm). `bind_marker_session` (lines 6211-6252) stamps the marker's single `session_id` slot once (first-writer-wins, idempotent). `lazy_guard.py::_bind_marker_on_allow` (lines 377-401) moved the bind anchor to allow-time (Phase 9 WU-9.2) precisely to make ownership unforgeable by a bystander. The residual hole: the slot is still a single owner; a marker overwrite (`--run-start` clobber path) or an unbound-marker bind race can stamp the wrong session, after which the true owner's own dispatches read "owned by someone else → None → allow" — silent disarm.

### Git History

The immediately prior bug work in this repo (`probe-full-read-before-dispatch`, commits `ac67713`…`4310bd7`) hardened a different lazy-probe class. The `multi-repo-concurrent-runs` feature (COMPLETE 2026-06-16, per `**Related:**`) introduced per-repo keying via `claude_state_dir()` and rewired the three hooks to the `--marker-present` gate — closing cross-repo contagion. This investigation is the residual same-repo / cross-session / stale dimension that keying did not address.

### Related Documentation

- `user/scripts/CLAUDE.md` → "Per-repo keyed state dir": documents the `--marker-present` gate and explicitly scopes its guarantee to the REPO dimension ("a marker for a *different* repo resolves to a different subdir → absent → the hook is a no-op"). It makes no same-session / same-repo ownership claim — consistent with the gap found here.
- `user/scripts/CLAUDE.md` → run-checkpoint contract: a `--run-end --reason checkpoint` writes `lazy-run-checkpoint.json` and the next `--run-start` consumes it. A checkpoint pause does NOT clear the *run marker* logic in a way that prevents a lingering same-repo marker; the audit's "checkpoint-run marker was lingering" wording (Symptom 1) is consistent with a marker that outlived the orchestrator's active dispatch window within the 24h age window.

## Theories

### Theory 1: The guard gate is session-blind, so a same-repo live marker arms validate-deny against ALL in-session dispatches (over-fire)
- **Hypothesis:** Because `lazy-dispatch-guard.sh` queries `--marker-present` without a session id, the guard runs for every dispatch in the repo while a marker is live — including unrelated, non-pipeline dispatches — and those denies become hardening debt that gates `--run-end`.
- **Supporting evidence:** Hook line 81-90 (no `--session-id`); handler line 6211 (`session_id=None`); `read_run_marker` lines 6204-6206 (path B disabled when session_id is None); `lazy_guard.py` lines 658-783 (registry-membership is the ONLY allow criterion; no pipeline-membership test); deny-ledger entry shape lines 8012-8019 (no discriminator); Symptom 1 log.
- **Contradicting evidence:** None found.
- **Status:** Confirmed.

### Theory 2: Single-slot marker ownership permits a foreign/overwriting session to disarm a live run's guard (under-fire)
- **Hypothesis:** A marker's `session_id` is one mutable slot; an overwrite or wrong-session bind makes the true owner read "owned by someone else → None → fast-path allow," silently disabling enforcement mid-run.
- **Supporting evidence:** Symptom 3 log ("a marker owned by someone else… fast-path allow"); `bind_marker_session` single-slot first-writer-wins (lines 6211-6252); `_bind_marker_on_allow` (lines 377-401) added specifically to harden the bind anchor against this; `read_run_marker` path B returns None on mismatch (lines 6204-6206).
- **Contradicting evidence:** The Phase 9 WU-9.2 allow-time bind already narrows the race (only an orchestrator allow binds), so the remaining window is the `--run-start` clobber/overwrite case + any pre-allow bind. Partial mitigation exists; the slot model itself is the residual.
- **Status:** Confirmed (residual, partially mitigated).

## Proven Findings

1. **Root cause (over-fire):** The validate-deny enforcement has TWO independent gaps that compound. (a) The hook's `--marker-present` gate is **session-blind** (no `--session-id` passed), so within a repo every in-session Agent dispatch is policed while any non-stale marker is live. (b) `lazy_guard.py` allows ONLY registry-registered prompts and charges EVERY other deny as hardening debt, with **no notion of pipeline-vs-unrelated** — so an ordinary hand-composed design/spec dispatch is denied and its deny gates `--run-end`. Per-repo keying narrowed (a) to the repo dimension but left the same-repo / same-session / stale window fully open.
2. **Root cause (under-fire):** Marker ownership is a **single mutable `session_id` slot**; an overwrite or wrong-session bind makes the true owner's dispatches read "not my marker → allow," silently disarming enforcement mid-run. Phase 9 WU-9.2 (allow-time bind) reduced but did not eliminate the race surface.
3. **The deny ledger is the choke point for the over-fire fix.** Because `pending_hardening()` / the `--run-end` gate count every unacked entry uniformly, and two event kinds (`auto_readmit`, `dispatch_by_reference`) are ALREADY excluded from the count, the cleanest correction is to classify a denied dispatch as "unrelated / non-pipeline" and either NOT ledger it as debt (mirroring the existing `_deny_no_ledger` transcription-slip path) or ledger it with a non-debt discriminator that `pending_hardening()` skips. The discriminator dimension does not yet exist in the entry shape.
4. **Distinguishing "pipeline" from "unrelated" is the load-bearing design decision** and is left to `/plan-bug`. Candidate signals (NOT pre-baked here): owning-session match (gate the guard on owning session, not mere repo-presence), an explicit orchestrator/subagent env or `agent_id` marker on the dispatch, or a heuristic on prompt provenance. The fix must preserve the sacred invariants: fail-OPEN on any error, never DESTROY the owning run's marker from a non-owner read (Phase 8 WU-8.1), and never weaken the depth-1 hardening cap.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Dispatch-guard gate (session-blindness) | `user/hooks/lazy-dispatch-guard.sh` (lines 81-90); `user/scripts/lazy-state.py` `--marker-present` handler (lines 6210-6212) | Gate runs the guard for ALL in-session dispatches in the repo; no owning-session scoping → over-fire against unrelated work. |
| Guard allow/deny + debt accrual | `user/scripts/lazy_guard.py` (`guard`, `_deny_and_ledger`, `_deny_no_ledger`) | No pipeline-vs-unrelated discriminator; every non-registry deny is charged as hardening debt. |
| Deny ledger + debt count + run-end gate | `user/scripts/lazy_core.py` (`append_deny_ledger_entry`, `pending_hardening`, `oldest_unacked_deny`, the `--run-end` refusal) | Entry shape has no discriminator; an unrelated deny gates `--run-end` and forces operator-only `--ack-unhardened`. |
| Marker ownership model (under-fire) | `user/scripts/lazy_core.py` (`read_run_marker` path B, `bind_marker_session`); `user/scripts/lazy_guard.py` (`_bind_marker_on_allow`) | Single mutable `session_id` slot; overwrite / wrong-session bind silently disarms the owner's guard. |
| Regression net | `user/scripts/test_hooks.py`, `test_lazy_core.py`, `lazy-state.py --test` | New fixtures needed: an unrelated in-session dispatch must NOT accrue debt; the owning session's guard must stay armed under a concurrent session. |

## Open Questions (for `/plan-bug` — design decisions, not blockers)

- **Discriminator mechanism:** owning-session scoping (pass `--session-id` so the gate consults the owning session) vs. an explicit orchestrator/`agent_id` provenance signal vs. a non-debt ledger discriminator — which one (or combination) cleanly separates pipeline cycles from unrelated in-session dispatches without weakening enforcement? (Each diverges in enforcement semantics — a product-class decision for the planning step.)
- **Disposition of an unrelated deny:** allow it through (gate scoped out) vs. deny-but-no-ledger (mirror `_deny_no_ledger`) vs. ledger-with-skip-discriminator. The first stops policing unrelated work entirely; the latter two keep a deny but drop the debt.
- **Under-fire fix scope:** is closing the residual single-slot ownership race in-scope for this bug, or split to a dedicated follow-up? The over-fire (Symptom 1) and under-fire (Symptom 2/3) share the marker but have opposite failure directions and largely independent fixes.
