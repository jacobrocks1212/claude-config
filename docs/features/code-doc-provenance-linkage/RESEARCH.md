# Research — Code↔Doc Provenance Linkage (Implementation Ledger)

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **The completion gate is already the single deterministic producer site.**
  `lazy_core.apply_pseudo` (`user/scripts/lazy_core.py`, `__mark_complete__`/`__mark_fixed__`
  branch) is documented as "the SOLE AUTHOR of every scripted completion write" and is guarded at
  the library boundary (`refuse_if_cycle_active`) precisely so no other author can exist. Adding
  the distillate + index write here inherits that single-writer guarantee for free — the SPEC's
  "one writer, two triggers" constraint is a structural property of this placement, not a new
  invention.
- **Receipt provenance vocabulary.** `write_completed_receipt` already writes
  `provenance: gated` at flip time and `provenance: backfilled-unverified` from
  `--backfill-receipts` — the exact honest-degraded-marking pattern the SPEC's D7/D9 reuse. The
  receipt schema even carries an (currently unpassed) `completed_commit:` field, evidence that a
  commit anchor was anticipated but never wired.
- **Commit tracking already exists in the markers.** `write_cycle_marker` snapshots
  `begin_head_sha` at every `--cycle-begin`, and `--cycle-end` resolves the current HEAD to run
  `detect_cycle_bracket_friction` (per-sub_skill commit budgets, `commit_tally`). The touched-file
  derivation (SPEC D4) is a small extension of snapshots the harness already takes — not new
  instrumentation.
- **Fail-open append-only ledgers.** `append_deny_ledger_entry` / `append_friction_ledger_entry`
  establish the contract for the commit-bracket ledger: plain append, corrupt-line-tolerant
  reader, write failure never propagates. The per-repo keyed state dir (`claude_state_dir()`,
  `multi-repo-concurrent-runs`) gives bracket records the right isolation.
- **The Locked-Decision surface is already machine-parsed.** `lazy-state.py --gate-coverage`
  (`lazy_core.gate_coverage`) enumerates `## Locked Decisions` tables / `## Resolved by Research`
  bullets / numbered key-decision blocks. The distillate cites decision ids from this parse —
  zero new SPEC-parsing code, and the ids stay consistent with what the MCP-coverage gate audits.
- **Committed generated docs riding pipeline commits.** `lazy-queue-doc.py` (mobile-queue-control)
  proved the model the index reuses: a byte-stable generated file, committed in the target repo,
  staged so it rides the cycle's existing commit on `main` (claude-config + AlgoBooth both push
  `main`). The adhoc-enqueue component documents the same ride-along convention for bootstrap
  files.
- **The failure class being generalized.** The coupled-pair tables (root `CLAUDE.md`),
  `mcp-coverage-audit.md`, and the nested CLAUDE.md files are all hand-maintained
  "this doc governs that code" links — each one added after a defect showed agents editing code
  without its decision record. `worktree-claude-doc-drift` (docs/bugs) shows what happens when
  such hand links rot. This feature is the mechanical, general form.
- **Peer:** `doc-drift-linter` (Draft stub) lints hand-written CLAUDE.md claims against
  settings/filesystem. Kept separate: different claim source (human prose vs machine-written
  index), different ground truth (settings.json vs git history).

## External prior art & concepts

(Training-knowledge survey, not live research.)

- **Architecture Decision Records (ADR / MADR, Nygard 2011).** The closest external analog to
  `IMPLEMENTED.md`: small, immutable, per-decision records kept next to the code, valued
  precisely because full design docs go stale while "what we decided and why" endures. The SPEC's
  "deliberately small" constraint matches the ADR community's core lesson — long records don't
  get read; the durable residue is decision + rationale + consequences.
- **Requirements traceability matrices (SWEBOK / DO-178C practice).** Reverse indexes from
  artifact → requirement are standard in certified software; their known failure mode is exactly
  SPEC D5/D10's target: matrices rot unless maintenance is mechanical and staleness is audited,
  not assumed.
- **CODEOWNERS (GitHub/GitLab).** A committed, repo-root, path → owners reverse index consumed
  mechanically at review time. Validates D3-A's shape: the index must live IN the governed repo to
  be visible to every reader, and path-pattern rows with no inference are what keep it cheap and
  trustworthy.
- **Commit trailers (`Fixes:`, `Link:`, kernel/Gerrit practice).** The alternative of embedding
  provenance in commit messages. Works only under strict message discipline enforced by tooling;
  this repo's real history (`harden(script): …` with no slug) shows the discipline does not hold,
  which is why message-grep is fallback-only (D4).
- **git notes.** Attach metadata to commits without touching them — superficially ideal as an
  index store, but notes don't push/fetch by default, have no rename story, and are invisible on
  GitHub. Rejected: the index must be a plain committed file.
- **Sourcegraph / code-intelligence "who owns this" panels.** Demonstrate the consumption UX the
  lookup CLI approximates: the value is at edit/review time, on demand — not injected globally
  (which is why D6 rejects component injection on token cost).

## Alternatives analysis

- **Producer placement (D1).** Inline-in-branch vs shared `lazy_core` helper vs orchestrator
  prose. Prose is excluded by the operator constraint (deterministic, never LLM-inferred). Inline
  would force the manual path through the completion gate's evidence checks (or fork the code).
  The shared helper is the only shape where "one writer, two triggers" is structural; it also
  lands in the file both state scripts import, so bug-pipeline coverage is automatic.
