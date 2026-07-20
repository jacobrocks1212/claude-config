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


# A near-miss is a MISTYPED word, so the fallback matches per query-TOKEN
# against the corpus's name-token vocabulary at a typo-grade cutoff — NOT a
# whole-query difflib, which at a loose cutoff surfaces noise over a large
# corpus (a genuine nonsense query must stay a clean MISS — the SPEC's MVB).
# Only significant tokens (len>=4) participate, so short/stop tokens can't drag
# in unrelated records.
_NEAR_MISS_MIN_TOKEN = 4
_NEAR_MISS_CUTOFF = 0.8


def _near_miss_fallback(corpus: list[dict], query: str,
                        top_n: int) -> list[dict]:
    """Per-token typo-grade difflib matches when token-overlap found nothing."""
    tokens = [t for t in _query_tokens(query) if len(t) >= _NEAR_MISS_MIN_TOKEN]
    if not tokens:
        return []
    vocab: dict[str, list[dict]] = {}
    for rec in corpus:
        for name_tok in _TOKEN_RE.findall(rec["name"].lower()):
            vocab.setdefault(name_tok, []).append(rec)
    if not vocab:
        return []
    surfaced: dict[str, dict] = {}
    for tok in tokens:
        for close in difflib.get_close_matches(
                tok, list(vocab), n=3, cutoff=_NEAR_MISS_CUTOFF):
            for rec in vocab[close]:
                surfaced.setdefault(rec["name"], {**rec, "score": 0})
    return list(surfaced.values())[:top_n]


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
# WU-5 — dedup check (toolify ledger + open queues).
# ---------------------------------------------------------------------------

