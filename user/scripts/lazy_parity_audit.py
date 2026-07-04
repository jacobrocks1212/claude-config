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
# no-sanctioned-queue-reorder-command Phase 4: the operator-only --reorder-queue
# subcommand is a coupled-pair surface — a primitive added to one state script
# must appear in the other to stay green.  Match the argparse flag literal.
_REORDER_QUEUE_RE = re.compile(r'"--reorder-queue"')
# single-slot-marker-ownership-race-disarms-owning-run Phase 2: the orchestrator-
# only --reassert-owner subcommand (owner re-arm of a foreign-stamped marker) is
# likewise a coupled-pair surface — the run marker is SHARED between pipelines, so
# the re-claim action added to one state script must appear in the other.
_REASSERT_OWNER_RE = re.compile(r'"--reassert-owner"')
# intervention-efficacy-tracking Phase 1: the orchestrator-only
# --record-intervention subcommand (hypothesis-ledger capture for the manual /
# hardening-round / D9-backfill paths; the completion-gate capture itself lives
# in the SHARED lazy_core.apply_pseudo, parity by construction) is a
# coupled-pair CLI surface — present on both state scripts.
_RECORD_INTERVENTION_RE = re.compile(r'"--record-intervention"')
# host-capability-declaration-for-gated-features Phase 6: the requires_host:
# PARSE + the unregistered-id FAIL-FAST is a MIRRORED coupled-pair surface — a
# requires_host: id with no registry probe could never be present on ANY host, so
# a silent defer would strand the item in infinite queue starvation; BOTH state
# scripts must fail fast (canonical BLOCKED.md, blocker_kind:
# unknown-host-capability) using the SHARED lazy_core.format_unknown_host_capability_blocker
# body formatter. A drop of the fail-fast from one script is a hard finding here.
#
# JUSTIFIED DIVERGENCE (NOT audited as a missing surface): the feature pipeline's
# capability-MISS DEFER (DEFERRED_REQUIRES_HOST.md skip + the
# host-capability-saturated terminal) is feature-pipeline-shaped (queue-selection
# curation). bug-state.py intentionally does NOT expose that branch — it has only
# the single device axis in v1. The SHARED lazy_core helpers (parse_requires_host,
# unknown_capability_ids, format_unknown_host_capability_blocker,
# write_deferred_requires_host) do not diverge; only the bug pipeline's *use* of
# the miss-defer is absent. So this audit checks ONLY the mirrored fail-fast, not
# the (correctly feature-only) miss-defer.
_HOST_CAPABILITY_FAILFAST_RE = re.compile(
    r"format_unknown_host_capability_blocker"
)
_HOST_CAPABILITY_BLOCKER_KIND_RE = re.compile(r"unknown-host-capability")
# bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref Phase 2: the
# cycle_prompt_ref surfacing assignment is a MIRRORED coupled-pair surface —
# both scripts must assign state["cycle_prompt_ref"] in their --emit-prompt
# path so the orchestrator receives the @@lazy-ref dispatch token.  A drop of
# the assignment from either script is a hard finding here.
_CYCLE_PROMPT_REF_RE = re.compile(r'state\["cycle_prompt_ref"\]\s*=')
# queue-dependency-dag Phase 5: the orchestrator-only --sync-deps subcommand
# (the SPEC dep-block → queue `deps` feeder, D5) is a coupled-pair surface —
# the dep-gate enforces the field on BOTH pipelines, so the script-owned
# writer must exist on both state scripts (a drop from one would leave that
# pipeline's queue deps stuck in manual-edit territory, violating the
# no-hand-edit-queue.json HARD CONSTRAINT).  Match the argparse flag literal.
_SYNC_DEPS_RE = re.compile(r'"--sync-deps"')
# operator-halt-notifications Phase 2: the terminal-emission notify_halt call
# site (surface #7) is a MIRRORED coupled-pair surface — every halt on either
# pipeline flows through main()'s state-JSON write, so BOTH scripts must call
# lazy_core.notify_halt(state, ...) immediately before it. A drop from one
# script would silently un-page that pipeline's halts (the exact
# time-to-notice gap the feature closes).  Match the call literal.
_NOTIFY_HALT_RE = re.compile(r"lazy_core\.notify_halt\(")


