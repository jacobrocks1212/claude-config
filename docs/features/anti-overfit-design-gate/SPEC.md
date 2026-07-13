# Anti-Overfit + Tautology Design Gate for Harness Changes — Feature Specification

> A self-improving harness has a failure mode ordinary code doesn't: it can overfit to single
> incidents, weaken its own gates, and grade itself with metrics it controls. This feature
> generalizes the existing `/harden-harness` anti-overfit reflex into a mechanical + adversarial
> review gate on harness self-modifications — overfit-smell detection (incident-literal rules),
> tautological-metric detection (via the intervention record's signal-independence declaration),
> gate-weakening detection (loosened thresholds / broadened exemptions demand explicit operator
> sign-off), and a complexity budget ("what does this retire?") — with every verdict recorded so
> the gate's own judgment is auditable and later falsifiable by efficacy data it does not
> control.

**Status:** Complete
<!-- Stays Draft by design: the four product decisions (D1/D3/D4/D7) were PROVISIONALLY accepted
     2026-07-12 under the operator's park-provisional directive (recommended option A each; see
     NEEDS_INPUT_PROVISIONAL.md, divergence: structural). The feature is implemented against those
     choices but MUST NOT reach Complete until the operator ratifies-or-redirects — completion is
     mechanically blocked while the unratified provisional sentinel exists. -->
**Priority:** P1
**Last updated:** 2026-07-12
**Friction-reduction feature:** yes
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; self-evolution
batch); fleshed out via internal desk research 2026-07-04 (Gemini research skipped by operator
directive — see RESEARCH.md)

**Depends on:**
- `intervention-efficacy-tracking` — composes — efficacy verdicts are the gate's ground truth (a
  gate must be falsifiable by data it doesn't control); the signal-independence field is shared
  vocabulary.

