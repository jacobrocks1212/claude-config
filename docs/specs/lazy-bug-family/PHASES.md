# PHASES — Lazy-Bug Family

> Tracking surface for `user/scripts/plans/lazy-bug-family.md`. This is the **persistent
> memory** the executing `/execute-plan` session checks off (`- [ ]` → `- [x]`) and annotates
> with Implementation Notes after each batch. The plan body stays read-only during execution
> per the execute-plan contract — all progress tracking lands here.
>
> **Feature:** Clone the `/lazy` autonomous-pipeline infrastructure to operate against
> `docs/bugs/`, standardizing the bug directory's frontmatter / plan structure / state-update
> protocol to match `docs/features/`. Research/Gemini/stub steps are dropped (N/A to bugs);
> the terminal action is **archive-on-fix** instead of mark-complete-in-place.
>
> **Cross-repo:** Phases 1, 2, 4 land in `claude-config`; Phases 3, 5 in `AlgoBooth`; Phase 6
> spans both. See the plan's Execution Schedule for repo + branch routing.

---

## Phase 1 — Shared core (`lazy_core.py`) · claude-config

**Goal:** Extract domain-agnostic helpers from `lazy-state.py` into an importable `lazy_core.py`;
rewire `lazy-state.py` to import them; keep `--test` green (zero behavior change). Riskiest phase —
it mutates the production features pipeline.

**Entry criteria:** None — first phase.

**Deliverables:**
- [x] Create `user/scripts/lazy_core.py` with the extracted helpers + a module docstring.
- [x] Rewire `lazy-state.py` to `from lazy_core import …` (or `import lazy_core`); resolve the
      `_DIAGNOSTICS` global so both modules share one diagnostics list per invocation (core owns
      it; each `compute_state()` calls `clear_diagnostics()` at entry).
- [x] `python3 lazy-state.py --test` passes with zero fixture changes.
- [x] Sanity: `python3 lazy-state.py` against AlgoBooth produces the same JSON as before
      (diff a captured baseline).

**Runtime Verification (workstation):**
- [x] `python3 ~/.claude/scripts/lazy-state.py --test` exits 0.

**Implementation Notes:**

#### Implementation Notes (Phase 1)
**Completed:** 2026-06-01
**Work completed:**
- `lazy_core.py` (581 lines, new): extracted domain-agnostic helpers verbatim — infra
  (`_atomic_write`, `_die`, `_DIAGNOSTICS`/`_diag`/`clear_diagnostics`, `_FENCE`), sentinel/plan
  parsing (`parse_sentinel`, `_parse_plan_frontmatter`, `_plan_status`, `_plan_lowest_phase`,
  `_plan_phase_set`, `_unchecked_wus_in_plan_scope`, `find_implementation_plans`,
  `_has_any_complete_plan`, `find_retro_plans`, `latest_retro_plan`,
  `retro_plan_has_significant_divergences`), PHASES analysis (`count_deliverables`,
  `_VERIFICATION_SECTION_RE`, `remaining_unchecked_are_verification_only`), receipts
  (`spec_status`, `has_completion_receipt`, `write_completed_receipt`).
- `lazy-state.py` (2948 → 2520 lines): rewired to `import lazy_core` + `from lazy_core import (...)`.
  `_state()` reads `lazy_core._DIAGNOSTICS` (the canonical shared list); `compute_state()` calls
  `clear_diagnostics()` at entry.
- `receipts` trio generalized for Phase-2 reuse: `write_completed_receipt(kind=, filename=)`,
  `has_completion_receipt(filename=)`, `spec_status` generic `**Status:**` reader — all with
  defaults reproducing current `COMPLETED.md`/`complete` behavior byte-for-byte.
- Characterization harness `test_lazy_core.py` (783 lines, 43 tests, stdlib-only — pytest is NOT
  installed in this env) + baselines under `tests/baselines/`.
**Integration notes:**
- Phase 2 `bug-state.py` imports the SAME `lazy_core` — reuse the generalized receipt helpers with
  `kind="fixed"`, `filename="FIXED.md"`.
