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
