# Process-friction unexpected-commits detector counts concurrent same-identity session commits — Investigation Spec

> `detect_cycle_bracket_friction`'s unexpected-commits signal subtracts a concurrent-writer
> commit count that is attributed by committer-EMAIL only, so a second session sharing this box's
> single git identity is invisible — its commits inflate the count and trip a FALSE
> unexpected-commits process-friction (self-announcing hardening debt that withholds the forward route).

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/adhoc-process-friction-detector-counts-concurrent-session-commits
**Related:**
- `docs/bugs/_archive/gate-scope-folds-concurrent-harden-commits` — sibling concurrent-commit blind spot in `harness-gate` scope (adjacent, already fixed).
- `concurrent-worktree-agent-coordination` (SPEC Requirement 2 / WU-2) — introduced the `concurrent_writer_commits` carve-out this bug extends; its email-only attribution is the limitation being closed.
- Root `CLAUDE.md` `<orchestration>` "sanctioned concurrent writers" carve-out — the policy the detector must honor.

<!-- Status lifecycle: Concluded → root cause traced; ready for /plan-bug. -->

---

## Verified Symptoms

1. **[VERIFIED]** For a `--cycle-end` bracket whose `begin_head_sha..HEAD` window includes commits
   made by a *concurrent second session on this machine* under the **same configured git identity**
   (`user.email`), those commits are counted in `commits_since` but attributed 0 to
   `concurrent_writer_commits`, so they fully charge against the cycle's per-`sub_skill` budget and
   trip `reason: unexpected-commits`. — Confirmed by reading the serving code
   (`_count_concurrent_writer_commits` at `user/scripts/lazy_core/markers.py:2132` counts only
   `email != own_email`) AND the in-code documented "known limitation" (`markers.py:2093-2102`),
   which names this exact scenario.
2. **[REPORTED]** Live case 2026-07-18: an `/execute-plan` part-1 cycle for `shared-hook-lib` logged
   `30 commits since --cycle-begin (budget=8)`; 28 were the operator's concurrent interactive session
   marking-fixed + archiving 28 Concluded/Superseded/Won't-fix bugs (`provenance:
   operator-directed-interactive`). — Source: `ADHOC_BRIEF.md`; origin `/lazy-batch` run 2026-07-18.

## Reproduction Steps

1. Start a `/lazy-batch` (or `/lazy-bug-batch`) run in `claude-config`; let a cycle `--cycle-begin`
   snapshot `begin_head_sha` on `main`.
2. In a SECOND session on the same machine (same `git config user.email`), commit ≥ (budget+1) commits
   to `main` during the first cycle's window — e.g. run `bug-state.py --repo-root . --archive-fixed
   docs/bugs/<slug>` repeatedly (each makes one commit under the shared identity).
3. Let the first cycle reach `--cycle-end`.

**Expected:** the concurrent second session's same-identity commits are attributed to the concurrent
writer and NOT charged against this cycle's budget; no `unexpected-commits` friction is logged.
**Actual:** `_count_concurrent_writer_commits` returns 0 (all committer emails equal `own_email`), so
`chargeable_commits == commits_since`; `chargeable_commits > budget` trips
`reason: unexpected-commits`, a `kind: process-friction` entry is appended to
`lazy-deny-ledger.jsonl`, `pending_hardening()` counts it, and the `--emit-prompt` probe withholds the
forward route until hardening drains.
**Consistency:** deterministic whenever a same-identity concurrent session commits more than
(budget − this-cycle's-own-commits) commits into the window.

## Evidence Collected

### Source Code
Symptom serving-path trace (surface → data source, each hop `file:line`; the SEAM-A root-cause gate
artifact):

```
surface: kind: process-friction {reason: unexpected-commits} appended to lazy-deny-ledger.jsonl
         (→ pending_hardening() counts it → --emit-prompt withholds the forward route)
  → cycle_end_friction_check(): append_friction_ledger_entry when descriptor is not None
                                             user/scripts/lazy_core/markers.py:2242
  → descriptor = detect_cycle_bracket_friction(...)          markers.py:2228
  → signal (b): if chargeable_commits > budget: return {reason: "unexpected-commits", ...}
                                             markers.py:1935
  → chargeable_commits = max(0, commits_since - concurrent_writer_commits)   markers.py:1932
      (else, when the count is None/ambiguous: chargeable_commits = commits_since   markers.py:1934)
  → concurrent_writer_commits = _count_concurrent_writer_commits(root, begin_head_sha)
                                             markers.py:2226
  → _count_concurrent_writer_commits: return sum(1 for email in emails if email != own_email)
                                             markers.py:2132   ← DATA SOURCE / fix site