- The diagnostics list is owned by `lazy_core`; any new state-computer MUST call
  `lazy_core.clear_diagnostics()` at the top of its `compute_state()`.
**Pitfalls & guidance:**
- Zero-behavior-change contract proven two ways: (1) `lazy-state.py --test` byte-identical to
  baseline after normalizing the per-run `tempfile` suffix (`lazy-state-fixtures-XXXXXXXX`
  placeholder), folded into a durable test `test_lazy_state_test_output_matches_baseline`; (2)
  `lazy-state.py --repo-root <AlgoBooth>` JSON byte-identical (empty diff).
- `lazy_core` MUST keep the underscore name and sit in `user/scripts/` so `import lazy_core`
  resolves under the `~/.claude/scripts` symlink.
- Two test-infra defects were fixed by a follow-up subagent (NOT production code): the baseline's
  non-deterministic temp path, and an assertion placed outside a `with TemporaryDirectory()` block.
**Files modified:**
- `user/scripts/lazy_core.py` — new shared core.
- `user/scripts/lazy-state.py` — rewired to import from `lazy_core`.
- `user/scripts/test_lazy_core.py` — new characterization harness (43 tests).
- `user/scripts/tests/baselines/{lazy-state-test-baseline.txt,lazy-state-algobooth.json,README.md}` — baselines.

---

## Phase 2 — Bug state machine (`bug-state.py`) · claude-config

**Goal:** A `compute_state()` for the bug lifecycle, emitting the same JSON contract, reusing
`lazy_core`. Includes its own in-file `--test` smoke fixtures.

**Entry criteria:** Phase 1 complete (`lazy_core.py` importable, `lazy-state.py --test` green).

**Deliverables:**
- [x] `load_bug_queue(repo_root)` reads `docs/bugs/queue.json` (same shape; `severity` optional).
      Hybrid order: queued entries first (listed order), then on-disk open bug dirs not in the
      queue, sorted by severity rank then `**Discovered:**` ascending. Skip `_archive/`.
- [x] `bug_severity(spec_path)` + `bug_discovered(spec_path)` frontmatter readers.
- [x] State machine steps: find-current → BLOCKED/NEEDS_INPUT → SPEC present? → PHASES? →
      plan/execute → retro → MCP gate (cloud/device aware, reused from core patterns) →
      `__mark_fixed__`.
- [x] Completion semantics: `Fixed`/`Won't-fix` + `FIXED.md` receipt → genuinely done; `Fixed`
      without receipt → `completion-unverified` halt; `Won't-fix` receipt-exempt.
- [x] Terminals: `blocked`, `needs-input`, `all-bugs-fixed`, `cloud-queue-exhausted`,
      `device-queue-exhausted`, `queue-missing`-equivalent (no queue **and** no open bugs →
      `all-bugs-fixed`; queue optional under hybrid).
- [x] `--backfill-receipts` writes `FIXED.md` for archived/`Fixed` bugs lacking one.
- [x] CLI mirrors `lazy-state.py` (`--cloud`, `--real-device`, `--repo-root`, `--test`).
- [x] In-file smoke fixtures covering: fresh-open-bug, blocked, mid-fix, phases-complete-no-retro,
      retro-done-needs-mcp, ready-to-mark-fixed, device-deferred, hybrid-ordering (queue + unlisted
      severity fallback), won't-fix-exempt, fixed-no-receipt-halt.

**Runtime Verification (workstation):**
- [x] `python3 ~/.claude/scripts/bug-state.py --test` exits 0.

**Implementation Notes:**

