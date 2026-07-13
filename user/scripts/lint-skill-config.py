#!/usr/bin/env python3
"""
lint-skill-config.py — Schema + reference lint for repos/*/.claude/skill-config/.

Feature: skill-config-schema-and-reference-lint.

`repos/<name>/.claude/skill-config/` is the harness's per-repo override surface. Nothing
declared which files a repo intends to provide, so absence was ambiguous by construction
(the #1 tool-error cluster in the mined AlgoBooth corpus: 377 failed Reads of the absent
`commit-policy.md`). This script closes that gap with THREE checks, run together:

  1. **Manifest validation (D1).** Each repo's skill-config/ dir carries a `MANIFEST.json`
     declaring `provides` (files it ships) and `intended_absent` (known cross-repo
     references it deliberately does not provide, each with a required `reason`). The
     bidirectional `provides` check keeps the manifest honest: declared-but-missing and
     present-but-undeclared are both errors.
  2. **JSON-schema validation (D2).** Load-bearing `*.json` configs (today: only
     `build-queue-ops.json`, which arms the fail-open `build-queue-enforce.sh` hook) get a
     stdlib structural checker, dispatched via the manifest's `json_schemas` map. An
     unregistered JSON file in skill-config/ is a WARNING (undeclared machine-read
     surface), not an error.
  3. **Reference sweep (D3).** Every `.claude/skill-config/<file>` mention across every
     skill source — user-level (`user/skills/**/SKILL.md` + `user/skills/_components/**/*.md`,
     checked against EVERY repo) and repo-scoped (`repos/<name>/.claude/skills/**/SKILL.md`,
     checked against only that repo) — is resolved against each repo's on-disk skill-config/
     dir, honoring `intended_absent`. A reference that resolves to an absent, UNDECLARED
     file is a dangling-reference error. A reference to a file that IS declared
     `intended_absent` is only OK when the reference form carries a fallback (a `!cat X
     2>/dev/null || cat _components/X` / `|| echo "..."` line, or prose language describing
     what happens when the file is absent) — `intended_absent` can never rescue a bare
     prose pointer with no fallback (the `long-build-ownership.md` class: a file that
     exists ONLY in one repo, pointed at by user-level prose with no fallback, so the
     pointer is dead everywhere else).

**Suppression, and why it lives here instead of inline in the skill file (Open Question 4
resolution).** The SPEC's D3 design left "prose-scan suppression syntax" as an
implementation-time choice, illustratively an inline comment in the referencing file. This
script instead uses the `SUPPRESSIONS` allowlist below: every genuinely-dead reference this
sweep finds today (see the allowlist) lives in `user/skills/**` or `repos/*/.claude/skills/**`,
which this feature does NOT own (concurrent SKILLS-lane work is in flight on those trees —
see the feature's COMPLETED.md / final report). Editing those files to add an inline marker
would be an out-of-lane write. A script-owned, reason-required allowlist keeps the same
"debt visible, never silent" invariant (the suppressed finding still PRINTS as a WARNING,
naming the file/line/reason) without touching a tree this feature doesn't own. Each entry is
a follow-up for whoever next edits the referencing skill file.

Exit codes: 0 clean (warnings allowed), 1 one or more errors, 2 malformed CLI usage.
Stdlib only. Pure read over `user/skills/` and `repos/*/.claude/skills/`; the only writes
this repo makes as part of the feature are the authored MANIFEST.json files themselves
(not by this script — those are hand-authored siblings of `build-queue-ops.json`).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent

MANIFEST_FILENAME = "MANIFEST.json"


# ---------------------------------------------------------------------------
# Reuse lint-skills.py's !cat regex forms (DRY — see module docstring)
# ---------------------------------------------------------------------------

def _load_lint_skills():
    spec = importlib.util.spec_from_file_location(
        "lint_skills", _SCRIPTS_DIR / "lint-skills.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------

class Issue:
    """One lint finding. `severity` is 'error' or 'warning'."""

    def __init__(self, repo, kind, detail, severity="error", file=None, line=0):
        self.repo = repo
        self.kind = kind
        self.detail = detail
        self.severity = severity
        self.file = file
        self.line = line

    def render(self, base_dir: Path | None = None) -> str:
        tag = "ERROR" if self.severity == "error" else "WARN"
        loc = ""
        if self.file is not None:
            f = self.file
            if base_dir is not None:
                try:
                    f = Path(self.file).resolve().relative_to(base_dir.resolve())
                except ValueError:
                    pass
            loc = f"  ({f}:{self.line})" if self.line else f"  ({f})"
        return f"[{tag}] ({self.repo}) {self.kind}: {self.detail}{loc}"


# ---------------------------------------------------------------------------
# D2 — JSON-schema checkers (stdlib structural validation, one per known config)
# ---------------------------------------------------------------------------

def check_build_queue_ops(data) -> list[str]:
    """Structural checker for build-queue-ops.json — shape derived from what
    build-queue-enforce.sh actually reads (command registration entries)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["top-level value must be an object"]
    if data.get("version") != 1:
        errors.append(f"'version' must be 1 (got {data.get('version')!r})")
    ops = data.get("ops")
    if not isinstance(ops, dict) or not ops:
        errors.append("'ops' must be a non-empty object")
        return errors
    for op_name, entry in ops.items():
        label = f"ops.{op_name}"
        if not isinstance(entry, dict):
            errors.append(f"{label}: must be an object")
            continue
        exec_ = entry.get("exec")
        if not isinstance(exec_, str) or not exec_.strip():
            errors.append(f"{label}.exec: must be a non-empty string")
        if entry.get("kind") not in ("build", "test"):
            errors.append(f"{label}.kind: must be 'build' or 'test' (got {entry.get('kind')!r})")
        hygiene = entry.get("hygiene")
        if not isinstance(hygiene, str) or not hygiene.strip():
            errors.append(f"{label}.hygiene: must be a non-empty string")
        skill = entry.get("skill")
        if not isinstance(skill, str) or not skill.startswith("/"):
            errors.append(f"{label}.skill: must be a string starting with '/' (got {skill!r})")
        deny = entry.get("deny")
        if not isinstance(deny, list) or not deny or not all(
            isinstance(d, str) and d.strip() for d in deny
        ):
            errors.append(f"{label}.deny: must be a non-empty list of non-empty strings")
        lane = entry.get("lane")
        if lane is not None and lane not in ("fast", "heavy"):
            errors.append(f"{label}.lane: must be 'fast' or 'heavy' when present (got {lane!r})")
    return errors


