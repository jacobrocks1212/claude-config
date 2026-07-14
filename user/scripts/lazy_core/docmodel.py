"""lazy_core.docmodel — the read-path document-parsing plane.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 2, Batch 2, WU-2) — a move-only refactor with zero behavior change. Owns
sentinel-file frontmatter parsing, the SKIP/app-surface waiver predicates,
SPEC.md status reads, plan-file frontmatter/analysis, and PHASES.md structural
analysis (checkbox/deliverable counting, verification-only-row detection,
phase parsing).

HARD EXCLUSION (SPEC D2 Constraint 3 ordering): the write-path receipt
functions ``has_completion_receipt`` / ``write_completed_receipt`` are NOT
here — they stay in ``_monolith.py`` (this module was sliced AROUND them).

``_die`` is shared kernel-ish infrastructure that stays in ``_monolith.py``;
``parse_sentinel`` reaches it via a function-local deferred import (this
module must not import ``_monolith`` at top level — that would be circular,
since ``_monolith`` imports FROM this module for the names below).
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys

import yaml

from pathlib import Path
from typing import Any

from ._ctx import _atomic_write, _diag


# ---------------------------------------------------------------------------
# Sentinel parsing (per _components/sentinel-frontmatter.md)
# ---------------------------------------------------------------------------

_FENCE = "---"


# A flat top-level `key: value` frontmatter line (no leading indentation).
# Group 1 = key, group 2 = the value (everything after the first colon+space).
_FLAT_SCALAR_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+):[ \t]+(.*)$")


def _yaml_load_tolerant(yaml_body: str) -> dict[str, Any] | None:
    """Rescue an unquoted colon-space (or trailing-colon) scalar VALUE.

    Called ONLY on the `yaml.YAMLError` path of parse_sentinel (well-formed
    frontmatter never reaches here — it parsed strictly). Operates per-line: for
    each flat top-level ``key: value`` line whose value is a plain (unquoted, non
    flow-collection, non block-scalar) scalar, single-quote the value so an
    embedded ``: `` / trailing ``:`` is read as a literal instead of a nested
    mapping. Re-invokes ``yaml.safe_load``; returns the dict on success or None
    (caller then falls through to the original ``_die`` — genuinely-malformed
    frontmatter, e.g. a broken indented block or an unclosed flow collection, is
    NOT rescued and still hard-halts). Strict schema semantics for keys/kinds are
    preserved: only VALUES are quoted, never keys or structure.
    """
    out_lines: list[str] = []
    for line in yaml_body.splitlines():
        m = _FLAT_SCALAR_LINE_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        key, value = m.group(1), m.group(2).rstrip()
        # Leave values that are empty (null), already quoted, a flow collection,
        # a block-scalar indicator, or an anchor/alias/tag — quoting those would
        # change meaning or is unnecessary.
        if not value or value[0] in ("'", '"', "[", "{", "|", ">", "&", "*", "!", "#"):
            out_lines.append(line)
            continue
        escaped = value.replace("'", "''")
        out_lines.append(f"{key}: '{escaped}'")
    rescued = "\n".join(out_lines)
    try:
        data = yaml.safe_load(rescued)
    except yaml.YAMLError:
        return None
    if isinstance(data, dict):
        return data
    return None


def _yaml_fallback_scalar(value: Any) -> str:
    """Render a scalar VALUE for the no-PyYAML manual frontmatter fallback.

    The state scripts' ``_write_yaml_sentinel`` ImportError fallback emits
    ``f"{k}: {v}"`` pairs by hand (used only when PyYAML is unavailable). A raw
    ``str(value)`` for a value carrying a colon-space (``a: b``) or a trailing
    colon (``waiting on:``) is INVALID YAML — the sentinel would then hard-halt
    ``parse_sentinel`` on re-read. This quotes exactly those two cases (parity
    with what ``yaml.safe_dump`` emits), single-quoting the value and doubling
    any embedded single quote. A colon-free string, a colon-WITHOUT-space string
    (``build:step`` — a valid plain scalar), and non-string values are rendered
    unchanged (``str(value)``), so the common-case output is byte-identical to
    before (skip-mcp-test-frontmatter-unquoted-colon — quote-on-write).
    """
    if isinstance(value, str) and (": " in value or value.endswith(":")):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def parse_sentinel(path: Path) -> dict[str, Any] | None:
    """Parse a sentinel file's YAML frontmatter. Returns dict or None if absent."""
    from ._ctx import _die  # deferred kernel import (kept function-local — hot parse path)
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
        # Tolerant re-parse: an unquoted colon-space (or trailing-colon) in a
        # flat scalar value is quoted on-read and re-loaded. Only rescues that
        # narrow case; genuinely-malformed frontmatter still falls through to
        # _die below (skip-mcp-test-frontmatter-unquoted-colon).
        rescued = _yaml_load_tolerant(yaml_body)
        if rescued is not None:
            return rescued
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


def repo_uses_cognito_planner(repo_root: Path) -> bool:
    """True iff ``repo_root`` ships the repo-scoped ``write-plan-cognito`` planner.

    The Cognito Forms repo installs a repo-scoped lane planner at
    ``.claude/skills/write-plan-cognito/`` (the renamed-from-``write-plan``
    variant). Its presence is the deterministic signal that pipeline dispatch
    should emit ``write-plan-cognito`` for this repo rather than the generic
    ``write-plan``. Keying off the installed skill — not a hardcoded repo name
    or worktree path — keeps the discriminator aligned with the rename and
    survives additional worktrees. Conservative: an unreadable repo root or a
    missing skill dir → False, so non-Cognito repos keep the generic planner.
    """
    try:
        return (repo_root / ".claude" / "skills" / "write-plan-cognito").is_dir()
    except OSError:
        return False


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

# park-provisional-acceptance: the filename state a provisionally-accepted
# NEEDS_INPUT.md is renamed to by provisionalize_sentinel(). It stays
# `kind: needs-input` in frontmatter — the FILENAME is the state carrier
# (same convention as the `_RESOLVED_` rename; kind-flips are the documented
# anti-pattern). Park-mode probes treat the file as workable; non-park probes
# halt on `needs-ratification`; the completion pseudo-skills refuse while it
# exists (the triple-layer backstop, SPEC D6).
PROVISIONAL_SENTINEL = "NEEDS_INPUT_PROVISIONAL.md"

# The closed divergence-grade vocabulary (SPEC D3). File-level = the MOST
# SEVERE grade across the file's decisions. Only these two low grades are
# provisional-eligible; `structural`, unknown values, and ABSENT grades all
# fail closed (park for the operator).
_PROVISIONAL_ELIGIBLE_GRADES = frozenset({"isolated", "contained"})


