#!/usr/bin/env python3
"""skill-size-ratchet.py — per-file byte + long-line ratchet lint for skill files.

lazy-batch-skill-deflation Phase 3 (D3): the observed failure mode is that a skill
file's growth curve (+57% in four weeks, 126 commits, on `user/skills/lazy-batch/SKILL.md`
alone) never reverses without a gate — advisory output "demonstrably does not hold
this line" (SPEC D3). This script is that gate: a small, opt-in, committed baseline
JSON (`user/scripts/skill-size-baseline.json`) records a byte ceiling + a long-line
(>500 chars) count ceiling per file; `--check` fails loudly (named file + metric +
current vs. ceiling) when either is exceeded.

Semantics (mirrors the AlgoBooth composite-score gate precedent):
  - Growth past baseline FAILS `--check` (exit 1). This is the whole point.
  - Improvement (current <= ceiling on BOTH metrics) never auto-lowers the
    ceiling — that requires an explicit `--lock-in <path>` (or `--lock-in --all`),
    so a transient deletion can't silently set an unreachable bar for the next
    legitimate addition.
  - `--lock-in` REFUSES to raise a ceiling — it only ever sets
    new_ceiling = min(current, existing_ceiling). Deliberately RAISING a ceiling
    (a legitimate new HARD CONSTRAINT that grows the file) is a manual, reviewable
    edit to the baseline JSON, never a CLI mutation.
  - Opt-in per file: a file not listed in the baseline is invisible to this gate
    (ordinary small skills carry no ceremony). Listing a new file is a manual
    baseline-JSON edit (`--lock-in --new <path>` seeds an entry at the file's
    CURRENT size so a first-time enrollment never fails its own gate).

Long-line census matches the SPEC's method: a "long line" is a line whose length
(character count, not byte count) exceeds 500 — the same threshold used in the
SPEC's inline recon.

Stdlib only. Read-only except `--lock-in`, whose write goes through
`lazy_core._atomic_write` (the repo's one-writer convention for structured JSON).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lazy_core  # noqa: E402  (sibling import, path bootstrap above)

SCHEMA_VERSION = 1
LONG_LINE_THRESHOLD = 500
DEFAULT_BASELINE_NAME = "skill-size-baseline.json"


def default_baseline_path() -> Path:
    return _SCRIPTS_DIR / DEFAULT_BASELINE_NAME


def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "files": {}}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "files" not in data or not isinstance(data["files"], dict):
        raise ValueError(f"malformed baseline JSON at {path}: expected {{'files': {{...}}}}")
    return data


def measure(repo_root: Path, rel_path: str) -> tuple[int, int]:
    """Return (byte_count, long_line_count) for a file, or raise FileNotFoundError."""
    full = repo_root / rel_path
    data = full.read_bytes()
    text = data.decode("utf-8", errors="replace")
    long_lines = sum(1 for line in text.splitlines() if len(line) > LONG_LINE_THRESHOLD)
    return len(data), long_lines


# ---------------------------------------------------------------------------
# Assembled-cycle-prompt profile measurement (cycle-prompt-deflation Phase 1)
#
# Extends the whole-FILE ratchet above to the ASSEMBLED per-cycle dispatch
# prompt. A "profile" is a concrete dispatchable cycle tuple
# (pipeline, mode, skill[, variant]); its assembled bytes are produced by
# driving the REAL emitter `lazy_core.emit_cycle_prompt` — never by re-parsing
# `cycle-base-prompt.md` and never by forking the emitter (the CLAUDE.md
# "a projection can never drift from the parser it introspects" convention).
#
# park/host profile dimensions are intentionally OUT of the v1 enumeration: the
# SPEC's KPI selector census is over "(pipeline,mode,skill,variant) profiles",
# and the host dimension is resolved implicitly by the emitter from the live
# os.name at measure time (hosts=windows sections are included on this box).
# ---------------------------------------------------------------------------

# A skill name guaranteed NOT to match any dedicated (non-`all`) @section, so a
# "generic" profile measures the pure skills=all boilerplate shape shared by
# every cycle whose skill carries no dedicated section (spec-phases, write-plan,
# plan-feature, spec, …). It is a real dispatch skill, so the emitter assembles.
_GENERIC_SKILL = "spec-phases"

_PIPELINES = ("feature", "bug")
_MODES = ("workstation", "cloud")

# A CANONICAL, deliberately-non-existent repo root used for the emit call so the
# measured byte count reflects the TEMPLATE PROSE + section selection ONLY — the
# deflation target — and NOT the machine's repo path. The emitter binds {cwd} to
# str(repo_root) and {work_branch} via `git -C repo_root` (19 combined
# occurrences in the template): a real repo root makes the count vary with the
# checkout path length (a longer path would false-trip the ratchet on another
# machine). This fixed root gives a stable {cwd} and forces the deterministic
# work-branch fallback ("the current branch"), so the seed ceilings are portable.
# (The measurement is still host-sensitive via os.name for hosts=windows
# sections — but a non-Windows host only ever measures FEWER bytes, i.e. stays
# under a Windows-seeded ceiling, so that never false-trips. claude-config has no
# `.claude/skill-config/cycle-prompt-addenda.md`, so no repo addenda is dropped.)
_MEASURE_REPO_ROOT = "__cycle-prompt-measure__"


def _profile_id(profile: dict) -> str:
    """Stable id string for a profile, e.g. ``feature/workstation/execute-plan``
    or ``feature/workstation/mcp-test/no-runtime``."""
    parts = [profile["pipeline"], profile["mode"], profile["skill"]]
    if profile.get("variant"):
        parts.append(profile["variant"])
    return "/".join(parts)


def _named_dispatch_skills(sections: list[dict]) -> set[str]:
    """The skills carrying a dedicated NON-park @section (their assembled size
    genuinely differs from the generic skills=all shape). park-only sections
    (park=park) do NOT drive enumeration — a non-park cycle never selects them,
    so such a skill's non-park assembly equals the generic shape."""
    named: set[str] = set()
    for sec in sections:
        attrs = sec["attrs"]
        skills = attrs.get("skills", "")
        if not skills or skills == "all":
            continue
        if attrs.get("park") == "park":
            continue
        named |= lazy_core._csv_set(skills)
    return named


