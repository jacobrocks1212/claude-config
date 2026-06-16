#!/usr/bin/env python3
"""
lazy_core.py — Domain-agnostic helpers extracted from lazy-state.py.

This module contains infrastructure and parsing utilities that are shared
between lazy-state.py and (in Phase 2) bug-state.py. All functions here
are pure helpers with no dependency on the /lazy pipeline's domain-specific
logic (queue loading, ROADMAP semantics, cloud/device branching, etc.).

Extracted as part of WU-1.2 (zero-behavior-change refactor). The acceptance
contract is that lazy-state.py's ``--test`` output is byte-identical before
and after extraction.

Public API (stable for Phase 2 reuse):
  Infrastructure:
    _atomic_write(path, content)
    _die(msg, path)
    _diag(msg)
    clear_diagnostics()

  Sentinel / plan parsing:
    parse_sentinel(path)
    _parse_plan_frontmatter(path)
    _plan_status(path)
    _plan_lowest_phase(path)
    _plan_series_index(path)
    _plan_sort_key(path)
    _plan_phase_set(path)
    _unchecked_wus_in_plan_scope(phases_text, phase_set)
    find_implementation_plans(spec_dir)
    find_retro_plans(spec_dir)
    latest_retro_plan(spec_dir)
    _has_any_complete_plan(spec_dir)
    retro_plan_has_significant_divergences(plan_path)

  PHASES.md analysis:
    count_deliverables(phases_text)
    remaining_unchecked_are_verification_only(phases_text)
    _VERIFICATION_SECTION_RE

  Receipts:
    write_completed_receipt(path, feature_id, date, *, provenance, ...)
    has_completion_receipt(spec_dir)
    spec_status(spec_dir)
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("lazy_core.py requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

# Diagnostics collected across helper calls. compute_state() in lazy-state.py
# resets this at the start of each invocation via clear_diagnostics(), and
# merges the list into the returned state dict before returning. Callers in
# lazy-state.py reference lazy_core._diag / lazy_core.clear_diagnostics so
# they mutate THIS list, not a separate copy.
_DIAGNOSTICS: list[str] = []


def _diag(msg: str) -> None:
    """Append a diagnostic message to the shared _DIAGNOSTICS list."""
    _DIAGNOSTICS.append(msg)


def clear_diagnostics() -> None:
    """Reset the shared _DIAGNOSTICS list (call once per compute_state invocation)."""
    _DIAGNOSTICS.clear()


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (temp file in the same dir + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _die(msg: str, path: Path | None = None) -> None:
    """Emit error JSON to stdout and exit 2."""
    out = {
        "error": msg,
        "path": str(path) if path else None,
    }
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Sentinel parsing (per _components/sentinel-frontmatter.md)
# ---------------------------------------------------------------------------

_FENCE = "---"


def parse_sentinel(path: Path) -> dict[str, Any] | None:
    """Parse a sentinel file's YAML frontmatter. Returns dict or None if absent."""
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        _die(f"cannot read sentinel: {exc}", path)
        return None  # pragma: no cover

    lines = raw.splitlines()
    # Skip leading blank lines
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != _FENCE:
        # No frontmatter — treat as legacy/freeform; return empty dict so callers
        # can distinguish "file exists" from "file absent".
        return {}

    # Find closing fence
    start = i + 1
    end = None
    for j in range(start, len(lines)):
        if lines[j].strip() == _FENCE:
            end = j
            break
    if end is None:
        _die("sentinel frontmatter missing closing '---'", path)
        return None  # pragma: no cover

    yaml_body = "\n".join(lines[start:end])
    try:
        data = yaml.safe_load(yaml_body) or {}
    except yaml.YAMLError as exc:
        _die(f"invalid YAML frontmatter: {exc}", path)
        return None  # pragma: no cover
    if not isinstance(data, dict):
        _die("sentinel frontmatter must be a YAML mapping", path)
        return None  # pragma: no cover
    return data


# Pipeline-authored `skipped_by` values. A SKIP_MCP_TEST.md whose skipped_by
# identifies the pipeline as the author but which carries NO granted_by field
# is the omission side-door skip_waiver_refusal() closes — without this list,
# simply leaving granted_by off the frontmatter bypassed the WU-5 provenance
# gate (absent was unconditionally treated as legacy-operator).
_PIPELINE_SKIPPED_BY = ("lazy", "lazy-cloud", "pipeline")


# App-surface detection for the structural MCP-skip short-circuit
# (lazy-cycle-containment follow-up). A repo with NO Tauri app and NO npm
# package has no MCP-reachable / dev-server surface at all, so a feature whose
# PHASES declares `**MCP runtime:** not-required` is MECHANICALLY untestable.
# The pipeline may grant the MCP skip inline (no /mcp-test subagent) WITHOUT
# weakening skip_waiver_refusal: that gate RE-VERIFIES this same predicate
# before accepting a ``granted_by: pipeline-structural`` waiver, so a repo that
# actually has an app surface can never auto-waive.
_APP_SURFACE_MARKERS = ("src-tauri", "package.json")


def repo_has_no_app_surface(repo_root: Path) -> bool:
    """True iff repo_root contains neither a ``src-tauri/`` dir nor ``package.json``.

    Mechanical proof that the repo has no Tauri/MCP/npm surface to drive an MCP
    HTTP tool against. Conservative by design: ANY marker present → False (an app
    surface may exist, so the skip must be EARNED by /mcp-test, not auto-granted),
    and an unreadable repo root → False (cannot prove absence).
    """
    try:
        if (repo_root / "src-tauri").is_dir():
            return False
        if (repo_root / "package.json").is_file():
            return False
    except OSError:
        return False
    return True


def phases_mcp_runtime_not_required(spec_path: Path) -> bool:
    """True iff ``spec_path/PHASES.md`` declares ``**MCP runtime:** not-required``.

    The PHASES ``**MCP runtime:**`` line is authored by /spec-phases at
    decomposition time and is ROUTING, not a waiver — it gates the structural
    MCP-skip short-circuit alongside repo_has_no_app_surface().
    """
    phases_path = spec_path / "PHASES.md"
    if not phases_path.exists():
        return False
    try:
        text = phases_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"(?mi)^\*\*MCP runtime:\*\*\s*not-required\b", text))


def skip_waiver_refusal(
    meta: dict[str, Any] | None, repo_root: Path | None = None
) -> str | None:
    """Return a refusal reason when a SKIP_MCP_TEST.md waiver lacks trustworthy provenance.

    Single source of truth for the Step-9 / pseudo-skill provenance gate —
    called by lazy-state.py and bug-state.py (Step 9, cloud + workstation
    branches) and by apply_pseudo's ``__write_validated_from_skip__``.
    Returns None when the waiver is acceptable, else a human-readable reason
    fragment (callers prefix it with the sentinel filename / feature name).

    Provenance contract (sentinel-frontmatter.md ``granted_by``):
      - ``operator`` — human-reviewed waiver: accepted.
      - ``mcp-test`` — granted by an /mcp-test validation cycle after
        cross-checking docs/features/mcp-testing/SPEC.md. Accepted ONLY when
        the sentinel also carries a non-empty ``spec_class`` field citing the
        untestable class it verified — the citation is what distinguishes a
        verified structural assessment from a convenience skip.
      - ``pipeline-structural`` — auto-granted inline by the state machine for a
        ``**MCP runtime:** not-required`` feature in a repo with no app surface
        (lazy-cycle-containment follow-up). Accepted ONLY when ``repo_root`` is
        provided AND ``repo_has_no_app_surface(repo_root)`` RE-VERIFIES (no
        ``src-tauri/`` and no ``package.json``). This re-check is what keeps the
        gate intact: an app repo re-verifies to False and the waiver is refused,
        so a structural grant can never vacuously validate a feature that
        actually has an MCP-reachable surface.
      - ``pipeline`` (or any unrecognized value) — self-granted by a
        non-validation pipeline step: refused.
      - absent — legacy files predate the field. Accepted UNLESS ``skipped_by``
        identifies a pipeline author (``lazy`` / ``lazy-cloud`` / ``pipeline``):
        a pipeline-written skip with no provenance field is refused, closing
        the omission loophole.
    """
    meta = meta or {}
    granted = meta.get("granted_by")
    if granted == "operator":
        return None
    if granted == "mcp-test":
        spec_class = str(meta.get("spec_class") or "").strip()
        if spec_class:
            return None
        return (
            "is granted_by: mcp-test without a spec_class citation — an "
            "mcp-test-granted skip must cite the untestable class it verified "
            "against docs/features/mcp-testing/SPEC.md (add `spec_class: "
            "<class>`), or an operator must confirm via granted_by: operator."
        )
    if granted == "pipeline-structural":
        # Structural auto-grant: accept ONLY when the no-app-surface predicate
        # re-verifies against the live repo. This does not weaken the gate — it
        # is a mechanical re-proof, not a trust-the-sentinel bypass.
        if repo_root is not None and repo_has_no_app_surface(repo_root):
            return None
        return (
            "is granted_by: pipeline-structural but the repo has an app surface "
            "(src-tauri/ or package.json present) or the structural check could "
            "not be re-verified — a structural skip is valid ONLY in a repo with "
            "no MCP-reachable surface. Run /mcp-test to earn the skip, or have an "
            "operator confirm via granted_by: operator."
        )
    if granted is None:
        if meta.get("skipped_by") in _PIPELINE_SKIPPED_BY:
            return (
                f"was written by the pipeline (skipped_by: "
                f"{meta.get('skipped_by')}) with NO granted_by provenance — a "
                "pipeline-authored skip cannot vacuously validate without "
                "provenance. Set granted_by: mcp-test (+ spec_class) if an "
                "/mcp-test cycle verified structural untestability, or have an "
                "operator confirm via granted_by: operator."
            )
        # Legacy file with no provenance fields at all — grandfathered as
        # operator-granted (backward compatibility for pre-WU-5 sentinels).
        return None
    # "pipeline" and any unrecognized value: refuse.
    return (
        f"was granted_by: {granted} (self-granted) — a pipeline-granted MCP "
        "skip needs operator confirmation before it can vacuously validate. "
        "Reconcile via NEEDS_INPUT or update granted_by to 'operator'."
    )


# ---------------------------------------------------------------------------
# Validation-escalation predicate (Phase 11 WU-1a)
# ---------------------------------------------------------------------------

# Suffix the Step-3 blocked terminal appends to notify_message when the
# escalation fires. Defined HERE (not in the state scripts) so lazy-state.py
# and bug-state.py emit the byte-identical message — the orchestrators key
# corrective-phase drafting discipline on this exact text.
VALIDATION_ESCALATION_SUFFIX = (
    " ESCALATION: 2+ validation failures — corrective phase requires a "
    "full-chain seam audit, not a single-layer fix."
)


def validation_escalation(meta: dict[str, Any] | None) -> bool:
    """Return True when a BLOCKED.md sentinel shows repeated MCP-validation failure.

    Single source of truth for the Phase 11 WU-1a escalation policy, consumed
    by BOTH state scripts' Step-3 blocked terminals: ``blocker_kind ==
    "mcp-validation"`` AND ``retry_count >= 2``. The threshold is 2 because the
    d8-live-looping pattern showed each BLOCKED→add-phase round discovering
    exactly ONE more broken layer — by the second failure a single-layer
    corrective fix is presumptively insufficient and the corrective phase needs
    a full-chain seam audit.

    Tolerances (backward compatibility — pre-Phase-11 sentinels must never
    escalate or crash):
      - ``retry_count`` as an int is used directly.
      - ``retry_count`` as a string of digits (quoted YAML) is coerced.
      - Missing/malformed ``retry_count``, missing ``blocker_kind``, a non-
        mcp-validation ``blocker_kind``, or a None/empty meta → False.
      - YAML booleans are ints in Python (``True == 1``); they are NOT counts,
        so bool values are explicitly rejected rather than coerced.
    """
    meta = meta or {}
    if meta.get("blocker_kind") != "mcp-validation":
        return False
    raw = meta.get("retry_count")
    # bool is an int subclass — `retry_count: true` must not coerce to 1.
    if isinstance(raw, bool):
        return False
    if isinstance(raw, int):
        return raw >= 2
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip()) >= 2
    # Missing or malformed → no escalation (never crash the blocked terminal).
    return False


# ---------------------------------------------------------------------------
# SPEC parsing helpers
# ---------------------------------------------------------------------------

def spec_status(spec_path: Path | None) -> str | None:
    """Return the feature SPEC.md ``**Status:**`` value (first occurrence), or None.

    The first ``**Status:**`` line wins; later occurrences are usually inside
    Implementation Notes blocks describing prior state.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    Default behavior (SPEC.md filename) is preserved byte-for-byte.
    """
    if spec_path is None:
        return None
    spec_md = spec_path / "SPEC.md"
    if not spec_md.exists():
        return None
    try:
        for line in spec_md.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\*\*Status:\*\*\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return None


def has_completion_receipt(spec_path: Path | None, filename: str = "COMPLETED.md") -> bool:
    """True iff a durable, content-valid completion receipt exists in the feature/bug dir.

    The receipt is written ONLY by ``__mark_complete__``'s completion-integrity
    gate (or backfilled with ``provenance: backfilled-unverified``). Its presence
    AND content validity are the structural proof that a feature reached
    ``Complete`` THROUGH the pipeline gate rather than via an out-of-band
    SPEC/ROADMAP edit. See _components/completion-integrity-gate.md.

    Content-validation contract:
    - ``spec_path is None`` → ``False`` (silently; no directory to check).
    - Receipt file absent → ``False`` (silently; normal not-yet-complete case).
    - Receipt file present but MALFORMED → ``False`` + emit a ``_diag()``
      diagnostic naming the path and the specific defect. Malformed means any of:
        * empty file / no YAML frontmatter (``parse_sentinel`` returns ``{}``)
        * ``kind`` key absent from frontmatter
        * ``kind`` value not in ``{"completed", "fixed"}``
        * ``provenance`` key absent or its value is empty/whitespace
      These cases count as "completion-unverified" and halt the gate just as if
      the file were absent, while producing a loud diagnostic so the issue can
      be investigated.
    - Receipt file present and valid → ``True``.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    Default receipt filename is ``COMPLETED.md`` — matches current behavior.
    Bug-state.py passes ``filename="FIXED.md"`` for the bug receipt convention.
    """
    if spec_path is None:
        return False

    receipt_path = spec_path / filename
    if not receipt_path.exists():
        # Normal not-yet-complete case — absence is silent, not a diagnostic.
        return False

    # Receipt file exists — validate its content before trusting it.
    meta = parse_sentinel(receipt_path)

    if meta is None:
        # parse_sentinel calls _die() internally for fatal parse errors; this
        # branch is a safety net in case it ever returns None without dying.
        _diag(
            f"completion receipt at {receipt_path} could not be parsed"
            " (parse_sentinel returned None) — treating as missing"
        )
        return False

    # Empty dict means the file existed but had no YAML frontmatter fence at all.
    if not meta:
        _diag(
            f"completion receipt at {receipt_path} has no YAML frontmatter"
            " — treating as missing (expected '---' fence with kind + provenance)"
        )
        return False

    # Validate 'kind' field.
    kind = meta.get("kind")
    if kind not in {"completed", "fixed"}:
        _diag(
            f"completion receipt at {receipt_path} has invalid or missing 'kind'"
            f" (got {kind!r}; expected 'completed' or 'fixed')"
            " — treating as missing"
        )
        return False

    # Validate 'provenance' field — must be present and non-empty.
    provenance = meta.get("provenance")
    if not provenance or not str(provenance).strip():
        _diag(
            f"completion receipt at {receipt_path} is missing or has empty 'provenance'"
            f" (got {provenance!r})"
            " — treating as missing (provenance is required to trust the receipt)"
        )
        return False

    return True


def build_parked_entry(item_id: str, sentinel_path: Path) -> dict[str, Any]:
    """Build a parked-entry record for use in the ``parked[]`` output array.

    Called by lazy-state.py and bug-state.py when ``--park-needs-input`` mode
    is active and a queue entry carries an unresolved NEEDS_INPUT.md.  The
    returned dict is appended to the module-level ``_PARKED`` list in each
    script so the orchestrator can surface every parked item without halting.

    Contract (locked by WU-1 Phase 4 tests in test_lazy_core.py):
      - ``"id"``             → ``item_id`` (str), unchanged.
      - ``"sentinel"``       → ``str(sentinel_path)``.
      - ``"decision_count"`` → ``len(decisions)`` where ``decisions`` is the
                               ``decisions:`` YAML list in the NEEDS_INPUT.md
                               frontmatter; **0** if absent, empty, or not a list.
      - ``"parked_since"``   → the ``date:`` frontmatter value (str), or
                               ``None`` if absent.

    Reuses ``parse_sentinel()`` for frontmatter parsing.  Missing file,
    missing field, and wrong-type (scalar) inputs are handled defensively and
    do not raise.  Structurally corrupt frontmatter (missing closing fence,
    invalid YAML, non-mapping root) routes through ``parse_sentinel``'s
    ``_die()`` → ``sys.exit(2)``, consistent with all other sentinel parsing
    in this codebase.
    """
    meta = parse_sentinel(sentinel_path) or {}
    decisions = meta.get("decisions")
    if not isinstance(decisions, list):
        decision_count = 0
    else:
        decision_count = len(decisions)
    parked_since = meta.get("date")
    # Coerce to str if present (YAML may deserialize dates as date objects).
    if parked_since is not None:
        parked_since = str(parked_since)
    return {
        "id": item_id,
        "sentinel": str(sentinel_path),
        "decision_count": decision_count,
        "parked_since": parked_since,
    }


def write_completed_receipt(
    path: Path,
    feature_id: str,
    date: str,
    *,
    provenance: str,
    kind: str = "completed",
    completed_commit: str | None = None,
    validated_via: str | None = None,
    mcp_pass_count: int | None = None,
    mcp_total_count: int | None = None,
    body_note: str = "",
) -> None:
    """Write a completion receipt (kind: completed by default) per sentinel-frontmatter.md.

    ``provenance: gated`` is written by the completion-integrity gate at flip
    time; ``provenance: backfilled-unverified`` is written by --backfill-receipts
    for features grandfathered in during the receipt-gating rollout.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    The ``kind: completed`` value and the ``# Completion Receipt`` title are
    the defaults that preserve byte-for-byte behavior at all existing call sites.

    ``kind`` is keyword-only and defaults to ``"completed"`` so that lazy-state.py's
    feature pipeline behavior is unchanged.  bug-state.py passes ``kind="fixed"``
    so that FIXED.md receipts carry the correct ``kind: fixed`` frontmatter value
    required by the Phase-5 consistency checker.
    """
    lines = [
        "---",
        f"kind: {kind}",
        f"feature_id: {feature_id}",
        f"date: {date}",
        f"provenance: {provenance}",
    ]
    if completed_commit:
        lines.append(f"completed_commit: {completed_commit}")
    if validated_via:
        lines.append(f"validated_via: {validated_via}")
    if mcp_pass_count is not None and mcp_total_count is not None:
        lines.append(f"mcp_pass_count: {mcp_pass_count}")
        lines.append(f"mcp_total_count: {mcp_total_count}")
    lines.append("---")
    lines.append("")
    lines.append("# Completion Receipt")
    lines.append("")
    if body_note:
        lines.append(body_note)
        lines.append("")
    _atomic_write(path, "\n".join(lines))


# ---------------------------------------------------------------------------
# Stale-upstream helpers
# ---------------------------------------------------------------------------

_STALE_UPSTREAM_FILENAME = "STALE_UPSTREAM.md"


def read_stale_upstream(item_dir: Path) -> str | None:
    """Return the full text of <item_dir>/STALE_UPSTREAM.md, or None if absent."""
    path = item_dir / _STALE_UPSTREAM_FILENAME
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_stale_upstream(item_dir: Path, diff: str) -> None:
    """Write <item_dir>/STALE_UPSTREAM.md with diff as its content (atomic)."""
    path = item_dir / _STALE_UPSTREAM_FILENAME
    _atomic_write(path, diff)


def clear_stale_upstream(item_dir: Path) -> None:
    """Remove <item_dir>/STALE_UPSTREAM.md; no-op if absent."""
    path = item_dir / _STALE_UPSTREAM_FILENAME
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Materialized-list helpers
# ---------------------------------------------------------------------------

_MATERIALIZED_FILENAME = "materialized.json"


def read_materialized(work_dir: Path) -> list[dict]:
    """Read <work_dir>/materialized.json and return the list of records.

    Returns an empty list if the file is absent.
    """
    path = work_dir / _MATERIALIZED_FILENAME
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_materialized(work_dir: Path, wi_id, feature_id, changed_date) -> None:
    """Append a record to <work_dir>/materialized.json (atomic, idempotent on wi_id).

    If a record with the given wi_id already exists, this is a no-op — the
    existing record's values are preserved and no duplicate is written.
    """
    records = read_materialized(work_dir)
    for record in records:
        if record.get("wi_id") == wi_id:
            return
    records.append({
        "wi_id": wi_id,
        "feature_id": feature_id,
        "materialized_changedDate": changed_date,
    })
    path = work_dir / _MATERIALIZED_FILENAME
    _atomic_write(path, json.dumps(records, indent=2))


def update_materialized_changeddate(work_dir: Path, wi_id, new_changed_date) -> None:
    """Update the materialized_changedDate for the record matching wi_id (atomic).

    If no record with the given wi_id is found, this is a no-op (no exception).
    """
    records = read_materialized(work_dir)
    found = False
    for record in records:
        if record.get("wi_id") == wi_id:
            record["materialized_changedDate"] = new_changed_date
            found = True
            break
    if not found:
        return
    path = work_dir / _MATERIALIZED_FILENAME
    _atomic_write(path, json.dumps(records, indent=2))


# ---------------------------------------------------------------------------
# Stage derivation
# ---------------------------------------------------------------------------

_WIP_FILENAME = "WIP.md"
_REVIEWED_FILENAME = "REVIEWED.md"


def derive_stage(item_dir) -> str:
    """Derive the current workflow stage of an item directory from its artifact set.

    Stage is DERIVED from filesystem artifacts (never asserted by a skill directly).
    Accepts any path-like object; coerces to Path internally. Never raises on a
    missing directory — returns "spec" as the documented default.

    Precedence (first match wins):
      1. done          — COMPLETED.md or FIXED.md receipt present (terminal; intentionally
                         wins over halt sentinels because receipts are permanent, irreversible).
      2. stale-upstream — STALE_UPSTREAM.md present (read_stale_upstream is not None).
      3. blocked       — BLOCKED.md present.
      4. needs-input   — NEEDS_INPUT.md present.
      5. reviewed      — REVIEWED.md present.
      6. review        — PR.md present AND PHASES.md present.  If PR.md is absent, this
                         rung is skipped and the artifact-ladder result (implement or lower)
                         stands — "omit PR.md and let implement stand" fallback.
      Artifact ladder:
      7. implement     — plans/ subdir with ≥1 *.md file AND PHASES.md has ≥1 checked
                         deliverable (line matching r"^\\s*-\\s*\\[[xX]\\]").
      8. plan          — plans/ subdir with ≥1 *.md file (but zero checked deliverables).
      9. phases        — PHASES.md exists (but no plans/).
     10. research      — RESEARCH.md or RESEARCH_SUMMARY.md exists.
     11. spec          — default / fallback.

    Returns one of: spec | research | phases | plan | implement | review |
                    reviewed | blocked | needs-input | stale-upstream | done
    """
    item_dir = Path(item_dir)
    if not item_dir.exists():
        return "spec"

    # 1. done — receipt files are terminal
    if has_completion_receipt(item_dir, "COMPLETED.md") or has_completion_receipt(item_dir, "FIXED.md"):
        return "done"

    # 2. stale-upstream
    if read_stale_upstream(item_dir) is not None:
        return "stale-upstream"

    # 3. blocked
    if (item_dir / "BLOCKED.md").exists():
        return "blocked"

    # 4. needs-input
    if (item_dir / "NEEDS_INPUT.md").exists():
        return "needs-input"

    # 5. reviewed
    if (item_dir / _REVIEWED_FILENAME).exists():
        return "reviewed"

    # 6. review — PR.md + PHASES.md both present
    if (item_dir / "PR.md").exists() and (item_dir / "PHASES.md").exists():
        return "review"

    # 7-8. Artifact ladder: plans/ subdir with ≥1 *.md
    plans_dir = item_dir / "plans"
    if plans_dir.exists() and any(plans_dir.glob("*.md")):
        # Determine implement vs plan by checking for ≥1 checked deliverable in PHASES.md
        phases_path = item_dir / "PHASES.md"
        if phases_path.exists():
            phases_text = phases_path.read_text(encoding="utf-8")
            for line in phases_text.splitlines():
                if re.match(r"^\s*-\s*\[[xX]\]", line):
                    return "implement"
        return "plan"

    # 9. phases
    if (item_dir / "PHASES.md").exists():
        return "phases"

    # 10. research
    if (item_dir / "RESEARCH.md").exists() or (item_dir / "RESEARCH_SUMMARY.md").exists():
        return "research"

    # 11. spec (default)
    return "spec"


