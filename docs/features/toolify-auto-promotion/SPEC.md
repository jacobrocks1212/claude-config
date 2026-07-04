# Auto-Promotion Pipeline for Toolify Candidates — Feature Specification

> `toolify-miner.py` proposes ranked, evidence-backed toolification candidates, but every promotion
> is hand-authored today, so above-bar candidates rot in a report. This feature ships a
> **materializer**: a deterministic script step that converts one above-bar miner candidate into a
> stub feature SPEC (with the miner's occurrence/token evidence embedded) plus a queue entry via
> the existing script-owned enqueue path — routed through the same `/spec` Step 4.5 interactive
> baseline-lock as any other stub, so auto-drafting never becomes auto-approval. A central
> promotion ledger records promoted/declined outcomes per candidate signature, deduplicates
> re-promotion, and feeds a report-only acceptance-rate view so the bar's thresholds can be tuned
> deliberately from real data.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented contracts, not sibling
> specs**:
> - `user/scripts/toolify-miner.py` — the READ-ONLY miner whose ranked output (`mine()`,
>   `signature()`, the `Candidate` schema, `render_json()`) this feature consumes. Its
>   READ-ONLY-over-logs invariant (hash-before/after in `test_toolify_miner.py`) is untouched.
> - `docs/features/unified-pipeline-orchestrator/toolify-bar.md` — the deterministic-only bar and
>   the deliberate-promotion checklist this feature mechanizes the *clerical* steps of (mine,
>   confirm above-bar, draft the stub). The judgment steps stay human.
> - `lazy-state.py --enqueue-adhoc` (`enqueue_adhoc()` at `user/scripts/lazy-state.py:582`) — the
>   script-owned queue insert + spec-dir seed the materializer calls; it never re-implements it.
> - The stub-spec conventions that route a new stub through `/spec` Step 4.5 baseline-lock: the
>   queue `"stub": true` flag plus the in-SPEC stub markers detected by
>   `_spec_text_has_stub_marker` (`lazy-state.py:1076`).

---

## Executive Summary

The toolification framework (unified-pipeline-orchestrator Phase 4) already does the hard analytic
work: `toolify-miner.py` parses the session-log corpus read-only, normalizes recurring tool-call
dances into argument-shape signatures, and ranks them with the deterministic-only bar
(`above_bar` iff deterministic AND ≥ `MIN_RUNS` distinct runs AND `score > TOKEN_HEAVY_THRESHOLD`).
But the output dead-ends in a markdown table. To act on a candidate the operator must hand-author a
feature stub, hand-edit nothing (queue edits are script-owned), and hand-track which candidates were
already promoted or declined — friction that means above-bar candidates observed in one mining pass
are still unpromoted several sessions later. This is an **efficiency** defect in the harness's own
self-improvement loop: the loop's most expensive segment (operator clerical work) sits exactly where
the framework promised mechanization.

The fix is a small, deterministic **materializer** (`toolify-promote.py`, a sibling script) plus a
**promotion ledger**. Promote takes a candidate id, verifies the candidate is genuinely above-bar,
refuses duplicates against the ledger, then reuses two existing script-owned surfaces: the
`--enqueue-adhoc` insert (extended with additive flags for tier/position/stub so a promotion lands
as roadmap work, not a head-of-queue jump) and the stub-SPEC conventions (the materializer's
template emits the canonical stub Status value and blockquote stub trailer that Step 4.5 detects, so
the item halts at the interactive baseline-lock exactly like an operator-authored stub). The miner's
evidence — occurrences, distinct runs, estimated tokens, score, the tool sequence — is embedded in
the stub's Problem section, so the later `/spec` conversation starts from data, not memory.

The operator gate is preserved by construction: the materializer writes a *stub*, never a decided
SPEC; it writes no RESEARCH.md, no PHASES.md, no sentinel; naming the dance (bar checklist step 3, a
judgment call) remains a required operator input to the promote command. Acceptance tracking is
**report-only**: the ledger records promoted/declined, shipped is derived from the target feature's
`COMPLETED.md` receipt at read time, and the acceptance report surfaces rates per threshold band —
the bar's constants in `toolify-miner.py` are only ever changed by a deliberate human edit.

## Design Decisions

### D1. Materializer home: separate sibling script, not a miner subcommand

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where does the promote/decline/ledger logic live — a `--promote` subcommand on
  `toolify-miner.py`, a separate script, or skill prose?
- **Options:**
  - **A — `toolify-miner.py --promote`:** One CLI for the whole framework. Pros: single entry
    point. Cons: the miner's documented identity (root `CLAUDE.md`, `user/scripts/CLAUDE.md`,
    its own docstring) is "READ-ONLY over logs, emits reports, never mutates"; adding repo-writing
    subcommands to the same file muddies a contract that `test_toolify_miner.py` pins with
    dir-hash assertions and that three docs restate.
  - **B — separate `user/scripts/toolify-promote.py`:** Sibling script importing the miner via
    `importlib.util.spec_from_file_location` (the hyphenated-module pattern already proven at
    `test_toolify_miner.py:44-52`) for `mine()`/`signature()`/`Candidate`. Pros: the miner stays
    byte-comprehensible as a pure reader; write paths, ledger, and enqueue shelling live in one
    place with their own test file. Cons: one more script file.
  - **C — skill prose:** an LLM step drafts the stub. Cons: violates the house invariant of
    script-owned deterministic state over LLM-inferred writes; template drift per invocation.