- **Touched-file derivation (D4).** Bracket ledger vs message-grep vs receipt anchor. Checked the
  actual git log: commit scopes are inconsistent (`fix(build-queue-false-green):` vs
  `harden(script):`), so message-grep is demonstrably lossy — acceptable only as a marked
  fallback. The bracket ledger reuses existing marker snapshots and the existing fail-open append
  pattern; its known gap (machine-locality, cloud→workstation handoff) degrades to the marked
  fallback rather than to silence.
- **Index residency (D3).** Committed-in-repo vs `.claude/`-resident. The manifest shows work-repo
  `.claude/` dirs are gitignored by their repos (Cognito comments in `manifest.psd1`), so a
  `.claude/` index is machine-local — invisible to exactly the teammates whose churn the manual
  path exists to link. Committed `docs/provenance-index.json` also inherits the
  ride-along-commit publish path proven by `LAZY_QUEUE.md`. Single-file until size forces
  sharding; POSIX-normalized keys avert Windows path-separator forks
  (`windows-portability-in-probe-glue-and-field-validators` history argues for normalizing at the
  writer).
- **Consumption (D6).** Skill-step lookup vs PreToolUse hook vs injection. Injection fails the
  efficiency criterion outright (every skill pays, always). The hook is mechanical but: fail-OPEN
  hooks silently miss anyway, the Bash/Write hook chains are already deep, and per-edit context
  injection charges tokens on every trivial edit. The skill step pays only on relevant edits and
  makes distillate-reading conditional on unfamiliarity; its compliance risk is the standard one
  the retro/hardening loop already polices. Hook-based enforcement remains the documented vN if
  lookup-skipping shows up as friction.
- **Backfill (D7).** Day-one usefulness vs purity. Most linkage value is historical (everything
  governing `lazy_core.py` is already Complete/Fixed), and the `--backfill-receipts` precedent
  shows how to grandfather honestly. Lint-driven lazy backfill is circular (the lint can't flag
  files whose governors were never indexed).
- **Manual drafting (D8).** The deterministic-producer constraint applies to the *producer* —
  file sets, index rows, frontmatter. Body prose for teammate work has no deterministic source (no
  SPEC exists), so drafted-then-approved is the honest option, with `provenance: manual`
  attribution making the trust level explicit.

## Pitfalls & risks

- **Completion-path fragility.** Any new write inside `__mark_complete__` risks blocking
  completions. Mitigated by ordering (after receipt + trim) and the `warnings[]` degradation
  policy already used for the malformed-queue trim; validated by an induced-failure test.
- **Index rot → distrust → abandonment.** The traceability-matrix death spiral. The lint (D10)
  plus path-literal honesty (D5) keep staleness visible; the manual path keeps correction cheap.
  If lint findings are ignored for months, the feature is dead weight — the churn report doubles
  as its own usage measurement (falsifiability: lookups per governed-file edit, dead-row count
  trend).
- **Token-cost inversion.** If lookups fire on every edit including trivial ones, the feature
  costs more than re-derivation. The step is scoped to first-edit-per-file with conditional
  distillate reads; D6 stays OPEN so the operator sets the aggressiveness.
- **Distillate drift.** IMPLEMENTED.md could contradict a later realign/supersede. Acceptable v1:
  the distillate records what shipped *at completion*, receipt-style (immutable record, not
  living doc); a superseding item writes its own distillate and the index carries both.
- **Merge conflicts on the committed index** under concurrent worktree completions
  (`lazy-worker`/`lazy_coord.py` fleet). Completions finalize under the coordination lock, and
  index merges are per-path list-appends — low risk, but Phase 2 should keep the JSON
  stable-sorted to make conflicts diffable.
- **Windows/WSL byte-stability.** Path separators and CRLF could make regeneration non-idempotent.
  Writer normalizes to POSIX-relative paths + LF (the `lazy-queue-doc.py` byte-stability
  discipline).

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 producer placement | Shared `lazy_core.write_provenance`, called from gate + manual CLI | High (auto-accepted) |
| D2 distillate schema | `kind: implemented` frontmatter + deterministic extract; registered in sentinel-frontmatter.md | High (auto-accepted) |
| D3 index residency/format | Committed `docs/provenance-index.json`, single file, POSIX keys | Medium-high (OPEN) |
| D4 touched-file derivation | Commit-bracket ledger at `--cycle-end`; message-grep as marked fallback; stamp `completed_commit` | High (auto-accepted) |
| D5 rename tolerance | Path-literal rows + lint; no read-time rename inference | High (auto-accepted) |
| D6 consumption | Skill-step lookup CLI v1; hook injection as vN | Medium (OPEN — token-cost call is the operator's) |
| D7 backfill | One-shot backfill claude-config; forward-only elsewhere | Medium (OPEN) |
| D8 manual ergonomics | `--commits` primary + `--pr` sugar; draft-then-approve skill writing through the producer | Medium-high (OPEN) |
| D9 attribution | `provenance: pipeline-gated \| manual \| backfilled` on both artifacts | High (auto-accepted) |
| D10 lint | `--lint-provenance` report-only: dead rows, un-provenanced churn, cross-orphans | High (auto-accepted) |
| D11 v1 scope | claude-config + AlgoBooth automatic; manual path everywhere | Medium-high (OPEN) |