# ---------------------------------------------------------------------------
# WIP liveness sentinel helpers
# ---------------------------------------------------------------------------

def _write_wip(item_dir: Path, fields: dict) -> None:
    """Serialize WIP frontmatter and atomically write <item_dir>/WIP.md.

    Unknown values serialize as empty (never the literal "None").
    """
    def _fmt(value):
        return "" if value is None or value == "None" else value

    lines = [
        "---",
        f"kind: {fields['kind']}",
        f"wi_id: {_fmt(fields['wi_id'])}",
        f"slug: {_fmt(fields['slug'])}",
        f"branch: {_fmt(fields['branch'])}",
        f"host: {_fmt(fields['host'])}",
        f"started_at: \"{fields['started_at']}\"",
        f"last_touched: \"{fields['last_touched']}\"",
        "---",
        "",
        "# Work in progress",
    ]
    _atomic_write(item_dir / _WIP_FILENAME, "\n".join(lines))


def track_open(item_dir, wi_id, slug, branch, host, now: str) -> None:
    """Create or refresh <item_dir>/WIP.md as the liveness sentinel for an active work item.

    Idempotent: if WIP.md already exists, ``started_at`` is preserved from the
    existing file and only ``last_touched`` is advanced to ``now``.  A refresh
    never degrades known fields: when ``wi_id``/``branch``/``host`` are missing
    (None/empty, or a stale literal "None" from a prior bad write), the existing
    values are kept.  Time is injected via ``now`` (ISO-8601 string) for
    determinism — no ``datetime.now()`` call occurs here.
    """
    item_dir = Path(item_dir)
    item_dir.mkdir(parents=True, exist_ok=True)

    def _keep(new, old):
        return new if new not in (None, "", "None") else old

    wip_path = item_dir / _WIP_FILENAME
    existing = parse_sentinel(wip_path) or {}
    started_at = existing.get("started_at") or now
    wi_id = _keep(wi_id, _keep(existing.get("wi_id"), None))
    branch = _keep(branch, _keep(existing.get("branch"), None))
    host = _keep(host, _keep(existing.get("host"), None))

    _write_wip(item_dir, {
        "kind": "wip",
        "wi_id": wi_id,
        "slug": slug,
        "branch": branch,
        "host": host,
        "started_at": started_at,
        "last_touched": now,
    })


def track_touch(item_dir, now: str) -> None:
    """Advance ``last_touched`` in an existing <item_dir>/WIP.md to ``now``.

    If WIP.md is absent, this is a no-op — the file is never created here.
    All other fields are preserved unchanged.  Time is injected via ``now``
    for determinism.
    """
    item_dir = Path(item_dir)
    wip_path = item_dir / _WIP_FILENAME
    existing = parse_sentinel(wip_path)
    if not existing:
        return
    existing["last_touched"] = now
    _write_wip(item_dir, existing)


def track_close(item_dir) -> None:
    """Remove <item_dir>/WIP.md, marking the work item as no longer active.

    No-op if WIP.md is absent.
    """
    item_dir = Path(item_dir)
    (item_dir / _WIP_FILENAME).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Plan file parsing
# ---------------------------------------------------------------------------

def _parse_plan_frontmatter(path: Path) -> dict[str, Any] | None:
    """Parse a plan file's YAML frontmatter per _components/plan-frontmatter.md.

    Returns:
      - dict with parsed YAML if frontmatter is present and valid.
      - {} (empty dict) if the file has no frontmatter block (legacy plan).
      - None only if the file cannot be read (caller treats as missing).

    Plan files share the parsing protocol of sentinel files but live in a
    disjoint kind namespace (implementation-plan / retro-plan / fix-plan /
    realign-plan). On malformed YAML, _die() halts via the same path as
    sentinels — parse errors should not be swallowed.
    """
    if not path.exists():
        return None
    return parse_sentinel(path)


def _plan_status(path: Path) -> str:
    """Return the plan's ``status:`` field. Defaults to 'Ready' for legacy plans
    (no frontmatter); caller records a diagnostics warning in that case.
    """
    meta = _parse_plan_frontmatter(path) or {}
    if not meta:
        return "Ready"
    raw = meta.get("status")
    if isinstance(raw, str) and raw:
        return raw
    return "Ready"


# The canonical per-plan-part complexity tier set (Phase 9 —
# lazy-validation-readiness). Mirrors the ``_VALID_PHASE_KINDS`` Phase-8 pattern
# for the per-PHASE ``**Phase kind:**`` marker, but lives in plan-part YAML
# frontmatter (``complexity:``) instead. ``complex`` is the CONSERVATIVE default:
# an untagged / unrecognized / unreadable plan dispatches on Opus (the safe,
# full-capability tier). Only an explicit, recognized ``mechanical`` tag —
# emitted by /write-plan when a part's WUs are ALL genuinely mechanical —
# downgrades the /execute-plan cycle to Sonnet. The model NEVER auto-guesses the
# tier at dispatch; it trusts only the tag /write-plan deliberately wrote.
_VALID_PLAN_COMPLEXITIES = frozenset({"mechanical", "complex"})
_DEFAULT_PLAN_COMPLEXITY = "complex"


def plan_complexity(path: Path) -> str:
    """Return a plan part's ``complexity:`` tier — ``"mechanical"`` or ``"complex"``.

    Reads the per-plan-part ``complexity`` field from the plan file's YAML
    frontmatter (per ``_components/plan-frontmatter.md``). Phase 9 —
    lazy-validation-readiness; mirrors ``_plan_status``'s lookup shape.

    Defaults to the SAFE tier ``"complex"`` (→ Opus dispatch) in every uncertain
    case — a legacy plan with no frontmatter, an absent ``complexity`` field, an
    unrecognized value, or a missing/unreadable file. Only an explicit,
    case-insensitively-recognized ``mechanical`` tag returns ``"mechanical"``.
    This makes the model-tiering back-compatible (every pre-Phase-9 plan keeps
    dispatching on Opus) and conservative (an ambiguous tag never silently
    downgrades implementation quality).
    """
    meta = _parse_plan_frontmatter(path) or {}
    if not meta:
        return _DEFAULT_PLAN_COMPLEXITY
    raw = meta.get("complexity")
    if isinstance(raw, str):
        norm = raw.strip().lower()
        if norm in _VALID_PLAN_COMPLEXITIES:
            return norm
    return _DEFAULT_PLAN_COMPLEXITY


def _plan_lowest_phase(path: Path) -> tuple[int, str]:
    """Return a sort key (lowest_phase_number, plan_name).

    Falls back to (sys.maxsize, name) when the plan lacks a ``phases:`` field —
    that means feature-wide / unspecified plans sort after phase-tagged ones,
    matching the user's requested ordering (lowest declared phase wins).
    """
    meta = _parse_plan_frontmatter(path) or {}
    phases = meta.get("phases") if meta else None
    lowest = sys.maxsize
    if isinstance(phases, list):
        for entry in phases:
            try:
                n = int(entry)
            except (TypeError, ValueError):
                # Non-numeric phase identifiers (e.g. "all", "P3a") — extract
                # any leading digit run, else skip. Mirrors the lenient handling
                # in latest_retro_plan().
                if isinstance(entry, str):
                    m = re.match(r"^(\d+)", entry)
                    if m:
                        n = int(m.group(1))
                    else:
                        continue
                else:
                    continue
            if n < lowest:
                lowest = n
    return (lowest, path.name)


# Recognizes the ``-part-K`` suffix /write-plan emits when it partitions a
# feature into a multi-part plan series (see write-plan/SKILL.md Step 2.5 naming
# rule: ``all-phases-<slug>-part-1.md``, ``...-part-2.md``, etc., and the
# ``> **Plan series:** part K of N`` preamble whose contract is "Execute parts
# strictly in order"). The K is captured just before the ``.md`` suffix.
_PLAN_PART_RE = re.compile(r"-part-(\d+)(?:\.md)?$", re.IGNORECASE)


def _plan_series_index(path: Path) -> int | None:
    """Return the 1-based part index K from a ``...-part-K.md`` plan filename.

    Returns None when the filename carries no ``-part-K`` suffix (a single-part
    or legacy plan). A frontmatter ``series_index:`` field, when present, takes
    precedence over the filename — this lets a producer carry the authoritative
    order machine-readably without renaming files. ``series_index:`` is an
    OPTIONAL, lazy-only ordering hint: it is read here but is NOT in the
    plan-frontmatter REQUIRED/OPTIONAL key set parsed by AlgoBooth's
    check-docs-consistency.ts, so it MUST stay filename-derived in the common
    case to avoid forcing a consumer-lockstep schema change. Prefer the filename
    suffix; reserve the frontmatter field for the rare case where the filename
    cannot encode the order.
    """
    meta = _parse_plan_frontmatter(path) or {}
    raw = meta.get("series_index") if meta else None
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    m = _PLAN_PART_RE.search(path.name)
    if m:
        return int(m.group(1))
    return None


def _plan_sort_key(path: Path) -> tuple[int, int, str]:
    """Authoritative execution-order sort key for implementation plans.

    Returns ``(series_index, lowest_phase, name)``.

    ROOT-CAUSE FIX (ISSUE 1 — d8-effect-chains live /lazy-batch run, 2026-06-14):
    A /realign-spec corrective Phase 6 was a PREREQUISITE for the pre-existing
    Phase 5 (Phase 5 documents the ``.cab()``/``.reverb()`` API that Phase 6
    builds). /write-plan emitted part-1 ``phases: [6]`` (the prerequisite) and
    part-2/part-3 ``phases: [5]`` (depend on part-1). Sorting purely by
    ``_plan_lowest_phase`` (phase number) routed part-2 (Phase 5) BEFORE part-1
    (Phase 6) — inverting the declared "Execute parts strictly in order"
    contract — so the router oscillated (step_repeat_count hit 3) and the
    execute-plan subagent silently deviated to part-1.

    The ``-part-K`` series index is the DECLARED, authoritative execution order
    ("part K of N … Execute parts strictly in order"). It therefore sorts FIRST,
    ahead of raw phase number. This makes a prerequisite phase numbered HIGHER
    than its dependents (part-1=Phase 6 before part-2=Phase 5) route correctly
    as long as the producer wrote the parts in dependency order — which is the
    series invariant. Plans with no ``-part-K`` suffix carry series_index
    sys.maxsize so they sort after an explicit part series but among themselves
    fall back to the prior (lowest_phase, name) behavior — preserving the
    single-plan / non-series ordering exactly.
    """
    idx = _plan_series_index(path)
    series = idx if idx is not None else sys.maxsize
    lowest, name = _plan_lowest_phase(path)
    return (series, lowest, name)


def _plan_phase_set(plan_path: Path) -> set[int]:
    """Return the set of phase numbers declared in a plan's ``phases:`` field.

    Empty set when the plan has no ``phases:`` field or all entries fail to parse.
    Mirrors the leniency in _plan_lowest_phase(): non-numeric entries with a
    leading digit run (e.g. "3a") contribute that integer; pure-string entries
    (e.g. "all") are skipped.
    """
    meta = _parse_plan_frontmatter(plan_path) or {}
    raw = meta.get("phases") if meta else None
    out: set[int] = set()
    if not isinstance(raw, list):
        return out
    for entry in raw:
        try:
            out.add(int(entry))
            continue
        except (TypeError, ValueError):
            pass
        if isinstance(entry, str):
            m = re.match(r"^(\d+)", entry)
            if m:
                out.add(int(m.group(1)))
    return out


def _unchecked_wus_in_plan_scope(phases_text: str, phase_set: set[int]) -> list[str]:
    """Return the unchecked-WU label strings in PHASES.md scoped to the plan's phases.

    Walks PHASES.md tracking the current ``### Phase N`` heading; collects each
    ``- [ ] <label>`` line whose enclosing phase number is in ``phase_set``. A line
    starting with ``## `` resets phase tracking (new top-level section).
    """
    current_phase: int | None = None
    out: list[str] = []
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        # Toggle fence state; fence markers are not headings or deliverables.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # Lines inside a code fence are illustrative examples — not real WUs.
            continue
        h = re.match(r"^###\s+Phase\s+(\d+)", line)
        if h:
            current_phase = int(h.group(1))
            continue
        if line.startswith("## "):
            current_phase = None
            continue
        if current_phase is None or current_phase not in phase_set:
            continue
        m = re.match(r"^\s*-\s*\[\s*\]\s*(.+?)\s*$", line)
        if m:
            out.append(m.group(1))
    return out


def find_implementation_plans(spec_dir: Path) -> list[Path]:
    """Find non-retro implementation plans, filtering out plans whose
    frontmatter marks them Complete, and sorting by the lowest ``phases:``
    entry (alphabetical fallback for plans without phases:).

    Mirrors /lazy Step 7a. See _components/plan-frontmatter.md for the schema.
    Plans with no frontmatter are treated as legacy ``status: Ready`` and
    surface a diagnostics warning so AlgoBooth's lint can flag the backlog.
    """
    plans: list[Path] = []
    plans_dir = spec_dir / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            name = p.name
            if name.startswith("retro-") or name.startswith("realign-"):
                continue
            meta = _parse_plan_frontmatter(p) or {}
            if meta:
                status = meta.get("status", "Ready")
                if status == "Complete":
                    continue
            else:
                _diag(
                    f"legacy plan (no frontmatter): {p} — backfill "
                    "kind/feature_id/status/created per _components/plan-frontmatter.md"
                )
            plans.append(p)
    # Legacy fallback
    legacy = spec_dir / "PLAN.md"
    if legacy.exists() and legacy not in plans:
        meta = _parse_plan_frontmatter(legacy) or {}
        if meta:
            if meta.get("status") != "Complete":
                plans.append(legacy)
        else:
            _diag(
                f"legacy plan (no frontmatter): {legacy} — backfill per "
                "_components/plan-frontmatter.md"
            )
            plans.append(legacy)
    # Sort by the authoritative execution-order key (_plan_sort_key):
    # (series_index, lowest_phase, name). The ``-part-K`` series index sorts
    # FIRST so a declared multi-part plan series ("Execute parts strictly in
    # order") always routes part-1 before part-2 — even when part-1 carries a
    # HIGHER phase number than part-2 (the d8-effect-chains corrective-Phase-6
    # inversion, ISSUE 1). Non-series plans (no ``-part-K`` suffix) carry
    # series_index sys.maxsize and fall back to the prior (lowest_phase, name)
    # ordering, so single-plan / legacy features behave exactly as before.
    plans.sort(key=_plan_sort_key)
    return plans


def _has_any_complete_plan(spec_dir: Path) -> bool:
    """Return True iff at least one non-retro/non-realign implementation plan
    has frontmatter ``status: Complete``.

    Used by the Step 7 cloud bypass to distinguish 'all implementation plans
    are Complete' from 'no plans authored yet' — only the former should fall
    through to Step 8 in cloud mode when PHASES.md still has unchecked rows
    (e.g. workstation-only Runtime Verification subsections).
    """
    plans_dir = spec_dir / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            name = p.name
            if name.startswith("retro-") or name.startswith("realign-"):
                continue
            meta = _parse_plan_frontmatter(p) or {}
            if meta and meta.get("status") == "Complete":
                return True
    legacy = spec_dir / "PLAN.md"
    if legacy.exists():
        meta = _parse_plan_frontmatter(legacy) or {}
        if meta and meta.get("status") == "Complete":
            return True
    return False


def find_retro_plans(spec_dir: Path) -> list[Path]:
    """Find retro plans, filtering out plans whose frontmatter marks them
    Complete. Plans without frontmatter are treated as legacy ``status: Ready``
    and surface a diagnostics warning.
    """
    plans_dir = spec_dir / "plans"
    if not plans_dir.exists():
        return []
    out: list[Path] = []
    for p in sorted(plans_dir.glob("retro-*.md")):
        meta = _parse_plan_frontmatter(p) or {}
        if meta:
            if meta.get("status") == "Complete":
                continue
        else:
            _diag(
                f"legacy retro plan (no frontmatter): {p} — backfill per "
                "_components/plan-frontmatter.md"
            )
        out.append(p)
    return out


def latest_retro_plan(spec_dir: Path) -> Path | None:
    """Return the most recent retro plan (by index then mtime), or None."""
    plans = find_retro_plans(spec_dir)
    if not plans:
        return None
    # Sort by leading number if present (retro-1-, retro-2-, etc.); fallback to mtime
    def keyfn(p: Path) -> tuple[int, float]:
        m = re.match(r"^retro-(\d+)-", p.name)
        idx = int(m.group(1)) if m else 0
        return (idx, p.stat().st_mtime)
    return max(plans, key=keyfn)


def retro_plan_has_significant_divergences(plan_path: Path) -> bool:
    """Heuristic: scan the retro plan for non-empty Significant divergence table."""
    if not plan_path.exists():
        return False
    text = plan_path.read_text(encoding="utf-8")
    # Look for a Significant table under Spec Divergences with at least one data row
    # Pattern: "### Significant" followed by table header then data row(s)
    m = re.search(
        r"### Significant.*?\n(.*?)(?=\n###|\n##|\Z)",
        text,
        flags=re.DOTALL,
    )
    if not m:
        return False
    section = m.group(1)
    # Count table rows that aren't header/separator/empty
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):  # separator
            continue
        # Skip header row (contains "Spec Requirement" or similar header text)
        if "Spec Requirement" in s or "---" in s or "Item " in s:
            continue
        # Data row with content other than '...'
        cells = [c.strip() for c in s.strip("|").split("|")]
        if any(c and c != "..." for c in cells):
            return True
    return False


# ---------------------------------------------------------------------------
# PHASES.md analysis
# ---------------------------------------------------------------------------

def count_deliverables(phases_text: str) -> tuple[int, int]:
    """Return (unchecked, checked) counts of '- [ ]' / '- [x]' lines.

    Lines that appear inside a triple-backtick code fence are skipped — they
    are illustrative examples, not real deliverables.
    """
    unchecked = 0
    checked = 0
    in_fence = False
    for line in phases_text.splitlines():
        # Toggle fence state when a line's stripped content starts with ```.
        # Handles both opening (```lang) and closing (```) fence markers.
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^\s*-\s*\[\s*\]", line):
            unchecked += 1
        elif re.match(r"^\s*-\s*\[[xX]\]", line):
            checked += 1
    return unchecked, checked


# Matches the title text of a "verification-only" subsection — rows under such
# a subsection are workstation-only runtime/MCP checks that cloud cannot tick
# and that the workstation /mcp-test step (not /write-plan) is responsible for.
_VERIFICATION_SECTION_RE = re.compile(
    r"runtime\s+verification|mcp\s+(?:integration\s+test|test\s+assertion|assertion)",
    re.IGNORECASE,
)


def remaining_unchecked_are_verification_only(phases_text: str) -> bool:
    """Return True iff every '- [ ]' line in PHASES.md sits under a
    Runtime Verification / MCP-assertion subsection.

    Used by the Step 7 workstation bypass: when all implementation plans are
    Complete and the only remaining unchecked rows are workstation-only
    verification rows, /lazy should fall through to the retro→MCP gate rather
    than loop on write-plan.

    Handles BOTH subsection-marker formats:
      - Markdown headings: ``### Runtime Verification``,
        ``## MCP Integration Test``, etc.
      - Bold markers (the real AlgoBooth PHASES.md format):
        ``**Runtime Verification** ...``, ``**MCP Integration Test Assertions:**``.

    Conservative: any heading or bold-marker subsection header whose title does
    NOT match the verification pattern leaves verification scope, so a genuine
    implementation row found outside a verification subsection returns False
    (caller keeps write-plan / execute-plan). Returns False if no unchecked
    rows are present.

    Superseded phases: a ``### Phase N:`` (or ``## Phase N:``) heading enters a
    new phase and resets the superseded flag. The first ``**Status:** Superseded``
    bold-status line seen inside that phase marks the entire phase exempt — its
    unchecked boxes are out-of-scope and must not cause a False return.
    """
    in_verification = False
    in_superseded_phase = False
    saw_unchecked = False
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        # Toggle fence state; fence markers are not section headers or deliverables.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # Lines inside a code fence are illustrative examples — skip entirely.
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if heading:
            heading_text = heading.group(1)
            # A Phase-level heading (e.g. "### Phase 10: ...") starts a new phase
            # block — reset both tracking flags so the new phase begins clean.
            if re.match(r"Phase\s+\d+", heading_text):
                in_superseded_phase = False
                in_verification = False
            else:
                # Non-phase heading (e.g. "### Runtime Verification") updates
                # in_verification as before; does NOT reset superseded tracking.
                in_verification = bool(_VERIFICATION_SECTION_RE.search(heading_text))
            continue
        # Bold-marker subsection header (e.g. ``**Runtime Verification** ...``).
        # A list item like ``- **x**`` starts with '-', so it is not caught here.
        if stripped.startswith("**"):
            bold = re.match(r"^\*\*(.+?)\*\*", stripped)
            if bold:
                bold_text = bold.group(1)
                # Detect a per-phase "**Status:** Superseded" status line.
                # Mark the entire current phase exempt; do not alter in_verification
                # because a Superseded phase has no effective verification rows either.
                if re.match(r"Status\s*:", bold_text) and "Superseded" in stripped:
                    in_superseded_phase = True
                    continue
                # A bold marker ONLY enters/stays in verification scope when its
                # title matches the verification pattern.  A non-matching bold
                # (e.g. **Assessment:** or **Status:**) must NOT alter
                # in_verification — it is prose structure, not a section boundary.
                if _VERIFICATION_SECTION_RE.search(bold_text):
                    in_verification = True
                # Non-matching bold: do nothing (preserve current in_verification).
                continue
        if re.match(r"^-\s*\[\s*\]", stripped):
            # Unchecked boxes inside a Superseded phase are out of scope —
            # deliverables moved to a successor feature; do not treat as remaining
            # implementation work.
            if in_superseded_phase:
                continue
            saw_unchecked = True
            if not in_verification:
                return False
    return saw_unchecked


# A phase heading in PHASES.md: ``## Phase ...`` or ``### Phase ...`` (two or
# three leading hashes, then the literal word "Phase"). Critically, "Phase" must
# be followed by an actual phase IDENTIFIER — NOT an English word. This mirrors
# the intent of the AlgoBooth repo checker's PHASE_HEADER_RE
# (``/^(#{2,4})\s+Phase\s+([A-Za-z0-9.+]+)\s*[:—-]\s*(.*)$/`` in
# check-docs-consistency.ts), whose author comment is explicit: the identifier
# must be delimited "to prevent matching headers like '### Phase Dependency
# Graph' where 'Phase' is just an English word, not a phase marker."
#
# The bare ``^#{2,3}\s+Phase\b`` form this replaced was a false-positive bug: it
# counted an h2 ``## Phase Summary`` summary section as an 8th phase for
# d8-session-format (7 real ``### Phase N`` headers + the summary). That made
# retro_staleness() return (8,7) on EVERY probe — a permanent "stale retro" loop
# that re-ran /retro forever and never advanced (hardening-log 2026-06 round).
#
# Discriminator (digit-OR-delimiter), strictly wider than the checker's
# delimiter-required form ONLY for bare numeric ids (``### Phase 1`` with no
# ``:``), which real PHASES.md and the existing parse_phases fixtures use:
#   - identifier CONTAINS a digit  → real phase   (``Phase 1``, ``Phase 4A``, ``Phase 10``)
#   - OR identifier is followed by a phase delimiter ``[:—-]`` → real phase
#     (``Phase G+:`` — a non-numeric id is only a phase when delimited)
#   - else (``Phase Summary``, ``Phase Dependency Graph``, ``Phase Implementation
#     Notes``) → NOT a phase.
# This is the SINGLE counter behind both retro_staleness() and lazy-state.py's
# ``--count-phases`` (the /retro phase_count_at_retro writer), so the staleness
# anchor and the recorded count can never disagree.
_PHASE_HEADING_RE = re.compile(
    r"^#{2,3}\s+Phase\s+(?:[A-Za-z.+]*\d[A-Za-z0-9.+]*|[A-Za-z0-9.+]+\s*[:—-])"
)

# A per-phase / top-level bold status line: ``**Status:** <value>``.
_BOLD_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$")

