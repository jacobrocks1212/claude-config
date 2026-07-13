# Implementation Phases — Skill-Config Schema + Reference Lint

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete

**MCP runtime:** not-required — pure claude-config harness mechanics (a per-repo declared-files
manifest, a stdlib Python schema + reference-lint sibling of `lint-skills.py`, an authored
AlgoBooth `commit-policy.md` pointer file, and a KPI registry row). No Tauri app, no
MCP-reachable surface anywhere in this repo; validation is `pytest`
(`test_lint_skill_config.py`), the existing gate suite (`lint-skills.py`,
`project-skills.py`, `kpi-scorecard.py --lint`), and a live run of the new lint against the
real tree. This is the `standalone — no app integration` untestable class → `SKIP_MCP_TEST.md`
at the MCP gate.

## Cross-feature Integration Notes

No hard SPEC dependencies. Reuses (never modifies) three existing mechanisms named in the
SPEC's "Substantive (non-block) dependencies" block: `lint-skills.py`'s `!cat` regex forms
(`_FALLBACK_CAT` / `_FALLBACK_ECHO`, reused via `importlib` for DRY — not duplicated),
`build-queue-enforce.sh`'s documented `build-queue-ops.json` shape (read-only reference for
the D2 structural checker), and `friction-kpi-registry`'s KPI-registry pattern (this feature's
Phase 3 adds one row following that registry's schema and "drafted/pending-baseline,
follow-up documented" convention verbatim).

**File-ownership note (concurrent-agent run):** the reference sweep (Phase 2) discovered two
genuinely dead prose pointers (`long-build-ownership.md`, `cycle-prompt-addenda.md`) whose fix
would require editing `user/skills/lazy-batch/SKILL.md` / `lazy-bug-batch/SKILL.md` /
`_components/lazy-dispatch-template.md` — files owned by the concurrently-running SKILLS lane
(coupled-pair-generation in progress) for this run, not this feature. Per the SPEC's Open
Questions resolution, these are handled via a script-owned `SUPPRESSIONS` allowlist (visible,
reason-carrying WARNING findings, not silent passes) instead of an inline file edit, and are
named as a SKILLS-lane follow-up in this feature's completion artifacts.

---

### Phase 0: Quick win — kill the commit-policy.md failed-Read cluster

**Phase kind:** design

**Scope:** D4-A. Author `repos/algobooth/.claude/skill-config/commit-policy.md` as an
explicit pointer-adoption of the `_components/commit-and-push.md` default (no policy fork —
AlgoBooth has no commit conventions beyond the generic default, confirmed by grep over
`repos/algobooth/*.md`). Independent of the manifest machinery (Phases 1-2) so the dominant
cost dies first.

**Deliverables:**
- [x] `repos/algobooth/.claude/skill-config/commit-policy.md` — pointer-adoption content
  (defers to `~/.claude/skills/_components/commit-and-push.md`, notes AlgoBooth is a personal
  repo so push is unblocked, no policy duplication).

