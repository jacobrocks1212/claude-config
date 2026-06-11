# Implementation Phases — Digestible Content

> Phases for [`SPEC.md`](./SPEC.md)

---

### Phase 1: Evaluation Engine

**Scope:** Build `SurfacingEvaluator` — the class that takes a work log entry, loads the compact KB index, invokes headless Claude haiku via subprocess (reusing the `HeadlessJudge` subprocess pattern), and returns a structured binary surface/no-surface result.

**Risk:** High — new subprocess call with a new prompt schema; parsing of a binary response with conditional fields requires careful validation against malformed/partial outputs.

**Deliverables:**
- [x] New file `servers/work_logging_mcp/surfacing.py` with `SurfacingEvaluator` class
- [x] `SurfacingResult` TypedDict: `{"surface": bool, "slug": str | None, "domain": str | None, "summary": str | None}`
- [x] `SurfacingEvaluator.__init__(self, model: str = "haiku", timeout: int = 60)` — mirrors `HeadlessJudge.__init__` signature
- [x] `SurfacingEvaluator.evaluate(self, entry: dict[str, Any], kb_entries: list[dict[str, Any]]) -> SurfacingResult`
  - Builds compact KB index lines: `{slug} ({domain}): {description}` for all 154 topics
  - Constructs evaluation prompt using `_SURFACING_PROMPT_TEMPLATE` (module-level constant)
  - Calls `subprocess.run([_CLAUDE_BIN, "-p", "-", "--model", self._model, "--output-format", "json"], capture_output=True, input=prompt.encode(), timeout=self._timeout)` — identical to `headless_judge.py` pattern
  - Parses outer JSON envelope via `_parse_outer()` (import or inline copy from `headless_judge.py`)
  - Extracts inner JSON via `_extract_json()` (same)
  - Validates: `surface` key present and is bool; if `True`, also validates `slug`, `domain`, `summary` are non-empty strings
  - Returns `SurfacingResult(surface=False)` on any parse/subprocess failure (never raises)
- [x] Module-level `_SURFACING_PROMPT_TEMPLATE` constant matching the prompt from SPEC.md §2 (haiku evaluation prompt section)
- [x] Test file `tests/test_surfacing.py`
  - `test_evaluate_surface_true_parses_correctly()` — mock subprocess returns `{"surface": true, "slug": "rate-limiting", "domain": "system-design", "summary": "..."}`, assert result fields
  - `test_evaluate_surface_false_parses_correctly()` — mock returns `{"surface": false}`, assert `result.surface is False`, `result.slug is None`
  - `test_evaluate_handles_malformed_json()` — mock returns non-JSON stdout, assert returns `surface=False`
  - `test_evaluate_handles_subprocess_failure()` — mock raises `subprocess.CalledProcessError`, assert returns `surface=False`
  - `test_evaluate_handles_missing_slug_on_surface_true()` — mock returns `{"surface": true}` (missing slug), assert treated as `surface=False`
  - `test_prompt_contains_entry_fields()` — capture `subprocess.run` `input` kwarg, assert `title`, `summary`, `project` from entry are in prompt
  - `test_prompt_contains_kb_entries()` — assert at least one slug from `kb_entries` appears in prompt
  - `test_evaluate_handles_markdown_fenced_response()` — mock returns response wrapped in ` ```json ``` `, assert parsed correctly

**Prerequisites:** None — pure new module; depends only on existing `headless_judge.py` utilities (can inline or import `_parse_outer`, `_extract_json`, `_CLAUDE_BIN`).

**Files likely modified:**
- `servers/work_logging_mcp/surfacing.py` — NEW: `SurfacingEvaluator`, `SurfacingResult`, `_SURFACING_PROMPT_TEMPLATE`
- `servers/work_logging_mcp/headless_judge.py` — optionally export `_parse_outer`, `_extract_json`, `_CLAUDE_BIN` as public helpers (or inline in surfacing.py)
- `tests/test_surfacing.py` — NEW: 8 unit tests mocking `subprocess.run`

