# Skill-Config Schema + Reference Lint — Feature Specification

> No schema or required-file contract exists for `repos/<name>/.claude/skill-config/`
> (algobooth: 21 files; cognito-forms: 16; cognito-docs: none) — missing-file semantics are
> per-reference prose conventions, with no way to distinguish intended-absent from broken.
> Field cost, transcript-mined: the #1 tool-error cluster in the entire AlgoBooth session
> corpus is **377 failed Reads of `.claude/skill-config/commit-policy.md` across ~100 sessions
> (over 10% of ALL tool errors)** — the file is referenced 29× across 17 skill files, exists in
> cognito-forms but NOT algobooth, so every cycle subagent burns a failed Read before falling
> back. Add a per-repo declared-files manifest with intended-absent markers, JSON-schema
> validation for the load-bearing `*.json` configs, and a `lint-skills.py` sweep of every
> `.claude/skill-config/<file>` mention (`!cat` AND prose) against each repo's dir — plus the
> immediate quick win: kill the 377-error cluster at the source.

**Status:** Draft
**Friction-reduction feature:** yes
**Priority:** P2
**Last updated:** 2026-07-11
**Source:** repo-exploration proposal session 2026-07-11 (transcript mining from that session;
on-disk facts — file counts, reference counts, lint behavior — re-verified against the working
tree the same day)

> Substantive (non-block) dependencies are **implemented mechanisms**, not sibling specs:
> - `user/scripts/lint-skills.py` — the extension point. Today it validates ONLY the
>   `_components/` half of the fallback pattern (`!cat .claude/skill-config/<x> || cat
>   ~/.claude/skills/_components/<x>`): the fallback target's existence is checked, the
>   skill-config primary is never resolved against any repo dir, and prose path mentions are
>   never scanned (only `!cat`-trigger lines enter the check at all). It already has the seed
>   of per-repo awareness: a repo with `skill-config/` but no `capabilities.txt` is flagged.
> - `user/hooks/build-queue-enforce.sh` — proof that skill-config is load-bearing config, not
>   just prose: it reads `<toplevel>/.claude/skill-config/build-queue-ops.json` (L336–342);
>   the file's *presence* arms enforcement for a repo (L394) and an unreadable file fails open
>   (L579) — all schema-unvalidated today.
> - `user/scripts/project-skills.py` — per-repo projection (`skills-projected/<repo>/`) already
>   resolves skill-config overrides per repo; the lint sweep reuses the same repo-discovery.
> - The `!cat` fallback convention (`_components/` override pattern) — established by
>   `friction-kpi-registry` D7 and used across the skill tree; this feature gives its
>   skill-config half the validation the components half already has.

---

## Executive Summary

`repos/<name>/.claude/skill-config/` is the harness's per-repo override surface: skills
reference `.claude/skill-config/<file>` and either fall back to a `_components/` default, fall
back to an inline echo, or — the dangerous class — just mention the path in prose and assume
it exists. Nothing declares which files a repo intends to provide, so absence is ambiguous
by construction: is a missing `commit-policy.md` "this repo uses the default" or "someone
forgot to create it"? Today (re-verified 2026-07-11): algobooth ships 21 files, cognito-forms
16, cognito-docs none — three repos, three implicit contracts, zero validation.

The cost is not hypothetical. Transcript mining across the AlgoBooth session corpus (proposal
session 2026-07-11) found the single largest tool-error cluster in the whole corpus is **377
failed Reads of `.claude/skill-config/commit-policy.md` across ~100 sessions — over 10% of ALL
tool errors**. The file is referenced 29 times across 17 skill files (re-measured; `user/skills`
+ `repos/*/.claude/skills`, projections excluded); it exists in cognito-forms but **not** in
algobooth's 21-file dir, and the reference convention is read-then-fallback — so every
AlgoBooth cycle subagent burns a failed Read, an error turn, and the fallback read of
`_components/commit-and-push.md`, hundreds of times over. The behavior is *correct* and the
cost is pure friction: the canonical example of intended-absent being indistinguishable from
broken.

Two more verified instances bound the problem class:

- **Dead prose pointer, no fallback:** `user/skills/lazy-batch/SKILL.md` L592 says "Full rule:
  `.claude/skill-config/long-build-ownership.md`" — a bare prose reference with no fallback
  form. The file exists ONLY in `repos/algobooth/`; from any other repo the pointer is dead,
  and no lint can see it because prose mentions are outside `lint-skills.py`'s scan entirely.
- **Load-bearing but schema-free:** `build-queue-ops.json`'s *presence* arms
  `build-queue-enforce.sh` for a repo; a malformed file fails open (unreadable → allow,
  enforce.sh L579). A typo'd ops entry silently disarms enforcement for that command — no
  validation exists at authoring time or lint time.