**Minimum Verifiable Behavior:** every one of the 15 skill/component sources that reference
`.claude/skill-config/commit-policy.md` now resolves the primary Read against AlgoBooth
instead of falling back after a failed lookup.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] `lint-skill-config.py`'s reference sweep confirms `commit-policy.md` is `on_disk` for
  algobooth (no longer needs an `intended_absent` entry) and every citing skill/component
  resolves clean. *(Evidence: `SKIP_MCP_TEST.md` + a live `lint-skill-config.py` run — 0
  findings for `commit-policy.md` across both repos.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (first phase).

**Files likely modified:** `repos/algobooth/.claude/skill-config/commit-policy.md` (new).

**Testing Strategy:** Confirmed by the Phase 2 reference sweep (the sweep is the acceptance
test for this phase — a real dangling/undeclared finding for `commit-policy.md` would fail it).

**Integration Notes for Next Phase:** Phase 1's MANIFEST.json for algobooth declares this file
in `provides` (22 total entries, matching the SPEC's "22 files incl. Phase 0's").

---

### Phase 1: MANIFEST.json schema + authored manifests + JSON-schema checkers

**Phase kind:** design

**Scope:** D1 + D2. `MANIFEST.json` schema (`schema_version`, `provides[]`,
`intended_absent[{file,reason}]`, `json_schemas{}`); authored manifests for algobooth (22
files) and cognito-forms (16); a stdlib structural checker for `build-queue-ops.json`
(dispatched via `json_schemas`); pytest fixtures for every violation class.

**Deliverables:**
- [x] `user/scripts/lint-skill-config.py` — `validate_manifest` (schema shape, duplicate
  detection, `intended_absent` reason-hygiene, `provides`/`intended_absent` overlap
  contradiction, unknown `json_schemas` key), `bidirectional_provides_check`
  (declared-but-missing / present-but-undeclared, both directions), `check_build_queue_ops`
  (structural checker keyed via `json_schemas`), `JSON_SCHEMA_CHECKERS` registry, an
  "unregistered JSON file" WARNING for any `*.json` in skill-config/ with no `json_schemas`
  entry.
- [x] `repos/algobooth/.claude/skill-config/MANIFEST.json` — 22 `provides` entries, 13
  `intended_absent` entries (each with a reason), `json_schemas: {"build-queue-ops.json":
  "build-queue-ops"}`.
- [x] `repos/cognito-forms/.claude/skill-config/MANIFEST.json` — 16 `provides` entries, 16
  `intended_absent` entries (each with a reason), same `json_schemas` map.
- [x] `user/scripts/test_lint_skill_config.py` (Phase 1 portion) — schema fixtures: bad
  `schema_version`, non-list `provides`, duplicate `provides`, `intended_absent` missing
  reason, duplicate `intended_absent` entry, `provides`/`intended_absent` overlap, unknown
  `json_schemas` key; bidirectional-check fixtures (both directions); `build-queue-ops.json`
  fixtures: bad version, bad `kind`, missing `exec`, bad `lane`, empty `deny`, `skill` missing
  leading `/`, empty `ops`.

**Minimum Verifiable Behavior:** `python3 user/scripts/lint-skill-config.py --repo-root .`
finds zero manifest-schema / bidirectional-provides / json-schema ERRORS against the real
tree; corrupting any real manifest field or `build-queue-ops.json` entry makes it exit 1
naming the repo, field, and file.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Lint green on the two real manifests + two real `build-queue-ops.json` files; red on
  each fixture violation (named field). *(Evidence: `SKIP_MCP_TEST.md` —
  `test_lint_skill_config.py` Phase-1 fixtures + a live `--repo-root .` run.)*
  <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 0 (algobooth's manifest declares the Phase-0 file).

**Files likely modified:** `user/scripts/lint-skill-config.py` (new),
`user/scripts/test_lint_skill_config.py` (new),
`repos/algobooth/.claude/skill-config/MANIFEST.json` (new),
`repos/cognito-forms/.claude/skill-config/MANIFEST.json` (new).

**Testing Strategy:** Hermetic pytest fixtures build a minimal two-repo tmp tree (`repo-a`,
`repo-b`) for every schema/bidirectional/JSON-schema class; the real manifests are additionally
exercised by the Phase 2 self-check (below) rather than duplicated as Phase-1-only fixtures.

**Integration Notes for Next Phase:** Phase 2's reference sweep consumes the SAME manifests'
`intended_absent` map to decide OK vs. ERROR vs. fallback-less-pointer for every cross-repo
reference.

---

### Phase 2: Reference sweep — `!cat` forms AND prose mentions, per repo, honoring markers

**Phase kind:** design

**Scope:** D3. Collect every `.claude/skill-config/<file>` mention across user-level skill
sources (`user/skills/**/SKILL.md` + `user/skills/_components/**/*.md`, checked against every
repo) and repo-scoped skill sources (`repos/<name>/.claude/skills/**/SKILL.md`, checked only
against that repo); resolve each against the repo's on-disk skill-config/ files, honoring
`intended_absent`; classify findings as dangling-reference (undeclared+absent),
fallback-less-pointer (declared absent but the reference has no fallback form — the
`long-build-ownership.md` class), or OK. Burn down the initial finding list against the real
tree via the script-owned `SUPPRESSIONS` allowlist (visible WARNING, reason required) for the
two findings this feature does not own the fix for.

**Deliverables:**
- [x] `user/scripts/lint-skill-config.py` (Phase 2 portion) — `scan_source_for_refs` (reuses
  `lint-skills.py`'s `_FALLBACK_CAT`/`_FALLBACK_ECHO` via `importlib`, plus a prose regex
  anchored on real file extensions + a fallback-language heuristic + a self-reference
  exclusion for `_components/<name>.md` describing its own override path), `_check_refs_
  against_repo`, `SUPPRESSIONS` allowlist (2 real dead-pointer classes + 1 aspirational
  mention, each reasoned).
- [x] Small additive hook-in on `user/scripts/lint-skills.py`: `--check-skill-config` flag
  (default off — byte-identical existing behavior without it) folding
  `lint-skill-config.run()`'s errors/warnings into the existing exit code, satisfying the
  SPEC's "no new invocation surface" design intent without a deep edit to the existing file.
- [x] `user/scripts/test_lint_skill_config.py` (Phase 2 portion) — dangling-reference,
  fallback-less-pointer (declared-but-no-fallback), intended-absent-with-fallback-is-OK,
  suppression downgrade (error→warning, reason preserved), repo-scoped-skill isolation
  (checked only against its own repo), self-referential component prose is not a dangling
  reference, and a self-check that the REAL tree lints clean (0 errors).

**Minimum Verifiable Behavior:** `python3 user/scripts/lint-skill-config.py --repo-root .`
exits 0 against the real tree (6 documented, reasoned WARNINGs; 0 errors);
`python3 user/scripts/lint-skills.py --check-skill-config` folds the same result in with no
change to the flag-less invocation's output.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Sweep exit 0 on the real tree; every finding class has a fixture; the two named known
  instances (`long-build-ownership.md`, `commit-policy.md`) are each provably detected/fixed
  by the fixture/lint that models them. *(Evidence: `SKIP_MCP_TEST.md` —
  `test_lint_skill_config.py` full suite (29 tests) + `python3 user/scripts/lint-skill-config.py
  --repo-root .` + `python3 user/scripts/lint-skills.py --check-skill-config` +
  `python3 user/scripts/lint-skills.py --check-projected --check-capabilities` +
  `python3 user/scripts/project-skills.py`, all green.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (the manifests this phase reads).

**Files likely modified:** `user/scripts/lint-skill-config.py` (extended),
`user/scripts/lint-skills.py` (small additive hook-in),
`user/scripts/test_lint_skill_config.py` (extended).

**Testing Strategy:** Hermetic pytest fixtures for every finding class (see Deliverables)
plus a non-hermetic subprocess self-check (`test_this_repo_is_clean`) mirroring
`test_doc_drift_lint.py`'s house pattern — the real repo is itself the acceptance fixture.

**Integration Notes for Next Phase:** Phase 3's KPI row measures the residual class this sweep
now prevents; no code dependency, just the narrative link (the KPI's `notes` field cites this
phase's Phase 0 + Phase 1-2 work as what should drive the signal toward zero / prevent new
clusters).

---

### Phase 3: Windowed KPI collector + registry follow-up

**Phase kind:** design

**Scope:** Register the drafted `skill-config-broken-reference-reads` row (already fully
specified in the SPEC's KPI Declaration) into `docs/kpi/registry.json`, bound to the already-
registered `deny-ledger` / `process-friction-count` selector (the coarse proxy channel —
`incident-scan.py` clusters recurring tool-error friction into the deny ledger as
`process-friction` entries). Documents, rather than blocks on, the dedicated
session-log-mining selector the SPEC names as a SHOULD-have follow-up (mirrors the
`build-queue-wait-time-p50` row's own "not computable yet, documented follow-up" precedent in
this same registry).

**Deliverables:**
- [x] `docs/kpi/registry.json` — new `skill-config-broken-reference-reads` row (`system:
  skill-config`, `signal: {source: deny-ledger, selector: process-friction-count}`,
  `baseline.provenance: pending`, `repo_scope: all`, `notes` documenting the coarse-proxy
  choice + the deferred dedicated-selector follow-up).
- [x] `docs/kpi/SCORECARD.md` — regenerated (`kpi-scorecard.py --repo-root .`).

**Minimum Verifiable Behavior:** `python3 user/scripts/kpi-scorecard.py --lint --repo-root .`
exits 0; the new row renders (NO-DATA or a real count, never a fabricated zero) in a fresh
`--stdout` render.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the
implementation agent):*
- [x] Registry lint green including the new row; scorecard render includes the row.
  *(Evidence: `SKIP_MCP_TEST.md` — `kpi-scorecard.py --lint --repo-root .` +
  `kpi-scorecard.py --repo-root .` live runs.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 2 (the row's `notes` narrates what Phases 0-2 do to the signal).

**Files likely modified:** `docs/kpi/registry.json`, `docs/kpi/SCORECARD.md`.

**Testing Strategy:** `kpi-scorecard.py`'s own existing lint suite already covers row-schema
validity generically; no new pytest needed for a single conforming row addition.

**Integration Notes for Next Phase:** None — last phase. The DEFERRED dedicated-selector +
`--capture-baseline` work is named as an explicit follow-up in the row's `notes`, not a gap in
this feature's own completion.
