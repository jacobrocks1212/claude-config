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
    python3 lazy-state.py --test    # run fixture smoke tests

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
                            | "completion-unverified",
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
import json
import os
import re
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
    return {
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
        # has RETRO_DONE.md + DEFERRED_REQUIRES_DEVICE.md + no VALIDATED.md on a
        # no-real-device host). Always present so /lazy-status and orchestrators
        # can surface lingering In-progress device-deferrals deterministically,
        # not only when the queue exhausts. Mirrors _DIAGNOSTICS.
        "device_deferred_features": list(_DEVICE_DEFERRED),
    }


# Device-deferred features observed this invocation (see _state()). Reset at the
# start of each compute_state() call alongside lazy_core._DIAGNOSTICS.
_DEVICE_DEFERRED: list[str] = []


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


# spec_status — imported from lazy_core


def roadmap_marks_complete(roadmap_text: str, feature_name: str) -> bool:
    """Fallback completion signal: a ROADMAP.md row mentioning the feature with
    both `~~` strikethrough AND the `COMPLETE` token. Retained for repos that
    don't follow the SPEC.md status convention."""
    if not roadmap_text:
        return False
    needle = re.escape(feature_name)
    for line in roadmap_text.splitlines():
        if re.search(needle, line) and "~~" in line and "COMPLETE" in line:
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
    if "Draft (pre-Gemini)" in spec_text:
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
        # ROADMAP rows usually mention the directory name or human name; check both
        for line in text.splitlines():
            if "~~" in line and "COMPLETE" in line and upstream_name in line:
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


def realign_is_fresh(spec_dir: Path, hard_complete_upstream_dirs: list[Path]) -> bool:
    """Skip-if-fresh gate per /lazy Step 4.6a."""
    plan = newest_realign_plan(spec_dir)
    if plan is None:
        return False
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
# Main state machine
# ---------------------------------------------------------------------------

