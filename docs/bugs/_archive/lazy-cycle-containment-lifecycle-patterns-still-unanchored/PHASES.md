# Implementation Phases — lazy-cycle-containment.sh LIFECYCLE_PATTERNS is the last unanchored `token in command` deny check

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure hook-logic fix, verified via subprocess pipe tests in
`user/scripts/test_hooks.py`. No `mcp-tool-catalog.md` in this repo; the planning-time MCP
tool-existence audit no-ops.

## Validated Assumptions

- **The SPEC's own reconstructed route + mechanical reproduction is authoritative** — this plan
  implements the SPEC's Candidate Approach / Fix Scope verbatim (already confirmed sound by the
  investigation against a HEAD-pinned copy of the hook), not a re-derivation.
- **Concurrent-edit reconciliation confirmed clean at plan time:** the `powershell-tool-bypasses-
  bash-matched-guards` round's `COMMAND_TOOL_NAMES` / `_normalize_ps_syntax` additions had already
  landed (commit `302258cb`) and do not touch `LIFECYCLE_PATTERNS` or its deny loop — the SPEC's
  own "textual rebase, not a semantic conflict" prediction held; no reconciliation work was needed.

## Cross-feature Integration Notes

No `**Depends on:**` block. `**Related:**` names three prior rounds in the same file
(`_LAZY_BATCH_*_RE` anchoring, `_STATE_PY_INVOKE_RE` anchoring, `build-queue-enforce.sh`'s
`_CMD_START` precedent) — this phase reuses the SAME `_CMD_START` anchor already defined in
`lazy-cycle-containment.sh`, no new anchoring primitive.

---

### Phase 1: Anchor `LIFECYCLE_PATTERNS` (segment-start or task-runner-verb-invoked), preserving every existing deny

**Scope:** Replace the unanchored `for pat in LIFECYCLE_PATTERNS: if pat in command` substring scan
with `_LIFECYCLE_INVOKE_RE` — matches a bare segment-leading lifecycle token OR the token
immediately after a recognized task-runner verb (`npm run` / `pnpm run` / `yarn run`), never a
mention elsewhere in the command string (a quoted commit-message body).

**TDD:** yes. The two pinned deny tests (`test_containment_denies_lifecycle_commands`,
`test_containment_agentid_present_denies_lifecycle_no_marker`) already exist and must stay green
unmodified; the new reference-only-mention allow test was written first and confirmed RED against
the pre-fix hook via the SPEC's own mechanical reproduction (both commands denied at HEAD).

**Status:** Complete

**Deliverables:**
- [x] `_LIFECYCLE_TAIL` — an alternation of the four lifecycle literals (`re.escape`d) followed by
      a lookahead requiring whitespace/end/segment-separator (`(?=$|[\s;&|)}])`), so a longer script
      name (`dev:kill-all`) cannot partial-match.
- [x] `_LIFECYCLE_INVOKE_RE = re.compile(_CMD_START + r"(?:(?:npm|pnpm|yarn)\s+run\s+)?" + _LIFECYCLE_TAIL)`
      — defined after `_CMD_START` (reusing the same env-prefix + segment-start anchor the
      `_LAZY_BATCH_*_RE` / `_STATE_PY_INVOKE_RE` checks in this file already use).
- [x] Deny loop replaced: `if _LIFECYCLE_INVOKE_RE.search(command): _deny(CORRECTIVE, "lifecycle-command")`
      (was the unanchored `for pat in LIFECYCLE_PATTERNS: if pat in command`).
- [x] `user/scripts/test_hooks.py::test_containment_allows_lifecycle_reference_only_mention` — the
      SPEC's exact two repro commands (`git commit -m "docs: explain the npm run dev:kill teardown
      behavior in README"` and `git commit -m "note: our docs mention kill-port 3333 as an
      example"`) must ALLOW. Registered in `_TESTS`.
- [x] Existing pinned tests unmodified and still green: `test_containment_denies_lifecycle_commands`
      (`npm run dev:kill`, `npm run dev:restart`, bare `dev:kill`, bare `dev:restart`, bare
      `kill-port 3333`, bare `kill-port 1420` — all still deny) and
      `test_containment_agentid_present_denies_lifecycle_no_marker`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q -k lifecycle` is
green (4 tests: the 2 pre-existing pinned deny tests unmodified + the new allow test, run 3 total
matches under the `-k lifecycle` filter since one pinned test name doesn't contain "lifecycle" in
its collection key — see Runtime Verification for the exact count), and the new allow test is
RED-for-the-right-reason against the pre-fix unanchored substring scan (manually confirmed via the
SPEC's own mechanical reproduction table).

**Runtime Verification** *(checked by the pipe tests — the hook's runtime IS the subprocess pipe)*:
- [x] <!-- verification-only --> The two existing pinned lifecycle-deny tests stay green
  UNMODIFIED after the anchoring fix (`npm run dev:kill`/`npm run dev:restart`/bare `dev:kill`/bare
  `dev:restart`/bare `kill-port 3333`/bare `kill-port 1420` all still deny). **Verified
  2026-07-12:** `test_containment_denies_lifecycle_commands`,
  `test_containment_agentid_present_denies_lifecycle_no_marker` — GREEN.
- [x] <!-- verification-only --> A subagent commit whose message body merely mentions a lifecycle
  token as prose ALLOWS. **Verified 2026-07-12:**
  `test_containment_allows_lifecycle_reference_only_mention` — GREEN. Full suite:
  `python -m pytest user/scripts/test_hooks.py -q` → 204 passed (up from 203 after the prior bug's
  phase).

**MCP Integration Test Assertions:** N/A — pure hook-logic fix, no MCP-observable runtime surface.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh`
- `user/scripts/test_hooks.py`

**Testing Strategy:** Pure pipe testing via the existing `_run_containment` helper.
RED-for-the-right-reason already established by the SPEC's own mechanical reproduction (Mechanical
Reproduction table) before this phase; the pytest leg reproduces the same finding.

**Integration Notes for Next Phase:** None — final phase. `FIXED.md` written directly
(`provenance: operator-directed-interactive`), mirroring
`docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
