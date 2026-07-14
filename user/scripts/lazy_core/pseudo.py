"""lazy_core.pseudo — the deterministic pseudo-skill apply plane.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 5, WU-2) — a move-only refactor with zero behavior change. Owns
``apply_pseudo`` (the SINGLE author of the deterministic pseudo-skill writes:
``__write_validated_from_{skip,results}__``, ``__write_deferred_non_cloud__``,
``__flip_plan_complete_cloud_saturated__``, ``__grant_skip_no_mcp_surface__``,
and the receipt-gated ``__mark_complete__`` / ``__mark_fixed__`` completion
sequence) plus its private helpers: the completion post-condition audit
(``_completion_postconditions_missing`` — the resumable-partial-completion
contract), the ROADMAP strike helpers (``_strike_roadmap_row`` /
``_roadmap_has_unstruck_row`` / ``_top_status_is``), and
``_resolve_under_repo``.

SPEC D3: ``apply_pseudo`` (~1,356 lines) moved INTACT as one verbatim slice —
NOT internally refactored in this feature (decomposing it is its own future
feature). Write-path move sanctioned by the two archived bug receipts (SPEC
D2 Constraint 3): docs/bugs/_archive/mark-complete-partial-apply-noop-
unrecoverable/FIXED.md and docs/bugs/_archive/production-sentinel-writes-
bypass-atomic-write/FIXED.md. All writes here go through
``_ctx._atomic_write``.

Module-top ``from ._monolith import`` is safe here (``_monolith`` never
imports this module — no cycle): ``_current_head`` and
``write_completed_receipt`` are monolith-resident until Phase-5 WU-3
(re-pointed to ``.runtimeplane`` / ``.gates`` there).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys

import yaml

from pathlib import Path

from ._ctx import _atomic_write, _diag
from . import docmodel
from .docmodel import (
    PROVISIONAL_SENTINEL,
    _BOLD_STATUS_RE,
    _PHASE_HEADING_RE,
    _evidence_gate_killed,
    _parse_plan_frontmatter,
    _phase_completion_plan,
    classify_blocking_unchecked_rows,
    find_implementation_plans,
    parse_phases,
    parse_sentinel,
    phases_mcp_runtime_not_required,
    repo_has_no_app_surface,
    retro_staleness,
    skip_waiver_refusal,
)
from .gates import (
    autotick_verification_rows,
    commit_drift_verdict,
    evaluate_completion_evidence,
    gate_verdict_ok,
    observation_gap_promotable,
)
from .ledgers import (
    _INTERVENTIONS_DIRNAME,
    _interventions_queue_flag,
    derive_touched_from_brackets,
    derive_touched_from_grep,
    parse_intervention_hypothesis,
    record_intervention,
    write_provenance,
)
from .markers import refuse_if_cycle_active
from ._monolith import (  # Phase-5 WU-3 re-point (write-path helpers still monolith-resident)
    _current_head,
    write_completed_receipt,
)


# ---------------------------------------------------------------------------
# Pseudo-skill dispatcher — deterministic sentinel / receipt writes
# ---------------------------------------------------------------------------

# _current_head is defined once, further below (WU-4 "Persisted probe
# signature / loop detection" section) — it used to be defined a second time
# here with an identical body, an undetected F811 duplicate (silently shadowed
# at module level; production-sentinel-writes-bypass-atomic-write's "bonus
# finding," the proof this file had zero lint coverage). Consumed here by
# apply_pseudo's ``__write_validated_from_results__`` freshness backstop —
# same function, no behavior change.


def _resolve_under_repo(repo_root: Path, value) -> str:
    """Canonicalize a path that may be absolute, repo-relative, or a bare
    basename into one comparable string (lowercased, forward-slashed).

    Used by the WU-3 (unified-pipeline-orchestrator P5) queue trim to match a
    completing feature against a queue entry whose stored ``spec_dir`` may be a
    path-form value ("docs/features/foo") rather than a bare basename ("foo").
    Both the completing dir and each entry's spec_dir are run through this so a
    ``-followups`` entry is matched by its RESOLVED path, not just the basename.
    """
    p = Path(value)
    if not p.is_absolute():
        p = repo_root / p
    try:
        resolved = os.path.realpath(str(p))
    except OSError:
        resolved = str(p)
    return resolved.replace("\\", "/").rstrip("/").lower()


# Marker appended to a struck ROADMAP row (and the idempotency sentinel — a row
# already carrying this token is NOT re-struck).
_ROADMAP_COMPLETE_TOKEN = "✅ COMPLETE"


def _strike_roadmap_row(
    roadmap_path: Path, repo_root: Path, spec_path: Path, feature_id: str
) -> bool:
    """Strike the ROADMAP row(s) referencing the completed feature.

    A row "references" the feature iff it contains the feature_id token OR the
    spec dir basename as a word. Striking = wrap the row's content in ``~~``
    strikethrough and append a `` ✅ COMPLETE`` token. Idempotent: a row that
    already carries the COMPLETE token (or is already ``~~``-wrapped for this
    feature) is left untouched.

    Returns True iff at least one row was newly struck (the file was rewritten).
    Matches the WU-3 deliverable; never raises on a malformed ROADMAP — it
    simply finds no row to strike and returns False (the OSError on read/write
    is surfaced as a warning by the caller).
    """
    text = roadmap_path.read_text(encoding="utf-8")
    basename = spec_path.name
    # A row references the feature if it contains the id or the basename as a
    # whole word (avoids matching a prefix of an unrelated longer slug).
    tokens = {t for t in (feature_id, basename) if t}
    token_res = [re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])") for t in tokens]

    lines = text.splitlines(keepends=True)
    changed = False
    for i, line in enumerate(lines):
        # Skip lines with no trailing newline handling difference — operate on
        # the content, re-attach the original line ending.
        stripped = line.rstrip("\n")
        eol = line[len(stripped):]
        if not any(rx.search(stripped) for rx in token_res):
            continue
        # Idempotency: already struck for this feature → skip.
        if _ROADMAP_COMPLETE_TOKEN in stripped:
            continue
        content = stripped
        # For a markdown table row, strike only the inner cells (keep the
        # leading/trailing pipes structurally intact) so the table still parses;
        # for a bullet/plain line, strike the whole content.
        if content.lstrip().startswith("|") and content.rstrip().endswith("|"):
            inner = content.strip().strip("|")
            new_inner = f" ~~{inner.strip()}~~  {_ROADMAP_COMPLETE_TOKEN} "
            # Preserve any leading indentation before the first pipe.
            lead = content[: len(content) - len(content.lstrip())]
            new_content = f"{lead}|{new_inner}|"
        else:
            new_content = f"~~{content.rstrip()}~~  {_ROADMAP_COMPLETE_TOKEN}"
        lines[i] = new_content + eol
        changed = True

    if changed:
        _atomic_write(roadmap_path, "".join(lines))
    return changed


def _top_status_is(md_path: Path, status_value: str) -> bool:
    """True iff the FIRST ``**Status:**`` line of ``md_path`` reads ``status_value``.

    A file with NO ``**Status:**`` line counts as satisfied — the completion
    sequence's ``re.sub(count=1)`` flip is a no-op there, so a genuinely-done dir
    whose SPEC/PHASES simply carries no top status line must not be forced into a
    resume. An unreadable file also returns True (an IO error must never
    manufacture a partial-apply verdict). Used by
    ``_completion_postconditions_missing``.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return True
    m = re.search(r"^\*\*Status:\*\*[ \t]*(.*?)[ \t]*$", text, re.MULTILINE)
    if m is None:
        return True
    return m.group(1).strip() == status_value


def _roadmap_has_unstruck_row(
    roadmap_path: Path, spec_path: Path, feature_id: str
) -> bool:
    """True iff ROADMAP.md carries a row referencing the feature that is NOT yet
    struck (i.e. ``_strike_roadmap_row`` WOULD rewrite it).

    Read-only mirror of the strike loop's match + ``_ROADMAP_COMPLETE_TOKEN``
    idempotency test — the completion post-condition audit's inverse of the
    ROADMAP strike. An unreadable ROADMAP returns False (the strike itself
    surfaces the OSError as a warning; the audit must not force a resume on it).
    """
    try:
        text = roadmap_path.read_text(encoding="utf-8")
    except OSError:
        return False
    tokens = {t for t in (feature_id, spec_path.name) if t}
    if not tokens:
        return False
    token_res = [re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])") for t in tokens]
    for line in text.splitlines():
        stripped = line.rstrip("\n")
        if not any(rx.search(stripped) for rx in token_res):
            continue
        if _ROADMAP_COMPLETE_TOKEN in stripped:
            continue
        return True
    return False


