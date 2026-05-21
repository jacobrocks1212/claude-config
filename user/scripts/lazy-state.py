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
    python3 lazy-state.py [--cloud] [--repo-root <path>]
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
                            | "blocked" | "needs-research" | "needs-input"
                            | "needs-spec-input" | "queue-missing",
  "notify_message":    "<string>"      | null
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
) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "spec_path": spec_path,
        "current_step": current_step,
        "sub_skill": sub_skill,
        "sub_skill_args": sub_skill_args,
        "terminal_reason": terminal_reason,
        "notify_message": notify_message,
    }


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


def is_workstation_complete(roadmap_text: str, feature_name: str) -> bool:
    """Match /lazy Step 2: ROADMAP row has both '~~' and 'COMPLETE'."""
    if not roadmap_text:
        return False
    needle = re.escape(feature_name)
    for line in roadmap_text.splitlines():
        if re.search(needle, line) and "~~" in line and "COMPLETE" in line:
            return True
    return False


# ---------------------------------------------------------------------------
# SPEC parsing
# ---------------------------------------------------------------------------

def is_stub_spec(spec_text: str) -> bool:
    """Detect stub-spec markers per /lazy Step 4.5."""
    if "**Status:** Draft (research stub)" in spec_text:
        return True
    if "> Stub generated from advanced feature research" in spec_text:
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


# ---------------------------------------------------------------------------
# Plan file discovery
# ---------------------------------------------------------------------------

def find_implementation_plans(spec_dir: Path) -> list[Path]:
    """Find non-retro implementation plans. Mirrors /lazy Step 7a."""
    plans: list[Path] = []
    plans_dir = spec_dir / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            name = p.name
            if name.startswith("retro-") or name.startswith("realign-"):
                continue
            plans.append(p)
    # Legacy fallback
    legacy = spec_dir / "PLAN.md"
    if legacy.exists() and legacy not in plans:
        plans.append(legacy)
    return plans


def find_retro_plans(spec_dir: Path) -> list[Path]:
    plans_dir = spec_dir / "plans"
    if not plans_dir.exists():
        return []
    return sorted(plans_dir.glob("retro-*.md"))


def latest_retro_plan(spec_dir: Path) -> Path | None:
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
# Main state machine
# ---------------------------------------------------------------------------

