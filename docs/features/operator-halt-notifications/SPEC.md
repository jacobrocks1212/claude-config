# Operator Paging on Pipeline Halts — Feature Specification

> A `NEEDS_INPUT.md`/`BLOCKED.md` halt currently sits silently until the operator checks in — a
> batch run can idle for hours on a decision that takes ten seconds to answer. This feature wires a
> **script-owned notifier** into the state scripts' halt path: a shared `lazy_core.notify_halt()`
> helper, called by both `lazy-state.py` and `bug-state.py` at the terminal-emission chokepoint,
> pushes the halt (kind, item, the sentinel's decision titles, a deep link) to the operator's phone
> over an HTTP push channel. Notification is dedup-gated per sentinel identity, fail-OPEN (a send
> failure never blocks or corrupts the halt), and inert when no channel is configured. v1's answer
> path is "notice fast, answer in chat as today"; a mobile-committable resolution surface is the
> `native-android-pipeline-steering` sibling's territory, not built here.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented contracts, not sibling
> specs**:
> - The state scripts' halt/terminal emission: `_state(..., terminal_reason=, notify_message=)` in
>   `user/scripts/lazy-state.py` (~line 111) and `user/scripts/bug-state.py` (~line 260) — every
>   halt `compute_state` detects flows through this one output helper, and `notify_message` is
>   already the composed human-readable halt line.
> - The `NEEDS_INPUT.md` rich-body schema (`user/skills/_components/sentinel-frontmatter.md`):
>   frontmatter `decisions:` one-liners (≤4) are machine-parseable via `parse_sentinel` without
>   touching the load-bearing body — they become the notification's inline option surface.
> - `LAZY_QUEUE.md` (`mobile-queue-control`, Complete) — the GitHub-mobile read channel this
>   composes with; the notification deep-links to the SPEC dir and to this doc.
> - The `NEEDS_INPUT_RESOLVED_*` / `BLOCKED_RESOLVED_*` neutralization convention
>   (`--neutralize-sentinel` renames, never deletes) — a resolved sentinel is a dead identity, so
>   dedup keyed on sentinel identity self-clears when the halt is genuinely resolved.
> - **Peer, not dependency:** the orchestrator-prose `PushNotification` policy (`/lazy-batch` and
>   siblings, §1c.6) is the existing notification surface. It stays untouched in v1; this feature
>   closes the coverage gaps it structurally cannot (manual `/lazy` stepping, crashed
>   orchestrators, non-LLM probes).

---

## Executive Summary

Halts in the lazy pipelines are honest but passive. The wall-clock cost of a halt is dominated by
time-to-notice, not time-to-answer — especially for overnight/cloud runs steered from a phone. The
harness already has a notification convention, but it lives in **skill prose**: `/lazy-batch`,
`/lazy-batch-cloud`, `/lazy-bug-batch` each carry a §1c.6 `PushNotification` policy fired by the
orchestrator LLM at named event points, with the explicit rule "state scripts never call it". That
placement has three structural gaps: a manual `/lazy` step that hits `BLOCKED.md` notifies nobody;
an orchestrator that dies (container reclaim, compaction accident) never reaches its notification
step; and prose-fired notification is only as reliable as the LLM's adherence to prose.

The fix follows the house pattern "deterministic behavior belongs in a script, not a skill": a
single `lazy_core.notify_halt()` helper, invoked by **both** state scripts at the one point every
halt already passes through — the terminal-state emission in `compute_state`/`main()`, where
`terminal_reason` and `notify_message` are composed. Because read-only consumers (`/lazy-status`,
`lazy-queue-doc.py`, the `pipeline_visualizer` dashboard) also shell the state scripts, the notifier
is dedup-gated by sentinel identity in the per-repo keyed state dir: one halt, one page, no matter
how many probes observe it. The send is fail-OPEN with a bounded timeout — the halt itself is never
blocked, delayed meaningfully, or corrupted by a channel outage — and the whole feature is inert
(zero behavior change, byte-identical output) until the operator configures a channel.

This serves the **efficient** mission criterion directly (idle-on-halt hours are the single largest
avoidable latency in autonomous runs) and the **effective** criterion indirectly: honest halts only
work as a control mechanism if the human in the loop actually learns about them promptly.

## Design Decisions

### D1. Notification channel (v1)

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Which push channel does v1 send to? This is THE product decision: it determines
  what app the operator installs, what secret must exist on every notifying host (workstation +
  cloud containers), and how rich the payload can be.
- **Options:**
  - **A — ntfy behind a minimal channel seam (Recommended):** `notify_halt()` dispatches through a
    channel-agnostic sender (`send(title, body, link)`); v1 ships exactly one channel, ntfy — a
    single stdlib `urllib` POST to a topic URL. Pros: no account, free, self-hostable later, the
    topic URL is the entire configuration, phone app supports tap-through links and priority, and
    the seam makes Pushover/GitHub a config value later instead of a rewrite. Cons: on the public
    ntfy.sh instance the topic URL is capability-security (anyone who guesses it can read/post);
    requires installing the ntfy app.
  - **B — Pushover:** paid-once ($5/platform), mature delivery, tokens + user keys. Pros: very
    reliable, quiet-hours/priority built in. Cons: account + two secrets to provision everywhere;
    paid; API is no simpler than ntfy's.
  - **C — GitHub issue/mention:** open (or comment on) a per-halt issue so GitHub mobile notifies.
    Pros: composes with `LAZY_QUEUE.md` in the same app; the notification IS a durable artifact.
    Cons: needs an API token in every environment (a heavier secret than a topic URL), is noisy as
    a paging channel, is public-ish on public repos, and turns a transient halt into repo litter
    that needs closing — a second lifecycle to manage.
- **Recommendation:** A — the topic-URL model is the only option whose secret provisioning is one
  env var / one untracked config line on every host class we have (Windows workstation, WSL, cloud
  container), and the channel seam keeps the decision reversible for the cost of one function
  signature.
- **Resolution:** RESOLVED — A (ntfy behind a minimal `send(title, body, link)` channel seam; the
  topic URL is the whole configuration). *(operator-approved 2026-07-04 — recommended option
  taken.)*

### D2. Trigger chokepoint — where the notifier is called

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Given the stub's locked constraint (state scripts, not skill prose), which exact
  script-side point fires the notification? Candidates: (a) the sentinel-write moment, (b) the
  terminal-JSON emission in `compute_state`/`main()`, (c) a new helper called from both.
- **Options:**
  - **A — terminal-emission in `main()`, via a shared `lazy_core.notify_halt()` (Recommended):**
    after `compute_state` returns and before the JSON is printed (`lazy-state.py` `main()` ~line
    10109; `bug-state.py` mirror), call `lazy_core.notify_halt(state, repo_root)` when
    `terminal_reason` is in the attention set. Pros: this is the ONLY true single chokepoint —
    every halt, from every producer, surfaces here; `notify_message` is already composed;
    parity-coupled by construction (one helper, two one-line call sites). Cons: fires on read-only
    probes too, so dedup is mandatory (D4/D8 handle it).
  - **B — the sentinel-write moment:** notify wherever `NEEDS_INPUT.md`/`BLOCKED.md` is written.
    Cons: there is no single writer — cycle subagents write these sentinels via skill prose (the
    Write tool), while the scripts write only a subset (`DEFERRED_REQUIRES_HOST.md`, the
    `unknown-host-capability` `BLOCKED.md`, `--apply-pseudo` outputs). Covering prose writers means
    a PostToolUse hook or more prose — exactly what the stub forbids.
  - **C — orchestrator-side:** already exists (§1c.6) and already misses manual `/lazy` stepping
    and dead orchestrators.
- **Recommendation:** A — the terminal emission is the empirically verified single funnel (every
  `terminal_reason=` in both scripts flows through `_state()`), and dedup was needed under any
  option because long-lived sentinels are re-observed every probe.
- **Resolution:** Auto-accepted A; the operator-visible behavior ("halts page me") is fixed by the
  stub — where the call lives inside the scripts is invisible implementation placement.
  *(operator-confirmed 2026-07-04: terminal-emission chokepoint in each script's `main()`, one-line
  `lazy_core.notify_halt(state, repo_root)` call immediately before the state-JSON write.)*

### D3. Event scope — which terminals notify

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Which `terminal_reason` values page the phone by default, and do clean/run-end
  events notify too? Also: how does this coexist with the orchestrator's §1c.6 `PushNotification`
  (which will keep firing on its own event points, on a different channel/app)?
- **Options:**
  - **A — attention terminals only, clean stops opt-in (Recommended):** default set =
    `blocked`, `blocked-misnamed`, `needs-input`, `needs-spec-input`, `needs-research`,
    `queue-blocked-on-research`, `completion-unverified`, `stale_upstream`,
    `queue-exhausted-all-parked`, `queue-exhausted-budget-deferred`, `queue-missing` — the
    terminals where the operator's action is the unblocker. Clean stops
    (`all-features-complete`, `all-bugs-fixed`, `cloud-queue-exhausted`,
    `device-queue-exhausted`, `host-capability-saturated`) notify only when the config sets
    `notify_on_clean_stop: true`. §1c.6 stays untouched (additive channels; the Claude-app ping
    and the ntfy page are different apps, and dedup is per-channel by construction). Pros: pages
    mean "you are needed"; signal stays high. Cons: an operator who wants "run finished" pages
    must flip the opt-in.
  - **B — every terminal:** simplest rule. Cons: clean nightly stops become nightly noise, which
    trains the operator to ignore pages — the exact failure paging systems die of.
  - **C — attention terminals + retire the §1c.6 prose policy:** single notification surface.
    Cons: §1c.6 also covers orchestrator-only events the script never sees (`max-cycles` cap at
    Step 1c, park events, the WU-4 flush), so retiring it loses coverage; and it is a
    four-skill coupled prose change — out of proportion for v1.
- **Recommendation:** A — attention-only default with an opt-in for clean stops, prose policy
  untouched. Honest boundary note: orchestrator-decided halts with no script terminal (the
  `forward_cycles >= max_cycles` cap, per-park events under `--park`) remain §1c.6 territory in
  v1; a parked sentinel still pages at the `queue-exhausted-all-parked` terminal.
- **Resolution:** RESOLVED — A. Attention set = the new `lazy_core._NOTIFY_ATTENTION_TERMINALS`
  frozenset (`blocked`, `blocked-misnamed`, `needs-input`, `needs-spec-input`, `needs-research`,
  `queue-blocked-on-research`, `completion-unverified`, `stale_upstream`,
  `queue-exhausted-all-parked`, `queue-exhausted-budget-deferred`, `queue-missing`); clean stops
  opt-in via `notify_on_clean_stop`; the orchestrator §1c.6 PushNotification prose stays
  UNTOUCHED. *(operator-approved 2026-07-04 — recommended option taken.)*

### D4. Dedup / re-ping policy for long-lived halts

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** A halt sentinel is re-observed by every subsequent probe (status views, doc
  regeneration, the next batch invocation). How often does one halt page?
- **Options:**
  - **A — notify-once per sentinel identity (Recommended):** identity =
    `(pipeline, item_id, terminal_reason, sentinel mtime + size)`, recorded in a ledger in the
    per-repo keyed state dir. One halt pages exactly once; resolution renames the sentinel
    (`--neutralize-sentinel` → `*_RESOLVED_*`), so a re-halt writes a NEW sentinel = new identity
    = new page. Pros: deterministic, zero daemon, self-clearing. Cons: a page missed (silenced
    phone) is never repeated.
  - **B — notify-once + re-ping after M hours:** same ledger, but a probe that observes a still-
    unresolved sentinel more than M hours (default 6) after the last send re-pages and updates the
    ledger timestamp. Pros: covers the missed-page case. Cons: re-ping fires only when something
    happens to probe — with no daemon it is opportunistic, not guaranteed; must be documented
    honestly as "re-ping on next observation after M hours".
  - **C — page on every halting probe:** no ledger. Cons: a dashboard refresh loop becomes a pager
    storm; unacceptable.
- **Recommendation:** A for v1, with the ledger schema carrying a `notified_at` timestamp so B is a
  pure additive config key (`reping_hours: 6`) later — no migration. The cloud caveat is disclosed:
  a fresh cloud container has an empty state dir, so a pre-existing halt observed there re-pages
  once per container — bounded, and arguably the desired reminder.
- **Resolution:** RESOLVED — A (notify-once per sentinel identity; the ledger schema carries
  `notified_at` so B's `reping_hours` is a pure additive config key later — no migration).
  *(operator-approved 2026-07-04 — recommended option taken.)*

### D5. Payload shape

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** What does the page contain? The operator reads this on a lock screen; it must
  carry enough to decide "grab the phone now vs. later" without opening anything.
- **Options:**
  - **A — rich payload (Recommended):** title = the script's existing `notify_message` (e.g.
    `NEEDS INPUT: <feature> — spec halted on an ambiguous decision.`); body = repo name + item id +
    halt kind + for `needs-input` the frontmatter `decisions:` one-liners (≤4 by schema, well
    inside ntfy's ~4 KB message cap); click-through link = the GitHub blob URL of the sentinel's
    spec dir (derived from `git config --get remote.origin.url`), with `LAZY_QUEUE.md` linked in
    the body as the queue-wide view. Pros: the decision titles ARE the ten-second-answer preview;
    deep link lands on GitHub mobile where the full rich body renders. Cons: a few more lines of
    payload composition; the URL derivation needs an honest fallback (no remote → no link, still
    notify).
  - **B — minimal one-liner:** `notify_message` only. Pros: trivial. Cons: the operator must open
    a session just to learn what is being asked — reintroduces half the latency this feature
    exists to remove.
- **Recommendation:** A — the marginal cost is one frontmatter parse (`parse_sentinel`, already
  imported) and one `git config` read; the marginal value is the whole "answerable from the lock
  screen" experience.
- **Resolution:** RESOLVED — A (rich payload: title = `notify_message` verbatim; body = repo
  basename + pipeline + item id + halt kind + `needs-input` decision one-liners; link = GitHub
  blob/tree URL from `git config --get remote.origin.url` SSH→HTTPS normalized, derivation
  failure ⇒ omit link, still send). *(operator-approved 2026-07-04 — recommended option taken.)*
  **Implementation note (fail-OPEN, discovered at implementation 2026-07-04):** the decisions
  extraction uses a tolerant local frontmatter read of the SAME `sentinel-frontmatter.md`
  contract instead of calling `parse_sentinel` directly — `parse_sentinel` `_die()`s (prints
  error JSON to stdout + `sys.exit(2)`) on a malformed sentinel, which would corrupt the halt's
  probe JSON, violating this SPEC's own D9 fail-OPEN constraint (notification is an observer of
  the halt, never a participant). A malformed sentinel degrades to "no decision lines", still
  notifies.

### D6. Answer path (v1 scope)

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Does v1 build any mobile answer mechanism, or only the notice?
- **Options:**
  - **A — notice fast, answer in chat as today (Recommended):** the page tells the operator a run
    is waiting; they answer via the existing surfaces (the batch orchestrator's `AskUserQuestion`
    in the Claude app, or a chat instruction that resolves/neutralizes the sentinel). Pros: zero
    new write path, zero new attack surface; composes with the sibling
    `native-android-pipeline-steering` spec, which owns the mobile write path (committing
    resolution files through the GitHub API). Cons: two apps in the loop (ntfy to notice, Claude
    to answer).
  - **B — mobile-committed resolution file in v1:** the page includes instructions to commit a
    `## Resolution` append from GitHub mobile. Pros: one-app flow for simple choices. Cons:
    hand-editing a load-bearing sentinel from a phone is exactly the malformed-sentinel risk the
    file contracts warn about; the sibling spec exists to do this properly with structure.
- **Recommendation:** A — scope discipline. The notification body may STATE where the answer
  happens ("answer in the Claude app / next session"), but v1 builds no write path.
- **Resolution:** RESOLVED — A (v1 is notice-only; the answer path stays in chat / the
  `native-android-pipeline-steering` sibling). *(operator-approved 2026-07-04 — recommended
  option taken.)*

### D7. Secrets and configuration residency

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where does the channel secret (ntfy topic URL / tokens) live?
- **Options:**
  - **A — untracked user-level config file + env override (Recommended):**
    `~/.claude/notify.json` (schema: `{channel, url, notify_on_clean_stop, reping_hours}`), never
    symlinked into this repo, listed alongside the existing untracked-secrets set
    (`settings.local.json`, `.credentials.json`); env var `LAZY_NOTIFY_URL` (+
    `LAZY_NOTIFY_DISABLE=1` kill switch) overrides, which is also how cloud containers are
    provisioned. Config absent ⇒ `notify_halt()` is a no-op and every test/CI/hermetic run stays
    byte-identical.
  - **B — per-repo `.claude/settings.local.json`:** per-repo channel choice. Cons: N repos × 1
    secret to rot; the operator is one person with one phone — user-level is the right scope.
- **Recommendation:** A — one secret, one place, env-overridable for cloud, absent-by-default so
  the feature is opt-in and hermetic tests need no teardown.
- **Resolution:** Auto-accepted A; secret placement is invisible plumbing — the operator-visible
  choice (which channel) is D1. *(operator-confirmed 2026-07-04: untracked `~/.claude/notify.json`
  `{channel, url, notify_on_clean_stop, reping_hours}` + `LAZY_NOTIFY_URL` env override +
  `LAZY_NOTIFY_DISABLE=1` kill switch; absent config ⇒ complete no-op.)*

### D8. Dedup ledger location and write discipline

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where is notified-state recorded, and how is it written?
- **Options:**
  - **A — `notify-ledger.json` in the per-repo keyed state dir (Recommended):** written via
    `lazy_core._atomic_write` into `claude_state_dir()` (which already resolves
    `~/.claude/state/<repo_key>/` and honors the `LAZY_STATE_DIR` hermetic-test override), one
    JSON object keyed by sentinel identity with `notified_at`. Pros: reuses the exact state-dir
    machinery the run marker uses; per-repo keyed for free; never pollutes the repo tree.
  - **B — a notified-marker file next to the sentinel:** e.g. `.NOTIFIED` in the spec dir. Cons:
    lands in git status noise, risks colliding with sentinel-name hooks and doc lints, and
    committing notification bookkeeping into the work tree conflates channels with state.
- **Recommendation:** A — repo-tree purity plus free hermeticity; the ledger is ephemeral state,
  exactly what the state dir is for.
- **Resolution:** Auto-accepted A; internal state layout with no operator-visible surface.
  *(operator-confirmed 2026-07-04: `notify-ledger.json` in the per-repo keyed state dir via
  `_atomic_write`, keyed by sentinel identity, entries >30 days dropped on write.)*

### D9. Failure semantics

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What happens when the send fails (offline, channel down, proxy-blocked cloud)?
- **Options:**
  - **A — fail-OPEN with bounded timeout and breadcrumb (Recommended):** the entire
    `notify_halt()` body is wrapped so no exception ever propagates; the HTTP send uses the
    house-standard `urllib` with `timeout=5` (the same bound as `_default_sidecar_probe` /
    `_default_frontend_probe`); on failure, write a `notify-error.json` breadcrumb in the state
    dir (the `hook-error.json` pattern) and append a `lazy_core._diag()` line so the probe JSON
    carries the "why no page" trail; exit code and state JSON are unchanged. The ledger is
    updated ONLY on a successful send, so a failed send retries on the next observation.
  - **B — surface failure as a terminal/diagnostic error:** violates the stub's locked
    constraint — notification is an observer of the halt, never a participant.
- **Recommendation:** A — this is the stub's own fail-OPEN constraint made concrete with the
  repo's existing timeout and breadcrumb conventions.
- **Resolution:** Auto-accepted A; the stub locks fail-OPEN — only the mechanics are chosen here.
  *(operator-confirmed 2026-07-04: urllib `timeout=5`, `notify-error.json` breadcrumb + `_diag`
  on failure; ledger updated ONLY on a successful send.)*

### D10. Cloud vs. workstation parity

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Does the cloud path (`--cloud`) get the same notifier?
- **Options:**
  - **A — identical code path, honest degrade (Recommended):** `notify_halt()` is environment-
    agnostic (no `--cloud` branch). Cloud containers get the channel secret via env (D7); cloud
    outbound HTTPS traverses the container's proxy, so reachability of the channel host is an
    empirical check — on failure the D9 breadcrumb fires and the existing cloud §1c.6
    `PushNotification` still covers run-level events. No cloud-specific divergence to mirror.
  - **B — workstation-only:** avoids the proxy question. Cons: overnight cloud runs are the
    highest-value paging case; excluding them guts the feature.
- **Recommendation:** A — with the ntfy-reachability-from-cloud check recorded as a deferred
  empirical verification (Phase 3), not assumed.
- **Resolution:** Auto-accepted A; environment parity of an invisible code path.
  *(operator-confirmed 2026-07-04: identical env-agnostic code path cloud/workstation.)*

## User Experience

Setup (once):

```bash
# workstation — ~/.claude/notify.json (untracked)
{ "channel": "ntfy", "url": "https://ntfy.sh/<random-topic>", "notify_on_clean_stop": false }
# cloud environment — env var provisioning
LAZY_NOTIFY_URL=https://ntfy.sh/<random-topic>
```

Then nothing: the operator changes no workflow. When any run — `/lazy-batch` on the workstation,
`/lazy-batch-cloud` overnight, or a manual `/lazy` step — produces an attention terminal, the phone
shows (D5 shape, ntfy rendering):

```
NEEDS INPUT: operator-halt-notifications — spec halted on an ambiguous decision.
claude-config · feature · needs-input
1. Notification channel (v1)
2. Event scope — which terminals notify
3. Dedup / re-ping policy for long-lived halts
→ tap: github.com/<owner>/claude-config/tree/main/docs/features/operator-halt-notifications
Queue: LAZY_QUEUE.md · answer in the Claude app / next session
```

Tapping lands on the spec dir on GitHub mobile, where `NEEDS_INPUT.md`'s rich `## Decision Context`
body renders in full. The operator answers in chat as today (D6). Resolution renames the sentinel
(`--neutralize-sentinel`), which retires its dedup identity; a later re-halt pages again.

Failure is silent by design at the halt itself: if the channel is down, the run halts exactly as it
would have, and `notify-error.json` + a diagnostics line record why no page arrived. `/lazy-status`
and the probe JSON carry the diagnostic. No channel configured ⇒ the feature does not exist.

## Technical Design

```
compute_state() ──► _state(terminal_reason, notify_message, …)      [both scripts — the chokepoint]
       │
main() before JSON print:
   lazy_core.notify_halt(state, repo_root)
       │
       ├─ config absent / LAZY_NOTIFY_DISABLE ──────────► no-op (byte-identical behavior)
       ├─ terminal_reason ∉ attention set (D3) ─────────► no-op
       ├─ identity in notify-ledger.json (D4) ──────────► no-op (already paged)
       └─ compose payload (D5) ──► urllib POST, timeout=5 (D9)
              ├─ ok  ──► _atomic_write ledger entry {identity, notified_at}
              └─ fail ─► notify-error.json breadcrumb + _diag(); halt unaffected
```

- **Helper placement:** `notify_halt(state, repo_root)` + `_load_notify_config()` +
  `_notify_identity(state, sentinel_path)` + the ntfy sender live in `lazy_core.py`
  (domain-agnostic, shared by both scripts per the contributor conventions in
  `user/scripts/CLAUDE.md`). Call sites: one line in each script's `main()` immediately before
  `sys.stdout.write(json.dumps(state, …))` — parity-coupled; run
  `python3 user/scripts/lazy_parity_audit.py --repo-root .` before committing.
- **Attention set:** a `lazy_core._NOTIFY_ATTENTION_TERMINALS` frozenset (D3 list), a sibling of
  `SANCTIONED_STOP_TERMINAL` (note: NOT its complement — `needs-research` and
  `queue-blocked-on-research` are sanctioned stops that still demand operator action).
- **Identity & ledger:** identity tuple `(pipeline, item_id, terminal_reason, sentinel_mtime_ns,
  sentinel_size)`; sentinel path resolved from the state's `spec_path` + the terminal's known
  sentinel filename (`NEEDS_INPUT.md`, `BLOCKED.md`, stray name for `blocked-misnamed`); terminals
  with no sentinel file (e.g. `queue-missing`) key on `(pipeline, terminal_reason, date)`.
  Ledger at `claude_state_dir() / "notify-ledger.json"`, written with `lazy_core._atomic_write`,
  bounded (drop entries older than 30 days on write) so it never grows unbounded.
- **Payload:** title = `notify_message` verbatim (already item-naming — the in-file `--test`
  harness asserts terminal notify messages name the feature, `lazy-state.py` ~line 6231); body =
  repo basename, pipeline, item id, halt kind, plus for `needs-input` the frontmatter `decisions:`
  list via the existing `parse_sentinel`; link = GitHub blob/tree URL derived from
  `git config --get remote.origin.url` (SSH→HTTPS normalized; derivation failure ⇒ omit link,
  still send). All stdlib; no new dependencies (pipeline-adjacent scripts stay stdlib-only).
- **House invariants honored:** script-owned deterministic state (the ledger, not LLM memory);
  atomic writes; fail-OPEN observer; per-repo keyed state dir; coupled-pair parity via a shared
  helper; read-only over the work tree (the notifier never writes into the repo); zero output
  change — the state JSON is byte-identical with or without the feature (diagnostics lines appear
  only on send attempts, matching existing `_diag` behavior).
- **Testing:** `notify_halt` takes an injected `sender` callable (the `ensure_runtime` injected-
  collaborator pattern) so pytest (`test_lazy_core.py`) covers: inert-without-config, attention-set
  gating, dedup across repeated probes, identity refresh on sentinel rewrite, ledger atomicity
  under `LAZY_STATE_DIR`, fail-OPEN on sender raise/timeout, breadcrumb write. In-file `--test`
  fixtures in both scripts assert the call-site wiring (halt fixture + fake config ⇒ exactly one
  send).

## Implementation Phases

- **Phase 1 — Core helper (lazy_core).** `notify_halt()` with config loader, attention set,
  identity/ledger, injected sender; full pytest coverage incl. fail-OPEN and hermetic state dir.
  Proves done: `test_lazy_core.py` green; no state-script change yet; probe output byte-identical.
- **Phase 2 — Wire both scripts (parity-coupled).** One-line call in each `main()`; payload
  composer (decisions extraction, deep-link derivation); in-file `--test` fixtures; parity audit
  green. Proves done: a fixture halt with a fake sender produces exactly one payload with the D5
  fields; repeated probes produce zero further sends.
- **Phase 3 — Live channel + environment verification.** Real ntfy sender (per D1 outcome);
  operator receives a page on the phone from (a) a workstation manual `/lazy` halt and (b) a cloud
  run (or the proxy-blocked degrade is captured as a `notify-error.json` breadcrumb and documented).
  Proves done: screenshot-grade manual evidence + breadcrumb path exercised by unplugging the URL.
- **Phase 4 — Opt-ins and docs.** `notify_on_clean_stop`, the D4 `reping_hours` key if confirmed;
  document the config in `user/scripts/CLAUDE.md` and the untracked-secrets list in the root
  `CLAUDE.md`. Proves done: docs reference real keys; lint/projection clean.

Estimate: ~3 sessions (Phases 1–2 one session, 3 one, 4 folds into either).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Halt pages once | Fixture `NEEDS_INPUT.md` + fake sender; probe 3× | Exactly 1 send; ledger has 1 entry | pytest / `--test` fixture |
| Inert without config | Same fixture, no config/env | 0 sends; state JSON byte-identical | pytest diff vs baseline |
| Fail-OPEN | Sender raises / times out | Halt JSON unchanged, exit 0, `notify-error.json` written, no ledger entry | pytest |
| Resolution re-arms | Neutralize sentinel, write a new one | Second send with new identity | pytest |
| Attention-set gating | `all-features-complete` fixture, opt-in off | 0 sends; with `notify_on_clean_stop` ⇒ 1 | pytest |
| Read-only probes safe | `lazy-queue-doc.py` / `--probe` against a halted repo | No duplicate page beyond the first | ledger inspection |
| Real phone delivery | Manual `/lazy` step into a blocked fixture | Page on device with decisions + working deep link | operator manual check |
| Cloud reachability | Cloud run halt with env-provisioned URL | Page received, or honest breadcrumb if proxy-blocked | device / state dir |
| Parity | `lazy_parity_audit.py --repo-root .` | Both call sites present, audit green | parity audit output |

## Open Questions

All five product-behavior decisions were RESOLVED 2026-07-04 (operator-approved, recommended
option taken in each case — see each decision's `**Resolution:**` entry above):

- **D1 — channel choice:** RESOLVED — ntfy behind a minimal channel seam (option A).
- **D3 — event scope:** RESOLVED — attention terminals only by default, clean stops opt-in,
  §1c.6 prose policy untouched (option A).
- **D4 — dedup/re-ping:** RESOLVED — notify-once per sentinel identity for v1 (option A), ledger
  schema re-ping-ready (`reping_hours` is a later additive config key).
- **D5 — payload:** RESOLVED — rich payload (option A).
- **D6 — answer path:** RESOLVED — v1 is notice-only (option A).

Remaining (empirical checks, not decisions):

- Deferred empirical checks (implementation, not decisions): ntfy reachability from a cloud
  container through the outbound proxy (Phase 3); GitHub remote-URL derivation across SSH/HTTPS
  remotes on the Windows workstation (Phase 2); ntfy click-through→GitHub-mobile handoff behavior
  (Phase 3, mirrors mobile-queue-control's deferred link check).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the §1c.6 orchestrator `PushNotification` policy's
  documented gaps; ntfy/Pushover prior art; paging-hygiene practice (attention-only paging).
- `user/skills/_components/sentinel-frontmatter.md` — the `decisions:` schema and neutralization
  convention the payload and dedup lean on.
- `docs/features/mobile-queue-control/SPEC.md` — the read channel this deep-links into.
- `docs/features/native-android-pipeline-steering/SPEC.md` — the sibling that owns the mobile
  write/answer path (explicitly out of scope here, per D6).
- `docs/features/scheduled-autonomous-runs/SPEC.md` — soft consumer: overnight runs are the
  highest-value paging case.
