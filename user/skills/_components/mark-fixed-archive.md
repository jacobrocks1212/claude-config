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

The `__mark_fixed__` pseudo-action MUST be gated by the completion-integrity gate FIRST:

!`cat ~/.claude/skills/_components/completion-integrity-gate.md`

Run the gate (adapted for bugs) with `{spec_path}`, `{bug_id}`, and `{cloud}=false` (workstation)
or `{cloud}=true` (cloud). The gate verifies:
- PHASES.md has zero unchecked non-verification deliverables.
- At least one validation sentinel exists: `VALIDATED.md` OR `SKIP_MCP_TEST.md` OR (cloud-only)
  `DEFERRED_NON_CLOUD.md`.
- `RETRO_DONE.md` exists (retro ran).
- `DEFERRED_REQUIRES_DEVICE.md` is NOT present (device-deferral blocks completion).

The gate writes the **`FIXED.md` receipt** (`kind: fixed`, `provenance: gated`) — this is the
equivalent of the feature pipeline's `COMPLETED.md`. For bugs, the gate should use:
- `kind: fixed` (not `completed`).
- `validated_via`: `mcp` / `skip-mcp-test` / `deferred-non-cloud` per the validation sentinel.
- Body: paste the validation summary from `VALIDATED.md` / skip rationale / deferral note so
  evidence survives the sentinel deletion below.

If the gate returns `refused:<reason>`, write `NEEDS_INPUT.md` per the gate's refusal protocol,
print a one-line halt note, and STOP. Do NOT proceed to the archive steps.

**Won't-fix exception:** A bug whose SPEC `**Status:**` is `Won't-fix` is **receipt-EXEMPT** —
`bug-state.py` skips it unconditionally and it NEVER reaches `__mark_fixed__`. However, if the
operator manually invokes the archive flow for a Won't-fix bug (e.g. to clean up an old bug
directory), skip the FIXED.md write (no receipt, no gate) and proceed directly to the archive
steps below. Won't-fix bugs are still archived; they just carry no receipt.

---

### Algorithm (runs after the integrity gate returns `gated`)

At this point, `FIXED.md` has been written by the gate. Proceed:

#### Step 1: Update SPEC.md header lines

Edit `{spec_path}/SPEC.md`:
1. Change the `**Status:**` line to `Fixed` (bare canonical token).
2. Add a `**Fixed:** <YYYY-MM-DD>` header line immediately after (or update it if already present).
3. Add a `**Fix commit:** <sha>` header line after `**Fixed:**`. Use the most recent commit SHA at
   this point in the flow (before the archive commit; the archive commit SHA is known only after
   the `git mv` commits, so use the last feature-work commit SHA — it is the load-bearing evidence
   of when the fix landed).

These header lines must be in the SPEC's header block (the cluster of `**Key:**` lines near the
top, before the first `##` section).

#### Step 2: Delete cleared sentinels

Delete (remove) these sentinel files from `{spec_path}/` — their evidence is now folded into
`FIXED.md`:
- `VALIDATED.md`
- `RETRO_DONE.md`
- `DEFERRED_NON_CLOUD.md` (if present — cloud-deferred bugs that completed on workstation)

Keep these permanently (audit trail):
- `FIXED.md` (the receipt — written by the gate in the precondition step)
- `SKIP_MCP_TEST.md` (permanent waiver record)
- `MCP_TEST_RESULTS.md` (permanent test evidence)
- `plans/` directory and all plan files
- `NEEDS_INPUT_RESOLVED.md` (if a decision was resolved — keep as audit trail). NOTE:
  a resolved decision is neutralized by RENAME (`git mv NEEDS_INPUT.md
  NEEDS_INPUT_RESOLVED.md`), NOT a `kind:` frontmatter flip — `bug-state.py` keys the
  `needs-input` halt on the FILENAME `NEEDS_INPUT.md` (file existence), so a file still
  named `NEEDS_INPUT.md` re-fires the halt every probe regardless of its `kind:`. By the
  time `__mark_fixed__` runs, the Step 1g decision-resume should already have renamed it;
  if a stray `NEEDS_INPUT.md` remains, rename it before archiving.

#### Step 3: `git mv` the bug directory to `_archive/`

```bash
# Determine paths
bug_dir="{spec_path}"           # e.g. docs/bugs/cue-channel-audio-bleed
bug_id="{bug_id}"               # e.g. cue-channel-audio-bleed
archive_dir="docs/bugs/_archive"

# Ensure _archive/ exists
mkdir -p "${archive_dir}"

# Move the entire bug directory into the archive
git mv "${bug_dir}" "${archive_dir}/${bug_id}"
```

The `git mv` handles tracking the rename atomically so the git history of all files in the bug
directory is preserved (accessible via `git log --follow`).

**If the archive already contains a directory with the same name** (a duplicate ID), append a
`-archived-<YYYY-MM-DD>` suffix to resolve the collision:

```bash
git mv "${bug_dir}" "${archive_dir}/${bug_id}-archived-$(date +%Y-%m-%d)"
```

#### Step 4: Repoint inbound references (root-relative paths)

Search the repository for any file that references the old bug path and update it to the new
`_archive/` path.

**Algorithm:**
1. Compute the old path: `docs/bugs/{bug_id}/` (root-relative, starting from the repo root).
2. Compute the new path: `docs/bugs/_archive/{bug_id}/` (same root-relative anchor).
3. Search all Markdown files and CLAUDE.md files in the repo for occurrences of the old path:

   ```bash
   grep -rl "docs/bugs/{bug_id}/" . --include="*.md" 2>/dev/null
   ```

4. For each file found, replace all occurrences of the old root-relative path with the new one.
   Use a targeted find-and-replace (not a wholesale file rewrite) to avoid accidental edits.

**Path format rule:** Per `docs/bugs/CLAUDE.md`, all links between bug docs and the wider repo
MUST be root-relative (starting with `/` relative to the repo root, or a path from the repo root
with no `..` traversals). This is what makes them resolvable after a `git mv`. If any discovered
reference uses a relative path with `..` (a bug-internal relative link pointing outside its own
directory), surface it as a warning in the commit message but do NOT rewrite it (relative paths
inside a single bug directory survive the `git mv` intact; it is cross-directory relative paths
that break).

**Typical reference sites:**
- `docs/bugs/CLAUDE.md` (general notes / cross-references)
- `docs/bugs/queue.json` (the `spec_dir` field referencing the bug's directory slug)
- Other bug `SPEC.md` files that list this bug in a `**Depends-on:**` or related section
- `docs/features/*/SPEC.md` files that reference the bug as a related issue

**`queue.json` special handling:** If `docs/bugs/queue.json` contains an entry whose `spec_dir`
field matches `{bug_id}`, remove that entry from the `queue` array — the bug is no longer open,
so it has no place in the active queue. Do NOT add it to the archive section; the archive
sentinel (`FIXED.md` inside `_archive/{bug_id}/`) is the durable record.

#### Step 5: Commit

Stage all changes (the SPEC.md edits, sentinel deletions, the `git mv` archive, and any
reference repoints including `queue.json`) and commit in one atomic operation:

```bash
git add -A  # captures the mv, deletions, edits, and queue.json update
git commit -m "fix({bug_id}): mark fixed and archive — FIXED.md receipt gated"
```

Follow the project's commit policy (`.claude/skill-config/commit-policy.md` if present; otherwise
use the standard pattern above).

---

### Return status to the consumer

After the commit lands:
- Print a one-line confirmation: `✅ {bug_name} archived → docs/bugs/_archive/{bug_id}/`.
- Call the work-log step (`interview_work_log_append`) per the consumer skill's work-log protocol.

If any step fails (e.g. `git mv` collision unresolvable, reference repoint ambiguous), write
`{spec_path}/BLOCKED.md` (`blocker_kind: archive-failure`, description of the failure) and halt.
Do NOT leave the bug directory in a half-archived state — either complete all steps in one
transaction or roll back (restore the original directory structure from git) and surface the
blocker.

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
