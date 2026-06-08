### Cognito Forms Review Guardrails (bake review pitfalls into the plan)

When drafting each phase, embed a **Review Guardrails:** block that front-loads the review
pitfalls most likely to bite *that phase's files* — the same rule corpus the PR-review
pipeline flags after the fact. The goal is to avoid the comment, not field it later.

**Rule corpus (single source of truth — do NOT transcribe rules from memory):**
- Rules: `~/.claude/plugins/local-tools/plugins/cognito-pr-review/knowledge/rules/*.yaml`
- Weights: `~/.claude/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml`

This is the same YAML that `/cognito-pr-review:learn-from-pr` appends to, so every rule learned
from a past review flows into future plans automatically — there is no second place to maintain.

#### Selection (run per phase)

1. **Build the file set.** Start from the phase's **Files likely modified** list. For
   `/add-phase`, UNION in the **Files likely modified** of every phase this new phase supersedes
   (identified in Step 3c) — corrective phases recur on exactly the files the superseded work
   touched, so those pitfalls are the highest-signal ones to surface.

2. **Map file types to rule categories** via each YAML's `category` + `file_patterns`:
   - `*.cs` → `csharp-architecture`, `performance`, `security`, `code-consistency` (+ `testing` when `*Tests.cs`)
   - `*.vue` / `*.ts` / `*.tsx` → `frontend-vue`, `template-binding`, `code-consistency` (+ `testing` when `*.test.ts` / `*.spec.ts`)
   - Controllers / `*Controller.cs` also pull `api-design`.

3. **Apply the weight floor.** Effective weight = `rule_weights[id].weight` (default `0.7` if
   absent) × the rule's category multiplier from `weights.yaml#category_multipliers`:

   | rule `category` | multiplier key | value |
   |---|---|---|
   | csharp-architecture | architecture | 1.0 |
   | code-consistency | consistency | 0.8 |
   | frontend-vue | frontend | 1.0 |
   | template-binding | template_binding | 0.7 |
   | testing | testing | 0.9 |
   | security | security | 1.2 |
   | performance | performance | 0.9 |
   | api-design | api_design | 1.0 |

   **Drop anything with effective weight < 0.50** (matches the sweep "important tier" floor).
   Sort the survivors by effective weight, descending.

4. **Subagent semantic trim.** `trigger_patterns` are code-time, not plan-time, so they can't
   gate selection here. From the weight-passing set, keep only the rules genuinely relevant to
   **this phase's scope and deliverables** — judge each rule's `description` against what the
   phase will actually build. **Cap at the ~5 highest-signal rules per phase.** If no rule is
   relevant, omit the block for that phase (don't pad it).

#### Snapshot format (embed into the phase, immediately after **Testing Strategy:**)

Add this block to the phase — it is an additional field in the standard PHASES.md phase format,
present only on Cognito Forms phases:

```markdown
**Review Guardrails:** *(snapshot from review rules — get ahead of review on this phase's files)*
- **[<severity>, w≈<effective-weight>]** <plain-language one-liner of the rule>. *Do:* <correct_pattern gist>. *Don't:* <anti_pattern gist>.
- ...
```

- Use the rule's plain-language `description`; **never** embed jargon-only phrasing (see
  `code-consistency#comments-add-context-no-jargon`). Name the concept plainly.
- Gist the anti/correct patterns to one clause each — do **not** paste whole code blocks; the
  phase plan is a checklist, not a rulebook.
- Keep each entry to one or two lines. This is a snapshot taken at authoring time; it is allowed
  to be point-in-time, because PHASES.md is itself a point-in-time artifact for one work item.
