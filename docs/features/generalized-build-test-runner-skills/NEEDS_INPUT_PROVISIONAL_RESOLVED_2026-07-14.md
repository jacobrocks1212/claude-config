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
  - id: D3-precision
    summary: Bare `npm run qg` is NOT hook-denied (deny rows cover only the exact heavy forms incl. the `quality-gate` alias) — a bare-qg deny row provably shadows `npm run qg -- ts` under the enforce hook's manifest deny compile, and adding an allow mechanism would violate the zero-enforce-hook-diff guard. Appended by spec-phases 2026-07-13.
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

### D3-precision — Can bare `npm run qg` be denied without false-denying `qg -- ts|docs`? (appended at planning, /spec-phases 2026-07-13)

**Problem:** SPEC D3 names three deny targets: `npm run qg -- rust`, `npm run qg -- sidecar`,
"and bare `npm run qg` since it runs the rust gate" — while requiring `npm run qg -- ts` stay
allowed. The planning-time capability audit verified the enforce hook's manifest deny compile
(`_compile_manifest_deny`, `user/hooks/build-queue-enforce.sh:488`): a non-`.ps1` deny entry is
`re.escape`-tokenized, `\s+`-joined, and anchored `_CMD_START … (?:\s|$)`. A `npm run qg` row
therefore MATCHES `npm run qg -- ts` (the trailing space satisfies `(?:\s|$)`); no negative
lookahead can be expressed (tokens are escaped), no per-op allow/suppression mechanism exists
for manifest ops (`_suppress_safe` covers only hard-coded dotnet/nx forms), and pattern order
cannot rescue it (first deny match wins; there is no allow). So "bare qg denied AND `-- ts`
allowed AND zero enforce-hook diff" is jointly unsatisfiable. Also discovered: `package.json`
aliases `quality-gate` ≡ `qg`, widening the raw-invocation surface the rows must cover.

**Options:**
- **Deny exact heavy forms only (CHOSEN provisionally):** deny rows = `npm run qg -- rust`,
  `npm run qg -- sidecar`, `npm run quality-gate -- rust`, `npm run quality-gate -- sidecar`.
  Bare `npm run qg` stays un-denied (advisory routing; pinned by an explicit ALLOW fixture
  test so the residual is deliberate, not accidental). Pros: zero enforce-hook diff (L6 guard
  intact); zero false-deny risk (the SPEC's own named risk class); implementable today on the
  existing machinery. Cons: an agent running bare `npm run qg` still triggers the heavy rust
  gate outside the queue — the KPI row `generalized-runner-raw-invocation-deny-recurrence`
  measures whether this residual actually recurs.
- **Additive hook change (allow-suppression for manifest ops):** grow the manifest schema with a
  per-op `allow` list suppressed from the scan copy before deny-matching (mirrors the existing
  `_suppress_safe` architecture); then bare `npm run qg` can be denied precisely. Pros: full D3
  surface. Cons: violates the zero-enforce-hook-diff guard this feature's plans carry (the hook
  is live Cognito enforcement; the false-deny bug class is recent and real); expands blast
  radius far beyond an additive feature.
- **Reshape AlgoBooth's qg surface** (e.g. bare `qg` stops running the rust gate): out of scope —
  changes AlgoBooth's own quality-gate UX to serve an enforcement detail.

**Recommendation:** Deny exact heavy forms only — matches the manifest-scoped enforcement
philosophy and the false-deny evidence; the residual is measured (KPI row) and reversible: if
ratification wants bare-qg denial, the allow-suppression hook feature is a separate, ordinary
queue-plane item (enqueue then; do not smuggle it into this additive feature).

## Ratification

*Recorded on 2026-07-14.*

ratified_by: operator
outcome: ratified

### 1. L2 — light ops bypass the machine-global build queue

**Choice:** Ratify Bypass — the claude-config battery + AlgoBooth `qg -- ts|docs` are light ops
served by runner+banner+await with no queue admission; only heavy `qg -- rust|sidecar` join the
queue. Implemented and validated (Phases 1–3): cloud-compatible stdlib runner, zero queue-plane
changes. Operator answered "Ratify all as-adopted" via interactive AskUserQuestion, 2026-07-14.

### 2. L3 — hook-deny heavy manifested ops only

**Choice:** Ratify Deny-heavy-only — additive manifest `deny` rows on the AlgoBooth heavy qg ops;
raw light invocations (pytest, `qg -- ts|docs`) are never hook-denied (advisory routing). Live
deny check in Phase 3 confirmed heavy forms denied + light forms allowed. Operator ratified via
AskUserQuestion, 2026-07-14.

### 3. L4 — stdlib-Python runner, documented-grammar seam

**Choice:** Ratify the stdlib-Python runner (`gate-battery.py`) conforming to the documented
banner grammar (`_components/runner-outcome-contract.md`) — the cross-repo seam is the contract,
not shared code. Both planes pin the grammar in their own tests. Operator ratified via
AskUserQuestion, 2026-07-14.

### 4. D3-precision — deny only exact heavy qg forms; bare `npm run qg` stays advisory

**Choice:** Ratify Deny-exact-heavy-forms-only — a bare `npm run qg` deny row provably shadows
`npm run qg -- ts` under `_compile_manifest_deny`, and an allow-suppression mechanism would
violate the zero-enforce-hook-diff guard. The residual is pinned by an ALLOW fixture test and
measured by KPI row `generalized-runner-raw-invocation-deny-recurrence`; bare-qg denial, if ever
wanted, is a separate queue-plane item. Operator ratified via AskUserQuestion, 2026-07-14.
