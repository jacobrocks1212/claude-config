# Test-Only Production Seams — Investigation Spec

> The agentic implementation workflow systematically ships speculative production code whose only purpose is to enable test coverage/observability (test-only hooks invoked in production hot paths, settable override properties read only by tests, and reaching for the codebase-forbidden `[InternalsVisibleTo]`), because no authoring guardrail, execute/review gate, constitution rule, or PR-review detector covers this specific class.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-13
**Placement:** docs/bugs/test-only-production-seams/
**Related:** `user/skills/test-driven-development/testing-anti-patterns.md` (Anti-Pattern 2); `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/rules/testing.yaml`; `user/skills/_components/subagent-review.md`

<!-- Status lifecycle: Investigating → Concluded (root cause + fix scope proven; ready for /plan-bug). -->

---

## Verified Symptoms

Both witnessed directly in the originating session (Cognito Forms, branch `p/57077-cog-pay-account-deletion`), not reported second-hand.

1. **[VERIFIED]** A test-only callback was invoked in a production hot path. `CoreService.PurgeOrganization` carried `ArchiveMidpointHookForTests?.Invoke()` between the archive-stamp write and the entity-teardown call — an `internal Action` whose only purpose was to let a test simulate a mid-archive crash. Removed this session; production destructive path no longer carries a test invocation point.
2. **[VERIFIED]** A settable override property exists whose sole consumer is a test. `CoreService.PaymentAccountTypeResolverOverride` (`internal Func<Type>`) is set only via `CoreServiceTests.SetPaymentAccountTypeResolverOverride` (by reflection) to inject a fake/null payment-account type. It is dead in production.
3. **[VERIFIED]** `[InternalsVisibleTo]` is a recurring reach for this same goal and is explicitly disallowed in the Cognito codebase — codified as `no-internals-visible-to-for-tests` (`testing.yaml:359`), which exists precisely because the workflow keeps proposing it.
4. **[VERIFIED — coverage gap]** None of the current guardrails name symptoms 1 and 2. The nearest authoring rule, `testing-anti-patterns.md` Anti-Pattern 2 "Test-Only Methods in Production" (line 63), covers test-only *methods* only, with a TypeScript example, and does not mention production-path hooks or settable test-override fields.

## Reproduction Steps

1. Run the implementation workflow (`/spec` → `/spec-phases` → `/write-plan` → `/execute-plan` or `/implement-phase`) on a feature whose behavior is hard to observe from the public surface (e.g. a retry/idempotency ordering inside a destructive path, or reflection over a type in a non-referenceable assembly).
2. Observe the generated production code: to make the behavior test-observable it introduces a test-only seam directly into the production class — an `Action`/`Func` hook invoked on the production path, an `internal` settable override read only by a test, or an `[InternalsVisibleTo]` grant.
3. Observe that `/execute-plan`'s batch review gate (`_components/subagent-review.md`) and `verification-before-completion` pass the change — the seam is not flagged.

**Expected:** Test observability is achieved through legitimate production seams (constructor-injected dependencies, mockable interfaces, `protected virtual` members intended for extension) or the test is restructured; where no seam exists, a real injectable dependency is introduced. Production code carries no test-only invocation points, override hooks, or visibility widening.
**Actual:** The workflow emits a test-only production seam and it survives review to merge.
**Consistency:** Recurring across sessions and seam-shapes (hook, override property, `[InternalsVisibleTo]`) — a class of defect, not one instance.

## Evidence Collected

### Source Code (originating symptoms)

| Seam shape | Where | Only consumer |
|---|---|---|
| Test-only hook on production path | `Cognito/CoreService.cs` `ArchiveMidpointHookForTests?.Invoke()` in `PurgeOrganization` (removed this session) | `CoreServiceTests.PurgeOrganization_HookThrows...` (removed) |
| Settable test-override property | `Cognito/CoreService.cs` `internal Func<Type> PaymentAccountTypeResolverOverride` | `CoreServiceTests.SetPaymentAccountTypeResolverOverride` (reflection) |
| Visibility widening | forbidden by `no-internals-visible-to-for-tests` (`testing.yaml:359`) | n/a — the rule exists because it keeps being proposed |

### Fix-site gaps (traced by reading the guardrail files)

