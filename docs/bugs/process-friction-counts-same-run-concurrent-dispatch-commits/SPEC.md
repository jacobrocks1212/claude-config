# Process-friction `unexpected-commits` counts same-run concurrent-dispatch commits — Investigation Spec

> `detect_cycle_bracket_friction`'s `unexpected-commits` signal subtracts a concurrent-writer
> commit count attributed by (1) a DIFFERENT committer-email OR (2) a ledger sha stamped under a
> DIFFERENT run identity. A background harden dispatch / between-cycle reconcile op that commits
> to the shared branch DURING an execute-plan cycle shares THIS box's single git identity AND the
> SAME live run identity, so BOTH arms attribute it 0 — its commits fully charge the cycle's own
> budget and trip a FALSE `unexpected-commits` process-friction (self-announcing hardening debt).

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-19
**Placement:** docs/bugs/process-friction-counts-same-run-concurrent-dispatch-commits
**Related:**
- `docs/bugs/_archive/adhoc-process-friction-detector-counts-concurrent-session-commits` — the DIRECT predecessor (added the distinct-run-identity ledger arm for a *second session*; this is the NEXT axis: a same-run, same-identity concurrent DISPATCH).
- `docs/bugs/_archive/gate-scope-folds-concurrent-harden-commits` — the sibling concurrent-commit blind spot on the `harness-gate` scope side.
- `docs/bugs/_archive/end-of-run-flush-commit-absorbs-concurrent-writer-staged-files` — the sibling concurrent-writer file-absorption blind spot at the flush commit.
- Root `CLAUDE.md` `<orchestration>` "sanctioned concurrent writers" carve-out — the policy the detector must honor ("an unexpected commit / moved HEAD is expected, not a defect").

<!-- Status lifecycle: Concluded → root cause traced; fix operator-PARKED (structural + gate-integrity carve-out). See the harden-harness NEEDS_INPUT below. -->

---

## Verified Symptoms

1. **[VERIFIED]** For a `--cycle-end` bracket whose `begin_head_sha..HEAD` window includes commits
   made by a *concurrent dispatch within the SAME run* on this machine (a background `/harden-harness`
   lane, a between-cycle `--archive-fixed` reconcile, an orchestrator per-cycle commit) under the
   **same configured git identity** AND the **same live run marker** as the cycle, those commits are
   counted in `commits_since` but attributed **0** to `concurrent_writer_commits`, so they fully
   charge the cycle's per-`sub_skill` budget and trip `reason: unexpected-commits`. — Confirmed by
   reading the serving code: `_count_concurrent_writer_commits`
   (`user/scripts/lazy_core/markers.py:2148`) unions ONLY (a) `email != own_email` and (b) a ledger
   sha whose recorded `run_started_at` is present AND `!= current_run_started_at`; a same-identity,
   same-run commit satisfies NEITHER.

2. **[VERIFIED — live incident 2026-07-19]** The dispatch that produced THIS spec:
   `HEAD advanced 11 commits since --cycle-begin (begin_head_sha=6cd9be290bc3, sub_skill='execute-plan', budget=7)`
   for the `decision-2-6-uncovered-row-reroute-to-mcp-test` execute-plan cycle. `begin_head_sha`
   `6cd9be29` is the harden Round-109 guard+skill commit. Of the 11 window commits, the cycle's OWN
   work was 3 (`fix(decision-2-6-reroute): WU-1/WU-2/WU-3` — `c2bca4d0`/`7e3bb229`/`aa056e87`); the
   other 8 were **concurrent same-run writers** — Round-109 harden (`7e2f54b5`/`5e1e587d`), Round-110
   harden (`57b07fe5`/`9ce3b8f1`/`92ea3305`), a wedge-backstop mark-fixed+archive (`b6614775`), and
   further reconcile/provenance ops — all interleaved with the WU commits, all under the shared git
   identity + run marker.

3. **[VERIFIED — dispositive from the detail STRING]** The friction detail carried **no**
   `concurrent_writer_commits=..., chargeable=...` suffix. That suffix is emitted iff
   `chargeable_commits != commits_since` (`markers.py:2016`). Its ABSENCE proves
   `chargeable_commits == commits_since == 11`, i.e. the attribution returned **0/None** for all 8
   concurrent commits — affirmative runtime evidence that BOTH arms were blind to them.

## Reproduction Steps

1. Start a `/lazy-batch` (or unified) run in `claude-config` on `main`; let an `execute-plan` cycle
   `--cycle-begin` snapshot `begin_head_sha`.
2. During that cycle's window, have a **sanctioned concurrent dispatch in the SAME run** commit
   ≥ (budget + this-cycle's-own-commits + 1) commits to `main` under the same git identity — e.g. a
   background `/harden-harness` lane landing `harden(...)` commits, or the orchestrator honoring a
   reconcile handback via `bug-state.py --archive-fixed` between cycles.
3. Let the execute-plan cycle reach `--cycle-end`.

**Expected:** the concurrent same-run commits are attributed to the concurrent writer and NOT
charged against this cycle's budget; no `unexpected-commits` friction is logged (per the
`<orchestration>` "sanctioned concurrent writers" carve-out).
**Actual:** `_count_concurrent_writer_commits` returns 0 (all emails equal `own_email`; no window sha
is in the ledger under a different run identity), so `chargeable_commits == commits_since > budget`;
`reason: unexpected-commits` fires, a `kind: process-friction` entry is appended to
`lazy-deny-ledger.jsonl`, `pending_hardening()` counts it, and the `--emit-prompt` probe withholds
the forward route until hardening drains (this dispatch).
**Consistency:** deterministic whenever a same-run concurrent dispatch commits more than
`(budget − this-cycle's-own-commits)` commits into the window.

