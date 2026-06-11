<!-- AlgoBooth repo hook for /investigate: how to drive THIS repo's live system.
     Served into AlgoBooth via the .claude/skill-config symlink. -->

**AlgoBooth runtime access for investigations:**

- **Boot/reuse the dev app** per `docs/development/CLAUDE.md` (Vite + MCP server + sidecar;
  readiness gates documented there). Resolve the CURRENT `logs/session-*/` directory FRESH on
  every probe — NEVER cache a session path; each app restart creates a new one.
- **Binary freshness:** after any Rust rebuild, verify the rebuilt code is actually live before
  trusting observations (boot-time log lines for new wiring, or a `[DIAG]` marker you added).
  A prior investigation lost a full verdict to a half-linked binary — the runtime held the
  build lock and the Rust half never linked.
- **Drive real input:** `update_code` (real pattern), `inject_midi`, `load_test_tone`
  (synthetic audio through the full pipeline).
- **Observe real output:** `get_audio_buffer` (POST, `capture` feature — interleaved samples +
  `rms`/`max_discontinuity`/`dc_offset` + ground-truth `scheduler_playing`), `audio_filter` and
  the audio-quality tools, `get_console_logs` / `get_session_events` (POST), session
  `app.jsonl` greps. Authoritative tool list + HTTP methods: `MCP_USAGE_GUIDE.md` +
  `src-tauri/src/ipc/mcp/registrations/mod.rs` — several `get_*` tools are POST; do NOT infer
  the method from the name.
- **Instrumentation placement:** one-off `tracing::warn!` / `console.error('[DIAG] …')` at
  NON-hot-path boundaries only (capnp decode site, sidecar stderr, command-drain entry).
  **NEVER instrument the audio-callback hot path** (`crates/audio-engine/src/{voice,callback,
  dattorro,convolution,...}`) — read `crates/audio-engine/INVARIANTS.md` BEFORE touching any
  file there; the ArcSwap Guard-across-`Arc<dyn Trait>` NO-OP invariant has burned two features.
- **Scheduler liveness:** before reading any "zero events" observation as a code defect,
  confirm the scheduler is actually playing (`scheduler_playing` from `get_audio_buffer`, or
  the session events) — a racy drive against a stopped scheduler produced a false negative in
  a prior live diagnostic.