def compute_state(repo_root: Path, cloud: bool) -> dict[str, Any]:
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
    for entry in queue:
        name = entry.get("name")
        feature_id = entry.get("id")
        spec_subdir = entry.get("spec_dir")
        if not name or not feature_id or not spec_subdir:
            continue
        spec_path = (repo_root / "docs" / "features" / spec_subdir).resolve()
        if is_workstation_complete(roadmap_text, name):
            continue
        if cloud:
            # Cloud-saturated skip
            retro_done = (spec_path / "RETRO_DONE.md").exists()
            deferred = (spec_path / "DEFERRED_NON_CLOUD.md").exists()
            validated = (spec_path / "VALIDATED.md").exists()
            if retro_done and deferred and not validated:
                cloud_saturated_skipped.append(name)
                continue
        current = {
            "name": name,
            "id": feature_id,
            "spec_path": spec_path,
            "tier": entry.get("tier"),
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
        return _state(
            **common,
            current_step="Step 4: SPEC missing, research files present",
            sub_skill="spec",
            sub_skill_args=f"{feature_name} — see {spec_path_str} for prior research",
        )

    spec_text = spec_file.read_text(encoding="utf-8")

    # Step 4.5: Stub spec
    if is_stub_spec(spec_text):
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
        return _state(
            **common,
            current_step="Step 6: generate phases",
            sub_skill="spec-phases",
            sub_skill_args=f"{spec_path_str}/SPEC.md",
        )

    phases_text = phases_file.read_text(encoding="utf-8")
    unchecked, checked = count_deliverables(phases_text)

    # Step 7: Phase completion
    if unchecked > 0:
        plans = find_implementation_plans(spec_path)
        if not plans:
            return _state(
                **common,
                current_step="Step 7a: write plan",
                sub_skill="write-plan",
                sub_skill_args=f"{spec_path_str}/PHASES.md",
            )
        # Use the lowest-ordered plan (sorted-name preference); if part-N exists,
        # this returns part-1 first which is what we want.
        plan = plans[0]
        return _state(
            **common,
            current_step="Step 7a: execute plan",
            sub_skill="execute-plan",
            sub_skill_args=str(plan),
        )

    # Phases complete — Step 8 (MCP gate) and Step 9 (retro)

    validated_file = spec_path / "VALIDATED.md"
    skip_mcp_file = spec_path / "SKIP_MCP_TEST.md"
    deferred_file = spec_path / "DEFERRED_NON_CLOUD.md"
    retro_done_file = spec_path / "RETRO_DONE.md"
    mcp_results_file = spec_path / "MCP_TEST_RESULTS.md"

    # Cloud Step 8: defer if not validated and not skipped
    if cloud:
        if not validated_file.exists() and not skip_mcp_file.exists() and not deferred_file.exists():
            # Cloud halts at Step 8 — defer to workstation. Orchestrator writes
            # the DEFERRED_NON_CLOUD.md sentinel and we fall through to retro on
            # the next state-script call (deferred_file then exists).
            return _state(
                **common,
                current_step="Step 8: cloud defers MCP test",
                sub_skill="__write_deferred_non_cloud__",
                sub_skill_args=spec_path_str,
            )
        # If SKIP_MCP_TEST exists in cloud, write VALIDATED (per /lazy-cloud Step 8)
        if skip_mcp_file.exists() and not validated_file.exists():
            return _state(
                **common,
                current_step="Step 8: skip-mcp-test → validated",
                sub_skill="__write_validated_from_skip__",
                sub_skill_args=spec_path_str,
            )

    # Workstation Step 8 (or cloud post-defer): MCP gate
    if not cloud:
        if not validated_file.exists():
            if skip_mcp_file.exists():
                return _state(
                    **common,
                    current_step="Step 8: skip-mcp-test → validated",
                    sub_skill="__write_validated_from_skip__",
                    sub_skill_args=spec_path_str,
                )
            # 100%-passing results already on disk?
            if mcp_results_file.exists():
                meta = parse_sentinel(mcp_results_file) or {}
                if meta.get("result") == "all-passing":
                    return _state(
                        **common,
                        current_step="Step 8b: write validated",
                        sub_skill="__write_validated_from_results__",
                        sub_skill_args=spec_path_str,
                    )
            # Run MCP tests
            return _state(
                **common,
                current_step="Step 8: run MCP tests",
                sub_skill="mcp-test",
                sub_skill_args=f"validate {feature_name} — see {spec_path_str}/SPEC.md",
            )

    # Step 9: Retro
    # Entry: validated_file OR (cloud AND deferred_file)
    entry_ok = validated_file.exists() or (cloud and deferred_file.exists())
    if not entry_ok:
        # No entry into retro — should be unreachable for cloud (Step 8 above
        # writes deferred or skip→validated) and for workstation. Be defensive.
        return _state(
            **common,
            current_step="Step 8/9: unexpected state",
            sub_skill=None,
            terminal_reason="needs-input",
            notify_message=(
                f"{feature_name}: unexpected state at Step 8/9 — no VALIDATED.md, "
                "SKIP_MCP_TEST.md, or DEFERRED_NON_CLOUD.md. Manual review needed."
            ),
        )

    if retro_done_file.exists():
        # Step 10: mark complete (workstation only; cloud halts here)
        if cloud and not validated_file.exists():
            # Defensive cloud halt — Step 2 normally skips first, but if state arrives
            # here, surface it.
            return _state(
                **common,
                current_step="Step 10a: cloud halt",
                terminal_reason="cloud-queue-exhausted",
                notify_message=(
                    f"{feature_name}: cloud work complete (phases + retro). "
                    "Awaiting workstation /lazy for deferred MCP test."
                ),
            )
        # Mark complete via /commit (orchestrator does the ROADMAP edit + sentinel cleanup)
        return _state(
            **common,
            current_step="Step 10: mark complete",
            sub_skill="__mark_complete__",
            sub_skill_args=spec_path_str,
        )

    # No RETRO_DONE.md — dispatch retro flow
    retro_plans = find_retro_plans(spec_path)
    if not retro_plans:
        return _state(
            **common,
            current_step="Step 9: first retro",
            sub_skill="retro",
            sub_skill_args=f"{spec_path_str}/PHASES.md --auto",
        )

    if len(retro_plans) == 1:
        first = retro_plans[0]
        if retro_plan_has_significant_divergences(first):
            return _state(
                **common,
                current_step="Step 9: second retro (verify fixes)",
                sub_skill="retro",
                sub_skill_args=f"{spec_path_str}/PHASES.md --auto",
            )
        return _state(
            **common,
            current_step="Step 9: execute retro plan",
            sub_skill="execute-plan",
            sub_skill_args=str(first),
        )

    # 2+ retro plans → execute latest
    latest = latest_retro_plan(spec_path)
    return _state(
        **common,
        current_step="Step 9: execute latest retro plan",
        sub_skill="execute-plan",
        sub_skill_args=str(latest) if latest else "",
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
    elif name == "all-complete":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-f", "name": "Feature F", "spec_dir": "feat-f", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n- ~~Feature F — done~~ **COMPLETE**\n"
        )
        (features / "feat-f").mkdir()
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
    else:
        raise ValueError(f"unknown fixture: {name}")

    return root


def run_smoke_tests() -> int:
    """Build fixtures in a temp dir and assert expected state shapes."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lazy-state-fixtures-") as td:
        td_path = Path(td)
        cases = [
            # (fixture_name, cloud, expectations dict)
            ("fresh-queue", False, {"terminal_reason": "needs-spec-input"}),
            ("blocker", False, {"terminal_reason": "blocked", "feature_id": "feat-b"}),
            ("mid-implementation", False, {"sub_skill": "execute-plan", "feature_id": "feat-c"}),
            ("cloud-saturated", True, {"feature_id": "feat-e"}),   # advances past saturated feat-d
            ("all-complete", False, {"terminal_reason": "all-features-complete"}),
            ("needs-research", False, {"terminal_reason": "needs-research"}),
            ("needs-realign", False, {
                "sub_skill": "realign-spec",
                "feature_id": "feat-h",
            }),
        ]
        for name, cloud, expected in cases:
            root = _build_fixture(td_path, name)
            try:
                got = compute_state(root, cloud=cloud)
            except SystemExit as exc:
                failures.append(f"[{name}] SystemExit: {exc.code}")
                continue
            for k, v in expected.items():
                if got.get(k) != v:
                    failures.append(
                        f"[{name}] expected {k}={v!r}, got {k}={got.get(k)!r}"
                    )
            print(f"  [{name}] cloud={cloud}: {got['current_step'] or got['terminal_reason']}")

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
    parser.add_argument("--repo-root", default=os.getcwd(),
                        help="Project root (default: $PWD)")
    parser.add_argument("--test", action="store_true",
                        help="Run fixture smoke tests instead of computing state")
    args = parser.parse_args()

    if args.test:
        return run_smoke_tests()

    state = compute_state(Path(args.repo_root), cloud=args.cloud)
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
