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

--lint mode (Phase 5 / F8):
  python surface_resolver.py --lint --repo-root <root> <scenario.md> [...]

  For each scenario, prints an ERROR line for every unresolved tool:
      ERROR: <scenario_path>:<line> asserts unregistered MCP tool '<name>' — not found
             in registrations/ (and not in GOLDEN_TOOL_NAMES)

  Exit code: 1 if any non-allowlisted unresolved tool is found; 0 if all clean.

Built-in allowlist (not MCP tools — control pseudo-steps):
  - sleep  : OS-level sleep directive, not an MCP tool endpoint
  Extend at runtime with repeatable --allow <name> flags.

  Do NOT allowlist evaluate_code / read_file / audio_perceptual_quality — those
  are genuine surface gaps the lint is designed to catch.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

# Insert this directory onto sys.path so `import cli_surface` resolves whether
# this script is run directly or loaded as a module in tests (mirrors the
# bug-state.py / lazy-state.py sibling-import guard).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_surface

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


def asserted_tools_with_lines(text: str) -> list[tuple[int, str]]:
    """Return a list of (line_number, tool_name) for every tool assertion in ``text``.

    Scans for ``POST /tools/<name>`` or ``GET /tools/<name>`` occurrences and
    returns the 1-based line number alongside each tool name.  Duplicate tool
    names may appear more than once (once per occurrence in the text).

    This is the *with-location* companion to ``asserted_tools``.  The lint
    (``run_lint``) uses it to produce precise file:line error messages so the
    author can jump directly to the offending line.  The set-based
    ``asserted_tools`` is preserved for callers that only need the unique set
    (e.g., ``unresolved_tools`` and the F5 pre-screen).
    """
    results: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in _SCENARIO_TOOL_RE.finditer(line):
            results.append((line_no, match.group(1)))
    return results


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
# Built-in non-tool allowlist
# ---------------------------------------------------------------------------

# Names that appear in scenario files as ``POST /tools/<name>`` or
# ``GET /tools/<name>`` but are NOT MCP tool registrations — they are control
# pseudo-steps interpreted by the test harness directly (e.g., the OS-level
# sleep directive).  The lint skips these names so they are never reported as
# "unregistered tools."
#
# DO NOT add genuine MCP-surface gaps to this list — names like
# ``evaluate_code``, ``read_file``, ``audio_perceptual_quality`` are real
# missing-surface findings the lint MUST report.  Only add names that are
# intentionally pseudo-tools that will never be registered in registrations/.
_DEFAULT_LINT_ALLOWLIST: frozenset[str] = frozenset({
    "sleep",  # OS-sleep directive written as `sleep N` — not an MCP tool.
})


# ---------------------------------------------------------------------------
# Lint entry point (F8 — authoring-time scenario surface lint)
# ---------------------------------------------------------------------------

def run_lint(
    scenario_paths: list[Path],
    repo_root: Path,
    *,
    allow: frozenset[str] | set[str] | None = None,
    registrations_glob: str = "src-tauri/src/ipc/mcp/registrations/*.rs",
) -> tuple[int, list[str]]:
    """Run the scenario-surface existence lint over one or more scenario files.

    For each scenario, checks every asserted MCP tool name (``POST /tools/<x>``
    or ``GET /tools/<x>``) against the registered tool set from ``repo_root``.
    Names in the effective allowlist (``_DEFAULT_LINT_ALLOWLIST | allow``) are
    silently skipped — they are pseudo-steps, not real MCP registrations.

    Returns:
        (exit_code, messages) where:
        - ``exit_code`` is 0 when ALL asserted tools (minus the allowlist) are
          registered, or 1 when at least one unresolved, non-allowlisted tool
          is found.
        - ``messages`` is a list of human-readable strings: ERROR lines for each
          finding plus a single summary line (always appended last).

    Error message format (one per unresolved occurrence):
        ERROR: <scenario_path>:<line_no> asserts unregistered MCP tool
        '<name>' — not found in registrations/ (and not in GOLDEN_TOOL_NAMES)

    This is the testable core — ``main()`` calls it and ``sys.exit``s on the
    returned code.  Tests call it directly (avoids subprocess overhead and the
    project's no-subprocess-in-tests rule).
    """
    effective_allow = _DEFAULT_LINT_ALLOWLIST | (allow or set())

    # Compute registered tools once (shared across all scenarios — same repo_root).
    registered = registered_tools(repo_root, registrations_glob=registrations_glob)

    messages: list[str] = []
    any_finding = False

    for scenario_path in scenario_paths:
        try:
            text = _resolve_scenario_text(scenario_path)
        except FileNotFoundError as exc:
            messages.append(f"ERROR: {exc}")
            any_finding = True
            continue

        # Walk every (line_no, tool_name) occurrence in this scenario.
        for line_no, tool_name in asserted_tools_with_lines(text):
            # Skip pseudo-steps (e.g. sleep) and registered tools.
            if tool_name in effective_allow:
                continue
            if tool_name in registered:
                continue

            # Unresolved, non-allowlisted tool — emit a precise error.
            messages.append(
                f"ERROR: {scenario_path}:{line_no} asserts unregistered MCP tool "
                f"'{tool_name}' — not found in registrations/ (and not in GOLDEN_TOOL_NAMES)"
            )
            any_finding = True

    if any_finding:
        messages.append(
            f"LINT FAIL: {len([m for m in messages if m.startswith('ERROR:')])} "
            f"unresolved tool assertion(s) found across {len(scenario_paths)} scenario(s)."
        )
        return 1, messages
    else:
        messages.append(
            f"LINT OK: all asserted MCP tools registered "
            f"({len(scenario_paths)} scenario(s) checked)."
        )
        return 0, messages