def audit_state_script_parity(repo_root: str | Path) -> list[str]:
    """Assert the shared per-repo state-dir surface is consistent across the
    feature and bug state scripts: each must call
    ``set_active_repo_root(args.repo_root)`` at main(), each must carry the
    operator-only ``--reorder-queue`` subcommand, each must carry the
    orchestrator-only ``--reassert-owner`` subcommand, each must carry the
    orchestrator-only ``--sync-deps`` feeder (queue-dependency-dag coupled-pair
    parity), AND each must carry the ``lazy_core.notify_halt(...)``
    terminal-emission call site (operator-halt-notifications coupled-pair
    parity, surface #7).
    Returns one finding per script missing any surface; empty means parity holds.

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
        if _REORDER_QUEUE_RE.search(text) is None:
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must carry the "
                f"operator-only --reorder-queue subcommand (calls "
                f"lazy_core.reorder_queue, gated by refuse_if_cycle_active) so "
                f"both state scripts expose the same queue-mutation surface "
                f"(no-sanctioned-queue-reorder-command coupled-pair parity)"
            )
        if _REASSERT_OWNER_RE.search(text) is None:
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must carry the "
                f"orchestrator-only --reassert-owner subcommand (calls "
                f"lazy_core.reassert_marker_owner, gated by refuse_if_cycle_active) "
                f"so both state scripts expose the same shared-marker re-arm "
                f"surface (single-slot-marker-ownership-race coupled-pair parity)"
            )
        if _RECORD_INTERVENTION_RE.search(text) is None:
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must carry the "
                f"orchestrator-only --record-intervention subcommand (calls "
                f"lazy_core.record_intervention, gated by refuse_if_cycle_active) "
                f"so both state scripts expose the same hypothesis-ledger capture "
                f"surface (intervention-efficacy-tracking coupled-pair parity)"
            )
        if (
            _HOST_CAPABILITY_FAILFAST_RE.search(text) is None
            or _HOST_CAPABILITY_BLOCKER_KIND_RE.search(text) is None
        ):
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must carry the "
                f"requires_host: unregistered-id FAIL-FAST (calls "
                f"lazy_core.format_unknown_host_capability_blocker, writes a "
                f"canonical BLOCKED.md with blocker_kind: unknown-host-capability) "
                f"so both state scripts fail fast on an unprobeable capability id "
                f"instead of silently deferring forever "
                f"(host-capability-declaration-for-gated-features coupled-pair parity)"
            )
        if _SYNC_DEPS_RE.search(text) is None:
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must carry the "
                f"orchestrator-only --sync-deps subcommand (calls "
                f"lazy_core.sync_deps, gated by refuse_if_cycle_active) so both "
                f"state scripts expose the same script-owned SPEC-dep-block → "
                f"queue-deps feeder (queue-dependency-dag coupled-pair parity)"
            )
        if _CYCLE_PROMPT_REF_RE.search(text) is None:
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must assign "
                f'state["cycle_prompt_ref"] in its --emit-prompt path so the '
                f"orchestrator receives the @@lazy-ref dispatch token (49-char "
                f"reference) instead of re-inlining the full cycle prompt "
                f"(bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref coupled-pair "
                f"parity)"
            )
        if _NOTIFY_HALT_RE.search(text) is None:
            findings.append(
                f"lazy-parity [state-scripts] STATE: {script} must call "
                f"lazy_core.notify_halt(state, ...) at the terminal-emission "
                f"chokepoint in main() (immediately before the state-JSON "
                f"write) so halts on both pipelines page the operator "
                f"(operator-halt-notifications coupled-pair parity)"
            )
    return findings


# ---------------------------------------------------------------------------
# Merged-view dispatch parity (unified-pipeline-orchestrator Phase 2)
# ---------------------------------------------------------------------------

# Phase 2 makes /lazy-batch the shared driver looping over the Phase-1 merged
# view (`lazy-state.py --next-merged`), type-dispatching each cycle to
# lazy-state.py (feature → __mark_complete__) or bug-state.py (bug →
# __mark_fixed__).  The merged-view dispatch branch must be present + consistent
# across the workstation driver AND its cloud mirror (coupled-pair rule), it must
# document type-correct terminals, and it must preserve single-type behavior
# (the no-regression guarantee).  This is a docs-consistency check over the
# SKILL.md prose — it never re-implements ordering (lazy_core.merged_priority is
# the single source of "bugs break ties") and never runs a pipeline.

# The unified-driver pair: (name, repo-relative SKILL.md path).  Both the
# workstation canonical driver and its cloud mirror carry the merged-view branch.
_MERGED_VIEW_DRIVER_FILES: tuple[tuple[str, str], ...] = (
    ("lazy-batch", "user/skills/lazy-batch/SKILL.md"),
    ("lazy-batch-cloud", "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md"),
)

# Each predicate is (probe regex, human label) that the merged-view dispatch
# branch must satisfy in EACH driver.  Consistency = every driver passes every
# predicate; an asymmetry (one driver missing a predicate the other has) is the
# coupled-pair drift this audit guards against.
_MERGED_VIEW_PREDICATES: tuple[tuple[str, str], ...] = (
    # (a) the merged-view probe surface is referenced.
    (r"--next-merged", "next-merged probe surface"),
    # (b) the feature-type terminal action is named in the dispatch branch.
    (r"__mark_complete__", "feature terminal __mark_complete__"),
    # (c) the bug-type terminal action is named in the dispatch branch.
    (r"__mark_fixed__", "bug terminal __mark_fixed__"),
    # (d) the bug state script is named as the bug-type dispatch target.
    (r"bug-state\.py", "bug-state.py dispatch target"),
    # (e) the single-type no-regression guarantee is asserted.
    (r"[Ss]ingle-type\b", "single-type no-regression guarantee"),
    # (f) the bug __mark_fixed__ terminal chains the --archive-fixed follow-up
    #     (lazy-batch-unified-driver-parity-and-accounting Phase 3, item 2): the
    #     unified driver AND its cloud mirror must archive + de-queue a fixed bug
    #     exactly as /lazy-bug-batch does.  A driver dropping the chain is the
    #     SPEC Coupling/parity drift this predicate guards against.
    (r"--archive-fixed", "bug archive --archive-fixed chain"),
)


def audit_merged_view_dispatch_parity(repo_root: str | Path) -> list[str]:
    """Assert the merged-view dispatch branch (unified-pipeline-orchestrator
    Phase 2) is present + consistent across the workstation driver and its cloud
    mirror.

    For each driver, every predicate in ``_MERGED_VIEW_PREDICATES`` must hold;
    a missing predicate is one finding.  Consistency across the pair is implied:
    because the SAME predicate set is applied to BOTH drivers, an asymmetry
    (one driver carries the merged-view branch, the other does not) surfaces as
    a finding against whichever driver is missing the predicate.

    Returns one finding per (driver, missing-predicate); empty means parity
    holds.  Additive — audits the SKILL.md prose, not the manifest pairs, and
    runs alongside the manifest pair audit + state-script parity in the default
    (no ``--pair``) invocation.
    """
    repo_root = Path(repo_root)
    findings: list[str] = []
    for name, rel_path in _MERGED_VIEW_DRIVER_FILES:
        path = repo_root / rel_path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                f"lazy-parity [merged-view] ERROR: cannot read {name} ({rel_path}): {exc}"
            )
            continue
        for pattern, label in _MERGED_VIEW_PREDICATES:
            if re.search(pattern, text) is None:
                findings.append(
                    f"lazy-parity [merged-view] {name}: missing {label} "
                    f"(pattern {pattern!r}) — the unified merged-view dispatch "
                    f"branch must be present + mirrored across the coupled pair "
                    f"(unified-pipeline-orchestrator Phase 2)"
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

    # Merged-view dispatch parity (unified-pipeline-orchestrator Phase 2): the
    # unified driver + its cloud mirror must carry a consistent merged-view
    # dispatch branch with type-correct terminals + the single-type no-regression
    # guarantee.  Also additive to the default whole-repo audit.
    all_findings.extend(audit_merged_view_dispatch_parity(repo_root))

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
    parser.add_argument(
        "--merged-view",
        action="store_true",
        help=(
            "Run ONLY the merged-view dispatch parity check "
            "(unified-pipeline-orchestrator Phase 2): the unified driver + its "
            "cloud mirror must carry a consistent merged-view dispatch branch."
        ),
    )
    args = parser.parse_args()

    if args.merged_view:
        # Targeted merged-view audit — no manifest needed (audits SKILL.md prose).
        findings = audit_merged_view_dispatch_parity(args.repo_root)
    elif args.pair:
        manifest = load_manifest(args.repo_root)
        findings = audit_pair(args.repo_root, args.pair, manifest=manifest)
    else:
        manifest = load_manifest(args.repo_root)
        findings = audit_all_pairs(args.repo_root, manifest=manifest)

    for finding in findings:
        print(finding)

    sys.exit(1 if findings else 0)
