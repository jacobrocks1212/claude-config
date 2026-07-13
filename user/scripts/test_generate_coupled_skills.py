"""
test_generate_coupled_skills.py — pytest suite for the coupled-pair generator
(coupled-pair-generation).

Covers: render determinism, byte-faithful round-trip (golden) for every real
pair, --check drift detection, overlay schema validation, canonical-edit
propagation, and CRLF byte-preservation.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent


def _load_module():
    # The script filename has hyphens — import by path.
    spec = importlib.util.spec_from_file_location(
        "generate_coupled_skills", _HERE / "generate-coupled-skills.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gcs = _load_module()


def _manifest():
    return gcs.load_manifest(_REPO_ROOT)


def _pairs():
    return _manifest().get("pairs", [])


# ---------------------------------------------------------------------------
# split_blocks round-trips exactly (the byte-faithful foundation)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "no headings here\r\njust prose\r\n",
    "## A\r\nbody a\r\n## B\r\nbody b",
    "preamble\r\n## H\r\nx\r\n### sub\r\ny\r\n",
    "## trailing-no-newline",
    "",
])
def test_split_blocks_concat_is_identity(text):
    blocks = gcs.split_blocks(text)
    assert "".join(b for _, b in blocks) == text


def test_verbatim_line_split_is_exact_inverse():
    # The verbatim storage relies on "\n".join(s.split("\n")) == s for any s.
    for s in ["a\r\nb\r\n", "x", "", "\n\n", "line\rcarriage", "a\nb\nc"]:
        assert "\n".join(s.split("\n")) == s


# ---------------------------------------------------------------------------
# GOLDEN: every real pair regenerates byte-identically from its committed overlay
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pair", _pairs(), ids=lambda p: gcs.pair_name(p))
def test_committed_overlay_regenerates_derived_byte_identical(pair):
    canonical_text = gcs.read_text_raw(_REPO_ROOT / pair["canonical"])
    subs = pair.get("token_substitutions", [])
    overlay = json.loads(gcs.read_text_raw(gcs.overlay_path(_REPO_ROOT, pair)))
    rendered = gcs.generate(canonical_text, subs, overlay)
    committed = gcs.read_text_raw(_REPO_ROOT / pair["derived"])
    assert rendered == committed, f"{gcs.pair_name(pair)} regen != committed derived"


@pytest.mark.parametrize("pair", _pairs(), ids=lambda p: gcs.pair_name(p))
def test_extract_then_generate_is_byte_identical(pair):
    # Extract fresh from committed files, then generate — must reproduce derived.
    overlay = gcs.build_overlay(pair, _REPO_ROOT)
    canonical_text = gcs.read_text_raw(_REPO_ROOT / pair["canonical"])
    subs = pair.get("token_substitutions", [])
    rendered = gcs.generate(canonical_text, subs, overlay)
    committed = gcs.read_text_raw(_REPO_ROOT / pair["derived"])
    assert rendered == committed


# ---------------------------------------------------------------------------
# --check is the drift gate: clean on the committed tree, red on a hand-edit
# ---------------------------------------------------------------------------

def test_check_clean_on_committed_tree():
    rc = gcs.cmd_check(_manifest(), _REPO_ROOT, None)
    assert rc == 0


def test_check_detects_derived_hand_edit(tmp_path):
    # Build a hermetic mini-repo with one canonical, one derived, one overlay.
    _stage_fixture_repo(tmp_path, derived_body="## H\r\nORIGINAL\r\n")
    manifest = gcs.load_manifest(tmp_path)
    assert gcs.cmd_check(manifest, tmp_path, None) == 0
    # Hand-edit the committed derived file (simulate drift / rot).
    derived = tmp_path / manifest["pairs"][0]["derived"]
    gcs.write_text_raw(derived, "## H\r\nHAND-EDITED\r\n")
    assert gcs.cmd_check(manifest, tmp_path, None) == 1


def test_write_then_check_is_clean(tmp_path):
    _stage_fixture_repo(tmp_path, derived_body="## H\r\nORIGINAL\r\n")
    manifest = gcs.load_manifest(tmp_path)
    # A hand-edited derived is repaired by --write (regenerate from overlay).
    derived = tmp_path / manifest["pairs"][0]["derived"]
    gcs.write_text_raw(derived, "## H\r\nHAND-EDITED\r\n")
    assert gcs.cmd_write(manifest, tmp_path, None) == 0
    assert gcs.cmd_check(manifest, tmp_path, None) == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pair", _pairs(), ids=lambda p: gcs.pair_name(p))
def test_generate_is_deterministic(pair):
    canonical_text = gcs.read_text_raw(_REPO_ROOT / pair["canonical"])
    subs = pair.get("token_substitutions", [])
    overlay = json.loads(gcs.read_text_raw(gcs.overlay_path(_REPO_ROOT, pair)))
    a = gcs.generate(canonical_text, subs, overlay)
    b = gcs.generate(canonical_text, subs, overlay)
    assert a == b


# ---------------------------------------------------------------------------
# Overlay schema validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pair", _pairs(), ids=lambda p: gcs.pair_name(p))
def test_committed_overlays_are_schema_valid(pair):
    canonical_text = gcs.read_text_raw(_REPO_ROOT / pair["canonical"])
    overlay = json.loads(gcs.read_text_raw(gcs.overlay_path(_REPO_ROOT, pair)))
    assert gcs.validate_overlay(overlay, canonical_text) == []


def test_validate_overlay_flags_unknown_op():
    problems = gcs.validate_overlay({"canonical": "c", "derived": "d",
                                     "directives": [{"op": "bogus"}]})
    assert any("unknown op" in p for p in problems)


def test_validate_overlay_flags_stale_canonical_heading():
    canonical_text = "## Real\r\nx\r\n"
    overlay = {"canonical": "c", "derived": "d",
               "directives": [{"op": "canonical", "heading": "## Gone"}]}
    problems = gcs.validate_overlay(overlay, canonical_text)
    assert any("not found in canonical" in p for p in problems)


def test_validate_overlay_flags_missing_required_keys():
    problems = gcs.validate_overlay({"directives": []})
    assert any("canonical" in p for p in problems)
    assert any("derived" in p for p in problems)


def test_generate_raises_on_stale_canonical_directive():
    canonical_text = "## Real\r\nx\r\n"
    overlay = {"canonical": "c", "derived": "d",
               "directives": [{"op": "canonical", "heading": "## Gone"}]}
    with pytest.raises(gcs.GenError):
        gcs.generate(canonical_text, [], overlay)


# ---------------------------------------------------------------------------
# Canonical edit propagates through 'canonical' directives (the maintenance win)
# ---------------------------------------------------------------------------

def test_canonical_edit_propagates_through_canonical_directive():
    canonical_v1 = "## Shared\r\nlazy-state.py drives this\r\n"
    subs = [{"canonical": "lazy-state.py", "derived": "bug-state.py"}]
    # Derived is the token-substituted canonical -> extracts as a canonical directive.
    derived = gcs.apply_tokens(canonical_v1, subs)
    directives = gcs.build_directives(canonical_v1, derived, subs)
    assert directives == [{"op": "canonical", "heading": "## Shared"}]
    overlay = {"canonical": "c", "derived": "d", "directives": directives}
    # Edit the canonical body; regenerate WITHOUT touching the overlay.
    canonical_v2 = "## Shared\r\nlazy-state.py drives this NOW WITH A FIX\r\n"
    regenerated = gcs.generate(canonical_v2, subs, overlay)
    assert regenerated == "## Shared\r\nbug-state.py drives this NOW WITH A FIX\r\n"


# ---------------------------------------------------------------------------
# Fixture-repo helper
# ---------------------------------------------------------------------------

def _stage_fixture_repo(root: Path, *, derived_body: str) -> None:
    """Create a minimal repo tree with one coupled pair + extracted overlay."""
    (root / "user" / "skills" / "canon").mkdir(parents=True)
    (root / "user" / "skills" / "deriv").mkdir(parents=True)
    (root / "user" / "scripts" / "coupled-overlays").mkdir(parents=True)
    canonical = root / "user" / "skills" / "canon" / "SKILL.md"
    derived = root / "user" / "skills" / "deriv" / "SKILL.md"
    gcs.write_text_raw(canonical, "## H\r\nORIGINAL\r\n")
    gcs.write_text_raw(derived, derived_body)
    manifest = {
        "mechanic_sets": {},
        "pairs": [{
            "canonical": "user/skills/canon/SKILL.md",
            "derived": "user/skills/deriv/SKILL.md",
            "overlay": "user/scripts/coupled-overlays/deriv.overlay.json",
            "token_substitutions": [],
        }],
    }
    gcs.write_text_raw(
        root / "user" / "scripts" / "lazy-parity-manifest.json",
        json.dumps(manifest, indent=2) + "\n",
    )
    # Extract the overlay from the staged (canonical, derived) pair.
    gcs.cmd_extract(manifest, root, None)
