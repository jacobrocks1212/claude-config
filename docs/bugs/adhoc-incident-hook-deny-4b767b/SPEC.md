# lazy-cycle-containment false-denies benign `lazy-batch` path references — Investigation Spec

> The `_LAZY_BATCH_RE` recursion trip in `lazy-cycle-containment.sh` matches a `lazy-batch` token ANYWHERE in a subagent's Bash command — including benign file-path references (`cat`/`grep`/`ls`/`git add` on the `lazy-batch*` skill files). In claude-config, the very repo that houses those skill files, a cycle subagent doing legitimate lazy-pipeline investigation trips the containment deny repeatedly. The deny is a false positive; the fix is to anchor the trip to an actual command invocation, mirroring the `_CMD_START` carve-out already proven in `build-queue-enforce.sh`.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-04
**Placement:** docs/bugs/adhoc-incident-hook-deny-4b767b
**Related:** auto-captured by `incident-scan.py` (incident-auto-capture) — `ADHOC_BRIEF.md` + `INCIDENT.md` in this dir; reuse target `user/hooks/build-queue-enforce.sh` (`_CMD_START` anchor) + `user/hooks/long-build-ownership-guard.sh` (the pattern it mirrors); `user/scripts/test_hooks.py::test_containment_agentid_present_denies_lazy_batch_invocation` (existing coverage the fix must preserve)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- Batch-mode investigation (no human in the loop): symptoms PROVEN from the incident
     evidence capsule, the hook source, and an end-to-end reproduction through the real hook —
     not via interactive AskUserQuestion. -->

1. **[PROVEN]** A dispatched cycle subagent (PreToolUse payload carries `agent_id`) running a Bash command that merely *references* a `lazy-batch*` skill-file path is DENIED by `lazy-cycle-containment` with signature `lazy-batch-invocation` — confirmed by feeding the real hook `cat user/skills/lazy-batch/SKILL.md` and observing the exact `permissionDecision: deny` + `CORRECTIVE` text that appears verbatim in this dir's `INCIDENT.md` evidence lines.
2. **[PROVEN]** The incident is recurring: 8 occurrences of signal class `hook-deny`, signature `lazy-cycle-containment|lazy-batch-invocation`, in a 27-minute window (2026-07-04T18:10:15Z → 18:37:27Z) on `/home/user/claude-config` — `incident_key claude-config|hook-deny|lazy-cycle-containment|lazy-batch-invocation`, above the `incident-scan.py` `hook-deny` bar (≥3 in 24h) — recorded in `INCIDENT.md`.
3. **[PROVEN]** Every recorded evidence line is the SAME deny (identical `detail`, `signature: lazy-batch-invocation`, `repo_root: /home/user/claude-config`), consistent with one subagent repeatedly running legitimate `lazy-batch*`-path Bash commands (read/edit/grep/add) during a claude-config lazy-pipeline cycle, each denied.

## Reproduction Steps

<!-- Concrete, runnable recipe. The symptom-reproduction gate binds the fix's serving-path
     regression test to these steps. -->

1. From a claude-config checkout, simulate a dispatched cycle subagent invoking a benign Bash reference to a `lazy-batch` skill file:
   ```bash
   export LAZY_STATE_DIR="$(mktemp -d)"
   printf '{"tool_name":"Bash","agent_id":"agent-xyz","cwd":"%s","tool_input":{"command":"cat user/skills/lazy-batch/SKILL.md"}}' "$PWD" \
     | bash user/hooks/lazy-cycle-containment.sh
   ```
