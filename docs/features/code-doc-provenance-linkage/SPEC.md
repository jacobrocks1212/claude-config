# Code↔Doc Provenance Linkage (Implementation Ledger) — Feature Specification

> Make the linkage between documentation and the code it governs a **byproduct of the agentic workflow**: at `__mark_complete__`/`__mark_fixed__`, distill each feature/bug into a small durable artifact (`IMPLEMENTED.md`: what shipped, which Locked Decisions drove it, why) and record the touched-file set from the cycle commits into a repo-level reverse index (file path → feature/bug slugs). Skills and cycle subagents consult the index before editing — "you're touching `lazy_core.py`; these 4 decision records govern it" — turning the docs corpus from a write-only archive into working memory.

**Status:** Draft (pre-Gemini)
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; must-have)

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The pipeline produces rich per-item docs (SPEC.md, PHASES.md, COMPLETED.md) but throws away the
one linkage it *knows deterministically at completion time*: which files the cycle commits touched
and which SPEC decisions drove them. Agents editing code later have no mechanical way to discover
the decision records that govern a file, so they re-derive — or contradict — past decisions. This
is the same failure class the coupled-pair sync rules and `mcp-coverage-audit.md` guard against,
un-generalized.

## Direction (deliberately not locked)

- **Producer:** the state scripts already hold the commit range and SPEC surface inside the
  completion gates — emit the distillate + index update there (deterministic script-owned output,
  never LLM-inferred).
- **Distillate:** deliberately small. SPECs are planning artifacts and go stale; "what exists and
  why" is the durable residue worth linking.
- **Reverse index:** per-target-repo residency (algobooth/cognito-forms/... `.claude/` or `docs/`),
  since the governed code lives there, not in claude-config.
- **Consumer:** component injection and/or lookup surfaced at edit time so subagents read the
  linked decision records nearest their edit.
- **Manual invocation for out-of-pipeline work (in scope):** not all governed code flows through
  the lazy pipeline — teammates land changes with no completion gate to emit the linkage. Provide
  an operator-invocable entry point (skill and/or script CLI) that runs the SAME distillate +
  index-update path against an arbitrary commit range / PR / branch: derive the touched-file set
  from the commits, author or point at the decision record (interactive when no SPEC exists —
  e.g. distill from the PR description/review thread), and write through the identical index
  format. One writer, two triggers — the automatic completion-gate path and the manual path must
  share the producer so the index never forks into pipeline-shaped vs. manual-shaped entries.
- **Maintenance:** a lint pass flags index entries whose files were deleted/renamed and
  high-churn files with no provenance — the latter doubling as the prompt to run the manual
  linking pass over teammate-authored churn.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: index format + location per repo;
> distillate schema; rename/churn tolerance; consumption mechanism (injection vs. hook vs. skill
> step); backfill strategy for already-completed items; manual-path ergonomics (commit-range vs.
> PR-number addressing; how much distillate authoring is interactive vs. LLM-drafted-then-
> approved; provenance attribution field distinguishing pipeline-emitted from manually-linked
> entries). Solutions above are directional, not locked.
