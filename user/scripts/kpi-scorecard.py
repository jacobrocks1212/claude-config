#!/usr/bin/env python3
"""kpi-scorecard.py — friction KPI registry lint + pure-read scorecard renderer.

friction-kpi-registry: every friction-reduction system declares its canonical KPIs
(signal source, direction-of-goodness, baseline + provenance, regression band,
review cadence) in the committed registry `docs/kpi/registry.json`. This script is
the registry's deterministic tooling — a stdlib-only sibling of `lazy-queue-doc.py`:

  - default:            render + write `<repo>/docs/kpi/SCORECARD.md`
  - `--stdout`:          render without writing
  - `--lint`:            registry schema / enum / band / rot validation
  - `--lint --spec <p>`: validate a SPEC.md's friction-KPI declaration (the
                         deterministic backstop the `/spec`-injected
                         `spec-friction-kpi-gate.md` component shells)
  - `--capture-baseline <kpi-id>`: the ONLY computed-field registry writer —
                         stamps the row's baseline from the current window
                         (`provenance: measured`) via `lazy_core._atomic_write`;
                         REFUSES when the signal has no data (a baseline is never
                         fabricated).

Rendering discipline (mobile-queue-control precedent): a PURE function of
(registry, signal readings, today) — NO embedded wall-clock, fixed rounding,
single trailing newline — so an unchanged-state regen is byte-identical and adds
nothing to the pipeline commit it rides. Honesty ladder (D4-A + D8-A): an
unavailable/unrecordable signal renders NO-DATA (with a note), never a zero; a
`pending` baseline / null band renders PENDING-BASELINE; only a measured value
against a declared band renders OK / WARN / BREACH (honoring `direction`).

Computation is REUSED, never re-implemented: telemetry math comes from
`pipeline_visualizer.trends` (`load_events`, `halt_dwell`, `cycles_per_completion`)
and ledger reads from `lazy_core` — one computation, two renderers. This script
never re-infers pipeline state and never mutates anything except its own
SCORECARD.md and the explicit `--capture-baseline` registry write.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Optional, Tuple

# Import sibling modules (lazy_core, pipeline_visualizer) — same
# _SCRIPTS_DIR-on-sys.path pattern as lazy-queue-doc.py.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Closed enums (D2-B) — an unknown value is a lint ERROR, never silent no-data.
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WINDOW_RE = re.compile(r"^(\d+)d$")

_SOURCES: dict[str, frozenset] = {
    "telemetry-ledger": frozenset({
        "containment-refusal-count",
        "halt-dwell-p50-seconds",
        "cycles-per-completion",
        # harness-change-canary-rollback: registered at spec-finalization so the
        # feature's drafted `## KPI Declaration` row lints clean. Compute is
        # wired in the feature's Phase 4 (until then _sel_telemetry returns an
        # honest NO-DATA for this selector — never a fabricated zero).
        "canary-trip-precision",
    }),
    "deny-ledger": frozenset({
        "build-queue-enforce-deny-count",
        "guard-deny-count",
        "process-friction-count",
    }),
    "build-queue-results": frozenset({
        "false-green-rate",
        "queue-wait-p50-seconds",
    }),
    "sentinel-scan": frozenset({
        "open-halt-count",
    }),
}

_DIRECTIONS = frozenset({"down-is-good", "up-is-good"})
_PROVENANCES = frozenset({"measured", "retro-derived", "pending"})

_REQUIRED_FIELDS = (
    "id", "system", "title", "friction", "signal", "unit", "direction",
    "baseline", "band", "review_by",
)

# Statuses (D4-A). Order here is only cosmetic.
_STATUS_NO_DATA = "NO-DATA"
_STATUS_PENDING = "PENDING-BASELINE"
_STATUS_OK = "OK"
_STATUS_WARN = "WARN"
_STATUS_BREACH = "BREACH"

_DIRECTION_GLYPH = {"down-is-good": "▼", "up-is-good": "▲"}  # ▼ ▲

# build-queue state is MACHINE-global (~/.claude/state/build-queue), not
# per-repo keyed. Env override for hermetic tests only.
_BUILD_QUEUE_DIR_ENV = "KPI_BUILD_QUEUE_DIR"

# hygiene.build_fidelity values that mean "the build lied about being green".
_FALSE_GREEN_FIDELITIES = frozenset({"log-failure-override", "no-output"})

# reason_head signature marking a build-queue-enforce hook deny in the deny
# ledger (the hook-side append itself is a workstation-deferred follow-up —
# see the registry row's notes; until it lands the ledger simply has no
# matching entries and windowed counts read over whatever IS recorded).
_BUILD_QUEUE_DENY_SIGNATURE = "build-queue"

# D6-B advisory keyword scan (non-blocking cross-check in --lint --spec).
_FRICTION_KEYWORDS = (
    "friction", "wasted cycles", "wasted tokens", "retry", "efficiency",
    "rework", "toil",
)


# ---------------------------------------------------------------------------
# Registry load + lint (Phase 1)
# ---------------------------------------------------------------------------

def registry_path(repo_root) -> Path:
    return Path(repo_root) / "docs" / "kpi" / "registry.json"


def load_registry(path) -> dict:
    """Load the registry JSON. Raises on missing/unparseable — the CLI turns
    that into a named exit-1 (the registry is a committed contract; a broken
    one must be loud, never silently empty)."""
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _lint_band(row_id: str, band, direction: str, provenance: str,
               errors: list) -> None:
    if band is None:
        return
    if provenance == "pending":
        errors.append(
            f"{row_id}: band must be null while baseline provenance is "
            f"'pending' (declare the band when the baseline exists)")
        return
    if not isinstance(band, dict) or set(band.keys()) != {"warn", "breach"}:
        errors.append(f"{row_id}: band must be null or {{warn, breach}}")
        return
    warn, breach = band.get("warn"), band.get("breach")
    if not isinstance(warn, (int, float)) or not isinstance(breach, (int, float)):
        errors.append(f"{row_id}: band warn/breach must be numbers")
        return
    if direction == "down-is-good" and warn > breach:
        errors.append(
            f"{row_id}: band inverted for down-is-good (warn {warn} > "
            f"breach {breach})")
    if direction == "up-is-good" and warn < breach:
        errors.append(
            f"{row_id}: band inverted for up-is-good (warn {warn} < "
            f"breach {breach})")


def _lint_baseline(row_id: str, baseline, errors: list) -> Optional[str]:
    """Validate a baseline dict; returns its provenance (or None on error)."""
    if not isinstance(baseline, dict):
        errors.append(f"{row_id}: baseline must be an object")
        return None
    provenance = baseline.get("provenance")
    if provenance not in _PROVENANCES:
        errors.append(
            f"{row_id}: baseline provenance {provenance!r} not in "
            f"{sorted(_PROVENANCES)}")
        return None
    window = baseline.get("window")
    if not isinstance(window, str) or not _WINDOW_RE.match(window):
        errors.append(
            f"{row_id}: baseline window {window!r} must match '<N>d' "
            f"(e.g. '30d')")
    value = baseline.get("value")
    captured_at = baseline.get("captured_at")
    if provenance == "pending":
        if value is not None:
            errors.append(
                f"{row_id}: baseline value must be null while provenance is "
                f"'pending' (never a fabricated number)")
    else:
        if not isinstance(value, (int, float)):
            errors.append(
                f"{row_id}: baseline with provenance '{provenance}' requires "
                f"a numeric value")
        if not isinstance(captured_at, str) or not _DATE_RE.match(captured_at):
            errors.append(
                f"{row_id}: baseline with provenance '{provenance}' requires "
                f"captured_at (YYYY-MM-DD)")
    return provenance


def lint_row(row, errors: list, warnings: list, today: datetime.date) -> None:
    """Row-level lint (shared by --lint and the --spec draft validator)."""
    row_id = row.get("id") if isinstance(row, dict) else None
    label = row_id if isinstance(row_id, str) and row_id else "<row without id>"
    if not isinstance(row, dict):
        errors.append(f"{label}: row must be an object")
        return
    if not isinstance(row_id, str) or not _ID_RE.match(row_id or ""):
        errors.append(f"{label}: id {row_id!r} must match ^[a-z0-9][a-z0-9-]*$")
    for field in _REQUIRED_FIELDS:
        if field not in row:
            errors.append(f"{label}: missing required field '{field}'")
    for field in ("system", "title", "friction", "unit"):
        v = row.get(field)
        if field in row and (not isinstance(v, str) or not v.strip()):
            errors.append(f"{label}: {field} must be a non-empty string")
    signal = row.get("signal")
    if "signal" in row:
        if not isinstance(signal, dict):
            errors.append(f"{label}: signal must be {{source, selector}}")
        else:
            source = signal.get("source")
            selector = signal.get("selector")
            if source not in _SOURCES:
                errors.append(
                    f"{label}: signal source {source!r} not in closed enum "
                    f"{sorted(_SOURCES)}")
            elif selector not in _SOURCES[source]:
                errors.append(
                    f"{label}: signal selector {selector!r} not a registered "
                    f"'{source}' selector {sorted(_SOURCES[source])}")
    direction = row.get("direction")
    if "direction" in row and direction not in _DIRECTIONS:
        errors.append(
            f"{label}: direction {direction!r} not in {sorted(_DIRECTIONS)}")
    provenance = None
    if "baseline" in row:
        provenance = _lint_baseline(label, row.get("baseline"), errors)
    if "band" in row and direction in _DIRECTIONS and provenance is not None:
        _lint_band(label, row.get("band"), direction, provenance, errors)
    review_by = row.get("review_by")
    if "review_by" in row:
        if not isinstance(review_by, str) or not _DATE_RE.match(review_by):
            errors.append(
                f"{label}: review_by {review_by!r} must be YYYY-MM-DD")
        else:
            try:
                due = datetime.date.fromisoformat(review_by)
                if due < today:
                    warnings.append(
                        f"{label}: past review_by {review_by} — re-confirm "
                        f"this row is still alive (registry rot)")
            except ValueError:
                errors.append(f"{label}: review_by {review_by!r} not a real date")
    for field in ("repo_scope", "notes"):
        if field in row and not isinstance(row.get(field), str):
            errors.append(f"{label}: {field} must be a string when present")


def lint_registry(registry, today: datetime.date) -> Tuple[list, list]:
    """Full-registry lint → (errors, warnings). Deterministic; no I/O."""
    errors: list = []
    warnings: list = []
    if not isinstance(registry, dict):
        return (["registry: top level must be an object"], warnings)
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"registry: schema_version {registry.get('schema_version')!r} != "
            f"{SCHEMA_VERSION}")
    kpis = registry.get("kpis")
    if not isinstance(kpis, list):
        errors.append("registry: 'kpis' must be a list")
        return (errors, warnings)
    seen: set = set()
    for row in kpis:
        lint_row(row, errors, warnings, today)
        rid = row.get("id") if isinstance(row, dict) else None
        if isinstance(rid, str):
            if rid in seen:
                errors.append(f"{rid}: duplicate id (ids must be unique)")
            seen.add(rid)
    return (errors, warnings)


# ---------------------------------------------------------------------------
# Signal layer (Phases 2–3) — every selector returns (value | None, note | None).
# A None value is an HONEST no-data verdict (absent source, unrecordable
# signal, empty window for a statistic) — never a fabricated zero. A real zero
# is only returned when the source is present and genuinely counts to zero.
# ---------------------------------------------------------------------------

def _window_seconds(row) -> float:
    m = _WINDOW_RE.match(((row.get("baseline") or {}).get("window")) or "")
    days = int(m.group(1)) if m else 30
    return days * 86400.0


def _parse_ts(value) -> Optional[float]:
    """Parse an epoch number or ISO-8601 string (incl. .NET 'o' 7-digit
    fractions and trailing Z) to an epoch float. None if unparseable."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return None
    s = value.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    # Trim >6 fractional digits (the .NET round-trip format emits 7).
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.timestamp()


