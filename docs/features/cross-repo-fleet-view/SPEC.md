# Cross-Repo Fleet Home Page — Feature Specification

> `pipeline_visualizer` takes one `--repo-root`; now that `multi-repo-concurrent-runs` allows concurrent runs across repos, add a multi-repo landing view aggregating every lazy-enabled repo's queues, run markers, and halts into one control plane.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

Steering N concurrent repo runs means N visualizer instances (or N terminal probes). There is no
single surface answering "which repos have live runs, which are halted, what's queued where" —
the per-repo keyed state dirs (`~/.claude/state/<repo_key>/`) already hold the answer.

## Direction (deliberately not locked)

- **Discovery:** enumerate per-repo keyed state dirs and/or a small registry of lazy-enabled repo
  roots (manifest.psd1's `Repos` scope is a candidate source).
- **Renderer:** a home page in the existing `pipeline_visualizer` server, linking into the current
  per-repo views; pure read over `probe_state`, never re-inferring state.
- **Peer surfaces:** complements per-repo `LAZY_QUEUE.md` (GitHub-mobile channel) and would be the
  natural backend for the Android-app proposal.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: repo-root discovery mechanism;
> staleness display for repos with dead markers; performance with many repos. Solutions above are
> directional, not locked.
