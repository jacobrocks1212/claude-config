# Implementation Phases — Cognito Doc Integration

> Phases for [`SPEC.md`](./SPEC.md)

### Phase 0: Bootstrap

**Scope:** Provision the `cog-docs` standalone git repo and seed all Cognito skill-config inputs; install Python dependencies for Phase 1; mint and store the ADO PAT. No scripts are authored here — this phase establishes the durable environment every subsequent phase requires.

**Deliverables:**
- [x] Create `repos/cog-docs` as a new standalone git repo with `docs/features/`, `docs/bugs/`, `docs/work/` directories (empty but tracked by a `.gitkeep`)
- [x] Add `.gitignore` to `cog-docs` excluding `pool/` (worktree pool dir), `docs/work/leases.json`, `docs/work/global.lock.d`, `docs/work/DASHBOARD.md`, and any other runtime-only coordination files
- [x] Create `repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` (or `.json`) containing: WIQL identity (`project: "Cognito Forms"`, `team: Poseidon`, `areaPath: "Cognito Forms\\Poseidon"`); type→pipeline map (`Bug/Defect/Story Bug/Engineering Bug → bug`; `User Story/Refactor Story/Enabler Story/Requirement → feature`; unknown → skip-and-log); pool defaults (`pool_size: 3`, `lease_ttl_seconds: 1800`, `heartbeat_interval_seconds: 600` i.e. ttl/3)
- [x] Install Python dependencies on the work machine: `pip install keyring requests` (or `pip install keyring httpx`); document the install command in a comment block at the top of `ado-sync.py` (Phase 1), since the repo has no `requirements.txt`
- [x] Mint a `vso.work`-scoped PAT in ADO (Work Items – Read only) and store it: `keyring.set_password("ado-local-poller", "vso_pat_readonly", "<PAT>")`
- [x] Tests: manually verify `python -c "import keyring, requests; print('ok')"` succeeds; verify `keyring.get_password("ado-local-poller", "vso_pat_readonly")` returns the PAT without prompting

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] `python -c "import keyring; print(keyring.get_password('ado-local-poller','vso_pat_readonly'))"` prints the PAT value (not `None`) — verified `PAT_PRESENT`
- [x] `python -c "import keyring, requests"` exits 0 with no ImportError — verified `DEPS_OK` (Python 3.14.0)
- [x] `repos/cog-docs` is a valid git repo: `git -C repos/cog-docs status` exits 0 — clean tree, commit `4bdd575`
- [x] `docs/features/`, `docs/bugs/`, `docs/work/` all exist under `repos/cog-docs`
- [x] `pool/` is listed in `repos/cog-docs/.gitignore`; `leases.json` and `global.lock.d` are also listed — confirmed via `git check-ignore`
- [x] `repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` parses as valid YAML/JSON and contains all type→pipeline entries — `PARSE_OK`, areaPath decodes to `Cognito Forms\Poseidon`

**MCP Integration Test Assertions:**

N/A — no runtime-observable behavior in this phase (environment provisioning only).

