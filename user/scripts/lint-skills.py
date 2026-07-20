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

# Insert this directory onto sys.path so `import skill_repos` resolves whether
# the script is run directly (~/.claude/scripts/lint-skills.py) or loaded as a
# module in tests (mirrors the bug-state.py / lazy-state.py sibling-import guard).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_repos import iter_config_repos, resolve_internal_repos_root
import cli_surface

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


def _skill_dirs_under(skills_root: Path) -> set:
    """Return the set of skill subdirectory names under a `.../skills` dir.

    A skill subdirectory is any immediate child dir (excluding `_components`)
    that contains a `SKILL.md`. Missing/unreadable roots yield an empty set.
    """
    names = set()
    if not skills_root.exists():
        return names
    try:
        children = list(skills_root.iterdir())
    except OSError:
        return names
    for child in children:
        if not child.is_dir() or child.name == "_components":
            continue
        if (child / "SKILL.md").exists():
            names.add(child.name)
    return names


def lint_planner_resolution(
    repos_dir: Path,
    user_skills_dir: Path,
    internal_repos_dir: Path | None = None,
) -> list[dict]:
    """Enforce the D1 deterministic-planner-resolution invariants.

    Positive: a skill named `write-plan-cognito` must resolve under some
    `repos/*/.claude/skills/` directory (the renamed Cognito lane planner), and
    its name must NOT collide with a same-named user-level skill (there must be
    no `write-plan-cognito` under the user skills dir — distinct names are the
    whole point of the rename).

    Negative ("One generic executor, no Cognito fork"): NO skill or directory
    named `execute-plan-cognito` may exist anywhere under `repos/*/.claude/skills/`
    or the user skills dir — execution always runs the single generic
    `/execute-plan`.
    """
    issues: list[dict] = []

    user_names = _skill_dirs_under(user_skills_dir)

    # Resolve repo skill roots from the UNION of the passed `repos_dir` (sibling
    # working copies under ~/source/repos) and the canonical, git-tracked internal
    # `<claude-config>/repos/`, deduplicated by resolved skills-root path. The
    # internal scan is an EXPLICIT parameter (not a hidden __file__ derivation) so
    # this function stays hermetically testable: production `main()` passes
    # `resolve_internal_repos_root()`; tests pass an empty dir to isolate. This is
    # what makes D1 resolution machine-independent — the gate must find
    # `write-plan-cognito` whether or not sibling checkouts exist under
    # ~/source/repos (see docs/bugs/planner-resolution-lint-blind-to-internal-repos
    # and docs/bugs/project-skills-under-projects-machine-variable-repos-dir).
    # Shared with project-skills.py via skill_repos.iter_config_repos.
    repo_skill_roots: list[Path] = [
        repo / ".claude" / "skills"
        for repo in iter_config_repos(repos_dir, internal_repos_dir, ".claude/skills")
    ]

    repo_names: set = set()
    for root in repo_skill_roots:
        repo_names |= _skill_dirs_under(root)

    # Positive: write-plan-cognito resolves under a repo skills dir.
    if "write-plan-cognito" not in repo_names:
        issues.append({
            "file": str(repos_dir),
            "line": 0,
            "kind": "planner-resolution",
            "detail": (
                "Cognito planner not found: no `write-plan-cognito` skill resolves "
                "under any repos/*/.claude/skills/ (D1 rename must be present)"
            ),
            "text": "",
        })

    # Positive: no same-name collision against a user-level skill.
    if "write-plan-cognito" in user_names:
        issues.append({
            "file": str(user_skills_dir / "write-plan-cognito"),
            "line": 0,
            "kind": "planner-collision",
            "detail": (
                "`write-plan-cognito` exists at the user level — it must be "
                "repo-scoped only, or it shadows the Cognito lane planner"
            ),
            "text": "",
        })

    # Negative: no execute-plan-cognito anywhere.
    for root in repo_skill_roots:
        offender = root / "execute-plan-cognito"
        if offender.exists():
            issues.append({
                "file": str(offender),
                "line": 0,
                "kind": "executor-fork",
                "detail": (
                    "`execute-plan-cognito` exists — there must be exactly one "
                    "generic /execute-plan executor (no Cognito fork)"
                ),
                "text": "",
            })
    if "execute-plan-cognito" in user_names:
        issues.append({
            "file": str(user_skills_dir / "execute-plan-cognito"),
            "line": 0,
            "kind": "executor-fork",
            "detail": (
                "`execute-plan-cognito` exists at the user level — there must be "
                "exactly one generic /execute-plan executor (no Cognito fork)"
            ),
            "text": "",
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


def build_parser() -> argparse.ArgumentParser:
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
        "--check-parity",
        action="store_true",
        help="Run the lazy skill-family parity audit (lazy_parity_audit.audit_all_pairs) across all five canonical/derived pairs; non-zero on drift.",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path.home() / "source" / "repos",
        help="Directory containing git repos (for capability checks)",
    )
    parser.add_argument(
        "--check-skill-config",
        action="store_true",
        help=(
            "Also run the skill-config schema + reference lint (lint-skill-config.py): "
            "repos/*/.claude/skill-config/ MANIFEST.json validation, build-queue-ops.json "
            "schema checks, and the cross-repo .claude/skill-config/<file> reference sweep."
        ),
    )
    parser.add_argument(
        "--check-skill-size",
        action="store_true",
        help=(
            "Also run the skill-size ratchet (skill-size-ratchet.py, lazy-batch-skill-deflation "
            "D3): per-file byte + long-line ceiling check against the committed "
            "skill-size-baseline.json. Opt-in per file; a file not listed is unaffected."
        ),
    )
    parser.add_argument(
        "--check-cli-surface",
        action="store_true",
        help=(
            "Also run the CLI-surface prose/fence lint (cli-surface-lint.py, "
            "state-cli-contract-registry): every --flag mention in skills/components/"
            "user/scripts/CLAUDE.md attributed to a roster script is checked against "
            "docs/cli/cli-surface.json."
        ),
    )
    cli_surface.add_dump_cli_surface_flag(parser)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    _dump = cli_surface.maybe_handle_dump_cli_surface(args, parser, "lint-skills.py")
    if _dump is not None:
        sys.exit(_dump)

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

    # D1 deterministic-planner-resolution invariants (always run):
    # `write-plan-cognito` resolves repo-scoped with no user-level collision,
    # and no `execute-plan-cognito` fork exists anywhere.
    repos_dir = args.repos_dir.expanduser().resolve()
    # Production always unions the canonical internal repos/ so D1 resolution is
    # machine-independent regardless of the host's ~/source/repos layout.
    planner_issues = lint_planner_resolution(
        repos_dir, skills_dir, resolve_internal_repos_root()
    )
    if not planner_issues:
        print("OK — planner resolution: write-plan-cognito resolves; no execute-plan-cognito fork.")
    else:
        _print_issues(planner_issues, repos_dir)
        print(f"\n{len(planner_issues)} planner-resolution issue(s) found.")
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

    # Lazy skill-family parity audit (optional standalone run; the hard gate is test_lazy_parity.py)
    if args.check_parity:
        import lazy_parity_audit  # same directory as this script
        parity_repo_root = Path(__file__).resolve().parents[2]  # user/scripts/lint-skills.py -> repo root
        parity_findings = lazy_parity_audit.audit_all_pairs(parity_repo_root)
        if parity_findings:
            for finding in parity_findings:
                print(finding)
            print(f"\n{len(parity_findings)} lazy-parity drift finding(s) found.")
            exit_code = 1
        else:
            print("OK — lazy skill-family parity: zero drift across all five pairs.")

    # Skill-config schema + reference lint (optional; skill-config-schema-and-reference-lint).
    if args.check_skill_config:
        import importlib.util as _ilu
        _sc_spec = _ilu.spec_from_file_location(
            "lint_skill_config", Path(__file__).resolve().parent / "lint-skill-config.py"
        )
        lint_skill_config = _ilu.module_from_spec(_sc_spec)
        _sc_spec.loader.exec_module(lint_skill_config)
        sc_repo_root = Path(__file__).resolve().parents[2]
        sc_errors, sc_warnings = lint_skill_config.run(sc_repo_root)
        for w in sc_warnings:
            print(w.render(sc_repo_root))
        if sc_warnings:
            print(f"\n{len(sc_warnings)} skill-config warning(s).")
        if sc_errors:
            for e in sc_errors:
                print(e.render(sc_repo_root))
            print(f"\n{len(sc_errors)} skill-config lint error(s) found.")
            exit_code = 1
        else:
            print("OK — skill-config schema + reference lint clean.")

    # Skill-size ratchet (optional; lazy-batch-skill-deflation D3).
    if args.check_skill_size:
        import importlib.util as _ilu
        _ss_spec = _ilu.spec_from_file_location(
            "skill_size_ratchet", Path(__file__).resolve().parent / "skill-size-ratchet.py"
        )
        skill_size_ratchet = _ilu.module_from_spec(_ss_spec)
        _ss_spec.loader.exec_module(skill_size_ratchet)
        ss_repo_root = Path(__file__).resolve().parents[2]
        ss_baseline = skill_size_ratchet.load_baseline(skill_size_ratchet.default_baseline_path())
        ss_findings = skill_size_ratchet.check(ss_repo_root, ss_baseline)
        # cycle-prompt-deflation Phase 1 (WU-3): also run the assembled-cycle-prompt
        # profile ratchet so `--check-skill-size` (and the gate battery that shells
        # it) gates the assembled prompt, not just whole files.
        ss_profile_findings = skill_size_ratchet.check_profiles(ss_repo_root, ss_baseline)
        if ss_findings or ss_profile_findings:
            for finding in ss_findings:
                if finding["metric"] == "missing":
                    print(f"MISSING  {finding['file']} — listed in baseline but not found on disk")
                else:
                    print(
                        f"OVER-CEILING  {finding['file']}  {finding['metric']}="
                        f"{finding['current']} > ceiling={finding['ceiling']}"
                    )
            for finding in ss_profile_findings:
                if finding["metric"] == "refused":
                    print(
                        f"REFUSED  profile {finding['profile']} — emitter could not "
                        f"assemble: {finding.get('note')}"
                    )
                else:
                    print(
                        f"OVER-CEILING  profile {finding['profile']}  {finding['metric']}="
                        f"{finding['current']} > ceiling={finding['ceiling']}"
                    )
            total = len(ss_findings) + len(ss_profile_findings)
            print(f"\n{total} skill-size ratchet finding(s) found.")
            exit_code = 1
        else:
            ss_profile_count = sum(
                1 for k in (ss_baseline.get("profiles") or {}) if not k.startswith("_")
            )
            print(
                f"OK — skill-size ratchet: {len(ss_baseline['files'])} file(s) and "
                f"{ss_profile_count} assembled cycle-prompt profile(s) within ceiling."
            )

    # CLI-surface prose/fence lint (optional; state-cli-contract-registry).
    if args.check_cli_surface:
        import importlib.util as _ilu
        _cs_spec = _ilu.spec_from_file_location(
            "cli_surface_lint", Path(__file__).resolve().parent / "cli-surface-lint.py"
        )
        cli_surface_lint = _ilu.module_from_spec(_cs_spec)
        _cs_spec.loader.exec_module(cli_surface_lint)
        cs_repo_root = Path(__file__).resolve().parents[2]
        cs_findings = cli_surface_lint.lint_repo(cs_repo_root)
        if cs_findings:
            for finding in cs_findings:
                print(finding.render())
            print(f"\n{len(cs_findings)} CLI-surface lint finding(s) found.")
            exit_code = 1
        else:
            print("OK — CLI-surface lint: no stale --flag mentions.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
