#!/usr/bin/env python3
"""
lazy-state.py — Compute the next /lazy or /lazy-cloud state for autonomous orchestration.

Mirrors the state machine documented in:
  - user/skills/lazy/SKILL.md
  - repos/algobooth/.claude/skills/lazy-cloud/SKILL.md

Reads queue.json, ROADMAP.md, per-feature SPEC/PHASES/sentinels, and emits a
JSON object describing what to do next. Used by:
  - The thin-wrapper /lazy and /lazy-cloud (one-skill-per-invocation dispatch)
  - The /lazy-batch and /lazy-batch-cloud orchestrators (autonomous loop)

Usage:
    python3 lazy-state.py [--cloud] [--skip-needs-research]
                          [--real-device {yes,no,auto}] [--repo-root <path>]
    python3 lazy-state.py --test                    # run fixture smoke tests
    python3 lazy-state.py --run-start               # write run marker (pipeline=feature); gates registry/counter side-effects
    python3 lazy-state.py --run-end                 # delete marker + registry (run-scoped teardown)
    python3 lazy-state.py --probe [--repeat-count]  # --probe/--repeat-count fold/advance marker-persisted counters when a run marker is present; --repeat-count-peek reads without advancing

Output schema (stdout JSON):
{
  "feature_id":        "<id>"          | null,
  "feature_name":      "<name>"        | null,
  "spec_path":         "<absolute>"    | null,
  "current_step":      "<step name>"   | null,
  "sub_skill":         "<name>"        | null,
  "sub_skill_args":    "<args>"        | null,
  "terminal_reason":   null | "all-features-complete" | "cloud-queue-exhausted"
                            | "device-queue-exhausted"
                            | "queue-blocked-on-research"
                            | "blocked" | "needs-research" | "needs-input"
                            | "needs-spec-input" | "queue-missing"
                            | "completion-unverified" | "stale_upstream"
                            | "scoped-id-not-found",
  "notify_message":    "<string>"      | null,
  "diagnostics":       []                                  # always present; non-empty
                                                           # surfaces backlog warnings
                                                           # (e.g. plan files missing
                                                           # frontmatter)
}

Exit codes:
  0 — success (state computed, even if terminal)
  2 — malformed input (invalid YAML frontmatter, broken queue.json, etc.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("lazy-state.py requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(2)

# Domain-agnostic helpers live in lazy_core (WU-1.2 extraction). Import the
# module itself so lazy_core._DIAGNOSTICS is the canonical list object and
# lazy-state.py's _state() / compute_state() always reference the same list.
import lazy_core
from lazy_core import (
    _atomic_write,
    _die,
    _diag,
    clear_diagnostics,
    parse_sentinel,
    _parse_plan_frontmatter,
    _plan_status,
    _plan_lowest_phase,
    _plan_phase_set,
    _unchecked_wus_in_plan_scope,
    _phases_text_scoped_to,
    find_implementation_plans,
    find_retro_plans,
    latest_retro_plan,
    _has_any_complete_plan,
    retro_plan_has_significant_divergences,
    count_deliverables,
    remaining_unchecked_are_verification_only,
    _VERIFICATION_SECTION_RE,
    write_completed_receipt,
    has_completion_receipt,
    skip_waiver_refusal,
    spec_status,
)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _state(
    *,
    feature_id: str | None = None,
    feature_name: str | None = None,
    spec_path: str | None = None,
    current_step: str | None = None,
    sub_skill: str | None = None,
    sub_skill_args: str | None = None,
    terminal_reason: str | None = None,
    notify_message: str | None = None,
    diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    # Always include any diagnostics accumulated during this compute_state()
    # invocation (e.g. legacy plan files missing frontmatter). Callers may
    # also pass explicit diagnostics; both lists merge.
    # Reference lazy_core._DIAGNOSTICS — the canonical list owned by lazy_core.
    merged_diag = list(lazy_core._DIAGNOSTICS)
    if diagnostics:
        merged_diag.extend(diagnostics)
    out = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "spec_path": spec_path,
        "current_step": current_step,
        "sub_skill": sub_skill,
        "sub_skill_args": sub_skill_args,
        "terminal_reason": terminal_reason,
        "notify_message": notify_message,
        "diagnostics": merged_diag,
        # Structured list of features the device axis deferred this probe (each
        # has DEFERRED_REQUIRES_DEVICE.md + no VALIDATED.md on a no-real-device
        # host). Always present so /lazy-status and orchestrators
        # can surface lingering In-progress device-deferrals deterministically,
        # not only when the queue exhausts. Mirrors _DIAGNOSTICS.
        "device_deferred_features": list(_DEVICE_DEFERRED),
    }
    # CRITICAL INVARIANT: "parked" is ONLY included when _PARK_MODE is True.
    # When False the key must be entirely absent so default output (no flag) is
    # byte-identical to the pre-WU-1 Phase-4 baseline.
    if _PARK_MODE:
        out["parked"] = list(_PARKED)
    return out


# Device-deferred features observed this invocation (see _state()). Reset at the
# start of each compute_state() call alongside lazy_core._DIAGNOSTICS.
_DEVICE_DEFERRED: list[str] = []

# Park mode: when True (--park-needs-input flag), NEEDS_INPUT.md items are
# skipped (parked) instead of halting. The parked items accumulate in _PARKED.
# Reset at the start of each compute_state() call, alongside _DEVICE_DEFERRED.
_PARKED: list = []
_PARK_MODE: bool = False


# ---------------------------------------------------------------------------
# Host-capability probe (real audio output device present?)
# ---------------------------------------------------------------------------
#
# The framework now models THREE environments, not two:
#   - cloud                          (--cloud)            — no Tauri, no MCP, no device
#   - no-real-device workstation     (--real-device no)   — WSL2/CI: HeadlessPumpDriver
#   - real-device workstation        (--real-device yes)  — native Windows etc.: CpalOutputDriver
#
# The device axis is ORTHOGONAL to the cloud axis. It exists because some MCP
# audio assertions (sustained zero-dropout / timing-stability) can only be
# certified when a real hardware device callback drives the audio clock from a
# hardware interrupt — under AlgoBooth's HeadlessPumpDriver (a normal
# OS-scheduled thread) those metrics are non-deterministic. Such assertions are
# DEFERRED on a no-device host (DEFERRED_REQUIRES_DEVICE.md) and RE-OPENED on a
# real-device host, rather than permanently skipped.

# Standing override an operator sets on a real-device host (e.g. native Windows)
# so `--real-device auto` resolves correctly without the app running. Absent →
# treat as no-device (the conservative default: defer rather than fake-certify).
REAL_DEVICE_ENV = "ALGOBOOTH_REAL_AUDIO_DEVICE"

TR_STALE_UPSTREAM = "stale_upstream"
STEP_STALE_UPSTREAM = "Step 2.9: stale-upstream"


def resolve_real_device(flag_value: str) -> bool:
    """Resolve whether the CURRENT host has a real audio output device.

    Kept deliberately simple and PURE so the smoke tests stay hermetic (they run
    with no audio hardware):

    - ``yes`` / ``no`` — explicit injection. Tests and the orchestrator (which
      probes the live backend via ``get_audio_mode`` — ``mode == cpal`` and not
      ``forced`` → a real device) pass these directly. This is the injectable
      path the SPEC requires: the AlgoBooth-specific cpal-vs-headless probe lives
      in the orchestrator, NOT baked into this generic state script.
    - ``auto`` — read the ``ALGOBOOTH_REAL_AUDIO_DEVICE`` env var (``1``/``true``
      → real device); ABSENT → ``False`` (no device). Conservative: an unknown
      host defers (safe) rather than claiming real-device (which would let a
      sustained-timing assertion fake-certify under the headless pump).

    We never key this on hostname or ``ALGOBOOTH_AUDIO_HEADLESS`` heuristics —
    those mirror device presence only indirectly. The orchestrator owns the real
    probe; this resolver just makes the result injectable + testable.
    """
    if flag_value == "yes":
        return True
    if flag_value == "no":
        return False
    # auto
    raw = os.environ.get(REAL_DEVICE_ENV, "")
    return raw == "1" or raw.strip().lower() == "true"


# parse_sentinel — imported from lazy_core


def _current_head(repo_root: Path) -> str | None:
    """Resolve repo_root's HEAD commit sha, or None when repo_root is not a
    git repo / git is unavailable. Best-effort — the freshness check is
    SKIPPED (behavior unchanged) when this returns None."""
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


# ---------------------------------------------------------------------------
# queue.json + ROADMAP.md
# ---------------------------------------------------------------------------

def load_queue(repo_root: Path) -> list[dict[str, Any]]:
    queue_path = repo_root / "docs" / "features" / "queue.json"
    if not queue_path.exists():
        return []
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid queue.json: {exc}", queue_path)
        return []  # pragma: no cover
    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("queue.json 'queue' field must be an array", queue_path)
        return []  # pragma: no cover
    return items


def enqueue_adhoc(
    repo_root: Path,
    feature_id: str,
    name: str,
    brief: str,
    spec_dir: str | None = None,
    tier: int = 0,
) -> dict[str, Any]:
    """Insert an ad-hoc feature at the TOP of docs/features/queue.json.

    Deterministic bootstrap for the /lazy ad-hoc path: prepends a queue entry
    (so the next state probe picks it first), creates the spec dir, seeds
    ADHOC_BRIEF.md (which Step 4 routes to /spec), and adds a ROADMAP.md row.
    queue.json / ROADMAP.md are created if absent so ad-hoc works in a fresh
    repo. Idempotent on the brief/dir; refuses a duplicate feature_id.
    """
    repo_root = repo_root.resolve()
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", feature_id):
        _die(f"invalid feature_id (must be kebab-case): {feature_id!r}")
    features = repo_root / "docs" / "features"
    features.mkdir(parents=True, exist_ok=True)
    spec_dir = spec_dir or feature_id

    queue_path = features / "queue.json"
    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _die(f"invalid queue.json: {exc}", queue_path)
            return {}  # pragma: no cover
    else:
        data = {"queue": []}
    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("queue.json 'queue' field must be an array", queue_path)
        return {}  # pragma: no cover
    if any(isinstance(e, dict) and e.get("id") == feature_id for e in items):
        _die(f"feature_id already queued: {feature_id}", queue_path)
        return {}  # pragma: no cover

    items.insert(0, {
        "id": feature_id,
        "name": name,
        "spec_dir": spec_dir,
        "tier": tier,
        "adhoc": True,
    })
    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")

    spec_path = (features / spec_dir).resolve()
    spec_path.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    brief_file = spec_path / "ADHOC_BRIEF.md"
    if not brief_file.exists():
        brief_file.write_text(
            "---\n"
            "kind: adhoc-brief\n"
            f"feature_id: {feature_id}\n"
            "enqueued_by: lazy-adhoc\n"
            f"date: {today}\n"
            "---\n\n"
            f"# Ad-hoc task: {name}\n\n"
            f"{brief.strip() or '(brief not supplied — infer from context during /spec)'}\n",
            encoding="utf-8",
        )

    roadmap = features / "ROADMAP.md"
    row = f"- {name} — (ad-hoc, enqueued {today})\n"
    if roadmap.exists():
        text = roadmap.read_text(encoding="utf-8")
        if name not in text:
            if text and not text.endswith("\n"):
                text += "\n"
            roadmap.write_text(text + row, encoding="utf-8")
    else:
        roadmap.write_text("# Roadmap\n\n" + row, encoding="utf-8")

    return {
        "enqueued": True,
        "feature_id": feature_id,
        "feature_name": name,
        "spec_path": str(spec_path),
        "brief_path": str(brief_file),
        "queue_position": 0,
        "queue_length": len(items),
    }


def materialize_wi(repo_root: Path, wi_id, type_pipeline_map: dict) -> dict:
    """Materialize an ADO work item from ado-mirror.json into a doc pipeline.

    Routes by WI type:
      - feature types  → docs/features/<slug> via enqueue_adhoc
      - bug types      → docs/bugs/<slug> via bug-state.py --enqueue-adhoc subprocess
      - unknown types  → skip (no dirs, no queue entry, no materialized record)

    Idempotent: a double-call on the same wi_id yields exactly one queue entry
    and one materialized record.
    """
    repo_root = repo_root.resolve()
    mirror_path = repo_root / "docs" / "work" / "ado-mirror.json"
    try:
        mirror_data = json.loads(mirror_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _diag(f"materialize_wi: cannot load mirror: {exc}")
        return {"status": "skipped", "reason": "mirror-load-error"}

    wi = None
    for item in mirror_data.get("workItems", []):
        if item.get("id") == wi_id:
            wi = item
            break
    if wi is None:
        _diag(f"materialize_wi: wi_id={wi_id} not found in mirror")
        return {"status": "skipped", "reason": "not-in-mirror"}

    wi_type = wi.get("type", "")
    title = wi.get("title", "")
    description = wi.get("description", "")
    ac = wi.get("acceptanceCriteria", "")
    url = wi.get("url", "")
    changed_date = wi.get("changedDate", "")

    feature_types = type_pipeline_map.get("feature", [])
    bug_types = type_pipeline_map.get("bug", [])

    if wi_type in feature_types:
        route = "feature"
    elif wi_type in bug_types:
        route = "bug"
    else:
        _diag(f"materialize_wi: unknown WI type {wi_type!r} for wi_id={wi_id}")
        return {"status": "skipped", "reason": "unknown-type"}

    # Build slug: kebab-case from title
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug or not re.match(r"^[a-z0-9][a-z0-9-]*$", slug):
        slug = f"wi-{wi_id}"

    # Verbatim brief combining title, description, and acceptance criteria
    brief = f"Title: {title}\n\nDescription: {description}\n\nAcceptance Criteria: {ac}"

    if route == "feature":
        features_dir = repo_root / "docs" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        queue_path = features_dir / "queue.json"
        # Idempotency guard: skip enqueue_adhoc if already queued
        already_queued = False
        if queue_path.exists():
            try:
                qdata = json.loads(queue_path.read_text(encoding="utf-8"))
                if any(isinstance(e, dict) and (e.get("id") == slug or e.get("spec_dir") == slug)
                       for e in qdata.get("queue", [])):
                    already_queued = True
            except json.JSONDecodeError:
                pass
        if not already_queued:
            enqueue_adhoc(repo_root, slug, title, brief=brief, spec_dir=slug)
        # Ensure ADHOC_BRIEF.md contains all verbatim substrings
        brief_file = features_dir / slug / "ADHOC_BRIEF.md"
        brief_file.parent.mkdir(parents=True, exist_ok=True)
        if not brief_file.exists():
            brief_file.write_text(f"# Ad-hoc task: {title}\n\n{brief}", encoding="utf-8")
        else:
            existing = brief_file.read_text(encoding="utf-8")
            missing = [s for s in [title, description, ac] if s and s not in existing]
            if missing:
                augmented = existing.rstrip("\n") + "\n\n" + "\n".join(missing) + "\n"
                brief_file.write_text(augmented, encoding="utf-8")
        item_dir = features_dir / slug

    else:  # bug route
        bugs_dir = repo_root / "docs" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        # Call bug-state.py --enqueue-adhoc via subprocess (idempotent skip-on-dup)
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "bug-state.py"),
                "--enqueue-adhoc",
                "--id", slug,
                "--name", title,
                "--spec-dir", slug,
                "--repo-root", str(repo_root),
            ],
            check=True,
        )
        item_dir = bugs_dir / slug
        item_dir.mkdir(parents=True, exist_ok=True)
        # Write ADHOC_BRIEF.md (idempotent — only if absent)
        brief_file = item_dir / "ADHOC_BRIEF.md"
        if not brief_file.exists():
            brief_file.write_text(f"# Ad-hoc task: {title}\n\n{brief}", encoding="utf-8")

    # Both routes: write stub SPEC.md (idempotent — only if absent)
    spec_file = item_dir / "SPEC.md"
    if not spec_file.exists():
        spec_file.write_text(
            f"**Work Item:** AB#{wi_id} ({url})\n",
            encoding="utf-8",
        )

    # Both routes: record in materialized.json (idempotent on wi_id)
    work_dir = repo_root / "docs" / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    lazy_core.append_materialized(work_dir, wi_id, slug, changed_date)

    return {
        "status": "materialized",
        "feature_id": slug,
        "route": route,
        "wi_id": wi_id,
    }


def check_stale_upstream(repo_root: Path, mirror: dict | None = None) -> list:
    """Scan materialized.json vs ado-mirror.json; write STALE_UPSTREAM.md where upstream changed.

    For each materialized record, compares mirror WI changedDate with the
    materialized_changedDate. ISO-8601 UTC timestamps sort lexically, so a
    simple string comparison suffices. Writes STALE_UPSTREAM.md into the
    item dir (docs/features/<feature_id>/ or docs/bugs/<feature_id>/) for
    any stale item. Does NOT touch SPEC.md.

    Returns the list of stale-item dicts (wi_id, feature_id).
    """
    repo_root = repo_root.resolve()
    work_dir = repo_root / "docs" / "work"
    records = lazy_core.read_materialized(work_dir)

    if mirror is None:
        mirror_path = work_dir / "ado-mirror.json"
        try:
            mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _diag(f"check_stale_upstream: cannot load mirror: {exc}")
            return []

    # Build a lookup by wi_id from the mirror
    mirror_by_id: dict[Any, dict] = {}
    for wi in mirror.get("workItems", []):
        mirror_by_id[wi.get("id")] = wi

    stale: list[dict] = []
    for record in records:
        wi_id = record.get("wi_id")
        feature_id = record.get("feature_id")
        materialized_date = record.get("materialized_changedDate", "")

        mirror_wi = mirror_by_id.get(wi_id)
        if mirror_wi is None:
            continue

        mirror_date = mirror_wi.get("changedDate", "")
        if mirror_date > materialized_date:
            # Find the item directory (features first, then bugs)
            feat_dir = repo_root / "docs" / "features" / feature_id
            bug_dir = repo_root / "docs" / "bugs" / feature_id
            if feat_dir.is_dir():
                item_dir = feat_dir
            elif bug_dir.is_dir():
                item_dir = bug_dir
            else:
                _diag(
                    f"check_stale_upstream: no dir found for feature_id={feature_id!r}; skipping"
                )
                continue
            diff = (
                f"Upstream WI {wi_id} changed on {mirror_date} "
                f"(materialized: {materialized_date}) — re-materialize required.\n"
            )
            lazy_core.write_stale_upstream(item_dir, diff)
            stale.append({"wi_id": wi_id, "feature_id": feature_id})

    return stale


# spec_status — imported from lazy_core


def roadmap_marks_complete(roadmap_text: str, feature_name: str) -> bool:
    """Fallback completion signal: a ROADMAP.md row mentioning the feature with
    both `~~` strikethrough AND the `COMPLETE` token. Retained for repos that
    don't follow the SPEC.md status convention.

    Anchoring: we extract the text inside the first `~~...~~` pair on the line,
    take the portion before any ` — ` (space–em-dash–space) separator (which
    separates the feature name from its description), trim whitespace, and compare
    case-insensitively for EQUALITY with feature_name. This prevents a strict
    substring like "Audio" from matching an unrelated completed row whose name is
    "Audio Engine". Word-boundary anchors are insufficient here because `\bAudio\b`
    still matches within "Audio Engine".

    ROADMAP row grammar this match relies on:
      ~~<Feature Name> — <description>~~ ... **COMPLETE**
      ~~<Feature Name>~~ ... **COMPLETE**   (no description variant)
    The extracted token is the text before the first ` — ` (or the full strikethrough
    text if no separator is present), trimmed of surrounding whitespace.  Comparison
    is case-insensitive EQUALITY against feature_name — so a feature whose name is a
    prefix or substring of a different completed row (e.g. "Audio" vs "Audio Engine")
    does NOT produce a false match.
    """
    if not roadmap_text:
        return False
    # Matches the content inside the first ~~...~~ on a line.
    strikethrough_re = re.compile(r"~~([^~]+)~~")
    for line in roadmap_text.splitlines():
        if "~~" not in line or "COMPLETE" not in line:
            continue
        m = strikethrough_re.search(line)
        if not m:
            continue
        # The strikethrough text is "Name — description"; take the name portion.
        struck_text = m.group(1)
        struck_name = struck_text.split(" — ")[0].strip()
        if struck_name.lower() == feature_name.lower():
            return True
    return False


# has_completion_receipt — imported from lazy_core


def completion_claimed(
    roadmap_text: str,
    feature_name: str,
    spec_path: Path | None = None,
) -> bool:
    """True iff the feature CLAIMS completion — SPEC.md `**Status:**` is
    `Complete`/`Superseded`, OR the ROADMAP strikethrough+COMPLETE fallback
    matches.

    A *claim* is not *proof*: a cycle subagent (or a hand edit) can flip
    `**Status:** Complete` outside the validation gate. `has_completion_receipt()`
    is the companion check that distinguishes a gated completion from a claimed
    one. Step 2 uses both: claimed + receipt → genuinely done (skip);
    claimed (Complete) without receipt → `completion-unverified` hard-halt.
    `Superseded` is exempt from the receipt requirement (a retired feature was
    never validated and never should be).
    """
    status = spec_status(spec_path)
    if status in ("Complete", "Superseded"):
        return True
    return roadmap_marks_complete(roadmap_text, feature_name)


# write_completed_receipt — imported from lazy_core


def backfill_receipts(repo_root: Path) -> dict[str, Any]:
    """One-shot migration: write a COMPLETED.md (provenance:
    backfilled-unverified) for every queue feature that currently CLAIMS
    completion but lacks a receipt.

    Grandfathers in features completed before receipt-gating shipped so they
    don't trip the `completion-unverified` hard-halt (in lazy-state.py) or the
    `spec-complete-requires-receipt` lint rule, while truthfully labeling them as
    never-gate-verified.

    Walks EVERY on-disk `SPEC.md` under `docs/features/` (excluding `_archive/`)
    whose `**Status:**` is `Complete` — NOT just queued features. The receipt is
    a repo-wide audit artifact: many shipped features have been dequeued, so a
    queue-only walk would leave them receiptless and tripping the repo lint.
    `Superseded` specs are exempt (retired, never validated). The feature_id is
    the SPEC directory basename.
    """
    repo_root = repo_root.resolve()
    features_root = repo_root / "docs" / "features"
    today = datetime.now().strftime("%Y-%m-%d")
    written: list[str] = []
    skipped_superseded: list[str] = []
    if not features_root.exists():
        return {"backfilled": [], "count": 0, "skipped_superseded": []}
    for spec_md in sorted(features_root.glob("**/SPEC.md")):
        # Skip archived specs.
        if "_archive" in spec_md.parts:
            continue
        spec_dir = spec_md.parent
        status = spec_status(spec_dir)
        if status == "Superseded":
            skipped_superseded.append(spec_dir.name)
            continue
        if status != "Complete":
            continue
        receipt = spec_dir / "COMPLETED.md"
        if receipt.exists():
            continue
        write_completed_receipt(
            receipt, spec_dir.name, today,
            provenance="backfilled-unverified",
            body_note=(
                "Grandfathered during the receipt-gating rollout. This feature "
                "was marked Complete BEFORE the completion-integrity gate existed, "
                "so its pipeline validation (MCP / retro) was NOT verified by the "
                "gate. Treat as completed-but-unverified; re-validate if its "
                "behavior is load-bearing."
            ),
        )
        written.append(spec_dir.name)
    return {
        "backfilled": written,
        "count": len(written),
        "skipped_superseded": skipped_superseded,
    }


# ---------------------------------------------------------------------------
# SPEC parsing
# ---------------------------------------------------------------------------

def is_stub_spec(spec_text: str, queue_entry: dict[str, Any] | None = None) -> bool:
    """Detect stub-spec markers per /lazy Step 4.5.

    A SPEC is a stub iff any of these match:
    - Legacy markers in spec_text (`**Status:** Draft (research stub)`,
      `> Stub generated from advanced feature research`) — kept for back-compat.
    - Canonical pre-Gemini marker `Draft (pre-Gemini)` substring in spec_text
      (per AlgoBooth docs/CLAUDE.md).
    - `queue_entry.get("stub") is True` — the queue.json cross-check (per
      AlgoBooth docs/CLAUDE.md). Triggers stub mode even when the SPEC trailer
      is absent.

    Stub mode routes to interactive /spec at Step 4.5; the baseline doesn't
    exist yet and needs design conversation. Structured-but-research-pending
    specs (no stub markers, missing RESEARCH.md) are a different state — they
    halt at Step 5 with needs-research and wait for a Gemini upload.
    """
    if "**Status:** Draft (research stub)" in spec_text:
        return True
    if "> Stub generated from advanced feature research" in spec_text:
        return True
    # Anchor the pre-Gemini stub check so it does NOT fire on arbitrary prose
    # mentions of the phrase "Draft (pre-Gemini)". We match two structural forms:
    #   (a) The **Status:** line's value contains "Draft (pre-Gemini)" — e.g.
    #       `**Status:** Draft (pre-Gemini)` as a first-class status value.
    #   (b) A blockquote line beginning with `>` contains "Draft (pre-Gemini)" —
    #       e.g. `> Draft (pre-Gemini). Open questions ...` which is the canonical
    #       stub trailer format used in older SPECs (kept for back-compat).
    # Normal inline prose ("Unlike a Draft (pre-Gemini) stub, this spec ...") does
    # NOT start with `>` and does NOT appear on the **Status:** line, so it is
    # excluded. This prevents a false-positive stub classification for researched
    # specs that merely discuss the concept.
    if re.search(r"^\s*\*\*Status:\*\*\s*.*Draft \(pre-Gemini\)", spec_text, re.MULTILINE):
        return True
    if re.search(r"^\s*>.*Draft \(pre-Gemini\)", spec_text, re.MULTILINE):
        return True
    if queue_entry is not None and queue_entry.get("stub") is True:
        return True
    return False


def parse_dep_block(spec_text: str) -> list[dict[str, str]]:
    """Parse **Depends on:** block per _components/dep-block-schema.md.

    Returns a list of {feature_id, kind, reason}. Empty list for '(none)' or
    malformed/missing block (caller decides how to handle).
    """
    lines = spec_text.splitlines()
    deps: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        if lines[i].rstrip() == "**Depends on:**" or re.match(r"^\*\*Depends on:\*\*\s*\(none\)\s*$", lines[i]):
            if "(none)" in lines[i]:
                return []
            # Block-form: parse subsequent "- " lines until blank or heading
            j = i + 1
            while j < len(lines):
                line = lines[j]
                stripped = line.strip()
                if not stripped:
                    # Allow one blank line between header and list (form A in schema)
                    if not deps:
                        j += 1
                        continue
                    break
                if stripped.startswith("# ") or stripped.startswith("## ") or stripped.startswith("---"):
                    break
                if not stripped.startswith("- "):
                    break
                # Split on " — " (space em-dash space)
                payload = stripped[2:]
                parts = payload.split(" — ")
                if len(parts) >= 3:
                    feature_id, kind, reason = parts[0].strip(), parts[1].strip(), " — ".join(parts[2:]).strip()
                    if kind in ("hard", "soft", "composes") and re.match(r"^[a-z0-9][a-z0-9-]*$", feature_id):
                        deps.append({"feature_id": feature_id, "kind": kind, "reason": reason})
                j += 1
            return deps
        i += 1
    return []


def resolve_upstream_dir(repo_root: Path, current_spec_dir: Path, feature_id: str) -> Path | None:
    """Resolve an upstream feature directory per the schema's resolution protocol."""
    # 1. Sibling-first
    sibling = current_spec_dir.parent / feature_id
    if (sibling / "SPEC.md").exists():
        return sibling
    # 2. queue.json fallback
    queue_path = repo_root / "docs" / "features" / "queue.json"
    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
            for entry in data.get("queue", []):
                if entry.get("id") == feature_id:
                    sd = entry.get("spec_dir")
                    if sd:
                        cand = (repo_root / "docs" / "features" / sd).resolve()
                        if (cand / "SPEC.md").exists():
                            return cand
                        cand2 = (repo_root / sd).resolve()
                        if (cand2 / "SPEC.md").exists():
                            return cand2
        except (json.JSONDecodeError, OSError):
            pass
    # 3. Search fallback
    features_root = repo_root / "docs" / "features"
    if features_root.exists():
        hits = list(features_root.glob(f"**/{feature_id}/SPEC.md"))
        if len(hits) == 1:
            return hits[0].parent
    return None


