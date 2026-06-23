# Lazy Queue — claude-config   (run active 🔒)

## Features (0)


## Bugs (1)

| # | item | state | sev |
|---|------|-------|------|
| 1 | [adhoc-ensure-runtime-test-injects-signal-under-test](docs/bugs/adhoc-ensure-runtime-test-injects-signal-under-test/SPEC.md) | Validate | P1 |
| | status: Validate · phase 3/3 · next: run mcp-test · The `ensure_runtime` cold-boot/runtime-recovery "production-binding" tests in `test_lazy_core.py` reach green by injecting a hand-set stand-in for the very OS-level signal whose production derivation is under test — so a defect in that derivation ships behind a green test (a recurring false-green; three rounds). | | |
