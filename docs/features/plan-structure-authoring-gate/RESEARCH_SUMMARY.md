# Research Summary — Plan-Structure Authoring Gate

Inline recon (no Gemini research sprint — see the `docs/features/CLAUDE.md` note that
claude-config skips `docs/gemini-sprint/` staging by design). Findings that shaped the locked
decisions in `SPEC.md`:

## 1. `lazy_core.py` parsers reused (imported, never edited)

Grepped and read in full before designing the validator, to confirm exact reuse surfaces:

- `_plan_wu_checkbox_counts(plan_text) -> (unchecked, checked)` (`lazy_core.py:3671`) — pure text
  function, no I/O, safe to import directly. Backs rule 1.
- `remaining_unchecked_are_verification_only(phases_text) -> bool` (`lazy_core.py:2312`) — pure
  text function; used for the recognizer-parity cross-check test, not as rule 2's own
  implementation (see finding 3 below for why).
- `_VERIFICATION_ONLY_MARKER`, `_VERIFICATION_SECTION_RE`, `_DELIVERABLES_SECTION_RE` — constants,
  imported by name into the new section-tracking helper so vocabulary can never silently drift
  from the state machine's own.
- `_PLAN_PART_RE`, `_plan_series_index`, `_plan_phase_set` (`lazy_core.py:1745-1829`) — the
  filename-suffix and `phases:`-frontmatter parsers `_plan_sort_key` composes. `_PLAN_PART_RE` is
  imported directly (a plain constant); `_plan_series_index`/`_plan_phase_set` are NOT called
  directly — see finding 2.

## 2. `_parse_plan_frontmatter` / `parse_sentinel` call `_die()` on malformed YAML — unsafe to
   call from a validator that must report, not abort

`parse_sentinel` (`lazy_core.py:878`) — the function every plan-frontmatter reader in `lazy_core`
ultimately calls — invokes `_die()` (prints JSON, `sys.exit(2)`) on a missing closing fence,
invalid YAML the tolerant rescue can't fix, or a non-mapping frontmatter body. A structural
validator's whole point is to collect and report EVERY finding across a file in one pass
(including "the frontmatter itself is broken") and never abort the process on the first such
file. Calling `_plan_series_index`/`_plan_phase_set`/`_parse_plan_frontmatter` directly on
arbitrary (possibly malformed) input would risk an uncontrolled `SystemExit(2)` mid-check-run.
**Consequence:** `validate-plan.py` reimplements a small, exception-safe, non-throwing sibling
(`_read_frontmatter_safe` + `_local_plan_series_index` + `_local_plan_phase_set`) rather than
calling the `lazy_core` originals — a documented, necessary divergence (see SPEC D1's locked
note), not an oversight.

## 3. A naive vocabulary/bracket scan false-positives heavily against the REAL corpus — the
   validator was tuned against it, not just synthetic fixtures

Before locking rule 2 and rule 3, I ran the first cut of the validator against every committed
plan part and PHASES.md in this repo (252 files: `docs/features/**/plans/*.md`,
`docs/bugs/**/plans/*.md`, `docs/features/**/PHASES.md`, `docs/bugs/**/PHASES.md`):

- **Rule 3 (template-row), first cut:** a bare `[{<][^{}<>]{2,80}[}>]` search flagged 124/252
  files. Root cause: the canonical `<!-- verification-only -->` marker (the very marker this
  gate imports and relies on) itself matches a naive "contains a bracket span" search — it starts
  with `<`, ends with `>`, and its inner text has no nested brackets. **Fix:** strip HTML
  comments first, then require the row's ENTIRE remaining text to BE the placeholder
  (`_TEMPLATE_WHOLE_ROW_RE`, anchored start-to-end) rather than merely contain one.
- **Rule 2 (verif-placement), first cut:** a vocabulary including bare `runtime verification` and
  `VALIDATED.md` flagged 13 files, 13/13 false positives — every hit was either a deliverable row
  cross-referencing the Runtime Verification section by name ("(see Runtime Verification
  below)", completely normal prose in this repo's own PHASES.md) or a row merely NAMING
  `VALIDATED.md` as a sentinel filename in an enumeration (also completely normal — this whole
  repo's PHASES.md corpus documents the pipeline that produces `VALIDATED.md`). **Fix:** narrowed
  to the self-describing tag vocabulary the templates actually emit ON a verification row ("mcp
  integration test" / "mcp test assertion" / "mcp assertion" / "reachability smoke").
- **Rule 5 (series-order), first cut:** a bare "Phase N" scan over Entry-criteria/Prerequisites
  text flagged `plan-skills-redesign/plans/all-phases-plan-skills-redesign-part-3.md` — its real
  text is "Entry criteria: None; establishes the pattern Phase 4 propagates," a FORWARD reference
  (Phase 3 feeds Phase 4 later), not a dependency in the "Phase 3 needs Phase 4 first" direction
  the rule targets. **Fix:** require a completion word ("Phase N complete/done/finished") or a
  dependency verb immediately before the mention ("requires/depends on/blocked by/needs/after
  Phase N").

After all three fixes, the same 252-file corpus scan returns exactly **4 genuine pre-existing
violations, 0 false positives** (3 pre-ISSUE-6 legacy plans missing a WU checklist, 1 historical
gate-owned Status-flip row — all predate this gate, all `status: Complete`/archived). These 4 are
enumerated in `test_validate_plan.py`'s `TestRealCorpusCheck._KNOWN_VIOLATIONS` allowlist so the
corpus stays a live regression net (a NEW violation anywhere in the tree fails that test) rather
than a one-time report.

## 4. `/plan-feature` and `/plan-bug` are pure dispatch wrappers

Read both `SKILL.md` files in full: neither authors PHASES.md or plan-part content directly —
both exclusively `Skill({ skill: "spec-phases", ... })` / `Skill({ skill: "write-plan", ... })`.
So D3's "all five inherit it" is satisfied for these two with ZERO additional wiring; the
finalization gate only needs physical injection into `/write-plan`, `/spec-phases`, and
`/spec-phases-batch` (which DOES author PHASES.md content directly via its own subagent
dispatch prompts, unlike the other two).

## 5. `/write-plan-cloud`'s own contract bans the checkbox format

Read `write-plan-cloud/SKILL.md` in full: Step 4's Self-Containment Audit item 7 explicitly
states "No progress checkboxes... Any `- [ ]` in the draft that the agent is told to 'check off'
is a leak — remove the check-off semantics." Its deliverable (`plans/cloud-*.md`) is a
self-contained GitHub-Copilot-cloud-agent briefing for the `cognitoforms/cognito` repo — a
categorically different artifact from a lazy-pipeline plan part. Wiring rules 1/2/3 (all of which
assume the checkbox format) onto it would force an incompatible shape onto a document engineered
specifically not to have it. Excluded by both the skill-wiring decision (D3) and the validator's
own path-convention scope gate (`plans/cloud-*.md` classifies as out-of-scope, same as any other
non-lazy-plan-shaped file).