# Dispatched via a manifest's `json_schemas` map: {"build-queue-ops.json": "build-queue-ops"}.
JSON_SCHEMA_CHECKERS = {
    "build-queue-ops": check_build_queue_ops,
}


# ---------------------------------------------------------------------------
# D1 — MANIFEST.json schema + bidirectional provides check
# ---------------------------------------------------------------------------

def validate_manifest(data) -> list[str]:
    """Structural + honesty checks on a parsed MANIFEST.json (schema_version 1)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["MANIFEST.json top-level value must be an object"]

    if data.get("schema_version") != 1:
        errors.append(f"schema_version must be 1 (got {data.get('schema_version')!r})")

    provides_raw = data.get("provides")
    if not isinstance(provides_raw, list) or not all(
        isinstance(x, str) and x for x in provides_raw
    ):
        errors.append("provides must be a list of non-empty strings")
        provides_raw = []
    if len(set(provides_raw)) != len(provides_raw):
        errors.append("provides contains duplicate entries")

    intended_absent = data.get("intended_absent", [])
    if not isinstance(intended_absent, list):
        errors.append("intended_absent must be a list")
        intended_absent = []
    seen_ia: set[str] = set()
    for i, entry in enumerate(intended_absent):
        if not isinstance(entry, dict):
            errors.append(f"intended_absent[{i}] must be an object")
            continue
        f = entry.get("file")
        reason = entry.get("reason")
        if not isinstance(f, str) or not f:
            errors.append(f"intended_absent[{i}].file must be a non-empty string")
            f = None
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"intended_absent[{i}] (file={f!r}) missing a non-empty 'reason'")
        if f is not None:
            if f in seen_ia:
                errors.append(f"intended_absent has a duplicate entry for {f!r}")
            seen_ia.add(f)

    json_schemas = data.get("json_schemas", {})
    if not isinstance(json_schemas, dict):
        errors.append("json_schemas must be an object")
        json_schemas = {}
    else:
        for fname, key in json_schemas.items():
            if key not in JSON_SCHEMA_CHECKERS:
                errors.append(
                    f"json_schemas[{fname!r}] references unknown schema {key!r} "
                    f"(known: {sorted(JSON_SCHEMA_CHECKERS)})"
                )

    overlap = set(provides_raw) & seen_ia
    if overlap:
        errors.append(
            f"file(s) declared in BOTH provides and intended_absent: {sorted(overlap)}"
        )

    return errors


def bidirectional_provides_check(skill_config_dir: Path, manifest: dict) -> list[str]:
    """provides <-> disk, both directions. MANIFEST.json itself is excluded from the
    disk-scan (it describes the directory; it does not describe itself)."""
    errors: list[str] = []
    try:
        on_disk = {
            p.name
            for p in skill_config_dir.iterdir()
            if p.is_file() and p.name != MANIFEST_FILENAME
        }
    except OSError:
        return [f"cannot list {skill_config_dir}"]

    provides = set(manifest.get("provides") or [])
    for f in sorted(provides - on_disk):
        errors.append(f"declared in provides but not found on disk: {f}")
    for f in sorted(on_disk - provides):
        errors.append(f"present on disk but not declared in provides: {f}")
    return errors


# ---------------------------------------------------------------------------
# D3 — Reference sweep
# ---------------------------------------------------------------------------

_SKILL_CONFIG_REF = re.compile(
    r"\.claude/skill-config/([A-Za-z0-9_][A-Za-z0-9_-]*\.(?:md|json|txt|yml))"
)

# Heuristic: a prose line that describes what happens when the file is absent (a
# natural-language fallback) rather than a bare "the file lives at X" pointer. Deliberately
# generous — false negatives here just mean a real fallback gets flagged loudly, which is
# the safe failure direction (visible, not silent).
_PROSE_FALLBACK_HINTS = re.compile(
    r"if absent|if it doesn.t exist|no-?op|absent\s*→|fallback|standard pattern|"
    r"or the standard|instead|2>/dev/null|configured for this repo|catalog absent",
    re.IGNORECASE,
)

# Script-owned suppression allowlist — see the module docstring's "Suppression" section.
# Keyed on (source file, repo-relative POSIX path from repo_root; referenced skill-config
# filename). Downgrades a finding from error to a printed warning; never deletes it.
SUPPRESSIONS: dict[tuple[str, str], str] = {
    ("user/skills/lazy-batch/SKILL.md", "long-build-ownership.md"):
        "bare prose pointer ('Full rule: ...'), no fallback form, file exists only in "
        "AlgoBooth — SKILLS-lane follow-up: give it a fallback or scope the mention to "
        "AlgoBooth (skill-config-schema-and-reference-lint final report).",
    ("user/skills/lazy-bug-batch/SKILL.md", "long-build-ownership.md"):
        "same class as lazy-batch/SKILL.md (mirrors the coupled pair) — SKILLS-lane follow-up.",
    ("user/skills/lazy-batch/SKILL.md", "cycle-prompt-addenda.md"):
        "bare prose pointer, no fallback form, file exists only in AlgoBooth — SKILLS-lane "
        "follow-up (skill-config-schema-and-reference-lint final report).",
    ("user/skills/_components/lazy-dispatch-template.md", "cycle-prompt-addenda.md"):
        "same class — component prose, no fallback form — SKILLS-lane follow-up.",
    ("user/skills/ingest-research/SKILL.md", "gemini-sprint.md"):
        "aspirational: \"parameterize ... later\" — not a live reference to any repo today.",
}


class Reference:
    __slots__ = ("source", "lineno", "target", "has_fallback")

    def __init__(self, source: Path, lineno: int, target: str, has_fallback: bool):
        self.source = source
        self.lineno = lineno
        self.target = target
        self.has_fallback = has_fallback


def iter_skill_sources(skills_dir: Path) -> list[Path]:
    """Every SKILL.md (recursive — covers namespaced dirs like lazy-batch-prompts/) plus
    every _components/**/*.md under one skills tree."""
    out: list[Path] = []
    if not skills_dir.exists():
        return out
    out.extend(sorted(skills_dir.rglob("SKILL.md")))
    comp_dir = skills_dir / "_components"
    if comp_dir.exists():
        out.extend(sorted(comp_dir.rglob("*.md")))
    return out


def scan_source_for_refs(path: Path, lint_skills_mod) -> list[Reference]:
    """Parse one skill source for skill-config references: the two fallback-bearing
    !cat forms (reusing lint-skills.py's own patterns) plus a prose scan for every other
    literal `.claude/skill-config/<file>` mention."""
    refs: list[Reference] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return refs

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()

        m = lint_skills_mod._FALLBACK_CAT.match(stripped)
        if m:
            refs.append(Reference(path, lineno, m.group(1), True))
            continue

        m = lint_skills_mod._FALLBACK_ECHO.match(stripped)
        if m:
            refs.append(Reference(path, lineno, m.group(1), True))
            continue

        for pm in _SKILL_CONFIG_REF.finditer(line):
            target = pm.group(1)
            if path.name == target:
                # A _components/<name>.md file documenting its OWN per-repo override
                # path (e.g. "the project-specific version lives at
                # .claude/skill-config/<name>.md, which is cat'd in place of this
                # file") is self-description of the fallback pattern, not a second,
                # independent consumption site — the real reference is the SKILL.md
                # !cat line that pulls this same component in, counted separately
                # (and correctly fallback-tagged) elsewhere.
                continue
            has_fallback = bool(_PROSE_FALLBACK_HINTS.search(line))
            refs.append(Reference(path, lineno, target, has_fallback))

    return refs


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _on_disk_files(skill_config_dir: Path) -> set[str]:
    if not skill_config_dir.is_dir():
        return set()
    try:
        return {
            p.name for p in skill_config_dir.iterdir()
            if p.is_file() and p.name != MANIFEST_FILENAME
        }
    except OSError:
        return set()


def _intended_absent_map(manifest: dict | None) -> dict[str, str]:
    if not manifest:
        return {}
    out: dict[str, str] = {}
    for e in manifest.get("intended_absent", []) or []:
        if isinstance(e, dict) and isinstance(e.get("file"), str):
            out[e["file"]] = e.get("reason", "")
    return out


def _check_refs_against_repo(
    refs: list[Reference],
    repo_name: str,
    on_disk: set[str],
    intended_absent: dict[str, str],
    repo_root: Path,
) -> list[Issue]:
    issues: list[Issue] = []
    by_target: dict[str, list[Reference]] = {}
    for r in refs:
        by_target.setdefault(r.target, []).append(r)

    for target, target_refs in sorted(by_target.items()):
        if target in on_disk:
            continue  # present — fine regardless of fallback/declaration
        for r in target_refs:
            src_rel = _rel(r.source, repo_root)
            suppress_reason = SUPPRESSIONS.get((src_rel, target))
            if target not in intended_absent:
                msg = (
                    f"{target} referenced at {src_rel}:{r.lineno} but absent from "
                    f"{repo_name}'s skill-config/ and not declared intended_absent"
                )
                kind = "dangling-reference"
            elif not r.has_fallback:
                msg = (
                    f"{target} referenced at {src_rel}:{r.lineno} as a bare pointer with "
                    f"no fallback form — intended_absent cannot rescue a fallback-less pointer"
                )
                kind = "fallback-less-pointer"
            else:
                continue  # absent + declared intended_absent + has fallback => OK
            severity = "warning" if suppress_reason else "error"
            if suppress_reason:
                msg += f"  [suppressed: {suppress_reason}]"
            issues.append(Issue(repo_name, kind, msg, severity, r.source, r.lineno))
    return issues


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def discover_repo_names(repos_root: Path) -> list[str]:
    if not repos_root.is_dir():
        return []
    return sorted(
        p.name
        for p in repos_root.iterdir()
        if p.is_dir() and (p / ".claude" / "skill-config").is_dir()
    )


def run(repo_root: Path) -> tuple[list[Issue], list[Issue]]:
    """Run every check. Returns (errors, warnings)."""
    lint_skills_mod = _load_lint_skills()
    repos_root = repo_root / "repos"
    repo_names = discover_repo_names(repos_root)

    all_issues: list[Issue] = []
    manifests: dict[str, dict | None] = {}

    for name in repo_names:
        scdir = repos_root / name / ".claude" / "skill-config"
        mpath = scdir / MANIFEST_FILENAME
        if not mpath.exists():
            all_issues.append(
                Issue(name, "missing-manifest", f"{scdir} has no MANIFEST.json", "error", mpath)
            )
            manifests[name] = None
            continue
        try:
            data = json.loads(mpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            all_issues.append(Issue(name, "malformed-manifest", str(e), "error", mpath))
            manifests[name] = None
            continue

        manifests[name] = data
        for e in validate_manifest(data):
            all_issues.append(Issue(name, "manifest-schema", e, "error", mpath))
        for e in bidirectional_provides_check(scdir, data):
            all_issues.append(Issue(name, "manifest-provides", e, "error", mpath))

        json_schemas = data.get("json_schemas", {})
        json_schemas = json_schemas if isinstance(json_schemas, dict) else {}
        for fname, key in json_schemas.items():
            checker = JSON_SCHEMA_CHECKERS.get(key)
            if checker is None:
                continue  # already flagged by validate_manifest
            fpath = scdir / fname
            if not fpath.exists():
                continue  # already flagged by bidirectional_provides_check
            try:
                fdata = json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                all_issues.append(Issue(name, f"json-schema:{key}", f"malformed JSON: {e}", "error", fpath))
                continue
            for e in checker(fdata):
                all_issues.append(Issue(name, f"json-schema:{key}", e, "error", fpath))

        try:
            for jp in sorted(scdir.glob("*.json")):
                if jp.name == MANIFEST_FILENAME:
                    continue
                if jp.name not in json_schemas:
                    all_issues.append(
                        Issue(
                            name, "unregistered-json",
                            f"{jp.name} has no json_schemas entry (unvalidated machine-read surface)",
                            "warning", jp,
                        )
                    )
        except OSError:
            pass

    # Reference sweep.
    user_skills_dir = repo_root / "user" / "skills"
    user_refs: list[Reference] = []
    for src in iter_skill_sources(user_skills_dir):
        user_refs.extend(scan_source_for_refs(src, lint_skills_mod))

    for name in repo_names:
        on_disk = _on_disk_files(repos_root / name / ".claude" / "skill-config")
        intended_absent = _intended_absent_map(manifests.get(name))
        all_issues.extend(
            _check_refs_against_repo(user_refs, name, on_disk, intended_absent, repo_root)
        )

    for name in repo_names:
        repo_skills_dir = repos_root / name / ".claude" / "skills"
        repo_refs: list[Reference] = []
        for src in iter_skill_sources(repo_skills_dir):
            repo_refs.extend(scan_source_for_refs(src, lint_skills_mod))
        on_disk = _on_disk_files(repos_root / name / ".claude" / "skill-config")
        intended_absent = _intended_absent_map(manifests.get(name))
        all_issues.extend(
            _check_refs_against_repo(repo_refs, name, on_disk, intended_absent, repo_root)
        )

    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]
    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schema + reference lint for repos/*/.claude/skill-config/."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="claude-config checkout root (default: derived from this script's location).",
    )
    args = parser.parse_args()
    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).expanduser().resolve()

    errors, warnings = run(repo_root)

    for w in warnings:
        print(w.render(repo_root))
    if warnings:
        print(f"\n{len(warnings)} warning(s).")

    if errors:
        for e in errors:
            print(e.render(repo_root))
        print(f"\n{len(errors)} error(s).")
        sys.exit(1)

    print("OK — skill-config schema + reference lint clean.")
    sys.exit(0)


if __name__ == "__main__":
    main()
