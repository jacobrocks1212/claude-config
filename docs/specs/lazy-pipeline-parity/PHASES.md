# Implementation Phases — Lazy Skill-Family Parity

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config harness tooling (Python lint scripts + skill-markdown edits); no Tauri desktop or MCP HTTP server involved.

---

### Phase 1: Close the Known Runtime-Affecting Leaks

**Scope:** Two targeted prose edits to `user/skills/lazy-bug-batch/SKILL.md` that close the two runtime-affecting gaps identified by the full `lazy-batch`→`lazy-bug-batch` audit. No new files, no new infra. Independently shippable — the edits restore behavioral parity in the bug pipeline immediately, and Phase 2's live zero-drift assertion depends on these gaps being closed.

**Deliverables:**
- [x] **F2a cycle-dispatch template fix** (~line 495 of `lazy-bug-batch/SKILL.md`): change the cycle-dispatch `prompt:` line from `prompt: <the probe's cycle_prompt, verbatim>` to `prompt: <the probe's cycle_prompt_ref if present, otherwise cycle_prompt verbatim>`, mirroring the wording already in `user/skills/lazy-batch/SKILL.md` (~line 494). Eliminates the byte-exact-retype transcription-slip class for bug-pipeline cycle dispatches.
- [x] **`dev:kill` run-end teardown in §1c.6**: add a mandatory `npm run dev:kill` on every `--run-end`/terminal path — placed AFTER `bug-state.py --run-end`, BEFORE the `PushNotification` call — matching the structure in `lazy-batch` §1c.6. Annotate as workstation-only / no-op-safe (mirrors the canonical note). Prevents the orchestrator-owned runtime (booted in bug Step 1d.0 for mcp-test cycles) from leaking after run-end.

**Minimum Verifiable Behavior:** Both of the following greps return matches in `lazy-bug-batch/SKILL.md` (zero output = still broken):
```
grep -n "cycle_prompt_ref" user/skills/lazy-bug-batch/SKILL.md
grep -n "dev:kill"         user/skills/lazy-bug-batch/SKILL.md
```

**Verification** *(grep / lint — run by the implementer):*
- [x] `grep -n "cycle_prompt_ref" user/skills/lazy-bug-batch/SKILL.md` — must match ≥1 line in the cycle-dispatch block (~line 495).
- [x] `grep -n "dev:kill" user/skills/lazy-bug-batch/SKILL.md` — must match ≥1 line in the §1c.6 run-end block.
- [x] `python3 user/scripts/lint-skills.py --check-projected` — exits 0 (no regressions to other skills from the edits).

**Prerequisites:** None.

#### Implementation Notes

**2026-06-15 — Phase 1 implemented (lazy-pipeline-parity Part 1 of 4).**
- **Work completed:** Two prose-parity edits to `user/skills/lazy-bug-batch/SKILL.md`, dispatched to one Sonnet impl agent (non-TDD — skill-markdown prose, no executable behavior).
- **F2a cycle-dispatch by-reference:** updated BOTH the consume-and-dispatch prose (now line **425**: "prefer the probe's `cycle_prompt_ref` if present, otherwise the `cycle_prompt` verbatim") AND the Dispatch code block (now line **504**: `prompt: <the probe's cycle_prompt_ref if present, otherwise cycle_prompt verbatim>`). The code-block line mirrors canonical `lazy-batch/SKILL.md` line 579 verbatim. (PHASES cited "~line 495"; actual landed location 504/425 — the cited line was advisory.)
- **`dev:kill` run-end teardown:** inserted a new paragraph in §1c.6 item 2 (halt), AFTER the `bug-state.py --run-end` mandatory paragraph and BEFORE "3. flush" — landing the `npm run dev:kill` fenced block (now line **315**) AFTER `--run-end` and BEFORE the `PushNotification`, exactly per spec. Mirrors canonical `lazy-batch` §1c.6 incl. the ISSUE 4 / d8-effect-chains provenance, the workstation-only/no-op-safe annotation, and the cloud-N/A note. `dev:kill` was 0 matches before this change (confirms genuinely new work).
- **Canonical anchors mirrored:** `lazy-batch/SKILL.md` line 579 (cycle dispatch by-ref) and §1c.6 lines 407–413 (dev:kill teardown). The already-shipped line-84 `dispatch_prompt_ref` meta-dispatch fallback was the pattern reference for the cycle-prompt analog.
- **Files modified:** `user/skills/lazy-bug-batch/SKILL.md` (875 ln after edit, +12/-3).
- **Gate results:** `python3 user/scripts/lint-skills.py --check-projected` → EXIT 0 (no projection regressions); both MVB greps return matches at the correct structural locations. MCP Integration Test: SKIPPED — PHASES declares `MCP runtime: not-required` (claude-config harness tooling, no Tauri/MCP server).
- **Ground-truth verification:** orchestrator independently re-ran `git status --short`, `wc -l`, both greps, and the lint — all matched the subagent's `GROUND-TRUTH OUTPUT` block exactly.
- **Review verdict:** PASS. Ground-truth verified: yes. Both edits mirror canonical wording; no unrelated prose touched; propagation/mount-site checks N/A (pure prose doc).

