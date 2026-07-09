# Lean Plan Files — Lane-Contract Single-Sourcing + Compact Reorientation (`/write-plan-cognito` v2, `/execute-plan`)

> Remove the ~16KB of verbatim lane policy that `/write-plan-cognito` re-emitted into every
> generated Cognito plan by single-sourcing it into a repo-scoped lane contract; make generated
> plans pointer-based; drop `/execute-plan`'s redundant 13.8KB `!cat` injection of
> `subagent-review.md`; and harden post-compaction recovery with a run-marker + SessionStart
> hook so a pointer-based plan re-anchors from disk instead of a lossy summary.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:**
- `plan-skills-redesign` — kind: hard — Complete. This feature is the follow-through: the 2026-06-29
  redesign single-sourced the GENERIC execution policy into
  `~/.claude/skills/_components/execution-contract.md`, but explicitly instructed
  `/write-plan-cognito` to keep re-emitting its lane OVERRIDES verbatim into every plan. This
  feature applies the same proven pattern one level down.

---

## Problem (measured 2026-07-09)

Despite `plan-skills-redesign`, `/write-plan-cognito` plans remained ~25–47KB, and `/execute-plan`
sessions hit ~150K resident context before the first subagent dispatch (Cognito Forms — no 1M
models in use). Byte-weighing the newest plan
(`cog-docs/docs/features/57077-cognito-pay-account-deletion/plans/phase-6-pr-16960-review-findings.md`,
47,327 B):

| Region | Bytes | Nature |
|--------|-------|--------|
| Policy header (Execution Policy pointer + lane EXECUTION MODEL + lane Component Reference Card + lane MANDATORY RULES) | 6,389 | **Identical template meta across every Cognito plan** |
| Work content (Verified Touchpoint Audit, Execution Schedule, lanes, batch structure) | 30,135 | Genuine per-plan content (load-bearing — untouched) |
| Protocol tail (lane Execution Protocol L.0–L.7, Blocking Issue Protocol, Completion, Work Log) | 9,525 | **Identical template meta across every Cognito plan** |

**15,914 B (~33.6%, ~4K tokens) of every generated lane plan was policy the skill's own template
marked "write verbatim"** — the same dual-sourced-policy defect `plan-skills-redesign` fixed for
the generic tier, one level down. Separately, `/execute-plan` inlined
`subagent-review.md` (13,785 B, ~3.4K tokens) via `!cat` at every invocation even though its own
Execution Contract section and Component Loading protocol already mandate `Read`-ing that
component from disk per batch — pure dual-sourcing plus a per-session token tax.

The original rationale for inlining policy into plans — surviving context compaction — is served
by the pointer mechanism (compaction summary → re-read plan → pointer block → `Read` contracts
from disk), proven in production since the generic contract shipped in June. The residual
compaction risk (the orchestrator acting *before* re-reading anything, e.g. inline-editing a
source file) is closed by a hook, not by re-inlining meta.

## Locked Decisions

1. **LD1 — Single-source the lane policy into a repo-scoped contract file**
   (`repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md`,
   symlinked into every Cognito worktree at
   `.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md`). It carries the lane
   EXECUTION MODEL, lane Component Reference Card, lane MANDATORY RULES, the full lane Execution
   Protocol (Steps L.0–L.7 + typegen seam + tiered gates + Part Completion incl. the SEAM B
   symptom-reproduction gate), Blocking Issue Protocol, Completion report, and Work Log step —
   lifted verbatim from the old per-plan template. Same consumption pattern as the generic
   contract; referenced repo-relative exactly like the already-working `lane-agent-briefing.md`.
