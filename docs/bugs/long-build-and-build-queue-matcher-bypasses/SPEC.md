# Long-build + build-queue matcher bypasses — Investigation Spec

> Empirically verified matcher-coverage gaps in two request-time guards: the long-build
> ownership guard allows every runner-prefixed / path-prefixed / string-wrapped form of the
> builds it exists to redirect (`npx tauri build`, `npm run tauri build` — the canonical Tauri
> invocation — `cargo tauri build`, absolute-path `cargo build --release`, `bash -c "..."`),
> and the build-queue enforce hook's wrapper allowlist is an **unanchored substring** checked
> before the deny scan, so any command merely *mentioning* `build-queue.ps1` bypasses the
> entire deny surface. Both errors are one-sided in the allow direction (under-blocking) — the
> guards are alive, their matchers are just narrower than the invocations they govern.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-11
**Related:** `docs/features/long-build-and-runtime-ownership/` (the guard's owning spec — M5
Prevent); `docs/features/build-queue-generalization/` (owns the manifest gate + `_WRAPPER_RE`
exemption, locked D5 "no ping-pong"); the `docs/bugs/build-queue-*` family
(`build-queue-false-green-on-silent-build-failure`, `build-queue-outcome-opacity-and-inspect-deny`,
et al. — those are **result-fidelity** bugs in the wrapper/runner; this bug is **matcher
coverage** in the enforcement hooks; complementary, no scope overlap);
`docs/features/shared-hook-lib/SPEC.md` (the `_ENV_PREFIX`/`_CMD_START` anchor pair this fix
must change is triplicated across three hooks — authored the same session).

## Verified Symptom

All results below are live pipe-tests run 2026-07-11 on this machine: PreToolUse JSON payloads
piped through the real hooks (`bash <hook> < payload`), deny = JSON emitted, allow = empty
output. Line numbers current as of that date.

**1. `long-build-ownership-guard.sh` (`_LONG_BUILD_RE`, lines 117-123).** The regex matches
only a raw binary token at a command-segment start
(`_CMD_START + (tauri\s+build | cargo\s+build\s+--release | npm\s+run\s+build)`):

| Command | Verdict | Should be |
|---|---|---|
| `cargo build --release` | DENY | DENY (guard alive) |
| `cd /x && tauri build` | DENY | DENY (chain-anchor works) |
| `npx tauri build` | **ALLOW** | DENY |
| `npm run tauri build` | **ALLOW** | DENY — the **canonical** Tauri invocation (Tauri docs + AlgoBooth scripts route through the `tauri` npm script) |
| `cargo tauri build` | **ALLOW** | DENY (cargo-tauri subcommand form) |
| `/abs/path/cargo build --release` | **ALLOW** | DENY |
| `bash -c "cargo build --release"` | **ALLOW** | DENY (string-wrap; see D2) |

Mechanism: `_CMD_START` (`(?:^|[\n;&|({])\s*` + optional env assignments, lines 113-116)
requires the *build binary token itself* at a segment start. A runner prefix (`npx `,
`npm run `, `cargo `), a path prefix (`/abs/path/`), or an enclosing quote places the token
after a non-separator character, so the regex never fires. The guard exists to stop a cycle
subagent's backgrounded long build dying at turn-end (M5) — the canonical invocation of the
single longest build in the fleet walks straight past it.

**2. `build-queue-enforce.sh` (`_WRAPPER_RE`, line 119; checked line 563).**

```python
_WRAPPER_RE = re.compile(r"build-queue\.ps1", re.IGNORECASE)   # line 119
...
if _WRAPPER_RE.search(command):                                 # line 563
    _allow()
```

The allow runs **before** both deny surfaces (manifest scan 566-571, legacy scan 601-613) and
is an unanchored substring over the whole command. Pipe-tested in a scratch repo carrying a
`.claude/skill-config/build-queue-ops.json` manifest (`ops.msbuild.deny: ["dotnet build"]`,
`BQE_PLATFORM_OVERRIDE=armed`):

| Command | Verdict | Should be |
|---|---|---|
| `dotnet build MySln.sln` | DENY | DENY (manifest gate armed + working) |
| `echo build-queue.ps1; dotnet build MySln.sln` | **ALLOW** | DENY |
| `grep foo build-queue.ps1 && dotnet build MySln.sln` | **ALLOW** | DENY |

