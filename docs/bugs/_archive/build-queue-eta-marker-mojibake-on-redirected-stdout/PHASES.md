# Implementation Phases — build-queue ETA approx marker mojibake on redirected stdout

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure PowerShell display-glyph change in the build-queue
wrapper/status scripts (`user/scripts/build-queue.ps1`, `build-queue-status.ps1`) with no app
integration / MCP-reachable surface. Validation is the Pester suite
(`build-queue-hygiene.Tests.ps1`) + a serving-path runtime repro (status view against a
fixture state root, byte-checked ASCII-clean). Per docs/features/mcp-testing untestable
classes: build tooling / non-app script with no runtime app integration.

## Cross-feature Integration Notes

- **`build-queue-eta-priority-lanes` (Complete):** shipped the `≈` marker and locked the
  *prediction-vs-measurement distinction* (D3) — the glyph itself is implementation detail.
  The fix preserves the distinction (`~` + `?` markers) and the banner's ETA-free pin
  (`build-queue-hygiene.Tests.ps1:1508-1522`). The completed SPEC's `≈` examples are
  historical and left unedited; the divergence is noted in root `CLAUDE.md`.
- **No `**Depends on:**` block in the SPEC** — a harness-self display bug, no upstream deps.

## Audit Table (touchpoints — verified by direct Read of each file/region)

| Planned file | Exists? | Real symbols (verified) | Action | Directive |
|--------------|---------|-------------------------|--------|-----------|
| `user/scripts/build-queue.ps1:177` | yes | `$script:etaApprox` (consumed at :184,187 via `Format-EtaSuffix`; position line :410-416 inherits) | edit | `[char]0x2248` → `'~'` + mojibake comment naming this bug dir |
| `user/scripts/build-queue-status.ps1:107,149` | yes | `$etaApprox` (active-build `remaining` line :121), `$etaApproxW` (waiter rows :166) | edit | same substitution, both sites |
| Root `CLAUDE.md` build-queue-status row | yes | `remaining≈`/`eta-start≈`/`eta-done≈` prose | edit | update to `~` forms + divergence note |
| `build-queue-hygiene.ps1` / `Format-BuildQueueBanner` | yes | banner composer | NO CHANGE | banner is ETA-free by Pester pin; untouched |

---

## Phase 1: Replace U+2248 with ASCII `~` on all pre-outcome ETA surfaces

**Status:** Fixed

**Scope:** Swap the marker literal at the three definition sites; update the live doc row;
verify via Pester + a serving-path byte-level repro. No numeric/logic change anywhere —
`Get-BuildQueueEta`, `Get-BuildQueueWaitEta`, and `Format-EtaDuration` are untouched.

**Deliverables:**
- [x] `build-queue.ps1:177` — `$script:etaApprox = '~'` (with root-cause comment)
- [x] `build-queue-status.ps1` — `$etaApprox = '~'` and `$etaApproxW = '~'`
- [x] Root `CLAUDE.md` row updated (`remaining~`, `eta-start~`/`eta-done~` + divergence note)
- [x] Pester regression: `Invoke-Pester build-queue-hygiene.Tests.ps1` — 172 passed; 3
  failures are pre-existing environment-dependent Job-Object tests (Tests.ps1:44,50,79) in an
  unmodified file; all ETA-estimator + banner-pin tests green
- [x] Serving-path symptom-gone repro: `build-queue-status.ps1 -StateRoot <fixture>` (active
  build + waiter + real 3-sample stats) emitted `remaining~ 1m 49s` /
  `eta-start~1m 49s eta-done~3m 40s`; `grep -P '[^\x00-\x7F]'` over captured stdout: zero
  non-ASCII bytes (evidence recorded in SPEC.md "Fix Applied")
