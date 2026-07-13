# Implementation Phases — block-noncanonical-blocker-write.sh denies ANY blocker-shaped basename anywhere in the tree

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure hook-logic fix, verified via subprocess pipe tests in
`user/scripts/test_hooks.py`. No `mcp-tool-catalog.md` in this repo; the planning-time MCP
tool-existence audit no-ops.

## Validated Assumptions

- **Pipeline sentinels only ever live under `docs/features/<slug>/` or `docs/bugs/<slug>/`**
  (incl. `docs/bugs/_archive/<slug>/`) — confirmed against `lazy_core.detect_noncanonical_blocker`'s
  only caller (`lazy-state.py`/`bug-state.py` Step 3), which always passes a specific item dir.
  There is no third location a legitimate `BLOCKED.md` (or its mis-named variants) is ever written.

## Cross-feature Integration Notes

No `**Depends on:**` block. This is a small, self-contained scope fix to an existing hook — no
coupling to any in-flight feature.

---

### Phase 1: Scope the deny to `docs/features/**` / `docs/bugs/**`

**Scope:** Add a path-scope check (`_SENTINEL_SCOPE_RE`, matched against the full
backslash-normalized `file_path`) alongside the existing basename-shape check
(`_is_noncanonical_blocker`) — both must hold for a deny.

**TDD:** yes. Wrote the allow-leg test first (the observed real-world false positive:
`user/skills/_components/blocked-resolution.md`), confirmed RED against the pre-fix hook (denied
purely on basename shape, no path check anywhere in `main()`), then implemented the fix green.

**Status:** Complete

**Deliverables:**
- [x] `_SENTINEL_SCOPE_RE = re.compile(r"(?:^|/)docs/(?:features|bugs)/")` + `_is_in_sentinel_scope(norm_path)`.
- [x] `main()`: `if _is_noncanonical_blocker(basename) and _is_in_sentinel_scope(norm_path):` (was
      `_is_noncanonical_blocker(basename)` alone). `norm_path` is the backslash-normalized
      `file_path`, computed once and reused for both the basename extraction and the scope check.
- [x] `import re` added to the hook's inline Python body (previously unused).
- [x] `user/scripts/test_hooks.py::test_noncanonical_denies_misnamed_blocker_under_docs_features`
      — `docs/features/x/BLOCKED_foo.md` still denies (no regression of the load-bearing in-scope
      case).
- [x] `user/scripts/test_hooks.py::test_noncanonical_allows_blocker_shaped_name_outside_docs_scope`
      — three out-of-scope blocker-shaped paths (the observed
      `user/skills/_components/blocked-resolution.md`, a bare repo-root `BLOCKED_NOTES.md`, and
      `plans/BLOCKED_2026-06-09.md`) all ALLOW. Both new tests registered in `_TESTS`.
- [x] Existing tests unmodified and still green: `test_events_noncanonical_deny_appends_event` /
      `test_events_noncanonical_allow_appends_nothing` (both already use `docs/bugs/x/...` paths,
      so they exercise the in-scope case and were unaffected by the scope-narrowing fix).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q -k noncanonical`
is green (5 tests), and the new allow-leg test is RED-for-the-right-reason against the pre-fix
hook (manually confirmed: `user/skills/_components/blocked-resolution.md` denied before the fix).

**Runtime Verification** *(checked by the pipe tests — the hook's runtime IS the subprocess pipe)*:
- [x] <!-- verification-only --> A misnamed blocker under `docs/features/<slug>/` still denies.
  **Verified 2026-07-12:** `test_noncanonical_denies_misnamed_blocker_under_docs_features` — GREEN.
- [x] <!-- verification-only --> A blocker-shaped basename outside `docs/features/**`/`docs/bugs/**`
  (incl. the observed `blocked-resolution.md` skill component) ALLOWS. **Verified 2026-07-12:**
  `test_noncanonical_allows_blocker_shaped_name_outside_docs_scope` — GREEN. Full suite:
  `python -m pytest user/scripts/test_hooks.py -q` → 206 passed (up from 204 after the prior bug's
  phase).

**MCP Integration Test Assertions:** N/A — pure hook-logic fix, no MCP-observable runtime surface.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/block-noncanonical-blocker-write.sh`
- `user/scripts/test_hooks.py`
- `docs/bugs/adhoc-blocker-write-hook-overbroad-scope/SPEC.md` (authored this session)

**Testing Strategy:** Pure pipe testing via the existing `_run_bash` + `_straybranch_payload`
helpers (the latter is a generic Write/Edit payload builder despite its stray-branch-test origin).

**Integration Notes for Next Phase:** None — final phase. `FIXED.md` written directly
(`provenance: operator-directed-interactive`), mirroring
`docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
