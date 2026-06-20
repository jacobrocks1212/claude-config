# Single-slot marker ownership permits a wrong-session bind to silently disarm a live run's dispatch guard (under-fire) — Investigation Spec

> A run marker's owner is a SINGLE mutable `session_id` slot, stamped first-writer-wins by an allow-time bind. The slot is now well-protected against OVERWRITE (clobber-refused, idempotent re-bind), but it carries NO fencing token and the owning run has NO detect/re-arm path: if the slot is ever stamped with the WRONG session (a pre-allow bind race, or a non-orchestrator allow), the TRUE owner's own dispatches read "owned by someone else → `read_run_marker` returns None → fast-path ALLOW" — silently disarming the guard mid-run with no signal.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/single-slot-marker-ownership-race-disarms-owning-run
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks); SPLIT OUT from `stale-marker-arms-validate-deny-on-unrelated-dispatches` per its Resolved Decision D3=A (the over-fire and under-fire were scoped apart so each gets a dedicated investigation + deterministic fixture).
**Origin (REVERSE-REFERENCE — D3=A spin-off):** `docs/bugs/_archive/stale-marker-arms-validate-deny-on-unrelated-dispatches/` — this bug is the SPLIT-OUT under-fire half. The origin's SPEC `## Resolved Decisions` D3 and its `PHASES.md` Cross-feature Integration Notes name this spin-off; this SPEC names that origin. The origin fixed the over-fire (D1 session-blind gate + D2 no pipeline discriminator); this bug owns the residual single-slot ownership race ONLY.
**Related:** `user/scripts/lazy_core.py` (`read_run_marker` staleness path B ~7887-7981, `bind_marker_session` ~8010-8051, `write_run_marker` ~7783-7884, `refuse_run_start_clobber` ~8838+); `user/scripts/lazy_guard.py` (`_bind_marker_on_allow` ~377-401, allow-time bind anchor); `user/scripts/CLAUDE.md` "Per-repo keyed state dir" + "Same-repo refusal / cross-repo concurrency"; `docs/bugs/_archive/concurrent-same-branch-walkers-no-arbitration/` (checkpoint-discriminated same-pipeline clobber refusal); `docs/features/multi-repo-concurrent-runs/` (per-repo keying — closed cross-repo, not this same-repo ownership race)

---

## Verified Symptoms

1. **[OBSERVED in logs]** A second session's marker silently DISARMED a live run's dispatch guard (fast-path allow, lost counters) — session `2899da98` @ `2026-06-12T15:01:49`: "a real design flaw that this conversation triggered against your live run… from ~8:53 it is silently unenforced — the guard fast-paths every dispatch (no marker → allow), probe registration stops, counters are lost."
2. **[OBSERVED in logs]** The disarm is driven by marker OWNERSHIP mismatch, not absence — session `2899da98` @ `2026-06-12T19:34:57`: "Your batch run's dispatch guard is silently disarmed — its hooks pass its session id, see a marker owned by someone else, and fast-path allow."

> Both symptoms predate the `_bind_marker_on_allow` allow-time bind anchor (Phase 9 WU-9.2) and the checkpoint-discriminated clobber refusal — see "Proven Findings" for what those landed defenses already close and the narrow residual they leave.

## Reproduction Steps

The disarm requires the marker's single `session_id` slot to be stamped with a session OTHER than the true orchestrator owner, while the run is still live. Two residual paths reach that state:

**Repro A — pre-allow bind race (the historical 2026-06-12 ~19:33Z incident):**
1. Orchestrator's `/lazy-batch` writes a marker with `session_id: None` (bind-pending) via `--run-start`.
2. BEFORE the orchestrator's first guard ALLOW binds it, a concurrent NON-owner session (interactive operator in the same repo) reaches a code path that calls `bind_marker_session(session_B)` on the unbound marker (e.g. the pre-WU-9.2 inject-time bind, or any future bind call not gated on an allow).
3. The slot is now stamped `session_B ≠ owner`. The orchestrator's subsequent dispatches pass `session_id=owner`; `read_run_marker` path B sees `owner ≠ session_B` → returns `None` → guard fast-path ALLOWS every cycle. Probe registration stops, counters freeze, enforcement is OFF with no signal.