2. **LD2 — Plans are pointer-based (`cognito-lanes-v2`).** A generated plan carries: header, a
   ~1.2KB pointer block naming BOTH contracts with explicit precedence (plan-specific notes →
   lane contract → generic contract), References, Execution Schedule, per-phase lanes + batch
   structure, the Verified Touchpoint Audit, and a new `## Plan-specific execution notes` section
   that is the ONLY home for per-plan policy deltas (typegen seam status, single-writer files,
   exact Tier 2 gate commands, extra blocking triggers, component overrides). NO policy section
   is ever re-emitted.
3. **LD3 — Contract versioning.** The lane contract carries `**Contract version:**
   cognito-lanes-v2` and the plan's pointer block stamps the version it was authored against —
   single-sourcing means old plans execute under today's contract (desirable for harness
   self-improvement), and the stamp keeps that auditable.
4. **LD4 — Remove `/execute-plan`'s `!cat subagent-review.md` injection**, replacing it with a
   read-from-disk pointer in the Batch Review Gate section. The gate's blocking semantics are
   unchanged; only the delivery mechanism moved to the already-mandated per-batch disk read.
   Planner-side `!cat`s in `/write-plan-cognito` (cog-doc-track-open, dep-block-schema,
   touchpoint-audit-gate, plan-file-output) are consumed at planning time and stay.
5. **LD5 — Compact reorientation is a marker + hook, NOT re-inlined meta.** `/execute-plan`
   Step 1d writes `~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json` (`{"plan", "repo_root"}`,
   forward-slash paths) once the status/saturation gates allow execution, and clears it at
   Step 4 completion and on BLOCKED/NEEDS_INPUT halts. A new SessionStart hook
   (`user/hooks/execute-plan-compact-reorient.sh`, matcher `compact`) injects a ~10-line
   reorientation block (active plan path + TaskList-first + re-read plan and both contracts +
   orchestrator-not-implementer reminder). The hook deliberately does NOT inject component
   content — that would re-add at every compaction the tokens this feature removed. Add-context
   only, fail-OPEN on every error path, per-repo keyed, self-heals a stale marker whose plan is
   already `status: Complete`.

## KPI Declaration

Drafted row (full schema, not yet registered in `docs/kpi/registry.json` — the signal has no
automated collector on the state-script path; measurement is a byte-count over generated plan
files in cog-docs, cheap to re-run by hand or in a retro):

```json
{
  "id": "cognito-plan-inlined-policy-bytes",
  "system": "write-plan-cognito",
  "title": "Inlined execution-policy bytes per generated Cognito lane plan",
  "friction": "Every generated plan re-emitted ~16KB of verbatim lane policy, paid as ~4K resident tokens by every /execute-plan session (and every re-read of the plan after compaction), crowding an already ~150K pre-dispatch context.",
  "signal": { "source": "session-log-mining", "selector": "predispatch-plan-read-bytes" },
  "unit": "bytes",
  "direction": "down-is-good",
  "baseline": { "value": 15914, "captured_at": "2026-07-09", "window": "1d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "cognito-forms",
  "notes": "Baseline: byte-weighing the single newest plan (phase-6-pr-16960, 2026-07-09) — the manual measurement; the session-log-mining source/selector (registered in kpi-scorecard.py by the sibling context-diet features) is the corpus-level channel via attribute_predispatch.py, honest NO-DATA in the scorecard until a collector is wired. Target after cognito-lanes-v2: ~1.2KB pointer block + plan-specific notes (>=90% reduction of the meta regions). Secondary win: /execute-plan sheds the 13,785 B subagent-review.md !cat injection. Verify on the next 2-3 generated plans; a plan re-emitting any policy section is a template-compliance regression against LD2."
}
```

## What Shipped