- **Recommendation:** B — it keeps the miner's tested READ-ONLY contract boundary crisp at zero
  behavioral cost, and mirrors the house pattern of small single-purpose siblings
  (`lazy-queue-doc.py` beside `lazy-state.py`).
- **Resolution:** B (operator-approved 2026-07-04 — recommended option taken); internal code
  placement with no operator-visible difference beyond the command name.

### D2. Candidate identity: content-hash id added to the miner's output schema

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Promote needs a stable handle for "this candidate" across mining passes; the miner
  currently emits only the signature string (long, shell-hostile).
- **Options:**
  - **A — `candidate_id` = first 12 hex chars of SHA-256 of the signature string**, emitted as an
    additive column in `render_markdown()` / field in `render_json()` (plus a row in
    `toolify-bar.md`'s candidate-schema table). Deterministic across passes because `signature()`
    is deterministic (values elided, sorted key tuples). Pros: copy-pasteable, stable, derivable
    offline from any saved report. Cons: none material; 12 hex ≈ 48 bits is collision-safe at
    this candidate volume.
  - **B — ordinal rank:** unstable across passes (rank shifts as logs grow) — unusable as a ledger
    key.
- **Recommendation:** A. The ledger keys on the same hash, so dedup survives re-mining and even a
  re-ranked report.
- **Resolution:** A (operator-approved 2026-07-04 — recommended option taken); an additive output
  column with no consumer-visible removal or rename.

### D3. Invocation cadence: standalone on-demand, retro reports but never invokes

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option A taken)`
- **Question:** When does promotion happen — as a `/lazy-batch-retro` step, standalone on demand,
  or an interactive prompt appended to every mining run?
- **Options:**
  - **A — standalone on-demand:** operator runs the miner, reads the table, runs
    `toolify-promote.py --promote <id> --id <slug> --name "<title>"` for the ones worth doing.
    Retro (and any other flow) may *report* above-bar candidates with the ready-to-run promote
    command line, but never calls the materializer. Pros: the deliberate-promotion bar stays a
    human act; zero new autonomous write paths; matches the bar doc's "promotion is DELIBERATE".
    Cons: relies on the operator remembering to run it (mitigated by the retro report).
  - **B — retro-integrated:** `/lazy-batch-retro` runs the miner and materializes every new
    above-bar candidate automatically. Pros: nothing rots. Cons: queue spam risk (mining
    artifacts with no nameable dance become queue entries); the naming judgment (checklist
    step 3) has no human input; contradicts the bar doc's step-7 note that even the future
    auto-initiation path keeps implementation reviewed.
  - **C — post-mine prompt:** the miner asks per candidate. Cons: turns a read-only reporter into
    an interactive flow; awkward in autonomous contexts.
- **Recommendation:** A for v1, with `/lazy-batch-retro` gaining a report-only step that prints
  new above-bar candidates joined against the ledger (so unpromoted ones resurface every retro
  instead of rotting silently). B remains a possible vN once acceptance-rate data shows the
  operator accepts nearly everything the bar surfaces.
- **Resolution:** A (operator-approved 2026-07-04 — recommended option taken): standalone
  on-demand promotion; `/lazy-batch-retro` gains a report-only step that prints ready-to-run
  promote command lines but NEVER invokes the materializer.

### D4. Queue landing position: tail + roadmap tier, not the ad-hoc head jump

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option B taken)`
- **Question:** `enqueue_adhoc()` always inserts at position 0 with `tier: 0` and `adhoc: true` —
  "do this next" semantics. Is that right for a promoted toolify candidate?