# A per-phase ``**Phase kind:** corrective | design`` marker (Phase 8 —
# lazy-validation-readiness). Mirrors the ``**Status:**`` per-phase convention
# and survives the docs-consistency parse. The captured value is normalized to
# lowercase and validated against {corrective, design}; anything else (including
# an absent line) falls back to the safe ``design`` default so legacy PHASES.md
# re-trigger retro exactly as before. Only the first occurrence inside a phase
# section wins (a later mention inside Implementation Notes is ignored).
_PHASE_KIND_RE = re.compile(r"^\*\*Phase kind:\*\*\s*(.+?)\s*$")

# The canonical phase-kind tier set. ``design`` is the conservative default:
# a design (or unknown / untagged) phase re-triggers /retro; only an explicit
# ``corrective`` tag suppresses the retro re-stale.
_VALID_PHASE_KINDS = frozenset({"corrective", "design"})
_DEFAULT_PHASE_KIND = "design"


def parse_phases(phases_text: str) -> list[dict]:
    """Parse PHASES.md into one record per phase section (Phase 9 WU-1).

    A phase starts at a heading matching ``^##{1,2} Phase\\b`` (i.e. ``## Phase
    ...`` or ``### Phase ...``) and runs to the next phase heading or EOF.

    For each phase the record captures:
      - ``heading``   – the full heading line text (stripped of a trailing
                        newline; leading/trailing whitespace stripped).
      - ``status``    – the value of the FIRST ``**Status:**`` line inside the
                        section, stripped; ``None`` when the section has no
                        status line. A top-level (pre-first-phase) Status line is
                        NEVER captured — content before the first phase heading
                        is not a phase.
      - ``unchecked`` – count of ``- [ ]`` rows in the section, FENCE-AWARE.
      - ``checked``   – count of ``- [x]`` / ``- [X]`` rows in the section,
                        FENCE-AWARE.
      - ``phase_kind`` – ``"corrective"`` or ``"design"``, read from the FIRST
                        ``**Phase kind:** ...`` line inside the section
                        (Phase 8 — lazy-validation-readiness). Defaults to
                        ``"design"`` when the line is absent or carries an
                        unrecognized value (back-compat: a legacy / untagged
                        phase re-triggers /retro exactly as before).

    Fence-awareness reuses the established ``in_fence`` toggle pattern (see
    ``count_deliverables``): a line whose stripped form starts with ``` (a fence
    open/close, including a ```lang opener) toggles fence state, and checkbox
    rows inside a fence are illustrative examples that do NOT count.

    Returns an empty list when ``phases_text`` contains no phase heading.
    """
    phases: list[dict] = []
    current: dict | None = None
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        # Fence markers are never headings, status lines, or deliverables.
        # Toggle the fence and skip — but note that a fence opened/closed inside
        # a phase still belongs to that phase, so we keep ``current`` as-is.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # Inside a fenced block: nothing counts (examples only). We still do
            # NOT start/stop phases here — fence content is opaque body.
            continue
        # A phase heading starts a new section (and closes the previous one).
        if _PHASE_HEADING_RE.match(line):
            current = {
                "heading": stripped,
                "status": None,
                "unchecked": 0,
                "checked": 0,
                # Tracks whether a **Phase kind:** line has been consumed yet
                # (first-wins, like status). The public ``phase_kind`` value is
                # set to the default here and overwritten by the first valid
                # marker; an unknown value leaves the default in place.
                "phase_kind": _DEFAULT_PHASE_KIND,
                "_phase_kind_seen": False,
            }
            phases.append(current)
            continue
        # Everything below only matters once we are inside a phase section.
        # Content before the first phase heading (top-level Status, preamble,
        # stray checkboxes) is intentionally ignored.
        if current is None:
            continue
        # First **Status:** line inside the section wins; later ones (e.g. inside
        # an Implementation Notes block describing prior state) are ignored.
        if current["status"] is None:
            sm = _BOLD_STATUS_RE.match(stripped)
            if sm:
                current["status"] = sm.group(1).strip()
                continue
        # First **Phase kind:** line inside the section wins; later mentions
        # (e.g. inside an Implementation Notes block) are ignored. An
        # unrecognized value leaves the safe ``design`` default in place.
        if not current["_phase_kind_seen"]:
            km = _PHASE_KIND_RE.match(stripped)
            if km:
                current["_phase_kind_seen"] = True
                kind = km.group(1).strip().lower()
                if kind in _VALID_PHASE_KINDS:
                    current["phase_kind"] = kind
                continue
        # Checkbox accounting (fence-aware — fenced rows already skipped above).
        if re.match(r"^-\s*\[\s*\]", stripped):
            current["unchecked"] += 1
        elif re.match(r"^-\s*\[[xX]\]", stripped):
            current["checked"] += 1
    # Drop the private bookkeeping key so the returned records expose only the
    # documented public fields (heading/status/unchecked/checked/phase_kind).
    for ph in phases:
        ph.pop("_phase_kind_seen", None)
    return phases


def retro_staleness(spec_path: Path) -> tuple[int, int] | None:
    """Detect a stale retro: a DESIGN phase landed AFTER the retro concluded.

    Shared predicate for Phase 11 WU-5c (lazy-state Step-8 routing) and WU-5d
    (the ``apply_pseudo __mark_complete__`` backstop) — both keys compare the
    CURRENT number of phase sections in PHASES.md against the count the retro
    recorded at conclusion time (``phase_count_at_retro`` in RETRO_DONE.md
    frontmatter, written by /retro per the Phase 11 WU-5a prose half).

    Returns ``(current_count, recorded_count)`` when the retro is STALE, else
    None.

    **Phase-8 phase-kind gate (lazy-validation-readiness).** A retro is stale
    only when ``>= 1`` of the phases added SINCE the retro is a ``design``
    (non-corrective) phase. The phases added since the retro are the ones at
    index ``>= recorded_count`` (the recorded count is the number of phase
    sections at retro time, so the trailing ``current - recorded`` sections are
    the post-retro additions). A run of PURELY ``corrective`` additions does NOT
    re-trigger retro — corrective phases make the impl satisfy the EXISTING
    spec and change no design surface, so the retro that graded the design has
    nothing to re-audit. A ``design`` (or untagged / unknown-kind, which
    defaults to ``design``) addition DOES re-stale retro. This narrows the
    pre-Phase-8 "any added phase re-stales" behavior; legacy untagged corrective
    tails still re-trigger (the safe default), preserving back-compat.

    Grandfathering / no-signal cases (all → None, preserving prior behavior):
      - RETRO_DONE.md absent, or present without frontmatter.
      - ``phase_count_at_retro`` missing or malformed (not an int / digit
        string; YAML bools rejected — not counts).
      - PHASES.md absent (nothing to compare against).
      - Equal or FEWER phases now (consolidation is not staleness).
      - More phases now, but every post-retro addition is ``corrective``
        (Phase-8 gate — design surface unchanged, no re-audit warranted).
    """
    retro_meta = parse_sentinel(spec_path / "RETRO_DONE.md")
    if not retro_meta:
        # Absent (None) or frontmatter-less ({}) — no recorded count, no signal.
        return None
    raw = retro_meta.get("phase_count_at_retro")
    # bool is an int subclass — reject before the int branch (see
    # validation_escalation for the same YAML-boolean pitfall).
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        recorded = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        recorded = int(raw.strip())
    else:
        # Missing or malformed — grandfathered (current behavior).
        return None
    phases_path = spec_path / "PHASES.md"
    if not phases_path.exists():
        return None
    try:
        phases_text = phases_path.read_text(encoding="utf-8")
    except OSError:
        # Unreadable PHASES.md: treat as no signal rather than crashing the
        # routing/gate — the doc-consistency lints own malformed-file policing.
        return None
    parsed = parse_phases(phases_text)
    current = len(parsed)
    if current <= recorded:
        # Equal or fewer phases now — consolidation is not staleness.
        return None
    # Phase-8 phase-kind gate: only a DESIGN phase added since the retro
    # re-stales. The post-retro additions are the trailing sections at index
    # >= recorded. ``recorded`` may exceed ``current`` only when current <=
    # recorded (already returned above), so this slice is always valid here.
    # A negative/over-large recorded is defended by clamping to [0, current].
    added = parsed[max(0, recorded):]
    if any(ph.get("phase_kind", _DEFAULT_PHASE_KIND) == "design" for ph in added):
        return (current, recorded)
    # Every post-retro addition is corrective — design surface unchanged,
    # nothing for the retro to re-audit. Not stale.
    return None


# Canonical terminal phase statuses (case-insensitive). A phase whose status is
# one of these is "done" and never refuses / auto-flips at completion time.
# Mirrors check-docs-consistency.ts's Complete/Superseded acceptance in the
# spec-complete-phases-not and complete-but-unchecked coherence rules.
_TERMINAL_PHASE_STATUSES = frozenset({"complete", "superseded"})


def _phase_completion_plan(phases: list[dict]) -> tuple[list[dict], list[str]]:
    """Compute the auto-flip set and residual-incoherence refusals for completion.

    Given the parsed ``phases`` (from ``parse_phases``), this mirrors the three
    coherence rules check-docs-consistency.ts enforces under a Complete SPEC —
    but evaluated PRE-flip at ``__mark_complete__`` / ``__mark_fixed__`` time:

      (auto-flip) a phase with >=1 checkbox, zero unchecked, and a PRESENT
        Status not in {Complete, Superseded} → flip to ``Complete`` (mirrors the
        checker's ``all-checked-but-not-complete`` rule; deterministic + safe).

      (refuse) AFTER hypothetically applying the auto-flips, a phase is residually
        incoherent — and the whole completion refuses — when, for a phase that is
        NOT Superseded:
          * it has >=1 unchecked checkbox (verification rows INCLUDED — by
            completion time the verification exemption's job is done), OR
          * its (post-flip) Status is PRESENT but not Complete/Superseded
            (this catches zero-checkbox non-Complete phases too: no mechanical
            signal to flip on → refuse).

        Null-status handling (deliberate, completeness-first / D7): the
        status-straggler check (the second bullet) exempts a phase with NO
        Status line — canonical-null is a non-straggler exactly as the repo
        checker's ``spec-complete-phases-not`` rule (which filters
        ``canonical !== null``) treats it. The unchecked-box check (the first
        bullet) is NOT exempted for null-status phases: the deliverable's box
        rule is "any phase with >=1 unchecked checkbox", so a status-less phase
        with visibly-unfinished work still refuses (the stricter, safer option —
        a feature must not complete with unfinished deliverables hiding under a
        status-less phase).

    Returns ``(flip, refusals)`` where ``flip`` is the list of phase records to
    auto-flip and ``refusals`` is a list of human-readable per-phase reasons
    (empty ⇒ coherent, proceed).
    """
    flip: list[dict] = []
    refusals: list[str] = []
    for ph in phases:
        status = ph["status"]
        status_norm = status.strip().lower() if status else None
        is_superseded = status_norm == "superseded"
        is_terminal = status_norm in _TERMINAL_PHASE_STATUSES
        has_boxes = (ph["checked"] + ph["unchecked"]) > 0
        all_checked = has_boxes and ph["unchecked"] == 0

        # --- (a) auto-flip candidates ---
        # A present, non-terminal status whose every box is checked → flip.
        will_flip = (
            status is not None
            and not is_terminal
            and all_checked
        )
        if will_flip:
            flip.append(ph)

        # --- (b/c) residual incoherence AFTER the hypothetical flip ---
        # Superseded is terminal: its unchecked boxes and status are acceptable.
        if is_superseded:
            continue

        # Unchecked boxes in a non-Superseded phase always block completion —
        # the verification carve-out does not apply at completion time.
        if ph["unchecked"] > 0:
            refusals.append(
                f'{ph["heading"]}: {ph["unchecked"]} unchecked box(es)'
            )
            continue

        # No unchecked boxes. The phase is coherent iff, post-flip, its status is
        # Complete/Superseded. A phase we just flipped lands at Complete → OK.
        # A phase with a present non-terminal status that did NOT qualify for the
        # flip (e.g. zero-checkbox In-progress) has no mechanical flip signal →
        # refuse. A phase with no status line is ignored.
        if status is not None and not is_terminal and not will_flip:
            refusals.append(
                f'{ph["heading"]}: status "{status}" not Complete/Superseded'
            )
    return flip, refusals


# ---------------------------------------------------------------------------
# Completion ledger verification
# ---------------------------------------------------------------------------

def _phases_text_scoped_to(phases_text: str, phase_set: set[int]) -> str:
    """Return the subset of PHASES.md lines belonging to phases in ``phase_set``.

    Phase 9 WU-3 helper: the plan-scoped ``deliverables_done`` check must apply
    the SAME verification-only exemption mid-feature
    (``remaining_unchecked_are_verification_only``) but only over the plan's
    phases. ``_unchecked_wus_in_plan_scope`` already collects in-scope unchecked
    rows but does NOT distinguish verification rows, so instead we slice the
    PHASES body down to the in-scope ``### Phase N`` sections (each section runs
    from its ``### Phase N`` heading until the next phase heading or a ``## ``
    top-level boundary) and hand that slice to the existing exemption helper.

    Fence-aware in the same spirit as ``_unchecked_wus_in_plan_scope``: a fenced
    block opened inside an in-scope phase stays part of that phase's slice (the
    downstream helper re-tracks fences itself, so we simply preserve the lines).
    """
    out: list[str] = []
    current_phase: int | None = None
    for line in phases_text.splitlines():
        h = re.match(r"^###\s+Phase\s+(\d+)", line)
        if h:
            current_phase = int(h.group(1))
            if current_phase in phase_set:
                out.append(line)
            continue
        # A top-level ``## `` heading (NOT ``### Phase``) closes phase tracking —
        # content after it is not part of any in-scope phase. Keep the verification
        # heading recognizable to the exemption helper by re-emitting the line only
        # when we are still inside an in-scope phase.
        if line.startswith("## ") and not line.startswith("### "):
            current_phase = None
            continue
        if current_phase is not None and current_phase in phase_set:
            out.append(line)
    return "\n".join(out)


# A per-WU plan progress checkbox: ``- [ ] WU-N — <title>`` / ``- [x] WU-N …``.
# Made mandatory by write-plan ISSUE-6 (d8-effect-chains run 2026-06-14): every
# work unit in every generated plan part carries exactly one such row in a
# ``## Work Units`` checklist. ``/execute-plan`` ticks each as it lands the WU,
# so these rows are the MACHINE source of truth for plan-part deliverable
# completion (PHASES.md per-deliverable ticks are demoted to human documentation
# — see the verify_ledger docstring + write-plan/execute-plan SKILL prose).
#
# The WU id may be a bare number (``WU-3``) or a dotted sub-id (``WU-9.0``,
# ``WU-3a``) — accept any ``[A-Za-z0-9.]+`` run after ``WU-``. The separator after
# the id is the em-dash convention but we do not require it (a ``- [ ] WU-3``
# with no title still counts as a progress row). The match is anchored at the
# list-item bullet so a mid-prose mention of "WU-3" is NOT a false checkbox.
_PLAN_WU_CHECKBOX_RE = re.compile(
    r"^\s*-\s*\[(?P<mark>[ xX])\]\s*WU-[A-Za-z0-9.]+\b",
)


def _plan_wu_checkbox_counts(plan_text: str) -> tuple[int, int]:
    """Return ``(unchecked, checked)`` counts of per-WU plan progress checkboxes.

    Parses the ISSUE-6 ``- [ ] WU-N — <title>`` / ``- [x] WU-N …`` rows from a
    plan part's body. Fence-aware in the same spirit as ``count_deliverables``:
    a checkbox inside a triple-backtick code fence is an illustrative example
    (e.g. the write-plan SKILL's own format sample) and is NOT counted.

    ``(0, 0)`` means the plan has NO parseable per-WU checkboxes at all — a
    legacy pre-ISSUE-6 plan. The caller uses that to fall back to the
    PHASES-phase-level behavior (with a diagnostic) rather than vacuously pass.
    """
    unchecked = 0
    checked = 0
    in_fence = False
    for line in plan_text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _PLAN_WU_CHECKBOX_RE.match(line)
        if not m:
            continue
        if m.group("mark") == " ":
            unchecked += 1
        else:
            checked += 1
    return unchecked, checked


def _plan_unchecked_wus_are_verification_only(plan_text: str) -> bool:
    """Return True iff every UNCHECKED ``- [ ] WU-N`` row in the plan body sits
    under a Runtime Verification / MCP Integration Test subsection.

    Preserves the verification-only-row exemption (the same one
    ``remaining_unchecked_are_verification_only`` applies to PHASES.md) but at
    the PLAN-WU granularity: a per-WU checkbox under a gate-owned
    ``**Runtime Verification**`` / ``## MCP Integration Test`` subsection is
    ticked by the Step-9 ``/mcp-test`` gate, NOT by ``/execute-plan``, so it must
    not fail the plan-part ``deliverables_done`` verdict.

    Reuses ``remaining_unchecked_are_verification_only`` over the plan body so the
    section-detection logic (markdown headings AND bold markers, fence-aware,
    Superseded-phase aware) is identical to the PHASES.md path — but only the
    ``- [ ] WU-N`` rows participate, because the underlying helper returns False
    on the FIRST unchecked ``- [ ]`` it sees outside a verification subsection,
    and an ISSUE-6-compliant plan body's only ``- [ ]`` rows ARE the WU rows plus
    any verification rows. (A stray non-WU ``- [ ]`` in the plan body would
    conservatively be treated as non-verification work — the safe direction.)
    """
    return remaining_unchecked_are_verification_only(plan_text)


def verify_ledger(repo_root: Path, spec_path: Path, plan_path: Path | None = None) -> dict:
    """Verify the four completion-ledger preconditions for a feature.

    Called by lazy-state.py and bug-state.py with ``--verify-ledger <spec_path>``
    as a scripted replacement for the five duplicated prose "completion ledger"
    guard blocks across the lazy skills (lazy/SKILL.md Step 4).

    Checks (evaluated in this exact order; ALL four are always computed):

    1. ``clean_tree`` — ``git -C <repo_root> status --short`` produces no output.
       An untracked, modified, or staged file means the feature's changes have
       not been fully committed. Any OSError or subprocess failure returns False.

    2. ``head_matches_origin`` — ``git rev-parse HEAD`` equals
       ``git rev-parse @{u}`` (the upstream tracking ref). A local commit that
       has not been pushed, or a repo with no upstream configured, returns False.

    3. ``plan_complete`` — at least one non-retro implementation plan exists AND
       every such plan has ``status: Complete`` in its frontmatter. Uses
       ``_has_any_complete_plan`` (at least one Complete) combined with
       ``find_implementation_plans`` (no non-Complete plans remain), which together
       are equivalent to "all plans exist and all are Complete". False when no
       plans have been authored at all, or any plan has a non-Complete status.

    4. ``deliverables_done`` — zero real (non-verification) unchecked
       deliverables remain. The SURFACE this reads depends on scope (see below).
       "Real" / verification-exempt is defined by
       ``remaining_unchecked_are_verification_only``: rows under a
       "Runtime Verification / MCP Integration Test" subsection heading are
       exempt workstation-only checks ticked by the Step-9 ``/mcp-test`` gate.

    Plan-scoped mode (``plan_path`` given) — deliverables_done SOURCE OF TRUTH
    (2026-06-15, d8-effect-chains review
    ``docs/features/audio/audio-vision/domains/d8-effect-chains/LAZY_BATCH_REVIEW_2026-06-15.md``):
      Multi-part plans split one feature across several plan files (each with a
      ``phases:`` set). Feature-level checks 3 + 4 fire false alarms while later
      parts are legitimately pending. When ``plan_path`` is provided, checks 3
      and 4 narrow to THAT plan's scope; checks 1 and 2 are unchanged:
        - ``plan_complete`` = THIS plan's frontmatter ``status:`` == ``Complete``
          (read via ``_plan_status`` — the same parser ``find_implementation_plans``
          and the stale-flip logic use). A missing ``plan_path`` file parses to the
          legacy default ``Ready`` → False.
        - ``deliverables_done`` reads the PLAN PART's own per-WU checkboxes
          (``- [ ] WU-N`` — mandatory since write-plan ISSUE-6) as the MACHINE
          record, NOT the PHASES.md phase-level deliverable rows. The plan part is
          the unit of execution and its WUs never span parts or phases, so this
          eliminates BOTH false-fail classes the PHASES-scoped read suffered:
          (a) cross-part — a phase-level deliverable belonging to part-3 failing
          the part-2 check (a phase spans parts); (b) cross-phase attribution — a
          deliverable filed under Phase 5 but built in corrective Phase 6 sitting
          done-but-unticked. Done iff no unchecked ``- [ ] WU-N`` rows remain,
          with the verification-only exemption applied at the WU level
          (``_plan_unchecked_wus_are_verification_only``).
        - LEGACY FALLBACK: a pre-ISSUE-6 plan with NO parseable per-WU checkboxes
          falls back to the prior PHASES-phase-level behavior (scoped to the
          plan's ``phases:``; or feature-level when the plan has no ``phases:`` —
          unknown scope must not vacuously pass) and records
          ``deliverables_source: "phases-fallback (legacy plan — no per-WU
          checkboxes)"`` so the operator knows the legacy path fired. Legacy plans
          are NOT hard-failed.
      ``plan_path=None`` → byte-for-byte the original feature-level behavior
      (the whole feature's PHASES.md via ``count_deliverables`` +
      ``remaining_unchecked_are_verification_only``). If PHASES.md does not exist
      at feature level, returns False (no evidence phases were completed).

    Return shape:
    ```
    {
        "ok": bool,                  # True iff ALL four checks are True
        "failing_check": str | None, # First False check key (order above), or None
        "checks": {
            "clean_tree": bool,
            "head_matches_origin": bool,
            "plan_complete": bool,
            "deliverables_done": bool,
        },
        "deliverables_source": str,  # diagnostic (additive, never gates):
                                     #   "plan-wu-checkboxes"       — new machine record
                                     #   "phases-fallback (…)"      — legacy plan path fired
                                     #   "phases-feature-level"     — no plan_path (whole feature)
    }
    ```

    ``ok`` is True only when all four checks are True. ``failing_check`` names
    the FIRST False check in the defined order; None when ok is True. All four
    ``checks`` values are always populated and accurate regardless of which check
    fails first — no short-circuit pruning is applied to the ``checks`` dict.
    """
    # --- check 1: clean working tree ---
    # Mirror the subprocess style used in _current_head in lazy-state.py:
    # capture_output + text + timeout guard, catch OSError/SubprocessError.
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        clean_tree = result.stdout.strip() == ""
    except (OSError, subprocess.SubprocessError):
        clean_tree = False

    # --- check 2: HEAD matches upstream tracking ref ---
    # Both rev-parse commands must succeed and return identical SHA strings.
    try:
        head_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        upstream_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "@{u}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if head_result.returncode == 0 and upstream_result.returncode == 0:
            head_sha = head_result.stdout.strip()
            upstream_sha = upstream_result.stdout.strip()
            head_matches_origin = bool(head_sha and upstream_sha and head_sha == upstream_sha)
        else:
            # @{u} can fail when no upstream is configured — treat as mismatch.
            head_matches_origin = False
    except (OSError, subprocess.SubprocessError):
        head_matches_origin = False

    # --- Plan scope (Phase 9 WU-3): None → feature-level (original behavior) ---
    # When plan_path is given, checks 3 + 4 narrow to that plan's declared phase
    # set. An empty phase set (no `phases:`) means unknown scope → fall back to
    # the feature-level deliverables_done semantics below.
    scoped = plan_path is not None
    plan_phase_set: set[int] = _plan_phase_set(plan_path) if scoped else set()

    # --- check 3: implementation plan(s) Complete ---
    if scoped:
        # Plan-scoped: ONLY this plan's own frontmatter status matters. Read it
        # via _plan_status (the same parser find_implementation_plans uses); a
        # missing plan_path file parses to the legacy default "Ready" → not
        # Complete → False.
        plan_complete = _plan_status(plan_path) == "Complete"
    else:
        # Feature-level: every implementation plan must be Complete (≥1 exists).
        # _has_any_complete_plan: at least one plan has status: Complete.
        # find_implementation_plans: returns only non-Complete plans.
        # Together: any_complete AND no_incomplete → all plans Complete (and ≥1).
        any_complete = _has_any_complete_plan(spec_path)
        incomplete_plans = find_implementation_plans(spec_path)
        plan_complete = any_complete and len(incomplete_plans) == 0

    # --- check 4: no real (non-verification) unchecked deliverables ---
    #
    # SOURCE OF TRUTH (2026-06-15 — d8-effect-chains review):
    #   * Plan-scoped (``plan_path`` given): the PLAN PART's own per-WU
    #     checkboxes (``- [ ] WU-N`` — mandatory since write-plan ISSUE-6) are
    #     the machine record. The plan part is the unit of execution and its WUs
    #     never span parts or phases, so reading them eliminates BOTH the
    #     cross-part false-fail (a Phase-5 deliverable belonging to part-3 failing
    #     the part-2 check) AND the cross-phase-attribution false-fail (a
    #     deliverable filed under Phase 5 but built in corrective Phase 6 sitting
    #     done-but-unticked). PHASES.md per-deliverable ticks are now
    #     human-readable documentation, NOT the gate.
    #   * Legacy fallback: a pre-ISSUE-6 plan with NO parseable per-WU checkboxes
    #     falls back to the prior PHASES-phase-level behavior and records
    #     ``deliverables_source`` so the operator knows the legacy path fired.
    #   * Feature-level (no ``plan_path`` — used by /mcp-test cycles): unchanged;
    #     it legitimately checks the whole feature's PHASES.md.
    phases_file = spec_path / "PHASES.md"
    # Diagnostic: which surface produced the deliverables_done verdict.
    deliverables_source = "phases-feature-level"
    if scoped:
        # Plan-scoped: prefer the plan part's own per-WU checkboxes.
        plan_text = ""
        if plan_path is not None and plan_path.exists():
            try:
                plan_text = plan_path.read_text(encoding="utf-8")
            except OSError:
                plan_text = ""
        wu_unchecked, wu_checked = _plan_wu_checkbox_counts(plan_text)
        if wu_unchecked or wu_checked:
            # ISSUE-6-compliant plan: the per-WU checkboxes ARE the machine
            # record. Done iff no unchecked WU rows remain — with the
            # verification-only exemption (a WU row under a Runtime Verification /
            # MCP Integration Test subsection is ticked by the Step-9 /mcp-test
            # gate, not by /execute-plan).
            deliverables_source = "plan-wu-checkboxes"
            if wu_unchecked == 0:
                deliverables_done = True
            else:
                deliverables_done = _plan_unchecked_wus_are_verification_only(plan_text)
        else:
            # Legacy pre-ISSUE-6 plan (no per-WU checkboxes): fall back to the
            # PHASES-phase-level behavior, scoped to the plan's phases. Emit a
            # diagnostic so the operator knows the legacy path fired.
            deliverables_source = "phases-fallback (legacy plan — no per-WU checkboxes)"
            if not phases_file.exists():
                deliverables_done = False
            else:
                phases_text = phases_file.read_text(encoding="utf-8")
                if plan_phase_set:
                    in_scope_unchecked = _unchecked_wus_in_plan_scope(phases_text, plan_phase_set)
                    if not in_scope_unchecked:
                        deliverables_done = True
                    else:
                        scoped_text = _phases_text_scoped_to(phases_text, plan_phase_set)
                        deliverables_done = remaining_unchecked_are_verification_only(scoped_text)
                else:
                    # Legacy plan with NO `phases:` set → unknown scope → must NOT
                    # vacuously pass; use feature-level semantics over all of PHASES.
                    unchecked, _checked = count_deliverables(phases_text)
                    if unchecked == 0:
                        deliverables_done = True
                    else:
                        deliverables_done = remaining_unchecked_are_verification_only(phases_text)
    else:
        # Feature-level (no plan_path): the whole feature's PHASES.md.
        if not phases_file.exists():
            # No PHASES.md means we have no evidence of phases being completed.
            deliverables_done = False
        else:
            phases_text = phases_file.read_text(encoding="utf-8")
            unchecked, _checked = count_deliverables(phases_text)
            if unchecked == 0:
                deliverables_done = True
            else:
                # Remaining unchecked rows may be exempted if they are all under
                # a Runtime Verification / MCP Integration Test subsection.
                deliverables_done = remaining_unchecked_are_verification_only(phases_text)

    # --- assemble result: determine first failing check in defined order ---
    checks = {
        "clean_tree": clean_tree,
        "head_matches_origin": head_matches_origin,
        "plan_complete": plan_complete,
        "deliverables_done": deliverables_done,
    }
    failing_check: str | None = None
    for key in ("clean_tree", "head_matches_origin", "plan_complete", "deliverables_done"):
        if not checks[key]:
            failing_check = key
            break

    return {
        "ok": failing_check is None,
        "failing_check": failing_check,
        "checks": checks,
        # Diagnostic (additive — never gates): which surface produced the
        # deliverables_done verdict. "plan-wu-checkboxes" is the new machine
        # source of truth; the "phases-fallback …" / "phases-feature-level"
        # values mark the legacy / feature-level paths for the operator.
        "deliverables_source": deliverables_source,
    }