| File | Change |
|------|--------|
| `repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md` | **NEW** — the single-sourced lane contract (238 lines), version `cognito-lanes-v2` |
| `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` | Step 3 rewritten: all "write verbatim" policy emissions deleted (413 → 275 lines); pointer-block template + `## Plan-specific execution notes` template added; plan version bumped to `cognito-lanes-v2`; "self-contained" redefined as pointer-based |
| `user/skills/execute-plan/SKILL.md` | New Step 1d (marker write) + marker clears at Step 4 completion and Blocking/NEEDS_INPUT halts; Execution Contract section now instructs reading plan-named repo contracts with the precedence chain and accepts pointer-only plans in Step 1b validation; `!cat subagent-review.md` injection replaced with a read-from-disk pointer; Compaction Recovery Protocol references the hook |
| `user/hooks/execute-plan-compact-reorient.sh` | **NEW** — SessionStart(compact) reorientation hook (fail-OPEN, add-context-only, jq-with-grep-fallback, stale-marker self-heal) |
| `user/settings.json` | Hook registered first in the existing SessionStart `compact` matcher group |
| `CLAUDE.md` (repo root) | Hooks table row added for `execute-plan-compact-reorient.sh` |

Untouched by design: the generic `/write-plan` (already pointer-based since
`plan-skills-redesign`), the generic `execution-contract.md`, `lane-agent-briefing.md`, the
Verified Touchpoint Audit content (the dense, load-bearing part of every plan), and all
lazy-parity coupled pairs (none of the edited files participate in
`user/scripts/lazy-parity-manifest.json`).

## Validation Criteria — evidence

- [x] `python user/scripts/project-skills.py` — clean (89 skills, 96 components across all
      projections; no unresolved/circular `!cat`).
- [x] `python user/scripts/lint-skills.py` — `OK — no broken or embedded !cat patterns found`;
      planner resolution intact (`write-plan-cognito` resolves; no execute-plan fork).
- [x] `python user/scripts/doc-drift-lint.py --repo-root .` — exit 0 (4 checks, 0 drift findings;
      the new Hooks-table row ↔ settings.json registration reconcile).
- [x] `user/settings.json` parses as valid JSON; hook passes `bash -n`.
- [x] Hook behavioral test (4 paths, sandbox repo + marker): (1) marker + `In-progress` plan →
      emits `hookSpecificOutput.additionalContext` with plan path + re-read sequence; (2) marker +
      `Complete` plan → silent, marker auto-removed; (3) no marker → silent exit 0; (4) garbage
      stdin → silent exit 0. Marker key derivation confirmed format-stable (`git rev-parse
      --show-toplevel` prints `C:/...` identically from both the skill-side shell and the
      hook-side `git -C <backslash-cwd>`).
- [ ] Field verification (deferred to next real Cognito planning cycle): the next
      `/write-plan-cognito` output contains the pointer block + plan-specific notes and NO policy
      sections; the next `/execute-plan` run reads both contracts and executes normally. If the
      executor stumbles on a pointer-only plan, the fallback is trivial — the contract file is on
      disk in every worktree.

## Expected Impact

- **Per generated plan:** ~15.9KB → ~1.5–2.5KB of policy/pointer content (≥85% of the meta
  removed; ~3.5–4K tokens saved per plan read, paid multiple times per session via source-reread
  and compaction re-reads).
- **Per `/execute-plan` invocation:** −13,785 B (~3.4K tokens) from the removed injection
  (projected executor skill now 44,675 B vs ~58.5K before).
- **Honesty note:** these are ~7K tokens against a ~150K pre-dispatch plateau — a real but
  partial win. The next levers, if the plateau needs to move materially, are SPEC-excerpt
  scoping per plan part and a mining pass over the remaining startup reads (out of scope here).

## Out of Scope / Follow-ups

- Registering the drafted KPI row in `docs/kpi/registry.json` with an automated collector.
- Retiring the legacy inline `~/.claude-personal/plans`-scanning compact hook in
  `user/settings.json` (left as-is; it serves a different plan directory).
- Applying a `contract_version` stamp to the GENERIC `execution-contract.md` / `/write-plan`
  pointer block (only the new lane contract is versioned).
- Trimming the generic `/write-plan` template further (its plans were already pointer-based; its
  remaining per-plan sections are genuine content).
