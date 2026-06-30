# Standardized Post-Disposition Issue Format (Proposed Fix + Proposed PR Comment) — Investigation/Design Spec

> After disposition, `review-pr-buddy` (and the shared `synthesizer-v2` agent) must present every kept issue in one standardized format that pairs each issue with a **proposed fix** and a **draft PR comment**, ordered most-important-first — so the reviewer knows how to actually resolve each issue.

**Status:** Concluded
**Severity:** P2 (workflow friction; no incorrect output)
**Discovered:** 2026-06-30
**Placement:** `docs/specs/review-pr-buddy-issue-format/` (harness feature work)
**Related:** `docs/specs/review-pr-buddy/SPEC.md` (the original buddy feature), `user/plugins/local-tools/plugins/cognito-pr-review/commands/review-pr-buddy.md`, `agents/synthesizer-v2.md`
**Phases:** [`PHASES.md`](./PHASES.md) — 2-phase decomposition (synthesizer-v2 format SSOT → buddy artifact + in-chat digest)

<!-- This is a feature enhancement with a fully-known design (no root-cause mystery to investigate),
     captured via /spec-bug. Status is Concluded: the four scoping decisions are locked (see
     "Resolved Decisions"), affected area is mapped, ready for /plan-bug → PHASES.md. -->

---

## Verified Symptoms

<!-- Confirmed directly with the user via AskUserQuestion on 2026-06-30 -->

1. **[VERIFIED]** After the reviewer provides dispositions, the buddy's issue digest leaves the reviewer **unclear on how to actually resolve** each issue — confirmed as the originating pain point.
2. **[VERIFIED]** The reviewer wants **every** issue (Blocking, Important, AND Suggestion/nit) accompanied by a **proposed fix** and a **proposed/draft PR comment** — not just the actionable ones. Dismissed findings stay excluded.
3. **[VERIFIED]** The standardized format must apply to **both** the in-chat digest surfaced at session close **and** the persisted curated review artifact (`PR-{id}.md`).
4. **[VERIFIED]** Most-important issues must still be presented first; the new fix/comment sections are added per-issue without disturbing the existing importance ordering.
5. **[VERIFIED]** The change should apply to **both** `review-pr-buddy` Phase 2 **and** the shared `synthesizer-v2` agent (so autonomous `/review-pr` output is consistent).

## Reproduction Steps

1. Run `/cognito-pr-review:review-pr-buddy <PR#>` and walk the chunks, dispositioning findings.
2. Reach Phase 2 (Human-Curated Synthesis). Buddy writes `PR-{id}.md` and reports counts/paths in chat.
3. Inspect a kept Important sweep/reuse/intrafile finding in the artifact.

**Expected:** Each kept issue appears in a uniform block carrying (a) the finding, (b) a concrete proposed fix, and (c) a ready-to-paste draft PR comment — both in chat and in `PR-{id}.md`, ordered by importance.
**Actual:** Findings are heterogeneous — investigation findings get full `File / Severity / Evidence / Suggestion` subsections; sweep/reuse/intrafile findings are terse one-line bullets (`- {title} [{file}:{line}] (weight: …)`). **No** finding carries a proposed fix or a draft PR comment. The in-chat close (`review-pr-buddy.md` "Cleanup and Report") reports only counts + paths — it does not render the findings at all.
**Consistency:** Always (structural — it is the current output contract, not an intermittent fault).

## Evidence Collected

### Source Code

