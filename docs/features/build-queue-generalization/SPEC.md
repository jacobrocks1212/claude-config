# Generalize Build-Queue Beyond Cognito — Feature Specification

> The FIFO serializer, hygiene sweeps, and outcome banners are Cognito-only, but AlgoBooth has the exact same problem class (`long-build-and-runtime-ownership`: `tauri build`/`cargo build --release`). Extract a config-driven per-repo ops manifest so any repo can register heavy ops into the same machine-global queue.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

`build-queue.ps1`'s op table, enforcement hook scoping (git remote `cognitoforms/cognito`), and
hygiene sweeps (VBCSCompiler recycle, DLL quarantine) are hard-wired to one repo. Other repos
solve the same "one heavy build at a time on this machine" problem ad-hoc (orchestrator-owned
transient builds) with no queueing, hygiene, or authoritative outcome banner.

## Direction (deliberately not locked)

- **Ops manifest:** per-repo `.claude/skill-config/build-queue-ops.md` (or JSON) declaring op
  names → filtered-script commands + hygiene profile; the wrapper/runner become repo-agnostic.
- **Hygiene profiles:** Cognito keeps VBCSCompiler/DLL sweeps; Rust/Tauri gets its own profile
  (target-dir hygiene, no-op recycle) — profile selection by manifest, not hard-code.
- **Enforcement:** `build-queue-enforce.sh` reads the manifest to decide which raw invocations to
  deny per repo, replacing the remote-match special case.
- **Composition:** must respect the `long-build-ownership-guard.sh` orchestrator-takeover contract
  rather than fighting it.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: manifest schema; queue fairness
> across repos; PowerShell dependency on non-Windows hosts; migration path for the four Cognito
> skills. Solutions above are directional, not locked.
