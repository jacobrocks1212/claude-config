# Code↔Doc Provenance Linkage (Implementation Ledger) — Feature Specification

> Make the linkage between documentation and the code it governs a **byproduct of the agentic
> workflow**: at `__mark_complete__`/`__mark_fixed__`, distill each feature/bug into a small
> durable artifact (`IMPLEMENTED.md`: what shipped, which Locked Decisions drove it, why) and
> record the touched-file set from the cycle commits into a repo-level reverse index (file path →
> feature/bug slugs). Skills and cycle subagents consult the index before editing — "you're
> touching `lazy_core.py`; these 4 decision records govern it" — turning the docs corpus from a
> write-only archive into working memory. One deterministic producer, two triggers: the automatic
> completion-gate path and an operator-invocable manual path for out-of-pipeline work.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; must-have); fleshed
out via internal desk research 2026-07-04 (Gemini research skipped by operator directive — see
RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented data contracts, not
> sibling specs** (the mobile-queue-control pattern):
> - The completion gates — `lazy-state.py --apply-pseudo __mark_complete__` / `__mark_fixed__`
>   (`lazy_core.apply_pseudo`, the SINGLE author of every scripted completion write). The producer
>   extends this surface: it already holds the SPEC dir, the evidence sentinels, and the receipt
>   write at the exact moment the linkage is knowable.
> - `lazy_core.write_completed_receipt` — the receipt writer whose `provenance:` /
>   `completed_commit:` fields this feature reuses and finally populates.
> - The run/cycle markers' commit-tracking fields — `write_cycle_marker`'s `begin_head_sha` +
>   `commit_tally` snapshots and `write_run_marker`'s `work_branch` — the deterministic raw
>   material for the touched-file set.
> - The `## Locked Decisions` SPEC surface parsed by `lazy-state.py --gate-coverage`
>   (`lazy_core.gate_coverage`) — the distillate cites decision ids from the same canonical
>   surface, re-parsing nothing new.
> - Per-repo `.claude/` residency via `manifest.psd1` Repos scope (`DotClaudeFiles` /
>   `DotClaudeDirs`) — one candidate home for the reverse index (Decision D3).
> - **Peer, not dependency:** `doc-drift-linter` lints hand-written CLAUDE.md claims against
>   reality; this feature's lint (D10) checks a machine-written index against git. The two coexist.

---

## Executive Summary

The pipeline produces rich per-item docs (SPEC.md, PHASES.md, COMPLETED.md) but throws away the
one linkage it *knows deterministically at completion time*: which files the cycle commits touched
and which SPEC decisions drove them. Agents editing code later have no mechanical way to discover
the decision records that govern a file, so they re-derive — or contradict — past decisions. This
is the failure class the coupled-pair sync rules and `mcp-coverage-audit.md` guard against,
un-generalized: each of those is a hand-maintained, single-purpose "this doc governs that code"
link, and every new one costs a hardening round to discover and wire.

The fix is a **provenance producer** owned by the state scripts. When `lazy_core.apply_pseudo`
runs `__mark_complete__`/`__mark_fixed__` and the completion-integrity gate passes, it additionally
(a) writes a small `IMPLEMENTED.md` distillate into the item dir — what shipped, the Locked
Decision ids that drove it, why — assembled purely from surfaces the gate already parses, and
(b) merges the item's touched-file set (derived from per-cycle commit brackets the markers already
snapshot) into a committed per-repo reverse index. A **manual trigger** (CLI + skill) runs the SAME
producer against an arbitrary commit range or PR for teammate-authored work that never crosses a
completion gate — one writer, two triggers, so the index never forks into pipeline-shaped vs
manual-shaped entries. Consumers pay for the index only when they edit: a lookup surfaced at edit
time (Decision D6) tells an agent which decision records govern the file under its cursor.

This serves all three mission criteria: **efficient** (no re-derivation of past decisions; lookup
cost is one cheap read, paid only on relevant edits), **effective** (edits are made against the
real decision record, not a reconstruction), and **best-practice-aligned** (audit-grade provenance
on every completion — the receipt says *that* it shipped; the ledger says *what and why*).

## Design Decisions

