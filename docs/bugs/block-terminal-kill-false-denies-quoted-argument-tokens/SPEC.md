# block-terminal-kill.sh false-denies a termination keyword inside a quoted argument value — Investigation Spec

> The 2026-07-12 segment-start anchoring fixed embedded-word false-positives (an awk `{exit}`
> body, a pytest `-k "...kill..."` filter) but does not account for a token — or a shell
> SEPARATOR that fabricates a false segment-start for one — living inside a quoted STRING
> ARGUMENT VALUE. A commit chain carrying a guard clause inside a single-quoted message
> (`git commit -m '... || exit 1'`) and an `--emit-dispatch --context "...exit..."` prose
> string both false-deny: the quoted `||`/`;` makes `_CMD_START` match the following
> termination keyword even though it never begins a real command segment.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-13
**Related:** `docs/bugs/_archive/powershell-tool-bypasses-bash-matched-guards/` (item 5 — the sibling segment-start-anchoring fix on this same hook that this extends to the quoting level); `docs/bugs/_archive/long-build-and-build-queue-matcher-bypasses/` (the plane-wide `bash -c "..."` quoted-argument residual — the accepted-gap direction this fix stays inside of); `user/hooks/CLAUDE.md` → "PowerShell-syntax regex audit" + "Known limitation — `bash -c` / `sh -c` string-wraps".

## Verified Symptom

Hit twice in this session's claude-config `/lazy-batch` run:

- **(a) guard-clause in a single-quoted commit body** — a write-plan cycle subagent commit chain contained a shell-termination-builtin guard clause of the form `'... || <builtin> 1'` inside the `git commit -m '...'` message; the hook denied the whole commit.
- **(b) quoted `--context` prose** — THIS orchestrator's `--emit-dispatch hardening --context "..."` call whose double-quoted prose described a nonzero-status refusal using the literal termination keyword; the hook denied the dispatch. (Observed live again while root-causing: the hook denied the investigating Bash call that merely *quoted* the repro strings.)

Reproduced against the shipped regexes (pre-fix), `term`/`kill` = would-deny:

```
git commit -m 'landed fix || exit 1'                        term=True   (BUG — should allow)
python3 x.py --context "refuses; exit code nonzero"         term=True   (BUG — should allow)
git commit -m 'oops | kill 5'                               kill=True   (BUG — should allow)
cd /tmp && exit 1                                           term=True   (correct — real)
kill 1234                                                   kill=True   (correct — real)
```

## Root Cause

**Classification: `hook-defect`** (`user/hooks/block-terminal-kill.sh`).

`_CMD_START = (?:^|[\n;&|(]|\{(?=\s))\s*` + env-prefix anchors a match to a command-segment start — string start or immediately after a shell separator. When a separator (`|`, `;`, `&`, `(`) appears INSIDE a quoted string literal, `re.search` finds that in-quote separator and matches the termination keyword that follows it. The anchoring is correct at the shell-token level but blind to shell QUOTING: the separator/keyword is genuinely at a segment-start position *within the quoted literal*, which is one shell-quoting level below the command line the hook guards. The prior fix removed the "bare word anywhere" class; this residual is the "separator+keyword inside a quoted argument" class.

## Fix Scope

Make the guard quote-aware BEFORE the anchored matchers run — a flat single-pass char scan (the same normalization discipline as `_normalize_ps_syntax` / the line-continuation collapse, deliberately NOT a full shell parser):

1. New `_mask_quoted(command)` blanks the CONTENT of single- and double-quoted spans to spaces, preserving the quote chars and every offset so the existing `_CMD_START` matchers run unchanged on the masked string. Outside a span a backslash-escaped quote does not open one; inside a double-quoted span `\"` does not close it; an unbalanced trailing quote masks to end-of-string.
2. `main()` applies `_mask_quoted` after the PS line-continuation collapse and before matching.
3. Masking can only REDUCE matches (a keyword outside every quote is untouched), so true positives — a real leading `kill`/`exit`/`taskkill`, a real `&& exit 1` outside quotes, a real `kill` after a quoted commit message — still deny. The accepted residual is a keyword inside a `bash -c "kill ..."` string argument (the same plane-wide quoted-argument residual documented in `user/hooks/CLAUDE.md`), which does not terminate THIS terminal anyway.
4. Regression fixtures in `test_hooks.py`: the single-quoted guard-clause case (a), the double-quoted `--context` case (b), a quoted `| kill` case (c) — all ALLOW; plus true-positive pins (real `&& kill` after a quoted message still denies) so the mask cannot silently over-allow.
