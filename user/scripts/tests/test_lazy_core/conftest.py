#!/usr/bin/env python3
"""conftest.py — pytest bootstrap for the (future) test_lazy_core/ split package.

lazy-core-package-decomposition WU-1 (scaffolding only — see
docs/features/lazy-core-package-decomposition/PHASES.md). WU-2 will move
user/scripts/test_lazy_core.py's ~1142 tests into per-seam files under this
directory (test_docmodel.py, test_gates.py, ...); this conftest is created
ahead of that move so the package layout and shared fixtures exist first.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Insert the scripts directory on sys.path so `import lazy_core` resolves when
# collected from any root (hyphen-free name, so direct import works once
# extracted). This conftest lives two directories deeper than the original
# flat test_lazy_core.py (user/scripts/tests/test_lazy_core/ vs.
# user/scripts/), so parents[2] — not parents[0] — is the scripts dir where
# lazy_core/ actually lives: parents[0]=test_lazy_core/, parents[1]=tests/,
# parents[2]=user/scripts.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS_DIR))


@pytest.fixture
def tmp_repo():
    """Yield a Path to a throwaway repo root with a minimal docs/features/ skeleton.

    This is the pytest-fixture form of the ``with tempfile.TemporaryDirectory()
    as td: repo_root = Path(td); ...`` scaffolding hand-rolled ~726 times across
    test_lazy_core.py (e.g. ``repo_root / "docs" / "features" / "my-feat"`` in
    the verify_ledger / apply_pseudo / gate tests). It intentionally stays
    minimal — just the empty ``docs/features/`` directory most fixtures then
    build a specific ``<slug>/`` subtree under.

    ADOPTION IS INCREMENTAL BY DESIGN (WU-1 scaffolding only): this phase does
    NOT rewrite any existing hand-rolled TemporaryDirectory test onto this
    fixture. It is defined here for FUTURE tests (and for WU-2-and-later
    opportunistic migrations) to opt into; the existing ~726 call sites are
    left exactly as they are when the file is split in WU-2.
    """
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        (repo_root / "docs" / "features").mkdir(parents=True)
        yield repo_root
