---
name: link-provenance
description: Manually link out-of-pipeline work (teammate PR, hotfix range) into the provenance ledger through lazy-state.py --link-provenance — never hand-writes IMPLEMENTED.md or the provenance index.
argument-hint: --id <slug> (--commits <A..B> | --pr <n>)
plan-mode: never
model: sonnet
allowed-tools: ["Bash", "Read", "Write", "Grep", "Glob", "AskUserQuestion"]
---

# Link Provenance — manual trigger of the one-writer producer

The provenance ledger (`IMPLEMENTED.md` distillates + the committed per-repo reverse index
`docs/provenance-index.json`) is normally a byproduct of the `__mark_complete__`/`__mark_fixed__`
completion gate. Work that never crosses a completion gate — a teammate's PR merged from GitHub, an
out-of-band hotfix, pre-pipeline history — is linked through THIS skill, which drives the SAME
producer (`lazy_core.write_provenance` via the `--link-provenance` CLI). One writer, two triggers
(SPEC `code-doc-provenance-linkage` D1-B): never author the distillate or index by hand — a
hand-written entry forks the index into pipeline-shaped vs manual-shaped rows.

**Both state scripts expose the identical CLI** (`lazy-state.py` / `bug-state.py` — shared
`lazy_core` implementation); use `lazy-state.py` by convention.

## Inputs

- `--id <slug>` (required): the decision-record id. An existing `docs/features/<slug>/`,
  `docs/bugs/<slug>/`, or `docs/bugs/_archive/<slug>/` dir is used when present; otherwise the
  producer creates a **minimal decision-record dir** `docs/features/<slug>/` with the distillate as
  its primary doc — NEVER invent a fake SPEC.md for unspecced work.
- Addressing (exactly one):
  - `--commits <A..B>` — commit-range primary.
  - `--pr <n>` — sugar; the producer resolves it via `gh pr view <n> --json baseRefOid,headRefOid`.
    When `gh` is absent or unauthenticated the CLI refuses cleanly and names the `--commits`
    fallback — resolve the range yourself (`git log`, the PR page) and re-run with `--commits`.

## Procedure

1. **Derive first, write nothing.** Run the producer's dry run and show the operator the derived
   touched-file set + commit list VERBATIM:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py --link-provenance --id <slug> \
       --commits <A..B> --dry-run --repo-root <repo>
   ```

   An unresolvable range aborts here with the producer's refusal text — surface it and stop
   (nothing is half-written; atomic writes throughout). If the file set looks wrong (e.g. the range
   swept unrelated commits), fix the range, not the output.

2. **Draft the distillate body.** From the PR description + review thread (`gh pr view <n>
   --json title,body` / `--comments`) or, when no PR exists, the range's diff and commit messages,
   draft the body prose: what shipped and why, in a few sentences. The deterministic parts — the
   frontmatter (`kind: implemented`, `provenance: manual`, `linked_by`, `derivation: commit-range`,
   `commits:`, `decisions:`) and the index rows — are producer-owned and NEVER come from you.

3. **Approve.** Present the derived file set and the drafted body via `AskUserQuestion`
   (approve / edit / abort). On "edit", apply the operator's changes and re-present.

4. **Write through the producer.** Save the approved body to a temp file and run the real link:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py --link-provenance --id <slug> \
       --commits <A..B> --body-file <approved-body.md> --repo-root <repo>
   ```

   Exit 1 = the producer refused (its JSON `refused` field says why) — surface it verbatim; do not
   work around it. Re-linking the same id later REPLACES that item's rows (idempotent, no
   duplicates).

5. **Commit.** Stage exactly the producer's `wrote` list (`docs/<pipe>/<slug>/IMPLEMENTED.md`,
   `docs/provenance-index.json`) and commit:
   `docs(<slug>): link provenance (manual, <A..B> | PR #<n>)`. Follow the repo's commit/push
   policy; in work repos let the operator push.

## Hard rules

- NEVER write `IMPLEMENTED.md` or `docs/provenance-index.json` with Write/Edit — only the producer
  CLI writes them.
- NEVER run this from inside a `/lazy*` cycle — the CLI is cycle-guarded (`refuse_if_cycle_active`,
  exit 3) like every other operator-only mutation.
- The body is the ONLY LLM-drafted part, and only after explicit operator approval; the frontmatter
  records the attribution (`provenance: manual`, `linked_by`).
- Verify after writing: `python3 ~/.claude/scripts/lazy-state.py --provenance-lookup <one-touched-file>
  --repo-root <repo>` should list the new id.
