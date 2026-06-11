---
kind: implementation-plan
feature_id: lazy-hardening
status: Ready
created: 2026-06-10
phases: [1, 2, 3, 4, 5, 6, 7]
---

> **Single-repo plan (claude-config)** — authored 2026-06-10 from the lazy-system audit
> (static audit of all 14 lazy-family SKILL.md files + state scripts, plus 8 real run
> transcripts: ~600 cycles, ~430 subagent spawns, ~70 AskUserQuestion exchanges).
> To execute: `/execute-plan user/scripts/plans/lazy-hardening.md`
> Tracking surface (checkbox persistence + Implementation Notes):
> `docs/specs/lazy-hardening/PHASES.md` (claude-config).
> Verification sanity-probes run against the AlgoBooth checkout as `--repo-root`.

# Implementation Plan — Lazy System Hardening

Harden the lazy skill family (lazy-batch, lazy-bug-batch, lazy, lazy-bug, cloud variants,
retro, shared components, `lazy-state.py` / `bug-state.py` / `lazy_core.py`) against the
findings of the 2026-06-10 audit. Three problem classes: **integrity side-doors** (models can
author validation sentinels the rest of the system triple-gates), **orchestrator cost**
(deterministic mechanics live in Opus prose — in the largest run the orchestrator emitted more
output tokens than all 311 subagents combined), and **fork drift** (lazy-bug-batch is a
hand-copied fork missing fixes the feature variant already has).

**Repo roots:**
- Windows (laptop): `C:\Users\Jacob\source\repos\claude-config`
- WSL: `/home/jacob/repos/claude-config`
- AlgoBooth (verification probes): `C:\Users\Jacob\repos\AlgoBooth` / `/home/jacob/repos/AlgoBooth`

**Total phases:** 7 · **Plan version:** v1 (reference-based)

---

## OPERATOR DECISION RECORD (locked 2026-06-10 via AskUserQuestion)

These six decisions were resolved with the operator before this plan was authored. They are
**locked** — do not re-litigate during execution; implement as specified.

| # | Decision | Resolution |
|---|----------|-----------|
| D1 | Halt-latency model | **Park-and-continue, opt-in via invocation flag** (e.g. `/lazy-batch 30 --park`). **Default (no flag): existing behavior** — a product decision halts the loop into the Step 1g resolution mode and waits for the operator. **With `--park`**: product decisions write NEEDS_INPUT.md, fire a push notification, park the item, and the loop advances to the next queue entry; parked questions are **flushed as one batched AskUserQuestion at first opportunity**: (a) any operator message mid-run, (b) no unparked work remains, (c) run end. Push notifications on halts fire in BOTH modes. |
| D2 | Auto-accept scope | **Two-key general classifier, active only in `--park` mode**: a decision may be auto-accepted (recommended option taken, fully logged) only when BOTH the cycle subagent classifies it `class: mechanical` AND the independent Step 1d.5 input-audit concurs. Default on any disagreement or absence: `product` (park it). Every auto-accept is recorded in the receipt and a run-end digest table. Without `--park`, no decision is ever auto-accepted — everything halts to the operator as today. |
| D3 | Cycle budget | **Split counters**: forward-work cycles consume `max_cycles`; resolution/meta cycles (blocked-resolve, decision-apply, recoveries, input-audits, stale-plan flips) get their own counter with a ceiling of 2× `max_cycles`. Both reported every cycle and at run end. |
| D4 | lazy-bug-batch drift | **Full by-reference rebuild** mirroring the lazy-batch-cloud pattern (path references into lazy-batch + a "Differences from /lazy-batch" table). |
| D5 | mcp-test inline fixes | **Bless with constraints**: an mcp-test cycle subagent MAY implement fix code inline when test-first and fully disclosed, but a cycle that wrote production code may NEVER write VALIDATED.md — it must end in BLOCKED/needs-re-verify; a later clean mcp-test cycle certifies. |
| D6 | LOOP-DETECTED sentinel authoring (auto-accepted as clear win) | The loop-breaker subagent may only write `NEEDS_INPUT.md` / `BLOCKED.md` — never `VALIDATED.md`, `SKIP_MCP_TEST.md`, `RETRO_DONE.md`, or any receipt. |