# ---------------------------------------------------------------------------
# Pseudo-skill dispatcher — deterministic sentinel / receipt writes
# ---------------------------------------------------------------------------

def _current_head(repo_root: Path) -> str | None:
    """Resolve repo_root's HEAD commit sha, or None when repo_root is not a
    git repo / git is unavailable.  Best-effort — mirrors the identically
    named helpers in lazy-state.py and bug-state.py (which gate Step-9
    routing on the same sha); consumed here by apply_pseudo's
    ``__write_validated_from_results__`` freshness backstop.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


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
      - ``flipped_phases`` (``__mark_complete__`` / ``__mark_fixed__``): phase
        headings the completion-coherence gate auto-flipped to Complete.
      - ``warnings`` (``__write_validated_from_results__``): non-fatal
        freshness caveats (legacy results without ``validated_commit``, or an
        unresolvable HEAD); also echoed to stderr.

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
        VALIDATED.md / RETRO_DONE.md / DEFERRED_NON_CLOUD.md.  Idempotent on
        existing COMPLETED.md.

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
        result_literal = results_meta.get("result")
        if result_literal != "all-passing":
            return _refused(
                f"MCP_TEST_RESULTS.md result is {result_literal!r} — expected "
                "'all-passing' (the canonical passing literal); a non-passing "
                "run must not mint VALIDATED.md. Re-run /mcp-test until all "
                "scenarios pass, or route the failure (BLOCKED/add-phase)."
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
                return _refused(
                    f"MCP_TEST_RESULTS.md is stale: validated_commit "
                    f"{recorded_commit} does not match current HEAD {head} — "
                    "stale results must not mint a fresh VALIDATED.md; re-run "
                    "/mcp-test against the current code"
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
        content = (
            "---\n"
            "kind: validated\n"
            f"feature_id: {feature_id}\n"
            f"date: {date}\n"
            f"mcp_scenarios: {scenarios_inline}\n"
            "result: all-passing\n"
            f"{commit_line}"
            "---\n"
            "\n"
            "# Validated\n"
            "\n"
            "Derived from MCP_TEST_RESULTS.md by the "
            "__write_validated_from_results__ gate (apply_pseudo): result "
            f"all-passing, {pass_count}/{total_count} scenarios passing.\n"
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

        # Idempotency: if the receipt already exists and parses correct kind → noop.
        # NOTE: this noop check runs BEFORE the completion-coherence gate below,
        # so an already-receipted dir is a clean noop even if its PHASES.md is
        # incoherent — re-completing a done feature must never re-refuse.
        receipt_path = spec_path / receipt_filename
        existing_receipt = parse_sentinel(receipt_path)
        if existing_receipt is not None and existing_receipt.get("kind") == receipt_kind:
            return _noop()

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
        _staleness = retro_staleness(spec_path)
        if _staleness is not None:
            _now_count, _retro_count = _staleness
            return _refused(
                f"retro is stale: {_now_count} phases now vs "
                f"{_retro_count} at retro — route a retro round before "
                "completion"
            )

        # --- Completion-coherence gate (Phase 9 WU-1) ---
        # Before minting the receipt and flipping the top-level Status, make
        # PHASES.md coherent the way AlgoBooth's check-docs-consistency.ts
        # requires a Complete SPEC to be: every phase Complete/Superseded with no
        # unchecked boxes. We (a) AUTO-FLIP all-ticked non-terminal phases to
        # Complete (deterministic, mirrors the checker's all-checked-but-not-
        # complete rule) and (b) REFUSE with ZERO writes when any phase would
        # remain incoherent after that flip (unchecked boxes incl. verification
        # rows, or a present non-Complete/non-Superseded status with no flip
        # signal). When PHASES.md is absent the gate is a no-op (preserves the
        # pre-Phase-9 behavior). ``flipped_phases`` records the headings flipped.
        flipped_phases: list[str] = []
        phases_md_path = spec_path / "PHASES.md"
        if phases_md_path.exists():
            phases_text = phases_md_path.read_text(encoding="utf-8")
            parsed_phases = parse_phases(phases_text)
            to_flip, refusals = _phase_completion_plan(parsed_phases)
            if refusals:
                # Residual incoherence → refuse with no filesystem writes at all
                # (no receipt, no status flips, no sentinel deletions). Name each
                # offending phase so the orchestrator can route a corrective
                # coherence cycle (per the Phase 9 refusal contract).
                return _refused(
                    f"PHASES.md is incoherent for completion — "
                    f"{len(refusals)} phase(s) block the receipt: "
                    + "; ".join(refusals)
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

        body_note = (
            f"Feature {feature_id} marked {status_value.lower()} via "
            f"apply_pseudo on {date}. Validated via: {validated_via}."
        )

        # Write the receipt using the existing helper.
        write_completed_receipt(
            receipt_path,
            feature_id,
            date,
            provenance="gated",
            kind=receipt_kind,
            validated_via=validated_via,
            mcp_pass_count=mcp_pass_count,
            mcp_total_count=mcp_total_count,
            body_note=body_note,
        )
        wrote = [receipt_filename]

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

        # Attach the Phase 9 WU-1 ``flipped_phases`` key (the per-phase headings
        # the completion-coherence gate auto-flipped to Complete this call).
        # Empty list when nothing needed flipping; documented in the docstring.
        result = _ok(wrote, deleted)
        result["flipped_phases"] = flipped_phases
        return result

    else:
        # Unknown pseudo-skill name — never crash, always refuse gracefully.
        return _refused(f"unknown pseudo-skill: {name}")


# ---------------------------------------------------------------------------
# neutralize_sentinel — WU-3: rename a resolved sentinel to the canonical
#   *_RESOLVED_<date> form (collision-safe, git-mv-aware).
# ---------------------------------------------------------------------------

def neutralize_sentinel(path: Path, date: str | None = None) -> dict:
    """Rename a sentinel file to its canonical RESOLVED form.

    Given a sentinel like NEEDS_INPUT.md or BLOCKED.md that has been acted on,
    this function renames it to ``<stem>_RESOLVED_<date><ext>`` in the same
    directory. The rename is collision-safe: if the canonical target already
    exists, a numeric suffix is appended (``_2``, ``_3``, …) until a free name
    is found. The original file is never clobbered.

    When the file lives inside a git repo and is tracked, ``git mv`` is used to
    preserve history. If ``git mv`` returns non-zero (plain temp dir, untracked
    file, or git unavailable) the function falls back to a plain filesystem
    rename via ``Path.rename()``.

    Args:
        path: Absolute (or relative) path to the sentinel file to neutralize.
        date: ISO date string (YYYY-MM-DD) to embed in the resolved name.
              Defaults to today's date (``datetime.date.today().isoformat()``).

    Returns:
        A dict with keys:
          ok              – True on success, False on any refusal/error.
          renamed_from    – Basename of the source file (str), or None on refusal.
          renamed_to      – Basename of the target file (str), or None on refusal.
          refused         – Human-readable refusal reason (str), or None on success.
          collision_suffix – Integer n (≥2) when a collision suffix was required,
                             or None when the base target name was free.
    """
    # Default to today when no date is provided by the caller.
    if date is None:
        date = datetime.date.today().isoformat()

    # Guard 1: source must exist — never create anything for a missing path.
    if not path.exists():
        return {
            "ok": False,
            "renamed_from": None,
            "renamed_to": None,
            "refused": "sentinel not found",
            "collision_suffix": None,
        }

    # Guard 2: refuse to double-neutralize a file that already contains _RESOLVED_.
    # The literal substring check is intentional — it catches any variant like
    # NEEDS_INPUT_RESOLVED_2026-06-09.md regardless of the date.
    if "_RESOLVED_" in path.name:
        return {
            "ok": False,
            "renamed_from": None,
            "renamed_to": None,
            "refused": "already neutralized",
            "collision_suffix": None,
        }

    # Compute the canonical base target name: <stem>_RESOLVED_<date><ext>.
    # path.stem is the filename without its final extension; path.suffix is the
    # extension including the leading dot (e.g. ".md").
    stem = path.stem
    ext = path.suffix
    base_target_name = f"{stem}_RESOLVED_{date}{ext}"
    target = path.parent / base_target_name

    # Collision-safe name selection: if the base target exists, increment a
    # numeric suffix starting at 2 until a free slot is found. Never clobber.
    collision_suffix: int | None = None
    if target.exists():
        n = 2
        while True:
            candidate_name = f"{stem}_RESOLVED_{date}_{n}{ext}"
            candidate = path.parent / candidate_name
            if not candidate.exists():
                target = candidate
                collision_suffix = n
                break
            n += 1

    # Attempt rename via git mv to preserve history when the file is tracked.
    # ``git -C <dir> mv <src_basename> <dst_basename>`` keeps the operation
    # within the directory; we pass basenames so git doesn't need absolute paths.
    # Modelled after _current_head in lazy-state.py (capture_output, text, timeout,
    # OSError/SubprocessError guard).
    renamed = False
    try:
        r = subprocess.run(
            ["git", "-C", str(path.parent), "mv", path.name, target.name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            # git mv succeeded: source is gone, target is present.
            renamed = True
    except (OSError, subprocess.SubprocessError):
        # git unavailable or some other OS-level failure — fall through to
        # the plain filesystem move below.
        pass

    if not renamed:
        # Fallback: plain filesystem rename. Use Path.rename() which is atomic
        # on POSIX and behaves correctly on Windows for in-directory renames.
        path.rename(target)

    return {
        "ok": True,
        "renamed_from": path.name,
        "renamed_to": target.name,
        "refused": None,
        "collision_suffix": collision_suffix,
    }


# ---------------------------------------------------------------------------
# Persisted probe signature / loop detection — WU-4
# ---------------------------------------------------------------------------

def _current_head(repo_root: Path) -> str | None:
    """Resolve repo_root's HEAD commit sha, or None when repo_root is not a git
    repo / git is unavailable.

    Best-effort and never raises: a missing git binary, a non-repo path, or any
    subprocess error all map to None. update_repeat_count uses this for the
    Phase 9 WU-2 HEAD-aware streak — None on both sides (e.g. a non-git
    repo_root) preserves the pre-Phase-9 same-tuple-increments behavior.

    This mirrors lazy-state.py's own _current_head (which lazy-state keeps for
    its Step-9 MCP-results freshness gate); the duplication is deliberate — the
    two scripts are independently importable and lazy_core must not depend on a
    sibling script. Both share the same best-effort contract.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


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
       (feature_id, current_step) pair is unchanged from the prior probe and
       resets to 1 only when that pair changes — commits in between are ignored.

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
    current_consume_count: object = _MISSING
    _marker = read_run_marker()
    if _marker is not None:
        _marker_repo = _marker.get("repo_root")
        if _marker_repo is not None and Path(_marker_repo).resolve() == repo_root.resolve():
            current_consume_count = consumed_emission_count()

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


# ---------------------------------------------------------------------------
# WU-5: Single-probe payload helpers
# ---------------------------------------------------------------------------

def _git(repo_root: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a git command against repo_root, capturing output. Never raises on
    non-zero exit (callers check .returncode); raises only on OS-level failure,
    which callers wrap."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def archive_fixed(
    repo_root: Path,
    spec_path: Path,
    *,
    date: str | None = None,
) -> dict:
    """Archive a Fixed bug directory: the deterministic successor to the prose
    archive mechanics in mark-fixed-archive.md Steps 1–5.

    Why this is script-owned (2026-06-10 incident): the orchestrator performing
    these steps as prose improvised through three consecutive failures — a
    `git mv` refused because apply_pseudo's sentinel deletions were unstaged
    (tracked-but-missing files inside the dir), a transient Windows
    "Permission denied" on the directory rename, and a repo-wide `grep -r`
    crawling node_modules. Each is handled deterministically here.

    Steps (all best-effort idempotent; safe to re-run after a partial failure):
      1. Gate: FIXED.md receipt present (kind: fixed) — or SPEC ``**Status:**
         Won't-fix`` (receipt-exempt). If spec_path is already gone and the
         archive destination exists, treat as a RESUME: skip to step 5.
      2. SPEC.md evidence header lines: ensure ``**Fixed:** <date>`` and
         ``**Fix commit:** <short sha>`` after ``**Discovered:**`` (fallback:
         after ``**Status:**``), updating them if already present.
      3. ``git add -A <spec_path>`` — stages the receipt, status flips, AND the
         sentinel deletions so the index is coherent before the move (the exact
         precondition the prose flow missed).
      4. ``git mv <spec_path> docs/bugs/_archive/<bug_id>`` with retry/backoff
         (1s/2s/4s — Windows transient handle locks), then a per-file
         ``git mv`` fallback if the directory rename never succeeds. A name
         collision in _archive/ gets a ``-archived-<date>`` suffix.
      5. Repoint inbound references: ``git grep -l`` (tracked files only — never
         node_modules/target) for ``docs/bugs/<bug_id>/`` across ``*.md``,
         replacing with ``docs/bugs/_archive/<bug_id>/``.
      6. Remove the bug's entry from docs/bugs/queue.json (matched on
         ``spec_dir`` or ``id``).
      7. Stage the touched paths and commit:
         ``fix(<bug_id>): mark fixed and archive — FIXED.md receipt gated``.

    Return shape (callers may JSON-dump unconditionally)::

        {
            "name": "archive_fixed",
            "ok": bool,
            "refused": str | None,   # non-None → nothing irreversible was done,
                                     #   OR a partial-state diagnostic (see note)
            "noop": bool,            # True iff there was nothing left to do
            "archived_to": str | None,   # repo-relative destination
            "fix_commit": str | None,    # short sha recorded in SPEC.md
            "repointed": [str, ...],     # repo-relative files whose refs moved
            "queue_removed": bool,
            "fallback_used": bool,       # per-file git mv fallback engaged
            "committed": str | None,     # short sha of the archive commit
        }

    Partial-state note: a refusal AFTER the move (e.g. commit failure) names
    the completed steps so the consumer can surface an accurate BLOCKED.md;
    re-running resumes from the archive destination rather than redoing the
    move.
    """
    if date is None:
        date = datetime.date.today().isoformat()
    repo_root = repo_root.resolve()
    bug_id = spec_path.name
    result: dict[str, Any] = {
        "name": "archive_fixed",
        "ok": False,
        "refused": None,
        "noop": False,
        "archived_to": None,
        "fix_commit": None,
        "repointed": [],
        "queue_removed": False,
        "fallback_used": False,
        "committed": None,
    }

    def _refuse(msg: str) -> dict:
        result["refused"] = msg
        return result

    archive_parent = repo_root / "docs" / "bugs" / "_archive"
    dest = archive_parent / bug_id

    try:
        # --- step 1: gate / resume detection --------------------------------
        resume = False
        if not spec_path.exists():
            if dest.exists():
                # Prior run moved the directory but died before repoint/commit.
                resume = True
            else:
                return _refuse(
                    f"spec_path does not exist and no archive at "
                    f"{dest.relative_to(repo_root).as_posix()} — nothing to archive"
                )
        if not resume:
            receipt_ok = has_completion_receipt(spec_path, "FIXED.md")
            wont_fix = (spec_status(spec_path) or "").startswith("Won't-fix")
            if not receipt_ok and not wont_fix:
                return _refuse(
                    "no FIXED.md receipt (kind: fixed) and SPEC is not "
                    "Won't-fix — run `--apply-pseudo __mark_fixed__` first; "
                    "archive_fixed never writes the receipt itself"
                )

            # --- step 2: SPEC.md evidence header lines -----------------------
            # Short sha of the last work commit BEFORE the archive commit — the
            # load-bearing evidence of when the fix landed (mark-fixed-archive
            # Step 1). Skipped for Won't-fix (no receipt → no fix commit).
            if receipt_ok:
                sha_proc = _git(repo_root, "rev-parse", "--short", "HEAD")
                fix_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
                if fix_sha:
                    result["fix_commit"] = fix_sha
                    spec_md = spec_path / "SPEC.md"
                    if spec_md.exists():
                        text = spec_md.read_text(encoding="utf-8")
                        # Update-in-place when the lines already exist…
                        text = re.sub(
                            r"^\*\*Fixed:\*\*.*$", f"**Fixed:** {date}",
                            text, count=1, flags=re.MULTILINE,
                        )
                        text = re.sub(
                            r"^\*\*Fix commit:\*\*.*$", f"**Fix commit:** {fix_sha}",
                            text, count=1, flags=re.MULTILINE,
                        )
                        # …then insert any that are still missing, after
                        # **Discovered:** (canonical field order per
                        # docs/bugs/CLAUDE.md: Status → Severity → Discovered →
                        # Fixed → Fix commit), falling back to **Status:**.
                        missing = []
                        if not re.search(r"^\*\*Fixed:\*\*", text, flags=re.MULTILINE):
                            missing.append(f"**Fixed:** {date}")
                        if not re.search(r"^\*\*Fix commit:\*\*", text, flags=re.MULTILINE):
                            missing.append(f"**Fix commit:** {fix_sha}")
                        if missing:
                            anchor = re.search(
                                r"^\*\*Discovered:\*\*.*$", text, flags=re.MULTILINE
                            ) or re.search(
                                r"^\*\*Status:\*\*.*$", text, flags=re.MULTILINE
                            )
                            if anchor:
                                insert_at = anchor.end()
                                text = (
                                    text[:insert_at]
                                    + "".join("\n" + line for line in missing)
                                    + text[insert_at:]
                                )
                            else:
                                # No header block at all — append (degenerate
                                # SPEC; keep the evidence rather than dropping it).
                                text = text.rstrip("\n") + "\n\n" + "\n".join(missing) + "\n"
                        _atomic_write(spec_md, text)

            # --- step 3: stage the bug dir (deletions included) --------------
            add_proc = _git(repo_root, "add", "-A", "--", str(spec_path))
            if add_proc.returncode != 0:
                return _refuse(
                    f"git add -A {spec_path.name} failed: {add_proc.stderr.strip()}"
                )

            # --- step 4: git mv with retry + per-file fallback ---------------
            archive_parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = archive_parent / f"{bug_id}-archived-{date}"
                if dest.exists():
                    return _refuse(
                        f"archive collision: both {bug_id} and "
                        f"{dest.name} already exist under _archive/"
                    )
            mv_err = ""
            moved = False
            for attempt, delay in enumerate((0, 1, 2, 4)):
                if delay:
                    time.sleep(delay)  # transient Windows handle/lock backoff
                mv_proc = _git(repo_root, "mv", str(spec_path), str(dest))
                if mv_proc.returncode == 0:
                    moved = True
                    break
                mv_err = mv_proc.stderr.strip()
            if not moved:
                # Per-file fallback: move every tracked file individually so a
                # single locked file is isolated instead of failing the whole
                # directory rename.
                ls_proc = _git(
                    repo_root, "ls-files", "--", str(spec_path)
                )
                if ls_proc.returncode != 0:
                    return _refuse(
                        f"git mv failed after retries ({mv_err}) and ls-files "
                        f"fallback failed: {ls_proc.stderr.strip()}"
                    )
                rel_spec = spec_path.relative_to(repo_root).as_posix()
                failed_files = []
                for rel in ls_proc.stdout.splitlines():
                    rel = rel.strip()
                    if not rel:
                        continue
                    suffix = rel[len(rel_spec):].lstrip("/")
                    target = dest / suffix
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f_proc = _git(repo_root, "mv", rel, str(target))
                    if f_proc.returncode != 0:
                        failed_files.append(f"{rel}: {f_proc.stderr.strip()}")
                if failed_files:
                    return _refuse(
                        "per-file git mv fallback left files behind — "
                        "PARTIAL STATE, resolve the locks and re-run: "
                        + "; ".join(failed_files)
                    )
                result["fallback_used"] = True
                # Remove the now-empty source tree (best-effort).
                for dirpath, dirnames, filenames in os.walk(spec_path, topdown=False):
                    if not filenames and not dirnames:
                        try:
                            os.rmdir(dirpath)
                        except OSError:
                            pass
                moved = True

        result["archived_to"] = dest.relative_to(repo_root).as_posix()

        # --- step 5: repoint inbound references (tracked *.md only) ----------
        old_ref = f"docs/bugs/{bug_id}/"
        # NOTE: dest may carry the -archived-<date> suffix; repoint to the
        # actual destination, not the canonical name.
        new_ref = dest.relative_to(repo_root).as_posix() + "/"
        grep_proc = _git(repo_root, "grep", "-l", "-F", old_ref, "--", "*.md")
        # returncode 1 = no matches (fine); >1 = real error.
        if grep_proc.returncode > 1:
            return _refuse(
                f"archived to {result['archived_to']} but inbound-reference "
                f"scan failed: {grep_proc.stderr.strip()} — PARTIAL STATE, "
                "re-run to resume"
            )
        for rel in grep_proc.stdout.splitlines():
            rel = rel.strip()
            if not rel:
                continue
            ref_path = repo_root / rel
            try:
                content = ref_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if old_ref in content:
                _atomic_write(ref_path, content.replace(old_ref, new_ref))
                result["repointed"].append(rel)

        # --- step 6: trim queue.json ------------------------------------------
        queue_path = repo_root / "docs" / "bugs" / "queue.json"
        if queue_path.exists():
            try:
                data = json.loads(queue_path.read_text(encoding="utf-8"))
                items = data.get("queue", [])
                kept = [
                    e for e in items
                    if not (
                        isinstance(e, dict)
                        and (e.get("spec_dir") == bug_id or e.get("id") == bug_id)
                    )
                ]
                if len(kept) != len(items):
                    data["queue"] = kept
                    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
                    result["queue_removed"] = True
            except (json.JSONDecodeError, AttributeError) as exc:
                return _refuse(
                    f"archived to {result['archived_to']} but queue.json is "
                    f"malformed ({exc}) — PARTIAL STATE, fix queue.json and re-run"
                )

        # --- step 7: stage + commit -------------------------------------------
        to_stage = ["docs/bugs"] + result["repointed"]
        add_proc = _git(repo_root, "add", "-A", "--", *to_stage)
        if add_proc.returncode != 0:
            return _refuse(
                f"archived to {result['archived_to']} but final staging "
                f"failed: {add_proc.stderr.strip()} — PARTIAL STATE, re-run"
            )
        diff_proc = _git(repo_root, "diff", "--cached", "--quiet")
        if diff_proc.returncode == 0:
            # Nothing staged — a re-run after a fully-completed prior pass.
            result["ok"] = True
            result["noop"] = True
            return result
        commit_proc = _git(
            repo_root, "commit", "-m",
            f"fix({bug_id}): mark fixed and archive — FIXED.md receipt gated",
        )
        if commit_proc.returncode != 0:
            return _refuse(
                f"archived to {result['archived_to']} but commit failed: "
                f"{commit_proc.stderr.strip()} — PARTIAL STATE (changes are "
                "staged), commit manually or re-run"
            )
        sha_proc = _git(repo_root, "rev-parse", "--short", "HEAD")
        result["committed"] = (
            sha_proc.stdout.strip() if sha_proc.returncode == 0 else "unknown"
        )
        result["ok"] = True
        return result
    except (OSError, subprocess.SubprocessError) as exc:
        return _refuse(f"git unavailable or I/O failure: {exc}")


