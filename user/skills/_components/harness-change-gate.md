### Harness-Change Design Gate (anti-overfit / tautology / gate-weakening / complexity)

> Injected at the **planning seam** for claude-config control-surface items (the
> `phases-runtime-validation.md` audit-before-drafting precedent) and referenced by
> `/harden-harness` Step 3. A self-improving harness can overfit to single incidents, silently
> weaken its own gates, and grade itself with metrics it controls; this gate makes those failure
> modes mechanical + recorded. Blocking authority lives ONLY at the completion gate (SPEC D3).

**When this runs.** A change is IN SCOPE iff `git diff` touches ≥1 path in the committed
control-surface manifest `docs/gate/control-surfaces.json` (SPEC D1). Ordinary feature work and
non-claude-config repos are byte-identical — the checker exits `in_scope: false` and no verdict is
required. Run:

```
python3 user/scripts/harness-gate.py --repo-root . --range origin/main..HEAD \
  --feature-dir docs/features/<slug> --json
```

Exit 0 = pass / out-of-scope; exit 1 = verdict-required findings; exit 2 = malformed input.

**The mechanical half is a FLAG, not a verdict.** The checker (SPEC D2) reports diff-shape
findings; the adversarial half below turns each flag into a recorded judgment in
`GATE_VERDICT.md`. Work the questions HONESTLY — pro-forma justification to clear a flag is
"judgment laundering" and is cross-checked later against `intervention-efficacy-tracking` verdicts
(a passed-then-REFUTED change indicts its verdict) and graded in retro.

#### Adversarial questions per check

- **overfit (`result: flag`)** — the diff appended a literal to a matcher (alternation / list /
  set / allow-list) or added an incident-shaped literal (a `docs/{features,bugs}/<slug>` id, a
  date, a session id). Answer in the verdict: **"Construct the nearest recurrence this rule does
  NOT catch."** If you can name a near-neighbor variant the literal misses, the rule is fitting to
  the observed instance — reshape it to key on the STRUCTURE that generates the class (the
  `_VERIFICATION_ONLY_MARKER` structural-marker precedent), or record why the literal is genuinely
  the whole class. Name the structural property the reshaped rule keys on.
- **tautology (`result: flag | self-emitted`)** — the item's `## Intervention Hypothesis` block is
  missing, or its `signal_independence` is `self-emitted`. Answer: **"If this change were BROKEN,
  how would its success metric look?"** If the answer is "identical to working", the metric is
  tautological regardless of the declaration (the canonical in-repo case: a deny-hook "working"
  because denies stopped — which is also what a broken hook looks like). Declare a signal the
  change does NOT itself emit or suppress (an efficacy verdict, a retro finding, an independent
  ledger count), and set `signal_independence: independent` with that justification.
- **gate_weakening (`result: hit`) — NEVER judgment-passable.** The diff deleted a `def test_*`,
  changed a numeric literal on a gate line, grew a sanction/exemption set, introduced a `*_BYPASS`
  env-var, or removed a `permissionDecision: deny` / `refuse_*` / `exit 3` branch. This ALWAYS
  routes to operator sign-off (SPEC D4) — see below. Do NOT self-approve a weakening in the
  verdict.
- **complexity (`result: declaration-required`)** — always required in scope. The verdict MUST
  carry a `retires:` line: name the rule/surface this change RETIRES (a "what does this replace?"
  regularization term), or `net-new` plus a one-sentence justification for the added surface.
  Answer honestly whether the retire claim is real (does the retired rule actually stop firing?).

#### Tiered blocking semantics (SPEC D7 — option A, provisional)

- **gate-weakening hit → always the D4 sign-off halt.** The cycle writes `NEEDS_INPUT.md`
  (`written_by: harness-change-gate`, `class: product`) into the item dir with a rich
  `## Decision Context` quoting the EXACT flagged diff hunks and naming the alternative (fix the
  underlying defect instead — `/harden-harness` Prohibition #2 "never weakens a gate"). The
  pipeline halts on the existing Step-3 sentinel machinery. The operator's approval is transcribed
  into `GATE_VERDICT.md` as `override: operator-approved <date> — <one-line rationale>`. **The
  override is per-change, never standing** — it does not exempt the file or pattern from future
  review. A decline reshapes the change.
- **overfit / tautology / complexity → justify-or-halt.** The cycle MAY proceed by recording a
  concrete adversarial justification in `GATE_VERDICT.md` (the structural property the rule keys
  on; the independent observable; the real retire). A flag with NO recorded justification fails the
  ship seam and surfaces as `NEEDS_INPUT.md`.
- **In `/harden-harness` context the existing protocol is preserved VERBATIM** — the mechanical fix
  ALWAYS lands first, the run is never blocked, and a tripped smell spins off the generalization
  (Step 3 spin-off). Here the gate adds RECORDING (cite the checker output in the round), not
  blocking.

#### GATE_VERDICT.md — the recorded verdict (SPEC D5, per-change, item-dir residency)

Draft it at the planning seam from the checker JSON + the adversarial answers; the ship seam
validates its presence/shape mechanically before completion. Frontmatter follows the
`gate-verdict` schema in `sentinel-frontmatter.md`:

```markdown
---
kind: gate-verdict
feature_id: <slug>
gate_version: 1
date: <YYYY-MM-DD>
scope_hit: [<repo-relative path>, ...]
checks:
  overfit: pass | flag-justified | fail
  tautology: pass | flag-justified | fail
  gate_weakening: pass | hit-signed | fail
  complexity: pass | declared
retires: <retired rule/surface, or `net-new` + justification>
override: <absent | operator-approved YYYY-MM-DD — rationale>   # only on a signed gate-weakening
---

## Adversarial answers

### overfit
<the nearest recurrence this rule does NOT catch, and the structural property the final rule keys on>

### tautology
<if this change were broken, how the metric would look; the independent signal declared>

### gate_weakening
<the exact weakening, the underlying-defect alternative, and — if approved — the operator rationale>

### complexity
<what this retires (or net-new + why the added surface pays for itself)>
```

`checks.<name>` values: `pass` (no flag), `flag-justified` (flagged + a recorded justification),
`hit-signed` (gate-weakening approved via the D4 override), `fail` (flagged, no justification —
the ship seam refuses). A verdict that is missing, has any `fail` check, or carries an unsigned
gate-weakening hit fails the completion gate for the scoped item.
