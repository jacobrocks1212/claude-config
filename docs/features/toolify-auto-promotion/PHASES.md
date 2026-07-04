# Implementation Phases — Auto-Promotion Pipeline for Toolify Candidates

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness mechanics (stdlib Python scripts +
one skill-prose step). No Tauri app, no MCP-reachable surface; validation is pytest
(`test_lazy_core.py` et al.), the self-contained `test_toolify_miner.py` /
`test_toolify_promote.py` runners, `lazy-state.py --test` / `bug-state.py --test` smoke baselines,
`lazy_parity_audit.py`, and `lint-skills.py`. This is the `standalone — no app integration`
untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. Substantive dependencies are implemented contracts, not sibling specs:

- **`unified-pipeline-orchestrator` Phase 4 (shipped):** owns `toolify-miner.py`, its READ-ONLY
  invariant (`test_toolify_miner.py` dir-hash tests), and `toolify-bar.md` (bar + schema +
  checklist). Phase 1 here adds the additive `candidate_id` field; Phase 4 annotates the checklist
  with which steps are now mechanized. The miner's read-only contract is untouched — all write
  paths live in the new sibling `toolify-promote.py` (D1-B).
- **`lazy-state.py --enqueue-adhoc` / `enqueue_adhoc()` (shipped, `lazy-state.py:582`):** the
  single queue author the materializer shells. Phase 2 extends it with default-off `--stub` /
  `--at {head,tail}` flags (`--tier` already exists); defaults byte-identical, pinned by the
  `--test` baseline.
- **Stub-spec mechanics (`stub-spec-route-loops-until-queue-stub-cleared` fix, shipped):**
  `_spec_text_has_stub_marker` (`lazy-state.py:1086`) / `is_stub_spec` / `_stub_is_queue_flag_only`
  (`lazy-state.py:1147`) define the D5 contract the stub template must satisfy — in-SPEC markers +
  queue flag, so Step 4.5 routes interactive `/spec` and the post-baseline flag-only state clears
  correctly.
- **`skill-usage-miner` (sibling spec, decoupled):** a separate consumer of the same log corpus;
  no shared code, no integration needed.

---

### Phase 1: Miner candidate identity

**Phase kind:** design

**Scope:** Give every mined candidate a stable, copy-pasteable identity: `candidate_id` =
first 12 hex chars of SHA-256 of the signature string (D2-A), additive on the miner's `Candidate`
schema and both render paths. Independently landable — useful in bare mining reports before
promote exists.

**Deliverables:**
- [x] `toolify-miner.py`: module-level `candidate_id(sig: str) -> str` helper (single derivation,
  nothing else re-hashes); `candidate_id` field on `Candidate`; populated in `mine()`; additive
  `candidate_id` column in `render_markdown()`; additive `candidate_id` key in `render_json()`.
- [x] `test_toolify_miner.py` new cases (registered by the `_TESTS` globals sweep): id stability
  across two mining passes over the same fixture corpus; id uniqueness across the fixture
  candidates; id present in markdown + JSON renders; id derivable offline from a saved report's
  signature; existing read-only dir-hash test still green (no expectations removed).
- [x] `toolify-bar.md` candidate-schema table: `candidate_id` row.

**Minimum Verifiable Behavior:** `mine()` over the fixture corpus twice yields identical
`candidate_id` per signature; `render_json()` rows carry the id; `sha256(signature)[:12]`
recomputed offline matches the emitted id.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Candidate ids stable + unique across passes on the fixture corpus. *(Evidence:
  `SKIP_MCP_TEST.md` — `test_toolify_miner.py` new cases.)* <!-- verification-only -->
