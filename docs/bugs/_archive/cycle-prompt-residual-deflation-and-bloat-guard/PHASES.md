# Implementation Phases — Cycle-Prompt Residual Deflation + Anti-Bloat Guard

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config harness/config plumbing with no MCP-reachable surface; every deliverable is verified by deterministic in-cycle gate exit codes + unit tests (the "structurally outside MCP reach" class per the mcp-testing SPEC). No live-runtime rows.

## Locked Decisions (do not re-open — see SPEC.md "Resolved Decisions")

1. Lint severity → HARD GATE from day one (no advisory-first soak).
2. Detector breadth → CONFIRMED SHAPES ONLY (ISO dates, `ISSUE \d`/`Round \d+`/`d8-effect-chains`,
   `Live incident:`, bare `docs/{bugs,features}/<slug>` literals). Loose narrative phrasing is a
   deliberate accepted miss.
3. Detector home → fold into `skill-size-ratchet.py` (no new script).
4. Allowlist → reason-required inline entries (mirrors `cli-surface-lint.py` / `lint-skill-config.py`).

## Validated Assumptions

**Step 2.7 capability audit skipped (justified):** every deliverable in this PHASES is a static
on-disk template edit or a deterministic Python lint over git-tracked files — there is no MCP
tool, runtime server, or external API surface anywhere in the affected area (`MCP runtime:
not-required` above). The capability audit's negative-evidence grep has nothing to check against;
skipping it here is the documented "structurally outside MCP reach" exemption, not an omission.

## Cross-feature Integration Notes

- **`docs/features/cycle-prompt-deflation` (composes).** This bug is the direct follow-up to the
  parent feature — Phase 1 here continues its exact playbook (trim-in-place, `SEMANTIC_DIFF`,
  `--lock-in-profile`, no reference-by-path) on the sections the parent deliberately left out of
  scope. Do not re-derive the discipline; reuse it.
- **`docs/features/coupled-pair-generation` (hard dependency, Phase 1).** `cycle-base-prompt.md`
  mirrors into bug/cloud variants via `generate-coupled-skills.py`. Every Phase 1 edit to that file
  MUST be followed by `python3 user/scripts/generate-coupled-skills.py --check --repo-root .`
  before the phase's work is considered done. (Expected exit 0 with no `--write` — the parent's
  Phase 2/3 notes confirm the emitter's OUTPUT template does not appear in the committed coupled
  SKILL.md files, so edits here don't shift committed output. Verify this holds; if `--check`
  reports drift, that itself is new evidence to resolve before continuing, not to work around.)
