---
kind: research-summary
feature_id: cycle-prompt-environment-dialect
date: 2026-07-12
source: inline codebase recon (no Gemini research dispatched — the SPEC's cited counts are the
  session-transcript-mining evidence; this pass verifies the CODE surfaces the SPEC's design
  depends on before locking Phase 2/3 implementation)
---

# Research Summary — cycle-prompt-environment-dialect

Inline recon verifying every surface the SPEC's Technical Design section names, against the
lane base at commit `a547c716`.

## Verified surfaces

### `cycle-base-prompt.md` — sectioned template + grammar

- 644 lines pre-edit; `@section` marker grammar confirmed exactly as the SPEC describes:
  `_SECTION_MARKER_RE` in `lazy_core.py` (~L7058) parses
  `<!-- @section <name> pipelines=... modes=... skills=... -->`, with optional `variant=` and
  `park=` attribute tokens. `_parse_section_attrs` (~L7143) stores ANY `key=value` token
  generically (not a closed allow-list) — confirmed a new `hosts=` attribute parses today
  without a grammar change, exactly the `park=` precedent the SPEC's D2 cites.
- Confirmed **zero** `phases-slice` mentions pre-edit and the exact "walk {spec_path}'s
  PHASES.md" instruction at the RECONCILE PHASES step (was line 374, inside
  `skill-mcp-test-common`) — matches the SPEC's cluster (f) citation verbatim.
- Confirmed `--marker-status` does **not** exist in `lazy-state.py` today (grep: zero hits)
  and no `bug-state.py` parity — Phase 1 (SPEC D3) is a clean addition, not yet started.

### `emit_cycle_prompt` selection loop — where `hosts=` wiring lands

- `user/scripts/lazy_core.py::emit_cycle_prompt` (~L7316) parses the base template AND an
  optional per-repo addenda file (`.claude/skill-config/cycle-prompt-addenda.md`) through
  **two** near-identical selection loops (~L7397 base, ~L7446 addenda). The existing `park=`
  filter is duplicated in both (~L7418, ~L7462) — confirms a `hosts=` filter needs the SAME
  two-site edit (see this feature's report for the exact diff), not a single-site change.
- `os` is already imported at module scope (~L59) — `os.name == "nt"` is a zero-new-import
  host check.

### `phases-slice.py` CLI — exact invocation shape

- Verified the real CLI takes a **positional** `target` (a PHASES.md path or a feature dir
  containing one) plus `--phase <id>` (repeatable) — **no** `--repo-root` flag. The SPEC's
  Technical Design prose didn't spell out the exact flags; the authored env-dialect-core
  section and the RECONCILE-step edit both use the verified positional-`target` form
  (`phases-slice.py {spec_path} [--phase <id>]`), not a guessed `--repo-root` form.

### Coupled-pair blast radius — confirmed zero

- `grep -rl cycle-base-prompt` across every `SKILL.md` shows it is referenced **by pointer**
  (`~/.claude/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`) from
  `lazy-batch/SKILL.md`, `lazy-bug-batch/SKILL.md`, `lazy-batch-cloud/SKILL.md`, and
  `add-phase/SKILL.md` — none inline its content. `user/scripts/coupled-overlays/*.overlay.json`
  confirms the coupled-pair generator's `canonical`/`derived` pairs are all `user/skills/lazy*/SKILL.md`
  files, never this component. Editing `cycle-base-prompt.md` therefore cannot desync a
  coupled pair by construction — verified post-edit: `generate-coupled-skills.py --check` and
  `lazy_parity_audit.py --repo-root .` both exit 0 unchanged.

### Cluster (g) — AlgoBooth `MCP_USAGE_GUIDE.md` is NOT reachable from this workspace

- `grep -rn MCP_USAGE_GUIDE.md .` inside claude-config finds only **pointer references**
  (`repos/algobooth/.claude/skill-config/investigation-runtime.md`,
  `.../phases-runtime-validation.md`) — the file itself lives in the AlgoBooth repo, which per
  `~/source/repos/CLAUDE.md` is developed via **cloud sessions only** ("the live repo was
  deleted from this machine"). Phase 3's cluster-(g) deliverable cannot be authored from this
  session; it is recorded as an outstanding cross-repo follow-up requiring an AlgoBooth cloud
  session, not implemented here.

## Assumptions that proved correct

- The SPEC's byte estimates (~0.7KB core / ~0.9KB Windows) were close: authored sections
  measured 1,110 / 820 bytes — both comfortably under the 2,048-byte D4 budget.
- `_PROMPT_RESIDUE_RE` only flags `{lower_snake_or_digit}` tokens — the JSON-shaped literal
  `{"present": bool, ...}` written into the core section's prose does NOT trip the residue
  guard (verified: `{"` fails the `[a-z0-9_]` class immediately after `{`).

## Assumptions that proved wrong / needed correction

- None on the SKILLS-lane surface. The one correction was internal to this session's drafting
  (the first `phases-slice.py` invocation guessed a `--repo-root` flag that doesn't exist —
  caught and fixed before commit by reading the actual `argparse` block).
