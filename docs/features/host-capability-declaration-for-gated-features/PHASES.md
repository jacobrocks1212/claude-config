# Implementation Phases — Host-Capability Declaration for Gated Features

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — `claude-config` has no Tauri/MCP server (`.claude/skill-config/capabilities.txt` declares no `mcp`; Step-9 MCP gate is operator-exempt). Per the mcp-testing untestable class this is build-tooling / state-machine code; validation is the repo's own `pytest` + `lint-skills` + `project-skills` + `lazy_parity_audit` suite (`.claude/skill-config/quality-gates.md`).

## Cross-feature Integration Notes

Phase-level dependencies extracted from each `**Depends on:**` upstream. The SPEC's dep block declares only `composes`/`soft` kinds (no `hard`), so there is no upstream PHASES.md whose contracts gate these phases — but the composed mechanisms are reused verbatim and named per phase:

- **feature-budget-guard-and-skip-ahead (kind=composes):** the capability-gated head defers and skip-ahead advances exactly as a research-gated head does. Phase 5 reuses the existing `skip_ahead_ready` predicate, the `gated_ids`/`_GATED_HEADS` skip-list bookkeeping, and the device-saturated-skip + `device-queue-exhausted` terminal shape in `lazy-state.py::compute_state()` (lines ~1497-1524 device skip; ~1839-1853 terminal). No change to that feature's code — the new capability gate is a sibling branch following the SAME pattern.
- **unified-pipeline-orchestrator (kind=composes):** the host-capability probe is a sibling to the toolify-framework `lazy_core` subcommands, reusing `lazy_core.ensure_runtime`'s injected-callable + hermetic-`--test` harness shape (`lazy_core.py` line ~6457). Phase 3's probe helper mirrors that injection pattern (probe callables passed in, real probes bound only in production).
- **multi-repo-concurrent-runs (kind=soft):** the probe cache (Phase 3) lives in the per-repo keyed state dir via `lazy_core.claude_state_dir()` (line ~7773) / `repo_key()` (line ~6153) — reads host state, never another repo's.

---

### Phase 1: `requires_host:` declaration parsing + closed-registry constant

**Scope:** Add the deterministic read of a feature's required-capability set and the closed-registry vocabulary constant — the pure, I/O-free foundation every later phase consumes. No probe, no match, no action yet. Mirrors `parse_independent_marker` (two-source read, safe-default-empty) and the `_INDEPENDENT_MARKER_*` constant block in `lazy_core.py`.

