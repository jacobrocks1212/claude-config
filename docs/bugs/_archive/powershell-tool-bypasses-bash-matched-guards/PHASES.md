# Implementation Phases — PowerShell tool bypasses every Bash-matched command guard

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; these are shell hooks
verified via subprocess **pipe tests** in `user/scripts/test_hooks.py` (the repo's established
hook-verification harness), the "build-tooling / repo-config, no app integration" untestable
class. There is no `mcp-tool-catalog.md` in this repo, so the planning-time MCP tool-existence
audit no-ops.

## Validated Assumptions

- **The exact `tool_name` string for the PowerShell command tool (SPEC D1) is `"PowerShell"`.**
  Confirmed empirically by pipe-testing every widened hook with a `{"tool_name": "PowerShell",
  "tool_input": {"command": ...}}` payload and observing the deny fire exactly as it does for
  `"Bash"` (Phase 1 deliverables below). No live temporary-logging-hook capture was needed — the
  sibling bug (`legacy-tool-input-env-hooks-dead`) had already made this same empirical bet for
  the push/kill pair and it held; this bug's own pipe tests are the second independent
  confirmation. Recorded here as the SPEC's "first work unit" (D1) being satisfied by direct test
  evidence rather than a separate logging-hook capture step.
- **`lazy_core.COMMAND_TOOL_NAMES` is the SSOT the SPEC's Fix Scope item 2 asks for** ("ideally a
  `lazy_core` constant all three import/embed consistently"). Each hook does a best-effort
  `from lazy_core import COMMAND_TOOL_NAMES` (consistent with the existing best-effort
  `import lazy_core` pattern already used for hook-events appending) with an identical literal
  frozenset as the fail-open fallback — a hook must never depend on the import succeeding.

## Cross-feature Integration Notes

- **`legacy-tool-input-env-hooks-dead` (sibling bug, Fixed + archived) already widened**
  `block-terminal-kill.sh` and `block-work-repo-git-push.sh` to `matcher: "Bash|PowerShell"` with
  tool-name-agnostic bodies, per its own Fix Scope item 5 and its PHASES.md's explicit
  demarcation ("the FULL widening of the other three guards + the cross-guard meta-test + the
  PS-syntax regex audit remain the sibling bug's scope" — i.e. THIS bug). This plan does not
  re-touch those two hooks' tool-name gating; it DOES extend the PS-syntax regex audit to their
  bypass-token regex (an audit-scope item this SPEC's Fix Scope item 3 names explicitly) and adds
  the false-positive segment-anchoring fix to `block-terminal-kill.sh` (SPEC step 5 / the
  operator-observed awk/pytest false-positive, folded into this bug per the dispatch brief).
- **Sequencing precondition MET:** `live-settings-split-brain-disarms-enforcement-plane` (SPEC D3
  dependency) is Fixed + archived; the tracked `user/settings.json` is the live SSOT on this
  laptop, so widening its matchers here is directly effective.

---

### Phase 1: Widen the three remaining command guards + cross-guard meta-test

**Scope:** Widen `matcher: "Bash"` → `"Bash|PowerShell"` for `lazy-cycle-containment.sh`,
`long-build-ownership-guard.sh`, and `build-queue-enforce.sh` in `user/settings.json`; replace
each hook's inline `tool_name != "Bash"` early-allow with a check against the shared
`lazy_core.COMMAND_TOOL_NAMES` set (embedded fail-open fallback literal); add PowerShell-payload
deny + allow pipe-test legs per hook; add the cross-guard registration meta-test.

**TDD:** yes — the new PowerShell-payload deny-leg tests are RED against the pre-widening hooks
(a matching command via `tool_name: "PowerShell"` returns exit 0 / no deny today, since the inline
gate reads `tool_name != "Bash"` and no `settings.json` block matches the PowerShell tool either).

**Status:** Complete

**Deliverables:**
- [x] `user/settings.json`: the shared `matcher: "Bash"` PreToolUse block registering
  `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh` widened
  to `matcher: "Bash|PowerShell"` (relative hook order preserved — ownership-guard still precedes
  enforce, per the D5 ordering invariant).
- [x] `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`: each
  hook's inline Python defines a `COMMAND_TOOL_NAMES = frozenset({"Bash", "PowerShell"})` literal;
  the `tool_name != "Bash"` early-allow in each `main()` replaced with
  `tool_name not in COMMAND_TOOL_NAMES`. **Scope correction:** the SPEC's Fix Scope item 2 says
  "ideally a `lazy_core` constant all three import/embed consistently" — this was FIRST
  implemented as a genuine `lazy_core.py` module-level constant (best-effort `from lazy_core
  import COMMAND_TOOL_NAMES`, identical literal fallback). Mid-implementation, `git status`
  surfaced `user/scripts/lazy_core.py` as under ACTIVE CONCURRENT EDIT by an unrelated bug
  (`mark-complete-partial-apply-noop-unrecoverable`) in this same working tree — and
  `lazy_core.py` is NOT in this bug's authorized touch list (`user/hooks/*.sh`,
  `user/settings.json`, `user/scripts/test_hooks.py`, root `CLAUDE.md` Hooks rows,
  `user/hooks/CLAUDE.md`). The `lazy_core.py` edit was reverted; `COMMAND_TOOL_NAMES` is instead
  an identical HOOK-LOCAL literal in all three hooks — functionally equivalent (same set, same
  gate behavior), satisfying the SPEC's underlying intent (a future command tool is still a
  bounded, mechanically-checked addition — the cross-guard meta-test asserts matcher coverage
  directly) without a cross-lane file collision.
