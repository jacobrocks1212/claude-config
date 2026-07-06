# Implementation Phases — lazy-cycle-containment false-denies benign `lazy-batch` path references

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is the harness repo; it has no Tauri/MCP dev runtime. Verification is the in-file `test_hooks.py` harness plus the SPEC's shell reproduction against the real hook (docs/hook/tooling class per docs/features/mcp-testing/SPEC.md — structurally outside MCP reach).

## Touchpoint Audit (verified against real source — /spec-phases Step C)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/hooks/lazy-cycle-containment.sh` | yes | `_LAZY_BATCH_RE = re.compile(r"/lazy(?:-bug)?-batch(?:-cloud)?\b")` def `:186`; unanchored `.search()` trip `:392-393` inside `if is_subagent:`; `import re` present | refactor | Replace the single unanchored regex with a command-position–anchored PAIR mirroring `build-queue-enforce.sh:113-114` (`_ENV_PREFIX` / `_CMD_START`). Update the `:392` trip to test both regexes. Do NOT touch the correctly-anchored `_LAZY_SKILL_RE` (Skill branch), `_STATE_PY_RE`, or `LIFECYCLE_PATTERNS`. |
| `user/scripts/test_hooks.py` | yes | existing `test_containment_agentid_present_denies_lazy_batch_invocation` `:3447` (covers `claude -p '/lazy-batch 25'` + `/lazy-batch 10`); registration list `:5593`; helpers `_bash_preToolUse_json` / `_run_containment` / `_containment_decision` / `_SUBAGENT_AGENT_ID` / `_guard` | modify | PRESERVE the existing invocation-deny test unchanged; ADD a benign-reference-allow test + widen the runaway deny set; register every new test in the `:5593` list. |

Reuse source (read, not memory): `user/hooks/build-queue-enforce.sh:111-138` — the proven `_CMD_START` command-position anchor (`_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"`; `_CMD_START = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX`) whose stated purpose is to distinguish an invoked command from a reference-only argument.

## Validated Assumptions

- **Fix behavior is code-provable, not runtime-coupled.** The containment deny is a pure function of the command string once `agent_id` is present (SPEC Consistency: "Always — deterministic"). The SPEC's Proven Findings already validated the anchored-pair direction against the full benign set (all allow) and the full runaway set (all deny), including `/lazy-batch 5`, `cd foo && /lazy-batch`, `claude -p '/lazy-batch 25'`, and `claude --dangerously-skip-permissions -p '/lazy-bug-batch 10'`. No live runtime observation is required — the in-file `test_hooks.py` harness drives the REAL hook end-to-end.
- **MCP tool-existence audit:** no-op — claude-config declares no `.claude/skill-config/mcp-tool-catalog.md`.
- **SPEC-example capability audit:** the only constructs consumed are Python `re` module features (`re.compile`, negative lookahead `(?!/)`, `\b`) — all supported by the stdlib the hook already imports.

---

### Phase 1: Anchor the `_LAZY_BATCH_RE` recursion trip to a command-segment start (fix + regression net)

**Scope:** Replace the single unanchored `_LAZY_BATCH_RE` substring match in `lazy-cycle-containment.sh` with a command-position–anchored regex pair (direct slash-command form + nested `claude -p` spawn form), mirroring `build-queue-enforce.sh`'s `_CMD_START` approach, so a benign `lazy-batch*` file-path reference is ALLOWED while an actual nested `/lazy-batch` invocation is still DENIED. This is the whole fix — a single-file behavior change plus its regression tests. TDD: the benign-reference-allow test is RED against the current unanchored regex (benign `cat` denies today) and turns GREEN after the anchor lands; the existing invocation-deny test must stay GREEN throughout.

