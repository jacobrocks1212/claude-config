---
kind: fixed
feature_id: doc-drift-lint-single-event-model-blocks-multi-event-hooks
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated __mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`doc-drift-lint-single-event-model-blocks-multi-event-hooks` marked fixed on 2026-07-12. The
fix itself (the `check_hooks` multi-event parsing branch + its four TDD fixtures + the
`lazy-route-inject.sh` Hooks-table row update) had already landed in commit `1b23a9ba`
("harden(script): validate multi-event hooks in doc-drift-lint check_hooks") ahead of this
bug directory's `PHASES.md`/`FIXED.md` paperwork — this session verified the landed fix against
the SPEC's "Proposed fix scope," authored `PHASES.md` to document it, and confirmed the gates.
This receipt was written by the orchestrating subagent, not the `/lazy-bug` pipeline's
`__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive` (this repo has
no MCP/Tauri app surface for the bug pipeline's `VALIDATED.md`/`RETRO_DONE.md` gate to key on;
`doc-drift-lint.py` is a pure-read script whose acceptance evidence is its own pytest suite).

## Root cause

`check_hooks` modeled each documented hook as registered under exactly ONE event
(`_TRIGGER_RE.search` — a single-clause match — compared via `set(reg_events) != {doc_event}`).
A hook legitimately wired under multiple events (e.g. `lazy-route-inject.sh`: `UserPromptSubmit`
+ `SessionStart (compact)` + `PostCompact`) produced a registered-side set that could never equal
a single-element documented set, so the row was drift by construction with no valid Trigger-cell
spelling — forcing the `doc-drift:deliberate-divergence` escape-hatch marker to mask a real
linter limitation rather than a genuine doc/reality divergence.

## Fix

`check_hooks` now branches on Trigger-cell clause count (`_TRIGGER_RE.findall`): a single clause
takes the byte-identical legacy path; ≥2 clauses parse the full documented `event -> matcher-set`
map and compare it against the full `registered[name]` map (set-equality on the event keys, then
a per-event matcher comparison honoring the existing `*`-matches-all empty-set semantics). The
`lazy-route-inject.sh` row now documents all three real events and the divergence marker was
retired.

## Symptom reproduction (red -> green)

The four multi-event fixtures in `user/scripts/test_doc_drift_lint.py` (`test_hooks_multi_event_*`,
`:406-487`) drive a synthetic `route.sh` hook shaped exactly like the real `lazy-route-inject.sh`
(three events, one with a non-matches-all matcher):

- `test_hooks_multi_event_all_documented_clean` — all three events documented + registered ->
  exit 0, zero drift findings. This is the case that was previously UNREACHABLE without the
  divergence marker; it is now genuinely clean.
- `test_hooks_multi_event_documented_event_not_registered` / `..._registered_event_not_documented`
  — a genuine event-set mismatch still trips exit 1 naming both sides.
- `test_hooks_multi_event_matcher_mismatch` — an aligned event set with a per-event matcher
  mismatch still trips exit 1 naming the offending event.

These fixtures were authored alongside the fix in commit `1b23a9ba` (pre-existing this session);
this session's independent re-verification is the gate evidence below.

## Gates (this session)

- `python -m pytest user/scripts/test_doc_drift_lint.py -q` -> **49 passed** (0 failed). (One
  transient failure was observed mid-session on `test_this_repo_is_clean`, caused by a
  concurrently-running sibling bug — `legacy-tool-input-env-hooks-dead` — mid-edit on the root
  `CLAUDE.md` Hooks table; unrelated to this bug's scope. It cleared once that sibling edit
  landed; the re-run above is the final green state.)
- `python user/scripts/doc-drift-lint.py --repo-root .` -> exit 0 (`5 checks, 0 drift findings,
  2 exempted divergences` — the two exemptions, `block-work-repo-git-writes.sh` and the
  pre-existing `algobooth` manifest entry, are both unrelated to this bug).
- `python user/scripts/lint-skills.py` -> `OK — no broken or embedded !cat patterns found.`

## Files touched (already committed in 1b23a9ba, prior to this session)

- `user/scripts/doc-drift-lint.py` — multi-event `check_hooks` branch.
- `user/scripts/test_doc_drift_lint.py` — four multi-event fixtures.
- `CLAUDE.md` (root) — `lazy-route-inject.sh` Hooks-table row + marker retirement.

## Files authored this session

- `docs/bugs/doc-drift-lint-single-event-model-blocks-multi-event-hooks/PHASES.md`
- `docs/bugs/doc-drift-lint-single-event-model-blocks-multi-event-hooks/SPEC.md` (`**Status:**`
  flipped to `Fixed`)
- `docs/bugs/doc-drift-lint-single-event-model-blocks-multi-event-hooks/FIXED.md` (this file)

No archive step was performed in this session (`bug-state.py --archive-fixed`) — left for the
orchestrator to run, consistent with the `worktree-claude-doc-drift` precedent this receipt is
modeled on.
