"""lazy_core.gates — the completion-gate plane (evidence / coherence / ledger-verify).

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 4, WU-1) — a move-only refactor with zero behavior change. Owns the
anti-overfit design-gate ship seam (``gate_verdict_ok``), the completion-
evidence gate (``evaluate_completion_evidence`` + the commit-drift /
observation-gap verdicts), the verification-row auto-tick
(``autotick_verification_rows``), the plan checkbox / structural-backstop
helpers, and the completion-ledger gate (``verify_ledger`` +
``summarize_failing_detail``).

First write-path move, sanctioned by the two archived bug receipts (SPEC D2
Constraint 3): docs/bugs/_archive/mark-complete-partial-apply-noop-unrecoverable/
FIXED.md and docs/bugs/_archive/production-sentinel-writes-bypass-atomic-write/
FIXED.md. All writes here go through ``_ctx._atomic_write``.

Deferred function-local imports: the provenance derivation helpers
``_git_capture_lines`` / ``derive_touched_from_brackets`` /
``derive_touched_from_grep`` (ledger plane — ``.ledgers``, kept
function-local: ``.ledgers`` imports this module at top level, a genuine
cycle). ``_current_head`` / ``_git`` resolve top-level from ``.runtimeplane``
(Phase-5 WU-3).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import time

from pathlib import Path
from typing import Any

from ._ctx import _SCRIPTS_DIR, _atomic_write, _diag
from . import docmodel
from .docmodel import (
    _FAIL_CLOSED_EVIDENCE_SENTINELS,
    spec_status,
    _coerce_evidence_count,
    _has_any_complete_plan,
    _implementation_plans_exist,
    _plan_phase_set,
    _plan_status,
    _unchecked_wus_in_plan_scope,
    count_deliverables,
    enumerate_deferred_verification_rows,
    find_implementation_plans,
    parse_sentinel,
    remaining_unchecked_are_verification_only,
    repo_has_no_app_surface,
    skip_waiver_refusal,
)
from .runtimeplane import _current_head, _git


# ---------------------------------------------------------------------------
# anti-overfit-design-gate D3 — completion-gate ship seam (STATE-lane seam,
# NEEDS_INPUT_PROVISIONAL.md D3/D4/D7 — feature is STRUCTURALLY PROVISIONAL,
# unratified; see this module's ``gate_verdict_ok`` docstring for the honesty
# rail this seam is deliberately keyed under). Reuses harness-gate.py's
# manifest loader + glob matcher via in-process import (the SAME pattern
# ``plan_structural_backstop`` uses for validate-plan.py) rather than
# duplicating the manifest schema/matching logic here.
# ---------------------------------------------------------------------------

def _load_harness_gate_module():
    """Import harness-gate.py (this script's sibling) via importlib — the
    same dash-free-module-name workaround as ``_load_validate_plan_module``.
    Never raises by itself; callers degrade fail-open/out-of-scope."""
    import importlib.util

    path = _SCRIPTS_DIR / "harness-gate.py"
    spec = importlib.util.spec_from_file_location("harness_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_control_surface_globs(repo_root: Path) -> "list[str] | None":
    """The merged ``control_surfaces`` + ``gate_own`` glob list from
    ``docs/gate/control-surfaces.json`` (harness-gate.py's own manifest
    schema/reader — imported, never re-implemented). Returns ``None`` when
    the manifest is absent or malformed — the caller treats that as
    out-of-scope (a repo without the manifest, or claude-config before D1
    ratification removes it, is completely unaffected)."""
    try:
        hg = _load_harness_gate_module()
        manifest = hg.load_manifest(Path(repo_root))
    except Exception:  # noqa: BLE001 — missing/malformed manifest -> None
        return None
    return manifest.get("globs")


def _manifest_glob_match(path: str, glob: str) -> bool:
    """Delegate to harness-gate.py's ``_glob_match`` (imported, never
    re-implemented). Any import failure degrades to no-match (never crashes
    the ship seam)."""
    try:
        hg = _load_harness_gate_module()
        return hg._glob_match(path, glob)
    except Exception:  # noqa: BLE001
        return False


def gate_verdict_ok(spec_path: Path, repo_root: Path) -> dict:
    """anti-overfit-design-gate D3 ship seam. PURE READ.

    Refuses a scoped item whose ``GATE_VERDICT.md`` is missing, has any
    ``fail``-graded check, or has an unsigned ``gate_weakening`` hit. Scope is
    RE-DERIVED from the item's own commit set against the committed
    control-surface manifest (never trusted from the verdict file itself —
    a verdict cannot self-attest its own applicability). Out-of-scope, or no
    manifest present at all, is ``{ok: True, in_scope: False}`` — byte-
    identical to a repo/feature this gate has never touched.

    **HONESTY RAIL (do not remove without a ratification event):** this
    feature (anti-overfit-design-gate) is itself STRUCTURALLY PROVISIONAL —
    ``docs/features/anti-overfit-design-gate/NEEDS_INPUT_PROVISIONAL.md``
    records D1/D3/D4/D7 as auto-accepted-not-ratified, `divergence:
    structural` (the most severe grade). This function's own enforcement is
    GATED ENTIRELY on ``docs/gate/control-surfaces.json`` existing (D1's own
    committed-manifest choice) — with the manifest absent (e.g. removed on a
    D1 redirect) this function is a pure no-op returning ``in_scope: False``
    for every caller, so ratification (or a full redirect) reverts cleanly:
    delete the manifest and this ship seam disarms itself with zero code
    changes required.

    Returns ``{ok: bool, in_scope: bool, reason: str}``.
    """
    manifest_globs = _load_control_surface_globs(repo_root)
    if manifest_globs is None:
        return {"ok": True, "in_scope": False, "reason": "no control-surface manifest"}
    changed = _item_commit_touched_files(spec_path, repo_root)
    hits = [f for f in changed if any(
        _manifest_glob_match(f, g) for g in manifest_globs)]
    if not hits:
        return {"ok": True, "in_scope": False, "reason": "out of scope"}
    verdict_path = Path(spec_path) / "GATE_VERDICT.md"
    if not verdict_path.exists():
        return {
            "ok": False, "in_scope": True,
            "reason": "scoped change missing GATE_VERDICT.md",
        }
    try:
        fm = parse_sentinel(verdict_path)
    except SystemExit:
        # parse_sentinel _die()s on malformed frontmatter — a ship seam must
        # report, never crash the completion process. Treat as a failing
        # verdict (never a silent pass on a corrupt file).
        return {
            "ok": False, "in_scope": True,
            "reason": "GATE_VERDICT.md frontmatter is malformed/unreadable",
        }
    checks = fm.get("checks") or {}
    if not isinstance(checks, dict):
        checks = {}
    failing = [k for k, v in checks.items() if v == "fail"]
    if failing:
        return {
            "ok": False, "in_scope": True,
            "reason": f"GATE_VERDICT.md failing check(s): {failing}",
        }
    if checks.get("gate_weakening") == "hit-signed" and not fm.get("override"):
        return {
            "ok": False, "in_scope": True,
            "reason": "gate_weakening hit lacks operator override",
        }
    return {"ok": True, "in_scope": True, "reason": "gate verdict clean"}


# A hardening-workstream commit carries the harden-harness Commit-discipline
# prefix ``harden(<area>):`` on its subject line (the skill MANDATES it on every
# commit it makes). It is the ONLY structural signal distinguishing a foreground
# observed-friction harden commit — a DIFFERENT workstream — from a queue item's
# own shipped commits when both land inside one cycle bracket's git-log range.
# A pipeline item never commits under this prefix, so excluding it from an item's
# completion-gate scope can never drop the item's own work.
_FOREIGN_HARDEN_SUBJECT_RE = re.compile(r"^\s*harden\(")


def _commit_subject_is_foreign_harden(repo_root: Path, sha: str) -> bool:
    """True iff commit ``sha``'s subject begins with the harden-harness
    commit-discipline prefix ``harden(`` — the structural marker of a
    hardening-workstream commit (a different workstream from any queue item).

    FAIL-OPEN: an unreadable subject (non-git tree, bad sha, git unavailable)
    returns ``False`` — treated as NOT foreign, so a real item commit is never
    silently dropped and the completion gate is never weakened by a read error.
    """
    from .ledgers import _git_capture_lines  # ledger plane (re-pointed at Phase-4 WU-2)
    lines = _git_capture_lines(
        repo_root, ["show", "-s", "--format=%s", str(sha)])
    if not lines:
        return False
    return bool(_FOREIGN_HARDEN_SUBJECT_RE.match(lines[0]))


def _files_from_commits(repo_root: Path, shas: "list[str]") -> "list[str]":
    """Union the per-commit ``git show --name-only`` file sets for ``shas``
    (each commit's OWN diff, not a range diff). Sorted; empty on any read
    failure per commit (fail-open, never raises)."""
    from .ledgers import _git_capture_lines  # ledger plane (re-pointed at Phase-4 WU-2)
    files: set[str] = set()
    for sha in shas:
        lines = _git_capture_lines(
            repo_root,
            ["show", "--no-merges", "--name-only", "--format=", str(sha)])
        for ln in (lines or []):
            s = ln.strip()
            if s:
                files.add(s)
    return sorted(files)


def _item_commit_touched_files(spec_path: Path, repo_root: Path) -> "list[str]":
    """The touched-file set for an item's shipped commits, reusing the
    EXISTING derivation ``write_provenance`` already uses (commit-brackets
    primary, message-grep fallback via ``derive_touched_from_brackets`` /
    ``derive_touched_from_grep``) — never re-implemented. ``spec_path`` may
    be the item's SPEC.md file or its containing dir; the item id is the
    dir's basename either way.

    FOREIGN-HARDEN EXCLUSION (gate-scope-folds-concurrent-harden-commits): the
    bracket ledger records each cycle as a ``begin_sha..end_sha`` RANGE, so a
    foreground observed-friction ``harden(...)`` commit the orchestrator lands
    mid-run is swept into the range diff even though it is a DIFFERENT
    workstream from the queue item. Those foreign commits are excluded from the
    item's completion-gate scope so a feature is never forced to answer for a
    concurrent harden workstream's control-surface changes. When no foreign
    commit is present (the common case), the pre-existing range-derived file
    set is returned BYTE-IDENTICALLY (no re-derivation, no behavior change).
    """
    from .ledgers import (  # ledger plane (re-pointed at Phase-4 WU-2)
        derive_touched_from_brackets,
        derive_touched_from_grep,
    )
    item_dir = Path(spec_path)
    if item_dir.name == "SPEC.md":
        item_dir = item_dir.parent
    item_id = item_dir.name
    derived = derive_touched_from_brackets(repo_root, item_id)
    if derived is None:
        derived = derive_touched_from_grep(repo_root, item_id)
    commit_shas = list((derived or {}).get("commits") or [])
    non_foreign = [
        c for c in commit_shas
        if not _commit_subject_is_foreign_harden(repo_root, c)]
    if non_foreign == commit_shas:
        # No foreign harden commit was filtered — preserve the exact prior
        # file set (byte-identical common-case behavior).
        return list((derived or {}).get("files") or [])
    return _files_from_commits(repo_root, non_foreign)


def evaluate_completion_evidence(feature_dir: Path, repo_root: Path) -> dict:
    """Evaluate a feature's on-disk /mcp-test evidence → completion verdict.

    Returns ``{verdict, reason, pass_count, validated_commit}`` where:
      - ``verdict`` ∈ {``"exempt-and-tick"``, ``"warn-exempt"``, ``"refuse"``}
        (the LOCKED contract Phase 3 branches on).
      - ``reason``  — a human-readable explanation (for diagnostics / receipts).
      - ``pass_count`` — the cardinality numerator Phase 2's auto-tick asserts
        against (``int`` on an exempt/warn verdict; ``None`` on most refusals).
      - ``validated_commit`` — the sha Phase 2 stamps into each auto-tick audit
        comment (``str`` on exempt/warn; ``None`` when unavailable).

    Decision table (SPEC Technical Design, LOCKED). The gate requires the UNION
    of VALIDATED.md (kind: validated, the VSA attestation envelope) AND
    MCP_TEST_RESULTS.md (kind: mcp-test-results, result: all-passing,
    pass==total, pass>0, the raw provenance) — neither file alone suffices:

      * both present + passing + validated_commit == HEAD → exempt-and-tick
      * VALIDATED.md present, results missing/malformed       → refuse (forged)
      * results present, VALIDATED.md missing                 → refuse (no VSA)
      * SKIP_MCP_TEST.md / DEFERRED_* (no passing results)    → refuse (closed)
      * pass==total==0                                        → refuse (zero-test)
      * validated_commit != HEAD, docs-only (*.md) drift      → warn-exempt
      * validated_commit != HEAD, any source/script/config    → refuse (TOCTOU)
      * neither file                                          → refuse (no evidence)
    """
    def _refuse(reason: str, *, pass_count=None, validated_commit=None) -> dict:
        return {
            "verdict": "refuse",
            "reason": reason,
            "pass_count": pass_count,
            "validated_commit": validated_commit,
        }

    validated_meta = parse_sentinel(feature_dir / "VALIDATED.md")
    has_validated = (
        validated_meta is not None
        and validated_meta.get("kind") == "validated"
    )

    results_meta = parse_sentinel(feature_dir / "MCP_TEST_RESULTS.md")
    has_results_kind = (
        results_meta is not None
        and results_meta.get("kind") == "mcp-test-results"
    )

    # --- Fail-closed sentinels (skip / defer) when no passing results back them.
    # These are checked when the passing-results union is NOT satisfied; a
    # passing run alongside a stray skip file still evaluates on the evidence.
    def _fail_closed_present() -> str | None:
        for fname in _FAIL_CLOSED_EVIDENCE_SENTINELS:
            if (feature_dir / fname).exists():
                return fname
        return None

    # --- Neither evidence file → no evidence of verification execution.
    if not has_validated and not has_results_kind:
        closed = _fail_closed_present()
        if closed:
            return _refuse(
                f"{closed} present without passing /mcp-test evidence — "
                "skip/defer fails closed (no auto-tick)"
            )
        return _refuse(
            "neither VALIDATED.md nor MCP_TEST_RESULTS.md present — "
            "no evidence of verification execution"
        )

    # --- results present, VALIDATED.md missing → policy/VSA layer never ran.
    if not has_validated:
        return _refuse(
            "MCP_TEST_RESULTS.md present but VALIDATED.md (kind: validated) "
            "missing — the attestation/VSA layer never ran"
        )

    # --- VALIDATED.md present, results missing/malformed → forged-attestation.
    if not has_results_kind:
        closed = _fail_closed_present()
        if closed:
            return _refuse(
                f"{closed} present without passing MCP_TEST_RESULTS.md — "
                "skip/defer fails closed (no auto-tick)"
            )
        return _refuse(
            "VALIDATED.md present but MCP_TEST_RESULTS.md missing or malformed "
            "(no 'kind: mcp-test-results') — forged-attestation risk"
        )

    # --- Both present. Require a genuinely-passing run — OR a scoped-validated
    # observation-gap disposition (Gap 1 coupling,
    # harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 1). This
    # MUST mirror the __write_validated_from_results__ apply gate's promotion rule
    # exactly: a `result: partial` is accepted ONLY when its
    # `observation_gap_exemptions` block is populated and EVERY entry carries a
    # non-empty `spec_class` provenance (the citation that distinguishes a verified
    # untestable-class assessment from a convenience skip) AND the MCP-driveable
    # scope is fully passing (the pass==total cross-check below). Without this
    # parallel acceptance the scoped VALIDATED.md minted by the apply gate would
    # still be re-refused here, perpetuating the deadlock one layer deeper at the
    # completion-integrity gate. A genuine MCP-scope failure (pass < total) or a
    # provenance-less exemption falls through to the unchanged refusal.
    _result_literal = results_meta.get("result")
    # Shared predicate (observation_gap_promotable) — the SINGLE home for the
    # scoped observation-gap partial rule. This gate MUST mirror the apply gate
    # and the Step-9 routing exactly; routing all three through one helper is
    # what keeps them from diverging (the divergence that reintroduced the
    # deadlock one layer up at the Step-9 MCP routing — community-sharing).
    _observation_gap_ok = observation_gap_promotable(results_meta)
    if _result_literal != "all-passing" and not _observation_gap_ok:
        return _refuse(
            f"MCP_TEST_RESULTS.md result is "
            f"{results_meta.get('result')!r} — expected 'all-passing' "
            "(or a scoped observation-gap partial whose every exemption carries "
            "a spec_class provenance and whose MCP scope fully passes)"
        )
    pass_count = _coerce_evidence_count(results_meta.get("pass_count"))
    total_count = _coerce_evidence_count(results_meta.get("total_count"))
    if pass_count is None or total_count is None:
        return _refuse(
            "MCP_TEST_RESULTS.md pass_count/total_count missing or malformed"
        )
    if pass_count != total_count:
        return _refuse(
            f"MCP_TEST_RESULTS.md pass_count ({pass_count}) != total_count "
            f"({total_count}) — a partial pass cannot exempt"
        )
    # pass>0 mandatory: pass==total==0 is the CI false-positive anti-pattern.
    if pass_count == 0:
        return _refuse(
            "MCP_TEST_RESULTS.md reports pass_count == total_count == 0 — a "
            "zero-test suite cannot certify (pass>0 required)"
        )

    validated_commit = results_meta.get("validated_commit")
    if validated_commit is not None:
        validated_commit = str(validated_commit)

    # --- Freshness / HEAD-drift carve-out.
    head = _current_head(repo_root)
    if validated_commit is None or head is None:
        # No recorded commit, or HEAD unresolvable (non-git tree): cannot prove
        # drift either way. Treat as fresh-enough (warn) — the upstream
        # __write_validated_from_results__ gate already required a fresh commit
        # to MINT VALIDATED.md, so a missing field here is the legacy path.
        return {
            "verdict": "exempt-and-tick",
            "reason": "passing evidence; validated_commit/HEAD unresolved "
                      "(legacy/non-git) — freshness UNVERIFIED",
            "pass_count": pass_count,
            "validated_commit": validated_commit,
        }
    if validated_commit == head:
        return {
            "verdict": "exempt-and-tick",
            "reason": "VALIDATED.md + passing MCP_TEST_RESULTS.md, "
                      "validated_commit == HEAD",
            "pass_count": pass_count,
            "validated_commit": validated_commit,
        }

    # validated_commit != HEAD → classify the drift via the SHARED
    # commit_drift_verdict helper (the SINGLE home for the docs-only carve-out;
    # the Step-9 state-script gates + the __write_validated_from_results__ apply
    # gate route through the same helper). Docs-only (*.md) → warn + exempt-and-
    # tick; any non-.md (source/script/config) path → refuse-and-revalidate
    # (TOCTOU: the validated code is not the code being promoted); an
    # unresolvable diff → refuse conservatively.
    drift = commit_drift_verdict(repo_root, validated_commit, head)
    if drift["verdict"] == "unresolvable":
        # Diff unresolvable (e.g. validated_commit not in this repo). Conservative
        # — cannot prove the drift is docs-only, so refuse-and-revalidate.
        return _refuse(
            f"validated_commit {validated_commit} != HEAD {head} and the diff "
            "could not be resolved — re-run /mcp-test against current HEAD",
            pass_count=pass_count,
            validated_commit=validated_commit,
        )
    if drift["verdict"] == "non-docs-drift":
        return _refuse(
            f"validated_commit {validated_commit} != HEAD {head} with "
            f"source/script/config drift ({', '.join(drift['non_docs'][:5])}) — "
            "refuse-and-revalidate (TOCTOU)",
            pass_count=pass_count,
            validated_commit=validated_commit,
        )
    # drift["verdict"] == "docs-only"
    return {
        "verdict": "warn-exempt",
        "reason": f"validated_commit {validated_commit} != HEAD {head} but the "
                  "drift is docs-only (*.md) — safe to exempt-and-tick",
        "pass_count": pass_count,
        "validated_commit": validated_commit,
    }


# ---------------------------------------------------------------------------
# Deferred-runtime completion exemption
#   (completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo).
#
# The completion path AUTO-TICKS verification-only rows only when
# evaluate_completion_evidence above authorizes on the UNION of VALIDATED.md +
# a passing MCP_TEST_RESULTS.md. In a no-MCP-surface repo (a re-verified
# ``granted_by: pipeline-structural`` skip) that union is STRUCTURALLY
# impossible — there is no MCP server to produce MCP_TEST_RESULTS.md — so a
# legitimately-DEFERRED ``<!-- verification-only -->`` row (closed later outside
# the pipeline, e.g. by a cloud-session run) deadlocks the completion-coherence
# gate. The only pre-existing exemption marker (``<!-- descoped -->``)
# MISREPRESENTS a deferred row as dropped.
#
# This helper is the honest route: it authorizes exempting those rows (they stay
# ``- [ ]`` — NOT ticked) ONLY when the deferral cannot be evidenced any other
# way AND is honestly tracked. It NEVER mutates state; the caller
# (apply_pseudo) writes the RUNTIME_GATES.md ledger and threads
# ``verification_only_exempt=True`` into _phase_completion_plan.
# ---------------------------------------------------------------------------

def evaluate_deferred_runtime_exemption(feature_dir: Path, repo_root: Path) -> dict:
    """Return ``{ok: bool, reason: str}`` — may a DEFERRED verification-only row
    complete via the no-MCP structural-skip route?

    ``ok`` is True iff ALL hold:
      * ``VALIDATED.md`` present with ``kind: validated`` — the attestation
        envelope exists (a bare skip without validation cannot complete).
      * ``SKIP_MCP_TEST.md`` present AND ``granted_by: pipeline-structural`` AND
        ``skip_waiver_refusal(meta, repo_root)`` returns None — i.e. the
        structural waiver RE-VERIFIES against the live repo
        (``repo_has_no_app_surface``). This single check is what confines the
        exemption to genuinely no-MCP-surface repos: an app repo (``src-tauri/``
        or ``package.json`` present) re-verifies False, ``skip_waiver_refusal``
        refuses, and a verification-only row there still requires real MCP
        evidence to auto-tick.

    PURE / side-effect-free (the only I/O is reading the two sentinels). Does NOT
    look at PHASES.md — the caller decides whether there are actually unchecked
    verification-only rows to exempt (an ``ok`` verdict with no such rows is a
    no-op). A structural skip that does NOT re-verify, a non-structural
    ``granted_by``, or a missing VALIDATED.md all return ``ok: False`` with a
    reason (the strict coherence gate then blocks as before).
    """
    validated_meta = parse_sentinel(feature_dir / "VALIDATED.md")
    if not (validated_meta and validated_meta.get("kind") == "validated"):
        return {
            "ok": False,
            "reason": "VALIDATED.md (kind: validated) absent — no attestation "
                      "envelope to certify the deferral",
        }
    skip_meta = parse_sentinel(feature_dir / "SKIP_MCP_TEST.md")
    if not skip_meta:
        return {
            "ok": False,
            "reason": "SKIP_MCP_TEST.md absent — the MCP auto-tick is not "
                      "structurally impossible; no deferred-runtime route",
        }
    if skip_meta.get("granted_by") != "pipeline-structural":
        return {
            "ok": False,
            "reason": "SKIP_MCP_TEST.md is not granted_by: pipeline-structural — "
                      "the deferred-runtime route is confined to a structural "
                      "no-app-surface skip (an operator/mcp-test skip earns its "
                      "rows the ordinary way)",
        }
    waiver_refusal = skip_waiver_refusal(skip_meta, repo_root)
    if waiver_refusal is not None:
        return {
            "ok": False,
            "reason": f"structural SKIP_MCP_TEST.md did not re-verify — "
                      f"{waiver_refusal}",
        }
    return {
        "ok": True,
        "reason": "structural no-app-surface skip re-verified + VALIDATED.md "
                  "present — deferred verification-only rows may complete with a "
                  "RUNTIME_GATES.md ledger",
    }


def write_runtime_gates_ledger(
    feature_dir: Path, rows: list[dict], *, date: str
) -> dict:
    """Write/overwrite ``RUNTIME_GATES.md`` for the deferred verification-only rows.

    Mirrors the ``_components/pending-runtime-gates.md`` contract (the manual
    ``/execute-plan`` seam) at the lazy completion gate: one table row per pending
    gate — verbatim gate text, owning phase, date deferred — led by the mandatory
    ``N MANUAL RUNTIME GATES PENDING`` line and the no-downstream-owner
    declaration (this repo has no ``/mcp-test`` step, so the ledger is the SOLE
    owner). Idempotent + byte-stable for a given ``(rows, date)``: the whole file
    is regenerated each call via ``_atomic_write`` (no incremental append, so a
    re-run never duplicates rows). Returns ``{"written": bool, "count": int,
    "path": str}``.

    ``rows`` is the ``enumerate_deferred_verification_rows`` output
    (``[{phase, lineno, text}]``). Empty ``rows`` writes nothing.
    """
    ledger_path = feature_dir / "RUNTIME_GATES.md"
    if not rows:
        return {"written": False, "count": 0, "path": str(ledger_path)}
    n = len(rows)
    lines = [
        f"# Runtime Gates — {n} MANUAL RUNTIME GATES PENDING (feature not "
        f"verified end-to-end)",
        "",
        "These runtime-verification rows are DEFERRED — their PHASES.md checkboxes "
        "stay `- [ ]` because they cannot run in this environment yet (closed "
        "later outside the pipeline; see each row's own closer). This repo "
        "declares `MCP runtime: not-required` (no `/mcp-test` step downstream), so "
        "**this ledger is the ONLY owner of these rows** — no pipeline gate will "
        "hold them; the operator working the ledger is the sole remaining "
        "mechanism.",
        "",
        "Written by the completion gate "
        "(`completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`) when "
        "`__mark_complete__`/`__mark_fixed__` exempted these deferred rows on the "
        "structural-skip route. Regenerated (not appended) on each completion.",
        "",
        "| # | Owning phase | Deferred | Gate row (verbatim) |",
        "|---|---|---|---|",
    ]
    for i, row in enumerate(rows, start=1):
        phase = (row.get("phase") or "").replace("|", "\\|")
        # Strip the leading checkbox token for readability; keep the rest verbatim.
        text = (row.get("text") or "")
        text = re.sub(r"^-\s*\[\s*\]\s*", "", text).replace("|", "\\|")
        lines.append(f"| {i} | {phase} | {date} | {text} |")
    lines.append("")
    _atomic_write(ledger_path, "\n".join(lines))
    return {"written": True, "count": n, "path": str(ledger_path)}


def _git_diff_name_only(
    repo_root: Path, base: str, head: str
) -> list[str] | None:
    """Return the list of paths changed between ``base`` and ``head``, or None.

    Best-effort, mirroring _current_head's subprocess posture: a non-git root,
    an unknown commit, or an unavailable git all yield None (the caller treats
    None conservatively as "cannot prove docs-only" → refuse).
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", base, head],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def observation_gap_promotable(meta: dict) -> bool:
    """Is this MCP_TEST_RESULTS.md metadata a sanctioned observation-gap partial?

    The SINGLE home for the "scoped observation-gap partial" promotion predicate.
    THREE routing/gate sites route through this helper so they cannot diverge
    (the divergence that produced the 2026-07 Step-9 observation-gap DEADLOCK —
    see hardening-log Round for community-sharing): (1) the
    ``__write_validated_from_results__`` apply gate in ``apply_pseudo``, (2) the
    completion-integrity gate in ``evaluate_completion_evidence``, and (3) the
    Step-9 MCP routing in ``lazy-state.py`` / ``bug-state.py``.

    Background (Gap 1 coupling,
    harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 1): some
    behavior classes are SPEC-LOCKED to the unit/WDIO test tier (see
    ``docs/features/mcp-testing/SPEC.md``) and thus have no MCP UI driver to
    exercise them end-to-end. A run over such a feature honestly carries
    ``result: partial`` even though its MCP-driveable scope fully passes. The
    downstream apply + completion gates ALREADY accept this disposition; the
    Step-9 routing did not, so a valid observation-gap partial re-dispatched
    ``/mcp-test`` every cycle — an infinite loop ONE LAYER UP from the deadlock
    the completion gate's comment warns about.

    Promotion is gated NARROWLY — a ``result: partial`` promotes ONLY when its
    ``observation_gap_exemptions`` is a NON-EMPTY list whose EVERY entry is a
    mapping carrying a non-empty ``spec_class`` provenance string (the citation
    that distinguishes a verified untestable-class assessment from a convenience
    skip — mirroring the SKIP_MCP_TEST.md ``spec_class``-required discipline).

    This predicate is HALF of the AND: callers MUST still enforce the
    ``pass_count == total_count`` cross-check separately, so a ``partial`` with a
    GENUINE MCP-scope failure (pass < total) is NOT promoted. A ``partial`` with
    no exemptions, or a provenance-less exemption, returns False here.
    """
    if meta.get("result") != "partial":
        return False
    exemptions = meta.get("observation_gap_exemptions")
    return (
        isinstance(exemptions, list)
        and len(exemptions) > 0
        and all(
            isinstance(e, dict)
            and isinstance(e.get("spec_class"), str)
            and e.get("spec_class", "").strip() != ""
            for e in exemptions
        )
    )


def _is_noninvalidating_drift_path(path: str) -> bool:
    """Can this changed path NOT invalidate an MCP validation? (drift carve-out)

    Two STRUCTURAL classes of changed file cannot make a recorded
    ``validated_commit`` stale relative to HEAD for the Step-9 staleness gate,
    because neither is the code-under-test:

      * any Markdown file (``*.md``) — MCP_TEST_RESULTS.md, PHASES.md
        reconciliation, spec docs. The original Round-36 (2026-06-23) carve-out.
      * an MCP test-SCENARIO definition (``*.yaml`` / ``*.yml``) that lives under
        an ``mcp-test`` / ``mcp-tests`` path segment — the scenario CORPUS
        (e.g. ``docs/testing/mcp-tests/corpus/live/<name>.yaml``). An /mcp-test
        FIRST-RUN authors these scenario files and commits them alongside
        MCP_TEST_RESULTS.md, so the structurally-unavoidable one-commit results
        lag includes them. A scenario definition IS the test, never the
        product code it exercises, so it cannot invalidate the validation
        (harden 2026-07: the ``.md``-only carve-out forced a wasted re-verify
        cycle on every first-run validation — the scenario ``.yaml`` in the same
        commit tripped ``non-docs-drift``).

    The mcp-test path-segment scope is what keeps a product ``config.yaml`` /
    ``.github/workflows/*.yml`` OUT of the carve-out — those carry no
    ``mcp-test(s)`` segment, so they still (correctly) classify as invalidating
    (TOCTOU) drift. Suffix + segment checks are case-insensitive and
    separator-normalized.
    """
    p = path.lower().replace("\\", "/")
    if p.endswith(".md"):
        return True
    if p.endswith((".yaml", ".yml")):
        return any(seg in ("mcp-test", "mcp-tests") for seg in p.split("/"))
    return False


def commit_drift_verdict(
    repo_root: Path, validated_commit, head
) -> dict:
    """Classify the drift between a recorded ``validated_commit`` and ``head``.

    The SINGLE home for the "stale MCP results" docs-only carve-out. Three call
    sites route through this helper so they cannot diverge (the divergence that
    produced the 2026-06-23 Step-9 re-verify DEADLOCK — see hardening-log Round
    36): (1) ``evaluate_completion_evidence`` (completion-coverage audit), (2)
    the Step-9 freshness gate in ``lazy-state.py`` / ``bug-state.py``, and (3)
    the ``__write_validated_from_results__`` apply gate in ``apply_pseudo``.

    WHY a docs-only carve-out is correct (and not a gate-weakening): an
    ``/mcp-test`` cycle that obeys its turn-end clean-tree contract MUST commit
    ``MCP_TEST_RESULTS.md`` — and that commit advances HEAD exactly one past the
    ``validated_commit`` it just recorded. On a FIRST-RUN validation the same
    commit ALSO carries the newly-authored mcp-test SCENARIO files
    (``*.yaml``/``*.yml`` under the ``mcp-test(s)`` corpus). The results file is
    therefore PERPETUALLY one commit stale, and that one-commit drift is a
    PURE NON-INVALIDATING delta (docs + scenario definitions — see
    ``_is_noninvalidating_drift_path``). Strict ``validated_commit == HEAD`` is
    structurally unsatisfiable in that bracket → an infinite re-verify loop on
    EVERY feature/bug (and the ``.md``-only carve-out forced a wasted re-verify
    on every first-run whose commit included scenario ``.yaml`` — harden
    2026-07). Accepting non-invalidating drift restores liveness WITHOUT
    weakening the TOCTOU guard: any real source / script / product-config drift
    still refuses, because that is genuine "the validated code is not the code
    being promoted" risk.

    Returns ``{verdict, non_docs, changed}`` where ``verdict`` ∈:
      - ``"fresh"``         — ``validated_commit`` / ``head`` unresolved (None /
                              blank) OR equal. The caller's existing
                              legacy-permissive / equality path applies; this
                              helper does NOT run ``git diff`` in that case.
      - ``"docs-only"``     — drift is exclusively NON-INVALIDATING validation
                              artifacts (``*.md`` docs, or mcp-test SCENARIO
                              ``*.yaml``/``*.yml`` under an ``mcp-test(s)`` path
                              segment — see ``_is_noninvalidating_drift_path``)
                              → safe to accept-and-validate. (Verdict string kept
                              as ``"docs-only"`` for call-site compatibility even
                              though scenario files are not ``.md``.)
      - ``"non-docs-drift"``— ≥1 non-``.md`` path changed → refuse-and-revalidate
                              (TOCTOU). ``non_docs`` lists the offending paths.
      - ``"unresolvable"``  — the diff could not be computed (non-git root,
                              unknown commit, git unavailable) → caller refuses
                              conservatively (cannot prove docs-only).

    Best-effort and side-effect-free, mirroring ``_git_diff_name_only`` /
    ``_current_head`` subprocess posture.
    """
    vc = str(validated_commit).strip() if validated_commit is not None else ""
    hd = str(head).strip() if head is not None else ""
    if not vc or not hd or vc == hd:
        # Unresolved or equal — not a drift this helper classifies. The caller
        # owns the legacy-permissive (missing field / non-git) + equality paths.
        return {"verdict": "fresh", "non_docs": [], "changed": []}
    changed = _git_diff_name_only(repo_root, vc, hd)
    if changed is None:
        return {"verdict": "unresolvable", "non_docs": [], "changed": []}
    non_docs = [p for p in changed if not _is_noninvalidating_drift_path(p)]
    if non_docs:
        return {
            "verdict": "non-docs-drift",
            "non_docs": non_docs,
            "changed": changed,
        }
    return {"verdict": "docs-only", "non_docs": [], "changed": changed}


# ---------------------------------------------------------------------------
# autotick_verification_rows — atomic, line-anchored, audited auto-tick rewrite
#   (completion-coherence-gate-reconciliation Phase 2).
#
# Given a feature whose Phase-1 verdict is exempt-and-tick / warn-exempt, rewrite
# every remaining unchecked verification-marked row (``- [ ]`` carrying the
# canonical ``_VERIFICATION_ONLY_MARKER`` on the SAME line) to ``- [x]`` —
# atomically (via _atomic_write), fence-safely, with a byte-stable audit comment,
# under a cardinality over-relaxation guard, and Superseded-aware. NOT wired into
# the completion gate here (Phase 3 owns the ordering: tick → re-check → receipt).
# ---------------------------------------------------------------------------

# An unchecked checkbox row, capturing the leading dash+bracket so the rewrite
# preserves indentation and replaces ONLY the inner blank with 'x'. Tolerates
# variable interior whitespace (``- [ ]`` / ``- [  ]``).
_UNCHECKED_ROW_RE = re.compile(r"^(\s*-\s+\[)\s+(\]\s.*)$")

# Idempotency marker: a row already carrying this comment is NOT re-ticked and
# the comment is NOT duplicated.
_AUTOTICK_COMMENT_PREFIX = "<!-- auto-ticked: validated_commit="


def autotick_verification_rows(
    phases_path: Path, validated_commit, pass_count: int
) -> dict:
    """Rewrite unchecked verification-marked rows to ``- [x]`` atomically.

    Returns ``{ticked_count: int, ok: bool, reason: str|None}``.

    A row is rewritten iff ALL hold:
      * it matches ``^\\s*-\\s+\\[\\s+\\]`` (an unchecked box, variable interior
        whitespace tolerated),
      * it carries ``_VERIFICATION_ONLY_MARKER`` (or its enclosing subsection
        header does — header-scope, mirroring
        ``remaining_unchecked_are_verification_only``),
      * it is NOT inside a ``` code fence,
      * it is NOT under a phase whose Status is ``Superseded``.

    Each rewritten row gets a byte-stable
    ``<!-- auto-ticked: validated_commit=<sha> -->`` audit comment appended so a
    later auditor distinguishes gate mutations from human/agent edits.

    **Cardinality lock (over-relaxation guard):** if the number of rows that
    WOULD be ticked exceeds ``pass_count``, the rewrite ABORTS writing nothing
    (``ok: False``) — catching marker-drift hallucination / forged evidence.

    **Atomic:** the file is rewritten via ``_atomic_write`` (temp-in-same-dir →
    ``os.replace``); a cardinality abort leaves the file byte-identical (no
    partial write — the count is computed BEFORE any write).

    **Idempotent:** a row already carrying the audit comment is skipped (not
    re-ticked, no duplicate comment); ``ticked_count`` counts only rows newly
    flipped this call.
    """
    text = phases_path.read_text(encoding="utf-8")
    src_lines = text.splitlines(keepends=True)

    # First PASS — identify the line indices to tick (cardinality computed
    # BEFORE any mutation so an abort writes nothing).
    to_tick: list[int] = []
    section_has_marker = False
    in_superseded_phase = False
    in_fence = False
    for idx, raw in enumerate(src_lines):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if heading:
            heading_text = heading.group(1)
            if re.match(r"Phase\s+\d+", heading_text):
                # New phase block — reset subsection + superseded tracking.
                in_superseded_phase = False
                section_has_marker = False
            else:
                section_has_marker = docmodel._VERIFICATION_ONLY_MARKER in raw
            continue
        if stripped.startswith("**"):
            bold = re.match(r"^\*\*(.+?)\*\*", stripped)
            if bold:
                bold_text = bold.group(1)
                if re.match(r"Status\s*:", bold_text) and "Superseded" in stripped:
                    in_superseded_phase = True
                    continue
                if docmodel._VERIFICATION_ONLY_MARKER in raw:
                    section_has_marker = True
                # else: preserve current scope (non-marker bold is prose).
                continue
        m = _UNCHECKED_ROW_RE.match(raw.rstrip("\r\n"))
        if not m:
            continue
        if in_superseded_phase:
            continue
        row_has_marker = docmodel._VERIFICATION_ONLY_MARKER in raw
        if not (row_has_marker or section_has_marker):
            continue
        # Idempotency: an already-audited row is not re-ticked.
        if _AUTOTICK_COMMENT_PREFIX in raw:
            continue
        to_tick.append(idx)

    # Cardinality lock — abort writing nothing on over-relaxation.
    if len(to_tick) > pass_count:
        return {
            "ticked_count": 0,
            "ok": False,
            "reason": (
                f"cardinality lock: {len(to_tick)} verification row(s) would be "
                f"ticked but only {pass_count} test(s) passed — refusing the "
                "auto-tick (marker-drift / forged-evidence guard)"
            ),
        }

    if not to_tick:
        return {"ticked_count": 0, "ok": True, "reason": None}

    # Second PASS — rewrite the identified rows in place, preserving the line
    # ending and flipping ONLY the inner blank to 'x', then appending the audit
    # comment before the line ending.
    audit = f"{_AUTOTICK_COMMENT_PREFIX}{validated_commit} -->"
    tick_set = set(to_tick)
    out_lines: list[str] = []
    for idx, raw in enumerate(src_lines):
        if idx not in tick_set:
            out_lines.append(raw)
            continue
        # Split the line ending off.
        ending = ""
        body = raw
        if raw.endswith("\r\n"):
            ending, body = "\r\n", raw[:-2]
        elif raw.endswith("\n"):
            ending, body = "\n", raw[:-1]
        elif raw.endswith("\r"):
            ending, body = "\r", raw[:-1]
        m = _UNCHECKED_ROW_RE.match(body)
        # ``m`` is guaranteed (idx came from the same regex in pass 1).
        new_body = f"{m.group(1)}x{m.group(2)} {audit}"
        out_lines.append(new_body + ending)

    _atomic_write(phases_path, "".join(out_lines))
    return {"ticked_count": len(to_tick), "ok": True, "reason": None}


# ---------------------------------------------------------------------------
# Completion ledger verification
# ---------------------------------------------------------------------------

def _phases_text_scoped_to(phases_text: str, phase_set: set[int]) -> str:
    """Return the subset of PHASES.md lines belonging to phases in ``phase_set``.

    Phase 9 WU-3 helper: the plan-scoped ``deliverables_done`` check must apply
    the SAME verification-only exemption mid-feature
    (``remaining_unchecked_are_verification_only``) but only over the plan's
    phases. ``_unchecked_wus_in_plan_scope`` already collects in-scope unchecked
    rows but does NOT distinguish verification rows, so instead we slice the
    PHASES body down to the in-scope ``### Phase N`` sections (each section runs
    from its ``### Phase N`` heading until the next phase heading or a ``## ``
    top-level boundary) and hand that slice to the existing exemption helper.

    Fence-aware in the same spirit as ``_unchecked_wus_in_plan_scope``: a fenced
    block opened inside an in-scope phase stays part of that phase's slice (the
    downstream helper re-tracks fences itself, so we simply preserve the lines).
    """
    out: list[str] = []
    current_phase: int | None = None
    for line in phases_text.splitlines():
        h = re.match(r"^###\s+Phase\s+(\d+)", line)
        if h:
            current_phase = int(h.group(1))
            if current_phase in phase_set:
                out.append(line)
            continue
        # A top-level ``## `` heading (NOT ``### Phase``) closes phase tracking —
        # content after it is not part of any in-scope phase. Keep the verification
        # heading recognizable to the exemption helper by re-emitting the line only
        # when we are still inside an in-scope phase.
        if line.startswith("## ") and not line.startswith("### "):
            current_phase = None
            continue
        if current_phase is not None and current_phase in phase_set:
            out.append(line)
    return "\n".join(out)


# A per-WU plan progress checkbox: ``- [ ] WU-N — <title>`` / ``- [x] WU-N …``.
# Made mandatory by write-plan ISSUE-6 (d8-effect-chains run 2026-06-14): every
# work unit in every generated plan part carries exactly one such row in a
# ``## Work Units`` checklist. ``/execute-plan`` ticks each as it lands the WU,
# so these rows are the MACHINE source of truth for plan-part deliverable
# completion (PHASES.md per-deliverable ticks are demoted to human documentation
# — see the verify_ledger docstring + write-plan/execute-plan SKILL prose).
#
# The WU id may be a bare number (``WU-3``) or a dotted sub-id (``WU-9.0``,
# ``WU-3a``) — accept any ``[A-Za-z0-9.]+`` run after ``WU-``. The separator after
# the id is the em-dash convention but we do not require it (a ``- [ ] WU-3``
# with no title still counts as a progress row). The match is anchored at the
# list-item bullet so a mid-prose mention of "WU-3" is NOT a false checkbox.
_PLAN_WU_CHECKBOX_RE = re.compile(
    r"^\s*-\s*\[(?P<mark>[ xX])\]\s*WU-[A-Za-z0-9.]+\b",
)


# ---------------------------------------------------------------------------
# completion-gate-refusal-opacity: verify_ledger `failing_detail` collectors.
#
# The `--verify-ledger` refusal historically named only the boolean
# `failing_check` — every axis had already computed the offending items
# (dirty files, divergent shas, incomplete plans, unchecked rows) and thrown
# them away, forcing the orchestrator to re-probe by hand. These collectors
# reuse the SAME fence-aware walks as count_deliverables /
# _plan_wu_checkbox_counts / _unchecked_wus_in_plan_scope so the diagnostic
# rows are byte-identical in shape to what the gate already computes — no new
# parsing surface, just line-number-annotated capture instead of a boolean
# reduction. Cap (`_DETAIL_MAX_ITEMS`) and excerpt truncation (`_excerpt`)
# mirror `classify_blocking_unchecked_rows`'s 80-char convention.
# ---------------------------------------------------------------------------
_DETAIL_MAX_ITEMS = 10


def _excerpt(text: str, max_chars: int = 80) -> str:
    """Truncate ``text`` to ``max_chars`` with an ellipsis marker — the same
    80-char convention ``classify_blocking_unchecked_rows`` uses."""
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _phases_unchecked_row_detail(
    phases_text: str, phase_set: set[int] | None = None, limit: int = _DETAIL_MAX_ITEMS
) -> dict:
    """Collect unchecked PHASES.md ``- [ ]`` rows with 1-based line numbers.

    Fence-aware, mirroring ``count_deliverables``. When ``phase_set`` is given,
    only rows inside a ``### Phase N`` section whose N is a member are
    collected (mirrors ``_unchecked_wus_in_plan_scope``'s heading-tracking
    walk — the legacy plan-scoped fallback); ``None`` scans the whole file
    (feature-level / unscoped-legacy-plan semantics).

    Returns ``{"rows": [{"line": N, "text": <=80-char excerpt}, ...], "total": M}``
    — ``rows`` capped at ``limit``, ``total`` uncapped (so a caller can report
    "N more" truncation honestly).
    """
    rows: list[dict] = []
    total = 0
    in_fence = False
    current_phase: int | None = None
    tracking = phase_set is not None
    for lineno, line in enumerate(phases_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if tracking:
            h = re.match(r"^###\s+Phase\s+(\d+)", line)
            if h:
                current_phase = int(h.group(1))
                continue
            if line.startswith("## "):
                current_phase = None
                continue
            if current_phase is None or current_phase not in phase_set:
                continue
        if re.match(r"^\s*-\s*\[\s*\]", line):
            total += 1
            if len(rows) < limit:
                rows.append({"line": lineno, "text": _excerpt(stripped)})
    return {"rows": rows, "total": total}


def _plan_wu_unchecked_row_detail(plan_text: str, limit: int = _DETAIL_MAX_ITEMS) -> dict:
    """Collect unchecked ISSUE-6 ``- [ ] WU-N`` rows with 1-based line numbers.

    Fence-aware, mirroring ``_plan_wu_checkbox_counts``'s walk. Same return
    shape as ``_phases_unchecked_row_detail`` — the ``deliverables_done``
    diagnostic for the ``plan-wu-checkboxes`` source.
    """
    rows: list[dict] = []
    total = 0
    in_fence = False
    for lineno, line in enumerate(plan_text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _PLAN_WU_CHECKBOX_RE.match(line)
        if not m or m.group("mark") != " ":
            continue
        total += 1
        if len(rows) < limit:
            stripped = line.strip()
            rows.append({"line": lineno, "text": _excerpt(stripped)})
    return {"rows": rows, "total": total}


def _plan_wu_checkbox_counts(plan_text: str) -> tuple[int, int]:
    """Return ``(unchecked, checked)`` counts of per-WU plan progress checkboxes.

    Parses the ISSUE-6 ``- [ ] WU-N — <title>`` / ``- [x] WU-N …`` rows from a
    plan part's body. Fence-aware in the same spirit as ``count_deliverables``:
    a checkbox inside a triple-backtick code fence is an illustrative example
    (e.g. the write-plan SKILL's own format sample) and is NOT counted.

    ``(0, 0)`` means the plan has NO parseable per-WU checkboxes at all — a
    legacy pre-ISSUE-6 plan. The caller uses that to fall back to the
    PHASES-phase-level behavior (with a diagnostic) rather than vacuously pass.
    """
    unchecked = 0
    checked = 0
    in_fence = False
    for line in plan_text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _PLAN_WU_CHECKBOX_RE.match(line)
        if not m:
            continue
        if m.group("mark") == " ":
            unchecked += 1
        else:
            checked += 1
    return unchecked, checked


# ---------------------------------------------------------------------------
# plan-structure-authoring-gate Phase 4 — pickup backstop (STATE-lane seam,
# NEEDS_INPUT_PROVISIONAL.md D1-RESIDENCY/D4-NOT-DONE). validate-plan.py's
# `--structural` rule set (rules 1/2/3/4/6, `run_structural_checks`) is
# authored and owned there — this seam calls it IN-PROCESS via importlib
# (mirroring validate-plan.py's own `_load_lazy_core`, which loads THIS
# module the same reverse-shaped way), so `lazy-state.py`/`bug-state.py`
# get the D4-recommended in-process check with ZERO subprocess spawn cost
# and WITHOUT hoisting the rule functions into this file (validate-plan.py
# stays byte-untouched — a third option satisfying D4's intent, distinct
# from both D1-RESIDENCY options (a) hoist / (b) subprocess shell-out).
# ---------------------------------------------------------------------------

def _load_validate_plan_module():
    """Import validate-plan.py (this script's sibling) via importlib — the
    reverse-direction mirror of validate-plan.py's own ``_load_lazy_core``.
    Resilient to invocation via the ``~/.claude/scripts`` symlink (resolves
    relative to THIS file's real parent, not the symlinked path). Never
    raises on import failure by itself — the caller degrades fail-open."""
    import importlib.util

    path = _SCRIPTS_DIR / "validate-plan.py"
    spec = importlib.util.spec_from_file_location("validate_plan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plan_structural_backstop(plan_path) -> dict:
    """Plan-structure-authoring-gate Phase 4 pickup backstop.

    Validates a plan part STRUCTURALLY (in-process, via validate-plan.py's
    ``run_structural_checks`` — imported, never re-implemented) at first
    ``/execute-plan`` routing, per the feature's recorded D4 design.

    Mid-execution exemption (WARN-only, per PHASES.md Phase 4's recorded
    Minimum Verifiable Behavior): a plan with >= 1 ticked WU
    (``_plan_wu_checkbox_counts``) is already in flight — a structurally
    invalid FRESH plan (zero ticked WUs) refuses the route; the SAME
    findings on an in-flight plan only WARN (never block work already
    underway).

    **Delta from the literal recorded design (documented, not silent):**
    a plan with ZERO parseable WU checkboxes at ALL (``unchecked == checked
    == 0``) is ALSO exempted from refusal (WARN-only), not just a plan with
    >= 1 ticked box. ``_plan_wu_checkbox_counts``'s own docstring calls this
    shape "a legacy pre-ISSUE-6 plan" whose caller "falls back to the
    PHASES-phase-level behavior... rather than vacuously pass" — i.e. the
    REST of this codebase has always tolerated a plan with no WU checklist
    at all as a different, valid, pre-existing shape, never an error.
    validate-plan.py's own rule 1 (``wu-checklist``) flags EVERY such plan
    as ERROR regardless of age; applying the literal "checked count only"
    discriminator here would refuse routing on every pre-existing legacy
    plan this repo already has (verified against this repo's own state-
    script smoke fixtures — see PHASES.md Implementation Notes). Refusal is
    reserved for a plan that genuinely HAS unchecked WU rows under the new
    convention and simply never had one ticked (fresh, badly authored).

    Returns ``{"ok": bool, "findings": [str, ...], "mid_execution": bool}``.
    ``mid_execution`` reflects the literal checked-count discriminator
    (checked > 0); the broader legacy exemption above is folded into ``ok``
    only, so callers reading ``mid_execution`` see the documented signal
    unchanged. Never raises — this is a backstop, not a new failure surface —
    but "never raises" is NOT "always passes": failures degrade by KIND.

    - **Plan-side failure** (unreadable plan file, unparseable checkbox
      counts): fail-open, ``ok: True`` — the plan's own imperfection is
      governed by the findings pipeline, and a missing plan is caught by
      the routing layer.
    - **Infrastructure failure** (validate-plan.py loader crash / import
      error — the gate MACHINERY is broken): degrades LOUDLY to a
      ``[ERROR] (infrastructure)`` finding + a ``_diag`` breadcrumb +
      ``infrastructure_error: True``, with ``ok`` honoring the SAME
      exemption discriminator as a structural ERROR (fresh plan refuses,
      mid-execution/legacy plan warns). A silent ``ok: True`` here once
      disarmed this gate repo-wide with zero signal when the flat
      ``lazy_core.py`` was deleted (see
      docs/bugs/plan-structural-backstop-silent-disarm-on-infrastructure-failure).
    """
    try:
        plan_text = Path(plan_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"ok": True, "findings": [], "mid_execution": False}
    try:
        unchecked, checked = _plan_wu_checkbox_counts(plan_text)
    except Exception:  # noqa: BLE001 — a backstop must never itself halt the pipeline
        unchecked, checked = 0, 0
    mid_execution = bool(checked)
    legacy_no_checkboxes = (unchecked == 0 and checked == 0)
    exempt = mid_execution or legacy_no_checkboxes
    try:
        vp_mod = _load_validate_plan_module()
        lines, exit_code = vp_mod.run_structural_checks(str(plan_path))
    except Exception as exc:  # noqa: BLE001 — never raises; degrade LOUDLY
        # Gate machinery broken (validate-plan.py missing/unimportable) —
        # never a silent pass (see the docstring's failure-kind contract).
        # run_structural_checks itself reports a lazy_core import failure as
        # its own infrastructure ERROR finding, so this branch covers only
        # the validate-plan.py loader itself.
        finding = (
            f"[ERROR] (infrastructure) plan-structure gate machinery failed "
            f"to load/run (validate-plan.py) — plan NOT validated: "
            f"{type(exc).__name__}: {exc}"
        )
        _diag(f"plan-structural-backstop infrastructure failure: {finding}")
        return {
            "ok": bool(exempt),
            "findings": [finding],
            "mid_execution": mid_execution,
            "infrastructure_error": True,
        }
    has_error = exit_code == 1
    ok = (not has_error) or exempt
    return {"ok": ok, "findings": lines, "mid_execution": mid_execution}


def format_plan_structural_blocker(plan_path, findings: "list[str]") -> str:
    """BLOCKED.md body for a FRESH (zero ticked WUs) plan part that fails the
    plan-structure-authoring-gate structural checks at first ``/execute-plan``
    routing (Phase 4 pickup backstop). Never fires for a mid-execution plan
    (>= 1 ticked WU) — that case WARNs and proceeds, never blocking in-flight
    work (the ``format_unknown_dependency_blocker`` shape, for the same
    "loud, immediate validation failure instead of silent starvation" reason).
    """
    finding_lines = "\n".join(f"  {f}" for f in findings) or "  (no findings text)"
    return (
        "# Blocked — plan fails structural validation\n\n"
        "## Details\n\n"
        f"`{plan_path}` failed `validate-plan.py --structural` at first "
        "`/execute-plan` routing (plan-structure-authoring-gate Phase 4 pickup "
        "backstop). The plan has ZERO ticked work units (a fresh plan, not "
        "in-flight execution), so this is refused rather than warned.\n\n"
        f"Findings:\n{finding_lines}\n\n"
        "Classification: `blocker_kind: plan-structural-invalid`.\n\n"
        "## Recovery Suggestion\n\n"
        "Fix the plan part per the findings above (re-run `python3 "
        "user/scripts/validate-plan.py --structural <plan path>` to confirm "
        "clean), then neutralize/rename this BLOCKED.md.\n"
    )


def _plan_unchecked_wus_are_verification_only(plan_text: str) -> bool:
    """Return True iff every UNCHECKED ``- [ ] WU-N`` row in the plan body sits
    under a Runtime Verification / MCP Integration Test subsection.

    Preserves the verification-only-row exemption (the same one
    ``remaining_unchecked_are_verification_only`` applies to PHASES.md) but at
    the PLAN-WU granularity: a per-WU checkbox under a gate-owned
    ``**Runtime Verification**`` / ``## MCP Integration Test`` subsection is
    ticked by the Step-9 ``/mcp-test`` gate, NOT by ``/execute-plan``, so it must
    not fail the plan-part ``deliverables_done`` verdict.

    Reuses ``remaining_unchecked_are_verification_only`` over the plan body so the
    section-detection logic (markdown headings AND bold markers, fence-aware,
    Superseded-phase aware) is identical to the PHASES.md path — but only the
    ``- [ ] WU-N`` rows participate, because the underlying helper returns False
    on the FIRST unchecked ``- [ ]`` it sees outside a verification subsection,
    and an ISSUE-6-compliant plan body's only ``- [ ]`` rows ARE the WU rows plus
    any verification rows. (A stray non-WU ``- [ ]`` in the plan body would
    conservatively be treated as non-verification work — the safe direction.)
    """
    return remaining_unchecked_are_verification_only(plan_text)


def verify_ledger(repo_root: Path, spec_path: Path, plan_path: Path | None = None) -> dict:
    """Verify the four completion-ledger preconditions for a feature.

    Called by lazy-state.py and bug-state.py with ``--verify-ledger <spec_path>``
    as a scripted replacement for the five duplicated prose "completion ledger"
    guard blocks across the lazy skills (lazy/SKILL.md Step 4).

    Checks (evaluated in this exact order; ALL four are always computed):

    1. ``clean_tree`` — ``git -C <repo_root> status --short`` produces no output.
       An untracked, modified, or staged file means the feature's changes have
       not been fully committed. Any OSError or subprocess failure returns False.

    2. ``head_matches_origin`` — ``git rev-parse HEAD`` equals
       ``git rev-parse @{u}`` (the upstream tracking ref). A local commit that
       has not been pushed, or a repo with no upstream configured, returns False.

    3. ``plan_complete`` — at least one non-retro implementation plan exists AND
       every such plan has ``status: Complete`` in its frontmatter. Uses
       ``_has_any_complete_plan`` (at least one Complete) combined with
       ``find_implementation_plans`` (no non-Complete plans remain), which together
       are equivalent to "all plans exist and all are Complete". False when any
       plan has a non-Complete status.
       ABSENT-BY-DESIGN (harness-hardening-retro-fixes Phase 3): a feature with
       NO implementation plan on disk and none required (only ``realign-*.md`` /
       ``retro-*.md``, or no plans at all — ``_implementation_plans_exist`` is
       False) is treated as plan_complete=True (a diagnostic notes it fired),
       NOT a false-alarm False. A feature WITH an incomplete implementation plan
       still returns False (the regression guard). Feature-level only — the
       plan-SCOPED branch reads the named plan's own status and is unaffected.

    4. ``deliverables_done`` — zero real (non-verification) unchecked
       deliverables remain. The SURFACE this reads depends on scope (see below).
       "Real" / verification-exempt is defined by
       ``remaining_unchecked_are_verification_only``: rows under a
       "Runtime Verification / MCP Integration Test" subsection heading are
       exempt workstation-only checks ticked by the Step-9 ``/mcp-test`` gate.

    Plan-scoped mode (``plan_path`` given) — deliverables_done SOURCE OF TRUTH
    (2026-06-15, d8-effect-chains review
    ``docs/features/audio/audio-vision/domains/d8-effect-chains/LAZY_BATCH_REVIEW_2026-06-15.md``):
      Multi-part plans split one feature across several plan files (each with a
      ``phases:`` set). Feature-level checks 3 + 4 fire false alarms while later
      parts are legitimately pending. When ``plan_path`` is provided, checks 3
      and 4 narrow to THAT plan's scope; checks 1 and 2 are unchanged:
        - ``plan_complete`` = THIS plan's frontmatter ``status:`` == ``Complete``
          (read via ``_plan_status`` — the same parser ``find_implementation_plans``
          and the stale-flip logic use). A missing ``plan_path`` file parses to the
          legacy default ``Ready`` → False.
        - ``deliverables_done`` reads the PLAN PART's own per-WU checkboxes
          (``- [ ] WU-N`` — mandatory since write-plan ISSUE-6) as the MACHINE
          record, NOT the PHASES.md phase-level deliverable rows. The plan part is
          the unit of execution and its WUs never span parts or phases, so this
          eliminates BOTH false-fail classes the PHASES-scoped read suffered:
          (a) cross-part — a phase-level deliverable belonging to part-3 failing
          the part-2 check (a phase spans parts); (b) cross-phase attribution — a
          deliverable filed under Phase 5 but built in corrective Phase 6 sitting
          done-but-unticked. Done iff no unchecked ``- [ ] WU-N`` rows remain,
          with the verification-only exemption applied at the WU level
          (``_plan_unchecked_wus_are_verification_only``).
        - LEGACY FALLBACK: a pre-ISSUE-6 plan with NO parseable per-WU checkboxes
          falls back to the prior PHASES-phase-level behavior (scoped to the
          plan's ``phases:``; or feature-level when the plan has no ``phases:`` —
          unknown scope must not vacuously pass) and records
          ``deliverables_source: "phases-fallback (legacy plan — no per-WU
          checkboxes)"`` so the operator knows the legacy path fired. Legacy plans
          are NOT hard-failed.
      ``plan_path=None`` → byte-for-byte the original feature-level behavior
      (the whole feature's PHASES.md via ``count_deliverables`` +
      ``remaining_unchecked_are_verification_only``). If PHASES.md does not exist
      at feature level, returns False (no evidence phases were completed).

    Return shape:
    ```
    {
        "ok": bool,                  # True iff ALL four checks are True
        "failing_check": str | None, # First False check key (order above), or None
        "checks": {
            "clean_tree": bool,
            "head_matches_origin": bool,
            "plan_complete": bool,
            "deliverables_done": bool,
        },
        "deliverables_source": str,  # diagnostic (additive, never gates):
                                     #   "plan-wu-checkboxes"       — new machine record
                                     #   "phases-fallback (…)"      — legacy plan path fired
                                     #   "phases-feature-level"     — no plan_path (whole feature)
        "failing_detail": dict,      # diagnostic (additive, never gates) — the
                                     # offending items for EVERY False check,
                                     # keyed by check name; {} when ok is True
                                     # (completion-gate-refusal-opacity):
                                     #   clean_tree -> {dirty_files: [...], total_count, git_error?}
                                     #   head_matches_origin -> {no_upstream, head_sha?, upstream_sha?, ahead?, behind?}
                                     #   plan_complete -> scoped: {plan_file, plan_status}
                                     #                    feature-level: {incomplete_plans: [{file, status}], total_count}
                                     #   deliverables_done -> {rows: [{line, text}], total, note?}
    }
    ```

    ``ok`` is True only when all four checks are True. ``failing_check`` names
    the FIRST False check in the defined order; None when ok is True. All four
    ``checks`` values are always populated and accurate regardless of which check
    fails first — no short-circuit pruning is applied to the ``checks`` dict.
    """
    # --- arg normalization: accept a SPEC.md file OR the spec directory ---
    # `spec_path` is contractually the feature/bug DIRECTORY (checks below compute
    # `spec_path / 'PHASES.md'` and scan the dir for plans). But the cycle-prompt
    # metavar reads as the SPEC.md FILE (`--verify-ledger <spec_path>`), so callers
    # legitimately pass `.../SPEC.md`. Passing the file used to yield a MISLEADING
    # verdict (phantom `.../SPEC.md/PHASES.md`) instead of an error. Normalize a
    # `.md` file arg to its parent directory at the SOURCE so the function and every
    # caller agree by construction — including direct callers and any future one
    # (bug `verify-ledger-planning-scope-and-file-arg`). `lazy-state.py` already
    # performs the same normalization at its wrapper; this is idempotent for a dir
    # arg (no `.md` suffix → unchanged) and harmless downstream of that wrapper.
    if spec_path.suffix == ".md":
        spec_path = spec_path.parent

    # --- check 1: clean working tree ---
    # Mirror the subprocess style used in _current_head in lazy-state.py:
    # capture_output + text + timeout guard, catch OSError/SubprocessError.
    # `_clean_tree_stdout` / `_clean_tree_errored` are retained (not just the
    # boolean) so a False verdict's failing_detail can name the dirty files
    # instead of discarding the already-captured `git status --short` output
    # (completion-gate-refusal-opacity Fix Scope §1).
    _clean_tree_stdout = ""
    _clean_tree_errored = False
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        clean_tree = result.stdout.strip() == ""
        _clean_tree_stdout = result.stdout
    except (OSError, subprocess.SubprocessError):
        clean_tree = False
        _clean_tree_errored = True

    # --- check 2: HEAD matches upstream tracking ref ---
    # Both rev-parse commands must succeed and return identical SHA strings.
    # `_head_sha` / `_upstream_sha` / `_no_upstream` are retained for the
    # failing_detail payload (short shas + an explicit no-upstream
    # discriminator, distinct from a genuine divergence).
    _head_sha = ""
    _upstream_sha = ""
    _no_upstream = True
    try:
        head_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        upstream_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "@{u}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if head_result.returncode == 0 and upstream_result.returncode == 0:
            head_sha = head_result.stdout.strip()
            upstream_sha = upstream_result.stdout.strip()
            head_matches_origin = bool(head_sha and upstream_sha and head_sha == upstream_sha)
            _head_sha, _upstream_sha, _no_upstream = head_sha, upstream_sha, False
        else:
            # @{u} can fail when no upstream is configured — treat as mismatch.
            head_matches_origin = False
            _head_sha = head_result.stdout.strip() if head_result.returncode == 0 else ""
            _no_upstream = upstream_result.returncode != 0
    except (OSError, subprocess.SubprocessError):
        head_matches_origin = False

    # --- Plan scope (Phase 9 WU-3): None → feature-level (original behavior) ---
    # When plan_path is given, checks 3 + 4 narrow to that plan's declared phase
    # set. An empty phase set (no `phases:`) means unknown scope → fall back to
    # the feature-level deliverables_done semantics below.
    scoped = plan_path is not None
    plan_phase_set: set[int] = _plan_phase_set(plan_path) if scoped else set()

    # --- check 3: implementation plan(s) Complete ---
    if scoped:
        # Plan-scoped: ONLY this plan's own frontmatter status matters. Read it
        # via _plan_status (the same parser find_implementation_plans uses); a
        # missing plan_path file parses to the legacy default "Ready" → not
        # Complete → False.
        plan_complete = _plan_status(plan_path) == "Complete"
    else:
        # Feature-level: every implementation plan must be Complete (≥1 exists).
        # _has_any_complete_plan: at least one plan has status: Complete.
        # find_implementation_plans: returns only non-Complete plans.
        # Together: any_complete AND no_incomplete → all plans Complete (and ≥1).
        any_complete = _has_any_complete_plan(spec_path)
        incomplete_plans = find_implementation_plans(spec_path)
        plan_complete = any_complete and len(incomplete_plans) == 0
        # --- absent-by-design (harness-hardening-retro-fixes Phase 3, WU-1) ---
        # A plan-less / realign-plan-only feature has NO implementation plan and
        # never needed one. The rule above returns False for it (any_complete is
        # False — there is no Complete IMPLEMENTATION plan), producing a
        # benign-but-noisy false-alarm plan_complete:false + recovery chase.
        # Distinguish absent-by-design (no implementation plan present, none
        # required) from incomplete (an implementation plan exists but is not
        # Complete): when there are zero incomplete plans AND no Complete plan
        # AND genuinely NO implementation plan on disk (only realign-*/retro-*,
        # or no plans at all — _implementation_plans_exist is False), treat
        # plan_complete as True (absent-by-design). A feature WITH an incomplete
        # implementation plan keeps plan_complete=False (the regression guard) —
        # _implementation_plans_exist is True in that case.
        if not plan_complete and len(incomplete_plans) == 0 and not any_complete:
            if not _implementation_plans_exist(spec_path):
                plan_complete = True
                _diag(
                    "plan_complete: no implementation plan required "
                    "(absent-by-design)"
                )

    # --- check 4: no real (non-verification) unchecked deliverables ---
    #
    # SOURCE OF TRUTH (2026-06-15 — d8-effect-chains review):
    #   * Plan-scoped (``plan_path`` given): the PLAN PART's own per-WU
    #     checkboxes (``- [ ] WU-N`` — mandatory since write-plan ISSUE-6) are
    #     the machine record. The plan part is the unit of execution and its WUs
    #     never span parts or phases, so reading them eliminates BOTH the
    #     cross-part false-fail (a Phase-5 deliverable belonging to part-3 failing
    #     the part-2 check) AND the cross-phase-attribution false-fail (a
    #     deliverable filed under Phase 5 but built in corrective Phase 6 sitting
    #     done-but-unticked). PHASES.md per-deliverable ticks are now
    #     human-readable documentation, NOT the gate.
    #   * Legacy fallback: a pre-ISSUE-6 plan with NO parseable per-WU checkboxes
    #     falls back to the prior PHASES-phase-level behavior and records
    #     ``deliverables_source`` so the operator knows the legacy path fired.
    #   * Feature-level (no ``plan_path`` — used by /mcp-test cycles): unchanged;
    #     it legitimately checks the whole feature's PHASES.md.
    phases_file = spec_path / "PHASES.md"
    # Diagnostic: which surface produced the deliverables_done verdict.
    deliverables_source = "phases-feature-level"
    if scoped:
        # Plan-scoped: prefer the plan part's own per-WU checkboxes.
        plan_text = ""
        if plan_path is not None and plan_path.exists():
            try:
                plan_text = plan_path.read_text(encoding="utf-8")
            except OSError:
                plan_text = ""
        wu_unchecked, wu_checked = _plan_wu_checkbox_counts(plan_text)
        if wu_unchecked or wu_checked:
            # ISSUE-6-compliant plan: the per-WU checkboxes ARE the machine
            # record. Done iff no unchecked WU rows remain — with the
            # verification-only exemption (a WU row under a Runtime Verification /
            # MCP Integration Test subsection is ticked by the Step-9 /mcp-test
            # gate, not by /execute-plan).
            deliverables_source = "plan-wu-checkboxes"
            if wu_unchecked == 0:
                deliverables_done = True
            else:
                deliverables_done = _plan_unchecked_wus_are_verification_only(plan_text)
        else:
            # Legacy pre-ISSUE-6 plan (no per-WU checkboxes): fall back to the
            # PHASES-phase-level behavior, scoped to the plan's phases. Emit a
            # diagnostic so the operator knows the legacy path fired.
            deliverables_source = "phases-fallback (legacy plan — no per-WU checkboxes)"
            if not phases_file.exists():
                deliverables_done = False
            else:
                phases_text = phases_file.read_text(encoding="utf-8")
                if plan_phase_set:
                    in_scope_unchecked = _unchecked_wus_in_plan_scope(phases_text, plan_phase_set)
                    if not in_scope_unchecked:
                        deliverables_done = True
                    else:
                        scoped_text = _phases_text_scoped_to(phases_text, plan_phase_set)
                        deliverables_done = remaining_unchecked_are_verification_only(scoped_text)
                else:
                    # Legacy plan with NO `phases:` set → unknown scope → must NOT
                    # vacuously pass; use feature-level semantics over all of PHASES.
                    unchecked, _checked = count_deliverables(phases_text)
                    if unchecked == 0:
                        deliverables_done = True
                    else:
                        deliverables_done = remaining_unchecked_are_verification_only(phases_text)
    else:
        # Feature-level (no plan_path): the whole feature's PHASES.md.
        if not phases_file.exists():
            # No PHASES.md means we have no evidence of phases being completed.
            deliverables_done = False
        else:
            phases_text = phases_file.read_text(encoding="utf-8")
            unchecked, _checked = count_deliverables(phases_text)
            if unchecked == 0:
                deliverables_done = True
            else:
                # Remaining unchecked rows may be exempted if they are all under
                # a Runtime Verification / MCP Integration Test subsection.
                deliverables_done = remaining_unchecked_are_verification_only(phases_text)

    # --- assemble result: determine first failing check in defined order ---
    checks = {
        "clean_tree": clean_tree,
        "head_matches_origin": head_matches_origin,
        "plan_complete": plan_complete,
        "deliverables_done": deliverables_done,
    }
    failing_check: str | None = None
    for key in ("clean_tree", "head_matches_origin", "plan_complete", "deliverables_done"):
        if not checks[key]:
            failing_check = key
            break

    # --- failing_detail (completion-gate-refusal-opacity, Fix Scope §1) ---
    # Populate the offending items for EVERY False check (not just the first),
    # so a single probe is diagnostic on every axis instead of the
    # orchestrator fixing one check and re-probing for the next. Additive
    # only — `ok`/`failing_check`/`checks`/`deliverables_source` are
    # byte-identical to before; an `ok: true` payload carries an empty dict.
    failing_detail: dict = {}
    if not clean_tree:
        dirty_lines = [ln for ln in _clean_tree_stdout.splitlines() if ln.strip()]
        detail_ct: dict = {
            "dirty_files": dirty_lines[:_DETAIL_MAX_ITEMS],
            "total_count": len(dirty_lines),
        }
        if _clean_tree_errored:
            detail_ct["git_error"] = True
        failing_detail["clean_tree"] = detail_ct
    if not head_matches_origin:
        detail_hm: dict = {"no_upstream": _no_upstream}
        if _head_sha:
            detail_hm["head_sha"] = _head_sha[:12]
        if not _no_upstream and _upstream_sha:
            detail_hm["upstream_sha"] = _upstream_sha[:12]
            try:
                lr = subprocess.run(
                    ["git", "-C", str(repo_root), "rev-list", "--left-right",
                     "--count", "@{u}...HEAD"],
                    capture_output=True, text=True, timeout=30,
                )
                if lr.returncode == 0:
                    parts = lr.stdout.split()
                    if len(parts) == 2:
                        detail_hm["behind"] = int(parts[0])
                        detail_hm["ahead"] = int(parts[1])
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        failing_detail["head_matches_origin"] = detail_hm
    if not plan_complete:
        if scoped:
            failing_detail["plan_complete"] = {
                "plan_file": plan_path.name if plan_path is not None else None,
                "plan_status": _plan_status(plan_path) if plan_path is not None else None,
            }
        else:
            failing_detail["plan_complete"] = {
                "incomplete_plans": [
                    {"file": p.name, "status": _plan_status(p)}
                    for p in incomplete_plans[:_DETAIL_MAX_ITEMS]
                ],
                "total_count": len(incomplete_plans),
            }
    if not deliverables_done:
        if deliverables_source == "plan-wu-checkboxes":
            failing_detail["deliverables_done"] = _plan_wu_unchecked_row_detail(plan_text)
        elif phases_file.exists():
            # phases-fallback (legacy plan) or phases-feature-level: re-read
            # PHASES.md fresh here so this block never depends on which
            # branch above happened to bind `phases_text` — diagnostic-only,
            # on the refusal path (not a hot loop).
            _pt = phases_file.read_text(encoding="utf-8")
            _scope = plan_phase_set if (scoped and plan_phase_set) else None
            failing_detail["deliverables_done"] = _phases_unchecked_row_detail(_pt, phase_set=_scope)
        else:
            failing_detail["deliverables_done"] = {"rows": [], "total": 0, "note": "PHASES.md absent"}

    return {
        "ok": failing_check is None,
        "failing_check": failing_check,
        "checks": checks,
        # Diagnostic (additive — never gates): which surface produced the
        # deliverables_done verdict. "plan-wu-checkboxes" is the new machine
        # source of truth; the "phases-fallback …" / "phases-feature-level"
        # values mark the legacy / feature-level paths for the operator.
        "deliverables_source": deliverables_source,
        # Diagnostic (additive — never gates): the offending items for every
        # False check, keyed by check name. Empty dict when ok is True.
        "failing_detail": failing_detail,
    }


def summarize_failing_detail(result: dict) -> str:
    """Compact one-line summary of a ``verify_ledger`` refusal's
    ``failing_detail``, for the ``gate-refusal`` telemetry event
    (completion-gate-refusal-opacity Fix Scope §3 — lets incident mining
    distinguish "dirty tree: 1 stray log file" from "dirty tree: 14
    uncommitted source files" without transcript access). Returns ``""``
    when ``result["ok"]`` is True or ``failing_detail`` has no entry for
    ``result["failing_check"]``. Never raises — a malformed/legacy payload
    (missing keys) degrades to ``""``, never a telemetry-path exception.
    """
    check = result.get("failing_check")
    detail = (result.get("failing_detail") or {}).get(check) if check else None
    if not check or not isinstance(detail, dict):
        return ""
    try:
        if check == "clean_tree":
            total = detail.get("total_count", 0)
            files = detail.get("dirty_files") or []
            head = f" (first: {files[0]})" if files else ""
            return f"dirty tree: {total} file(s){head}"
        if check == "head_matches_origin":
            if detail.get("no_upstream"):
                return "no upstream configured"
            ahead, behind = detail.get("ahead"), detail.get("behind")
            if ahead is not None and behind is not None:
                return f"{ahead} ahead / {behind} behind upstream"
            return "HEAD does not match upstream"
        if check == "plan_complete":
            if "incomplete_plans" in detail:
                total = detail.get("total_count", 0)
                plans = detail.get("incomplete_plans") or []
                head = f" (first: {plans[0]['file']} — {plans[0]['status']})" if plans else ""
                return f"{total} incomplete plan(s){head}"
            return (
                f"plan {detail.get('plan_file')} not Complete "
                f"(status: {detail.get('plan_status')})"
            )
        if check == "deliverables_done":
            total = detail.get("total", 0)
            rows = detail.get("rows") or []
            if rows:
                head = f" (first: {rows[0]['text']})"
            elif detail.get("note"):
                head = f" ({detail['note']})"
            else:
                head = ""
            return f"{total} unchecked row(s){head}"
    except (KeyError, IndexError, TypeError):
        return ""
    return ""


# lazy-core-package-decomposition Phase 5 WU-3 (residue sweep): the validation
# escalation ladder, the completion receipt writers (has_completion_receipt /
# write_completed_receipt), archive_fixed (the bug archive-on-fix write path),
# and the Gate-1 MCP-coverage plane (gate_coverage + _parse_locked_decisions)
# moved here from _monolith.py — verbatim (the completion write-path plane).

# ---------------------------------------------------------------------------
# Validation-escalation predicate (Phase 11 WU-1a)
# ---------------------------------------------------------------------------

# Suffix the Step-3 blocked terminal appends to notify_message when the
# escalation fires. Defined HERE (not in the state scripts) so lazy-state.py
# and bug-state.py emit the byte-identical message — the orchestrators key
# corrective-phase drafting discipline on this exact text.
#
# REWORDED (mcp-validation-peels-one-seam-per-loop Deferred Follow-Up item 2,
# closed by stale-runtime-health-200-false-blocked's STATE-lane pass): the
# full-chain seam-audit mandate was RE-SCOPED by that bug's SKILLS-lane fix to
# apply at EVERY mcp-validation retry_count (starting at the first failure,
# authored into BLOCKED.md's own body), not only here at retry_count >= 2. This
# predicate's THRESHOLD is unchanged (still exactly `retry_count >= 2` — see
# below); only the WORDING is corrected so `retry_count >= 2` reads as the
# ADDITIONAL /investigate-mandatory backstop tier layered on top of the
# standing seam-audit requirement, not as the sole trigger for seam enumeration
# (a documentation-accuracy edit only — no test asserts this string's exact
# wording, only that the notify_message carries the constant verbatim; see
# test_lazy_state_blocked_escalation_payload / test_bug_state_blocked_
# escalation_payload in test_lazy_core.py).
VALIDATION_ESCALATION_SUFFIX = (
    " ESCALATION: 2+ validation failures — /investigate is now MANDATORY "
    "before the next corrective phase (the full-chain seam audit itself is "
    "required starting at the FIRST mcp-validation failure, not gated on "
    "this threshold)."
)


def validation_escalation(meta: dict[str, Any] | None) -> bool:
    """Return True when a BLOCKED.md sentinel shows repeated MCP-validation failure.

    Single source of truth for the Phase 11 WU-1a escalation policy, consumed
    by BOTH state scripts' Step-3 blocked terminals: ``blocker_kind ==
    "mcp-validation"`` AND ``retry_count >= 2``. The threshold is 2 because the
    d8-live-looping pattern showed each BLOCKED→add-phase round discovering
    exactly ONE more broken layer.

    REWORDED (mcp-validation-peels-one-seam-per-loop): this predicate's
    BEHAVIOR is unchanged — still exactly ``retry_count >= 2``. What changed is
    what firing MEANS: the full-chain seam-audit requirement itself now applies
    at every ``mcp-validation`` retry_count (the SKILLS-lane prose mandate,
    authored starting at the first failure); this predicate firing True marks
    the point past which ``/investigate`` is ADDITIONALLY mandatory before the
    next corrective phase — the backstop tier, not the sole seam-enumeration
    trigger.

    Tolerances (backward compatibility — pre-Phase-11 sentinels must never
    escalate or crash):
      - ``retry_count`` as an int is used directly.
      - ``retry_count`` as a string of digits (quoted YAML) is coerced.
      - Missing/malformed ``retry_count``, missing ``blocker_kind``, a non-
        mcp-validation ``blocker_kind``, or a None/empty meta → False.
      - YAML booleans are ints in Python (``True == 1``); they are NOT counts,
        so bool values are explicitly rejected rather than coerced.
    """
    meta = meta or {}
    if meta.get("blocker_kind") != "mcp-validation":
        return False
    raw = meta.get("retry_count")
    # bool is an int subclass — `retry_count: true` must not coerce to 1.
    if isinstance(raw, bool):
        return False
    if isinstance(raw, int):
        return raw >= 2
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip()) >= 2
    # Missing or malformed → no escalation (never crash the blocked terminal).
    return False


def spike_escalation(meta: dict[str, Any] | None) -> bool:
    """Return True when a BLOCKED.md sentinel shows repeated spike-verdict failure.

    spike-pipeline-role Phase 2 (WU-2) mirror of ``validation_escalation`` above,
    for the tooling-round escalation signal consumed by Part 3's tooling-round
    cap. This predicate is NOT itself a gate on the blocked→spike routing (that
    routing fires unconditionally on the blocker_kind, see the Step-3 BLOCKED
    block in ``compute_state``) — it is a separate signal a caller consults to
    decide whether repeated spike-tooling-round failures warrant escalation.

    Gated on ``blocker_kind == "runtime-spike-verdict-pending"`` AND
    ``retry_count >= 2`` — same threshold as ``validation_escalation``, for the
    same reason: each retry round is expected to make exactly one more round of
    progress before escalation is warranted.

    Tolerances (mirrors ``validation_escalation`` exactly):
      - ``retry_count`` as an int is used directly.
      - ``retry_count`` as a string of digits (quoted YAML) is coerced.
      - Missing/malformed ``retry_count``, missing ``blocker_kind``, a non-
        runtime-spike-verdict-pending ``blocker_kind``, or a None/empty meta →
        False.
      - YAML booleans are ints in Python (``True == 1``); they are NOT counts,
        so bool values are explicitly rejected rather than coerced.
    """
    meta = meta or {}
    if meta.get("blocker_kind") != "runtime-spike-verdict-pending":
        return False
    raw = meta.get("retry_count")
    # bool is an int subclass — `retry_count: true` must not coerce to 1.
    if isinstance(raw, bool):
        return False
    if isinstance(raw, int):
        return raw >= 2
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip()) >= 2
    # Missing or malformed → no escalation (never crash the blocked terminal).
    return False


# spike-pipeline-role Phase 4 (WU-2): the machine-enforced bound on the Spike
# tooling-existence loop. Operator-tunable default cap — SPEC Open Question 2.
_SPIKE_TOOLING_ROUNDS_CAP = 3


def spike_tooling_cap_exceeded(meta: dict[str, Any] | None, cap: int | None = None) -> bool:
    """Return True when ``spike_tooling_rounds`` has reached/exceeded the cap.

    spike-pipeline-role Phase 4 (WU-2) — the machine-enforced BOUND on the
    Spike tooling-existence loop (SPEC "The tooling-existence loop (bounded)" /
    "Loop guard (bound)"). Mirrors ``spike_escalation``'s tolerance shape
    exactly, but is a PURE count check reused across two routing seams that
    read different sentinels (BLOCKED.md's Step-3 blocked-resolver and
    SPIKE_VERDICT.md's Step-9.5 header gate) — so, unlike ``spike_escalation``,
    it does NOT gate on ``blocker_kind``.

    Tolerances (identical to ``spike_escalation``):
      - ``spike_tooling_rounds`` as an int is used directly.
      - ``spike_tooling_rounds`` as a string of digits (quoted YAML) is coerced.
      - Missing/malformed ``spike_tooling_rounds``, or a None/empty meta → False.
      - YAML booleans are ints in Python (``True == 1``); they are NOT counts,
        so bool values are explicitly rejected (checked BEFORE the int check,
        since bool is an int subclass) rather than coerced.
    """
    meta = meta or {}
    cap = _SPIKE_TOOLING_ROUNDS_CAP if cap is None else cap
    raw = meta.get("spike_tooling_rounds")
    # bool is an int subclass — `spike_tooling_rounds: true` must not coerce to 1.
    if isinstance(raw, bool):
        return False
    if isinstance(raw, int):
        rounds = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        rounds = int(raw.strip())
    else:
        # Missing or malformed → never exceeds the cap (never crash a caller).
        return False
    return rounds >= cap


# ---------------------------------------------------------------------------
# SPEC parsing helpers
# ---------------------------------------------------------------------------

def has_completion_receipt(spec_path: Path | None, filename: str = "COMPLETED.md") -> bool:
    """True iff a durable, content-valid completion receipt exists in the feature/bug dir.

    The receipt is written ONLY by ``__mark_complete__``'s completion-integrity
    gate (or backfilled with ``provenance: backfilled-unverified``). Its presence
    AND content validity are the structural proof that a feature reached
    ``Complete`` THROUGH the pipeline gate rather than via an out-of-band
    SPEC/ROADMAP edit. See _components/completion-integrity-gate.md.

    Content-validation contract:
    - ``spec_path is None`` → ``False`` (silently; no directory to check).
    - Receipt file absent → ``False`` (silently; normal not-yet-complete case).
    - Receipt file present but MALFORMED → ``False`` + emit a ``_diag()``
      diagnostic naming the path and the specific defect. Malformed means any of:
        * empty file / no YAML frontmatter (``parse_sentinel`` returns ``{}``)
        * ``kind`` key absent from frontmatter
        * ``kind`` value not in ``{"completed", "fixed"}``
        * ``provenance`` key absent or its value is empty/whitespace
      These cases count as "completion-unverified" and halt the gate just as if
      the file were absent, while producing a loud diagnostic so the issue can
      be investigated.
    - Receipt file present and valid → ``True``.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    Default receipt filename is ``COMPLETED.md`` — matches current behavior.
    Bug-state.py passes ``filename="FIXED.md"`` for the bug receipt convention.
    """
    if spec_path is None:
        return False

    receipt_path = spec_path / filename
    if not receipt_path.exists():
        # Normal not-yet-complete case — absence is silent, not a diagnostic.
        return False

    # Receipt file exists — validate its content before trusting it.
    meta = parse_sentinel(receipt_path)

    if meta is None:
        # parse_sentinel calls _die() internally for fatal parse errors; this
        # branch is a safety net in case it ever returns None without dying.
        _diag(
            f"completion receipt at {receipt_path} could not be parsed"
            " (parse_sentinel returned None) — treating as missing"
        )
        return False

    # Empty dict means the file existed but had no YAML frontmatter fence at all.
    if not meta:
        _diag(
            f"completion receipt at {receipt_path} has no YAML frontmatter"
            " — treating as missing (expected '---' fence with kind + provenance)"
        )
        return False

    # Validate 'kind' field.
    kind = meta.get("kind")
    if kind not in {"completed", "fixed"}:
        _diag(
            f"completion receipt at {receipt_path} has invalid or missing 'kind'"
            f" (got {kind!r}; expected 'completed' or 'fixed')"
            " — treating as missing"
        )
        return False

    # Validate 'provenance' field — must be present and non-empty.
    provenance = meta.get("provenance")
    if not provenance or not str(provenance).strip():
        _diag(
            f"completion receipt at {receipt_path} is missing or has empty 'provenance'"
            f" (got {provenance!r})"
            " — treating as missing (provenance is required to trust the receipt)"
        )
        return False

    return True


def write_completed_receipt(
    path: Path,
    feature_id: str,
    date: str,
    *,
    provenance: str,
    kind: str = "completed",
    completed_commit: str | None = None,
    validated_via: str | None = None,
    mcp_pass_count: int | None = None,
    mcp_total_count: int | None = None,
    auto_ticked_rows: int | None = None,
    body_note: str = "",
) -> None:
    """Write a completion receipt (kind: completed by default) per sentinel-frontmatter.md.

    ``provenance: gated`` is written by the completion-integrity gate at flip
    time; ``provenance: backfilled-unverified`` is written by --backfill-receipts
    for features grandfathered in during the receipt-gating rollout.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    The ``kind: completed`` value and the ``# Completion Receipt`` title are
    the defaults that preserve byte-for-byte behavior at all existing call sites.

    ``kind`` is keyword-only and defaults to ``"completed"`` so that lazy-state.py's
    feature pipeline behavior is unchanged.  bug-state.py passes ``kind="fixed"``
    so that FIXED.md receipts carry the correct ``kind: fixed`` frontmatter value
    required by the Phase-5 consistency checker.
    """
    lines = [
        "---",
        f"kind: {kind}",
        f"feature_id: {feature_id}",
        f"date: {date}",
        f"provenance: {provenance}",
    ]
    if completed_commit:
        lines.append(f"completed_commit: {completed_commit}")
    if validated_via:
        lines.append(f"validated_via: {validated_via}")
    if mcp_pass_count is not None and mcp_total_count is not None:
        lines.append(f"mcp_pass_count: {mcp_pass_count}")
        lines.append(f"mcp_total_count: {mcp_total_count}")
    # auto_ticked_rows: how many unchecked verification rows the evidence-gated
    # completion gate auto-ticked this completion (completion-coherence-gate-
    # reconciliation Phase 3). Omitted when None (legacy / --backfill callers);
    # 0 is recorded explicitly so an auditor can tell "gate ran, ticked nothing"
    # from "gate did not run".
    if auto_ticked_rows is not None:
        lines.append(f"auto_ticked_rows: {auto_ticked_rows}")
    lines.append("---")
    lines.append("")
    lines.append("# Completion Receipt")
    lines.append("")
    if body_note:
        lines.append(body_note)
        lines.append("")
    _atomic_write(path, "\n".join(lines))

def archive_fixed(
    repo_root: Path,
    spec_path: Path,
    *,
    date: str | None = None,
) -> dict:
    """Archive a Fixed bug directory: the deterministic successor to the prose
    archive mechanics in mark-fixed-archive.md Steps 1–5.

    Why this is script-owned (2026-06-10 incident): the orchestrator performing
    these steps as prose improvised through three consecutive failures — a
    `git mv` refused because apply_pseudo's sentinel deletions were unstaged
    (tracked-but-missing files inside the dir), a transient Windows
    "Permission denied" on the directory rename, and a repo-wide `grep -r`
    crawling node_modules. Each is handled deterministically here.

    Steps (all best-effort idempotent; safe to re-run after a partial failure):
      1. Gate: FIXED.md receipt present (kind: fixed) — or SPEC ``**Status:**
         Won't-fix`` (receipt-exempt). If spec_path is already gone and the
         archive destination exists, treat as a RESUME: skip to step 5.
      2. SPEC.md evidence header lines: ensure ``**Fixed:** <date>`` and
         ``**Fix commit:** <short sha>`` after ``**Discovered:**`` (fallback:
         after ``**Status:**``), updating them if already present.
      3. ``git add -A <spec_path>`` — stages the receipt, status flips, AND the
         sentinel deletions so the index is coherent before the move (the exact
         precondition the prose flow missed).
      4. ``git mv <spec_path> docs/bugs/_archive/<bug_id>`` with retry/backoff
         (1s/2s/4s — Windows transient handle locks), then a per-file
         ``git mv`` fallback if the directory rename never succeeds. A name
         collision in _archive/ gets a ``-archived-<date>`` suffix.
      5. Repoint inbound references: ``git grep -l`` (tracked files only — never
         node_modules/target) for ``docs/bugs/<bug_id>/`` across ``*.md``,
         replacing with ``docs/bugs/_archive/<bug_id>/``.
      6. Remove the bug's entry from docs/bugs/queue.json (matched on
         ``spec_dir`` or ``id``).
      7. Stage the touched paths and commit:
         ``fix(<bug_id>): mark fixed and archive — FIXED.md receipt gated``.

    Return shape (callers may JSON-dump unconditionally)::

        {
            "name": "archive_fixed",
            "ok": bool,
            "refused": str | None,   # non-None → nothing irreversible was done,
                                     #   OR a partial-state diagnostic (see note)
            "noop": bool,            # True iff there was nothing left to do
            "archived_to": str | None,   # repo-relative destination
            "fix_commit": str | None,    # short sha recorded in SPEC.md
            "repointed": [str, ...],     # repo-relative files whose refs moved
            "queue_removed": bool,
            "fallback_used": bool,       # per-file git mv fallback engaged
            "committed": str | None,     # short sha of the archive commit
        }

    Partial-state note: a refusal AFTER the move (e.g. commit failure) names
    the completed steps so the consumer can surface an accurate BLOCKED.md;
    re-running resumes from the archive destination rather than redoing the
    move.
    """
    if date is None:
        date = datetime.date.today().isoformat()
    repo_root = repo_root.resolve()
    # Normalize spec_path to an ABSOLUTE path anchored at repo_root BEFORE any
    # `spec_path.relative_to(repo_root)` below (the per-file git-mv fallback at
    # ~L2104 that computes `rel_spec` for the repo-relative suffix strip). repo_root
    # is resolved to absolute just above, so a RELATIVE spec_path — e.g. the
    # repo-relative `docs/bugs/<id>` the CLI passes straight through as
    # `Path(args.archive_fixed)` — would make relative_to() raise an UNCAUGHT
    # ValueError (the try/except at the end of this fn catches only OSError /
    # SubprocessError), killing --archive-fixed with a raw traceback instead of a
    # structured refusal. Sibling gates (apply_pseudo/verify_ledger) never mix a
    # relative spec_path with an absolute repo_root in a relative_to() call, so they
    # were unaffected; this puts archive_fixed on the same footing. Anchoring a
    # relative spec_path at repo_root (not CWD) is the correct interpretation:
    # git ls-files output downstream is likewise repo-relative.
    spec_path = Path(spec_path)
    spec_path = (
        spec_path.resolve()
        if spec_path.is_absolute()
        else (repo_root / spec_path).resolve()
    )
    bug_id = spec_path.name
    result: dict[str, Any] = {
        "name": "archive_fixed",
        "ok": False,
        "refused": None,
        "noop": False,
        "archived_to": None,
        "fix_commit": None,
        "repointed": [],
        "queue_removed": False,
        "fallback_used": False,
        "committed": None,
    }

    def _refuse(msg: str) -> dict:
        result["refused"] = msg
        return result

    archive_parent = repo_root / "docs" / "bugs" / "_archive"
    dest = archive_parent / bug_id

    try:
        # --- step 1: gate / resume detection --------------------------------
        resume = False
        if not spec_path.exists():
            if dest.exists():
                # Prior run moved the directory but died before repoint/commit.
                resume = True
            else:
                return _refuse(
                    f"spec_path does not exist and no archive at "
                    f"{dest.relative_to(repo_root).as_posix()} — nothing to archive"
                )
        if not resume:
            receipt_ok = has_completion_receipt(spec_path, "FIXED.md")
            wont_fix = (spec_status(spec_path) or "").startswith("Won't-fix")
            if not receipt_ok and not wont_fix:
                return _refuse(
                    "no FIXED.md receipt (kind: fixed) and SPEC is not "
                    "Won't-fix — run `--apply-pseudo __mark_fixed__` first; "
                    "archive_fixed never writes the receipt itself"
                )

            # --- step 2: SPEC.md evidence header lines -----------------------
            # Short sha of the last work commit BEFORE the archive commit — the
            # load-bearing evidence of when the fix landed (mark-fixed-archive
            # Step 1). Skipped for Won't-fix (no receipt → no fix commit).
            if receipt_ok:
                sha_proc = _git(repo_root, "rev-parse", "--short", "HEAD")
                fix_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
                if fix_sha:
                    result["fix_commit"] = fix_sha
                    spec_md = spec_path / "SPEC.md"
                    if spec_md.exists():
                        text = spec_md.read_text(encoding="utf-8")
                        # Update-in-place when the lines already exist…
                        text = re.sub(
                            r"^\*\*Fixed:\*\*.*$", f"**Fixed:** {date}",
                            text, count=1, flags=re.MULTILINE,
                        )
                        text = re.sub(
                            r"^\*\*Fix commit:\*\*.*$", f"**Fix commit:** {fix_sha}",
                            text, count=1, flags=re.MULTILINE,
                        )
                        # …then insert any that are still missing, after
                        # **Discovered:** (canonical field order per
                        # docs/bugs/CLAUDE.md: Status → Severity → Discovered →
                        # Fixed → Fix commit), falling back to **Status:**.
                        missing = []
                        if not re.search(r"^\*\*Fixed:\*\*", text, flags=re.MULTILINE):
                            missing.append(f"**Fixed:** {date}")
                        if not re.search(r"^\*\*Fix commit:\*\*", text, flags=re.MULTILINE):
                            missing.append(f"**Fix commit:** {fix_sha}")
                        if missing:
                            anchor = re.search(
                                r"^\*\*Discovered:\*\*.*$", text, flags=re.MULTILINE
                            ) or re.search(
                                r"^\*\*Status:\*\*.*$", text, flags=re.MULTILINE
                            )
                            if anchor:
                                insert_at = anchor.end()
                                text = (
                                    text[:insert_at]
                                    + "".join("\n" + line for line in missing)
                                    + text[insert_at:]
                                )
                            else:
                                # No header block at all — append (degenerate
                                # SPEC; keep the evidence rather than dropping it).
                                text = text.rstrip("\n") + "\n\n" + "\n".join(missing) + "\n"
                        _atomic_write(spec_md, text)

            # --- step 3: stage the bug dir (deletions included) --------------
            add_proc = _git(repo_root, "add", "-A", "--", str(spec_path))
            if add_proc.returncode != 0:
                return _refuse(
                    f"git add -A {spec_path.name} failed: {add_proc.stderr.strip()}"
                )

            # --- step 4: git mv with retry + per-file fallback ---------------
            archive_parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = archive_parent / f"{bug_id}-archived-{date}"
                if dest.exists():
                    return _refuse(
                        f"archive collision: both {bug_id} and "
                        f"{dest.name} already exist under _archive/"
                    )
            mv_err = ""
            moved = False
            for attempt, delay in enumerate((0, 1, 2, 4)):
                if delay:
                    time.sleep(delay)  # transient Windows handle/lock backoff
                mv_proc = _git(repo_root, "mv", str(spec_path), str(dest))
                if mv_proc.returncode == 0:
                    moved = True
                    break
                mv_err = mv_proc.stderr.strip()
            if not moved:
                # Per-file fallback: move every tracked file individually so a
                # single locked file is isolated instead of failing the whole
                # directory rename.
                ls_proc = _git(
                    repo_root, "ls-files", "--", str(spec_path)
                )
                if ls_proc.returncode != 0:
                    return _refuse(
                        f"git mv failed after retries ({mv_err}) and ls-files "
                        f"fallback failed: {ls_proc.stderr.strip()}"
                    )
                rel_spec = spec_path.relative_to(repo_root).as_posix()
                failed_files = []
                for rel in ls_proc.stdout.splitlines():
                    rel = rel.strip()
                    if not rel:
                        continue
                    suffix = rel[len(rel_spec):].lstrip("/")
                    target = dest / suffix
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f_proc = _git(repo_root, "mv", rel, str(target))
                    if f_proc.returncode != 0:
                        failed_files.append(f"{rel}: {f_proc.stderr.strip()}")
                if failed_files:
                    return _refuse(
                        "per-file git mv fallback left files behind — "
                        "PARTIAL STATE, resolve the locks and re-run: "
                        + "; ".join(failed_files)
                    )
                result["fallback_used"] = True
                # Remove the now-empty source tree (best-effort).
                for dirpath, dirnames, filenames in os.walk(spec_path, topdown=False):
                    if not filenames and not dirnames:
                        try:
                            os.rmdir(dirpath)
                        except OSError:
                            pass
                moved = True

        result["archived_to"] = dest.relative_to(repo_root).as_posix()

        # --- step 5: repoint inbound references (tracked *.md only) ----------
        old_ref = f"docs/bugs/{bug_id}/"
        # NOTE: dest may carry the -archived-<date> suffix; repoint to the
        # actual destination, not the canonical name.
        new_ref = dest.relative_to(repo_root).as_posix() + "/"
        grep_proc = _git(repo_root, "grep", "-l", "-F", old_ref, "--", "*.md")
        # returncode 1 = no matches (fine); >1 = real error.
        if grep_proc.returncode > 1:
            return _refuse(
                f"archived to {result['archived_to']} but inbound-reference "
                f"scan failed: {grep_proc.stderr.strip()} — PARTIAL STATE, "
                "re-run to resume"
            )
        for rel in grep_proc.stdout.splitlines():
            rel = rel.strip()
            if not rel:
                continue
            ref_path = repo_root / rel
            try:
                content = ref_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if old_ref in content:
                _atomic_write(ref_path, content.replace(old_ref, new_ref))
                result["repointed"].append(rel)

        # --- step 6: trim queue.json ------------------------------------------
        queue_path = repo_root / "docs" / "bugs" / "queue.json"
        if queue_path.exists():
            try:
                data = json.loads(queue_path.read_text(encoding="utf-8"))
                items = data.get("queue", [])
                kept = [
                    e for e in items
                    if not (
                        isinstance(e, dict)
                        and (e.get("spec_dir") == bug_id or e.get("id") == bug_id)
                    )
                ]
                if len(kept) != len(items):
                    data["queue"] = kept
                    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
                    result["queue_removed"] = True
            except (json.JSONDecodeError, AttributeError) as exc:
                return _refuse(
                    f"archived to {result['archived_to']} but queue.json is "
                    f"malformed ({exc}) — PARTIAL STATE, fix queue.json and re-run"
                )

        # --- step 7: stage + commit -------------------------------------------
        to_stage = ["docs/bugs"] + result["repointed"]
        add_proc = _git(repo_root, "add", "-A", "--", *to_stage)
        if add_proc.returncode != 0:
            return _refuse(
                f"archived to {result['archived_to']} but final staging "
                f"failed: {add_proc.stderr.strip()} — PARTIAL STATE, re-run"
            )
        diff_proc = _git(repo_root, "diff", "--cached", "--quiet")
        if diff_proc.returncode == 0:
            # Nothing staged — a re-run after a fully-completed prior pass.
            result["ok"] = True
            result["noop"] = True
            return result
        commit_proc = _git(
            repo_root, "commit", "-m",
            f"fix({bug_id}): mark fixed and archive — FIXED.md receipt gated",
        )
        if commit_proc.returncode != 0:
            return _refuse(
                f"archived to {result['archived_to']} but commit failed: "
                f"{commit_proc.stderr.strip()} — PARTIAL STATE (changes are "
                "staged), commit manually or re-run"
            )
        sha_proc = _git(repo_root, "rev-parse", "--short", "HEAD")
        result["committed"] = (
            sha_proc.stdout.strip() if sha_proc.returncode == 0 else "unknown"
        )
        result["ok"] = True
        return result
    except (OSError, subprocess.SubprocessError) as exc:
        return _refuse(f"git unavailable or I/O failure: {exc}")

# ---------------------------------------------------------------------------
# gate_coverage — WU-2: deterministic, symlink-resolving Gate-1 verdict.
#
# Promotes the mcp-coverage-audit.md algorithm to code: enumerate the SPEC's
# Locked-Decision surface, grep mcp-tests/*.md (RESOLVING symlink / 64-byte
# pointer targets — the Windows blindspot), return covered/uncovered per
# decision.
# ---------------------------------------------------------------------------

# Words dropped when deriving keyword anchors from a decision title.
_GATE_COVERAGE_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "be", "by", "with", "from", "as", "at", "via", "uses", "use", "only",
    "decision", "must", "should", "will", "that", "this", "it",
})


def _gate_coverage_keywords(title: str) -> list[str]:
    """Extract the distinctive content words from a decision title (lowercased,
    stopwords dropped, deduped, order-preserved)."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", title.lower())
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        if w in _GATE_COVERAGE_STOPWORDS or len(w) < 3:
            continue
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _parse_locked_decisions(spec_md: str) -> list[dict]:
    """Parse the SPEC.md Locked-Decision surface into [{id, title, keywords}].

    Priority order (first surface that yields rows wins):
      1. ``## Locked Decisions`` H2 with a table whose first column is the id.
      2. ``## Resolved by Research`` H2 with ``- [x]`` bullets.
      3. ``## Key Decisions`` / ``## Design Decisions`` numbered block.
    Returns [] when no surface exists (caller passes vacuously).
    """
    lines = spec_md.splitlines()

    def _section_body(heading_res: list[str]) -> list[str] | None:
        for i, ln in enumerate(lines):
            for pat in heading_res:
                if re.match(pat, ln.strip(), re.IGNORECASE):
                    body: list[str] = []
                    for nxt in lines[i + 1:]:
                        if re.match(r"^##\s", nxt.strip()):
                            break
                        body.append(nxt)
                    return body
        return None

    decisions: list[dict] = []

    # --- Surface 1: ## Locked Decisions table ---
    body = _section_body([r"^##\s+Locked Decisions\b"])
    if body is not None:
        for ln in body:
            s = ln.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2:
                continue
            first = cells[0]
            title = cells[1]
            # Skip the header row and the |---|---| separator row. The header's
            # id column may be labelled 'id' / 'decision' / '#' / 'no' / 'num',
            # and its SECOND (Decision/title) column literally reads "Decision" —
            # key on the title-column header for robustness, not only the id
            # label. The observed canonical header '| # | Decision | Choice |
            # Source |' slipped the id-only skip (first == '#', not in the set)
            # and became a PHANTOM decision id='#', title='Decision' that could
            # never be covered → Gate 1 unsatisfiable (harden 2026-07).
            if (
                not first
                or set(first) <= set("-: ")
                or first.lower() in ("id", "decision", "#", "no", "num", "idx")
                or title.strip().lower() == "decision"
            ):
                continue
            did = first
            decisions.append(
                {"id": did, "title": title, "keywords": _gate_coverage_keywords(title)}
            )
        if decisions:
            return decisions

    # --- Surface 2: ## Resolved by Research checked bullets ---
    body = _section_body([r"^##\s+Resolved by Research\b"])
    if body is not None:
        idx = 0
        for ln in body:
            m = re.match(r"^\s*-\s*\[x\]\s+(.*)$", ln, re.IGNORECASE)
            if m:
                idx += 1
                title = m.group(1).strip()
                # Try to lift a leading id token (R1:, L2 —, etc.).
                idm = re.match(r"^([A-Z]\d+)\b[:\.\)\-\s]", title)
                did = idm.group(1) if idm else f"R{idx}"
                decisions.append(
                    {"id": did, "title": title,
                     "keywords": _gate_coverage_keywords(title)}
                )
        if decisions:
            return decisions

    # --- Surface 3: ## Key/Design Decisions numbered block ---
    body = _section_body([r"^##\s+Key Decisions\b", r"^##\s+Design Decisions\b"])
    if body is not None:
        idx = 0
        for ln in body:
            m = re.match(r"^\s*\d+[\.\)]\s+(.*)$", ln)
            if m:
                idx += 1
                title = m.group(1).strip()
                decisions.append(
                    {"id": f"K{idx}", "title": title,
                     "keywords": _gate_coverage_keywords(title)}
                )
        if decisions:
            return decisions

    return []


def _resolve_scenario_text(path: Path) -> str:
    """Read an mcp-tests/*.md scenario, RESOLVING symlink / 64-byte pointer
    targets (the Windows blindspot).

    On a real symlink, ``read_text`` already follows it. But git on Windows
    without symlink privilege writes a tiny TEXT file whose CONTENT is the
    relative target path (the "64-byte pointer file"). We detect that case: a
    small file whose entire content is a single relative path that resolves to
    an existing file → read the TARGET instead. Best-effort; never raises.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # Pointer-file heuristic: short, single-line, no newline-y markdown, and the
    # content resolves to an existing sibling file.
    stripped = raw.strip()
    if stripped and "\n" not in stripped and len(stripped) <= 260:
        # Looks path-like (has a separator or ends in .md) and is not prose.
        looks_pathish = (
            stripped.endswith(".md")
            and ("/" in stripped or "\\" in stripped or stripped == path.name)
            and " " not in stripped
        )
        if looks_pathish:
            candidate = (path.parent / stripped).resolve()
            if candidate.exists() and candidate.is_file() and candidate != path.resolve():
                try:
                    return candidate.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return raw
    return raw


def _parse_mcp_coverage_exemptions(spec_md: str) -> dict:
    """Parse a ``## MCP Coverage Exemptions`` SPEC section → {id: rationale}.

    This is the DETERMINISTIC home for the mcp-coverage-audit.md D7 disposition
    "documented-MCP-untestable decisions get an inline SPEC test-exempt note".
    Before this parser existed, ``gate_coverage`` had NO exemption path — a
    decision was coverable ONLY by an ``mcp-tests/*.md`` scenario reference — so
    the component's prescribed inline SPEC exempt note could not actually satisfy
    the gate (a backend/miniflare-verified Locked Decision, which has no Tauri
    MCP surface to drive, was permanently ``uncovered``). harden 2026-07.

    Recognized surface — an H2 ``## MCP Coverage Exemptions`` whose body carries
    bullets of the shape ``- <ID>: <rationale>`` (or ``- <ID> — <rationale>``).
    An entry counts ONLY when BOTH the id token and a NON-EMPTY rationale are
    present (mirroring the ``observation_gap_exemptions`` ``spec_class``-required
    discipline: the citation is what distinguishes a verified untestable-class
    assessment from a convenience skip). A bare ``- D4`` with no rationale is
    IGNORED (not exempt) so an empty stub cannot launder the gate.

    Returns ``{}`` when the section is absent (the gate is unchanged for every
    SPEC that does not opt in).
    """
    lines = spec_md.splitlines()
    exemptions: dict = {}
    in_section = False
    for ln in lines:
        s = ln.strip()
        if re.match(r"^##\s+MCP Coverage Exemptions\b", s, re.IGNORECASE):
            in_section = True
            continue
        if in_section and re.match(r"^##\s", s):
            break  # next H2 ends the section
        if not in_section:
            continue
        # ``- <ID>: <rationale>`` or ``- <ID> — <rationale>`` (id = leading
        # alnum token; rationale = the remainder after the : / — / - separator).
        m = re.match(r"^-\s+([A-Za-z]?\d+|[A-Za-z]{1,4}\d*)\s*[:—\-]\s*(.+\S)\s*$", s)
        if m:
            did = m.group(1).strip()
            rationale = m.group(2).strip()
            if did and rationale:
                exemptions[did] = rationale
    return exemptions


def gate_coverage(spec_path: Path) -> dict:
    """Deterministic Gate-1 MCP-coverage verdict for a feature/bug spec dir.

    Reads ``spec_path/SPEC.md``'s Locked-Decision surface, greps
    ``spec_path/mcp-tests/*.md`` (RESOLVING symlink / pointer targets), and
    returns per-decision covered/uncovered.

    A decision is **covered** iff at least one scenario file contains the
    decision ``id`` as a literal OR contains at least 2 of the decision's
    keywords (case-insensitive) — OR it is **exempt**: listed in a
    ``## MCP Coverage Exemptions`` SPEC section with a non-empty rationale (the
    mcp-coverage-audit.md D7 disposition for documented-MCP-untestable decisions,
    e.g. backend/miniflare-verified Locked Decisions with no Tauri MCP surface).
    An exempt decision is NOT added to ``uncovered``; its entry carries
    ``exempt: True`` + the ``rationale`` so the disposition is auditable. This
    mirrors mcp-coverage-audit.md Step 3.

    Return shape::

        {"ok": True,
         "decisions": [{"id", "title", "keywords", "covered"}, ...],
         "uncovered": [id, ...],
         "scenario_count": int}

    A SPEC with no Locked-Decision surface passes vacuously (empty lists). An
    empty/absent mcp-tests dir → every decision uncovered.
    """
    spec_md_path = spec_path / "SPEC.md"
    spec_md = ""
    if spec_md_path.exists():
        try:
            spec_md = spec_md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            spec_md = ""

    decisions = _parse_locked_decisions(spec_md)
    exemptions = _parse_mcp_coverage_exemptions(spec_md)

    # Gather (resolved) scenario texts.
    mcp_dir = spec_path / "mcp-tests"
    scenario_texts: list[str] = []
    if mcp_dir.exists() and mcp_dir.is_dir():
        for p in sorted(mcp_dir.glob("*.md")):
            scenario_texts.append(_resolve_scenario_text(p))

    result_decisions: list[dict] = []
    uncovered: list[str] = []
    for d in decisions:
        did = d["id"]
        kws = d["keywords"]
        covered = False
        for text in scenario_texts:
            if did and re.search(rf"\b{re.escape(did)}\b", text):
                covered = True
                break
            low = text.lower()
            if kws and sum(1 for k in kws if k in low) >= 2:
                covered = True
                break
        # Exemption path (D7): a decision documented as MCP-untestable in the
        # ``## MCP Coverage Exemptions`` section with a non-empty rationale is
        # NOT uncovered — it is a sanctioned disposition, not a gap. Scenario
        # coverage still wins (a decision that is BOTH scenario-covered and
        # listed stays covered=True, exempt=False).
        exempt_rationale = exemptions.get(did)
        exempt = (not covered) and bool(exempt_rationale)
        entry = {"id": did, "title": d["title"], "keywords": kws, "covered": covered}
        if exempt:
            entry["exempt"] = True
            entry["rationale"] = exempt_rationale
        result_decisions.append(entry)
        if not covered and not exempt:
            uncovered.append(did)

    return {
        "ok": True,
        "decisions": result_decisions,
        "uncovered": uncovered,
        "scenario_count": len(scenario_texts),
    }
