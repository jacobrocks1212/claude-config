#!/usr/bin/env python3
"""
test_efficacy_eval.py — Tests for the intervention-efficacy evaluator.

Covers intervention-efficacy-tracking Phases 2 + 3:
  - Phase 2: window accrual (post-ship run counting off the frozen
    `baseline.last_run_id`), min-sample floor, the D5 ±band verdict arithmetic
    (CONFIRMED / REFUTED / INCONCLUSIVE), honest degradation reasons
    (undeclared / kpi-unresolvable / no-baseline / min-sample), confounder
    scan + same-signal INCONCLUSIVE(confounded) cap, self-emitted independence
    annotation, review append + frontmatter update, escalation after 2
    INCONCLUSIVE reviews, --dry-run byte-inertness, --id filter, exit codes.
  - Phase 3: the REFUTED consequence — auto-enqueue of reconsider-<id> via the
    sanctioned `lazy-state.py --enqueue-adhoc --type bug` subprocess behind the
    D7 two-layer recurrence guard (bug-dir existence incl. archive; the
    `reconsideration_enqueued` stamp).

Conventions match test_lazy_queue_doc.py: the dash-named module is loaded via
importlib; everything is hermetic via LAZY_STATE_DIR temp dirs + temp repos.
Fixture records are written by the REAL lazy_core.record_intervention and
fixture ledgers by the REAL append_telemetry_event under REAL run markers —
never hand-rolled shapes.

Run with: python -m pytest user/scripts/test_efficacy_eval.py -q
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lazy_core  # noqa: E402


def _load_module():
    """Import the dash-named evaluator module via importlib."""
    import importlib.util

    path = _SCRIPTS_DIR / "efficacy-eval.py"
    spec = importlib.util.spec_from_file_location("efficacy_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eff = _load_module()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_BASE_NOW = 1_700_000_000.0


@pytest.fixture()
def state_env(tmp_path, monkeypatch):
    """Hermetic LAZY_STATE_DIR + a temp repo root."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("LAZY_STATE_DIR", str(state))
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    return {"state": state, "repo": repo}


def _seed_runs(n: int, events_per_run: int, *, start: int = 0,
               event: str = "gate-refusal") -> list[str]:
    """Seed `n` fixture runs (run index `start`..`start+n-1`) into the
    LAZY_STATE_DIR ledger via the REAL marker + emitter. Returns run_ids."""
    run_ids: list[str] = []
    for i in range(start, start + n):
        now = _BASE_NOW + i * 3600.0
        marker = lazy_core.write_run_marker(
            pipeline="feature", cloud=False, repo_root="/r",
            max_cycles=5, now=now,
        )
        run_ids.append(marker["started_at"])
        # Every real run emits its run-bracket events regardless of the
        # targeted signal — a zero-signal run must still COUNT as a run.
        assert lazy_core.append_telemetry_event(
            "run-start", data={}, now=now + 0.5,
        ) is True
        for j in range(events_per_run):
            assert lazy_core.append_telemetry_event(
                event, item_id=f"i{i}", data={}, now=now + 1.0 + j,
            ) is True
    return run_ids


def _capture(repo: Path, rid: str, *, target: str = "event:gate-refusal",
             direction: str = "decrease", review_after: int = 4,
             baseline_runs: int = 4, min_sample: int = 5, band: int = 20,
             independence: str = "independent — external counter",
             shipped_date: str | None = None) -> Path:
    """Write a record via the REAL record_intervention (SPEC-block route)."""
    spec_dir = repo / "docs" / "features" / rid
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "SPEC.md").write_text(
        f"# {rid}\n\n## Intervention Hypothesis\n\n"
        f"- target_signal: {target}\n"
        f"- expected_direction: {direction}\n"
        f"- signal_independence: {independence}\n"
        f"- review_after_runs: {review_after}\n"
        f"- baseline_runs: {baseline_runs}\n"
        f"- min_sample: {min_sample}\n"
        f"- band_pct: {band}\n",
        encoding="utf-8",
    )
    res = lazy_core.record_intervention(
        repo, rid, pipeline="feature", spec_path=spec_dir,
        shipped_date=shipped_date, date=shipped_date,
    )
    assert res["recorded"] is True, res
    return Path(res["path"])


