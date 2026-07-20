# Research Summary — generalized-build-test-runner-skills

**Method:** No Gemini deep-research run (repo policy: claude-config has negligible research
volume; research resume is a direct-drop). The research substrate is (a) the committed operator
brief `ADHOC_BRIEF.md` — itself field-grounded against both target repos on 2026-07-13 — and
(b) this session's independent on-disk re-verification of every brief claim, on box
DESKTOP-GHTC5K6, 2026-07-13.

## Key findings relevant to the baseline

1. **The reference architecture is real and complete.** `user/scripts/build-queue.ps1` +
   `build-queue-runner.ps1` + `build-queue-await.ps1` + `Format-BuildQueueBanner`
   (`build-queue-hygiene.ps1:2275` — pure, side-effect-free, RESULT precedence documented) +
   `user/hooks/build-queue-enforce.sh` (manifest-scoped at lines 12–26; fail-open; Cognito
   legacy fallback; `BUILD_QUEUE_BYPASS=1` incl. the PowerShell env form at lines 146–147),
   covered by 5 Pester suites. Await exits verified in source: 124 = not-yet (line 99),
   125 = malformed (lines 69/96/122).

2. **The failure class is current, named, and half-generalized already.**
   `docs/bugs/_archive/subagent-backgrounds-verification-ends-turn-before-green/` (Fixed, P1)
   closed the Cognito build-queue instance; `docs/bugs/_archive/generic-execution-surfaces-lack-turn-end-gate/`
   (Concluded, P1, 2026-07-13) recorded 4 recurrences on GENERIC surfaces in one orchestrated
   run — including executors of the lazy-core decomposition hand-rolling the battery. The
   prose/turn-end half is generalized (`_components/turn-end-gate.md`, Round 39); the
   runner/banner/await half is not — that is this feature.

3. **The 7-command battery is a stable contract over an unstable layout.** Enumerated verbatim
   in `docs/features/lazy-core-package-decomposition/plans/all-phases-...-part-2.md` note 1.
   The pytest target (`user/scripts/`, now growing `user/scripts/tests/test_lazy_core/`) is
   being reshaped by the in-flight decomposition (Phases 3–6) — hence: spec the runner against
   the commands, sequence the implementation after the decomposition (hard dep), and keep the
   command list in a committed manifest rather than the runner body.

4. **AlgoBooth already has the banner half.** `npm run qg` emits a guaranteed final
   `QG_VERDICT: PASS|FAIL (exit N)` line and documents the never-pipe-through-tail rule
   (`.claude/skill-config/quality-gates.md`). Its `build-queue-ops.json` already manifests
   `tauri-build`/`cargo-release` (heavy lane, rust-tauri hygiene, deny rows). Missing: queue
   routing + skills + await + deny for the compile-heavy `qg -- rust|sidecar` gates. So the
   AlgoBooth work is purely additive manifest rows + thin skills on existing machinery.

5. **Contention profile supports the light/heavy split.** Concurrent claude-config batteries ran
   fine all session (pure CPU, no shared compiler state, no artifact hygiene) — machine-global
   serialization is not the needed piece for light ops; the outcome contract is. Heavy qg gates
   compile and contend with tauri/cargo builds — they belong in the existing queue.

6. **Cloud constraint shapes the runner-language seam.** build-queue is workstation-only
   (locked D7, build-queue-generalization), but the battery must run in cloud sessions (nightly
   lazy runs). A stdlib-Python runner conforming to the documented banner grammar — with no
   shared code with the PowerShell plane — serves both; the seam is the contract, not a library.

7. **False-deny precedent bounds enforcement.** Three recent guard false-deny bug variants
   (quoted-argument tokens; unanchored lifecycle patterns; overbroad blocker-write scope) argue
   against hook-denying high-frequency, many-shaped light invocations (raw pytest, qg ts/docs).
   Deny rows are confined to the heavy manifested ops, riding the enforce hook's existing
   per-op-deny machinery unchanged.

8. **Path discovery.** AlgoBooth lives at `C:\Users\Jacob\repos\AlgoBooth` (non-standard;
   the workspace CLAUDE.md "cloud-only" note is stale — it IS checked out natively here).
   Hook/queue keying is unaffected (payload-cwd git-toplevel). `~/.claude/lazy-repos.json`
   does not exist on this box; only fleet discovery would need a pin — documented, not built.

## Baseline decisions this research shaped

- D1 contract-as-component (finding 2: the turn-end half already lives as a component;
  the runner contract joins it, referencing — never copying — the gate).
- D2 light/heavy op classes (findings 5, 6).
- D3 enforcement confined to heavy manifested ops (finding 7).
- D4 Python runner, documented-grammar seam (finding 6).
- D5 battery manifest as SSOT + L7 sequencing dep (finding 3).
- D7 additive AlgoBooth ops (finding 4).
- L6 Cognito byte-untouched + Pester-green gate (finding 1).

## Pitfalls carried into the SPEC

- Deny-pattern precision (bare `npm run qg` vs `npm run qg -- ts`) — named risk in D3.
- `hygiene` profile for qg ops — provisionally `none`; re-check in phases (Open Question 4).
- Battery state-dir unwritable in exotic environments — degrade gracefully, banner still prints.
