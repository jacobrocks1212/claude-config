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
import subprocess
import sys
import tempfile
import time
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


def skip_waiver_refusal(meta: dict[str, Any] | None) -> str | None:
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
    # Sort by lowest declared phase, then plan name. Plans without phases:
    # fall to (sys.maxsize, name) so they sort after phase-tagged plans —
    # preserves a sensible order for single-plan features while letting
    # multi-plan features pick the earliest phase first.
    plans.sort(key=_plan_lowest_phase)
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
# three leading hashes, then the literal word "Phase" on a word boundary). This
# mirrors the AlgoBooth repo checker's PHASE_HEADER_RE so lazy_core's notion of
# "a phase" stays equivalent to check-docs-consistency.ts.
_PHASE_HEADING_RE = re.compile(r"^#{2,3}\s+Phase\b")

# A per-phase / top-level bold status line: ``**Status:** <value>``.
_BOLD_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$")


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
        # Checkbox accounting (fence-aware — fenced rows already skipped above).
        if re.match(r"^-\s*\[\s*\]", stripped):
            current["unchecked"] += 1
        elif re.match(r"^-\s*\[[xX]\]", stripped):
            current["checked"] += 1
    return phases


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

def verify_ledger(repo_root: Path, spec_path: Path) -> dict:
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

    4. ``deliverables_done`` — ``spec_path/PHASES.md`` exists and has zero real
       (non-verification) unchecked deliverables. "Real" is defined by
       ``remaining_unchecked_are_verification_only``: rows under a
       "Runtime Verification / MCP Integration Test" subsection heading are
       exempt workstation-only checks. Uses ``count_deliverables`` to detect
       zero-unchecked, and falls back to ``remaining_unchecked_are_verification_only``
       for the exemption. If PHASES.md does not exist, returns False (no evidence
       that implementation phases were ever completed).

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

    # --- check 3: all implementation plans are Complete ---
    # _has_any_complete_plan: at least one plan has status: Complete.
    # find_implementation_plans: returns only non-Complete plans (filters out Complete).
    # Together: any_complete AND no_incomplete → all plans are Complete (and ≥1 exists).
    any_complete = _has_any_complete_plan(spec_path)
    incomplete_plans = find_implementation_plans(spec_path)
    plan_complete = any_complete and len(incomplete_plans) == 0

    # --- check 4: no real (non-verification) unchecked deliverables ---
    phases_file = spec_path / "PHASES.md"
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
    }


# ---------------------------------------------------------------------------
# Pseudo-skill dispatcher — deterministic sentinel / receipt writes
# ---------------------------------------------------------------------------

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

    Parameters
    ----------
    repo_root:
        Root of the repository.  Used only by ``__flip_plan_complete_*`` when
        building the relative path returned in ``wrote``.
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
        Gate: ``spec_path/MCP_TEST_RESULTS.md`` must exist and parse a
        ``scenarios`` list.  Writes VALIDATED.md copying ``mcp_scenarios`` from
        the results file.  Idempotent on existing VALIDATED.md with
        kind=="validated".

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
        # must NOT vacuously validate.
        _waiver_refusal = skip_waiver_refusal(skip_meta)
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
        # Gate: MCP_TEST_RESULTS.md must exist and parse a scenarios list.
        results_path = spec_path / "MCP_TEST_RESULTS.md"
        results_meta = parse_sentinel(results_path)
        if results_meta is None or not isinstance(results_meta.get("scenarios"), list):
            return _refused("MCP_TEST_RESULTS.md absent or missing scenarios list")
        scenarios = results_meta["scenarios"]
        # Idempotency: if VALIDATED.md already exists as kind=validated → noop.
        validated_path = spec_path / "VALIDATED.md"
        existing = parse_sentinel(validated_path)
        if existing is not None and existing.get("kind") == "validated":
            return _noop()
        # Emit mcp_scenarios with yaml.safe_dump so that scenario strings
        # containing ":", ",", or "]" are properly quoted and round-trip
        # through parse_sentinel back to the original Python list unchanged.
        # yaml.safe_dump with default_flow_style=True produces a compact
        # flow-sequence like ['audio: no dropout', 'load, stress'].
        # .strip() removes the trailing newline that safe_dump appends.
        scenarios_inline = yaml.safe_dump(scenarios, default_flow_style=True).strip()
        content = (
            "---\n"
            "kind: validated\n"
            f"feature_id: {feature_id}\n"
            f"date: {date}\n"
            f"mcp_scenarios: {scenarios_inline}\n"
            "result: all-passing\n"
            "---\n"
            "\n"
            "# Validated\n"
            "\n"
            "Validated from MCP_TEST_RESULTS.md — scenarios copied from results file "
            "by apply_pseudo.\n"
        )
        _atomic_write(validated_path, content)
        return _ok(["VALIDATED.md"])

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