def _skill_has_section(sections: list[dict], pipeline: str, mode: str, skill: str) -> bool:
    """True iff a dedicated non-park @section for *skill* matches (pipeline, mode)."""
    for sec in sections:
        attrs = sec["attrs"]
        skills = attrs.get("skills", "")
        if not skills or skills == "all" or attrs.get("park") == "park":
            continue
        if pipeline not in lazy_core._csv_set(attrs.get("pipelines")):
            continue
        if mode not in lazy_core._csv_set(attrs.get("modes")):
            continue
        if skill in lazy_core._csv_set(skills):
            return True
    return False


def _cycle_template_dir(template_dir: Path | None) -> Path:
    return template_dir if template_dir is not None else lazy_core._default_cycle_template_dir()


def enumerate_profiles(template_dir: Path | None = None) -> list[dict]:
    """Derive the concrete dispatchable cycle profiles from the @section matrix.

    Deterministic + template-driven (never hand-guessed):
      - one GENERIC profile per (pipeline, mode) — the skills=all boilerplate shape;
      - one profile per named-dispatch skill × (pipeline, mode) where that skill
        carries a dedicated non-park section for that combination;
      - the two mcp-test runtime variants (runtime-up / no-runtime) instead of a
        bare mcp-test profile.
    """
    base_path = _cycle_template_dir(template_dir) / "cycle-base-prompt.md"
    sections = lazy_core._parse_cycle_template(base_path.read_text(encoding="utf-8"))
    named = _named_dispatch_skills(sections)

    profiles: list[dict] = []
    for pipeline in _PIPELINES:
        for mode in _MODES:
            profiles.append({"pipeline": pipeline, "mode": mode, "skill": _GENERIC_SKILL})
    for skill in sorted(named):
        for pipeline in _PIPELINES:
            for mode in _MODES:
                if not _skill_has_section(sections, pipeline, mode, skill):
                    continue
                if skill == "mcp-test":
                    for variant in ("runtime-up", "no-runtime"):
                        profiles.append({
                            "pipeline": pipeline, "mode": mode,
                            "skill": skill, "variant": variant,
                        })
                else:
                    profiles.append({"pipeline": pipeline, "mode": mode, "skill": skill})
    return profiles


def _profile_state(profile: dict, spec_path: str | None) -> dict:
    """Synthesize the minimal `compute_state`-shaped dict emit_cycle_prompt reads."""
    return {
        "feature_id": "profile-measure",
        "feature_name": "Assembled-profile measurement",
        "spec_path": spec_path,
        "current_step": "Step: assembled-profile measurement",
        "sub_skill": profile["skill"],
        "sub_skill_args": "",
    }


