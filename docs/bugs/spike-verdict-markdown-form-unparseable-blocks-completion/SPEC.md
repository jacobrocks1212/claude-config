# Bug: a proven-PASS Spike whose SPIKE_VERDICT.md records the verdict in markdown-bold form is unparseable → completion blocked with no forward route

**Status:** Fixed
**Severity:** P2 (a genuinely-passing runtime proof cannot advance the pipeline; the
orchestrator must hand-edit SPIKE_VERDICT.md — a HARD-CONSTRAINT-stretching manual write — to proceed)
**Discovered:** 2026-07-21
**Reported via:** `/harden-harness` observed-friction dispatch (2026-07-21, item in flight
`waveform-visualization`, AlgoBooth `/lazy-batch`)
**Root-cause class:** `script-defect` (parser) + `ambiguous-prose`/`missing-contract` (dispatch template)
**Placement:** docs/bugs/spike-verdict-markdown-form-unparseable-blocks-completion

**Related:**
- `user/skills/_components/spike-dispatch.md`, `user/skills/_components/lazy-batch-prompts/dispatch-spike.md`
  — the Spike dispatch component + the script-emitted dispatch template (the verdict-writing contract).
- `docs/specs/spike-pipeline-role/` — the Spike role + `**Spike:** required` routing (Step 9.5).
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — this round.

## Symptom (verified)

A `spike` cycle (Step 1c.7 of `/lazy-batch`) ran the runtime audio-safety proof for
`waveform-visualization` and genuinely PASSED, writing `SPIKE_VERDICT.md`. But `compute_state`
kept routing `spike` (Step 9.5 "spike verdict pending") and would NOT advance to
`__mark_complete__`. The spike subagent recorded the verdict as a rendered-markdown line:

```
**Verdict:** GO / PASS (scoped to the MCP-provable envelope; ...)
```

`lazy_core.docmodel.spike_verdict_is_pass()` scanned lines for
`re.match(r"(?i)verdict:\s*PASS\b", stripped)` — an ANCHORED match requiring a line that (after
strip) STARTS with `verdict:` immediately followed by whitespace then `PASS`. The markdown form
fails it two ways: (a) the leading `**` bold prefix means the stripped line does not start with
`verdict:`; and (b) the value is `GO / PASS`, so even unbolded `verdict:\s*PASS` would not match
`verdict: GO / PASS`. Result: a proven-PASS spike is unparseable → completion blocked with no
forward route. The orchestrator hand-added a `verdict: pass` frontmatter line to proceed.

Reproduced directly against `spike_verdict_is_pass` (2026-07-21):
`**Verdict:** GO / PASS` → `False` (bug); `verdict: PASS` (bare line) → `True`; a
`verdict: pass` frontmatter field → `True` (why the manual fix worked). A markdown FAIL / PENDING
line → `False` (correctly).

## Root cause

**Parser (`script-defect`).** `spike_verdict_is_pass`'s anchored regex recognizes only the bare
`verdict: PASS` line (and, incidentally, a `verdict: pass` frontmatter field, since that line also
scans). It has no tolerance for the rendered-markdown `**Verdict:** ... PASS` form the dispatch
template's human prose naturally produces, and no tolerance for a PASS/FAIL token appearing after
a `GO /` / `NO-GO /` prefix.

**Contract (`ambiguous-prose`/`missing-contract`).** `dispatch-spike.md` §verdict-branching tells
the subagent to "record the verdict + evidence in the spike results doc (`SPIKE_VERDICT.md`)" but
never mandates a MACHINE-PARSEABLE authoritative verdict field — so a subagent legitimately writes
the human-readable `**Verdict:** GO / PASS` and nothing the parser can key on. The authoritative
gate signal and the human prose were never separated.

## Fix scope

1. Replace `spike_verdict_is_pass`'s single anchored regex with a shared classifier
   `classify_spike_verdict()` → `"pass" | "fail" | "pending"` that reads, in order:
   (a) an authoritative frontmatter `verdict:` field (via `parse_sentinel`), then
   (b) a line scan tolerant of leading markdown emphasis (`**`, `#`) and of a PASS/FAIL token
   anywhere in the value (`GO / PASS`, `NO-GO / FAIL`), with FAIL taking precedence (fail-closed:
   a PASS misread as pending merely re-routes to spike; a FAIL misread as PASS wrongly completes).
   `spike_verdict_is_pass` becomes `classify_spike_verdict(...) == "pass"`; add a `_is_fail`
   sibling for symmetric FAIL detection. Shared by both state scripts (single home in `docmodel`).
2. Mandate in `dispatch-spike.md` + `spike-dispatch.md` that `SPIKE_VERDICT.md` carries a
   machine-parseable authoritative verdict — a `---`-delimited frontmatter `verdict: pass|fail`
   (or a canonical `verdict: PASS`/`verdict: FAIL` line) — as the gate signal, with the human
   `**Verdict:** GO / PASS ...` prose secondary.
3. Regression tests over: frontmatter `verdict: pass`, bare `verdict: PASS` line, markdown
   `**Verdict:** GO / PASS`, a markdown FAIL doc, and a PENDING doc — asserting PASS vs FAIL vs
   pending classification (a FAIL must NEVER read as PASS).
