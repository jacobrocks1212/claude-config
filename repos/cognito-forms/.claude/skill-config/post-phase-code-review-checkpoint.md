After each committed batch, emit a concise Why → How checkpoint to chat and then continue immediately.

**Skip entirely under `--batch`.** When `/execute-plan` is driven by `--batch` (i.e. a `/lazy-batch` autonomous run), there is no chat audience — do NOT emit anything and proceed directly to the next batch.

**When to fire:** once per batch, after the atomic gate+commit for that batch lands (Step 3 item 8) and before starting the next batch. Do not fire mid-batch or before the commit.

**Content:** 2–5 sentences of Why → How prose. State the batch's **purpose** (the Why), drawn from the intent in the surrounding PHASES.md and SPEC.md context plus the work-unit scope. Then map each part of that purpose to the concrete `file:symbol` locations that fulfill it (the How). **Reuse the material from the Batch Review Gate you just completed** — do not re-analyze the diff from scratch; you already have the synthesis, use it.

**Non-blocking:** emit the checkpoint, then proceed. You **MUST NOT call `AskUserQuestion`**, **MUST NOT pause for user input**, and **MUST NOT wait** before moving on to the next batch. The checkpoint is informational only. If the user wants to steer, they will interrupt the run themselves.

**No artifacts:** the checkpoint is chat output only. It writes no files and does not alter PHASES.md, the plan, any commits, or any other tracked artifact.

Rendered format:

```
📋 Batch 2 checkpoint — Why → How

Purpose: persist the resolved customer entry id onto the order projection so
deferred auto-created person entries backfill correctly (PHASES.md Phase 3, WU-2).

- Resolution of the id is done in `EntryIndexService.ResolveCustomerEntryIdAsync`
  (Cognito.Core/Services/Forms/EntryIndexService.cs).
- Backfill onto the projection is wired in `OrderProjectionBuilder.Apply`
  (Cognito/.../OrderProjectionBuilder.cs).

Continuing to Batch 3.
```

Header: `📋 Batch N checkpoint — Why → How`. Body: a `Purpose:` line, then bulleted `file:symbol` anchors. Closing: `Continuing to Batch N+1.`