def update_repeat_count(
    repo_root: Path,
    state: dict,
    *,
    signature_path: Path | None = None,
    pipeline: str = "feature",
) -> int:
    """Persist the current probe signature and return the consecutive-repeat count.

    The «signature» is the 4-tuple
        (feature_id, sub_skill, sub_skill_args, current_step)
    extracted with ``.get()`` so that missing keys produce ``None`` components
    (an all-None signature is stable and valid).

    Each call:
    1. Derives or accepts a ``signature_path`` for the persisted JSON file.
    2. Reads the existing JSON (shape ``{"signature": [...], "count": int}``).
       Any missing file, OS error, or corrupt/invalid JSON is silently treated
       as «no prior» — the function never raises on a bad state file.
    3. Compares the stored signature (a list) to the new signature (a tuple).
       JSON has no tuple type, so comparison is list-vs-list after converting
       the new tuple to a list.
    4. If the signatures match → increments count; otherwise resets to 1.
    5. Atomically persists the new ``{"signature": ..., "count": count}`` JSON
       back to ``signature_path`` so the next call can read it.
    6. Returns the (int >= 1) count.

    Default ``signature_path`` (when None):
        feature pipeline: ``<tempdir>/lazy-state-last-<sha1_of_repo_root[:16]>.json``
        bug pipeline:     ``<tempdir>/bug-state-last-<sha1_of_repo_root[:16]>.json``
    This keeps the state file outside the repo tree — it is never committed
    and never triggers gitignore concerns. The per-``pipeline`` filename keeps
    the feature and bug resolvers from sharing one signature file: the operator
    runs /lazy-batch and /lazy-bug-batch in parallel sessions against the same
    repo, and interleaved probes through a shared file would reset each other's
    repeat streaks, silently defeating mechanical loop detection.
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

    # --- Build the new signature from the current state ----------------------
    new_sig = (
        state.get("feature_id"),
        state.get("sub_skill"),
        state.get("sub_skill_args"),
        state.get("current_step"),
    )

    # --- Read the persisted prior signature (fail-safe) ----------------------
    prior_count = 0
    prior_sig_list: list | None = None
    try:
        raw = signature_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Validate expected shape: {"signature": [4 items], "count": int}
        if (
            isinstance(data, dict)
            and isinstance(data.get("signature"), list)
            and len(data["signature"]) == 4
            and isinstance(data.get("count"), int)
        ):
            prior_sig_list = data["signature"]
            prior_count = data["count"]
        # If shape is wrong, treat as no-prior (prior_count stays 0, prior_sig_list stays None).
    except (OSError, ValueError, json.JSONDecodeError):
        # File absent, unreadable, or corrupt → treat as no prior.
        pass

    # --- Compute new count ---------------------------------------------------
    # JSON round-trips tuples as lists, so compare new_sig as a list.
    if prior_sig_list is not None and list(new_sig) == prior_sig_list:
        # Same signature as last time — consecutive repeat.
        count = prior_count + 1
    else:
        # Changed signature (or no prior) — reset streak.
        count = 1

    # --- Persist the updated record ------------------------------------------
    payload = json.dumps({"signature": list(new_sig), "count": count})
    _atomic_write(signature_path, payload)

    return count


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

        ### Cycle fwd {fwd}/{max} · meta {meta}/{double} · {feature} · {sub_skill}

    Counter rendering:
    - ``{fwd}``    = ``forward_cycles`` if not None else ``?``
    - ``{max}``    = ``max_cycles`` if not None else ``?``
    - ``{meta}``   = ``meta_cycles`` if not None else ``?``
    - ``{double}`` = ``2 * max_cycles`` if ``max_cycles is not None`` else ``?``
      (the orchestrator's total meta-cycle budget is double the forward-cycle
      ceiling — computed here, not supplied by the caller)

    State field rendering:
    - ``{feature}``   = ``state.get("feature_id")`` if truthy else ``—`` (U+2014)
    - ``{sub_skill}`` = ``state.get("sub_skill")``  if truthy else ``—`` (U+2014)
    """
    # Render each counter: use the value when supplied, else the '?' placeholder.
    fwd_str = str(forward_cycles) if forward_cycles is not None else "?"
    max_str = str(max_cycles) if max_cycles is not None else "?"
    meta_str = str(meta_cycles) if meta_cycles is not None else "?"
    # double is derived from max_cycles — the meta-cycle budget is 2× the
    # forward-cycle ceiling.  Fall back to '?' when max is unknown.
    double_str = str(2 * max_cycles) if max_cycles is not None else "?"

    # Render state fields: use the value when truthy, else the em-dash sentinel.
    feature_str = state.get("feature_id") or "—"
    sub_skill_str = state.get("sub_skill") or "—"

    return (
        f"### Cycle fwd {fwd_str}/{max_str}"
        f" · meta {meta_str}/{double_str}"
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

# Residue regex: any `{lower_snake}` token surviving the bind is an unbound
# token the emitter REFUSES on (never emits a half-bound prompt).
_PROMPT_RESIDUE_RE = re.compile(r"\{[a-z_]+\}")


def _default_cycle_template_dir() -> Path:
    """Resolve the default cycle-prompt template dir from this module's path."""
    return Path(__file__).resolve().parent.parent.joinpath(*_CYCLE_TEMPLATE_DIRNAME)


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

    # --- Token bindings (per-pipeline + per-state) ----------------------------
    is_bug = pipeline == "bug"
    bindings = {
        "item_label": "Bug" if is_bug else "Feature",
        "pipeline_phrase": "bug pipeline" if is_bug else "feature pipeline",
        "item_name": state.get("feature_name") or "",
        "item_id": state.get("feature_id") or "",
        "cwd": str(repo_root),
        "current_step": state.get("current_step") or "",
        "sub_skill": sub_skill,
        # sub_skill_args binds to "" when None so the prompt never shows "None".
        "sub_skill_args": state.get("sub_skill_args") or "",
        "spec_path": state.get("spec_path") or "",
        "work_branch": _emit_work_branch(repo_root),
        "receipt_name": "FIXED.md" if is_bug else "COMPLETED.md",
        "mark_pseudo": "__mark_fixed__" if is_bug else "__mark_complete__",
        "forbidden_status": "Fixed or Won't-fix" if is_bug else "Complete",
        # untestability_reason is only present in the no-runtime mcp-test section;
        # bind it whenever a reason was derived (fallback applies otherwise).
        "untestability_reason": untestability_reason
        or "the plan declares no MCP-reachable surface",
    }

    prompt = "\n\n".join(selected)

    # --- Loop block: appended when the same signature repeated (>= 2) ---------
    # The loop block lives in loop-block.md inside a ``` fence; strip the fence
    # lines and bind its tokens. Model flips to sonnet when the block is added.
    model = "opus"
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
        # De-duplicate while preserving first-seen order for a stable message.
        seen: list[str] = []
        for tok in residue:
            if tok not in seen:
                seen.append(tok)
        return {"ok": False, "refused": "unbound tokens: " + ", ".join(seen)}

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
