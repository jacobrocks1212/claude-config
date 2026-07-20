# Semantic-Equivalence + Scope-Tightening Review — Phase 3

**Purpose:** (a) no-policy-lost mapping for the remaining `skills=all` boilerplate
deflated in Phase 3; (b) the evidence-backed scope-tightening decision (lever 2).

**Measured reduction (Phase 3, beyond the Phase-2 floor):** 8,300 B saved across
the 20 profiles; cumulative off the original seed: 80,876 B (19.8%). All profiles
under ceiling, then re-locked via `--lock-in-profile`.

**Preserved literals (test-asserted, green):** every `@section` selector line incl.
the `env-dialect-windows … hosts=windows` attribute; terminal-stop `"Your dispatch
is exactly ONE cycle"` + `"pipeline/orchestration"`/`"lifecycle commands"` +
`"orchestrator"` + `"DENY"` + `"STOP"` (`test_project_skills.py`); `CLOUD OVERRIDE
— LOAD-BEARING`; tokens `{pipeline_phrase}`/`{item_label}`/`{item_name}`/
`{item_id}`/`{cwd}`/`{current_step}`/`{sub_skill}`/`{sub_skill_args}`/`{spec_path}`/
`{forbidden_status}`/`{receipt_name}`/`{mark_pseudo}`; zero unbound-token residue.

---

## Part A — deflated sections (trim-only; no policy dropped)

| Section (selector) | Preserved policy anchors |
|--------------------|--------------------------|
| `d7` (feature,bug / ws,cloud / all) | scope test (PRODUCT-behavior-differ), scope-class → MOST COMPLETE + `⚖ policy:` line format, NEEDS_INPUT reserved for product-class + SPEC-Locked-Decision conflict, `completeness-policy.md` path, SPIN-OFF both-directions (reverse-ref + report → PushNotification/D7 digest) |
| `env-dialect-core` (ws,cloud / all) | STDIN-not-tempfile handoff + the `python3 -c json.load(sys.stdin)` form, `--marker-status` always-exit-0 `{"present": bool, ...}` + the no-hand-roll rule, `phases-slice.py {spec_path} [--phase]` never-whole-Read |
| `env-dialect-windows` (ws / all / hosts=windows) | trailing-`\`-before-quote hazard, no `/mnt/c/...` (Git Bash not WSL) + `{cwd}`, `$HOME`-anchored `sys.path` import rule |
| `status-honesty` (ws,cloud / all) | never flip `**Status:**` to `{forbidden_status}` / never write `{receipt_name}`, `{mark_pseudo}` gate owns both, `completion-unverified` HARD-HALT, MAY flip plan-part/per-phase status, last-phase → `In-progress` not `{forbidden_status}` |
| `terminal-stop` (ws,cloud / all) | `"Your dispatch is exactly ONE cycle"`, no route-next / no second feature / no pipeline-orchestration-or-lifecycle-commands / no `/lazy*`, `DENY` in-flight assurance, orchestrator owns routing |
| `cloud-override` (cloud / all) | Agent tool FORBIDDEN + inline sub-subagent work, never another /lazy(-batch), BLOCKED.md not for the dispatch limit but for genuine cloud-RUNTIME limits `blocker_kind: cloud-limitation`, "zero dispatches EXPECTED — NOT a violation", cloud terminal `In-progress` |
| `task` (ws + cloud / all) | tokens + "Operating mode: batch" + NEEDS_INPUT-is-a-human-halt; cloud variant keeps the container-limits preamble + "state script --cloud already guaranteed safe" |

All rules survive as equivalent terse rules — prose-density reduction only.

## Part B — Scope-tightening decision (lever 2)

⚖ policy: scope-tightening selector narrowing → trim-only (no narrowing)

**Decision: NO `skills=` selector was narrowed. All sections stay `skills=all`
(trim-only).** This is the plan's pre-authorized conservative default for any
section whose exclusion safety is uncertain.

**Candidate evaluated (the one the SPEC/plan names): narrow `workstation-dispatch`
(`modes=workstation skills=all`) to exclude cycles that never fan out.**

- The only workstation cycle that provably never dispatches a sub-subagent is
  `mcp-test` (its `skill-mcp-test-common` section mandates driving the MCP tools
  INLINE — no Sonnet test subagent). `spec`, `spec-phases`, `plan-feature`,
  `write-plan`, `execute-plan`, `retro-feature` all legitimately fan out.
- **Why it is NOT provably safe to narrow:** the `@section` grammar's `skills=`
  attribute is a positive ALLOWLIST — there is no "all-except" form. Narrowing
  `workstation-dispatch` therefore means enumerating every fan-out skill by name.
  A skill added to the pipeline later without being appended to that list would
  SILENTLY lose the entire sub-subagent dispatch policy (terminal-stop restatement
  duty, single-writer, synchronous-await, wedge-resilience) — the exact "a scope
  error silently under-briefs a cycle, which is worse than a few extra KB" failure
  the SPEC's scope-tighten lever warns against.
- **Gain foregone:** excluding only the 2 workstation `mcp-test` profiles from a
  now-already-deflated section — a marginal saving against a real under-brief risk.

**Conclusion:** trim-only is the correct, evidence-backed choice; the conservative
default holds. No scope-tightening presence/absence regression test is owed
(none narrowed). The existing `test_dispatch.py::test_emit_cycle_prompt_binding_
matrix_real_template` already pins `WORKSTATION DISPATCH — LOAD-BEARING` present in
every workstation fan-out cycle (execute-plan/retro/retro-feature/spec) and absent
from every cloud cycle — the standing regression guard for this section's scope.
