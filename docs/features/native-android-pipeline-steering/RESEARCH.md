# Research — Native Android App for Pipeline Steering

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **`mobile-queue-control` (Complete)** — the direct foundation AND the precise definition of the
  gap. Its Decision 1 locked the read channel (committed `LAZY_QUEUE.md` per repo, GitHub mobile)
  and simultaneously locked "write channel — chat, via the existing CLI; **nothing new built**";
  its Decision 4 records that reorder/remove/enqueue "already exist as CLI ops driven from chat,
  so this feature implements no write path". The android app is the deliberate re-opening of
  exactly that punt — so the relationship is: reads *extend* mobile-queue-control (same committed
  state, richer render), writes *supersede its punt* without touching its locked read-channel
  decisions. Also inherited: the byte-stable/no-embedded-wall-clock freshness model (git commit
  time), and the v1 repo scope (claude-config + AlgoBooth — the repos that work on, commit to,
  and push `main`; Decision 6), which becomes the app's tier-1 reachable set.
- **`user/scripts/lazy-queue-doc.py`** — the generator whose output is the app's primary tier-1
  render source; pure read over `pipeline_visualizer.probe.probe_state`, orchestrator-invoked at
  the per-cycle commit. Its ride-the-cycle-commit publish cadence is what makes the app's
  intent-ack loop work with zero new plumbing (an applied intent shows up in the next
  `LAZY_QUEUE.md` commit).
- **Sentinel schemas (`user/skills/_components/sentinel-frontmatter.md`)** — the load-bearing
  discovery for the write path: `NEEDS_INPUT.md`'s lifecycle already IS a file-edit interface
  ("after the human appends `## Resolution`, the orchestrator re-runs and the writer skill
  consumes it"; neutralization is a script-side rename to `NEEDS_INPUT_RESOLVED_<date>.md` via
  `--neutralize-sentinel`). The rich-body contract (`## Decision Context`, 1:1 H3↔`decisions[i]`
  mapping, recommended-option-first, ≤4 decisions / ≤4 options) is effectively a ready-made
  mobile UI schema — the app renders what batch skills already author. The `resolved_by` marker
  convention gives mobile answers an audit tag for free.
- **State-script CLI ownership (`user/scripts/CLAUDE.md`)** — the constraint that shaped D3:
  `--reorder-queue --id --to {tail|head|remove|<index>}` and `--enqueue-adhoc` are
  operator-only/out-of-cycle ops (guarded by `refuse_if_cycle_active`, exit 3, zero side
  effects), HARD CONSTRAINT 1 forbids hand-editing `queue.json`, and every queue write funnels
  through `lazy_core.reorder_queue`/`enqueue_adhoc` + `_atomic_write`. A mobile commit that
  edits `queue.json` directly would be the exact hand-edit class the constraint names — hence
  the intent-file design, with consumption at the same bracket where `adhoc-enqueue.md` already
  runs (`/lazy*` Step 0.3 / Step 0.45).
- **The `_RESOLVED_`/rename audit convention** — `--neutralize-sentinel` renames rather than
  deletes, and the noncanonical-blocker machinery explicitly whitelists `_RESOLVED_` names. The
  intent lifecycle (`INTENT_*` → `*_APPLIED_*` / `*_REJECTED_*`) copies this proven shape.
- **Hook boundary honesty** — the write-guard hooks (`block-noncanonical-blocker-write.sh`,
  `block-sentinel-write-on-stray-branch.sh`) fire on workstation PreToolUse only; GitHub-API
  commits bypass them entirely. This is documented in the SPEC as a by-construction safety
  requirement (validated formats, non-sentinel-shaped filenames, consumption-side validation)
  rather than assumed protection.
- **Git-divergence machinery** — the probe's `git_guards` (`head_matches_origin`, `unpushed`)
  and `detect_cycle_bracket_friction`'s per-cycle commit budget both observe commit topology; a
  remote-first mobile commit interacts with both. Flagged as a named Phase 3 `/spec-phases`
  integration item rather than resolved here (the reconciliation point — fetch before
  `--consume-intents` — is designed; its friction-detector accounting needs the phases-level
  look).
- **`pipeline_visualizer` + `cross-repo-fleet-view` (Draft, parallel)** — the tier-2 live
  backend shape (`/api/state`, `/api/queue`, prospective `/api/fleet`). The server binds
  127.0.0.1 and has no auth — which is why tier 2 is config-gated behind an operator-provided
  reachable URL (tailscale-class) and why tier 1 is the default posture.

## External prior art & concepts

Training-knowledge, not live research:

- **PWA vs native for single-maintainer tools:** installable PWAs on Android (Chrome) get
  home-screen install, service-worker offline, and Push API notifications; the classic native
  advantages (widgets, Keystore, background reliability) matter most for consumer-grade apps
  with push SLAs. For an operator tool whose paging is delivered by a separate notifier channel
  (ntfy/Pushover-class apps have their own reliable delivery), the PWA loses little. The
  maintenance asymmetry (static bundle vs Gradle/signing/store or sideload pipeline) dominates
  at n=1 users. Honest caveat: iOS PWA push is more limited, but the stub targets Android.
- **GitOps write patterns:** "the phone commits a declarative intent; a trusted agent
  reconciles" is the standard GitOps answer to untrusted/edge writers (Flux/Argo-style: git is
  the API, the controller applies). The intent-file design is a small-scale instance: git is the
  transport + audit log, the state script is the sole applier.
- **Optimistic concurrency via the GitHub contents API:** update-by-sha (409 on mismatch) is the
  idiomatic conflict guard for bot/app file edits; create-only unique-named files are the
  idiomatic conflict-free append. Both are used where they fit (resolutions vs intents).
