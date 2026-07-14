# build-queue ETA approx marker (U+2248) mojibakes on redirected stdout — Investigation Spec

> The `≈` prediction marker on every pre-outcome ETA surface is emitted as OEM byte `0xF7`
> through powershell.exe's redirected stdout, which is invalid UTF-8 — agents and the Bash
> tool render `eta-start�0s eta-done�?` instead of `eta-start≈0s eta-done≈?`.

**Status:** Fixed
**Severity:** Low
**Discovered:** 2026-07-10
**Fixed:** 2026-07-14
**Fix commit:** 985e4457
**Placement:** docs/bugs/build-queue-eta-marker-mojibake-on-redirected-stdout
**Related:** docs/features/build-queue-eta-priority-lanes (shipped the marker; SPEC examples show `≈`), docs/bugs/_archive & open build-queue-* siblings, docs/bugs/crlf-hook-blanket-enforce-mixed-eol (prior encoding-boundary defect class)

---

## Verified Symptoms

1. **[VERIFIED]** The seq=991 enqueue echo in a live Cognito `/msbuild` run rendered
   `eta-start�0s eta-done�?` in the Bash tool / Claude Code shell view — confirmed via
   operator-supplied screenshot (2026-07-10) showing U+FFFD replacement chars where `≈`
   belongs, on both the enqueue echo and the backgrounded-shell Output pane.
2. **[VERIFIED]** Deterministic local repro:
   `powershell.exe -NoProfile -Command "[char]0x2248" | od -c` → octal `367` (byte `0xF7`),
   not the UTF-8 sequence `E2 89 88`. `0xF7` is not valid UTF-8, so any UTF-8 consumer
   substitutes U+FFFD (`�`).

### Not a bug (triaged alongside)

- **`eta-done≈?` at seq=991 was correct cold-start honesty**, not a missing value:
  `Get-BuildQueueEta` returns `$null` (rendered `?`) with fewer than 3 successful samples
  (`build-queue-hygiene.ps1:1889`), and `stats/msbuild.json` held only 2 entries (seqs
  988, 989) at enqueue time. Seq 991's completion made it 3 — subsequent msbuild enqueues
  produce a real median (~111.5s). `eta-start≈0s` was likewise populated correctly
  (position=1, idle queue → 0s wait). Only the **marker glyph** is defective.

## Reproduction Steps

1. From bash (or the Claude Code Bash tool), run:
   `powershell.exe -NoProfile -Command "[char]0x2248 ; 'eta-start' + [char]0x2248 + '0s'" | od -c`
2. Observe byte `367` (0xF7) where `≈` should be — not `342 211 210` (E2 89 88, UTF-8).
3. End-to-end: enqueue any manifested op via the wrapper from bash, e.g.
   `powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op msbuild -Exec <filtered-script>`
   and read the first stdout line.

**Expected:** `build-queue: enqueued as seq=N (op=msbuild, lane=heavy) position=1 eta-start≈0s eta-done≈?`
**Actual:** `build-queue: enqueued as seq=N (op=msbuild, lane=heavy) position=1 eta-start�0s eta-done�?`
**Consistency:** Always, whenever powershell.exe stdout is redirected/piped (the primary
consumption path — every agent invocation) and `[Console]::OutputEncoding` is an OEM
codepage (the Windows default). A native interactive console may render it fine, which is
why it shipped unnoticed.

## Evidence Collected

### Source Code — serving-path trace (cause: `traced`)

Surface: the Bash-tool-captured stdout line `…eta-start�0s eta-done�?`.

```
Bash tool decodes captured bytes as UTF-8 → 0xF7 invalid → U+FFFD (�)
  ← powershell.exe encodes Write-Output text via [Console]::OutputEncoding
      (OEM codepage on redirect; ≈ = 0xF7 in CP437/CP850)      [verified: od -c → 367]
  ← Write-Output $enqueueEcho                                   build-queue.ps1:201
  ← $enqueueEcho += Format-EtaSuffix …                          build-queue.ps1:200
  ← Format-EtaSuffix interpolates $script:etaApprox             build-queue.ps1:184,187
  ← $script:etaApprox = [char]0x2248                            build-queue.ps1:177   ← fix site
```

The fix site (`[char]0x2248` / the output-encoding boundary) is ON the traced path — the
marker char is the exact value consumed at build-queue.ps1:184/187 to compose the surface
line. The encoding claim is runtime-coupled and carries cited runtime evidence (Verified
Symptom 2), not a static read.

Sibling emission sites (same root cause, same literal):

| Surface | Site |
|---------|------|
| Enqueue echo (`eta-start≈`/`eta-done≈`) | `build-queue.ps1:177,184,187` (composed :193-201) |
| Waiting-position line (`, eta-start≈…`) | `build-queue.ps1:410-416` (via `Format-EtaSuffix`) |
| Status view, active build `remaining≈` | `build-queue-status.ps1:107,121` |
| Status view, per-waiter `eta-start≈`/`eta-done≈` | `build-queue-status.ps1:149,166` |

Unaffected: `Format-BuildQueueBanner` (the authoritative last-line outcome) — Pester-pinned
to contain neither `≈` nor `eta-` (`build-queue-hygiene.Tests.ps1:1508,1515,1521-1522`).
`build-queue-await.ps1` re-emits the banner only. `Get-BuildQueueEta`/`Get-BuildQueueWaitEta`
and `Format-EtaDuration` return correct values — no numeric defect anywhere.

### Runtime Evidence

- `od -c` repro above (byte 0xF7).
- Operator screenshot of the live seq=991 run (both the `cat`-ed task output and the
  Shell-details Output pane show `�`).
