---
kind: fixed
feature_id: powershell-tool-bypasses-bash-matched-guards
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests (test_hooks.py, 199 passed) + doc-drift-lint.py (0 drift findings); NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`powershell-tool-bypasses-bash-matched-guards` marked fixed on 2026-07-12. Root cause
(`enumerated-tool-allowlist drift`): every command-content guard hook was registered under
`matcher: "Bash"` only, and three of the five (`lazy-cycle-containment.sh`,
`long-build-ownership-guard.sh`, `build-queue-enforce.sh`) additionally early-allowed inline
whenever `tool_name != "Bash"`. The harness's PowerShell tool carries the identical
`tool_input.command` payload shape, so `git push`, `Stop-Process`, `lazy-state.py --run-end`,
long builds, and build-queue-gated ops all walked past containment/ownership/enforcement when
issued through PowerShell instead of Bash. The sibling bug (`legacy-tool-input-env-hooks-dead`)
had already widened the push/kill pair; this bug closes the remaining three guards, adds the
cross-guard registration meta-test the Root Cause named as the missing contract, and performs the
PowerShell-syntax regex audit (env-assignment prefix forms, backtick line-continuation, nested
`pwsh -Command "..."` invocation) plus a separately-observed `block-terminal-kill.sh`
false-positive fix (segment-start anchoring).

## What shipped

1. **Matcher + inline-gate widening (Phase 1).** `user/settings.json`'s shared `matcher: "Bash"`
   PreToolUse block registering `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, and
   `build-queue-enforce.sh` widened to `"Bash|PowerShell"`. Each hook's inline gate now checks
   membership in a `COMMAND_TOOL_NAMES = frozenset({"Bash", "PowerShell"})` literal. **Scope
   correction during implementation:** this was first authored as a shared `lazy_core.py` constant
   (best-effort `import lazy_core`, identical fallback literal) per the SPEC's "ideally a
   `lazy_core` constant" phrasing — but `user/scripts/lazy_core.py` is **not** in this bug's
   authorized touch list, and mid-session it was found under active concurrent edit by an
   unrelated bug (`mark-complete-partial-apply-noop-unrecoverable`) in the same working tree. The
   `lazy_core.py` edit was reverted and `COMMAND_TOOL_NAMES` is instead an identical hook-LOCAL
   literal duplicated across the three hooks (no cross-file dependency, no shared-file collision
   risk) — functionally equivalent (each hook's own gate reads the exact same set either way), just
   without the cross-hook import indirection. Added PowerShell-payload deny + allow pipe-test legs
   per hook and the cross-guard meta-test
   `test_all_command_guards_registered_with_widened_matcher` asserting all five command-content
   guards carry a matcher containing both `Bash` and `PowerShell`.
2. **PowerShell-syntax regex audit (Phase 2).** `_ENV_PREFIX` in all three widened hooks now
   recognizes `$env:NAME='value';` alongside bash `NAME=value`; the same widening extended to
   `build-queue-enforce.sh`'s `BUILD_QUEUE_BYPASS` bypass token and
   `block-work-repo-git-push.sh`'s `CLAUDE_PUSH_APPROVED` bypass token. A shared-shape
   `_normalize_ps_syntax(command)` helper (duplicated per-hook by design — each hook is a
   standalone `bash -c` invocation) collapses a PowerShell backtick line-continuation
   (`` `\r?\n ``) to a space and unwraps one level of nested `powershell(.exe)?|pwsh -Command
   "..."` by re-appending the tail after the opening quote as an additional segment. The `&`/`&&`
   call/chain-operator case needed no code change (verified by inspection: `re.search`'s
   non-anchored scan already finds a valid segment-start position regardless of single- vs.
   double-character form) — documented, not patched.
3. **`block-terminal-kill.sh` false-positive fix (Phase 2, folded in per the dispatch brief).**
   The four bare `\b(kill|exit|...)\b` word-boundary patterns — which denied an awk `'{exit}'`
   script body and a pytest `-k "...kill..."` expression (operator-observed today) — replaced
   with segment-start-anchored regexes (`{` counts as a separator only when followed by
   whitespace, which is exactly what keeps a no-space `{exit}` from matching while a real
   `{ cmd; }` bash grouping still does). All four behavioral rules and the kill-port allowance
   preserved verbatim.
