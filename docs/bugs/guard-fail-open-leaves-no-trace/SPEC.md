# Guard fail-open leaves no trace — Investigation Spec

> Every PreToolUse hook fails open by documented contract (a non-zero exit is a hard harness
> error), but fail-open **observability** is inconsistent-to-absent: the no-python path is
> silent across the entire guard plane, one bash-side breadcrumb writer targets an unset
> variable and has never worked, two enforcement hooks have no error-path trace at all, and
> the severest failure class (python unavailable) is exactly the one the python-side
> appenders cannot record. A dead guard plane today is indistinguishable from a quiet one.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-11
**Related:** `user/hooks/CLAUDE.md` (the Fail-OPEN + countable-events contracts this bug is
measured against); `docs/features/shared-hook-lib/SPEC.md` (the natural fix vehicle for the
shared bash-side fallback writer — authored the same session); `docs/bugs/legacy-tool-input-env-hooks-dead/`
(sibling drift-class bug, authored in parallel 2026-07-11); `user/scripts/incident-scan.py`
(the downstream consumer of `hook-error.json` + `hook-events.jsonl` — blind to everything this
bug leaves unwritten); `user/scripts/lazy_inject.py` (surfaces `hook-error.json` on the next
inject turn — only helps when the crumb was actually written).

## Verified Symptom

All findings re-verified against the working tree 2026-07-11. Line numbers current as of that
date.

**(a) The no-python path is silent for the entire python-bearing guard plane.** All 7
python-dependent hooks (`block-noncanonical-blocker-write.sh` 35-38,
`block-sentinel-write-on-stray-branch.sh` 33-36, `long-build-ownership-guard.sh` 62-65,
`build-queue-enforce.sh` 79-81, `lazy-dispatch-guard.sh` 45-48, `lazy-route-inject.sh`,
`lazy-cycle-containment.sh` 88-93) resolve `python3` → `python` and, when neither exists,
`exit 0` with no output. Six of the seven write nothing at all; grep-verified there is **no
bash-side writer** of `hook-error.json` or `hook-events.jsonl` anywhere in `user/hooks/` —
every breadcrumb/event writer lives inside the inline Python bodies. Python missing (broken
PATH, non-login shell without `BASH_ENV`, a machine where the nvm/venv shim vanished) ⇒ the
**entire guard plane is dead with zero trace**, silently, on every tool call.

**(b) CONFIRMED DEFECT — the one bash-side breadcrumb attempt writes to an unset variable.**
`lazy-cycle-containment.sh` line 90-91 (the only hook that even tries to leave a no-python
crumb):

```bash
printf '{"hook":"lazy-cycle-containment","error":"no python interpreter on PATH","at":""}\n' \
  > "$STATE_DIR/hook-error.json" 2>/dev/null || true
```

The bash-scope variable is `LCC_BASE_DIR` (line 64). `STATE_DIR` exists only **inside the
inline Python body** (line 118) — in bash scope it is unset, so the target path expands to
`/hook-error.json`, the root-level write fails (or lands at the msys root on git-bash), and
`2>/dev/null || true` swallows the failure. This breadcrumb has never worked; the header
comment (line 40-42, "writes a hook-error.json breadcrumb and ALLOWS") documents behavior
that does not exist.

**(c) The two sentinel hooks have no error-path observability at all.**
`block-noncanonical-blocker-write.sh` 165-170 and `block-sentinel-write-on-stray-branch.sh`
237-242 end in a bare catch-all:

```python
except Exception:  # noqa: BLE001 — fail-OPEN on ANY error.
    sys.exit(0)
```

No `_breadcrumb`, no `_append_hook_event("error", ...)` — their only event sites are the
deny paths. This diverges from their siblings (`long-build-ownership-guard.sh` 299-301 and
`build-queue-enforce.sh` 622-624 both call `_breadcrumb(exc)` from the same catch-all) and
from `user/hooks/CLAUDE.md`: the Fail-OPEN section prescribes dropping a `hook-error.json`
breadcrumb (phrased advisorily — "if useful for diagnosis"), and the countable-events section
requires every *existing* breadcrumb site to also append an event — which quietly enshrines
the coverage gap rather than closing it (the sentinel pair simply never became breadcrumb
sites). Nuance vs the raw evidence: this is a **contract gap the CLAUDE.md wording permits**,
not a sentence-level contradiction — but the intent (a broken hook must be diagnosable) is
plainly unmet.

**(d) The observability that does exist cannot record the severest failure class.**
`hook-error.json` is a single overwriting slot (opened `"w"` at `long-build` 232,
`build-queue` 250, `lazy-cycle` 272, `lazy_guard.py` ~99) — a second failure clobbers the
first. The countable history (`hook-events.jsonl` error lines) is appended **only from
Python** (`_append_hook_event` ×5 hooks + `lazy_core.append_hook_event`). Catch-22: the
failure class most likely to take out the whole plane (python unresolvable / interpreter
dies before the appender runs) is precisely the one no python-side appender can record.