def git_guard_status(repo_root: Path) -> dict:
    """Return a three-key git status snapshot for the probe payload.

    Runs three lightweight git commands against ``repo_root`` and returns a
    dict with the following keys:

    ``clean_tree`` (bool)
        True when ``git status --short`` produces no output (no staged,
        unstaged, or untracked changes).

    ``head_matches_origin`` (bool)
        True when ``git rev-parse HEAD`` equals ``git rev-parse @{u}``.
        False when the repo has no upstream configured or any git command
        fails.

    ``unpushed`` (bool)
        True when ``git rev-list --count @{u}..HEAD`` returns an integer > 0
        (local commits are ahead of the upstream tracking ref).  False on any
        git failure or when no upstream is configured.

    Error-handling contract (best-effort, mirrors verify_ledger / _current_head):
    - Each of the three checks is independent; a failure in one does not
      prevent the others from running.
    - Any ``OSError`` or ``subprocess.SubprocessError`` (including timeout)
      silently produces the safe-default value for that check.
    - When ``@{u}`` does not resolve (no upstream), both ``head_matches_origin``
      and ``unpushed`` are False; ``clean_tree`` still reflects the status
      command result if it succeeded.
    """
    # --- check 1: clean working tree -----------------------------------------
    # Mirror the subprocess style used in verify_ledger: capture_output + text
    # + explicit timeout + catch OSError/SubprocessError.
    try:
        status_result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Require a zero returncode in addition to empty stdout.  When
        # repo_root is not a git repo, `git status --short` exits 128 with
        # empty stdout — without the returncode guard that would produce a
        # false-positive clean_tree=True (contradicting the docstring contract
        # that an invalid repo → safe-dirty False, matching checks 2 and 3).
        clean_tree = (status_result.returncode == 0 and status_result.stdout.strip() == "")
    except (OSError, subprocess.SubprocessError):
        # Git unavailable or repo_root invalid — assume dirty so callers don't
        # proceed with a false-positive clean signal.
        clean_tree = False

    # --- check 2: HEAD matches upstream tracking ref -------------------------
    # Both rev-parse commands must succeed and return identical SHA strings.
    # @{u} fails with a non-zero returncode when no upstream is configured.
    try:
        head_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        upstream_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "@{u}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if head_result.returncode == 0 and upstream_result.returncode == 0:
            head_sha = head_result.stdout.strip()
            upstream_sha = upstream_result.stdout.strip()
            # Require both SHAs to be non-empty before comparing.
            head_matches_origin = bool(head_sha and upstream_sha and head_sha == upstream_sha)
        else:
            # @{u} can fail when no upstream is configured; treat as mismatch.
            head_matches_origin = False
    except (OSError, subprocess.SubprocessError):
        head_matches_origin = False

    # --- check 3: unpushed local commits -------------------------------------
    # rev-list --count @{u}..HEAD returns the number of commits ahead of the
    # upstream.  A non-zero integer means at least one local commit is unpushed.
    try:
        revlist_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", "@{u}..HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if revlist_result.returncode == 0:
            unpushed = int(revlist_result.stdout.strip()) > 0
        else:
            # No upstream or other git error — cannot determine ahead-count.
            unpushed = False
    except (OSError, subprocess.SubprocessError, ValueError):
        # ValueError covers int() failing on unexpected output.
        unpushed = False

    return {
        "clean_tree": clean_tree,
        "head_matches_origin": head_matches_origin,
        "unpushed": unpushed,
    }


# ---------------------------------------------------------------------------
# Phase 1 (lazy-cycle-containment, C8) — Self-edit reload discipline.
#
# When a /lazy-batch run executes *inside* claude-config it is editing the very
# harness it runs from. Most of that harness self-refreshes mid-run and needs NO
# reload — the AUTO-REFRESH BOUNDARY below. The ONLY surfaces that go stale are
# the orchestrator's own in-context governing prose: GOVERNING_FILE_SET.
#
# AUTO-REFRESH BOUNDARY (documented no-ops — MUST NOT be flagged for reload;
# they were never stale):
#   * lazy_core.py / lazy-state.py / bug-state.py — a fresh `python3` subprocess
#     runs on every probe, so an edit is live on the next probe.
#   * lazy-batch-prompts/cycle-base-prompt.md (+ addenda + loop-block.md) —
#     re-read by emit_cycle_prompt() from disk on every probe.
#   * hook .sh bodies — `bash ~/.claude/hooks/X.sh` reads the file each
#     invocation, so a body edit is live on the next tool call.
#   * downstream skill prose (SKILL.md a dispatched subagent loads) — each
#     dispatched subagent loads its skill fresh, so the edit is live next dispatch.
# These are EXCLUDED from GOVERNING_FILE_SET by construction.
#
# The governing-file set MUST stay in lockstep with the orchestrator's
# compaction re-read list (lazy-dispatch-template.md + orchestrator-voice.md +
# completeness-policy.md + the orchestrator's own SKILL.md) — the self-edit
# reload is the SAME re-read, triggered by a self-edit commit instead of a
# compaction boundary. Paths are repo-root-relative POSIX strings (the form
# `git diff --name-only` emits).
# ---------------------------------------------------------------------------
GOVERNING_FILE_SET: frozenset[str] = frozenset({
    # Orchestrator SKILLs the running orchestrator holds in-context (coupled trio).
    "user/skills/lazy-batch/SKILL.md",
    "user/skills/lazy-bug-batch/SKILL.md",
    "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
    # Components the orchestrator holds in-context (the compaction re-read list).
    "user/skills/_components/orchestrator-voice.md",
    "user/skills/_components/completeness-policy.md",
    "user/skills/_components/lazy-dispatch-template.md",
})


