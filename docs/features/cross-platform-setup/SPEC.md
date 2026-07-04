# Cross-Platform Setup (Python Port of setup.ps1/manifest.psd1) — Feature Specification

> Bootstrap/check/repair is PowerShell-only, so Linux/cloud containers can't materialize the
> symlink layout, and the windows-portability bug class keeps recurring. A stdlib-only Python
> `setup.py bootstrap|check|repair` at the repo root — reading the EXISTING `manifest.psd1`
> through a minimal tolerant psd1 parser — makes the harness self-hosting in cloud sessions
> while keeping one manifest as the single source of truth and keeping `setup.ps1` working
> unchanged on Windows.

**Status:** Complete
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; baseline-locked 2026-07-04 (Gemini
research skipped by operator directive — internal codebase survey in RESEARCH_SUMMARY.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented artifacts**, not
> sibling specs:
> - `manifest.psd1` — the symlink-mapping source of truth (four scopes: `User`, `Personal`,
>   `Workspace`, `Repos`; per-repo `Path`/`Alias`/`RootFiles`/`DotClaudeFiles`/`DotClaudeDirs`).
> - `setup.ps1` — the reference implementation whose bootstrap/check/repair semantics the port
>   must mirror (mapping expansion, SKIP/RELINK/COPYLINK/MOVE/LINK/NONE/WARN bootstrap actions,
>   OK/MISSING/ABSENT/REAL/WRONG check verdicts, BACKUP/REPAIR repair actions).
> - Root `CLAUDE.md` "Symlink System" section — the operator-facing contract both scripts serve.

---

## Executive Summary

The symlink system is this repo's core mechanism — every live config location (`~/.claude/`,
`~/.claude-personal/`, `~/source/repos/CLAUDE.md`, per-repo `.claude/`) is a link back into this
repo — and it is unreachable from non-Windows hosts: `manifest.psd1` is a PowerShell data file
and `setup.ps1` requires PowerShell. Cloud sessions (including `/lazy-batch-cloud` runs against
this very repo) operate on a bare clone without the write-through layout, and portability fixes
get rediscovered per-bug (`windows-portability-in-probe-glue-and-field-validators`).

This feature ships a **stdlib-only `setup.py` at the repo root** with the same three verbs
(`bootstrap`, `check`, `repair`), the same scoping flag (`--target {All,User,Personal,Workspace,
Repos}`), and the same mapping semantics as `setup.ps1` — parsing the **existing `manifest.psd1`
directly** via a minimal, tolerant psd1 reader scoped to the manifest's actual grammar
(hashtable literals, arrays, nested hashtables, single/double-quoted strings, comments). No
second manifest file exists, so no drift is possible; the parser dies loudly on any construct it
cannot handle rather than guessing. Link strategy is per-platform: plain symlinks on POSIX; on
Windows, symlink-first with a directory-junction fallback (privilege-free) and a loud
actionable error for privilege-blocked file links. `setup.ps1` is kept as-is; retirement is a
separate operator decision after `setup.py` has soaked on Windows.

The cloud story falls out naturally: live locations are the real `~/.claude`,
`~/.claude-personal`, `~/source/repos` paths resolved from `HOME`, so in an ephemeral container
`check` reports missing links honestly and `bootstrap --target User` materializes the User scope
(skills/hooks/scripts/templates/CLAUDE.md/settings) so cloud sessions can self-host. Repos scope
links only repos actually present on disk (skip-absent with a note); `--repos-root` remaps the
manifest's Windows repo paths onto a host-local checkout root.

## Design Decisions

### D1. Manifest format: KEEP `manifest.psd1` as the single source of truth, parsed from Python

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** Parse `.psd1` from Python, or migrate to JSON/TOML (with or without a psd1 shim)?
- **Options:**
  - **A — keep `manifest.psd1`, add a minimal tolerant psd1 reader in `setup.py`
    (recommended):** the parser is scoped to this manifest's ACTUAL grammar — top-level
    hashtable literal `@{…}`, nested hashtables, arrays `@(…)` (newline- or comma-separated),
    single-quoted strings (with `''` escape), double-quoted strings (no interpolation — a `$`
    inside one is a parse error), `#` line comments, bare-word and quoted keys. Anything outside
    that grammar (expressions, variables, type accelerators, here-strings) makes the parser
    `_die()` loudly with the offending line. Pros: ONE manifest, zero drift risk, `setup.ps1`
    keeps `Import-PowerShellDataFile`-ing the same file unchanged; the grammar subset is stable
    (the manifest has only ever used these constructs). Cons: a hand-rolled parser is new code —
    mitigated by fixture tests PLUS a test that parses the real `manifest.psd1`.
  - **B — migrate to JSON/TOML with a psd1 shim during transition:** two files describing the
    same mappings is exactly the drift failure mode the stub warned about; the shim would need
    its own sync check.
