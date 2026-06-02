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
- [ ] Create `user/scripts/lazy_core.py` with the extracted helpers + a module docstring.
- [ ] Rewire `lazy-state.py` to `from lazy_core import …` (or `import lazy_core`); resolve the
      `_DIAGNOSTICS` global so both modules share one diagnostics list per invocation (core owns
      it; each `compute_state()` calls `clear_diagnostics()` at entry).
- [ ] `python3 lazy-state.py --test` passes with zero fixture changes.
- [ ] Sanity: `python3 lazy-state.py` against AlgoBooth produces the same JSON as before
      (diff a captured baseline).

**Runtime Verification (workstation):**
- [ ] `python3 ~/.claude/scripts/lazy-state.py --test` exits 0.

**Implementation Notes:**
<!-- executor appends date, work completed, integration notes, pitfalls, files modified -->

---

## Phase 2 — Bug state machine (`bug-state.py`) · claude-config

**Goal:** A `compute_state()` for the bug lifecycle, emitting the same JSON contract, reusing
`lazy_core`. Includes its own in-file `--test` smoke fixtures.

**Entry criteria:** Phase 1 complete (`lazy_core.py` importable, `lazy-state.py --test` green).

**Deliverables:**
- [ ] `load_bug_queue(repo_root)` reads `docs/bugs/queue.json` (same shape; `severity` optional).
      Hybrid order: queued entries first (listed order), then on-disk open bug dirs not in the
      queue, sorted by severity rank then `**Discovered:**` ascending. Skip `_archive/`.
- [ ] `bug_severity(spec_path)` + `bug_discovered(spec_path)` frontmatter readers.
- [ ] State machine steps: find-current → BLOCKED/NEEDS_INPUT → SPEC present? → PHASES? →
      plan/execute → retro → MCP gate (cloud/device aware, reused from core patterns) →
      `__mark_fixed__`.
- [ ] Completion semantics: `Fixed`/`Won't-fix` + `FIXED.md` receipt → genuinely done; `Fixed`
      without receipt → `completion-unverified` halt; `Won't-fix` receipt-exempt.
- [ ] Terminals: `blocked`, `needs-input`, `all-bugs-fixed`, `cloud-queue-exhausted`,
      `device-queue-exhausted`, `queue-missing`-equivalent (no queue **and** no open bugs →
      `all-bugs-fixed`; queue optional under hybrid).
- [ ] `--backfill-receipts` writes `FIXED.md` for archived/`Fixed` bugs lacking one.
- [ ] CLI mirrors `lazy-state.py` (`--cloud`, `--real-device`, `--repo-root`, `--test`).
- [ ] In-file smoke fixtures covering: fresh-open-bug, blocked, mid-fix, phases-complete-no-retro,
      retro-done-needs-mcp, ready-to-mark-fixed, device-deferred, hybrid-ordering (queue + unlisted
      severity fallback), won't-fix-exempt, fixed-no-receipt-halt.

**Runtime Verification (workstation):**
- [ ] `python3 ~/.claude/scripts/bug-state.py --test` exits 0.

**Implementation Notes:**
<!-- executor appends -->

---

## Phase 3 — Bug frontmatter standard + migration · AlgoBooth

**Goal:** Bring `docs/bugs/` SPECs and queue up to the machine-parseable standard.

**Entry criteria:** Phase 2 complete (`bug-state.py --backfill-receipts` available).

**Deliverables:**
- [ ] Define the canonical bug SPEC header (Status/Severity/Discovered/Fixed/Fix commit/optional
      Depends-on) and document it in `docs/bugs/CLAUDE.md` (Phase 6 finalizes prose).
- [ ] Create `docs/bugs/queue.json` (hybrid seed from the 10 open bugs; minimal — explicit
      ordering only where it matters).
- [ ] Normalize the **10 open** bug SPEC headers: bare `**Status:**` token, prose moved to a `>`
      description / note line (fixes `cue-channel-audio-bleed` et al.).
- [ ] Backfill `FIXED.md` receipts for the **27 archived** bugs (via `bug-state.py
      --backfill-receipts`) so future probes don't trip the receipt gate.
- [ ] No bug-internal relative links broken (root-relative path rule already in CLAUDE.md).

**Runtime Verification (workstation):**
- [ ] `python3 ~/.claude/scripts/bug-state.py --repo-root <AlgoBooth>` parses every migrated SPEC
      header without diagnostics warnings.

**Implementation Notes:**
<!-- executor appends -->

---

## Phase 4 — The three skills · claude-config (user-level)

**Goal:** Thin wrappers mirroring `lazy`/`-batch`/`-status`, dispatching against `bug-state.py`.

**Entry criteria:** Phase 2 complete (wrappers dispatch against `bug-state.py`).

**Deliverables:**
- [ ] `user/skills/lazy-bug/SKILL.md` — mirror of `lazy` (one sub-skill per invocation;
      `__mark_fixed__` special action; status bookends; work-log).
- [ ] `user/skills/lazy-bug-batch/SKILL.md` — mirror of `lazy-batch` (autonomous loop).
- [ ] `user/skills/lazy-bug-status/SKILL.md` — mirror of `lazy-status` (read-only).
- [ ] Reuse `_components/`: `sentinel-frontmatter.md`, `mcp-coverage-audit.md`,
      `completion-integrity-gate.md` where they generalize; add a bug-specific
      `mark-fixed-archive.md` component (the `git mv` + inbound-ref repoint) and decompose any
      shared block per /crud-skill Step 6.
- [ ] Frontmatter `plan-mode: never` on all three (mirrors `lazy`).
- [ ] Lint (`lint-skills.py` exit 0), projection (`project-skills.py`), capability lint.

**Runtime Verification (workstation):**
- [ ] `python3 ~/.claude/scripts/lint-skills.py` exits 0.
- [ ] `python3 ~/.claude/scripts/project-skills.py` resolves the three skills with no circular includes.

**Implementation Notes:**
<!-- executor appends -->

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
