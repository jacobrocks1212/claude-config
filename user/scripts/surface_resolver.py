"""
surface_resolver.py — Shared MCP surface-existence resolver.

Consumed by:
  - F5 (lazy-validation-readiness Phase 4): curation-time pre-screen per feature
  - F8 (lazy-validation-readiness Phase 5): authoring-time lint per scenario

The resolver answers two questions given a repo root:
  1. Which MCP tool names are *registered* (present in registrations/ *.rs files)?
  2. Which MCP tool names are *asserted* by a given scenario file?
  3. Of the asserted names, which are UNRESOLVED (not registered)?

Spec: docs/specs/lazy-validation-readiness/SPEC.md §F5 + §F8
"""

import re
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Regex constants — authoritative formats per the prompt specification.
# ---------------------------------------------------------------------------

# Matches ANY register_tool_*! macro invocation (post, get, post_action,
# get_query, and any future suffix — the [a-z_]* wildcard is intentional).
# The first capture group is the bare tool-name identifier (snake_case).
# Uses MULTILINE so \s* correctly spans newlines between macro name and identifier.
_REGISTER_RE = re.compile(
    r"register_tool_[a-z_]*!\s*\(\s*([a-z0-9_]+)",
    re.MULTILINE,
)

# Matches a quoted tool-name string literal inside a GOLDEN_TOOL_NAMES array.
# The capture group is the bare identifier.
_GOLDEN_ENTRY_RE = re.compile(r'"([a-z0-9_]+)"')

# Matches POST /tools/<name> or GET /tools/<name> in scenario markdown.
# Tool names are lowercase snake_case (alphanumeric + underscore).
_SCENARIO_TOOL_RE = re.compile(
    r"\b(?:POST|GET)\s+/tools/([a-z0-9_]+)"
)

# Maximum byte size we'll attempt to read as a "symlink pointer" file.
# Real symlink files on Windows (git symlinks stored as text) are tiny —
# they contain just the relative target path.  A real scenario file will
# be much larger.  We use 512 bytes as the threshold.
_SYMLINK_POINTER_MAX_BYTES = 512


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def _parse_golden_tool_names(
    text: str,
    *,
    golden_array_name: str = "GOLDEN_TOOL_NAMES",
) -> set[str]:
    """Extract tool-name string literals from a GOLDEN_TOOL_NAMES array in Rust source.

    Finds the block starting at ``<golden_array_name>`` ... ``= [`` (or ``= &[``) up to
    the next ``];`` and extracts every ``"<identifier>"`` string literal inside it.

    Returns an empty set if the named array is absent — callers treat that as
    "no authoritative list available, fall back to macro matches only".
    """
    # Find the start of the array declaration.
    start_idx = text.find(golden_array_name)
    if start_idx == -1:
        return set()

    # Find the opening bracket after the array name (allowing for type annotations
    # and optional `&` reference sigil: e.g. `= &[`, `= [`, `: &[&str] = &[`).
    bracket_idx = text.find("[", start_idx)
    if bracket_idx == -1:
        return set()

    # Find the matching closing bracket + semicolon `];`.
    end_idx = text.find("];", bracket_idx)
    if end_idx == -1:
        return set()

    # Extract only the slice between `[` and `];`.
    array_body = text[bracket_idx + 1 : end_idx]

    return set(_GOLDEN_ENTRY_RE.findall(array_body))


def registered_tools(
    repo_root: Path,
    *,
    registrations_glob: str = "src-tauri/src/ipc/mcp/registrations/*.rs",
    golden_array_name: str = "GOLDEN_TOOL_NAMES",
) -> set[str]:
    """Return the set of MCP tool names registered in the given repo.

    Returns the UNION of two sources:

    1. **All ``register_tool_*!`` macro first-args** — scans every *.rs file
       matched by ``registrations_glob`` for any macro of the form
       ``register_tool_<suffix>!(tool_name, ...)`` (post, get, post_action,
       get_query, and any future suffix) and collects the bare identifier.
       This is the "belt-and-braces" set: it catches tools in repos that have
       no golden list, and provides cross-validation in those that do.

    2. **The ``GOLDEN_TOOL_NAMES`` array entries** — parses the ``mod.rs`` file
       (found via the same glob) for the named array and extracts every quoted
       string literal inside it.  This is the *authoritative* complete tool set:
       it is a behaviour-preservation test golden that lists EVERY registered MCP
       tool name, including tools whose macro registration files the glob might not
       reach (e.g. feature-gated submodules) or tools registered via mechanisms
       other than the macros.  Tools present ONLY in GOLDEN_TOOL_NAMES (e.g.
       ``play``, ``stop``, ``reset_state``) would be false-positively flagged as
       "missing" by a macro-only scan — hence the union.

    The ``golden_array_name`` kwarg makes the golden-array name configurable so
    the function remains generic for repos that use a different constant name.
    If the array is absent, only the macro matches are returned (no error).

    Pure filesystem operation — tolerates a missing registrations directory
    by returning an empty set, so the caller never has to guard for it.
    """
    root = Path(repo_root)
    names: set[str] = set()

    # Expand the glob relative to repo_root.
    for rs_file in root.glob(registrations_glob):
        try:
            text = rs_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # Individual file unreadable; skip but keep going.
            continue

        # Source 1: all register_tool_*! macro first-args (any suffix).
        for match in _REGISTER_RE.finditer(text):
            names.add(match.group(1))

        # Source 2: GOLDEN_TOOL_NAMES array entries (authoritative complete set).
        # Multiple files are scanned; the golden list is expected in mod.rs but
        # we check every file in the glob so the caller doesn't need to name it.
        golden = _parse_golden_tool_names(text, golden_array_name=golden_array_name)
        names.update(golden)

    return names


