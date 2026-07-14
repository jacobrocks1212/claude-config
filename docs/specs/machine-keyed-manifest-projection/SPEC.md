# Machine-Keyed Manifest Projection

**Status:** Concluded
**Type:** Harness capability (hardening Round 40 audit trail — `/harden-harness`, manual trigger)
**Date:** 2026-07-13
**Owner:** harden-harness (operator-ratified design via AskUserQuestion, 2026-07-13)

## Verified Symptom

`manifest.psd1` is shared across two machines (work laptop, user `JacobMadsen`; personal
workstation `DESKTOP-GHTC5K6`, user `Jacob`) but has **no per-machine projection support** —
every entry applies everywhere. Consequence: `workspace/CLAUDE.md` is projected to
`~/source/repos/CLAUDE.md` on BOTH boxes and can only describe one machine truthfully. It
described the work laptop (Cognito repos, "AlgoBooth is cloud-only"); on `DESKTOP-GHTC5K6`
(repos = claude-config + a live native AlgoBooth at `C:\Users\Jacob\repos\AlgoBooth`) it was
materially wrong — verified live 2026-07-13 (the operator hit the stale claims in-session, and
`C:\Users\Jacob\algobooth-windows-native-setup.md` §0 documents the same confusion from
2026-06). An earlier fix attempt (commit `1b9fcb0a`) made the ONE shared file machine-aware
with a two-box table; the operator REJECTED that shape — each box should project its OWN
workspace CLAUDE.md.

## Route Reconstruction (Step 1)

Not a dispatch misroute — a config-projection contract gap surfaced by operator report
(trigger 5, manual). The divergence point is `setup.ps1::Get-AllMappings` /
`setup.py::expand_mappings`: both flatten every manifest entry unconditionally, so there is no
mechanism by which two machines can receive different content at the same `Live` path.

## Root Cause (Step 2)

**missing-contract** — the manifest schema (`manifest.psd1`, consumed by
`setup.ps1:38-101` `Get-AllMappings` and `setup.py:287-348` `expand_mappings`) was designed for
a single machine and grew a second consumer without a machine axis. Evidence: the
`doc-drift:deliberate-divergence` comment block in `manifest.psd1` (lines 25-43, the algobooth
no-entry workaround) is prior art of the same gap being worked around by *omitting* entries;
`1b9fcb0a` is the same gap worked around by making shared *content* machine-aware. Both are
symptoms; the missing contract is per-machine entry selection.

## Operator-Ratified Design (locked — do not re-litigate)

1. **Mechanism: machine-keyed manifest entries.** An optional `Machine = '<hostname>'` key on
   any manifest entry. `setup.ps1` AND `setup.py` skip entries whose `Machine` doesn't match
   the local hostname, **case-insensitively** (PS: `$env:COMPUTERNAME` via the default
   case-insensitive `-eq`; py: `platform.node()` via `casefold()` — the two agree on Windows,
   where both boxes live). Precedence: for the same `Live` path, a Machine-matching entry
   **WINS** over a machine-agnostic entry; a non-matching Machine entry is skipped entirely.
   Semantics identical across both setup implementations (one manifest; `setup.py`'s tolerant
   psd1 parser already parses arbitrary quoted-string keys — `Machine` is consumed
   deliberately in `expand_mappings`, and on `Repos` entries as skip-only, not inherited
   through `Alias`).
2. **Scope: Workspace CLAUDE.md only.** The operator explicitly declined forking the
   user-level constitution. The Workspace section gains the machine-agnostic work entry
   (unchanged target `workspace\CLAUDE.md`) + a `Machine = 'DESKTOP-GHTC5K6'` entry targeting
   `workspace\CLAUDE.DESKTOP-GHTC5K6.md`, same Live path.

## Fix Scope

- `Machine` key support in `setup.py` (`expand_mappings` + injectable `machine=` param) and
  `setup.ps1` (`Get-AllMappings`), + pytest coverage in `user/scripts/test_setup_py.py`
  (setup.ps1 has no test suite — manual on-box verification recorded in the hardening round).
- Revert `workspace/CLAUDE.md` to pre-`1b9fcb0a` work-laptop content + a one-line
  per-machine-variant pointer.
- New `workspace/CLAUDE.DESKTOP-GHTC5K6.md` grounded against the live box (repo map, git
  identity verified from `~/.gitconfig`, platform, projection tables).
- Manifest Workspace section: both entries as above.
- Entry-key schema docs updated (root `CLAUDE.md` Symlink System section);
  `doc-drift-lint.py` stays exit 0 (its psd1 reader parses only the `Repos` block —
  Workspace `Machine` keys are outside its scope by construction).
- On-box verification: `python3 setup.py check` → `repair --target Workspace` → check exit 0;
  `~/source/repos/CLAUDE.md` resolves to the new file; `setup.ps1 check -Target Workspace`
  agrees (the setup.ps1 manual receipt).

## Out of Scope

- Per-machine forks of any other entry (user CLAUDE.md, settings) — operator-declined.
- A general machine-profiles system (env-var overrides, machine groups) — YAGNI until a third
  machine or a third forked file exists.
- Retiring the algobooth no-Repos-entry workaround by re-adding a Machine-keyed entry — a
  separate operator decision (the workaround's comment block predates this capability; a
  future round may propose `Machine = 'DESKTOP-GHTC5K6'` on an algobooth Repos entry).