### D1. Producer placement — one writer, two triggers

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where does the code that writes `IMPLEMENTED.md` + the index live, so the
  pipeline path and the manual path cannot diverge?
- **Options:**
  - **A — inline in the `__mark_complete__` branch:** extend the existing branch in
    `lazy_core.apply_pseudo` directly. Pros: zero new surface. Cons: the manual path would have to
    fake a pseudo-skill call (and pass its evidence gates) to reuse the code — forcing either a
    gate bypass or a fork.
  - **B — new `lazy_core.write_provenance(...)` helper, called from BOTH the
    `__mark_complete__`/`__mark_fixed__` branch and a new manual CLI:** the pseudo-skill branch
    calls it after the receipt write; a `--link-provenance` handler calls it with
    operator-supplied inputs. Pros: literal one-writer guarantee; shared by both pipelines for
    free (`lazy_core` is imported by `lazy-state.py` AND `bug-state.py`, so no coupled-pair mirror
    is owed); testable in `test_lazy_core.py`. Cons: one more `lazy_core` public helper.
  - **C — orchestrator prose step:** the skill wrappers author the files. Cons: violates the
    stub's operator constraint (deterministic script-owned, never LLM-inferred) outright.
- **Recommendation:** B — it is the only shape that satisfies "one writer, two triggers" as a
  structural fact rather than a convention, and it follows the house helper-placement rule
  (domain-agnostic writers live in `lazy_core.py`; see `user/scripts/CLAUDE.md`).
- **Resolution:** Auto-accepted B; helper placement is an invisible implementation choice with an
  established house rule.

### D2. Distillate schema — `IMPLEMENTED.md`, deliberately small, deterministically assembled

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What exactly goes in the distillate, and how is it produced without LLM inference?
  The stub locks the content triad (what shipped / which Locked Decisions / why) and the size
  constraint (SPECs are planning artifacts and go stale; "what exists and why" is the durable
  residue) — this decision fixes the file contract.