**Testing Strategy:** All tests mock `servers.work_logging_mcp.surfacing.subprocess.run`. Use `_make_mock_result(payload)` helper (same pattern as `test_headless_judge.py`). Verify `SurfacingResult` fields on both branches. Verify graceful fallback on every failure mode. Run `mypy --strict` on `surfacing.py`.

**Integration Notes for Next Phase:**
- `SurfacingEvaluator` is the only dependency Phase 3's `evaluate_and_notify.py` needs from this module
- `KnowledgeBank.entries` is the KB source; Phase 3 instantiates `KnowledgeBank` and maps to `dict[str, Any]` list before calling `evaluate()`
- Keep `SurfacingResult` as a TypedDict (not dataclass) for easy JSON serialization in the surfacing log (Phase 4)

**Implementation Notes:**
- Imported `_CLAUDE_BIN`, `_parse_outer`, `_extract_json` directly from `headless_judge.py` (no rename needed)
- Technologies/patterns lists joined with ", " for prompt formatting
- All 8 tests pass, mypy strict clean

---

### Phase 2: ntfy.sh Client

**Scope:** Build `NtfyNotifier` — an HTTP client class that constructs and POSTs the ntfy.sh notification payload with title, body, `copy` action, tags, and optional auth header. Extend `config.json` schema to hold ntfy settings.

**Risk:** Medium — HTTP client with no new third-party dependencies; edge cases around auth headers, action syntax, and HTTP error responses need explicit coverage.

**Deliverables:**
- [x] New file `servers/work_logging_mcp/ntfy.py` with `NtfyNotifier` class and `NtfyConfig` TypedDict
- [x] `NtfyConfig` TypedDict: `{"topic_url": str, "token": str | None}` — loaded from `config.json` at key `"ntfy"`
- [x] `NtfyNotifier.__init__(self, config: NtfyConfig)` — stores config, no I/O
- [x] `NtfyNotifier.notify(self, topic_name: str, slug: str, domain: str, summary: str) -> bool`
  - Constructs request: `POST {config["topic_url"]}`
  - Headers: `Title: 📚 {topic_name}`, `Tags: {domain}`, `Actions: copy, Study, study /interview-study {slug}`, `Content-Type: text/plain`
  - If `config["token"]`: add `Authorization: Bearer {token}` header
  - Body: `summary` encoded as UTF-8 bytes
  - Uses `urllib.request.urlopen` with `urllib.request.Request` (stdlib only — no new deps)
  - Timeout: 10 seconds
  - Returns `True` on 2xx, `False` on any error (logs warning, never raises)
- [x] `load_ntfy_config(base_path: Path = _DEFAULT_BASE) -> NtfyConfig | None` — module-level helper; reads `config.json`, returns `None` if `"ntfy"` key absent or `topic_url` empty
- [x] Test file `tests/test_ntfy.py`
  - `test_notify_sends_correct_headers()` — mock `urllib.request.urlopen`, assert `Title`, `Tags`, `Actions` headers on the `Request` object
  - `test_notify_sends_auth_header_when_token_present()` — assert `Authorization: Bearer <token>` header present
  - `test_notify_omits_auth_header_when_token_none()` — assert no `Authorization` header
  - `test_notify_sends_correct_body()` — assert body is `summary.encode("utf-8")`
  - `test_notify_returns_true_on_success()` — mock returns HTTP 200, assert `True`
  - `test_notify_returns_false_on_http_error()` — mock raises `urllib.error.HTTPError(None, 403, ...)`, assert `False`
  - `test_notify_returns_false_on_timeout()` — mock raises `TimeoutError`, assert `False`
  - `test_load_ntfy_config_returns_config_when_present()` — write temp `config.json` with `"ntfy"` key, assert returned config
  - `test_load_ntfy_config_returns_none_when_absent()` — write `config.json` without `"ntfy"` key, assert `None`

