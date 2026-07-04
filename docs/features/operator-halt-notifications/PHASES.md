# Implementation Phases — Operator Paging on Pipeline Halts

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness mechanics (a `lazy_core.py` notifier +
two one-line state-script call sites). No Tauri app, no MCP-reachable surface; validation is
`pytest` (`test_lazy_core.py`, `test_lazy_parity.py`), the in-file `--test` smoke baselines, and
`lazy_parity_audit.py`. This is the `standalone — no app integration` untestable class →
`SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)` — substantive dependencies are already-shipped contracts, re-verified in
[`RESEARCH_SUMMARY.md`](./RESEARCH_SUMMARY.md):

- **harness-telemetry-ledger (freshly landed):** `--emit-prompt` already emits a `halt` telemetry
  event (`TELEMETRY_HALT_TERMINAL_REASONS`, 6 terminals, marker-gated). The notifier COMPOSES with
  it — telemetry records history, notify pages the operator — and shares no constant with it (the
  D3 attention set is a different, 11-element, operator-action-shaped list). The `notify_halt`
  call site lands AFTER the telemetry block, immediately before the final state-JSON write.
- **queue-dependency-dag (freshly landed):** its `queue-exhausted-dependency-gated` clean terminal
  is deliberately in NEITHER notify set (not attention, not a named clean stop) — dep-holds
  re-open by themselves.
- **multi-repo-concurrent-runs:** the ledger/breadcrumb live in the per-repo keyed
  `claude_state_dir()` (hermetic under `LAZY_STATE_DIR`), inheriting per-repo isolation for free.
- **mobile-queue-control:** the payload body names `LAZY_QUEUE.md` as the queue-wide view; the
  deep link lands on the item dir on GitHub mobile.
- **Coupled-pair discipline:** the call site is a NEW parity-audit surface (#7,
  `lazy_core.notify_halt(`) in `lazy_parity_audit.py::audit_state_script_parity`;
  `test_lazy_parity.py`'s lockstep stubs move six → seven surfaces in the same commit.

---

### Phase 1: Core helper (`lazy_core.notify_halt`)

**Phase kind:** design

**Scope:** The whole notifier as a self-contained, fail-OPEN `lazy_core` unit: config loader (D7),
attention/clean-stop frozensets (D3), sentinel-identity + dedup ledger (D4/D8), rich payload
composer (D5), ntfy sender behind the injected-`sender` seam (D1), breadcrumb + diagnostics on
failure (D9). No state-script change yet — probe output byte-identical.

**Deliverables:**
- [x] `lazy_core._NOTIFY_ATTENTION_TERMINALS` frozenset (the locked 11-terminal D3 list) +
  `_NOTIFY_CLEAN_STOP_TERMINALS` (the 5 named clean stops, gated on `notify_on_clean_stop`).
- [x] `lazy_core._load_notify_config()` — `LAZY_NOTIFY_DISABLE=1` kill switch → `None`;
  `~/.claude/notify.json` (`{channel, url, notify_on_clean_stop, reping_hours}`) merged with the
  `LAZY_NOTIFY_URL` env override (env url wins); absent both → `None` (complete no-op).
- [x] `lazy_core._notify_identity(state, repo_root, pipeline, ...)` — sentinel-backed terminals
  (`blocked` → `BLOCKED.md`, `needs-input` → `NEEDS_INPUT.md`, `blocked-misnamed` → the
  `detect_noncanonical_blocker` stray, `needs-research` → `NEEDS_RESEARCH.md`/`RESEARCH_PROMPT.md`)
  key on `(pipeline, item_id, terminal_reason, mtime_ns, size)`; sentinel-less terminals key on
  `(pipeline, item_id, terminal_reason, date)`.
- [x] `notify-ledger.json` read/write in `claude_state_dir()` via `_atomic_write` — `notified_at`
  per identity (re-ping-ready schema), entries older than 30 days dropped on write; ledger updated
  ONLY on a successful send.
- [x] Payload composer — title = `notify_message` verbatim; body = repo basename · pipeline ·
  item id · halt kind, `needs-input` `decisions:` one-liners via a tolerant frontmatter read,
  `LAZY_QUEUE.md` + answer-path pointer; link = GitHub tree URL from
  `git config --get remote.origin.url` (SSH→HTTPS normalized; failure ⇒ link omitted, still send).
- [x] `lazy_core._ntfy_send(url, title, body, link)` — stdlib `urllib`, `timeout=5`, RFC-2047
  header encoding for non-latin-1 titles; `notify_halt(state, repo_root, *, pipeline, sender=None,
  now=None)` dispatches through the injected `sender` seam (defaults to the ntfy binding).