> Shipped prose-level ancestor: the `/harden-harness` anti-overfit reflex from
> `harness-hardening-retro-fixes` (Complete) — `user/skills/harden-harness/SKILL.md` Step 3's
> over-fit detector (four smell signals, first-occurrence rule for literal-phrase patches,
> generalization bound, spin-off protocol) and its Prohibition #2 ("Never weakens a gate").
> This feature promotes that reflex from one skill's prose into a repo-wide mechanical checker +
> adversarial protocol with recorded verdicts. Other implemented contracts consumed:
> `lazy_core.apply_pseudo` completion gates (the ship-time seam), the
> `phases-runtime-validation.md` planning-time-audit component pattern, the NEEDS_INPUT.md
> rich-body sentinel convention (`_components/sentinel-frontmatter.md`), and the logged
> operator decline of a gate-weakening proposal
> (`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md:44`, "GAP 2 DECLINED
> (gate-weakening — Prohibition #2)") as the canonical positive example the detector must
> catch mechanically.

---

## Executive Summary

The hardening loop already exhibits every smell this gate targets, with receipts: rules keyed to
one incident's literal strings (the canonical `_VERIFICATION_SECTION_RE` phrase-append that
motivated the `/harden-harness` over-fit detector), proposals the operator had to decline as
gate-weakening (the logged GAP-2 decline at `hardening-log/2026-07.md:44` — an exemption that
would have required deleting a passing gate test), and success claims measured by the absence of
a signal the change itself suppresses (a deny-hook "working" because denies stopped — which is
also what a broken hook looks like). Today the only defense is prose guidance inside one skill
plus operator vigilance; nothing mechanical stands between a plausible-but-wrong harness change
and `main`. This serves the mission's "best-practice-aligned" criterion directly: when the
harness and best practice conflict, fix the harness — and this gate is the fixture that notices
the conflict.

The design splits each check into the part a deterministic script can do and the part that needs
adversarial judgment, then runs both at two seams. A stdlib checker
(`user/scripts/harness-gate.py`) inspects a diff against a committed control-surface manifest
and mechanically flags: literals appended to matcher constructs (overfit), missing or
`self-emitted` signal-independence declarations (tautology), threshold/exemption/refusal changes
in gate code (gate-weakening), and a missing retires-or-justifies declaration (complexity
budget). A shared component carries the adversarial half — "construct the nearest recurrence
this rule does NOT catch"; "what would this metric show if the change were broken?" — whose
answers are recorded in a per-change `GATE_VERDICT.md`. Gate-weakening hits never pass on
judgment alone: they demand explicit operator sign-off via the existing NEEDS_INPUT.md decision
mechanism. Every verdict is recorded, and the gate is not exempt from the system it enforces:
its own checker, manifest, and component are on the manifest, its verdicts are cross-checkable
against `intervention-efficacy-tracking` outcomes (a gate that passes changes which later get
REFUTED is itself mis-tuned), and it registers its own KPI row.

The alternative seams — a blocking pre-commit hook, or leaving the reflex where it lives —
fail on house invariants: hooks are fail-OPEN by convention (a blocking design gate at the hook
layer would either violate that or be silently skippable), and the `/harden-harness` reflex only
sees hardening rounds, not the pipeline items that ship most control-surface changes.

## Design Decisions

### D1. Scope trigger — what counts as a control surface

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** Which changed paths arm the gate? Too narrow and gate-weakening ships ungated;
  too broad and ordinary feature work pays a review tax the stub explicitly exempts it from.
- **Options:**
  - **A — committed manifest of glob patterns (recommended initial set):**
    `docs/gate/control-surfaces.json` listing: `user/hooks/**`, `user/scripts/lazy-state.py`,
    `user/scripts/bug-state.py`, `user/scripts/lazy_core.py`, `user/scripts/lazy_guard.py`,
    `user/scripts/lazy_inject.py`, `user/scripts/lazy-parity-manifest.json`,
    `user/scripts/build-queue*.ps1`, `user/skills/lazy*/**`, `user/skills/harden-harness/**`,
    gate-bearing components (`_components/mcp-coverage-audit.md`,
    `_components/adhoc-enqueue.md`, `_components/sentinel-frontmatter.md`,
    `_components/phases-runtime-validation.md`), hook registrations in `user/settings.json` and
    `repos/*/.claude/settings.json`, and the gate's own files (`user/scripts/harness-gate.py`,
    the manifest itself, the gate component). A diff is in scope iff it touches ≥1 matching
    path. Pros: auditable, diffable, and self-referential by construction — widening or
    narrowing the manifest is itself a control-surface change the gate reviews. Cons: a
    manifest can go stale (mitigated: the planned `doc-drift-linter` class of check, and the
    gate's own KPI row tracks misses found in retro).
  - **B — heuristic path classification in code:** no manifest to maintain, but the trigger
    becomes invisible, untestable prose-in-code — and editing the heuristic would not
    self-trigger.
- **Recommendation:** A. The initial glob set above is the recommendation; the operator owns
  additions/removals (each being a gated change thereafter).
- **Resolution:** **A — committed glob manifest, self-included** (`docs/gate/control-surfaces.json`
  with the listed initial glob set). Provisionally accepted 2026-07-12 per the operator's
  park-provisional directive (`NEEDS_INPUT_PROVISIONAL.md`, `decision_commit 3c15b7ef`,
  divergence: structural — ratification pending; the feature does not complete until the operator
  ratifies or redirects).

### D2. Mechanical vs LLM-adversarial split per check

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Which part of each check is deterministic script territory and which needs an
  adversarial reviewer?
- **Options:** One serious candidate, assigning each check the strongest layer that can
  actually decide it:
  - **Overfit-smell — mechanical flag + adversarial follow-up.** The script flags a diff that
    appends a quoted literal to an existing matcher construct (regex alternation, list/set
    literal, keyword/header allow-list) in manifest-scoped code — the literal-string heuristic
    is mechanically detectable (canonical instance: another `|seam\s+audit` alternative added
    to `_VERIFICATION_SECTION_RE`, cited in `harden-harness/SKILL.md`). It also flags added
    literals that match an existing `docs/{features,bugs}/<slug>` id or a dated/session-shaped
    path. A flag is not a verdict: the adversarial reviewer must then answer "construct the
    nearest recurrence this rule does NOT catch" in the verdict, or the change reshapes to a
    structural rule.
  - **Tautology — mechanical presence check + adversarial substance check.** The script
    requires the item's Intervention Hypothesis `signal_independence` field (shared vocabulary
    with `intervention-efficacy-tracking`) to be present and not `self-emitted`-without-
    justification for scoped changes. The adversarial half answers: "if this change were
    broken, how would its success metric look?" — if the answer is "identical", the metric is
    tautological regardless of the declaration.
  - **Gate-weakening — mechanical diff detection, never judgment-passable.** Diff-level
    detectors: deletion/rename of `def test_*` in `test_lazy_core.py` / `test_hooks.py` or of
    in-file `--test` fixtures without replacement; numeric-literal changes on lines in gate
    code; additions to sanction/exemption sets (e.g. `SANCTIONED_STOP_TERMINAL`,
    `_FAIL_CLOSED_EVIDENCE_SENTINELS`, hook allow-prefixes); introduction of new bypass
    env-vars (the `BUILD_QUEUE_BYPASS=1` shape); removal of `permissionDecision: deny`
    branches, `refuse_*` call sites, or exit-3 refusals. Any hit routes to operator sign-off
    (D4) — mechanical detection, human authority, per the stub.
  - **Complexity budget — mechanical presence check + adversarial reality check.** The script
    requires a `retires:` declaration in the verdict (names a retired rule/surface, or
    `net-new` plus a justification sentence); the adversarial half judges whether the retire
    claim is real.
