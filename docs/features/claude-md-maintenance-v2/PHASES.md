# Implementation Phases — CLAUDE.md Maintenance v2

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this feature edits harness skill/component markdown, 12
documentation files (`CLAUDE.local.md`), and one KPI registry JSON row. `claude-config` has no
Tauri/MCP dev-runtime surface; every validation criterion in the SPEC is static file inspection
(`wc -c`, `grep`, `Read`) or a single deterministic script invocation
(`kpi-scorecard.py --capture-baseline`). Docs-only class per the mcp-testing untestable-class
carve-out.

## Validated Assumptions

- **Every load-bearing assumption here is code-provable, not runtime-coupled.** Nothing in this
  plan crosses a live process boundary (no app, no MCP server, no build artifact consumed at
  runtime). The reachability axiom is satisfied by direct verification instead of a runtime spike:
  Phase 0's edit is confirmed by reading the merged component text as it renders when injected
  into each dependent skill (all `!cat`/reference-based — no build step to go stale); Phase 1/2's
  trims are confirmed by reading each file through the same repo symlink
  (`repos/cognito-forms/**/CLAUDE.local.md` → `Cognito Forms/**/CLAUDE.local.md`) that a live
  Cognito session already auto-loads through. No spike phase is required — recorded here per the
  Runtime Assumption Validation Gate's skip-reason requirement.
- **Byte-count baseline independently reconfirmed at authoring time (2026-07-17).** Fresh
  `wc -c` over the 12 files sums to exactly 50,182 B — matches both the SPEC's Executive Summary
  and the already-registered `claude-md-corpus-bytes` KPI baseline. No drift found.
- **The false purge-exception claim is independently reconfirmed false** (not just trusted from
  SPEC prose): `Cognito/Tasks/PurgeOrganizationQueueMessage.cs:46` does construct and throw
  `PurgeOrganizationException` — grepped directly against the live Cognito Forms working tree.
- **SPEC-example capability audit / MCP tool-existence audit / data-reach audit / module-move
  inbound-seam audit: all no-op for this feature.** No code examples consuming an API surface, no
  MCP tool catalog dependency, no entity/data-type retention or migration, and no file is moved,
  renamed, or deleted (only edited in place) — each audit's trigger condition is absent.

## Touchpoint Verification Summary

Verified inline (`Grep`/`Read`/`Bash`, dispatch not needed — the file set is small and every path
below was read or grepped directly against the live repo before drafting):