- [x] Fail-OPEN wrapper — no exception propagates; on send failure write the `notify-error.json`
  breadcrumb (`_atomic_write`, single overwritten file) + append the "why no page" line to
  `state["diagnostics"]`; halt JSON/exit code unchanged.
- [x] `test_lazy_core.py` additions (registered in `_TESTS`): inert-without-config byte-identity
  (state dict deep-equal + zero state-dir writes), attention-set gating (incl. clean-stop opt-in
  both ways), dedup across repeated probes, identity refresh on sentinel rewrite/neutralize,
  ledger written via `_atomic_write` + 30-day prune, fail-OPEN on sender raise, breadcrumb write,
  payload shape (decisions + link + no-remote fallback), config loader precedence
  (disable > env url > file), RFC-2047 title encoding.

**Minimum Verifiable Behavior:** With `LAZY_NOTIFY_URL` set and a fake sender, a `needs-input`
state notifies exactly once across three `notify_halt` calls (ledger holds one entry); with no
config, the same calls leave the state dict and state dir byte-untouched.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] One halt pages once across repeated probes; ledger self-clears on sentinel neutralize+rewrite (second page, new identity). *(Evidence: `SKIP_MCP_TEST.md` — `test_lazy_core.py` notify suite.)* <!-- verification-only -->
- [x] Sender raise leaves halt JSON unchanged, writes `notify-error.json`, adds no ledger entry. *(Evidence: `test_lazy_core.py` fail-OPEN cases.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no
Tauri/MCP app). Verification is `pytest`.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

**Testing Strategy:** Hermetic `LAZY_STATE_DIR` temp dirs + injected `sender`/`now`; env vars
set/cleared per test; no network, no real `~/.claude` writes. TDD — each behavior's failing test
first.

**Integration Notes for Next Phase:** Phase 2 wires `lazy_core.notify_halt(state, args.repo_root,
pipeline=...)` as ONE line per script immediately before the final
`sys.stdout.write(json.dumps(state, ...))`, and adds parity surface #7.

---

### Phase 2: Wire both scripts (parity-coupled) + audit surface

**Phase kind:** integration

**Scope:** The two one-line call sites (D2 locked chokepoint); parity-audit surface #7 +
lockstep `test_lazy_parity.py` fixture updates (six → seven); in-file `--test` call-site fixtures
in BOTH scripts; baselines re-pinned via `_normalize_smoke_output` only.

**Deliverables:**
- [ ] `lazy-state.py` `main()`: `lazy_core.notify_halt(state, args.repo_root, pipeline="feature")`
  immediately before the state-JSON write (after the telemetry block — composes, never duplicates).
- [ ] `bug-state.py` `main()`: `lazy_core.notify_halt(state, args.repo_root, pipeline="bug")` at
  the mirrored point.
- [ ] `lazy_parity_audit.py`: `_NOTIFY_HALT_RE` surface #7 in `audit_state_script_parity` (both
  scripts must carry the call); audit stays exit 0 against the live tree.
- [ ] `test_lazy_parity.py`: lockstep stub updates (all `TestStateScriptParity` fixtures gain the
  `notify_halt` token; docstrings six → seven) + a new fires-when-missing test.
- [ ] In-file `--test` fixture in `lazy-state.py`: halt fixture + `LAZY_NOTIFY_URL` + monkeypatched
  module sender ⇒ driving `main()` twice produces EXACTLY one send (dedup on the second probe) and
  parseable halt JSON; inert leg (disable switch) byte-identical.
- [ ] In-file `--test` fixture in `bug-state.py`: same shape over a bug halt.
- [ ] Baselines (`tests/baselines/*-test-baseline.txt`) re-pinned ONLY by piping live `--test`
  output through `_normalize_smoke_output`.

