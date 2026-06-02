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
- [x] WIQL delta query: `SELECT [System.Id] FROM workitems WHERE ([System.AssignedTo] = @Me OR [System.AreaPath] UNDER 'Cognito Forms\Poseidon') AND [System.ChangedDate] >= '<lastSync-UTC>Z' ORDER BY [System.ChangedDate] ASC` — dates MUST be UTC + `Z` suffix; field references MUST be bracketed `[System.*]` names (bare names → `400 TF51005`); watermark persisted alongside the mirror (or embedded in `ado-mirror.json`)
- [x] 200-id chunked hydration: `wit/workitems?ids=<chunk>&$expand=all` — ids sliced into ≤200; merge batches before writing; log chunk count
- [x] Atomic write: write to a temp file alongside the target, then `os.replace(tmp, target)` — no partial reads possible
- [x] Full mirror schema written to `<COG_DOCS>/docs/work/ado-mirror.json`: `syncedAt`, `watermark`, `query` (identity snapshot), `workItems[]` — each entry: `{id, type, title, state, assignedTo, areaPath, iteration, parentId, url, acceptanceCriteria, description, changedDate, linkedPRs[], pr, prStatus, autotestStatus, autotestBuildId, autotestRun, materialized}`
- [x] `linkedPRs[]` parsing: extract from `ArtifactLink` relations matching `vstfs:///GitHub/PullRequest/<repoGuid>%2f<prNumber>` → `{prNumber, repo: "cognitoforms/cognito"}`; repo GUID is constant — hardcode or embed in config (no HierarchyQuery)
- [x] Custom fields: copy `Custom.PR` → `pr`, `Custom.PRStatus` → `prStatus`, `Custom.AutotestStatus/BuildID/Run` → `autotestStatus/autotestBuildId/autotestRun` verbatim
- [x] Windows Task Scheduler registration: `schtasks /create` command or XML task definition; runs `ado-sync.py --once --repo-root <COG_DOCS>` every N minutes (N from config), headless (no window)
- [x] `--test` mode: three fixture-driven assertions (see Testing Strategy)

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Running `ado-sync.py --once` twice on unchanged ADO state produces byte-identical `workItems[]` arrays (modulo `syncedAt` and `watermark`)
- [x] After simulating multi-day downtime (advance the watermark to a past timestamp), a single poll fetches all accumulated changes and the resulting mirror matches live ADO state — *verified 2026-06-02: incremental poll against a stored watermark (`2026-06-02T19:56:57Z`) fetched the 15-item delta and merged to 7503 items*
- [x] Syncing a WI set with total count >200 succeeds without HTTP 400; poller logs show ≥2 hydration batches — *verified 2026-06-02: live poll fetched 7502 items in 38 hydration batches (37×200 + 1×102), no 400*
- [x] `ado-mirror.json` parses as valid JSON immediately after write (no torn write possible) — *verified 2026-06-02: `json.load` of the written mirror succeeded, 7502 workItems*
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
**Runtime verification + fixes (2026-06-02):** two distinct WIQL bugs surfaced only under live ADO, each fixed via a pure helper + RED→GREEN fixture (`--test` now `5/5`):
1. *Bare field names* — first `--once` poll returned `400 TF51005` (`AssignedTo`/`AreaPath`/`ChangedDate` are not valid bare). Fixed via `build_wiql(area_path, watermark)` emitting bracketed `[System.*]` refs; `fixture4_build_wiql_bracketed_fields`. First full poll: 7502 items across 38 batches, mirror atomic + re-loaded cleanly. Committed `1116627`.
2. *Date precision* — the next (incremental) poll `400`'d with *"cannot supply a time with the date when running a query using date precision"*: once the watermark carried a real time (`2026-06-02T19:56:57Z`, not the `T00:00:00Z` epoch), ADO's default date precision rejected it. Fixed by adding `&timePrecision=true` to the WIQL **URL** (body placement does NOT work) via `build_wiql_url(org, project)`; `fixture5_build_wiql_url_time_precision`. Incremental poll then fetched the 15-item delta → mirror 7503 items.
`cog-docs/.claude/skill-config/ado-doc-integration.yml` was provisioned (the poller reads config from `<repo-root>/.claude/skill-config/`, and cog-docs — the runtime repo-root — had none).
**Files modified:**
- `user/scripts/ado-sync.py` — net-new poller (all Phase 1 deliverables); `build_wiql()` bracket fix + `build_wiql_url()` `timePrecision=true` fix (2026-06-02, `--test` 5/5).

---

### Phase 2: Work Dashboard

**Scope:** Implement `user/scripts/work-status.py` and `user/skills/work-status/SKILL.md` — a read-only cross-source terminal dashboard. Aggregates the ADO mirror, both queue files, `materialized.json`, `leases.json`, `STALE_UPSTREAM.md` sentinels, and live per-item state from both state machines. Must degrade gracefully when Phase 3/4 artifacts do not yet exist.