def measure_assembled_profile(
    repo_root: Path, profile: dict, *, template_dir: Path | None = None
) -> tuple[int | None, int | None, str | None]:
    """Drive the real emitter for one profile and return
    ``(byte_count, long_line_count, note)``.

    A refusing/``None`` emitter result is surfaced HONESTLY as
    ``(None, None, <note>)`` — NEVER counted as 0 bytes (a refusal is a distinct
    outcome from an empty prompt). The mcp-test variant is controlled by seeding
    a throwaway ``PHASES.md`` (``**MCP runtime:** not-required`` for no-runtime;
    absent → runtime-up) that the emitter's ``_read_mcp_runtime_decision`` reads.

    ``repo_root`` is accepted for API symmetry but is NOT used for the emit — the
    measurement binds the emitter to the canonical ``_MEASURE_REPO_ROOT`` so the
    byte count is repo-path-independent (see that constant's rationale).
    """
    import tempfile

    variant = profile.get("variant")
    tmpdir = None
    spec_path: str | None = None
    try:
        if variant == "no-runtime":
            tmpdir = tempfile.mkdtemp(prefix="ratchet-profile-")
            (Path(tmpdir) / "PHASES.md").write_text(
                "**MCP runtime:** not-required — measurement fixture\n",
                encoding="utf-8",
            )
            spec_path = tmpdir
        # variant == "runtime-up" (or None): spec_path None → default runtime-up.
        state = _profile_state(profile, spec_path)
        result = lazy_core.emit_cycle_prompt(
            Path(_MEASURE_REPO_ROOT), state,
            pipeline=profile["pipeline"],
            cloud=(profile["mode"] == "cloud"),
            template_dir=_cycle_template_dir(template_dir),
        )
    finally:
        if tmpdir is not None:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    if result is None:
        return (None, None, "emitter returned None (non-dispatchable profile)")
    if not result.get("ok"):
        return (None, None, f"emitter refused: {result.get('refused')}")
    prompt = result["prompt"]
    data = prompt.encode("utf-8")
    long_lines = sum(1 for line in prompt.splitlines() if len(line) > LONG_LINE_THRESHOLD)
    return (len(data), long_lines, None)


def check_profiles(
    repo_root: Path, baseline: dict, *, template_dir: Path | None = None
) -> list[dict]:
    """Return finding dicts for assembled-profile ceilings (empty == clean).

    Mirrors ``check`` for files: each finding names the profile id, the metric,
    the current value, and the recorded ceiling. A profile the emitter refuses to
    assemble is itself a finding (``metric: refused``) — an unassemblable profile
    is a regression, never silently passed."""
    findings: list[dict] = []
    profiles = baseline.get("profiles") or {}
    for profile_id, entry in sorted(profiles.items()):
        # `_`-prefixed keys are metadata (e.g. `_notes`), never a profile.
        if profile_id.startswith("_"):
            continue
        profile = _parse_profile_id(profile_id)
        cur_bytes, cur_long_lines, note = measure_assembled_profile(
            repo_root, profile, template_dir=template_dir
        )
        if cur_bytes is None:
            findings.append({
                "profile": profile_id, "metric": "refused",
                "current": None, "ceiling": None, "note": note,
            })
            continue
        ceiling_bytes = entry.get("byte_ceiling")
        ceiling_lines = entry.get("long_line_ceiling")
        if ceiling_bytes is not None and cur_bytes > ceiling_bytes:
            findings.append({
                "profile": profile_id, "metric": "byte_ceiling",
                "current": cur_bytes, "ceiling": ceiling_bytes,
            })
        if ceiling_lines is not None and cur_long_lines > ceiling_lines:
            findings.append({
                "profile": profile_id, "metric": "long_line_ceiling",
                "current": cur_long_lines, "ceiling": ceiling_lines,
            })
    return findings


def _parse_profile_id(profile_id: str) -> dict:
    """Inverse of ``_profile_id`` — parse ``pipeline/mode/skill[/variant]``."""
    parts = profile_id.split("/")
    profile = {"pipeline": parts[0], "mode": parts[1], "skill": parts[2]}
    if len(parts) > 3:
        profile["variant"] = parts[3]
    return profile


