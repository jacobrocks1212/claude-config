# Generalized Build/Test Runner Skills — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 0 — Runner-outcome contract

#### Implementation Notes (Phase 0)
**Completed:** 2026-07-14 (commit cd0efba1)

- **Work completed:** authored `user/skills/_components/runner-outcome-contract.md` — the ONE
  documented contract (SPEC D1/L1): Leg 1 banner grammar with the three conforming instances
  (`build-queue:` existing / `QG_VERDICT:` grandfathered verbatim / `gate-battery:` new, quoted
  from SPEC D1), Leg 2 followable-await 124/125 semantics (mirrors `build-queue-await.ps1` —
  124 @ line 99, 125 @ lines 69/96/122), Leg 3 turn-end gate BY REFERENCE (one pointer sentence,
  zero copied gate text, zero `!cat` inside the component), Leg 4 never-pipe-through-tail
  (generalized from AlgoBooth `quality-gates.md:10-16`), the seam statement (documented grammar,
  not shared code — D4), and the D8 AlgoBooth path note with the `lazy-repos.json` pin recipe
  (documented only). Plus the `user/scripts/CLAUDE.md` prose-pointer paragraph (a new
  `## Runner-outcome contract` section above Contributor conventions — deliberately NOT a
  script-table row, so `doc-drift-lint.py` doc→disk mapping stays clean).
- **MVB verified:** `lint-skills.py` exit 0; `grep -c "turn-end"` = 3;
  `grep "may not end while work"` = 0 hits (referenced, not copied).
- **Gates:** full 7-command battery green pre-commit (pytest 2243 passed in 416s; both `--test`
  smoke suites; parity exit 0; cli-surface `--check` OK; doc-drift 0 findings; lint-skills OK).
  Cognito byte-untouched guard: commit touches nothing under `repos/cognito-forms/` or
  `build-queue*`.
- **Integration notes for Phase 1:** the `gate-battery:` grammar string in the component is the
  SSOT — WU-2/WU-3 tests must quote it verbatim from
  `user/skills/_components/runner-outcome-contract.md` (cite the path in test docstrings). If
  implementation forces a grammar change, change the component in the SAME commit (plan note 6).
- **Pitfalls:** none — docs-only phase. Components carry no YAML frontmatter (house style
  confirmed against `_components/` siblings).

## Phase 1 — Battery runner + manifest + pytest

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-14

- **Work completed (WU-2..WU-4):** `user/scripts/gate-battery.py` (stdlib-only, manifest-driven,
  contract-conformant) + `user/scripts/tests/test_gate_battery.py` (17 hermetic tests, tmp state
  roots + fixture manifests). WU-2 = runner core (git-toplevel manifest load, sequential gates
  with streamed output, last-line banner via try/finally, results JSON, private `_repo_key` copy
  of `lazy_core/statedir.py::repo_key` with keep-in-sync comment, manifest-less exit-2 clean
  refusal, state-root-unwritable graceful degrade, no-PowerShell source-scan proxy). WU-3 =
  `--await <run-id>` with 124 (not-yet, NEVER success) / 125 (malformed) semantics mirroring
  `build-queue-await.ps1`. WU-4 = seeded `.claude/skill-config/gate-battery.json` (7-command
  invariant battery AS COMMANDS, `python3` interpreter), CLI-surface roster addition
  (`DidYouMeanArgumentParser` + `--dump-cli-surface`, `docs/cli/cli-surface.json` regenerated
  same commit), `user/scripts/CLAUDE.md` script-table row.
- **MVB / dogfood (WU-4):** `python3 user/scripts/gate-battery.py --repo-root .` ran all 7 gates,
  last stdout line `gate-battery: run=20260714-1336 op=battery RESULT=PASS cmds=7 failed=0
  (elapsed=417s)`, exit 0. `--await 20260714-1336` re-emitted the same banner as its last line,
  exit 0. `cli_surface_gen.py --check` green (8 roster scripts).
- **Sequencing gate (SPEC L7):** verified `lazy-core-package-decomposition` Status=Complete with
  `COMPLETED.md` before any edit — dep satisfied.
- **Cognito byte-untouched guard (SPEC L6):** WU-4 commit touches nothing under
  `repos/cognito-forms/` or `build-queue*` / `build-queue-enforce.sh`.

## Phase 3 — AlgoBooth heavy qg ops (workstation)