| File | Exists? | Verified state | Phase |
|---|---|---|---|
| `user/skills/_components/claude-md-review.md` | yes, 1204 B / 20 lines | "MANDATORY — DO NOT SKIP" heading frames the *review* as the deliverable; escape hatch is the last line; no mention of `CLAUDE.local.md` | 0 |
| `user/skills/retro/SKILL.md` | yes | Lines 411–418: 4-question generalization test table. Lines 450–455: 5-point durability checklist. Read-only source — not modified. | 0 (source) |
| `user/skills/_components/execution-contract.md` | yes | Line 24 carve-out: `` The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`, ... `` — no `CLAUDE.local.md` | 0 |
| `user/skills/fix/SKILL.md`, `fix-mobile/SKILL.md`, `implement-phase/SKILL.md`, `implement-phase-batch/SKILL.md` | yes (all 4) | each carries its own copy of the same carve-out phrase | 0 |
| `repos/cognito-forms/CLAUDE.local.md` | yes, 12,074 B | stale `<structure>` libs list + `<subdirectory-docs>` list (INVENTORY class); GetFieldPath/ModelSource gotcha lives here; no `Maintenance:` footer | 1 |
| `repos/cognito-forms/Cognito/CLAUDE.local.md` | yes, 8,120 B | false claim at line 9 ("no `PurgeOrganizationException` anywhere... zero matches repo-wide" — **verified false**, see above); flush-per-iteration + Stripe await-before-cast gotchas present; footer present | 1 |
| `repos/cognito-forms/Cognito.Core/CLAUDE.local.md` | yes, 4,420 B | reference exemplar (SPEC: ~10% bloat); footer present; flush-per-iteration gotcha present | 1 |
| `repos/cognito-forms/Cognito.Services/CLAUDE.local.md` | yes, 4,706 B | reference exemplar (SPEC: ~6% bloat); footer present | 1 |
| `repos/cognito-forms/Cognito.UnitTests/CLAUDE.local.md` | yes, 4,559 B | no footer; flush-per-iteration gotcha present | 1 |
| `repos/cognito-forms/Cognito.QueueJob/CLAUDE.local.md` | yes, 2,031 B | no footer; DequeueCount off-by-one gotcha present | 1 |
| `repos/cognito-forms/Cognito.Web.Client/CLAUDE.local.md` | yes, 1,796 B | no footer; holds one of two element-ui-fork statements and one of two server-types statements | 2 |
| `repos/cognito-forms/Cognito.Web.Client/apps/spa/CLAUDE.local.md` | yes, 6,425 B | no footer; SPEC's single largest bloat item (two pasted validation-report paragraphs ≈45% of file); holds the other element-ui-fork statement; Stripe await-before-cast gotcha also present here | 2 |
| `repos/cognito-forms/Cognito.Web.Client/apps/client/CLAUDE.local.md` | yes, 1,389 B | no footer | 2 |
| `repos/cognito-forms/Cognito.Web.Client/libs/model.js/CLAUDE.local.md` | yes, 2,030 B | no footer | 2 |
| `repos/cognito-forms/Cognito.Web.Client/libs/types/CLAUDE.local.md` | yes, 1,407 B | no footer; holds the other server-types statement | 2 |
| `repos/cognito-forms/Cognito.Web.Client/libs/vuemodel/CLAUDE.local.md` | yes, 1,225 B | no footer | 2 |
| `docs/kpi/registry.json` | yes | `claude-md-corpus-bytes` row **already present** (not a fresh promotion) at the row starting near "id": "claude-md-corpus-bytes"; `baseline.value: 50182`, `band: {warn: 36000, breach: 42000}` | 3 |
| `user/scripts/kpi-scorecard.py` | yes | `--capture-baseline <kpi-id>` confirmed as "the ONLY computed-field registry writer"; **no `--band` flag exists** — band is hand-edited, not script-written | 3 |

**Mechanical drift correction (anchor-grade, corrected in-plan, no halt needed):** SPEC's Part B
describes an "element-ui-fork ×3" duplication for Phase 2 to resolve. Verification shows only 2 of
the 3 hits are *substantive fork-usage statements* (`Cognito.Web.Client/CLAUDE.local.md` line 20
and `apps/spa/CLAUDE.local.md` line 6) — both already inside Phase 2's file set. The third hit is
an incidental mention inside the root file's stale `<structure>` libs list, which Phase 1 deletes
outright as INVENTORY regardless of Phase 2's dedup work. **No cross-phase coordination is
needed** — Phase 2's dedup is self-contained to its own 2 files, and the root file's mention
disappears as an ordinary side effect of Phase 1's INVENTORY-class deletion, in whichever order
the two phases run. The server-types "×2/×3" duplication is confirmed as exactly 2 substantive
statements (`Cognito.Web.Client/CLAUDE.local.md` line 22–23, `libs/types/CLAUDE.local.md` lines
1–21), both already inside Phase 2's file set — same conclusion, no coordination needed.

No premise-grade contradictions found — every factual claim in the SPEC (baseline byte count, the
false purge claim, footer coverage, bloat percentages) was independently reconfirmed true.

## Execution-Order Advisory (soft — not a Prerequisites dependency)

SPEC states Phase 0/1/2 have **no ordering dependency**, and that remains true for correctness.
But there is a self-referential execution-quality consideration worth surfacing for whoever runs
`/write-plan` + `/execute-plan` against this PHASES.md: Phase 1/2's own execution will pass
through `claude-md-review.md`'s post-implementation step (it fires after any implementation work,
including work that edits `CLAUDE.local.md` files). If Phase 1 or 2 executes **before** Phase 0
lands, the executor sees the *old*, un-inverted, "MANDATORY — DO NOT SKIP" framing right after
finishing a trim pass — a mildly perverse nudge to bolt prose back onto the files it just cut. If
Phase 0 has already landed, the same step now correctly steers toward "no update needed" as the
expected outcome. **Recommendation: land Phase 0 first** (or in the same batch, before Phase 1/2's
own post-implementation gate fires) purely to avoid this self-referential nudge — not because
Phase 1/2 are technically blocked on it.

---

### Phase 0: Prescription Rewrite (Part A)

**Scope:** Rewrite `user/skills/_components/claude-md-review.md` so it inverts the default (no
update is the normal, expected outcome of most implementation work), imports `/retro`'s existing
4-question generalization test and 5-point durability checklist as an aligned copy (not a `!cat`
of retro internals — retro's section lives embedded in a larger skill), promotes the "no updates
needed" escape hatch from buried-last-line to a first-class expected branch, and adds
`CLAUDE.local.md` to both the component's target-file list and the orchestrator write-carve-out
line in every skill that carries its own copy of that line.

**Deliverables:**
- [x] Rewrite `user/skills/_components/claude-md-review.md`: lead with "most implementation work
  needs no CLAUDE.md/CLAUDE.local.md update" framing (retitle away from "MANDATORY — DO NOT SKIP"
  as a review-is-the-deliverable heading); fold in the 4-question generalization test (source:
  `user/skills/retro/SKILL.md:411-418`) and the durability checklist (source:
  `user/skills/retro/SKILL.md:450-455`) as an aligned copy; promote "if no updates are needed,
  state so and move on" to a first-class expected outcome, not the last line; add `CLAUDE.local.md`
  alongside every existing `CLAUDE.md` mention in the target-file list.
- [x] Add a one-line parity note in `claude-md-review.md` pointing at
  `user/skills/retro/SKILL.md`'s generalization-test section (and vice versa in `retro/SKILL.md`)
  so a future edit to one prompts a check of the other, per SPEC's coupling note.
- [x] Update the write-carve-out line (`The ONLY files you may modify directly: ...`) in each of the
  5 files that carries its own copy: `user/skills/_components/execution-contract.md:24`,
  `user/skills/fix/SKILL.md`, `user/skills/fix-mobile/SKILL.md`,
  `user/skills/implement-phase/SKILL.md`, `user/skills/implement-phase-batch/SKILL.md` — add
  `` `CLAUDE.local.md` `` alongside `` `CLAUDE.md` `` in each. Also applied the same edit to
  `user/skills/execute-plan/SKILL.md:155` (differently-worded carve-out) and
  `repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md:41`
  (Cognito lane contract) — 7 carve-out edits total, per the task's expanded instruction.
- [x] Do NOT modify `user/skills/retro/SKILL.md` itself — it stays the source of truth for retro;
  only the aligned copy in the component changes (per SPEC Part A coupling note). Confirmed
  untouched.

**Minimum Verifiable Behavior:** reading the rewritten `claude-md-review.md` shows an inverted
default, the imported test + checklist, a first-class escape hatch, and `CLAUDE.local.md` in the
target list; grepping each of the 5 carve-out files for the write-carve-out line shows
`CLAUDE.local.md` present alongside `CLAUDE.md`.

**Runtime Verification** *(read-verification — no MCP; this repo has none):*
- [x] <!-- verification-only --> Read the final `claude-md-review.md` end to end; confirm it (a)
  leads with a "no update expected" framing rather than a review-as-mandatory-deliverable framing,
  (b) contains the 4-question generalization test table, (c) contains the 5-point durability
  checklist, (d) promotes the escape hatch out of last-line position, (e) names `CLAUDE.local.md`.
- [x] <!-- verification-only --> Grep the 5 carve-out files for the write-carve-out line; confirm
  `CLAUDE.local.md` appears in every one.
- [x] <!-- verification-only --> Read each of the known consumer skills
  (`user/skills/crud-skill/SKILL.md`, `user/skills/fix/SKILL.md`,
  `user/skills/fix-mobile/SKILL.md`, `user/skills/implement-phase/SKILL.md`,
  `user/skills/implement-phase-batch/SKILL.md`, and any skill that inherits
  `execution-contract.md`'s post-implementation step) to confirm the inherited text reads
  correctly in context — this is SPEC's own Phase 0 verification instruction, carried forward
  verbatim as a Runtime Verification row rather than left implicit.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (skill/
component markdown edit; validation is inspection, not execution). Consistent with the
project-wide `MCP runtime: not-required` declaration above — there is no MCP surface to defer.

**Prerequisites:** None. Independent of Phase 1 and Phase 2 (disjoint file sets, no shared state).
See the Execution-Order Advisory above for a non-blocking sequencing recommendation.

**Files likely modified:**
- `user/skills/_components/claude-md-review.md` — full rewrite (verified 1204 B / 20 lines today)
- `user/skills/_components/execution-contract.md` — one-line carve-out edit (line 24)
- `user/skills/fix/SKILL.md` — one-line carve-out edit
- `user/skills/fix-mobile/SKILL.md` — one-line carve-out edit
- `user/skills/implement-phase/SKILL.md` — one-line carve-out edit
- `user/skills/implement-phase-batch/SKILL.md` — one-line carve-out edit

**Testing Strategy:** Pure read/grep verification — no build, no test runner. Read the rewritten
component in full; grep the 5 carve-out files; spot-read the consumer skills listed above to
confirm the inherited text still reads coherently when injected into their surrounding sections.

**Integration Notes for Next Phase:**
- Phase 1/2 do not consume the rewritten component directly — they are pure content edits to the
  12 `CLAUDE.local.md` files. The only coupling is the soft execution-order advisory above.
- Phase 3 does not touch this component or the carve-out files at all.

---

### Phase 1: Trim the Backend + Root Files (Part B, batch 1)

**Scope:** Apply the SPEC's fixed rubric (DURABLE keep / INVENTORY delete / IMPLEMENTATION-NOTE
delete-or-extract / STALE delete-or-correct / agent-docs-covered → pointer) to the root
`CLAUDE.local.md` and the 5 backend-project files. Fix the two live defects that fall in this
batch's scope by hand regardless of rubric class. Standardize the `Maintenance:` footer onto every
file in this batch.

**Deliverables:**
- [x] Trim `repos/cognito-forms/CLAUDE.local.md` (12,074 B today): delete the stale
  `<structure>` libs list and `<subdirectory-docs>` list per the INVENTORY rule (hand-maintained
  mirrors that already omit real dirs — delete, do not correct, per SPEC Part B); apply the rubric
  to remaining sections; preserve the GetFieldPath/ModelSource gotcha (DURABLE,
  incident-anchored); add the `Maintenance:` footer (currently absent).
- [x] Fix the false purge-exception claim in `repos/cognito-forms/Cognito/CLAUDE.local.md`
  (line 9 today): delete the paused-feature narrative wrapper and the false "zero matches
  repo-wide" claim; if a durable current-behavior fact is buried in it (e.g. "`CoreService.
  PurgeOrganization` → `DeleteAllProjectEntities` is a plain unconditional hard-delete" — a true,
  general statement about production code, not the paused-feature narrative around it), extract
  and keep only that fact per the IMPLEMENTATION-NOTE rule ("extract the rule and drop the
  narrative"); otherwise delete the whole paragraph. Preserve the flush-per-iteration and Stripe
  await-before-cast gotchas (footer already present — no-op there).
- [x] Trim `repos/cognito-forms/Cognito.Core/CLAUDE.local.md` (4,420 B today, ~10% bloat per
  SPEC's audit — reference exemplar): light trim only; preserve the flush-per-iteration gotcha;
  footer already present.
- [x] Trim `repos/cognito-forms/Cognito.Services/CLAUDE.local.md` (4,706 B today, ~6% bloat per
  SPEC's audit — reference exemplar): light trim only; footer already present.
- [x] Trim `repos/cognito-forms/Cognito.UnitTests/CLAUDE.local.md` (4,559 B today, ~39% bloat per
  SPEC's audit): apply the rubric; preserve the flush-per-iteration gotcha; replace any content
  duplicating `.agents/agent-docs/testing.md` with a one-line pointer per Locked Decision L3; add
  the `Maintenance:` footer (currently absent).
- [x] Trim `repos/cognito-forms/Cognito.QueueJob/CLAUDE.local.md` (2,031 B today): apply the
  rubric; preserve the DequeueCount off-by-one gotcha; add the `Maintenance:` footer (currently
  absent).

**Minimum Verifiable Behavior:** `wc -c` sum over this batch's 6 files is measurably below the
pre-trim sum of 35,910 B (12,074 + 8,120 + 4,420 + 4,706 + 4,559 + 2,031); `grep -c
"PurgeOrganizationException\|zero matches repo-wide" repos/cognito-forms/Cognito/CLAUDE.local.md`
returns 0; all 6 files carry the `Maintenance:` footer.

**Runtime Verification** *(read/grep-verification — no MCP):*
- [x] <!-- verification-only --> `wc -c` each of the 6 files after trim; confirm the batch sum
  dropped from 35,910 B toward the rubric's guidance (per-file targets are guidance, not gates —
  the rubric itself is the authority, per SPEC).
- [x] <!-- verification-only --> Grep `repos/cognito-forms/Cognito/CLAUDE.local.md` for
  `PurgeOrganizationException` and `zero matches repo-wide`; confirm no hits.
- [x] <!-- verification-only --> Grep all 6 files for the `Maintenance:` footer marker; confirm
  present in every one (3 already had it — `Cognito`, `Cognito.Core`, `Cognito.Services` — confirm
  those weren't accidentally dropped during trim; 3 need it newly added — root, `Cognito.
  UnitTests`, `Cognito.QueueJob`).
- [x] <!-- verification-only --> Diff each trimmed file against its pre-trim version; spot-check
  that the GetFieldPath/ModelSource, flush-per-iteration, Stripe await-before-cast, and
  DequeueCount off-by-one gotchas are still present verbatim (or equivalently reworded, not
  dropped) in whichever file(s) they originated from.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (markdown
content edits; validation is `wc -c`/`grep`/diff inspection).

**Prerequisites:** None. Independent of Phase 0 and Phase 2 (disjoint file sets). See the
Execution-Order Advisory above.

**Files likely modified:**
- `repos/cognito-forms/CLAUDE.local.md` — delete stale inventories, trim, add footer
- `repos/cognito-forms/Cognito/CLAUDE.local.md` — fix false purge claim, trim
- `repos/cognito-forms/Cognito.Core/CLAUDE.local.md` — light trim (reference exemplar)
- `repos/cognito-forms/Cognito.Services/CLAUDE.local.md` — light trim (reference exemplar)
- `repos/cognito-forms/Cognito.UnitTests/CLAUDE.local.md` — trim, agent-docs pointer, add footer
- `repos/cognito-forms/Cognito.QueueJob/CLAUDE.local.md` — trim, add footer

**Editing mechanics reminder (from SPEC):** these 6 paths are symlinks into
`claude-config/repos/cognito-forms/`; the Edit tool refuses to write through a symlink, so target
the real paths under `claude-config/repos/cognito-forms/<subdir>/CLAUDE.local.md`. Commit in
`claude-config`, not the Cognito Forms repo (untracked there).

**Testing Strategy:** `wc -c` before/after per file; `git diff` against the pre-trim committed
version in `claude-config` to spot-check no DURABLE row was silently dropped; targeted grep for
the defect-fix and footer marker.

**Integration Notes for Next Phase:**
- No shared state with Phase 2 — the two batches touch disjoint files. Phase 2 does inherit the
  *pattern* used here (footer placement, defect-fix style, INVENTORY-deletion-not-correction) for
  consistency, but nothing here gates Phase 2's start.
- Phase 3 needs this batch's post-trim byte total (summed with Phase 2's) — hold the final
  per-file `wc -c` values so Phase 3 doesn't have to re-derive them from scratch, though it will
  re-verify via its own sweep regardless.

---

### Phase 2: Trim the Frontend Files (Part B, batch 2)

**Scope:** Apply the same rubric to `Cognito.Web.Client/` root plus `apps/spa`, `apps/client`,
`libs/model.js`, `libs/types`, `libs/vuemodel`. Standardize the `Maintenance:` footer. Resolve the
element-ui-fork and server-types duplications (both confirmed self-contained to this batch's files
— see Touchpoint Verification Summary's mechanical-drift correction above) down to one
authoritative statement each, with the other location reduced to a one-line pointer.

**Deliverables:**
- [x] Trim `repos/cognito-forms/Cognito.Web.Client/CLAUDE.local.md` (1,796 B today): apply the
  rubric; add the `Maintenance:` footer (currently absent); this file holds one of the two
  element-ui-fork statements (line 20, the fuller build-chain statement) and one of the two
  server-types statements (lines 22–23) — see the dedup deliverables below.
- [x] Trim `repos/cognito-forms/Cognito.Web.Client/apps/spa/CLAUDE.local.md` (6,425 B today,
  ~55% bloat per SPEC's audit — the single largest bloat item in the corpus): delete the two
  pasted validation-report paragraphs (IMPLEMENTATION-NOTE class, ≈45% of this file alone) per the
  rubric; add the `Maintenance:` footer (currently absent); this file holds the other
  element-ui-fork statement (line 6) and the Stripe await-before-cast gotcha (DURABLE — preserve).
- [x] Trim `repos/cognito-forms/Cognito.Web.Client/apps/client/CLAUDE.local.md` (1,389 B today):
  apply the rubric; add the `Maintenance:` footer (currently absent).
- [x] Trim `repos/cognito-forms/Cognito.Web.Client/libs/model.js/CLAUDE.local.md` (2,030 B
  today): apply the rubric; add the `Maintenance:` footer (currently absent).
- [x] Trim `repos/cognito-forms/Cognito.Web.Client/libs/types/CLAUDE.local.md` (1,407 B today):
  apply the rubric; add the `Maintenance:` footer (currently absent); this file holds the other
  server-types statement (lines 1–21, the fuller regeneration-workflow content) — see the dedup
  deliverables below.
- [x] Trim `repos/cognito-forms/Cognito.Web.Client/libs/vuemodel/CLAUDE.local.md` (1,225 B
  today): apply the rubric; add the `Maintenance:` footer (currently absent).
- [x] **Resolve the element-ui-fork duplication** (2 substantive statements — see Touchpoint
  Verification Summary): pick one authoritative home and reduce the other to a one-line pointer.
  Recommended default (defensible, not locked — adjust freely if the implementer finds a better
  fit): keep the fuller statement in `Cognito.Web.Client/CLAUDE.local.md` (monorepo-wide index, a
  natural single home for a cross-app convention) as authoritative; reduce `apps/spa/CLAUDE.local.md`'s
  copy to a one-line pointer.
- [x] **Resolve the server-types duplication** (2 substantive statements — see Touchpoint
  Verification Summary): pick one authoritative home and reduce the other to a one-line pointer.
  Recommended default (defensible, not locked): keep the fuller regeneration-workflow content in
  `libs/types/CLAUDE.local.md` (the actual owning package) as authoritative; reduce
  `Cognito.Web.Client/CLAUDE.local.md`'s copy to a one-line pointer.

**Minimum Verifiable Behavior:** `wc -c` sum over all 12 files (this batch's 6 + Phase 1's 6) is
≈34,000 B, a ≥30% reduction from the pre-trim 50,182 B baseline; all 12 files carry the
`Maintenance:` footer; the element-ui-fork and server-types statements each appear as exactly one
full statement + one pointer, not two full statements.

**Runtime Verification** *(read/grep-verification — no MCP):*
- [x] <!-- verification-only --> `wc -c` each of this batch's 6 files after trim, then sum with
  Phase 1's 6 post-trim values; confirm the full 12-file total is ≈34,000 B (≥30% reduction from
  50,182 B). This is the SPEC's headline validation criterion, and — since Phase 1/2 have no
  ordering dependency — the first phase to finish can only confirm its own half; the full-corpus
  assertion is only meaningful once BOTH have landed.
- [x] <!-- verification-only --> Grep all 6 files for the `Maintenance:` footer marker; confirm
  present in every one.
- [x] <!-- verification-only --> Grep for the element-ui-fork phrase across
  `Cognito.Web.Client/CLAUDE.local.md` and `apps/spa/CLAUDE.local.md`; confirm exactly one full
  statement and one pointer remain (not two full statements, not zero).
- [x] <!-- verification-only --> Grep for the server-types statement across
  `Cognito.Web.Client/CLAUDE.local.md` and `libs/types/CLAUDE.local.md`; confirm exactly one full
  statement and one pointer remain.
- [x] <!-- verification-only --> Diff `apps/spa/CLAUDE.local.md` against its pre-trim version;
  confirm the Stripe await-before-cast gotcha survived the heavy trim (this file loses ~55% of its
  bytes — the highest risk of an accidental DURABLE-row loss in the whole corpus).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (markdown
content edits; validation is `wc -c`/`grep`/diff inspection). Two consecutive N/A phases (0 and 1)
precede this one, but the terminal-MCP-stacking concern does not apply here: this feature has no
MCP surface at any phase (declared `MCP runtime: not-required` at the top), so there is no deferred
user-surface→engine→observable chain to have stacked in the first place.

**Prerequisites:** None. Independent of Phase 0 and Phase 1 (disjoint file sets). See the
Execution-Order Advisory above.

**Files likely modified:**
- `repos/cognito-forms/Cognito.Web.Client/CLAUDE.local.md` — trim, add footer, dedup (keep
  element-ui-fork authoritative copy, pointer server-types)
- `repos/cognito-forms/Cognito.Web.Client/apps/spa/CLAUDE.local.md` — heavy trim (delete
  validation-report prose), add footer, dedup (pointer element-ui-fork)
- `repos/cognito-forms/Cognito.Web.Client/apps/client/CLAUDE.local.md` — trim, add footer
- `repos/cognito-forms/Cognito.Web.Client/libs/model.js/CLAUDE.local.md` — trim, add footer
- `repos/cognito-forms/Cognito.Web.Client/libs/types/CLAUDE.local.md` — trim, add footer, dedup
  (keep server-types authoritative copy)
- `repos/cognito-forms/Cognito.Web.Client/libs/vuemodel/CLAUDE.local.md` — trim, add footer

**Editing mechanics reminder (from SPEC):** same as Phase 1 — these 6 paths are symlinks into
`claude-config/repos/cognito-forms/`; edit the real paths under `claude-config/repos/cognito-forms/`;
commit in `claude-config`.

**Testing Strategy:** `wc -c` before/after per file, then combined with Phase 1's totals for the
full-corpus check; `git diff` against pre-trim committed versions to spot-check no DURABLE row
(especially the Stripe gotcha in the heavily-trimmed `apps/spa` file) was silently dropped; grep
for the dedup outcome and footer marker.

**Integration Notes for Next Phase:**
- Phase 3 needs the full 12-file `wc -c` sum (this batch + Phase 1's), captured AFTER both have
  landed — Phase 3's Prerequisites therefore name both Phase 1 and Phase 2 explicitly, the one
  real ordering dependency in this feature.
- The dedup choices above (element-ui-fork → `Cognito.Web.Client/CLAUDE.local.md`; server-types →
  `libs/types/CLAUDE.local.md`) are recorded here so Phase 3's byte count and any future reviewer
  can tell the "one authoritative statement + pointer" shape was intentional, not an accidental
  content loss.

---

### Phase 3: Register + Baseline the KPI (Part C)

**Scope:** The `claude-md-corpus-bytes` row is **already promoted** into `docs/kpi/registry.json`
(verified present — see Touchpoint Verification Summary; this is not a fresh promotion despite
Part C's general "promoted at spec-finalization" phrasing, which already happened for this row).
This phase is narrowly: capture the real post-trim byte count into the row's `baseline` field via
the sanctioned script, and confirm or tighten the `band` thresholds against that real number.

**Deliverables:**
- [x] Run `python user/scripts/kpi-scorecard.py --capture-baseline claude-md-corpus-bytes
  --repo-root .` from `claude-config` to write the measured post-trim value into the row's
  `baseline` field. This is the sanctioned path — `kpi-scorecard.py` is "the ONLY computed-field
  registry writer"; do not hand-edit `baseline`.
- [x] Compare the captured value against the drafted band (`warn: 36000`, `breach: 42000`, set
  relative to a ~34,000 B guess per SPEC's Open Questions). If the real post-trim number diverges
  meaningfully from ~34,000 B, hand-edit `band.warn`/`band.breach` in the registry row — `band` is
  NOT a computed field (`kpi-scorecard.py` has no `--band` writer), so this is a direct JSON edit,
  not a script invocation.
- [x] Confirm the row's `notes` field still accurately describes the measurement (it currently
  says "Post-trim target ~34 KB" — update if the tightened band changes the target language).

**Minimum Verifiable Behavior:** `kpi-scorecard.py --capture-baseline claude-md-corpus-bytes`
exits 0, and `docs/kpi/registry.json`'s `claude-md-corpus-bytes` row shows a `baseline.value`
reflecting the real post-trim sum (not the pre-trim 50,182 placeholder) with a fresh
`captured_at` date.

**Runtime Verification** *(deterministic script run — no MCP):*
- [x] <!-- verification-only --> Run the capture-baseline command; confirm exit 0.
- [x] <!-- verification-only --> Re-open `docs/kpi/registry.json`; confirm `baseline.value`
  updated to the real post-trim number and `captured_at` updated.
- [x] <!-- verification-only --> Independently `wc -c` sum all 12 files; confirm it matches the
  script-captured `baseline.value` exactly (no drift between the manual sweep and the script's own
  count).
- [x] <!-- verification-only --> Confirm `band.warn`/`band.breach` were either left as-is (if the
  real number lands close to ~34,000 B) or tightened with a rationale matching the actual post-trim
  number, not the pre-trim guess.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; validation is the KPI
capture command itself plus a manual cross-check, exactly per SPEC's own Validation Criteria row
("`kpi-scorecard.py --capture-baseline claude-md-corpus-bytes` resolves and writes a value").

**Prerequisites:** Phase 1 AND Phase 2 both complete. This is the one genuine ordering dependency
in the feature — the post-trim byte count is only meaningful once all 12 files have been trimmed.

**Files likely modified:**
- `docs/kpi/registry.json` — `baseline.value`/`captured_at`/`provenance` written by the script;
  `band.warn`/`band.breach`/`notes` possibly hand-edited if the real number warrants tightening.
  The row itself already exists (verified present today) — no fresh row creation.

**Testing Strategy:** Deterministic script run (`--capture-baseline`) plus one independent manual
`wc -c` cross-check for parity. No mocks — pure file-count arithmetic and a JSON field write.

**Completion (gate-owned):** Any SPEC.md `**Status:**` flip to Complete, and any COMPLETED.md
receipt for this feature, is owned by the `__mark_complete__` gate once this phase's runtime
verification passes — not authored as a checkbox in this phase.

**Integration Notes for Next Phase:** None — this is the terminal phase.
