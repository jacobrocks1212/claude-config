#!/usr/bin/env python3
"""
lint-skills.py - Validate skill files for broken or dangerous !cat patterns.

Scans raw SKILL.md files (not projected output) and flags:
  1. Standalone injections targeting non-existent component files
  2. Embedded !cat patterns that the runtime may try to expand
  3. Capability namespace pollution in projected output

Exit code 0 = clean, 1 = issues found.
"""

import re
import sys
import argparse
from pathlib import Path

# Matches the literal trigger the runtime looks for anywhere on a line.
_RUNTIME_TRIGGER = re.compile(r'!`cat\s+')

# Standalone injection patterns (same as project-skills.py)
_SIMPLE_CAT = re.compile(
    r'^!`cat\s+~/.claude/skills/_components/(.+?)`$'
)
_FALLBACK_CAT = re.compile(
    r'^!`cat\s+\.claude/skill-config/(.+?)\s+2>/dev/null\s*\|\|\s*cat\s+~/.claude/skills/_components/(.+?)`$'
)
_FALLBACK_ECHO = re.compile(
    r'^!`cat\s+\.claude/skill-config/(.+?)\s+2>/dev/null\s*\|\|\s*echo\s+"(.+?)"`$'
)

_BEGIN_COMPONENT = re.compile(r'<!-- BEGIN component: (.+?) -->')


def _read_capabilities(project_dir: Path) -> set | None:
    """Read capabilities.txt from skill-config. Returns None if file absent."""
    cap_file = project_dir / ".claude" / "skill-config" / "capabilities.txt"
    if not cap_file.exists():
        return None
    lines = cap_file.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def _known_namespaces(skills_dir: Path) -> set:
    """Discover capability namespaces from _components/ subdirectories."""
    components_dir = skills_dir / "_components"
    if not components_dir.exists():
        return set()
    return {d.name for d in components_dir.iterdir() if d.is_dir()}


def lint_skill(skill_path: Path, skills_dir: Path) -> list[dict]:
    """Lint a single SKILL.md. Returns a list of issue dicts."""
    issues = []
    text = skill_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    for lineno, line in enumerate(lines, start=1):
        if not _RUNTIME_TRIGGER.search(line):
            continue

        stripped = line.strip()

        m = _SIMPLE_CAT.match(stripped)
        if m:
            comp = m.group(1)
            target = skills_dir / "_components" / comp
            if not target.exists():
                issues.append({
                    "file": str(skill_path),
                    "line": lineno,
                    "kind": "missing-component",
                    "detail": f"Component not found: _components/{comp}",
                    "text": line,
                })
            continue

        m = _FALLBACK_CAT.match(stripped)
        if m:
            comp = m.group(2)
            target = skills_dir / "_components" / comp
            if not target.exists():
                issues.append({
                    "file": str(skill_path),
                    "line": lineno,
                    "kind": "missing-component",
                    "detail": f"Component not found: _components/{comp}",
                    "text": line,
                })
            continue

        if _FALLBACK_ECHO.match(stripped):
            continue

        issues.append({
            "file": str(skill_path),
            "line": lineno,
            "kind": "embedded-pattern",
            "detail": "Line contains !`cat that is not a standalone injection — runtime will try to expand it",
            "text": line,
        })

    return issues