- **`docs/features/anti-overfit-design-gate` (Phase 2's design constraint).** Phase 2's war-story
  detector edits a matcher/pattern set inside `skill-size-ratchet.py`, a file this bug adds to
  `docs/gate/control-surfaces.json`. Run `python3 user/scripts/harness-gate.py --repo-root . --staged`
  (or `--range`) on the Phase 2 diff; if it flags `overfit` or any other detector, author
  `GATE_VERDICT.md` in this bug's dir per `_components/harness-change-gate.md` BEFORE the phase is
  considered complete — the structural, shape-keyed design (Locked Decision 2) is the intended
  defense, but the gate's own verdict is the proof, not an assumption.
- **`docs/features/lazy-batch-skill-deflation` (prior art).** The prose→verdict-rule playbook and
  the `skill-size-ratchet.py` gate this bug extends both originate here; no new pattern is invented,
  only the existing per-file ratchet is generalized to per-section + per-pattern.

## Touchpoint Audit

| File | Phase | Nature of change |
|---|---|---|
| `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` | 1 | Trim-in-place: Class A skill-specific sections + Class B rationale tails |
| `repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md` | 1 | Condense over-cap-gate-decomposition + audio-invariants blocks |
| `docs/bugs/_archive/cycle-prompt-residual-deflation-and-bloat-guard/SEMANTIC_DIFF.md` | 1 | New — no-policy-lost review artifact |
| `user/scripts/skill-size-baseline.json` | 1, 2 | Phase 1 re-locks the 20 assembled-profile ceilings; Phase 2 adds a new per-section ceiling block |
| `user/scripts/skill-size-ratchet.py` | 2 | New war-story pattern detector + per-section byte ceiling check |
| `user/scripts/test_skill_size_ratchet.py` | 2 | New failing-first tests for both checks |
| `user/scripts/lint-skills.py` | 2 | Confirm/wire the new checks under `--check-skill-size` |
| `docs/gate/control-surfaces.json` | 2 | Register `skill-size-ratchet.py` + the dispatched-prompt template family |
| `docs/bugs/_archive/cycle-prompt-residual-deflation-and-bloat-guard/GATE_VERDICT.md` | 2 (conditional) | Only if `harness-gate.py` flags the Phase 2 diff |
| `user/skills/_components/lazy-batch-prompts/CLAUDE.md` | 3 | New — authoring contract at the edit site |

## Phase 1 — Residual prose-density deflation (D1)

**Scope:** Trim war-story / historical-justification / redundant-rationale prose IN PLACE from
the dispatched cycle-subagent prompt, without dropping any enforceable rule. Prose-density ONLY —
no `@section` selector-narrowing, no path-shorthand/reference-by-path (both operator-rejected per
SPEC "Resolved Decisions" / "Out of scope").

**TDD:** no (prose-density trim; the existing pytest guards below are the regression net, not new
test authorship).

**Prerequisites:** None — first phase.

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`
- `repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md`
- `docs/bugs/_archive/cycle-prompt-residual-deflation-and-bloat-guard/SEMANTIC_DIFF.md` (new)
- `user/scripts/skill-size-baseline.json` (profiles block only)

**Deliverables:**
- [x] Deflate the never-touched skill-specific `@section` families `skill-execute-plan` and
      `skill-execute-plan-cloud`: strip `(Live incident: …)`, `(HARD — ISSUE 2, d8-effect-chains
      run)`, `(hydra-overlay false-block, 2026-07-19)` and other dated/issue narrative — but
      PRESERVE the `series_index` prerequisite-ordering ALGORITHM as terse imperative logic (it is
      load-bearing rule, not a war-story: compress the framing, keep the rule intact).
- [x] Deflate `skill-mcp-test-common` (the largest un-deflated block, ~5,658 B) and both
      `mcp-test-runtime` variants to terse imperative rules.
- [x] Deflate `skill-retro`, `skill-retro-feature`, `provenance-lookup`, `resume-safety` (both
      variants), and `park-spec-sentinel-mediation` to terse imperative rules.
- [x] Strip Class-B residual rationale tails from the already-deflated `skills=all` sections:
      `env-dialect-core` (`an absent file raises on empty stdin`, `a mature PHASES.md exceeds the
      Read cap; the slicer returns the index…`), `env-dialect-windows` (`No /mnt/c/... (WSL
      dialect)…` rationale clause), `workstation-dispatch` (the `2026-07-09 — the former
      inline-only ban is lifted…` removed-history clause) — keep each surviving rule, drop only
      the explanatory tail.
- [x] Condense the AlgoBooth addendum's `over-cap-gate-decomposition` and `audio-invariants`
      blocks to imperative rules.
- [x] Produce `SEMANTIC_DIFF.md` (this bug's dir) mapping EVERY removed clause to its surviving
      terse rule (proof no policy was dropped — follow the `SEMANTIC_DIFF_PHASE2.md` /
      `SEMANTIC_DIFF_PHASE3.md` table format from the parent feature), and list the load-bearing
      literals preserved verbatim: every `@section` selector line; `WORKSTATION DISPATCH —
      LOAD-BEARING`; tokens `{cwd}` / `{work_branch}` / `{receipt_name}` / `{item_label}`; the R5
      chained-command form; `git_safe_push`; the `git add -A` ban; `classify_conflict` +
      `conflict_kind: semantic` + `--park-provisional`; the `--verify-ledger` + `ok:true`
      four-condition certification; `cycle-subagent-bg-gate-guard.sh`; the `series_index` algorithm.
- [x] Re-lock the assembled-profile ratchet to the new lower floor: run `skill-size-ratchet.py
      --lock-in-profile <profile-id>` for each of the 20 seeded profiles (never hand-raise a
      ceiling — the script only lowers on improvement).
- [x] Run `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` and confirm
      exit 0 (per the Cross-feature Integration Notes above).

**Minimum Verifiable Behavior:**
```bash
python3 user/scripts/skill-size-ratchet.py --check   # exit 0 at the new lower floor
grep -REn "Live incident|ISSUE 2|hydra-overlay|d8-effect-chains" \
  user/skills/_components/lazy-batch-prompts/ \
  repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md   # empty output
```

**Testing Strategy:** No new tests are authored this phase (TDD=no, prose-density trim). The
existing pytest guards are the regression net and MUST stay green: `test_dispatch.py`'s
binding-matrix + residue guards (assert the emitter still assembles every profile with no
unbound `{token}` and that preserved literals survive) and `test_project_skills.py`'s
terminal-stop/variant tests. `SEMANTIC_DIFF.md` is the human-reviewable no-policy-lost artifact
that complements (not replaces) the automated guards.

**Runtime Verification:** none — static template artifact; deterministic gate exit codes above
are the proof. Do not author gate-owned rows in this phase.

**Integration Notes for Next Phase:** Phase 2's per-section byte ceiling is seeded from the sizes
this phase produces — Phase 2 CANNOT start until Phase 1's `--lock-in-profile` re-lock has landed
and `skill-size-baseline.json` reflects the deflated floor. Both phases write the same baseline
file, so they must not run concurrently (single-writer discipline).

## Phase 2 — Standing anti-bloat guard: war-story lint + per-section ceiling (D2a)

**Scope:** Extend `skill-size-ratchet.py` with a HARD-gate war-story pattern detector and a
per-section byte ceiling over the dispatched-prompt template family, so a future harden round
re-accreting narrative is refused at authoring time (Locked Decisions 1–4). Composes with, does
not replace, the existing whole-assembled-profile ceiling.

**TDD:** yes.

**Prerequisites:** Phase 1 complete (per-section ceilings seed from deflated sizes; shared
`skill-size-baseline.json` writer).

**Files likely modified:**
- `user/scripts/skill-size-ratchet.py`
- `user/scripts/skill-size-baseline.json` (new per-section block, seeded post-Phase-1)
- `user/scripts/test_skill_size_ratchet.py`
- `user/scripts/lint-skills.py`
- `docs/gate/control-surfaces.json`
- `docs/bugs/_archive/cycle-prompt-residual-deflation-and-bloat-guard/GATE_VERDICT.md` (conditional — only
  if `harness-gate.py` flags the diff)

**Deliverables:**
- [x] Write failing tests first in `test_skill_size_ratchet.py`: (a) a fixture dispatched-prompt
      template carrying each confirmed war-story shape makes the check FAIL, naming the file and
      the matched shape; (b) a fixture section over its per-section byte ceiling FAILS, naming the
      section; (c) a reason-required allowlist entry RESCUES a genuine load-bearing literal that
      would otherwise match a shape; (d) an ordinary `SKILL.md` / docs file carrying a date is NOT
      flagged — scope is dispatched-prompt templates ONLY, never orchestrator/docs prose.
- [x] Implement the war-story pattern detector over CONFIRMED SHAPES ONLY (structural, shape-keyed
      — not incident-literal, so it passes `harness-gate.py`'s own overfit detector): ISO-date
      tokens `\b20\d\d-\d\d-\d\d\b`, `ISSUE \d` / `Round \d+` / `d8-effect-chains`, the literal
      `Live incident:`, and bare `docs/{bugs,features}/<slug>` incident literals. Scope strictly to
      `user/skills/_components/lazy-batch-prompts/*.md` + per-repo
      `<repo>/.claude/skill-config/cycle-prompt-addenda.md` — never `SKILL.md` or general docs.
- [x] Implement the per-section byte ceiling: extend `skill-size-baseline.json` with a new
      per-`@section` block (keyed by section name, seeded at post-Phase-1 sizes) and a
      corresponding check function in `skill-size-ratchet.py` alongside the existing per-file and
      per-profile checks.
- [x] Implement a reason-required INLINE allowlist for genuine load-bearing literals that would
      otherwise trip the war-story detector (mirror `cli-surface-lint.py`'s `<!-- marker -->` /
      `lint-skill-config.py`'s `SUPPRESSIONS` pattern — every exemption carries a reason at its
      point of use).
- [x] Fold both new checks into the default `--check` path and confirm they run reachable via
      `lint-skills.py --check-skill-size` (already shelled by the gate battery — no new battery
      entry needed if wiring is correct; verify, don't assume).
- [x] Register `user/scripts/skill-size-ratchet.py` and the dispatched-prompt template family glob
      (`user/skills/_components/lazy-batch-prompts/**`) in `docs/gate/control-surfaces.json`
      `control_surfaces[]`.
- [x] Run `python3 user/scripts/harness-gate.py --repo-root . --staged` (or `--range`) on the
      change. If it flags the matcher-set edit, author `GATE_VERDICT.md` in this bug's dir per
      `_components/harness-change-gate.md` before the phase is considered complete — the
      structural shape-keyed design above is the intended overfit defense; the verdict records the
      judgment call, not a rubber stamp.

**Minimum Verifiable Behavior:** adding any confirmed war-story shape to a dispatched-prompt
template makes `python3 user/scripts/lint-skills.py --check-skill-size` exit 1, naming the file and
the shape; removing it makes the same command exit 0.

**Testing Strategy:** strict TDD — write the four failing fixtures in `test_skill_size_ratchet.py`
first, confirm red, then implement the detector + ceiling + allowlist until green. Re-run the full
Phase 1 regression net (`test_dispatch.py`, `test_project_skills.py`) to confirm the new checks
don't false-positive against the deflated Phase 1 output.

**Runtime Verification:** none — deterministic gate exit codes are the proof.

**Integration Notes for Next Phase:** Phase 3 is disjoint (a new file, no shared edit surface) and
can be authored independently of this phase's completion, but should reference the concrete
detector/ceiling names this phase lands (not aspirational ones) — hold Phase 3 authoring until
Phase 2's function/flag names are settled to avoid documenting a contract that doesn't match code.

## Phase 3 — Authoring-contract CLAUDE.md (D2b)

**Scope:** Author a new directory-level `CLAUDE.md` stating the dispatched-prompt authoring
contract at the edit site (none exists there today). Disjoint files from Phase 1 — independent.

**TDD:** no (documentation deliverable).

**Prerequisites:** None (disjoint from Phase 1).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/CLAUDE.md` (new)

**Deliverables:**
- [x] Write `user/skills/_components/lazy-batch-prompts/CLAUDE.md` covering: these files are
      assembled by `lazy_core.emit_cycle_prompt` and DISPATCHED VERBATIM to a subagent — they
      carry imperative rules + load-bearing marker literals ONLY; incident/provenance/dated-history
      narrative belongs in the SPEC/IMPLEMENTATION_NOTES, never the prompt (point at
      `skill-size-ratchet.py` / `lint-skills.py --check-skill-size` as the enforcing mechanism);
      the `@section` selector grammar + emitter contract (how sections are chosen/bound); the
      deflation playbook (trim-in-place, never reference-by-path, per
      `phases-slice-scoped-reads`'s precedent failure); the preserved-load-bearing-literal list
      (mirroring `SEMANTIC_DIFF.md`'s list); the per-section + assembled-profile ratchet and how to
      re-lock it. Follow the style/altitude of the sibling `user/skills/_components/CLAUDE.md`
      (concise, load-bearing facts only — not a restatement of the SPEC).

**Minimum Verifiable Behavior:** `python3 user/scripts/lint-skills.py` and
`python3 user/scripts/doc-drift-lint.py --repo-root .` both stay green (the new file introduces no
broken injection, no undeclared reference, no doc-drift finding).

**Testing Strategy:** no new tests — a documentation-only deliverable verified by the two lint
gates above staying green (they would catch a malformed/broken reference in the new file).

**Runtime Verification:** none.

**Integration Notes for Next Phase:** none — this is the final phase.

---

**Completion (gate-owned):** `**Status:**` flip to `Fixed`, the `FIXED.md` receipt, and the
archive-on-fix move (`bug-state.py --archive-fixed`) are owned entirely by the `__mark_fixed__`
gate — no phase above performs them as a checkbox.
