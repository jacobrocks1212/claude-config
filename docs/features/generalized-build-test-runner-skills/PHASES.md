# Implementation Phases — Generalized Build/Test Runner Skills

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Not started — planned 2026-07-13; execution gated on hard dep `lazy-core-package-decomposition` (SPEC L7; machine-enforced via the queue `deps` field, synced 2026-07-13)
**MCP runtime:** not-required — docs + CLI/pytest/Pester surfaces only; claude-config has no MCP server (Step 9 exemption via operator-granted `SKIP_MCP_TEST.md` per `.claude/skill-config/quality-gates.md`; SPEC L8)
**Friction-reduction feature:** yes — KPI rows `generalized-runner-raw-invocation-deny-recurrence` + `runner-turn-end-stall-recurrence` (full-schema drafts in SPEC `## KPI Declaration`; registered into `docs/kpi/registry.json` at Phase 4)
**Last updated:** 2026-07-13

## Cross-feature Integration Notes

Phase-level dependencies on completed upstream features, extracted during /spec-phases Step 1.5.
Phase plans below MUST honor these; deviations require /realign-spec before implementation.

- **build-queue-generalization (kind=hard, Complete)** `(no PHASES.md — verify against SPEC.md and
  COMPLETED.md)`: locked the contracts Phase 3 extends — the per-repo
  `build-queue-ops.json` schema (`{version, ops: {<op>: {exec, kind, hygiene, skill, deny, lane}}}`),
  `Resolve-BuildQueueOp` (exec resolved repo-root-relative from the manifest; `-Exec` an override),
  the manifest-scoped `build-queue-enforce.sh` deny compile (`_compile_manifest_deny`,
  `user/hooks/build-queue-enforce.sh:488`), locked D4 (Cognito legacy fallback) and D7
  (workstation-only; `BQE_PLATFORM_OVERRIDE` test seam). Its `COMPLETED.md` documents an
  OUTSTANDING gap this feature inherits: **the AlgoBooth exec scripts
  (`.claude/scripts/tauri-build-filtered.ps1` / `cargo-release-filtered.ps1`) DO NOT EXIST** and
  no AlgoBooth op has ever been live-fired through the queue — Phase 3's live-fire is the FIRST
  runtime exercise of the queue-on-AlgoBooth path (risk flagged in Phase 3).
- **build-queue-eta-priority-lanes (kind=soft, Complete):** the manifest `lane` field and per-op
  ETA/stats mechanics exist; the new qg ops declare `lane: "heavy"` and ride them with zero
  runner/status changes.
- **lazy-core-package-decomposition (kind=hard, In-progress — NOT Complete, skipped per Step 1.5):**
  nothing settled to integrate against yet; SPEC L7 sequences implementation AFTER it completes
  (the dep-gate enforces this). Two facts already landed and consumed here: its Phase 3 shipped
  the `user/scripts/tests/` layout (new tests go there), and the battery manifest is authored as
  **commands, not file paths** (SPEC L5) precisely so its remaining Phases 4–6 layout churn cannot
  invalidate this feature.

## Validated Assumptions — planning-time capability audit (2026-07-13)

SPEC-example capability audit (per `_components/phases-runtime-validation.md`): every surface the
SPEC's code examples consume, negative-evidence-grepped on disk this session.

