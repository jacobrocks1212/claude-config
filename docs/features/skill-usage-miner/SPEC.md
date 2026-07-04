# Skill Usage Miner + Dead-Weight Audit — Feature Specification

> The skills tree only grows — 83 user-level skills plus 29 repo-scoped ones today, with stray
> non-skill artifacts checked in alongside them — and nothing measures which skills are
> load-bearing. This feature ships a stdlib-only, **read-only** miner over the same session-log
> corpus `toolify-miner.py` reads, counting per-skill invocations via two honest detectors
> (Skill-tool calls and slash-command markers), and emits a ranked usage report with a
> never-invoked list, a hygiene sweep of non-skill files, and toolify-bar cross-links for
> high-frequency prose skills. It **proposes, never auto-archives** — archival stays a deliberate
> operator move into `archived/` with its audit-trail row.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented contracts, not sibling
> specs**:
> - `user/scripts/toolify-miner.py` — the JSONL corpus-walking layer (`_iter_log_files`, the
>   assistant-turn `tool_use` extraction loop) is directly reusable; its value-*eliding*
>   normalization (`_normalize_call`) is deliberately NOT (skill names are argument values).
> - `~/.claude/projects/**/*.jsonl` session-log corpus (+ per-parent `subagents/agent-*.jsonl`) —
>   the transcript anatomy documented in `user/skills/mine-sessions/SKILL.md`, including the
>   `<command-name>/foo</command-name>` slash-command marker its `digest_sessions.py` already
>   parses.
> - `archived/CLAUDE.md` — the deliberate-archival convention (move, don't delete; add a
>   supersession row) the report's proposals must emit verbatim-ready text for.
> - `user/skills/CLAUDE.md` — the frontmatter contract defining what counts as a skill (a
>   `<name>/SKILL.md` dispatcher), which the inventory and hygiene sweep enforce.

---

## Executive Summary

Every skill in `user/skills/` (and every repo-scoped skill under `repos/<name>/.claude/skills/`)
is permanent prompt surface and maintenance burden: coupled-pair rules, projection runs, lint
scope, and operator attention. The tree has only ever grown, and it already carries provable dead
weight — `user/skills/sh.exe.stackdump` is a crash dump, `user/skills/remotion` is a dangling
Windows-path symlink, and `local-site/`/`teach/` carry lowercase `skill.md` files the frontmatter
contract does not recognize. Meanwhile there is no usage signal at all: nobody can say which of the
83 user-level skills were invoked this quarter and which have never been invoked. That contradicts
the mission's **efficient** criterion — the harness prunes nothing because it measures nothing.

