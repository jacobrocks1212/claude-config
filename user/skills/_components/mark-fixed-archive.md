## Mark-Fixed Archive (inline, docs-only — terminal action for `__mark_fixed__`)

**Why this component exists.** Bug resolution has two distinct operations that feature completion
does not: a **receipt write** (FIXED.md) and a **physical archive** (`git mv` into `_archive/`).
Features are marked complete in-place on ROADMAP.md; bugs are retired by moving the entire spec
directory so the active `docs/bugs/` tree contains only open / in-progress bugs. This component
documents the exact procedure so every consumer (`/lazy-bug`, `/lazy-bug-batch`) performs it
identically.

The component is docs-only — it performs `git mv`, `git log`, and file edits inside `docs/bugs/`.
It does NOT touch source code, test files, or the feature pipeline.

---

### Precondition: Completion-Integrity Gate (MANDATORY — runs BEFORE this component)

The `__mark_fixed__` pseudo-action MUST be gated by the completion-integrity gate FIRST.

Run the completion-integrity gate documented in `~/.claude/skills/_components/completion-integrity-gate.md` (Read it now) with `kind: fixed`, `filename: FIXED.md`.

Run the gate (adapted for bugs) with `{spec_path}`, `{bug_id}`, and `{cloud}=false` (workstation)
or `{cloud}=true` (cloud). The gate verifies:
- PHASES.md has zero unchecked non-verification deliverables.
- At least one validation sentinel exists: `VALIDATED.md` OR `SKIP_MCP_TEST.md` OR (cloud-only)
  `DEFERRED_NON_CLOUD.md`.
- `RETRO_DONE.md` exists (retro ran).
- `DEFERRED_REQUIRES_DEVICE.md` is NOT present (device-deferral blocks completion).

On pass, the gate delegates the receipt write to the script — run
`python3 ~/.claude/scripts/bug-state.py --apply-pseudo __mark_fixed__ {spec_path}` per the
gate component. The script is the **sole author** of:
- the **`FIXED.md` receipt** (`kind: fixed`, `provenance: gated`) — the equivalent of the
  feature pipeline's `COMPLETED.md` — with `validated_via`: `mcp` (VALIDATED.md present) or
  `skip-mcp-test` (only SKIP_MCP_TEST.md present), and the validation evidence folded into the
  receipt body so it survives the sentinel deletion. (The script refuses when neither
  VALIDATED.md nor SKIP_MCP_TEST.md is present, so `validated_via` can never be a bare
  deferral.)
- the SPEC.md/PHASES.md `**Status:** Fixed` flip (first `**Status:**` line in each).
- the deletion of the consumed `VALIDATED.md` / `RETRO_DONE.md` / `DEFERRED_NON_CLOUD.md`
  sentinels.

The consumer skill MUST NOT hand-write the receipt, the status flip, or the sentinel
deletions — its job after the script returns is the archive mechanics below.

If the gate returns `refused:<reason>`, write `NEEDS_INPUT.md` per the gate's refusal protocol,
print a one-line halt note, and STOP. Do NOT proceed to the archive steps.

**Won't-fix exception:** A bug whose SPEC `**Status:**` is `Won't-fix` is **receipt-EXEMPT** —
`bug-state.py` skips it unconditionally and it NEVER reaches `__mark_fixed__`. However, if the
operator manually invokes the archive flow for a Won't-fix bug (e.g. to clean up an old bug
directory), skip the FIXED.md write (no receipt, no gate) and proceed directly to the archive
steps below. Won't-fix bugs are still archived; they just carry no receipt.

---

### Algorithm (runs after the integrity gate returns `gated`)

At this point, `bug-state.py --apply-pseudo __mark_fixed__ {spec_path}` (invoked by the gate
in the precondition step) has already written `FIXED.md`, flipped the SPEC.md/PHASES.md
`**Status:**` lines to `Fixed`, and deleted the consumed `VALIDATED.md` / `RETRO_DONE.md` /
`DEFERRED_NON_CLOUD.md` sentinels. Do NOT re-perform any of those writes.

**The archive mechanics are SCRIPT-OWNED** — one call performs everything that used to be
prose Steps 1–5 (`lazy_core.archive_fixed`, tested in `test_lazy_core.py`):

```bash
python3 ~/.claude/scripts/bug-state.py --repo-root {repo_root} --archive-fixed {spec_path}
```

The script (sole author — do NOT hand-perform any of these):
1. Adds the SPEC.md evidence header lines — `**Fixed:** <date>` + `**Fix commit:** <short sha
   of the last work commit>` — after `**Discovered:**` (canonical field order per
   `docs/bugs/CLAUDE.md`), updating them if already present. Skipped for Won't-fix (no receipt
   → no fix-commit evidence).
2. Stages the bug dir (`git add -A {spec_path}`) so apply_pseudo's **unstaged sentinel
   deletions** can't break the move (tracked-but-missing files inside a dir make `git mv` fail
   — the 2026-06-10 incident).
3. `git mv`'s the directory to `docs/bugs/_archive/{bug_id}` with retry/backoff (1s/2s/4s —
   transient Windows handle locks) and a per-file `git mv` fallback that isolates a single
   locked file. A name collision in `_archive/` gets a `-archived-<date>` suffix; inbound
   refs then repoint to the actual suffixed destination.
4. Repoints inbound references: `git grep -l` (tracked files only — never node_modules/target)
   for `docs/bugs/{bug_id}/` across `*.md`, replacing with the archive path. Root-relative
   links (the `docs/bugs/CLAUDE.md` HARD format rule) are what make this a pure string
   substitution; bug-internal relative links survive the move untouched.
5. Removes the bug's `docs/bugs/queue.json` entry (matched on `spec_dir` or `id`).
6. Commits everything atomically: `fix({bug_id}): mark fixed and archive — FIXED.md receipt
   gated`.

The call is idempotent and resume-safe: a re-run after success is a `noop`; a re-run after a
partial failure (e.g. the mv landed but the commit didn't) resumes from the archive
destination instead of redoing the move.

**Receipt-keeping reference** (what the two script calls leave on disk):
- Gone (deleted by `--apply-pseudo __mark_fixed__`): `VALIDATED.md`, `RETRO_DONE.md`,
  `DEFERRED_NON_CLOUD.md` (their evidence is folded into `FIXED.md`).
- Kept permanently (audit trail): `FIXED.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`,
  `plans/`, `NEEDS_INPUT_RESOLVED_<date>.md`. NOTE: a resolved decision is neutralized by
  RENAME to `*_RESOLVED_<date>` (`bug-state.py --neutralize-sentinel
  {spec_path}/NEEDS_INPUT.md`), NOT a `kind:` flip — `bug-state.py` keys the halt on the
  FILENAME. If a stray `NEEDS_INPUT.md` remains, neutralize it BEFORE the archive call.

---

### Return status to the consumer

The script prints a JSON result (`ok` / `refused` / `archived_to` / `committed` / …) and exits
non-zero on refusal.

On `ok: true`:
- Push the archive commit (`git push origin $(git rev-parse --abbrev-ref HEAD)`, 4× backoff
  retry on network error; work branch only, never main, never force).
- Print a one-line confirmation: `✅ {bug_name} archived → {archived_to}/`.
- Call the work-log step (`interview_work_log_append`) per the consumer skill's work-log protocol.

On `ok: false`: write `{spec_path}/BLOCKED.md` (`blocker_kind: archive-failure`, quoting the
script's `refused` diagnostic verbatim) and halt. If the diagnostic says PARTIAL STATE, do NOT
hand-unwind anything — the next `--archive-fixed` call resumes from where it stopped.

---

### Coupling note

Consumed by `__mark_fixed__` in the bug-pipeline skills:
- `user/skills/lazy-bug/SKILL.md` Step 3 `__mark_fixed__`
- `user/skills/lazy-bug-batch/SKILL.md` Step 1c.5 `__mark_fixed__`

When editing this component, run:
```bash
grep -rn "mark-fixed-archive.md" ~/.claude/skills/ ~/.claude/skills/_components/ --include="*.md"
```
to confirm the blast radius matches the two files above.