```

**Cause label: `traced`.** The fix site (`_count_concurrent_writer_commits`, `markers.py:2077-2134`)
lies **on** the symptom's serving path — its return value is read at `markers.py:1932` and feeds the
budget comparison at `markers.py:1935` that produces the friction descriptor. The email-only
attribution (`email != own_email`) is affirmative evidence a commit came from a distinct identity; it
has NO positive signal for a *same-identity* concurrent writer, so it returns 0 and the subtraction is
a no-op. This is not runtime-coupled — it is a pure function of the git log + `user.email`, fully
determined by static read.

### Runtime Evidence
The 2026-07-18 live friction detail (`30 commits since --cycle-begin ... budget=8`) is the runtime
manifestation; not independently re-collected this cycle (the code read is dispositive for a pure
function). No session-log trawl was needed.

### Git History
Recent `claude-config` commits (`git log -6 --format=%b`) carry **no** `Claude-Session:` /
`Co-Authored-By:` trailer — cycle-subagent commits are authored with the bare repo identity and no
per-session marker. This forecloses a commit-message session-trailer attribution as a fix path (the
discriminating trailer is simply not present on harness commits today).

### Related Documentation
`user/scripts/CLAUDE.md` → "Per-sub_skill commit budget is DERIVED from skill-declared frontmatter"
and the `--cycle-end` friction-detector contract; root `CLAUDE.md` `<orchestration>` sanctioned-
concurrent-writers carve-out. `bug-state.py --archive-fixed` is a script-owned single-commit mover
(`docs/bugs/CLAUDE.md`) — the exact commit site that produced the 28 concurrent commits.

## Theories

### Theory 1: Email-only concurrent-writer attribution is blind to same-identity sessions — CONFIRMED
- **Hypothesis:** the false friction is produced solely because `_count_concurrent_writer_commits`
  attributes concurrent commits by committer-email inequality, and this box has ONE git identity, so a
  second local session's commits are attributed 0.
- **Supporting evidence:** the serving-path trace above; the in-code documented known-limitation
  (`markers.py:2093-2102`) describing this exact case; single-identity git config on this box
  (workspace `CLAUDE.md`: `user.email = 66210812+jacobrocks1212@...`, no work `includeIf`).
- **Contradicting evidence:** none. The detector's fail-safe (None/ambiguous ⇒ no suppression) is
  intact and correct; the gap is purely the missing positive same-identity signal.
- **Status:** Confirmed.

### Theory 2 (RULED OUT): the WU-2 carve-out was never wired into the caller
- **Hypothesis:** the `concurrent_writer_commits` param exists on the detector but the caller passes None.
- **Contradicting evidence:** `cycle_end_friction_check` DOES compute and pass it
  (`markers.py:2226,2238`). The wiring is present; the attribution *heuristic* is the gap.
- **Status:** Ruled Out.

## Proven Findings

- **Root cause (traced):** `_count_concurrent_writer_commits` has no positive signal for a
  same-identity concurrent writer, so same-identity concurrent commits contribute 0 to the subtraction
  and charge fully against the cycle budget → false `unexpected-commits`. Fix site is on the serving
  path (`markers.py:2077-2134`).
- **Fail-safe invariant that any fix MUST preserve:** an unknown/ambiguous attribution must NEVER
  suppress a genuine runaway (the detector already honors this — `None` ⇒ raw comparison). A fix must
  only ADD positive same-identity attribution; it must not turn ambiguity into suppression.
- **A commit-message session trailer is NOT available** (harness commits carry none today), so the
  discriminator must come from harness-owned state, not commit metadata.

## Candidate Fix Approaches (for /plan-bug — root cause is settled; approach is planning scope)

Enumerated so `/plan-bug` (Step 0.4 findings gate) can select scope. **Recommended: Approach B.**

- **Approach B (RECOMMENDED) — subtract script-owned concurrent-mutation commit shas via a ledger.**
  The operator's 28 commits all came through **script-owned** commit sites
  (`bug-state.py --archive-fixed`, `--apply-pseudo __mark_fixed__/__mark_complete__`,
  `--reorder-queue`, provenance writers). Have those sites append their produced commit sha(s) to a
  concurrent-activity ledger in the shared per-repo keyed state dir; `_count_concurrent_writer_commits`
  then ALSO counts window commits whose sha is in that ledger but not authored by THIS cycle. Bounded
  (only script-owned commit sites change), deterministic, no gate-weakening, and catches the exact
  motivating incident. Does not catch a fully-foreign hand-typed `git commit` — but there the fail-safe
  (over-report ⇒ self-announcing friction) is the safe direction.
- **Approach A — positive per-cycle commit marker (nonce trailer).** Stamp each cycle's commits with
  the cycle nonce; this-cycle count = commits carrying the nonce, everything else in the window =
  concurrent. Most robust (catches foreign commits too) but BROAD blast radius: touches every skill's
  commit step and the ATOMIC GATE+COMMIT chains.
- **Approach C — committer-timestamp windowing.** Heuristic; risks false-negatives (a genuine runaway
  within the window is indistinguishable) — violates the fail-safe direction unless combined with a
  positive signal. Not recommended alone.
- **Approach D — make unexpected-commits advisory (non-blocking) on same-identity churn.** Weakens
  runaway detection (a gate-weakening change → operator sign-off per `harness-change-gate.md`). Not
  recommended.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Concurrent-writer attribution | `user/scripts/lazy_core/markers.py` (`_count_concurrent_writer_commits` 2077-2134; consumed by `cycle_end_friction_check` 2226-2238; subtracted in `detect_cycle_bracket_friction` 1922-1935) | The fix site — extend attribution with a positive same-identity signal. |
| Script-owned commit sites (Approach B) | `bug-state.py` / `lazy-state.py` `--archive-fixed`, `--apply-pseudo`, `--reorder-queue`, provenance writers (shared `lazy_core.ledgers`) | Would append produced commit shas to a concurrent-activity ledger. Coupled-pair surface — parity-audited. |
| Tests | `tests/test_lazy_core/test_markers.py` (+ the in-file `--test` harness) | New fixture: same-identity concurrent commits in-window ⇒ no false `unexpected-commits`; genuine runaway still trips; ambiguous ⇒ no suppression (fail-safe). |

## Open Questions

- **Approach selection** (B vs A) is deferred to `/plan-bug` — a genuine product/scope fork (blast
  radius + which concurrent scenarios are caught). Not a root-cause ambiguity; the cause is traced. If
  `/plan-bug` judges the fork operator-gating, it surfaces it at its findings gate.
- Whether the concurrent-activity ledger (Approach B) should also record the *feature* pipeline's
  script-owned mutation commits, or only bug-pipeline archive/mark commits — a scoping detail for planning.