Any command that mentions the wrapper filename anywhere — an echo, a grep, a comment string, a
path argument — is fully exempt from the deny surface the rest of the hook painstakingly
anchors (`_CMD_START`-anchored dotnet/nx denies, path-prefix-aware filtered-script denies,
segment-aware bypass suppression). The line-117 comment even documents the intent ("it may
appear inside a quoted path as an argument to powershell.exe -File ...") — the implementation
just never anchored to that form.

## Root Cause

**Classification: `matcher-gap` (incomplete matcher coverage), both instances.** Two distinct
under-matches with a common shape — each matcher encodes one narrow syntactic form of a
semantic family:

1. `_LONG_BUILD_RE` enumerates the three raw-binary spellings the spec named, but the
   *semantic* target is "an invocation that starts this long build", which in the wild is
   dominated by runner-prefixed forms (`npx`/`npm run`/`cargo` subcommand) the enumeration
   never included. The command-position anchor is correct; the token alternatives behind it
   are incomplete.
2. `_WRAPPER_RE` was written as a recognizer for "this command routes through the sanctioned
   wrapper" but implemented as "this command's text contains the wrapper's filename" — an
   allowlist with weaker anchoring than the deny surface it short-circuits. Allow-before-deny
   ordering (locked D5, no ping-pong) is itself sound; the recognizer feeding it is not.

Neither is a fail-open violation — both err in the allow direction, preserving the plane's
posture — but both silently void their guard's purpose for the bypassing forms.

## Fix Scope (Concluded)

1. **Extend `_LONG_BUILD_RE`** (long-build-ownership-guard.sh):
   - Optional runner prefixes for the tauri form: `(?:npx\s+|npm\s+run\s+|cargo\s+)?tauri\s+build`.
   - Optional path prefix on the binary tokens (`(?:\.?[\\/])?(?:[^\s;&|]*[\\/])?` — reuse the
     proven `_FILTERED_SCRIPT_DIRECT_RE` prefix idiom from build-queue-enforce.sh lines
     162-168) so `/abs/path/cargo build --release` matches.
   - Keep the existing negative space intact: `npm run build:docs`, `cargo check --release`,
     plain `cargo build` (debug), and `npm run tauri dev` must stay ALLOW — each becomes an
     explicit negative pipe-test.
2. **Anchor `_WRAPPER_RE`** (build-queue-enforce.sh): recognize only (a) a command-segment-start
   invocation whose token path ends in `build-queue.ps1` (same `_CMD_START` + path-prefix
   idiom), and (b) the `powershell/pwsh ... -File <path>build-queue.ps1` form (mirror the
   existing `_FILTERED_SCRIPT_POWERSHELL_RE`, lines 171-175). `echo build-queue.ps1; dotnet
   build` must then DENY on the second segment.
3. **`bash -c` / `sh -c` string-wraps — decide, don't drift (D2):** a quoted-string wrap
   smuggles *any* denied command past *every* `_CMD_START`-anchored matcher in the plane
   (lazy-cycle-containment's recursion denies included, which share the same anchor pair).
   Either add a quoted-string subscan (rescan the argument of `(?:ba)?sh\s+-l?c\s+` as a
   nested command text) or write the explicit out-of-scope note in the hook headers +
   `user/hooks/CLAUDE.md`. Do not fix it for one hook only.
4. **Pipe-tests in `test_hooks.py`** — one test per verified bypass row above (positive) and
   per protected negative (the table's ALLOW-and-should-stay-ALLOW forms), both hooks.
5. **Anchor-pair coordination:** `_ENV_PREFIX`/`_CMD_START` exist in three copies
   (lazy-cycle-containment ~195-196, long-build ~113-116, build-queue ~140-141). If §3
   changes anchor semantics, it must land in all three — route through
   `docs/features/shared-hook-lib` if scheduled, else a three-site coordinated edit with a
   drift note.

## Decisions

- **D1 — enumeration vs generic runner-prefix:** enumerate the known runner forms (`npx`,
  `npm run`, `cargo`) rather than a generic "any token before tauri" wildcard — the guard's
  near-zero false-positive charter (header lines 24-27) outweighs hypothetical coverage;
  `npm run tauri dev` / `cargo tauri dev` must not match. Per-repo manifest-driven
  enumeration (the `build-queue-ops.json` `deny` patterns `_queue_routing_hint` already
  reads) is the escape hatch if repo-specific script aliases keep appearing — surface as an
  option at planning, don't build speculatively.
- **D2 — `bash -c` scope:** unresolved at investigation close; fix-scope §3 requires the
  planner to pick subscan vs documented-limitation **plane-wide** (the gap is shared by every
  anchored matcher, not just these two hooks).
- **D3 — no scope creep into the build-queue result-fidelity family:** the
  `docs/bugs/build-queue-*` bugs own wrapper/runner outcome fidelity; this fix touches only
  the two matchers + tests. Cross-link, don't merge.
