# `GEMINI_PROMPT_CHAR_CAP = 24,000` Sits ABOVE Gemini's True 20,000-Char Hard Truncation — Investigation Spec

> The research-prompt pipeline sizes `RESEARCH_PROMPT.md` against
> `GEMINI_PROMPT_CHAR_CAP = 24,000`, on the assumption that Gemini's Deep Research prompt
> textarea has a ~30,000-char practical limit with ~6,000 chars of headroom. **That assumption
> is wrong.** Gemini's prompt-input field SILENTLY HARD-TRUNCATES at exactly **20,000
> characters** — everything past char 20,000 is dropped with no warning, and the paste simply
> ends mid-content. Because the cap (24,000) sits ABOVE the true hard limit (20,000), every
> prompt sized "under cap" that lands in the 20,000–24,000 band is silently truncated, AND the
> `{within | over}` indicator reports "within" for a prompt that will in fact be cut. The
> operator has no signal that the most load-bearing tail of the prompt was severed.

**Status:** Concluded
**Severity:** P2 (correctness/silent-data-loss — research prompts in the 20,000–24,000-char band
are silently truncated at paste time with a falsely-reassuring "within" indicator. Not
destructive to on-disk state — the `RESEARCH_PROMPT.md` file is written whole — but the operator
pastes a prompt they believe is complete and Gemini receives a truncated one, corrupting the
research output at the top of the pipeline. Detected only by an operator happening to notice the
paste ended mid-sentence.)
**Discovered:** 2026-07-17
**Placement:** docs/bugs/gemini-prompt-char-cap-above-hard-truncation-limit
**Related:**
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — this investigation is the
  Step-2.5 audit-trail artifact for the corresponding hardening round.
- `user/skills/spec/SKILL.md` Phase 2 — the canonical `GEMINI_PROMPT_CHAR_CAP` definition +
  cap-source rationale comment.

## Reconstructed route (harden-harness Step 1)

- **Trigger kind:** manual (`/harden-harness <description>`) — operator-observed friction from a
  real research-prompt paste; no probe/registry/marker state (not a validate-deny / no-route).
- **Divergence point:** `/spec` Phase 2 step 3/5 (prompt compose + length check) and the
  `/lazy-batch` research-halt announcement (`{within | over}` indicator). The pipeline sizes and
  labels the prompt against a 24,000-char cap; the paste field truncates at 20,000. The intended
  behavior — "never hand the operator a prompt that will be cut" — diverges because the encoded
  limit is above the real one.
- **Empirical measurement (this session):** a **21,275-character** `RESEARCH_PROMPT.md` pasted
  into the Gemini Deep Research prompt field was hard-truncated at **exactly character 20,000**.
  The cut fell mid-word inside Question 10 and severed the ENTIRE "Output Format Request" section
  (the most load-bearing part of the prompt — it tells Gemini how to structure its answer). The
  operator discovered the loss only by noticing the paste ended mid-sentence. 20,000 is a clean
  round number, consistent with a fixed textarea `maxlength`.

## Root cause (harden-harness Step 2)

**Classification: `script-defect` (a wrong constant + its rationale, spanning skill prose /
components — no executable script owns the value, so it is prose-constant debt).**

The constant `GEMINI_PROMPT_CHAR_CAP = 24,000` was chosen on a mistaken model of the field's
behavior: the cap-source comment (`user/skills/spec/SKILL.md:440-443`) reasons from a
"~30,000-char practical limit per Google support docs" and sets 24,000 to leave "~6,000 chars of
headroom." The real behavior is a hard silent truncation at 20,000 — so:

1. The cap (24,000) is ABOVE the truncation point (20,000), inverting the safety discipline. The
   old design deliberately targeted BELOW the assumed real limit; the number encoded no longer
   does that relative to the actual limit.
2. The `{within | over}` indicator (`lazy-batch/SKILL.md:1433`,
   `_components/lazy-batch-prompts/research-halt-announcement.md`) compares to 24,000, so a
   20,000–24,000-char prompt is reported "within" while it will actually be truncated.

## Fix scope

Mechanical (prose-constant, everywhere referenced). Set the cap BELOW the empirically-confirmed
20,000 hard truncation, preserving the original discipline (cap sits below the real limit with
headroom): **`GEMINI_PROMPT_CHAR_CAP = 18,000`** (~2,000 chars headroom below 20,000). Update the
`{within | over}` comparison threshold to 18,000 and rewrite all human-readable "24,000-char"
mentions + the headroom rationale to state the measured 20,000 hard limit and cite the
measurement. Occurrences:

- `user/skills/spec/SKILL.md` — constant (~L438), cap-source rationale comment (~L440-443),
  body-budget note (~L445), length-check (~L491), reporting line (~L498).
- `user/skills/spec-buddy/SKILL.md` — constant (~L255), length-check (~L273).
- `docs/specs/spec-buddy/PHASES.md` — minimal-replication seam note (~L111, keeps the
  "keep in step" constraint truthful).
- `user/skills/lazy-batch/SKILL.md` — `{within | over}` comparison threshold (~L1433).
- `user/skills/_components/lazy-batch-prompts/research-halt-announcement.md` — comparison note
  (~L17-18) and both `[length: …]` template lines (~L93, ~L152).
- `user/scripts/coupled-overlays/lazy-batch-cloud.overlay.json` (verbatim divergence lines) +
  regenerate `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` via
  `generate-coupled-skills.py --write`.

Deliberately OUT of scope: `user/scripts/test_project_skills.py::_CYCLE_PROMPT_SIZE_CEILING =
24000` — an unrelated ceiling on assembled *cycle* prompts (dispatch-prompt size guard), not the
Gemini paste cap. `IDENTITY_PREPEND_CHAR_BUDGET = 6,000` is unchanged (independent of the cap);
only the derived "leaves N for body" arithmetic updates (6,000 prepend under an 18,000 cap →
12K+ body).

`lazy-bug-batch/SKILL.md` carries no 24,000 reference (verified) — no coupled-twin edit needed
there.
