# Implementation Phases — Push-hook bypass token `^`-anchored (false-blocks composed push)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a stdlib hook unit test in claude-config (bash hook exercised via `test_hooks.py`'s subprocess harness); no Tauri/MCP HTTP surface exists in this repo. Per `docs/features/mcp-testing/SPEC.md`, harness/tooling changes with no app-integration surface are structurally outside MCP reach.

## Touchpoint Audit (verified inline — dispatch unnecessary for a 2-file bug)

`verified: inline (dispatch unavailable — 2-file mechanical scope)`

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/hooks/block-work-repo-git-push.sh` | yes | `_BYPASS_RE` (lines 50–52, unanchored `(?:\bCLAUDE_PUSH_APPROVED=1\b\|$env:…)`), `main()` uses `_BYPASS_RE.search(command)` (line 82) | **no change (already fixed)** | The SPEC's load-bearing fix (relax `^`-anchored `re.match` → unanchored `.search`) **already landed** at commit `365df0b9` ("fix(hooks): recognize push bypass token anywhere in command", 2026-07-14). Do NOT re-edit the hook. |
| `user/scripts/test_hooks.py` | yes | `_PUSH_HOOK_SH`, `_init_email_repo()`, `_hook_payload(command, cwd=)`, `_run_bash()`, `_hook_decision()` (None ⇒ allow), `_TESTS` registration list; existing push block `test_push_denies_in_work_repo` … `test_push_allows_with_powershell_style_bypass_token` | **add test** | Add one composed-approved-push allow-case. Reuse the exact harness pattern of `test_push_allows_with_bypass_token`; only the command string changes to a `cd … && CLAUDE_PUSH_APPROVED=1 git push` form. Register the new test in `_TESTS`. |

**Drift note (mechanical, corrected in-plan — not a premise falsification).** The SPEC (written 2026-07-13) scoped two deliverables: (1) the hook regex fix and (2) regression coverage. Between SPEC authorship and this plan, deliverable (1) landed independently at commit `365df0b9`. The remaining, un-done scope is deliverable (2) only — the composed-push regression test. The SPEC's root cause and fix design remain accurate; only the sequencing changed (the fix shipped early, its regression test did not follow it). No test in the current push block exercises a composed/prefixed approved push, so the anchor regression is still uncovered — exactly the gap the SPEC's scope item 2 names.

### Phase 1: Regression coverage for composed approved pushes

**Scope:** Add a `test_hooks.py` case asserting that a composed approved push — `cd "…" && CLAUDE_PUSH_APPROVED=1 git push origin main` — is ALLOWED (not denied) in a work-email repo. This locks in the already-landed hook fix and pins against any future re-anchoring of the bypass detector. No production hook code changes in this phase (the hook fix is already on `main`).

**Deliverables:**
- [ ] Add `test_push_allows_with_bypass_token_after_cd_prefix` to `user/scripts/test_hooks.py`, adjacent to the existing push-hook block. It builds a work-email repo via `_init_email_repo(td, "jacob@cognitoforms.com")`, fires `_run_bash(_PUSH_HOOK_SH, _hook_payload('cd "<repo>" && CLAUDE_PUSH_APPROVED=1 git push origin main', cwd=str(repo)), _base_env(state_dir))`, and asserts `_hook_decision(result) is None` (allow). The composed form fails against the pre-`365df0b9` `^`-anchored `re.match` and passes against the current unanchored `_BYPASS_RE.search`.
- [ ] Register the new test in the `_TESTS` list so the runner executes it.
- [ ] Tests: the new case is the test; verify the whole `test_hooks.py` suite is green (`python user/scripts/test_hooks.py`).

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` runs the new `test_push_allows_with_bypass_token_after_cd_prefix` and the case reports PASS (composed approved push → allow), with the full suite still green.

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; this is a bash-hook unit test verified by the `test_hooks.py` subprocess harness.

**Prerequisites:** None. (The load-bearing hook fix already landed at commit `365df0b9`; this phase only adds its missing regression test.)

**Files likely modified:**
- `user/scripts/test_hooks.py` — add the composed-push allow-case + its `_TESTS` registration entry.

**Testing Strategy:**
Run `python user/scripts/test_hooks.py` and confirm the new case passes and no existing case regresses. The test is a genuine RED-against-the-old-anchor case: it would have FAILED (deny) under the pre-`365df0b9` `re.match(r"^CLAUDE_PUSH_APPROVED=1\b", …)` and PASSES (allow) under the current `_BYPASS_RE.search`. Optional sanity: a local git-stash of the hook fix would flip the new test red, confirming it guards the intended behavior (do not commit that experiment).

**Integration Notes for Next Phase:**
- Single-phase bug — no next phase.
- Do NOT touch `user/hooks/block-work-repo-git-push.sh`: its fix is on `main` (commit `365df0b9`). Re-editing it is out of scope and would be redundant.
- `user/skills/push/SKILL.md` stays unchanged (SPEC "Out of scope, decided"): the bare token-led form remains the prescribed caller shape; the hook fix makes composed callers safe without relying on caller discipline.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes FIXED.md once this phase's regression test is green and the validation tail passes. Do NOT author a Status-flip or receipt-write checkbox.

## Implementation Notes

- **Already-landed fix (reverse reference):** the SPEC's load-bearing deliverable — relax the `^`-anchored bypass detector to an unanchored token match — shipped independently at commit `365df0b9` before this plan was authored. The current hook (`user/hooks/block-work-repo-git-push.sh:50–52,82`) uses `_BYPASS_RE.search(command)` with an unanchored pattern; the hook's contract comment (line ~46) now documents the compound `cd <repo> && CLAUDE_PUSH_APPROVED=1 git push` case explicitly. This PHASES.md therefore plans only the remaining regression coverage (SPEC scope item 2).
- **Symptom-reproduction gate (SEAM B) mapping:** the SPEC's `## Reproduction Steps` composed-push deny is reproduced-then-gone by the new allow-case test — the regression test IS the serving-path reproduction (the hook is the serving path; the composed command is the original symptom's exact surface), satisfying the bug-completion evidence ladder.
