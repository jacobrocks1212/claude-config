# Incident Auto-Capture → Bug Stubs — Feature Specification

> Hooks write `hook-error.json` breadcrumbs and deny signatures, but turning a runaway/deny-loop into a `docs/bugs/` entry is manual retro work. A collector that watches breadcrumbs + repeated-deny patterns and auto-enqueues `--type bug` stubs closes the observe→harden loop without waiting for `/lazy-batch-retro`.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The mission says friction observed in a run is a bug report against this repo — but today that
report only materializes if a retro notices it. Hook fail-OPEN breadcrumbs, repeated deny
signatures, and halt churn are structured evidence that currently evaporates between retros.

## Direction (deliberately not locked)

- **Signals:** `hook-error.json` breadcrumbs (fail-OPEN events), N-repeats of the same deny
  signature in a window, noncanonical-sentinel denies, containment trips.
- **Collector:** deterministic script (state-dir scan, read-only over logs) that clusters signals
  and enqueues via the existing `adhoc-enqueue` `--type bug` path — stub-status, so `/spec-bug`
  still owns root-cause investigation.
- **Noise control:** dedup against open/concluded bug slugs; a signal must clear a recurrence bar
  before enqueueing (one-off fail-OPEN ≠ incident).
- **Relationship to retro:** feeds the same pipeline earlier; retro remains the deep-analysis
  pass, not the sole detector.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: signal inventory + recurrence
> thresholds; run cadence (post-run hook vs. scheduled); breadcrumb schema standardization across
> hooks. Solutions above are directional, not locked.
