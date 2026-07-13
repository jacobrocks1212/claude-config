# Implementation Phases — Cycle-Prompt Environment Dialect

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress

**MCP runtime:** not-required — pure claude-config harness mechanics (a prompt-template
component, a Python emitter, state-script subcommands). No Tauri app, no MCP-reachable
surface. Validation is `pytest` (`test_lazy_core.py`, `test_lazy-state.py` /
`test_bug-state.py`) plus the standing skill gates
(`generate-coupled-skills.py --check`, `lazy_parity_audit.py`, `lint-skills.py`,
`project-skills.py`). This is the `standalone — no app integration` untestable class →
`SKIP_MCP_TEST.md` at the MCP gate, once all phases below are closed.

## Cross-feature Integration Notes

`**Depends on:** phases-slice-scoped-reads (Complete, hard) — the mandated PHASES.md reader
this feature forces onto the cycle prompt's remaining direct-Read instruction.` No other hard
deps. Same-batch soft relation: `lazy-batch-skill-deflation` (Draft) shares the <2KB
prompt-budget discipline this feature's D4 introduces for the dialect block specifically.

**LANE SPLIT (operator-directed, this session):** this feature's four phases split across two
active lanes that may NOT both write the same files concurrently (`user/CLAUDE.md`
"One writer per file"):
- **SKILLS lane (this session)** owns `user/skills/**` +
  `repos/algobooth/.claude/skills/**` — i.e. `cycle-base-prompt.md` itself. Phase 2's
  template-side deliverables and Phase 3's PHASES-read-mandate sweep are IN this lane and
  DONE (see per-phase deliverables below).
- **STATE lane (busy elsewhere this session — NOT touched here)** owns
  `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/lazy_core.py`,
  `user/scripts/kpi-scorecard.py`, and their test files. Phase 1 (`--marker-status`), Phase
  2's emitter `hosts=` selection-filter + unit tests, and Phase 4 (KPI selector
  registration) all land in files owned by that lane. **NOT started here** — the exact
  wanted diffs are recorded in each phase's Implementation Notes below and in this session's
  final report, for the STATE-lane agent (or a follow-up session) to apply.
- **Cross-repo (AlgoBooth, unreachable from this workspace):** Phase 3's cluster-(g)
  `MCP_USAGE_GUIDE.md` one-liner lives in the AlgoBooth repo, which is developed via cloud
  sessions only (`~/source/repos/CLAUDE.md`: "the live repo was deleted from this machine").
  **NOT started here** — recorded as an outstanding cross-repo follow-up.

---

### Phase 1: `--marker-status` (STATE lane — APPLIED, state-batch-5)

**Phase kind:** design

**Scope:** A read-only, never-throws probe subcommand in `lazy-state.py` (+ parity in
`bug-state.py`) that replaces the fragile taught `cat <marker> | python -c
"json.load(sys.stdin)"` idiom (cluster e, 94 mined tracebacks) with a single command.

**Deliverables:**
- [x] `lazy-state.py --marker-status --repo-root <root>` — prints `{"present": bool}`,
  **always** exits 0: absent marker, corrupt JSON, and no-state-dir all resolve to
  `{"present": false}` rather than raising (wraps `lazy_core.read_run_marker`, which already
  never raises, plus a belt-and-braces `except Exception` for future-proofing).
- [x] `bug-state.py --marker-status --repo-root <root>` — parity mirror (same contract,
  bug-pipeline state dir; the marker is shared between pipelines).
- [x] Fixture tests: `test_marker_status_cli_never_throws_lazy_state` /
  `test_marker_status_cli_never_throws_bug_state` in `test_lazy_core.py` (subprocess-driven,
  absent/present/corrupt-JSON all exit 0 with the right `present` value; the absent probe is
  also asserted read-only — no state dir created). `lazy_parity_audit.py --repo-root .` exit 0.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --marker-status
