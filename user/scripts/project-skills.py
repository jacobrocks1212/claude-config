#!/usr/bin/env python3
"""
project-skills.py - Resolve skill files by expanding !cat component includes.

Walks a skills directory, resolves all !cat directives in each SKILL.md,
and writes the expanded output to a projected output directory.

Capability namespaces: Components under _components/{namespace}/ are only
included when the project's skill-config/capabilities.txt declares that
namespace. Missing capabilities.txt = include all (permissive default).
"""

import re
import sys
import shutil
import argparse
from pathlib import Path
from typing import Optional


# Regex patterns for the three !cat forms
_SIMPLE_CAT = re.compile(
    r'^!`cat\s+~/.claude/skills/_components/(.+?)`$'
)
_FALLBACK_CAT = re.compile(
    r'^!`cat\s+\.claude/skill-config/(.+?)\s+2>/dev/null\s*\|\|\s*cat\s+~/.claude/skills/_components/(.+?)`$'
)
_FALLBACK_ECHO = re.compile(
    r'^!`cat\s+\.claude/skill-config/(.+?)\s+2>/dev/null\s*\|\|\s*echo\s+"(.+?)"`$'
)


def _read_capabilities(project_dir: Path) -> Optional[set]:
    """Read capabilities.txt from skill-config. Returns None if file absent (include all)."""
    cap_file = project_dir / ".claude" / "skill-config" / "capabilities.txt"
    if not cap_file.exists():
        return None
    lines = cap_file.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def _extract_namespace(component_path: str) -> Optional[str]:
    """Extract namespace from 'namespace/component.md'. Returns None for flat components."""
    if "/" in component_path:
        return component_path.split("/", 1)[0]
    return None


def _wrap(name: str, content: str) -> str:
    """Wrap resolved component content in BEGIN/END markers."""
    return f"<!-- BEGIN component: {name} -->\n{content}<!-- END component: {name} -->"


def _resolve_file_content(
    file_path: Path,
    skills_dir: Path,
    project_dir: Path,
    resolved_stack: set,
    capabilities: Optional[set] = None,
) -> str:
    """Read a file and recursively resolve any !cat lines within it."""
    if not file_path.exists():
        return ""
    raw = file_path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    resolved_lines = []
    for line in lines:
        stripped = line.rstrip("\n")
        resolved_lines.append(
            resolve_cat_line(stripped, skills_dir, project_dir, resolved_stack, capabilities)
        )
    return "\n".join(resolved_lines) + ("\n" if raw.endswith("\n") else "")


def resolve_cat_line(
    line: str,
    skills_dir: Path,
    project_dir: Path,
    resolved_stack: Optional[set] = None,
    capabilities: Optional[set] = None,
) -> str:
    """
    Resolve a single line. If it matches a !cat pattern, expand it.
    Otherwise return the line unchanged.

    Capability gating: if the component path is namespaced (e.g. mcp/foo.md)
    and capabilities is not None and the namespace is not in capabilities,
    the component is skipped with a comment marker.
    """
    if resolved_stack is None:
        resolved_stack = set()

    stripped = line.strip()

    # --- Simple: !`cat ~/.claude/skills/_components/<name>` ---
    m = _SIMPLE_CAT.match(stripped)
    if m:
        name = m.group(1)
        ns = _extract_namespace(name)
        if ns and capabilities is not None and ns not in capabilities:
            return f"<!-- SKIPPED component: {name} (capability '{ns}' not declared) -->"
        target = skills_dir / "_components" / name
        abs_target = str(target.resolve()) if target.exists() else str(target)
        if abs_target in resolved_stack:
            return f"<!-- CIRCULAR INCLUDE DETECTED: {name} -->"
        resolved_stack = resolved_stack | {abs_target}
        content = _resolve_file_content(target, skills_dir, project_dir, resolved_stack, capabilities)
        return _wrap(name, content)

    # --- Fallback with cat ---
    m = _FALLBACK_CAT.match(stripped)
    if m:
        proj_name = m.group(1)
        comp_name = m.group(2)
        proj_file = project_dir / ".claude" / "skill-config" / proj_name
        if proj_file.exists():
            content = proj_file.read_text(encoding="utf-8")
            return _wrap(proj_name, content)
        else:
            ns = _extract_namespace(comp_name)
            if ns and capabilities is not None and ns not in capabilities:
                return f"<!-- SKIPPED component: {comp_name} (capability '{ns}' not declared) -->"
            fallback = skills_dir / "_components" / comp_name
            abs_fallback = str(fallback.resolve()) if fallback.exists() else str(fallback)
            if abs_fallback in resolved_stack:
                return f"<!-- CIRCULAR INCLUDE DETECTED: {comp_name} -->"
            resolved_stack = resolved_stack | {abs_fallback}
            content = _resolve_file_content(fallback, skills_dir, project_dir, resolved_stack, capabilities)
            return _wrap(comp_name, content)

    # --- Fallback with echo ---
    m = _FALLBACK_ECHO.match(stripped)
    if m:
        proj_name = m.group(1)
        echo_text = m.group(2)
        proj_file = project_dir / ".claude" / "skill-config" / proj_name
        if proj_file.exists():
            content = proj_file.read_text(encoding="utf-8")
            return _wrap(proj_name, content)
        else:
            return echo_text

    return line


