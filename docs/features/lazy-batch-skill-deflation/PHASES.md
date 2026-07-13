# Implementation Phases — Lazy-Batch Skill Deflation

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
one hotspot excised, three dense hotspots explicitly deferred per RESEARCH_SUMMARY.md's
risk finding; Phase 2 not started; Phase 4 complete FOR the edits landed this session)

**MCP runtime:** not-required — pure claude-config harness mechanics (skill-prose edits, a
stdlib Python lint script + baseline JSON, coupled-pair overlay regeneration). No Tauri app, no
MCP-reachable surface. Validation is `pytest` (`test_skill_size_ratchet.py`,
`test_generate_coupled_skills.py`), `lint-skills.py`, `project-skills.py`, `lazy_parity_audit.py`,
and `doc-drift-lint.py`. Same untestable class as `friction-kpi-registry` → `SKIP_MCP_TEST.md`
at the MCP gate.

## Cross-feature Integration Notes

- **`coupled-pair-generation` (soft dep, LANDED as a substrate, premise refuted).** The generator
  (`generate-coupled-skills.py`) + committed overlay JSONs exist and `--check` is the freshness
  gate this feature relies on — but most derived blocks are `verbatim` overlay entries (not
  token-substituted), so every canonical excision in this feature still requires a hand-mirror
  into the derived file(s) BEFORE `--extract` can regenerate a fresh, `--check`-clean overlay.
  D4 (LOCKED) codifies this as the accepted fallback path.
- **`execute-plan-skill-diet` (Complete) — the method precedent.** Reused directly: rule-
  preservation-checklist-as-acceptance-gate, KPI shape, "content diet not mechanism change."
- **`efficacy-signal-integrity` (in-progress elsewhere) — cross-lane dependency for Phase 5.**
  That feature's `NEEDS_INPUT_PROVISIONAL.md` named a SKILLS-lane follow-up (D4's orchestrator-
  prose wiring); this feature's Phase 5 discharges it.

---

### Phase 1: Hotspot excision (PARTIAL — one hotspot landed, three deferred)

**Phase kind:** design