2. Observe the hook emits a `permissionDecision: deny` JSON whose `permissionDecisionReason` is the `CORRECTIVE` string (the deny is recorded to `hook-events.jsonl` with `signature: lazy-batch-invocation`).
3. Repeat with any of: `cat ~/.claude/skills/lazy-batch/SKILL.md`, `grep -rn foo repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `ls user/skills/lazy-bug-batch/`, `git add user/skills/lazy-batch/SKILL.md` — all deny.

**Expected:** A benign reference to a `lazy-batch*` file path is ALLOWED; only an actual nested `/lazy-batch` invocation is denied.
**Actual:** All of the above are DENIED because `_LAZY_BATCH_RE` matches the `lazy-batch` substring wherever it appears.
**Consistency:** Always (deterministic; a pure function of the command string once `agent_id` is present).

## Evidence Collected

### Source Code

Serving path, surface → source (each hop `file:line`):

- **Surface:** `INCIDENT.md` evidence lines — `{"kind":"deny","hook":"lazy-cycle-containment","signature":"lazy-batch-invocation", ...}`. These are appended by the hook's `_deny()` → `_append_hook_event("deny", signature, reason)` and clustered by `incident-scan.py` (`hook-deny` class keyed on `hook|signature`, `user/scripts/incident-scan.py:239`).
- **Trip site:** `user/hooks/lazy-cycle-containment.sh:391-393` — inside the `if is_subagent:` block:
  ```python
  # --- Recursive batch invocation (the literal runaway path). ---
  if _LAZY_BATCH_RE.search(command):
      _deny(CORRECTIVE, "lazy-batch-invocation")
  ```
- **Root (fix site, ON the path):** `user/hooks/lazy-cycle-containment.sh:186` —
  ```python
  _LAZY_BATCH_RE = re.compile(r"/lazy(?:-bug)?-batch(?:-cloud)?\b")
  ```
  `.search()` is unanchored, so the token matches inside file paths (`.../lazy-batch/SKILL.md`, `.../lazy-bug-batch/`, `.../lazy-batch-cloud/...`) and any other reference-only mention. Because a directory component `lazy-batch` is followed by `/` — a `\b` boundary — the regex fires on every skill-file path in this repo.

The **`agent_id` recursion trip is arming-free** (fires with no cycle marker present), so this false positive occurs on any dispatched cycle subagent in claude-config, independent of marker state.

The correct sibling trip in the SAME hook — the Skill-tool `/lazy*` intercept `_LAZY_SKILL_RE = re.compile(r"^/?lazy(?:-bug)?(?:-batch)?(?:-cloud)?$")` (`lazy-cycle-containment.sh`, Skill branch) — is already correctly anchored (`^...$`, an exact skill-name match). Only the Bash `_LAZY_BATCH_RE` path is unanchored.

### Runtime Evidence

End-to-end reproduction through the real hook (see Reproduction Steps) yields the byte-for-byte `CORRECTIVE` deny for a benign `cat user/skills/lazy-batch/SKILL.md`, and correctly denies `/lazy-batch 5`. The false-positive and true-positive both currently fire — the regex cannot tell them apart.

### Git History

The hook's `_LAZY_BATCH_RE` was introduced with the D4 agent_id-targeted recursion trip (`hardening-blind-to-process-friction` Phase 1). The unanchored `.search()` predates the `_CMD_START` command-position anchor that `build-queue-enforce.sh` / `long-build-ownership-guard.sh` later adopted precisely to distinguish an invoked command from a reference-only argument — the containment hook never received that same treatment.

### Related Documentation

- Root `CLAUDE.md` Hooks table documents `build-queue-enforce.sh` denying "only when a build token *begins a command segment* — a reference-only mention like `cat …/build-filtered.ps1` is allowed". This is the exact carve-out `lazy-cycle-containment.sh`'s `lazy-batch` trip is missing.
- `user/hooks/CLAUDE.md` — fail-OPEN + deny-is-JSON invariants (the fix must preserve both) and the "stable signature token" contract for deny sites.

## Theories

### Theory 1: Unanchored regex false-matches path references (root cause)
- **Hypothesis:** `_LAZY_BATCH_RE.search(command)` matches the `lazy-batch` substring inside benign file-path arguments, so a cycle subagent's legitimate read/edit of a `lazy-batch*` skill file is denied as a "recursive batch invocation."
- **Supporting evidence:** Reproduced end-to-end (benign `cat` denies with the exact INCIDENT.md text); regex-level confirmation that `cat`/`grep`/`ls`/`git add` on `lazy-batch*` paths all match; the 8 evidence lines are identical denies in the repo that houses those skill files.
- **Contradicting evidence:** None found. (An actual runaway would also be denied, but a runaway would not recur 8× as a subagent quietly retries benign file ops.)
- **Status:** Confirmed.

## Proven Findings

- **Root cause (traced, fix-site-on-path):** `user/hooks/lazy-cycle-containment.sh:186` `_LAZY_BATCH_RE` is an unanchored substring match; the `.search()` at `:392` fires on any `lazy-batch*` path reference by a cycle subagent, producing the `lazy-batch-invocation` deny at `:393`.
- **This is a false positive, not a real containment event.** The deny is the hook mis-firing; the subagent's command was benign. No runaway occurred.
- **Recommended fix direction (validated, NOT yet implemented):** replace the single unanchored regex with a command-position–anchored pair, mirroring `build-queue-enforce.sh`'s `_CMD_START` approach:
  - `_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"`
  - `_CMD_START  = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX`
  - Direct form: `re.compile(_CMD_START + r"/lazy(?:-bug)?-batch(?:-cloud)?\b(?!/)")` — a slash-command that *begins a command segment* (start or after `;&|({`/newline, optional env prefix), with a negative lookahead `(?!/)` so a `.../lazy-batch/...` path segment never matches.
  - Nested-spawn form: `re.compile(_CMD_START + r"claude\b[^\n;&|]*/lazy(?:-bug)?-batch(?:-cloud)?\b")` — a `claude -p '/lazy-batch …'` headless runaway, with `claude` ALSO anchored to a command-segment start so the `.claude/` path component does not false-match.
  - **Design constraint the fix MUST honor:** the existing test `test_hooks.py::test_containment_agentid_present_denies_lazy_batch_invocation` covers `claude -p '/lazy-batch 25'` (token inside a quoted prompt) and `/lazy-batch 10`. A naive `_CMD_START` anchor on the DIRECT form alone would break the `claude -p` case — hence the two-signal pair. This direction was validated against the full benign set (all allow) and the full runaway set (all deny), including `/lazy-batch 5`, `cd foo && /lazy-batch`, `claude -p '/lazy-batch 25'`, and `claude --dangerously-skip-permissions -p '/lazy-bug-batch 10'`.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Containment hook (Bash recursion trip) | `user/hooks/lazy-cycle-containment.sh` (`_LAZY_BATCH_RE` def `:186`; trip `:391-393`) | False-denies benign `lazy-batch*` path references by cycle subagents |
| Hook test suite | `user/scripts/test_hooks.py` (`test_containment_agentid_present_denies_lazy_batch_invocation`) | Must keep denying real invocations; add benign-reference-allow cases for the regression net |

## Open Questions

- **Scope of the nested-spawn form.** The current `_LAZY_BATCH_RE` requires a leading `/` on the token. Should the fix also catch a slash-less `claude -p 'lazy-batch …'`? The existing test only exercises the `/`-prefixed form; the fix stage should decide whether to widen (out of scope for this investigation — no evidence of a slash-less runaway).
- **Parity with the settings-registration.** `lazy-cycle-containment.sh` is wired once in `user/settings.json`; no coupled-hook mirror is owed. The fix is a single-file change plus its test.
