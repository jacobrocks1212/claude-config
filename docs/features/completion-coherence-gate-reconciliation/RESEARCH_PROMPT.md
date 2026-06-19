# Reconciling redundant "are the deliverables done?" gates in an autonomous LLM dev pipeline — evidence-gated completion checks vs. checkbox-state coherence checkers

## Research Question

In a deterministic, script-owned state machine that drives an autonomous AI software-development pipeline, three separate completion-time gates each answer "are this feature's deliverables done?" by counting unchecked Markdown checkboxes in a plan file (`PHASES.md`) — but they apply **three different rules** to one category of checkbox (runtime/MCP *verification* rows that a dedicated test step has already certified, with its passing evidence written to disk as receipt files). The disagreement forces a redundant "coherence-recovery" cycle whose only job is to tick boxes the on-disk evidence already proves done.

The chosen fix (Direction A) is locked: extend the verification-only carve-out to the completion gate, **gated on on-disk passing evidence**, and have the gate **auto-tick** the certified verification rows so the plan file ends fully coherent for a downstream checker that has no carve-out. What remains open are the **edge-case and authoritative-evidence questions** below. I want prior-art, industry-convention, and pitfall research to harden the gate's evidence-evaluation logic and de-risk the auto-tick rewrite before implementation.

## Context

- **System:** A self-improving "harness" for autonomous agentic software development built on Claude Code primitives (skills, components, deterministic Python state scripts, hooks). The state machine (`lazy_core.py` / `lazy-state.py`) owns pipeline state; LLM agents are thin wrappers that progress one cycle at a time.
- **Pipeline tail for a feature:** `/spec` → `/plan-feature` → `/execute-plan` (implementation) → `/mcp-test` (runtime validation) → `__mark_complete__` (mints the `COMPLETED.md` receipt and flips `SPEC.md` Status → Complete).
- **Plan file:** `PHASES.md` contains per-phase deliverable checkboxes (`- [ ]` / `- [x]`). Two row classes: **implementation rows** (owned by `/execute-plan`) and **verification rows** (runtime/MCP checks owned by `/mcp-test`). Verification rows carry a structural marker `<!-- verification-only -->`.
- **Evidence receipts written by `/mcp-test` BEFORE completion runs:** `VALIDATED.md` (frontmatter `kind: validated`) and/or `MCP_TEST_RESULTS.md` (`kind: mcp-test-results`, `result: all-passing`, `pass == total`, `validated_commit == HEAD`). There are also negative/edge receipts in the family: `SKIP_MCP_TEST.md` and `DEFERRED_*` variants.
- **The three gates (verified in code 2026-06-19):**
  1. `remaining_unchecked_are_verification_only` (mid-feature, `lazy_core.py:1372`) — **EXEMPTS** verification rows via a per-row structural marker.
  2. `verify_ledger.deliverables_done` (`lazy_core.py:~1970/2001`) — **EXEMPTS** (reuses the detector above).
  3. `_phase_completion_plan` (`lazy_core.py:1777/1838`, called inside `__mark_complete__` at `:3050`) — **INCLUDES** verification rows ("carve-out does not apply at completion time") and does NOT consult the on-disk evidence. This is the gate being changed.
  - Plus a **downstream, non-editable** checker in a sibling repo: `check-docs-consistency.ts` runs *post-flip* under a `Complete` SPEC and counts **every** checkbox with no carve-out at all. Because the chosen fix auto-ticks the certified rows, this checker should end up satisfied with no edit — a claim that needs confirmation.

## Baseline Spec Summary (locked decisions)

- **Direction A (chosen):** `_phase_completion_plan` applies the `remaining_unchecked_are_verification_only` exemption **only when** (a) on-disk `/mcp-test` evidence certifies passing AND (b) every remaining unchecked row is verification-marked.
- **Auto-tick (chosen):** when both conditions hold, the gate rewrites the matching `- [ ]` verification rows to `- [x]` in `PHASES.md` using the same byte-stable, in-place rewrite the existing phase-Status auto-flip already performs, then mints the receipt. Plan file ends fully coherent.
- **Evidence — not the checkbox — is the source of truth.** A genuine unchecked *implementation* (non-verification) row still refuses, naming the offending phase. The gate's defect-catching job is preserved; only the redundant re-demand for already-certified verification rows is removed.
- **Reversible:** a guarded exemption, easy to tighten.

## Research Areas

