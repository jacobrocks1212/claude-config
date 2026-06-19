# Declare host capabilities (binary toolchains, audio devices) so host-gated features skip/defer proactively instead of churning through BLOCKED/SKIP/AskUserQuestion — Feature Spec (stub)

> Draft (pre-Gemini)

**Status:** Draft (research stub)
**Tier:** 2
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` Step 0.52 validation-readiness pre-screen, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`

---

## Problem / Friction Observed

Features whose only remaining work is runtime verification requiring an absent host capability (a C++ toolchain, an audio device) each cycle into BLOCKED.md / SKIP_MCP_TEST.md / AskUserQuestion churn and a manual deferral, because the pipeline has no advance knowledge of which host capabilities are present.

- session `a0eae4be` @ 2026-06-18T14:41:16.068Z — "their *only* unchecked items are the `golden:report` runtime-verification rows… 'deferred — requires C++ Zimtohrli toolchain'. That toolchain isn't on this host." (audio-quality-analysis, analysis-informed-dsp-updates, perceptual-audio-quality all gate on an absent C++ toolchain.)
- Related golden-gate / binary-host deferrals also appear in sessions `14de0c30` and `80dbeeaf`.

## Desired Outcome (intent, NOT design)

The pipeline knows which host capabilities are present (toolchains, devices) and proactively skips/defers features that require absent capabilities, instead of each one cycling into BLOCKED.md / SKIP_MCP_TEST.md / AskUserQuestion churn and a manual deferral. Step 0.52 already pre-screens MCP tool registration — this extends the same idea to host capabilities. The declaration format + matching is left to `/spec`.

## Open Questions / Design Forks (for `/spec` to shape — do NOT pre-bake answers)

- Where do host capabilities get declared — a host-local manifest, per-repo config, or runtime probing — and who owns keeping it current?
- How does a feature declare the capabilities it requires, and how are the two matched?
- On a capability miss, is the right action defer-to-back-of-queue, mark deferred-non-host, or skip — and does it differ for cloud vs. workstation?
- Should this fold into the existing Step 0.52 pre-screen, or be a distinct pre-screen stage?
- What capability granularity matters (named toolchain, version, audio-device presence, GPU), and how coarse vs. fine should declarations be?

> **Stub — design NOT yet shaped.** Pre-Gemini draft. `/spec` (Step 4.5) shapes the baseline interactively (AskUserQuestion), then the research gate + `/plan-feature` follow. Do not bake the solution, phases, or implementation here.
