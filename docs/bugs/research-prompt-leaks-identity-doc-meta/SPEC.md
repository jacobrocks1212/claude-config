# Research prompt leaks identity-doc meta into the `## Project context` prepend — Investigation Spec

> `/spec` Phase 2 pastes the identity summary doc *verbatim* into the Gemini research prompt, carrying the doc's own self-describing preamble (artifact-naming H1 + maintainer provenance blockquotes) instead of only the actual product identity.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-25
**Placement:** docs/bugs/research-prompt-leaks-identity-doc-meta
**Related:** `user/skills/spec/SKILL.md` Phase 2 (identity-prepend resolution, steps 2 & 4); `user/skills/ingest-research/SKILL.md` (downstream consumer of `RESEARCH_PROMPT.md`)

<!-- Status lifecycle: Investigating → Concluded (root cause proven, fix scope understood; ready for /plan-bug). -->

---

## Verified Symptoms

1. **[VERIFIED]** The generated Gemini research prompt's `## Project context` block leads with **meta about the identity document itself** rather than product identity — confirmed via the user's screenshot of an AlgoBooth `RESEARCH_PROMPT.md` and confirmed interactively (AskUserQuestion, 2026-06-25). The leaked meta:
   - `# AlgoBooth — Identity Summary (Gemini Prepend)` — an H1 that **self-labels the file as the prepend artifact**.
   - `> Pre-sized, ready-to-go product context for LLM…` — maintainer note.
   - `> This is the **budget-friendly** condensation o…` — maintainer note.
   - `> When the full identity doc changes materially…` — regeneration-policy note.

   The substantive identity (`## What AlgoBooth is …`) only begins *after* this preamble.

2. **[VERIFIED]** Expected behavior: the prepend should contain **only the actual product identity** — the meta header and provenance blockquotes must be stripped (confirmed interactively).

## Reproduction Steps

1. In a repo whose `docs/product/PRODUCT_IDENTITY_SUMMARY.md` begins with a self-referential title + maintainer blockquotes (AlgoBooth's does), run `/spec` for any feature.
2. `/spec` Phase 2 step 2 resolves the prepend from `PRODUCT_IDENTITY_SUMMARY.md` and uses it **verbatim** (fast path).
3. Step 4 writes `RESEARCH_PROMPT.md` with that verbatim content under `## Project context`.
4. Open the resulting `RESEARCH_PROMPT.md`.

**Expected:** `## Project context` contains only product-identity substance.
**Actual:** `## Project context` leads with the identity doc's own title (`… Identity Summary (Gemini Prepend)`) and three maintainer/provenance blockquotes before any identity content.
**Consistency:** Always — deterministic for any identity doc carrying a self-describing preamble.

## Evidence Collected

### Source Code

`user/skills/spec/SKILL.md`, Phase 2 ("Research Prompt Generation"):

- **Step 2 (line 386–394):** resolves the prepend in priority order. Case 1 — `docs/product/PRODUCT_IDENTITY_SUMMARY.md`: *"If it exists, read it and use it verbatim. This is the fast path: no condensing, no token burn."* Closing line 394: *"Whichever file is used, treat its contents as the identity prepend below."* No filtering of the doc's content.
- **Step 4 (line 413–433):** writes the file as `## Project context` + `<verbatim contents of the identity prepend>` + `---` + prompt body. Line 433 explicitly whitelists the whole block: *"The `## Project context` identity prepend and the structured prompt sections (below) ARE legitimate prompt content and stay."*
- **The asymmetry:** Step 4's "No meta-fluff in the prompt body (HARD)" rule (line 429–431) bans operator/tool metadata and ship-as-a-unit framing — but **applies only to the prompt body**, and line 433 explicitly exempts the identity prepend. So the same class of meta-fluff the skill is careful to keep out of the body rides in unchallenged through the prepend.

### Runtime Evidence

User screenshot (uploaded 2026-06-25): an AlgoBooth `RESEARCH_PROMPT.md` rendered on mobile, showing the `## Project context` → `# AlgoBooth — Identity Summary (Gemini Prepend)` → three provenance blockquotes → `## What AlgoBooth is` ordering described above.

### Git History

No recent change to Phase 2's prepend handling implicated; this is a latent gap in the verbatim fast path, not a regression.

### Related Documentation

- `user/skills/ingest-research/SKILL.md` — downstream; correlates Gemini results back to features via the prompt. Not a cause, but it reads `RESEARCH_PROMPT.md`, so a cleaner prompt helps correlation signal.
- AlgoBooth `docs/product/PRODUCT_IDENTITY_SUMMARY.md` — the polluting source doc. **Not cloned on this machine**, so it cannot be edited from this repo.

## Theories

### Theory 1: Verbatim fast path carries the doc's self-describing preamble
- **Hypothesis:** Because step 2's fast path uses `PRODUCT_IDENTITY_SUMMARY.md` verbatim and step 4 whitelists the entire prepend, any self-referential preamble in the doc (artifact-naming H1 + maintainer blockquotes) is pasted straight into the prompt.
- **Supporting evidence:** Screenshot shows exactly that ordering; skill prose says "use it verbatim" and "ARE legitimate prompt content and stay."
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

- **Root cause:** `/spec` Phase 2 treats the *entire* contents of the resolved identity doc as prompt-worthy and pastes it verbatim. A doc's own self-describing preamble — an H1 that labels it as an identity-summary / Gemini-prepend artifact, plus the immediately-following maintainer/provenance blockquotes (pre-sized / budget-friendly / regenerate-when-the-full-doc-changes) — is **meta about the artifact, not product identity**, and pollutes every generated research prompt.
- **Decided fix (interactive, 2026-06-25):**
  - **Seam — harness-side strip in `/spec`** (the only seam editable in this repo; also the durable one — it covers every repo and survives the step-2 self-heal path that *auto-generates* `PRODUCT_IDENTITY_SUMMARY.md`, which could otherwise re-introduce a title/notes). The AlgoBooth source doc is a secondary cleanup, out of scope here (not cloned).
  - **Strip boundary — self-label H1 + provenance blockquotes.** When composing the prepend, strip a leading H1 that self-labels the artifact (matches identity-summary / Gemini-prepend / prepend self-reference) **and** the immediately-following maintainer blockquote run (provenance/regeneration notes). Keep everything from the first substantive section (e.g. `## What AlgoBooth is`) onward. Do not strip substantive content; the strip is bounded to the leading self-describing preamble only.
- **Where the fix lands:** `user/skills/spec/SKILL.md` Phase 2 — add a preamble-strip sub-step to step 2 (applied to whichever doc is resolved, before it becomes "the identity prepend"), and amend step 4's line-433 whitelist so it no longer blanket-exempts the prepend's self-describing meta. Be lenient/heuristic about phrasing (the skill's house style for content matching), bounded to the leading preamble.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| `/spec` Phase 2 identity prepend | `user/skills/spec/SKILL.md` (steps 2 & 4, ~L386–433) | Every `RESEARCH_PROMPT.md` whose identity doc carries a self-describing preamble leaks meta into the Gemini paste |
| AlgoBooth source doc (secondary, out of scope) | `docs/product/PRODUCT_IDENTITY_SUMMARY.md` (AlgoBooth repo — not cloned here) | Tidy-at-rest cleanup; harness strip makes it non-blocking |

## Open Questions

- Should the strip also apply to the full-doc path (step 2 case 2, `PRODUCT_IDENTITY.md`) and the self-heal condensation output, or only the summary fast path? (Recommended: apply uniformly in step 2 after resolution, since all three converge on "the identity prepend" — the fix lands at the convergence point.) To be settled in `/plan-bug`.