# ---------------------------------------------------------------------------
# MCP-test model-tier routing (harness-hardening-retro-fixes Phase 4)
# ---------------------------------------------------------------------------

# A prior MCP-test verdict is "definitive" (no Sonnet escalation needed) only
# when the run reached a settled, trustworthy conclusion. Everything else —
# uncertain, an unrepaired harness fault, or a post-heal `genuine` failure that
# still needs diagnosis — is NON-definitive and forces Sonnet. We enumerate the
# DEFINITIVE set (allow-list) so an unrecognized/novel verdict label fails safe
# toward Sonnet rather than silently routing a diagnosis cycle to haiku.
_DEFINITIVE_MCP_VERDICTS: frozenset[str] = frozenset({
    "all-passing",   # canonical PASS (MCP_TEST_RESULTS.md result: all-passing)
    "passing",       # synonym some scenarios use
    "pass",
    "all_passing",
})


def route_mcp_test_tier(
    scenario_path: Path,
    prior_verdict: Optional[str] = None,
    yaml_exists: Optional[bool] = None,
) -> str:
    """Return the model tier (``"haiku"`` | ``"sonnet"``) the mcp-test cycle
    should use for ``scenario_path``, derived purely from script-observable
    state — NOT a per-run human/orchestrator override.

    This is the SCRIPT-DERIVED routing signal that re-scopes the mcp-test haiku
    tier (harness-hardening-retro-fixes Phase 4 / SPEC §4, Open Question 3):
    haiku handles only ready-to-run converted-YAML happy paths; scenario
    authoring, first-run ``.md``→YAML conversion, and diagnosis cycles route to
    Sonnet BY DEFAULT. ``repos/algobooth/.claude/skills/mcp-test/SKILL.md``
    consults this helper instead of relying on an orchestrator override.

    Args:
      scenario_path: the RESOLVED scenario reference (a ``corpus/live/*.yaml``
        converted scenario, or a legacy ``.md`` awaiting conversion).
      prior_verdict: the recorded verdict from a prior run (from
        ``verdict.json`` / ``MCP_TEST_RESULTS.md``), or None if this is the
        first run. Matched case-insensitively against ``_DEFINITIVE_MCP_VERDICTS``;
        any value NOT in that allow-list (``uncertain`` / ``harness`` /
        ``genuine`` / unknown) is treated as adverse.
      yaml_exists: optional override for "does a converted YAML counterpart
        exist?". When None (the default), the function performs the one
        permitted existence check (does the path itself, or — for a ``.md``
        path — its ``.yaml`` sibling, exist on disk?). Passing an explicit bool
        keeps the function hermetic (no I/O) for callers that already know.

    Sonnet-forcing conditions (any one → ``"sonnet"``):
      1. The resolved scenario is a legacy ``.md`` with NO converted
         ``*.yaml`` counterpart (first-run conversion needed).
      2. ``prior_verdict`` is non-definitive (``uncertain`` / unrepaired
         ``harness`` / post-heal ``genuine`` / any non-allow-listed label).
      3. No scenario exists at all (scenario-authoring needed): the path is
         absent and no YAML counterpart exists.
    Otherwise — a ready converted YAML with no adverse prior verdict →
    ``"haiku"`` (the happy-path default).

    Pure function: the ONLY I/O is the optional existence check when
    ``yaml_exists is None``; with ``yaml_exists`` supplied it touches no disk.
    Note: generalizes only to the mcp-test routing decision — it does not infer
    any other pipeline tier.
    """
    # --- condition 2: a non-definitive prior verdict always forces Sonnet,
    # regardless of YAML readiness (a diagnosis cycle is never a haiku job). ---
    if prior_verdict is not None:
        if prior_verdict.strip().lower() not in _DEFINITIVE_MCP_VERDICTS:
            return "sonnet"

    # --- resolve "is a ready converted YAML present?" ---
    if yaml_exists is None:
        suffix = scenario_path.suffix.lower()
        if suffix == ".yaml" or suffix == ".yml":
            yaml_present = scenario_path.exists()
        else:
            # A legacy .md (or other) path: a converted counterpart is the
            # sibling .yaml of the same stem.
            yaml_present = scenario_path.with_suffix(".yaml").exists()
    else:
        yaml_present = yaml_exists

    # --- conditions 1 + 3: no ready converted YAML → Sonnet ---
    # This single check covers BOTH "legacy .md, unconverted" (condition 1) and
    # "no scenario at all" (condition 3): in either case there is no ready YAML
    # to run, so the cycle needs Sonnet (conversion or authoring).
    if not yaml_present:
        return "sonnet"

    # --- happy path: ready YAML + no adverse prior verdict ---
    return "haiku"


