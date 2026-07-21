# CLAUDE.md — _components/lazy-batch-prompts/

`cycle-base-prompt.md`, the `dispatch-*.md` family, and per-repo `cycle-prompt-addenda.md` are
assembled at probe time by `lazy_core.emit_cycle_prompt` (`user/scripts/lazy_core/dispatch.py`)
from `@section` blocks selected by pipeline × mode × skills × variant × park × host. The
assembled bytes are **dispatched VERBATIM** to a cycle subagent — nothing here is read by a
human first.

## THE CONTRACT

Because these bytes go straight to a subagent, they carry **imperative rules + load-bearing
marker literals ONLY**. Incident narrative, provenance, dated history, issue/round references,
and "here's why this rule exists" rationale do **not** belong in a dispatched prompt — that
context belongs in the SPEC / IMPLEMENTATION_NOTES / the harden-harness record. A harden round
documents WHY in docs; the prompt only tells the subagent WHAT to do.

**Mechanically enforced**, not just convention: the war-story lint in
`user/scripts/skill-size-ratchet.py` (reachable via `python3 user/scripts/lint-skills.py
--check-skill-size`, run in the gate battery) HARD-fails on incident-dated / "Live incident:" /
`ISSUE-N` / `Round-N` / bare `docs/{bugs,features}/<slug>` shapes within this template family,
plus a per-section byte ceiling (see below). This lint landed in Phase 2 of
`cycle-prompt-residual-deflation-and-bloat-guard`.

## `@section` grammar

Each block is fenced by a selector line:

```
<!-- @section <name> pipelines=<feature|bug|feature,bug> modes=<workstation|cloud|workstation,cloud> skills=<all|csv> [variant=…] [park=…] [hosts=…] -->
```

`emit_cycle_prompt` parses these markers, selects the sections matching the current dispatch
context, binds tokens, and concatenates. **Editing the OUTPUT template never forks the
emitter** — add/remove/adjust `@section` blocks in place; the selection algorithm itself lives
only in `lazy_core/dispatch.py`.

## Deflation playbook

Trim in place to terse verdict-rules. **Never externalize / reference-by-path** — a prose "go
read file X" mandate already failed in this exact prompt (the `phases-slice-scoped-reads`
precedent). Preserve semantic content; cut narrative, not rules.

## Preserved load-bearing literals

These must survive any deflation **verbatim**:

- Every `@section` selector line
- `WORKSTATION DISPATCH — LOAD-BEARING`
- Tokens `{cwd}` / `{work_branch}` / `{receipt_name}` / `{item_label}`
- The R5 chained-command form
- `git_safe_push`
- The `git add -A` ban
- `classify_conflict` / `conflict_kind: semantic` / `--park-provisional`
- `--verify-ledger` + `ok:true`
- `cycle-subagent-bg-gate-guard.sh`
- The `series_index` prerequisite-ordering algorithm

## Size ratchets

Two ceilings guard this dir, both in `skill-size-ratchet.py`:

- **Per-section byte ceiling** — one file/section at a time.
- **Assembled-profile ceiling** — the whole prompt as emitted for a given pipeline/mode/skill
  combination.

Re-lock a ceiling after a legitimate edit via `--lock-in <path>` (per-file/section) or
`--lock-in-profile <profile-id>` (assembled profile) — **never hand-raise** either baseline.

## Coupled-pair note

`cycle-base-prompt.md` is consumed by both `/lazy-batch` and `/lazy-bug-batch`, and its cloud
sections are selected the same way by `/lazy-batch-cloud`. The generated coupled SKILL.md
variants (`generate-coupled-skills.py`) reference this file's behavior by name — after editing
sections here, run `python3 user/scripts/generate-coupled-skills.py --check` to confirm no
derived skill's description of this file has drifted.
