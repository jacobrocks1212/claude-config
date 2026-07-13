#!/usr/bin/env python3
"""lazy-queue-doc.py — pure-read GitHub-mobile LAZY_QUEUE.md generator.

A stdlib-only generator (sibling to lazy-state.py) that reads a repo's lazy
feature + bug queue state via the proven peer `pipeline_visualizer.probe.probe_state`
and emits a per-repo grouped `LAZY_QUEUE.md`:

  - a Features table and a Bugs table (one row per queue item: reorder index,
    name as a SPEC.md link, curated state, tier/severity),
  - an inline curated summary per item (status · phase N/M · next action ·
    one-line exec summary),
  - a "Needs attention" triage section mirroring Blocked / Needs-input items,
  - a freshness header carrying the run-active/idle marker.

It is a PURE function of on-disk state: `render_doc()` takes the probe aggregate
dict and returns the full markdown. It embeds NO wall-clock timestamp, so two
renders of unchanged state are byte-identical (GitHub mobile shows "last updated"
from the file's native git commit time). It never re-implements state inference
and never mutates queue.json — it only reads state and writes its own document.

Usage:
    python lazy-queue-doc.py --repo-root <path>     # write <repo>/LAZY_QUEUE.md
    python lazy-queue-doc.py --repo-root <path> --stdout   # print, don't write
    python lazy-queue-doc.py --link-mode absolute   # github.com/.../blob/... links
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# Import the sibling pipeline_visualizer package — same _SCRIPTS_DIR-on-sys.path
# pattern as pipeline_visualizer/__main__.py (lines 18-20).
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pipeline_visualizer.probe import probe_state  # noqa: E402
import lazy_core  # noqa: E402 — bug-queue-aging-backpressure D4-A marker helper

_LAZY_STATE = _SCRIPTS_DIR / "lazy-state.py"

# Curated stages that route an item into the "Needs attention" triage section.
_TRIAGE_STAGES = {"Blocked", "Needs-input"}

# Display glyphs per curated stage (purely cosmetic; absent → no glyph).
_STAGE_GLYPH = {
    "Blocked": "⛔",       # ⛔
    "Needs-input": "⬡",   # ⬡
    "Deferred": "⏸",      # ⏸
}

# Display-only "next action" hint per curated stage. Derived from the stage, not
# re-inferred from the state machine — a human-readable nudge for the mobile read.
_NEXT_ACTION = {
    "Pending": "queue",
    "Spec": "spec",
    "Research": "research",
    "Plan": "plan",
    "Implement": "execute plan",
    "Validate": "run mcp-test",
    "Complete": "done",
    "Blocked": "resolve blocker",
    "Needs-input": "answer needs-input",
    "Deferred": "deferred",
}


# ---------------------------------------------------------------------------
# Link-target resolution
# ---------------------------------------------------------------------------

def _rel_spec_path(item: dict, queue_dir: str, repo_root: Path) -> str:
    """Resolve an item's SPEC.md link target, RELATIVE to repo root.

    Prefers the state script's own `spec_path` (authoritative, absolute) and
    expresses it relative to repo_root; falls back to
    docs/<queue_dir>/<id>/SPEC.md. Always uses forward slashes (markdown link).
    """
    spec_path = item.get("spec_path")
    item_id = item.get("feature_id") or item.get("bug_id") or "unknown"
    if spec_path:
        try:
            sp = Path(spec_path)
            if sp.name != "SPEC.md":
                sp = sp / "SPEC.md"
            rel = os.path.relpath(sp, repo_root)
            return rel.replace(os.sep, "/")
        except (ValueError, OSError):
            pass
    return f"docs/{queue_dir}/{item_id}/SPEC.md"


def parse_owner_repo(remote_url: Optional[str]) -> Optional[Tuple[str, str]]:
    """Parse `owner/repo` from a git remote URL (https or ssh). None if unparseable."""
    if not remote_url:
        return None
    url = remote_url.strip()
    # ssh form: git@github.com:owner/repo(.git)
    m = re.match(r"git@[^:]+:([^/]+)/(.+?)(?:\.git)?/?$", url)
    if m:
        return m.group(1), m.group(2)
    # https form: https://github.com/owner/repo(.git)
    m = re.match(r"https?://[^/]+/([^/]+)/(.+?)(?:\.git)?/?$", url)
    if m:
        return m.group(1), m.group(2)
    return None


def _link_target(item: dict, queue_dir: str, repo_root: Path, *, link_mode: str,
                 remote_url: Optional[str], branch: str) -> str:
    rel = _rel_spec_path(item, queue_dir, repo_root)
    if link_mode == "absolute":
        parsed = parse_owner_repo(remote_url)
        if parsed:
            owner, repo = parsed
            return f"https://github.com/{owner}/{repo}/blob/{branch}/{rel}"
    return rel


# ---------------------------------------------------------------------------
# Phase-progress reader + exec-summary reader (display-only)
# ---------------------------------------------------------------------------

_PHASE_HEADING_RE = re.compile(r"^###\s+Phase\b", re.MULTILINE)


def phase_progress(phases_md_path) -> Tuple[Optional[int], Optional[int]]:
    """Return (checked_phases, total_phases) for an item's PHASES.md.

    A phase is "checked" when it has at least one `- [x]` deliverable and NO
    `- [ ]` deliverables (all its boxes are ticked). Display-only — never
    re-infers pipeline state. Missing/unreadable file → (None, None).
    """
    p = Path(phases_md_path)
    if not p.exists():
        return (None, None)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return (None, None)

    # Split into per-phase blocks at each `### Phase` heading.
    headings = list(_PHASE_HEADING_RE.finditer(text))
    total = len(headings)
    if total == 0:
        return (None, None)

    checked = 0
    in_fence = False
    bounds = [m.start() for m in headings] + [len(text)]
    for i in range(total):
        block = text[bounds[i]:bounds[i + 1]]
        has_checked = False
        has_unchecked = False
        in_fence = False
        for line in block.splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if re.match(r"^\s*-\s*\[\s*\]", line):
                has_unchecked = True
            elif re.match(r"^\s*-\s*\[[xX]\]", line):
                has_checked = True
        if has_checked and not has_unchecked:
            checked += 1
    return (checked, total)


_DISCOVERED_RE = re.compile(r"^\*\*Discovered:\*\*\s*(.+?)\s*$", re.MULTILINE)
_SEVERITY_LINE_RE = re.compile(r"^\*\*Severity:\*\*\s*(.+?)\s*$", re.MULTILINE)


def _bug_spec_field(spec_md_path, pattern: re.Pattern) -> Optional[str]:
    """Read a `**Field:**` header line from a bug SPEC.md (display-only;
    mirrors bug-state.py's bug_discovered()/bug_severity() parsing — duplicated
    here rather than imported since bug-state.py is a hyphenated module).
    Missing/unreadable file or absent field → None."""
    p = Path(spec_md_path)
    if not p.exists():
        return None
    try:
        m = pattern.search(p.read_text(encoding="utf-8"))
    except OSError:
        return None
    return m.group(1).strip() if m else None


def _first_sentence(text: str) -> str:
    """Extract the first sentence from a blob of prose (period-terminated)."""
    text = text.strip()
    if not text:
        return ""
    # Stop at the first sentence-terminating period followed by space/EOL.
    m = re.search(r"\.(\s|$)", text)
    if m:
        return text[:m.start() + 1].strip()
    return text.split("\n", 1)[0].strip()


def _exec_summary(spec_md_path) -> str:
    """One-line exec summary = the SPEC's lead blockquote first sentence, else the
    `## Executive Summary` first sentence. Failure-tolerant: missing/short SPEC →
    empty string, NEVER an exception (Phase 3 runs this every cycle)."""
    p = Path(spec_md_path)
    if not p.exists():
        return ""
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return ""

    # Lead blockquote: consecutive `>` lines near the top.
    quote_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            quote_lines.append(stripped.lstrip(">").strip())
        elif quote_lines:
            break  # blockquote ended
        elif stripped and not stripped.startswith("#"):
            break  # hit body prose before any blockquote
    if quote_lines:
        return _first_sentence(" ".join(quote_lines))

    # Fallback: ## Executive Summary section first sentence.
    m = re.search(r"^##\s+Executive Summary\s*$", text, re.MULTILINE)
    if m:
        rest = text[m.end():].lstrip("\n")
        para = rest.split("\n\n", 1)[0].replace("\n", " ").strip()
        return _first_sentence(para)
    return ""


def _spec_md_abspath(item: dict, queue_dir: str, repo_root: Path) -> Path:
    """Absolute on-disk SPEC.md path for reading exec-summary / sibling PHASES.md."""
    spec_path = item.get("spec_path")
    if spec_path:
        sp = Path(spec_path)
        if sp.name != "SPEC.md":
            sp = sp / "SPEC.md"
        return sp
    item_id = item.get("feature_id") or item.get("bug_id") or "unknown"
    return repo_root / "docs" / queue_dir / item_id / "SPEC.md"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _item_id(item: dict) -> str:
    return item.get("feature_id") or item.get("bug_id") or "unknown"


def _badge(item: dict, *, is_bug: bool) -> str:
    meta = item.get("queue_meta") or {}
    if is_bug:
        sev = meta.get("severity")
        return str(sev) if sev else "—"
    tier = meta.get("tier")
    return f"T{tier}" if tier is not None else "—"


def _inline_summary(item: dict, queue_dir: str, repo_root: Path) -> str:
    """Build the inline curated-summary line: status · phase N/M · next · summary."""
    stage = item.get("curated_stage") or "Pending"
    parts = [f"status: {stage}"]

    spec_md = _spec_md_abspath(item, queue_dir, repo_root)
    phases_md = spec_md.parent / "PHASES.md"
    checked, total = phase_progress(phases_md)
    if total:
        parts.append(f"phase {checked}/{total}")

    parts.append(f"next: {_NEXT_ACTION.get(stage, stage.lower())}")

    summary = _exec_summary(spec_md)
    if summary:
        parts.append(summary)
    return " · ".join(parts)


def _bug_aging_cell(item: dict, queue_dir: str, repo_root: Path) -> str:
    """Render the bug-queue-aging-backpressure D4-A "aging" cell: the SPEC's
    ``**Discovered:**`` date plus a pin/escalation marker (from
    ``lazy_core.bug_priority_marker``). Renders stable on-disk FACTS, not a
    computed age-in-days, so the table stays byte-stable for unchanged state
    (D4-A) — save the marker, which is itself a function of ``today`` (an
    honest, documented exception: it can change day-to-day with no state
    change). Empty string when Discovered is absent (never fabricated)."""
    spec_md = _spec_md_abspath(item, queue_dir, repo_root)
    discovered = _bug_spec_field(spec_md, _DISCOVERED_RE)
    meta = item.get("queue_meta") or {}
    marker = lazy_core.bug_priority_marker(
        severity=meta.get("severity"),
        spec_severity=_bug_spec_field(spec_md, _SEVERITY_LINE_RE),
        discovered=discovered,
        pinned_at=meta.get("pinned_at"),
        pinned_until=meta.get("pinned_until"),
    )
    if not discovered and not marker:
        return ""
    parts = [p for p in (discovered, marker) if p]
    return " ".join(parts)


def _render_table(items: list, *, queue_dir: str, repo_root: Path, is_bug: bool,
                  link_mode: str, remote_url: Optional[str], branch: str) -> list:
    """Render one queue's table + inline summaries as a list of markdown lines."""
    label = "Bugs" if is_bug else "Features"
    badge_col = "sev" if is_bug else "tier"
    lines = [f"## {label} ({len(items)})", ""]
    if not items:
        lines.append("")
        return lines
    if is_bug:
        lines.append(f"| # | item | state | {badge_col} | aging |")
        lines.append("|---|------|-------|------|------|")
    else:
        lines.append(f"| # | item | state | {badge_col} |")
        lines.append("|---|------|-------|------|")
    for idx, item in enumerate(items, start=1):
        iid = _item_id(item)
        target = _link_target(item, queue_dir, repo_root, link_mode=link_mode,
                              remote_url=remote_url, branch=branch)
        stage = item.get("curated_stage") or "Pending"
        glyph = _STAGE_GLYPH.get(stage)
        state_cell = f"{glyph} {stage}" if glyph else stage
        badge = _badge(item, is_bug=is_bug)
        summary = _inline_summary(item, queue_dir, repo_root)
        if is_bug:
            aging = _bug_aging_cell(item, queue_dir, repo_root)
            lines.append(f"| {idx} | [{iid}]({target}) | {state_cell} | {badge} | {aging} |")
            lines.append(f"| | {summary} | | | |")
        else:
            lines.append(f"| {idx} | [{iid}]({target}) | {state_cell} | {badge} |")
            lines.append(f"| | {summary} | | |")
    lines.append("")
    return lines


