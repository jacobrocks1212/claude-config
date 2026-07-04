---
kind: implementation-plan
feature_id: cross-platform-setup
status: Complete
created: 2026-07-04
complexity: medium
phases: [1, 2, 3, 4]
---

> **Plan** — generated inline on 2026-07-04.
> To execute: `/execute-plan docs/features/cross-platform-setup/plans/all-phases-cross-platform-setup-part-1.md`
> Single self-contained part covering all 4 phases.

# Implementation Plan — cross-platform-setup (Phases 1–4)

**PHASES.md:** `docs/features/cross-platform-setup/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/cross-platform-setup/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
cd user/scripts
python3 -m pytest test_setup_py.py -q                # feature suite (this plan's new file)
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py \
  test_project_skills.py -q                          # full pytest gates (final acceptance)
python3 test_toolify_miner.py
python3 lazy-state.py --test && python3 bug-state.py --test && python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <repo-root>
python3 lint-skills.py --skills-dir <repo-root>/user/skills --repos-dir <repo-root>/repos
```

## Key design contract (read before WU-1.1)

- ONE file: repo-root `setup.py`, stdlib-only, importing NOTHING from `user/scripts/` (must run
  on a bare clone). Tests load it via `importlib.util.spec_from_file_location('cps_setup', …)`.
- Parser is scoped to the manifest's real grammar (SPEC D1-A) and `_die()`s (SetupError, line
  number) on anything else — never silent tolerance.
- Verbs mirror `setup.ps1` per the SPEC's normative parity table; deliberate divergences are
  ONLY: check exit code hardened (0 iff broken==0), Repos skip_absent (D5), advisories not
  ported (D6), `add-repo` not ported (D2).
- All tests hermetic: temp `HOME`/`USERPROFILE`, temp repo fixtures; NEVER the session's real
  `~/.claude` (LANE rule 6). Repo side of the e2e uses the worktree read-only.
- `setup.ps1` + `manifest.psd1` byte-untouched (`git diff` empty at every commit).

---

## Phase 1 — psd1 parser

- [x] WU-1.1 — Failing tests: grammar fixtures (nested hashtables, newline+comma arrays, `''`
  escape, double-quoted string, full-line + trailing comments, quoted keys) + loud-die cases
  (`$var`, here-string, expression, unterminated string, garbage token → SetupError w/ line) +
  real-manifest shape assertions. Run → fail (module lacks `parse_psd1`).
- [x] WU-1.2 — Implement `SetupError`/`_die` + tokenizer + recursive-descent `parse_psd1` in
  new `setup.py`; re-run → green.

## Phase 2 — expansion + link primitives

- [x] WU-2.1 — Failing tests: `expand_live_path` home/separator handling; `expand_mappings`
  per-scope fixtures, alias resolution (own live base, shared repo side), optional-key
  tolerance, sorted Repos order, `repos_root` remap, skip_absent flag, target filter;
  real-manifest expansion spot checks (11 User mappings, section labels).
- [x] WU-2.2 — Implement `Mapping`, `expand_live_path`, `expand_mappings`; green.
- [x] WU-2.3 — Failing tests: `_is_link`/`_read_link_target`/`_resolve_target` on real Linux
  symlinks; mocked-nt selection (`symlink ok`, `OSError+dir → _create_junction`,
  `OSError+file → SetupError` naming Developer Mode); junction-probe `_is_link` on mocked nt.
- [x] WU-2.4 — Implement link primitives (patchable `_create_junction` seam); green.

## Phase 3 — verbs + CLI + e2e

- [x] WU-3.1 — Failing tests: bootstrap parity rows (SKIP / RELINK / COPYLINK / MOVE / WARN /
  LINK-recovery / NONE / SKIP-repo-absent) incl. filesystem effects + summary line.
- [x] WU-3.2 — Implement `cmd_bootstrap`; green.
- [x] WU-3.3 — Failing tests: check verdicts (OK/MISSING/ABSENT/REAL/WRONG), exit 0/1
  contract, empty-HOME honesty, skip_absent never-broken.
- [x] WU-3.4 — Implement `cmd_check`; green.
- [x] WU-3.5 — Failing tests: repair rows (skip-correct, skip-repo-missing, relink-wrong,
  BACKUP+REPAIR real file, REPAIR missing live) + repair→check round-trip.
- [x] WU-3.6 — Implement `cmd_repair`; green.
- [x] WU-3.7 — Failing tests: CLI (`main(argv)` header/labels/exit codes; SetupError → exit 2;
  subprocess smoke) + END-TO-END: temp HOME, `python3 setup.py bootstrap --target User` against
  the real worktree → links materialized; `check --target User` exit 0; write-through proof.
- [x] WU-3.8 — Implement argparse `main` + wire verbs; green. Full feature suite green.

## Phase 4 — docs + gates

- [x] WU-4.1 — Root `CLAUDE.md` Setup Commands: add `python3 setup.py` forms (scoped edit).
  `user/scripts/CLAUDE.md`: `test_setup_py.py` note.
- [x] WU-4.2 — FULL gate suite green (all pytest suites + `--test` harnesses + parity audit +
  lint-skills; only the two sanctioned skips). `git diff setup.ps1 manifest.psd1` empty.
- [x] WU-4.3 — `SKIP_MCP_TEST.md` with suites/counts + `validated_commit`; PHASES.md +
  plan finalized (checkboxes ticked with evidence, statuses per protocol).

**Implementation Notes (2026-07-04 — all phases complete):**
- Parser: single-pass tokenizer (string/comment aware) + recursive descent; `;` accepted as a
  separator alongside newline/comma; trailing comments stripped outside strings; double-quoted
  strings accepted but die on `$`/backtick (no interpolation in a data file); bare-word values
  refused (this manifest only uses quoted strings/arrays/hashtables) — loud over guessing.
- Expansion refinement vs `setup.ps1`: skip_absent is flagged at expansion time (Repos base
  `Path` dir absent) so all three verbs render `SKIP … (repo absent: …)` uniformly — the D5
  divergence. Dangling-link + repo-missing (a case setup.ps1 would throw on) degrades to
  removing the dead link + NONE.
- Windows selection logic behind patchable seams (`_WINDOWS`, `_symlink`, `_readlink`,
  `_create_junction`) — covered by 5 mocked-platform tests; exercised for real on Windows only.
- CLI: `--repos-root` validated to exist (SetupError, exit 2) so a typo is loud rather than
  silently skip-absent-ing every repo; `check` exits 0 iff broken==0 (documented hardening —
  setup.ps1 never propagated its bool).
- e2e runs `setup.py` as a subprocess with temp HOME/USERPROFILE and proves write-through by
  realpath identity + content equality (no writes into the worktree from tests).
- Root `.gitignore` gained `__pycache__/` (the test suite imports the repo-root script, which
  writes bytecode there — new artifact introduced by this feature).
