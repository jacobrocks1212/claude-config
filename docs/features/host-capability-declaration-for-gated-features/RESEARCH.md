# Host-Capability Declaration and Probing Architectures in Autonomous Build Pipelines

## Introduction

The orchestration of autonomous, deterministic state-machine build pipelines demands a rigorous separation between the declarative intent of a software feature and the imperative realization of its execution environment. In systems governed by large language models (LLMs), the model's responsibility must be strictly confined to planning, specifying, and writing code, while the underlying state script—such as lazy_core.py—must retain absolute, deterministic authority over the execution state. When a feature requires specific host capabilities, such as specialized compiler toolchains, hardware interfaces, or localized runtime environments, the system must deterministically map these requirements against the host's actual provisions. Deferring feature execution dynamically upon encountering unmet capabilities prevents pipeline stalls, resource starvation, and manual intervention loops at the validation boundary.

Generalizing a single-device dependency into an N-capability axis introduces architectural complexity. The system requires a robust syntax for declaring host requirements, a secure and accurate probing mechanism to query the host, and a governed vocabulary to prevent unfulfillable dependencies from silently hanging the queue. If an LLM hallucinates a capability identifier, or if a host probe returns a false positive due to an operating system shim, the autonomous pipeline will fail catastrophically at the runtime-validation boundary, burning precious computational cycles. The analysis of mature Continuous Integration (CI), build matrices, and task runners—specifically GitHub Actions, Bazel, Buck2, Nix, Earthly, Kubernetes, and GitLab Runner—provides a definitive blueprint for architectural conventions, governance structures, and critical failure modes to avoid when designing a deferred-execution orchestrator.

## Research Area 1: Capability-Declaration Conventions in CI/Build Systems

Mature task runners utilize declarative, decoupled interfaces for host requirements, ranging from flat string arrays to highly structured, hierarchical constraint objects. Flat label arrays offer maximum operational simplicity and direct compatibility with minimal parser overhead, whereas hierarchical constraint tuples ensure mathematically deterministic target resolution at the cost of increased verbosity. For a flat, per-feature `requires_host:` primitive operating within a state machine, a strict string-based list governed by a static schema represents the optimal balance of architectural simplicity and execution safety.

- **GitHub Actions:** host capabilities declared via `runs-on`, a flat array of string labels (e.g. `runs-on: [self-hosted, linux, x64, gpu]`), evaluated with strict logical AND semantics. Labels are open strings — no validation prior to job queuing, shifting correctness burden onto the author.
- **Bazel:** structured/hierarchical `constraint_setting` (dimension) + `constraint_value` (specific capability); targets declare requirements via `exec_compatible_with`. A platform may not hold multiple values for the same constraint setting — strict taxonomic rigidity.
- **Buck2:** inherits Bazel's target/execution-platform concepts; `ConfigurationInfo` providers + `exec_compatible_with`, plus an explicit `ExecutionPlatformRegistrationInfo` provider to evaluate constraint satisfaction.
- **Nix:** functional via package metadata — `meta.platforms` / `meta.badPlatforms` (system identifier strings/patterns matched against `stdenv.hostPlatform` at evaluation; fails fast before build actions).
- **Earthly:** shifts resolution into the container runtime; capabilities mandated via base images / multi-arch manifests / target tags. Declaration is implicit (bundled into layer execution).

### Comparison of Capability Declaration Shapes

| System | Declaration Mechanism | Granularity | Vocabulary Governance | Disjunction (OR) Support |
|--------|----------------------|-------------|-----------------------|--------------------------|
| GitHub Actions | `runs-on` array of labels | Coarse (string IDs) | Open (any string) | Workflow logic/expressions or matrix strategies |
| Bazel | `exec_compatible_with` | Fine (constraint values) | Closed (strict DAG validation) | `select()` on target attributes |
| Buck2 | `exec_compatible_with` | Fine (constraint values) | Closed (strict DAG validation) | Configuration rules & transitions |
| Nix | `meta.platforms` / `badPlatforms` | Coarse/Fine (pattern match) | Closed (stdlib sets) | Implicit in lists / functional eval |
| Earthly | Earthfile targets / base images | Implicit (container layer) | Open (any container tag) | N/A (underlying container runtime) |

## Research Area 2: Host/Toolchain Probing Conventions and Hazards

Relying on simple path resolution or file existence is highly susceptible to false positives due to execution stubs, alias files, and stale caches, which frequently lead to silent pipeline failures. Robust systems employ active execution probes (sanity checks) and strict cache invalidation keys to certify capability presence. Hermetic toolchain resolution demands that probes execute a minimal functional test rather than merely asserting binary location.

