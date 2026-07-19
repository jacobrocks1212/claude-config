---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
class: harness
divergence: structural
next_skill: harden-harness
decisions:
  - "Same-run concurrent-dispatch commit attribution: how should `detect_cycle_bracket_friction`'s `unexpected-commits` signal stop charging a cycle's budget for commits made by a SANCTIONED CONCURRENT DISPATCH within the SAME run (a background `/harden-harness` lane, a between-cycle `--archive-fixed` reconcile) that shares this box's single git identity AND the live run identity — so BOTH existing attribution arms (distinct committer-email; distinct-run-identity ledger) attribute it 0? Recommended: measure the cycle's OWN commits directly (per-commit cycle-nonce attribution feeding a purely-additive subtraction) rather than the pollutable `begin_head_sha..HEAD` window count. Forks the detector's core measurement approach; gate-integrity (false-negative) stakes. (harden Round 111, 2026-07-19)"
date: 2026-07-19
---

## Decision Context

An observed-friction dispatch (item in flight `decision-2-6-uncovered-row-reroute-to-mcp-test`,
claude-config, bug pipeline at Step 10 `__mark_fixed__`) logged a FALSE `unexpected-commits`
process-friction:

```
HEAD advanced 11 commits since --cycle-begin
(begin_head_sha=6cd9be290bc3, sub_skill='execute-plan', budget=7)
```

`begin_head_sha` `6cd9be29` is the harden Round-109 guard+skill commit. Of the 11 window commits,
the `decision-2-6` execute-plan cycle's OWN work was **3** (`fix(decision-2-6-reroute): WU-1/2/3`);
the other **8 were concurrent same-run writers** — Round-109 harden, Round-110 harden, a
wedge-backstop `--archive-fixed`, and reconcile/provenance ops — all interleaved with the WU commits,
all under this box's single git identity AND the same live run marker. Root cause is CONCLUDED and
runtime-verified: `docs/bugs/process-friction-counts-same-run-concurrent-dispatch-commits/SPEC.md`.

The detector's two concurrent-writer attribution arms (`_count_concurrent_writer_commits`,
`user/scripts/lazy_core/markers.py:2148`) are BOTH structurally blind to this shape:
- **Signal 1 (committer-email)** — attributes a window commit iff `email != own_email`. This box has
  ONE git identity (`66210812+jacobrocks1212@...`, no work `includeIf`), so a same-identity
  concurrent dispatch is attributed 0.
- **Signal 2 (concurrent-activity ledger)** — attributes a window sha iff its recorded
  `run_started_at` is present AND `!= current_run_started_at`. A dispatch WITHIN the same run shares
  this run's `started_at`, so `rsa != current` is False → attributed 0. (It also only sees SCRIPT-
  OWNED commit sites; the Agent-driven `harden(...)` commits are absent from the ledger entirely.)

**Dispositive runtime proof:** the friction detail carried **no** `concurrent_writer_commits=...,
chargeable=...` suffix. That suffix is emitted iff `chargeable_commits != commits_since`
(`markers.py:2016`); its absence proves the attribution returned **0/None** for all 8 concurrent
commits.