--repo-root <a dir with no .claude/state>` exits 0 and prints `{"present": false}` (not a
traceback). Verified via the fixture above, including the corrupt-JSON case (not just absent).

**Runtime Verification** *(checked by integration test)*:
- [x] Never-throws contract holds under all three fixtures (absent/present/corrupt), both
  scripts. *(Evidence: `python -m pytest user/scripts/test_lazy_core.py -k marker_status` — 2
  passed.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (first phase; independent of Phase 2's grammar work).

**Files modified:** `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`,
`user/scripts/test_lazy_core.py` (fixture tests added there, not a separate `test_lazy-state.py`
module — matching this repo's actual test-file convention).

**Testing Strategy:** Hermetic pytest fixtures constructing a temp `.claude/state/<repo_key>/`
in each of the four shapes.

**Integration Notes for Next Phase:** Phase 2's `env-dialect-core` section (already authored
this session) already NAMES `--marker-status --repo-root {cwd}` as the mandated probe — the
prose is written assuming this subcommand exists. Ship Phase 1 before (or same session as)
Phase 2 reaches a Windows cycle subagent in the field, or the prompt will teach a command that
404s.

---

### Phase 2: `hosts=` grammar + dialect sections

**Phase kind:** implementation (SPLIT — template-side DONE this session; emitter-side pending)

**Scope:** The new `@section env-dialect-core` / `@section env-dialect-windows` blocks in
`cycle-base-prompt.md`, an optional `hosts=` section attribute (grammar-additive, `park=`
precedent), and the emitter-side filter that makes `hosts=windows` actually host-conditional.

**Deliverables:**
- [x] `env-dialect-core` section (`pipelines=feature,bug modes=workstation,cloud skills=all`,
  1,110 bytes) — stdin-pipe cross-process rule, `--marker-status` probe mandate,
  `phases-slice.py` PHASES-read mandate. Authored in
  `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`.
- [x] `env-dialect-windows` section (`pipelines=feature,bug modes=workstation skills=all
  hosts=windows`, 820 bytes) — trailing-backslash-before-closing-quote rule, no `/mnt/c` on
  Git Bash, `$HOME`-anchored `sys.path` for `lazy_core`/state-script imports.
- [x] Both sections measured and asserted <2,048 bytes each (D4 budget) via a one-off
  extraction script mirroring `_parse_cycle_template` — 1,110 / 820 bytes, well under budget.
- [x] Template-header **RULE INVENTORY** updated (R18 environment dialect, R19 PHASES-read
  mandate) and the **SECTION MARKER GRAMMAR** doc comment extended with a `hosts=` paragraph
  that explicitly flags the attribute as **declared but not yet selection-filtered**
  (grammar parses it today via the existing generic `key=value` capture in
  `_parse_section_attrs`; it is simply not read by the selection loop yet — v1 acceptable
  static behavior per this feature's operator-directed scope: the section is selected on
  every host its `pipelines`/`modes`/`skills` match, same as before this attribute existed).
- [x] Re-projected (`project-skills.py`) and linted (`lint-skills.py
  --check-projected --check-capabilities`) — both exit 0.
- [x] `generate-coupled-skills.py --check` and `lazy_parity_audit.py --repo-root .` confirmed
  exit 0 unchanged (verified in `RESEARCH_SUMMARY.md`: `cycle-base-prompt.md` is referenced
  by pointer only from every coupled-pair SKILL.md, never inlined into a `derived` file, so
  it sits outside the coupled-pair generator's canonical/derived pairs by construction).
- [x] Ran the REAL-template `emit_cycle_prompt` test suite (`pytest test_lazy_core.py -k
  emit_cycle_prompt`) against the edited file as a read-only sanity check — 28/28 pass,
  confirming no residue/anchor regressions from the new sections.
- [x] **Emitter `hosts=` selection filter (STATE lane — APPLIED, state-batch-5):** wired
  `attrs.get("hosts")` into BOTH selection loops in `lazy_core.emit_cycle_prompt` (the base
  template loop and the repo-addenda loop), mirroring the existing `park=` filter shape exactly
  as recorded:
  ```python
  # hosts= filter (cycle-prompt-environment-dialect, SPEC D2): hosts=windows sections
  # are selected ONLY when the emitting host is Windows. Absent -> always selected
  # (grammar-additive, same shape as park=).
  host_attr = attrs.get("hosts")
  if host_attr == "windows" and os.name != "nt":
      continue
  ```
  Added identically at both selection sites (base + addenda), byte-identical to the recorded
  snippet.
- [x] **Size + selection unit tests (STATE lane — APPLIED, state-batch-5):** all three named
  tests landed in `test_lazy_core.py`, PLUS a fourth (`test_emit_cycle_prompt_hosts_windows_
  addenda_excluded_on_non_windows`) proving the filter applies to the repo-addenda loop too, not
  just the base template:
  - `test_emit_cycle_prompt_hosts_windows_selected_on_win32`
  - `test_emit_cycle_prompt_hosts_windows_excluded_on_non_windows`
  - `test_env_dialect_section_byte_budget`
  **Delta from the literal recorded technique (documented, not silent):** the tests do NOT
  monkeypatch the real `os.name` global — doing so flips which `pathlib` class the bare `Path()`
  factory returns platform-wide, and `emit_cycle_prompt` calls `Path(spec_path) / "PHASES.md"`
  internally on EVERY invocation (`_read_mcp_runtime_decision`), which raised
  `NotImplementedError: cannot instantiate 'PosixPath' on your system` when tested live on this
  Windows machine. Instead, a small `_FakeOsName` proxy (overrides only `.name`, forwards
  everything else to the real `os` module) is bound to `lazy_core.os` for the duration of the
  call and restored after — this changes ONLY what `emit_cycle_prompt`'s `os.name` reads resolve
  to, leaving the real `os` module (and therefore `pathlib`) completely untouched.

**Minimum Verifiable Behavior:** emitting a cycle prompt with a forced non-Windows `os.name`
excludes the `env-dialect-windows` section's content from the assembled prompt while
`env-dialect-core`'s content remains present. Verified.

**Runtime Verification** *(checked by integration test)*:
- [x] Budget held (1,110 / 820 bytes < 2,048 each). *(Evidence: this session's one-off byte
  count over `_parse_cycle_template` output — see `RESEARCH_SUMMARY.md`.)* <!-- verification-only -->
- [x] Windows block reaches Windows cycles / absent on non-Windows / grammar backward-compat
  (sections without `hosts=` select byte-identically to pre-feature — proven by the full
  `emit_cycle_prompt` suite staying green, 31/31 passed). *(Evidence: `python -m pytest
  user/scripts/test_lazy_core.py -k "hosts_windows or env_dialect_section_byte_budget or
  emit_cycle_prompt"` — 35 passed.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None (independent of Phase 1; the template-side half has no dependency on