def self_edit_mode(repo_root: "str | Path") -> bool:
    """True iff this run is editing the harness it executes from.

    Returns True when ``~/.claude/skills``, ``~/.claude/scripts``, AND
    ``~/.claude/hooks`` ALL resolve (after ``os.path.realpath`` symlink
    resolution) to a path UNDER the run's ``git rev-parse --show-toplevel``.

    This is the semantically-correct predicate — robust to the repo being cloned
    to any path (it compares resolved real paths, NOT a brittle cwd-basename
    match). ``~`` is resolved via ``os.path.expanduser``.

    Returns False (never raises) when:
      * ``repo_root`` is not a git repo (``--show-toplevel`` fails);
      * any of the three ``~/.claude/*`` paths is missing or resolves OUTSIDE
        the toplevel;
      * any OS/subprocess error occurs.
    """
    # Resolve the run's git toplevel; non-git repo or any git failure → False.
    try:
        proc = _git(Path(repo_root), "rev-parse", "--show-toplevel", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    toplevel_raw = proc.stdout.strip()
    if not toplevel_raw:
        return False
    toplevel = os.path.realpath(toplevel_raw)

    for name in ("skills", "scripts", "hooks"):
        candidate = os.path.join(os.path.expanduser("~"), ".claude", name)
        if not os.path.exists(candidate):
            return False
        resolved = os.path.realpath(candidate)
        # Membership test on the resolved real paths: resolved must be the
        # toplevel itself or a descendant of it.
        try:
            common = os.path.commonpath([toplevel, resolved])
        except ValueError:
            # Different drives (Windows) or otherwise incomparable → not under.
            return False
        if common != toplevel:
            return False
    return True


def governing_files_touched(repo_root: "str | Path") -> list[str]:
    """Return the GOVERNING_FILE_SET members touched by the last commit.

    Intersects the last commit's changed files (``git diff --name-only HEAD~1
    HEAD``; falls back to the root-commit file list when there is no parent)
    with GOVERNING_FILE_SET. Auto-refresh surfaces never appear (they are not in
    the set). Best-effort: any git failure returns ``[]`` (the orchestrator's
    reload check then simply finds nothing to reload).
    """
    try:
        proc = _git(repo_root if isinstance(repo_root, Path) else Path(repo_root),
                    "diff", "--name-only", "HEAD~1", "HEAD", timeout=30)
        if proc.returncode != 0:
            # No parent commit (root commit): list the commit's own files.
            proc = _git(repo_root if isinstance(repo_root, Path) else Path(repo_root),
                        "show", "--name-only", "--pretty=format:", "HEAD",
                        timeout=30)
            if proc.returncode != 0:
                return []
    except (OSError, subprocess.SubprocessError):
        return []
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    return sorted(changed & GOVERNING_FILE_SET)


def format_cycle_header(
    state: dict,
    *,
    forward_cycles: "int | None" = None,
    max_cycles: "int | None" = None,
    meta_cycles: "int | None" = None,
) -> str:
    """Return a formatted cycle-header line for the orchestrator probe payload.

    Produces a string in EXACTLY this form (separators are U+00B7 MIDDLE DOT
    ``·``, and the em-dash placeholder is U+2014 ``—``):

        ### Cycle fwd {fwd}/{max} · meta {meta} · {feature} · {sub_skill}

    Counter rendering:
    - ``{fwd}``    = ``forward_cycles`` if not None else ``?``
    - ``{max}``    = ``max_cycles`` if not None else ``?``
    - ``{meta}``   = ``meta_cycles`` if not None else ``?``  (COUNT ONLY — no
      denominator: meta_cycles has NO ceiling. Operator decision 2026-06-14 —
      the meta loop is unbounded; only forward_cycles is capped at max_cycles.)

    State field rendering:
    - ``{feature}``   = ``state.get("feature_id")`` if truthy else ``—`` (U+2014)
    - ``{sub_skill}`` = ``state.get("sub_skill")``  if truthy else ``—`` (U+2014)
    """
    # Render each counter: use the value when supplied, else the '?' placeholder.
    fwd_str = str(forward_cycles) if forward_cycles is not None else "?"
    max_str = str(max_cycles) if max_cycles is not None else "?"
    meta_str = str(meta_cycles) if meta_cycles is not None else "?"

    # Render state fields: use the value when truthy, else the em-dash sentinel.
    feature_str = state.get("feature_id") or "—"
    sub_skill_str = state.get("sub_skill") or "—"

    # meta is a bare COUNT (no "/cap") — meta_cycles is uncapped by design.
    return (
        f"### Cycle fwd {fwd_str}/{max_str}"
        f" · meta {meta_str}"
        f" · {feature_str}"
        f" · {sub_skill_str}"
    )


# ---------------------------------------------------------------------------
# Phase 8 WU-2: script-assembled cycle dispatch prompt (emit_cycle_prompt)
# ---------------------------------------------------------------------------
#
# Moves the LAST unscripted deterministic orchestrator mechanic — re-typing the
# ~2K-token cycle dispatch prompt every dispatch — into the state scripts. The
# emitter parses the sectioned, parameterized `cycle-base-prompt.md`, selects
# the sections that apply to this (pipeline, mode, sub_skill) cycle, binds the
# 14 tokens, optionally appends the loop block, and returns the finished prompt
# + the model to dispatch it under. See the template file's header comment for
# the authoritative marker grammar / selection semantics / token inventory.

# Default cycle-prompt template directory, resolved through this module's own
# path. lazy_core.py lives at <claude-config>/user/scripts/lazy_core.py, so
# parent.parent is <claude-config>/user, and the templates live under
# skills/_components/lazy-batch-prompts/. The PHASES "Validated Assumptions"
# table confirms this resolves correctly through the ~/.claude symlink chain.
_CYCLE_TEMPLATE_DIRNAME = ("skills", "_components", "lazy-batch-prompts")

# The marker line shape the emitter parses, e.g.:
#   <!-- @section task pipelines=feature,bug modes=workstation skills=all -->
# with an optional `variant=runtime-up|no-runtime` token before the closing
# `-->`. Attributes are matched by key=value tokens (order-tolerant), so the
# variant attribute's position in the file is not load-bearing.
_SECTION_MARKER_RE = re.compile(r"^<!--\s*@section\s+(?P<rest>.*?)\s*-->\s*$")

# Residue regex: any `{lower_snake_or_digit}` token surviving the bind is an
# unbound token the emitter REFUSES on (never emits a half-bound prompt).
# Widened to include digits so tokens like {item_id} and {item_id2} are caught —
# previously `\{[a-z_]+\}` allowed digit-bearing tokens to pass through silently.
_PROMPT_RESIDUE_RE = re.compile(r"\{[a-z0-9_]+\}")


def _default_cycle_template_dir() -> Path:
    """Resolve the default cycle-prompt template dir from this module's path."""
    return Path(__file__).resolve().parent.parent.joinpath(*_CYCLE_TEMPLATE_DIRNAME)


def _standard_dispatch_bindings(pipeline: str) -> dict[str, str]:
    """Return the standard pipeline-token bindings shared by emit_cycle_prompt and
    emit_dispatch_prompt.

    These five tokens appear in every dispatch template and in the cycle base
    template.  Factored out here so the two emitters stay byte-identical on the
    same input without code duplication.

    Args:
        pipeline: ``"feature"`` or ``"bug"``.

    Returns:
        A fresh dict with the five standard pipeline tokens bound to their
        pipeline-appropriate values.
    """
    is_bug = pipeline == "bug"
    return {
        "item_label":       "Bug" if is_bug else "Feature",
        "pipeline_phrase":  "bug pipeline" if is_bug else "feature pipeline",
        "receipt_name":     "FIXED.md" if is_bug else "COMPLETED.md",
        "mark_pseudo":      "__mark_fixed__" if is_bug else "__mark_complete__",
        "forbidden_status": "Fixed or Won't-fix" if is_bug else "Complete",
    }


def _dedup_residue(tokens: list[str]) -> list[str]:
    """Return ``tokens`` deduplicated while preserving first-seen order.

    Used by the residue guard in both emit_cycle_prompt and emit_dispatch_prompt
    to produce a stable, human-readable list of unbound {token} names.
    """
    seen: list[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.append(tok)
    return seen


def _emit_work_branch(repo_root: Path) -> str:
    """Resolve repo_root's current branch name for the {work_branch} token.

    Best-effort, mirroring _current_head's subprocess guard: any non-zero exit,
    empty output, or OS/subprocess error falls back to the literal string
    ``"the current branch"`` so the emitter never raises on a non-git root."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            branch = r.stdout.strip()
            if branch:
                return branch
    except (OSError, subprocess.SubprocessError):
        pass
    return "the current branch"


def _parse_section_attrs(rest: str) -> dict[str, str]:
    """Parse the attribute tokens of a `@section` marker into a dict.

    `rest` is the text between `@section` and the closing `-->` (already
    stripped), e.g. ``task pipelines=feature,bug modes=workstation skills=all``.
    The first whitespace token is the section NAME (stored under the special
    key ``"name"``); every remaining ``key=value`` token is stored verbatim.
    Tokens without an ``=`` (other than the leading name) are ignored.
    """
    tokens = rest.split()
    if not tokens:
        return {}
    attrs: dict[str, str] = {"name": tokens[0]}
    for tok in tokens[1:]:
        if "=" in tok:
            key, _, value = tok.partition("=")
            attrs[key] = value
    return attrs


def _parse_cycle_template(text: str) -> list[dict[str, Any]]:
    """Split a cycle-base-prompt template into its `@section` blocks.

    Everything BEFORE the first marker line is template metadata and is dropped.
    Each returned dict has: ``attrs`` (the parsed marker attributes, incl.
    ``name``) and ``content`` (the section body with leading/trailing blank
    lines stripped). A section's content runs from the line AFTER its marker to
    the line BEFORE the next marker (or EOF).
    """
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    body: list[str] = []

    def _flush():
        if current is not None:
            # Strip leading/trailing blank lines from the accumulated body.
            content_lines = body[:]
            while content_lines and not content_lines[0].strip():
                content_lines.pop(0)
            while content_lines and not content_lines[-1].strip():
                content_lines.pop()
            current["content"] = "\n".join(content_lines)
            sections.append(current)

    for line in lines:
        m = _SECTION_MARKER_RE.match(line)
        if m:
            # New section starts — finish the previous one (if any).
            _flush()
            current = {"attrs": _parse_section_attrs(m.group("rest"))}
            body = []
        elif current is not None:
            # Accumulate content (lines before the first marker are metadata).
            body.append(line)
    _flush()
    return sections


def _csv_set(value: str | None) -> set[str]:
    """Split a comma-separated attribute value into a set of trimmed tokens."""
    if not value:
        return set()
    return {tok.strip() for tok in value.split(",") if tok.strip()}


def _read_mcp_runtime_decision(spec_path: str | None) -> tuple[str, str | None]:
    """Decide the mcp-test runtime variant + untestability reason from PHASES.md.

    Reads ``{spec_path}/PHASES.md`` and looks for a line starting
    ``**MCP runtime:**``:
      - contains ``not-required`` → ``("no-runtime", <reason>)`` where reason is
        the text after the first ``-`` / ``—`` dash on that line (or a fallback
        when no dash is present).
      - any other value, line absent, or file/dir absent → ``("runtime-up", None)``.

    Never raises: an unreadable file is treated as "line absent" → runtime-up.
    """
    fallback_reason = "the plan declares no MCP-reachable surface"
    if not spec_path:
        return ("runtime-up", None)
    phases = Path(spec_path) / "PHASES.md"
    try:
        text = phases.read_text(encoding="utf-8")
    except OSError:
        return ("runtime-up", None)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**MCP runtime:**"):
            if "not-required" in stripped:
                # Reason = text after the first dash (ASCII '-' or em-dash '—').
                reason = fallback_reason
                for dash in ("—", "-"):
                    idx = stripped.find(dash)
                    if idx != -1:
                        candidate = stripped[idx + len(dash):].strip()
                        if candidate:
                            reason = candidate
                        break
                return ("no-runtime", reason)
            # Line present but not the not-required value → runtime-up.
            return ("runtime-up", None)
    # No **MCP runtime:** line at all → runtime-up.
    return ("runtime-up", None)


def emit_cycle_prompt(
    repo_root: Path,
    state: dict,
    *,
    pipeline: str,
    cloud: bool = False,
    repeat_count: int | None = None,
    template_dir: Path | None = None,
) -> dict | None:
    """Assemble the cycle dispatch prompt for one orchestrator cycle.

    The state scripts call this under ``--emit-prompt`` so the orchestrator
    never re-types the boilerplate prompt (the 2026-06-10 audit found this was
    ~70% of the orchestrator's output tokens). The emitter is the single
    assembler: it parses the sectioned ``cycle-base-prompt.md``, selects the
    sections matching this cycle, binds the tokens, optionally appends the loop
    block, and returns the finished prompt + dispatch model.

    Args:
        repo_root: the project root (used for {cwd} and {work_branch}).
        state: the dict ``compute_state`` produced. Consumed keys:
            ``feature_id``, ``feature_name``, ``spec_path``, ``current_step``,
            ``sub_skill``, ``sub_skill_args`` (bug-state reuses the feature_*
            keys for bugs).
        pipeline: ``"feature"`` or ``"bug"`` — selects per-pipeline sections and
            the bug/feature token bindings.
        cloud: when True the mode is ``"cloud"``, else ``"workstation"``.
        repeat_count: the consecutive-identical-probe count; when ``>= 2`` the
            loop block is appended and the dispatch model flips to ``"sonnet"``.
        template_dir: override the template directory (for tests). Defaults to
            the resolved ``skills/_components/lazy-batch-prompts/`` dir.

    Returns:
        ``None`` when the probe is not a dispatchable real-skill cycle —
        ``sub_skill`` is falsy, ``sub_skill`` starts with ``"__"`` (a pseudo-skill
        the orchestrator applies via ``--apply-pseudo``, not a dispatched skill),
        or ``feature_id`` is falsy (a terminal / idle probe). This keeps the
        orchestrator's single probe call uniform — the field is always present.

        Otherwise a dict: ``{"ok": True, "prompt": <str>, "model": "opus"|"sonnet"}``
        on success, or ``{"ok": False, "refused": <reason>}`` when binding leaves
        an unbound ``{token}`` (the emitter never emits a half-bound prompt). The
        function never raises on bad template content — it refuses instead.
    """
    sub_skill = state.get("sub_skill")
    # Not a dispatchable real-skill cycle → None (uniform "no prompt" signal).
    if not sub_skill or sub_skill.startswith("__"):
        return None
    if not state.get("feature_id"):
        return None

    if template_dir is None:
        template_dir = _default_cycle_template_dir()

    mode = "cloud" if cloud else "workstation"
    # Normalize the sub_skill for skills-csv matching: strip a leading "/".
    norm_skill = sub_skill[1:] if sub_skill.startswith("/") else sub_skill

    # --- Read + parse the base template (refuse, never raise, on bad input) ---
    base_path = template_dir / "cycle-base-prompt.md"
    try:
        base_text = base_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "refused": f"cannot read cycle-base-prompt.md: {exc}"}

    sections = _parse_cycle_template(base_text)

    # --- mcp-test runtime variant decision (only consulted for mcp-test) ------
    runtime_variant, untestability_reason = _read_mcp_runtime_decision(
        state.get("spec_path")
    )

    # --- Select the sections that apply to this cycle -------------------------
    selected: list[str] = []
    for sec in sections:
        attrs = sec["attrs"]
        pipelines = _csv_set(attrs.get("pipelines"))
        modes = _csv_set(attrs.get("modes"))
        skills = attrs.get("skills", "")
        if pipeline not in pipelines:
            continue
        if mode not in modes:
            continue
        # skills=all OR the normalized sub_skill is in the csv.
        if skills != "all" and norm_skill not in _csv_set(skills):
            continue
        # variant= sections are mcp-test-only and additionally filtered by the
        # runtime decision (the emitter picks EXACTLY ONE variant).
        variant = attrs.get("variant")
        if variant is not None:
            if norm_skill != "mcp-test" or variant != runtime_variant:
                continue
        if sec["content"]:
            selected.append(sec["content"])

    # --- Repo prompt addenda (Phase 10 WU-3) ----------------------------------
    # After the base sections (and BEFORE the loop block), append any matching
    # sections from the OPTIONAL repo addenda file. The addenda path is keyed off
    # repo_root (NOT template_dir): it is the established per-repo config surface
    # (.claude/skill-config/). Parsing + selection reuse the SAME helpers as the
    # base template (no duplicated grammar), and the appended content is bound +
    # residue-guarded by the SAME map below — so a bad addenda section refuses the
    # WHOLE emission exactly like a bad base section. Absent file (or a file with
    # no matching sections) → no change, byte-identical to base-only behavior.
    # Orchestrators must NEVER hand-append to cycle_prompt; repo-specific gates
    # live here (a live orchestrator hand-spliced the AlgoBooth audio-INVARIANTS
    # gate onto the emitted prompt on 2026-06-11 — that path is now closed).
    addenda_path = repo_root / ".claude" / "skill-config" / "cycle-prompt-addenda.md"
    # Track addenda-contributed content separately so the residue guard can name
    # the addenda file when an unbound token came from a (mis-authored) addenda
    # section rather than the base template.
    addenda_selected: list[str] = []
    try:
        addenda_text = addenda_path.read_text(encoding="utf-8")
    except OSError:
        # Absent / unreadable → no addenda (the common, byte-identical path).
        addenda_text = None
    if addenda_text is not None:
        for sec in _parse_cycle_template(addenda_text):
            attrs = sec["attrs"]
            if pipeline not in _csv_set(attrs.get("pipelines")):
                continue
            if mode not in _csv_set(attrs.get("modes")):
                continue
            skills = attrs.get("skills", "")
            if skills != "all" and norm_skill not in _csv_set(skills):
                continue
            # Addenda sections may carry a variant= attribute too (same mcp-test
            # one-variant rule), kept for parity with the base selection logic.
            variant = attrs.get("variant")
            if variant is not None:
                if norm_skill != "mcp-test" or variant != runtime_variant:
                    continue
            if sec["content"]:
                addenda_selected.append(sec["content"])
    # Appended AFTER base sections — order: base → addenda → (loop block below).
    selected.extend(addenda_selected)

    # --- Token bindings (per-pipeline + per-state) ----------------------------
    # Standard pipeline tokens come from the shared helper; cycle-specific tokens
    # are layered on top (context wins on collision, same as emit_dispatch_prompt).
    bindings = _standard_dispatch_bindings(pipeline)
    bindings.update({
        "item_name": state.get("feature_name") or "",
        "item_id": state.get("feature_id") or "",
        "cwd": str(repo_root),
        "current_step": state.get("current_step") or "",
        "sub_skill": sub_skill,
        # sub_skill_args binds to "" when None so the prompt never shows "None".
        "sub_skill_args": state.get("sub_skill_args") or "",
        "spec_path": state.get("spec_path") or "",
        "work_branch": _emit_work_branch(repo_root),
        # untestability_reason is only present in the no-runtime mcp-test section;
        # bind it whenever a reason was derived (fallback applies otherwise).
        "untestability_reason": untestability_reason
        or "the plan declares no MCP-reachable surface",
    })

    prompt = "\n\n".join(selected)

    # --- Per-part complexity model tiering (Phase 9 — lazy-validation-readiness)
    # The /execute-plan cycle's dispatch model is selected from the CURRENT plan
    # part's `complexity:` frontmatter tag:
    #     mechanical → sonnet ; complex / absent / untagged → opus.
    # The plan part is `state["sub_skill_args"]` (the plan path) when the cycle
    # is an /execute-plan dispatch — the ONLY cycle this tiering applies to (a
    # /retro, /spec, /mcp-test, etc. cycle is unaffected and stays opus). Gated
    # strictly on the explicit tag /write-plan emitted: `plan_complexity` returns
    # the SAFE `complex`/opus default for any uncertain case, so the model never
    # auto-guesses cheaper. This baseline composes with the loop-block downgrade
    # below: a `complex`/opus part that loops (repeat_count>=2) still flips to
    # sonnet (sonnet ∧ sonnet = sonnet), and a `mechanical`/sonnet part stays
    # sonnet — the two never conflict because both only ever DOWNGRADE to sonnet.
    model = "opus"
    norm_sub_skill = norm_skill  # already leading-"/"-stripped above
    if norm_sub_skill in ("execute-plan", "execute_plan"):
        plan_arg = state.get("sub_skill_args")
        if plan_arg:
            # sub_skill_args may carry trailing flags (e.g. "<plan> --batch");
            # the plan path is the first whitespace-delimited token.
            plan_token = str(plan_arg).split()[0] if str(plan_arg).split() else ""
            if plan_token and plan_complexity(Path(plan_token)) == "mechanical":
                model = "sonnet"

    # --- Loop block: appended when the same signature repeated (>= 2) ---------
    # The loop block lives in loop-block.md inside a ``` fence; strip the fence
    # lines and bind its tokens. Model flips to sonnet when the block is added.
    if repeat_count is not None and repeat_count >= 2:
        loop_path = template_dir / "loop-block.md"
        try:
            loop_text = loop_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "refused": f"cannot read loop-block.md: {exc}"}
        loop_inner = _strip_loop_fence(loop_text)
        if loop_inner:
            prompt = prompt + "\n\n" + loop_inner if prompt else loop_inner
            model = "sonnet"

    # --- Bind all tokens (all occurrences, all sections + loop block) ---------
    for token, value in bindings.items():
        prompt = prompt.replace("{" + token + "}", value)

    # --- Residue guard: any surviving {token} → refuse (never half-bound) -----
    residue = _PROMPT_RESIDUE_RE.findall(prompt)
    if residue:
        seen = _dedup_residue(residue)
        # Attribute the residue to the addenda file when an unbound token traces
        # back to a (mis-authored) addenda section — so the operator knows which
        # file to fix. We bind the addenda blob in isolation and check whether
        # any of the surviving tokens originated there.
        suffix = ""
        if addenda_selected:
            addenda_blob = "\n\n".join(addenda_selected)
            for token, value in bindings.items():
                addenda_blob = addenda_blob.replace("{" + token + "}", value)
            addenda_residue = set(_PROMPT_RESIDUE_RE.findall(addenda_blob))
            if addenda_residue & set(seen):
                suffix = (
                    " (from .claude/skill-config/cycle-prompt-addenda.md — fix or "
                    "remove the offending addenda section)"
                )
        return {"ok": False, "refused": "unbound tokens: " + ", ".join(seen) + suffix}

    return {"ok": True, "prompt": prompt, "model": model}


def _strip_loop_fence(loop_text: str) -> str:
    """Extract the inner text of loop-block.md, dropping its ``` code fence.

    loop-block.md wraps its emittable body in a single ```-fenced block (after a
    metadata header comment). This returns the content BETWEEN the opening and
    closing fence lines, with leading/trailing blank lines stripped. When no
    fence is found (defensive), the whole text minus blank edges is returned.
    """
    lines = loop_text.splitlines()
    fence_idxs = [i for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    if len(fence_idxs) >= 2:
        inner = lines[fence_idxs[0] + 1: fence_idxs[1]]
    else:
        inner = lines
    while inner and not inner[0].strip():
        inner.pop(0)
    while inner and not inner[-1].strip():
        inner.pop()
    return "\n".join(inner)


# ---------------------------------------------------------------------------
# Phase 3 — emit_dispatch_prompt: every remaining dispatch class becomes
#            script-emitted.  Reuses the same template grammar and binding/
#            residue machinery as emit_cycle_prompt — no reimplementation.
#
# Six classes (Phase 3); 'hardening' is deferred to Phase 4.
# Model assignments derive from the SOURCE COMPONENTS (not the SPEC.md, which
# pins no per-class models):
#   apply-resolution → opus  (blocked-resolution.md dispatches its apply subagent
#                             as Opus: judgment work — enacting Add-a-phase,
#                             Defer, or custom operator directives)
#   recovery / coherence-recovery → sonnet (bounded mechanical reconciliation)
#   input-audit / investigation / needs-runtime-redispatch → opus (judgment)
# ---------------------------------------------------------------------------

# The ordered tuple of dispatch classes.  Phase 3 added the first 6; Phase 4
# appends 'hardening' as the 7th entry (the harness-hardening stage class).
DISPATCH_CLASSES: tuple[str, ...] = (
    "apply-resolution",
    "input-audit",
    "investigation",
    "recovery",
    "coherence-recovery",
    "needs-runtime-redispatch",
    "hardening",          # Phase 4 — harness-hardening stage (always Opus)
)

# Model to use when dispatching each class.  'opus' for judgment work;
# 'sonnet' for bounded mechanical work.  Source: the dispatch SOURCE COMPONENTS
# (blocked-resolution.md, decision-resume.md, investigation-dispatch.md, etc.).
DISPATCH_MODELS: dict[str, str] = {
    "apply-resolution":        "opus",    # blocked-resolution.md: Opus apply subagent
    "input-audit":             "opus",
    "investigation":           "opus",
    "recovery":                "sonnet",
    "coherence-recovery":      "sonnet",
    "needs-runtime-redispatch": "opus",
    "hardening":               "opus",   # Phase 4 — root-cause + mechanical fixes = Opus
}

# Regex to extract @requires keys from the first non-empty line of a dispatch
# template, e.g.: <!-- @requires item_id,spec_path,sentinel_path -->
_DISPATCH_REQUIRES_RE = re.compile(r"^<!--\s*@requires\s+([a-z0-9_,]+)\s*-->")


def load_context_json(text: str) -> dict:
    """Parse a --context-file / --context-stdin JSON payload into a context dict.

    ISSUE 3 (d8-effect-chains live /lazy-batch run, 2026-06-14): a ~1500-char
    ``failure_summary`` with commas/colons/parens/newlines was unreliable as an
    inline ``--context KEY=VALUE`` flag (the shell — not the script — mangled it).
    The JSON channel sidesteps shell quoting entirely: the orchestrator writes the
    payload to a file (or pipes it) and the value may contain ANY characters.

    Validation is strict so a malformed payload becomes a STRUCTURED error in the
    --emit-dispatch handler rather than silently-empty context:
      - The decoded JSON MUST be an object (dict). A list/str/number → ValueError.
      - Every key MUST be a string. A non-string key → ValueError.
      - Values are coerced to str (None → "") to match the inline-flag contract
        (emit_dispatch_prompt stringifies all bindings anyway).

    Raises:
        ValueError: on invalid JSON, a non-object top level, or a non-string key.
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"context payload is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(
            f"context payload must be a JSON object, got {type(obj).__name__}"
        )
    out: dict = {}
    for key, value in obj.items():
        if not isinstance(key, str):
            raise ValueError(f"context key must be a string, got {key!r}")
        out[key] = "" if value is None else str(value)
    return out

# Phase 7 WU-7.5a: per-class Step name for the meta cycle_header.  The header
# the orchestrator echoes is `### {Step} — {summary} [meta {m}]` (bare count, no
# cap — meta_cycles is uncapped as of 2026-06-14); this map
# pins {Step} per the PHASES.md Phase 7 interface contract so every meta dispatch
# carries a canonical heading (0/8 meta cycles carried one before this WU).
DISPATCH_STEP_NAMES: dict[str, str] = {
    "investigation":            "Investigate",
    "apply-resolution":         "Resolve",
    "recovery":                 "Recover",
    "coherence-recovery":       "Recover",
    "hardening":                "Harden",
    "input-audit":              "Audit",
    "needs-runtime-redispatch": "Validate",
}


def emit_dispatch_prompt(
    cls: str,
    context: dict,
    *,
    pipeline: str,
    cloud: bool = False,
    template_dir: "Path | None" = None,
) -> dict:
    """Assemble a fully-bound dispatch prompt for one of the Phase 3 dispatch
    classes.

    Unlike ``emit_cycle_prompt`` (which assembles cycle prompts from state-script
    probe output), this assembler is called with an *explicit* context dict that
    the orchestrator builds from probe output + sentinel paths.  The matched
    template lives at ``dispatch-<cls>.md`` inside the same
    ``lazy-batch-prompts/`` directory used by the cycle emitter.

    The template grammar is identical to ``cycle-base-prompt.md``:
      - First non-empty line MUST be ``<!-- @requires key1,key2,... -->``
        declaring the *class-specific* context keys this template needs.
      - Subsequent lines use ``<!-- @section name pipelines=... modes=... -->``
        markers and ``{lower_snake}`` token placeholders.

    Standard pipeline tokens are always bound (same set as emit_cycle_prompt):
      {item_label}, {pipeline_phrase}, {receipt_name}, {mark_pseudo},
      {forbidden_status}
    Context dict values are overlaid on top (context wins on collision).

    Refusal semantics (mirrors emit_cycle_prompt — never half-binds):
      - Missing @requires key in context → refused, names the first missing key.
      - Unbound {token} residue after binding → refused, names the residue.
      - Unknown cls → ValueError (not a refusal dict — caller error).

    Args:
        cls: dispatch class name.  Must be in DISPATCH_CLASSES or DISPATCH_MODELS
             (Phase 4 will add 'hardening' before that class's template exists).
        context: dict of class-specific token values supplied by the caller.
        pipeline: ``"feature"`` or ``"bug"`` — section filtering + standard tokens.
        cloud: ``True`` → mode ``"cloud"``; ``False`` → mode ``"workstation"``.
        template_dir: override the template directory (for tests and Phase 4).
                      Defaults to the same ``lazy-batch-prompts/`` dir used by
                      emit_cycle_prompt.

    Returns:
        On success: ``{"ok": True, "prompt": <str>, "model": <"opus"|"sonnet">}``;
          additionally ``"cycle_header"`` (Phase 7 WU-7.5a) when a run marker is
          present (marker-gated — omitted entirely with no marker so no-marker
          callers stay byte-identical).
        On refusal: ``{"ok": False, "refused": <reason_str>}``

    Raises:
        ValueError: when ``cls`` is not a known dispatch class.
    """
    # --- Unknown-class guard (caller error — must raise, not refuse) -----------
    # Combine DISPATCH_CLASSES + DISPATCH_MODELS keys so Phase 4 can extend
    # DISPATCH_MODELS before or after appending to DISPATCH_CLASSES without a gap.
    all_known = set(DISPATCH_CLASSES) | set(DISPATCH_MODELS.keys())
    if cls not in all_known:
        raise ValueError(
            f"emit_dispatch_prompt: unknown dispatch class {cls!r}. "
            f"Known classes: {sorted(all_known)}"
        )

    if template_dir is None:
        template_dir = _default_cycle_template_dir()

    mode = "cloud" if cloud else "workstation"

    # --- Read the dispatch template -------------------------------------------
    tpl_path = template_dir / f"dispatch-{cls}.md"
    try:
        tpl_text = tpl_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "refused": f"cannot read dispatch-{cls}.md: {exc}"}

    # --- Parse @requires from line 1 ------------------------------------------
    # The first non-empty line must declare the class-specific required keys.
    first_line = next((ln for ln in tpl_text.splitlines() if ln.strip()), "")
    m = _DISPATCH_REQUIRES_RE.match(first_line)
    if not m:
        return {
            "ok": False,
            "refused": (
                f"dispatch-{cls}.md: first non-empty line must be "
                f"'<!-- @requires key1,key2,... -->' (only [a-z0-9_,] chars); "
                f"got: {first_line!r}"
            ),
        }
    requires_keys = [k.strip() for k in m.group(1).split(",") if k.strip()]

    # --- Validate that all @requires keys are present in context ---------------
    for key in requires_keys:
        if key not in context:
            return {
                "ok": False,
                "refused": (
                    f"dispatch-{cls}.md requires context key {key!r} which is "
                    f"absent from the supplied context dict. "
                    f"All @requires keys: {requires_keys}"
                ),
            }

    # --- Parse sections (reuse the same machinery as emit_cycle_prompt) --------
    sections = _parse_cycle_template(tpl_text)

    # --- Section selection by pipeline + mode (no skills= filtering needed) ---
    selected: list[str] = []
    for sec in sections:
        attrs = sec["attrs"]
        pipelines = _csv_set(attrs.get("pipelines"))
        modes = _csv_set(attrs.get("modes"))
        if pipeline not in pipelines:
            continue
        if mode not in modes:
            continue
        if sec["content"]:
            selected.append(sec["content"])

    prompt = "\n\n".join(selected)

    # --- Build the binding map -------------------------------------------------
    # Standard pipeline tokens come from the shared helper; context dict values
    # are overlaid on top (context wins on collision — the caller provides the
    # class-specific tokens; standard tokens above are the fallback defaults).
    bindings: dict[str, str] = _standard_dispatch_bindings(pipeline)
    for key, value in context.items():
        bindings[key] = str(value) if value is not None else ""

    # --- Bind all tokens -------------------------------------------------------
    for token, value in bindings.items():
        prompt = prompt.replace("{" + token + "}", value)

    # --- Residue guard: any surviving {lower_snake_or_digit} → refuse ----------
    residue = _PROMPT_RESIDUE_RE.findall(prompt)
    if residue:
        seen = _dedup_residue(residue)
        return {
            "ok": False,
            "refused": (
                f"dispatch-{cls}.md: unbound token(s) after binding: "
                + ", ".join(seen)
                + " — either add to @requires or remove from the template"
            ),
        }

    # --- Return assembled prompt + model assignment ----------------------------
    model = DISPATCH_MODELS.get(cls, "opus")
    result: dict = {"ok": True, "prompt": prompt, "model": model}

    # --- Meta cycle_header (Phase 7 WU-7.5a — MARKER-GATED) --------------------
    # When a run marker is present, attach a canonical cycle heading the
    # orchestrator echoes verbatim:  ### {Step} — {summary} [meta {m}]
    #   Step    : from DISPATCH_STEP_NAMES (per the Phase 7 interface contract).
    #   summary : the work summary — context item_name, fallback item_id, fallback
    #             the class name.
    #   m       : the marker's persisted meta counter + 1 — the cycle THIS dispatch
    #             will consume (1-based current-cycle semantics, matching the
    #             forward cycle_header's POST-advance convention noted in Phase 1).
    # COUNT ONLY — no "/cap" denominator: meta_cycles has NO ceiling (operator
    # decision 2026-06-14 — the meta loop is unbounded; only forward_cycles is
    # capped at max_cycles).
    # No marker → no cycle_header key at all, so no-marker emissions remain
    # byte-identical to the Phase 3/4 shape.
    marker = read_run_marker()
    if marker is not None:
        step = DISPATCH_STEP_NAMES.get(cls, cls)
        summary = (
            context.get("item_name")
            or context.get("item_id")
            or cls
        )
        meta_now = marker.get("meta_cycles", 0) or 0
        m = meta_now + 1
        result["cycle_header"] = f"### {step} — {summary} [meta {m}]"

    return result


# ---------------------------------------------------------------------------
# Phase 1 — Run-state core: claude_state_dir, run marker, prompt registry,
#            persisted run counters
#
# All writes use _atomic_write (defined above) to prevent partial-write
# corruption across platforms.  All new behavior is gated on an explicit
# --run-start / marker-present path so the default (no-marker) output of
# both state scripts remains byte-identical.
# ---------------------------------------------------------------------------

# Registry TTL: unconsumed entries older than this are not dispatchable.
# 30 minutes is a deliberate approximation of "current turn window" — hooks
# have no reliable turn counter, so we use two complementary controls:
#   1. Single-use nonce + TTL (REGISTRY_ENTRY_TTL_SECONDS): entries expire 30
#      minutes after emission regardless of run marker state.
#   2. Run-start freshness gate (belt-and-braces): when a valid run marker is
#      present, lookup_emission additionally requires emitted_at >= marker's
#      started_at epoch — entries that predate the current run are never
#      dispatchable even if they are within the TTL window.  When no marker is
#      present the gate is skipped and only nonce+TTL semantics apply.
# SPEC deviation (recorded): the spec §Validate-deny step 2 says "emitted_at
# within the current turn window"; we approximate that as nonce + TTL +
# emitted_at-vs-started_at rather than a per-turn counter that hooks cannot
# observe.
REGISTRY_ENTRY_TTL_SECONDS: int = 1800  # 30 minutes

# Maximum number of entries kept in the prompt registry (ring cap).
# When a new entry would exceed the cap, the oldest entry is evicted first.
_REGISTRY_RING_CAP: int = 64

# Marker filename inside the state dir.
_MARKER_FILENAME = "lazy-run-marker.json"

# Registry filename inside the state dir.
_REGISTRY_FILENAME = "lazy-prompt-registry.json"

# Phase 7 WU-7.1: deny-ledger filename (one JSON object per line; JSONL).
# The guard appends one entry on EVERY deny; --emit-dispatch hardening acks the
# oldest unacked entry (FIFO); --run-end refuses on unacked entries unless
# --ack-unhardened is passed.
_DENY_LEDGER_FILENAME = "lazy-deny-ledger.jsonl"

# Phase 7 WU-7.4: run-checkpoint filename (single JSON object).  Written by
# --run-end --reason checkpoint; consumed (echoed + deleted) by the next
# --run-start.  Consume-once resume context across a sanctioned pause.
_CHECKPOINT_FILENAME = "lazy-run-checkpoint.json"

# Phase 7: max characters retained for the ledger's reason_head / prompt_head
# summary fields (keeps the JSONL line bounded regardless of prompt size).
_LEDGER_HEAD_CHARS: int = 200

# Staleness threshold: markers older than this (in seconds) are deleted.
_MARKER_STALE_SECONDS: float = 24 * 3600  # 24 hours


def claude_state_dir(create: bool = True) -> Path:
    """Return the Claude state directory, optionally creating it on demand.

    Default resolution: ``~/.claude/state/``.

    Override: set the ``LAZY_STATE_DIR`` environment variable to any absolute
    path — the function will use that directory instead of the default.  This
    env-var override exists for two purposes:
      1. **Hermetic unit tests** (test_lazy_core.py): each test that touches
         the state dir sets ``LAZY_STATE_DIR`` to a ``tempfile.TemporaryDirectory``
         and clears it afterward, so tests never touch ``~/.claude/state/``.
      2. **Hook pipe-tests** (Phase 2): the inject/validate hooks can point at a
         fixture state dir via env var for scriptable, reproducible pipe-test runs
         on both Windows (git-bash) and WSL without affecting the live session.

    Args:
        create: when True (default) create the directory if absent — used by
                write paths (write_run_marker, register_emission, etc.).
                Pass ``create=False`` from read-only paths (read_run_marker,
                _load_registry, lookup_emission, delete_run_marker, etc.) so a
                probe that finds no marker never creates ``~/.claude/state/``
                as a side-effect.  A missing directory on a read path simply
                means "no state" — callers treat a missing path the same as an
                empty result.
    """
    override = os.environ.get("LAZY_STATE_DIR")
    if override:
        d = Path(override)
    else:
        d = Path.home() / ".claude" / "state"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


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
    "queue-missing",           # queue.json absent → cannot continue
    "blocked-halt-for-manual", # script-emitted BLOCKED.md halt
    "needs-research",          # NEEDS_INPUT.md needs-research halt
    "queue-blocked-on-research",  # all queue items need research
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
    }
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


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


