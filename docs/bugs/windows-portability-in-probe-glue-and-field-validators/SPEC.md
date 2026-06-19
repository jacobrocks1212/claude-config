# Windows path & line-ending portability defects in orchestrator probe glue and docs-consistency field validators — Investigation Spec

> During `/lazy-batch` runs on AlgoBooth (Windows), the orchestrator's improvised probe glue writes `lazy-state.py` output to a POSIX `/tmp/` path and then reads it back with Windows-native Python, which has no `/tmp`, so the read crashes with `FileNotFoundError` and a redundant re-probe is forced. Separately, sentinel/plan files carrying a trailing carriage return (`\r`) fail AlgoBooth's `check-docs-consistency.ts` field validators on values that are otherwise legitimately correct, triggering mid-run normalization detours. Both are Windows-portability defects observed across multiple real runs; their fix loci differ (Symptom A → claude-config probe-glue prose; Symptom B → AlgoBooth-side validator).

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/windows-portability-in-probe-glue-and-field-validators
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` probe glue (line ~400); AlgoBooth `scripts/check-docs-consistency.ts` / `qg:docs-consistency`; `user/scripts/fix-line-endings.ps1`; `user/scripts/lazy_core.py::parse_sentinel`; `user/skills/_components/lazy-preflight.md`; `repos/algobooth/.claude/skill-config/docs-consistency-rules-pending.md`

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED — logs]** Probe round-trip via a POSIX `/tmp/` path crashes on Windows-native Python (STILL LIVE — hit 2026-06-19) — session `80dbeeaf` @ `2026-06-19T14:37:56.491Z`: "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/probe.json'"; recovery @ `14:38:15`: "The temp-file path crossed Git-Bash/Windows-python conventions. Re-running the probe directly." Recurs across runs days apart (`9d5b0983` 2026-06-16, `deb9f0cf` 2026-06-16 `/tmp/probe.out`, `e076ed30` 6× on 2026-06-12). Confirmed reproducible by code inspection (see Proven Findings — Symptom A).
2. **[VERIFIED — logs + code]** A trailing `\r` defeats AlgoBooth's docs-consistency field-type validators on otherwise-valid values — session `f2437fdb` 2026-06-08: "plan 'created' must match YYYY-MM-DD, got \"2026-05-18\r\"" (@17:40:34), "field 'skipped_by' must be one of {lazy | lazy-cloud}, got \"lazy\r\"" (@17:40:52), "total_count must be an integer, got \"11\r\" / \"13\r\"" (@18:05:07 / 18:32:29). Confirmed: the failing validator is AlgoBooth-side (`check-docs-consistency.ts`), NOT claude-config's own reader (which is already CRLF-safe — see Proven Findings — Symptom B). Last directly observed 2026-06-08; the producing path (a `\r`-bearing write that escapes `fix-line-endings.ps1`) is still reachable.

## Reproduction Steps

**Symptom A (probe round-trip):**
1. Run `/lazy-batch` on Windows from Git-Bash (the orchestrator's Bash tool).
2. On a turn with NO `LAZY-ROUTE` inject banner (hook inactive / first post-compaction turn), the orchestrator runs the probe manually and — following the existing prose that says "write to the OS temp dir" — captures stdout by redirecting to a temp file. With `$TMPDIR` unset (common in Git-Bash), it falls back to the POSIX-idiomatic `/tmp/probe.json`.
3. It reads `/tmp/probe.json` back with Windows-native Python (`python` resolves to the Windows interpreter, which has no `/tmp`).

**Expected:** the probe JSON round-trips, or is consumed in-band with no temp file.
**Actual:** `FileNotFoundError: '/tmp/probe.json'`; the orchestrator detects the crash and re-probes directly — one wasted probe cycle per occurrence.
**Consistency:** intermittent (only on the manual-probe path, only when the temp file lands at a POSIX `/tmp/` path); reproduced across ≥4 distinct sessions spanning 2026-06-12 → 2026-06-19.

**Symptom B (CRLF field validator):**
1. A sentinel/plan file is authored or edited with a trailing `\r` on a value line (CRLF content that escapes `fix-line-endings.ps1` — e.g. written by a tool whose PostToolUse hook did not fire, or a value embedded mid-line).
2. The AlgoBooth `qg:docs-consistency` gate (`check-docs-consistency.ts`) parses the frontmatter by splitting on `\n` only, leaving a trailing `\r` on each value.
3. A field-type validator (date / enum / integer) compares the `\r`-suffixed value against its pattern.

**Expected:** the value validates (the date/enum/integer is correct).
**Actual:** the validator rejects `"2026-05-18\r"` / `"lazy\r"` / `"11\r"`, forcing a mid-run normalization detour.
**Consistency:** conditional — only when a `\r` survives to the validator. claude-config's own readers do NOT exhibit this (CRLF-safe).

## Evidence Collected

### Source Code
- **`user/skills/lazy-batch/SKILL.md` line ~400 (Symptom A root):** The probe glue is NOT a hardcoded `/tmp/probe.json` string anywhere in the skill files — it is LLM-improvised at runtime. The only guidance present is: *"Never redirect probe or diagnostic output into the repo tree — write to the OS temp dir (`$TMPDIR` / `%TEMP%`) if you must capture it."* This (a) does not forbid a `/tmp/...` path, and (b) names `$TMPDIR` which is commonly UNSET in Git-Bash, so the orchestrator falls back to the POSIX idiom `/tmp/probe.json`. The probe already prints JSON to **stdout**, so the temp-file round-trip is unnecessary in the first place.
- **`user/hooks/lazy-route-inject.sh` (Symptom A — ruled out as locus):** The inject hook pipes the probe directly (`printf | python INJECT_PY`) and writes NO temp file. So the `/tmp` round-trip is purely the orchestrator's manual-probe improvisation, not hook behavior.
- **`user/scripts/lazy_core.py::parse_sentinel` lines 130-170 (Symptom B — claude-config is NOT affected):** Frontmatter is parsed via `raw.splitlines()` (which strips BOTH `\r\n` and `\n` terminators) then `yaml.safe_load`. A trailing `\r` is removed before any field-type check. claude-config's own state machine is CRLF-safe; it does not produce the Symptom-B errors.
- **`user/scripts/fix-line-endings.ps1` (Symptom B — partial mitigation, not wired as a hook):** Normalizes a file to CRLF on Write/Edit, but it is NOT registered in `user/settings.json` (no PostToolUse entry found). CLAUDE.md documents it as a PostToolUse hook, but the registration is absent — so a `\r`-bearing write is not reliably normalized. Even when it runs, it normalizes to CRLF (adds `\r`), which is exactly what a `\n`-only TS parser then trips on.

### Runtime Evidence
- Symptom A: 4+ sessions, ≥9 distinct `FileNotFoundError '/tmp/probe*.{json,out}'` occurrences, 2026-06-12 → 2026-06-19 (still live).
- Symptom B: session `f2437fdb`, 4 distinct field-validator rejections on `\r`-suffixed values, 2026-06-08.

### Git History
- Recent commits are bug-pipeline fixes (loop-detection false positives, mark-complete roadmap-strike). No commit has touched the probe-glue prose or the line-ending wiring for this defect.

### Related Documentation
- `user/scripts/CLAUDE.md` → "Sentinel / plan / receipt schemas": claude-config's `lazy_core.py` sentinel readers are kept in lockstep with AlgoBooth's `check-docs-consistency.ts` `SENTINEL_SCHEMAS`. The two implementations diverge on CRLF handling (Python `splitlines()` is CRLF-safe; the TS `\n`-split is not) — this is the Symptom-B seam.
- `repos/algobooth/.claude/skill-config/docs-consistency-rules-pending.md`: confirms `check-docs-consistency.ts` lives in the AlgoBooth repo root and is the gate behind `qg:docs-consistency`. Symptom-B's validator fix lands in an AlgoBooth-side PR, not claude-config.

## Theories

### Theory 1: Symptom A is an LLM-improvised `/tmp` round-trip under-specified by the probe-glue prose
- **Hypothesis:** The orchestrator captures probe stdout to a temp file because the prose tells it to, and lands at `/tmp/probe.json` because `$TMPDIR` is unset in Git-Bash and `/tmp` is the POSIX idiom; the read-back crashes under Windows-native Python.
- **Supporting evidence:** No hardcoded `/tmp` string in any skill file (it's improvised); the recovery log literally says "the temp-file path crossed Git-Bash/Windows-python conventions"; the prose at line ~400 names `$TMPDIR`/`%TEMP%` but does not forbid `/tmp`.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

### Theory 2: Symptom B is an AlgoBooth-side `\n`-only parser, not a claude-config defect
- **Hypothesis:** The failing field validators are in AlgoBooth's `check-docs-consistency.ts`, which splits frontmatter on `\n` only and leaves a trailing `\r`; claude-config's own readers are CRLF-safe.
- **Supporting evidence:** `parse_sentinel` uses `splitlines()` (CRLF-safe); the three error message formats ("must match YYYY-MM-DD", "must be one of", "must be an integer") do NOT exist anywhere in claude-config's scripts (grep returned no matches) — they are AlgoBooth-side; `docs-consistency-rules-pending.md` locates the validator in the AlgoBooth repo root.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

### Symptom A — probe `/tmp` round-trip (claude-config locus)
The defect is in the **probe-glue prose** of `user/skills/lazy-batch/SKILL.md` (and its coupled pair `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, plus `/lazy`/`/lazy-cloud`/`/lazy-bug`/`/lazy-bug-batch` if they carry the same guidance). It under-specifies temp-capture: it permits a temp file, names a Git-Bash-unset `$TMPDIR`, and does not forbid the POSIX `/tmp/...` path that crashes on Windows-native Python read-back. **The probe already emits JSON to stdout**, so the cleanest fix is to instruct in-band capture (`$(python3 … )` / pipe to the consumer) and NEVER round-trip through a temp file; failing that, mandate a portable temp path (`mktemp` / `%TEMP%` resolved by the SAME interpreter that reads it). Fix locus: claude-config.