**Files likely modified / created:**
- `user/skills/lazy-bug-batch/SKILL.md` — two prose edits (cycle-dispatch template, §1c.6 run-end teardown).

**Testing Strategy:** Grep-based verification that the two mechanics are present in the target file at the correct structural locations. Then a full `--check-projected` lint run confirms no component-expansion or projection side-effects were introduced.

**Integration Notes for Next Phase:**
- Phase 2's live zero-drift assertion for `lazy-batch`→`lazy-bug-batch` will fail unless these two gaps are closed. Phase 2 is the mechanical re-verification of Phase 1: the C3 check in the audit engine is exactly what would have caught these gaps — the fixture suite simulates both.
- Do not touch the `lazy-batch-cloud/SKILL.md` `dev:kill` absence here — that is a legitimate, per-pair divergence that will be recorded in Phase 2/3 (not a gap to close).

---

### Phase 2: Registry Schema + Audit Engine + Tests (Proven on the Fully-Audited Pair)

**Scope:** Author the machine-readable parity manifest, build the audit engine (`lazy_parity_audit.py`) implementing checks C1–C6, and write the test suite (`test_lazy_parity.py`) — fixture-based engine tests plus a live zero-drift assertion for the fully-audited `lazy-batch`→`lazy-bug-batch` pair. Phase 2 transitively re-verifies Phase 1 (the live pair must be in-sync for the zero-drift assertion to pass).

**Deliverables:**
- [x] **`user/scripts/lazy-parity-manifest.json`** — the per-pair divergence registry. Must include:
  - `mechanic_sets` keyed by canonical root (`lazy-batch`, `lazy`, `lazy-status`), each containing the full Tier-2 mechanic catalog with `id` and `assert` predicates (regex_present pattern). Seed from the SPEC §Technical Design §1: `cycle-dispatch-by-ref`, `meta-dispatch-by-ref`, `run-end-dev-kill`, `two-gate-terminal`, `output-contract-voice`, `completeness-policy`, `stop-authorization-hc10` for `lazy-batch`; `mark-terminal-two-gate`, `one-skill-per-invocation`, `preflight-first`, `completeness-policy` for `lazy`; `read-only-no-mutation`, `runs-state-script` for `lazy-status`.
  - The **fully-populated** `lazy-batch`→`lazy-bug-batch` pair entry: `canonical`, `derived`, `axis`, `flavor`, `mechanic_set`, `token_substitutions` (lazy-state.py→bug-state.py, COMPLETED.md→FIXED.md, `__mark_complete__`→`__mark_fixed__`), `headings[]` (one entry per canonical `## Step`/`### sub-step` heading with `coverage` ∈ {restated, inherited, divergence} and `reason` where coverage=divergence), and `mechanic_overrides: []` (empty — both mechanics apply to this pair). Divergence entries must include Step 0.52 (validation-readiness pre-screen) and Step 4 (Research Halt / Gemini) with authored reasons per the SPEC audit findings.
  - Stub entries (empty `headings[]`) for the four remaining pairs — filled in Phase 3.
- [x] **`user/scripts/lazy_parity_audit.py`** — importable module + CLI (`--repo-root <path>`, optional `--pair <derived-name>`, exit 0 clean / exit 1 drift). Implements checks C1–C6 per the SPEC §Technical Design §2:
  - **C1** (Tier-1 completeness): every `## Step`/`### sub-step` heading in the canonical has a `headings[]` entry for this pair.
  - **C2** (coverage resolves): a `restated`/`inherited` entry's evidence regex (after token substitution) matches in the derived skill file.
  - **C3** (Tier-2 predicates): every mechanic in the pair's `mechanic_set` (minus `mechanic_overrides` with coverage=divergence) matches in the derived skill file.
  - **C4** (no stale divergence): every `headings[]`/override entry references a heading/mechanic that still exists in the canonical.
  - **C5** (reason hygiene): a divergence entry has a non-empty `reason`; a non-divergence entry has no `reason` field.
  - **C6** (soft/warn): a divergence with a `doc_anchor` field has that anchor text present in the derived skill's prose. Emits a warning, does not affect exit code.
  - Token substitutions applied before all regex matching (canonical vocab → derived vocab, never false-failing on axis differences).
- [x] **`user/scripts/test_lazy_parity.py`** — two test classes:
  - *Fixture-based engine tests* (synthetic canonical/derived pair built in a tmp directory): one test per hard check proving the check fires — missing heading → C1 fails naming the heading + pair; broken pointer regex → C2 fails; missing mechanic → C3 fails; stale divergence entry → C4 fails; reasonless divergence entry → C5 fails. Plus: a `mechanic_override` with coverage=divergence correctly suppresses C3 for that mechanic on the overriding pair (C3 passes despite the mechanic being absent from the derived file). C6 warns (captured in stderr) without failing exit code.
  - *Live zero-drift assertion* for `lazy-batch`→`lazy-bug-batch`: calls `lazy_parity_audit.audit_pair(repo_root, pair_name="lazy-bug-batch")` and asserts zero drift findings. This is the hard gate for the pair; it passes iff Phase 1 is complete and the manifest is correctly populated.

