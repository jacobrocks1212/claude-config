#!/usr/bin/env python3
"""
toolify-miner.py — offline session-log toolification miner.

unified-pipeline-orchestrator, Phase 4. Stdlib-only. READ-ONLY over logs.

Parses Claude Code session transcripts (``~/.claude/projects/**/*.jsonl`` plus
``**/subagents/agent-*.jsonl``), extracts orchestrator-turn tool-call
sequences, normalizes each into a *signature* (tool name + argument SHAPE, with
all values elided), and ranks recurring sequences by

    score = occurrences x est_tokens_per_occurrence

emitting a ranked markdown table and/or JSON. It applies the **deterministic-
only bar**: a candidate surfaces *above the bar* iff it is

  (a) deterministic — the sequence contains NO judgment-marker step
      (AskUserQuestion, verdict/recovery-dispatch, ``--verify-ledger``); its
      branches are computable from observable state, not agent reasoning,
  (b) repeated — it occurs across >= MIN_RUNS distinct session runs, and
  (c) token-heavy — its score exceeds TOKEN_HEAVY_THRESHOLD.

Judgment sequences are still surfaced (so the operator sees them) but rank
*below* the bar by construction.

> READ-ONLY-OVER-LOGS INVARIANT. This script opens every log file in read mode
> only and NEVER writes, renames, or deletes anything under the logs dir. The
> test suite hashes the fixture log dir before/after every run and asserts it is
> byte-identical. See `docs/features/unified-pipeline-orchestrator/toolify-bar.md`.

Promotion is DELIBERATE: the miner *proposes* candidates. It never auto-writes
code. See the promotion checklist in toolify-bar.md.

Usage:
    python3 toolify-miner.py [--logs DIR] [--markdown | --json]
                             [--min-runs N] [--top N]

Defaults: --logs ~/.claude/projects ; --markdown (both emitted if neither flag).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Tunable constants (the deterministic-only bar) — documented in toolify-bar.md.
# ---------------------------------------------------------------------------

#: A candidate must occur across at least this many DISTINCT session runs to
#: clear the "repeated" predicate.
MIN_RUNS = 2

#: Score (occurrences x est_tokens_per_occurrence) must exceed this to clear the
#: "token-heavy" predicate. Tuned so a single trivial Read/Bash call falls below
#: while a multi-call dance repeated across runs clears it. A lone call is
#: ~EST_TOKENS_PER_CALL tokens x a couple of occurrences; the threshold sits
#: above that so single short calls do not surface above the bar.
TOKEN_HEAVY_THRESHOLD = 600

#: Rough token cost attributed to one tool call (call + its result echo). Used
#: only for relative ranking — the absolute number is a heuristic, not a metering.
EST_TOKENS_PER_CALL = 120

#: Sliding-window bounds for candidate sequences. A toolify-worthy dance is a
#: short recurring run of calls; windows shorter than MIN_NGRAM or longer than
#: MAX_NGRAM are not considered. Tuned to the three retro-named dances (2-6
#: calls) — see the granularity rationale on ``_windows``.
MIN_NGRAM = 1
MAX_NGRAM = 6

#: Tool names / argument-content markers that make a sequence JUDGMENT-bearing
#: (and therefore NOT deterministic — explicitly out of scope per the SPEC).
_JUDGMENT_TOOLS = frozenset({"AskUserQuestion"})

#: Substrings in a Bash command (or any string arg value) that mark a judgment /
#: verdict / recovery-dispatch / ledger-verification step. These keep a sequence
#: below the bar even when its tool-shape looks mechanical.
_JUDGMENT_VALUE_MARKERS = (
    "--verify-ledger",
    "verdict",
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    """One normalized tool invocation: tool name + the argument SHAPE.

    ``arg_shape`` is the sorted tuple of top-level argument keys (values elided).
    ``judgment`` flags a call that requires agent judgment (AskUserQuestion, a
    verdict/recovery/ledger-verification command).
    """

    tool: str
    arg_shape: tuple
    judgment: bool = False


@dataclass
class Candidate:
    signature: str
    occurrences: int
    run_count: int
    est_tokens_per_occurrence: int
    score: int
    deterministic: bool
    above_bar: bool
    n_calls: int = 0
    sample_tools: tuple = field(default_factory=tuple)
    #: Stable content-hash identity (toolify-auto-promotion D2-A): the first 12
    #: hex chars of SHA-256 of the signature string. Deterministic across mining
    #: passes because ``signature()`` is deterministic; the promotion ledger
    #: (`toolify-promote.py`) keys on it. Additive — no prior field changed.
    candidate_id: str = ""


def candidate_id(sig: str) -> str:
    """The ONE canonical candidate-id derivation (toolify-auto-promotion D2-A).

    ``sha256(signature)[:12]`` — copy-pasteable, stable across passes, and
    derivable offline from any saved report. Both the miner's renderers and
    ``toolify-promote.py`` call this; nothing re-implements the hash.
    """
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _is_judgment_call(tool: str, inp) -> bool:
    if tool in _JUDGMENT_TOOLS:
        return True
    if isinstance(inp, dict):
        for v in inp.values():
            if isinstance(v, str):
                low = v.lower()
                for marker in _JUDGMENT_VALUE_MARKERS:
                    if marker in low:
                        return True
    return False


def _normalize_call(tool: str, inp) -> ToolCall:
    """Elide values; keep the argument SHAPE (sorted top-level key tuple)."""
    if isinstance(inp, dict):
        shape = tuple(sorted(inp.keys()))
    else:
        shape = ()
    return ToolCall(tool=tool, arg_shape=shape, judgment=_is_judgment_call(tool, inp))


def signature(calls) -> str:
    """Deterministic signature string for a sequence of calls.

    Accepts either a list of ``ToolCall`` or a list of ``(tool_name, input)``
    tuples (the test-fixture form). Values are fully elided — only tool names
    and argument SHAPES contribute, so value-variant occurrences of the same
    dance collapse to one signature, while shape-distinct sequences stay apart.
    """
    norm = []
    for c in calls:
        if isinstance(c, ToolCall):
            norm.append(c)
        else:
            tool, inp = c
            norm.append(_normalize_call(tool, inp))
    parts = []
    for c in norm:
        parts.append(f"{c.tool}({','.join(c.arg_shape)})")
    return " -> ".join(parts)


# ---------------------------------------------------------------------------
# Parsing — READ-ONLY over the logs dir.
# ---------------------------------------------------------------------------

def _iter_log_files(logs_dir: Path) -> Iterable[Path]:
    """Yield every transcript file under logs_dir (top-level + subagents)."""
    if not logs_dir.exists():
        return
    for p in sorted(logs_dir.rglob("*.jsonl")):
        if p.is_file():
            yield p


def _tool_calls_in_file(path: Path):
    """Yield normalized ToolCall objects, in order, from one transcript file.

    Only assistant-turn ``tool_use`` blocks contribute. Malformed lines are
    skipped. The file is opened in READ mode only.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "assistant":
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        yield _normalize_call(block.get("name", "?"), block.get("input"))
    except OSError:
        return