The solution is a sibling of `toolify-miner.py`: `skill-usage-miner.py`, stdlib-only and read-only
over the same corpus, joining a **skill inventory** (enumerated from the repo's `SKILL.md` files)
against **invocation signals** mined from the logs. Two detectors are defined honestly: Skill-tool
`tool_use` blocks on assistant turns (reading the `skill` input value), and slash-command markers
in user-turn text (the exact `<command-name>(/[\w:-]+)</command-name>` regex
`digest_sessions.py:125` already uses). Both undercount by construction — component-injected
protocols, auto-invoke prose triggers, and cloud-session logs are invisible — so the report treats
a zero count as a *flag to investigate*, never proof of deadness, and the feature's operator
constraint follows: it proposes archival (with ready-to-review `git mv` + `archived/CLAUDE.md` row
text), and a human executes it.

The report closes the loop with the toolification framework without coupling to it: high-frequency
skills are annotated as candidates worth running the sequence miner against, cross-linked to the
bar doc — this miner never invokes the sibling promotion pipeline. The result is a pruning loop
that is cheap to run, safe by construction (no writes outside its own report output), and honest
about its blind spots.

## Design Decisions

### D1. Sibling script reusing the miner's corpus-walk, not a merged CLI

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** One tool or two? The toolify miner and this miner read the same corpus.
- **Options:**
  - **A — merge into `toolify-miner.py` as a mode:** Pros: one corpus walker. Cons: the two tools
    answer different questions with different schemas, bars, and output shapes (sequence
    signatures ranked by token score vs. per-skill counts joined against an inventory); a merged
    CLI couples their release cadence and bloats the miner's tested surface.
  - **B — sibling `user/scripts/skill-usage-miner.py` importing the miner via
    `importlib.util.spec_from_file_location`** (the hyphenated-module pattern proven at
    `test_toolify_miner.py:44-52`) for `_iter_log_files` and the assistant-turn parsing shape.
    Carries its own value-*preserving* extractor, since the reusable `_normalize_call` elides
    exactly the values (the `skill` argument) this miner needs. Pros: shared walk, independent
    contracts, each with its own test file. Cons: a second file.
  - **C — extract a shared `toolify_common.py` module:** premature for two consumers of ~40 lines;
    revisit when a third log-mining tool appears.
- **Recommendation:** B — mirrors the house pattern of small single-purpose scripts
  (`lazy-queue-doc.py` beside `lazy-state.py`) and keeps `toolify-miner.py` untouched except as an
  import source.
- **Resolution:** Auto-accepted B; internal code placement, no operator-visible difference beyond
  the command name.

### D2. Two invocation detectors, counted separately, honestly caveated

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What counts as "the skill was used"?
- **Options:**
  - **A — two detectors, separate columns:** (1) **Skill-tool detector** — assistant-turn
    `tool_use` blocks with `name == "Skill"`, reading `input["skill"]` (covers programmatic and
    proactive invocations, including inside `subagents/agent-*.jsonl`); (2) **slash-command
    detector** — user-turn text matched by `<command-name>(/[\w:-]+)</command-name>`, the marker
    Claude Code writes when the operator types `/foo` (regex already field-proven in
    `user/skills/mine-sessions/scripts/digest_sessions.py:125`). Report both counts plus distinct
    session counts and a last-seen timestamp (per-line ISO `timestamp`).
  - **B — single merged count:** loses the ability to distinguish operator-driven skills from
    agent-driven ones — a real signal when deciding what to prune or toolify.
  - **C — add fuzzy prose-mention matching:** high false-positive risk (skill names are common
    words: `fix`, `commit`, `push`, `stage`, `explain`); rejected for v1.
- **Recommendation:** A, with the standing caveat block in every report: **known false negatives**
  are `_components/` protocols injected via `!cat` (never a Skill invocation), skills followed
  from `auto-invoke` prose preferences without a formal dispatch, and any usage in sessions whose
  logs are not on this workstation. Zero count = "investigate", never "dead".
- **Resolution:** Auto-accepted A; detector internals with the caveat carried as report prose.

### D3. Window semantics: full corpus + `--since`, never-invoked gated by skill age

- **Classification:** `product-behavior (operator-approved 2026-07-04)`
- **Question:** Over what time window is usage counted, and when is a zero-count skill flagged
  "never invoked" (the archival-proposal trigger)?
- **Options:**
  - **A — full available corpus by default, optional `--since YYYY-MM-DD` filter, plus a fixed
    recent-window column (e.g. last 30 days) in the report.** "Never invoked" is flagged only
    when the skill is *older than the observation floor*: its first-commit date (via
    `git log --follow --diff-filter=A -- user/skills/<name>/SKILL.md`) predates the oldest scanned
    log AND the corpus spans ≥ the recent window — so a brand-new skill or a freshly rotated log
    dir cannot generate a false archival proposal. Pros: honest with an aging/rotating corpus;
    the git-age gate makes the flag falsifiable. Cons: slightly more machinery (one git subprocess
    per zero-count skill).
  - **B — fixed rolling window (e.g. 90 days) only:** simpler, but "never invoked in 90 days" and
    "never invoked ever" are different claims, and the report should make the stronger one only
    when the data supports it.
  - **C — no time dimension:** cheapest; loses trend and recency entirely.
- **Recommendation:** A — the report's headline claims must survive scrutiny, and the age gate is
  what turns "no signal" into "no signal despite N months of opportunity".
- **Resolution:** **A** — operator-approved 2026-07-04 — recommended option taken. Full corpus by
  default, optional `--since YYYY-MM-DD`, a 30-day recency column, and the never-invoked flag
  gated by git-derived skill age (`git log --follow --diff-filter=A --format=%cs`).
  Implementation note: the 30-day recency window is anchored to the **newest corpus timestamp**
  (not wall clock) so a saved report is byte-stable and diffs cleanly.

### D4. Scope: include repo-scoped skills; workstation-visible logs only in v1

- **Classification:** `product-behavior (operator-approved 2026-07-04)`
- **Question:** Does v1 cover only `user/skills/` or also the 29 repo-scoped skills? And what
  about cloud sessions?
- **Options:**
  - **A — inventory both scopes; attribute repo-scoped skills per repo; workstation logs only.**
    Inventory = `user/skills/*/SKILL.md` (83 today) + `repos/<name>/.claude/skills/*/SKILL.md`
    (29 today: 2 algobooth, 27 cognito-forms), each row labeled with its scope. Per-repo
    invocation attribution uses the encoded-cwd project-dir heuristic documented in
    `mine-sessions/SKILL.md` (a session's project dir name embeds its working directory; match on
    the repo slug), explicitly labeled *heuristic* in the report. **Cloud sessions are out of
    scope for v1** — their transcripts do not land in this workstation's `~/.claude/projects` —
    so cloud-variant skills (`lazy-cloud`, `lazy-batch-cloud`, `write-plan-cloud`) are annotated
    `cloud-biased undercount` rather than ranked naively. Pros: the dead-weight question applies
    at least as much to the 27 cognito-forms skills as to user-level ones; the honesty labels
    prevent the two known distortions. Cons: attribution heuristic can misfile worktree-suffixed
    project dirs (mitigation: substring match over all dirs containing the slug, as mine-sessions
    prescribes).
  - **B — user-level skills only:** smaller v1; leaves the largest single skill population
    (cognito-forms) unmeasured.
  - **C — attempt cloud-log ingestion in v1:** no local source exists to read; would require new
    sync infrastructure far beyond a miner.
- **Recommendation:** A — inclusion is nearly free (the inventory is a glob; attribution is
  labeling, not gating), and the cloud caveat is a documentation obligation either way.
- **Resolution:** **A** — operator-approved 2026-07-04 — recommended option taken. Inventory both
  scopes; heuristic per-repo attribution (project-dir slug substring match, labeled heuristic);
  cloud sessions out of scope with cloud-variant skills (`*-cloud`) annotated
  `cloud-biased undercount`. (Implementation-time count correction: the repo-scoped population is
  30 today — 3 algobooth incl. `mcp-test`, 27 cognito-forms — not the 29 the survey snapshot said.)

### D5. Hygiene-sweep rule and placement

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How are non-skill artifacts detected, and does the check live here or in
  `lint-skills.py`?
- **Options:**
  - **A — a `## Hygiene` section in this miner's report:** flag any top-level `user/skills/`
    entry that is not `CLAUDE.md`, `_components/`, or a directory containing `SKILL.md`; also
    flag dirs whose dispatcher is a case-variant (`skill.md`) and symlinks whose target does not
    resolve from the repo. Verified real findings today: `sh.exe.stackdump` (530-byte crash
    dump), `remotion` (symlink → `C:/Users/.../remotion-skills/...`, dangling on any
    case/OS-sensitive checkout), `local-site/` and `teach/` (lowercase `skill.md` — invisible to
    the `SKILL.md` frontmatter contract on case-sensitive filesystems). Same rule applied to each
    `repos/<name>/.claude/skills/`.
  - **B — extend `lint-skills.py`:** thematically plausible, but that script's contract is
    injection/`!cat` validation with exit-code semantics existing flows consume
    (`lint_skill`/`lint_projected`/`lint_capabilities`); adding inventory checks changes when it
    fails for consumers that don't care about hygiene.
- **Recommendation:** A for v1, with a noted vN option to promote the stabilized rule into
  `lint-skills.py` (or CI) once its false-positive rate is known. The `remotion` symlink case is
  deliberately *flagged, not auto-classified* — it may be an intentional local-machine link that
  simply doesn't belong in the repo; the operator decides.
- **Resolution:** Auto-accepted A; detection internals — the findings themselves are what the
  operator sees, and those are report content, not a mode choice.

### D6. Report destination and cadence: on-demand stdout, optional `--out`, no auto-wiring

- **Classification:** `product-behavior (operator-approved 2026-07-04)`
- **Question:** Where does the report go and what triggers it?
- **Options:**
  - **A — on-demand CLI mirroring `toolify-miner.py`'s shape:** `--markdown` / `--json`
    (both when neither), `--out <file>` to save, run by the operator when curious and cited by
    `/lazy-batch-retro` if the operator asks. Pros: zero new autonomous surface; the deliberate
    cadence matches the deliberate-archival constraint; identical mental model to the sibling
    miner. Cons: relies on the operator running it.
  - **B — committed report doc regenerated by the pipeline (the `LAZY_QUEUE.md` pattern):**
    Pros: always current. Cons: usage stats change with every session, so the doc would churn
    every commit unless windowed-and-rounded; unlike queue state, nothing downstream *reads* it.
  - **C — auto-feed into `/lazy-batch-retro`:** couples a P2 audit tool into the retro's already
    long contract before the report's value is proven.
- **Recommendation:** A for v1; revisit B/C only if the operator finds themself running it on a
  fixed cadence anyway.
- **Resolution:** **A** — operator-approved 2026-07-04 — recommended option taken. On-demand CLI
  (`--markdown` / `--json`, both when neither; `--out <file>` to save); no auto-wiring into the
  pipeline or the retro.

### D7. Toolify cross-feed: annotate-only, never auto-enqueue

- **Classification:** `product-behavior (operator-approved 2026-07-04)`
- **Question:** The stub asks that high-frequency prose skills be flagged as toolification
  candidates. How hard is that link?
- **Options:**
  - **A — annotate-only:** the report's `## Toolify candidates` section lists skills above a
    frequency threshold whose bodies are deterministic-looking prose, each cross-linked to
    `docs/features/unified-pipeline-orchestrator/toolify-bar.md` with the suggested next step
    ("run `toolify-miner.py` over the sessions that invoked this skill"). Pros: the toolify bar
    judges *tool-call sequences*, not skills — a frequent skill is a hint about where dances
    live, not itself an above-bar candidate; keeps the two miners decoupled.
  - **B — auto-run `toolify-miner.py` scoped to matching sessions and inline its table:** heavier
    runs, and scoping the sequence miner by skill needs a session-filter it doesn't have yet.
  - **C — auto-enqueue via the sibling `toolify-auto-promotion` materializer:** violates that
    feature's own operator gate (naming is human) and creates a spec-to-spec coupling both specs
    deliberately avoid.
- **Recommendation:** A for v1; B becomes attractive if/when the sequence miner grows a
  session-filter flag (noted as a deferred idea, not a dependency).
- **Resolution:** **A** — operator-approved 2026-07-04 — recommended option taken. Annotate-only
  cross-links to `docs/features/unified-pipeline-orchestrator/toolify-bar.md`; the documented
  frequency threshold is a module constant (`TOOLIFY_CANDIDATE_THRESHOLD`); this miner never
  invokes the sequence miner or the promotion pipeline.

### D8. Archival proposals are ready-to-review text, never executed

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What exactly does "proposes, never auto-archives" (operator-set constraint) emit?
- **Options:**
  - **A — per-skill proposal block:** the `git mv user/skills/<name> archived/user-skills/<name>`
    command plus the `archived/CLAUDE.md` table-row text (`| Archived | Replaced by | When |` —
    the existing convention), plus the evidence line (zero invocations across N sessions spanning
    D1..D2; skill age M days). The miner never runs `git mv`, never edits `archived/CLAUDE.md`,
    never touches `user/skills/`.
  - **B — bare never-invoked list:** pushes the clerical assembly back onto the operator, which
    is the exact friction class this cluster of features exists to remove.
- **Recommendation:** A — proposal ergonomics without any write authority; the operator's paste
  is the deliberate act, and the `archived/` audit trail stays intact by construction.
- **Resolution:** Auto-accepted A; the constraint itself is operator-set, this is only its output
  formatting.

### D9. Read-only invariant, stdlib-only, test parity with the sibling miner

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What safety contract does the new script carry?
- **Options:**
  - **A — the full toolify-miner contract:** stdlib-only; opens every log in read mode only;
    never writes, renames, or deletes under the logs dir OR under `user/skills/` /
    `repos/*/.claude/skills/`; `test_skill_usage_miner.py` mirrors
    `test_toolify_miner.py::_dir_hash` hash-before/after over BOTH the fixture log dir and a
    fixture skills tree; malformed JSONL lines skipped without crashing (same graceful-skip
    behavior as `_tool_calls_in_file`).
  - **B — trust-based read-only:** the sibling already set the stronger precedent; weakening it
    for the second miner invites drift.
- **Recommendation:** A — the two-tree hash assertion is this feature's version of the
  load-bearing invariant, and it is cheap.
- **Resolution:** Auto-accepted A; test/discipline internals.

## User Experience

```bash
# Full report (markdown): ranked usage + never-invoked + hygiene + toolify candidates
python3 ~/.claude/scripts/skill-usage-miner.py

# JSON for tooling; restrict the window; save alongside
python3 ~/.claude/scripts/skill-usage-miner.py --json --since 2026-04-01 --out usage.json
```

Report shape (markdown mode):

```
## Skill usage (corpus: 2025-11-02 → 2026-07-04, 412 sessions, workstation logs only)
| rank | skill | scope | skill-tool | slash | sessions | last seen | 30d |
|------|-------|-------|-----------|-------|----------|-----------|-----|
| 1 | commit | user | 0 | 143 | 98 | 2026-07-03 | 22 |
| 2 | execute-plan | user | 41 | 87 | 76 | 2026-07-02 | 18 |
...

## Never invoked (age-gated — candidates for deliberate archival)
- three-best-practices — 0 invocations across 412 sessions; skill age 214d
  propose: git mv user/skills/three-best-practices archived/user-skills/three-best-practices
  archived/CLAUDE.md row: | `user-skills/three-best-practices` | (none — retired unused) | <sha> |

## Hygiene (non-skill artifacts in skills trees)
- user/skills/sh.exe.stackdump — file, not a skill dir (crash dump)
- user/skills/remotion — symlink to C:/Users/... (unresolvable from repo)
- user/skills/local-site/, user/skills/teach/ — lowercase skill.md (contract expects SKILL.md)

## Toolify candidates (high-frequency prose skills — see toolify-bar.md)
- commit (143 slash invocations): run toolify-miner.py over invoking sessions

## Caveats (standing)
- Component-injected protocols and auto-invoke prose usage are NOT counted (false negatives).
- Cloud sessions are invisible to workstation logs; cloud-variant skills undercount.
- Zero count = investigate, never proof of deadness. Archival is a human act.
```

The operator reads, investigates anything surprising, and executes archival proposals by hand
(paste the `git mv`, add the `archived/CLAUDE.md` row, commit). On an empty corpus or a missing
logs dir the miner prints an explicit "no corpus found at <path>" report rather than an empty
table. Nothing about the pipeline changes; this tool is never on the state-script compute path.

## Technical Design

```
~/.claude/projects/**/*.jsonl                      claude-config repo (read-only)
 + <parent>/subagents/agent-*.jsonl                 user/skills/*/SKILL.md          (83)
        │ read-only (reused _iter_log_files)        repos/*/.claude/skills/*/SKILL.md (29)
        ▼                                                   │ inventory glob + frontmatter name
  skill-usage-miner.py ◀────────────────────────────────────┘
        │  detector 1: assistant tool_use name=="Skill" → input["skill"] (value-preserving)
        │  detector 2: user-turn text  <command-name>(/[\w:-]+)</command-name>
        │  join on skill name; timestamps → last-seen / windows; git log → skill age (D3)
        ▼
  ranked report (markdown/JSON, stdout or --out) — usage · never-invoked · hygiene · toolify links
```

- **Corpus walk:** import `toolify-miner.py` via `importlib.util.spec_from_file_location` and call
  its `_iter_log_files(logs_dir)` (top-level + subagent transcripts, sorted, read-mode only).
  Default `--logs ~/.claude/projects`, same as the sibling.
- **Extraction:** a value-preserving reader per file — for each JSON line, `type == "assistant"`
  yields Skill-tool hits (`block["name"] == "Skill"` → `block["input"]["skill"]`, normalized to
  the bare skill name with any `plugin:` prefix and leading `/` stripped); `type == "user"` text
  content is scanned with the `digest_sessions.py:125` regex. Each hit records
  (skill, detector, session file, timestamp, project dir).
- **Inventory:** glob the two skills trees for `SKILL.md`, record scope (`user` / `repo:<name>`).
  *(Implementation-time correction, live-validated 2026-07-04:)* the inventory keys by the **dir
  name**, not the frontmatter `name:` — the dir name is the invocation identity (`/foo` dispatches
  by dir; both detectors record that form), and several real skills carry a human-title
  frontmatter name (`name: Error Resolver`) that would break the join AND the proposal paths. A
  missing `name:` (malformed header) and a frontmatter/dir-name mismatch are both flagged in
  Hygiene. Names not in the inventory but seen in logs are reported in an
  `## Unknown invocations` section (renamed/archived/plugin skills) rather than dropped.
- **Attribution (D4):** repo-scoped rows also report the share of hits whose project-dir slug
  matches their repo — labeled heuristic.
- **Never-invoked gate (D3):** for zero-count inventory rows only, one
  `git log --follow --diff-filter=A --format=%cs -- <SKILL.md>` subprocess against the
  claude-config checkout (the miner runs from the repo; a failure degrades to "age unknown —
  age gate not applied", never a crash).
- **House invariants honored:** stdlib-only Python; READ-ONLY over the logs dir and both skills
  trees (two-tree hash test, D9); no queue/marker/sentinel interaction whatsoever; deterministic
  output ordering (count desc, then name) so diffs of saved reports are stable; the only writes
  are stdout and an explicit `--out` path.
- **Deliberate non-goals:** no archival execution (D8), no toolify invocation (D7), no cloud-log
  ingestion (D4), no prose-mention fuzzy matching (D2-C).

## Implementation Phases

- **Phase 1 — Corpus walk + detectors + user-level inventory + ranked table.** Sibling script,
  importlib reuse of `_iter_log_files`, both detectors with separate columns, distinct-session
  and last-seen fields, markdown+JSON renderers, the standing-caveats block, and
  `test_skill_usage_miner.py` with fixture transcripts (Skill tool_use, command-name markers,
  subagent files, malformed lines) plus the two-tree read-only hash test.
- **Phase 2 — Scope + windows.** Repo-scoped inventory with per-repo attribution labels (D4);
  `--since` + the recent-window column; the git-age gate and the age-gated never-invoked list
  (D3). Fixture: a zero-count skill younger than the corpus must NOT be flagged.
- **Phase 3 — Hygiene sweep + archival proposal blocks.** The D5 rule over both trees (fixture
  trees reproducing all four real classes: stray file, dangling symlink, case-variant
  dispatcher, missing dispatcher); D8 proposal blocks with `archived/CLAUDE.md`-convention row
  text. Validate against the live repo: the four known findings above appear, and nothing else
  false-positives.
- **Phase 4 — Toolify cross-links + docs.** The D7 annotate-only section with a documented
  frequency threshold; `## Unknown invocations`; doc rows in `user/scripts/CLAUDE.md` and the
  root `CLAUDE.md` script table; a pointer from `user/skills/CLAUDE.md` to the audit tool.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Skill-tool hits counted | Fixture transcript with `Skill` tool_use blocks (incl. subagent file) | Correct per-skill counts + distinct sessions | `test_skill_usage_miner.py` |
| Slash markers counted | Fixture user turns with `<command-name>/foo</command-name>` | Counted under detector 2, separate column | `test_skill_usage_miner.py` |
| Read-only both trees | Full run over fixture logs + fixture skills tree | Both dir hashes byte-identical before/after | mirrored `_dir_hash` test |
| Never-invoked age gate | Zero-count skill younger than corpus vs older | Young skill absent from list; old skill present with age | Phase 2 fixture |
| Hygiene findings exact | Run against the live repo | Flags `sh.exe.stackdump`, `remotion` symlink, `local-site`/`teach` case-variants; no other user-skill false positives | manual operator check |
| Proposals never executed | Full run on a real checkout | `git status` clean afterward (report-only; `--out` outside the trees) | manual + test asserting no writes |
| Unknown invocations surfaced | Fixture log invoking a non-inventory skill | Row in `## Unknown invocations`, not silently dropped | `test_skill_usage_miner.py` |
| Malformed corpus tolerated | Corrupt JSONL line; missing logs dir | No crash; explicit empty-corpus message | `test_skill_usage_miner.py` |
| Deterministic output | Same fixture, two runs | Byte-identical report (given fixed `--since`) | diff test |

## Open Questions

All four product-behavior decisions were resolved by the operator on 2026-07-04 (each at its
recommended option — see the per-decision `Resolution` entries above):

- **D3 — window semantics:** RESOLVED → A (full corpus + `--since` + 30-day recency column;
  never-invoked gated by git-derived skill age).
- **D4 — v1 scope:** RESOLVED → A (both scopes inventoried; heuristic per-repo attribution;
  workstation logs only, cloud-variant skills annotated as cloud-biased undercount).
- **D6 — report destination/cadence:** RESOLVED → A (on-demand stdout + optional `--out`; no
  auto-wiring).
- **D7 — toolify cross-feed:** RESOLVED → A (annotate-only cross-links to the bar doc).
- **Deferred empirical checks (implementation-time, not decisions):** confirm on the live corpus
  that Skill-tool `tool_use` blocks record the skill name under `input["skill"]` across current
  and older transcript formats (and whether plugin-namespaced names appear); measure a full-corpus
  run's wall time on the real `~/.claude/projects` (tens of MB per busy session — decide whether a
  size-guard or progress line is warranted); verify the `<command-name>` marker survives in
  compacted-session continuations; check whether any repo-scoped skill name collides with a
  user-level name (would need scope-qualified counting).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: `toolify-miner.py`'s read-only miner contract and
  `mine-sessions`' documented transcript anatomy + field-proven detector regex.
- `user/skills/mine-sessions/SKILL.md` + `scripts/digest_sessions.py` — transcript record anatomy,
  the subagent-transcript location, and the slash-command marker regex reused verbatim.
- `docs/features/unified-pipeline-orchestrator/toolify-bar.md` — the bar the report cross-links
  high-frequency skills to (annotate-only).
- `archived/CLAUDE.md` — the deliberate-archival convention the proposal blocks target.
- Sibling: `docs/features/toolify-auto-promotion/SPEC.md` — deliberately decoupled consumer of the
  same corpus; this report may point at it, never invoke it.