def _completion_postconditions_missing(
    spec_path: Path,
    repo_root: Path,
    feature_id: str,
    status_value: str,
    is_fixed: bool,
) -> list[str]:
    """Return the list of unsatisfied completion post-conditions for an
    already-receipted dir (empty ⇒ the completion is fully applied → noop).

    The idempotency key of ``apply_pseudo``'s ``__mark_complete__`` /
    ``__mark_fixed__`` branch (mark-complete-partial-apply-noop-unrecoverable).
    The receipt is the FIRST externally-observable post-condition written, so a
    crash between the receipt write and the SPEC status flip leaves a
    receipt-present + ``Status: In-progress`` dir that the receipt-only noop
    could never repair (the state machine re-routed to ``__mark_complete__``
    forever, zero writes). This audit checks EVERY post-condition the state
    machine routes on:

      * SPEC.md / PHASES.md first ``**Status:**`` line == ``status_value``
        (a file with no status line is satisfied — the flip is a no-op there);
      * cleanup sentinels (VALIDATED.md / RETRO_DONE.md / DEFERRED_NON_CLOUD.md)
        absent;
      * feature (complete) path ONLY: the queue.json entry trimmed AND the
        ROADMAP row struck (the bug/fixed path trims via ``archive_fixed`` and
        has no feature ROADMAP, so those two are audited only when not is_fixed).

    Any missing entry means the prior completion died mid-sequence → the caller
    RESUMES the idempotent tail. Pure read; never raises.
    """
    missing: list[str] = []

    spec_md = spec_path / "SPEC.md"
    if spec_md.exists() and not _top_status_is(spec_md, status_value):
        missing.append("SPEC.md status")

    phases_md = spec_path / "PHASES.md"
    if phases_md.exists() and not _top_status_is(phases_md, status_value):
        missing.append("PHASES.md status")

    for cleanup_name in ("VALIDATED.md", "RETRO_DONE.md", "DEFERRED_NON_CLOUD.md"):
        if (spec_path / cleanup_name).exists():
            missing.append(cleanup_name)

    if not is_fixed:
        queue_path = repo_root / "docs" / "features" / "queue.json"
        if queue_path.exists():
            try:
                qdata = json.loads(queue_path.read_text(encoding="utf-8"))
                qitems = qdata.get("queue", [])
                if isinstance(qitems, list):
                    resolved_spec = _resolve_under_repo(repo_root, spec_path)

                    def _entry_matches(e: dict) -> bool:
                        sd = e.get("spec_dir")
                        if sd == spec_path.name or e.get("id") == feature_id:
                            return True
                        if isinstance(sd, str) and sd:
                            if _resolve_under_repo(repo_root, sd) == resolved_spec:
                                return True
                        return False

                    if any(
                        isinstance(e, dict) and _entry_matches(e) for e in qitems
                    ):
                        missing.append("queue.json entry")
            except (json.JSONDecodeError, OSError):
                # A malformed queue is a non-fatal warning at trim time, not a
                # partial-apply signal — do not force a resume on it here.
                pass

        roadmap_path = repo_root / "docs" / "features" / "ROADMAP.md"
        if roadmap_path.exists() and _roadmap_has_unstruck_row(
            roadmap_path, spec_path, feature_id
        ):
            missing.append("ROADMAP.md row")

    return missing


