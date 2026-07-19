---
kind: bug-investigation
bug_id: adhoc-decision-key-relative-absolute-mismatch
severity: P2
discovered: 2026-07-18
status: Concluded
written_by: harden-harness
---

# Decision-record sentinel key fails to reconcile relative vs absolute paths

**Status:** Concluded

**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage, Round 99);
`lazy_core/ledgers.py` decision-record ledger (`--record-decision` / `--emit-dispatch
apply-resolution`); origin — observed live during the
`concurrent-worktree-agent-coordination` `/lazy-batch` run, 2026-07-18.

## Symptom (verified)

`lazy-state.py --emit-dispatch apply-resolution` refuses with `dispatch_prompt_refused:
"no recorded decision for sentinel <path> — record the operator's answer first: …"`
even though `--record-decision --sentinel <same-file>` was run for that sentinel earlier
in the same cycle. The refusal forces the orchestrator to guess the sentinel path form
(relative vs absolute) and re-issue the emit, burning a corrective round-trip.

## Reproduction Steps

1. `lazy-state.py --record-decision --sentinel docs/features/<f>/NEEDS_INPUT.md --chosen "…"`
   (orchestrator passes a **repo-relative** sentinel path).
2. `lazy-state.py --emit-dispatch apply-resolution --context '{"sentinel_path":
   "C:\\…\\docs\\features\\<f>\\NEEDS_INPUT.md", …}'` (the emit context carries the
   **absolute** Windows path).
3. The emit refuses `no recorded decision for sentinel` — the two invocations agree on
   the file but disagree on the dict key.

## Root cause (proven) — script-defect

Both writer (`record_decision`) and reader (`read_decision_record`, via
`bind_decision_record_context`) derive their dict key through the SAME shared helper
`lazy_core.ledgers._normalize_sentinel_key`. That helper normalizes with
`os.path.normpath(str(path)).replace("\\", "/")` — which collapses separators and
`.`/`..` segments but does **not** absolutize. So:

- relative record key: `docs/features/<f>/NEEDS_INPUT.md`
- absolute lookup key: `C:/…/docs/features/<f>/NEEDS_INPUT.md`

are different keys → the lookup misses. The helper's own docstring **falsely claims**
"the SAME sentinel recorded and looked up via slightly different path spellings (relative
vs absolute …) still round-trips" — the promise was never delivered because a pure-string
`normpath` cannot reconcile a relative spelling with an absolute one without joining a
base. (The dispatch's framing — "record keys on the raw string while emit normalizes" —
is imprecise: both sides normalize identically; the shared normalizer is simply too weak.)

## Fix scope

Strengthen `_normalize_sentinel_key` to **absolutize** the path (`os.path.abspath`, which
also applies `normpath`) before the forward-slash normalization. Both `--record-decision`
and `--emit-dispatch apply-resolution` are invoked by the orchestrator from the run's
repo-root cwd, so `os.path.abspath` deterministically reconciles a relative record with an
absolute lookup (and vice versa). Do NOT use `os.path.realpath` — a sentinel lives in the
repo working tree, never behind a `~/.claude/*` skill symlink, so symlink resolution is
unneeded and abspath is the smaller, more predictable change. Same-spelling round-trip
(the existing behavior) is preserved: abspath is idempotent on an already-absolute path
and deterministic on a relative one from a fixed cwd.

Regression test: record with a relative sentinel, look up with its abspath form (and the
reverse), asserting a hit — red on `normpath`, green on `abspath`.
