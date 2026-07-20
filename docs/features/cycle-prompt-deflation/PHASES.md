# Implementation Phases — Cycle-Prompt Deflation

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness/config plumbing with no MCP-reachable surface (the "user" is the harness operator; observable surfaces are deterministic lint/census output + the KPI registry, per the mcp-testing SPEC's build-tooling/no-app-integration class). Every deliverable is verified by a deterministic in-cycle command (gate exit code + census) and unit tests — nothing defers to a live runtime.

## Cross-feature Integration Notes

Phase-level dependencies on completed upstream features (extracted per /spec-phases Step 1.5). Phase plans below MUST honor these.

- **coupled-pair-generation (kind=hard, Complete):** `generate-coupled-skills.py` derives each coupled/cloud SKILL.md from its canonical + a per-pair overlay (`coupled-overlays/<pair>.overlay.json`) via `apply_tokens`; `--check` is the byte-diff drift gate. The overlays only *reference* `cycle-base-prompt.md` by name in prose — they do NOT byte-embed its section content — so a section-content edit does not directly rewrite an overlay. The load-bearing constraint is therefore: after every deflation phase (2 and 3), run `generate-coupled-skills.py --check` (and `--write` if any embedded prose about the prompt shifted) and confirm exit 0, as defense-in-depth against a marker/boundary edit that the coupled SKILL.md prose depends on.
- **lazy-batch-skill-deflation (kind=composes, Complete):** provides `skill-size-ratchet.py` (the per-file byte + long-line gate) and `skill-size-baseline.json` (the opt-in ceiling store), plus the prose→verdict-rule deflation playbook. Phase 1 EXTENDS this ratchet from whole-file to assembled-profile measurement; Phases 2–3 apply the same playbook to the assembled cycle prompt. Reuse `check`/`lock_in`/`_write` machinery — do not fork.
- **mechanize-prose-only-orchestrator-contracts (kind=soft) / cycle-prompt-environment-dialect (kind=soft):** the `emit_cycle_prompt`/`@section` emitter and the `env-dialect-*` sections are owned upstream. Deflation edits the emitter's OUTPUT (the template prose), never forks the emitter, and preserves the `env-dialect-*` `@section` boundaries + `hosts=windows` selection attributes.

## Validated Assumptions

- **Runtime Assumption Validation Gate — SKIPPED (recorded reason).** Every load-bearing assumption is **code-provable**: assembled byte measurement is a pure in-process call to the real `emit_cycle_prompt` (imported, not re-implemented — `dispatch.py:886`); the ratchet, KPI selector, and coupled-generator gates are deterministic static scans with exit-code verdicts. There is **no user-facing serving path, no cross-boundary runtime behavior, and no MCP surface** — so the reachability axiom does not apply (the feature has no runtime-reachable surface). The one "does the emitter assemble each profile without residue" question is answered by the ratchet *calling the real emitter in-process* (a real call, not a mock) and by unit tests — not a live-service observation.
- **Verified anchor (emitter reuse):** `lazy_core.emit_cycle_prompt(repo_root, state, *, pipeline, cloud, repeat_count, template_dir, park_mode)` returns `{"ok": True, "prompt": str, "model": ...}` or `{"ok": False, "refused": ...}` / `None` for non-dispatchable probes. The assembled bytes = `len(result["prompt"].encode("utf-8"))`. Section selection is driven by `pipeline × mode × skills × variant × park × hosts` attributes (`dispatch.py:965-997`). The ratchet MUST import and drive this — never re-parse `cycle-base-prompt.md` itself.

## Touchpoint Audit (verified inline against the live tree — dispatch skipped per Step-B fallback; contained, directly-verifiable set)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/skill-size-ratchet.py` | yes | `measure`, `check`, `lock_in`, `load_baseline`, `default_baseline_path`, `_write`, `main` (186 ln) | refactor | Add an assembled-profile measurement mode; REUSE `check`/`lock_in`/`_write` shape + `lazy_core._atomic_write`. Import `emit_cycle_prompt` to assemble profiles — never re-parse the template. |
| `user/scripts/skill-size-baseline.json` | yes | `{schema_version:1, files:{5 entries}}` | refactor | Add an assembled-profile ceiling store (new top-level `profiles` key OR per-profile entries); seed at current assembled sizes. Ordinary `files` entries untouched. |
| `user/scripts/lazy_core/dispatch.py` | yes | `emit_cycle_prompt` (`:886`), `_parse_cycle_template`, `_csv_set`, selection loop `:965-997` | reuse (NO edit) | Import for assembled measurement + profile enumeration. Forking the emitter is banned (CLAUDE.md "projection can never drift from the parser it introspects"). |
| `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` | yes | 28 `@section` blocks; `env-dialect-windows … hosts=windows`; 8 `skills=all` boilerplate sections | refactor (deflate) | Trim prose in place. PRESERVE every `@section` selector line + marker literals depended on by 18 co-editing features (provenance-verified). |
| `user/scripts/generate-coupled-skills.py` | yes | `--check`/`--write`/`--extract`/`--report` | reuse (run gate) | Run `--check` after each deflation phase; overlays reference the prompt by name only, but keep the gate green. |
| `user/scripts/kpi-scorecard.py` | yes | `_SOURCES["repo-static-scan"]` frozenset (`:154`), dispatch (`:1089-1091`), `_sel_hook_duplicated_line_count`, `--capture-baseline` writer | refactor | Register the new selector in `_SOURCES["repo-static-scan"]`; add `_sel_cycle_prompt_assembled_bytes(repo_root)`; wire into dispatch. `--capture-baseline` reuses the existing sole computed-field writer. |
| `docs/kpi/registry.json` | yes | 502-ln registry | refactor | Add the SPEC's `cycle-prompt-assembled-bytes` row (Phase 1, `baseline: pending`); Phase 4 stamps `measured`. **Anchor detail:** `signal.selector` string MUST equal the id registered in `_SOURCES["repo-static-scan"]` (the `--lint` check is `selector in _SOURCES[source]`). |
| `user/scripts/lint-skills.py` | yes | `--check-skill-size` (`:399`,`:527`) loads the ratchet via importlib → `load_baseline`+`check` | refactor | Extend the `--check-skill-size` branch so the assembled-profile check runs too (or have the ratchet's `check` cover both when profiles live in the same baseline — preferred, zero lint-skills change beyond confirmation). |
| `.claude/skill-config/gate-battery.json` | yes | 7 gates incl. `lint-skills` | reuse/confirm | The `lint-skills` gate runs every battery; confirm the assembled ratchet is reached from it (add `--check-skill-size` to that gate's cmd if the default `lint-skills.py` invocation does not run the ratchet). |
| `user/scripts/test_skill_size_ratchet.py` | yes | 161 ln incl. a live self-check on the real baseline+tree | refactor | Add assembled-profile measurement/ratchet tests; keep the live self-check green (it now also asserts assembled profiles within ceilings). |

**Contradictions:** none premise-grade. One **anchor-grade** (mechanical, corrected in-plan, not a halt): the SPEC's drafted KPI row carries a long prose `selector` string, whereas `_SOURCES` entries are short ids — Phase 1 reconciles by registering whatever exact string the committed registry row uses, so `--lint` passes. Recorded in Phase 1 Integration Notes.

---

### Phase 1: Assembled-profile measurement harness + baseline seed + KPI/gate wiring

**Scope:** Add an assembled-cycle-prompt measurement mode to `skill-size-ratchet.py` (imports `emit_cycle_prompt`, never re-parses the template), enumerate the real dispatchable profiles, seed their current assembled sizes as ceilings in `skill-size-baseline.json`, register the `cycle-prompt-assembled-bytes` KPI selector + its census computation in `kpi-scorecard.py`, add the registry row (`baseline: pending`), and confirm the assembled ratchet runs from `lint-skills.py --check-skill-size` and the gate-battery. **No prompt edits in this phase** — this locks the "before" numbers and stops further accretion immediately.

**Status:** Complete (implementation; feature validation pending later phases)

**Deliverables:**
- [x] Assembled-profile measurement in `skill-size-ratchet.py`: a function that, given a `(pipeline, mode, skill[, variant, park, host])` profile, drives `lazy_core.emit_cycle_prompt` and returns `len(prompt.encode("utf-8"))` (refusing/`None` results surfaced honestly, never counted as 0).
- [x] Profile enumeration: the concrete set of real dispatchable profiles (e.g. `feature/workstation/execute-plan`, `feature/workstation/spec`, `feature/workstation/mcp-test/runtime-up`, `feature/workstation/mcp-test/no-runtime`, bug-pipeline equivalents) — derived from the `@section` selector matrix, not hand-guessed.
- [x] `skill-size-baseline.json` extended with an assembled-profile ceiling store seeded at current sizes; `--lock-in` semantics for profiles identical to files (only ever lowers; new profiles seeded at current). Existing per-file `files` entries byte-untouched.
- [x] `kpi-scorecard.py`: `cycle-prompt-assembled-bytes` registered in `_SOURCES["repo-static-scan"]`; `_sel_cycle_prompt_assembled_bytes(repo_root)` computes `max(assembled_bytes)` over all profiles (honest NO-DATA on an unreadable target, never a fabricated 0); wired into the dispatch at the `repo-static-scan` branch.
- [x] `docs/kpi/registry.json`: the SPEC's KPI row added with `baseline.provenance: pending` and `signal.selector` matching the registered id.
- [x] Confirm/extend `lint-skills.py --check-skill-size` so the assembled-profile check runs; confirm the gate-battery reaches it.
- [x] Tests: assembled measurement returns a positive byte count for a known profile; `check` flags an over-ceiling profile; `--lock-in` only lowers; `kpi-scorecard.py --lint` passes with the new row; the live self-check stays green.

**Minimum Verifiable Behavior:** `python3 user/scripts/skill-size-ratchet.py --check` exits 0 naming N assembled profiles within their seed ceilings, AND `python3 user/scripts/kpi-scorecard.py --lint` exits 0 with the new row registered. Both are runnable in-cycle (deterministic; no runtime).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (deterministic static-scan tooling; verified by unit tests + gate exit codes).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/skill-size-ratchet.py` — add assembled-profile mode (reuse `check`/`lock_in`/`_write`).
- `user/scripts/skill-size-baseline.json` — seed assembled-profile ceilings.
- `user/scripts/kpi-scorecard.py` — register selector + census computation (`_SOURCES` `:154`, dispatch `:1089`).
- `docs/kpi/registry.json` — add the KPI row.
- `user/scripts/lint-skills.py` — confirm/extend `--check-skill-size` reaches the assembled check.
- `.claude/skill-config/gate-battery.json` — confirm the assembled ratchet is reached (edit the `lint-skills` cmd only if needed).
- `user/scripts/test_skill_size_ratchet.py` — assembled-profile tests.

**Testing Strategy:** Hermetic unit tests over a fixture template dir (drive `emit_cycle_prompt` with `template_dir=` override, as the emitter's own tests do) so profile measurement is deterministic without the real prompt. Plus the live self-check on the real baseline+tree.

**Integration Notes for Next Phase:**
- The seed ceilings captured here are the "before" numbers Phase 2 lowers via `--lock-in`. Do NOT hand-raise them.
- **Anchor (KPI selector):** the registry row's `signal.selector` and the `_SOURCES["repo-static-scan"]` id MUST be byte-identical — `kpi-scorecard.py --lint` checks `selector in _SOURCES[source]`. Pick one id and use it in both.
- The profile enumeration is the contract Phases 2–3 measure against — it must cover every real dispatch class (both pipelines, workstation mode; cloud where it dispatches; the two mcp-test variants; `hosts=windows` matters on this box).

---

### Phase 2: Trim-in-place the top-3 boilerplate sections

**Scope:** Deflate the three highest-return `skills=all` boilerplate sections — `turn-end` (~4.9 KB), `workstation-dispatch` (~4.8 KB), `hard-contract` (~3 KB) — to terse verdict-routing rules, preserving every policy as an equivalent rule (prose-density reduction, NOT policy removal). Regenerate coupled-pair mirrors and confirm the drift gate green. Lower the affected profile ceilings.

**Deliverables:**
- [ ] `turn-end`, `workstation-dispatch`, `hard-contract` sections in `cycle-base-prompt.md` rewritten to terse rules, each `@section` selector line + every depended-on marker literal preserved verbatim.
- [ ] Semantic-equivalence review artifact: a per-section old-rule → surviving-terse-rule mapping (`SEMANTIC_DIFF_PHASE2.md` in the feature dir) proving no policy was dropped.
- [ ] `generate-coupled-skills.py --check` exits 0 (coupled SKILL.md mirrors regenerate cleanly; run `--write` first if any prompt-describing prose shifted).
- [ ] `emit_cycle_prompt` still assembles every profile (residue guard passes — no unbound `{token}`).
- [ ] Affected profile ceilings lowered via `skill-size-ratchet.py --lock-in`.
- [ ] Tests: emitter residue-guard/assembly tests green for all profiles; assembled bytes measurably smaller for profiles carrying these three sections.

**Minimum Verifiable Behavior:** `python3 user/scripts/generate-coupled-skills.py --check` exits 0 AND `python3 user/scripts/skill-size-ratchet.py --check` exits 0 at the new lower ceilings AND the emitter assembles every profile without a residue error (assertable via the existing `emit_cycle_prompt` tests). All runnable in-cycle.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior.

**Prerequisites:**
- Phase 1: the assembled-profile measurement + seed ceilings must exist to measure the reduction and re-lock the floor.

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — deflate the three sections.
- `user/scripts/coupled-overlays/*.overlay.json` and the coupled SKILL.md files — only if `--write` regenerates a shift; otherwise untouched.
- `user/scripts/skill-size-baseline.json` — via `--lock-in` (lowered ceilings).
- `docs/features/cycle-prompt-deflation/SEMANTIC_DIFF_PHASE2.md` — the equivalence review artifact (net-new).

**Testing Strategy:** Run the `lazy_core` dispatch tests (`tests/test_lazy_core/test_dispatch.py`) to prove assembly + residue-guard integrity across profiles; diff assembled bytes before/after; human-readable semantic-equivalence review as the no-policy-lost guard.

**Integration Notes for Next Phase:**
- The marker-literal preservation list is load-bearing: 18 features govern `cycle-base-prompt.md` (e.g. `cycle-prompt-environment-dialect` owns `env-dialect-*`, `lazy-cycle-containment` owns the terminal-stop C4 literal, `stub-origin-provisional-exclusion`, `code-doc-provenance-linkage`). Grep each governing feature's expected literal after editing.
- If `generate-coupled-skills.py --check` reports drift, run `--write` then re-`--check` — never leave the drift gate red.

---

### Phase 3: Trim remaining boilerplate + evidence-backed scope-tightening

**Scope:** Deflate the remaining `skills=all` boilerplate — `d7`, `env-dialect-core`, `env-dialect-windows` (hosts=windows), `status-honesty`, `terminal-stop`, `task` — to terse rules; then narrow any `skills=all` selector *proven safe* to exclude a cycle class (candidate: `workstation-dispatch` for cycles that never fan out). Each narrowing carries an explicit safety justification; the conservative default is trim-only (no selector change) for any section whose exclusion safety is uncertain. Lock in the new floor.

**Deliverables:**
- [ ] `d7`, `env-dialect-core`, `env-dialect-windows`, `status-honesty`, `terminal-stop`, `task` deflated to terse rules; `@section` boundaries + marker literals preserved (esp. the `env-dialect-*` `hosts=` attributes and terminal-stop C4).
- [ ] Any `skills=` selector narrowing carries a per-section written safety justification (the excluded cycle class genuinely does not consume the section's rules) in `SEMANTIC_DIFF_PHASE3.md`; uncertain sections stay `skills=all` (trim-only).
- [ ] `generate-coupled-skills.py --check` exits 0; `emit_cycle_prompt` assembles every profile without residue error; every profile's assembled bytes ≤ its ceiling and moving toward the ~9–10 KB working target.
- [ ] New floor locked via `skill-size-ratchet.py --lock-in`.
- [ ] Tests: assembly/residue green for all profiles; a narrowed section is asserted absent from the excluded cycle's assembled prompt AND present in the cycles that DO consume it (the scope-tightening regression guard).

**Minimum Verifiable Behavior:** `python3 user/scripts/skill-size-ratchet.py --check` exits 0 at the Phase-3 floor AND `python3 user/scripts/generate-coupled-skills.py --check` exits 0 AND a test asserts each narrowed selector's section is present/absent in exactly the right cycle classes. All runnable in-cycle.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior.

**Prerequisites:**
- Phase 2: the top-3 sections deflated and the coupled/emitter gates green (Phase 3 continues on the same template).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — deflate remaining sections; narrow proven-safe selectors.
- `user/scripts/skill-size-baseline.json` — via `--lock-in`.
- `docs/features/cycle-prompt-deflation/SEMANTIC_DIFF_PHASE3.md` — equivalence + scope-tightening safety review (net-new).
- `user/scripts/test_skill_size_ratchet.py` / `tests/test_lazy_core/test_dispatch.py` — scope-tightening presence/absence assertions.

**Testing Strategy:** Same as Phase 2 plus a per-narrowing presence/absence assertion (a scope error silently under-briefs a cycle — worse than a few extra KB, so this test is the load-bearing guard for the scope-tighten lever).

**Integration Notes for Next Phase:**
- After Phase 3 the assembled census is final — Phase 4 captures the KPI baseline from it.
- Record the achieved floor (the ratchet locks whatever Phase 3 achieves; no up-front number was committed).

---

### Phase 4: KPI measured baseline + gate-wiring confirmation

**Scope:** Capture the friction KPI measured baseline from the final post-Phase-3 assembled census, and confirm the assembled ratchet is wired into the lint battery and the gate-battery so re-bloat is blocked going forward.

**Deliverables:**
- [ ] `python3 user/scripts/kpi-scorecard.py --capture-baseline cycle-prompt-assembled-bytes` run — stamps `provenance: measured` + the measured value + `captured_at` from the current census into `docs/kpi/registry.json` (the sole computed-field writer; refuses on no-data, never fabricates).
- [ ] Confirm `lint-skills.py --check-skill-size` and the `gate-battery.json` battery both exercise the assembled-profile ratchet (add the flag to the battery's `lint-skills` cmd if it is not already reached).
- [ ] `kpi-scorecard.py --lint` exits 0 with the now-measured row; `kpi-scorecard.py` renders `SCORECARD.md` with the new KPI (byte-stable).
- [ ] Tests: `--capture-baseline` writes a measured provenance from a fixture census; the full lint battery / gate-battery is green end-to-end.

**Minimum Verifiable Behavior:** `python3 user/scripts/kpi-scorecard.py --lint` exits 0 with `cycle-prompt-assembled-bytes` at `provenance: measured`, AND `python3 user/scripts/gate-battery.py` (or the invariant battery) returns `RESULT=PASS`. Runnable in-cycle.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior.

**Prerequisites:**
- Phase 3: the final assembled census must be locked (the measured baseline is computed from it).
- Phase 1: the selector + computation registration (`--capture-baseline` needs the computation wired).

**Files likely modified:**
- `docs/kpi/registry.json` — `--capture-baseline` stamps the measured baseline (script-owned write).
- `.claude/skill-config/gate-battery.json` — confirm/wire the assembled ratchet reach (only if needed).
- `docs/kpi/SCORECARD.md` — regenerated render (byte-stable).
- `user/scripts/test_kpi_scorecard.py` — `--capture-baseline` measured-provenance test.

**Testing Strategy:** Hermetic `--capture-baseline` test over a fixture census + registry; run the full invariant battery to confirm end-to-end green.

**Completion (gate-owned):** the `__mark_complete__` gate flips SPEC.md **Status:** to Complete and writes COMPLETED.md once the validation tail passes — never authored as a checkbox row here.

---

## Decomposition notes

- **Verification distribution:** each phase carries its own deterministic in-cycle verification (gate exit code + census + unit tests) — there is no terminal-only MCP phase (this is a `MCP runtime: not-required` feature; the terminal-MCP-stacking / reachability-smoke rules are N/A by construction, no new user-facing API surface).
- **Phase ordering rationale:** Phase 1 measures + seeds + wires (stops accretion immediately, before any risky edit); Phases 2–3 are the actual deflation (top-3 first for highest absolute return, then the tail + scope-tightening); Phase 4 captures the measured KPI from the settled census. Linear dependency chain, no circularity.
- **The one non-mechanical lever (scope-tightening, Phase 3)** is applied conservatively with a per-section safety proof + a presence/absence regression test — a scope error under-briefs a cycle, which is worse than carrying a few extra KB.