4. **Docs reconciliation (Phase 3).** Root `CLAUDE.md` Hooks table rows for all five
   command-content guards updated to describe the widened matcher + regex-audit findings;
   `user/hooks/CLAUDE.md` gained two new sections ("Every command-execution tool the harness
   exposes, not just Bash" and "PowerShell-syntax regex audit") documenting the pattern for future
   hook authors.

## Symptom reproduction — evidence the bypass is closed

**Original symptom (SPEC "Verified Symptom" item 4):** a matching command via the PowerShell tool
reached no hook at all for `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, and
`build-queue-enforce.sh` — no `settings.json` registration matched, and even where one might, the
inline `tool_name != "Bash"` gate would have allowed it.

**Evidence the symptom is gone (2026-07-12):** the same class of payload, against the widened
hooks, now denies via structured JSON — proven by pipe tests driving the REAL hook scripts as
subprocesses:

```
python -m pytest user/scripts/test_hooks.py -k "powershell or containment or longbuild or bqe or termkill or push" -q
```

covering (among others) `test_containment_powershell_loop_formation_flag_denies`,
`test_longbuild_guard_powershell_denies_cargo_build_release`,
`test_bqe_powershell_denies_dotnet_build`, the six PS-syntax regex-audit tests (backtick
continuation ×2, nested `-Command` ×2, PS-style bypass token/env-prefix ×3), the four
`block-terminal-kill.sh` false-positive/true-positive tests, and the cross-guard meta-test
`test_all_command_guards_registered_with_widened_matcher`. A full-suite run confirms no
regression: `python -m pytest user/scripts/test_hooks.py -q` → **199 passed**.

## Gates run

- `python -m pytest user/scripts/test_hooks.py -q` → **199 passed** (0 failed).
- `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0
  (`doc-drift-lint: 5 checks, 0 drift findings, 2 exempted divergences` — both exemptions
  pre-existing and unrelated: the sibling bug's retired `block-work-repo-git-writes.sh` row and an
  unrelated `algobooth` manifest divergence).
- `python user/scripts/lazy-state.py --test` → all smoke tests passed (sanity check run while the
  `lazy_core.py` edit was briefly live, before it was reverted per the scope correction above; no
  state-machine logic was ever touched in this bug).

## Guards widened vs. not, and why

| Hook | Widened this bug? | Why |
|------|--------------------|-----|
| `lazy-cycle-containment.sh` | Yes (matcher + inline gate) | Command-content guard; already Skill-matched separately for its Skill-tool intercept (unaffected) |
| `long-build-ownership-guard.sh` | Yes (matcher + inline gate) | Command-content guard |
| `build-queue-enforce.sh` | Yes (matcher + inline gate) | Command-content guard |
| `block-work-repo-git-push.sh` | No (already widened by the sibling bug); bypass-token regex audited here | Command-content guard, already tool-name-agnostic |
| `block-terminal-kill.sh` | No (already widened by the sibling bug); segment-anchoring false-positive fix here | Command-content guard, already tool-name-agnostic |
| `block-noncanonical-blocker-write.sh`, `block-sentinel-write-on-stray-branch.sh` | No | `Write|Edit`-matched, not command-execution — the SPEC's D2 explicitly accepts the command-string-write blind spot (a Bash/PowerShell `Set-Content`/redirection write) as unwinnable against quoting/subexpression forms; the stray-branch sentinel already has a read-time backstop analog documented separately |
| `lazy-dispatch-guard.sh` | No | `Agent|Task`-matched; the PowerShell tool cannot dispatch agents (SPEC item 6, "Not affected") |

## Residual / deferred (documented, not blocking)

- **Sentinel command-write class (SPEC D2 option (c), accepted gap).** Command-string writes via
  `Set-Content`/`Out-File`/redirection bypass the `Write|Edit`-matched sentinel hooks regardless of
  which command tool emits them. Out of this bug's scope per the SPEC's own recommendation —
  full command-string write detection is unwinnable against quoting/subexpression forms.
- **D4 (other command-execution surfaces).** No additional non-Bash/non-PowerShell command tool
  was found active on this host during this fix. The cross-guard meta-test turns a future
  addition into a one-line `COMMAND_TOOL_NAMES` update instead of a per-hook audit.
- **`_normalize_ps_syntax` is duplicated per-hook (not a shared import).** Each of the three hooks
  is a standalone `bash -c '...'` invocation with its own embedded Python body (mirroring the
  existing repo convention — hooks do not share a Python module across the `-c` boundary; a hook
  may best-effort `import lazy_core` for hook-events appending, but `COMMAND_TOOL_NAMES` itself is
  a hook-local literal, not imported). The three copies are kept in lockstep by inspection and by
  the shared documentation section in `user/hooks/CLAUDE.md`; a future change to the regex-audit
  logic must be applied to all three.
- **`user/scripts/lazy_core.py` is untouched by this bug's final state** (see the Phase 1 scope
  correction above) — `lazy-state.py --test` was re-run once more after the revert as a final
  sanity check and remained green.

## Files touched

- `user/settings.json` — widened the `matcher: "Bash"` block to `"Bash|PowerShell"`.
- `user/hooks/lazy-cycle-containment.sh`, `user/hooks/long-build-ownership-guard.sh`,
  `user/hooks/build-queue-enforce.sh` — tool-name gate widened; `_ENV_PREFIX` PS-aware;
  `_normalize_ps_syntax` (backtick continuation + nested `-Command` unwrap) added.
- `user/hooks/block-terminal-kill.sh` — segment-start-anchored regexes (false-positive fix).
- `user/hooks/block-work-repo-git-push.sh` — bypass-token regex widened for PS syntax.
- `user/scripts/test_hooks.py` — ~30 new tests (PowerShell payload legs, regex-audit legs,
  false-positive/true-positive legs, cross-guard meta-test) + 2 pre-existing registration tests
  updated from exact-equality to matcher membership.
- `CLAUDE.md` (root) — Hooks table rows for all five command-content guards.
- `user/hooks/CLAUDE.md` — two new documentation sections.
- `docs/bugs/powershell-tool-bypasses-bash-matched-guards/PHASES.md` — this bug's implementation
  plan (new).
- `docs/bugs/powershell-tool-bypasses-bash-matched-guards/SPEC.md` — `**Status:**` flipped to
  `Fixed`.
- `docs/bugs/powershell-tool-bypasses-bash-matched-guards/FIXED.md` — this receipt (new).