def build_parked_entry(item_id: str, sentinel_path: Path) -> dict[str, Any]:
    """Build a parked-entry record for use in the ``parked[]`` output array.

    Called by lazy-state.py and bug-state.py when park mode
    (``--park-needs-input`` and/or ``--park-blocked``) is active and a queue
    entry carries an unresolved NEEDS_INPUT.md or a feature/bug-local BLOCKED.md.
    The returned dict is appended to the module-level ``_PARKED`` list in each
    script so the orchestrator can surface every parked item without halting.

    Contract (locked by WU-1 Phase 4 + park-mode-halts-on-blocked Phase 3 tests
    in test_lazy_core.py):
      - ``"id"``             → ``item_id`` (str), unchanged.
      - ``"sentinel"``       → ``str(sentinel_path)``.
      - ``"decision_count"`` → ``len(decisions)`` where ``decisions`` is the
                               ``decisions:`` YAML list in the NEEDS_INPUT.md
                               frontmatter; **0** if absent, empty, or not a list
                               (a BLOCKED.md has no ``decisions:`` list → 0).
      - ``"parked_since"``   → the ``date:`` frontmatter value (str), or
                               ``None`` if absent.
      - ``"sentinel_kind"``  → derived from ``sentinel_path.name``:
                               ``"blocked"`` for ``BLOCKED.md``,
                               ``"needs-input"`` for ``NEEDS_INPUT.md``,
                               else ``"unknown"`` (defensive — never raises).
                               Lets the flush distinguish a blocked-parked item
                               from a needs-input one without filesystem
                               inspection (SPEC D4).

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
    # sentinel_kind: derive from the sentinel filename (additive, never raises).
    name = sentinel_path.name
    if name == "BLOCKED.md":
        sentinel_kind = "blocked"
    elif name == "NEEDS_INPUT.md":
        sentinel_kind = "needs-input"
    elif name == PROVISIONAL_SENTINEL:
        # park-provisional-acceptance: an auto-accepted-on-recommendation
        # sentinel awaiting operator ratification (Step-10 park + flush
        # ratification branch key on this kind).
        sentinel_kind = "provisional"
    else:
        sentinel_kind = "unknown"
    return {
        "id": item_id,
        "sentinel": str(sentinel_path),
        "decision_count": decision_count,
        "parked_since": parked_since,
        "sentinel_kind": sentinel_kind,
    }

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


def _all_wus_in_plan_scope(phases_text: str, phase_set: set[int]) -> list[str]:
    """Return ALL deliverable label strings — checked ([x]) AND unchecked ([ ]) —
    in PHASES.md scoped to the plan's phases.

    Companion to ``_unchecked_wus_in_plan_scope()``. The stale-plan gate uses the
    TOTAL row count to disambiguate the two cases that an empty
    ``_unchecked_wus_in_plan_scope()`` result conflates:

      (a) every referenced WU is already ``[x]``  -> unchecked empty, TOTAL non-empty
          -> the plan is genuinely stale (work done, frontmatter never flipped).
      (b) the plan's ``phases:`` scope resolves to ZERO rows  -> unchecked empty AND
          TOTAL empty -> the scope is UNDEFINED in PHASES.md (e.g. a ``phases: [0]``
          decomposition part with no matching ``### Phase 0`` section — write-plan
          emits these for touchpoint-audit ``block`` verdicts and tracks the
          decomposition WUs in the PLAN BODY, not a PHASES Phase 0). This is NOT a
          "work done" signal; declaring it stale would vacuously flip the plan
          Complete and silently drop the work. The gate must fall through (to the
          plan's own per-WU checkboxes, then to /execute-plan) instead.

    Same fence/heading/``## `` reset walk as ``_unchecked_wus_in_plan_scope()`` — only
    the checkbox-mark class differs (``[ xX]`` here vs. unchecked-only there).
    """
    current_phase: int | None = None
    out: list[str] = []
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
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
        m = re.match(r"^\s*-\s*\[\s*[xX]?\s*\]\s*(.+?)\s*$", line)
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


def _implementation_plans_exist(spec_dir: Path) -> bool:
    """Return True iff at least one IMPLEMENTATION plan file exists on disk,
    regardless of its frontmatter status (Ready / In-progress / Complete / none).

    "Implementation plan" excludes ``realign-*.md`` / ``retro-*.md`` (mirrors the
    filter in ``find_implementation_plans``) and the legacy ``PLAN.md``. Used by
    ``verify_ledger`` (harness-hardening-retro-fixes Phase 3) to distinguish
    *absent-by-design* (a plan-less / realign-only feature — no implementation
    plan, none required → ``plan_complete`` is True) from *incomplete* (an
    implementation plan exists but is not Complete → ``plan_complete`` stays
    False). Unlike ``find_implementation_plans``, this does NOT filter out
    Complete plans — it answers the pure existence question.
    """
    plans_dir = spec_dir / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            name = p.name
            if name.startswith("retro-") or name.startswith("realign-"):
                continue
            return True
    legacy = spec_dir / "PLAN.md"
    if legacy.exists():
        return True
    return False


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
#
# CANONICAL VERIFICATION-SUBSECTION HEADER SET (the source of truth this regex
# must stay in lockstep with). Every header below is authored by a /spec-phases
# or /blocked-resolution component, nests gate-owned (`/mcp-test`) unchecked
# rows, and must be recognized as a verification boundary — otherwise its only
# unchecked rows read as plannable implementation work and Step 7a loops on
# write-plan forever even though every implementation plan part is Complete. The
# whole family is gate-owned re-probe / certification work, NOT /write-plan or
# /execute-plan deliverables. Two consecutive single-phrase gaps in one run
# (`reachability smoke` Round 24 / d8d02ef, then `full-chain seam audit` this
# round) motivated enumerating the FULL convention set here rather than patching
# one phrase per incident:
#
#   1. "Runtime Verification"          — _components/phases-runtime-verification.md
#                                         (the canonical nesting heading/bold marker).
#   2. "MCP Integration Test" /
#      "MCP (test )?assertion(s)"      — same component (gate assertion subsection).
#   3. "Reachability smoke"            — same component: every phase introducing a
#                                         new user-facing API surface carries one
#                                         in-phase reachability-smoke row (a single
#                                         live MCP call proving the surface is
#                                         callable end-to-end), often emitted as its
#                                         own sibling bold header
#                                         ``**Reachability smoke (...):**``.
#   4. "Full-chain seam audit" /
#      "seam audit" /
#      "seam re-validation"            — _components/blocked-resolution.md step 1a/6
#                                         + phases-runtime-verification.md: the
#                                         retry_count>=2 escalation convention. A
#                                         corrective phase at escalation MUST carry a
#                                         full-chain seam-audit deliverable —
#                                         enumerate every boundary in the failing
#                                         path and live-probe each seam post-fix to
#                                         the final observable BEFORE full
#                                         re-validation. Those rows (plus the
#                                         certifying ``Workstation: /mcp-test ...
#                                         passes`` row) are all live-MCP re-probe
#                                         assertions owned by /mcp-test, so the
#                                         ``**Full-chain seam audit (HARD — retry_count
#                                         >= 2 escalation ...):**`` sibling header is
#                                         a verification boundary. (Live no-progress
#                                         loop: d8-session-format Phase 9, 2026-06-16
#                                         hardening round.)
#
# When a NEW verification/escalation subsection convention is added to either
# component, add it here AND add a regression fixture to test_lazy_core.py — do
# NOT wait for it to manifest as a production no-progress loop.
# ---------------------------------------------------------------------------
# Verification-only canonical marker (harness-hardening-retro-fixes Phase 2).
#
# SINGLE SOURCE OF TRUTH for the structural marker that flags a PHASES.md
# checkbox row (or its enclosing subsection) as runtime-verification-only —
# owned by the Step-9 /mcp-test gate, NOT outstanding implementation work.
#
# Open Question 2 (canonical marker form) is RESOLVED toward the per-row HTML
# comment ``<!-- verification-only -->`` rather than a single canonical
# subsection header, for two reasons:
#   1. Most robustly machine-detectable in remaining_unchecked_are_verification_only:
#      a row carries its OWN exemption marker, so no heading-scope bookkeeping is
#      needed and the detector survives NOVEL subsection phrasing by construction
#      (a never-before-seen header no longer needs a new regex alternative).
#   2. Survives the free-text-header whack-a-mole that motivated this feature
#      (two consecutive hardening rounds each grew _VERIFICATION_SECTION_RE).
#
# An HTML comment is invisible in rendered markdown, so it does not clutter the
# human-readable PHASES.md. It MAY appear on the checkbox row itself OR on the
# subsection header line (header-scope: it then exempts every row beneath that
# header until the next phase/section boundary).
#
# check-docs-consistency.ts fallback: the marker is a ROW ANNOTATION, not a
# sentinel, so it does NOT enter that script's SENTINEL_SCHEMAS. If a future
# edit to check-docs-consistency.ts cannot validate the HTML-comment form
# cleanly, fall back to a canonical subsection-header form and update BOTH this
# constant's value AND the producers that reference it by name (the lockstep
# test asserts producer prose == this constant).
# ---------------------------------------------------------------------------
_VERIFICATION_ONLY_MARKER = "<!-- verification-only -->"


# DEPRECATION SHIM (Phase 2). The legacy free-text header regex is retained ONLY
# so un-migrated PHASES.md (rows under a recognized header but WITHOUT the
# canonical marker) keep exempting cleanly — no regression. But every time the
# regex (and not the marker) is what exempts a row, the shim appends a
# _DIAGNOSTICS warning naming the un-migrated subsection so the migration gap is
# VISIBLE (a future cycle retires the regex once the shim stops firing across all
# live PHASES.md). New verification-subsection conventions should rely on the
# marker, NOT grow this regex.
_VERIFICATION_SECTION_RE = re.compile(
    r"runtime\s+verification|reachability\s+smoke"
    r"|mcp\s+(?:integration\s+test|test\s+assertion|assertion)"
    # Escalation (retry_count >= 2) seam-audit convention — blocked-resolution.md.
    # ``full[- ]chain\s+seam`` covers "full-chain seam audit"/"full chain seam
    # audit"; the bare ``seam\s+(?:audit|re-?validation)`` covers the shorter
    # "seam audit" / "seam re-validation" / "seam revalidation" header forms.
    r"|full[-\s]chain\s+seam|seam\s+(?:audit|re-?validation)",
    re.IGNORECASE,
)


# Bold subsection headers that introduce genuine IMPLEMENTATION work (`- [ ]`
# deliverables), as opposed to verification rows or prose. Entering one ENDS the
# prior verification subsection's legacy scope: a ``**Deliverables:**`` /
# ``**Implementation:**`` subsection placed AFTER a ``**Runtime Verification:**``
# / seam-audit subsection within the same phase must NOT let its implementation
# rows inherit the verification exemption (the escalation-corrective-phase shape
# `/add-phase` produces — seam audit first, deliverables second — which otherwise
# misroutes the feature straight to the MCP gate before the corrective code is
# written; burned on `adhoc-clap-live-poly-mod-producer-feed` Phase 6, 2026-06-24).
# DISTINCT from a prose bold like ``**Assessment:**`` / ``**Note:**`` (which must
# PRESERVE the enclosing verification scope — see
# test_verification_only_non_verification_bold_not_a_boundary): only a header
# naming an implementation section ends the scope. A markdown ``#`` heading already
# resets the scope structurally (the heading branch derives in_verification from
# _VERIFICATION_SECTION_RE) — this regex closes the same gap for the BOLD-marker
# subsection form the real AlgoBooth PHASES.md uses.
_DELIVERABLES_SECTION_RE = re.compile(
    r"\b(?:deliverable|implementation|work\s*unit|task)\w*\b",
    re.IGNORECASE,
)


# Deliberately-DROPPED-in-place deliverable rows (descope-in-place). A PHASES
# author (e.g. a NEEDS_INPUT.md resolution) may retire a planned deliverable by
# STRIKING IT THROUGH and tagging it with an explicit descope marker, rather
# than deleting the row (preserves the audit trail of WHY it was dropped):
#
#   - [ ] ~~<text>~~ **DROPPED** (decision N, NEEDS_INPUT.md resolution, <date>)
#
# Such a row is unambiguously not-to-be-done — exactly like a Superseded-phase
# row — and MUST count toward the "all remaining unchecked are exempt -> True"
# Step-7 bypass, else a fully-implemented item whose SOLE unchecked box is a
# descope note loops write-plan forever (live: live-settings-split-brain-...
# PHASES line 128, 2026-07-12). CONSERVATIVE BY CONSTRUCTION: BOTH a
# strikethrough span AND an explicit descope marker are required — a plain
# unchecked row, or a struck row WITHOUT a descope marker, still returns False
# (never over-exempt genuine implementation work).
#
# OVER-FIT NOTE: the descope-marker vocabulary below is a keyword set; the
# durable fix is a CANONICAL STRUCTURAL descope marker emitted by producers
# (parallel to _VERIFICATION_ONLY_MARKER, with this free-text form retained as a
# deprecation shim like _VERIFICATION_SECTION_RE). That generalization is spun
# off as its own item — until it lands, this is the free-text shim.
_DESCOPE_STRIKETHROUGH_RE = re.compile(r"~~.+?~~")
_DESCOPE_MARKER_RE = re.compile(
    r"\*\*\s*(?:DROPPED|DESCOPED|WON[’']?T[-\s]?FIX)\s*\*\*",
    re.IGNORECASE,
)


# Canonical structural descope marker (descoped-row-recognition-needs-canonical-marker).
#
# SINGLE SOURCE OF TRUTH for the per-row HTML comment that flags a PHASES.md
# checkbox row (or its enclosing subsection) as a deliberately-DROPPED-in-place
# deliverable — not-to-be-done, exactly like a Superseded row. Mirrors
# _VERIFICATION_ONLY_MARKER exactly: a per-row HTML comment, invisible in
# rendered markdown, PHRASING-INDEPENDENT. It is the PRIMARY descope signal —
# a row carrying it (or under a header carrying it) is exempt regardless of the
# free-text keyword, and needs NO accompanying strikethrough (unlike the legacy
# _DESCOPE_STRIKETHROUGH_RE + _DESCOPE_MARKER_RE shim path, which requires BOTH).
#
# The legacy free-text keyword pair below is now a DEPRECATION SHIM (parallel to
# _VERIFICATION_SECTION_RE): it still exempts un-migrated rows (no regression),
# but when the shim (and not this marker) is what exempts a row, a _DIAGNOSTICS
# warning names the un-migrated row so the migration gap is VISIBLE.
#
# check-docs-consistency.ts fallback: the marker is a ROW ANNOTATION, not a
# sentinel, so it does NOT enter that script's SENTINEL_SCHEMAS. If a future
# edit there cannot validate the HTML-comment form cleanly, fall back to a
# canonical subsection-header form and update BOTH this constant's value AND the
# producers that reference it by name (a lockstep test asserts producer == this).
_DESCOPED_MARKER = "<!-- descoped -->"


def _row_is_descoped_in_place(row_text: str) -> bool:
    """A deliberately-dropped deliverable row: struck-through AND descope-marked.

    LEGACY free-text path ONLY (the deprecation shim): BOTH a strikethrough span
    AND an explicit descope keyword marker are required — a plain unchecked row,
    or a bare strikethrough without a descope marker, is NOT exempt. Case-
    insensitive marker match; supports DROPPED / DESCOPED / WON'T-FIX.

    The canonical structural path (the caller checking ``_DESCOPED_MARKER``,
    row- or header-scope) requires NO strikethrough — this free-text function is
    consulted only as a fallback for un-migrated rows lacking the canonical marker.
    """
    return bool(_DESCOPE_STRIKETHROUGH_RE.search(row_text)) and bool(
        _DESCOPE_MARKER_RE.search(row_text)
    )


def remaining_unchecked_are_verification_only(phases_text: str) -> bool:
    """Return True iff every '- [ ]' line in PHASES.md is runtime-verification-only.

    Used by the Step 7 workstation bypass: when all implementation plans are
    Complete and the only remaining unchecked rows are workstation-only
    verification rows, /lazy should fall through to the retro→MCP gate rather
    than loop on write-plan.

    A row is verification-exempt when ANY of:
      - the row itself carries the canonical ``_VERIFICATION_ONLY_MARKER``
        (per-row HTML comment) — the PRIMARY, structural, header-text-independent
        path (Phase 2);
      - its enclosing subsection's HEADER line carries the marker (header-scope);
      - LEGACY (deprecation shim): its enclosing heading/bold-marker header text
        matches ``_VERIFICATION_SECTION_RE``. When the regex (and not a marker) is
        what exempts a row, a ``_DIAGNOSTICS`` warning is appended naming the
        un-migrated subsection — the rows still exempt (no regression) but the
        migration gap is surfaced (does NOT silently pass).

    Marker-based exemption is INDEPENDENT of the bold-header/heading free text, so
    a NOVEL verification-subsection phrasing no longer gaps the gate.

    Conservative: an unchecked row that is neither marker-exempt nor under a
    regex-matched header returns False (caller keeps write-plan / execute-plan).
    Returns False if no unchecked rows are present.

    Returns True when the ONLY remaining unchecked rows are all exempt — whether
    verification-only OR inside a Superseded phase (or a mix). This is the
    Step-7 bypass signal: no genuine implementation work remains, so fall through
    to the Step-9 MCP gate instead of looping on write-plan.

    Superseded phases: a ``### Phase N:`` (or ``## Phase N:``) heading enters a
    new phase and resets tracking. The first ``**Status:** Superseded`` bold-status
    line seen inside that phase marks the entire phase exempt; its unchecked rows
    count toward the True return (bypass-eligible) — they are descoped to a
    successor feature, never remaining implementation work.

    Descoped-in-place rows: the canonical structural ``_DESCOPED_MARKER``
    (``<!-- descoped -->``, row- or header-scope) is now the PRIMARY exemption
    signal — no strikethrough or keyword required, exactly parallel to
    ``_VERIFICATION_ONLY_MARKER``. LEGACY (deprecation shim): an unchecked row
    that is BOTH struck through (``~~...~~``) AND carries an explicit descope
    marker (``**DROPPED**``/``**DESCOPED**``/``**WON'T-FIX**``) is also a
    deliberately-dropped deliverable — not-to-be-done, exactly like a Superseded
    row — and counts toward the True return (see ``_row_is_descoped_in_place``),
    but emits a ``_DIAGNOSTICS`` migration warning since the canonical marker is
    absent. Conservative: a plain unchecked row, or a struck row without a
    descope marker AND without the canonical marker, still returns False.
    """
    in_verification = False        # legacy: enclosing header matched the regex
    section_has_marker = False     # marker present on the enclosing header line
    current_header_text = ""       # for the deprecation-shim diagnostic
    warned_headers: set[str] = set()  # de-dupe diagnostics per header text
    in_superseded_phase = False
    saw_unchecked = False
    # Superseded-phase unchecked rows are exempt (deliverables descoped to a
    # successor feature) and MUST count toward the "all remaining unchecked are
    # exempt → True" return exactly like verification-only rows. They are
    # `continue`d before ``saw_unchecked`` is set, so without a separate flag a
    # feature whose ONLY remaining unchecked rows all sit inside a Superseded
    # phase returns ``saw_unchecked=False`` — the Step-7 workstation bypass never
    # fires and the state machine loops on write-plan forever against an
    # already-implemented + MCP-validated feature (split-editor Phase 6,
    # 2026-07-01; the __mark_complete__ gate itself already exempts Superseded,
    # so the bypass was the sole hold-out).
    saw_superseded_unchecked = False
    # Deliberately-DROPPED-in-place rows (struck-through + descope marker) are
    # exempt like Superseded rows and MUST count toward the True return — see
    # _row_is_descoped_in_place. Tracked separately so an all-descoped remainder
    # still bypasses (mirrors saw_superseded_unchecked).
    saw_descoped_unchecked = False
    section_has_descope_marker = False   # descope marker present on the enclosing header line
    warned_descope_rows: set[str] = set()  # de-dupe descope-shim diagnostics per row text
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
            # block — reset all subsection tracking so the new phase begins clean.
            if re.match(r"Phase\s+\d+", heading_text):
                in_superseded_phase = False
                in_verification = False
                section_has_marker = False
                section_has_descope_marker = False
                current_header_text = ""
            else:
                # Non-phase heading (e.g. "### Runtime Verification" or a NOVEL
                # header). Marker on the header line → header-scope exemption,
                # text-independent. Else fall back to the legacy regex.
                section_has_marker = _VERIFICATION_ONLY_MARKER in line
                section_has_descope_marker = _DESCOPED_MARKER in line
                in_verification = bool(_VERIFICATION_SECTION_RE.search(heading_text))
                current_header_text = heading_text
            continue
        # Bold-marker subsection header (e.g. ``**Runtime Verification** ...``).
        # A list item like ``- **x**`` starts with '-', so it is not caught here.
        if stripped.startswith("**"):
            bold = re.match(r"^\*\*(.+?)\*\*", stripped)
            if bold:
                bold_text = bold.group(1)
                # Detect a per-phase "**Status:** Superseded" status line.
                # Mark the entire current phase exempt; do not alter scope flags
                # because a Superseded phase has no effective verification rows.
                if re.match(r"Status\s*:", bold_text) and "Superseded" in stripped:
                    in_superseded_phase = True
                    continue
                # Descope header-scope marker (orthogonal to the verification
                # if/elif below): a bold header carrying _DESCOPED_MARKER exempts
                # every plain row beneath it until the next phase / named-subsection
                # boundary. A new verification or deliverables subsection header
                # ends that scope (mirrors how section_has_marker is reset).
                if _DESCOPED_MARKER in line:
                    section_has_descope_marker = True
                elif _VERIFICATION_SECTION_RE.search(bold_text) or _DELIVERABLES_SECTION_RE.search(bold_text):
                    section_has_descope_marker = False
                # A bold subsection header enters verification scope via the
                # marker (text-independent) OR the legacy regex; an
                # implementation-section header (**Deliverables:** etc.) EXITS it;
                # any other non-matching bold (e.g. **Assessment:** / **Status:**)
                # is prose structure, NOT a section boundary — preserve current
                # scope.
                if _VERIFICATION_ONLY_MARKER in line:
                    section_has_marker = True
                    current_header_text = bold_text
                elif _VERIFICATION_SECTION_RE.search(bold_text):
                    in_verification = True
                    section_has_marker = False
                    current_header_text = bold_text
                elif _DELIVERABLES_SECTION_RE.search(bold_text):
                    # Implementation/deliverables subsection: rows beneath it are
                    # genuine implementation work. End the prior verification scope
                    # so they are NOT swept verification-only (the marker-based
                    # exemptions — per-row marker / section_has_marker — are
                    # unaffected; a genuinely-marked row beneath still exempts).
                    in_verification = False
                    section_has_marker = False
                    current_header_text = bold_text
                # else: do nothing (preserve current scope).
                continue
        if re.match(r"^-\s*\[\s*\]", stripped):
            # Unchecked boxes inside a Superseded phase are out of scope —
            # deliverables moved to a successor feature; do not treat as remaining
            # implementation work. Record that we saw one so an all-Superseded
            # remainder still returns True (bypass-eligible) at the end.
            if in_superseded_phase:
                saw_superseded_unchecked = True
                continue
            # A deliberately-DROPPED-in-place row (struck-through AND descope-
            # marked) is not-to-be-done, exactly like a Superseded-phase row.
            # Count it toward the all-remaining-exempt -> True bypass; do NOT
            # set saw_unchecked (it is not a verification row). Conservative:
            # _row_is_descoped_in_place requires BOTH signals, so a plain
            # unchecked row / a struck row without a marker falls through below.
            # PRIMARY descope path: a row carrying the canonical _DESCOPED_MARKER
            # (or under a header carrying it) is a deliberately-dropped deliverable,
            # exempt regardless of the free-text keyword and with NO strikethrough
            # required. No migration diagnostic — this is the non-deprecated path.
            if _DESCOPED_MARKER in line or section_has_descope_marker:
                saw_descoped_unchecked = True
                continue
            # LEGACY deprecation shim: struck-through AND a free-text descope keyword
            # (_DESCOPE_STRIKETHROUGH_RE + _DESCOPE_MARKER_RE) but NO canonical marker.
            # Still exempt (no regression for un-migrated PHASES.md), but surface the
            # migration gap so a future cycle can retire the shim.
            if _row_is_descoped_in_place(stripped):
                saw_descoped_unchecked = True
                if stripped not in warned_descope_rows:
                    warned_descope_rows.add(stripped)
                    _diag(
                        "descope marker absent (un-migrated producer): the "
                        f"unchecked row {stripped!r} is exempted by the legacy "
                        f"_DESCOPE_MARKER_RE deprecation shim, not the canonical "
                        f"{_DESCOPED_MARKER} marker. The producer should emit the "
                        f"marker per lazy_core:_DESCOPED_MARKER."
                    )
                continue
            saw_unchecked = True
            row_has_marker = _VERIFICATION_ONLY_MARKER in line
            # PRIMARY: a marker on the row or its enclosing subsection exempts,
            # independent of header free text.
            if row_has_marker or section_has_marker:
                continue
            # LEGACY deprecation shim: the header matched the regex but neither
            # the row nor the header carries the canonical marker. Still exempt
            # (no regression for un-migrated PHASES.md), but surface the gap.
            if in_verification:
                if current_header_text not in warned_headers:
                    warned_headers.add(current_header_text)
                    _diag(
                        "verification-only marker absent (un-migrated producer): "
                        f"unchecked rows under verification subsection "
                        f"{current_header_text!r} are exempted by the legacy "
                        f"_VERIFICATION_SECTION_RE deprecation shim, not the "
                        f"canonical {_VERIFICATION_ONLY_MARKER} marker. The "
                        f"producer should emit the marker per "
                        f"lazy_core:_VERIFICATION_ONLY_MARKER."
                    )
                continue
            # Neither marker nor regex-matched header → genuine implementation row.
            return False
    # True iff there were remaining unchecked rows AND every one was exempt —
    # verification-only (saw_unchecked, all reached a `continue`), inside a
    # Superseded phase (saw_superseded_unchecked), OR a deliberately-dropped-in-
    # place row (saw_descoped_unchecked). A genuine implementation row would
    # have returned False above. Genuinely-zero-unchecked returns False (all
    # flags stay False) — unchanged.
    return saw_unchecked or saw_superseded_unchecked or saw_descoped_unchecked


def classify_blocking_unchecked_rows(phases_text: str) -> dict:
    """Split completion-blocking unchecked PHASES rows for an ACTIONABLE refusal.

    ``--apply-pseudo __mark_complete__`` auto-ticks canonically
    ``<!-- verification-only -->``-marked rows, then REFUSES on any phase that
    still has an unchecked box — the DELIBERATE "the verification carve-out does
    not apply at completion time" strictness (see ``_phase_completion_plan`` /
    the parse note at its docstring). The bare "N unchecked box(es)" refusal
    could not distinguish two very different causes, which is exactly the friction
    observed on managed-llm-credits (5 of 7 blocking rows were merely un-migrated
    verification rows; 2 were genuine gaps). This helper classifies the STILL
    unchecked (post-autotick), non-Superseded rows into:

      - ``shim``    – exempt by the LEGACY ``_VERIFICATION_SECTION_RE`` subsection
                      shim (under a "Runtime Verification"-style header) but
                      LACKING the canonical marker. Such a row would clear the
                      gate IF migrated to the canonical marker — but migration →
                      auto-tick ASSERTS the row was actually validated, so a row
                      whose verification genuinely did not run on this host must
                      NOT be blindly migrated (the open per-row host-deferral
                      design question — see the turn-routing-enforcement
                      NEEDS_INPUT).
      - ``genuine`` – neither a canonical marker nor the legacy shim: a real
                      incomplete deliverable.

    DIAGNOSTIC ONLY — mirrors ``remaining_unchecked_are_verification_only``'s
    scope tracking; does NOT change the gate's decision (the refusal still fires).
    Returns ``{"shim": [row_excerpt, ...], "genuine": [row_excerpt, ...]}`` —
    each excerpt is prefixed ``L<N>: `` with the row's 1-based line number
    (completion-gate-refusal-opacity Fix Scope §2: both classes carry line
    numbers so the coherence-gate advisory is actionable without a second
    probe or a manual PHASES.md line count).
    """
    shim: list[str] = []
    genuine: list[str] = []
    in_verification = False
    section_has_marker = False
    in_superseded_phase = False
    in_fence = False
    for lineno, line in enumerate(phases_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if heading:
            heading_text = heading.group(1)
            if re.match(r"Phase\s+\d+", heading_text):
                in_superseded_phase = False
                in_verification = False
                section_has_marker = False
            else:
                section_has_marker = _VERIFICATION_ONLY_MARKER in line
                in_verification = bool(_VERIFICATION_SECTION_RE.search(heading_text))
            continue
        if stripped.startswith("**"):
            bold = re.match(r"^\*\*(.+?)\*\*", stripped)
            if bold:
                bold_text = bold.group(1)
                if re.match(r"Status\s*:", bold_text) and "Superseded" in stripped:
                    in_superseded_phase = True
                    continue
                if _VERIFICATION_ONLY_MARKER in line:
                    section_has_marker = True
                elif _VERIFICATION_SECTION_RE.search(bold_text):
                    in_verification = True
                    section_has_marker = False
                elif _DELIVERABLES_SECTION_RE.search(bold_text):
                    in_verification = False
                    section_has_marker = False
                continue
        if re.match(r"^-\s*\[\s*\]", stripped):
            if in_superseded_phase:
                continue
            # Canonical-marked rows are auto-ticked before this classifier runs,
            # so they are not blocking — skip them defensively if any remain.
            if _VERIFICATION_ONLY_MARKER in line or section_has_marker:
                continue
            excerpt = f"L{lineno}: " + stripped[:80] + ("…" if len(stripped) > 80 else "")
            if in_verification:
                shim.append(excerpt)
            else:
                genuine.append(excerpt)
    return {"shim": shim, "genuine": genuine}


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
#
# KEEP IN SYNC: user/scripts/phases-slice.py carries a deliberately private
# byte-identical copy of this pattern (it must not import lazy_core). The
# lockstep is mechanically pinned by
# test_phases_slice.py::LockstepTests::test_phase_heading_re_lockstep_with_lazy_core
# — if you edit this pattern, mirror the edit there or that test fails.
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
    # Header-scope descope tracking (descoped-marker-blind-completion-coherence-gate):
    # a non-phase heading or bold subsection header carrying _DESCOPED_MARKER exempts
    # every plain unchecked row beneath it until the next phase / named-subsection
    # boundary — the descope axis of the scope machinery proven in
    # remaining_unchecked_are_verification_only. Reset at each phase heading.
    section_has_descope_marker = False
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
            section_has_descope_marker = False
            current = {
                "heading": stripped,
                "status": None,
                "unchecked": 0,
                # Count of the ``unchecked`` rows above that are deliberately-DROPPED
                # (descoped-in-place) deliverables — a strict subset of ``unchecked``,
                # consulted ONLY by _phase_completion_plan so a fully-descoped phase
                # is not counted as a genuine incomplete deliverable at completion time
                # (descoped-marker-blind-completion-coherence-gate).
                "unchecked_descoped": 0,
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
        # Descope header-scope tracking (mirror of
        # remaining_unchecked_are_verification_only, descope axis only). A non-phase
        # heading (phase headings were handled + continued above) or a bold
        # subsection header carrying _DESCOPED_MARKER opens header-scope descope;
        # a verification/deliverables header WITHOUT the marker closes it. Other
        # bold prose (**Status:**, **Assessment:**) preserves the current scope.
        # This block only updates the flag and falls through — the Status /
        # phase-kind / checkbox handling below is unchanged.
        if re.match(r"^#{1,6}\s+", stripped):
            section_has_descope_marker = _DESCOPED_MARKER in line
        elif stripped.startswith("**"):
            if _DESCOPED_MARKER in line:
                section_has_descope_marker = True
            else:
                _bold = re.match(r"^\*\*(.+?)\*\*", stripped)
                if _bold and (
                    _VERIFICATION_SECTION_RE.search(_bold.group(1))
                    or _DELIVERABLES_SECTION_RE.search(_bold.group(1))
                ):
                    section_has_descope_marker = False
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
            # A deliberately-DROPPED-in-place unchecked row is exempt at completion
            # time exactly as remaining_unchecked_are_verification_only exempts it
            # mid-feature: canonical row-scope _DESCOPED_MARKER, an enclosing
            # header-scope descope marker, OR the legacy struck-through descope shim.
            if (
                _DESCOPED_MARKER in line
                or section_has_descope_marker
                or _row_is_descoped_in_place(stripped)
            ):
                current["unchecked_descoped"] += 1
        elif re.match(r"^-\s*\[[xX]\]", stripped):
            current["checked"] += 1
    # Drop the private bookkeeping key so the returned records expose only the
    # documented public fields (heading/status/unchecked/checked/phase_kind).
    for ph in phases:
        ph.pop("_phase_kind_seen", None)
    return phases


# Line-start "Implementation Notes" heading (## or ###). The body-evidence
# signal for phases_show_implementation — an Implementation Notes block is
# appended by /execute-plan after a phase lands, so its presence is positive
# proof the feature is past the pre-planning research stage. Matched only at
# line start (re.M); a fenced occurrence is a non-issue for this signal.
_IMPL_NOTES_HEADING_RE = re.compile(r"^#{2,3}\s+Implementation Notes\b", re.MULTILINE)

# Sibling IMPLEMENTATION_NOTES.md evidence signal. After the D3 writer flip,
# /execute-plan appends per-batch notes blocks (headed ``#### Implementation
# Notes (Phase N)``) to a sibling IMPLEMENTATION_NOTES.md instead of embedding
# them in PHASES.md. The block heading can be authored at any level (## / ### /
# ####), so this matches 2–4 leading hashes — broader than the embedded-PHASES
# regex above. A bare scaffold sibling (title + preamble only, no notes block)
# does NOT match, so it cannot falsely suppress research.
_SIBLING_IMPL_NOTES_HEADING_RE = re.compile(
    r"^#{2,4}\s+Implementation Notes\b", re.MULTILINE
)


def _sibling_impl_notes_present(phases_path: Path) -> bool:
    """Return True iff a sibling ``IMPLEMENTATION_NOTES.md`` next to ``phases_path``
    exists and carries at least one Implementation Notes block.

    Sibling = same directory as the PHASES.md being checked (the D3 writer
    resolves the sibling that way). Presence of a notes block (``#### / ### / ##
    Implementation Notes``) is the relocated equivalent of the legacy embedded
    heading; a bare title/preamble-only scaffold returns False. Read errors and
    a missing file return False (degrade to the embedded fallback).
    """
    sibling = phases_path.parent / "IMPLEMENTATION_NOTES.md"
    try:
        if not sibling.is_file():
            return False
        text = sibling.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(_SIBLING_IMPL_NOTES_HEADING_RE.search(text))


def phases_show_implementation(
    phases_text: str, phases_path: Path | None = None
) -> bool:
    """Return True iff a PHASES.md shows implementation EVIDENCE.

    The reusable primitive the Step-5 research-gate guard consults
    (research-gate-ignores-existing-phases): a feature whose PHASES.md already
    shows implementation is past the pre-planning research stage, so the
    research gate must NOT send it back for research.

    Composes the existing parsers — adds NO new parsing surface:

    - **Zero-phase stub guard (FIRST):** when ``parse_phases(phases_text)``
      yields zero phases (no ``## Phase`` heading — a stub / empty PHASES.md),
      return ``False`` unconditionally. A stub is treated exactly like "no
      PHASES.md" so a placeholder file does NOT suppress legitimate research
      (SPEC Open-Q1 / D2).
    - Otherwise return ``True`` when ANY of these signals holds:
        1. a parsed phase's ``status`` is ``Complete`` or ``In-progress``
           (case-insensitive compare on the stripped value), OR
        2. ``count_deliverables(phases_text)[1] >= 1`` — at least one checked
           ``- [x]`` deliverable (fence-awareness inherited from
           ``count_deliverables``: a checkbox inside a ``` fence does not
           count), OR
        3. **(sibling-then-embedded, D3)** when ``phases_path`` is supplied, a
           sibling ``IMPLEMENTATION_NOTES.md`` next to it carries an
           Implementation Notes block (the relocated-notes shape) — checked
           FIRST; OR
        4. an embedded ``## Implementation Notes`` (or ``###``) heading is
           present at a line start in PHASES.md (legacy in-flight features).
      Else ``False``.

    The sibling check (3) and the embedded fallback (4) make the predicate
    tolerant of the D3 split: a relocated-notes feature whose PHASES.md is now a
    thin checklist still reads as "implemented" and is NOT re-routed to research.
    When ``phases_path`` is ``None`` (legacy callers passing only text), only the
    embedded heading is consulted — behavior is unchanged for those callers.

    Side-effect-free apart from the optional sibling read. It emits NO ``_diag``
    — the diagnostic is the caller's responsibility (the Step-5 guard in
    ``lazy-state.py`` emits the D3 ``_diag`` line), keeping this predicate
    reusable elsewhere.
    """
    phases = parse_phases(phases_text)
    if not phases:
        # Stub / empty PHASES.md — treat as "no PHASES.md": do not suppress
        # research.
        return False
    for ph in phases:
        if (ph.get("status") or "").strip().lower() in {"complete", "in-progress"}:
            return True
    if count_deliverables(phases_text)[1] >= 1:
        return True
    # Sibling-then-embedded: prefer the relocated IMPLEMENTATION_NOTES.md, then
    # fall back to the embedded heading for legacy in-flight features.
    if phases_path is not None and _sibling_impl_notes_present(phases_path):
        return True
    if _IMPL_NOTES_HEADING_RE.search(phases_text):
        return True
    return False


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
        # Deliberately-DROPPED-in-place (descoped) unchecked rows are not owed
        # deliverables — they are exempt at completion time exactly as
        # remaining_unchecked_are_verification_only exempts them mid-feature (a
        # whole phase deferred by SPEC decision via row-/header-scope
        # _DESCOPED_MARKER, e.g. a "DEFERRED, not attempted" phase). Discount them
        # from the blocking count so a fully-descoped phase is coherent for
        # completion instead of deadlocking the receipt
        # (descoped-marker-blind-completion-coherence-gate). ``unchecked`` still
        # tallies every box; only the BLOCKING (non-descoped) remainder gates.
        effective_unchecked = ph["unchecked"] - ph.get("unchecked_descoped", 0)
        all_checked = has_boxes and effective_unchecked == 0

        # --- (a) auto-flip candidates ---
        # A present, non-terminal status whose every non-descoped box is checked
        # → flip (a phase whose only remaining rows are descoped is done-for-
        # completion just like an all-ticked phase).
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

        # Genuine (non-descoped) unchecked boxes in a non-Superseded phase always
        # block completion — the verification carve-out does not apply at
        # completion time, but a deliberately-descoped row is not a deliverable.
        if effective_unchecked > 0:
            refusals.append(
                f'{ph["heading"]}: {effective_unchecked} unchecked box(es)'
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
# evaluate_completion_evidence — authoritative-evidence decision table
#   (completion-coherence-gate-reconciliation Phase 1).
#
# A PURE, side-effect-free read of a feature's on-disk /mcp-test receipts that
# returns one of three LOCKED verdict literals — ``exempt-and-tick`` /
# ``warn-exempt`` / ``refuse`` — implementing the SPEC's Technical Design
# (LOCKED) authoritative-evidence decision table. The completion gate (Phase 3)
# branches on these literals; once landed they are a contract.
#
# It NEVER mutates PHASES.md (that is autotick_verification_rows, Phase 2) and
# is NOT wired into the completion gate here (Phase 3). The only I/O is reading
# the sentinel files + (for the HEAD-drift row) one ``git diff --name-only``
# via the existing subprocess pattern. It reuses parse_sentinel + _current_head
# and the SAME pass/total/validated_commit parse shape the
# __write_validated_from_results__ freshness backstop uses — no parallel reader.
# ---------------------------------------------------------------------------

def _coerce_evidence_count(raw):
    """Coerce a YAML count field to int, or None. Mirrors the
    __write_validated_from_results__ ``_coerce_count`` tolerance: a bool is NOT
    a count (YAML ``True`` is int 1 in Python), an int passes through, and a
    digit-string (quoted YAML) is coerced.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


# Sentinel filenames that, in the ABSENCE of passing results, mean "skip" or
# "defer" — both fail CLOSED (refuse, do NOT tick) per the decision table.
_FAIL_CLOSED_EVIDENCE_SENTINELS = (
    "SKIP_MCP_TEST.md",
    "DEFERRED_NON_CLOUD.md",
    "DEFERRED_REQUIRES_DEVICE.md",
    # host-capability-declaration-for-gated-features Phase 5: the host-axis
    # generalization of DEFERRED_REQUIRES_DEVICE.md. A capability-deferred
    # feature is defer-NOT-evidence — the completion gate must treat it as a
    # skip/defer (fail CLOSED: refuse, do NOT tick), exactly like the device
    # sentinel, so a host-deferred feature never reaches Complete on a host that
    # lacks the capability.
    "DEFERRED_REQUIRES_HOST.md",
)

# Kill-switch env vars (completion-coherence-gate-reconciliation Phase 3 /
# research §8 reversibility hardening). When EITHER is set to a truthy value,
# the evidence-gated auto-tick relaxation is disabled: the completion gate falls
# back to the legacy strict path (verification rows INCLUDED in refusals) and
# the PHASES.md auto-tick rewrite is skipped entirely — frictionless rollback
# without a code revert.
_EVIDENCE_GATE_KILL_SWITCHES = ("LAZY_STRICT_EVIDENCE_GATE", "LAZY_DISABLE_AUTOTICK")
_FALSY_ENV_VALUES = frozenset({"", "0", "false", "no", "off"})


def _evidence_gate_killed() -> bool:
    """True iff a kill-switch env var is set to a truthy value.

    Read once per completion call. A var set to an explicitly-falsy value
    (``""`` / ``0`` / ``false`` / ``no`` / ``off``, case-insensitive) does NOT
    arm the switch, so an inherited empty export cannot accidentally disable the
    feature.
    """
    for var in _EVIDENCE_GATE_KILL_SWITCHES:
        val = os.environ.get(var)
        if val is not None and val.strip().lower() not in _FALSY_ENV_VALUES:
            return True
    return False


# lazy-core-package-decomposition Phase 5 WU-3 (residue sweep): the sentinel
# lifecycle plane — detect_noncanonical_blocker, neutralize_sentinel, the
# PROVISIONAL eligibility/transform (provisional_eligibility /
# provisionalize_sentinel), and the independent-marker parse
# (parse_independent_marker) — moved here from _monolith.py — verbatim.

# ---------------------------------------------------------------------------
# detect_noncanonical_blocker — read-time stray-blocker detector
#   (noncanonical-blocker-filename-invisible-to-state-machine). Single writer of
#   the detection logic; lazy-state.py / bug-state.py Step 3 only CALL it.
# ---------------------------------------------------------------------------

def detect_noncanonical_blocker(spec_dir: Path) -> Path | None:
    """Return the first blocker-shaped *stray* file in ``spec_dir``, or None.

    A *stray* is a mis-named blocker sentinel that the literal ``BLOCKED.md``
    Step-3 check is blind to — e.g. ``BLOCKED_2026-06-09-foo.md`` or a
    lowercase ``blocked.md``. Such a file silently loops the pipeline (the
    state machine re-routes straight back into the same wall). This detector
    surfaces it so the caller can emit a distinct ``blocked-misnamed`` terminal.

    A directory entry's basename ``name`` is a stray iff ALL hold:
      * ``name.upper().startswith("BLOCKED")`` — blocker-shaped (case-insensitive).
      * ``name.lower().endswith(".md")``       — markdown sentinel.
      * ``name != "BLOCKED.md"``                — NOT the exact canonical name
        (canonical is owned by the caller's literal check; precise, case-sensitive).
      * ``"_RESOLVED_" not in name``            — NOT an already-neutralized
        blocker. Reuses ``neutralize_sentinel``'s literal ``_RESOLVED_`` guard
        so a renamed ``BLOCKED_RESOLVED_<date>.md`` never re-halts.

    Entries are scanned in ``sorted(spec_dir.iterdir())`` order so the "first
    offending path" is deterministic across platforms — the byte-pinned
    ``--test`` baselines depend on it.

    Robustness: returns None (never raises) when ``spec_dir`` does not exist or
    holds no stray.
    """
    if not spec_dir.exists():
        return None
    try:
        entries = sorted(spec_dir.iterdir())
    except OSError:
        return None
    # Canonical precedence (belt-and-suspenders): when the EXACT canonical
    # BLOCKED.md is present, the caller's literal Step-3 check owns the halt —
    # never surface a stray alongside it (would double-emit / shadow the
    # canonical `blocked` terminal). The state machines also wire this detector
    # AFTER their canonical check, so this is a second line of defense.
    # The check is case-SENSITIVE against the listed basenames (NOT
    # ``(spec_dir / "BLOCKED.md").exists()``, which is case-insensitive on
    # Windows/macOS and would wrongly treat a lowercase ``blocked.md`` stray as
    # the canonical file).
    names = [e.name for e in entries]
    if "BLOCKED.md" in names:
        return None
    for entry in entries:
        name = entry.name
        if (
            name.upper().startswith("BLOCKED")
            and name.lower().endswith(".md")
            and name != "BLOCKED.md"
            and "_RESOLVED_" not in name
        ):
            return entry
    return None


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
# park-provisional-acceptance — provisional acceptance of low-divergence
# product-class NEEDS_INPUT.md decisions (`--park-provisional`).
# ---------------------------------------------------------------------------

def _split_decision_context_h3s(body: str) -> list[str]:
    """Return the H3 subsection texts under the ``## Decision Context`` H2.

    Empty list when the H2 is absent. Each returned string starts at its
    ``### `` heading line and runs to the next H3/H2 boundary. Pure text
    helper shared by provisional_eligibility / provisionalize_sentinel.
    """
    m = re.search(r"^## Decision Context\s*$", body, re.MULTILINE)
    if not m:
        return []
    # Section runs to the next H2 (or EOF).
    tail = body[m.end():]
    next_h2 = re.search(r"^## \S", tail, re.MULTILINE)
    section = tail[: next_h2.start()] if next_h2 else tail
    parts = re.split(r"(?=^### )", section, flags=re.MULTILINE)
    return [p for p in parts if p.startswith("### ")]


def _extract_recommended_label(h3_text: str) -> str | None:
    """Extract the recommended option label from one Decision-Context H3.

    Primary source: the first ``- **<label> (Recommended)**`` options bullet
    (the schema mandates recommendation-first with the ``(Recommended)``
    suffix inside or right after the bold label). Fallback: the
    ``**Recommendation:** <label> — justification`` line's leading label.
    Returns None when neither yields a non-empty label (caller refuses).
    """
    # Options bullet carrying the (Recommended) marker — bold label with the
    # marker either inside the bold (`**X (Recommended)**`) or right after.
    for bm in re.finditer(r"^\s*-\s*\*\*(.+?)\*\*", h3_text, re.MULTILINE):
        label = bm.group(1).strip()
        rest = h3_text[bm.end(): bm.end() + 40]
        if "(Recommended)" in label or rest.lstrip().startswith("(Recommended)"):
            return label.replace("(Recommended)", "").strip() or None
    # Fallback: the Recommendation line — label runs to the em/double dash.
    rm = re.search(r"\*\*Recommendation:\*\*\s*(.+)", h3_text)
    if rm:
        line = rm.group(1).strip()
        label = re.split(r"\s+—\s+|\s+--\s+|\s+-\s+", line, maxsplit=1)[0]
        label = label.strip().strip("*").strip()
        if label:
            return label
    return None


def provisional_eligibility(sentinel_path: Path) -> tuple[bool, str]:
    """Deterministic, FAIL-CLOSED provisional-acceptance predicate (SPEC D3/D4/D8).

    Returns ``(eligible, reason)`` — ``reason`` names the first failed check
    (for the probe's ``_diag`` breadcrumb) or ``"eligible"``.

    A ``NEEDS_INPUT.md`` is provisional-eligible iff ALL of:
      - the frontmatter parses with ``kind: needs-input`` and a non-empty
        ``decisions:`` list of ≤4 entries;
      - it is NOT two-key mechanical (``class: mechanical`` AND
        ``audit_concurs: true``) — the existing flush auto-accept is the
        stronger path for those (full resolution, no ratification debt);
      - ``written_by`` is not ``completion-integrity-gate`` (integrity gaps
        are never recommendations);
      - ``stub_origin`` is absent or explicitly false (stub-origin-provisional-
        exclusion: baseline-shaping decisions from a stub-spec /spec Phase-1
        round or a /spec-bug pre-conclusion halt are never provisional);
      - the divergence two-key holds: ``divergence`` (producer, Key 1) AND
        ``audit_divergence`` (input-audit, Key 2) are BOTH in
        {isolated, contained} — absence, ``structural``, or any unknown value
        fails closed;
      - the body carries ``## Decision Context`` with one H3 per decision
        (1:1) and every H3 carries a ``**Recommendation:**`` block;
      - no ``## Resolution`` section exists yet (a mid-resolution file is
        owned by another path).

    Structurally corrupt frontmatter routes through ``parse_sentinel``'s
    ``_die`` like every other sentinel read.
    """
    if sentinel_path.name != "NEEDS_INPUT.md":
        return (False, f"not a NEEDS_INPUT.md ({sentinel_path.name})")
    meta = parse_sentinel(sentinel_path)
    if meta is None:
        return (False, "sentinel missing or without frontmatter")
    if meta.get("kind") != "needs-input":
        return (False, f"kind is {meta.get('kind')!r}, not needs-input")
    decisions = meta.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return (False, "decisions: absent or empty")
    if len(decisions) > 4:
        return (False, f"{len(decisions)} decisions exceeds the 4-decision cap")
    if str(meta.get("written_by", "")).strip() == "completion-integrity-gate":
        return (False, "written_by completion-integrity-gate — never provisional")
    # stub-origin-provisional-exclusion: decisions that shaped a baseline the
    # operator never saw (park-mode stub-spec /spec Phase-1 round, /spec-bug
    # pre-conclusion halt) are NEVER provisionally accepted, regardless of
    # divergence grades — jointly they define the item's foundation.
    # FAIL-CLOSED on malformed values: any present value that is not an
    # explicit false excludes.
    if "stub_origin" in meta:
        _so = meta.get("stub_origin")
        if not (_so is False or str(_so).strip().lower() in ("false", "no")):
            return (False, "stub_origin baseline decision — never provisional "
                           "(fail-closed)")
    if meta.get("class") == "mechanical" and meta.get("audit_concurs") is True:
        return (False, "two-key mechanical — flush auto-accept path wins (D4)")
    divergence = str(meta.get("divergence", "")).strip().lower()
    audit_divergence = str(meta.get("audit_divergence", "")).strip().lower()
    if divergence not in _PROVISIONAL_ELIGIBLE_GRADES:
        return (False, f"divergence {divergence or 'absent'!s} not in "
                       "{isolated, contained} (fail-closed)")
    if audit_divergence not in _PROVISIONAL_ELIGIBLE_GRADES:
        return (False, f"audit_divergence {audit_divergence or 'absent'!s} not in "
                       "{isolated, contained} (fail-closed)")
    try:
        text = sentinel_path.read_text(encoding="utf-8")
    except OSError as exc:
        return (False, f"unreadable sentinel: {exc}")
    if re.search(r"^## Resolution\s*$", text, re.MULTILINE):
        return (False, "already carries a ## Resolution section")
    h3s = _split_decision_context_h3s(text)
    if not h3s:
        return (False, "body missing ## Decision Context")
    if len(h3s) != len(decisions):
        return (False, f"{len(h3s)} H3 subsection(s) != {len(decisions)} "
                       "decisions (1:1 schema violation)")
    for i, h3 in enumerate(h3s):
        if "**Recommendation:**" not in h3:
            return (False, f"decision {i + 1} lacks a **Recommendation:** block")
    return (True, "eligible")


def provisionalize_sentinel(path: Path, repo_root: Path,
                            date: str | None = None) -> dict:
    """Provisionally accept a NEEDS_INPUT.md on its recommendations (SPEC D2).

    Re-validates the FULL eligibility predicate (fail-closed — the CLI action
    must never trust a stale probe), extracts each decision's recommended
    option label, appends a ``## Resolution`` block carrying
    ``resolved_by: auto-provisional`` + the HEAD ``decision_commit``, and
    renames the file to ``NEEDS_INPUT_PROVISIONAL.md`` (git-mv-aware,
    refusing — zero writes — when the target already exists).

    Returns::

        {ok, refused, choices: [{title, choice}], divergence,
         audit_divergence, decision_commit, renamed_to}
    """
    from .runtimeplane import _current_head  # deferred — runtimeplane imports docmodel at top level (genuine cycle)
    def _refuse(reason: str) -> dict:
        return {
            "ok": False, "refused": reason, "choices": [],
            "divergence": None, "audit_divergence": None,
            "decision_commit": None, "renamed_to": None,
        }

    eligible, reason = provisional_eligibility(path)
    if not eligible:
        return _refuse(reason)
    target = path.parent / PROVISIONAL_SENTINEL
    if target.exists():
        return _refuse(f"{PROVISIONAL_SENTINEL} already exists — refusing to clobber")

    meta = parse_sentinel(path) or {}
    decisions = [str(d) for d in meta.get("decisions", [])]
    text = path.read_text(encoding="utf-8")
    h3s = _split_decision_context_h3s(text)
    choices: list[dict] = []
    for i, h3 in enumerate(h3s):
        label = _extract_recommended_label(h3)
        if not label:
            return _refuse(
                f"decision {i + 1}: could not extract a recommended option "
                "label (no (Recommended) bullet and no parsable "
                "**Recommendation:** line)"
            )
        title = h3.splitlines()[0].lstrip("#").strip()
        choices.append({"title": title, "choice": label})

    # decision_commit anchors any later redirect's blast-radius diff
    # (`git diff <decision_commit>..HEAD`). Best-effort: a non-git dir (test
    # fixtures) records "unknown" rather than blocking the acceptance — the
    # sha is audit metadata, not a gate.
    decision_commit = _current_head(repo_root) or "unknown"
    if date is None:
        date = datetime.date.today().isoformat()
    divergence = str(meta.get("divergence")).strip().lower()
    audit_divergence = str(meta.get("audit_divergence")).strip().lower()

    lines = [
        "",
        "## Resolution",
        "",
        f"*Recorded on {date}. Provisionally auto-accepted on recommendation "
        "(`--park-provisional` divergence two-key). Ratify or redirect via "
        "the provisional-ratification affordance before completion.*",
        "",
        "resolved_by: auto-provisional",
        f"decision_commit: {decision_commit}",
        "",
    ]
    for i, ch in enumerate(choices, start=1):
        lines += [
            f"### {i}. {ch['title']}",
            "",
            f"**Choice:** {ch['choice']}",
            f"**Notes:** Provisionally accepted — divergence graded "
            f"{divergence} (producer) / {audit_divergence} (input-audit); "
            "pending operator ratification.",
            "",
        ]
    new_text = text.rstrip("\n") + "\n" + "\n".join(lines)
    _atomic_write(path, new_text)

    # Rename via git mv (history-preserving) with plain-rename fallback —
    # same pattern as neutralize_sentinel.
    renamed = False
    try:
        r = subprocess.run(
            ["git", "-C", str(path.parent), "mv", path.name, target.name],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            renamed = True
    except (OSError, subprocess.SubprocessError):
        pass
    if not renamed:
        path.rename(target)

    return {
        "ok": True, "refused": None, "choices": choices,
        "divergence": divergence, "audit_divergence": audit_divergence,
        "decision_commit": decision_commit, "renamed_to": target.name,
    }

# ---------------------------------------------------------------------------
# feature-budget-guard-and-skip-ahead Phase 3 — two-key skip-ahead predicates
#   (Locked Decision 5). Both are pure/near-pure and deterministic (no LLM
#   judgment): parse_independent_marker reads on-disk markers; skip_ahead_ready
#   combines a (caller-parsed) dep list with the gated-id set + the marker.
# ---------------------------------------------------------------------------

# The affirmative shared-state-isolation markers. `independent: true` is the
# primary; `no_shared_state: true` is a documented alias (SPEC Locked Decision 5).
_INDEPENDENT_MARKER_KEYS = ("independent", "no_shared_state")
# Matches a frontmatter line `independent: true` / `no_shared_state: true`
# (case-insensitive value; leading whitespace tolerated). Truthy ONLY for an
# explicit `true` — `false`/absent default to NOT-independent (the safe rail).
_INDEPENDENT_MARKER_RE = re.compile(
    r"^\s*(independent|no_shared_state)\s*:\s*true\s*$",
    re.IGNORECASE,
)


def _coerce_marker_truthy(value: object) -> bool:
    """True iff `value` is an explicit affirmative (bool True or a 'true' string).

    Deliberately strict: only ``True`` or a case-insensitive ``"true"`` count.
    A queue.json entry can carry either a JSON bool or a string; anything else
    (False, None, 0, "false", "") is NOT independent — the safe default.
    """
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def parse_independent_marker(spec_text: str, queue_entry: dict | None) -> bool:
    """Deterministic two-source read of the `independent: true` isolation marker
    (feature-budget-guard-and-skip-ahead Phase 3, Locked Decision 5).

    Returns ``True`` iff an explicit ``independent: true`` (or its
    ``no_shared_state: true`` alias) is present in EITHER the SPEC.md frontmatter
    OR the ``queue.json`` entry. Default (marker absent, or explicitly ``false``)
    is ``False`` — the shared-state-isolation rail that makes default-on
    skip-ahead safe (absent-flag items degrade to today's strict halt). On-disk,
    deterministic — no LLM judgment.

    Args:
        spec_text: the raw SPEC.md text (its frontmatter is scanned line-by-line;
            only the leading ``---`` fenced block is consulted when present, else
            the whole head of the file — a leading marker before any heading).
        queue_entry: the feature's ``queue.json`` entry (may be ``None``/empty).

    Returns:
        ``True`` if the affirmative marker is present in either source, else
        ``False``.
    """
    # Source 1: the queue entry (a JSON bool or string under either key).
    if isinstance(queue_entry, dict):
        for key in _INDEPENDENT_MARKER_KEYS:
            if _coerce_marker_truthy(queue_entry.get(key)):
                return True
    # Source 2: the SPEC.md frontmatter. Scan the leading `---` fenced block if
    # present; otherwise scan the head of the file up to the first markdown
    # heading (a bare leading `independent: true` line). The regex matches ONLY
    # an explicit `: true`, so a `: false` line is never a false positive.
    if isinstance(spec_text, str) and spec_text:
        lines = spec_text.splitlines()
        in_fence = False
        fence_seen = False
        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if not fence_seen and not in_fence:
                    in_fence = True
                    fence_seen = True
                    continue
                if in_fence:
                    # Closing fence — stop scanning the frontmatter block.
                    break
            if fence_seen and not in_fence:
                # We have already consumed a fenced block; don't scan the body.
                break
            if not fence_seen and stripped.startswith("#"):
                # No frontmatter fence and we hit a heading → no leading marker.
                break
            if _INDEPENDENT_MARKER_RE.match(line):
                return True
    return False
