# Host-Capability Declaration for Gated Features — Feature Specification

> Let a feature declare the host capabilities (binary toolchains, audio/GPU devices) its runtime validation requires, and have the state script proactively defer/skip features whose capabilities are absent on the current host — instead of each one churning through BLOCKED/SKIP/AskUserQuestion at the Step-9 mcp-test boundary.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-20
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)

**Depends on:**

- feature-budget-guard-and-skip-ahead — composes — Reuses the skip-ahead readiness predicate and the `independent: true` / live-queue skip-list pattern in `compute_state()`; a capability-gated head defers and skip-ahead advances onto the next ready item the same way a research-gated head does.
- unified-pipeline-orchestrator — composes — Adds a host-capability probe sibling to the toolify-framework subcommands (`--ensure-runtime` / `--gate-coverage`), reusing `lazy_core`'s injected-callable + hermetic-`--test` harness shape.
- multi-repo-concurrent-runs — soft — Any host-probe cache lives in the per-repo keyed state dir (`claude_state_dir()` / `repo_key`); the probe reads host state, never another repo's.

<!-- Decision 1 resolved (marker + runtime probe): feature-budget-guard-and-skip-ahead kind is `composes` — the capability-gated head defers and skip-ahead advances exactly as a research-gated head does. -->

---

## Executive Summary

The `/lazy-batch` pipeline already defers runtime-verification work it cannot certify on the current host along **two hard-coded axes**: the **cloud axis** (`DEFERRED_NON_CLOUD.md` — no Tauri/MCP in cloud) and the **real-audio-device axis** (`DEFERRED_REQUIRES_DEVICE.md` — keyed on the single `$ALGOBOOTH_REAL_AUDIO_DEVICE` env signal). What it has **no** mechanism for is an **arbitrary, named host capability** — a C++ toolchain (Zimtohrli `golden:report`), a GPU, a specific CLI binary. A feature whose only remaining unchecked work is a runtime-verification row requiring such a capability has nowhere to declare that requirement, and the host has no declared inventory of what it provides. So each such feature **re-discovers the gap at the Step-9 mcp-test boundary** — after the orchestrator has already specced, planned, and implemented it — and burns a BLOCKED.md / SKIP_MCP_TEST.md / AskUserQuestion churn cycle plus a manual deferral. Session `a0eae4be` (2026-06-18) is canonical: `audio-quality-analysis`, `analysis-informed-dsp-updates`, and `perceptual-audio-quality` all gate on an absent C++ Zimtohrli toolchain; related binary-host deferrals recur in `14de0c30` and `80dbeeaf`.

This feature **generalizes the existing device-axis deferral into an N-capability axis**. Two coupled pieces:

1. **A host-capability declaration** — a feature records, in machine-readable on-disk form, the set of named host capabilities its runtime validation requires (a `requires_host:` set). Absent the declaration, a feature behaves exactly as today (no gating) — safe degradation, identical to how an item without an `independent: true` marker degrades to strict-halt in `feature-budget-guard-and-skip-ahead`.

2. **A host-capability probe + match** — the state script learns which capabilities the **current host** provides (the source of that knowledge is Decision 1) and, when a feature's `requires_host:` set contains a capability the host lacks, takes a **proactive, deterministic action at pre-dispatch time** (the action is Decision 2) — generalizing `DEFERRED_REQUIRES_DEVICE.md`'s device-saturated skip so the queue advances and the feature re-opens on a host that has the capability.

Both pieces preserve the harness's "state script owns state" principle: capability presence is probed/declared from on-disk + host signals, the match is computed by `lazy_core`, and the orchestrator LLM never infers it. This is the same architectural shape as the Step-0.52 validation-readiness pre-screen (MCP tool registration) — extended from "is this tool registered?" to "does this host have this capability?".

## User Experience

The "user" is the operator running `/lazy-batch` (attended or scheduled). This is autonomous-pipeline plumbing; the user-visible surface is the run's behavior, the new on-disk declaration authors write, the deferral sentinel, and any new flag/notification.

### Declaring a required capability (feature-author / spec-author surface)

- A feature whose runtime validation needs a host capability declares it on-disk in a `requires_host:` set (exact field placement = Decision 1). Each entry is a **named capability id** drawn from a small, host-probe-able vocabulary (e.g. `zimtohrli-toolchain`, `real-audio-device`, `gpu`). The capability id is the join key between the feature's requirement and the host's inventory.
- Capability **granularity** is coarse by default — a named capability is present-or-absent, not version-ranged. (Fine-grained version/feature matching is an Open Question routed to research; v1 ships coarse named-presence.)
- A feature that declares **no** `requires_host:` set is ungated — identical to today's behavior (no false deferrals).

### What happens on a capability miss (operator surface)

