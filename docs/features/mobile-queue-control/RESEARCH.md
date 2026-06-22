# Research — Lazy Queue Status Doc

**Status: Gemini deep research intentionally skipped (operator decision, 2026-06-22).**

This feature is internal harness tooling — a pure-read markdown generator over the existing
`lazy-state.py` / `bug-state.py` state contract, committed per repo and read on GitHub mobile.
There is negligible external prior art to mine, and the design is fully grounded in the existing
lazy pipeline + `lazy-pipeline-visualizer` system. A deep-research round would not change any
locked decision, so it was skipped (see SPEC.md "Research References").

This file exists so the lazy pipeline does not halt on `needs-research` if the feature is later
enqueued — it is the canonical "research satisfied" marker for this repo (direct RESEARCH.md drop,
per `claude-config/CLAUDE.md`).

## Deferred empirical check (do during implementation, not research)

- **GitHub mobile relative-link behavior.** Confirm that relative links to `docs/.../SPEC.md`
  render and navigate correctly in the GitHub mobile app's markdown viewer. If they misbehave,
  fall back to absolute `github.com/<owner>/<repo>/blob/main/...` links in the generator output.
  This is a quick manual verification on the phone, captured as a Phase 2 validation step.