#### Implementation Notes (Phase 0)
**Completed:** 2026-06-02
**Work completed:**
- cog-docs repo: standalone git repo at `C:\Users\JacobMadsen\source\repos\cog-docs` (commit `4bdd575`, personal identity `jacobmadsen12321@gmail.com`). Tracks `.gitignore` + `docs/{features,bugs,work}/.gitkeep`. `.gitignore` = exactly `pool/`, `docs/work/leases.json`, `docs/work/global.lock.d`, `docs/work/DASHBOARD.md` (all confirmed ignored via `git check-ignore`).
- `ado-doc-integration.yml`: written with wiql_identity (project/team Poseidon/areaPath `Cognito Forms\Poseidon`/includeChildren false), type_pipeline_map (bug: [Bug, Defect, Story Bug, Engineering Bug]; feature: [User Story, Refactor Story, Enabler Story, Requirement]), github_repo (cognitoforms/cognito), pool (3 / 1800 / 600). 17 lines, parses cleanly.
- Manual prereqs: PAT present in keyring (`ado-local-poller` / `vso_pat_readonly`); `keyring`+`requests` import OK; `pyyaml` present. Python 3.14.0.
**Integration notes:**
- **SYMLINK DISCOVERY (load-bearing for all later phases):** `Cognito Forms/.claude/skill-config/` is a symlink into the claude-config repo. The `.yml` physically lives at `claude-config/repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` and shows as untracked (`??`) in **claude-config**, not in the Cognito work repo. Per plan it MUST stay uncommitted → never use `git add -A` for phase commits; stage only explicit per-file paths so this `.yml` is never swept in.
- `pr_artifact_repo_guid` is a placeholder (`TODO_FILL_FROM_REAL_WI_ARTIFACTLINK`). Phase 1 (`ado-sync.py` linkedPRs parse) can hardcode the constant GitHub repo GUID or read this key; fill from a real WI ArtifactLink when available.
- `<COG_DOCS>` = `C:\Users\JacobMadsen\source\repos\cog-docs`. Phase 1 writes `<COG_DOCS>/docs/work/ado-mirror.json` here.
- **Windows console encoding:** Python test runners crash on cp1252 when printing `→`/Unicode in FAIL messages. All Python gates MUST run with `PYTHONUTF8=1` (bash: `export PYTHONUTF8=1`).
- **Baseline gate state (pre-this-plan boundary):** `lazy-state.py --test` PASS, `bug-state.py --test` PASS, `test_lazy_core.py` 42/43 — the 1 failure (`test_lazy_state_test_output_matches_baseline`) is a pre-existing Windows-temp-path vs POSIX `/tmp/claude-1000/` golden mismatch, NOT a logic bug. Do not attribute it to this plan.
**Pitfalls & guidance:**
- claude-config push fails with HTTP 403 (credential helper authenticates as work account `jacob-cognitoforms`, which lacks access to personal `jacobrocks1212/claude-config`). Local commits succeed; remote sync needs user to fix git credentials / `gh auth switch`. Treated as non-fatal — work proceeds with local commits.
**Files modified:**
- `C:\Users\JacobMadsen\source\repos\cog-docs\` — net-new repo (.gitignore, docs/{features,bugs,work}/.gitkeep)
- `claude-config/repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` — net-new config (uncommitted, via symlink from Cognito Forms tree)

**Prerequisites:** None (first phase)

**Files likely modified:**
- `repos/cog-docs/` (net-new repo) — create new standalone git repo; `docs/{features,bugs,work}/` directories + `.gitkeep`s; `.gitignore` covering `pool/` and all runtime coordination files (`leases.json`, `global.lock.d`, `DASHBOARD.md`)
- `repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` (net-new config file in dir-exists location) — create WIQL identity, type→pipeline map, and pool/lease defaults; config-driven so new WI types are a data-only edit

**Testing Strategy:** Manual verification only. Confirm PAT retrieval, dependency imports, repo structure, and config parse. No automated test fixtures needed at this stage — Phase 1 fixtures cover the runtime behavior these settings enable.

**Integration Notes for Next Phase:**
- Phase 1 (`ado-sync.py`) reads the PAT via `keyring.get_password("ado-local-poller", "vso_pat_readonly")` — the exact service/username must match what was stored here
- Phase 1 reads WIQL identity from `repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml`; the `areaPath` value drives the WIQL `WHERE` clause verbatim
- Phase 1 writes `<COG_DOCS>/docs/work/ado-mirror.json`; `<COG_DOCS>` is the absolute path to `repos/cog-docs` (passed as `--repo-root` or resolved from config)
- `pool/` gitignore must be in place before Phase 4 adds worktrees there

---

### Phase 1: Deterministic ADO Sync

**Scope:** Implement `user/scripts/ado-sync.py` — the headless WIQL poller that writes the ADO mirror to disk. Covers keyring auth, delta watermark, 200-id chunked hydration, atomic file write, full mirror schema (including PR/CI fields and `linkedPRs[]` parsing), Windows Task Scheduler registration, and `--test` fixtures covering the three critical correctness properties.

**Deliverables:**
- [x] `user/scripts/ado-sync.py` (net-new): CLI entry point with `--repo-root <COG_DOCS>`, `--config <skill-config-yml>`, `--test`, `--once` (single poll, no scheduler)
- [x] Keyring auth: `keyring.get_password("ado-local-poller", "vso_pat_readonly")` — fail fast with a clear error if absent
- [x] WIQL delta query: `SELECT [System.Id] FROM workitems WHERE (AssignedTo = @Me OR AreaPath UNDER 'Cognito Forms\Poseidon') AND ChangedDate >= '<lastSync-UTC>Z' ORDER BY ChangedDate ASC` — dates MUST be UTC + `Z` suffix; watermark persisted alongside the mirror (or embedded in `ado-mirror.json`)
- [x] 200-id chunked hydration: `wit/workitems?ids=<chunk>&$expand=all` — ids sliced into ≤200; merge batches before writing; log chunk count
- [x] Atomic write: write to a temp file alongside the target, then `os.replace(tmp, target)` — no partial reads possible
- [x] Full mirror schema written to `<COG_DOCS>/docs/work/ado-mirror.json`: `syncedAt`, `watermark`, `query` (identity snapshot), `workItems[]` — each entry: `{id, type, title, state, assignedTo, areaPath, iteration, parentId, url, acceptanceCriteria, description, changedDate, linkedPRs[], pr, prStatus, autotestStatus, autotestBuildId, autotestRun, materialized}`
- [x] `linkedPRs[]` parsing: extract from `ArtifactLink` relations matching `vstfs:///GitHub/PullRequest/<repoGuid>%2f<prNumber>` → `{prNumber, repo: "cognitoforms/cognito"}`; repo GUID is constant — hardcode or embed in config (no HierarchyQuery)
- [x] Custom fields: copy `Custom.PR` → `pr`, `Custom.PRStatus` → `prStatus`, `Custom.AutotestStatus/BuildID/Run` → `autotestStatus/autotestBuildId/autotestRun` verbatim
- [x] Windows Task Scheduler registration: `schtasks /create` command or XML task definition; runs `ado-sync.py --once --repo-root <COG_DOCS>` every N minutes (N from config), headless (no window)
- [x] `--test` mode: three fixture-driven assertions (see Testing Strategy)

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Running `ado-sync.py --once` twice on unchanged ADO state produces byte-identical `workItems[]` arrays (modulo `syncedAt` and `watermark`)
- [ ] After simulating multi-day downtime (advance the watermark to a past timestamp), a single poll fetches all accumulated changes and the resulting mirror matches live ADO state
- [ ] Syncing a WI set with total count >200 succeeds without HTTP 400; poller logs show ≥2 hydration batches
- [ ] `ado-mirror.json` parses as valid JSON immediately after write (no torn write possible)
- [ ] A WI with a linked GitHub PR shows `linkedPRs: [{prNumber: <N>, repo: "cognitoforms/cognito"}]`
- [ ] A WI with custom fields populated shows non-null `pr`, `prStatus`, `autotestStatus`