- **Options:**
  - **A — frontmatter + deterministic extract:** YAML frontmatter (`kind: implemented`,
    `feature_id`, `date`, `provenance` (D9), `derivation` (D4), `commits: [<shas>]`,
    `decisions: [<ids>]`) followed by a body assembled from surfaces the gate already parses: the
    SPEC's leading `>` summary paragraph (what shipped), the Locked-Decision id + title rows from
    the `--gate-coverage` surface (which decisions, why), and the receipt facts (validated-via,
    pass counts). Pros: byte-reproducible from on-disk state; zero new parsing (reuses
    `lazy_core.gate_coverage`'s decision enumeration); honest when a SPEC has no Locked-Decision
    surface (`decisions: []` + a body note). Cons: body quality is capped by SPEC quality.
  - **B — LLM-summarized body:** richer prose, but violates the deterministic-producer constraint
    for the pipeline path.
- **Recommendation:** A for the pipeline path. The manual path (D8) may carry an
  operator-approved drafted body, but it is written *through the same producer*, which owns the
  frontmatter and validates the schema either way. Register the schema in
  `user/skills/_components/sentinel-frontmatter.md` (and its AlgoBooth
  `check-docs-consistency.ts` `SENTINEL_SCHEMAS` mirror — keep the lockstep). `IMPLEMENTED.md` is
  a NEW filename touching no state-machine read path: `compute_state` never reads it, the
  `__mark_complete__` cleanup deletes only `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md`,
  and the `BLOCKED*` write-hook pattern does not match it — verified against
  `lazy_core.apply_pseudo` and `block-noncanonical-blocker-write.sh`.
- **Resolution:** Auto-accepted A; the operator already locked the content triad and smallness —
  the remaining schema choice is an internal file contract.

### D3. Reverse-index format + location per target repo

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option taken)`
- **Question:** Where does the index live in each governed repo, and in what shape? The stub locks
  per-target-repo residency (the governed code lives there, not in claude-config); this decides
  the concrete path and format teammates and agents will see.
- **Options:**
  - **A — committed `docs/provenance-index.json`, single file per repo:** one JSON object,
    repo-relative POSIX path → list of `{id, type, provenance}` entries (doc path derived
    deterministically from `type` + `id`). Pros: versioned WITH the code it describes; visible to
    teammates and to GitHub review; rides the pipeline's existing per-cycle commit (the
    `LAZY_QUEUE.md` / adhoc-enqueue ride-along precedent); survives machine changes. Cons: one
    more committed generated file; merge conflicts possible under concurrent completions (rare —
    completions are orchestrator-serialized per repo).
  - **B — `.claude/provenance-index.json` via `manifest.psd1` Repos scope:** harness-owned,
    tracked in claude-config for symlinked repos. Pros: keeps generated state out of work repos.
    Cons: `.claude/` is gitignored in work repos (e.g. Cognito Forms — see the manifest comments),
    so the index becomes machine-local and invisible to teammates — which defeats the manual
    teammate-churn linking story the stub scopes IN; also couples index availability to symlink
    health.
  - **C — sharded per top-level dir (`docs/provenance/<top>.json`):** scales better; premature at
    current sizes (claude-config: 10 feature receipts + 39 archived bug fixes today).
- **Recommendation:** A. The index is only working memory if every reader — including a teammate's
  session with no claude-config symlinks — can resolve it from the repo checkout itself. Keep the
  format single-file v1 with a documented shard threshold (move to C when the file exceeds ~500 KB
  or review-noise becomes real), and normalize all keys to repo-relative POSIX paths so
  Windows/WSL writers produce identical bytes.
- **Resolution:** RESOLVED A (operator-approved 2026-07-04 — recommended option taken): committed
  `docs/provenance-index.json` per repo, single JSON file, repo-relative POSIX-path keys;
  documented shard threshold (~500 KB → option C) deferred to vN.

### D4. Touched-file-set derivation — commit brackets, with an honest fallback

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How does the producer learn which files an item's commits touched, without
  trusting an LLM's memory of the cycle?
- **Options:**
  - **A — per-cycle commit-bracket ledger:** `--cycle-end` already resolves the cycle marker's
    `begin_head_sha` and the current HEAD to run `detect_cycle_bracket_friction`; additionally
    append `{feature_id, begin_sha, end_sha, ts}` to a `lazy-commit-brackets.jsonl` in the
    per-repo keyed state dir (same append-only, fail-open contract as
    `append_friction_ledger_entry` — a write failure never blocks the marker clear). At
    completion, the producer unions `git diff --name-only <begin>..<end>` over the item's recorded
    brackets. Pros: fully deterministic; reuses snapshots the markers already take; spans
    multi-run items (the state dir persists across runs). Cons: machine-local — brackets recorded
    on one workstation are invisible to a completion on another (cloud → workstation handoff),
    and pre-feature history has no brackets.
  - **B — commit-message grep (`git log --grep <slug>`):** no new state. Cons: NOT reliable —
    real history in this repo mixes `fix(build-queue-false-green): …` (slug in scope) with
    `harden(script): …` (no slug), so message-grep both misses and over-matches; unacceptable as
    the primary source for a deterministic producer.
  - **C — receipt-anchored HEAD only:** `completed_commit` gives a point, not a range.
- **Recommendation:** A primary; B as the explicitly-marked fallback (`derivation: message-grep`
  in the distillate frontmatter) for legacy items, backfill (D7), and cross-machine gaps — the
  `--backfill-receipts` precedent of honest degraded provenance, never silent. Additionally stamp
  `completed_commit` into the receipt: `write_completed_receipt` already supports the field, but
  the `apply_pseudo` mark-complete call site does not pass it today — a one-line closure of an
  existing gap.
- **Resolution:** Auto-accepted A+fallback; derivation strategy is invisible plumbing with a
  deterministic-first house answer, and the degraded path self-describes.

### D5. Rename/churn tolerance — path-literal rows + lint, no read-time inference

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What happens to index rows when files are renamed or deleted?
- **Options:**
  - **A — path-literal rows; the maintenance lint (D10) flags rows whose path no longer exists;**
    correction is a re-link (manual path) or an accepted tombstone. Pros: the index stays a pure
    record of what the producer observed; reads are trivially deterministic. Cons: rows go stale
    until linted.
  - **B — git rename detection at read time (`git log --follow`):** rows silently track renames.
    Cons: read-time inference (similarity-threshold heuristics) inside what must be a dumb lookup;
    expensive; violates the "never re-infers" renderer discipline (`lazy-queue-doc.py` precedent).
- **Recommendation:** A. Deterministic-but-occasionally-stale beats clever-but-heuristic in this
  harness; staleness is exactly what the lint exists to surface, and the flagged row doubles as
  the prompt to run the manual pass (per the stub).
- **Resolution:** Auto-accepted A; invisible read-path implementation choice with a house
  precedent.

### D6. Consumption mechanism — how the linkage reaches an agent at edit time

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option taken)`
- **Question:** How do skills and cycle subagents actually see "these decision records govern the
  file you're touching"? Token cost is the binding constraint (the mission's "efficient"
  criterion): the index is only worth having if consulting it costs less than re-deriving.