**Scope:** Per SPEC D1 (route on verdict fields, never narrate the machinery), excise the four
named hotspots: model-selection prose, §1c.5 (pseudo-skill handling), §1b/§1c.6 (terminal
handling + PushNotification policy), §1d.0 (runtime pre-boot). RESEARCH_SUMMARY.md's full-text
read of all four this session found the model-selection paragraph is the ONLY one that matches
the SPEC's "mostly restatement" characterization cleanly end-to-end; the other three carry a
long sequence of individually-incident-driven operational rules whose safe compression requires
a per-rule preservation checklist (the SPEC's own stated acceptance gate) built and audited
line-by-line — assessed as too large/risky to rush in this session without materially
increasing the chance of silently dropping a rule in the harness's most safety-critical,
production-driving prompt.

**Deliverables:**
- [x] `user/skills/lazy-batch/SKILL.md` — model-selection paragraph excised: 816 B → 353 B
  (−57%). Rule preserved verbatim: copy `cycle_model` from the probe (never omit it); `"sonnet"`
  only when the script appended the loop block (`repeat_count >= 2`); `"opus"` otherwise; the
  orchestrator never computes or overrides this. Rationale prose (cost-efficiency framing)
  compressed to the one clause needed to explain WHY the loop-block case exists, per D1.
- [x] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — same excision mirrored
  (D4 hand-mirror): 763 B → ~360 B. Same rule, same compression.
- [ ] <!-- descoped --> ~~**DEFERRED — §1c.5 inline pseudo-skill handling** (~18.5KB). Rule-preservation checklist not yet built. Follow-up session.~~ **DEFERRED** (operator complete-all directive, 2026-07-13; deferred Phase-1 hotspot tracked in SPEC + RESEARCH_SUMMARY.md)
- [ ] <!-- descoped --> ~~**DEFERRED — §1b/§1c.6 terminal handling + PushNotification policy** (~13.5KB + ~19KB — larger than the SPEC's original estimate; see RESEARCH_SUMMARY.md, 15+ distinct terminals each with their own dispatch rule, not a collapsible 5-row table). Follow-up session.~~ **DEFERRED** (operator complete-all directive, 2026-07-13; deferred Phase-1 hotspot tracked in SPEC + RESEARCH_SUMMARY.md)
- [ ] <!-- descoped --> ~~**DEFERRED — §1d.0 runtime pre-boot** (~34KB — the densest hotspot; cold-compile patient-wait, pre-Vite boot-liveness wait, soft owned-unverified READY, sidecar-pipe readiness, guard-takeover long-build contract are each individually incident-driven, not narration). Follow-up session; RESEARCH_SUMMARY.md recommends re-sizing this phase to ~2–3 sessions given the checklist granularity found.~~ **DEFERRED** (operator complete-all directive, 2026-07-13; deferred Phase-1 hotspot tracked in SPEC + RESEARCH_SUMMARY.md)

**Minimum Verifiable Behavior:** `grep -n "Model selection" user/skills/lazy-batch/SKILL.md
repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` shows the compressed 3-sentence form
in both; `wc -c` on both files shows the excised paragraph's byte delta; no other line in either
file changed except the two paragraphs excised.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Rule preservation: the compressed paragraph asserts the exact same three facts as the
  original (copy verbatim / never omit; sonnet-iff-loop-block; orchestrator never computes it).
  *(Evidence: `SKIP_MCP_TEST.md` — side-by-side diff review, this report's before/after text.)* <!-- verification-only -->
- **DEFERRED (next `/lazy-batch` run over a loop-resolution cycle):** observing the orchestrator
  still correctly copies `cycle_model` verbatim under the compressed prose (behavior-preserving
  by construction — the rule text is unchanged in substance, only rationale is compressed).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/skills/lazy-batch/SKILL.md`,
`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.

**Testing Strategy:** Manual side-by-side rule-preservation review (no automated test for
skill-prose content — matches `execute-plan-skill-diet`'s precedent). The three deferred
hotspots each need their OWN rule-preservation checklist authored BEFORE editing (SPEC Method
section) — not attempted this session; see RESEARCH_SUMMARY.md.

**Integration Notes for Next Phase:** Phase 2 (HISTORY sidecar + long-line sweep) has no
material to relocate yet — no "Motivating incident" narrative was touched by the one hotspot
landed this session (it had no incident citation to relocate). Phase 2 becomes substantive once
the three deferred hotspots land.

---

### Phase 2: HISTORY sidecar + long-line sweep (NOT STARTED)

**Phase kind:** design

**Scope:** Per the ratified `NEEDS_INPUT_PROVISIONAL.md` (D2, option A): create
`user/skills/lazy-batch/HISTORY.md`, keyed by rule id/section, and relocate dated "Motivating
incident" narratives there as the three deferred Phase-1 hotspots are excised, leaving a
`(burned: <slug>)` citation in the skill. Sweep the remaining `>500`-char paragraphs not covered
by Phase 1's named hotspots.

**Deliverables:**
- [ ] <!-- descoped --> ~~`user/skills/lazy-batch/HISTORY.md` — NOT YET CREATED (no content to seed it with until Phase 1's deferred hotspots land; creating an empty scaffold now would be premature — this feature's own D1 rule is "citation only where a rule exists because of a named incident," and no such citation has been authored yet this session).~~ **DEFERRED** (operator complete-all directive, 2026-07-13; Phase 2 gated on deferred Phase-1 hotspots — tracked in SPEC)
- [ ] ~~Long-line sweep beyond the four named hotspots — not started.~~ **DEFERRED** <!-- descoped --> (operator complete-all directive, 2026-07-13; Phase 2 follow-up tracked in SPEC)

**Minimum Verifiable Behavior:** N/A — not started.

**Runtime Verification:** N/A — not started.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1 (the deferred hotspots) substantially landed.

**Files likely modified:** `user/skills/lazy-batch/HISTORY.md` (new), `user/skills/lazy-batch/SKILL.md`.

**Testing Strategy:** Manual spot-check (5 relocated narratives reachable from their rule's
citation) per the SPEC's Validation Criteria table.

---

### Phase 3: Ratchet lint (COMPLETE this session)

**Phase kind:** integration

**Scope:** Per SPEC D3 (mechanical-internal, auto-accepted): a committed baseline JSON + a
stdlib lint script enforcing a per-file byte ceiling and long-line-count ceiling, opt-in per
file, wired into the same invocation path as `lint-skills.py`. Growth past baseline fails;
improvement lowers the ceiling only via an explicit `--lock-in` (never automatically).

**Deliverables:**
- [x] `user/scripts/skill-size-ratchet.py` — `check()` (byte + long-line ceiling comparison
  per baseline-listed file), `lock_in()` (lowers only — `min(current, existing)`, refuses to
  raise; `--new` seeds a not-yet-listed file), `load_baseline()`. Stdlib only; writes go
  through `lazy_core._atomic_write`.
- [x] `user/scripts/skill-size-baseline.json` — seeded at end-of-session sizes (post Phase 1's
  landed excision AND Phase 5's follow-up edits — see the file's own `notes` fields for the
  exact provenance of each ceiling) for `lazy-batch`, `lazy-batch-cloud`, `lazy-bug-batch`,
  `lazy`, `lazy-status` — the SPEC's named D3 scope.
- [x] `user/scripts/test_skill_size_ratchet.py` — 12 fixtures (clean pass, byte-ceiling
  regression, long-line regression, missing file, opt-in-ignores-unlisted, lock-in lowers on
  improvement, lock-in NEVER raises a ceiling, lock-in refuses an unlisted file without `--new`,
  lock-in seeds with `--new`, malformed baseline raises, missing baseline returns empty schema,
  AND a live self-check that the real repo tree + real baseline are clean).
- [x] `user/scripts/lint-skills.py` — new `--check-skill-size` flag (same dynamic-import pattern
  as the existing `--check-skill-config` flag), so the ratchet joins the existing invocation
  path rather than requiring a second CI entry point.
- [x] Docs: `CLAUDE.md` Scripts table row + Lint Commands example; `user/scripts/CLAUDE.md`
  Scripts table row.

**Minimum Verifiable Behavior:** `python user/scripts/lint-skills.py --check-skill-size` exits 0
on the current tree; artificially growing any listed file past its ceiling (fixture, not the
real tree) makes `check()` return a non-empty finding naming the file + metric + current vs.
ceiling.

**Runtime Verification** *(checked by integration test — NOT by the implementation agent):*
- [x] The ratchet actually fired mid-session: Phase 5's follow-up (ii) edit grew `lazy-batch`,
  `lazy-batch-cloud`, and `lazy-bug-batch` past their just-seeded ceilings, and
  `lint-skills.py --check-skill-size` correctly reported all three as `OVER-CEILING` (verified
  live, not simulated) before the baseline was deliberately bumped to the new end-of-session
  sizes — proving the gate fires on real growth, not just fixtures.
  *(Evidence: `SKIP_MCP_TEST.md` — this report's gate-run transcript.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (independent of Phase 1/2's content — deliberately sequenced first
per this session's risk assessment, since it is safe/mechanical and provides value even before
the full diet lands: it stops further silent accretion immediately).

**Files likely modified:** `user/scripts/skill-size-ratchet.py` (new),
`user/scripts/skill-size-baseline.json` (new), `user/scripts/test_skill_size_ratchet.py` (new),
`user/scripts/lint-skills.py`, `CLAUDE.md`, `user/scripts/CLAUDE.md`.

**Testing Strategy:** Hermetic `tmp_path` fixtures for every check/lock-in path; a live
self-check test pins the real repo tree + the real committed baseline stay clean (catches the
ratchet lying about its own subject).

---

### Phase 4: Derived-pair propagation (COMPLETE for edits landed this session; ongoing)

**Phase kind:** integration

**Scope:** Per SPEC D4 (LOCKED, fallback path): hand-mirror every canonical excision into
`lazy-batch-cloud` / `lazy-bug-batch` per their divergence tables, then regenerate overlays.

**Deliverables:**
- [x] Model-selection excision (Phase 1) mirrored into `lazy-batch-cloud` (present there as a
  distinct "mirrored with `/lazy-batch`" paragraph; no analog exists in `lazy-bug-batch`, so
  correctly NOT mirrored there).
- [x] Follow-up (i) fallback-prose fixes (Phase 5) mirrored into `lazy-bug-batch`
  (`long-build-ownership.md` site) and `_components/lazy-dispatch-template.md`
  (`cycle-prompt-addenda.md` site, consumed by both `lazy-batch-cloud` — via its own inline
  bullet — and `lazy-bug-batch`'s Step-1d prose).
- [x] Follow-up (ii) KPI-scorecard-flush wiring (Phase 5) mirrored into `lazy-batch-cloud`,
  including its "Differences from `/lazy-batch`" table (new row added — the coupled-pair
  contract requires the table stay accurate, not just the prose).
- [x] `python user/scripts/generate-coupled-skills.py --extract` re-run after every edit batch
  this session; `--check` green (all pairs byte-identical/fresh) at session end.
- [x] `python user/scripts/lazy_parity_audit.py --repo-root .` exit 0.
- [x] `python user/scripts/doc-drift-lint.py --repo-root .` exit 0 (only the two pre-existing,
  unrelated `doc-drift:deliberate-divergence`-marked exemptions).
- [ ] <!-- descoped --> ~~Remaining (ongoing): the three deferred Phase-1 hotspots will each need the same mirror-then-regenerate treatment when they land.~~ **DEFERRED** (operator complete-all directive, 2026-07-13; follows the deferred Phase-1 hotspots — tracked in SPEC)

**Minimum Verifiable Behavior:** `generate-coupled-skills.py --check` exits 0; `lazy_parity_audit.py
--repo-root .` exits 0.

**Runtime Verification:**
- [x] Both gates run and green this session (live, not simulated). *(Evidence: `SKIP_MCP_TEST.md`
  — this report's gate-run transcript.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1 / Phase 5 edits landed (this phase runs after each).

**Files likely modified:** `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`,
`user/skills/lazy-bug-batch/SKILL.md`, `user/skills/_components/lazy-dispatch-template.md`,
`user/scripts/coupled-overlays/*.overlay.json` (regenerated, not hand-edited).

**Testing Strategy:** `generate-coupled-skills.py --check` + `lazy_parity_audit.py` +
`doc-drift-lint.py`, all exit-0 gates; no new tests needed (this phase produces no new logic).

---

### Phase 5: SKILLS-lane follow-up items (i)–(iii) (COMPLETE) — ancillary, not in the original SPEC decomposition

**Phase kind:** integration

**Scope:** Three small items handed to this lane alongside the deflation work because they
touch the same files: (i) AlgoBooth-only skill-config references need a fallback or scoping so
the two `lint-skill-config.py` `SUPPRESSIONS` entries covering them can be deleted; (ii) route
the KPI scorecard regen through the claude-config commit path (efficacy-signal-integrity D4,
ratified option A); (iii) verify the canary flush wiring is already present.

**Deliverables:**
- [x] **(i)** Added same-line fallback prose ("AlgoBooth-only … absent → no-op") to all four
  bare-pointer sites: `lazy-batch/SKILL.md` ×2 (`long-build-ownership.md`,
  `cycle-prompt-addenda.md`), `lazy-bug-batch/SKILL.md` ×1 (`long-build-ownership.md`),
  `_components/lazy-dispatch-template.md` ×1 (`cycle-prompt-addenda.md`). Deleted the
  corresponding 4 `SUPPRESSIONS` entries in `user/scripts/lint-skill-config.py` (kept the
  unrelated 5th, `gemini-sprint.md` — out of scope). `python -m pytest
  user/scripts/test_lint_skill_config.py` — the four target warnings are gone (confirmed by
  diffing this session's run against a `git stash`-verified pre-session baseline run, which
  showed all four present as pre-existing suppressed warnings). One PRE-EXISTING, UNRELATED
  failure remains (`test_this_repo_is_clean`, `plan-structural-gate.md` dangling-reference
  errors) — verified via `git stash` to predate this session and originate outside the SKILLS
  lane; reported as a wanted cross-lane fix, not touched here (not this lane's ownership and
  not part of this feature's scope).
- [x] **(ii)** Added a new "KPI scorecard regen rides the SAME claude-config-rooted scope"
  paragraph immediately after the existing TWO-SCOPE efficacy/canary flush block in BOTH
  `lazy-batch/SKILL.md` §1c.6 and `lazy-batch-cloud/SKILL.md` §1c.6 (mirrored, + a new
  "Differences" table row in the cloud skill per the coupled-pair contract). The existing
  per-cycle per-repo-registry-gated regen is UNCHANGED (additive, not a replacement) — matches
  the ratified `NEEDS_INPUT_PROVISIONAL.md` choice exactly. `lazy-bug-batch` carries no
  KPI-scorecard mention at all, so correctly no mirror there.
- [x] **(iii)** Verified (grep, no edit): the harness-change canary watch
  (`efficacy-eval.py --canary`) is already wired at the end-of-run flush in both `lazy-batch`
  (3 mentions) and `lazy-batch-cloud` (5 mentions, incl. a cloud-specific TWO-SCOPE note). No
  duplication risk found; no action taken.

**Minimum Verifiable Behavior:** `grep -c "kpi-scorecard" user/skills/lazy-batch/SKILL.md
repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` shows the new claude-config-rooted
invocation in both; `python -m pytest user/scripts/test_lint_skill_config.py -q` shows 28/29
passing with the 1 pre-existing unrelated failure named above (not 6+ as at session start).

**Runtime Verification:**
- [x] All three items verified live this session (grep evidence + pytest run + `git stash`
  differential to isolate pre-existing debt). *(Evidence: `SKIP_MCP_TEST.md` — this report's
  transcript.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None (independent of Phases 1–4; done because "trivially compatible ...
touch the same files" per the assignment).

**Files likely modified:** `user/scripts/lint-skill-config.py`, `user/skills/lazy-batch/SKILL.md`,
`user/skills/lazy-bug-batch/SKILL.md`, `user/skills/_components/lazy-dispatch-template.md`,
`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.

**Testing Strategy:** `test_lint_skill_config.py` (pre-existing suite, no new tests needed —
the fix is a prose + allowlist change validated by the existing reference-sweep lint).