## Evidence Collected

### Source Code
Symptom serving-path trace (surface → data source, each hop `file:line`; the SEAM-A gate artifact):

```
surface: kind: process-friction {reason: unexpected-commits} appended to lazy-deny-ledger.jsonl
         (→ pending_hardening() counts it → --emit-prompt withholds the forward route)
  → cycle_end_friction_check(): append_friction_ledger_entry when descriptor is not None
                                             user/scripts/lazy_core/markers.py:2357
  → descriptor = detect_cycle_bracket_friction(...)          markers.py:2343
  → signal (b): if chargeable_commits > budget: return {reason: "unexpected-commits", ...}
                                             markers.py:2006
  → chargeable_commits = max(0, commits_since - concurrent_writer_commits)   markers.py:2003
      (else, when the count is None/ambiguous: chargeable_commits = commits_since  markers.py:2005)
  → concurrent_writer_commits = _count_concurrent_writer_commits(root, begin_head_sha,
        current_run_started_at)                              markers.py:2339
  → _count_concurrent_writer_commits: attribute a window sha iff
        (signal 1) email != own_email                        markers.py:2232   ← blind: 1 identity
      OR (signal 2) ledger[sha] is a str AND != current_run_started_at   markers.py:2241  ← blind: same run
                                                             ← DATA SOURCE / gap site
```

**Cause label: `traced`.** The gap site (`_count_concurrent_writer_commits`,
`markers.py:2148-2247`) lies **on** the symptom's serving path — its return value feeds the budget
comparison at `markers.py:2006` that produces the friction descriptor. This is a pure function of
the git log + `user.email` + the concurrent-activity ledger; fully determined by static read, no
runtime coupling. The two attribution arms have NO positive signal for a **same-identity,
same-run-identity** concurrent commit, so the subtraction is a no-op.

### Runtime Evidence
The 2026-07-19 live friction detail (Symptom 2/3) is the runtime manifestation. Further
corroboration: during THIS very investigation the repo HEAD advanced (`4f6b280f → 4f92bd47`) from a
concurrent same-run writer — the regime is live and reproducing.

### Git History
`git config user.email` on this box = `66210812+jacobrocks1212@users.noreply.github.com` (single
identity, no work `includeIf` — workspace `CLAUDE.md`). Recent `claude-config` commits carry no
`Claude-Session:` / `Co-Authored-By:` per-session trailer on cycle-subagent commits, so a
commit-message session-trailer attribution is not available today (same finding as the predecessor
bug). `commit_tally` (the cycle marker's own hook-counted commit count, incremented by
`lazy-cycle-containment.sh:702`) is NOT read by the detector — the window count is the numerator.

### Related Documentation
`user/scripts/CLAUDE.md` → "Per-sub_skill commit budget is DERIVED from skill-declared frontmatter"
+ the `--cycle-end` friction-detector contract; root `CLAUDE.md` `<orchestration>` sanctioned-
concurrent-writers carve-out; the predecessor bug's SPEC ("known limitation" it partially closed).

## Theories

### Theory 1: Both attribution arms are structurally blind to a same-run, same-identity concurrent dispatch — CONFIRMED
- **Hypothesis:** the false friction is produced because `_count_concurrent_writer_commits` attributes
  concurrent commits ONLY by (a) committer-email inequality (this box has ONE identity) or (b) a
  ledger sha under a DIFFERENT run identity (a same-run dispatch shares this run's `started_at`), so a
  same-run concurrent dispatch's commits are attributed 0.
- **Supporting evidence:** the serving-path trace; the detail-string suffix absence (Symptom 3);
  single-identity git config; the interleaved commit history (Symptom 2).
- **Contradicting evidence:** none. The detector's fail-safe (None/ambiguous ⇒ no suppression) is
  intact and correct; the gap is purely the missing positive same-run signal.
- **Status:** Confirmed.

### Theory 2 (RULED OUT): the WU-2 carve-out / ledger arm was never wired into the caller
- **Hypothesis:** `concurrent_writer_commits` is computed as None at the caller.
- **Contradicting evidence:** `cycle_end_friction_check` DOES compute and pass it
  (`markers.py:2339,2353`); the ledger arm IS present (`markers.py:2236-2244`). The wiring is present;
  the attribution *heuristic set* is the gap — no arm covers the same-run case.

## Root Cause

**Class: `missing-contract`.** The concurrent-writer attribution contract covers two writer shapes —
a distinct git identity (signal 1) and a distinct-run-identity ledger entry (signal 2) — but has NO
coverage for the THIRD shape now common on this workstation: a **sanctioned concurrent DISPATCH
within the SAME run** (a background harden lane / a between-cycle reconcile op) that shares both the
git identity AND the live run identity. This is the exact scenario the root `CLAUDE.md`
`<orchestration>` block declares EXPECTED ("an unexpected commit / moved HEAD is expected, not a
defect"), yet the detector charges those commits to the cycle's own budget.

## Recommended Fix Scope — OPERATOR-PARKED (structural + gate-integrity carve-out)

The durable fix forks the friction detector's **core measurement approach** and every candidate
either (a) is partial for the headline background-harden-commit case, or (b) trades the false
positive for a false NEGATIVE that can mask a genuine hook-bypassed runaway (a gate-integrity loss),
or (c) is a broad multi-site instrumentation change. Because the friction is **non-blocking**
(observed-friction background harden — the run continues) there is no interim degradation to justify
a risky/partial provisional pick. Per the `/harden-harness` park-provisional **structural** carve-out
this is HARD-PARKED for the operator — nothing implemented. The options + recommendation are in
`docs/specs/turn-routing-enforcement/NEEDS_INPUT_2026-07-19-process-friction-same-run-concurrent-dispatch-attribution.md`.
