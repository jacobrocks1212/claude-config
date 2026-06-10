# Lazy Family — Step 0 Environment Preflight

**Runs FIRST — before the start banner and before any remote sync (Step 0.4) or state probe.**
Its job: catch the environment faults that have left `/lazy*` sessions dead-on-arrival (missing
skill/script symlinks, no `python3`, node off PATH) BEFORE a single cycle is spent. On any failed
check it prints the setup recipe and STOPS — **zero cycles consumed** (no `lazy-state.py`/`bug-state.py`
call, no start banner, no loop entry).

## Why this exists
On 2026-06-10, 2 of 7 Windows sessions were DOA on missing symlinks / missing `python3`, and node-PATH
hunts cost 7 wasted probes. This preflight converts those silent multi-cycle deaths into one actionable
message printed before any work begins.

## Checks (one read-only Bash block; run from the repo cwd)
The state-script check depends on the pipeline: use `lazy-state.py` for `/lazy-batch`, `/lazy`,
`/lazy-batch-cloud`, `/lazy-cloud`; use `bug-state.py` for `/lazy-bug-batch`, `/lazy-bug`.

```bash
FAIL=0
# 1. Skills symlink resolves (the skill can find its own _components)
test -e ~/.claude/skills/_components || { echo "PREFLIGHT FAIL: ~/.claude/skills does not resolve"; FAIL=1; }
# 2. State script resolves (swap lazy-state.py -> bug-state.py for the bug pipeline)
test -e ~/.claude/scripts/lazy-state.py || { echo "PREFLIGHT FAIL: ~/.claude/scripts/lazy-state.py missing"; FAIL=1; }
# 3. python3 runs (the state scripts are python3)
command -v python3 >/dev/null 2>&1 || { echo "PREFLIGHT FAIL: python3 not found"; FAIL=1; }
# 4. node resolvable — bake the known Windows Git-Bash home so no per-call export is needed
command -v node >/dev/null 2>&1 || export PATH="/c/nvm4w/nodejs:$PATH"
command -v node >/dev/null 2>&1 || { echo "PREFLIGHT FAIL: node not found (tried /c/nvm4w/nodejs)"; FAIL=1; }
echo "PREFLIGHT: FAIL=$FAIL"
```

## Node path (baked — no more per-call `export PATH`)
The known node homes, baked here so the per-call `export PATH` boilerplate disappears for the rest of
the session:
- **Windows Git-Bash:** `/c/nvm4w/nodejs` (contains `node.exe`)
- **WSL:** the nvm path under `~/.nvm/versions/node/<ver>/bin`, restored via `BASH_ENV` →
  `<claude-config>/user/scripts/claude-bash-env.sh` (per AlgoBooth `CLAUDE.md` "WSL PATH note").

Check 4 prepends the Windows home when `node` is absent, so the orchestrator never hunts for it again.

## On failure (`FAIL=1`) — print this recipe verbatim and STOP (zero cycles)
Do NOT print the start banner, do NOT call the state script, do NOT enter the loop. The run consumed
zero cycles.

```
## /lazy* — Environment preflight FAILED — run aborted (0 cycles)

One or more preconditions are missing. Fix and re-invoke.

Symlinks (the claude-config repo is the source of truth):
  - Windows: from the claude-config repo run   .\setup.ps1 repair
    (recreates ~/.claude/{skills,scripts} + per-repo .claude/ links)
  - Or recreate by hand (per AlgoBooth CLAUDE.md "Claude Code Config"):
      ln -s <claude-config>/user/skills    ~/.claude/skills
      ln -s <claude-config>/user/scripts   ~/.claude/scripts
      ln -s <claude-config>/repos/algobooth/.claude/skills        .claude/skills
      ln -s <claude-config>/repos/algobooth/.claude/skill-config  .claude/skill-config
    claude-config repo path:
      Windows (Jacob laptop):  C:\Users\Jacob\source\repos\claude-config
      Windows (JacobMadsen):   C:\Users\JacobMadsen\source\repos\claude-config
      WSL:                     ~/repos/claude-config
python3:
  - Install Python 3 and ensure `python3` is on PATH (the state scripts are python3).
node:
  - Windows Git-Bash: node lives at /c/nvm4w/nodejs (already baked into this preflight).
  - WSL: ensure BASH_ENV points at <claude-config>/user/scripts/claude-bash-env.sh (restores nvm node + cargo).
```

## On success
All checks passed → continue to the start banner / Step 0.4 remote sync as normal. Node is now on PATH
for the whole session — no per-call `export PATH` needed.