**(e) Hook timeout kills are presumed traceless (UNVERIFIED — flagged).** Every hook is
registered with `"timeout": 5` in `user/settings.json` (verified). A timeout kill is
delivered harness-side; no hook installs a trap or start/finish marker pair, so a hook killed
at 5s leaves the same nothing as a hook that never ran. Not empirically reproduced (would
require staging a deliberately slow hook); the mechanism is inferred from the settings +
absence of any trap/marker code. Verify or refute during fix planning.

## Root Cause

**Classification: `missing-contract` (plane-wide) + one `copy-drift` instance defect.**

1. **Missing contract:** the Fail-OPEN mandate (`user/hooks/CLAUDE.md`) was adopted without a
   matching **fail-open observability** contract. Breadcrumb coverage grew ad hoc, hook by
   hook — three hooks got `_breadcrumb`, two got nothing, and the pre-python bash layer got
   nothing anywhere — because each hook copy-pastes its own scaffolding instead of inheriting
   a shared prelude with the contract built in (the systemic half is
   `docs/features/shared-hook-lib`).
2. **Instance defect:** the `$STATE_DIR`-vs-`LCC_BASE_DIR` mismatch in
   `lazy-cycle-containment.sh` is bash/python namespace drift inside one file — the python
   body's `STATE_DIR` name leaked into the bash-side write — undetected because the failure
   is itself swallowed by the fail-open idiom (`2>/dev/null || true`), and no test exercises
   the no-python branch.

## Fix Scope (Concluded)

1. **Pure-bash fallback writer (no python required)** — a small shared function (natural
   home: `hook-prelude.sh` from `docs/features/shared-hook-lib`; interim: a copied block) that
   best-effort appends one `{ts, kind:"error", hook, repo_root:"", signature, detail}` line to
   `$LAZY_STATE_DIR`-or-`~/.claude/state/hook-events.jsonl` **and** overwrites
   `hook-error.json`, using only printf/date. Wire it into the no-python branch of all 7
   python-bearing hooks so a dead interpreter finally leaves a countable trace
   (`incident-scan.py` already reads both files).
2. **Fix the `$STATE_DIR` bug** in `lazy-cycle-containment.sh` line 91 → `$LCC_BASE_DIR`
   (or the shared writer from §1), plus a pipe-test that forces the no-python branch
   (`PATH` stripped) and asserts the crumb lands in the override state dir.
3. **Error-path breadcrumb + event for the sentinel pair** — give
   `block-noncanonical-blocker-write.sh` / `block-sentinel-write-on-stray-branch.sh` the same
   `except Exception: _breadcrumb(exc)` tail their two siblings already have (the
   `_breadcrumb` helper chains into `_append_hook_event("error", ...)`), and tighten the
   `user/hooks/CLAUDE.md` wording from "if useful" to a requirement: **every** python-bearing
   hook's catch-all writes the breadcrumb + event.
4. **Fail-open heartbeat / dead-plane alarm** — the silent-death class needs an active check,
   not just richer corpses: surface "guards executed 0 times this run" via the
   `lazy-route-inject` banner or `lazy-state.py --probe` when a live run's window shows zero
   guard-plane events. Needs a cheap execution heartbeat (e.g. a per-run first-execution touch
   file or sampled allow-path event) — design decided at planning, sized against the
   fail-open latency budget.
5. **Timeout-kill tracing (pending the §(e) verification)** — if confirmed traceless, either a
   start-marker/clean-exit-delete pair (a stale start marker = a killed hook) or an explicit
   documented limitation in `user/hooks/CLAUDE.md`. A bash `trap` alone cannot catch a hard
   kill.
6. **Pipe-tests in `test_hooks.py`** for every new path: no-python fallback writes the event
   line; sentinel-pair catch-all writes crumb + event with byte-identical allow output;
   heartbeat fires on the staged dead-plane fixture.

## Decisions

- **D1 — bash-side event-line schema fidelity:** the bash writer emits the same JSONL fields
  as `lazy_core.append_hook_event` (`ts` from `date +%s` is second-granularity — acceptable;
  `repo_root` empty — bash never re-derives repo identity per the CLAUDE.md rule). Confirm
  `incident-scan.py` tolerates integer `ts` before landing.
- **D2 — heartbeat surface:** inject-banner vs `--probe` vs both — decide at planning; the
  probe is the cheaper first landing (no per-turn cost), the banner is the one the
  orchestrator actually sees mid-run.
- **D3 — timeout tracing in- or out-of-scope:** gated on verifying symptom (e). If out, it
  must be documented as a known limitation, not silently dropped.
- **D4 — sequencing vs shared-hook-lib:** fix §2/§3 immediately (small, self-contained);
  land §1's shared writer through `shared-hook-lib` if that feature is scheduled promptly,
  else as a copied block with a migration note (do not let the systemic feature block the
  instance fixes).
