# PHASES — subagent-backgrounds-verification-ends-turn-before-green

> Phases for [SPEC.md](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP dev runtime; the deliverables are a standalone PowerShell utility plus skill/component prose, structurally outside any MCP-reachable surface (mcp-testing SPEC: no app-integration surface).

## Validated Assumptions

The plan rests on ONE runtime-coupled assumption:

> `build-queue-await.ps1` reading `results/<seq>.json` and calling `Format-BuildQueueBanner` reproduces the same authoritative banner the wrapper prints at `build-queue.ps1:497`.

This is validated in Phase 1's Pester test by driving the **real** `Format-BuildQueueBanner` (defined at `user/scripts/build-queue-hygiene.ps1:1419`, dot-sourced via the `build-queue.ps1:48` pattern) against a **real** `results/<seq>.json` fixture — a test that crosses the actual filesystem→banner boundary, NOT a static trace or a mocked composer. `Format-BuildQueueBanner` is confirmed pure, side-effect-free, and non-throwing; its params are `-Seq [int]`, `-Op [string]`, `-ExitCode [int]`, `-ResultFidelity [string]`, `-BuildFidelity [string]`, `-Counts [hashtable]` (keys `passed`/`failed`/`total`; the hashtable or any key may be `$null`).

## Completion Evidence

Per the bug pipeline's symptom-reproduction gate:

- **Mechanism half (FIX SITE 1) — unit-provable.** Phase 1's Pester test reproduces the symptom's serving path to GREEN: a backgrounded/deferred `results/<seq>.json` is genuinely blocked-on to presence and the authoritative `RESULT=` banner is re-emitted as the last stdout line with the build's `exit_code`. This is the primary completion evidence — the original symptom ("turn ends on the `enqueued as seq=N` line, never seeing `RESULT=`") is directly negated on its actual serving path.
- **Contract-gate half (FIX SITE 2, Phase 3) — not unit-testable.** The turn-end gate is prose injected into `!cat`-referenced components; it cannot be exercised by a runtime test. It is verified honestly by projection (`project-skills.py` re-expands the injected components without error) + lint (`lint-skills.py` clean). This is a PLAUSIBLE-grade, projection-verified change, not a runtime-VERIFIED one, and is stated as such rather than over-claimed.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes FIXED.md once these phases' verification passes. No phase authors a status/receipt/ROADMAP/archive row.

---

### Phase 1: `build-queue-await.ps1` — followable-wait primitive

**Scope:** Create a net-new standalone PowerShell helper that blocks until a build's `results/<seq>.json` is present, reads its outcome fields, and re-emits the exact authoritative banner by calling the existing `Format-BuildQueueBanner`. This is the followable-wait primitive that both FIX SITE 1 (Phase 2, backgrounded builds) and Gap 2 (foreground builds killed by the 10-min Bash timeout) rely on. It is the only executable artifact in the plan and the only phase that crosses a real boundary (filesystem results-file → banner).

Design to encode:
- Param `-Seq [int]` (required); optional `-TimeoutSeconds`, `-PollIntervalMs`, `-StateRoot` (default `$HOME/.claude/state/build-queue`).
- Resolve `results/<Seq>.json` under `<StateRoot>/results/`.
- Bounded poll until the file is present (honoring `-PollIntervalMs` / `-TimeoutSeconds`).
- On present: read `exit_code`, `op`, `counts`, `hygiene.result_fidelity`, `hygiene.build_fidelity` with defensive/`Get-SafeValue`-style reads (any field may be missing/`$null`); dot-source `build-queue-hygiene.ps1` (same `Join-Path $PSScriptRoot` pattern as `build-queue.ps1:48`); call `Format-BuildQueueBanner`; write the composed banner as the **last** stdout line; exit with the build's `exit_code`.
- On await-timeout: a DISTINCT non-zero exit code (not the build's) + a clear `result not yet present for seq=<N>` message, so the caller keeps waiting / investigates rather than treating absence as success.
- Repo PowerShell conventions: `$null` never `/dev/null`; defensive reads matching the sibling scripts (`build-queue-hygiene.ps1`, `build-queue-runner.ps1`).

**Deliverables:**
- [ ] `user/scripts/build-queue-await.ps1` (net-new) — `-Seq`/`-TimeoutSeconds`/`-PollIntervalMs`/`-StateRoot`, bounded poll on `results/<Seq>.json`, defensive field reads, dot-sources `build-queue-hygiene.ps1`, calls `Format-BuildQueueBanner`, banner as last stdout line, exits with the build's `exit_code`; distinct non-zero exit + `result not yet present for seq=N` on await-timeout.
- [ ] Tests: `user/scripts/build-queue-await.Tests.ps1` (net-new Pester, sibling convention to `user/scripts/build-queue-hygiene.Tests.ps1`) — drives the **real** `Format-BuildQueueBanner` against a **real** fixture `results/<seq>.json`, asserting the re-emitted banner matches the wrapper's authoritative line for PASS / FAIL / NO-TESTS-MATCHED shapes, that exit code mirrors the fixture's `exit_code`, and that a missing results file yields the distinct await-timeout exit + message.

**Minimum Verifiable Behavior:** `Invoke-Pester user/scripts/build-queue-await.Tests.ps1` passes — including the case that writes a fixture `results/<seq>.json` (with `exit_code`, `op`, `counts`, `hygiene.{result_fidelity,build_fidelity}`), runs `build-queue-await.ps1 -Seq <n> -StateRoot <fixture-root>`, and asserts the last stdout line equals the banner produced by the real `Format-BuildQueueBanner` for that fixture, plus the timeout-absent case.

**Prerequisites:** none (foundation phase). Depends only on the already-present `Format-BuildQueueBanner` (`build-queue-hygiene.ps1:1419`) and the confirmed `results/<seq>.json` shape (`build-queue-runner.ps1:248-259`).

**Files likely modified:**
- `user/scripts/build-queue-await.ps1` — **net-new (create)**
- `user/scripts/build-queue-await.Tests.ps1` — **net-new (create)**

**Testing Strategy:** TDD=yes. Write the Pester spec first (RED) against the intended banner-parity + timeout-exit behavior, then implement the script to GREEN. The test drives the real component across the real filesystem boundary (fixture results-file → banner), satisfying the Validated Assumptions note above.

**MCP Integration Test Assertions:** N/A — no runtime-observable MCP surface in claude-config (see MCP runtime header).

**Integration Notes for Next Phase:** Phases 2 and 3 reference this helper by path (`user/scripts/build-queue-await.ps1`) and by its contract: run it with `-Seq N`, trust its last-line banner and exit code, treat a distinct non-zero (timeout) exit as "keep waiting", never as success. This phase's Pester test is the load-bearing proof of the one runtime-coupled assumption; downstream phases add no new runtime surface.

---

### Phase 2: Wire the 4 queue skills to the helper (FIX SITE 1)

**Scope:** Rewrite the §4 (step "4.") background-fallback prose in each of the four Cognito build-queue SKILL.md files so the unenforced "then poll results/<seq>.json" instruction becomes ONE uniform, mechanical instruction: run `user/scripts/build-queue-await.ps1 -Seq N` (seq taken from the `build-queue: enqueued as seq=N` return line) and trust ITS re-emitted banner + exit code as authoritative. Also add Gap 2 recovery: a FOREGROUND build whose wrapper is killed by the 10-min Bash timeout before the banner prints uses the same helper against the seq from its `enqueued as seq=N` line. File-disjoint from Phase 3.

**Deliverables:**
- [ ] `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` — §4 rewritten to run `build-queue-await.ps1 -Seq N` + Gap 2 (foreground-timeout) recovery.
- [ ] `repos/cognito-forms/.claude/skills/mstest/SKILL.md` — same §4 rewrite + Gap 2.
- [ ] `repos/cognito-forms/.claude/skills/nxbuild/SKILL.md` — same §4 rewrite + Gap 2.
- [ ] `repos/cognito-forms/.claude/skills/nxtest/SKILL.md` — same §4 rewrite + Gap 2.
- [ ] Tests: none (docs-only prose change; verified by lint + projection — see MVB).

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/lint-skills.py` runs clean AND `python ~/.claude/scripts/project-skills.py` re-projects the affected skills without error (these are standalone SKILL.md files, not injected components, so lint clean + successful re-projection is the check). Manual read confirms all four §4 sections carry the identical `build-queue-await.ps1 -Seq N` instruction and Gap 2 foreground-timeout recovery.

**Prerequisites:** Phase 1 (references `build-queue-await.ps1` by path/contract).

**Files likely modified:**
- `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` (verified; background-fallback prose is §4 / step "4.")
- `repos/cognito-forms/.claude/skills/mstest/SKILL.md` (verified; §4)
- `repos/cognito-forms/.claude/skills/nxbuild/SKILL.md` (verified; §4)
- `repos/cognito-forms/.claude/skills/nxtest/SKILL.md` (verified; §4)

**Testing Strategy:** TDD=no. Prose/skill change with no executable surface; correctness is enforced by `lint-skills.py` (no broken injections / embedded patterns) and by `project-skills.py` re-projecting cleanly, plus a uniformity read across the four files.

**MCP Integration Test Assertions:** N/A — no runtime-observable MCP surface in claude-config (see MCP runtime header).

**Integration Notes for Next Phase:** Parallel-eligible with Phase 3 (file-disjoint: Phase 2 touches only the four SKILL.md files; Phase 3 touches only the three contract components). Both share Phase 1's helper as their referenced mechanism.

---

### Phase 3: Subagent turn-end gate (FIX SITE 2a+2b)

**Scope:** Add an explicit turn-end gate to the three subagent contract files. Today the "confirm GREEN before ending your turn" obligation exists only implicitly as a report-format requirement (paste a GROUND-TRUTH block); no gate forbids ending a turn on a backgrounded/incomplete build. Add a gate stating: the build/tests must be **COMPLETED** (never left backgrounded) AND **GREEN**, with the completed pass/fail summary pasted, BEFORE the agent ends its turn / produces its report — and reference `user/scripts/build-queue-await.ps1` as the mechanism that turns a backgrounded/timeout-killed enqueue into a followable, completed result. Prose-only (v1); the mechanical Stop-hook backstop is explicitly deferred. File-disjoint from Phase 2.

**Deliverables:**
- [ ] `user/skills/_components/implementation-agent.md` — turn-end gate added in the §Verification area (~line 29) and immediately before the required-report block (~line 104), referencing `build-queue-await.ps1`.
- [ ] `user/skills/_components/tdd-test-agent.md` — turn-end gate added in the §Verification / RED-state capture area (~line 21).
- [ ] `repos/cognito-forms/.claude/skills/write-plan-cognito/lane-agent-briefing.md` — turn-end gate added at GREEN-capture (~line 27) and in the GROUND-TRUTH block (~line 86).
- [ ] Tests: none (prose contract; verified by projection + lint — see MVB).

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/project-skills.py` re-projects the affected components without error (these files are `!cat`-injected into consuming skills, so successful projection of the resolved output is the load-bearing check that no injection broke) AND `python ~/.claude/scripts/lint-skills.py` runs clean. Manual read of the projected output confirms the turn-end gate text ("COMPLETED, never backgrounded" + "GREEN with pass/fail summary pasted" + `build-queue-await.ps1` reference) appears in each consuming skill.

**Prerequisites:** Phase 1 (references the helper as the gate's mechanism).

**Files likely modified:**
- `user/skills/_components/implementation-agent.md` (verified; §Verification ~line 29 + before required-report block ~line 104)
- `user/skills/_components/tdd-test-agent.md` (verified; §Verification / RED-state capture ~line 21)
- `repos/cognito-forms/.claude/skills/write-plan-cognito/lane-agent-briefing.md` (verified; GREEN-capture ~line 27 + GROUND-TRUTH block ~line 86)

**Testing Strategy:** TDD=no. Contract-gate prose cannot be unit-tested; verified by projection (the load-bearing check for `!cat`-injected components) + lint, as stated in the Completion Evidence note.

**MCP Integration Test Assertions:** N/A — no runtime-observable MCP surface in claude-config (see MCP runtime header).

**Integration Notes for Next Phase:** Terminal phase. Parallel-eligible with Phase 2 (file-disjoint). A mechanical Stop-hook backstop enforcing this gate is explicitly OUT of scope for v1 and deferred to a possible follow-up — do not add a hook phase here.

---

## Review Notes

**Review verdict:** PASS (2026-07-09) — /spec-phases Step 6 inline review (1-file batch). All three SPEC fix sites + Gap 2 covered; locked decisions honored (await-helper mechanism, prose-gate-only, no hook phase); clean Phase 1 → {2,3} DAG with Phase 2 ∥ Phase 3 verified file-disjoint; authoring rules (MCP-runtime header, no gate-owned rows, N/A MCP assertions, honest PLAUSIBLE-grade completion evidence for the prose half) all satisfied. Ready for /plan-bug (or /fix).