- **Recommendation:** As above — each check's mechanical floor is what a script can decide
  without judgment; everything requiring judgment is recorded prose in the verdict, so it is
  auditable later.
- **Resolution:** Auto-accepted; internal detector architecture with no operator-visible mode
  choice (the operator-visible consequences are D4/D7).

### D3. Where the gate runs

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** Which seam(s) host the gate — hardening pipeline step, pre-commit hook, cycle
  review, planning-time audit, completion gate?
- **Options:**
  - **A — two pipeline seams + harden-harness delegation, one shared checker (recommended):**
    (1) *Design seam:* a `_components/harness-change-gate.md` component injected into the
    planning stage for claude-config items (the `phases-runtime-validation.md` per-repo
    audit-before-drafting precedent) — the cycle runs `harness-gate.py` on the proposed
    surface, works the adversarial questions, and drafts `GATE_VERDICT.md` before
    implementation. (2) *Ship seam:* the `__mark_complete__`/`__mark_fixed__` path refuses a
    scoped item whose `GATE_VERDICT.md` is missing, failing, or carrying an unsigned
    gate-weakening hit (fail-closed at the completion gate, where fail-closed already lives —
    receipts, MCP coverage). (3) `/harden-harness` Step 3 delegates its smell detection to the
    same `harness-gate.py` (single source), keeping its own spin-off + never-blocks-the-run
    protocol unchanged.
  - **B — blocking pre-commit / PreToolUse hook:** rejected as the *blocking* layer. Hooks in
    this repo are fail-OPEN by convention (`user/hooks/CLAUDE.md`) — a blocking design gate at
    the hook layer is either a convention violation or silently skippable, and a review
    requiring adversarial prose cannot run in a deny hook at all. A WARN-only advisory hook
    remains a possible later addition, out of v1.
  - **C — harden-harness step only (status quo, generalized in place):** misses the primary
    shipping path — most control-surface changes arrive through pipeline items, not hardening
    rounds.
- **Recommendation:** A — one checker, three consumers; blocking authority lives only at the
  completion gate, which is already the repo's fail-closed layer.
- **Resolution:** **A — two pipeline seams + harden-harness delegation, one shared checker**
  (planning-time design seam drafts the verdict; completion-gate ship seam is the only blocking
  layer; `/harden-harness` Step 3 delegates to the same checker). Provisionally accepted 2026-07-12
  per the operator's park-provisional directive (`NEEDS_INPUT_PROVISIONAL.md`, divergence:
  structural — ratification pending).

