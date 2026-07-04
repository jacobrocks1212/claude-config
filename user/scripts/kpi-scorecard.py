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
# CLI
# ---------------------------------------------------------------------------

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