---

## EXECUTION MODEL — READ THIS FIRST

Same orchestrator + Sonnet subagent architecture as `lazy-bug-family.md`:

| Role | What it does | Allowed tools |
|------|-------------|---------------|
| **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch subagents, review output, run `--test` harnesses, update tracking docs, manage git | `Agent`, `Read`, `Bash` (tests/git only), task tracking, `Edit`/`Write` on PHASES.md only |
| **Sonnet subagent** | Write ALL source and skill changes (`.py`, `SKILL.md`, `_components/*.md`) | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob` |

**HARD CONSTRAINT:** the orchestrator MUST NOT `Edit`/`Write` any `.py`, `SKILL.md`, or
`_components/*.md`. Subagent prompts must name the absolute repo root and include verbatim:

> **You do not run `git commit` or `git push`.** Staging (`git add`) is also reserved for the
> orchestrator. Your job ends after producing the `GROUND-TRUTH OUTPUT` block defined in your briefing.

**Regression gates (run after every phase, both must exit 0):**
```bash
python3 ~/.claude/scripts/lazy-state.py --test
python3 ~/.claude/scripts/bug-state.py --test
python3 ~/.claude/scripts/test_lazy_core.py
```
Plus the zero-drift sanity probe: `python3 lazy-state.py --repo-root <AlgoBooth>` diffed against
a captured baseline whenever a phase claims zero behavior change.

**Line-number caveat:** all line anchors below are as-read on 2026-06-10. Re-locate by quoted
text, not raw line number.

---

## Phase 1 — Test safety net (zero behavior change)

**Goal:** Lock in the current behavior of `bug-state.py` before anything touches it. lazy-state
has a byte-pinned `--test` baseline; bug-state has none.

**Why first:** every later phase modifies the scripts; without a baseline there is no
zero-behavior-change contract for the bug pipeline at all.

**Deliverables:**
- [ ] Add `user/scripts/tests/baselines/bug-state-test-baseline.txt` (mirror the lazy-state
      baseline mechanism, including the temp-path normalization placeholder) and a durable test
      asserting `bug-state.py --test` output matches it.
- [ ] Add missing bug-state fixtures: **cloud mode** (currently ZERO `cloud=True` fixtures — the
      Phase-2 cloud fix lands in untested territory), real-device re-open (`STEP_DEVICE_REOPEN`
      never asserted), Step-9 `SKIP_MCP_TEST.md` and `MCP_TEST_RESULTS.md` paths,
      `backfill_receipts`, severity ordering among multiple unlisted bugs.
- [ ] Clean stale harness docstrings in both scripts ("All failures stem from
      NotImplementedError because compute_state() is a stub" at bug-state ~1382; the "RED"
      comments around scope kwargs).
- [ ] Capture an AlgoBooth `--repo-root` JSON baseline for `bug-state.py` (parallel to the
      existing lazy-state one).

**Runtime Verification:** all three regression gates exit 0; new fixtures fail-then-pass
demonstrated for at least the cloud and device-reopen cases (RED on a deliberately broken
assertion, GREEN after).

---

## Phase 2 — Integrity side-doors (P0)

**Goal:** Close every path where a model can silently author or defeat a validation gate.

**Script deliverables (`user/scripts/`):**
- [ ] **Receipt content validation** — `lazy_core.has_completion_receipt()` (~line 192) is a bare
      `.exists()`; `touch COMPLETED.md` defeats the completion-unverified gate. Require parseable
      frontmatter with `kind: completed|fixed` and a `provenance:` value; malformed receipt →
      loud diagnostic + treat as missing (i.e. `completion-unverified` still halts).
- [ ] **bug-state cloud guards** — in `compute_state()` (~704–756), when `DEFERRED_NON_CLOUD.md`
      exists without `VALIDATED.md`, control currently falls through to Step 10
      `__mark_fixed__` (archive with zero validation). Mirror lazy-state's Step-2
      cloud-saturated skip (~912–919) and Step-10 cloud hard-halt (~1425–1453). Resolve the dead
      terminals: either emit `TR_QUEUE_MISSING` / `TR_CLOUD_QUEUE_EXHAUSTED` (~107–108) or
      delete them and fix the module docstring + lazy-bug-batch's clean-stop list.
- [ ] **Unqueued Fixed-no-receipt bypass** — `_find_open_bug_dirs` (~356) pre-filters Fixed
      before the receipt gate runs, so only queue.json-listed bugs are enforced. Apply the gate
      uniformly (or at minimum emit a diagnostic for unqueued Fixed-without-FIXED.md dirs).
- [ ] **MCP_TEST_RESULTS freshness** — record the validating commit sha in
      `MCP_TEST_RESULTS.md` frontmatter and check it against HEAD before
      `__write_validated_from_results__`; stale results must not validate current code.
- [ ] **SKIP_MCP_TEST provenance** — add `granted_by: operator|pipeline` to the sentinel schema
      (`_components/sentinel-frontmatter.md`); `mcp-coverage-audit.md` step 2 treats only
      `operator` grants as vacuous-pass; `__write_validated_from_skip__` refuses
      `granted_by: pipeline` (routes to NEEDS_INPUT instead).

**Skill deliverables (apply to lazy-batch + lazy-batch-cloud fully; minimal inline patch to
lazy-bug-batch's copies — Phase 6's rebuild inherits the lazy-batch text):**
- [ ] **D6 — LOOP-DETECTED restriction** (lazy-batch ~499–529, bug-batch ~391–409, cloud
      ~457–487): remove the "write the missing sentinel directly" license for
      `VALIDATED.md`/`SKIP_MCP_TEST.md`/receipts; the loop-breaker may only author
      `NEEDS_INPUT.md`/`BLOCKED.md`. Also fix the stale anchor at lazy-batch ~531 (the quoted
      base-prompt sentence no longer exists).
- [ ] **Step 1e.4a recovery** (lazy-batch ~696–701, bug-batch ~508–530): forbid "tick the
      remaining PHASES.md verification boxes" as a reconciliation move without evidence the
      verification ran; on a verification-box mismatch the recovery writes NEEDS_INPUT.md.
- [ ] **Input-audit gaps** (Step 1d.5): (a) run the audit even when a spec cycle ends in
      needs-input/blocked (Jun 10 run: cycles 28 and 30 escaped audit by routing straight to
      Step 1g); (b) decisions beyond the 4-question cap must land in a durable follow-up
      `NEEDS_INPUT.md`, not an `## Open Questions` section that gets buried on rename.
- [ ] **Standing-directive protocol**: when a mid-run operator message implies a budget change,
      a standing resolution mode, or an early stop, the orchestrator echoes its interpretation
      back through one AskUserQuestion before entering the mode ("Extend to N cycles and
      auto-resolve blockers as add-phase-and-fix until X completes — confirm?"). Never end a run
      with budget and queue remaining without asking. Reject non-integer `max_cycles` args
      (the "infinity"→100 silent translation) with a clarifying question.
- [ ] **D5 — mcp-test inline-fix policy**: add to the mcp-test prompt overrides (lazy-batch
      ~381–412 and the bug-batch equivalent): inline fixes allowed only test-first + fully
      disclosed, and a cycle that modified production code MUST NOT write VALIDATED.md — it ends
      BLOCKED/needs-re-verify; a subsequent clean mcp-test cycle certifies.

**Runtime Verification:** regression gates green; new fixtures: malformed/empty receipt →
completion-unverified; bug-state cloud deferral → halt not `__mark_fixed__`; stale-sha
MCP_TEST_RESULTS → no validation; `granted_by: pipeline` skip → NEEDS_INPUT route.

---

## Phase 3 — Routing & parser fixes (cycle-burn class)

**Goal:** Eliminate the state-script blind spots that burned ~5+ Opus cycles per long run.

**Deliverables (`user/scripts/` unless noted):**
- [ ] **plan-bug wiring** — bug-state Step 4 (~605) always emits `spec-bug` when PHASES.md is
      absent; a concluded investigation loops (fired 3× in the Jun 10 run alone). Detect
      conclusion (SPEC `**Status:** In-progress` or a `## Conclusion`/investigation-concluded
      marker — pick one, document it in the SPEC template) and emit `plan-bug`. Update
      lazy-bug-batch's "never plan-bug" description text.
- [ ] **Fence-aware checkbox parsing** — `count_deliverables` (lazy_core ~784),
      `remaining_unchecked_are_verification_only` (~805), `_unchecked_wus_in_plan_scope` (~609)
      match `- [ ]` inside ``` fences (phantom deliverables → plan churn). Skip fenced lines;
      fix the `workstation-verification-only-bold-marker` fixture that currently depends on
      counting a fenced row.
- [ ] **Bold-marker heuristic hardening** — the verification-only heuristic clashed with
      `**Assessment:**` bold-leads twice in production (WSL run paid two corrective spawns).
      Anchor the heuristic to the `## Runtime Verification` section heading rather than bold
      prose markers.
- [ ] **Verification-row placement convention** — pin in the write-plan component / PHASES
      template: runtime-verification checkboxes live under `## Runtime Verification`, never
      under a phase's `### Deliverables` (two Sonnet recoveries + two stalls re-learned this).
- [ ] **Substring anchoring** — `roadmap_marks_complete` (lazy-state ~499) and
      `upstream_is_complete` (~703) use bare substring matches (a feature name that is a
      substring of a completed row spuriously hard-halts the whole queue); anchor to whole-row /
      word-boundary. Anchor `is_stub_spec`'s `Draft (pre-Gemini)` match (~623) to the
      `**Status:**` line / blockquote trailer.
- [ ] **Stale already-applied plan detection** — when every deliverable a plan references is
      already `[x]`, emit an inline `__flip_plan_complete_stale__`-style pseudo-action instead
      of `execute-plan` (two full Opus dispatches were burned verifying plans executed weeks
      earlier).
- [ ] **D3 — split counters + cap reachability** — fix the unreachable-cap bug (the
      1a→1b→1g/1h/1i→1a path never passes the Step 1c cap check) by checking the cap at the top
      of every resolution mode; implement forward vs meta counters per the decision record
      (skills: lazy-batch, lazy-bug-batch, cloud; report both in the cycle header and final
      report; meta ceiling 2× `max_cycles`). Fix halt-resolution.md's "(max_cycles bounds it
      regardless)" claim (~199).
- [ ] **Terminal honesty** — scoped `--feature-id`/`--bug-id` that matches nothing must emit a
      distinct `scoped-id-not-found` terminal, not `all-features-complete`/`all-bugs-fixed`;
      emit diagnostics for queue entries skipped for missing `name`/`id`/`spec_dir` (lazy-state
      ~856, bug-state ~270).
- [ ] **Misc**: replace the realign mtime freshness gate (~724–747) with a recorded upstream
      PHASES hash in the realign plan frontmatter; wire `check_stale_upstream` (~434) to a CLI
      flag or auto-run at probe start when `materialized.json` exists (the stale-upstream halt
      currently has no production writer); Step-10 "unexpected state" (~1428) must write the
      `NEEDS_INPUT.md` it tells the orchestrator to resolve.

**Runtime Verification:** regression gates green; new fixtures: concluded-investigation →
`plan-bug`; fenced checkboxes ignored; substring-collision ROADMAP row → no false halt;
stale plan → flip action; typo'd scope id → `scoped-id-not-found`.

---

## Phase 4 — Parked-decision protocol + notifications (D1/D2)

**Goal:** Convert decision stalls (35h idle in the WSL run; 6.4h + 7.3h overnight stalls; ~1M+
tokens of cache rebuild after each) into park-and-continue with batched flushes.

**Deliverables:**
- [ ] **Skill-level opt-in flag (D1)** — park-and-continue is gated by an invocation flag
      (canonical name: `--park`, e.g. `/lazy-batch 30 --park`), parsed alongside `max_cycles`
      in the arg-parsing step of lazy-batch / lazy-bug-batch / lazy-batch-cloud. **Without the
      flag, behavior is byte-for-byte the existing one**: NEEDS_INPUT halts into Step 1g and
      waits for the operator. The flag is recorded in the start banner and the final report.
- [ ] **Script support** — `bug-state.py`/`lazy-state.py` gain `--park-needs-input` (passed by
      the orchestrator ONLY when the skill was invoked with `--park`): a feature/bug carrying
      an unresolved `NEEDS_INPUT.md` is skipped (not halted), reported in a new `parked[]`
      output array (id, sentinel path, decision count, parked-since). Without the script flag,
      probe output is unchanged. Halt behavior always unchanged for single-dispatch wrappers
      (no `--park` support there). Parked items re-enter automatically once the sentinel is
      resolved/renamed (existing routing handles this).
- [ ] **Push notifications** — fire in BOTH modes: every park (with running parked-count),
      every halt, every flush, and run end. (Proven mid-run in the Jun 9 session.)
- [ ] **Flush protocol (D1, `--park` mode only)** — flush all parked decisions as batched
      AskUserQuestion(s) (≤4 questions per call, preserving the Zero-Context Operator Briefing
      discipline: verbatim context re-print in chat BEFORE the call, options 1:1 with chat) at
      first opportunity: (a) any operator message mid-run, (b) no unparked work remains, (c)
      run end. After answers: existing decision-apply machinery per item, sentinels renamed,
      loop continues.
- [ ] **Two-key auto-accept (D2, `--park` mode only)** — extend the NEEDS_INPUT schema with
      `class: mechanical|product` (author = cycle subagent) and require Step 1d.5 input-audit
      concurrence recorded in the sentinel (`audit_concurs: true`). Only when both keys agree
      `mechanical` AND a recommended option exists: auto-accept it, append the resolution with
      `resolved_by: auto-two-key`, log in the receipt and a run-end digest table ("auto-accepted
      decisions" with links). Any disagreement, absence, or missing audit → `product` → park.
- [ ] **Cache-aware note** — document in both batch skills that flushes (b)/(c) are also the
      cache-rebuild boundaries; do not interleave unrelated long waits between park and flush.

**Runtime Verification:** default-mode regression first — without `--park-needs-input` a
NEEDS_INPUT fixture still emits the `needs-input` halt and probe output is byte-identical to
the Phase 1 baseline. Then flagged-mode fixtures for `parked[]` output; a scripted dry-run
transcript walkthrough (orchestrator-level behavior is prose — verify via a
`/lazy-batch-retro`-style audit checklist addition: parks fire notifications, flush batches
match parked count, every auto-accept carries two keys + digest entry, zero parks/auto-accepts
in no-flag runs).

---

## Phase 5 — Script-ification of the orchestrator loop

**Goal:** Cut per-cycle orchestrator overhead from ~6 messages to ≤3 by moving deterministic
mechanics into the scripts. (Evidence: orchestrator output 1.64M tokens vs 1.01M for all 311
subagents in the WSL run; ~70–75% mechanical boilerplate; inline `__mark_complete__` /
`__mark_fixed__` cost 15–27 tool calls each.)

**Deliverables (`lazy-state.py` + `bug-state.py`, shared impl in `lazy_core.py`):**
- [ ] **`--verify-ledger <spec_path>`** — clean tree, HEAD==origin, plan `status: Complete`,
      zero non-verification `- [ ]`; returns pass/fail + failing check. Replaces 5 duplicated
      prose blocks (lazy Step 4, lazy-bug Step 4, both batch 1e.4a blocks, cloud 1e).
- [ ] **`--apply-pseudo <name> <spec_path>`** — script the deterministic sentinel/receipt
      writes: `__write_validated_from_results__`, `__write_validated_from_skip__`,
      `__write_deferred_non_cloud__`, `__flip_plan_complete_cloud_saturated__`, and the
      receipt+status-flip+sentinel-cleanup core of `__mark_complete__`/`__mark_fixed__`
      (reuse `write_completed_receipt` — currently only wired to `--backfill-receipts`).
      Gate checks stay where they are; the *writes* become mechanical. Resolve the
      receipt-write ownership contradiction (completion-integrity-gate.md says the gate writes
      the receipt; consumers say they do) by making `--apply-pseudo` the single author and
      updating both texts.
- [ ] **`--neutralize-sentinel <path>`** — scripted rename to the canonical `*_RESOLVED_<date>`
      form with collision handling (the rename collided once in practice).
- [ ] **Persisted probe signature** — the script stores the last emitted
      `(id, sub_skill, args, step)` tuple (e.g. `.lazy-state-last.json` under the repo's logs or
      docs dir) and emits `repeat_count` so loop detection is mechanical, not prose.
- [ ] **Single probe payload** — fold the git guard results (tree clean? HEAD==origin? unpushed?)
      and a pre-formatted cycle-header block into the probe JSON so the orchestrator's
      happy-path turn is: read payload → dispatch → record.
- [ ] **Skill text updates** — both batch orchestrators consume the new subcommands; delete the
      superseded prose blocks; happy-path cycle = probe → dispatch → verify/commit (≤3 messages).

**Runtime Verification:** regression gates green; fixtures per subcommand (verify-ledger each
failing check; apply-pseudo idempotency + refusal when gate inputs absent; neutralize collision
case; repeat_count increments across identical probes).

---

## Phase 6 — Fork rebuild + contradiction sweep (D4)

**Goal:** Rebuild lazy-bug-batch by-reference and fix every documented contradiction so the
family has one source of truth per rule.

**Deliverables:**
- [ ] **D4 — lazy-bug-batch by-reference rebuild**: mirror the lazy-batch-cloud pattern
      ("See ~/.claude/skills/lazy-batch/SKILL.md Step X" + a "Differences from /lazy-batch"
      table). Must inherit/port: Step 1d.0 mcp-test runtime pre-boot + "RUNTIME IS ALREADY UP" +
      "NO FIRE-AND-FORGET / resultless return is a violation" contract (the documented turn-loss
      failure will otherwise recur on bug runs); gate parity for `__mark_fixed__` (batch runs
      BOTH gates; `/lazy-bug` currently runs one — make them identical); Step 1.5 exclusion-set
      parity; 1d.5 prompt wording covering both spec-bug and spec-phases triggers. Replace its
      six `!cat`s with path references (~66KB saved per invocation).
- [ ] **lazy-batch componentization**: extract the three inlined prompt templates (cycle base
      prompt + per-skill overrides, LOOP block, input-audit prompt) and the Step 1f / Step 4
      research-halt announcement templates (near-duplicates — dedupe) into
      `_components/lazy-batch-prompts/*.md`, Read on demand by cycle type (~45KB of the 108KB
      file loads on 100% of invocations but is used on ~10% of cycles). Stop `!cat`ing
      sentinel-frontmatter.md (22KB) in lazy / lazy-bug / lazy-cloud — path-reference it. Fix
      the nested-`!cat` hazard in mark-fixed-archive.md (~19). Trim the 2–3KB frontmatter
      descriptions of all three batch skills to 2–3 sentences.
- [ ] **Contradiction sweep** (each item small; do them all):
      - lazy-batch-cloud HARD CONSTRAINT numbering off-by-one (~27/38/40/42/622/713); "Step 8
        deferral" stragglers (~348); lazy-status stale Step 8 (~22) + missing
        `__flip_plan_complete_cloud_saturated__` row.
      - lazy-batch stale Notes (~1186: "orchestrator does not commit anything itself except…");
        dangling `__write_deferred_non_cloud__` reference (~252); HARD CONSTRAINT 5 must
        enumerate the Step 5 resume + adhoc-enqueue AskUserQuestion exceptions (frontmatter
        description too).
      - sentinel-frontmatter.md lifecycle table: NEEDS_INPUT cleared by **rename**, not delete
        (~345); identify the NEEDS_RESEARCH owner.
      - Component coupling notes: completion-integrity-gate.md (~106–115) and
        mcp-coverage-audit.md (~88–96) must list the bug-pipeline consumers.
      - plan-feature ~75 authoring artifact ("wait, that's the sentinel file…") — remove.
      - lazy `__mark_complete__` internal step-label collision (~166–191).
- [ ] **lazy-batch-retro grading fixes**: add an explicit workstation **inline-override branch**
      (detect "INLINE OVERRIDE — LOAD-BEARING"; stop relying on the accidental "does NOT have
      the `Agent` tool" substring); add Sonnet LOOP-DETECTED + 1e.4a recovery dispatches to
      R-O-3's exception list; fix R-O-6's `-u` expectation; add `__flip_plan_complete_*` and
      `__mark_fixed__` to the Step 3 scan list; fix the Notes sentinel-frontmatter path (~608).
      Add Phase-4 checks: parks fire notifications; auto-accepts carry two keys + digest entry.

**Runtime Verification:** regression gates green (skills are prose — primary verification is a
fresh `/lazy-bug-batch-retro`-style compliance read of the rebuilt skill against a dry-run, plus
grep checks that every path reference resolves and no `!cat` of sentinel-frontmatter.md remains
in the thin wrappers).

---

## Phase 7 — Environment & compaction hardening

**Goal:** Stop runs dying or degrading on preconditions and context churn. (2 of 7 Windows
sessions were DOA on missing symlinks / missing python3; 7 failed node-PATH probes; post-compact,
41% of spawns lost their `model:` param and 13 Edit-without-Read errors accumulated in the WSL run.)

**Deliverables:**
- [ ] **Step 0 preflight** in both batch skills + single-dispatch wrappers, BEFORE the start
      banner and any remote sync: `.claude/skills` symlink resolves, `python3` runs,
      `~/.claude/scripts/lazy-state.py` (or bug-state) exists, node resolvable. On failure:
      print the setup recipe (symlink recreation per CLAUDE.md, path mapping) and stop — zero
      cycles consumed.
- [ ] **Node path** — bake the known Windows Git-Bash node location (`/c/nvm4w/nodejs`) into the
      preflight/skill-config so the per-call `export PATH` boilerplate disappears.
- [ ] **Compaction protocol** — the canonical dispatch template (subagent_type, model param,
      prompt skeleton) lives in a small on-disk component; after any compact boundary the
      orchestrator re-reads it before the next dispatch, and applies a "Read before Edit" rule
      (read-state is wiped by compaction). Note the operator's manual-compact-during-dispatch
      pattern as the sanctioned cadence.
- [ ] **Long-build ownership** — codify: any build/test expected to exceed a subagent turn is
      orchestrator-owned (harness-tracked background task) — subagent-backgrounded processes die
      at turn end (a `tauri build` silently vanished this way). Require `cargo check --release`
      before committing to a 20–40min packaged build.
- [ ] **Prompt hygiene** — purge the stale `interview_work_log_append` MCP-tool reference from
      all dispatch prompt templates (subagents reliably burn closing turns discovering it
      doesn't exist); add the canonical-sentinel-filenames + work-branch-only-commits clauses to
      the base dispatch prompt (3 subagent git/sentinel deviations in one Jun 9 run).

**Runtime Verification:** simulate the two DOA conditions (rename the symlink in a scratch
clone / shadow python3) → preflight catches both with the recipe printed; grep confirms zero
`interview_work_log_append` references remain under `user/skills/`.

---

## Risks & sequencing notes

- **Phase 2 edits text Phase 6 later replaces** (lazy-bug-batch inline copies). Accepted: the
  side-doors are live and cheap to patch twice; Phase 6 inherits the canonical lazy-batch text.
- **Phase 5 changes the orchestrator contract** — land script subcommands first, then the skill
  text that consumes them, in the same phase but separate commits, so a mid-phase interruption
  leaves prose fallbacks intact.
- **Phase 6 is the highest-regression-risk phase** (by-reference rebuild). Mitigation: the
  Phase 1 baselines + a post-rebuild compliance read; keep the old lazy-bug-batch text
  retrievable via git, not via a parallel file.
- The audit's full finding inventory (with quotes and line anchors) lives in the
  "Windows AlgoBooth Fable" session report of 2026-06-10 and the session-memory entry
  `lazy-system-audit-2026-06-10.md`; consult it if a deliverable's anchor text has drifted.