- **Authoring layer.** `user/skills/test-driven-development/testing-anti-patterns.md:63-116` (Anti-Pattern 2) + Iron Law `:17` cover test-only **methods**; no rule names production-path hooks or settable test-override fields. `SKILL.md:357-362` (`## Testing Anti-Patterns`) is the index that would need a matching bullet. `_components/implementation-agent.md:16` says "no speculative features beyond what the tests require" — targets speculative *features*, not test-enabling *seams*.
- **Execute/review gate.** `user/skills/execute-plan/SKILL.md` Step 3 reads `_components/subagent-review.md` before each commit; its "TDD DISCIPLINE" block (~`:105-112`) is the natural enforcement point and currently has no test-seam-hygiene check.
- **Constitution.** `user/CLAUDE.md` has a `<testing>` block ("xUnit, AAA pattern, test behavior not implementation, mock external dependencies") — the home for a one-line always-on principle that applies outside the skill pipeline.
- **PR-review detector — with a scoping trap.** `cognito-pr-review` uses a YAML rule-catalog (`knowledge/rules/*.yaml`) → generated shards (`knowledge/rendered/*.md`) → the rule-agnostic `agents/sweep.md`. The seam-hygiene cluster (`no-test-only-service-params:44`, `no-public-for-tests:56`, `no-internals-visible-to-for-tests:359`) lives in `testing.yaml`, whose `file_patterns` (`:5-10`) match only `*Tests.cs` / `*.test.ts`. **The offending seams live in production `.cs` files, so a rule added to `testing.yaml` would never fire on them.** A new detector must live in (or be cross-listed in) a category whose patterns match production code — `csharp-architecture.yaml` (all `.cs`) or `code-consistency.yaml` (all files).

## Proven Findings

- **Root cause (design/coverage gap, not a runtime fault).** The workflow's test-authoring guidance, execute/review gate, constitution, and PR-review catalog each cover adjacent shapes (test-only methods, test-only params, public-for-tests, `[InternalsVisibleTo]`) but none covers **test-only hooks invoked in production paths** or **settable test-override properties read only by tests**, and none frames the general principle: *production code must not carry seams that exist only for test observability.* Where the shapes are partially covered (`[InternalsVisibleTo]`), coverage lives only in the PR-review catalog — downstream of authoring — and even there is mis-scoped to test files. So the workflow both **emits** these seams (no authoring guardrail) and **fails to catch** them (no correctly-scoped detector).
- **Correct output when no seam exists.** The remedy is not "delete the test" but "introduce a legitimate injectable dependency / mockable interface / `protected virtual` extension point," or restructure the test to drive real behavior. The guidance must say this so it does not merely forbid without redirecting.

## Affected Area

| Component | Files | Change |
|---|---|---|
| TDD authoring guidance | `user/skills/test-driven-development/testing-anti-patterns.md`, `.../SKILL.md` | New/expanded anti-pattern covering production-path hooks + settable test-override fields + the "introduce a real seam instead" redirect; index bullet |
| Execute/review gate | `user/skills/_components/subagent-review.md` | One line in the TDD-discipline block: flag net-new production code whose only consumer is a test |
| Constitution | `user/CLAUDE.md` `<testing>` block | Terse always-on principle |
| PR-review detector | `cognito-pr-review/knowledge/rules/{csharp-architecture,code-consistency}.yaml`, `knowledge/weights.yaml`, then `/cognito-pr-review:rebuild-agents` | New rule (e.g. `no-test-only-production-seam`) in a **production-file-matching** category; weight entry; regenerate shard |

## Fix Scope (to be locked in /plan-bug)

1. **Author** the anti-pattern in `testing-anti-patterns.md` (hook-on-production-path + settable test-override property; C# examples; Gate Function; redirect to DI / mockable interface / `protected virtual`), add the `SKILL.md` index bullet.
2. **Gate** it in `_components/subagent-review.md` TDD-discipline block (one flag line) so `/execute-plan` and `/implement-phase` catch it pre-commit.
3. **Codify** the always-on principle in `user/CLAUDE.md` `<testing>`.
4. **Detect** it in `cognito-pr-review`: add `no-test-only-production-seam` to a category whose `file_patterns` match production `.cs` (NOT `testing.yaml`), add its `weights.yaml` entry, run `/cognito-pr-review:rebuild-agents`.

## Open Questions

- **PR-review category placement** — `csharp-architecture.yaml` (C#-only, matches the observed cases) vs `code-consistency.yaml` (all files, also catches TS/Vue analogs). Language-agnostic argues for `code-consistency`; the witnessed cases are all C#. Decide in planning.
- **Anti-pattern granularity** — one consolidated "Production Seams That Exist Only for Test Observability" anti-pattern subsuming the existing method/param/InternalsVisibleTo rules by cross-reference, vs a new sibling that only adds the two uncovered shapes. Leaning consolidated-with-cross-refs to avoid a fragmented catalog.
- **Legitimate-seam boundary** — the guidance must not chill genuine injectable dependencies or `protected virtual` extension points (which ARE the sanctioned remedy). The rule keys on "sole consumer is a test," not "used by tests."