**Minimum Verifiable Behavior:** `pytest user/scripts/test_lazy_parity.py -q` green — specifically: the C3-fixture test fails (C3 fires) when the derived file lacks `cycle_prompt_ref`; the `mechanic_override` fixture suppresses C3 for the overriding pair; and the live `lazy-batch→lazy-bug-batch` zero-drift assertion passes (confirming Phase 1 closed both gaps).

**Verification** *(pytest — run by the implementer):*
- [x] `pytest user/scripts/test_lazy_parity.py -q` — all tests green (fixtures + live pair).
- [x] `python3 user/scripts/lazy_parity_audit.py --repo-root . --pair lazy-bug-batch` — exits 0 (zero drift on the fully-audited pair).
- [x] `python3 user/scripts/lint-skills.py --check-projected` — still exits 0.

**Prerequisites:** Phase 1: Close the Known Runtime-Affecting Leaks (the live pair must be in-sync for the zero-drift assertion to pass).

**Files likely modified / created:**
- `user/scripts/lazy-parity-manifest.json` — new; fully-populated `lazy-batch`→`lazy-bug-batch` pair + stub entries for the other four pairs.
- `user/scripts/lazy_parity_audit.py` — new; importable module + CLI.
- `user/scripts/test_lazy_parity.py` — new; fixture-based engine tests + live pair zero-drift assertion.

**Testing Strategy:** Fixture tests construct minimal synthetic canonical/derived SKILL.md files in a `tmp_path` directory (pytest `tmp_path` fixture) and drive `lazy_parity_audit.audit_pair()` directly — no CLI subprocess, no cross-process risk. Each check is proven in isolation with a minimal breaking case and a passing case. The live assertion drives the same function against the real repo root, so the engine and the manifest are both exercised on production data. Ground-truth assertions are literal: `assert len(findings) == 0` for zero-drift; `assert any("cycle-dispatch-by-ref" in f for f in findings)` for C3.

**Integration Notes for Next Phase:**
- The manifest's stub entries for the four remaining pairs are the Phase 3 input surface. Phase 3 populates each stub with full `headings[]` + `mechanic_overrides` + divergences after running a full audit.
- The engine's C3 check is exactly what would have caught Phase 1's two gaps — the Phase 2 C3-fixture test simulates both (a useful regression anchor).
- Keep `lazy_parity_audit.py` importable (not `__main__`-only) so `test_lazy_parity.py` drives it without subprocess invocation (false-green smell: subprocess tests with `execSync`/`subprocess.run` mask import errors and swallow assertion failures).

#### Implementation Notes

