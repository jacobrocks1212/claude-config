# Native Android App for Pipeline Steering — Feature Specification

> A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's
> queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone:
> answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue.
> Reads come from committed state via the GitHub API (zero server), with an optional live tier
> against a reachable fleet endpoint. Writes are **mobile-authored commits of files the pipeline
> already understands** — sentinel `## Resolution` appends plus a new sanctioned queue-intent
> file that the pipeline ingests through the existing state-script CLI — never a parallel write
> API and never a hand-edit of `queue.json`. Closes the writes gap `mobile-queue-control`
> explicitly punted to chat. High ambition; structured as a multi-phase build.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator example); fleshed out via
internal desk research 2026-07-04 (Gemini research skipped by operator directive — see
RESEARCH.md)

**Depends on:**
- cross-repo-fleet-view — soft — the fleet endpoint is the natural live-read backend, but the v1 read tier can be GitHub-API-over-committed-state with zero server.
- operator-halt-notifications — soft — halt paging is the push channel that deep-links into the app; the app is browsable without it.

> Substantive dependencies beyond the dep block are **implemented data contracts, not sibling
> specs**:
> - `mobile-queue-control` (Complete) is the read-path foundation: root-level `LAZY_QUEUE.md`
>   per repo (`user/scripts/lazy-queue-doc.py`), byte-stable, riding each cycle's commit on
>   `main` — the committed-state read channel this app renders and extends.
> - The state-script CLI is the write-path contract the app composes with, never bypasses:
>   `lazy-state.py`/`bug-state.py` `--reorder-queue --id <id> --to {tail|head|remove|<index>}`,
>   `--enqueue-adhoc … --type {feature,bug}`, `--neutralize-sentinel <path>` (rename →
>   `<stem>_RESOLVED_<date><ext>`). All are orchestrator-only out-of-cycle ops
>   (`refuse_if_cycle_active`, exit 3), and HARD CONSTRAINT 1 forbids hand-editing `queue.json`.
> - Sentinel schemas (`user/skills/_components/sentinel-frontmatter.md`): `NEEDS_INPUT.md`
>   (`kind: needs-input`, `decisions:` list, load-bearing `## Decision Context` body,
>   recommended-option-first) and its human-resolution convention (append `## Resolution`;
>   pipeline neutralizes by rename to `NEEDS_INPUT_RESOLVED_*`). These are the files a mobile
>   write path may legitimately author edits to.

---

## Executive Summary

Mobile steering today is asymmetric. Reads are solved: `mobile-queue-control` ships a per-repo
`LAZY_QUEUE.md` that GitHub mobile renders, with SPEC drill-in via native markdown links. Writes
were explicitly punted: its Decision 1 locked "write channel — chat, via the existing CLI;
nothing new built", so answering a ten-second `NEEDS_INPUT.md` question from the phone still
means opening a chat session to a workstation and asking it to run the CLI. Combined with silent
halts (the `operator-halt-notifications` problem), the wall-clock cost of a halt is dominated by
indirection, not by the decision itself.

This feature builds the mobile client that closes the loop. The read path is tiered: **tier 1**
renders committed state through the GitHub API — `LAZY_QUEUE.md`, `queue.json`, `SPEC.md`,
sentinel files — which needs zero server and works from anywhere the phone has internet; **tier
2** (optional, config-gated) talks to a reachable `pipeline_visualizer`/fleet endpoint for
live-run fidelity, with the LAN/tailscale-class reachability assumption stated explicitly. The
write path is the design core: the phone commits **only files the pipeline already understands**.
For halt sentinels that is literally the existing human-resolution convention (append a
`## Resolution` block to `NEEDS_INPUT.md`/`BLOCKED.md`); for queue mutations — where the on-disk
file is script-owned and hand-edits are forbidden — the app commits a new **queue-intent file**
that the orchestrator ingests at the next cycle boundary and applies through the sanctioned
`--reorder-queue`/`--enqueue-adhoc` CLI, preserving the one-writer contract and run-marker safety
by construction (intents are consumed at the same out-of-cycle points the CLI already requires).