- **Options:**
  - **A — skill-step lookup via a read-only CLI:** a `--provenance-lookup <path>` subcommand
    (pure read over the index; prints governing slugs + distillate paths + decision ids). Wire one
    step into the edit-adjacent surfaces: the cycle-subagent base prompt
    (`_components/lazy-batch-prompts/cycle-base-prompt.md` — "before editing a file, look it up;
    read the cited IMPLEMENTED.md ONLY if the ids are unfamiliar"), `/spec-phases` (alongside the
    existing capability audit), and the coupled `/lazy*` wrapper prose. Pros: cost is one Bash
    call per edited file, and the expensive part (reading distillates) is conditional; degrades to
    a no-op where no index exists. Cons: relies on prompt compliance — a subagent can skip it
    (mitigated the usual way: retro/hardening catches skips as friction).
  - **B — PreToolUse Write/Edit hook injecting governing decisions as context:** mechanical, not
    compliance-based (the `block-sentinel-write-on-stray-branch.sh` shape: read the target path,
    query Python, act). Pros: cannot be skipped. Cons: fail-OPEN means silent misses anyway; adds
    a 7th+ hook to an already-deep Bash/Write chain; pays the lookup + injected-context tokens on
    EVERY edit of every governed file including trivial ones; hook output is advisory context, a
    channel the hooks currently use only for deny/allow.
  - **C — component injection of the index into skills:** static, token-heavy, stale between
    projections. Rejected on the efficiency criterion.
- **Recommendation:** A for v1, with B documented as a vN upgrade once the index has proven its
  hit-rate (the lint's churn report gives the measurement: how often governed files are edited).
  Prompt-compliance risk is real but is the same risk every skill step carries, and the
  self-improvement loop already routes compliance failures back as hardening.
- **Resolution:** RESOLVED A (operator-approved 2026-07-04 — recommended option taken): skill-step
  lookup via the read-only `--provenance-lookup` CLI in v1, wired into the cycle-subagent base
  prompt (`_components/lazy-batch-prompts/cycle-base-prompt.md`), `/spec-phases`, and the coupled
  `/lazy*` wrapper prose (coupled pairs mirrored exactly); PreToolUse hook injection (B)
  documented as the vN upgrade once hit-rate is measured.

### D7. Backfill strategy for already-completed items

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option taken)`
- **Question:** Do the ~10 receipted features + ~39 archived bug fixes in claude-config (and
  completed items in other lazy repos; counts estimated — verify during Phase 5) get distillates
  and index rows, or is the ledger forward-only?
- **Options:**
  - **A — one-shot `--backfill-provenance`:** walk items with a valid `COMPLETED.md`/`FIXED.md`
    (including `docs/bugs/_archive/`), assemble distillates marked `provenance: backfilled` with
    `derivation: message-grep` (no commit brackets exist for them). Pros: the index is useful on
    day one — most of the governed-code knowledge is in already-completed items; mirrors the
    `--backfill-receipts` precedent exactly (honest debt marking, not silence). Cons: message-grep
    derivation is lossy, so backfilled rows are lower-confidence; one-time review noise.
  - **B — forward-only:** clean but leaves the index nearly empty for months; the highest-value
    linkages (e.g. everything governing `lazy_core.py`) are historical.
  - **C — lint-driven lazy backfill:** backfill an item only when the churn lint flags one of its
    files. Pros: effort proportional to value. Cons: the lint can't know a file is governed by an
    unbackfilled item — circular.
- **Recommendation:** A for claude-config (the primary consumer, richest receipts), forward-only
  elsewhere until v1 proves out. C is circular and B starves the feature of its demo value.
- **Resolution:** RESOLVED A (operator-approved 2026-07-04 — recommended option taken): one-shot
  `--backfill-provenance` for claude-config only (`provenance: backfilled`,
  `derivation: message-grep`); forward-only elsewhere until v1 proves out.

### D8. Manual-path ergonomics — addressing, drafting, and attribution

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option taken)`
- **Question:** The stub scopes IN an operator-invocable entry point for teammate/out-of-pipeline
  work. How is the work addressed, and how much of the distillate is drafted vs typed?
