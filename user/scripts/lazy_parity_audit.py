"""
lazy_parity_audit.py — Parity audit engine for lazy-batch derived skill pairs.

Checks C1–C6 for each pair in lazy-parity-manifest.json:
  C1 — Every canonical heading has a headings[] manifest entry.
  C2 — Every restated/inherited heading's evidence resolves in the derived file.
  C3 — Every mechanic pattern is present in the derived file (unless overridden).
  C4 — No stale manifest entries: headings/mechanic_overrides referencing absent items.
  C5 — Reason hygiene: divergence entries must have a reason; restated/inherited must not.
  C6 — Soft (stderr only): divergence doc_anchor text not found in derived prose.

Public API:
  load_manifest(repo_root) -> dict
  audit_pair(repo_root, pair_name, manifest=None) -> list[str]
  audit_all_pairs(repo_root, manifest=None) -> list[str]

CLI:
  python3 lazy_parity_audit.py --repo-root <path> [--pair <pair_name>]
  Exit 0 if no findings, 1 if findings exist.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_manifest(repo_root: str | Path) -> dict:
    """Read and return the lazy-parity-manifest.json located under repo_root."""
    manifest_path = Path(repo_root) / "user" / "scripts" / "lazy-parity-manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Token substitution
# ---------------------------------------------------------------------------

def apply_tokens(text: str, subs: list[dict]) -> str:
    """
    Replace canonical vocab with derived vocab in text.
    Substitutions are applied in array order so order-dependent replacements
    (e.g. 'lazy-state.py' before 'lazy-batch') are respected.

    When applying substitutions to regex evidence strings or mechanic patterns,
    the canonical token may appear in regex-escaped form (e.g. 'COMPLETED.md'
    stored as 'COMPLETED\\.md' in the evidence regex).  We therefore try BOTH
    the literal canonical token AND its re.escape() form so that substitutions
    work regardless of whether the evidence is written in plain or regex-escaped
    canonical vocab.
    """
    for s in subs:
        canonical = s["canonical"]
        derived = s["derived"]
        # Literal replacement (covers plain-text tokens and mechanic patterns).
        text = text.replace(canonical, derived)
        # Regex-escaped replacement (covers evidence strings where '.' → '\\.').
        escaped_canonical = re.escape(canonical)
        escaped_derived = re.escape(derived)
        if escaped_canonical != canonical:
            # Only bother if the escaped form differs from the literal form,
            # i.e. the token contains regex-special characters (like '.').
            text = text.replace(escaped_canonical, escaped_derived)
    return text


# ---------------------------------------------------------------------------
# Heading enumeration (canonical)
# ---------------------------------------------------------------------------

def _enumerate_headings(text: str) -> list[str]:
    """
    Return all ## / ### headings from text, each rstrip()-normalized.
    Pattern: any line starting with 2-3 '#' followed by a space and text.
    """
    raw = re.findall(r"(?m)^#{2,3} .*$", text)
    return [h.rstrip() for h in raw]


# ---------------------------------------------------------------------------
# Core audit per pair
# ---------------------------------------------------------------------------

def audit_pair(
    repo_root: str | Path,
    pair_name: str,
    manifest: dict | None = None,
) -> list[str]:
    """
    Run checks C1–C5 for the single pair whose derived-skill directory name
    equals pair_name.  C6 warnings are written to stderr only and never
    appear in the returned findings list.

    Parameters
    ----------
    repo_root : str or Path
        Root of the repository; all canonical/derived paths in the manifest
        are resolved relative to this directory.
    pair_name : str
        The directory name of the derived skill
        (Path(pair["derived"]).parent.name).
    manifest : dict or None
        If None, load from <repo_root>/user/scripts/lazy-parity-manifest.json.
        If a dict, use it directly (useful for hermetic fixture tests).

    Returns
    -------
    list[str]
        One string per finding; empty means the pair is clean.
    """
    repo_root = Path(repo_root)

    if manifest is None:
        manifest = load_manifest(repo_root)

    # Locate the pair whose derived directory name matches pair_name.
    pair = None
    for p in manifest.get("pairs", []):
        if Path(p["derived"]).parent.name == pair_name:
            pair = p
            break

    if pair is None:
        return [
            f"lazy-parity [{pair_name}] ERROR: no pair with derived dir '{pair_name}' found in manifest"
        ]

    # Resolve file paths relative to repo_root.
    canonical_path = repo_root / pair["canonical"]
    derived_path = repo_root / pair["derived"]

    # Read files with universal-newline normalization (\r\n → \n).
    canonical_text = canonical_path.read_text(encoding="utf-8")
    derived_text = derived_path.read_text(encoding="utf-8")

    # Token substitutions for this pair (may be absent).
    subs: list[dict] = pair.get("token_substitutions", [])

    # Mechanic set for this pair.
    mechanic_set_name: str = pair.get("mechanic_set", "")
    mechanics: list[dict] = manifest.get("mechanic_sets", {}).get(mechanic_set_name, [])

    # Per-pair mechanic overrides.
    mechanic_overrides: list[dict] = pair.get("mechanic_overrides", [])
    # Build a set of mechanic ids suppressed by divergence override.
    suppressed_mechanic_ids: set[str] = {
        ov["id"]
        for ov in mechanic_overrides
        if ov.get("coverage") == "divergence"
    }

    # Canonical heading list (rstrip-normalized).
    canon_headings: list[str] = _enumerate_headings(canonical_text)
    canon_heading_set: set[str] = set(canon_headings)

    # Manifest headings[] entries.
    heading_entries: list[dict] = pair.get("headings", [])

    findings: list[str] = []

    # -------------------------------------------------------------------
    # C1 — Tier-1 completeness
    # Every canonical heading must have a corresponding headings[] entry.
    # -------------------------------------------------------------------
    manifest_heading_keys: set[str] = {e["heading"].rstrip() for e in heading_entries}

    for heading in canon_headings:
        if heading not in manifest_heading_keys:
            findings.append(
                f"lazy-parity [{pair_name}] C1: canonical heading {heading!r} has no headings[] entry"
            )

    # -------------------------------------------------------------------
    # C2 — Coverage resolves
    # For restated/inherited entries, the evidence regex must match the
    # derived text (after applying token substitutions to the evidence string).
    # -------------------------------------------------------------------
    for entry in heading_entries:
        coverage = entry.get("coverage")
        if coverage not in ("restated", "inherited"):
            # Skip divergence entries — C2 does not apply to them.
            continue

        heading_text = entry.get("heading", "")
        evidence = entry.get("evidence", "")

        # If evidence is absent, treat as C2 failure per spec.
        if not evidence:
            findings.append(
                f"lazy-parity [{pair_name}] C2: heading {heading_text!r} evidence missing/empty — cannot verify in derived"
            )
            continue

        # Apply token substitutions to the canonical-vocab evidence string
        # before searching the derived file text.
        pattern = apply_tokens(evidence, subs)
        if re.search(pattern, derived_text) is None:
            findings.append(
                f"lazy-parity [{pair_name}] C2: heading {heading_text!r} evidence {pattern!r} not found in derived"
            )

    # -------------------------------------------------------------------
    # C3 — Tier-2 predicates (mechanics)
    # Each mechanic pattern must appear in the derived file unless the pair
    # has a mechanic_override entry for that id with coverage='divergence'.
    # -------------------------------------------------------------------
    for mech in mechanics:
        mech_id = mech["id"]
        if mech_id in suppressed_mechanic_ids:
            # Explicitly overridden as divergence — skip C3 for this mechanic.
            continue

        pattern = apply_tokens(mech["assert"]["pattern"], subs)
        if re.search(pattern, derived_text) is None:
            findings.append(
                f"lazy-parity [{pair_name}] C3: mechanic {mech_id!r} pattern {pattern!r} not found in derived"
            )

    # -------------------------------------------------------------------
    # C4 — No stale divergence
    # (a) headings[] entries referencing a heading NOT in canonical.
    # (b) mechanic_overrides entries whose id is NOT in the pair's mechanic_set.
    # -------------------------------------------------------------------
    mechanic_ids_in_set: set[str] = {m["id"] for m in mechanics}

    for entry in heading_entries:
        heading_text = entry.get("heading", "").rstrip()
        if heading_text not in canon_heading_set:
            findings.append(
                f"lazy-parity [{pair_name}] C4: headings[] entry {heading_text!r} not found in canonical"
            )

    for ov in mechanic_overrides:
        ov_id = ov.get("id", "")
        if ov_id not in mechanic_ids_in_set:
            findings.append(
                f"lazy-parity [{pair_name}] C4: mechanic_override id {ov_id!r} not in mechanic_set {mechanic_set_name!r}"
            )

    # -------------------------------------------------------------------
    # C5 — Reason hygiene
    # divergence entries must have a non-empty reason.
    # restated/inherited entries must NOT have a reason key.
    # -------------------------------------------------------------------
    for entry in heading_entries:
        coverage = entry.get("coverage")
        heading_text = entry.get("heading", "")
        reason = entry.get("reason")

        if coverage == "divergence":
            # Must have a non-empty reason.
            if not reason:
                findings.append(
                    f"lazy-parity [{pair_name}] C5: divergence entry {heading_text!r} missing required 'reason'"
                )
        elif coverage in ("restated", "inherited"):
            # Must NOT have a reason key.
            if "reason" in entry:
                findings.append(
                    f"lazy-parity [{pair_name}] C5: restated/inherited entry {heading_text!r} has unexpected 'reason' key"
                )

    # -------------------------------------------------------------------
    # C6 — Soft (stderr only)
    # For divergence entries with a doc_anchor, warn if the anchor text is
    # absent from the derived prose.  Never append to findings.
    # -------------------------------------------------------------------
    for entry in heading_entries:
        if entry.get("coverage") != "divergence":
            continue
        doc_anchor = entry.get("doc_anchor")
        if doc_anchor and doc_anchor not in derived_text:
            print(
                f"C6 warning [{pair_name}]: doc_anchor {doc_anchor!r} not found in derived prose",
                file=sys.stderr,
            )

    return findings


# ---------------------------------------------------------------------------
# State-script parity (multi-repo-concurrent-runs WU-3.2)
# ---------------------------------------------------------------------------

# The shared per-repo state-dir surface that BOTH state scripts must wire at
# main() so claude_state_dir() scopes every run-scoped file (marker / registry /
# deny-ledger / cycle marker / checkpoint) to the active repo's keyed subdir.
# bug-state.py inherits the keyed dir purely by importing lazy_core, but it MUST
# still bind the active repo from --repo-root at main() — otherwise it resolves
# the cwd fallback instead of the orchestrator-supplied repo.  This check makes
# a silent drop of that binding a hard finding.
_STATE_SCRIPTS: tuple[str, ...] = ("lazy-state.py", "bug-state.py")
_ACTIVE_REPO_BINDING_RE = re.compile(
    r"(?:lazy_core\.)?set_active_repo_root\(\s*args\.repo_root\s*\)"
)


def audit_state_script_parity(repo_root: str | Path) -> list[str]:
    """Assert the shared per-repo state-dir surface is consistent across the
    feature and bug state scripts: each must call
    ``set_active_repo_root(args.repo_root)`` at main().  Returns one finding per
    script missing the binding; empty means parity holds.

    This is additive — it audits the Python state machines (not the SKILL.md
    pairs) and runs alongside the manifest pair audit in the default (no
    ``--pair``) invocation.
    """
    repo_root = Path(repo_root)
    findings: list[str] = []
    for script in _STATE_SCRIPTS:
        path = repo_root / "user" / "scripts" / script
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                f"lazy-parity [state-scripts] ERROR: cannot read {script}: {exc}"
            )
            continue
        if _ACTIVE_REPO_BINDING_RE.search(text) is None:
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must call "
                f"set_active_repo_root(args.repo_root) at main() so "
                f"claude_state_dir() scopes run-scoped state per repo "
                f"(multi-repo-concurrent-runs parity)"
            )
    return findings


# ---------------------------------------------------------------------------
# Audit all pairs
# ---------------------------------------------------------------------------

def audit_all_pairs(
    repo_root: str | Path,
    manifest: dict | None = None,
) -> list[str]:
    """
    Run audit_pair for every pair in the manifest and return the concatenated
    findings list.  Empty list means all pairs are clean.  Also runs the
    state-script parity check (the shared per-repo state-dir binding).
    """
    repo_root = Path(repo_root)

    if manifest is None:
        manifest = load_manifest(repo_root)

    all_findings: list[str] = []
    for pair in manifest.get("pairs", []):
        pair_name = Path(pair["derived"]).parent.name
        all_findings.extend(audit_pair(repo_root, pair_name, manifest=manifest))

    # State-script parity (multi-repo-concurrent-runs): runs in the default
    # whole-repo audit, independent of the SKILL.md manifest pairs.
    all_findings.extend(audit_state_script_parity(repo_root))

    return all_findings


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Audit parity between canonical and derived lazy-batch SKILL.md pairs.",
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root (parent of user/).",
    )
    parser.add_argument(
        "--pair",
        default=None,
        help=(
            "Derived skill directory name (e.g. 'lazy-bug-batch'). "
            "If omitted, audit ALL pairs."
        ),
    )
    args = parser.parse_args()

    manifest = load_manifest(args.repo_root)

    if args.pair:
        findings = audit_pair(args.repo_root, args.pair, manifest=manifest)
    else:
        findings = audit_all_pairs(args.repo_root, manifest=manifest)

    for finding in findings:
        print(finding)

    sys.exit(1 if findings else 0)
