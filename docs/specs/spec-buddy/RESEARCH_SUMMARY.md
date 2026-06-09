# spec-buddy — Research Summary

> **Research was skipped for this feature.** This file is a stub so downstream planning
> (`/plan-feature`, `/spec-phases`, `/write-plan`) can proceed. No Gemini deep-research pass was run.

## Status

- **Research conducted:** No (`/spec-buddy` skip-research path).
- **Grounding instead of research:** the design is grounded in direct reading of the `/spec` skill,
  its shared `_components/` files, and the `review-pr-buddy` SPEC (the structural template), all
  performed during the originating brainstorm session.

## Key findings relevant to the baseline

- The reuse story is strong: nearly every capability spec-buddy needs already exists as a
  `_components/` file or a `/spec` phase. Net-new is only the partition-walk control flow and the
  confidence-scored check-in format. (See SPEC.md § Reuse Ledger.)
- `review-pr-buddy` establishes the precedent that a "buddy" variant should compose its autonomous
  counterpart's pipeline rather than fork it. spec-buddy follows the same single-source-of-truth
  discipline against `/spec`.

## Ideas adopted from prior art (review-pr-buddy)

- Pre-compute autonomously, then walk the human through the result.
- Persist session state for compaction recovery (`buddy-session.json`).
- Emit a downstream-compatible artifact (`SPEC.md`) so the rest of the pipeline consumes it unchanged.

## Pitfalls / concerns to address

- **Drift between `/spec` and `/spec-buddy`** — mitigated by `!cat`'ing the same `_components/` files
  rather than copying, and delegating the SPEC structure / research / finalize logic to `/spec`.
- **Partition mis-tiering** — mitigated by letting the user edit tiers at the Phase 1 approval gate.

## Baseline decisions to revisit

None — research was skipped, so no findings contradict the baseline. All six brainstorm decisions
stand as written in SPEC.md.