| Construct / surface | Confirmed | Evidence (how-confirmed: grep/read) |
|---|---|---|
| `_components/turn-end-gate.md` (referenced, never copied) | yes | file exists, 2.4KB (Round 39 canonical) |
| `Format-BuildQueueBanner` | yes | `user/scripts/build-queue-hygiene.ps1:2275` |
| `build-queue-await.ps1` exits 124/125 | yes | exit 124 @ line 99; exit 125 @ lines 69/96/122 |
| Enforce-hook per-op deny compile | yes — **with a NEGATIVE finding** | `_compile_manifest_deny` @ `user/hooks/build-queue-enforce.sh:488`: a non-`.ps1` deny entry is `re.escape`-tokenized, `\s+`-joined, anchored `_CMD_START … (?:\s\|$)`. **No allow-list / negative-lookahead mechanism exists for manifest ops** (`_suppress_safe` covers only the hard-coded dotnet/nx safe forms). Therefore a bare `npm run qg` deny row PROVABLY shadows `npm run qg -- ts` — the exact D3 false-deny risk. Resolution: D3-precision provisional decision (see `NEEDS_INPUT_PROVISIONAL.md`): deny ONLY exact heavy forms; bare `npm run qg` stays advisory. |
| AlgoBooth `build-queue-ops.json` (tauri-build/cargo-release, deny, lane) | yes | live path is a SYMLINK → authored at `repos/algobooth/.claude/skill-config/build-queue-ops.json` in this repo |
| AlgoBooth `.claude/skills` symlinked from this repo | yes | `C:\Users\Jacob\repos\AlgoBooth\.claude\skills -> repos/algobooth/.claude/skills` |
| AlgoBooth `.claude/scripts/` | **does not exist** (repo-local surface, NOT symlinked) | `ls` miss; `build-queue-generalization/COMPLETED.md` documents the wrappers as outstanding onboarding work. Phase 3 creates the qg wrappers IN the live AlgoBooth repo. |
| AlgoBooth `QG_VERDICT:` banner + never-pipe-through-tail | yes | `repos/algobooth/.claude/skill-config/quality-gates.md:10-16` |
| AlgoBooth npm alias `quality-gate` ≡ `qg` | yes — widens the deny surface | `package.json:55-56` — both map to `bash scripts/quality-gate.sh`; deny rows must cover BOTH alias spellings (exact heavy forms) |
| stdlib argparse/subprocess/json/pathlib | yes | Python 3 stdlib; no negative evidence |
| `user/scripts/tests/` pytest layout | yes | exists (decomposition Phase 3 Complete) |
| Canonical repo-key convention | yes | `lazy_core/statedir.py:88` `repo_key` (SHA-1 of normalized realpath). The runner keeps a PRIVATE copy with a keep-in-sync comment (stdlib-only per L4; same precedent as `phases-slice.py`'s private `_PHASE_HEADING_RE`). |
| CLI-surface roster (one-line addition) | yes | `ROSTER` @ `user/scripts/cli_surface_gen.py:34`; helpers in `user/scripts/cli_surface.py` |

**MCP tool-existence audit: NO-OP** — no `.claude/skill-config/mcp-tool-catalog.md` configured for
claude-config, and SPEC L8 declares "Required MCP tooling: none". Recorded per the component's
catalog-absent rule.

**Runtime-coupled load-bearing assumptions** (each scheduled, none riding unverified):

1. *Reachability axiom* — agents can reach each new surface end-to-end: `gate-battery.py` CLI
   (Phase 1 dogfood run), `/gate-battery` skill (Phase 2 invocation), `/qg-rust`//`qg-sidecar`
   queue path (Phase 3 live-fire — scheduled in the SAME phase that creates the surface).
2. *Light ops don't contend* — observed live 2026-07-13 (concurrent batteries all session;
   RESEARCH_SUMMARY finding 5). Cited, not re-derived.
3. *The queue-on-AlgoBooth path works at all* — NEVER live-fired (upstream receipt says so).
   Phase 3 WU-4 is the explicit early validation spike; evidence = the recorded
   `build-queue: seq=N op=qg-rust RESULT=…` banner + `results/<seq>.json`, not a code trace.
4. *qg heavy gates need no artifact hygiene* (`hygiene: none`, SPEC Open Question 4) — Phase 3
   WU-1 re-checks qg's cargo invocations against shared-target-dir poisoning BEFORE the manifest
   rows land; the decision is recorded in Implementation Notes.
5. *Cloud battery parity* — the runner must behave identically with no PowerShell present.
   Proxied mechanically in Phase 1 (pytest asserts zero PS invocations on the runner's code
   path); the real cloud-session run is a deferred verification row in Phase 4.

---

### Phase 0: Runner-outcome contract (docs-only, cloud-safe)

**Status:** Complete (2026-07-14, commit cd0efba1)