Mission criteria served: **efficient** (halt answer latency drops from
notice-then-open-a-workstation-chat to a phone tap; no redone context), **effective** (answers
land as auditable committed artifacts the state machine consumes, not chat paraphrases), and
**best-practice-aligned** (honest halts stay honest — the app changes who can answer them and
from where, never the gating itself).

## Design Decisions

### D1. App form factor — PWA vs native Android

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** THE product decision. What does the operator install and what maintenance burden
  does the harness take on, for a single-operator tool?
- **Options:**
  - **A — Installable PWA:** one static web codebase (installable to the home screen, service
    worker for offline cache). Pros: no app store, no signing, no Kotlin/Gradle toolchain in a
    repo that is otherwise Python + Markdown; updates are a static redeploy; runs on any device
    (a tablet or desktop browser gets it free); Android Chrome supports the Push API and
    notifications for installed PWAs if app-owned push is ever wanted. Cons: no home-screen
    widgets; background execution limits (irrelevant for a poll-on-open reader); credential
    storage is browser storage, weaker than Android Keystore (see D4).
  - **B — Native Kotlin app:** Pros: best notification reliability, widgets, Keystore-backed
    credential storage, richer offline. Cons: a full Android project to maintain for one
    operator; store or sideload distribution; every harness contract change now has a compiled
    client to update. The notification advantage is further shrunk by the dep verdict:
    `operator-halt-notifications` will carry halt push on its own channel (e.g. a notifier
    app) regardless of this app's stack — the app then only needs to be deep-linkable.
  - **C — Hybrid (Tauri Mobile / Capacitor shell around the PWA):** Pros: Keystore access +
    web codebase. Cons: adds the native toolchain anyway; the shell's value is mostly D4
    credential storage, which has cheaper mitigations.
- **Recommendation:** A — for a single-operator steering tool, the PWA delivers the read/write
  loop at a fraction of B's standing maintenance cost, and the one genuine native advantage
  (push reliability) is being provided by the notification feature's own channel. Reversible:
  the app is API-shaped around GitHub contents calls, so a later native shell (C) can wrap the
  same code if widgets/Keystore ever justify it.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D2. Read tiers — what v1 reads and from where

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Committed-state reads (GitHub API) and live reads (fleet endpoint) differ in
  freshness, reach, and infrastructure. Which tiers ship, and when?
- **Options:**
  - **A — Tier 1 first, tier 2 later and config-gated:** v1 reads committed state only —
    `LAZY_QUEUE.md`, `queue.json`, `SPEC.md`, sentinel files via the GitHub contents API, with
    freshness from the native last-commit time (the `mobile-queue-control` freshness model).
    Works anywhere, zero server. Tier 2 (a reachable `cross-repo-fleet-view`/`pipeline_visualizer`
    endpoint for live per-item stage fidelity) lands as a later phase, explicitly gated on the
    operator configuring an endpoint URL + the reachability assumption (LAN/tailscale-class; the
    visualizer binds 127.0.0.1 by default and has no auth — exposure is the operator's tunnel
    choice, out of app scope). Cons: v1 freshness is commit-cadence, not live; mid-cycle state
    is invisible until the cycle commits.
  - **B — Both tiers in v1:** richer day one; doubles the v1 surface and couples the MVP to the
    sibling fleet feature landing first (the dep is deliberately soft).
  - **C — Tier 2 only:** live-first. Rejected: requires the phone to reach the workstation for
    ANY read, which fails the steer-from-anywhere case (the overnight/cloud-run scenario).
