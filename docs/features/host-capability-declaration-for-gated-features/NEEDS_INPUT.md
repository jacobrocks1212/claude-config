---
kind: needs-input
feature_id: host-capability-declaration-for-gated-features
written_by: spec
decisions:
  - Source-of-truth ownership for host capabilities (how feature requirements and host inventory are each known)
  - Capability-miss action (defer-to-capability-host vs permanent skip vs defer-to-back-of-queue)
date: 2026-06-20
next_skill: spec
---

# /spec --batch — Needs Input

## Decision Context

This feature lets a pipeline feature declare the host capabilities (a C++ toolchain, a real audio device, a GPU) its runtime validation needs, so `/lazy-batch` proactively defers/skips features whose capabilities the current host lacks — instead of each one discovering the gap at the Step-9 mcp-test boundary and burning a BLOCKED/SKIP/AskUserQuestion churn cycle. The harness already does exactly this along two hard-coded axes: the **cloud axis** (`DEFERRED_NON_CLOUD.md`) and the **real-audio-device axis** (`DEFERRED_REQUIRES_DEVICE.md`, keyed on the single `$ALGOBOOTH_REAL_AUDIO_DEVICE` env var). This feature generalizes that into an **N named-capability axis**. Two decisions gate the baseline architecture; both are operator-authority calls (they pick the ownership model and the pipeline behavior) that research cannot decide.

### 1. Source-of-truth ownership for host capabilities (how feature requirements and host inventory are each known)

**Problem:** Two things must be knowable on-disk for the match to be deterministic: (a) which capabilities a *feature* requires, and (b) which capabilities the *current host* provides. The stub's first open question — "Where do host capabilities get declared — a host-local manifest, per-repo config, or runtime probing — and who owns keeping it current?" — is exactly this. The answer sets the entire architecture: it decides whether the harness *probes* the host (zero operator upkeep, but probe-design + staleness risk) or *trusts a declared manifest* (operator-maintained, can drift from reality but is auditable and fast). This is product-behavior because it changes what the operator must author/maintain and how the pipeline behaves when host reality and declared state disagree.

**Options:**
- **Per-feature `requires_host:` marker + runtime host probe (Recommended)** — The feature declares its required capability ids in a `requires_host:` set; the host's present set is resolved by a deterministic runtime probe (binary-on-PATH / env-var / device-enumeration), with injected callables so `--test` stays hermetic. Pros: zero operator upkeep for host inventory (the machine answers for itself), always reflects ground truth, and directly mirrors the existing `DEFERRED_REQUIRES_DEVICE.md` device probe (`$ALGOBOOTH_REAL_AUDIO_DEVICE`) generalized to N checks. Cons: each capability id needs a probe check authored; a probe can false-positive (binary on PATH but broken). Reversible — a host manifest can be layered on later as a probe override. Lowest operator burden, strongest fidelity, smallest new concept.
- **Per-feature `requires_host:` marker + host-local manifest the operator maintains** — Feature requirements as today, but the host's present set comes from an operator-authored manifest file (e.g. `~/.claude/host-capabilities.json`) rather than a probe. Pros: no probe-check authoring; fast; fully auditable; the operator declares ground truth explicitly. Cons: drifts from reality the moment a toolchain is installed/removed and the operator forgets to update it (the exact "who owns keeping it current?" hazard the stub flagged); a stale manifest re-introduces false deferrals/false-passes. Higher operator burden.
- **Both feature requirement and host inventory as static manifests (no runtime probe)** — Both sides fully declarative: a per-repo (or per-host) static manifest. Pros: simplest to implement (pure file reads, trivially hermetic); fully auditable. Cons: maximal drift risk on the host side AND requires the feature requirement to be hand-maintained too; no ground-truth check anywhere. Most brittle.

**Recommendation:** Per-feature `requires_host:` marker + runtime host probe — it has the lowest operator burden, always reflects ground truth, generalizes the proven device-probe pattern, and keeps a host manifest available as a later override if probe authoring proves heavy.

### 2. Capability-miss action (defer-to-capability-host vs permanent skip vs defer-to-back-of-queue)

**Problem:** When a feature requires a capability the current host lacks, what does the pipeline DO? The harness already distinguishes three established outcomes (per `user/scripts/CLAUDE.md` "Skip ≠ defer"): **defer** = re-openable later on the right host (`DEFERRED_REQUIRES_DEVICE.md`); **skip** = permanent waiver, untestable anywhere (`SKIP_MCP_TEST.md`); **back-of-queue** = run-scoped reorder, retried this run (`feature-budget-guard-and-skip-ahead`). The stub's third open question asks exactly this ("defer-to-back-of-queue, mark deferred-non-host, or skip"). This is product-behavior because it changes whether the feature ever reaches `Complete` on this host, whether a different host re-opens it, and what the operator sees.

**Options:**
- **Defer-to-capability-host — re-openable, generalizing `DEFERRED_REQUIRES_DEVICE.md` (Recommended)** — Write a capability-keyed deferral sentinel (e.g. `DEFERRED_REQUIRES_HOST.md` carrying the missing capability ids); the host becomes capability-saturated for that feature, the queue advances (skip-ahead), and a host that DOES provide the capability re-opens exactly those deferred scenarios. Pros: semantically correct — the feature IS testable, just not here; preserves the invariant that `Complete` always means fully validated (no false completion on a capability-poor host); directly generalizes the existing, proven device axis; composes with the cloud axis. Cons: needs a new sentinel kind + a re-open path (modest, but the device-axis code is the template). Reversible. This is the option that matches the established "defer ≠ skip" contract.
- **Skip — permanent waiver (`SKIP_MCP_TEST.md`-class)** — Treat a capability miss as "won't validate," write a skip waiver, mark the feature validated-by-waiver. Pros: simplest; no re-open machinery. Cons: WRONG semantics — the feature is testable on the right host, so a permanent skip silently lets it reach `Complete` un-validated on a capability-poor host, exactly the false-pass the harness's skip/defer split exists to prevent. Only correct for genuinely-untestable-anywhere capabilities, which is a different (operator-granted) case.
- **Defer-to-back-of-queue — run-scoped reorder (`feature-budget-guard` pattern)** — Move the feature to the live-queue tail this run; retry it later in the same run. Pros: reuses the budget-guard skip-list directly; no new sentinel. Cons: pointless for a capability miss — the host won't grow the toolchain mid-run, so the feature just hits the same wall at the tail; no cross-host re-open, so it never completes on a capability-poor host. Right tool for a transient/stubborn feature, wrong tool for a stable host-capability gap.

**Recommendation:** Defer-to-capability-host — it is the only option that preserves the "`Complete` means fully validated" invariant across hosts, matches the established defer-≠-skip contract, and generalizes the proven `DEFERRED_REQUIRES_DEVICE.md` device axis rather than inventing new semantics.
