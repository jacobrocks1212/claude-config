---
kind: needs-input
feature_id: decision-2-6-uncovered-row-reroute-to-mcp-test
written_by: spec-phases
decisions:
  - Where does the per-row host-defer recognizer live — land it in THIS bug, dep on the sibling, or ship without it
date: 2026-07-19
next_skill: plan-bug
class: product
divergence: structural
---

# /spec-phases --batch — Needs Input

## Decision Context

### 1. Where does the per-row host-defer recognizer live — land it in THIS bug, dep on the sibling, or ship without it

**Problem:** This bug inserts a SHARED predicate immediately before the unconditional
`__mark_complete__` dispatch at `user/scripts/lazy-state.py:4087` (verified on disk). The
operator-LOCKED fix shape (SPEC "Proven Findings → Fix shape") makes the predicate route to
`mcp-test` when a non-Superseded phase has an unchecked runtime-verification row that is
**(a)** NOT observation-gap-exempt, **(b)** NOT host-deferred (`<!-- requires-host: <cap> -->`),
and **(c)** not covered by recorded evidence. Clauses (a) and (c) are satisfiable today —
`observation_gap_promotable` (`gates.py:608`) and `autotick_verification_rows` (`gates.py:781`)
both exist. **Clause (b) has no implementation:** the `requires_host:` axis exists only at the
FEATURE level (`hostcaps.py` — SPEC frontmatter + `queue.json`); there is NO per-row
`<!-- requires-host: <cap> -->` marker recognizer anywhere in `lazy_core/`. Without clause (b),
a genuinely host-blocked unchecked verification row is treated as "non-host-deferred" and
re-routes to `mcp-test`, which cannot run it on this host — so the fix would INTRODUCE a new
loop on host-blocked rows, and the "termination is load-bearing" contract holds only via
`mcp-test`'s BLOCKED/NEEDS_INPUT safety valve (a hand-deferred halt, not a silent host-defer).
The SPEC's Open Question ("Sequencing vs. decision 5") explicitly defers this to plan time.
Complicating it: the named sibling bug `feature-operator-host-defer-not-honored-over-validated`
is Concluded-but-unimplemented (only SPEC.md on disk) and is scoped around FEATURE-level defer
being honored over a VALIDATED feature — the per-row marker is turn-routing **decision #5**, not
clearly that sibling's deliverable, so a hard queue dep on it may never be satisfied.

**Options:**
- **Land a minimal per-row host-defer recognizer as a phase of THIS bug (Recommended)** — add a
  small `lazy_core` recognizer for the per-row `<!-- requires-host: <cap> -->` marker (a regex +
  per-row check composed into the shared predicate), so all three clauses of the operator-locked
  fix shape are honored and the fix is self-contained and fully terminating in one cycle. Cost:
  ~1 extra phase; touches host-defer territory that overlaps turn-routing decision #5. Reversible
  (the recognizer is additive and small). Risk: mild scope overlap with the sibling's concern,
  but no fragile cross-bug dependency and no starvation.
- **Declare a hard queue `deps` on the sibling bug and defer clause (b) to it** — keep this bug's
  scope to the re-route only, and add `"deps": ["feature-operator-host-defer-not-honored-over-validated"]`
  so this bug is dep-gated until the sibling lands the recognizer. Cost: this bug is HELD (cannot
  progress to execute-plan) until the sibling is implemented; the sibling is Concluded-unimplemented
  and its scope may not actually cover the per-row marker, risking indefinite starvation
  (fail-fast to `BLOCKED.md` `unknown-dependency` if the dep never completes).
- **Ship the re-route now WITHOUT clause (b), relying on mcp-test's BLOCKED safety valve** — drop
  clause (b) from the predicate (every row treated as non-host-deferred); host-blocked rows re-route
  to `mcp-test`, which writes BLOCKED/NEEDS_INPUT (the operator defers by hand) instead of a silent
  host-defer. Ships the two actual symptom fixes (oscillation + stranded coverage — both involve
  testable-HERE rows) immediately. Cost: CONFLICTS with the operator-locked fix shape (clause (b)
  is explicit), and degrades host-blocked-row features from silent-defer to a manual BLOCKED halt.

**Recommendation:** Land a minimal per-row host-defer recognizer as a phase of THIS bug — it is
the only option that honors the full operator-locked fix shape and terminates completely in one
cycle, without a fragile dep on a sibling whose scope may not deliver the marker; the recognizer
is small and additive, so the scope overlap is minor and reversible.
