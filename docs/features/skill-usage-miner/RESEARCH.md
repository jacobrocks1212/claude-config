# Research — Skill Usage Miner + Dead-Weight Audit

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **`user/scripts/toolify-miner.py`** — the corpus-walking layer is directly reusable:
  `_iter_log_files` yields every `*.jsonl` under the logs dir (top-level sessions plus
  `subagents/agent-*.jsonl`), sorted, opened read-only, with malformed lines skipped in
  `_tool_calls_in_file`. The critical *non*-reuse finding: `_normalize_call` deliberately elides
  all argument values (that is the whole point of shape signatures), but the skill name lives in
  the `Skill` tool's `input["skill"]` **value** — so this miner needs its own value-preserving
  extractor over the same walk. The SPEC's reuse claims are scoped accordingly (D1).
- **`user/skills/mine-sessions/SKILL.md` + `scripts/digest_sessions.py`** — the strongest prior
  art in the repo, discovered during desk research. It documents the transcript anatomy this miner
  depends on: one JSONL per session under `~/.claude/projects/<encoded-cwd>/`; worktrees get
  sibling project dirs (match all dirs containing the repo slug); subagent internal turns live in
  `<parent-uuid>/subagents/agent-*.jsonl`, NOT inline; and slash-command invocations appear in
  user-message text as `<command-name>/foo</command-name>`. Its `digest_sessions.py:125` already
  parses that marker with `<command-name>(/[\w:-]+)</command-name>` — reused verbatim as
  detector 2. What it does NOT provide: per-skill attribution joined against a repo inventory,
  never-invoked detection, hygiene sweeping, or a persisted rankable report — the gap this
  feature fills. (Its tool-use histogram counts the literal tool name `Skill` without reading
  which skill.)
- **Live inventory + hygiene ground truth (verified 2026-07-04):** 86 top-level dirs in
  `user/skills/`, of which 83 contain `SKILL.md`; the three exceptions are `_components/`
  (legitimate) and `local-site/` + `teach/` (lowercase `skill.md` — invisible to the frontmatter
  contract on case-sensitive filesystems). Non-dir strays: `sh.exe.stackdump` (530-byte crash
  dump) and `remotion` (symlink → `C:/Users/JacobMadsen/source/repos/remotion-skills/...`,
  dangling from the repo's perspective). Repo-scoped skills: 29 (2 under
  `repos/algobooth/.claude/skills/`, 27 under `repos/cognito-forms/.claude/skills/`). These four
  hygiene classes are exactly the Phase-3 fixture set.
- **`archived/CLAUDE.md`** — the deliberate-archival convention: move (never delete) into
  `archived/`, add a table row (`| Archived | Replaced by | When |`) so supersession stays
  traceable. The report's proposal blocks (D8) emit paste-ready text in this exact shape; the
  miner itself never executes a move — the stub's "proposes, never auto-archives" constraint is
  operator-set.
- **`user/skills/CLAUDE.md`** — defines what counts as a skill (a `<name>/SKILL.md` dispatcher
  with `name:` frontmatter) and the user-level vs repo-scoped split; the inventory and hygiene
  rules are its mechanical enforcement.
- **`user/scripts/lint-skills.py`** — considered as a home for the hygiene sweep (D5); its
  surface (`lint_skill` / `lint_projected` / `lint_capabilities` / `lint_planner_resolution`) is
  injection-pattern validation with exit-code semantics existing flows rely on, so v1 keeps the
  inventory checks in the report and defers any promotion into the linter.
- **`lazy-queue-doc.py` precedent** — the house pattern for a pure-read sibling renderer with a
  deterministic, byte-stable output; this miner follows the same shape (deterministic ordering,
  no wall-clock surprises beyond timestamps derived from the corpus itself).
- **Falsifiability conventions** — the harness's insistence on honest evidence (receipt-gated
  completion, defer-vs-skip) motivated the age-gated never-invoked flag (D3) and the standing
  false-negative caveats (D2): a zero count is only reported as actionable when the skill had
  genuine opportunity to be invoked.

## External prior art & concepts

Training-knowledge, not live research:

- **Dead-code detection (vulture, coverage.py, JaCoCo, tree-shaking)** — the canonical lesson:
  static/dynamic usage analysis always has false negatives (reflection, dynamic dispatch), so
  responsible tools report candidates for human review rather than deleting. Directly analogous:
  component injection and auto-invoke prose are this system's "reflection", hence
  proposes-never-auto-archives.