- **Options (addressing):**
  - **A — commit-range primary (`--commits A..B`), PR resolved to a range:** the CLI accepts
    `--commits <range>` natively and `--pr <n>` as sugar (resolved via
    `gh pr view <n> --json baseRefOid,headRefOid,title,body` to a range + seed text). Pros: the
    producer's git surface stays one code path (ranges); PR addressing costs one `gh` call and
    degrades cleanly when `gh` is absent. Cons: none material.
  - **B — PR-number primary:** couples the deterministic producer to GitHub availability.
- **Options (drafting):**
  - **C — LLM-drafted-then-approved:** a `/link-provenance` skill derives the touched-file set via
    the producer (`--dry-run`), drafts the distillate body from the PR description/review thread
    or the diff, presents it via `AskUserQuestion` for approval, then writes THROUGH the producer
    CLI. Pros: matches how the operator actually works (steering, not typing); the deterministic
    parts (file set, index rows, frontmatter) never come from the LLM — only the approved body
    prose does, and the frontmatter records that (D9). Cons: an approval step per link.
  - **D — fully interactive prompts:** operator types the body; slower, no quality gain over C's
    approve/edit loop.
- **Recommendation:** A + C: CLI `lazy-state.py --link-provenance --id <slug> --commits <range>`
  (or `--pr <n>`) with `--body-file` for the approved prose; skill `/link-provenance` as the
  ergonomic front end. When no SPEC exists for the linked work, the skill creates a minimal
  decision-record dir (`docs/features/<slug>/` with the distillate as its primary doc) rather
  than inventing a fake SPEC.
- **Resolution:** RESOLVED A+C (operator-approved 2026-07-04 — recommended option taken):
  commit-range-primary addressing (`--commits A..B`) with `--pr <n>` sugar; distillate body
  LLM-drafted-then-approved via the `/link-provenance` skill, always written THROUGH the producer
  CLI (`--body-file` for the approved prose).

### D9. Provenance-attribution field

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How do readers distinguish pipeline-emitted, manually-linked, and backfilled
  entries (the stub asks for this field explicitly)?
- **Options:** a single `provenance:` enum on both the distillate frontmatter and each index
  entry: **`pipeline-gated`** (written inside the completion gate) | **`manual`** (the D8 path;
  plus `linked_by:` and the addressing used) | **`backfilled`** (D7). Extends the receipt
  vocabulary (`gated` / `backfilled-unverified`) rather than inventing a new one.
- **Recommendation:** As above — one enum, three values, mirrored in both artifacts so a reader
  never needs the other file to know an entry's trust level.
- **Resolution:** Auto-accepted; a schema field with operator-locked intent — only the value
  names are being fixed here.

