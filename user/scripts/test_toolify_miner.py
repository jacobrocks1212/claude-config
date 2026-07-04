#!/usr/bin/env python3
"""
test_toolify_miner.py — Tests for toolify-miner.py (unified-pipeline-orchestrator Phase 4).

The miner is an offline session-log analyzer that ranks recurring deterministic
tool-call sequences as toolification candidates. These tests lock in:

  WU-1: JSONL parsing, signature normalization (values elided, shape kept),
        occurrence ranking by `occurrences x est_tokens_per_occurrence`,
        markdown + JSON output, and the READ-ONLY-OVER-LOGS invariant
        (the fixture log dir is byte-identical before and after a run).
  WU-2: the deterministic-only bar (above-bar iff deterministic AND repeated
        AND token-heavy); judgment sequences (AskUserQuestion / verdict /
        recovery-dispatch / --verify-ledger) classify below-bar even if
        frequent; signature-granularity tuning (value-variant occurrences
        merge; shape-distinct sequences do NOT merge).

Run with: python3 user/scripts/test_toolify_miner.py   (exit 0 on pass)
Also pytest-discoverable (every `test_*` function is a standalone test).
No third-party dependencies — stdlib only.

RED STATE (today): import toolify_miner fails — the module doesn't exist yet.
GREEN STATE: all assertions pass.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Import the hyphenated module under a clean name.
# ---------------------------------------------------------------------------
_IMPORT_ERROR = None
toolify_miner = None
try:
    _spec = importlib.util.spec_from_file_location(
        "toolify_miner", str(_SCRIPTS_DIR / "toolify-miner.py")
    )
    toolify_miner = importlib.util.module_from_spec(_spec)
    # Register before exec so dataclass type-resolution can find the module.
    sys.modules["toolify_miner"] = toolify_miner
    _spec.loader.exec_module(toolify_miner)  # type: ignore[union-attr]
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _ModuleMissing(Exception):
    pass


def _guard():
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"toolify-miner.py not importable: {_IMPORT_ERROR}")


# ---------------------------------------------------------------------------
# Fixture builders — synthesize realistic transcript .jsonl files.
# ---------------------------------------------------------------------------

def _assistant_turn(tool_calls, *, sidechain=False):
    """One assistant transcript line carrying the given tool_use blocks.

    tool_calls: list of (tool_name, input_dict).
    """
    content = []
    for name, inp in tool_calls:
        content.append(
            {"type": "tool_use", "id": "tu_x", "name": name, "input": inp}
        )
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "uuid": "u",
        "message": {"role": "assistant", "content": content},
    }


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _runtime_ensure_dance(host="3333"):
    """A deterministic 'ensure runtime' dance: health probe -> restart -> curl loop.

    Two occurrences differ only in argument VALUES (port literal, sleep count),
    same argument SHAPE -> must normalize to ONE signature.
    """
    return [
        ("Bash", {"command": f"curl -s localhost:{host}/health", "description": "probe health"}),
        ("Bash", {"command": "npm run dev:restart", "description": "restart dev"}),
        ("Bash", {"command": f"curl --retry 5 localhost:{host}/health", "description": "wait for 200"}),
    ]


def _judgment_sequence():
    """A sequence containing a judgment marker (AskUserQuestion) — below-bar."""
    return [
        ("Read", {"file_path": "/x/verdict.json"}),
        ("AskUserQuestion", {"question": "salvageable?"}),
        ("Bash", {"command": "git commit -m x", "description": "commit"}),
    ]


def _verify_ledger_sequence():
    """A --verify-ledger-shaped sequence — explicitly out of scope, below-bar."""
    return [
        ("Bash", {"command": "python lazy-state.py --verify-ledger", "description": "verify ledger"}),
    ]


def _build_two_run_log_dir(td: Path):
    """A fixture log dir with TWO 'runs' (two .jsonl session files).

    Each run contains the runtime-ensure dance (value-variant), plus a judgment
    sequence. The dance is repeated across >=2 runs -> eligible. The judgment
    sequence is also repeated but must rank below the bar.
    """
    logs = td / "projects"
    proj = logs / "C--proj-A"
    # Run 1
    _write_jsonl(
        proj / "session-1.jsonl",
        [
            _assistant_turn([c]) for c in _runtime_ensure_dance("3333")
        ]
        + [_assistant_turn([c]) for c in _judgment_sequence()],
    )
    # Run 2 — value-variant dance (different port/retry literals), same shape
    _write_jsonl(
        proj / "session-2.jsonl",
        [
            _assistant_turn([c]) for c in _runtime_ensure_dance("4444")
        ]
        + [_assistant_turn([c]) for c in _judgment_sequence()],
    )
    return logs


def _dir_hash(root: Path) -> str:
    """A stable hash of every file's relative path + bytes under root."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).replace("\\", "/").encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


