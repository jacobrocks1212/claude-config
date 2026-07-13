---
kind: fixed
feature_id: legacy-tool-input-env-hooks-dead
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests (test_hooks.py) + doc-drift-lint.py; NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`legacy-tool-input-env-hooks-dead` marked fixed on 2026-07-12. Root cause: `block-terminal-kill.sh`
and `block-work-repo-git-push.sh` (both registered in `user/settings.json`'s PreToolUse Bash chain)
read `$TOOL_INPUT_command`, an environment variable the Claude Code hook interface never
populates — the payload arrives as stdin JSON. `command` was always empty, every `grep -qiE`
missed, and both hooks exit 0 on all inputs: the mobile-workflow terminal-kill protection and the
work-repo push protection had been illusory since introduction (May 2026).

## What shipped, across three commits + this close-out pass

1. **`53c3c024`** — authored the investigation SPEC + this PHASES.md plan.
2. **`030531c7`** ("revive the two dead stdin-JSON guard hooks (part 1)") — Phase 1: rewrote
   `block-terminal-kill.sh` and `block-work-repo-git-push.sh` on the stdin-JSON interface (the
   `block-noncanonical-blocker-write.sh` skeleton: `python3`→`python` resolution, inline `-c` body,
   fail-OPEN `try/except`, deny-via-JSON `permissionDecision` — never `exit 2`). Bodies read
   `tool_input.command` tool-name-agnostically, so a `Stop-Process`/`git push` fired via the
   PowerShell tool denies exactly like via Bash. `user/settings.json`'s PreToolUse matcher for
   these two hooks was widened to `Bash|PowerShell`. Added 10 pipe tests (deny/allow/malformed/
   PowerShell-payload legs + registration meta-tests) to `user/scripts/test_hooks.py`.
3. **`2f1e3eda`** ("WU-5 retire writes-variant to archived/") — Phase 2 (partial): `git mv
   user/hooks/block-work-repo-git-writes.sh archived/block-work-repo-git-writes.sh` (same defect,
   unregistered by documented decision, superseded by the now-live push hook — SPEC D1) plus the
   `archived/CLAUDE.md` retirement row.
4. **This close-out pass (2026-07-12)** — audited Phase 2 against reality and found the root
   `CLAUDE.md` Hooks table had not been reconciled (deliverable 2 of Phase 2 was still outstanding
   — the three rows for these hooks still read Phase-0 prose: plain `PreToolUse (Bash)` for the two
   revived hooks, and "NOT registered (script exists in `user/hooks/`…)" for the retired
   writes-variant, which was itself now drift since the file no longer lives there). Fixed:
   - `block-work-repo-git-push.sh` / `block-terminal-kill.sh` rows now read
     `PreToolUse (Bash, PowerShell)` and describe the stdin-JSON rewrite + deny-via-JSON fail-OPEN
     contract.
   - `block-work-repo-git-writes.sh` row now reads `**NOT registered** — retired to
     \`archived/\`` and carries an inline `<!-- doc-drift:deliberate-divergence -->` marker (the
     row necessarily fails `doc-drift-lint.py`'s on-disk check since the file no longer lives in
     `user/hooks/` by design — exempted in place per the linter's own documented D2 escape hatch,
     the same pattern used in `docs/features/doc-drift-linter/SPEC.md`'s own example row).
   - Confirmed `user/hooks/CLAUDE.md` carries no dangling reference to the retired file (grep
     clean — no edit needed there).
   - Ticked the four Phase-1 Runtime Verification rows and the one Phase-2 Runtime Verification
     row (all `<!-- verification-only -->`), citing the specific GREEN test names / gate output as
     evidence (see below). Added a "Status: Complete" line to Phase 2 (Phase 1 already had one) and
     inline Implementation Notes recording the gap found + fixed.

## Symptom reproduction — evidence the defect is gone

**Original symptom (SPEC "Verified Symptom" item 2, 2026-07-11):** piping a matching payload to
either dead hook exited 0 with no output — the deny never fired.

```
{"tool_name":"Bash","tool_input":{"command":"taskkill /F /IM node.exe"}}  -> block-terminal-kill.sh exit 0, no output
{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}     -> block-work-repo-git-push.sh exit 0, no output
```

**Evidence the symptom is gone (2026-07-12):** the same class of payload, against the rewritten
hooks, now denies via structured JSON — proven by the pipe-test suite driving the REAL hook
scripts as subprocesses (not a mock):

```
python -m pytest user/scripts/test_hooks.py -k "termkill or push" -q
-> 17 passed, 164 deselected
```

covering (among others) `test_termkill_denies_taskkill`, `test_termkill_denies_bare_kill`,
`test_termkill_denies_exit`, `test_push_denies_in_work_repo`, `test_termkill_powershell_payload_denies`,
`test_push_powershell_payload_denies`, and the registration meta-tests
`test_termkill_registered_widened_matcher` / `test_push_registered_widened_matcher` (asserting the
`Bash|PowerShell` matcher in `user/settings.json`). A live full-suite run confirms no regression:
`python -m pytest user/scripts/test_hooks.py -q` → **181 passed**.

I also observed the revived hooks live, in-session, during this close-out pass: a Bash command
containing the token `exit` (used to echo an exit code) was denied by the now-live
`block-terminal-kill.sh` mid-investigation — the fastest possible confirmation that the guard is
no longer dead code.

## Gates run

- `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0
  (`doc-drift-lint: 5 checks, 0 drift findings, 2 exempted divergences` — the two exemptions are
  this bug's deliberate writes-variant-retirement row and a pre-existing, unrelated `algobooth`
  manifest divergence out of this bug's scope).
- `python -m pytest user/scripts/test_hooks.py -k "termkill or push" -q` → 17 passed.
- `python -m pytest user/scripts/test_hooks.py -q` → 181 passed (full-file regression check).

## Files touched this close-out pass

- `CLAUDE.md` (root) — Hooks table: reconciled the three rows for `block-work-repo-git-push.sh`,
  `block-terminal-kill.sh`, `block-work-repo-git-writes.sh`.
- `docs/bugs/legacy-tool-input-env-hooks-dead/PHASES.md` — ticked Phase 1's four Runtime
  Verification rows + Phase 2's Runtime Verification row and all three Phase 2 deliverables; added
  a Phase 2 Status line + Implementation Notes.
- `docs/bugs/legacy-tool-input-env-hooks-dead/SPEC.md` — `**Status:**` flipped to `Fixed`.
- `docs/bugs/legacy-tool-input-env-hooks-dead/FIXED.md` — this receipt (new).

No hook script, `user/settings.json`, or test file needed further changes — Phase 1's rewrite and
Phase 2's file move were both already correct on disk; the only gap was documentation drift.
