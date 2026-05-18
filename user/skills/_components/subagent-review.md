### Batch Review (MANDATORY — DO NOT SKIP)

**STOP.** Do not proceed to the next batch, update PHASES.md, or do anything else until this entire review protocol is complete.

> **Anti-pattern (NEVER do this):** Reading a few files, saying "looks correct", and moving on. That is NOT a review. Every batch must go through the full protocol below — no exceptions, no shortcuts.

Wait for ALL implementation subagents in the current batch to complete before beginning review. Do not review incrementally — the review covers the entire batch as a unit.

---

#### Step 1: Measure Batch Scope (MANDATORY FIRST ACTION)

Run this command NOW — before reading any files or assessing anything:

```bash
git diff --stat
```

Count total files changed and total lines changed (insertions + deletions) from the output.

**You must print one of these two messages verbatim before continuing:**

- If **≤ 2 files AND ≤ 150 lines changed:**
  > `📋 Reviewing inline — batch touched [N] file(s), [M] lines. Changes are small enough to review directly.`

- If **> 2 files OR > 150 lines changed:**
  > `🔍 Spawning review subagent — batch touched [N] file(s), [M] lines. Delegating to a dedicated reviewer.`

If neither message appears in your output, you have violated the protocol. Go back and do it.

---

#### Step 1.5: Ground-Truth Verification Gate (MANDATORY — RUN BEFORE ANY SUBSTANTIVE REVIEW)

> **Why this exists:** Subagents have repeatedly reported "work is already done" or "this was in a prior commit" when ground-truth investigation showed the work was newly performed in their own session. Treating subagent reports as fact rather than hypothesis has cost ~5 minutes per incident across multiple plans. This gate makes report falsification mechanically detectable before any prose review happens.

For every subagent report in this batch, locate the fenced `GROUND-TRUTH OUTPUT` block at the end of the report. If a subagent did not produce one, the verdict is automatically `NEEDS-REWORK` for that work unit — request the missing block and re-review when it arrives. Do NOT attempt to reconstruct it yourself.

For each subagent report that DID produce a block:

1. **Re-run every command in the block yourself**, fresh, from the orchestrator's shell — do not trust the pasted output. Specifically:
   - `git status --short`
   - `wc -l <file>` for every file the subagent listed
   - `grep -n '<symbol>' <file>` for every new symbol the subagent listed
   - The same test runner one-liner
2. **Diff your output against the subagent's pasted block.** Compare line by line.
3. **Any mismatch is a falsified report.** Mismatches include:
   - Off-by-one (or larger) LOC counts in `wc -l`
   - Missing grep matches (subagent claimed `grep -n` returned a hit; your fresh run returns nothing or a different line number)
   - Test counts that don't match (passed/failed/ignored differ from the subagent's paste)
   - `git status --short` entries that don't match (extra files, missing files, different status flags)
4. **"Already complete" sanity check.** If the subagent claimed any deliverable was "already complete before my work" or "done in a prior session," run:
   ```
   git log -1 --format='%H %cI %s' -- <file>
   ```
   for each file involved. If the most recent commit is from the current session (e.g., within the last hour, or after the session start timestamp), the "already complete" claim is almost certainly the subagent misreading its own diff. Treat the claim as falsified and the verdict as `NEEDS-REWORK`.

Record the gate outcome explicitly. One of:

- `Ground-truth verified: yes` — every command's fresh output matched the subagent's pasted block exactly, and no "already complete" claims survived the sanity check.
- `Ground-truth verified: no` — the subagent omitted the `GROUND-TRUTH OUTPUT` block or the block is incomplete.
- `Ground-truth verified: mismatch` — the block is present but at least one command's fresh output differs from the pasted output, OR an "already complete" claim was contradicted by `git log`.

**If the outcome is `no` or `mismatch`, the verdict for that work unit is `NEEDS-REWORK`** regardless of how good the prose review looks. Note the specific mismatches in the actionable items. Do not proceed to substantive review of that work unit until the subagent re-produces a verified block — but do continue to substantive review of OTHER work units in the batch whose blocks verified cleanly.

---

#### Step 2: Execute the Review

**Path A — Spawning a review subagent** (> 2 files OR > 150 lines):

Dispatch a single review agent using the **same model as the orchestrating session** (do NOT hardcode a model — inherit whatever model is running). The review agent's prompt must include the context and instructions defined below.

**Path B — Inline review** (≤ 2 files AND ≤ 150 lines):