# ===========================================================================
# WU-1 — parser / signature normalization / ranking / output / read-only
# ===========================================================================

def test_module_importable():
    _guard()
    assert toolify_miner is not None


def test_extracts_tool_calls_from_assistant_turns():
    """Tool-use blocks on assistant turns are extracted; non-assistant /
    non-tool lines are ignored."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        seqs = toolify_miner.extract_sequences(logs)
        # At least the dance + judgment, across 2 runs.
        assert seqs, "expected extracted sequences"
        # All extracted entries are tool-name strings we put in.
        names = {tc.tool for run in seqs for tc in run}
        assert "Bash" in names and "Read" in names


def test_signature_elides_values_keeps_shape():
    """Two occurrences of the same dance with different argument VALUES but the
    same argument SHAPE normalize to ONE signature (positive merge case)."""
    _guard()
    sig_a = toolify_miner.signature(_runtime_ensure_dance("3333"))
    sig_b = toolify_miner.signature(_runtime_ensure_dance("4444"))
    assert sig_a == sig_b, "value-variant dances must share one signature"


def test_signature_distinguishes_shape_distinct_sequences():
    """Two genuinely distinct sequences (different tools / arg shapes) do NOT
    merge (negative over-merge case — granularity tuning)."""
    _guard()
    sig_dance = toolify_miner.signature(_runtime_ensure_dance("3333"))
    sig_judgment = toolify_miner.signature(_judgment_sequence())
    assert sig_dance != sig_judgment, "shape-distinct sequences must not merge"


def test_signature_value_in_string_does_not_affect_shape():
    """Same tool + same arg keys but different string VALUES -> same signature."""
    _guard()
    a = [("Bash", {"command": "curl localhost:3333", "description": "x"})]
    b = [("Bash", {"command": "curl localhost:9999/other --retry 10", "description": "y"})]
    assert toolify_miner.signature(a) == toolify_miner.signature(b)


def test_signature_different_arg_keys_distinct():
    """Same tool, different argument KEY SET -> distinct signature."""
    _guard()
    a = [("Read", {"file_path": "/x"})]
    b = [("Read", {"file_path": "/x", "limit": 5, "offset": 0})]
    assert toolify_miner.signature(a) != toolify_miner.signature(b)


def test_ranking_score_is_occurrences_times_est_tokens():
    """A candidate's score == occurrences * est_tokens_per_occurrence."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        assert cands, "expected candidates"
        for c in cands:
            assert c.score == c.occurrences * c.est_tokens_per_occurrence, c


def test_ranking_orders_descending_by_score():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        scores = [c.score for c in cands]
        assert scores == sorted(scores, reverse=True), scores


def test_emits_markdown_table():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        md = toolify_miner.render_markdown(cands)
        assert "|" in md and "score" in md.lower()
        # A markdown table has a header separator row.
        assert "---" in md


def test_emits_json():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        out = toolify_miner.render_json(cands)
        parsed = json.loads(out)
        assert isinstance(parsed, list) and parsed
        row = parsed[0]
        for key in ("signature", "occurrences", "est_tokens_per_occurrence",
                    "score", "deterministic", "above_bar"):
            assert key in row, f"missing schema field {key}"