The fix is a declaration surface plus a lint that consumes it: (1) each repo's skill-config dir
carries a small `MANIFEST.json` declaring its files — including explicit intended-absent
markers for known references the repo deliberately does not provide; (2) the load-bearing
`*.json` configs get JSON-schema validation; (3) `lint-skills.py` sweeps every
`.claude/skill-config/<file>` mention — `!cat` forms AND prose paths — against each repo dir,
honoring the markers, so a dangling reference or an undeclared file is a lint finding, not a
runtime failed-Read x100 sessions. Named in scope as the immediate quick win: kill the
377-error cluster (author `repos/algobooth/.claude/skill-config/commit-policy.md`, or flip the
17 skills' reference order to test-then-read) without waiting for the full manifest machinery.

Mission criteria: **efficient** (the #1 error cluster, plus every future sibling of it, stops
burning subagent turns) and **effective** (absence becomes a declared, lintable state — the
same debt-must-be-visible posture as the KPI registry's `pending` provenance).

## KPI Declaration

Drafted row (full schema). Baseline is honestly `pending`: the mined 377-count is a
corpus-total from the proposal session, not a windowed rate — the windowed collector is part of
this feature's scope:

```json
{
  "id": "skill-config-broken-reference-reads",
  "system": "skill-config",
  "title": "Failed Reads / dangling references on .claude/skill-config/ paths",
  "friction": "The #1 tool-error cluster in the mined AlgoBooth corpus: 377 failed Reads of .claude/skill-config/commit-policy.md across ~100 sessions (>10% of all tool errors) — referenced 29x across 17 skill files, present in cognito-forms but absent in algobooth, with no way to declare intended-absent; plus dead prose pointers (long-build-ownership.md) and schema-unvalidated load-bearing JSON (build-queue-ops.json) invisible to lint-skills.py.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "failed-reads-per-window",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "all",
  "notes": "Manual evidence of record: 377 failed commit-policy.md Reads across ~100 mined AlgoBooth sessions (proposal session 2026-07-11, transcript mining) — a corpus total, not a windowed rate, hence provenance pending. The registered machine signal (deny-ledger process-friction-count) is the coarse channel: incident-scan clusters recurring tool-error friction into the ledger as process-friction entries. Implementation SHOULD register a dedicated session-log-mining selector (e.g. skill-config-failed-read-count) and re-point this row, then capture the windowed baseline — the same registry follow-up pattern as lean-plan-files' drafted row. The quick win (Phase 0) should drive the commit-policy component of this signal to ~0 immediately; the lint (Phase 2) prevents new clusters from forming."
}
```

## Design Decisions

### D1. Declaration surface: per-repo `skill-config/MANIFEST.json`

- **Classification:** `product-behavior (needs operator confirmation)`
- **Question:** Where does a repo declare which skill-config files it provides and which
  known references it deliberately leaves absent?
- **Options:**
  - **A — `repos/<name>/.claude/skill-config/MANIFEST.json` (recommended):** lives with what it
    describes; travels with the repo's `.claude/` symlink; one file per repo. Shape (v1):
    `{"schema_version": 1, "provides": ["quality-gates.md", ...], "intended_absent":
    [{"file": "commit-policy.md", "reason": "uses the _components default"}], "json_schemas":
    {"build-queue-ops.json": "build-queue-ops"}}`. `provides` is lint-checked both ways
    (declared-but-missing = error; present-but-undeclared = error — the manifest stays honest).
    `intended_absent` entries require a `reason` (the C5 reason-hygiene precedent).
  - **B — central registry in `user/scripts/`:** one file to rule all repos, but it inverts
    ownership (a repo's contract living outside the repo's dir) and bit-rots exactly like any
    central inventory; the per-repo dir is already the unit of projection and symlinking.
  - **C — infer from references (no manifest):** lint computes the union of all
    `.claude/skill-config/` references and flags any repo missing any referenced file — no
    declaration needed, but it cannot express intended-absent, which is THE distinguishing
    requirement (commit-policy.md is *correctly* absent in algobooth today; C would force
    creating stub files everywhere or suppressing the check).
- **Recommendation:** A. The manifest is small, diffable, and the intended-absent marker is the
  feature's core semantic. `capabilities.txt` (already flagged-if-missing by `lint-skills.py`)
  folds into `provides` conceptually but stays a separate file (hooks read it directly);
  the manifest simply declares it like any other file.

### D2. JSON-schema validation for load-bearing configs

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** `build-queue-ops.json` arms a fail-open enforcement hook; malformed = silently
  disarmed. What validates it?
- **Design:** stdlib-only structural validation (hand-rolled checkers, the `kpi-scorecard.py`
  `lint_row` style — NOT a jsonschema dependency), one checker per known config, dispatched via
  the manifest's `json_schemas` map. v1 covers `build-queue-ops.json` (shape derived from what
  `build-queue-enforce.sh` actually reads at L336–394 — command registration entries) and the
  manifest itself. Unknown JSON files in skill-config with no `json_schemas` entry are a
  warning (undeclared machine-read surface), not an error. Validation runs in the lint sweep
  (D3) — authoring-time, never on the hook's read path (the hook's fail-open stays untouched;
  a broken file still fails open at runtime, it just can no longer *land* unnoticed).