- **Options:**
  - **A — keep head insert (reuse `--enqueue-adhoc` verbatim):** Pros: zero state-script change.
    Cons: every promotion jumps the operator-curated roadmap; `tier: 0` also outranks all bugs in
    the `--next-merged` merged ordering (`lazy_core.merged_priority` normalizes feature tier vs
    bug severity), which is wrong for speculative self-improvement work.
  - **B — tail insert at tier 2 with `stub: true`:** extend `--enqueue-adhoc` with additive,
    default-off flags (`--tier N`, `--stub`, `--at {head,tail}`; defaults preserve byte-identical
    behavior — the `tier` parameter already exists on `enqueue_adhoc()` at `lazy-state.py:588`,
    it is just not CLI-exposed). Promotions ride normal roadmap order and sit below P0/P1 work in
    merged ordering. Pros: promotion ≠ priority; the operator reorders with the existing
    `--reorder-queue --id <id> --to head` when one is urgent. Cons: a small additive CLI change
    to a load-bearing script (covered by new `--test` fixtures; feature-queue-shaped flags are a
    justified divergence from `bug-state.py`'s enqueue — the bug pipeline has no stub step and
    orders by severity, so no parity mirror is owed; confirm with `lazy_parity_audit.py`).
  - **C — compose existing primitives:** `--enqueue-adhoc` then `--reorder-queue --to tail`.
    Pros: no new flags. Cons: leaves `tier: 0` + `adhoc: true` metadata lying about the item's
    nature; two mutations where one suffices.
- **Recommendation:** B — the single-author invariant for queue writes is preserved (the
  materializer shells the state script; it never edits `queue.json` itself), the flags are
  additive with byte-identical defaults, and the metadata honestly describes the item (a stub on
  the roadmap, not an ad-hoc jump).
- **Resolution:** B (operator-approved 2026-07-04 — recommended option taken): tail insert at
  tier 2 with `stub: true`, via additive default-off flags `--tier N` / `--stub` /
  `--at {head,tail}` on `lazy-state.py --enqueue-adhoc`, threaded into `enqueue_adhoc()`;
  defaults stay byte-identical.

### D5. Stub authoring contract: the in-SPEC stub marker is load-bearing, not optional

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What must the materialized SPEC.md contain for the operator gate to actually
  engage?