**Minimum Verifiable Behavior:** `python3 lazy-state.py --test` and `python3 bug-state.py --test`
pass with the new call-site fixtures; `lazy_parity_audit.py --repo-root .` exits 0; deleting either
call site would flip the audit to a finding (proven by the parity-test negative fixture).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] A fixture halt with a fake sender produces exactly one payload carrying the D5 fields; repeated probes produce zero further sends. *(Evidence: in-file `--test` fixtures, both scripts.)* <!-- verification-only -->
- [ ] Parity audit green with both call sites; red when one is removed (negative fixture). *(Evidence: `test_lazy_parity.py` seven-surface suite.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** GitHub remote-URL derivation
  spot-check across the Windows workstation's real SSH/HTTPS remotes (this container's remote is a
  local git proxy; the normalizer is unit-tested against SSH/HTTPS/ssh:// fixture forms). <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (the helper + seams).

**Files likely modified:** `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`,
`user/scripts/lazy_parity_audit.py`, `user/scripts/test_lazy_parity.py`,
`user/scripts/tests/baselines/lazy-state-test-baseline.txt`,
`user/scripts/tests/baselines/bug-state-test-baseline.txt`.

**Testing Strategy:** The `--test` fixtures drive `main()` in-process (patched `sys.argv`,
captured stdout, hermetic `LAZY_STATE_DIR`/`LAZY_NOTIFY_URL`, module-level sender monkeypatch) so
the WIRING is exercised, not re-mocked. Parity fixtures follow the existing stub pattern exactly.

**Integration Notes for Next Phase:** Phase 3 is the live-channel leg — everything script-side is
now in place; only real-device/real-network evidence remains.

---

### Phase 3: Live channel + environment verification

**Phase kind:** integration

**Scope:** Real ntfy delivery evidence on the operator's phone (workstation manual `/lazy` halt +
a cloud run), and the breadcrumb path exercised against an unplugged URL. This phase is
environment-bound by nature: it needs the operator's phone, the real workstation, and a live cloud
run — none exist in this container.

**Deliverables:**
- [ ] The production sender path is complete and unit-verified (RFC-2047 headers, timeout=5,
  Click link) — nothing code-side remains for this phase.
- **DEFERRED (workstation-only, not a completion blocker):** operator receives a real page on the
  phone from a workstation manual `/lazy` step into a blocked fixture (screenshot-grade evidence),
  including the ntfy click-through → GitHub-mobile handoff. <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** cloud-run delivery with an
  env-provisioned `LAZY_NOTIFY_URL` — page received, or the proxy-blocked degrade captured as a
  live `notify-error.json` breadcrumb and documented. <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** breadcrumb path exercised live by
  unplugging the URL (the hermetic twin is covered by the Phase-1 fail-OPEN tests). <!-- verification-only -->

**Minimum Verifiable Behavior:** (deferred legs above) — the hermetic equivalents (fake sender,
raising sender, breadcrumb write) are all green in `test_lazy_core.py` and the `--test` fixtures.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- **DEFERRED (workstation-only, not a completion blocker):** real phone delivery with decisions +
  working deep link (SPEC Validation Criteria rows 7–8). <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 2.

**Files likely modified:** none (evidence-only phase).

**Testing Strategy:** Manual operator check per SPEC Validation Criteria rows "Real phone
delivery" / "Cloud reachability"; hermetic twins already pin the code paths.

**Integration Notes for Next Phase:** Phase 4 documents the config keys the operator will use for
the live legs.

---

### Phase 4: Opt-ins and docs

**Phase kind:** integration

**Scope:** `notify_on_clean_stop` opt-in (shipped in Phase 1's gating — documented here);
`reping_hours` stays a documented additive follow-up key (D4: ledger schema is re-ping-ready, the
key is parsed-but-inert in v1); doc rows in `user/scripts/CLAUDE.md` and the root `CLAUDE.md`
untracked-secrets list.

**Deliverables:**
- [ ] `user/scripts/CLAUDE.md`: an "Operator halt notifications" section — config file schema +
  env overrides, the attention/clean-stop sets, ledger/breadcrumb residency, fail-OPEN semantics,
  the §1c.6 coexistence note, and the parity surface #7 row.
- [ ] Root `CLAUDE.md`: `notify.json` added to the untracked-secrets list ("What's NOT Tracked").
- [ ] `notify_on_clean_stop` behavior documented (opt-in flips the 5 named clean stops into the
  notify set); `reping_hours` documented as accepted-but-inert (schema-ready for D4-B).
- [ ] Lint/projection clean (no SKILL.md/component edits in this feature; `lint-skills.py` green).

**Minimum Verifiable Behavior:** Docs reference the real keys/filenames the code reads
(`notify.json`, `LAZY_NOTIFY_URL`, `LAZY_NOTIFY_DISABLE`, `notify-ledger.json`,
`notify-error.json`); gate suite green.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] Doc keys match code constants (grep-verified names in both CLAUDE.md files vs `lazy_core.py`). *(Evidence: gate suite + manual grep at commit time.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2.

**Files likely modified:** `user/scripts/CLAUDE.md`, `CLAUDE.md` (root).

**Testing Strategy:** Docs-only phase; the gate suite (incl. `lint-skills.py`) proves nothing
regressed.
