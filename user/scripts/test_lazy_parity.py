"""
test_lazy_parity.py — TDD tests for lazy_parity_audit.py (does NOT exist yet).

All fixture-driven tests (Class 1) build synthetic canonical/derived SKILL.md
files inside tmp_path and drive audit_pair() directly via the manifest= kwarg so
they never touch the real repo tree.

The live zero-drift test (Class 2) drives the real repo + manifest to prove
Phase 1 closed both gaps.

Run with:
    cd C:/Users/Jacob/source/repos/claude-config
    python3 -m pytest user/scripts/test_lazy_parity.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — ensure the scripts directory is importable regardless of
# how pytest is invoked (project root, scripts dir, etc.).
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lazy_parity_audit
from lazy_parity_audit import audit_pair, audit_all_pairs


# ---------------------------------------------------------------------------
# Shared fixture helper
# ---------------------------------------------------------------------------

def _make_pair(
    tmp_path: Path,
    canonical_text: str,
    derived_text: str,
    *,
    pair_name: str = "deriv",
    mechanic_set: str = "test-set",
    mechanics: list | None = None,
    mechanic_overrides: list | None = None,
    headings: list | None = None,
    token_substitutions: list | None = None,
) -> dict:
    """
    Write tmp_path/canon/SKILL.md and tmp_path/deriv/SKILL.md with the given
    text, then return a synthetic manifest dict whose canonical/derived paths
    are repo-root-relative strings ("canon/SKILL.md" / "deriv/SKILL.md").

    The caller passes this dict as manifest= to audit_pair() so no disk lookup
    of the real manifest.json is needed.
    """
    canon_dir = tmp_path / "canon"
    deriv_dir = tmp_path / pair_name
    canon_dir.mkdir(parents=True, exist_ok=True)
    deriv_dir.mkdir(parents=True, exist_ok=True)
    (canon_dir / "SKILL.md").write_text(canonical_text, encoding="utf-8")
    (deriv_dir / "SKILL.md").write_text(derived_text, encoding="utf-8")

    manifest = {
        "mechanic_sets": {
            mechanic_set: mechanics or [],
        },
        "pairs": [
            {
                "canonical": "canon/SKILL.md",
                "derived": f"{pair_name}/SKILL.md",
                "mechanic_set": mechanic_set,
                "mechanic_overrides": mechanic_overrides or [],
                "headings": headings or [],
                "token_substitutions": token_substitutions or [],
            }
        ],
    }
    return manifest


# ===========================================================================
# Class 1 — Fixture engine tests
# ===========================================================================

class TestFixtureEngine:
    """
    Hermetic tests: every check has a FIRING case and a PASSING case.
    Tests never read the real lazy-parity-manifest.json; they use synthetic
    manifests passed via the manifest= kwarg.
    """

    # -----------------------------------------------------------------------
    # C1 — Tier-1 completeness
    # -----------------------------------------------------------------------

    def test_c1_fires_on_missing_heading(self, tmp_path: Path) -> None:
        """
        Canonical has a '## Step X' heading with NO corresponding headings[]
        entry in the manifest → a C1 finding must appear.
        """
        canon = "## Step X\nSome content here.\n"
        deriv = "## Step X\nSome derived content.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[],  # no entry for '## Step X' → C1 must fire
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert any(
            "C1" in f and "Step X" in f and "deriv" in f for f in findings
        ), f"Expected a C1/Step X/deriv finding; got: {findings}"

    def test_c1_passes_when_all_headings_covered(self, tmp_path: Path) -> None:
        """
        Every canonical heading has a headings[] entry → no C1 finding.
        """
        canon = "## Step A\nContent.\n"
        deriv = "## Step A\nDerived content.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[
                {
                    "heading": "## Step A",
                    "coverage": "restated",
                    "evidence": "Step A",
                }
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert not any("C1" in f for f in findings), (
            f"Unexpected C1 finding(s): {findings}"
        )

    # -----------------------------------------------------------------------
    # C2 — coverage resolves
    # -----------------------------------------------------------------------

    def test_c2_fires_on_broken_pointer(self, tmp_path: Path) -> None:
        """
        A 'restated' entry whose evidence regex does NOT appear in the derived
        file → a C2 finding for that heading.
        """
        canon = "## Heading Alpha\nCanonical body.\n"
        deriv = "## Heading Alpha\nCompletely different body.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[
                {
                    "heading": "## Heading Alpha",
                    "coverage": "restated",
                    # This regex will NOT match anything in 'deriv'
                    "evidence": "canonical body phrase XYZ",
                }
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert any(
            "C2" in f and "Heading Alpha" in f and "deriv" in f for f in findings
        ), f"Expected a C2/Heading Alpha finding; got: {findings}"

    def test_c2_passes_when_evidence_resolves(self, tmp_path: Path) -> None:
        """
        Evidence present in derived → no C2 finding.
        Also proves token_substitutions are applied before matching:
        the manifest stores evidence in canonical vocab ('COMPLETED.md') but
        the derived file only has 'FIXED.md' (the substituted form), and a
        token_substitutions entry maps canonical→derived.
        """
        canon = "## Terminal Action\nWrite COMPLETED.md to disk.\n"
        # Derived uses 'FIXED.md' — the substituted token
        deriv = "## Terminal Action\nWrite FIXED.md to disk.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[
                {
                    "heading": "## Terminal Action",
                    "coverage": "restated",
                    # Evidence written in canonical vocab; token sub must convert it
                    "evidence": "COMPLETED\\.md",
                }
            ],
            token_substitutions=[
                # Engine must replace 'COMPLETED.md' → 'FIXED.md' in evidence
                {"canonical": "COMPLETED.md", "derived": "FIXED.md"},
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert not any("C2" in f for f in findings), (
            f"Unexpected C2 finding(s) — token substitution may not be applied: {findings}"
        )

    # -----------------------------------------------------------------------
    # C3 — Tier-2 predicates (mechanics)
    # -----------------------------------------------------------------------

    def test_c3_fires_on_missing_mechanic(self, tmp_path: Path) -> None:
        """
        A mechanic whose pattern is absent from the derived file (and NOT
        overridden) → a C3 finding containing the mechanic id.
        Uses 'cycle-dispatch-by-ref' to mirror the real manifest assertion.
        """
        canon = "## Overview\ncycle_prompt_ref is used here.\n"
        # Derived does NOT contain 'cycle_prompt_ref'
        deriv = "## Overview\nThis derived skill uses some other mechanism.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            mechanics=[
                {
                    "id": "cycle-dispatch-by-ref",
                    "assert": {"type": "regex_present", "pattern": "cycle_prompt_ref"},
                }
            ],
            headings=[
                {
                    "heading": "## Overview",
                    "coverage": "restated",
                    "evidence": "Overview",
                }
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert any(
            "C3" in f and "cycle-dispatch-by-ref" in f for f in findings
        ), f"Expected C3/cycle-dispatch-by-ref finding; got: {findings}"

    def test_c3_passes_when_mechanic_present(self, tmp_path: Path) -> None:
        """
        Mechanic pattern present in derived → no C3 finding for it.
        """
        canon = "## Overview\ncycle_prompt_ref used here.\n"
        deriv = "## Overview\ncycle_prompt_ref is also present here.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            mechanics=[
                {
                    "id": "cycle-dispatch-by-ref",
                    "assert": {"type": "regex_present", "pattern": "cycle_prompt_ref"},
                }
            ],
            headings=[
                {
                    "heading": "## Overview",
                    "coverage": "restated",
                    "evidence": "Overview",
                }
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert not any("C3" in f for f in findings), (
            f"Unexpected C3 finding(s): {findings}"
        )

    def test_mechanic_override_suppresses_c3(self, tmp_path: Path) -> None:
        """
        A mechanic absent from the derived file BUT listed in this pair's
        mechanic_overrides with coverage='divergence' → NO C3 finding.
        This is the per-pair gap-vs-divergence suppression (the dev:kill-in-cloud case).
        """
        canon = "## Overview\ndev:kill is invoked on run end.\n"
        # Derived intentionally omits 'dev:kill' — it's a cloud skill
        deriv = "## Overview\nCloud variant; no dev:kill.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            mechanics=[
                {
                    "id": "run-end-dev-kill",
                    "assert": {"type": "regex_present", "pattern": "dev:kill"},
                }
            ],
            mechanic_overrides=[
                # This override suppresses C3 for run-end-dev-kill
                {"id": "run-end-dev-kill", "coverage": "divergence"}
            ],
            headings=[
                {
                    "heading": "## Overview",
                    "coverage": "restated",
                    "evidence": "Overview",
                }
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert not any("C3" in f for f in findings), (
            f"mechanic_override with divergence should suppress C3; got: {findings}"
        )

    # -----------------------------------------------------------------------
    # C4 — no stale divergence
    # -----------------------------------------------------------------------

    def test_c4_fires_on_stale_divergence(self, tmp_path: Path) -> None:
        """
        A headings[] entry referencing a heading that does NOT exist in the
        canonical file → a C4 finding naming that heading.
        """
        canon = "## Real Heading\nContent.\n"
        deriv = "## Real Heading\nDerived content.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[
                {
                    "heading": "## Real Heading",
                    "coverage": "restated",
                    "evidence": "Real Heading",
                },
                {
                    # This heading does NOT exist in canon → C4
                    "heading": "## Ghost Heading",
                    "coverage": "divergence",
                    "reason": "This section was removed from canonical.",
                },
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert any(
            "C4" in f and "Ghost Heading" in f for f in findings
        ), f"Expected C4/Ghost Heading finding; got: {findings}"

    # -----------------------------------------------------------------------
    # C5 — reason hygiene
    # -----------------------------------------------------------------------

    def test_c5_fires_on_reasonless_divergence(self, tmp_path: Path) -> None:
        """
        A coverage='divergence' entry with NO reason → a C5 finding.
        """
        canon = "## Diverged Section\nCanonical content.\n"
        deriv = "## Something Else\nDerived content.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[
                {
                    "heading": "## Diverged Section",
                    "coverage": "divergence",
                    # Missing 'reason' → C5 must fire
                },
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert any(
            "C5" in f and "Diverged Section" in f for f in findings
        ), f"Expected C5/Diverged Section finding; got: {findings}"

    def test_c5_fires_on_restated_with_reason(self, tmp_path: Path) -> None:
        """
        A 'restated' entry that wrongly carries a 'reason' key → a C5 finding.
        restated/inherited entries must NOT have a reason.
        """
        canon = "## Restated Section\nCanonical content.\n"
        deriv = "## Restated Section\nDerived content.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[
                {
                    "heading": "## Restated Section",
                    "coverage": "restated",
                    "evidence": "Restated Section",
                    # 'reason' must NOT be present on restated entries → C5
                    "reason": "Wrongly included reason",
                },
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)

        assert any(
            "C5" in f and "Restated Section" in f for f in findings
        ), f"Expected C5/Restated Section finding; got: {findings}"

    # -----------------------------------------------------------------------
    # C6 — soft (stderr warn, never in return list)
    # -----------------------------------------------------------------------

    def test_c6_warns_to_stderr_without_failing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """
        A divergence entry with a doc_anchor whose text is absent from the
        derived file → C6 warning written to stderr only.

        Asserts:
        - The returned findings list contains NO 'C6' entry (C6 is soft).
        - capsys.readouterr().err contains the doc_anchor text or a C6/warning
          marker, proving the warning was emitted.
        """
        canon = "## Research Step\nCanonical research content.\n"
        # Derived does NOT contain the doc_anchor text 'Differences table: Research'
        deriv = "## No Research\nCloud variant; no research steps.\n"
        manifest = _make_pair(
            tmp_path,
            canon,
            deriv,
            headings=[
                {
                    "heading": "## Research Step",
                    "coverage": "divergence",
                    "reason": "Bug pipeline has no research stage.",
                    "doc_anchor": "Differences table: Research section",
                },
            ],
        )

        findings = audit_pair(tmp_path, "deriv", manifest=manifest)
        captured = capsys.readouterr()

        # C6 must NEVER appear in the returned findings list
        assert not any("C6" in f for f in findings), (
            f"C6 must be soft (stderr only); found in return list: {findings}"
        )

        # But a warning must have been written to stderr
        assert (
            "Differences table: Research section" in captured.err
            or "C6" in captured.err
            or "warn" in captured.err.lower()
        ), (
            f"Expected a C6/warn marker in stderr; got: {captured.err!r}"
        )


# ===========================================================================
# Class 2 — Live zero-drift assertion
# ===========================================================================

class TestLiveZeroDrift:
    """
    Drives the REAL repo + REAL manifest.  Passes iff Phase 1 closed both
    gaps and the manifest is correct.
    """

    def test_live_lazy_bug_batch_zero_drift(self) -> None:
        """
        Hard gate: lazy-bug-batch must pass all checks against lazy-batch
        with the current state of both SKILL.md files and the real manifest.

        repo_root = parents[2] of this file:
            test_lazy_parity.py          → parents[0] = user/scripts/
                                         → parents[1] = user/
                                         → parents[2] = repo root
        """
        repo_root = Path(__file__).resolve().parents[2]

        # Sanity: the manifest must exist at the expected location
        manifest_path = repo_root / "user" / "scripts" / "lazy-parity-manifest.json"
        assert manifest_path.exists(), (
            f"Manifest not found at {manifest_path}; "
            f"check parents[] index — repo_root resolved to {repo_root}"
        )

        findings = audit_pair(repo_root, "lazy-bug-batch")

        assert findings == [], (
            "lazy-bug-batch has parity drift vs lazy-batch:\n"
            + "\n".join(f"  {f}" for f in findings)
        )

    def test_live_lazy_batch_cloud_zero_drift(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        findings = audit_pair(repo_root, "lazy-batch-cloud")
        assert findings == [], (
            "lazy-batch-cloud has parity drift vs lazy-batch:\n"
            + "\n".join(f"  {f}" for f in findings)
        )

    def test_live_lazy_bug_zero_drift(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        findings = audit_pair(repo_root, "lazy-bug")
        assert findings == [], (
            "lazy-bug has parity drift vs lazy:\n"
            + "\n".join(f"  {f}" for f in findings)
        )

    def test_live_lazy_cloud_zero_drift(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        findings = audit_pair(repo_root, "lazy-cloud")
        assert findings == [], (
            "lazy-cloud has parity drift vs lazy:\n"
            + "\n".join(f"  {f}" for f in findings)
        )

    def test_live_lazy_bug_status_zero_drift(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        findings = audit_pair(repo_root, "lazy-bug-status")
        assert findings == [], (
            "lazy-bug-status has parity drift vs lazy-status:\n"
            + "\n".join(f"  {f}" for f in findings)
        )


# ===========================================================================
# Class 3 — Cycle-marker dispatch bracket (lazy-cycle-containment Phase 5, C1)
# ===========================================================================
#
# SPEC §C1 + Validation row "All three orchestrators bracket every dispatch":
# the coupled trio (lazy-batch + lazy-bug-batch + lazy-batch-cloud) must each
# wrap every Agent dispatch with `--cycle-begin` (immediately before) and
# `--cycle-end` (immediately after, on EVERY return path: success, halt, error).
# This is a docs-consistency check over the SKILL.md prose — no pipeline run.

# The coupled trio: (derived-name, repo-relative SKILL.md path, state script).
_CYCLE_BRACKET_TRIO: list[tuple[str, str, str]] = [
    ("lazy-batch", "user/skills/lazy-batch/SKILL.md", "lazy-state.py"),
    ("lazy-bug-batch", "user/skills/lazy-bug-batch/SKILL.md", "bug-state.py"),
    (
        "lazy-batch-cloud",
        "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
        "lazy-state.py",
    ),
]


def _read_trio_skill(repo_root: Path, rel_path: str) -> str:
    p = repo_root / rel_path
    assert p.exists(), f"coupled-trio SKILL.md not found: {p}"
    return p.read_text(encoding="utf-8")


class TestCycleBracket:
    """
    The C1 dispatch bracket must be present + mirrored across the coupled trio,
    and each bracket must document --cycle-end on every return path.
    """

    def test_each_orchestrator_has_nonzero_begin_and_end(self) -> None:
        """Every SKILL in the trio carries >=1 --cycle-begin and >=1 --cycle-end."""
        repo_root = Path(__file__).resolve().parents[2]
        for name, rel_path, _script in _CYCLE_BRACKET_TRIO:
            text = _read_trio_skill(repo_root, rel_path)
            begins = text.count("--cycle-begin")
            ends = text.count("--cycle-end")
            assert begins >= 1, f"{name}: expected >=1 --cycle-begin, found {begins}"
            assert ends >= 1, f"{name}: expected >=1 --cycle-end, found {ends}"

    def test_each_orchestrator_uses_correct_state_script(self) -> None:
        """The bug orchestrator brackets with bug-state.py; the others lazy-state.py."""
        repo_root = Path(__file__).resolve().parents[2]
        for name, rel_path, script in _CYCLE_BRACKET_TRIO:
            text = _read_trio_skill(repo_root, rel_path)
            # The bracket block must reference the orchestrator's own state script.
            assert f"{script} --cycle-begin" in text or f"{script} \\\n" in text or (
                "--cycle-begin" in text and script in text
            ), f"{name}: --cycle-begin not associated with {script}"

    def test_each_orchestrator_documents_all_return_paths(self) -> None:
        """
        Each SKILL's bracket prose names the three return paths for --cycle-end —
        an orphan --cycle-begin without a matching end on every path is the
        failure C1 guards against.
        """
        repo_root = Path(__file__).resolve().parents[2]
        for name, rel_path, _script in _CYCLE_BRACKET_TRIO:
            text = _read_trio_skill(repo_root, rel_path).lower()
            # "every return path (success, halt, error)" wording (or close).
            assert "success" in text and "halt" in text and "error" in text, (
                f"{name}: bracket prose must name success/halt/error return paths"
            )
            assert "return path" in text, (
                f"{name}: bracket prose must reference 'return path' for --cycle-end"
            )

    def test_bracket_is_mirrored_across_trio(self) -> None:
        """
        Parity: all three carry the bracket (non-zero begin+end in each). A bracket
        present in one but absent in another is coupled-trio drift.
        """
        repo_root = Path(__file__).resolve().parents[2]
        present = []
        for name, rel_path, _script in _CYCLE_BRACKET_TRIO:
            text = _read_trio_skill(repo_root, rel_path)
            present.append(("--cycle-begin" in text and "--cycle-end" in text))
        assert all(present), (
            "coupled-trio drift: the --cycle-begin/--cycle-end bracket must appear "
            f"in ALL three orchestrators, got presence={present} "
            f"for {[n for n, _, _ in _CYCLE_BRACKET_TRIO]}"
        )


# ===========================================================================
# Class 4 — State-script per-repo parity (multi-repo-concurrent-runs WU-3.2)
# ===========================================================================

class TestStateScriptParity:
    """Both feature + bug state scripts must bind the active repo at main() so
    claude_state_dir() scopes run-scoped state per repo."""

    def test_live_state_scripts_bind_active_repo(self) -> None:
        """Hard gate: lazy-state.py AND bug-state.py both call
        set_active_repo_root(args.repo_root) at main() (the shared per-repo
        state-dir surface).  Zero findings against the real repo."""
        repo_root = Path(__file__).resolve().parents[2]
        findings = lazy_parity_audit.audit_state_script_parity(repo_root)
        assert findings == [], (
            "state-script per-repo parity drift:\n"
            + "\n".join(f"  {f}" for f in findings)
        )

    def test_audit_state_script_parity_fires_when_binding_missing(
        self, tmp_path: Path
    ) -> None:
        """The check FIRES (one finding) when a state script drops the
        set_active_repo_root(args.repo_root) binding."""
        scripts = tmp_path / "user" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "lazy-state.py").write_text(
            'def main():\n    lazy_core.set_active_repo_root(args.repo_root)\n'
            '    parser.add_argument("--reorder-queue")\n',
            encoding="utf-8",
        )
        # bug-state.py is MISSING the binding (but HAS --reorder-queue) → exactly
        # one finding, naming the binding gap.
        (scripts / "bug-state.py").write_text(
            'def main():\n    pass  # no active-repo binding\n'
            '    parser.add_argument("--reorder-queue")\n',
            encoding="utf-8",
        )
        findings = lazy_parity_audit.audit_state_script_parity(tmp_path)
        assert len(findings) == 1, findings
        assert "bug-state.py" in findings[0]
        assert "STATE" in findings[0]
        assert "set_active_repo_root" in findings[0]

    def test_audit_state_script_parity_fires_when_reorder_queue_missing(
        self, tmp_path: Path
    ) -> None:
        """The check FIRES (one finding) when a state script drops the
        --reorder-queue subcommand (coupled-pair queue-mutation surface)."""
        scripts = tmp_path / "user" / "scripts"
        scripts.mkdir(parents=True)
        # Both bind the active repo; only lazy-state.py carries --reorder-queue.
        (scripts / "lazy-state.py").write_text(
            'set_active_repo_root(args.repo_root)\n'
            'parser.add_argument("--reorder-queue")\n',
            encoding="utf-8",
        )
        (scripts / "bug-state.py").write_text(
            'set_active_repo_root(args.repo_root)  # no --reorder-queue\n',
            encoding="utf-8",
        )
        findings = lazy_parity_audit.audit_state_script_parity(tmp_path)
        assert len(findings) == 1, findings
        assert "bug-state.py" in findings[0]
        assert "--reorder-queue" in findings[0]

    def test_audit_state_script_parity_clean_when_both_bind(
        self, tmp_path: Path
    ) -> None:
        """No findings when both scripts carry the binding (bare or lazy_core.
        prefixed form) AND the --reorder-queue subcommand."""
        scripts = tmp_path / "user" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "lazy-state.py").write_text(
            'set_active_repo_root( args.repo_root )\n'
            'parser.add_argument("--reorder-queue")\n',
            encoding="utf-8",
        )
        (scripts / "bug-state.py").write_text(
            'lazy_core.set_active_repo_root(args.repo_root)\n'
            'parser.add_argument("--reorder-queue")\n',
            encoding="utf-8",
        )
        assert lazy_parity_audit.audit_state_script_parity(tmp_path) == []


# ===========================================================================
# Class 5 — Merged-view dispatch parity (unified-pipeline-orchestrator Phase 2)
# ===========================================================================
#
# Phase 2 makes /lazy-batch the SHARED driver looping over the Phase-1 merged
# view (`lazy-state.py --next-merged`), type-dispatching each cycle to
# lazy-state.py (feature → __mark_complete__) or bug-state.py (bug →
# __mark_fixed__).  The merged-view dispatch branch must be present + consistent
# across the workstation driver and its cloud mirror (coupled-pair rule), and a
# single-type run must stay identical to the per-type batch (no-regression
# guard).  audit_merged_view_dispatch_parity(repo_root) owns this — it audits the
# SKILL.md prose (no pipeline run), additive to the manifest pair audit + the
# state-script parity check.

# The unified-driver pair: (name, repo-relative SKILL.md path).  The workstation
# canonical driver and its cloud mirror BOTH carry the merged-view branch; the
# bug-batch driver carries the convergence cross-reference (single-type bug runs
# still use it).
_MERGED_VIEW_DRIVERS: list[tuple[str, str]] = [
    ("lazy-batch", "user/skills/lazy-batch/SKILL.md"),
    (
        "lazy-batch-cloud",
        "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
    ),
]


class TestMergedViewDispatchParity:
    """The merged-view dispatch branch must be present + mirrored across the
    unified driver and its cloud variant, document type-correct terminals, and
    preserve single-type behavior."""

    def test_live_merged_view_dispatch_parity_clean(self) -> None:
        """Hard gate: the real workstation + cloud drivers both carry a
        consistent merged-view dispatch branch.  Zero findings."""
        repo_root = Path(__file__).resolve().parents[2]
        findings = lazy_parity_audit.audit_merged_view_dispatch_parity(repo_root)
        assert findings == [], (
            "merged-view dispatch parity drift:\n"
            + "\n".join(f"  {f}" for f in findings)
        )

    def test_fires_when_cloud_missing_merged_branch(self, tmp_path: Path) -> None:
        """The check FIRES when one driver carries the merged-view branch but the
        other does not (coupled-pair drift)."""
        skills = tmp_path / "user" / "skills" / "lazy-batch"
        cloud = (
            tmp_path / "repos" / "algobooth" / ".claude" / "skills" / "lazy-batch-cloud"
        )
        skills.mkdir(parents=True)
        cloud.mkdir(parents=True)
        # Workstation driver HAS the merged-view branch + type-dispatch.
        (skills / "SKILL.md").write_text(
            "## Unified driver — merged-view dispatch\n"
            "Probe `lazy-state.py --next-merged` for the head; dispatch feature → "
            "`lazy-state.py` + `__mark_complete__`, bug → `bug-state.py` + "
            "`__mark_fixed__`. Single-type run is unchanged. "
            "A fixed bug chains the `--archive-fixed` archive + de-queue follow-up.\n",
            encoding="utf-8",
        )
        # Cloud driver is MISSING --next-merged → must be flagged.
        (cloud / "SKILL.md").write_text(
            "## Cloud driver\nLoops on lazy-state.py --cloud; no merged view here.\n",
            encoding="utf-8",
        )
        findings = lazy_parity_audit.audit_merged_view_dispatch_parity(tmp_path)
        assert findings, "expected a finding when cloud lacks the merged-view branch"
        assert any("lazy-batch-cloud" in f and "next-merged" in f for f in findings), (
            f"expected a next-merged finding for lazy-batch-cloud; got: {findings}"
        )

    def test_fires_when_terminal_dispatch_inconsistent(
        self, tmp_path: Path
    ) -> None:
        """The check FIRES when a driver's merged-view branch omits a type-correct
        terminal action (feature __mark_complete__ / bug __mark_fixed__)."""
        skills = tmp_path / "user" / "skills" / "lazy-batch"
        cloud = (
            tmp_path / "repos" / "algobooth" / ".claude" / "skills" / "lazy-batch-cloud"
        )
        skills.mkdir(parents=True)
        cloud.mkdir(parents=True)
        full = (
            "## Unified driver — merged-view dispatch\n"
            "Probe `lazy-state.py --next-merged`; feature → `lazy-state.py` + "
            "`__mark_complete__`, bug → `bug-state.py` + `__mark_fixed__`. "
            "Single-type run is unchanged. "
            "A fixed bug chains the `--archive-fixed` archive + de-queue follow-up.\n"
        )
        (skills / "SKILL.md").write_text(full, encoding="utf-8")
        # Cloud has --next-merged but NEVER names the bug terminal __mark_fixed__.
        (cloud / "SKILL.md").write_text(
            "## Unified driver — merged-view dispatch\n"
            "Probe `lazy-state.py --next-merged`; feature → `lazy-state.py` + "
            "`__mark_complete__`. Single-type run is unchanged.\n",
            encoding="utf-8",
        )
        findings = lazy_parity_audit.audit_merged_view_dispatch_parity(tmp_path)
        assert any(
            "lazy-batch-cloud" in f and "__mark_fixed__" in f for f in findings
        ), f"expected a __mark_fixed__ consistency finding; got: {findings}"

    def test_fires_when_no_regression_guard_absent(self, tmp_path: Path) -> None:
        """The check FIRES when a driver's merged-view branch omits the
        single-type no-regression guarantee."""
        skills = tmp_path / "user" / "skills" / "lazy-batch"
        cloud = (
            tmp_path / "repos" / "algobooth" / ".claude" / "skills" / "lazy-batch-cloud"
        )
        skills.mkdir(parents=True)
        cloud.mkdir(parents=True)
        full = (
            "## Unified driver — merged-view dispatch\n"
            "Probe `lazy-state.py --next-merged`; feature → `lazy-state.py` + "
            "`__mark_complete__`, bug → `bug-state.py` + `__mark_fixed__`. "
            "Single-type run is unchanged. "
            "A fixed bug chains the `--archive-fixed` archive + de-queue follow-up.\n"
        )
        (skills / "SKILL.md").write_text(full, encoding="utf-8")
        # Cloud omits the single-type guarantee phrase.
        (cloud / "SKILL.md").write_text(
            "## Unified driver — merged-view dispatch\n"
            "Probe `lazy-state.py --next-merged`; feature → `lazy-state.py` + "
            "`__mark_complete__`, bug → `bug-state.py` + `__mark_fixed__`.\n",
            encoding="utf-8",
        )
        findings = lazy_parity_audit.audit_merged_view_dispatch_parity(tmp_path)
        assert any(
            "lazy-batch-cloud" in f and "single-type" in f.lower() for f in findings
        ), f"expected a single-type no-regression finding; got: {findings}"

    def test_passes_when_both_drivers_consistent(self, tmp_path: Path) -> None:
        """No findings when both drivers carry a complete, consistent merged-view
        dispatch branch."""
        skills = tmp_path / "user" / "skills" / "lazy-batch"
        cloud = (
            tmp_path / "repos" / "algobooth" / ".claude" / "skills" / "lazy-batch-cloud"
        )
        skills.mkdir(parents=True)
        cloud.mkdir(parents=True)
        full = (
            "## Unified driver — merged-view dispatch\n"
            "Probe `lazy-state.py --next-merged`; feature → `lazy-state.py` + "
            "`__mark_complete__`, bug → `bug-state.py` + `__mark_fixed__`. "
            "Single-type run is unchanged (byte-for-byte identical to the "
            "per-type batch). "
            "A fixed bug chains the `--archive-fixed` archive + de-queue follow-up.\n"
        )
        (skills / "SKILL.md").write_text(full, encoding="utf-8")
        (cloud / "SKILL.md").write_text(full, encoding="utf-8")
        assert lazy_parity_audit.audit_merged_view_dispatch_parity(tmp_path) == []

    def test_included_in_audit_all_pairs(self) -> None:
        """audit_all_pairs runs the merged-view dispatch check against the real
        repo with zero findings (regression: the new check is wired into the
        default whole-repo audit)."""
        repo_root = Path(__file__).resolve().parents[2]
        findings = audit_all_pairs(repo_root)
        merged_findings = [f for f in findings if "merged-view" in f]
        assert merged_findings == [], (
            "audit_all_pairs surfaced merged-view findings:\n"
            + "\n".join(f"  {f}" for f in merged_findings)
        )