- **Options:**
  - **A — queue `"stub": true` flag only, plain SPEC text:** looks sufficient, but is a silent
    gate bypass: `_stub_is_queue_flag_only()` (`lazy-state.py:1137`) treats "queue flag set AND no
    in-SPEC stub marker" as the *post-baseline* state — Step 4.5 clears the flag and falls through
    to Step 5 as if the baseline were already locked. The interactive baseline-lock never runs.
  - **B — emit the in-SPEC stub markers:** the materializer's template quotes the canonical stub
    Status value on the `**Status:**` line and the canonical `>` blockquote stub trailer — the two
    anchored forms `_spec_text_has_stub_marker()` (`lazy-state.py:1076`) matches — plus sets the
    queue flag. `is_stub_spec()` then routes Step 4.5 → interactive `/spec`; the Phase 1 rewrite
    drops the text markers, after which the flag-only state is *correctly* read as baseline-locked
    and cleared by `lazy_core.clear_queue_stub`.
- **Recommendation:** B — it is the only mechanics that preserves the gate. The template also
  hard-excludes everything decided-looking: no RESEARCH.md, no PHASES.md, no sentinel, no locked
  decisions; the evidence block is presented as input to `/spec`, and the open-questions trailer
  explicitly marks all direction as not locked.
- **Resolution:** B (operator-approved 2026-07-04 — recommended option taken); this is a
  correctness constraint of the existing state machine, not a product choice. (The marker strings
  themselves live once, in the materializer's template constant, with a test pinning them against
  `_spec_text_has_stub_marker` acceptance.)

### D6. Promotion ledger: central, git-tracked, keyed on candidate_id

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where do promoted/declined records live, and what do they contain?
- **Options:**
  - **A — `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` in claude-config:**
    co-located with `toolify-bar.md` (the checklist it instruments), git-tracked so every
    promotion/decline carries commit provenance (the mission's audit-grade-provenance criterion),
    written via `lazy_core._atomic_write`. One central ledger even for cross-repo promotions —
    the miner reads one workstation-global corpus, so its acceptance data is global.
  - **B — per-target-repo ledger:** fragments acceptance data across repos; a candidate promoted
    into AlgoBooth and declined for claude-config would look contradictory with no joined view.
  - **C — untracked state dir (`~/.claude/state/`):** loses history and provenance; the state dir
    is for run-scoped ephemera, not durable decisions.
- **Recommendation:** A. Schema per entry, keyed by `candidate_id`:
  `{signature, status: "promoted"|"declined", feature_id, target_repo, decided_at,
  reason, evidence: {occurrences, run_count, est_tokens_per_occurrence, score, sample_tools},
  forced: bool}`. `shipped` is **derived at read time** (the target repo's
  `docs/features/<feature_id>/COMPLETED.md` receipt is the single source of truth for "done") —
  never stored, so it can never contradict the receipt gate.
- **Resolution:** A (operator-approved 2026-07-04 — recommended option taken); central
  git-tracked ledger `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` keyed on
  `candidate_id`; `shipped` derived at read time, never stored. Internal file layout, invisible
  except through the reports.

### D7. Dedup semantics: refuse repeats, `--force` (with recorded reason) for declined ones

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option B taken)`
- **Question:** An above-bar candidate resurfaces in every mining pass until its dance stops
  happening. What does `--promote` do when the ledger already has its `candidate_id`?
- **Options:**
  - **A — hard refuse both `promoted` and `declined` (exit 2, naming the prior record):** Pros:
    simplest; no accidental re-drafts. Cons: a decline is forever — but circumstances change (a
    dance that was declined at 3 occurrences may be worth promoting at 30).
  - **B — refuse `promoted`; allow re-promoting `declined` only with `--force --reason "<why>"`,
    recording the override in the ledger:** Pros: promoted stays hard (the stub/feature already
    exists — re-drafting would collide with `enqueue_adhoc`'s duplicate-id refusal anyway);
    declined is revisitable deliberately, with the reversal reasoned and audited. Cons: one more
    flag.
  - **C — warn and proceed:** silent-ish overrides erode the ledger's meaning.
- **Recommendation:** B. Below-bar candidates are refused unconditionally in all options —
  `--force` never bypasses the bar itself (bar checklist step 2 is an operator-set constraint,
  and eligibility is the miner's `above_bar` field, recomputed fresh at promote time).
- **Resolution:** B (operator-approved 2026-07-04 — recommended option taken): hard-refuse
  re-promoting `promoted`; re-promote `declined` only with `--force --reason "<why>"`, the
  override recorded (`forced: true`) in the ledger. Below-bar candidates are refused
  unconditionally — `--force` never bypasses the bar.

### D8. Acceptance-rate feedback: report-only, never auto-adjusting the bar

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended
  option A taken)`