- [ ] Miner over the REAL workstation corpus still maps top above-bar rows to nameable dances,
  now with ids (bar doc's manual runtime verification). DEFERRED: no `~/.claude/projects` corpus
  exists in this cloud container — workstation-only check. <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/toolify-miner.py`, `user/scripts/test_toolify_miner.py`,
`docs/features/unified-pipeline-orchestrator/toolify-bar.md`.

**Testing Strategy:** Extend the existing self-contained runner's fixture builders; TDD (new
tests red first — module lacks `candidate_id`); the READ-ONLY dir-hash tests are the invariant
guard that the additive change stays read-only.

**Integration Notes for Next Phase:** Phase 3's promote resolves operator-supplied ids against
`candidate_id(signature)` — the helper added here is the single derivation both sides use.

---

### Phase 2: Enqueue path flags

**Phase kind:** integration

**Scope:** D4-B landing mechanics: additive, default-off `--stub` and `--at {head,tail}` flags on
`lazy-state.py --enqueue-adhoc` (the `--tier` flag already exists and threads), threaded into
`enqueue_adhoc()` as new `stub`/`at` params with byte-identical defaults. Feature-pipeline-only —
a justified divergence from `bug-state.py` (no stub step; severity ordering).

**Deliverables:**
- [x] `enqueue_adhoc(…, stub: bool = False, at: str = "head")`: `stub=True` adds `"stub": true`
  to the queue entry (key absent otherwise — byte-identical default); `at="tail"` appends instead
  of prepending (`queue_position` reported honestly).
- [x] CLI: `--stub` (store_true) + `--at {head,tail}` (default `head`) on `lazy-state.py`;
  threaded in the `args.enqueue_adhoc` feature branch; `--stub`/`--at tail` combined with
  `--type bug` is refused loudly (`_die`, exit 2) — never silently ignored.
- [x] `--test` fixtures (inline functional checks beside the existing `[enqueue]` block): default
  invocation writes NO `stub` key + prepends (byte-identical to today); `stub=True` writes
  `"stub": true`; `at="tail"` appends after existing entries with correct `queue_position`;
  tier threads (existing param).
- [x] Baseline: `tests/baselines/lazy-state-test-baseline.txt` regenerated ONLY via
  `_normalize_smoke_output` (new fixture prints legitimately change the output);
  `bug-state-test-baseline.txt` untouched.
- [x] Parity audit run recorded: `lazy_parity_audit.py --repo-root .` exit 0 (the audit's
  state-script checks name five fixed surfaces, none enqueue-flag-shaped — divergence confirmed
  un-audited and documented in `user/scripts/CLAUDE.md`).

**Minimum Verifiable Behavior:** `--enqueue-adhoc --id x --name X` produces a queue entry byte-
identical to pre-change; adding `--stub --at tail --tier 2` lands `{id, name, spec_dir, tier: 2,
adhoc: true, stub: true}` at the queue tail.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Enqueue defaults untouched: default-path fixture asserts no `stub` key + position 0.
  *(Evidence: `SKIP_MCP_TEST.md` — `lazy-state.py --test` `[enqueue-flags]` fixture.)*
  <!-- verification-only -->
- [x] Parity audit stays exit 0 with the feature-only flags present. *(Evidence:
  `SKIP_MCP_TEST.md` — `lazy_parity_audit.py` run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** None (parallel-safe with Phase 1; sequenced for one-session flow).

**Files likely modified:** `user/scripts/lazy-state.py`,
`user/scripts/tests/baselines/lazy-state-test-baseline.txt`, `user/scripts/CLAUDE.md` (CLI
surface line — folded into Phase 4's doc pass).

**Testing Strategy:** TDD inside the smoke harness (add the fixture asserting the new behavior,
watch it fail, implement); `test_lazy_core.py` baseline-diff test guards the regen; both `--test`
harnesses re-run.

**Integration Notes for Next Phase:** Phase 3 shells exactly
`lazy-state.py --enqueue-adhoc --id <slug> --name <title> --brief <text> --tier 2 --stub --at
tail --repo-root <target>`; the `"stub": true` queue flag pairs with the in-SPEC markers Phase 3
writes (D5 two-marker contract).

---

### Phase 3: Materializer + ledger

**Phase kind:** feature

**Scope:** `user/scripts/toolify-promote.py` (stdlib-only sibling) with `--promote` / `--decline`
/ `--status` / `--from-json` / `--id` / `--name` / `--repo-root` / `--reason` / `--force` (+
`--logs` and `--ledger` seams); the central git-tracked ledger; the D5 stub template with the
marker round-trip pinned against the real detector.

**Deliverables:**
- [x] `toolify-promote.py`: imports the miner via `importlib.util.spec_from_file_location`
  (test-file pattern) for `mine()`/`signature()`/`candidate_id()`; imports `lazy_core` (plain
  module) for `_atomic_write`.
- [x] `--promote <cid>`: requires `--id` (kebab) + `--name` (D10); resolves the candidate from a
  fresh `mine()` (or `--from-json <report>`); enforces `above_bar` RECOMPUTED from the miner's
  constants (never trusted from a stale report), naming the failed predicate (judgment /
  run-count / score) on refusal; ledger dedup per D7-B (promoted → hard refuse; declined →
  `--force --reason` only, recorded `forced: true`); then, in failure-safe order: shell
  `lazy-state.py --enqueue-adhoc … --tier 2 --stub --at tail` → write the stub SPEC.md into the
  seeded dir → append the ledger entry last. Prints the one-block summary (queue position, stub
  path, Step-4.5 baseline-lock reminder).
- [x] `--decline <cid>`: requires `--reason`; resolves the candidate (fresh mine or
  `--from-json`); refuses an already-recorded id (prior record printed); appends a `declined`
  ledger entry. No repo writes beyond the ledger.
- [x] Stub template as a single module constant: canonical `**Status:** Draft (pre-Gemini)`
  Status line + `> Draft (pre-Gemini). …` blockquote trailer (the two anchored
  `_spec_text_has_stub_marker` forms), evidence table (candidate_id / signature / occurrences /
  runs / est_tokens/occ / score / sample_tools / mined date), Problem section, "Direction
  (deliberately not locked)" suggestion, open-questions trailer. Hard-excludes decided-looking
  artifacts: no RESEARCH.md, no PHASES.md, no sentinel, no locked decisions.
- [x] Ledger `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` (seeded empty,
  git-tracked): `{"entries": {<candidate_id>: {signature, status, feature_id, target_repo,
  decided_at, reason, evidence: {occurrences, run_count, est_tokens_per_occurrence, score,
  sample_tools}, forced}}}`; `shipped` NEVER stored — derived at read time from
  `<target_repo>/docs/features/<feature_id>/COMPLETED.md`.
- [x] `--status`: fresh mine (or `--from-json`) ⨯ ledger join; each above-bar candidate marked
  `NEW` / `promoted → <feature_id>` / `declined (<reason>)` / `shipped` (receipt-derived).
- [x] `test_toolify_promote.py` (mirrors the miner test's self-contained runner): template
  round-trip (real `_spec_text_has_stub_marker` True on the rendered template, False after a
  `/spec`-style marker strip); refusals (below-bar naming each failed predicate, unknown id,
  promoted-dup, declined-dup without force, missing `--id`/`--name`, malformed slug,
  `--force` without `--reason`); `--force --reason` success recording `forced: true`;
  failure-ordering (SPEC write failure ⇒ queue entry + brief still present ⇒ routable, ledger
  UNWRITTEN, re-run refused loudly by the duplicate-id enqueue); ledger atomicity via
  `_atomic_write`; decline path; status join; scratch-repo probe (materialized stub routes
  `lazy-state.py` Step 4.5 stub branch, NOT the Step-4 brief branch, NOT Step-5 fall-through).

**Minimum Verifiable Behavior:** In a scratch repo, `--promote <id-of-above-bar-fixture-candidate>
--id demo-dance --name "Demo"` lands a tail/tier-2/stub queue entry + a marker-bearing stub SPEC +
one `promoted` ledger entry; `lazy-state.py --repo-root <scratch>` dispatches `/spec` at
`Step 4.5: stub-spec detected`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Stub routes to baseline-lock: scratch-repo probe JSON shows Step 4.5 (stub branch), not
  Step-5 fall-through. *(Evidence: `SKIP_MCP_TEST.md` — `test_toolify_promote.py` probe test.)*
  <!-- verification-only -->
- [x] Gate-bypass impossible by template: marker round-trip against the REAL detector.
  *(Evidence: `test_toolify_promote.py` round-trip test.)* <!-- verification-only -->
- [x] Ledger atomic + audited: promote/decline diffs appear in `git status`; ledger remains valid
  JSON (written via `_atomic_write`). *(Evidence: `test_toolify_promote.py` +
  `_atomic_write` usage.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phase 1 (`candidate_id`), Phase 2 (enqueue flags).

**Files likely modified:** `user/scripts/toolify-promote.py` (new),
`user/scripts/test_toolify_promote.py` (new),
`docs/features/unified-pipeline-orchestrator/toolify-ledger.json` (new).

**Testing Strategy:** Hermetic: fixture log dirs (reuse the miner test's builders), temp scratch
repos, `--ledger`/`--logs` seams, `LAZY_STATE_DIR` env for the probe test; monkeypatch the
module's spec-writer for the failure-ordering case. TDD per behavior.

**Integration Notes for Next Phase:** Phase 4's `--acceptance-report` reads the same ledger loader
+ receipt-derivation helper; the retro step prints `--status`-shaped NEW rows as ready-to-run
promote lines.

---

### Phase 4: Reports + docs + retro hook

**Phase kind:** integration

**Scope:** `--acceptance-report` (D8-A, report-only); the `/lazy-batch-retro` report-only step
(D3-A); doc rows everywhere the SPEC lists them; checklist annotations.

**Deliverables:**
- [ ] `--acceptance-report`: totals (promoted / declined / shipped-derived), acceptance rate,
  score + run-count distribution per cohort, and the SAMPLE SIZE named on every rate (a
  two-candidate "100%" is labeled as such). Observations only — never edits the bar's constants.
- [ ] `test_toolify_promote.py` report cases: rates + sample sizes match a hand-counted fixture
  ledger; `shipped` matches receipts on disk.
- [ ] `user/skills/lazy-batch-retro/SKILL.md`: new report-only Step 6d — runs the miner
  (read-only), joins the ledger, prints NEW above-bar candidates with ready-to-run
  `toolify-promote.py --promote <id> --id <slug> --name "<title>"` lines; NEVER invokes the
  materializer; degrades gracefully (no corpus / no miner → skip with a note). Projection +
  lint re-run (lane-local output dir).
- [ ] Docs: `user/scripts/CLAUDE.md` (script-table row for `toolify-promote.py`, miner row
  updated for `candidate_id`, CLI-surface line for the new enqueue flags + justified-divergence
  note); root `CLAUDE.md` script-table row; `toolify-bar.md` checklist annotated (steps 1–2
  mechanized, 3 human-named, 4 stub-drafted, 5–6 unchanged) + ledger/promote cross-references.

**Minimum Verifiable Behavior:** `--acceptance-report` over a fixture ledger prints cohort stats
with sample sizes matching a hand count; `lint-skills.py` + projection clean after the SKILL.md
edit.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [ ] Acceptance report honest: fixture cohorts hand-counted; shipped receipt-derived.
  *(Evidence: `SKIP_MCP_TEST.md` — `test_toolify_promote.py` report tests.)*
  <!-- verification-only -->
- [ ] Skill projection + lint green after the retro-step edit. *(Evidence: `SKIP_MCP_TEST.md` —
  `project-skills.py` lane-local run + `lint-skills.py`.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phase 3 (ledger + status join).

**Files likely modified:** `user/scripts/toolify-promote.py`,
`user/scripts/test_toolify_promote.py`, `user/skills/lazy-batch-retro/SKILL.md`,
`user/scripts/CLAUDE.md`, `CLAUDE.md`,
`docs/features/unified-pipeline-orchestrator/toolify-bar.md`.

**Testing Strategy:** Fixture-ledger report tests (TDD); docs are lint-gated
(`lint-skills.py`, projection); full gate suite as final acceptance.