def _run_eval(repo: Path, *args: str) -> "tuple[int, dict]":
    """Invoke the evaluator's main() in-process; return (exit_code, json)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = eff.main(["--repo-root", str(repo), "--json", *args])
    out = buf.getvalue()
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:  # pragma: no cover — aids debugging
        raise AssertionError(f"non-JSON evaluator output (exit {code}): {out!r}")
    return code, payload


def _verdict_of(payload: dict, rid: str) -> dict | None:
    for v in payload.get("verdicts", []):
        if v.get("id") == rid:
            return v
    return None


# ---------------------------------------------------------------------------
# Phase 2 — verdict arithmetic + windows + degradation
# ---------------------------------------------------------------------------


def test_confirmed_on_expected_direction_movement(state_env):
    """Baseline 2.0 ev/run → post 0.25 ev/run (−87.5%) with decrease expected
    → CONFIRMED; delta reported; exit 0; record status flips terminal."""
    repo = state_env["repo"]
    _seed_runs(4, 2)                      # baseline: 8 events / 4 runs
    rec = _capture(repo, "containment-tighten-denyset")
    _seed_runs(4, 0, start=4)             # post: 0 events / 4 runs... need ≥5 sample
    # min_sample = 5 → baseline 8 + post 0 = 8 ≥ 5 → conclusive allowed.
    code, payload = _run_eval(repo)
    assert code == 0
    v = _verdict_of(payload, "containment-tighten-denyset")
    assert v is not None, payload
    assert v["verdict"] == "confirmed", v
    assert float(v["delta_pct"]) <= -20.0
    meta = lazy_core.parse_sentinel(rec)
    assert meta["status"] == "confirmed"
    assert meta["review_count"] == 1
    # A terminal record is not re-reviewed.
    code2, payload2 = _run_eval(repo)
    assert _verdict_of(payload2, "containment-tighten-denyset") is None


def test_refuted_on_against_direction_movement_exit_zero(state_env):
    """Post rate ≥ +20% against an expected decrease → REFUTED — and the
    evaluator still exits 0 (verdicts are data, not errors)."""
    repo = state_env["repo"]
    _seed_runs(4, 1)                      # baseline 1.0 ev/run
    rec = _capture(repo, "adhoc-fix-probe-cache")
    _seed_runs(4, 3, start=4)             # post 3.0 ev/run → +200%
    code, payload = _run_eval(repo)
    assert code == 0, "REFUTED must NOT be a non-zero exit"
    v = _verdict_of(payload, "adhoc-fix-probe-cache")
    assert v["verdict"] == "refuted", v
    assert float(v["delta_pct"]) >= 20.0
    meta = lazy_core.parse_sentinel(rec)
    assert meta["status"] == "refuted"


def test_inconclusive_within_band_and_min_sample(state_env):
    """(a) movement inside the ±band → INCONCLUSIVE (within-band);
    (b) combined events below min_sample → INCONCLUSIVE (min-sample x/y)."""
    repo = state_env["repo"]
    # (a) within band: 2.0 → 2.0 (0%).
    _seed_runs(4, 2)
    rec_a = _capture(repo, "spec-gate-tune")
    # (b) min-sample: separate signal (event:halt — zero occurrences anywhere,
    # so 0 baseline + 0 post events < min_sample 5) sharing the same window.
    rec_b = _capture(repo, "tiny-sample", target="event:halt",
                     min_sample=5, review_after=4, baseline_runs=4)
    _seed_runs(4, 2, start=4)
    code, payload = _run_eval(repo)
    assert code == 0
    va = _verdict_of(payload, "spec-gate-tune")
    assert va["verdict"] == "inconclusive"
    assert "within-band" in va["reason"]
    meta_a = lazy_core.parse_sentinel(rec_a)
    assert meta_a["status"] == "inconclusive"
    assert meta_a["escalated"] is False  # one review < N=2
    vb = _verdict_of(payload, "tiny-sample")
    # halt events: zero everywhere → 0 baseline + 0 post < 5 sample.
    assert vb["verdict"] == "inconclusive"
    assert "min-sample" in vb["reason"]


def test_window_accrual_not_due_until_review_after_runs(state_env):
    """A record is NOT reviewed until review_after_runs post-ship runs have
    accrued; it surfaces under not_due with the accrual count."""
    repo = state_env["repo"]
    _seed_runs(4, 2)
    _capture(repo, "slow-accrual", review_after=4)
    _seed_runs(2, 1, start=4)             # only 2 of 4 post runs
    code, payload = _run_eval(repo)
    assert code == 0
    assert _verdict_of(payload, "slow-accrual") is None
    nd = [e for e in payload["not_due"] if e["id"] == "slow-accrual"]
    assert nd and nd[0]["post_runs"] == 2 and nd[0]["needed"] == 4


def test_frozen_baseline_survives_ledger_deletion(state_env):
    """The Validation-Criteria 'Baseline frozen' row: delete the state-dir
    ledger after capture — evaluation still uses the RECORDED baseline."""
    repo = state_env["repo"]
    _seed_runs(4, 2)                      # baseline 2.0 ev/run frozen
    rec = _capture(repo, "frozen-base")
    # Rotate/delete the raw ledger (retention must not matter).
    ledger = Path(os.environ["LAZY_STATE_DIR"]) / "lazy-telemetry.jsonl"
    ledger.unlink()
    _seed_runs(4, 0, start=4)             # fresh post-only ledger
    code, payload = _run_eval(repo)
    v = _verdict_of(payload, "frozen-base")
    assert v is not None and v["verdict"] == "confirmed", (v, payload)
    meta = lazy_core.parse_sentinel(rec)
    assert meta["baseline"]["value"] == 2.0  # untouched by evaluation


def test_undeclared_and_kpi_targets_degrade_inconclusive(state_env):
    """target_signal: undeclared → INCONCLUSIVE (undeclared);
    kpi:<...> without the registry → INCONCLUSIVE (kpi-unresolvable).
    Neither errors; both still accrue reviews on the run cadence."""
    repo = state_env["repo"]
    _seed_runs(2, 1)
    # Undeclared: no hypothesis block.
    spec = repo / "docs" / "features" / "undeclared-item"
    spec.mkdir(parents=True)
    (spec / "SPEC.md").write_text("# U\n", encoding="utf-8")
    res = lazy_core.record_intervention(
        repo, "undeclared-item", pipeline="feature", spec_path=spec)
    assert res["recorded"] is True
    # kpi target via overrides (the soft-dep seam).
    lazy_core.record_intervention(
        repo, "kpi-item", pipeline="feature",
        hypothesis_overrides={"target_signal": "kpi:containment.runaway-trips",
                              "expected_direction": "decrease",
                              "review_after_runs": 2},
    )
    # Give the undeclared item a small window too.
    # (record_intervention default review_after_runs = 20; use the CLI-shaped
    # override path for a small window.)
    lazy_core.record_intervention(
        repo, "undeclared-small", pipeline="feature",
        hypothesis_overrides={"review_after_runs": 2},
    )
    _seed_runs(2, 1, start=2)
    code, payload = _run_eval(repo)
    assert code == 0
    vk = _verdict_of(payload, "kpi-item")
    assert vk["verdict"] == "inconclusive" and "kpi-unresolvable" in vk["reason"]
    vu = _verdict_of(payload, "undeclared-small")
    assert vu["verdict"] == "inconclusive" and "undeclared" in vu["reason"]


def test_confounder_same_signal_caps_both_inconclusive(state_env):
    """D6: two open records targeting the SAME signal with overlapping post
    windows → both reviews capped INCONCLUSIVE (confounded), cross-annotated.
    A different-signal record annotates WITHOUT capping."""
    repo = state_env["repo"]
    _seed_runs(4, 2)
    rec_a = _capture(repo, "same-sig-a", shipped_date="2026-07-01")
    rec_b = _capture(repo, "same-sig-b", shipped_date="2026-07-02")
    rec_c = _capture(repo, "other-sig", target="event:halt",
                     shipped_date="2026-07-03", min_sample=1)
    _seed_runs(4, 0, start=4)  # a decisive move that WOULD confirm a+b
    code, payload = _run_eval(repo)
    va = _verdict_of(payload, "same-sig-a")
    vb = _verdict_of(payload, "same-sig-b")
    assert va["verdict"] == "inconclusive" and "confounded" in va["reason"], va
    assert vb["verdict"] == "inconclusive" and "confounded" in vb["reason"], vb
    assert any("same-sig-b" in c for c in va["confounders"])
    assert any("same-sig-a" in c for c in vb["confounders"])
    # Cross-annotation lands in the review body too.
    assert "same-sig-b" in rec_a.read_text(encoding="utf-8")
    # Different-signal: annotated (a+b list it as confounders? no — OTHER
    # records list c only if same window; c itself is NOT capped by a/b).
    vc = _verdict_of(payload, "other-sig")
    assert vc is not None
    assert "confounded" not in vc["reason"], vc
    assert any("same-sig-a" in c for c in vc.get("confounders", []))


def test_self_emitted_independence_is_annotated(state_env):
    """A self-emitted signal_independence is ANNOTATED on the review (visibly
    weaker verdict) — never enforced/blocked (that is the sibling gate's job)."""
    repo = state_env["repo"]
    _seed_runs(4, 2)
    rec = _capture(repo, "self-emitted-item",
                   independence="self-emitted — the change emits this event")
    _seed_runs(4, 0, start=4)
    code, payload = _run_eval(repo)
    v = _verdict_of(payload, "self-emitted-item")
    assert v["verdict"] == "confirmed"          # not blocked
    assert v.get("independence") == "self-emitted"
    assert "self-emitted" in rec.read_text(encoding="utf-8")


def test_escalation_after_two_inconclusive_reviews(state_env):
    """D8: after 2 INCONCLUSIVE reviews the record gains escalated: true and
    is listed under needs_triage; it keeps reviewing (passive surfacing)."""
    repo = state_env["repo"]
    lazy_core.record_intervention(
        repo, "old-halt-tweak", pipeline="feature",
        hypothesis_overrides={"review_after_runs": 1},
    )
    _seed_runs(1, 1)
    code, p1 = _run_eval(repo)
    meta = lazy_core.parse_sentinel(
        repo / "docs" / "interventions" / "old-halt-tweak.md")
    assert meta["review_count"] == 1 and meta["escalated"] is False
    _seed_runs(1, 1, start=1)
    code, p2 = _run_eval(repo)
    meta = lazy_core.parse_sentinel(
        repo / "docs" / "interventions" / "old-halt-tweak.md")
    assert meta["review_count"] == 2 and meta["escalated"] is True
    assert any("old-halt-tweak" in t for t in p2["needs_triage"])
    # Third window: still reviewed (passive, never halted), still triaged.
    _seed_runs(1, 1, start=2)
    code, p3 = _run_eval(repo)
    assert any("old-halt-tweak" in t for t in p3["needs_triage"])
    meta = lazy_core.parse_sentinel(
        repo / "docs" / "interventions" / "old-halt-tweak.md")
    assert meta["review_count"] == 3


def test_dry_run_is_byte_inert_and_id_filters(state_env):
    """--dry-run reports verdicts but writes NOTHING; --id restricts the scan
    to one record."""
    repo = state_env["repo"]
    _seed_runs(4, 2)
    rec_a = _capture(repo, "dry-a")
    rec_b = _capture(repo, "dry-b", target="event:halt", min_sample=1)
    _seed_runs(4, 0, start=4)
    before_a = rec_a.read_bytes()
    before_b = rec_b.read_bytes()
    code, payload = _run_eval(repo, "--dry-run")
    assert code == 0
    assert payload["dry_run"] is True
    assert _verdict_of(payload, "dry-a") is not None
    assert rec_a.read_bytes() == before_a, "--dry-run must not write"
    assert rec_b.read_bytes() == before_b
    # --id: only the named record is considered.
    code, payload = _run_eval(repo, "--dry-run", "--id", "dry-a")
    assert _verdict_of(payload, "dry-a") is not None
    assert _verdict_of(payload, "dry-b") is None
    # Real run then writes reviews.
    code, payload = _run_eval(repo, "--id", "dry-a")
    assert rec_a.read_bytes() != before_a
    assert rec_b.read_bytes() == before_b


def test_no_records_and_missing_dirs_are_clean(state_env):
    """No docs/interventions dir → clean empty run, exit 0 (never an error)."""
    repo = state_env["repo"]
    code, payload = _run_eval(repo)
    assert code == 0
    assert payload["reviewed"] == 0
    assert payload["verdicts"] == []


def test_malformed_repo_root_exits_2(state_env):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = eff.main(["--repo-root",
                         str(state_env["repo"] / "nope-not-a-dir"), "--json"])
    assert code == 2


# ---------------------------------------------------------------------------
# Phase 3 — REFUTED consequence (two-layer recurrence guard)
# ---------------------------------------------------------------------------


def _refuted_fixture(repo: Path) -> Path:
    """Build a record that will evaluate REFUTED on the next run."""
    _seed_runs(4, 1)
    rec = _capture(repo, "probe-cache-fix")
    _seed_runs(4, 3, start=4)
    return rec


def test_refuted_enqueues_reconsideration_exactly_once(state_env):
    """D7 end-to-end: a REFUTED verdict enqueues reconsider-<id> through the
    sanctioned --type bug route EXACTLY ONCE across repeated evaluations; the
    record is stamped reconsideration_enqueued; the brief names the record."""
    repo = state_env["repo"]
    rec = _refuted_fixture(repo)
    code, payload = _run_eval(repo)
    v = _verdict_of(payload, "probe-cache-fix")
    assert v["verdict"] == "refuted"
    assert "reconsider-probe-cache-fix" in (v.get("consequence") or "")
    queue = json.loads(
        (repo / "docs" / "bugs" / "queue.json").read_text(encoding="utf-8"))
    entries = [e for e in queue["queue"]
               if e.get("id") == "reconsider-probe-cache-fix"]
    assert len(entries) == 1
    brief = (repo / "docs" / "bugs" / "reconsider-probe-cache-fix"
             / "ADHOC_BRIEF.md").read_text(encoding="utf-8")
    assert "probe-cache-fix" in brief
    assert "revert" in brief.lower()
    meta = lazy_core.parse_sentinel(rec)
    assert meta["reconsideration_enqueued"] is not None
    assert meta["status"] == "refuted"

    # Repeated evaluations: terminal status → no re-review, no second entry.
    for _ in range(2):
        _run_eval(repo)
    queue = json.loads(
        (repo / "docs" / "bugs" / "queue.json").read_text(encoding="utf-8"))
    entries = [e for e in queue["queue"]
               if e.get("id") == "reconsider-probe-cache-fix"]
    assert len(entries) == 1


def test_guard_layer2_stamp_blocks_even_if_bug_dir_vanishes(state_env):
    """Layer 2: once reconsideration_enqueued is stamped, the enqueue never
    re-fires — even when the bug dir AND queue entry vanish."""
    repo = state_env["repo"]
    rec = _refuted_fixture(repo)
    _run_eval(repo)
    # Nuke the bug pipeline artifacts entirely.
    import shutil
    shutil.rmtree(repo / "docs" / "bugs")
    # Force a re-evaluation attempt by reopening the record (simulates any
    # future path that would re-verdict REFUTED for the same intervention).
    text = rec.read_text(encoding="utf-8")
    rec.write_text(text.replace("status: refuted", "status: open"),
                   encoding="utf-8")
    _seed_runs(4, 3, start=8)
    code, payload = _run_eval(repo)
    v = _verdict_of(payload, "probe-cache-fix")
    assert v is not None and v["verdict"] == "refuted"
    assert not (repo / "docs" / "bugs" / "reconsider-probe-cache-fix").exists()
    assert "already" in (v.get("consequence") or ""), v


def test_guard_layer1_open_or_archived_dir_skips_enqueue(state_env):
    """Layer 1: an existing docs/bugs/reconsider-<id>/ dir — OPEN or ARCHIVED —
    skips the enqueue even when the stamp is absent (e.g. a hand-cleared
    frontmatter)."""
    repo = state_env["repo"]
    rec = _refuted_fixture(repo)
    # Pre-create an ARCHIVED reconsideration dir (post-archive recurrence).
    arch = repo / "docs" / "bugs" / "_archive" / "reconsider-probe-cache-fix"
    arch.mkdir(parents=True)
    code, payload = _run_eval(repo)
    v = _verdict_of(payload, "probe-cache-fix")
    assert v["verdict"] == "refuted"
    assert not (repo / "docs" / "bugs" / "reconsider-probe-cache-fix").exists()
    qpath = repo / "docs" / "bugs" / "queue.json"
    if qpath.exists():
        queue = json.loads(qpath.read_text(encoding="utf-8"))
        assert not [e for e in queue.get("queue", [])
                    if e.get("id") == "reconsider-probe-cache-fix"]
    # The record is STILL stamped (the guard outcome is recorded).
    meta = lazy_core.parse_sentinel(rec)
    assert meta["reconsideration_enqueued"] is not None


def test_dry_run_never_enqueues_on_refuted(state_env):
    repo = state_env["repo"]
    _refuted_fixture(repo)
    code, payload = _run_eval(repo, "--dry-run")
    v = _verdict_of(payload, "probe-cache-fix")
    assert v["verdict"] == "refuted"
    assert not (repo / "docs" / "bugs").exists()


# ---------------------------------------------------------------------------
# Canary watcher (harness-change-canary-rollback Phases 2 + 3)
# ---------------------------------------------------------------------------

# _BASE_NOW = 1_700_000_000.0 ≈ 2023-11-14T22:13:20Z, so a canary opened
# "2023-11-14" has its window-start epoch just before the seeded fixture runs
# and is 30-day-ceiling-matured relative to any real `today`.
_CANARY_OPENED_PAST = "2023-11-14"
_CANARY_WINDOW_START = 1_699_920_000.0  # 2023-11-14T00:00:00Z


def _add_canary(rec_path: Path, *, opened: str = _CANARY_OPENED_PAST,
                surfaces=None, window_runs: int = 10, pair_scope=None,
                commit_set=None, status: str = "open",
                degraded_note=None) -> None:
    """Inject a `canary:` sub-map onto an existing record (Phase-1 registration
    is tested in test_lazy_core.py; here we fixture the watcher's input)."""
    meta = lazy_core.parse_sentinel(rec_path)
    body = eff._split_record_body(rec_path.read_text(encoding="utf-8"))
    meta["canary"] = {
        "opened": opened,
        "window_runs": window_runs,
        "surfaces": list(surfaces or ["user/hooks/lazy-cycle-containment.sh"]),
        "commit_set": list(commit_set or ["deadbeefcafe"]),
        "pair_scope": list(pair_scope or []),
        "degraded_revert_note": degraded_note,
        "status": status,
    }
    lazy_core._atomic_write(
        rec_path, lazy_core._render_intervention_record(meta, body))


def _run_canary(repo: Path, *args: str) -> "tuple[int, dict]":
    """Invoke the evaluator's canary mode in-process; return (exit_code, json)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = eff.main(["--repo-root", str(repo), "--json", "--canary", *args])
    out = buf.getvalue()
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:  # pragma: no cover
        raise AssertionError(f"non-JSON canary output (exit {code}): {out!r}")
    return code, payload


def _write_hook_events(entries: list[dict]) -> None:
    """Append fixture hook-events.jsonl lines into the LAZY_STATE_DIR keyed
    dir (the incident-scan reader surface)."""
    state = lazy_core.claude_state_dir(create=True)
    path = state / "hook-events.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _mon_of(payload: dict, rid: str) -> dict | None:
    for m in payload.get("monitoring", []):
        if m.get("id") == rid:
            return m
    return None


def _trip_of(payload: dict, rid: str) -> dict | None:
    for t in payload.get("trips", []):
        if t.get("id") == rid:
            return t
    return None


# --- WU-4: scaffold + window accrual + no-data ------------------------------


def test_canary_enumerates_only_open_records(state_env):
    """--canary wakes ONLY records whose canary.status is open — a closed-clean
    / tripped / no-canary record is skipped."""
    repo = state_env["repo"]
    _seed_runs(4, 1)
    open_rec = _capture(repo, "open-canary")
    _add_canary(open_rec, opened="2099-01-01")  # future → not matured, no trip
    closed_rec = _capture(repo, "closed-canary")
    _add_canary(closed_rec, status="closed-clean", opened="2099-01-01")
    _capture(repo, "no-canary-record")  # plain intervention, no canary sub-map
    code, payload = _run_canary(repo)
    assert code == 0
    assert payload["open_canaries"] == 1
    assert _mon_of(payload, "open-canary") is not None
    assert _mon_of(payload, "closed-canary") is None
    assert _mon_of(payload, "no-canary-record") is None


def test_canary_window_accrues_post_ship_runs_capped_at_window(state_env):
    """Window accrual counts distinct post-ship run_ids up to window_runs; a
    window shorter than window_runs is not yet run-matured."""
    repo = state_env["repo"]
    _seed_runs(4, 1)                          # baseline
    rec = _capture(repo, "accrual-item")
    _add_canary(rec, opened="2099-01-01", window_runs=10)  # not ceiling-matured
    _seed_runs(6, 1, start=4)                 # 6 post-ship runs
    code, payload = _run_canary(repo)
    assert code == 0
    mon = _mon_of(payload, "accrual-item")
    assert mon is not None and mon["window"] == "6/10 runs"
    assert mon["matured"] is False
    # Shrink the window to 4 → run-matured (6 post >= 4).
    _add_canary(rec, opened="2099-01-01", window_runs=4)
    code, payload = _run_canary(repo)
    mon = _mon_of(payload, "accrual-item")
    assert mon["window"] == "4/4 runs" and mon["matured"] is True


def test_canary_30day_ceiling_matures_with_few_runs(state_env):
    """The 30-day wall-clock ceiling matures a window even with < window_runs
    observable runs."""
    repo = state_env["repo"]
    _seed_runs(4, 1)
    rec = _capture(repo, "ceiling-item")
    _add_canary(rec, opened=_CANARY_OPENED_PAST, window_runs=10)
    _seed_runs(2, 1, start=4)                 # only 2 post runs (< 10)
    code, payload = _run_canary(repo)
    mon = _mon_of(payload, "ceiling-item")
    assert mon is not None and mon["window"] == "2/10 runs"
    assert mon["matured"] is True             # ceiling, not run count


def test_canary_absent_telemetry_accrues_nothing_exit_zero(state_env):
    """An absent/unreadable telemetry ledger accrues nothing this run and the
    invocation returns exit 0 (never raises)."""
    repo = state_env["repo"]
    # A canary record with NO telemetry ledger at all (never seeded).
    spec = repo / "docs" / "features" / "no-ledger"
    spec.mkdir(parents=True)
    (spec / "SPEC.md").write_text("# N\n", encoding="utf-8")
    res = lazy_core.record_intervention(repo, "no-ledger", pipeline="feature",
                                        spec_path=spec)
    rec = Path(res["path"])
    _add_canary(rec, opened="2099-01-01")     # future → open, not matured
    code, payload = _run_canary(repo)
    assert code == 0
    mon = _mon_of(payload, "no-ledger")
    assert mon is not None and mon["window"] == "0/10 runs"
    assert payload["trips"] == [] and payload["closed_no_data"] == []


def test_canary_matured_zero_run_window_stamps_no_data(state_env):
    """A matured window (30-day ceiling) with ZERO observable post-ship runs
    stamps canary.status = 'closed-clean (no-data)' honestly."""
    repo = state_env["repo"]
    _seed_runs(4, 1)                          # baseline only; NO post runs
    rec = _capture(repo, "no-data-item")
    _add_canary(rec, opened=_CANARY_OPENED_PAST)
    code, payload = _run_canary(repo)
    assert code == 0
    assert "no-data-item" in payload["closed_no_data"]
    meta = lazy_core.parse_sentinel(rec)
    assert meta["canary"]["status"] == "closed-clean (no-data)"
    # A subsequent run no longer wakes it (status != open).
    code, payload2 = _run_canary(repo)
    assert payload2["open_canaries"] == 0


def test_canary_dry_run_does_not_stamp_no_data(state_env):
    """--dry-run reports the no-data close but writes nothing."""
    repo = state_env["repo"]
    _seed_runs(4, 1)
    rec = _capture(repo, "dry-no-data")
    _add_canary(rec, opened=_CANARY_OPENED_PAST)
    before = rec.read_bytes()
    code, payload = _run_canary(repo, "--dry-run")
    assert code == 0
    assert "dry-no-data" in payload["closed_no_data"]
    assert rec.read_bytes() == before
    assert lazy_core.parse_sentinel(rec)["canary"]["status"] == "open"


# --- WU-5: D2 band tripwire + D3 surface attribution ------------------------


def test_canary_band_regression_trips(state_env):
    """A telemetry ledger regressing the targeted signal past +25% within the
    window trips, with the band numbers reported."""
    repo = state_env["repo"]
    _seed_runs(4, 1)                          # baseline 1.0 ev/run (decrease)
    rec = _capture(repo, "band-regress")
    _add_canary(rec, opened=_CANARY_OPENED_PAST)
    _seed_runs(4, 3, start=4)                 # post 3.0 ev/run → +200%
    code, payload = _run_canary(repo)
    assert code == 0
    t = _trip_of(payload, "band-regress")
    assert t is not None, payload
    assert t["band"]["rel"] >= 25.0
    assert t["band"]["post_events"] >= 3
    assert "regressed" in t["reason"]


def test_canary_incident_attribution_trips_on_surface_match(state_env):
    """≥2 fresh incidents whose emitting surface ∈ canary.surfaces trip."""
    repo = state_env["repo"]
    _seed_runs(4, 1)
    rec = _capture(repo, "incident-trip")
    _add_canary(rec, surfaces=["user/hooks/lazy-cycle-containment.sh"],
                opened=_CANARY_OPENED_PAST)
    _write_hook_events([
        {"hook": "lazy-cycle-containment.sh", "kind": "error", "ts": _BASE_NOW},
        {"hook": "lazy-cycle-containment.sh", "kind": "error",
         "ts": _BASE_NOW + 60},
    ])
    code, payload = _run_canary(repo)
    t = _trip_of(payload, "incident-trip")
    assert t is not None, payload
    assert len(t["attributed"]) == 2


def test_canary_no_trip_on_unrelated_surface_listed_not_counted(state_env):
    """Incidents on an UNRELATED surface do not trip; they are listed as
    unattributed but not counted (D3)."""
    repo = state_env["repo"]
    _seed_runs(4, 1)
    rec = _capture(repo, "unrelated-surface")
    _add_canary(rec, surfaces=["user/hooks/lazy-cycle-containment.sh"],
                opened=_CANARY_OPENED_PAST)
    _seed_runs(2, 0, start=4)                 # observable runs → not no-data
    _write_hook_events([
        {"hook": "block-terminal-kill.sh", "kind": "error", "ts": _BASE_NOW},
        {"hook": "block-terminal-kill.sh", "kind": "error",
         "ts": _BASE_NOW + 60},
    ])
    code, payload = _run_canary(repo)
    assert _trip_of(payload, "unrelated-surface") is None
    mon = _mon_of(payload, "unrelated-surface")
    assert mon is not None and mon["attributed"] == 0
    assert mon["unattributed"] == 2


def test_canary_unresolvable_surface_never_attributes(state_env):
    """An incident whose surface cannot be resolved NEVER attributes."""
    repo = state_env["repo"]
    _seed_runs(4, 1)
    rec = _capture(repo, "unresolvable-surface")
    _add_canary(rec, surfaces=["user/hooks/lazy-cycle-containment.sh"],
                opened=_CANARY_OPENED_PAST)
    _seed_runs(2, 0, start=4)
    _write_hook_events([
        {"op": "some-op", "kind": "error", "ts": _BASE_NOW},   # no hook/surface
        {"op": "some-op", "kind": "error", "ts": _BASE_NOW + 60},
    ])
    code, payload = _run_canary(repo)
    assert _trip_of(payload, "unresolvable-surface") is None
    mon = _mon_of(payload, "unresolvable-surface")
    assert mon is not None and mon["attributed"] == 0


def test_canary_shared_surface_counts_against_all_matching(state_env):
    """A surface shared by two open canaries counts the incident against BOTH
    — each trips its own item."""
    repo = state_env["repo"]
    _seed_runs(4, 1)
    rec_a = _capture(repo, "shared-a")
    rec_b = _capture(repo, "shared-b")
    for r in (rec_a, rec_b):
        _add_canary(r, surfaces=["user/hooks/lazy-cycle-containment.sh"],
                    opened=_CANARY_OPENED_PAST)
    _write_hook_events([
        {"hook": "lazy-cycle-containment.sh", "kind": "error", "ts": _BASE_NOW},
        {"hook": "lazy-cycle-containment.sh", "kind": "error",
         "ts": _BASE_NOW + 60},
    ])
    code, payload = _run_canary(repo)
    assert _trip_of(payload, "shared-a") is not None, payload
    assert _trip_of(payload, "shared-b") is not None, payload


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
