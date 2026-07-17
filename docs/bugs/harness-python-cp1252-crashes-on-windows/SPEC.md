# Bug: harness Python crashes on Windows under the default cp1252 codec

**Status:** Concluded
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage; discovered Round 48, fixed Round 49); `docs/features/anti-overfit-design-gate/` (`harness-gate.py` is the mechanical over-fit floor)

## Symptom (verified)

On a stock Windows Python (no `PYTHONUTF8` / `PYTHONIOENCODING` set), `sys.stdout.encoding`
and `locale.getpreferredencoding()` are both `cp1252`. Three harness surfaces crash:

1. **`harness-gate.py`** — the anti-overfit / gate-weakening mechanical gate. Over a `git diff`
   whose output contains a byte undefined in cp1252 (e.g. `Í` = UTF-8 `C3 8D`; `0x8D` is
   unmapped in cp1252), it raises `UnicodeDecodeError` **inside the subprocess reader thread**,
   which leaves `proc.stdout is None` while git's own returncode is `0`. `_run_git` therefore
   returns `(0, None, "")`, and `parse_diff(None)` crashes with
   `AttributeError: 'NoneType' object has no attribute 'splitlines'`. The gate silently cannot
   run natively on Windows — the harden pipeline's OWN over-fit floor is dark on this workstation.

2. **`lazy-state.py --test`** and **`bug-state.py --test`** — the smoke-test harnesses print a
   step description containing `→` (U+2192) to stdout; encoding it to cp1252 raises
   `UnicodeEncodeError: 'charmap' codec can't encode character '→'`.

All three run clean under `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`. Pre-existing; orthogonal to
any recent change (discovered incidentally during Round 48).

## Reproduction

- `harness-gate.py`: staged diff containing `printf 'Í arrow \xe2\x86\x92'` in an in-scope file →
  `UnicodeDecodeError (byte 0x8d)` in the reader thread + downstream `NoneType.splitlines()`.
- `python user/scripts/lazy-state.py --test` → `UnicodeEncodeError '→'` in `run_smoke_tests`.
- `python user/scripts/bug-state.py --test` → same.

## Root cause (proven)

**script-defect** — reliance on the ambient locale codec (`cp1252` on Windows) instead of an
explicit UTF-8 contract, in two distinct sub-classes:

- **subprocess reads:** `subprocess.run(..., text=True)` with no `encoding=` decodes child stdout
  with `locale.getpreferredencoding()`. Git emits UTF-8; cp1252 cannot decode ~5 undefined byte
  slots (`0x81/0x8D/0x8F/0x90/0x9D`), so any git output carrying such a byte (filenames, commit
  subjects, diff bodies) raises in the reader thread. Because the decode happens off-thread,
  `capture_output`/`text` returns `None` for the failed stream with `returncode` still `0` —
  callers that don't guard `None` crash downstream (`harness-gate.py: parse_diff(None)`).
- **stdout writes:** printing a non-ASCII literal (`→`, and other markers like `✓ ✗ ⚠ …`) to a
  cp1252-backed `sys.stdout` raises `UnicodeEncodeError`.

## Fix scope

At the source, robustly and consistently — do NOT rely on the ambient locale codec:

- **`harness-gate.py`** `_run_git`: pass `encoding="utf-8", errors="replace"`; return
  `proc.stdout or ""` / `proc.stderr or ""` so a failed/empty read degrades to `""` instead of
  crashing `parse_diff` (kills the `NoneType.splitlines()` class permanently). Keep the script
  dependency-free (stdlib only) — its JSON output is already ASCII (`json.dumps` default
  `ensure_ascii=True`), so it needs no stdout reconfigure.
- **`lazy-state.py` / `bug-state.py`**: reconfigure `sys.stdout`/`sys.stderr` to UTF-8
  (`errors="replace"`) once at the top of `main()` via a shared stdlib helper. One call fixes
  ALL non-ASCII prints in each script, not just the `→` in `--test` (over an ad-hoc per-print
  guard).
- **Near-neighbor content reads** (git output that can carry non-ASCII bytes → same decode
  crash): the shared git helpers `lazy_core/runtimeplane.py::_git` and
  `lazy_core/ledgers.py::_git_capture_lines`, plus the inline reads in `lazy_core/gates.py`
  (`_git_diff_name_only`, `git status --short`) and `lazy_core/ledgers.py` (`git log --format=%s`
  commit subject) — add `encoding="utf-8", errors="replace"`.
- **Deliberately left** (cannot crash — output is format-constrained ASCII: hex SHAs from
  `rev-parse`, integer counts from `rev-list`, ISO/short dates from `%cI`/`%cs`, remote/config
  URLs, branch names from `--abbrev-ref`) and the `run_smoke_tests` test-fixture git spawns that
  read child ASCII. Logged in the Round 49 near-neighbor sweep. The durable, class-level guard
  (a mechanical lint that FLAGS any text-mode `subprocess` read without an explicit `encoding=`,
  and requires CLI entrypoints to reconfigure stdio) is the over-fit spin-off of Round 49.