- **`commands/review-pr-buddy.md`** (424 lines) — the buddy orchestration.
  - Phase 2 "Collect Curated Content" (≈ L296–309) maps severity → synthesizer-v2 sections; carries a finding's optional free-text `note` as "comment text." There is **no** proposed-fix or draft-PR-comment generation step.
  - "Review Document Format" (≈ L311–328) mandates the artifact follow **"the exact synthesizer-v2 output format defined in `agents/synthesizer-v2.md`"** — so any format change must be made in synthesizer-v2 and mirrored here (or vice versa). This is the coupling seam.
  - "Cleanup and Report" (≈ L384–400) is the **in-chat** session close: it reports artifact path, journey path, finding counts, REVIEWED.md status — it does **not** render an in-chat issue digest. Adding the in-chat standardized digest is net-new behavior here.
  - Buddy orchestrator has **local-codebase-on-`main` read access** (the investigation-style carve-out, ≈ L226) — so it *can* ground a concrete snippet from real code.
- **`agents/synthesizer-v2.md`** (193 lines) — shared synthesis format, used by autonomous `/review-pr`.
  - "Output Format" (≈ L70–151) defines the per-finding shapes: investigation findings get `**File:** / **Severity:** / **Evidence:** / **Suggestion:**`; sweep/reuse/intrafile get one-line bullets.
  - Findings JSON already carries a `suggestion` field and, for investigation findings, `evidence.snippet` + `evidence.reference` (≈ L33–52). The proposed-fix work *extends* `suggestion` into an actionable fix; the snippet is available from `evidence.snippet`.
  - **Cache-boundary constraint** (≈ L179–186): synthesizer-v2 **"Do NOT read from the local codebase."** It is cache-only. Therefore its "concrete snippet" must be sourced from the **already-cached** `evidence.snippet` in `processed-findings.json`, NOT a fresh local read. This is the key asymmetry vs. the buddy orchestrator.
  - "Ordering" (≈ L176–177): `processed_findings` is pre-sorted by tier→severity→weight; "Do not re-sort." The new per-issue sections must preserve this.

### Related Documentation

- **`cognito-pr-review/CLAUDE.md`** — confirms `review-pr-buddy.md` "delegates Phase 0 to `review-pr.md`; do NOT copy or duplicate its step bodies," and that buddy writes the review directly (does not invoke the synthesizer-v2 *agent*) but follows its *format*. So the format contract lives in `synthesizer-v2.md` and is consumed by buddy by reference.
- **`user/CLAUDE.local.md`** — **NEVER** use ADO MCP tools to reply to PR comments. ✅ The "proposed PR comment" is an explicit **draft for the reviewer to paste manually** — fully consistent with this constraint. The feature must not auto-post.

### Git History

- Current branch: `main`. No in-flight work on these files. The existing `docs/specs/review-pr-buddy/SPEC.md` (Status: Draft, 2026-06-08) is the originating feature spec; this enhancement post-dates it.

## Resolved Decisions

<!-- These were the open scoping questions; all four locked via AskUserQuestion on 2026-06-30.
     They are the design contract for /plan-bug. -->

| # | Decision | Resolution |
|---|----------|------------|
| D1 | **Severity scope** of the standardized block | **All kept findings** — Blocking, Important, AND Suggestion/nit. Dismissed remain excluded. Every non-dismissed finding gets the full block. |
| D2 | **Form of the proposed fix** | **Snippet where cheap, prose otherwise** — concrete before→after code snippet/diff when the fix is small/local and the code is in hand; precise prose resolution steps (what to change, where, why) when the fix is broad or spans files. |
| D3 | **Output surface** | **Both** — the persisted `PR-{id}.md` artifact AND a new in-chat digest rendered at buddy session close. One standardized format, two surfaces. |
| D4 | **Apply to** | **Buddy Phase 2 + the shared `synthesizer-v2` agent** — so autonomous `/review-pr` emits the same standardized blocks. The format is defined once in `synthesizer-v2.md` and consumed by buddy by reference (preserving the existing single-source-of-format coupling). |

## Proposed Standardized Issue Block (design target)

Each kept issue, regardless of source (investigation / sweep / reuse / intrafile / reviewer), renders in this uniform shape, ordered most-important-first (preserving the existing tier→severity→weight sort):