**Prerequisites:** Phase 1 complete (conceptually independent, but both are needed in Phase 3's wiring).

**Files likely modified:**
- `servers/work_logging_mcp/ntfy.py` — NEW: `NtfyNotifier`, `NtfyConfig`, `load_ntfy_config`
- `tests/test_ntfy.py` — NEW: 9 unit tests
- `servers/work_logging_mcp/persistence.py` — no changes required; `config.json` is already managed by `ConfigReader`; `load_ntfy_config` reads it independently

**Testing Strategy:** Mock `urllib.request.urlopen` at `servers.work_logging_mcp.ntfy.urllib.request.urlopen`. Capture the `Request` object passed to `urlopen` and assert `get_header()` values. Use `tmp_path` pytest fixture for config file tests. Run `mypy --strict` on `ntfy.py`.

**Integration Notes for Next Phase:**
- `evaluate_and_notify.py` in Phase 3 calls `load_ntfy_config()` and instantiates `NtfyNotifier(config)` — if config is `None`, skip notification silently (log to surfacing log with `notified=False, reason="ntfy_not_configured"`)
- The `topic_name` passed to `notify()` comes from `KnowledgeBankEntry.name` — Phase 3 must look up the entry by slug after evaluation
- Keep `ntfy.py` import-free from the rest of the plugin package to allow standalone use in `evaluate_and_notify.py` with minimal `sys.path` manipulation

**Implementation Notes:**
- Headers set via `Request` constructor dict (not `add_header`) for correct casing with `get_header()`
- `Content-type` casing matches urllib's internal normalization
- All 9 tests pass, mypy strict clean

---

### Phase 3: Hook + CLI Entrypoint

**Scope:** Wire Phase 1 and Phase 2 into a working end-to-end pipeline: `hooks/evaluate-surfacing.sh` (PostToolUse hook), `scripts/evaluate_and_notify.py` (detached entrypoint), and hook registration in the plugin config.

**Risk:** Medium — Windows process spawning with `pythonw.exe` + `cmd //c start` is platform-specific and hard to test automatically; hook stdin JSON parsing has edge cases; temp file cleanup must be in a `finally` block.

**Deliverables:**
- [x] New directory `hooks/` at repo root
- [x] New file `hooks/evaluate-surfacing.sh` — PostToolUse hook script per SPEC.md §1
  - Reads full stdin JSON into `$INPUT`
  - Filters: extracts `tool_name` field via `python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))"`, exits 0 if not matching `*work_log_append*`
  - Extracts `tool_input` to temp file via inline Python: `json.dump(data.get('tool_input', {}), open('$TEMP_FILE', 'w'))`
  - Spawns: `cmd //c start "" pythonw.exe "$SCRIPT_DIR/evaluate_and_notify.py" "$TEMP_FILE" &>/dev/null`
  - Exits 0 immediately after spawn (non-blocking)
- [x] New file `scripts/evaluate_and_notify.py` — standalone CLI entrypoint
  - `sys.path.insert(0, ...)` pattern (same as `scripts/correlate_headless.py`) to import from `servers/`
  - Accepts single positional arg: path to temp JSON file
  - Reads and JSON-parses the temp file
  - Instantiates `KnowledgeBank(Path.home() / ".interview-prep" / "knowledge-bank")`, maps entries to `list[dict[str, Any]]`
  - Instantiates `SurfacingEvaluator()`, calls `evaluate(entry, kb_entries)`
  - If `surface=True`: looks up `KnowledgeBankEntry` by slug to get `topic_name`, calls `NtfyNotifier(config).notify(topic_name, slug, domain, summary)` — skips if `load_ntfy_config()` returns `None`
  - Cleans up temp file in `finally` block
  - Logs outcome to `~/.interview-prep/surfacing-log.jsonl` (Phase 4 formalizes this; Phase 3 uses a simple `json.dumps` + file append inline)
  - All errors caught at top level: logged to `~/.interview-prep/surfacing-errors.log`, then `sys.exit(0)` (never let the detached process crash visibly)
- [x] Hook registration in `.claude-plugin/hooks.json` (new file if not exists): `{"postToolUse": [{"script": "./hooks/evaluate-surfacing.sh"}]}`
  - OR register via `settings.json` pattern if that's how Claude Code discovers hooks — verify against plugin manifest
- [x] Test file `tests/test_evaluate_and_notify.py`
  - `test_main_calls_evaluator_with_entry()` — write temp JSON, mock `SurfacingEvaluator.evaluate` returning `surface=False`, assert called with correct entry dict
  - `test_main_notifies_when_surface_true()` — mock evaluator returns `surface=True, slug="rate-limiting", domain="system-design", summary="..."`, mock `NtfyNotifier.notify`, assert `notify()` called
  - `test_main_skips_notify_when_ntfy_not_configured()` — `load_ntfy_config` returns `None`, assert `NtfyNotifier` never instantiated
  - `test_main_cleans_up_temp_file_on_success()` — assert temp file deleted after run
  - `test_main_cleans_up_temp_file_on_evaluator_error()` — mock evaluator raises, assert temp file still deleted
  - `test_main_exits_0_on_missing_temp_file()` — pass nonexistent path, assert no unhandled exception
- [ ] Manually verify end-to-end on Windows: trigger `work_log_append` via Claude Code, observe no `conhost.exe` flash, check `surfacing-log.jsonl` for new entry

**Implementation Notes:**
- Fixed `kb.get_by_slug_and_domain()` → `kb.get()` to match real KnowledgeBank API
- Inline surfacing log append (Phase 4 replaces with SurfacingLogWriter)
- Hook registered in `.claude-plugin/hooks.json`, plugin.json updated with `"hooks"` key
- All 6 tests pass, mypy strict clean, 170 total tests pass

**Prerequisites:** Phase 1 (`SurfacingEvaluator`) and Phase 2 (`NtfyNotifier`, `load_ntfy_config`) complete.

**Files likely modified:**
- `hooks/evaluate-surfacing.sh` — NEW: PostToolUse hook script
- `hooks/` — NEW directory
- `scripts/evaluate_and_notify.py` — NEW: CLI entrypoint (~80 lines)
- `.claude-plugin/hooks.json` — NEW (or update plugin manifest to register hook)
- `.claude-plugin/plugin.json` — possibly add `"hooks"` key pointing to `hooks.json`
- `tests/test_evaluate_and_notify.py` — NEW: 6 tests using `tmp_path` fixture

**Testing Strategy:** `test_evaluate_and_notify.py` imports and calls `main(temp_file_path)` directly (extract from `if __name__ == "__main__"` block into a callable `main(path: str) -> None`). Mock `SurfacingEvaluator`, `NtfyNotifier`, `load_ntfy_config`, and `KnowledgeBank` at the `scripts.evaluate_and_notify` module level. The hook shell script logic is validated manually + by inspecting the generated temp file in integration testing.

**Integration Notes for Next Phase:**
- Phase 4 replaces the inline surfacing-log append in `evaluate_and_notify.py` with a `SurfacingLogWriter` (or equivalent utility), but the log schema is established here — define it now: `{timestamp, work_title, work_project, surfaced, topic_slug, topic_domain, summary, notified}`
- If the hook registration format isn't supported by the current plugin manifest version, escalate to a manual `settings.json` `hooks` entry in Phase 4

---

### Phase 4: Study Wrapper + Hardening

**Scope:** Add the `~/.local/bin/study` wrapper, formalize the surfacing log as a proper append utility, harden error logging, ensure temp file cleanup is airtight, and document setup for ntfy clients.

**Risk:** Low — primarily error paths, logging utilities, and a single wrapper script; no new integration surfaces.

**Deliverables:**
- [x] New file `~/.local/bin/study` (bash wrapper script, installed outside the repo)
  - Content per SPEC.md §4: `export CLAUDE_CONFIG_DIR="$HOME/.claude-personal"` + `exec claude --dangerously-skip-permissions --model claude-opus-4-6 "$@"`
  - Mark executable: `chmod +x ~/.local/bin/study`
  - Verify `~/.local/bin` is on `$PATH` (document in setup notes if not)
- [x] `SurfacingLogWriter` utility in `servers/work_logging_mcp/surfacing.py` (or inline in `persistence.py` — keep consistent with `WorkLogWriter` pattern)
  - `SurfacingLogWriter(base_path: Path = _DEFAULT_BASE)`
  - `append(self, entry: dict[str, Any]) -> None` — stamps `timestamp`, appends to `surfacing-log.jsonl`
  - Schema: `timestamp`, `work_title`, `work_project`, `surfaced` (bool), `topic_slug` (str | None), `topic_domain` (str | None), `summary` (str | None), `notified` (bool)
  - No auto-commit (diagnostic log only)
- [x] Refactor `scripts/evaluate_and_notify.py` to use `SurfacingLogWriter` instead of inline append
- [x] Error logging in `evaluate_and_notify.py`: `except Exception as exc:` at top-level wraps entire run; appends `f"{datetime.now(UTC).isoformat()} ERROR: {exc}\n{traceback.format_exc()}\n"` to `~/.interview-prep/surfacing-errors.log`; then `sys.exit(0)`
- [x] Verify `finally: temp_file_path.unlink(missing_ok=True)` is present and correct (no double-unlink on success path)
- [x] Review `/interview-study` skill (`skills/interview-study/SKILL.md`) — confirm no changes needed for surfacing-triggered sessions; skill already loads context via `get_study_context` at runtime
- [x] Test file `tests/test_surfacing_log.py`
  - `test_surfacing_log_writer_appends_entry()` — assert entry written to `surfacing-log.jsonl`
  - `test_surfacing_log_writer_stamps_timestamp()` — assert `timestamp` key present and ISO format
  - `test_surfacing_log_writer_does_not_auto_commit()` — use tmp dir without `.git`, assert no git subprocess called
  - `test_evaluate_and_notify_logs_surfaced_true()` — mock all externals, assert `surfacing-log.jsonl` contains `"surfaced": true`
  - `test_evaluate_and_notify_logs_surfaced_false()` — assert `surfacing-log.jsonl` contains `"surfaced": false`
  - `test_evaluate_and_notify_logs_error_on_exception()` — mock evaluator raises, assert `surfacing-errors.log` created with traceback text
- [x] Run full quality gate suite: `mypy --strict servers/ scripts/`, `ruff check .`, `ruff format --check .`, `pytest tests/ -v`
- [ ] Manually verify complete flow: log a work entry → hook fires → notification appears on Windows ntfy-desktop → "Study" button copies `study /interview-study <slug>` → paste in terminal → Claude Opus opens with `/interview-study` pre-invoked

**Implementation Notes:**
- `SurfacingLogWriter` added to `surfacing.py` (co-located with evaluator, not persistence.py)
- `_log_error()` helper writes timestamped traceback to `surfacing-errors.log`
- `/interview-study` skill confirmed compatible — accepts slug argument, no changes needed
- 176 total tests pass, mypy strict clean, ruff clean

**Prerequisites:** Phase 3 complete. `ntfy-desktop` installed on Windows 11. `ntfy` app installed on Pixel 10. ntfy.sh topic created with access token. `~/.interview-prep/config.json` updated with `"ntfy": {"topic_url": "...", "token": "..."}`.

**Files likely modified:**
- `servers/work_logging_mcp/surfacing.py` — add `SurfacingLogWriter` class (or `persistence.py` if keeping all writers co-located)
- `scripts/evaluate_and_notify.py` — use `SurfacingLogWriter`; add top-level try/except with error log; verify `finally` cleanup
- `tests/test_surfacing_log.py` — NEW: 6 tests
- `tests/test_evaluate_and_notify.py` — extend with error-log and surfacing-log assertions (tests added to existing file)
- `~/.local/bin/study` — NEW (installed on host, not in repo)
- `skills/interview-study/SKILL.md` — review only; modify if surfacing-triggered sessions need a different preamble

**Testing Strategy:** All tests use `tmp_path` fixture for file I/O. `SurfacingLogWriter` tests follow `WorkLogWriter` test patterns from `tests/test_persistence.py`. Error log test mocks `SurfacingEvaluator` to raise and asserts file contents with `Path.read_text()`. Manual end-to-end verification is the gate for this phase — automated tests cover the logic paths, but the Windows process-spawning + toast notification path requires hands-on confirmation.
