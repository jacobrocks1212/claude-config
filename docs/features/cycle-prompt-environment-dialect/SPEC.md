# Cycle-Prompt Environment Dialect — Feature Specification

> Add a compact (<2KB), host-conditional environment-dialect section to the emitted cycle
> prompt (`_components/lazy-batch-prompts/cycle-base-prompt.md`) so cycle SUBAGENTS stop paying
> the transcript-mined Windows/environment error tax: Git-Bash trailing-backslash quoting
> failures (267 across 82 sessions), Bash-`/tmp`-vs-Windows-python mismatches (~119, still
> recurring despite a MEMORY.md note — memory notes don't reach subagents), WSL-guessed
> `sys.path` imports (~36), `/mnt/c` paths on Git Bash (~25), `json.load`-on-empty-stdin
> tracebacks from the taught marker-probe idiom (94), and oversized-PHASES.md Read failures
> (114) that `phases-slice.py` already exists to prevent but the cycle prompt never mandates.
> Anything that must bind subagent behavior must live in the emitted prompt or a hook — this
> puts the six killable clusters in the prompt, plus a never-throws `--marker-status` probe.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-11
**Source:** repo-exploration proposal session 2026-07-11 (session-transcript mining of the
Windows/environment error tax across cycle-subagent transcripts)
**Friction-reduction feature:** yes

> Substantive (non-block) dependencies are **implemented mechanisms this feature extends**:
> - The sectioned cycle-prompt template + emitter (`cycle-base-prompt.md`, 45,127 bytes today;
>   `lazy_core.emit_cycle_prompt` `@section` grammar with `pipelines=/modes=/skills=`
>   selection) — the dialect block is one new section, emitted host-conditionally.
> - `user/scripts/phases-slice.py` (`phases-slice-scoped-reads`, Complete) — the mandated
>   PHASES reader this prompt finally forces onto the failing paths.
> - The prompt-size-budget discipline of the deflation/context-diet family —
>   `docs/features/lazy-batch-skill-deflation/SPEC.md` (Draft, same proposal batch: size +
>   long-line lint ratchet on the SKILL tier) and the landed `execute-plan-skill-diet`,
>   `lean-plan-files`, `phases-slice-scoped-reads`, `spec-excerpt-scoped-plans` — the <2KB
>   budget keeps this block from re-inflating what that family deflates.

---

## Executive Summary

Cycle subagents are spawned fresh with the emitted prompt as ~their entire standing context.
MEMORY.md notes, CLAUDE.md gotchas learned mid-session, and operator corrections **do not reach
them** — so environment lessons the harness has "learned" keep being re-paid inside cycles.
Transcript mining quantifies the tax, all from cycle subagents on the Windows workstation:

| # | Cluster | Mined count | Shape |
|---|---------|-------------|-------|
| a | Git-Bash quoting | **267** errors / 82 sessions | dominant: trailing backslash before closing quote in Windows paths (`ls "C:\...\dir\"` → unexpected EOF) |
| b | Bash-`/tmp` vs Windows-python | **~119** | bash writes `/tmp/x.json`; Windows `python` can't `open()` it — still recurring 2026-07-11 despite a MEMORY.md note |
| c | `ModuleNotFoundError: lazy_core` | **~36** | WSL/cloud `sys.path` guesses hardcoded on Windows |
| d | `/mnt/c/...` on Git Bash | **~25** | WSL path dialect on a non-WSL shell |
| e | `json.load` on empty stdin | **94** | the taught `cat <marker> 2>/dev/null \| python -c "json.load(sys.stdin)"` idiom when the marker is absent |
| f | Oversized-PHASES.md Reads | **114** | Read fails on the 25k-token cap; `phases-slice.py` EXISTS as the mandated reader, but `cycle-base-prompt.md` contains **zero** `phases-slice` mentions while instructing direct PHASES walks (e.g. "walk {spec_path}'s PHASES.md", line ~374) — verified 2026-07-11 |
| g | `curl :3333/info` tools-as-objects | **39** | `TypeError` piping `/info` to python assuming `tools` entries are objects (they're strings) — killable by one line in AlgoBooth's `MCP_USAGE_GUIDE.md` (cross-repo deliverable row, not a prompt-block item) |

The design: one new `@section env-dialect` block in `cycle-base-prompt.md`, emitted
**host-conditionally** (Windows Git-Bash rules only reach Windows-host runs), hard-budgeted
**<2KB** so it does not re-bloat the prompt surface the deflation/context-diet family exists
to shrink (`lazy-batch-skill-deflation`, drafted in this same proposal batch, ratchets the
SKILL tier the same way). Content:
forward-slash/no-trailing-backslash-quote rules; pipe-python-via-stdin (never `open()` a
Bash-written `/tmp` file from Windows python); `$HOME`-anchored `sys.path` for `lazy_core`;
no `/mnt/c` on Git Bash; a tolerant marker-probe idiom — or better, a
`lazy-state.py --marker-status` subcommand that never throws (does not exist today —
verified); and a phases-slice.py mandate for every PHASES read. Cluster (g) is a one-line
cross-repo doc fix, tracked here as a deliverable row.

This is the same lesson `phases-slice-scoped-reads` already proved: prose mandates outside the
executing context are "ignored-in-the-field"; the binding surface for a cycle subagent is the
emitted prompt (and hooks). At ~700 mined incidents, even one wasted turn per incident dwarfs
the ~500-token prompt cost.

## Design Decisions

### D1. Delivery surface: prompt section vs hook vs both

- **Classification:** `product-behavior (open — recommendation below)`
- **Question:** Where does the dialect binding live?
- **Options:**
  - **A — prompt section (recommended v1):** a new `@section env-dialect pipelines=feature,bug
    skills=all` block; the emitter selects it host-conditionally (D2). Pros: reaches every
    cycle subagent by construction, zero runtime machinery, testable as emitter fixtures.
    Cons: advisory — a model can still type the error; measured value is prevention-rate, not
    a guarantee.
  - **B — PreToolUse Bash hook lint:** deny/warn on the known-fatal shapes (trailing
    `\"` in a path token, `ls /mnt/c`, `open('/tmp/…')` in a `python -c` on win32). Stronger,
    but each pattern needs careful false-positive engineering, and a deny converts a typo into
    a retry loop.
  - **C — both.**
- **Recommendation:** A for v1, with B documented as the escalation path for whichever clusters
  the KPI shows the prompt failing to kill (hooks then target only the residual shapes —
  evidence-driven, not speculative). Matches the house sequence: teach in the prompt, mechanize
  what recurs.

### D2. Host-conditionality mechanism

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** The `@section` grammar selects on `pipelines`/`modes`/`skills` (+
  `variant`/`park`); `modes=workstation|cloud` is runtime-environment, not OS. How does a
  Windows-only block get selected?
- **Options:**
  - **A — new optional `hosts=` section attribute (recommended):** `hosts=windows` selected
    when the emitting python reports a Windows host (`os.name == "nt"`, or Git-Bash-on-Windows
    via `platform`); absent → always selected (byte-identical grammar extension, the same
    pattern the `park=` attribute used per its SPEC-D13 note). Cloud/Linux runs never see the
    Windows block; a small OS-neutral core (stdin-pipe rule, marker-probe idiom,
    phases-slice mandate — clusters b/e/f are not Windows-specific in principle) can sit in an
    unconditional sibling section.
  - **B — one unconditional block with "if on Windows…" prose:** simpler, but pays the token
    cost on every host and dilutes the rules with conditionals.
- **Recommendation:** A — grammar-consistent, fixture-testable (`emit_cycle_prompt` tests
  already assert section selection), and keeps the <2KB budget honest per host.

### D3. Marker probe: tolerant idiom vs `--marker-status` subcommand

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** Cluster (e)'s 94 tracebacks come from a *taught* fragile idiom. Replace the
  idiom's text, or replace the idiom with a script?
- **Options:**
  - **A — `lazy-state.py --marker-status` (recommended):** a read-only subcommand that prints
    `{"present": bool, …summary}` and **exits 0 in every case** — absent marker, corrupt JSON,
    missing state dir (verified absent today; trivially parity-mirrored in `bug-state.py`).
    The prompt block teaches exactly one probe command. Pros: kills the whole cluster
    structurally; a script surface is testable and never dialect-sensitive.
  - **B — tolerant shell idiom only** (`python - <<'EOF'` with try/except reading the path
    directly): no script change, but keeps a multi-line taught idiom that models will keep
    mistyping — the cluster's root cause.
- **Recommendation:** A, with the block's fallback line being B's one-liner for hosts where the
  script is unreachable. Ships in the same feature (the block must reference a real command on
  day one).

### D4. Prompt-size budget enforcement

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** How is "<2KB, doesn't bloat the prompt" kept true over time?
- **Recommendation:** a unit test in the emitter suite asserts the rendered `env-dialect`
  section(s) total <2,048 bytes per host variant, and the template-header rule inventory gains
  the section (each rule lives EXACTLY ONCE — the dialect block states rules, and no other
  section may restate them). This mirrors the template's existing single-statement discipline
  and cross-links the context-diet family's byte accounting.

### D5. Cluster (g) routing — cross-repo deliverable

- **Classification:** `mechanical-internal (auto-accepted)`
- The `/info` tools-are-strings fix is one documentation line in AlgoBooth's
  `MCP_USAGE_GUIDE.md` (a different repo). It is tracked as an explicit deliverable row in this
  feature's PHASES (tagged cross-repo, AlgoBooth workstation) rather than silently dropped or
  awkwardly forced into the claude-config prompt block. The prompt block itself stays
  repo-agnostic.

## User Experience

- **Cycle subagents:** the dispatched prompt carries a short "Environment dialect (this host)"
  block — e.g. on Windows: *forward slashes or no trailing backslash before a closing quote;
  never `open()` a Bash-written `/tmp` path from Windows python — pipe via stdin; import
  `lazy_core` via `$HOME/.claude/scripts`; no `/mnt/c` on Git Bash; probe the run marker with
  `--marker-status` (never `json.load` a maybe-empty stream); read PHASES.md ONLY through
  `phases-slice.py`.* Six rules, one screen.
- **Operator:** the recurring tracebacks disappear from cycle transcripts; run reports stop
  burning turns on quoting retries; no interaction change otherwise.
- **Failure states:** on non-Windows hosts the Windows rules are absent by construction (D2);
  `--marker-status` never throws by contract; if `phases-slice.py` is missing on a host the
  block's mandate names the fallback (ranged Read via the existing grep-then-Read discipline).

## Technical Design

```
cycle-base-prompt.md
  ├─ <!-- @section env-dialect-core pipelines=feature,bug modes=workstation,cloud skills=all -->
  │     stdin-pipe python rule · --marker-status probe · phases-slice.py mandate   (~0.7KB)
  ├─ <!-- @section env-dialect-windows pipelines=feature,bug modes=workstation skills=all hosts=windows -->
  │     quoting/trailing-backslash · no /mnt/c · $HOME sys.path                    (~0.9KB)
  └─ (emitter) lazy_core.emit_cycle_prompt: parse optional hosts= attr;
       select iff host matches (absent attr → always) — grammar-additive, park= precedent

lazy-state.py --marker-status  (+ bug-state.py parity)
  read-only; {"present": false} on absent/corrupt/no-state-dir; ALWAYS exit 0

AlgoBooth MCP_USAGE_GUIDE.md  ← cross-repo row: "/info `tools` entries are strings"
```

- Emitter change is additive: absent `hosts=`, section selection is byte-identical to today
  (fixture-asserted), preserving the "default output remains byte-identical" discipline the
  emit path already documents.
- Both dialect sections respect the template's token rules (no new `{tokens}`; angle-bracket
  placeholders only).
- Re-project (`project-skills.py`) + `lint-skills.py` after the component edit, per house rule.

## KPI Declaration

Drafted row (full schema). Signal source is session-transcript mining — pending-baseline
posture per the registry's honesty rules (the mined counts below are the initial baseline
evidence, formalized when the dedicated `session-log-mining` selector (e.g.
`cycle-env-dialect-error-count`) is registered in `kpi-scorecard.py` `_SOURCES` at
implementation, per the context-diet features' registration precedent). Until then the row
points at the live deny-ledger process-friction channel where `/incident-scan` clusters these
recurring errors.

```json
{
  "id": "cycle-env-dialect-error-rate",
  "system": "lazy-cycle-prompts",
  "title": "Environment-dialect errors per 30d across cycle-subagent transcripts",
  "friction": "Cycle subagents re-pay Windows/environment lessons that never reach them (memory notes don't bind subagents): Git-Bash quoting EOFs, /tmp cross-dialect opens, sys.path import guesses, /mnt/c paths, empty-stdin json.load tracebacks, oversized-PHASES Read failures — each costing 1+ wasted turns.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "errors/30d",
  "direction": "down-is-good",
  "baseline": { "value": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-10-15",
  "notes": "Initial mined evidence (2026-07-11, full-transcript corpus): 267 Git-Bash quoting errors/82 sessions; ~119 /tmp-vs-Windows-python; ~36 lazy_core ModuleNotFoundError; ~25 /mnt/c-on-Git-Bash; 94 empty-stdin json.load; 114 oversized-PHASES Reads; 39 :3333/info TypeErrors (cross-repo doc fix). Baseline formalized via --capture-baseline once the mining selector is registered; per-cluster kill-rate is the retro grading axis."
}
```

## Implementation Phases

- **Phase 1 — `--marker-status` (~0.5 session).** Subcommand in `lazy-state.py` +
  `bug-state.py` parity; never-throws contract under absent/corrupt/no-dir fixtures; parity
  audit green.
- **Phase 2 — `hosts=` grammar + dialect sections (~1 session).** Emitter attribute (additive,
  byte-identical default); the two sections authored inside the <2KB budget; size + selection
  unit tests; rule-inventory header updated; re-project + lint-skills.
- **Phase 3 — cross-repo row + PHASES-read mandate sweep (~0.5 session).** AlgoBooth
  `MCP_USAGE_GUIDE.md` one-liner (tools-are-strings); audit the cycle template's remaining
  direct-PHASES-walk instructions (e.g. the RECONCILE step) to route through `phases-slice.py`
  where the read is a whole-file read.
- **Phase 4 — measurement hookup (~0.5 session).** Register the `session-log-mining` selector +
  `--capture-baseline`; retro grading note for per-cluster kill-rate; evidence review feeding
  the D1 hook-escalation decision.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Windows block reaches Windows cycles | emit on win32 host | rendered prompt contains the Windows rules | emitter fixtures |
| Non-Windows prompt clean | emit with hosts mismatch | Windows section absent; core section present | emitter fixtures |
| Grammar backward-compat | sections without `hosts=` | selection byte-identical to pre-feature | emitter fixtures |
| Budget held | render both variants | env-dialect bytes < 2,048 per host | emitter unit test |
| Marker probe never throws | absent / corrupt / no state dir | JSON with `present:false`, exit 0 | state-script self-tests |
| Parity | `bug-state.py --marker-status` | same contract | `lazy_parity_audit.py` |
| PHASES mandate present | emitted cycle prompt | phases-slice.py named as the ONLY PHASES reader | emitter fixtures |
| Cross-repo row landed | AlgoBooth guide | tools-are-strings line present | manual check |
| Field kill-rate | next mined corpus window | per-cluster counts fall from the cited baseline | retro / KPI row |

## Open Questions

- D1's hook-escalation threshold (which residual cluster rate justifies a PreToolUse lint) —
  deliberately deferred to post-Phase-4 evidence; surfacing now would be speculative
  mechanization.
- Whether cluster (f)'s mandate should also bind the *orchestrator's* own PHASES reads (today
  covered by `/execute-plan`'s skill contract from `phases-slice-scoped-reads`) — likely
  already covered; confirm during Phase 3's sweep.

## Research References

- Session-transcript mining corpus 2026-07-11 — the seven cluster counts cited above (initial
  KPI baseline evidence).
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — sectioned template
  (45,127 bytes; `@section` grammar header; zero `phases-slice` mentions vs the ~374
  "walk {spec_path}'s PHASES.md" instruction — verified 2026-07-11).
- `user/scripts/phases-slice.py` + `docs/features/phases-slice-scoped-reads/SPEC.md`
  (Complete) — the "ignored-in-the-field prose mandate → deterministic script" precedent this
  feature completes for cycle subagents.
- `user/scripts/lazy-state.py` — no `--marker-status` today (verified); emit path's
  byte-identical-default discipline (~12563).
- AlgoBooth `MEMORY.md` — `bash-tmp-vs-windows-python-tmp` note (documented 2026-06, cluster
  still recurring 2026-07-11: memory notes do not bind subagents).
- Context-diet family SPECs (`execute-plan-skill-diet`, `lean-plan-files`,
  `spec-excerpt-scoped-plans`) — prompt/plan byte-budget discipline the <2KB cap inherits.