**Scope:** Author the generalization deliverable — the ONE documented contract
(`user/skills/_components/runner-outcome-contract.md`, SPEC D1/L1) — plus its
`user/scripts/CLAUDE.md` pointer. No code.

**Deliverables:**
- [x] `user/skills/_components/runner-outcome-contract.md` (new component) specifying,
      surface-neutrally: (1) the authoritative LAST-stdout-line banner grammar
      (`<runner>: <run-key> [op=<op>] RESULT=<…> [counts] [(fidelity)] [-> next-action]`) with
      the three conforming instances — `build-queue:` (existing), `QG_VERDICT:` (existing,
      grandfathered verbatim), `gate-battery:` (new, exact grammar from SPEC D1); (2) followable
      await semantics — re-emit the same banner as the await's last line, exit = the run's own
      exit code, reserved exits 124 (not-yet, NEVER success) / 125 (malformed); (3) the turn-end
      gate BY REFERENCE to `_components/turn-end-gate.md` — never copied; (4) the
      never-pipe-through-tail rule (generalized from AlgoBooth quality-gates.md); (5) the seam
      statement — the cross-repo seam is this documented grammar, not shared code (D4); (6) the
      D8 AlgoBooth path-discovery note incl. the one-line `~/.claude/lazy-repos.json` fleet-pin
      recipe (documented, not implemented).
- [x] Pointer to the contract in `user/scripts/CLAUDE.md` as a PROSE paragraph (NOT a script-table
      row — `doc-drift-lint.py` asserts script-table rows map doc→disk to `user/scripts/` files;
      the component is not a script; the script-table row lands with the runner in Phase 1).
- [x] Tests: `python user/scripts/project-skills.py` + `python user/scripts/lint-skills.py`
      clean (no broken/circular includes); `doc-drift-lint.py --repo-root .` exit 0.

**Minimum Verifiable Behavior:** `python user/scripts/lint-skills.py` exits 0 with the new
component present, and `grep -c "turn-end" user/skills/_components/runner-outcome-contract.md`
shows a reference line while `grep "may not end while work" …/runner-outcome-contract.md`
returns ZERO hits (gate referenced, not copied).

**Prerequisites:** None (first phase). NOTE: the whole feature's *execution* is dep-gated on
`lazy-core-package-decomposition` completing (SPEC L7).

**Files likely modified:**
- `user/skills/_components/runner-outcome-contract.md` — new
- `user/scripts/CLAUDE.md` — prose pointer paragraph

**Testing Strategy:** docs-only — projection + skill lint + doc-drift; the grammar itself is
pinned by Phase 1's runner tests (both sides cite the contract).

**Integration Notes for Next Phase:**
- Phase 1's banner/`--await` tests assert the EXACT grammar this component locks — author the
  grammar strings once here and quote them in the Phase 1 tests verbatim.
- The pointer paragraph placement (prose, not table row) is deliberate; Phase 1 adds the real
  script-table row for `gate-battery.py` in the same commit as the script (doc-drift same-commit
  discipline).

---

### Phase 1: Battery runner + manifest + pytest (cloud-safe)

**Scope:** `user/scripts/gate-battery.py` (stdlib-only, manifest-driven, contract-conformant) +
the seeded claude-config `.claude/skill-config/gate-battery.json` + pytest suite. SPEC D4/D5/L4/L5.

**Deliverables:**
- [ ] `user/scripts/gate-battery.py` (new, stdlib-only — argparse/subprocess/json/pathlib/hashlib):
      reads `.claude/skill-config/gate-battery.json` at the INVOKING repo's git toplevel
      (`{version: 1, gates: [{id, cmd, cwd?}]}`); **refuses with exit 2 and a one-line reason,
      zero state written, when no manifest exists** (L5 — manifest-less repo unaffected by
      construction); runs gates sequentially via subprocess, streaming their output; prints as
      its LAST stdout line the banner
      `gate-battery: run=<id> op=battery RESULT=<PASS|FAIL> cmds=<n> failed=<k> (elapsed=<s>s) [-> first failing gate: <id>]`;
      exit 0 all-green / 1 on any failure; writes
      `~/.claude/state/gate-battery/<repo-key>/results/<run-id>.json` (repo key = private copy of
      the `lazy_core/statedir.py:88` SHA-1 convention with a keep-in-sync comment; run-id
      `<UTC yyyymmdd>-<4 hex>`); state-dir-unwritable degrades gracefully — banner still prints,
      `-> next-action` notes await unavailable; **zero PowerShell invocations on any code path**
      (cloud-compatible per L4).