- **Feature-flag debt cleanup practice (e.g. as popularized around LaunchDarkly/Unleash)** — stale
  flags are found by *usage telemetry joined with age* ("no evaluations in 90 days AND created
  > 90 days ago"), the same two-signal gate as D3's age-gated never-invoked flag.
- **Package/API usage telemetry (npm download stats, crates.io, internal API-deprecation
  scorecards)** — ranked usage tables drive deprecation conversations but never auto-remove;
  undercounting caveats (mirrors, vendoring) are always carried alongside — the model for the
  standing caveats block.
- **Log-based product analytics** — counting distinct sessions rather than raw hits to avoid one
  loop inflating a rank (the miner reports both), and windowed columns for recency trends.
- **Repository-hygiene linters (pre-commit, editorconfig-checker)** — precedent for flagging
  artifacts that don't belong (crash dumps, broken symlinks, case-variant filenames) as a
  report/lint concern; the case-variant `skill.md` class is a classic case-insensitive-filesystem
  hazard (authored on Windows, broken on Linux).

## Alternatives analysis

- **Merged tool vs sibling (D1).** One CLI over the shared corpus was weighed and rejected: the
  two miners have different units (sequence signatures vs skills), different joins (none vs repo
  inventory), different bars (deterministic-only vs age-gated zero-usage), and different output
  contracts. The shared piece is ~the corpus walk, importable via the already-proven
  `importlib.util.spec_from_file_location` pattern. A shared `toolify_common.py` module is the
  right refactor at the *third* consumer, not the second.
- **Detector set (D2).** Slash-marker-only would miss programmatic/proactive Skill-tool
  dispatches; Skill-tool-only would miss operator-typed commands in older flows; fuzzy prose
  matching drowns in false positives given skill names like `fix`, `commit`, `push`, `stage`.
  Two exact detectors with separate columns preserve the operator/agent split as signal.
- **Window semantics (D3).** A fixed rolling window is simpler but weakens the headline claim the
  archival proposal rests on. The age gate (git first-commit date vs corpus span) is one cheap
  subprocess per zero-count skill and converts "no signal" into "no signal despite opportunity" —
  the difference between a defensible proposal and a false one for any newly added skill.
- **Cloud coverage (D4).** Ingesting cloud-session logs would require sync infrastructure that
  does not exist; pretending coverage instead of labeling the bias would produce actively wrong
  archival proposals for the cloud-variant skills. Honest scoping (workstation-visible logs,
  cloud-biased-undercount annotations on the known cloud skills) is the only v1 that tells the
  truth.
- **Hygiene placement (D5).** Extending `lint-skills.py` couples new failure modes into existing
  consumers of its exit code; the report section costs nothing and lets the rule's false-positive
  rate be observed before it gates anything.
- **Report cadence (D6).** A committed always-current doc (the `LAZY_QUEUE.md` pattern) fits
  state that downstream surfaces *read*; usage stats churn per session and have no downstream
  reader — commit noise with no consumer. On-demand matches the deliberate-archival cadence.

## Pitfalls & risks

- **False archival proposals** — the feature's worst outcome: proposing a load-bearing skill for
  archival because its usage is invisible (component-injected, auto-invoke, cloud-side). Defenses:
  the two-detector design, the age gate, the standing caveats block, cloud-variant annotations,
  and — decisively — the operator constraint that archival is always a human act with an
  `archived/` audit row.
- **Corpus scale** — busy sessions run to tens of MB; a full walk is IO-bound. The extractor reads
  line-by-line (never whole-file loads), and a deferred check measures real wall time before
  deciding whether a progress line or size guard is needed. Session logs may also be rotated or
  pruned; the report prints the observed corpus span so a short span self-discloses.
- **Name ambiguity** — repo-scoped vs user-level name collisions (none observed today; a deferred
  check confirms) and renamed skills (`write-plan` was once `mobile`, per the `archived/` trail)
  make some historical invocations attribute to `## Unknown invocations` rather than the current
  name — surfaced, not silently dropped, but rank for recently renamed skills will read low.
- **Transcript-format drift** — the detectors are pinned to today's format (`tool_use` blocks,
  `<command-name>` markers). Format changes degrade counts silently; the `## Unknown
  invocations` section and the caveat block mitigate, and fixtures document the assumed shapes so
  a drift shows up as a fixture-vs-live discrepancy.
- **Hygiene false positives** — an intentional local symlink (the `remotion` class) must be
  flagged neutrally, not condemned; the rule reports facts (symlink, target unresolvable from
  repo) and leaves classification to the operator.
- **Dead-weight check on itself** — this audit tool is subject to its own standard: if its report
  never changes an archival/toolify decision within a few review cycles, it is dead weight and
  should be proposed for `archived/` by the same convention it emits. Its measurable outputs
  (archival proposals accepted, hygiene items fixed, toolify hints pursued) are the falsifiers.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 sibling script reusing `_iter_log_files` via importlib | Sibling `skill-usage-miner.py` | High |
| D2 detectors | Skill-tool + slash-marker, separate columns, standing caveats | High |
| D3 window semantics (OPEN) | Full corpus + `--since` + 30d column; age-gated never-invoked | Medium-high |
| D4 scope (OPEN) | Include repo-scoped skills; workstation logs only, labeled | Medium-high |
| D5 hygiene sweep | Report section, rule over both trees; linter promotion deferred | High |
| D6 destination/cadence (OPEN) | On-demand stdout + `--out`; no auto-wiring | Medium-high |
| D7 toolify cross-feed (OPEN) | Annotate-only links to the bar doc | High |
| D8 archival proposal shape | Paste-ready `git mv` + `archived/CLAUDE.md` row; never executed | High |
| D9 safety contract | Read-only over logs + skills trees, two-tree hash test, stdlib-only | High |
