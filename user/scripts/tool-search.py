#!/usr/bin/env python3
"""tool-search.py — read-only, cross-source tool-availability search.

orchestrator-tool-search: the dispatch-time "search-before-acting" step the
/lazy-batch orchestrator invokes when it hits an abnormal operation needing a
specific tool/CLI and is unsure one already exists. Modeled on Claude Code's own
ToolSearch (query -> matched tools). It AGGREGATES the tool inventories that
already ship in the repo into one searchable corpus and returns deterministic
ranked matches, or an explicit `MISS` verdict as the authoritative LAST stdout
line (the runner-outcome-contract house banner convention).

Corpus (never a new curated index — always the existing registries):
  - docs/cli/cli-surface.json          (roster scripts + their argparse flags)
  - CLAUDE.md + user/scripts/CLAUDE.md (Scripts-table purpose prose)
  - skill catalogs (SKILL.md frontmatter description)
  - host-capability declarations       (lazy_core._HOST_CAPABILITY_REGISTRY ids)
  - per-repo mcp-tool-catalog.md        (no-op where absent, e.g. claude-config)

Ranking REUSES the exact token-overlap scoring shape from
cli_surface.py::search_ops (name-match weight 2, help-text weight 1, score-0
dropped, ties broken on name ascending) with a difflib.get_close_matches
near-miss fallback — a documented reuse, never a new fuzzy engine.

On a MISS this script additionally dedups against the toolify promotion ledger
and the open queues, recognizes an absent-host-capability special case, and
prints a correctness-gated `--emit-dispatch hardening` command SUGGESTION. It
NEVER shells out, mutates state, or forks the dispatch surface — the suggestion
is pure string rendering; classification authority stays with the caller.

Read-only, stdlib-only; a CLI-surface roster member.
"""

from __future__ import annotations

import argparse
import difflib
import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import cli_surface  # noqa: E402  (roster-conformance helpers — reused, never re-implemented)

try:  # sibling harness module — telemetry breadcrumb + host-capability registry
    import lazy_core  # noqa: E402
except Exception:  # noqa: BLE001 — a read-only search must survive its absence
    lazy_core = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Corpus source names (the five aggregated inventories).
# ---------------------------------------------------------------------------
SOURCE_CLI_SURFACE = "cli-surface"
SOURCE_SCRIPTS_TABLE = "scripts-table"
SOURCE_SKILL_CATALOG = "skill-catalog"
SOURCE_HOST_CAPABILITY = "host-capability"
SOURCE_MCP_TOOL_CATALOG = "mcp-tool-catalog"

# Same token grammar as cli_surface.py::_OPS_QUERY_TOKEN_RE (reuse, not re-derive).
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Natural-language stopwords dropped before scoring. cli_surface.py::search_ops
# does not filter these because its queries are terse flag phrases ("set bug
# severity"); tool-search takes a prose need ("regenerate the cli surface
# registry"), so an unfiltered "the"/"a" would spuriously match help prose and
# turn a genuine MISS into a false hit. Length-2+ retained (keeps "id", "cli").
_STOPWORDS = frozenset({
    "the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "with",
    "my", "is", "it", "that", "this", "at", "by", "be", "as", "if", "we",
    "i", "so", "do", "up", "no",
})


def _query_tokens(query: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((query or "").lower())
            if t not in _STOPWORDS]

# A markdown Scripts-table row whose first cell is a backtick-wrapped name:
#   | `name.py` | one-line purpose |
_TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|")


def _norm_record(source: str, name: str, invocation: str,
                 help_head: str | None) -> dict:
    """Normalize one corpus entry to the documented shape."""
    return {
        "source": source,
        "name": name,
        "invocation": invocation,
        "help_head": help_head if help_head else None,
    }


# ---------------------------------------------------------------------------
# WU-1 — corpus loaders (one per source; all pure, read-only).
# ---------------------------------------------------------------------------