- Before dispatching a feature's next runtime-verification sub-skill, the state script compares the feature's `requires_host:` set against the host's probed-present set. On a miss (≥1 required capability absent), the script takes the Decision-2 action **proactively** — the feature never reaches the Step-9 mcp-test wall, so no BLOCKED/SKIP/AskUserQuestion churn occurs.
- The deferral is **surfaced** (notification + end-of-run flush) so the operator sees the feature needs a capability-bearing host — it is deferred, not silently dropped. The notification names the feature and the missing capability id(s): `host-capability miss — <feature-id> requires <cap-id> (absent on this host); deferred to capability-host`.
- On a host that **does** provide the capability, the deferred feature re-opens and its runtime validation runs — the same re-open contract `DEFERRED_REQUIRES_DEVICE.md` already has on a real-device host.

### Cloud vs workstation

- The cloud axis (`DEFERRED_NON_CLOUD.md`) is unchanged and orthogonal — cloud already defers ALL MCP/Tauri/device work. Host-capability gating is a **workstation-axis** refinement: a workstation that lacks a specific toolchain still runs everything else. Whether the capability-miss action differs by environment is folded into Decision 2 (the recommended action is environment-agnostic and composes with both existing axes).

## Technical Design

### Where it lives

Per "state script is the source of truth," the probe + match + action live in `lazy-state.py` / `lazy_core.py`, with the `/lazy-batch` (+ `/lazy-batch-cloud`) wrappers carrying only thin dispatch/notification glue. The coupled `/lazy` ↔ `/lazy-cloud` and `/lazy-batch` ↔ `/lazy-batch-cloud` pairs (and `bug-state.py`, for parity of any shared `lazy_core` helper) update in lockstep.

### The declaration (`requires_host:`)

- A feature's required-capability set is parsed by a single `lazy_core` helper (mirroring `marker_work_branch()` / dep-block parsing): present → a set of capability ids; absent/legacy → empty set (ungated). **On-disk location (Decision 1, resolved):** a per-feature `requires_host:` marker (the requirement side stays declarative, as today); the *host inventory* side is resolved by runtime probe (below), not a manifest.
- Capability ids match `^[a-z0-9][a-z0-9-]*$` (same shape as feature-ids), drawn from a host-probe-able vocabulary defined alongside the probe.

### The host-capability probe

- The host's present-capability set is resolved by a new `lazy_core` helper with **injected probe callables** (so `--test` stays hermetic — same pattern `ensure_runtime` uses for its probe/restart/stale callables). Each capability id maps to a deterministic host check (binary-on-PATH, env-var-set, device-enumeration). **Source of truth for "what this host has" (Decision 1, resolved): a runtime host probe** — the machine answers for itself (zero operator upkeep, always reflects ground truth), generalizing the existing `$ALGOBOOTH_REAL_AUDIO_DEVICE` device probe to N checks. A declared host manifest is NOT the v1 source of truth; it remains available as a later probe-override layer if probe authoring proves heavy (reversible).
- The probe result is cacheable in the per-repo keyed state dir (`claude_state_dir()`); whether to cache for the run or re-probe per cycle is a mechanical-internal choice (auto-accepted: cache per run, re-probe on a new run marker — cheapest correct option).

### The match + action

- In `compute_state()` queue selection, before dispatching the current feature's next runtime-verification sub-skill, compute `missing = feature.requires_host - host.present`. On non-empty `missing`, take the **Decision-2 action (resolved): defer-to-capability-host** — write a capability-keyed `DEFERRED_REQUIRES_HOST.md` sentinel carrying the missing capability ids (re-openable; generalizing `DEFERRED_REQUIRES_DEVICE.md`), and emit a probe field the orchestrator translates into a notification + a live-queue skip, reusing the `feature-budget-guard-and-skip-ahead` skip-list + skip-ahead plumbing. The deferral preserves the "`Complete` means fully validated" invariant: the feature is testable, just not on this host, so it re-opens on a host that provides the capability rather than being permanently waived (skip) or pointlessly retried at the same wall (back-of-queue).
- **Fold into Step 0.52 vs a distinct pre-screen stage** is a mechanical-internal choice (auto-accepted: a distinct, capability-specific match in `compute_state` reusing the skip-ahead plumbing — keeps the advisory MCP-tool pre-screen and the hard capability gate separate-concern; Step 0.52 stays advisory-only).

### Reused infrastructure (no new code where it exists)

