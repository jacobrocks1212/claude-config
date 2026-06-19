# Single-slot marker ownership permits a foreign/overwriting session to disarm a live run's dispatch guard (under-fire) — Investigation Spec (stub)

> A run marker's owning session is a SINGLE mutable `session_id` slot. A marker overwrite (the `--run-start` clobber path) or a wrong-session bind race can stamp the wrong session, after which the TRUE owner's own dispatches read "owned by someone else → `read_run_marker` returns None → fast-path ALLOW" — silently disarming the guard mid-run. Probe registration stops, counters are lost, enforcement is off with no signal. This is the UNDER-fire dimension, the inverse of the over-fire fixed by the origin bug.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/single-slot-marker-ownership-race-disarms-owning-run
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks); SPLIT OUT from `stale-marker-arms-validate-deny-on-unrelated-dispatches` per its Resolved Decision D3=A (the over-fire and under-fire were scoped apart so each gets a dedicated investigation + deterministic fixture).
**Origin (REVERSE-REFERENCE — D3=A spin-off):** `docs/bugs/stale-marker-arms-validate-deny-on-unrelated-dispatches/` — this bug is the SPLIT-OUT under-fire half. The origin's SPEC `## Resolved Decisions` D3 and its `PHASES.md` Cross-feature Integration Notes name this spin-off; this SPEC names that origin. The origin fixed the over-fire (D1 session-blind gate + D2 no pipeline discriminator); this bug owns the residual single-slot ownership race ONLY.
**Related:** `user/scripts/lazy_core.py` (`read_run_marker` staleness path B, `bind_marker_session`); `user/scripts/lazy_guard.py` (`_bind_marker_on_allow`, Phase 9 WU-9.2 allow-time bind); `user/scripts/CLAUDE.md` "Per-repo keyed state dir" + "Same-repo refusal / cross-repo concurrency" (`refuse_run_start_clobber`); `docs/features/multi-repo-concurrent-runs/` (per-repo keying — closed cross-repo, not this same-repo ownership race)

---

## Verified Symptoms

1. **[OBSERVED in logs]** A second session's marker silently DISARMED a live run's dispatch guard (fast-path allow, lost counters) — session `2899da98` @ `2026-06-12T15:01:49`: "a real design flaw that this conversation triggered against your live run… from ~8:53 it is silently unenforced — the guard fast-paths every dispatch (no marker → allow), probe registration stops, counters are lost."
2. **[OBSERVED in logs]** The disarm is driven by marker OWNERSHIP mismatch, not absence — session `2899da98` @ `2026-06-12T19:34:57`: "Your batch run's dispatch guard is silently disarmed — its hooks pass its session id, see a marker owned by someone else, and fast-path allow."

## Reproduction Steps (from the origin SPEC's under-fire repro — to be confirmed by /spec-bug)

1. Run A's `/lazy-batch` is live in repo R; its marker is bound to `session_A`.
2. A second session B (interactive, same repo) makes a dispatch. The guard reads the marker WITH `session_id=B`; the marker is bound to `session_A ≠ B` → `read_run_marker` returns `None` (staleness path B) → guard fast-path ALLOW (correct for B).
3. The underlying defect: marker ownership is a single `session_id` slot. A marker rebound/overwritten by a competing run, or a marker whose bind raced to the wrong session, leaves run A's OWN dispatches reading "owned by someone else → None → allow" — probe registration stops, counters are lost.

**Expected:** a live run's guard stays armed for its own owning session regardless of concurrent sessions; a foreign session is invisible to it but cannot disarm it.
**Actual:** under a bind race / marker overwrite the owning run's guard silently fast-paths allow — enforcement is off mid-run with no signal.
**Consistency:** intermittent — depends on the timing of a competing session's bind/overwrite versus run A's bind. (The intermittent race is hard to fixture — a deterministic fixture is part of this bug's deliverable, per D3.)

## Evidence Collected (carried from the origin SPEC as the origin record — re-verify in investigation)

- **Marker ownership is a single mutable slot.** `read_run_marker` staleness path B (`lazy_core.py` ~lines 6195-6206) is NON-DESTRUCTIVE and asymmetric by design (Phase 8 WU-8.1, fixing the 2026-06-12 ~14:53Z destructive-disarm). `bind_marker_session` (~lines 6211-6252) stamps the marker's single `session_id` slot once (first-writer-wins, idempotent). `lazy_guard.py::_bind_marker_on_allow` (~lines 377-401) moved the bind anchor to allow-time (Phase 9 WU-9.2) to make ownership unforgeable by a bystander. The residual hole: the slot is still a SINGLE owner; a marker overwrite (`--run-start` clobber path) or an unbound-marker bind race can stamp the wrong session, after which the true owner's own dispatches read "owned by someone else → None → allow."
- **Partial mitigation already exists.** Phase 9 WU-9.2's allow-time bind narrows the race (only an orchestrator ALLOW binds), so the remaining window is the `--run-start` clobber/overwrite case + any pre-allow bind. `refuse_run_start_clobber` (per `user/scripts/CLAUDE.md`) refuses a second `--run-start` against a live, non-stale, DIFFERENT-pipeline marker — but the slot model itself is the residual.

## Why this is friction

When the owning run's guard silently fast-paths allow, validate-deny enforcement is OFF mid-run with no signal — probe registration stops and the run's counters are lost, undermining the whole hardening-debt mechanism the pipeline relies on for honest run-end gating. Unlike the over-fire (which is loud — it accrues debt that gates run-end), the under-fire is SILENT, which makes it more dangerous.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)

- Should marker ownership move from a single mutable `session_id` slot to a model that the true owner cannot be evicted from (e.g. an owner-set, a fencing token like `lazy_coord.py`'s `term_token`, or a first-writer-wins lock that a clobber cannot silently overwrite)?
- Can the `--run-start` clobber path (`refuse_run_start_clobber`) be hardened so an overwrite never rebinds a live owner's marker to a different session, or so the true owner detects the rebind and re-arms rather than fast-path-allowing?
- How does the existing `lazy_coord.py` fencing-token / lease machinery (Phase 4 concurrency plane) relate — is it reusable here, or is the run-marker ownership model deliberately separate?
- How to build a DETERMINISTIC fixture for an intermittent bind/overwrite race (injected clock / forced bind ordering) so the fix carries a real regression net?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence carried from the origin bug only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope for the under-fire. Do not add Theories / Proven Findings / Affected Area / fix scope here — the origin SPEC documents Theory 2 / Proven Finding #2 as its origin record, but THIS bug's investigation must re-confirm them under its own scope.
