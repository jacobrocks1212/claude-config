# Implementation Phases — probe-full-read-before-dispatch

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — docs-only harness-contract edit (skill prose + shared component). No app surface, no MCP-reachable behavior; verification is `lint-skills.py` + `project-skills.py` projection, not a live runtime. (Cross-checked against `docs/specs/.../mcp-testing` class: contract/prose edits to `user/skills/**/SKILL.md` and `_components/*.md` are structurally outside MCP reach.)

## Cross-feature Integration Notes

(No hard deps on Complete upstream features. This is a standalone harness-contract hardening item.)

**Origin / cross-reference:** This bug spun off from the AlgoBooth `/lazy-batch` routing near-miss (2026-06-19). Related prior-art point-fix: `user/scripts/lazy-state.py:6654-6664` (withholds `cycle_prompt`/`cycle_model` on pending hardening debt so a field-extractor "fails loudly on the missing key"). This bug generalizes that one-key hardening to a contract clause covering ALL probe keys. Sibling: `docs/bugs/_archive/mcp-test-legacy-md-routes-to-haiku/`.

---

### Phase 1: Author the canonical full-read clause once in the shared dispatch component

**Scope:** Add a single canonical "full-probe-JSON read" clause to the shared dispatch component (`user/skills/_components/lazy-dispatch-template.md`) so the contract is stated once in the place all `/lazy*` wrappers already re-read. The clause: a routing/dispatch decision MUST be made against the COMPLETE current probe JSON; never field-extract a subset of keys (no jq-style cherry-pick) and route on it, because any signal outside the extracted subset (`diagnostics`, `git_guards`, `self_edit_mode`, `route_overridden_by`, `cycle_prompt_refused`, `device_deferred_features`, `terminal_reason`, …) is then invisible to the decision. Reference the prior `cycle_model` point-fix (`lazy-state.py:6654-6664`) as the precedent this generalizes.

**Deliverables:**
- [x] New subsection in `user/skills/_components/lazy-dispatch-template.md` stating the full-read-before-route clause (read the COMPLETE probe JSON; never route from a field-extracted subset), with the enumerated at-risk keys and the `lazy-state.py` precedent reference.
- [x] Tests: `python ~/.claude/scripts/lint-skills.py` passes (no broken injections / embedded patterns introduced); `python ~/.claude/scripts/project-skills.py` re-projects cleanly with the new clause expanded into every consuming wrapper.

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/project-skills.py` regenerates `~/.claude/skills-projected/` with the new clause text present in each projected `/lazy*` SKILL.md that injects this component; `lint-skills.py` exits 0.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/skills/_components/lazy-dispatch-template.md` — add the full-read clause subsection.

**Testing Strategy:** Run `lint-skills.py` (basic + `--check-projected --check-capabilities`) and `project-skills.py`; grep the projected output to confirm the clause expanded into the wrappers that inject the component. Pure docs verification — no runtime.

**Integration Notes for Next Phase:**
- The shared component is NOT injected into the per-file atomicity/freshness prose (`SKILL.md:591`/`:593` is hand-written, not a `!cat` injection). So Phase 2 must still mirror the clause directly into each SKILL.md's atomicity rule — Phase 1 alone does not reach the atomicity prose.
- Keep the clause wording stable so Phase 2 can quote/echo it consistently across the six wrappers.

---

### Phase 2: Mirror the clause into the atomicity rule of every coupled wrapper