### D4. Override protocol — the shape of operator sign-off

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** A gate-weakening hit (or a contested overfit/tautology fail) needs explicit
  operator sign-off "rather than riding an ordinary cycle." What form does sign-off take?
- **Options:**
  - **A — NEEDS_INPUT.md decision round (recommended):** the cycle writes `NEEDS_INPUT.md`
    (`written_by: harness-change-gate`, rich `## Decision Context` body quoting the exact diff
    hunks the detector flagged) into the item dir; the pipeline halts on the existing Step-3
    sentinel machinery; the operator's answer is transcribed into `GATE_VERDICT.md` as
    `override: operator-approved <date> — <one-line rationale>`. Pros: reuses the shipped
    halt/resume mechanism and the exact shape `/harden-harness` already uses for contract
    forks; the sign-off is durable and auditable on the verdict. Cons: a halt, by design —
    gate-weakening should not be frictionless.
  - **B — a standalone `GATE_OVERRIDE.md` sentinel the operator hand-writes:** hand-written
    sentinels are the anti-pattern the write hooks exist to reject
    (`block-noncanonical-blocker-write.sh` class); a new hand-authored sentinel family invites
    exactly that confusion.
  - **C — an env-var bypass (`HARNESS_GATE_BYPASS=1`):** the detector would have to flag its
    own bypass mechanism as gate-weakening; unauditable after the fact.
- **Recommendation:** A — and the override is per-change, never standing: an approved weakening
  does not exempt the file or the pattern from future review.
- **Resolution:** **A — NEEDS_INPUT.md decision round; approval transcribed to the verdict
  `override:` field; per-change only.** Provisionally accepted 2026-07-12 per the operator's
  park-provisional directive (`NEEDS_INPUT_PROVISIONAL.md`, divergence: structural — ratification
  pending).

### D5. Verdict recording

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where and in what shape is each verdict recorded so the gate is self-auditable?
- **Options:**
  - **A — `GATE_VERDICT.md` in the item dir + summary pointer on the intervention record:**
    frontmatter (`kind: gate-verdict`, `feature_id`, `gate_version`, `date`, `scope_hit:`
    paths, per-check results `pass|flag-justified|fail`, `override:`) parsed by the existing
    `lazy_core.parse_sentinel`; body carries the adversarial answers verbatim. At capture time,
    `intervention-efficacy-tracking`'s record gains a `gate_verdict:` summary field, so the
    durable central ledger retains the verdict outcome even after a bug dir is archived.
    Written by the cycle agent from the checker's JSON + its own adversarial prose; the ship
    seam validates presence/shape mechanically.
  - **B — central-only verdict files:** loses co-residency with the item the operator is
    reviewing during the needs-input round.
- **Recommendation:** A — item-dir residency rides the existing item lifecycle and the central
  pointer solves archive-survival, aligning with the efficacy feature's residency
  recommendation.
- **Resolution:** Auto-accepted A; artifact layout with the operator-facing halt/override
  behavior carried in D4/D7.

### D6. The gate's own KPI row and efficacy hypothesis

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How is "the gate itself becoming friction" or "the gate not working" made
  measurable from day one?
- **Options:** Single candidate: on shipping, the gate registers KPI rows with
  `friction-kpi-registry` (by role: per-system KPI declarations with signal sources and
  direction-of-goodness) — hit rate per scoped change, override rate (operator sign-offs /
  gate-weakening hits), false-positive burden (flags judged spurious in the verdict), and
  verdict-vs-efficacy disagreement (changes the gate passed that `intervention-efficacy-
  tracking` later REFUTED, and changes it flagged that were CONFIRMED). Its own intervention
  record declares `target_signal` over gate-weakening incidents reaching `main` unreviewed,
  with `signal_independence: independent` — the efficacy evaluator and retro produce that
  signal, not the gate.
- **Recommendation:** As above — the stub locks "not exempt from the system it enforces"; this
  is the concrete instantiation.
- **Resolution:** Auto-accepted; measurement plumbing mandated by the stub, no new operator
  choice.