def upstream_is_complete(repo_root: Path, upstream_dir: Path) -> bool:
    """ROADMAP strikethrough+COMPLETE OR upstream SPEC Status: Complete."""
    roadmap = repo_root / "docs" / "features" / "ROADMAP.md"
    if roadmap.exists():
        text = roadmap.read_text(encoding="utf-8")
        upstream_name = upstream_dir.name
        # ROADMAP rows usually mention the directory name or human name; check both.
        # We apply whole-token anchoring: extract the text inside ~~...~~, take the
        # portion before any " — " separator, trim, and compare case-insensitively
        # for EQUALITY. This prevents "audio" from matching "~~audio-engine — ...~~".
        # The bare `upstream_name in line` check would produce a false positive
        # whenever upstream_name is a prefix/substring of a different completed name.
        strikethrough_re = re.compile(r"~~([^~]+)~~")
        for line in text.splitlines():
            if "~~" not in line or "COMPLETE" not in line:
                continue
            m = strikethrough_re.search(line)
            if not m:
                continue
            struck_name = m.group(1).split(" — ")[0].strip()
            if struck_name.lower() == upstream_name.lower():
                return True
    spec = upstream_dir / "SPEC.md"
    if spec.exists():
        try:
            for line in spec.read_text(encoding="utf-8").splitlines():
                if re.match(r"^\*\*Status:\*\*\s*Complete\s*$", line):
                    return True
        except OSError:
            pass
    return False


