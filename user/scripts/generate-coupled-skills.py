#!/usr/bin/env python3
"""
generate-coupled-skills.py — derive the coupled-pair SKILL.md files from a
canonical skill + a per-pair divergence overlay (coupled-pair-generation).

The five coupled skill pairs (feature→bug and workstation→cloud variants) are
maintained today by hand-duplication audited by regex-presence
(``lazy_parity_audit.py`` C1–C6). This generator makes each derived SKILL.md a
BUILD OUTPUT of:

    derived = for each directive in the pair's overlay, in order:
        · op "canonical" -> apply_tokens(canonical_block[heading])  (restated;
          a canonical edit propagates mechanically, no stored content)
        · op "verbatim"  -> the stored divergent/inserted block, byte-exact
      (a canonical block absent from the overlay is DELETED by omission)

``apply_tokens`` is IMPORTED from ``lazy_parity_audit`` — the substitution
semantics (ordered, literal + regex-escaped) are the one compatibility contract,
never re-implemented here.

Byte-faithfulness is guaranteed BY CONSTRUCTION: ``--extract`` classifies a
derived block as "canonical" ONLY when ``apply_tokens(canonical_block)`` equals
the committed derived block byte-for-byte; every other block (divergence, drift,
or insert) is stored ``verbatim``. So ``--write`` reproduces the committed
derived files exactly, and ``--check`` (the drift gate) byte-diffs a regenerated
file against the committed one.

    FIELD NOTE (2026-07-12 extraction): the derived files are NOT mechanical
    token-copies of the canonical — measured per-block line-diff ratios are
    0.3–0.8 even on the cloud axis (zero token subs). Most blocks therefore
    extract as ``verbatim`` today. The generator is byte-faithful regardless;
    the ``verbatim`` count IS the true divergence surface (the drift the
    C1–C6 regex-presence audit could not see). See the feature's
    NEEDS_INPUT_PROVISIONAL.md.

Modes
-----
    --check   (default) regenerate each derived in memory, byte-diff against the
              committed file; exit 1 on any mismatch (the freshness/drift gate).
    --write   regenerate each derived file from canonical+overlay and write it.
    --extract (re)build each pair's overlay from the committed canonical+derived.
    --report  print per-pair canonical/verbatim/deleted block accounting.

    --pair <derived-dir-name>   restrict to one pair (e.g. lazy-bug-batch).
    --repo-root <path>          repo root (default: inferred from this file).

Exit codes: 0 ok · 1 drift/mismatch (--check) or write/generate failure · 2
malformed overlay/manifest input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --- one substitution implementation (imported, never re-implemented) --------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from lazy_parity_audit import apply_tokens  # noqa: E402  (shared contract)

# Heading model: reuse the audit's exact regex so section boundaries match the
# manifest's headings[] model byte-for-byte (## / ### ATX headings).
_HEAD_RE = re.compile(r"(?m)^#{2,3} .*$")

_PREAMBLE_KEY = "__preamble__"
_OVERLAY_REL_DIR = "user/scripts/coupled-overlays"

# Overlay schema (v1).
_OVERLAY_SCHEMA_VERSION = 1


class GenError(Exception):
    """Raised on a malformed overlay/manifest or an unresolvable directive."""


# ---------------------------------------------------------------------------
# Byte-faithful IO — NO newline translation (the derived files are CRLF).
# ---------------------------------------------------------------------------

def read_text_raw(path: str | Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text_raw(path: str | Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Section splitting (contiguous — concat of blocks == original text exactly)
# ---------------------------------------------------------------------------

def split_blocks(text: str) -> list[tuple[str, str]]:
    """Split into ordered (key, block_text) pairs.

    key is the rstrip-normalized heading line, or ``__preamble__`` for the
    content before the first heading. block_text includes the heading line and
    everything up to (not including) the next heading, so ``"".join(block_text
    for _, block_text in split_blocks(t)) == t`` byte-for-byte.
    """
    matches = list(_HEAD_RE.finditer(text))
    if not matches:
        return [(_PREAMBLE_KEY, text)]
    blocks: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        blocks.append((_PREAMBLE_KEY, text[: matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((m.group(0).rstrip(), text[m.start(): end]))
    return blocks


def _canonical_block_map(canonical_text: str) -> dict[str, str]:
    """heading-key -> block_text for the canonical file (headings are unique)."""
    out: dict[str, str] = {}
    for key, block in split_blocks(canonical_text):
        out[key] = block
    return out


# ---------------------------------------------------------------------------
# Extract — build a pair's overlay from committed canonical + derived
# ---------------------------------------------------------------------------

def build_directives(
    canonical_text: str, derived_text: str, subs: list[dict]
) -> list[dict]:
    """Return the ordered directive list reproducing derived_text exactly.

    A derived block becomes a ``canonical`` directive iff some canonical block,
    token-substituted, equals it byte-for-byte; otherwise a ``verbatim``
    directive storing the block as a ``"\\n"``-split line array.
    """
    canon_blocks = split_blocks(canonical_text)
    # Index canonical blocks by their TOKEN-SUBSTITUTED heading key so a derived
    # block can be matched to the canonical block that would generate it.
    tok_index: dict[str, tuple[str, str]] = {}
    for ckey, cblock in canon_blocks:
        tok_block = apply_tokens(cblock, subs)
        tok_key = ckey if ckey == _PREAMBLE_KEY else apply_tokens(ckey, subs)
        tok_index[tok_key] = (ckey, tok_block)

    directives: list[dict] = []
    for dkey, dblock in split_blocks(derived_text):
        cand = tok_index.get(dkey)
        if cand is not None and cand[1] == dblock:
            directives.append({"op": "canonical", "heading": cand[0]})
        else:
            directives.append(
                {"op": "verbatim", "heading": dkey, "lines": dblock.split("\n")}
            )
    return directives


def build_overlay(pair: dict, repo_root: Path) -> dict:
    canonical_text = read_text_raw(repo_root / pair["canonical"])
    derived_text = read_text_raw(repo_root / pair["derived"])
    subs = pair.get("token_substitutions", [])
    directives = build_directives(canonical_text, derived_text, subs)
    return {
        "schema_version": _OVERLAY_SCHEMA_VERSION,
        "canonical": pair["canonical"],
        "derived": pair["derived"],
        "generator": "generate-coupled-skills.py",
        "note": (
            "GENERATED build input for the coupled-pair generator. Token "
            "substitutions live in lazy-parity-manifest.json (single source). "
            "'canonical' directives restate the canonical block via those subs "
            "(edit the canonical to change them); 'verbatim' directives are "
            "authored divergences/inserts for THIS variant (edit here, then "
            "re-run generate-coupled-skills.py --write). Re-extract with "
            "--extract after a byte-faithful bootstrap."
        ),
        "directives": directives,
    }


# ---------------------------------------------------------------------------
# Overlay schema validation
# ---------------------------------------------------------------------------

def validate_overlay(overlay: dict, canonical_text: str | None = None) -> list[str]:
    """Return a list of schema problems; empty means valid.

    When canonical_text is given, also assert every ``canonical`` directive
    keys a heading that still exists in the canonical (the C4-successor: a
    stale overlay directive keying a deleted canonical heading is loud).
    """
    problems: list[str] = []
    if not isinstance(overlay, dict):
        return ["overlay is not an object"]
    for req in ("canonical", "derived", "directives"):
        if req not in overlay:
            problems.append(f"missing required key {req!r}")
    directives = overlay.get("directives")
    if not isinstance(directives, list):
        problems.append("'directives' must be a list")
        return problems

    canon_keys: set[str] | None = None
    if canonical_text is not None:
        canon_keys = {k for k, _ in split_blocks(canonical_text)}

    for i, d in enumerate(directives):
        if not isinstance(d, dict):
            problems.append(f"directive[{i}] is not an object")
            continue
        op = d.get("op")
        if op == "canonical":
            heading = d.get("heading")
            if not isinstance(heading, str) or not heading:
                problems.append(f"directive[{i}] canonical: missing 'heading'")
            elif canon_keys is not None and heading not in canon_keys:
                problems.append(
                    f"directive[{i}] canonical: heading {heading!r} not found "
                    f"in canonical (stale overlay — re-extract or fix)"
                )
        elif op == "verbatim":
            if not isinstance(d.get("lines"), list):
                problems.append(f"directive[{i}] verbatim: 'lines' must be a list")
            if not all(isinstance(x, str) for x in d.get("lines", [])):
                problems.append(f"directive[{i}] verbatim: 'lines' must be strings")
        else:
            problems.append(f"directive[{i}]: unknown op {op!r}")
    return problems


# ---------------------------------------------------------------------------
# Generate — render a derived file from canonical + overlay
# ---------------------------------------------------------------------------

def generate(canonical_text: str, subs: list[dict], overlay: dict) -> str:
    canon_map = _canonical_block_map(canonical_text)
    parts: list[str] = []
    for i, d in enumerate(overlay.get("directives", [])):
        op = d.get("op")
        if op == "canonical":
            heading = d.get("heading")
            block = canon_map.get(heading)
            if block is None:
                raise GenError(
                    f"directive[{i}]: canonical heading {heading!r} referenced "
                    f"by overlay not found in canonical — stale overlay"
                )
            parts.append(apply_tokens(block, subs))
        elif op == "verbatim":
            parts.append("\n".join(d.get("lines", [])))
        else:
            raise GenError(f"directive[{i}]: unknown op {op!r}")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Pair resolution
# ---------------------------------------------------------------------------

def load_manifest(repo_root: Path) -> dict:
    path = repo_root / "user" / "scripts" / "lazy-parity-manifest.json"
    return json.loads(read_text_raw(path))


def pair_name(pair: dict) -> str:
    return Path(pair["derived"]).parent.name


def overlay_path(repo_root: Path, pair: dict) -> Path:
    ref = pair.get("overlay")
    if ref:
        return repo_root / ref
    return repo_root / _OVERLAY_REL_DIR / f"{pair_name(pair)}.overlay.json"


def select_pairs(manifest: dict, only: str | None) -> list[dict]:
    pairs = manifest.get("pairs", [])
    if only is None:
        return pairs
    picked = [p for p in pairs if pair_name(p) == only]
    if not picked:
        raise GenError(f"no pair with derived dir {only!r} in manifest")
    return picked


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def account(pair: dict, repo_root: Path) -> dict:
    canonical_text = read_text_raw(repo_root / pair["canonical"])
    derived_text = read_text_raw(repo_root / pair["derived"])
    subs = pair.get("token_substitutions", [])
    directives = build_directives(canonical_text, derived_text, subs)
    n_can = sum(1 for d in directives if d["op"] == "canonical")
    n_verb = sum(1 for d in directives if d["op"] == "verbatim")
    der_headings = {d.get("heading") for d in directives}
    canon_keys = [k for k, _ in split_blocks(canonical_text)]
    deleted = [k for k in canon_keys if apply_tokens(k, subs) not in der_headings
               and k != _PREAMBLE_KEY]
    verb_bytes = sum(len("\n".join(d["lines"])) for d in directives
                     if d["op"] == "verbatim")
    return {
        "pair": pair_name(pair),
        "canonical_blocks": n_can,
        "verbatim_blocks": n_verb,
        "deleted_canonical_blocks": len(deleted),
        "verbatim_bytes": verb_bytes,
    }


# ---------------------------------------------------------------------------
# CLI actions
# ---------------------------------------------------------------------------

def cmd_extract(manifest: dict, repo_root: Path, only: str | None) -> int:
    for pair in select_pairs(manifest, only):
        overlay = build_overlay(pair, repo_root)
        out = overlay_path(repo_root, pair)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_text_raw(out, json.dumps(overlay, indent=2, ensure_ascii=False) + "\n")
        acct = account(pair, repo_root)
        print(
            f"extracted {acct['pair']}: {acct['canonical_blocks']} canonical, "
            f"{acct['verbatim_blocks']} verbatim, "
            f"{acct['deleted_canonical_blocks']} deleted -> {out.name}"
        )
    return 0


def cmd_write(manifest: dict, repo_root: Path, only: str | None) -> int:
    rc = 0
    for pair in select_pairs(manifest, only):
        canonical_text = read_text_raw(repo_root / pair["canonical"])
        subs = pair.get("token_substitutions", [])
        overlay = json.loads(read_text_raw(overlay_path(repo_root, pair)))
        problems = validate_overlay(overlay, canonical_text)
        if problems:
            for p in problems:
                print(f"OVERLAY-INVALID [{pair_name(pair)}]: {p}", file=sys.stderr)
            rc = 2
            continue
        try:
            rendered = generate(canonical_text, subs, overlay)
        except GenError as exc:
            print(f"GENERATE-FAIL [{pair_name(pair)}]: {exc}", file=sys.stderr)
            rc = 1
            continue
        write_text_raw(repo_root / pair["derived"], rendered)
        print(f"wrote {pair['derived']}")
    return rc


def cmd_check(manifest: dict, repo_root: Path, only: str | None) -> int:
    findings: list[str] = []
    for pair in select_pairs(manifest, only):
        name = pair_name(pair)
        canonical_text = read_text_raw(repo_root / pair["canonical"])
        subs = pair.get("token_substitutions", [])
        opath = overlay_path(repo_root, pair)
        if not opath.exists():
            findings.append(f"[{name}] overlay missing: {opath} (run --extract)")
            continue
        overlay = json.loads(read_text_raw(opath))
        problems = validate_overlay(overlay, canonical_text)
        if problems:
            findings.extend(f"[{name}] overlay-invalid: {p}" for p in problems)
            continue
        try:
            rendered = generate(canonical_text, subs, overlay)
        except GenError as exc:
            findings.append(f"[{name}] generate-fail: {exc}")
            continue
        committed = read_text_raw(repo_root / pair["derived"])
        if rendered != committed:
            findings.append(
                f"[{name}] DRIFT: regenerated derived != committed "
                f"{pair['derived']} — {_first_divergent_section(committed, rendered)}"
            )
    for f in findings:
        print(f)
    if findings:
        return 1
    print("coupled-pair generation: all pairs byte-identical (fresh)")
    return 0


def _first_divergent_section(committed: str, rendered: str) -> str:
    a = split_blocks(committed)
    b = split_blocks(rendered)
    for i in range(max(len(a), len(b))):
        ka = a[i] if i < len(a) else None
        kb = b[i] if i < len(b) else None
        if ka != kb:
            key = (ka or kb)[0]
            return f"first divergent section: {key!r}"
    return "length/content mismatch"


def cmd_report(manifest: dict, repo_root: Path, only: str | None) -> int:
    rows = [account(p, repo_root) for p in select_pairs(manifest, only)]
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _default_repo_root() -> Path:
    # user/scripts/generate-coupled-skills.py -> repo root is parents[2].
    return _SCRIPT_DIR.parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate coupled-pair SKILL.md files from canonical + overlays."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="(default) byte-diff regenerated vs committed derived (drift gate)")
    mode.add_argument("--write", action="store_true",
                      help="regenerate and write the derived files")
    mode.add_argument("--extract", action="store_true",
                      help="(re)build overlays from the committed canonical+derived")
    mode.add_argument("--report", action="store_true",
                      help="print per-pair block accounting as JSON")
    parser.add_argument("--pair", default=None,
                        help="restrict to one derived-dir name (e.g. lazy-bug-batch)")
    parser.add_argument("--repo-root", default=None,
                        help="repo root (default: inferred from this script's path)")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
    try:
        manifest = load_manifest(repo_root)
        if args.extract:
            return cmd_extract(manifest, repo_root, args.pair)
        if args.write:
            return cmd_write(manifest, repo_root, args.pair)
        if args.report:
            return cmd_report(manifest, repo_root, args.pair)
        return cmd_check(manifest, repo_root, args.pair)
    except GenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