def write_cycle_marker(
    feature_id: str,
    nonce: str,
    *,
    kind: str = "real",
    session_id: str | None = None,
    run_started_at: str | None = None,
    begin_head_sha: str | None = None,
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


# ---------------------------------------------------------------------------
# Process-friction detector (hardening-blind-to-process-friction Phase 2 / D1)
#
# The conservative expected-commit budget per dispatched sub_skill. Most cycles
# commit 0–1 times (one atomic gate+commit per plan-part / batch completion);
# anything beyond the budget is "unexpected commits" hardening signal. The budget
# is deliberately generous (defensible default = 1 for every sub_skill) so the
# detector never false-positives on a legitimate single-commit cycle — only a
# genuinely runaway cycle that strings several commits trips D1(b). A sub_skill
# absent from the map falls back to the default. (D1-out: no runtime-death
# heuristic — both signals are deterministic on-disk facts.)
# ---------------------------------------------------------------------------
_CYCLE_COMMIT_BUDGET_DEFAULT = 1
_CYCLE_COMMIT_BUDGET: dict[str, int] = {
    # Multi-batch plan execution may legitimately commit once per batch; allow a
    # slightly higher ceiling so a normal multi-batch /execute-plan cycle is not
    # flagged, while a true runaway (many commits) still trips.
    "execute-plan": 3,
    "retro-feature": 3,
}


def detect_cycle_bracket_friction(
    marker: dict,
    current_run_started_at: str | None,
    current_head_sha: str | None,
    sub_skill: str | None,
    *,
    commits_since: int | None = None,
    now: float | None = None,
) -> dict | None:
    """Detect process-friction at --cycle-end: a torn cycle bracket or unexpected
    commits (hardening-blind-to-process-friction Phase 2, Locked Decision D1).

    Pure function — NO I/O. The caller (--cycle-end) supplies the live values:
    the cycle marker as snapshotted at --cycle-begin, the CURRENT run identity
    and HEAD sha resolved fresh at --cycle-end, the dispatched sub_skill, and the
    number of commits HEAD advanced since ``marker['begin_head_sha']``.

    Two deterministic on-disk signals (D1):
      (a) cycle-bracket-break — the run identity present at --cycle-begin
          (``marker['run_started_at']``) is absent or CHANGED at --cycle-end
          (the dispatched cycle ran --run-end, started a new run, or overwrote the
          run marker). A null begin-snapshot disables this signal (degraded
          --cycle-begin had no run marker to snapshot → no false positive).
      (b) unexpected-commits — HEAD advanced by more than the conservative
          per-sub_skill budget beyond ``marker['begin_head_sha']``. A null
          begin-snapshot or a null/None ``commits_since`` disables this signal.

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

    # --- Signal (b): unexpected-commits -------------------------------------
    # Requires a known begin HEAD snapshot AND a known commit count.
    if begin_head_sha is not None and commits_since is not None:
        budget = _CYCLE_COMMIT_BUDGET.get(
            sub_skill or "", _CYCLE_COMMIT_BUDGET_DEFAULT
        )
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
    root = repo_root or Path.cwd()
    try:
        proc = _git(root, "rev-parse", "HEAD")
        if proc.returncode == 0:
            return (proc.stdout or "").strip() or None
    except Exception:  # noqa: BLE001
        pass
    return None


def cycle_end_friction_check(repo_root: Path | None = None) -> dict | None:
    """--cycle-end I/O wiring (hardening-blind-to-process-friction Phase 2 / D1).

    Called by the ``--cycle-end`` handler in BOTH state machines (lazy-state.py
    and bug-state.py) BEFORE it clears the cycle marker. It:
      1. reads the cycle marker (the --cycle-begin snapshot); a missing/partial
         marker → None no-op (the bracket was never armed or already cleared);
      2. resolves the CURRENT run identity (``read_run_marker().started_at``,
         None when no run marker is live) and the CURRENT HEAD sha;
      3. computes how many commits HEAD advanced since the snapshotted
         ``begin_head_sha`` (``git rev-list --count <begin>..HEAD``);
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
    root = (repo_root or Path.cwd())
    commits_since: int | None = None
    begin_head_sha = marker.get("begin_head_sha")
    current_head_sha = head_sha_snapshot(root)
    if begin_head_sha:
        try:
            count_proc = _git(
                root, "rev-list", "--count", f"{begin_head_sha}..HEAD"
            )
            if count_proc.returncode == 0:
                commits_since = int((count_proc.stdout or "").strip() or "0")
        except Exception:  # noqa: BLE001  (incl. ValueError from int())
            commits_since = None

    # (4) the cycle marker does not carry the dispatched sub_skill name, so the
    # detector uses the conservative DEFAULT commit budget (sub_skill=None). The
    # bracket-break signal — the literal incident (a runaway that ran --run-end) —
    # is sub_skill-independent and fully covered.
    descriptor = detect_cycle_bracket_friction(
        marker,
        current_run_started_at=current_run_started_at,
        current_head_sha=current_head_sha,
        sub_skill=None,
        commits_since=commits_since,
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
# lifecycle / recursive-dispatch deny-set (the agent_id trip in
# lazy-cycle-containment.sh: recursive Agent/Task, nested /lazy-batch, the
# LOOP_FORMATION_FLAGS routing flags, and dev:kill/dev:restart) — they are
# intentionally redundant defense-in-depth. A divergence is a coverage hole. The
# allow-listed ops a legitimately-dispatched subagent needs
# (`--neutralize-sentinel`, `--verify-ledger`) and all read/probe ops are
# deliberately NOT in this set.
# ---------------------------------------------------------------------------

CYCLE_REFUSED_OPS: frozenset[str] = frozenset({
    "--run-end",
    "--run-start",
    "--apply-pseudo",
    "--enqueue-adhoc",
    "--emit-dispatch",
})


def _env_truthy(name: str) -> bool:
    """Return True when env var *name* is set to a non-empty, non-falsey value.

    Treats "", "0", "false", "no", "off" (case-insensitive) as false so a
    deliberately-cleared var doesn't read as set.
    """
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def refuse_if_cycle_active(op_name: str) -> None:
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
    """
    # 1. The main-thread orchestrator asserts its identity → never self-refuse,
    #    even if a stale marker lingers from a crashed prior dispatch.
    if _env_truthy("LAZY_ORCHESTRATOR"):
        return

    # 2/3. Explicit subagent signal, else the marker as the fallback carrier.
    explicit_subagent = _env_truthy("LAZY_CYCLE_SUBAGENT")
    marker = read_cycle_marker()
    if not explicit_subagent and marker is None:
        return

    feature_id = (marker or {}).get("feature_id", "<unknown>")
    sys.stderr.write(
        f"REFUSED: `{op_name}` is an orchestrator-only operation and you are a "
        f"single cycle subagent (the lazy-cycle-active marker is present for "
        f"feature '{feature_id}'). STOP after your commit + push + report — "
        f"routing the next cycle, lifecycle teardown ({op_name}), enqueuing, and "
        f"completion are the orchestrator's job. This op was refused with zero "
        f"side effects.\n"
    )
    sys.exit(3)


# ---------------------------------------------------------------------------
# Prompt-registry API
# ---------------------------------------------------------------------------

def normalize_prompt_for_hash(prompt: str) -> str:
    """Normalize a prompt before hashing so cosmetic copy artifacts cannot defeat
    the registry match while semantic edits still do.

    Five transforms, applied in order (Phase 7 WU-7.3b widened the original
    Phase 1 pair with two more — trailing-whitespace strip + Unicode NFC; leg 5
    added by F2b / lazy-validation-readiness Phase 2):
      1. CRLF (\\r\\n) → LF (\\n)
      2. Lone CR (\\r not followed by \\n) → LF (\\n)
      3. Per-line trailing-whitespace strip (rstrip each line) — a copy/paste
         that picks up trailing spaces or tabs on some lines must not change the
         hash (observed in session 2f6f27dc as a transcription-slip deny source).
      4. Unicode NFC normalization — a decomposed (NFD) variant of an accented
         character (e.g. an editor that emits combining marks) must hash equal to
         the composed (NFC) form.
      5. [F2b / lazy-validation-readiness] Fold Unicode characters the model trivially
         substitutes when retyping a script-emitted prompt:
           - em-dash U+2014, en-dash U+2013, horizontal bar U+2015,
             figure dash U+2012  →  hyphen-minus '-'
           - left single curly quote U+2018, right single curly quote U+2019  →  '
           - left double curly quote U+201C, right double curly quote U+201D  →  "
           - non-breaking space U+00A0, narrow NBSP U+202F  →  regular space
         Applied AFTER NFC so code-point normalization happens first.  These are
         purely cosmetic punctuation/space variants; a genuine word change still
         alters the hash (the fold cannot collapse distinct words).  This makes an
         em-dash/curly-quote/NBSP slip on an otherwise-verbatim emitted prompt
         hash-equal → ALLOW without any guard change.  It also improves the F1b
         auto-readmit near-match (shares this normalize) for free.

    This ensures that a prompt registered on Windows (with CRLF line endings,
    trailing whitespace, or NFD text) produces the same sha256 as the same prompt
    re-typed clean, so Windows/WSL round-trips and editor quirks cannot defeat the
    registry match.  A genuine word change still alters the hash (the deny still
    fires for a real edit).  The SPEC requires CRLF normalization in §Validate-deny
    step 1; WU-7.3b adds the trailing-whitespace + NFC legs; F2b / lazy-validation-
    readiness Phase 2 adds the dash/quote/NBSP folding leg.
    """
    # Step 1: collapse CRLF → LF
    normalized = prompt.replace("\r\n", "\n")
    # Step 2: replace any remaining lone CRs with LF
    normalized = normalized.replace("\r", "\n")
    # Step 3: strip trailing whitespace from each line (newlines preserved).
    # Splitting on "\n" after steps 1+2 means every line boundary is a single LF.
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    # Step 4: Unicode NFC — fold decomposed sequences into their composed form so
    # an NFD copy hashes identically to the clean NFC form.
    normalized = unicodedata.normalize("NFC", normalized)
    # Step 5 (F2b / lazy-validation-readiness): fold cosmetic Unicode punctuation/
    # space substitutes that the model trivially introduces when retyping a prompt.
    # Applied after NFC so we operate on fully-composed code points.
    # Translation table built once (str.translate is O(n) and very fast).
    normalized = normalized.translate(_NORM_FOLD_TABLE)
    return normalized


# F2b (lazy-validation-readiness Phase 2): translation table for leg 5 of
# normalize_prompt_for_hash.  Maps Unicode cosmetic-substitute code points to their
# ASCII equivalents.  Keys are Unicode code-point integers; values are the folded
# strings (str.translate allows multi-char replacements via a mapping str→str on the
# table, but for 1-to-1 folds it is more efficient to map ord→ord or ord→str).
#
# Dashes: em-dash U+2014, en-dash U+2013, horizontal bar U+2015, figure dash U+2012
#         → hyphen-minus U+002D '-'
# Single quotes: U+2018 LEFT SINGLE QUOTATION MARK, U+2019 RIGHT SINGLE QUOTATION MARK
#                → apostrophe U+0027 "'"
# Double quotes: U+201C LEFT DOUBLE QUOTATION MARK, U+201D RIGHT DOUBLE QUOTATION MARK
#                → quotation mark U+0022 '"'
# Spaces: U+00A0 NO-BREAK SPACE, U+202F NARROW NO-BREAK SPACE → U+0020 ' '
_NORM_FOLD_TABLE: dict = str.maketrans(
    {
        0x2014: "-",   # EM DASH
        0x2013: "-",   # EN DASH
        0x2015: "-",   # HORIZONTAL BAR
        0x2012: "-",   # FIGURE DASH
        0x2018: "'",   # LEFT SINGLE QUOTATION MARK
        0x2019: "'",   # RIGHT SINGLE QUOTATION MARK
        0x201C: '"',   # LEFT DOUBLE QUOTATION MARK
        0x201D: '"',   # RIGHT DOUBLE QUOTATION MARK
        0x00A0: " ",   # NO-BREAK SPACE
        0x202F: " ",   # NARROW NO-BREAK SPACE
    }
)


def prompt_sha256(prompt: str) -> str:
    """Return the hex sha256 of a prompt after normalizing line endings.

    Uses normalize_prompt_for_hash() before hashing so CRLF and LF variants
    of the same prompt produce identical digests.
    """
    normalized = normalize_prompt_for_hash(prompt)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_registry() -> dict:
    """Load the prompt registry from disk.  Returns ``{"entries": []}`` on any
    read/parse error (fail-open — the validate hook also fails open separately).

    Corrupt registry → start fresh so a bad write never bricks subsequent
    sessions.  The old file is left in place; the next write (via
    register_emission) will atomically replace it with a clean copy.

    Read-only path: passes ``create=False`` to ``claude_state_dir()`` so a
    registry probe never creates ``~/.claude/state/`` as a side-effect.
    """
    # Read-only — do not create the directory if absent; treat as empty.
    registry_path = claude_state_dir(create=False) / _REGISTRY_FILENAME
    if not registry_path.exists():
        return {"entries": []}
    try:
        raw = registry_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    # Corrupt / wrong shape — start fresh.
    return {"entries": []}


def registry_summary() -> str:
    """Return a short one-line summary of the prompt-registry state.

    Phase 8 WU-8.2: bound into the routed-hardening-debt ``hardening_emit_command``
    as ``--context registry_state=...`` so the dispatched hardening subagent has
    a snapshot of how many emissions are outstanding.  Read-only.

    Returns:
        ``"empty"`` when there are no entries, otherwise
        ``"<N> entries, <M> unconsumed"``.
    """
    entries = _load_registry().get("entries", [])
    if not entries:
        return "empty"
    unconsumed = sum(1 for e in entries if not e.get("consumed", False))
    return f"{len(entries)} entries, {unconsumed} unconsumed"


def consumed_emission_count() -> int:
    """Return the number of CONSUMED registry entries — the dispatch oracle.

    The validate-deny guard calls ``consume_nonce`` on every ALLOW (one consume
    per dispatch), so this monotone-within-the-ring count is a sound "how many
    dispatches have landed" signal.  ``update_repeat_counts`` (F2) reads it twice
    around a re-read: an UNCHANGED consumed-count between two identical step
    probes means NO dispatch happened between them → the second probe is a
    re-read, not a re-attempt → hold the step counter (double-probe debounce).

    Read-only: ``_load_registry`` passes ``create=False`` so a probe never
    creates the state dir as a side-effect, and returns ``{"entries": []}`` (→ 0)
    on any missing / corrupt registry.  The registry ring-cap can evict the
    oldest entries, but the debounce only compares two consecutive probes within
    one run, where eviction of a consumed entry between adjacent probes is not a
    concern (it would only *lower* the count, never spuriously raise it, so it
    can at worst fail-open into an increment — never a spurious hold).

    Returns:
        The count of entries whose ``consumed`` flag is truthy (0 when empty).
    """
    entries = _load_registry().get("entries", [])
    return sum(1 for e in entries if e.get("consumed", False))


def _save_registry(data: dict) -> None:
    """Persist the registry dict to disk atomically."""
    registry_path = claude_state_dir() / _REGISTRY_FILENAME
    _atomic_write(registry_path, json.dumps(data, indent=2) + "\n")


def register_emission(
    prompt: str,
    cls: str,
    item_id: str | None = None,
    now: float | None = None,
) -> dict:
    """Register a prompt emission in the prompt registry.

    Each registration creates one entry in ``lazy-prompt-registry.json`` with:
      - nonce (str): unique uuid4 hex string — single-use control
      - prompt_sha256 (str): sha256 of the normalized prompt
      - prompt_norm (str): the normalize_prompt_for_hash-normalized prompt text.
        Stored verbatim (not just hashed) so the validate-deny guard can do a
        pure trailing-suffix superset match for F1b auto-readmit
        (lazy-pipeline-ergonomics Phase 1).  Registry entries are ephemeral
        (ring-cap + TTL) so storing the text is size-safe.
      - prompt_raw (str): the EXACT original prompt bytes before any normalization.
        F2a (lazy-validation-readiness Phase 3): stored so that
        resolve_emission_by_nonce() can return the EXACT original text for a
        by-reference dispatch — the guard resolves nonce → prompt_raw and returns
        it via hookSpecificOutput.updatedInput, so the spawned subagent receives
        the fully-expanded prompt without any retyping.
      - emitted_at (float): epoch timestamp of the emission
      - class (str): dispatch class tag (e.g. "cycle", "recovery", "hardening")
      - item_id (str|None): the feature/bug id for context (optional)
      - consumed (bool): False until consume_nonce() is called

    Ring cap: when the registry would exceed ``_REGISTRY_RING_CAP`` (64) entries,
    the oldest entry (lowest index, earliest emitted_at) is evicted first.  This
    keeps the registry bounded regardless of run length.

    Args:
        prompt: the dispatch prompt text (normalized before hashing)
        cls: the dispatch class tag (e.g. "cycle")
        item_id: the feature or bug id associated with this dispatch (optional)
        now: epoch float for emitted_at (injectable for hermetic tests;
             defaults to time.time())

    Returns:
        The newly created entry dict.
    """
    if now is None:
        now = time.time()

    entry: dict = {
        "nonce": uuid.uuid4().hex,
        "prompt_sha256": prompt_sha256(prompt),
        # F1b: store the normalized prompt text so the guard can prefix-match a
        # pure trailing suffix (auto-readmit) using identical normalization.
        "prompt_norm": normalize_prompt_for_hash(prompt),
        # F2a (lazy-validation-readiness Phase 3): store the EXACT original bytes
        # so resolve_emission_by_nonce() can return them verbatim for by-reference
        # dispatch — the guard copies prompt_raw into updatedInput.prompt so the
        # spawned subagent receives the fully-expanded original prompt, eliminating
        # the byte-exact-retype requirement for the orchestrator.
        "prompt_raw": prompt,
        "emitted_at": now,
        "class": cls,
        "item_id": item_id,
        "consumed": False,
    }

    data = _load_registry()
    entries: list = data["entries"]
    entries.append(entry)

    # Ring cap: evict the oldest entry (index 0) when over the cap.
    # The list is ordered by insertion time; oldest is always index 0.
    while len(entries) > _REGISTRY_RING_CAP:
        entries.pop(0)

    data["entries"] = entries
    _save_registry(data)
    return entry


def lookup_emission(
    prompt: str,
    now: float | None = None,
) -> dict | None:
    """Look up an unconsumed, fresh registry entry by prompt hash.

    Freshness has two components (belt-and-braces):
      1. Nonce + TTL: entry must be unconsumed AND within
         REGISTRY_ENTRY_TTL_SECONDS (1800 s) of ``emitted_at``.
      2. Run-start gate (when a non-stale run marker exists): additionally
         require ``emitted_at`` >= marker's ``started_at`` epoch — entries
         that were written before the current run started are never
         dispatchable even if they are within the TTL.  When no run marker is
         present this gate is skipped and only nonce+TTL semantics apply.

    Returns the first matching entry, or None when:
      - no entry with this prompt's sha256 exists, OR
      - all matching entries are consumed, beyond the TTL, OR predate the
        current run's started_at.

    Args:
        prompt: the prompt text to look up (normalized before hashing)
        now: epoch float for TTL comparison (injectable; defaults to time.time())

    Returns:
        The matching entry dict, or None.
    """
    if now is None:
        now = time.time()
    target_sha = prompt_sha256(prompt)

    # Compute the run-start epoch once for all entry comparisons.
    # read_run_marker is a read-only path (no mkdir) and returns None when
    # there is no active (or non-stale) run — in that case the freshness gate
    # is skipped and only nonce+TTL semantics apply.
    marker = read_run_marker(now=now)
    run_started_epoch: float | None = None
    if marker is not None:
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(
                started_at_str, "%Y-%m-%dT%H:%M:%SZ"
            )
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            # Unrecognised format — skip the run-start gate for safety.
            run_started_epoch = None

    data = _load_registry()
    for entry in data["entries"]:
        if entry.get("prompt_sha256") != target_sha:
            continue
        if entry.get("consumed", True):
            # Already consumed — not dispatchable.
            continue
        emitted_at = entry.get("emitted_at", 0.0)
        if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
            # Beyond TTL — not dispatchable (re-probe required).
            continue
        if run_started_epoch is not None and emitted_at < run_started_epoch:
            # Entry predates the current run — not dispatchable.  A re-probe
            # (new register_emission call) is required to get a fresh entry.
            continue
        return entry
    return None


def resolve_emission_by_nonce(
    nonce: str,
    *,
    now: float | None = None,
) -> dict | None:
    """Look up a registry entry by nonce and return it ONLY when dispatchable.

    F2a (lazy-validation-readiness Phase 3): the by-reference dispatch path.
    The guard calls this when it receives a ``@@lazy-ref nonce=<hex>`` prompt
    token.  If the nonce resolves to a fresh, unconsumed, run-start-gated entry,
    the guard returns ``permissionDecision: "allow"`` PLUS
    ``hookSpecificOutput.updatedInput`` (with ``prompt = entry["prompt_raw"] or
    entry["prompt_norm"]``), so the spawned subagent receives the fully-expanded
    prompt without any retyping.

    Freshness gates mirror ``lookup_emission`` exactly:
      1. Nonce + TTL: entry must be unconsumed AND within
         REGISTRY_ENTRY_TTL_SECONDS (1800 s) of ``emitted_at``.
      2. Run-start gate (when a non-stale run marker exists): additionally
         require ``emitted_at >= marker.started_at`` epoch — entries predating
         the current run are not dispatchable even if within TTL.

    This function is READ-ONLY and fail-safe: any error → None (fail-open to
    deny, never a spurious allow).  The guard is responsible for consuming the
    nonce after resolving it.

    Args:
        nonce: the nonce hex string from the ``@@lazy-ref`` token.
        now: epoch float for TTL comparison (injectable for hermetic tests;
             defaults to time.time()).

    Returns:
        The matching registry entry dict when dispatchable, or None when:
          - the nonce does not exist in the registry, OR
          - the entry is consumed, OR
          - the entry is beyond TTL, OR
          - the entry predates the current run's started_at.
    """
    if now is None:
        now = time.time()

    try:
        # Compute the run-start epoch gate (mirrors lookup_emission).
        marker = read_run_marker(now=now)
        run_started_epoch: float | None = None
        if marker is not None:
            started_at_str = marker.get("started_at", "")
            try:
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                run_started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
            except (ValueError, TypeError):
                run_started_epoch = None

        data = _load_registry()
        for entry in data["entries"]:
            if entry.get("nonce") != nonce:
                continue
            # Gate 1: must be unconsumed.
            if entry.get("consumed", True):
                return None
            # Gate 2: must be within TTL.
            emitted_at = entry.get("emitted_at", 0.0)
            if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
                return None
            # Gate 3: must not predate the current run (when a marker is present).
            if run_started_epoch is not None and emitted_at < run_started_epoch:
                return None
            # All gates passed — this entry is dispatchable by reference.
            return entry
        # Nonce not found in registry.
        return None
    except Exception:  # noqa: BLE001
        # Fail-safe: any error → None so the guard falls through to deny,
        # never a spurious allow.
        return None


def append_dispatch_by_reference_event(
    *,
    tool_use_id: str,
    nonce: str,
    resolved_sha12: str,
    item_id: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``dispatch_by_reference: true`` audit event to the deny ledger.

    F2a (lazy-validation-readiness Phase 3): every by-reference allow must write
    an auditable record to the same deny ledger (JSONL) used by denies and
    auto-readmits, so the path is retro-gradable and distinguishable from a
    verbatim allow.

    Event shape (mirrors append_auto_readmit_event for reader uniformity):

        {"ts": <epoch float>, "tool_use_id": <str>,
         "dispatch_by_reference": true, "nonce": <hex>,
         "resolved_sha12": <12 hex chars of the resolved prompt's sha256>,
         "item_id": <str|None>, "acked": true}

    ``acked`` is True because a by-reference allow owes NO hardening debt —
    it is a sanctioned dispatch path, not a harness gap.

    Best-effort / fail-open: mirrors the contract of append_auto_readmit_event —
    the caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising.

    Args:
        tool_use_id: the dispatched Agent tool_use_id.
        nonce: the ``@@lazy-ref`` nonce that was resolved.
        resolved_sha12: first 12 hex chars of the resolved prompt's sha256
                        (for retro correlation without storing the full sha).
        item_id: the matched entry's feature/bug id (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        event = {
            "ts": now,
            "tool_use_id": tool_use_id,
            # Discriminator field: retro readers filter on this to see
            # by-reference dispatches separately from verbatim allows and denies.
            "dispatch_by_reference": True,
            "nonce": nonce,
            "resolved_sha12": resolved_sha12,
            "item_id": item_id,
            # Pre-acked: by-reference dispatches owe no hardening debt — they are
            # the SAFE path (bytes come from the registered emission, not from
            # hand-composition), so they must never inflate pending_hardening()
            # or block --run-end.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        # Plain append (same pattern as append_deny_ledger_entry and
        # append_auto_readmit_event): the ledger is append-only and a torn final
        # line is tolerated by the corrupt-line-skipping reader.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate to the guard.
        return False


def consume_nonce(nonce: str, consumer: str | None = None) -> bool:
    """Mark a registry entry's nonce as consumed (one dispatch per emission).

    After consumption, ``lookup_emission`` will no longer return this entry,
    enforcing the single-use constraint: a re-dispatch requires a re-probe,
    which is the continuation-cycles-must-re-emit rule made mechanical.

    Phase 2 extension: when ``consumer`` is provided (non-None), the
    ``consumed_by`` field is written onto the entry.  This enables the
    idempotent re-fire logic in ``lazy_guard.py`` — when the PreToolUse hook
    fires twice for the same denied dispatch (same tool_use_id, E4 spike
    finding), the guard reads ``consumed_by`` and allows the second call if
    the consumer matches.

    Backward compatibility: ``consumer=None`` (the default) preserves Phase 1
    behavior exactly — the entry is consumed but no ``consumed_by`` field is
    written.  All 264 existing test_lazy_core.py tests rely on this.

    Args:
        nonce: the nonce string from a previously registered entry
        consumer: optional string identifying the consumer (e.g. tool_use_id);
                  stored as ``consumed_by`` on the entry when provided.

    Returns:
        True if the nonce was found and consumed; False if not found or already
        consumed.
    """
    data = _load_registry()
    changed = False
    for entry in data["entries"]:
        if entry.get("nonce") == nonce:
            if entry.get("consumed", False):
                # Already consumed — idempotent False.
                return False
            entry["consumed"] = True
            # Phase 2: record the consuming tool_use_id when provided so the
            # guard can distinguish idempotent re-fire (same consumer) from a
            # legitimately distinct second attempt (different consumer → deny).
            if consumer is not None:
                entry["consumed_by"] = consumer
            changed = True
            break
    if not changed:
        return False
    _save_registry(data)
    return True


def register_emission_if_marked(
    prompt: str,
    cls: str,
    item_id: str | None = None,
    now: float | None = None,
) -> dict | None:
    """Register a prompt emission only when a valid run marker is present.

    This is the primary integration point for both state scripts' --emit-prompt
    handling: after computing a cycle_prompt, the script calls this function.
    If no marker is active → no-op (returns None, writes nothing).  This
    ensures default (no-marker) invocations remain byte-identical and the
    registry file is never created by accident.

    SPEC: all new Phase 1 behavior is unreachable without an explicit --run-start
    call (A10: byte-identical default output guarantee).

    Args:
        prompt: the dispatch prompt text
        cls: the dispatch class (e.g. "cycle")
        item_id: the feature or bug id (optional)
        now: epoch float (injectable; defaults to time.time())

    Returns:
        The registry entry dict if a marker is present and the registration
        succeeded; None otherwise (no marker = no write).
    """
    if now is None:
        now = time.time()
    # read_run_marker applies all staleness guards — if it returns None there
    # is no active run and we must not write.
    marker = read_run_marker(now=now)
    if marker is None:
        return None
    return register_emission(prompt, cls=cls, item_id=item_id, now=now)


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
    # guard ALLOW). A legacy marker without the watermark key uses -1 so the first
    # dispatch of the run always advances.
    current_consume = consumed_emission_count()
    prior_consume = marker.get("last_advance_consume_count", 0)
    try:
        prior_consume = int(prior_consume)
    except (TypeError, ValueError):
        prior_consume = 0
    if current_consume <= prior_consume:
        # No dispatch consumed since the last advance — this is a bare probe/inject
        # firing (or a re-read). Do NOT advance, do NOT write. Idempotent across
        # the many inject-hook firings within one cycle.
        return marker

    sub_skill = state.get("sub_skill")
    # Real sub_skill: truthy and does not start with "__"
    if sub_skill and not str(sub_skill).startswith("__"):
        marker["forward_cycles"] = marker.get("forward_cycles", 0) + 1
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


# ---------------------------------------------------------------------------
# Phase 7 WU-7.1 — Deny ledger (routed hardening debt)
# ---------------------------------------------------------------------------
#
# Every guard deny appends one JSON line to lazy-deny-ledger.jsonl (best-effort,
# fail-open — the guard's own writer wraps this in try/except so a ledger failure
# never changes the deny response).  The ledger is the ground truth for "how many
# denials this run still owe a hardening round": --emit-dispatch hardening acks
# the OLDEST unacked entry (FIFO, one per emission), and --run-end refuses to
# retire the marker while unacked entries remain unless --ack-unhardened is passed.
#
# The deny path is the ONLY writer of new entries; allows never write.  Reads and
# acks tolerate a missing or partially-corrupt file: unparseable lines are skipped
# rather than treated as a fatal error (a single bad append must not brick the
# whole ledger).


def append_deny_ledger_entry(
    tool_use_id: str,
    denied_sha12: str,
    reason_head: str,
    prompt_head: str,
    now: float | None = None,
) -> bool:
    """Append one deny entry to the deny ledger (JSONL), best-effort.

    Called by lazy_guard.py on EVERY deny.  The caller wraps this in its own
    try/except so a ledger-write failure never changes the guard's deny output
    or exit code (fail-open is sacred) — this function additionally swallows its
    own write errors and returns False rather than raising, so it is safe to call
    from any context.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "tool_use_id": <str>, "denied_sha12": <12 hex>,
         "reason_head": <≤200 chars>, "prompt_head": <≤200 chars>, "acked": false}

    Args:
        tool_use_id: the denied Agent dispatch's tool_use_id (may be "").
        denied_sha12: the first 12 hex chars of the computed prompt sha256.
        reason_head: the deny reason, truncated to the first ~200 chars.
        prompt_head: the dispatched prompt, truncated to the first ~200 chars.
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "tool_use_id": tool_use_id,
            "denied_sha12": denied_sha12,
            "reason_head": (reason_head or "")[:_LEDGER_HEAD_CHARS],
            "prompt_head": (prompt_head or "")[:_LEDGER_HEAD_CHARS],
            "acked": False,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        # Append a single compact JSON line.  Plain append (not _atomic_write):
        # the ledger is append-only and a torn final line is tolerated by the
        # corrupt-line-skipping reader, so the atomic-rewrite ceremony would only
        # add a read-modify-write race window with the ack path.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def append_friction_ledger_entry(
    reason_head: str,
    detail: str,
    now: float | None = None,
) -> bool:
    """Append one process-friction entry to the SAME deny ledger (JSONL).

    hardening-blind-to-process-friction Phase 2 (D1): when --cycle-end detects a
    torn cycle bracket or unexpected commits, it records the friction as
    hardening debt by appending to ``lazy-deny-ledger.jsonl`` — the SAME file the
    guard's denies use. A ``kind: "process-friction"`` discriminator lets a single
    reader walk denies + friction, while the existing consumers
    (``pending_hardening()`` / ``oldest_unacked_deny()`` / the ``--run-end`` gate /
    the ``--emit-prompt`` probe's withholding) count any unacked entry unchanged —
    so a runaway self-announces as hardening debt with NO new routing machinery.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "kind": "process-friction",
         "reason_head": <≤200 chars — the signal: cycle-bracket-break /
         unexpected-commits>, "detail": <≤200 chars — the human-readable
         specifics>, "acked": false}

    Best-effort / fail-open — identical contract to append_deny_ledger_entry: the
    caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising, so a ledger-write failure never derails the
    --cycle-end marker clear.

    Args:
        reason_head: the friction signal name (e.g. "cycle-bracket-break"),
            truncated to the head-char cap.
        detail: the human-readable specifics of the friction, truncated to the cap.
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "kind": "process-friction",
            "reason_head": (reason_head or "")[:_LEDGER_HEAD_CHARS],
            "detail": (detail or "")[:_LEDGER_HEAD_CHARS],
            "acked": False,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def append_auto_readmit_event(
    tool_use_id: str,
    readmitted_sha12: str,
    suffix_head: str,
    item_id: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``auto_readmit: true`` event to the deny ledger (JSONL).

    F1b (lazy-pipeline-ergonomics Phase 1): when the validate-deny guard
    auto-readmits a pure trailing-suffix superset of a fresh cycle-class entry
    (instead of denying it), it MUST write an auditable record so the readmit is
    never silent — the retro grader reads the same JSONL stream as the denies.

    The event reuses the deny-ledger shape so a single reader walks both denies
    and auto-readmits, distinguished by the ``auto_readmit`` flag:

        {"ts": <epoch float>, "tool_use_id": <str>, "auto_readmit": true,
         "readmitted_sha12": <12 hex of the MATCHED entry>,
         "suffix_head": <≤200 chars of the appended trailing suffix>,
         "item_id": <str|None>, "acked": true}

    ``acked`` is True because an auto-readmit owes NO hardening debt (the dispatch
    was allowed, not denied) — it must never inflate ``pending_hardening()`` or
    block ``--run-end``.

    Best-effort / fail-open: identical contract to append_deny_ledger_entry — the
    caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising.

    Args:
        tool_use_id: the auto-readmitted Agent dispatch's tool_use_id.
        readmitted_sha12: first 12 hex chars of the MATCHED entry's prompt_sha256.
        suffix_head: the appended trailing suffix, truncated to the head-char cap.
        item_id: the matched entry's feature/bug id (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "tool_use_id": tool_use_id,
            "auto_readmit": True,
            "readmitted_sha12": readmitted_sha12,
            "suffix_head": (suffix_head or "")[:_LEDGER_HEAD_CHARS],
            "item_id": item_id,
            # Auto-readmits owe no hardening debt — pre-acked so they never count
            # toward pending_hardening() / --run-end refusal.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def find_auto_readmit_entry(
    prompt: str,
    now: float | None = None,
) -> dict | None:
    """Find an unconsumed, fresh, ``class == "cycle"`` registry entry whose stored
    normalized prompt text is a PURE TRAILING-SUFFIX PREFIX of *prompt*.

    F1b (lazy-pipeline-ergonomics Phase 1): the common validate-deny accident is
    an ORCHESTRATOR NOTE appended to a script-emitted ``cycle_prompt``.  The full
    hash misses (lookup_emission → None), so the guard would deny.  This helper
    lets the guard instead AUTO-READMIT the dispatch when the only difference is a
    trailing suffix appended to a sanctioned cycle prompt.

    Match criteria (ALL must hold):
      - the entry is unconsumed AND within REGISTRY_ENTRY_TTL_SECONDS AND
        (when a run marker exists) emitted at/after the run's started_at — the
        SAME freshness gate as lookup_emission, so a stale entry never readmits;
      - the entry's ``class`` is exactly ``"cycle"`` — NEVER ``"hardening"``
        (the depth-1 cap stays intact) and never any other ad-hoc class;
      - ``dispatched_norm.startswith(entry_norm)`` after identical
        normalize_prompt_for_hash normalization, with a NON-EMPTY remainder
        (a pure suffix superset — an exact equal would have hit lookup_emission,
        and an in-body edit is not a prefix so it never matches).

    Returns the matched entry dict (the FIRST qualifying entry in insertion
    order), or None when nothing qualifies.  Read-only — does NOT consume; the
    caller consumes the nonce on a successful readmit.

    Args:
        prompt: the dispatched prompt text (normalized before comparison).
        now: epoch float for the TTL/run-start gate (injectable for tests).

    Returns:
        The matching entry dict, or None.
    """
    if now is None:
        now = time.time()
    dispatched_norm = normalize_prompt_for_hash(prompt)

    # Compute the run-start epoch the same way lookup_emission does so the
    # freshness gate is identical (entries predating the current run never
    # readmit).
    marker = read_run_marker(now=now)
    run_started_epoch: float | None = None
    if marker is not None:
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(
                started_at_str, "%Y-%m-%dT%H:%M:%SZ"
            )
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            run_started_epoch = None

    for entry in _load_registry()["entries"]:
        # Hard class exclusion FIRST — never readmit anything but a cycle entry.
        if entry.get("class") != "cycle":
            continue
        if entry.get("consumed", True):
            continue
        entry_norm = entry.get("prompt_norm")
        # Legacy entries (registered before F1b) have no prompt_norm — skip them
        # (they can still be denied; auto-readmit just doesn't apply).
        if not isinstance(entry_norm, str) or not entry_norm:
            continue
        emitted_at = entry.get("emitted_at", 0.0)
        if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
            continue
        if run_started_epoch is not None and emitted_at < run_started_epoch:
            continue
        # Pure trailing-suffix superset: the dispatched prompt must START WITH the
        # registered prompt AND add a non-empty trailing remainder.  An exact
        # match (no remainder) would already have hit lookup_emission, and an
        # in-body edit is not a prefix so it never qualifies.
        if dispatched_norm.startswith(entry_norm) and len(dispatched_norm) > len(entry_norm):
            return entry
    return None


def find_transcription_slip_entry(
    prompt: str,
    *,
    now: float | None = None,
    threshold: float = 0.97,
) -> dict | None:
    """F2c (lazy-validation-readiness Phase 2): find a registry entry that the
    dispatched *prompt* is a TRANSCRIPTION SLIP of.

    A transcription slip is an otherwise-faithful reproduction of a script-emitted
    prompt that was mangled by cosmetic editing (e.g. one word retyped, an NBSP
    introduced) in a way that F2b's dash/quote/NBSP folding does NOT cover.  The
    high similarity ratio (>= *threshold*, default 0.97) means the orchestrator was
    clearly trying to dispatch a KNOWN registered prompt — the body is almost
    identical — but the bytes differ just enough to miss the hash gate.

    When this function returns an entry, the corrective action is always:
      re-run the Step 1a probe and dispatch the registered ``cycle_prompt``
      **verbatim or by-reference** — do NOT hand-edit the prompt again.

    A genuinely unregistered / hand-composed prompt has NO close registered entry
    (the difflib ratio is low) and falls through to the existing corrective deny
    with hardening debt (the no-match case returns None, so the caller continues to
    ``_deny_and_ledger``).

    Scope (F2c applies ONLY here):
      - Only applies when a valid run marker is present (this is a marked-run
        concern; if no marker, return None immediately — fail-safe for unmarked
        runs and ``--test`` baselines which must remain byte-identical).
      - Scans only entries emitted in the CURRENT run (emitted_at >= run-start
        epoch from ``read_run_marker``), mirroring ``lookup_emission``'s run-start
        gate, so stale cross-run entries cannot mis-classify a real gap.
      - EXCLUDES ``class == "hardening"`` entries unconditionally — the depth-1
        hardening cap must stay fully intact; a slip against a hardening-class
        entry must still go to ``_deny_and_ledger`` (which writes hardening debt).
      - Uses ``difflib.SequenceMatcher`` against the NFC-normalized text (stored
        as ``prompt_norm`` on the entry; falls back to normalizing a raw prompt
        field if ``prompt_norm`` is missing; skips the entry if neither is
        available).

    FAIL-SAFE / FAIL-OPEN contract:
      - Read-only; does NOT consume any nonce or write any state.
      - Any exception is caught and returns None so the caller falls through to
        the existing deny path — a slip-check error must NEVER turn a deny into
        a spurious allow and must NEVER cause an unhandled exception in the guard.

    Args:
        prompt: the dispatched prompt text (normalized before comparison).
        now: epoch float for the TTL / run-start gate (injectable for tests;
             defaults to time.time()).
        threshold: minimum SequenceMatcher ratio to classify as a slip (default
                   0.97 — very high so only near-verbatim copies qualify).

    Returns:
        The highest-ratio entry whose ratio >= *threshold*, or None.
    """
    # Fail-safe: all errors return None (never raise from a guard sub-path).
    try:
        if now is None:
            now = time.time()

        # Marker-gated: F2c is a marked-run concern.  No marker → not applicable.
        marker = read_run_marker(now=now)
        if marker is None:
            return None

        # Compute the run-start epoch (same logic as lookup_emission).
        run_started_epoch: float | None = None
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            run_started_epoch = None

        # Normalize the dispatched prompt for comparison.
        dispatched_norm = normalize_prompt_for_hash(prompt)

        import difflib as _difflib  # stdlib; imported lazily to keep startup cost low

        best_entry: dict | None = None
        best_ratio: float = 0.0

        for entry in _load_registry().get("entries", []):
            try:
                # Hard class exclusion: never classify a hardening-class entry as a
                # slip — the depth-1 cap must stay intact regardless.
                if entry.get("class") == "hardening":
                    continue

                # Run-start gate: only consider entries from the CURRENT run.
                emitted_at = entry.get("emitted_at", 0.0)
                if run_started_epoch is not None and emitted_at < run_started_epoch:
                    continue

                # TTL gate: entries beyond the TTL window are never candidates.
                if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
                    continue

                # Consumed entries can still be slip candidates — we only want to
                # classify the DENY path (the slip did not get an ALLOW), so the
                # relevant registered entries may or may not be consumed.
                # (If the exact-sha match had succeeded, the guard would already
                # have allowed via lookup_emission or _find_entry_by_sha, so we
                # only reach here when the sha did NOT match.)

                # Retrieve normalized form for comparison.
                entry_norm = entry.get("prompt_norm")
                if not isinstance(entry_norm, str) or not entry_norm:
                    # Legacy entry without prompt_norm — skip (no text to compare).
                    continue

                # SequenceMatcher similarity ratio.
                ratio = _difflib.SequenceMatcher(
                    None, dispatched_norm, entry_norm
                ).ratio()
                if ratio >= threshold and ratio > best_ratio:
                    best_ratio = ratio
                    best_entry = entry
            except Exception:  # noqa: BLE001
                # Skip a single bad entry — don't abort the scan.
                continue

        return best_entry

    except Exception:  # noqa: BLE001
        # Fail-open: any outer exception → return None so the caller falls through
        # to the existing deny path.  Never raise from a guard sub-path.
        return None


def read_deny_ledger() -> list[dict]:
    """Read all deny-ledger entries, skipping any unparseable lines.

    A missing ledger file → empty list (no denials yet).  A corrupt line (e.g.
    a torn final append) is skipped rather than aborting the whole read.

    Returns:
        The list of parsed entry dicts in file (FIFO insertion) order.
    """
    ledger_path = claude_state_dir(create=False) / _DENY_LEDGER_FILENAME
    if not ledger_path.exists():
        return []
    entries: list[dict] = []
    try:
        raw = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # Skip an unparseable line — a single torn append must not brick
            # the whole ledger.
            continue
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


def pending_hardening() -> int:
    """Return the count of unacked deny-ledger entries (the routed hardening debt).

    An entry is "pending" when its ``acked`` field is falsy.  A missing or empty
    ledger → 0.
    """
    return sum(1 for e in read_deny_ledger() if not e.get("acked", False))


def pending_denial_reasons() -> list[str]:
    """Return the ``reason_head`` strings of all unacked deny-ledger entries, in
    FIFO order.  Used to surface ``pending_denials`` in the marker-gated probe
    enrichment so the orchestrator sees WHAT it still owes a hardening round for.
    """
    return [
        e.get("reason_head", "")
        for e in read_deny_ledger()
        if not e.get("acked", False)
    ]


def oldest_unacked_deny() -> dict | None:
    """Return the OLDEST (FIFO) unacked deny-ledger entry, or None when there is
    no pending debt.

    Phase 8 WU-8.2: the probe's routed-hardening-debt override pre-composes a
    ``--emit-dispatch hardening`` command whose ``--context`` bindings are derived
    from this entry (``prompt_head`` → denied_prompt_summary, ``reason_head`` →
    denial_reason).  Read-only — does NOT mutate the ledger (the guard's
    allow-time ack is the only mutator now).
    """
    for entry in read_deny_ledger():
        if not entry.get("acked", False):
            return entry
    return None


def build_hardening_emit_command(
    state_script_name: str,
    *,
    item_id: str,
    oldest_deny: dict | None,
    probe_summary: str,
    registry_summary: str,
    cwd: str,
) -> str:
    """Pre-compose the single-line shell command that dispatches the routed
    hardening debt (Phase 8 WU-8.2).

    The returned string is meant to be pasted verbatim into bash by the
    orchestrator when the probe withholds the forward route over pending
    hardening debt.  Every ``--context`` VALUE is shell-quoted via ``shlex.quote``
    (POSIX single-quote escaping) so embedded spaces, quotes, and newlines round-
    trip safely regardless of the host platform — the command targets ``bash`` /
    ``python3`` on the operator's machine, not the Windows host that emits it.

    Args:
        state_script_name: ``"lazy-state.py"`` or ``"bug-state.py"`` — the script
            whose ``--emit-dispatch hardening`` retires this debt.
        item_id: the current feature/bug id (becomes ``--context item_id=...``).
        oldest_deny: the oldest unacked deny-ledger entry (from
            ``oldest_unacked_deny()``), or None.  Its ``prompt_head`` /
            ``reason_head`` bind denied_prompt_summary / denial_reason; absent →
            empty strings.
        probe_summary: a compact one-line summary of the withholding probe.
        registry_summary: a short registry-state summary (e.g. "N entries, M
            unconsumed" or "empty").
        cwd: the repo root the dispatch should run against.

    Returns:
        A single shell command string, safe to paste into bash.
    """
    def _ctx(key: str, value: str) -> str:
        # shlex.quote escapes the VALUE only; the key=value join stays literal.
        return f"--context {key}={shlex.quote(value)}"

    entry = oldest_deny or {}

    # hardening-blind-to-process-friction Phase 2: a process-friction entry
    # (kind: "process-friction", from a torn cycle bracket / unexpected commits)
    # binds trigger_kind=process-friction and surfaces the friction reason+detail
    # instead of the deny-specific denied_prompt_summary/denial_reason.
    if entry.get("kind") == "process-friction":
        friction_reason = entry.get("reason_head", "") or ""
        friction_detail = entry.get("detail", "") or ""
        parts = [
            f"python3 ~/.claude/scripts/{state_script_name}",
            "--emit-dispatch hardening",
            _ctx("trigger_kind", "process-friction"),
            _ctx("item_id", item_id or ""),
            _ctx("friction_reason", friction_reason),
            _ctx("friction_detail", friction_detail),
            _ctx("probe_json", probe_summary),
            _ctx("registry_state", registry_summary),
            _ctx("cwd", cwd or ""),
        ]
        return " ".join(parts)

    denied_prompt_summary = entry.get("prompt_head", "") or ""
    denial_reason = entry.get("reason_head", "") or ""

    parts = [
        f"python3 ~/.claude/scripts/{state_script_name}",
        "--emit-dispatch hardening",
        _ctx("trigger_kind", "validate-deny"),
        _ctx("item_id", item_id or ""),
        _ctx("denied_prompt_summary", denied_prompt_summary),
        _ctx("denial_reason", denial_reason),
        _ctx("probe_json", probe_summary),
        _ctx("registry_state", registry_summary),
        _ctx("cwd", cwd or ""),
    ]
    return " ".join(parts)


def ack_oldest_deny(now: float | None = None) -> dict | None:
    """Ack the OLDEST unacked deny-ledger entry (FIFO), rewriting the ledger.

    Called once per successful ``--emit-dispatch hardening`` emission so the
    one-dispatch-per-deny cadence (locked decision 4) is preserved: each hardening
    dispatch retires exactly one unit of routed hardening debt.

    The oldest unacked entry's ``acked`` flips to True and gains an ``acked_ts``.
    The whole ledger is then rewritten atomically (the file is small — one line
    per deny, bounded by run length).

    Args:
        now: epoch float for acked_ts (injectable for hermetic tests).

    Returns:
        The entry dict that was acked, or None when there were no pending
        entries (no-op — not an error).
    """
    if now is None:
        now = time.time()
    entries = read_deny_ledger()
    target: dict | None = None
    for entry in entries:
        if not entry.get("acked", False):
            entry["acked"] = True
            entry["acked_ts"] = now
            target = entry
            break
    if target is None:
        # Nothing pending — no-op, no rewrite.
        return None
    # Rewrite the whole ledger (one JSON object per line) atomically.
    try:
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        body = "".join(json.dumps(e) + "\n" for e in entries)
        _atomic_write(ledger_path, body)
    except Exception:  # noqa: BLE001
        # A rewrite failure leaves the on-disk ledger unchanged; report the ack
        # as not-applied so callers do not over-count.  The next emission retries.
        return None
    return target


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
) -> dict:
    """Write lazy-run-checkpoint.json to the state dir (checkpoint run-end).

    Args:
        next_route: the probed next route the resumed run should take.
        counters: the marker's fold counters as folded at run end (e.g.
                  {"forward_cycles": N, "meta_cycles": M, "max_cycles": K}).
        now: epoch float for the ts field (injectable for hermetic tests).

    Returns:
        The checkpoint dict that was written.
    """
    if now is None:
        now = time.time()
    checkpoint = {
        "reason": "checkpoint",
        "next_route": next_route,
        "counters": counters,
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
    """Restore a resumed run's monotonic cycle counters from its checkpoint.

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

    Intended semantics (resume-continues-counts): a checkpoint resume is the SAME
    logical run continuing after a sanctioned pause, so the resumed marker must
    CARRY FORWARD the paused counts. This helper reads the just-written marker,
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
        no checkpoint, no active marker, or no usable counters (no-op).
    """
    if not isinstance(checkpoint, dict):
        return None
    counters = checkpoint.get("counters")
    if not isinstance(counters, dict):
        return None
    marker = read_run_marker()
    if marker is None:
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

    marker["forward_cycles"] = _coerce(counters.get("forward_cycles"))
    marker["meta_cycles"] = _coerce(counters.get("meta_cycles"))
    # Registry is freshly cleared on this run-start → the consume watermark must
    # start at 0 so the first real post-resume dispatch advances (see docstring).
    marker["last_advance_consume_count"] = 0
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker
