# Host-Capability Declaration for Gated Features — Feature Specification

> Let a feature declare the host capabilities (binary toolchains, audio/GPU devices) its runtime validation requires, and have the state script proactively defer/skip features whose capabilities are absent on the current host — instead of each one churning through BLOCKED/SKIP/AskUserQuestion at the Step-9 mcp-test boundary.

**Status:** Final
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

- A feature whose runtime validation needs a host capability declares it on-disk in a `requires_host:` set (exact field placement = Decision 1). Each entry is a **named capability id** drawn from a small, **closed** host-probe-able vocabulary (e.g. `zimtohrli-toolchain`, `real-audio-device`, `gpu`) — see "Closed-registry vocabulary" below. The capability id is the join key between the feature's requirement and the host's inventory.
- Capability **granularity** is coarse — a named capability is present-or-absent, not version-ranged. Research (Area 3) confirms this is the dominant v1 convention across GitHub Actions, Bazel, and Nix; none use `>=`/`<` version operators. Future version-discrimination is handled by **namespacing the capability id** (`zimtohrli-v2`, `cuda-11`) — a Bazel/Nix-style suffix taxonomy, not a semantic-version solver (vN upgrade path, no engine change).
- A feature that declares **no** `requires_host:` set is ungated — identical to today's behavior (no false deferrals).
- **Composite requirements are a flat AND-set.** All declared ids must be present; the match is `set(requires_host).issubset(host_present)`. Research (Area 5) confirms flat AND-sets satisfy the overwhelming majority of build-matrix scenarios; OR-groups / optional fallbacks cause unsatisfiable-scheduling deadlocks (K8s `FailedScheduling`) and are deferred to a vN config-profile mechanism (Bazel `select()`-style), never a change to the array shape.

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
- Capability ids match `^[a-z0-9][a-z0-9-]*$` (same shape as feature-ids), drawn from the **closed registry** (below).

#### Closed-registry vocabulary (fail-fast on unknown ids)

- The capability vocabulary is a **closed registry**: a hardcoded `lazy_core` mapping `capability-id → probe-callable`. A capability id only exists if it has a probe check mapped to it. This is the natural reading of "ids defined alongside the probe" — research (Area 4) makes it load-bearing: an **open** vocabulary causes **silent infinite queue starvation** when an author (here, an LLM authoring `requires_host:`) typos an id — the feature defers forever to a capability that will never be probed-present (GitHub Actions `self-hsted` sits queued indefinitely; GitLab/Jenkins worker starvation).
- **An unregistered `requires_host:` id is a loud, immediate validation failure**, NOT a silent defer-forever. This is *forced* by the already-locked "`Complete` means fully validated / clean terminal, no false completion" invariant (Locked Decision 2 + the all-capability-gated-terminal validation row): a typo'd id that silently deferred would strand the feature un-terminated with no surfaced reason, violating that invariant. The failure routes through the existing `BLOCKED.md` path (`blocker_kind: unknown-host-capability`) naming the offending id and the registry's known ids — the operator either fixes the typo or registers a new probe. Mirrors Bazel's "No matching toolchains found" / Nix's evaluation-phase failure (fail fast at parse, never spin on an unfulfillable requirement).

### The host-capability probe

- The host's present-capability set is resolved by a new `lazy_core` helper with **injected probe callables** (so `--test` stays hermetic — same pattern `ensure_runtime` uses for its probe/restart/stale callables). Each capability id maps to a deterministic host check. **Source of truth for "what this host has" (Decision 1, resolved): a runtime host probe** — the machine answers for itself (zero operator upkeep, always reflects ground truth), generalizing the existing `$ALGOBOOTH_REAL_AUDIO_DEVICE` device probe to N checks. A declared host manifest is NOT the v1 source of truth; it remains available as a later probe-override layer if probe authoring proves heavy (reversible).
- **Probes use active invocation, not filesystem presence (research Area 2 — load-bearing on this Windows host).** A binary-capability probe MUST run the tool (`subprocess.run([tool, "--version" | "--help"])`) and check the exit code / parse stdout — it MUST NOT use `shutil.which()` / `os.path.exists()`. The canonical false-positive this guards against is the **Windows 10/11 App Execution Alias**: a zero-byte `python3.exe` / `python.exe` stub in `\WindowsApps` on `$PATH` that `which()` resolves successfully but whose invocation opens a GUI Microsoft Store prompt and silently hangs the pipeline (consuming parallel-execution limits). Stale path caches (CMake-style) are the same class of hazard. Env-var capabilities check the var; device capabilities query the device interface directly — never a bare filesystem stat.
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
| Probe uses active invocation, not `which()` | Probe a binary capability | helper invokes the tool + checks exit code; a `\WindowsApps` zero-byte alias on PATH does NOT register as present | `lazy-state.py --test` (inject an alias-stub probe callable that exits non-zero) |
| Unregistered capability id fails fast | Feature declares `requires_host: [typo-cap]` (not in registry) | loud `BLOCKED.md` (`blocker_kind: unknown-host-capability`) naming the id; NOT a silent defer-forever | `--test` fixture |
| Composite requirement is flat AND | Feature declares two caps, one present one absent | `missing` is the absent cap; subset-match defers (any miss ⇒ defer) | `--test` fixture |
| Capability miss defers proactively | Required cap absent on host, before Step-9 | probe returns the deferral action; no BLOCKED/SKIP churn; queue advances | `--test` fixture |
| Deferred feature re-opens on capability-host | Same feature, probe now reports the cap present | feature re-dispatched into runtime validation | `--test` fixture |
| All-capability-gated terminal | Every remaining feature gated on an absent cap | clean terminal (capability-saturated), not false completion | `--test` fixture |
| Parity preserved | full `--test` suites + parity audit | `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py` green | smoke/baseline run |

## Resolved by Research (Phase 3 integration — see [`RESEARCH.md`](./RESEARCH.md) + [`RESEARCH_SUMMARY.md`](./RESEARCH_SUMMARY.md))

All four Open Questions routed to Gemini are now answered; the verdicts are integrated into the baseline above. None reopened a Locked Decision.

- **Capability granularity (coarse vs fine) — RESOLVED: coarse named-presence for v1.** Confirmed dominant across GitHub Actions (exact-match strings), Bazel (subset-match, no operators), Nix (static arch strings). Versioning later via **namespaced suffix** (`zimtohrli-v2`, `cuda-11`), never a semantic-version solver. (vN upgrade path documented; no v1 engine change.)
- **Probe design conventions — RESOLVED: active-invocation sanity checks.** Probe by running the tool (`subprocess.run([tool, "--version"])`) + exit-code/stdout, NOT `which()`/`exists()`. Headline hazard: the Windows `\WindowsApps` zero-byte App-Execution-Alias false-positive (GUI Store prompt hangs the pipeline). Stale path caches are the same class. Integrated into "The host-capability probe" + a Validation Criteria row.
- **Declaration-vocabulary ownership — RESOLVED: closed registry, fail-fast on unknown id.** A hardcoded `id → probe-callable` map; an unregistered id is a loud `BLOCKED.md`, not silent defer-forever (open vocab ⇒ silent queue starvation on a typo). Integrated into "Closed-registry vocabulary." Forced by the locked clean-terminal invariant.
- **Composite/AND-OR requirements — RESOLVED: flat AND-set for v1.** `set(required).issubset(host_present)`. OR-groups cause unsatisfiable-scheduling deadlocks (K8s); deferred to a vN config-profile mechanism, never an array-shape change. Integrated into "The declaration."

### Documented vN upgrade paths (out of v1 scope)

- **Version matrices** via namespaced-suffix taxonomy (Bazel `constraint_value` / Nix naming) — no semantic-version parser.
- **OR-groups / optional capabilities** via separate config profiles (Bazel `select()`-style), not a change to the `requires_host:` array.
- **Host-manifest probe override** — leave a state-init seam to override the deterministic probe with an operator-maintained manifest (Nix-style), as an air-gapped-environment safety valve.
- **Fleet-wide deferral-starvation monitoring** — if a capability never materializes on ANY host, deferred features accumulate; v1 surfaces each deferral (notification + end-of-run flush), cross-host fleet monitoring is vN.

## Locked Decisions (operator-resolved 2026-06-20)

> These two GATE the baseline architecture and were user-authority calls research could not decide (they pick the ownership model and the pipeline behavior). Resolved by the operator on 2026-06-20 (see `NEEDS_INPUT_RESOLVED_2026-06-20.md`); the baseline narrative above reflects these.

- **Decision 1 — Source-of-truth ownership for host capabilities — RESOLVED: per-feature `requires_host:` marker + runtime host probe.** The feature's required capabilities stay declarative in a per-feature `requires_host:` marker; the host's present-capability inventory is resolved by a deterministic runtime probe (binary-on-PATH / env-var / device-enumeration, injected callables for hermetic `--test`), NOT an operator-maintained manifest. Lowest operator upkeep, always reflects ground truth, generalizes the proven `$ALGOBOOTH_REAL_AUDIO_DEVICE` device probe. A host manifest remains a later probe-override layer (reversible).
- **Decision 2 — Capability-miss action — RESOLVED: defer-to-capability-host (re-openable).** On a capability miss the script writes a capability-keyed `DEFERRED_REQUIRES_HOST.md` sentinel (carrying the missing capability ids) and advances the queue via skip-ahead; a host that provides the capability re-opens the deferred feature. This preserves the "`Complete` means fully validated" invariant across hosts and generalizes `DEFERRED_REQUIRES_DEVICE.md` — chosen over permanent skip (`SKIP_MCP_TEST.md`-class, wrong semantics: the feature IS testable elsewhere) and back-of-queue reorder (pointless — the host won't grow the toolchain mid-run, no cross-host re-open).

## Research References

- [`RESEARCH.md`](./RESEARCH.md) — Gemini deep research over GitHub Actions, Bazel, Buck2, Nix, Earthly, Kubernetes/Mesos, GitLab Runner. Five research areas (declaration conventions, probing hazards, granularity, vocabulary governance, composite requirements) + a 7-row specific-recommendations table + a v1-vs-vN blueprint + an anti-patterns table.
- [`RESEARCH_SUMMARY.md`](./RESEARCH_SUMMARY.md) — condensed mapping of each finding onto the baseline; records the two ⚖ in-cycle refinements (active-invocation probes; fail-fast on unregistered id).
- Key findings that shaped the final spec: **closed registry + fail-fast** (prevents silent queue starvation — research Area 4), **active-invocation probes** (Windows `\WindowsApps` alias false-positive — Area 2), **flat AND-set + coarse granularity** with namespaced-suffix and config-profile vN paths (Areas 3, 5). All four Open Questions resolved; both operator-Locked Decisions confirmed by prior art.