- `~/.claude/state/build-queue/stats/msbuild.json` at investigation time:
  3 entries (29s, 111.5s, 167.5s — seqs 988/989/991), confirming the cold-start `?` math.

### Git History

Marker introduced by `801aec1` (feat(build-queue): generalize beyond Cognito … add ETA +
K=3 priority lanes) — the `build-queue-eta-priority-lanes` feature. No later commit touched
the glyph.

### Related Documentation

- `docs/features/build-queue-eta-priority-lanes/SPEC.md:136-147,261-269` — locks "`≈` marks
  every prediction, `?` on cold start" and shows `eta-start≈` examples. The *intent* (a
  visually distinct approx marker so predictions are never mistaken for measurements) is a
  Locked Decision; the *glyph choice* U+2248 is implementation detail.
- Root `CLAUDE.md` build-queue rows document `remaining≈`/`eta-start≈`/`eta-done≈` surfaces.
- Pester: no test pins `≈` PRESENT on any ETA surface (only ABSENT from the banner), so an
  ASCII marker substitution breaks no test.

## Theories

### Theory 1: OEM-codepage encoding boundary (root cause)
- **Hypothesis:** powershell.exe (5.1) encodes redirected stdout via `[Console]::OutputEncoding`,
  which defaults to the OEM codepage; U+2248 maps to single byte 0xF7 there; downstream
  UTF-8 consumers (Bash tool, Claude Code) see an invalid sequence and render U+FFFD.
- **Supporting evidence:** `od -c` shows exactly one byte `367`; screenshot shows `�` at
  exactly the marker positions; ASCII text on the same lines is intact.
- **Contradicting evidence:** none.
- **Status:** Confirmed (`traced` — serving path + cited runtime evidence above).

## Proven Findings

1. Every pre-outcome ETA surface (4 emission sites, 2 scripts) emits U+2248 through an
   OEM-encoded stdout and is mojibaked for any UTF-8 consumer. Values are correct; only the
   glyph is lost.
2. The authoritative outcome banner is structurally immune (no-ETA Pester pin).
3. No mechanical consumer parses the `≈` form (skills tell agents to trust the banner;
   SPEC prose says predictions never gate anything) — impact is legibility/honesty-marker
   fidelity, hence Severity: Low.
4. `eta-done≈?` cold-start behavior is by design and self-heals at ≥3 samples.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Build-queue wrapper pre-outcome echoes | `user/scripts/build-queue.ps1:177,184,187,410-416` | `�` in enqueue echo + position lines |
| Build-queue status view | `user/scripts/build-queue-status.ps1:107,121,149,166` | `�` in `remaining≈` + waiter ETA rows |
| Outcome banner / await | `build-queue-hygiene.ps1` (`Format-BuildQueueBanner`), `build-queue-await.ps1` | None (pinned ETA-free) |

## Fix Direction (for /plan-bug)

Replace the U+2248 literal with the ASCII marker `~` at all four sites (e.g. `eta-start~0s`,
`remaining~ 1m 10s`) — deterministic on every codepage, zero encoding side effects, keeps
the SPEC's prediction-vs-measurement distinction, breaks no Pester pin. Update the two
root-`CLAUDE.md` build-queue rows + `build-queue-eta-priority-lanes` SPEC surface examples
(or annotate the divergence). Rejected alternative: forcing `[Console]::OutputEncoding`
to UTF-8 inside the wrapper — wider blast radius (all wrapper/runner output, detached
child processes, log files) for a one-glyph win.

## Open Questions

- None blocking. Optional: whether a `~` should also be pinned ABSENT from the banner the
  way `≈` is (cheap extra Pester assertion at the existing pin site). Not added in the fix —
  `~` can legitimately appear in paths/next-action text, and the existing `eta-` absence pin
  (`build-queue-hygiene.Tests.ps1:1521-1522`) already guards the banner surface.

---

## Fix Applied (2026-07-10, interactive session)

`≈` → ASCII `'~'` at all three definition sites (the position-line surface inherits via
`Format-EtaSuffix`); each site carries a comment naming this bug dir:

- `user/scripts/build-queue.ps1` — `$script:etaApprox = '~'`
- `user/scripts/build-queue-status.ps1` — `$etaApprox = '~'` (active-build `remaining~`) and
  `$etaApproxW = '~'` (waiter rows)
- Root `CLAUDE.md` `build-queue-status.ps1` row updated to the `~` forms + a divergence note
  against the `build-queue-eta-priority-lanes` SPEC's `≈` examples (historical, not edited).

### Symptom-gone evidence (original surface, serving path)

Ran `build-queue-status.ps1 -StateRoot <fixture>` against a fake state root (active msbuild
build + one waiter + the real 3-sample `stats/msbuild.json`); output:

```
  elapsed: 1s   remaining~ 1m 49s
  [1] seq=995 op=msbuild lane=heavy worktree=C:/fake/wt2 waiting=1s eta-start~1m 49s eta-done~3m 40s
```

`grep -P '[^\x00-\x7F]'` over the captured stdout: **zero non-ASCII bytes** — the U+FFFD
symptom cannot recur on any codepage because no non-ASCII byte is emitted. The enqueue-echo
surface consumes the same `$script:etaApprox` variable (`build-queue.ps1:184,187`), now `'~'`.

### Regression suite

`Invoke-Pester build-queue-hygiene.Tests.ps1`: 172 passed / 3 failed — the 3 failures are
pre-existing environment-dependent Job-Object tests (`Add-ProcessToBuildJob`,
`Stop-BuildJobTree`, `Reset-CompilerServer` at Tests.ps1:44,50,79) in a file this fix does
not modify; all ETA-estimator and banner-pin tests passed (`≈`-absent + `eta-`-absent pins
at 1508-1522 remain trivially green).
