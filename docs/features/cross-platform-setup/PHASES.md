# Implementation Phases — Cross-Platform Setup (Python Port of setup.ps1/manifest.psd1)

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
<!-- All 4 phases implemented + validated 2026-07-04 (test_setup_py 66 green; full gate suite
     1268 passed + 2 sanctioned skips; parity audit exit 0; lint clean; live container e2e:
     bootstrap --target User -> 11 linked, check exit 0). NOT Complete on the SPEC — the
     __mark_complete__ integrity gate owns the SPEC Complete flip + COMPLETED.md receipt. -->

**MCP runtime:** not-required — pure claude-config harness mechanics (a stdlib-only Python CLI at
the repo root porting `setup.ps1`'s symlink bootstrap/check/repair). No Tauri app, no
MCP-reachable surface; validation is `pytest` on `user/scripts/test_setup_py.py` (hermetic
temp-`HOME` + temp-repo fixtures, incl. an end-to-end User-scope bootstrap→check round-trip)
plus the standard repo gate suite. This is the `standalone — no app integration` untestable
class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. This feature ports already-shipped root-level tooling; no sibling
feature's PHASES.md is upstream:

- **`setup.ps1` / `manifest.psd1` (repo root):** the reference implementation and its single
  source of truth. This feature reads BOTH and changes NEITHER (SPEC D1/D4 — `git diff
  setup.ps1 manifest.psd1` must stay empty).
- **Lazy pipeline (`user/scripts/*`):** untouched. `setup.py` imports nothing from
  `user/scripts/` (must run on a bare clone before any layout exists); only the NEW test file
  `user/scripts/test_setup_py.py` lands there so the standard gate suite location picks it up.
  `lazy_parity_audit.py` surface unaffected.
- **`windows-portability-in-probe-glue-and-field-validators` (bug, shipped):** motivating bug
  class; no code coupling. New files are `\n`-only; the unwired `fix-line-endings.ps1` hook is
  irrelevant to them.

---

### Phase 1: Minimal tolerant psd1 parser

**Phase kind:** design

**Scope:** `parse_psd1(text) -> dict` in a new repo-root `setup.py`, scoped to the manifest's
actual grammar (SPEC D1-A): top-level/nested hashtable literals, arrays (newline/comma/semicolon
separated), single-quoted strings (`''` escape), double-quoted strings (die on `$`/backtick),
bare-word + quoted keys, `#` comments. Any other construct → `_die()` (SetupError → exit 2)
naming the offending line. No CLI yet.

**Deliverables:**
- [x] `setup.py`: `SetupError` + `_die(msg)`; tokenizer + recursive-descent `parse_psd1(text)`
  returning plain dict/list/str values.
- [x] `user/scripts/test_setup_py.py` (pytest, loads `setup.py` via
  `importlib.util.spec_from_file_location` under a unique module name): grammar fixtures —
  nested hashtables, arrays with newline AND comma separation, `''` escape, double-quoted
  string, comments (full-line + trailing), quoted keys.
- [x] Loud-die fixtures: `$variable`, here-string `@'…'@`, expression `(1+2)`, unterminated
  string — each raises SetupError naming a line number.
- [x] REAL-manifest fixture: `parse_psd1(<repo>/manifest.psd1)` succeeds; assert the four
  scopes, User count/types, the cognito alias chain (`cognito-forms-B`→`Alias='cognito-forms'`),
  nested RootFiles subpaths, and `cognito-docs` lacking RootFiles/DotClaudeDirs.

**Minimum Verifiable Behavior:** `parse_psd1(open('manifest.psd1').read())` returns a dict whose
`Repos['cognito-forms']['DotClaudeDirs'] == ['skill-config', 'skills', 'knowledge']`; feeding it
a `$var` line raises SetupError citing that line.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] The real `manifest.psd1` parses with the exact shape `setup.ps1`'s
  `Import-PowerShellDataFile` sees (spot-asserted per structure facts in RESEARCH_SUMMARY.md). *(Evidence: `test_setup_py.py::TestParsePsd1RealManifest` — 6 tests incl. alias chain, nested RootFiles, optional-keys-absent.)*