# ---------------------------------------------------------------------------
# Standalone CLI (informational base mode + --lint mode for F8)
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "surface_resolver.py — Check which MCP tools asserted by scenario(s) "
            "are not registered in the target repo.\n\n"
            "Base mode: informational, always exits 0.\n"
            "Lint mode (--lint): exits 1 if any non-allowlisted unresolved tool found "
            "(F8 / lazy-validation-readiness Phase 5)."
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
            "Lint mode: exit 1 if any scenario asserts an unresolved MCP tool "
            "(not in registrations/ and not in GOLDEN_TOOL_NAMES).  "
            "Prints file:line ERROR messages for each finding.  "
            "The built-in allowlist exempts 'sleep' (an OS sleep directive, "
            "not an MCP tool).  Extend with --allow <name>."
        ),
    )
    parser.add_argument(
        "--allow",
        action="append",
        dest="allow",
        metavar="NAME",
        default=[],
        help=(
            "Additional name to suppress from lint findings (repeatable).  "
            "Only use for pseudo-steps that are intentionally not registered.  "
            "Do NOT use to hide genuine surface gaps."
        ),
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        metavar="SCENARIO",
        help="Path(s) to scenario .md file(s) to check.",
    )
    cli_surface.add_dump_cli_surface_flag(parser)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Base mode (informational, exit 0):
        python surface_resolver.py --repo-root <root> <scenario.md> [...]

    Lint mode (F8 / Phase 5, exits non-zero on findings):
        python surface_resolver.py --lint --repo-root <root> <scenario.md> [...]
        python surface_resolver.py --lint --allow my_pseudo_step --repo-root <root> <scenario.md>

    --allow <name>   Suppress lint findings for <name> (repeatable).  Useful for
                     project-specific pseudo-steps that are not MCP tool
                     registrations but appear as ``POST /tools/<name>`` in
                     scenarios.  The built-in allowlist already covers ``sleep``;
                     only add genuinely-intentional pseudo-steps here.
                     DO NOT use --allow to silence real surface gaps like
                     evaluate_code, read_file, or audio_perceptual_quality.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    _dump = cli_surface.maybe_handle_dump_cli_surface(args, parser, "surface_resolver.py")
    if _dump is not None:
        return _dump

    repo_root = Path(args.repo_root).resolve()

    if args.lint:
        # Lint mode (F8): use run_lint for precise file:line errors + exit code.
        extra_allow = set(args.allow) if args.allow else set()
        scenario_paths = [Path(s) for s in args.scenarios]
        exit_code, messages = run_lint(
            scenario_paths,
            repo_root,
            allow=extra_allow,
        )
        for msg in messages:
            # Route ERROR lines to stderr; summary to stdout.
            if msg.startswith("ERROR:"):
                print(msg, file=sys.stderr)
            else:
                print(msg)
        return exit_code

    # Base (informational) mode — always exits 0.
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

    # Base mode is always informational — exit 0 regardless.
    _ = any_missing  # suppresses "unused variable" warning; not used for exit code.
    return 0


if __name__ == "__main__":
    sys.exit(main())
