# Implementation Notes — Cycle-Prompt Deflation

## Phase 1 — Assembled-profile measurement harness + baseline seed + KPI/gate wiring (2026-07-19)

**Work completed (Part 1, WU-1/2/3):**
- **WU-1** — `user/scripts/skill-size-ratchet.py`: added the assembled-cycle-prompt
  profile mode — `enumerate_profiles()`, `measure_assembled_profile()`,
  `check_profiles()`, `lock_in_profile()`, plus `--lock-in-profile` in `main()` and
  a profile check folded into the default `--check`. `skill-size-baseline.json` gained
  a top-level `profiles` block (20 seeded profiles). Tests in
  `test_skill_size_ratchet.py` (now 21 pass).
- **WU-2** — `user/scripts/kpi-scorecard.py`: registered `cycle-prompt-assembled-bytes`
  in `_SOURCES["repo-static-scan"]`, added `_sel_cycle_prompt_assembled_bytes()`
  (REUSES the ratchet's measurement via a cached importlib load — never duplicated),
  wired into the `repo-static-scan` dispatch branch. `docs/kpi/registry.json` gained the
  row (`baseline.provenance: pending`). Tests in `test_kpi_scorecard.py` (now 140 pass;
  the seeded-registry row-count assertion bumped 23→24).
- **WU-3** — `user/scripts/lint-skills.py` `--check-skill-size` branch now ALSO runs
  `check_profiles()`; `.claude/skill-config/gate-battery.json` `lint-skills` gate cmd
  gained `--check-skill-size` so the assembled ratchet runs every battery pass.

**Key integration decisions / pitfalls:**
- **Emitter reuse, never a re-parse/fork.** Measurement drives the real
  `lazy_core.emit_cycle_prompt` through the facade (`_default_cycle_template_dir` /
  `_parse_cycle_template` / `_csv_set` are all exposed on the lazy_core facade).
- **Path-independence is load-bearing.** The emitter binds `{cwd}` (=`str(repo_root)`)
  and `{work_branch}` (19 combined template occurrences), so measuring with the real
  repo root makes byte counts vary with the checkout path — a longer path on another
  machine would false-trip the ratchet. The measurement binds a canonical
  `_MEASURE_REPO_ROOT = "__cycle-prompt-measure__"` so the count reflects template prose
  ONLY (deterministic + machine-portable). Still host-sensitive via `os.name`
  (`hosts=windows` sections), but a non-Windows host only measures FEWER bytes → never a
  false trip. Seeded on Windows (this box); max seed 25694 B (feature/workstation/mcp-test/runtime-up).
- **park/host profile dims OUT of v1 enumeration** — the SPEC KPI selector is over
  `(pipeline,mode,skill,variant)`; host resolved by live `os.name`. `_notes` metadata key
  in the `profiles` block is skipped by `check_profiles`/count (`_`-prefix guard).
- **Selector-id ANCHOR reconciled.** The SPEC drafted a long prose `signal.selector`;
  the `--lint` check is `selector in _SOURCES[source]`, so the registry row's
  `signal.selector` and the `_SOURCES` id are BOTH the short `cycle-prompt-assembled-bytes`
  (the prose moved to the row `notes`).

**⚖ policy (scope-class, disclosed):**
- `park/host profile dims → excluded from v1 enumeration` (SPEC KPI selector lists only
  pipeline,mode,skill,variant; host via live os.name).
- `registry selector prose vs short id → short id "cycle-prompt-assembled-bytes" in both sites`
  (Phase-1 ANCHOR; SPEC prose preserved in the row notes).
- `pre-existing ratchet file-ceiling debt blocked WU-3 battery wiring → hand-raised the 3
  over-ceiling file entries (lazy-batch, lazy-batch-cloud, lazy-bug-batch SKILL.md) to
  current` — the ratchet's own sanctioned legitimate-growth path (deliberate documented
  growth from spike-pipeline-role Phase 3 + harden rounds 68/70 had landed without a
  baseline realignment). WU-3 wiring `--check-skill-size` into the battery is the systemic
  fix that stops such debt accumulating silently again. Not accretion — a corrective
  realignment; none of these files are on the control-surface manifest.

**Pre-existing failures observed (NOT caused by this cycle — for orchestrator/harden):**
- `python3 -m pytest user/scripts/` is red on 4 pre-existing coupled-skills DRIFT
  failures (`test_generate_coupled_skills.py`: lazy-bug-batch / lazy-batch-cloud /
  lazy-cloud + `test_check_clean_on_committed_tree`) — the committed coupled SKILL.md
  files (which this cycle never touched) diverge from the PROVISIONAL overlay generator,
  from spike-pipeline-role's hand-mirroring. Plus 1 flaky
  `test_pipeline_visualizer.py::TestFleetServer::test_post_to_fleet_routes_404`
  (ConnectionAbortedError socket race — passes on retry). All other battery gates
  (lazy-state/bug-state `--test`, parity-audit, cli-surface `--check`, doc-drift,
  lint-skills `--check-skill-size`) are green.

**For next phases (2–4):** the 20 seed ceilings are the pre-deflation "before" numbers —
Phase 2/3 lower them via `--lock-in-profile` as prose is trimmed (never hand-raise).
Phase 4 stamps the KPI measured baseline via `kpi-scorecard.py --capture-baseline
cycle-prompt-assembled-bytes`.

## Phase 2 — Trim-in-place the top-3 boilerplate sections (2026-07-19)

