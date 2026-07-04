# Research Summary — Harness-Change Canary + Rollback

Distillation of `RESEARCH.md` (internal desk research; Gemini deep research intentionally skipped
by operator directive 2026-07-04). Gates the downstream `/spec-phases` → `/write-plan` →
`/execute-plan` tail.

## Key findings relevant to the baseline spec

- **Detection latency is the documented problem, not a hypothetical.** In-repo prior art
  establishes that the failure class this feature targets is quiet by design: hooks are fail-OPEN
  by convention (`user/hooks/CLAUDE.md`) — a broken hook writes a `hook-error.json` breadcrumb and
  *allows*, so silence is indistinguishable from health without a watcher. `lazy-deny-ledger.jsonl`
  (guard denies + `kind: process-friction`) is structured evidence that today only a retro reads.
  The canary is the first consumer that reads these streams *during* the damage window.
- **The coupled-pair hazard is real and enforced.** The root `CLAUDE.md` pairs table and
  `lazy-parity-manifest.json` + `lazy_parity_audit.py` define pairs whose halves must move
  together. A naive revert of one half is exactly the edit that breaks parity — validating the
  design's decision to compute `pair_scope` at ship time and carry it on every revert item.
- **Flag-and-enqueue has a shipped precedent.** `/harden-harness`'s spin-off protocol (fix lands,
  generalized item front-enqueued via `adhoc-enqueue`, `PushNotification`, run never blocked) is
  the exact shape for "the harness noticed something and queued work about it." The canary's trip
  consequence copies it, including the never-blocks-the-run property.
- **Run-denominated windows match the constitution.** The budget guard, max-cycles, and the
  sibling efficacy windows all count runs/cycles, not wall-clock ("estimate in sessions, never
  time"). Canary windows follow suit, with a wall-clock ceiling only as a staleness bound.
- **Honest-degradation is the house pattern.** `DEFERRED_* / SKIP_*`, `baseline: unavailable`,
  `provenance: backfilled-unverified` — the canary's `closed-clean (no-data)` stamp and
  never-blocks-a-run watcher follow the same "record the limitation loudly, never fake or block."

## Ideas adopted from prior art

- **Automated canary analysis (Spinnaker Kayenta / Argo Rollouts / feature-flag canaries):** ship,
  observe a bounded window against a baseline, judge with declared metrics. Two adaptations:
  (1) the "traffic split" is **temporal** (before/after runs) because a single-operator harness has
  no parallel cohorts; (2) the rollback is a **proposed change** (flag-and-enqueue), not an
  automated action, because the deployment target is the safety system itself.
- **SRE burn-rate alerting (fast-burn + slow-burn windows):** the canary window vs the efficacy
  review window is exactly this two-speed pattern — the hair-triggered canary bands are acceptable
  because the consequence is an *investigation*, not a verdict.
- **GitOps revert-as-PR:** automation *prepares* the revert (commit set + evidence), a human
  merges. The evidence-bearing bug stub with commit set + pair scope is the pipeline-native
  equivalent; the bug pipeline under full gates is the "merge."
- **Kill switches vs safety interlocks:** reverting a live gate is *interlock removal*, never a
  reversible kill-switch actuation — the strongest external argument for the no-auto-revert lean.

## Pitfalls / concerns to address (carried into PHASES)

- **Trip noise → operator fatigue → ignored canaries.** Hair-triggered bands are safe only while
  trips stay rare and evidence stays good. Mitigation: trip precision is the system's own KPI
  (closes-as-noise counted), and the bands live in ONE constants block whose loosening is itself a
  gated control-surface change.
- **Attribution blind spot:** surface-less incidents never attribute, so a change that corrupts a
  shared state file another component trips over evades the incident tripwire. The KPI-regression
  tripwire + the slower efficacy review are the backstop; the gap is documented, not papered over.
- **Schema coupling to in-flight siblings.** Registration reads the provenance mapping + the
  manifest; the watcher reads the telemetry ledger. The SPEC pins these by feature-id/role and
  defers exact field names to phase-time empirical checks (Phase 1/2). Per HANDOFF.md all hard deps
  are landed on the branch; `docs/gate/control-surfaces.json` is NOT yet present (ships with
  `anti-overfit-design-gate`) → Phase 1 ships a canary-owned fallback surface-glob constant and
  documents that the manifest takes precedence when present.
- **Self-application:** the canary's own changes touch the control-surface manifest, so they get
  canaried and gated themselves. The no-data/closed-clean distinction + the retro citation exist so
  "very good harness" and "broken watcher" read differently.
- **Revert-item staleness:** further commits may land on the same surfaces before triage. Evidence
  carries the commit SET, not a patch, so `/plan-bug` plans against current reality; the
  degraded-revert note flags known-unsafe cases at ship time.

## Baseline decisions revisited by research

Research **converged with** the baseline on every decision — none was overturned. It hardened the
rationale for the three OPEN product-behavior calls (now operator-resolved per HANDOFF.md
2026-07-04):

| Decision | Recommendation | Research confidence | Operator resolution (HANDOFF 2026-07-04) |
|----------|----------------|---------------------|-------------------------------------------|
| D2 window + bands | 10 runs / 30-day ceiling; KPI band else 25% relative (≥3 events); ≥2 incidents | Medium (numbers are tunables) | Approved A |
| D3 attribution | Surface-based; unknown never attributes; shared surfaces count against all | Medium-high | Approved A |
| D4 auto-revert | No class in v1; flag-and-enqueue always; revisit only on trip-precision evidence | High (standing policy) | Approved A |
| D1 registration | `canary:` sub-map on the intervention record; scope via the sibling gate's manifest | High | Auto-accepted A |
| D5 revert item | Evidence-bearing `canary-revert-<id>` bug stub; commit set + pair scope; once ever | High | Auto-accepted A |
| D6 watcher | `efficacy-eval.py --canary` at every end-of-run flush while windows open | High | Auto-accepted A |
| D7 handoff | Status stamp + `## Canary` record section; efficacy review unaffected | High | Auto-accepted A |

The one genuinely contestable product call (D4 auto-revert) converged with the stub's lean for
three independent reasons: interlock-removal asymmetry, the coupled-pair hazard making mechanical
one-shot reverts structurally unsafe, and an unattended writer to `main` needing its own
containment story. Carried as a standing operator-owned policy — revisit only on accumulated
trip-precision evidence.