### D10. Maintenance lint — dead rows and un-provenanced churn

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What keeps the index honest over time?
- **Options:** a read-only `--lint-provenance` subcommand (same script as the producer; report
  only, never mutates) with three checks: (a) index rows whose path no longer exists in the
  working tree (deleted/renamed — D5's correction prompt); (b) high-churn files with NO index
  rows (`git log --since <window> --name-only` aggregation over a commit-count threshold — the
  prompt to run the manual pass over teammate churn, per the stub); (c) cross-orphans (a
  distillate with no index rows, or rows citing a missing distillate). Alternative — folding
  these checks into the sibling `doc-drift-linter`: rejected; that feature lints hand-written
  CLAUDE.md claims, this lints a machine-written index against git, and coupling them couples two
  Draft specs.
- **Recommendation:** As above. Churn thresholds are config with placeholder defaults (e.g. ≥5
  commits in 90 days — estimated, tune during Phase 5); thresholds are numbers in one place, not
  judgment calls.
- **Resolution:** Auto-accepted; report-only tooling shape with the stub's intent already fixed.

### D11. v1 repo scope

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option taken)`
- **Question:** Which repos get the producer wired in v1?
- **Options:**
  - **A — claude-config + AlgoBooth:** both run the full lazy pipeline, work on and push `main`,
    and already carry the pipeline-integrated commit rider precedent (mobile-queue-control
    Decision 6). Pros: the committed index (D3-A) lands on the default branch with zero publish
    machinery. Cons: other lazy-enabled repos wait.
  - **B — every repo with a `docs/{features,bugs}/queue.json`:** maximal coverage; but work-branch
    repos complicate the committed-index story and multiply rollout risk.
- **Recommendation:** A. The producer stays `--repo-root`-addressable everywhere (any repo can
  link manually), but the automatic gate wiring ships to the two repos whose publishing model is
  already proven.
- **Resolution:** RESOLVED A (operator-approved 2026-07-04 — recommended option taken):
  claude-config + AlgoBooth automatic gate wiring; the manual path (`--link-provenance`) stays
  `--repo-root`-addressable everywhere.

## User Experience

### Pipeline path (invisible until read)

Nothing changes in the operator's workflow. When a completion gate passes, the `apply_pseudo`
result JSON additionally reports `provenance_written: true` and the item dir gains:

```markdown
---
kind: implemented
feature_id: budget-guard-defers-near-complete-feature
date: 2026-07-04
provenance: pipeline-gated
derivation: commit-brackets
commits: [a1b2c3d, 4e5f6a7, 8b9c0d1]
decisions: [L1, L2, L4]
---

# Implementation Ledger

**What shipped:** <the SPEC's leading `>` summary paragraph, verbatim>

**Decisions that drove it:**
- L1 — near-completion grace is one-shot
- L2 — corrective cycles discount the budget trip count
- L4 — evicted features are never auto-resumed

**Validated via:** mcp (12/12). Receipt: COMPLETED.md (provenance: gated).
```

The repo-level `docs/provenance-index.json` gains rows for each touched file, riding the
completion's existing commit:

```json
{
  "user/scripts/lazy_core.py": [
    {"id": "budget-guard-defers-near-complete-feature", "type": "feature",
     "provenance": "pipeline-gated"},
    {"id": "hardening-blind-to-process-friction", "type": "bug", "provenance": "backfilled"}
  ]
}
```

### Lookup at edit time (per D6 outcome)

```bash
python3 ~/.claude/scripts/lazy-state.py --provenance-lookup user/scripts/lazy_core.py
# → {"path": "user/scripts/lazy_core.py", "governed_by": [
#     {"id": "...", "type": "feature", "doc": "docs/features/.../IMPLEMENTED.md",
#      "decisions": ["L1","L2","L4"], "provenance": "pipeline-gated"}, ...]}
```

A cycle subagent's base prompt directs: look up before the first edit to a file; open the cited
`IMPLEMENTED.md` only when the decision ids are unfamiliar to the task at hand.

### Manual path (per D8 outcome)

```
/link-provenance --pr 87
```

The skill resolves the PR to a commit range, runs the producer's `--dry-run` to show the derived
touched-file set, drafts the distillate body from the PR description + review thread, asks for
approval (`AskUserQuestion`), then writes through the producer. Failure modes are explicit: an
unresolvable range or a dirty index write aborts with the producer's refusal text; nothing is
half-written (atomic writes throughout).

### Lint

```bash
python3 ~/.claude/scripts/lazy-state.py --lint-provenance --repo-root .
# → dead rows (file gone), churn hotspots with no provenance, cross-orphans — report only
```

## Technical Design

```
 cycle markers (begin_head_sha)          completion gate                       committed artifacts
 --cycle-end ──append──▶ lazy-commit-    apply_pseudo __mark_complete__ ──▶  docs/<pipe>/<slug>/IMPLEMENTED.md
 brackets.jsonl (keyed state dir,        │  (gate passes) → write_provenance  docs/provenance-index.json
 fail-open, per-repo)                    │      ├─ union git diff over         (rides the completion commit)
                                         │      │  recorded brackets
 manual: --link-provenance ─────────────▶│      └─ merge index rows (atomic)
 (--commits A..B | --pr N, D8)           └─ failure ⇒ warnings[], never
                                            blocks the completion
 consumers: --provenance-lookup <path> (pure read) ◀── skills / cycle prompts (D6)
 maintenance: --lint-provenance (pure read, report only) (D10)