#### Implementation Notes (Phase 3)
**Completed:** 2026-07-14 — workstation `DESKTOP-GHTC5K6`, live AlgoBooth checkout
`C:\Users\Jacob\repos\AlgoBooth`. Commits: WU-1 `dcf25aac`, WU-2 (AlgoBooth repo) `933b0a2bc`,
WU-3 `3f2cbfa9`, WU-4 (this).

- **Hygiene re-check (SPEC Open Question 4) — decision `hygiene: none` for BOTH ops.** The
  criterion is whether `qg -- rust|sidecar` invoke cargo in a way that writes shared Tauri
  **release** artifacts (`src-tauri/target` release outputs). Evidence from
  `C:\Users\Jacob\repos\AlgoBooth\scripts\quality-gate.sh`: the `rust` gate (`run_rust_gates`,
  quality-gate.sh:1176-1188) runs only debug-profile cargo — `cargo check --manifest-path
  src-tauri/Cargo.toml` (:666), `cargo clippy … src-tauri/Cargo.toml` (:671), `cargo test …
  src-tauri/Cargo.toml --bin algobooth` (:693), `cargo test -p algobooth-audio-core` (:699),
  `cargo nextest run -p algobooth-audio-engine …` (:744) + `cargo test --doc …` (:745). NONE
  use `--release`. The `sidecar` gate (`run_sidecar_gates`, quality-gate.sh:1240-1246) is three
  npm scripts (`sidecar:type-check`/`:test`/`:build`) — no cargo at all. No shared release
  artifacts ⇒ the `rust-tauri` Job-Object-reap/compiler-recycle profile is unwarranted;
  `hygiene: none`. (SPEC ground truth confirmed: a `sidecar` gate name exists — quality-gate.sh
  dispatch `sidecar) run_sidecar_gates` at :1396 — so the halt condition (c) did not fire.)
- **Manifest rows + TDD (WU-1, `dcf25aac`).** Two additive ops in
  `repos/algobooth/.claude/skill-config/build-queue-ops.json` (`kind: test`, `hygiene: none`,
  `lane: heavy`); `tauri-build`/`cargo-release` byte-untouched. Deny rows = EXACT heavy forms
  only per the LOCKED D3-precision provisional (bare `npm run qg` deliberately un-denied). 9
  additive `test_hooks.py` fixtures (armed via `BQE_PLATFORM_OVERRIDE=armed`) GREEN, incl. the
  pinned-residual ALLOW test for bare `npm run qg` citing `NEEDS_INPUT_PROVISIONAL.md`.
- **Exec wrappers (WU-2, AlgoBooth `933b0a2bc`).** `.claude/scripts/qg-{rust,sidecar}-filtered.ps1`
  — thin PS shims: resolve repo root from `$PSScriptRoot\..\..`, `Set-Location`, run
  `& npm run qg -- rust|sidecar` (forwarding pass-through `$ExecArgs`), `exit $LASTEXITCODE`
  (no ErrorActionPreference=Stop, so a qg FAIL propagates as a faithful exit code). Both parse
  clean (`[scriptblock]::Create`). Force-added past AlgoBooth's `.claude/*` gitignore (WU-2's
  allowed set kept to exactly the two wrappers; `.gitignore` intentionally NOT expanded).
- **Skills + catalog (WU-3, `3f2cbfa9`).** `/qg-rust` + `/qg-sidecar` (haiku, Bash-only) mirror
  the `/tauri-build` shape; cite `runner-outcome-contract.md`, inject the turn-end gate by
  `!cat`, note the light siblings (`-- ts|docs`) stay DIRECT. `skill-catalog.md` +2 rows.
  Projection + `lint-skills.py --check-projected --check-capabilities` + `lint-skill-config.py`
  all exit 0.

