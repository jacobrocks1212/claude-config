# Research — Auto-Promotion Pipeline for Toolify Candidates

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **`user/scripts/toolify-miner.py`** — the entire analytic half already exists: `mine()` returns
  ranked `Candidate` objects with `signature` / `occurrences` / `run_count` /
  `est_tokens_per_occurrence` / `score` / `deterministic` / `above_bar` / `sample_tools`;
  `signature()` is deterministic (tool name + sorted top-level argument keys, values elided), which
  is what makes a content-hash `candidate_id` a stable cross-pass key. The miner's READ-ONLY-over-
  logs invariant is pinned by `test_toolify_miner.py::test_read_only_over_logs_dir_unchanged`
  (dir-hash before/after) — the design keeps all write paths out of that file (SPEC D1).
- **`docs/features/unified-pipeline-orchestrator/toolify-bar.md`** — the deliberate-promotion
  checklist is the product contract this feature mechanizes around. Steps 1-2 (mine, confirm
  above-bar) are mechanizable verbatim; step 3 (name the dance) is explicitly a judgment filter
  ("a signature with no clear real-world dance behind it is a mining artifact"), which is why the
  promote command *requires* operator-supplied `--id`/`--name` rather than generating them; steps
  5-6 (implement under gates, rewire callers) stay in the normal pipeline. The checklist's step-7
  note (future auto-initiation still keeps implementation reviewed) bounds how far any vN
  automation may go.
- **`lazy-state.py::enqueue_adhoc` (line 582) + `_components/adhoc-enqueue.md`** — the existing
  script-owned queue insert: prepend at position 0 with `tier: 0` / `adhoc: true`, seed
  `docs/features/<slug>/ADHOC_BRIEF.md`, append a ROADMAP.md row, refuse duplicate ids, all via
  `_atomic_write`. Notably `enqueue_adhoc()` already takes a `tier` parameter the CLI does not
  expose — the D4 extension is mostly plumbing. The component's Notes section establishes the rule
  the materializer inherits: queue mutations are Bash calls into the state script, never
  `Write`/`Edit` hand-edits.
- **Stub-spec detection mechanics (`lazy-state.py:1076-1155`)** — the decisive constraint found
  during desk research: `is_stub_spec()` fires on an in-SPEC stub marker OR the queue flag, but
  `_stub_is_queue_flag_only()` treats "queue flag set AND no in-SPEC marker" as the
  *post-baseline* state and **clears the flag and falls through** (the
  `stub-spec-route-loops-until-queue-stub-cleared` fix). A materializer that set only the queue
  flag would therefore silently skip the Step 4.5 baseline-lock — the operator gate the stub
  explicitly requires preserved. Hence SPEC D5: the template must emit the canonical in-SPEC
  stub Status value and blockquote trailer (the anchored forms `_spec_text_has_stub_marker`
  matches), and a round-trip test pins the template against the real detector.
- **Queue ordering context** — `docs/features/queue.json`'s `_note` ("Tier orders priority;
  explicit queue order takes precedence") plus `lazy_core.merged_priority` (feature `tier` int
  normalized against bug severity for `--next-merged`) is why D4 treats the head/tier-0 insert as
  wrong for promotions: a tier-0 stub would outrank every bug in the merged work-list.
- **`--reorder-queue`** — the operator's existing escalation path for a promoted stub that turns
  out to be urgent; it is why D4-B can safely default to tail.
- **Receipt-gated completion** (`docs/features/CLAUDE.md`, `user/scripts/CLAUDE.md`) — the reason
  the ledger never stores a `shipped` status: `COMPLETED.md` is the single receipt-gated truth,
  and the acceptance report derives shipped from it at read time.
- **Hyphenated-module import pattern** — `test_toolify_miner.py:44-52` already imports
  `toolify-miner.py` via `importlib.util.spec_from_file_location`; `toolify-promote.py` reuses the
  same pattern rather than renaming the miner or duplicating its logic.
- **`enqueue_adhoc_bug` (lazy-state.py:671)** — precedent for one script shelling another state
  script as a subprocess rather than reimplementing its write (the "reuse, never reimplement"
  shape the materializer follows for the feature enqueue).

## External prior art & concepts

Training-knowledge, not live research:

- **Dependabot / Renovate** — the closest well-known shape: an analyzer detects an actionable
  condition, *auto-drafts* the change artifact (a PR), and a human gate (review + merge) decides.
  Their key lesson adopted here: auto-drafting with a mandatory human gate keeps trust, while
  auto-merge is a separate, later, opt-in decision — mirrored by D3's standalone-first cadence and
  the bar doc's step-7 boundary.
- **Issue-triage / stale bots** — demonstrate the failure mode of B-style auto-materialization:
  bots that open items automatically train humans to ignore them (queue spam). Supports D3-A and
  the artifact filter in D10.
- **Scaffolding generators (cookiecutter, yeoman, `cargo generate`)** — deterministic
  template-instantiation from a small set of human-supplied names, everything else derived; the
  materializer's stub template follows this shape (two human strings in, deterministic document
  out).