**MCP Integration Test Assertions:**

```
ASSERTIONS:
1. After running ado-sync.py --once twice on unchanged ADO state: ado-mirror.json workItems[] arrays MUST be byte-identical (modulo syncedAt/watermark fields)
2. After watermark is set to a stale past timestamp and one poll runs: mirror workItems MUST contain all changes that accumulated since the stale watermark (verified against live ADO via MCP)
3. After syncing a WI set whose total id count exceeds 200: poller logs MUST show ids chunked into batches of ≤200; HTTP 400 MUST NOT occur
4. After ado-sync.py writes ado-mirror.json: json.loads(open("ado-mirror.json").read()) MUST succeed without exception (atomicity invariant)
5. After syncing a teammate WI that has a linked GitHub PR (ArtifactLink vstfs://...): ado-mirror.json entry MUST have linkedPRs[] non-empty AND pr/prStatus fields populated from Custom.PR/Custom.PRStatus
```

**Prerequisites:** Phase 0 complete (PAT stored in keyring, `cog-docs` repo exists at `<COG_DOCS>`, `docs/work/` dir exists, config YAML with WIQL identity is in place)

**Files likely modified:**
- `user/scripts/ado-sync.py` (net-new) — create; stdlib + `keyring` + HTTP client; this is the first script in the repo to use non-stdlib dependencies; add a comment block at the top documenting `pip install keyring requests` (no requirements.txt exists)

**Testing Strategy:** `--test` mode runs three fixture-driven self-checks inline: (1) chunking fixture — a synthetic list of 210 ids is split and the split produces batches ≤200; (2) watermark-recovery fixture — a canned mirror + a stale watermark + a small delta response; assert the merged result equals the expected final state; (3) determinism fixture — run the merge logic twice on identical inputs; assert output is identical. All three run without network access (stubs or canned JSON). For live integration, the Runtime Verification steps above require a real ADO connection.

**Integration Notes for Next Phase:**
- Phase 2 (`work-status.py`) reads `<COG_DOCS>/docs/work/ado-mirror.json` — the schema locked here (field names, `linkedPRs[]` shape, `materialized` boolean) is the contract; do not rename fields between phases
- The `watermark` field in the mirror is the only mutable coordination state Phase 1 owns; Phase 3 adds `materialized` flags on top of the same file (must merge cleanly)
- Phase 3 reads `changedDate` from each WI entry to compare against `materialized_changedDate`; the field MUST be present and ISO-8601 UTC+Z on every entry
- The `query` identity snapshot embedded in the mirror lets Phase 2 display the WIQL scope in the dashboard's sync-health panel

#### Implementation Notes (Phase 1)
**Completed:** 2026-06-02
**Work completed:**
- `user/scripts/ado-sync.py` (net-new, 643 lines) authored via TDD (RED test-agent → GREEN impl-agent). `python ado-sync.py --test` exits 0 with `3/3 fixtures passed`.
- Pure helpers (test-covered): `chunk_ids` (≤200, order-preserving), `merge_work_items` (id-keyed, delta-wins, sorted by `int(id)`), `compute_watermark` (lexicographic max over `changedDate` + prior), `serialize_mirror` (`json.dumps(indent=2, sort_keys=True, ensure_ascii=False)`).
- Network/IO path (not fixture-covered — exercised by Runtime Verification, still unchecked): `get_pat` (lazy keyring, fail-fast non-zero), `fetch_delta_ids` (WIQL POST, UTC+Z watermark, basic-auth PAT), `hydrate` (chunked `?ids=...&$expand=all`), `work_item_from_api` (raw→LOCKED schema), `build_mirror`, `install_task` (`schtasks /create` minute-interval), `_atomic_write` (`tempfile.mkstemp`+`os.replace`, mirrors `lazy_core`), `_load_config` (PyYAML + minimal fallback), `_load_mirror`.
**Integration notes:**
- LOCKED mirror schema field names are emitted verbatim by `work_item_from_api` — all 19 keys present, `materialized` initialized `false`, `changedDate` normalized to `YYYY-MM-DDTHH:MM:SSZ` via `_normalize_changed_date`. Phases 2/3/4 consume these names; do not rename.
- `parse_linked_prs` matches `vstfs:///GitHub/PullRequest/<guid>%2f<prNumber>` (case-insensitive) → `{prNumber:int, repo:"cognitoforms/cognito"}`; default `repo` arg keeps the constant out of per-call config.
- ADO org is hardcoded `cognitoforms` in `fetch_delta_ids`/`hydrate` URLs (`https://dev.azure.com/cognitoforms/...`); project/areaPath read from config `wiql_identity`. If the real ADO org slug differs, adjust there — runtime-only, not test-covered.
**Pitfalls & guidance:**
- `--test` is fully offline: keyring/requests/yaml are all lazy-imported inside the functions that need them, so the fixtures run with zero non-stdlib deps. Do not hoist those imports to module top.
- Windows console is cp1252 — run gates with `PYTHONUTF8=1` or unicode in diagnostics crashes the runner.
- `pr_artifact_repo_guid` in config is still the `TODO_FILL_FROM_REAL_WI_ARTIFACTLINK` placeholder; `parse_linked_prs` does not depend on it (regex is guid-agnostic), so this is non-blocking until a real ArtifactLink is available to confirm the GUID.
**Files modified:**
- `user/scripts/ado-sync.py` — net-new poller (all Phase 1 deliverables).