- **Question:** The stub asks that promoted/declined be recorded "so the bar's thresholds are
  tunable from acceptance data". Does the tool tune, or report?
- **Options:**
  - **A — report-only:** `toolify-promote.py --acceptance-report` joins the ledger with a fresh
    mine and prints: totals (promoted / declined / shipped-derived), acceptance rate, and the
    score/run-count distribution of each cohort — e.g. "every candidate with score < 1200 was
    declined" — as *observations*. Changing `MIN_RUNS` / `TOKEN_HEAVY_THRESHOLD` /
    `EST_TOKENS_PER_CALL` stays a deliberate human edit to `toolify-miner.py` (they are documented
    constants with a table in `toolify-bar.md`). Pros: the gate never modifies itself; consistent
    with the harness treating gate bypasses as defects. Cons: threshold updates need a human.
  - **B — auto-adjust:** the tool rewrites the constants when rates drift. Cons: a self-tuning
    gate is exactly the class of silent harness mutation the mission's "integrity gates are
    load-bearing" clause forbids; also statistically premature at this candidate volume.
- **Recommendation:** A — emphatically. The report should also name the sample size so a
  two-candidate "100% acceptance" is not mistaken for signal.
- **Resolution:** A (operator-approved 2026-07-04 — recommended option taken): report-only
  `--acceptance-report` naming the sample size of every cohort; the bar's constants in
  `toolify-miner.py` are only ever changed by a deliberate human edit.

### D9. Cross-repo targeting via the house `--repo-root` convention

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Mined dances may belong to another repo's pipeline (e.g. an AlgoBooth mcp-test
  dance). How does a promotion land in that repo's queue?
- **Options:**
  - **A — `--repo-root <path>` on `--promote`, defaulting to the cwd git toplevel:** identical to
    `lazy-state.py` / `bug-state.py` / `lazy-queue-doc.py` addressing. The enqueue subprocess is
    already `--repo-root`-addressable; the stub SPEC is written into
    `<repo-root>/docs/features/<slug>/`; the ledger stays central (D6) with `target_repo`
    recorded.
  - **B — infer target repo from the log project-dir of the candidate's occurrences:** the
    encoded-cwd heuristic is plausible but a dance observed in claude-config sessions may still
    belong in AlgoBooth's queue — inference here is judgment, not derivation.
- **Recommendation:** A — following the uniform, already-learned addressing convention is not a
  new operator-facing choice; B misclassifies a judgment as mechanical.
- **Resolution:** A (operator-approved 2026-07-04 — recommended option taken);
  convention-following flag plumbing.

### D10. Naming stays human: `--promote` requires operator-supplied `--id` and `--name`

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Bar checklist step 3 ("Name the dance") maps a signature back to the human dance
  it represents and rejects mining artifacts. Can the materializer do it?
- **Options:**
  - **A — require `--id <kebab-slug>` and `--name "<title>"` from the operator; refuse without
    them:** the one judgment input the command needs; a candidate the operator cannot name is,
    per the checklist, a mining artifact and *should* fail to promote.
  - **B — auto-generate names from `sample_tools`:** produces plausible-sounding non-names
    (`bash-bash-read`) that defeat step 3's artifact filter.
- **Recommendation:** A. This is the operator-set checklist constraint carried into the CLI shape;
  everything downstream of the two supplied strings is deterministic.
