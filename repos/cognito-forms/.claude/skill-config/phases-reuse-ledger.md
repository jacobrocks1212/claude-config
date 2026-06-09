### Phase-Level Reuse (Cognito Forms)

The SPEC carries a `## Reuse Ledger` (produced by `/spec`'s reuse-first discovery). The phase plan must
**honor and extend it** — phases build on existing systems, they do not silently re-create them. If the
SPEC has no Reuse Ledger (older spec, or one authored before this gate existed), run an abbreviated
reuse pass over the phases' candidate files before drafting, and note the gap in
`## Cross-feature Integration Notes`.

When analyzing phase boundaries (Step 2) and drafting each phase:

- **Cite the ledger.** Each phase that touches a capability in the ledger carries a **Reuse:** field
  naming the existing code it extends / refactors / wraps (`file:line` + the governing domain skill),
  and references the ledger row it consumes.
- **Refactor phases name their blast radius.** A phase whose verdict is *refactor* must list the existing
  callers of the changed code (tree-sitter `get_callers`) in **Files likely modified**, so the phase
  scope is honest about ripple.
- **Parallel-system red flag.** A phase that introduces a new service / type / component doing what an
  existing ledger candidate already does is a design defect — reconcile it against the ledger (extend the
  existing thing) before authoring the phase, or, if genuinely justified, record why in the phase and flag
  it for the user. New code that bypasses an existing system is the single most expensive thing to unwind
  in this codebase.
- **build-new phases inherit the trail.** If a phase is genuinely greenfield, reference the ledger's
  recorded negative-search trail for that capability so the reviewer can see the reuse question was
  already answered, not skipped.

Add **Reuse:** as a field in each phase of the PHASES.md output, immediately after **Files likely
modified:**

```markdown
**Reuse:** extends `Cognito/Foo/BarService.cs` (`BarService.Compute`) — see SPEC Reuse Ledger row "X".
Governed by the `forms-service` skill.
```

(If a phase touches no ledger capability — pure wiring or test scaffolding — omit the field.)
