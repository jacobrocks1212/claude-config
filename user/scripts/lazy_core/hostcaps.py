"""lazy_core.hostcaps — the host-capability declaration + probe seam.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 2, Batch 3, WU-3) — a move-only refactor with zero behavior change. Owns
the ``requires_host:`` declaration parse (SPEC frontmatter + queue.json entry),
the closed capability-id registry + probe-config vocabulary, the per-run
present-capability resolver (with its state-dir cache), and the shared
unknown-capability BLOCKED.md body formatter. See
docs/features/host-capability-declaration-for-gated-features and
user/scripts/CLAUDE.md -> "The host-capability axis" for the full contract.

HARD EXCLUSION (per the WU-3 slice boundary): ``write_deferred_requires_host``
is a sentinel WRITER (write-path) and stays in ``_monolith.py`` — this module
was sliced AROUND it, ending at ``format_unknown_host_capability_blocker``.

``utc_now_iso`` sits mid-seam under its own "Phases 4 + 5" mini section header
in the original monolith (a generic time helper, "one-line reuse" of broader
infra). It moved here WITH the rest of the contiguous slice rather than being
sliced back out: a grep of ``_monolith.py`` at extraction time found ZERO
remaining bare-name (``utc_now_iso(...)``) consumers there (every caller reads
it via the facade, ``lazy_core.utc_now_iso()``), and ``test_lazy_core.py``
never patches it by module-attribute assignment (``lazy_core._monolith.utc_now_iso
= ...``) — only facade-level calls. Smallest blast radius: no import-back, no
test redirect.

Two monolith-resident dependencies are resolved via function-local deferred
imports (this module must not import ``_monolith`` at top level — that would
be circular, since ``_monolith`` imports FROM this module for the names
below):

- ``host_present_capabilities`` calls ``read_run_marker()`` (the marker
  plane — ``.markers`` since Phase-5 WU-1) and ``claude_state_dir()``
  (``.statedir`` since Phase 2 WU-5).
- ``_default_host_probes`` calls the Phase-2 active-invocation probe
  primitives ``probe_binary_capability`` / ``probe_env_capability`` /
  ``probe_platform_capability``. These live in a separate, NON-contiguous
  section of ``_monolith.py`` (lines ~7180-7300, "host-capability-declaration
  Phase 2") and were deliberately NOT chased into this slice — the WU scope is
  the ONE contiguous Phase 1/3/4/5 range; a partial plane is fine (a later
  Phase-5 residue sweep can move the Phase-2 probes too).
"""

from __future__ import annotations

import datetime
import json
import re
import time

import yaml

from pathlib import Path

from ._ctx import _atomic_write


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phase 1
#   The `requires_host:` declaration parse + the closed-registry vocabulary.
#
# A feature records the named host capabilities its runtime validation requires
# in a `requires_host:` set (SPEC frontmatter and/or queue.json entry). The set
# is matched against the host's probed-present set; a miss defers the feature to
# a capability-bearing host. The vocabulary is a CLOSED registry: a capability id
# exists only if the registry maps it to a probe callable (the callable wiring
# lands in Phase 3 — Phase 1 defines the id vocabulary as the dict's KEYS). An
# unregistered id is a loud fail-fast (Phase 4), never a silent defer-forever.
# ---------------------------------------------------------------------------

