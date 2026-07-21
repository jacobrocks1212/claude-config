# Semantic-Equivalence Review — Phase 1 (Residual prose-density deflation, D1)

**Purpose (no-policy-lost guard):** for every clause removed by WU-1
(`cycle-base-prompt.md` skill-specific `@section`s + Class-B rationale tails) and
WU-2 (`cycle-prompt-addenda.md`), map the removed prose → the surviving terse rule
it belonged to, proving deflation is prose-density reduction ONLY — no enforceable
rule dropped. Follows the parent's `SEMANTIC_DIFF_PHASE2.md` / `SEMANTIC_DIFF_PHASE3.md`
table precedent.

**Scope (binding):** prose-density trim ONLY — no `@section` selector-narrowing, no
path-shorthand/reference-by-path (both operator-rejected; SPEC "Out of scope"). Every
`@section` selector line preserved BYTE-EXACT (the emitter's filter depends on them).

**Measured reduction (all 20 assembled profiles, re-locked via `--lock-in-profile`):**
13,012 B saved (3.83%) across the 20 dispatchable profiles — per-profile 145–1,180 B
(largest: feature/bug workstation mcp-test/runtime-up ~1.18 KB, the 5.7 KB
`skill-mcp-test-common` section's share). No profile grew; every ceiling lowered.

**Gates green:** `skill-size-ratchet.py --check` exit 0 at the new floor;
`test_dispatch.py` binding-matrix + residue guards green (emitter still assembles every
profile, no unbound `{token}`, preserved literals survive); `generate-coupled-skills.py
--check` exit 0 (the emitter OUTPUT template does not appear in the committed coupled
SKILL.md files, so no `--write` owed); `project-skills.py` + `lint-skills.py` clean.

---

## WU-1 — `cycle-base-prompt.md`

### Class A — never-deflated `skills=<specific>` sections

#### `skill-execute-plan` + `skill-execute-plan-cloud` (execute-plan,retro-feature)

| Removed clause | Surviving terse rule (every branch preserved) |
|----------------|-----------------------------------------------|
| `(HARD — ISSUE 2, d8-effect-chains run)` framing on the header | `EXECUTE ONLY THE DISPATCHED PLAN PART (HARD)` — the HARD marker kept, the issue-round provenance dropped |
| `Order those prerequisites by series_index (frontmatter-honored — the same order the router uses), NOT by raw part-number` | `ordered by series_index (NOT raw part-number)` — the ordering RULE kept, the "same order the router uses" aside dropped |
| `a sibling P is a prerequisite of the dispatched part D iff series_index(P) < series_index(D)` | Preserved verbatim as terse logic: `a sibling P is a prerequisite of dispatched part D iff series_index(P) < series_index(D)` |
| `A part rescheduled to a HIGHER series_index (series_index: N  # RESCHEDULED …) to run LAST is NOT a prerequisite of a lower-series_index part … do NOT block on it (hydra-overlay false-block, 2026-07-19)` | `A part rescheduled to a HIGHER series_index is NOT a prerequisite of a lower one even when its -part-K filename number is lower — do NOT block on it` — the RULE kept in full; the `# RESCHEDULED` example syntax and the dated `hydra-overlay false-block` incident dropped |
| `Absent a series_index field, fall back to the raw part-number` | `Absent series_index, fall back to raw part-number` |
| `If a genuine prerequisite part is not status: Complete, STOP and write BLOCKED.md (blocker_kind: prerequisite-part-incomplete) naming the unmet part — do NOT silently switch to it` | Kept: `A genuine incomplete prerequisite (not status: Complete) → STOP + BLOCKED.md (blocker_kind: prerequisite-part-incomplete) naming the unmet part; never silently switch to it` |
| `(Live incident: dispatched on Sonnet for the mechanical part-2, the subagent silently executed the complex part-1 instead, then died resultless.)` | REMOVED entirely — pure war-story; the rule it illustrated (the model-tier-mismatch branch below) survives independently |
| `If the dispatched part's real work exceeds its declared complexity: tier (e.g. complex work under a Sonnet dispatch), STOP with BLOCKED.md blocker_kind: model-tier-mismatch rather than grinding it out` | Kept: `Real work exceeding the part's declared complexity: tier (e.g. complex work under a Sonnet dispatch) → STOP + BLOCKED.md (blocker_kind: model-tier-mismatch) rather than grinding it out` |
| TEST-FIRST / SUBSTANTIVE-REVIEW / ATOMIC-GATE+COMMIT bullets — verbose framing | Condensed to terse rules; R4 test-agent→impl-agent (ws) / inline-collapse (cloud), R6 subagent-review-contract-vs-inline split, R5 chained command — all retained |

**No branch lost:** series_index ordering, the `<`-comparison, the higher-index
non-prereq exception, the raw-part-number fallback, `prerequisite-part-incomplete`,
and `model-tier-mismatch` all survive. Only the FRAMING was compressed.

#### `skill-mcp-test-common` (mcp-test) — largest section (~5.7 KB)

| Removed clause | Surviving terse rule |
|----------------|----------------------|
| `(a feature once burned three ~1M-token rounds peeling one layer per round — the historical pattern this mandate now heads off from round 1, not just round 3)` | REMOVED — pure war-story; the SEAM ENUMERATION mandate (`## Seam Enumeration` at ANY retry_count incl. 0, per-seam probed-OK/probed-FAIL/unprobed, `/investigate` at retry_count >= 2) survives in full |
| Verbose framing across VALIDATED_COMMIT / INLINE-FIX / NO-FIRE-AND-FORGET / VALIDATION-BLOCKED / SKIP-PROVENANCE / RECONCILE-PHASES bullets | Every rule kept: `validated_commit` sha-freshness, D5 inline-fix test-first+disclose+no-self-certify, the full sentinel ladder (VALIDATED.md/MCP_TEST_RESULTS.md/DEFERRED_REQUIRES_DEVICE.md/SKIP_MCP_TEST.md/BLOCKED.md), `requires_host` vs device deferral litmus, `mcp-validation` code-only + `get_sidecar_status` + `mcp-runtime-unready` env-transient exclusion, `granted_by`+`spec_class` skip provenance, `phases-slice.py` reconcile, per-phase R7 flips |

#### `mcp-test-runtime` variant=runtime-up (mcp-test)

| Removed clause | Surviving terse rule |
|----------------|----------------------|
| `A zombie node process left holding the :3333 pipe after a dev:restart leaves the runtime HTTP-healthy but MCP-functionally DEAD — a self-inflicted ENVIRONMENT transient, NOT a code failure` | REMOVED (war-story detail); the RULE survives: `/health == 200 does NOT prove the sidecar is connected` + probe `get_sidecar_status` + `is_connected: false` → NEEDS_RUNTIME, never an `mcp-validation` BLOCKED |
| `(Same escape as the no-runtime variant's DISAGREE path — the env transient routes to runtime-readiness, never to mcp-validation.)` | REMOVED — redundant cross-reference; both variants already state the NEEDS_RUNTIME escape |
| `in its own session BEFORE dispatching you` / `against the live server, not a boot wait` verbose asides | Condensed; the rules kept: don't restart the server, SKIP Step 2 + health-poll, `get_session_meta` never-cache-log-dir |

#### `mcp-test-runtime` variant=no-runtime (mcp-test)

Only preamble framing compressed (`FIRST verify the assessment against …` →
`FIRST verify it against …`). Every rule preserved: `{untestability_reason}` token,
CONCUR (SKIP_MCP_TEST.md `granted_by`+`spec_class`+`alternative_validation`),
DISAGREE (NEEDS_RUNTIME return), "Audio IS MCP-testable" caveat.

#### `provenance-lookup` (execute-plan,retro-feature)

| Removed clause | Surviving terse rule |
|----------------|----------------------|
| `This is how you avoid re-deriving — or contradicting — a past Locked Decision that governs the file under edit.` | REMOVED — redundant closing rationale; the `--provenance-lookup <file>` command + governed_by rows + `Empty governed_by / no index → proceed (no-op)` rule survive |

#### `skill-retro` (retro,retro-feature) — DORMANT

Minor framing trim (`rather than fanning out … — only the parallelism is dropped` →
`instead of fanning out …`). The rule (Step 3 A–G research INLINE + SERIALLY;
deliverable = retro plan + RETRO_DONE.md) is preserved. DORMANT marker comment kept.

#### `skill-retro-feature` (retro-feature) · `resume-safety` ×2 (ws + cloud) — carry NO war-story/dated/rationale prose

These sections were inspected and left byte-unchanged: they contain only terse
enforceable rules (retro-feature Skill-tool inline loop; resume-safety Ready→In-progress
flip + per-WU tick + cloud push-each-flip + no-Complete-when-DEFERRED_NON_CLOUD). Per the
binding "prose-density ONLY, NO policy loss" scope, a section with nothing to strip is
correctly left intact — trimming load-bearing terse rules for their own sake would risk
policy loss (⚖ scope-class decision, see below).

#### `park-spec-sentinel-mediation` (spec,spec-bug / park=park)

Framing compressed (`no operator is watching, so an AskUserQuestion round would silently
hang` → `an AskUserQuestion round would silently hang`; `the "Phase 1 under --batch"
contract` → `Phase 1 under --batch`; `always park for the operator` → `always park`).
Every rule + id preserved: no-AskUserQuestion, DRAFT-BASELINE-FIRST, D7 in-cycle,
≤4 gating forks via NEEDS_INPUT.md with `## Decision Context` + recommendation-first +
`**Recommendation:**` + `divergence:` self-grade + `stub_origin: true`
(stub-origin-provisional-exclusion), `audit_divergence` backstop, RESEARCH_PROMPT.md
routing, BLOCKED.md `pre-research-input-required`.

### Class B — residual rationale tails inside already-deflated `skills=all` sections

| Section | Removed tail | Surviving rule |
|---------|-------------|----------------|
| `env-dialect-core` | `(an absent file raises on empty stdin)` | `Never hand-roll a cat <marker> \| python -c ... idiom` |
| `env-dialect-core` | `(a mature PHASES.md exceeds the Read cap; the slicer returns the index + only the phase(s) named)` | `Read PHASES.md ONLY through phases-slice.py {spec_path} [--phase <id>] — never a whole-file Read` |
| `env-dialect-windows` | `(WSL dialect) — this Bash tool is Git Bash on native Windows, not WSL;` | `No /mnt/c/... — use the native C:/... path (or a relative path from {cwd})` — the imperative kept |
| `workstation-dispatch` | `(workstation-recursive-subagent-dispatch, 2026-07-09 — the former inline-only ban is lifted on workstation; cloud keeps it)` | `You MAY use the Agent tool on workstation (cloud forbids it)` — the ws-permitted/cloud-forbidden policy kept; removed-history clause dropped |

## WU-2 — `cycle-prompt-addenda.md` (AlgoBooth)

### `audio-invariants` (execute-plan,retro-feature,mcp-test)

Framing compressed (`If ANY work this cycle edits a file under … , READ …` →
`Editing ANY file under … → READ …`). **KEEP-list preserved intact:** the
`crates/audio-engine/INVARIANTS.md` read mandate, the ArcSwap Guard-across-`Arc<dyn Trait>`
NO-OP `load_full()` invariant, and the "every NEW DSP module adds a §10.1 row +
`HOT_PATH_FILES` entry at the SAME commit" rule.

### `over-cap-gate-decomposition` (execute-plan,retro-feature)

Rationale condensed (the "resultless pause needing an orchestrator resume" /
"it does NOT skip or weaken any gate; it only keeps each foreground and under the cap"
elaborations tightened to one clause each). **KEEP-list preserved intact:** the four named
ts sub-gates (`npm run type-check` / `npm run lint` / `npm run test:run` / `npm run build`),
the "never run the aggregate `npm run qg -- ts`" rule, and "never `run_in_background` a long
gate" — plus the `run_ts_gates`/`scripts/quality-gate.sh` pointer and the qg-rust/qg-sidecar
build-queue distinction.

---

## Preserved load-bearing literals (verbatim, never touched)

Confirmed present by grep after all WU-1/WU-2 edits (asserted by `test_dispatch.py`):

- **Every `@section` selector line** — all `<!-- @section … pipelines=… modes=… skills=… [variant=…] [park=…] [hosts=…] -->` markers byte-exact (emitter filter depends on them), incl. `env-dialect-windows … hosts=windows`.
- `WORKSTATION DISPATCH — LOAD-BEARING` · `CLOUD OVERRIDE — LOAD-BEARING`
- Tokens: `{cwd}` · `{work_branch}` · `{receipt_name}` · `{item_label}` (+ all other bindable tokens: `{pipeline_phrase}`/`{item_name}`/`{item_id}`/`{current_step}`/`{sub_skill}`/`{sub_skill_args}`/`{spec_path}`/`{forbidden_status}`/`{mark_pseudo}`/`{untestability_reason}`)
- The R5 chained-command form `<gate> && git add <paths> && git commit … && git push` (turn-end — untouched)
- `git_safe_push` · the `git add -A` ban (turn-end — untouched)
- `classify_conflict` + `conflict_kind: semantic` + `--park-provisional` (turn-end — untouched)
- `--verify-ledger` + `ok:true` four-condition certification (turn-end — untouched)
- `cycle-subagent-bg-gate-guard.sh` (turn-end — untouched)
- `--provenance-lookup` (provenance-lookup section) · `--tool-search`/`tool-search.py` (tool-search section — untouched)
- The `series_index` prerequisite-ordering ALGORITHM (compressed framing, every branch intact — see the skill-execute-plan table above)

## ⚖ Scope-class decisions (D7, disclosed)

1. `⚖ policy: sections with no war-story/dated/rationale prose → left byte-intact` —
   `skill-retro-feature` and both `resume-safety` variants carry only terse enforceable
   rules; the binding scope is prose-density trim with NO policy loss, so nothing was
   removed from them (removing terse rules to hit a byte target would be policy loss).
2. `⚖ policy: gate-5 residuals in out-of-scope sibling files → surfaced, not edited` —
   the plan/gate-5 whole-directory grep also matches three sibling dispatch templates
   (`dispatch-recovery.md:26` "d8-effect-chains review", `dispatch-spike.md:11`
   "hydra-overlay", `research-halt-announcement.md:38` "d8-effect-chains") whose matches
   live in NON-EMITTED HTML-comment provenance (never dispatched — not the bug's symptom,
   which is emitted `@section` prose). Those files are OUTSIDE this plan part's declared
   file list (WU-1 = `cycle-base-prompt.md` only); their cleanup belongs to Deliverable 2's
   family-wide guard (a later phase), not D1. The two in-scope files are residue-free.

---

# Phase 2 — Family-wide cleanup (D2a, standing anti-bloat guard)

**Purpose:** Land the new HARD war-story lint GREEN honestly — the family-wide hard gate
requires the family clean, so removable emitted war-story/dated provenance is REMOVED
(never grandfathered via the allowlist), preserving every load-bearing rule. The war-story
detector is EMITTED-TEXT-SCOPED (drives the emitter's own parser: selectable `@section`
bodies, non-allowlist HTML-comment spans stripped), so ONLY prose the emitter actually
dispatches to a subagent is in scope.

## Removed emitted provenance clauses → surviving rule

| File (section) | Removed clause | Surviving rule (every branch preserved) |
|----------------|----------------|-----------------------------------------|
| `dispatch-hardening.md` (`full-gates`) | `(operator-authorized 2026-07-19)` → `(operator-authorized)` | The ONE sanctioned `claude-code-guide` read-only exception + its enforcement-plane admission — kept verbatim; only the ISO date dropped |
| `dispatch-recovery.md` (`job-steps`, deliverables_done) | `(the machine source of truth since the 2026-06-15 d8-effect-chains review)` → `(the machine source of truth)` | The plan-part `- [ ] WU-N` checkboxes ARE the machine record vs. PHASES phase-level rows — kept; the dated review provenance dropped |
| `dispatch-recovery.md` (`job-steps`, plan-scoped form) | `(cite: live-run false alarm 2026-06-11 where a plan-level check incorrectly flagged In-progress parts beyond the one just executed)` → `(the plan-scoped check evaluates only the named part's WUs)` | Use the plan-scoped `--verify-ledger --plan` form to avoid false-fails from still-pending later parts — the RULE restated terse; the dated incident citation dropped |
| `cycle-base-prompt.md` (`status-honesty`) | `(The /retro step is unwired — 2026-06.)` → `(The /retro step is unwired.)` | The `/retro`-unwired fact kept; the year-month provenance dropped (cosmetic — `2026-06` never matched the ISO-date shape, cleaned for tidiness) |

## Deliberately LEFT (verified NON-emitted provenance — "clean only emitted ones")

These carry war-story shapes but live in the leading metadata / authoring HTML comments the
emitters DROP (before the first `@section`, or an authoring `<!-- ... -->` note) — the
emitted-text-scoped detector correctly does not flag them, and the contract permits
WHY-in-comments. Verified non-emitted by driving `emit_cycle_prompt` / `_parse_cycle_template`:

- `repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md` — `(… hand-spliced the audio
  gate on 2026-06-11; that path is now closed)` — in the leading metadata comment (before the
  first `@section`), never appended to a dispatch.
- `dispatch-spike.md` — `Origin: hydra-overlay blocked … (AlgoBooth SPIKE_PROJECTOR_FPS.md)` —
  in the leading `<!-- ... -->` metadata block.
- `dispatch-ingest-research.md` / `dispatch-corrective-coverage.md` — `(harden Round 44,
  2026-06-29)` — in the leading metadata comment.
- `research-halt-announcement.md` — `Burned on d8-effect-chains, 2026-06-14.` — inside the
  multi-line authoring HTML comment (stripped wholesale; the operator-facing variant blocks are
  clean).
- `cycle-base-prompt.md` — the two DORMANT retro-section metadata comments (`…2026-06;
  emit_cycle_prompt never selects this section…`) — inline HTML comments (and `2026-06` never
  matched the ISO shape); deliberate structural metadata, left intact.

## Not-flagged operational references (shape-4 precision, no allowlist needed)

`docs/features/mcp-testing/SPEC.md` (2× in `cycle-base-prompt.md` mcp-test-common, 2× in
`dispatch-corrective-coverage.md`) is a legit OPERATIONAL doc reference, not an incident-dir
literal. Shape 4 is BARE-dir-only (`docs/(bugs|features)/<slug>` NOT continuing into a longer
path via `(?![/\w-])`), so these are structurally excluded WITHOUT an inline allowlist marker —
keeping the dispatched prompts free of added allowlist-comment bytes (the profiles block part 1
re-locked is untouched; the cleanup only REMOVED bytes).

## ⚖ Scope-class decisions (Phase 2, disclosed)

1. `⚖ scope-class: family-wide hard gate requires a clean family` — the removable emitted
   war-stories (4 clauses above) were REMOVED, not grandfathered via the `war-story-allow`
   allowlist. The allowlist is reserved for genuine load-bearing literals; using it to
   grandfather removable narrative would defeat the guard. No real family file needs an
   allowlist entry today.
2. `⚖ scope-class: clean only emitted prose` — non-emitted metadata/authoring-comment
   provenance (the "LEFT" list above) is preserved. The contract (`lazy-batch-prompts/CLAUDE.md`)
   permits WHY-in-comments; the guard is scoped to dispatched imperative prose, so editing inert
   comment provenance would be out-of-contract churn.
3. `⚖ scope-class: per-section ceiling seeded at cleaned sizes` — the new `sections` baseline
   block (26 `@section` ceilings over `cycle-base-prompt.md`) was seeded AFTER the cleanup via
   `--seed-sections`, so it locks the post-cleanup floor; it lowers only via `--lock-in-section`.
