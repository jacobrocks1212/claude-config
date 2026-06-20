# Research Summary — Completion / Coherence Gate Reconciliation

> Gemini deep-research pass analyzed against the locked baseline (Direction A, evidence-gated, auto-tick). Full report: `RESEARCH.md`.

**Bottom line:** the research **confirms** the locked Direction A and converts the three remaining research-answerable Open Questions (3–5) into a concrete, evidence-gated implementation contract. No baseline reversal; the research is purely additive — it specifies the edge-case decision table, the atomic-write contract, and a kill-switch the baseline left as TBD.

---

## Key findings relevant to our baseline

1. **Direction A is the correct frame (confirmed).** The research models our three-gate disagreement as a CI/CD artifact-normalization problem: a trusted intermediary (the completion gate) normalizes the human-readable plan (`PHASES.md`) to match verifiable on-disk evidence, shielding the naive downstream checker (`check-docs-consistency.ts`). Auto-ticking *is* the normalization pass. This is exactly Direction A + Decision 2 = A.

2. **Evidence model = Verification Summary Attestation (VSA).** Treat `MCP_TEST_RESULTS.md` as the raw execution provenance (the test payload) and `VALIDATED.md` as the attestation envelope (the policy claim). The gate must evaluate the **union** — neither file in isolation is sufficient. Accepting `VALIDATED.md` alone risks a forged receipt minted without test execution; accepting `MCP_TEST_RESULTS.md` alone bypasses the policy-evaluation layer. This **answers Open Question 3** (authoritative evidence): require BOTH, with `VALIDATED.md` as the trigger and `MCP_TEST_RESULTS.md` as the contingent proof.

3. **Authoritative-evidence decision table (Open Question 3, fully mapped).** The research gives a precise truth table the gate must implement:

   | `VALIDATED.md` | `MCP_TEST_RESULTS.md` | `validated_commit` | Gate action |
   |----------------|-----------------------|--------------------|-------------|
   | present (`kind: validated`) | present (`all-passing`, `pass==total`, `pass>0`) | `== HEAD` | **Exempt-and-tick** |
   | present | missing / malformed | `== HEAD` | Refuse (forged-attestation risk) |
   | missing | present | n/a | Refuse (VSA not executed) |
   | present | present | `!= HEAD`, source-file delta | Refuse-and-revalidate (TOCTOU) |
   | present | present | `!= HEAD`, **docs-only** delta | Warn + exempt-and-tick |
   | `SKIP_MCP_TEST.md` | missing | `== HEAD` | Refuse (fail-closed) |
   | `DEFERRED_*` | missing | `== HEAD` | Refuse, do NOT tick |
   | neither | neither | n/a | Refuse |

4. **SKIP / DEFERRED = fail-closed (Open Question 3 edge cases).** A skip or deferral receipt is functionally equivalent to absent evidence. The gate must **refuse the auto-tick exemption** for `SKIP_MCP_TEST.md` / `DEFERRED_*` unless an explicit operator override marker is present. Because the uneditable downstream checker counts all boxes, the only mathematically sound paths are: run the test, or have the agent excise the deliverables from the plan. The gate must NOT auto-tick deferred rows.

5. **HEAD-drift handling (Open Question 3, TOCTOU).** Strict `validated_commit == HEAD` is the default. But the agent legitimately commits doc/status updates between `/mcp-test` and `__mark_complete__`, so a naive strict check would over-refuse. Resolution: when `validated_commit != HEAD`, **inspect the git diff** — if it touches only non-executable docs (`PHASES.md`, `*.md`), warn-and-proceed; if it touches source/scripts/config, refuse-and-revalidate.

6. **`check-docs-consistency.ts` needs NO change (Open Question 4 — confirmed).** Final verdict from the research: auto-ticking is **fully sufficient** to satisfy the naive count-everything downstream checker, *provided the normalization pass is exhaustive*. Because the checker evaluates physical `- [x]` state (not semantic intent), rewriting the rows before the flip shields it entirely. No sibling-repo edit required — exactly what Decision 2 = A assumed.

