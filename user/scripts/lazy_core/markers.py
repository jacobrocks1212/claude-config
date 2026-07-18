"""lazy_core.markers — the run-marker / ownership / refusals / cycle-bracket plane.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 5, WU-1) — a move-only refactor with zero behavior change. Owns the
run-marker lifecycle (``write_run_marker`` / ``read_run_marker`` /
``delete_run_marker`` + the born-owner-bound ``bind_marker_session`` /
``marker_owner_status`` / ``reassert_marker_owner`` ownership plane), the
cycle-subagent marker (``write_cycle_marker`` / ``read_cycle_marker`` /
``clear_cycle_marker`` / ``resolve_cycle_worker_nonce``), the C3 refusal
plane (``refuse_if_cycle_active`` / ``refuse_cycle_marker_mutation_if_subagent``
/ ``refuse_run_start_clobber`` + ``CYCLE_REFUSED_OPS`` /
``SANCTIONED_STOP_TERMINAL``), the run-continuity partition
(``RUN_CONTINUITY_FIELDS`` / ``RUN_FRESH_FIELDS``) + checkpoints
(``write_run_checkpoint`` / ``consume_run_checkpoint`` /
``restore_checkpoint_counters``), the budget counters
(``advance_run_counters`` / ``advance_forward_cycle`` / ``fold_run_counters``
+ the per-feature budget guard ``budget_trip_signals`` /
``feature_is_near_complete``), the cycle-bracket friction detector
(``detect_cycle_bracket_friction`` / ``cycle_end_friction_check``), the
loop-detection repeat counters (``update_repeat_counts``), the resolution
signal, and the D2-A audit-obligation marker fields.

This is the single most guard-coupled surface in the package (the hooks shell
``lazy-state.py --marker-*``, which resolves here via the facade) — moved
LAST per SPEC D3, byte-identical behavior mandatory. Write-path move
sanctioned by the two archived bug receipts (SPEC D2 Constraint 3):
docs/bugs/_archive/mark-complete-partial-apply-noop-unrecoverable/FIXED.md and
docs/bugs/_archive/production-sentinel-writes-bypass-atomic-write/FIXED.md.
All writes here go through ``_ctx._atomic_write``.

Deferred function-local imports (this module must not import
``.runtimeplane`` at top level — kept function-local to keep the guard's
marker probe surface light): ``_die`` in ``parse_parent_run_arg``
(``._ctx``), ``_git`` in ``head_sha_snapshot`` / ``current_branch_snapshot``
/ ``_count_authored_commits_since`` and ``_current_head`` in
``update_repeat_counts`` (``.runtimeplane``).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
import tempfile
import time

from pathlib import Path

from ._ctx import _atomic_write, _diag
from .statedir import (
    _MARKER_FILENAME,
    _REGISTRY_FILENAME,
    _load_registry,
    claude_state_dir,
)
from .docmodel import (
    _plan_phase_set,
    remaining_unchecked_are_verification_only,
)
from .gates import _plan_wu_checkbox_counts
from .ledgers import append_friction_ledger_entry, append_telemetry_event
from .dispatch import (
    _CYCLE_COMMIT_BUDGET_DEFAULT,
    _CYCLE_COMMIT_MULTI,
    _CYCLE_COMMIT_NOISE_ALLOWANCE,
    _MULTI_COMMIT_CEILING_OVERRIDE,
    _emit_work_branch,
    consumed_emission_count,
    skill_declares_multi_commit,
    skill_declares_subagent_model,
)


def update_repeat_counts(
    repo_root: Path,
    state: dict,
    *,
    signature_path: Path | None = None,
    pipeline: str = "feature",
    peek: bool = False,
) -> dict:
    """Persist the probe signatures and return BOTH consecutive-repeat counts.

    Two independent counters share ONE per-pipeline state file:

    1. ``repeat_count`` — the Phase-9 dispatch-tuple streak.
       Signature = ``(feature_id, sub_skill, sub_skill_args, current_step)``.
       HEAD-AWARE: identical tuple + a NEW HEAD since the last probe RESETS to 1
       (commits between two identical probes are forward progress, not a stall).

    2. ``step_repeat_count`` — the Phase-10 step-level oscillation counter.
       Signature = ``(feature_id, current_step)`` ONLY (no sub_skill / args).
       NO head-advance reset: its whole purpose is catching
       "productive-looking" oscillation where each spurious cycle commits a file
       (HEAD advances → the dispatch streak resets every iteration) while the
       state machine keeps returning to the SAME step. It increments whenever the
       (feature_id, current_step) pair is unchanged from the prior probe.
       It RESETS to 1 on exactly THREE paths (all "genuine forward progress",
       never a HEAD/commit reset — that immunity is the d8 design constraint):
         (a) the step signature (feature_id, current_step) CHANGES;
         (b) ORDERED-ADVANCE EXEMPTION — step signature unchanged but
             ``sub_skill_args`` advanced (a multi-part /execute-plan sequence);
         (c) RESOLUTION-AWARE RESET — the prior cycle was a needs-input
             RESOLUTION at this exact step signature (the run marker carried a
             one-shot ``last_resolution_step_key`` recorded by
             ``record_resolution_signal``).  A resolution is itself an Agent
             dispatch (it consumes a nonce, defeating the F2 hold), so without
             (c) the counter would survive a legitimately-resolved blocker.
             One-shot + signal-gated: fires once across the resolution, never on
             a missing/legacy/foreign-repo marker.

    The persisted JSON shape is
    ``{"signature": [4], "count": int, "head": str|None,
       "step_signature": [2], "step_count": int, "consume_count": int}``. Legacy
    files (Phase-9 shape, no ``step_*`` keys) are honored: ``step_count`` starts
    at 1 and the new keys are added on the next write — mirroring the ``head``-field
    migration.

    ``consume_count`` (lazy-pipeline-ergonomics Phase 2 / F2, and now also F1 /
    lazy-validation-readiness) is the DOUBLE-PROBE DEBOUNCE oracle and is
    MARKER-GATED: it is written ONLY when a run marker is present
    (``read_run_marker()`` is non-None), recording the registry's consumed-entry
    count (``consumed_emission_count``) at the time of the probe.  On the next
    probe, when (a) a marker is present, (b) the relevant signature is unchanged,
    AND (c) the prior file recorded a ``consume_count`` that equals the current
    consumed-count → NO dispatch landed between the two probes (the guard consumes
    a nonce on every ALLOW), so the second probe is a RE-READ.  Both ``count``
    (F1: same-tuple same-HEAD branch) and ``step_count`` (F2) are HELD instead of
    incremented.  This stops an inspection-probe-then-dispatch-probe pair from
    inflating either counter and tripping a false LOOP DETECTED. A genuine
    oscillation still trips because
    a real dispatch (hence a consume) lands between its repeats. The key is
    legacy-tolerant exactly like ``head`` / ``step_*``: a file with no
    ``consume_count`` cannot prove a re-read, so ``step_count`` behaves as before
    (increments). When NO marker is present the key is never written and the
    debounce is inert — the no-marker path stays byte-identical (``--test``
    baselines unchanged). HEAD-blindness is preserved: the debounce keys on
    DISPATCH occurrence, never on commits — no HEAD reset is added to
    ``step_count``.

    Any missing file, OS error, or corrupt/invalid JSON is silently treated as
    «no prior» — the function never raises on a bad state file.

    ``peek`` (mirrors Phase-9 semantics): when True, compute and RETURN both
    would-be counts WITHOUT any mutation — the state file is neither created nor
    rewritten, so neither counter advances. Diagnostic / inspection probes use
    peek so only the single dispatch-bound probe advances the streaks.

    ``head`` is the repo_root's current HEAD sha (via ``_current_head``), or
    None when repo_root is not a git repo.

    Default ``signature_path`` (when None):
        feature pipeline: ``<tempdir>/lazy-state-last-<sha1_of_repo_root[:16]>.json``
        bug pipeline:     ``<tempdir>/bug-state-last-<sha1_of_repo_root[:16]>.json``
    This keeps the state file outside the repo tree — it is never committed
    and never triggers gitignore concerns. The per-``pipeline`` filename keeps
    the feature and bug resolvers from sharing one signature file (interleaved
    parallel /lazy-batch + /lazy-bug-batch probes would otherwise reset each
    other's streaks, defeating mechanical loop detection).

    Returns ``{"repeat_count": int >= 1, "step_repeat_count": int >= 1}``.
    """
    # --- Derive default path from a stable hash of the resolved repo root ----
    # The hash keeps per-repo state separate even when multiple repos live on
    # the same machine, while keeping the filename deterministic across runs.
    from .runtimeplane import _current_head  # deferred (runtime/git plane; function-local avoids import cycle)
    if signature_path is None:
        repo_hash = hashlib.sha1(
            str(repo_root.resolve()).encode("utf-8")
        ).hexdigest()[:16]
        # "feature" keeps the historical filename so existing state files
        # carry over; any other pipeline gets its own namespaced file.
        prefix = "lazy-state-last" if pipeline == "feature" else f"{pipeline}-state-last"
        signature_path = Path(tempfile.gettempdir()) / f"{prefix}-{repo_hash}.json"

    # --- Build the new signatures from the current state ---------------------
    # Dispatch tuple (Phase-9): full routing identity.
    new_sig = (
        state.get("feature_id"),
        state.get("sub_skill"),
        state.get("sub_skill_args"),
        state.get("current_step"),
    )
    # Step signature (Phase-10): feature_id + current_step ONLY. Deliberately
    # excludes sub_skill / sub_skill_args so oscillation that re-routes the SAME
    # step through different skills/args (the d8 write-plan loop) still counts.
    new_step_sig = (
        state.get("feature_id"),
        state.get("current_step"),
    )

    # --- Resolve the repo's current HEAD (None when not a git repo) ----------
    current_head = _current_head(repo_root)

    # --- Read the persisted prior signatures (fail-safe) ---------------------
    prior_count = 0
    prior_sig_list: list | None = None
    # Sentinel distinguishing "no `head` key at all" (legacy file) from an
    # explicit ``"head": null`` (a non-git repo wrote it under the new shape).
    _MISSING = object()
    prior_head: object = _MISSING
    prior_step_count = 0
    prior_step_sig_list: list | None = None
    # F2 debounce oracle: the consumed-emission count recorded by the prior
    # MARKED probe. _MISSING distinguishes "no consume_count key" (legacy file,
    # or an unmarked prior write) from a recorded count — only a recorded prior
    # count can prove a re-read, so a legacy/unmarked prior never debounces.
    prior_consume_count: object = _MISSING
    # Residual gap B (loop-detector-false-positives-probes-and-cross-run-state):
    # the run-marker's ``started_at`` the record was written under. _MISSING
    # distinguishes "no run_started_at key" (legacy file, or a probe taken with
    # no live marker) from a recorded run identity — only a recorded identity
    # can prove "this streak belongs to a DIFFERENT/no-longer-live run", so a
    # legacy/unmarked prior is never treated as foreign (conservative: it falls
    # through to the pre-existing same-run behavior).
    prior_run_started_at: object = _MISSING
    try:
        raw = signature_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Validate expected shape: {"signature": [4 items], "count": int, ...}.
        # ``head`` is OPTIONAL — a legacy pre-Phase-9 file has no head key.
        if (
            isinstance(data, dict)
            and isinstance(data.get("signature"), list)
            and len(data["signature"]) == 4
            and isinstance(data.get("count"), int)
        ):
            prior_sig_list = data["signature"]
            prior_count = data["count"]
            if "head" in data:
                prior_head = data["head"]
        # ``step_signature`` / ``step_count`` are OPTIONAL — a legacy pre-Phase-10
        # file has neither key. Validated INDEPENDENTLY of the dispatch tuple so
        # a partially-upgraded file still reads what it can.
        if (
            isinstance(data, dict)
            and isinstance(data.get("step_signature"), list)
            and len(data["step_signature"]) == 2
            and isinstance(data.get("step_count"), int)
        ):
            prior_step_sig_list = data["step_signature"]
            prior_step_count = data["step_count"]
        # ``consume_count`` is OPTIONAL (F2 migration, like ``head``/``step_*``).
        # Read it INDEPENDENTLY so a partially-upgraded file still reads what it
        # can. Only an int is honored — anything else leaves the sentinel so the
        # debounce stays inert (cannot prove a re-read).
        if isinstance(data, dict) and isinstance(data.get("consume_count"), int):
            prior_consume_count = data["consume_count"]
        # ``run_started_at`` is OPTIONAL (Residual gap B migration, like
        # ``head``/``step_*``/``consume_count``) and, like ``consume_count``,
        # is written ONLY on a marked probe (mirrored below) — so a str value
        # here always means "this record was stamped under a live run".
        # Read it INDEPENDENTLY so a partially-upgraded file still reads what
        # it can.
        if isinstance(data, dict) and isinstance(data.get("run_started_at"), str):
            prior_run_started_at = data["run_started_at"]
        # If shape is wrong, treat as no-prior (counts stay 0, sig lists None).
    except (OSError, ValueError, json.JSONDecodeError):
        # File absent, unreadable, or corrupt → treat as no prior.
        pass

    # --- Resolve the F2/F1 double-probe debounce oracle (MARKER-GATED, REPO-SCOPED)
    # Moved ABOVE both count blocks so BOTH the dispatch-tuple count (Phase 9 /
    # F1) and the step-level count (Phase 10 / F2) can share this single oracle
    # read.  (Previously it sat between the two blocks; hoisting it here is the
    # only structural change required by F1 / lazy-validation-readiness.)
    #
    # When a run marker for THIS repo is present, read the registry's
    # consumed-emission count (the guard consumes one nonce per ALLOW, so this is
    # a dispatch counter).  current_consume_count stays the _MISSING sentinel
    # otherwise → the key is never written and the debounce is inert (no-marker
    # path stays byte-identical, --test baselines unchanged).  read_run_marker is
    # a read-only path (create=False) so a probe never creates the state dir as a
    # side-effect.
    #
    # REPO SCOPING (hardening-log Round 8, 2026-06-13): the marker is a SINGLE
    # global file, but the consume-count it gates (consumed_emission_count) is a
    # global registry counter shared by whatever marked run is live.  A probe for
    # repo A must NOT engage the debounce off repo B's marker — doing so
    # (a) made this very function non-hermetic to its `repo_root` argument, so the
    # step-counter unit tests went RED whenever ANY marked run was live on the
    # machine, and (b) latently let a concurrent run in another repo spuriously
    # debounce repo A's step counter (the same cross-session hazard Rounds 3 & 5
    # closed for the marker itself).  Gate the oracle on the marker's `repo_root`
    # matching the probe's resolved `repo_root`; a marker missing `repo_root`
    # (legacy/bind-pending) is treated as non-matching → debounce stays inert.
    # Residual gap A (loop-detector-false-positives-probes-and-cross-run-state):
    # count only CYCLE-class consumptions as "a dispatch landed between probes".
    # A mid-step META dispatch (hardening / recovery / coherence-recovery /
    # investigation / input-audit / …) still consumes a registry nonce, but it
    # is not a forward attempt at the step, so it must not defeat the F1/F2
    # hold. Filtering the oracle to cls="cycle" is the localized fix (D1,
    # oracle refinement over signal generalization) — a genuine same-step
    # oscillation still dispatches a CYCLE each repeat, so it still trips.
    current_consume_count: object = _MISSING
    _marker = read_run_marker()
    _marker_started_at: object = _MISSING
    if _marker is not None:
        _marker_repo = _marker.get("repo_root")
        if _marker_repo is not None and Path(_marker_repo).resolve() == repo_root.resolve():
            current_consume_count = consumed_emission_count(cls="cycle")
            _marker_started_at = _marker.get("started_at")

    # --- Residual gap B: run-lifetime scoping of streak state ----------------
    # (loop-detector-false-positives-probes-and-cross-run-state) Streak files
    # live outside the per-repo keyed state dir (an OS-tempdir file keyed only
    # on repo_root) and NOTHING previously cleared them at --run-end/--run-start
    # — a next run's first probe landing on the same (feature_id, current_step)
    # as a dead run's last probe silently INHERITS that streak (the false-loop
    # T6 warning at run open). Stamp/compare against the run marker's
    # ``started_at`` (the established run identity, already resolved above,
    # repo-scoped the same way the F1/F2 oracle is): reset to NO PRIOR only when
    # we can PROVE the persisted record belongs to a DIFFERENT, SPECIFIC run —
    # i.e. a live marker exists now AND the record carries a DIFFERENT recorded
    # run_started_at (this is exactly the crash scenario: the dead run had a
    # live marker throughout, so every one of its probes stamped its identity).
    # A record with NO run_started_at key at all (legacy/pre-migration, or a
    # write taken with no marker) is NOT treated as foreign — same legacy-
    # tolerance discipline as the head/step_*/consume_count migrations
    # elsewhere in this function: absence is never proof, so it falls through
    # to the pre-existing same-repo streak semantics (conservative — never
    # reset on ambiguous data). When no marker is live for this repo, behavior
    # is UNCHANGED (no established run identity to compare against at all).
    if _marker_started_at is not _MISSING and prior_run_started_at is not _MISSING:
        if prior_run_started_at != _marker_started_at:
            prior_sig_list = None
            prior_step_sig_list = None

    # --- Compute the dispatch-tuple count (Phase 9 WU-2 — HEAD-aware) ---------
    # JSON round-trips tuples as lists, so compare new_sig as a list.
    if prior_sig_list is None or list(new_sig) != prior_sig_list:
        # Changed signature (or no prior) — fresh streak.
        count = 1
    elif prior_head is _MISSING:
        # Legacy file (no `head` recorded) — increment for backward-compat and
        # begin recording head going forward.
        count = prior_count + 1
    elif prior_head is not None and prior_head != current_head:
        # Same tuple but commits landed between probes (HEAD advanced) — that is
        # forward progress, not a stall, so reset the streak to 1.
        count = 1
    elif (
        # F1 (lazy-validation-readiness) double-probe debounce: HOLD count (do
        # NOT increment) when this is provably a RE-READ — the dispatch tuple is
        # unchanged, the HEAD is unchanged, AND no dispatch landed between the
        # two probes.  "No dispatch" = unchanged registry consume-count, which
        # we can only assert when BOTH this probe and the prior write recorded a
        # consume-count (i.e. both were marked probes).  A legacy/unmarked prior
        # (sentinel) or an unmarked current probe (sentinel) cannot prove a
        # re-read → fall through to the normal increment.  This prevents the
        # orchestrator from reading a spurious count=2 and firing a false LOOP
        # DETECTED when an inspection probe and a dispatch probe share the same
        # tuple with no intervening dispatch.  A genuine oscillation still trips
        # because a real dispatch (hence a consume) lands between its repeats.
        current_consume_count is not _MISSING
        and prior_consume_count is not _MISSING
        and current_consume_count == prior_consume_count
    ):
        count = prior_count
    else:
        # Same tuple AND same head (or both None) — genuine consecutive repeat.
        count = prior_count + 1

    # --- Resolve prior vs current sub_skill_args for the ordered-advance exempt
    # The dispatch tuple is (feature_id, sub_skill, sub_skill_args, current_step),
    # so index 2 of the persisted ``signature`` list is the PRIOR probe's
    # sub_skill_args. We reuse that already-persisted field rather than adding a
    # new key — no extra streak state is introduced. ``_MISSING`` when there is
    # no valid prior dispatch tuple (no prior file, or a corrupt/legacy file
    # whose signature failed the 4-element validation above → prior_sig_list is
    # None). When prior args are unknowable we CANNOT prove an advance, so we
    # fall through to the existing debounce/increment (conservative: never
    # weakens the tripwire on a missing/old file).
    current_step_args = state.get("sub_skill_args")
    prior_step_args: object = _MISSING
    if prior_sig_list is not None:  # validated as a 4-element list when set
        prior_step_args = prior_sig_list[2]

    # --- Resolve the resolution-aware reset signal (symptom 3) ---------------
    # (loop-detected-false-positives-from-probe-and-reboot-churn) A needs-input
    # RESOLUTION meta-cycle is itself an Agent dispatch → it consumes a nonce, so
    # the F2 debounce below CANNOT hold the step counter across it (a dispatch
    # provably landed).  Without this branch the HEAD-blind step_count survives a
    # legitimately-resolved blocker and false-trips LOOP-DETECTED.  The resolution
    # bracket persisted ``last_resolution_step_key`` on the run marker
    # (record_resolution_signal); read it here keyed on the CURRENT step
    # signature.  Deterministic + persisted (⚖ D7), never probe-time inference.
    #
    # The signal is ONE-SHOT: it is consumed-and-cleared so the reset fires once
    # across the resolution (not on every subsequent probe — that would
    # re-introduce d8 HEAD-advance immunity for the resolved step).  In ``peek``
    # mode we must NOT mutate the marker, so we do a READ-ONLY check there and
    # leave the consume-and-clear to the real (non-peek) probe.  Marker-gated and
    # repo-scoped inside the helper; a missing/legacy/foreign marker → False, so
    # the reset can never spuriously fire.  Reached only when the step signature
    # is UNCHANGED (the "changed step → fresh streak" branch returns first).
    _resolution_reset = False
    if prior_step_sig_list is not None and list(new_step_sig) == prior_step_sig_list:
        if peek:
            _marker_peek = read_run_marker()
            if (
                _marker_peek is not None
                and _marker_peek.get("repo_root") is not None
                and Path(_marker_peek["repo_root"]).resolve() == repo_root.resolve()
                and _marker_peek.get("last_resolution_step_key") == list(new_step_sig)
            ):
                _resolution_reset = True
        else:
            _resolution_reset = _consume_resolution_signal(repo_root, new_step_sig)

    # --- Compute the step-level count (Phase 10 WU-2 — NO HEAD reset) ---------
    # Deliberately HEAD-BLIND: identical (feature_id, current_step) increments
    # regardless of intervening commits (that is the oscillation-with-commits
    # signal). Legacy files (no step keys) → start at 1 and add the keys below.
    if prior_step_sig_list is None or list(new_step_sig) != prior_step_sig_list:
        step_count = 1
    elif (
        # ORDERED-ADVANCE EXEMPTION (audio-rate-modulation false-positive fix):
        # the step signature (feature_id, current_step) is UNCHANGED but
        # ``sub_skill_args`` ADVANCED since the prior probe. That is genuine
        # ordered forward progress — e.g. a multi-part /execute-plan sequence
        # (part-1.md → part-2.md → …) that legitimately stays on the SAME
        # "Step 7a: execute plan" while marching through plan parts — so it must
        # NOT count toward the oscillation tripwire. RESET to 1.
        #
        # This is the deliberate inverse of the Phase-10 design choice that made
        # the step signature args-BLIND: that choice was to catch the d8
        # write-plan loop, where each cycle COMMITS (HEAD advances → the
        # dispatch-tuple repeat_count resets every iteration so it never trips)
        # yet routing never leaves the step AND the work target is the SAME. The
        # discriminator between the two is precisely whether sub_skill_args moved:
        #   - d8 stuck loop:        args UNCHANGED across repeats → still counts.
        #   - ordered multi-part:   args DIFFERENT each repeat   → exempt here.
        # HEAD-advance-immunity (the d8 property) is preserved: we add NO head
        # reset; we only exempt the case where the work TARGET itself advanced.
        # Guarded on a known prior (prior_step_args is not _MISSING) so a
        # missing/legacy prior can never spuriously reset the tripwire.
        prior_step_args is not _MISSING
        and current_step_args != prior_step_args
    ):
        step_count = 1
    elif _resolution_reset:
        # RESOLUTION-AWARE RESET (symptom 3 — the residual fix). The prior cycle
        # was a needs-input RESOLUTION at this exact step signature (the marker
        # carried a matching one-shot ``last_resolution_step_key``). A resolution
        # is genuine forward progress past a legitimately-resolved blocker, NOT
        # oscillation — so RESET step_count to 1 rather than letting it survive the
        # resolution dispatch's consume (which defeated the F2 hold above).
        #
        # Ordered AFTER the ordered-advance exemption and BEFORE the F2 debounce —
        # the same "genuine forward progress → reset to 1" shape and the same guard
        # discipline (fires only on a recorded/known signal; a missing/legacy/
        # foreign marker yields _resolution_reset=False). HEAD-blindness is
        # preserved: this adds NO head/commit reset (the d8 commit-masked
        # oscillation case has NO resolution signal, so it still falls through to
        # the increment below — symptom-5 design constraint intact). One-shot: the
        # signal was consumed-and-cleared in the read above, so a subsequent probe
        # with no fresh signal increments normally.
        step_count = 1
    elif (
        # F2 double-probe debounce: HOLD step_count (do NOT increment) when this
        # is provably a RE-READ — the step signature is unchanged AND no dispatch
        # landed between the two probes. "No dispatch" = an unchanged registry
        # consume-count, which we can only assert when BOTH this probe and the
        # prior write recorded one (i.e. both were marked). A legacy/unmarked
        # prior (sentinel) or an unmarked current probe (sentinel) cannot prove a
        # re-read → fall through to the normal increment. This preserves
        # HEAD-blindness (keyed on dispatch occurrence, never on commits).
        #
        # Reached only when sub_skill_args is UNCHANGED (the ordered-advance
        # branch above already handled the advanced-args case), so the debounce
        # still governs the genuine same-target re-read it was built for.
        current_consume_count is not _MISSING
        and prior_consume_count is not _MISSING
        and current_consume_count == prior_consume_count
    ):
        step_count = prior_step_count
    else:
        step_count = prior_step_count + 1

    # --- Persist the updated record (skipped entirely in peek mode) ----------
    # peek=True returns the would-be counts WITHOUT touching the state file, so
    # diagnostic probes never inflate or reset either persisted streak.
    if not peek:
        record: dict = {
            "signature": list(new_sig),
            "count": count,
            "head": current_head,
            "step_signature": list(new_step_sig),
            "step_count": step_count,
        }
        # F2: record the consume-count ONLY on a marked probe. Omitting the key
        # on the no-marker path keeps that path's persisted shape byte-identical
        # to the pre-Phase-2 record (legacy-tolerant, like the head/step_*
        # migrations). current_consume_count is the sentinel when no marker.
        if current_consume_count is not _MISSING:
            record["consume_count"] = current_consume_count
        # Residual gap B: record the LIVE run's identity ONLY on a marked
        # probe — same legacy-tolerant discipline as consume_count. Omitting
        # the key on the no-marker path keeps that path's persisted shape
        # byte-identical to before this fix.
        if _marker_started_at is not _MISSING:
            record["run_started_at"] = _marker_started_at
        _atomic_write(signature_path, json.dumps(record))

    return {"repeat_count": count, "step_repeat_count": step_count}


def update_repeat_count(
    repo_root: Path,
    state: dict,
    *,
    signature_path: Path | None = None,
    pipeline: str = "feature",
    peek: bool = False,
) -> int:
    """Backward-compatible wrapper: return ONLY the dispatch-tuple ``repeat_count``.

    Phase-10 added the step-level oscillation counter via ``update_repeat_counts``
    (which returns both counts and persists the ``step_*`` keys in the SAME state
    file). This wrapper preserves the pre-Phase-10 int return for existing callers
    that only need the dispatch streak, while still writing the step keys (so a
    later ``update_repeat_counts`` probe of the same step sees them). Kept as a
    thin delegate — there is exactly one read/write of the shared state file.

    See ``update_repeat_counts`` for the full counting + persistence contract.
    """
    return update_repeat_counts(
        repo_root,
        state,
        signature_path=signature_path,
        pipeline=pipeline,
        peek=peek,
    )["repeat_count"]


# Phase 7 WU-7.4: run-checkpoint filename (single JSON object).  Written by
# --run-end --reason checkpoint; consumed (echoed + deleted) by the next
# --run-start.  Consume-once resume context across a sanctioned pause.
_CHECKPOINT_FILENAME = "lazy-run-checkpoint.json"


# Staleness threshold: markers older than this (in seconds) are deleted.
_MARKER_STALE_SECONDS: float = 24 * 3600  # 24 hours

# ---------------------------------------------------------------------------
# Run-scoped marker field partition SSOT
# (adhoc-checkpoint-resume-field-complete-continuity, 2026-06-23)
#
# A sanctioned same-run checkpoint resume re-mints ALL run-scoped marker state on
# the resuming --run-start (write_run_marker writes the full literal at :8861).
# Continuity is then reconstructed AFTER the mint by restore_checkpoint_counters.
# Previously the reset-vs-carry decision was implicit and split across two
# functions, so a newly-added run-scoped field defaulted to the RESET side BY
# CONSTRUCTION and became the next reactive whack-a-mole.
#
# These two frozensets are the EXPLICIT, ENUMERATED SSOT that partitions every
# run-scoped key of the write_run_marker literal (:8861-8907) into:
#
#   RUN_CONTINUITY_FIELDS — CARRIED across a sanctioned (non-operator-authorized)
#     same-run pause/resume.  These are run-scoped accumulators / identity that
#     the SAME run accrues; resetting any mid-run violates the super-invariant
#     "run-scoped continuity state survives a same-run pause" (HARD CONSTRAINT 8
#     for the counters; cycle-bracket continuity for started_at; the per-feature
#     budget maps are run-scoped accumulators a sanctioned resume must continue).
#
#   RUN_FRESH_FIELDS — RESET / re-minted fresh on resume.  last_advance_consume_count
#     deliberately zeros (the registry is freshly cleared on run-start; carrying a
#     stale watermark would suppress the first post-resume advance — SPEC Out of
#     Scope).  The remaining keys are run-INVARIANT identity/config that
#     write_run_marker re-derives identically anyway (session_id is owner-bound by
#     the resuming --run-start; work_branch is re-resolved at run-start).
#
# COMPLETENESS INVARIANT (the by-construction guarantee, enforced by
# test_run_marker_continuity_partition_is_complete_and_disjoint):
#   set(RUN_CONTINUITY_FIELDS) | set(RUN_FRESH_FIELDS) == _run_marker_scoped_keys()
#   AND the two sets are disjoint.
# A newly-added run-scoped marker key is then a HARD test failure until it is
# explicitly placed in ONE set — it can never silently default to reset.
RUN_CONTINUITY_FIELDS: frozenset = frozenset({
    "forward_cycles",
    "meta_cycles",
    "started_at",
    "per_feature_forward_cycles",
    "per_feature_corrective_cycles",
})
RUN_FRESH_FIELDS: frozenset = frozenset({
    "last_advance_consume_count",
    "pipeline",
    "cloud",
    "repo_root",
    "session_id",
    "max_cycles",
    "nonce_seed",
    "attended",
    "work_branch",
    # parallel-worktree-batch-execution (D2-A): the sanctioned-lane identity
    # stamp ({repo_root, started_at} of the parent run; None on serial runs).
    # Run-INVARIANT identity re-derived at run-start — a checkpoint resume's
    # --run-start re-supplies it (or correctly resets a serial resume to None),
    # so it belongs on the FRESH side, never carried.
    "parent_run",
    # lazy-batch-no-mid-run-budget-or-park-controls: park mode is RUN-SCOPED
    # config re-supplied at run-start from the invocation --park flags (exactly
    # like max_cycles), so a checkpoint resume re-derives it from the resume's
    # own --park args — FRESH, never carried. A mid-run --set-park toggle is a
    # deliberate in-run mutation (like --set-max-cycles on the FRESH max_cycles);
    # a resume re-passes --park if the operator still wants it.
    "park_needs_input",
    "park_blocked",
    "park_provisional",
})


def _run_marker_scoped_keys() -> "set[str]":
    """Return the ACTUAL run-scoped key set of a freshly-minted marker.

    The completeness assertion (test) checks the RUN_CONTINUITY_FIELDS /
    RUN_FRESH_FIELDS partition against THIS — the live write_run_marker literal —
    so the assertion can never drift from a hand-copied list.  Hermetic: mints a
    throwaway marker into the active state dir with an injected ``now`` and reads
    its keys (write_run_marker has no side effect beyond the state-dir file, which
    the test fixture owns and clears).
    """
    return set(
        write_run_marker(
            pipeline="feature", cloud=False, repo_root="/r", now=0.0,
        ).keys()
    )


# ---------------------------------------------------------------------------
# Run-marker API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 7 (lazy-validation-readiness) — sanctioned stop-terminal set.
#
# Motivating incident 2026-06-14: an attended /lazy-batch 50 run stopped at
# 5/50 cycles via --run-end --reason terminal with a fabricated reason, without
# operator authorization.  This constant is the authoritative list of reasons
# that allow an unattended or operator-authorized terminal stop.  Any reason
# NOT in this set is refused unless --operator-authorized is passed.
#
# Both lazy-state.py and bug-state.py import this constant so the set is
# defined in exactly one place (no copy-paste drift between the coupled pair).
# ---------------------------------------------------------------------------
SANCTIONED_STOP_TERMINAL: frozenset[str] = frozenset({
    "all-features-complete",   # feature queue exhausted
    "all-bugs-fixed",          # bug queue exhausted
    "max-cycles",              # hard cycle cap reached
    "cloud-queue-exhausted",   # cloud run out of queue items
    "device-queue-exhausted",  # device run out of queue items
    # host-capability-declaration-for-gated-features Phase 6: the host-axis
    # generalization of device-queue-exhausted — every remaining feature is
    # gated on a host capability absent on THIS host (DEFERRED_REQUIRES_HOST.md).
    # A clean, sanctioned stop (re-opens on a capability-bearing host), so the
    # orchestrator may end a run on it without --operator-authorized, exactly
    # like the device terminal. Feature-pipeline-only in practice (bug-state.py
    # does not emit it), but membership is harmless for the shared frozenset.
    "host-capability-saturated",  # all remaining features gated on an absent host capability
    "queue-missing",           # queue.json absent → cannot continue
    "blocked-halt-for-manual", # script-emitted BLOCKED.md halt
    "needs-research",          # NEEDS_INPUT.md needs-research halt
    "queue-blocked-on-research",  # all queue items need research
    # queue-dependency-dag D4: every remaining queue item is dep-gated (held
    # on an incomplete declared dependency). A clean, sanctioned stop — the
    # holds re-open automatically as their deps complete — so the orchestrator
    # may end a run on it without --operator-authorized, exactly like the
    # host-capability / all-parked exhaustion terminals. Emitted by BOTH state
    # scripts (the dep-gate is a coupled-pair surface).
    "queue-exhausted-dependency-gated",  # all remaining items held on incomplete deps
})


# ---------------------------------------------------------------------------
# SANCTIONED_LANE_PARK_TERMINAL — the park-class terminal reasons a
# /lazy-batch-parallel LANE marker (one whose `parent_run` is non-null) may
# retire on WITHOUT --operator-authorized (lazy-batch-parallel-run-harness-gaps
# gap 4).
#
# A lane is a coordinator-authorized CHILD: SKILL P6 makes park-on-sentinel the
# parallel mode's DEFINING failure isolation ("not an opt-in"), and a lane that
# exhausts its budget slice parks as budget-deferred. A `--feature-id`-scoped
# lane probe emits the SCOPED park terminals (`needs-input-scoped` /
# `blocked-scoped` / `needs-ratification-scoped`), so both the bare and scoped
# forms are sanctioned. This set is consulted ONLY when the run marker carries a
# non-null `parent_run`; a SERIAL run (parent_run: null) parking is a real halt
# that still needs authorization, so these reasons stay OUT of
# SANCTIONED_STOP_TERMINAL. Both state scripts read it (coupled-pair surface —
# a lane marker is pipeline-agnostic).
# ---------------------------------------------------------------------------
SANCTIONED_LANE_PARK_TERMINAL: frozenset[str] = frozenset({
    "needs-input",            # P6 park on NEEDS_INPUT.md (bare)
    "needs-input-scoped",     # …as emitted by a --feature-id lane probe
    "blocked",                # P6 park on BLOCKED.md (bare)
    "blocked-scoped",         # …as emitted by a --feature-id lane probe
    "needs-ratification",     # unratified NEEDS_INPUT_PROVISIONAL.md park (bare)
    "needs-ratification-scoped",  # …scoped lane form
    "budget-deferred",        # lane slice exhausted → parked (P4/Step 3)
})


def write_run_marker(
    pipeline: str,
    cloud: bool,
    repo_root: str,
    *,
    max_cycles: int | None = None,
    session_id: str | None = None,
    nonce_seed: str | None = None,
    attended: bool = True,
    parent_run: dict | None = None,
    park_needs_input: bool = False,
    park_blocked: bool = False,
    park_provisional: bool = False,
    now: float | None = None,
) -> dict:
    """Write (or overwrite) the run marker to the state dir.

    The marker signals that an orchestrator run is active.  Both state scripts'
    ``--run-start`` flag calls this function after preflight passes.  The marker
    is the gating signal for all Phase 1 side effects: without it, registry
    writes, counter advances, and hook injections are all no-ops.

    Fields written:
      - pipeline (str): "feature" | "bug"
      - cloud (bool): whether the run targets cloud mode
      - repo_root (str): absolute path to the project root
      - session_id (str|None): the orchestrator's Claude Code session id.
        None means "bind-on-first-hook-firing" — the inject hook stamps it.
      - started_at (str): ISO-8601 UTC timestamp ending in 'Z'
      - max_cycles (int|None): hard cap for the run
      - nonce_seed (str|None): seed used by nonce derivation (optional — callers
        may omit for fully random nonces)
      - forward_cycles (int): number of real-skill dispatch cycles so far (0)
      - meta_cycles (int): number of meta/pseudo-skill cycles so far (0)
      - attended (bool): Phase 7 — True for interactive /lazy-batch runs (the
        default); False for scheduled/cron/unattended runs.  The stop-
        authorization gate on --run-end reads this field: an attended run cannot
        checkpoint-stop without explicit operator authorization.  Legacy markers
        lacking this field are treated as attended=True (the stricter gate).

    Args:
        pipeline: "feature" or "bug"
        cloud: True when the run is a cloud run
        repo_root: absolute path to the project root as a string
        max_cycles: optional hard cap (stored for inject hook / cycle headers)
        session_id: optional Claude Code session id; None = bind-pending
        nonce_seed: optional nonce seed string
        attended: Phase 7 — True (default) for interactive runs; False for
            scheduled/unattended runs that pass --unattended to --run-start.
        parent_run: parallel-worktree-batch-execution (D2-A) — the sanctioned-
            lane identity stamp `{repo_root, started_at}` of the PARENT run
            whose coordinator armed this marker at a worktree root. None (the
            default) on every serial run — the key is ALWAYS minted so the
            marker shape is stable and the continuity-partition completeness
            test forces explicit classification. Audits and --run-end sweeps
            use it to prove a lane marker sanctioned (vs a rogue walker's).
            Run-invariant identity re-derived at run-start ⇒ RUN_FRESH_FIELDS.
        now: epoch float for started_at (injectable for hermetic tests;
             defaults to time.time())

    Returns:
        The marker dict that was written.
    """
    if now is None:
        now = time.time()
    # Convert the epoch float to an ISO-8601 UTC string ending in 'Z' —
    # the spec's exact format requirement for the started_at field.
    # Use fromtimestamp(tz=utc) — the deprecated utcfromtimestamp() produces a
    # naive datetime that is ambiguous in Python ≥3.12 deprecation warnings.
    started_at = (
        datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    )
    marker: dict = {
        "pipeline": pipeline,
        "cloud": cloud,
        "repo_root": str(repo_root),
        "session_id": session_id,
        "started_at": started_at,
        "max_cycles": max_cycles,
        "nonce_seed": nonce_seed,
        "forward_cycles": 0,
        "meta_cycles": 0,
        # feature-budget-guard-and-skip-ahead Phase 1: per-feature forward-cycle
        # consumption, keyed on feature_id. Advanced as a SIBLING write inside the
        # SAME marker mutation that advances the run-level forward_cycles (both
        # forward-advance triggers carry it), gated by the EXACT same forward-vs-
        # meta classifier. The Phase-2 trip eval reads this map vs the computed
        # ceiling. Legacy markers lacking the key default to {} on read/advance.
        "per_feature_forward_cycles": {},
        # budget-guard-defers-near-complete-feature Phase 1: per-feature count of
        # forward cycles attributable to validation-driven corrective work,
        # keyed on feature_id. Incremented at the corrective-dispatch bracket
        # (record_corrective_cycle, wired in Phase 2) and DISCOUNTED from the
        # budget-guard trip count by budget_trip_signals so a feature that did
        # legitimate corrective work is not punished as monopolization. Seeded
        # {} here in lockstep with per_feature_forward_cycles; legacy markers
        # lacking the key default to {}/0 on read (count_validation_corrective_cycles).
        "per_feature_corrective_cycles": {},
        # ISSUE 5 (d8-effect-chains live run, 2026-06-14): the consume-count
        # watermark at which a cycle counter was last advanced. A counter advances
        # only when the registry consume-count exceeds this (one consume per real
        # dispatch), so bare inject-probe firings never inflate the counter.
        # Starts at 0 — the first advance requires at least one consumed dispatch.
        "last_advance_consume_count": 0,
        # Phase 7 / lazy-validation-readiness: record whether this is an
        # attended (interactive) or unattended (scheduled/cron) run.
        # Default True ensures legacy/migrated callers default to the stricter
        # gate — an attended run cannot checkpoint-stop without operator auth.
        "attended": attended,
        # cycle-subagent-fabricates-policy-or-stray-branch Phase 2: capture the
        # work branch the orchestrator is on at run-start so the write-time
        # stray-branch hook (block-sentinel-write-on-stray-branch.sh) has a
        # reference branch to compare HEAD against. Resolved via _emit_work_branch
        # (best-effort; a non-git root yields its documented fallback string,
        # never raises). Legacy markers lacking this field read as None via
        # marker_work_branch() (back-compat, same pattern as attended /
        # per_feature_forward_cycles).
        "work_branch": _emit_work_branch(Path(repo_root)),
        # parallel-worktree-batch-execution (D2-A): sanctioned-lane identity —
        # the parent run's {repo_root, started_at} when a coordinator armed
        # this marker at a worktree root; None on every serial run. ALWAYS
        # minted (stable marker shape); classified RUN_FRESH_FIELDS.
        "parent_run": parent_run,
        # lazy-batch-no-mid-run-budget-or-park-controls: park mode is now
        # RUN-SCOPED state, persisted in the marker, so an operator can toggle it
        # mid-run (--set-park / --set-park-provisional) and the probe reads it each
        # cycle — instead of park being a pure invocation arg threaded per probe.
        # SEEDED here from the --run-start invocation flags (default False → the
        # marker is byte-identical to a non-park run when no --park was passed).
        # Classified RUN_FRESH_FIELDS: re-supplied at run-start (like max_cycles);
        # a checkpoint resume re-passes --park if the operator wants it. The
        # standing invariant park_provisional ⇒ park_needs_input is enforced by
        # the CLI (--park-provisional requires --park-needs-input) and by
        # set_marker_park; write_run_marker itself trusts its caller (--run-start
        # already validates the pairing before calling here).
        "park_needs_input": bool(park_needs_input),
        "park_blocked": bool(park_blocked),
        "park_provisional": bool(park_provisional),
    }
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def parse_parent_run_arg(raw: "str | None") -> "dict | None":
    """Validate a ``--run-start --parent-run`` JSON payload (D2-A, shared).

    ``None``/empty → ``None`` (a serial run; the marker still mints
    ``parent_run: null``).  Otherwise the payload MUST be a JSON object with
    string ``repo_root`` and ``started_at`` — anything else ``_die``s exit 2
    with ZERO side effects (callers invoke this BEFORE ``write_run_marker``).
    Extra keys are dropped: the marker stores exactly the two-identity stamp.
    Shared by BOTH state scripts (coupled pair — the marker is shared).
    """
    from ._ctx import _die  # deferred kernel import (kept function-local — parity with sibling call sites)
    if not raw:
        return None
    shape_msg = (
        "--parent-run must be a JSON object "
        '{"repo_root": <str>, "started_at": <str>} identifying the parent run'
    )
    try:
        val = json.loads(raw)
    except ValueError:
        _die(shape_msg)
        return None  # pragma: no cover — _die exits
    if not (
        isinstance(val, dict)
        and isinstance(val.get("repo_root"), str)
        and isinstance(val.get("started_at"), str)
    ):
        _die(shape_msg)
        return None  # pragma: no cover — _die exits
    return {"repo_root": val["repo_root"], "started_at": val["started_at"]}


def read_run_marker(
    now: float | None = None,
    session_id: str | None = None,
) -> dict | None:
    """Read the run marker from the state dir, or return None if absent/stale.

    Staleness rules — note the ASYMMETRY between paths A and B (Phase 8 WU-8.1):
      A) Age staleness (DELETE-ON-READ): the marker's ``started_at`` is more
         than 24 hours before ``now`` (injectable epoch float; defaults to
         time.time()).  The marker is DELETED and None is returned.  A crashed
         run must not haunt the next interactive session, and after 24h the
         owning run is presumed dead — destroying its marker is safe.
      B) Session-id mismatch (NON-DESTRUCTIVE — returns None WITHOUT deleting):
         BOTH of the following must be true for the marker to be session-stale:
           * The caller passes a non-None ``session_id`` argument.
           * The marker's ``session_id`` field is also non-None (i.e. the
             marker is "bound", not "bind-pending").
         When that mismatch holds, this function returns None but LEAVES THE
         MARKER FILE ON DISK.  Rationale (Phase 8): a concurrent NON-owner
         session (e.g. an interactive session running while a marked /lazy-batch
         run is live) must see "no marker" (no banner, fast-path allow) but must
         NEVER destroy the OWNING session's live run state.  Deleting here
         silently disarmed enforcement mid-run on 2026-06-12 (~14:53Z, session
         e076ed30).  The owner session_id still reads the marker successfully on
         its own subsequent calls.  If the marker's session_id is None, it is
         bind-pending and is NEVER stale on session-id alone — the inject hook
         has not yet stamped it.

    Corrupt or unparseable marker files are treated as stale (DELETED, None
    returned) so a partial write from a crash never bricks subsequent sessions.
    Corruption deletion is retained (like path A) because a corrupt marker
    belongs to no readable session — there is no owner to protect.

    Args:
        now: epoch float for age comparison (injectable; defaults to time.time())
        session_id: caller's session id for session-binding staleness check;
                    None disables the session-id staleness path

    Returns:
        The marker dict if fresh and valid, otherwise None.
    """
    if now is None:
        now = time.time()
    # Read-only path: do NOT create the directory if it doesn't exist — a
    # missing dir simply means "no marker".
    marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
    if not marker_path.exists():
        return None

    # Load — treat any parse/OS error as stale (crashed write protection).
    try:
        raw = marker_path.read_text(encoding="utf-8")
        marker = json.loads(raw)
        if not isinstance(marker, dict):
            raise ValueError("marker root is not a dict")
    except (OSError, json.JSONDecodeError, ValueError):
        # Corrupt / unparseable — delete and return None.
        try:
            marker_path.unlink()
        except OSError:
            pass
        return None

    # --- Staleness path A: age > 24h ----------------------------------------
    started_at_str = marker.get("started_at", "")
    try:
        # Parse the ISO-8601 UTC 'Z' format we write.
        started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
        started_epoch = (
            started_dt - datetime.datetime(1970, 1, 1)
        ).total_seconds()
    except (ValueError, TypeError):
        # Unrecognized format — treat as stale.
        started_epoch = 0.0
    if now - started_epoch > _MARKER_STALE_SECONDS:
        try:
            marker_path.unlink()
        except OSError:
            pass
        return None

    # --- Staleness path B: session_id mismatch (NON-DESTRUCTIVE) --------------
    # Only fires when BOTH the caller supplies a session_id AND the marker has
    # a non-None session_id (bound, not bind-pending).
    #
    # Phase 8 WU-8.1: this path returns None WITHOUT deleting the marker.  A
    # non-owner session sees "no marker" but must not destroy the owner's run
    # state.  Unlike path A (age) and the corrupt-file path above, NO unlink()
    # happens here — the owning session's next read still succeeds.
    marker_session = marker.get("session_id")
    if session_id is not None and marker_session is not None:
        if session_id != marker_session:
            return None

    return marker


def marker_work_branch(
    now: float | None = None,
    session_id: str | None = None,
) -> str | None:
    """Return the run marker's ``work_branch`` field, or None.

    cycle-subagent-fabricates-policy-or-stray-branch Phase 2: the single read
    helper the ``--marker-work-branch`` CLI query and the write-time
    stray-branch hook share — branch identity is owned in ONE place (same
    contract as ``--marker-present`` owning presence). Returns None when:
      - no live (non-stale) marker is present, OR
      - the marker is a legacy one lacking the ``work_branch`` field, OR
      - the field is present but empty/falsy.
    A None result is the hook's fail-OPEN signal: with no known work branch
    there is nothing to enforce against. Never raises on a missing field
    (back-compat, like ``attended`` / ``per_feature_forward_cycles``).
    """
    marker = read_run_marker(now=now, session_id=session_id)
    if not isinstance(marker, dict):
        return None
    branch = marker.get("work_branch")
    if isinstance(branch, str) and branch:
        return branch
    return None


def bind_marker_session(session_id: str) -> bool:
    """Stamp the run marker with the given session_id if it is currently unbound.

    Called by the inject hook (lazy_inject.py) on the first firing for a new
    run: when the marker has ``session_id: None`` (bind-pending), this function
    atomically writes the provided session_id into the marker so subsequent hook
    firings (and guard calls) can use staleness path B (session-id mismatch
    cleanup) for proper isolation across runs.

    Contract:
      - If no valid marker exists → no-op, returns False.
      - If the marker already has a non-None session_id → no-op (idempotent),
        returns False.  The first hook firing wins; subsequent firings for the
        same session are consistent.
      - If the marker's session_id is None → stamp it atomically, returns True.

    The write uses _atomic_write (temp file + os.replace) to avoid partial
    writes under concurrent hook firings.

    Args:
        session_id: the Claude Code session id from the hook-input JSON.

    Returns:
        True if the marker was stamped (was unbound and is now bound); False
        otherwise (no marker, already bound, or write failed).
    """
    try:
        marker = read_run_marker()
        if marker is None:
            return False
        if marker.get("session_id") is not None:
            # Already bound — idempotent no-op.
            return False
        # Stamp the session_id.
        marker["session_id"] = session_id
        marker_path = claude_state_dir() / _MARKER_FILENAME
        _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail silently — a bind failure is non-fatal; the inject hook proceeds
        # and the marker simply remains unbound (staleness path B stays dormant).
        return False


def marker_owner_status(
    session_id: str,
    *,
    now: float | None = None,
) -> str:
    """Owner-side, NON-DESTRUCTIVE detect: distinguish "no run" from "wrong-stamped run".

    single-slot-marker-ownership-race-disarms-owning-run Phase 2 (Proven Finding
    #4(b)). The silent disarm exists because the OWNER reading ``None`` from
    ``read_run_marker(session_id=owner)`` (staleness path B) cannot tell:
      - "no run is live" (correct fast-path allow), from
      - "my run IS live but the slot was stamped with a foreign session".
    This helper makes the two DISTINGUISHABLE, returning one of:

      - ``"absent"``        — no live marker (missing / age-stale / corrupt). It
                              REUSES ``read_run_marker``'s age + corrupt rules
                              verbatim (by delegating to it with NO session_id,
                              so path B never fires here) — an age-stale or
                              corrupt marker IS deleted by that call, exactly as
                              ``read_run_marker`` would, which is correct: a
                              presumed-dead/unreadable marker has no owner to
                              protect.
      - ``"owned-by-me"``   — a live marker whose ``session_id`` is None
                              (bind-pending — the owner's, not yet stamped) OR
                              equals the caller.
      - ``"foreign-stamped"`` — a live marker whose NON-None ``session_id``
                              differs from the caller.

    HARD CONTRACT: this function is NON-DESTRUCTIVE on the ``foreign-stamped``
    case — it NEVER deletes a live marker on a session mismatch (deleting there
    re-introduces the 2026-06-12 ~14:53Z silent-disarm-by-delete that path B's
    non-destructive rule exists to avoid). The only deletions are the age/corrupt
    ones inherited from ``read_run_marker`` (a marker with no live owner).

    Args:
        session_id: the calling owner's session id (the expected owner on record).
        now: epoch float for age comparison (injectable; defaults to time.time()).

    Returns:
        "absent" | "owned-by-me" | "foreign-stamped".
    """
    # Delegate age/corrupt staleness to read_run_marker with NO session_id, so
    # path B (session mismatch) is DISABLED and we do the owner comparison here
    # non-destructively. An age-stale/corrupt/missing marker → None → "absent".
    marker = read_run_marker(now=now)
    if marker is None:
        return "absent"
    marker_session = marker.get("session_id")
    if marker_session is None or marker_session == session_id:
        return "owned-by-me"
    return "foreign-stamped"


def reassert_marker_owner(
    session_id: str,
    *,
    now: float | None = None,
) -> bool:
    """RE-ARM: re-claim a live, foreign-stamped marker slot for the calling owner.

    single-slot-marker-ownership-race-disarms-owning-run Phase 2 (Proven Finding
    #4(c)). The owner-side re-claim path: when ``marker_owner_status`` is
    ``foreign-stamped`` (a live marker whose slot holds a non-None session OTHER
    than the caller), atomically re-stamp the slot to ``session_id`` and return
    True. For ``absent`` or ``owned-by-me`` it is a no-op returning False
    (idempotent — a second call after a re-claim sees ``owned-by-me`` and
    no-ops).

    This is the ONLY sanctioned mutator of a foreign-stamped slot. It is exposed
    ONLY through the orchestrator-only ``--reassert-owner`` CLI action (guarded by
    ``refuse_if_cycle_active``): only the run's actual orchestrator (which holds
    the ``repo_root``-keyed state dir and its own session_id) re-claims its own
    run's guard.

    Args:
        session_id: the calling owner's session id to re-stamp into the slot.
        now: epoch float for age comparison (injectable; defaults to time.time()).

    Returns:
        True if the slot was foreign-stamped and is now re-claimed; False on an
        absent / owned-by-me marker, or any read/write failure (fail-safe no-op).
    """
    try:
        if marker_owner_status(session_id, now=now) != "foreign-stamped":
            return False
        # Re-read the live marker (NO session_id → no path-B disarm) and re-stamp.
        marker = read_run_marker(now=now)
        if marker is None:
            return False
        marker["session_id"] = session_id
        marker_path = claude_state_dir() / _MARKER_FILENAME
        _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-safe: a re-arm failure is non-fatal; the owner can retry. Never
        # raise into the CLI handler.
        return False


# ---------------------------------------------------------------------------
# lazy-batch-no-mid-run-budget-or-park-controls: operator-authorized in-place
# mid-run mutators of the ACTIVE run marker. Both follow the bind_marker_session
# / reassert_marker_owner discipline: read the live marker, mutate ONE facet,
# _atomic_write it back — NO clobber, NO restart, NO run-end flush. The CLI
# wrappers gate them behind refuse_if_cycle_active (orchestrator-only) AND
# --operator-authorized (the operator explicitly approved the change), parallel
# to the --run-end --reason checkpoint authorization gate.
# ---------------------------------------------------------------------------

def set_marker_max_cycles(new_max: int) -> "dict | None":
    """Update the ACTIVE run marker's ``max_cycles`` in place (mid-run budget change).

    The atomic, marker-consistent enactment of an operator "extend/reduce budget
    to N" — the first-class replacement for the two broken workarounds
    (``--run-start --max-cycles N`` REFUSES on an active marker via the
    clobber guard; ``--run-end`` + ``--run-start`` runs the heavy flush and ENDS
    the run; passing ``--max-cycles N`` per probe leaves the marker stale). After
    this call the marker IS the authoritative live budget: the cycle header
    (fold_max_cycles) and the per-feature budget guard (which reads the marker's
    max_cycles) both agree with it, with no restart.

    Contract:
      - No active marker → no-op, returns None (the CLI wrapper _dies with a
        clear "no active run marker" message).
      - Otherwise: set ``max_cycles = new_max`` atomically and return a summary
        ``{"max_cycles": new_max, "prior_max_cycles": <old>}``.

    Args:
        new_max: the new whole-run cycle budget (a positive int; the CLI
            validates ``>= 1`` before calling).

    Returns:
        Summary dict on success, or None when no active marker exists.
    """
    marker = read_run_marker()
    if marker is None:
        return None
    prior = marker.get("max_cycles")
    marker["max_cycles"] = int(new_max)
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return {"max_cycles": int(new_max), "prior_max_cycles": prior}


def set_marker_park(
    *,
    park_needs_input: "bool | None" = None,
    park_blocked: "bool | None" = None,
    park_provisional: "bool | None" = None,
) -> "dict | None":
    """Toggle the ACTIVE run marker's park fields in place (mid-run park toggle).

    Each argument is tri-state: ``None`` leaves that field untouched; a bool sets
    it. The resulting park state MUST satisfy the standing invariant
    ``park_provisional ⇒ park_needs_input`` (a provisional-accept run is a strict
    modifier of needs-input park mode, SPEC D1). An update that would violate it
    is REFUSED via ``_die`` with ZERO writes — the same fail-closed discipline as
    the CLI's ``--park-provisional requires --park-needs-input`` guard.

    Contract:
      - No active marker → no-op, returns None (the CLI wrapper _dies "no active
        run marker").
      - Otherwise: apply the supplied field changes, enforce the invariant
        (refuse on violation), _atomic_write, and return the resulting park state
        ``{"park_needs_input": ..., "park_blocked": ..., "park_provisional": ...,
        "prior": {<the three prior values>}}``.

    Args:
        park_needs_input: set the needs-input park facet, or None to leave it.
        park_blocked: set the blocked park facet, or None to leave it.
        park_provisional: set the provisional-accept modifier, or None to leave it.

    Returns:
        Resulting park-state summary dict on success, or None when no active
        marker exists.
    """
    from ._ctx import _die  # deferred kernel import (function-local — parity with parse_parent_run_arg)
    marker = read_run_marker()
    if marker is None:
        return None
    prior = {
        "park_needs_input": bool(marker.get("park_needs_input")),
        "park_blocked": bool(marker.get("park_blocked")),
        "park_provisional": bool(marker.get("park_provisional")),
    }
    ni = prior["park_needs_input"] if park_needs_input is None else bool(park_needs_input)
    bl = prior["park_blocked"] if park_blocked is None else bool(park_blocked)
    pv = prior["park_provisional"] if park_provisional is None else bool(park_provisional)
    # Standing invariant: park_provisional is a strict modifier of park_needs_input.
    # Refuse the inconsistent result with ZERO writes (fail-closed).
    if pv and not ni:
        _die(
            "--set-park-provisional on requires park mode (park_needs_input) to be "
            "on. Enable park first (--set-park on), or turn provisional off."
        )
        return None  # pragma: no cover — _die exits
    marker["park_needs_input"] = ni
    marker["park_blocked"] = bl
    marker["park_provisional"] = pv
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return {
        "park_needs_input": ni,
        "park_blocked": bl,
        "park_provisional": pv,
        "prior": prior,
    }


def delete_run_marker(clear_registry: bool = False) -> bool:
    """Delete the run marker file from the state dir.

    Called by both state scripts' ``--run-end`` flag and by every terminal path
    in the orchestrator SKILLs (the 1c.6 PushNotification enumeration doubles
    as the deletion checklist: all-features-complete, cloud/device-queue-exhausted,
    queue-missing, max-cycles, operator-chosen halt, script-error).
    (meta-cap was removed 2026-06-14 — meta_cycles is now uncapped.)

    Args:
        clear_registry: when True, also delete ``lazy-prompt-registry.json`` from
                        the state dir.  Pass ``True`` from the ``--run-end`` path
                        of both state scripts — the registry is run-scoped state and
                        must not bleed across runs.  Default False preserves the
                        existing behaviour for all other callers (terminal paths in
                        orchestrator skills that only need to retire the marker).

    Returns:
        True if the marker file existed and was deleted; False if it was already
        absent (idempotent — safe to call on every terminal path without checking
        first).
    """
    # Read-only directory probe — do not create the dir just to see it's empty.
    state_dir = claude_state_dir(create=False)
    marker_path = state_dir / _MARKER_FILENAME
    deleted = False
    if marker_path.exists():
        try:
            marker_path.unlink()
            deleted = True
        except OSError:
            pass
    if clear_registry:
        registry_path = state_dir / _REGISTRY_FILENAME
        if registry_path.exists():
            try:
                registry_path.unlink()
            except OSError:
                pass
    return deleted


# ---------------------------------------------------------------------------
# Cycle-subagent marker API (lazy-cycle-containment C1 / Phase 2)
#
# The cycle marker (`lazy-cycle-active.json`) is the SIBLING of the run marker
# (`lazy-run-marker.json`) in the same state dir (respecting LAZY_STATE_DIR).
# It says "a dispatched cycle subagent is currently executing" — the on/off
# switch the C3 refusals (Phase 3) and the C2 PreToolUse hook (Phase 4) key on.
# Script-owned: the orchestrator never hand-writes it; it issues
# `--cycle-begin`/`--cycle-end` around every Agent dispatch.
# ---------------------------------------------------------------------------

# Cycle-marker filename inside the state dir (sibling of _MARKER_FILENAME).
_CYCLE_MARKER_FILENAME = "lazy-cycle-active.json"


def resolve_cycle_worker_nonce(passed_nonce: str | None) -> str | None:
    """Resolve the nonce stamped onto a subagent-model cycle marker so the
    dispatch guard's workstation sub-subagent exemption can find it.

    dispatch-guard-denies-workstation-subsubagent-split (consumed-fence wiring
    fix, 2026-07-11): the guard's exemption keys its CONSUMED FENCE on the cycle
    marker's ``nonce`` (``emission_consumed_by_nonce(cycle["nonce"])`` at
    ``lazy_guard.py``). That precise nonce-exact fence only matches when the
    marker's nonce equals the cycle's REGISTERED emission nonce (a ``uuid4().hex``
    from ``register_emission``). The orchestrator, however, is permitted by the
    ``/lazy-batch`` SKILL (Step §1d "reuse the probe's ``cycle_prompt_ref``/
    registry nonce when present, **else any fresh hex**") to pass an arbitrary
    fresh hex for ``--cycle-begin --nonce``. A fresh hex is NOT a registered
    emission nonce, so the fence can never match it → the exemption is DEAD in
    production and every worker-composed sub-subagent dispatch (``/execute-plan``
    test-agent/impl-agent split, ``/spec-phases`` phase-author, …) is denied and
    booked as false hardening debt (hardening-log Rounds 9→13 were the pre-fix
    no-exemption era; this is the post-ship mis-wiring). The unit test masked it
    by hard-coding ``cycle.nonce == emission.nonce`` (``test_hooks.py``
    ``_arm_worker_in_flight``).

    Resolution rule (only the CALLER for a subagent-model cycle invokes this):
      - If ``passed_nonce`` is ALREADY a registered emission nonce, keep it — the
        orchestrator reused the registry/ref nonce (the design-intended path).
      - Otherwise (fresh hex) rebind to THIS cycle's worker emission: the NEWEST
        UNCONSUMED ``class == "cycle"`` registry entry. ``--emit-prompt``
        registers the cycle emission IMMEDIATELY before ``--cycle-begin`` and the
        worker dispatch (which consumes it) has not happened yet, so at write
        time the newest unconsumed cycle emission is unambiguously this cycle's.
        Binding the marker to it makes the precise fence fire when the worker
        dispatch later consumes that same emission — regardless of what
        ``--nonce`` the orchestrator chose.
      - If neither applies (no unconsumed cycle emission — a degraded / no-emit
        cycle), preserve ``passed_nonce`` unchanged (the fence simply will not
        fire — the safe pre-fix degradation).

    Security window is UNCHANGED: the marker is bound to an UNCONSUMED emission,
    so in the pre-dispatch window the fence still reads consumed=False (deny); it
    opens only after the guard-ALLOWed worker dispatch consumes the emission.
    The cycle marker ``nonce`` is read by EXACTLY ONE consumer (the guard fence),
    so this rebind has no other blast radius.

    FAIL-SAFE: any error returns ``passed_nonce`` unchanged (never rebinds to a
    wrong value on a registry read failure).
    """
    try:
        entries = _load_registry().get("entries", [])
        # Reused-nonce path: the orchestrator already passed a registered emission
        # nonce (consumed or not) — keep it (this is the design-intended wiring).
        for entry in entries:
            if entry.get("nonce") == passed_nonce:
                return passed_nonce
        # Fresh-hex path: rebind to this cycle's worker emission — the newest
        # UNCONSUMED cycle-class emission (iterate newest-first / reverse
        # insertion order, mirroring _find_entry_by_sha's newest-wins rule).
        for entry in reversed(entries):
            if entry.get("class") == "cycle" and not entry.get("consumed", False):
                return entry.get("nonce") or passed_nonce
        return passed_nonce
    except Exception:  # noqa: BLE001
        return passed_nonce


def write_cycle_marker(
    feature_id: str,
    nonce: str,
    *,
    kind: str = "real",
    session_id: str | None = None,
    run_started_at: str | None = None,
    begin_head_sha: str | None = None,
    sub_skill: str | None = None,
    sub_skill_args: str | None = None,
    subagent_model: bool | None = None,
    now: float | None = None,
) -> dict:
    """Write (or overwrite) the cycle-subagent marker to the state dir.

    Called by `--cycle-begin` immediately before every Agent dispatch.

    Fields written:
      - feature_id (str): the single feature this dispatch may touch (the C2
        hook's 2nd-feature tripwire compares staged paths against it).
      - nonce (str): the dispatch nonce.
      - kind (str): "real" (a real-skill cycle) | "meta" (input-audit,
        apply-resolution, recovery, hardening, coherence-recovery,
        needs-runtime-redispatch). Default "real".
      - started_at (str): ISO-8601 UTC timestamp ending in 'Z'.
      - session_id (str|None): the parent orchestrator session id, best-effort
        from the env (CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID) when not
        passed explicitly; None when unavailable.
      - commit_tally (int): starts at 0; the C2 hook (Phase 4) increments it on
        each allowed `git commit` for the commit-count backstop.
      - run_started_at (str|None): the owning run marker's ``started_at`` snapshot
        at --cycle-begin (the stable run identity). None when no run marker was
        present. Used by detect_cycle_bracket_friction (hardening-blind-to-
        process-friction Phase 2) to detect a torn cycle bracket — a dispatched
        cycle that ran --run-end / overwrote the run marker.
      - begin_head_sha (str|None): ``git rev-parse HEAD`` snapshot at --cycle-begin.
        None when not a git tree / degraded. Used to detect unexpected commits
        (HEAD advanced beyond the per-sub_skill budget by --cycle-end).
      - sub_skill (str|None): the dispatched sub_skill name (e.g. "execute-plan").
        None for callers that omit it. detect_cycle_bracket_friction selects the
        per-sub_skill commit budget from this — WITHOUT it the detector falls back
        to the conservative default budget (1) and false-positives on a normal
        multi-commit cycle (e.g. execute-plan's test+impl commits, budget 3).
      - sub_skill_args (str|None): the dispatched sub_skill_args (for an
        execute-plan cycle this is the PLAN PART path). None for callers that omit
        it. cycle_end_friction_check uses it to read the plan's declared phase
        count and SCALE the execute-plan commit budget (one commit per phase is
        the normal /execute-plan cadence — a 6-phase plan legitimately makes ~6
        commits, which the fixed budget of 3 false-positived as unexpected-commits;
        hardening Round 20 D2). Additive (default None) → legacy markers degrade to
        the fixed per-sub_skill budget, never a crash.
      - subagent_model (bool): whether the dispatched sub_skill's SKILL.md
        frontmatter declares ``subagent-model: true`` (see
        skill_declares_subagent_model). Copied here at --cycle-begin so the
        dispatch guard's workstation sub-subagent exemption reads a marker
        field, never SKILL.md itself (dispatch-guard-denies-workstation-
        subsubagent-split, decision 4). Callers may pass an explicit bool to
        override; the default None computes it from the sub_skill, using the
        live run marker's repo_root (best-effort) for the repo-scoped lookup.
        Additive — legacy markers without the field read as falsy (no
        exemption), never a crash.

    Self-healing staleness: if a marker already EXISTS (a prior dispatch crashed
    without `--cycle-end`), it is OVERWRITTEN and the event logged. The
    orchestrator is single-threaded — only one dispatch is ever in flight — so
    overwrite-and-log is the correct recovery, never a hard error.

    Args:
        feature_id: the feature this dispatch is scoped to.
        nonce: the dispatch nonce.
        kind: "real" | "meta" (default "real").
        session_id: parent session id; None → best-effort env lookup.
        now: epoch float for started_at (injectable for tests; defaults to
             time.time()).

    Returns:
        The marker dict that was written.
    """
    if now is None:
        now = time.time()
    if session_id is None:
        session_id = (
            os.environ.get("CLAUDE_SESSION_ID")
            or os.environ.get("CLAUDE_CODE_SESSION_ID")
        )
    # decision 4: stamp the sub_skill's declared sub-subagent capability onto
    # the marker (explicit override wins; None → compute). The run marker's
    # repo_root feeds the repo-scoped SKILL.md lookup; every read is
    # best-effort and the helper is fail-closed, so a degraded read stamps
    # False (no exemption) and never blocks the marker write.
    if subagent_model is None:
        _sm_repo_root = None
        try:
            _sm_repo_root = (read_run_marker() or {}).get("repo_root")
        except Exception:  # noqa: BLE001
            _sm_repo_root = None
        subagent_model = skill_declares_subagent_model(
            sub_skill, repo_root=_sm_repo_root
        )
    # Normalize to a bool once (an explicit caller may pass any truthy/falsy).
    subagent_model = bool(subagent_model)
    # consumed-fence wiring fix (dispatch-guard-denies-workstation-subsubagent-
    # split, 2026-07-11): for a subagent-model cycle, rebind the marker's nonce
    # to this cycle's registered worker emission so the guard's exemption fence
    # (emission_consumed_by_nonce(cycle["nonce"])) can find it even when the
    # orchestrator passed a fresh, unregistered hex for --cycle-begin --nonce.
    # See resolve_cycle_worker_nonce for the full rationale + security argument.
    # Scoped to subagent_model cycles so meta/non-exempt cycles keep their passed
    # nonce byte-identically (zero behavior change off the exemption path).
    if subagent_model:
        nonce = resolve_cycle_worker_nonce(nonce)
    state_dir = claude_state_dir()
    marker_path = state_dir / _CYCLE_MARKER_FILENAME

    # Self-healing staleness: an existing marker means a prior dispatch never
    # cleared — overwrite it and log the event (single-threaded orchestrator).
    if marker_path.exists():
        prior_id = None
        try:
            prior = json.loads(marker_path.read_text(encoding="utf-8"))
            if isinstance(prior, dict):
                prior_id = prior.get("feature_id")
        except (OSError, json.JSONDecodeError):
            prior_id = "<unreadable>"
        _diag(
            f"cycle marker overwrite (stale prior dispatch never --cycle-end'd): "
            f"prior feature_id={prior_id!r} → new feature_id={feature_id!r}"
        )

    # Use fromtimestamp(tz=utc) — the deprecated utcfromtimestamp() warns in
    # Python ≥3.12 (mirrors write_run_marker's started_at formatting).
    started_at = (
        datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    )
    marker = {
        "feature_id": feature_id,
        "nonce": nonce,
        "kind": kind,
        "started_at": started_at,
        "session_id": session_id,
        "commit_tally": 0,
        # hardening-blind-to-process-friction Phase 2: additive run-identity +
        # HEAD snapshot (default None so existing 6-field callers/fixtures are
        # unbroken). --cycle-begin populates these.
        "run_started_at": run_started_at,
        "begin_head_sha": begin_head_sha,
        # hardening-blind-to-process-friction (false-positive fix): the dispatched
        # sub_skill, so cycle_end_friction_check can recover the correct per-sub_skill
        # commit budget instead of forcing the conservative default. Additive
        # (default None) → legacy markers/fixtures degrade to the default budget,
        # never a crash.
        "sub_skill": sub_skill,
        # hardening Round 20 (D2): the dispatched sub_skill_args (plan part path for
        # an execute-plan cycle) so cycle_end_friction_check can scale the
        # execute-plan commit budget by the plan's declared phase count. Additive
        # (default None) → legacy markers degrade to the fixed per-sub_skill budget.
        "sub_skill_args": sub_skill_args,
        # decision 4 (dispatch-guard-denies-workstation-subsubagent-split): the
        # sub_skill's declared sub-subagent capability, read by the guard's
        # workstation exemption. bool — never None (normalized above).
        "subagent_model": subagent_model,
    }
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def read_cycle_marker() -> dict | None:
    """Read the cycle-subagent marker from the state dir, or None if absent.

    This is the single predicate the C3 refusals (Phase 3) and the C2 hook
    fast-path (Phase 4) both consult. Read-only: never creates the state dir.
    A corrupt/unparseable marker reads as None (never bricks a caller) — the
    C2 hook fast-path uses a bare `test -f`, so the worst case of a corrupt
    marker is that the script-side refusals treat it as absent while the hook
    still denies; the orchestrator's next `--cycle-begin`/`--cycle-end`
    rewrites/clears it.

    Returns:
        The parsed marker dict if present and valid, otherwise None.
    """
    marker_path = claude_state_dir(create=False) / _CYCLE_MARKER_FILENAME
    if not marker_path.exists():
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            return None
        return marker
    except (OSError, json.JSONDecodeError):
        return None


def clear_cycle_marker() -> bool:
    """Delete the cycle-subagent marker. Idempotent.

    Called by `--cycle-end` after every Agent return (success, halt, error).
    A missing marker is a no-op: returns False, raises nothing, exits cleanly.

    Returns:
        True if the marker existed and was deleted; False if already absent.
    """
    marker_path = claude_state_dir(create=False) / _CYCLE_MARKER_FILENAME
    if not marker_path.exists():
        return False
    try:
        marker_path.unlink()
        return True
    except OSError:
        return False


# Slack added on top of the plan's phase count for a phase-scaled execute-plan
# budget (hardening Round 20 D2): /execute-plan commits once per phase, but a phase
# may split into a test commit + an impl commit (TDD cadence), so allow a small
# constant cushion above the phase count before a cycle is deemed a runaway.
_EXECUTE_PLAN_PHASE_BUDGET_SLACK = 2

# Deterministic BOOKEND-cadence commits that EVERY /execute-plan cycle makes but
# the per-WU-checkbox / phase `scale_count` structurally OMITS (hardening Round 46,
# 2026-06-30). The execute-plan SKILL commits a plan STATUS FLIP at BOTH ends of a
# cycle — `chore(<id>): mark plan In-progress` at the start (SKILL Step 4e / :296)
# and `chore/docs(<id>): mark plan part N Complete` + PHASES/spin-off reconcile at
# the end (SKILL Step 4f / :105, :310) — plus an occasional in-cycle `revert(...)`
# self-correction. None of these are per-WU work units, so `scale_count` (= max of
# phase count and per-WU checkbox count) never counts them; the Round-20 SLACK of 2
# was sized for the WITHIN-phase test+impl split, NOT the two out-of-band bookend
# commits. When a plan's authored WU commits land close to its declared WU count
# AND a bookend/revert is present, the bookends push the AUTHORED (merge-excluded,
# Round 42) count past `scale_count + slack`, false-positiving a clean cycle as a
# runaway.
#
# Concrete recurrence (Round 46, AlgoBooth bug `audio-engine-clippy-warnings-fail-
# rust-gate`, Step 7a execute-plan, begin_head_sha=e01a97dd6685): the plan declares
# `phases: [1]` and 4 per-WU checkboxes → `scale_count = max(1, 4) = 4`, budget
# `4 + slack 2 = 6`. The cycle authored 7 non-merge commits — begin-chore
# `ba6049ce5 mark plan In-progress`, WU commits `5f90e4e80`/`0b1477faa`/`daef5aadd`
# (WU-1/2/3+4) + `20870de77` (feature-gated lint fix), an in-cycle
# `0325bb91d revert(...): un-commit accidentally-regenerated golden JSONs`, and the
# end reconcile `88ca68794 docs(...): reconcile — plan Complete, SPEC In-progress,
# spin-offs`. All 7 are legitimate; NONE are merges (`git rev-list --count
# --no-merges` = 7, so Round 42's merge exclusion does not help). The overflow is
# exactly the two structural bookends (In-progress flip + Complete reconcile) the
# WU budget never modeled — 7 = 4 WU-ish + 1 extra fix + 1 revert + ... but the
# load-bearing 2 that push it over `scale_count(4)+slack(2)=6` are the bookends.
#
# Budgeting the two deterministic bookends explicitly closes this: budget becomes
# `scale_count + slack + bookend`. This is a budget-DENOMINATOR structural fix (the
# same class as the Round-20 slack), narrowly scoped to execute-plan — it does NOT
# touch the friction threshold or the runaway ceiling for any other skill, and a
# genuine runaway (authored commits beyond WUs + slack + the 2 bookends) STILL trips.
_EXECUTE_PLAN_BOOKEND_COMMITS = 2


def _execute_plan_commit_budget(
    sub_skill: str | None, sub_skill_args: str | None
) -> int | None:
    """Work-scaled commit budget for an execute-plan cycle (hardening Round 20 D2;
    WU-scaling follow-up 2026-06-16).

    /execute-plan commits once per WORK UNIT — the per-WU ``tick the box + commit``
    cadence is the dominant signal, not the phase count. Round 20 scaled the budget
    by ``phase_count + slack``, but a WU-dense plan part (e.g. 5 WUs spread across
    2 phases) legitimately makes ~5 commits, which a phase-only budget of
    ``2 + slack = 4`` under-counts and false-positives as ``unexpected-commits``
    (the 2026-06-16 cycle-subagent part-1 recurrence: 5 commits vs a phase-derived
    budget of 4). This derives the budget from the GREATER of the dispatched plan
    part's declared phase count (``phases:`` frontmatter) and its parseable per-WU
    checkbox count (``- [ ] WU-N`` rows, write-plan ISSUE-6), plus a small slack —
    so a legacy phase-only plan and an ISSUE-6 per-WU plan both get an honest
    ceiling while a genuine runaway (commits beyond the work the plan declares)
    still trips.

    Returns the scaled budget, or ``None`` when it cannot be computed — for ANY of:
    a non-execute-plan sub_skill, a missing/blank sub_skill_args, an unreadable
    plan file, or a plan with NEITHER a parseable ``phases:`` field NOR any per-WU
    checkboxes. A ``None`` return makes ``detect_cycle_bracket_friction`` fall back
    to the fixed table budget, so the worst case is the pre-Round-20 behavior —
    never a false negative, never a crash.

    The sub_skill_args may carry trailing flags (e.g. ``"<plan>.md --batch"``);
    only the leading whitespace-delimited token is treated as the plan path
    (mirrors the plan-arg extraction already used in the probe-enrichment path).
    """
    if sub_skill != "execute-plan":
        return None
    if not sub_skill_args:
        return None
    plan_token = str(sub_skill_args).split()[0] if str(sub_skill_args).split() else ""
    if not plan_token:
        return None
    plan_path = Path(plan_token)
    try:
        phase_set = _plan_phase_set(plan_path)
    except Exception:  # noqa: BLE001
        phase_set = set()
    try:
        unchecked_wus, checked_wus = _plan_wu_checkbox_counts(
            plan_path.read_text(encoding="utf-8")
        )
    except Exception:  # noqa: BLE001
        unchecked_wus, checked_wus = 0, 0
    # Commits scale with WORK UNITS, so take the greater of the phase count and the
    # total (checked + unchecked) per-WU checkbox count. Either signal alone may be
    # absent (a legacy plan with no per-WU rows; an unusual plan with no phases:
    # field) — using the max means whichever the plan actually declares governs.
    scale_count = max(len(phase_set), unchecked_wus + checked_wus)
    if scale_count <= 0:
        return None
    # scale_count models per-WU authored commits; slack covers the within-phase
    # test+impl split; bookend covers the two deterministic out-of-band status-flip
    # commits (In-progress at start, Complete-reconcile at end) that EVERY cycle
    # makes but scale_count never counts (Round 46). A genuine runaway still trips.
    return scale_count + _EXECUTE_PLAN_PHASE_BUDGET_SLACK + _EXECUTE_PLAN_BOOKEND_COMMITS


def detect_cycle_bracket_friction(
    marker: dict,
    current_run_started_at: str | None,
    current_head_sha: str | None,
    sub_skill: str | None,
    *,
    commits_since: int | None = None,
    budget_override: int | None = None,
    current_branch: str | None = None,
    expected_work_branch: str | None = None,
    repo_root: "str | Path | None" = None,
    now: float | None = None,
) -> dict | None:
    """Detect process-friction at --cycle-end: a torn cycle bracket or unexpected
    commits (hardening-blind-to-process-friction Phase 2, Locked Decision D1).

    Almost pure: every signal is computed from caller-supplied values EXCEPT the
    registry-derived commit-budget membership test (branch 3 below), which reads
    the dispatched skill's own SKILL.md frontmatter via ``skill_declares_multi_commit``
    (adhoc-derive-multi-commit-budget-from-dispatch-sites, 2026-07-12) — the same
    class of deterministic, git-committed-file read ``skill_declares_subagent_model``
    already performs elsewhere in this module. The caller (--cycle-end) supplies
    every other live value: the cycle marker as snapshotted at --cycle-begin, the
    CURRENT run identity and HEAD sha resolved fresh at --cycle-end, the dispatched
    sub_skill, and the number of commits HEAD advanced since
    ``marker['begin_head_sha']``.

    Two deterministic on-disk signals (D1):
      (a) cycle-bracket-break — the run identity present at --cycle-begin
          (``marker['run_started_at']``) is absent or CHANGED at --cycle-end
          (the dispatched cycle ran --run-end, started a new run, or overwrote the
          run marker). A null begin-snapshot disables this signal (degraded
          --cycle-begin had no run marker to snapshot → no false positive).
      (b) unexpected-commits — HEAD advanced by more than the conservative
          per-sub_skill budget beyond ``marker['begin_head_sha']``. A null
          begin-snapshot or a null/None ``commits_since`` disables this signal.
          EXEMPT when ``marker['kind'] == 'meta'``: a meta cycle is an
          orchestrator-driven remediation dispatch (hardening / input-audit /
          recovery / apply-resolution) that legitimately commits an unbounded
          number of times and carries no sub_skill to budget — signal (b) is
          skipped entirely for it (signal (a) still applies). ALSO exempt when a
          NON-meta cycle carries a falsy ``sub_skill`` (the marker was written by a
          --cycle-begin that omitted --sub-skill): the commit budget is
          INDETERMINATE without a dispatch identity, so applying the single-commit
          default would false-positive every legitimately multi-commit real cycle —
          signal (b) is disabled (fail-open), signals (a)/(a.5) still fire.

    Args:
        marker: the cycle marker dict from read_cycle_marker() (snapshotted at
            --cycle-begin). May lack the additive fields (legacy/partial) → those
            signals degrade to off.
        current_run_started_at: the run marker's ``started_at`` resolved NOW, or
            None when no run marker is present.
        current_head_sha: ``git rev-parse HEAD`` resolved NOW, or None (degraded).
        sub_skill: the dispatched sub_skill name (selects the commit budget).
        commits_since: number of commits HEAD advanced since
            ``marker['begin_head_sha']`` (caller computes via ``git rev-list
            --count begin..HEAD``); None/degraded disables signal (b).
        budget_override: an explicit commit budget that SUPERSEDES the per-sub_skill
            table lookup when provided (hardening Round 20 D2). The caller
            (cycle_end_friction_check) computes this for an execute-plan cycle by
            reading the plan part's declared phase count, so a normal one-commit-
            per-phase /execute-plan cadence (e.g. a 6-phase plan → ~6 commits) does
            NOT false-positive against the fixed table budget of 3. None → fall back
            to the per-sub_skill table (legacy behavior, never a crash).
        now: unused placeholder for caller symmetry / future timing fields.

    Returns:
        A friction descriptor ``{"reason": <str>, "detail": <str>, ...}`` on the
        FIRST signal that trips (bracket-break checked before commits), or None
        when the bracket is clean / inputs are degraded.
    """
    if not isinstance(marker, dict):
        return None
    begin_run_started_at = marker.get("run_started_at")
    begin_head_sha = marker.get("begin_head_sha")

    # --- Signal (a): cycle-bracket-break ------------------------------------
    # Only meaningful when --cycle-begin actually snapshotted a run identity.
    # A null begin snapshot means there was no run marker to compare against —
    # degrade to off (never a false positive).
    if begin_run_started_at is not None:
        if current_run_started_at != begin_run_started_at:
            absent = current_run_started_at is None
            detail = (
                "run marker absent at --cycle-end (present at --cycle-begin: "
                f"started_at={begin_run_started_at!r})"
                if absent
                else (
                    "run identity changed mid-cycle: begin started_at="
                    f"{begin_run_started_at!r} != end started_at="
                    f"{current_run_started_at!r}"
                )
            )
            return {
                "reason": "cycle-bracket-break",
                "detail": detail,
                "sub_skill": sub_skill,
            }

    # --- Signal (a.5): branch-divergence (harden Round 43, 2026-06-29) -------
    # A cycle that ends on a branch OTHER than the run's work_branch strands every
    # commit/sentinel it wrote where the state scripts (which read the work_branch)
    # cannot see them. The cycle-base-prompt R10 hard-contract already forbids
    # `git checkout -b` / `git switch -c` / `git branch <new>` mid-cycle, but that
    # rule relies on SUBAGENT COMPLIANCE — and a real mcp-test cycle violated it
    # (created fix/<...>, committed the fix there, and reported success WITHOUT the
    # mandated STOP), so the divergence was caught only by manual orchestrator
    # reconciliation (ff-merge to work branch + branch delete). This signal makes the
    # violation SELF-ANNOUNCING (a kind: process-friction ledger entry → pending
    # hardening), exactly like unexpected-commits — turning a silent, manually-caught
    # integrity break into a routed one. It applies to ALL cycles (meta INCLUDED — a
    # wrong branch is always integrity-breaking), so it is checked BEFORE the
    # meta-cycle exemption below. Degrades to off when either branch is unknown
    # (legacy run marker without work_branch, a detached HEAD reading "HEAD", or a
    # degraded git read) → never a false positive.
    if (
        current_branch
        and current_branch != "HEAD"
        and expected_work_branch
        and current_branch != expected_work_branch
    ):
        return {
            "reason": "branch-divergence",
            "detail": (
                f"cycle ended on branch {current_branch!r} but the run's "
                f"work_branch is {expected_work_branch!r} — commits/sentinels this "
                f"cycle wrote are stranded off the work branch (R10 work-branch-only "
                f"hard-contract violated; reconcile by ff-merging onto "
                f"{expected_work_branch!r} and deleting the stray branch)"
            ),
            "sub_skill": sub_skill,
        }

    # --- Signal (b): unexpected-commits -------------------------------------
    # Requires a known begin HEAD snapshot AND a known commit count.
    #
    # META-CYCLE EXEMPTION (hardening-blind-to-process-friction, 2026-06-16 D-A):
    # a cycle whose marker kind=="meta" (hardening / input-audit / recovery /
    # apply-resolution / coherence-recovery / needs-runtime-redispatch) is an
    # ORCHESTRATOR-DRIVEN remediation dispatch, NOT a runaway real-skill subagent.
    # A meta cycle legitimately commits an UNBOUNDED number of times (e.g. a
    # hardening cycle commits a script fix AND a hardening-log append; an
    # apply-resolution cycle commits each resolved sentinel) and carries
    # sub_skill=None (no work-skill is dispatched), so the per-sub_skill budget
    # defaults to 1 and 2+ legit commits tripped `unexpected-commits` on EVERY
    # meta cycle — a self-perpetuating loop where each hardening cycle re-tripped
    # at its own --cycle-end (Rounds 16/17 chased the symptom via the pseudo-skill
    # budget rows + mandatory --sub-skill prose, but a meta cycle has no sub_skill
    # to budget; the structural fix is to exempt kind==meta from signal (b)).
    # Signal (a) bracket-break is NOT exempted — a meta cycle that tears the run
    # bracket (overwrites/ends the run marker, e.g. the D-B clobber) is genuine
    # corruption and must still self-announce.  The exemption is read from the
    # marker dict the caller already passes (cycle_end_friction_check threads the
    # live marker), so it is effective for the meta hardening cycle running THIS
    # very dispatch — it cannot re-trip at its own --cycle-end.
    if marker.get("kind") == "meta":
        return None
    if begin_head_sha is not None and commits_since is not None:
        # hardening Round 20 (D2): an explicit budget_override (e.g. a phase-scaled
        # execute-plan budget the caller derived from the plan frontmatter)
        # supersedes the fixed per-sub_skill table. Only a POSITIVE override is
        # honored — a None/degraded computation falls back to the table so the
        # signal never accidentally disables.
        if isinstance(budget_override, int) and budget_override > 0:
            budget = budget_override
        elif not (sub_skill or "").strip():
            # BUDGET-INDETERMINATE INPUT (adhoc-derive-multi-commit-budget…,
            # harden 2026-07-04): a NON-meta cycle whose sub_skill was never
            # recorded (the marker was written by a --cycle-begin that omitted
            # --sub-skill) has NO derivable commit budget — the dispatch identity
            # that selects the multi-commit ceiling is unknown, so the registry
            # lookup below would fall to the single-commit default and
            # false-positive EVERY legitimately multi-commit real cycle. That is
            # the observed friction: an /execute-plan cycle whose --cycle-begin
            # recorded sub_skill=None landed 3 sanctioned per-WU commits and
            # tripped budget=1 (a FALSE unexpected-commits). Disable signal (b)
            # for this degraded input — the SAME fail-open posture the meta
            # exemption and the null-HEAD / null-commits guards already take ("a
            # degraded input yields None signals, never a false positive"). The
            # integrity signals (a) bracket-break and (a.5) branch-divergence were
            # evaluated ABOVE and are sub_skill-independent, so they still fire; a
            # genuine runaway with a RECORDED sub_skill is unaffected (its budget is
            # derivable). Write-side complement: the /lazy-batch(-bug-batch) prose
            # MANDATES --sub-skill on every real --cycle-begin, so this input never
            # occurs for a sanctioned dispatch — this guard is the read-side
            # backstop that stops the mis-recorded marker from manufacturing debt.
            return None
        else:
            # Branch (3): DERIVE the budget from skill_declares_multi_commit — a
            # skill-declared `commit-cadence: multi` frontmatter flag (or pseudo-
            # skill dict membership) ⇒ the multi-commit ceiling, else the
            # single-commit default. No hand-maintained literal registry to keep in
            # sync (closes the recurring missing-row defect class:
            # adhoc-derive-multi-commit-budget-from-dispatch-sites). A flagged
            # skill's ceiling is the uniform `_CYCLE_COMMIT_MULTI` UNLESS it
            # declares a higher worst-case cadence in `_MULTI_COMMIT_CEILING_OVERRIDE`
            # (the MAGNITUDE dimension — e.g. mcp-test's self-heal + 2-part reconcile
            # + sentinel correction = 4); an unflagged skill always gets the default.
            # `_CYCLE_COMMIT_NOISE_ALLOWANCE` (adhoc-align-cycle-commit-count-with-
            # budget-population) then adds ONE shared, skill-agnostic cushion on top
            # of EITHER ceiling — the population-alignment fix — leaving
            # execute-plan's own budget_override model (handled above) untouched.
            ss = sub_skill or ""
            base_budget = (
                _MULTI_COMMIT_CEILING_OVERRIDE.get(ss, _CYCLE_COMMIT_MULTI)
                if skill_declares_multi_commit(ss, repo_root=repo_root)
                else _CYCLE_COMMIT_BUDGET_DEFAULT
            )
            budget = base_budget + _CYCLE_COMMIT_NOISE_ALLOWANCE
        if commits_since > budget:
            return {
                "reason": "unexpected-commits",
                "detail": (
                    f"HEAD advanced {commits_since} commits since --cycle-begin "
                    f"(begin_head_sha={(begin_head_sha or '')[:12]}, "
                    f"sub_skill={sub_skill!r}, budget={budget})"
                ),
                "sub_skill": sub_skill,
                "commits_since": commits_since,
            }

    return None


def head_sha_snapshot(repo_root: Path | None = None) -> str | None:
    """Best-effort ``git rev-parse HEAD`` against repo_root (cwd default).

    Returns the full HEAD sha string, or None when not a git tree / git fails /
    any OS-level error — callers treat None as a degraded snapshot (the
    unexpected-commits signal disables, never a false positive). Used by
    --cycle-begin to snapshot the begin HEAD into the cycle marker.
    """
    from .runtimeplane import _git  # deferred (runtime/git plane; function-local avoids import cycle)
    root = repo_root or Path.cwd()
    try:
        proc = _git(root, "rev-parse", "HEAD")
        if proc.returncode == 0:
            return (proc.stdout or "").strip() or None
    except Exception:  # noqa: BLE001
        pass
    return None


def current_branch_snapshot(repo_root: Path | None = None) -> str | None:
    """Best-effort ``git rev-parse --abbrev-ref HEAD`` against repo_root (cwd default).

    Returns the current branch NAME, or None when not a git tree / git fails / the
    output is empty / HEAD is detached (the literal ``"HEAD"``). Callers treat None
    as a degraded snapshot (the branch-divergence signal disables — never a false
    positive). Distinct from ``_emit_work_branch`` (the prompt-token resolver), which
    returns the human fallback string ``"the current branch"`` on failure — a value
    that would FALSE-trip an equality comparison; the friction detector needs a clean
    None instead, so it uses this helper. Used by --cycle-end to resolve the live
    branch for the branch-divergence signal (harden Round 43).
    """
    from .runtimeplane import _git  # deferred (runtime/git plane; function-local avoids import cycle)
    root = repo_root or Path.cwd()
    try:
        proc = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if proc.returncode == 0:
            branch = (proc.stdout or "").strip()
            if branch and branch != "HEAD":
                return branch
    except Exception:  # noqa: BLE001
        pass
    return None


def _count_authored_commits_since(
    repo_root: Path, begin_head_sha: str | None
) -> int | None:
    """Count AUTHORED commits HEAD advanced since ``begin_head_sha``, EXCLUDING
    merge commits (hardening Round 42, 2026-06-29).

    The ``unexpected-commits`` budget is a model of *authored work-unit commits*:
    the budget side (``_execute_plan_commit_budget``) derives the ceiling from the
    plan part's per-WU checkbox / phase count, i.e. the units of work the cycle is
    expected to author. The count side MUST measure the same thing — authored
    commits — or the comparison is apples-to-oranges. A bare
    ``git rev-list --count <begin>..HEAD`` ALSO counts merge commits, which are
    branch-integration artifacts, not authored work units: a sibling PR merged into
    ``main`` during the cycle window (or any out-of-band merge) inflates the count by
    ≥1 with ZERO corresponding work, false-positiving an otherwise-clean cycle as a
    runaway.

    Concrete recurrence (Round 42, AlgoBooth ``algorithmic-fill-buffer``, Step 7a
    execute-plan): the dispatched part-3 plan declared 5 WUs (budget = 5 + slack 2 =
    7), and the cycle authored exactly 5 WU commits — but ``begin..HEAD`` also spanned
    a merge commit (``d7b867a81`` — PR #107 pre-release-roadmap branch integration)
    plus 2 unrelated ``docs:`` roadmap/queue commits that landed on ``main`` during
    the window, so the bare count was 8 > 7 and tripped ``unexpected-commits``.
    ``--no-merges`` brings the count to exactly 7 (≤ budget) — the merge commit was
    the load-bearing overflow.

    ``--no-merges`` is the structural fix (a merge commit is NEVER an authored
    work unit, for ANY sub_skill). It is deliberately NARROW: the two unrelated
    non-merge ``docs:`` commits are still counted — filtering those would require
    per-cycle path scoping and risk masking a real runaway (false negative). Excluding
    only merges removes a category error without lowering the runaway ceiling: a
    genuine runaway authoring commits beyond budget STILL trips.

    Returns the merge-excluded count, or ``None`` on a degraded git read / no
    begin sha (caller disables signal (b) on None — never a false positive,
    never a crash). Mirrors the pre-existing best-effort contract of the inline
    count it replaces.
    """
    from .runtimeplane import _git  # deferred (runtime/git plane; function-local avoids import cycle)
    if not begin_head_sha:
        return None
    try:
        count_proc = _git(
            repo_root, "rev-list", "--count", "--no-merges",
            f"{begin_head_sha}..HEAD",
        )
        if count_proc.returncode != 0:
            return None
        return int((count_proc.stdout or "").strip() or "0")
    except Exception:  # noqa: BLE001  (incl. ValueError from int())
        return None


def cycle_end_friction_check(repo_root: Path | None = None) -> dict | None:
    """--cycle-end I/O wiring (hardening-blind-to-process-friction Phase 2 / D1).

    Called by the ``--cycle-end`` handler in BOTH state machines (lazy-state.py
    and bug-state.py) BEFORE it clears the cycle marker. It:
      1. reads the cycle marker (the --cycle-begin snapshot); a missing/partial
         marker → None no-op (the bracket was never armed or already cleared);
      2. resolves the CURRENT run identity (``read_run_marker().started_at``,
         None when no run marker is live) and the CURRENT HEAD sha;
      3. computes how many AUTHORED (merge-excluded) commits HEAD advanced since
         the snapshotted ``begin_head_sha``
         (``git rev-list --count --no-merges <begin>..HEAD`` via
         ``_count_authored_commits_since`` — Round 42: a merge commit is a
         branch-integration artifact, not authored work, so it must not count
         toward the per-cycle commit budget);
      4. calls the pure detect_cycle_bracket_friction(...);
      5. on a non-None descriptor, appends a kind: process-friction entry to the
         deny ledger via append_friction_ledger_entry(...).

    Every git/marker read is best-effort: a degraded input (no git tree, no run
    marker, unreadable marker) yields None signals, never a false positive and
    never a crash — the --cycle-end clear must always proceed.

    Args:
        repo_root: the repo to resolve HEAD / commit-count against. Defaults to
            cwd. Degrades to no-commit-signal when not a git tree.

    Returns:
        The friction descriptor that was logged, or None when the bracket was
        clean / inputs were degraded / no marker was present.
    """
    marker = read_cycle_marker()
    if not isinstance(marker, dict):
        return None

    # (2) current run identity — None when no run marker is live (the torn-bracket
    # signal). read_run_marker swallows its own errors and returns None.
    try:
        live_run = read_run_marker()
    except Exception:  # noqa: BLE001
        live_run = None
    current_run_started_at = (live_run or {}).get("started_at")

    # (2/3) current HEAD + commits-since-begin — best-effort git reads.
    # commits_since EXCLUDES merge commits (Round 42): the budget side models
    # authored work-unit commits, so the count side must too — a merge commit (e.g. a
    # sibling PR integrated into main during the cycle window) is a branch-integration
    # artifact with no authored work and must not count toward the runaway budget.
    # _count_authored_commits_since carries the full provenance + best-effort contract.
    root = (repo_root or Path.cwd())
    begin_head_sha = marker.get("begin_head_sha")
    current_head_sha = head_sha_snapshot(root)
    commits_since: int | None = _count_authored_commits_since(root, begin_head_sha)

    # (4) recover the dispatched sub_skill from the marker (--cycle-begin persists
    # it) so the unexpected-commits detector selects the CORRECT per-sub_skill
    # commit budget. A legacy/partial marker without the field reads None → the
    # detector falls back to the conservative default budget (never a crash). The
    # bracket-break signal is sub_skill-independent and was always fully covered;
    # this fix stops the unexpected-commits signal from false-positiving on a
    # normal multi-commit cycle (e.g. execute-plan test+impl, budget 3) that the
    # forced sub_skill=None previously squeezed under the default budget of 1.
    marker_sub_skill = marker.get("sub_skill")

    # hardening Round 20 (D2): for an execute-plan cycle, scale the commit budget
    # by the plan part's declared phase count. /execute-plan commits once per phase
    # (the standard per-phase gate+commit cadence), so a legitimate N-phase single-
    # part plan makes ~N commits — which the fixed table budget of 3 false-positived
    # as unexpected-commits on any plan with 4+ phases. The plan part path is the
    # dispatched sub_skill_args (lazy-state.py routes execute-plan with
    # sub_skill_args=str(plan)). Read the phase count via the existing
    # _plan_phase_set helper and allow one commit per phase plus a small slack for
    # the test+impl split within a phase. A genuine runaway (many commits beyond the
    # plan's phase count) still trips. Best-effort: an unreadable plan / no phases:
    # field / non-execute-plan cycle → None → the detector falls back to the fixed
    # per-sub_skill table (never a false NEGATIVE, never a crash).
    budget_override = _execute_plan_commit_budget(marker_sub_skill, marker.get("sub_skill_args"))

    # (4b) branch-divergence inputs (harden Round 43): the live branch at --cycle-end
    # vs the run's work_branch. Both best-effort — a None on either degrades the
    # signal to off (never a false positive). expected_work_branch comes from the
    # LIVE run marker (read in step 2); a legacy run marker without the field → None.
    current_branch = current_branch_snapshot(root)
    expected_work_branch = (live_run or {}).get("work_branch")

    descriptor = detect_cycle_bracket_friction(
        marker,
        current_run_started_at=current_run_started_at,
        current_head_sha=current_head_sha,
        sub_skill=marker_sub_skill,
        commits_since=commits_since,
        budget_override=budget_override,
        current_branch=current_branch,
        expected_work_branch=expected_work_branch,
        repo_root=root,
    )

    # (5) log the friction as hardening debt (fail-open).
    if descriptor is not None:
        append_friction_ledger_entry(
            descriptor.get("reason", ""),
            descriptor.get("detail", ""),
        )
    return descriptor


# ---------------------------------------------------------------------------
# Refuse-by-construction (lazy-cycle-containment C3 / Phase 3; agent_id-aware
# per hardening-blind-to-process-friction Phase 1 / D4)
#
# The orchestrator-only state-script operations REFUSE for a subagent caller —
# the belt-and-suspenders backstop if the C2 hook (lazy-cycle-containment.sh) is
# disabled or bypassed. The subagent-vs-main-thread distinction is established
# in PRIORITY ORDER (D4):
#
#   1. LAZY_ORCHESTRATOR truthy in the env → NEVER refuse (the main-thread
#      orchestrator asserts its identity). This makes the orchestrator
#      STRUCTURALLY IMMUNE to a stale/lingering cycle marker — the
#      Proven-Finding-#3 self-deny defect cannot recur even if a prior dispatch
#      crashed without --cycle-end.
#   2. LAZY_CYCLE_SUBAGENT truthy in the env → REFUSE. This is the explicit
#      subagent-context signal a dispatch may set; it does not depend on the
#      marker being armed.
#   3. Otherwise fall back to the cycle MARKER as the carrier: marker present →
#      REFUSE (the legacy backstop, retained per D4's final clause). A subagent
#      running mid-dispatch sees the orchestrator's marker; the orchestrator's
#      correct flow (set marker → dispatch → clear marker → THEN run these ops)
#      means the marker is cleared when the orchestrator reaches them.
#
# Why the env var matters (D4): a Python subprocess (lazy-state.py called from a
# subagent's Bash) CANNOT read the PreToolUse `agent_id` field — that is
# hook-input-only and does not propagate to subprocess env. So C3's reachable
# subagent signal is the env var (preferred) + the marker (fallback carrier),
# NOT agent_id. The C2 hook uses agent_id directly (it runs in the hook
# pipeline where the field IS present); C3 is the script-side backstop using the
# reachable signals. The deny SCOPE (which ops) stays in lockstep across both.
#
# CYCLE_REFUSED_OPS MUST stay in lockstep with the C2 hook's loop-formation /
# lifecycle deny-set (the agent_id trip in lazy-cycle-containment.sh:
# /lazy* Skill invocations, nested /lazy-batch, the LOOP_FORMATION_FLAGS
# routing flags, and dev:kill/dev:restart; recursive Agent/Task dispatch was
# REMOVED from the C2 deny set 2026-07-09 — the harness allows nested dispatch
# and the deny broke mandated read-only Explore fan-outs, see
# docs/bugs/adhoc-containment-denies-mandated-explore-fanout) — they are
# intentionally redundant defense-in-depth. A divergence is a coverage hole. The
# allow-listed ops a legitimately-dispatched subagent needs
# (`--neutralize-sentinel`, `--verify-ledger`) and all read/probe ops are
# deliberately NOT in this set.
#
# NOTE (cycle-subagent-runs-orchestrator-work Phase 2, KEYSTONE): `--cycle-end`
# and `--cycle-begin` are deliberately NOT added to CYCLE_REFUSED_OPS. Members of
# this set use the plain marker-fallback (refuse anyone-with-a-marker), which the
# orchestrator's own --cycle-end/--cycle-begin cannot tolerate — those run WHILE
# the orchestrator's marker is present. They are instead guarded by the dedicated
# `refuse_cycle_marker_mutation_if_subagent`, which keys on the POSITIVE
# LAZY_ORCHESTRATOR signal (orchestrator allowed under a live marker; subagent
# refused). The C2/C3 deny SCOPE still matches: the C2 hook adds --cycle-end /
# --cycle-begin to LOOP_FORMATION_FLAGS (agent_id trip), so a subagent cannot
# clear/arm the marker at EITHER layer. Keep the two in lockstep.
# ---------------------------------------------------------------------------

CYCLE_REFUSED_OPS: frozenset[str] = frozenset({
    "--run-end",
    "--run-start",
    "--apply-pseudo",
    "--enqueue-adhoc",
    "--emit-dispatch",
})

# dispatched-harden-record-intervention-refused-by-containment: cycle-marker
# ``sub_skill`` values that identify a dispatched harness-hardening subagent. A
# hardening dispatch (``dispatch.DISPATCH_CLASSES`` tag "hardening", emitted via
# ``--emit-dispatch hardening``) is bracketed ``--cycle-begin --kind meta
# --sub-skill hardening`` (coupled-trio §1d.1), so the cycle marker records
# ``sub_skill == "hardening"`` for a live /harden-harness cycle. The narrow
# ``--record-intervention`` containment exemption below keys on this set: a
# dispatched harden's SKILL contract MANDATES recording its round as a
# hypothesis-ledger intervention with a measurable target_signal, and
# ``--record-intervention`` is capture-only telemetry (it writes
# ``docs/interventions/<id>.md`` — no run-marker/registry/queue mutation), NOT a
# run-lifecycle op, so permitting it for a hardening subagent does not open any
# loop-formation surface (the genuinely-dangerous ops stay refused).
_HARDENING_CYCLE_SUBSKILLS: frozenset[str] = frozenset({"hardening"})


def _cycle_marker_is_hardening(marker: "dict | None") -> bool:
    """True iff *marker* is a live cycle marker for a dispatched hardening cycle.

    Keyed on the marker's own ``sub_skill`` (stamped at ``--cycle-begin``), so it
    cannot be spoofed by a runaway's environment — only the orchestrator writes the
    cycle marker. A missing/None marker or a non-hardening ``sub_skill`` → False.
    """
    if not isinstance(marker, dict):
        return False
    return str(marker.get("sub_skill") or "").strip() in _HARDENING_CYCLE_SUBSKILLS


def _env_truthy(name: str) -> bool:
    """Return True when env var *name* is set to a non-empty, non-falsey value.

    Treats "", "0", "false", "no", "off" (case-insensitive) as false so a
    deliberately-cleared var doesn't read as set.
    """
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def refuse_if_cycle_active(
    op_name: str, *, allow_hardening_subagent: bool = False
) -> None:
    """Refuse an orchestrator-only op when the caller is a cycle subagent (D4).

    Invoked at the ENTRY of each guarded CLI handler (`--run-end`, `--run-start`,
    `--apply-pseudo`, `--enqueue-adhoc`, `--emit-dispatch`) in lazy-state.py and
    bug-state.py, BEFORE any side effect (marker write/delete, queue mutation,
    prompt emission) so a refused op leaves state untouched.

    Subagent-vs-main-thread is decided in priority order (see the module comment
    above CYCLE_REFUSED_OPS):
      1. LAZY_ORCHESTRATOR truthy → return silently (never refuse the orchestrator,
         even with a stale marker present — structural immunity to the self-deny
         defect).
      2. LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal).
      3. else cycle marker present → refuse (legacy backstop carrier).
    A refusal prints a corrective message to stderr and exits 3 with ZERO side
    effects.

    Args:
        op_name: the CLI flag being guarded (e.g. "--run-end"). Echoed in the
                 corrective message so the subagent sees exactly what it tried.
        allow_hardening_subagent: when True, a dispatched HARDENING cycle subagent
                 (the cycle marker's ``sub_skill`` is a hardening class) is PERMITTED
                 this op instead of refused. Passed ONLY by the ``--record-intervention``
                 handler (dispatched-harden-record-intervention-refused-by-containment):
                 the /harden-harness SKILL MANDATES a dispatched harden record its
                 round as a hypothesis-ledger intervention with a measurable
                 target_signal, and ``--record-intervention`` is capture-only
                 telemetry (writes ``docs/interventions/<id>.md`` — no
                 run-marker/registry/queue mutation), so it opens no loop-formation
                 surface. The genuinely-dangerous lifecycle ops
                 (``--run-end`` / ``--run-start`` / ``--emit-dispatch`` /
                 ``--apply-pseudo`` / ``--enqueue-adhoc``) DEFAULT this to False and
                 stay refused for ANY cycle subagent, hardening or not.
    """
    # 1. The main-thread orchestrator asserts its identity → never self-refuse,
    #    even if a stale marker lingers from a crashed prior dispatch.
    #    cycle-subagent-runs-orchestrator-work Phase 1 (2026-06-16): this branch
    #    was READ-but-never-SET until the three orchestrators (lazy-batch,
    #    lazy-bug-batch, lazy-batch-cloud) began `export LAZY_ORCHESTRATOR=1` at
    #    their Step 0.55 run-start. Until then containment degraded to the
    #    deletable marker (the absence of any positive orchestrator signal). The
    #    export is now the load-bearing positive carrier; this guard's immunity
    #    actually fires for the real orchestrator.
    if _env_truthy("LAZY_ORCHESTRATOR"):
        return

    # 2/3. Explicit subagent signal, else the marker as the fallback carrier.
    explicit_subagent = _env_truthy("LAZY_CYCLE_SUBAGENT")
    marker = read_cycle_marker()
    if not explicit_subagent and marker is None:
        return

    # dispatched-harden-record-intervention-refused-by-containment: a dispatched
    # HARDENING cycle subagent may record its own intervention (capture-only
    # telemetry — the one op its SKILL contract requires). Keyed on the marker's
    # own ``sub_skill`` (orchestrator-written; unspoofable by a runaway's env), so
    # ONLY a real /harden-harness cycle is exempted, and ONLY for the op that
    # passes allow_hardening_subagent (``--record-intervention``). Every other op
    # keeps its default (allow_hardening_subagent=False) → still refused. This is
    # checked AFTER the subagent-identity gate above so a non-subagent path is
    # never reached here.
    if allow_hardening_subagent and _cycle_marker_is_hardening(marker):
        return

    feature_id = (marker or {}).get("feature_id", "<unknown>")
    # harness-telemetry-ledger Phase 2 (D4-B): record the containment trip AFTER
    # the refusal decision, BEFORE exit. The append-only ledger line is
    # observability, not state — the refused op still has ZERO state side
    # effects (same standing the deny ledger has at guard-deny time).
    # Marker-gated (non-destructive read) + fail-open inside the emitter.
    append_telemetry_event(
        "containment-refusal",
        item_id=(marker or {}).get("feature_id"),
        data={"op": op_name, "guard": "refuse_if_cycle_active"},
    )
    sys.stderr.write(
        f"REFUSED: `{op_name}` is an orchestrator-only operation and you are a "
        f"single cycle subagent (the lazy-cycle-active marker is present for "
        f"feature '{feature_id}'). STOP after your commit + push + report — "
        f"routing the next cycle, lifecycle teardown ({op_name}), enqueuing, and "
        f"completion are the orchestrator's job. This op was refused with zero "
        f"side effects.\n"
    )
    sys.exit(3)


def refuse_cycle_marker_mutation_if_subagent(op_name: str) -> None:
    """Refuse a cycle-MARKER MUTATION op (``--cycle-end`` / ``--cycle-begin``) for
    a subagent caller (cycle-subagent-runs-orchestrator-work Phase 2, KEYSTONE).

    Invoked at the ENTRY of the ``--cycle-end`` / ``--cycle-begin`` handlers in
    lazy-state.py and bug-state.py, BEFORE ``cycle_end_friction_check`` /
    ``clear_cycle_marker`` / ``write_cycle_marker`` — so a refused op leaves the
    marker file untouched (zero side effects).

    WHY THIS IS A SEPARATE GUARD (not ``refuse_if_cycle_active`` / not in
    ``CYCLE_REFUSED_OPS``): the ops in ``CYCLE_REFUSED_OPS`` use the plain
    marker-fallback (refuse anyone-with-a-marker), which is correct for them
    because the orchestrator's correct flow has the marker CLEARED when it runs
    them. But ``--cycle-end`` / ``--cycle-begin`` are exactly the ops the
    orchestrator runs WHILE its own marker is present (begin arms it, end clears
    it). Reusing the plain marker-fallback would refuse the orchestrator's own
    legitimate bracket and wedge the pipeline. So this guard keys on the POSITIVE
    ``LAZY_ORCHESTRATOR`` signal instead — that is why Phase 1 (the export) is a
    HARD prerequisite. The deny SCOPE still matches the C2 hook (a subagent cannot
    clear/arm the marker).

    Decided in priority order:
      1. LAZY_ORCHESTRATOR truthy → return silently (the orchestrator owns the
         bracket; allowed to clear/arm under its own live marker).
      2. else LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal).
      3. else cycle marker present (no orchestrator env) → refuse (the reachable
         subagent-context signal: a subagent mid-dispatch sees the orchestrator's
         marker but never inherits the LAZY_ORCHESTRATOR export).
      4. else (no marker, no subagent env) → return silently (the genuinely
         uncontained main-thread case with no marker armed yet — e.g. the very
         first ``--cycle-begin`` of a run before any marker exists).
    A refusal prints a corrective message to stderr and exits 3 with ZERO side
    effects (the marker is NOT mutated).

    Args:
        op_name: the CLI flag being guarded ("--cycle-end" | "--cycle-begin").
    """
    # 1. The orchestrator asserts its identity → never refuse its own bracket.
    if _env_truthy("LAZY_ORCHESTRATOR"):
        return

    # 2/3. Explicit subagent signal, else marker-present-without-orchestrator-env.
    explicit_subagent = _env_truthy("LAZY_CYCLE_SUBAGENT")
    marker = read_cycle_marker()
    if not explicit_subagent and marker is None:
        # 4. No subagent env AND no marker → genuinely uncontained main thread.
        return

    feature_id = (marker or {}).get("feature_id", "<unknown>")
    # harness-telemetry-ledger Phase 2 (D4-B): observability-only ledger line
    # (see refuse_if_cycle_active) — zero STATE side effects preserved.
    append_telemetry_event(
        "containment-refusal",
        item_id=(marker or {}).get("feature_id"),
        data={"op": op_name, "guard": "refuse_cycle_marker_mutation_if_subagent"},
    )
    sys.stderr.write(
        f"REFUSED: `{op_name}` mutates the cycle-containment marker and is an "
        f"orchestrator-only operation — you are a single cycle subagent (the "
        f"lazy-cycle-active marker is present for feature '{feature_id}'). A "
        f"subagent must NOT clear or re-arm the containment marker: clearing it "
        f"un-arms every downstream guard at once. STOP after your commit + push "
        f"+ report — the cycle bracket ({op_name}) is the orchestrator's job. "
        f"This op was refused with zero side effects (the marker is untouched).\n"
    )
    sys.exit(3)


def refuse_run_start_clobber(incoming_pipeline: str, *, now: float | None = None) -> None:
    """Refuse a ``--run-start`` that would CLOBBER a live run marker owned by a
    DIFFERENT pipeline (hardening-blind-to-process-friction, 2026-06-16 D-B).

    Invoked at the ENTRY of each ``--run-start`` handler (lazy-state.py pipeline
    "feature" / bug-state.py pipeline "bug"), AFTER ``refuse_if_cycle_active`` and
    BEFORE ``write_run_marker`` — so a refused clobber leaves the existing marker
    and all registry/counter state untouched.

    THE DEFECT THIS CLOSES: a nested ``/lazy`` (feature) dispatched mid-run ran
    ``lazy-state.py --run-start`` and ``write_run_marker`` UNCONDITIONALLY
    overwrote the ACTIVE bug run marker (pipeline:bug session X → pipeline:feature
    session Y).  That silently re-pointed the run identity, breaking the
    validate-deny / ack guard for the real orchestrator session — the bug run's
    hardening debt could never ack because its marker no longer existed.

    DISCRIMINATOR (why pipeline, not session_id): at ``--run-start`` the INCOMING
    run has no session_id yet — ``write_run_marker`` writes it bind-pending
    (None), to be stamped by the inject hook on first firing.  So an incoming-vs-
    existing session_id compare is impossible here.  The robust, mechanical
    discriminator is the PIPELINE field: a feature ``--run-start`` clobbering a
    live ``bug`` marker (or vice versa) is exactly the D-B signature and is ALWAYS
    a cross-run accident → refused.

    SAME-pipeline arbitration is CHECKPOINT-DISCRIMINATED
    (concurrent-same-branch-walkers-no-arbitration, 2026-06-20).  A same-pipeline
    re-``--run-start`` is NOT unconditionally a resume: a genuinely-concurrent
    SECOND walker on the same repo+branch+pipeline is also same-pipeline and would
    silently clobber the first walker's live marker (the residual gap left open by
    ``multi-repo-concurrent-runs``).  The discriminator is the presence of
    ``lazy-run-checkpoint.json`` on disk: a legitimate checkpoint-resume always
    carries that file (written by ``--run-end --reason checkpoint``, consumed by
    the handler's own ``consume_run_checkpoint()`` LATER), whereas a fresh second
    walker has none.  So:
      - same-pipeline + checkpoint file PRESENT  → ALLOW overwrite (sanctioned
        resume — the resume path restores its own counters).
      - same-pipeline + checkpoint file ABSENT (marker live + age-fresh)  → REFUSE
        (exit 3, zero side effects), naming the in-flight run.
    The checkpoint read here is NON-DESTRUCTIVE — an existence check ONLY, NEVER
    ``consume_run_checkpoint()`` (which deletes the resume signal the ``--run-start``
    handler legitimately consumes at a LATER step).

    Reads the marker file RAW (not via ``read_run_marker``) so the session-id
    staleness path (path B, which returns None for a non-owner caller and would
    hide the very marker we must protect) cannot mask the live owner.  Only the
    24h AGE staleness is honored: a marker older than ``_MARKER_STALE_SECONDS`` is
    a presumed-dead crashed run and may be freely overwritten (no refusal).

    Fail-open: a missing / unreadable / corrupt / unparseable marker, or a marker
    with no/blank pipeline field, never refuses — only an age-fresh, well-formed,
    DIFFERENT-pipeline marker triggers the exit-3 refusal.

    Args:
        incoming_pipeline: the pipeline of the run being started ("feature" |
            "bug").
        now: epoch float for age comparison (injectable for hermetic tests;
            defaults to time.time()).
    """
    if now is None:
        now = time.time()
    marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
    if not marker_path.exists():
        return
    try:
        existing = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            return  # corrupt root → fail-open (write_run_marker will overwrite)
    except (OSError, json.JSONDecodeError):
        return  # unreadable / unparseable → fail-open

    # Age staleness: a >24h-old marker is a presumed-dead crashed run — overwriting
    # it is the documented recovery (mirrors read_run_marker path A), so do NOT
    # refuse.  Any parse failure on started_at degrades to "not age-stale" so we
    # err toward protecting a live marker (conservative).
    started_at_str = existing.get("started_at", "")
    try:
        started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
        started_epoch = (started_dt - datetime.datetime(1970, 1, 1)).total_seconds()
    except (ValueError, TypeError):
        started_epoch = now  # unparseable → treat as fresh (protect, don't clobber)
    if now - started_epoch > _MARKER_STALE_SECONDS:
        return  # presumed-dead crashed run → safe to overwrite, no refusal

    existing_pipeline = (existing.get("pipeline") or "").strip()
    if not existing_pipeline:
        return  # no pipeline field → fail-open
    if existing_pipeline == incoming_pipeline:
        # Same-pipeline arbitration is checkpoint-discriminated: a sanctioned
        # checkpoint-resume carries lazy-run-checkpoint.json (read existence-only,
        # NON-destructively — NEVER consume_run_checkpoint, which deletes the
        # resume signal the --run-start handler consumes at a later step).
        checkpoint_present = (
            claude_state_dir(create=False) / _CHECKPOINT_FILENAME
        ).exists()
        if checkpoint_present:
            return  # same-pipeline checkpoint-resume → allow overwrite
        # Live, age-fresh, same-pipeline marker WITHOUT a checkpoint → a genuinely-
        # concurrent SECOND walker on this repo+branch+pipeline → refuse the clobber.
        existing_session = existing.get("session_id")
        forward_cycles = existing.get("forward_cycles")
        # harness-telemetry-ledger Phase 2 (D4-B): observability-only ledger
        # line, attributed to the LIVE run being protected (its marker supplies
        # the run identity). Zero STATE side effects preserved.
        append_telemetry_event(
            "containment-refusal",
            data={"op": "--run-start", "guard": "refuse_run_start_clobber",
                  "incoming_pipeline": incoming_pipeline},
            now=now,
        )
        sys.stderr.write(
            f"REFUSED: `--run-start` (pipeline={incoming_pipeline!r}) would CLOBBER "
            f"an ACTIVE run marker for the SAME pipeline with NO checkpoint waiting "
            f"(pipeline={existing_pipeline!r}, session_id={existing_session!r}, "
            f"started_at={started_at_str!r}, forward_cycles={forward_cycles!r}). A "
            f"second autonomous walker is already live on this same repo + branch + "
            f"pipeline — overwriting its marker would leave both walkers running with "
            f"no arbitration (collisions on feature selection and push ordering "
            f"surface mid-run). STOP and do NOT start a second {incoming_pipeline} "
            f"walker here. If the in-flight run is genuinely dead, end it first "
            f"(`--run-end`) from its own orchestrator; a legitimate checkpoint-resume "
            f"would carry lazy-run-checkpoint.json (absent here). This op was refused "
            f"with ZERO side effects (the existing marker is untouched).\n"
        )
        sys.exit(3)

    # Live, well-formed, DIFFERENT-pipeline marker → refuse the clobber.
    existing_session = existing.get("session_id")
    # harness-telemetry-ledger Phase 2 (D4-B): observability-only ledger line
    # (see the same-pipeline branch above). Zero STATE side effects preserved.
    append_telemetry_event(
        "containment-refusal",
        data={"op": "--run-start", "guard": "refuse_run_start_clobber",
              "incoming_pipeline": incoming_pipeline},
        now=now,
    )
    sys.stderr.write(
        f"REFUSED: `--run-start` (pipeline={incoming_pipeline!r}) would CLOBBER an "
        f"ACTIVE run marker owned by a DIFFERENT pipeline "
        f"(pipeline={existing_pipeline!r}, session_id={existing_session!r}, "
        f"started_at={started_at_str!r}). Overwriting it silently re-points the run "
        f"identity and breaks the validate-deny/ack guard for the live "
        f"{existing_pipeline} orchestrator (the D-B clobber). This is almost always "
        f"a nested/off-task pipeline dispatched inside another run — STOP and do "
        f"NOT start a {incoming_pipeline} run here. If the {existing_pipeline} run is "
        f"genuinely dead, end it first (`--run-end`) from its own orchestrator. This "
        f"op was refused with ZERO side effects (the existing marker is untouched).\n"
    )
    sys.exit(3)


# ---------------------------------------------------------------------------
# Script-persisted run counters
# ---------------------------------------------------------------------------

def fold_run_counters(
    forward_flag: int | None,
    meta_flag: int | None,
    marker: dict | None,
) -> tuple[int | None, int | None]:
    """Fold explicit CLI flags with marker-persisted counters.

    Priority: explicit flag wins over marker value wins over None.
    When both a flag and a marker value exist, the flag wins (backward compat:
    callers that pass --forward-cycles / --meta-cycles explicitly still get
    exactly those values; the marker fill-in is only for the post-compaction
    case where the flags are absent).

    Returns:
        (forward_cycles, meta_cycles) tuple where each element is:
          - the explicit flag value when it is not None, else
          - the marker's persisted value when marker is not None, else
          - None (no flag, no marker)
    """
    if marker is not None:
        # Marker exists: use its stored counters as fallback for absent flags.
        forward = (
            forward_flag
            if forward_flag is not None
            else marker.get("forward_cycles")
        )
        meta = (
            meta_flag
            if meta_flag is not None
            else marker.get("meta_cycles")
        )
    else:
        # No marker: only use explicit flag values; absent flags stay None.
        forward = forward_flag
        meta = meta_flag
    return (forward, meta)


def fold_max_cycles(
    max_cycles_flag: "int | None",
    marker: dict | None,
) -> "int | None":
    """Resolve the effective ``max_cycles`` for the cycle header / budget cap.

    lazy-batch-no-mid-run-budget-or-park-controls: the MARKER is the authoritative
    live budget. When a marker is present, its persisted ``max_cycles`` wins — so a
    mid-run ``--set-max-cycles N`` update is reflected in the header immediately,
    WITHOUT the orchestrator re-passing ``--max-cycles`` (the old cosmetic
    workaround left the marker stale while the header diverged). Note the ASYMMETRY
    with ``fold_run_counters`` (where the explicit flag wins): the counters are the
    live truth an orchestrator supplies each probe, whereas the budget is
    run-scoped state OWNED by the marker and mutated only via ``--set-max-cycles``.
    At ``--run-start`` the marker's ``max_cycles`` is seeded from ``--max-cycles``,
    so the two agree until an explicit mid-run change — exactly the intent.

    Priority:
      - marker present → the marker's ``max_cycles`` (may be None for an unbounded
        run — respected as-is), else
      - no marker → the explicit ``--max-cycles`` flag (may be None).

    Args:
        max_cycles_flag: the explicit ``--max-cycles`` CLI value (or None).
        marker: the active run marker (or None).

    Returns:
        The effective max_cycles (int or None).
    """
    if marker is not None:
        # ``max_cycles`` is an original marker field (never legacy-absent), so a
        # plain .get is safe; None means an unbounded run and is respected.
        return marker.get("max_cycles")
    return max_cycles_flag


def fold_park_flags(
    needs_input_flag: bool,
    blocked_flag: bool,
    provisional_flag: bool,
    marker: dict | None,
) -> "tuple[bool, bool, bool]":
    """Resolve the effective park state for the probe (marker-authoritative).

    lazy-batch-no-mid-run-budget-or-park-controls: park mode is RUN-SCOPED state
    persisted in the marker, so a live run's probe reads the MARKER each cycle —
    letting an operator toggle park mid-run via ``--set-park`` /
    ``--set-park-provisional``. Priority (mirrors the byte-identity discipline):

      - NEW-SCHEMA marker present (carries the ``park_needs_input`` key, seeded at
        run-start from the invocation flags) → the marker is AUTHORITATIVE. A
        mid-run ``--set-park off`` then disables park even though the orchestrator
        may still pass the invocation ``--park-*`` flags (marker wins).
      - No marker, OR a LEGACY marker lacking the fields (an in-flight run started
        before this change) → fall back to the CLI flags (back-compat: an
        in-flight ``--park`` run keeps parking; a no-marker probe is byte-identical
        to the pre-feature baseline).

    Args:
        needs_input_flag: the ``--park-needs-input`` CLI value.
        blocked_flag: the ``--park-blocked`` CLI value.
        provisional_flag: the ``--park-provisional`` CLI value.
        marker: the active run marker (or None).

    Returns:
        ``(park_needs_input, park_blocked, park_provisional)`` bools.
    """
    if marker is not None and "park_needs_input" in marker:
        return (
            bool(marker.get("park_needs_input")),
            bool(marker.get("park_blocked")),
            bool(marker.get("park_provisional")),
        )
    return (bool(needs_input_flag), bool(blocked_flag), bool(provisional_flag))


def _bump_per_feature_forward(marker: dict, feature_id) -> None:
    """Increment ``marker["per_feature_forward_cycles"][feature_id]`` by 1, in
    place, as a SIBLING write inside whichever forward-advance mutation is already
    underway (feature-budget-guard-and-skip-ahead Phase 1).

    Called ONLY from the forward branch of ``advance_run_counters`` /
    ``advance_forward_cycle`` — so the per-feature increment rides the EXACT same
    forward-vs-meta gate as the run-level ``forward_cycles`` (no second oracle;
    meta-only advances never reach here). Legacy-tolerant: a marker lacking the key
    (a run resumed from a pre-feature marker) defaults to ``{}`` and never
    KeyErrors. A falsy/None ``feature_id`` is a no-op (no spurious key).
    """
    if not feature_id:
        return
    per_feature = marker.get("per_feature_forward_cycles")
    if not isinstance(per_feature, dict):
        per_feature = {}
    key = str(feature_id)
    per_feature[key] = int(per_feature.get(key, 0)) + 1
    marker["per_feature_forward_cycles"] = per_feature


def compute_per_feature_ceiling(
    max_cycles: int,
    ready_queue_depth: int,
    override: int | None = None,
) -> int | None:
    """Per-feature forward-cycle ceiling L_task — **OFF by default**
    (per-feature-cycle-cap-defers-incomplete-work Phase 1).

    The per-feature budget guard is DISABLED by default. With no ``override``
    (the default ``/lazy-batch`` path), this returns ``None`` — and the entire
    marker+ceiling-gated budget block in ``lazy-state.py`` short-circuits on
    ``_bg_ceiling is None`` (the trip gate is ``if _bg_marker is not None and
    _bg_ceiling is not None:``). So by default the whole-run ``max_cycles`` is the
    SOLE budget; no single feature is ever deferred/evicted for cycle-count
    monopolization. This reverses the prior default-on dynamic ceiling, which
    deferred incomplete work mid-flight instead of completing it.

    When ``override`` is supplied (the ``--per-feature-cycle-cap <N>`` path — the
    OFF-by-default OPT-IN) it is returned VERBATIM, re-arming a fixed ceiling
    ``N`` — including a deliberate ``0`` (a falsy-but-not-None cap). Only the
    opt-in re-arms the trip/defer/evict/grace/flush machinery, which is otherwise
    fully retained and unmodified; it is simply never reached by default.

    Pure + side-effect-free for direct characterization in ``test_lazy_core.py``.

    Args:
        max_cycles: the run's whole-run budget (``C_global`` / marker ``max_cycles``).
            Unused on the default-off path; retained for the stable call signature.
        ready_queue_depth: count of ready queue features. Likewise unused by default.
        override: a fixed ceiling that re-arms the guard (``None`` ⇒ OFF, return None).

    Returns:
        ``None`` by default (guard off); the ``override`` int verbatim when supplied.
    """
    if override is not None:
        return int(override)
    # Default-off: no override ⇒ the guard does not arm. Return None so the
    # ceiling-gated budget block in lazy-state.py short-circuits entirely. The
    # whole-run max_cycles is the only default budget; --per-feature-cycle-cap
    # <N> is the opt-in that re-arms a fixed ceiling.
    return None


def read_per_feature_forward_cycles(marker: dict | None) -> dict:
    """Read helper exposing the ``per_feature_forward_cycles`` map from a marker
    (feature-budget-guard-and-skip-ahead Phase 1).

    Returns the map (a ``{feature_id: int}`` dict) or ``{}`` when the marker is
    None or lacks the key (legacy tolerance). The Phase-2 trip evaluation and the
    probe path read the per-feature counts through here so the ``{}``-default lives
    in exactly one place.
    """
    if not isinstance(marker, dict):
        return {}
    value = marker.get("per_feature_forward_cycles")
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# budget-guard-defers-near-complete-feature Phase 1 — near-completion predicate
#   + corrective-cycle accounting + composite trip-signal evaluator.
#
# These four pure/near-pure helpers are wired into the trip site (Phase 2) and
# the end-of-run flush (Phase 3). They land first with direct red→green
# fixtures in test_lazy_core.py — no run marker / state-machine wiring needed to
# characterize them.
# ---------------------------------------------------------------------------


def feature_is_near_complete(feature_dir, repo_root=None) -> bool:
    """True iff a feature is within one validation cycle of done — the SAME
    "ready to validate" definition the mid-feature gate uses to fall through to
    the Step-9 ``/mcp-test``:

      - ``PHASES.md`` is present AND ``remaining_unchecked_are_verification_only``
        is True (every still-unchecked ``- [ ]`` row is a verification-only row
        owned by the runtime gate), AND
      - at least one ``plans/*.md`` part carries ``status: Complete``
        (implementation has fully landed), AND
      - no ``BLOCKED.md`` on disk (a blocker is not near-complete).

    Reuses ``remaining_unchecked_are_verification_only`` for the verification
    check (no re-implementation) so "near-complete" == the existing predicate.
    Tolerant of EVERY missing input — a missing PHASES.md, missing plans dir, or
    a nonexistent feature dir returns False and NEVER raises (the grace gate must
    fail safe toward "not near-complete" / no grace).

    ``repo_root`` is accepted for call-site symmetry with the other budget
    helpers but is not needed (everything is read relative to ``feature_dir``).
    """
    try:
        feat = Path(feature_dir)
    except (TypeError, ValueError):
        return False
    try:
        if (feat / "BLOCKED.md").exists():
            return False
        phases_md = feat / "PHASES.md"
        if not phases_md.exists():
            return False
        phases_text = phases_md.read_text(encoding="utf-8")
        if not remaining_unchecked_are_verification_only(phases_text):
            return False
        plans_dir = feat / "plans"
        if not plans_dir.is_dir():
            return False
        for plan_path in sorted(plans_dir.glob("*.md")):
            try:
                text = plan_path.read_text(encoding="utf-8")
            except OSError:
                continue
            # status lives in the frontmatter; a simple line scan suffices (the
            # frontmatter is the first block, and "status: Complete" is unique to
            # a completed plan part).
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("status:"):
                    value = stripped.split(":", 1)[1].strip()
                    if value == "Complete":
                        return True
                    break  # first status: line per file is authoritative
        return False
    except OSError:
        return False


def count_validation_corrective_cycles(marker, feature_id) -> int:
    """Read-only count of forward cycles attributable to validation-driven
    corrective work for ``feature_id``, read from the run-marker sub-map
    ``per_feature_corrective_cycles: {feature_id: int}``.

    Legacy/absent map ⇒ 0 (same tolerance pattern as
    ``read_per_feature_forward_cycles``). A None/non-dict marker, a missing key,
    or a non-int value all collapse to 0 — the discount never raises and never
    inflates the trip count.
    """
    if not isinstance(marker, dict):
        return 0
    per_feature = marker.get("per_feature_corrective_cycles")
    if not isinstance(per_feature, dict):
        return 0
    try:
        return int(per_feature.get(str(feature_id), 0) or 0)
    except (TypeError, ValueError):
        return 0


def record_corrective_cycle(marker: dict, feature_id) -> dict:
    """Increment ``marker["per_feature_corrective_cycles"][feature_id]`` by 1, in
    place, mirroring ``_bump_per_feature_forward``'s shape.

    Called at the apply-resolution / corrective-phase dispatch bracket (wired in
    Phase 2) so a validation-failure-driven corrective dispatch is counted as
    corrective and discounted from the budget trip. Legacy-tolerant: a marker
    lacking the key defaults to ``{}`` and never KeyErrors. A falsy/None
    ``feature_id`` is a no-op (no spurious key). Returns the marker (the caller
    persists it via the atomic marker write).
    """
    if not isinstance(marker, dict):
        return marker
    if not feature_id:
        return marker
    per_feature = marker.get("per_feature_corrective_cycles")
    if not isinstance(per_feature, dict):
        per_feature = {}
    key = str(feature_id)
    per_feature[key] = int(per_feature.get(key, 0) or 0) + 1
    marker["per_feature_corrective_cycles"] = per_feature
    return marker


def budget_trip_signals(
    forward_count: int,
    corrective_count: int,
    ceiling: int,
    near_complete: bool,
) -> dict:
    """Composite budget-guard trip evaluator — the SINGLE decision point Phase 2
    substitutes for the bare ``_bg_count >= _bg_ceiling`` comparison.

    Returns ``{should_defer: bool, effective_count: int, reason: str}``:

      - ``effective_count = max(0, forward_count - corrective_count)`` — discount
        validation-driven corrective work (option a), clamped at 0 so a feature
        whose corrective cycles exceed its forward cycles never goes negative.
      - ``should_defer`` is True ONLY when ``effective_count >= ceiling`` AND NOT
        ``near_complete`` — a near-complete feature is granted grace (no defer)
        even at/over the ceiling.
      - ``reason`` distinguishes the three branches for the probe/diag:
        ``near-complete-grace`` (grace short-circuited a would-be defer),
        ``corrective-discount`` (the discount dropped effective below ceiling),
        ``over-ceiling`` (a genuine trip).

    Pure: same inputs → identical dict, no marker/clock I/O.
    """
    try:
        fwd = int(forward_count or 0)
    except (TypeError, ValueError):
        fwd = 0
    try:
        corr = int(corrective_count or 0)
    except (TypeError, ValueError):
        corr = 0
    try:
        ceil = int(ceiling or 0)
    except (TypeError, ValueError):
        ceil = 0
    effective_count = max(0, fwd - corr)
    over_ceiling = effective_count >= ceil
    if near_complete and over_ceiling:
        # Grace: a near-complete feature is allowed past the ceiling.
        return {
            "should_defer": False,
            "effective_count": effective_count,
            "reason": "near-complete-grace",
        }
    if not over_ceiling:
        # Below the ceiling. If the raw forward count WOULD have tripped but the
        # corrective discount pulled it under, attribute it to the discount;
        # otherwise it simply has not reached the ceiling yet.
        reason = "corrective-discount" if (corr > 0 and fwd >= ceil) else "under-ceiling"
        return {
            "should_defer": False,
            "effective_count": effective_count,
            "reason": reason,
        }
    return {
        "should_defer": True,
        "effective_count": effective_count,
        "reason": "over-ceiling",
    }


def advance_run_counters(state: dict) -> dict | None:
    """Advance the persisted forward_cycles or meta_cycles counter in the marker —
    ONLY when an actual dispatch (registry consume) has landed since the last
    advance.

    ROOT-CAUSE FIX (ISSUE 5 — d8-effect-chains live /lazy-batch run, 2026-06-14):
    The inject hook (lazy-route-inject.sh → lazy_inject.py) runs the full probe
    with ``--repeat-count`` on EVERY UserPromptSubmit turn while the marker is
    present — including non-dispatch turns (task notifications, the orchestrator's
    own bookkeeping turns, etc.). The prior implementation advanced the counter on
    EACH such firing, so ``forward_cycles`` reached 11 after only ~2 real
    dispatches + 2 recoveries (premature inflation → a false max-cycles halt at
    11/25 mid-run). The fix applies the SAME peek-vs-advance / consume-oracle
    discipline already used by ``update_repeat_counts`` (F2 debounce): a counter
    advances ONLY when the registry's consumed-emission count (``consume_count``,
    one consume per guard ALLOW = one real dispatch) has increased since the marker
    last recorded it. A probe firing with no intervening dispatch is a no-op.

    Classification rule (mirrors the emit_cycle_prompt None-return logic):
      - Real sub_skill: sub_skill is truthy AND does NOT start with ``"__"``
        → forward_cycles += 1  (a real dispatch cycle)
      - Pseudo/meta sub_skill: sub_skill starts with ``"__"``, OR sub_skill is
        falsy (None / empty) → meta_cycles += 1
    Meta/recovery dispatches that go through ``--emit-dispatch`` (not a probe) call
    ``advance_meta_cycle`` directly — those increment ``meta_cycles`` and bump the
    consume watermark too, so a subsequent probe in the same turn does not
    double-count.

    The marker carries ``last_advance_consume_count``: the consume-count at which a
    counter was last advanced (initialized to 0 at --run-start). The advance fires
    iff the current consume-count is strictly greater. After advancing, the
    watermark is updated to the current count. A legacy marker without the key is
    treated as 0, so the first advance still requires at least one consumed
    dispatch — a bare probe before any dispatch (consume-count 0) never advances.

    The updated marker is written atomically and returned. When no marker is
    present (read_run_marker returns None), this function returns None without
    writing anything — marker-gated, no-op when inactive. When a marker is present
    but no dispatch has landed since the last advance, the marker is returned
    UNCHANGED (no write).

    Args:
        state: the probe state dict (must contain "sub_skill")

    Returns:
        The marker dict (advanced or unchanged); None when no marker.
    """
    marker = read_run_marker()
    if marker is None:
        return None

    # Consume-oracle gate: only advance when a real dispatch landed since the last
    # advance. consumed_emission_count() is monotone-within-a-run (one consume per
    # guard ALLOW) UNTIL the ring cap evicts consumed entries, at which point the
    # LIVE census steps DOWN (non-monotonic oracle — Contributor B). A legacy marker
    # without the watermark key uses 0 so the first dispatch of the run always
    # advances.
    current_consume = consumed_emission_count()
    prior_consume = marker.get("last_advance_consume_count", 0)
    try:
        prior_consume = int(prior_consume)
    except (TypeError, ValueError):
        prior_consume = 0
    # CLAMP (Phase 2 — byref-dispatch-undercounts-forward-cycles): a non-monotonic
    # oracle can leave prior_consume STRANDED above the live census after ring-cap
    # eviction (or after advance_meta_cycle's +1 over-absorb), permanently freezing
    # the gate (current_consume <= prior_consume forever, even as real dispatches
    # land). When the census has dropped strictly BELOW the persisted watermark, the
    # watermark is stale — re-arm by clamping it down to the live census so this
    # observation (a genuine consume that crossed the eviction boundary) re-advances
    # exactly once, then the gate resumes normal strict-greater comparison. This does
    # NOT re-introduce the ISSUE-5 inflation: a bare re-probe with NO census change
    # leaves current_consume == prior_consume → still a no-op (the equality branch
    # below). Only a census that moved (rose, or dropped from eviction) can advance.
    if current_consume < prior_consume:
        prior_consume = current_consume - 1
    if current_consume <= prior_consume:
        # No dispatch consumed since the last advance — this is a bare probe/inject
        # firing (or a re-read). Do NOT advance, do NOT write. Idempotent across
        # the many inject-hook firings within one cycle.
        return marker

    sub_skill = state.get("sub_skill")
    # Real sub_skill: truthy and does not start with "__"
    if sub_skill and not str(sub_skill).startswith("__"):
        marker["forward_cycles"] = marker.get("forward_cycles", 0) + 1
        # feature-budget-guard-and-skip-ahead Phase 1: sibling per-feature
        # increment inside the SAME marker mutation, gated by the SAME forward
        # classification (a real non-`__` skill here). Reuses the existing advance
        # gate — no second oracle. Legacy-tolerant (defaults to {}).
        _bump_per_feature_forward(marker, state.get("feature_id"))
    else:
        # Pseudo or absent sub_skill → meta cycle
        marker["meta_cycles"] = marker.get("meta_cycles", 0) + 1

    marker["last_advance_consume_count"] = current_consume

    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def advance_meta_cycle() -> dict | None:
    """Increment the marker's ``meta_cycles`` counter for a meta/recovery dispatch.

    ISSUE 5 (d8-effect-chains live run): recovery / coherence-recovery / hardening
    / apply-resolution / investigation dispatches go through ``--emit-dispatch``,
    NOT the ``--repeat-count`` probe path, so the prior code never incremented
    ``meta_cycles`` for them (it stayed 0 through 2 recoveries in the live run).
    This helper is called from the --emit-dispatch handler when it registers a
    meta-class emission so the meta budget actually advances.

    It bumps ``last_advance_consume_count`` to the current consume-count PLUS ONE
    — absorbing the meta dispatch's OWN forthcoming guard-ALLOW consume — so the
    next ``--repeat-count`` probe does not mis-attribute that consume as a forward
    cycle. (If the meta dispatch is ultimately refused/never consumed, the worst
    case is one delayed forward advance — far cheaper than the inflation bug.)
    Marker-gated: no-op (returns None) when no marker is active.

    Phase 2 hardening (byref-dispatch-undercounts-forward-cycles, Contributor A):
    the ``+1`` is intentionally retained — it is load-bearing for the
    no-double-count invariant (``test_advance_meta_cycle_increments_meta`` pins it).
    Its only PERMANENT-strand risk was when meta dispatches outpaced forward
    consumes AND a later ring-cap eviction dropped the live census below this
    inflated watermark. That tail is now subsumed by ``advance_run_counters``'s
    census-drop CLAMP (a watermark stranded above the live census re-arms on the
    next census step), so the ``+1`` can no longer freeze the gate permanently — at
    most it delays a single forward advance by one cycle, as documented above.

    Returns:
        The updated marker dict; None when no marker.
    """
    marker = read_run_marker()
    if marker is None:
        return None
    marker["meta_cycles"] = marker.get("meta_cycles", 0) + 1
    # +1 absorbs this meta dispatch's own forthcoming consume (see docstring).
    marker["last_advance_consume_count"] = consumed_emission_count() + 1
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def advance_cycle_bracket_counter(cycle_marker: dict | None) -> dict | None:
    """Advance the run-marker cycle-budget counter for ONE completed dispatch
    bracket, keyed on the CYCLE marker's ``kind`` (cycle-budget-counters-double-
    count-on-probes-and-inject-hook).

    THE budget authority for real/meta Agent dispatches. Called from BOTH
    ``--cycle-end`` handlers (lazy-state.py / bug-state.py) AFTER reading the cycle
    marker and BEFORE ``clear_cycle_marker()``. The ``--cycle-begin`` /
    ``--cycle-end`` bracket wraps EXACTLY ONE Agent dispatch, so a completed bracket
    is a real dispatch event the script observes directly. Moving the budget
    increment here DECOUPLES it from the ``--repeat-count`` probe path — which fired
    on inspection probes AND the per-turn inject hook (lazy_inject.py), inflating
    ``forward_cycles`` with no dispatch (the root cause). The probe path now advances
    only the loop-detection streaks (``update_repeat_counts``), never the budget.

    Classification (from the cycle marker's ``kind``, written by ``--cycle-begin``):
      - ``kind == "real"`` → ``forward_cycles += 1`` PLUS the sibling
        ``per_feature_forward_cycles[feature_id]`` bump, via the SAME
        ``_bump_per_feature_forward`` helper ``advance_run_counters`` /
        ``advance_forward_cycle`` use (no second oracle — "what counts as a forward
        cycle" and "which feature it bumps" stay defined in exactly one place).
      - ``kind == "meta"`` → ``meta_cycles += 1`` (uncapped).
      - any other / absent kind → no-op, no write (defensive; the bracket contract
        only ever writes "real" | "meta").

    Idempotent per bracket BY CONSTRUCTION: one cycle marker == one dispatch, and
    the marker is cleared immediately after this call at ``--cycle-end`` — so a
    bracket can advance the budget at most once.

    Marker-gated: no RUN marker → returns None and writes nothing (byte-identical to
    the no-run path, so a --cycle-end outside a live run is inert). A None / non-dict
    / kind-less CYCLE marker is likewise a no-op. On a real advance the updated run
    marker is atomic-written and returned.

    Args:
        cycle_marker: the cycle marker dict just read at --cycle-end (or None).

    Returns:
        The updated run marker dict; None when there is no run marker (or nothing
        to count for this bracket).
    """
    marker = read_run_marker()
    if marker is None:
        return None
    if not isinstance(cycle_marker, dict):
        return None
    kind = cycle_marker.get("kind")
    if kind == "real":
        marker["forward_cycles"] = marker.get("forward_cycles", 0) + 1
        # Sibling per-feature bump, gated by the SAME real classification (no
        # second oracle) — reuses the helper the probe-path advances also use.
        _bump_per_feature_forward(marker, cycle_marker.get("feature_id"))
    elif kind == "meta":
        marker["meta_cycles"] = marker.get("meta_cycles", 0) + 1
    else:
        # Neither "real" nor "meta" (legacy / malformed cycle marker) — count
        # nothing and do not write.
        return None
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


# Forward-advancing pseudo-skills: inline (--apply-pseudo) terminals that ADVANCE
# the pipeline a step (write a receipt / flip status / archive), as opposed to
# cleanup/meta pseudo-skills. A forward-advancing pseudo-skill counts toward the
# forward budget (forward_cycles); any other __-prefixed (or falsy) sub_skill is
# meta. Kept here as the SSOT for the Fix-A classifier (item 1,
# lazy-batch-unified-driver-parity-and-accounting Phase 1).
_FORWARD_ADVANCING_PSEUDO_SKILLS = frozenset({
    "__mark_complete__",
    "__mark_fixed__",
    "__write_validated_from_skip__",
    "__write_validated_from_results__",
    "__grant_skip_no_mcp_surface__",
    "__flip_plan_complete_cloud_saturated__",
})


def advance_forward_cycle(state: dict, *, consume_gate: bool = False) -> dict | None:
    """Fix-A (item 1): a CONSUME-INDEPENDENT forward/meta advance keyed on a change
    in the marker-recorded ``(feature_id, current_step, sub_skill)`` tuple.

    SECOND-TRIGGER FIX (byref-forward-cycles-frozen-on-multicycle-same-step,
    2026-07-16): the state-change trigger ALONE freezes ``forward_cycles`` whenever
    consecutive genuine cycles share an IDENTICAL ``(feature_id, current_step,
    sub_skill)`` tuple — the canonical case being a multi-part ``/execute-plan``
    implementation that dispatches the SAME real sub_skill for the SAME feature at
    the SAME step, one cycle per plan part. After the first advance sets
    ``last_advance_state_key``, every later same-step cycle sees ``prior_key ==
    current_key`` and no-ops, so ``forward_cycles`` stuck at 1 for the whole phase,
    ``max_cycles`` could never trip (unbounded run vs. the operator's cost budget),
    and the derived ``cycle_header`` (``[1/10]``) + inject-banner turn
    (``forward_cycles + meta_cycles + 1`` → "turn 2") froze too. The ``consume_gate``
    parameter adds the registry consume-census rise as a SECOND advance trigger
    (OR): on the real-skill ``--repeat-count`` probe path each distinct consumed
    dispatch advances the budget even when the state tuple is unchanged. The census
    is non-monotonic under ring-cap eviction, so the same down-step CLAMP as
    ``advance_run_counters`` is applied and the shared ``last_advance_consume_count``
    watermark is maintained (so the meta path's +1 absorb still prevents
    double-count). Advancing on EITHER trigger, at most once per probe, is
    double-count-safe: a feature/step transition that changes the tuple AND raises
    the census still advances exactly once. A bare re-fire (SAME tuple AND no new
    consume) still no-ops, preserving within-cycle idempotence. ``consume_gate``
    defaults False so the pseudo-skill ``--apply-pseudo`` caller — whose distinct
    ``(slug, pseudo_name, pseudo_name)`` tuple per apply already discriminates and
    which emits no consume — stays byte-identical.

    ROOT CAUSE (lazy-batch-unified-driver-parity-and-accounting, 2026-06-17):
    forward-advancing inline pseudo-skills (``__mark_complete__``/``__mark_fixed__``/
    ``__write_validated_*``/``__grant_skip_no_mcp_surface__``/
    ``__flip_plan_complete_cloud_saturated__``) run via ``--apply-pseudo`` — they
    dispatch no Agent, trigger no guard ALLOW, and increment no registry consume.
    ``advance_run_counters`` gates on a consume rise, so the forward budget never
    advances for them (and ``advance_meta_cycle`` only covers ``--emit-dispatch``
    meta calls). This helper closes that gap by advancing on a genuine STATE
    CHANGE — independent of the consume oracle.

    The marker carries ``last_advance_state_key``: the
    ``[feature_id, current_step, sub_skill]`` tuple at which a counter was last
    advanced (a JSON list; a legacy marker without the key is treated as None, so
    the first state change always advances). The advance fires iff the current
    tuple DIFFERS from the recorded one — so a bare probe/inject re-fire with the
    SAME tuple is a no-op (preserves the idempotence that the consume-gated
    ``advance_run_counters`` provides for re-fires). On advance the key is updated.

    Classification (a forward-advancing pseudo-skill OR a real sub_skill →
    ``forward_cycles``; any other ``__``-prefixed / falsy sub_skill → ``meta_cycles``):
      - real sub_skill (truthy, not ``__``-prefixed) → forward
      - ``__``-prefixed AND in ``_FORWARD_ADVANCING_PSEUDO_SKILLS`` → forward
      - any other ``__``-prefixed, OR falsy sub_skill → meta

    Marker-gated: returns None (no write) when no run marker is present, mirroring
    ``advance_meta_cycle``. When the tuple is unchanged, returns the marker
    UNCHANGED (no write).

    Args:
        state: the resolved probe/apply state dict (reads ``sub_skill``,
               ``feature_id``, ``current_step``).

    Returns:
        The marker dict (advanced or unchanged); None when no marker.
    """
    marker = read_run_marker()
    if marker is None:
        return None

    sub_skill = state.get("sub_skill")
    # The advance key — JSON-serializable list (json.loads round-trips a tuple to a
    # list, so compare as lists for stable equality across re-reads).
    current_key = [
        state.get("feature_id"),
        state.get("current_step"),
        sub_skill,
    ]
    prior_key = marker.get("last_advance_state_key")
    state_changed = prior_key != current_key

    # Second trigger (consume_gate): a consume-census rise since the last advance.
    # Only consulted on the real-skill probe path so a genuine NEXT cycle of the
    # SAME tuple (multi-part execute-plan) still advances the budget. Mirrors the
    # advance_run_counters clamp/watermark discipline so ring-cap eviction and the
    # meta path's +1 absorb are both respected.
    consume_rose = False
    current_consume: int | None = None
    if consume_gate:
        current_consume = consumed_emission_count()
        prior_consume = marker.get("last_advance_consume_count", 0)
        try:
            prior_consume = int(prior_consume)
        except (TypeError, ValueError):
            prior_consume = 0
        # Non-monotonic-oracle CLAMP (identical to advance_run_counters): a census
        # stranded below the watermark after ring-cap eviction re-arms exactly once
        # rather than freezing the gate forever.
        if current_consume < prior_consume:
            prior_consume = current_consume - 1
        consume_rose = current_consume > prior_consume

    if not state_changed and not consume_rose:
        # Same state AND no new dispatch consumed — a bare re-fire. Do NOT advance.
        return marker

    # Classify: forward iff a real skill OR a forward-advancing pseudo-skill.
    is_real = bool(sub_skill) and not str(sub_skill).startswith("__")
    is_forward_pseudo = sub_skill in _FORWARD_ADVANCING_PSEUDO_SKILLS
    if is_real or is_forward_pseudo:
        marker["forward_cycles"] = marker.get("forward_cycles", 0) + 1
        # feature-budget-guard-and-skip-ahead Phase 1: sibling per-feature
        # increment, gated by the SAME forward classification used above (the
        # state-change trigger). Keeps "what counts as a forward cycle" defined in
        # exactly one place; no second oracle. Legacy-tolerant (defaults to {}).
        _bump_per_feature_forward(marker, state.get("feature_id"))
    else:
        marker["meta_cycles"] = marker.get("meta_cycles", 0) + 1

    marker["last_advance_state_key"] = current_key
    # Maintain the shared consume watermark whenever the consume gate is active, so
    # the next probe compares against this advance (and the meta path's +1 absorb
    # stays coherent). Only written on the consume-gated path; the pseudo path never
    # touches it (byte-identical to prior behavior).
    if consume_gate and current_consume is not None:
        marker["last_advance_consume_count"] = current_consume

    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def record_resolution_signal(state: dict) -> dict | None:
    """Persist the resolution-aware reset signal on the run marker.

    ROOT CAUSE (loop-detected-false-positives-from-probe-and-reboot-churn,
    symptom 3 — the sole residual class after the F1/F2 consume-debounce):
    a needs-input *resolution* meta-cycle is itself an Agent dispatch, so it
    consumes a registry nonce.  That defeats the F2 double-probe debounce's
    "no dispatch landed between the two probes" precondition — the HEAD-blind
    ``step_repeat_count`` therefore SURVIVES a legitimately-resolved blocker and
    keeps marching toward the LOOP-DETECTED tripwire.

    The fix is a DETERMINISTIC, PERSISTED signal (⚖ D7: a recorded marker field,
    NOT a racy probe-time re-inference of cleared-sentinel state).  The resolution
    dispatch bracket calls this helper to record
    ``last_resolution_step_key = [feature_id, current_step]`` on the run marker.
    ``update_repeat_counts`` reads it and, on the NEXT probe with the SAME step
    signature, RESETS ``step_count`` to 1 and CLEARS the field — so the reset
    fires exactly ONCE across the resolution (one-shot), scoped exactly like the
    ordered-advance exemption.

    Mirrors the ``last_advance_state_key`` marker-field pattern
    (``advance_forward_cycle``).  Marker-gated: returns None and writes nothing
    when no run marker is present (so an ordinary, non-resolution cycle never
    leaves the signal asserted).  Legacy markers lacking the field simply never
    trigger the reset (same legacy-tolerance as ``head`` / ``step_*`` /
    ``consume_count``) — the reset can never spuriously fire on an old marker.

    Args:
        state: a dict carrying ``feature_id`` and ``current_step`` (the step
               signature the resolution was applied at).

    Returns:
        The updated marker dict; None when no marker is present.
    """
    marker = read_run_marker()
    if marker is None:
        return None

    # The step signature the resolution was applied at — a JSON-serializable list
    # (json round-trips a tuple to a list, so the consumer compares as lists).
    marker["last_resolution_step_key"] = [
        state.get("feature_id"),
        state.get("current_step"),
    ]
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def _consume_resolution_signal(repo_root: Path, step_sig: tuple) -> bool:
    """Read-and-clear the one-shot resolution signal for ``update_repeat_counts``.

    Returns True iff a run marker for THIS repo is present AND it carries a
    ``last_resolution_step_key`` equal to ``step_sig`` (the current
    ``(feature_id, current_step)`` step signature).  On a match the field is
    CLEARED from the marker (one-shot — the reset fires once across the
    resolution, not on every subsequent probe) and the marker is re-persisted.

    Repo-scoped exactly like the F2 debounce oracle: a marker bound to a
    DIFFERENT repo never matches (so a concurrent run in another repo can never
    reset this repo's step counter).  Fail-safe: any read/parse/path error
    returns False (the reset simply does not fire — never raises, never weakens
    the tripwire on a degraded marker).
    """
    try:
        marker = read_run_marker()
        if marker is None:
            return False
        # Repo-scope: only honor a signal whose marker belongs to THIS repo.
        marker_repo = marker.get("repo_root")
        if marker_repo is None or Path(marker_repo).resolve() != repo_root.resolve():
            return False
        recorded = marker.get("last_resolution_step_key")
        if recorded != list(step_sig):
            return False
        # One-shot: clear the signal and re-persist before returning the match.
        marker.pop("last_resolution_step_key", None)
        marker_path = claude_state_dir() / _MARKER_FILENAME
        _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


# ---------------------------------------------------------------------------
# mechanize-prose-only-orchestrator-contracts (b): post-cycle input-audit
# obligation — the §1d.5 dispatch made unskippable.
#
# ROOT CAUSE: the input-audit dispatch (--emit-dispatch input-audit) has
# existed as a registered, guard-safe emission class for a while, but WHETHER
# the orchestrator runs it after a /spec or plan-feature cycle was pure
# SKILL.md prose (§1d.5) — an orchestrator under autonomous load can skip the
# step entirely with no mechanical consequence, which is exactly the failure
# mode §1d.5 itself exists to catch for the CYCLE SUBAGENT's self-audit ("zero
# NEEDS_INPUT.md sentinels fired from /spec's self-audit across ~75 observed
# cycles"). This promotes the DISPATCH obligation itself to the same
# script-enforced withhold the pending-hardening-debt precedent uses
# (lazy-state.py ~13215: route_overridden_by == "pending-hardening-debt").
#
# Mechanism (marker-field pattern, mirroring last_advance_state_key /
# last_resolution_step_key): --cycle-end records `audit_obligation:
# {item_id, cycle_kind}` on the run marker when the ending cycle's sub_skill
# is an audited kind (spec/plan-feature on the feature pipeline; spec-bug/
# plan-bug on the bug pipeline). The NEXT --emit-prompt probe sees the
# obligation and WITHHOLDS the forward cycle_prompt (byte-identical shape to
# the hardening-debt withhold) until --emit-dispatch input-audit registers a
# real dispatch under the SAME live marker, which discharges it.
# ---------------------------------------------------------------------------

# The sub_skill kinds whose cycle-end obligates a post-cycle input audit.
# feature pipeline: spec, plan-feature (author SPEC/PHASES content).  bug
# pipeline: spec-bug, spec-phases — per the EXISTING lazy-bug-batch/SKILL.md
# Step 1d.5 skip-condition prose this mechanizes: "plan-bug is a planning
# step, not a SPEC/PHASES-authoring cycle — skip audit for plan-bug" (D5:
# a discovered ambiguity resolves in favor of existing prose semantics, not
# a naive plan-feature/plan-bug pairing). spec-phases is carried for prose
# fidelity even though bug-state.py's live routing never emits it today
# (SKILL_SPEC_PHASES is an unused constant) — harmless if it never fires,
# pre-covered if the bug pipeline ever starts emitting it. One shared set —
# a sub_skill name never collides across pipelines within a single process
# (only one state script's sub_skill vocabulary is live).
AUDITED_CYCLE_KINDS: frozenset = frozenset({
    "spec", "plan-feature", "spec-bug", "spec-phases",
})


def record_audit_obligation(item_id: str | None, cycle_kind: str | None) -> dict | None:
    """Record the post-cycle input-audit obligation on the run marker (D2-A).

    Called from --cycle-end immediately after a /spec or plan-feature (or the
    bug-pipeline spec-bug/plan-bug) cycle ends. Marker-gated: returns None and
    writes nothing when no run marker is present (mirrors
    ``record_resolution_signal``). A falsy/non-audited ``cycle_kind`` is a
    no-op (returns the marker UNCHANGED, no write) — only the four audited
    kinds ever arm the obligation.

    Overwrites any PRIOR obligation (there is at most one outstanding
    obligation at a time — cycles are serial, and the withhold this powers
    forces discharge before the next cycle can begin).

    Args:
        item_id: the feature/bug id the obligation is owed for.
        cycle_kind: the sub_skill of the cycle that just ended.

    Returns:
        The updated marker dict; None when no marker is present.
    """
    marker = read_run_marker()
    if marker is None:
        return None
    if cycle_kind not in AUDITED_CYCLE_KINDS:
        return marker
    marker["audit_obligation"] = {"item_id": item_id, "cycle_kind": cycle_kind}
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def pending_audit_obligation() -> dict | None:
    """Read-only: the current run marker's outstanding audit_obligation, or
    None (no marker / no obligation / legacy marker lacking the field).

    Never raises, never writes. Used by the --emit-prompt withhold check and
    by any read-only probe/status surface that wants to display it.
    """
    marker = read_run_marker()
    if marker is None:
        return None
    obligation = marker.get("audit_obligation")
    return obligation if isinstance(obligation, dict) else None


def discharge_audit_obligation() -> bool:
    """Clear the run marker's audit_obligation (D2-A discharge).

    Called at the --emit-dispatch input-audit success site, AFTER the
    dispatch is registered under a live marker (register_emission_if_marked
    returned a non-None entry) — the same transaction the SPEC calls out
    ("discharged by the --emit-dispatch input-audit registration itself").

    Returns True iff a marker was present and carried a (now-cleared)
    obligation; False on a no-op (no marker, or no obligation to clear) —
    never raises.
    """
    marker = read_run_marker()
    if marker is None:
        return False
    if "audit_obligation" not in marker:
        return False
    marker.pop("audit_obligation", None)
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return True


# ---------------------------------------------------------------------------
# Phase 7 WU-7.4 — Run-checkpoint contract (sanctioned unattended pause)
# ---------------------------------------------------------------------------
#
# A --run-end --reason checkpoint writes lazy-run-checkpoint.json carrying the
# next route the orchestrator should resume with plus the marker's fold counters
# at run end.  The next --run-start consumes it (echoes + deletes), giving the
# resumed run its sanctioned-pause context.  This gives /lazy-batch-retro a
# mechanical sanctioned-vs-improvised signal for an early stop.


def write_run_checkpoint(
    next_route: str,
    counters: dict,
    now: float | None = None,
    operator_authorized: bool = False,
) -> dict:
    """Write lazy-run-checkpoint.json to the state dir (checkpoint run-end).

    Args:
        next_route: the probed next route the resumed run should take.
        counters: the marker's fold counters as folded at run end (e.g.
                  {"forward_cycles": N, "meta_cycles": M, "max_cycles": K}).
        now: epoch float for the ts field (injectable for hermetic tests).
        operator_authorized: whether this checkpoint was written for a deliberate
            operator-authorized stop (a `/lazy-batch <N>` re-invoke wants a fresh
            0/0 budget) vs. an automatic reliability pause (monotonic carry-forward
            on resume).  Persisted as a top-level field so restore_checkpoint_counters
            can branch on resume provenance.  Defaults False —
            backward-compatible: a pre-fix checkpoint file lacking the field reads
            as falsy, taking the carry-forward path.

    Returns:
        The checkpoint dict that was written.
    """
    if now is None:
        now = time.time()
    # cycle-bracket-break-on-checkpoint-resume (hardening Round 35, 2026-06-23):
    # capture the RUN IDENTITY (the marker's started_at) at checkpoint-write time
    # so the carry-forward resume path can RESTORE it. A non-operator-authorized
    # checkpoint resume is "the SAME run continuing after a sanctioned pause" — it
    # already carries forward the monotonic forward/meta counters (HARD CONSTRAINT
    # 8). The run IDENTITY (started_at) is the value detect_cycle_bracket_friction
    # signal (a) compares (run_started_at snapshotted at --cycle-begin vs the live
    # marker's started_at at --cycle-end). write_run_marker unconditionally MINTS a
    # fresh started_at on the resuming --run-start, so without restoring it a
    # legitimate same-run pause/resume changed the run identity mid-cycle and
    # false-tripped cycle-bracket-break on any cycle whose begin snapshot predates
    # the resume (observed: begin 03:15:38Z != end 05:41:28Z, jog-wheel-nudging).
    # Best-effort read — a missing/None marker (degraded) omits the field, and
    # restore_checkpoint_counters falls back to leaving the freshly-minted identity
    # (no crash, no false restore). Operator-authorized resumes do NOT restore it
    # (they are a genuinely NEW run wanting a fresh identity — see restore_*).
    # Read the marker RAW (not via read_run_marker, whose path-A age gate DELETES a
    # >24h-stale marker on read) — a checkpoint-write must NEVER have a destructive
    # side effect on the marker it is snapshotting.
    # adhoc-checkpoint-resume-field-complete-continuity (2026-06-23): snapshot the
    # FULL run-scoped continuity set (RUN_CONTINUITY_FIELDS) as ONE nested
    # `continuity` block — not the ad-hoc started_at-only snapshot that grew
    # reactively in lockstep with the carry-set. restore_checkpoint_counters
    # re-applies this whole block as one unit on a sanctioned resume, so a newly-
    # added continuity field rides through by construction (no third whack-a-mole).
    # Read the marker RAW (never read_run_marker, whose path-A age gate DELETES a
    # >24h-stale marker on read) — a checkpoint-write must NEVER have a destructive
    # side effect on the marker it is snapshotting. The flat run_started_at key is
    # retained as a mirror for one transition so a restore by an older code path or
    # a half-flight legacy reader still sees the identity (back-compat belt).
    run_started_at = None
    continuity: dict = {}
    try:
        _marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
        if _marker_path.exists():
            _live = json.loads(_marker_path.read_text(encoding="utf-8"))
            if isinstance(_live, dict):
                run_started_at = _live.get("started_at")
                for _k in RUN_CONTINUITY_FIELDS:
                    if _k in _live:
                        continuity[_k] = _live[_k]
    except Exception:  # pragma: no cover - defensive; never block a checkpoint
        run_started_at = None
        continuity = {}
    checkpoint = {
        "reason": "checkpoint",
        "next_route": next_route,
        "counters": counters,
        "operator_authorized": bool(operator_authorized),
        "run_started_at": run_started_at,
        "continuity": continuity,
        "ts": now,
    }
    checkpoint_path = claude_state_dir() / _CHECKPOINT_FILENAME
    _atomic_write(checkpoint_path, json.dumps(checkpoint, indent=2) + "\n")
    return checkpoint


def consume_run_checkpoint() -> dict | None:
    """Read and DELETE lazy-run-checkpoint.json (consume-once resume context).

    Called by --run-start: if a checkpoint file exists, its content is returned
    (so run-start can echo it as resume context) and the file is deleted so the
    same checkpoint is never replayed twice.  A missing or corrupt file → None.

    Returns:
        The checkpoint dict, or None when no (valid) checkpoint is present.
    """
    checkpoint_path = claude_state_dir(create=False) / _CHECKPOINT_FILENAME
    if not checkpoint_path.exists():
        return None
    data: dict | None = None
    try:
        raw = checkpoint_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
    except (OSError, json.JSONDecodeError, ValueError):
        data = None
    # Delete regardless of parse outcome — a corrupt checkpoint must not haunt
    # every subsequent run-start.
    try:
        checkpoint_path.unlink()
    except OSError:
        pass
    return data


def restore_checkpoint_counters(checkpoint: dict | None) -> dict | None:
    """Restore a resumed run's monotonic cycle counters AND run identity from its
    checkpoint.

    Identity carry-forward (cycle-bracket-break-on-checkpoint-resume, hardening
    Round 35, 2026-06-23): in the carry-forward (non-operator-authorized) branch
    this ALSO restores the marker's ``started_at`` (the run identity) from the
    checkpoint's ``run_started_at`` field — in lockstep with the counters and for
    the same HARD CONSTRAINT 8 reason (the SAME run continues across a sanctioned
    pause, so its identity must be continuous, not freshly minted). Guarded so a
    >24h-old identity is NOT restored (it would subvert read_run_marker's age
    gate), and a missing/unparseable identity leaves the minted started_at intact.

    ROOT-CAUSE FIX (accidental mid-run counter reset, 2026-06-14): a sanctioned
    checkpoint pause writes ``lazy-run-checkpoint.json`` carrying the marker's
    ``forward_cycles`` / ``meta_cycles`` at run end (see ``write_run_checkpoint``).
    The resuming ``--run-start`` previously called ``write_run_marker`` (which
    UNCONDITIONALLY zeros both counters + the consume watermark) and then merely
    echoed the checkpoint as ``resumed_from_checkpoint`` WITHOUT writing those
    counters back. Result: a checkpoint pause/resume reset the running cycle count
    to 0 MID-RUN — a direct violation of HARD CONSTRAINT 8 (both counters are
    monotonic for the LIFE of a run and never reset on a within-run transition).
    This is the operator-observed reset.

    Two resume classes (operator-checkpoint-resume-counter-reset, 2026-06-17):
    a checkpoint carries an ``operator_authorized`` flag recorded at write time.

    * **operator-authorized** (``operator_authorized`` truthy) — a DELIBERATE
      ``/lazy-batch <N>`` re-invoke after an operator-authorized stop. The operator
      wants a FRESH authorized budget, so this helper does NOT carry the paused
      counts forward: it returns ``None`` (a no-op), leaving the just-written
      marker's by-design ``0/0`` start. This is NOT a within-run reset (no HARD
      CONSTRAINT 8 violation) — it is a NEW authorized run that happens to resume
      a route, not a within-run transition.
    * **automatic reliability pause / legacy** (``operator_authorized`` falsy or
      ABSENT) — an automatic mid-run pause (e.g. cloud ≥2 guard denials) or a
      pre-fix checkpoint file. The resumed marker must CARRY FORWARD the paused
      counts so the running total never goes backward mid-run and an auto-resume
      cannot silently exceed the authorized ``max_cycles`` (HARD CONSTRAINT 8).
      A truthy-check (``if checkpoint.get("operator_authorized"):``) makes both
      ``False`` and a missing field take this carry-forward path uniformly.

    For the carry-forward class, this helper reads the just-written marker,
    overwrites ``forward_cycles`` / ``meta_cycles`` from the checkpoint's
    ``counters`` block, and resets ``last_advance_consume_count`` to 0.

    Why ``last_advance_consume_count`` resets to 0 (and that is CORRECT, not a
    reset of a cycle counter): the registry/consume-count watermark is run-scoped
    and a fresh ``--run-start`` clears the registry (``delete_run_marker`` cleared
    it at the prior checkpoint). The watermark only gates whether a *future*
    consume since the last advance is real; carrying a stale watermark across the
    registry reset would suppress the first post-resume advance. Zeroing it means
    the first real dispatch after resume advances correctly ON TOP of the restored
    forward/meta totals — so the visible running total N never goes backward.

    A genuinely NEW ``/lazy-batch <N>`` invocation (no checkpoint on disk) is NOT
    affected: ``checkpoint`` is None → this is a no-op and the marker keeps the
    by-design 0/0 start.

    Args:
        checkpoint: the dict returned by ``consume_run_checkpoint()`` (or None).
            Only its ``counters`` sub-dict is consulted; absent/garbage values
            fall back to 0 so a malformed checkpoint can never crash run-start.

    Returns:
        The updated marker dict when counters were restored; None when there was
        no checkpoint, no active marker, no usable counters, OR the checkpoint was
        operator-authorized (fresh-budget resume — intentional no-op).
    """
    if not isinstance(checkpoint, dict):
        return None
    counters = checkpoint.get("counters")
    if not isinstance(counters, dict):
        return None
    marker = read_run_marker()
    if marker is None:
        return None
    # operator-checkpoint-resume-counter-reset (2026-06-17): an operator-authorized
    # checkpoint is a deliberate stop whose resume wants a FRESH 0/0 budget — skip
    # the carry-forward so the just-written marker keeps its by-design start. A
    # truthy-check makes False AND a missing field (pre-fix files / automatic
    # reliability pauses) fall through to the carry-forward path below.
    if checkpoint.get("operator_authorized"):
        return None

    def _coerce(value: object) -> int:
        # A checkpoint counter may legitimately be None (marker lacked the field
        # at checkpoint time) or a non-int from a hand-edited/corrupt file —
        # coerce to a non-negative int, never crash run-start.
        try:
            n = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0
        return n if n >= 0 else 0

    def _restore_identity(candidate: object) -> None:
        # cycle-bracket-break-on-checkpoint-resume (hardening Round 35): restore the
        # RUN IDENTITY (started_at) in lockstep with the counters. A non-operator-
        # authorized resume is the SAME run continuing, so started_at (which
        # write_run_marker just MINTED afresh) must be the pre-pause identity —
        # otherwise detect_cycle_bracket_friction signal (a) false-trips
        # cycle-bracket-break. Only restore a well-formed, NON-stale-by-age value:
        # restoring a >24h-old identity would subvert read_run_marker's age gate
        # into auto-resuming a presumed-dead run, so KEEP the minted identity then.
        # A missing/blank/unparseable value leaves the minted started_at untouched.
        if isinstance(candidate, str) and candidate:
            try:
                _ident_dt = datetime.datetime.strptime(
                    candidate, "%Y-%m-%dT%H:%M:%SZ"
                )
                _ident_epoch = (
                    _ident_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if time.time() - _ident_epoch <= _MARKER_STALE_SECONDS:
                    marker["started_at"] = candidate
            except (ValueError, TypeError):
                pass  # unparseable identity → keep the freshly-minted started_at

    # adhoc-checkpoint-resume-field-complete-continuity (2026-06-23): re-apply the
    # FULL continuity block as one unit when the checkpoint carries one. This
    # closes the field-by-field whack-a-mole — every RUN_CONTINUITY_FIELDS key
    # (incl. both per_feature_* budget maps) survives a sanctioned same-run pause
    # by construction, with the per-field guards preserved:
    #   - the two counters coerce to a non-negative int (fail-safe);
    #   - started_at restores only when well-formed AND not >24h stale (age gate);
    #   - the two per_feature_* maps apply only when a well-formed dict (else the
    #     minted {} is left);
    #   - last_advance_consume_count stays FORCED to 0 (a RUN_FRESH_FIELD — the
    #     registry is freshly cleared, carrying a stale watermark would suppress
    #     the first post-resume advance; SPEC Out of Scope).
    continuity = checkpoint.get("continuity")
    if isinstance(continuity, dict) and continuity:
        if "forward_cycles" in continuity:
            marker["forward_cycles"] = _coerce(continuity.get("forward_cycles"))
        if "meta_cycles" in continuity:
            marker["meta_cycles"] = _coerce(continuity.get("meta_cycles"))
        _restore_identity(continuity.get("started_at"))
        for _map_key in ("per_feature_forward_cycles", "per_feature_corrective_cycles"):
            _val = continuity.get(_map_key)
            if isinstance(_val, dict):
                marker[_map_key] = _val
    else:
        # Back-compat: a legacy / pre-fix / mid-flight checkpoint with the flat
        # `counters` + `run_started_at` fields but NO `continuity` block still
        # restores identity + counters via the original legacy path.
        marker["forward_cycles"] = _coerce(counters.get("forward_cycles"))
        marker["meta_cycles"] = _coerce(counters.get("meta_cycles"))
        _restore_identity(checkpoint.get("run_started_at"))
    # Registry is freshly cleared on this run-start → the consume watermark must
    # start at 0 so the first real post-resume dispatch advances (see docstring).
    marker["last_advance_consume_count"] = 0
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def rebaseline_loop_signature_after_registry_reset(
    repo_root: Path,
    *,
    pipeline: str = "feature",
    signature_path: Path | None = None,
) -> bool:
    """Re-baseline the loop-detection signature file's ``consume_count`` to the
    current (freshly-cleared) registry consume-count on a checkpoint resume.

    ROOT CAUSE (checkpoint-resume-false-loop-flips-complex-part-to-sonnet, 2026-07-12):
    ``update_repeat_counts``'s F1/F2 double-probe debounce HOLDS a repeat count
    (rather than incrementing it) only when it can prove NO dispatch landed
    between two identical probes — i.e. the persisted ``consume_count`` equals the
    live ``consumed_emission_count()``. That ``consume_count`` lives in the OS-temp
    signature file (``lazy-state-last-<hash>.json``), which SURVIVES ``--run-end``.
    But a checkpoint ``--run-end`` deletes the prompt registry and the resuming
    ``--run-start`` recreates it fresh, so ``consumed_emission_count()`` resets to
    0 while the signature file still carries the PRE-checkpoint count. The first
    re-probe of the SAME ``next_route`` (which a checkpoint resume deterministically
    re-probes) then sees ``prior_consume != current``, cannot prove the re-read,
    and inflates ``repeat_count`` to 2 → a FALSE ``LOOP DETECTED`` on a route that
    was NEVER re-dispatched (a probe→checkpoint→probe is not a stall; a genuine
    stall requires a DISPATCH that failed to advance between two probes).

    The fix re-baselines ONLY the ``consume_count`` field to the fresh registry's
    count (``consumed_emission_count()`` — 0 at run-start, the registry having just
    been cleared), so the next probe of the unchanged route reads
    ``prior_consume == current`` and HOLDS. The persisted ``signature`` / ``count``
    / ``step_signature`` / ``step_count`` are PRESERVED untouched, so a GENUINE
    pre-pause loop streak (``count >= 2``) survives — the loop block still fires —
    while a never-re-attempted route no longer inflates.

    Called from the checkpoint-resume block of both state scripts' ``--run-start``
    handlers (coupled-pair mirror; the helper is shared, the call site per-script).
    ``signature_path`` defaults to the same per-repo/per-pipeline OS-temp path
    ``update_repeat_counts`` derives, so the two agree by construction.

    Returns True when the field was re-baselined; False (no-op) when no signature
    file exists, when it is unreadable/corrupt/wrong-shape, or when no run marker
    is present (the debounce is marker-gated — with no marker the next probe never
    engages it, so re-baselining would be meaningless). NEVER raises.
    """
    # Defensive coercion (checkpoint-resume-rebaseline-crashes-on-str-repo-root):
    # a real caller passed lazy_core.active_repo_root() here directly — that
    # helper returns str, not Path, and `.resolve()` below raised AttributeError
    # on it, breaking the documented "NEVER raises" contract. Path(Path(x)) is a
    # no-op for an already-Path caller, so this is byte-identical for every
    # existing correct call site.
    repo_root = Path(repo_root)
    if signature_path is None:
        repo_hash = hashlib.sha1(
            str(repo_root.resolve()).encode("utf-8")
        ).hexdigest()[:16]
        prefix = "lazy-state-last" if pipeline == "feature" else f"{pipeline}-state-last"
        signature_path = Path(tempfile.gettempdir()) / f"{prefix}-{repo_hash}.json"
    try:
        if not signature_path.exists():
            return False
        # The debounce is marker-gated (update_repeat_counts writes/reads
        # consume_count only under a live marker). At checkpoint resume the marker
        # was just written by --run-start, so it is present and age-fresh; a
        # missing marker means the next probe cannot engage the debounce anyway.
        if read_run_marker() is None:
            return False
        data = json.loads(signature_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        data["consume_count"] = consumed_emission_count()
        _atomic_write(signature_path, json.dumps(data))
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False