### D3. Reference sweep: `!cat` forms AND prose mentions, per repo, honoring markers

- **Classification:** `mechanical-internal (recommend auto-accept)`
- **Question:** How does lint close the gap where only the `_components/` fallback half is
  validated and prose pointers are invisible?
- **Design:** extend `lint-skills.py` with a skill-config sweep: collect every
  `.claude/skill-config/<file>` mention across all skill sources — the three `!cat` regex
  forms it already parses (now validating the *primary* path too) plus a prose scan for the
  literal path pattern in skill bodies and components. For each (reference, repo) pair over the
  repos discovered from `repos/*/.claude/skill-config/`: file present ⇒ OK (and must be in
  `provides`); absent + `intended_absent` entry ⇒ OK when the reference form has a fallback,
  ERROR when it is a bare prose pointer with no fallback (an intended-absent file cannot
  satisfy a fallback-less pointer — the `long-build-ownership.md` class becomes mechanically
  visible); absent + undeclared ⇒ ERROR naming file, repo, and every referencing skill:line.
  References inside repo-scoped skills (e.g. `repos/algobooth/.claude/skills/**`) are checked
  against that repo only; user-level skills are checked against every repo. Prose-scan false
  positives (illustrative paths in documentation-of-the-pattern, like `friction-kpi-registry`'s
  D7 text) are handled with an explicit inline suppression comment, kept rare and visible.
- **No new invocation surface:** the sweep runs inside the existing `lint-skills.py` entry
  point (the projection/lint house rule already runs it after every skill edit).

### D4. The commit-policy quick win ships first and is named in scope

- **Classification:** `product-behavior (needs operator confirmation of which variant)`
- **Question:** The 377-error cluster has a two-line fix available today. Which variant?
- **Options:**
  - **A — author `repos/algobooth/.claude/skill-config/commit-policy.md` (recommended):**
    content = an explicit adoption of the `_components/commit-and-push.md` default (a pointer
    file, not a fork — no policy duplication), plus any AlgoBooth-specific commit rules that
    already exist in prose elsewhere. Kills all 377-class failed Reads at the source; the read
    succeeds and says "use the default + these deltas".
  - **B — flip the 29 references from read-then-fallback to test-then-read:** no new file, but
    edits 17 skills (and their coupled pairs), and every future reference must remember the
    ordering — a convention fix for a declaration problem.
  - **C — wait for the manifest (D1) + a smarter reference convention:** leaves the #1 error
    cluster burning for however long the pipeline takes to get here.
- **Recommendation:** A, executed as Phase 0 the moment this feature enters implementation —
  it is deliberately independent of the manifest machinery so the dominant cost dies first.
  (Authoring that file is an implementation act of this feature; this SPEC only names it.)

## Technical Design

```
repos/<name>/.claude/skill-config/
├── MANIFEST.json            (NEW — schema_version, provides[], intended_absent[{file,reason}],
│                             json_schemas{})
├── build-queue-ops.json     (existing; gains a structural checker keyed via json_schemas)
└── *.md / capabilities.txt  (existing; now declared in provides[])

user/scripts/lint-skills.py  (extended)
  ├─ existing: !cat component-existence checks, capabilities checks
  ├─ NEW: manifest validation (schema; provides ↔ dir bidirectional check;
  │        intended_absent reason hygiene)
  ├─ NEW: json_schemas dispatch (stdlib structural checkers)
  └─ NEW: reference sweep — every `.claude/skill-config/<file>` mention
          (!cat primary paths + prose literals) × every discovered repo,
          honoring intended_absent; bare prose pointers require presence
          or an explicit suppression
```

- **Failure semantics:** lint findings are exit-nonzero errors (authoring-time gate); nothing
  on any runtime read path changes — hooks keep their fail-open behavior, skills keep their
  fallback forms. This feature makes absence *visible*, it never makes reads stricter.