def lock_in_profile(
    repo_root: Path, baseline_path: Path, baseline: dict, profile_id: str,
    *, seed_new: bool = False, template_dir: Path | None = None,
) -> dict:
    """Update (or seed) one profile's assembled-byte ceiling — the profile analog
    of ``lock_in``. Only ever LOWERS an existing ceiling (``min(current, existing)``);
    ``--new`` seeds a not-yet-listed profile at its current size."""
    profile = _parse_profile_id(profile_id)
    cur_bytes, cur_long_lines, note = measure_assembled_profile(
        repo_root, profile, template_dir=template_dir
    )
    if cur_bytes is None:
        return {"profile": profile_id, "action": "refused", "reason": note or "emitter refused"}
    baseline.setdefault("profiles", {})
    entry = baseline["profiles"].get(profile_id)
    if entry is None:
        if not seed_new:
            return {"profile": profile_id, "action": "refused",
                    "reason": "not in baseline — pass --new to seed"}
        baseline["profiles"][profile_id] = {
            "byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines,
        }
        _write(baseline_path, baseline)
        return {"profile": profile_id, "action": "seeded",
                "byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines}

    old_bytes = entry.get("byte_ceiling")
    old_lines = entry.get("long_line_ceiling")
    new_bytes = cur_bytes if old_bytes is None else min(cur_bytes, old_bytes)
    new_lines = cur_long_lines if old_lines is None else min(cur_long_lines, old_lines)
    if new_bytes == old_bytes and new_lines == old_lines:
        return {"profile": profile_id, "action": "noop",
                "reason": "no improvement over recorded ceiling"}
    entry["byte_ceiling"] = new_bytes
    entry["long_line_ceiling"] = new_lines
    _write(baseline_path, baseline)
    return {"profile": profile_id, "action": "lowered",
            "byte_ceiling": new_bytes, "long_line_ceiling": new_lines,
            "prior_byte_ceiling": old_bytes, "prior_long_line_ceiling": old_lines}


# ---------------------------------------------------------------------------
# Standing anti-bloat guard — war-story pattern detector + per-@section ceiling
# (cycle-prompt-residual-deflation-and-bloat-guard Phase 2).
#
# The dispatched-prompt template family (`cycle-base-prompt.md`, the
# `dispatch-*.md` classes, `loop-block.md`, `input-audit-prompt.md`,
# `research-halt-announcement.md`, + per-repo `cycle-prompt-addenda.md`) is
# emitted VERBATIM to a cycle subagent. Those bytes carry imperative rules +
# load-bearing marker literals ONLY; incident narrative / dated provenance /
# issue-round refs belong in the SPEC / IMPLEMENTATION_NOTES, never the prompt
# (see user/skills/_components/lazy-batch-prompts/CLAUDE.md — the authoring
# contract). This detector HARD-fails (D1) on the four CONFIRMED SHAPES (D2)
# within the DISPATCHED text ONLY.
#
# What "dispatched text" means (matches the real emitters' behavior, verified by
# driving emit_cycle_prompt): for an @section file, the union of section BODIES
# the emitter can ever SELECT (pipelines∩{feature,bug} ≠ ∅ AND modes∩{
# workstation,cloud} ≠ ∅ — a structurally-never-selected section is inert), with
# the leading pre-first-@section metadata and the @section marker lines dropped
# (the parser already drops them). Provenance that legitimately lives in an HTML
# comment inside a body (the contract permits WHY-in-comments) is excluded by
# stripping every non-allowlist `<!-- ... -->` span (single- or multi-line)
# BEFORE the shape scan. A file with no @section markers (loop-block.md,
# input-audit-prompt.md, research-halt-announcement.md) is scanned whole, minus
# its comment spans — so a multi-line leading authoring comment never leaks.
#
# Reuses the emitter's OWN parser (`lazy_core._parse_cycle_template`) and CSV
# helper (`lazy_core._csv_set`) so the scanned surface cannot drift from what the
# emitter selects ("a projection can never drift from the parser it introspects").
# ---------------------------------------------------------------------------

# The four CONFIRMED SHAPES (D2 — LOCKED). STRUCTURAL / shape-keyed, not incident
# literals, so the detector passes harness-gate.py's own overfit check. The one
# named token (`d8-effect-chains`) is an operator-confirmed recurring narrative
# marker, not a one-off incident dir (see GATE_VERDICT.md).
WAR_STORY_SHAPES: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("iso-date", re.compile(r"\b20\d\d-\d\d-\d\d\b")),
    ("issue-round-marker",
     re.compile(r"\b(?:ISSUE|Round)\s+\d+\b|\bd8-effect-chains\b")),
    ("live-incident", re.compile(r"(?i)\bLive incident:")),
    # Shape 4 is BARE-dir-only: `docs/{bugs,features}/<slug>` NOT continuing into
    # a longer operational path (a doc FILE like `docs/features/mcp-testing/SPEC.md`
    # is a legit operational reference, not an incident-provenance literal). This
    # keeps shape 4 a precise incident-provenance guard with no false-positive on
    # operational feature/bug doc paths — no inline allowlist needed for those.
    ("docs-incident-literal",
     re.compile(r"\bdocs/(?:bugs|features)/[a-z0-9][a-z0-9-]+(?![/\w-])")),
)