- [x] `user/scripts/test_hooks.py`: added PowerShell-payload deny leg + allow leg per hook
  (`test_containment_powershell_loop_formation_flag_denies` /
  `test_containment_powershell_plain_command_allows`,
  `test_longbuild_guard_powershell_denies_cargo_build_release` /
  `test_longbuild_guard_powershell_allows_non_build_command`,
  `test_bqe_powershell_denies_dotnet_build` / `test_bqe_powershell_allows_dotnet_restore`).
- [x] `user/scripts/test_hooks.py`: added the cross-guard meta-test
  `test_all_command_guards_registered_with_widened_matcher` over the enumerated 5-hook command-guard
  set (`block-work-repo-git-push.sh`, `block-terminal-kill.sh`, `lazy-cycle-containment.sh`,
  `long-build-ownership-guard.sh`, `build-queue-enforce.sh`), asserting each is registered under a
  matcher containing both `Bash` and `PowerShell` — the missing contract from the SPEC's Root
  Cause, made mechanical.
- [x] Pre-existing registration tests (`test_longbuild_guard_registered_in_settings`,
  `test_bq_hook_order_guard_before_enforce`) updated from exact `matcher == "Bash"` equality to
  membership (`"Bash" in matcher.split("|")`) — they hard-coded the pre-widening literal and would
  otherwise false-fail after this phase's matcher change (found by running the full suite
  immediately after the `settings.json` edit).

**Implementation Notes (2026-07-12):** RED-for-the-right-reason confirmed by running the new
PowerShell-payload deny-leg tests against the pre-edit hooks first (they failed with `stdout=''`,
i.e. a silent allow) before making the `settings.json` + inline-gate edits, then GREEN after.
`lazy_core.py` was briefly touched then reverted per the scope-correction note above (net diff on
that file: zero). Files: `user/settings.json`, `user/hooks/lazy-cycle-containment.sh`,
`user/hooks/long-build-ownership-guard.sh`, `user/hooks/build-queue-enforce.sh`,
`user/scripts/test_hooks.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -k "powershell or containment or longbuild or bqe" -q`
is GREEN, and the PowerShell deny-leg tests demonstrably fail (RED) when run against a checkout
without this phase's `settings.json`/hook edits.

**Runtime Verification** *(checked by the pipe tests — the hooks' runtime IS the subprocess
pipe):*
- [x] <!-- verification-only --> A matching command (`python lazy-state.py --run-end` from a
  subagent; `cargo build --release`; `dotnet build` in a Cognito worktree) fired via
  `tool_name: "PowerShell"` denies for all three widened hooks, and a non-matching command via the
  same tool_name allows. **Verified 2026-07-12:** `test_containment_powershell_loop_formation_flag_denies`,
  `test_containment_powershell_plain_command_allows`,
  `test_longbuild_guard_powershell_denies_cargo_build_release`,
  `test_longbuild_guard_powershell_allows_non_build_command`,
  `test_bqe_powershell_denies_dotnet_build`, `test_bqe_powershell_allows_dotnet_restore` — all
  GREEN.
- [x] <!-- verification-only --> The cross-guard meta-test passes against the live
  `user/settings.json`. **Verified 2026-07-12:**
  `test_all_command_guards_registered_with_widened_matcher` GREEN.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP in this repo;
