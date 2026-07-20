# Semantic-Equivalence Review — Phase 2 (Trim-in-place: top-3 sections)

**Purpose (no-policy-lost guard):** for each of the three deflated `skills=all`
boilerplate section families in `cycle-base-prompt.md`, map every original policy
rule to its surviving terse rule. Deflation is prose-density reduction ONLY — no
policy removed. Both mode variants (workstation + cloud) of `turn-end` and
`hard-contract` were deflated for full profile coverage; `workstation-dispatch`
is workstation-only (its cloud analog `cloud-override` is Phase 3).

**Measured reduction (all 20 profiles under ceiling after edit):** 72,576 B
saved (17.8%) — 4,454 B per workstation profile, 2,391 B per cloud profile.

**Preserved verbatim (asserted by tests):** every `@section` selector line;
`WORKSTATION DISPATCH — LOAD-BEARING` (present, ws) / `INLINE OVERRIDE —
LOAD-BEARING` (absent, ws) / `CLOUD OVERRIDE — LOAD-BEARING` (cloud, untouched);
tokens `{receipt_name}`/`{work_branch}`/`{item_label}`; zero unbound-token
residue (`test_dispatch.py` binding-matrix + `test_project_skills.py` variants
green).

---

## Section: `workstation-dispatch` (modes=workstation, skills=all)

| # | Original rule | Surviving terse rule |
|---|---------------|----------------------|
| 1 | MAY use `Agent` tool (workstation-recursive-subagent-dispatch, 2026-07-09; inline-override ban lifted on workstation, cloud keeps it) | "You MAY use the `Agent` tool … the former inline-only ban is lifted on workstation; cloud keeps it" |
| 2 | FOLLOW the dispatched skill's sub-subagent model (execute-plan test/impl split, /retro research, Explore fan-outs); its contract is authoritative incl. test-first separation | "When the dispatched skill's SKILL.md defines a sub-subagent model … FOLLOW it — the skill's contract is authoritative, including its test-first agent separation" |
| 3 | Dispatch is a tool not an obligation; small mechanical batch → inline is cheaper | "Dispatch is a tool, not an obligation: for a small mechanical batch, inline Read/Edit/Write is the cheaper right choice" |
| 4 | TERMINAL STOP ban binds you AND every child (no /lazy* skills, no run-lifecycle/routing ops [enumerated], no second-feature commits); RESTATE in every child prompt | Guardrail 1 — verbatim op list retained; "RESTATE it in EVERY child prompt (the hook is the backstop, not the contract)" |
| 5 | Single-writer discipline; you are sole integrator; child claim is not evidence, verify on disk | Guardrail 2 — kept in full |
| 6 | Scope containment; delegating whole cycle = re-dispatching, forbidden; `{item_label}` scope | Guardrail 3 — kept, `{item_label}` token preserved |
| 7 | SYNCHRONOUS AWAIT; child result returns as Agent tool result; never SendMessage to parent (deadlock); never background-then-await-message; sequence dependent children (test→impl); independent may batch but still await | Guardrail 4 — condensed; deadlock cause + test→impl sequencing + independent-batch-still-await all retained |
| 8 | WEDGE RESILIENCE; wedge = empty/all-errored result (depth-2 platform limit, `No tools needed for summary`); don't wait/re-dispatch; perform INLINE with depth-1 tools; still produce deliverable; PREFER dispatch when it works | Guardrail 5 — condensed; wedge definition + inline fallback + "resilience, not avoidance" retained |

## Section: `hard-contract` (modes=workstation AND modes=cloud, skills=all)

| # | Original rule | Surviving terse rule (both variants) |
|---|---------------|--------------------------------------|
| 1 | Canonical sentinel filenames (never renamed; mis-named = invisible/loops); re-read sentinel-frontmatter.md; receipt = `{receipt_name}`; NEEDS_INPUT_FOLLOWUP_<N>.md orchestrator-only | Item 1 — kept; `{receipt_name}` + `NEEDS_INPUT_FOLLOWUP_<N>.md` preserved |
| 2 | Work-branch-only commits to `{work_branch}`; no branch creation (checkout -b/switch -c/branch); no --force; re-assert HEAD before EVERY commit/push | Item 2 — kept; `{work_branch}` + branch-creation ban + before-every-commit re-assert preserved |
| 3 | Commit policy read from disk (commit-policy.md), never memory; absent ≠ policy; default commit+push; skip only if no changes. **(cloud)** commit+push EACH batch, fetch+ff, bounded non-ff retry (~4× 2/4/8/16s), no force (`git_safe_push`) | Item 3 — kept both variants; cloud durability + `git_safe_push` no-force retained |
| 4 | Report ≤8 lines, no sha; NEEDS_INPUT disposition explicit (wrote / skip-disclosure with reason); Decision-Classification Ledger on decision-bearing cycles (empty-ledger fallback) for Step 1d.5 diff-vs-ledger; execute-plan/retro[-feature] INLINE + test-first confirmation | Item 4 — kept; ws lists `/retro-feature`, cloud lists `/retro` (+ pushed-each-batch), matching originals |

## Section: `turn-end` (modes=workstation AND modes=cloud, skills=all)

| # | Original rule | Surviving terse rule (both variants) |
|---|---------------|--------------------------------------|
| 1 | Background processes die at turn end; never end turn on a running process; block/poll auto-backgrounded gate; PREVENT auto-background by running under-cap sub-components synchronously (never aggregate); never background a long gate inside cycle subagent (`cycle-subagent-bg-gate-guard.sh` denies) | Item 1 — kept; sub-component-not-aggregate rule + guard name preserved |
| 2 | ATOMIC GATE+COMMIT (R5) chained `<gate> && git add <paths> && git commit && git push`; pathspec-scoped, never `git add -A`; `git_safe_push`, never `--force`; **(cloud)** commit+push | Item 2 — kept; chained command form + `git add -A` ban + `git_safe_push` retained |
| 3 | Concurrent-writer awareness (moved HEAD expected); conflict routing via `lazy_core.classify_conflict`; WRITE conflict non-halting (retry+continue); SEMANTIC conflict halts → class-`product` NEEDS_INPUT.md `conflict_kind: semantic`, never auto-accepted under `--park-provisional` | Kept; `classify_conflict` + WRITE/SEMANTIC split + `conflict_kind: semantic` + `--park-provisional` carve-out preserved |
| 4 | TERMINAL VERIFY GATE (executed): (i) finalize writes (tick boxes, flip status, write sentinel); (ii) run `--verify-ledger` as separate step (`--plan` only on execute-plan); (iii) reconcile until `ok:true`; certifies 4 conditions (a-d no bg job / clean tree / pushed / sentinel on disk) | Item 3 — kept; `--verify-ledger` invocation + `--plan` scoping + `ok:true` + all four (a-d) conditions preserved |

**Conclusion:** every original policy rule survives as an equivalent terse rule.
No policy dropped; every test-asserted literal + token preserved (verified green).