#### Implementation Notes (Phase 2)
**Completed:** 2026-06-01
**Work completed:**
- `bug-state.py` (1329 lines, new): full bug-lifecycle `compute_state()` mirroring
  `lazy-state.py`'s structure. `_bug_state()` builder emits the identical JSON contract keys
  (incl. `device_deferred_features`). `load_bug_queue()` (hybrid: queue.json order, then on-disk
  open dirs by `_SEVERITY_RANK` P0→P1→P2→Low then `**Discovered:**` asc, skipping `_archive/`).
  `bug_severity`/`bug_discovered` frontmatter readers. Completion gate (Fixed+FIXED.md=done,
  Fixed+no-receipt=`completion-unverified` halt, Won't-fix=receipt-exempt). Device axis
  (`resolve_real_device`, `_DEVICE_DEFERRED`, device-deferred terminal + real-device re-open)
  mirrored from lazy-state. `--backfill-receipts`, full CLI parity.
- 11 in-file `--test` smoke fixtures (test-agent owned section), all green.
- `lazy_core.has_completion_receipt` generalized with optional `filename="COMPLETED.md"` param
  (backward-compatible; bug-state passes `filename="FIXED.md"`).
**Integration notes:**
- Contract tokens are module-level constants (`TR_*`/`STEP_*`/`SKILL_*`) shared between the state
  machine and its `--test` assertions — single source of truth, no drift. Phase-4 skills dispatch
  against the `sub_skill`/`current_step` these emit.
- `bug-state.py --repo-root <AlgoBooth>` already runs clean against the UN-migrated tree (picks the
  first open bug for `spec-bug` investigation) — Phase 3 migration makes the parse warning-free.
**Pitfalls & guidance:**
- The fixtures + their assertions ARE the precise behavioral spec; implement to satisfy them.
- Shared-core regression guard is load-bearing: any `lazy_core` change must keep `lazy-state.py
  --test` byte-identical (verified) + `test_lazy_core.py` green.
**Files modified:**
- `user/scripts/bug-state.py` — new bug state machine.
- `user/scripts/lazy_core.py` — `has_completion_receipt` filename param (backward-compatible).

---

## Phase 3 — Bug frontmatter standard + migration · AlgoBooth

**Goal:** Bring `docs/bugs/` SPECs and queue up to the machine-parseable standard.

**Entry criteria:** Phase 2 complete (`bug-state.py --backfill-receipts` available).

**Deliverables:**
- [x] Define the canonical bug SPEC header (Status/Severity/Discovered/Fixed/Fix commit/optional
      Depends-on) and document it in `docs/bugs/CLAUDE.md` (Phase 6 finalizes prose).
- [x] Create `docs/bugs/queue.json` (hybrid seed from the open bugs; minimal — explicit
      ordering only where it matters).
- [x] Normalize the open bug SPEC headers: bare `**Status:**` token, prose moved to a `>`
      description / note line (fixed `cue-channel-audio-bleed` et al.).
- [x] Backfill `FIXED.md` receipts for the **27 archived** bugs (via `bug-state.py
      --backfill-receipts`) so future probes don't trip the receipt gate.
- [x] No bug-internal relative links broken (root-relative path rule already in CLAUDE.md).

**Runtime Verification (workstation):**
- [x] `python3 ~/.claude/scripts/bug-state.py --repo-root <AlgoBooth>` parses every migrated SPEC
      header without diagnostics warnings.

**Implementation Notes:**

#### Implementation Notes (Phase 3)
**Completed:** 2026-06-01 · repo: AlgoBooth (branch `feature/lazy-bug-pipeline`)
**Work completed:**
- **9 open bugs** (NOT 10): `qg-inventory-2026-05-30` is a QG audit artifact (INVENTORY.md +
  logs, no SPEC.md), NOT a lifecycle bug — `bug-state.py` silently skips SPEC-less dirs, so it is
  correctly excluded. Normalized the 9 real bug SPEC headers to bare canonical `**Status:**`
  tokens; mapped non-vocab statuses: `Draft`→`Open`, `Partially Fixed (downscoped)`→`In-progress`;
  moved all trailing prose to `>` notes (no info lost).
- `docs/bugs/queue.json` created — 9 entries (`id`/`name`/`severity`), hybrid-order note. NOTE:
  `bug-state.py load_bug_queue` requires BOTH `id` and `name` per entry (a name-less entry falls
  through to severity sort) — Phase 5's queue.json schema check enforces this.
- Backfilled `FIXED.md` for all **27 archived** bugs. The backfill surfaced **5 archived SPECs**
  with non-bare Status lines (`Fixed (downstream of …)`, `RESOLVED (…)`, etc.) + 1 with trailing
  whitespace — all normalized so the receipt gate recognizes them as `Fixed`.
- `docs/bugs/check-bug-links.py` (168 lines, stdlib) — reusable root-relative link-integrity
  checker; zero broken links introduced.
- `docs/bugs/CLAUDE.md` gained a canonical-header + queue.json section (Phase 6 finalizes prose).
**Integration notes:**
- Selected bug under the migrated tree = `cue-channel-audio-bleed` (top P1), diagnostics `[]`.
- Phase 5's docs-consistency checker validates this migrated tree (queue.json schema, bare Status,
  archive-coherence, fixed-requires-receipt) — `check-bug-links.py` is a complementary local check.
