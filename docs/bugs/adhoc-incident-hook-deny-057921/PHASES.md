# Implementation Phases — lazy-cycle-containment second-feature tripwire false-denies concurrent-lane commits

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — the fix is a bash/Python PreToolUse hook with a hermetic `pytest` harness (`user/scripts/test_hooks.py`) driving crafted PreToolUse JSON + a `LAZY_CYCLE_STAGED_PATHS` env fixture; there is no Tauri/MCP-reachable surface, and claude-config has no MCP runtime at all.

## Verified Assumptions

- **`command` is in scope at the tripwire (code-provable).** `main()` binds `command` (PS-normalized + `_mask_heredoc`-applied) at `lazy-cycle-containment.sh:644-652`; the git-commit tripwire block (`re.search(r"\bgit\s+commit\b", command)`, L689) runs after that binding, so the commit invocation's own pathspec is available to filter the staged set. Verified by reading the file — no runtime observation needed.
- **`_staged_paths()` is the sole producer of the evaluated set (code-provable).** L716 `staged = _staged_paths()` feeds the L717-721 `offending` comprehension directly; no other source. The `LAZY_CYCLE_STAGED_PATHS` override (L541-543) short-circuits the `git diff --cached` read, so the test harness supplies the "whole shared index" fixture while the commit pathspec comes independently from `command`.
- **Guard safety direction (design constraint, not a runtime assumption).** A guard must never false-ALLOW a foreign path; a false-DENY is merely friction. The pathspec filter therefore NARROWS the evaluated set only when the commit is *confidently* pathspec-scoped; any parse ambiguity (unrecognized option, `-a`/`--all`, no explicit pathspec) falls back to the whole index — byte-identical to today's deny behavior. This makes the change a strict precision improvement (a re-scope), never a weakening.

## Root-cause / fix-design record (gate-weakening review — planning-time)

The SPEC's Open Question (fix-design, deferred here) asked which scoping is correct: **(A)** parse the `git commit` pathspec and evaluate only the paths that commit includes (bare/`-a` still evaluates the whole index); **(B)** intersect with paths this tool call explicitly stages; **(C)** suppress denies for a KNOWN concurrent lane.

**Chosen: Option A** (SPEC recommendation). Rationale, and the anti-overfit / gate-weakening review the SPEC required at planning time:

- **This is a RE-SCOPE, not a gate-weakening.** The genuine catch is fully preserved: a **bare** `git commit -m "…"` under a dirty shared index *does* flush a concurrent lane's staged files into one commit (the exact cross-contamination the harness's own turn-end contract warns of — "NEVER a blanket `git add -A` … can absorb a concurrent writer's staged files"), so a bare commit continues to evaluate the whole index and DENY. Only a commit that *names its own pathspec* (`git commit docs/bugs/A/SPEC.md -m …`, or `-- <paths>`) — which cannot absorb foreign files — is narrowed to the intersection and allowed.
- **Mechanical gate-weakening detectors do not fire.** Against `harness-gate.py`'s gate_weakening shapes (a `def test_*` deletion, a numeric-literal-only change on a gate line, an exemption/sanction-set membership add, a `*_BYPASS` env-var, a `permissionDecision: deny`/`refuse_*`/`exit 3` removal): NONE apply. The change adds a helper + a filter and ADDS tests; the `_deny(... "second-feature-commit")` call site is untouched.
- **Option B** collapses to A for a pathspec commit (a single `git commit` "explicitly stages" nothing) and is strictly vaguer; **Option C** needs a live concurrent-lane registry the containment hook has no access to and would *miss* the bare-commit absorption case. Both are inferior on the SPEC's own analysis.

⚖ policy: fix-scoping A/B/C for the tripwire → Option A (pathspec-aware re-scope, in-cycle)

## Affected Area (verified touchpoints)

| Planned file | Exists? | Action | Reuse / refactor directive |
|--------------|---------|--------|----------------------------|
| `user/hooks/lazy-cycle-containment.sh` | yes | refactor | Add `_commit_pathspecs(command)` + `_commit_effective_paths(command, staged)`; call the latter at L716 so `offending` (L717-721) evaluates the effective set. Reuse `_is_carve_out`/`_FEATURE_DIR_RE`/`_path_under_feature` **unchanged**. |
| `user/scripts/test_hooks.py` | yes | modify | Add red→green regression cases via the existing `_run_containment(..., staged_paths=…)` + `_bash_preToolUse_json(cmd, agent_id=…)` helpers and `_write_cycle_marker_in_dir(feature_id=…)`. |
| `user/hooks/CLAUDE.md` | yes | modify | One line on the containment row (or the "Marker-armed" section): the second-feature tripwire scopes to the commit's *effective pathspec*, not the whole index; bare/`-a` still evaluates the index. |

### Phase 1: Scope the second-feature tripwire to the commit's effective pathspec

**Scope:** Fix the shared-index cross-contamination false-deny by filtering the staged-path set to the paths the pending `git commit` will actually include, before the `offending` computation. Bare `git commit` / `git commit -a`/`--all` / any parse ambiguity → whole index unchanged (deny preserved). Add red→green hook tests and a one-line doc note.