7. **Lint AND gate, not lint OR gate (Open Question 5 — answered: both).** Neither layer suffices alone ("Swiss Cheese" defense). Evidence-gating alone is dangerous: a hallucinating LLM could attach `<!-- verification-only -->` to a real implementation deliverable (`- [ ] Write database migration <!-- verification-only -->`), and the gate would auto-tick unwritten code. Lint alone doesn't remove the friction (the agent still hits the completion refusal). The durable fix is authoring-time lint enforcing the marker only sits on test-shaped rows **plus** the evidence gate doing the physical mutation. The lint side for the MID-feature path is already partly addressed by `harness-hardening-retro-fixes`; this feature owns the completion-gate evidence side.

---

## Ideas to adopt from prior art

- **Atomic write contract (research §4 + checklist).** The auto-tick rewrite must NOT use `open('r+')` / naive truncating writes. Use write-to-temp-in-same-dir → `flush()` + `os.fsync()` → `os.replace()` (atomic rename). This is exactly the pattern the existing phase-Status auto-flip should already follow; the auto-tick pass reuses it. (macOS `fcntl.F_FULLFSYNC` note is moot on this Windows-primary harness but harmless to honor cross-platform.)
- **Line-anchored regex, code-block exclusion.** Match `^\s*-\s+\[\s+\]` with the `<!-- verification-only -->` marker required on the SAME line; skip lines inside ``` fences. Forbid naive global `.replace('- [ ]','- [x]')`.
- **Audit-trail comment.** Append a byte-stable `<!-- auto-ticked: validated_commit=<sha> -->` to each rewritten row so a later auditor can distinguish gate mutations from agent/human edits. Record the count of auto-ticked rows in `COMPLETED.md`.
- **Cardinality lock (over-relaxation guard).** Assert `auto_tick_count <= pass_count` from `MCP_TEST_RESULTS.md`. If more rows are slated for ticking than tests passed, refuse — this catches marker-drift hallucination and forged evidence.
- **Kill-switch env var.** Gate the whole relaxation behind an env flag (e.g. `LAZY_STRICT_EVIDENCE_GATE` / `LAZY_DISABLE_AUTOTICK`): when set, fall back to the legacy strict `_phase_completion_plan` and skip mutation. Frictionless rollback without a code revert.

---

## Pitfalls / concerns to address

- **Superseded phases with stray unchecked boxes** — the auto-tick pass must prune (or the lint must force removal of) unchecked boxes under phases marked `Superseded`, or the downstream checker fails on them. Already partly handled by the existing phase-Status auto-flip; confirm the auto-tick pass covers Superseded rows.
- **Malformed / variable-whitespace checkboxes** (`- [  ]`) — regex must tolerate `^\s*-\s+\[\s+\]`, else the row is skipped and the downstream checker flags it.
- **Marker typos** (`verification-onlly`) — the gate silently skips a typo'd marker, causing a downstream failure. Authoring-time lint must enforce exact, case-sensitive marker spelling. (Lint side — partly upstream in `harness-hardening-retro-fixes`.)
- **Forged / zero-test evidence** — `pass==total` with `total==0` is a known false-positive anti-pattern; the gate must require `pass>0`.

---

## Baseline decisions to revisit

None reversed. The research **confirms** Direction A and Decision 2 = A (auto-tick). It converts the three research-answerable Open Questions into a locked implementation contract:

- **OQ3 (authoritative evidence)** → require BOTH `VALIDATED.md` + `MCP_TEST_RESULTS.md` (VSA model); SKIP/DEFERRED fail-closed; HEAD-drift handled by docs-only-diff carve-out. Decision table above is authoritative.
- **OQ4 (downstream checker)** → no `check-docs-consistency.ts` edit needed; auto-tick is sufficient given an exhaustive normalization pass.
- **OQ5 (lint vs gate)** → both layers; this feature owns the completion-gate evidence side, lint side is the marker-correctness enforcement (partly upstream).

The research also **adds** four implementation contracts the baseline did not specify and which `/spec-phases` + `/write-plan` must carry into phases: atomic write, line-anchored regex + code-fence exclusion, audit-trail comment + receipt count, cardinality lock, and the kill-switch env var.
