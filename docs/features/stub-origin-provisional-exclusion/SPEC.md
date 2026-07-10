# Stub-Origin Provisional Exclusion — Feature Specification

> Special-case stub-origin decisions in the provisional-acceptance tier: a `NEEDS_INPUT.md` whose decisions shaped a BASELINE the operator has never seen (a park-mode stub-spec `/spec` Phase-1 round, or a `/spec-bug` pre-conclusion halt) is marked `stub_origin: true` by its producer and is NEVER provisionally accepted — baseline-gating forks always park for the operator, no matter how low their per-decision divergence grades look.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** no

**Depends on:**

- park-provisional-acceptance — hard — Amends its D8 never-provisional list with the stub-origin class; extends `lazy_core.provisional_eligibility`, the sentinel schema, and the D13 park-mode `/spec` section that feature introduced.

---

## Executive Summary

`park-provisional-acceptance` gates provisional auto-acceptance on a per-decision rework signal: the divergence two-key (`divergence` + `audit_divergence` both low). That signal has a blind spot for **stub-origin decisions** — the baseline-GATING product forks a park-mode stub-spec `/spec` Phase-1 round surfaces (scope of v1, ownership, core UX shape, user-facing defaults), and the analogous `/spec-bug` halt written while an investigation is still `Investigating`. Each such decision can look `isolated`/`contained` in code terms while JOINTLY defining the entire feature's foundation — and, uniquely, the operator has never seen ANY of the surrounding baseline (there was no interactive brainstorm; the whole SPEC was drafted sentinel-mediated). Provisionally accepting them would let an overnight run lock a baseline and build a whole feature on it before the operator has confirmed a single foundational choice — exactly the "significant rework" class the tier exists to prevent.

This feature closes the blind spot with a producer-marked, fail-closed exclusion:

1. **Producer marking (the `/spec` + `/spec-bug` addendum):** a `NEEDS_INPUT.md` written for baseline-gating decisions from a stub-origin baseline carries `stub_origin: true` in its frontmatter — written by `/spec`'s "Phase 1 under `--batch`" halt, by `/spec-bug`'s pre-conclusion (`Status: Investigating`) halt, and mandated by the park-mode stub-spec interaction contract (the D13 cycle-prompt section).
2. **Audit backstop:** the Step 1d.5 input-audit, when the audited cycle was a stub-spec baseline round, verifies the marker and ADDS it if the producer omitted it — the marker is two-key like everything else in this tier (producer + independent audit).
3. **Fail-closed exclusion:** `lazy_core.provisional_eligibility` refuses any sentinel whose `stub_origin` key is present and not explicitly false — such sentinels park for the operator exactly as plain `--park` behaves, and surface at the flush like any other product-class park.

## Technical Design

- `user/scripts/lazy_core.py::provisional_eligibility`: new exclusion after the `written_by: completion-integrity-gate` check — `stub_origin` present and not explicitly falsy (`false`/`no`) → `(False, "stub_origin baseline decision — never provisional (fail-closed)")`. Conservative on malformed values: any unrecognized value excludes.
- `user/skills/_components/sentinel-frontmatter.md`: `stub_origin: true` optional key (producers + audit backstop enumerated); the provisional-acceptance rule's condition list gains item (6); the never-provisional decision-tier summary updated.
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (`park-spec-sentinel-mediation` section, D13): the sentinel written by a park-mode stub-spec `/spec` round MUST carry `stub_origin: true`.
- `user/skills/_components/lazy-batch-prompts/input-audit-prompt.md`: step 7c — stub-origin verification/backstop duty.
- `user/skills/spec/SKILL.md` ("Phase 1 under `--batch`" step 4): the Phase-1 gating-decision sentinel carries `stub_origin: true`.
- `user/skills/spec-bug/SKILL.md` (batch path): a `NEEDS_INPUT.md` written while the investigation has not concluded carries `stub_origin: true`.
- `user/skills/lazy-batch/SKILL.md`: the `--park-provisional` token bullet's never-provisional list names the stub-origin class (the T7 digest-table note already does).
- Fixtures: both state scripts' `--test` harnesses — an otherwise-eligible sentinel (low divergence two-key + recommendation) with `stub_origin: true` PARKS instead of routing `__provisional_accept__`; baselines regenerated through `_normalize_smoke_output`.

## Locked Decisions

Resolved 2026-07-09 under the operator's completeness-first standing policy (autonomous session; flagged for operator review in the session summary).

1. **Exclusion is marker-based and fail-closed, not writer-based.** Keying on `written_by: spec` alone would over-exclude (post-research Phase-3 `/spec` sentinels are NOT stub-origin — the operator locked that baseline) and under-exclude (the input-audit, not `/spec`, may be the writer). The producer states the stub-origin fact; the audit backstops it; the predicate refuses on any present-and-not-explicitly-false value (malformed values exclude — conservative).
2. **Amends park-provisional-acceptance D8.** The never-provisional list becomes: research gates, BLOCKED.md, structural/ungraded divergence, malformed sentinels, gate-written sentinels, two-key-mechanical (better path), **and stub-origin baseline decisions**. The completed `park-provisional-acceptance` SPEC is not edited post-receipt; this SPEC records the amendment (provenance stays honest).
3. **`/spec-bug` pre-conclusion halts are stub-origin.** A bug sentinel written while `**Status:** Investigating` (the investigation did not conclude) is foundation-shaping in the same sense — the root cause the fix would build on is unconfirmed. Post-conclusion `/spec-bug`/planning sentinels are ordinary product-class decisions and stay divergence-governed.
4. **No new probe key or terminal.** A stub-origin park is an ordinary needs-input park (`parked[]`, flush, decision-resume) — the exclusion only removes the provisional shortcut. Zero new state-machine states keeps the blast radius one predicate clause + prose.
5. **Marker is inert outside `--park-provisional`.** Like `divergence`/`audit_divergence`, `stub_origin` is read ONLY by the provisional eligibility predicate; default and plain-`--park` behavior is byte-identical.

## KPI Declaration

Classified `no` for the measurability gate — a correctness rail on an existing tier, not a process-overhead-reduction system with its own KPI surface.

## MCP validation

No MCP-reachable surface (one predicate clause + prose + fixtures). Validation: both state scripts' `--test` harnesses (new stub-origin fixtures), regenerated baselines, `pytest test_lazy_core.py`, `lazy_parity_audit.py` exit 0, projection + skill lint clean.

## Open Questions

- **vN — stub-origin ratification fast-path.** When the operator answers a stub-origin sentinel at the flush, the whole baseline could be presented for one-shot review (baseline diff + decisions together) rather than per-decision questions. Deferred until field data shows stub-origin flushes are frequent.
