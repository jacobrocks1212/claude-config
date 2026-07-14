---
kind: needs-input
feature_id: generalized-build-test-runner-skills
decisions:
  - id: L2
    summary: Light ops (claude-config battery, AlgoBooth qg ts/docs) bypass the machine-global build queue — runner+banner+await only; heavy AlgoBooth qg gates join the queue.
  - id: L3
    summary: Hook-deny enforcement only for heavy manifested ops; raw light invocations (pytest, qg ts/docs) are never hook-denied — advisory routing only.
  - id: L4
    summary: The claude-config battery runner is stdlib cross-platform Python conforming to the documented banner grammar; the seam with the PowerShell queue plane is the contract, not shared code.
divergence: product
written_by: spec
date: 2026-07-13
next_skill: spec
---

# Provisional decisions — generalized-build-test-runner-skills

Recorded under the operator-directed **park-provisional protocol** (batch posture, never halt):
each fork below changes an operator-owned contract, so the RECOMMENDED option was adopted
provisionally and the baseline locked. Ratification is pending; a reversal before Phase 3 is
cheap (every touched surface is additive and isolated). These correspond to Locked Decisions
L2/L3/L4 in `SPEC.md`.

## Decision Context

### L2 — Do light ops join the machine-global queue, or bypass it?

**Problem:** The Cognito pattern couples the outcome banner to queue admission (one heavy build
machine-wide). claude-config's 7-command battery and AlgoBooth's `qg -- ts|docs` are light (pure
CPU, no shared compiler state, no artifact hygiene; concurrent batteries ran fine all session),
and the queue is workstation-only (locked D7) while the battery must run in cloud sessions.

**Options:**
- **Bypass (CHOSEN provisionally):** light ops get runner+banner+await with NO queue admission;
  heavy AlgoBooth gates (`qg -- rust|sidecar`) join the existing queue as manifested ops. The
  queue manifest gains no "unserialized" lane value — light ops live in their own
  `gate-battery.json`. Pros: cloud-compatible by construction; zero queue-plane changes; no
  added latency on 4–5-min batteries. Cons: two manifest files per repo in the limit; if a
  light op later grows contention, it must be re-homed into the queue manifest.
- **Everything queues:** grow `build-queue-ops.json` with an unserialized/light lane value and
  register light ops there too. Pros: one manifest, one mental model. Cons: couples the battery
  to the workstation-only PowerShell plane (breaks the cloud requirement outright, or forces a
  dual-path runner); changes the queue manifest's semantics ("admitted to the slot" no longer
  holds); more machinery for no observed contention.

**Recommendation:** Bypass — the observed friction is the missing outcome contract, not missing
serialization; the cloud constraint makes queue coupling actively harmful.

### L3 — Are raw light invocations hook-denied like raw msbuild?

**Problem:** Cognito denies raw build invocations to force skill routing. Should raw
`python -m pytest user/scripts/` / raw `npm run qg` be denied the same way?

**Options:**
- **Deny heavy only (CHOSEN provisionally):** additive `deny` rows on the new AlgoBooth heavy
  ops (`npm run qg -- rust`, `npm run qg -- sidecar`, bare `npm run qg`) via the existing
  manifest machinery; light invocations are never denied — routing is advisory (skill prose +
  CLAUDE.md). Pros: enforcement exactly where contention/cost is real; zero new hook logic;
  avoids the recent false-deny bug class (3 variants in the guard plane) on a high-frequency,
  many-shaped surface (pytest). Cons: agents can still hand-roll the battery raw and re-create
  the turn-end friction the feature exists to close (mitigated by the KPI row + turn-end gate
  in the execution contracts).
- **Deny light too:** deny raw pytest/qg in opted-in repos, redirect to `/gate-battery`.
  Pros: maximal routing consistency. Cons: pytest invocation shapes are legion (single-test
  runs, -k filters, collect-only) — precision-denying only the full-battery shape is fragile
  exactly the way the false-deny bugs were; every false deny burns a turn and erodes trust in
  the guard plane.
- **Deny nothing new:** skip AlgoBooth deny rows as well. Pros: zero false-deny risk. Cons:
  heavy qg gates keep bypassing the queue and contending with tauri/cargo builds — the one
  place enforcement demonstrably pays.

**Recommendation:** Deny heavy only — matches the manifest-scoped enforcement philosophy
(build-queue-generalization) and the false-deny evidence.

### L4 — Runner language / seam for the claude-config battery

**Problem:** The queue plane is PowerShell; claude-config's gates are Python and must also run
in cloud sessions (no PowerShell, no queue — locked D7 keeps the queue workstation-only).

**Options:**
- **Stdlib Python runner, documented-grammar seam (CHOSEN provisionally):**
  `user/scripts/gate-battery.py` emits the banner grammar and implements `--await` (124/125)
  independently; the cross-repo seam is the documented contract
  (`_components/runner-outcome-contract.md`), not shared code. Pros: cloud-compatible; zero risk
  to the working PowerShell plane; testable in the repo's own pytest gate. Cons: two banner
  implementations to keep grammar-conformant (mitigated: the contract doc is the SSOT and both
  sides pin it in tests).
- **PowerShell wrapper for the battery too:** reuse `build-queue.ps1`/`Format-BuildQueueBanner`.
  Pros: single banner implementation. Cons: breaks the cloud requirement; drags a light op into
  the workstation-only plane; contradicts L2.
- **Python shim that enqueues into the PS queue on workstation, direct in cloud:** Pros: queue
  telemetry for batteries on workstation. Cons: dual-path complexity for an op class with no
  observed contention; the shim inherits both planes' failure modes.

**Recommendation:** Stdlib Python with the documented-grammar seam — it is the only option that
satisfies the cloud constraint without dual-pathing.