**Repro B — post-checkpoint-resume re-bind window:**
1. A live run checkpoints (`--run-end --reason checkpoint`) and later resumes (`--run-start` consumes the checkpoint).
2. `write_run_marker` on resume re-writes the marker with `session_id: None` (bind-pending again — confirmed at `lazy-state.py` ~7540-7570: the resume path calls `write_run_marker` then `restore_checkpoint_counters`, but never re-stamps the prior owner's session).
3. The run re-enters the same unbound pre-bind window as Repro A; a wrong-session bind in that window disarms the resumed run identically.

**Expected:** a live run's guard stays armed for its own owning session regardless of concurrent sessions; a foreign session is invisible to it but cannot stamp itself as owner, and the true owner can DETECT a wrong stamp and re-arm rather than silently fast-path-allowing.
**Actual:** under a wrong-session bind the owning run's guard silently fast-paths allow — enforcement is off mid-run with no signal, no detection, no re-arm.
**Consistency:** intermittent — depends on the timing of a competing session's bind versus the orchestrator's first allow-time bind. The window is NARROW post-WU-9.2 (only an orchestrator ALLOW binds in the normal path) but is NOT closed: any pre-allow bind call, plus the resume re-bind window, still reaches it. A deterministic fixture (injected bind ordering) is part of this bug's deliverable, per D3.

## Evidence Collected

### Source Code

**Marker ownership is a single mutable slot, but OVERWRITE is now well-defended.** `bind_marker_session` (`lazy_core.py` ~8010-8051) is first-writer-wins + idempotent: it reads the marker (via `read_run_marker()` with NO session_id, so path B is disabled), and stamps the slot ONLY when `marker.get("session_id") is None`. Once bound, it is a no-op — so a CORRECTLY-bound marker cannot be re-stamped by a later `bind_marker_session` call. This is stronger than the original stub's "single mutable slot → trivially overwritable" framing.

**The remaining hole is the UNBOUND→wrong-bind transition, not a rebind.** The slot's protection is "first writer wins." If the first writer is the WRONG session (a non-orchestrator session that reaches `bind_marker_session` while the marker is bind-pending), it wins permanently for that run. Three layers narrow but do not close this:
- **Allow-time bind anchor** (`lazy_guard.py::_bind_marker_on_allow` ~377-401, Phase 9 WU-9.2): only an ALLOW binds, and only the orchestrator produces an ALLOW (an allow needs a registry hit, which only script-emitted prompts produce). This makes the NORMAL bind path unforgeable by a bystander. But it is a CONVENTION enforced by call-site discipline, not by the slot itself — any other code path that calls `bind_marker_session` (or a future one) bypasses it.
- **Non-destructive path B** (`read_run_marker` ~7968-7981): a non-owner read returns `None` WITHOUT deleting (Phase 8 WU-8.1). This protects the owner's marker from a bystander's READ, but is exactly the mechanism that SILENTLY DISARMS the true owner once the slot holds the wrong session — the owner reads its own marker as "not mine."
- **Clobber refusal** (`refuse_run_start_clobber` ~8838+): refuses a second `--run-start` overwriting a live marker — different-pipeline ALWAYS, same-pipeline UNLESS a checkpoint is waiting (`concurrent-same-branch-walkers-no-arbitration`). This closes the `--run-start` OVERWRITE vector entirely. It does NOT touch the in-marker `session_id` bind vector — a wrong bind happens to an already-written marker, never via a second `--run-start`.

**No fencing token / no detection / no re-arm.** Unlike `lazy_coord.py`'s lease machinery (which carries a `term_token` fencing token incremented per claim, with `verify_fencing` called before every transition), the run marker's `session_id` is a bare slot with no monotonic fence and no owner-side verification. There is no path by which the orchestrator, on reading `None` from its OWN session, distinguishes "no run is live" (correct fast-path allow) from "my run is live but the slot was stamped wrong" (silent disarm). The two are indistinguishable at the read, which is why the disarm is SILENT.

**The resume re-bind window is real.** `lazy-state.py` `--run-start` (~7540-7570) calls `write_run_marker` (which writes `session_id: None`) then `consume_run_checkpoint` + `restore_checkpoint_counters` (which restore the paused COUNTERS but never re-stamp the prior owner's `session_id`). So a checkpoint-resume re-opens the bind-pending window for the resumed run.

### Git History

The origin bug (`stale-marker-arms-validate-deny-on-unrelated-dispatches`, fix commit `4414f1b`, 2026-06-19) fixed the over-fire (D1 owner-scoped gate + D2 pre-bind no-debt deny) and SPLIT this under-fire out per D3=A. The allow-time bind anchor (Phase 9 WU-9.2) and the checkpoint-discriminated clobber refusal (`concurrent-same-branch-walkers-no-arbitration`, 2026-06-20) landed between the 2026-06-12 incident and this investigation — they substantially narrowed the race surface, which is why this bug is P2 (residual, partially mitigated) and not P1.

### Related Documentation

- `user/scripts/CLAUDE.md` → "Owner-scoping (D1)" + "Pre-bind no-debt deny (D2)": the over-fire fix. D1 makes the GATE owner-scoped (a non-owner dispatch fast-path-allows); D2 makes a pre-bind deny carry no debt. Neither addresses the under-fire — they make a non-owner's dispatch HARMLESS, but do nothing about a wrong-session BIND that disarms the true owner.
- `user/scripts/CLAUDE.md` → "Concurrency plane (Phase 4 — `lazy_coord.py`)": documents the `term_token` fencing-token + `verify_fencing` pattern — the in-codebase precedent for a fencing/detection model that the run marker lacks. Candidate reuse target for the fix.

## Theories

### Theory 1: A wrong-session bind in the unbound pre-bind window disarms the true owner (CONFIRMED)
- **Hypothesis:** The slot is first-writer-wins; if a non-owner session stamps it before the orchestrator's allow-time bind, the orchestrator's own reads return `None` (path B) → silent fast-path allow for the rest of the run.
- **Supporting evidence:** Symptom 2 log ("a marker owned by someone else… fast-path allow"); `bind_marker_session` first-writer-wins (~8010-8051); `read_run_marker` path B returns None on mismatch (~7977-7979); `_bind_marker_on_allow` exists specifically to narrow this (~377-401, its docstring names the "live incident 2026-06-12 ~19:33Z").
- **Contradicting evidence:** WU-9.2's allow-time bind means the NORMAL path only binds on an orchestrator allow, so the window is narrow. But it is convention-enforced, not slot-enforced, and the resume re-bind window (Repro B) re-opens it.
- **Status:** Confirmed (residual, partially mitigated).

### Theory 2: A marker OVERWRITE (`--run-start` clobber) can rebind to a wrong session (RULED OUT as a live vector)
- **Hypothesis (from the stub):** the `--run-start` clobber path can stamp a different session, disarming the owner.
- **Supporting evidence:** the stub carried this from the origin record.
- **Contradicting evidence:** `refuse_run_start_clobber` (~8838+) now refuses a second `--run-start` that would overwrite a live, age-fresh marker — different-pipeline always, same-pipeline unless a checkpoint waits. A clobber cannot silently overwrite a live owner's marker. The OVERWRITE vector is closed; only the in-marker BIND vector (Theory 1) remains.
- **Status:** Ruled out as a live vector (closed by `concurrent-same-branch-walkers-no-arbitration`). Retained as documentation of why the remaining surface is bind-only.

## Proven Findings

1. **Root cause:** Run-marker ownership is a single `session_id` slot protected ONLY by "first-writer-wins + idempotent + allow-time-bind convention." It has **no fencing token, no owner-side verification, and no detect/re-arm path**. When the slot is stamped with the wrong session (a pre-allow bind by a non-orchestrator caller, or a wrong bind in the post-checkpoint-resume re-bind window), the true owner's `read_run_marker(session_id=owner)` returns `None` via path B — indistinguishable from "no run is live" — so the guard silently fast-path-allows for the rest of the run. The disarm is SILENT because the owner cannot tell "no marker" from "marker stamped wrong."

2. **The overwrite vector is already closed; the residual is bind-only.** `refuse_run_start_clobber` (different- and same-pipeline, checkpoint-discriminated) closes the `--run-start` clobber path. The only remaining vector is a wrong `bind_marker_session` stamp on an unbound marker (Theory 1, Repro A/B). Any fix must target the BIND, not the overwrite.

3. **`lazy_coord.py`'s fencing-token model is the in-codebase precedent for the fix.** The concurrency plane already solves "a zombie writer must not corrupt shared state" with a monotonic `term_token` + a `verify_fencing` check before every transition. The run marker has no analog. The two ownership models are deliberately separate today (marker = session identity; lease = worktree claim), so reuse is by PATTERN, not by sharing the lease store.

4. **The fix needs three independent capabilities, none of which exist yet** (the load-bearing design decisions, deferred to `/plan-bug`): (a) make the bind UNFORGEABLE by a non-owner — bind only from the owning orchestrator, structurally not by convention (e.g. a bind that requires proof of orchestrator identity, or a `--run-start`-time bind to the orchestrator's known session_id rather than bind-pending); (b) give the owner a DETECT path — distinguish "no marker" from "marker stamped with a different session while MY run is live" (a fencing token or an owner-recorded expected-session the orchestrator can check against the slot); (c) give the owner a RE-ARM path — on detecting a wrong stamp, re-claim the slot rather than silently fast-path-allowing. Plus a deterministic fixture (injected bind ordering / forced wrong-bind) that drives Repro A and B without a real race.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Marker bind (forgeability) | `user/scripts/lazy_core.py` (`bind_marker_session` ~8010-8051); `user/scripts/lazy_guard.py` (`_bind_marker_on_allow` ~377-401) | Bind is convention-gated to allow-time, not structurally restricted to the owner. A non-allow bind path stamps the wrong session permanently for the run. |
| Owner-side read (silent disarm) | `user/scripts/lazy_core.py` (`read_run_marker` path B ~7968-7981) | A wrong-stamped slot makes the OWNER read `None`, indistinguishable from "no run" — the silent-disarm mechanism. No detect/re-arm hook here. |
| Marker schema (no fence) | `user/scripts/lazy_core.py` (`write_run_marker` ~7783-7884) | The marker carries `session_id` but no fencing token / no owner-expected-session field. No structural anchor for a detect/re-arm fix. |
| Resume re-bind window | `user/scripts/lazy-state.py` `--run-start` (~7540-7570); mirror in `bug-state.py` | Checkpoint-resume re-writes `session_id: None`, re-opening the bind-pending window for the resumed run. |
| Regression net | `user/scripts/test_lazy_core.py`, `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py` | New DETERMINISTIC fixtures: a wrong-session pre-allow bind must NOT permanently disarm the owner; the owner must detect + re-arm; the resume re-bind window must be covered; existing path-B non-destructive + clobber-refusal fixtures stay green. Any marker-schema/bind change is a coupled-pair edit (audited by `lazy_parity_audit.py`). |

## Open Questions (for `/plan-bug` — design forks, NOT blocking the conclusion)

These are the load-bearing design decisions named in Proven Finding #4. They are **scope/mechanism choices** (the END-STATE behavior is the same: a live run's guard stays armed for its owner and cannot be silently disarmed by a wrong bind), so they are resolved IN-PLANNING per the completeness-first policy, not via NEEDS_INPUT:

- **Bind-unforgeability mechanism:** bind to the orchestrator's known session at `--run-start` (eliminating the bind-pending window entirely) vs. keep allow-time bind but add a fencing token the owner verifies. (Tradeoff: `--run-start`-time bind requires the orchestrator's session_id to be known at run-start — is it? The inject hook currently supplies it. `/plan-bug` must confirm whether `--run-start` has the orchestrator session_id available.)
- **Detect/re-arm shape:** a `term_token`-style fence on the marker (reusing the `lazy_coord.py` pattern) vs. an owner-recorded expected-session the orchestrator re-asserts. Both give the owner a way to tell "no run" from "wrong-stamped run."
- **Resume re-bind handling:** re-stamp the prior owner's session on a checkpoint-resume `--run-start` (closing Repro B at the resume site) vs. let the general bind-unforgeability fix cover it.
- **Deterministic fixture design:** injected bind ordering (a test hook forcing a wrong-session `bind_marker_session` before the owner's allow) to drive Repro A + B without a real timing race.