the emitter-side half landing first — the section is simply always-selected until the filter
ships, a strict superset of the target behavior, never a narrower one).

**Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

**Testing Strategy:** Hermetic pytest against a synthetic template fixture (existing pattern
in `test_lazy_core.py`) plus the real-template regression already run this session.

**Integration Notes for Next Phase:** Phase 4's KPI selector should be able to cite
per-cluster `env-dialect-windows` selection correctness once Phase 2's emitter filter and
tests land — no further template changes anticipated.

---

### Phase 3: cross-repo row + PHASES-read mandate sweep (SPLIT — sweep DONE, cross-repo row NOT reachable)

**Phase kind:** implementation

**Scope:** Cluster (g)'s one-line AlgoBooth doc fix, and auditing `cycle-base-prompt.md`'s
remaining direct-PHASES-walk instructions.

**Deliverables:**
- [x] Audited `cycle-base-prompt.md` for direct-PHASES-walk instructions: the RECONCILE
  PHASES step inside `skill-mcp-test-common` (previously "walk {spec_path}'s PHASES.md") now
  reads "`read {spec_path}'s PHASES.md via the env-dialect-core mandate above
  (phases-slice.py {spec_path} --phase <id>), never a whole-file Read`" — routes through the
  same mandate rather than restating it (RULE INVENTORY R19 documents this as the one
  sanctioned reference, not a restatement).
- [x] No other direct-PHASES-walk instruction found in the template (grep for `PHASES.md`
  confirms the remaining hits are the mcp-test variant's `**MCP runtime:**` line lookup —
  read via `_read_mcp_runtime_decision`, already a targeted single-line read, not a
  whole-file walk — and the template's own header-comment documentation references).
- [ ] **AlgoBooth `MCP_USAGE_GUIDE.md` one-liner (cross-repo, NOT reachable this session):**
  add a line clarifying `curl :3333/info`'s `tools` entries are STRINGS, not objects (the
  cluster-(g) `TypeError`, 39 mined incidents). The file lives in the AlgoBooth repo itself,
  which per `~/source/repos/CLAUDE.md` has no live local checkout ("developed via cloud
  sessions only... the live repo was deleted from this machine"). **Wanted change** (for a
  future AlgoBooth cloud session): in `MCP_USAGE_GUIDE.md`'s `/info` endpoint description,
  add a line such as: "`tools` entries in the `/info` response are plain strings (tool
  names), not objects — do not assume `.name`/`.description` attributes; iterate them
  directly." No local file exists to point at from this workspace (claude-config's own
  `repos/algobooth/.claude/skill-config/*.md` files only POINT AT the guide by name, per
  `RESEARCH_SUMMARY.md`; they do not embed its content, so there is nothing to edit here as a
  substitute).

**Minimum Verifiable Behavior:** `grep -c "phases-slice" cycle-base-prompt.md` is 1
(post-edit) where it was 0 pre-edit (matches the SPEC's cluster-(f) citation).

**Runtime Verification** *(checked by integration test or manual testing)*:
- [x] RECONCILE step routes through the mandate. *(Evidence: manual diff review this
  session — see the exact before/after text in `plans/` below.)* <!-- verification-only -->
- [ ] Cross-repo row landed. *(Evidence: pending an AlgoBooth cloud session.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 2's `env-dialect-core` section (the RECONCILE step's edit references
it by name).

**Files likely modified (remaining):** AlgoBooth repo's `MCP_USAGE_GUIDE.md` — **outside this
workspace; not touched this session.**

**Testing Strategy:** Grep-based anchor check (done); the cross-repo row has no test surface
reachable from claude-config.

**Integration Notes for Next Phase:** Phase 4's retro-grading note should treat cluster (g) as
a separately-tracked cross-repo follow-up, not a claude-config completion blocker.

---

### Phase 4: measurement hookup (STATE lane — NOT started this session)

**Phase kind:** design

**Scope:** Register the `session-log-mining` selector (e.g. `cycle-env-dialect-error-count`)
in `kpi-scorecard.py`'s `_SOURCES`, wire `--capture-baseline`, and add the retro grading note
for per-cluster kill-rate.

**Deliverables:**
- [ ] `kpi-scorecard.py` `_SOURCES` gains a `session-log-mining` source +
  `cycle-env-dialect-error-count` selector (or the operator's chosen final name), per the
  registration precedent the context-diet features used.
- [ ] `docs/kpi/registry.json`'s `cycle-env-dialect-error-rate` row (already drafted in
  `SPEC.md`'s `## KPI Declaration`) gets its `signal.selector` updated from the interim
  `process-friction-count` deny-ledger channel to the dedicated selector once registered.
- [ ] Retro-grading note (for `/lazy-batch-retro` or a manual review) documenting per-cluster
  kill-rate as the D1 hook-escalation evidence input.

**Minimum Verifiable Behavior:** `python3 user/scripts/kpi-scorecard.py --lint` still exits 0
with the updated selector; a `--capture-baseline cycle-env-dialect-error-rate` run (once real
signal history exists) stamps `provenance: measured`.

**Runtime Verification** *(checked by integration test or manual testing)*:
- [ ] Selector registered and lint-green. *(Evidence: pending — STATE lane not yet engaged.)*
  <!-- verification-only -->

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 2 and Phase 3 landed (the selector measures the field effect of both).

**Files likely modified:** `user/scripts/kpi-scorecard.py`, `docs/kpi/registry.json` —
**STATE-lane-owned; NOT touched this session** (`kpi-scorecard.py` is explicitly out of this
session's file ownership per the dispatch brief, though it is fine to RUN `--lint`).

**Testing Strategy:** `test_kpi_scorecard.py` fixture for the new selector; `--lint --spec
docs/features/cycle-prompt-environment-dialect/SPEC.md` should already pass today (the SPEC's
KPI Declaration is present and schema-valid) — worth a read-only spot-check.

**Integration Notes for Next Phase:** None — this is the last phase. Once it lands, the
D1 hook-escalation open question in `NEEDS_INPUT_PROVISIONAL.md` can be ratified/redirected
with real field evidence instead of the current provisional recommendation.