**Deliverables:**
- [ ] `lazy_core._HOST_CAPABILITY_REGISTRY` — the closed registry constant: a mapping `capability-id → probe-callable-key` (the callable wiring lands in Phase 3; Phase 1 defines the id vocabulary as the dict's keys). Seed with the SPEC's named v1 capabilities (`real-audio-device`, plus at least one binary-toolchain id e.g. `zimtohrli-toolchain`, and `gpu`). Ids match `^[a-z0-9][a-z0-9-]*$` (asserted at module load).
- [ ] `lazy_core.parse_requires_host(spec_text, queue_entry) -> set[str]` — two-source read (SPEC frontmatter + `queue.json` entry) returning the declared capability-id set; absent/legacy ⇒ empty set (ungated). Frontmatter scan reuses the exact fenced-block walk shape of `parse_independent_marker`. A list/array value and a comma/space string both parse to a set (tolerant input, same as the independent-marker coercion).
- [ ] `lazy_core.unknown_capability_ids(required: set[str]) -> set[str]` — pure helper returning `required - set(_HOST_CAPABILITY_REGISTRY)` (the fail-fast input for Phase 4).
- [ ] Tests: `test_lazy_core.py` — parse from SPEC frontmatter only; from queue entry only; from both (union); absent ⇒ empty set; legacy `requires_host` absent byte-identical; id-shape regex rejects a malformed id; `unknown_capability_ids` returns the typo'd id; registry-keys-are-shape-valid assertion. Register each in `_TESTS` (dead-coverage guard).

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` runs and the new parse/registry tests pass — `parse_requires_host` returns `{zimtohrli-toolchain}` for a fixture SPEC declaring it and `set()` for a SPEC without the field.

<!-- verification-only -->
**Runtime Verification** *(checked by the pytest suite — no app runtime in this repo):*
- [ ] `python -m pytest user/scripts/test_lazy_core.py -q` green including the new parse + registry cases. <!-- verification-only -->

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` - new `_HOST_CAPABILITY_REGISTRY` constant block + `parse_requires_host` / `unknown_capability_ids` helpers, sited beside the `_INDEPENDENT_MARKER_*` / `parse_independent_marker` block (~line 9838).
- `user/scripts/test_lazy_core.py` - new test functions + `_TESTS` registrations.

**Testing Strategy:** Pure-function unit tests over hand-built `spec_text` strings and `queue_entry` dicts — no filesystem, no probe. Characterize the safe-default-empty (ungated) path explicitly so the baseline-regression invariant ("no `requires_host:` ⇒ identical to today") is locked at the parse layer.

**Integration Notes for Next Phase:**
- The registry's KEYS are the closed vocabulary; Phase 3 fills each key's VALUE with a real probe callable. Keep the constant the single source of truth for "what ids exist" — Phase 4's fail-fast and Phase 5's match both read it.
- `parse_requires_host` returns a `set` (not a list) so the Phase-5 subset match is `required.issubset(present)` directly.

---

### Phase 2: Active-invocation probe primitives (hermetic, injected)

**Scope:** Build the deterministic per-capability host checks as injected callables — the active-invocation primitive that runs a tool and checks its exit code (NEVER `shutil.which()`/`os.path.exists()`), plus the env-var and device-probe variants. This phase delivers the probe *callables* in isolation; wiring them into a host-present-set resolver is Phase 3. Modeled on `ensure_runtime`'s injected `probe`/`restart`/`stale_check` callable contract.

**Deliverables:**
- [ ] `lazy_core.probe_binary_capability(argv, *, run=None) -> bool` — runs `argv` (e.g. `[tool, "--version"]`) via an injected `run` callable (default a real `subprocess.run` with a short timeout, `capture_output`, no shell) and returns `True` iff exit code 0. NEVER consults the filesystem for presence. The injected `run` is what keeps `--test` hermetic.
- [ ] `lazy_core.probe_env_capability(var_name, *, environ=None) -> bool` — truthy iff the env var is set to a non-falsy value (reuses the existing `_FALSY_ENV_VALUES` set), generalizing the `$ALGOBOOTH_REAL_AUDIO_DEVICE` device read. `environ` injectable for `--test`.
- [ ] An explicit comment + test asserting the `\WindowsApps` zero-byte App-Execution-Alias false-positive is NOT registered: an injected `run` stub that simulates the alias (exit code != 0 / would-hang) ⇒ `probe_binary_capability` returns `False`. This is the load-bearing Windows-host hazard from research Area 2.
- [ ] Tests: `test_lazy_core.py` — binary probe exit-0 ⇒ True; exit-nonzero ⇒ False; alias-stub ⇒ False; env probe set/unset/falsy-value; injected `run`/`environ` never touch the real host. Register in `_TESTS`.

**Minimum Verifiable Behavior:** `probe_binary_capability(["x"], run=lambda *a, **k: _FakeCompleted(returncode=0))` returns `True` and `run=lambda ...: _FakeCompleted(returncode=1)` returns `False`, asserted under `python user/scripts/test_lazy_core.py`.

<!-- verification-only -->
**Runtime Verification** *(checked by the pytest suite):*
- [ ] `python -m pytest user/scripts/test_lazy_core.py -q` green including the alias-false-positive guard test. <!-- verification-only -->

**Prerequisites:**
- Phase 1: the `_HOST_CAPABILITY_REGISTRY` keys define which probe primitives are needed.

**Files likely modified:**
- `user/scripts/lazy_core.py` - `probe_binary_capability` / `probe_env_capability` helpers (sited near `ensure_runtime` / `_default_runtime_probe`, reusing `_FALSY_ENV_VALUES`).
- `user/scripts/test_lazy_core.py` - probe-primitive tests incl. the alias-false-positive guard.

**Testing Strategy:** Inject a fake `run` returning a `subprocess.CompletedProcess`-shaped object; assert the active-invocation contract (exit-code gate) and the explicit anti-`which()` behavior. No real binary is ever invoked in `--test`.

**Integration Notes for Next Phase:**
- Phase 3 binds each registry key to one of these primitives (production wiring) and exposes a `host_present_set` resolver that takes the SAME injected callables so `compute_state` `--test` fixtures stay hermetic.
- Keep production `subprocess.run` bounded by a short timeout — a probe that hangs is the failure mode the active-invocation design exists to prevent.

---

### Phase 3: Host-present-set resolver + per-run probe cache

**Scope:** Compose the Phase-2 primitives into a single `lazy_core` resolver that returns the host's present-capability set, bound to the closed registry, with injected callables for hermetic `--test`; cache the result in the per-repo keyed state dir for the run-marker's lifetime (re-probe on a new run). This is the `host.present` side of the Phase-5 match.

**Deliverables:**
- [ ] `lazy_core.host_present_capabilities(*, probes=None, cache=True) -> set[str]` — for each registry id, evaluates its bound probe callable; returns the set of present ids. `probes` injects a `{capability-id: callable}` map (default: the real production bindings from the registry) so `--test` passes a stub map and no real host is touched. Mirrors `ensure_runtime`'s "real defaults bound only when callables are None" pattern.
- [ ] Per-run cache: write/read the present-set as JSON under `lazy_core.claude_state_dir()` keyed to the current run marker (cache-per-run, re-probe on a new run marker — the auto-accepted mechanical-internal choice from SPEC "The host-capability probe"). Cache miss / no marker ⇒ probe fresh. Non-destructive read.
- [ ] Production registry binding: each `_HOST_CAPABILITY_REGISTRY` id maps to a concrete Phase-2 primitive (`real-audio-device` → `probe_env_capability("ALGOBOOTH_REAL_AUDIO_DEVICE")`; `zimtohrli-toolchain` → `probe_binary_capability([...])`; `gpu` → a documented probe). Keep AlgoBooth-specific argv in the config-overridable dict pattern, not hard-coded into the resolver flow.
- [ ] Tests: `test_lazy_core.py` — resolver with injected all-present / all-absent / mixed probe maps; cache writes once per run + re-probes on a new run marker; no-marker path probes fresh; hermetic (injected probes only). Register in `_TESTS`.

**Minimum Verifiable Behavior:** `host_present_capabilities(probes={"gpu": lambda: True, "zimtohrli-toolchain": lambda: False, ...})` returns exactly `{gpu, ...}` (the True-valued ids), asserted under `python user/scripts/test_lazy_core.py`.

<!-- verification-only -->
**Runtime Verification** *(checked by the pytest suite):*
- [ ] `python -m pytest user/scripts/test_lazy_core.py -q` green including resolver + cache cases. <!-- verification-only -->

**Prerequisites:**
- Phase 1: the registry (which ids to probe).
- Phase 2: the probe primitives the resolver calls.

**Files likely modified:**
- `user/scripts/lazy_core.py` - `host_present_capabilities` resolver + per-run cache read/write (reuses `claude_state_dir()` / run-marker read).
- `user/scripts/test_lazy_core.py` - resolver + cache tests.

**Testing Strategy:** Inject a stub `probes` map; assert the present-set is exactly the True-valued subset. Cache tests use the `LAZY_STATE_DIR`-override path (the hermetic-test seam) so no `~/.claude/state/` is touched; assert one probe per run and a re-probe after a new run marker.

**Integration Notes for Next Phase:**
- `compute_state` (Phase 5) calls `host_present_capabilities` ONCE per probe and diffs against each candidate's `requires_host` set. Pass the resolver's result down rather than re-probing per feature.
- The cache key must include the run-marker identity so a `--test` fixture without a marker re-probes deterministically.

---

### Phase 4: Fail-fast on unregistered capability id (`BLOCKED.md`)

**Scope:** Wire the closed-registry fail-fast: a `requires_host:` id not in `_HOST_CAPABILITY_REGISTRY` is a loud, immediate `BLOCKED.md` (`blocker_kind: unknown-host-capability`) naming the offending id and the registry's known ids — NEVER a silent defer-forever. Forced by the locked clean-terminal invariant. This branch fires in `compute_state` BEFORE the Phase-5 match (a typo can never be "missing on this host" — it can never be present anywhere).

**Deliverables:**
- [ ] In `lazy-state.py::compute_state()`, for the current feature compute `unknown = lazy_core.unknown_capability_ids(parse_requires_host(...))`; on non-empty `unknown`, route through the existing `BLOCKED.md` path with `blocker_kind: unknown-host-capability`, a body naming the offending id(s) and the sorted registry ids. Reuse the existing blocker-write/terminal plumbing (do NOT invent a new sentinel).
- [ ] `lazy_core` shared helper if the body/message formatting is non-trivial (so `bug-state.py` parity in Phase 6 is a one-line mirror). Keep the actual blocker authoring in the existing path.
- [ ] Tests: `lazy-state.py --test` fixture — a feature declaring `requires_host: [typo-cap]` ⇒ `terminal_reason: blocked` / a `BLOCKED.md` with `blocker_kind: unknown-host-capability` naming `typo-cap` and the known ids; NOT a silent defer. A feature with only registered ids does NOT trip this branch. Add the fixture; regenerate the byte-pinned `tests/baselines/lazy-state-test-baseline.txt` via the `_normalize_smoke_output` helper (never by hand).

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` passes with a new fixture asserting a `typo-cap` feature halts `blocked` with `blocker_kind: unknown-host-capability`.

<!-- verification-only -->
**Runtime Verification** *(checked by the `--test` smoke suite):*
- [ ] `python user/scripts/lazy-state.py --test` green; baseline file regenerated through `_normalize_smoke_output`. <!-- verification-only -->

**Prerequisites:**
- Phase 1: `unknown_capability_ids` + the registry.

**Files likely modified:**
- `user/scripts/lazy-state.py` - the unknown-id fail-fast branch in `compute_state()` (before the capability match), reusing the existing BLOCKED terminal.
- `user/scripts/lazy_core.py` - optional shared blocker-body formatter (for Phase-6 parity).
- `user/scripts/test_lazy_core.py` and/or `lazy-state.py` in-file fixtures + `tests/baselines/lazy-state-test-baseline.txt`.

**Testing Strategy:** A `--test` fixture builds a feature dir with a `requires_host: [typo-cap]` SPEC and asserts the computed terminal is `blocked` with the named `blocker_kind`. A second fixture (only registered ids) asserts the branch does NOT fire — guarding against an over-broad fail-fast.

**Integration Notes for Next Phase:**
- Fail-fast MUST precede the Phase-5 match: an unregistered id has no probe, so it could never be "present" and would otherwise silently defer forever (the exact starvation hazard research Area 4 names).
- The `BLOCKED.md` write must land on the run's work branch (the write-time stray-branch hook already enforces this) — no new sentinel name, so the existing canonical-blocker hooks cover it.

---

### Phase 5: Capability match + defer-to-capability-host action + terminal

**Scope:** The behavioral core. In `compute_state` queue selection, before dispatching a feature's next runtime-verification sub-skill, compute `missing = feature.requires_host - host.present`; on non-empty `missing`, write a capability-keyed `DEFERRED_REQUIRES_HOST.md` sentinel (carrying the missing ids), record the skip, and advance the queue via the existing skip-ahead plumbing. Add the `host-capability-saturated` clean terminal. Generalizes the `DEFERRED_REQUIRES_DEVICE.md` device-saturated skip + `device-queue-exhausted` terminal.

**Deliverables:**
- [ ] `DEFERRED_REQUIRES_HOST.md` sentinel: schema added to `_components/sentinel-frontmatter.md` (`kind: deferred-requires-host`, `missing_capabilities: [...]`, re-openable), mirrored in the `_FAIL_CLOSED_EVIDENCE_SENTINELS` tuple in `lazy_core.py` (line ~2153, alongside `DEFERRED_REQUIRES_DEVICE.md`) so the completion gate treats it as defer-not-evidence.
- [ ] In `compute_state()`: the capability-miss branch (sibling to the `not real_device` device-saturated skip at ~line 1497). On a feature past implementation whose `missing` set is non-empty and no `VALIDATED.md`: write `DEFERRED_REQUIRES_HOST.md` (via a `lazy_core` writer mirroring the device-sentinel pattern), append to a `host_saturated_skipped` list + a `_HOST_DEFERRED` module accumulator, emit the per-probe diagnostic naming the missing ids, and `continue` (skip — queue advances).
- [ ] Re-open contract: on a host where the probe now reports every required cap present (`missing` empty), the deferred feature is re-dispatched into runtime validation — same re-open shape as the device sentinel (no special-case; an empty `missing` simply does not skip).
- [ ] `host-capability-saturated` terminal: when the queue exhausts and the ONLY remaining items are host-capability-deferred, return a distinct terminal (NOT `all-features-complete`), placed beside the `device-queue-exhausted` terminal (~line 1839) with the same precedence ordering. Notification names the missing capability id(s) per feature: `host-capability miss — <feature-id> requires <cap-id> (absent on this host); deferred to capability-host`.
- [ ] Probe field + notification glue: surface a probe field the orchestrator translates into the notification + a live-queue skip (reusing the budget-guard `_GATED_HEADS`/skip-list surfacing pattern). Thin wrapper glue only — the decision is the script's.
- [ ] Tests: `lazy-state.py --test` fixtures — (a) one cap present one absent ⇒ `missing` is the absent id ⇒ defers (subset/AND); (b) all caps present ⇒ dispatches into validation (re-open); (c) all remaining features capability-gated ⇒ `host-capability-saturated` terminal (clean, not false completion); (d) ungated feature unaffected (baseline-regression). Regenerate the byte-pinned baseline via `_normalize_smoke_output`.

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` passes new fixtures: a feature requiring an absent cap defers with `DEFERRED_REQUIRES_HOST.md` and the queue advances; the same feature with the cap present dispatches into validation.

<!-- verification-only -->
**Runtime Verification** *(checked by the `--test` smoke suite):*
- [ ] `python user/scripts/lazy-state.py --test` green; the four capability-match fixtures pass; baseline regenerated through `_normalize_smoke_output`. <!-- verification-only -->

**Prerequisites:**
- Phase 1: `parse_requires_host`.
- Phase 3: `host_present_capabilities` (the `host.present` set).
- Phase 4: fail-fast runs first (this branch assumes all ids are registered).

**Files likely modified:**
- `user/scripts/lazy_core.py` - `DEFERRED_REQUIRES_HOST.md` writer + `_FAIL_CLOSED_EVIDENCE_SENTINELS` entry.
- `user/scripts/lazy-state.py` - the capability-miss skip branch + `host-capability-saturated` terminal + probe field in `compute_state()`.
- `user/skills/_components/sentinel-frontmatter.md` - the `deferred-requires-host` schema.
- `user/scripts/test_lazy_core.py` / in-file fixtures + `tests/baselines/lazy-state-test-baseline.txt`.

**Testing Strategy:** `--test` fixtures inject a stub host-present set (via the Phase-3 resolver seam) and assert the four behaviors: composite AND-defer, re-open on present, clean saturated terminal, ungated-unaffected baseline-regression. The ungated-unaffected fixture is the load-bearing regression guard for "no `requires_host:` ⇒ byte-identical to baseline."

**Integration Notes for Next Phase:**
- Phase 6 mirrors any new `lazy_core` shared helper (sentinel writer, terminal message formatter) into `bug-state.py` and registers it in the parity manifest — the writers must be shared, not duplicated.
- The thin-wrapper notification glue (probe field → PushNotification + end-of-run flush) is added to the `/lazy-batch` (+ `/lazy-batch-cloud`) wrappers in Phase 6 in lockstep with the coupled `/lazy` ↔ `/lazy-cloud` pair.

---

### Phase 6: Parity mirror + wrapper glue + coupled-pair lockstep + docs

**Scope:** Close the harness contracts: mirror every new shared `lazy_core` helper into the bug pipeline (`bug-state.py` — the marker/sentinel infra is shared), update the parity manifest, add the thin notification/skip glue to all four coupled `/lazy*` wrappers in lockstep, and document the new axis. No new behavior — this phase makes the Phase-1..5 work parity-clean and surfaced.

**Deliverables:**
- [ ] `bug-state.py` parity: any `lazy_core` helper Phases 1-5 added that the bug pipeline shares (probe resolver, sentinel writer) is reachable/mirrored; the unknown-id fail-fast and capability-miss defer apply identically IF bugs can declare `requires_host:` (decision: mirror the parsing + fail-fast for parity; the capability-miss skip is feature-pipeline-shaped but the shared helpers must not diverge). Update `lazy-parity-manifest.json` with the new canonical units (or register a justified divergence).
- [ ] `python user/scripts/lazy_parity_audit.py --report` green (no unexplained drift).
- [ ] Wrapper glue (coupled-pair lockstep): the capability-miss probe field → notification + live-queue skip is added to `user/skills/lazy/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` and `user/skills/lazy-batch/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, mirrored per the coupling rule, with each file's State Machine Summary / "Differences" block updated for the new `host-capability-saturated` terminal.
- [ ] Docs: `user/scripts/CLAUDE.md` "Three environments + the device axis" section gains the host-capability axis; the `_components/sentinel-frontmatter.md` schema (from Phase 5) and the `DEFERRED_REQUIRES_HOST.md` re-open contract are documented alongside `DEFERRED_REQUIRES_DEVICE.md`. The SPEC's vN upgrade paths (namespaced-suffix versioning, OR-via-profiles, manifest override) are noted as out-of-scope seams.
- [ ] Tests: `bug-state.py --test` green (parity baseline regenerated if touched); the full gate set runs clean.

**Minimum Verifiable Behavior:** The full quality-gate set is green: `python user/scripts/project-skills.py`, `python user/scripts/lint-skills.py --check-projected --check-capabilities`, `python -m pytest user/scripts/ -q`, `python user/scripts/lazy_parity_audit.py --report`.

<!-- verification-only -->
**Runtime Verification** *(checked by the full quality-gate suite):*
- [ ] `python -m pytest user/scripts/ -q` green (lazy-state, bug-state, lazy-core, parity). <!-- verification-only -->
- [ ] `python user/scripts/lazy_parity_audit.py --report` green — new canonical units mirrored or registered as divergences. <!-- verification-only -->
- [ ] `python user/scripts/project-skills.py` + `python user/scripts/lint-skills.py --check-projected --check-capabilities` clean (wrapper-prose edits projected + linted). <!-- verification-only -->

**Prerequisites:**
- Phases 1-5: all the shared helpers + the `lazy-state.py` behavior to mirror.

**Files likely modified:**
- `user/scripts/bug-state.py` - parity mirror of shared helpers / fail-fast.
- `user/scripts/lazy-parity-manifest.json` - new canonical units / divergences.
- `user/skills/lazy/SKILL.md`, `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`, `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` - notification/skip glue + State Machine Summary, in coupled-pair lockstep.
- `user/scripts/CLAUDE.md`, `user/skills/_components/sentinel-frontmatter.md` - docs.
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` - if the bug `--test` output changes.

**Testing Strategy:** Run the FULL gate set (`project-skills` + `lint-skills --check-projected --check-capabilities` + `pytest user/scripts/ -q` + `lazy_parity_audit --report`) per the repo's "mixed / feature completion" rule. The parity audit is the load-bearing check that no shared helper drifted between the two state machines.

**Integration Notes for Next Phase:** Terminal phase — feature implementation complete. The Step-9 MCP gate is operator-exempt for this repo (`SKIP_MCP_TEST.md` granted_by operator pointing at the passing quality gates); the orchestrator's `__mark_complete__` gate owns the final SPEC/PHASES Complete flip + receipt.