def _render_triage(features: list, bugs: list, repo_root: Path) -> list:
    """Render the 'Needs attention' section, or [] when no item needs attention
    (byte-stability: an empty triage emits NO header)."""
    flagged = []
    for item in features:
        if (item.get("curated_stage") or "") in _TRIAGE_STAGES:
            flagged.append(item)
    for item in bugs:
        if (item.get("curated_stage") or "") in _TRIAGE_STAGES:
            flagged.append(item)
    if not flagged:
        return []
    lines = ["## Needs attention", ""]
    for item in flagged:
        stage = item.get("curated_stage")
        glyph = _STAGE_GLYPH.get(stage, "")
        prefix = f"{glyph} " if glyph else ""
        lines.append(f"- {prefix}{_item_id(item)} — {stage.lower()}")
    lines.append("")
    return lines


def render_doc(state: dict, repo_root, *, run_active: bool, link_mode: str = "relative",
               remote_url: Optional[str] = None, branch: str = "main") -> str:
    """Render the full LAZY_QUEUE.md markdown from a probe_state() aggregate.

    PURE function of `state` + the on-disk SPEC/PHASES files the items point at.
    Embeds NO wall-clock (state["server_time"] is intentionally ignored) so an
    unchanged-state re-render is byte-identical.
    """
    repo_root = Path(repo_root)
    repo_name = repo_root.name or str(repo_root)
    features = state.get("features", [])
    bugs = state.get("bugs", [])

    marker = "run active \U0001F512" if run_active else "idle"
    lines = [f"# Lazy Queue — {repo_name}   ({marker})", ""]

    lines += _render_table(features, queue_dir="features", repo_root=repo_root,
                           is_bug=False, link_mode=link_mode, remote_url=remote_url,
                           branch=branch)
    lines += _render_table(bugs, queue_dir="bugs", repo_root=repo_root,
                           is_bug=True, link_mode=link_mode, remote_url=remote_url,
                           branch=branch)
    lines += _render_triage(features, bugs, repo_root)

    # Single trailing newline; no embedded wall-clock anywhere.
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# CLI glue (impure — shells the marker query + git remote/branch)
# ---------------------------------------------------------------------------