def resolve_skill_file(
    skill_path: Path,
    skills_dir: Path,
    project_dir: Path,
    capabilities: Optional[set] = None,
) -> str:
    """
    Read a SKILL.md, expand all !cat lines, return full expanded text.
    Frontmatter (YAML between --- delimiters) is preserved verbatim.
    """
    raw = skill_path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=False)
    resolved_lines = []

    in_frontmatter = False
    frontmatter_done = False
    fm_count = 0

    for line in lines:
        if not frontmatter_done and line.strip() == "---":
            fm_count += 1
            in_frontmatter = fm_count == 1
            if fm_count == 2:
                in_frontmatter = False
                frontmatter_done = True
            resolved_lines.append(line)
            continue

        if in_frontmatter:
            resolved_lines.append(line)
            continue

        resolved_lines.append(resolve_cat_line(line, skills_dir, project_dir, capabilities=capabilities))

    return "\n".join(resolved_lines) + ("\n" if raw.endswith("\n") else "")


def project_skills(
    skills_dir: Path,
    output_dir: Path,
    project_dir: Path,
    capabilities: Optional[set] = None,
) -> dict:
    """
    Walk skills_dir for subdirectories containing SKILL.md (excluding _components/).
    Resolve each and write to output_dir/<skill-name>/SKILL.md.

    Returns {"skills_projected": int, "components_resolved": int, "components_skipped": int, "errors": list}
    """
    skills_projected = 0
    components_resolved = 0
    components_skipped = 0
    errors = []

    if not skills_dir.exists():
        return {"skills_projected": 0, "components_resolved": 0, "components_skipped": 0,
                "errors": [f"skills_dir not found: {skills_dir}"]}

    for skill_subdir in sorted(skills_dir.iterdir()):
        if not skill_subdir.is_dir():
            continue
        if skill_subdir.name == "_components":
            continue
        skill_file = skill_subdir / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            raw = skill_file.read_text(encoding="utf-8")
            cat_count = sum(
                1 for line in raw.splitlines()
                if line.strip().startswith("!`cat")
            )

            expanded = resolve_skill_file(skill_file, skills_dir, project_dir, capabilities)
            skip_count = expanded.count("<!-- SKIPPED component:")

            out_dir = output_dir / skill_subdir.name
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "SKILL.md").write_text(expanded, encoding="utf-8")

            skills_projected += 1
            components_resolved += cat_count
            components_skipped += skip_count
        except Exception as exc:
            errors.append(f"{skill_subdir.name}: {exc}")

    return {
        "skills_projected": skills_projected,
        "components_resolved": components_resolved,
        "components_skipped": components_skipped,
        "errors": errors,
    }


def project_all(skills_dir: Path, output_dir: Path, repos_dir: Path) -> dict:
    """
    Project skills for _default and all repos that have .claude/skill-config/.

    _default projection includes ALL capabilities (no filtering).
    Repo projections filter by capabilities.txt when present.
    """
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    default_summary = project_skills(
        skills_dir=skills_dir,
        output_dir=output_dir / "_default",
        project_dir=skills_dir,
        capabilities=None,
    )

    repos_summaries: dict = {}

    if repos_dir.exists():
        for repo_path in sorted(repos_dir.iterdir()):
            if not repo_path.is_dir():
                continue
            skill_config_dir = repo_path / ".claude" / "skill-config"
            if not skill_config_dir.is_dir():
                continue
            caps = _read_capabilities(repo_path)
            repo_summary = project_skills(
                skills_dir=skills_dir,
                output_dir=output_dir / repo_path.name,
                project_dir=repo_path,
                capabilities=caps,
            )
            repo_summary["capabilities"] = sorted(caps) if caps is not None else None
            repos_summaries[repo_path.name] = repo_summary

    return {
        "default": default_summary,
        "repos": repos_summaries,
        "repos_discovered": len(repos_summaries),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve skill files by expanding !cat component includes."
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path.home() / ".claude" / "skills",
        help="Directory containing skill subdirectories (default: ~/.claude/skills)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / ".claude" / "skills-projected",
        help="Directory to write resolved skills (default: ~/.claude/skills-projected)",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path("."),
        help="Project root for resolving .claude/skill-config overrides (default: .)",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path.home() / "source" / "repos",
        help="Directory containing git repos to scan for .claude/skill-config/ overrides",
    )
    args = parser.parse_args()

    skills_dir = args.skills_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    repos_dir = args.repos_dir.expanduser().resolve()

    if repos_dir.exists():
        summary = project_all(
            skills_dir=skills_dir,
            output_dir=output_dir,
            repos_dir=repos_dir,
        )
        default_s = summary["default"]
        print(f"Skills projected (_default): {default_s['skills_projected']}")
        print(f"Components resolved (_default): {default_s['components_resolved']}")
        if default_s["errors"]:
            print(f"Errors in _default ({len(default_s['errors'])}):")
            for err in default_s["errors"]:
                print(f"  - {err}")
        else:
            print("Errors (_default)  : none")
        print(f"Repos discovered   : {summary['repos_discovered']}")
        for repo_name, repo_s in summary["repos"].items():
            caps = repo_s.get("capabilities")
            caps_str = f" caps=[{','.join(caps)}]" if caps is not None else " caps=ALL"
            skipped_str = f", {repo_s['components_skipped']} skipped" if repo_s["components_skipped"] else ""
            print(f"  {repo_name}: {repo_s['skills_projected']} skills, "
                  f"{repo_s['components_resolved']} components{skipped_str}{caps_str}"
                  + (f", {len(repo_s['errors'])} error(s)" if repo_s["errors"] else ""))
    else:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = project_skills(
            skills_dir=skills_dir,
            output_dir=output_dir,
            project_dir=args.project_dir.expanduser().resolve(),
        )
        print(f"Skills projected : {summary['skills_projected']}")
        print(f"Components resolved: {summary['components_resolved']}")
        if summary["components_skipped"]:
            print(f"Components skipped : {summary['components_skipped']}")
        if summary["errors"]:
            print(f"Errors ({len(summary['errors'])}):")
            for err in summary["errors"]:
                print(f"  - {err}")
        else:
            print("Errors           : none")


if __name__ == "__main__":
    main()
