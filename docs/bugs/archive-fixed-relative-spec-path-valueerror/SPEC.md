# `archive_fixed` Crashes on a Relative `spec_path` With an Absolute `repo_root` — Investigation Spec

> `bug-state.py --archive-fixed` passes the CLI `spec_path` through un-normalized as
> `Path(args.archive_fixed)`, while `archive_fixed` (`lazy_core/gates.py`) resolves
> `repo_root` to an absolute path (`repo_root = repo_root.resolve()`, gates.py:1973) but leaves
> `spec_path` untouched. The per-file `git mv` fallback then computes
> `spec_path.relative_to(repo_root)` (gates.py:2104). With a RELATIVE `spec_path`
> (`docs/bugs/<id>`) and an ABSOLUTE `repo_root`, `Path.relative_to` raises `ValueError`. That
> `ValueError` is UNCAUGHT — the function's only `try/except` catches
> `(OSError, subprocess.SubprocessError)` (gates.py:2213), so `--archive-fixed` dies with a raw
> traceback instead of a structured refusal. Sibling completion-gate subcommands
> (`--apply-pseudo`, `--verify-ledger`) never mix a relative `spec_path` with an absolute
> `repo_root` in a `relative_to()` call, so they are unaffected — the inconsistency is
> `archive_fixed`-specific and surprising.

**Status:** Concluded
**Severity:** P2 (correctness/robustness — the scripted `__mark_fixed__ → --archive-fixed`
mover crashes on a documented, sibling-accepted invocation form; the run's archive step aborts
rather than completing or refusing cleanly. Not data-destructive — the crash occurs before or
during the move, and the operation is re-runnable — but it defeats the whole point of promoting
the archive mechanics to a deterministic script, and forces an undocumented "pass absolute
paths" workaround.)
**Discovered:** 2026-07-17
**Placement:** docs/bugs/archive-fixed-relative-spec-path-valueerror
**Related:**
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` (Round 62) — this
  investigation is the Step-2.5 audit-trail artifact for that hardening round.
- `archive_fixed` provenance: promoted from prose to code after the 2026-06-10 incident
  (unstaged sentinel deletions + Windows rename lock broke the prose `git mv`); see the
  `archive_fixed` docstring in `lazy_core/gates.py`.

## Reconstructed route (harden-harness Step 1)

- **Trigger kind:** observed-friction (background, non-blocking) — orchestrator-observed mid-run
  harness gap; no probe/registry state (not a validate-deny / no-route failure).
- **Item in flight:** `adhoc-hydra-sidecar-dist-esm-no-frames`.
- **Divergence point:** the bug-pipeline archive step
  (`bug-state.py --repo-root . --archive-fixed docs/bugs/<id>`, wiring at
  `bug-state.py:8883-8889`). The intended act is the deterministic script-owned archive move.
  The actual path diverged when `archive_fixed`'s per-file `git mv` fallback dereferenced
  `spec_path.relative_to(repo_root)` on a relative `spec_path`, raising an uncaught `ValueError`.
- **Workaround used this run:** pass BOTH `spec_path` and `repo_root` as absolute Windows paths
  (with both absolute, `relative_to` succeeds).

## Root cause (harden-harness Step 2)

**Classification: `script-defect`** in `lazy_core/gates.py::archive_fixed`.

Evidence:

- `gates.py:1973` — `repo_root = repo_root.resolve()` normalizes `repo_root` to an ABSOLUTE
  path, but `spec_path` is never normalized (it is used as-passed from
  `Path(args.archive_fixed)`, `bug-state.py:8884-8885`).
- `gates.py:2104` — `rel_spec = spec_path.relative_to(repo_root).as_posix()` in the per-file
  `git mv` fallback. `Path.relative_to` requires `spec_path` to be under `repo_root`; a RELATIVE
  `spec_path` against an ABSOLUTE `repo_root` raises `ValueError`. (This `rel_spec` must be
  repo-relative so the `suffix = rel[len(rel_spec):]` strip at gates.py:2110 lines up with the
  repo-relative output of `git ls-files` — i.e. the correct fix anchors `spec_path` at
  `repo_root`, it does not drop the `relative_to`.)
- `gates.py:2213` — the sole `try/except` catches `(OSError, subprocess.SubprocessError)` only,
  so the `ValueError` is UNCAUGHT: the process dies with a raw traceback instead of returning
  the structured `{"refused": ...}` shape every other failure path uses.
- Contrast siblings: `verify_ledger` (gates.py:1253) drives git via `git -C <repo_root>` and
  reads `spec_path` directly — it never computes `spec_path.relative_to(repo_root)`, so a
  relative `spec_path` is harmless. `apply_pseudo` is likewise unaffected. Hence the surprise:
  the two subcommands an operator would compare against accept a relative `spec_path` fine.

Note on manifestation: the `relative_to` at gates.py:2104 lives in the fallback branch, which
engages only when the directory-level `git mv` fails (e.g. a transient Windows handle lock — the
exact 2026-06-10 condition the fallback exists to handle). The un-normalized `spec_path` is the
latent defect on every relative-path invocation; the crash surfaces when that fallback is
reached. The fix removes the latent defect regardless of which branch runs.

## Fix scope (harden-harness Step 3 — mechanical)

Normalize `spec_path` to an absolute path anchored at `repo_root` immediately after
`repo_root = repo_root.resolve()` in `archive_fixed`, so every downstream
`spec_path.relative_to(repo_root)` is well-defined regardless of whether the caller passed a
relative (`docs/bugs/<id>`) or absolute `spec_path`:

```python
repo_root = repo_root.resolve()
spec_path = Path(spec_path)
spec_path = spec_path.resolve() if spec_path.is_absolute() else (repo_root / spec_path).resolve()
```

This mirrors the repo-relative anchoring that `git ls-files` already assumes downstream, changes
no observable behavior for the already-working absolute-path invocation, and leaves every gate,
refusal, and provenance check intact (no gate-weakening). Regression-locked by a new test that
drives `archive_fixed` with a RELATIVE `spec_path` and asserts a clean archive (red before the
fix: the relative path, anchored at CWD rather than `repo_root`, resolves to a non-existent
directory and the call refuses "nothing to archive" instead of archiving).

## Related observation (SECONDARY — NOT fixed in this round; lower priority, distinct subsystem)

Reported alongside the primary friction: the `lazy-state.py` probe reports
`live_settings_ok=false` with detail *"tracked user/settings.json is missing/unreadable at
<repo>/user/settings.json"* for AlgoBooth. Root of the observation:
`lazy-state.py::live_settings_probe` (lazy-state.py:11392) passes the TARGET `repo_root` into
`doc-drift-lint.live_settings_status`, which reads `repo_root/user/settings.json`
(`doc-drift-lint.py:560-572`). The tracked-settings SSOT lives in **claude-config**, not in an
arbitrary target repo (AlgoBooth has no `user/` dir), so for any non-claude-config target repo
the check resolves the wrong path and reports a non-benign `False` (rather than either resolving
against claude-config or benign-skipping as "not applicable").

This is a real but **distinct** defect touching probe semantics, and it carries a small design
choice (resolve the tracked-settings path against claude-config always, vs. benign-skip the
check when the target repo has no tracked `user/settings.json`). It is deliberately scoped OUT
of this round to keep the primary mechanical fix clean and well-verified; captured here as a
follow-up candidate and relayed to the orchestrator. Verified far enough to name the mechanism
(`live_settings_probe` feeding the target `repo_root` straight through), not yet fixed.
