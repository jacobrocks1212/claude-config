---
kind: research-summary
feature_id: cross-platform-setup
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — cross-platform-setup

Internal codebase survey verifying every surface the SPEC names. No external research needed —
the reference implementation (`setup.ps1`) and its data file (`manifest.psd1`) are both in-repo.

## Surfaces verified

### `manifest.psd1` (repo root, 81 lines)

Verified grammar corpus — the FULL set of constructs the file uses (the D1 parser's scope):

- One top-level hashtable literal `@{ … }`.
- Keys: bare words (`User`, `Personal`, `Workspace`, `Repos`, `Live`, `Repo`, `Type`, `Path`,
  `Alias`, `RootFiles`, `DotClaudeFiles`, `DotClaudeDirs`) and single-quoted strings
  (`'cognito-forms'`, `'cognito-forms-B'`, …).
- Values: single-quoted strings only (no double-quoted strings currently present, no `''`
  escapes currently present — the parser still supports both per the psd1 spec subset),
  arrays `@( … )` with newline AND comma separation (RootFiles mixes both), nested hashtables
  (array-of-hashtable in User/Personal/Workspace; hashtable-of-hashtable in Repos).
- `#` line comments, both full-line and after values? — verified: comments appear on their own
  lines only (lines 3, 8, 11, 30–32, 44–51), but the parser strips trailing comments too
  (cheap, spec-conformant).
- NOT present anywhere: variables, expressions, here-strings, type literals, double quotes.

Structure facts the expansion logic consumes:

- `User` = 11 entries (6 Directory incl. two `plugins\local-tools\plugins\*` nested paths,
  5 File incl. untracked `CLAUDE.local.md` / `settings.local.json` — both-absent → NONE/ABSENT).
- `Personal` / `Workspace` = 1 File entry each.
- `Repos` = 5 entries: `cognito-forms` (full: Path, RootFiles ×13 incl. nested subpaths like
  `Cognito.Web.Client\apps\spa\CLAUDE.local.md`, DotClaudeFiles ×14 incl. nested
  `hooks\normalize-crlf.ps1` / `commands\*.md` / `scripts\*.ps1`, DotClaudeDirs ×3),
  `cognito-forms-B/C/D` (Path + `Alias = 'cognito-forms'`), `cognito-docs` (Path +
  DotClaudeFiles ×1, NO RootFiles/DotClaudeDirs — expansion must tolerate absent keys).
- All Repos `Path` values are absolute Windows paths (`C:\Users\JacobMadsen\source\repos\…`),
  one containing a SPACE (`Cognito Forms`) — on POSIX these never exist → skip_absent unless
  `--repos-root` remaps.

### `setup.ps1` (repo root, 396 lines) — reference semantics

- `Expand-LivePath` (line 16): `~` prefix → `$env:USERPROFILE`. Port: platform home
  (`USERPROFILE` on nt, `HOME` on POSIX) + `\`→os.sep normalization (PowerShell tolerates `\`
  natively; Python on Linux must convert).
- `Get-AllMappings` (line 38): User/Personal/Workspace pass entries through; Repos iterates
  `Repos.Keys | Sort-Object` (port: sorted(keys)), resolves `Alias` → source config for
  RootFiles/DotClaudeFiles/DotClaudeDirs while `Live` base stays the ALIAS entry's own `Path`
  and `Repo` uses the alias-TARGET name (`repos\<configName>\…`) — i.e. all four cognito
  worktrees share one repo-side config dir. RootFiles → `<Path>\<f>` (File);
  DotClaudeFiles → `<Path>\.claude\<f>` (File); DotClaudeDirs → `<Path>\.claude\<d>`
  (Directory). Section labels: `User`/`Personal`/`Workspace`/`Repo:<name>`.
- `Invoke-Bootstrap` (line 103), decision tree confirmed exactly as the SPEC parity table:
  correct link → SKIP; ensure repo parent; live-link-wrong + repo-exists → RELINK;
  live-link-wrong + repo-missing → COPYLINK (Copy-Item, recurse for dirs — NOTE: copies the
  link's *referent* content); live-real + repo-exists → WARN (skip); live-real + repo-missing
  → MOVE + link; live-missing + repo-exists → mkdir live parent + LINK (recovery);
  both-missing → NONE. Summary `Bootstrap: X moved, Y linked, Z skipped, W warnings`.
- `Invoke-Check` (line 175): live-missing → MISSING (broken) if repo exists else ABSENT
  (not broken); live-not-link → REAL (broken); target==repo (full-path compare, target
  resolved relative to link parent via `Resolve-Absolute`) → OK else WRONG (broken). Summary
  `Check: X OK, Y broken, Z absent`; returns `$broken -eq 0` (NOTE: setup.ps1 never maps this
  to `exit` — the port strengthens it to a real exit code, `0 iff broken==0`, documented).
  Plus THREE warn-only advisories (lines 218–334: turn-routing hook registration in live
  settings.json; Cognito team-doc DRIFT/BEHIND; UNREGISTERED subdir backfill) — exit-code
  neutral; NOT ported (SPEC D6).
- `Invoke-Repair` (line 339): repo-missing → skip; correct link → skip; wrong link → remove +
  relink; live-real → `Move-Item` to `<live>.bak` (BACKUP) then link; live-missing → mkdir
  parent + link. Summary `Repair: X fixed, Y OK`.
- `add-repo` verb (line 388): prints guidance only — not ported (SPEC D2 resolution).
- Link creation is ALWAYS `New-Item -ItemType SymbolicLink` (file and directory alike; no
  junctions today). Link detection = ReparsePoint attribute (line 24) — junctions WOULD pass
  it, so the port's "junction counts as link" (D3) is consistent with the PS check.

## Integration points

- **Gate suite:** new `user/scripts/test_setup_py.py` (pytest) — loaded via
  `importlib.util.spec_from_file_location` (repo-root `setup.py` is not importable as a
  package member; unique module name avoids setuptools-shim collisions). Runs from
  `user/scripts` like every other suite; added to the lane gate invocation.
- **Docs:** root `CLAUDE.md` "Setup Commands" (line ~78) gains the `python3 setup.py` forms;
  `user/scripts/CLAUDE.md` gains a short `test_setup_py.py` note (the script itself lives at
  repo root, deliberately — D2).
- **No state-script surface touched:** `lazy_core.py`/`lazy-state.py`/`bug-state.py`/hooks/
  skills are untouched; parity audit unaffected. `setup.py` imports nothing from
  `user/scripts/` (must run on a bare clone).

## Spec assumptions checked — corrections

1. **Stub said "`~/.claude/` exists there too" (cloud):** verified in THIS container — the live
   `~/.claude` symlink layout does NOT exist (bare clone; LANE_PROTOCOL rule 6 confirms).
   `check` on a fresh container legitimately reports MISSING rows → exit 1. Honest, per D5.
2. **`setup.ps1` check "exit code":** the PS function returns a bool that the script never
   propagates to `$LASTEXITCODE` — so "matching setup.ps1's exit semantics" would mean exit 0
   always. The port deliberately hardens this: `check` exits 0 iff broken==0 (SPEC UX section).
   Recorded as an intentional improvement, not parity drift.
3. **Absent-repo handling:** setup.ps1 does NOT skip absent worktrees in bootstrap/repair — it
   would `New-Item` parent dirs and link into a non-existent worktree location (creating
   orphan dirs). D5's skip_absent (whole entry skipped when base `Path` absent) is a deliberate
   divergence, operator-approved.
4. **`fix-line-endings` hazard check:** `setup.py` and `test_setup_py.py` are new `\n`-only
   files; no CRLF interaction (the hook is unwired; nothing normalizes them).

## Risks

- Parser under-tolerance breaking future manifest edits → mitigated: `_die()` is loud with a
  line number, and the real manifest is a pinned test fixture (any manifest edit that the
  parser can't read fails `test_setup_py.py` immediately).
- Windows branch untestable here → mocked-platform unit tests (D3), honestly labeled; live
  junction fallback exercised on first Windows soak (SPEC deferred list).