1. **Prior art — redundant "definition of done" gates in CI/CD and release-automation pipelines.** How do mature systems avoid having multiple gates re-evaluate the same completion predicate with divergent rules? Patterns: single-source-of-truth status oracles, gate composition/ordering, idempotent "promotion" steps that consume upstream evidence rather than re-deriving it.
2. **Evidence/attestation-gated promotion.** Conventions for treating a signed/attested artifact (a test-result receipt) as authoritative for a downstream gate — e.g., SLSA provenance, in-toto attestations, GitHub deployment/environment "required checks", artifact-promotion gates in Spinnaker/Argo. What makes such evidence *trustworthy enough to gate on* (freshness/commit-pinning, completeness, signature)? How do they handle skipped/deferred/partial evidence?
3. **Freshness / staleness binding of evidence to a commit.** The receipt pins `validated_commit == HEAD`. What are robust conventions for binding an attestation to the exact tree/commit it certifies, and the failure modes when HEAD moves between test and promote (re-validate? refuse? warn)?
4. **Auto-mutation of a plan/state file by a gate — pitfalls.** The gate will rewrite `- [ ]` → `- [x]` in `PHASES.md`. Risks: idempotency, partial writes/crash mid-rewrite, ticking the wrong row (marker drift), masking real incompleteness, audit-trail loss ("who ticked this and why?"). Best practices for safe, auditable, idempotent in-place mutation of a human-readable source-of-truth file by an automated step.
5. **Marker-based vs. position-based vs. section-based classification of checklist rows.** The carve-out keys on a per-row structural marker (`<!-- verification-only -->`). Tradeoffs vs. section headers or row position; lint-enforcement strategies that prevent authors from mis-marking rows.
6. **Lint-up-front vs. gate-honors-evidence.** Open Question 5: is recurring "tick the boxes" friction better fixed by stronger authoring-time lint (force correct marking) or by the gate honoring evidence? What do real teams do when an automated gate and a hand-maintained checklist drift?
7. **Multi-gate reconciliation without editing every gate.** The downstream `check-docs-consistency.ts` cannot be edited. Patterns for making one gate's output satisfy a later un-coordinated gate (normalize the artifact so the later, dumber gate trivially passes) vs. mirroring the carve-out everywhere.

## Specific Questions

1. **Authoritative evidence set:** Given receipts `VALIDATED.md` and `MCP_TEST_RESULTS.md`, is it safer to require *both*, accept *either*, or define a precedence order? What conditions should the gate check on each (frontmatter `result: all-passing`, `pass == total`, `validated_commit == HEAD`) before treating the evidence as authoritative? Cite analogous "required checks" evidence models.
2. **Skip/deferred edge cases:** When `SKIP_MCP_TEST.md` or a `DEFERRED_*` receipt is present instead of a passing one, should the completion gate (a) still refuse, (b) exempt only if an explicit operator-signed skip exists, or (c) something else? What do CI promotion gates do with "tests skipped" vs "tests passed"?
3. **HEAD drift:** If `validated_commit` no longer equals current HEAD at completion time (a commit landed after `/mcp-test`), should the gate refuse-and-require-revalidation, warn-and-proceed, or auto-revalidate? What's the convention in attestation-based promotion?
4. **Auto-tick safety:** What's the safest pattern to make the `- [ ]` → `- [x]` rewrite idempotent and crash-safe, and to leave an audit trail (e.g., a marker comment or receipt line recording that the gate — not a human — ticked the row, and which evidence authorized it)? Any prior art where an automated gate mutates the very checklist it evaluates, and the pitfalls observed?
5. **Downstream-checker confirmation:** Is auto-ticking the rows sufficient to satisfy a separate, carve-out-unaware checker (`check-docs-consistency.ts`) that counts all checkboxes post-flip — or are there realistic cases (Superseded phases, non-checkbox status lines, phases with zero deliverables) where coherence still breaks? What normalization makes a downstream "count everything" checker robustly satisfiable?
6. **Lint vs. gate (Open Question 5):** From real teams' experience, which lever more durably eliminates recurring checklist-drift friction: authoring-time lint that forces correct row marking, or a gate that honors evidence? Or is the durable fix *both* (lint to keep markers correct + gate to honor evidence)? What are the failure modes of each in isolation?
7. **Guarding against over-relaxation:** What guardrails keep an evidence-gated exemption from silently passing features with genuine unfinished work (e.g., an implementation row mis-marked as verification-only, or stale/forged evidence)? Cite defense-in-depth patterns from attestation/promotion systems.
8. **Reversibility / kill-switch:** Conventions for shipping a gate-relaxation behind a guard that's trivial to tighten or disable if it proves too permissive — feature flags, env gates, or a documented one-line revert. What granularity is standard?

## Output Format Request

Return structured findings with these sections:

1. **Executive summary** — the 3-5 highest-leverage recommendations for this specific reconciliation, each one actionable against the locked Direction A design.
2. **Per-question findings** — answer each of the 8 Specific Questions above with concrete recommendations, citing prior art / industry convention where it exists. Where a question is genuinely a product call with no single right answer, say so and give the tradeoffs.
3. **Authoritative-evidence decision table** — a recommended rule for each evidence state: `VALIDATED.md` only / `MCP_TEST_RESULTS.md` only / both / neither / `SKIP_MCP_TEST.md` / `DEFERRED_*` / HEAD-drift → {exempt-and-tick | refuse | refuse-and-revalidate | warn}, with one-line rationale per row.
4. **Auto-tick implementation checklist** — concrete safety requirements (idempotency, crash-safety, audit-trail, marker-drift protection) the rewrite must satisfy, framed as a checklist the implementer can verify against.
5. **Pitfalls & anti-patterns** — failure modes observed in analogous systems (redundant gates, evidence-gated promotion, auto-mutated checklists), each with a one-line mitigation.
6. **Downstream-checker confirmation** — a clear verdict on whether auto-ticking alone satisfies a carve-out-unaware "count everything" checker, plus the residual cases (if any) that still need handling.

Keep recommendations concrete and tied to the locked design. Prefer specific patterns and named prior art over generic advice.