def compute_state(
    repo_root: Path,
    cloud: bool,
    skip_needs_research: bool = False,
    real_device: bool = True,
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
    repo_root = repo_root.resolve()
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
    for entry in queue:
        name = entry.get("name")
        feature_id = entry.get("id")
        spec_subdir = entry.get("spec_dir")
        if not name or not feature_id or not spec_subdir:
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
            # Cloud-saturated skip
            retro_done = (spec_path / "RETRO_DONE.md").exists()
            deferred = (spec_path / "DEFERRED_NON_CLOUD.md").exists()
            validated = (spec_path / "VALIDATED.md").exists()
            if retro_done and deferred and not validated:
                cloud_saturated_skipped.append(name)
                continue
        if not real_device:
            # Device-saturated skip (the device-axis mirror of the cloud skip).
            # A feature whose retro is done and whose only remaining MCP gap is
            # real-device-only assertions (deferred via DEFERRED_REQUIRES_DEVICE.md,
            # no VALIDATED.md yet) cannot be certified on THIS no-device host.
            # Skip it so the queue advances — a real-device host re-opens it
            # (Step 9) to run the deferred scenarios. This applies to cloud too
            # (cloud has no device), but in practice cloud features carry
            # DEFERRED_NON_CLOUD.md and are caught by the cloud skip above first.
            retro_done = (spec_path / "RETRO_DONE.md").exists()
            device_deferred = (spec_path / "DEFERRED_REQUIRES_DEVICE.md").exists()
            validated = (spec_path / "VALIDATED.md").exists()
            if retro_done and device_deferred and not validated:
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

    # Step 3: BLOCKED.md
    blocked_file = spec_path / "BLOCKED.md"
    if blocked_file.exists():
        meta = parse_sentinel(blocked_file) or {}
        phase = meta.get("phase", "unknown")
        return _state(
            **common,
            current_step="Step 3: blocked",
            terminal_reason="blocked",
            notify_message=f"BLOCKED: {feature_name} — {phase}. Awaiting input.",
        )

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
            # fall through to Step 8 (cloud defers or honors an existing
            # DEFERRED_NON_CLOUD.md), Step 9 retro runs, and Step 2's
            # cloud-saturated skip eventually fires.
            #
            # Workstation: bypass ONLY when the unchecked remainder is entirely
            # verification rows. Workstation CAN run those checks, so falling
            # through reaches Step 8 retro → Step 9 /mcp-test (the dispatch
            # that actually ticks them). If any real implementation row is
            # still unchecked we skip this branch and write-plan as before.
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

    # Phases complete — new order: Step 8 (retro) → Step 9 (MCP gate) → Step 10 (mark complete).
    #
    # /retro now runs BEFORE /mcp-test. Rationale: cloud halts at MCP deferral,
    # so under the old (mcp → retro) order, cloud runs never reached retro and
    # workstation runs lacked an implementation-time retrospective gate. /retro
    # is a docs/analysis pass (no Tauri, no MCP), so it runs identically in
    # cloud and workstation.

    validated_file = spec_path / "VALIDATED.md"
    skip_mcp_file = spec_path / "SKIP_MCP_TEST.md"
    deferred_file = spec_path / "DEFERRED_NON_CLOUD.md"
    retro_done_file = spec_path / "RETRO_DONE.md"
    mcp_results_file = spec_path / "MCP_TEST_RESULTS.md"

    # Step 8: Retro phase (runs FIRST after implementation completes).
    # Entry condition: phases complete + no RETRO_DONE.md. No MCP precondition.
    #
    # The retro skill (Step 6c) writes RETRO_DONE.md when a round concludes
    # with no significant divergences. /retro-feature is the composed skill
    # that loops /retro + /execute-plan internally until RETRO_DONE.md,
    # BLOCKED.md, NEEDS_INPUT.md, or its own max-rounds cap. It is idempotent
    # — re-dispatch after a partial run picks up from on-disk state.
    if not retro_done_file.exists():
        return _state(
            **common,
            current_step="Step 8: retro phase",
            sub_skill="retro-feature",
            sub_skill_args=f"{spec_path_str} --batch",
        )

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
        # device-saturated skip catches this before Step 9 (RETRO_DONE is present
        # by Step 8), so this is a defensive guard ensuring a no-device host NEVER
        # re-dispatches /mcp-test for an already-deferred scenario set (which
        # would no-op-loop). Surface the same device-queue terminal.
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

    # Step 9: MCP gate (retro complete; now validate runtime).
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
    # Entry: RETRO_DONE.md (guaranteed by the Step 8 short-circuit above) AND
    # (VALIDATED.md OR (cloud AND DEFERRED_NON_CLOUD.md)).
    entry_ok = validated_file.exists() or (cloud and deferred_file.exists())
    if not entry_ok:
        # No entry — should be unreachable: Step 9 either wrote validated /
        # deferred or dispatched mcp-test. Defensive.
        return _state(
            **common,
            current_step="Step 10: unexpected state",
            sub_skill=None,
            terminal_reason="needs-input",
            notify_message=(
                f"{feature_name}: unexpected state at Step 10 — RETRO_DONE.md "
                "present but no VALIDATED.md, SKIP_MCP_TEST.md, or "
                "DEFERRED_NON_CLOUD.md. Manual review needed."
            ),
        )

    # Cloud cannot finalize without VALIDATED.md — Step 2's cloud-saturated
    # skip normally catches this earlier (RETRO_DONE.md + DEFERRED_NON_CLOUD.md
    # + no VALIDATED.md), but defensively halt here too.
    if cloud and not validated_file.exists():
        return _state(
            **common,
            current_step="Step 10a: cloud halt",
            terminal_reason="cloud-queue-exhausted",
            notify_message=(
                f"{feature_name}: cloud work complete (phases + retro). "
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
        # already on disk. Cloud Step 7 bypass → Step 8 (deferred exists, no
        # action) → Step 9 retro entry.
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
        # the retro→MCP gate. With no RETRO_DONE.md, Step 8 retro dispatches
        # first (mirrors the cloud-bypass cases above).
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
        # Workstation bypass with RETRO_DONE.md already on disk: Step 8 retro
        # is satisfied, so the fall-through reaches Step 9 → mcp-test (the
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
        # Assertions:**`. All impl plans Complete, no RETRO_DONE.md →
        # bypass → Step 8 retro.
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
        # Under the new state machine, Step 8 (retro) fires FIRST — expects
        # sub_skill: retro-feature, NOT mcp-test.
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
        # All phases complete + RETRO_DONE.md present, no VALIDATED.md yet.
        # Under the new state machine, Step 9 (mcp test) fires — expects
        # sub_skill: mcp-test, NOT retro-feature.
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
        # Cloud variant: phases complete, no sentinels. Should dispatch
        # retro-feature in cloud just like workstation — /retro is a
        # docs/analysis pass with no Tauri/MCP requirements.
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
            # through to phases-complete logic. Under the new ordering
            # (retro before MCP), Step 8 retro dispatches first, since
            # /retro is cloud-runnable.
            ("cloud-workstation-only-remainder", True, False, {
                "sub_skill": "retro-feature",
                "feature_id": "feat-cw",
            }),
            # Same bypass with DEFERRED_NON_CLOUD.md already on disk — also
            # has no RETRO_DONE.md, so Step 8 retro still dispatches first.
            ("cloud-workstation-only-with-deferred", True, False, {
                "sub_skill": "retro-feature",
                "feature_id": "feat-cwd",
            }),
            # Workstation MCP-gate bypass: all impl plans Complete, only
            # unchecked rows are Runtime Verification → fall through to the
            # retro→MCP gate. No RETRO_DONE.md yet → Step 8 retro fires first
            # (mirrors the cloud-bypass cases above).
            ("workstation-all-plans-complete-phases-unchecked", False, False, {
                "sub_skill": "retro-feature",
                "feature_id": "feat-wapcpu",
            }),
            # Workstation bypass + RETRO_DONE.md present → Step 9 mcp-test
            # (the dispatch that actually ticks the deferred verification rows).
            ("workstation-verification-only-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-wvrd",
                "current_step": "Step 9: run MCP tests",
            }),
            # Workstation bypass with bold-marker (`**Runtime Verification**`)
            # subsections instead of `### ` headings — real AlgoBooth format.
            # No RETRO_DONE.md → Step 8 retro.
            ("workstation-verification-only-bold-marker", False, False, {
                "sub_skill": "retro-feature",
                "feature_id": "feat-wbold",
            }),
            # NEGATIVE: all impl plans Complete but a remaining unchecked row is
            # a real implementation deliverable (outside any verification
            # subsection) → bypass must NOT fire; write-plan still dispatched.
            ("workstation-all-plans-complete-real-unchecked", False, False, {
                "sub_skill": "write-plan",
                "feature_id": "feat-wreal",
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
            # Retro-before-mcp gate (new state-machine order). Workstation:
            # phases complete, no RETRO_DONE.md → Step 8 dispatches retro,
            # NOT mcp-test.
            ("phases-complete-no-retro-done", False, False, {
                "sub_skill": "retro-feature",
                "feature_id": "feat-pcnr",
                "current_step": "Step 8: retro phase",
            }),
            # Same feature after RETRO_DONE.md lands → Step 9 mcp test.
            ("phases-complete-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-pcrd",
                "current_step": "Step 9: run MCP tests",
            }),
            # Cloud variant: phases complete, no RETRO_DONE.md → retro
            # runs in cloud too (docs/analysis pass; no Tauri/MCP needed).
            ("phases-complete-no-retro-done-cloud", True, False, {
                "sub_skill": "retro-feature",
                "feature_id": "feat-pcnrc",
                "current_step": "Step 8: retro phase",
            }),
            # Cloud variant: retro complete, no validated yet → Step 9
            # writes DEFERRED_NON_CLOUD.md.
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
            print(
                f"  [{name}] cloud={cloud} skip_nr={skip_nr} "
                f"real_device={real_device}: "
                f"{got['current_step'] or got['terminal_reason']}"
            )

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
    args = parser.parse_args()

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

    if args.backfill_receipts:
        result = backfill_receipts(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.test:
        return run_smoke_tests()

    state = compute_state(
        Path(args.repo_root),
        cloud=args.cloud,
        skip_needs_research=args.skip_needs_research,
        real_device=resolve_real_device(args.real_device),
    )
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