def asserted_tools(scenario_text: str) -> set[str]:
    """Return the set of MCP tool names asserted in a scenario's text.

    Parses lines of the form ``POST /tools/<name>`` or ``GET /tools/<name>``
    and returns the set of unique tool names found.
    """
    return set(_SCENARIO_TOOL_RE.findall(scenario_text))


def _resolve_scenario_text(scenario_path: Path) -> str:
    """Read a scenario file, following Windows git-symlink pointers.

    On Windows, git stores symlinks as small text files containing the
    relative target path (mode 120000 in the index).  Python's ``Path``
    does not recognise them as symlinks (``is_symlink()`` returns False),
    so we detect them by size: if the file is tiny and its content looks
    like a relative path (no newlines, no MCP tool call patterns), we
    resolve the pointer and read the target instead.

    Falls back gracefully to reading the original file content if anything
    goes wrong, so legitimate tiny scenario files are not silently skipped.
    """
    path = Path(scenario_path)

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FileNotFoundError(
            f"Cannot read scenario file: {scenario_path}"
        ) from exc

    # Heuristic: real symlink pointers are tiny and contain only a relative
    # path string (no whitespace other than a possible trailing newline).
    if len(raw) <= _SYMLINK_POINTER_MAX_BYTES:
        candidate = raw.decode("utf-8", errors="replace").strip()
        # A relative path pointer has no spaces, starts with "../" or a name,
        # and does not look like scenario markdown (no "#", "POST", "GET").
        if (
            candidate
            and "\n" not in candidate
            and " " not in candidate
            and not candidate.startswith("#")
            and "POST" not in candidate
            and "GET" not in candidate
        ):
            # Attempt to resolve it relative to the file's parent directory.
            resolved = (path.parent / candidate).resolve()
            if resolved.exists() and resolved != path.resolve():
                try:
                    return resolved.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass  # Fall through to reading the original.

    return raw.decode("utf-8", errors="replace")


def unresolved_tools(
    scenario_path: Path,
    repo_root: Path,
    *,
    registrations_glob: str = "src-tauri/src/ipc/mcp/registrations/*.rs",
) -> list[str]:
    """Return a sorted list of tool names asserted in a scenario but not registered.

    Reads the scenario at ``scenario_path`` (following Windows git-symlink
    pointers — AlgoBooth feature ``mcp-tests/`` entries are git symlinks to
    ``docs/testing/mcp-tests/*.md``), extracts all asserted tool names, and
    subtracts the set returned by ``registered_tools(repo_root)``.

    Returns a sorted list (deterministic; stable across Python runs) of the
    missing tool names, or an empty list when all asserted tools are registered.
    """
    text = _resolve_scenario_text(scenario_path)
    asserted = asserted_tools(text)
    registered = registered_tools(repo_root, registrations_glob=registrations_glob)
    missing = asserted - registered
    return sorted(missing)


# ---------------------------------------------------------------------------
# Standalone CLI (informational — exit 0; Phase 5/F8 adds --lint / exit !=0)
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Usage:
        python surface_resolver.py --repo-root <root> <scenario.md> [...]

    Prints unresolved tool names per scenario.  Exit code is always 0 in the
    base CLI (informational).  Phase 5 / F8 adds ``--lint`` which exits
    non-zero when any unresolved tool is found.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "surface_resolver.py — Check which MCP tools asserted by scenario(s) "
            "are not registered in the target repo.  Exit 0 (informational).  "
            "Phase 5 adds --lint for non-zero exit on findings."
        )
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        metavar="ROOT",
        help="Root of the target repository (must contain src-tauri/src/ipc/mcp/registrations/).",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        default=False,
        help=(
            "Exit non-zero if any scenario asserts an unresolved tool.  "
            "(Phase 5 / F8 mode — reserved for that phase.)"
        ),
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        metavar="SCENARIO",
        help="Path(s) to scenario .md file(s) to check.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    any_missing = False

    for scenario_str in args.scenarios:
        scenario_path = Path(scenario_str)
        try:
            missing = unresolved_tools(scenario_path, repo_root)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            any_missing = True
            continue

        if missing:
            any_missing = True
            print(
                f"{scenario_path}: UNRESOLVED tools — {', '.join(missing)}"
            )
        else:
            print(f"{scenario_path}: OK (all asserted tools registered)")

    if args.lint and any_missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
