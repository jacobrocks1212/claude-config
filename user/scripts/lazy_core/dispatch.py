"""lazy_core.dispatch — the cycle/dispatch prompt-emission + prompt-registry plane.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 4, WU-3) — a move-only refactor with zero behavior change. Owns cycle
prompt emission (``emit_cycle_prompt`` + template parsing / dispatch bindings /
the mcp-test model-tier glue ``_mcp_test_cycle_model``), meta-dispatch prompt
emission (``emit_dispatch_prompt`` + ``DISPATCH_*`` tables), the
skill-frontmatter readers (``skill_declares_subagent_model`` /
``skill_declares_multi_commit``) with the ``_CYCLE_COMMIT_*`` budget
constants, and the prompt registry (hash normalization, emission
register/lookup/resolve, by-reference events, ``consume_nonce``).

Boundary discipline (SPEC D3 — marker plane LAST): everything in the
marker/ownership/refusals plane (``read_run_marker``, ``write_cycle_marker``,
``refuse_*``, ``REGISTRY_ENTRY_TTL_SECONDS``, ``_REGISTRY_RING_CAP``) stays in
``_monolith`` until Phase 5 — reached here only via deferred function-local
imports (this module must not import ``_monolith`` at top level — circular,
since ``_monolith`` imports FROM this module). ``consume_nonce`` itself is
registry read/write (it sits in the registry block, not the marker plane) and
moves here; the registry LOADER ``_load_registry`` lives in ``.statedir``
(Phase 2), and the deny-ledger filename lives in ``.ledgers`` (WU-2).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import uuid

from pathlib import Path
from typing import Any

from ._ctx import _SCRIPTS_DIR, _atomic_write
from .docmodel import _DEFAULT_PLAN_COMPLEXITY, plan_complexity
from .ledgers import _DENY_LEDGER_FILENAME
from .statedir import _REGISTRY_FILENAME, _load_registry, claude_state_dir


# ---------------------------------------------------------------------------
# Phase 8 WU-2: script-assembled cycle dispatch prompt (emit_cycle_prompt)
# ---------------------------------------------------------------------------
#
# Moves the LAST unscripted deterministic orchestrator mechanic — re-typing the
# ~2K-token cycle dispatch prompt every dispatch — into the state scripts. The
# emitter parses the sectioned, parameterized `cycle-base-prompt.md`, selects
# the sections that apply to this (pipeline, mode, sub_skill) cycle, binds the
# 14 tokens, optionally appends the loop block, and returns the finished prompt
# + the model to dispatch it under. See the template file's header comment for
# the authoritative marker grammar / selection semantics / token inventory.

# Default cycle-prompt template directory, resolved through the package's
# _SCRIPTS_DIR anchor (see _ctx.py). The lazy_core package lives at
# <claude-config>/user/scripts/lazy_core/, so _SCRIPTS_DIR is
# <claude-config>/user/scripts, its parent is <claude-config>/user, and the
# templates live under skills/_components/lazy-batch-prompts/. The PHASES
# "Validated Assumptions" table confirms this resolves correctly through the
# ~/.claude symlink chain.
_CYCLE_TEMPLATE_DIRNAME = ("skills", "_components", "lazy-batch-prompts")

# The marker line shape the emitter parses, e.g.:
#   <!-- @section task pipelines=feature,bug modes=workstation skills=all -->
# with an optional `variant=runtime-up|no-runtime` token before the closing
# `-->`. Attributes are matched by key=value tokens (order-tolerant), so the
# variant attribute's position in the file is not load-bearing.
_SECTION_MARKER_RE = re.compile(r"^<!--\s*@section\s+(?P<rest>.*?)\s*-->\s*$")

# Residue regex: any `{lower_snake_or_digit}` token surviving the bind is an
# unbound token the emitter REFUSES on (never emits a half-bound prompt).
# Widened to include digits so tokens like {item_id} and {item_id2} are caught —
# previously `\{[a-z_]+\}` allowed digit-bearing tokens to pass through silently.
_PROMPT_RESIDUE_RE = re.compile(r"\{[a-z0-9_]+\}")


def _default_cycle_template_dir() -> Path:
    """Resolve the default cycle-prompt template dir from this module's path."""
    return _SCRIPTS_DIR.parent.joinpath(*_CYCLE_TEMPLATE_DIRNAME)


def _standard_dispatch_bindings(pipeline: str) -> dict[str, str]:
    """Return the standard pipeline-token bindings shared by emit_cycle_prompt and
    emit_dispatch_prompt.

    These seven tokens appear across the dispatch templates and the cycle base
    template.  Factored out here so the two emitters stay byte-identical on the
    same input without code duplication.

    The last two tokens split the ``forbidden_status`` compound into its two
    distinct terminal statuses so a template can reference them separately
    (``dispatch-apply-resolution.md`` needs this: the receipt-EXEMPT terminal —
    ``Won't-fix``/``Superseded`` — is a legitimate operator-directed close that
    carries no receipt, whereas the receipt-GATED terminal — ``Fixed``/``Complete``
    — must never be set without a receipt).  ``forbidden_status`` itself is
    UNCHANGED (still the compound "Fixed or Won't-fix"/"Complete") because the
    other dispatch templates + the cycle base template use it as the blanket
    "set no terminal status" ban where that broad reading is correct.

    Args:
        pipeline: ``"feature"`` or ``"bug"``.

    Returns:
        A fresh dict with the standard pipeline tokens bound to their
        pipeline-appropriate values.
    """
    is_bug = pipeline == "bug"
    return {
        "item_label":            "Bug" if is_bug else "Feature",
        "pipeline_phrase":       "bug pipeline" if is_bug else "feature pipeline",
        "receipt_name":          "FIXED.md" if is_bug else "COMPLETED.md",
        "mark_pseudo":           "__mark_fixed__" if is_bug else "__mark_complete__",
        "forbidden_status":      "Fixed or Won't-fix" if is_bug else "Complete",
        # Split terminals (apply-resolution terminal-disposition contract):
        "receipt_gated_status":  "Fixed" if is_bug else "Complete",
        "receipt_exempt_status": "Won't-fix" if is_bug else "Superseded",
    }


