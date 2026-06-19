# Implementation Phases — Windows path & line-ending portability defects (probe glue / validators)

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Fixed

**MCP runtime:** not-required — docs/harness-prose + hook-config bug. No app-reachable surface: the fix loci are `/lazy-batch` probe-glue prose, the coupled `/lazy-batch-cloud` prose, and a PostToolUse hook-registration decision in `user/settings.json`. None of these is observable through the AlgoBooth MCP server (no store, audio, UI, or IPC surface). Validation is by `lint-skills.py` / `project-skills.py` + grep assertions over the edited prose, not `/mcp-test`.

## Validated Assumptions

All load-bearing assumptions for this bug are **code-provable** (prose content, hook-registration presence, file behavior) — no runtime-coupled assumptions, so the Runtime Assumption Validation gate is skipped with this recorded reason. Ground truth confirmed during planning's touchpoint audit:

- **Symptom A locus (verified by grep):** the probe-glue prose lives in EXACTLY TWO files — `user/skills/lazy-batch/SKILL.md` (line ~400) and its coupled pair `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (line 323). `/lazy`, `/lazy-cloud`, `/lazy-bug`, `/lazy-bug-batch` do **NOT** carry the "redirect probe or diagnostic output into the repo tree" / "OS temp dir" guidance (grep returned zero hits in them). This resolves SPEC Open Question 2: the Symptom-A sweep is the coupled pair only, not the whole lazy family.
- **Symptom A prose text (verified by Read):** lazy-batch reads `… write to the OS temp dir (`$TMPDIR` / `%TEMP%`) if you must capture it.`; lazy-batch-cloud reads `… write to the OS temp dir if you must capture it (doubly important under cloud, where stray repo files get committed + pushed).` Both permit a temp file, neither forbids a `/tmp/...` path, and the probe already prints JSON to stdout (so the temp round-trip is unnecessary).
- **Symptom B secondary locus (verified by Read):** `user/settings.json` `PostToolUse` is `[]` — `fix-line-endings.ps1` is NOT registered (CLAUDE.md documents it as a PostToolUse hook; the registration is absent). The script itself (`user/scripts/fix-line-endings.ps1`) normalizes TO CRLF (`-replace "`n", "`r`n"`), i.e. it ADDS `\r`.
- **Symptom B primary locus (out-of-repo):** the failing field validators are in AlgoBooth's `scripts/check-docs-consistency.ts` (splits frontmatter on `\n` only, leaving a trailing `\r`). That fix CANNOT land in claude-config — it is spun off / cross-referenced (Phase 3).

## Cross-feature Integration Notes

No hard deps on Complete upstreams (this is a harness bug, not a feature with a `**Depends on:**` block). Omitted.

---

### Phase 1: Harden the probe-glue prose (Symptom A) — coupled-pair lockstep

**Scope:** Replace the under-specified temp-capture guidance in BOTH `/lazy-batch` and `/lazy-batch-cloud` so the orchestrator never round-trips the probe through a POSIX `/tmp/` path that crashes on Windows-native Python read-back. The probe already emits JSON to stdout, so the canonical guidance is **in-band capture** (consume stdout directly: `$(python3 … )` / pipe to the consumer) and NEVER a temp-file round-trip; if a temp file is genuinely unavoidable, mandate a path produced and read by the SAME interpreter (`mktemp` consumed by the same shell, or `%TEMP%` resolved by the same Windows Python) — never a hardcoded/idiomatic `/tmp/...`.

This is a **coupled-pair edit** (`user/skills/lazy-batch/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`): per the claude-config CLAUDE.md coupling rule, both files MUST be edited in lockstep and diffed against each other immediately afterward. The cloud variant keeps its "doubly important under cloud" framing; only the temp-capture instruction changes.

**Deliverables:**
- [x] Edit `user/skills/lazy-batch/SKILL.md` (~line 400): replace the `Never redirect probe or diagnostic output into the repo tree — write to the OS temp dir (`$TMPDIR` / `%TEMP%`) if you must capture it.` sentence with guidance that (a) forbids redirecting probe/diagnostic output into the repo tree (unchanged intent), (b) mandates in-band stdout capture as the default (no temp file), and (c) if a temp file is unavoidable, forbids `/tmp/...` and requires an interpreter-consistent portable path.
- [x] Edit `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (line 323): mirror the same Symptom-A fix, preserving the cloud-specific "doubly important under cloud, where stray repo files get committed + pushed" framing.
- [x] Diff the two edited sentences against each other and confirm the only divergence is the cloud framing (coupled-pair lockstep check, per CLAUDE.md).
- [x] Tests: grep assertions — `redirect probe or diagnostic output into the repo tree` still present in both files; the new in-band / no-`/tmp` guidance present in both; the old bare `OS temp dir (`$TMPDIR` / `%TEMP%`) if you must capture it` permissive phrasing no longer the operative instruction.