**Pitfalls & guidance:**
- Archiving moves dirs, so bug docs MUST use root-relative links (enforced by `check-bug-links.py`).
- Non-canonical Status prose is the #1 migration hazard — the bare-token rule is load-bearing for
  `spec_status()`.
**Files modified (AlgoBooth):**
- 11 open+archived `SPEC.md` headers normalized; `docs/bugs/queue.json` (new);
  `docs/bugs/check-bug-links.py` (new); 27 `_archive/**/FIXED.md` (new); `docs/bugs/CLAUDE.md`.

---

## Phase 4 — The three skills · claude-config (user-level)

**Goal:** Thin wrappers mirroring `lazy`/`-batch`/`-status`, dispatching against `bug-state.py`.

**Entry criteria:** Phase 2 complete (wrappers dispatch against `bug-state.py`).

**Deliverables:**
- [x] `user/skills/lazy-bug/SKILL.md` — mirror of `lazy` (one sub-skill per invocation;
      `__mark_fixed__` special action; status bookends; work-log).
- [x] `user/skills/lazy-bug-batch/SKILL.md` — mirror of `lazy-batch` (autonomous loop).
- [x] `user/skills/lazy-bug-status/SKILL.md` — mirror of `lazy-status` (read-only).
- [x] Reuse `_components/`: `sentinel-frontmatter.md`, `mcp-coverage-audit.md`,
      `completion-integrity-gate.md` where they generalize; add a bug-specific
      `mark-fixed-archive.md` component (the `git mv` + inbound-ref repoint) and decompose any
      shared block per /crud-skill Step 6.
- [x] Frontmatter `plan-mode: never` on all three (mirrors `lazy`).
- [x] Lint (`lint-skills.py` exit 0), projection (`project-skills.py`), capability lint.

**Runtime Verification (workstation):**
- [x] `python3 ~/.claude/scripts/lint-skills.py` exits 0.
- [x] `python3 ~/.claude/scripts/project-skills.py` resolves the three skills with no circular includes.

**Implementation Notes:**

#### Implementation Notes (Phase 4)
**Completed:** 2026-06-01 · repo: claude-config (branch `feature/lazy-bug-family`)
**Work completed:**
- `user/skills/lazy-bug/SKILL.md` (320 lines) — mirror of `/lazy`: stateless one-sub-skill-per-
  invocation dispatcher over `bug-state.py`; routes `spec-bug`/`spec-phases`/`write-plan`/
  `execute-plan`/`retro-feature`/`mcp-test` + the `__mark_fixed__` archive-on-fix terminal;
  FIXED.md receipt; status + work-log bookends. Research/Gemini/stub/realign steps dropped.
- `user/skills/lazy-bug-batch/SKILL.md` (595 lines) — mirror of `/lazy-batch`: autonomous Opus
  cycle loop; all 9 HARD CONSTRAINTS, Step 1g inline NEEDS_INPUT resolution, Step 1d.5 input-audit
  preserved; research-halt/`--allow-research-skip`/ingest machinery dropped.