**2026-06-15 — Phase 2 Batch 1 (WU-1: manifest) implemented.**
- **Built:** `user/scripts/lazy-parity-manifest.json` (274 ln), dispatched to one Sonnet impl agent (non-TDD data file — exercised by WU-2's live assertion).
- **`mechanic_sets`:** three roots — `lazy-batch` (7 mechanics), `lazy` (4), `lazy-status` (2) — patterns verbatim from SPEC §Technical Design §1. All 7 `lazy-batch` patterns confirmed to resolve in the derived `lazy-bug-batch/SKILL.md` (incl. `two-gate-terminal` `MCP-coverage audit.*completion-integrity` at L3/L60, and the two Phase-1-closed mechanics `cycle_prompt_ref` / `dev:kill`).
- **`lazy-batch`→`lazy-bug-batch` pair fully populated:** 39 `headings[]` entries (one per canonical `##`/`###` heading — count matches `grep -cE "^#{2,3} "` = 39). 30 restated (each with a token-subbed `evidence` regex verified to grep in the derived file) + 9 divergence (each with a `reason`, no `evidence`). The 9 divergences are the Gemini-research path (Step 0.5 ingest, Step 4 Research Halt + its 5 sub-headings, Step 5 in-session resume) and Step 0.52 validation-readiness pre-screen — the two SPEC-mandated divergences (Step 0.52, Step 4) carry `doc_anchor`s. `token_substitutions` ordered `lazy-state.py`→`bug-state.py` BEFORE `lazy-batch`→`lazy-bug-batch`; `mechanic_overrides: []` (both mechanics apply post-Phase-1).
- **4 stub pairs** present (`lazy-batch-cloud`, `lazy-bug`, `lazy-cloud`, `lazy-bug-status`) with correct `canonical`/`derived`/`axis`/`flavor`/`mechanic_set` and empty `headings[]` — Phase 3 (Part 3) input surface.
- **Review verdict:** PASS. Ground-truth verified: yes (status / wc=274 / JSON 5-pairs-39-headings-9-divergences / canonical heading count all re-run and matched). Definitive validation deferred to WU-2's live zero-drift assertion.

**2026-06-15 — Phase 2 Batch 2 (WU-2: engine + tests, TDD) implemented.**
- **Built (TDD — test agent → impl agent):** `user/scripts/test_lazy_parity.py` (496 ln, 12 tests) written first (RED with `ModuleNotFoundError`), then `user/scripts/lazy_parity_audit.py` (345 ln) written to green.
- **Engine:** importable `audit_pair(repo_root, pair_name, manifest=None)` / `audit_all_pairs(...)` / `load_manifest(...)` + argparse CLI (`--repo-root`, optional `--pair`; exit 1 on findings else 0). Implements C1 (Tier-1 heading completeness), C2 (restated/inherited evidence resolves after token sub), C3 (mechanic predicates, suppressed by `mechanic_overrides` coverage=divergence), C4 (no stale heading/override), C5 (reason hygiene), C6 (soft — stderr-only doc_anchor warning, never in findings). Token substitutions applied to the canonical-vocab side (evidence + mechanic patterns) before `re.search` against the derived file; headings rstrip-normalized; files read with universal newlines. No subprocess; stdlib only.
- **Tests:** 11 fixture engine tests (each check has a firing + passing case; token-sub C2 case; `mechanic_override` suppresses C3; C6 warns via `capsys` without entering findings) + 1 live zero-drift assertion `audit_pair(repo_root, "lazy-bug-batch") == []` driving the real repo + committed manifest. Fixtures build synthetic canonical/derived SKILL.md in `tmp_path` and drive `audit_pair()` directly.
- **Gate results:** `pytest user/scripts/test_lazy_parity.py -q` → 12 passed; `pytest user/scripts/ -q` → 507 passed (no regressions, +12 new); `lazy_parity_audit.py --repo-root . --pair lazy-bug-batch` → exit 0 (2 expected C6 stderr warnings for the Step 0.52 / Step 4 doc_anchors not yet present in bug-batch prose — soft, reconciled in Phase 4). `lint-skills.py --check-projected` → exit 0. MCP test: SKIPPED (`MCP runtime: not-required`).
- **Ground-truth verification:** orchestrator independently re-ran `git status`, `wc -l`, function greps, the parity pytest, and the audit CLI — all matched (one stale `wc -l` in the test agent's report — 430 vs actual 496 — was a mid-edit capture; the substantive RED-tests claim was independently verified true and the file content reviewed in full).
- **Review verdict:** PASS (both batches). Ground-truth verified: yes (engine/CLI/suite re-run); test-agent wc mismatch noted + resolved by orchestrator re-verification. Propagation: new module, no import indirection / no existing-API change. The pytest suite is the live hard gate.

---

### Phase 3: Extend the Registry to the Remaining Four Pairs

**Scope:** For each of the four remaining pairs — `lazy-batch`→`lazy-batch-cloud`, `lazy`→`lazy-bug`, `lazy`→`lazy-cloud`, `lazy-status`→`lazy-bug-status` — run a full Tier-1/Tier-2 audit, author its registry section, fix any genuine gaps discovered, record intentional divergences (including the known `dev:kill`-in-cloud divergence), and extend `test_lazy_parity.py` to assert zero drift across all five pairs. Special attention to the two full-restatement pairs (`lazy`↔`lazy-bug` and `lazy-status`↔`lazy-bug-status`), which have the highest drift risk.

**Deliverables:**
- [x] **`lazy-batch`→`lazy-batch-cloud` registry section** (inherit-by-reference, `repos/algobooth/.claude/skills/`): full `headings[]` audit. Record the **`run-end-dev-kill` mechanic as a legitimate divergence** via `mechanic_overrides` with `reason: "Cloud defers Tauri/MCP and never boots the orchestrator-owned runtime, so there is nothing to tear down at run-end."` — this is the canonical per-pair gap-vs-divergence example from the SPEC. Close any genuine gaps found (the spot-check found `cycle_prompt_ref` synced 8/8; confirm all other Tier-2 mechanics). Record cloud-axis steps (`DEFERRED_NON_CLOUD`, cloud terminals) as derived-only divergences.
- [x] **`lazy`→`lazy-bug` registry section** (full restatement, `user/skills/`): full Tier-1 heading-parity + Tier-2 mechanic audit. Highest drift risk — prose duplicated with no pointers to anchor it. Audit every `## Step`/`### sub-step` heading in `lazy/SKILL.md` and record coverage for each. The spot-check found near-identical heading structure (Sentinel Format, Step 0.0/0/0.3/1/2a/2b/3/4/5, Refs, State-Machine Summary) and two-gate `__mark_fixed__` logic — confirm, populate `headings[]`, record any genuine gaps found and close them, record divergences (bug axis skips Gemini/research). Apply `token_substitutions` (feature/bug vocab, `__mark_complete__`→`__mark_fixed__`, etc.).
- [x] **`lazy`→`lazy-cloud` registry section** (inherit-by-reference, thin wrapper, ~44 pointers, `repos/algobooth/.claude/skills/`): full pointer-resolution audit (C2) + Tier-2 mechanic predicates. Record cloud-axis steps (`__write_deferred_non_cloud__`, deferral bookends) as derived-only divergences. Close any genuine gaps.
- [x] **`lazy-status`→`lazy-bug-status` registry section** (full restatement, `user/skills/`): full Tier-1 heading-parity (7/7 heading spot-check confirmed) + Tier-2 mechanic audit. Lower stakes (read-only dashboards) but in scope for completeness. Record bug-axis divergences (bug-facing terminology, `bug-state.py` vs `lazy-state.py`). Apply token substitutions.
- [x] For each pair above: if a genuine gap is found (a canonical mechanic with no coverage in the derived skill, unambiguously a leak not a divergence), fix it in the derived skill's SKILL.md AND populate the registry with `coverage: "restated"` or `coverage: "inherited"` (not a divergence entry). If ambiguous, record as a divergence with a stated reason.
- [x] **Extend `user/scripts/test_lazy_parity.py`**: add a live zero-drift assertion for each of the four new pairs (`audit_pair(repo_root, pair_name=<name>)` asserts zero drift). The suite now covers all five pairs.

**Minimum Verifiable Behavior:** `pytest user/scripts/test_lazy_parity.py -q` green across all five pairs — specifically the four new live zero-drift assertions pass, meaning every `headings[]` entry and every `mechanic_set` predicate resolves cleanly against the derived skill files after any gap fixes.

**Verification** *(pytest — run by the implementer):*
- [x] `pytest user/scripts/test_lazy_parity.py -q` — all tests green (fixtures + all five live pairs).
- [x] `python3 user/scripts/lazy_parity_audit.py --repo-root .` — exits 0 (zero drift across all five pairs).
- [x] `python3 user/scripts/lint-skills.py --check-projected` — exits 0.

**Prerequisites:** Phase 2: Registry Schema + Audit Engine + Tests (engine must exist and be importable before the extended live assertions can run).

**Files likely modified / created:**
- `user/scripts/lazy-parity-manifest.json` — populate the four stub pair entries with full `headings[]`, `mechanic_overrides`, and `divergences`.
- `user/skills/lazy-bug/SKILL.md` — any genuine gaps found during the full audit (fix in-file, record in manifest as restated/inherited).
- `user/skills/lazy-bug-status/SKILL.md` — same.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — any genuine gaps found (the `dev:kill` absence is NOT a gap — record divergence only); do not add `dev:kill` here.
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` — any genuine gaps found in pointer resolution.
- `user/scripts/test_lazy_parity.py` — four new live zero-drift assertions.

**Testing Strategy:** Each pair's live assertion drives `audit_pair()` against the real repo. For the two full-restatement pairs (`lazy-bug`, `lazy-bug-status`), confirm the C1 heading-match loop isn't excessively noisy (each canonical heading should map to either a restated or divergence entry, not trigger false C4s from minor rewords — adjust `headings[]` entries to match the actual current heading text exactly). For the pointer pairs (`lazy-batch-cloud`, `lazy-cloud`), the C2 pointer-resolution check is the primary signal.

**Integration Notes for Next Phase:**
- Phase 4's C6 doc-anchor cross-linking and optional `lint-skills.py --check-parity` flag both read from the completed five-pair manifest. Ensure every `divergence` entry that has a corresponding human-readable "Differences" table entry in the derived skill carries a `doc_anchor` field — Phase 4 validates these.
- The `dev:kill` divergence in `lazy-batch-cloud` is the canonical example of a per-pair mechanic_override — use it as the reference pattern when authoring the other pairs' overrides.

#### Implementation Notes

**2026-06-15 — Phase 3 Batch 1 (WU-1: `lazy-batch`→`lazy-batch-cloud`).**
- **Audited + filled** the `lazy-batch-cloud` manifest stub (one Sonnet impl agent) + appended a live zero-drift assertion. 39 canonical `lazy-batch` headings classified: **35 restated + 3 inherited + 1 divergence** (independently verified — agent prose said "36 restated", actual file 35; immaterial).
- **mechanic_override:** `run-end-dev-kill` = divergence ("Cloud defers Tauri/MCP and never boots the orchestrator-owned runtime, so there is nothing to tear down at run-end") — the canonical gap-vs-divergence example. `dev:kill` was NOT added to the cloud skill. The other 6 `lazy-batch` mechanics all resolve in cloud (C3 clean).
- **1 divergence heading:** `## Step 0.52: Validation-readiness pre-screen` — cloud omits the pre-loop pre-screen (cloud emits DEFERRED_NON_CLOUD at Step 9, not before the loop). **3 inherited:** the Step 4 DEFAULT/OPT-IN/shared-sentinel-write sub-paths — cloud points to `/lazy-batch` Step 4 ("See …lazy-batch/SKILL.md Step 4 for the full algorithm") rather than restating them as headings.
- **No genuine prose leaks** — no cloud SKILL.md edit needed (`token_substitutions: []`; evidence authored directly against derived form).
- **Gate:** `audit_pair --pair lazy-batch-cloud` exit 0; `pytest test_lazy_parity.py` 13/13. **Review verdict:** PASS (ground-truth verified: yes — audit + pytest + independent C1/C5/dedup analysis re-run).

**2026-06-15 — Phase 3 Batch 2 (WU-2: `lazy`→`lazy-bug`).**
- **Audited + filled** the `lazy-bug` manifest stub + live assertion (one Sonnet impl agent). 18 canonical `lazy` headings: **18 restated, 0 divergence** (independently verified — clean 1:1 full restatement). `token_substitutions`: `lazy-state.py`→`bug-state.py`, `__mark_complete__`→`__mark_fixed__`, `COMPLETED.md`→`FIXED.md`.
- **All 4 `lazy` mechanics resolve** in `lazy-bug` (`completion-integrity`, `exactly ONE sub-skill`, `lazy-preflight.md`, `completeness-policy.md`) → `mechanic_overrides: []`. No genuine prose leak; no SKILL.md edit.
- **Gate:** `audit_pair --pair lazy-bug` exit 0; `pytest test_lazy_parity.py` 14/14. **Review verdict:** PASS (ground-truth verified: yes — audit + pytest + independent 18-entry C1/C5/dedup analysis).

**2026-06-15 — Phase 3 Batch 3 (WU-3: `lazy`→`lazy-cloud`).**
- **Audited + filled** the `lazy-cloud` manifest stub + live assertion (one Sonnet impl agent + one corrective-fix subagent). 18 canonical `lazy` headings: **17 restated + 1 divergence**. `mechanic_overrides: []`; `token_substitutions: []`.
- **1 divergence:** `### \`__write_validated_from_results__\`` — "Cloud defers Tauri/MCP and never boots the runtime, so it cannot produce live MCP validation results — only `__write_validated_from_skip__` (and the cloud-only `__write_deferred_non_cloud__`) apply." (Verified `_from_results` absent in lazy-cloud.)
- **Genuine leak fixed (`one-skill-per-invocation`):** lazy-cloud lacked the `exactly ONE sub-skill` phrase the mechanic asserts. **Corrected** `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` to mirror the canonical `/lazy` + sibling `lazy-bug` pattern: added "invokes exactly ONE sub-skill per invocation" to the **frontmatter description** (the mount point where canonical/lazy-bug carry it) and restored the HARD-REQUIREMENT body to "Execute at most one sub-skill (via Skill tool)" (verbatim parity with canonical `/lazy`'s body). NOTE: the first impl attempt instead mangled the body line ("exactly ONE … (at most one …)"), introducing new body-text drift; this was caught at review and reworked. No `mechanic_override` needed (the mechanic now resolves via the description).
- **Gate:** `audit_pair --pair lazy-cloud` exit 0; `pytest test_lazy_parity.py` 15/15; `lint-skills.py --check-projected` exit 0 (SKILL.md edited). **Review verdict:** PASS (after 1 rework cycle; ground-truth verified: yes — audit + pytest + independent 18-entry analysis + the corrective-fix re-verification).

**2026-06-15 — Phase 3 Batch 4 (WU-4: `lazy-status`→`lazy-bug-status`) + phase-end integration.**
- **Audited + filled** the `lazy-bug-status` manifest stub + live assertion (one Sonnet impl agent). 7 canonical `lazy-status` headings: **7 restated, 0 divergence** (clean full restatement). `token_substitutions`: `lazy-state.py`→`bug-state.py`. Both `lazy-status` mechanics resolve (`NO mutations|read-only` via "NO mutations"; `state\.py` via "bug-state.py") → `mechanic_overrides: []`. No prose leak.
- **WHOLE FAMILY NOW IN SYNC (SPEC Validation row 8):** all five pairs populated — `lazy-bug-batch` (39), `lazy-batch-cloud` (39), `lazy-bug` (18), `lazy-cloud` (18), `lazy-bug-status` (7). `python3 user/scripts/lazy_parity_audit.py --repo-root .` → **exit 0 (zero drift across all five pairs)**; `pytest user/scripts/` → **511 passed** (507 + 4 new live assertions); `lint-skills.py --check-projected` → exit 0.
- **Per-pair override (SPEC Validation row 5):** `run-end-dev-kill` suppressed for `lazy-batch-cloud` only (cloud divergence) while still enforced for `lazy-bug-batch` — verified by the two pairs' live assertions both passing.
- **Gate:** `audit_pair --pair lazy-bug-status` exit 0; `pytest test_lazy_parity.py` 16/16; five-pair audit exit 0. **Review verdict:** PASS (ground-truth verified: yes — per-pair + whole-family audit + full suite re-run independently).
- **Integration verification:** the five-pair manifest is internally consistent (every canonical heading mapped; all evidence/mechanics resolve; all divergences carry reasons). **doc_anchor population for the new divergences (lazy-batch-cloud Step 0.52, lazy-cloud `__write_validated_from_results__`) is deferred to Phase 4** — Phase 4 is the dedicated C6 doc-anchor cross-linking + prose-reconciliation phase, and it also resolves the 2 pre-existing soft C6 warnings on `lazy-bug-batch`'s Step 0.52 / Step 4 doc_anchors. (C6 is soft — no exit-code impact; the family gate is green.)
- **CLAUDE.md review:** no `user/scripts/CLAUDE.md` exists → no update (the parity gate is self-documenting via the manifest + `test_lazy_parity.py`; Phase 4 adds authoring notes into the skill files).

---

### Phase 4: Doc Reconciliation + Hardening

**Scope:** Cross-link each derived skill's prose "Differences" table to the manifest (so `doc_anchor` fields resolve and C6 emits no warnings), add an optional `lint-skills.py --check-parity` CLI flag for standalone human runs, add authoring notes to the `/lazy-*` skill-maintenance docs pointing future editors at the parity gate, and add a `lazy-batch-retro` note so its grading rubric can reference recorded divergences. Run the full suite to confirm the gate passes clean family-wide.

**Deliverables:**
- [x] **C6 doc-anchor cross-linking**: for every `divergence` entry in the manifest that has a `doc_anchor` field, verify the anchor text is present in the derived skill's "Differences" section (the C6 soft check). Where the anchor is missing or stale, either update the derived skill's prose to include the referenced divergence description OR update the `doc_anchor` value to match the current prose. Goal: C6 emits zero warnings on a clean run.
- [x] **`lint-skills.py --check-parity` flag** (optional; decided at implementation): add a CLI flag analogous to `--check-projected` and `--check-capabilities` that invokes `lazy_parity_audit` across all five pairs and reports findings. Non-zero findings cause `lint-skills.py` to exit non-zero. If determined to be too noisy or duplicative given `test_lazy_parity.py` already enforces the hard gate, document the decision and skip the flag (the pytest gate is sufficient).
- [x] **Authoring notes in skill-maintenance docs**: add a short note to each derived skill's intro/header or "Differences" section instructing: "Before editing this skill, run `python3 user/scripts/lazy_parity_audit.py --repo-root . --pair <name>` to confirm parity is clean, and run the suite after to confirm your change doesn't introduce drift." Point to `user/scripts/lazy-parity-manifest.json` as the source of truth for intentional divergences.
- [x] **`lazy-batch-retro` note**: add a comment or note in `lazy-batch-retro/SKILL.md` (or its grading rubric section) indicating that the divergence registry at `user/scripts/lazy-parity-manifest.json` records the known intentional differences between `lazy-batch` and its derived twins — retro grading rubrics may reference these entries when assessing whether a deviation from the canonical pattern is expected or anomalous.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0 with zero warnings on C6 (no `doc_anchor` unresolved), confirming the human docs and registry are in agreement across all five pairs.

**Verification** *(pytest / lint — run by the implementer):*
- [x] `pytest user/scripts/` — full suite green (all prior phase tests remain passing; no regressions).
- [x] `python3 user/scripts/lazy_parity_audit.py --repo-root .` — exits 0 with zero C6 warnings.
- [x] `python3 user/scripts/lint-skills.py --check-projected --check-capabilities` — exits 0.
- [x] If `--check-parity` was implemented: `python3 user/scripts/lint-skills.py --check-parity` — exits 0.

**Prerequisites:** Phase 3: Extend the Registry to the Remaining Four Pairs (full five-pair manifest must exist before C6 cross-linking can be validated).

#### Implementation Notes

**2026-06-15 — Phase 4 (WU-1/2/3, single parallel batch) — TERMINAL PHASE.** Three file-disjoint Sonnet impl agents in parallel.
- **WU-1 (C6 doc-anchor cross-linking + authoring notes):** reconciled all `doc_anchor`s so **C6 emits ZERO warnings**. lazy-bug-batch's two anchors now resolve (Step 0.52 → "Step 0.52 validation-readiness pre-screen" via a new Differences-table row; Step 4 → "Research / Gemini steps" matching the existing row). For completeness, ADDED resolving `doc_anchor`s to the two Phase-3-deferred divergences: lazy-batch-cloud Step 0.52 ("Step 0.52 validation-readiness pre-screen") and lazy-cloud `__write_validated_from_results__` ("not applicable in cloud") — each backed by a new line in that skill's Differences/Cloud-Limitations section. Manifest diff is **doc_anchor-only** (no heading/coverage/reason/evidence/mechanic field touched — verified). Added the parity authoring-note blockquote to **all five** derived skills.
- **WU-2 (`--check-parity` flag — IMPLEMENTED, not skipped):** added to `user/scripts/lint-skills.py`, mirroring `--check-projected`/`--check-capabilities`; invokes `lazy_parity_audit.audit_all_pairs(parents[2])`, prints findings + `exit_code=1` on drift, else "OK — … zero drift across all five pairs." Added a hermetic `test_check_parity_clean_repo` to `test_lint_skills.py` (direct `audit_all_pairs` call, no subprocess). **Decision rationale:** implemented (not skip-if-noisy) — it's a low-risk pattern-mirror of an existing flag and gives a standalone human-run convenience alongside the `test_lazy_parity.py` hard gate (completeness-first).
- **WU-3 (`lazy-batch-retro` note):** added a registry-awareness blockquote at the corrected path `repos/algobooth/.claude/skills/lazy-batch-retro/SKILL.md` (line ~286, before the grading rule sets) pointing graders at the manifest as the record of intentional per-pair divergences.
- **Gates:** five-pair audit `--repo-root .` exit 0 with **0 C6 warnings**; `pytest user/scripts/` **512 passed** (511 + 1 new flag test); `lint-skills.py --check-projected --check-capabilities` exit 0; `lint-skills.py --check-parity` exit 0. **Review verdict:** PASS (ground-truth verified: yes — all gates + manifest doc_anchor-only diff + flag block + 5 notes + retro note re-run/inspected independently).
- **CLAUDE.md review:** no `user/scripts/CLAUDE.md` exists → none created; the per-skill authoring notes + the `lazy-batch-retro` note + the manifest now carry the maintenance guidance (decision recorded).
- **Integration verification:** the hard gate (`test_lazy_parity.py`) is active family-wide; C6 is clean (human "Differences" docs and the registry agree across all five pairs — SPEC Validation "C6 doc-table consistency"); a future canonical edit adding a `## Step` heading surfaces as a C1 failure per affected twin (new-unit detector live).

**Files likely modified / created:**
- `user/skills/lazy-bug-batch/SKILL.md` — authoring note + any `doc_anchor` prose additions.
- `user/skills/lazy-bug/SKILL.md` — authoring note + any `doc_anchor` prose additions.
- `user/skills/lazy-bug-status/SKILL.md` — authoring note + any `doc_anchor` prose additions.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — authoring note + any `doc_anchor` prose additions.
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` — authoring note + any `doc_anchor` prose additions.
- `user/skills/lazy-batch-retro/SKILL.md` — divergence-registry reference note.
- `user/scripts/lint-skills.py` — `--check-parity` flag (if implemented).

**Testing Strategy:** C6 is the primary signal for this phase — it's a soft check by design (warns, doesn't fail), but the goal is zero warnings. Verify by running `lazy_parity_audit.py` and inspecting its stderr for C6 output. The full `pytest user/scripts/` run is the regression gate. The `--check-parity` flag (if implemented) is manually verified against `test_lint_skills.py` if a test is warranted.

**Integration Notes for Next Phase:** None — this is the terminal phase. The hard gate (`test_lazy_parity.py` in the pytest suite) is now active family-wide. Future canonical edits that add a `## Step` heading will surface as C1 failures per affected twin until the author populates a manifest entry.

---

## Validation Criteria Coverage

The SPEC's Validation Criteria table rows map to phases as follows — confirming nothing is dropped:

| SPEC Validation Criterion | Satisfied by |
|---|---|
| F2a cycle-dispatch mirrored (`cycle_prompt_ref` in bug-batch §1d) | **Phase 1** (prose edit + grep verification) |
| `dev:kill` teardown mirrored (bug-batch §1c.6) | **Phase 1** (prose edit + grep verification) |
| New canonical step detected per twin (C1 fires on a dummy `## Step X`) | **Phase 2** (C1 fixture test) |
| Leaked Tier-2 mechanic detected (C3 fires on missing `cycle_prompt_ref`) | **Phase 2** (C3 fixture test) |
| Per-pair override works (`dev:kill` absent in `lazy-batch-cloud` suppresses C3) | **Phase 3** (live assertion for cloud pair with `mechanic_override`; the override mechanic is set up in Phase 2's manifest and exercised in Phase 3's live zero-drift run) |
| Broken pointer detected (C2 fires on corrupt inherited evidence) | **Phase 2** (C2 fixture test) |
| Reasonless divergence rejected (C5 fires) | **Phase 2** (C5 fixture test) |
| Whole family in sync (zero drift across all five pairs; suite green) | **Phase 3** (five live zero-drift assertions) |
| Divergences documented (F5, research, `dev:kill`-in-cloud, cloud/bug axis steps carry `reason`) | **Phase 2** (lazy-bug-batch pair fully populated) + **Phase 3** (remaining four pairs) |
| C6 doc-table consistency — no warnings on clean run | **Phase 4** (cross-linking + authoring notes) |

---

## Review Notes

**2026-06-15 — /spec-phases authoring review (inline, orchestrator-held full spec context).**
- **Verdict:** PASS. Phases are faithful to SPEC, well-bounded, strictly chained (P1→P2→P3→P4, no cycles), and verification is distributed per-phase (no terminal-only test phase). claude-config adaptations correct: `MCP runtime: not-required`, Branch omitted (on `main`), no Cross-feature Integration Notes (dep block `(none)`). No gate-owned checkboxes authored.
- **Minor note (no rework):** in the Validation Criteria Coverage table, the "Per-pair override works" row attributes the override *setup* to Phase 2's manifest — precisely, Phase 2 fixture-tests the override mechanism on a synthetic pair, while the real `lazy-batch-cloud` `dev:kill` override is authored in Phase 3 (Phase 2 leaves that pair a stub). The phase bodies state this correctly; the table wording is a slight conflation only.
