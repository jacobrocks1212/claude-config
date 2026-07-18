# Implementation Phases — Test-Only Production Seams

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — docs/skills/config-only harness change (no Tauri app surface, no MCP-reachable behavior, no audio/UI/store). Verification is deterministic grep + `lint-skills.py`/`project-skills.py` + the cognito-pr-review shard regeneration; nothing is MCP-observable.

## Validated Assumptions

All load-bearing assumptions are **code-provable** (no runtime-coupled assumption, no user-facing surface), so the Runtime Assumption Validation Gate is skipped by rule. Ground truth confirmed by reading the touchpoints this cycle:

- **`testing.yaml` mis-scoping is real.** `knowledge/rules/testing.yaml` `file_patterns` = `*Tests.cs` / `*Test.cs` / `*.test.ts` / `*.spec.ts` / `**/__tests__/**` — production `.cs` files never match, so the seam-hygiene cluster (`no-test-only-service-params`, `no-public-for-tests`, `no-internals-visible-to-for-tests`) cannot fire on the offending production files. Confirmed by reading the file head.
- **Production-file-matching category homes exist.** `csharp-architecture.yaml` matches `*.cs` (excluding `*Tests.cs`/`*Test.cs`/`**/TestFiles/**`); `code-consistency.yaml` matches `*.cs` / `*.ts` / `*.tsx` / `*.vue`. Both would fire on production `.cs`; only `code-consistency.yaml` also covers TS/Vue.
- **Rule + weight schema.** A rule is `{id, severity, description, rationale, anti_pattern, correct_pattern}` (model: `no-internals-visible-to-for-tests`, `testing.yaml:359`). A weight entry is `<rule-id>:\n    weight: 0.7\n    data_points: 0`.
- **Existing anti-pattern surface.** `testing-anti-patterns.md` carries Iron Laws (`:15-19`) + Anti-Patterns 1/2/3, each with a `### Gate Function`. `SKILL.md`'s `## Testing Anti-Patterns` index (`:357-362`) lists three bullets. `_components/subagent-review.md`'s `TDD DISCIPLINE` block (`:105-112`) is the pre-commit review enforcement point. `user/CLAUDE.md` `<testing>` holds the always-on constitution principle.

## Cross-feature Integration Notes

No `**Depends on:**` block on the SPEC — no hard upstream deps. (Omitted: nothing to integrate against.)

---

### Phase 1: Authoring + review + constitution guardrails (the emit-prevention layer)

**Status:** Fixed

**Scope:** Close the claude-config-side gap so the workflow stops *emitting* test-only production seams. One consolidated anti-pattern in the TDD reference (covering the two uncovered shapes and cross-referencing the existing partial coverage), its index bullet, a pre-commit review flag line, and a terse always-on constitution principle. Each keys on **"sole consumer is a test"** (not "used by tests"), and each redirects to the legitimate remedy (constructor-injected dependency / mockable interface / `protected virtual` extension point) so the guidance forbids-and-redirects rather than merely forbidding.

