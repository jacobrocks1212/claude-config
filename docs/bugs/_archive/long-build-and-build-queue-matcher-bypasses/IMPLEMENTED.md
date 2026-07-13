---
kind: implemented
feature_id: long-build-and-build-queue-matcher-bypasses
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** Empirically verified matcher-coverage gaps in two request-time guards: the long-build ownership guard allows every runner-prefixed / path-prefixed / string-wrapped form of the builds it exists to redirect (`npx tauri build`, `npm run tauri build` — the canonical Tauri invocation — `cargo tauri build`, absolute-path `cargo build --release`, `bash -c "..."`), and the build-queue enforce hook's wrapper allowlist is an **unanchored substring** checked before the deny scan, so any command merely *mentioning* `build-queue.ps1` bypasses the entire deny surface. Both errors are one-sided in the allow direction (under-blocking) — the guards are alive, their matchers are just narrower than the invocations they govern.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
