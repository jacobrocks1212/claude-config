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

## Phase 4 — Validation + docs + KPI wiring

#### Implementation Notes (Phase 4)
**Completed:** 2026-07-14 — workstation `DESKTOP-GHTC5K6`. Commits: WU-1 `fc52e868`,
WU-2 `8916bbcc`, WU-3 (this).

- **WU-1 (KPI wiring, `fc52e868`).** Appended the two full-schema rows VERBATIM from SPEC
  `## KPI Declaration` (`generalized-runner-raw-invocation-deny-recurrence` scope=algobooth,
  `runner-turn-end-stall-recurrence` scope=claude-config) to `docs/kpi/registry.json` — existing
  19 rows byte-untouched (19→21). `kpi-scorecard.py --lint` exit 0. Re-rendered
  `docs/kpi/SCORECARD.md`: both rows surface under a new `## generalized-runner` section as honest
  `PENDING-BASELINE` (`0/30d` and `1/30d` current, null baselines by design — NO `--capture-baseline`,
  no signal data yet). The row-count pin in `user/scripts/test_kpi_scorecard.py` was bumped 19→21
  with a documenting comment + a positive id assertion for the two new rows (the file's established
  maintenance pattern — a strengthening, not a gate weakening). SCORECARD churn beyond the two new
  rows (bug-age 13→14, concluded 23→21, canary ages, monolith baseline text) is date-driven signal
  recomputation (scorecard is a pure function of registry+signals+today; last rendered 2026-07-13,
  today 2026-07-14) — the committed `kpi-scorecard.py` was unmodified, so it is expected designed
  behavior, not a wrong-version render.
- **WU-2 (docs, `8916bbcc`).** Surgical root `CLAUDE.md` edits (plan note 6): one Scripts-table row
  for `gate-battery.py` (runner + last-line banner grammar + `--await` 124/125 + manifest opt-in +
  exit vocab + `/gate-battery` skill pointer), plus a one-sentence addendum to the `build-queue.ps1`
  row noting the two new AlgoBooth heavy qg ops (`qg-rust`/`qg-sidecar`, `hygiene: none`,
  `lane: heavy`, exact-heavy-form `deny`; Cognito byte-untouched). `user/scripts/CLAUDE.md` already
  carries the runner row (part 1, 2 mentions) — verified. `doc-drift-lint.py --repo-root .` exit 0
  (the new script-table row maps doc→disk cleanly to `user/scripts/gate-battery.py`).
- **WU-3 validation sweep (this commit) — recorded evidence:**
  - **Dogfood (also the WU-3 commit gate):** `python3 user/scripts/gate-battery.py --repo-root .`
    last stdout line `gate-battery: run=20260714-6097 op=battery RESULT=PASS cmds=7 failed=0
    (elapsed=420s)`, exit 0. (WU-1/WU-2 commit gates recorded PASS banners `run=20260714-abf9`
    and `run=20260714-a2f4`.) NOTE: one intervening battery run (`run=20260714-06be`) reported
    `RESULT=FAIL failed=1 -> first failing gate: pytest` from a TRANSIENT `TestFleetServer`
    server-binding flake (the known-flaky `test_pipeline_visualizer.py::TestFleetServer` class,
    a port/bind race under full-suite parallel load); an immediate standalone `pytest user/scripts/`
    re-run passed 2269/2269 and the battery re-ran GREEN — re-run-to-green per the flaky-test
    protocol, not a real regression.
  - **Cognito byte-untouched proof (L6) — baseline `1a8fb777`** (parent of this feature's first
    commit `16366c8a`). `git diff 1a8fb777..HEAD --stat -- repos/cognito-forms
    user/scripts/build-queue.ps1 user/scripts/build-queue-runner.ps1
    user/scripts/build-queue-hygiene.ps1 user/scripts/build-queue-status.ps1
    user/scripts/build-queue-await.ps1 user/hooks/build-queue-enforce.sh` → **EMPTY** (zero lines).
    Per-commit guard also PASS on every claude-config commit (`git show --name-only HEAD` carries
    nothing under `repos/cognito-forms/` or `build-queue*.ps1` / `build-queue-enforce.sh`).
  - **Pester gate (workstation, Pester 6.0.0) — 4 of 5 suites GREEN, 1 environmental.**
    `build-queue-await.Tests.ps1`, `build-queue-hygiene.Tests.ps1`, `build-queue-status.Tests.ps1`,
    `build-queue.Tests.ps1` → **193 Passed / 0 Failed** aggregate. The known sandbox-environmental
    Job-Object warning fired (`Add-ProcessToBuildJob: failed to assign process to Job Object;
    returning $false`, one of the 3 upstream-documented cases) — its suite still PASSED.
    `build-queue-runner.Tests.ps1` fails at **DISCOVERY** (Total=0, zero assertions run):
    `System.Management.Automation.RuntimeException: BeforeAll is already defined in this block.
    Each block can only have one BeforeAll.` — the file carries two top-level `BeforeAll` blocks
    (lines 33 + 126), Pester-5 valid but rejected by Pester 6.0.0's stricter parser.
    **Verdict = ENVIRONMENTAL, proceed (plan WU-3 step 2 protocol).** PROOF of identical-at-baseline:
    (a) `git diff 1a8fb777..HEAD --stat -- user/scripts/build-queue-runner.Tests.ps1` is **EMPTY**
    (the test file is byte-untouched by this feature); (b) discovery only PARSES the unchanged file
    structure (it never executes the byte-untouched `build-queue-runner.ps1` under test — L6 diff
    also empty); (c) Pester is the same 6.0.0 — so the discovery failure is deterministic and
    provably identical at baseline `1a8fb777`. This is a **NEW environmental class** (Pester-5→6
    major-version discovery incompatibility) distinct from the 3 documented Job-Object cases; it is
    a pre-existing defect in a build-queue `*.Tests.ps1` file that this feature **cannot fix**
    (the file matches the L6 `build-queue*.ps1` protected glob — editing it would trip the
    Cognito byte-untouched guard). Flagged as a harness follow-up (harden-harness spin-off:
    "build-queue-runner.Tests.ps1 has two top-level BeforeAll blocks — fails Pester 6.0.0 discovery").
  - **Lint sweep — all exit 0.** `lint-skills.py --check-projected --check-capabilities` (clean),
    `lint-skill-config.py --repo-root .` (exit 0; 3 suppressed warnings incl. the expected
    script-suppressed `gate-battery.json` cognito-forms dangling-reference — L6 forbids a
    repo-side `intended_absent` there, so a script-owned suppression is the sanctioned avoidance),
    `kpi-scorecard.py --lint` (0 warnings).
- **Completion is gate-owned (plan note c):** SPEC/PHASES `**Status:**` NOT flipped, NO
  `COMPLETED.md` / `SKIP_MCP_TEST.md` written — left to `__mark_complete__` / the operator
  (SKIP_MCP_TEST.md is operator-granted per `.claude/skill-config/quality-gates.md`).
- **Pending manual runtime gate (pending-runtime-gates contract):** the P4 `**Runtime
  Verification**` row (cloud-compatibility battery run with zero PowerShell invocations) stays
  UNCHECKED — it is `<!-- verification-only -->`, closed later by the first cloud-session battery
  run (e.g. the nightly lazy run) citing its session log; mechanically proxied until then by the
  Phase 1 no-PowerShell pytest. **1 MANUAL RUNTIME GATE PENDING — feature not verified
  end-to-end in cloud.**
