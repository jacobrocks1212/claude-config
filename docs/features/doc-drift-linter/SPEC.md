# Doc-Drift Linter (CLAUDE.md vs. Reality) — Feature Specification

> The CLAUDE.md hooks/scripts tables are hand-maintained claims about `settings.json` and the
> filesystem, and drift has already happened once (`worktree-claude-doc-drift`). A stdlib-only
> lint script (`user/scripts/doc-drift-lint.py`, sibling of `lint-skills.py`) cross-checks four
> structured-claim surfaces mechanically — the root `CLAUDE.md` hooks table against
> `user/settings.json` hook registrations (including asserting the deliberately NOT-registered
> rows stay documented as such), the root + `user/scripts/CLAUDE.md` script tables against
> `user/scripts/` files on disk, the root Coupled Skill Pairs table against
> `user/scripts/lazy-parity-manifest.json`, and `manifest.psd1` Repos entries against
> `repos/<name>/` dirs — catching drift at lint time instead of in retros. Deliberate
> divergences are annotated in place with a single SSOT marker constant
> (the `<!-- verification-only -->` precedent).

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; baseline-locked via internal codebase
survey 2026-07-04 (Gemini research skipped per operator direction — see RESEARCH_SUMMARY.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **existing artifacts read
> read-only**, not sibling specs:
> - Root `CLAUDE.md` (`## Hooks` table, `## Scripts` table, `### Coupled Skill Pairs` table) and
>   `user/scripts/CLAUDE.md` (`## Files in this directory` table) — the claim surfaces.
> - `user/settings.json` `hooks` object — the registration reality for the hooks check.
> - `user/scripts/lazy-parity-manifest.json` (`pairs[].canonical` / `pairs[].derived`) — the
>   coupled-pair reality (owned by `lazy_parity_audit.py`; this linter only reads it).
> - `manifest.psd1` `Repos` block + the `repos/` directory tree — the symlink-mapping reality.
> - `lint-skills.py` — the shape precedent (stdlib-only sibling validator, `--repo-root`-style
>   local invocation, findings-to-stdout, non-zero exit on findings).

---

## Executive Summary

Nested CLAUDE.md files are the orientation layer agents read first; when their tables lie (a hook
documented as registered but unwired, a script renamed, a coupled pair missing from the sync
table, a manifest entry pointing at a repo dir that no longer exists), agents act on stale claims.
Today the only detector is a human retro — `worktree-claude-doc-drift` is the recorded incident,
and the codebase survey for this feature found live drift of every class the stub predicted:
a hooks-table row for a hook that is registered nowhere (`block-work-repo-git-writes.sh`), a
hooks-table trigger that names the wrong matcher (`pr-review-cache-guard.sh` documented as Bash,
registered on Read), a registered hook with no table row (`load-branch-docs-context.sh`), three
parity-manifest pairs absent from the Coupled Skill Pairs table (the whole bug axis), and a
`repos/algobooth/` dir with no `manifest.psd1` entry (deliberate — commit `47b4fa4` — and thus
exactly the case the divergence-annotation convention exists for).

The fix is mechanical: the claims are already structured (markdown tables + one JSON manifest +
one PowerShell data file), so a deterministic stdlib-only linter can extract each claim and test
it against the artifact it describes. Prose claims are explicitly out of scope — no NLP, no
heuristics over sentences; if a claim matters enough to gate on, it belongs in a table. The linter
follows the house validator pattern (`lint-skills.py`): runnable locally, findings on stdout,
exit 0 clean / 1 findings / 2 malformed-input, `--repo-root` for out-of-tree invocation. It never
mutates anything. Deliberate divergences carry an in-place marker (module-constant SSOT, like
`<!-- verification-only -->`) so the linter distinguishes "stale claim" from "documented
exception" without a side-channel allowlist file.

Serving the mission's **effective** criterion (docs agents act on are certified, not narrated)
and **best-practice-aligned** (gates that refuse early over retros that catch late).

## Design Decisions

### D1. Machine-checkable claims v1 = the four named cross-checks; prose out of scope

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** Which CLAUDE.md claims are machine-checkable vs. prose-only?
- **Options:**
  - **A — the four structured cross-checks (recommended):**
    1. **hooks:** root `CLAUDE.md` `## Hooks` table ↔ `user/settings.json` hook registrations.
       Bidirectional: a row claiming a trigger must be registered under that event with exactly
       the documented matchers; a row claiming **NOT registered** must appear in no registered
       command (the two deliberately-unwired `.ps1` rows stay documented as such and are
       asserted, not exempted); a registered hook-script with no table row is drift; a documented
       hook script must exist on disk (`user/hooks/` or `user/scripts/`).
    2. **scripts:** root `CLAUDE.md` `## Scripts` table + `user/scripts/CLAUDE.md`
       `## Files in this directory` table ↔ `user/scripts/` on disk. Doc→disk only: every
       documented entry must exist (trailing `/` rows are directory checks). Disk→doc is NOT
       checked — both tables are curated, not exhaustive (documented v1 limitation).
    3. **coupled pairs:** root `CLAUDE.md` `### Coupled Skill Pairs` table ↔
       `user/scripts/lazy-parity-manifest.json` `pairs[]`. Bidirectional over unordered
       `{canonical, derived}` path pairs.
    4. **manifest:** `manifest.psd1` `Repos` entries ↔ `repos/<name>/` dirs. Forward: every
       non-`Alias` entry must have a `repos/<name>/` dir; every `Alias` must name an existing
       entry key (alias entries have no dir by design). Reverse: every `repos/<name>/` dir must
       have an entry (marker-exemptable — see D2).
  - **B — A plus prose-claim extraction** (e.g. the per-repo hook-scoping note, the
    "Deliberately unwired" prose in `user/hooks/CLAUDE.md`): catches more, but requires NLP-ish
    sentence parsing the stub explicitly rejects ("structured-claim extraction from markdown
    tables only"), and false positives would train agents to ignore the linter.
- **Recommendation:** A — every recorded drift incident lands in one of the four classes, and
  each check compares two deterministic artifacts with zero inference.
- **Resolution:** A — operator-approved 2026-07-04 — recommended option taken.

### D2. Deliberate-divergence annotation: one SSOT marker constant, carried in-place

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** How does a *deliberate* doc↔reality divergence tell the linter "this is known and
  intended" without silencing genuine drift?
- **Options:**
  - **A — in-place marker on the claim line (recommended):** a module constant
    `DIVERGENCE_MARKER = "doc-drift:deliberate-divergence"` (SSOT — the
    `<!-- verification-only -->` precedent from the PHASES.md contract). In markdown it rides an
    HTML comment appended to the table row
    (`<!-- doc-drift:deliberate-divergence: <reason> -->`); in `manifest.psd1` (not markdown) the
    SAME token rides a `#` comment naming the exempted subject (e.g. `algobooth`). A finding
    whose claim line (or, for a missing-row finding, whose section/manifest comment naming the
    subject) carries the marker is reported as an exempted divergence, not drift. The reason text
    is free-form and human-owned.
  - **B — a side-channel allowlist file:** central, but detaches the exemption from the claim it
    excuses — the exact drift pattern this feature exists to kill.
- **Recommendation:** A — the annotation lives where the reader reads the claim, and the marker
  is greppable + constant-owned.
- **Resolution:** A — operator-approved 2026-07-04 — recommended option taken.

### D3. Scope v1: this repo's root `CLAUDE.md` + `user/scripts/CLAUDE.md` + `user/hooks/CLAUDE.md`

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** This repo only, or per-repo `.claude/` CLAUDE.md files too?
- **Options:**
  - **A — this repo's three docs (recommended):** root `CLAUDE.md` (hooks, scripts,
    coupled-pairs tables), `user/scripts/CLAUDE.md` (files table), `user/hooks/CLAUDE.md`
    (scanned; it currently carries no structured tables, so it contributes zero claims in v1 —
    honest no-op, documented). Per-repo `.claude/` CLAUDE.md files are a **documented vN**: their
    claims cross a repo boundary (they describe *other* repos' trees and settings), which needs a
    per-repo reality resolver this v1 deliberately does not grow.
  - **B — all CLAUDE.md files under `repos/` too:** broader, but each repo's reality lives
    outside this repo's tree — un-checkable in CI or a worktree without the live machine.
- **Recommendation:** A — most conservative scope that covers every recorded drift incident.
- **Resolution:** A — operator-approved 2026-07-04 — recommended option taken.

### D4. Shape: stdlib-only `user/scripts/doc-drift-lint.py`, exit 0/1/2, `--repo-root`; CI wiring deferred

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** Where does the linter live and how is it invoked?
- **Options:**
  - **A — sibling of `lint-skills.py` (recommended):** `user/scripts/doc-drift-lint.py`,
    stdlib-only (json, re, pathlib, argparse), pure-read, runnable locally
    (`python3 user/scripts/doc-drift-lint.py [--repo-root <path>]`). Exit contract: `0` clean
    (exempted divergences allowed), `1` ≥1 drift finding, `2` malformed input (missing/unreadable
    claim source, unparseable JSON/psd1/table). Findings print one line each
    (`<check>: <subject> — <message> [<doc-file>]`) plus a summary line. CI wiring is **deferred
    to the `claude-config-ci` feature** (out of scope here); a pytest case that runs the linter
    against this repo root keeps it enforced by the existing gate suite in the meantime.
  - **B — fold into `lint-skills.py`:** fewer entry points, but `lint-skills.py` is
    skills-domain-specific and its flags/exit semantics are already load-bearing in three
    orchestrators — additive risk for no gain.
- **Recommendation:** A.
- **Resolution:** A — operator-approved 2026-07-04 — recommended option taken.

### D5. `.psd1` reading: a minimal tolerant parser for THIS manifest's shape, not a PowerShell parser

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How does stdlib Python read `manifest.psd1` (no PowerShell exists in cloud/CI)?
- **Options:**
  - **A — minimal shape-bound parser (recommended):** a small line/regex walker that understands
    exactly what this manifest uses — `@{ key = value }` hashtables, `@( ... )` arrays,
    single-quoted strings, `'name' = @{ ... }` nested one level under `Repos`, `#` comments —
    and extracts `{repo_name: {Path?, Alias?}}` plus the file's comment lines (for D2 markers).
    **Honest about limitations:** anything outside that shape (double-quoted strings with
    escapes, expressions, multi-level nesting beyond `Repos.<name>`) → a `malformed` finding +
    exit 2, never a silent guess.
  - **B — a general PowerShell data-file parser:** out of all proportion (PowerShell tokenizer in
    stdlib Python), and unneeded — the manifest's shape is stable and owned by this repo.
- **Recommendation:** A — parse the file we have, refuse loudly on the file we don't.
- **Resolution:** Auto-accepted A; internal parsing strategy with an explicit fail-closed
  malformed contract.

### D6. Finding model + output: deterministic, pure-read, marker-aware

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What does one finding look like and what does the linter never do?
- **Options considered / resolution (auto-accepted):**
  - Each finding carries `check ∈ {hooks, scripts, coupled-pairs, manifest}`,
    `kind ∈ {drift, malformed}`, the doc file, a subject token (hook/script/pair/repo name), and
    a one-line message naming both sides of the mismatch (claim vs. reality) — the corrective
    action is legible from the message alone.
  - Marker-exempted findings are counted and listed under an `exempted divergences` summary
    (visible, never silent) but do not affect the exit code.
  - The linter is **pure-read**: it never edits docs, never auto-fixes, never writes state. It is
    deterministic and byte-stable for a given tree (no wall-clock in output).
  - Output is plain text (the `lint-skills.py` convention); a `--json` machine mode is a
    documented vN, not v1.
- **Resolution:** Auto-accepted; internal contract with no operator-visible surface beyond the
  printed findings.

## User Experience

The "users" are the operator and the autonomous pipeline's meta/hardening cycles.

```bash
# From the repo root (or anywhere, with --repo-root):
python3 user/scripts/doc-drift-lint.py --repo-root .

# Clean tree:
doc-drift-lint: 4 checks, 0 drift findings, 1 exempted divergence
  exempted: manifest: algobooth — repos/algobooth/ has no Repos entry (marker present)
# → exit 0

# Drifted tree:
hooks: block-work-repo-git-writes.sh — documented as 'PreToolUse (Bash)' but registered nowhere in user/settings.json [CLAUDE.md]
coupled-pairs: user/skills/lazy/SKILL.md <-> user/skills/lazy-bug/SKILL.md — in lazy-parity-manifest.json but missing from the Coupled Skill Pairs table [CLAUDE.md]
doc-drift-lint: 4 checks, 2 drift findings, 1 exempted divergence
# → exit 1

# Malformed input (e.g. manifest.psd1 outside the supported shape):
manifest: manifest.psd1 — unparseable at line 42: <line> (minimal .psd1 parser — see doc-drift-lint.py header)
# → exit 2
```

Annotating a deliberate divergence (D2):

```markdown
| `some-hook.sh` | **NOT registered** (…) | … <!-- doc-drift:deliberate-divergence: wired per-repo only --> |
```

```powershell
# doc-drift:deliberate-divergence: algobooth — live repo deleted (47b4fa4); repos/algobooth/.claude
# stays tracked as the cloud halves of the /lazy coupled pairs.
```

## Technical Design

```
claim surfaces (docs)                        reality surfaces
 CLAUDE.md ## Hooks table          ◄─check─► user/settings.json hooks{event:[{matcher,hooks[]}]}
 CLAUDE.md ## Scripts table        ◄─check─► user/scripts/* on disk
 user/scripts/CLAUDE.md files tbl  ◄─check─►     (doc→disk existence only)
 CLAUDE.md ### Coupled Skill Pairs ◄─check─► user/scripts/lazy-parity-manifest.json pairs[]
 manifest.psd1 Repos block         ◄─check─► repos/<name>/ dirs
                     │
                     ▼
      doc-drift-lint.py (stdlib, pure-read)
        findings → stdout; exit 0/1/2; DIVERGENCE_MARKER exemptions
```

- **Markdown table extraction:** a generic `parse_markdown_tables(text)` (pipe-row splitter,
  separator-row skip, raw line retained per row for marker detection) + section-anchored lookup
  (`table under the '## Hooks' heading`). Cell tokens of interest are backtick-quoted filenames /
  paths; the Trigger cell parses to `(event, {matchers})` or a `NOT registered` claim.
- **Hooks reality extraction:** walk `settings.json` `hooks` → for each event/matcher/command,
  extract hook-script basenames via a `hooks/<name>.(sh|ps1)` path match (inline `bash -c`
  commands with no hooks-path reference are ignored — documented limitation). Matcher strings
  split on `|` to a set; doc matcher lists split on `,`/`|`. Comparison is set-equality per
  basename over `(event, matchers)`.
- **Coupled-pairs comparison:** doc rows → frozensets of the two backticked paths in the Files
  cell; manifest → frozensets of `{canonical, derived}` per `pairs[]` entry; symmetric
  difference is drift. A missing-doc-row finding is exemptable by a marker comment inside the
  Coupled Skill Pairs section naming either path (D2's missing-row case).
- **Manifest check:** D5 parser → entries + comments; forward/reverse dir checks; reverse
  findings exemptable by a marker `#` comment naming the dir.
- **No state, no writes, no network.** Not on any state-script compute path; never imports
  `lazy_core` (nothing it needs — keeps the linter dependency-free and trivially runnable).
- **Tests:** `user/scripts/test_doc_drift_lint.py` (pytest, hermetic tmp-tree fixtures per check
  class: drift-present and clean cases, divergence-marker exemption, malformed exit 2) plus a
  self-check case running the linter against THIS repo root (must be exit 0 — the linter gates
  its own home).

## Implementation Phases

- **Phase 1 — Linter core + tests (~1 session).** `doc-drift-lint.py` (table parser, psd1
  mini-parser, four checks, CLI, exit codes, marker exemption) built TDD against hermetic
  fixtures in `test_doc_drift_lint.py`. Proven done: new pytest suite green; existing gate suite
  untouched.
- **Phase 2 — Fix the live drift this repo has (~1 session).** Run the linter against the repo;
  fix genuine drift in the docs (hooks-table corrections, missing coupled-pair rows, missing hook
  row) and annotate the deliberate `algobooth` divergence with the D2 marker in `manifest.psd1`.
  Proven done: `doc-drift-lint.py --repo-root .` exit 0 with the drift fixes as ordinary doc
  commits — the feature proving itself.
- **Phase 3 — Docs + finalize (~0.5 session).** Script-table rows for `doc-drift-lint.py` in
  root `CLAUDE.md` + `user/scripts/CLAUDE.md` (which the scripts check then verifies); full gate
  suite. Proven done: all gates green + linter still exit 0.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Hooks: documented-but-unregistered | Fixture row claiming `PreToolUse (Bash)` with empty settings | 1 hooks drift finding; exit 1 | `test_doc_drift_lint.py` |
| Hooks: registered-but-undocumented | Fixture settings registering a hook with no table row | 1 hooks drift finding | `test_doc_drift_lint.py` |
| Hooks: matcher mismatch | Doc `(Bash)` vs registered matcher `Read` | 1 hooks drift finding naming both sides | `test_doc_drift_lint.py` |
| Hooks: NOT-registered rows asserted | The two unwired `.ps1` rows + empty `PostToolUse` | clean; registering one flips to drift | `test_doc_drift_lint.py` |
| Scripts: documented file missing | Table row for a deleted script | 1 scripts drift finding; dir rows (`x/`) check dirs | `test_doc_drift_lint.py` |
| Coupled pairs: both directions | Manifest pair absent from doc table, and vice versa | 1 drift finding each way | `test_doc_drift_lint.py` |
| Manifest: entry↔dir both directions + Alias | Entry w/o dir; dir w/o entry; alias to missing key | 1 drift finding each | `test_doc_drift_lint.py` |
| Marker exemption | Marker on row / psd1 comment | finding reported as exempted; exit unaffected | `test_doc_drift_lint.py` |
| Malformed inputs | Missing settings.json / bad JSON / out-of-shape psd1 | `malformed` finding; exit 2 | `test_doc_drift_lint.py` |
| Self-check | Linter vs THIS repo at HEAD | exit 0 (post Phase-2 doc fixes) | pytest self-check + manual run |

## Open Questions

None — all four stub questions resolved above (D1–D4, each
`operator-approved 2026-07-04 — recommended option taken`); D5–D6 auto-accepted
mechanical-internal. Documented vN follow-ups (not blocking): per-repo `.claude/` CLAUDE.md
scope (D3), `--json` output mode (D6), disk→doc completeness for the scripts tables (D1.2),
CI wiring via `claude-config-ci` (D4).

## Research References

- `RESEARCH_SUMMARY.md` — internal codebase survey (Gemini deep research intentionally skipped by
  operator directive, 2026-07-04): live-drift inventory across all four check classes.
- `user/scripts/lint-skills.py` — the sibling-validator shape precedent.
- `user/scripts/lazy-parity-manifest.json` / `lazy_parity_audit.py` — coupled-pair reality
  source (read-only consumer relationship).
- `docs/bugs/worktree-claude-doc-drift` — the recorded drift incident motivating the feature.
- `<!-- verification-only -->` SSOT-constant precedent (PHASES.md Runtime Verification rows) —
  the D2 marker convention model.
