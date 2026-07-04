# Operator Paging on Pipeline Halts — Feature Specification

> A `NEEDS_INPUT.md`/`BLOCKED.md` currently sits silently until the operator checks in — a batch run can idle for hours on a decision that takes ten seconds to answer. Wire a notifier into the state scripts' halt paths that pushes the decision (with its options inline) to the operator's phone, ideally answerable from mobile by replying or committing a resolution file.

**Status:** Draft (pre-Gemini)
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

Halts are honest (`NEEDS_INPUT.md`, `BLOCKED.md`) but passive: nothing tells the operator a run is
waiting. The wall-clock cost of a halt is dominated by time-to-notice, not time-to-answer —
especially for overnight/cloud runs steered from a phone.

## Direction (deliberately not locked)

- **Trigger point:** the state scripts' halt writers (single chokepoint, both pipelines) — not
  skill prose.
- **Channel candidates:** ntfy / Pushover / a GitHub issue-or-mention (renders on GitHub mobile,
  composing with `LAZY_QUEUE.md` from `mobile-queue-control`).
- **Payload:** halt kind, item id, the sentinel's option surface, and a deep link to the SPEC dir.
- **Answer path:** at minimum "notice fast, answer in chat as today"; ideally a mobile-committable
  resolution file the pipeline already understands (`NEEDS_INPUT_RESOLVED_*` convention).
- Fail-OPEN: a notification failure must never block or corrupt the halt itself.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: channel choice + secrets handling;
> dedup/re-ping policy for long-lived halts; cloud vs. workstation parity; whether completion/
> run-end events also notify. Solutions above are directional, not locked.