### D7. Blocking semantics per check class for autonomous runs

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** When a check fails mid-autonomous-run, what happens — halt, justify-and-
  proceed, or warn-and-log?
- **Options:**
  - **A — tiered (recommended):** *gate-weakening* → always the D4 sign-off halt (stub-locked
    authority). *Overfit / tautology / complexity* → justify-or-halt: the cycle may proceed by
    recording a concrete adversarial justification in `GATE_VERDICT.md` (e.g. naming the
    structural property the rule keys on, or the independent observable); a flag with no
    recorded justification fails the ship seam and surfaces as NEEDS_INPUT. In `/harden-
    harness` context the existing protocol is preserved verbatim: the mechanical fix ALWAYS
    lands first, the run is never blocked, and a tripped smell spins off the generalization —
    the gate adds recording, not blocking, there.
  - **B — everything halts:** turns every flagged literal into an operator interrupt; the
    harden-harness never-block-the-run principle exists precisely because that is unworkable.
  - **C — everything warns:** a gate that cannot refuse is a dashboard; gate-weakening
    specifically must not ride an ordinary cycle (stub-locked).
- **Recommendation:** A — authority proportional to irreversibility: weakening an existing gate
  is the one class where a wrong pass is silently catastrophic.
- **Resolution:** **A — tiered** (gate-weakening → D4 sign-off halt; overfit/tautology/complexity
  → justify-or-halt via a recorded adversarial justification; `/harden-harness` never blocked).
  Provisionally accepted 2026-07-12 per the operator's park-provisional directive
  (`NEEDS_INPUT_PROVISIONAL.md`, divergence: structural — ratification pending).

## User Experience

- **Ordinary feature work (any repo, non-scoped paths):** zero change. The checker exits
  `in_scope: false` and no verdict is required.
- **A scoped claude-config item:** at planning time the injected component runs the checker and
  the cycle drafts the verdict skeleton; the operator sees nothing unless a gate-weakening hit
  (or unjustified flag) halts the item with a NEEDS_INPUT round quoting the flagged hunks:

  ```
  $ python3 user/scripts/harness-gate.py --repo-root . --range origin/main..HEAD --json
  {
    "in_scope": true,
    "scope_hit": ["user/hooks/lazy-cycle-containment.sh"],
    "checks": {
      "overfit": {"result": "flag", "evidence":
        ["+ 'adhoc-fix-probe-cache' appended to deny-slug list (matches docs/bugs slug)"]},
      "tautology": {"result": "pass"},
      "gate_weakening": {"result": "hit", "evidence":
        ["- exit 2  # deny branch removed (lazy-cycle-containment.sh:141)"]},
      "complexity": {"result": "missing-declaration"}
    },
    "verdict_required": true
  }
  ```