def test_read_only_over_logs_dir_unchanged():
    """THE LOAD-BEARING INVARIANT: a full mine() run never mutates the log dir.
    Hash the fixture dir before and after; must be byte-identical."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        before = _dir_hash(logs)
        toolify_miner.mine(logs)
        toolify_miner.render_markdown(toolify_miner.mine(logs))
        toolify_miner.render_json(toolify_miner.mine(logs))
        after = _dir_hash(logs)
        assert before == after, "miner MUST NOT mutate the logs dir"


def test_parses_subagent_transcripts():
    """subagents/agent-*.jsonl files are also parsed."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "projects"
        sub = logs / "C--proj" / "subagents"
        _write_jsonl(
            sub / "agent-abc.jsonl",
            [_assistant_turn([c], sidechain=True) for c in _runtime_ensure_dance()],
        )
        seqs = toolify_miner.extract_sequences(logs)
        assert seqs, "subagent transcripts must be parsed"


def test_malformed_lines_skipped_gracefully():
    """A corrupt JSONL line does not crash the miner."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "projects"
        p = logs / "C--proj" / "s.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            fh.write("{not valid json\n")
            fh.write(json.dumps(_assistant_turn([("Bash", {"command": "x", "description": "y"})])) + "\n")
        seqs = toolify_miner.extract_sequences(logs)  # must not raise
        assert isinstance(seqs, list)


# ===========================================================================
# WU-2 — the deterministic-only bar + granularity tuning
# ===========================================================================

def test_deterministic_repeated_token_heavy_is_above_bar():
    """The runtime-ensure dance (deterministic, repeated >=2 runs, token-heavy)
    classifies above-bar."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        dance_sig = toolify_miner.signature(_runtime_ensure_dance("3333"))
        dance = next((c for c in cands if c.signature == dance_sig), None)
        assert dance is not None, "dance not found among candidates"
        assert dance.above_bar is True, dance
        assert dance.deterministic is True, dance


def test_judgment_sequence_is_below_bar_even_if_frequent():
    """A sequence containing AskUserQuestion (judgment) is below-bar even when
    it occurs across >=2 runs."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        judg_sig = toolify_miner.signature(_judgment_sequence())
        judg = next((c for c in cands if c.signature == judg_sig), None)
        assert judg is not None, "judgment sequence should still be surfaced (ranked below)"
        assert judg.deterministic is False, judg
        assert judg.above_bar is False, judg


def test_verify_ledger_sequence_below_bar():
    """A --verify-ledger-shaped sequence is below-bar (explicitly out of scope)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "projects"
        proj = logs / "C--proj"
        for i in (1, 2):
            _write_jsonl(
                proj / f"s{i}.jsonl",
                [_assistant_turn([c]) for c in _verify_ledger_sequence()],
            )
        cands = toolify_miner.mine(logs)
        sig = toolify_miner.signature(_verify_ledger_sequence())
        c = next((x for x in cands if x.signature == sig), None)
        assert c is not None
        assert c.deterministic is False, c
        assert c.above_bar is False, c


def test_single_run_dance_not_above_bar():
    """A dance that occurs in only ONE run fails the 'repeated' predicate and is
    NOT above-bar even though it is deterministic + token-heavy."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "projects"
        # The dance repeats within a single run but never across runs.
        _write_jsonl(
            logs / "C--proj" / "s1.jsonl",
            [_assistant_turn([c]) for c in _runtime_ensure_dance()] * 3,
        )
        cands = toolify_miner.mine(logs)
        sig = toolify_miner.signature(_runtime_ensure_dance())
        c = next((x for x in cands if x.signature == sig), None)
        assert c is not None
        assert c.run_count == 1, c
        assert c.above_bar is False, "single-run dance must fail the repeated predicate"


def test_below_token_threshold_not_above_bar():
    """A short, deterministic, repeated single-call sequence whose score is below
    the documented token-heavy threshold is NOT above-bar."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "projects"
        proj = logs / "C--proj"
        tiny = [("Read", {"file_path": "/x"})]
        for i in (1, 2):
            _write_jsonl(proj / f"s{i}.jsonl", [_assistant_turn([c]) for c in tiny])
        cands = toolify_miner.mine(logs)
        sig = toolify_miner.signature(tiny)
        c = next((x for x in cands if x.signature == sig), None)
        assert c is not None
        assert c.score < toolify_miner.TOKEN_HEAVY_THRESHOLD, c
        assert c.above_bar is False, c