- **Resolution:** A. Single source of truth preserved; the parser's failure contract is
  "loud and early", never silent tolerance of constructs it doesn't understand.

### D2. Script shape: stdlib-only `setup.py` at the repo root, `bootstrap|check|repair`, `--target` + `--repos-root`

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** What is the Python entrypoint's surface?
- **Options:**
  - **A — `setup.py` at the repo root (recommended):** sibling of `setup.ps1`, stdlib-only
    (python3 ≥ 3.9, no pip installs), subcommands `bootstrap`, `check`, `repair`; flags
    `--target {All,User,Personal,Workspace,Repos}` (default `All`, mirroring `-Target`) and
    `--repos-root <dir>` (maps each Repos entry's manifest `Path` to
    `<repos-root>/<basename(Path)>` so a non-Windows host can link repo checkouts living under
    a different root). Exit codes: `check` exits 0 iff zero broken mappings; `bootstrap`/
    `repair` exit 0 on completion; any manifest/parse/link error exits 2 with a loud message.
    Pros: mirrors `setup.ps1`'s CLI one-for-one; discoverable next to the file it ports.
    Cons: the name `setup.py` collides with the legacy setuptools convention — harmless here
    (this repo is not a Python package and nothing pip-installs it), and the name symmetry with
    `setup.ps1` is worth more.
  - **B — `user/scripts/setup.py`:** hides the entrypoint away from the manifest and
    `setup.ps1` it pairs with.
- **Resolution:** A. `setup.ps1`'s `add-repo` verb (which only prints guidance) is NOT ported —
  the "Adding a New Repo" doc section already covers it; `setup.py` keeps to the three real
  verbs. Tests live at `user/scripts/test_setup_py.py` (pytest, temp-`HOME` hermetic) so the
  standard gate suite picks them up.

### D3. Per-platform link strategy: POSIX symlinks; Windows symlink-first with directory-junction fallback

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** How are links created per platform, and what happens when Windows denies
  symlink creation (no Developer Mode / no `SeCreateSymbolicLinkPrivilege`)?