- **Recommendation:** A — tier 1 alone already covers the dominant workflow (notice halt →
  read decision context → answer), the commit-cadence freshness limit is exactly the one the
  operator already accepts on GitHub mobile today, and it keeps the soft dep honest. Note the
  scope consequence: tier 1 only reaches repos whose pipelines commit AND push (claude-config +
  AlgoBooth, both main-based — the `mobile-queue-control` Decision 6 set); work repos with
  push blocked by hook are tier-2-only by construction.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D3. Write-path contract — how mobile writes enter the pipeline

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The critical seam. `--reorder-queue`/`--enqueue-adhoc`/`--neutralize-sentinel`
  are CLI ops run by a session on the workstation; HARD CONSTRAINT 1 forbids hand-editing
  `queue.json`; a mobile commit that edits `queue.json` directly would violate script ownership.
  How do phone-authored writes become pipeline state?
- **Options:**
  - **A — Split write path: direct sentinel resolutions + queue-intent files:**
    1. *Sentinel answers are already-sanctioned file edits.* The `NEEDS_INPUT.md` lifecycle is
       "human appends `## Resolution`, the orchestrator re-runs and the writer skill consumes
       it" — the app commits exactly that append (and the analogous resolution note on
       `BLOCKED.md`), then the pipeline neutralizes via `--neutralize-sentinel` as it already
       does. No new pipeline surface at all.
    2. *Queue mutations go through a new sanctioned **queue-intent** file.* The app commits a
       create-only intent doc (schema in D7) under `docs/{features,bugs}/intents/`; the
       orchestrator consumes intents at its existing out-of-cycle boundary by invoking a new
       script-owned `--consume-intents` op, which applies each intent through the existing
       `reorder_queue`/`enqueue_adhoc` helpers and renames the intent `*_APPLIED_<date>*`
       (audit trail, mirroring `_RESOLVED_`). `queue.json` keeps exactly one writer — the
       script. Mid-run safety is inherited, not added: consumption happens only where the CLI
       ops are already legal (out-of-cycle, `refuse_if_cycle_active`-guarded), so an intent
       landing mid-cycle simply waits for the boundary.
    Pros: preserves one-writer and every existing guard; intents are durable, auditable, and
    replayable; idle-repo intents are honestly "pending" until a session runs. Cons: apply
    latency (next cycle boundary, or next session for an idle repo); a new consumption step to
    build and parity-mirror.
  - **B — Relax script ownership for specific mobile-committed formats:** allow the app to edit
    `queue.json` directly under a signed/convention-marked commit. Pros: zero apply latency.
    Cons: breaks the single-writer contract that every guard, atomic write, and friction
    detector assumes; a mobile reorder racing the walker's own queue trim is exactly the
    corruption class `lazy_core._atomic_write` + marker gating exist to prevent; unauditable
    divergence between "queue.json changed" and "the script changed it".
  - **C — Writes stay in chat (status quo):** punt again. Pros: nothing to build. Cons: the
    feature's entire reason to exist is closing this gap; reads-only is `mobile-queue-control`.
- **Recommendation:** A — it is the only option that adds mobile writes while keeping the
  script-ownership invariant intact, and its latency cost is bounded and honest (the app surfaces
  pending-intent state; a cycle boundary is minutes in a live run). Lean confirmed by the
  precedent that resolution-by-file-edit is already the pipeline's human interface.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D4. Auth — GitHub credential scope and on-device storage

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The app needs GitHub reads everywhere and Contents writes for D3. What credential
  does the operator mint, and where does it live on the phone?
- **Options:**
  - **A — Fine-grained PAT, per-repo, Contents read/write, short expiry:** one fine-grained
    token selecting exactly the lazy-enabled repos, `Contents: read and write` (+ `Metadata:
    read`), 90-day expiry, entered once in the app's settings and stored in the installed PWA's
    origin storage (IndexedDB). Pros: minimal blast radius (selected repos, one permission);
    revocable/rotatable independently of everything else; no OAuth app to register. Cons:
    browser origin storage is weaker than Keystore — mitigated by the narrow scope, expiry, and
    the fact that the repos it can write are the operator's own config/tooling repos.
  - **B — GitHub OAuth device flow:** nicer ergonomics, but requires registering an OAuth app
    and yields broader classic scopes unless a GitHub App is built — disproportionate for one
    operator.
  - **C — GitHub App installation:** the "right" answer at team scale; strictly more moving
    parts (app registration, installation tokens, a token-refresh component somewhere) for zero
    marginal benefit at single-operator scale.