**Deliverables:**
- [ ] `_commit_pathspecs(command)` in `user/hooks/lazy-cycle-containment.sh`: returns the explicit pathspec token list from a `git commit …` invocation, or `None` when the commit is index-wide. Returns `None` (⇒ whole-index fallback) when `-a`/`--all` is present, when no explicit pathspec follows, or on any parse ambiguity. Correctly skips argument-consuming options so their values are never mistaken for pathspecs — at minimum `-m`/`--message`, `-F`/`--file`, `-C`/`--reuse-message`, `-c`/`--reedit-message`, `--author`, `--date`, `-t`/`--template`, `--fixup`, `--squash`, `--cleanup`, `-S`/`--gpg-sign` (all in both `--opt value` and `--opt=value` forms) — and treats `--` as the explicit pathspec separator (everything after it is pathspec).
- [ ] `_commit_effective_paths(command, staged)`: returns `staged` unchanged when `_commit_pathspecs` is `None`; otherwise returns `[p for p in staged if <p matches some pathspec>]`, where a match is an exact path equality OR `p` under a pathspec directory prefix (`pathspec.rstrip('/') + '/'`), path-separator-normalized (`\\`→`/`) exactly as `_is_carve_out`/`_path_under_feature` normalize.
- [ ] Wire it in: at `lazy-cycle-containment.sh:716`, compute `staged = _commit_effective_paths(command, _staged_paths())` (or an equivalent two-line form) so the L717-721 `offending` comprehension and the `_batch_docs_writer` exemption both read the effective set. No change to `_deny(...)`, `_is_carve_out`, `COMMIT_CEILING`, or the commit-count backstop.
- [ ] Tests: see Runtime Verification / test deliverables below.

**Minimum Verifiable Behavior:** `pytest user/scripts/test_hooks.py -k containment` passes, including a NEW case that reproduces the incident — a cycle marker `feature_id=feat-A`, a `LAZY_CYCLE_STAGED_PATHS` fixture containing a foreign `docs/bugs/feat-B/FIXED.md`, and a `git commit docs/bugs/feat-A/SPEC.md -m "…"` command → decision is NOT `deny` (was `deny` pre-fix: red→green).

**Test deliverables (TDD — write RED first against the unfixed hook, then implement):**
- [ ] `test_containment_allows_pathspec_scoped_commit_with_foreign_staged_path` — marker `feat-A`; staged fixture `["docs/bugs/feat-A/SPEC.md", "docs/bugs/feat-B/FIXED.md"]`; command `git commit docs/bugs/feat-A/SPEC.md -m "fix"` → **allow** (the incident; RED before the fix because the whole-index read lands `feat-B` in `offending`).
- [ ] `test_containment_denies_bare_commit_absorbing_foreign_staged_path` — same marker + staged fixture; command `git commit -m "fix"` (no pathspec) → **still deny** (a bare commit flushes the whole index incl. `feat-B` — the genuine cross-contamination catch; proves the fix is a re-scope, not a blanket allow).
- [ ] `test_containment_denies_commit_all_flag_with_foreign_staged_path` — same; command `git commit -a -m "fix"` → **still deny** (`-a` re-stages tracked mods and commits the whole index; must not narrow).
- [ ] `test_containment_denies_pathspec_commit_that_names_foreign_path` — command `git commit docs/bugs/feat-B/FIXED.md -m "fix"` → **still deny** (a pathspec that itself includes the foreign path is a real second-feature commit; the foreign path is in the effective set).
- [ ] `test_containment_pathspec_message_containing_path_token_not_mistaken_for_pathspec` — command `git commit docs/bugs/feat-A/SPEC.md -m "closes docs/bugs/feat-B/FIXED.md"` → **allow** (the `-m` value is skipped; only the real pathspec `feat-A/SPEC.md` is evaluated) — guards the argument-skipping logic.
- [ ] Confirm the existing `test_containment_denies_second_feature_commit`, `test_containment_allows_same_feature_commit`, `test_containment_allows_carve_out_commit`, and the grouped/multilevel cases stay green (their commands are either pathspec-scoped same-feature or index-wide foreign — both must be unchanged by the re-scope). If any existing case relies on an index-wide-yet-foreign command that the new filter would narrow, treat that as a review signal, not a test edit — the deny must be preserved via the bare/`-a` fallback.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> The full hook suite is green on the target platform: `python3 -m pytest user/scripts/test_hooks.py -k containment -q` exits 0 with the five new cases collected and passing, and no previously-passing containment test regressed.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior beyond the hermetic hook-process tests; this is a PreToolUse guard exercised entirely by `pytest` driving crafted stdin JSON.

**Prerequisites:** None (single phase).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh` — add `_commit_pathspecs` + `_commit_effective_paths`; call the latter at the tripwire (L716). No deny-site or carve-out change.
- `user/scripts/test_hooks.py` — five new `test_containment_*` cases (reuse `_run_containment`/`_bash_preToolUse_json`/`_write_cycle_marker_in_dir`).
- `user/hooks/CLAUDE.md` — one-line note that the tripwire scopes to the commit's effective pathspec (bare/`-a` still index-wide).

**Testing Strategy:**
TDD against the existing hermetic hook harness. The `LAZY_CYCLE_STAGED_PATHS` env override supplies the "whole shared index" fixture (simulating a concurrent lane's staged foreign file) while the `git commit` command carried in the PreToolUse JSON supplies the pathspec — the two are independent inputs, so every case is deterministic with no real git. Red-first: the incident-repro case (`allows_pathspec_scoped_commit_with_foreign_staged_path`) must fail against the unmodified hook before the fix lands.

**Integration Notes for Next Phase:** None — single phase.

- Keep the fix confined to `lazy-cycle-containment.sh`; do NOT touch `lazy_core` or the other `_CMD_START`-anchored guards (this defect is specific to the second-feature tripwire's staged-path source, orthogonal to the shared masking helpers).
- The parser must be a flat, not-a-shell-parser string scan (same discipline as `_mask_heredoc`/`_normalize_ps_syntax` in this file). Safe-fallback bias: unsure ⇒ return `None` ⇒ whole index ⇒ deny.