**Scope:** Add the full-read clause directly adjacent to the existing `probe→emit→dispatch atomicity` + freshness rules in every wrapper that carries that prose, so the contract is visible at the exact point the orchestrator reads the probe and decides a route. The coupling rules in `CLAUDE.md` require mirroring across both coupled pairs plus the single-item wrappers. Six files:
- `user/skills/lazy-batch/SKILL.md` (~591–593, the atomicity + freshness rules)
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (coupled twin)
- `user/skills/lazy-bug-batch/SKILL.md` (coupled twin — bug pipeline)
- `user/skills/lazy/SKILL.md` (single-item)
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` (single-item, coupled with `lazy`)
- `user/skills/lazy-bug/SKILL.md` (single-item, bug pipeline)

The mirrored clause is identical in substance to Phase 1's canonical wording; each file states it where its dispatch/atomicity protocol is described. Update each coupled file's State Machine Summary / "Differences from" block only if the change alters orchestration shape (it does not — it tightens an existing rule, so no divergence-table edit is expected; confirm during the diff-the-twin check).

**Deliverables:**
- [ ] Full-read clause added to the atomicity rule region of all six SKILL.md files above.
- [ ] Coupled-pair parity confirmed: after editing each member of a pair, diff its twin and confirm the clause text matches (per the `CLAUDE.md` coupling rule). Run `python user/scripts/lazy_parity_audit.py` if it covers these files.
- [ ] Tests: `lint-skills.py` + `project-skills.py` pass after all six edits; per-repo projections regenerate cleanly.

**Minimum Verifiable Behavior:** A grep for the clause's key phrase (e.g. "full probe JSON" / "never route from a field-extracted subset") returns a hit in all six SKILL.md files; `lint-skills.py --check-projected --check-capabilities` exits 0.

**Runtime Verification** *(checked by lint + projection, not a live runtime):*
- [ ] `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` exits 0 after all edits.
- [ ] `python ~/.claude/scripts/project-skills.py` regenerates `_default/` + all per-repo projections without error.

**Prerequisites:**
- Phase 1: the canonical clause wording exists in the shared component so Phase 2 mirrors consistent text.

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`
- `user/skills/lazy-bug-batch/SKILL.md`
- `user/skills/lazy/SKILL.md`
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`
- `user/skills/lazy-bug/SKILL.md`

**Testing Strategy:** Per-file Read-before-Edit; after each coupled-pair edit, diff the twin to confirm parity. Final `lint-skills.py` (full mode) + `project-skills.py` run. Grep all six files for the clause phrase. No runtime.

**Integration Notes for Next Phase:**
- The optional mechanical guard (dispatch-guard hook / `--emit-prompt` path detecting a route that ignored a live signal) is explicitly OUT of scope for this bug — the SPEC's Open Question recommends prose-only this pass and notes the guard as a candidate follow-up. If pursued, it is a separate `--enqueue-adhoc` item, not a phase here.

---

## Implementation Notes

**Scope decision (D7, scope-class — pre-authorized, disclosed):** The SPEC's Open Questions raise (1) prose-only vs. a mechanical guard, and (2) where to state the clause once. Both differ only in effort/sizing, not in end-state product behavior (the harness contract is documentation; no user-visible / API / data-semantics divergence). Per the completeness-first policy I took the most complete IN-SCOPE prose path: state the clause once in the shared component (Phase 1) AND mirror it into every wrapper's atomicity rule (Phase 2), matching the SPEC's own recommendation ("prose clause across all wrappers in this pass"). The stronger mechanical guard is deliberately deferred as a candidate follow-up (a future `--enqueue-adhoc` item), exactly as the SPEC recommends — not silently dropped.

  ⚖ policy: prose-only vs mechanical guard → prose clause across all wrappers; guard deferred as follow-up
  ⚖ policy: state-once vs hand-mirror → both — canonical in shared component + mirrored into per-file atomicity prose

#### Implementation Notes (Phase 1)
**Completed:** 2026-06-19
**Work completed:**
- New subsection `## Full-probe-JSON read before routing (completeness, not just freshness)` added to `user/skills/_components/lazy-dispatch-template.md`. Clause states: routing decisions MUST be made against the COMPLETE probe JSON; never field-extract a subset and route on it. Enumerates at-risk keys. Cites `lazy-state.py:6654–6664` as the precedent this generalizes. Clarifies this is additive to the atomicity (provenance) and freshness (same-turn) rules.
**Integration notes:**
- `lazy-dispatch-template.md` is NOT `!cat`-injected into the per-file atomicity/freshness prose in SKILL.md — those passages are hand-written. Phase 2 must mirror the clause directly into each of the six wrapper SKILLs. The shared component serves as the canonical statement that orchestrators re-read at compaction boundaries and before dispatches.
- Projection confirmed: `project-skills.py` regenerated 80 skills, 91 components, 0 errors.
**Pitfalls & guidance:**
- The component is referenced by name (not `!cat`-injected) in `lazy-batch`, `lazy-bug-batch`, `lazy-batch-cloud`, and `orchestrator-voice.md` for re-read discipline — the projection tool doesn't expand these name-only references as injections.
**Files modified:**
- `user/skills/_components/lazy-dispatch-template.md` — added `## Full-probe-JSON read before routing` subsection (canonical full-read clause)
**Review verdict:** PASS — clause states the required contract correctly, includes at-risk key enumeration, cites precedent, and is additive to existing rules.