**File-level divergence: `structural`.** The candidate fixes fork the friction detector's CORE
MEASUREMENT — replacing or bounding the `begin_head_sha..HEAD` window numerator (the ONLY signal that
reads git directly and therefore the ONLY one that catches a hook-BYPASSED runaway) — a load-bearing
INTEGRITY gate. A wrong provisional pick that lets the cycle's own runaway slip below the budget is a
false NEGATIVE that masks a genuine runaway (gate-integrity loss, expensive/dangerous to redirect).
This is the THIRD recurrence of the concurrent-writer / `unexpected-commits` class (after
`gate-scope-folds-concurrent-harden-commits` and
`adhoc-process-friction-detector-counts-concurrent-session-commits`); each prior fix added another
committer-attribution ARM to the same pollutable proxy. The durable fix is a measurement redesign,
not a fourth arm — exactly the over-fit whack-a-mole the anti-overfit reflex exists to stop. Per the
`/harden-harness` park-provisional **structural** carve-out this is HARD-PARKED: nothing implemented
until the operator ratifies the measurement approach. The friction is **non-blocking** (observed-
friction background harden — the run continues on current behavior), so no interim degradation
justifies a risky/partial provisional (mirrors Round 108's reasoning).

### 1. Same-run concurrent-dispatch commit attribution mechanism

**Problem:** the `unexpected-commits` signal answers "did THIS cycle's dispatch commit beyond its
budget?" via the `begin_head_sha..HEAD` window count — a PROXY that assumes the cycle's own subagent
is the only writer in the window. Under the sanctioned concurrent-writer regime (`<orchestration>`)
that assumption is false, and neither attribution arm can subtract a same-run, same-identity
concurrent commit.

**Options:**

- **A — Per-commit cycle-nonce attribution → purely-additive subtraction (Recommended).**
  Give each cycle's OWN commits a durable, cheap tag keyed on the cycle marker's `nonce`, and attribute
  as concurrent any window commit whose tag is a DIFFERENT (or absent) cycle nonce. Two viable
  taggers: (a) the C2 hook (`lazy-cycle-containment.sh`) already increments the cycle marker's
  `commit_tally` on each allowed `git commit` while the marker is live — extend it to append each
  such sha to a per-repo-keyed `lazy-cycle-commit-attribution.jsonl` `{sha: nonce}` (the
  `append_concurrent_commit_sha` precedent), OR (b) stamp a `Cycle-Nonce: <nonce>` commit trailer at
  the sanctioned commit sites. `_count_concurrent_writer_commits` gains a THIRD arm: a window sha
  whose recorded nonce `!= current cycle nonce` (or absent) is attributed concurrent. **Purely
  additive** — it only ever SUBTRACTS commits provably NOT made under this cycle's nonce; it never
  reduces the count of the cycle's OWN commits, so it introduces NO false negative and does not weaken
  the runaway catch. Cost: instrument the commit path + a new ledger/schema; coupled-pair mirror on
  `bug-state.py`; new tests. Residual: a background harden that commits via a path the C2 hook does
  not intercept is untagged → treated as concurrent (correct here) — but a genuine hook-bypassed
  runaway of the CYCLE's own would ALSO be untagged and thus (wrongly) exempted; mitigated by keeping
  the raw window count as the fallback when the cycle produced zero tagged commits, and by the fact
  that a hook-bypassed commit already evades the `commit_tally` COMMIT_CEILING tripwire too (no NEW
  blind spot). This is the state-machine-correct direction: measure the cycle's own commits, not a
  window the whole run pollutes.

- **B — Cap `chargeable_commits` by the cycle marker's own `commit_tally`.** `chargeable = min(commits_since
  − concurrent, commit_tally)`. Simple, one-site, no new ledger. BUT `commit_tally` counts commits
  made while THIS marker was live — it is polluted by concurrent commits DURING the live window (only
  excludes between-cycle ops), so it is PARTIAL for the headline background-harden case; and it REMOVES
  the window count's unique ability to catch a hook-BYPASSED runaway (a runaway that evades the C2
  hook has a low `commit_tally` → capped below budget → masked). **Coverage-reducing / brushes
  gate-weakening — not recommended.**

- **C — Message-class attribution: exempt a window commit whose message does not reference the
  cycle's `feature_id`.** Structurally grounded (a commit for a DIFFERENT slug is not this cycle's
  work) but heuristic and fragile (execute-plan commits do not always name the slug; gameable), and
  over-fits commit-message shape. Not recommended.

- **D — Broaden the ledger arm to record every SCRIPT-OWNED between-cycle commit site
  (`--archive-fixed` / `--link-provenance` / the per-cycle orchestrator commit) under the current
  cycle nonce.** A subset of option A that closes the between-cycle reconcile commits (e.g.
  `b6614775`) but NOT the Agent-driven `harden(...)` commits (no script site to instrument), so it is
  partial for the headline case. Fold into A rather than shipping alone.

**Recommendation:** **Option A** (per-commit cycle-nonce attribution, purely-additive subtraction).
It is the only option that is BOTH structurally correct (measures the cycle's own commits) AND
non-gate-weakening (additive; never masks a runaway). Requires operator ratification because it
forks the friction detector's core measurement and is coupled-pair mirrored across both state
scripts + the C2 hook.

## Out of scope (verified, not a decision)

- **The `unexpected-commits` signal itself and its budget derivation** stay — a genuine single-cycle
  runaway must still trip. Only the ATTRIBUTION numerator is at issue.
- **The `<orchestration>` sanctioned-concurrent-writers policy** is correct and unchanged; the fix
  makes the detector HONOR it, it does not relax the policy.
- **Widening the budget / adding a concurrency slack** is explicitly REJECTED — that is
  gate-weakening (softening the threshold to clear the trip), Prohibition #2.

## Resolution

(unresolved — awaiting operator ratification of the measurement approach for decision 1)
