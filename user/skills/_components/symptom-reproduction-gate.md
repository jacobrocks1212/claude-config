## Symptom-Reproduction Gate (SEAM B — back gate, completion evidence)

**Why this component exists.** "Fixed" requires reproducing the **original** symptom and
confirming it is gone at its reported surface. A green unit test on the fix's *internal target*
(a stored value, a facet, a private helper) is **not** sufficient — it certifies the proxy, not
the symptom. The failure this prevents: green-tests-on-proxy while the symptom persists; a fix
that compiles but whose wired path never executes; a regression test that pins the internal value
instead of the observable; any "unit-green = done" completion in a repo with no MCP surface.
(Subject incident: bug 57585 shipped on `build clean, 97/97 green` with zero observation of the
pill it was meant to remove; the symptom survived deploy.)

This gate is **docs-only** — it verifies that the required evidence exists, and refuses the
`Fixed` flip otherwise. It is the **back** half of the two-seam contract; `root-cause-trace-gate.md`
is the **front** half. This gate consumes the serving-path trace that front gate produced.

### Generalization guard (surface-agnostic)

The "serving path" is defined relative to whatever surface the symptom was reported on —
backend, frontend, CLI, or service. This gate is not tied to any UI/domain vocabulary; it
requires evidence that the *reported observable* is gone, however that observable is surfaced.

### Evidence ladder (strongest-first; the gate is satisfied by ≥ the REQUIRED rung)

1. **REQUIRED rung — serving-path regression test.** A red→green regression test that exercises
   the symptom's **actual serving path** (the path traced by `root-cause-trace-gate.md`), verified
   **RED before the fix / GREEN after**. A test that asserts on the fix's *internal target* does
   **NOT** satisfy this gate when that target is not itself on the symptom's serving path.
   - *Concrete (57585):* a qualifying test exercises `GetLinkedPersonAsync` / the `linked-person`
     endpoint (the pill's real serving path) — **not** `CompositeEntryIndex.SubmitterPersonEntryId`
     (the fix's internal facet).
2. **STRONGER (accepted, not required) — runtime/manual artifact.** A manual-testing doc
   (`/write-manual-testing-doc`) or a Selenium `local-ui-test` run observing the original symptom
   gone at the user surface. Accepted as a superset of rung 1; never demanded in addition to it.

### Repro-recipe binding

The test/artifact MUST map to the SPEC's `## Reproduction Steps` (the concrete repro recipe
captured at `/spec-bug` time). If the SPEC has **no concrete repro recipe** (only free prose),
that is itself a block — there is nothing to bind the reproduction evidence to.

### Honesty ladder (mirror `_components/mcp/mcp-integration-test.md`)

- "code changed + unit tests green on the internal target" → **NOT verified**; at most **50%
  PLAUSIBLE**.
- Only a serving-path regression test (rung 1) or a runtime/manual artifact (rung 2) reaches
  **VERIFIED**.
- **"Tests green" and "symptom resolved" are distinct claims.** Never let the first stand in for
  the second.

### No `SKIP_MCP_TEST.md` bypass for bugs

In a repo with no MCP surface, `SKIP_MCP_TEST.md` may satisfy the **MCP validation-sentinel**
check — but it MUST NOT be read as satisfying **symptom reproduction**. The serving-path
regression test lives in ordinary unit-test land and needs no MCP; it is still required. A bug
may not flip `Fixed` on a `SKIP_MCP_TEST.md` alone.

### Consumers

Injected as a completion / verification gate by:

- `user/skills/_components/completion-integrity-gate.md` — the `__mark_fixed__` (bug) path.
- `user/skills/fix/SKILL.md` — the Integration Verification step.
- `user/skills/_components/integration-verification.md` — the bug-fix clause.
- `user/skills/verification-before-completion/SKILL.md` — the sharpened "Bug fixed" row.
- `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` — Part-Completion (this repo
  declares "No MCP integration test step").

When editing this component, run `grep -rl "symptom-reproduction-gate.md" ~/.claude/ --include="*.md"`
to confirm the blast radius. This gate does not re-teach TDD or full-stack smoke testing — it
requires the *serving-path* evidence as the bug-completion bar, composing with (not duplicating)
those existing rules.
