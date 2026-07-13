## Plan-Structure Authoring Gate (finalization step — run BEFORE reporting done)

**Why this component exists.** Transcript mining of two `/lazy-batch` runs attributed ~7% of
all dispatches to plan/PHASES.md structural defects the harness itself permitted at authoring
time — plans with no per-WU checklist, verification rows counted as incomplete deliverables
because they weren't under a recognized subsection, unfilled template skeleton rows surviving
into committed files, and (worst case) a plan-part series that contradicted its own declared
dependency order, producing a routing impasse. Every one of these classes was caught only
downstream, as a recovery/coherence-recovery meta-dispatch mid-run. This gate moves the refusal
to the moment of authorship — the same house move as `mcp-coverage-audit.md` /
`spec-friction-kpi-gate.md` (a deterministic script the skill shells, not an LLM self-check).

**When this runs.** After writing or updating any plan part (`plans/*.md`) or `PHASES.md` in
this cycle, and BEFORE reporting the cycle done (before the halt-protocol Decision-Classification
Ledger / final summary), run the structural validator on every such file:

```bash
python3 ~/.claude/scripts/validate-plan.py --structural <absolute-path-to-file>
```

- **Exit 0** — clean (or WARN-only; WARNs print but never block). Continue.
- **Exit 1** — one or more ERROR findings. **Fix every named defect and re-run until exit 0**
  before finalizing. Each finding names the rule, the line (when applicable), and the fix (e.g.
  `[ERROR] (wu-checklist) No per-WU '- [ ] WU-N' checklist rows found...`). Do NOT report the
  cycle done with an unresolved ERROR finding on a file this cycle authored or modified.
- A file the validator reports **"out of scope"** (not a recognized lazy plan/PHASES shape — e.g.
  a Cognito lane plan, a `/write-plan-cloud` `plans/cloud-*.md` output, or any non-plan doc) is
  correctly untouched — no action needed.

**What it checks (deterministic, no LLM judgment — the exact rule set, per rule):**

1. **Per-WU checklist (plan parts, ERROR).** A `## Work Units` flat checklist with ≥1
   `- [ ] WU-N` row — mechanizes write-plan ISSUE-6. Exempt for `kind: retro-plan` /
   `kind: realign-plan` (a deliberately different, checklist-free shape).
2. **Verification-row placement (plans + PHASES, ERROR).** A checkbox carrying verification
   vocabulary (`mcp integration test` / `mcp test assertion` / `mcp assertion` / `reachability
   smoke`) must sit under a recognized `**Runtime Verification**` / `**MCP Integration Test
   Assertions:**` subsection (tag it with the canonical `<!-- verification-only -->` marker —
   see `~/.claude/skills/_components/phases-runtime-verification.md`). A row merely mentioning
   these terms in passing (e.g. `(see Runtime Verification below)`) is NOT what this rule
   targets — only a row that reads as an actual verification assertion.
3. **Template-row rejection (plans + PHASES, ERROR).** An unfilled skeleton row lifted verbatim
   from the spec-phases/write-plan templates (`{Concrete code output 1}`,
   `Tests: {What tests verify this phase}`, `WU-N — <short title>`) — the ENTIRE row content must
   be the placeholder, not merely contain a bracket somewhere (a real row citing
   `` `<slug>/` `` or the canonical `<!-- verification-only -->` marker is correctly untouched).
4. **Gate-owned-row ban (plans + PHASES, ERROR).** A `- [ ]` row for a Status flip, a
   COMPLETED.md/FIXED.md receipt write, a ROADMAP mark, or an archive move — these are
   `__mark_complete__`/`__mark_fixed__`-gate-owned; author a prose
   `**Completion (gate-owned):**` note instead (see `phases-runtime-verification.md`'s
   GATE-OWNED ROW BAN section).
5. **Dependency-ordered plan series (plan parts, ERROR).** For a multi-part plan (`-part-K`
   suffix), a part's declared prerequisite (`**Entry criteria:**`/`**Prerequisites:**` naming
   "Phase N complete" or "requires/depends on/blocked by/after Phase N") must resolve to a
   sibling part whose series index does NOT exceed this part's — the authoring-side closure of
   the phase-number-inversion impasse `lazy_core._plan_sort_key`'s series-index ordering relies
   on producers upholding. N/A for a single-part plan.
6. **Frontmatter sanity (plan parts, WARN).** Parseable frontmatter, numeric-ish `phases:`
   entries, no duplicate WU numbers. WARNs print but never block.

**Failure states:** an unreadable/unparseable file is reported as an ERROR naming the parse
failure (never a silent pass).

**Residency note.** This validator lives in `~/.claude/scripts/validate-plan.py` (`--structural`
mode) — a new mode on the existing "validate a plan" entry point (its long-standing Cognito
coding-rules mode, invoked with a plan file + rules dir, is completely untouched). It imports
(never re-implements) `lazy_core`'s canonical parsers (`_plan_wu_checkbox_counts`,
`_VERIFICATION_ONLY_MARKER`, `_VERIFICATION_SECTION_RE`, `_DELIVERABLES_SECTION_RE`,
`_PLAN_PART_RE`) so this gate and the state machine's own consumer-side recognizers can never
silently disagree on vocabulary. A companion **pickup backstop** (running the same checks
in-process at the first `/execute-plan` routing, so a structurally invalid plan authored outside
these skills — hand-written, cloud-generated — is also caught) is tracked separately as a
state-machine change; this gate is the authoring-time half of that two-seam contract.

### Coupling note

Injected into:
- `user/skills/write-plan/SKILL.md` (Step 4, alongside the plan-file-output write protocol)
- `user/skills/spec-phases/SKILL.md` (Step 7, after PHASES.md is written)
- `user/skills/spec-phases-batch/SKILL.md` (Step E.3, alongside the holistic cross-feature review)

`/plan-feature` and `/plan-bug` inherit this gate for free — they only DISPATCH `/spec-phases`
and `/write-plan`, never author plan/PHASES content of their own. `/write-plan-cloud` is
DELIBERATELY not wired — its output (`plans/cloud-*.md`, a self-contained GitHub-Copilot-cloud
briefing for a different consumer/repo) explicitly bans the checkbox format these rules assume
(see write-plan-cloud/SKILL.md Step 4 item 7: "No progress checkboxes") and is excluded by the
validator's own path convention. When editing this component, run
`grep -r "plan-structural-gate.md" ~/.claude/skills/ --include="*.md" -l` to confirm the blast
radius matches the three files above.