- [ ] `--await <run-id>`: re-emits the run's banner as ITS last stdout line and exits with the
      run's own exit code; exit **124** when the result is not yet present (never success);
      exit **125** on a malformed/unreadable result file. Mirrors `build-queue-await.ps1`
      semantics per the Phase 0 contract.
- [ ] Seed `.claude/skill-config/gate-battery.json` in claude-config with the 7-command battery
      **as commands** (pytest `user/scripts/`, `lazy-state.py --test`, `bug-state.py --test`,
      `lazy_parity_audit.py --repo-root .`, `cli_surface_gen.py --check --repo-root .`,
      `doc-drift-lint.py --repo-root .`, `lint-skills.py`), interpreter spelling verified to work
      on BOTH Windows and cloud at the dogfood run.
- [ ] CLI-surface registration: adopt `cli_surface.py`'s `DidYouMeanArgumentParser` +
      `--dump-cli-surface`, add the one-line `ROSTER` entry in `cli_surface_gen.py`, regenerate
      `docs/cli/cli-surface.json` in the same commit (keeps `cli_surface_gen.py --check` green).
- [ ] `user/scripts/CLAUDE.md` script-table row for `gate-battery.py` (same commit — doc-drift).
- [ ] Tests: `user/scripts/tests/test_gate_battery.py` (TDD; fixture manifests + fixture state
      dirs in tmp): manifest-less refusal (exit 2, zero state); banner grammar last-line
      PASS and FAIL(+first-failing-gate); results-file shape; `--await` in-flight → 124 with no
      success language; `--await` done → banner re-emit + run's exit; corrupted result → 125;
      state-dir-unwritable degradation; no-PowerShell proxy (no `powershell`/`pwsh` token on the
      runner's execution path).

**Minimum Verifiable Behavior:** `python3 user/scripts/gate-battery.py --repo-root .` in this
repo runs all 7 gates and prints `gate-battery: run=… op=battery RESULT=PASS cmds=7 failed=0 …`
as its last stdout line, exit 0 (the dogfood run — doubles as this phase's pre-commit battery).

**Prerequisites:**
- Phase 0: the contract component exists (tests quote its grammar verbatim).

**Files likely modified:**
- `user/scripts/gate-battery.py` — new
- `user/scripts/tests/test_gate_battery.py` — new
- `.claude/skill-config/gate-battery.json` — new (this repo's seed)
- `user/scripts/cli_surface_gen.py` — one-line ROSTER addition
- `docs/cli/cli-surface.json` — regenerated
- `user/scripts/CLAUDE.md` — script-table row

**Testing Strategy:** pytest (all behaviors above are CLI-verifiable against fixture manifests /
fixture result dirs — no live system needed except the dogfood run, which the per-commit battery
provides for free).

**Integration Notes for Next Phase:**
- The skill (Phase 2) must trust the banner and never grep gate output — the runner's stdout
  streams gate output ABOVE the banner by design; the banner line is the only parse surface.
- Exit-code vocabulary the skill documents: 0 pass, 1 fail, 2 no-manifest (clean refusal),
  124/125 await-reserved.
- If a gate command's own exit is 124/125 the await still reports it faithfully (same accepted
  ambiguity as `build-queue-await.ps1`; documented in the contract, not special-cased).

---

### Phase 2: `/gate-battery` thin skill (cloud-safe)

**Scope:** user-level skill wrapping the runner (SPEC D6), generic across repos.

**Deliverables:**
- [ ] `user/skills/gate-battery/SKILL.md` (new): announce + run
      `python3 ~/.claude/scripts/gate-battery.py --repo-root <repo>`; TRUST the banner (never
      grep gate output or `results/*.json` to disambiguate); backgrounding contract — a long
      battery may run with `run_in_background`, then MUST be followed to the banner via
      `--await <run-id>` (124 = still going, re-await); carries the turn-end gate **by
      reference** (`!cat ~/.claude/skills/_components/turn-end-gate.md` injection — no copied
      gate text in the source); documents the exit-2 clean refusal in manifest-less repos and the
      opt-in recipe (commit a `gate-battery.json`); cloud note (no PowerShell, no queue).
- [ ] Skill-config reference hygiene: the skill's `.claude/skill-config/gate-battery.json`
      mention carries an explicit absent-is-fine fallback form so
      `lint-skill-config.py --repo-root .` stays exit 0 (add `intended_absent` rows to repo
      MANIFESTs only if the lint still flags it).
- [ ] Tests: `project-skills.py` re-projection clean; `lint-skills.py --check-projected
      --check-capabilities` exit 0; grep proves the turn-end gate is injected, not duplicated.

**Minimum Verifiable Behavior:** invoking `/gate-battery` in this repo (workstation, interactive)
runs the battery and reports the authoritative banner; the projected
`skills-projected/_default/gate-battery/SKILL.md` shows the turn-end gate expanded from the
component.

**Prerequisites:**
- Phase 1: runner + seeded manifest exist.

**Files likely modified:**
- `user/skills/gate-battery/SKILL.md` — new
- (conditional) `repos/*/.claude/skill-config/MANIFEST.json` — `intended_absent` rows only if the
  reference lint flags the new mention

**Testing Strategy:** skill lint + projection + skill-config reference lint; behavioral surface
is Phase 1's (already pytest-pinned).

**Integration Notes for Next Phase:**
- Phase 3's `/qg-rust` / `/qg-sidecar` skills mirror the EXISTING `/tauri-build` shape (queue
  enqueue + `build-queue-await.ps1`), NOT this skill's shape — light vs heavy op classes (L2)
  produce deliberately different wrappers; both reference the same Phase 0 contract.

---

### Phase 3: AlgoBooth heavy qg ops (workstation)

**Scope:** additive `qg-rust`/`qg-sidecar` manifest ops + exec wrappers + deny rows + repo-scoped
thin skills (SPEC D2/D3/D7 + the D3-precision provisional decision). First-ever live-fire of the
queue-on-AlgoBooth path.

**Authoring-surface map (verified 2026-07-13 — two repos, three surfaces):**
- Manifest + skills + skill-catalog: authored in THIS repo under `repos/algobooth/.claude/`
  (symlink targets for the live repo's `.claude/skill-config` + `.claude/skills`).
- Exec wrappers: authored IN the live AlgoBooth repo (`C:\Users\Jacob\repos\AlgoBooth\.claude\scripts\`
  — the dir does not exist yet and is NOT symlinked; cross-repo commit in AlgoBooth per its
  commit policy). Precedent gap noted: the tauri/cargo wrappers are ALSO still missing (upstream
  receipt); authoring those is OUT of scope — qg wrappers only.
- Hook fixture tests: `user/scripts/test_hooks.py` in this repo (additive; `BQE_PLATFORM_OVERRIDE`
  armed seam).

**Deliverables:**
- [ ] Hygiene re-check (SPEC Open Question 4) BEFORE the manifest rows: inspect
      `scripts/quality-gate.sh rust|sidecar` for cargo target-dir writes; record `hygiene: none`
      confirmation (or the escalation to `rust-tauri`) in Implementation Notes.
- [ ] Manifest rows in `repos/algobooth/.claude/skill-config/build-queue-ops.json`: `qg-rust` +
      `qg-sidecar` — `kind: "test"`, `hygiene:` per the re-check, `lane: "heavy"`,
      `skill: "/qg-rust"|"/qg-sidecar"`, `exec: ".claude/scripts/qg-rust-filtered.ps1"|"…sidecar…"`,
      `deny`: **EXACT heavy forms only** (D3-precision): `npm run qg -- rust`,
      `npm run qg -- sidecar`, `npm run quality-gate -- rust`, `npm run quality-gate -- sidecar`.
      Bare `npm run qg` is NOT denied (provisional; see `NEEDS_INPUT_PROVISIONAL.md` D3-precision).
- [ ] Hook fixture tests (TDD) in `user/scripts/test_hooks.py`: with a tmp-repo manifest carrying
      the new ops — DENY `npm run qg -- rust`, `npm run qg -- sidecar` (incl. a chained
      `cd … && npm run qg -- rust` segment) with the redirect naming the op's skill; ALLOW
      `npm run qg -- ts`, `npm run qg -- docs`, **bare `npm run qg`** (the pinned documented
      residual), and `BUILD_QUEUE_BYPASS=1 npm run qg -- rust`.
- [ ] Exec wrappers `C:\Users\Jacob\repos\AlgoBooth\.claude\scripts\qg-rust-filtered.ps1` +
      `qg-sidecar-filtered.ps1` (new, thin): run `npm run qg -- rust|sidecar` from the repo root,
      stream output, exit with the underlying exit code (the runner records it; the qg wrapper's
      own `QG_VERDICT:` line rides the log).
- [ ] Repo-scoped skills `repos/algobooth/.claude/skills/qg-rust/SKILL.md` +
      `qg-sidecar/SKILL.md`, same shape as `/tauri-build`: enqueue via
      `build-queue.ps1 -Op qg-rust|qg-sidecar`, trust the `build-queue:` banner, follow
      backgrounded runs via `build-queue-await.ps1 -Seq <N>`, turn-end gate by reference.
      Update `repos/algobooth/.claude/skill-config/skill-catalog.md`.
- [ ] Live-fire validation spike (runtime evidence REQUIRED — a static trace does NOT satisfy
      this): on the workstation, `build-queue.ps1 -Op qg-rust` in AlgoBooth → record the
      authoritative `build-queue: seq=<N> op=qg-rust RESULT=…` last line +
      `results/<seq>.json`; `build-queue-await.ps1 -Seq <N>` re-emits the banner; live hook
      check — raw `npm run qg -- rust` denied naming `/qg-rust`, raw `npm run qg -- ts` allowed.
- [ ] Tests: full 7-command battery green on every claude-config commit; `lint-skill-config.py
      --repo-root .` exit 0; `lint-skills.py` + projection green (new repo-scoped skills).

**Minimum Verifiable Behavior:** `build-queue.ps1 -Op qg-rust` in AlgoBooth prints
`build-queue: seq=<N> op=qg-rust RESULT=<PASS|FAIL> …` as its last stdout line and the result is
recorded in `~/.claude/state/build-queue/results/<seq>.json`.

**Prerequisites:**
- Phase 0: contract (the skills cite it).
- Workstation session (locked D7 — queue ops never run in cloud). Cloud-cycle handling: this
  phase is `DEFERRED_NON_CLOUD` class if picked up by a cloud orchestrator.

**Files likely modified:**
- `repos/algobooth/.claude/skill-config/build-queue-ops.json` — two additive op entries
- `repos/algobooth/.claude/skill-config/skill-catalog.md` — two rows
- `repos/algobooth/.claude/skills/qg-rust/SKILL.md`, `…/qg-sidecar/SKILL.md` — new
- `user/scripts/test_hooks.py` — additive fixture tests
- `C:\Users\Jacob\repos\AlgoBooth\.claude\scripts\qg-{rust,sidecar}-filtered.ps1` — new (AlgoBooth repo commit)

**Testing Strategy:** hook fixtures (deterministic, tmp-repo manifests, platform-override seam)
for the deny surface; live-fire for the queue path (first-ever AlgoBooth queue exercise — runtime
artifact recorded in Implementation Notes); the enforce hook itself is byte-untouched (L6 guard).

**Integration Notes for Next Phase:**
- Whatever `hygiene` value the re-check locked, Phase 4's docs (root CLAUDE.md build-queue rows)
  must state it.
- The live-fire seq numbers + banner lines recorded here are the runtime evidence Phase 4's
  validation table cites — don't re-run heavy compiles in Phase 4 just to re-prove them.
- The D3-precision residual (bare `npm run qg` un-denied) is PINNED by an ALLOW fixture test —
  Phase 4 must not "fix" it by widening deny rows; ratification is pending.

---

### Phase 4: Validation + docs + KPI wiring (mixed)

**Scope:** dogfood, Cognito-untouched proof, KPI registry rows, doc tables. SPEC Validation
Criteria closure.

**Deliverables:**
- [ ] KPI wiring: append the two full-schema rows from SPEC `## KPI Declaration`
      (`generalized-runner-raw-invocation-deny-recurrence`, `runner-turn-end-stall-recurrence`)
      to `docs/kpi/registry.json`; `python3 user/scripts/kpi-scorecard.py --lint` exit 0;
      re-render `docs/kpi/SCORECARD.md` (rows surface as honest NO-DATA / PENDING-BASELINE).
- [ ] Docs: root `CLAUDE.md` Scripts-table row for `gate-battery.py` + a build-queue row note for
      the two AlgoBooth qg ops; `user/scripts/CLAUDE.md` already carries the runner row (Phase 1)
      — verify; `doc-drift-lint.py --repo-root .` exit 0.
- [ ] Cognito byte-untouched proof (L6): `git diff <pre-feature-baseline>..HEAD --stat --
      repos/cognito-forms user/scripts/build-queue.ps1 user/scripts/build-queue-runner.ps1
      user/scripts/build-queue-hygiene.ps1 user/scripts/build-queue-status.ps1
      user/scripts/build-queue-await.ps1 user/hooks/build-queue-enforce.sh` → EMPTY; record the
      baseline commit hash + the empty output in Implementation Notes.
- [ ] Pester gate (workstation): all 5 `user/scripts/build-queue*.Tests.ps1` suites via
      `Invoke-Pester`; 100% pass expected — if any failure reproduces, re-run the SAME suite at
      the pre-feature baseline commit: identical-at-baseline = environmental (record both runs
      verbatim), new-at-HEAD = a real L6 violation → BLOCKED.
- [ ] Dogfood: one fresh `python3 user/scripts/gate-battery.py --repo-root .` run recorded
      (banner `RESULT=PASS cmds=7 failed=0` — this is also the final commit's gate).
- [ ] Tests: full battery + `lint-skills.py --check-projected --check-capabilities` +
      `lint-skill-config.py` + `kpi-scorecard.py --lint` all exit 0 at HEAD.

**Runtime Verification** *(deferred — closed outside /execute-plan)*:
- [ ] <!-- verification-only --> Cloud compatibility: a battery run in a cloud session (no
      PowerShell) produces identical banner/results behavior with zero PS invocations — closed by
      the first cloud-session battery run (e.g. the nightly lazy run) citing its session log;
      mechanically proxied until then by the Phase 1 no-PowerShell pytest.

**Minimum Verifiable Behavior:** the full Phase 4 gate set exits 0 at HEAD in one recorded sweep
(battery banner PASS + Pester all-pass/baseline-identical + empty Cognito diff).

**Completion (gate-owned):** SPEC/PHASES Status flips, the COMPLETED.md receipt, and the ROADMAP
mark are `__mark_complete__`-owned — no checkbox rows for them. Step-9 MCP exemption is the
operator-granted `SKIP_MCP_TEST.md` (`granted_by: operator`, per `.claude/skill-config/quality-gates.md`)
— never pipeline-granted, so it is deliberately NOT a deliverable here.

**Prerequisites:**
- Phases 0–3 complete (Pester + live-fire evidence require the workstation).

**Files likely modified:**
- `docs/kpi/registry.json`, `docs/kpi/SCORECARD.md`
- `CLAUDE.md` (root — Scripts table + build-queue note)
- `docs/features/generalized-build-test-runner-skills/` Implementation Notes

**Testing Strategy:** everything CLI/Pester-verifiable in-session on the workstation; the single
cloud row is a marked verification-only deferral with a named closer.

**Integration Notes:** none (terminal phase). Open Question 2 (AlgoBooth light qg ops registering
a `gate-battery.json` for await coverage) and Open Question 3 (dedicated gate-battery KPI signal
source) remain deliberately unimplemented — v1 scope ends here.

## Implementation Notes

(populated during execution)