- **Human-in-the-loop threshold tuning (alerting practice, e.g. SLO burn-rate reviews)** —
  operational consensus that alert/gate thresholds should be tuned from recorded
  acceptance/actionability data by humans on a cadence, not self-adjusted online; supports D8-A
  report-only, including the sample-size caveat.
- **Dead-letter/decision ledgers in workflow engines** — recording declined work with reasons so
  re-proposals are deliberate (`--force --reason`) rather than amnesiac, as in D7-B.

## Alternatives analysis

- **Materializer home (D1).** A miner subcommand minimizes file count but couples a writing code
  path to a file whose whole documented identity is "read-only over logs" and whose test suite
  hashes directories to prove it; a separate script costs one file and keeps both contracts
  independently testable. Skill-prose drafting was rejected on the house invariant: deterministic
  writes belong in scripts (`user/skills/CLAUDE.md`: "behavior that must be deterministic belongs
  in a script").
- **Queue insertion (D4).** Reusing `--enqueue-adhoc` verbatim (head, tier 0, `adhoc: true`) was
  attractive for zero script change, but desk research showed it is semantically wrong twice over:
  it jumps the operator's curated order, and tier 0 distorts `--next-merged`'s cross-pipeline
  ordering. Composing enqueue + `--reorder-queue --to tail` avoids new flags but leaves lying
  metadata (`tier: 0`, `adhoc: true`) on a non-ad-hoc item. Additive flags with byte-identical
  defaults won: one queue author, honest metadata, fixture-pinned defaults.
- **Gate preservation (D5).** Queue-flag-only stubs *look* like the lighter design until
  `_stub_is_queue_flag_only` is read closely — the flag-only state is reserved as the
  "baseline already locked" signal, so the in-SPEC markers are the only mechanics that route the
  interactive gate. No real alternative survives contact with the state machine.
- **Ledger placement (D6).** Per-target-repo ledgers fragment the acceptance data that D8's report
  needs joined; untracked state loses provenance. Central + git-tracked in claude-config matches
  where the miner, the bar doc, and the harness's self-improvement loop live.
- **Dedup strictness (D7).** Forever-declines are simpler but wrong for a growing corpus (the
  evidence behind a candidate strengthens over time); silent re-promotion erodes the ledger.
  Reasoned `--force` for declined-only threads the needle and keeps promoted-side collisions
  impossible (they would also trip `enqueue_adhoc`'s duplicate-id refusal).

## Pitfalls & risks

- **Silent gate bypass** — the worst failure: a template drift that drops the in-SPEC stub markers
  turns every promotion into an unreviewed baseline. Mitigated by the round-trip test against
  `_spec_text_has_stub_marker` itself (not a copied string), so the test fails if either side
  changes.
- **Queue spam / candidate rot inversion** — over-mechanized promotion (D3-B) trades rotting
  candidates for a rotting queue. The standalone cadence plus the retro's report-only resurface is
  the deliberate middle.
- **Partial-failure states** — enqueue succeeded but SPEC write failed: designed to degrade to the
  Step-4 `ADHOC_BRIEF.md` route (item still reaches `/spec`); ledger append failed: re-run trips
  the duplicate-id refusal loudly. Neither wedges the pipeline; both are tested.
- **Ledger as a second source of truth** — storing `shipped` would eventually contradict the
  receipt gate; derived-at-read-time avoids the class entirely.
- **Statistical over-reach in the acceptance report** — with single-digit promotions, rates are
  noise; the report must print sample sizes, and threshold edits stay human (D8).
- **Coupled-script drift** — the enqueue flags touch `lazy-state.py`; the change is
  feature-pipeline-only (no bug-side stub step), which must be recorded as a justified divergence
  and confirmed against `lazy_parity_audit.py` to avoid a false parity failure later.
- **Falsifiability / dead-weight check** — this feature is itself measurable by its own ledger: if
  after a few months the ledger shows near-zero promotions (the friction was never the clerical
  work) or near-100% declines (the bar surfaces junk), the feature or the bar's constants are the
  defect, and the acceptance report is the instrument that shows it.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 materializer home | Separate `toolify-promote.py` sibling script | High |
| D2 candidate identity | SHA-256[:12] of signature, additive miner column | High |
| D3 invocation cadence (OPEN) | Standalone on-demand; retro reports, never invokes | Medium-high |
| D4 queue landing (OPEN) | Tail + tier 2 + `stub: true` via additive enqueue flags | Medium-high |
| D5 stub authoring contract | In-SPEC stub markers required; round-trip-tested template | High |
| D6 ledger location/schema | Central git-tracked JSON beside `toolify-bar.md`; shipped derived | High |
| D7 dedup semantics (OPEN) | Refuse repeats; `--force --reason` for declined only | Medium |
| D8 acceptance feedback (OPEN) | Report-only; bar constants stay human-edited | High |
| D9 cross-repo targeting | `--repo-root` house convention, central ledger | High |
| D10 naming | Operator-supplied `--id`/`--name` required | High |
