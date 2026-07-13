#!/usr/bin/env python3
"""
cli-surface-lint.py — Prose/fence lint of `--flag` mentions against the
committed CLI-surface registry (state-cli-contract-registry Phase 2 / D2-A).

Scans skills/components/scripts-CLAUDE.md prose for `--flag` tokens, attributes
each to a roster script via a same-line co-occurrence rule (a roster script's
basename and a `--flag` token appearing on the SAME logical line — consecutive
lines joined on a trailing backslash count as one logical line, covering
multi-line shell continuations), and flags a flag that is not in that script's
`docs/cli/cli-surface.json` entry as an ERROR (unless the mention line carries
the `<!-- cli-surface: historical -->` exemption marker, mirroring
doc-drift-lint.py's DIVERGENCE_MARKER precedent).

A bare `--flag` token with no attributable roster script on the same line is
ignored (false-positive control — most `--flag`-shaped tokens in this repo's
prose belong to non-roster CLIs). A line mentioning MORE THAN ONE roster
script is also skipped (ambiguous attribution) rather than risk a false
positive against the wrong script's surface.

Scanned surface (D2-A):
  - user/skills/**/SKILL.md
  - user/skills/_components/*.md
  - repos/*/.claude/skills/**/*.md
  - repos/*/.claude/skill-config/**/*.md
  - user/scripts/CLAUDE.md

CLI:
    python3 user/scripts/cli-surface-lint.py --repo-root .
    Exit 0 clean / 1 findings / 2 malformed input (registry missing/unreadable).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

REGISTRY_REL_PATH = Path("docs") / "cli" / "cli-surface.json"
EXEMPTION_MARKER = "cli-surface: historical"

_FLAG_TOKEN_RE = re.compile(r"(?<![\w-])--[A-Za-z][A-Za-z0-9-]*")


class Finding:
    __slots__ = ("path", "line_no", "script", "flag", "nearest", "flag_count")

    def __init__(self, path, line_no, script, flag, nearest, flag_count):
        self.path = path
        self.line_no = line_no
        self.script = script
        self.flag = flag
        self.nearest = nearest
        self.flag_count = flag_count

    def render(self) -> str:
        nearest_txt = f"nearest: {self.nearest}" if self.nearest else "no close match"
        return (
            f"ERROR {self.path}:{self.line_no}: {self.script} has no flag {self.flag} "
            f"({nearest_txt}; registry entry: {self.script}, {self.flag_count} flags). "
            f"Fix the prose or regenerate docs/cli/cli-surface.json if the script changed."
        )


def load_registry(repo_root: Path) -> dict:
    path = repo_root / REGISTRY_REL_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _known_names(script_entry: dict) -> set[str]:
    names = set()
    for flag in script_entry.get("flags", []):
        if flag.get("positional"):
            continue
        names.add(flag["name"])
        names.update(flag.get("aliases", []))
    return names


def _roster_pattern(roster_names: list[str]) -> re.Pattern:
    alts = "|".join(re.escape(name) for name in sorted(roster_names, key=len, reverse=True))
    return re.compile(rf"\b(?:{alts})\b")


def _iter_scan_files(repo_root: Path):
    patterns = [
        "user/skills/**/SKILL.md",
        "user/skills/_components/*.md",
        "repos/*/.claude/skills/**/*.md",
        "repos/*/.claude/skill-config/**/*.md",
    ]
    seen = set()
    for pattern in patterns:
        for path in sorted(repo_root.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path
    scripts_claude_md = repo_root / "user" / "scripts" / "CLAUDE.md"
    if scripts_claude_md.is_file() and scripts_claude_md not in seen:
        yield scripts_claude_md


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+")


def _logical_lines(text: str):
    """Yield (start_line_no, joined_text) — consecutive lines ending with a
    trailing backslash (shell continuation) are merged into one logical
    line, attributed to the FIRST physical line number."""
    raw_lines = text.splitlines()
    i = 0
    n = len(raw_lines)
    while i < n:
        start = i
        parts = [raw_lines[i]]
        while parts[-1].rstrip().endswith("\\") and i + 1 < n:
            i += 1
            parts.append(raw_lines[i])
        yield start + 1, " ".join(p.rstrip("\\").rstrip() for p in parts)
        i += 1


def _attribution_units(text: str):
    """Yield (line_no, sentence_text, exempted) — the actual attribution
    grain (SPEC D2: "same code fence or same prose line/SENTENCE"). A single
    markdown line can be a huge multi-sentence table cell (this repo's
    script tables are one line per script), so a naive whole-line unit
    over-attributes a flag that belongs to a DIFFERENT, non-roster tool
    mentioned earlier in the same line to a roster script mentioned later
    in it. Splitting on '.'/';' boundaries keeps genuine same-clause
    co-mentions (e.g. "shells `lazy-state.py --enqueue-adhoc`") attributed
    while separating unrelated clauses packed into one line. `exempted` is
    computed at the LOGICAL-LINE level (not per-sentence) — the marker
    exempts its whole mention line regardless of which clause it lands in
    after the period/semicolon split."""
    for line_no, line in _logical_lines(text):
        exempted = EXEMPTION_MARKER in line
        for sentence in _SENTENCE_SPLIT_RE.split(line):
            if sentence.strip():
                yield line_no, sentence, exempted


def lint_text(path_label: str, text: str, registry: dict, roster_pattern: re.Pattern) -> list[Finding]:
    findings: list[Finding] = []
    scripts = registry.get("scripts", {})
    for line_no, line, exempted in _attribution_units(text):
        if exempted:
            continue
        mentioned = sorted(set(roster_pattern.findall(line)))
        if len(mentioned) != 1:
            continue  # no attributable script, or ambiguous (>1) — skip
        script = mentioned[0]
        script_entry = scripts.get(script)
        if script_entry is None:
            continue  # roster script not (yet) in the registry — nothing to check against
        known = _known_names(script_entry)
        flag_count = len(known)
        for match in _FLAG_TOKEN_RE.finditer(line):
            flag = match.group(0)
            if flag == script:  # defensive; flags never equal a script name
                continue
            if flag in known:
                continue
            nearest_matches = difflib.get_close_matches(flag, sorted(known), n=1, cutoff=0.3)
            nearest = nearest_matches[0] if nearest_matches else None
            findings.append(Finding(path_label, line_no, script, flag, nearest, flag_count))
    return findings


def lint_repo(repo_root: Path) -> list[Finding]:
    registry = load_registry(repo_root)
    roster_pattern = _roster_pattern(list(registry.get("scripts", {}).keys()))
    findings: list[Finding] = []
    for path in _iter_scan_files(repo_root):
        text = path.read_text(encoding="utf-8", errors="replace")
        label = str(path.relative_to(repo_root)).replace("\\", "/")
        findings.extend(lint_text(label, text, registry, roster_pattern))
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lint every --flag mention in skills/components/scripts-CLAUDE.md "
                    "attributed to a roster script against docs/cli/cli-surface.json."
    )
    parser.add_argument("--repo-root", default=".", help="claude-config repo root (default: cwd)")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    registry_path = repo_root / REGISTRY_REL_PATH
    if not registry_path.is_file():
        print(f"cli-surface-lint.py: {REGISTRY_REL_PATH} not found — run "
              f"cli_surface_gen.py --repo-root {args.repo_root} first", file=sys.stderr)
        return 2
    try:
        findings = lint_repo(repo_root)
    except json.JSONDecodeError as exc:
        print(f"cli-surface-lint.py: malformed registry: {exc}", file=sys.stderr)
        return 2

    if not findings:
        print("OK — cli-surface-lint: no stale --flag mentions found.")
        return 0
    for finding in findings:
        print(finding.render())
    print(f"\ncli-surface-lint.py: {len(findings)} finding(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
