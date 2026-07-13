---
kind: investigation-spec
bug_id: adhoc-incident-hook-deny-19343d
---

# Repeated hook deny: lazy-cycle-containment loop-formation-flag (3x/24h) — Investigation Spec

> incident-scan auto-captured 3 `lazy-cycle-containment` `loop-formation-flag` denies in claude-config within 24h (2026-07-12 14:24→15:59Z). Investigation traces the deny mechanism to correct-by-design containment and correlates all three to the `live-settings-split-brain-disarms-enforcement-plane` remediation run; the specific driving command is not transcript-recoverable, so the disposition (working-as-designed close vs. durable traceability fix) is an operator decision.

**Status:** Won't-fix
**Severity:** Low
**Discovered:** 2026-07-12
**Placement:** docs/bugs/adhoc-incident-hook-deny-19343d
**Related:** `docs/bugs/live-settings-split-brain-disarms-enforcement-plane` (the run these denies occurred within); `docs/bugs/adhoc-incident-hook-deny-4b767b` (prior containment-deny false-positive incident); `docs/bugs/adhoc-containment-denies-mandated-explore-fanout` (prior containment-scope carve-out); feature `incident-auto-capture` (the collector that raised this stub)

---

## Verified Symptoms

1. **[REPORTED]** incident-scan captured 3 `hook-deny` events with hook `lazy-cycle-containment` + signature `loop-formation-flag` for repo claude-config between 2026-07-12T14:24:08Z and 2026-07-12T15:59:24Z (`incident_key claude-config|hook-deny|lazy-cycle-containment|loop-formation-flag`). Source: this dir's `INCIDENT.md` capsule + the keyed `hook-events.jsonl` (`~/.claude/state/853ac81…/hook-events.jsonl`). Not user-observed — this is an autonomous-run signal captured by the harness; there is no interactive human symptom to confirm via AskUserQuestion.

## Reproduction Steps

The event itself is deterministic given the trigger; to reproduce a `loop-formation-flag` deny:

1. Ensure `lazy-cycle-containment.sh` is registered in the live `user/settings.json` PreToolUse(Bash) chain (it was UNREGISTERED on this machine 2026-06-11→2026-07-12 — see the split-brain bug + the `BLIND_WINDOW` constant in `incident-scan.py`).
2. From inside a dispatched cycle subagent (a tool-call whose PreToolUse payload carries an `agent_id`), run a Bash command invoking a state script with a routing/lifecycle flag, e.g. `python3 ~/.claude/scripts/bug-state.py --probe --repo-root <cwd>` (or any of `--emit-prompt` / `--run-start` / `--run-end` / `--apply-pseudo` / `--enqueue-adhoc` / `--emit-dispatch` / `--cycle-begin` / `--cycle-end` / `--repeat-count[-peek]`).
3. Observe the PreToolUse deny + a `deny`/`loop-formation-flag` line appended to the keyed `hook-events.jsonl`.

**Expected:** the hook denies the op (the routing/lifecycle flags are orchestrator-only). This is the intended containment behavior.
**Actual:** identical — the hook denies the op. The "bug" is not a mis-fire; it is the *recurrence* being surfaced as a bug stub with no transcript to pin the driver.
**Consistency:** deterministic given the trigger (subagent context + a loop-formation flag on a state-script command).

## Evidence Collected

### Source Code

- **Deny site — `user/hooks/lazy-cycle-containment.sh:473`** — `_deny(CORRECTIVE, "loop-formation-flag")`. Reached in `main()` iff **all** hold:
  - `is_subagent` is true — `payload.get("agent_id")` present (line 408); the main-thread orchestrator has no `agent_id` and is never self-denied.
  - the command matches `_STATE_PY_RE = \b(lazy-state|bug-state)\.py\b` (line 469).
  - the command does **not** contain an allow-listed flag `--neutralize-sentinel` / `--verify-ledger` (line 470 short-circuits ALLOW first).
  - the command contains a `LOOP_FORMATION_FLAGS` member (line 472): `--probe, --emit-prompt, --repeat-count, --repeat-count-peek, --run-start, --run-end, --apply-pseudo, --enqueue-adhoc, --emit-dispatch, --cycle-end, --cycle-begin`.