# Non-allowlist HTML comment spans (single- or multi-line) are stripped before
# scanning. A `<!-- war-story-allow: <reason> -->` marker is PRESERVED so the
# per-line allowlist check can rescue a genuine load-bearing literal (D4).
_WS_COMMENT_STRIP_RE = re.compile(r"<!--(?!\s*war-story-allow)(?:.|\n)*?-->")
# REASON-REQUIRED inline allowlist (D4) — mirrors cli-surface-lint.py's
# `<!-- marker -->` / lint-skill-config.py's SUPPRESSIONS. An exemption carries a
# NON-EMPTY reason at its point of use; a bare/empty-reason marker does NOT
# rescue (forcing an auditable reason, resisting silent overfit growth).
_WS_ALLOW_RE = re.compile(
    r"<!--\s*war-story-allow:\s*(?P<reason>.*?)\s*-->", re.DOTALL
)

_WAR_STORY_FAMILY_DIRPARTS = ("user", "skills", "_components", "lazy-batch-prompts")


def _section_is_selectable(attrs: dict) -> bool:
    """True iff emit_cycle_prompt can EVER select this @section — i.e. its
    pipelines and modes each intersect the real dispatch vocabulary. A section
    whose pipelines/modes can never match (e.g. ``modes=disabled``) is inert
    (never dispatched) and its body is not scanned. skills/variant/park/hosts do
    NOT make a section unreachable (any skill is reachable by dispatching it;
    park under park-mode; hosts=windows on Windows)."""
    pipelines = lazy_core._csv_set(attrs.get("pipelines")) & {"feature", "bug"}
    modes = lazy_core._csv_set(attrs.get("modes")) & {"workstation", "cloud"}
    return bool(pipelines) and bool(modes)


def _dispatched_prose(text: str) -> str:
    """Return the text the emitter would DISPATCH from *text*: the selectable
    @section bodies joined (leading metadata + marker lines already dropped by
    the parser); or, when the file has no @section markers, the whole text."""
    sections = lazy_core._parse_cycle_template(text)
    if sections:
        return "\n".join(
            s["content"] for s in sections if _section_is_selectable(s["attrs"])
        )
    return text


def scan_war_stories(text: str, filename: str) -> list[dict]:
    """Scan one dispatched-prompt template's DISPATCHED prose for the confirmed
    war-story shapes. Returns finding dicts ``{file, shape, match, line}`` (empty
    == clean). Comment provenance is excluded; a reason-bearing
    ``war-story-allow`` marker on a line rescues that line's matches."""
    prose = _dispatched_prose(text)
    # Strip every non-allowlist comment span (single- or multi-line) up front so a
    # multi-line authoring comment cannot leak an interior line into the scan.
    prose = _WS_COMMENT_STRIP_RE.sub("", prose)
    findings: list[dict] = []
    for line in prose.splitlines():
        allow = _WS_ALLOW_RE.search(line)
        rescued = bool(allow and allow.group("reason").strip())
        if rescued:
            continue
        # Drop any surviving allowlist marker text so it is not itself scanned.
        scan_line = _WS_ALLOW_RE.sub("", line)
        for shape, rx in WAR_STORY_SHAPES:
            for m in rx.finditer(scan_line):
                findings.append({
                    "file": filename, "shape": shape,
                    "match": m.group(0), "line": line.strip(),
                })
    return findings


def _war_story_family_files(repo_root: Path, template_dir: Path | None) -> list[Path]:
    """The dispatched-prompt template family scanned by the war-story detector:
    every ``*.md`` under the lazy-batch-prompts dir EXCEPT ``CLAUDE.md`` (the
    authoring-contract doc necessarily quotes the detector patterns — a
    self-match), plus every per-repo ``cycle-prompt-addenda.md``."""
    family_dir = template_dir if template_dir is not None else repo_root.joinpath(
        *_WAR_STORY_FAMILY_DIRPARTS
    )
    files: list[Path] = []
    if family_dir.is_dir():
        files.extend(sorted(p for p in family_dir.glob("*.md") if p.name != "CLAUDE.md"))
    files.extend(sorted(repo_root.glob("repos/*/.claude/skill-config/cycle-prompt-addenda.md")))
    return files


