# Research Summary — Host-Capability Declaration for Gated Features

Condenses [`RESEARCH.md`](./RESEARCH.md) (Gemini deep research over GitHub Actions, Bazel, Buck2, Nix, Earthly, Kubernetes/Mesos, GitLab Runner) against the locked baseline `SPEC.md`. The research validates the two operator-locked decisions and resolves all four routed Open Questions; it surfaced **no new product-behavior fork** — every finding either confirms the baseline or forces a mechanically-consequent refinement of an already-locked invariant.

## Key findings relevant to the baseline

| Open Question (SPEC) | Research verdict | Effect on baseline |
|----------------------|------------------|--------------------|
| Capability granularity (coarse vs fine) | **Coarse named-presence for v1** is the dominant starting convention (GHA exact-match strings, Bazel/Nix subset-match — no `>=`/`<` operators anywhere). Versioning later via **namespaced suffix** (`zimtohrli-v2`, `cuda-11`), NOT a semantic-version solver. | Confirms baseline (`v1 ships coarse named-presence`). Adds the namespaced-suffix upgrade path as the documented vN convention. |
| Probe design conventions | **Active-invocation sanity checks** (`subprocess.run([tool, "--version"])`, parse exit code/stdout) over passive `$PATH` / `os.path.exists()` / `shutil.which()`. The canonical false-positive is the **Windows 10/11 App Execution Alias** — a zero-byte `python3.exe` stub in `\WindowsApps` that `which()` finds but whose invocation opens a GUI Store prompt and silently hangs the pipeline. Also: stale CMake-style path caches. | Refines the probe implementation (mechanical-internal): each probe callable must actively invoke + check exit code, never filesystem-presence. Directly relevant — this is a Windows host. |
| Declaration-vocabulary ownership (open vs closed) | **Closed registry** — a hardcoded dict mapping valid ids → probe callables. Open vocabularies cause **silent infinite queue starvation** on a typo (GHA `self-hsted` sits queued forever; GitLab/Jenkins worker starvation). Closed registries fail fast at parse time (Bazel "No matching toolchains found"; Nix evaluation-phase failure). | Confirms the baseline shape: SPEC already binds the vocabulary to "ids defined alongside the probe / each id maps to a deterministic host check" — that IS a closed registry. **Forces** one new behavior: an unregistered id must fail loud, not silently defer-forever (see ⚖ below). |
| Composite / AND-OR requirements | **Flat AND-set for v1.** `set(required).issubset(set(host))`. OR-groups / optional fallbacks cause unsatisfiable-scheduling deadlocks (K8s `FailedScheduling`, Mesos). OR handled later via separate config profiles (Bazel `select()`), never by changing the `requires_host:` array shape. | Confirms baseline (flat subset match). Adds OR-via-profiles as the documented vN path. |

## Ideas adopted from prior art

- **Closed-registry fail-fast** (Bazel/Nix): an unrecognized `requires_host:` id is a loud, immediate validation error — never a silent forever-deferral. This is forced by the already-locked "clean terminal / no false completion" invariant; a typo'd id that silently defers would violate it.
- **Active-invocation probes** (CMake `try_compile` philosophy): probe callables invoke `tool --version`/`--help` and check exit code, never `which()`/`exists()`. Mandatory on this Windows host because of the `\WindowsApps` zero-byte alias hazard.
- **Namespaced-suffix versioning** (Bazel `constraint_value` taxonomy, Nix `python38`): the documented vN path to versioned capabilities — no semantic-version parser in the state machine.
- **Instant skip-ahead on miss** (GitLab worker-starvation lesson): `DEFERRED_REQUIRES_HOST.md` must skip immediately; never spin/poll on an unfulfillable requirement.

## Pitfalls to address

- **Windows App Execution Alias false-positive** — the headline hazard for a `which()`-based probe; mitigated by active invocation. Captured as a Validation Criteria row.
- **Stale probe cache** — the baseline caches the probe per run-marker (re-probe on a new run); research's CMake-cache-staleness warning confirms not caching across runs is correct.
- **Fleet-wide deferral starvation** (research rec #6) — if a capability never materializes on ANY host, deferred features accumulate forever. v1 surfaces each deferral (notification + end-of-run flush) so the operator sees the standing gap; cross-host fleet monitoring is a documented vN concern, not v1 scope.

## Baseline decisions revisited

None reversed. The two operator-Locked Decisions (per-feature `requires_host:` marker + runtime probe; defer-to-capability-host) are both confirmed by prior art. The only baseline *additions* are the three mechanically-consequent refinements above (active-invocation probes, fail-fast on unregistered id, namespaced-suffix vN path), all integrated into the finalized SPEC.

⚖ policy: fail-fast on unregistered capability id → bake in (forced by locked clean-terminal invariant; closed registry already baseline)
⚖ policy: probe via active invocation not `which()` → bake in (Windows `\WindowsApps` alias hazard; probe-internal, operator-invisible)