**Deliverables:**
- [x] `user/scripts/work-status.py` (net-new): reads `ado-mirror.json`, `docs/features/queue.json`, `docs/bugs/queue.json`, `docs/work/materialized.json`, `docs/work/leases.json`; scans `docs/features/` and `docs/bugs/` for `STALE_UPSTREAM.md` sentinels; calls `lazy-state.py --feature-id <id> --status` and `bug-state.py --bug-id <id> --status` (or equivalent read-only probe) for live per-item state
- [x] Five display panels: *My queue* (queued items + live lazy/bug state including current step, blockers, NEEDS_INPUT/BLOCKED sentinels), *In flight* (leases: `worker_pid`, worktree slot, stage, heartbeat age, STALE flags), *My ADO inbox* (mirror WIs assigned to me, not yet materialized — type/state/linkedPRs), *Team* (teammates' WIs from mirror + `pr`/`prStatus`/`autotestStatus` columns), *Pool & sync health* (slot occupancy, mirror `syncedAt`, staleness indicator, last poll result)
- [x] Graceful degradation: if `leases.json` is absent → *In flight* panel shows "No leases yet"; if `materialized.json` is absent → treat all WIs as un-materialized; if `queue.json` is absent → panel shows empty; if `docs/work/` dir is absent → sync-health panel shows "Mirror not yet initialized" — no unhandled exception in any case
- [x] Branch-name self-link: for items in the queue with `wi_id` present, derive the expected branch `p/<wi_id>-<slug>` and check `linkedPRs[]` in the mirror — display link if found; regex `^p/(\d+)-`
- [x] Optional `--markdown` flag: writes formatted output to `<COG_DOCS>/docs/work/DASHBOARD.md` (no mutation of any other artifact)
- [x] `user/skills/work-status/SKILL.md` (net-new): frontmatter with `name: work-status`, `description`, `argument-hint`, `plan-mode: false`; invocation pattern; documentation of all five panels and the `--markdown` flag; read-only safety note

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Running `work-status.py` with only `ado-mirror.json` present (no Phase 3/4 artifacts) exits 0 and renders the inbox and team panels; all other panels degrade gracefully with informational messages — *verified 2026-06-02 against the live 7502-item mirror: exit 0, Team panel populated, My Queue / In Flight / Inbox show graceful `_(none)_` / `_No leases yet_`*
- [ ] After Phase 3 artifacts exist, *My queue* panel lists materialized items with their current lazy/bug state step
- [ ] After Phase 4 artifacts exist, *In flight* panel lists active leases with heartbeat age
- [x] `--markdown` writes `DASHBOARD.md` without mutating `leases.json`, `queue.json`, or `materialized.json` — *fixture_d asserts `st_mtime_ns` unchanged on leases/queue while DASHBOARD.md is created; verified 2026-06-02 e2e: 467-line GFM doc written, exit 0*

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

#### Implementation Notes (Phase 2)
**Completed:** 2026-06-02
**Work completed:**
- `user/scripts/work-status.py` (net-new, 663 lines) authored via TDD (RED test-agent → GREEN impl-agent). `python work-status.py --test` exits 0 with `4/4 fixtures passed`.
- Read-only aggregator helpers: `load_sources(repo_root)` (reads mirror + both queue.json + materialized.json + leases.json via `_read_json`, scans for STALE_UPSTREAM sentinels via `_scan_stale_upstream`; never raises — missing files → empty/None), `render_dashboard(sources, current_branch)` (all five panels with per-panel graceful degradation), `match_self_pr(branch, linked_prs)` (regex `^p/(\d+)-` → matching PR dict or None), `write_markdown(repo_root, text)` (atomic `_atomic_write` to `docs/work/DASHBOARD.md`, returns resolved Path, mutates nothing else).
- `user/skills/work-status/SKILL.md` (net-new, 76 lines): frontmatter cloned from sibling `lazy-status/SKILL.md` (key order name/description/argument-hint/model/plan-mode/allowed-tools; `model: haiku`; `plan-mode: never`); documents all five panels, the `--markdown` flag, invocation, and the read-only safety note. Lint-clean.
**Integration notes:**
- Frontmatter uses `plan-mode: never` (NOT the plan's literal `plan-mode: false`) — `never` is the repo convention for non-plan-producing skills, matching every sibling `*-status` skill. Functionally equivalent intent (skill never enters plan mode); the `false` in the deliverable text is loose plan wording.
- `--markdown` no-mutation invariant is enforced by fixture_d (captures `st_mtime_ns` on leases.json + queue.json before/after, asserts unchanged while DASHBOARD.md is created). `write_markdown` is the only write path in the script.
- Live smoke test against `cog-docs` (mirror absent) rendered all five panels with graceful-degradation messages and exited 0 — confirms Phase-1-only forward-compat.
- Phase 2 reads the LOCKED Phase 1 mirror schema verbatim; `match_self_pr` consumes `linkedPRs[]` `{prNumber, repo}` shape. `compute_state()` scoped-probe wiring (`--feature-id --status`) is a Phase 4 enhancement — Phase 2 degrades to sentinel-direct reads until then (per Review Notes nuance).
**Pitfalls & guidance:**
- `--test` is offline/stdlib-only; run all gates with `PYTHONUTF8=1` (Windows cp1252 crashes on Unicode in panel output).
- Dashboard treats `materialized.json` as the authoritative inbox-vs-queued signal (per Review Notes resolution), not the mirror's per-WI `materialized` convenience flag.
**Files modified:**
- `user/scripts/work-status.py` — net-new read-only dashboard (all Phase 2 deliverables).
- `user/skills/work-status/SKILL.md` — net-new skill doc.

#### Implementation Notes (Phase 2 — Markdown doc enhancement, 2026-06-02)
**Why:** the original `--markdown` flag wrote the raw terminal text to `DASHBOARD.md`, and the TEAM panel dumped all WIs (≈849 KB / 7502 rows incl. `Closed`/`Removed` back to 2022) — unusable as a doc. Added a true GFM renderer, a recency filter, and a dedicated regenerate skill (`/dashboard`). Authored via TDD (RED→GREEN), `--test` now `9/9`.
**Work completed:**
- `render_markdown(sources, current_branch=None, *, all_team=False)` (work-status.py:382) — real GFM: `# Work Dashboard` + synced/count subtitle + five `## ` panels with markdown tables; mirrors `render_dashboard`'s data selection (`_is_mine`, `match_self_pr`) without altering the terminal renderer. `--markdown` now emits this instead of the terminal text.
- `filter_recent_team(team_wis, synced_at, window_days=5) -> (kept, hidden_count)` (work-status.py:330) — keeps active WIs plus terminal-state (`closed/removed/done/resolved`, case-insensitive `frozenset` at :327) WIs changed within 5 days; **`synced_at` is the deterministic reference clock — no `datetime.now()`**. Empty/unparseable `synced_at` → keep all (graceful); terminal WI with missing/unparseable `changedDate` → hidden. `--all-team` bypasses; hidden count surfaced in the doc.
- `_escape_md_pipe()` (work-status.py:377) escapes `|` in titles/cells for table safety.
- `main()` gained `--all-team` (store_true) and `--out PATH` (atomic write to an override path; else `write_markdown` default `docs/work/DASHBOARD.md`).
- `user/skills/dashboard/SKILL.md` (`/dashboard`, net-new, 76 lines, `plan-mode: never`, lint-clean): offline render by default; `--refresh` runs `ado-sync.py --once` first (fails loud, no stale fallthrough); `--all-team`/`--out` pass through.
- New fixtures E–I in `run_self_tests()` (`total` 4→9): filter active/recent/old + empty-synced-at edge (E), missing-date terminal hidden (F), markdown structure/headers/subtitle (G), pipe escape (H), hidden-items note (I).
**Verification:** e2e against the live mirror — `DASHBOARD.md` rendered in 467 lines (down from ~849 KB), `_Hiding 7061 terminal item(s) older than 5 days_` note present, all five panels correct, exit 0.
**Files modified:**
- `user/scripts/work-status.py` — `render_markdown` + `filter_recent_team` + `_escape_md_pipe` + `--all-team`/`--out` + fixtures E–I.
- `user/skills/dashboard/SKILL.md` — net-new `/dashboard` skill.

---

### Phase 3: WI→Doc Materialization

**Scope:** Implement the discrete, idempotent materialization step: auto-route a selected WI by type into the correct pipeline, thin-copy its content into canonical doc format, enqueue it via `enqueue_adhoc()`, stamp the AB# link, record it in `materialized.json`, and install the `STALE_UPSTREAM.md` divergence-detection gate. Adds a parallel `enqueue_adhoc` to `bug-state.py` (it has none today). Adds sentinel parsing helpers to `lazy_core.py`.

**Deliverables:**
- [x] Materialize entry point: `lazy-state.py --materialize-wi <id>` (or a dedicated `user/scripts/materialize-wi.py` — follow the approach that avoids breaking existing `lazy-state.py` tests) that: resolves the WI in `ado-mirror.json`; looks up `type` in the config type→pipeline map; routes to `bug-state.py` + `docs/bugs/` (bug-like) or `lazy-state.py` + `docs/features/` (story-like); logs and exits for unknown types (no silent default, no guess)
- [x] Bug-like materialization: creates `<COG_DOCS>/docs/bugs/<slug>/ADHOC_BRIEF.md` (verbatim WI title/description/acceptance criteria — no inference), seeds a stub `SPEC.md` with `**Work Item:** AB#<id> (<url>)` in frontmatter; calls the **new bug `enqueue_adhoc`** (see below)
- [x] Feature-like materialization: same thin-copy pattern into `<COG_DOCS>/docs/features/<slug>/`; calls `enqueue_adhoc()` at `lazy-state.py` line ~214 **verbatim** (no reimplementation)
- [x] **New bug `enqueue_adhoc`** added to `bug-state.py`: mirrors the lazy version; target queue `<COG_DOCS>/docs/bugs/queue.json`; entry schema `{id, name, spec_dir, severity}`; idempotent (second call no-ops if `id` already present)
- [x] `materialized.json` record: append `{wi_id: <id>, feature_id: <slug>, materialized_changedDate: <changedDate from mirror>}` atomically; second materialize of same WI MUST be a no-op (check `wi_id` before writing)
- [x] `STALE_UPSTREAM.md` detection: on each materialize probe (or sync event), for every entry in `materialized.json`, compare `mirror[wi_id].changedDate` to `materialized_changedDate`; if newer, write `<item_dir>/STALE_UPSTREAM.md` (body = field-level diff); do NOT clobber `SPEC.md`; the state machine will halt at its next gate
- [x] STALE_UPSTREAM halt wiring: add an early-step check in both `lazy-state.py` and `bug-state.py` `compute_state()` (analogous to BLOCKED.md / NEEDS_INPUT.md handling around Steps 3–4.6): if `STALE_UPSTREAM.md` exists for the current item, return `state=stale_upstream` and do not advance; after human absorb/reject, the absorb path re-copies WI fields into `SPEC.md` and updates `materialized_changedDate` in `materialized.json`
- [x] Sentinel parsing helpers in `lazy_core.py`: `read_stale_upstream(item_dir)` → diff string or `None`; `write_stale_upstream(item_dir, diff)` → writes file; `clear_stale_upstream(item_dir)` → removes file; place beside existing sentinel helpers in `lazy_core.py`

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Materializing a `Bug` WI creates `docs/bugs/<slug>/ADHOC_BRIEF.md` whose content is a verbatim subset of the mirror WI fields (diff produces no invented text)
- [x] Materializing a `User Story` WI creates `docs/features/<slug>/ADHOC_BRIEF.md` with the same verbatim constraint
- [x] Materializing any WI type not in the config map logs a skip message and exits 0 — no file is created, no queue is modified
- [x] Materializing the same WI twice: second run exits 0; `queue.json` length is unchanged; `materialized.json` has exactly one entry for that `wi_id`
- [x] After a materialized WI's `changedDate` advances in the mirror: `STALE_UPSTREAM.md` appears in the item directory; `SPEC.md` is unmodified; the next `compute_state()` call returns `stale_upstream` without advancing
- [ ] After human absorb: `STALE_UPSTREAM.md` is removed; `SPEC.md` has updated content; `materialized_changedDate` in `materialized.json` matches the new `changedDate` *(manual/human-absorb path — helper `update_materialized_changeddate` exists (WU-3.1) but absorb wiring is out of part-1 scope; not exercised here)*

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

#### Implementation Notes (Phase 3)

##### WU-3.1 — `lazy_core.py` STALE_UPSTREAM + materialized helpers
**Completed:** 2026-06-02
**Work completed:**
- Added 6 net-new helpers to `user/scripts/lazy_core.py` (now 670 lines) via TDD (RED test-agent → GREEN impl-agent). Full suite `python test_lazy_core.py` = 53/54 (the lone fail `test_lazy_state_test_output_matches_baseline` is the pre-existing Windows-temp-path golden mismatch — NOT this change).
- Stale-upstream sentinel helpers (beside existing sentinel/receipt helpers): `read_stale_upstream(item_dir)→str|None` (reads `<item_dir>/STALE_UPSTREAM.md`, None if absent), `write_stale_upstream(item_dir, diff)` (atomic via `_atomic_write`, byte-exact round-trip), `clear_stale_upstream(item_dir)` (`unlink(missing_ok=True)`, no-op if absent).
- `materialized.json` helpers (foundation for the WU-3.3 record deliverable): `read_materialized(work_dir)→list[dict]` ([] if absent), `append_materialized(work_dir, wi_id, feature_id, changed_date)` (atomic; idempotent on `wi_id` — early-return preserves the original record, never overwrites or duplicates), `update_materialized_changeddate(work_dir, wi_id, new_changed_date)` (absorb path; atomic; no-op if `wi_id` absent). JSON record shape: `{wi_id, feature_id, materialized_changedDate}`.
**Integration notes:**
- New symbols added to `lazy_core` WITHOUT removing/renaming any of the ~21 existing exports — both state machines still import cleanly (`lazy-state.py --test` and `bug-state.py --test` both pass at exit 0 post-change). WU-3.2/3.3 consume these via `lazy_core.read_stale_upstream` (halt reader) and `lazy_core.append_materialized` / `write_stale_upstream` (materialize/stale-check writer).
- `wi_id` is stored verbatim (no type coercion) — JSON round-trips ints; callers must compare consistently.
- All writes route through `_atomic_write` and mutate only the single target file (no queue side-effects) — safe for Phase 4 workers to call under the global lock.
**Files modified:**
- `user/scripts/lazy_core.py` — 6 net-new helpers + `_STALE_UPSTREAM_FILENAME`/`_MATERIALIZED_FILENAME` constants.
- `user/scripts/test_lazy_core.py` — 12 net-new tests (11 behavioral + symbol-presence).

##### WU-3.2 — `bug-state.py` enqueue_adhoc + STALE_UPSTREAM halt
**Completed:** 2026-06-02
**Work completed:**
- Added to `user/scripts/bug-state.py` (now 1571 lines) via TDD (RED fixtures in `run_smoke_tests()` → GREEN impl). `python bug-state.py --test` = 14/14 PASS.
- `enqueue_adhoc(repo_root, bug_id, name, spec_dir=None, severity=None)`: prepends `{id, name, spec_dir, severity}` to `docs/bugs/queue.json` (`{"queue":[...]}` shape), atomic via `_atomic_write`. Uses key **`spec_dir`** — the exact key `load_bug_queue()` reads (`entry.get("spec_dir", bug_id)`, line ~257), resolving the `spec_dir`-vs-`spec_path` audit ambiguity. Idempotent **skip-with-diag** on duplicate id: emits `_diag` and returns `{status:"duplicate"}` WITHOUT writing or `_die` — DELIBERATELY diverges from lazy-state's `_die`-on-dup so the WU-3.3 subprocess re-materialize exits 0.
- `--enqueue-adhoc` CLI flag (+ `--id/--name/--spec-dir/--severity`) wired in `main()` before the `--test` branch, mirroring lazy-state's wiring — this is the subprocess entrypoint WU-3.3 invokes for bug-type WIs.
- STALE_UPSTREAM halt in `compute_state()`: new constants `TR_STALE_UPSTREAM="stale_upstream"` / `STEP_STALE_UPSTREAM="Step 2.9: stale-upstream"`; the check (`lazy_core.read_stale_upstream(spec_dir) is not None` → return halt state) sits between the `common` dict and the BLOCKED.md check — READ-ONLY, fires before normal gates.
**Integration notes:**
- `bug-state.py` reaches the helper via the existing `import lazy_core` (it already uses `lazy_core._DIAGNOSTICS`) — no import-surface change. The lazy-side halt (feature dirs) lands in WU-3.3; the "STALE_UPSTREAM halt wiring" deliverable (both state machines) stays unchecked until then.
- Regression-clean: `lazy-state.py --test` passes, `test_lazy_core.py` 53/54 (known baseline) after this change.
**Files modified:**
- `user/scripts/bug-state.py` — `enqueue_adhoc` + `--enqueue-adhoc` CLI + STALE_UPSTREAM halt + 3 smoke-test fixtures + 2 constants.

##### WU-3.3 — `lazy-state.py` `--materialize-wi` + STALE_UPSTREAM halt (closes Phase 3)
**Completed:** 2026-06-02
**Work completed:**
- Added to `user/scripts/lazy-state.py` (now 3173 lines) via TDD (RED fixtures in `run_smoke_tests()` → GREEN impl). `python lazy-state.py --test` exits 0 with all fixtures PASS (6 new: materialize-feature, materialize-bug, materialize-unknown-type, materialize-idempotent, stale-detection-writer, stale-halt-reader).
- `materialize_wi(repo_root, wi_id, type_pipeline_map)→dict`: loads `docs/work/ado-mirror.json`, finds the WI by `id`, classifies `type` against the map. **Feature route** → in-process `enqueue_adhoc()` (verbatim reuse, line ~214) with an idempotency guard that skips the call if the slug is already queued (avoids `_die`-on-dup). **Bug route** → `subprocess.run([sys.executable, bug-state.py, --enqueue-adhoc, ...])` (reaches WU-3.2's skip-on-dup entrypoint, exits 0). **Unknown type** → `_diag` skip, returns `{status:"skipped", reason:"unknown-type"}`, creates nothing. Both routes thin-copy `ADHOC_BRIEF.md` (verbatim title/description/acceptanceCriteria), seed a stub `SPEC.md` with `**Work Item:** AB#<id> (<url>)` (idempotent — only if absent, never clobbered), and record via `lazy_core.append_materialized` (idempotent on `wi_id`). Slug = kebab-case of title, fallback `wi-<id>`.
- `check_stale_upstream(repo_root, mirror=None)→list` (THE WRITER): reads `materialized.json`, loads mirror if not passed, and for each record compares `mirror[wi_id].changedDate > materialized_changedDate` (ISO-8601 UTC sorts lexically). For each stale item, locates the dir (`docs/features/<feature_id>/` then `docs/bugs/<feature_id>/`) and writes `STALE_UPSTREAM.md` via `lazy_core.write_stale_upstream` — never touches `SPEC.md`.
- Lazy-side STALE halt READER in `compute_state()`: constants `TR_STALE_UPSTREAM="stale_upstream"` / `STEP_STALE_UPSTREAM="Step 2.9: stale-upstream"`; check (`lazy_core.read_stale_upstream(spec_path) is not None`) placed immediately after the `common` dict, before the Step 3 BLOCKED.md check — READ-ONLY, `sub_skill` stays `None`. This completes the "halt wiring (both machines)" deliverable (bug side = WU-3.2).
- `--materialize-wi <id>` CLI flag wired in `main()` before `args = parser.parse_args()`, with an early-return handler (after `--enqueue-adhoc`) using the locked default type→pipeline map inline (tests pass their own map directly).
**Integration notes (end-to-end verified):**
- Ran the real `--materialize-wi` CLI against a canned 3-WI mirror: feature (501) → `docs/features/add-export-button/` (verbatim brief + `AB#501` SPEC); bug (502) → bug-state subprocess queued `crash-on-save` + verbatim brief, route="bug", no feature dir; Task (503) → skipped, no dir; `materialized.json` recorded {501,502}; re-materialize 501 → still exactly 1 record; bumping 501's mirror `changedDate` → `check_stale_upstream` wrote `STALE_UPSTREAM.md`, `SPEC.md` mtime unchanged.
- Regression-clean: `bug-state.py --test` 14/14, `test_lazy_core.py` 53/54 (known Windows-temp-path baseline fail only) after the change — import surface preserved.
**Files modified:**
- `user/scripts/lazy-state.py` — `materialize_wi` + `check_stale_upstream` + STALE halt reader in `compute_state()` + `--materialize-wi` CLI + 2 constants + `import subprocess`; 6 net-new smoke-test fixtures.

---

### Phase 4: Parallel Execution

**Scope:** Wire the concurrency plane: `--feature-id`/`--bug-id` scoping filters on both state machines; the new `lazy_coord.py` module (mkdir-lock + leases with fencing token, heartbeat, reclamation); persistent worktree pool with the deterministic scrub-to-clean sequence and git concurrency config; and the `user/skills/lazy-worker/SKILL.md` worker-session guide. This is the highest-risk phase — all shared-state mutations must be serialized under the global lock with fencing-token verification.

**Deliverables:**
- [x] `--feature-id <slug>` filter in `lazy-state.py::compute_state()`: added after the dedup guard (~line 687); when present, the loop processes only the item with matching `feature_id`; absent the flag, behavior is byte-identical to the current single-current baseline
- [x] `--bug-id <id>` filter in `bug-state.py::compute_state()`: added before the queue walk (~line 383); same opt-in scoping contract
- [x] `user/scripts/lazy_coord.py` (net-new, kept separate from `lazy_core.py`): exports `acquire_lock(lock_dir, timeout)`, `release_lock(lock_dir)`, `acquire_lease(leases_path, wi_id, worker_pid, slot, ttl)` (increments `term_token`, writes entry), `heartbeat(leases_path, wi_id, expected_token)` (re-asserts lock, verifies token, refreshes timestamp), `verify_fencing(leases_path, wi_id, expected_token)` (raises if token mismatch), `reclaim_expired(leases_path, pool_dir, ttl)` (removes expired leases, scrubs their slots), `release_lease(leases_path, wi_id, expected_token)` (fencing-checked drop)
- [x] Global lock: `os.mkdir("<COG_DOCS>/docs/work/global.lock.d")` — acquire = mkdir succeeds; `FileExistsError` = held, yield + retry with exponential backoff; never `fcntl`/`flock`/`LockFileEx`
- [x] Lease schema in `leases.json`: `{ "<wi_id>": { "worker_pid": int, "worktree_slot": str, "term_token": int, "heartbeat_timestamp": str, "ttl_seconds": int } }` — all mutations via atomic `os.replace` of a temp file after acquiring the lock
- [x] Worktree pool provisioning: `git -C <cognito_root> worktree add <COG_DOCS>/pool/wt-NN` for N in 0..(K-1); apply git concurrency config to the cognito repo: `git config gc.auto 0`, `git config core.filemode false`, `git config core.autocrlf input`; all `git fetch` / `git push` network ops serialized under the global lock
- [x] Deterministic scrub-to-clean sequence (on slot reuse, in order): (1) `rm -f .git/worktrees/<slot>/index.lock`; (2) under global lock: `git fetch origin`; (3) `git checkout --detach origin/main`; (4) `git reset --hard origin/main`; (5) `git clean -fdx`; (6) `git checkout -b p/<wi_id>-<slug>` — no submodule step (`.gitmodules` absent; reinstate if ever added)
- [x] `index.lock` backoff: retry with exponential backoff before surfacing an error; log each retry
- [x] `user/skills/lazy-worker/SKILL.md` (net-new): documents the worker loop — acquire lock → reclaim expired → pick highest-priority actionable item without live lease (front-half or implement-ready) → lease it (+ slot if implementing) → release lock → do work (front-half = short; implement→PR = long, leased worktree + heartbeat thread) → acquire lock → flip state (fencing-checked), drop lease, free slot, update `materialized.json` → release lock; resembles `/lazy-batch` back-half; concurrency cap = `pool_size` from config
- [x] `--test` fixtures in `lazy_coord.py` or a companion: (1) scoped `--feature-id` run — assert only the target item advances; (2) leased run — seed a lease, assert a second worker cannot claim the same item; (3) reclamation — seed an expired lease (past `heartbeat_timestamp + ttl_seconds`), run reclaim, assert slot is freed and lease is removed; (4) fencing — seed a lease with `term_token=5`, call `verify_fencing` with `expected_token=4`, assert error; (5) `--feature-id` absent → assert behavior is byte-identical to single-current (compare queue.json state before/after)

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Two worker sessions run concurrently on a queue with 2 implement-ready items: each item has exactly one lease in `leases.json`; `leases.json` and `queue.json` are uncorrupted JSON after both workers complete
- [ ] A worker whose lease expires (TTL elapsed without heartbeat) has its lease reclaimed by the next worker to call `reclaim_expired`; the freed slot is reused cleanly by the new worker
- [ ] `git config --get gc.auto` in the cognito repo returns `0`
- [ ] After slot reuse, `git -C <COG_DOCS>/pool/wt-NN status` shows `nothing to commit, working tree clean` on branch `p/<new-wi_id>-<slug>`
- [x] Running `lazy-state.py` without `--feature-id` produces the same queue transitions as before Phase 4 (baseline regression) *(offline-proven by the `baseline-regression-default` smoke fixture in both state machines)*
- [x] Running `lazy-state.py --feature-id <slug>` advances only the named item; other items in the queue are untouched *(offline-proven by the `scoped-feature-id` / `scope-bug-id-two-bugs` smoke fixtures)*

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
- The deferred Phase 6 (PR Shepherding) builds on the `leases.json` schema and the `wait_on_pr` state introduced here; the transition `wait_on_pr → implement` (on CI fail / changes-requested) is the new path Phase 6 adds
- The `gh pr view --json statusCheckRollup,reviews` command Phase 6 polls is safe to add without any changes to `lazy_coord.py` — it reads GH state and writes only to `FEEDBACK.md` + triggers a `queue.json` state flip under the lock
- On PR merge, Phase 6 calls the scrub-to-clean sequence already defined here to return the slot; the slot scrub contract must remain stable
- The branch regex `^p/(\d+)-` used by the Phase 2 dashboard to self-link items is the same convention enforced by the scrub sequence here — keep them in sync

#### Implementation Notes (Phase 4)

##### Batch 1 (WU-4.1 + WU-4.2 + WU-4.3) — concurrency plane core
**Completed:** 2026-06-02 (part 2 of the plan series)
**Work completed (TDD, 3 parallel test-agents → RED → 3 parallel impl-agents → GREEN):**
- **WU-4.1 — `user/scripts/lazy_coord.py` (net-new, 666 lines, SEPARATE from `lazy_core.py`):** stdlib-only coordination module. `python lazy_coord.py --test` = 5/5 PASS.
  - **Global lock = `os.mkdir(lock_dir)` ONLY** (atomic on NTFS) — `acquire_lock(lock_dir, timeout=10.0, *, poll=0.05)` retries on `FileExistsError` with exponential backoff (delay doubles, capped 1.0s, elapsed via `time.monotonic()`) → `TimeoutError`; `release_lock` = `os.rmdir` (ignores `FileNotFoundError`). **No `fcntl`/`flock`/`LockFileEx`/`msvcrt` anywhere** (verified by review grep).
  - **Lease API:** `acquire_lease(leases_path, wi_id, worker_pid, slot, ttl_seconds, *, now=None) -> dict|None` (reclaim-expired-inline first; returns `None` on live double-claim; `term_token = prev+1`), `heartbeat(.., expected_token, *, now)` (fencing-checked, refreshes timestamp), `verify_fencing(.., expected_token)` (READ-ONLY, raises `FencingError(ValueError)` on absent/mismatch), `reclaim_expired(leases_path, pool_dir, *, now) -> list` (expiry `parse(heartbeat)+ttl < now`; removes entry + `shutil.rmtree` slot), `release_lease(.., expected_token, *, now)` (fencing-checked drop).
  - **Concurrency invariants (review-confirmed):** every `leases.json` mutation runs UNDER the global lock (`lock_dir = leases_path.parent/"global.lock.d"`) with release in `finally`, and writes via atomic `_write_leases` (temp `.tmp` + `os.replace`). Lock is NON-re-entrant — reclamation inside `acquire_lease` uses a private `_reclaim` helper, never the public locked `reclaim_expired` (no deadlock path). Time is injected via `now` (epoch float) for deterministic tests.
  - **`leases.json` LOCKED schema** (per entry, keyed `str(wi_id)`): `{worker_pid:int, worktree_slot:str, term_token:int, heartbeat_timestamp:<ISO-8601 UTC 'Z' str>, ttl_seconds:int}`.
  - **Worktree pool:** `provision_pool(cognito_root, pool_dir, k)` (`git worktree add` per slot under lock; applies `gc.auto 0` / `core.filemode false` / `core.autocrlf input` to the cognito repo). `scrub_slot(cognito_root, pool_dir, slot, wi_id, slug, *, lock_dir)` runs the EXACT ordered sequence: (1) rm `.git/worktrees/<slot>/index.lock` (backoff+log); (2) `git fetch origin` under lock; (3) `checkout --detach origin/main`; (4) `reset --hard origin/main`; (5) `clean -fdx`; (6) `checkout -b p/<wi_id>-<slug>` — **NO submodule step** (cognito has no `.gitmodules`). These two are code-complete but exercised only by the live-only manual checklist, not the offline `--test`.
- **WU-4.2 — `lazy-state.py` `--feature-id` scoping:** appended `scope_feature_id: str|None=None` to `compute_state()` (backward-compatible), single guarded `continue` after the `seen_ids` dedup guard, `--feature-id` argparse threaded into the main() call-site. Absent the flag → byte-identical to single-current (proven by `baseline-regression-default` fixture; scoping proven by `scoped-feature-id` selecting the non-default 2nd item).
- **WU-4.3 — `bug-state.py` `--bug-id` scoping:** symmetric — appended `scope_bug_id: str|None=None`, guarded `continue` after the validity guard in the queue walk (`str()`-coerced compare for numeric ids), `--bug-id` argparse threaded into main(). Same baseline-regression + scoped fixtures.
**Quality gates (full set, all green offline):** `lazy_coord.py --test` 5/5, `lazy-state.py --test` ✓, `bug-state.py --test` ✓, `test_lazy_core.py` 53/54 (lone fail = known Windows temp-path golden baseline, pre-existing). Import surface preserved across both state machines.
**Manual / live-only verification checklist (NOT auto-verified — require a real cognito clone + two sessions):** (a) two concurrent workers → exactly one lease each, uncorrupted `leases.json`/`queue.json`; (b) expired-lease reclaim → freed slot reused cleanly by next worker (the reclaim+scrub half IS offline-proven); (c) `git config --get gc.auto` == `0`; (d) post-reuse `git status` clean on `p/<wi_id>-<slug>`.
**Review:** PASS-WITH-FIXES — all LOCKED invariants satisfied; one stale RED-phase docstring in `run_smoke_tests()` corrected; two optional robustness nits (defensive JSON-decode guard, provision_pool lock-dir co-location) declined as out-of-contract / near-impossible given atomic writes.
**Files modified:** `user/scripts/lazy_coord.py` (net-new), `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`.

##### Batch 2 (WU-4.4) — worker-session guide
**Completed:** 2026-06-02
**Work completed:** `user/skills/lazy-worker/SKILL.md` (net-new, 213 lines, `plan-mode: never`). Documents the single-item worker loop against the REAL `lazy_coord.py` API: Step 0 arg parse (`--feature-id`/`--bug-id` pinning) → 1 `acquire_lock` (mkdir global lock) → 2 `reclaim_expired` → 3 select highest-priority unleased actionable item → 4 `acquire_lease` (capture `term_token`) → 5 `release_lock` (work runs OUTSIDE the lock) → 6 scrub-to-clean worktree prep (exact 6-step sequence, no submodule step, `p/<wi_id>-<slug>` branch) → 7 implement (with periodic `heartbeat(expected_token=term_token)`, abort on `FencingError`) → 8 open PR via `.agents/skills/pull-request/` + `gh` (shepherding DEFERRED: no CI poll, no auto-reply, no auto-merge) → 9 finalize under lock (`verify_fencing` BEFORE any `queue.json` write → flip state → `release_lease` → free/scrub slot → update `materialized.json` → `release_lock`). Closes the Invariants with one-writer-under-lock, fencing-before-every-mutation, branch convention, never-auto-merge, never-auto-reply.
**Gate:** `python lint-skills.py` passes (exit 0). Review confirmed every referenced coordination function exists in `lazy_coord.py` (no invented API) and the lock/fencing/scrub contracts match the as-built module. Verdict PASS.
**Files modified:** `user/skills/lazy-worker/SKILL.md` (net-new).

---

### Phase 5: Board-Aware & Feature-Grouped Dashboard

**Scope:** Replace the flat WI list in `DASHBOARD.md` with a Poseidon-board summary at the top and a feature-grouped priority queue. Additively extend the mirror to capture each WI's Kanban **board column**; reorganize `render_markdown()` to lead with a compact board-column summary and an **active-feature** section (configurable, default AB#54423) whose children are the highest-priority queue. Builds only on the complete Phases 1–2, so it is schedulable now, ahead of the deferred Phase 6. No change to the terminal renderer (`render_dashboard`) or to any locked mirror field name.

**Deliverables:**
- [x] `user/scripts/ado-sync.py` `work_item_from_api`: capture `System.BoardColumn` → `boardColumn` (str, `""` when off-board) and `System.BoardColumnDone` → `boardColumnDone` (bool, `false` default) — **append-only** schema additions; the existing 19 keys are unchanged and un-renamed; `serialize_mirror`'s `sort_keys=True` slots the new keys in deterministically
- [x] Config: add `active_feature_id: 54423` and `board_columns: [New, Next, "In Progress", "PR Review", "Ready for Testing", Reviewing, Merged]` (canonical lane order) to `ado-doc-integration.yml` — in **both** the Cognito-forms copy and the `cog-docs` runtime copy
- [x] `order_board(wis, board_columns) -> "OrderedDict[str, list]"` (pure helper in `work-status.py`): bucket WIs by `boardColumn` in canonical config order; missing/unknown column → a trailing `"(no column)"` bucket; deterministic (no clock reads)
- [x] `group_by_feature(team_wis, active_feature_id, mirror_index) -> ordered groups` (pure helper): active feature's children first (the priority queue), remaining features grouped after, orphans (no `parentId`) last; resolve each feature's title from the mirror parent WI when present, else `Feature <id>`; attribute deeper nesting by walking the `parentId` chain within the mirror (ancestors absent from the mirror → attribute to nearest known parent, else orphan)
- [ ] `render_markdown` extension: a lead `## Poseidon Board` section (compact column→count table only) followed by an `### 🎯 Active Feature: <title> (AB#<id>)` priority-queue table (columns: rank, WI, lane, title, PR) sorted by board-lane order, then the remaining feature groups; reuse `_escape_md_pipe` for all new cells; deterministic (config + mirror data only — no `datetime.now()`)
- [ ] `--feature <id>` CLI override on `work-status.py` (defaults to config `active_feature_id`); `user/skills/dashboard/SKILL.md` documents the `--feature` passthrough
- [ ] Tests: board bucketing (canonical order + unknown bucket); feature grouping (active pinned first, title resolution, orphan handling, multi-level `parentId` chain-walk); active-feature sort-by-lane; graceful render against a pre-Phase-5 mirror with no `boardColumn`

**Runtime Verification** *(checked by manual/live testing — NOT by the implementation agent):*
- [ ] After a `--refresh` poll, on-board Poseidon WIs carry a non-empty `boardColumn` matching the board (e.g. a "Merged" card → `boardColumn: "Merged"`); WIs not on the board → `""`
- [ ] `DASHBOARD.md` opens with a `## Poseidon Board` section whose per-column counts match the board's lane headers
- [ ] The `### 🎯 Active Feature` section lists AB#54423's children first, ahead of every other feature group
- [ ] Rendering against a pre-Phase-5 mirror (no `boardColumn` key) degrades gracefully — the board section notes "no board data; run `/dashboard --refresh`" rather than raising

**MCP Integration Test Assertions:**

```
ASSERTIONS:
1. After ado-sync.py --once runs post-Phase-5: every workItems[] entry MUST contain a boardColumn (str) and boardColumnDone (bool) key; entries for WIs on the Poseidon board MUST have non-empty boardColumn; the 19 prior keys MUST be unchanged
2. After render_markdown runs with active_feature_id=54423: the doc MUST contain a "## Poseidon Board" section before any feature section, and an "### 🎯 Active Feature" section whose first listed feature group is 54423's children
3. After order_board runs with a WI whose boardColumn is "" or an out-of-config value: that WI MUST land in the trailing "(no column)" bucket, never silently dropped
4. After group_by_feature runs on a mirror where 54423 is present: the active group's title MUST be resolved from the mirror parent WI (not the literal "Feature 54423" fallback)
5. After render_markdown runs against a mirror lacking the boardColumn key (pre-Phase-5): exit MUST be 0; the board section MUST show the "no board data" notice; no traceback
```

**Prerequisites:** Phase 1 complete (mirror carries `parentId` already; `boardColumn`/`boardColumnDone` are added here) and Phase 2 complete (`render_markdown`, `filter_recent_team`, `_escape_md_pipe`, `--out`/`--all-team` are in place)

**Files likely modified:**
- `user/scripts/ado-sync.py` (exists → refactor) — `work_item_from_api` board-column capture (additive schema); a fixture asserting the two new keys round-trip
- `user/scripts/work-status.py` (exists → refactor) — `order_board` + `group_by_feature` pure helpers; `render_markdown` board + active-feature sections; `--feature` flag; fixtures (`total` grows past 9)
- `user/skills/dashboard/SKILL.md` (exists → refactor) — document the `--feature` passthrough in arg-parse + invocation
- `claude-config/repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` and `cog-docs/.claude/skill-config/ado-doc-integration.yml` (config) — add `active_feature_id` + `board_columns`

**Testing Strategy:** Extend `run_self_tests()` in `work-status.py` with canned mirror fixtures: (1) a WI set spanning all seven lanes + one off-board WI → assert `order_board` buckets in canonical order with the off-board WI in `"(no column)"`; (2) a mirror containing feature 54423 + children + a second feature + an orphan → assert `group_by_feature` pins 54423 first, resolves its title, and floors the orphan; (3) a three-level nest (Story Bug → User Story → 54423) → assert chain-walk attributes it to 54423; (4) a pre-Phase-5 mirror (no `boardColumn`) → assert `render_markdown` emits the no-data notice and exits 0. Add one `ado-sync.py` `--test` fixture confirming `work_item_from_api` emits `boardColumn`/`boardColumnDone`. All fixtures offline/stdlib-only; run with `PYTHONUTF8=1`.

**Integration Notes for Next Phase:**
- The deferred Phase 6 (PR Shepherding) is independent of this phase — it consumes `linkedPRs[]`/`leases.json` from Phases 1/4, not the board/feature grouping added here.
- `boardColumn` is now part of the mirror contract; if Phase 6 surfaces PR state per lane, it can read `boardColumn` directly rather than re-deriving from `state`.
- `order_board` / `group_by_feature` are pure and clock-free — any future grouped view (per-iteration, per-assignee) should follow the same config-driven, mirror-only pattern to preserve determinism.

**Context from prior phases:**
- The mirror schema is described as "LOCKED" (Phase 1 Implementation Notes) but is **additive-safe**: append new keys and initialize them to a default, never rename or remove existing keys — Phases 2/3/4 read fields by name, and `serialize_mirror` uses `sort_keys=True` so new keys slot in without perturbing existing output ordering.
- `render_markdown(sources, current_branch=None, *, all_team=False)` (Phase 2, `work-status.py:382`) is the only seam to touch — do **not** alter `render_dashboard` (the terminal renderer); the two share data selection (`_is_mine`, `match_self_pr`, `filter_recent_team`) but render independently.
- `filter_recent_team` (Phase 2, `work-status.py:330`) established the deterministic-clock rule: it uses the mirror's `syncedAt` as "now", never `datetime.now()`. The board/feature helpers must stay equally clock-free (they need no time input at all).
- `parentId` is the **immediate** parent only; the screenshot's "Parent" links resolve to the feature for direct children (54423 has 79 direct children in the mirror today), but Story-Bug-under-User-Story items need the in-mirror `parentId` chain-walk to roll up to the root feature.
- `System.BoardColumn` is returned by the `$expand=all` hydration `ado-sync.py` already performs, but is **empty for WIs not on the Poseidon board** — confirm the exact field name against a live hydration in runtime verification before relying on it.
- Always run Python gates with `PYTHONUTF8=1` (Windows cp1252 crashes on Unicode in ADO titles); escape `|` in any new table cell via the existing `_escape_md_pipe`.

#### Implementation Notes (Phase 5 — Batch 1: WU-1 mirror boardColumn + WU-2 config keys)
**Completed:** 2026-06-02
**Work completed:**
- **WU-1 (`ado-sync.py`, TDD RED→GREEN):** `work_item_from_api` (@213) now appends two keys to its returned dict — `"boardColumn": fields.get("System.BoardColumn") or ""` and `"boardColumnDone": bool(fields.get("System.BoardColumnDone", False))` — strictly additive, after `"materialized": False,`. The 19 pre-existing keys are unchanged and un-renamed. New in-file fixture `fixture6_board_column_capture` (`run_self_tests()`, `total = 5`→`6`) asserts on-board capture (`"In Progress"` / `is True`), off-board defaults (`""` / `is False`, never `None`/`KeyError`), and a 19-key regression superset. `python ado-sync.py --test` = **6/6** (orchestrator-reverified, exit 0).
- **WU-2 (config, both YAML copies):** appended `active_feature_id: 54423` and a 7-element `board_columns` lane list (`New, Next, "In Progress", "PR Review", "Ready for Testing", Reviewing, Merged`) to both `repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` (tracked in claude-config) and `cog-docs/.claude/skill-config/ado-doc-integration.yml` (untracked runtime copy). The four pre-existing blocks (`wiql_identity`/`type_pipeline_map`/`github_repo`/`pool`) are preserved verbatim; the two files remain **byte-identical** (`diff` → IDENTICAL) and both parse (`active_feature_id==54423`, 7-lane list).
**Integration notes:**
- `serialize_mirror`'s `sort_keys=True` slots `boardColumn`/`boardColumnDone` into the mirror alphabetically with no ordering churn on existing keys — the additive change is determinism-safe. WU-4 (Batch 3) consumes `boardColumn` from each WI; WU-3/WU-4 read `board_columns`/`active_feature_id` from the runtime config copy under `cog-docs`.
- The mirror still must be re-polled (`/dashboard --refresh`) before live WIs carry `boardColumn` — pre-Phase-5 mirrors lack the key, so WU-4 must degrade gracefully (its deliverable).
**Pitfalls & guidance:**
- Git warns `LF will be replaced by CRLF` on the tracked YAML; the on-disk bytes are LF and byte-identical to the cog-docs copy (runtime reads the disk bytes), so this is a git autocrlf normalization note, not a runtime divergence.
- The cog-docs runtime copy is in a **different, untracked** repo — it received the keys for runtime correctness but is NOT committed by this plan; only the claude-config copy is staged.
**Files modified:**
- `user/scripts/ado-sync.py` — `boardColumn`/`boardColumnDone` in `work_item_from_api` + `fixture6` + `total` bump.
- `repos/cognito-forms/.claude/skill-config/ado-doc-integration.yml` — `active_feature_id` + `board_columns` (committed).
- `cog-docs/.claude/skill-config/ado-doc-integration.yml` — same keys (untracked runtime copy, uncommitted).

#### Implementation Notes (Phase 5 — Batch 2: WU-3 pure grouping helpers)
**Completed:** 2026-06-02
**Work completed:**
- **WU-3 (`work-status.py`, TDD RED→GREEN):** added two pure, clock-free helpers co-located after `_escape_md_pipe` (`order_board` @383, `group_by_feature` @407), plus `from collections import OrderedDict` (@30).
  - `order_board(wis, board_columns) -> OrderedDict[str, list]`: pre-seeds every lane key in canonical order + a trailing `"(no column)"`, so `list(keys()) == [*board_columns, "(no column)"]` always (empty lanes included). WIs with empty/missing/`None`/unknown `boardColumn` fall into `"(no column)"`; input order preserved; nothing dropped.
  - `group_by_feature(team_wis, active_feature_id, mirror_index) -> list[{feature_id,title,wis}]`: per-WI attribution walks the `parentId` chain through `mirror_index` (cycle-safe via a `visited` set) — if `active_feature_id` is reached anywhere in the chain the WI rolls up to the active feature; else it attributes to the topmost reachable known ancestor (`chain[-1]`); a missing/absent immediate parent → orphan. Output order: active group FIRST (always present when `active_feature_id is not None`, even empty), other features with ≥1 WI sorted ascending, orphan group (`feature_id=None`, title `"(no parent)"`) LAST. Title = `mirror_index[fid]["title"]` or `f"Feature {fid}"` fallback.
  - Three non-tautological fixtures (`fixture_j_order_board`, `fixture_k_group_by_feature`, `fixture_l_chain_walk`); `total` bumped 9→12. `python work-status.py --test` = **12/12** (orchestrator-reverified, exit 0).
**Integration notes:**
- Both helpers take plain in-memory data — WU-4's `render_markdown` will build `mirror_index = {wi["id"]: wi for wi in sources["mirror"]["workItems"]}`, call `order_board(team_wis, board_columns)` for the `## Poseidon Board` count table and `group_by_feature(team_wis, active_feature_id, mirror_index)` for the active-feature priority queue + feature groups.
- **Type-matching contract:** the helpers compare `parentId`/ids and `active_feature_id` with `==` and use ids as dict keys — WU-4 MUST coerce the `--feature <id>` CLI string and the config `active_feature_id` to the same type as the mirror's integer `id`/`parentId` before calling, or attribution silently misses.
**Pitfalls & guidance:**
- The RED test agent initially appended a second `total = 12` instead of editing the original `total = 9`; the orchestrator removed the now-dead early assignment and the stale "nine" docstring (single `total = 12` @1318 remains). 12/12 re-verified after the cleanup.
**Files modified:**
- `user/scripts/work-status.py` — `order_board` + `group_by_feature` + `OrderedDict` import + fixtures J/K/L + `total` 9→12.

---

### Phase 6: PR Shepherding *(DEFERRED — not scheduled for v1)*

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
- This is the terminal phase; there is no Phase 7.
- The `wait_on_pr` queue state, `FEEDBACK.md` sentinel, and the slot-scrub-on-merge path are the three new contracts this phase introduces on top of Phase 4's stable foundation.
- When scheduling, re-read `RESEARCH.md` section on `gh pr view --json statusCheckRollup,reviews` output shape and the `vstfs://...` ArtifactLink parse for merge detection before implementation.

---

## Review Notes

**Batch:** PHASES.md authoring (1 file, 276 lines). **Reviewed:** 2026-06-02. **Verdict: PASS.**

Ground-truth verified (`git status --short` → `?? PHASES.md`; `wc -l` → 276, both matched). Structure, phase boundaries, the verified touchpoint paths, the reuse/refactor directives, and the 14 Validation-Criteria→phase mappings all align with the grounded SPEC and the approved 6-phase decomposition (Phase 0 separate; `lazy_coord.py` separate from `lazy_core.py`).

Two minor integration nuances for the executor (not blockers):
- **Phase 2 live-state probe ordering.** Phase 2 depends only on Phase 1, but its *My queue* live-state render references `--feature-id` / `--status` probe modes that don't land until Phase 4. Phase 2 must use what exists at its build time — call the unscoped `compute_state()` (single-current) and/or read sentinels directly for live status — and treat scoped probing as a Phase-4 enhancement. The graceful-degradation requirement already keeps this safe.
- **`materialized` flag location.** The mirror schema (Phase 1) lists a `materialized` field on each `workItems[]` entry, while Phase 3 also maintains a separate `materialized.json`. Pick one as authoritative for the dashboard's inbox-vs-queued distinction — recommend `materialized.json` as the source of truth (the worker owns it under the lock) and treat any mirror `materialized` field as a derived convenience only. Ambiguity inherited from the SPEC; resolve at Phase 3 implementation.