def check_war_stories(
    repo_root: Path, *, template_dir: Path | None = None
) -> list[dict]:
    """Scan the whole dispatched-prompt template family; return finding dicts
    (empty == clean). Each finding names the file, the shape, the match, and the
    offending line."""
    findings: list[dict] = []
    for path in _war_story_family_files(repo_root, template_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(scan_war_stories(text, path.name))
    return findings


# --- Per-@section byte ceiling (over cycle-base-prompt.md) ------------------

def _cycle_section_content_map(template_dir: Path | None) -> dict[str, str]:
    """Map each cycle-base-prompt.md @section to its body content, keyed by a
    collision-free id (the section name; duplicated names are disambiguated by
    appending ``/<modes>[/<variant>][/park=<v>]``)."""
    base_path = _cycle_template_dir(template_dir) / "cycle-base-prompt.md"
    sections = lazy_core._parse_cycle_template(base_path.read_text(encoding="utf-8"))
    from collections import Counter
    name_counts = Counter(s["attrs"].get("name") for s in sections)
    out: dict[str, str] = {}
    for s in sections:
        attrs = s["attrs"]
        name = attrs.get("name")
        if name_counts[name] == 1:
            key = name
        else:
            parts = [name]
            if attrs.get("modes"):
                parts.append(attrs["modes"].replace(",", "+"))
            if attrs.get("variant"):
                parts.append(attrs["variant"])
            if attrs.get("park"):
                parts.append("park=" + attrs["park"])
            key = "/".join(parts)
        out[key] = s["content"]
    return out


def _measure_section(content: str) -> tuple[int, int]:
    data = content.encode("utf-8")
    long_lines = sum(1 for line in content.splitlines() if len(line) > LONG_LINE_THRESHOLD)
    return len(data), long_lines


def check_sections(
    repo_root: Path, baseline: dict, *, template_dir: Path | None = None
) -> list[dict]:
    """Return finding dicts for per-@section ceilings (empty == clean). A section
    over its byte/long-line ceiling is a finding; a baselined section no longer
    present in the template is a ``metric: missing`` finding. Mirrors
    ``check_profiles``. This catches a single @section bloating even when the
    whole assembled profile nets under its ceiling."""
    findings: list[dict] = []
    sections = baseline.get("sections") or {}
    if not sections:
        return findings
    content_map = _cycle_section_content_map(template_dir)
    for key, entry in sorted(sections.items()):
        if key.startswith("_"):  # metadata (e.g. `_notes`)
            continue
        content = content_map.get(key)
        if content is None:
            findings.append({
                "section": key, "metric": "missing", "current": None, "ceiling": None,
            })
            continue
        cur_bytes, cur_long_lines = _measure_section(content)
        ceiling_bytes = entry.get("byte_ceiling")
        ceiling_lines = entry.get("long_line_ceiling")
        if ceiling_bytes is not None and cur_bytes > ceiling_bytes:
            findings.append({
                "section": key, "metric": "byte_ceiling",
                "current": cur_bytes, "ceiling": ceiling_bytes,
            })
        if ceiling_lines is not None and cur_long_lines > ceiling_lines:
            findings.append({
                "section": key, "metric": "long_line_ceiling",
                "current": cur_long_lines, "ceiling": ceiling_lines,
            })
    return findings


def lock_in_section(
    repo_root: Path, baseline_path: Path, baseline: dict, key: str,
    *, seed_new: bool = False, template_dir: Path | None = None,
) -> dict:
    """Update (or seed) one @section's ceiling — the section analog of
    ``lock_in_profile``. Only ever LOWERS an existing ceiling
    (``min(current, existing)``); ``--new`` seeds a not-yet-listed section at its
    current size."""
    content_map = _cycle_section_content_map(template_dir)
    content = content_map.get(key)
    if content is None:
        return {"section": key, "action": "refused",
                "reason": f"no @section named {key!r} in cycle-base-prompt.md"}
    cur_bytes, cur_long_lines = _measure_section(content)
    baseline.setdefault("sections", {})
    entry = baseline["sections"].get(key)
    if entry is None:
        if not seed_new:
            return {"section": key, "action": "refused",
                    "reason": "not in baseline — pass --new to seed"}
        baseline["sections"][key] = {
            "byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines,
        }
        _write(baseline_path, baseline)
        return {"section": key, "action": "seeded",
                "byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines}
    old_bytes = entry.get("byte_ceiling")
    old_lines = entry.get("long_line_ceiling")
    new_bytes = cur_bytes if old_bytes is None else min(cur_bytes, old_bytes)
    new_lines = cur_long_lines if old_lines is None else min(cur_long_lines, old_lines)
    if new_bytes == old_bytes and new_lines == old_lines:
        return {"section": key, "action": "noop",
                "reason": "no improvement over recorded ceiling"}
    entry["byte_ceiling"] = new_bytes
    entry["long_line_ceiling"] = new_lines
    _write(baseline_path, baseline)
    return {"section": key, "action": "lowered",
            "byte_ceiling": new_bytes, "long_line_ceiling": new_lines,
            "prior_byte_ceiling": old_bytes, "prior_long_line_ceiling": old_lines}


def seed_all_sections(
    repo_root: Path, baseline_path: Path, baseline: dict,
    *, template_dir: Path | None = None,
) -> list[dict]:
    """Seed EVERY cycle-base @section not yet in the baseline at its CURRENT size
    (bulk ``--new``). Idempotent — an already-listed section is a no-op (never
    raised). Used for the initial post-cleanup population of the ``sections``
    block."""
    results: list[dict] = []
    for key in _cycle_section_content_map(template_dir):
        if (baseline.get("sections") or {}).get(key) is not None:
            continue
        results.append(lock_in_section(
            repo_root, baseline_path, baseline, key,
            seed_new=True, template_dir=template_dir,
        ))
    return results


def check(repo_root: Path, baseline: dict) -> list[dict]:
    """Return a list of finding dicts (empty == clean). Each finding names the
    file, the metric, the current value, and the recorded ceiling."""
    findings: list[dict] = []
    for rel_path, entry in sorted(baseline["files"].items()):
        ceiling_bytes = entry.get("byte_ceiling")
        ceiling_lines = entry.get("long_line_ceiling")
        try:
            cur_bytes, cur_long_lines = measure(repo_root, rel_path)
        except FileNotFoundError:
            findings.append({
                "file": rel_path, "metric": "missing",
                "current": None, "ceiling": None,
            })
            continue
        if ceiling_bytes is not None and cur_bytes > ceiling_bytes:
            findings.append({
                "file": rel_path, "metric": "byte_ceiling",
                "current": cur_bytes, "ceiling": ceiling_bytes,
            })
        if ceiling_lines is not None and cur_long_lines > ceiling_lines:
            findings.append({
                "file": rel_path, "metric": "long_line_ceiling",
                "current": cur_long_lines, "ceiling": ceiling_lines,
            })
    return findings


def lock_in(repo_root: Path, baseline_path: Path, baseline: dict, rel_path: str, *, seed_new: bool = False) -> dict:
    """Update (or seed) one file's ceiling. Returns a result dict with the
    outcome — never silently no-ops without saying so."""
    cur_bytes, cur_long_lines = measure(repo_root, rel_path)
    entry = baseline["files"].get(rel_path)
    if entry is None:
        if not seed_new:
            return {"file": rel_path, "action": "refused", "reason": "not in baseline — pass --new to seed"}
        entry = {"byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines}
        baseline["files"][rel_path] = entry
        _write(baseline_path, baseline)
        return {"file": rel_path, "action": "seeded", "byte_ceiling": cur_bytes, "long_line_ceiling": cur_long_lines}

    old_bytes = entry.get("byte_ceiling")
    old_lines = entry.get("long_line_ceiling")
    new_bytes = cur_bytes if old_bytes is None else min(cur_bytes, old_bytes)
    new_lines = cur_long_lines if old_lines is None else min(cur_long_lines, old_lines)

    if new_bytes == old_bytes and new_lines == old_lines:
        return {"file": rel_path, "action": "noop", "reason": "no improvement over recorded ceiling"}

    if (old_bytes is not None and cur_bytes > old_bytes) or (old_lines is not None and cur_long_lines > old_lines):
        # At least one metric got worse — --lock-in NEVER raises a ceiling.
        # Report what it DID do (the other metric may still have improved) —
        # min() above already refused to raise either individually.
        pass

    entry["byte_ceiling"] = new_bytes
    entry["long_line_ceiling"] = new_lines
    _write(baseline_path, baseline)
    return {
        "file": rel_path, "action": "lowered",
        "byte_ceiling": new_bytes, "long_line_ceiling": new_lines,
        "prior_byte_ceiling": old_bytes, "prior_long_line_ceiling": old_lines,
    }


def _write(path: Path, data: dict) -> None:
    lazy_core._atomic_write(path, json.dumps(data, indent=2) + "\n")


def _resolve_repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[2]  # user/scripts/<this> -> repo root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--baseline", default=None, help="path to baseline JSON (default: sibling of this script)")
    parser.add_argument("--check", action="store_true", help="check all baseline files against their ceilings (default action)")
    parser.add_argument("--lock-in", metavar="PATH", default=None, help="lower one file's ceiling to its current size (never raises)")
    parser.add_argument("--lock-in-profile", metavar="PROFILE", default=None, help="lower one assembled-cycle-prompt profile's ceiling to its current size (never raises); PROFILE is a pipeline/mode/skill[/variant] id")
    parser.add_argument("--lock-in-section", metavar="SECTION", default=None, help="lower one cycle-base-prompt.md @section's ceiling to its current size (never raises); SECTION is the section key (name, or name/<modes>[/<variant>] when duplicated)")
    parser.add_argument("--seed-sections", action="store_true", help="seed EVERY cycle-base @section not yet in the baseline at its current size (idempotent bulk --new; the initial post-cleanup population of the per-section block)")
    parser.add_argument("--new", action="store_true", help="with --lock-in / --lock-in-profile / --lock-in-section on an entry NOT yet in the baseline, seed it at its current size")
    args = parser.parse_args()

    repo_root = _resolve_repo_root(args.repo_root)
    baseline_path = Path(args.baseline).resolve() if args.baseline else default_baseline_path()
    baseline = load_baseline(baseline_path)

    if args.lock_in:
        result = lock_in(repo_root, baseline_path, baseline, args.lock_in, seed_new=args.new)
        print(json.dumps(result, indent=2))
        return 0 if result["action"] != "refused" else 1

    if args.lock_in_profile:
        result = lock_in_profile(repo_root, baseline_path, baseline, args.lock_in_profile, seed_new=args.new)
        print(json.dumps(result, indent=2))
        return 0 if result["action"] != "refused" else 1

    if args.lock_in_section:
        result = lock_in_section(repo_root, baseline_path, baseline, args.lock_in_section, seed_new=args.new)
        print(json.dumps(result, indent=2))
        return 0 if result["action"] != "refused" else 1

    if args.seed_sections:
        results = seed_all_sections(repo_root, baseline_path, baseline)
        print(json.dumps({"seeded": results}, indent=2))
        return 0

    findings = check(repo_root, baseline)
    profile_findings = check_profiles(repo_root, baseline)
    section_findings = check_sections(repo_root, baseline)
    war_story_findings = check_war_stories(repo_root)
    profile_count = sum(1 for k in (baseline.get("profiles") or {}) if not k.startswith("_"))
    section_count = sum(1 for k in (baseline.get("sections") or {}) if not k.startswith("_"))

    if not findings and not profile_findings and not section_findings and not war_story_findings:
        print(f"OK — {len(baseline['files'])} skill file(s), {profile_count} assembled "
              f"cycle-prompt profile(s), and {section_count} cycle-base @section(s) within "
              f"their recorded size ceilings; dispatched-prompt family carries no war-story prose.")
        return 0

    for f in findings:
        if f["metric"] == "missing":
            print(f"MISSING  {f['file']} — listed in baseline but not found on disk")
        else:
            print(f"OVER-CEILING  {f['file']}  {f['metric']}={f['current']} > ceiling={f['ceiling']}")
    for f in profile_findings:
        if f["metric"] == "refused":
            print(f"REFUSED  profile {f['profile']} — emitter could not assemble: {f.get('note')}")
        else:
            print(f"OVER-CEILING  profile {f['profile']}  {f['metric']}={f['current']} > ceiling={f['ceiling']}")
    for f in section_findings:
        if f["metric"] == "missing":
            print(f"MISSING  section {f['section']} — listed in baseline but not found in cycle-base-prompt.md")
        else:
            print(f"OVER-CEILING  section {f['section']}  {f['metric']}={f['current']} > ceiling={f['ceiling']}")
    for f in war_story_findings:
        print(f"WAR-STORY  {f['file']}  [{f['shape']}] {f['match']!r} — dispatched-prompt "
              f"prose carries incident/provenance narrative; move it to the SPEC/"
              f"IMPLEMENTATION_NOTES (or, for a genuine load-bearing literal, add an inline "
              f"`<!-- war-story-allow: <reason> -->`). Line: {f['line'][:100]}")
    total = (len(findings) + len(profile_findings) + len(section_findings)
             + len(war_story_findings))
    print(f"\n{total} ratchet finding(s). Re-bloat / re-accretion detected — trim the "
          f"file/section/prose or, for a deliberate legitimate growth, hand-edit "
          f"{baseline_path.name} (never auto-raised).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