def _run_active(repo_root: Path) -> bool:
    """Shell `lazy-state.py --marker-present` (exit 0 → active, 1 → idle)."""
    try:
        proc = subprocess.run(
            [sys.executable, str(_LAZY_STATE), "--marker-present",
             "--repo-root", str(repo_root)],
            capture_output=True, text=True, timeout=60,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _git_remote_url(repo_root: Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _git_branch(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            [sys.executable, str(_LAZY_STATE), "--marker-work-branch",
             "--repo-root", str(repo_root)],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return "main"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="lazy-queue-doc",
        description="Generate a per-repo, GitHub-mobile-readable LAZY_QUEUE.md "
                    "from on-disk lazy state (pure read; never mutates queue.json).",
    )
    parser.add_argument(
        "--repo-root", default=os.getcwd(),
        help="Repo whose docs/features + docs/bugs to render (default: cwd).",
    )
    parser.add_argument(
        "--stdout", action="store_true",
        help="Print the doc to stdout instead of writing <repo>/LAZY_QUEUE.md.",
    )
    parser.add_argument(
        "--link-mode", choices=["relative", "absolute"], default="relative",
        help="SPEC.md link form (default: relative). 'absolute' emits "
             "github.com/<owner>/<repo>/blob/<branch>/... for the GitHub-mobile "
             "relative-link fallback.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    state = probe_state(repo_root)
    run_active = _run_active(repo_root)

    remote_url = None
    branch = "main"
    if args.link_mode == "absolute":
        remote_url = _git_remote_url(repo_root)
        branch = _git_branch(repo_root)

    doc = render_doc(state, repo_root, run_active=run_active,
                     link_mode=args.link_mode, remote_url=remote_url, branch=branch)

    if args.stdout:
        sys.stdout.write(doc)
    else:
        out_path = repo_root / "LAZY_QUEUE.md"
        out_path.write_text(doc, encoding="utf-8")
        print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