Read the same context listed below and apply the same review instructions yourself. Produce the same structured output format.

---

**Context to provide (re-read from disk — do NOT rely on memory):**
- Relevant sections of `SPEC.md` for the features/requirements covered in this batch
- Relevant sections of `PHASES.md` — specifically the phase deliverables and acceptance criteria for this batch
- The plan's work unit definitions for each subagent in this batch (what each was supposed to implement)
- A complete list of all files modified by every subagent in this batch

**Review instructions:**

PRIMARY — Correctness (weight this heavily):
- Does the implementation align with the SPEC.md requirements? Flag any divergence, missing behavior, or misinterpretation.
- Does it satisfy the phase deliverables defined in PHASES.md?
- Does it match the intent of the plan's work unit definitions?
- Are there logic errors, broken contracts, or unhandled edge cases that would cause incorrect behavior?

TDD DISCIPLINE (for TDD work units):
- Were tests written against spec requirements, not shaped around the implementation?
- Do tests cover the deliverables' acceptance criteria?
- Are test assertions specific enough to catch regressions (not overly broad or tautological)?
- Did the implementation agent satisfy the test contract without modifying test files?

SECONDARY — Code quality:
- Performance: any obvious inefficiencies or scalability concerns?
- Patterns: consistent with the codebase conventions visible in the modified files?
- Readability: overly complex or unclear code that should be simplified?
- Potential issues: anything that could cause bugs under normal usage?

**Output format (REQUIRED — must appear in the review output):**

```
## Batch N Review Report

### Per-Work-Unit Findings

#### WU-[ID]: [name]
**Ground-truth verified:** [yes | no | mismatch]   ← from Step 1.5; mandatory line
**Satisfactory:** [what's correct]
**Issues:** [gaps, misalignments, bugs — with file:line references]

[repeat for each WU]

### Overall Batch Assessment

**Verdict:** [PASS | PASS-WITH-FIXES | NEEDS-REWORK]

> The batch verdict is **`NEEDS-REWORK`** if ANY work unit has `Ground-truth verified: no` or `Ground-truth verified: mismatch`. Prose quality cannot upgrade a falsified-report verdict.

### Actionable Items
- [specific description of what must be changed and why]
- [for ground-truth mismatches: cite the exact diff between subagent's pasted output and the orchestrator's fresh re-run]
```

After producing the report, **append a "Review Notes" section to `PHASES.md`** documenting all findings for the reviewed batch. Include the assessment verdict and date. Then return the full report to the orchestrating agent.

---

#### Step 2.5: Propagation Check (MANDATORY after review — before verdict)

Before issuing the verdict, check whether this batch introduced any of the following:

1. **Import indirection** — a new module that wraps/proxies an existing import (e.g., a Tauri invoke wrapper, a fetch wrapper, a logger facade)
2. **Struct/interface field additions** — a new field on a type that is constructed in multiple files (especially test files)
3. **Vitest/Jest alias changes** — new resolve aliases in test config
4. **Public API surface changes** — renamed exports, moved modules, changed function signatures on widely-imported utilities

If ANY of these are present, the review must additionally verify:
- All consumers of the original import/type are migrated to the new path
- Test mocks target the correct module boundary (not the underlying wrapped module)
- All struct constructors in test code accommodate new fields (via `..Default::default()` or equivalent)

**If the propagation check reveals unmigrated consumers or broken mock targets, the verdict MUST be `NEEDS-REWORK`** — even if the implementation logic itself is correct. Propagation failures create delayed blast-zone failures that surface only when the full test suite runs later.

---

#### Step 2.7: Mount-Site Verification (MANDATORY for new files)

!`cat ~/.claude/skills/_components/mount-site-verification.md`

---

#### Step 3: Act on the Review Verdict

**`PASS`** → Proceed to the next step in the plan.

**`PASS-WITH-FIXES`** (small/localized fixes — a few lines, a single function, a missing guard):
- Fix directly in the orchestrating session.
- Update `PHASES.md` to note the fixes applied.
- Proceed to the next step.

**`NEEDS-REWORK`** (or fixes are extensive/cross-cutting):
- Dispatch Sonnet subagent(s) with specific fix instructions from the review report's actionable items. Include file paths, the issue description, and the expected correct behavior.
- After fix subagents complete, **re-run this entire review protocol** on the fixed code.
- Do NOT proceed to the next batch until the re-review returns `PASS` or `PASS-WITH-FIXES` (with fixes applied).