# Capability ids share the feature-id shape: lowercase alnum, internal dashes.
_HOST_CAPABILITY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The closed v1 registry. KEYS are the closed vocabulary (the only ids a feature
# may declare); VALUES are probe-callable PLACEHOLDERS — Phase 3 (WU-3) rebinds
# each to a real injected probe via host_present_capabilities' production
# bindings. A capability id only "exists" if it is a key here; an id absent from
# this map is an unknown-capability fail-fast (Phase 4). Keep this the single
# source of truth for "what ids exist" — both the fail-fast and the Phase-5
# match read it.
_HOST_CAPABILITY_REGISTRY: dict[str, object] = {
    # Generalizes the proven $ALGOBOOTH_REAL_AUDIO_DEVICE device axis.
    "real-audio-device": None,
    # A C++ toolchain (Zimtohrli golden:report) — the canonical binary-host gap
    # (session a0eae4be: audio-quality-analysis et al. gate on this absent).
    "zimtohrli-toolchain": None,
    # A GPU device.
    "gpu": None,
    # A motorized/MCU MIDI control surface (physical fader travel, MCU Device
    # Query handshake byte observation). The device axis ($ALGOBOOTH_REAL_AUDIO_
    # DEVICE) is AUDIO-only and cannot express this — a host with real audio but
    # no MIDI surface MUST defer (not re-open) MIDI-hardware scenarios. Added for
    # motorized-fader-sync, whose 2 hardware RV rows looped on the audio-axis
    # device re-open (Round 40). The fix: features needing MIDI hardware declare
    # `requires_host: midi-controller` + DEFERRED_REQUIRES_HOST.md, so a non-MIDI
    # host defers cleanly (host-capability-saturated) instead of looping.
    "midi-controller": None,
    # A 2nd Ableton Link peer reachable on the LAN (device-vs-host mis-
    # classification, Round 41, 2026-06-29). d5-ableton-link's multi-peer
    # scenarios (peerCount:0 on a solo host) were written DEFERRED_REQUIRES_DEVICE
    # by the cycle and looped: a real-audio-device host re-opens them (Step 9) but
    # cannot certify them (no 2nd peer), tripping the step-repeat tripwire. The
    # unmet prerequisite is a HOST capability (a peer), not an audio device. No
    # automated probe exists — a solo host cannot self-detect a 2nd peer — so this
    # id intentionally has NO _HOST_CAPABILITY_PROBE_CONFIG entry and binds to the
    # constant-False placeholder (fail-safe absent: it re-opens only when a future
    # mock_peers / peer probe is configured).
    "link-multi-peer": None,
    # A Linux or macOS host (device-vs-host mis-classification, Round 41,
    # 2026-06-29). non-windows-audio-hardening's cfg(unix) code is un-runnable on
    # Windows; the cycle wrote DEFERRED_REQUIRES_DEVICE and looped (a real-audio-
    # device WINDOWS host re-opens but can never run cfg(unix) code). The unmet
    # prerequisite is the OS, not an audio device. Unlike link-multi-peer, the OS
    # IS deterministically detectable — this id DOES have a probe (kind "platform",
    # predicate "non-windows") so a non-Windows host reports it present and certifies.
    "non-windows-host": None,
}

# Module-load assertion: every registered id is shape-valid (a typo in the
# registry itself is a developer error, surfaced at import, never at runtime).
assert all(
    _HOST_CAPABILITY_ID_RE.match(_cap_id) for _cap_id in _HOST_CAPABILITY_REGISTRY
), "every _HOST_CAPABILITY_REGISTRY key must match ^[a-z0-9][a-z0-9-]*$"


def _coerce_capability_ids(value: object) -> set[str]:
    """Coerce a raw `requires_host:` value into a set of shape-valid capability
    ids (tolerant input, same spirit as the independent-marker coercion).

    Accepts a list/tuple of strings OR a single string (comma- and/or
    whitespace-separated). Each token is stripped; tokens that do NOT match the
    capability-id shape are DROPPED (the parse never emits a shape-invalid id —
    an unregistered-but-shaped typo is caught later by ``unknown_capability_ids``
    at the fail-fast; a mis-shaped token is simply not a capability). Anything
    that is neither a string nor a list/tuple yields the empty set.
    """
    def _split(raw: str) -> list[str]:
        # Tolerate an inline YAML/JSON flow-list literal `[a, b]` (frontmatter is
        # scanned as raw lines, not YAML-parsed) by stripping the surrounding
        # brackets, then split on commas/whitespace and strip any quotes.
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        return [tok.strip().strip("'\"") for tok in re.split(r"[,\s]+", raw)]

    tokens: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                tokens.extend(_split(item))
    elif isinstance(value, str):
        tokens.extend(_split(value))
    return {t for t in tokens if t and _HOST_CAPABILITY_ID_RE.match(t)}


# Matches a frontmatter line `requires_host: <value>` (case-insensitive key,
# leading whitespace tolerated). The captured tail is coerced by
# _coerce_capability_ids — a list literal `[a, b]` or a bare comma/space string.
_REQUIRES_HOST_RE = re.compile(
    r"^\s*requires_host\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)


def parse_requires_host(spec_text: str, queue_entry: dict | None) -> set[str]:
    """Deterministic two-source read of a feature's `requires_host:` capability
    set (host-capability-declaration-for-gated-features Phase 1).

    Mirrors ``parse_independent_marker``'s two-source fenced-block walk. Returns
    the UNION of the capability ids declared in EITHER the SPEC.md frontmatter OR
    the ``queue.json`` entry. Absent/legacy (no ``requires_host:`` anywhere) ⇒
    the EMPTY set — the ungated baseline-regression rail (a feature without the
    field behaves exactly as today). On-disk, deterministic — no LLM judgment.

    Input is tolerant (via ``_coerce_capability_ids``): a YAML/JSON list value
    ``[a, b]`` and a bare comma/space-separated string both parse to the same
    set; shape-invalid tokens are dropped (never emitted).

    Args:
        spec_text: the raw SPEC.md text (its leading ``---`` fenced frontmatter
            block is scanned when present, else the head of the file up to the
            first markdown heading — a bare leading marker).
        queue_entry: the feature's ``queue.json`` entry (may be ``None``/empty).

    Returns:
        The set of declared capability ids (possibly empty).
    """
    result: set[str] = set()
    # Source 1: the queue entry (a JSON list or string under `requires_host`).
    if isinstance(queue_entry, dict) and "requires_host" in queue_entry:
        result |= _coerce_capability_ids(queue_entry.get("requires_host"))
    # Source 2: the SPEC.md frontmatter. Scan the leading `---` fenced block if
    # present; otherwise scan the head of the file up to the first heading.
    if isinstance(spec_text, str) and spec_text:
        lines = spec_text.splitlines()
        in_fence = False
        fence_seen = False
        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if not fence_seen and not in_fence:
                    in_fence = True
                    fence_seen = True
                    continue
                if in_fence:
                    # Closing fence — stop scanning the frontmatter block.
                    break
            if fence_seen and not in_fence:
                # We have already consumed a fenced block; don't scan the body.
                break
            if not fence_seen and stripped.startswith("#"):
                # No frontmatter fence and we hit a heading → no leading marker.
                break
            m = _REQUIRES_HOST_RE.match(line)
            if m:
                result |= _coerce_capability_ids(m.group(1))
    return result


def unknown_capability_ids(required: set[str]) -> set[str]:
    """Return the subset of ``required`` ids NOT in the closed registry.

    Pure helper — the fail-fast input for Phase 4 (an unregistered id is a loud,
    immediate validation failure, never a silent defer-forever). Empty set ⇒
    every required id is registered.
    """
    return set(required) - set(_HOST_CAPABILITY_REGISTRY)


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phase 3
#   Host-present-set resolver + per-run probe cache + production bindings.
#
# Composes the Phase-2 primitives into ONE resolver returning the host's
# present-capability set, bound to the closed registry, hermetic via injection
# (real production bindings used only when probes is None). The result is cached
# in the per-repo keyed state dir keyed to the run-marker identity: cache for the
# run, re-probe on a new run marker (the cheapest correct option). No marker ⇒
# probe fresh (no cache). Phase-5's match diffs each candidate's requires_host
# set against this present set.
# ---------------------------------------------------------------------------

_HOST_PROBE_CACHE_FILENAME = "lazy-host-capability-cache.json"

# AlgoBooth-specific probe configuration — kept config-overridable here, NOT
# hard-coded into the resolver flow (so a non-AlgoBooth repo can override the
# binary argv / env var names without touching the resolver). Each entry names
# the probe primitive + its argument for the production binding below.
_HOST_CAPABILITY_PROBE_CONFIG: dict[str, dict] = {
    "real-audio-device": {"kind": "env", "var": "ALGOBOOTH_REAL_AUDIO_DEVICE"},
    "zimtohrli-toolchain": {"kind": "binary", "argv": ["zimtohrli", "--version"]},
    # GPU presence on this Windows host: a documented active-invocation probe
    # (nvidia-smi exits 0 iff an NVIDIA GPU + driver are present). A host without
    # the binary reports absent — never a which()/exists() false positive.
    "gpu": {"kind": "binary", "argv": ["nvidia-smi", "-L"]},
    # A motorized/MCU MIDI control surface, probed via an explicit env var
    # (mirrors the real-audio-device env probe). A host with a motorized fader
    # connected sets ALGOBOOTH_REAL_MIDI_DEVICE=1; absent ⇒ defer. An env probe
    # (not live MIDI-port enumeration) is the conservative v1 — a virtual/aggregate
    # MIDI port would false-positive "real hardware present" for the servo-travel
    # assertion, exactly the false-certify the device axis guards against.
    "midi-controller": {"kind": "env", "var": "ALGOBOOTH_REAL_MIDI_DEVICE"},
    # A Linux or macOS host. The OS is deterministically detectable, so this binds
    # a real "platform" probe (predicate "non-windows" → platform.system() != Windows).
    # A Windows host reports absent and defers cfg(unix)-only scenarios cleanly.
    # (link-multi-peer is deliberately ABSENT from this config — no self-probe for a
    # 2nd network peer — so it binds to the constant-False placeholder below.)
    "non-windows-host": {"kind": "platform", "predicate": "non-windows"},
}


def _default_host_probes() -> dict:
    """Build the production ``{capability-id: callable}`` map from the closed
    registry + the (config-overridable) probe config.

    Each callable closes over its config entry and calls the matching Phase-2
    primitive with the real default invoker/environ. An id present in the
    registry but missing a config entry binds to a constant-False probe (it can
    never be present until a probe is configured — fail-safe absent, never a
    crash). Real defaults are bound ONLY here (the resolver passes ``probes=None``
    through to this), mirroring ``ensure_runtime``'s injected-callable contract.
    """
    # Phase-4 WU-4 re-point (was Phase-2's deferred _monolith import): the
    # active-invocation probe primitives moved to lazy_core.runtimeplane with
    # the runtime/spawn plane. Deferred import avoids paying the probe plane's
    # import on the hook-surface path (this module stays _monolith-free).
    from .runtimeplane import (
        probe_binary_capability,
        probe_env_capability,
        probe_platform_capability,
    )

    probes: dict[str, object] = {}
    for cap_id in _HOST_CAPABILITY_REGISTRY:
        cfg = _HOST_CAPABILITY_PROBE_CONFIG.get(cap_id)
        if not cfg:
            probes[cap_id] = (lambda: False)
        elif cfg.get("kind") == "env":
            var = cfg["var"]
            probes[cap_id] = (lambda v=var: probe_env_capability(v))
        elif cfg.get("kind") == "binary":
            argv = cfg["argv"]
            probes[cap_id] = (lambda a=argv: probe_binary_capability(a))
        elif cfg.get("kind") == "platform":
            predicate = cfg["predicate"]
            probes[cap_id] = (lambda p=predicate: probe_platform_capability(p))
        else:
            probes[cap_id] = (lambda: False)
    return probes


def host_present_capabilities(*, probes=None, cache: bool = True) -> set[str]:
    """Resolve the host's present-capability set (host-capability-declaration
    Phase 3).

    For each ``_HOST_CAPABILITY_REGISTRY`` id, evaluates its bound probe callable
    and returns the set of ids whose probe returned truthy. ``probes`` injects a
    ``{capability-id: callable}`` map so ``--test`` stays hermetic; ``None`` binds
    the real production probes (``_default_host_probes``). A registry id with no
    entry in ``probes`` is treated as absent.

    Caching (cache=True, the default): the present-set is cached as JSON under
    ``claude_state_dir()`` keyed to the live run marker's identity (``started_at``).
    A second call within the SAME run hits the cache (no re-probe); a NEW run
    marker (different ``started_at``) re-probes and rewrites the cache. With NO
    run marker present there is no run identity to key on, so the probe runs
    FRESH every call (no cache write/read). The cache read is non-destructive.

    Args:
        probes: injected ``{capability-id: callable() -> bool}`` map; ``None`` ⇒
            real production bindings.
        cache: when True, read/write the per-run cache; when False, always probe
            fresh (used by callers that want a one-shot uncached resolution).

    Returns:
        The set of present capability ids.
    """
    # Deferred imports avoid a top-level circular import: read_run_marker
    # moved to .markers (Phase-5 WU-1); claude_state_dir moved to .statedir
    # in Phase-2 WU-5 (both re-pointed).
    from .markers import read_run_marker
    from .statedir import claude_state_dir

    probe_map = _default_host_probes() if probes is None else probes

    # Resolve the live run identity (the cache key). Read-only marker access —
    # never creates the state dir, never mutates the marker.
    run_id = None
    if cache:
        marker = read_run_marker()
        if isinstance(marker, dict):
            run_id = marker.get("started_at")

    cache_path = None
    if cache and run_id is not None:
        cache_path = claude_state_dir(create=False) / _HOST_PROBE_CACHE_FILENAME
        # Cache hit: same run id ⇒ return the cached present-set without probing.
        try:
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if (
                    isinstance(cached, dict)
                    and cached.get("run_id") == run_id
                    and isinstance(cached.get("present"), list)
                ):
                    return set(cached["present"])
        except (OSError, json.JSONDecodeError, ValueError):
            # Corrupt/unreadable cache ⇒ ignore and re-probe (non-fatal).
            pass

    # Probe fresh: evaluate each registry id's bound callable.
    present: set[str] = set()
    for cap_id in _HOST_CAPABILITY_REGISTRY:
        probe = probe_map.get(cap_id)
        if probe is None:
            continue
        try:
            if probe():
                present.add(cap_id)
        except Exception:  # noqa: BLE001 — a misbehaving probe ⇒ absent
            continue

    # Write the cache only when there is a run identity to key on.
    if cache and run_id is not None and cache_path is not None:
        try:
            payload = {"run_id": run_id, "present": sorted(present)}
            _atomic_write(cache_path, json.dumps(payload, indent=2) + "\n")
        except OSError:
            pass  # cache write best-effort — never fail the resolution

    return present


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phases 4 + 5
#   Shared blocker-body formatter (Phase 4) + DEFERRED_REQUIRES_HOST.md writer
#   (Phase 5). Both live in lazy_core so the bug-pipeline parity mirror in Part 3
#   is a one-line reuse, not a re-implementation (the marker/sentinel infra is
#   shared between lazy-state.py and bug-state.py).
# ---------------------------------------------------------------------------

def utc_now_iso(now: float | None = None) -> str:
    """Return an ISO-8601 UTC timestamp with a trailing ``Z`` (the BLOCKED.md
    ``blocked_at`` format). ``now`` (epoch seconds) is injectable for hermetic
    tests; default is the real wall clock. Timezone-aware (no naive-UTC
    deprecation warning under Python ≥3.12).
    """
    if now is None:
        now = time.time()
    return (
        datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    )


def format_unknown_host_capability_blocker(
    feature_id: str, unknown: set[str] | list[str]
) -> str:
    """Build the human-readable BLOCKED.md body for the Phase-4
    unknown-host-capability fail-fast.

    Names BOTH the offending unregistered id(s) AND the sorted closed-registry
    ids so the operator can either fix the typo or register a new probe — the
    Bazel "No matching toolchains found" / Nix evaluation-failure shape (fail
    fast at parse, never spin on an unfulfillable requirement). Shared so the
    bug-pipeline parity mirror is a one-line reuse.
    """
    unknown_sorted = sorted(set(unknown))
    registry_sorted = sorted(_HOST_CAPABILITY_REGISTRY)
    return (
        "# Blocked — unregistered host capability\n\n"
        "## Details\n\n"
        f"Feature `{feature_id}` declares a `requires_host:` capability id that is "
        f"NOT in the closed host-capability registry: "
        f"{', '.join(f'`{u}`' for u in unknown_sorted)}.\n\n"
        "An unregistered id has no probe and could never be reported present on "
        "ANY host, so deferring it would strand the feature in silent, infinite "
        "queue starvation. This is a loud, immediate validation failure instead.\n\n"
        "## Known (registered) capability ids\n\n"
        f"{', '.join(f'`{r}`' for r in registry_sorted)}\n\n"
        "## Recovery Suggestion\n\n"
        "Either fix the typo in the feature's `requires_host:` set to a known id "
        "above, or register a new probe for the capability in "
        "`lazy_core._HOST_CAPABILITY_REGISTRY` (+ a binding in "
        "`_HOST_CAPABILITY_PROBE_CONFIG`). Then rename/neutralize this BLOCKED.md.\n"
    )


# lazy-core-package-decomposition Phase 5 WU-3 (residue sweep): the host-plane
# sentinel writer write_deferred_requires_host moved here from _monolith.py —
# verbatim (completes the host-capability plane this module owns).

def write_deferred_requires_host(
    path: Path,
    *,
    feature_id: str,
    missing_capabilities: list[str],
    deferred_by: str = "lazy",
    date: str | None = None,
) -> None:
    """Write a capability-keyed ``DEFERRED_REQUIRES_HOST.md`` sentinel
    (host-capability-declaration Phase 5).

    The host-axis generalization of ``DEFERRED_REQUIRES_DEVICE.md``: it records
    that the feature is testable, just NOT on THIS host (≥1 required capability
    absent), so it re-opens on a host that provides the capability rather than
    being permanently waived or back-of-queued. ``missing_capabilities`` is
    LOAD-BEARING and MUST be non-empty — it is the self-limiting scope a
    capability-bearing host re-opens. Atomic write; the body keeps the
    human-readable re-open context.

    Args:
        path: destination ``DEFERRED_REQUIRES_HOST.md`` path.
        feature_id: the deferred feature's id.
        missing_capabilities: the absent required capability ids (non-empty).
        deferred_by: ``lazy`` | ``lazy-batch`` (the writer).
        date: ``YYYY-MM-DD`` (default: today).
    """
    if not missing_capabilities:
        raise ValueError(
            "write_deferred_requires_host: missing_capabilities MUST be non-empty "
            "(it is the self-limiting scope a capability-host re-opens)."
        )
    if date is None:
        date = datetime.date.today().isoformat()
    missing_sorted = sorted(set(missing_capabilities))
    fm = {
        "kind": "deferred-requires-host",
        "feature_id": feature_id,
        "missing_capabilities": missing_sorted,
        "deferred_by": deferred_by,
        "date": date,
    }
    body = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False).strip()
        + "\n---\n\n"
        "# Deferred — requires host capability\n\n"
        "## What was deferred and why\n\n"
        f"Feature `{feature_id}`'s runtime validation requires host "
        f"capability/ies {', '.join(f'`{m}`' for m in missing_sorted)}, which "
        "is absent on this host. The feature is testable — just not HERE — so it "
        "is deferred (not skipped/waived) and re-opens automatically on a host "
        "that provides the capability.\n\n"
        "## How to resume\n\n"
        "Run `/lazy` (or `/lazy-batch`) on a host that provides the missing "
        "capability/ies above. The capability-match re-opens this feature into "
        "runtime validation and deletes this sentinel on success.\n"
    )
    _atomic_write(path, body)
