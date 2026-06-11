# Completeness-First Standing Policy (D7 — operator-authorized 2026-06-10)

A durable, pre-authorized operator directive for the lazy-batch family (`/lazy-batch`,
`/lazy-bug-batch`, `/lazy-batch-cloud`, and the single-dispatch wrappers via their shared
resolution components). It applies in **BOTH modes** (default and `--park`). Because it is
pre-authorized, applying it requires NO echo-back and NO AskUserQuestion — it is logged, never
asked.

**The directive:** when a decision's options differ only in *how much work gets done now* —
effort, sizing, sequencing, completeness, defer-vs-fix — resolve to the **most complete
option** autonomously. The operator wants to see genuine product decisions and almost nothing
else.

## The scope test (apply before asking ANY question or writing ANY NEEDS_INPUT.md)

Ask: **would the end-state product behavior differ between the options?**

- **No — every option converges on the same product behavior**, differing only in how much is
  done now vs deferred/descoped/waived → `class: scope`. Resolve to the most complete option.
  Never ask. Typical shapes: "quick patch vs root-cause fix", "fix now vs defer to queue tail",
  "partial coverage vs full", "waive vs author", "split into phases vs do it in one".
- **Yes — options diverge in user-visible behavior, UX, API, or data semantics** →
  `class: product`. Ask (default mode: Step 1g halt; `--park` mode: park + flush).
- Two *complete but different* end states is a product fork, not a scope decision — ask.

## Resolution rules by decision site

1. **Cycle subagents (source suppression — the biggest lever).** Subagents MUST NOT write
   NEEDS_INPUT.md for scope-class decisions. Apply this policy in-cycle: take the complete
   path, and disclose it in the cycle summary (one `⚖ policy:` line, see Logging). NEEDS_INPUT
   is reserved for product-class decisions. Choosing a lower-effort path silently is a policy
   violation the input-audit flags.
2. **NEEDS_INPUT.md carrying `class: scope`** (or whose options match the scope shape
   regardless of declared class) — at Step 1g / park time, the orchestrator auto-resolves to
   the most complete option (`resolved_by: completeness-policy`), neutralizes the sentinel, and
   continues. Both modes. No question.
3. **BLOCKED.md (Step 1h).** Classify the blocker first. When every resolution path converges
   on the same product behavior (the standard "fix now / defer / halt" shape), auto-resolve:
   - **In-scope defect** → add-phase + fix now (the complete path).
   - **Discovered defect beyond this item's scope** → spin off `/spec-bug` (author the bug doc
     directly per the established dispatched-subagent pattern), cross-reference both docs,
     dependency-gate the current item if it cannot proceed, requeue it to the tail, continue.
   - **Feature-scope growth** → enqueue a new feature (`--enqueue-adhoc` + brief), cross-
     reference, dependency-gate as needed, continue.
   Only a blocker embedding a genuine product fork still asks (1h question with the fork as
   the options).
4. **Gate-1 MCP-coverage refusals (uncovered Locked Decisions).** Author the missing coverage
   automatically — route the work as a corrective cycle (mcp-tests scenario authoring + run)
   instead of asking. If coverage is genuinely infeasible (the decision falls in a documented
   MCP-untestable class per `docs/features/mcp-testing/SPEC.md`), record a test-exempt
   acknowledgement with a receipt note + digest entry — still no question. Gate-1 never asks
   under this policy.
5. **Spin-offs are pre-authorized, notify + log, no cap.** Every spin-off fires a
   PushNotification ("spun off {id} — {reason}") and a digest entry. Cross-references in BOTH
   directions are mandatory (the new doc names its origin; the origin names the spin-off).

## Exceptions — still ask (or park)

- Product-class decisions (the scope test said behaviors diverge).
- The complete option would contradict a SPEC **Locked Decision** (that contradiction IS a
  product decision).
- Destructive/irreversible operations or outward-facing actions (pushing to shared infra,
  publishing, deleting user data) beyond the pipeline's normal commit/push discipline.
- Genuine ambiguity about what "complete" means after the scope test — treat as product.

## Logging (mandatory — auto-resolved ≠ invisible)

- Each application: one line in the cycle output (T6-class, single line):
  `⚖ policy: {decision, ≤8 words} → {chosen path}[ · spun off {id}]`
- Sentinel resolutions append `resolved_by: completeness-policy` in the `## Resolution` block.
- Run-end report (T7): a **D7 digest table** — every application with decision, chosen path,
  spin-offs, and links — alongside the `--park` auto-accept digest.
- Spin-offs additionally push-notify at creation time.

## Interplay

- **D2 two-key auto-accept** (park mode, `class: mechanical`) is unchanged — D7 adds the
  `scope` class, resolved in both modes without the two-key requirement (the policy itself is
  the operator's standing key).
- **Standing-directive echo-back** (Phase 2) governs NEW mid-run directives; D7 is already
  authorized — no echo-back per application.
- **`class:` enum** in NEEDS_INPUT.md frontmatter: `mechanical | scope | product`
  (see `sentinel-frontmatter.md`).
- Graded by `/lazy-batch-retro` (R-D7-*): a scope-class question asked to the operator is a
  fail; unlogged policy applications are a fail.