**Work completed (Part 2, WU-1):** deflated the three highest-return `skills=all`
boilerplate section families in `cycle-base-prompt.md` to terse rules —
`workstation-dispatch` (ws), `hard-contract` (ws + cloud), `turn-end` (ws + cloud).
Both mode variants of `turn-end`/`hard-contract` were deflated (not just the
workstation copy) so cloud profiles shrink too — the more-complete path.

**Measured reduction (all 20 profiles under ceiling, then re-locked to the new floor
via `--lock-in-profile`):** 72,576 B saved (17.8%) across the 20 profiles — 4,454 B
per workstation profile, 2,391 B per cloud profile. Largest post-deflation profile:
feature/workstation/mcp-test/runtime-up 25,694 → 21,240 B.

**No policy lost:** `SEMANTIC_DIFF_PHASE2.md` maps every original rule → its surviving
terse rule per section. Preserved literals (test-asserted): every `@section` selector,
`WORKSTATION DISPATCH — LOAD-BEARING` (present) / `INLINE OVERRIDE — LOAD-BEARING`
(absent) / `CLOUD OVERRIDE — LOAD-BEARING`; tokens `{receipt_name}`/`{work_branch}`/
`{item_label}`; the R5 chained-command form, `git_safe_push`, `git add -A` ban,
`classify_conflict` + `conflict_kind: semantic` + `--park-provisional`,
`--verify-ledger` + `ok:true` four-condition certification,
`cycle-subagent-bg-gate-guard.sh`.

**Gates green:** `test_dispatch.py` binding-matrix + residue guards + `test_project_skills.py`
terminal-stop/variant tests (228 passed); `skill-size-ratchet.py --check` exit 0 at the
new floor; `generate-coupled-skills.py --check` exit 0 (editing the emitter's OUTPUT
template never shifts the committed coupled SKILL.md — the prompt is assembled at runtime,
so no `--write` was needed).

## Phase 3 — Trim remaining boilerplate + scope-tightening (2026-07-19)

**Work completed (Part 2, WU-2):** deflated the remaining `skills=all` boilerplate —
`d7`, `env-dialect-core`, `env-dialect-windows` (hosts=windows preserved),
`status-honesty`, `terminal-stop`, `task` (ws + cloud), plus `cloud-override`
(cloud analog of the P2 `workstation-dispatch` deflation — done for cloud-profile
parity, the more-complete path). Prose-density only; all policy anchors survive
(`SEMANTIC_DIFF_PHASE3.md` Part A).

**Scope-tightening (lever 2) — trim-only, NO narrowing.**
`⚖ policy: scope-tightening selector narrowing → trim-only (no narrowing)`. The one
named candidate (narrow `workstation-dispatch` to exclude the never-fan-out
`mcp-test` cycle) is NOT provably safe: the `@section` `skills=` grammar is a
positive allowlist with no "all-except" form, so narrowing means enumerating every
fan-out skill and any future skill omitted from that list silently loses the
dispatch policy — the exact under-brief failure the SPEC calls worse than a few KB.
Conservative default (the plan's pre-authorized path) holds. Justification in
`SEMANTIC_DIFF_PHASE3.md` Part B; existing `test_dispatch.py` binding-matrix already
guards `workstation-dispatch` presence/absence across cycle classes.

**Measured:** Phase 3 saved a further 8,300 B; cumulative off the original seed
80,876 B (19.8%) across the 20 profiles. Re-locked to the new floor via
`--lock-in-profile`. The SPEC's ~9–10 KB directional target is not reached with
trim-only (smallest profile ~12.7 KB) — reaching it would require aggressive
scope-tightening/section removal the conservative default declined.

**Gates green:** `test_dispatch.py` + `test_project_skills.py` (228 passed);
`skill-size-ratchet.py --check` exit 0 at the new floor; `generate-coupled-skills.py
--check` exit 0 (no `--write` needed — the emitter's OUTPUT template does not appear
in the committed coupled SKILL.md files).

## Phase 4 — KPI measured baseline + gate-wiring confirmation (2026-07-19)

**Work completed (Part 2, WU-3):**
- `kpi-scorecard.py --capture-baseline cycle-prompt-assembled-bytes` → stamped
  `provenance: measured`, `value: 20843` (bytes — the max assembled profile after
  Phase 3), `captured_at: 2026-07-19` into `docs/kpi/registry.json` (script-owned).
- Gate wiring CONFIRMED already complete (no gap): `.claude/skill-config/gate-battery.json`
  `lint-skills` gate cmd is `python3 user/scripts/lint-skills.py --check-skill-size`
  (Phase 1 WU-3 wired it), and `--check-skill-size` runs `check_profiles` — so the
  assembled-profile ratchet is exercised on every battery pass. No edit needed.
- Rendered `docs/kpi/SCORECARD.md` (byte-stable); `kpi-scorecard.py --lint` exit 0
  with the row now measured.
- Test added (Sonnet sub-subagent, test-first characterization; reviewed on disk):
  `test_kpi_scorecard.py::TestCaptureBaseline::test_captures_cycle_prompt_assembled_bytes_measured`
  — hermetic fixture registry, asserts measured provenance + positive value +
  today captured_at + lint-clean. kpi test file 141 passed.

**Feature-level result:** all three deflation phases (2–4) landed. Cumulative
assembled-cycle-prompt reduction 80,876 B / 19.8% across the 20 dispatchable
profiles; the assembled ratchet now blocks re-bloat and the KPI baseline is
measured. This is a `MCP runtime: not-required` feature — the validation tail is
deterministic gates (already green); no live-runtime rows are pending. SPEC.md
**Status:** and COMPLETED.md remain gate-owned (`__mark_complete__`); the state
machine routes to /mcp-test (SKIP grant) → mark-complete next.