---

### Phase 2: Work Dashboard

**Scope:** Implement `user/scripts/work-status.py` and `user/skills/work-status/SKILL.md` — a read-only cross-source terminal dashboard. Aggregates the ADO mirror, both queue files, `materialized.json`, `leases.json`, `STALE_UPSTREAM.md` sentinels, and live per-item state from both state machines. Must degrade gracefully when Phase 3/4 artifacts do not yet exist.

**Deliverables:**
- [ ] `user/scripts/work-status.py` (net-new): reads `ado-mirror.json`, `docs/features/queue.json`, `docs/bugs/queue.json`, `docs/work/materialized.json`, `docs/work/leases.json`; scans `docs/features/` and `docs/bugs/` for `STALE_UPSTREAM.md` sentinels; calls `lazy-state.py --feature-id <id> --status` and `bug-state.py --bug-id <id> --status` (or equivalent read-only probe) for live per-item state
- [ ] Five display panels: *My queue* (queued items + live lazy/bug state including current step, blockers, NEEDS_INPUT/BLOCKED sentinels), *In flight* (leases: `worker_pid`, worktree slot, stage, heartbeat age, STALE flags), *My ADO inbox* (mirror WIs assigned to me, not yet materialized — type/state/linkedPRs), *Team* (teammates' WIs from mirror + `pr`/`prStatus`/`autotestStatus` columns), *Pool & sync health* (slot occupancy, mirror `syncedAt`, staleness indicator, last poll result)
- [ ] Graceful degradation: if `leases.json` is absent → *In flight* panel shows "No leases yet"; if `materialized.json` is absent → treat all WIs as un-materialized; if `queue.json` is absent → panel shows empty; if `docs/work/` dir is absent → sync-health panel shows "Mirror not yet initialized" — no unhandled exception in any case
- [ ] Branch-name self-link: for items in the queue with `wi_id` present, derive the expected branch `p/<wi_id>-<slug>` and check `linkedPRs[]` in the mirror — display link if found; regex `^p/(\d+)-`
- [ ] Optional `--markdown` flag: writes formatted output to `<COG_DOCS>/docs/work/DASHBOARD.md` (no mutation of any other artifact)
- [ ] `user/skills/work-status/SKILL.md` (net-new): frontmatter with `name: work-status`, `description`, `argument-hint`, `plan-mode: false`; invocation pattern; documentation of all five panels and the `--markdown` flag; read-only safety note

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Running `work-status.py` with only `ado-mirror.json` present (no Phase 3/4 artifacts) exits 0 and renders the inbox and team panels; all other panels degrade gracefully with informational messages
- [ ] After Phase 3 artifacts exist, *My queue* panel lists materialized items with their current lazy/bug state step
- [ ] After Phase 4 artifacts exist, *In flight* panel lists active leases with heartbeat age
- [ ] `--markdown` writes `DASHBOARD.md` without mutating `leases.json`, `queue.json`, or `materialized.json`

**MCP Integration Test Assertions:**

```
ASSERTIONS:
1. After work-status.py runs with only ado-mirror.json present (no leases.json, no materialized.json, no queue.json): exit code MUST be 0; output MUST contain "My ADO inbox" panel with ≥1 row if mirror is non-empty; output MUST NOT contain an unhandled exception traceback
2. After a teammate WI is synced with Custom.PR and Custom.PRStatus populated: Team panel MUST display that WI row with pr and prStatus values sourced from ado-mirror.json (not from branch name)
3. After an item is materialized (Phase 3) and a branch p/<wi_id>-<slug> is open: My queue panel MUST show a PR link derived via regex ^p/(\d+)- matched against linkedPRs[] in the mirror
4. After --markdown flag is used: DASHBOARD.md MUST be created/updated; leases.json and queue.json modification timestamps MUST be unchanged
```

**Prerequisites:** Phase 1 complete (`ado-mirror.json` exists with the locked schema, including `linkedPRs[]`, `pr`/`prStatus`/`autotest*` fields, and per-WI `changedDate`)

**Files likely modified:**
- `user/scripts/work-status.py` (net-new) — create; reads mirror + both `queue.json`s + calls both `compute_state()`; must not mutate any artifact; graceful degradation when Phase 3/4 outputs absent
- `user/skills/work-status/SKILL.md` (net-new) — create; frontmatter `name/description/argument-hint/plan-mode`; read-only

**Testing Strategy:** Run with a canned `ado-mirror.json` (fixtures from Phase 1 tests) and no other artifacts — verify all five panels render without error. Then add minimal `queue.json` + `materialized.json` stubs and verify *My queue* populates. No new `--test` infrastructure needed; rely on Phase 1 fixtures for the mirror and manually constructed minimal stubs for queue/lease shapes.

**Integration Notes for Next Phase:**
- Phase 3 sets the `materialized` boolean on WI entries in `ado-mirror.json` (or in the separate `materialized.json`); the dashboard reads `materialized.json` to distinguish inbox items from queued items — the Phase 3 schema (`{wi_id → feature_id, materialized_changedDate}`) is the contract
- The `leases.json` schema (`{wi_id: {worker_pid, worktree_slot, term_token, heartbeat_timestamp, ttl_seconds}}`) established in Phase 4 is what the *In flight* panel will parse; the graceful-degradation path keeps Phase 2 forward-compatible
- `compute_state()` in `lazy-state.py` and `bug-state.py` must expose a read-only probe mode (status-only, no side effects) for the dashboard to call safely; verify this contract is not broken by the Phase 3/4 additions

---

### Phase 3: WI→Doc Materialization

**Scope:** Implement the discrete, idempotent materialization step: auto-route a selected WI by type into the correct pipeline, thin-copy its content into canonical doc format, enqueue it via `enqueue_adhoc()`, stamp the AB# link, record it in `materialized.json`, and install the `STALE_UPSTREAM.md` divergence-detection gate. Adds a parallel `enqueue_adhoc` to `bug-state.py` (it has none today). Adds sentinel parsing helpers to `lazy_core.py`.

**Deliverables:**
- [ ] Materialize entry point: `lazy-state.py --materialize-wi <id>` (or a dedicated `user/scripts/materialize-wi.py` — follow the approach that avoids breaking existing `lazy-state.py` tests) that: resolves the WI in `ado-mirror.json`; looks up `type` in the config type→pipeline map; routes to `bug-state.py` + `docs/bugs/` (bug-like) or `lazy-state.py` + `docs/features/` (story-like); logs and exits for unknown types (no silent default, no guess)
- [ ] Bug-like materialization: creates `<COG_DOCS>/docs/bugs/<slug>/ADHOC_BRIEF.md` (verbatim WI title/description/acceptance criteria — no inference), seeds a stub `SPEC.md` with `**Work Item:** AB#<id> (<url>)` in frontmatter; calls the **new bug `enqueue_adhoc`** (see below)
- [ ] Feature-like materialization: same thin-copy pattern into `<COG_DOCS>/docs/features/<slug>/`; calls `enqueue_adhoc()` at `lazy-state.py` line ~214 **verbatim** (no reimplementation)
- [ ] **New bug `enqueue_adhoc`** added to `bug-state.py`: mirrors the lazy version; target queue `<COG_DOCS>/docs/bugs/queue.json`; entry schema `{id, name, spec_dir, severity}`; idempotent (second call no-ops if `id` already present)
- [ ] `materialized.json` record: append `{wi_id: <id>, feature_id: <slug>, materialized_changedDate: <changedDate from mirror>}` atomically; second materialize of same WI MUST be a no-op (check `wi_id` before writing)
- [ ] `STALE_UPSTREAM.md` detection: on each materialize probe (or sync event), for every entry in `materialized.json`, compare `mirror[wi_id].changedDate` to `materialized_changedDate`; if newer, write `<item_dir>/STALE_UPSTREAM.md` (body = field-level diff); do NOT clobber `SPEC.md`; the state machine will halt at its next gate
- [ ] STALE_UPSTREAM halt wiring: add an early-step check in both `lazy-state.py` and `bug-state.py` `compute_state()` (analogous to BLOCKED.md / NEEDS_INPUT.md handling around Steps 3–4.6): if `STALE_UPSTREAM.md` exists for the current item, return `state=stale_upstream` and do not advance; after human absorb/reject, the absorb path re-copies WI fields into `SPEC.md` and updates `materialized_changedDate` in `materialized.json`
- [ ] Sentinel parsing helpers in `lazy_core.py`: `read_stale_upstream(item_dir)` → diff string or `None`; `write_stale_upstream(item_dir, diff)` → writes file; `clear_stale_upstream(item_dir)` → removes file; place beside existing sentinel helpers in `lazy_core.py`

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Materializing a `Bug` WI creates `docs/bugs/<slug>/ADHOC_BRIEF.md` whose content is a verbatim subset of the mirror WI fields (diff produces no invented text)
- [ ] Materializing a `User Story` WI creates `docs/features/<slug>/ADHOC_BRIEF.md` with the same verbatim constraint
- [ ] Materializing any WI type not in the config map logs a skip message and exits 0 — no file is created, no queue is modified
- [ ] Materializing the same WI twice: second run exits 0; `queue.json` length is unchanged; `materialized.json` has exactly one entry for that `wi_id`
- [ ] After a materialized WI's `changedDate` advances in the mirror: `STALE_UPSTREAM.md` appears in the item directory; `SPEC.md` is unmodified; the next `compute_state()` call returns `stale_upstream` without advancing
- [ ] After human absorb: `STALE_UPSTREAM.md` is removed; `SPEC.md` has updated content; `materialized_changedDate` in `materialized.json` matches the new `changedDate`

**MCP Integration Test Assertions:**

```
ASSERTIONS:
1. After materializing a WI of type "Bug": docs/bugs/<slug>/ADHOC_BRIEF.md MUST exist; diff between ADHOC_BRIEF.md and mirror WI fields for title/description/acceptanceCriteria MUST be empty (verbatim copy, no additions)
2. After materializing a WI of type "User Story": docs/features/<slug>/ADHOC_BRIEF.md MUST exist; same verbatim constraint holds; docs/bugs/ MUST be unmodified
3. After materializing a WI of unknown type (not in config map): docs/features/ and docs/bugs/ MUST be unmodified; queue.json length MUST be unchanged; exit code MUST be 0
4. After materializing the same WI twice: materialized.json MUST have exactly one entry with that wi_id; queue.json MUST have exactly one entry for that item
5. After a materialized WI's changedDate advances in the mirror and the stale-check runs: STALE_UPSTREAM.md MUST exist in the item directory; SPEC.md modification timestamp MUST be unchanged (not overwritten)
6. After the stale-check writes STALE_UPSTREAM.md and compute_state() is called: return value MUST indicate stale_upstream state; the item MUST NOT advance to its next step
```

**Prerequisites:** Phase 1 complete (mirror exists with `type`, `changedDate`, `acceptanceCriteria`, `description`, `url` fields); Phase 0 config (type→pipeline map) must be readable

**Files likely modified:**
- `user/scripts/lazy-state.py` (exists → refactor) — add `--materialize-wi <id>` entry point; reuse `enqueue_adhoc()` at ~line 214 verbatim; add STALE_UPSTREAM early-step halt check in `compute_state()` (analogous to BLOCKED.md/NEEDS_INPUT.md handling around Steps 3–4.6); add `run_smoke_tests()` fixtures for materialize + stale paths (~line 2102)
- `user/scripts/bug-state.py` (exists → refactor) — add the new bug `enqueue_adhoc` (target `docs/bugs/queue.json`, entry `{id, name, spec_dir, severity}`; mirrors lazy's implementation); add STALE_UPSTREAM early-step halt check in `compute_state()` (before queue walk ~line 383); add fixtures
- `user/scripts/lazy_core.py` (exists → reuse) — add `read_stale_upstream`, `write_stale_upstream`, `clear_stale_upstream` sentinel parsing helpers beside existing sentinel helpers; add materialized.json read/write helpers if not already present

**Testing Strategy:** Use `--test` / `run_smoke_tests()` fixtures in both state machines. Fixtures cover: (1) materialize a bug-type WI → assert `docs/bugs/` path and queue entry; (2) materialize a feature-type WI → assert `docs/features/` path; (3) materialize unknown type → assert no-op; (4) idempotent materialize → assert single queue entry; (5) stale detection → seed a `materialized.json` entry with an old `materialized_changedDate`, advance the mirror `changedDate`, run the check, assert `STALE_UPSTREAM.md` exists; (6) stale halt → assert `compute_state()` returns `stale_upstream`. All fixtures use temporary in-memory or `tempfile` directory trees.

**Integration Notes for Next Phase:**
- Phase 4's `--feature-id` / `--bug-id` scoping flags target items already in the queue via materialize; the `feature_id` slug in `materialized.json` is the join key
- The `enqueue_adhoc` entry schema for bugs (`{id, name, spec_dir, severity}`) must be stable — Phase 4's worker reads `queue.json` entries and expects this shape
- The STALE_UPSTREAM halt in `compute_state()` must check its condition BEFORE attempting any file mutation — Phase 4 workers rely on this to be safe to call under the fencing-token check
- `lazy_core.py` sentinel helpers are imported by `ado-sync.py`-adjacent code for the stale-check loop; keep them side-effect-free (read: return data; write/clear: single file op, no queue mutations)

---

### Phase 4: Parallel Execution

**Scope:** Wire the concurrency plane: `--feature-id`/`--bug-id` scoping filters on both state machines; the new `lazy_coord.py` module (mkdir-lock + leases with fencing token, heartbeat, reclamation); persistent worktree pool with the deterministic scrub-to-clean sequence and git concurrency config; and the `user/skills/lazy-worker/SKILL.md` worker-session guide. This is the highest-risk phase — all shared-state mutations must be serialized under the global lock with fencing-token verification.

**Deliverables:**
- [ ] `--feature-id <slug>` filter in `lazy-state.py::compute_state()`: added after the dedup guard (~line 687); when present, the loop processes only the item with matching `feature_id`; absent the flag, behavior is byte-identical to the current single-current baseline
- [ ] `--bug-id <id>` filter in `bug-state.py::compute_state()`: added before the queue walk (~line 383); same opt-in scoping contract
- [ ] `user/scripts/lazy_coord.py` (net-new, kept separate from `lazy_core.py`): exports `acquire_lock(lock_dir, timeout)`, `release_lock(lock_dir)`, `acquire_lease(leases_path, wi_id, worker_pid, slot, ttl)` (increments `term_token`, writes entry), `heartbeat(leases_path, wi_id, expected_token)` (re-asserts lock, verifies token, refreshes timestamp), `verify_fencing(leases_path, wi_id, expected_token)` (raises if token mismatch), `reclaim_expired(leases_path, pool_dir, ttl)` (removes expired leases, scrubs their slots), `release_lease(leases_path, wi_id, expected_token)` (fencing-checked drop)
- [ ] Global lock: `os.mkdir("<COG_DOCS>/docs/work/global.lock.d")` — acquire = mkdir succeeds; `FileExistsError` = held, yield + retry with exponential backoff; never `fcntl`/`flock`/`LockFileEx`
- [ ] Lease schema in `leases.json`: `{ "<wi_id>": { "worker_pid": int, "worktree_slot": str, "term_token": int, "heartbeat_timestamp": str, "ttl_seconds": int } }` — all mutations via atomic `os.replace` of a temp file after acquiring the lock
- [ ] Worktree pool provisioning: `git -C <cognito_root> worktree add <COG_DOCS>/pool/wt-NN` for N in 0..(K-1); apply git concurrency config to the cognito repo: `git config gc.auto 0`, `git config core.filemode false`, `git config core.autocrlf input`; all `git fetch` / `git push` network ops serialized under the global lock
- [ ] Deterministic scrub-to-clean sequence (on slot reuse, in order): (1) `rm -f .git/worktrees/<slot>/index.lock`; (2) under global lock: `git fetch origin`; (3) `git checkout --detach origin/main`; (4) `git reset --hard origin/main`; (5) `git clean -fdx`; (6) `git checkout -b p/<wi_id>-<slug>` — no submodule step (`.gitmodules` absent; reinstate if ever added)
- [ ] `index.lock` backoff: retry with exponential backoff before surfacing an error; log each retry
- [ ] `user/skills/lazy-worker/SKILL.md` (net-new): documents the worker loop — acquire lock → reclaim expired → pick highest-priority actionable item without live lease (front-half or implement-ready) → lease it (+ slot if implementing) → release lock → do work (front-half = short; implement→PR = long, leased worktree + heartbeat thread) → acquire lock → flip state (fencing-checked), drop lease, free slot, update `materialized.json` → release lock; resembles `/lazy-batch` back-half; concurrency cap = `pool_size` from config
- [ ] `--test` fixtures in `lazy_coord.py` or a companion: (1) scoped `--feature-id` run — assert only the target item advances; (2) leased run — seed a lease, assert a second worker cannot claim the same item; (3) reclamation — seed an expired lease (past `heartbeat_timestamp + ttl_seconds`), run reclaim, assert slot is freed and lease is removed; (4) fencing — seed a lease with `term_token=5`, call `verify_fencing` with `expected_token=4`, assert error; (5) `--feature-id` absent → assert behavior is byte-identical to single-current (compare queue.json state before/after)

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Two worker sessions run concurrently on a queue with 2 implement-ready items: each item has exactly one lease in `leases.json`; `leases.json` and `queue.json` are uncorrupted JSON after both workers complete
- [ ] A worker whose lease expires (TTL elapsed without heartbeat) has its lease reclaimed by the next worker to call `reclaim_expired`; the freed slot is reused cleanly by the new worker
- [ ] `git config --get gc.auto` in the cognito repo returns `0`
- [ ] After slot reuse, `git -C <COG_DOCS>/pool/wt-NN status` shows `nothing to commit, working tree clean` on branch `p/<new-wi_id>-<slug>`
- [ ] Running `lazy-state.py` without `--feature-id` produces the same queue transitions as before Phase 4 (baseline regression)
- [ ] Running `lazy-state.py --feature-id <slug>` advances only the named item; other items in the queue are untouched

**MCP Integration Test Assertions:**

```
ASSERTIONS:
1. After K workers run concurrently on a ready set of K items: leases.json MUST have exactly K entries, each with a distinct worktree_slot; queue.json MUST be valid JSON (no corruption); each item MUST be leased by exactly one worker_pid
2. After a lease's heartbeat_timestamp is artificially aged beyond ttl_seconds and reclaim_expired is called: that wi_id entry MUST be absent from leases.json; the previously leased worktree_slot MUST be available for reuse
3. After verify_fencing is called with a stale term_token (expected < actual): the call MUST raise an exception; queue.json MUST be unmodified
4. After os.mkdir(global.lock.d) is called by Worker A and Worker B simultaneously: exactly one MUST succeed (mkdir is atomic on NTFS); the other MUST receive FileExistsError and retry
5. After a worktree slot is scrubbed and reused for a second item: git -C <pool/wt-NN> status MUST report "nothing to commit, working tree clean"; branch MUST be p/<new-wi_id>-<slug>
6. After git config is applied to the cognito repo: git config --get gc.auto MUST return "0"
7. After lazy-state.py is run without --feature-id: queue.json transitions MUST be byte-identical to a pre-Phase-4 baseline run (--feature-id flag preserves single-current default behavior)
8. After materialize → parallel lazy-worker run with genuine decisions present: judgment surfaces MUST appear only as NEEDS_INPUT.md or BLOCKED.md sentinels; no inline LLM inference in queue/mirror files
```

**Prerequisites:** Phase 3 complete (materialized items in `queue.json`s, `materialized.json` with `feature_id` slugs, STALE_UPSTREAM halt wired in `compute_state()`); Phase 0 `cog-docs` repo exists with `pool/` gitignored

**Files likely modified:**
- `user/scripts/lazy-state.py` (exists → refactor) — add `--feature-id` filter in `compute_state()` loop after the dedup guard (~line 687); absent the flag behavior is byte-identical to today; add `run_smoke_tests()` fixtures for scoped + leased paths (~line 2102)
- `user/scripts/bug-state.py` (exists → refactor) — add `--bug-id` filter before queue walk (`compute_state()` ~line 383); absent the flag behavior is byte-identical to today; add fixtures
- `user/scripts/lazy_coord.py` (net-new) — create; `os.mkdir` atomic lock + `leases.json` (fencing/heartbeat/reclaim); separate from `lazy_core.py`
- `user/skills/lazy-worker/SKILL.md` (net-new) — create; resembles `/lazy-batch` back-half; worker loop with lease claim, slot scrub, implement→open GH PR, release

**Testing Strategy:** `--test` / `run_smoke_tests()` fixtures in `lazy_coord.py` cover the five concurrency cases listed in Deliverables. The `--feature-id` / `--bug-id` baseline regression fixtures use a canned `queue.json` snapshot — run once without the flag, capture output, run once with an unrelated flag, assert queue state is identical. Live concurrency testing requires two terminal sessions; the Runtime Verification steps above serve as the acceptance criteria.

**Integration Notes for Next Phase:**
- Phase 5 builds on the `leases.json` schema and the `wait_on_pr` state introduced here; the transition `wait_on_pr → implement` (on CI fail / changes-requested) is the new path Phase 5 adds
- The `gh pr view --json statusCheckRollup,reviews` command Phase 5 polls is safe to add without any changes to `lazy_coord.py` — it reads GH state and writes only to `FEEDBACK.md` + triggers a `queue.json` state flip under the lock
- On PR merge, Phase 5 calls the scrub-to-clean sequence already defined here to return the slot; the slot scrub contract must remain stable
- The branch regex `^p/(\d+)-` used by the Phase 2 dashboard to self-link items is the same convention enforced by the scrub sequence here — keep them in sync

---

### Phase 5: PR Shepherding *(DEFERRED — not scheduled for v1)*

**Scope:** `gh`-based provider module for polling GitHub PR state; automatic `FEEDBACK.md` routing on CI failure or changes-requested reviews; `wait_on_pr → implement` transition; teammate guardrails; slot scrub on merge. Marked DEFERRED — do not implement until Phase 4 is stable and the deferred decision is explicitly revisited.

**Deliverables:**
- [ ] *(DEFERRED)* `gh`-based provider module: `gh pr view --json statusCheckRollup,reviews` poll against the `linkedPRs[]` from the mirror (Phase 1) and the branch regex `^p/(\d+)-` for self-authored items
- [ ] *(DEFERRED)* On `changes-requested` or CI failure: route response to `FEEDBACK.md` in the item directory; transition `wait_on_pr → implement` under the global lock + fencing-token check
- [ ] *(DEFERRED)* Merge stays human-gated: worker MUST NOT auto-merge; on detected merge, scrub the slot and return it to the pool (same scrub-to-clean sequence from Phase 4)
- [ ] *(DEFERRED)* Never auto-reply to PR comments (explicit guardrail per `user/CLAUDE.local.md`)
- [ ] *(DEFERRED)* Teammate guardrails: read-only mirror access for teammate PRs; no writes to teammate item directories; no attempt to modify teammate branches
- [ ] *(DEFERRED)* No `HierarchyQuery` enrichment — grounding showed it is unnecessary (single repo, constant GUID, branch-name regex is sufficient for self-authored items; teammates covered by ADO custom fields)
- [ ] *(DEFERRED)* Tests: PR-state poll fixture; `wait_on_pr → implement` transition under fencing; slot scrub on merge detection

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] *(DEFERRED)* On CI failure for a self-authored PR: `FEEDBACK.md` written; item transitions to `implement`; worker does not auto-merge
- [ ] *(DEFERRED)* On PR merge detection: worktree slot scrubbed cleanly; lease released; slot available for reuse

**MCP Integration Test Assertions:**

N/A — Phase deferred; assertions will be defined when this phase is scheduled.

**Prerequisites:** Phase 4 complete and stable (leases, slot pool, fencing, `wait_on_pr` state in queue)

**Files likely modified:**
- *(DEFERRED — file list TBD at scheduling time; will extend `lazy_coord.py` and `lazy-worker/SKILL.md` from Phase 4 and add a new GH provider module)*

**Testing Strategy:** *(DEFERRED)*

**Integration Notes for Next Phase:**
- This is the terminal phase; there is no Phase 6.
- The `wait_on_pr` queue state, `FEEDBACK.md` sentinel, and the slot-scrub-on-merge path are the three new contracts this phase introduces on top of Phase 4's stable foundation.
- When scheduling, re-read `RESEARCH.md` section on `gh pr view --json statusCheckRollup,reviews` output shape and the `vstfs://...` ArtifactLink parse for merge detection before implementation.

---

## Review Notes

**Batch:** PHASES.md authoring (1 file, 276 lines). **Reviewed:** 2026-06-02. **Verdict: PASS.**

Ground-truth verified (`git status --short` → `?? PHASES.md`; `wc -l` → 276, both matched). Structure, phase boundaries, the verified touchpoint paths, the reuse/refactor directives, and the 14 Validation-Criteria→phase mappings all align with the grounded SPEC and the approved 6-phase decomposition (Phase 0 separate; `lazy_coord.py` separate from `lazy_core.py`).

Two minor integration nuances for the executor (not blockers):
- **Phase 2 live-state probe ordering.** Phase 2 depends only on Phase 1, but its *My queue* live-state render references `--feature-id` / `--status` probe modes that don't land until Phase 4. Phase 2 must use what exists at its build time — call the unscoped `compute_state()` (single-current) and/or read sentinels directly for live status — and treat scoped probing as a Phase-4 enhancement. The graceful-degradation requirement already keeps this safe.
- **`materialized` flag location.** The mirror schema (Phase 1) lists a `materialized` field on each `workItems[]` entry, while Phase 3 also maintains a separate `materialized.json`. Pick one as authoritative for the dashboard's inbox-vs-queued distinction — recommend `materialized.json` as the source of truth (the worker owns it under the lock) and treat any mirror `materialized` field as a derived convenience only. Ambiguity inherited from the SPEC; resolve at Phase 3 implementation.