### Symptom B — CRLF field validator (AlgoBooth locus + claude-config mitigation gap)
The failing validators are **AlgoBooth-side** (`scripts/check-docs-consistency.ts`), which must `.trim()` / strip trailing `\r` from each frontmatter value BEFORE field-type checks (mirroring claude-config's CRLF-safe `splitlines()` behavior). claude-config's own readers are already correct. A secondary, in-scope claude-config finding: `fix-line-endings.ps1` is documented as a PostToolUse hook but is NOT registered in `user/settings.json` — wiring it (or confirming the registration belongs in a per-repo settings file) is the claude-config-side hardening that reduces the rate of `\r`-bearing writes. Primary fix locus: AlgoBooth; secondary: claude-config hook wiring.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Probe glue prose (Symptom A) | `user/skills/lazy-batch/SKILL.md` (~line 400); coupled pair `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`; check `/lazy`, `/lazy-cloud`, `/lazy-bug`, `/lazy-bug-batch` for the same guidance | One wasted probe cycle per `/tmp` round-trip crash; recurs across runs |
| Docs-consistency field validators (Symptom B, PRIMARY) | AlgoBooth `scripts/check-docs-consistency.ts` (NOT in claude-config) | Valid sentinel/plan values rejected; mid-run normalization detours |
| Line-ending hook wiring (Symptom B, SECONDARY) | `user/settings.json` (PostToolUse registration absent); `user/scripts/fix-line-endings.ps1` | `\r`-bearing writes not reliably normalized |
| Sentinel reader (reference, already correct) | `user/scripts/lazy_core.py::parse_sentinel` | CRLF-safe — no change needed; the convergence target for the AlgoBooth-side fix |

## Open Questions

- Symptom B's PRIMARY fix is AlgoBooth-side (`check-docs-consistency.ts`), outside this repo. `/plan-bug` should scope the claude-config-side deliverables (Symptom A probe-glue hardening + the `fix-line-endings.ps1` hook-wiring gap) here, and either (a) spin off / cross-reference an AlgoBooth-branch work item for the TS validator `.trim()`, or (b) document it as an out-of-repo follow-up in the PHASES Implementation Notes. The AlgoBooth validator change cannot land in claude-config.
- Confirm which of the lazy-family skills carry the line-~400 "write to the OS temp dir" probe-glue prose, so the Symptom-A fix sweeps all of them (coupled-pair lockstep).