- `user/skills/lazy-bug-status/SKILL.md` (152 lines) — mirror of `/lazy-status`: read-only
  dashboard (`allowed-tools: Bash, Read`; `model: haiku`).
- `user/skills/_components/mark-fixed-archive.md` (180 lines, new) — archive-on-fix procedure:
  completion-integrity gate → SPEC Status/Fixed/Fix-commit header → sentinel cleanup → `git mv`
  to `_archive/` → inbound-ref repoint (root-relative) + queue.json entry removal → commit.
  Won't-fix is receipt-exempt but still archived.
- All three carry `plan-mode: never`; all `!cat` component injections resolve.
**Integration notes:**
- The skills are now live (visible in the Skill tool registry as `lazy-bug`/`-batch`/`-status`).
- Projection: 69 skills / 74 components / 0 errors; projected lazy-bug skills have 0 unexpanded
  `!cat`. Phase 6's dry run exercises `/lazy-bug-status` + one `/lazy-bug` cycle end-to-end.
**Pitfalls & guidance:**
- All stray `lazy-state.py`/`docs/features`/`__mark_complete__` mentions in the new skills are
  intentional CONTRAST language ("drives bug-state.py NOT lazy-state.py"), verified — not leftovers.
- `!cat` injections must be standalone lines pointing at existing components (lint enforces this).
**Files modified (claude-config):**
- `user/skills/lazy-bug/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`,
  `user/skills/lazy-bug-status/SKILL.md`, `user/skills/_components/mark-fixed-archive.md` (all new).

---

## Phase 5 — docs-consistency gate for bugs · AlgoBooth

**Goal:** Mechanically enforce the bug contracts the way features are enforced.

**Entry criteria:** Phase 3 complete (gate validates the migrated standard).

**Deliverables:**
- [ ] Extend `scripts/check-docs-consistency.ts` (or a sibling `check-bugs-consistency.ts`) to
      validate: bug SPEC frontmatter (canonical Status/Severity), `docs/bugs/queue.json` schema,
      bug sentinels/plans frontmatter, `fixed-requires-receipt`, archive-coherence (`Fixed` ⇒
      under `_archive/`).
- [ ] Wire into `npm run qg` (new `qg:bugs-consistency` or fold into `qg:docs-consistency`).
- [ ] Gate passes against the migrated tree from Phase 3.

**Runtime Verification (workstation):**
- [ ] `npm run qg:bugs-consistency` (or folded gate) exits 0 against migrated `docs/bugs/`.

**Implementation Notes:**
<!-- executor appends -->

---

## Phase 6 — Docs + end-to-end dry run · both repos

**Goal:** Finalize documentation and prove the loop end-to-end.

**Entry criteria:** Phases 1–5 complete.

**Deliverables:**
- [ ] Rewrite `docs/bugs/CLAUDE.md` to mirror `docs/features/CLAUDE.md` (lifecycle, sentinel
      table, receipt-gating, plan schema, archive protocol).
- [ ] Update `user/scripts/CLAUDE.md` to drop the "(planned)" markers on `lazy_core.py` /
      `bug-state.py` and document the lazy-bug family as shipped.
- [ ] Dry-run `/lazy-bug-status` then a single `/lazy-bug` cycle against a real open bug; confirm
      the dispatch + sentinel writes are correct.
- [ ] `interview_work_log_append` for the build.

**Runtime Verification (workstation):**
- [ ] `/lazy-bug-status` reports the migrated queue correctly; one `/lazy-bug` cycle advances a
      real open bug (dispatch + sentinel writes verified).

**Implementation Notes:**
<!-- executor appends -->

---

## Acceptance (whole feature)

- `lazy-state.py --test` **and** `bug-state.py --test` both green.
- `npm run qg:bugs-consistency` (or folded) passes against migrated `docs/bugs/`.
- `/lazy-bug-status` reports correctly; one `/lazy-bug` cycle advances a real bug.
- No regression in the existing `/lazy` family (baseline JSON diff clean).
