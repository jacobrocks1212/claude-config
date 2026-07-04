# SKIP_MCP_TEST frontmatter with an unquoted colon breaks the strict sentinel parser at the completion gate — Investigation Spec

> A `SKIP_MCP_TEST.md` waiver whose YAML frontmatter carries an **unquoted colon inside a value**
> (e.g. `reason: blocked by X: no host device`, or a `skipped_by:` line that names a `key: value`
> pair) is parsed by the strict PyYAML-backed sentinel reader as a nested mapping — or fails to
> parse outright. Because the completion gate (`__mark_complete__` / the evidence-evaluation path)
> reads the waiver through that strict parser, a colon a human naturally typed into a prose reason
> either mis-parses into the wrong shape or `_die()`s, stalling the feature at the finish line. This
> is a recurring lane friction: every `/lazy*` cycle that authors a `SKIP_MCP_TEST.md` has to
> remember to quote colon-bearing values, and the harness reminds authors in prose
> ("quote YAML values with colons!") instead of tolerating them mechanically.

**Status:** Investigating
**Severity:** P0
**Discovered:** 2026-07-04
**Placement:** docs/bugs/skip-mcp-test-frontmatter-unquoted-colon
**Related:** `user/scripts/lazy_core.py` (`parse_sentinel` / the SKIP_MCP_TEST provenance + evidence reads — `evaluate_completion_evidence`, `skipped_by` validation); `user/skills/_components/sentinel-frontmatter.md` (the canonical sentinel schema — mirror `check-docs-consistency.ts` / `check-bugs-consistency.ts` if the tolerance changes); the SKIP_MCP_TEST authoring prose in the `/lazy*` completion legs. Recurring-friction origin: the parallel-worktree-batch-execution + friction-kpi-registry lane HANDOFFs both carry the standing warning "SKIP_MCP_TEST.md (quote YAML values with colons!)".

<!-- Status lifecycle:
  - Investigating → root cause not yet proven; /spec-bug owns the root-cause investigation.
  - Concluded     → root cause proven, affected area + fix scope understood; ready for /plan-bug.
-->

---

## Problem

The sentinel frontmatter reader is strict YAML. YAML treats an unquoted `key: value` inside a
scalar as a mapping indicator, so a value like:

```yaml
---
kind: skipped
skipped_by: pipeline
reason: untestable on this host: no real audio device
---
```

either raises a `yaml` error (which the strict reader turns into a `_die()` / halt) or silently
mis-parses `reason` into a nested mapping. Either way the completion-time evidence read of
`SKIP_MCP_TEST.md` does not see the shape it expects, and a fully-waived feature cannot reach
`Status: Complete`. The current mitigation is prose discipline ("quote colon-bearing values"),
which is exactly the kind of human-remembered invariant the harness mission says to replace with a
mechanical guarantee.

## Symptoms (to verify in /spec-bug)

1. A `SKIP_MCP_TEST.md` with an unquoted colon in a value halts or mis-parses at the completion
   gate instead of being read tolerantly.
2. The failure surfaces at the very end of a feature's lifecycle (the completion leg), so it wastes
   a full cycle — the feature is otherwise done.
3. It recurs across lanes because the only defense is authoring prose, not a parser/writer contract.

## Candidate fix directions (for /spec-bug → /plan-bug to weigh, not yet decided)

- **Tolerant read:** pre-process frontmatter values so an unquoted colon in a scalar is treated as
  a literal (quote-on-read), keeping the strict schema for keys/kinds.
- **Quote-on-write:** whichever pseudo-skill authors `SKIP_MCP_TEST.md` emits colon-bearing values
  pre-quoted, so the on-disk artifact is always valid YAML.
- **Both (defense-in-depth):** tolerant read + quote-on-write, with the schema doc + the two
  `check-*-consistency.ts` validators kept in lockstep.

Whichever direction wins must keep `_components/sentinel-frontmatter.md` and the AlgoBooth/bug
consistency validators in sync (the schema-lockstep coupling), and add a regression fixture to the
in-file `--test` harness proving an unquoted-colon waiver parses and the completion gate accepts it.

## Why P0

It blocks completion — a done feature cannot certify — and it is on the critical path for the very
completion gate the resumed lane features (friction-kpi-registry, parallel-worktree-batch-execution)
will hit when they author their own `SKIP_MCP_TEST.md`. Fixing the parser before those features
reach the gate removes the recurring footgun for the whole batch.