- **Repo discovery:** `repos/*/.claude/skill-config/` (the same set `project-skills.py`
  per-repo projection discovers); a repo with a `.claude/` but no skill-config dir
  (cognito-docs today) is out of scope for the sweep until it grows one — at which point the
  manifest requirement applies from file one.
- **Coupled-pair note:** none of the edited surfaces participate in
  `user/scripts/lazy-parity-manifest.json` except insofar as skill prose mentioning
  skill-config paths lives in coupled skills; the sweep reads, never edits, so no parity
  interaction. (If Phase 0's variant B were chosen instead, the 17-file edit WOULD touch
  coupled pairs — one more reason for variant A.)
- **House invariants honored:** stdlib-only; declaration over inference; reasons required on
  exemptions; fail-open runtime preserved; loud authoring-time errors over silent runtime
  fallbacks; debt (intended-absent) visible rather than indistinguishable from breakage.

## Implementation Phases

- **Phase 0 — Quick win (~0.5 session).** D4-A: author algobooth's `commit-policy.md`
  pointer-adoption file. Proven done: a fresh AlgoBooth session's commit flow reads it
  successfully (no failed-Read turn); mined error count for that path trends to ~0 in
  subsequent sessions.
- **Phase 1 — Manifests + JSON checkers (~1 session).** `MANIFEST.json` schema + authored
  manifests for algobooth (22 files incl. Phase 0's) and cognito-forms (16); structural
  checkers for the manifest + `build-queue-ops.json`; pytest fixtures. Proven done: lint green
  on real manifests, red on each fixture violation (undeclared file, declared-but-missing,
  reasonless intended_absent, malformed ops entry).
- **Phase 2 — Reference sweep (~1–2 sessions).** D3 in `lint-skills.py`; burn down the initial
  finding list (expect: the `long-build-ownership.md` prose pointer gains a fallback or an
  algobooth-scoped home; stray dangling references surfaced then fixed or suppressed-with-
  reason). Proven done: sweep exit 0 on the tree; fixture coverage for every finding class;
  the known instances in this SPEC each provably detected by the fixture that models them.
- **Phase 3 — Windowed KPI collector + registry follow-up (~0.5–1 session).** Register the
  dedicated selector; re-point the KPI row; capture the baseline. Proven done: scorecard
  renders a real value for the row (not NO-DATA).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| 377-cluster dead | AlgoBooth session post-Phase 0 | commit-policy.md Read succeeds; error mining shows ~0 new failures on that path | session transcript / mining |
| Intended-absent ≠ broken | Fixture: absent file with marker + fallback form | Lint OK | pytest fixture |
| Broken reference caught | Fixture: absent file, no marker | Lint error naming file, repo, skill:line | pytest fixture |
| Dead prose pointer caught | Fixture: bare prose pointer to an absent/intended-absent file | Lint error (fallback-less pointer class) | pytest fixture |
| Manifest honesty (both ways) | Fixture: file on disk not in provides / provides entry not on disk | Lint error each direction | pytest fixture |
| Load-bearing JSON validated | Fixture: malformed build-queue-ops.json entry | Lint error; runtime hook behavior unchanged (still fail-open) | pytest + hook test |
| No runtime strictness added | All existing skills/hooks post-lint | Fallback forms and hook fail-open behave byte-identically | regression run |

## Open Questions

- **D1 operator confirmation:** per-repo MANIFEST.json as the declaration surface (vs central
  registry).
- **D4 operator confirmation:** variant A (author the algobooth file) vs B (flip reference
  order) for the quick win — A recommended.
- Whether user-level skills referencing skill-config paths should be checked against ALL repos
  (current D3 design) or only repos whose skill catalog actually routes that skill — start
  with all-repos + intended_absent markers; tighten only if marker noise appears.
- Prose-scan suppression syntax (inline comment form) — implementation-time choice; must be
  greppable and require a reason string.

## Cross-links

- `docs/features/friction-kpi-registry/SPEC.md` — the measurability gate this KPI Declaration
  satisfies; also the documented home of the `!cat` per-repo override convention (D7) whose
  skill-config half this feature finally validates.
- `docs/features/execute-plan-skill-diet/SPEC.md` — Complete — created
  `repos/algobooth/.claude/skill-config/execute-plan-repo-gates.md` and flagged the AlgoBooth
  pickup-path question (repos/algobooth has no manifest.psd1 Repos entry); this feature's
  manifest + sweep make that class of "does the repo actually receive this file?" question
  answerable by lint instead of by nightly-run observation.
- `docs/features/lean-plan-files/SPEC.md` — Complete — precedent for the drafted-KPI-row +
  collector-follow-up registry pattern reused here.