- **Recommendation:** A — smallest credential that does the job, straightforward rotation, and
  the storage risk is proportionate to a single-operator tool whose write scope is two config
  repos. Revisit toward C only if the harness ever becomes multi-operator.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (credential minting
  and its risk posture are operator acts).

### D5. Offline behavior — read cache and queued intents

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The stub names offline behavior an open question. What does the app do without
  connectivity?
- **Options:**
  - **A — Cached reads + queued writes with explicit pending state:** the service worker caches
    the last-fetched read views (marked with their fetch time — stale data is always labeled,
    never presented as live); writes composed offline (resolution appends, intents) queue in
    IndexedDB and replay on reconnect. Replay safety differs by kind and is designed for it:
    intents are create-only files with client-unique names (timestamp+nonce), so replay is
    trivially idempotent; a sentinel `## Resolution` append replays via the contents API's
    sha-guarded update — if the file changed meanwhile (e.g. answered from chat first), the
    update 409s and the app surfaces the conflict instead of overwriting.
  - **B — Online-only:** simplest; rejected-by-default because the halt-answering flow is
    exactly the flow used from flaky mobile connectivity.
  - **C — Full offline-first sync:** CRDT-grade machinery for a one-operator tool; unjustified.
- **Recommendation:** A — the two write kinds have natural idempotence/conflict stories, so the
  queue-and-replay design is cheap; B loses the core use case; C is over-engineering.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D6. Notifications posture — consume, don't build

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Does the app own a push stack?
- **Options:**
  - **A — Consume `operator-halt-notifications`, app owns deep links only:** the notification
    feature (fleshed in parallel; soft dep) owns channel choice and delivery; this app's
    obligation is stable, documented deep-link routes (`#/repo/<repo>/<pipeline>/<item-id>` →
    the item's halt view) that a notification payload can carry. If that channel's chosen
    notifier taps open a URL, the loop closes with zero push code here.
  - **B — App-owned web push:** a second notification pipeline duplicating the sibling
    feature's job, plus a push relay to stand up.
- **Recommendation:** A — the stub's own direction line ("consumes the
  `operator-halt-notifications` channel for halt paging + deep links") and the dep verdict both
  frame the app as a consumer; building push here would duplicate a sibling feature.
- **Resolution:** Auto-accepted A; this implements the stub's stated direction — the operator-
  visible channel decision lives in `operator-halt-notifications`, not here.

### D7. Queue-intent file contract (given D3-A)

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** The intent file's format, location, naming, and consumption mechanics.
- **Options:**
  - **A — Sentinel-style markdown-with-frontmatter, one file per intent, rename-on-apply:**
    `docs/{features,bugs}/intents/INTENT_<utc-timestamp>_<nonce>.md` with YAML frontmatter
    (schema below), consumed by a new coupled-pair CLI op `--consume-intents` on both state
    scripts (script-owned application via the existing `lazy_core.reorder_queue` /
    `enqueue_adhoc` helpers; orchestrator-invoked out-of-cycle; `refuse_if_cycle_active`-guarded
    like `--reorder-queue`; malformed intents are surfaced, renamed `*_REJECTED_<date>*`, never
    silently dropped). Applied intents rename to `INTENT_…_APPLIED_<date>.md` — the
    `_RESOLVED_` audit convention. Filenames never match `BLOCKED*`/sentinel patterns, so the
    stray-sentinel hooks and Step-3 detectors are structurally unconfusable.
  - **B — Single append-only `QUEUE_INTENTS.jsonl`:** one file invites GitHub-API sha conflicts
    between the phone's append and the pipeline's consumption commit; per-intent files are
    create-only and conflict-free.
- **Recommendation:** A. Draft frontmatter (finalized at `/spec-phases`):

  ```yaml
  ---
  kind: queue-intent
  pipeline: feature        # feature | bug
  op: reorder              # reorder | enqueue-adhoc
  id: waveform-zoom        # reorder/remove target (op: reorder)
  to: head                 # head | tail | remove | <index>   (op: reorder)
  # op: enqueue-adhoc instead carries: name, brief, type
  requested_at: 2026-07-04T09:15:00Z
  requested_via: mobile-app
  ---
  ```

- **Resolution:** Auto-accepted A; the contract's *existence* is D3 (OPEN), but its file shape
  is internal plumbing following the house sentinel-frontmatter and `_RESOLVED_`-rename
  conventions. `kind: queue-intent` gets a schema entry in
  `_components/sentinel-frontmatter.md` when built.

### D8. App hosting and distribution

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where does the PWA's static bundle live and how does the phone install it?
- **Recommendation / Options considered:** Static bundle in a repo, served via GitHub Pages
  (HTTPS, required for service workers/installability) — Pages availability on a private repo
  under the operator's plan is `(estimated — verify during Phase 1)`, with fallback options of a
  public app-only repo (the bundle contains no secrets; the PAT is entered on-device) or any
  static host. No server component by tier-1 design. The bundle lives in its own directory (or
  repo) — NOT inside `user/scripts/` — since it is a client, not pipeline-adjacent tooling
  (the stdlib-only convention governs pipeline scripts; a web client is outside that boundary).
- **Resolution:** Auto-accepted; invisible deployment plumbing with a named Phase 1
  verification.

### D9. In-app repo set configuration

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** The phone cannot read `~/.claude/lazy-repos.json` or glob `~/source/repos`. How
  does the app know which repos to show?
- **Recommendation:** An in-app repo list (owner/name entries) in settings, seeded manually; a
  repo qualifies by having `LAZY_QUEUE.md` or `docs/{features,bugs}/queue.json` at its default
  branch (the app verifies on add and shows why a repo doesn't qualify). When tier 2 lands, the
  fleet endpoint's discovered set can be offered as an import. Deliberately NOT a new committed
  registry file — the fleet view's discovery (its D1) stays the workstation-side truth.
- **Resolution:** Auto-accepted; device-local configuration with no pipeline surface.

## User Experience

Screens (tier 1, PWA):

1. **Fleet list** — one card per configured repo: name, freshness (last `LAZY_QUEUE.md` commit
   time via the API), queue depths, halt badges, pending-intent count. Tap → repo view.
2. **Repo queue view** — the `LAZY_QUEUE.md` content rendered natively (Features/Bugs tables,
   Needs-attention section), each row tappable. Reorder mode: drag rows → the app shows the diff
   ("move waveform-zoom → head") → confirm → commits an intent file → the row badges `⏳ intent
   pending` until a later `LAZY_QUEUE.md` commit reflects the new order (the natural ack loop —
   the doc rides the cycle commit that follows consumption).
3. **Item view** — SPEC.md rendered; sentinel files listed with parsed frontmatter badges.
4. **Halt answering flow** — for `NEEDS_INPUT.md`: the app parses the frontmatter `decisions:`
   list and the load-bearing `## Decision Context` body, renders each H3 with its full option
   prose (recommended option first, as the schema guarantees), and presents a picker + optional
   note. Confirm → the app appends a `## Resolution` block (chosen option per decision +
   note + `resolved_by: operator`) via a sha-guarded contents-API update and shows the commit.
   For `BLOCKED.md`: renders the body sections and commits a `## Resolution` note the
   blocked-resolution flow reads. A malformed sentinel (missing `## Decision Context`) renders
   an explicit "malformed — answer from chat" error, mirroring the orchestrator's own refusal
   rule.
5. **Enqueue flow** — a small form (name, brief, feature/bug) → commits an `enqueue-adhoc`
   intent.

Failure states are explicit: API errors and rate limits render as banners with the failing call;
stale cache is labeled with its fetch time; a 409 on a resolution commit (file changed upstream)
shows a "changed since you read it — reload" conflict, never a silent overwrite.

## Technical Design

```
phone (PWA)                         GitHub (committed state)              workstation pipeline
──────────                          ────────────────────────              ────────────────────
read tier 1: contents API  ──GET──▶ LAZY_QUEUE.md / queue.json /
                                    SPEC.md / sentinels (main)
answer halt  ──PUT (sha-guarded)──▶ NEEDS_INPUT.md + ## Resolution  ──┐   next run/cycle:
queue write  ──PUT (create-only)──▶ docs/*/intents/INTENT_*.md      ──┤─▶ git pull at Step 0.x →
                                                                      │   --consume-intents →
read tier 2 (optional, config-gated)                                  │   reorder_queue/enqueue
  ──GET /api/fleet, /repo/<slug>/api/state──▶ fleet endpoint          │   → rename *_APPLIED_*;
     (LAN/tailscale reachability, operator-provided URL)              └─▶ sentinel resume path
                                                                          (--neutralize-sentinel)
                              ack loop: cycle commit updates LAZY_QUEUE.md ──▶ phone sees applied
```

- **Reads (tier 1):** GitHub REST contents API against each configured repo's default branch.
  Freshness = the file's last-commit time (the `mobile-queue-control` model — no embedded
  wall-clock exists in `LAZY_QUEUE.md` by design). `queue.json` is read for structure,
  `LAZY_QUEUE.md` for the curated render, sentinels for halt detail. The app re-implements no
  state inference — it renders what the generator and the schemas already committed.
- **Writes are files the pipeline already understands (D3-A):**
  - *Sentinel resolutions* reuse the existing human interface: the schema's own lifecycle says
    the human appends `## Resolution` and the pipeline consumes it, then neutralizes via
    `--neutralize-sentinel` (rename to `NEEDS_INPUT_RESOLVED_<date>.md`). The app is a nicer
    pen for the same edit. Sha-guarded updates (GitHub contents API `sha` parameter) give
    optimistic concurrency against a simultaneous chat-side answer.
  - *Queue intents* (D7) are create-only files consumed by the new `--consume-intents` op —
    built as a coupled-pair CLI on `lazy-state.py` + `bug-state.py` (parity-audited via
    `lazy_parity_audit.py`), applying through the existing `lazy_core.reorder_queue` /
    `enqueue_adhoc` helpers with `lazy_core._atomic_write` semantics, guarded by
    `refuse_if_cycle_active` exactly like `--reorder-queue`. The orchestrators invoke it at
    their existing out-of-cycle enqueue point (the Step 0.x bracket where `adhoc-enqueue.md`
    already runs), which serializes intent application against the walker by construction.
  - **Important hook honesty:** PreToolUse hooks (`block-noncanonical-blocker-write.sh`,
    `block-sentinel-write-on-stray-branch.sh`) guard *workstation tool calls* — a GitHub-API
    commit never passes through them. The mobile formats are therefore safe **by construction**,
    not by hook: intent filenames cannot match sentinel patterns, resolution writes are appends
    to existing sentinels on the default branch (the same branch the target repos' pipelines
    work and push on, per `mobile-queue-control` Decision 6), and the consumption step
    validates before applying (malformed → `*_REJECTED_*`, surfaced).
  - **Remote-first divergence:** a mobile commit advances `origin/main` while a live run commits
    locally — the run's `git_guards` (`head_matches_origin`/`unpushed`) will observe divergence.
    The consumption bracket therefore begins with a fetch + ff-or-rebase pull before
    `--consume-intents`, so mobile commits are integrated at the same boundary that applies
    them. The exact reconciliation (and its interaction with the cycle-friction detector's
    commit budget) is a named `/spec-phases` integration item, not hand-waved (see Open
    Questions).
- **Reads (tier 2, later phase):** the `cross-repo-fleet-view` endpoint (`/api/fleet`,
  `/repo/<slug>/api/state`) over an operator-configured base URL. The app treats tier 2 as
  additive fidelity: absent/unreachable endpoint degrades to tier 1 with a banner, never an
  error page.
- **House invariants honored:** script-owned deterministic state (the app never edits
  `queue.json`, never re-infers state; every queue mutation lands via the state scripts);
  one-writer preserved (intents are create-only; application is script-side under the existing
  atomic-write chokepoint); coupled-pair parity (`--consume-intents` mirrored on both scripts);
  honest halts (the app answers sentinels through their own documented resolution convention);
  audit-grade provenance (intents and resolutions are commits with `requested_via`/
  `resolved_by` markers, applied intents renamed not deleted); receipt-gated completion is
  untouched (the app has no completion-adjacent surface). The PWA itself is a client outside the
  stdlib-only pipeline-script boundary; the pipeline-side additions (`--consume-intents`) are
  stdlib-only Python in the state scripts.

## Implementation Phases

- **Phase 1 — Tier-1 read-only PWA (MVP).** Installable shell, repo settings + PAT entry, fleet
  list, repo queue view (LAZY_QUEUE.md + queue.json render), item/SPEC/sentinel views, service
  worker read cache with labeled staleness. Verify D8's hosting assumption. Done when: the
  operator installs it on-phone and reads live claude-config + AlgoBooth queue state end-to-end
  with no server running. (~2 sessions)
- **Phase 2 — Sentinel answer path.** `NEEDS_INPUT.md` parser (frontmatter + Decision Context),
  answering flow UI, sha-guarded `## Resolution` commit; `BLOCKED.md` resolution note; conflict
  UX. Done when: a real batch halt is answered from the phone and the next run consumes the
  resolution and neutralizes the sentinel with zero chat involvement. (~1-2 sessions)
- **Phase 3 — Queue-intent write path (pipeline side + app side).** `--consume-intents` coupled-
  pair CLI + `queue-intent` schema entry + orchestrator Step 0.x consumption bracket (with the
  fetch-first reconciliation) + parity audit + `--test` fixtures; app-side reorder/enqueue flows
  committing intents; pending/applied/rejected states surfaced in the app. Done when: a reorder
  tapped on the phone is applied by the next run through `lazy_core.reorder_queue` and the
  updated `LAZY_QUEUE.md` round-trips back to the phone. (~2 sessions)
- **Phase 4 — Notifications consumption + deep links.** Stable route scheme, deep-link handling
  from the `operator-halt-notifications` channel's payloads (by feature-id reference; its channel
  choice is its own spec's decision). Done when: a halt notification tap lands on that item's
  answering screen. (~1 session)
- **Phase 5 — Tier-2 live reads (config-gated).** Fleet-endpoint client, reachability config,
  graceful degradation to tier 1. Gated on `cross-repo-fleet-view` shipping; independently
  landable without it (the gate simply stays off). (~1 session)
- **Phase 6 — Offline hardening.** Queued offline writes (IndexedDB) with replay (create-only
  intents; sha-conflict surfacing for resolutions), cache eviction policy, failure-state polish.
  (~1 session)

Phases 1-2 alone already deliver the headline capability (read anywhere + answer halts from the
phone); each later phase is independently landable.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Tier-1 read fidelity | Open a configured repo in the app | Rendered queue matches committed `LAZY_QUEUE.md`/`queue.json` at HEAD | Manual on-phone vs GitHub |
| Halt answer round-trip | Answer a real `NEEDS_INPUT.md` from the phone | `## Resolution` commit on main; next run consumes it and renames to `NEEDS_INPUT_RESOLVED_*` | Git log + sentinel rename |
| Concurrent-answer safety | Answer on phone after the file changed upstream | Contents-API 409 surfaced as a conflict; no overwrite | App error state + git log |
| Intent applied via script only | Commit a reorder intent, run the pipeline | `queue.json` mutated by `--consume-intents` (via `lazy_core.reorder_queue`), intent renamed `*_APPLIED_*` | `--test` fixture + git log |
| Malformed intent rejected | Commit an intent with bad frontmatter | Renamed `*_REJECTED_*`, surfaced in run output; `queue.json` untouched | `--test` fixture |
| Mid-cycle intent safety | Intent lands while a cycle subagent is active | Not applied until the out-of-cycle bracket; `--consume-intents` refused for a subagent (exit 3) | `--test` fixture (cycle marker present) |
| Parity | `--consume-intents` on both scripts | `lazy_parity_audit.py --repo-root .` green | Parity audit |
| Pending-intent honesty | Intent committed, pipeline idle | App shows `intent pending`, not the new order | Manual on-phone |
| Deep link lands | Open a `#/repo/…/<item-id>` URL from a notification | Item's answering screen opens | Manual on-phone |
| Tier-2 degradation | Configure an unreachable endpoint | Banner + tier-1 fallback, no error page | Manual |

## Open Questions

- **D1 — form factor:** installable PWA vs native Kotlin vs hybrid shell? Standing
  recommendation: PWA — single-operator maintenance economics; push is carried by the
  notifications feature's own channel; reversible via a later native shell.
- **D2 — read tiers:** ship tier 1 (GitHub-API-over-committed-state, zero server) first with
  tier 2 (live fleet endpoint, explicit reachability config) as a later phase? Standing
  recommendation: yes (option A).
- **D3 — write-path contract:** split path — direct sentinel `## Resolution` commits (already
  the pipeline's human interface) + create-only queue-intent files consumed by a new
  script-owned `--consume-intents` at the existing out-of-cycle bracket — vs relaxing
  `queue.json` script-ownership for mobile commits? Standing recommendation: the split path
  (option A); one-writer is preserved by construction.
- **D4 — auth:** fine-grained per-repo PAT (Contents read/write, short expiry) stored on-device
  vs OAuth/GitHub App? Standing recommendation: fine-grained PAT (option A).
- **D5 — offline:** labeled cached reads + queued replayable writes (create-only intents;
  sha-conflict surfacing) vs online-only? Standing recommendation: option A.
- Deferred empirical checks (implementation-time, not decisions): GitHub Pages availability for
  the chosen hosting repo/plan (D8, Phase 1); the exact fetch/pull reconciliation in the
  consumption bracket and its interaction with `detect_cycle_bracket_friction`'s commit budget
  and the `git_guards` probe fields (Phase 3 `/spec-phases` item); GitHub API rate-limit
  behavior under the app's polling pattern (Phase 1); whether `BLOCKED.md` resolution notes need
  a schema addition or ride the existing blocked-resolution reading of the body (Phase 2).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the `mobile-queue-control` committed-doc channel and
  its writes-punt; the sentinel-frontmatter resolution lifecycle; the `--reorder-queue`/
  `--enqueue-adhoc` script-ownership contract that forced the intent-file design.
- `docs/features/mobile-queue-control/SPEC.md` — the read foundation and the explicit write-punt
  this feature closes; freshness model; repo scope (main-based, pushed repos).
- `user/skills/_components/sentinel-frontmatter.md` — `NEEDS_INPUT.md` schema, Decision Context
  contract, `_RESOLVED_` neutralization convention the write path composes with.
- `user/scripts/CLAUDE.md` — CLI surface (`--reorder-queue`, `--enqueue-adhoc`,
  `--neutralize-sentinel`, `refuse_if_cycle_active`), marker ownership, coupled-pair parity.
- `docs/features/cross-repo-fleet-view/SPEC.md` + `docs/features/operator-halt-notifications/`
  — soft-dep siblings (live-read backend; halt push channel), referenced by feature-id and role.
