---
kind: research-summary
feature_id: skill-usage-miner
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — skill-usage-miner

Codebase survey verifying every surface the SPEC names, done in the implementation lane before
writing PHASES.md. All anchors checked against the lane checkout at branch `lane/skill-usage-miner`.

## Verified surfaces (SPEC anchors)

| SPEC claim | Verified at | Status |
|------------|-------------|--------|
| `toolify-miner.py` `_iter_log_files(logs_dir)` — top-level + subagent `*.jsonl`, sorted, read-only | `user/scripts/toolify-miner.py:172-178` | ✓ exact — `rglob("*.jsonl")`, sorted, `is_file()` guard |
| `_normalize_call` elides values (unsuitable for skill-name extraction) | `user/scripts/toolify-miner.py:138-144` | ✓ — `tuple(sorted(inp.keys()))`, values dropped; this miner needs its own value-preserving extractor |
| Assistant-turn `tool_use` extraction shape (type=="assistant" → message.content list → block type=="tool_use") | `user/scripts/toolify-miner.py:181-209` (`_tool_calls_in_file`) | ✓ — also the malformed-line graceful-skip precedent (bare `continue` on `ValueError`/`TypeError`, `OSError` → return) |
| Hyphenated-module import pattern | `user/scripts/test_toolify_miner.py:44-52` | ✓ — `importlib.util.spec_from_file_location` + `sys.modules` registration before `exec_module` |
| `_dir_hash` read-only hash test to mirror | `user/scripts/test_toolify_miner.py:151-160` | ✓ — sha256 over sorted relative paths + bytes |
| Slash-command marker regex | `user/skills/mine-sessions/scripts/digest_sessions.py:125` | ✓ exact: `re.findall(r"<command-name>(/[\w:-]+)</command-name>", txt)` on user-turn text |
| Transcript anatomy (encoded-cwd project dirs; `<parent>/subagents/agent-*.jsonl`; per-line ISO `timestamp`; worktree-suffixed project dirs → substring matching) | `user/skills/mine-sessions/SKILL.md` ("Where session history lives", "Transcript record anatomy") | ✓ |
| `archived/CLAUDE.md` convention (move don't delete; `| Archived | Replaced by | When |` row) | `archived/CLAUDE.md` | ✓ — one existing row uses a short sha in the `When` column |
| Frontmatter contract (`<name>/SKILL.md` dispatcher, `name:` key) | `user/skills/CLAUDE.md` | ✓ — NOTE: `name:` is not always the first frontmatter key (e.g. `user/skills/commit/SKILL.md` has `description` first), so the parser must scan the whole frontmatter block |
| Hygiene findings exist in the live tree | `user/skills/` | ✓ all four: `sh.exe.stackdump` (530-byte file), `remotion` (symlink → `C:/Users/JacobMadsen/...`, dangling on Linux), `local-site/skill.md` + `teach/skill.md` (lowercase dispatcher; no `SKILL.md`) |
| `docs/features/unified-pipeline-orchestrator/toolify-bar.md` exists (cross-link target) | checked | ✓ |
| Exemplar artifact shapes | `docs/features/multi-repo-concurrent-runs/` (PHASES.md, plans/, SKIP_MCP_TEST.md) | ✓ read in full |

## Spec assumptions that drifted

- **Skill counts:** user-level is 83 as stated (89 top-level entries minus `CLAUDE.md`,
  `_components/`, and the four hygiene strays). Repo-scoped is **30, not 29**: algobooth has **3**
  (`lazy-batch-cloud`, `lazy-cloud`, `mcp-test`) not 2, cognito-forms has 27. All 30 carry a
  proper `SKILL.md`. Recorded in D4's Resolution; no design impact (the inventory is a glob).
- Nothing else the SPEC anchors had moved.

## Integration points

- **Read-only imports:** `_iter_log_files` from `toolify-miner.py` (D1). No change to the sibling.
- **No pipeline coupling:** the miner is never on the state-script compute path; no
  queue/marker/sentinel interaction; not wired into hooks or settings. Output is stdout / `--out`.
- **Docs rows to add (Phase 4):** `user/scripts/CLAUDE.md` files table, root `CLAUDE.md` scripts
  table, and a pointer in `user/skills/CLAUDE.md` to the audit tool.
- **Test-suite integration:** new `test_skill_usage_miner.py` mirrors `test_toolify_miner.py`
  (pytest-discoverable + self-contained `_TESTS` runner; stdlib-only).

## Environment notes (cloud lane)

- `~/.claude/projects` does not exist in this container — the **live-corpus run is
  workstation-deferred**; the lane demonstrates output against a fixture logs dir.
- Git IS available in the lane checkout, so the D3 age-gate command
  (`git log --follow --diff-filter=A --format=%cs -- <SKILL.md>`) was verified live
  (e.g. `user/skills/three-best-practices/SKILL.md` → `2026-04-24`).
- Determinism refinement adopted (recorded in D3's Resolution): the 30-day recency window anchors
  to the newest corpus timestamp, not wall clock, so saved reports are byte-stable.

## Locked baseline (from the SPEC's auto-accepted decisions)

1. D1 — sibling script `user/scripts/skill-usage-miner.py`, importlib reuse of the corpus walk.
2. D2 — two detectors counted separately (Skill-tool `tool_use`; slash `<command-name>` regex)
   with the standing Caveats block.
3. D5 — hygiene sweep lives in this report, not `lint-skills.py`.
4. D8 — archival proposals are ready-to-review text blocks (`git mv` + `archived/CLAUDE.md` row);
   NEVER executed.
5. D9 — stdlib-only, read-only, two-tree hash test (logs dir + skills tree).