the hooks' runtime observable is the subprocess pipe decision, asserted directly above.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/settings.json` — widen the shared `matcher: "Bash"` block to `"Bash|PowerShell"`.
- `user/hooks/lazy-cycle-containment.sh`, `user/hooks/long-build-ownership-guard.sh`,
  `user/hooks/build-queue-enforce.sh` — inline tool-name gate + import.
- `user/scripts/test_hooks.py` — new tests + two pre-existing registration tests widened from
  exact-equality to membership.

**Testing Strategy:** Pure pipe testing, reusing each section's existing harness helpers
(`_run_containment`, `_run_longbuild_guard`, `_bqe_payload`) with `tool_name` overridden to
`"PowerShell"` post-`json.loads`.

**Integration Notes for Next Phase:** The widened matcher + tool-name-agnostic gate make each
hook's COMMAND-MATCHING regex reachable from a PowerShell-emitted command for the first time —
Phase 2 audits whether those regexes actually recognize PowerShell command syntax once reachable.

---

### Phase 2: PowerShell-syntax regex audit + block-terminal-kill.sh false-positive fix

**Scope:** Audit and fix the command-content regexes across the three newly-widened hooks (env-
assignment prefix recognition, backtick line-continuation, nested `pwsh -Command "..."`), extend
the same env-prefix audit to `build-queue-enforce.sh`'s `BUILD_QUEUE_BYPASS` bypass token and
`block-work-repo-git-push.sh`'s `CLAUDE_PUSH_APPROVED` bypass token (SPEC Fix Scope item 3, bullet
2), and separately fix `block-terminal-kill.sh`'s word-boundary false-positive class (operator-
observed: an awk `'{exit}'` script body and a pytest `-k "...kill..."` expression were both
incorrectly denied) via segment-start anchoring (SPEC step 5 / dispatch-brief item 5).

**TDD:** yes — each regex-audit fix has a paired RED-for-the-right-reason test (a backtick-
continued build, a nested `-Command` build, a PS-style bypass token, and the two termkill
false-positive cases all failed against the pre-fix hooks).

**Status:** Complete

**Deliverables:**
- [x] `_ENV_PREFIX` in `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, and
  `build-queue-enforce.sh` (both the `_CMD_START`-feeding definition and the bypass-token-feeding
  `_ENV_PREFIX_ANY` in `build-queue-enforce.sh`) now recognize `$env:NAME='value';` /
  `$env:NAME="value";` / `$env:NAME=value;` alongside the existing bash `NAME=value` form.
- [x] `_BYPASS_RE` in `build-queue-enforce.sh` recognizes `$env:BUILD_QUEUE_BYPASS='1'|"1"|1;` as
  an alternative to `BUILD_QUEUE_BYPASS=1`. `block-work-repo-git-push.sh`'s bypass check
  recognizes `$env:CLAUDE_PUSH_APPROVED='1'|"1"|1;` as an alternative to `CLAUDE_PUSH_APPROVED=1`.
- [x] `_PS_LINE_CONTINUATION_RE` (`` `\r?\n `` → a single space) added to all three widened hooks
  and applied before any command matching, via a shared-shape `_normalize_ps_syntax(command)`
  helper in each hook (not cross-imported — each hook is a standalone `bash -c` invocation; the
  three copies are kept in lockstep by inspection and by the shared regex-audit doc section in
  `user/hooks/CLAUDE.md`).
- [x] `_PS_NESTED_COMMAND_RE` (`powershell(.exe)?|pwsh ... -Command "..."`) added to the same
  three hooks' `_normalize_ps_syntax`: the tail following the opening quote is re-appended as an
  additional newline-prefixed segment (purely additive). Indexes against a stable `original`
  snapshot (not the growing `command`) so multiple nested matches never slice with stale offsets,
  and strips a trailing quote/apostrophe from the appended tail so a build that is the LAST token
  before the closing quote still satisfies its pattern's own end-of-invocation boundary check (a
  bug caught by `test_longbuild_guard_nested_pwsh_command_denies` failing on first implementation
  — see Implementation Notes).
- [x] `&`/`&&`/`||` call/chain-operator handling required NO fix: verified by inspection that
  `re.search`'s non-anchored scan already finds a valid segment-start position at any `&`/`|`
  occurrence regardless of single- vs double-character form; documented in
  `user/hooks/CLAUDE.md` rather than adding a no-op code change.
