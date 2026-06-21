# Host-capability declaration and probing for a gated autonomous-build pipeline

## Research Question

We are designing a **host-capability declaration + probe** mechanism for an autonomous software-build pipeline (a Claude Code "lazy-batch" orchestrator that walks a feature queue, specs/plans/implements each feature, then runtime-validates it). The pipeline already defers runtime-verification work it cannot certify on the current host along two hard-coded axes (a cloud axis: no Tauri/MCP in cloud; a real-audio-device axis: keyed on a single env var). We want to **generalize the single-device axis into an N-capability axis**: a feature declares the set of named host capabilities its runtime validation requires (a `requires_host:` set of capability ids), a deterministic probe learns what the current host provides, and on a miss the pipeline proactively defers the feature to a capability-bearing host instead of churning through BLOCKED/SKIP/manual-intervention at the validation boundary.

The core architecture is locked. What we need from research is **convention and prior-art guidance** on four open questions so we adopt proven patterns rather than reinvent them, and so the v1 design leaves clean upgrade paths. Specifically: how mature CI/build-matrix and task-runner systems (GitHub Actions, Bazel, Buck2, Nix, Earthly, and similar) declare, probe, version, and govern host/build capabilities — and what failure modes (false positives, staleness, typo'd-never-probed ids, composite requirements) those systems guard against.

## Context

- **System type:** an autonomous, deterministic-state-machine build pipeline. A Python state script (`lazy-state.py` / shared `lazy_core.py`) owns ALL state; the LLM orchestrator never infers state — it dispatches one sub-skill per cycle based on what the state script computes. Capability presence MUST therefore be computed deterministically by the state script from on-disk declarations + host probes, never inferred by the model.
- **Existing precedent we are generalizing:** a `DEFERRED_REQUIRES_DEVICE.md` sentinel keyed on a single env signal (`$ALGOBOOTH_REAL_AUDIO_DEVICE`). A feature needing a real audio device defers when the host lacks one and **re-opens** on a host that has it. We want the same re-openable defer semantics for an arbitrary, named capability set.
- **Probe constraints:** each capability id maps to a deterministic host check — a binary-on-PATH test, an env-var-set test, or a device enumeration. The probe must be **hermetic under test** (injected probe callables, so the unit-test suite touches no real binary/device). Probe results are cacheable in a per-repo keyed state dir.
- **Declaration constraints:** capability ids match `^[a-z0-9][a-z0-9-]*$` (same shape as feature ids). A feature that declares no `requires_host:` set is ungated — byte-identical to today's behavior (no false deferrals). v1 ships **coarse named-presence** (a capability is present-or-absent, not version-ranged).
- **Canonical motivating case:** three features (`audio-quality-analysis`, `analysis-informed-dsp-updates`, `perceptual-audio-quality`) all gate on an absent C++ "Zimtohrli" toolchain. Each currently re-discovers the gap at the validation wall after being fully specced/planned/implemented, burning a churn cycle plus a manual deferral. The goal is to defer them proactively at pre-dispatch time.

## Baseline Spec Summary (locked decisions)

- **Source-of-truth ownership (locked):** the feature's required capabilities stay **declarative** in a per-feature `requires_host:` marker; the host's present-capability inventory is resolved by a **runtime probe** (binary-on-PATH / env-var / device-enumeration), NOT an operator-maintained manifest. A host manifest remains a possible later probe-override layer (reversible).
- **Capability-miss action (locked):** on a miss, write a capability-keyed `DEFERRED_REQUIRES_HOST.md` sentinel carrying the missing ids and advance the queue (skip-ahead). A host that provides the capability **re-opens** the deferred feature. Chosen over permanent skip (wrong semantics — the feature IS testable elsewhere) and over back-of-queue reorder (pointless — the host won't grow the toolchain mid-run).
- **v1 granularity (locked):** coarse named-presence. Whether to add version/feature matching later is one of the open research questions below.

## Research Areas

1. **Capability-declaration conventions in CI/build systems.** How do GitHub Actions runner labels, Bazel platform `constraint_setting`/`constraint_value` + toolchain resolution, Buck2 platforms/constraints, Nix `meta.platforms` / `meta.badPlatforms`, and Earthly host/platform selection let a job declare "I require host capability X"? What is the *shape* of the declaration (flat label set, key/value constraints, platform tuples, feature flags) and what made each shape succeed or fail in practice?
2. **Host/toolchain probing conventions and hazards.** How do mature task runners (Bazel toolchain resolution, Buck2, Earthly, Nix) **probe and discover** host/build capabilities vs. require explicit declaration? What concrete false-positive and staleness hazards do they guard against — e.g. a binary present on PATH but broken/wrong-arch, a cached capability result gone stale, a probe that passes in CI but fails at runtime? What mitigations (version pinning, checksum/sanity invocation, cache invalidation keys) are standard?
3. **Capability granularity — coarse named-presence vs. version-ranged / feature-flagged.** Is coarse present-or-absent sufficient in practice, or do real build matrices need `name@>=version` ranges or feature flags (e.g. "CUDA >= 11", "Python 3.11+ with sqlite")? What is the migration cost of starting coarse and adding version constraints later, and which systems' upgrade paths from coarse→fine are worth imitating?
4. **Declaration-vocabulary governance.** Should the capability-id vocabulary be **open** (any string an author coins) or a **closed registry** validated against the probe's known checks? How do declarative-requirement systems prevent typo'd / never-probed capability ids (a requirement that can never be satisfied because nothing probes for it)? What governance patterns (linting against a known-id set, a registry file, fail-loud-on-unknown-id) do similar systems use?
5. **Composite / AND-OR / optional requirements.** Is a flat AND-set of required capabilities sufficient for real features, or do they need OR-groups and optional capabilities (e.g. "GPU OR a 4-core CPU fallback", "optionally a real audio device")? How do CI matrix systems and build-constraint languages express disjunctive or optional host requirements, and is the added expressiveness worth the complexity for a v1?

## Specific Questions

1. For each of GitHub Actions (runner labels), Bazel (constraints + toolchain resolution), Buck2, Nix (`meta.platforms`), and Earthly: what is the exact declaration shape for "this job/target requires host capability X," and which shape best fits a flat per-feature `requires_host:` id set?
2. What are the documented false-positive and staleness failure modes of "binary on PATH" / "device present" style probes, and what sanity-check or cache-invalidation patterns are standard mitigations?
3. Is coarse named-presence (no versions) a defensible v1, and what is the lowest-friction upgrade path to `name@>=version` if we later need it? Which system's coarse→fine evolution is the best model?
4. Open vocabulary vs. closed registry for capability ids — what do similar declarative-requirement systems do, and what is the recommended guard against a typo'd id that nothing ever probes for (so the requirement silently never satisfies)?
5. Flat AND-set vs. OR-groups/optional capabilities — do real-world host-requirement declarations need disjunction/optionality, or is flat-AND sufficient for the overwhelming majority of cases? If disjunction is needed, what is the simplest expression that doesn't over-engineer v1?
6. Are there cross-host **re-open / defer-and-retry** patterns in CI/build systems analogous to our "defer to a capability-bearing host, re-open when the capability appears" — e.g. matrix jobs skipped-then-retried on a labeled runner — and what scheduling pitfalls (starvation, never-scheduled jobs) do they warn about?
7. What naming conventions do these systems use for capability/constraint ids (casing, namespacing, vendor prefixes), and is there a convention worth adopting for our `^[a-z0-9][a-z0-9-]*$` id space?

## Output Format Request

Provide structured findings with:
- One section per Research Area (1–5 above), each opening with a 2–3 sentence direct answer, then the supporting prior-art evidence (named system + concrete mechanism).
- A comparison table of the five systems' declaration shapes (system | declaration mechanism | granularity | open vs. governed vocabulary | disjunction support).
- For each of the seven Specific Questions, an explicit recommendation (adopt / defer-to-vN / skip) with a one-line justification grounded in the prior art.
- A short "v1 vs. later" list: which patterns to adopt now (coarse, flat-AND, runtime probe) and which to leave as documented upgrade paths (versioning, OR-groups, closed registry, host manifest override).
- Call out any failure modes or anti-patterns we should explicitly guard against in v1, with the system that demonstrates each.