- **The catastrophic false positive:** binary present on `$PATH` but broken / wrong-arch / shimmed.
- **Windows 10/11 "App Execution Aliases":** zero-byte `python.exe` / `python3.exe` stubs injected into `\WindowsApps` on `$PATH`. `shutil.which()` / `which` succeed, but invocation opens a GUI Microsoft Store prompt that silently hangs automated pipelines and consumes parallel-execution limits.
- **Cache staleness:** CMake caching of compiler paths (`config.cache`) → fatal generator mismatches when the compiler is upgraded/removed while the cache persists.
- **Mitigations (active sanity checks):** CMake `try_compile` / `CheckSourceCompiles` compile a minimal source file end-to-end (preprocessor→linker) before asserting; `try_compile`-only for cross-compilation edge cases. The general rule: execute a deterministic, cacheable invocation (`tool --version` / `tool --help`, parse stdout / check exit code) rather than filesystem checks. For a device, query the device interface directly. Hermetic tests require injectable mock probe callables.

## Research Area 3: Capability Granularity

Coarse, named-presence capabilities dominate initial implementations due to the high maintenance burden of fine-grained semantic-version solvers. Evolution to version-ranged declarations is handled by **namespacing the capability ID**, not by building a constraint solver.

- **GitHub Actions:** coarse strings; versions encoded into the string itself (`ubuntu-20.04` vs `ubuntu-latest`) — exact match, no version math.
- **Bazel:** transitions coarse→fine by expanding the taxonomy (`gcc_version` setting with explicit values like `gcc_12.2.0`), keeping resolution a simple subset-match — no `>=`/`<` operators.
- **Nix:** static architecture strings (`x86_64-linux`); toolchain variants via naming suffixes (`python38`, `python-unwrapped`).
- **Recommendation for this pipeline:** adopt a coarse string array (`["zimtohrli", "real-audio-device"]`). For future versioning, a namespaced suffix convention (`zimtohrli-v2`, `cuda-11`) mirrors Bazel/Nix and avoids building a semantic-version parser into the Python state machine.

## Research Area 4: Declaration-Vocabulary Governance

Open vocabularies routinely lead to infinite queue starvation when typoed capabilities remain unfulfilled without failing fast. Closed registries prevent this by failing validation at parse/evaluation time.

- **Open-vocabulary failure (silent starvation):** GitHub Actions `runs-on: self-hsted` → job sits "queued" forever; Jenkins `NodeLabelParameter` with a nonexistent label never binds; GitLab Runner "worker starvation" on nonexistent tags.
- **Closed-registry fail-fast:** Bazel `constraint_value` typo (`loongarch65`) → immediate "No matching toolchains found" analysis failure; Nix undefined architecture → deterministic evaluation-phase failure.
- **Recommendation:** because the **LLM** dictates the `requires_host:` array, an open vocabulary is a critical vulnerability. Implement a **closed registry** — a hardcoded Python dict in `lazy_core.py` mapping valid string IDs → deterministic probe callables. An unrecognized ID triggers an immediate, loud validation failure, so no feature is indefinitely deferred to a non-existent capability.

## Research Area 5: Composite and Optional Requirements

A flat AND-set satisfies the overwhelming majority of real-world build-matrix scenarios; optionality and OR-groups introduce non-deterministic scheduling behavior.

- **GitHub Actions:** `runs-on` array is a strict AND; OR achieved only via matrix strategies / expression functions selecting a flat AND-set beforehand.
- **Bazel:** platforms are a strict AND-set of `constraint_value`s; multi-config handled via `select()` at the target-attribute level, never OR in the platform definition.
- **Kubernetes / Mesos:** pushing OR/affinity logic into the scheduler causes "unsatisfiable" topology constraints and `Pending`/`FailedScheduling`; Mesos abstracts the decision to frameworks (offers).
- **Recommendation:** restrict v1 to a **flat AND-set** so host-probe logic is a simple `set(required).issubset(set(host))` subset verification — maximizes determinism, keeps the state machine lightweight.

## Specific Recommendations