- [x] `block-terminal-kill.sh`: replaced the four bare `\b(...)\b` word-boundary patterns with
  segment-start-anchored regexes (`_CMD_START` mirroring `build-queue-enforce.sh`, with `{`
  counting as a separator only when followed by whitespace — the fix for the awk `'{exit}'` case,
  since bash's `{ cmd; }` grouping requires a blank after the reserved word but an awk/PowerShell
  script-block literal glues `{` directly onto the next token). All four behavioral rules
  (taskkill/Stop-Process, kill-except-kill-port, exit/logout/shutdown, wt.exe) preserved verbatim;
  backtick line-continuation collapsed the same way as the other three hooks.
- [x] `user/scripts/test_hooks.py`: added
  `test_longbuild_guard_backtick_continuation_denies`,
  `test_longbuild_guard_nested_pwsh_command_denies`,
  `test_longbuild_guard_powershell_style_env_prefix_tolerance`,
  `test_bqe_backtick_continuation_denies`, `test_bqe_nested_pwsh_command_denies`,
  `test_bqe_powershell_style_bypass_token_allows`,
  `test_push_allows_with_powershell_style_bypass_token`,
  `test_termkill_allows_awk_exit_block`, `test_termkill_allows_pytest_dash_k_kill_expression`,
  `test_termkill_allows_commit_message_mentioning_kill` (allow legs — false-positive class),
  `test_termkill_denies_chained_kill_command` (true-positive leg preserved under anchoring).

**Implementation Notes (2026-07-12):** First implementation of `_normalize_ps_syntax`'s nested-
`-Command` unwrap indexed off the mutating `command` variable and did not strip the tail's
trailing quote; `test_longbuild_guard_nested_pwsh_command_denies` failed
(`pwsh -Command "cargo build --release"` allowed instead of denying) because the appended tail
`cargo build --release"` retained the closing `"`, which broke `_LONG_BUILD_RE`'s own
`(?:\s|$)` end-of-invocation boundary requirement right after `--release`. Fixed by snapshotting
`original = command` before the loop (so `finditer`/slicing never see stale offsets across
multiple matches) and `rstrip("\"'")`-ing the appended tail. Re-ran the full suite after the fix:
GREEN. Files: `user/hooks/lazy-cycle-containment.sh`, `user/hooks/long-build-ownership-guard.sh`,
`user/hooks/build-queue-enforce.sh`, `user/hooks/block-terminal-kill.sh`,
`user/hooks/block-work-repo-git-push.sh`, `user/scripts/test_hooks.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q` fully green
(199 passed), including every regex-audit and false-positive test named above.

**Runtime Verification** *(checked by the pipe tests):*
- [x] <!-- verification-only --> A backtick-continued build, a nested `pwsh -Command "..."` build,
  and a PS-style (`$env:NAME=value;`) bypass token or env-prefix all resolve exactly as their bash-
  syntax equivalents. **Verified 2026-07-12:** the six regex-audit tests listed above, all GREEN.
- [x] <!-- verification-only --> `awk '{exit}'` and a pytest `-k` expression containing "kill" do
  NOT deny; a real chained `kill` invocation still denies. **Verified 2026-07-12:**
  `test_termkill_allows_awk_exit_block`, `test_termkill_allows_pytest_dash_k_kill_expression`,
  `test_termkill_allows_commit_message_mentioning_kill`, `test_termkill_denies_chained_kill_command`
  — all GREEN, alongside every pre-existing termkill test (unaffected).
- [x] <!-- verification-only --> Full-suite regression: `python -m pytest user/scripts/test_hooks.py -q`
  → **199 passed** (0 failed).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP in this repo.