def _windows(calls, max_ngram=None):
    """Yield every contiguous tool-call WINDOW (n-gram) of length
    MIN_NGRAM..max_ngram from one file's ordered call stream.

    GRANULARITY TUNING (closes the Open Question "Miner signature
    granularity"): the chosen coarseness is a sliding contiguous n-gram over
    (tool_name, sorted-argument-key-tuple) calls — values fully elided. This is
    coarse enough that "the same dance" clusters across runs even when argument
    VALUES differ (a curl to :3333 vs :4444 share one window signature), yet
    fine enough that two shape-distinct sequences never merge (a different tool
    or a different argument key-set yields a different window). Windows are
    bounded by MAX_NGRAM so a long transcript cannot blow up the candidate set;
    the recurring multi-call dances the bar targets are short (2-6 calls).
    """
    if max_ngram is None:
        max_ngram = MAX_NGRAM
    n = len(calls)
    for size in range(MIN_NGRAM, max_ngram + 1):
        if size > n:
            break
        for start in range(0, n - size + 1):
            yield calls[start:start + size]


def extract_sequences(logs_dir) -> list:
    """Return one ordered ToolCall list per transcript file under logs_dir.

    Used by callers that want the raw per-run call stream (the miner itself
    enumerates n-gram windows over these via ``_windows``). Files with no tool
    calls are omitted.
    """
    logs_dir = Path(logs_dir)
    out: list = []
    for f in _iter_log_files(logs_dir):
        calls = list(_tool_calls_in_file(f))
        if calls:
            out.append(calls)
    return out


# ---------------------------------------------------------------------------
# Mining / ranking / the bar
# ---------------------------------------------------------------------------

def _est_tokens_per_occurrence(calls) -> int:
    return max(1, len(calls)) * EST_TOKENS_PER_CALL


