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

import json
import os
import re
import sys
import tempfile
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
    """True iff a durable completion receipt exists in the feature/bug dir.

    The receipt is written ONLY by ``__mark_complete__``'s completion-integrity
    gate (or backfilled with ``provenance: backfilled-unverified``). Its presence
    is the structural proof that a feature reached ``Complete`` THROUGH the
    pipeline gate rather than via an out-of-band SPEC/ROADMAP edit. See
    _components/completion-integrity-gate.md.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    Default receipt filename is ``COMPLETED.md`` — matches current behavior.
    Bug-state.py passes ``filename="FIXED.md"`` for the bug receipt convention.
    """
    return spec_path is not None and (spec_path / filename).exists()


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
    for line in phases_text.splitlines():
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
    """Return (unchecked, checked) counts of '- [ ]' / '- [x]' lines."""
    unchecked = 0
    checked = 0
    for line in phases_text.splitlines():
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
    for line in phases_text.splitlines():
        stripped = line.strip()
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
                in_verification = bool(_VERIFICATION_SECTION_RE.search(bold_text))
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
