# Native Android App for Pipeline Steering — Feature Specification

> Build on the `mobile-queue-control` foundation (read-only `LAZY_QUEUE.md`) and the `pipeline_visualizer` probe to give the operator a real mobile client: live queue/fleet/graph views plus a *write path* (enqueue ad-hoc, reorder, resolve `NEEDS_INPUT.md`, answer BLOCKED halts) by committing sentinel/queue files through the GitHub API. Closes the writes gap `mobile-queue-control` explicitly punted to chat.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator example)

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock; peers: `mobile-queue-control` (complete), `cross-repo-fleet-view`, `operator-halt-notifications`)

---

## Problem

Mobile steering today is read via GitHub-mobile (`LAZY_QUEUE.md`) and write via asking a
workstation chat session to run the state-script CLI. That's workable but indirect: no push
awareness of halts, no structured write UI, and drill-in is limited to what the committed doc
renders.

## Direction (deliberately not locked)

- **Read path:** either render committed state (GitHub API over `LAZY_QUEUE.md` + queue.json +
  SPECs — works with zero server) or talk to a reachable `pipeline_visualizer`/fleet endpoint for
  live-run fidelity; possibly both tiers.
- **Write path:** mobile-authored commits of files the pipeline already understands
  (`NEEDS_INPUT_RESOLVED_*`, queue reorder via a sanctioned commit format) — never a parallel
  write API that bypasses the state scripts' contracts; run-marker safety must be preserved.
- **Notifications:** consumes the `operator-halt-notifications` channel for halt paging + deep
  links into the app.
- **Stack:** native Android vs. PWA is an open decision — PWA may deliver 90% at far lower
  maintenance cost for a single-operator tool.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: PWA vs. native; auth (GitHub PAT
> scope); write-path contract (which files may be mobile-committed and how the pipeline ingests
> them mid-run); offline behavior. Solutions above are directional, not locked. High ambition —
> expect multi-phase.