```markdown
### {Issue title}
**Severity:** {Blocking | Important | Suggestion}   **Source:** {investigation|sweep|reuse|intrafile|reviewer}   **Location:** {file}:{line}   **Confidence:** {CONFIRMED|UNVERIFIED|—}
**What:** {1–2 line statement of the issue and why it matters — drawn from evidence/hypothesis/description}
**Proposed fix:** {concrete before→after snippet/diff when cheap; precise prose resolution steps otherwise (D2)}
**Proposed PR comment:** {ready-to-paste draft comment text — reviewer posts manually (never auto-posted)}
```

Notes for planning:
- The block **supersedes** the current heterogeneous per-source shapes inside each existing section (Critical Findings, Rule-Based Findings, Reuse & Duplication, Intra-File Consistency). The section grouping and omission rules stay; only the per-finding rendering becomes uniform.
- If a kept finding carries a reviewer `note`, fold it into / seed the **Proposed PR comment** (the note is the reviewer's own intended comment text).
- **Proposed PR comment** should be terse and reviewer-voiced (it is what gets posted on the PR), distinct from **What** (the internal explanation).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Buddy Phase 2 synthesis | `commands/review-pr-buddy.md` ("Collect Curated Content", "Review Document Format") | Generate proposed-fix + draft-comment per kept finding; emit standardized block in `PR-{id}.md`. Buddy may use local-`main` access to ground snippets. |
| Buddy in-chat close | `commands/review-pr-buddy.md` ("Cleanup and Report") | NEW: render the standardized digest in chat (currently counts/paths only), most-important-first. |
| Shared synthesis format | `agents/synthesizer-v2.md` ("Output Format", "Narrative Guidelines", "Section Omission Rules", "Ordering") | Redefine per-finding rendering to the standardized block; source the concrete snippet from cached `evidence.snippet` only (cache-only constraint). |
| Findings data shape (verify, likely no change) | `scripts/post-process.ts`, `scripts/aggregate-findings.ts`, `processed-findings.json` schema | Confirm `suggestion` + `evidence.snippet`/`reference` carry enough to author a fix; for sweep/reuse/intrafile findings (no `evidence.snippet`), the fix is authored from `description`/`suggestion`/`candidate`/`suggested action` → likely prose-form (D2). Decide whether any new field is needed or fix/comment are generated at synthesis time. |
| Calibration join (regression guard) | `commands/review-pr-buddy.md` "Finding ID Convention", `scripts/disposition-calibration.ts` | The standardized block must NOT alter the canonical `<file>:<line>`/`<file>#<slug>` finding IDs that the calibration join depends on. New sections are additive only. |

## Theories

N/A — root cause is known and trivial: the current output contract has no proposed-fix/draft-comment fields and a heterogeneous per-source rendering. This is a feature gap, not a defect with an unknown cause. No hypotheses to confirm or rule out.

## Open Questions

- **Snippet grounding for buddy vs. synthesizer-v2:** buddy can read local `main` to produce a concrete snippet; synthesizer-v2 is cache-only and must rely on `evidence.snippet`. Confirm during planning whether the two surfaces should produce *identical* blocks (then buddy is constrained to cache-only too, for parity) or whether buddy is allowed richer snippets than the autonomous path. (Leaning: keep the *format* identical; allow buddy's snippet to be richer since it has the access — document the asymmetry.)
- **Sweep/reuse/intrafile fix authoring:** these findings lack `evidence.snippet`; their "Proposed fix" will usually be prose (D2) built from `description` + `candidate` + `suggested action`. Confirm that is sufficient, or whether the agents should emit a richer `suggestion`/`fix` field upstream.
- **Draft-comment length/tone guidance:** define a short style rule (terse, reviewer-voiced, references `file:line`) so generated comments are paste-ready and consistent.
- **Re-review (`## Re-Review Status`) interaction:** confirm the standardized block coexists cleanly with lifespan annotations on re-reviews.