def lint_projected(projected_dir: Path) -> list[dict]:
    """Scan projected output directory for any remaining !cat patterns."""
    issues = []

    if not projected_dir.exists():
        return issues

    for md_file in sorted(projected_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _RUNTIME_TRIGGER.search(line):
                issues.append({
                    "file": str(md_file),
                    "line": lineno,
                    "kind": "unexpanded-cat",
                    "detail": "Projected file still contains !cat directive — projection script failed to expand it",
                    "text": line,
                })

    return issues


def lint_capabilities(
    projected_dir: Path,
    repos_dir: Path,
    skills_dir: Path,
) -> list[dict]:
    """Check projected output for capability namespace violations.

    For each repo projection:
    - Warns if no capabilities.txt exists (no filtering applied)
    - Errors if projected output contains namespaced components the repo doesn't declare
    """
    issues = []

    if not projected_dir.exists() or not repos_dir.exists():
        return issues

    namespaces = _known_namespaces(skills_dir)
    if not namespaces:
        return issues

    for repo_proj_dir in sorted(projected_dir.iterdir()):
        if not repo_proj_dir.is_dir() or repo_proj_dir.name == "_default":
            continue

        repo_path = repos_dir / repo_proj_dir.name
        if not repo_path.exists():
            continue

        caps = _read_capabilities(repo_path)

        if caps is None:
            issues.append({
                "file": str(repo_proj_dir),
                "line": 0,
                "kind": "missing-capabilities",
                "detail": (f"Repo '{repo_proj_dir.name}' has skill-config/ but no capabilities.txt "
                           f"— all namespaced components included (known namespaces: {', '.join(sorted(namespaces))})"),
                "text": "",
            })
            continue

        for md_file in sorted(repo_proj_dir.rglob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                m = _BEGIN_COMPONENT.match(line.strip())
                if not m:
                    continue
                comp_name = m.group(1)
                if "/" not in comp_name:
                    continue
                ns = comp_name.split("/", 1)[0]
                if ns in namespaces and ns not in caps:
                    issues.append({
                        "file": str(md_file),
                        "line": lineno,
                        "kind": "capability-pollution",
                        "detail": (f"Component '{comp_name}' requires capability '{ns}' "
                                   f"but repo declares: [{', '.join(sorted(caps)) if caps else 'none'}]"),
                        "text": line,
                    })

    return issues


def lint_all(skills_dir: Path) -> list[dict]:
    """Lint every SKILL.md under skills_dir (excluding _components/)."""
    all_issues = []

    if not skills_dir.exists():
        print(f"Skills directory not found: {skills_dir}", file=sys.stderr)
        sys.exit(2)

    for skill_subdir in sorted(skills_dir.iterdir()):
        if not skill_subdir.is_dir() or skill_subdir.name == "_components":
            continue
        skill_file = skill_subdir / "SKILL.md"
        if not skill_file.exists():
            continue
        all_issues.extend(lint_skill(skill_file, skills_dir))

    return all_issues


def _print_issues(issues: list[dict], base_dir: Path | None = None) -> None:
    """Print formatted issue list."""
    for issue in issues:
        if base_dir:
            try:
                rel = Path(issue["file"]).relative_to(base_dir)
            except ValueError:
                rel = Path(issue["file"])
        else:
            rel = Path(issue["file"])

        line_suffix = f":{issue['line']}" if issue["line"] else ""
        print(f"\n  {rel}{line_suffix}  [{issue['kind']}]")
        print(f"    {issue['detail']}")
        if issue["text"].strip():
            print(f"    > {issue['text'].strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate skill files for broken or dangerous !cat patterns."
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path.home() / ".claude" / "skills",
        help="Directory containing skill subdirectories (default: ~/.claude/skills)",
    )
    parser.add_argument(
        "--check-projected",
        type=Path,
        nargs="?",
        const=Path.home() / ".claude" / "skills-projected",
        default=None,
        metavar="DIR",
        help="Also scan projected output directory for unexpanded !cat patterns",
    )
    parser.add_argument(
        "--check-capabilities",
        action="store_true",
        help="Check projected output for capability namespace pollution (requires --check-projected and --repos-dir)",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path.home() / "source" / "repos",
        help="Directory containing git repos (for capability checks)",
    )
    args = parser.parse_args()
    skills_dir = args.skills_dir.expanduser().resolve()

    exit_code = 0

    # Source lint
    issues = lint_all(skills_dir)

    if not issues:
        print("OK — no broken or embedded !cat patterns found.")
    else:
        _print_issues(issues, skills_dir)
        print(f"\n{len(issues)} issue(s) found.")
        exit_code = 1

    # Projected output lint
    if args.check_projected is not None:
        projected_dir = args.check_projected.expanduser().resolve()
        projected_issues = lint_projected(projected_dir)
        if not projected_issues:
            print(f"OK — no unexpanded !cat patterns in projected output ({projected_dir}).")
        else:
            _print_issues(projected_issues, projected_dir)
            print(f"\n{len(projected_issues)} unexpanded !cat directive(s) found in projected output.")
            exit_code = 1

        # Capability checks
        if args.check_capabilities:
            repos_dir = args.repos_dir.expanduser().resolve()
            namespaces = _known_namespaces(skills_dir)
            if namespaces:
                print(f"Known capability namespaces: {', '.join(sorted(namespaces))}")
            cap_issues = lint_capabilities(projected_dir, repos_dir, skills_dir)
            warnings = [i for i in cap_issues if i["kind"] == "missing-capabilities"]
            errors = [i for i in cap_issues if i["kind"] == "capability-pollution"]

            if warnings:
                print(f"\n{len(warnings)} capability warning(s):")
                _print_issues(warnings, projected_dir)

            if errors:
                _print_issues(errors, projected_dir)
                print(f"\n{len(errors)} capability pollution error(s) found.")
                exit_code = 1
            elif not warnings:
                print("OK — no capability namespace pollution detected.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