def _abbrev_home(text: str) -> str:
    return text.replace(str(Path.home()), "~")


# -- build-queue-results ------------------------------------------------------

def _build_queue_dir() -> Path:
    override = os.environ.get(_BUILD_QUEUE_DIR_ENV)
    if override:
        return Path(override)
    return Path.home() / ".claude" / "state" / "build-queue"


def _read_build_queue_records() -> Tuple[Optional[list], Optional[str]]:
    results = _build_queue_dir() / "results"
    if not results.is_dir():
        return (None, f"build-queue results dir absent "
                      f"({_abbrev_home(str(results))}) — no build-queue state "
                      f"on this machine")
    records = []
    for p in sorted(results.glob("*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue  # a torn/partial result never bricks the scan
        if isinstance(obj, dict):
            records.append(obj)
    return (records, None)


def _bq_windowed(records: list, cutoff: float) -> list:
    out = []
    for rec in records:
        ts = _parse_ts(rec.get("ended_at"))
        if ts is not None and ts >= cutoff:
            out.append(rec)
    return out


def _sel_false_green_rate(records: list) -> Tuple[Optional[float], Optional[str]]:
    fidelities = []
    for rec in records:
        fid = (rec.get("hygiene") or {}).get("build_fidelity")
        if isinstance(fid, str) and fid != "n/a":
            fidelities.append(fid)
    if not fidelities:
        return (None, "no build records carrying hygiene.build_fidelity in "
                      "the window")
    flagged = sum(1 for f in fidelities if f in _FALSE_GREEN_FIDELITIES)
    return (round(100.0 * flagged / len(fidelities), 2), None)


def _sel_queue_wait_p50(records: list) -> Tuple[Optional[float], Optional[str]]:
    waits = []
    for rec in records:
        queued = _parse_ts(rec.get("queued_at"))
        started = _parse_ts(rec.get("started_at"))
        if queued is not None and started is not None and started >= queued:
            waits.append(started - queued)
    if not waits:
        return (None, "results records carry no queued_at/started_at pair — "
                      "runner timestamp add is a workstation-deferred "
                      "follow-up")
    return (round(statistics.median(waits), 2), None)


# -- deny-ledger ---------------------------------------------------------------

def _bind_lazy_core(repo_root):
    """Import lazy_core bound to the target repo (trends._bind_lazy_core
    pattern). LAZY_STATE_DIR, when set, wins inside lazy_core regardless."""
    import lazy_core
    try:
        if repo_root is not None:
            lazy_core.set_active_repo_root(str(repo_root))
    except Exception:  # noqa: BLE001 — binding failure degrades to cwd fallback
        pass
    return lazy_core


def _read_deny_entries(repo_root) -> Tuple[Optional[list], Optional[str]]:
    lazy_core = _bind_lazy_core(repo_root)
    ledger = (lazy_core.claude_state_dir(create=False)
              / lazy_core._DENY_LEDGER_FILENAME)
    if not ledger.exists():
        return (None, "deny ledger absent — no denies recorded for this repo")
    return (lazy_core.read_deny_ledger(), None)


def _deny_windowed(entries: list, cutoff: float) -> list:
    return [e for e in entries
            if isinstance(e.get("ts"), (int, float)) and e["ts"] >= cutoff]


def _sel_deny_count(entries: list, kind: str) -> Tuple[Optional[float], Optional[str]]:
    if kind == "build-queue-enforce-deny-count":
        n = sum(1 for e in entries
                if _BUILD_QUEUE_DENY_SIGNATURE
                in str(e.get("reason_head", "")).lower())
    elif kind == "process-friction-count":
        n = sum(1 for e in entries if e.get("kind") == "process-friction")
    else:  # guard-deny-count — plain guard denies (not friction/readmit)
        n = sum(1 for e in entries
                if e.get("kind") != "process-friction"
                and not e.get("auto_readmit"))
    return (float(n), None)


# -- telemetry-ledger ----------------------------------------------------------

def _telemetry_available(repo_root) -> bool:
    """True iff any ledger segment (state dir) or committed cloud segment
    exists — distinguishes 'no ledger at all' (NO-DATA) from 'ledger present,
    zero matching events' (a real zero)."""
    lazy_core = _bind_lazy_core(repo_root)
    base = lazy_core.claude_state_dir(create=False)
    active = base / lazy_core._TELEMETRY_LEDGER_FILENAME
    if active.exists():
        return True
    for i in range(1, lazy_core._TELEMETRY_ROTATED_SEGMENTS + 1):
        if Path(f"{active}.{i}").exists():
            return True
    cloud_dir = Path(repo_root) / "docs" / "telemetry" / "cloud"
    try:
        return cloud_dir.is_dir() and any(cloud_dir.glob("*.jsonl"))
    except OSError:
        return False


def _load_trends():
    from pipeline_visualizer import trends
    return trends


def _sel_telemetry(repo_root, selector: str,
                   cutoff: float) -> Tuple[Optional[float], Optional[str]]:
    if not _telemetry_available(repo_root):
        return (None, "telemetry ledger absent — no run has emitted events "
                      "for this repo yet")
    trends = _load_trends()
    events = trends.load_events(repo_root)
    windowed = [e for e in events
                if isinstance(e.get("ts"), (int, float)) and e["ts"] >= cutoff]
    if selector == "containment-refusal-count":
        n = sum(1 for e in windowed
                if e.get("event") == "containment-refusal")
        return (float(n), None)
    if selector == "halt-dwell-p50-seconds":
        dwells = [r["dwell_seconds"] for r in trends.halt_dwell(events)
                  if r.get("dwell_seconds") is not None
                  and isinstance(r.get("halt_ts"), (int, float))
                  and r["halt_ts"] >= cutoff]
        if not dwells:
            return (None, "no resolved halts in the window (open halts are "
                          "honest unknowns, never counted as zero)")
        return (round(statistics.median(dwells), 2), None)
    if selector == "cycles-per-completion":
        cpc = trends.cycles_per_completion(windowed)
        if cpc["cycles_per_completion"] is None:
            return (None, "no completions in the window — a ratio is never "
                          "fabricated")
        return (float(cpc["cycles_per_completion"]), None)
    return (None, f"unknown telemetry selector {selector!r}")


# -- sentinel-scan ---------------------------------------------------------------

_OPEN_SENTINELS = frozenset({"BLOCKED.md", "NEEDS_INPUT.md"})


def _sel_open_halt_count(repo_root) -> Tuple[Optional[float], Optional[str]]:
    roots = [Path(repo_root) / "docs" / "features",
             Path(repo_root) / "docs" / "bugs"]
    present = [r for r in roots if r.is_dir()]
    if not present:
        return (None, "docs/features + docs/bugs trees absent — nothing to "
                      "scan")
    n = 0
    for root in present:
        for name in _OPEN_SENTINELS:
            n += sum(1 for _ in root.rglob(name))
    return (float(n), None)


# -- dispatcher -------------------------------------------------------------------

def compute_reading(row, *, repo_root,
                    now: float) -> Tuple[Optional[float], Optional[str]]:
    """Compute one row's current windowed value → (value, note).

    Pure-read; failure-tolerant (an exception is an honest NO-DATA with the
    error as the note, never a crash of the whole render)."""
    signal = row.get("signal") or {}
    source = signal.get("source")
    selector = signal.get("selector")
    cutoff = now - _window_seconds(row)
    try:
        if source == "build-queue-results":
            records, note = _read_build_queue_records()
            if records is None:
                return (None, note)
            windowed = _bq_windowed(records, cutoff)
            if selector == "false-green-rate":
                return _sel_false_green_rate(windowed)
            if selector == "queue-wait-p50-seconds":
                return _sel_queue_wait_p50(windowed)
        elif source == "deny-ledger":
            entries, note = _read_deny_entries(repo_root)
            if entries is None:
                return (None, note)
            return _sel_deny_count(_deny_windowed(entries, cutoff), selector)
        elif source == "telemetry-ledger":
            return _sel_telemetry(repo_root, selector, cutoff)
        elif source == "sentinel-scan":
            if selector == "open-halt-count":
                return _sel_open_halt_count(repo_root)
        return (None, f"no computation registered for "
                      f"{source!r}/{selector!r}")
    except Exception as exc:  # noqa: BLE001 — honest NO-DATA, never a crash
        return (None, f"signal read failed: {exc}")


def compute_readings(registry, *, repo_root, now: float) -> dict:
    """{row id → (value, note)} for every registry row."""
    readings: dict = {}
    for row in registry.get("kpis", []):
        rid = row.get("id")
        if isinstance(rid, str):
            readings[rid] = compute_reading(row, repo_root=repo_root, now=now)
    return readings


# ---------------------------------------------------------------------------
# Status engine (D4-A) + renderer (Phase 2)
# ---------------------------------------------------------------------------

def row_status(row, value) -> str:
    """The D4-A honesty ladder: NO-DATA → PENDING-BASELINE → band comparison."""
    if value is None:
        return _STATUS_NO_DATA
    baseline = row.get("baseline") or {}
    band = row.get("band")
    if baseline.get("provenance") == "pending" or band is None:
        return _STATUS_PENDING
    warn, breach = band.get("warn"), band.get("breach")
    if row.get("direction") == "up-is-good":
        if value <= breach:
            return _STATUS_BREACH
        if value <= warn:
            return _STATUS_WARN
        return _STATUS_OK
    if value >= breach:
        return _STATUS_BREACH
    if value >= warn:
        return _STATUS_WARN
    return _STATUS_OK


def _fmt_num(value) -> str:
    v = round(float(value), 2)
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


def _fmt_measure(value, unit: str) -> str:
    n = _fmt_num(value)
    if unit == "percent":
        return f"{n}%"
    if unit == "seconds":
        return f"{n}s"
    if isinstance(unit, str) and unit.startswith("count/"):
        return f"{n}/{unit.split('/', 1)[1]}"
    return n


def _baseline_cell(row) -> str:
    baseline = row.get("baseline") or {}
    if baseline.get("provenance") == "pending" or baseline.get("value") is None:
        return "pending"
    return (f"{_fmt_measure(baseline['value'], row.get('unit', ''))} "
            f"({baseline.get('provenance')} {baseline.get('captured_at')})")


def _band_cell(row) -> str:
    band = row.get("band")
    if not isinstance(band, dict):
        return "—"
    return f"{_fmt_num(band['warn'])} / {_fmt_num(band['breach'])}"


def render_scorecard(registry, readings: dict, *, today: datetime.date) -> str:
    """Render the full SCORECARD.md — a PURE function of (registry, readings,
    today). No wall-clock embed; unchanged inputs → byte-identical output."""
    lines = [
        "# Friction KPI Scorecard",
        "",
        "> Pure-read render of `docs/kpi/registry.json` by "
        "`user/scripts/kpi-scorecard.py` — script-computed values only, "
        "no embedded wall-clock (freshness is this file's git commit "
        "time). An absent/unrecordable signal renders NO-DATA, never a "
        "fabricated zero; a `pending` baseline renders PENDING-BASELINE.",
        "",
    ]
    kpis = [r for r in registry.get("kpis", []) if isinstance(r, dict)]
    # Group by system, in first-seen registry order.
    systems: list = []
    by_system: dict = {}
    for row in kpis:
        system = row.get("system") or "unknown"
        if system not in by_system:
            by_system[system] = []
            systems.append(system)
        by_system[system].append(row)

    regressions: list = []
    notes: list = []
    for system in systems:
        lines.append(f"## {system}")
        lines.append("")
        lines.append("| KPI | current | baseline | band (warn/breach) | status |")
        lines.append("|-----|---------|----------|--------------------|--------|")
        for row in by_system[system]:
            rid = row.get("id")
            value, note = readings.get(rid, (None, "no reading computed"))
            status = row_status(row, value)
            window = (row.get("baseline") or {}).get("window", "")
            if value is None:
                current = "—"
            else:
                current = _fmt_measure(value, row.get("unit", ""))
                if window and not str(row.get("unit", "")).startswith("count/"):
                    current = f"{current} ({window})"
            glyph = _DIRECTION_GLYPH.get(row.get("direction"), "")
            status_cell = (f"{status} {glyph}"
                           if status in (_STATUS_OK, _STATUS_WARN,
                                         _STATUS_BREACH) and glyph
                           else status)
            scope = f" `[{row['repo_scope']}]`" if row.get("repo_scope") else ""
            lines.append(
                f"| {row.get('title', rid)}{scope} | {current} | "
                f"{_baseline_cell(row)} | {_band_cell(row)} | {status_cell} |")
            if status in (_STATUS_WARN, _STATUS_BREACH):
                band = row.get("band") or {}
                threshold = (band.get("breach") if status == _STATUS_BREACH
                             else band.get("warn"))
                regressions.append(
                    f"- ⚠ {system}/{rid} {status}: {current} vs "
                    f"{'breach' if status == _STATUS_BREACH else 'warn'} "
                    f"{_fmt_num(threshold)} (baseline {_baseline_cell(row)})")
            if note:
                notes.append(f"- `{rid}`: {_abbrev_home(note)}")
        lines.append("")

    lines.append("## Regressions")
    lines.append("")
    lines.extend(regressions if regressions else ["- (none)"])
    lines.append("")

    lines.append("## Registry health")
    lines.append("")
    health: list = []
    for row in kpis:
        review_by = row.get("review_by")
        if isinstance(review_by, str) and _DATE_RE.match(review_by):
            try:
                if datetime.date.fromisoformat(review_by) < today:
                    health.append(f"- ⚠ {row.get('id')} past review_by "
                                  f"{review_by}")
            except ValueError:
                pass
    lines.extend(health if health else ["- (none)"])

    if notes:
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        lines.extend(notes)

    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_render(repo_root: Path, *, stdout: bool, today: datetime.date,
                now: Optional[float] = None) -> int:
    import time
    path = registry_path(repo_root)
    try:
        registry = load_registry(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"kpi-scorecard: cannot read registry {path}: {exc}",
              file=sys.stderr)
        return 1
    readings = compute_readings(registry, repo_root=repo_root,
                                now=now if now is not None else time.time())
    doc = render_scorecard(registry, readings, today=today)
    if stdout:
        sys.stdout.write(doc)
        return 0
    out_path = Path(repo_root) / "docs" / "kpi" / "SCORECARD.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def _cmd_lint(repo_root: Path, today: datetime.date) -> int:
    path = registry_path(repo_root)
    try:
        registry = load_registry(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"kpi-scorecard --lint: cannot read registry {path}: {exc}")
        return 1
    errors, warnings = lint_registry(registry, today=today)
    for e in errors:
        print(f"ERROR   {e}")
    for w in warnings:
        print(f"WARNING {w}")
    if errors:
        print(f"kpi-scorecard --lint: {len(errors)} error(s), "
              f"{len(warnings)} warning(s)")
        return 1
    print(f"kpi-scorecard --lint: OK ({len(warnings)} warning(s))")
    return 0


# ---------------------------------------------------------------------------
# `/spec` measurability gate validator (Phase 4, D6/D7) — the deterministic
# backstop the injected `spec-friction-kpi-gate.md` component shells.
# ---------------------------------------------------------------------------

_CLASSIFICATION_RE = re.compile(
    r"^\*\*Friction-reduction feature:\*\*\s*(yes|no)\b",
    re.IGNORECASE | re.MULTILINE)


def parse_spec_classification(spec_text: str) -> Optional[str]:
    """Return 'yes' | 'no' from the mandatory classification line, or None
    when the line is absent (a missing declaration is itself the gate miss)."""
    m = _CLASSIFICATION_RE.search(spec_text or "")
    return m.group(1).lower() if m else None


def _spec_friction_keywords(spec_text: str) -> list:
    # Scan the SPEC body EXCLUDING the classification line itself — the line
    # "**Friction-reduction feature:** no" contains "friction" by construction
    # and must not self-trigger the advisory cross-check.
    body = _CLASSIFICATION_RE.sub("", spec_text or "")
    low = body.lower()
    return [k for k in _FRICTION_KEYWORDS if k in low]


def _extract_declaration_section(spec_text: str) -> Tuple[str, bool]:
    """Return (section_body, present) for the `## KPI Declaration` section —
    everything up to the next `## ` header or EOF."""
    out: list = []
    inside = False
    for line in (spec_text or "").splitlines():
        if re.match(r"^##\s+KPI Declaration\s*$", line):
            inside = True
            continue
        if inside and re.match(r"^##\s+\S", line):
            break
        if inside:
            out.append(line)
    return ("\n".join(out), inside)


def _parse_declaration(section_text: str) -> Tuple[list, list, list]:
    """Parse the declaration body → (referenced_ids, draft_rows, json_errors).

    Referenced rows are `- kpi: <id>` lines; drafted rows are fenced ```json
    blocks (each a full-schema row)."""
    ids: list = []
    for line in section_text.splitlines():
        m = re.match(r"^\s*-\s*kpi:\s*(\S+)\s*$", line)
        if m:
            ids.append(m.group(1))
    drafts: list = []
    json_errors: list = []
    for block in re.findall(r"```json\s*\n(.*?)```", section_text,
                            re.DOTALL):
        try:
            drafts.append(json.loads(block))
        except (json.JSONDecodeError, ValueError) as exc:
            json_errors.append(str(exc))
    return (ids, drafts, json_errors)


def lint_spec(spec_text: str, registry, today: datetime.date) -> Tuple[list, list]:
    """Validate a SPEC's friction-KPI declaration → (errors, warnings).

    Pure; no I/O. Contract (D6/D7):
      - missing classification line → error.
      - `no` → clean; `no` + friction vocabulary → advisory warning (non-blocking).
      - `yes` → a `## KPI Declaration` section is REQUIRED; every `- kpi: <id>`
        must resolve to the registry and every fenced-json draft row must pass
        row-level lint.
    """
    errors: list = []
    warnings: list = []
    classification = parse_spec_classification(spec_text)
    if classification is None:
        errors.append(
            "SPEC missing the mandatory '**Friction-reduction feature:** "
            "yes|no' classification line (the measurability gate cannot "
            "classify this feature)")
        return (errors, warnings)
    keywords = _spec_friction_keywords(spec_text)
    if classification == "no":
        if keywords:
            warnings.append(
                f"SPEC declares '**Friction-reduction feature:** no' but "
                f"carries friction vocabulary {keywords} — confirm this is "
                f"not a friction-reduction feature (advisory, non-blocking; "
                f"D6-B keyword cross-check)")
        return (errors, warnings)
    # classification == "yes" — a KPI Declaration is required.
    section, present = _extract_declaration_section(spec_text)
    if not present:
        errors.append(
            "friction-reduction feature ('yes') requires a '## KPI "
            "Declaration' section — name existing registry row ids "
            "('- kpi: <id>') and/or draft new fully-schema'd rows (fenced "
            "json) before finalizing")
        return (errors, warnings)
    ids, drafts, json_errors = _parse_declaration(section)
    for je in json_errors:
        errors.append(f"KPI Declaration: malformed JSON draft row ({je})")
    if not ids and not drafts and not json_errors:
        errors.append(
            "KPI Declaration section is empty — name at least one registry "
            "row id ('- kpi: <id>') or draft a new row (fenced json)")
    known = {r.get("id") for r in registry.get("kpis", [])
             if isinstance(r, dict)}
    for rid in ids:
        if rid not in known:
            errors.append(
                f"KPI Declaration: referenced kpi id '{rid}' does not resolve "
                f"to the registry (add the row or fix the id)")
    for draft in drafts:
        d_errors: list = []
        d_warnings: list = []
        lint_row(draft, d_errors, d_warnings, today)
        for e in d_errors:
            errors.append(f"KPI Declaration draft row: {e}")
    return (errors, warnings)


def _cmd_lint_spec(repo_root: Path, spec_path: Path,
                   registry_arg: Optional[Path], today: datetime.date) -> int:
    try:
        spec_text = Path(spec_path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"kpi-scorecard --lint --spec: cannot read spec {spec_path}: "
              f"{exc}")
        return 1
    reg_path = registry_arg if registry_arg else registry_path(repo_root)
    try:
        registry = load_registry(reg_path)
    except (OSError, json.JSONDecodeError, ValueError):
        registry = {"schema_version": SCHEMA_VERSION, "kpis": []}
    errors, warnings = lint_spec(spec_text, registry, today=today)
    for e in errors:
        print(f"ERROR   {e}")
    for w in warnings:
        print(f"WARNING {w}")
    if errors:
        print(f"kpi-scorecard --lint --spec: {len(errors)} error(s), "
              f"{len(warnings)} warning(s)")
        return 1
    print(f"kpi-scorecard --lint --spec: OK ({len(warnings)} warning(s))")
    return 0


# ---------------------------------------------------------------------------
# `--capture-baseline` (Phase 4, D3) — the ONLY computed-field registry writer.
# ---------------------------------------------------------------------------

def _cmd_capture_baseline(repo_root: Path, kpi_id: str,
                          today: datetime.date) -> int:
    import time
    path = registry_path(repo_root)
    try:
        registry = load_registry(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"kpi-scorecard --capture-baseline: cannot read registry "
              f"{path}: {exc}")
        return 1
    row = next((r for r in registry.get("kpis", [])
                if isinstance(r, dict) and r.get("id") == kpi_id), None)
    if row is None:
        print(f"kpi-scorecard --capture-baseline: no KPI row with id "
              f"{kpi_id!r} in {path}")
        return 1
    value, note = compute_reading(row, repo_root=repo_root, now=time.time())
    if value is None:
        print(f"kpi-scorecard --capture-baseline: REFUSED — {kpi_id} has no "
              f"data to measure ({_abbrev_home(note or 'no reading')}); a "
              f"baseline is never fabricated. Capture it on a host where the "
              f"signal exists.")
        return 1
    window = (row.get("baseline") or {}).get("window") or "30d"
    row["baseline"] = {
        "value": value,
        "captured_at": today.isoformat(),
        "window": window,
        "provenance": "measured",
    }
    # Re-lint the mutated registry BEFORE writing — never persist a row the
    # linter would reject.
    errors, _ = lint_registry(registry, today=today)
    if errors:
        print("kpi-scorecard --capture-baseline: ABORTED — the captured "
              "baseline would make the registry lint-dirty:")
        for e in errors:
            print(f"ERROR   {e}")
        return 1
    lazy_core = _bind_lazy_core(repo_root)
    lazy_core._atomic_write(
        path, json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    print(f"kpi-scorecard --capture-baseline: {kpi_id} baseline = "
          f"{_fmt_measure(value, row.get('unit', ''))} "
          f"(measured {today.isoformat()}, window {window})")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="kpi-scorecard",
        description="Friction KPI registry lint + pure-read scorecard renderer "
                    "(friction-kpi-registry).",
    )
    parser.add_argument("--repo-root", default=os.getcwd(),
                        help="Repo whose docs/kpi/registry.json to use "
                             "(default: cwd).")
    parser.add_argument("--stdout", action="store_true",
                        help="Print the scorecard instead of writing "
                             "docs/kpi/SCORECARD.md.")
    parser.add_argument("--lint", action="store_true",
                        help="Validate the registry (schema, enums, bands, "
                             "review_by rot). With --spec, validate a SPEC's "
                             "friction-KPI declaration instead.")
    parser.add_argument("--spec", default=None,
                        help="Path to a SPEC.md whose friction-KPI declaration "
                             "to validate (requires --lint).")
    parser.add_argument("--registry", default=None,
                        help="Explicit registry path for --lint --spec id "
                             "resolution (default: <repo-root>/docs/kpi/"
                             "registry.json).")
    parser.add_argument("--capture-baseline", default=None, metavar="KPI_ID",
                        help="Stamp the row's baseline from the current window "
                             "(provenance: measured). Refuses when the signal "
                             "has no data.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    today = datetime.date.today()

    if args.capture_baseline:
        return _cmd_capture_baseline(repo_root, args.capture_baseline, today)
    if args.lint and args.spec:
        return _cmd_lint_spec(repo_root, Path(args.spec),
                              Path(args.registry) if args.registry else None,
                              today)
    if args.lint:
        return _cmd_lint(repo_root, today)
    return _cmd_render(repo_root, stdout=args.stdout, today=today)


if __name__ == "__main__":
    sys.exit(main())
