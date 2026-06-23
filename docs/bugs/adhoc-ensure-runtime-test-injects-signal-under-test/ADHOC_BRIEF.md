# Ad-hoc bug: ensure_runtime production-binding tests fake the OS signal they verify

**Origin:** harden-harness Round 33 (over-fit spin-off; mechanical fix committed
separately). Cross-reference: `docs/specs/turn-routing-enforcement/hardening-log/2026-06.md`
Round 33, and Round 32 (the first occurrence of the class).

## The class (smallest subsuming the observed instances)

`ensure_runtime`'s production boot-liveness / runtime-recovery tests in
`user/scripts/test_lazy_core.py` that claim to exercise the **production
derivation** of an OS-level signal, but do so by **injecting a fake of the exact
signal whose production derivation is the thing under test** — so a green test
cannot catch a defect in that derivation. This is a concrete, recurring instance
of the "five false-green smells" (a test faking the subject of the assertion).

### Cited instances (evidence)

1. **Round 32** (`a9ab567`): added `test_ensure_runtime_production_boot_alive_live_handle_patient_waits`
   which fed a `_FakeBootPopen` whose `.poll()` **stays None**. It asserted
   "exactly ONE spawn" but reached that green via the recovery loop, NEVER
   exercising the Windows reality where the `npm run dev:restart` cmd/npm wrapper
   `Popen` **exits early** (`.poll()` returns an exit code) while the detached
   `tauri dev`/`cargo build` child keeps compiling for ~3.5 min. The test passed
   782/782; production STILL starved the cold boot (5 kill-restarts in ~60s →
   false `mcp-runtime-unready` BLOCKED on `d2-sample-import-ui`).

2. **Round 33** (this round): the refix had to ADD a production-faithful
   reproducing test that drives the **exited-handle + fresh-stamp** condition
   (`test_ensure_runtime_production_wrapper_exits_early_patient_waits_one_spawn`
   and its M4 sibling) — i.e. it had to reproduce the OS timing/condition rather
   than fake the signal — and update the Round-32 dead-handle test whose
   expectation was premised on the now-removed wrapper-handle-only signal.

### Class boundary

- **IN:** any `ensure_runtime` (or `_recover_runtime` / `_await_compile_serving` /
  `boot_alive`) production-binding test that injects a stand-in for an OS-level
  liveness/timing signal (`Popen.poll()`, process-tree liveness, wall-clock grace)
  and then asserts behavior that depends on that signal's **production
  derivation**. The durable fix is a test-discipline guard / pattern that forces
  such tests to drive a production-faithful OS condition (the real default
  `restart`/clock/stamp seam) rather than a hand-set return value of the subject.
- **OUT:** tests that legitimately inject `probe`/`stale_check`/`sidecar_check`
  (genuinely external dependencies the harness OWNS no derivation of — mocking
  them is correct), and the hermetic `--test` contract itself (injection is the
  right tool for a genuinely external collaborator; the smell is ONLY when the
  injected thing is the very derivation under test).

## What to do

Investigate (`/spec-bug`) whether harden-harness (or a `test_lazy_core` lint/guard)
can mechanically flag a "production-binding" test that fakes the signal it
verifies — e.g. a naming/structure convention plus a check that any test claiming
to bind the production `boot_alive`/`restart` derivation routes through the real
default closures (swapping `lazy_core.subprocess`/`lazy_core.time`) rather than
injecting `boot_alive=`/`restart=` directly. The goal: a future production-only
derivation defect cannot ship behind a green "production-binding" test again.

Do NOT widen beyond the cited instances + their near neighbors (the runtime-ensure
production-derivation tests). A speculative repo-wide false-green linter is out of
scope for this bug.