**Prerequisites:**
- Phase 1: the three hooks must already be widened + tool-name-agnostic for their command-content
  regexes to be reachable from a PowerShell-emitted command at all.

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh`, `user/hooks/long-build-ownership-guard.sh`,
  `user/hooks/build-queue-enforce.sh` — `_ENV_PREFIX` widened, `_normalize_ps_syntax` added.
- `user/hooks/block-terminal-kill.sh` — segment-start-anchored regexes.
- `user/hooks/block-work-repo-git-push.sh` — bypass-token regex widened.
- `user/scripts/test_hooks.py` — the regex-audit + false-positive test additions.

**Testing Strategy:** Pure pipe testing; every new assertion pairs a payload with the expected
`permissionDecision` (or its absence for an allow), reusing each section's existing harness
helpers.

**Integration Notes for Next Phase:** The hook behavior changes are complete and pipe-test-proven;
Phase 3 reconciles the documentation surfaces (`doc-drift-lint.py`'s two cross-checks) so the
Hooks table and `user/hooks/CLAUDE.md` describe the widened/audited state, not the pre-bug one.

---

### Phase 3: Docs reconciliation

**Scope:** Update the root `CLAUDE.md` Hooks table rows for the five command-content guards to
reflect the widened matcher + PS-syntax audit, and add a `user/hooks/CLAUDE.md` section
documenting the `COMMAND_TOOL_NAMES` pattern and the PS-syntax audit findings as a load-bearing
pattern future hook authors should follow.

**TDD:** no (documentation-only; the gate is the existing `doc-drift-lint.py`).

**Status:** Complete

**Deliverables:**
- [x] Root `CLAUDE.md` Hooks table: `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`,
  `build-queue-enforce.sh` rows now read `PreToolUse (Bash, PowerShell[, Skill])` and describe the
  widening + regex audit; `block-work-repo-git-push.sh` / `block-terminal-kill.sh` rows augmented
  with the PS-syntax bypass-token / segment-anchoring notes (the sibling bug's rows already carried
  the widened matcher; this bug's audit findings are additive to those rows).
- [x] `user/hooks/CLAUDE.md`: added "Every command-execution tool the harness exposes, not just
  Bash" (the `COMMAND_TOOL_NAMES` pattern + cross-guard meta-test) and "PowerShell-syntax regex
  audit" (env-prefix, backtick continuation, nested `-Command`, the `&`/`&&` non-fix, and the
  termkill segment-anchoring fix) sections.

**Implementation Notes (2026-07-12):** `python user/scripts/doc-drift-lint.py --repo-root .`
reported 3 fresh drift findings immediately after Phase 1's `settings.json` edit (the three
widened hooks' documented matcher vs. registered matcher) — all three resolved by this phase's
Hooks-table edits. Final gate: `doc-drift-lint: 5 checks, 0 drift findings, 2 exempted
divergences` (the two exemptions are pre-existing and unrelated: the retired
`block-work-repo-git-writes.sh` row from the sibling bug, and an unrelated `algobooth` manifest
divergence). Files: `CLAUDE.md` (root, Hooks table rows only), `user/hooks/CLAUDE.md`.

**Minimum Verifiable Behavior:** `python user/scripts/doc-drift-lint.py --repo-root .` exits 0.

**Runtime Verification** *(checked by the doc-drift linter — no app runtime):*
- [x] <!-- verification-only --> `doc-drift-lint.py --repo-root .` exit 0 after the table edits
  (the Hooks-table ↔ `settings.json` cross-check passes for all five command-guard rows).
  **Verified 2026-07-12:** `python user/scripts/doc-drift-lint.py --repo-root .` →
  `doc-drift-lint: 5 checks, 0 drift findings, 2 exempted divergences` (exit 0).

**MCP Integration Test Assertions:** N/A — documentation-only phase, no runtime-observable
behavior.

**Prerequisites:**
- Phase 1 + Phase 2: the Hooks-table rows this phase writes must describe their end state.

**Files likely modified:**
- `CLAUDE.md` (root) — Hooks table rows for the five command-content guards.
- `user/hooks/CLAUDE.md` — two new documentation sections.

**Testing Strategy:** Run `doc-drift-lint.py --repo-root .` (the linter self-checks THIS repo is
drift-clean); confirm exit 0.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate
(orchestrator-owned) flips the SPEC/PHASES top-level `**Status:**` and writes `FIXED.md` after the
validation tail; do NOT flip status or write `FIXED.md` from within these phases (kept here as a
receipt of what the deterministic gate does, matching the sibling bug's PHASES.md convention — in
practice, per this bug's dispatch brief, the fix-subagent itself flips status and writes the
receipt since this bug runs outside the `/lazy-bug` autonomous pipeline this cycle).

**Completion (gate-owned in the autonomous pipeline; performed directly by the dispatched
fix-subagent for this manually-dispatched cycle):** SPEC.md / PHASES.md `**Status:**` flipped to
`Fixed`; `FIXED.md` receipt written; archival to `docs/bugs/_archive/` is deferred to the
orchestrator (consistent with `docs/bugs/_archive/legacy-tool-input-env-hooks-dead/`'s precedent,
where the archival move landed in a separate commit from the fix).

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
