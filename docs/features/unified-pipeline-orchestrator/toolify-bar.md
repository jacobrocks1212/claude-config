# The Deterministic-Only Bar — toolify candidate schema + promotion checklist

> Part of **unified-pipeline-orchestrator** Phase 4 (the Toolification framework).
> Governs `user/scripts/toolify-miner.py`. The miner *proposes*; promotion to a real
> subcommand is a deliberate, reviewed step — the miner never auto-writes code.

The retro found the orchestrator hand-runs the same deterministic multi-tool sequences
every run — booting/health-checking the runtime, the Gate-1 coverage audit, the
`__mark_complete__` ROADMAP-strike + queue-trim. Each is a token-heavy *dance* the agent
re-derives from prose every time. The toolification framework mines those dances out of
the session logs and ranks them as candidates for promotion into a single
`lazy-state.py` subcommand. This document defines **what may be toolified** (the bar),
**the candidate record** (the schema), and **how a candidate becomes code** (the
promotion checklist).

## The miner (one-paragraph summary)

`toolify-miner.py` is stdlib-only and **read-only over the logs**. It parses
`~/.claude/projects/**/*.jsonl` (plus `**/subagents/agent-*.jsonl`), extracts the
ordered tool-call stream from each assistant turn, slides a contiguous n-gram window
over it, normalizes each window into a **signature** (tool name + argument *shape*, with
all values elided), and ranks recurring signatures by
`score = occurrences × est_tokens_per_occurrence`. It emits a markdown table and/or
JSON. It NEVER writes, renames, or deletes anything under the logs dir — the test suite
hashes the fixture log dir before and after every run and asserts byte-equality.

## The deterministic-only bar

A candidate surfaces **above the bar** (i.e. is toolify-eligible) **iff all three** hold:

1. **Deterministic** — the sequence contains no *judgment* step. Its branches are
   computable from observable state, not from the agent's reasoning. A window is
   judgment-bearing (and therefore NOT deterministic) if any call is:
   - `AskUserQuestion` (an explicit human-judgment prompt), or
   - a verdict / recovery-dispatch / ledger-verification step — detected heuristically
     by value markers (`--verify-ledger`, `verdict`) in any string argument.
   Steps requiring judgment (verdicts, recovery-dispatch decisions, "is this output
   salvageable") are **explicitly out of scope** per the retro's counter-note —
   `--verify-ledger` and recovery dispatch are already the right shape and must stay
   agent-driven.
2. **Repeated** — it occurs across **≥ `MIN_RUNS` distinct session runs** (default 2).
   A dance that repeats only *within a single run* fails this predicate (it may be a
   one-off loop, not a recurring dance).
3. **Token-heavy** — its `score` exceeds **`TOKEN_HEAVY_THRESHOLD`** (default 600). A
   short single-call sequence repeated a couple of times falls below; a multi-call dance
   repeated across runs clears it.

Judgment sequences and below-threshold sequences are **still surfaced** in the ranked
table (so the operator sees them) but are flagged `above_bar: false`. Ranking is strictly
by `score` descending — a frequent judgment sequence may out-rank a deterministic dance,
and the table shows that honestly with the `above_bar` column doing the gatekeeping.

### Signature granularity (Open Question — resolved)

> **Open Question (SPEC):** "How coarse should tool-call signatures be to cluster 'the
> same dance' without over-merging distinct sequences?"

**Resolved coarseness:** a signature is the ordered tuple of `(tool_name,
sorted-tuple-of-top-level-argument-keys)` over the window, with **all argument values
fully elided**. Rationale:

- **Positive (must merge):** two occurrences of the runtime-ensure dance that differ only
  in argument *values* — `curl localhost:3333/health` vs `curl localhost:4444/health`,
  different `--retry` counts — share one signature, so the same dance clusters across
  runs. (Tested: `test_signature_elides_values_keeps_shape`,
  `test_signature_value_in_string_does_not_affect_shape`.)
- **Negative (must NOT merge):** two genuinely distinct sequences do not collapse. A
  different tool, or the *same* tool with a different argument **key set**
  (`Read{file_path}` vs `Read{file_path,limit,offset}`), yields a different signature.
  (Tested: `test_signature_distinguishes_shape_distinct_sequences`,
  `test_signature_different_arg_keys_distinct`.)

This sits at the **argument-shape** granularity: coarser than raw values (so dances
cluster), finer than tool-name-only (so distinct argument shapes stay apart). Windows are
bounded to `MIN_NGRAM..MAX_NGRAM` (1..6) calls — the recurring dances the bar targets are
short (the three retro-named dances are 2-6 calls), and bounding the window keeps the
candidate set from blowing up on long transcripts.

## Candidate schema

Each row the miner emits (markdown and JSON) carries:

| Field | Type | Meaning |
|-------|------|---------|
| `signature` | string | Normalized sequence: `Tool(arg,keys) -> Tool(arg,keys) -> …` (values elided). |
| `occurrences` | int | Total times this signature appeared across all runs. |
| `run_count` | int | Number of DISTINCT session runs (files) it appeared in — the "repeated" predicate reads this. |
| `est_tokens_per_occurrence` | int | Heuristic token cost of one occurrence (`n_calls × EST_TOKENS_PER_CALL`). |
| `score` | int | `occurrences × est_tokens_per_occurrence` — the ranking key. |
| `deterministic` | bool | True iff the window contains no judgment-marker call. |
| `above_bar` | bool | True iff deterministic AND `run_count ≥ MIN_RUNS` AND `score > TOKEN_HEAVY_THRESHOLD`. |
| `n_calls` | int | Window length (number of tool calls in the sequence). |
| `sample_tools` | list[str] | The tool names in order (a quick human-readable gloss of the signature). |

## Promotion is deliberate — the checklist

The miner **proposes**; a candidate becomes a real subcommand only via this reviewed
sequence. No step here is automatic, and the miner itself **never writes code**.

1. **Mine.** Run `toolify-miner.py` over real session logs; read the ranked table.
2. **Confirm above-bar.** The candidate must be `above_bar: true`. A below-bar candidate
   (judgment-bearing, single-run, or below the token threshold) is **not** eligible —
   re-confirm by eye that the dance is genuinely deterministic, not just lacking a marker.
3. **Name the dance.** Map the signature back to the human dance it represents (e.g. the
   runtime-ensure, Gate-1 coverage, or mark-complete dance). A signature with no clear
   real-world dance behind it is a mining artifact, not a candidate.
4. **Spec the subcommand.** Decide its name, inputs, structured return, and home script.
   Capture genuine product/architecture forks (e.g. repo-specific coupling) as
   `NEEDS_INPUT.md`, not as a silent hard-code.
5. **Implement under full gates.** Promote the dance to a `lazy-state.py` (or
   `bug-state.py`) subcommand test-first; keep the coupled pairs + parity audit in sync;
   run the full quality-gate suite.
6. **Rewire the caller.** Replace the hand-run dance in the batch skill prose with the new
   subcommand call. Mirror the change across any coupled-pair twin.
7. **(Future) Auto-initiation.** Once `harness-hardening-retro-fixes` lands, harden-harness
   may auto-initiate steps 1-4 as a `/spec-bug` when it detects a dance in-run — but the
   *implementation* (step 5+) stays a reviewed change. The framework defines the schema and
   this checklist; it does not auto-write code.

> **Cross-reference — RESEARCH_SUMMARY Locked Decision 5.** Automatic *in-run*
> identification of toolify candidates (harden-harness detecting a dance and spinning off a
> `/spec-bug` to toolify it) is wired downstream by the `harness-hardening-retro-fixes`
> feature. This Phase ships the framework that path plugs into — the miner, the bar, the
> schema, and this promotion checklist.

## The first three proven consumers (Phase 5)

Phase 5 promotes exactly the three retro-named dances this bar targets, proving the
framework end-to-end:

- `lazy-state.py --ensure-runtime` → `{ready|booted|stale-rebuilt, mcp_tools_present}`
  (the runtime-ensure dance).
- `lazy-state.py --gate-coverage <spec_path>` → deterministic Gate-1 verdict (the
  coverage-audit dance; promotes `_components/mcp-coverage-audit.md`'s algorithm to code).
- `lazy-state.py --apply-pseudo __mark_complete__ <spec_path>` → existing flip + ROADMAP
  strike + `spec_dir`-keyed queue trim (the mark-complete dance).

## Tunable constants (live in `toolify-miner.py`)

| Constant | Default | Predicate |
|----------|---------|-----------|
| `MIN_RUNS` | 2 | "repeated" — distinct runs a candidate must appear in. Overridable via `--min-runs`. |
| `TOKEN_HEAVY_THRESHOLD` | 600 | "token-heavy" — score must exceed this. |
| `EST_TOKENS_PER_CALL` | 120 | Heuristic per-call token cost (relative ranking only). |
| `MIN_NGRAM` / `MAX_NGRAM` | 1 / 6 | Sliding-window bounds for candidate sequences. |
| `_JUDGMENT_TOOLS` | `{AskUserQuestion}` | Tools that make a window non-deterministic. |
| `_JUDGMENT_VALUE_MARKERS` | `--verify-ledger`, `verdict` | String-arg markers that flag a judgment step. |

## Runtime verification (manual — NOT closed by `/execute-plan`)

Running the miner over the operator's **real** session logs should produce a ranked table
whose top above-bar rows correspond to the three retro-named dances (runtime-ensure,
Gate-1 coverage, mark-complete), with the judgment sequences (`--verify-ledger`, recovery
dispatch) ranking below the bar. This is a manual/integration sanity check that the chosen
granularity clusters real dances without over-merging — it is documented here and in the
PHASES Runtime Verification row, not asserted by the hermetic fixture tests.
