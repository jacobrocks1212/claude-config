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
    # Offline session-log corpus, mined on demand by mine-sessions'
    # attribute_predispatch.py (pre-first-dispatch context attribution). No
    # state-script collector exists, so compute returns honest NO-DATA for these
    # (the `no computation registered` fall-through) — registering the selectors
    # lets the plan-execution context-diet features' drafted `## KPI Declaration`
    # rows lint clean, same pattern as canary-trip-precision above.
    "session-log-mining": frozenset({
        "predispatch-phases-read-bytes",   # phases-slice-scoped-reads
        "predispatch-spec-read-bytes",     # spec-excerpt-scoped-plans
        "predispatch-skill-body-bytes",    # execute-plan-skill-diet
        "predispatch-plan-read-bytes",     # lean-plan-files
        # cognito-pr-review efficiency features: registered at spec-finalization
        # so their drafted `## KPI Declaration` rows lint clean (compute returns
        # honest NO-DATA until a collector is wired), same pattern as above.
        "review-run-fresh-tokens",             # pr-review-size-aware-pipeline-downshift
        "sweep-agent-first-turn-ctx-tokens",   # pr-review-sweep-rule-sharding-and-read-dedup
        "buddy-first-ask-ctx-tokens",          # pr-review-buddy-phase0-subagent-isolation
        "turn1-baseline-ctx-tokens-noncognito",  # pr-review-plugin-repo-scoping-and-orphan-purge
    }),
    # efficacy-signal-integrity Phase 3: a pure-read scan of committed
    # docs/interventions/*.md frontmatter + `## Review <date>` / `## Canary
    # <date>` body sections — never a re-implementation of the evaluator's
    # own verdict/canary arithmetic, just a read over what it already wrote.
    "intervention-records": frozenset({
        "conclusive-verdict-count",
        "confounded-verdict-ratio",
        "canary-closure-latency-p50-days",
    }),
}

# vantage.host closed enum (efficacy-signal-integrity D3).
_VANTAGE_HOSTS = frozenset({"workstation", "cloud", "any"})

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
# efficacy-signal-integrity D3: rendered INSTEAD OF NO-DATA when the current
# repo/host cannot observe the row's declared vantage — pure classification,
# no new data access.
_STATUS_WRONG_VANTAGE = "WRONG-VANTAGE"

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
    vantage = row.get("vantage")
    if vantage is not None:
        if not isinstance(vantage, dict):
            errors.append(f"{label}: vantage must be an object {{repo, host}}")
        else:
            v_repo = vantage.get("repo", "any")
            v_host = vantage.get("host", "any")
            if not isinstance(v_repo, str) or not v_repo.strip():
                errors.append(f"{label}: vantage.repo must be a non-empty string")
            if v_host not in _VANTAGE_HOSTS:
                errors.append(
                    f"{label}: vantage.host {v_host!r} not in "
                    f"{sorted(_VANTAGE_HOSTS)}")


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