| # | Specific Question | Recommendation | Justification (prior art) |
|---|-------------------|----------------|---------------------------|
| 1 | Exact declaration shape | Flat string array (`["zimtohrli", "real-audio"]`) | Matches GitHub Actions `runs-on` ergonomics + Bazel flat constraint sets; simple subset-inclusion; minimizes LLM hallucination risk |
| 2 | Probe failure modes & mitigations | Active invocation sanity checks (`subprocess.run`) | Prevents false positives from zero-byte Windows Apps stubs and stale CMake caches that plague passive `$PATH` checks |
| 3 | Granularity (coarse vs versioned) | Coarse named-presence for v1 | Standard starting point; versions later via namespaced suffixes (`tool-v2`) mimicking Bazel taxonomies, no engine change |
| 4 | Open vs closed vocabulary | Closed registry in `lazy_core.py` | Open vocabularies → silent infinite starvation on typo; closed registry fails fast like Bazel/Nix |
| 5 | Flat AND-set vs OR-groups | Strict flat AND-sets | GHA/Buck2/Bazel rely on AND-sets; OR-logic causes K8s `FailedScheduling` |
| 6 | Re-open / defer-and-retry patterns | Proactive deferral but monitor cycle starvation | Deferring (skip-ahead) prevents blocking, but unmonitored deferral queues starve if capabilities never materialize fleet-wide |
| 7 | Naming conventions for IDs | lowercase kebab-case w/ optional namespaces (`os-linux`, `tool-zim`) | Aligns with `^[a-z0-9][a-z0-9-]*$`; mirrors Bazel platform naming |

## V1 vs. Later Implementation Blueprint

**Adopt for v1:**
- **Coarse granularity** — binary presence/absence ("Is Zimtohrli present?", not "version >= 2.1").
- **Flat-AND sets** — features declare an explicit list; all must be satisfied.
- **Active runtime probing** — non-destructive command (`--help` / `--version`), evaluate exit code, bypass execution shims/aliases.
- **Closed registry validation** — hardcoded allowable vocabulary mapping string IDs → probe callables; unknown string throws fatal exception.
- **Hermetic test injection** — probes mocked during unit testing.
- **Deterministic deferral** — write `DEFERRED_REQUIRES_HOST.md` on a miss and immediately skip ahead.

**Document as upgrade paths (vN):**
- **Version matrices** — namespaced suffix convention (`zimtohrli-3_1`) mirroring Bazel `constraint_value` naming; no semantic-version parser.
- **Logical disjunction (OR-groups)** — separate configuration profiles (Bazel `select()`), not changes to the `requires_host:` array structure.
- **Host manifest overrides** — leave space in state-init to override the deterministic probe with an operator-maintained manifest (Nix-style), as a safety valve for air-gapped environments.

## Failure Modes and Anti-Patterns to Guard Against

| Anti-Pattern | Demonstration System | Guard / Mitigation in v1 |
|--------------|----------------------|--------------------------|
| Zero-byte execution stub (false positives) | Windows 10/11 `python3.exe` stub in `\WindowsApps` → GUI Store prompt freezes pipelines | Do NOT probe via `os.path.exists()` / `shutil.which()`; require active execution (`subprocess.run(["tool", "--version"])`) + parse stdout |
| Typo-induced infinite queueing (silent starvation) | GHA misspelled `runs-on` label waits forever | No open-string labels; validate `requires_host:` keys against a known registry at parse time, fail fast on hallucinated IDs |
| Unsatisfiable scheduling deadlocks | K8s pods `Pending` / `FailedScheduling` from conflicting selectors/anti-affinities | Don't over-constrain with OR-logic/fallbacks; keep requirements a minimal flat AND-set |
| Long-polling worker starvation | GitLab Runner workers polling for jobs they can't run consume concurrency | `DEFERRED_REQUIRES_HOST.md` must instantly skip; never spin/poll on unfulfillable requirements — advance to the next compatible feature |

## Conclusion

Rigid, closed-vocabulary declarations paired with deterministic, active host probing yield the highest resilience. The v1 design must reject semantic-version solvers and complex Boolean scheduling logic. Instead: coarse, flat AND-sets mapped against a strictly governed registry of active sanity-check probes. This eliminates LLM hallucination, execution-stub false-positives, and infinite queue starvation while keeping `lazy_core.py` the absolute authority over execution state, with a clean upgrade path for capability scaling.

## Works Cited

GitHub Docs (choosing the runner; queued-state discussions); Stack Overflow (runs-on OR-logic; runner pickup; Windows python permission); Bazel (platforms & toolchains, building with platforms, auto-exec-groups, "No matching toolchains" discussions); Buck2 (configurations, constraint, constraint_value); Nixpkgs manual + meta-attributes + `lib/meta.nix` + naming conventions; Earthly (Google Cloud Build, 0.7 docs); Windows `\WindowsApps` python3 stub gist + HN thread; CMake try_compile modules; GitLab Runner advanced configuration + concurrency-deadlock MR; Kubernetes FailedScheduling / Pending troubleshooting + Karpenter topology issue; Kubernetes vs Mesos comparisons. (Full URL list preserved in the source Gemini export.)