**Deliverables:**
- [x] In `user/hooks/lazy-cycle-containment.sh`, introduce the command-position anchor pair reused from `build-queue-enforce.sh:113-114`: `_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"` and `_CMD_START = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX` (only if not already present in this file's scope).
- [x] Replace the unanchored `_LAZY_BATCH_RE` (`:186`) with a pair:
  - Direct form: `re.compile(_CMD_START + r"/lazy(?:-bug)?-batch(?:-cloud)?\b(?!/)")` — the `(?!/)` negative lookahead makes a `.../lazy-batch/...` path segment never match.
  - Nested-spawn form: `re.compile(_CMD_START + r"claude\b[^\n;&|]*/lazy(?:-bug)?-batch(?:-cloud)?\b")` — `claude` ALSO anchored to a command-segment start so the `.claude/` path component does not false-match; preserves the existing `claude -p '/lazy-batch 25'` deny.
- [x] Update the trip at `:392-393` so the `lazy-batch-invocation` deny fires when EITHER regex matches the command (preserve the exact `_deny(CORRECTIVE, "lazy-batch-invocation")` call — the signature token is the incident cluster key and must not change).
- [x] Preserve every fail-OPEN and deny-is-JSON invariant (per `user/hooks/CLAUDE.md`); the change is regex-only — no new error paths, no exit-code denies.
- [x] Tests (in `user/scripts/test_hooks.py`): ADD `test_containment_agentid_present_allows_lazy_batch_path_reference` — a SUBAGENT payload running each of `cat user/skills/lazy-batch/SKILL.md`, `cat ~/.claude/skills/lazy-batch/SKILL.md`, `grep -rn foo repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `ls user/skills/lazy-bug-batch/`, `git add user/skills/lazy-batch/SKILL.md` MUST be allowed (asserts `_containment_decision(result) != "deny"`).
- [x] Tests: WIDEN the runaway coverage — either extend the existing `test_containment_agentid_present_denies_lazy_batch_invocation` command set or add `test_containment_agentid_present_denies_lazy_batch_invocation_extra_forms` covering `cd foo && /lazy-batch`, `/lazy-bug-batch 10`, and `claude --dangerously-skip-permissions -p '/lazy-bug-batch 10'` — all MUST still deny. Keep the ORIGINAL test asserting `claude -p '/lazy-batch 25'` and `/lazy-batch 10` deny, unchanged.
- [x] Register every new test function in the `test_hooks.py` registration list (near `:5593`, alongside the existing `test_containment_agentid_present_denies_lazy_batch_invocation` entry).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_hooks.py` runs green, INCLUDING the new benign-reference-allow test and the preserved/widened invocation-deny tests; and the SPEC Reproduction-Steps one-liner (`printf '{...,"command":"cat user/skills/lazy-batch/SKILL.md"}' | bash user/hooks/lazy-cycle-containment.sh`) now emits an ALLOW (no `permissionDecision: deny`), while the same harness fed `/lazy-batch 5` still emits the `CORRECTIVE` deny.

**Runtime Verification** *(checked by the test harness / manual hook reproduction — NOT by the implementing agent):*
- [x] <!-- verification-only --> Serving-path regression (benign reference): feeding the REAL hook a SUBAGENT payload whose `command` is `cat user/skills/lazy-batch/SKILL.md` returns an ALLOW (no `permissionDecision: deny`) — the exact false-positive from `INCIDENT.md` is gone at its reported surface. Evidence: `test_containment_agentid_present_allows_lazy_batch_path_reference` (`user/scripts/test_hooks.py:3464`) drives this exact case through the real hook and passes (`python3 user/scripts/test_hooks.py` → 130/131 passed, 1 unrelated skip, 0 failed); `VALIDATED.md` (structural MCP-skip) is on disk.
- [x] <!-- verification-only --> Serving-path regression (true positive preserved): feeding the REAL hook a SUBAGENT payload whose `command` is `/lazy-batch 5` (and `claude -p '/lazy-batch 25'`) still returns the `CORRECTIVE` `lazy-batch-invocation` deny — real recursion is still contained. Evidence: the preserved `test_containment_agentid_present_denies_lazy_batch_invocation` (`:3447`) plus the widened `test_containment_agentid_present_denies_lazy_batch_invocation_extra_forms` (`:3490`) both pass in the same green run; `SKIP_MCP_TEST.md` (`granted_by: pipeline-structural`) confirms no MCP-reachable surface exists in this repo, so this test-suite evidence is the authoritative serving-path check.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in claude-config; the hook is exercised directly by `test_hooks.py` and the SPEC's shell reproduction, which are the authoritative runtime observations here.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh` — replace unanchored `_LAZY_BATCH_RE` (`:186`) with the `_CMD_START`-anchored direct + nested-spawn pair; update the `:392-393` trip to OR the two.
- `user/scripts/test_hooks.py` — add benign-reference-allow test + widened runaway-deny coverage; register new tests near `:5593`. Do NOT edit the existing `test_containment_agentid_present_denies_lazy_batch_invocation` body except to widen its command set (its original assertions must survive).

**Testing Strategy:**
Drive the real hook through the existing `test_hooks.py` helpers (`_bash_preToolUse_json` with `agent_id=_SUBAGENT_AGENT_ID`, `_run_containment`, `_containment_decision`). RED first: the new benign-reference-allow test fails against the current unanchored regex (benign `cat` denies). GREEN after: the anchored pair allows benign references while the preserved/widened deny tests keep every runaway form denied. Full-file run `python3 user/scripts/test_hooks.py` is the gate (in-file harness, not pytest).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md/PHASES.md **Status:** and writes `FIXED.md` once this phase's runtime verification passes through the validation tail — never authored as a checkbox here.

**Integration Notes for Next Phase:** None — single-phase bug fix. The `lazy-batch-invocation` deny signature token is unchanged, so `incident-scan.py`'s existing cluster key and `INCIDENT.md` dedup continue to work. The design constraint the SPEC flags (a naive `_CMD_START` anchor on the DIRECT form alone would break the `claude -p '/lazy-batch 25'` case) is why the fix is a two-signal PAIR, not a single anchored regex.

#### Implementation Notes

- **Landed (`user/hooks/lazy-cycle-containment.sh`):** the unanchored `_LAZY_BATCH_RE` was replaced by the `_CMD_START`-anchored pair `_LAZY_BATCH_DIRECT_RE` (`_CMD_START + r"/lazy(?:-bug)?-batch(?:-cloud)?\b(?!/)"`) and `_LAZY_BATCH_NESTED_RE` (`_CMD_START + r"claude\b[^\n;&|]*/lazy(?:-bug)?-batch(?:-cloud)?\b"`), backed by the new `_ENV_PREFIX` / `_CMD_START` constants copied verbatim from `build-queue-enforce.sh`. The trip at the (now-shifted) recursion site ORs the two: `if _LAZY_BATCH_DIRECT_RE.search(command) or _LAZY_BATCH_NESTED_RE.search(command)`. The `_deny(CORRECTIVE, "lazy-batch-invocation")` call — signature token unchanged — is preserved, so `incident-scan.py`'s cluster key is intact. No new error paths / no exit-code deny; fail-OPEN + deny-is-JSON invariants preserved (`test_containment_fail_open_on_malformed_json` still green). `_LAZY_SKILL_RE`, `_STATE_PY_RE`, `LIFECYCLE_PATTERNS` untouched.
- **Tests (`user/scripts/test_hooks.py`):** added `test_containment_agentid_present_allows_lazy_batch_path_reference` (RED-confirmed against the pre-fix regex — benign `cat user/skills/lazy-batch/SKILL.md` denied with the exact incident CORRECTIVE text; GREEN after) and `test_containment_agentid_present_denies_lazy_batch_invocation_extra_forms` (chained `cd foo && /lazy-batch`, `/lazy-bug-batch 10`, headless `claude --dangerously-skip-permissions -p '/lazy-bug-batch 10'`). Both registered next to the existing entry; the original `test_containment_agentid_present_denies_lazy_batch_invocation` is unchanged and still green.
- **Gate:** `python3 user/scripts/test_hooks.py` → 130/131 passed, 1 skipped, 0 failed (the 1 skip is pre-existing and unrelated). Manual SPEC reproduction confirmed: benign `cat` → empty stdout (ALLOW); `/lazy-batch 5` → `permissionDecision: deny`.
- **Review verdict:** PASS — TDD executed INLINE (zero Agent dispatches per the cycle dispatch override), tests written and confirmed RED-for-the-right-reason before the fix, assertion-vs-intent reads clean, all deliverables covered.

---

## Red-Flag Detection (batch mode)

Ran the Step-3 red-flag checks: **clean.**
- Circular dependencies — none (single phase).
- Unclear scope — no; the SPEC traces the root cause to `lazy-cycle-containment.sh:186` with a validated fix direction.
- Integration explosion — no; two files, one behavior change.
- Testing impossible — no; the SPEC carries a concrete runnable reproduction and the fix is a pure function of the command string.
- Platform/variant expansion without a gate phase — N/A.

No `NEEDS_INPUT.md` required.