- **LIVE-FIRE (WU-4 — first-ever queue-on-AlgoBooth exercise; runtime evidence).** Launched from
  cwd `C:\Users\Jacob\repos\AlgoBooth` (manifest resolution requirement).
  - **`qg-rust` — seq=1, RESULT=PASS.** Enqueue echo (records `lane=heavy` + cold `?` ETA):
    `build-queue: enqueued as seq=1 (op=qg-rust, lane=heavy) position=1 eta-start~0s eta-done~?`.
    The real gate ran (`bash scripts/quality-gate.sh rust` → the 7 rust gates). Authoritative
    LAST line (from both `build-queue.ps1` and the `build-queue-await.ps1 -Seq 1` re-emit,
    await exit 0):
    `build-queue: seq=1 op=qg-rust RESULT=PASS (result_fidelity=verified)`.
    `~/.claude/state/build-queue/results/1.json`:
    `{"seq":1,"exit_code":0,…,"hygiene":{"status":"complete","result_fidelity":"verified",
    "build_fidelity":"n/a",…},"op":"qg-rust","duration_seconds":340}`.
  - **`qg-sidecar` — seq=2, RESULT=FAIL (acceptable PLUMBING evidence).** Enqueue echo:
    `build-queue: enqueued as seq=2 (op=qg-sidecar, lane=heavy) …`. The real gate ran all 3
    sidecar sub-gates; `sidecar-build` PASSED, `sidecar-test` FAILED with genuine test failures
    (`StrudelRegistryParity` + `TutorialSnippetEval` — `ReferenceError: link is not defined`).
    The failing exit propagated through the wrapper's `exit $LASTEXITCODE`:
    `build-queue: seq=2 op=qg-sidecar RESULT=FAIL (result_fidelity=verified) -> read logs/2.build.err.log`
    (`build-queue-await.ps1 -Seq 2` re-emitted it, await exit 1). `results/2.json`:
    `{"seq":2,"exit_code":1,…,"result_fidelity":"verified",…,"op":"qg-sidecar",
    "duration_seconds":45.4}`. This is a qg-code FAIL, NOT a plumbing failure — the gate ran, the
    exit propagated, the banner + result were recorded — i.e. correct PLUMBING (the queue contract
    under test, not AlgoBooth's code quality).
  - **`lane=heavy` observation:** surfaced on both enqueue echoes (`lane=heavy`) and via
    `/build-queue-status` while seq=1 was active (Active Build op=qg-rust). Cold `eta-done~?` /
    `remaining~ ?` as expected with <3 samples.
  - **Live deny check — REAL hook + REAL manifest, no override (armed naturally on nt).** Fired
    `user/hooks/build-queue-enforce.sh` against PreToolUse payloads (`_bqe_payload` shape):
    - cwd=AlgoBooth `npm run qg -- rust` → **DENY** `BUILD QUEUE ENFORCED — use \`/qg-rust\``
    - cwd=AlgoBooth `npm run qg -- sidecar` → **DENY** naming `/qg-sidecar`
    - cwd=AlgoBooth `npm run qg -- ts` → **ALLOW** (light sibling)
    - cwd=claude-config `npm run qg -- rust` → **ALLOW** (no manifest at claude-config)
    **Honest caveat:** a raw `npm run qg -- rust` issued as an ordinary in-session Bash tool call
    did NOT deny — it ran directly. Root cause: this executing agent is rooted in the claude-config
    project, so its PreToolUse payload `cwd` is the claude-config toplevel (no build-queue manifest
    there) — the DOCUMENTED, ACCEPTED "cd-into-another-repo blind spot" of the manifest-scoped
    enforce hook (root CLAUDE.md build-queue-enforce row), NOT a defect in the deny rows. The deny
    rows themselves fire correctly whenever the hook evaluates with AlgoBooth as the effective repo
    (proven directly above). The accidental raw run completed exit 0 (idempotent checks), no state
    corruption.
- **Gates (per claude-config commit):** WU-1 `gate-battery: run=20260714-0795 RESULT=PASS cmds=7
  failed=0 (elapsed=422s)`; WU-3 `run=20260714-db55 RESULT=PASS cmds=7 failed=0 (elapsed=419s)`.
  ZERO changes under `user/scripts/tests/baselines/`. Cognito byte-untouched guard PASS on every
  claude-config commit (`git show --name-only HEAD` carries nothing under `repos/cognito-forms/`
  or `build-queue*.ps1` / `build-queue-enforce.sh`).
- **Pitfalls / notes for Phase 4:** (1) the seq=1/seq=2 banners + results here are the runtime
  evidence Phase 4's validation table cites — do NOT re-run heavy compiles to re-prove them.
  (2) The D3-precision bare-`npm run qg` residual stays PINNED by an ALLOW fixture — Phase 4 must
  not widen deny rows; ratification pending. (3) `hygiene: none` is the locked re-check value
  Phase 4's root-CLAUDE.md build-queue rows must state.