- **No legitimate cycle-subagent path reaches a loop-formation flag.** A dispatched subagent's only sanctioned state-script calls are `--verify-ledger` (the mandated turn-end verifier — allow-listed at line 470) and non-routing reads (`--marker-present` / `--marker-work-branch` / `--provenance-lookup` — no routing flag → the "state-script call with no routing flag → allow" fall-through at line 474). **Every** `LOOP_FORMATION_FLAG` op is orchestrator-only by the C3 lockstep contract (`lazy_core.refuse_if_cycle_active` refuses the identical set with exit 3, "ZERO side effects"; documented in `user/scripts/CLAUDE.md`). Therefore a `loop-formation-flag` deny is **categorically the containment hook working as designed** — it is never a false positive (unlike the recursion-token false-positive class fixed in `adhoc-incident-hook-deny-4b767b`, which keyed on a text match, not on a subagent invoking an orchestrator-only flag).
- The deny event records only the CORRECTIVE reason string, **not the offending command** (`_deny` → `_append_hook_event("deny", "loop-formation-flag", reason)`; `reason` is the fixed CORRECTIVE text). This is the traceability gap that blocks pinning the exact driving op.

### Runtime Evidence

- Keyed state dir `~/.claude/state/853ac81ed4c78fc48ca40112a1426e224f3475bb/` (claude-config's `repo_key`).
- **`hook-events.jsonl`** — the 3 verbatim `loop-formation-flag` deny lines (ts 1783866248 / 1783870103 / 1783871964 = 14:24:08 / 15:28:23 / 15:59:24Z). All carry `repo_root: C:\Users\Jacob\source\repos\claude-config` (a **workstation** run — not cloud; the Windows path rules out a cloud Linux-path origin).
- **`lazy-deny-ledger.jsonl` correlation (the key finding)** — the dispatch/deny entries surrounding all three timestamps are for `item_id: live-settings-split-brain-disarms-enforcement-plane`:
  - …1783865564Z dispatch (split-brain) → **1783866248Z loop-formation deny #1** → 1783868620Z dispatch (split-brain) → **1783870103Z deny #2** → 1783870830Z dispatch (split-brain) → **1783871964Z deny #3** → 1783874978Z dispatch (split-brain).
  - The first dispatch for *this* incident bug (`adhoc-incident-hook-deny-19343d`) is at 1783875236Z (16:53Z), **after** all three denies. So the current bug-pipeline session did not produce them.
- **Temporal root cause:** the enforcement hooks were unregistered in the live `settings.json` for 2026-06-11→2026-07-12 (`live-settings-split-brain-disarms-enforcement-plane`; `incident-scan.py` `BLIND_WINDOW`). These 3 denies are the **first** `loop-formation-flag` fires after `lazy-cycle-containment.sh` was re-registered — and they occur inside the very run that performed the re-registration. They are the containment hook coming back online and catching in-flight cycle-subagent overreach during that remediation.

### Git History

- Recent claude-config commits (all on `main`, 2026-07-12) are the split-brain remediation + its receipts (`fix(live-settings-split-brain-disarms-enforcement-plane): mark fixed and archive`; `chore(...): coherence-recovery`; `grant structural MCP-skip`; `end-of-run flush — incident stub (adhoc-incident-hook-deny-19343d) + split-brain intervention record`). The incident stub for THIS bug was enqueued by that run's end-of-run `incident-scan` flush.

### Related Documentation

- `user/scripts/CLAUDE.md` — the C2 hook / C3 script lockstep: the C2 `LOOP_FORMATION_FLAGS` deny-set and the C3 `refuse_if_cycle_active` refused-op set are kept in lockstep; both are orchestrator-only.
- `user/hooks/lazy-cycle-containment.sh` header — documents the agent_id-targeted (D4) arming-free trip and the 2026-07-09 carve-out that removed recursive Agent/Task dispatch from the deny set (`adhoc-containment-denies-mandated-explore-fanout`).
- `INCIDENT.md` (this dir) — the evidence capsule; "The collector proposes evidence; `/spec-bug` owns root cause."

## Theories

### Theory 1: Working-as-designed containment during the split-brain re-arm (LIKELY)
- **Hypothesis:** Cycle subagents in the `live-settings-split-brain-disarms-enforcement-plane` run invoked an orchestrator-only state-script routing/lifecycle flag mid-cycle; the freshly re-registered `lazy-cycle-containment.sh` correctly denied each. No standing code defect.
- **Supporting evidence:** all 3 denies bracket split-brain dispatch entries in the deny ledger; the hook is provably correct (no legitimate subagent path to a loop-formation flag); the denies are the first after the hook re-armed; the run's whole purpose was re-arming the enforcement plane.
- **Contradicting evidence:** none observed. (The exact command per deny is not recoverable, so "a subagent overreached" is established structurally, not by reading each command.)
- **Status:** Likely.

### Theory 2: A standing skill/component mandates a subagent loop-formation op (RULED OUT for the observed run)
- **Hypothesis:** Some skill a cycle subagent runs shells a state-script routing flag as normal operation → recurring false-deny.
- **Supporting evidence:** none found. A grep over `user/skills/**` for a state script + a loop-formation flag surfaced only orchestrator-path sites (`adhoc-enqueue.md` `--enqueue-adhoc`, `completion-integrity-gate.md` / `mark-fixed-archive.md` `--apply-pseudo`, and the `/lazy*` orchestrators) — all main-thread (agent_id absent) by contract; none is on a dispatched-subagent path.
- **Contradicting evidence:** the mandated turn-end verifier a subagent DOES run (`--verify-ledger`) is allow-listed and cannot trip this signature.
- **Status:** Ruled Out for the observed cluster (no standing driver identified). Cannot be ruled out for *all future* recurrences without the offending command captured (see Open Questions / the traceability gap).

## Proven Findings

- **The deny mechanism is correct-by-design and is NOT the fix site.** `loop-formation-flag` is categorically not a false positive: it fires only when a subagent invokes an orchestrator-only state-script flag, which no sanctioned subagent path does. Any "fix" that relaxes the hook would re-open the runaway-loop hole the C2/C3 lockstep exists to close.
- **The observed cluster is contained to one remediation run** (`live-settings-split-brain-disarms-enforcement-plane`), correlated via the deny ledger, and is best explained as the hook re-arming mid-run.
- **The exact driving command is not transcript-recoverable** — the deny event stores only the fixed CORRECTIVE string, and no 2026-07-12 workstation transcript survives locally (newest project `.jsonl` is dated Jun 29; no `subagents/` transcripts present). So the specific op per deny (`--probe` vs `--emit-prompt` vs `--cycle-begin` …) and its authoring instruction are `asserted`, not `traced`.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Containment hook (deny site) | `user/hooks/lazy-cycle-containment.sh` | Provably correct — NOT to be relaxed. Candidate only for an *additive* traceability enrichment (record the offending command in the deny event). |
| Deny-event capture | `lazy-cycle-containment.sh` `_append_hook_event` / `lazy_core.append_hook_event` | The event omits the offending command → future `loop-formation-flag` recurrences are equally un-root-causable. |
| Incident collector | `user/scripts/incident-scan.py` | Raised this stub from a provably-working-as-designed deny class; may warrant dedup/down-weight of never-false-positive containment signatures. |

## Open Questions

- **Disposition (operator-authority — surfaced in `NEEDS_INPUT.md`): RESOLVED 2026-07-12 — Close as working-as-designed, no code change.** The operator selected the recommended disposition: the containment hook is provably correct (relaxing it would re-open the runaway-loop hole the C2/C3 lockstep closes), the cluster is a one-off transient of the split-brain enforcement-plane re-arm, and no standing skill/component driver was found. This queue item resolves toward `Won't-fix` (no code change; the Won't-fix status flip itself remains receipt-gated — deferred to the pipeline's completion path, not set here). **No spin-off enqueued this cycle:** the durable-traceability option (capture the offending command in `loop-formation-flag` deny events) remains the recommended follow-up should the signature recur *outside* a re-arm event; it was deliberately not implemented, to avoid relaxing the correct hook or blinding the collector.
- Not recoverable from current evidence: the exact state-script command each of the 3 subagents ran, and the specific instruction that drove it. (Accepted as low-risk given severity Low and no product impact; the traceability gap persists by operator decision.)
