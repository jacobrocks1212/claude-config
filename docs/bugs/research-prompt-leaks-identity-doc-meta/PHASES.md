# Implementation Phases — Research prompt leaks identity-doc meta into the `## Project context` prepend

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — docs/prose harness edit to a single `SKILL.md` (`/spec` Phase 2 steps 2 & 4); no app surface, no Tauri/MCP-reachable behavior. The only validation surface is the rendered prompt text the skill prose produces, verifiable by reading the amended skill prose against the strip contract.

## Cross-feature Integration Notes

(No hard deps on Complete upstreams.)

## Notes on Scope

- **Strip-scope decision (Open Question in SPEC, settled here per D7):** the SPEC's `## Open Questions` asks whether the preamble strip applies only to the summary fast path (step 2 case 1) or uniformly across all three resolution branches (case 1 verbatim summary, case 2 full-doc verbatim, and the case-2 self-heal condensation output). **Settled: apply uniformly at the step-2 convergence point** — all three branches converge on "treat its contents as the identity prepend below" (line 394), so a single strip applied at that convergence line covers every branch and survives the self-heal path that auto-generates `PRODUCT_IDENTITY_SUMMARY.md` (which could otherwise re-introduce a self-labelling title). This is the SPEC's own recommendation; the options differ only in completeness/coverage, not in user-visible product behavior, so it is scope-class — taken in-cycle.
  - ⚖ policy: strip-scope (uniform vs summary-only) → uniform at step-2 convergence point
- **Out of scope (per SPEC):** the AlgoBooth `docs/product/PRODUCT_IDENTITY_SUMMARY.md` source-doc tidy-up. That repo is not cloned here and the harness-side strip makes the at-rest pollution non-blocking. Recorded in the SPEC's Affected Area as secondary.

### Phase 1: Strip the identity doc's self-describing preamble in `/spec` Phase 2

**Scope:** Amend `user/skills/spec/SKILL.md` Phase 2 so the resolved identity prepend has its leading self-describing preamble (a self-labelling H1 + the immediately-following maintainer/provenance blockquote run) stripped before it becomes the `## Project context` prepend, and so step 4's whitelist no longer blanket-exempts that meta. Single file, two coupled edits at the convergence point and the whitelist line.

**Deliverables:**
- [ ] Add a **preamble-strip sub-step** to `user/skills/spec/SKILL.md` Phase 2 step 2, applied at the convergence line ("Whichever file is used, treat its contents as the identity prepend below", ~L394) so it covers all three resolution branches (verbatim summary, verbatim full doc, self-heal condensation). The strip removes, from the TOP of the resolved content only: (a) a leading H1 (`# …`) that self-labels the artifact — heuristic/lenient phrase match on identity-summary / Gemini-prepend / prepend self-reference (house-style content matching, not a brittle exact-string match); and (b) the **immediately-following contiguous run of blockquote lines** (`> …`, provenance/regeneration/maintainer notes such as "pre-sized", "budget-friendly", "regenerate when the full doc changes"). Strip stops at the first non-blockquote, non-blank line — i.e. the first substantive section (e.g. `## What AlgoBooth is`) onward is preserved verbatim. Bounded to the leading preamble; never strip substantive content.
- [ ] Amend step 4's line-433 whitelist (`The `## Project context` identity prepend … ARE legitimate prompt content and stay.`) so it no longer blanket-exempts the prepend's self-describing meta — state that the prepend's SUBSTANTIVE identity content is legitimate, but the artifact's self-describing preamble (self-label H1 + provenance blockquotes) is the same class of meta-fluff the body rule already bans and is stripped in step 2. Keep the existing step-4 "No meta-fluff in the prompt body (HARD)" rule intact; this edit closes the asymmetry the SPEC's Evidence calls out.
- [ ] Tests: re-project + lint the edited skill (`python ~/.claude/scripts/project-skills.py` then `python ~/.claude/scripts/lint-skills.py`) — confirm no broken `!cat` injections / embedded-pattern regressions introduced by the prose edits. (No unit-test harness exists for skill prose; the lint + projection is the mechanical verification surface.)

**Minimum Verifiable Behavior:** Reading the amended `user/skills/spec/SKILL.md` Phase 2, step 2 contains an explicit preamble-strip sub-step at the convergence line and step 4's whitelist no longer blanket-exempts the self-describing preamble — verifiable by grepping the file for the strip sub-step text and confirming the amended whitelist wording. `python ~/.claude/scripts/lint-skills.py` exits clean over the edited skill.

**Runtime Verification** *(checked by manual testing):*
- [ ] Trace-through: against the SPEC's documented AlgoBooth example (H1 `# AlgoBooth — Identity Summary (Gemini Prepend)` + three provenance blockquotes + `## What AlgoBooth is …`), the strip contract as written removes the H1 and the three blockquotes and keeps everything from `## What AlgoBooth is` onward — confirm the prose unambiguously yields that result.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/skills/spec/SKILL.md` — Phase 2 step 2 (add preamble-strip sub-step at the convergence line ~L394) and step 4 (amend the ~L433 whitelist so it no longer exempts the self-describing preamble).

**Testing Strategy:**
Mechanical: re-project (`project-skills.py`) and lint (`lint-skills.py`) the edited skill — these catch broken injections, embedded anti-patterns, and capability drift introduced by the prose change. Semantic: a trace-through of the strip contract against the SPEC's documented AlgoBooth preamble example, confirming the rule keeps substantive identity and strips only the leading self-describing meta. There is no executable test harness for skill prose, so the lint pass + the documented trace-through ARE the verification surface for a docs-class harness fix.

**Integration Notes for Next Phase:**
- Single-phase fix — no next phase. The strip is bounded to the LEADING preamble (first H1 + immediately-following blockquote run); be explicit in the prose that it must NOT scan deeper into the doc, so a legitimate later blockquote inside substantive identity content is never collateral-stripped.
- The strip lands at the step-2 convergence line so the case-2 self-heal path (which writes `PRODUCT_IDENTITY_SUMMARY.md` and could re-introduce a title) is also covered — keep the strip downstream of resolution, not inside any single branch.

---
