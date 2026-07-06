## Root-Cause Trace Gate (SEAM A — front gate, HARD BLOCK)

**Why this component exists.** A bug's `"observed symptom X is produced by value/code Y"`
finding is only trustworthy when the symptom's *serving path* has been traced surface→source in
code (or backed by cited runtime evidence for runtime-coupled claims) and the proposed fix site
lies **on** that path. The failure this prevents: a fix aimed at a *hypothesized* cause,
recorded as settled fact without ever reading the code that actually produces the symptom, then
certified "done" on tests asserting the fix's *internal target* — while the symptom persists
because the assumed value was never on its path. (Subject incident: bug 57585 — a fix suppressed
a composite facet on the premise "the linked-person pill is driven by that facet," but the pill
is served by a live person-field resolve that never reads the facet; the fix could not remove the
pill.)

This gate is **docs-only** — it reads the bug SPEC, greps/reads the serving code, and refuses a
status flip. It runs no build, no MCP server, no shell beyond ordinary code inspection. It is the
**front** half of the two-seam contract; `symptom-reproduction-gate.md` is the **back** half.

### Generalization guard (state this — it is NOT overfit to chips/facets/avatars)

The gate keys on the **generic symptom↔source relationship**, not any UI/domain vocabulary. It is:

- **Surface-neutral** — the observed symptom may appear on a UI component, an API response field,
  a CLI output line, a log entry, or a persisted table row.
- **Language-neutral** — the "serving path" is whatever chain of code produces that surface,
  regardless of stack.

It catches a whole class of siblings, not one incident: fixing the *write* path when the *read*
path is broken; fixing a cache when the symptom is served fresh; editing a config the feature
never consumes; suppressing a value the symptom never reads; treating a *correlated* value as the
*causal* one.

### Scope (when this gate runs)

Whenever a bug SPEC records a causal finding of the shape *"observed symptom X is produced by
value/code Y"* — **before**:

- the SPEC may flip `Investigating → Concluded` (`/spec-bug` Step 6), and
- that finding may be turned into fix scope (`/plan-bug` Step 0.4 findings gate).

### Required artifact — the symptom serving-path trace

For **each `[VERIFIED]` symptom** whose cause the SPEC intends to lock, record the chain from the
**user-facing surface the symptom appears on** back to the **data source that produces it**, each
hop cited `file:line`:

```
surface (UI component / API field / log line / table row)
  → <intermediate hop>   file.ext:NN
  → <intermediate hop>   file.ext:NN
  → data source Y        file.ext:NN     ← the value/code the fix will change
```

Rules for the trace:

1. **It must be produced by reading/greping the actual serving code**, not inferred. *"There is
   no other read-model, so it must be Y"* is an **inference, not a trace** — explicitly forbidden
   as sufficient. The chain must show the code that actually reads Y on the way to producing the
   surface.
2. **Fix-site-on-path rule.** The proposed fix must change a node **on the traced path** — the
   value/code being changed must be *read* on the symptom's path, not merely *related* to it. If
   the fix targets a value, the trace must show that value is *consumed* on the symptom's serving
   path. A fix site that exists but is not on the traced path does not satisfy the gate.

### `symptom-verified` ≠ `cause-traced` (the labeling rule)

A reproduced/verified symptom does **not** imply a verified cause. Every causal finding carries
an explicit label:

- **`traced`** — serving-path chain cited (each hop `file:line`) **and** fix-site-on-path shown.
- **`asserted`** — a hypothesis without a cited trace (or whose fix site is not on the path).

A `[VERIFIED]` symptom may **never** be used to upgrade an `asserted` cause to fact. (This is the
exact 57585 mislabel: a verified symptom was laundered onto an untraced cause.)

### Runtime-coupled claims

A **runtime-coupled** causal claim (behavior that only manifests at runtime — timing, ordering,
cache population, environment-dependent resolution) is **never** confirmed by reading source
alone. It requires cited runtime/observed evidence, per the `/investigate` four-attempt-trap and
`systematic-debugging`'s root-cause discipline. **Require their artifact — do not re-teach the
method here.** A runtime-coupled claim with only a static code read stays `asserted`.

### HARD BLOCK

An `asserted` (untraced) causal link may **not** conclude a SPEC or be planned.

- **Interactive** → refuse, naming the specific untraced symptom→cause link and the missing
  serving-path hops. Do not flip the SPEC status; do not proceed to planning.
- **`--batch`** → write `{spec_path}/NEEDS_INPUT.md` per `~/.claude/skills/_components/sentinel-frontmatter.md`
  (`written_by: root-cause-trace-gate`, `next_skill:` the consuming skill), with one decision
  naming the untraced symptom→cause link and the missing serving-path hops, plus the rich
  `## Decision Context` body. STOP; the orchestrator surfaces the halt on its next cycle.

### Coupling note

Injected as a front gate by:

- `user/skills/spec-bug/SKILL.md` — Step 6, gating the `Investigating → Concluded` status flip.
- `user/skills/plan-bug/SKILL.md` — Step 0.4 findings gate, before a finding becomes fix scope.

When editing this component, run `grep -rl "root-cause-trace-gate.md" ~/.claude/skills/ --include="*.md"`
to confirm the blast radius matches those two files. This gate does NOT teach root-cause tracing
(that is `systematic-debugging` + `investigate`); it requires their *artifact* as a lockable gate.
