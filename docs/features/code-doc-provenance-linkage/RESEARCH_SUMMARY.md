---
kind: research-summary
feature_id: code-doc-provenance-linkage
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — code-doc-provenance-linkage

**Research: intentionally skipped (operator directive, 2026-07-04).** Internal harness mechanics
over surfaces this repo already owns; external prior art (ADR/traceability matrices, CODEOWNERS)
was already folded into `RESEARCH.md` at spec time. This file records the codebase survey that
verified every surface the SPEC names, plus the deltas found.

## Verified surfaces (line anchors as of lane HEAD b5c1021)

| SPEC claim | Verified at | Notes |
|------------|-------------|-------|
| `lazy_core.apply_pseudo` `__mark_complete__`/`__mark_fixed__` branch is the single scripted completion author | `lazy_core.py:3978` (branch), receipt write at `:4193` | Gate order: evidence-kind gate → receipt-noop → retro-staleness → auto-tick → coherence gate → receipt → status flips → sentinel cleanup → queue trim (features only) → ROADMAP strike. Provenance write slots AFTER queue trim/ROADMAP strike, before result assembly. |
| `write_completed_receipt` supports `completed_commit` but the mark-complete call site omits it | `lazy_core.py:749-806` (helper, field at `:785`); call site `:4193-4204` passes no `completed_commit` | Confirmed one-line closure as SPEC D4 states. `_current_head` is available in `lazy_core` (`:3142`). |
| `--cycle-end` already resolves `begin_head_sha` → HEAD | `lazy_core.cycle_end_friction_check` (`lazy_core.py:10403`); handlers `lazy-state.py:9454`, `bug-state.py` mirror | The handler itself does not read the marker — the bracket append needs its own marker read (new `lazy_core` helper), called from BOTH handlers before `clear_cycle_marker()`. |
| `append_friction_ledger_entry` fail-open append precedent | `lazy_core.py:12645` | Contract copied for `lazy-commit-brackets.jsonl`: swallow write errors, return False, never block the clear. |
| Locked-Decision surface parser | `lazy_core._parse_locked_decisions` (`:8968`), used by `gate_coverage` (`:9087`) | Three surfaces (Locked Decisions table / Resolved by Research / Key|Design Decisions). The distillate reuses this parser verbatim — zero new parsing. |
| `IMPLEMENTED.md` touches no state-machine read path | `apply_pseudo` cleanup deletes only `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` (`:4235`); `block-noncanonical-blocker-write.sh` matches `BLOCKED*` only | Confirmed: `compute_state` greps show no `IMPLEMENTED` reference anywhere in either state script. |
| Per-repo keyed state dir | `lazy_core.claude_state_dir` (`:9209`) — `LAZY_STATE_DIR` override returns exact dir (hermetic tests) | Bracket ledger lands there; machine-local as D4 documents. |
| Receipt/backfill vocabulary precedent | `lazy-state.py:1025 backfill_receipts` / `bug-state.py:1437` | `--backfill-provenance` mirrors the shape (walk receipted items, honest degraded provenance value). |

## Deltas / assumptions corrected

- **Bug receipts are mostly ARCHIVED:** claude-config today has **10** feature `COMPLETED.md`
  receipts, **1** in-place bug `FIXED.md`, and **39** archived (`docs/bugs/_archive/*/FIXED.md`)
  — matching the SPEC's estimates (10 / 39). Backfill must walk `docs/bugs/_archive/` (the SPEC
  says so) AND the non-archived bug dirs.
- **`--pr` sugar:** `gh` availability in this cloud lane is not guaranteed; the CLI degrades to a
  refusal naming the `--commits` fallback (as D8 requires). The skill documents the same.
- **AlgoBooth mirror is CROSS-REPO:** the `check-docs-consistency.ts` `SENTINEL_SCHEMAS`
  registration for `kind: implemented` (D2) lives in the AlgoBooth repo, which is not reachable
  from this claude-config lane. Recorded as an explicitly deferred row in PHASES.md.
- **Baselines:** adding in-file `--test` fixtures changes the byte-pinned baselines; regeneration
  is sanctioned only via `_normalize_smoke_output` (tests/baselines/README.md).
- **Parity audit:** `lazy_parity_audit.py::audit_state_script_parity` is regex-predicate-based
  (reorder-queue / reassert-owner / host-capability / cycle_prompt_ref). New CLI flags added
  SYMMETRICALLY to both scripts do not trip it; confirmed exit 0 at baseline.

## Integration points

1. `lazy_core.py` — producer (`write_provenance`), bracket ledger append + read, manual-link /
   lookup / lint / backfill helpers; `apply_pseudo` gate wiring; `completed_commit` threading.
2. `lazy-state.py` + `bug-state.py` — `--cycle-end` bracket append (coupled pair, mirrored) +
   four new CLI subcommands each (`--link-provenance`, `--provenance-lookup`,
   `--lint-provenance`, `--backfill-provenance`), all thin wrappers over `lazy_core`.
3. `user/skills/_components/sentinel-frontmatter.md` — `kind: implemented` schema registration.
4. `user/skills/link-provenance/SKILL.md` — new user-level skill (draft-then-approve front end).
5. D6 consumption wiring: `_components/lazy-batch-prompts/cycle-base-prompt.md`, `/spec-phases`,
   and the coupled `/lazy*` wrappers (`lazy`↔`lazy-cloud`, `lazy-batch`↔`lazy-batch-cloud`).
6. Docs: `user/scripts/CLAUDE.md` CLI-surface rows (tight, merge-conscious — sibling lanes touch
   the same blocks).
