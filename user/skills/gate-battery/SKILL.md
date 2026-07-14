---
name: gate-battery
description: Run a repo's manifest-declared gate battery (build/lint/test commands) via the stdlib-only cross-platform runner and trust its single last-line outcome banner. Triggers on "run the gates", "run the battery", "gate battery", "invariant battery", "run the invariant tests".
argument-hint: [--repo-root <path>] [--await <run-id>]
model: haiku
allowed-tools: ["Bash"]
---

# Gate Battery — Generic Trust-the-Banner Runner

Runs the manifest-declared gate battery for a repo via `gate-battery.py` — the stdlib-only,
cross-platform (cloud-capable) half of the **Runner-Outcome Contract**
(`~/.claude/skills/_components/runner-outcome-contract.md`, the SSOT for the banner grammar,
the followable-await semantics, and the never-pipe-through-tail rule). It is a **light op**: no
build-queue coupling, no PowerShell, no serialization — it runs directly, in this session.

## Usage

- `/gate-battery` — run the battery for the current repo (`--repo-root` defaults to cwd).
- `/gate-battery --repo-root <path>` — run against a specific repo root.
- `/gate-battery --await <run-id>` — follow a previously backgrounded run to its result.

## Instructions

1. **Resolve the repo root** — use `$ARGUMENTS` if it supplies `--repo-root`, else the current
   working directory.

2. **Run the battery:**
   ```
   python3 ~/.claude/scripts/gate-battery.py --repo-root <repo-root>
   ```
   (The live path is the symlinked `~/.claude/scripts/gate-battery.py`; the repo source is
   `user/scripts/gate-battery.py`.) A battery can legitimately run long (a full invariant
   battery — pytest + the state-script smoke suites + parity/doc-drift/lint gates — can take
   several minutes); use Bash `timeout: 600000` (10 min) for the foreground invocation.

3. **TRUST the authoritative LAST-stdout-line banner — do not disambiguate any other way.**
   Per the Runner-Outcome Contract Leg 1, the runner prints, as its last stdout line:
   ```
   gate-battery: run=<id> op=battery RESULT=<PASS|FAIL> cmds=<n> failed=<k> (elapsed=<s>s) [-> first failing gate: <id>]
   ```
   That line is the ONLY parse surface. Never `grep`/`cat` the runner's streamed gate output or
   the results JSON (`~/.claude/state/gate-battery/<repo-key>/results/<run-id>.json`) to
   disambiguate an exit code — everything above the banner is diagnostics for humans. Never pipe
   the runner through `tail`/`head` (Leg 4) — a pipe reports the last command's exit status, not
   the runner's, and can mask a real failure as green.

4. **Backgrounding + await (Leg 2).** A long battery may be launched with `run_in_background:
   true`. An `enqueue`/launch echo is NOT an outcome — do not end the turn or report a result on
   it (see the turn-end gate below). Follow it to the authoritative result:
   ```
   python3 ~/.claude/scripts/gate-battery.py --await <run-id>
   ```
   It re-emits the SAME Leg-1 banner as its last stdout line and exits with the run's own exit
   code. Two exit codes are reserved and mirror `build-queue-await.ps1` byte-for-byte:
   - **124** — result not yet present (the run may still be going). NEVER treat 124 as success —
     re-await, or re-run with a longer window, or check on the run again later.
   - **125** — the result file is present but malformed/unreadable after bounded retries.
   Any other exit code is the awaited run's own recorded exit code.

!`cat ~/.claude/skills/_components/turn-end-gate.md`

5. **Manifest-less repo — the correct generic refusal.** If absent, `.claude/skill-config/gate-battery.json` triggers no error: the runner refuses cleanly with **exit 2** and a one-line reason (`gate-battery: manifest not found at <path>`) — this is expected, not an error to work around. A repo opts in by committing that manifest at its toplevel:
   ```json
   { "version": 1, "gates": [{ "id": "<str>", "cmd": "<str-or-argv-list>", "cwd": "<optional>" }] }
   ```
   Gates run sequentially in manifest order; a failing gate does not stop the battery — the
   banner records the first failing gate's id. Do NOT add a manifest to a repo that has not
   opted in — that is an operator decision, not something this skill does on the agent's own
   initiative.

6. **Cloud note.** `gate-battery.py` is pure stdlib Python — no PowerShell, no build-queue
   coupling, no Windows-only dependency. It runs identically in a cloud session.

7. **Not queue-admitted.** This is a light op (SPEC L2) — it never enqueues into the
   `build-queue.ps1` FIFO serializer and carries no ETA/wait-position semantics. Don't describe
   it as "queued" or "waiting its turn"; it just runs.

## Exit-code vocabulary

| Exit | Meaning |
|------|---------|
| `0` | All gates passed (all-green). |
| `1` | At least one gate failed, or an unexpected internal runner error. |
| `2` | Manifest missing or malformed at the repo toplevel — zero state written. |
| `124` | `--await` only — result not yet present. NEVER success; re-await or check later. |
| `125` | `--await` only — result file present but malformed/unreadable after bounded retries. |