**Deliverables:**
- [x] Add a new anti-pattern to `user/skills/test-driven-development/testing-anti-patterns.md` (after Anti-Pattern 3) titled for **production seams that exist only for test observability**, covering both uncovered shapes: (a) a test-only hook invoked on a production path (an `internal Action`/`Func` `?.Invoke()`'d inside a production method — model the `ArchiveMidpointHookForTests` case) and (b) a settable test-override property/field whose sole consumer is a test (model the `PaymentAccountTypeResolverOverride` case). Include: C# `❌ BAD` / `✅ GOOD` examples, a `### Gate Function` block matching the file's existing style, an explicit redirect to DI / mockable interface / `protected virtual`, and cross-references to Anti-Pattern 2 (test-only *methods*) and the PR-review seam-hygiene rules (`no-test-only-service-params`, `no-public-for-tests`, `no-internals-visible-to-for-tests`) so the catalog reads as one consolidated cluster, not fragments.
- [x] Add a matching 4th bullet under `## Testing Anti-Patterns` (`SKILL.md:357-362`) naming the new anti-pattern.
- [x] Add one flag line to the `TDD DISCIPLINE` block in `user/skills/_components/subagent-review.md` (`:105-112`): flag **net-new production code whose only consumer is a test** (hook on a production path, settable test-override field, visibility widening) → `NEEDS-REWORK`, redirecting to a real injectable seam.
- [x] Add one terse always-on principle to the `<testing>` block in `user/CLAUDE.md` — e.g. "production code carries no seams (hooks, settable overrides, visibility widening) whose sole consumer is a test; introduce a real injectable dependency instead."
- [x] Re-project + lint: `python ~/.claude/scripts/project-skills.py && python ~/.claude/scripts/lint-skills.py` exit clean (the edit touches a `_components/` file + a skill, so the projection must be regenerated and validated).

**Minimum Verifiable Behavior:** After the edits, all of the following return a hit and the lint is clean:
```bash
grep -n "sole consumer is a test\|only consumer is a test\|test observability" user/skills/test-driven-development/testing-anti-patterns.md
grep -c "Anti-Pattern 4\|test observability" user/skills/test-driven-development/testing-anti-patterns.md   # >= 1
grep -n "test observability\|sole consumer is a test" user/skills/test-driven-development/SKILL.md
grep -n "only consumer is a test\|sole consumer is a test" user/skills/_components/subagent-review.md
grep -n "sole consumer is a test\|seams" user/CLAUDE.md
python ~/.claude/scripts/project-skills.py && python ~/.claude/scripts/lint-skills.py   # exit 0
```

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/skills/test-driven-development/testing-anti-patterns.md` — new consolidated anti-pattern (violation/why/fix/Gate-Function + redirect + cross-refs).
- `user/skills/test-driven-development/SKILL.md` — 4th index bullet under `## Testing Anti-Patterns`.
- `user/skills/_components/subagent-review.md` — one flag line in the `TDD DISCIPLINE` block.
- `user/CLAUDE.md` — one always-on principle in `<testing>`.

**Testing Strategy:** Deterministic grep for the new content at each site + `lint-skills.py` (broken injections / embedded patterns) + `project-skills.py` (component re-expands cleanly, no circular include). No runtime.

**Integration Notes for Next Phase:** The framing principle ("sole consumer is a test," with the DI/mockable/`protected virtual` redirect) is established here and MUST be reused verbatim as the PR-review rule's `description`/`rationale` in Phase 2 so authoring guidance and the detector speak identically. Phase 2 is independent of Phase 1's files (disjoint file set) and may proceed regardless of Phase 1 state.

---

### Phase 2: cognito-pr-review detector in a production-file-matching category (the catch layer)

**Status:** Complete

**Scope:** Add a correctly-scoped PR-review detector so a test-only production seam that reaches a PR is *caught*. The rule lands in a category whose `file_patterns` match production code (NOT `testing.yaml`, which matches only test files — the SPEC's scoping trap), gets a `weights.yaml` entry, and the rendered shard is regenerated via the plugin's own command.

⚖ policy: PR-review category placement → `code-consistency.yaml` (all-files: `*.cs`/`*.ts`/`*.tsx`/`*.vue`). Chosen as the most-complete path (D7): it catches the witnessed C# cases AND TS/Vue analogs, the rule keys language-agnostically on "sole consumer is a test" so broader coverage introduces no false-positive risk, and it is a cleaner thematic home than `csharp-architecture.yaml` (C#-architecture-specific). This is a coverage-completeness choice, not a product fork.

**Deliverables:**
- [x] Add a `no-test-only-production-seam` rule to `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/rules/code-consistency.yaml`, mirroring the `no-internals-visible-to-for-tests` schema (`id`, `severity: important`, `description`, `rationale`, `anti_pattern`, `correct_pattern`). `description` keys on **sole consumer is a test** and enumerates the shapes (hook `?.Invoke()` on a production path, settable `internal` test-override property/field, visibility widening); `correct_pattern` shows the DI / mockable interface / `protected virtual` remedy. Explicitly does NOT flag genuine injectable dependencies or `protected virtual` extension points ("used by tests" ≠ "sole consumer is a test").
- [x] Add `no-test-only-production-seam:` with `weight: 0.7` / `data_points: 0` to `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml` (matching the seam-cluster entries).
- [x] Run `/cognito-pr-review:rebuild-agents` to regenerate `knowledge/rendered/code-consistency.md` from the updated rule catalog (never hand-edit the rendered shard). *(Rendered append-only per `commands/rebuild-agents.md` §3 — the new rule's H4 subsection only; no other rule changed, so no full-catalog re-render was needed.)*
- [x] Confirm the regenerated shard carries the new rule.

**Minimum Verifiable Behavior:** After the rule + weight edits and the rebuild:
```bash
grep -n "no-test-only-production-seam" user/plugins/local-tools/plugins/cognito-pr-review/knowledge/rules/code-consistency.yaml   # rule present
grep -n "no-test-only-production-seam" user/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml                  # weight present
grep -n "no-test-only-production-seam" user/plugins/local-tools/plugins/cognito-pr-review/knowledge/rendered/code-consistency.md  # shard regenerated with the rule
```
The host category's `file_patterns` (`*.cs`/`*.ts`/`*.tsx`/`*.vue`) match production files, so — unlike a rule in `testing.yaml` — this rule is reachable on the offending production `.cs` (and TS/Vue) files.

**Prerequisites:** None on Phase 1 (disjoint files). Independent — may run before, after, or alongside Phase 1.

**Files likely modified:**
- `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/rules/code-consistency.yaml` — new `no-test-only-production-seam` rule.
- `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml` — weight entry.
- `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/rendered/code-consistency.md` — regenerated by `/cognito-pr-review:rebuild-agents` (generated artifact; do not hand-edit).

**Testing Strategy:** Deterministic grep at the rule source, the weight source, and the regenerated shard. The `file_patterns` scope-correctness is verified by inspection (the whole point of the SPEC): the rule sits in an all-files category, not the test-only-scoped `testing.yaml`.

**Integration Notes for Next Phase:** Terminal phase. **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` and writes `FIXED.md` after the validation tail — this plan never flips status or writes the receipt.

---

## Implementation Notes

- **Two disjoint layers, one defect.** Phase 1 stops the workflow *emitting* the seam (authoring + review + constitution); Phase 2 *catches* one that slips through (PR review). Their file sets are disjoint, so they may be executed in either order or together.
- **⚖ policy: PR-review category placement → `code-consistency.yaml`** (all-files) — most-complete coverage (C# + TS/Vue analogs); the rule keys narrowly on "sole consumer is a test" so breadth adds no false-positive risk. (SPEC Open Question 1.)
- **⚖ policy: anti-pattern granularity → one consolidated anti-pattern with cross-references** to the existing method/param/`InternalsVisibleTo` rules, rather than a fragmented sibling — matches the SPEC's stated lean and avoids catalog fragmentation, while leaving the existing Anti-Patterns 1–3 renumbering-free. (SPEC Open Question 2.)
- **Legitimate-seam boundary (SPEC Open Question 3, settled — not a decision):** every guardrail keys on "sole consumer is a test," NOT "used by tests," so genuine injectable dependencies / `protected virtual` extension points are never chilled. Baked into the Phase 1 anti-pattern, the Phase 1 review flag, and the Phase 2 rule text.

### Execution Notes (2026-07-18)

- **Phase 1 — anti-pattern placement drift reconciled.** The plan/PHASES anchor "add after Anti-Pattern 3" was authored against a stale 3-anti-pattern view of `testing-anti-patterns.md`; the file now carries 8 anti-patterns. To honor the ⚖ "leave existing anti-patterns renumbering-free" policy, the new anti-pattern was appended as **Anti-Pattern 9: Production Seams That Exist Only for Test Observability** (after AP-8, before "When Mocks Become Too Complex"), renumbering nothing. Added matching Quick Reference row + Red Flags entry for catalog consistency. All MVB greps pass; `project-skills.py` + `lint-skills.py` clean.
- **Phase 2 — rule appended at end of `code-consistency.yaml` `rules:` list** (order-independent); rendered shard regenerated append-only by rendering the new rule's H4 subsection per `commands/rebuild-agents.md` §3 (severity + description + anti/correct-pattern fences; rationale is not rendered by spec). Weight entry `weight: 0.7 / data_points: 0` mirrors the seam-cluster entries.