- **Operator sign-off:** an ordinary AskUserQuestion round driven by the NEEDS_INPUT.md — the
  decision text names the exact weakening and the alternative (fix the underlying defect
  instead, per harden-harness Prohibition #2). Approval is transcribed onto the verdict;
  decline reshapes the change.
- **Audit:** `GATE_VERDICT.md` sits next to the item's SPEC (readable on GitHub mobile); retro
  and the efficacy evaluator cross-reference it. On any checker error the pipeline seams treat
  the gate as un-run and say so — a crashed checker never silently passes a scoped change
  (fail-closed at the completion seam, unlike hooks).

## Technical Design

```
diff (origin/main..HEAD or --staged)          docs/gate/control-surfaces.json (manifest)
        │                                                  │
        ▼                                                  ▼
 user/scripts/harness-gate.py  ── JSON verdict ──►  cycle agent drafts GATE_VERDICT.md
   (stdlib; read-only over git)                       (adversarial answers recorded)
        │                                                  │
        │                              gate-weakening hit / unjustified flag
        │                                                  ▼
        │                                    NEEDS_INPUT.md (written_by: harness-change-gate)
        ▼                                                  │ operator sign-off → override field
 ship seam: __mark_complete__/__mark_fixed__ refuse scoped items with missing/failing/
 unsigned GATE_VERDICT.md;  /harden-harness Step 3 delegates smell detection to the checker
```

- **Checker (`user/scripts/harness-gate.py`):** stdlib-only, read-only (shells `git diff`
  / `git diff --name-only`; never writes). `--repo-root`, `--range <a>..<b>` or `--staged`,
  `--json`. Exit codes: 0 = pass/out-of-scope, 1 = verdict-required findings, 2 = malformed
  input — matching the state scripts' exit-code conventions. Detectors per D2 operate on diff
  hunks plus light context (enough lines to recognize an alternation/list/set append); they are
  deliberately structural, not literal-keyed — the checker must pass its own overfit check.
  Tests in `test_harness_gate.py` (pytest, fixture diffs for each detector, including the
  GAP-2-shaped exemption-add and the `_VERIFICATION_SECTION_RE`-shaped phrase-append as named
  regression fixtures).
- **Component (`user/skills/_components/harness-change-gate.md`):** the adversarial protocol +
  verdict template, injected at the planning stage for claude-config items (per-repo injection
  via `repos/`-side skill-config, the `phases-runtime-validation.md` override pattern) and
  referenced by `/harden-harness` Step 3. After editing: re-project + lint
  (`project-skills.py`, `lint-skills.py`) per `_components/CLAUDE.md`.
- **Ship seam:** a `lazy_core.gate_verdict_ok(spec_path, repo_root)` helper consulted on the
  `__mark_complete__`/`__mark_fixed__` path for scoped items (scope re-derived from the item's
  commit set against the manifest — deterministic, not trusted from the verdict); refusal text
  names the missing/failing check. Coupled-pair parity: mirrored in both completion handlers,
  `lazy_parity_audit.py` green. Non-claude-config repos and out-of-scope items are
  byte-identical to today.
- **Self-application:** `harness-gate.py`, `control-surfaces.json`, and the component are ON
  the manifest; the gate's KPI rows and intervention record (D6) make its judgment falsifiable
  by signals it does not emit (efficacy verdicts, retro findings).
- **House invariants honored:** the blocking layer is the completion gate (fail-closed where
  fail-closed already lives), never a hook (hooks stay fail-OPEN); script-owned deterministic
  detection with recorded human judgment (never silent LLM judgment); atomic writes via
  `lazy_core._atomic_write` for any file the seam writes; stdlib-only; verdicts and overrides
  are durable committed artifacts, satisfying audit-grade provenance.

## Implementation Phases

- **Phase 1 — Manifest + mechanical checker.** `docs/gate/control-surfaces.json`,
  `harness-gate.py` with all four detectors + `--json`, `test_harness_gate.py` fixtures
  (including the two named historical instances). Proven by: fixture diffs classify correctly;
  the checker flags a synthetic exemption-add to `SANCTIONED_STOP_TERMINAL`.
- **Phase 2 — Verdict artifact + adversarial component.** `GATE_VERDICT.md` schema (+
  `sentinel-frontmatter.md` lockstep note), `_components/harness-change-gate.md`, planning-seam
  injection for claude-config, projection + lint green. Proven by: a scoped fixture item
  produces a complete verdict; an unscoped item produces none.
- **Phase 3 — Ship seam + override round.** `lazy_core.gate_verdict_ok` wired into both
  completion handlers (parity-audited); NEEDS_INPUT.md flow for gate-weakening hits and
  unjustified flags per D7. Proven by: `test_lazy_core.py` fixtures — scoped item without
  verdict refuses; signed override completes; out-of-scope byte-identical.
- **Phase 4 — Delegation + self-audit.** `/harden-harness` Step 3 smell detection delegates to
  the checker (spin-off protocol unchanged); KPI rows registered; the gate's own intervention
  record captured. Proven by: a hardening-round dry run citing checker output; KPI/record
  artifacts present.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Scope trigger | Diff touching a manifest path vs one that doesn't | `in_scope` true/false respectively; out-of-scope runs unchanged | checker JSON |
| Overfit detection | Fixture diff appending a literal to a matcher alternation/list | `overfit: flag` with hunk-level evidence | `test_harness_gate.py` |
| Gate-weakening detection | Fixture diffs: test deletion, exemption-set add, deny-branch removal, new bypass env-var | `gate_weakening: hit` each time | `test_harness_gate.py` |
| Weakening needs sign-off | Scoped item with an unsigned weakening hit | Completion refused; NEEDS_INPUT.md present; approval + `override:` field completes | apply_pseudo output + item dir |
| Justify-or-halt | Flagged overfit with vs without recorded adversarial justification | Proceeds vs refuses at the ship seam | GATE_VERDICT.md + gate output |
| Harden-harness unchanged | Hardening round with a tripped smell | Fix lands first, spin-off enqueued, run not blocked, checker output cited in the round | hardening-log round |
| Self-application | Edit `harness-gate.py` or the manifest | The editing item is itself in scope and produces a verdict | checker JSON + item dir |
| Gate auditable | Efficacy verdict lands on a gated change | Verdict-vs-efficacy disagreement computable from records | intervention records + verdicts |

## Open Questions

> **D1 / D3 / D4 / D7 were PROVISIONALLY resolved to option A** on 2026-07-12 under the operator's
> park-provisional directive (`NEEDS_INPUT_PROVISIONAL.md`, `decision_commit 3c15b7ef`, file-level
> `divergence: structural`). These are **pending ratification** — the operator ratifies-or-redirects
> each before the feature completes. The bullets below are retained as the ratification agenda.

- **D1 — scope manifest:** committed glob manifest with the listed initial set vs heuristic
  classification. **Provisional: A** (the manifest, self-referentially included).
- **D3 — where the gate runs:** planning seam + completion-gate ship seam + harden-harness
  delegation (one shared checker) vs a blocking hook vs harden-harness-only. **Provisional: A**
  (the two pipeline seams + delegation; no hook-layer blocking).
- **D4 — override protocol:** NEEDS_INPUT.md decision round with the approval transcribed as a
  verdict `override:` field vs a hand-written override sentinel vs an env-var bypass.
  **Provisional: A** (NEEDS_INPUT.md round; per-change, never standing).
- **D7 — blocking semantics:** tiered (weakening always halts for sign-off; other checks
  justify-or-halt; harden-harness never blocked) vs all-halt vs all-warn. **Provisional: A**
  (tiered).
- Deferred empirical checks: false-positive rate of the numeric-literal-change detector on
  real historical control-surface diffs (tune context rules during Phase 1 against the
  hardening log's committed fixes); whether planning-seam injection needs a claude-config
  `skill-config/` scaffold that does not exist yet (verify during Phase 2); exact
  `sentinel-frontmatter.md` + AlgoBooth `SENTINEL_SCHEMAS` lockstep obligations for the new
  `gate-verdict` kind (verify during Phase 2).

## Intervention Hypothesis

The gate is **not exempt from the system it enforces** (D6): it declares its own falsifiable
hypothesis over a signal it does NOT emit. Parsed by `lazy_core.parse_intervention_hypothesis`;
captured at completion (which, being provisional-blocked, is deferred until ratification).

- target_signal: kpi:anti-overfit-gate.gate-weakening-unreviewed-reaching-main
- expected_direction: decrease
- signal_independence: independent — gate-weakening incidents reaching `main` unreviewed are
  produced by `intervention-efficacy-tracking` REFUTED verdicts and `/lazy-batch-retro` findings,
  NOT by the gate itself. The gate cannot suppress its own target signal (a change the gate wrongly
  passed that efficacy later REFUTES indicts the gate's verdict — the definition of a signal it
  does not control).
- review_after_runs: 20

## KPI Declaration

**Friction-reduction feature:** yes — the friction this gate cuts is a *gate-weakening or overfit
harness change reaching `main` unreviewed*, and the re-diagnosis + revert churn that follows (the
`_VERIFICATION_SECTION_RE` whack-a-mole and the GAP-2 near-miss are the receipts). Success is
measured by signals the gate does NOT emit (efficacy verdicts, retro findings, operator override
rate), per D6.

> **Registry residency is seam-deferred.** The `harness-gate` signal source + its four selectors
> are registered in `kpi-scorecard.py`'s `_SOURCES` (so these drafted rows lint clean — the
> `canary-trip-precision` spec-finalization precedent), but their COMPUTE + the
> `docs/kpi/registry.json` rows land at ratification (the registry is concurrently owned tonight —
> one-writer rule; the ship seam that produces the signal is itself seam-deferred). Until then the
> rows render NO-DATA honestly, never a fabricated zero.

Declared rows (draft — `--lint --spec` validates them; insert into `docs/kpi/registry.json` at
ratification):

```json
{
  "id": "anti-overfit-gate-hit-rate",
  "system": "anti-overfit-gate",
  "title": "Design-gate scoped-change hit rate",
  "friction": "A rising share of scoped changes tripping the checker signals either genuine risk concentration or false-positive creep — paired with the false-positive-rate row to disambiguate; tuning the numeric-literal detector to reduce it is itself a sign-off-gated weakening.",
  "signal": {"source": "harness-gate", "selector": "hit-rate"},
  "unit": "percent",
  "direction": "down-is-good",
  "baseline": {"value": null, "captured_at": null, "window": "30d", "provenance": "pending"},
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config"
}
```

```json
{
  "id": "anti-overfit-gate-override-rate",
  "system": "anti-overfit-gate",
  "title": "Gate-weakening override rate",
  "friction": "Operator sign-offs divided by gate-weakening hits — a high rate means the gate is routinely asked to bless weakenings rather than fixing the underlying defect (Prohibition #2 erosion).",
  "signal": {"source": "harness-gate", "selector": "override-rate"},
  "unit": "percent",
  "direction": "down-is-good",
  "baseline": {"value": null, "captured_at": null, "window": "30d", "provenance": "pending"},
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config"
}
```

```json
{
  "id": "anti-overfit-gate-false-positive-rate",
  "system": "anti-overfit-gate",
  "title": "Design-gate false-positive burden",
  "friction": "Flags the verdict judged spurious over total flags — the row that surfaces the numeric-literal-change detector's tuning debt (RESEARCH pitfall #1); a persistently high burden is the gate becoming friction.",
  "signal": {"source": "harness-gate", "selector": "false-positive-rate"},
  "unit": "percent",
  "direction": "down-is-good",
  "baseline": {"value": null, "captured_at": null, "window": "30d", "provenance": "pending"},
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config"
}
```

```json
{
  "id": "anti-overfit-gate-verdict-efficacy-disagreement",
  "system": "anti-overfit-gate",
  "title": "Verdict-vs-efficacy disagreement",
  "friction": "Changes the gate PASSED that intervention-efficacy-tracking later REFUTED, plus changes it FLAGGED that were CONFIRMED — the D6 self-audit signal that makes the gate falsifiable by data it does not control (a mis-tuned gate indicts itself here).",
  "signal": {"source": "harness-gate", "selector": "verdict-efficacy-disagreement"},
  "unit": "count",
  "direction": "down-is-good",
  "baseline": {"value": null, "captured_at": null, "window": "30d", "provenance": "pending"},
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "claude-config"
}
```

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by
  operator directive, 2026-07-04). Key influences: the `/harden-harness` over-fit detector and
  Prohibition #2 as in-repo ancestors; Goodhart's law, policy-as-code review gates, and
  four-eyes change control as external frames.
- `user/skills/harden-harness/SKILL.md` — the prose-level ancestor (smell signals, spin-off
  protocol, never-weaken prohibition).
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` (GAP-2 decline) — the
  canonical gate-weakening instance the detector must catch.
- `docs/features/intervention-efficacy-tracking/SPEC.md` — signal-independence vocabulary and
  the verdict ground truth this gate is audited against.
- `_components/phases-runtime-validation.md` + `_components/mcp-coverage-audit.md` — the
  planning-seam and completion-seam patterns this design reuses.
