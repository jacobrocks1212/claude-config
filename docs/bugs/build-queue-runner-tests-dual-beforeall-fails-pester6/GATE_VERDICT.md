---
kind: gate-verdict
feature_id: build-queue-runner-tests-dual-beforeall-fails-pester6
gate_version: 1
date: 2026-07-14
scope_hit: [user/scripts/build-queue-runner.Tests.ps1]
checks:
  overfit: pass
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: the two-top-level-`BeforeAll` "merged suite" construct in build-queue-runner.Tests.ps1 (a Pester-5-only pattern) — replaced by one `BeforeAll`. Net surface DECREASES (two block openers → one; three duplicate setup statements dropped); no rule, matcher, or gate added.
override: absent
---

## Adversarial answers

### overfit
Not flagged (harness-gate `overfit: pass`). The fix appends NO literal to any matcher,
alternation, keyword set, or allow-list — it merges two `BeforeAll` blocks into one and drops
three idempotent duplicate statements. There is no "observed instance" being fitted: the change
is structural and applies to the whole container, not to a specific test or phrasing. The
nearest recurrence — another `build-queue*.Tests.ps1` growing a second top-level `BeforeAll` —
would be caught the same way (Pester 6 discovery refusal), and the durable guard against it is
the L6 gate itself now being able to DISCOVER this suite (it could not before). No structural
property is being narrowly keyed on.

### tautology
Not flagged (`tautology: pass`, no feature-dir passed to the checker; the ship seam supplies the
SPEC). The change emits no metric it also consumes. Its independent signal is the Pester runner's
own discovery+run verdict: before, `Discovery … failed … 0 tests`; after, `Tests Passed: 17,
Failed: 0`. That signal is produced by Pester, not by this change — a broken merge would show as a
discovery error or a failing `It`, both externally observable.

### gate_weakening
Not flagged (`gate_weakening: pass`). No `It`/`Describe`/test was deleted, no threshold softened,
no assertion removed, no exemption/sanction-set membership added. The change is the OPPOSITE of a
weakening: it RE-ENABLES a completion-gate suite (one of the five build-queue L6 suites) that was
silently un-runnable under Pester 6 — coverage goes from 0 discoverable tests in this file to 17
running. Verified: `Invoke-Pester -Path user/scripts/build-queue-runner.Tests.ps1` → 17 passed / 0
failed / 0 skipped.

### complexity
`retires:` above. The change RETIRES the dual-`BeforeAll` "merged suite" construct — a
Pester-5-tolerated pattern the file's own header docstring described ("Each concern group carries
its own BeforeAll setup") — in favor of a single `BeforeAll`, which is legal under BOTH Pester 5
and 6. Net control surface strictly decreases: two block openers become one and three duplicate
statements (`$script:RunnerPath` / `$script:HygienePath` re-assignments + the second
`. $script:HygienePath`) are dropped. No new rule, script, matcher, or config is introduced; the
setup runs the identical statements in the identical order the two sequential Pester-5 `BeforeAll`s
ran. This pays for itself trivially — it is a net simplification that restores gate coverage.