- **Options:**
  - **A — POSIX: `os.symlink` always. Windows: try `os.symlink` (matching `setup.ps1`'s
    `New-Item -ItemType SymbolicLink` behavior); on a privilege `OSError`, fall back to a
    directory **junction** for `Type = Directory` mappings (junctions need no privilege) and
    raise a loud actionable error for `File` mappings ("enable Developer Mode or run
    elevated") (recommended):** link detection treats both symlinks and junctions as links
    (`os.path.islink` OR a successful `os.readlink` on Windows reparse points). Pros: parity
    with `setup.ps1` when privileged; strictly better than `setup.ps1` when unprivileged
    (directory scopes still materialize); the selection logic is pure and unit-testable with a
    mocked platform, which is how it is covered (this environment is Linux — the Windows branch
    is exercised on Windows only).
  - **B — junctions for all directories unconditionally:** diverges from `setup.ps1`'s current
    on-disk state (existing links are symlinks); junctions also store absolute targets only and
    behave differently across drive mappings.
  - **C — copy-instead-of-link fallback:** silently breaks the write-through contract — edits
    would no longer land in the repo. Never acceptable.
- **Resolution:** A. The check/repair verbs recognize either link kind as "linked"; target
  comparison uses the resolved absolute target (mirroring `setup.ps1`'s `Resolve-Absolute`
  against the link's parent).

### D4. `setup.ps1` is KEPT as-is

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** Is `setup.ps1` retired, rewritten as a thin caller of `setup.py`, or kept?
- **Options:**
  - **A — keep `setup.ps1` unchanged (recommended):** it is the battle-tested implementation on
    the primary (Windows) machine and carries Windows-only warn-only advisories the port
    deliberately does not take (D6). Retirement (or thin-caller conversion) is a **separate
    operator decision once `setup.py` has soaked on Windows** — not part of this feature.
  - **B — retire immediately / thin-caller now:** swaps the proven implementation out on the
    machine that depends on it most, before the port has any Windows soak time.
- **Resolution:** A. This SPEC changes zero lines of `setup.ps1`. The two scripts read the same
  manifest, so they cannot drift on mappings; behavioral parity is pinned by this SPEC's
  semantics table (below) and the port's tests.

### D5. Cloud story: HOME-resolved live locations; honest `check`; `bootstrap --target User` self-hosts; Repos skip-absent

- **Classification:** `product-behavior (operator-approved 2026-07-04 — recommended option taken)`
- **Question:** What do "live locations" mean in an ephemeral container, and which scopes make
  sense to link there?
- **Options:**
  - **A — live locations are the real `~/.claude`, `~/.claude-personal`, `~/source/repos` paths
    resolved from `HOME` (recommended):** the manifest's `~` prefix expands via the platform
    home (`USERPROFILE` on Windows, `HOME` on POSIX), exactly like `Expand-LivePath`. In an
    ephemeral container, `check` reports missing links **honestly** (they ARE missing);
    `bootstrap --target User` materializes the User scope (skills/hooks/scripts/templates/
    CLAUDE.md/settings) as symlinks into the clone so a cloud session can self-host the
    harness. Repos scope links only repos actually **present on disk**: a Repos entry whose
    base `Path` directory does not exist is skipped with a per-entry
    `SKIP (repo absent: <path>)` note — counted as skipped, never broken — matching
    `setup.ps1`'s tolerance of absent worktrees (its check counts a fully-absent mapping as
    `ABSENT`, not broken) while avoiding its bootstrap/repair behavior of materializing parent
    directories for absent worktrees. `--repos-root` (D2) is the lever for pointing Repos scope
    at a host-local checkout root.
  - **B — a container-specific "live layout" config:** a second source of truth about
    locations; drift again.
- **Resolution:** A. No special cloud mode flag exists — the same code runs everywhere; the
  container case is just "live locations start empty".

### D6. Ported `check` surface: symlink state only; `setup.ps1`'s warn-only advisories stay PowerShell-side

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** `setup.ps1`'s `check` carries three warn-only, exit-code-neutral advisory
  passes (turn-routing hook registration in live `settings.json`; Cognito worktree team-doc
  DRIFT/BEHIND detection; unregistered-subdir CLAUDE.local.md backfill guard). Does the port
  take them?
- **Options:**
  - **A — port symlink-state verification only (recommended):** the advisories are
    Windows-live-machine concerns (Cognito worktrees exist only there; hook registration
    matters on the armed machine), are warn-only by contract (never affect exit code), and
    `setup.ps1` — which remains the Windows tool per D4 — keeps running them. Porting them
    would triple the port's surface for zero cloud value.
  - **B — port everything:** parity for parity's sake; the advisories would be dead code on
    every host `setup.py` newly enables.
- **Resolution:** A. Documented as a deliberate, permanent divergence (not a TODO): `setup.py
  check` verifies mapping state; machine-specific advisories are `setup.ps1`'s.

## User Experience

The "users" are the operator (Windows workstation + occasional Linux) and cloud sessions
running against a bare clone.

```bash
# Anywhere (Linux, macOS, cloud container, Windows with python3):
python3 setup.py check                     # verify all symlinks; exit 0 iff none broken
python3 setup.py bootstrap --target User   # materialize ~/.claude/* links into this clone
python3 setup.py repair                    # fix broken/wrong links (real files -> .bak)
python3 setup.py bootstrap --target Repos --repos-root ~/source/repos
                                           # link per-repo .claude/ for repos present on disk
```

- **Output shape mirrors `setup.ps1`:** a header (`command | target | root | mappings: N`), one
  line per mapping with the same action labels (`SKIP`, `RELINK`, `COPYLINK`, `MOVE`, `LINK`,
  `NONE`, `WARN` for bootstrap; `OK`, `MISSING`, `ABSENT`, `REAL`, `WRONG` for check;
  `REPAIR`, `BACKUP` for repair; plus `SKIP (repo absent: …)` per D5), and the same summary
  line (`Bootstrap: X moved, Y linked, Z skipped, W warnings` / `Check: X OK, Y broken,
  Z absent` / `Repair: X fixed, Y OK`).
- **Failure is loud:** an unparseable manifest construct, a missing manifest, or a link-creation
  error prints the offending detail and exits 2 — never a silent partial pass.
- **On Windows without symlink privilege:** directory mappings still link (junction fallback);
  a file mapping fails with an actionable message naming Developer Mode / elevation. Nothing is
  ever copied in place of a link (D3-C rejected).
- **`setup.ps1` users notice nothing:** the PowerShell path is byte-identical to today.

## Technical Design

```
manifest.psd1 ──(minimal tolerant psd1 parser; _die() on unknown grammar)──▶ manifest dict
      │
      ▼
expand_mappings(manifest, target, repos_root)          [pure]
  User/Personal/Workspace: {live: ~-expanded, repo: <repo_root>/<rel>, type}
  Repos: alias resolution ──▶ source config (RootFiles / DotClaudeFiles / DotClaudeDirs)
         live base = entry Path (or <repos_root>/<basename(Path)>)
         base dir absent on disk ──▶ mapping flagged skip_absent
      │
      ▼
verbs (imperative, mirror setup.ps1 one-for-one)
  bootstrap: SKIP | RELINK | COPYLINK | MOVE | LINK | NONE | WARN
  check:     OK | MISSING | ABSENT | REAL | WRONG        (exit 0 iff broken == 0)
  repair:    REPAIR | BACKUP | skip
      │
      ▼
link primitives (per-platform, D3)
  _is_link / _read_link_target / _create_link(live, repo, is_dir)
    POSIX: os.symlink
    Windows: os.symlink ──OSError──▶ dir: junction fallback · file: loud error
```

- **One file:** all of the above lives in `setup.py` at the repo root (stdlib-only:
  `argparse`, `os`, `sys`, `shutil`, `pathlib`). No imports from `user/scripts/` — the script
  must run on a bare clone before any layout exists.
- **Parser contract:** `parse_psd1(text) -> dict` recognizes exactly the D1-A grammar.
  Separators are newlines and/or commas/semicolons; `#` comments stripped outside strings;
  single-quoted strings unescape `''`; double-quoted strings reject `$`/backtick interpolation
  by dying. Everything else (`$var`, `@'…'@`, `[type]`, parentheses-expressions) → `_die()`
  with line number. The REAL `manifest.psd1` is a pinned test fixture.
- **Path semantics:** manifest paths use `\` separators; the port normalizes separators
  per-host. `~` expands to the platform home. Absolute Windows paths (`C:\…`) on a POSIX host
  never exist → Repos entries resolve to skip_absent unless `--repos-root` remaps them.
  Target comparison in check/repair resolves the stored link target against the link's parent
  directory and compares normalized absolute paths (mirroring `Resolve-Absolute` +
  `GetFullPath`; `os.path.normcase` gives the Windows case-insensitivity `-eq` had, and is an
  exact-string comparison on POSIX).
- **Verb semantics parity table (normative):**

| Situation | setup.ps1 | setup.py |
|-----------|-----------|----------|
| live is link → repo | bootstrap SKIP / check OK / repair skip | identical |
| live is link → elsewhere, repo exists | RELINK / WRONG / REPAIR | identical |
| live is link → elsewhere, repo missing | COPYLINK (copy content into repo, relink) / WRONG / skip | identical |
| live real, repo exists | WARN both-exist / REAL / BACKUP+REPAIR (`<live>.bak`) | identical |
| live real, repo missing | MOVE into repo + link / REAL / skip | identical |
| live missing, repo exists | LINK (recovery) / MISSING (broken) / REPAIR | identical |
| both missing | NONE / ABSENT (not broken) / skip | identical |
| Repos entry base Path absent | (not distinguished; per-mapping fallthrough) | `SKIP (repo absent)` for the whole entry — never broken, never materialized (D5) |
| warn-only advisories | 3 advisory passes | not ported (D6) |

- **House invariants honored:** stdlib-only; no network; loud-fail (`_die` → exit 2) over
  silent tolerance; no writes outside the mapped live/repo locations; tests are hermetic
  (temp `HOME`, temp repo fixtures — never the session's real `~/.claude`); Windows-only
  branches covered by mocked-platform unit tests, honestly labeled as such.

## Implementation Phases

- **Phase 1 — psd1 parser (~1 session).** `parse_psd1` + `_die`, fixture grammar tests
  (comments, nested hashtables, arrays, `''` escapes, loud-die cases) + the REAL
  `manifest.psd1` parsed and shape-asserted. Proven done: `test_setup_py.py` parser tests green.
- **Phase 2 — mapping expansion + link primitives (~1 session).** `expand_mappings` (scopes,
  alias resolution, RootFiles/DotClaudeFiles/DotClaudeDirs, `~`/separator expansion,
  `--repos-root` remap, skip_absent flagging) + `_is_link`/`_read_link_target`/`_create_link`
  with the mocked-Windows selection tests. Proven done: expansion + primitive tests green.
- **Phase 3 — verbs + CLI (~1 session).** `bootstrap`/`check`/`repair` + argparse + exit
  codes; Linux round-trip tests (all parity-table rows); end-to-end: temp `HOME`,
  `python3 setup.py bootstrap --target User` materializes the layout and `check` exits 0.
  Proven done: full `test_setup_py.py` green including the end-to-end.
- **Phase 4 — docs + gates (~0.5 session).** Root `CLAUDE.md` Setup Commands gains the Python
  form; `user/scripts/CLAUDE.md` gains a `test_setup_py.py` note; full repo gate suite green;
  `SKIP_MCP_TEST.md`.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Real manifest parses | `parse_psd1(manifest.psd1)` | Four scopes, cognito alias chain, nested RootFiles paths present | `test_setup_py.py` |
| Loud parser death | psd1 with `$var` / here-string / expression | exit-2 / SetupError naming the line | `test_setup_py.py` |
| End-to-end self-host | temp `HOME`; `setup.py bootstrap --target User` then `check --target User` | live `~/.claude/*` are links into the clone; check exits 0 | `test_setup_py.py` e2e |
| Bootstrap parity rows | fixtures for each live/repo state combination | action labels + filesystem effects per the parity table | `test_setup_py.py` |
| Check honesty | empty temp `HOME` | MISSING rows, exit 1 | `test_setup_py.py` |
| Repair | real-file live + wrong-target link fixtures | `.bak` backup + relink; exit 0; subsequent check exits 0 | `test_setup_py.py` |
| Alias repos | alias entry with base Path present | mappings point at alias-target repo dir, live under alias entry Path | `test_setup_py.py` |
| Skip-absent repos | Repos entry Path absent | `SKIP (repo absent)`, not broken, nothing created | `test_setup_py.py` |
| `--repos-root` | override with relocated checkout | mappings resolve under `<repos-root>/<basename>` | `test_setup_py.py` |
| Windows selection logic | mocked `os.name='nt'`, symlink raises | junction fallback for dirs; loud error for files | `test_setup_py.py` (mocked platform) |
| `setup.ps1` untouched | `git diff setup.ps1` | zero changes | git |

## Open Questions

None — all stub-era open questions resolved at baseline-lock (D1 manifest format; D3 Windows
privilege handling; D4 setup.ps1 retention; D5 cloud story), each
`operator-approved 2026-07-04 — recommended option taken`. Deferred (explicitly NOT this
feature): `setup.ps1` retirement/thin-caller conversion (separate operator decision after
Windows soak, D4); porting the warn-only advisories (permanent divergence, D6); live Windows
validation of the junction fallback (Windows-only branch — mocked-platform tests here; first
Windows soak run exercises it for real).

## Research References

- `RESEARCH_SUMMARY.md` — codebase survey (Gemini research skipped per operator direction).
- `setup.ps1` — reference semantics (mapping expansion, verb behavior, advisory passes).
- `manifest.psd1` — the grammar corpus the parser is scoped to.
- `docs/bugs/windows-portability-in-probe-glue-and-field-validators/` — the recurring
  portability bug class motivating the port.
