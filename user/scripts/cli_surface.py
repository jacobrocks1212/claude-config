"""
cli_surface.py — Shared CLI-surface introspection (state-cli-contract-registry).

Every roster script (see cli_surface_gen.py's ROSTER) hoists its argparse
construction into a module-level ``build_parser() -> argparse.ArgumentParser``
and calls ``add_dump_cli_surface_flag(parser)`` at the end of it. ``main()``
then calls ``maybe_handle_dump_cli_surface(args, parser, "<script>.py")``
immediately after ``parser.parse_args(...)`` so ``--dump-cli-surface`` is
handled before any other side effect.

The dump introspects the LIVE parser's ``_actions`` — it is a projection of
reality, never a parallel description (D1). ``cli_surface_gen.py`` (the
aggregator) shells each roster script with ``--dump-cli-surface`` and merges
the per-script JSON into the committed ``docs/cli/cli-surface.json``.

Schema v1 per-flag fields: name, aliases, action, nargs, required, choices,
metavar, help_head (first sentence only), group (mutually-exclusive group id,
or null), positional (bool), default_kind (none|const|value — never the
actual default VALUE, which may be env-dependent and would break byte
stability).

Public API:
    SCHEMA_VERSION
    add_dump_cli_surface_flag(parser) -> None
    dump_parser_surface(parser) -> dict            # {"flags": [...]}
    maybe_handle_dump_cli_surface(args, parser, script_name) -> Optional[int]
    DidYouMeanArgumentParser                        # Phase 3 (opt-in subclass)
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from typing import Any, Optional

SCHEMA_VERSION = 1

_CONST_ACTION_TYPES = (
    argparse._StoreTrueAction,
    argparse._StoreFalseAction,
    argparse._StoreConstAction,
    argparse._HelpAction,
    argparse._AppendConstAction,
)
if hasattr(argparse, "_VersionAction"):
    _CONST_ACTION_TYPES = _CONST_ACTION_TYPES + (argparse._VersionAction,)
if hasattr(argparse, "BooleanOptionalAction"):
    # store_true/store_false-flavored; still a "const" default in spirit —
    # excluded here since it uses a real default value (usually None/bool)
    # and str.__contains__ below would misclassify it as const. Leave it in
    # the general default_kind branch instead (handled by the default check).
    pass


def _canonical_name_and_aliases(action: argparse.Action) -> tuple[str, list[str]]:
    """Return (name, aliases) for an action.

    Positionals (no option_strings) use ``dest`` as the name with no
    aliases. Optional actions prefer the first long (``--``) option string
    as the canonical name; every other spelling is an alias.
    """
    if not action.option_strings:
        return action.dest, []
    long_opts = [o for o in action.option_strings if o.startswith("--")]
    name = long_opts[0] if long_opts else action.option_strings[0]
    aliases = sorted(o for o in action.option_strings if o != name)
    return name, aliases


def _default_kind(action: argparse.Action) -> str:
    if isinstance(action, _CONST_ACTION_TYPES):
        return "const"
    default = action.default
    if default is None or default is argparse.SUPPRESS:
        return "none"
    return "value"


def _help_head(help_text: Optional[str]) -> Optional[str]:
    if not help_text:
        return None
    text = " ".join(str(help_text).split())
    match = re.search(r"(.*?\.)(\s|$)", text)
    head = match.group(1) if match else text
    if len(head) > 200:
        head = head[:197].rstrip() + "..."
    return head


def _group_id(action: argparse.Action, parser: argparse.ArgumentParser) -> Optional[str]:
    for index, group in enumerate(getattr(parser, "_mutually_exclusive_groups", [])):
        if action in getattr(group, "_group_actions", []):
            return f"group{index}"
    return None


def _describe_action(action: argparse.Action, parser: argparse.ArgumentParser) -> dict[str, Any]:
    name, aliases = _canonical_name_and_aliases(action)
    is_positional = not action.option_strings
    choices = list(action.choices) if action.choices is not None else None
    if choices is not None:
        choices = sorted(str(c) for c in choices)
    nargs = action.nargs
    if nargs is not None and not isinstance(nargs, (int, str)):
        nargs = str(nargs)
    return {
        "name": name,
        "aliases": aliases,
        "action": type(action).__name__,
        "nargs": nargs,
        "required": bool(getattr(action, "required", False)),
        "choices": choices,
        "metavar": action.metavar,
        "help_head": _help_head(action.help),
        "group": _group_id(action, parser),
        "positional": is_positional,
        "default_kind": _default_kind(action),
    }


def add_dump_cli_surface_flag(parser: argparse.ArgumentParser) -> None:
    """Add the self-describing ``--dump-cli-surface`` flag to ``parser``.

    Call this LAST inside every roster script's ``build_parser()`` so the
    flag itself is introspected into the registry (D1: "--dump-cli-surface
    is itself a flag in the registry — self-describing").
    """
    parser.add_argument(
        "--dump-cli-surface",
        action="store_true",
        help=(
            "Introspect this script's live ArgumentParser and print its "
            "CLI-surface projection as JSON (schema_version 1), then exit 0. "
            "Consumed by cli_surface_gen.py — never hand-edit the output."
        ),
    )


def dump_parser_surface(parser: argparse.ArgumentParser) -> dict[str, Any]:
    """Introspect ``parser`` and return the schema-v1 flags projection."""
    flags = [_describe_action(action, parser) for action in parser._actions]
    flags.sort(key=lambda f: (f["positional"], f["name"]))
    return {"flags": flags}


def maybe_handle_dump_cli_surface(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    script_name: str,
) -> Optional[int]:
    """If ``args.dump_cli_surface`` is set, print the JSON dump and return 0.

    Returns None (meaning "not handled — proceed with normal main()") when
    the flag is absent so callers can write::

        _dump = cli_surface.maybe_handle_dump_cli_surface(args, parser, "foo.py")
        if _dump is not None:
            return _dump
    """
    if not getattr(args, "dump_cli_surface", False):
        return None
    payload = {"script": script_name, "schema_version": SCHEMA_VERSION}
    payload.update(dump_parser_surface(parser))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# no-sanctioned-cli-for-queue-state-mutations — op discoverability search.
#
# The orchestrator must never hand-edit queue.json; every mutation has a CLI
# command, but the surface is large. --list-ops / --search-ops let the
# orchestrator find the right command for a natural-language op ("set bug
# severity" -> --set-severity) WITHOUT reading source. It introspects the LIVE
# parser (same projection cli_surface_gen.py consumes) so it is deterministic,
# stdlib-only, and can never drift from the real flags.
# ---------------------------------------------------------------------------

def add_ops_query_flags(parser: argparse.ArgumentParser) -> None:
    """Add ``--list-ops`` / ``--search-ops`` to ``parser``.

    Call alongside ``add_dump_cli_surface_flag`` in each roster twin's
    ``build_parser()`` so the search surface is itself introspected into the
    registry (self-describing, like ``--dump-cli-surface``).
    """
    parser.add_argument(
        "--list-ops",
        action="store_true",
        help=(
            "List every CLI operation this script exposes as JSON "
            "({name, usage, help_head}), then exit 0. The deterministic op "
            "catalog — use it instead of hand-editing queue.json / the run "
            "marker when you are unsure which command performs a mutation."
        ),
    )
    parser.add_argument(
        "--search-ops",
        metavar="QUERY",
        default=None,
        help=(
            "Search this script's CLI operations for a natural-language QUERY "
            "(e.g. \"set bug severity\", \"add dependency\") and print the "
            "ranked matching commands as JSON ({name, usage, help_head, "
            "score}), then exit 0. Deterministic token-overlap ranking over "
            "each flag's name + help."
        ),
    )


def _usage_for_action(action: argparse.Action) -> str:
    """Render a compact one-line usage hint for an optional action:
    ``--flag`` / ``--flag VALUE`` / ``--flag {a,b}``."""
    name, _aliases = _canonical_name_and_aliases(action)
    if isinstance(action, _CONST_ACTION_TYPES):
        return name
    if action.choices:
        return f"{name} {{{','.join(str(c) for c in action.choices)}}}"
    metavar = action.metavar
    if isinstance(metavar, (list, tuple)):
        return f"{name} {' '.join(str(m) for m in metavar)}"
    if metavar:
        return f"{name} {metavar}"
    return f"{name} {action.dest.upper()}"


def ops_index(parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    """Return the searchable op catalog: one ``{name, usage, help_head}`` per
    optional flag (positionals + the ``--help`` action excluded)."""
    ops: list[dict[str, Any]] = []
    for action in parser._actions:
        if not action.option_strings:
            continue  # positional
        if isinstance(action, argparse._HelpAction):
            continue
        name, aliases = _canonical_name_and_aliases(action)
        ops.append({
            "name": name,
            "aliases": aliases,
            "usage": _usage_for_action(action),
            "help_head": _help_head(action.help),
        })
    ops.sort(key=lambda o: o["name"])
    return ops


_OPS_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")


def search_ops(
    parser: argparse.ArgumentParser, query: str
) -> list[dict[str, Any]]:
    """Rank the op catalog against ``query`` by token overlap.

    Deterministic: each lowercased alnum query token scores a hit if it is a
    substring of the flag NAME (weight 2 — a name match is the strongest
    signal) or of its help_head (weight 1). Ops with score 0 are dropped;
    ties break on name (ascending) for byte-stable ordering.
    """
    tokens = _OPS_QUERY_TOKEN_RE.findall((query or "").lower())
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for op in ops_index(parser):
        name_l = op["name"].lower()
        help_l = (op["help_head"] or "").lower()
        score = 0
        for tok in tokens:
            if tok in name_l:
                score += 2
            elif tok in help_l:
                score += 1
        if score > 0:
            scored.append((score, op["name"], {**op, "score": score}))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [op for _s, _n, op in scored]


def maybe_handle_ops_query(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    script_name: str,
) -> Optional[int]:
    """Handle ``--list-ops`` / ``--search-ops`` if set (print JSON, return 0);
    else return None so ``main()`` proceeds. Call immediately after
    ``maybe_handle_dump_cli_surface`` — both are read-only introspection that
    must run before any side effect."""
    if getattr(args, "search_ops", None):
        payload = {
            "script": script_name,
            "query": args.search_ops,
            "matches": search_ops(parser, args.search_ops),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if getattr(args, "list_ops", False):
        payload = {
            "script": script_name,
            "ops": ops_index(parser),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    return None


# ---------------------------------------------------------------------------
# Phase 3 — runtime "did you mean" (D4-A: the two state-script twins only).
# ---------------------------------------------------------------------------

_REGISTRY_POINTER = "registry: docs/cli/cli-surface.json"


class DidYouMeanArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that appends a near-miss suggestion on an unrecognized
    argument error, per SPEC D4-A. The leading ``error:`` line + exit code
    (2) stay byte-identical to stock argparse — the suggestion is a purely
    ADDITIVE epilogue line, so smoke-test baselines that don't exercise this
    error path are unaffected.
    """

    def error(self, message: str) -> None:  # pragma: no cover - exercised via unit test
        if message.startswith("unrecognized arguments:"):
            bad_tokens = message[len("unrecognized arguments:"):].strip().split()
            option_strings = sorted(self._option_string_actions.keys())
            suggestions = []
            for token in bad_tokens:
                if not token.startswith("-"):
                    continue
                close = difflib.get_close_matches(token, option_strings, n=1, cutoff=0.6)
                if close:
                    suggestions.append(f"{token} -> did you mean: {close[0]}?")
            if suggestions:
                self.print_usage(_stderr())
                joined = " ".join(suggestions)
                self.exit(2, f"{self.prog}: error: {message}\n{joined} ({_REGISTRY_POINTER})\n")
        # Fall through to stock behavior for every other error class, and
        # for an unrecognized-arguments error with no close match.
        super().error(message)


def _stderr():
    import sys

    return sys.stderr