- **Resolution:** A (operator-approved 2026-07-04 — recommended option taken); enforcing an
  existing operator-set constraint is not a new product call.

## User Experience

The operator's promotion loop, end to end:

```bash
# 1. Mine (unchanged miner; table now carries a candidate_id column)
python3 ~/.claude/scripts/toolify-miner.py --top 20

# 2. Promote an above-bar candidate into this repo's feature queue
python3 ~/.claude/scripts/toolify-promote.py --promote a3f9c21be04d \
    --id toolify-gate1-coverage-dance --name "Promote the Gate-1 coverage dance" \
    --repo-root ~/source/repos/claude-config

# 3. Decline one that is a mining artifact / not worth doing
python3 ~/.claude/scripts/toolify-promote.py --decline 7c0d55e1aa02 \
    --reason "artifact: overlapping window of the mark-complete dance"

# 4. See where everything stands (fresh mine ⨯ ledger join)
python3 ~/.claude/scripts/toolify-promote.py --status

# 5. Periodically: how is the bar performing?
python3 ~/.claude/scripts/toolify-promote.py --acceptance-report
```

On a successful `--promote` the command prints a one-block summary: the queue position
(tail, tier 2 under D4-B), the stub path, and the reminder that the item halts at `/spec`
Step 4.5 for interactive baseline-lock — auto-draft is not approval. Failure modes are loud and
side-effect-free: unknown `candidate_id` (exit 2, suggests re-mining), below-bar candidate
(exit 2, prints which predicate failed — judgment / run-count / score), duplicate in ledger
(exit 2, prints the prior record; D7 governs `--force`), duplicate `feature_id` in the target
queue (surfaced from `enqueue_adhoc`'s existing refusal).

The materialized stub SPEC contains: a Problem section built from the evidence block (the table
below), a "Direction (deliberately not locked)" section naming the candidate subcommand home per
bar checklist step 4 as a *suggestion*, the canonical stub Status value and blockquote trailer
(D5), and an open-questions trailer. Embedded evidence:

```
| candidate_id | signature | occurrences | runs | est_tokens/occ | score | sample_tools | mined |
```

`--status` output marks each fresh above-bar candidate as `NEW` / `promoted → <feature_id>` /
`declined (<reason>)` / `shipped` (receipt-derived), so the operator triages in one glance. The
`/lazy-batch-retro` report-only step (D3) prints the `NEW` rows with ready-to-run promote command
lines.

## Technical Design

```
~/.claude/projects/**/*.jsonl          toolify-miner.py (READ-ONLY, unchanged + candidate_id)
        │  read-only                          │ mine()/render_*()
        ▼                                     ▼
   session corpus  ──────────────▶  ranked candidates (markdown/JSON)
                                              │ operator picks + names (D10)
                                              ▼
                              toolify-promote.py  ── reads ──▶ toolify-ledger.json (dedup, D7)
                                    │                                ▲ append via _atomic_write
                                    │ shells                         │
                                    ▼                                │
              lazy-state.py --enqueue-adhoc [--tier 2 --stub --at tail]   (D4; single queue author)
                                    │  seeds docs/features/<slug>/ + queue entry + ROADMAP row
                                    ▼
              stub SPEC.md written into the seeded dir (evidence embedded; stub markers per D5)
                                    │
                                    ▼
              lazy pipeline: Step 4.5 → interactive /spec baseline-lock (operator gate PRESERVED)
```

- **`toolify-promote.py`** (new, stdlib-only, sibling of the miner): loads `toolify-miner.py` via
  `importlib.util.spec_from_file_location` and calls `mine()` fresh at promote time (or reads a
  saved `--from-json <report>` for offline use); resolves `candidate_id` by hashing each
  candidate's `signature`; enforces `above_bar` (recomputed, not trusted from a stale report);
  performs the ledger dedup check; shells `lazy-state.py --enqueue-adhoc` with the D4 flags via
  `subprocess.run(..., check=True)`; writes the stub SPEC.md into the seeded
  `docs/features/<slug>/` dir; appends the ledger entry last. Ordering is failure-safe: if the
  SPEC write fails after the enqueue, the queue entry + `ADHOC_BRIEF.md` still route the item to
  `/spec` via the Step-4 brief path (degraded but never wedged); if the ledger append fails, a
  re-run hits `enqueue_adhoc`'s duplicate-id refusal (loud, no double-draft).
- **Miner change (additive only):** `candidate_id` field on `Candidate`, threaded through
  `render_markdown()` / `render_json()`; the schema table in `toolify-bar.md` gains the row. No
  existing field changes; `test_toolify_miner.py`'s read-only hash tests and schema assertions
  continue to pass with the new key added to the expected set.
- **State-script change (additive only):** `--tier N`, `--stub`, `--at {head,tail}` on
  `lazy-state.py --enqueue-adhoc`, threading into `enqueue_adhoc()` (whose `tier` parameter
  already exists; `stub`/position are new parameters with byte-identical defaults). New `--test`
  fixtures pin: default invocation byte-identical to today; `--stub` writes `"stub": true`;
  `--at tail` appends. Feature-pipeline-only flags — the bug pipeline has no stub step and orders
  by severity, a justified divergence; run `lazy_parity_audit.py --repo-root .` to confirm the
  audit stays green.
- **House invariants honored:** all repo writes go through `lazy_core._atomic_write` (ledger) or
  the existing state-script author (queue/ROADMAP/spec-dir seed) — the materializer never
  hand-edits `queue.json`; the miner remains READ-ONLY over logs; everything is stdlib-only
  Python; completion truth stays receipt-gated (`shipped` derived from `COMPLETED.md`, never
  stored); the Step 4.5 operator gate is preserved by the D5 marker mechanics; no hook, marker,
  or run-scoped state is touched, so nothing here runs on the state-script compute path.
- **Template ownership:** the stub template (including the two canonical stub-marker forms) lives
  as a single constant in `toolify-promote.py`, with a test asserting
  `lazy-state.py::_spec_text_has_stub_marker(rendered_template)` is True and that a `/spec`-style
  rewrite (markers removed) flips it False — pinning the round-trip against the state machine's
  actual detector rather than a copied string.

## Implementation Phases

- **Phase 1 — Miner candidate identity.** Add `candidate_id` (SHA-256[:12] of `signature`) to
  `Candidate`, both renderers, and the `toolify-bar.md` schema table. Tests: id stability across
  passes, uniqueness on the existing fixtures, read-only hash test still green. Independently
  landable; the id is useful in bare mining reports even before promote exists.
- **Phase 2 — Enqueue path flags.** `--tier` / `--stub` / `--at {head,tail}` on
  `lazy-state.py --enqueue-adhoc` with byte-identical defaults; `--test` fixtures for each flag
  and for the default path; parity audit run recorded. (~1 session with Phase 1.)
- **Phase 3 — Materializer + ledger.** `toolify-promote.py` with `--promote` / `--decline` /
  `--status` / `--from-json`; ledger read/append via `_atomic_write`; stub template + the
  marker round-trip test; refusal tests (below-bar, unknown id, promoted-dup, declined-dup,
  missing `--id`/`--name`); failure-ordering test (SPEC write failure leaves a routable item).
  `test_toolify_promote.py` mirrors the miner test file's self-contained-runner pattern.
- **Phase 4 — Reports + docs + retro hook.** `--acceptance-report` (cohort stats, sample sizes,
  receipt-derived `shipped`); the report-only `/lazy-batch-retro` step (subject to D3); doc rows
  in `user/scripts/CLAUDE.md` and the root `CLAUDE.md` script table; `toolify-bar.md` checklist
  annotated with which steps are now mechanized (1-2 mechanized, 3 human-named, 4 stub-drafted,
  5-6 unchanged).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Candidate ids stable | Mine the same fixture corpus twice | Identical `candidate_id` per signature | `test_toolify_miner.py` new cases |
| Miner still read-only | Full mine + render with ids | Fixture log dir hash unchanged | existing `test_read_only_over_logs_dir_unchanged` |
| Enqueue defaults untouched | `--enqueue-adhoc` without new flags | Queue/brief/ROADMAP bytes identical to pre-change fixture | `lazy-state.py --test` |
| Stub routes to baseline-lock | Materialize into a scratch repo, run `lazy-state.py` | Probe dispatches `/spec` at Step 4.5 (not Step 5 fall-through) | scratch-repo probe JSON |
| Gate-bypass impossible by template | Render template, strip markers | `_spec_text_has_stub_marker` True before, False after | template round-trip test |
| Below-bar refused | `--promote` a judgment/single-run candidate | Exit 2 naming the failed predicate; no queue/ledger/spec writes | `test_toolify_promote.py` |
| Dedup enforced | Re-promote a promoted id; re-promote a declined id | Exit 2 with prior record; declined + `--force --reason` succeeds and records `forced` | `test_toolify_promote.py` |
| Ledger atomic + audited | Promote/decline on a real checkout | Ledger diff in `git status`; valid JSON after kill-mid-write simulation | `_atomic_write` usage + test |
| Acceptance report honest | Ledger with known cohorts | Rates + sample sizes match hand-count; `shipped` matches receipts | report fixture test |

## Open Questions

> All four formerly-OPEN product-behavior decisions were resolved at their recommended options
> (operator-approved 2026-07-04 — recommended option taken):

- **D3 — invocation cadence:** RESOLVED → A. Standalone on-demand promotion; `/lazy-batch-retro`
  gains a report-only step printing ready-to-run promote command lines but never invokes the
  materializer.
- **D4 — queue landing position:** RESOLVED → B. Tail insert at tier 2 with `stub: true` via
  additive default-off `--tier` / `--stub` / `--at {head,tail}` enqueue flags; promotion is
  roadmap work, and the operator escalates with `--reorder-queue` when warranted.
- **D7 — dedup override:** RESOLVED → B. Hard-refuse re-promoting `promoted`; `--force --reason`
  allowed for declined candidates only, with the override recorded (`forced: true`) in the ledger.
- **D8 — acceptance feedback:** RESOLVED → A. Report-only acceptance-rate view (sample sizes
  named); threshold tuning stays a deliberate human edit to `toolify-miner.py`.
- **Deferred empirical checks (implementation-time, not decisions):** run the miner over the real
  workstation corpus and confirm the top above-bar candidates still map to nameable dances at
  current log volume (bar doc's manual runtime verification); confirm in a scratch repo that a
  materialized stub with both `ADHOC_BRIEF.md` and a stub SPEC.md present routes Step 4.5 (stub
  branch) rather than the Step-4 brief branch; measure ledger size growth to confirm JSON (not
  JSONL) stays comfortable.

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the deliberate-promotion checklist in `toolify-bar.md`
  and the gate-preservation mechanics of `lazy-state.py`'s stub detection.
- `docs/features/unified-pipeline-orchestrator/toolify-bar.md` — the bar, candidate schema, and
  promotion checklist this feature mechanizes around.
- `user/scripts/toolify-miner.py` + `user/scripts/test_toolify_miner.py` — the consumed miner
  surface and the READ-ONLY invariant test pattern the new test file mirrors.
- `user/skills/_components/adhoc-enqueue.md` — the shared enqueue protocol whose script-owned
  single-author rule the materializer inherits.
- Sibling: `docs/features/skill-usage-miner/SPEC.md` — a separate consumer of the same log corpus;
  deliberately decoupled (its report may *point* at this pipeline but never invokes it).