- **Fine-grained PATs:** per-repository selection + `Contents: read and write` is the minimal
  credential for exactly this app shape; OAuth apps / GitHub Apps buy token rotation and
  installation semantics that pay off at team scale, not single-operator scale.
- **Command-inbox / outbox pattern:** queueing user commands durably (IndexedDB) and replaying
  idempotently on reconnect is the settled mobile-offline pattern; idempotence via
  client-generated unique ids maps directly to timestamp+nonce intent filenames.

## Alternatives analysis

- **Form factor (D1):** native Kotlin's remaining advantages after the notifications feature
  carries paging: widgets and Keystore. Widgets are a nice-to-have on a steering tool; Keystore
  matters for the PAT, but the PAT is deliberately minimal-scope and short-expiry (D4), which
  bounds the browser-storage risk. Against that: a compiled client adds a standing tax on every
  harness contract change. PWA, with the hybrid shell documented as the reversible upgrade.
- **Read tiers (D2):** tier-2-first fails the away-from-home case; both-in-v1 couples the MVP to
  the fleet feature (soft dep by operator design). Tier-1-first also matches where the data
  already is — `mobile-queue-control` did the work of making committed state render-ready.
- **Write path (D3):** the decisive argument for intents over relaxed script-ownership is that
  every existing safety property (atomic writes, marker gating, cycle containment, friction
  detection, parity audit) assumes the state scripts are `queue.json`'s only writer; option B
  would re-litigate all of them for one latency win. The latency cost of option A is bounded
  (next out-of-cycle bracket in a live run) and honest (pending state displayed). Sentinel
  resolutions need no intent indirection because the human-append interface already exists —
  using it keeps the mobile path byte-compatible with the chat path.
- **Consumption owner (within D3-A):** state-script-owned `--consume-intents` (orchestrator-
  triggered) beat two alternatives: orchestrator-prose consumption (would put queue-mutation
  logic in LLM wrapper prose — against the "state machine lives in the script" rule) and
  probe-time consumption inside `compute_state` (would make the read probe a writer — against
  the pure-probe posture that `lazy-queue-doc.py` and the visualizer rely on).
- **Auth (D4):** device-flow OAuth without a GitHub App yields classic-scope tokens (worse than
  fine-grained); a GitHub App is the right ceiling but wrong floor. Fine-grained PAT with expiry
  is the smallest credible credential; rotation is a settings-screen paste.

## Pitfalls & risks

- **Two write channels racing (phone vs chat).** The same sentinel answered from both sides:
  handled by sha-guarded updates (phone loses cleanly with a surfaced conflict). The same queue
  reordered from both sides: intents apply through the same serialized CLI path as chat-driven
  reorders, so the outcome is last-applied-wins with full audit — acceptable for one operator,
  documented not hidden.
- **Remote-first commits destabilizing a live run.** The known-sharp edge (git_guards,
  commit-budget friction detector). Mitigation is designed (fetch-first consumption bracket) but
  its accounting is explicitly deferred to `/spec-phases` — this is the feature's highest
  implementation-risk seam and should be Phase 3's first work unit.
- **Hook-bypass complacency.** Mobile commits skip the workstation write-guard hooks; if a
  future mobile-committed format is added carelessly (e.g. a file matching `BLOCKED*`), the
  stray-sentinel protections do not apply at commit time. The SPEC bakes the rule (formats safe
  by construction + consumption-side validation with `*_REJECTED_*`), and any new mobile format
  must repeat that analysis.
- **PAT on a phone.** Loss/theft exposes Contents write on the selected repos until expiry or
  revocation. Bounded by fine-grained scope + expiry; the repos at risk are the operator's own
  tooling repos, and git history makes any abuse visible and revertible.
- **Dead-weight risk / falsifiability.** The measurable claim: halts get answered materially
  faster from the phone than via chat relay. Signal is cheap to collect — resolution commits
  carry `requested_via`/`resolved_by` markers and timestamps against the sentinel's
  `date`/`blocked_at`, so a retro can compare time-to-resolution for app-authored vs
  chat-authored answers. If Phase 2 ships and the operator keeps answering from chat, stop at
  Phase 2 (Phases 3-6 are independently landable precisely so the build can halt at the last
  phase that earns its keep).
- **Scope creep toward a parallel control plane.** The app must stay a pen for existing file
  contracts. The bright line from the stub is preserved verbatim in the SPEC's out-of-scope
  posture: no direct state-script execution from the phone, no parallel write API, no bypass of
  script ownership.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 form factor | Installable PWA (hybrid shell as documented reversible upgrade) | Medium-high |
| D2 read tiers | Tier 1 (GitHub API over committed state) first; tier 2 config-gated later | High |
| D3 write path | Split: direct sentinel `## Resolution` commits + create-only queue intents consumed by script-owned `--consume-intents` | High |
| D4 auth | Fine-grained per-repo PAT, Contents read/write, short expiry, on-device entry | High |
| D5 offline | Labeled cached reads + queued idempotent write replay | Medium-high |
| D6 notifications | Consume `operator-halt-notifications`; app owns deep links only | High (auto-accepted, stub-directed) |
| D7 intent contract | Sentinel-style frontmatter, one file per intent, `*_APPLIED_*` rename | High (auto-accepted) |
| D8 hosting | Static bundle via GitHub Pages (verify plan) or public app-only repo | Medium (Phase 1 verification) |
| D9 repo set | In-app device-local list; fleet-endpoint import when tier 2 lands | High (auto-accepted) |
