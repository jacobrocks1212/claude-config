---
kind: deferred
feature_id: block-terminal-kill-matches-separators-inside-quoted-args
written_by: lazy-batch-parallel-orchestrator
date: 2026-07-18
reason: superseded
---

# Operator-Deferred — Superseded SPEC routed to investigation

This SPEC is `**Status:** Superseded` (its failure class was closed by the successor fix
`block-terminal-kill-false-denies-quoted-argument-tokens`, shipped 2026-07-13 — `_mask_quoted`
quote-content masking in `block-terminal-kill.sh`; see the root CLAUDE.md Hooks table), but the
on-disk bug pickup does not exclude `Superseded` SPECs, so the merged head routed it to
`spec-bug` during the 2026-07-18 overnight run. Deferred mechanically under the run's standing
directive so the pipeline does not burn an investigation cycle on a superseded document.

The routing gap itself is tracked as `docs/bugs/adhoc-bug-pickup-routes-superseded-specs/`
(8th exclude-set facet class; generalization: `docs/features/merged-head-actionability-oracle`).
Un-defer by deleting this file if the supersession is ever revisited.
