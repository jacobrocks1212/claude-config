## Spec-Buddy Check-in Format

The canonical shape for every partition check-in produced by the spec-buddy workflow. Fixed structure, confidence-scored, auditable. Consuming skills `!cat` this file directly — it is self-contained.

### Tiers

Every partition is tagged **important** or **minor** before analysis begins.

- **Important-tier:** use the full structure below.
- **Minor-tier:** condense to Recommendation + Confidence + one-sentence confirm. Omit Evidence, Pseudo-code, and Open questions unless something unexpected surfaces.

---

### Full Structure (important-tier)

**Partition:** `<name>` — `<one-line purpose>`

**Recommendation:** State the opinionated call directly. If confidence is high, commit to it ("add X here", "reuse Y", "this is a no-op"). If confidence is med or low, frame as a leaning, not a directive ("likely needs X, pending verification").

**Evidence:**
- `<file:line>` or `<SymbolName>` or `<PHASES.md §section>` — one cited fact per bullet
- Each bullet stands alone; no padding prose

**Confidence:** `high` / `med` / `low` — `<one-line reason>`
- `low` ⇒ propose a concrete investigation step, not a forced call. Name the file, symbol, or question that would resolve the uncertainty.

**Pseudo-code:** *(omit if the partition is purely structural or config-only)*
```
// concise sketch — not production code
// shows the shape of the change, not every detail
```

**Open questions:**
- Anything deferred that a later partition or a human must resolve
- Omit this field entirely if there are none

---

### Condensed Structure (minor-tier)

**Partition:** `<name>` — `<one-line purpose>`
**Recommendation:** `<call or leaning>`
**Confidence:** `<high/med/low>` — `<one-line reason>`

Add a single sentence of confirmation only if the partition's behavior is non-obvious. No Evidence block, no Pseudo-code, no Open questions unless something unexpected surfaces.

---

### Rules

- **Confidence drives the recommendation's posture.** High → commit. Med → lean. Low → investigate before deciding.
- **Every Evidence bullet is cited.** `file:line`, a named symbol, or a `PHASES.md` path. Uncited bullets are not evidence.
- **No fluff.** Each field is one line or a tight list. No introductory sentences ("This partition is responsible for…").
- **Pseudo-code is for code-shaped partitions only.** Skip it for configuration, schema-only, or purely structural changes.
- **Open questions are deferred, not blocked.** Name them and move on; resolution happens elsewhere.

---

### Example — Important-tier

**Partition:** `WorkflowActionFilter.Evaluate` — determine whether a workflow action is reachable given current entry state

**Recommendation:** Add a new `EvaluateTarget` path in `WorkflowActionFilter` that short-circuits when `action.IsTargetAction` is true; do not touch the existing `Evaluate` path.

**Evidence:**
- `Cognito/Workflow/WorkflowActionFilter.cs:42` — `Evaluate` currently returns `Viability.NotApplicable` for target actions without consulting entry state
- `Cognito.Core/Workflow/IWorkflowAction.cs:18` — `IsTargetAction` property already exists on the interface
- `PHASES.md §Phase 2 — Filter routing` — decision to keep existing path stable; new path required

**Confidence:** `high` — the interface contract is settled and the call site is isolated

**Pseudo-code:**
```
public bool? EvaluateTarget(IWorkflowAction action, IEntry entry)
{
    if (!action.IsTargetAction) return null; // not my concern
    return EvaluateConditions(action, entry);
}
```

**Open questions:**
- Should `EvaluateTarget` return `bool?` or a full `Viability` value? Depends on Phase 3 routing decision.

---

### Example — Minor-tier

**Partition:** `WorkflowActionFilterTests` helper update — add `IsTargetAction = true` to existing test-builder
**Recommendation:** Set `IsTargetAction = true` in the `BuildAction` helper; no new test class needed.
**Confidence:** `high` — helper is a simple POCO builder with no side effects