def newest_realign_plan(spec_dir: Path) -> Path | None:
    plans_dir = spec_dir / "plans"
    if not plans_dir.exists():
        return None
    candidates = sorted(plans_dir.glob("realign-*.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _phases_sha(upstream_dir: Path) -> str | None:
    """Return the sha256 hex digest of <upstream_dir>/PHASES.md, or None if absent.

    Used by realign_is_fresh to compare recorded upstream hashes in a realign
    plan's frontmatter against the current on-disk state. Git checkout/clone
    resets mtimes, making them unreliable; content hashes are stable.
    """
    phases_path = upstream_dir / "PHASES.md"
    if not phases_path.exists():
        return None
    return hashlib.sha256(phases_path.read_bytes()).hexdigest()


def realign_is_fresh(spec_dir: Path, hard_complete_upstream_dirs: list[Path]) -> bool:
    """Skip-if-fresh gate per /lazy Step 4.6a.

    Hash path (new): if the newest realign plan's frontmatter carries an
    ``upstream_phases_hashes`` dict (dir-name → sha256 hex), compare each
    recorded hash against the current PHASES.md on disk. Any mismatch or
    missing recorded entry means stale → realign needed → return False.
    All hashes match → return True (fresh, no realign needed).

    Legacy/mtime path (preserved): if the plan has no ``upstream_phases_hashes``
    field (older plan written before WU-8), fall back to the original mtime
    comparison so pre-existing realign plans are not invalidated.
    """
    plan = newest_realign_plan(spec_dir)
    if plan is None:
        return False

    # Try the hash path first: parse the plan's frontmatter and look for the
    # recorded upstream hashes dict.
    meta = _parse_plan_frontmatter(plan) or {}
    recorded_hashes = meta.get("upstream_phases_hashes")

    if recorded_hashes is not None:
        # Hash path: compare recorded sha256 against current PHASES.md content.
        # Any upstream whose hash is absent from the recorded dict OR whose
        # current sha256 differs from the recorded value triggers a re-realign.
        for ud in hard_complete_upstream_dirs:
            dir_name = ud.name
            if dir_name not in recorded_hashes:
                # Upstream not recorded — treat as stale (plan was written
                # before this dependency was added, or for a different set).
                return False
            current_sha = _phases_sha(ud)
            if current_sha is None:
                # Upstream has no PHASES.md — skip (same as before; can't
                # compare a hash for a file that doesn't exist).
                continue
            if current_sha != recorded_hashes[dir_name]:
                # Hash mismatch: upstream PHASES.md changed since the realign
                # plan was written → stale → re-realign needed.
                return False
        return True

    # Legacy/mtime fallback: no upstream_phases_hashes in the plan frontmatter
    # (old plan). Preserve exact original behaviour so pre-WU-8 plans still work.
    plan_mtime = plan.stat().st_mtime
    for ud in hard_complete_upstream_dirs:
        upstream_phases = ud / "PHASES.md"
        if not upstream_phases.exists():
            continue
        if upstream_phases.stat().st_mtime > plan_mtime:
            return False
    return True


# ---------------------------------------------------------------------------
# PHASES.md analysis — imported from lazy_core
# ---------------------------------------------------------------------------
# count_deliverables, remaining_unchecked_are_verification_only,
# _VERIFICATION_SECTION_RE — all imported from lazy_core above.

# ---------------------------------------------------------------------------
# Plan file discovery — imported from lazy_core
# ---------------------------------------------------------------------------
# _parse_plan_frontmatter, _plan_status, _plan_lowest_phase, _plan_phase_set,
# _unchecked_wus_in_plan_scope, find_implementation_plans, _has_any_complete_plan,
# find_retro_plans, latest_retro_plan, retro_plan_has_significant_divergences
# — all imported from lazy_core above.


def _plan_cloud_saturated(plan_path: Path, phases_text: str, spec_path: Path) -> bool:
    """Return True iff every unchecked WU in PHASES.md scoped to this plan's
    declared phases is documented (by substring match) in
    `<spec_path>/DEFERRED_NON_CLOUD.md`.

    Used by the Step 7a cloud-saturation gate to decide whether an
    In-progress plan should be auto-flipped to Complete because all
    cloud-runnable work is done and the only remainder is workstation-only
    deliverables explicitly deferred to the workstation MCP path.

    Conservative semantics:
      - Plans with no `phases:` field → False (we can't scope what counts as
        "in this plan", so we refuse to auto-flip).
      - Zero unchecked WUs in scope → False (the plan is already cloud-done;
        Step 8 retro would normally fire instead — let the existing flow run).
      - Any unchecked WU whose label does NOT appear (substring) in
        DEFERRED_NON_CLOUD.md → False.
    """
    deferred_file = spec_path / "DEFERRED_NON_CLOUD.md"
    if not deferred_file.exists():
        return False
    phase_set = _plan_phase_set(plan_path)
    if not phase_set:
        return False
    unchecked = _unchecked_wus_in_plan_scope(phases_text, phase_set)
    if not unchecked:
        return False
    try:
        deferred_text = deferred_file.read_text(encoding="utf-8")
    except OSError:
        return False
    for wu in unchecked:
        if wu not in deferred_text:
            return False
    return True


# find_implementation_plans, _has_any_complete_plan, find_retro_plans,
# latest_retro_plan, retro_plan_has_significant_divergences
# — all imported from lazy_core above.


# ---------------------------------------------------------------------------
# Step 10 helpers
# ---------------------------------------------------------------------------

def _write_step10_needs_input(spec_dir: Path, feature_name: str) -> None:
    """Write a well-formed NEEDS_INPUT.md sentinel into spec_dir for the Step 10
    unexpected-state defensive branch.

    The Step 10 branch fires when all phases are complete but none of the
    expected validation sentinels (VALIDATED.md, SKIP_MCP_TEST.md, or
    DEFERRED_NON_CLOUD.md) exists — a state that should be unreachable via the
    normal pipeline but may arise from manual sentinel manipulation. Writing
    NEEDS_INPUT.md here ensures the orchestrator's Step 1g decision-resume can
    surface the issue to the operator rather than silently cycling.

    Follows the NEEDS_INPUT.md schema in
    ~/.claude/skills/_components/sentinel-frontmatter.md:
      - YAML frontmatter: kind, feature_id, written_by, decisions list, date
      - Body: ## Decision Context H2 with one H3 per decision

    Idempotent: overwrites an existing NEEDS_INPUT.md without error.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    # Derive feature_id from the last component of spec_dir (standard convention:
    # docs/features/<feature-id>/). Used in both the frontmatter and body.
    feature_id = spec_dir.name

    decision_title = (
        "Resolve unexpected Step 10 state: phases complete without a validation sentinel"
    )
    content = (
        "---\n"
        "kind: needs-input\n"
        f"feature_id: {feature_id}\n"
        "written_by: lazy-state-step10\n"
        "decisions:\n"
        f'  - "{decision_title}"\n'
        f"date: {today}\n"
        "---\n"
        "\n"
        "## Decision Context\n"
        "\n"
        f"### 1. {decision_title}\n"
        "\n"
        "**Problem:** All PHASES.md deliverables are complete but none of the "
        "expected validation sentinels exist: no `VALIDATED.md`, no "
        "`SKIP_MCP_TEST.md`, and no `DEFERRED_NON_CLOUD.md`. This state is "
        "defensively unreachable via the normal pipeline — it most likely means "
        f"sentinels were deleted or renamed manually for `{feature_name}`. "
        "The pipeline cannot proceed to Step 10 (mark complete) without knowing "
        "whether MCP validation was performed.\n"
        "\n"
        "**Options:**\n"
        "- **Re-open for MCP validation** — re-run `/lazy` so the pipeline "
        "re-dispatches `/mcp-test`. Use this when the feature was never actually "
        "validated.\n"
        "- **Restore a missing sentinel** — if `VALIDATED.md` or `SKIP_MCP_TEST.md` "
        "was accidentally deleted, recreate it (check git history for the original "
        "content) and re-run `/lazy`. Use this when validation DID happen but the "
        "file was lost.\n"
        "- **Investigate and reset** — if the root cause is unclear, check "
        "`git log -- docs/features/ ` and `git log --diff-filter=D` to find when "
        "the sentinels were removed, then decide which of the above options applies.\n"
        "\n"
        "**Recommendation:** Re-open for MCP validation — this is the safest option "
        "because it forces a confirmed validation pass before `Complete` is written.\n"
    )
    needs_input_path = spec_dir / "NEEDS_INPUT.md"
    needs_input_path.write_text(content, encoding="utf-8")


def _phases_effectively_complete(spec_path: Path) -> bool:
    """Return True iff a feature has no remaining actionable implementation work.

    This is the precondition the Step 2 cloud/device-saturated skips used to
    encode via the presence of RETRO_DONE.md (which only ever existed once
    phases were complete and a retro round ran). With retro unwired, RETRO_DONE
    no longer exists, so we test the underlying property directly: a feature is
    "past implementation" when its PHASES.md has zero unchecked deliverables, OR
    every implementation plan is Complete and only verification-only rows remain
    (the same condition the Step-7 MCP-gate bypass keys on). A feature still
    mid-implementation (unchecked real deliverables, or an In-progress plan that
    still has actionable cloud work) is NOT saturated — it must keep dispatching
    execute-plan / Step-7a, never be silently skipped here.
    """
    phases_file = spec_path / "PHASES.md"
    if not phases_file.exists():
        return False
    phases_text = phases_file.read_text(encoding="utf-8")
    unchecked, _checked = count_deliverables(phases_text)
    if unchecked == 0:
        return True
    # Remaining unchecked rows are tolerable ONLY when they are verification-only
    # AND every implementation plan is already Complete (no execute-plan work
    # left). This mirrors the Step-7 bypass: an In-progress plan with actionable
    # rows still has work and is therefore NOT saturated.
    if (
        not find_implementation_plans(spec_path)
        and _has_any_complete_plan(spec_path)
        and remaining_unchecked_are_verification_only(phases_text)
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Main state machine
# ---------------------------------------------------------------------------

def compute_state(
    repo_root: Path,
    cloud: bool,
    skip_needs_research: bool = False,
    real_device: bool = True,
    scope_feature_id: str | None = None,
    park_needs_input: bool = False,
) -> dict[str, Any]:
    # `real_device` defaults to True (behavior-preserving: a feature completes
    # exactly as before). ALL device-deferral logic below is gated on the
    # presence of a `DEFERRED_REQUIRES_DEVICE.md` sentinel, so this default has
    # NO effect on a feature that doesn't carry one. The CLI's `--real-device
    # auto` resolves the host's true capability and passes the result.
    #
    # Cloud has no audio device by definition, so cloud forces no-device: a
    # nonsensical `--cloud --real-device yes` is ignored. The device re-open
    # path lives in the workstation branch, which cloud never reaches; the
    # Step 2 device-saturated skip below is gated on `not real_device`, which
    # cloud satisfies.
    if cloud:
        real_device = False
    # Reset diagnostics for this invocation so callers get a fresh list per
    # compute_state() call (matters in run_smoke_tests() which loops).
    # clear_diagnostics() resets lazy_core._DIAGNOSTICS — the canonical list.
    clear_diagnostics()
    _DEVICE_DEFERRED.clear()
    # Park mode: set the module global from the param so _state() can gate
    # the "parked" key on it.  _PARKED accumulates items skipped this invocation.
    global _PARK_MODE, _PARKED
    _PARK_MODE = park_needs_input
    _PARKED.clear()
    repo_root = repo_root.resolve()

    # WU-8: auto-trigger stale-upstream detection at probe start when an ADO
    # materialization mirror exists. check_stale_upstream writes STALE_UPSTREAM.md
    # into any item dir whose upstream WI changed since materialize; Step 2.9 then
    # halts on it. This is the production writer the stale-upstream halt previously
    # lacked. Guarded by materialized.json so the common queue-only workflow is a no-op.
    if (repo_root / "docs" / "work" / "materialized.json").exists():
        check_stale_upstream(repo_root)

    queue = load_queue(repo_root)
    if not queue:
        return _state(
            terminal_reason="queue-missing",
            notify_message="queue.json not found — /lazy cannot operate.",
        )

    roadmap_path = repo_root / "docs" / "features" / "ROADMAP.md"
    roadmap_text = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else ""

    # Step 2: find current feature
    current = None
    cloud_saturated_skipped: list[str] = []
    device_saturated_skipped: list[str] = []
    research_pending_skipped: list[str] = []
    seen_ids: set[str] = set()
    # Tracks whether the --feature-id scope arg matched ANY entry in the queue
    # (by raw id, before any dir/duplicate/completion skip).  If scope is set but
    # no entry matched, we emit "scoped-id-not-found" instead of "all-features-complete"
    # so callers can distinguish "queue exhausted" from "id typo / not queued".
    scope_id_seen: bool = False
    for entry in queue:
        name = entry.get("name")
        feature_id = entry.get("id")
        spec_subdir = entry.get("spec_dir")
        if not name or not feature_id or not spec_subdir:
            missing = [k for k, v in (("id", feature_id), ("name", name), ("spec_dir", spec_subdir)) if not v]
            _diag(
                f"queue entry skipped — missing {', '.join(missing)} "
                f"(entry: {str(entry)[:120]!r})"
            )
            continue
        # FM3 anti-fabrication guard: a queue entry whose spec_dir does NOT
        # resolve to an on-disk directory is a dangling reference (typo, stale
        # entry, or — the failure this guards — a hallucinated feature). Skip it
        # with a loud diagnostic rather than returning it for dispatch; a cycle
        # against a non-existent feature is exactly what lets a subagent
        # FABRICATE the SPEC/RESEARCH/queue entries from a bare slug. The ONLY
        # sanctioned dir-creating paths are --enqueue-adhoc (seeds the dir
        # before the queue entry) and /spec on an already-seeded dir.
        spec_path = (repo_root / "docs" / "features" / spec_subdir).resolve()
        if not spec_path.exists():
            _diag(
                f"dangling queue entry: '{feature_id}' (spec_dir '{spec_subdir}') "
                "does not resolve to an on-disk directory under docs/features/ — "
                "skipped. Create the spec dir (via /spec or --enqueue-adhoc) or "
                "remove the stale queue entry. A cycle is NEVER dispatched against "
                "a feature that does not exist on disk."
            )
            continue
        # Duplicate-id guard: first entry wins; a second entry with the same id
        # is silently orphaned otherwise. Surface it.
        if feature_id in seen_ids:
            _diag(f"duplicate queue id '{feature_id}' — second entry ignored.")
            continue
        seen_ids.add(feature_id)
        # --feature-id scoping: when set, process ONLY the matching queue entry.
        # Absent the flag (None) behavior is byte-identical to single-current.
        # scope_id_seen is set here — BEFORE any completion/cloud/device skip
        # would continue past the entry — so a matched-but-skipped scoped feature
        # still counts as "seen" (not reported as scoped-id-not-found).
        if scope_feature_id is not None:
            if feature_id != scope_feature_id:
                continue
            scope_id_seen = True
        # FM1 receipt-gated completion. A feature is genuinely DONE only when it
        # CLAIMS completion AND carries a durable COMPLETED.md receipt proving it
        # passed through __mark_complete__'s integrity gate. Superseded is exempt
        # (a retired feature was never validated).
        if completion_claimed(roadmap_text, name, spec_path):
            if spec_status(spec_path) == "Superseded" or has_completion_receipt(spec_path):
                continue
            # Claimed Complete WITHOUT a receipt → the SPEC/ROADMAP was flipped
            # outside the validation gate (a cycle subagent or hand edit). This
            # is the exact failure that let a feature skip /retro + /mcp-test.
            # Hard-halt and surface for reconciliation rather than silently
            # treating it as done.
            return _state(
                feature_id=feature_id,
                feature_name=name,
                spec_path=str(spec_path),
                current_step="Step 2: completion claimed without receipt",
                terminal_reason="completion-unverified",
                notify_message=(
                    f"{name}: SPEC/ROADMAP marks this Complete but no COMPLETED.md "
                    "receipt exists — it was flipped OUTSIDE the validation gate. "
                    "Reconcile: reopen to In-progress for real validation, or run "
                    "lazy-state.py --backfill-receipts to grandfather it as "
                    "completed-but-unverified."
                ),
            )
        if cloud:
            # Cloud-saturated skip. (Retro unwired: the old RETRO_DONE.md
            # precondition is replaced by _phases_effectively_complete() — the
            # underlying "past implementation" property RETRO_DONE used to
            # proxy. A cloud feature past implementation that deferred MCP to
            # workstation carries DEFERRED_NON_CLOUD.md + no VALIDATED.md. A
            # feature still mid-implementation must NOT be skipped — it has
            # actionable Step-7 work.)
            deferred = (spec_path / "DEFERRED_NON_CLOUD.md").exists()
            validated = (spec_path / "VALIDATED.md").exists()
            if deferred and not validated and _phases_effectively_complete(spec_path):
                cloud_saturated_skipped.append(name)
                continue
        if not real_device:
            # Device-saturated skip (the device-axis mirror of the cloud skip).
            # A feature past implementation whose only remaining MCP gap is
            # real-device-only assertions (deferred via DEFERRED_REQUIRES_DEVICE.md,
            # no VALIDATED.md yet) cannot be certified on THIS no-device host.
            # Skip it so the queue advances — a real-device host re-opens it
            # (Step 9) to run the deferred scenarios. This applies to cloud too
            # (cloud has no device), but in practice cloud features carry
            # DEFERRED_NON_CLOUD.md and are caught by the cloud skip above first.
            # (Retro unwired: _phases_effectively_complete() replaces the old
            # RETRO_DONE.md precondition.)
            device_deferred = (spec_path / "DEFERRED_REQUIRES_DEVICE.md").exists()
            validated = (spec_path / "VALIDATED.md").exists()
            if device_deferred and not validated and _phases_effectively_complete(spec_path):
                device_saturated_skipped.append(name)
                _DEVICE_DEFERRED.append(name)
                # Per-feature diagnostic on EVERY probe (not only when the queue
                # exhausts) so a lingering In-progress device-deferral is always
                # visible, even when a later feature is dispatched this cycle.
                meta = parse_sentinel(spec_path / "DEFERRED_REQUIRES_DEVICE.md") or {}
                scen = meta.get("deferred_scenarios") or []
                scen_str = ", ".join(str(s) for s in scen) if scen else "(unspecified)"
                _diag(
                    f"device-saturated skipped: {name} — real-device-only "
                    f"assertions deferred [{scen_str}] (DEFERRED_REQUIRES_DEVICE.md); "
                    "re-opens on a real-device /lazy host."
                )
                continue
        if skip_needs_research:
            # Cheap filesystem peek — don't run the full per-feature state machine.
            # Skip features that would terminate the loop with needs-research.
            needs_research_file = spec_path / "NEEDS_RESEARCH.md"
            research_prompt = spec_path / "RESEARCH_PROMPT.md"
            research = spec_path / "RESEARCH.md"
            research_summary = spec_path / "RESEARCH_SUMMARY.md"
            research_pending = (
                needs_research_file.exists()
                or (
                    research_prompt.exists()
                    and not research.exists()
                    and not research_summary.exists()
                )
            )
            if research_pending:
                research_pending_skipped.append(name)
                continue
        # Park-mode: if --park-needs-input is active and this feature has an
        # unresolved NEEDS_INPUT.md, skip (park) it instead of halting the queue.
        # The item re-enters automatically once NEEDS_INPUT.md is resolved/renamed.
        # BLOCKED.md retains precedence: a feature carrying BOTH BLOCKED.md and
        # NEEDS_INPUT.md must still halt as "blocked", not be silently parked.
        if (
            park_needs_input
            and (spec_path / "NEEDS_INPUT.md").exists()
            and not (spec_path / "BLOCKED.md").exists()
        ):
            _PARKED.append(lazy_core.build_parked_entry(feature_id, spec_path / "NEEDS_INPUT.md"))
            _diag(
                f"parked: {name} — unresolved NEEDS_INPUT.md; skipped (park mode). "
                "Re-enters when resolved."
            )
            continue
        current = {
            "name": name,
            "id": feature_id,
            "spec_path": spec_path,
            "tier": entry.get("tier"),
            "queue_entry": entry,
        }
        break

    if current is None:
        if cloud and cloud_saturated_skipped:
            return _state(
                terminal_reason="cloud-queue-exhausted",
                notify_message=(
                    f"Cloud queue exhausted — {len(cloud_saturated_skipped)} feature(s) "
                    "awaiting workstation /lazy for MCP test."
                ),
            )
        if (not real_device) and device_saturated_skipped:
            # Device-axis mirror of cloud-queue-exhausted. The no-device host has
            # done everything it can; the listed features carry deferred
            # real-device-only assertions awaiting a real-device /lazy host.
            # (Per-feature diagnostics were already emitted inline at the skip
            # site above, on every probe — not just here at exhaustion.)
            return _state(
                terminal_reason="device-queue-exhausted",
                notify_message=(
                    f"Device queue exhausted — {len(device_saturated_skipped)} feature(s) "
                    "carry real-device-only assertions deferred to a real-device "
                    "/lazy host (set ALGOBOOTH_REAL_AUDIO_DEVICE=1 or run on native "
                    "hardware)."
                ),
            )
        if skip_needs_research and research_pending_skipped:
            for fname in research_pending_skipped:
                _diag(f"research-pending skipped: {fname}")
            return _state(
                terminal_reason="queue-blocked-on-research",
                notify_message=(
                    f"Queue blocked — {len(research_pending_skipped)} feature(s) "
                    "awaiting Gemini research uploads."
                ),
            )
        # scoped-id-not-found: --feature-id was given but matched no queue entry.
        # This is distinct from "queue exhausted" — the id itself is unknown.
        # Placed here (after all other specific terminals) because when the scope
        # id is a typo none of the skip-lists will have populated.
        if scope_feature_id is not None and not scope_id_seen:
            return _state(
                terminal_reason="scoped-id-not-found",
                notify_message=(
                    f"--feature-id '{scope_feature_id}' matched no entry in "
                    "docs/features/queue.json — check the id (typo?) or that the "
                    "feature is queued. No cycle was dispatched."
                ),
            )
        return _state(
            terminal_reason="all-features-complete",
            notify_message="ALL FEATURES COMPLETE — roadmap finished.",
        )

    feature_name = current["name"]
    feature_id = current["id"]
    spec_path: Path = current["spec_path"]
    spec_path_str = str(spec_path)

    common = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "spec_path": spec_path_str,
    }

    # Step 2.9: upstream WI changed since materialize — halt for re-materialize.
    if lazy_core.read_stale_upstream(spec_path) is not None:
        return _state(
            **common,
            current_step=STEP_STALE_UPSTREAM,
            terminal_reason=TR_STALE_UPSTREAM,
            notify_message=f"STALE UPSTREAM: {feature_name} — upstream WI changed since materialize; re-materialize required.",
        )

    # Step 3: BLOCKED.md
    blocked_file = spec_path / "BLOCKED.md"
    if blocked_file.exists():
        meta = parse_sentinel(blocked_file) or {}
        phase = meta.get("phase", "unknown")
        notify_message = f"BLOCKED: {feature_name} — {phase}. Awaiting input."
        # Validation-escalation payload (Phase 11 WU-1a): blocker_kind
        # mcp-validation at retry_count >= 2 means repeated validation rounds
        # each found one more broken layer (the d8 serial-discovery pattern) —
        # the orchestrator must draft the corrective phase as a full-chain seam
        # audit, not another single-layer fix. The `validation_escalation` key
        # is added ONLY in the escalation case (post-hoc, mirroring the
        # _PARK_MODE "parked" invariant) so non-escalated output — including
        # every existing retry_count: 0 fixture — stays byte-identical.
        escalated = lazy_core.validation_escalation(meta)
        if escalated:
            notify_message += lazy_core.VALIDATION_ESCALATION_SUFFIX
        state = _state(
            **common,
            current_step="Step 3: blocked",
            terminal_reason="blocked",
            notify_message=notify_message,
        )
        if escalated:
            state["validation_escalation"] = True
        return state

    # NEEDS_INPUT.md (batch-mode halt)
    needs_input_file = spec_path / "NEEDS_INPUT.md"
    if needs_input_file.exists():
        meta = parse_sentinel(needs_input_file) or {}
        writer = meta.get("written_by", "<unknown>")
        return _state(
            **common,
            current_step="Step 3.5: needs-input",
            terminal_reason="needs-input",
            notify_message=(
                f"NEEDS INPUT: {feature_name} — {writer} halted on an ambiguous decision."
            ),
        )

    # Step 4: SPEC.md
    spec_file = spec_path / "SPEC.md"
    if not spec_file.exists():
        # Check if directory has any files (research, etc.)
        has_files = spec_path.exists() and any(
            p.is_file() and p.name not in ("BLOCKED.md", "NEEDS_INPUT.md")
            for p in spec_path.iterdir()
        )
        if not has_files:
            return _state(
                **common,
                current_step="Step 4: no SPEC, no research",
                terminal_reason="needs-spec-input",
                notify_message=(
                    f"{feature_name} needs spec input — no SPEC.md or research found. "
                    "Provide direction via /spec."
                ),
            )
        # Ad-hoc enqueue path: an ADHOC_BRIEF.md seed (written by
        # --enqueue-adhoc) routes to /spec with a brief-specific arg so /spec
        # treats it as the task brief rather than "prior research".
        if (spec_path / "ADHOC_BRIEF.md").exists():
            return _state(
                **common,
                current_step="Step 4: ad-hoc brief → spec",
                sub_skill="spec",
                sub_skill_args=(
                    f"{feature_name} — ad-hoc task; see "
                    f"{spec_path_str}/ADHOC_BRIEF.md for the brief"
                ),
            )
        return _state(
            **common,
            current_step="Step 4: SPEC missing, research files present",
            sub_skill="spec",
            sub_skill_args=f"{feature_name} — see {spec_path_str} for prior research",
        )

    spec_text = spec_file.read_text(encoding="utf-8")

    # Step 4.5: Stub spec
    if is_stub_spec(spec_text, current.get("queue_entry")):
        return _state(
            **common,
            current_step="Step 4.5: stub-spec detected",
            sub_skill="spec",
            sub_skill_args=(
                f"{feature_name} — existing stub at {spec_path_str}/SPEC.md is auto-generated "
                "from research summary; treat as starting context for Phase 1 brainstorming "
                "and overwrite when baseline is locked in"
            ),
        )

    # Step 4.6: upstream realign check
    deps = parse_dep_block(spec_text)
    hard_complete_upstream_dirs: list[Path] = []
    for dep in deps:
        if dep["kind"] != "hard":
            continue
        ud = resolve_upstream_dir(repo_root, spec_path, dep["feature_id"])
        if ud is None:
            continue
        if upstream_is_complete(repo_root, ud):
            hard_complete_upstream_dirs.append(ud)

    if hard_complete_upstream_dirs and not realign_is_fresh(spec_path, hard_complete_upstream_dirs):
        return _state(
            **common,
            current_step="Step 4.6: upstream realign needed",
            sub_skill="realign-spec",
            # --apply pushes the act-on-recommendation logic into /realign-spec
            # itself so the orchestrator subagent doesn't need follow-on logic.
            sub_skill_args=f"{spec_path_str}/SPEC.md --apply",
        )

    # Step 5: Research validation gate
    research = spec_path / "RESEARCH.md"
    research_summary = spec_path / "RESEARCH_SUMMARY.md"
    research_prompt = spec_path / "RESEARCH_PROMPT.md"
    needs_research_file = spec_path / "NEEDS_RESEARCH.md"

    if not research.exists() and not research_summary.exists():
        # Persistent halt: if a NEEDS_RESEARCH sentinel is already present, the
        # orchestrator already dropped one in a prior cycle — surface and stop.
        if needs_research_file.exists():
            meta = parse_sentinel(needs_research_file) or {}
            prompt_rel = meta.get("research_prompt_path", "RESEARCH_PROMPT.md")
            return _state(
                **common,
                current_step="Step 5: needs-research (persistent)",
                terminal_reason="needs-research",
                notify_message=(
                    f"{feature_name}: research prompt exists at {prompt_rel} but no RESEARCH.md. "
                    "Run Gemini deep research and drop RESEARCH.md next to the prompt."
                ),
            )
        if research_prompt.exists():
            # Tell orchestrator to halt and (for batch orchestrators) write NEEDS_RESEARCH.md
            return _state(
                **common,
                current_step="Step 5: prompt exists, awaiting research",
                terminal_reason="needs-research",
                notify_message=(
                    f"{feature_name}: research prompt exists but no results. "
                    "Run Gemini deep research and provide results to /spec."
                ),
            )
        # No research at all → /spec Phase 2 (research prompt generation)
        return _state(
            **common,
            current_step="Step 5: generate research prompt",
            sub_skill="spec",
            sub_skill_args=(
                f"{feature_name} — SPEC.md already exists at {spec_path_str}/SPEC.md, "
                "skip to Phase 2 (research prompt generation)"
            ),
        )

    if research.exists() and not research_summary.exists():
        return _state(
            **common,
            current_step="Step 5: integrate research",
            sub_skill="spec",
            sub_skill_args=(
                f"{feature_name} — SPEC.md and RESEARCH.md exist at {spec_path_str}, "
                "skip to Phase 3 (integrate research and finalize spec)"
            ),
        )

    # Step 6: PHASES.md
    phases_file = spec_path / "PHASES.md"
    if not phases_file.exists():
        # Consolidated planning: dispatch /plan-feature (which runs /spec-phases
        # THEN /write-plan back-to-back) instead of /spec-phases alone. This
        # collapses the two planning cycles into one orchestrator round-trip —
        # the next probe sees PHASES.md + a plan on disk and routes straight to
        # /execute-plan, skipping the separate Step 7a write-plan dispatch.
        #
        # /plan-feature's hard precondition (SPEC.md + RESEARCH_SUMMARY.md both
        # present) is GUARANTEED here: the research gates above (the
        # `not research and not research_summary` and `research and not
        # research_summary` branches) make RESEARCH_SUMMARY.md a precondition of
        # ever reaching Step 6, so /plan-feature can never refuse on a missing
        # summary at this node. /plan-feature surfaces any NEEDS_INPUT.md its
        # sub-skills write (genuine design forks) and STOPs; the next probe sees
        # the sentinel and routes to needs-input as before. Step 7a (write-plan)
        # remains the fallback for a feature whose PHASES.md exists but has no
        # plan yet (e.g. after a NEEDS_INPUT resolution that neutralized the
        # sentinel write-plan halted on).
        return _state(
            **common,
            current_step="Step 6: plan feature (phases + plan)",
            sub_skill="plan-feature",
            sub_skill_args=f"{spec_path_str}/SPEC.md",
        )

    phases_text = phases_file.read_text(encoding="utf-8")
    unchecked, checked = count_deliverables(phases_text)

    # Step 7: Phase completion
    if unchecked > 0:
        plans = find_implementation_plans(spec_path)
        if not plans and _has_any_complete_plan(spec_path) and (
            cloud or remaining_unchecked_are_verification_only(phases_text)
        ):
            # All implementation plans are Complete; remaining PHASES.md
            # unchecked rows are workstation-only (e.g. per-phase Runtime
            # Verification / MCP-assertion subsections ticked at MCP test
            # time).
            #
            # Cloud: always bypass — cloud can't tick any workstation row, so
            # fall through to Step 9 (cloud defers or honors an existing
            # DEFERRED_NON_CLOUD.md), and Step 2's cloud-saturated skip
            # eventually fires.
            #
            # Workstation: bypass ONLY when the unchecked remainder is entirely
            # verification rows. Workstation CAN run those checks, so falling
            # through reaches Step 9 /mcp-test (the dispatch that actually ticks
            # them). If any real implementation row is still unchecked we skip
            # this branch and write-plan as before.
            pass
        elif not plans:
            return _state(
                **common,
                current_step="Step 7a: write plan",
                sub_skill="write-plan",
                sub_skill_args=f"{spec_path_str}/PHASES.md",
            )
        else:
            # Use the lowest-ordered plan (sorted-name preference); if part-N
            # exists, this returns part-1 first which is what we want.
            plan = plans[0]
            # Stale-plan gate (all modes). When every work-unit referenced by
            # this plan's phases: scope is already checked ([x]) in PHASES.md,
            # the plan is stale — its work was completed in a prior session but
            # the plan's frontmatter was never flipped to Complete. Dispatching
            # /execute-plan in this state wastes an Opus cycle re-verifying work
            # that is already done (observed twice in production). Instead, flip
            # the plan Complete inline via the __flip_plan_complete_stale__
            # pseudo-action. The non-empty plan_phase_set guard is required: a
            # plan with no phases: field has an empty scope and must fall through
            # to execute-plan (its full scope is unknown so we cannot declare it
            # stale). This check runs before the cloud-saturation gate so a
            # fully-checked scope always flips stale regardless of cloud mode.
            plan_phase_set = _plan_phase_set(plan)
            if plan_phase_set:
                in_scope_unchecked = _unchecked_wus_in_plan_scope(
                    phases_text, plan_phase_set
                )
                # Phase 8 (lazy-validation-readiness) — close the /execute-plan
                # finalization gap, option (b). A plan is "finalize-stale" when,
                # within its phase scope, the only remaining-open WUs are
                # Step-9-owned Runtime-Verification rows (the impl is done; only
                # the verification subsections the MCP cycle ticks remain). The
                # plan's frontmatter is still Ready/In-progress, so without this
                # branch lazy-state re-dispatches a full /execute-plan cycle that
                # does nothing but flip the plan to Complete (d7-multi-timbral
                # Phase 11: cycle 33 ticked everything, cycle 34 burned ~97k tok
                # just to flip the status). Routing those cases to the existing
                # __flip_plan_complete_stale__ pseudo-action makes the state
                # machine self-correct regardless of which /execute-plan revision
                # ran (more robust than tightening the skill prose alone — the
                # rejected option (a); see PHASES.md Implementation Notes).
                #
                # Two finalize-stale shapes, both routed to the pseudo-action:
                #   (1) ZERO in-scope unchecked WUs (the original stale-plan
                #       gate — every referenced WU is already [x]).
                #   (2) The in-scope unchecked remainder is ENTIRELY
                #       verification-only rows (the Phase-8 addition). We scope
                #       PHASES.md down to the plan's phases and reuse the
                #       verification-only predicate so a genuine implementation
                #       row in scope still falls through to /execute-plan.
                scoped_text = _phases_text_scoped_to(phases_text, plan_phase_set)
                finalize_stale = (
                    not in_scope_unchecked
                    or remaining_unchecked_are_verification_only(scoped_text)
                )
                if finalize_stale:
                    # Stale already-applied plan: every implementation WU this plan
                    # references (scoped to its phases: field) is already [x] — only
                    # Step-9 verification rows (if any) remain — yet its frontmatter is
                    # still Ready/In-progress and PHASES.md still has unchecked rows
                    # elsewhere so we reached this branch. Dispatching /execute-plan
                    # would burn an Opus cycle re-verifying a plan whose work is already
                    # done (observed in production). Flip it Complete inline via the
                    # __flip_plan_complete_stale__ pseudo-action instead.
                    return _state(
                        **common,
                        current_step="Step 7a: flip plan Complete (stale — all referenced implementation deliverables already checked)",
                        sub_skill="__flip_plan_complete_stale__",
                        sub_skill_args=str(plan),
                    )
            # Cloud-saturation gate (cloud mode only). When a plan is
            # In-progress because the only unchecked WUs in its phase scope
            # are explicitly documented in DEFERRED_NON_CLOUD.md as
            # workstation-only, flipping the plan to Complete in-place is the
            # documented exit. The orchestrator handles this pseudo-skill
            # inline (Step 1c.5) — no execute-plan dispatch needed. This
            # prevents the loop where execute-plan repeatedly diagnoses "no
            # cloud work" and reports a no-op without advancing.
            if cloud and _plan_status(plan) == "In-progress" and \
                    _plan_cloud_saturated(plan, phases_text, spec_path):
                return _state(
                    **common,
                    current_step="Step 7a: flip plan Complete (cloud-saturated)",
                    sub_skill="__flip_plan_complete_cloud_saturated__",
                    sub_skill_args=str(plan),
                )
            return _state(
                **common,
                current_step="Step 7a: execute plan",
                sub_skill="execute-plan",
                sub_skill_args=str(plan),
            )

    # Phases complete — order: Step 9 (MCP gate) → Step 10 (mark complete).
    #
    # RETRO UNWIRED (operator decision, 2026-06): the Step 8 /retro phase has
    # been removed from the pipeline. The retro gate proved low-yield (a
    # docs/design-alignment audit that structurally can't see the runtime
    # defects /mcp-test catches) while costing a full Opus dispatch per feature.
    # Once all phases are Complete, the pipeline now routes DIRECTLY to the MCP
    # validation gate (Step 9) — the state previously reached only after
    # RETRO_DONE.md existed is now reached as soon as execute-plan finalization
    # is done. Git history is the restore path; /retro-feature SKILL remains in
    # place. The now-inert retro_staleness()/phase_kind parsing is left dormant
    # (harmless, aids a future restore); nothing gates on it anymore — see the
    # __mark_complete__ backstop note in lazy_core.apply_pseudo.

    validated_file = spec_path / "VALIDATED.md"
    skip_mcp_file = spec_path / "SKIP_MCP_TEST.md"
    deferred_file = spec_path / "DEFERRED_NON_CLOUD.md"
    mcp_results_file = spec_path / "MCP_TEST_RESULTS.md"

    # Step 9-pre: device-deferral re-open / guard. A feature carrying
    # DEFERRED_REQUIRES_DEVICE.md has real-device-only MCP assertions that a
    # prior no-device /mcp-test could not certify (e.g. sustained zero-dropout
    # under the HeadlessPumpDriver). This is keyed on the device axis, NOT the
    # cloud axis, and is checked BEFORE the cloud/workstation split so it
    # governs both.
    #
    # The sentinel's MERE PRESENCE blocks completion — we deliberately do NOT
    # require `not VALIDATED.md` here. The contract is that a real-device
    # /mcp-test DELETES this sentinel on success; so if a VALIDATED.md and this
    # sentinel coexist, the re-open's cleanup did not happen (a race / aborted
    # run). Rather than letting that stray VALIDATED.md flip the feature Complete
    # — leaving Complete + a deferral sentinel, the `complete-not-device-deferred`
    # lint contradiction — we re-fire the re-open on a real-device host (mcp-test
    # is idempotent: it re-certifies the deferred scenarios and deletes the
    # sentinel, self-healing the state). The completion-integrity gate enforces
    # the same invariant a second time at flip time (refuses while the sentinel
    # is present).
    #
    # The deferral ALSO takes precedence over a SKIP_MCP_TEST.md — we do NOT
    # require `not skip_mcp`. A feature can legitimately carry BOTH (some
    # assertions any-host-untestable → skip; one real-device-only → deferral);
    # the deferral must still gate completion until a real-device run certifies
    # its scenarios, even though the skip alone would otherwise validate-and-
    # complete. Once the deferral is cleared (sentinel deleted), the residual
    # skip resumes its normal `__write_validated_from_skip__` path.
    device_deferred_file = spec_path / "DEFERRED_REQUIRES_DEVICE.md"
    if device_deferred_file.exists():
        if real_device:
            # RE-OPEN — the inverse the framework previously lacked. On a
            # real-device host, route back to /mcp-test scoped to the deferred
            # scenario set so the hardware-clock-driven assertions get a real
            # certification. /mcp-test certifies them, DELETES this sentinel, and
            # writes VALIDATED.md; the next probe reaches Step 10 mark-complete.
            meta = parse_sentinel(device_deferred_file) or {}
            scenarios = meta.get("deferred_scenarios") or []
            scen_str = (
                ", ".join(str(s) for s in scenarios)
                if scenarios else "(see DEFERRED_REQUIRES_DEVICE.md)"
            )
            return _state(
                **common,
                current_step="Step 9: re-open device-deferred scenarios (real-device host)",
                sub_skill="mcp-test",
                sub_skill_args=(
                    f"re-validate {feature_name} deferred real-device assertions "
                    f"[{scen_str}] on THIS real-device host — see "
                    f"{spec_path_str}/DEFERRED_REQUIRES_DEVICE.md. On pass, delete "
                    "that sentinel and write VALIDATED.md; on a genuine failure "
                    "treat it as a real bug (BLOCKED.md), not an environment skip."
                ),
            )
        # No-device host: the feature is device-saturated. Step 2's
        # device-saturated skip catches this before Step 9, so this is a
        # defensive guard ensuring a no-device host NEVER re-dispatches /mcp-test
        # for an already-deferred scenario set (which would no-op-loop). Surface
        # the same device-queue terminal.
        return _state(
            **common,
            current_step="Step 9: device-deferred (no real device on this host)",
            terminal_reason="device-queue-exhausted",
            notify_message=(
                f"{feature_name}: real-device-only assertions are deferred and "
                "cannot be certified here. Awaiting a real-device /lazy host "
                "(set ALGOBOOTH_REAL_AUDIO_DEVICE=1 or run on native hardware)."
            ),
        )

    # Step 9: MCP gate (validate runtime).
    # Cloud defers via DEFERRED_NON_CLOUD.md; workstation runs the tests.
    if cloud:
        if not validated_file.exists() and not skip_mcp_file.exists() and not deferred_file.exists():
            # Cloud halts at Step 9 — defer to workstation. Orchestrator writes
            # the DEFERRED_NON_CLOUD.md sentinel; next cycle either completes
            # (if workstation has since produced VALIDATED.md) or hits the
            # Step 2 cloud-saturated skip.
            return _state(
                **common,
                current_step="Step 9: cloud defers MCP test",
                sub_skill="__write_deferred_non_cloud__",
                sub_skill_args=spec_path_str,
            )
        # SKIP_MCP_TEST.md from a prior workstation assessment → write VALIDATED.md
        if skip_mcp_file.exists() and not validated_file.exists():
            # Provenance gate (skip_waiver_refusal): a pipeline-self-granted
            # skip, a pipeline-authored skip with NO granted_by field, or an
            # mcp-test grant missing its spec_class citation must NOT vacuously
            # validate — the pipeline cannot waive its own MCP requirement.
            # Accepted: operator grants, legacy no-provenance files, and
            # mcp-test grants carrying a spec_class citation.
            _skip_refusal = skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {})
            if _skip_refusal:
                return _state(
                    **common,
                    current_step="Step 9: pipeline-granted skip needs operator confirmation",
                    terminal_reason="needs-input",
                    notify_message=(
                        f"{feature_name}: SKIP_MCP_TEST.md {_skip_refusal}"
                    ),
                )
            return _state(
                **common,
                current_step="Step 9: skip-mcp-test → validated",
                sub_skill="__write_validated_from_skip__",
                sub_skill_args=spec_path_str,
            )
    else:
        # Workstation Step 9: run MCP tests (or use existing results / skip marker).
        if not validated_file.exists():
            if skip_mcp_file.exists():
                # Provenance gate (skip_waiver_refusal): a pipeline-self-granted
                # skip, a pipeline-authored skip with NO granted_by field, or an
                # mcp-test grant missing its spec_class citation must NOT
                # vacuously validate. Accepted: operator grants, legacy
                # no-provenance files, mcp-test grants with a spec_class citation.
                _skip_refusal = skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {})
                if _skip_refusal:
                    return _state(
                        **common,
                        current_step="Step 9: pipeline-granted skip needs operator confirmation",
                        terminal_reason="needs-input",
                        notify_message=(
                            f"{feature_name}: SKIP_MCP_TEST.md {_skip_refusal}"
                        ),
                    )
                return _state(
                    **common,
                    current_step="Step 9: skip-mcp-test → validated",
                    sub_skill="__write_validated_from_skip__",
                    sub_skill_args=spec_path_str,
                )
            # 100%-passing results already on disk?
            if mcp_results_file.exists():
                meta = parse_sentinel(mcp_results_file) or {}
                if meta.get("result") == "all-passing":
                    # Freshness gate: ensure the results were validated against the
                    # CURRENT HEAD commit, not a stale one. If validated_commit is
                    # present and doesn't match HEAD, the results are stale and we
                    # must re-run MCP tests against the current code before writing
                    # VALIDATED.md. When _current_head returns None (not a git repo)
                    # or validated_commit is absent (legacy results), skip the check
                    # and fall through to the existing write-validated path.
                    head = _current_head(repo_root)
                    validated_commit = meta.get("validated_commit")
                    if head and validated_commit and str(validated_commit) != head:
                        # Stale results validated an older commit — must NOT validate
                        # current code. Re-verify by re-running MCP tests against HEAD.
                        return _state(
                            **common,
                            current_step="Step 9: stale MCP results — re-verify",
                            sub_skill="mcp-test",
                            sub_skill_args=(
                                f"re-validate {feature_name} — MCP_TEST_RESULTS.md was "
                                f"validated against a stale commit; see {spec_path_str}/SPEC.md"
                            ),
                        )
                    return _state(
                        **common,
                        current_step="Step 9b: write validated",
                        sub_skill="__write_validated_from_results__",
                        sub_skill_args=spec_path_str,
                    )
            # Run MCP tests
            return _state(
                **common,
                current_step="Step 9: run MCP tests",
                sub_skill="mcp-test",
                sub_skill_args=f"validate {feature_name} — see {spec_path_str}/SPEC.md",
            )

    # Step 10: Mark complete.
    # Entry: VALIDATED.md OR (cloud AND DEFERRED_NON_CLOUD.md). (Retro is
    # unwired — there is no longer a RETRO_DONE.md precondition.)
    entry_ok = validated_file.exists() or (cloud and deferred_file.exists())
    if not entry_ok:
        # No entry — should be unreachable: Step 9 either wrote validated /
        # deferred or dispatched mcp-test. Defensive.
        # Write a durable NEEDS_INPUT.md so the orchestrator's Step 1g
        # decision-resume can surface the issue to the operator.
        _write_step10_needs_input(spec_path, feature_name)
        return _state(
            **common,
            current_step="Step 10: unexpected state",
            sub_skill=None,
            terminal_reason="needs-input",
            notify_message=(
                f"{feature_name}: unexpected state at Step 10 — phases complete "
                "but no VALIDATED.md, SKIP_MCP_TEST.md, or DEFERRED_NON_CLOUD.md. "
                "Manual review needed."
            ),
        )

    # Cloud cannot finalize without VALIDATED.md — Step 2's cloud-saturated
    # skip normally catches this earlier (DEFERRED_NON_CLOUD.md + no
    # VALIDATED.md), but defensively halt here too.
    if cloud and not validated_file.exists():
        return _state(
            **common,
            current_step="Step 10a: cloud halt",
            terminal_reason="cloud-queue-exhausted",
            notify_message=(
                f"{feature_name}: cloud work complete (phases). "
                "Awaiting workstation /lazy for deferred MCP test."
            ),
        )

    # Mark complete via the orchestrator's __mark_complete__ pseudo-skill
    # (ROADMAP edit + sentinel cleanup + commit).
    return _state(
        **common,
        current_step="Step 10: mark complete",
        sub_skill="__mark_complete__",
        sub_skill_args=spec_path_str,
    )


# ---------------------------------------------------------------------------
# Fixture smoke tests
# ---------------------------------------------------------------------------

def _write_yaml_sentinel(path: Path, kind: str, **fields: Any) -> None:
    fm = {"kind": kind, **fields}
    body = "---\n" + yaml.safe_dump(fm, sort_keys=False).strip() + "\n---\n\n# Sentinel\n"
    path.write_text(body, encoding="utf-8")


def _build_fixture(tmpdir: Path, name: str) -> Path:
    """Build one of the named fixtures under tmpdir/<name>/ and return its repo root."""
    root = tmpdir / name
    features = root / "docs" / "features"
    if (features / "queue.json").exists():
        # Idempotent: fixture already materialized in this temp dir (some smoke
        # cases run the same fixture under different flag combinations).
        return root
    features.mkdir(parents=True, exist_ok=True)

    if name == "fresh-queue":
        # First feature has no SPEC, no research, no files
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-a", "name": "Feature A", "spec_dir": "feat-a", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        (features / "feat-a").mkdir()
    elif name == "blocker":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-b", "name": "Feature B", "spec_dir": "feat-b", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fdir = features / "feat-b"
        fdir.mkdir()
        (fdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            fdir / "BLOCKED.md", "blocked",
            feature_id="feat-b", phase="MCP Validation",
            blocked_at="2026-05-19T12:00:00Z", retry_count=0,
        )
    elif name == "mid-implementation":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fdir = features / "feat-c"
        fdir.mkdir()
        (fdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (fdir / "RESEARCH.md").write_text("# Research\n")
        (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n")
        (fdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n"
        )
        (fdir / "plans").mkdir()
        (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n")
    elif name == "cloud-saturated":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-d", "name": "Feature D", "spec_dir": "feat-d", "tier": 1},
                {"id": "feat-e", "name": "Feature E", "spec_dir": "feat-e", "tier": 2},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        d = features / "feat-d"
        d.mkdir()
        (d / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (d / "RESEARCH.md").write_text("# R\n")
        (d / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (d / "PHASES.md").write_text("# P\n\n- [x] Done\n")
        _write_yaml_sentinel(
            d / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-d", deferred_step=8, reason="cloud limitation",
            deferred_by="lazy-cloud", date="2026-05-19",
        )
        _write_yaml_sentinel(
            d / "RETRO_DONE.md", "retro-done",
            feature_id="feat-d", date="2026-05-19",
            rounds=1, retro_plans=["retro-1-feat-d.md"],
            mcp_validation_status="deferred-to-workstation",
        )
        # Feature E: empty spec dir → will be picked up next
        e = features / "feat-e"
        e.mkdir()
    elif name == "cloud-workstation-only-remainder":
        # All implementation plans Complete, PHASES.md still has unchecked
        # workstation-only rows (Runtime Verification), no DEFERRED_NON_CLOUD.md
        # yet. Cloud Step 7 must bypass to Step 8 (write deferred sentinel)
        # rather than looping on write-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-cw", "name": "Feature CW", "spec_dir": "feat-cw", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        cw = features / "feat-cw"
        cw.mkdir()
        (cw / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (cw / "RESEARCH.md").write_text("# R\n")
        (cw / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (cw / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = cw / "plans"
        plans.mkdir()
        (plans / "all-phases-cw.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-cw\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "cloud-workstation-only-with-deferred":
        # Same shape as cloud-workstation-only-remainder, but DEFERRED_NON_CLOUD.md
        # already on disk. Retro unwired: Step 2's cloud-saturated skip fires
        # (DEFERRED_NON_CLOUD.md + no VALIDATED.md) → cloud-queue-exhausted.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-cwd", "name": "Feature CWD", "spec_dir": "feat-cwd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        cwd = features / "feat-cwd"
        cwd.mkdir()
        (cwd / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (cwd / "RESEARCH.md").write_text("# R\n")
        (cwd / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (cwd / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = cwd / "plans"
        plans.mkdir()
        (plans / "all-phases-cwd.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-cwd\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
        _write_yaml_sentinel(
            cwd / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-cwd", deferred_step=8, reason="workstation MCP test",
            deferred_by="lazy-cloud", date="2026-05-19",
        )
    elif name == "workstation-all-plans-complete-phases-unchecked":
        # Workstation MCP-gate bypass: all impl plans Complete and the only
        # unchecked PHASES.md rows are workstation-only Runtime Verification
        # rows. Workstation can run those checks, so /lazy must fall through to
        # the MCP gate. Retro unwired → Step 9 mcp-test dispatches directly.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wapcpu", "name": "Feature WAPCPU",
                 "spec_dir": "feat-wapcpu", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wapcpu"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-w.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wapcpu\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "workstation-verification-only-retro-done":
        # Workstation bypass with a stale RETRO_DONE.md on disk (left over from
        # an in-flight feature; retro is unwired). RETRO_DONE.md is now ignored
        # for routing — the fall-through reaches Step 9 → mcp-test directly (the
        # dispatch that ticks the deferred Runtime Verification rows).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wvrd", "name": "Feature WVRD",
                 "spec_dir": "feat-wvrd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wvrd"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-wvrd.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wvrd\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
        _write_yaml_sentinel(
            w / "RETRO_DONE.md", "retro-done",
            feature_id="feat-wvrd", date="2026-05-22",
            rounds=1, retro_plans=["retro-1-feat-wvrd.md"],
            mcp_validation_status="pending",
        )
    elif name == "workstation-verification-only-bold-marker":
        # Bold-marker format (the real AlgoBooth PHASES.md style) rather than
        # `### Runtime Verification` headings. Locks in that the detector
        # handles `**Runtime Verification**` / `**MCP Integration Test
        # Assertions:**`. All impl plans Complete → bypass → Step 9 mcp-test
        # (retro unwired).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wbold", "name": "Feature WBOLD",
                 "spec_dir": "feat-wbold", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wbold"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Implement the thing\n\n"
            "**Runtime Verification** (workstation-only):\n\n"
            "- [ ] Live MCP smoke test passes\n\n"
            "**MCP Integration Test Assertions:**\n\n"
            "```\n- [ ] assertion one holds\n```\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-wbold.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wbold\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "workstation-all-plans-complete-real-unchecked":
        # NEGATIVE case: all impl plans Complete, but a remaining unchecked row
        # is a genuine implementation deliverable (NOT under a verification
        # subsection). Bypass must NOT fire — workstation keeps emitting
        # write-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wreal", "name": "Feature WREAL",
                 "spec_dir": "feat-wreal", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wreal"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n"
            "- [ ] Real implementation deliverable still pending\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-wreal.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wreal\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "superseded-phase-unchecked":
        # All impl plans Complete. PHASES.md has one In-progress phase whose only
        # unchecked rows are under **Runtime Verification:**, PLUS a Superseded
        # phase with plain unchecked deliverable rows. The bypass must fire (True)
        # because the Superseded phase's boxes are out-of-scope and the only
        # remaining In-progress unchecked rows are verification-only.
        # Expected: Step 8 retro (bypass fires → no write-plan loop).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sup", "name": "Feature SUP",
                 "spec_dir": "feat-sup", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-sup"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 9 is In-progress with only verification-only unchecked rows.
        # Phase 10 is Superseded with plain unchecked deliverable rows — these
        # must be ignored by remaining_unchecked_are_verification_only.
        (w / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 9: Realignment MCP tests\n\n"
            "**Status:** In-progress\n\n"
            "**Deliverables:**\n\n"
            "- [x] Scenario document authored\n\n"
            "**Runtime Verification:**\n\n"
            "- [ ] Workstation: /mcp-test passes\n\n"
            "---\n\n"
            "### Phase 10: Replay stages\n\n"
            "**Status:** Superseded\n\n"
            "> Superseded into successor-feature.\n\n"
            "**Deliverables:**\n\n"
            "- [ ] Extend the ledger with orbit_gain field\n"
            "- [ ] Implement stage 3 replay\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-sup.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-sup\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [9]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "cloud-saturated-in-progress-plan":
        # In-progress plan whose only unchecked WU is documented in
        # DEFERRED_NON_CLOUD.md as workstation-only. Cloud Step 7a should emit
        # __flip_plan_complete_cloud_saturated__ rather than execute-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-cs", "name": "Feature CS",
                 "spec_dir": "feat-cs", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        cs = features / "feat-cs"
        cs.mkdir()
        (cs / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (cs / "RESEARCH.md").write_text("# R\n")
        (cs / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (cs / "PHASES.md").write_text(
            "# Phases\n\n### Phase 6\n"
            "- [x] WU1 cloud-runnable deliverable A\n"
            "- [x] WU2 cloud-runnable deliverable B\n"
            "- [x] WU3 cloud-runnable deliverable C\n"
            "- [x] WU4 cloud-runnable deliverable D\n"
            "- [ ] WU5 promote SPEC to Complete via workstation MCP\n"
        )
        plans = cs / "plans"
        plans.mkdir()
        (plans / "part-6.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-cs\n"
            "status: In-progress\ncreated: 2026-05-01\nphases: [6]\n---\n\n"
            "# Plan part 6\n"
        )
        _write_yaml_sentinel(
            cs / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-cs", deferred_step=8,
            reason="workstation MCP gate",
            deferred_by="lazy-cloud", date="2026-05-22",
        )
        # Append a body block enumerating the workstation-only WU so the
        # substring saturation check matches.
        with (cs / "DEFERRED_NON_CLOUD.md").open("a", encoding="utf-8") as fh:
            fh.write("\nDeferred WUs:\n- WU5 promote SPEC to Complete via workstation MCP\n")
    elif name == "cloud-in-progress-plan-not-saturated":
        # In-progress plan with unchecked WUs NOT documented in
        # DEFERRED_NON_CLOUD.md → must NOT auto-flip; must dispatch
        # execute-plan as usual.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-csn", "name": "Feature CSN",
                 "spec_dir": "feat-csn", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        csn = features / "feat-csn"
        csn.mkdir()
        (csn / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (csn / "RESEARCH.md").write_text("# R\n")
        (csn / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (csn / "PHASES.md").write_text(
            "# Phases\n\n### Phase 6\n"
            "- [x] WU1 done\n"
            "- [ ] WU2 still actual cloud work\n"
        )
        plans = csn / "plans"
        plans.mkdir()
        (plans / "part-6.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-csn\n"
            "status: In-progress\ncreated: 2026-05-01\nphases: [6]\n---\n\n"
            "# Plan part 6\n"
        )
        _write_yaml_sentinel(
            csn / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-csn", deferred_step=8,
            reason="workstation MCP gate",
            deferred_by="lazy-cloud", date="2026-05-22",
        )
        # NOTE: DEFERRED_NON_CLOUD.md body does NOT mention WU2 — gate
        # must NOT fire.
    elif name == "workstation-in-progress-plan-with-deferred":
        # Same shape as cloud-saturated-in-progress-plan but workstation. The
        # gate is cloud-only — workstation should keep dispatching execute-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wcs", "name": "Feature WCS",
                 "spec_dir": "feat-wcs", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wcs"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 6\n"
            "- [x] WU1 done\n"
            "- [ ] WU5 workstation gate\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "part-6.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wcs\n"
            "status: In-progress\ncreated: 2026-05-01\nphases: [6]\n---\n\n"
            "# Plan part 6\n"
        )
        _write_yaml_sentinel(
            w / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-wcs", deferred_step=8,
            reason="workstation MCP gate",
            deferred_by="lazy-cloud", date="2026-05-22",
        )
        with (w / "DEFERRED_NON_CLOUD.md").open("a", encoding="utf-8") as fh:
            fh.write("\nDeferred WUs:\n- WU5 workstation gate\n")
    elif name == "all-complete":
        # ROADMAP strikethrough+COMPLETE fallback AND a COMPLETED.md receipt →
        # genuinely done, queue exhausts to all-features-complete.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-f", "name": "Feature F", "spec_dir": "feat-f", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n- ~~Feature F — done~~ **COMPLETE**\n"
        )
        f = features / "feat-f"
        f.mkdir()
        _write_yaml_sentinel(
            f / "COMPLETED.md", "completed",
            feature_id="feat-f", date="2026-05-19", provenance="gated",
        )
    elif name == "needs-research":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-g", "name": "Feature G", "spec_dir": "feat-g", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        g = features / "feat-g"
        g.mkdir()
        (g / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (g / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "stub-pre-gemini-marker":
        # Canonical pre-Gemini stub: SPEC carries the `> Draft (pre-Gemini)`
        # trailer, queue.json has no `stub` field. Step 4.5 should fire.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stub-marker", "name": "Stub Marker",
                 "spec_dir": "feat-stub-marker", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sdir = features / "feat-stub-marker"
        sdir.mkdir()
        (sdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n\n"
            "> Draft (pre-Gemini). Open questions in this spec are captured "
            "in RESEARCH_PROMPT.md and will be addressed by the upcoming "
            "manual Gemini deep-research sprint.\n"
        )
        (sdir / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "stub-queue-flag-only":
        # queue.json `"stub": true` cross-check fires Step 4.5 even when the
        # SPEC body has no stub marker (belt-and-suspenders per docs/CLAUDE.md).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stub-queue", "name": "Stub Queue",
                 "spec_dir": "feat-stub-queue", "tier": 1, "stub": True}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sdir = features / "feat-stub-queue"
        sdir.mkdir()
        (sdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (sdir / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "spec-status-complete":
        # SPEC.md Status: Complete WITH a COMPLETED.md receipt → genuinely done
        # even when the ROADMAP grep wouldn't match (no strikethrough/COMPLETE).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-i", "name": "Feature I", "spec_dir": "feat-i", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n\n- Feature I — still listed without COMPLETE token\n")
        idir = features / "feat-i"
        idir.mkdir()
        (idir / "SPEC.md").write_text("# Spec\n\n**Status:** Complete\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            idir / "COMPLETED.md", "completed",
            feature_id="feat-i", date="2026-05-19", provenance="gated",
        )
    elif name == "complete-no-receipt":
        # FM1: SPEC.md Status: Complete but NO COMPLETED.md receipt → flipped
        # outside the gate → completion-unverified hard-halt.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-nr", "name": "Feature NR", "spec_dir": "feat-nr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        nr = features / "feat-nr"
        nr.mkdir()
        (nr / "SPEC.md").write_text("# Spec\n\n**Status:** Complete\n\n**Depends on:** (none)\n")
    elif name == "superseded-no-receipt":
        # Superseded is exempt from the receipt requirement (retired, never
        # validated) → skipped, queue exhausts to all-features-complete.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sup", "name": "Feature SUP", "spec_dir": "feat-sup", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sup = features / "feat-sup"
        sup.mkdir()
        (sup / "SPEC.md").write_text("# Spec\n\n**Status:** Superseded\n\n**Depends on:** (none)\n")
    elif name == "dangling-queue-entry":
        # FM3: queue entry whose spec_dir does not exist on disk → skipped with
        # a diagnostic; queue exhausts to all-features-complete (not dispatched).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "ghost", "name": "Ghost Feature", "spec_dir": "ghost", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        # NOTE: deliberately do NOT create features/ghost/
    elif name == "plan-frontmatter-filter":
        # Three plans in plans/. One Complete (filtered), one with phases: [3],
        # one with phases: [4]. Expectation: lowest phase among non-Complete
        # plans is selected.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-j", "name": "Feature J", "spec_dir": "feat-j", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        jdir = features / "feat-j"
        jdir.mkdir()
        (jdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (jdir / "RESEARCH.md").write_text("# R\n")
        (jdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (jdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 3\n- [ ] Thing A\n\n### Phase 4\n- [ ] Thing B\n"
        )
        plans = jdir / "plans"
        plans.mkdir()
        # Complete plan (should be filtered)
        (plans / "all-phases-old.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-j\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1, 2]\n---\n\n"
            "# Plan (already complete)\n"
        )
        # Phase 4 plan (Ready, but later phase number)
        (plans / "all-phases-later.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-j\n"
            "status: Ready\ncreated: 2026-05-10\nphases: [4]\n---\n\n"
            "# Plan (phase 4)\n"
        )
        # Phase 3 plan (Ready, lowest phase number — expected pick)
        (plans / "phase-3-corrective.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-j\n"
            "status: Ready\ncreated: 2026-05-15\nphases: [3]\n---\n\n"
            "# Plan (phase 3)\n"
        )
    elif name == "legacy-plan-diagnostics":
        # Plan file with no frontmatter — should be included but raise a
        # diagnostics warning.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-k", "name": "Feature K", "spec_dir": "feat-k", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        kdir = features / "feat-k"
        kdir.mkdir()
        (kdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (kdir / "RESEARCH.md").write_text("# R\n")
        (kdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (kdir / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [ ] T\n")
        plans = kdir / "plans"
        plans.mkdir()
        # Legacy plan — no frontmatter
        (plans / "all-phases-legacy.md").write_text("# Legacy plan\n\nNo frontmatter here.\n")
    elif name == "research-pending-skip":
        # Queue: feat-a (research prompt only — would terminate on needs-research),
        # feat-b (ready to plan — SPEC/RESEARCH/RESEARCH_SUMMARY all present, no PHASES).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-a", "name": "Feature A", "spec_dir": "feat-a", "tier": 1},
                {"id": "feat-b", "name": "Feature B", "spec_dir": "feat-b", "tier": 2},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        a = features / "feat-a"
        a.mkdir()
        (a / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (a / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
        b = features / "feat-b"
        b.mkdir()
        (b / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (b / "RESEARCH.md").write_text("# R\n")
        (b / "RESEARCH_SUMMARY.md").write_text("# S\n")
    elif name == "research-pending-only":
        # Single-feature queue with only research-pending feat-a; under
        # --skip-needs-research the script should terminate with
        # queue-blocked-on-research.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-a", "name": "Feature A", "spec_dir": "feat-a", "tier": 1},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        a = features / "feat-a"
        a.mkdir()
        (a / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (a / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "phases-complete-no-retro-done":
        # All phases complete (no unchecked rows), no sentinels at all.
        # Retro unwired: Step 9 (mcp test) fires directly — expects
        # sub_skill: mcp-test, NOT retro-feature.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcnr", "name": "Feature PCNR",
                 "spec_dir": "feat-pcnr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcnr"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "phases-complete-retro-done":
        # All phases complete + a stale RETRO_DONE.md on disk, no VALIDATED.md
        # yet. Retro unwired: RETRO_DONE.md is ignored for routing — Step 9
        # (mcp test) fires regardless — expects sub_skill: mcp-test.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcrd", "name": "Feature PCRD",
                 "spec_dir": "feat-pcrd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcrd"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            p / "RETRO_DONE.md", "retro-done",
            feature_id="feat-pcrd", date="2026-05-22",
            rounds=1, retro_plans=["retro-1-feat-pcrd.md"],
            mcp_validation_status="complete",
        )
    elif name == "phases-complete-retro-done-cloud":
        # Cloud variant: phases complete + RETRO_DONE.md, no VALIDATED.md,
        # no DEFERRED_NON_CLOUD.md. Under cloud Step 9 → defer MCP test.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcrdc", "name": "Feature PCRDC",
                 "spec_dir": "feat-pcrdc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcrdc"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            p / "RETRO_DONE.md", "retro-done",
            feature_id="feat-pcrdc", date="2026-05-22",
            rounds=1, retro_plans=["retro-1-feat-pcrdc.md"],
            mcp_validation_status="deferred-to-workstation",
        )
    elif name == "phases-complete-no-retro-done-cloud":
        # Cloud variant: phases complete, no sentinels. Retro unwired → cloud
        # routes directly to Step 9, which defers MCP to workstation
        # (__write_deferred_non_cloud__).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcnrc", "name": "Feature PCNRC",
                 "spec_dir": "feat-pcnrc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcnrc"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "adhoc-brief":
        # Ad-hoc feature seeded by --enqueue-adhoc: queue entry at top, spec
        # dir with ADHOC_BRIEF.md but no SPEC.md yet. Step 4 must route to /spec
        # with the ad-hoc-specific arg.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "adhoc-x", "name": "Ad-hoc X", "spec_dir": "adhoc-x",
                 "tier": 0, "adhoc": True}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        a = features / "adhoc-x"
        a.mkdir()
        (a / "ADHOC_BRIEF.md").write_text(
            "---\nkind: adhoc-brief\nfeature_id: adhoc-x\n"
            "enqueued_by: lazy-adhoc\ndate: 2026-05-24\n---\n\n"
            "# Ad-hoc task: Ad-hoc X\n\nDo the thing.\n"
        )
    elif name == "needs-realign":
        # feat-h has a hard dep on feat-up (complete upstream); no realign plan yet.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-h", "name": "Feature H", "spec_dir": "feat-h", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n- ~~Upstream U — done~~ **COMPLETE**\n"
        )
        up = features / "feat-up"
        up.mkdir()
        (up / "SPEC.md").write_text("# Upstream\n\n**Status:** Complete\n")
        (up / "PHASES.md").write_text("# Phases\n\n- [x] Done\n")
        h = features / "feat-h"
        h.mkdir()
        (h / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:**\n\n"
            "- feat-up — hard — relies on the upstream contract\n"
        )
    elif name == "device-deferred-pending":
        # Phases + retro complete; a prior no-device /mcp-test deferred the
        # real-device-only assertion AQ-TE-05 via DEFERRED_REQUIRES_DEVICE.md
        # (no VALIDATED.md). Exercised under BOTH device states:
        #   real_device=False → Step 2 device-saturated skip → device-queue-exhausted
        #   real_device=True  → Step 9 re-open → mcp-test scoped to AQ-TE-05
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dd", "name": "Feature DD",
                 "spec_dir": "feat-dd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dd = features / "feat-dd"
        dd.mkdir()
        (dd / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dd / "RESEARCH.md").write_text("# R\n")
        (dd / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dd / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dd / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dd", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dd.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            dd / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="feat-dd",
            deferred_scenarios=["AQ-TE-05"],
            reason="sustained zero-dropout not certifiable under HeadlessPumpDriver",
            deferred_by="lazy", date="2026-05-30",
        )
    elif name == "device-deferred-cleared":
        # The real-device re-open succeeded: /mcp-test deleted
        # DEFERRED_REQUIRES_DEVICE.md and wrote VALIDATED.md. With retro already
        # done, a real-device run proceeds straight to __mark_complete__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dc", "name": "Feature DC",
                 "spec_dir": "feat-dc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dc = features / "feat-dc"
        dc.mkdir()
        (dc / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dc / "RESEARCH.md").write_text("# R\n")
        (dc / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dc / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dc / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dc", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dc.md"],
            mcp_validation_status="complete",
        )
        _write_yaml_sentinel(
            dc / "VALIDATED.md", "validated",
            feature_id="feat-dc", date="2026-05-30",
            mcp_scenarios=["AQ-TE-05"], result="all-passing",
        )
    elif name == "device-deferred-stale-validated":
        # Stray-race state: a real-device re-open wrote VALIDATED.md but did NOT
        # delete DEFERRED_REQUIRES_DEVICE.md. The sentinel's presence MUST still
        # block completion — on a real-device host it re-fires the re-open
        # (idempotent, self-healing) rather than flipping Complete (which would
        # leave Complete + a deferral sentinel, the lint contradiction).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dsv", "name": "Feature DSV",
                 "spec_dir": "feat-dsv", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dsv = features / "feat-dsv"
        dsv.mkdir()
        (dsv / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dsv / "RESEARCH.md").write_text("# R\n")
        (dsv / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dsv / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dsv / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dsv", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dsv.md"],
            mcp_validation_status="complete",
        )
        _write_yaml_sentinel(
            dsv / "VALIDATED.md", "validated",
            feature_id="feat-dsv", date="2026-05-30",
            mcp_scenarios=["AQ-TE-05"], result="all-passing",
        )
        _write_yaml_sentinel(
            dsv / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="feat-dsv",
            deferred_scenarios=["AQ-TE-05"],
            reason="sustained zero-dropout not certifiable under HeadlessPumpDriver",
            deferred_by="lazy", date="2026-05-30",
        )
    elif name == "device-deferred-with-skip":
        # Mixed waiver: some assertions are any-host-untestable (permanent
        # SKIP_MCP_TEST.md) AND one is real-device-only (DEFERRED_REQUIRES_DEVICE.md)
        # — the learn-system-v2 shape. The deferral MUST take precedence: on a
        # real-device host the feature RE-OPENS (does not validate-from-skip and
        # complete), so the device assertion is certified before completion.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dws", "name": "Feature DWS",
                 "spec_dir": "feat-dws", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dws = features / "feat-dws"
        dws.mkdir()
        (dws / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dws / "RESEARCH.md").write_text("# R\n")
        (dws / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dws / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dws / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dws", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dws.md"],
            mcp_validation_status="complete",
        )
        _write_yaml_sentinel(
            dws / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-dws",
            reason="two items need a live LLM API key / dev-console — not MCP-drivable here",
            alternative_validation="covered by the deterministic test suite",
            date="2026-05-30", skipped_by="lazy",
        )
        _write_yaml_sentinel(
            dws / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="feat-dws",
            deferred_scenarios=["modeling-audio-in-cue"],
            reason="audio item blocked by no-device ALSA failure under HeadlessPumpDriver",
            deferred_by="lazy", date="2026-05-30",
        )
    elif name == "stale-mcp-results-reverify":
        # Workstation Step 9 path: on-disk MCP_TEST_RESULTS.md claims all-passing
        # but carries a stale validated_commit (all-zeros sha) that does NOT match
        # the fixture's actual HEAD. The fixture root is a real git repo so the
        # implementation's `git rev-parse HEAD` resolves to a non-zero sha.
        # Expected: compute_state detects staleness and re-verifies (sub_skill=
        # "mcp-test"), NOT __write_validated_from_results__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-smrr", "name": "Feature SMRR",
                 "spec_dir": "feat-smrr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        smrr = features / "feat-smrr"
        smrr.mkdir()
        (smrr / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (smrr / "RESEARCH.md").write_text("# R\n")
        (smrr / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # All phases checked — no remaining unchecked rows.
        (smrr / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            smrr / "RETRO_DONE.md", "retro-done",
            feature_id="feat-smrr", date="2026-06-01",
            rounds=1, retro_plans=["retro-1-feat-smrr.md"],
            mcp_validation_status="pending",
        )
        # Stale on-disk results: all-passing but validated against the all-zeros sha
        # (a sha that cannot equal any real git HEAD). The implementation's freshness
        # check should catch this and route to re-verify rather than auto-validate.
        _write_yaml_sentinel(
            smrr / "MCP_TEST_RESULTS.md", "mcp-test-results",
            result="all-passing",
            validated_commit="0000000000000000000000000000000000000000",
        )
        # NO VALIDATED.md — not yet validated.
        # NO SKIP_MCP_TEST.md — waiver not present.

        # Make the fixture root a real git repo so `git rev-parse HEAD` resolves
        # to a genuine (non-zero) sha. The implementation compares that sha against
        # the stale validated_commit above and must detect the mismatch.
        for cmd in [
            ["git", "-C", str(root), "init", "-q"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "add", "-A"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "fixture"],
        ]:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"stale-mcp-results-reverify git setup failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )
    elif name == "skip-pipeline-granted-needs-input":
        # WU-5 Phase-2 contract (RED fixture): SKIP_MCP_TEST.md carrying
        # `granted_by: pipeline` must NOT be accepted as a waiver by the
        # pipeline itself — a model could self-grant the skip to defeat MCP
        # validation. When `granted_by == "pipeline"`, compute_state must
        # refuse and route to terminal_reason="needs-input" rather than
        # emitting __write_validated_from_skip__.
        # This fixture is RED against current code: current Step 9 ignores
        # `granted_by` and always emits __write_validated_from_skip__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-spg", "name": "Feature SPG",
                 "spec_dir": "feat-spg", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        spg = features / "feat-spg"
        spg.mkdir()
        (spg / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (spg / "RESEARCH.md").write_text("# R\n")
        (spg / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # All phases checked — retro + MCP gate reached.
        (spg / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            spg / "RETRO_DONE.md", "retro-done",
            feature_id="feat-spg", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-spg.md"],
            mcp_validation_status="pending",
        )
        # SKIP_MCP_TEST.md with granted_by: pipeline — self-grant the waiver.
        # Phase-2 contract: this must be refused (needs-input), not validated.
        _write_yaml_sentinel(
            spg / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-spg",
            reason="pipeline self-asserted skip to avoid MCP test",
            alternative_validation="none",
            date="2026-06-10", skipped_by="pipeline",
            granted_by="pipeline",
        )
        # NO VALIDATED.md — not yet validated.
        # NO DEFERRED_REQUIRES_DEVICE.md — pure skip path.

    elif name == "skip-operator-granted-validates":
        # WU-5 Phase-2 positive guard (GREEN fixture): SKIP_MCP_TEST.md
        # carrying `granted_by: operator` is a legitimate human-authored waiver.
        # compute_state must continue to emit __write_validated_from_skip__ for
        # operator grants — the existing vacuous-pass behavior is intentional
        # here and must not regress.
        # This fixture is expected GREEN even against current code (current
        # always validates-from-skip, regardless of granted_by).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sog", "name": "Feature SOG",
                 "spec_dir": "feat-sog", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sog = features / "feat-sog"
        sog.mkdir()
        (sog / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (sog / "RESEARCH.md").write_text("# R\n")
        (sog / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # All phases checked — retro + MCP gate reached.
        (sog / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            sog / "RETRO_DONE.md", "retro-done",
            feature_id="feat-sog", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-sog.md"],
            mcp_validation_status="pending",
        )
        # SKIP_MCP_TEST.md with granted_by: operator — legitimate human waiver.
        # Phase-2 contract: operator grant → __write_validated_from_skip__
        # (same as the pre-Phase-2 vacuous-pass behavior).
        _write_yaml_sentinel(
            sog / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-sog",
            reason="feature is a pure docs/config change — no runtime MCP path",
            alternative_validation="manual smoke test by operator",
            date="2026-06-10", skipped_by="operator",
            granted_by="operator",
        )
        # NO VALIDATED.md — not yet validated.
        # NO DEFERRED_REQUIRES_DEVICE.md — pure skip path.

    elif name == "skip-mcp-test-granted-with-class-validates":
        # Provenance positive: granted_by: mcp-test + a spec_class citation is a
        # verified structural assessment by the validation step itself —
        # accepted as a waiver → __write_validated_from_skip__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-smtc", "name": "Feature SMTC",
                 "spec_dir": "feat-smtc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        smtc = features / "feat-smtc"
        smtc.mkdir()
        (smtc / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (smtc / "RESEARCH.md").write_text("# R\n")
        (smtc / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (smtc / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            smtc / "RETRO_DONE.md", "retro-done",
            feature_id="feat-smtc", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-smtc.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            smtc / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-smtc",
            reason="standalone crate — no MCP-reachable surface",
            alternative_validation="covered by cargo tests",
            date="2026-06-10", skipped_by="lazy",
            granted_by="mcp-test",
            spec_class="no app integration — covered by cargo tests",
        )
        # NO VALIDATED.md — not yet validated.

    elif name == "skip-mcp-test-granted-missing-class-refuses":
        # Provenance gate: granted_by: mcp-test WITHOUT a spec_class citation is
        # an unverified claim — refused (needs-input), not validated. The
        # citation is what distinguishes a verified structural assessment from
        # a convenience skip.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-smtn", "name": "Feature SMTN",
                 "spec_dir": "feat-smtn", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        smtn = features / "feat-smtn"
        smtn.mkdir()
        (smtn / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (smtn / "RESEARCH.md").write_text("# R\n")
        (smtn / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (smtn / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            smtn / "RETRO_DONE.md", "retro-done",
            feature_id="feat-smtn", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-smtn.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            smtn / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-smtn",
            reason="claims untestable but cites no class",
            alternative_validation="none",
            date="2026-06-10", skipped_by="lazy",
            granted_by="mcp-test",
        )
        # NO VALIDATED.md — not yet validated.

    elif name == "skip-pipeline-authored-no-grant-refuses":
        # Provenance omission gate: a skip whose skipped_by identifies a
        # pipeline author ("lazy") but which carries NO granted_by at all used
        # to sail through as legacy-operator — the omission side-door (observed
        # 2026-06-10: an mcp-test cycle wrote a skip without the field and it
        # auto-validated with no operator confirmation). Must now refuse.
        # Files with NEITHER provenance field stay grandfathered.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-spa", "name": "Feature SPA",
                 "spec_dir": "feat-spa", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        spa = features / "feat-spa"
        spa.mkdir()
        (spa / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (spa / "RESEARCH.md").write_text("# R\n")
        (spa / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (spa / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            spa / "RETRO_DONE.md", "retro-done",
            feature_id="feat-spa", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-spa.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            spa / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-spa",
            reason="pipeline-written skip with no provenance field",
            alternative_validation="none",
            date="2026-06-10", skipped_by="lazy",
        )
        # NO VALIDATED.md — not yet validated.

    elif name == "roadmap-substring-collision-no-false-halt":
        # Fixture A — substring-collision bug in roadmap_marks_complete.
        # completion_claimed() passes the queue entry's `name` (not id) to
        # roadmap_marks_complete. The feature name "Audio" is a STRICT SUBSTRING
        # of the unrelated completed ROADMAP row text "Audio Engine". "Audio"
        # itself is NOT marked complete anywhere.
        #
        # Pre-fix (RED): roadmap_marks_complete does a bare re.search(re.escape("Audio"), line)
        # which matches the "Audio Engine" row → completion_claimed() returns True
        # → no COMPLETED.md receipt → hard-halt with terminal_reason="completion-unverified".
        #
        # Post-fix (GREEN): the match is anchored to whole-word / word-boundary so
        # "Audio" does NOT match the "Audio Engine" row → completion_claimed()
        # returns False → feature proceeds normally → Step 5 dispatches /spec to
        # generate a research prompt (no research files present).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-audio", "name": "Audio",
                 "spec_dir": "feat-audio", "tier": 1}
            ]
        }))
        # ROADMAP has a completed row for the UNRELATED "Audio Engine" feature.
        # "Audio" appears as a substring inside "Audio Engine" — this is the
        # exact collision the fix must prevent. Note the feature name searched by
        # roadmap_marks_complete is the queue entry name "Audio", not the id.
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n"
            "- ~~Audio Engine — deep audio processing~~ **COMPLETE**\n"
        )
        a_dir = features / "feat-audio"
        a_dir.mkdir()
        # SPEC.md Status: Draft — not complete. No receipt, no research files.
        (a_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        # No RESEARCH.md, no RESEARCH_SUMMARY.md, no RESEARCH_PROMPT.md →
        # Step 5 will dispatch /spec (generate research prompt).

    elif name == "is-stub-prose-mention-not-stub":
        # Fixture B — substring-collision bug in is_stub_spec.
        # The SPEC.md has a non-stub **Status:** (just "Draft", no "(pre-Gemini)"
        # qualifier) but the body PROSE contains the literal phrase
        # "Draft (pre-Gemini)" in a sentence discussing the concept.
        #
        # Pre-fix (RED): is_stub_spec does `"Draft (pre-Gemini)" in spec_text`
        # which is a bare substring match against the ENTIRE spec body. It matches
        # the prose mention → the feature is falsely routed to Step 4.5 stub-spec
        # → sub_skill="spec" at the stub branch instead of the normal pipeline.
        #
        # Post-fix (GREEN): the check is anchored to the **Status:** line, so the
        # prose mention does NOT trigger is_stub_spec → the feature falls through
        # to the normal pipeline. With RESEARCH.md + RESEARCH_SUMMARY.md present
        # but no PHASES.md yet → Step 6 dispatches /plan-feature.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-prose-stub", "name": "Prose Stub Feature",
                 "spec_dir": "feat-prose-stub", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        ps = features / "feat-prose-stub"
        ps.mkdir()
        # **Status:** is a clean "Draft" — NOT a stub marker. The body prose
        # mentions "Draft (pre-Gemini)" as an illustrative example, which is
        # the text that the buggy bare-substring check incorrectly matches.
        (ps / "SPEC.md").write_text(
            "# Spec\n\n"
            "**Status:** Draft\n\n"
            "**Depends on:** (none)\n\n"
            "## Background\n\n"
            "Unlike a Draft (pre-Gemini) stub, this spec is fully researched "
            "and does not require a Gemini deep-research sprint before phases "
            "can be written.\n"
        )
        # Research files present → passes Step 5 gate, reaches Step 6.
        (ps / "RESEARCH.md").write_text("# Research\n\nResearch complete.\n")
        (ps / "RESEARCH_SUMMARY.md").write_text("# Summary\n\nKey findings.\n")
        # No PHASES.md → Step 6 dispatches /plan-feature.

    elif name == "upstream-substring-collision":
        # Fixture C — substring-collision bug in upstream_is_complete.
        # The upstream feature directory is named "audio". The ROADMAP contains
        # a strikethrough+COMPLETE row for the UNRELATED "audio-engine" feature.
        # upstream_is_complete checks `upstream_name in line` (bare substring) which
        # matches the "audio-engine" row when upstream_name="audio".
        #
        # Pre-fix (RED): upstream_is_complete("audio") returns True (false positive)
        # → hard_complete_upstream_dirs is non-empty → realign_is_fresh returns False
        # (no realign plan exists) → compute_state emits sub_skill="realign-spec"
        # at Step 4.6, even though "audio" upstream is NOT actually complete.
        #
        # Post-fix (GREEN): the match is anchored to word boundary / whole directory
        # name so "audio" does NOT match "audio-engine" → upstream_is_complete returns
        # False → hard_complete_upstream_dirs stays empty → Step 4.6 does not fire
        # → feature proceeds to Step 5 (no research) → sub_skill="spec".
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-downstream", "name": "Downstream Feature",
                 "spec_dir": "feat-downstream", "tier": 1}
            ]
        }))
        # ROADMAP has a completed row for "audio-engine" — NOT for "audio" (the
        # upstream the downstream feature depends on). Bare substring "audio" in
        # "audio-engine" is the collision.
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n"
            "- ~~audio-engine — deep audio processing~~ **COMPLETE**\n"
        )
        # Create the upstream "audio" feature directory. Its SPEC.md status is
        # Draft (NOT Complete), so the SPEC-based check in upstream_is_complete
        # also returns False. Only the buggy ROADMAP substring check fires.
        aud = features / "audio"
        aud.mkdir()
        (aud / "SPEC.md").write_text(
            "# Upstream Audio\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        # Create the downstream feature with a hard dep on "audio" (the upstream).
        ds = features / "feat-downstream"
        ds.mkdir()
        # The dep block references "audio" by feature_id. resolve_upstream_dir
        # finds the sibling "audio" dir (has SPEC.md).
        (ds / "SPEC.md").write_text(
            "# Downstream Spec\n\n"
            "**Status:** Draft\n\n"
            "**Depends on:**\n\n"
            "- audio — hard — this feature builds on the audio foundation\n"
        )
        # No research files → if Step 4.6 correctly does NOT fire, the feature
        # falls through to Step 5 and dispatches /spec (research prompt generation).

    elif name == "stale-plan-all-refs-checked-flips":
        # Fixture A — stale-plan detection.
        # Plan's phases: [1] scope is fully checked (all Phase 1 deliverables
        # are [x]). Phase 2 still has an unchecked row, so unchecked > 0 overall
        # and Step 7 is entered. The plan is STALE: every WU it references is
        # done, yet its frontmatter still says status: Ready (never flipped to
        # Complete by a prior session).
        #
        # Pre-fix (RED): compute_state dispatches execute-plan — it burns an
        # Opus cycle re-verifying a plan whose work is already done.
        #
        # Post-fix (GREEN): the stale-plan guard detects that
        # _unchecked_wus_in_plan_scope(phases_text, {1}) is empty → emits
        # sub_skill="__flip_plan_complete_stale__" with sub_skill_args=plan path.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stale", "name": "Feature Stale",
                 "spec_dir": "feat-stale", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        st = features / "feat-stale"
        st.mkdir()
        (st / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (st / "RESEARCH.md").write_text("# R\n")
        (st / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 1: ALL deliverables checked (the plan's scope is fully done).
        # Phase 2: one unchecked deliverable → unchecked > 0 overall so Step 7
        # is entered and plan selection runs.
        (st / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] WU1 implement core logic\n"
            "- [x] WU2 write unit tests\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = st / "plans"
        plans.mkdir()
        # Plan scoped to phases: [1] only — the fully-checked phase.
        # status: Ready (never updated after phase 1 completed) → STALE.
        (plans / "all-phases-stale.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-stale\n"
            "status: Ready\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan for Phase 1\n"
        )
        # No RETRO_DONE.md → stays in Step 7 (not past Step 8).
        # No DEFERRED_NON_CLOUD.md → cloud-saturation gate does not interfere.

    elif name == "ready-plan-unchecked-in-scope-still-executes":
        # Fixture B — discriminating guard: plan scope has genuine remaining work.
        # Phase 1 still has an unchecked deliverable inside the plan's phases: [1]
        # scope. The stale-plan guard must NOT fire — _unchecked_wus_in_plan_scope
        # returns a non-empty list so the plan is live work.
        #
        # Expected (GREEN today and must stay GREEN): sub_skill="execute-plan".
        # This fixture proves the flip fires ONLY when the scope is fully checked.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-live", "name": "Feature Live",
                 "spec_dir": "feat-live", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        lv = features / "feat-live"
        lv.mkdir()
        (lv / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (lv / "RESEARCH.md").write_text("# R\n")
        (lv / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 1: UNCHECKED deliverable still in scope → plan is NOT stale.
        # Phase 2: also unchecked, but the plan only declares phases: [1].
        (lv / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] WU1 implement core logic\n"
            "- [ ] WU2 write unit tests\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = lv / "plans"
        plans.mkdir()
        # Plan scoped to phases: [1] — phase 1 has WU2 unchecked → live work
        # remains → execute-plan must be dispatched as normal.
        (plans / "all-phases-live.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-live\n"
            "status: Ready\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan for Phase 1\n"
        )
        # No RETRO_DONE.md, no DEFERRED_NON_CLOUD.md.

    elif name == "finalize-plan-verification-rows-only-flips":
        # Phase 8 (lazy-validation-readiness) — close the /execute-plan
        # finalization gap, option (b). The plan's phase scope has all its
        # IMPLEMENTATION deliverables checked; the ONLY remaining unchecked rows
        # in scope sit under a Runtime Verification subsection (Step-9-owned).
        # The plan frontmatter is still Ready. Phase 2 (out of scope) has a real
        # unchecked impl row so unchecked > 0 overall and Step 7 is entered.
        #
        # Pre-fix (RED): _unchecked_wus_in_plan_scope returns the RV row as
        # unchecked → the stale-plan gate does NOT fire → execute-plan is
        # re-dispatched (a redundant cycle that only flips the plan to Complete).
        #
        # Post-fix (GREEN): the finalize-stale branch sees the in-scope unchecked
        # remainder is entirely verification-only → routes to
        # __flip_plan_complete_stale__ with no redundant execute-plan dispatch.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-fin", "name": "Feature Finalize",
                 "spec_dir": "feat-fin", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fn = features / "feat-fin"
        fn.mkdir()
        (fn / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (fn / "RESEARCH.md").write_text("# R\n")
        (fn / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 1 (plan scope): all impl WUs [x]; only a Runtime Verification
        # row remains unchecked. Phase 2 (out of scope): a real unchecked row.
        (fn / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] WU1 implement core logic\n"
            "- [x] WU2 write unit tests\n"
            "\n"
            "**Runtime Verification** *(checked on the next marked run):*\n"
            "- [ ] live MCP assertion certifies the surface\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = fn / "plans"
        plans.mkdir()
        # Plan scoped to phases: [1] — its only in-scope unchecked row is the
        # verification row → finalize-stale → flip, do NOT execute-plan.
        (plans / "all-phases-fin.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-fin\n"
            "status: Ready\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan for Phase 1\n"
        )
        # No RETRO_DONE.md → stays in Step 7 (not past Step 8).

    elif name == "realign-hash-gate-detects-changed-upstream":
        # WU-8 Fixture 1: realign freshness gate hash comparison.
        #
        # Scenario: downstream feat-rhg has a hard dep on upstream feat-rhg-up
        # (Complete). The downstream has a realign plan whose frontmatter records
        # upstream_phases_hashes: with a BOGUS hash (64 zeros) that does NOT match
        # the upstream PHASES.md actual content. The plan file's mtime is NEWER
        # than the upstream PHASES.md (simulating: upstream changed AFTER the plan
        # was written, but the plan mtime ordering is reversed by os.utime trickery
        # — actually here we write PHASES.md first so plan is naturally newer).
        #
        # RED today (mtime gate): plan mtime > upstream PHASES.md mtime → mtime
        # gate says "fresh" → no realign needed → routes onward (Step 5/6).
        # GREEN after fix (hash gate): recorded hash ≠ actual PHASES.md sha256 →
        # hash gate says "stale" → routes to Step 4.6 realign-spec.
        #
        # We write upstream PHASES.md FIRST so its mtime is older, then write the
        # realign plan so its mtime is newer — satisfying the "plan is newer"
        # condition the old mtime gate would declare as fresh.
        import time as _time_mod
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-rhg", "name": "Feature RHG", "spec_dir": "feat-rhg", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n- ~~Upstream RHG Up — done~~ **COMPLETE**\n"
        )
        # Complete upstream feature directory
        up_dir = features / "feat-rhg-up"
        up_dir.mkdir(parents=True, exist_ok=True)
        (up_dir / "SPEC.md").write_text("# Upstream\n\n**Status:** Complete\n")
        upstream_phases = up_dir / "PHASES.md"
        upstream_phases.write_text("# Phases\n\n- [x] Upstream done\n")
        # Force the upstream PHASES.md mtime to be clearly OLDER (10 seconds ago)
        # so the plan file written next is naturally NEWER.
        old_mtime = _time_mod.time() - 10.0
        os.utime(str(upstream_phases), (old_mtime, old_mtime))

        # Downstream feature with hard dep on the upstream
        down_dir = features / "feat-rhg"
        down_dir.mkdir(parents=True, exist_ok=True)
        (down_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n"
            "**Depends on:**\n\n"
            "- feat-rhg-up — hard — downstream relies on upstream contract\n"
        )
        (down_dir / "RESEARCH.md").write_text("# R\n")
        (down_dir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Realign plan with a BOGUS recorded hash (64 zeros) that will never match
        # the real upstream PHASES.md sha256. The impl agent's hash gate must detect
        # the mismatch and require a new realign even though plan mtime > PHASES mtime.
        plans_dir = down_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        bogus_hash = "0" * 64
        realign_plan_path = plans_dir / "realign-2026-01-01.md"
        realign_plan_path.write_text(
            "---\n"
            "kind: realign\n"
            "upstream_phases_hashes:\n"
            # Use the upstream dir NAME as the key (per task description: dir-name → sha256)
            f"  feat-rhg-up: {bogus_hash}\n"
            "---\n\n"
            "# Realign plan (with stale recorded hash)\n"
        )
        # The plan is written AFTER upstream PHASES.md (so plan mtime > PHASES mtime).
        # The old mtime gate reads plan mtime > PHASES mtime → declares fresh → no realign.
        # The new hash gate reads recorded hash ≠ real sha256 → declares stale → realign.

    elif name == "stale-upstream-auto-wired-at-probe":
        # WU-8 Fixture 2: check_stale_upstream auto-runs at probe start.
        #
        # Scenario: docs/work/materialized.json records wi_id=201, feature_id=
        # "feat-sau" with materialized_changedDate "2026-01-01T00:00:00Z".
        # docs/work/ado-mirror.json has the same WI with changedDate
        # "2026-06-01T00:00:00Z" (STRICTLY NEWER). The feature dir exists with
        # a minimal queue entry so compute_state would otherwise process it.
        # STALE_UPSTREAM.md is NOT pre-written.
        #
        # RED today: nothing auto-calls check_stale_upstream → STALE_UPSTREAM.md
        # is never written → Step 2.9 stale check finds nothing → feature routes
        # through its normal early pipeline (no stale halt).
        # GREEN after fix: compute_state auto-calls check_stale_upstream at probe
        # start → writes STALE_UPSTREAM.md → Step 2.9 reads it and halts with
        # terminal_reason="stale_upstream".
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sau", "name": "Feature SAU", "spec_dir": "feat-sau", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sau_dir = features / "feat-sau"
        sau_dir.mkdir(parents=True, exist_ok=True)
        (sau_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        # Seed materialized.json with an OLDER changedDate for this WI
        work_dir = root / "docs" / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        lazy_core.append_materialized(
            work_dir, 201, "feat-sau", "2026-01-01T00:00:00Z"
        )
        # Mirror has a STRICTLY NEWER changedDate for the same WI
        (work_dir / "ado-mirror.json").write_text(
            json.dumps({
                "syncedAt": "2026-06-10T12:00:00Z",
                "watermark": "2026-06-10",
                "query": "SELECT ...",
                "workItems": [
                    {
                        "id": 201,
                        "type": "User Story",
                        "title": "Feature SAU upstream",
                        "description": "Updated upstream.",
                        "acceptanceCriteria": "AC.",
                        "url": "https://dev.azure.com/org/proj/_workitems/edit/201",
                        "changedDate": "2026-06-01T00:00:00Z",
                    }
                ],
            }, indent=2),
            encoding="utf-8",
        )
        # Do NOT pre-write STALE_UPSTREAM.md — the auto-wiring at probe start must create it.

    else:
        raise ValueError(f"unknown fixture: {name}")

    return root


def run_smoke_tests() -> int:
    """Build fixtures in a temp dir and assert expected state shapes."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lazy-state-fixtures-") as td:
        td_path = Path(td)
        cases = [
            # (fixture_name, cloud, skip_needs_research, expectations dict)
            ("fresh-queue", False, False, {"terminal_reason": "needs-spec-input"}),
            ("blocker", False, False, {"terminal_reason": "blocked", "feature_id": "feat-b"}),
            ("mid-implementation", False, False, {"sub_skill": "execute-plan", "feature_id": "feat-c"}),
            ("cloud-saturated", True, False, {"feature_id": "feat-e"}),   # advances past saturated feat-d
            # Step 7 cloud bypass: all plans Complete + PHASES.md has
            # workstation-only unchecked rows → bypass triggers, falls
            # through to phases-complete logic. Retro unwired → cloud routes
            # directly to Step 9 (defer MCP to workstation).
            ("cloud-workstation-only-remainder", True, False, {
                "sub_skill": "__write_deferred_non_cloud__",
                "feature_id": "feat-cw",
                "current_step": "Step 9: cloud defers MCP test",
            }),
            # Same bypass with DEFERRED_NON_CLOUD.md already on disk. Retro
            # unwired → Step 2's cloud-saturated skip fires (deferred + no
            # validated) → cloud-queue-exhausted (only feature in queue).
            ("cloud-workstation-only-with-deferred", True, False, {
                "terminal_reason": "cloud-queue-exhausted",
            }),
            # Workstation MCP-gate bypass: all impl plans Complete, only
            # unchecked rows are Runtime Verification → fall through to the
            # MCP gate. Retro unwired → Step 9 mcp-test fires directly.
            ("workstation-all-plans-complete-phases-unchecked", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-wapcpu",
                "current_step": "Step 9: run MCP tests",
            }),
            # Workstation bypass + a stale RETRO_DONE.md present (retro unwired;
            # the sentinel is ignored for routing) → Step 9 mcp-test (the
            # dispatch that actually ticks the deferred verification rows).
            ("workstation-verification-only-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-wvrd",
                "current_step": "Step 9: run MCP tests",
            }),
            # Workstation bypass with bold-marker (`**Runtime Verification**`)
            # subsections instead of `### ` headings — real AlgoBooth format.
            # Retro unwired → Step 9 mcp-test.
            ("workstation-verification-only-bold-marker", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-wbold",
                "current_step": "Step 9: run MCP tests",
            }),
            # NEGATIVE: all impl plans Complete but a remaining unchecked row is
            # a real implementation deliverable (outside any verification
            # subsection) → bypass must NOT fire; write-plan still dispatched.
            ("workstation-all-plans-complete-real-unchecked", False, False, {
                "sub_skill": "write-plan",
                "feature_id": "feat-wreal",
            }),
            # Superseded-phase bypass: one In-progress phase with only
            # verification-only unchecked rows, plus a Superseded phase with
            # plain unchecked deliverable rows. Superseded boxes must be ignored
            # → bypass fires → Step 9 mcp-test (retro unwired; no write-plan loop).
            ("superseded-phase-unchecked", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-sup",
                "current_step": "Step 9: run MCP tests",
            }),
            # Ad-hoc enqueue: ADHOC_BRIEF.md present, no SPEC.md → /spec with
            # the ad-hoc-specific arg (Step 4 ad-hoc branch).
            ("adhoc-brief", False, False, {
                "sub_skill": "spec",
                "feature_id": "adhoc-x",
                "current_step": "Step 4: ad-hoc brief → spec",
            }),
            ("all-complete", False, False, {"terminal_reason": "all-features-complete"}),
            ("needs-research", False, False, {"terminal_reason": "needs-research"}),
            # Canonical `> Draft (pre-Gemini)` SPEC trailer → Step 4.5 stub
            # dispatch, NOT needs-research. Without this match, the script
            # would halt the queue waiting on Gemini for a SPEC whose baseline
            # doesn't exist yet.
            ("stub-pre-gemini-marker", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-stub-marker",
                "current_step": "Step 4.5: stub-spec detected",
            }),
            # queue.json `"stub": true` cross-check fires Step 4.5 even when
            # the SPEC body has no stub marker.
            ("stub-queue-flag-only", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-stub-queue",
                "current_step": "Step 4.5: stub-spec detected",
            }),
            ("needs-realign", False, False, {
                "sub_skill": "realign-spec",
                "feature_id": "feat-h",
            }),
            ("spec-status-complete", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            # FM1: Complete claim without a COMPLETED.md receipt hard-halts.
            ("complete-no-receipt", False, False, {
                "terminal_reason": "completion-unverified",
                "feature_id": "feat-nr",
            }),
            # Superseded is exempt from the receipt requirement → skipped.
            ("superseded-no-receipt", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            # FM3: dangling spec_dir is skipped (not dispatched).
            ("dangling-queue-entry", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            ("plan-frontmatter-filter", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-j",
            }),
            ("legacy-plan-diagnostics", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-k",
            }),
            # --skip-needs-research: feat-a has a research prompt only (would
            # terminate on needs-research); skipping it should advance to feat-b's
            # Step 6 (generate phases).
            ("research-pending-skip", False, False, {
                "terminal_reason": "needs-research",
                "feature_id": "feat-a",
            }),
            ("research-pending-skip", False, True, {
                "sub_skill": "plan-feature",
                "feature_id": "feat-b",
            }),
            # --skip-needs-research with only research-pending features in queue
            # should terminate with queue-blocked-on-research.
            ("research-pending-only", False, True, {
                "terminal_reason": "queue-blocked-on-research",
            }),
            # Retro unwired: when all phases are complete the pipeline routes
            # DIRECTLY to the Step 9 MCP gate, never to retro-feature.
            # Workstation: phases complete, no sentinels → Step 9 mcp-test.
            ("phases-complete-no-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-pcnr",
                "current_step": "Step 9: run MCP tests",
            }),
            # A stale RETRO_DONE.md on disk does NOT change routing (ignored) →
            # still Step 9 mcp test.
            ("phases-complete-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-pcrd",
                "current_step": "Step 9: run MCP tests",
            }),
            # Cloud variant: phases complete, no sentinels → Step 9 defers
            # MCP to workstation directly (retro unwired).
            ("phases-complete-no-retro-done-cloud", True, False, {
                "sub_skill": "__write_deferred_non_cloud__",
                "feature_id": "feat-pcnrc",
                "current_step": "Step 9: cloud defers MCP test",
            }),
            # Cloud variant with stale RETRO_DONE.md: ignored for routing →
            # Step 9 writes DEFERRED_NON_CLOUD.md.
            ("phases-complete-retro-done-cloud", True, False, {
                "sub_skill": "__write_deferred_non_cloud__",
                "feature_id": "feat-pcrdc",
                "current_step": "Step 9: cloud defers MCP test",
            }),
            # Cloud-saturation gate: In-progress plan whose only unchecked
            # WU is documented in DEFERRED_NON_CLOUD.md → flip pseudo-skill.
            ("cloud-saturated-in-progress-plan", True, False, {
                "sub_skill": "__flip_plan_complete_cloud_saturated__",
                "feature_id": "feat-cs",
                "current_step": "Step 7a: flip plan Complete (cloud-saturated)",
            }),
            # Cloud: In-progress plan but DEFERRED_NON_CLOUD.md does NOT
            # document the unchecked WU → gate must NOT fire; dispatch
            # execute-plan as usual.
            ("cloud-in-progress-plan-not-saturated", True, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-csn",
                "current_step": "Step 7a: execute plan",
            }),
            # Workstation regression: same shape as the cloud-saturated
            # fixture, but cloud=False. Gate is cloud-only — workstation
            # must keep dispatching execute-plan so the workstation runtime
            # can still complete the gated WU.
            ("workstation-in-progress-plan-with-deferred", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-wcs",
                "current_step": "Step 7a: execute plan",
            }),
            # Device-deferral (real-device axis). Same fixture under both device
            # states (5-tuple pins real_device):
            #   no-device → Step 2 device-saturated skip → device-queue-exhausted
            ("device-deferred-pending", False, False, {
                "terminal_reason": "device-queue-exhausted",
            }, False),
            #   real-device → Step 9 re-open → /mcp-test scoped to the deferred
            #   scenario set (AQ-TE-05). Asserts the scenario IDs are threaded
            #   into the dispatch args (extra check below).
            ("device-deferred-pending", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-dd",
                "current_step": "Step 9: re-open device-deferred scenarios (real-device host)",
            }, True),
            # After re-open succeeds (sentinel deleted, VALIDATED.md written),
            # a real-device run proceeds to __mark_complete__.
            ("device-deferred-cleared", False, False, {
                "sub_skill": "__mark_complete__",
                "feature_id": "feat-dc",
            }, True),
            # Stray-race hardening: VALIDATED.md present but the deferral sentinel
            # was NOT deleted. The sentinel's presence MUST block completion — a
            # real-device host re-fires the re-open (self-healing), it does NOT
            # flip Complete. Proves VALIDATED.md alone cannot bypass the deferral.
            ("device-deferred-stale-validated", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-dsv",
                "current_step": "Step 9: re-open device-deferred scenarios (real-device host)",
            }, True),
            # Mixed skip+deferral: the deferral takes precedence — a real-device
            # host RE-OPENS rather than completing via the skip. Proves a buried
            # real-device assertion can't be masked by a co-present permanent skip.
            ("device-deferred-with-skip", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-dws",
                "current_step": "Step 9: re-open device-deferred scenarios (real-device host)",
            }, True),
            # Stale MCP results freshness gate (WU-4). The on-disk
            # MCP_TEST_RESULTS.md carries validated_commit=all-zeros, which cannot
            # equal the fixture's actual git HEAD. The implementation must detect
            # the mismatch and re-verify (sub_skill=mcp-test) rather than silently
            # accepting the stale results as proof of the current commit.
            # RED against current code: compute_state ignores validated_commit and
            # returns sub_skill="__write_validated_from_results__" instead.
            ("stale-mcp-results-reverify", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-smrr",
                "current_step": "Step 9: stale MCP results — re-verify",
            }),
            # WU-5: pipeline-self-granted SKIP_MCP_TEST.md must NOT vacuously
            # validate. When `granted_by: pipeline`, the pipeline is trying to
            # self-waive its own validation requirement — refuse this and route
            # to needs-input so an operator can review.
            # RED against current code: current Step 9 ignores `granted_by` and
            # emits sub_skill="__write_validated_from_skip__" instead of
            # terminal_reason="needs-input".
            ("skip-pipeline-granted-needs-input", False, False, {
                "terminal_reason": "needs-input",
                "feature_id": "feat-spg",
            }),
            # WU-5 positive guard: operator-granted SKIP_MCP_TEST.md must still
            # produce __write_validated_from_skip__ (legitimate human waiver).
            # GREEN even against current code — kept as a non-regression guard.
            # If this fixture ever turns RED, it means the Phase-2 impl broke
            # the backward-compat path for operator grants.
            ("skip-operator-granted-validates", False, False, {
                "sub_skill": "__write_validated_from_skip__",
                "feature_id": "feat-sog",
                "current_step": "Step 9: skip-mcp-test → validated",
            }),
            # Provenance positive: granted_by: mcp-test WITH a spec_class
            # citation is a verified structural assessment by the validation
            # step itself — accepted → __write_validated_from_skip__.
            ("skip-mcp-test-granted-with-class-validates", False, False, {
                "sub_skill": "__write_validated_from_skip__",
                "feature_id": "feat-smtc",
                "current_step": "Step 9: skip-mcp-test → validated",
            }),
            # Provenance gate: granted_by: mcp-test WITHOUT spec_class is an
            # unverified claim — refuse (needs-input), never vacuous-validate.
            ("skip-mcp-test-granted-missing-class-refuses", False, False, {
                "terminal_reason": "needs-input",
                "feature_id": "feat-smtn",
            }),
            # Provenance omission gate: pipeline-authored skip (skipped_by:
            # lazy) with NO granted_by must refuse — closes the side-door where
            # omitting the field bypassed the WU-5 provenance gate entirely.
            ("skip-pipeline-authored-no-grant-refuses", False, False, {
                "terminal_reason": "needs-input",
                "feature_id": "feat-spa",
            }),
            # Fixture A — roadmap_marks_complete substring collision.
            # Feature name "Audio" is a strict substring of the completed ROADMAP
            # text "Audio Engine". Pre-fix: falsely halts with completion-unverified.
            # Post-fix: normal Draft routing → Step 5 /spec (no research files).
            # RED today: roadmap_marks_complete substring-matches the Audio Engine
            # row → completion_claimed returns True → no receipt → halt.
            ("roadmap-substring-collision-no-false-halt", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-audio",
                "current_step": "Step 5: generate research prompt",
            }),
            # Fixture B — is_stub_spec prose-mention false-positive.
            # SPEC.md Status is plain "Draft" (not a stub), but the body prose
            # contains the literal phrase "Draft (pre-Gemini)" as illustrative text.
            # Pre-fix: bare substring match triggers stub route → Step 4.5 /spec.
            # Post-fix: only the **Status:** line is checked → not a stub →
            # proceeds to Step 6 /plan-feature (research present, no PHASES.md).
            # RED today: "Draft (pre-Gemini)" in spec_text matches the prose.
            ("is-stub-prose-mention-not-stub", False, False, {
                "sub_skill": "plan-feature",
                "feature_id": "feat-prose-stub",
                "current_step": "Step 6: plan feature (phases + plan)",
            }),
            # Fixture C — upstream_is_complete substring collision.
            # Upstream feature dir "audio" is a strict substring of the completed
            # ROADMAP entry "audio-engine". Pre-fix: upstream_is_complete falsely
            # returns True → triggers realign-spec at Step 4.6. Post-fix: word-
            # boundary anchor prevents the collision → no realign → Step 5 /spec.
            # RED today: upstream_name in line matches "audio-engine" for "audio".
            ("upstream-substring-collision", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-downstream",
                "current_step": "Step 5: generate research prompt",
            }),
            # Fixture A — stale-plan: plan's phases: [1] scope is fully checked
            # but Phase 2 has an unchecked row so unchecked > 0 overall → Step 7
            # is entered. The plan should be recognised as stale and the pseudo-
            # skill __flip_plan_complete_stale__ emitted (not execute-plan).
            # RED today: current code emits sub_skill="execute-plan".
            # current_step is asserted via a post-loop substring check below
            # (impl agent sets the exact string; we require "stale" appear in it).
            ("stale-plan-all-refs-checked-flips", False, False, {
                "sub_skill": "__flip_plan_complete_stale__",
                "feature_id": "feat-stale",
            }),
            # Fixture B — discriminating guard: plan still has real unchecked work
            # inside its phases: [1] scope → stale-plan guard must NOT fire.
            # GREEN today and must stay GREEN after the fix lands.
            ("ready-plan-unchecked-in-scope-still-executes", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-live",
                "current_step": "Step 7a: execute plan",
            }),
            # Phase 8 — finalization gap (option b). The plan's in-scope
            # unchecked remainder is entirely Runtime-Verification rows → the
            # finalize-stale branch must route to __flip_plan_complete_stale__
            # (NOT a redundant execute-plan re-dispatch).
            # RED today: code emits sub_skill="execute-plan".
            ("finalize-plan-verification-rows-only-flips", False, False, {
                "sub_skill": "__flip_plan_complete_stale__",
                "feature_id": "feat-fin",
            }),

            # WU-8 Fixture 1: realign hash gate detects changed upstream.
            # Downstream has a hard dep on a complete upstream. The realign plan
            # frontmatter records upstream_phases_hashes: with a BOGUS hash (64
            # zeros). The plan mtime is NEWER than the upstream PHASES.md mtime
            # (so the old mtime gate declares fresh). The hash gate must detect the
            # mismatch and require a new realign.
            # RED today: realign_is_fresh() compares mtimes → plan is newer →
            # declares fresh → no realign → routes onward (Step 5/6, not Step 4.6).
            # GREEN after fix: hash gate fires → sub_skill="realign-spec".
            ("realign-hash-gate-detects-changed-upstream", False, False, {
                "sub_skill": "realign-spec",
                "feature_id": "feat-rhg",
                "current_step": "Step 4.6: upstream realign needed",
            }),

            # WU-8 Fixture 2: check_stale_upstream auto-wired at probe start.
            # materialized.json + ado-mirror.json show upstream WI changed.
            # STALE_UPSTREAM.md NOT pre-written. compute_state must auto-call
            # check_stale_upstream and then halt at Step 2.9.
            # RED today: nothing auto-runs check_stale_upstream → no STALE_UPSTREAM.md
            # written → feature routes through normal early pipeline (e.g. Step 4/5).
            # GREEN after fix: auto-call writes STALE_UPSTREAM.md → Step 2.9 halts
            # with terminal_reason="stale_upstream".
            ("stale-upstream-auto-wired-at-probe", False, False, {
                "terminal_reason": "stale_upstream",
                "feature_id": "feat-sau",
            }),

            # NOTE: WU-8 Fixture 3 (step10-unexpected-writes-needs-input) is NOT a
            # compute_state routing case. The Step 10 "unexpected state" branch is
            # GENUINELY UNREACHABLE through compute_state's inputs (workstation Step 9
            # is fully guarded by `if not validated_file.exists():` and every sub-path
            # returns, so Step 10 is only reached when validated_file exists →
            # entry_ok is always True there). Forcing a RETRO_DONE + no-validation
            # state to write NEEDS_INPUT would break normal MCP-test dispatch.
            #
            # The honest, testable unit for this defensive branch is the sentinel
            # WRITE itself, which the impl agent extracts into the module-level helper
            # _write_step10_needs_input(spec_dir, feature_name). That helper is
            # exercised directly in an inline functional check AFTER this loop (search
            # for "Fixture WU-8.3" below), mirroring how enqueue_adhoc / materialize_wi
            # are tested directly rather than through compute_state.
        ]
        for case in cases:
            # Cases are 4-tuples (real_device defaults to True — behavior
            # preserving) or 5-tuples that pin real_device explicitly for the
            # device-deferral fixtures.
            name, cloud, skip_nr, expected = case[0], case[1], case[2], case[3]
            real_device = case[4] if len(case) > 4 else True
            root = _build_fixture(td_path, name)
            try:
                got = compute_state(
                    root, cloud=cloud, skip_needs_research=skip_nr,
                    real_device=real_device,
                )
            except SystemExit as exc:
                failures.append(f"[{name}] SystemExit: {exc.code}")
                continue
            for k, v in expected.items():
                if got.get(k) != v:
                    failures.append(
                        f"[{name}] expected {k}={v!r}, got {k}={got.get(k)!r}"
                    )
            # Extra assertions: plan-frontmatter selection prefers lowest phase
            if name == "plan-frontmatter-filter":
                args = got.get("sub_skill_args") or ""
                if "phase-3-corrective.md" not in args:
                    failures.append(
                        f"[{name}] expected phase-3 plan to be selected, got "
                        f"sub_skill_args={args!r}"
                    )
                if "all-phases-old.md" in args:
                    failures.append(
                        f"[{name}] Complete plan should be filtered out, "
                        f"sub_skill_args={args!r}"
                    )
            if name == "legacy-plan-diagnostics":
                diag = got.get("diagnostics") or []
                if not any("all-phases-legacy.md" in d for d in diag):
                    failures.append(
                        f"[{name}] expected diagnostics warning about legacy "
                        f"plan; got diagnostics={diag!r}"
                    )
            if name == "research-pending-only" and skip_nr:
                diag = got.get("diagnostics") or []
                if not any("research-pending skipped" in d for d in diag):
                    failures.append(
                        f"[{name}] expected research-pending diagnostics; "
                        f"got diagnostics={diag!r}"
                    )
            if name == "adhoc-brief":
                args = got.get("sub_skill_args") or ""
                if "ADHOC_BRIEF.md" not in args:
                    failures.append(
                        f"[{name}] expected sub_skill_args to reference "
                        f"ADHOC_BRIEF.md; got {args!r}"
                    )
            if name == "device-deferred-pending" and real_device:
                # The re-open MUST thread the specific deferred scenario IDs so
                # /mcp-test knows exactly which assertions to certify.
                args = got.get("sub_skill_args") or ""
                if "AQ-TE-05" not in args:
                    failures.append(
                        f"[{name}] re-open args must name the deferred scenario "
                        f"IDs (AQ-TE-05); got {args!r}"
                    )
            if name == "device-deferred-pending" and not real_device:
                diag = got.get("diagnostics") or []
                if not any("device-saturated skipped" in d for d in diag):
                    failures.append(
                        f"[{name}] expected device-saturated diagnostics; "
                        f"got diagnostics={diag!r}"
                    )
            if name == "stale-plan-all-refs-checked-flips":
                # current_step substring check: after the fix the impl agent will
                # emit something containing "stale". We do NOT assert the exact
                # string so small wording changes don't break this fixture.
                # (The primary behavioral signal is sub_skill above.)
                cs = got.get("current_step") or ""
                if cs and "stale" not in cs.lower():
                    failures.append(
                        f"[{name}] expected current_step to contain 'stale'; "
                        f"got {cs!r}"
                    )
                # sub_skill_args must reference the plan file path.
                args = got.get("sub_skill_args") or ""
                if args and "all-phases-stale.md" not in args:
                    failures.append(
                        f"[{name}] expected sub_skill_args to reference the stale "
                        f"plan file; got {args!r}"
                    )
            if name == "finalize-plan-verification-rows-only-flips":
                # Phase 8 finalization gap: the flip must reference the plan file
                # and the step must read as a stale/finalize flip (not execute).
                cs = got.get("current_step") or ""
                if cs and "stale" not in cs.lower():
                    failures.append(
                        f"[{name}] expected current_step to read as a stale flip; "
                        f"got {cs!r}"
                    )
                args = got.get("sub_skill_args") or ""
                if args and "all-phases-fin.md" not in args:
                    failures.append(
                        f"[{name}] expected sub_skill_args to reference the plan "
                        f"file; got {args!r}"
                    )
            if name == "stale-upstream-auto-wired-at-probe":
                # Post-call disk check (WU-8 Fixture 2): the auto-wiring at probe
                # start must have WRITTEN STALE_UPSTREAM.md into the feature dir.
                # RED today: check_stale_upstream is never auto-called → the file
                # doesn't exist → this assertion fails regardless of terminal_reason.
                sau_stale_sentinel = (
                    root / "docs" / "features" / "feat-sau" / "STALE_UPSTREAM.md"
                )
                if not sau_stale_sentinel.exists():
                    failures.append(
                        f"[{name}] STALE_UPSTREAM.md was NOT written to "
                        f"{sau_stale_sentinel} — check_stale_upstream not auto-wired "
                        "at probe start"
                    )
            print(
                f"  [{name}] cloud={cloud} skip_nr={skip_nr} "
                f"real_device={real_device}: "
                f"{got['current_step'] or got['terminal_reason']}"
            )

        # -------------------------------------------------------------------
        # Fixture WU-8.3: _write_step10_needs_input writes a well-formed
        # NEEDS_INPUT.md sentinel (direct helper unit test).
        # -------------------------------------------------------------------
        # The Step 10 "unexpected state" defensive branch (compute_state, the
        # `if not entry_ok:` arm) is GENUINELY UNREACHABLE through compute_state's
        # inputs — workstation Step 9 is fully guarded by
        # `if not validated_file.exists():` and every sub-path returns, so Step 10
        # is reached only when validated_file exists, where entry_ok is always
        # True. We therefore can't drive this branch via a routing fixture without
        # breaking normal MCP-test dispatch. The honest, testable unit is the
        # sentinel WRITE the branch performs, which the impl agent extracts into
        # the module-level helper _write_step10_needs_input(spec_dir, feature_name)
        # and calls from the defensive arm. We exercise that helper directly here,
        # exactly the way enqueue_adhoc / materialize_wi are tested directly below.
        #
        # RED today: _write_step10_needs_input does not exist yet → calling it
        # raises NameError ("missing symbol" RED — the standard TDD red for a new
        # function). GREEN after the impl lands the helper: NEEDS_INPUT.md exists
        # on disk, parses as kind="needs-input" with a written_by field, and its
        # body carries the `## Decision Context` H2 that the orchestrator's
        # decision-resume (Step 1g) consumes.
        fix_name_s10 = "step10-unexpected-writes-needs-input"
        s10_spec_dir = td_path / fix_name_s10 / "docs" / "features" / "feat-s10u"
        s10_spec_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Reference the helper as a module-level name (mirrors how the inline
            # checks below call enqueue_adhoc / materialize_wi directly). When the
            # symbol does not yet exist this raises NameError — the intended RED.
            _write_step10_needs_input(s10_spec_dir, "Some Feature")
            s10_ok = True
            # Assertion 1: the sentinel now EXISTS on disk.
            s10_sentinel = s10_spec_dir / "NEEDS_INPUT.md"
            if not s10_sentinel.exists():
                failures.append(
                    f"[{fix_name_s10}] NEEDS_INPUT.md was NOT written to "
                    f"{s10_sentinel} — _write_step10_needs_input must create the "
                    "sentinel the defensive branch tells the orchestrator to resolve"
                )
                s10_ok = False
            else:
                # Assertion 2a: well-formed frontmatter — parse_sentinel yields the
                # required schema fields (kind: needs-input + written_by) so the
                # orchestrator's Step 1g decision-resume can consume it.
                s10_meta = parse_sentinel(s10_sentinel) or {}
                if s10_meta.get("kind") != "needs-input":
                    failures.append(
                        f"[{fix_name_s10}] NEEDS_INPUT.md frontmatter kind must be "
                        f"'needs-input'; got {s10_meta.get('kind')!r}"
                    )
                    s10_ok = False
                if not s10_meta.get("written_by"):
                    failures.append(
                        f"[{fix_name_s10}] NEEDS_INPUT.md frontmatter must carry a "
                        f"'written_by' field; got {s10_meta.get('written_by')!r}"
                    )
                    s10_ok = False
                # Assertion 2b: well-formed body — the `## Decision Context` H2 the
                # orchestrator re-prints verbatim before AskUserQuestion, plus at
                # least one decision described under it. Kept specific (the H2 must
                # be a real heading line) but not brittle (no exact wording pinned).
                s10_text = s10_sentinel.read_text(encoding="utf-8")
                s10_body_lines = s10_text.splitlines()
                has_decision_h2 = any(
                    ln.strip() == "## Decision Context" for ln in s10_body_lines
                )
                if not has_decision_h2:
                    failures.append(
                        f"[{fix_name_s10}] NEEDS_INPUT.md body must contain a "
                        "'## Decision Context' H2 heading (the structure Step 1g "
                        "requires)"
                    )
                    s10_ok = False
                else:
                    # At least one decision must be described under the H2: either a
                    # frontmatter decisions[] entry or an H3 subsection in the body.
                    has_decision_h3 = any(
                        ln.lstrip().startswith("### ") for ln in s10_body_lines
                    )
                    decisions_fm = s10_meta.get("decisions")
                    has_decision_fm = bool(
                        isinstance(decisions_fm, list) and decisions_fm
                    )
                    # Regression guard: every entry must be a plain string, not a
                    # dict. An unquoted "key: value" YAML list item (e.g. a title
                    # containing a colon-space) parses as a nested mapping — a dict —
                    # which breaks the orchestrator's Step 1g decision-resume that
                    # expects string descriptions.
                    if has_decision_fm and not all(
                        isinstance(x, str) for x in decisions_fm
                    ):
                        failures.append(
                            f"[{fix_name_s10}] NEEDS_INPUT.md decisions[] entries must "
                            "all be strings (not dicts); got "
                            f"{[type(x).__name__ for x in decisions_fm]!r} — "
                            "ensure decision_title is quoted in the YAML list item"
                        )
                        s10_ok = False
                        has_decision_fm = False  # don't double-count as passing
                    if not (has_decision_h3 or has_decision_fm):
                        failures.append(
                            f"[{fix_name_s10}] NEEDS_INPUT.md must describe at least "
                            "one decision (an H3 subsection under '## Decision "
                            "Context' or a non-empty decisions[] frontmatter list)"
                        )
                        s10_ok = False
            print(f"  {'PASS' if s10_ok else 'FAIL'} [{fix_name_s10}] "
                  "_write_step10_needs_input writes well-formed NEEDS_INPUT.md")
        except (NameError, AttributeError) as exc:
            # Missing-symbol RED: the helper genuinely does not exist yet. The impl
            # agent will create _write_step10_needs_input and this flips to GREEN.
            failures.append(
                f"[{fix_name_s10}] _write_step10_needs_input is not defined yet "
                f"(missing-helper RED — impl must extract it): {exc}"
            )
            print(f"  FAIL [{fix_name_s10}]: helper not defined — {exc}")

        # Functional check: enqueue_adhoc prepends the queue, seeds the brief,
        # creates the spec dir, and adds a ROADMAP row.
        enq_features = td_path / "enqueue-test" / "docs" / "features"
        enq_features.mkdir(parents=True, exist_ok=True)
        (enq_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-z", "name": "Z", "spec_dir": "feat-z", "tier": 1}
            ]
        }))
        (enq_features / "ROADMAP.md").write_text("# Roadmap\n")
        enq_root = td_path / "enqueue-test"
        res = enqueue_adhoc(enq_root, "adhoc-test", "Adhoc Test", "Fix the thing")
        enq_queue = json.loads((enq_features / "queue.json").read_text())
        if not res.get("enqueued"):
            failures.append("[enqueue] enqueue_adhoc did not report enqueued=True")
        if enq_queue["queue"][0].get("id") != "adhoc-test":
            failures.append(
                f"[enqueue] expected adhoc-test at queue[0]; got "
                f"{enq_queue['queue'][0].get('id')!r}"
            )
        if enq_queue["queue"][0].get("adhoc") is not True:
            failures.append("[enqueue] queue[0] missing adhoc: true")
        if len(enq_queue["queue"]) != 2:
            failures.append(
                f"[enqueue] expected 2 queue entries; got {len(enq_queue['queue'])}"
            )
        brief = enq_features / "adhoc-test" / "ADHOC_BRIEF.md"
        if not brief.exists():
            failures.append("[enqueue] ADHOC_BRIEF.md was not written")
        elif "Fix the thing" not in brief.read_text():
            failures.append("[enqueue] ADHOC_BRIEF.md missing the brief text")
        roadmap_text = (enq_features / "ROADMAP.md").read_text()
        if "Adhoc Test" not in roadmap_text:
            failures.append("[enqueue] ROADMAP.md missing the ad-hoc row")
        # Duplicate id must be refused (enqueue_adhoc calls _die → SystemExit).
        try:
            enqueue_adhoc(enq_root, "adhoc-test", "Dup", "x")
            failures.append("[enqueue] duplicate feature_id was not refused")
        except SystemExit:
            pass
        print("  [enqueue] enqueue_adhoc prepend + brief + roadmap: ok")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-1: feature materialize (User Story → docs/features)
        # -------------------------------------------------------------------
        fix_name_fm = "materialize-feature"
        mat_root = td_path / fix_name_fm
        mat_work = mat_root / "docs" / "work"
        mat_work.mkdir(parents=True, exist_ok=True)
        (mat_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (mat_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _mat_wi_id = 42
        _mat_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _mat_wi_id,
                    "type": "User Story",
                    "title": "Build the thing",
                    "description": "Detailed description here.",
                    "acceptanceCriteria": "Given X then Y.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/42",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (mat_work / "ado-mirror.json").write_text(
            json.dumps(_mat_mirror, indent=2), encoding="utf-8"
        )
        _mat_type_map = {
            "bug": ["Bug", "Defect", "Story Bug", "Engineering Bug"],
            "feature": ["User Story", "Refactor Story", "Enabler Story", "Requirement"],
        }
        try:
            result_fm = materialize_wi(mat_root, _mat_wi_id, _mat_type_map)
            slug_fm = result_fm.get("feature_id") or result_fm.get("slug") or ""
            fm_ok = True
            # status must indicate materialized + feature pipeline
            if result_fm.get("status") not in ("materialized", "ok") and "feature" not in str(result_fm.get("status", "")):
                failures.append(
                    f"[{fix_name_fm}] expected status indicating materialized/feature, "
                    f"got {result_fm.get('status')!r}"
                )
                fm_ok = False
            # ADHOC_BRIEF.md exists and contains verbatim WI fields
            brief_fm = mat_root / "docs" / "features" / slug_fm / "ADHOC_BRIEF.md"
            if not brief_fm.exists():
                failures.append(
                    f"[{fix_name_fm}] ADHOC_BRIEF.md not found at {brief_fm}"
                )
                fm_ok = False
            else:
                brief_text = brief_fm.read_text(encoding="utf-8")
                for substr in ["Build the thing", "Detailed description here.", "Given X then Y."]:
                    if substr not in brief_text:
                        failures.append(
                            f"[{fix_name_fm}] ADHOC_BRIEF.md missing verbatim substring: {substr!r}"
                        )
                        fm_ok = False
            # SPEC.md contains the Work Item line
            spec_fm = mat_root / "docs" / "features" / slug_fm / "SPEC.md"
            if not spec_fm.exists():
                failures.append(f"[{fix_name_fm}] SPEC.md not found at {spec_fm}")
                fm_ok = False
            else:
                spec_text = spec_fm.read_text(encoding="utf-8")
                expected_wi_line = f"**Work Item:** AB#{_mat_wi_id}"
                if expected_wi_line not in spec_text:
                    failures.append(
                        f"[{fix_name_fm}] SPEC.md missing {expected_wi_line!r}"
                    )
                    fm_ok = False
            # queue.json has the slug entry
            fq_path = mat_root / "docs" / "features" / "queue.json"
            if not fq_path.exists():
                failures.append(f"[{fix_name_fm}] docs/features/queue.json not written")
                fm_ok = False
            else:
                fq = json.loads(fq_path.read_text(encoding="utf-8"))
                if not any(e.get("id") == slug_fm or e.get("spec_dir") == slug_fm for e in fq.get("queue", [])):
                    failures.append(
                        f"[{fix_name_fm}] queue.json has no entry for slug {slug_fm!r}"
                    )
                    fm_ok = False
            # read_materialized returns exactly 1 record for that wi_id
            mat_records = lazy_core.read_materialized(mat_work)
            wi_records = [r for r in mat_records if r.get("wi_id") == _mat_wi_id]
            if len(wi_records) != 1:
                failures.append(
                    f"[{fix_name_fm}] expected 1 materialized record for wi_id={_mat_wi_id}; "
                    f"got {len(wi_records)}"
                )
                fm_ok = False
            print(f"  {'PASS' if fm_ok else 'FAIL'} [{fix_name_fm}] feature materialize")
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_fm}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_fm}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-2: bug materialize (Bug → docs/bugs via subprocess)
        # -------------------------------------------------------------------
        fix_name_bm = "materialize-bug"
        bm_root = td_path / fix_name_bm
        bm_work = bm_root / "docs" / "work"
        bm_work.mkdir(parents=True, exist_ok=True)
        (bm_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (bm_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _bm_wi_id = 99
        _bm_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _bm_wi_id,
                    "type": "Bug",
                    "title": "Broken submit button",
                    "description": "The submit button does nothing.",
                    "acceptanceCriteria": "Button triggers form submission.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/99",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (bm_work / "ado-mirror.json").write_text(
            json.dumps(_bm_mirror, indent=2), encoding="utf-8"
        )
        try:
            result_bm = materialize_wi(bm_root, _bm_wi_id, _mat_type_map)
            slug_bm = result_bm.get("feature_id") or result_bm.get("slug") or ""
            bm_ok = True
            # ADHOC_BRIEF.md in docs/bugs/<slug> with verbatim fields
            brief_bm = bm_root / "docs" / "bugs" / slug_bm / "ADHOC_BRIEF.md"
            if not brief_bm.exists():
                failures.append(
                    f"[{fix_name_bm}] ADHOC_BRIEF.md not found at {brief_bm}"
                )
                bm_ok = False
            else:
                brief_bm_text = brief_bm.read_text(encoding="utf-8")
                for substr in ["Broken submit button", "The submit button does nothing.", "Button triggers form submission."]:
                    if substr not in brief_bm_text:
                        failures.append(
                            f"[{fix_name_bm}] ADHOC_BRIEF.md missing verbatim substring: {substr!r}"
                        )
                        bm_ok = False
            # docs/bugs/queue.json has a spec_dir entry for this slug
            bq_path = bm_root / "docs" / "bugs" / "queue.json"
            if not bq_path.exists():
                failures.append(f"[{fix_name_bm}] docs/bugs/queue.json not written")
                bm_ok = False
            else:
                bq = json.loads(bq_path.read_text(encoding="utf-8"))
                if not any(e.get("spec_dir") == slug_bm or e.get("id") == str(_bm_wi_id) for e in bq.get("queue", [])):
                    failures.append(
                        f"[{fix_name_bm}] bugs/queue.json has no entry with spec_dir={slug_bm!r}"
                    )
                    bm_ok = False
            # docs/features/ must NOT have a new dir for this WI
            feat_dirs_bm = [
                p.name for p in (bm_root / "docs" / "features").iterdir()
                if p.is_dir()
            ]
            if slug_bm in feat_dirs_bm:
                failures.append(
                    f"[{fix_name_bm}] bug route must NOT create docs/features/{slug_bm}"
                )
                bm_ok = False
            print(f"  {'PASS' if bm_ok else 'FAIL'} [{fix_name_bm}] bug materialize")
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_bm}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_bm}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-3: unknown type (no-op / skip)
        # -------------------------------------------------------------------
        fix_name_ut = "materialize-unknown-type"
        ut_root = td_path / fix_name_ut
        ut_work = ut_root / "docs" / "work"
        ut_work.mkdir(parents=True, exist_ok=True)
        (ut_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (ut_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _ut_wi_id = 77
        _ut_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _ut_wi_id,
                    "type": "Task",
                    "title": "A task nobody wants",
                    "description": "Just a task.",
                    "acceptanceCriteria": "Done.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/77",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (ut_work / "ado-mirror.json").write_text(
            json.dumps(_ut_mirror, indent=2), encoding="utf-8"
        )
        try:
            result_ut = materialize_wi(ut_root, _ut_wi_id, _mat_type_map)
            ut_ok = True
            # No new dir under docs/features or docs/bugs
            feat_dirs_ut = [p.name for p in (ut_root / "docs" / "features").iterdir() if p.is_dir()]
            bug_dirs_ut = [p.name for p in (ut_root / "docs" / "bugs").iterdir() if p.is_dir()]
            if feat_dirs_ut:
                failures.append(
                    f"[{fix_name_ut}] unknown-type must not create features dirs; got {feat_dirs_ut}"
                )
                ut_ok = False
            if bug_dirs_ut:
                failures.append(
                    f"[{fix_name_ut}] unknown-type must not create bugs dirs; got {bug_dirs_ut}"
                )
                ut_ok = False
            # Queue lengths unchanged (no queue files created)
            fq_ut = ut_root / "docs" / "features" / "queue.json"
            bq_ut = ut_root / "docs" / "bugs" / "queue.json"
            if fq_ut.exists() and json.loads(fq_ut.read_text())["queue"]:
                failures.append(f"[{fix_name_ut}] unknown-type must not enqueue in features")
                ut_ok = False
            if bq_ut.exists() and json.loads(bq_ut.read_text())["queue"]:
                failures.append(f"[{fix_name_ut}] unknown-type must not enqueue in bugs")
                ut_ok = False
            # materialized.json unchanged (0 records)
            ut_records = lazy_core.read_materialized(ut_work)
            if ut_records:
                failures.append(
                    f"[{fix_name_ut}] unknown-type must not append to materialized.json; "
                    f"got {ut_records}"
                )
                ut_ok = False
            # returned a skip status (did not raise)
            if result_ut.get("status") not in ("skipped", "skip", "unknown-type"):
                failures.append(
                    f"[{fix_name_ut}] expected skip status, got {result_ut.get('status')!r}"
                )
                ut_ok = False
            print(f"  {'PASS' if ut_ok else 'FAIL'} [{fix_name_ut}] unknown type → skip")
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_ut}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_ut}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-4: idempotent double-materialize
        # -------------------------------------------------------------------
        fix_name_idem = "materialize-idempotent"
        idem_root = td_path / fix_name_idem
        idem_work = idem_root / "docs" / "work"
        idem_work.mkdir(parents=True, exist_ok=True)
        (idem_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (idem_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _idem_wi_id = 55
        _idem_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _idem_wi_id,
                    "type": "User Story",
                    "title": "Idempotent feature",
                    "description": "Should only appear once.",
                    "acceptanceCriteria": "Only one record.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/55",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (idem_work / "ado-mirror.json").write_text(
            json.dumps(_idem_mirror, indent=2), encoding="utf-8"
        )
        try:
            result_idem1 = materialize_wi(idem_root, _idem_wi_id, _mat_type_map)
            result_idem2 = materialize_wi(idem_root, _idem_wi_id, _mat_type_map)
            slug_idem = result_idem1.get("feature_id") or result_idem1.get("slug") or ""
            idem_ok = True
            # materialized.json must have exactly 1 record for wi_id
            idem_records = [r for r in lazy_core.read_materialized(idem_work) if r.get("wi_id") == _idem_wi_id]
            if len(idem_records) != 1:
                failures.append(
                    f"[{fix_name_idem}] expected exactly 1 materialized record after 2 calls; "
                    f"got {len(idem_records)}"
                )
                idem_ok = False
            # queue.json has exactly 1 entry for the slug
            fq_idem = idem_root / "docs" / "features" / "queue.json"
            if not fq_idem.exists():
                failures.append(f"[{fix_name_idem}] queue.json not written")
                idem_ok = False
            else:
                fq_idem_data = json.loads(fq_idem.read_text(encoding="utf-8"))
                slug_entries = [
                    e for e in fq_idem_data.get("queue", [])
                    if e.get("id") == slug_idem or e.get("spec_dir") == slug_idem
                ]
                if len(slug_entries) != 1:
                    failures.append(
                        f"[{fix_name_idem}] expected exactly 1 queue entry for {slug_idem!r}; "
                        f"got {len(slug_entries)}"
                    )
                    idem_ok = False
            print(
                f"  {'PASS' if idem_ok else 'FAIL'} [{fix_name_idem}] "
                f"idempotent: 1 record after 2 materialize calls"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_idem}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_idem}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-5: stale detection (writer)
        # -------------------------------------------------------------------
        fix_name_stale = "stale-detection-writer"
        stale_root = td_path / fix_name_stale
        stale_work = stale_root / "docs" / "work"
        stale_work.mkdir(parents=True, exist_ok=True)
        _stale_wi_id = 101
        _stale_slug = "feat-stale-wi"
        stale_feat_dir = stale_root / "docs" / "features" / _stale_slug
        stale_feat_dir.mkdir(parents=True, exist_ok=True)
        (stale_feat_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        spec_mtime_before = (stale_feat_dir / "SPEC.md").stat().st_mtime_ns
        # Seed materialized.json with an OLDER changedDate
        lazy_core.append_materialized(stale_work, _stale_wi_id, _stale_slug, "2026-06-01T00:00:00Z")
        # Mirror has a NEWER changedDate for the same WI
        _stale_mirror = {
            "syncedAt": "2026-06-10T12:00:00Z",
            "watermark": "2026-06-10",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _stale_wi_id,
                    "type": "User Story",
                    "title": "Updated upstream WI",
                    "description": "Updated description.",
                    "acceptanceCriteria": "New AC.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/101",
                    "changedDate": "2026-06-10T00:00:00Z",
                }
            ],
        }
        (stale_work / "ado-mirror.json").write_text(
            json.dumps(_stale_mirror, indent=2), encoding="utf-8"
        )
        try:
            check_stale_upstream(stale_root)
            stale_ok = True
            # STALE_UPSTREAM.md must now exist in the feature dir
            stale_sentinel = stale_feat_dir / "STALE_UPSTREAM.md"
            if not stale_sentinel.exists():
                failures.append(
                    f"[{fix_name_stale}] STALE_UPSTREAM.md not written to {stale_sentinel}"
                )
                stale_ok = False
            # SPEC.md must NOT have been modified (mtime_ns unchanged)
            spec_mtime_after = (stale_feat_dir / "SPEC.md").stat().st_mtime_ns
            if spec_mtime_after != spec_mtime_before:
                failures.append(
                    f"[{fix_name_stale}] SPEC.md was clobbered (mtime changed)"
                )
                stale_ok = False
            print(
                f"  {'PASS' if stale_ok else 'FAIL'} [{fix_name_stale}] "
                f"stale detection writes STALE_UPSTREAM.md, preserves SPEC.md"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_stale}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_stale}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-6: stale halt (reader) — compute_state returns
        #   terminal_reason == "stale_upstream" when STALE_UPSTREAM.md is present
        # -------------------------------------------------------------------
        fix_name_halt = "stale-halt-reader"
        halt_root = td_path / fix_name_halt
        halt_features = halt_root / "docs" / "features"
        halt_features.mkdir(parents=True, exist_ok=True)
        (halt_features / "ROADMAP.md").write_text("# Roadmap\n")
        (halt_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stale-halt", "name": "Stale Halt Feature",
                 "spec_dir": "feat-stale-halt", "tier": 1}
            ]
        }))
        halt_dir = halt_features / "feat-stale-halt"
        halt_dir.mkdir()
        (halt_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (halt_dir / "RESEARCH.md").write_text("# R\n")
        (halt_dir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Drop a STALE_UPSTREAM.md into the feature dir
        (halt_dir / "STALE_UPSTREAM.md").write_text(
            "Upstream WI changed on 2026-06-10 — re-materialize required.\n",
            encoding="utf-8",
        )
        try:
            got_halt = compute_state(halt_root, cloud=False, real_device=True)
            halt_ok = True
            if got_halt.get("terminal_reason") != "stale_upstream":
                failures.append(
                    f"[{fix_name_halt}] expected terminal_reason='stale_upstream', "
                    f"got {got_halt.get('terminal_reason')!r} "
                    f"(current_step={got_halt.get('current_step')!r})"
                )
                halt_ok = False
            # Must NOT have routed to a normal work step
            if got_halt.get("sub_skill") is not None:
                failures.append(
                    f"[{fix_name_halt}] stale halt must not dispatch a sub_skill; "
                    f"got sub_skill={got_halt.get('sub_skill')!r}"
                )
                halt_ok = False
            print(
                f"  {'PASS' if halt_ok else 'FAIL'} [{fix_name_halt}] "
                f"stale halt: terminal_reason={got_halt.get('terminal_reason')!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_name_halt}] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture WU-4.2-1: scoped-feature-id
        # Two actionable ad-hoc features; default picks the FIRST (feat-scope-alpha),
        # so scoping to the SECOND (feat-scope-beta) proves the filter took effect.
        # scope_feature_id is now implemented; the TypeError guard below is dead code
        # retained for harness symmetry.
        # -------------------------------------------------------------------
        fix_scope_root = td_path / "scope-filter"
        scope_features = fix_scope_root / "docs" / "features"
        scope_features.mkdir(parents=True, exist_ok=True)
        (scope_features / "ROADMAP.md").write_text("# Roadmap\n")
        (scope_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-scope-alpha", "name": "Scope Alpha",
                 "spec_dir": "feat-scope-alpha", "tier": 1},
                {"id": "feat-scope-beta", "name": "Scope Beta",
                 "spec_dir": "feat-scope-beta", "tier": 1},
            ]
        }))
        for fid in ("feat-scope-alpha", "feat-scope-beta"):
            fdir = scope_features / fid
            fdir.mkdir()
            (fdir / "SPEC.md").write_text(
                "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
            )
            (fdir / "RESEARCH.md").write_text("# R\n")
            (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Defensive: scope_feature_id is implemented; the TypeError guard below is dead code retained for harness symmetry.
        try:
            got_scoped = compute_state(
                fix_scope_root, cloud=False, real_device=True,
                scope_feature_id="feat-scope-beta",
            )
            # If we reach here the param already exists; validate the filter result.
            if got_scoped.get("feature_id") != "feat-scope-beta":
                failures.append(
                    f"[scoped-feature-id] expected feature_id='feat-scope-beta', "
                    f"got {got_scoped.get('feature_id')!r}"
                )
                print("  FAIL [scoped-feature-id] scoping did not select feat-scope-beta")
            else:
                print("  PASS [scoped-feature-id] scope_feature_id selected feat-scope-beta")
        except TypeError as e:
            failures.append(
                f"[scoped-feature-id] TypeError (scope_feature_id param not yet "
                f"implemented): {e}"
            )
            print(f"  FAIL [scoped-feature-id] TypeError — {e}")

        # -------------------------------------------------------------------
        # Fixture WU-4.2-2: baseline-regression-default (GREEN GUARD)
        # Same two-feature queue; default (no scope param) must pick the FIRST
        # actionable feature (feat-scope-alpha). This fixture is intentionally
        # GREEN now and must stay GREEN after the impl lands — it proves the
        # upcoming change is non-breaking.
        # -------------------------------------------------------------------
        try:
            got_default = compute_state(
                fix_scope_root, cloud=False, real_device=True,
            )
            default_ok = True
            if got_default.get("feature_id") != "feat-scope-alpha":
                failures.append(
                    f"[baseline-regression-default] expected feature_id='feat-scope-alpha', "
                    f"got {got_default.get('feature_id')!r}"
                )
                default_ok = False
            if got_default.get("current_step") != "Step 6: plan feature (phases + plan)":
                failures.append(
                    f"[baseline-regression-default] expected current_step='Step 6: plan "
                    f"feature (phases + plan)', got {got_default.get('current_step')!r}"
                )
                default_ok = False
            print(
                f"  {'PASS' if default_ok else 'FAIL'} [baseline-regression-default] "
                f"default picks feat-scope-alpha at "
                f"{got_default.get('current_step')!r}"
            )
        except SystemExit as exc:
            failures.append(f"[baseline-regression-default] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture: scoped-feature-id-not-found  (RED until impl lands)
        # Same two-feature queue as the scoped-feature-id fixture above; but
        # the scope_feature_id is a typo'd id that matches NO entry.
        # EXPECTED: terminal_reason == "scoped-id-not-found"
        # CURRENT (pre-fix): falls through to terminal_reason == "all-features-complete"
        # The impl agent must emit a distinct terminal so callers can distinguish
        # "queue exhausted" from "id was never in the queue at all".
        # -------------------------------------------------------------------
        fix_not_found = "scoped-feature-id-not-found"
        try:
            got_not_found = compute_state(
                fix_scope_root, cloud=False, real_device=True,
                scope_feature_id="feat-typo-does-not-exist",
            )
            actual_tr = got_not_found.get("terminal_reason")
            if actual_tr == "scoped-id-not-found":
                print(f"  PASS [{fix_not_found}] terminal_reason='scoped-id-not-found' (impl landed)")
            else:
                failures.append(
                    f"[{fix_not_found}] expected terminal_reason='scoped-id-not-found', "
                    f"got {actual_tr!r}"
                )
                print(f"  FAIL [{fix_not_found}] expected 'scoped-id-not-found', got {actual_tr!r}")
        except (TypeError, SystemExit) as e:
            failures.append(f"[{fix_not_found}] unexpected exception: {type(e).__name__}: {e}")
            print(f"  FAIL [{fix_not_found}] {type(e).__name__} — {e}")

        # -------------------------------------------------------------------
        # Fixture WU-1-park: --park-needs-input mode (Phase 4)
        #
        # Two-feature queue:
        #   feat-parked  — carries NEEDS_INPUT.md (well-formed, 1 decision)
        #   feat-after   — actionable (Open, SPEC+RESEARCH present)
        #
        # Sub-fixture A: WITHOUT park_needs_input → terminal_reason=="needs-input"
        #                AND "parked" key ABSENT from output.
        # Sub-fixture B: WITH park_needs_input=True → feat-after is dispatched,
        #                output has "parked" list with one entry whose id matches
        #                feat-parked and decision_count==1.
        # Sub-fixture C: RESOLVED sentinel (NEEDS_INPUT.md removed) → feat-parked
        #                is dispatched normally, "parked" is empty.
        # -------------------------------------------------------------------
        park_root = td_path / "park-needs-input"
        park_features = park_root / "docs" / "features"
        park_features.mkdir(parents=True, exist_ok=True)
        (park_features / "ROADMAP.md").write_text("# Roadmap\n")
        (park_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-parked", "name": "Parked Feature",
                 "spec_dir": "feat-parked", "tier": 1},
                {"id": "feat-after", "name": "After Feature",
                 "spec_dir": "feat-after", "tier": 1},
            ]
        }))
        # feat-parked: Open spec + RESEARCH + NEEDS_INPUT.md (1 decision, date set)
        parked_dir = park_features / "feat-parked"
        parked_dir.mkdir()
        (parked_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (parked_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (parked_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
        needs_input_content = (
            "---\n"
            "kind: needs-input\n"
            "feature_id: feat-parked\n"
            "written_by: spec-phases\n"
            "decisions:\n"
            "  - Choose auth strategy\n"
            "date: 2026-06-10\n"
            "---\n\n"
            "# Needs Input\n"
        )
        park_sentinel = parked_dir / "NEEDS_INPUT.md"
        park_sentinel.write_text(needs_input_content, encoding="utf-8")
        # feat-after: actionable (Open, SPEC+RESEARCH, no NEEDS_INPUT.md)
        after_dir = park_features / "feat-after"
        after_dir.mkdir()
        (after_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (after_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (after_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")

        # Sub-fixture A: without park_needs_input → needs-input halt, NO "parked" key
        fix_park_default = "park-needs-input-default-halt"
        try:
            got_park_default = compute_state(park_root, cloud=False, real_device=True)
            pda_ok = True
            actual_tr_park = got_park_default.get("terminal_reason")
            # CORRECT assertion: without the flag, needs-input halt must fire.
            if actual_tr_park != "needs-input":
                failures.append(
                    f"[{fix_park_default}] expected terminal_reason='needs-input', "
                    f"got {actual_tr_park!r}"
                )
                pda_ok = False
            # CRITICAL: "parked" key must be ABSENT when not in park mode.
            if "parked" in got_park_default:
                failures.append(
                    f"[{fix_park_default}] 'parked' key must be absent in default mode; "
                    f"got parked={got_park_default['parked']!r}"
                )
                pda_ok = False
            print(
                f"  {'PASS' if pda_ok else 'FAIL'} [{fix_park_default}] "
                f"default: terminal_reason={actual_tr_park!r}, parked key absent={('parked' not in got_park_default)}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_default}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_default}] SystemExit: {exc.code}")

        # Sub-fixture B: WITH park_needs_input=True → feat-after dispatched,
        # output["parked"] has one entry with id="feat-parked", decision_count=1.
        fix_park_mode = "park-needs-input-mode-skip"
        try:
            got_park_mode = compute_state(
                park_root, cloud=False, real_device=True, park_needs_input=True
            )
            pmode_ok = True
            # The halt must NOT be needs-input (feat-parked is skipped)
            actual_tr_mode = got_park_mode.get("terminal_reason")
            if actual_tr_mode == "needs-input":
                failures.append(
                    f"[{fix_park_mode}] terminal_reason must NOT be 'needs-input' in park mode; "
                    f"got {actual_tr_mode!r}"
                )
                pmode_ok = False
            # feat-after must be dispatched as current
            if got_park_mode.get("feature_id") != "feat-after":
                failures.append(
                    f"[{fix_park_mode}] expected feature_id='feat-after', "
                    f"got {got_park_mode.get('feature_id')!r}"
                )
                pmode_ok = False
            # "parked" key must be present and contain one entry
            parked_list = got_park_mode.get("parked")
            if not isinstance(parked_list, list) or len(parked_list) != 1:
                failures.append(
                    f"[{fix_park_mode}] expected parked=[...1 entry...], "
                    f"got {parked_list!r}"
                )
                pmode_ok = False
            elif parked_list[0].get("id") != "feat-parked":
                failures.append(
                    f"[{fix_park_mode}] parked[0].id must be 'feat-parked', "
                    f"got {parked_list[0].get('id')!r}"
                )
                pmode_ok = False
            elif parked_list[0].get("decision_count") != 1:
                failures.append(
                    f"[{fix_park_mode}] parked[0].decision_count must be 1, "
                    f"got {parked_list[0].get('decision_count')!r}"
                )
                pmode_ok = False
            print(
                f"  {'PASS' if pmode_ok else 'FAIL'} [{fix_park_mode}] "
                f"park mode: dispatched={got_park_mode.get('feature_id')!r}, "
                f"parked count={len(parked_list) if isinstance(parked_list, list) else 'N/A'}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_mode}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_mode}] SystemExit: {exc.code}")

        # Sub-fixture C: RESOLVED — remove NEEDS_INPUT.md → feat-parked is dispatched
        # normally and parked[] is empty.
        fix_park_resolved = "park-needs-input-resolved-reenter"
        try:
            park_sentinel.unlink()  # resolve the sentinel
            got_park_resolved = compute_state(
                park_root, cloud=False, real_device=True, park_needs_input=True
            )
            presolved_ok = True
            # feat-parked is now first and actionable — it must be dispatched.
            if got_park_resolved.get("feature_id") != "feat-parked":
                failures.append(
                    f"[{fix_park_resolved}] expected feature_id='feat-parked' after resolution, "
                    f"got {got_park_resolved.get('feature_id')!r}"
                )
                presolved_ok = False
            # parked[] must be empty (no items parked this probe).
            parked_resolved = got_park_resolved.get("parked")
            if not isinstance(parked_resolved, list) or len(parked_resolved) != 0:
                failures.append(
                    f"[{fix_park_resolved}] expected parked=[], "
                    f"got {parked_resolved!r}"
                )
                presolved_ok = False
            print(
                f"  {'PASS' if presolved_ok else 'FAIL'} [{fix_park_resolved}] "
                f"resolved: dispatched={got_park_resolved.get('feature_id')!r}, "
                f"parked={parked_resolved!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_resolved}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_resolved}] SystemExit: {exc.code}")

        # Sub-fixture D: BLOCKED.md precedence — feat-parked carries BOTH
        # BLOCKED.md AND NEEDS_INPUT.md.  Under park mode it must STILL halt as
        # "blocked", not be silently parked.  This locks FIX 1 of the code review.
        fix_park_blocked_precedence = "park-needs-input-blocked-precedence"
        try:
            # Restore NEEDS_INPUT.md (removed in sub-fixture C) and add BLOCKED.md.
            park_sentinel.write_text(needs_input_content, encoding="utf-8")
            _write_yaml_sentinel(
                parked_dir / "BLOCKED.md", "blocked",
                feature_id="feat-parked", phase="Spec",
                blocked_at="2026-06-10T00:00:00Z", retry_count=0,
            )
            got_park_blocked = compute_state(
                park_root, cloud=False, real_device=True, park_needs_input=True
            )
            pbp_ok = True
            # Must halt as "blocked" — NOT parked, not dispatched.
            actual_tr_pbp = got_park_blocked.get("terminal_reason")
            if actual_tr_pbp != "blocked":
                failures.append(
                    f"[{fix_park_blocked_precedence}] expected terminal_reason='blocked' "
                    f"(BLOCKED.md must retain precedence over park-mode); "
                    f"got {actual_tr_pbp!r}"
                )
                pbp_ok = False
            # feat-parked must be the reported feature (it is the one that is blocked).
            if got_park_blocked.get("feature_id") != "feat-parked":
                failures.append(
                    f"[{fix_park_blocked_precedence}] expected feature_id='feat-parked', "
                    f"got {got_park_blocked.get('feature_id')!r}"
                )
                pbp_ok = False
            # "parked" key must NOT contain feat-parked (it was NOT parked).
            parked_pbp = got_park_blocked.get("parked", [])
            parked_ids = [e.get("id") for e in parked_pbp if isinstance(e, dict)]
            if "feat-parked" in parked_ids:
                failures.append(
                    f"[{fix_park_blocked_precedence}] feat-parked must NOT appear in "
                    f"parked[] when BLOCKED.md is present; got parked={parked_pbp!r}"
                )
                pbp_ok = False
            print(
                f"  {'PASS' if pbp_ok else 'FAIL'} [{fix_park_blocked_precedence}] "
                f"blocked-precedence: terminal_reason={actual_tr_pbp!r}, "
                f"feat-parked in parked[]={'feat-parked' in parked_ids}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_blocked_precedence}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_blocked_precedence}] SystemExit: {exc.code}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll smoke tests passed.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--cloud", action="store_true",
                        help="Use /lazy-cloud state machine variants")
    parser.add_argument("--skip-needs-research", action="store_true",
                        help=("Skip queue entries that would terminate on "
                              "needs-research; emit terminal_reason "
                              "'queue-blocked-on-research' when the queue is "
                              "exhausted with only research-pending features remaining."))
    parser.add_argument("--repo-root", default=os.getcwd(),
                        help="Project root (default: $PWD)")
    parser.add_argument("--real-device", choices=["yes", "no", "auto"], default="auto",
                        help=("Whether THIS host has a real audio output device "
                              "(governs real-device-only MCP-assertion deferral). "
                              "'auto' reads $ALGOBOOTH_REAL_AUDIO_DEVICE (absent → "
                              "'no'). The orchestrator probes the live backend "
                              "(get_audio_mode: cpal & not forced) and may pass "
                              "yes/no explicitly. Ignored under --cloud (cloud has "
                              "no device)."))
    parser.add_argument("--test", action="store_true",
                        help="Run fixture smoke tests instead of computing state")
    parser.add_argument("--backfill-receipts", action="store_true",
                        help=("One-shot migration: write COMPLETED.md "
                              "(provenance: backfilled-unverified) for every "
                              "queue feature that claims completion but lacks a "
                              "receipt. Grandfathers pre-gating completions."))
    # Ad-hoc enqueue mode: insert a feature at the top of the queue and exit.
    parser.add_argument("--enqueue-adhoc", action="store_true",
                        help=("Prepend an ad-hoc feature to docs/features/queue.json "
                              "(requires --id and --name; --brief seeds ADHOC_BRIEF.md)."))
    parser.add_argument("--id", help="Ad-hoc feature id (kebab-case).")
    parser.add_argument("--name", help="Ad-hoc feature human-readable name.")
    parser.add_argument("--brief", default="",
                        help="One-paragraph ad-hoc task brief (seeds ADHOC_BRIEF.md).")
    parser.add_argument("--spec-dir", default=None,
                        help="Spec dir under docs/features/ (default: same as --id).")
    parser.add_argument("--tier", type=int, default=0,
                        help="Tier for the ad-hoc entry (default: 0).")
    parser.add_argument("--materialize-wi", type=int, default=None,
                        help="Materialize ADO work item <id> from docs/work/ado-mirror.json into a doc pipeline.")
    parser.add_argument("--feature-id", default=None,
                        help="Scope this run to a single feature by id (queue entry id). Absent → single-current default.")
    parser.add_argument("--park-needs-input", action="store_true",
                        help=(
                            "OPT-IN park mode: when active, a feature carrying an unresolved "
                            "NEEDS_INPUT.md is SKIPPED (parked) rather than halting the queue. "
                            "The parked item is reported in the 'parked[]' output array and "
                            "re-enters automatically once NEEDS_INPUT.md is resolved/renamed. "
                            "Without this flag, output is byte-identical to the default behavior "
                            "('parked' key is entirely absent and the needs-input halt fires as today)."
                        ))
    parser.add_argument("--verify-ledger", default=None, metavar="SPEC_PATH",
                        help=(
                            "Scripted completion-ledger guard (replaces the prose guard blocks "
                            "in the lazy skills). Verifies: (1) clean working tree, "
                            "(2) HEAD == @{u}, (3) all implementation plans are status: Complete, "
                            "(4) no real (non-verification) unchecked deliverables in SPEC_PATH/PHASES.md. "
                            "With --plan PLAN, checks 3+4 narrow to that plan part's phase scope "
                            "(plan_complete = the plan's own status: Complete; deliverables_done = "
                            "no unchecked non-verification rows in the plan's phases). "
                            "Emits a JSON verdict and exits 0 on pass, 1 on first failing check."
                        ))
    parser.add_argument("--apply-pseudo", nargs=2, default=None, metavar=("NAME", "SPEC_PATH"),
                        help="Single-author the deterministic sentinel/receipt write for a lazy pseudo-skill.")
    parser.add_argument("--plan", default=None,
                        help="Plan-file path for __flip_plan_complete_*__ pseudo-skills AND "
                             "for plan-scoped --verify-ledger (Phase 9 WU-3).")
    parser.add_argument("--apply-date", default=None,
                        help="Override date (YYYY-MM-DD) for --apply-pseudo writes.")
    parser.add_argument("--reason", default=None,
                        help="Reason string for __write_deferred_non_cloud__.")
    parser.add_argument("--deferred-step", type=int, default=None,
                        help="deferred_step for __write_deferred_non_cloud__.")
    parser.add_argument("--neutralize-sentinel", default=None, metavar="PATH",
                        help="Rename a resolved sentinel to the canonical *_RESOLVED_<date> form (collision-safe).")
    parser.add_argument("--repeat-count", action="store_true",
                        help="Persist the probe signature and emit a 'repeat_count' field "
                             "(consecutive identical-probe count) for mechanical loop detection. "
                             "ADVANCES the persisted streak — reserve for the single dispatch-bound "
                             "probe per cycle. Without this flag, output is byte-identical to the "
                             "default and no state file is written.")
    parser.add_argument("--repeat-count-peek", action="store_true",
                        help="Like --repeat-count but PEEK only: compute and emit the would-be "
                             "'repeat_count' WITHOUT advancing the persisted streak (no state-file "
                             "write). Use for diagnostic/inspection probes so they do not inflate "
                             "the streak. Mutually exclusive with --repeat-count.")
    parser.add_argument("--probe", action="store_true",
                        help="Fold git-guard results + a pre-formatted cycle-header line into the "
                             "probe JSON (orchestrator happy-path payload). Without this flag, output "
                             "is byte-identical to the default.")
    parser.add_argument("--emit-prompt", action="store_true",
                        help="Enrich the probe JSON with cycle_prompt + cycle_model "
                             "(script-assembled cycle dispatch prompt; composes with "
                             "--repeat-count for loop detection).")
    parser.add_argument("--forward-cycles", type=int, default=None,
                        help="Orchestrator forward-cycle count (for --probe cycle header).")
    parser.add_argument("--meta-cycles", type=int, default=None,
                        help="Orchestrator meta-cycle count (for --probe cycle header).")
    parser.add_argument("--max-cycles", type=int, default=None,
                        help="Orchestrator max-cycles ceiling (for --probe cycle header).")
    # Phase 1 run-lifecycle flags: --run-start writes the marker (pipeline=feature
    # for this script), --run-end deletes it.  Both print a JSON result and exit
    # immediately, like other action flags.  All new Phase 1 behavior (registry
    # writes, counter advances) is unreachable without first calling --run-start.
    parser.add_argument("--run-start", action="store_true",
                        help=(
                            "Write the run marker to the state dir (pipeline=feature), "
                            "gating registry and counter side-effects for this run. "
                            "Uses --cloud, --repo-root, and --max-cycles when present. "
                            "Prints the marker JSON and exits."
                        ))
    parser.add_argument("--run-end", action="store_true",
                        help=(
                            "Delete the run marker from the state dir. "
                            "Call on every terminal run path to avoid haunting the "
                            "next session. Prints {\"run_marker_deleted\": true|false} "
                            "and exits."
                        ))
    # Phase 3/4: --emit-dispatch <class> assembles and registers a fully-bound
    # dispatch prompt for one of the seven dispatch classes (six from Phase 3
    # plus the Phase 4 'hardening' class).  It is an
    # action flag like --run-start: it exits immediately, does NOT run the
    # normal state computation, and does NOT require --repo-root.
    # Success → JSON {dispatch_prompt, dispatch_model, dispatch_class}, exit 0.
    # Refusal → JSON {dispatch_prompt: null, dispatch_model: null,
    #                  dispatch_class, dispatch_prompt_refused: <reason>}, exit 1.
    # Marker present → registers the emission (write-through to registry).
    # Marker absent  → peek semantics (prompt produced, no registry write).
    parser.add_argument("--emit-dispatch", metavar="CLASS",
                        help=(
                            "Emit a fully-bound dispatch prompt for the named "
                            "dispatch class (apply-resolution, input-audit, "
                            "investigation, recovery, coherence-recovery, "
                            "needs-runtime-redispatch, hardening). Outputs JSON and exits. "
                            "Marker present → registers the emission. "
                            "Marker absent → peek only (no registry write). "
                            "Use --context KEY=VALUE (repeatable) to supply "
                            "class-specific token bindings."
                        ))
    parser.add_argument("--context", action="append", metavar="KEY=VALUE",
                        default=[],
                        help=(
                            "Supply a context key=value for --emit-dispatch. "
                            "Repeatable. Split on the first '=' only."
                        ))
    # ISSUE 3 (d8-effect-chains live run, 2026-06-14): long/complex --context
    # values (e.g. a ~1500-char failure_summary with commas/colons/parens/newlines)
    # are brittle through the shell + a single inline --context flag. Two robust
    # large-value channels, both bypassing shell quoting entirely:
    #   --context-file PATH : read a JSON object {key: value, ...} from a file.
    #   --context-stdin     : read the SAME JSON object from stdin.
    # Both MERGE into the --context KEY=VALUE dict (inline --context wins on a key
    # collision, since it is the most explicit). Values may contain ANY characters
    # — newlines, commas, colons, parens — because JSON, not the shell, frames them.
    parser.add_argument("--context-file", default=None, metavar="PATH",
                        help=(
                            "With --emit-dispatch: read a JSON object of context "
                            "key/value pairs from PATH. Robust channel for long "
                            "values with punctuation/newlines that would be mangled "
                            "as inline --context KEY=VALUE. Merged with --context "
                            "(inline --context wins on collision)."
                        ))
    parser.add_argument("--context-stdin", action="store_true",
                        help=(
                            "With --emit-dispatch: read a JSON object of context "
                            "key/value pairs from stdin. Same merge semantics as "
                            "--context-file. Use for very large failure_summary "
                            "payloads piped from the orchestrator."
                        ))
    # Phase 7 WU-7.1 / WU-7.4: --run-end behavior modifiers.
    #   --ack-unhardened : proceed with --run-end even when unacked guard denials
    #                      remain in the deny ledger (the override is recorded in
    #                      the run-end output so retros can grade it).
    #   --next-route TEXT: the probed next route, REQUIRED for a checkpoint
    #                      run-end; written into lazy-run-checkpoint.json.
    # The run-end reason ({terminal,checkpoint}) reuses the existing free-text
    # --reason flag (default terminal) — see the run-end handler.
    parser.add_argument("--ack-unhardened", action="store_true",
                        help=(
                            "With --run-end: proceed even when unacked guard "
                            "denials remain in the deny ledger. The override is "
                            "recorded in the run-end output for retro grading."
                        ))
    parser.add_argument("--next-route", default=None, metavar="TEXT",
                        help=(
                            "With --run-end --reason checkpoint: the probed next "
                            "route to resume with (written into the checkpoint "
                            "file and echoed by the next --run-start)."
                        ))
    # Phase 7 (lazy-validation-readiness) stop-authorization gates.
    # Motivating incident 2026-06-14: attended /lazy-batch 50 stopped at 5/50
    # without operator authorization.  These flags close the enforcement gap
    # between the prose-only prior constraint and the script gate.
    #
    # --unattended: pass at --run-start for scheduled/cron invocations.
    #   Interactive /lazy-batch does NOT pass it → defaults attended=True.
    #   An unattended run may checkpoint-stop without operator authorization
    #   (the sanctioned overnight-pause path).
    #
    # --operator-authorized: pass at --run-end when the operator has explicitly
    #   confirmed the stop via the budget-and-queue-guard AskUserQuestion.
    #   INDEPENDENT of --ack-unhardened (hardening-debt gate) — both gates can
    #   apply simultaneously; each checks its own concern.
    #
    # --terminal-reason REASON: supply the exact stop-terminal reason for
    #   --run-end --reason terminal.  If the reason is NOT in
    #   lazy_core.SANCTIONED_STOP_TERMINAL and --operator-authorized is absent,
    #   the run-end is REFUSED (exit 1, marker kept).  Omitting --terminal-reason
    #   is backward-compatible (legacy behavior) but adds a 'deprecation' note.
    parser.add_argument("--unattended", action="store_true",
                        help=(
                            "With --run-start: write attended=False into the run "
                            "marker (scheduled/cron/unattended invocation). "
                            "Interactive /lazy-batch does NOT pass this flag — the "
                            "default attended=True enables the stop-authorization "
                            "gate that prevents unilateral checkpoint stops."
                        ))
    parser.add_argument("--operator-authorized", action="store_true",
                        help=(
                            "With --run-end: bypass the stop-authorization gate "
                            "(checkpoint on attended run, or non-sanctioned terminal "
                            "reason). Pass ONLY after the operator explicitly confirms "
                            "the stop via the budget-and-queue-guard AskUserQuestion. "
                            "Independent of --ack-unhardened (hardening-debt gate)."
                        ))
    parser.add_argument("--terminal-reason", default=None, metavar="REASON",
                        help=(
                            "With --run-end --reason terminal: the explicit stop "
                            "reason token (e.g. 'all-features-complete', 'max-cycles'). "
                            "Must be in lazy_core.SANCTIONED_STOP_TERMINAL or "
                            "--operator-authorized must be passed. Omitting this flag "
                            "is backward-compatible but adds a deprecation note to the "
                            "output."
                        ))
    # Retro staleness anchor: the SINGLE source of truth for "how many phases
    # does this PHASES.md have right now". /retro's `phase_count_at_retro` writer
    # MUST use this (not an ad-hoc `grep -c '^### Phase'`) so the count it records
    # is byte-identical to what `retro_staleness()` later compares against via
    # `len(parse_phases(...))`. A divergent counter is exactly what produced the
    # d8-session-format permanent-stale loop (a `## Phase Summary` h2 the grep
    # missed but the old parse_phases regex over-counted). Prints the integer
    # count and exits; PHASES.md absent → prints 0.
    parser.add_argument("--count-phases", default=None, metavar="PHASES_PATH",
                        help=(
                            "Print len(parse_phases(PHASES_PATH)) and exit — the "
                            "canonical phase-section count for the retro staleness "
                            "anchor. Use this for `phase_count_at_retro`; never an "
                            "ad-hoc grep. Missing file → 0."
                        ))
    args = parser.parse_args()

    # --repeat-count (advances the streak) and --repeat-count-peek (reads it
    # without advancing) are mutually exclusive — a single probe cannot both
    # advance and peek the persisted streak.
    if args.repeat_count and args.repeat_count_peek:
        _die("--repeat-count and --repeat-count-peek are mutually exclusive")

    # --count-phases: canonical phase-section count for the retro staleness
    # anchor. Exits immediately like the other action flags. Goes through the
    # SAME parse_phases() that retro_staleness() uses, so the written
    # phase_count_at_retro can never disagree with the later staleness compare.
    if args.count_phases is not None:
        phases_path = Path(args.count_phases)
        if not phases_path.exists():
            sys.stdout.write("0\n")
            return 0
        try:
            text = phases_path.read_text(encoding="utf-8")
        except OSError as exc:
            _die(f"--count-phases: cannot read {phases_path}: {exc}")
        sys.stdout.write(f"{len(lazy_core.parse_phases(text))}\n")
        return 0

    # Phase 1 run-lifecycle dispatch: --run-start / --run-end exit immediately
    # like all other action flags so they compose cleanly with orchestrator
    # scripting (e.g. ``python lazy-state.py --run-start --cloud --max-cycles 20``).
    if args.run_start:
        # Write the marker for the feature pipeline.  cloud, repo_root, and
        # max_cycles are taken from the matching existing flags so no new flags
        # are needed for those values.
        # Phase 7 / lazy-validation-readiness: pass attended=not args.unattended
        # so interactive /lazy-batch runs (which do NOT pass --unattended) default
        # to attended=True, enabling the stop-authorization gate on --run-end.
        # Scheduled/cron invocations pass --unattended → attended=False → the
        # overnight-pause checkpoint path is allowed without operator authorization.
        marker = lazy_core.write_run_marker(
            pipeline="feature",
            cloud=args.cloud,
            repo_root=args.repo_root,
            max_cycles=args.max_cycles,
            attended=not args.unattended,
        )
        out: dict = dict(marker)
        # Phase 7 WU-7.4: consume any checkpoint left by a prior checkpoint
        # run-end and echo it as resume context (consume-once — the file is
        # deleted on read).  No checkpoint → field omitted.
        checkpoint = lazy_core.consume_run_checkpoint()
        if checkpoint is not None:
            out["resumed_from_checkpoint"] = checkpoint
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.run_end:
        # Phase 7: the run-end reason reuses the existing free-text --reason flag
        # (default "terminal"; "checkpoint" triggers the WU-7.4 checkpoint write).
        reason = args.reason or "terminal"
        if reason not in ("terminal", "checkpoint"):
            _die("--run-end --reason must be 'terminal' or 'checkpoint'")

        # WU-7.1: refuse to retire the marker while unacked guard denials remain,
        # unless --ack-unhardened was passed (the override is recorded for retros).
        # This gate is INDEPENDENT of the Phase 7 stop-authorization gate below —
        # both can apply; each checks its own concern.
        pending = lazy_core.pending_hardening()
        override_note = None
        if pending > 0:
            if not args.ack_unhardened:
                # Refuse: marker is LEFT IN PLACE so the run is not falsely retired.
                sys.stdout.write(json.dumps({
                    "run_marker_deleted": False,
                    "refused": (
                        f"{pending} unacked guard denial(s) remain in the deny "
                        f"ledger. Each denial owes a hardening round: re-run "
                        f"`--emit-dispatch hardening` once per pending denial "
                        f"(FIFO-acked), or pass --ack-unhardened to override. "
                        f"The marker was NOT deleted."
                    ),
                    "pending_hardening": pending,
                }, indent=2) + "\n")
                return 1
            # Override path: proceed, but mark it clearly so retros grade it.
            override_note = (
                f"OVERRIDE: --ack-unhardened retired the run with {pending} "
                f"unacked guard denial(s) still pending in the deny ledger."
            )

        # -----------------------------------------------------------------------
        # Phase 7 (lazy-validation-readiness) stop-authorization gates.
        #
        # Motivating incident 2026-06-14: an attended /lazy-batch 50 run stopped
        # at 5/50 cycles via --run-end --reason checkpoint without operator
        # authorization.  These gates make unilateral stops mechanically impossible.
        #
        # CHECKPOINT GATE: an attended run may NOT checkpoint-stop without
        #   --operator-authorized.  The marker's attended field defaults to True
        #   when absent (legacy marker → stricter gate = safer default).
        #   Unattended runs and operator-authorized stops proceed normally.
        #
        # TERMINAL-REASON GATE: if --terminal-reason is supplied, it must be in
        #   lazy_core.SANCTIONED_STOP_TERMINAL or --operator-authorized must be
        #   present.  A fabricated/unknown reason is refused.  Omitting
        #   --terminal-reason is backward-compatible but adds a deprecation note.
        #
        # CRITICAL: on ANY refusal, the marker MUST be left on disk.  A refused
        # stop must not retire the run — the orchestrator must continue or
        # escalate to the operator AskUserQuestion path.
        # -----------------------------------------------------------------------

        if reason == "checkpoint":
            # Read the marker to learn attendedness.  Default True when marker
            # is absent or lacks the 'attended' field (legacy → stricter gate).
            marker_now = lazy_core.read_run_marker()
            attended = True  # fallback: absent/legacy marker → treated as attended
            if marker_now is not None:
                attended = marker_now.get("attended", True)

            if attended and not args.operator_authorized:
                # REFUSE: keep marker + registry in place.  The orchestrator
                # must either continue the loop or route through the operator
                # AskUserQuestion and pass --operator-authorized only after
                # confirmation.  An attended run may never checkpoint-stop
                # unilaterally (this is the core fix for the 2026-06-14 incident).
                sys.stdout.write(json.dumps({
                    "run_marker_deleted": False,
                    "refused": (
                        "Stop-authorization gate: this is an ATTENDED run "
                        "(attended=True in the marker). A checkpoint stop requires "
                        "explicit operator authorization. The orchestrator must "
                        "either (a) continue the loop, or (b) present the "
                        "budget-and-queue-guard AskUserQuestion to the operator "
                        "and re-invoke --run-end --reason checkpoint --operator-authorized "
                        "only after the operator confirms. The marker was NOT deleted. "
                        "[Phase 7 / lazy-validation-readiness — 2026-06-14 incident fix]"
                    ),
                    "attended": True,
                }, indent=2) + "\n")
                return 1
            # Attended + authorized, or unattended: fall through to WU-7.4 below.

        elif reason == "terminal":
            # TERMINAL-REASON GATE: validate the supplied reason against the
            # sanctioned set.  Backward-compatible: omitting --terminal-reason
            # is allowed but adds a deprecation note (the caller should migrate).
            terminal_reason = getattr(args, "terminal_reason", None)
            if terminal_reason is not None:
                if (terminal_reason not in lazy_core.SANCTIONED_STOP_TERMINAL
                        and not args.operator_authorized):
                    # REFUSE: non-sanctioned reason without authorization.
                    # Marker LEFT IN PLACE.
                    sys.stdout.write(json.dumps({
                        "run_marker_deleted": False,
                        "refused": (
                            f"Stop-authorization gate: non-sanctioned terminal reason "
                            f"'{terminal_reason}'. Sanctioned reasons: "
                            f"{sorted(lazy_core.SANCTIONED_STOP_TERMINAL)}. "
                            f"Pass --operator-authorized to override (operator must "
                            f"explicitly confirm). The marker was NOT deleted. "
                            f"[Phase 7 / lazy-validation-readiness]"
                        ),
                    }, indent=2) + "\n")
                    return 1
                # Sanctioned reason or operator-authorized: proceed.
            # else: terminal_reason is None → backward-compatible (deprecation
            # note added to the output below after deletion).

        # WU-7.4 checkpoint: requires --next-route, and writes the checkpoint
        # file BEFORE the marker/registry are cleared (it folds the marker's
        # counters as they stand at run end).
        checkpoint_written = None
        if reason == "checkpoint":
            if not args.next_route:
                _die("--run-end --reason checkpoint requires --next-route")
            marker_now2 = lazy_core.read_run_marker()
            counters = {}
            if marker_now2 is not None:
                counters = {
                    "forward_cycles": marker_now2.get("forward_cycles"),
                    "meta_cycles": marker_now2.get("meta_cycles"),
                    "max_cycles": marker_now2.get("max_cycles"),
                }
            checkpoint_written = lazy_core.write_run_checkpoint(
                args.next_route, counters,
            )

        # Delete the marker AND the registry (both are run-scoped state).
        # clear_registry=True ensures the prompt registry does not bleed
        # across runs — entries from a previous run must never be dispatchable
        # in the next run's fresh startup.
        deleted = lazy_core.delete_run_marker(clear_registry=True)
        result_out: dict = {"run_marker_deleted": deleted, "reason": reason}
        if override_note is not None:
            result_out["override"] = override_note
        if checkpoint_written is not None:
            result_out["checkpoint"] = checkpoint_written
        # Phase 7: backward-compat deprecation note for legacy --reason terminal
        # callers that omit --terminal-reason.
        if reason == "terminal" and not getattr(args, "terminal_reason", None):
            result_out["deprecation"] = (
                "--run-end --reason terminal should pass --terminal-reason <reason> "
                "for stop-authorization validation (Phase 7 / lazy-validation-readiness). "
                "Sanctioned reasons: " + str(sorted(lazy_core.SANCTIONED_STOP_TERMINAL))
            )
        sys.stdout.write(json.dumps(result_out, indent=2) + "\n")
        return 0

    # Phase 3: --emit-dispatch exits immediately like all other action flags.
    # Pipeline is always "feature" for lazy-state.py (the feature pipeline script).
    if args.emit_dispatch is not None:
        cls = args.emit_dispatch
        # ISSUE 3 (d8-effect-chains live run): the ENTIRE handler is wrapped so it
        # NEVER emits non-JSON / partial output. Any failure — a bad --context-file
        # path, malformed context JSON, an unexpected exception inside the
        # assembler — is caught and surfaced as a structured JSON error object on
        # stdout (exit 1), never a bare traceback or empty stdout. The live run's
        # failure mode was a long --context value parsed to all-None fields; a
        # structured error object lets the orchestrator detect+retry instead of
        # silently proceeding on garbage.
        try:
            # Parse repeatable --context KEY=VALUE flags into a dict (split on first =).
            # The robust large-value channels (--context-file / --context-stdin)
            # are MERGED in first; inline --context wins on a key collision.
            context: dict = {}
            if args.context_file is not None:
                file_obj = lazy_core.load_context_json(
                    Path(args.context_file).read_text(encoding="utf-8")
                )
                context.update(file_obj)
            if args.context_stdin:
                context.update(lazy_core.load_context_json(sys.stdin.read()))
            for kv in (args.context or []):
                if "=" in kv:
                    key, _, value = kv.partition("=")
                    context[key] = value
            result = lazy_core.emit_dispatch_prompt(
                cls, context,
                pipeline="feature",
                cloud=args.cloud,
            )
        except Exception as exc:  # noqa: BLE001
            # ISSUE 3: emit a STRUCTURED JSON error object for ANY failure (unknown
            # class ValueError, unreadable --context-file, malformed context JSON,
            # or an unexpected internal error) — never a bare traceback / empty
            # stdout. `error_kind` lets the orchestrator distinguish a context
            # parse/IO problem (retry with a fixed payload) from a genuine refusal.
            sys.stdout.write(json.dumps({
                "dispatch_prompt": None,
                "dispatch_model": None,
                "dispatch_class": cls,
                "dispatch_prompt_refused": str(exc),
                "error_kind": type(exc).__name__,
            }, indent=2) + "\n")
            return 1
        if result.get("ok"):
            prompt = result["prompt"]
            model = result["model"]
            # Marker present → register the emission (write-through to registry).
            # Marker absent  → peek semantics (prompt produced, no registry write).
            # Phase 7 (lazy-validation-readiness) Deliverable 3: capture the
            # returned entry so we can surface dispatch_prompt_ref (@@lazy-ref
            # nonce=<hex>) in the output JSON — mirrors how --emit-prompt adds
            # cycle_prompt_ref (lazy-state.py ~5266-5276 from Phase 3).
            # The guard's existing @@lazy-ref resolution path resolves any
            # registered class, so meta dispatches (apply-resolution, hardening,
            # etc.) can be dispatched by reference without any guard edit.
            _ref_entry = lazy_core.register_emission_if_marked(
                prompt, cls,
                item_id=context.get("item_id"),
            )
            # ISSUE 5 (d8-effect-chains live run): a meta/recovery dispatch goes
            # through --emit-dispatch (NOT the --repeat-count probe path), so the
            # meta budget was never advancing (meta_cycles stayed 0 through 2 live
            # recoveries). Advance it here on a registered (marker-present) meta
            # emission so recovery/hardening/apply-resolution dispatches count
            # against the meta-cycle budget. Gated on _ref_entry (marker present →
            # this is a real, registered dispatch — not a no-marker peek).
            if _ref_entry is not None:
                lazy_core.advance_meta_cycle()
            # Phase 8 WU-8.2: emission no longer acks the deny ledger.  The ack
            # moves to GUARD-ALLOW time (lazy_guard.py, on allowing a hardening-
            # class entry) so the debt clears only when a hardening dispatch
            # actually reaches execution — repeated emissions can no longer drain
            # the debt without any hardening dispatch occurring (the Phase 7
            # emission-time ack let exactly that happen).
            out: dict = {
                "dispatch_prompt": prompt,
                "dispatch_model": model,
                "dispatch_class": cls,
            }
            # Phase 7 WU-7.5a: surface the marker-gated cycle_header when present
            # (emit_dispatch_prompt only attaches it when a run marker is active).
            if "cycle_header" in result:
                out["cycle_header"] = result["cycle_header"]
            # Phase 7 Deliverable 3: surface the @@lazy-ref reference token so
            # the orchestrator can dispatch meta prompts by reference (no retyping
            # → no transcription-slip denial for apply-resolution, hardening, etc.).
            # Null when no marker is active (peek semantics → no registry write).
            if _ref_entry is not None:
                out["dispatch_prompt_ref"] = f"@@lazy-ref nonce={_ref_entry['nonce']}"
            else:
                out["dispatch_prompt_ref"] = None
            sys.stdout.write(json.dumps(out, indent=2) + "\n")
            return 0
        else:
            # Refusal (missing @requires key or unbound residue).
            sys.stdout.write(json.dumps({
                "dispatch_prompt": None,
                "dispatch_model": None,
                "dispatch_class": cls,
                "dispatch_prompt_refused": result.get("refused", "unknown refusal"),
            }, indent=2) + "\n")
            return 1

    if args.neutralize_sentinel is not None:
        result = lazy_core.neutralize_sentinel(Path(args.neutralize_sentinel), date=args.apply_date)
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.apply_pseudo is not None:
        name, spec = args.apply_pseudo
        result = lazy_core.apply_pseudo(
            Path(args.repo_root), name, Path(spec),
            plan_path=Path(args.plan) if args.plan else None,
            date=args.apply_date, reason=args.reason,
            deferred_step=args.deferred_step,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.enqueue_adhoc:
        if not args.id or not args.name:
            _die("--enqueue-adhoc requires --id and --name")
        result = enqueue_adhoc(
            Path(args.repo_root),
            args.id,
            args.name,
            args.brief,
            args.spec_dir,
            args.tier,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.materialize_wi is not None:
        # type_pipeline_map: load from the Cognito skill-config yml if available,
        # else fall back to the locked default below.
        type_map = {
            "bug": ["Bug", "Defect", "Story Bug", "Engineering Bug"],
            "feature": ["User Story", "Refactor Story", "Enabler Story", "Requirement"],
        }
        result = materialize_wi(Path(args.repo_root), args.materialize_wi, type_map)
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.backfill_receipts:
        result = backfill_receipts(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.verify_ledger is not None:
        # Scripted completion-ledger guard: verify the four preconditions for
        # marking a feature complete. The orchestrator's && chains short-circuit
        # on non-zero exit when any check fails. When --plan is also passed,
        # checks 3+4 narrow to that plan part's scope (Phase 9 WU-3) — reuses the
        # existing --plan flag (shared with --apply-pseudo, no dest collision).
        result = lazy_core.verify_ledger(
            Path(args.repo_root), Path(args.verify_ledger),
            plan_path=Path(args.plan) if args.plan else None,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.test:
        return run_smoke_tests()

    state = compute_state(
        Path(args.repo_root),
        cloud=args.cloud,
        skip_needs_research=args.skip_needs_research,
        real_device=resolve_real_device(args.real_device),
        scope_feature_id=args.feature_id,
        park_needs_input=args.park_needs_input,
    )
    # --repeat-count / --repeat-count-peek are strictly additive and flag-gated
    # so that default output remains byte-identical when neither is passed.
    # --repeat-count ADVANCES the persisted streak; --repeat-count-peek computes
    # the same fields via peek=True (no state-file write). Both populate the
    # 'repeat_count' (Phase-9 dispatch-tuple) AND 'step_repeat_count' (Phase-10
    # step-level oscillation) output fields — emitted together so no new flag is
    # needed and the default (no flag) output stays byte-identical.
    if args.repeat_count or args.repeat_count_peek:
        _counts = lazy_core.update_repeat_counts(
            Path(args.repo_root), state, peek=args.repeat_count_peek
        )
        state["repeat_count"] = _counts["repeat_count"]
        state["step_repeat_count"] = _counts["step_repeat_count"]
    # Counter advance (Phase 1): at dispatch-bound probe time (--repeat-count,
    # NOT --repeat-count-peek) advance the marker-persisted forward/meta counters.
    # Mirror of the peek discipline for update_repeat_counts: only the one
    # dispatch-bound probe per cycle advances any persisted state.
    # No marker present → no-op (advance_run_counters returns None).
    if args.repeat_count:
        lazy_core.advance_run_counters(state)
    # --emit-prompt is strictly additive and flag-gated so that default output
    # remains byte-identical when the flag is absent. Placed AFTER the repeat
    # flags so the same-invocation count (from EITHER --repeat-count or
    # --repeat-count-peek) drives the emitter's loop-block + model decision.
    # emit_cycle_prompt(...) is None for pseudo-skills / terminal probes →
    # cycle_prompt: null, cycle_model: null (so the orchestrator's one probe
    # call is uniform); on refusal it also adds cycle_prompt_refused.
    if args.emit_prompt:
        # Phase 8 WU-8.2: routed hardening debt WITHHOLDS the forward route.
        # When (marker present AND pending_hardening() > 0) the probe must NOT
        # emit/register a cycle_prompt — the orchestrator owes a hardening
        # dispatch first.  Surfacing the debt (Phase 7) was not enough: an
        # orchestrator that field-extracted cycle_model dispatched a forward
        # route over live debt (session e076ed30).  Routing the override here
        # means no cycle_prompt/cycle_model/cycle registration side-effect this
        # probe; the extractor now fails loudly on the missing key.
        _emit_marker = lazy_core.read_run_marker()
        _emit_debt = lazy_core.pending_hardening() if _emit_marker is not None else 0
        if _emit_marker is not None and _emit_debt > 0:
            # Withhold: no cycle_prompt, no cycle_model, no registration.
            _oldest = lazy_core.oldest_unacked_deny()
            state["route_overridden_by"] = "pending-hardening-debt"
            # Compact one-line probe summary for the dispatched hardening subagent.
            _probe_summary = (
                f"step={state.get('current_step')} sub_skill={state.get('sub_skill')} "
                f"feature_id={state.get('feature_id')} pending_hardening={_emit_debt}"
            )
            state["hardening_emit_command"] = lazy_core.build_hardening_emit_command(
                "lazy-state.py",
                item_id=state.get("feature_id") or "",
                oldest_deny=_oldest,
                probe_summary=_probe_summary,
                registry_summary=lazy_core.registry_summary(),
                cwd=str(args.repo_root),
            )
        else:
            rc = state.get("repeat_count") if (args.repeat_count or args.repeat_count_peek) else None
            # Phase 9 (lazy-validation-readiness) — per-part model tiering.
            # emit_cycle_prompt selects cycle_model from the CURRENT plan part's
            # `complexity:` tag when this is an /execute-plan cycle (read off
            # state["sub_skill_args"], the plan path): mechanical → sonnet,
            # complex / absent → opus. It composes with the loop-block downgrade
            # (repeat_count >= 2 → sonnet). bug-state.py shares this exact call,
            # so the bug pipeline mirrors the tiering automatically (no separate
            # cycle-model path). Gated strictly on the explicit tag — never an
            # auto-guess at dispatch.
            emitted = lazy_core.emit_cycle_prompt(
                Path(args.repo_root), state,
                pipeline="feature", cloud=args.cloud, repeat_count=rc,
            )
            if emitted is None:
                state["cycle_prompt"] = None
                state["cycle_model"] = None
            elif emitted.get("ok"):
                state["cycle_prompt"] = emitted["prompt"]
                state["cycle_model"] = emitted["model"]
            else:
                state["cycle_prompt"] = None
                state["cycle_model"] = None
                state["cycle_prompt_refused"] = emitted.get("refused")
            # Registry integration (Phase 1): when a marker is active and the
            # emission produced a non-null cycle_prompt, register it so the
            # validate hook can check it.  No marker → no-op (zero writes,
            # byte-identical output).
            # F2a: capture the returned entry so we can surface the @@lazy-ref
            # token alongside the prompt; orchestrators may use the shorter
            # token to dispatch subagents (dispatch-by-reference).
            cycle_prompt = state.get("cycle_prompt")
            if cycle_prompt:
                _ref_entry = lazy_core.register_emission_if_marked(
                    cycle_prompt, "cycle",
                    item_id=state.get("feature_id"),
                )
                if _ref_entry is not None:
                    # Surface the @@lazy-ref token so the orchestrator can use
                    # dispatch-by-reference instead of repeating the full text.
                    state["cycle_prompt_ref"] = f"@@lazy-ref nonce={_ref_entry['nonce']}"
                else:
                    # No marker active or registration failed — no ref available.
                    state["cycle_prompt_ref"] = None
            else:
                state["cycle_prompt_ref"] = None
    # --probe is strictly additive and flag-gated so that default output remains
    # byte-identical when the flag is absent.  Composes independently with
    # --repeat-count (both may be present simultaneously).
    if args.probe:
        state["git_guards"] = lazy_core.git_guard_status(Path(args.repo_root))
        # Counter fold (Phase 1): when a marker is present, fill in absent
        # --forward-cycles / --meta-cycles from the marker's persisted values.
        # Explicit flag values win over marker values (backward compat).
        # When no marker is present, behavior is byte-identical to before.
        _marker = lazy_core.read_run_marker()
        _fwd, _meta = lazy_core.fold_run_counters(
            args.forward_cycles, args.meta_cycles,
            _marker,
        )
        state["cycle_header"] = lazy_core.format_cycle_header(
            state, forward_cycles=_fwd,
            max_cycles=args.max_cycles, meta_cycles=_meta,
        )
        # Phase 7 WU-7.1: deny-ledger enrichment — MARKER-GATED so default
        # (no-marker) probe output stays byte-identical to the committed
        # baselines.  When a marker is present, surface the routed hardening
        # debt: pending_hardening (count) always, pending_denials (reason heads)
        # only when there is debt.
        if _marker is not None:
            _pending = lazy_core.pending_hardening()
            state["pending_hardening"] = _pending
            if _pending > 0:
                state["pending_denials"] = lazy_core.pending_denial_reasons()
                # Phase 8 WU-8.3: warn to STDERR (never stdout — stdout must stay
                # parseable JSON; lazy_inject.py's _run_probe reads stdout only and
                # captures stderr separately, so this cannot corrupt the banner).
                sys.stderr.write(
                    f"⚠ pending_hardening: {_pending} — forward route withheld; "
                    f"run hardening_emit_command first\n"
                )
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