def mine(logs_dir, min_runs=None) -> list:
    """Mine candidates from logs_dir, ranked descending by score.

    Groups segmented sequences by signature; counts total occurrences and the
    number of DISTINCT runs (files) each appears in; applies the deterministic-
    only bar; returns ranked ``Candidate`` objects.
    """
    logs_dir = Path(logs_dir)
    repeated_threshold = MIN_RUNS if min_runs is None else min_runs

    # Per-signature accumulation, tracking which run-file each occurrence came from.
    agg: dict = {}
    for f in _iter_log_files(logs_dir):
        calls = list(_tool_calls_in_file(f))
        for seq in _windows(calls):
            if not seq:
                continue
            sig = signature(seq)
            rec = agg.get(sig)
            if rec is None:
                rec = {
                    "occurrences": 0,
                    "runs": set(),
                    "deterministic": all(not c.judgment for c in seq),
                    "est": _est_tokens_per_occurrence(seq),
                    "n_calls": len(seq),
                    "sample_tools": tuple(c.tool for c in seq),
                }
                agg[sig] = rec
            rec["occurrences"] += 1
            rec["runs"].add(str(f))

    candidates = []
    for sig, rec in agg.items():
        occ = rec["occurrences"]
        run_count = len(rec["runs"])
        est = rec["est"]
        score = occ * est
        deterministic = rec["deterministic"]
        above_bar = (
            deterministic
            and run_count >= repeated_threshold
            and score > TOKEN_HEAVY_THRESHOLD
        )
        candidates.append(
            Candidate(
                signature=sig,
                occurrences=occ,
                run_count=run_count,
                est_tokens_per_occurrence=est,
                score=score,
                deterministic=deterministic,
                above_bar=above_bar,
                n_calls=rec["n_calls"],
                sample_tools=rec["sample_tools"],
                candidate_id=candidate_id(sig),
            )
        )

    # Rank strictly by score descending (the SPEC's
    # `occurrences x est_tokens_per_occurrence`), signature as a stable
    # tie-break. `above_bar` is a CLASSIFICATION column, not a sort key — a
    # frequent judgment sequence may out-score a deterministic dance, and the
    # table shows that honestly with the dance flagged above-bar and the
    # judgment sequence flagged below.
    candidates.sort(key=lambda c: (-c.score, c.signature))
    return candidates


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(candidates) -> str:
    lines = [
        "| rank | candidate_id | above_bar | signature | occurrences | runs | est_tokens/occ | score | deterministic |",
        "|------|--------------|-----------|-----------|-------------|------|----------------|-------|---------------|",
    ]
    for i, c in enumerate(candidates, 1):
        sig = c.signature.replace("|", "\\|")
        cid = c.candidate_id or candidate_id(c.signature)
        lines.append(
            f"| {i} | `{cid}` | {'YES' if c.above_bar else 'no'} | `{sig}` | "
            f"{c.occurrences} | {c.run_count} | {c.est_tokens_per_occurrence} | "
            f"{c.score} | {c.deterministic} |"
        )
    return "\n".join(lines)


def render_json(candidates) -> str:
    rows = []
    for c in candidates:
        rows.append(
            {
                "candidate_id": c.candidate_id or candidate_id(c.signature),
                "signature": c.signature,
                "occurrences": c.occurrences,
                "run_count": c.run_count,
                "est_tokens_per_occurrence": c.est_tokens_per_occurrence,
                "score": c.score,
                "deterministic": c.deterministic,
                "above_bar": c.above_bar,
                "n_calls": c.n_calls,
                "sample_tools": list(c.sample_tools),
            }
        )
    return json.dumps(rows, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline toolification miner (read-only over session logs)."
    )
    default_logs = Path(os.path.expanduser("~/.claude/projects"))
    parser.add_argument(
        "--logs", type=Path, default=default_logs,
        help="logs directory (default: ~/.claude/projects)",
    )
    parser.add_argument("--markdown", action="store_true", help="emit a markdown table")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--min-runs", type=int, default=None,
        help=f"override the repeated-predicate run threshold (default {MIN_RUNS})",
    )
    parser.add_argument("--top", type=int, default=None, help="limit to top N candidates")
    args = parser.parse_args(argv)

    candidates = mine(args.logs, min_runs=args.min_runs)
    if args.top is not None:
        candidates = candidates[: args.top]

    # Default: markdown if neither flag given. Both if both given.
    emit_md = args.markdown or not args.json
    emit_json = args.json

    if emit_md:
        print(render_markdown(candidates))
    if emit_json:
        if emit_md:
            print()
        print(render_json(candidates))
    return 0


if __name__ == "__main__":
    sys.exit(main())
