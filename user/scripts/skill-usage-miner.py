#!/usr/bin/env python3
"""
skill-usage-miner.py — offline skill-usage miner + dead-weight audit.

Feature: docs/features/skill-usage-miner/SPEC.md. Stdlib-only. READ-ONLY over
the session-log corpus AND both skills trees.

Joins a skill inventory (user-level ``user/skills/*/SKILL.md`` + repo-scoped
``repos/<name>/.claude/skills/*/SKILL.md``) against invocation signals mined
from Claude Code transcripts (``~/.claude/projects/**/*.jsonl`` plus
``**/subagents/agent-*.jsonl``) via TWO detectors, counted separately (D2):

  detector 1 — skill-tool: assistant-turn ``tool_use`` blocks with
               ``name == "Skill"`` (value-preserving read of ``input["skill"]``)
  detector 2 — slash: user-turn text matched by the field-proven marker regex
               ``<command-name>(/[\\w:-]+)</command-name>``
               (mine-sessions ``digest_sessions.py:125``, reused verbatim)

Both detectors UNDERCOUNT by construction — component-injected protocols,
auto-invoke prose usage, and off-workstation (cloud) sessions are invisible —
so a zero count is a flag to INVESTIGATE, never proof of deadness, and the
standing ``## Caveats`` block says so in every report.

> READ-ONLY INVARIANT (D9). This script opens every log file in read mode only
> and NEVER writes, renames, or deletes anything under the logs dir OR under
> ``user/skills/`` / ``repos/*/.claude/skills/``. The test suite hashes BOTH
> fixture trees before/after every run and asserts byte-identity. The only
> writes are stdout and an explicit ``--out`` path.

Archival is DELIBERATE (D8): the report emits ready-to-review proposal blocks
(``git mv`` + the ``archived/CLAUDE.md`` row) for age-gated never-invoked
skills; a human executes them. The miner never runs ``git mv``.

Toolify cross-feed is ANNOTATE-ONLY (D7): high-frequency skills are
cross-linked to ``docs/features/unified-pipeline-orchestrator/toolify-bar.md``;
this miner never invokes the sequence miner or the promotion pipeline.

Usage:
    python3 skill-usage-miner.py [--logs DIR] [--repo-root DIR]
                                 [--since YYYY-MM-DD]
                                 [--markdown | --json] [--out FILE]

Defaults: --logs ~/.claude/projects ; --repo-root = the claude-config checkout
containing this script; BOTH formats emitted when neither flag is given (D6).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Tunable constants (documented in the SPEC's decision entries).
# ---------------------------------------------------------------------------

#: D3 — the recency column window, in days. Anchored to the NEWEST corpus
#: timestamp (not wall clock) so a saved report is byte-stable.
RECENT_WINDOW_DAYS = 30

#: D7 — a skill whose TOTAL invocations (both detectors) reach this threshold
#: is annotated as a toolify candidate (annotate-only; the toolify bar judges
#: tool-call sequences, not skills — the annotation says where dances may live).
TOOLIFY_CANDIDATE_THRESHOLD = 10

#: D4 — cloud-variant skills (their sessions run off-workstation, so their
#: workstation-log counts are structurally biased low).
CLOUD_VARIANT_SUFFIX = "-cloud"

#: D7 cross-link target.
TOOLIFY_BAR_DOC = "docs/features/unified-pipeline-orchestrator/toolify-bar.md"

#: D2 detector-2 regex — verbatim from mine-sessions digest_sessions.py:125.
SLASH_MARKER_RE = re.compile(r"<command-name>(/[\w:-]+)</command-name>")

_CAVEATS = [
    "Component-injected protocols (`!cat` `_components/`) and auto-invoke prose usage are NOT "
    "counted (false negatives by construction).",
    "Cloud sessions are invisible to workstation logs; cloud-variant skills (`*-cloud`) "
    "undercount and are annotated, not ranked naively.",
    "Zero count = investigate, never proof of deadness. Archival is a human act — this miner "
    "proposes, never executes.",
]


# ---------------------------------------------------------------------------
# D1 — reuse the sibling miner's corpus walk (read-only), nothing else.
# ---------------------------------------------------------------------------

def _load_toolify_miner():
    spec = importlib.util.spec_from_file_location(
        "toolify_miner", str(Path(__file__).parent / "toolify-miner.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("toolify_miner", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_iter_log_files = _load_toolify_miner()._iter_log_files


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Hit:
    """One skill invocation signal: which skill, via which detector, where."""

    skill: str
    detector: str            # "skill_tool" | "slash"
    session: str             # project-qualified session key
    timestamp: str | None    # ISO string or None
    project: str             # encoded-cwd project dir name


@dataclass(frozen=True)
class SkillEntry:
    """One inventory row: a SKILL.md dispatcher found in the repo."""

    name: str
    scope: str               # "user" | "repo:<name>"
    repo: str | None
    skill_md: str            # repo-relative path (forward slashes)
    frontmatter_ok: bool


@dataclass
class Corpus:
    hits: list
    sessions: set
    ts_min: str | None       # YYYY-MM-DD
    ts_max: str | None       # YYYY-MM-DD
    found: bool


# ---------------------------------------------------------------------------
# Extraction — value-preserving (deliberately NOT _normalize_call, which
# elides exactly the values this miner needs).
# ---------------------------------------------------------------------------

def normalize_skill_name(raw) -> str | None:
    """Bare skill name: strip a leading '/' and any plugin-style 'ns:' prefix."""
    if not isinstance(raw, str):
        return None
    name = raw.strip().lstrip("/")
    if ":" in name:
        name = name.rsplit(":", 1)[-1]
    return name or None


def _texts_of_user_message(msg) -> list:
    content = msg.get("content")
    if isinstance(content, str):
        return [content]
    out = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    out.append(t)
    return out


def _session_and_project(path: Path, logs_dir: Path):
    """Session identity for one transcript file.

    ``<encoded-cwd>/<uuid>.jsonl`` is its own session; a subagent transcript
    ``<encoded-cwd>/<parent-uuid>/subagents/agent-<id>.jsonl`` attributes to
    its PARENT session (mine-sessions transcript anatomy).
    """
    try:
        rel = path.relative_to(logs_dir)
    except ValueError:
        rel = Path(path.name)
    parts = rel.parts
    project = parts[0] if len(parts) > 1 else ""
    if "subagents" in parts:
        idx = parts.index("subagents")
        session_id = parts[idx - 1] if idx >= 1 else rel.stem
    else:
        session_id = rel.stem
    return f"{project}/{session_id}", project


def _date_of(ts) -> str | None:
    if isinstance(ts, str) and len(ts) >= 10:
        d = ts[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            return d
    return None


def extract_hits(logs_dir) -> Corpus:
    """Scan the corpus READ-ONLY; return hits + session census + timestamp span.

    Malformed JSONL lines are skipped without crashing (the sibling miner's
    graceful-skip contract).
    """
    logs_dir = Path(logs_dir)
    hits: list = []
    sessions: set = set()
    ts_min = ts_max = None
    found = False
    for path in _iter_log_files(logs_dir):
        found = True
        session, project = _session_and_project(path, logs_dir)
        sessions.add(session)
        try:
            fh = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                ts = obj.get("timestamp")
                d = _date_of(ts)
                if d is not None:
                    ts_min = d if ts_min is None or d < ts_min else ts_min
                    ts_max = d if ts_max is None or d > ts_max else ts_max
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                otype = obj.get("type")
                if otype == "assistant":
                    content = msg.get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if (isinstance(block, dict)
                                and block.get("type") == "tool_use"
                                and block.get("name") == "Skill"):
                            inp = block.get("input")
                            skill = normalize_skill_name(
                                inp.get("skill") if isinstance(inp, dict) else None
                            )
                            if skill:
                                hits.append(Hit(skill, "skill_tool", session,
                                                ts if isinstance(ts, str) else None,
                                                project))
                elif otype == "user":
                    for txt in _texts_of_user_message(msg):
                        for m in SLASH_MARKER_RE.findall(txt):
                            skill = normalize_skill_name(m)
                            if skill:
                                hits.append(Hit(skill, "slash", session,
                                                ts if isinstance(ts, str) else None,
                                                project))
    return Corpus(hits=hits, sessions=sessions, ts_min=ts_min, ts_max=ts_max,
                  found=found)


# ---------------------------------------------------------------------------
# Inventory — user-level + repo-scoped SKILL.md dispatchers (read-only).
# ---------------------------------------------------------------------------

def _frontmatter_name(skill_md: Path) -> str | None:
    """The frontmatter ``name:`` value, scanning the whole frontmatter block
    (``name:`` is not always the first key). None on a malformed header."""
    try:
        lines = skill_md.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:60]:
        if line.strip() == "---":
            break
        m = re.match(r"^name:\s*(\S.*)$", line)
        if m:
            return m.group(1).strip()
    return None


def build_inventory(repo_root) -> list:
    """Enumerate every SKILL.md dispatcher in both skills trees (D4)."""
    repo_root = Path(repo_root)
    entries: list = []

    def _add(skill_dir: Path, scope: str, repo):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            return
        fm = _frontmatter_name(skill_md)
        entries.append(SkillEntry(
            name=fm if fm else skill_dir.name,
            scope=scope,
            repo=repo,
            skill_md=skill_md.relative_to(repo_root).as_posix(),
            frontmatter_ok=fm is not None,
        ))

    user_tree = repo_root / "user" / "skills"
    if user_tree.is_dir():
        for d in sorted(user_tree.iterdir()):
            if d.is_dir() and d.name != "_components":
                _add(d, "user", None)
    repos_tree = repo_root / "repos"
    if repos_tree.is_dir():
        for repo_dir in sorted(repos_tree.iterdir()):
            tree = repo_dir / ".claude" / "skills"
            if tree.is_dir():
                for d in sorted(tree.iterdir()):
                    if d.is_dir():
                        _add(d, f"repo:{repo_dir.name}", repo_dir.name)
    return entries


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def skill_added_date(repo_root, skill_md_rel) -> str | None:
    """D3 — first-commit date (YYYY-MM-DD) of the skill's SKILL.md, via
    ``git log --follow --diff-filter=A --format=%cs``. The LAST output line is
    the earliest add under --follow. Any failure degrades to None
    ("age unknown — age gate not applied"), never a crash. Read-only."""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "log", "--follow", "--diff-filter=A",
             "--format=%cs", "--", str(skill_md_rel)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
    if not lines:
        return None
    return _date_of(lines[-1])


def _proposal_row(entry: SkillEntry, created, age_days, n_sessions,
                  floor, end, cloud_note) -> dict:
    """One age-gated never-invoked row (D8 proposal text lands in Phase 3)."""
    return {
        "skill": entry.name,
        "scope": entry.scope,
        "created": created,
        "age_days": age_days,
        "cloud_note": cloud_note,
    }


def _shift_date(day: str, delta_days: int) -> str:
    d = _dt.date.fromisoformat(day) + _dt.timedelta(days=delta_days)
    return d.isoformat()


def _span_days(start: str, end: str) -> int:
    return (_dt.date.fromisoformat(end) - _dt.date.fromisoformat(start)).days


def build_report(repo_root, logs_dir, since=None) -> dict:
    """Assemble the full report structure (pure function of the two trees)."""
    repo_root = Path(repo_root)
    logs_dir = Path(logs_dir)
    corpus = extract_hits(logs_dir)
    inventory = build_inventory(repo_root)
    inv_names = {e.name for e in inventory}

    # --since filter (D3): drop hits strictly before the date; undated hits kept.
    hits = corpus.hits
    if since:
        hits = [h for h in hits
                if _date_of(h.timestamp) is None or _date_of(h.timestamp) >= since]
    floor = corpus.ts_min
    if since and floor is not None and since > floor:
        floor = since

    # Recency window anchored to the newest corpus timestamp (byte-stable).
    recent_start = (_shift_date(corpus.ts_max, -RECENT_WINDOW_DAYS)
                    if corpus.ts_max else None)

    # Aggregate per skill name.
    agg: dict = {}
    for h in hits:
        rec = agg.setdefault(h.skill, {
            "skill_tool": 0, "slash": 0, "sessions": set(),
            "last_seen": None, "recent": 0, "projects": [],
        })
        rec[h.detector] += 1
        rec["sessions"].add(h.session)
        d = _date_of(h.timestamp)
        if d is not None:
            if rec["last_seen"] is None or d > rec["last_seen"]:
                rec["last_seen"] = d
            if recent_start is not None and d >= recent_start:
                rec["recent"] += 1
        rec["projects"].append(h.project)

    usage = []
    for entry in inventory:
        rec = agg.get(entry.name)
        if rec is None:
            continue
        notes = []
        if entry.name.endswith(CLOUD_VARIANT_SUFFIX):
            notes.append("cloud-biased undercount")
        if entry.repo is not None:
            total_hits = len(rec["projects"])
            slug = entry.repo.lower().replace("-", "")
            matched = sum(1 for p in rec["projects"]
                          if slug in p.lower().replace("-", ""))
            notes.append(
                f"repo-attribution: {matched}/{total_hits} hits in "
                f"'{entry.repo}' project dirs (heuristic)"
            )
        usage.append({
            "skill": entry.name,
            "scope": entry.scope,
            "skill_tool": rec["skill_tool"],
            "slash": rec["slash"],
            "total": rec["skill_tool"] + rec["slash"],
            "sessions": len(rec["sessions"]),
            "last_seen": rec["last_seen"],
            "recent": rec["recent"],
            "notes": notes,
        })
    usage.sort(key=lambda r: (-r["total"], r["skill"]))

    # Zero-count rows: age-gated never-invoked (D3) vs not-gated (explicit reason).
    never_invoked: list = []
    zero_unaged: list = []
    span_ok = (corpus.found and floor is not None and corpus.ts_max is not None
               and _span_days(floor, corpus.ts_max) >= RECENT_WINDOW_DAYS)
    for entry in inventory:
        if entry.name in agg:
            continue
        cloud_note = ("cloud-biased undercount"
                      if entry.name.endswith(CLOUD_VARIANT_SUFFIX) else None)
        if not corpus.found:
            zero_unaged.append({"skill": entry.name, "scope": entry.scope,
                                "reason": "no corpus scanned",
                                "cloud_note": cloud_note})
            continue
        created = skill_added_date(repo_root, entry.skill_md)
        if created is None:
            zero_unaged.append({"skill": entry.name, "scope": entry.scope,
                                "reason": "age unknown — age gate not applied",
                                "cloud_note": cloud_note})
            continue
        if not span_ok:
            zero_unaged.append({
                "skill": entry.name, "scope": entry.scope,
                "reason": (f"corpus span < {RECENT_WINDOW_DAYS}d — "
                           "age gate not applied"),
                "cloud_note": cloud_note})
            continue
        if created >= floor:
            zero_unaged.append({
                "skill": entry.name, "scope": entry.scope,
                "reason": (f"skill younger than the observation floor "
                           f"(created {created}, floor {floor})"),
                "cloud_note": cloud_note})
            continue
        age_days = _span_days(created, corpus.ts_max)
        never_invoked.append(_proposal_row(entry, created, age_days,
                                           len(corpus.sessions), floor,
                                           corpus.ts_max, cloud_note))
    never_invoked.sort(key=lambda r: r["skill"])
    zero_unaged.sort(key=lambda r: r["skill"])

    # Toolify candidates (D7) land in Phase 4.
    toolify: list = []

    # Unknown invocations land in Phase 4.
    unknown: list = []

    return {
        "meta": {
            "logs_dir": str(logs_dir),
            "repo_root": str(repo_root),
            "since": since,
            "corpus_found": corpus.found,
            "corpus_start": corpus.ts_min,
            "corpus_end": corpus.ts_max,
            "observation_floor": floor,
            "sessions": len(corpus.sessions),
            "recent_window_days": RECENT_WINDOW_DAYS,
            "recent_window_start": recent_start,
            "toolify_threshold": TOOLIFY_CANDIDATE_THRESHOLD,
        },
        "usage": usage,
        "never_invoked": never_invoked,
        "zero_unaged": zero_unaged,
        "hygiene": [],  # D5 sweep lands in Phase 3
        "toolify_candidates": toolify,
        "unknown_invocations": unknown,
        "caveats": list(_CAVEATS),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(report) -> str:
    meta = report["meta"]
    lines: list = []
    if not meta["corpus_found"]:
        lines.append(f"## Skill usage — no corpus found at {meta['logs_dir']}")
        lines.append("")
        lines.append("No session transcripts were scanned; usage counts, the "
                     "never-invoked list, and toolify candidates are unavailable. "
                     "The inventory/hygiene sections below still reflect the repo.")
    else:
        since_note = f", since {meta['since']}" if meta["since"] else ""
        lines.append(
            f"## Skill usage (corpus: {meta['corpus_start']} → {meta['corpus_end']}, "
            f"{meta['sessions']} sessions, workstation logs only{since_note})"
        )
        lines.append("")
        lines.append("| rank | skill | scope | skill-tool | slash | sessions "
                     "| last seen | 30d | notes |")
        lines.append("|------|-------|-------|-----------|-------|----------"
                     "|-----------|-----|-------|")
        if report["usage"]:
            for i, r in enumerate(report["usage"], 1):
                notes = "; ".join(r["notes"])
                lines.append(
                    f"| {i} | {r['skill']} | {r['scope']} | {r['skill_tool']} "
                    f"| {r['slash']} | {r['sessions']} | {r['last_seen'] or '—'} "
                    f"| {r['recent']} | {notes} |"
                )
        else:
            lines.append("| — | (no skill invocations found in corpus) "
                         "| | | | | | | |")

    lines.append("")
    lines.append("## Never invoked (age-gated — candidates for deliberate archival)")
    if report["never_invoked"]:
        for r in report["never_invoked"]:
            cloud = f" [{r['cloud_note']}]" if r.get("cloud_note") else ""
            lines.append(f"- {r['skill']} ({r['scope']}) — created {r['created']}, "
                         f"age {r['age_days']}d{cloud}")
    else:
        lines.append("- (none)")
    if report["zero_unaged"]:
        lines.append("")
        lines.append("### Zero invocations — age gate not met (NOT proposed)")
        for r in report["zero_unaged"]:
            cloud = f" [{r['cloud_note']}]" if r.get("cloud_note") else ""
            lines.append(f"- {r['skill']} ({r['scope']}) — {r['reason']}{cloud}")

    lines.append("")
    lines.append("## Hygiene (non-skill artifacts in skills trees)")
    if report["hygiene"]:
        for f in report["hygiene"]:
            lines.append(f"- {f['path']} — {f['detail']}")
    else:
        lines.append("- (clean)")

    lines.append("")
    lines.append(f"## Toolify candidates (total invocations ≥ "
                 f"{meta['toolify_threshold']} — see {TOOLIFY_BAR_DOC})")
    if report["toolify_candidates"]:
        for r in report["toolify_candidates"]:
            lines.append(f"- {r['skill']} ({r['total']} invocations): {r['note']}")
    else:
        lines.append("- (none above threshold)")

    lines.append("")
    lines.append("## Unknown invocations (seen in logs, not in the inventory)")
    if report["unknown_invocations"]:
        for r in report["unknown_invocations"]:
            lines.append(f"- {r['skill']} — skill-tool {r['skill_tool']}, "
                         f"slash {r['slash']} (renamed/archived/plugin?)")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("## Caveats (standing)")
    for c in report["caveats"]:
        lines.append(f"- {c}")
    return "\n".join(lines) + "\n"


def render_json(report) -> str:
    return json.dumps(report, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _default_repo_root() -> Path:
    # <repo>/user/scripts/skill-usage-miner.py -> <repo>
    return Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline skill-usage miner + dead-weight audit "
                    "(read-only over session logs and skills trees).")
    parser.add_argument(
        "--logs", type=Path,
        default=Path(os.path.expanduser("~/.claude/projects")),
        help="logs directory (default: ~/.claude/projects)")
    parser.add_argument(
        "--repo-root", type=Path, default=_default_repo_root(),
        help="claude-config checkout (default: the repo containing this script)")
    parser.add_argument(
        "--since", type=str, default=None, metavar="YYYY-MM-DD",
        help="only count hits on/after this date")
    parser.add_argument("--markdown", action="store_true",
                        help="emit the markdown report")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the report to this file instead of stdout")
    args = parser.parse_args(argv)

    if args.since is not None:
        try:
            _dt.date.fromisoformat(args.since)
        except ValueError:
            parser.error(f"--since must be YYYY-MM-DD, got {args.since!r}")

    report = build_report(repo_root=args.repo_root, logs_dir=args.logs,
                          since=args.since)

    # D6: both formats when neither flag is given.
    emit_md = args.markdown or not args.json
    emit_json = args.json or not args.markdown

    chunks = []
    if emit_md:
        chunks.append(render_markdown(report))
    if emit_json:
        chunks.append(render_json(report) + "\n")
    text = "\n".join(chunks)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