def _dedup_residue(tokens: list[str]) -> list[str]:
    """Return ``tokens`` deduplicated while preserving first-seen order.

    Used by the residue guard in both emit_cycle_prompt and emit_dispatch_prompt
    to produce a stable, human-readable list of unbound {token} names.
    """
    seen: list[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.append(tok)
    return seen


def _emit_work_branch(repo_root: Path) -> str:
    """Resolve repo_root's current branch name for the {work_branch} token.

    Best-effort, mirroring _current_head's subprocess guard: any non-zero exit,
    empty output, or OS/subprocess error falls back to the literal string
    ``"the current branch"`` so the emitter never raises on a non-git root."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            branch = r.stdout.strip()
            if branch:
                return branch
    except (OSError, subprocess.SubprocessError):
        pass
    return "the current branch"


def _parse_section_attrs(rest: str) -> dict[str, str]:
    """Parse the attribute tokens of a `@section` marker into a dict.

    `rest` is the text between `@section` and the closing `-->` (already
    stripped), e.g. ``task pipelines=feature,bug modes=workstation skills=all``.
    The first whitespace token is the section NAME (stored under the special
    key ``"name"``); every remaining ``key=value`` token is stored verbatim.
    Tokens without an ``=`` (other than the leading name) are ignored.
    """
    tokens = rest.split()
    if not tokens:
        return {}
    attrs: dict[str, str] = {"name": tokens[0]}
    for tok in tokens[1:]:
        if "=" in tok:
            key, _, value = tok.partition("=")
            attrs[key] = value
    return attrs


def _parse_cycle_template(text: str) -> list[dict[str, Any]]:
    """Split a cycle-base-prompt template into its `@section` blocks.

    Everything BEFORE the first marker line is template metadata and is dropped.
    Each returned dict has: ``attrs`` (the parsed marker attributes, incl.
    ``name``) and ``content`` (the section body with leading/trailing blank
    lines stripped). A section's content runs from the line AFTER its marker to
    the line BEFORE the next marker (or EOF).
    """
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    body: list[str] = []

    def _flush():
        if current is not None:
            # Strip leading/trailing blank lines from the accumulated body.
            content_lines = body[:]
            while content_lines and not content_lines[0].strip():
                content_lines.pop(0)
            while content_lines and not content_lines[-1].strip():
                content_lines.pop()
            current["content"] = "\n".join(content_lines)
            sections.append(current)

    for line in lines:
        m = _SECTION_MARKER_RE.match(line)
        if m:
            # New section starts — finish the previous one (if any).
            _flush()
            current = {"attrs": _parse_section_attrs(m.group("rest"))}
            body = []
        elif current is not None:
            # Accumulate content (lines before the first marker are metadata).
            body.append(line)
    _flush()
    return sections


def _csv_set(value: str | None) -> set[str]:
    """Split a comma-separated attribute value into a set of trimmed tokens."""
    if not value:
        return set()
    return {tok.strip() for tok in value.split(",") if tok.strip()}


def _read_mcp_runtime_decision(spec_path: str | None) -> tuple[str, str | None]:
    """Decide the mcp-test runtime variant + untestability reason from PHASES.md.

    Reads ``{spec_path}/PHASES.md`` and looks for a line starting
    ``**MCP runtime:**``:
      - contains ``not-required`` → ``("no-runtime", <reason>)`` where reason is
        the text after the first ``-`` / ``—`` dash on that line (or a fallback
        when no dash is present).
      - any other value, line absent, or file/dir absent → ``("runtime-up", None)``.

    Never raises: an unreadable file is treated as "line absent" → runtime-up.
    """
    fallback_reason = "the plan declares no MCP-reachable surface"
    if not spec_path:
        return ("runtime-up", None)
    phases = Path(spec_path) / "PHASES.md"
    try:
        text = phases.read_text(encoding="utf-8")
    except OSError:
        return ("runtime-up", None)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**MCP runtime:**"):
            # ANCHORED value-token test — mirror phases_mcp_runtime_not_required
            # (line ~449). Match ``not-required`` ONLY as the VALUE token right
            # after the marker (word-boundary terminated), NOT as a substring
            # anywhere on the line. Without the anchor, a ``**MCP runtime:**
            # required`` line whose REASON PROSE mentions "not-required" (e.g.
            # "... not eligible for not-required") is mis-classified as
            # no-runtime, deadlocking a required-runtime mcp-test cycle
            # (first-time-login, 2026-07).
            if re.match(r"(?i)\*\*MCP runtime:\*\*\s*not-required\b", stripped):
                # Reason = text after the first dash (ASCII '-' or em-dash '—').
                reason = fallback_reason
                for dash in ("—", "-"):
                    idx = stripped.find(dash)
                    if idx != -1:
                        candidate = stripped[idx + len(dash):].strip()
                        if candidate:
                            reason = candidate
                        break
                return ("no-runtime", reason)
            # Line present but not the not-required value → runtime-up.
            return ("runtime-up", None)
    # No **MCP runtime:** line at all → runtime-up.
    return ("runtime-up", None)


def _mcp_test_cycle_model(spec_path: str | None) -> str:
    """Return the dispatch model (``"haiku"`` | ``"sonnet"``) for an mcp-test
    cycle, derived from the item's candidate scenarios via the script-derived
    tier signal (``surface_resolver.route_mcp_test_tier``).

    OPTION-(b) conservative escalation (docs/bugs/mcp-test-legacy-md-routes-to-haiku
    PHASES.md decision): enumerate the candidate scenarios under the resolved
    spec/bug dir — legacy ``mcp-tests/*.md`` + converted ``corpus/live/*.yaml``
    (recursively, so the canonical ``mcp-tests/corpus/live/`` nesting is covered)
    — and return ``"haiku"`` ONLY when at least one candidate resolves AND every
    candidate resolves to ``"haiku"`` via the tier router (ready converted YAML).
    Otherwise return ``"sonnet"``.

    Fail-safe: zero resolvable candidates, or any enumeration/resolution error,
    → ``"sonnet"`` (matches ``route_mcp_test_tier``'s own "unknown → Sonnet"
    bias). NEVER a silent haiku fallback — that is the exact defect this fixes.
    """
    # Lazy in-function import: surface_resolver is a sibling module in
    # user/scripts/. Import here (not at module top) to avoid any import-time
    # coupling/cycle and to keep the helper a no-op cost on non-mcp-test cycles.
    try:
        try:
            from surface_resolver import route_mcp_test_tier
        except ImportError:
            _here = _SCRIPTS_DIR
            if str(_here) not in sys.path:
                sys.path.insert(0, str(_here))
            from surface_resolver import route_mcp_test_tier

        if not spec_path:
            return "sonnet"  # no item dir to resolve scenarios from.
        item_dir = Path(spec_path)
        if not item_dir.is_dir():
            return "sonnet"

        # Candidate scenarios: legacy .md + converted .yaml under mcp-tests/
        # (recursive — covers both a flat mcp-tests/*.md and the canonical
        # mcp-tests/corpus/live/*.yaml nesting).
        mcp_root = item_dir / "mcp-tests"
        candidates: list[Path] = []
        if mcp_root.is_dir():
            candidates.extend(sorted(mcp_root.rglob("*.md")))
            candidates.extend(sorted(mcp_root.rglob("*.yaml")))
            candidates.extend(sorted(mcp_root.rglob("*.yml")))

        if not candidates:
            return "sonnet"  # no scenario resolves → conservative escalation.

        # haiku only when EVERY candidate is a ready converted YAML (the router
        # returns "haiku"); a single legacy-.md (or any sonnet verdict) escalates.
        for scenario in candidates:
            if route_mcp_test_tier(scenario) != "haiku":
                return "sonnet"
        return "haiku"
    except Exception:
        # Any unexpected failure fails safe toward the capable tier.
        return "sonnet"


def emit_cycle_prompt(
    repo_root: Path,
    state: dict,
    *,
    pipeline: str,
    cloud: bool = False,
    repeat_count: int | None = None,
    template_dir: Path | None = None,
    park_mode: bool = False,
) -> dict | None:
    """Assemble the cycle dispatch prompt for one orchestrator cycle.

    The state scripts call this under ``--emit-prompt`` so the orchestrator
    never re-types the boilerplate prompt (the 2026-06-10 audit found this was
    ~70% of the orchestrator's output tokens). The emitter is the single
    assembler: it parses the sectioned ``cycle-base-prompt.md``, selects the
    sections matching this cycle, binds the tokens, optionally appends the loop
    block, and returns the finished prompt + dispatch model.

    Args:
        repo_root: the project root (used for {cwd} and {work_branch}).
        state: the dict ``compute_state`` produced. Consumed keys:
            ``feature_id``, ``feature_name``, ``spec_path``, ``current_step``,
            ``sub_skill``, ``sub_skill_args`` (bug-state reuses the feature_*
            keys for bugs).
        pipeline: ``"feature"`` or ``"bug"`` — selects per-pipeline sections and
            the bug/feature token bindings.
        cloud: when True the mode is ``"cloud"``, else ``"workstation"``.
        repeat_count: the consecutive-identical-probe count; when ``>= 2`` the
            loop block is appended and the dispatch model flips to ``"sonnet"``.
        template_dir: override the template directory (for tests). Defaults to
            the resolved ``skills/_components/lazy-batch-prompts/`` dir.
        park_mode: True when the emitting probe ran under ``--park-needs-input``
            (park-provisional-acceptance, SPEC D13). Selects sections whose
            ``park=park`` attribute marks them park-only (e.g. the stub-spec
            sentinel-mediation contract). Sections without a ``park=``
            attribute — every pre-existing section — are selected exactly as
            before, so non-park emission is byte-identical.

    Returns:
        ``None`` when the probe is not a dispatchable real-skill cycle —
        ``sub_skill`` is falsy, ``sub_skill`` starts with ``"__"`` (a pseudo-skill
        the orchestrator applies via ``--apply-pseudo``, not a dispatched skill),
        or ``feature_id`` is falsy (a terminal / idle probe). This keeps the
        orchestrator's single probe call uniform — the field is always present.

        Otherwise a dict: ``{"ok": True, "prompt": <str>, "model": "opus"|"sonnet"}``
        on success, or ``{"ok": False, "refused": <reason>}`` when binding leaves
        an unbound ``{token}`` (the emitter never emits a half-bound prompt). The
        function never raises on bad template content — it refuses instead.
    """
    sub_skill = state.get("sub_skill")
    # Not a dispatchable real-skill cycle → None (uniform "no prompt" signal).
    if not sub_skill or sub_skill.startswith("__"):
        return None
    if not state.get("feature_id"):
        return None

    if template_dir is None:
        template_dir = _default_cycle_template_dir()

    mode = "cloud" if cloud else "workstation"
    # Normalize the sub_skill for skills-csv matching: strip a leading "/".
    norm_skill = sub_skill[1:] if sub_skill.startswith("/") else sub_skill

    # --- Read + parse the base template (refuse, never raise, on bad input) ---
    base_path = template_dir / "cycle-base-prompt.md"
    try:
        base_text = base_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "refused": f"cannot read cycle-base-prompt.md: {exc}"}

    sections = _parse_cycle_template(base_text)

    # --- mcp-test runtime variant decision (only consulted for mcp-test) ------
    runtime_variant, untestability_reason = _read_mcp_runtime_decision(
        state.get("spec_path")
    )

    # --- Select the sections that apply to this cycle -------------------------
    selected: list[str] = []
    for sec in sections:
        attrs = sec["attrs"]
        pipelines = _csv_set(attrs.get("pipelines"))
        modes = _csv_set(attrs.get("modes"))
        skills = attrs.get("skills", "")
        if pipeline not in pipelines:
            continue
        if mode not in modes:
            continue
        # skills=all OR the normalized sub_skill is in the csv.
        if skills != "all" and norm_skill not in _csv_set(skills):
            continue
        # variant= sections are mcp-test-only and additionally filtered by the
        # runtime decision (the emitter picks EXACTLY ONE variant).
        variant = attrs.get("variant")
        if variant is not None:
            if norm_skill != "mcp-test" or variant != runtime_variant:
                continue
        # park= filter (park-provisional-acceptance, SPEC D13): `park=park`
        # sections are selected ONLY under a park-mode probe; absent attribute
        # (or `park=both`) keeps the pre-existing always-selected behavior.
        if attrs.get("park") == "park" and not park_mode:
            continue
        # hosts= filter (cycle-prompt-environment-dialect, SPEC D2): hosts=windows
        # sections are selected ONLY when the emitting host is Windows. Absent ->
        # always selected (grammar-additive, same shape as park=).
        host_attr = attrs.get("hosts")
        if host_attr == "windows" and os.name != "nt":
            continue
        if sec["content"]:
            selected.append(sec["content"])

    # --- Repo prompt addenda (Phase 10 WU-3) ----------------------------------
    # After the base sections (and BEFORE the loop block), append any matching
    # sections from the OPTIONAL repo addenda file. The addenda path is keyed off
    # repo_root (NOT template_dir): it is the established per-repo config surface
    # (.claude/skill-config/). Parsing + selection reuse the SAME helpers as the
    # base template (no duplicated grammar), and the appended content is bound +
    # residue-guarded by the SAME map below — so a bad addenda section refuses the
    # WHOLE emission exactly like a bad base section. Absent file (or a file with
    # no matching sections) → no change, byte-identical to base-only behavior.
    # Orchestrators must NEVER hand-append to cycle_prompt; repo-specific gates
    # live here (a live orchestrator hand-spliced the AlgoBooth audio-INVARIANTS
    # gate onto the emitted prompt on 2026-06-11 — that path is now closed).
    addenda_path = repo_root / ".claude" / "skill-config" / "cycle-prompt-addenda.md"
    # Track addenda-contributed content separately so the residue guard can name
    # the addenda file when an unbound token came from a (mis-authored) addenda
    # section rather than the base template.
    addenda_selected: list[str] = []
    try:
        addenda_text = addenda_path.read_text(encoding="utf-8")
    except OSError:
        # Absent / unreadable → no addenda (the common, byte-identical path).
        addenda_text = None
    if addenda_text is not None:
        for sec in _parse_cycle_template(addenda_text):
            attrs = sec["attrs"]
            if pipeline not in _csv_set(attrs.get("pipelines")):
                continue
            if mode not in _csv_set(attrs.get("modes")):
                continue
            skills = attrs.get("skills", "")
            if skills != "all" and norm_skill not in _csv_set(skills):
                continue
            # Addenda sections may carry a variant= attribute too (same mcp-test
            # one-variant rule), kept for parity with the base selection logic.
            variant = attrs.get("variant")
            if variant is not None:
                if norm_skill != "mcp-test" or variant != runtime_variant:
                    continue
            # park= filter — same rule as the base selection (SPEC D13).
            if attrs.get("park") == "park" and not park_mode:
                continue
            # hosts= filter — same rule as the base selection (SPEC D2).
            host_attr = attrs.get("hosts")
            if host_attr == "windows" and os.name != "nt":
                continue
            if sec["content"]:
                addenda_selected.append(sec["content"])
    # Appended AFTER base sections — order: base → addenda → (loop block below).
    selected.extend(addenda_selected)

    # --- Token bindings (per-pipeline + per-state) ----------------------------
    # Standard pipeline tokens come from the shared helper; cycle-specific tokens
    # are layered on top (context wins on collision, same as emit_dispatch_prompt).
    bindings = _standard_dispatch_bindings(pipeline)
    bindings.update({
        "item_name": state.get("feature_name") or "",
        "item_id": state.get("feature_id") or "",
        "cwd": str(repo_root),
        "current_step": state.get("current_step") or "",
        "sub_skill": sub_skill,
        # sub_skill_args binds to "" when None so the prompt never shows "None".
        "sub_skill_args": state.get("sub_skill_args") or "",
        "spec_path": state.get("spec_path") or "",
        "work_branch": _emit_work_branch(repo_root),
        # untestability_reason is only present in the no-runtime mcp-test section;
        # bind it whenever a reason was derived (fallback applies otherwise).
        "untestability_reason": untestability_reason
        or "the plan declares no MCP-reachable surface",
    })

    prompt = "\n\n".join(selected)

    # --- Per-part complexity model tiering (Phase 9 — lazy-validation-readiness)
    # The /execute-plan cycle's dispatch model is selected from the CURRENT plan
    # part's `complexity:` frontmatter tag:
    #     mechanical → sonnet ; complex / absent / untagged → opus.
    # The plan part is `state["sub_skill_args"]` (the plan path) when the cycle
    # is an /execute-plan dispatch — the ONLY cycle this tiering applies to (a
    # /retro, /spec, /mcp-test, etc. cycle is unaffected and stays opus). Gated
    # strictly on the explicit tag /write-plan emitted: `plan_complexity` returns
    # the SAFE `complex`/opus default for any uncertain case, so the model never
    # auto-guesses cheaper. This baseline composes with the loop-block downgrade
    # below WITH A COMPLEXITY FLOOR (checkpoint-resume-false-loop-flips-complex-part-
    # to-sonnet, 2026-07-12): a `mechanical`/sonnet part stays sonnet, but a
    # `complex`/opus (or untagged-default-complex) /execute-plan part that loops
    # does NOT flip to sonnet — the cycle prompt HARD-refuses complex work under a
    # sonnet dispatch (`BLOCKED model-tier-mismatch`, cycle-base-prompt.md:260,287),
    # so a loop-flip to sonnet cannot advance the part and only climbs the stall
    # streak toward a halt. Such a cycle is `complexity_pinned_opus` and the loop
    # block below leaves it on opus.
    norm_sub_skill = norm_skill  # already leading-"/"-stripped above
    # Per-sub_skill base model tier.
    #
    # mcp-test is TIER-ROUTED at emit time via surface_resolver.route_mcp_test_tier
    # (docs/bugs/mcp-test-legacy-md-routes-to-haiku). The dispatch model is bound
    # by the orchestrator BEFORE the cycle subagent resolves which scenario it
    # runs, so a literal haiku here lands an UNCONVERTED legacy `.md` scenario on
    # haiku — which cannot author the `.md`→v1-YAML conversion and writes
    # BLOCKED.md. The fix consults the same script-derived tier signal the
    # interactive mcp-test SKILL.md uses (harness-hardening-retro-fixes Phase 4),
    # using OPTION-(b) CONSERVATIVE ESCALATION (per the bug's PHASES.md decision):
    # enumerate the item's candidate scenarios under the resolved spec/bug dir
    # (legacy `mcp-tests/*.md` + converted `corpus/live/*.yaml`); stay haiku ONLY
    # when at least one candidate resolves AND EVERY candidate is a ready
    # converted YAML (route_mcp_test_tier → "haiku"); otherwise escalate to
    # sonnet. Fail-safe: zero resolvable candidates OR an enumeration error →
    # sonnet (matches the router's own "unknown → Sonnet" bias) — NEVER a silent
    # haiku fallback. Every other sub_skill keeps the conservative opus base.
    #
    # The loop-block downgrade below sets model = "sonnet" UNCONDITIONALLY — from
    # a haiku/opus base that is the correct ESCALATION/downgrade toward sonnet; it
    # composes with this tier routing (both only ever move toward sonnet, never
    # away). Opus-on-failure for mcp-test is handled separately by the
    # needs-runtime-redispatch recovery path (dispatch_model "opus", tagged
    # "(opus, recovery)"), not here.
    if norm_sub_skill == "mcp-test":
        model = _mcp_test_cycle_model(state.get("spec_path"))
    else:
        model = "opus"
    # complexity_pinned_opus: True when this is an /execute-plan cycle whose plan
    # part's declared complexity is NOT mechanical (i.e. `complex`, or the SAFE
    # untagged/unknown default). Such a cycle is HARD-refused on sonnet by the
    # subagent, so the loop-block downgrade below must NOT drop it to sonnet.
    complexity_pinned_opus = False
    if norm_sub_skill in ("execute-plan", "execute_plan"):
        plan_arg = state.get("sub_skill_args")
        plan_token = ""
        if plan_arg:
            # sub_skill_args may carry trailing flags (e.g. "<plan> --batch");
            # the plan path is the first whitespace-delimited token.
            parts = str(plan_arg).split()
            plan_token = parts[0] if parts else ""
        # plan_complexity defaults to the SAFE `complex` for any uncertain case
        # (no arg, unreadable, untagged) — so an /execute-plan cycle is pinned to
        # opus unless the part is EXPLICITLY `mechanical`. This matches the
        # subagent's model-tier-mismatch refusal condition exactly.
        part_complexity = (
            plan_complexity(Path(plan_token)) if plan_token else _DEFAULT_PLAN_COMPLEXITY
        )
        if part_complexity == "mechanical":
            model = "sonnet"
        else:
            complexity_pinned_opus = True

    # --- Loop block: appended when the same signature repeated (>= 2) ---------
    # The loop block lives in loop-block.md inside a ``` fence; strip the fence
    # lines and bind its tokens. The loop-flip downgrades to sonnet to break a
    # stall cheaply — BUT never below a complexity-pinned-opus /execute-plan part
    # (a complex part on sonnet is refused as model-tier-mismatch, so the flip
    # would only climb the stall streak). Such cycles keep opus AND still get the
    # loop block appended (the loop guidance is model-independent).
    if repeat_count is not None and repeat_count >= 2:
        loop_path = template_dir / "loop-block.md"
        try:
            loop_text = loop_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "refused": f"cannot read loop-block.md: {exc}"}
        loop_inner = _strip_loop_fence(loop_text)
        if loop_inner:
            prompt = prompt + "\n\n" + loop_inner if prompt else loop_inner
            if not complexity_pinned_opus:
                model = "sonnet"

    # --- Bind all tokens (all occurrences, all sections + loop block) ---------
    for token, value in bindings.items():
        prompt = prompt.replace("{" + token + "}", value)

    # --- Residue guard: any surviving {token} → refuse (never half-bound) -----
    residue = _PROMPT_RESIDUE_RE.findall(prompt)
    if residue:
        seen = _dedup_residue(residue)
        # Attribute the residue to the addenda file when an unbound token traces
        # back to a (mis-authored) addenda section — so the operator knows which
        # file to fix. We bind the addenda blob in isolation and check whether
        # any of the surviving tokens originated there.
        suffix = ""
        if addenda_selected:
            addenda_blob = "\n\n".join(addenda_selected)
            for token, value in bindings.items():
                addenda_blob = addenda_blob.replace("{" + token + "}", value)
            addenda_residue = set(_PROMPT_RESIDUE_RE.findall(addenda_blob))
            if addenda_residue & set(seen):
                suffix = (
                    " (from .claude/skill-config/cycle-prompt-addenda.md — fix or "
                    "remove the offending addenda section)"
                )
        return {"ok": False, "refused": "unbound tokens: " + ", ".join(seen) + suffix}

    return {"ok": True, "prompt": prompt, "model": model}


def _strip_loop_fence(loop_text: str) -> str:
    """Extract the inner text of loop-block.md, dropping its ``` code fence.

    loop-block.md wraps its emittable body in a single ```-fenced block (after a
    metadata header comment). This returns the content BETWEEN the opening and
    closing fence lines, with leading/trailing blank lines stripped. When no
    fence is found (defensive), the whole text minus blank edges is returned.
    """
    lines = loop_text.splitlines()
    fence_idxs = [i for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    if len(fence_idxs) >= 2:
        inner = lines[fence_idxs[0] + 1: fence_idxs[1]]
    else:
        inner = lines
    while inner and not inner[0].strip():
        inner.pop(0)
    while inner and not inner[-1].strip():
        inner.pop()
    return "\n".join(inner)


# ---------------------------------------------------------------------------
# Phase 3 — emit_dispatch_prompt: every remaining dispatch class becomes
#            script-emitted.  Reuses the same template grammar and binding/
#            residue machinery as emit_cycle_prompt — no reimplementation.
#
# Six classes (Phase 3); 'hardening' is deferred to Phase 4.
# Model assignments derive from the SOURCE COMPONENTS (not the SPEC.md, which
# pins no per-class models):
#   apply-resolution → opus  (blocked-resolution.md dispatches its apply subagent
#                             as Opus: judgment work — enacting Add-a-phase,
#                             Defer, or custom operator directives)
#   recovery / coherence-recovery → sonnet (bounded mechanical reconciliation)
#   input-audit / investigation / needs-runtime-redispatch → opus (judgment)
# ---------------------------------------------------------------------------

# The ordered tuple of dispatch classes.  Phase 3 added the first 6; Phase 4
# appends 'hardening' as the 7th entry (the harness-hardening stage class).
DISPATCH_CLASSES: tuple[str, ...] = (
    "apply-resolution",
    "input-audit",
    "investigation",
    "recovery",
    "coherence-recovery",
    "needs-runtime-redispatch",
    "corrective-coverage",  # harden Round 44 — Gate-1 MCP-coverage authoring cycle
    "ingest-research",      # harden Round 44 — pre-loop / in-session staged-research ingest
    "hardening",          # Phase 4 — harness-hardening stage (always Opus)
)

# Model to use when dispatching each class.  'opus' for judgment work;
# 'sonnet' for bounded mechanical work.  Source: the dispatch SOURCE COMPONENTS
# (blocked-resolution.md, decision-resume.md, investigation-dispatch.md, etc.).
DISPATCH_MODELS: dict[str, str] = {
    "apply-resolution":        "opus",    # blocked-resolution.md: Opus apply subagent
    "input-audit":             "opus",
    "investigation":           "opus",
    "recovery":                "sonnet",
    "coherence-recovery":      "sonnet",
    "needs-runtime-redispatch": "opus",
    "corrective-coverage":     "opus",   # harden Round 44 — classify + author + run coverage = Opus
    "ingest-research":         "sonnet", # harden Round 44 — bounded mechanical ingest = Sonnet
    "hardening":               "opus",   # Phase 4 — root-cause + mechanical fixes = Opus
}

# Regex to extract @requires keys from the first non-empty line of a dispatch
# template, e.g.: <!-- @requires item_id,spec_path,sentinel_path -->
_DISPATCH_REQUIRES_RE = re.compile(r"^<!--\s*@requires\s+([a-z0-9_,]+)\s*-->")


def load_context_json(text: str) -> dict:
    """Parse a --context-file / --context-stdin JSON payload into a context dict.

    ISSUE 3 (d8-effect-chains live /lazy-batch run, 2026-06-14): a ~1500-char
    ``failure_summary`` with commas/colons/parens/newlines was unreliable as an
    inline ``--context KEY=VALUE`` flag (the shell — not the script — mangled it).
    The JSON channel sidesteps shell quoting entirely: the orchestrator writes the
    payload to a file (or pipes it) and the value may contain ANY characters.

    Validation is strict so a malformed payload becomes a STRUCTURED error in the
    --emit-dispatch handler rather than silently-empty context:
      - The decoded JSON MUST be an object (dict). A list/str/number → ValueError.
      - Every key MUST be a string. A non-string key → ValueError.
      - Values are coerced to str (None → "") to match the inline-flag contract
        (emit_dispatch_prompt stringifies all bindings anyway).

    Raises:
        ValueError: on invalid JSON, a non-object top level, or a non-string key.
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"context payload is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(
            f"context payload must be a JSON object, got {type(obj).__name__}"
        )
    out: dict = {}
    for key, value in obj.items():
        if not isinstance(key, str):
            raise ValueError(f"context key must be a string, got {key!r}")
        out[key] = "" if value is None else str(value)
    return out

# Phase 7 WU-7.5a: per-class Step name for the meta cycle_header.  The header
# the orchestrator echoes is `### {Step} — {summary} [meta {m}]` (bare count, no
# cap — meta_cycles is uncapped as of 2026-06-14); this map
# pins {Step} per the PHASES.md Phase 7 interface contract so every meta dispatch
# carries a canonical heading (0/8 meta cycles carried one before this WU).
DISPATCH_STEP_NAMES: dict[str, str] = {
    "investigation":            "Investigate",
    "apply-resolution":         "Resolve",
    "recovery":                 "Recover",
    "coherence-recovery":       "Recover",
    "hardening":                "Harden",
    "input-audit":              "Audit",
    "needs-runtime-redispatch": "Validate",
}


def emit_dispatch_prompt(
    cls: str,
    context: dict,
    *,
    pipeline: str,
    cloud: bool = False,
    template_dir: "Path | None" = None,
) -> dict:
    """Assemble a fully-bound dispatch prompt for one of the Phase 3 dispatch
    classes.

    Unlike ``emit_cycle_prompt`` (which assembles cycle prompts from state-script
    probe output), this assembler is called with an *explicit* context dict that
    the orchestrator builds from probe output + sentinel paths.  The matched
    template lives at ``dispatch-<cls>.md`` inside the same
    ``lazy-batch-prompts/`` directory used by the cycle emitter.

    The template grammar is identical to ``cycle-base-prompt.md``:
      - First non-empty line MUST be ``<!-- @requires key1,key2,... -->``
        declaring the *class-specific* context keys this template needs.
      - Subsequent lines use ``<!-- @section name pipelines=... modes=... -->``
        markers and ``{lower_snake}`` token placeholders.

    Standard pipeline tokens are always bound (same set as emit_cycle_prompt):
      {item_label}, {pipeline_phrase}, {receipt_name}, {mark_pseudo},
      {forbidden_status}
    Context dict values are overlaid on top (context wins on collision).

    Refusal semantics (mirrors emit_cycle_prompt — never half-binds):
      - Missing @requires key in context → refused, names the first missing key.
      - Unbound {token} residue after binding → refused, names the residue.
      - Unknown cls → ValueError (not a refusal dict — caller error).

    Args:
        cls: dispatch class name.  Must be in DISPATCH_CLASSES or DISPATCH_MODELS
             (Phase 4 will add 'hardening' before that class's template exists).
        context: dict of class-specific token values supplied by the caller.
        pipeline: ``"feature"`` or ``"bug"`` — section filtering + standard tokens.
        cloud: ``True`` → mode ``"cloud"``; ``False`` → mode ``"workstation"``.
        template_dir: override the template directory (for tests and Phase 4).
                      Defaults to the same ``lazy-batch-prompts/`` dir used by
                      emit_cycle_prompt.

    Returns:
        On success: ``{"ok": True, "prompt": <str>, "model": <"opus"|"sonnet">}``;
          additionally ``"cycle_header"`` (Phase 7 WU-7.5a) when a run marker is
          present (marker-gated — omitted entirely with no marker so no-marker
          callers stay byte-identical).
        On refusal: ``{"ok": False, "refused": <reason_str>}``

    Raises:
        ValueError: when ``cls`` is not a known dispatch class.
    """
    # --- Unknown-class guard (caller error — must raise, not refuse) -----------
    # Combine DISPATCH_CLASSES + DISPATCH_MODELS keys so Phase 4 can extend
    # DISPATCH_MODELS before or after appending to DISPATCH_CLASSES without a gap.
    from ._monolith import read_run_marker  # Phase-5 re-point (marker/registry plane still monolith-resident)
    all_known = set(DISPATCH_CLASSES) | set(DISPATCH_MODELS.keys())
    if cls not in all_known:
        raise ValueError(
            f"emit_dispatch_prompt: unknown dispatch class {cls!r}. "
            f"Known classes: {sorted(all_known)}"
        )

    if template_dir is None:
        template_dir = _default_cycle_template_dir()

    mode = "cloud" if cloud else "workstation"

    # --- Read the dispatch template -------------------------------------------
    tpl_path = template_dir / f"dispatch-{cls}.md"
    try:
        tpl_text = tpl_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "refused": f"cannot read dispatch-{cls}.md: {exc}"}

    # --- Parse @requires from line 1 ------------------------------------------
    # The first non-empty line must declare the class-specific required keys.
    first_line = next((ln for ln in tpl_text.splitlines() if ln.strip()), "")
    m = _DISPATCH_REQUIRES_RE.match(first_line)
    if not m:
        return {
            "ok": False,
            "refused": (
                f"dispatch-{cls}.md: first non-empty line must be "
                f"'<!-- @requires key1,key2,... -->' (only [a-z0-9_,] chars); "
                f"got: {first_line!r}"
            ),
        }
    requires_keys = [k.strip() for k in m.group(1).split(",") if k.strip()]

    # --- Validate that all @requires keys are present in context ---------------
    for key in requires_keys:
        if key not in context:
            return {
                "ok": False,
                "refused": (
                    f"dispatch-{cls}.md requires context key {key!r} which is "
                    f"absent from the supplied context dict. "
                    f"All @requires keys: {requires_keys}"
                ),
            }

    # --- Parse sections (reuse the same machinery as emit_cycle_prompt) --------
    sections = _parse_cycle_template(tpl_text)

    # --- Section selection by pipeline + mode (no skills= filtering needed) ---
    selected: list[str] = []
    for sec in sections:
        attrs = sec["attrs"]
        pipelines = _csv_set(attrs.get("pipelines"))
        modes = _csv_set(attrs.get("modes"))
        if pipeline not in pipelines:
            continue
        if mode not in modes:
            continue
        if sec["content"]:
            selected.append(sec["content"])

    prompt = "\n\n".join(selected)

    # --- Build the binding map -------------------------------------------------
    # Standard pipeline tokens come from the shared helper; context dict values
    # are overlaid on top (context wins on collision — the caller provides the
    # class-specific tokens; standard tokens above are the fallback defaults).
    bindings: dict[str, str] = _standard_dispatch_bindings(pipeline)
    for key, value in context.items():
        bindings[key] = str(value) if value is not None else ""

    # --- Bind all tokens -------------------------------------------------------
    for token, value in bindings.items():
        prompt = prompt.replace("{" + token + "}", value)

    # --- Residue guard: any surviving {lower_snake_or_digit} → refuse ----------
    residue = _PROMPT_RESIDUE_RE.findall(prompt)
    if residue:
        seen = _dedup_residue(residue)
        return {
            "ok": False,
            "refused": (
                f"dispatch-{cls}.md: unbound token(s) after binding: "
                + ", ".join(seen)
                + " — either add to @requires or remove from the template"
            ),
        }

    # --- Return assembled prompt + model assignment ----------------------------
    model = DISPATCH_MODELS.get(cls, "opus")
    result: dict = {"ok": True, "prompt": prompt, "model": model}

    # --- Meta cycle_header (Phase 7 WU-7.5a — MARKER-GATED) --------------------
    # When a run marker is present, attach a canonical cycle heading the
    # orchestrator echoes verbatim:  ### {Step} — {summary} [meta {m}]
    #   Step    : from DISPATCH_STEP_NAMES (per the Phase 7 interface contract).
    #   summary : the work summary — context item_name, fallback item_id, fallback
    #             the class name.
    #   m       : the marker's persisted meta counter + 1 — the cycle THIS dispatch
    #             will consume (1-based current-cycle semantics, matching the
    #             forward cycle_header's POST-advance convention noted in Phase 1).
    # COUNT ONLY — no "/cap" denominator: meta_cycles has NO ceiling (operator
    # decision 2026-06-14 — the meta loop is unbounded; only forward_cycles is
    # capped at max_cycles).
    # No marker → no cycle_header key at all, so no-marker emissions remain
    # byte-identical to the Phase 3/4 shape.
    marker = read_run_marker()
    if marker is not None:
        step = DISPATCH_STEP_NAMES.get(cls, cls)
        summary = (
            context.get("item_name")
            or context.get("item_id")
            or cls
        )
        meta_now = marker.get("meta_cycles", 0) or 0
        m = meta_now + 1
        result["cycle_header"] = f"### {step} — {summary} [meta {m}]"

    return result


# Frontmatter flag a skill declares to state "my contract orchestrates
# sub-subagents" (e.g. /execute-plan's test-agent/impl-agent split,
# /spec-phases' phase-writer launch, /spec's Explore fan-outs). The cycle
# marker copies this capability at --cycle-begin so the dispatch guard can
# honor the workstation sub-subagent exemption WITHOUT a hardcoded skill list
# (dispatch-guard-denies-workstation-subsubagent-split, decision 4 Round-11
# amendment: the discriminator MUST be a general skill-declared predicate —
# an allow-list re-opens the gap for every new sub-subagent-model skill).
_SUBAGENT_MODEL_FLAG_RE = re.compile(
    r"^subagent-model:\s*true\s*$", re.IGNORECASE | re.MULTILINE
)


def skill_declares_subagent_model(
    sub_skill: str | None,
    *,
    repo_root: "str | Path | None" = None,
) -> bool:
    """True iff *sub_skill*'s SKILL.md frontmatter declares ``subagent-model: true``.

    The predicate source of truth for the guard's workstation sub-subagent
    exemption (decision 4). Resolution order:

      1. Repo-scoped skill: ``<repo_root>/.claude/skills/<name>/SKILL.md``
         (when *repo_root* is provided) — covers repo-local skills like
         AlgoBooth's mcp-test family.
      2. User-level skill: ``<_SCRIPTS_DIR.parent>/skills/<name>/SKILL.md``
         (the package's scripts-dir anchor from ``_ctx``) — resolves to
         ``~/.claude/skills/`` for the live copy and
         ``<claude-config>/user/skills/`` for the repo copy (the same
         anchor _default_cycle_template_dir uses).

    Only the leading YAML frontmatter block (between the first two ``---``
    lines) is consulted, so prose mentioning the flag never false-positives.

    FAIL-CLOSED: a falsy/pseudo (``__*``) sub_skill, a missing SKILL.md, an
    unreadable file, or an absent flag all return False — the exemption never
    fires on uncertainty (the pre-fix deny is the safe degradation).

    Args:
        sub_skill: dispatched skill name (leading "/" tolerated); None → False.
        repo_root: optional repo root for the repo-scoped lookup.

    Returns:
        True only when the frontmatter flag is explicitly ``true``.
    """
    try:
        if not sub_skill or sub_skill.startswith("__"):
            return False
        norm = sub_skill[1:] if sub_skill.startswith("/") else sub_skill
        # Refuse path-traversal shapes outright (the name is a directory key).
        if not re.fullmatch(r"[A-Za-z0-9._-]+", norm):
            return False
        candidates: list[Path] = []
        if repo_root:
            candidates.append(
                Path(repo_root) / ".claude" / "skills" / norm / "SKILL.md"
            )
        candidates.append(
            _SCRIPTS_DIR.parent / "skills" / norm / "SKILL.md"
        )
        for skill_md in candidates:
            try:
                if not skill_md.is_file():
                    continue
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            # Extract the leading frontmatter block only.
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end == -1:
                continue
            frontmatter = text[3:end]
            if _SUBAGENT_MODEL_FLAG_RE.search(frontmatter):
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


# Frontmatter flag a skill declares to state "my dispatched cycle legitimately
# commits more than once" (adhoc-derive-multi-commit-budget-from-dispatch-sites,
# 2026-07-12) — the commit-budget-MEMBERSHIP analog of `subagent-model: true`
# above. Replaces the hand-maintained `_MULTI_COMMIT_DISPATCH_SKILLS` frozenset
# (see its retirement comment) as the input to `detect_cycle_bracket_friction`'s
# per-sub_skill commit-budget derivation.
_COMMIT_CADENCE_MULTI_FLAG_RE = re.compile(
    r"^commit-cadence:\s*multi\s*$", re.IGNORECASE | re.MULTILINE
)


def skill_declares_multi_commit(
    sub_skill: str | None,
    *,
    repo_root: "str | Path | None" = None,
) -> bool:
    """True iff *sub_skill* legitimately commits more than once per dispatch.

    The commit-budget MEMBERSHIP source of truth for
    ``detect_cycle_bracket_friction``'s branch-(3) derivation, replacing the
    hand-maintained ``_MULTI_COMMIT_DISPATCH_SKILLS`` frozenset. Modeled DIRECTLY
    on ``skill_declares_subagent_model`` (same resolution order, same fail-closed
    posture) — a skill declares its own commit cadence via a
    ``commit-cadence: multi`` YAML-frontmatter line, exactly like the
    ``subagent-model: true`` sibling flag.

    Two identities have no SKILL.md at all (the forward-advancing terminal
    pseudo-skills, which dispatch no Agent subagent and can never be "newly
    dispatched" from elsewhere): those are answered directly from the small,
    bounded ``_MULTI_COMMIT_PSEUDO_SKILLS`` dict, checked BEFORE the normal
    ``__``-prefix fail-closed short-circuit below (which would otherwise return
    False for them, same as any other pseudo-skill).

    Resolution order (real skills only):
      1. Repo-scoped skill: ``<repo_root>/.claude/skills/<name>/SKILL.md``
         (when *repo_root* is provided) — covers repo-local skills like
         AlgoBooth's mcp-test family.
      2. User-level skill: ``<_SCRIPTS_DIR.parent>/skills/<name>/SKILL.md``.

    Only the leading YAML frontmatter block is consulted, so prose mentioning the
    flag never false-positives.

    FAIL-CLOSED: a falsy sub_skill, a missing SKILL.md, an unreadable file, or an
    absent flag all return False — a newly-dispatched, unflagged skill falls to
    the conservative single-commit default (never a crash, never a silent
    escalation).

    Args:
        sub_skill: dispatched skill name (leading "/" tolerated); None → False.
        repo_root: optional repo root for the repo-scoped lookup.

    Returns:
        True when the pseudo-skill dict names it, or the frontmatter flag is
        explicitly ``true``.
    """
    try:
        if not sub_skill:
            return False
        if sub_skill in _MULTI_COMMIT_PSEUDO_SKILLS:
            return True
        if sub_skill.startswith("__"):
            return False
        norm = sub_skill[1:] if sub_skill.startswith("/") else sub_skill
        # Refuse path-traversal shapes outright (the name is a directory key).
        if not re.fullmatch(r"[A-Za-z0-9._-]+", norm):
            return False
        candidates: list[Path] = []
        if repo_root:
            candidates.append(
                Path(repo_root) / ".claude" / "skills" / norm / "SKILL.md"
            )
        candidates.append(
            _SCRIPTS_DIR.parent / "skills" / norm / "SKILL.md"
        )
        for skill_md in candidates:
            try:
                if not skill_md.is_file():
                    continue
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end == -1:
                continue
            frontmatter = text[3:end]
            if _COMMIT_CADENCE_MULTI_FLAG_RE.search(frontmatter):
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Process-friction detector (hardening-blind-to-process-friction Phase 2 / D1)
#
# The conservative expected-commit budget per dispatched sub_skill. Most cycles
# commit 0–1 times (one atomic gate+commit per plan-part / batch completion);
# anything beyond the budget is "unexpected commits" hardening signal. The budget
# is deliberately generous (defensible default = 1 for every sub_skill) so the
# detector never false-positives on a legitimate single-commit cycle — only a
# genuinely runaway cycle that strings several commits trips D1(b). A sub_skill
# absent from the map falls back to the default. (D1-out: no runtime-death
# heuristic — both signals are deterministic on-disk facts.)
# ---------------------------------------------------------------------------
_CYCLE_COMMIT_BUDGET_DEFAULT = 1
# The uniform commit ceiling granted to a multi-commit dispatch identity. Every
# multi-commit skill historically used the SAME number (3) — the per-skill budget
# never varied, so the budget is a binary "single-commit (default 1) vs.
# multi-commit (this ceiling)" decision keyed on skill_declares_multi_commit below.
_CYCLE_COMMIT_MULTI = 3

# Shared noise-allowance cushion (adhoc-align-cycle-commit-count-with-budget-
# population, 2026-07-12): the `unexpected-commits` NUMERATOR
# (`_count_authored_commits_since`) counts ONE uniform population — every authored
# non-merge commit — for every sub_skill alike, but only `execute-plan`'s DENOMINATOR
# (`_execute_plan_commit_budget`) modeled the noise categories that population
# legitimately includes (an in-cycle revert/self-correction, an off-plan commit
# landing mid-window, an unmodeled status-flip). Every OTHER registry-derived budget
# (branch 3 below — both the multi-commit ceiling and the single-commit default) had
# ZERO cushion, so the SAME noise categories Round 46 fixed for execute-plan remained
# fully exposed for every other multi-commit identity — most acutely `mcp-test`,
# whose ceiling equals its exact documented worst case with no headroom at all. This
# ONE small, skill-agnostic allowance applied uniformly in branch 3 closes that
# residual population mismatch WITHOUT touching `execute-plan`'s own already-correct
# work-scaled + bookend-cushioned model (which lives entirely in
# `_execute_plan_commit_budget`'s `budget_override` path and short-circuits branch 3
# via the `isinstance(budget_override, int) and budget_override > 0` check above).
# A genuine runaway (authored commits beyond the member/default ceiling + this
# allowance) STILL trips — no gate weakened, only the population mismatch closed.
_CYCLE_COMMIT_NOISE_ALLOWANCE = 1

# ---------------------------------------------------------------------------
# Per-skill ceiling OVERRIDE (commit-budget MAGNITUDE, not membership).
#
# `_MULTI_COMMIT_DISPATCH_SKILLS` above answers WHICH skills are multi-commit
# (the membership SSOT). This map answers HOW MANY commits a specific skill's
# WORST-CASE cadence legitimately makes, for the cases where the uniform
# `_CYCLE_COMMIT_MULTI` ceiling of 3 is too low for a skill's own documented
# cadence. A skill ABSENT from this map keeps the uniform ceiling — so this is
# additive and never lowers any skill's budget.
#
# `mcp-test` (4): the Step-9 /mcp-test validation cycle's documented worst-case
# cadence exceeds the original Round-23 "self-heal + sentinel/PHASES-reconcile"
# 2-commit estimate. A real cycle (2026-06-26 `pattern-abstractions`,
# begin_head_sha=0dd654ae39ce, budget=3, HEAD advanced 4 commits) committed FOUR
# legitimate, non-overlapping mcp-test-owned units, ALL within the mcp-test SKILL
# Step 3.4/Step 5 reconcile surface:
#   1. `4b9b3ddaa` self-heal (scenario `unlock_master_editor` fix + verdict/artifact)
#      + Phase-5 Runtime-Verification tick;
#   2. `0db5974e4` PHASES reconcile — tick Phase 1-4 RVs covered by the Phase-5 run;
#   3. `7b119b512` PHASES top-level Complete;
#   4. `d744204da` correct the engine-written VALIDATED.md schema.
# The PHASES reconcile (Step 5.2) legitimately fans out into sub-phase RV ticks +
# the top-level Complete flip (two commits), and the engine-written sentinel may
# need a schema correction — so the honest worst case is self-heal + 2-part
# reconcile + sentinel correction = 4. Budget 3 was exactly one short. Raising the
# SHARED `_CYCLE_COMMIT_MULTI` to 4 would loosen the runaway ceiling for `spec`,
# `write-plan`, `plan-feature`, etc. — a per-skill override keeps everyone else at
# 3 (no gate weakening) and gives only `mcp-test` its honest ceiling. The runaway
# ceiling for `mcp-test` itself is unchanged in KIND — a cycle beyond its declared
# cadence (>4) STILL trips `unexpected-commits`.
#
# NOTE — distinct from the `adhoc-derive-multi-commit-budget-from-dispatch-sites`
# spin-off (harden Round 38): that bug targets MEMBERSHIP derivation (which skills
# are multi-commit) and explicitly scopes OUT "any change to the friction-detection
# thresholds or the runaway ceiling". This map is the orthogonal MAGNITUDE
# dimension (how many commits a member legitimately makes) — see the over-fit
# spin-off for the magnitude class below.
# ---------------------------------------------------------------------------
_MULTI_COMMIT_CEILING_OVERRIDE: dict[str, int] = {
    "mcp-test": 4,
}

# ---------------------------------------------------------------------------
# RETIRED (adhoc-derive-multi-commit-budget-from-dispatch-sites, 2026-07-12):
# `_MULTI_COMMIT_DISPATCH_SKILLS` — the hand-maintained frozenset that used to be
# this SSOT — is gone. It required a human/hardening-agent to remember to append
# every new multi-commit dispatch identity here (a missing-row class that recurred
# 6+ times: Rounds 15, 16/17, 23, 31, 38), and it had ALREADY drifted stale in the
# opposite direction too (`retro-feature` stayed a member long after the Step-8
# retro phase was unwired 2026-06 and it stopped being dispatched from anywhere).
#
# Membership is now DERIVED from a `commit-cadence: multi` frontmatter flag the
# dispatched skill's OWN SKILL.md declares — see `skill_declares_multi_commit()`
# below, modeled directly on `skill_declares_subagent_model()` (same repo-scoped-
# then-user-level resolution order, same leading-frontmatter-only extraction, same
# fail-closed posture). A skill's own commit cadence now travels WITH the skill
# (a review-visible 1-line frontmatter edit), not in a separate module 3 hops
# away. `detect_cycle_bracket_friction` branch (3) consults it directly; a skill
# ABSENT from this derivation (including `retro-feature`, whose SKILL.md is left
# unflagged) falls to `_CYCLE_COMMIT_BUDGET_DEFAULT` exactly like before.
#
# The 2 forward-advancing terminal PSEUDO-skills (`__mark_complete__` /
# `__mark_fixed__`) have no SKILL.md (they dispatch no Agent subagent) and can
# never be "newly dispatched" from elsewhere, so they keep a small explicit,
# bounded dict below rather than a frontmatter lookup.
# ---------------------------------------------------------------------------
_MULTI_COMMIT_PSEUDO_SKILLS: frozenset[str] = frozenset({
    "__mark_complete__",
    "__mark_fixed__",
})


# ---------------------------------------------------------------------------
# Prompt-registry API
# ---------------------------------------------------------------------------

def normalize_prompt_for_hash(prompt: str) -> str:
    """Normalize a prompt before hashing so cosmetic copy artifacts cannot defeat
    the registry match while semantic edits still do.

    Five transforms, applied in order (Phase 7 WU-7.3b widened the original
    Phase 1 pair with two more — trailing-whitespace strip + Unicode NFC; leg 5
    added by F2b / lazy-validation-readiness Phase 2):
      1. CRLF (\\r\\n) → LF (\\n)
      2. Lone CR (\\r not followed by \\n) → LF (\\n)
      3. Per-line trailing-whitespace strip (rstrip each line) — a copy/paste
         that picks up trailing spaces or tabs on some lines must not change the
         hash (observed in session 2f6f27dc as a transcription-slip deny source).
      4. Unicode NFC normalization — a decomposed (NFD) variant of an accented
         character (e.g. an editor that emits combining marks) must hash equal to
         the composed (NFC) form.
      5. [F2b / lazy-validation-readiness] Fold Unicode characters the model trivially
         substitutes when retyping a script-emitted prompt:
           - em-dash U+2014, en-dash U+2013, horizontal bar U+2015,
             figure dash U+2012  →  hyphen-minus '-'
           - left single curly quote U+2018, right single curly quote U+2019  →  '
           - left double curly quote U+201C, right double curly quote U+201D  →  "
           - non-breaking space U+00A0, narrow NBSP U+202F  →  regular space
         Applied AFTER NFC so code-point normalization happens first.  These are
         purely cosmetic punctuation/space variants; a genuine word change still
         alters the hash (the fold cannot collapse distinct words).  This makes an
         em-dash/curly-quote/NBSP slip on an otherwise-verbatim emitted prompt
         hash-equal → ALLOW without any guard change.  It also improves the F1b
         auto-readmit near-match (shares this normalize) for free.

    This ensures that a prompt registered on Windows (with CRLF line endings,
    trailing whitespace, or NFD text) produces the same sha256 as the same prompt
    re-typed clean, so Windows/WSL round-trips and editor quirks cannot defeat the
    registry match.  A genuine word change still alters the hash (the deny still
    fires for a real edit).  The SPEC requires CRLF normalization in §Validate-deny
    step 1; WU-7.3b adds the trailing-whitespace + NFC legs; F2b / lazy-validation-
    readiness Phase 2 adds the dash/quote/NBSP folding leg.
    """
    # Step 1: collapse CRLF → LF
    normalized = prompt.replace("\r\n", "\n")
    # Step 2: replace any remaining lone CRs with LF
    normalized = normalized.replace("\r", "\n")
    # Step 3: strip trailing whitespace from each line (newlines preserved).
    # Splitting on "\n" after steps 1+2 means every line boundary is a single LF.
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    # Step 4: Unicode NFC — fold decomposed sequences into their composed form so
    # an NFD copy hashes identically to the clean NFC form.
    normalized = unicodedata.normalize("NFC", normalized)
    # Step 5 (F2b / lazy-validation-readiness): fold cosmetic Unicode punctuation/
    # space substitutes that the model trivially introduces when retyping a prompt.
    # Applied after NFC so we operate on fully-composed code points.
    # Translation table built once (str.translate is O(n) and very fast).
    normalized = normalized.translate(_NORM_FOLD_TABLE)
    return normalized


# F2b (lazy-validation-readiness Phase 2): translation table for leg 5 of
# normalize_prompt_for_hash.  Maps Unicode cosmetic-substitute code points to their
# ASCII equivalents.  Keys are Unicode code-point integers; values are the folded
# strings (str.translate allows multi-char replacements via a mapping str→str on the
# table, but for 1-to-1 folds it is more efficient to map ord→ord or ord→str).
#
# Dashes: em-dash U+2014, en-dash U+2013, horizontal bar U+2015, figure dash U+2012
#         → hyphen-minus U+002D '-'
# Single quotes: U+2018 LEFT SINGLE QUOTATION MARK, U+2019 RIGHT SINGLE QUOTATION MARK
#                → apostrophe U+0027 "'"
# Double quotes: U+201C LEFT DOUBLE QUOTATION MARK, U+201D RIGHT DOUBLE QUOTATION MARK
#                → quotation mark U+0022 '"'
# Spaces: U+00A0 NO-BREAK SPACE, U+202F NARROW NO-BREAK SPACE → U+0020 ' '
_NORM_FOLD_TABLE: dict = str.maketrans(
    {
        0x2014: "-",   # EM DASH
        0x2013: "-",   # EN DASH
        0x2015: "-",   # HORIZONTAL BAR
        0x2012: "-",   # FIGURE DASH
        0x2018: "'",   # LEFT SINGLE QUOTATION MARK
        0x2019: "'",   # RIGHT SINGLE QUOTATION MARK
        0x201C: '"',   # LEFT DOUBLE QUOTATION MARK
        0x201D: '"',   # RIGHT DOUBLE QUOTATION MARK
        0x00A0: " ",   # NO-BREAK SPACE
        0x202F: " ",   # NARROW NO-BREAK SPACE
    }
)


def prompt_sha256(prompt: str) -> str:
    """Return the hex sha256 of a prompt after normalizing line endings.

    Uses normalize_prompt_for_hash() before hashing so CRLF and LF variants
    of the same prompt produce identical digests.
    """
    normalized = normalize_prompt_for_hash(prompt)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def registry_summary() -> str:
    """Return a short one-line summary of the prompt-registry state.

    Phase 8 WU-8.2: bound into the routed-hardening-debt ``hardening_emit_command``
    as ``--context registry_state=...`` so the dispatched hardening subagent has
    a snapshot of how many emissions are outstanding.  Read-only.

    Returns:
        ``"empty"`` when there are no entries, otherwise
        ``"<N> entries, <M> unconsumed"``.
    """
    entries = _load_registry().get("entries", [])
    if not entries:
        return "empty"
    unconsumed = sum(1 for e in entries if not e.get("consumed", False))
    return f"{len(entries)} entries, {unconsumed} unconsumed"


def consumed_emission_count(cls: str | None = None) -> int:
    """Return the number of CONSUMED registry entries — the dispatch oracle.

    The validate-deny guard calls ``consume_nonce`` on every ALLOW (one consume
    per dispatch), so this monotone-within-the-ring count is a sound "how many
    dispatches have landed" signal.  ``update_repeat_counts`` (F2) reads it twice
    around a re-read: an UNCHANGED consumed-count between two identical step
    probes means NO dispatch happened between them → the second probe is a
    re-read, not a re-attempt → hold the step counter (double-probe debounce).

    ``cls`` (loop-detector-false-positives-probes-and-cross-run-state, Residual
    gap A): when given, count ONLY consumed entries whose ``class`` field equals
    ``cls`` (e.g. ``"cycle"``) instead of every consumed entry regardless of
    class. The F1/F2 oracle in ``update_repeat_counts`` uses ``cls="cycle"`` so
    a mid-step META-class dispatch (``hardening``, ``recovery``,
    ``coherence-recovery``, ``investigation``, ``input-audit``, …) no longer
    counts as "a dispatch landed between probes" for the streak debounce — only
    a genuine forward CYCLE attempt does. Every OTHER caller (the
    forward/meta-cycle watermark machinery in ``advance_run_counters`` etc.)
    keeps calling this with no argument (``cls=None``), which is
    byte-identical to the pre-existing unfiltered count.

    Read-only: ``_load_registry`` passes ``create=False`` so a probe never
    creates the state dir as a side-effect, and returns ``{"entries": []}`` (→ 0)
    on any missing / corrupt registry.  The registry ring-cap can evict the
    oldest entries, but the debounce only compares two consecutive probes within
    one run, where eviction of a consumed entry between adjacent probes is not a
    concern (it would only *lower* the count, never spuriously raise it, so it
    can at worst fail-open into an increment — never a spurious hold).

    NON-MONOTONIC CAVEAT (Phase 2, byref-dispatch-undercounts-forward-cycles): this
    census is a LIVE count over the ring-capped registry, so once cumulative
    emissions cross ``_REGISTRY_RING_CAP`` (64) the oldest CONSUMED entries are
    evicted and this count steps DOWN.  The run-lifetime ``last_advance_consume_count``
    watermark in ``advance_run_counters`` (NOT the F2 double-probe debounce above —
    that compares only adjacent probes) is now CLAMPED against this one-time downward
    step: a watermark stranded above the live census re-arms (advances once) instead
    of no-oping forever, so ring-cap eviction can no longer permanently strand the
    forward/meta gate.  The forward-cycle COUNT itself no longer depends on this
    oracle at all (Phase 1 routed it through the consume-independent
    ``advance_forward_cycle`` state-change trigger); this caveat governs only the
    residual watermark consumers.

    Returns:
        The count of entries whose ``consumed`` flag is truthy (0 when empty),
        optionally restricted to entries whose ``class`` equals ``cls``.
    """
    entries = _load_registry().get("entries", [])
    if cls is not None:
        return sum(
            1 for e in entries
            if e.get("consumed", False) and e.get("class") == cls
        )
    return sum(1 for e in entries if e.get("consumed", False))


def _save_registry(data: dict) -> None:
    """Persist the registry dict to disk atomically."""
    registry_path = claude_state_dir() / _REGISTRY_FILENAME
    _atomic_write(registry_path, json.dumps(data, indent=2) + "\n")


def register_emission(
    prompt: str,
    cls: str,
    item_id: str | None = None,
    now: float | None = None,
    model: str | None = None,
) -> dict:
    """Register a prompt emission in the prompt registry.

    Each registration creates one entry in ``lazy-prompt-registry.json`` with:
      - nonce (str): unique uuid4 hex string — single-use control
      - prompt_sha256 (str): sha256 of the normalized prompt
      - prompt_norm (str): the normalize_prompt_for_hash-normalized prompt text.
        Stored verbatim (not just hashed) so the validate-deny guard can do a
        pure trailing-suffix superset match for F1b auto-readmit
        (lazy-pipeline-ergonomics Phase 1).  Registry entries are ephemeral
        (ring-cap + TTL) so storing the text is size-safe.
      - prompt_raw (str): the EXACT original prompt bytes before any normalization.
        F2a (lazy-validation-readiness Phase 3): stored so that
        resolve_emission_by_nonce() can return the EXACT original text for a
        by-reference dispatch — the guard resolves nonce → prompt_raw and returns
        it via hookSpecificOutput.updatedInput, so the spawned subagent receives
        the fully-expanded prompt without any retyping.
      - emitted_at (float): epoch timestamp of the emission
      - class (str): dispatch class tag (e.g. "cycle", "recovery", "hardening")
      - item_id (str|None): the feature/bug id for context (optional)
      - consumed (bool): False until consume_nonce() is called
      - model (str|None): the script-selected model tier for this dispatch
        (mechanize-prose-only-orchestrator-contracts (a) — model-tier pinning).
        Populated from the emitter's return value at every registration site;
        the validate-deny guard's ALLOW paths correct the dispatched
        ``model:`` field to this value when it differs (pin-by-rewrite).
        None on a legacy/unrelated registration — the guard fails open (no
        pin) rather than pinning against an unknown tier.

    Ring cap: when the registry would exceed ``_REGISTRY_RING_CAP`` (64) entries,
    the oldest entry (lowest index, earliest emitted_at) is evicted first.  This
    keeps the registry bounded regardless of run length.

    Args:
        prompt: the dispatch prompt text (normalized before hashing)
        cls: the dispatch class tag (e.g. "cycle")
        item_id: the feature or bug id associated with this dispatch (optional)
        now: epoch float for emitted_at (injectable for hermetic tests;
             defaults to time.time())

    Returns:
        The newly created entry dict.
    """
    from ._monolith import _REGISTRY_RING_CAP  # Phase-5 re-point (marker/registry plane still monolith-resident)
    if now is None:
        now = time.time()

    entry: dict = {
        "nonce": uuid.uuid4().hex,
        "prompt_sha256": prompt_sha256(prompt),
        # F1b: store the normalized prompt text so the guard can prefix-match a
        # pure trailing suffix (auto-readmit) using identical normalization.
        "prompt_norm": normalize_prompt_for_hash(prompt),
        # F2a (lazy-validation-readiness Phase 3): store the EXACT original bytes
        # so resolve_emission_by_nonce() can return them verbatim for by-reference
        # dispatch — the guard copies prompt_raw into updatedInput.prompt so the
        # spawned subagent receives the fully-expanded original prompt, eliminating
        # the byte-exact-retype requirement for the orchestrator.
        "prompt_raw": prompt,
        "emitted_at": now,
        "class": cls,
        "item_id": item_id,
        "consumed": False,
        "model": model,
    }

    data = _load_registry()
    entries: list = data["entries"]
    entries.append(entry)

    # Ring cap: evict the oldest entry (index 0) when over the cap.
    # The list is ordered by insertion time; oldest is always index 0.
    while len(entries) > _REGISTRY_RING_CAP:
        entries.pop(0)

    data["entries"] = entries
    _save_registry(data)
    return entry


def lookup_emission(
    prompt: str,
    now: float | None = None,
) -> dict | None:
    """Look up an unconsumed, fresh registry entry by prompt hash.

    Freshness has two components (belt-and-braces):
      1. Nonce + TTL: entry must be unconsumed AND within
         REGISTRY_ENTRY_TTL_SECONDS (1800 s) of ``emitted_at``.
      2. Run-start gate (when a non-stale run marker exists): additionally
         require ``emitted_at`` >= marker's ``started_at`` epoch — entries
         that were written before the current run started are never
         dispatchable even if they are within the TTL.  When no run marker is
         present this gate is skipped and only nonce+TTL semantics apply.

    Returns the first matching entry, or None when:
      - no entry with this prompt's sha256 exists, OR
      - all matching entries are consumed, beyond the TTL, OR predate the
        current run's started_at.

    Args:
        prompt: the prompt text to look up (normalized before hashing)
        now: epoch float for TTL comparison (injectable; defaults to time.time())

    Returns:
        The matching entry dict, or None.
    """
    from ._monolith import REGISTRY_ENTRY_TTL_SECONDS, read_run_marker  # Phase-5 re-point (marker/registry plane still monolith-resident)
    if now is None:
        now = time.time()
    target_sha = prompt_sha256(prompt)

    # Compute the run-start epoch once for all entry comparisons.
    # read_run_marker is a read-only path (no mkdir) and returns None when
    # there is no active (or non-stale) run — in that case the freshness gate
    # is skipped and only nonce+TTL semantics apply.
    marker = read_run_marker(now=now)
    run_started_epoch: float | None = None
    if marker is not None:
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(
                started_at_str, "%Y-%m-%dT%H:%M:%SZ"
            )
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            # Unrecognised format — skip the run-start gate for safety.
            run_started_epoch = None

    data = _load_registry()
    for entry in data["entries"]:
        if entry.get("prompt_sha256") != target_sha:
            continue
        if entry.get("consumed", True):
            # Already consumed — not dispatchable.
            continue
        emitted_at = entry.get("emitted_at", 0.0)
        if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
            # Beyond TTL — not dispatchable (re-probe required).
            continue
        if run_started_epoch is not None and emitted_at < run_started_epoch:
            # Entry predates the current run — not dispatchable.  A re-probe
            # (new register_emission call) is required to get a fresh entry.
            continue
        return entry
    return None


def resolve_emission_by_nonce(
    nonce: str,
    *,
    now: float | None = None,
) -> dict | None:
    """Look up a registry entry by nonce and return it ONLY when dispatchable.

    F2a (lazy-validation-readiness Phase 3): the by-reference dispatch path.
    The guard calls this when it receives a ``@@lazy-ref nonce=<hex>`` prompt
    token.  If the nonce resolves to a fresh, unconsumed, run-start-gated entry,
    the guard returns ``permissionDecision: "allow"`` PLUS
    ``hookSpecificOutput.updatedInput`` (with ``prompt = entry["prompt_raw"] or
    entry["prompt_norm"]``), so the spawned subagent receives the fully-expanded
    prompt without any retyping.

    Freshness gates mirror ``lookup_emission`` exactly:
      1. Nonce + TTL: entry must be unconsumed AND within
         REGISTRY_ENTRY_TTL_SECONDS (1800 s) of ``emitted_at``.
      2. Run-start gate (when a non-stale run marker exists): additionally
         require ``emitted_at >= marker.started_at`` epoch — entries predating
         the current run are not dispatchable even if within TTL.

    This function is READ-ONLY and fail-safe: any error → None (fail-open to
    deny, never a spurious allow).  The guard is responsible for consuming the
    nonce after resolving it.

    Args:
        nonce: the nonce hex string from the ``@@lazy-ref`` token.
        now: epoch float for TTL comparison (injectable for hermetic tests;
             defaults to time.time()).

    Returns:
        The matching registry entry dict when dispatchable, or None when:
          - the nonce does not exist in the registry, OR
          - the entry is consumed, OR
          - the entry is beyond TTL, OR
          - the entry predates the current run's started_at.
    """
    from ._monolith import REGISTRY_ENTRY_TTL_SECONDS, read_run_marker  # Phase-5 re-point (marker/registry plane still monolith-resident)
    if now is None:
        now = time.time()

    try:
        # Compute the run-start epoch gate (mirrors lookup_emission).
        marker = read_run_marker(now=now)
        run_started_epoch: float | None = None
        if marker is not None:
            started_at_str = marker.get("started_at", "")
            try:
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                run_started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
            except (ValueError, TypeError):
                run_started_epoch = None

        data = _load_registry()
        for entry in data["entries"]:
            if entry.get("nonce") != nonce:
                continue
            # Gate 1: must be unconsumed.
            if entry.get("consumed", True):
                return None
            # Gate 2: must be within TTL.
            emitted_at = entry.get("emitted_at", 0.0)
            if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
                return None
            # Gate 3: must not predate the current run (when a marker is present).
            if run_started_epoch is not None and emitted_at < run_started_epoch:
                return None
            # All gates passed — this entry is dispatchable by reference.
            return entry
        # Nonce not found in registry.
        return None
    except Exception:  # noqa: BLE001
        # Fail-safe: any error → None so the guard falls through to deny,
        # never a spurious allow.
        return None


def append_dispatch_by_reference_event(
    *,
    tool_use_id: str,
    nonce: str,
    resolved_sha12: str,
    item_id: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``dispatch_by_reference: true`` audit event to the deny ledger.

    F2a (lazy-validation-readiness Phase 3): every by-reference allow must write
    an auditable record to the same deny ledger (JSONL) used by denies and
    auto-readmits, so the path is retro-gradable and distinguishable from a
    verbatim allow.

    Event shape (mirrors append_auto_readmit_event for reader uniformity):

        {"ts": <epoch float>, "tool_use_id": <str>,
         "dispatch_by_reference": true, "nonce": <hex>,
         "resolved_sha12": <12 hex chars of the resolved prompt's sha256>,
         "item_id": <str|None>, "acked": true}

    ``acked`` is True because a by-reference allow owes NO hardening debt —
    it is a sanctioned dispatch path, not a harness gap.

    Best-effort / fail-open: mirrors the contract of append_auto_readmit_event —
    the caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising.

    Args:
        tool_use_id: the dispatched Agent tool_use_id.
        nonce: the ``@@lazy-ref`` nonce that was resolved.
        resolved_sha12: first 12 hex chars of the resolved prompt's sha256
                        (for retro correlation without storing the full sha).
        item_id: the matched entry's feature/bug id (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        event = {
            "ts": now,
            "tool_use_id": tool_use_id,
            # Discriminator field: retro readers filter on this to see
            # by-reference dispatches separately from verbatim allows and denies.
            "dispatch_by_reference": True,
            "nonce": nonce,
            "resolved_sha12": resolved_sha12,
            "item_id": item_id,
            # Pre-acked: by-reference dispatches owe no hardening debt — they are
            # the SAFE path (bytes come from the registered emission, not from
            # hand-composition), so they must never inflate pending_hardening()
            # or block --run-end.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        # Plain append (same pattern as append_deny_ledger_entry and
        # append_auto_readmit_event): the ledger is append-only and a torn final
        # line is tolerated by the corrupt-line-skipping reader.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate to the guard.
        return False


def emission_consumed_by_nonce(nonce: str) -> bool:
    """Return True iff a registry entry with this nonce exists AND is consumed.

    dispatch-guard-denies-workstation-subsubagent-split (decision 4, 2026-07-10):
    this is the CONSUMED FENCE for the guard's workstation sub-subagent
    exemption. The cycle marker is written by ``--cycle-begin`` BEFORE the
    orchestrator's own worker dispatch, so "cycle marker active" alone would
    open a window where the orchestrator itself could improvise an unregistered
    dispatch under its freshly-armed cycle marker. Requiring the cycle's OWN
    registered emission to already be consumed closes that window: consumption
    happens only on the guard-ALLOWed worker dispatch, session tool calls are
    serial, and the marker is cleared at ``--cycle-end`` — so any unregistered
    Agent prompt arriving while (marker active AND its emission consumed) can
    only originate INSIDE the in-flight cycle worker.

    Deliberately ignores TTL and the run-start gate: the question is "did the
    dispatch land", not "is the entry still dispatchable" (a long cycle may
    outlive the 1800 s registry TTL and its sub-subagent dispatches must not
    start re-denying mid-cycle).

    Read-only and FAIL-CLOSED: any error (missing/corrupt registry, absent
    nonce) returns False — the exemption never fires on uncertainty, so a
    failure here degrades to the pre-fix deny, never to a spurious allow.

    Args:
        nonce: the cycle marker's dispatch nonce.

    Returns:
        True when the entry exists and its ``consumed`` flag is truthy.
    """
    try:
        if not nonce:
            return False
        for entry in _load_registry().get("entries", []):
            if entry.get("nonce") == nonce:
                return bool(entry.get("consumed", False))
        return False
    except Exception:  # noqa: BLE001
        return False


def append_worker_subdispatch_event(
    *,
    tool_use_id: str,
    sha12: str,
    item_id: str | None = None,
    sub_skill: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``worker_subdispatch: true`` audit event to the deny ledger.

    dispatch-guard-denies-workstation-subsubagent-split (decision 4): every
    guard ALLOW taken through the workstation sub-subagent exemption writes an
    auditable record to the same deny ledger used by denies, auto-readmits, and
    by-reference dispatches, so the exemption path is retro-gradable and
    distinguishable from a registered-prompt allow.

    Event shape (mirrors append_dispatch_by_reference_event for reader
    uniformity):

        {"ts": <epoch float>, "tool_use_id": <str>,
         "worker_subdispatch": true, "sha12": <12 hex chars>,
         "item_id": <str|None>, "sub_skill": <str|None>, "acked": true}

    ``acked`` is True because an exempted sub-subagent dispatch owes NO
    hardening debt — it is a sanctioned dispatch path (the cycle worker
    following its skill's own orchestration model), not a harness gap — so it
    must never inflate ``pending_hardening()`` or block ``--run-end``.

    Best-effort / fail-open: swallows its own write errors and returns False
    rather than raising (a ledger failure must never affect the allow).

    Args:
        tool_use_id: the dispatched Agent tool_use_id.
        sha12: first 12 hex chars of the dispatched prompt's sha256.
        item_id: the active cycle marker's feature/bug id (optional).
        sub_skill: the active cycle marker's sub_skill (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        event = {
            "ts": now,
            "tool_use_id": tool_use_id,
            # Discriminator field: retro readers filter on this to see exempted
            # worker sub-subagent dispatches separately from other allow paths.
            "worker_subdispatch": True,
            "sha12": sha12,
            "item_id": item_id,
            "sub_skill": sub_skill,
            # Pre-acked: a sanctioned dispatch path owes no hardening debt.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return True
    except Exception:  # noqa: BLE001
        return False


def consume_nonce(nonce: str, consumer: str | None = None) -> bool:
    """Mark a registry entry's nonce as consumed (one dispatch per emission).

    After consumption, ``lookup_emission`` will no longer return this entry,
    enforcing the single-use constraint: a re-dispatch requires a re-probe,
    which is the continuation-cycles-must-re-emit rule made mechanical.

    Phase 2 extension: when ``consumer`` is provided (non-None), the
    ``consumed_by`` field is written onto the entry.  This enables the
    idempotent re-fire logic in ``lazy_guard.py`` — when the PreToolUse hook
    fires twice for the same denied dispatch (same tool_use_id, E4 spike
    finding), the guard reads ``consumed_by`` and allows the second call if
    the consumer matches.

    Backward compatibility: ``consumer=None`` (the default) preserves Phase 1
    behavior exactly — the entry is consumed but no ``consumed_by`` field is
    written.  All 264 existing test_lazy_core.py tests rely on this.

    Args:
        nonce: the nonce string from a previously registered entry
        consumer: optional string identifying the consumer (e.g. tool_use_id);
                  stored as ``consumed_by`` on the entry when provided.

    Returns:
        True if the nonce was found and consumed; False if not found or already
        consumed.
    """
    data = _load_registry()
    changed = False
    for entry in data["entries"]:
        if entry.get("nonce") == nonce:
            if entry.get("consumed", False):
                # Already consumed — idempotent False.
                return False
            entry["consumed"] = True
            # Phase 2: record the consuming tool_use_id when provided so the
            # guard can distinguish idempotent re-fire (same consumer) from a
            # legitimately distinct second attempt (different consumer → deny).
            if consumer is not None:
                entry["consumed_by"] = consumer
            changed = True
            break
    if not changed:
        return False
    _save_registry(data)
    return True


def register_emission_if_marked(
    prompt: str,
    cls: str,
    item_id: str | None = None,
    now: float | None = None,
    model: str | None = None,
) -> dict | None:
    """Register a prompt emission only when a valid run marker is present.

    This is the primary integration point for both state scripts' --emit-prompt
    handling: after computing a cycle_prompt, the script calls this function.
    If no marker is active → no-op (returns None, writes nothing).  This
    ensures default (no-marker) invocations remain byte-identical and the
    registry file is never created by accident.

    SPEC: all new Phase 1 behavior is unreachable without an explicit --run-start
    call (A10: byte-identical default output guarantee).

    Args:
        prompt: the dispatch prompt text
        cls: the dispatch class (e.g. "cycle")
        item_id: the feature or bug id (optional)
        now: epoch float (injectable; defaults to time.time())

    Returns:
        The registry entry dict if a marker is present and the registration
        succeeded; None otherwise (no marker = no write).
    """
    from ._monolith import read_run_marker  # Phase-5 re-point (marker/registry plane still monolith-resident)
    if now is None:
        now = time.time()
    # read_run_marker applies all staleness guards — if it returns None there
    # is no active run and we must not write.
    marker = read_run_marker(now=now)
    if marker is None:
        return None
    return register_emission(prompt, cls=cls, item_id=item_id, now=now, model=model)