def test_cli_smoke_runs_and_writes_nothing(tmp_path=None):
    """End-to-end CLI: `toolify-miner.py --logs <dir> --json` runs, prints JSON,
    and leaves the logs dir byte-unchanged."""
    _guard()
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        before = _dir_hash(logs)
        res = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "toolify-miner.py"),
             "--logs", str(logs), "--json"],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        json.loads(res.stdout)  # valid JSON on stdout
        after = _dir_hash(logs)
        assert before == after, "CLI run mutated the logs dir"


# ===========================================================================
# toolify-auto-promotion Phase 1 — candidate_id (content-hash identity, D2-A)
# ===========================================================================

def test_candidate_id_stable_across_passes():
    """Mining the same fixture corpus twice yields IDENTICAL candidate_id per
    signature — the ledger key survives re-mining (D2-A)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        first = {c.signature: c.candidate_id for c in toolify_miner.mine(logs)}
        second = {c.signature: c.candidate_id for c in toolify_miner.mine(logs)}
        assert first, "expected candidates"
        assert first == second, "candidate_id must be stable across passes"


def test_candidate_id_unique_and_derivable():
    """candidate_id is unique per signature on the fixture corpus AND derivable
    offline: sha256(signature)[:12] — so an operator can recompute it from any
    saved report."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        ids = [c.candidate_id for c in cands]
        assert len(ids) == len(set(ids)), "candidate_id must be unique per signature"
        for c in cands:
            expected = hashlib.sha256(c.signature.encode("utf-8")).hexdigest()[:12]
            assert c.candidate_id == expected, (
                f"candidate_id must be sha256(signature)[:12]; got {c.candidate_id!r}"
            )
            assert toolify_miner.candidate_id(c.signature) == expected


def test_candidate_id_in_renders():
    """candidate_id is emitted as an ADDITIVE markdown column and JSON key; no
    existing schema field is removed or renamed."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        logs = _build_two_run_log_dir(Path(td))
        cands = toolify_miner.mine(logs)
        md = toolify_miner.render_markdown(cands)
        assert "candidate_id" in md.splitlines()[0], "markdown header missing candidate_id"
        assert cands[0].candidate_id in md, "markdown rows missing the id value"
        rows = json.loads(toolify_miner.render_json(cands))
        for row in rows:
            assert "candidate_id" in row, "JSON row missing candidate_id"
        # Additive: the full prior schema is still present.
        for key in ("signature", "occurrences", "run_count",
                    "est_tokens_per_occurrence", "score", "deterministic",
                    "above_bar", "n_calls", "sample_tools"):
            assert key in rows[0], f"prior schema field {key} must survive"


# ---------------------------------------------------------------------------
# Self-contained runner (mirrors test_lazy_core.py's pattern).
# ---------------------------------------------------------------------------

_TESTS = [(n, f) for n, f in sorted(globals().items())
          if n.startswith("test_") and callable(f)]

_PASSES: list[str] = []
_FAILURES: list[str] = []


def _run_test(name, fn):
    try:
        fn()
        _PASSES.append(name)
        print(f"  PASS  {name}")
    except _ModuleMissing as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except AssertionError as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")


def main() -> int:
    print("=" * 60)
    print("test_toolify_miner.py — toolify miner tests")
    print("=" * 60)
    if _IMPORT_ERROR is not None:
        print(f"\nMODULE NOT YET PRESENT (expected RED): {_IMPORT_ERROR}\n")
    print()
    for name, fn in _TESTS:
        _run_test(name, fn)
    total, passed, failed = len(_TESTS), len(_PASSES), len(_FAILURES)
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if _FAILURES:
        print("\nFailed tests:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