def _canary_date_epoch(value) -> Optional[float]:
    """Parse a YYYY-MM-DD canary trip date to a midnight-UTC epoch. An
    unparseable value → None (the caller then keeps the trip in-window — favors
    inclusion, never silently drops a real trip)."""
    try:
        d = datetime.datetime.strptime(str(value), "%Y-%m-%d")
        return d.replace(tzinfo=datetime.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


# efficacy-signal-integrity D2 — canary staleness alarm constants. Mirrored
# (documented, deliberate duplication — kpi-scorecard.py is a pure-read
# renderer that does not import efficacy-eval.py, same house pattern as
# lazy_coord.py's documented small-helper duplication from lazy_core.py) from
# lazy_core.CANARY_WINDOW_DAYS_CEILING / efficacy-eval.py's
# CANARY_STALENESS_LOOKAHEAD_DAYS.
_CANARY_WINDOW_DAYS_CEILING = 30
_CANARY_STALENESS_LOOKAHEAD_DAYS = 7


def _canary_age_days(opened, today: datetime.date) -> Optional[int]:
    """Days elapsed since `opened` (canary staleness alarm). Unparseable →
    None (skipped from the aggregate, never fabricated)."""
    try:
        o = datetime.datetime.strptime(str(opened), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (today - o).days


def _canary_post_run_count(meta: dict, run_ids: list) -> int:
    """Distinct post-ship run_ids strictly newer than the record's frozen
    `baseline.last_run_id` (mirrors efficacy-eval.py's `_post_runs`; None
    boundary ⇒ every run counts)."""
    baseline = meta.get("baseline") or {}
    boundary = baseline.get("last_run_id") if isinstance(baseline, dict) else None
    if boundary is None:
        return len(run_ids)
    return sum(1 for r in run_ids if isinstance(r, str) and r > boundary)


def _canary_health_summary(repo_root, today: datetime.date) -> dict:
    """The Canary health section's data: open count, oldest age, and the
    count of open canaries projected to `closed-clean (no-data)`-close within
    the lookahead window (nearing the 30-day ceiling AND zero observed
    post-ship runs so far). Pure read over docs/interventions/*.md; fail-open
    to an honest all-zero summary on any error."""
    try:
        lazy_core = _bind_lazy_core(repo_root)
        interventions = Path(repo_root) / "docs" / "interventions"
        open_records = []
        if interventions.is_dir():
            for path in sorted(interventions.glob("*.md")):
                try:
                    meta = lazy_core.parse_sentinel(path)
                except (SystemExit, Exception):  # noqa: BLE001
                    continue
                if not isinstance(meta, dict):
                    continue
                canary = meta.get("canary")
                if isinstance(canary, dict) and canary.get("status") == "open":
                    open_records.append((meta.get("intervention_id") or
                                         path.stem, meta, canary))
        if not open_records:
            return {"open_count": 0, "oldest_age_days": 0,
                    "projected_no_data_close_count": 0, "items": []}
        try:
            events = lazy_core.read_intervention_telemetry(repo_root)
            run_ids = sorted({
                e.get("run_id") for e in events
                if isinstance(e.get("run_id"), str) and e.get("run_id")
            })
        except Exception:  # noqa: BLE001
            run_ids = []
        ages: list = []
        projected = 0
        items: list = []
        for rid, meta, canary in open_records:
            age = _canary_age_days(canary.get("opened"), today)
            if age is None:
                continue
            ages.append(age)
            remaining = _CANARY_WINDOW_DAYS_CEILING - age
            post_count = _canary_post_run_count(meta, run_ids)
            will_no_data = (remaining <= _CANARY_STALENESS_LOOKAHEAD_DAYS
                           and post_count == 0)
            if will_no_data:
                projected += 1
            items.append({"id": rid, "age_days": age,
                         "remaining_days": remaining, "post_runs": post_count})
        return {
            "open_count": len(open_records),
            "oldest_age_days": max(ages) if ages else 0,
            "projected_no_data_close_count": projected,
            "items": items,
        }
    except Exception:  # noqa: BLE001 — never break a scorecard render
        return {"open_count": 0, "oldest_age_days": 0,
                "projected_no_data_close_count": 0, "items": []}


def _canary_revert_closed_as_noise(repo_root, rid: str) -> bool:
    """True iff the `canary-revert-<rid>` bug resolved as `Won't-fix` (the
    close-as-noise triage outcome). An open / in-progress / fixed / MISSING
    revert item is NOT noise (it counts toward precision). Archive-aware."""
    revert_id = f"canary-revert-{rid}"
    bugs = Path(repo_root) / "docs" / "bugs"
    candidates = [bugs / revert_id / "SPEC.md"]
    archive = bugs / "_archive"
    try:
        if archive.is_dir():
            for child in sorted(archive.iterdir()):
                if child.name == revert_id or child.name.startswith(
                        revert_id + "-"):
                    candidates.append(child / "SPEC.md")
    except OSError:
        pass
    for spec in candidates:
        try:
            text = spec.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r"(?mi)^\*\*Status:\*\*\s*(.+?)\s*$", text)
        if m:
            status = m.group(1).strip().lower().replace("’", "'")
            return status in ("won't-fix", "wont-fix")
    return False


def _sel_canary_trip_precision(
        repo_root, cutoff: float) -> Tuple[Optional[float], Optional[str]]:
    """harness-change-canary-rollback KPI: precision = the fraction of canary
    trips (in the window) whose `canary-revert-<id>` item was NOT closed-as-noise.
    Read-only over docs/interventions/ records + docs/bugs/ revert outcomes.
    Honest NO-DATA (None) until the canary has tripped — never a fabricated
    zero (the D4-A ladder)."""
    lazy_core = _bind_lazy_core(repo_root)
    interventions = Path(repo_root) / "docs" / "interventions"
    if not interventions.is_dir():
        return (None, "no interventions ledger — the canary has never tripped")
    trips: list = []
    for path in sorted(interventions.glob("*.md")):
        try:
            meta = lazy_core.parse_sentinel(path)
        except (SystemExit, Exception):  # noqa: BLE001 — a malformed record skips
            continue
        if not isinstance(meta, dict):
            continue
        canary = meta.get("canary")
        if not isinstance(canary, dict) or canary.get("status") != "tripped":
            continue
        rid = meta.get("intervention_id") or path.stem
        ts = _canary_date_epoch(
            meta.get("canary_revert_enqueued") or canary.get("opened"))
        if ts is not None and ts < cutoff:
            continue  # trip predates the window
        trips.append(rid)
    if not trips:
        return (None, "no canary trips in the window — precision is undefined "
                      "until the canary has tripped (never a fabricated zero)")
    not_noise = sum(
        1 for rid in trips
        if not _canary_revert_closed_as_noise(repo_root, rid))
    return (round(not_noise / len(trips) * 100.0, 1), None)


# -- intervention-records (efficacy-signal-integrity Phase 3) -----------------

_REVIEW_SECTION_RE = re.compile(r"(?m)^## Review (\d{4}-\d{2}-\d{2})\s*$")
_VERDICT_LINE_RE = re.compile(r"(?m)^- verdict:\s*([A-Z]+)")


def _iter_review_sections(body: str):
    """Yield (date_str, section_text) for each `## Review <date>` section in
    a record body — everything up to the next `## ` header or EOF."""
    matches = list(_REVIEW_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        yield (m.group(1), body[start:end])


def _sel_conclusive_verdict_count(
        repo_root, cutoff: float) -> Tuple[Optional[float], Optional[str]]:
    """Count `## Review` sections in the window whose verdict is CONFIRMED or
    REFUTED — the measurement-theater KPI (a ledger that never yields a
    conclusive verdict is not measuring anything)."""
    interventions = Path(repo_root) / "docs" / "interventions"
    if not interventions.is_dir():
        return (None, "no interventions ledger — no reviews have run yet")
    count = 0
    any_review = False
    for path in sorted(interventions.glob("*.md")):
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for date_str, section in _iter_review_sections(body):
            ts = _canary_date_epoch(date_str)
            if ts is None or ts < cutoff:
                continue
            any_review = True
            m = _VERDICT_LINE_RE.search(section)
            if m and m.group(1) in ("CONFIRMED", "REFUTED"):
                count += 1
    if not any_review:
        return (None, "no reviews recorded in the window")
    return (float(count), None)


def _sel_confounded_verdict_ratio(
        repo_root, cutoff: float) -> Tuple[Optional[float], Optional[str]]:
    """Share of due reviews in the window capped INCONCLUSIVE (confounded) —
    the D6 same-signal cap; the sub-signal seam (efficacy-signal-integrity
    Phase 1) is the lever that moves this down."""
    interventions = Path(repo_root) / "docs" / "interventions"
    if not interventions.is_dir():
        return (None, "no interventions ledger — no reviews have run yet")
    total = 0
    confounded = 0
    for path in sorted(interventions.glob("*.md")):
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for date_str, section in _iter_review_sections(body):
            ts = _canary_date_epoch(date_str)
            if ts is None or ts < cutoff:
                continue
            total += 1
            if "confounded" in section.lower():
                confounded += 1
    if total == 0:
        return (None, "no due reviews in the window — ratio is undefined")
    return (round(100.0 * confounded / total, 1), None)


def _canary_closed_date(meta: dict, body: str) -> Optional[str]:
    """The closed-on date for a terminal (non-open) canary: the trip date
    (`canary_revert_enqueued`, stamped at trip — tripped canaries get no `##
    Canary` body section) for a tripped canary, else the `## Canary <date>`
    heading date (closed-clean / closed-clean (no-data))."""
    status = (meta.get("canary") or {}).get("status")
    if status == "tripped":
        return meta.get("canary_revert_enqueued")
    if isinstance(status, str) and status.startswith("closed-clean"):
        m = re.search(r"(?m)^## Canary (\d{4}-\d{2}-\d{2})", body)
        return m.group(1) if m else None
    return None


def _sel_canary_closure_latency_p50(
        repo_root, cutoff: float) -> Tuple[Optional[float], Optional[str]]:
    """Median opened→closed days over canaries closed in the window,
    EXCLUDING `closed-clean (no-data)` ceiling closes (those never count as a
    genuine closure latency — the canary-health alarm counts them
    separately). Both `closed-clean` and `tripped` count as terminal
    closures."""
    lazy_core = _bind_lazy_core(repo_root)
    interventions = Path(repo_root) / "docs" / "interventions"
    if not interventions.is_dir():
        return (None, "no interventions ledger — no canaries have closed")
    latencies: list = []
    for path in sorted(interventions.glob("*.md")):
        try:
            meta = lazy_core.parse_sentinel(path)
        except (SystemExit, Exception):  # noqa: BLE001
            continue
        if not isinstance(meta, dict):
            continue
        canary = meta.get("canary")
        if not isinstance(canary, dict):
            continue
        status = canary.get("status")
        if status == "closed-clean (no-data)":
            continue  # excluded per the KPI's own notes
        if status not in ("closed-clean", "tripped"):
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        closed = _canary_closed_date(meta, body)
        opened_ts = _canary_date_epoch(canary.get("opened"))
        closed_ts = _canary_date_epoch(closed) if closed else None
        if opened_ts is None or closed_ts is None:
            continue
        if closed_ts < cutoff:
            continue  # closed before the window
        latencies.append((closed_ts - opened_ts) / 86400.0)
    if not latencies:
        return (None, "no canary closures (excluding no-data) in the window")
    return (round(statistics.median(latencies), 1), None)


def _sel_intervention_records(
        repo_root, selector: str,
        cutoff: float) -> Tuple[Optional[float], Optional[str]]:
    if selector == "conclusive-verdict-count":
        return _sel_conclusive_verdict_count(repo_root, cutoff)
    if selector == "confounded-verdict-ratio":
        return _sel_confounded_verdict_ratio(repo_root, cutoff)
    if selector == "canary-closure-latency-p50-days":
        return _sel_canary_closure_latency_p50(repo_root, cutoff)
    return (None, f"unknown intervention-records selector {selector!r}")


def _sel_telemetry(repo_root, selector: str,
                   cutoff: float) -> Tuple[Optional[float], Optional[str]]:
    # The canary-trip-precision selector's data source is the intervention
    # records + revert-bug outcomes, NOT the telemetry ledger — evaluate it
    # before the ledger-presence gate so a repo with canary trips but no
    # (yet-rotated) ledger still computes honestly.
    if selector == "canary-trip-precision":
        return _sel_canary_trip_precision(repo_root, cutoff)
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
        elif source == "intervention-records":
            return _sel_intervention_records(repo_root, selector, cutoff)
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

def _vantage_match(row, repo_root, host) -> bool:
    """efficacy-signal-integrity D3: does the CURRENT (repo_root, host) match
    the row's declared `vantage`? Absent/non-dict `vantage` → always matches
    (default any/any, fully backward-compatible). A dimension is checked ONLY
    when the caller supplies a value for it AND the row declares a non-"any"
    value — omitting `repo_root`/`host` (old callers, --lint) never produces a
    WRONG-VANTAGE classification, preserving pre-D3 behavior exactly."""
    vantage = row.get("vantage")
    if not isinstance(vantage, dict):
        return True
    v_repo = vantage.get("repo", "any")
    v_host = vantage.get("host", "any")
    if v_repo not in (None, "any") and repo_root is not None:
        if Path(repo_root).name != v_repo:
            return False
    if v_host not in (None, "any") and host is not None:
        if host != v_host:
            return False
    return True


def row_status(row, value, *, repo_root=None, host=None) -> str:
    """The D4-A honesty ladder: NO-DATA → PENDING-BASELINE → band comparison.
    efficacy-signal-integrity D3: a NO-DATA value renders WRONG-VANTAGE
    instead when the current (repo_root, host) cannot observe this row's
    declared vantage — pure classification swap, no new data access."""
    if value is None:
        if not _vantage_match(row, repo_root, host):
            return _STATUS_WRONG_VANTAGE
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


def render_scorecard(registry, readings: dict, *, today: datetime.date,
                     repo_root=None, host=None, canary_health=None) -> str:
    """Render the full SCORECARD.md — a PURE function of (registry, readings,
    today, repo_root, host, canary_health). No wall-clock embed; unchanged
    inputs → byte-identical output. `repo_root`/`host` (efficacy-signal-
    integrity D3) enable the WRONG-VANTAGE classification; omitted, every row
    renders exactly as before D3 shipped. `canary_health` (D2) feeds the
    Canary health section; omitted renders an honest "(none open)"."""
    lines = [
        "# Friction KPI Scorecard",
        "",
        "> Pure-read render of `docs/kpi/registry.json` by "
        "`user/scripts/kpi-scorecard.py` — script-computed values only, "
        "no embedded wall-clock (freshness is this file's git commit "
        "time). An absent/unrecordable signal renders NO-DATA, never a "
        "fabricated zero; a `pending` baseline renders PENDING-BASELINE; a "
        "signal unobservable from this repo/host renders WRONG-VANTAGE.",
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
            status = row_status(row, value, repo_root=repo_root, host=host)
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

    # efficacy-signal-integrity D2: the committed-channel canary staleness
    # alarm — mirrors the run-end flush notify line so the operator reaches
    # it even on a day with no run. A `closed-clean (no-data)` close is
    # ALWAYS a distinct, separately-counted signal from a genuine clean close
    # (never laundered into silence here either).
    lines.append("")
    lines.append("## Canary health")
    lines.append("")
    ch = canary_health or {"open_count": 0, "oldest_age_days": 0,
                           "projected_no_data_close_count": 0}
    if ch.get("open_count", 0) == 0:
        lines.append("- (none open)")
    else:
        lines.append(
            f"- {ch['open_count']} canaries open, oldest "
            f"{ch['oldest_age_days']}d, "
            f"{ch['projected_no_data_close_count']} will no-data-close "
            f"within {_CANARY_STALENESS_LOOKAHEAD_DAYS}d")
        if ch.get("projected_no_data_close_count", 0) > 0:
            lines.append(
                "  - ⚠ a no-data close launders an unwatched change as "
                "observed — investigate before the 30-day ceiling fires.")

    if notes:
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        lines.extend(notes)

    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_host(host_arg: Optional[str]) -> str:
    """efficacy-signal-integrity D3: resolve the CURRENT host classification.
    Explicit `--host` wins; else `LAZY_HOST_KIND` env; else the safe default
    `workstation` (kpi-scorecard's typical invocation context — the
    claude-config commit path). An unrecognized value falls back to
    `workstation` rather than erroring a render."""
    for candidate in (host_arg, os.environ.get("LAZY_HOST_KIND")):
        if candidate in _VANTAGE_HOSTS - {"any"}:
            return candidate
    return "workstation"


def _cmd_render(repo_root: Path, *, stdout: bool, today: datetime.date,
                now: Optional[float] = None,
                host: Optional[str] = None) -> int:
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
    canary_health = _canary_health_summary(repo_root, today)
    doc = render_scorecard(registry, readings, today=today,
                           repo_root=repo_root, host=_resolve_host(host),
                           canary_health=canary_health)
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
    parser.add_argument("--host", default=None, choices=sorted(_VANTAGE_HOSTS - {"any"}),
                        help="Current host classification for the D3 vantage "
                             "check (default: $LAZY_HOST_KIND env, else "
                             "'workstation'). Only affects rendering.")
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
    return _cmd_render(repo_root, stdout=args.stdout, today=today, host=args.host)


if __name__ == "__main__":
    sys.exit(main())