def _load_toolify_promote():
    """Import the hyphenated toolify-promote module (the _load_miner precedent)."""
    if "toolify_promote" in sys.modules:
        return sys.modules["toolify_promote"]
    spec = importlib.util.spec_from_file_location(
        "toolify_promote", str(_SCRIPTS_DIR / "toolify-promote.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["toolify_promote"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _best_match(need: str, texts: list[tuple[str, str]]) -> tuple[str, int]:
    """Return (id, score) of the highest token-overlap over (id, text) pairs."""
    tokens = _query_tokens(need)
    best_id, best_score = "", 0
    for ident, text in texts:
        tl = text.lower()
        score = sum(1 for tok in tokens if tok in tl)
        if score > best_score:
            best_id, best_score = ident, score
    return best_id, best_score


def dedup_check(need: str, ledger_entries: dict,
                queue_entries: list) -> dict:
    """Dedup a runtime tool-gap against the toolify ledger + open queues.

    Matching is the SAME token-overlap idea as the main ranker, applied to each
    ledger/queue entry's recorded text — a dedup hit is a ranking hit against a
    different corpus, not a new algorithm. Ledger wins over queue on a tie.
    """
    ledger_entries = ledger_entries or {}
    queue_entries = queue_entries or []
    ledger_texts = [
        (cid, " ".join(str(e.get(k, "")) for k in
                       ("signature", "feature_id", "name", "title")))
        for cid, e in ledger_entries.items()]
    lid, lscore = _best_match(need, ledger_texts)
    if lscore > 0:
        disposition = None
        try:
            tp = _load_toolify_promote()
            disposition = tp.candidate_disposition(
                {"candidate_id": lid}, ledger_entries)
        except Exception:  # noqa: BLE001 — disposition is a nicety, not required
            disposition = None
        return {"hit": True, "source": "ledger", "candidate_id": lid,
                "disposition": disposition}
    queue_texts = [
        (str(q.get("id", "")),
         f"{q.get('id', '')} {q.get('name', '')}") for q in queue_entries]
    qid, qscore = _best_match(need, queue_texts)
    if qscore > 0:
        return {"hit": True, "source": "queue", "candidate_id": qid,
                "disposition": None}
    return {"hit": False, "source": None, "candidate_id": None,
            "disposition": None}


def _load_ledger_entries(repo_root) -> dict:
    """The toolify promotion ledger's entries dict (fail-open → {})."""
    path = (Path(repo_root) / "docs" / "features"
            / "unified-pipeline-orchestrator" / "toolify-ledger.json")
    try:
        return _load_toolify_promote().load_ledger(path).get("entries", {})
    except Exception:  # noqa: BLE001 — a missing/odd ledger just means no dedup
        return {}


def load_queue_entries(repo_root) -> list[dict]:
    """Open feature + bug queue entries (read-only; fail-open → [])."""
    out: list[dict] = []
    for rel in ("docs/features/queue.json", "docs/bugs/queue.json"):
        path = Path(repo_root) / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entries = data.get("queue") if isinstance(data, dict) else data
        if isinstance(entries, list):
            out += [e for e in entries if isinstance(e, dict)]
    return out


# ---------------------------------------------------------------------------
# WU-6 — host-capability special case + correctness-gated suggestion text.
# ---------------------------------------------------------------------------

def host_capability_match(need: str, corpus: list[dict]) -> dict | None:
    """The best-matching host-capability corpus record for `need`, or None.

    A match short-circuits the miss protocol BEFORE dedup/harden: an absent host
    binary/toolchain is remediated by the host-capability defer model, never a
    build dispatch."""
    caps = [r for r in corpus if r.get("source") == SOURCE_HOST_CAPABILITY]
    if not caps:
        return None
    tokens = _query_tokens(need)
    best, best_score = None, 0
    for rec in caps:
        nl = rec["name"].lower()
        score = sum(2 for tok in tokens if tok in nl)
        if score > best_score:
            best, best_score = rec, score
    return best if best_score > 0 else None


def render_host_capability_suggestion(capability_id: str) -> str:
    """Point at the existing host-capability defer model (no new mechanism)."""
    return (
        f"host-capability gap: the need matches the closed-registry host "
        f"capability `{capability_id}`. This is an absent host binary/toolchain, "
        f"not a harness script to author — do NOT dispatch a build. Route "
        f"through host-capability-declaration-for-gated-features: declare "
        f"`requires_host: {capability_id}` on the feature and let a "
        f"capability-lacking host write DEFERRED_REQUIRES_HOST.md (defer, "
        f"re-open on a capability-bearing host).")


def render_dedup_suggestion(dedup: dict) -> str:
    """Point at the already-proposed item; do NOT dispatch a duplicate."""
    where = "toolify ledger" if dedup["source"] == "ledger" else "open queue"
    disp = f" ({dedup['disposition']})" if dedup.get("disposition") else ""
    return (
        f"dedup hit: this tool-gap is already proposed in the {where} as "
        f"`{dedup['candidate_id']}`{disp}. Point at that existing item — do "
        f"NOT dispatch a second /harden-harness (no double-proposal).")


def render_harden_suggestion(need: str, correctness_load_bearing: bool) -> str:
    """A copy-pasteable observed-friction harden-dispatch command SUGGESTION.

    Pure string rendering — this script NEVER shells out or forks the dispatch
    surface (--emit-dispatch stays orchestrator-only per refuse_if_cycle_active).
    The caller carries the classification forward when copying it."""
    classification = ("correctness_load_bearing=true" if correctness_load_bearing
                      else "convenience=true")
    safe_need = need.replace('"', "'")
    return (
        "no existing tool found. If this operation needs a durable tool, dispatch "
        "an observed-friction harden (orchestrator-only — copy this, do not let "
        "tool-search run it):\n"
        f"  python3 user/scripts/lazy-state.py --emit-dispatch hardening "
        f"--context 'trigger_kind=observed-friction "
        f"need=\"{safe_need}\" {classification}'")


def _handle_miss(need: str, corpus: list[dict], args) -> dict:
    """Classify a MISS: host-capability defer → dedup pointer → harden suggestion."""
    cap = host_capability_match(need, corpus)
    if cap is not None:
        return {"kind": "host-capability", "capability": cap["name"],
                "text": render_host_capability_suggestion(cap["name"])}
    repo_root = getattr(args, "repo_root", ".")
    dedup = dedup_check(need, _load_ledger_entries(repo_root),
                        load_queue_entries(repo_root))
    if dedup["hit"]:
        return {"kind": "dedup", "dedup": dedup,
                "text": render_dedup_suggestion(dedup)}
    correctness = bool(getattr(args, "correctness_load_bearing", False))
    return {"kind": "harden", "need": need,
            "correctness_load_bearing": correctness,
            "text": render_harden_suggestion(need, correctness)}


def _render_miss_human(miss_info: dict) -> str:
    return miss_info.get("text", "") if miss_info else ""


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
