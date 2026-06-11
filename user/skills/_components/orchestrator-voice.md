# Orchestrator Voice — Output Contract (lazy-batch family)

Governs the **orchestrator's chat output only** — what the operator reads on a phone while a
batch run executes. It does NOT govern subagent prompts, sentinel file contents, docs, commit
messages, or subagent transcripts. Consumed by `/lazy-batch`, `/lazy-bug-batch`,
`/lazy-batch-cloud`; graded by `/lazy-batch-retro` (R-V-* rules).

Re-read this file after any compaction boundary (alongside `lazy-dispatch-template.md`) — the
contract survives summarization by re-read, not by memory.

## THE ZERO-TEXT RULE (overrides the harness default — read this twice)

Claude Code's general guidance — "before your first tool call, say in a sentence what you're
about to do; while working, give brief updates" — is **explicitly OVERRIDDEN** for orchestrator
runs. The operator's UI already prints every tool call (`Read lazy-preflight.md`,
`Ran bug-state.py …`); a sentence announcing the same call duplicates the line directly above
it and is pure noise on a phone.

**Between tool calls, emit ZERO text** unless what you are about to type is byte-shaped as one
of the templates. Operational test — sanctioned output starts with exactly one of:

- `## ` (T1 run-start / T7 final report headings)
- `### ` (T2/T4 cycle-block heading: `### {Step name} — {work summary} [x/y]`)
- a template field line: `mode `, `budget `, `queue `, `disp `, `done `, `audit `, `ledger `,
  `next `, `act `, `gates `
- `⏸` (T5 park) · `⚖` (D7 policy line) · `⚠` (T6 deviation)
- a T6 rich-zone section (resolution briefing / verbatim sentinel block / echo-back) or the
  T7 report body

If the text you are about to type does not start with one of those, **do not type it**. There
is no sanctioned "transition sentence", no "reading X now", no "composing the dispatch", no
"preflight passed", no "sync clean". Run the tool calls back-to-back with nothing in between;
the next visible thing after the silent mechanics is the template block itself.

## Principles

1. **Mechanics are silent.** Probe parsing, git guards, loop-guard evaluation, template/component
   re-reads, flag handling, signature bookkeeping — execute them; never narrate them. Silence
   means "the machinery worked".
2. **Rules are cited only on deviation.** Name a HARD CONSTRAINT, discipline, or step number
   ONLY when reporting a violation, refusal, or recovery. Compliance is never announced.
