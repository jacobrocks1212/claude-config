---
kind: needs-input
feature_id: lazy-validation-readiness
written_by: harden-harness
decisions:
  - "Heterogeneous device-axis: how MIDI-hardware (and future non-audio device) deferrals avoid the audio-axis device re-open loop"
  - "mcp-test test-pattern isolation: where to enforce single-pattern isolation for a global-shadow observable"
date: 2026-06-27
---

# /harden-harness — Needs Input (Round 40 forks)

Two validation-harness gaps were observed during a `/lazy-batch` run of
`motorized-fader-sync` (AlgoBooth) on a host with **real audio but NO MIDI
controller hardware**. The mechanical enabling fix landed (`harden(script)`
commit `8904244` — a `midi-controller` host capability, env-probed via
`ALGOBOOTH_REAL_MIDI_DEVICE`). Two decisions remain that the operator should own
because they involve cross-repo coordination and/or a structural axis choice.

## Decision Context

### Heterogeneous device-axis: how MIDI-hardware deferrals avoid the audio-axis device re-open loop

**Problem:** `lazy-state.py:3037` re-opens **every** `DEFERRED_REQUIRES_DEVICE.md`
feature whenever the host is a "real-device" host — but `real_device` is the
**AUDIO** axis only (`resolve_real_device` reads `$ALGOBOOTH_REAL_AUDIO_DEVICE`).
A feature whose deferred scenarios need a *different* device (MIDI controller:
`mcu-device-query-handshake-byte-observation`, `physical-servo-fader-travel`)
gets re-opened on an audio-only-real host that can never certify them, so the
route loops on "Step 9: re-open device-deferred scenarios" forever, never
advancing and blocking the `COMPLETED.md` receipt. Root cause class:
**missing-contract** — the device axis was designed for audio-device-only
deferrals; heterogeneous device types are a novel case. The harness now has the
`midi-controller` capability on the **host-capability axis** (`requires_host` /
`DEFERRED_REQUIRES_HOST.md` / `host-capability-saturated`), which expresses
"this host lacks capability X → defer cleanly" — but two things remain unsettled.

**Options:**
- **Migrate the feature to the host-capability axis (recommended, minimal).** In
  AlgoBooth (target repo — operator-coordinated): change
  `docs/features/mixer/motorized-fader-sync/` so the 2 MIDI-hardware rows defer
  via `DEFERRED_REQUIRES_HOST.md` (`requires_host: midi-controller`) instead of
  `DEFERRED_REQUIRES_DEVICE.md`, and set `ALGOBOOTH_REAL_MIDI_DEVICE=1` on a host
  with a motorized fader. Then this host defers cleanly (`host-capability-saturated`)
  and a MIDI-hardware host re-opens + completes. No further claude-config change.
- **Also make the device-axis re-open capability-aware (defense-in-depth).** In
  addition, guard `lazy-state.py:3037` so a `DEFERRED_REQUIRES_DEVICE.md` whose
  feature ALSO declares absent `requires_host` capabilities does NOT re-open
  (defers instead). Prevents a *future* mis-axised deferral from looping even if
  someone forgets to migrate. Small, mechanical, in claude-config scope.
- **Unify the axes (largest, structural).** `real-audio-device` already exists in
  BOTH the `real_device` flag and the host-capability registry — the device axis
  is a special case of the host-capability axis. Subsume `real_device` /
  `DEFERRED_REQUIRES_DEVICE.md` into `requires_host` / `DEFERRED_REQUIRES_HOST.md`
  so there is ONE mechanism and new device types never need per-axis handling.
  This is a `/spec`-sized refactor with broad blast radius (every device-deferred
  feature + the two terminals).

**Recommendation:** Do **Option 1** now (unblocks `motorized-fader-sync` the moment
it runs on a MIDI-hardware host) **plus Option 2** as cheap defense-in-depth. Defer
**Option 3** (axis unification) unless this conflation class recurs — it is recorded
as a first-occurrence structural observation in hardening Round 40; a second
occurrence trips the over-fit spin-off threshold.

### mcp-test test-pattern isolation: where to enforce single-pattern isolation for a global-shadow observable

**Problem:** `motorized-fader-sync`'s renderer reads code-driven values from a
`CodeValueShadow` keyed by `parameter_id` (global, last-write-wins). During an
`/mcp-test` cycle a stale UI-loaded pattern kept running concurrently on channel
`main` and overwrote the MCP-injected validation pattern's shadow writes, pinning
`lastEmitted14bit` constant and **false-failing** the central LFO-tracking RV row
— even though a clean single-pattern drive demonstrably produces the correct
varying sweep. The validation harness lacks deterministic single-pattern
isolation before asserting a shared-global-shadow observable. (This produced a
spurious `BLOCKED.md blocker_kind: mcp-validation retry_count: 2` on a feature
whose behavior actually works.)

**Options:**
- **/mcp-test skill setup discipline (claude-config, partial).** The `/mcp-test`
  SKILL (lives in claude-config: `repos/algobooth/.claude/skills/mcp-test/`)
  mandates a clean-runtime reset before asserting renderer-emitted state — stop
  playback, clear/replace any concurrent editor pattern, reset active editors —
  so leftover runtime state can't race the scenario. Reachable here, but relies
  on the cycle following prose.
- **Engine/scenario isolation (AlgoBooth target repo).** The deterministic engine
  (`scripts/mcp-test/`, target repo — out of harden-harness scope) adds a
  scenario-level editor/channel reset step (or a `requires`-style precondition)
  so isolation is mechanical, not prose-dependent. Stronger, but target-repo work.
- **Both.** Skill prose for immediate coverage + an engine/scenario primitive for
  the durable mechanical guarantee.

**Recommendation:** **Option 3 (both)** — add the skill-prose reset discipline now
(claude-config, mechanical) and file the engine/scenario-reset primitive as
target-repo work (AlgoBooth `scripts/mcp-test/`), since the durable fix needs
engine support harden-harness cannot author. The skill-prose half can land in a
follow-up `/harden-harness` round once the reset sequence is specified; this
NEEDS_INPUT defers the placement choice to the operator.