def load_cli_surface_corpus(cli_surface_json_path) -> list[dict]:
    """One record per (script, flag) from docs/cli/cli-surface.json.

    The record NAME packs both the script filename and the flag so a search for
    either the script or the flag ranks it (name-match weight 2)."""
    path = Path(cli_surface_json_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[dict] = []
    for script, meta in sorted((data.get("scripts") or {}).items()):
        for flag in (meta.get("flags") or []):
            fname = flag.get("name")
            if not fname:
                continue
            out.append(_norm_record(
                SOURCE_CLI_SURFACE,
                name=f"{script} {fname}",
                invocation=f"python3 user/scripts/{script} {fname}",
                help_head=flag.get("help_head"),
            ))
    return out


def _parse_md_table_rows(text: str) -> list[tuple[str, str]]:
    """Yield (name, purpose) for every backtick-first-cell markdown table row."""
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = _TABLE_ROW_RE.match(line)
        if m:
            rows.append((m.group(1).strip(), m.group(2).strip()))
    return rows


def load_scripts_table_corpus(claude_md_paths) -> list[dict]:
    """Records from the Scripts tables in the given CLAUDE.md files."""
    out: list[dict] = []
    for p in claude_md_paths:
        path = Path(p)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for name, purpose in _parse_md_table_rows(text):
            out.append(_norm_record(
                SOURCE_SCRIPTS_TABLE, name=name, invocation=name,
                help_head=purpose))
    return out


def _read_frontmatter_field(text: str, field: str) -> str | None:
    """Return a single top-level YAML frontmatter scalar (no yaml dep needed)."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    for line in block.splitlines():
        if line.startswith(f"{field}:"):
            return line[len(field) + 1:].strip().strip('"').strip("'")
    return None


def load_skill_catalog_corpus(skills_dirs) -> list[dict]:
    """Records from every SKILL.md's frontmatter (name + description)."""
    out: list[dict] = []
    for d in skills_dirs:
        base = Path(d)
        if not base.is_dir():
            continue
        for skill_md in sorted(base.glob("*/SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            name = _read_frontmatter_field(text, "name") or skill_md.parent.name
            desc = _read_frontmatter_field(text, "description")
            out.append(_norm_record(
                SOURCE_SKILL_CATALOG, name=f"/{name}", invocation=f"/{name}",
                help_head=desc))
    return out


def load_host_capability_corpus(registry_ids) -> list[dict]:
    """Name-only records for each closed-registry host-capability id (no probe)."""
    out: list[dict] = []
    for cap_id in registry_ids:
        out.append(_norm_record(
            SOURCE_HOST_CAPABILITY, name=cap_id,
            invocation=f"requires_host: {cap_id}",
            help_head="host capability (declare requires_host; deferred on a "
                      "host that lacks it)"))
    return out


def load_mcp_tool_catalog_corpus(catalog_path) -> list[dict]:
    """Records from a per-repo mcp-tool-catalog.md; [] when absent (SPEC no-op)."""
    path = Path(catalog_path)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict] = []
    for name, purpose in _parse_md_table_rows(text):
        out.append(_norm_record(
            SOURCE_MCP_TOOL_CATALOG, name=name, invocation=name,
            help_head=purpose))
    return out


def _host_capability_ids() -> list[str]:
    """The closed registry's ids (empty on any lazy_core import failure)."""
    if lazy_core is None:
        return []
    try:
        return sorted(lazy_core._HOST_CAPABILITY_REGISTRY)
    except Exception:  # noqa: BLE001 — corpus is best-effort; a miss is fine
        return []


def build_corpus(repo_root) -> list[dict]:
    """Compose all five sources into one corpus for `repo_root`."""
    root = Path(repo_root)
    corpus: list[dict] = []
    corpus += load_cli_surface_corpus(root / "docs" / "cli" / "cli-surface.json")
    corpus += load_scripts_table_corpus([
        root / "CLAUDE.md", root / "user" / "scripts" / "CLAUDE.md"])
    skills_dirs = [root / "user" / "skills"]
    skills_dirs += sorted((root / "repos").glob("*/.claude/skills")) \
        if (root / "repos").is_dir() else []
    corpus += load_skill_catalog_corpus(skills_dirs)
    corpus += load_host_capability_corpus(_host_capability_ids())
    corpus += load_mcp_tool_catalog_corpus(
        root / ".claude" / "skill-config" / "mcp-tool-catalog.md")
    return corpus


# ---------------------------------------------------------------------------
# WU-2 — deterministic ranking + near-miss fallback + MISS banner.
# ---------------------------------------------------------------------------

def _score_record(record: dict, tokens: list[str]) -> int:
    """Token-overlap score (cli_surface.py::search_ops shape: name 2, help 1)."""
    name_l = record["name"].lower()
    help_l = (record.get("help_head") or "").lower()
    score = 0
    for tok in tokens:
        if tok in name_l:
            score += 2
        elif tok in help_l:
            score += 1
    return score


def rank_corpus(corpus: list[dict], query: str, top_n: int = 5) -> list[dict]:
    """Rank `corpus` against `query`; empty ⇒ MISS.

    Token-overlap first (search_ops shape); if that scores everything 0, a
    difflib.get_close_matches near-miss fallback (cutoff 0.3) fires once."""
    tokens = _query_tokens(query)
    scored: list[tuple[int, str, dict]] = []
    for rec in corpus:
        score = _score_record(rec, tokens)
        if score > 0:
            scored.append((score, rec["name"], {**rec, "score": score}))
    scored.sort(key=lambda t: (-t[0], t[1]))
    ranked = [rec for _s, _n, rec in scored[:top_n]]
    if ranked:
        return ranked
    return _near_miss_fallback(corpus, query or "", top_n)


def _near_miss_fallback(corpus: list[dict], query: str,
                        top_n: int) -> list[dict]:
    """difflib close-name matches when token-overlap found nothing."""
    by_name: dict[str, dict] = {}
    for rec in corpus:
        by_name.setdefault(rec["name"].lower(), rec)
    close = difflib.get_close_matches(
        query.lower(), list(by_name), n=top_n, cutoff=0.3)
    return [{**by_name[name], "score": 0} for name in close]


def search_verdict(ranked: list[dict]) -> str:
    """`hit` when ranked non-empty, else the authoritative `MISS`."""
    return "hit" if ranked else "MISS"


def render_search_result(ranked: list[dict], query: str, top_n: int) -> str:
    """Human-readable table; the LAST line is a ranked summary or `MISS`."""
    if not ranked:
        return (f"tool-search: no ranked match for {query!r}\n"
                "MISS")
    lines = [f"tool-search: {len(ranked)} match(es) for {query!r} "
             f"(top {top_n}):"]
    for rec in ranked:
        head = (rec.get("help_head") or "").strip()
        head = (head[:80] + "…") if len(head) > 81 else head
        lines.append(f"  [{rec['source']}] {rec['name']}  (score "
                     f"{rec['score']})")
        lines.append(f"      -> {rec['invocation']}")
        if head:
            lines.append(f"      {head}")
    top = ranked[0]
    lines.append(f"top match: {top['name']} (score {top['score']}) -> "
                 f"{top['invocation']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Miss-handling placeholders — fully implemented in WU-5 (dedup) + WU-6
# (host-capability special case + correctness-gated suggestion text).
# ---------------------------------------------------------------------------

def _handle_miss(need: str, corpus: list[dict], args) -> dict | None:
    return None


def _render_miss_human(miss_info: dict) -> str:
    return ""


# ---------------------------------------------------------------------------
# WU-3 — CLI scaffold, roster conformance, telemetry breadcrumb.
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """The roster-conformant parser (DidYouMeanArgumentParser + dump flag)."""
    parser = cli_surface.DidYouMeanArgumentParser(
        prog="tool-search.py",
        description="Search the repo's existing tool inventories for a "
                    "natural-language need; ranked matches or an explicit MISS.")
    parser.add_argument(
        "--tool-search", metavar="QUERY", default=None,
        help="The natural-language need to search for (e.g. \"regenerate the "
             "cli surface registry\"). Prints ranked matches or MISS as the "
             "authoritative last line.")
    parser.add_argument(
        "--json", action="store_true",
        help="Emit the result as a JSON object {query, verdict, top_score, "
             "matches[], miss} instead of the human table.")
    parser.add_argument(
        "--top", type=int, default=5, metavar="N",
        help="Cap the number of ranked matches returned (default 5).")
    parser.add_argument(
        "--repo-root", default=".",
        help="Repo root whose inventories form the corpus (default: cwd).")
    parser.add_argument(
        "--correctness-load-bearing", action="store_true",
        help="Mark the needed operation correctness/gate-load-bearing so a MISS "
             "harden-suggestion carries correctness_load_bearing=true (advisory "
             "text only — this script never dispatches).")
    cli_surface.add_dump_cli_surface_flag(parser)
    return parser


def _emit_telemetry(query: str, verdict: str, top_score) -> None:
    """Best-effort tool-search-invocation breadcrumb (fail-open, never raises).

    Reuses lazy_core.append_telemetry_event — the same marker-gated, fail-open
    writer refuse_if_cycle_active uses for its containment-refusal events. The
    Phase-4 KPI selector correlates against this event kind."""
    if lazy_core is None:
        return
    try:
        lazy_core.append_telemetry_event(
            "tool-search-invocation",
            data={"query": query, "verdict": verdict, "top_score": top_score})
    except Exception:  # noqa: BLE001 — telemetry can never break the search
        pass


def _render_json(need: str, ranked: list[dict], miss_info) -> str:
    return json.dumps({
        "query": need,
        "verdict": "hit" if ranked else "miss",
        "top_score": ranked[0]["score"] if ranked else None,
        "matches": ranked,
        "miss": miss_info,
    }, indent=2, sort_keys=True)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handled = cli_surface.maybe_handle_dump_cli_surface(
        args, parser, "tool-search.py")
    if handled is not None:
        return handled  # read-only introspection — NOT a real invocation
    if not args.tool_search:
        parser.error("--tool-search QUERY is required")
    need = args.tool_search
    corpus = build_corpus(args.repo_root)
    ranked = rank_corpus(corpus, need, top_n=args.top)
    miss_info = None if ranked else _handle_miss(need, corpus, args)
    _emit_telemetry(need, "hit" if ranked else "miss",
                    ranked[0]["score"] if ranked else None)
    if args.json:
        print(_render_json(need, ranked, miss_info))
    elif ranked:
        print(render_search_result(ranked, need, args.top))
    else:
        # miss suggestion prints BEFORE the authoritative MISS banner line.
        if miss_info:
            print(_render_miss_human(miss_info))
        print(render_search_result([], need, args.top))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