| Need | Existing mechanism reused |
|------|---------------------------|
| Per-repo probe-cache state | `lazy_core.claude_state_dir()` / `repo_key` (multi-repo-concurrent-runs) |
| Live-queue defer + skip-ahead | `feature-budget-guard-and-skip-ahead` skip-list + readiness predicate |
| Re-open-on-capability-host sentinel | `DEFERRED_REQUIRES_HOST.md` (new, capability-keyed) — generalizes the `DEFERRED_REQUIRES_DEVICE.md` device-axis re-open pattern |
| Hermetic injected-callable probe harness | `lazy_core.ensure_runtime`'s injected probe/restart/stale callables |
| Pre-screen-at-curation-time framing | Step 0.52 validation-readiness pre-screen (`validation_readiness.py`) |

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown (authored after the baseline is locked and research integrated).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| `requires_host:` parsed to a capability set | Feature declares `requires_host: [zimtohrli-toolchain]` | `lazy_core` helper returns the set; absent ⇒ empty | `lazy-state.py --test` fixture |
| Ungated feature unaffected | Feature with no `requires_host:` | byte-identical to baseline (no deferral) | `--test` baseline-regression fixture |
| Host probe is hermetic | Inject a probe stub | helper returns the injected present-set; no real binary/device touched | `lazy-state.py --test` |
| Capability miss defers proactively | Required cap absent on host, before Step-9 | probe returns the deferral action; no BLOCKED/SKIP churn; queue advances | `--test` fixture |
| Deferred feature re-opens on capability-host | Same feature, probe now reports the cap present | feature re-dispatched into runtime validation | `--test` fixture |
| All-capability-gated terminal | Every remaining feature gated on an absent cap | clean terminal (capability-saturated), not false completion | `--test` fixture |
| Parity preserved | full `--test` suites + parity audit | `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py` green | smoke/baseline run |

## Open Questions (research-answerable — routed to Phase 2 RESEARCH_PROMPT.md)

These are deferred into the Gemini research prompt, NOT lifted to the operator (they ask "what do similar systems do" / "what is the convention," which research can answer):

- **Capability granularity (coarse vs fine).** v1 ships coarse named-presence. Do CI/build-matrix systems (GitHub Actions runner labels, Bazel `--host_platform` constraints, Nix `meta.platforms`) version-range or feature-flag host capabilities in a way worth adopting later? Is a `name@>=version` form worth a Phase-N upgrade?
- **Probe design conventions.** How do mature task runners (Bazel toolchain resolution, Buck2, Earthly, Nix) probe + declare host/build capabilities, and what false-positive/staleness hazards (a binary on PATH but broken; a cached probe gone stale) should the probe guard against?
- **Declaration vocabulary ownership.** Should the capability-id vocabulary be open (any string the author coins) or a closed registry validated against the probe's known checks? What do similar declarative-requirement systems do to prevent typo'd / never-probed capability ids?
- **Composite/AND-OR requirements.** Is a flat AND-set of required capabilities sufficient, or do real features need OR-groups / optional capabilities ("GPU OR a 4-core CPU fallback")?

## Locked Decisions (operator-resolved 2026-06-20)

> These two GATE the baseline architecture and were user-authority calls research could not decide (they pick the ownership model and the pipeline behavior). Resolved by the operator on 2026-06-20 (see `NEEDS_INPUT_RESOLVED_2026-06-20.md`); the baseline narrative above reflects these.

- **Decision 1 — Source-of-truth ownership for host capabilities — RESOLVED: per-feature `requires_host:` marker + runtime host probe.** The feature's required capabilities stay declarative in a per-feature `requires_host:` marker; the host's present-capability inventory is resolved by a deterministic runtime probe (binary-on-PATH / env-var / device-enumeration, injected callables for hermetic `--test`), NOT an operator-maintained manifest. Lowest operator upkeep, always reflects ground truth, generalizes the proven `$ALGOBOOTH_REAL_AUDIO_DEVICE` device probe. A host manifest remains a later probe-override layer (reversible).
- **Decision 2 — Capability-miss action — RESOLVED: defer-to-capability-host (re-openable).** On a capability miss the script writes a capability-keyed `DEFERRED_REQUIRES_HOST.md` sentinel (carrying the missing capability ids) and advances the queue via skip-ahead; a host that provides the capability re-opens the deferred feature. This preserves the "`Complete` means fully validated" invariant across hosts and generalizes `DEFERRED_REQUIRES_DEVICE.md` — chosen over permanent skip (`SKIP_MCP_TEST.md`-class, wrong semantics: the feature IS testable elsewhere) and back-of-queue reorder (pointless — the host won't grow the toolchain mid-run, no cross-host re-open).

## Research References

Pre-Gemini draft baseline. The Phase 2 `RESEARCH_PROMPT.md` will probe the Open Questions above: host/build-capability declaration + probing conventions in CI and build systems (GitHub Actions, Bazel/Buck2/Nix/Earthly), coarse-vs-fine capability granularity, declaration-vocabulary governance, and composite-requirement shapes.