**Minimum Verifiable Behavior:** `python3 ~/.claude/scripts/lint-skills.py` exits 0 over both edited skills (no broken injections / embedded-pattern regressions), AND a grep confirms the new guidance text is present in both files and the old permissive phrasing is gone. (This is a prose change in LLM-improvised glue — there is no runnable probe path to assert; the deterministic check is the lint + grep over the edited text.)

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — probe-glue prose at ~line 400 (the Step 1a `--repeat-count` paragraph's trailing temp-capture sentence).
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — coupled-twin prose at line 323.

**Testing Strategy:** Run `lint-skills.py` (and `project-skills.py` to confirm the projection still expands cleanly). Grep both files for the new and old phrasings. Manual read-back of the two edited sentences side by side to confirm lockstep.

**Integration Notes for Next Phase:**
- The coupling rule (CLAUDE.md → "Coupled Skill Pairs") is load-bearing: any future edit to one of these two files' probe-glue prose must mirror the other. The Phase-1 edit establishes the canonical "in-band capture, no `/tmp`" phrasing both files now share.
- Phase 2 (settings/hook) is independent of Phase 1 — no shared files. They can land in either order but are kept in one bug for one fix receipt.

---

### Phase 2: Resolve the `fix-line-endings.ps1` hook-wiring gap (Symptom B secondary, claude-config side)

**Scope:** Close the documented-but-unwired gap: CLAUDE.md lists `fix-line-endings.ps1` as a PostToolUse hook, but `user/settings.json` `PostToolUse` is `[]`. The SPEC's secondary claude-config finding is to wire it OR confirm the registration belongs elsewhere.

**⚖ Scope note (D7 — resolved in-plan, not a NEEDS_INPUT):** the naive "just register the hook" path is a **trap the SPEC itself flags** (line 50): `fix-line-endings.ps1` normalizes TO CRLF (adds `\r`), which is *exactly* what AlgoBooth's `\n`-only TS parser (Symptom B primary) then trips on. Wiring a CRLF-adding PostToolUse hook globally would not reduce — and could increase — `\r`-bearing writes reaching the AlgoBooth validator. The options do NOT differ in user-visible product behavior (this is harness config, not an app surface), so per the completeness-first policy this is scope-class, resolved in-cycle:

> ⚖ policy: wire CRLF hook vs document gap → reconcile the doc to reality (do NOT blind-wire a `\r`-adding hook against a `\n`-intolerant downstream)

The executor implements the **reconcile** path: make `user/settings.json` and the CLAUDE.md hook table agree on the actual state, and record that the real Symptom-B mitigation is the AlgoBooth-side `.trim()` (Phase 3), NOT a global CRLF-adding hook. The executor decides between (2a) registering the hook scoped so it does not feed CRLF into the docs-consistency path, or (2b) correcting the CLAUDE.md hook table to stop claiming an unwired/counterproductive registration and recording the rationale — whichever leaves settings.json and the docs internally consistent. Either way the end state is: no documentation claims a hook that is both absent AND counterproductive, and the `\r`-source reduction story points at Phase 3.

**Deliverables:**
- [x] Reconcile `user/settings.json` `PostToolUse` and the CLAUDE.md / `user/CLAUDE.md` hook table so they agree on the actual wiring state of `fix-line-endings.ps1` (no doc claims an unwired hook; no hook is wired in a way that worsens Symptom B).
- [x] Record (in the bug's PHASES Implementation Notes and/or the relevant CLAUDE.md) that the CRLF-add behavior of `fix-line-endings.ps1` is the reason a naive global registration is NOT the fix, and that the primary `\r`-tolerance fix is AlgoBooth-side (Phase 3 cross-reference).
- [x] Tests: if `settings.json` is edited, assert it remains valid JSON (`python3 -c "import json,sys; json.load(open(...))"`); grep the hook table and settings to confirm they are consistent (no doc claims a registration that settings.json lacks, unless the registration is added).

**Minimum Verifiable Behavior:** `python3 -c "import json; json.load(open('user/settings.json'))"` exits 0 (settings.json stays valid JSON), AND a grep cross-check confirms the CLAUDE.md hook table and `settings.json` `PostToolUse` agree on `fix-line-endings.ps1`'s state (both claim it wired, or both reflect it unwired with the recorded rationale).

**Prerequisites:** None (independent of Phase 1).

**Files likely modified:**
- `user/settings.json` — `PostToolUse` array (currently `[]`) — only if the reconcile path registers the hook.
- `CLAUDE.md` (project) and/or `user/CLAUDE.md` — the Hooks table claiming `fix-line-endings.ps1` is a PostToolUse hook — corrected to match reality if the hook is left unwired.

**Testing Strategy:** Validate `settings.json` parses as JSON after any edit. Grep both the settings file and the CLAUDE.md hook tables to confirm internal consistency. No runtime hook firing is asserted (that would require driving a real Write/Edit through the live hook host — out of scope for a docs/config reconcile; the behavior of the script itself is unchanged).

**Integration Notes for Next Phase:**
- This phase deliberately does NOT attempt to fix Symptom B's *primary* cause (the `\n`-only TS validator) — that is out-of-repo (Phase 3). The claude-config-side deliverable is bounded to the hook-wiring gap + the doc reconcile.

---

### Phase 3: Spin off / cross-reference the AlgoBooth-side validator fix (Symptom B primary, out-of-repo)

**Scope:** Symptom B's PRIMARY fix — making `scripts/check-docs-consistency.ts` `.trim()` / strip trailing `\r` from each frontmatter value before field-type checks — lives in the **AlgoBooth repo**, NOT claude-config. It cannot land in this repo. Per the SPEC's Open Questions and the spin-off-leg contract (both-directions cross-reference is mandatory), this phase records the out-of-repo follow-up so it is not lost, with a reverse-reference back to this bug.

**⚖ Scope note (D7):** the SPEC offers two dispositions — (a) spin off an AlgoBooth-branch work item, or (b) document it as an out-of-repo follow-up in the PHASES Implementation Notes. These do not diverge in product behavior (the claude-config repo cannot enact either fix; both are bookkeeping that points a future AlgoBooth session at the real fix). Most-complete in-cycle:

> ⚖ policy: spin-off vs doc-only for AlgoBooth fix → document the out-of-repo follow-up here (no AlgoBooth queue reachable from this repo's bug pipeline)

The executor implements disposition (b): a clearly-scoped, copy-pasteable follow-up record in this bug's documentation naming the exact AlgoBooth file, the exact fix (`.trim()` each frontmatter value before validation, mirroring claude-config's CRLF-safe `splitlines()`), and the evidence (the three field-validator error formats from the SPEC). If a reachable AlgoBooth bug queue exists at execution time, the executor MAY instead enqueue an `--enqueue-adhoc --type bug` item into the AlgoBooth `docs/bugs/queue.json` and cross-reference it — but the doc-only follow-up is the baseline that always lands.

**Deliverables:**
- [x] Author the out-of-repo follow-up record (in this bug's PHASES Implementation Notes, or a sibling `FOLLOWUP.md` under the bug dir) naming: target file `scripts/check-docs-consistency.ts` (AlgoBooth repo root), the fix (strip/`.trim()` trailing `\r` from each frontmatter value before date/enum/integer validation), and the convergence target (claude-config's `lazy_core.py::parse_sentinel` `splitlines()` CRLF-safe behavior).
- [x] Add a REVERSE-REFERENCE in this bug's PHASES Implementation Notes naming the out-of-repo follow-up (both-directions cross-reference contract).
- [x] Tests: grep this bug's docs to confirm the AlgoBooth follow-up record + reverse-reference are present.

**Minimum Verifiable Behavior:** A grep over this bug directory finds the AlgoBooth-side follow-up record (file path + fix description) AND the reverse-reference, satisfying the spin-off both-directions cross-reference contract. (No code is changed in this phase — it is a bookkeeping deliverable; the only verifiable artifact is the on-disk follow-up record.)

**Prerequisites:** None (independent; documents work that cannot land here).

**Files likely modified:**
- `docs/bugs/windows-portability-in-probe-glue-and-field-validators/PHASES.md` — Implementation Notes (the follow-up record + reverse-reference), or a sibling `FOLLOWUP.md` under the same bug dir.

**Testing Strategy:** Grep the bug directory for the AlgoBooth file name and the fix description. Confirm the reverse-reference names the spun-off/documented follow-up.

**Integration Notes for Next Phase:** Terminal phase. After Phases 1–3 land, the claude-config-side scope of this bug is complete; the only remaining work (AlgoBooth `check-docs-consistency.ts` `.trim()`) is explicitly recorded as out-of-repo.

---

## Implementation Notes

### Phase 1 — Harden probe-glue prose (coupled pair) — DONE 2026-06-19

- Replaced the permissive temp-capture sentence in BOTH coupled files with guidance that (a) keeps "never redirect probe/diagnostic output into the repo tree", (b) mandates IN-BAND stdout capture as the default (`result=$(python3 user/scripts/lazy-state.py … )` / pipe to consumer; no temp file), and (c) if a temp file is genuinely unavoidable, FORBIDS a bare POSIX `/tmp/...` path and requires a path produced AND read by the SAME interpreter (`mktemp`/same-shell or `%TEMP%`/same-Windows-Python).
- Files modified: `user/skills/lazy-batch/SKILL.md` (~L400), `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (L323).
- Coupled-pair lockstep verified: the two edited sentences diff identically except for the cloud-only `(doubly important under cloud, where stray repo files get committed + pushed)` framing — the single intended divergence (CLAUDE.md → "Coupled Skill Pairs").
- Gates green: `lint-skills.py` exit 0, `project-skills.py` re-projected cleanly, grep assertions confirm intent preserved + new guidance present + old permissive phrasing gone in both files.

### Phase 2 — Reconcile fix-line-endings.ps1 hook-wiring gap — DONE 2026-06-19

- Reconcile path chosen (D7 scope-class, ⚖ policy: wire CRLF hook vs document gap → reconcile the doc to reality). `user/settings.json` `PostToolUse` is `[]` — `fix-line-endings.ps1` was NEVER registered. Per-repo settings (`repos/cognito-forms/.claude/settings.json`, `repos/meridian-setup/.claude/settings.json`) use their own hooks, not these scripts.
- Corrected the project-root `CLAUDE.md` Scripts table (L161) and Hooks table (L184) rows for `fix-line-endings.ps1` to mark it **NOT registered**, with the recorded rationale: the script normalizes TO CRLF (ADDS `\r`), so a naive global PostToolUse registration would INCREASE — not reduce — `\r`-bearing writes reaching the `\n`-only AlgoBooth `check-docs-consistency.ts` validator (Symptom B primary). The doc now points the real `\r`-tolerance fix at the AlgoBooth-side `.trim()` (Phase 3).
- ⚖ policy: also correct adjacent identically-mis-documented `run-eslint.ps1` row → corrected in-cycle (same table, same defect class — both rows claimed an unwired user-level PostToolUse registration). Per-repo eslint/format is wired in repo-scoped settings (Cognito Forms `format-frontend.ps1`).
- Files modified: `CLAUDE.md` (project root, Scripts + Hooks tables). `user/settings.json` left unchanged (the reconcile is doc-to-reality, NOT registering a counterproductive hook). `user/CLAUDE.md` does not document these hooks, so no edit there.
- Gates green: `python3 -c "import json; json.load(open('user/settings.json'))"` exit 0; grep cross-check confirms the hook table and settings agree (both reflect unwired, rationale recorded).

### Phase 3 — AlgoBooth follow-up cross-reference — DONE 2026-06-19

- ⚖ policy: spin-off vs doc-only for AlgoBooth fix → documented the out-of-repo follow-up here (no AlgoBooth `docs/bugs/queue.json` reachable from this repo's bug pipeline — checked 2026-06-19, absent → doc-only disposition (b) is the baseline that lands).
- Authored **[`FOLLOWUP.md`](./FOLLOWUP.md)** in this bug dir: names target file `scripts/check-docs-consistency.ts` (AlgoBooth repo root), the fix (`.trim()` / strip trailing `\r` from each frontmatter value BEFORE date/enum/integer field-type validation), the three evidence error formats (`"2026-05-18\r"` date, `"lazy\r"` enum, `"11\r"`/`"13\r"` integer), and the convergence target (claude-config's CRLF-safe `lazy_core.py::parse_sentinel` `splitlines()` behavior).
- **REVERSE-REFERENCE (spin-off both-directions contract):** [`FOLLOWUP.md`](./FOLLOWUP.md) names THIS bug as its origin; this Implementation Notes block names FOLLOWUP.md as the spun-off record. Both directions present.

- **Out-of-repo follow-up (Symptom B primary):** the AlgoBooth `scripts/check-docs-consistency.ts` `.trim()`/`\r`-strip fix is authored as the doc-only follow-up record **[`FOLLOWUP.md`](./FOLLOWUP.md)** (Phase 3) — it CANNOT land in claude-config. This is the reverse-reference leg of the spin-off contract; `FOLLOWUP.md` names this bug as its origin.
- **Coupled-pair lockstep (Phase 1):** `user/skills/lazy-batch/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` must be edited together and diffed afterward (CLAUDE.md → "Coupled Skill Pairs").
- **D7 scope-class resolutions (no NEEDS_INPUT written):** Phase 2 (reconcile-vs-blind-wire) and Phase 3 (spin-off-vs-doc-only) are scope-class decisions — the options do not diverge in user-visible product behavior — resolved in-plan with `⚖ policy:` lines above, per the completeness-first standing policy.