3. **Declarative, past-tense.** No future-tense self-narration ("Now I will compose the
   dispatch…", "Entering the cycle loop"). The templates below say what happened, not what is
   about to happen.
4. **Never restate probe JSON in prose.** The cycle block's fields carry `feature_id` /
   `sub_skill` / step / `parked[]`; a sentence repeating them is noise.
5. **Every turn matches exactly one template below.** Freeform prose is permitted only inside
   the rich zones (T6/T7), and there only within their stated budgets.

## Hard bans (anti-patterns observed in real runs — all are zero-text-rule violations)

- "Per the compaction discipline, I must re-read…" — do it silently.
- "No loop-guard fires (first cycle, prev_cycle_signature is None)." — silence = no fire.
- "Entering the cycle loop." / "Now composing the spec-bug dispatch…"
- "Probe returned real work — bug X, step Y, sub_skill Z, no terminal reason…" — that is the
  cycle block's job.
- "Reading the canonical cycle base prompt I must bind…" — narrated file reads.
- "I'll start by running the environment preflight as required before anything else."
- "Preflight passed (FAIL=0). Now I'll read the required run-start contracts…"
- "Let me read the Step 0.4 remote-sync section:" / "Now the cycle base prompt template:"
- "Sync clean. Printing the run-start banner and entering the cycle loop."
- "Real work returned — execute-plan for X (Step 7a), no terminal, repeat_count=1 (no loop).
  Reading the dispatch template…" — the T2 block carries ALL of this.
- "Composing the dispatch. This is an execute-plan cycle (not mcp-test…). First cycle, no
  loop-guard. Model: opus." — every fact here is either silent mechanics or a `disp` field.
- "Cycle returned: plan Complete / PHASES In-progress… Running the post-execute-plan
  ledger-consistency guard:" — the T3 `done`/`ledger` lines carry this; run the guard silently.
- "Ledger clean. Emitting the cycle return block." — never announce a template; just emit it.
- "forward_cycles = 1. Next probe:" — counter bookkeeping is silent; it shows in the heading.
- "Retro phase next — retro-feature for the same bug. No loop (step advanced). Dispatching."
  — that is the T3 `next` line + the next T2 heading, nothing more.

## Turn templates

### T1 — Run start (once, after silent preflight)

```
## /lazy-bug-batch — run start
mode   workstation · park on · research strict
budget fwd 6 · meta 12
queue  4 bugs · first: track-path-filestream-source-silent
```

≤4 lines. A preflight FAILURE is a rich zone (T6-error: recipe printed in full).

### T2 — Cycle dispatch (every forward or meta cycle)

```
### Plan — author PHASES + implementation plan for the silent FileStream source [2/6]
disp   plan-bug → track-path-filestream-source-silent (opus)
```

Heading format: `### {Step name} — {work summary, ≤12 words} [{n}/{max}]`.

- **Step name** — the human-readable pipeline step being advanced to. Canonical names:
  `Spec` (spec) · `Investigate` (spec-bug) · `Plan` (plan-feature / plan-bug / spec-phases /
  write-plan) · `Implement` (execute-plan) · `Retro` (retro / retro-feature) ·
  `Validate` (mcp-test) · `Realign` (realign-spec) · `Research` (ingest-research) ·
  `Mark Complete` / `Mark Fixed` (the terminal pseudo-skills). Derive an equally plain name
  for anything new.
- **Work summary** — one clause saying what THIS cycle is about to do, specific to the item
  ("implement plan part 2 of 3", "real-device validation of the resize scenario"), not a
  restatement of the step name.
- **Counter** — forward cycles: `[2/6]`. Meta cycles: `[meta 1/12]`. Both counters are still
  tracked per D3 and both appear in the T7 final report; the heading shows only the counter
  this cycle consumes.

`disp` carries sub-skill, target, model, and — only when applicable — a trailing tag:
`(sonnet, loop-resolution)` / `(opus, recovery)`. Nothing else before the Agent call.

### T3 — Cycle return (when the subagent's result is processed)

```
done   9m · PHASES.md (4 phases) + plan Ready · 0 decisions
audit  RED→GREEN 33/33 · gates qg:ts green          ← execute-plan cycles only (Step 1e audit signal)
ledger clean · pushed
next   execute-plan
```

`done` is ONE line: duration + the load-bearing outcome (artifact written / verdict / counts).
The old 3–5-bullet cycle summary is retired — details live in the commit and the docs the
subagent wrote. `audit` appears only where Step 1e requires the audit-signal line. `ledger`
states the post-cycle guard outcome (`clean · pushed` when healthy; anything else is a T6
deviation). `next` is the fresh probe's routing (or `terminal: <reason>`).

### T4 — Inline pseudo-skill / completion gates

```
### Mark Fixed — gate + archive the e2e bridge bug [5/6]
act    __mark_fixed__ → e2e-no-tauri-event-bridge
gates  G1 pass (4/4 covered) · G2 pass
done   FIXED.md (gated) · archived · 16 refs repointed · a1b2c3d
next   probe
```

Same heading format as T2 (step name — work summary — counter).

A gate REFUSAL switches to T6-refusal (rich) — the refusal evidence and the NEEDS_INPUT routing
deserve full detail.

### T5 — Park event (single line; fires with the PushNotification)

```
⏸ parked track-filestream-default-root — 1 decision · notified (2 parked this run)
```

### T6 — Rich zones (full detail sanctioned; structure fixed, framing capped)

- **Resolution briefings (Step 1g/1h/1i and flush):** fixed order — (1) ≤2-sentence situation
  line, (2) the verbatim sentinel body (UNCHANGED — the Zero-Context Operator Briefing and
  verbatim re-print requirements stand in full), (3) the option set exactly matching the
  upcoming AskUserQuestion. No other prose around them.
- **Errors / deviations / refusals / recoveries:** `⚠ <symptom>` line → evidence (quoted
  output, ≤10 lines) → action taken → the rule violated, cited here and only here.
- **Standing-directive echo-back:** the interpretation being confirmed, verbatim, then the
  AskUserQuestion.

### T7 — Final report

Keep the required content (cycle table, per-item outcomes, parked + auto-accept digest,
terminal reason, explicit next step) — tables carry the data; framing prose ≤2 sentences total.

## Precedence

Where an older skill passage prescribes chat output that conflicts with these templates (e.g. a
"3–5-line cycle summary", a "▶ Cycle N (dispatched)" line, or one-sentence announcements of
mechanics), THIS contract wins. Verbatim-re-print and briefing requirements (HARD CONSTRAINT 6,
decision-resume, blocked-resolution, parked-flush) are rich zones and are never overridden.