def apply_pseudo(
    repo_root: Path,
    name: str,
    spec_path: Path,
    *,
    plan_path: Path | None = None,
    date: str | None = None,
    feature_id: str | None = None,
    reason: str | None = None,
    deferred_step: int | None = None,
) -> dict:
    """Single-author the deterministic sentinel/receipt write for a lazy pseudo-skill.

    This function is the SOLE AUTHOR of every scripted file write that lazy
    pseudo-skills previously requested via prose instructions.  Moving authorship
    here gives us:
      (1) A machine-verifiable idempotency contract for every named write.
      (2) A single grep-able call-site instead of duplicated skill prose.
      (3) An easy way to dry-run or audit the writes before they happen.

    Return shape (always present — callers may JSON-dump unconditionally):
    ::

        {
            "name":    str,          # the pseudo-skill name
            "ok":      bool,         # True iff the action succeeded (or was a noop)
            "refused": str | None,   # non-None means a precondition was not met
            "wrote":   [str, ...],   # relative paths written (empty on noop/refused)
            "deleted": [str, ...],   # relative paths deleted (empty on noop/refused)
            "noop":    bool,         # True iff the file(s) already existed exactly
        }

    Extra keys some pseudo-skills attach (absent otherwise — callers may still
    JSON-dump unconditionally):
      - ``resumed`` (``__mark_complete__`` / ``__mark_fixed__``): True iff this
        call recovered a crash-window PARTIAL apply — a receipt was already
        present but a completion post-condition was missing, so the idempotent
        tail (SPEC/PHASES flip, sentinel delete, queue trim, ROADMAP strike,
        provenance) was re-applied to converge
        (mark-complete-partial-apply-noop-unrecoverable). False on the normal
        path; a genuinely-done dir returns a plain ``noop`` earlier.
      - ``flipped_phases`` (``__mark_complete__`` / ``__mark_fixed__``): phase
        headings the completion-coherence gate auto-flipped to Complete.
      - ``queue_trimmed`` (``__mark_complete__`` / ``__mark_fixed__``): True iff
        the completed feature's entry was removed from
        ``docs/features/queue.json`` this call. Always False for the bug/fixed
        path (whose queue trim lives in ``archive_fixed`` step 6). Prevents the
        AlgoBooth ``queue.no-completed`` consistency error on feature completion.
      - ``warnings`` (``__write_validated_from_results__``,
        ``__mark_complete__``): non-fatal caveats — freshness caveats (legacy
        results without ``validated_commit``, or an unresolvable HEAD) or a
        malformed ``docs/features/queue.json`` that could not be auto-trimmed;
        also echoed to stderr.

    Parameters
    ----------
    repo_root:
        Root of the repository.  Used by ``__flip_plan_complete_*`` when
        building the relative path returned in ``wrote``, and by
        ``__write_validated_from_results__`` to resolve the current
        ``git rev-parse HEAD`` for the sha-freshness backstop.
    name:
        The pseudo-skill identifier dispatched by the orchestrator.  Recognised
        values are listed below; anything else returns ``refused``.
    spec_path:
        Absolute path to the feature / bug spec directory (contains SPEC.md,
        PHASES.md, plans/, etc.).
    plan_path:
        Override for ``__flip_plan_complete_cloud_saturated__``.  When given, this
        exact file is flipped rather than auto-discovering via
        ``find_implementation_plans``.
    date:
        ISO-8601 date string (``YYYY-MM-DD``) stamped into every receipt.
        Defaults to ``datetime.date.today().isoformat()`` when ``None``.
    feature_id:
        Frontmatter ``feature_id:`` value.  Defaults to ``spec_path.name``.
    reason:
        Human-readable reason for ``__write_deferred_non_cloud__``; defaults to
        ``"deferred to workstation (no Tauri/MCP in cloud)"``.
    deferred_step:
        The step index being deferred; used only by
        ``__write_deferred_non_cloud__``.  Defaults to ``8``.

    Dispatched pseudo-skills
    ------------------------
    ``__write_validated_from_skip__``
        Gate: ``spec_path/SKIP_MCP_TEST.md`` must exist and parse to a non-None
        dict.  Writes ``spec_path/VALIDATED.md`` (kind: validated).  Idempotent:
        if VALIDATED.md already exists and parses kind=="validated" → noop.

    ``__write_validated_from_results__``
        Gates (in order; see the branch comment for why the order is
        load-bearing): (1) ``spec_path/MCP_TEST_RESULTS.md`` must exist,
        carry ``kind: mcp-test-results``, and parse a ``scenarios`` list;
        (2) noop on existing VALIDATED.md with kind=="validated";
        (3) result-literal gate — ``result: all-passing`` AND
        ``pass_count == total_count`` (ints; refusals name expected vs
        found); (4) freshness backstop — ``validated_commit`` must match
        repo_root's current HEAD (legacy field-less files and non-git roots
        pass with a ``warnings`` entry instead).  Writes VALIDATED.md
        copying ``mcp_scenarios`` (and the ``validated_commit`` anchor when
        present) from the results file.

    ``__write_deferred_non_cloud__``
        No gate input.  Writes ``spec_path/DEFERRED_NON_CLOUD.md`` (kind:
        deferred-non-cloud).  Idempotent: file already exists → noop.

    ``__flip_plan_complete_cloud_saturated__``
        Target plan: ``plan_path`` if given, else the single non-Complete plan
        returned by ``find_implementation_plans(spec_path)``.  Regex-replaces
        the first ``status:`` frontmatter line with ``status: Complete``,
        leaving every other byte intact.  Idempotent on already-Complete plan.

    ``__mark_complete__``
        Gate: ``spec_path/VALIDATED.md`` OR ``spec_path/SKIP_MCP_TEST.md``
        must be present.  Writes COMPLETED.md (kind: completed, provenance:
        gated), flips SPEC.md/PHASES.md top-level ``**Status:**``, deletes
        VALIDATED.md / RETRO_DONE.md / DEFERRED_NON_CLOUD.md, TRIMS the
        completed feature's ``docs/features/queue.json`` entry, and STRIKES its
        ``docs/features/ROADMAP.md`` row.  Idempotent on existing COMPLETED.md.

        WU-3 (unified-pipeline-orchestrator P5) enhancements:
          - The queue trim now matches by the RESOLVED ``spec_dir`` (each
            entry's stored ``spec_dir`` resolved against ``repo_root`` and
            compared to the resolved ``spec_path``), in addition to the legacy
            basename + ``id`` keys — so a ``-followups`` entry whose stored
            ``spec_dir`` is a path-form value (not the bare basename) is still
            trimmed, killing the ``-followups`` queue.no-completed recovery
            class. The returned dict's ``queue_trimmed`` reports it.
          - The ROADMAP strike (previously an orchestrator-inline step) is now
            authored HERE: the row referencing the feature is wrapped in ``~~``
            strikethrough + a ``✅ COMPLETE`` token. Idempotent (a row already
            carrying the token is skipped). The returned dict carries
            ``roadmap_struck`` (True iff a row was newly struck this call;
            always False on the bug/fixed path and when no ROADMAP.md exists).

        Completion-coherence gate (Phase 9 WU-1): when PHASES.md exists, BEFORE
        any write the function makes PHASES.md coherent the way the AlgoBooth
        ``check-docs-consistency.ts`` checker requires a Complete SPEC to be —
        (a) AUTO-FLIPS every phase with >=1 checkbox, zero unchecked, and a
        present non-Complete/non-Superseded ``**Status:**`` line to ``Complete``
        (in place; only that line changes), then (b) REFUSES with ZERO writes
        (no receipt, no status flips, no sentinel deletions) when any phase
        would remain incoherent — any unchecked box in a non-Superseded phase
        (verification rows INCLUDED at completion time) or any present
        non-Complete/non-Superseded status with no flip signal. The refusal
        message names each offending phase. Phases with no Status line are
        ignored; PHASES.md absent → gate is a no-op. The returned dict carries an
        extra ``flipped_phases`` key (list of the headings auto-flipped; ``[]``
        when none).

    ``__mark_fixed__``
        Same as ``__mark_complete__`` (including the completion-coherence gate
        and ``flipped_phases`` key) but the receipt file is FIXED.md (kind:
        fixed) and SPEC.md status is flipped to ``Fixed``.  Idempotent on
        existing FIXED.md with kind=="fixed".
    """
    # --- C3 cycle-containment at the LIBRARY boundary (integrity backstop) ---
    # refuse_if_cycle_active was historically invoked ONLY by the lazy-state.py /
    # bug-state.py `--apply-pseudo` CLI wrappers (immediately before this call).
    # That left a direct-import side-door: a dispatched cycle subagent (whose
    # process never inherits the orchestrator's `export LAZY_ORCHESTRATOR=1`) can
    # `import lazy_core` and call `apply_pseudo("__mark_complete__", ...)` in-process,
    # bypassing the CLI-only guard entirely — self-authoring COMPLETED.md + the
    # SPEC/PHASES Complete flip and pushing to main. That is exactly how a
    # first-time-login mcp-test subagent rogue-completed a feature on partial
    # evidence (hardening round, 2026-07). Guarding HERE — the sole author of every
    # scripted completion write — closes the hole no matter the caller:
    #   * The two CLI wrappers already export LAZY_ORCHESTRATOR=1 for the real
    #     orchestrator, so refuse_if_cycle_active returns silently for them
    #     (priority 1 immunity); the extra call is a harmless idempotent no-op.
    #   * A subagent CLI call was already refused at the wrapper; now a subagent
    #     DIRECT library call is refused here too (priority 2/3: LAZY_CYCLE_SUBAGENT
    #     or a present cycle marker → exit 3, zero side effects — refuse_if_cycle_active
    #     runs BEFORE any default resolution or filesystem work below).
    # Immunity honors the SAME LAZY_ORCHESTRATOR=1 signal used by every other
    # guarded op, so orchestrator behavior is byte-unchanged. In-process test
    # callers run with no marker and no subagent env → the guard is a silent no-op.
    refuse_if_cycle_active("apply_pseudo")

    # Resolve defaults for optional keyword arguments.
    if date is None:
        date = datetime.date.today().isoformat()
    if feature_id is None:
        feature_id = spec_path.name

    # Helper: build a minimal refused result without writing anything.
    def _refused(msg: str) -> dict:
        return {
            "name": name,
            "ok": False,
            "refused": msg,
            "wrote": [],
            "deleted": [],
            "noop": False,
        }

    # Helper: build a noop result.
    def _noop() -> dict:
        return {
            "name": name,
            "ok": True,
            "refused": None,
            "wrote": [],
            "deleted": [],
            "noop": True,
        }

    # Helper: build an ok result with specific wrote/deleted lists.
    def _ok(wrote: list[str], deleted: list[str] | None = None) -> dict:
        return {
            "name": name,
            "ok": True,
            "refused": None,
            "wrote": wrote,
            "deleted": deleted or [],
            "noop": False,
        }

    # ---------------------------------------------------------------------------
    # Dispatch
    # ---------------------------------------------------------------------------

    if name == "__grant_skip_no_mcp_surface__":
        # Structural MCP-skip auto-grant (lazy-cycle-containment follow-up).
        # Eliminates the wasted /mcp-test Opus dispatch for a `**MCP runtime:**
        # not-required` feature in a repo that has NO app surface at all
        # (no src-tauri/, no package.json) — there is provably nothing to boot
        # and nothing to probe. Writes SKIP_MCP_TEST.md inline so the next probe
        # routes straight to __write_validated_from_skip__ (no subagent).
        #
        # Defense in depth — refuse unless BOTH structural conditions hold, so
        # this can never auto-waive a feature that actually has an MCP surface.
        # The grant carries granted_by: pipeline-structural, which
        # skip_waiver_refusal RE-VERIFIES against the same predicate downstream.
        if not repo_has_no_app_surface(repo_root):
            return _refused(
                "repo has an app surface (src-tauri/ or package.json present) — "
                "a structural MCP-skip grant is valid ONLY in a repo with no "
                "MCP-reachable surface; route to /mcp-test instead"
            )
        if not phases_mcp_runtime_not_required(spec_path):
            return _refused(
                "PHASES.md does not declare `**MCP runtime:** not-required` — a "
                "structural MCP-skip grant requires the plan to route the feature "
                "as not-required first"
            )
        skip_path = spec_path / "SKIP_MCP_TEST.md"
        existing_skip = parse_sentinel(skip_path)
        # Idempotency: a skip sentinel already on disk → noop (never clobber a
        # richer operator / mcp-test grant).
        if skip_path.exists() and existing_skip is not None and existing_skip.get(
            "kind"
        ) == "skip-mcp-test":
            return _noop()
        head = _current_head(repo_root)
        commit_line = f"validated_commit: {head}\n" if head else ""
        content = (
            "---\n"
            "kind: skip-mcp-test\n"
            f"feature_id: {feature_id}\n"
            "reason: repo has no MCP-reachable surface (no src-tauri/, no "
            "package.json) — nothing to boot, nothing to probe; the MCP gate is "
            "structurally vacuous.\n"
            "alternative_validation: per-phase quality gates ran during "
            "/execute-plan (tests + lint green on each plan part before commit); "
            "this repo has no Tauri app or dev server to validate against.\n"
            f"date: {date}\n"
            "skipped_by: pipeline\n"
            "granted_by: pipeline-structural\n"
            "spec_class: standalone — no app integration (no Tauri/MCP surface "
            "in repo)\n"
            f"{commit_line}"
            "---\n"
            "\n"
            "# MCP Test Skip — structural (no app surface)\n"
            "\n"
            "Granted inline by the state machine: this repo contains no "
            "`src-tauri/` and no `package.json`, so there is no MCP HTTP server / "
            "dev runtime to drive any MCP tool against. The `**MCP runtime:** "
            "not-required` PHASES declaration is re-verified structurally here, so "
            "no /mcp-test subagent is dispatched. `skip_waiver_refusal()` re-checks "
            "the same structural predicate before this waiver can validate — an app "
            "repo (src-tauri/ or package.json present) would be refused.\n"
        )
        _atomic_write(skip_path, content)
        return _ok(["SKIP_MCP_TEST.md"])

    if name == "__write_validated_from_skip__":
        # Gate: SKIP_MCP_TEST.md must be present and parseable.
        skip_path = spec_path / "SKIP_MCP_TEST.md"
        skip_meta = parse_sentinel(skip_path)
        if not skip_path.exists() or skip_meta is None:
            return _refused("SKIP_MCP_TEST.md absent")
        # Provenance gate — the SAME skip_waiver_refusal() helper compute_state
        # consults in lazy-state.py / bug-state.py Step 9: a pipeline-self-
        # granted skip (and a pipeline-authored skip that simply OMITS
        # granted_by, and an mcp-test grant missing its spec_class citation)
        # must NOT vacuously validate. repo_root is passed so a
        # granted_by: pipeline-structural waiver re-verifies the no-app-surface
        # predicate.
        _waiver_refusal = skip_waiver_refusal(skip_meta, repo_root)
        if _waiver_refusal:
            return _refused(f"SKIP_MCP_TEST.md {_waiver_refusal}")
        # Idempotency: if VALIDATED.md already exists as kind=validated → noop.
        validated_path = spec_path / "VALIDATED.md"
        existing = parse_sentinel(validated_path)
        if existing is not None and existing.get("kind") == "validated":
            return _noop()
        # Write VALIDATED.md per sentinel-frontmatter.md schema.
        content = (
            "---\n"
            "kind: validated\n"
            f"feature_id: {feature_id}\n"
            f"date: {date}\n"
            "mcp_scenarios: []\n"
            "result: all-passing\n"
            "---\n"
            "\n"
            "# Validated\n"
            "\n"
            "Validated from SKIP_MCP_TEST.md — MCP test was explicitly skipped "
            "per the skip sentinel; validation recorded by apply_pseudo.\n"
        )
        _atomic_write(validated_path, content)
        return _ok(["VALIDATED.md"])

    elif name == "__write_validated_from_results__":
        # Script-executed VALIDATED.md derivation (2026-06-11 hardening): this
        # was the LAST pseudo-skill the orchestrator hand-wrote, bypassing all
        # integrity gates — a hand-authored VALIDATED.md could mint a passing
        # certification from a failing or stale results file. The gates below
        # make the derivation refuse instead.
        #
        # Gate ORDER (load-bearing — mirrors __mark_complete__'s ordering rule):
        #   1. Evidence gate (presence + kind + scenarios) — BEFORE the noop,
        #      exactly as __mark_complete__'s evidence-kind gate precedes its
        #      receipt-noop: a content-less or mis-kinded results file is a
        #      malformation to surface, not a state to noop over.
        #   2. VALIDATED.md noop (idempotent) — BEFORE the result-literal and
        #      freshness backstops, so re-running against an already-validated
        #      dir never re-refuses (the Phase-9/11 receipt-noop rule).
        #   3. Result-literal + count gate — the frontmatter must show a
        #      genuinely passing run: result == "all-passing" (the canonical
        #      passing literal per sentinel-frontmatter.md; failing runs carry
        #      "partial") AND pass_count == total_count as integers.
        #   4. Freshness backstop — validated_commit (the sha anchor the
        #      /mcp-test producers record) must match repo_root's current
        #      HEAD; stale results must not mint a fresh VALIDATED.md.
        #      Legacy files without the field (and non-git roots) are allowed
        #      with a warning, mirroring the state scripts' Step-9 leniency.
        results_path = spec_path / "MCP_TEST_RESULTS.md"
        results_meta = parse_sentinel(results_path)
        if results_meta is None:
            return _refused(
                "MCP_TEST_RESULTS.md absent — run /mcp-test to produce a "
                "results file before deriving VALIDATED.md"
            )
        if results_meta.get("kind") != "mcp-test-results":
            return _refused(
                "MCP_TEST_RESULTS.md exists but lacks 'kind: mcp-test-results' "
                f"frontmatter (parsed kind: {results_meta.get('kind')!r}) — "
                "refusing to derive VALIDATED.md from an unrecognized file"
            )
        if not isinstance(results_meta.get("scenarios"), list):
            return _refused(
                "MCP_TEST_RESULTS.md is missing its scenarios: list — "
                "cannot derive mcp_scenarios for VALIDATED.md"
            )
        scenarios = results_meta["scenarios"]

        # Idempotency: if VALIDATED.md already exists as kind=validated → noop.
        # Runs BEFORE the result-literal/freshness backstops (see ORDER above).
        validated_path = spec_path / "VALIDATED.md"
        existing = parse_sentinel(validated_path)
        if existing is not None and existing.get("kind") == "validated":
            return _noop()

        # Result-literal gate: only the canonical passing literal mints a
        # VALIDATED.md. The refusal names expected vs found so the orchestrator
        # can't guess-loop. (Real results files use "all-passing" / "partial";
        # one legacy file carries "pass" — deliberately NOT accepted, the
        # schema's passing literal is "all-passing".)
        #
        # Gap-1 observation-gap scoped-validated disposition
        # (harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 1):
        # a SECOND accepted route, strictly ADDITIVE to the all-passing path. A
        # feature whose every MCP-DRIVEABLE assertion passed but whose remaining
        # surfaces are SPEC-locked observation gaps (no MCP control-API tool exists
        # to drive them end-to-end; locked to the unit/WDIO test tier per
        # docs/features/mcp-testing/SPEC.md) honestly carries `result: partial`.
        # The pre-fix binary all-passing/refuse gate looped /mcp-test forever for
        # that shape (the only escape was an operator hand-editing the literal — a
        # manual bypass, not a sanctioned disposition). This is SPEC-CONSISTENT:
        # building MCP UI drivers for these surfaces would contradict
        # mcp-testing/SPEC.md's locked unit/WDIO test-tier decision, so "accept the
        # documented observation-gap exemption" is the correct disposition, not a
        # missing test.
        #
        # The promotion is gated NARROWLY — a `result: partial` promotes ONLY when
        # BOTH hold: (a) every entry in `observation_gap_exemptions` carries a
        # non-empty `spec_class` provenance string referencing the untestable class
        # (mirroring the SKIP_MCP_TEST.md `spec_class`-required discipline — the
        # citation is what distinguishes a verified assessment from a convenience
        # skip), AND (b) the MCP-driveable scope is fully passing
        # (pass_count == total_count, enforced by the count cross-check below). A
        # `partial` with NO exemptions, with a provenance-less exemption, or with a
        # genuine MCP-scope failure (pass_count < total_count) falls through to the
        # EXISTING refusal — the genuine-failure refusal is NOT relaxed.
        result_literal = results_meta.get("result")
        observation_gap_exemptions = results_meta.get("observation_gap_exemptions")
        # Shared predicate (observation_gap_promotable) — the SINGLE home for the
        # scoped observation-gap partial rule, mirrored across this apply gate,
        # the completion-integrity gate, and the Step-9 routing so they cannot
        # diverge. This is HALF the AND: the count cross-check below
        # (pass_count == total_count) is the other half and refuses a genuine
        # MCP-scope failure on its own.
        observation_gap_promotion = observation_gap_promotable(results_meta)
        if result_literal != "all-passing" and not observation_gap_promotion:
            return _refused(
                f"MCP_TEST_RESULTS.md result is {result_literal!r} — expected "
                "'all-passing' (the canonical passing literal); a non-passing "
                "run must not mint VALIDATED.md. Re-run /mcp-test until all "
                "scenarios pass, or route the failure (BLOCKED/add-phase). "
                "(An observation-gap promotion requires a populated "
                "observation_gap_exemptions list whose every entry carries a "
                "spec_class provenance AND a fully-passing MCP-driveable scope.)"
            )

        # Count cross-check: the literal alone is not trusted — pass_count must
        # equal total_count, both present as integers. YAML booleans are ints
        # in Python (True == 1) but are NOT counts → rejected; digit strings
        # (quoted YAML) are coerced, matching validation_escalation's tolerance.
        def _coerce_count(raw):
            if isinstance(raw, bool):
                return None
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str) and raw.strip().isdigit():
                return int(raw.strip())
            return None

        raw_pass = results_meta.get("pass_count")
        raw_total = results_meta.get("total_count")
        pass_count = _coerce_count(raw_pass)
        total_count = _coerce_count(raw_total)
        if pass_count is None or total_count is None:
            return _refused(
                "MCP_TEST_RESULTS.md pass_count/total_count missing or "
                f"malformed (pass_count: {raw_pass!r}, total_count: "
                f"{raw_total!r}) — expected both as integers; the counts are "
                "the cross-check behind the result literal"
            )
        if pass_count != total_count:
            return _refused(
                f"MCP_TEST_RESULTS.md pass_count ({pass_count}) != total_count "
                f"({total_count}) — expected pass_count == total_count for a "
                "passing run; a partial pass must not mint VALIDATED.md"
            )

        # Freshness backstop: the results' validated_commit sha anchor must
        # match the target repo's current HEAD. Legacy files without the field
        # are allowed with a warning (the schema requires it going forward);
        # a non-git repo_root (HEAD unresolvable) also warns rather than
        # refusing, mirroring the state scripts' permissive Step-9 skip.
        warnings: list[str] = []
        recorded_commit = results_meta.get("validated_commit")
        # Presence-based (not truthiness): an unquoted all-zeros sha YAML-parses
        # as int 0 (falsy) — that file RECORDED a commit and must hit the
        # freshness gate, not silently downgrade to the legacy-absent path.
        if recorded_commit is not None:
            head = _current_head(repo_root)
            if head is None:
                warnings.append(
                    f"could not resolve HEAD for {repo_root} — "
                    "validated_commit freshness UNVERIFIED"
                )
            elif str(recorded_commit) != head:
                # Drift detected. Route through the SHARED commit_drift_verdict
                # helper (the same docs-only carve-out evaluate_completion_evidence
                # uses) so this apply gate cannot diverge from the Step-9 routing.
                # WHY this is not a gate-weakening: an /mcp-test cycle that obeys
                # its clean-tree contract MUST commit MCP_TEST_RESULTS.md, and
                # that commit advances HEAD exactly one past the validated_commit
                # it recorded — so a PURE DOCS-ONLY (*.md) one-commit drift is
                # STRUCTURALLY UNAVOIDABLE and strict equality is unsatisfiable
                # (the 2026-06-23 re-verify DEADLOCK — hardening-log Round 36).
                # Docs-only drift → accept-and-mint with a warning. Any non-.md
                # (source/script/config) drift STILL refuses (genuine TOCTOU: the
                # validated code is not the code being promoted).
                drift = commit_drift_verdict(repo_root, recorded_commit, head)
                if drift["verdict"] == "docs-only":
                    warnings.append(
                        f"validated_commit {recorded_commit} != HEAD {head} but "
                        "the drift is docs-only (*.md) — accepting (the "
                        "MCP_TEST_RESULTS.md commit itself is the expected "
                        "one-commit docs-only lag; no source/script/config drift)"
                    )
                else:
                    # non-docs-drift OR unresolvable → refuse-and-revalidate.
                    detail = (
                        f"source/script/config drift "
                        f"({', '.join(drift['non_docs'][:5])})"
                        if drift["verdict"] == "non-docs-drift"
                        else "the diff could not be resolved"
                    )
                    return _refused(
                        f"MCP_TEST_RESULTS.md is stale: validated_commit "
                        f"{recorded_commit} does not match current HEAD {head} "
                        f"with {detail} — stale results must not mint a fresh "
                        "VALIDATED.md; re-run /mcp-test against the current code"
                    )
        else:
            warnings.append(
                "MCP_TEST_RESULTS.md has no validated_commit field (legacy) — "
                "freshness UNVERIFIED; new results files MUST record `git "
                "rev-parse HEAD` per sentinel-frontmatter.md"
            )

        # Emit mcp_scenarios with yaml.safe_dump so that scenario strings
        # containing ":", ",", or "]" are properly quoted and round-trip
        # through parse_sentinel back to the original Python list unchanged.
        # yaml.safe_dump with default_flow_style=True produces a compact
        # flow-sequence like ['audio: no dropout', 'load, stress'].
        # .strip() removes the trailing newline that safe_dump appends.
        scenarios_inline = yaml.safe_dump(scenarios, default_flow_style=True).strip()
        # Carry the results' sha anchor into VALIDATED.md's optional
        # validated_commit field (sentinel-frontmatter.md documents it as the
        # SAME freshness anchor) so downstream consumers keep the match
        # between certification and the exact code it ran against.
        commit_line = (
            f"validated_commit: {recorded_commit}\n"
            if recorded_commit is not None else ""
        )
        # Gap-1: carry the observation-gap exemptions forward onto the receipt so
        # the SCOPED nature of the validation is auditable — a scoped-validated
        # VALIDATED.md must NOT impersonate a clean all-passing certification that
        # hides the untestable surfaces. The receipt's `result:` records
        # `validated-modulo-observation-gaps` (vs `all-passing`) and embeds the
        # exemptions block (round-tripped through yaml.safe_dump so spec_class
        # strings containing ':' / ',' quote correctly and parse_sentinel reads
        # them back unchanged).
        if observation_gap_promotion:
            exemptions_block = yaml.safe_dump(
                observation_gap_exemptions, default_flow_style=False
            ).strip()
            # Indent the multi-line block under the `observation_gap_exemptions:`
            # key so it is valid YAML frontmatter.
            exemptions_indented = "\n".join(
                "  " + ln if ln else ln for ln in exemptions_block.splitlines()
            )
            result_field = "validated-modulo-observation-gaps"
            exemptions_line = f"observation_gap_exemptions:\n{exemptions_indented}\n"
            body_note = (
                "Derived from MCP_TEST_RESULTS.md by the "
                "__write_validated_from_results__ gate (apply_pseudo): "
                "SCOPED-validated — every MCP-driveable assertion passed "
                f"({pass_count}/{total_count}), and the remaining surfaces are "
                f"documented observation-gap exemptions "
                f"({len(observation_gap_exemptions)}) verified against "
                "docs/features/mcp-testing/SPEC.md's unit/WDIO test tier. Building "
                "MCP UI drivers for these surfaces would contradict that "
                "SPEC-locked decision, so this is the SPEC-consistent disposition.\n"
            )
        else:
            result_field = "all-passing"
            exemptions_line = ""
            body_note = (
                "Derived from MCP_TEST_RESULTS.md by the "
                "__write_validated_from_results__ gate (apply_pseudo): result "
                f"all-passing, {pass_count}/{total_count} scenarios passing.\n"
            )
        content = (
            "---\n"
            "kind: validated\n"
            f"feature_id: {feature_id}\n"
            f"date: {date}\n"
            f"mcp_scenarios: {scenarios_inline}\n"
            f"result: {result_field}\n"
            f"{exemptions_line}"
            f"{commit_line}"
            "---\n"
            "\n"
            "# Validated\n"
            "\n"
            f"{body_note}"
        )
        _atomic_write(validated_path, content)
        result = _ok(["VALIDATED.md"])
        if warnings:
            # Surface in BOTH channels: the JSON result (for the orchestrator,
            # like flipped_phases) and stderr (for a human watching the run).
            result["warnings"] = warnings
            for w in warnings:
                sys.stderr.write(f"WARNING: {w}\n")
        return result

    elif name == "__write_deferred_non_cloud__":
        # No gate input — this write is always permitted.
        deferred_path = spec_path / "DEFERRED_NON_CLOUD.md"
        # Idempotency: file already exists → noop.
        if deferred_path.exists():
            return _noop()
        step = deferred_step if deferred_step is not None else 8
        resolved_reason = reason if reason is not None else "deferred to workstation (no Tauri/MCP in cloud)"
        content = (
            "---\n"
            "kind: deferred-non-cloud\n"
            f"feature_id: {feature_id}\n"
            f"deferred_step: {step}\n"
            f"reason: {resolved_reason}\n"
            "deferred_by: lazy-cloud\n"
            f"date: {date}\n"
            "---\n"
            "\n"
            "# Deferred Non-Cloud\n"
            "\n"
            "This feature step requires a local Tauri/MCP environment and has been "
            "deferred to the workstation for completion.\n"
        )
        _atomic_write(deferred_path, content)
        return _ok(["DEFERRED_NON_CLOUD.md"])

    elif name == "__flip_plan_complete_cloud_saturated__":
        # Resolve the target plan file.
        if plan_path is not None:
            target_plan = plan_path
        else:
            # find_implementation_plans returns only non-Complete plans.
            # We need exactly one; zero or multiple → refused.
            plans_dir = spec_path / "plans"
            if not plans_dir.exists():
                return _refused(
                    "no plan_path given and plans/ directory not found under spec_path"
                )
            non_complete = find_implementation_plans(spec_path)
            if len(non_complete) == 0:
                return _refused(
                    "no plan_path given and no non-Complete implementation plans found"
                )
            if len(non_complete) > 1:
                return _refused(
                    f"no plan_path given and {len(non_complete)} non-Complete plans found "
                    f"— provide --plan to disambiguate"
                )
            target_plan = non_complete[0]
        # Use _parse_plan_frontmatter to inspect the status without touching the
        # body — this lets us decide noop/refuse before doing any textual rewrite.
        fm = _parse_plan_frontmatter(target_plan)
        if fm is None:
            # File could not be read at all.
            return _refused("plan file could not be read")

        # Locate the YAML frontmatter fence span in the raw text so the textual
        # rewrite is scoped to the frontmatter block only.  A body line that
        # happens to start with "status: ..." must not be altered.
        raw = target_plan.read_text(encoding="utf-8")
        lines = raw.splitlines(keepends=True)

        # Locate the opening "---" fence (first non-blank line).
        fence_open: int | None = None
        for idx, line in enumerate(lines):
            if line.strip():
                if line.strip() == "---":
                    fence_open = idx
                break
        if fence_open is None:
            # File has no valid frontmatter block — refuse; do not touch the body.
            return _refused("plan file has no valid YAML frontmatter block (no opening ---)")

        # Locate the closing "---" fence.
        fence_close: int | None = None
        for idx in range(fence_open + 1, len(lines)):
            if lines[idx].strip() == "---":
                fence_close = idx
                break
        if fence_close is None:
            return _refused("plan file has no valid YAML frontmatter block (missing closing ---)")

        # Check for a ``status:`` key inside the frontmatter span.
        # fm is {} when there is no frontmatter; a dict when frontmatter parsed OK.
        # _parse_plan_frontmatter returns {} for a no-frontmatter file, but we
        # already ruled that out above.  If the parsed dict has no "status" key
        # the plan is malformed — refuse rather than silently inserting one.
        if "status" not in (fm or {}):
            return _refused("plan frontmatter has no status: field")

        current_status = (fm or {}).get("status", "")
        if str(current_status).strip() == "Complete":
            # Already Complete → noop (idempotent).
            return _noop()

        # Find the FIRST ``status:`` line within the frontmatter span and rewrite
        # only that line.  Every other byte — both frontmatter and body — is
        # left unchanged.
        status_re = re.compile(r"^(status:\s*\S.*)$")
        new_lines = list(lines)
        replaced = False
        for idx in range(fence_open + 1, fence_close):
            if status_re.match(lines[idx]):
                # Preserve the original line ending (splitlines(keepends=True)).
                original_ending = ""
                if lines[idx].endswith("\r\n"):
                    original_ending = "\r\n"
                elif lines[idx].endswith("\n"):
                    original_ending = "\n"
                elif lines[idx].endswith("\r"):
                    original_ending = "\r"
                new_lines[idx] = "status: Complete" + original_ending
                replaced = True
                break  # only the first occurrence

        if not replaced:
            # status key was in parsed YAML but no matching line found in the
            # fence span — this is a parse/text inconsistency; refuse safely.
            return _refused(
                "plan frontmatter parsed a status: value but no status: line found "
                "in the frontmatter text span — refusing to rewrite"
            )

        new_raw = "".join(new_lines)
        _atomic_write(target_plan, new_raw)
        # Report the plan path relative to repo_root when possible, else just name.
        try:
            rel = str(target_plan.relative_to(repo_root))
        except ValueError:
            rel = target_plan.name
        return _ok([rel])

    elif name in ("__mark_complete__", "__mark_fixed__"):
        # Determine whether this is a complete or fixed operation.
        is_fixed = name == "__mark_fixed__"
        receipt_filename = "FIXED.md" if is_fixed else "COMPLETED.md"
        receipt_kind = "fixed" if is_fixed else "completed"
        status_value = "Fixed" if is_fixed else "Complete"

        # Gate: validation evidence must be present AND carry the correct
        # sentinel kind. parse_sentinel returns {} (which is `not None`) for a
        # file with NO frontmatter, so a bare existence-plus-parse check would
        # let a content-less `touch VALIDATED.md` satisfy the gate and mint a
        # provenance: gated receipt. Require kind: validated (VALIDATED.md) /
        # kind: skip-mcp-test (SKIP_MCP_TEST.md) — consistent with the
        # idempotency check below that already requires kind == receipt_kind.
        validated_path = spec_path / "VALIDATED.md"
        skip_path = spec_path / "SKIP_MCP_TEST.md"
        validated_meta = parse_sentinel(validated_path)
        has_validated = (
            validated_meta is not None
            and validated_meta.get("kind") == "validated"
        )
        skip_meta = parse_sentinel(skip_path)
        has_skip = (
            skip_meta is not None
            and skip_meta.get("kind") == "skip-mcp-test"
        )
        if not has_validated and not has_skip:
            # Distinguish "evidence file present but malformed/content-less"
            # from "evidence absent" so the operator sees exactly why the gate
            # refused (and what kind: field the file must carry).
            malformed: list[str] = []
            if validated_meta is not None:
                malformed.append(
                    "VALIDATED.md exists but lacks 'kind: validated' "
                    f"frontmatter (parsed kind: {validated_meta.get('kind')!r})"
                )
            if skip_meta is not None:
                malformed.append(
                    "SKIP_MCP_TEST.md exists but lacks 'kind: skip-mcp-test' "
                    f"frontmatter (parsed kind: {skip_meta.get('kind')!r})"
                )
            if malformed:
                return _refused(
                    "validation evidence rejected — " + "; ".join(malformed)
                )
            return _refused(
                "no validation evidence (VALIDATED.md/SKIP_MCP_TEST.md) present "
                "to fold into receipt"
            )

        # Idempotency / crash-recovery audit
        # (mark-complete-partial-apply-noop-unrecoverable). The OLD check noop'd
        # on receipt-existence ALONE — but the receipt is the FIRST
        # externally-observable post-condition written, so a crash between the
        # receipt write and the SPEC status flip left a receipt-present +
        # `Status: In-progress` dir that the receipt-only noop could NEVER
        # repair: the state machine re-routed to __mark_complete__ every probe,
        # zero writes, unrecoverable loop.
        #
        # Now: receipt present → AUDIT every completion post-condition
        # (_completion_postconditions_missing). ALL satisfied → noop (genuinely
        # done — preserves the re-completing-never-re-refuses rule; this still
        # runs BEFORE the retro-staleness / provisional / coherence gates below,
        # exactly where the noop sat). ANY missing → RESUME: skip the gates +
        # receipt write + intervention capture (steps 1–4) and re-apply only the
        # idempotent tail (steps 5–10) to converge — mirroring archive_fixed's
        # in-file resume-not-noop posture. The tail steps are each individually
        # idempotent (count=1 status sub, exists-guarded deletes, no-op
        # trims/strikes), so re-running them is safe.
        receipt_path = spec_path / receipt_filename
        existing_receipt = parse_sentinel(receipt_path)
        receipt_present = (
            existing_receipt is not None
            and existing_receipt.get("kind") == receipt_kind
        )
        resuming = False
        if receipt_present:
            missing_postconditions = _completion_postconditions_missing(
                spec_path, repo_root, feature_id, status_value, is_fixed
            )
            if not missing_postconditions:
                # Genuinely done — carry resumed=False so the key is consistently
                # present on every __mark_complete__/__mark_fixed__ return.
                done = _noop()
                done["resumed"] = False
                return done
            resuming = True
            _diag(
                f"apply_pseudo {name}: receipt present but PARTIAL apply detected "
                f"(missing: {', '.join(missing_postconditions)}) — resuming the "
                "idempotent completion tail (steps 5–10)"
            )

        # --- Retro-staleness backstop (Phase 11 WU-5d + WU-5e) ---
        # Mechanical second key behind the state scripts' Step-8 staleness
        # routing (WU-5c lazy-state, WU-5e bug-state): when RETRO_DONE.md
        # recorded fewer phase sections than PHASES.md carries NOW, corrective
        # phases landed after the retro concluded — the retro graded work it
        # never saw finished, so completion must refuse until a fresh retro
        # round runs. ZERO writes: this check sits BEFORE the coherence gate's
        # auto-flip writes, and AFTER the receipt-noop above (matching the
        # Phase-9 ordering rule — re-completing an already-receipted dir never
        # re-refuses). Covers BOTH __mark_complete__ AND __mark_fixed__: the
        # original WU-5 scoping assumed bugs have no retro step, but
        # bug-state.py has its own Step 8 (retro-feature) and bug dirs carry
        # the identical RETRO_DONE.md + PHASES.md shape, so the bug pipeline
        # needs the same backstop. Missing field / missing PHASES.md →
        # retro_staleness returns None (grandfathered, pre-Phase-11 behavior).
        # Skipped on a RESUME: the receipt already exists, so this gate passed
        # pre-receipt on the crashed run — re-refusing here would trade a silent
        # loop for a wrong halt.
        _staleness = None if resuming else retro_staleness(spec_path)
        if _staleness is not None:
            _now_count, _retro_count = _staleness
            return _refused(
                f"retro is stale: {_now_count} phases now vs "
                f"{_retro_count} at retro — route a retro round before "
                "completion"
            )

        # --- Provisional-ratification backstop (park-provisional-acceptance,
        # SPEC D6 layer c — the load-bearing one). A feature/bug carrying an
        # unratified NEEDS_INPUT_PROVISIONAL.md was auto-accepted on a
        # recommendation under --park-provisional and the operator has not yet
        # ratified (or redirected) that choice. Completion MUST refuse with
        # ZERO writes until the sentinel is neutralized by the ratification
        # affordance — a provisionally-decided item can never silently
        # complete. Sits AFTER the receipt-noop (re-completing an
        # already-receipted dir never re-refuses) and BEFORE any auto-tick
        # write, matching the retro-staleness ordering rule above.
        if not resuming and (spec_path / PROVISIONAL_SENTINEL).exists():
            return _refused(
                f"unratified provisional decision(s) — {PROVISIONAL_SENTINEL} "
                "present; ratify or redirect via the provisional-ratification "
                "affordance before completion"
            )

        # --- anti-overfit-design-gate D3 ship seam (STATE-lane SEAM-DEFERRED
        # diff, PHASES.md Phase 3 Implementation Notes) — the completion-gate
        # half of the harness-change design gate. Re-derives whether this
        # item's shipped commits touch a committed control surface
        # (docs/gate/control-surfaces.json); a scoped item with a missing,
        # failing, or unsigned-gate-weakening GATE_VERDICT.md refuses with
        # ZERO writes. Out-of-scope / no manifest present -> no-op (in_scope:
        # False), so this is inert everywhere the manifest doesn't exist —
        # see gate_verdict_ok's own docstring for the honesty rail (this
        # feature is itself unratified/structurally-provisional; deleting the
        # manifest reverts this seam cleanly with zero code changes).
        if not resuming:
            _gv = gate_verdict_ok(spec_path, repo_root)
            if not _gv["ok"]:
                return _refused(
                    f"harness-change design gate: {_gv['reason']} — author/"
                    "repair GATE_VERDICT.md (see "
                    "_components/harness-change-gate.md) before completion"
                )

        # --- Evidence-gated auto-tick of certified verification rows ---
        # (completion-coherence-gate-reconciliation Phase 3). BEFORE the
        # coherence gate's residual-incoherence check, consult the on-disk
        # /mcp-test evidence (evaluate_completion_evidence). When that verdict
        # AUTHORIZES (exempt-and-tick / warn-exempt) and the kill-switch is OFF,
        # rewrite the remaining unchecked verification-marked rows to ``- [x]``
        # (autotick_verification_rows) FIRST, so the coherence re-check below
        # then sees ZERO unchecked verification rows and proceeds. A genuine
        # unchecked *implementation* row (no marker) is NOT touched by the
        # rewrite, so the coherence gate still refuses naming its phase — evidence,
        # not the checkbox, is the source of truth.
        #
        # Order (load-bearing): tick → re-check → write receipt. The receipt's
        # ``auto_ticked_rows`` records how many rows the gate mutated.
        #
        # Kill-switch (LAZY_STRICT_EVIDENCE_GATE / LAZY_DISABLE_AUTOTICK): when
        # truthy, the auto-tick is skipped entirely → the coherence gate falls
        # back to the legacy strict path (verification rows INCLUDED in
        # refusals), restoring byte-identical pre-feature behavior with no code
        # revert.
        auto_ticked_rows = 0
        strict_gate = _evidence_gate_killed()
        phases_md_path = spec_path / "PHASES.md"
        if not resuming and phases_md_path.exists() and not strict_gate:
            verdict = evaluate_completion_evidence(spec_path, repo_root)
            if verdict["verdict"] in ("exempt-and-tick", "warn-exempt"):
                tick_res = autotick_verification_rows(
                    phases_md_path,
                    verdict.get("validated_commit"),
                    verdict.get("pass_count") or 0,
                )
                # A cardinality-lock abort (ok: False) leaves the file
                # byte-unchanged; the coherence gate below then refuses on the
                # still-unchecked rows (the over-tick guard surfaces at the live
                # gate, exactly as the Phase-1/2 contract requires).
                if tick_res.get("ok"):
                    auto_ticked_rows = tick_res.get("ticked_count", 0)

        # --- Completion-coherence gate (Phase 9 WU-1) ---
        # Before minting the receipt and flipping the top-level Status, make
        # PHASES.md coherent the way AlgoBooth's check-docs-consistency.ts
        # requires a Complete SPEC to be: every phase Complete/Superseded with no
        # unchecked boxes. We (a) AUTO-FLIP all-ticked non-terminal phases to
        # Complete (deterministic, mirrors the checker's all-checked-but-not-
        # complete rule) and (b) REFUSE with ZERO writes when any phase would
        # remain incoherent after that flip (unchecked boxes incl. verification
        # rows NOT auto-ticked above, or a present non-Complete/non-Superseded
        # status with no flip signal). When PHASES.md is absent the gate is a
        # no-op (preserves the pre-Phase-9 behavior). ``flipped_phases`` records
        # the headings flipped.
        flipped_phases: list[str] = []
        if not resuming and phases_md_path.exists():
            # Re-read: the auto-tick above may have rewritten the file.
            phases_text = phases_md_path.read_text(encoding="utf-8")
            parsed_phases = parse_phases(phases_text)
            to_flip, refusals = _phase_completion_plan(parsed_phases)
            if refusals:
                # Residual incoherence → refuse with no filesystem writes at all
                # (no receipt, no status flips, no sentinel deletions). Name each
                # offending phase so the orchestrator can route a corrective
                # coherence cycle (per the Phase 9 refusal contract).
                #
                # ACTIONABLE advisory (harden 2026-07): split the blocking
                # unchecked rows into un-migrated verification-shim rows (clear via
                # canonical-marker migration — IF the verification actually ran)
                # vs genuine incomplete deliverables, so the orchestrator/operator
                # can tell a marker migration from real work. Diagnostic only — the
                # refusal decision is unchanged.
                cls = classify_blocking_unchecked_rows(phases_text)
                advisory = ""
                if cls["shim"] or cls["genuine"]:
                    advisory = (
                        f" — of the blocking unchecked row(s), {len(cls['shim'])} "
                        f"are un-migrated verification-shim rows (under a "
                        f"Runtime-Verification subsection WITHOUT the canonical "
                        f"{docmodel._VERIFICATION_ONLY_MARKER} marker) and "
                        f"{len(cls['genuine'])} are genuine incomplete "
                        f"deliverable(s). Migrating a shim row to the canonical "
                        f"marker lets the gate auto-tick it — but ONLY when its "
                        f"verification ACTUALLY ran; a row that could not run on "
                        f"this host must be deferred, not migrated (per-row "
                        f"host-deferral is an open design question)."
                    )
                    if cls["shim"]:
                        advisory += " Shim rows: " + " | ".join(cls["shim"])
                    if cls["genuine"]:
                        # completion-gate-refusal-opacity Fix Scope §2: print the
                        # genuine excerpts (not just the count) — previously
                        # collected at classify_blocking_unchecked_rows() above
                        # and discarded here.
                        advisory += " Genuine rows: " + " | ".join(cls["genuine"])
                return _refused(
                    f"PHASES.md is incoherent for completion — "
                    f"{len(refusals)} phase(s) block the receipt: "
                    + "; ".join(refusals)
                    + advisory
                )
            if to_flip:
                # Apply the auto-flips IN PLACE: rewrite ONLY the first
                # ``**Status:**`` line inside each to-be-flipped phase's section,
                # leaving every other byte (including line endings) untouched.
                flip_headings = {ph["heading"] for ph in to_flip}
                src_lines = phases_text.splitlines(keepends=True)
                out_lines: list[str] = []
                in_phase_to_flip = False
                status_flipped_this_phase = False
                in_fence = False
                for raw in src_lines:
                    stripped = raw.strip()
                    if stripped.startswith("```"):
                        in_fence = not in_fence
                        out_lines.append(raw)
                        continue
                    if not in_fence and _PHASE_HEADING_RE.match(raw):
                        # Entering a new phase section — decide if it's a flip target.
                        in_phase_to_flip = stripped in flip_headings
                        status_flipped_this_phase = False
                        out_lines.append(raw)
                        continue
                    if (
                        not in_fence
                        and in_phase_to_flip
                        and not status_flipped_this_phase
                        and _BOLD_STATUS_RE.match(stripped)
                    ):
                        # Flip ONLY this line's value to Complete; preserve the
                        # original line ending so byte-stability holds elsewhere.
                        ending = ""
                        if raw.endswith("\r\n"):
                            ending = "\r\n"
                        elif raw.endswith("\n"):
                            ending = "\n"
                        elif raw.endswith("\r"):
                            ending = "\r"
                        out_lines.append("**Status:** Complete" + ending)
                        status_flipped_this_phase = True
                        continue
                    out_lines.append(raw)
                _atomic_write(phases_md_path, "".join(out_lines))
                flipped_phases = [ph["heading"] for ph in to_flip]

        # --- (a) Fold evidence ---
        validated_via = "mcp" if has_validated else "skip-mcp-test"

        # Optionally copy pass_count / total_count from MCP_TEST_RESULTS.md.
        mcp_pass_count: int | None = None
        mcp_total_count: int | None = None
        results_path = spec_path / "MCP_TEST_RESULTS.md"
        results_meta = parse_sentinel(results_path)
        if results_meta:
            raw_pass = results_meta.get("pass_count")
            raw_total = results_meta.get("total_count")
            if isinstance(raw_pass, int):
                mcp_pass_count = raw_pass
            if isinstance(raw_total, int):
                mcp_total_count = raw_total

        # Write the receipt (SKIPPED on a RESUME — the receipt already exists and
        # re-writing it would clobber its original provenance / completed_commit /
        # auto_ticked_rows). The idempotent tail below re-applies steps 5–10 only.
        wrote: list[str] = []
        if not resuming:
            body_note = (
                f"Feature {feature_id} marked {status_value.lower()} via "
                f"apply_pseudo on {date}. Validated via: {validated_via}."
            )

            # Write the receipt using the existing helper.
            # code-doc-provenance-linkage Phase 1 (D4): anchor the receipt to the
            # HEAD at flip time. write_completed_receipt has always supported the
            # field; this call site simply never passed it. A non-git repo_root
            # resolves None → the field is omitted (legacy byte-shape preserved).
            write_completed_receipt(
                receipt_path,
                feature_id,
                date,
                provenance="gated",
                kind=receipt_kind,
                completed_commit=_current_head(repo_root),
                validated_via=validated_via,
                mcp_pass_count=mcp_pass_count,
                mcp_total_count=mcp_total_count,
                auto_ticked_rows=auto_ticked_rows,
                body_note=body_note,
            )
            wrote = [receipt_filename]

        # --- Intervention capture (intervention-efficacy-tracking D1-A) ---
        # AFTER the receipt write (the receipt is the completion's core; the
        # record is additive) and BEHIND the receipt-noop guard above (a
        # re-completion never re-captures). Eligibility (D2-A): the repo's
        # top-level `"interventions": true` queue flag OR a present
        # `## Intervention Hypothesis` SPEC block — otherwise this branch is
        # byte-inert (no keys, no file; every non-opted-in repo unchanged).
        # FAIL-OPEN: any capture error degrades to a `warnings` entry — the
        # completion stands; capture can never fail a completion.
        # SKIPPED on a RESUME: the record is written once at the original
        # completion (guarded by its own record-exists noop anyway); a resume
        # re-applies only the idempotent tail, never re-captures.
        intervention_result: dict | None = None
        intervention_warnings: list[str] = []
        try:
            _spec_md_path = spec_path / "SPEC.md"
            _hyp_present = False
            if not resuming and _spec_md_path.exists():
                _hyp_present = parse_intervention_hypothesis(
                    _spec_md_path.read_text(encoding="utf-8")
                ) is not None
            if not resuming and (_interventions_queue_flag(repo_root) or _hyp_present):
                intervention_result = record_intervention(
                    repo_root,
                    feature_id,
                    pipeline="bug" if is_fixed else "feature",
                    spec_path=spec_path,
                    date=date,
                    provenance="gated",
                )
        except Exception as exc:  # noqa: BLE001 — capture is fail-open
            intervention_warnings.append(
                f"intervention capture failed ({exc}) — the completion "
                f"stands; record docs/{_INTERVENTIONS_DIRNAME}/"
                f"{feature_id}.md was not written (re-capture manually via "
                f"--record-intervention)"
            )

        # --- (b) Flip status lines in SPEC.md and PHASES.md ---
        status_line_re = re.compile(r"^\*\*Status:\*\*.*$", re.MULTILINE)

        spec_md_path = spec_path / "SPEC.md"
        if spec_md_path.exists():
            spec_text = spec_md_path.read_text(encoding="utf-8")
            # Replace the first **Status:** line only.
            new_spec_text = status_line_re.sub(
                f"**Status:** {status_value}", spec_text, count=1
            )
            if new_spec_text != spec_text:
                _atomic_write(spec_md_path, new_spec_text)
                wrote.append("SPEC.md")

        phases_md_path = spec_path / "PHASES.md"
        if phases_md_path.exists():
            phases_text = phases_md_path.read_text(encoding="utf-8")
            new_phases_text = status_line_re.sub(
                f"**Status:** {status_value}", phases_text, count=1
            )
            if new_phases_text != phases_text:
                _atomic_write(phases_md_path, new_phases_text)
                wrote.append("PHASES.md")

        # --- (c) Delete cleanup sentinels ---
        # Delete VALIDATED.md, RETRO_DONE.md, DEFERRED_NON_CLOUD.md if present.
        # KEEP: SKIP_MCP_TEST.md, MCP_TEST_RESULTS.md, the receipt file itself.
        deleted: list[str] = []
        for cleanup_name in ("VALIDATED.md", "RETRO_DONE.md", "DEFERRED_NON_CLOUD.md"):
            cleanup_path = spec_path / cleanup_name
            if cleanup_path.exists():
                cleanup_path.unlink()
                deleted.append(cleanup_name)

        # --- (d) Trim the completed feature's entry from the feature queue ---
        # Symmetric to the BUG pipeline, whose ``archive_fixed`` (step 6) removes
        # the fixed bug from ``docs/bugs/queue.json``. The feature pipeline has no
        # archive step — a completed feature stays in place and only its SPEC
        # status flips — so WITHOUT this trim the feature's queue.json entry
        # lingers forever. AlgoBooth's check-docs-consistency.ts ``queue.no-completed``
        # rule then HARD-ERRORS on every feature completion (the queue is the
        # active-work list; a Complete/Superseded entry is pure noise). Match on
        # ``spec_dir`` (== this dir's name) OR ``id`` (== feature_id), mirroring
        # the bug trim's match keys. Idempotent: only rewrites when an entry was
        # actually removed (a re-run after the receipt-noop above never reaches
        # here, and a queue already trimmed is a no-write pass).
        #
        # ONLY the feature (complete) path trims here — the bug (fixed) path's
        # queue lives at docs/bugs/queue.json and is trimmed by archive_fixed,
        # so trimming it here too would be a no-op at best and a double-author at
        # worst. Gate on ``not is_fixed``.
        #
        # Malformed-queue policy: unlike archive_fixed (which refuses with a
        # PARTIAL-STATE diagnostic because its move already happened and the
        # consumer commits), the receipt + status flips here are the completion's
        # core and are already on disk. Refusing post-write would mis-report the
        # completion as failed. So a malformed queue.json degrades to a
        # non-fatal ``warnings`` entry — the completion stands; the operator is
        # told the queue could not be auto-trimmed and must be fixed by hand
        # (the lingering entry will surface as the same queue.no-completed error
        # this trim exists to prevent, so the signal is preserved either way).
        queue_trimmed = False
        queue_warnings: list[str] = []
        if not is_fixed:
            queue_path = repo_root / "docs" / "features" / "queue.json"
            if queue_path.exists():
                try:
                    qdata = json.loads(queue_path.read_text(encoding="utf-8"))
                    qitems = qdata.get("queue", [])
                    if isinstance(qitems, list):
                        # WU-3 (unified-pipeline-orchestrator P5): match by the
                        # RESOLVED spec_dir, not just the basename. The queue
                        # entry's stored ``spec_dir`` can be a path-form value
                        # (e.g. "docs/features/foo-followups") that does NOT
                        # equal the dir basename (``spec_path.name``). The legacy
                        # basename-only match MISSED those entries, leaving a
                        # ``-followups`` feature lingering and tripping AlgoBooth's
                        # ``queue.no-completed`` consistency error. We now resolve
                        # BOTH the completing dir and each entry's spec_dir
                        # (against repo_root) and compare the canonical paths,
                        # keeping the basename + id matches as additional
                        # (backward-compatible) keys.
                        resolved_spec = _resolve_under_repo(repo_root, spec_path)

                        def _entry_matches(e: dict) -> bool:
                            sd = e.get("spec_dir")
                            if sd == spec_path.name or e.get("id") == feature_id:
                                return True
                            if isinstance(sd, str) and sd:
                                if _resolve_under_repo(repo_root, sd) == resolved_spec:
                                    return True
                            return False

                        kept = [
                            e for e in qitems
                            if not (isinstance(e, dict) and _entry_matches(e))
                        ]
                        if len(kept) != len(qitems):
                            qdata["queue"] = kept
                            _atomic_write(
                                queue_path, json.dumps(qdata, indent=2) + "\n"
                            )
                            queue_trimmed = True
                    else:
                        queue_warnings.append(
                            "docs/features/queue.json 'queue' field is not an "
                            "array — could not auto-trim the completed entry"
                        )
                except (json.JSONDecodeError, OSError) as exc:
                    queue_warnings.append(
                        f"docs/features/queue.json could not be auto-trimmed "
                        f"({exc}) — fix it by hand to clear the queue.no-completed "
                        "error"
                    )

        # --- (e) Strike the completed feature's ROADMAP row ---
        # WU-3 (unified-pipeline-orchestrator P5): the ROADMAP strikethrough was
        # previously an orchestrator-inline step (the "one remaining orchestrator
        # step" after __mark_complete__). Moving it INTO apply_pseudo makes the
        # completion a single deterministic author for SPEC/PHASES/queue/ROADMAP.
        # Only the feature (complete) path strikes (bugs have no feature ROADMAP).
        # Idempotent: a row already struck (already ~~wrapped~~ or carrying a
        # COMPLETE token) is left untouched, so a re-run is a no-write pass — and
        # the whole branch sits BEHIND the receipt-noop guard above, so a noop
        # re-entry never reaches here.
        roadmap_struck = False
        if not is_fixed:
            roadmap_path = repo_root / "docs" / "features" / "ROADMAP.md"
            if roadmap_path.exists():
                try:
                    struck = _strike_roadmap_row(
                        roadmap_path, repo_root, spec_path, feature_id
                    )
                    if struck:
                        wrote.append("ROADMAP.md")
                        roadmap_struck = True
                except OSError as exc:
                    queue_warnings.append(
                        f"docs/features/ROADMAP.md could not be auto-struck "
                        f"({exc}) — strike the completed row by hand"
                    )

        # --- (f) Provenance ledger (code-doc-provenance-linkage Phase 2) ---
        # AFTER the receipt write + queue trim + ROADMAP strike (the
        # completion's core is already durable), distill the item into
        # IMPLEMENTED.md + merge its touched-file rows into the committed
        # reverse index — via the ONE producer (write_provenance, D1-B).
        # Derivation (D4): recorded commit brackets primary; message-grep as
        # the explicitly-marked fallback (legacy items / cross-machine gaps).
        # FAILURE CONTAINMENT: any provenance failure degrades to a
        # ``warnings[]`` entry (the malformed-queue-trim policy) — completion
        # is NEVER blocked by its own bookkeeping.
        provenance_written = False
        try:
            derived = derive_touched_from_brackets(repo_root, feature_id)
            prov_derivation = "commit-brackets"
            if derived is None:
                derived = derive_touched_from_grep(repo_root, feature_id)
                prov_derivation = "message-grep"
            counts_part = (
                f" ({mcp_pass_count}/{mcp_total_count})"
                if mcp_pass_count is not None and mcp_total_count is not None
                else ""
            )
            prov_validated_line = (
                f"Validated via: {validated_via}{counts_part}. "
                f"Receipt: {receipt_filename} (provenance: gated)."
            )
            prov_result = write_provenance(
                repo_root, spec_path, feature_id,
                "bug" if is_fixed else "feature",
                derived["commits"], derived["files"],
                provenance="pipeline-gated",
                derivation=prov_derivation,
                date=date,
                validated_line=prov_validated_line,
            )
            if prov_result.get("ok"):
                provenance_written = True
                wrote.extend(prov_result.get("wrote", []))
            else:
                queue_warnings.append(
                    "provenance ledger could not be written "
                    f"({prov_result.get('refused')}) — the completion stands; "
                    "re-link via --link-provenance"
                )
        except Exception as exc:  # noqa: BLE001 — bookkeeping never blocks
            queue_warnings.append(
                f"provenance ledger could not be written ({exc}) — the "
                "completion stands; re-link via --link-provenance"
            )

        # Attach the Phase 9 WU-1 ``flipped_phases`` key (the per-phase headings
        # the completion-coherence gate auto-flipped to Complete this call).
        # Empty list when nothing needed flipping; documented in the docstring.
        result = _ok(wrote, deleted)
        # mark-complete-partial-apply-noop-unrecoverable: True iff this call was a
        # crash-window RESUME (receipt already present, a post-condition was
        # missing, and the idempotent tail was re-applied to converge). False on
        # the normal completion path and on a genuinely-done noop (which returns
        # earlier). The re-applied artifacts are surfaced via wrote/deleted.
        result["resumed"] = resuming
        result["flipped_phases"] = flipped_phases
        # auto_ticked_rows: count of verification rows the evidence-gated gate
        # auto-ticked this call (completion-coherence-gate-reconciliation Phase
        # 3). 0 when the kill-switch is set, the verdict did not authorize, or
        # there were no unchecked verification rows. Orchestrator-visible,
        # matching the flipped_phases surfacing pattern.
        result["auto_ticked_rows"] = auto_ticked_rows
        # WU: feature-queue trim — True iff a queue.json entry was removed this
        # call (always False for the bug/fixed path, whose trim lives in
        # archive_fixed). Callers may JSON-dump unconditionally.
        result["queue_trimmed"] = queue_trimmed
        # WU-3 (unified-pipeline-orchestrator P5): True iff a ROADMAP row was
        # struck this call (always False for the bug/fixed path and when no
        # ROADMAP.md exists or the row was already struck).
        result["roadmap_struck"] = roadmap_struck
        # code-doc-provenance-linkage Phase 2: True iff the IMPLEMENTED.md
        # distillate + index rows were written this call (False on a contained
        # provenance failure — see the warnings[] entry it leaves behind).
        result["provenance_written"] = provenance_written
        # intervention-efficacy-tracking D1-A: attach the capture keys ONLY
        # when capture fired (eligibility met) — a non-opted-in repo's result
        # stays byte-identical to pre-feature. `intervention_recorded` is True
        # for a fresh record AND for an existing-record noop (the record
        # exists either way — e.g. a prior D9 backfill).
        if intervention_result is not None:
            result["intervention_recorded"] = bool(
                intervention_result.get("recorded")
                or intervention_result.get("noop")
            )
            result["intervention_record"] = intervention_result.get("path")
        all_warnings = intervention_warnings + queue_warnings
        if all_warnings:
            existing_warnings = result.get("warnings") or []
            result["warnings"] = existing_warnings + all_warnings
            for w in all_warnings:
                print(f"WARNING: {w}", file=sys.stderr)
        return result

    else:
        # Unknown pseudo-skill name — never crash, always refuse gracefully.
        return _refused(f"unknown pseudo-skill: {name}")
