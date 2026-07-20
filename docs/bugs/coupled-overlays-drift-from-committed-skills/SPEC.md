# Committed coupled overlays drifted from their hand-authored SKILL.md — `generate-coupled-skills.py --check` red on the committed tree — Investigation Spec

> Three recent commits edited a canonical + coupled SKILL.md but did NOT re-extract the per-pair overlays, so `generate-coupled-skills.py --check` (and `test_generate_coupled_skills.py`) is red on the committed tree for `lazy-bug-batch`, `lazy-batch-cloud`, and `lazy-cloud`. The advisory overlay-drift gate is not in the mandatory gate list, so the drift landed uncaught and surfaced reactively mid-run.

**Status:** Fixed
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/coupled-overlays-drift-from-committed-skills
**Fixed:** 2026-07-19 - reconciled overlays out-of-pipeline via `generate-coupled-skills.py --extract`
**Fix commit:** see FIXED.md
**Related:** `coupled-pair-generation` (PROVISIONAL) feature; CLAUDE.md "Coupled Skill Pairs" table; hardening-log 2026-07 lines 1321/1358/1376 (prior rounds that observed this drift and left it as "advisory, out of scope"); over-fit spin-off for the durable fix (drift gate not in mandatory gate list)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
  - Fixed         → fix landed + receipt written (out-of-pipeline reconciliation).
-->

---

## Verified Symptoms

1. **[VERIFIED]** `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` exits non-zero on the committed tree, reporting DRIFT for three derived skills: `lazy-bug-batch` (first divergent section `## HARD CONSTRAINTS`), `lazy-batch-cloud` (`## HARD CONSTRAINTS (non-negotiable)`), and `lazy-cloud` (`__preamble__`). — confirmed by direct run.
2. **[VERIFIED]** `python3 -m pytest user/scripts/test_generate_coupled_skills.py` fails on `test_committed_overlay_regenerates_derived_byte_identical[lazy-bug-batch]` and the sibling drift/`--check` tests — the same drift surfaced as a red suite. — confirmed by direct run.
3. **[VERIFIED]** The drift was NOT introduced by the in-flight `cycle-prompt-deflation` item (which never touched these files). A commit bisect shows the tree was clean at `4cee96e3` (spike-pipeline-role, DRIFT=0) and went red across `ca7f2c8b` (DRIFT=2) → `f79c1a12` (DRIFT=3), then stayed red through `4ba985f4` (Round 114). — confirmed by `git checkout` + `--check` at each commit.

## Reproduction Steps

1. On the committed tree at HEAD (`0698534f`), run `python3 user/scripts/generate-coupled-skills.py --check --repo-root .`.
2. Observe non-zero exit with three `DRIFT:` lines.
3. Run `python3 -m pytest user/scripts/test_generate_coupled_skills.py` — observe the byte-identity/`--check` tests red.

**Expected:** the committed overlays regenerate each derived SKILL.md byte-identically; `--check` exits 0.
**Actual:** three derived skills diverge from `generate(canonical, subs, overlay)` because the overlays were never re-extracted after their canonical/derived SKILL.md were hand-edited.
**Consistency:** deterministic on the committed tree.

## Evidence Collected

### Root cause (proven)

The `coupled-pair-generation` model: each derived skill is `generate(canonical_text, token_substitutions, overlay)`, where the per-pair `overlay` (`user/scripts/coupled-overlays/<pair>.overlay.json`) records the intended per-block divergences from the canonical. The PROVISIONAL contract makes **hand-authoring the load-bearing discipline**; the generator is a drift **gate** (`--check`), not a replacement authoring workflow. When an author edits a canonical or a derived SKILL.md, the matching overlay must be re-extracted (`--extract`) so `generate(...)` still reproduces the committed derived byte-for-byte.

Three commits edited coupled SKILL.md files WITHOUT re-extracting overlays:

- **`ca7f2c8b`** (`harden(skill-prose): orchestrator ignores grandchild sub-sub-agent notifications`) — edited `lazy-batch` (canonical), `lazy-bug-batch`, `lazy-batch-cloud`; overlays untouched → introduced `lazy-bug-batch` + `lazy-batch-cloud` drift.
- **`f79c1a12`** (`feat(concurrent-worktree-agent-coordination): Phase 1`) — edited `lazy-batch`, `lazy-batch-cloud`, `lazy-cloud`; overlays untouched → introduced `lazy-cloud` drift.
- **`4ba985f4`** (Round 114, `harden(skill-prose): surface orchestrator single-Agent-per-cycle rule`) — edited `lazy-batch` + `lazy-bug-batch`; overlays untouched → kept `lazy-bug-batch` drift.

In every case the committed derived SKILL.md is the **intended hand-authored state** (each commit deliberately edited or deliberately left the derived files — e.g. Round 114 explicitly "Cloud unchanged"). The defect is purely the missing overlay re-extraction, so the sanctioned reconciliation is `--extract` (rebuild overlays from the committed canonical+derived), which touches ZERO SKILL.md.

**Why it landed uncaught (the class, spun off separately):** the mandatory gate list run by harden rounds and feature commits includes `lazy_parity_audit.py` (the ENFORCED coupled-pair audit — green throughout) but NOT `generate-coupled-skills.py --check` (the advisory overlay-drift gate). Prior hardening rounds explicitly observed this drift and left it as "advisory / out of scope" (hardening-log 2026-07 lines 1321, 1358; line 1376 fixed it only as a `--extract` side effect). The durable prevention — wiring the drift gate into the mandatory gates — is out of scope for THIS instance fix and is front-enqueued as a separate `/spec-bug`.

### Fix scope (this round — instance only)

Run `python3 user/scripts/generate-coupled-skills.py --extract --repo-root .`, which rewrites only the three drifted overlays (`lazy-batch-cloud`, `lazy-bug-batch`, `lazy-cloud`) to record the current hand-authored divergences. No SKILL.md is modified. `--check` then exits 0 and `test_generate_coupled_skills.py` passes (34/34). This honors the PROVISIONAL hand-authoring contract: the shipped skills are unchanged; only the overlay drift-gate baseline is reconciled to reality.