<!-- verification-only -->
- [x] Unknown grammar dies loudly (exit-2 class), never silently tolerated. *(Evidence: `test_setup_py.py::TestParsePsd1Dies` — 7 loud-die cases, each asserting the cited line number.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (first phase).

**Files likely modified:** `setup.py` (new), `user/scripts/test_setup_py.py` (new).

**Testing Strategy:** Pure-function pytest; TDD (fixtures written failing first). No filesystem
side effects in this phase.

**Integration Notes for Next Phase:** Phase 2 consumes the parsed dict; the parser's output
shape (plain dict/list/str, keys as written) is the contract.

---

### Phase 2: Mapping expansion + per-platform link primitives

**Phase kind:** design

**Scope:** Pure `expand_mappings(manifest, repo_root, target, repos_root=None) -> list[Mapping]`
mirroring `Get-AllMappings` (scopes filter, alias resolution, RootFiles/DotClaudeFiles/
DotClaudeDirs, section labels `User`/`Personal`/`Workspace`/`Repo:<name>`), path expansion
(`~` → platform home, `\` → host separators), `--repos-root` remap
(`<repos_root>/<basename(Path)>`), and skip_absent flagging for Repos entries whose base Path
dir is absent (SPEC D5). Plus the D3 link primitives: `_is_link`, `_read_link_target`,
`_create_link(live, repo, is_dir)` with the Windows symlink→junction/loud-error selection.

**Deliverables:**
- [x] `setup.py`: `expand_live_path` (home expansion per `USERPROFILE`/`HOME`), separator
  normalization, `Mapping` records (live, repo, type, section, skip_absent[+reason]).
- [x] `expand_mappings`: target filtering (All/User/Personal/Workspace/Repos), Repos iteration
  in sorted-key order, alias → source-config resolution with live base = alias entry's Path and
  repo side = `repos/<alias-target>/…`, tolerant of absent RootFiles/DotClaudeFiles/
  DotClaudeDirs keys, `repos_root` remap, skip_absent flag.
- [x] `_is_link` (POSIX: `os.path.islink`; Windows: also readlink-probe for junctions),
  `_read_link_target`, `_resolve_target` (relative-to-link-parent + normcase compare, mirroring
  `Resolve-Absolute`/`GetFullPath`), `_create_link` (POSIX symlink; Windows symlink-first,
  junction fallback for dirs via a patchable `_create_junction`, SetupError for
  privilege-blocked files).
- [x] Tests: expansion fixtures (each scope; alias; nested subpaths; missing optional keys;
  repos-root remap; skip_absent; target filter); real-manifest expansion count/spot checks;
  mocked-platform Windows selection tests (symlink OK → symlink; OSError+dir → junction
  helper called; OSError+file → SetupError with actionable message).

**Minimum Verifiable Behavior:** With a temp HOME and the real manifest,
`expand_mappings(m, repo_root, 'User')` yields 11 mappings whose live paths sit under the temp
`~/.claude/` and repo paths under `<repo_root>/user/`; a `cognito-forms-B` mapping's repo path
contains `repos/cognito-forms/` while its live path is under the B worktree Path.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Alias worktrees share one repo-side config dir while linking their own live locations. *(Evidence: `test_setup_py.py::TestExpandMappings::test_alias_repo_resolves_source_config_own_live_base`.)*
<!-- verification-only -->
- [x] Windows selection logic: junction fallback (dirs) and loud file error occur ONLY on the
  mocked nt branch; POSIX path is a plain symlink. *(Evidence: `test_setup_py.py::TestCreateLinkWindowsSelection` — 5 mocked-platform cases + `TestLinkPrimitivesPosix`.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (`parse_psd1` output shape).

**Files likely modified:** `setup.py`, `user/scripts/test_setup_py.py`.

**Testing Strategy:** Hermetic temp `HOME` (monkeypatched `HOME`/`USERPROFILE`) + temp dirs;
mocked `os.name`/`os.symlink`/`_create_junction` for the Windows-only branch (exercised on
Windows only in production — honestly labeled).

**Integration Notes for Next Phase:** Phase 3's verbs consume `Mapping` records and the link
primitives only — no verb re-derives paths or platform logic.

---

### Phase 3: bootstrap / check / repair verbs + CLI + end-to-end

**Phase kind:** feature

**Scope:** The three verbs mirroring `setup.ps1` one-for-one per the SPEC's normative parity
table, argparse CLI (`bootstrap|check|repair`, `--target {All,User,Personal,Workspace,Repos}`
default All, `--repos-root`), output labels + summary lines, exit codes (`check` 0 iff
broken==0 else 1; errors exit 2), skip_absent rendering (`SKIP (repo absent: <path>)`).

**Deliverables:**
- [x] `cmd_bootstrap`: SKIP / RELINK / COPYLINK (referent copy, recurse for dirs) / MOVE /
  WARN (both exist) / LINK (recovery) / NONE; repo-parent + live-parent dir creation; summary
  `Bootstrap: X moved, Y linked, Z skipped, W warnings`.
- [x] `cmd_check`: OK / MISSING (broken) / ABSENT / REAL (broken) / WRONG (broken); summary
  `Check: X OK, Y broken, Z absent`; exit 0 iff broken==0 (documented hardening over
  setup.ps1's unpropagated bool — RESEARCH_SUMMARY correction 2).
- [x] `cmd_repair`: skip (repo missing / already correct) / wrong-link relink / BACKUP
  (`<live>.bak`) + REPAIR / missing-live REPAIR; summary `Repair: X fixed, Y OK`.
- [x] CLI `main(argv)`: header (`command | target | root | mappings: N`), SetupError → stderr +
  exit 2; `python3 setup.py …` runnable from any cwd (repo root derived from `__file__`).
- [x] Tests: one fixture per parity-table row for each verb (Linux symlinks); check exit-code
  cases; skip_absent never-broken/never-materialized; repair→check round-trip; CLI subprocess
  smoke (`python3 setup.py check` on a fixture layout).
- [x] End-to-end: temp `HOME` + the REAL repo clone — `bootstrap --target User` materializes
  `~/.claude/{skills,hooks,scripts,templates,CLAUDE.md,settings.json,keybindings.json}` links
  into the worktree and `check --target User` exits 0 (untracked `CLAUDE.local.md`/
  `settings.local.json` rows render NONE/ABSENT, not broken).

**Minimum Verifiable Behavior:** In a temp `HOME`, `python3 setup.py bootstrap --target User`
followed by `python3 setup.py check --target User` exits 0 with every present mapping OK;
editing through a live link writes through to the repo file (symlink write-through).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] End-to-end cloud self-host: fresh temp HOME → bootstrap User → check exits 0; links
  resolve into the clone. *(Evidence: `test_setup_py.py::TestEndToEnd` — 2 subprocess e2e tests incl. idempotence; live container run recorded in SKIP_MCP_TEST.md.)*
<!-- verification-only -->
- [x] Honest check on an empty container HOME: MISSING rows, exit 1. *(Evidence: `test_setup_py.py::TestCli::test_check_header_and_honest_exit_on_empty_home` + `TestCheck::test_missing_is_broken_exit_1`.)*
<!-- verification-only -->
- [x] Every bootstrap/check/repair parity-table row produces the same action label + filesystem
  effect as `setup.ps1`'s documented behavior. *(Evidence: `test_setup_py.py` — TestBootstrap 9 rows, TestCheck 6 verdicts, TestRepair 6 rows.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2.

**Files likely modified:** `setup.py`, `user/scripts/test_setup_py.py`.

**Testing Strategy:** TDD per verb row; subprocess tests pass an env with temp `HOME` (never
the session's real `~/.claude` — LANE rule 6); e2e uses the actual worktree as repo_root
read-only on the repo side (links point INTO it; nothing inside the repo is written).

**Integration Notes for Next Phase:** Phase 4 is docs + gates only — no behavior change.

---

### Phase 4: Documentation + gate suite

**Phase kind:** chore

**Scope:** Doc rows the SPEC lists; full repo gate suite; skip receipt.

**Deliverables:**
- [x] Root `CLAUDE.md` "Setup Commands": add the cross-platform `python3 setup.py` forms
  (check / bootstrap --target User / repair / --repos-root note) alongside the PowerShell
  block; tightly scoped (no reflow of other text).
- [x] `user/scripts/CLAUDE.md`: short note that `test_setup_py.py` covers the repo-root
  `setup.py` (stdlib-only cross-platform port of `setup.ps1`; script deliberately NOT in this
  directory — must run on a bare clone).
- [x] Full gate suite green (all pytest suites incl. `test_setup_py.py`, `--test` harnesses,
  parity audit, lint-skills) with only the two sanctioned skips.
- [x] `SKIP_MCP_TEST.md` (standalone — no app integration) naming suites + counts +
  `validated_commit`.

**Minimum Verifiable Behavior:** Gate suite green; `git diff setup.ps1 manifest.psd1` empty;
docs name the Python forms.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Full gate suite green with exactly the two sanctioned skips. *(Evidence: SKIP_MCP_TEST.md — pytest 1268 passed / 2 sanctioned skips; smoke + parity + lint green; `git diff setup.ps1 manifest.psd1` empty.)*
<!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `CLAUDE.md`, `user/scripts/CLAUDE.md`,
`docs/features/cross-platform-setup/SKIP_MCP_TEST.md`.

**Testing Strategy:** Docs/lint only; full harness gate suite as final acceptance.