```

- **Producer:** `lazy_core.write_provenance(repo_root, item_dir, item_id, kind, commits, ...)` —
  stdlib-only, every file write through `lazy_core._atomic_write`. Called from the
  `__mark_complete__`/`__mark_fixed__` branch of `apply_pseudo` AFTER the receipt write and queue
  trim succeed (the completion's core is already durable), and from the `--link-provenance` CLI.
  Shared `lazy_core` implementation means both pipelines get it with no coupled-pair mirror;
  `lazy_parity_audit.py --repo-root .` must stay green over the CLI additions.
- **Failure containment:** a provenance write failure inside the gate degrades to a `warnings[]`
  entry on the `apply_pseudo` result — the exact policy the malformed-queue trim already uses.
  Completion is never blocked by its own bookkeeping.
- **Commit brackets:** the `--cycle-end` handler (which already resolves `begin_head_sha` → HEAD
  for `cycle_end_friction_check`) appends `{feature_id, begin_sha, end_sha, ts}` to
  `lazy-commit-brackets.jsonl` in `claude_state_dir()` (per-repo keyed; append-only; fail-open —
  identical contract to `append_friction_ledger_entry`). Mirrored on both state scripts' handlers
  (coupled pair; parity-audited).
- **Receipt anchor:** pass `completed_commit=_current_head(repo_root)` at the existing
  `write_completed_receipt` call in the mark-complete branch (the field exists; the call site
  omits it today).
- **Index writes:** load → merge → `_atomic_write`, mirroring `lazy_core.reorder_queue`'s
  load-mutate-write shape. Keys normalized to repo-relative POSIX paths. Idempotent: re-running a
  completion (receipt-noop path) writes nothing; re-linking the same range replaces that item's
  rows rather than duplicating them.
- **Reads:** `--provenance-lookup` and `--lint-provenance` are pure reads — they never mutate the
  index and never re-infer state (the `lazy-queue-doc.py` renderer discipline).
- **Sentinel schema:** `kind: implemented` registered in `_components/sentinel-frontmatter.md` +
  the AlgoBooth `SENTINEL_SCHEMAS` mirror. `IMPLEMENTED.md` is read by humans and lookups only;
  `compute_state` ignores it entirely.

## Implementation Phases

- **Phase 1 — Commit-bracket ledger + receipt anchor.** `--cycle-end` appends bracket records
  (both state scripts; fail-open); `apply_pseudo` stamps `completed_commit`. Proven by
  `test_lazy_core.py` fixtures (bracket append, fail-open on unwritable dir) + in-file `--test`
  additions + a green `lazy_parity_audit.py` run.
- **Phase 2 — Producer + gate wiring.** `lazy_core.write_provenance`; distillate + index emission
  from `__mark_complete__`/`__mark_fixed__` (D2/D3/D4/D9); `warnings[]` degradation; schema
  registration. Proven by: a fixture completion produces byte-stable IMPLEMENTED.md + index rows;
  a refused gate writes neither; an induced index-write failure still completes with a warning.
- **Phase 3 — Manual path.** `--link-provenance` CLI (`--commits`/`--pr`/`--body-file`/
  `--dry-run`) + `/link-provenance` skill (draft-then-approve per D8). Proven by: linking a
  historical range produces `provenance: manual` entries byte-identical in shape to pipeline
  entries; `--dry-run` mutates nothing.
- **Phase 4 — Consumption.** `--provenance-lookup` + wiring per the D6 outcome (cycle-base-prompt
  step, `/spec-phases` step, wrapper prose — coupled-pair mirrors diffed). Proven by: lookup
  returns correct rows for a seeded index; a cycle subagent transcript shows the step firing.
- **Phase 5 — Backfill + lint.** `--backfill-provenance` per the D7 outcome; `--lint-provenance`
  (D10); verify the estimated item counts; tune churn thresholds against real history. Proven by:
  backfilled entries carry `provenance: backfilled` + `derivation: message-grep`; lint catches a
  planted dead row and a planted hot un-provenanced file.

Estimate: ~4-5 sessions (Phases 1-2 one session; 3, 4, 5 roughly one each).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Distillate emitted at completion | Fixture `__mark_complete__` with brackets recorded | `IMPLEMENTED.md` with `provenance: pipeline-gated`, correct decision ids, commit shas | `test_lazy_core.py` fixture assertions |
| Index rows match touched files | Same fixture | Index keys == `git diff --name-only` union over brackets | pytest diff of index vs computed set |
| Completion never blocked by bookkeeping | Induced index-write failure | Receipt + status flip land; result carries `warnings[]` | pytest fixture |
| One writer, two triggers | Manual link of a range | Entry shape byte-identical to pipeline entries except `provenance`/`derivation` | pytest comparing both outputs |
| Refused gate writes nothing | `__mark_complete__` with no evidence sentinel | No distillate, no index change | pytest fixture |
| Idempotency | Re-run completion / re-link same range | No duplicate rows; receipt-noop path writes nothing | pytest + byte-diff |
| Bracket append is fail-open | Unwritable state dir at `--cycle-end` | Marker still cleared; no exception | in-file `--test` fixture |
| Lookup is pure read | `--provenance-lookup` on seeded repo | Correct rows; index mtime unchanged | pytest |
| Lint catches rot | Delete an indexed file; churn a non-indexed one | Both flagged in report; nothing mutated | pytest + manual run |
| Backfill honesty | `--backfill-provenance` on a receipted item | `provenance: backfilled`, `derivation: message-grep` | manual inspection |

## Open Questions

- **D3 — index format + location:** committed `docs/provenance-index.json` per repo (single JSON,
  POSIX-path keys) vs `.claude/`-resident via manifest. Standing recommendation: committed
  `docs/provenance-index.json` — teammate-visible, versioned with the code, rides existing
  commits.
- **D6 — consumption mechanism:** skill-step lookup CLI vs PreToolUse hook injection vs component
  injection. Standing recommendation: skill-step lookup CLI in v1 (cheapest tokens, degrades to
  no-op); hook injection documented as vN.
- **D7 — backfill:** one-shot backfill of receipted items vs forward-only. Standing
  recommendation: backfill claude-config only (`provenance: backfilled`, message-grep derivation),
  forward-only elsewhere.
- **D8 — manual-path ergonomics:** commit-range-primary addressing with `--pr` sugar; distillate
  body LLM-drafted-then-approved via `/link-provenance`, written through the producer. Standing
  recommendation: yes to both.
- **D11 — v1 repo scope:** claude-config + AlgoBooth automatic wiring (manual path available
  everywhere) vs all lazy-enabled repos. Standing recommendation: claude-config + AlgoBooth.
- Deferred empirical checks (implementation, not decisions): exact backfill item counts (10
  feature receipts / 39 archived bug fixes in claude-config — re-verify at Phase 5); churn-lint
  threshold defaults against real history; index size at AlgoBooth scale (shard trigger); whether
  `gh` is reliably present where `--pr` addressing will run.

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the receipt-gating + `--backfill-receipts` provenance
  vocabulary; ADR/traceability-matrix prior art for the distillate; CODEOWNERS as the
  path→governors reverse-index shape; git-notes rejected as the index store.
- `user/scripts/lazy_core.py` — `apply_pseudo` (`__mark_complete__` branch),
  `write_completed_receipt`, `_atomic_write`, `write_cycle_marker` (`begin_head_sha`),
  `gate_coverage` (Locked-Decision surface), `append_friction_ledger_entry` (fail-open append
  precedent).
- `docs/features/mobile-queue-control/SPEC.md` — committed-generated-doc + ride-along-commit
  precedent (Decision 6) and the pure-read renderer discipline.
- Siblings: `docs/features/doc-drift-linter/SPEC.md` (peer lint, distinct target);
  `user/skills/_components/mcp-coverage-audit.md` (the un-generalized doc↔code guard this
  feature generalizes).
