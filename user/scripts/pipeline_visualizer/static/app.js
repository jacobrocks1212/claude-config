/* Lazy Pipeline Visualizer — Phase 2 frontend (read-only three-pane render).
 *
 * Architecture (per SPEC "Technical Design"):
 *   - Layout bootstrap runs ONCE: build the stage-node graph, run `dagre`
 *     rankDir:'LR' in a HEADLESS Cytoscape instance, extract settled (x,y) for
 *     both tracks, then render the live canvas with the `preset` layout
 *     (immutable positions). Never run a layout on poll. Never cola/cose/elk.
 *   - The stage -> (x,y) map is exposed as a module-level object
 *     (window.PV_STAGE_COORDS) so Phase 3 animates tokens against the same coords.
 *   - Tokens are FLAT peers at a higher z-index (NOT compound nodes), each
 *     rendered at its curated_stage coordinate. Phase 2 does a full re-render per
 *     poll (acceptable); Phase 3 replaces that with cy.add/remove + animate.
 *   - Liveness: poll /api/state every 2.5s. On any fail/timeout, flip the live
 *     dot red, dim the screen, and show "Connection Lost" within <=1 poll. Never
 *     present stale data as live.
 */
"use strict";

(function () {
  // ---- Constants ---------------------------------------------------------
  var POLL_INTERVAL_MS = 2500;   // SPEC Decision 12: UI poll 2.5s
  var POLL_TIMEOUT_MS = 2000;    // a poll that exceeds this counts as a failure

  // Curated workflow stages, left-to-right. Features get all; bugs omit Research.
  var FEATURE_STAGES = ["Pending", "Spec", "Research", "Plan", "Implement", "Validate", "Complete"];
  var BUG_STAGES = ["Pending", "Spec", "Plan", "Implement", "Validate", "Complete"];
  var SIDE_STAGES = ["Blocked", "Needs-input", "Deferred"];

  // Color & shape encoding (SPEC table). Maps a curated_stage -> visual class.
  var STAGE_COLOR = {
    Pending: "#888888",
    Spec: "#0074D9", Research: "#0074D9", Plan: "#0074D9",
    Implement: "#0074D9", Validate: "#0074D9", Running: "#0074D9",
    Complete: "#2ECC40",
    "Needs-input": "#FF851B",
    Blocked: "#FF4136",
    Deferred: "#B10DC9",
  };

  // ---- Module-level state ------------------------------------------------
  // Exposed for Phase 3: the settled preset coordinate substrate.
  var stageCoords = {};            // "feature:Implement" -> {x, y}
  window.PV_STAGE_COORDS = stageCoords;
  var cy = null;                   // the live (preset) Cytoscape instance
  var layoutReady = false;

  // ---- Headless -> preset layout bootstrap (runs ONCE) -------------------
  // Build the two-track stage graph, settle it with dagre in a headless
  // instance, capture (x,y), then mount a live preset-layout instance.
  function trackNodeId(track, stage) { return track + ":" + stage; }

  function buildStageElements() {
    var nodes = [];
    var edges = [];
    function addTrack(track, stages) {
      for (var i = 0; i < stages.length; i++) {
        var id = trackNodeId(track, stages[i]);
        nodes.push({ data: { id: id, label: stages[i], track: track, stage: stages[i], kind: "stage" } });
        if (i > 0) {
          edges.push({ data: { id: id + "<-" + stages[i - 1], source: trackNodeId(track, stages[i - 1]), target: id } });
        }
      }
    }
    addTrack("feature", FEATURE_STAGES);
    addTrack("bug", BUG_STAGES);
    return nodes.concat(edges);
  }

  function bootstrapLayout() {
    if (typeof cytoscape === "undefined") {
      console.error("PV: cytoscape not loaded");
      return;
    }
    // Register the dagre adapter (UMD attaches to window.cytoscapeDagre).
    if (typeof cytoscapeDagre !== "undefined" && !cytoscape.__pvDagreRegistered) {
      cytoscape.use(cytoscapeDagre);
      cytoscape.__pvDagreRegistered = true;
    }

    var elements = buildStageElements();

    // 1) HEADLESS settle with dagre rankDir:'LR'.
    var headless = cytoscape({ headless: true, elements: elements });
    headless.layout({ name: "dagre", rankDir: "LR", nodeSep: 30, rankSep: 90 }).run();
    headless.nodes().forEach(function (n) {
      var p = n.position();
      stageCoords[n.id()] = { x: p.x, y: p.y };
    });
    headless.destroy();

    // 2) Live canvas with the PRESET layout (immutable positions). No layout on poll.
    var presetElements = elements.map(function (el) {
      if (el.data.kind === "stage") {
        var c = stageCoords[el.data.id] || { x: 0, y: 0 };
        return { data: el.data, position: { x: c.x, y: c.y } };
      }
      return el;
    });

    cy = cytoscape({
      container: document.getElementById("cy"),
      elements: presetElements,
      layout: { name: "preset" },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      style: [
        { selector: 'node[kind="stage"]', style: {
          "label": "data(label)", "text-valign": "center", "color": "#e6edf3",
          "font-size": 10, "background-color": "#232b37", "border-color": "#303a48",
          "border-width": 1, "shape": "round-rectangle", "width": 70, "height": 28,
        }},
        { selector: 'edge', style: {
          "width": 1.5, "line-color": "#303a48", "target-arrow-color": "#303a48",
          "target-arrow-shape": "triangle", "curve-style": "bezier",
        }},
        // Tokens — flat peers, higher z-index, NOT compound nodes.
        { selector: 'node[kind="token"]', style: {
          "label": "data(label)", "font-size": 8, "color": "#fff",
          "text-valign": "center", "text-halign": "center",
          "width": 16, "height": 16, "z-index": 10,
          "background-color": "data(color)", "border-width": 2, "border-color": "data(color)",
          "shape": "data(shape)",
        }},
        { selector: 'node[kind="token"][hollow="1"]', style: {
          "background-opacity": 0, "border-style": "solid",
        }},
        { selector: 'node[kind="token"][ghost="1"]', style: {
          "background-opacity": 0, "border-style": "dashed", "opacity": 0.6,
        }},
        // Per-node count badge / swimlane (6–20 / 20+ items collapse).
        { selector: 'node[kind="badge"]', style: {
          "label": "data(label)", "font-size": 9, "color": "#fff",
          "text-valign": "center", "text-halign": "center",
          "width": 26, "height": 22, "z-index": 11,
          "background-color": "data(color)", "border-width": 2,
          "border-color": "#e6edf3", "shape": "data(shape)",
        }},
        { selector: 'node[kind="badge"][scale="swimlane"]', style: {
          "width": 40, "height": 22, "border-style": "double",
        }},
        // Border-pulse on a stage node that has ejected a side-state token.
        { selector: 'node.pulse', style: {
          "border-color": "#FF851B", "border-width": 3,
        }},
      ],
    });
    cy.fit(undefined, 30);
    wireGraphInteractions();
    startPulseAnimation();
    layoutReady = true;
  }

  // ---- Drill-down + popover + pulse animation ----------------------------
  function closeDrillPanel() {
    var p = document.getElementById("drill-panel");
    if (p) p.hidden = true;
  }

  function literalsForStage(track, stage) {
    // List the live literal current_step / terminal_reason values rolling up to
    // this curated node, from the last polled state (the full machine behind 6).
    var st = window.PV._lastState || { features: [], bugs: [] };
    var items = track === "bug" ? st.bugs : st.features;
    var lits = [];
    (items || []).forEach(function (it) {
      if ((it.curated_stage || "Pending") === stage) {
        var id = it.feature_id || it.bug_id;
        var lit = it.terminal_reason || it.current_step || "(no literal — Pending)";
        lits.push({ id: id, literal: lit });
      }
    });
    return lits;
  }

  function openDrillPanel(title, rows) {
    var p = document.getElementById("drill-panel");
    if (!p) return;
    p.innerHTML = "";
    var h = el("div", "drill-title", title);
    var close = el("button", "drill-close", "×");
    close.addEventListener("click", closeDrillPanel);
    h.appendChild(close);
    p.appendChild(h);
    var ul = el("ul", "drill-list");
    if (!rows.length) {
      ul.appendChild(el("li", "drill-empty", "no items"));
    } else {
      rows.forEach(function (r) {
        var li = el("li", "drill-row");
        li.appendChild(el("span", "drill-id", r.id || "?"));
        li.appendChild(el("span", "drill-lit", r.literal != null ? r.literal : ""));
        ul.appendChild(li);
      });
    }
    p.appendChild(ul);
    p.hidden = false;
  }

  function wireGraphInteractions() {
    // Click a curated stage node → drill-down panel of literal sub-states.
    cy.on("tap", 'node[kind="stage"]', function (evt) {
      var n = evt.target;
      var track = n.data("track"), stage = n.data("stage");
      var rows = literalsForStage(track, stage);
      openDrillPanel(track + " · " + stage, rows.map(function (r) {
        return { id: r.id, literal: r.literal };
      }));
    });
    // Click a count badge → popover list of the collapsed items.
    cy.on("tap", 'node[kind="badge"]', function (evt) {
      var n = evt.target;
      var members = (window.PV._badges || {})[n.id()] || [];
      openDrillPanel("Items on " + (n.data("anchorId") || "node"),
        members.map(function (m) {
          return { id: m.id, literal: m.item.curated_stage || "Pending" };
        }));
    });
    // Click empty canvas → dismiss.
    cy.on("tap", function (evt) { if (evt.target === cy) closeDrillPanel(); });
  }

  // Border-pulse for ejected side-states: oscillate the .pulse border width.
  function startPulseAnimation() {
    var on = false;
    setInterval(function () {
      if (!cy) return;
      on = !on;
      cy.nodes(".pulse").style("border-width", on ? 4 : 2);
    }, 600);
  }

  // ---- Token mapping -----------------------------------------------------
  // Phase 3 constants for per-node scaling + Complete fade-and-drop (Decision 13).
  var SCALE_BADGE_MIN = 6;     // 6–20 items on a node → count badge + popover
  var SCALE_SWIMLANE_MIN = 21; // 20+ items → swimlane/table collapse
  var COMPLETE_FADE_MS = 10000;        // fade to ~50% ~10s after reaching Complete
  var COMPLETE_FADE_OPACITY = 0.5;
  var ANIM_DURATION_MS = 400;          // single-stage tween
  var MULTI_STAGE_ARC_MS = 600;        // arc/fade for a multi-stage jump

  // Map a curated_stage -> the track node it sits on. Side-states anchor on the
  // nearest workflow node but EJECT off-track on a parallel Y-axis (Phase 3).
  function anchorStageFor(track, curated) {
    var stages = track === "bug" ? BUG_STAGES : FEATURE_STAGES;
    if (stages.indexOf(curated) !== -1) return curated;
    if (SIDE_STAGES.indexOf(curated) !== -1) return "Implement";
    return "Pending";
  }

  function tokenVisual(item, track) {
    var stage = item.curated_stage || "Pending";
    var color = STAGE_COLOR[stage] || STAGE_COLOR.Pending;
    var shapeMap = { "Needs-input": "hexagon", "Blocked": "octagon" };
    var baseShape = track === "bug" ? "rectangle" : "ellipse";
    var shape = shapeMap[stage] || baseShape;
    return {
      color: color,
      shape: shape,
      hollow: stage === "Pending" ? "1" : "0",
      ghost: stage === "Deferred" ? "1" : "0",
    };
  }

  function stageIndex(track, stage) {
    var stages = track === "bug" ? BUG_STAGES : FEATURE_STAGES;
    return stages.indexOf(stage);
  }

  // Per-item position within a stage's micro-grid (deterministic by slot k).
  function gridOffset(track, k, ejected) {
    var dx = (k % 3) * 10 - 10;
    var laneBase = track === "bug" ? 26 : -26;
    var dy = Math.floor(k / 3) * 16 + laneBase;
    if (ejected) {
      // Side-states branch onto a parallel Y-axis FURTHER off the track.
      dy += (track === "bug" ? 52 : -52);
    }
    return { dx: dx, dy: dy };
  }

  // ---- Module-level token bookkeeping (survives across polls) -------------
  var tokenSeen = {};        // tokId -> last curated_stage (diff source of truth)
  var completeSince = {};    // tokId -> epoch ms first observed on Complete
  var completionLog = [];    // recently-dropped completed items (collapsed log)

  function tokId(track, id) { return "tok:" + track + ":" + id; }

  // Group items by the curated node they occupy (for per-node scaling).
  function groupByNode(items, track) {
    var byNode = {};
    (items || []).forEach(function (item, i) {
      var id = item.feature_id || item.bug_id || ("item-" + i);
      var stage = item.curated_stage || "Pending";
      var anchor = anchorStageFor(track, stage);
      var anchorId = trackNodeId(track, anchor);
      (byNode[anchorId] = byNode[anchorId] || []).push(
        { id: id, item: item, stage: stage, anchor: anchor }
      );
    });
    return byNode;
  }

  // Poll-diff render: add new tokens, animate moved tokens, remove gone tokens,
  // collapse high-count nodes to badges. NEVER clear+redraw the whole graph.
  function renderGraphTokens(state) {
    if (!cy) return;
    var now = Date.now();
    var liveTokIds = {};       // tokIds present this poll (drives removal)
    var liveBadgeIds = {};

    function place(items, track) {
      var byNode = groupByNode(items, track);
      Object.keys(byNode).forEach(function (anchorId) {
        var members = byNode[anchorId];
        var base = stageCoords[anchorId] || { x: 0, y: 0 };
        var count = members.length;

        if (count >= SCALE_BADGE_MIN) {
          // Per-node scaling: collapse to a count badge (6–20) or swimlane (20+).
          var swim = count >= SCALE_SWIMLANE_MIN;
          var badgeId = "badge:" + anchorId;
          liveBadgeIds[badgeId] = members;
          var sample = members[0];
          var vis = tokenVisual(sample.item, track);
          var dy = track === "bug" ? 26 : -26;
          var existing = cy.getElementById(badgeId);
          if (existing.empty()) {
            cy.add({ group: "nodes", data: {
              id: badgeId, kind: "badge", label: (swim ? "▤ " : "") + count,
              color: vis.color, shape: swim ? "round-rectangle" : "ellipse",
              track: track, anchorId: anchorId, scale: swim ? "swimlane" : "badge",
            }, position: { x: base.x, y: base.y + dy } });
          } else {
            existing.data("label", (swim ? "▤ " : "") + count);
            existing.data("scale", swim ? "swimlane" : "badge");
          }
          // Any individual tokens previously on this node are superseded by the badge.
          members.forEach(function (m) {
            var tid = tokId(track, m.id);
            if (!cy.getElementById(tid).empty()) cy.getElementById(tid).remove();
            delete tokenSeen[tid];
          });
          return;
        }

        // 1–5 items: individual animated tokens in a micro-grid.
        members.forEach(function (m, k) {
          var tid = tokId(track, m.id);
          liveTokIds[tid] = true;
          var ejected = SIDE_STAGES.indexOf(m.stage) !== -1;
          var off = gridOffset(track, k, ejected);
          var target = { x: base.x + off.dx, y: base.y + off.dy };
          var vis = tokenVisual(m.item, track);
          var receipt = !!m.item.receipt_present;
          var node = cy.getElementById(tid);

          if (node.empty()) {
            cy.add({ group: "nodes", data: {
              id: tid, kind: "token", label: "",
              color: vis.color, shape: vis.shape, hollow: vis.hollow, ghost: vis.ghost,
              itemId: m.id, stage: m.stage, track: track,
              ejected: ejected ? "1" : "0",
            }, position: target });
            tokenSeen[tid] = m.stage;
          } else {
            // Diff: update visuals + animate to the new coordinate if it moved.
            node.data("color", vis.color);
            node.data("shape", vis.shape);
            node.data("hollow", vis.hollow);
            node.data("ghost", vis.ghost);
            node.data("stage", m.stage);
            node.data("ejected", ejected ? "1" : "0");
            var prevStage = tokenSeen[tid];
            var jump = Math.abs(stageIndex(track, m.stage) - stageIndex(track, prevStage));
            var p = node.position();
            if (Math.abs(p.x - target.x) > 0.5 || Math.abs(p.y - target.y) > 0.5) {
              if (jump > 1 && prevStage && m.stage) {
                // Multi-stage jump: arc/fade rather than tween through skipped nodes.
                node.animate({ style: { opacity: 0 } }, { duration: MULTI_STAGE_ARC_MS / 2,
                  complete: function () {
                    node.position(target);
                    node.animate({ style: { opacity: 1 } }, { duration: MULTI_STAGE_ARC_MS / 2 });
                  } });
              } else {
                node.animate({ position: target }, {
                  duration: ANIM_DURATION_MS, easing: "ease-in-out-cubic" });
              }
            }
            tokenSeen[tid] = m.stage;
          }

          // Complete fade-and-drop (Decision 13).
          if (m.stage === "Complete") {
            if (!completeSince[tid]) completeSince[tid] = now;
            var age = now - completeSince[tid];
            if (age >= COMPLETE_FADE_MS) {
              cy.getElementById(tid).style("opacity", COMPLETE_FADE_OPACITY);
            }
            if (receipt) {
              // Drop the token; record it in the collapsed completion log.
              completionLog.unshift({ id: m.id, track: track, at: now });
              if (completionLog.length > 50) completionLog.pop();
              cy.getElementById(tid).remove();
              delete liveTokIds[tid];
              delete tokenSeen[tid];
              delete completeSince[tid];
            }
          } else if (completeSince[tid]) {
            delete completeSince[tid];   // moved back off Complete (rare) — reset
          }

          // Border-pulse the settled stage node when a side-state is ejected.
          if (ejected) {
            var stageNode = cy.getElementById(anchorId);
            if (!stageNode.empty()) stageNode.addClass("pulse");
          }
        });
      });
    }

    place(state.features, "feature");
    place(state.bugs, "bug");

    // Remove tokens that vanished from the state entirely (not via fade-drop).
    cy.nodes('[kind="token"]').forEach(function (n) {
      if (!liveTokIds[n.id()]) {
        delete tokenSeen[n.id()];
        delete completeSince[n.id()];
        n.remove();
      }
    });
    // Remove stale count badges.
    cy.nodes('[kind="badge"]').forEach(function (n) {
      if (!liveBadgeIds[n.id()]) n.remove();
    });
    // Clear border-pulse on nodes with no current ejection.
    var pulsedAnchors = {};
    cy.nodes('[kind="token"][ejected="1"]').forEach(function (n) {
      var stage = n.data("stage");
      var anchor = anchorStageFor(n.data("track"), stage);
      pulsedAnchors[trackNodeId(n.data("track"), anchor)] = true;
    });
    cy.nodes(".pulse").forEach(function (n) {
      if (!pulsedAnchors[n.id()]) n.removeClass("pulse");
    });

    // Stash badge membership so the popover/drill-down can list the items.
    window.PV._badges = liveBadgeIds;
    window.PV._completionLog = completionLog;
  }

  // ---- Pane renderers ----------------------------------------------------
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function chip(track, stage) {
    var c = el("span", "chip chip--" + track);
    c.setAttribute("data-stage", stage);
    return c;
  }

  // ---- Queue drag-reorder write path (Phase 4) ---------------------------
  var queueLocked = false;          // mirrors /api/state queue_locked
  var pendingReorder = {};          // track -> optimistic order awaiting reconcile
  var LOCK_TOOLTIP = "Queue locked — the orchestrator is executing a batch run. " +
    "Reordering is disabled until the run ends (Decision 11).";

  // POST a new order for one track; pipeline name maps track -> server key.
  function postReorder(track, order) {
    var pipeline = track === "bug" ? "bugs" : "features";
    pendingReorder[track] = order.slice();   // optimistic — reconciled next poll
    return fetch("api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pipeline: pipeline, order: order }),
    }).then(function (resp) {
      if (!resp.ok) {
        // 409 (locked) / 400 / 503 — drop the optimistic order; next poll snaps back.
        delete pendingReorder[track];
        if (resp.status === 409) queueLocked = true;
        return resp.json().then(function (j) { throw new Error(j.error || ("HTTP " + resp.status)); },
          function () { throw new Error("HTTP " + resp.status); });
      }
      return resp.json();
    }).catch(function (err) {
      console.warn("PV: reorder failed —", err && err.message);
    });
  }

  function renderQueues(state) {
    queueLocked = !!state.queue_locked;
    applyLockBanner();
    renderQueueCol("queue-features", state.features, "feature");
    renderQueueCol("queue-bugs", state.bugs, "bug");
  }

  function applyLockBanner() {
    var banner = document.getElementById("queue-lock-banner");
    if (banner) banner.hidden = !queueLocked;
  }

  // Reorder `items` to a track's pending optimistic order (if any) so the row
  // visibly moves on drop before the poll confirms it.
  function applyPendingOrder(items, track) {
    var order = pendingReorder[track];
    if (!order) return items;
    var byId = {};
    (items || []).forEach(function (it) { byId[it.feature_id || it.bug_id] = it; });
    // Only honor the optimistic order while it is still a valid permutation.
    var ok = order.length === (items || []).length && order.every(function (id) { return byId[id]; });
    if (!ok) { delete pendingReorder[track]; return items; }
    // If the server order already matches, the reconcile is done — clear it.
    var serverOrder = (items || []).map(function (it) { return it.feature_id || it.bug_id; });
    if (serverOrder.join("") === order.join("")) { delete pendingReorder[track]; return items; }
    return order.map(function (id) { return byId[id]; });
  }

  function renderQueueCol(elId, items, track) {
    var list = document.getElementById(elId);
    list.innerHTML = "";
    items = applyPendingOrder(items, track);
    if (!items || !items.length) {
      list.appendChild(el("li", "queue-empty", "empty"));
      return;
    }
    items.forEach(function (item) {
      var id = item.feature_id || item.bug_id || "?";
      var stage = item.curated_stage || "Pending";
      var row = el("li", "queue-row");
      row.setAttribute("data-id", id);
      row.setAttribute("data-track", track);
      // Drag handle — visible always; disabled (not hidden) when locked (Decision 11).
      var handle = el("span", "queue-handle", "⠿");
      handle.setAttribute("aria-hidden", "true");
      row.appendChild(handle);
      row.appendChild(chip(track, stage));
      row.appendChild(el("span", "queue-id", id));
      var meta = item.queue_meta || {};
      if (meta.tier != null) row.appendChild(el("span", "badge badge--tier", "T" + meta.tier));
      if (meta.adhoc) row.appendChild(el("span", "badge badge--adhoc", "ad-hoc"));
      if (meta.stub) row.appendChild(el("span", "badge badge--stub", "stub"));
      if (meta.severity) row.appendChild(el("span", "badge", meta.severity));

      if (queueLocked) {
        row.classList.add("queue-row--locked");
        row.setAttribute("title", LOCK_TOOLTIP);
        row.draggable = false;
      } else {
        row.draggable = true;
        wireRowDrag(row, list, track);
      }
      list.appendChild(row);
    });
  }

  // HTML5 drag-and-drop wiring for one row (no build step, no vendored lib).
  function wireRowDrag(row, list, track) {
    row.addEventListener("dragstart", function (e) {
      if (queueLocked) { e.preventDefault(); return; }
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", row.getAttribute("data-id")); } catch (_) {}
    });
    row.addEventListener("dragend", function () {
      row.classList.remove("dragging");
      commitDragOrder(list, track);
    });
    row.addEventListener("dragover", function (e) {
      if (queueLocked) return;
      e.preventDefault();
      var dragging = list.querySelector(".dragging");
      if (!dragging || dragging === row) return;
      var rect = row.getBoundingClientRect();
      var after = (e.clientY - rect.top) > rect.height / 2;
      list.insertBefore(dragging, after ? row.nextSibling : row);
    });
  }

  // Read the DOM order after a drop and POST it if it changed.
  function commitDragOrder(list, track) {
    if (queueLocked) return;
    var order = Array.prototype.map.call(
      list.querySelectorAll(".queue-row"),
      function (r) { return r.getAttribute("data-id"); }
    );
    var serverItems = ((window.PV._lastState || {})[track === "bug" ? "bugs" : "features"]) || [];
    var serverOrder = serverItems.map(function (it) { return it.feature_id || it.bug_id; });
    if (order.join("") === serverOrder.join("")) return;  // no change
    postReorder(track, order);
  }

  // Build a wi_id -> item lookup so Fleet cards can show shape/color/branch.
  function itemIndex(state) {
    var idx = {};
    (state.features || []).forEach(function (it) { idx[it.feature_id] = { item: it, track: "feature" }; });
    (state.bugs || []).forEach(function (it) { idx[it.bug_id || it.feature_id] = { item: it, track: "bug" }; });
    return idx;
  }

  function slugify(s) {
    return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  }

  function renderFleet(state) {
    var grid = document.getElementById("fleet-grid");
    grid.innerHTML = "";
    var leases = state.leases || [];
    if (!leases.length) {
      grid.appendChild(el("div", "fleet-empty", "no active workers"));
      return;
    }
    var idx = itemIndex(state);
    leases.forEach(function (lease) {
      var card = el("div", "fleet-card");
      card.appendChild(el("div", "fleet-slot", lease.worktree_slot || "wt-??"));
      var wi = lease.wi_id;
      var ref = idx[wi];
      var line = el("div", "fleet-meta");
      if (ref) {
        line.appendChild(chip(ref.track, ref.item.curated_stage || "Pending"));
        line.appendChild(document.createTextNode(" " + wi));
      } else {
        line.textContent = wi || "(unleased)";
      }
      card.appendChild(line);
      var branch = "p/" + slugify(wi) + (ref ? "" : "");
      card.appendChild(el("div", "fleet-meta", branch));
      var hb = el("div", "fleet-meta " + (lease.heartbeat_fresh ? "hb-fresh" : "hb-stale"),
        lease.heartbeat_fresh ? "heartbeat fresh" : "heartbeat STALE");
      card.appendChild(hb);
      card.appendChild(el("div", "fleet-meta", "pid " + (lease.worker_pid != null ? lease.worker_pid : "?")));
      grid.appendChild(card);
    });
  }

  function renderTriage(state) {
    var list = document.getElementById("triage-list");
    list.innerHTML = "";
    var hits = [];
    function scan(items, track) {
      (items || []).forEach(function (it) {
        var stage = it.curated_stage || "";
        if (SIDE_STAGES.indexOf(stage) !== -1) {
          hits.push({ id: it.feature_id || it.bug_id, stage: stage, track: track });
        }
      });
    }
    scan(state.features, "feature");
    scan(state.bugs, "bug");
    if (!hits.length) {
      list.appendChild(el("li", "triage-empty", "nothing requires action"));
      return;
    }
    hits.forEach(function (h) {
      var item = el("li", "triage-item");
      item.setAttribute("data-stage", h.stage);
      item.appendChild(chip(h.track, h.stage));
      item.appendChild(el("span", null, h.id + " — " + h.stage));
      list.appendChild(item);
    });
  }

  // ---- Liveness ----------------------------------------------------------
  function setLive(state) {
    var dot = document.getElementById("live-dot");
    var label = document.getElementById("live-label");
    var dim = document.getElementById("dim-overlay");
    var banner = document.getElementById("connection-banner");
    if (state === "live") {
      dot.className = "live-dot live-dot--live";
      label.textContent = "Live";
      dim.hidden = true;
      banner.hidden = true;
    } else if (state === "lost") {
      dot.className = "live-dot live-dot--lost";
      label.textContent = "Connection Lost";
      dim.hidden = false;
      banner.hidden = false;
    } else {
      dot.className = "live-dot live-dot--unknown";
      label.textContent = "Connecting…";
    }
  }

  function fetchState() {
    // AbortController gives us a hard timeout so a hung probe still trips the guard.
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, POLL_TIMEOUT_MS);
    return fetch("api/state", { signal: controller.signal, cache: "no-store" })
      .then(function (resp) {
        clearTimeout(timer);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .catch(function (err) {
        clearTimeout(timer);
        throw err;
      });
  }

  function renderAll(state) {
    window.PV._lastState = state;   // drill-down reads the latest polled state
    renderGraphTokens(state);
    renderQueues(state);
    renderFleet(state);
    renderTriage(state);
    var st = document.getElementById("server-time");
    if (st) st.textContent = state.server_time ? ("server " + state.server_time) : "";
  }

  function poll() {
    fetchState()
      .then(function (state) {
        setLive("live");
        renderAll(state);
      })
      .catch(function (err) {
        // Any fail/timeout: never present stale-as-live.
        console.warn("PV: poll failed —", err && err.message);
        setLive("lost");
      });
  }

  // ---- Expose internals (MUST precede start() — renderAll writes PV._lastState) ----
  window.PV = {
    get cy() { return cy; },
    get stageCoords() { return stageCoords; },
    get layoutReady() { return layoutReady; },
    poll: poll,
    _lastState: null,
    _badges: {},
    _completionLog: [],
  };

  // ---- Boot --------------------------------------------------------------
  function start() {
    bootstrapLayout();
    setLive("unknown");
    poll();
    setInterval(poll, POLL_INTERVAL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

/* ---- Trends tab (harness-telemetry-ledger Phase 3) ----------------------
 * Collapsed by default. On "Show", fetch /api/trends (pure-read, server-side
 * TtlCache-debounced) and render per-run aggregate tables + the deny-ledger
 * trend. An empty ledger renders the server's honest empty message — never
 * fabricated zeros. Self-contained IIFE: no coupling to the graph renderer.
 */
(function () {
  "use strict";
  var TRENDS_REFRESH_MS = 10000; // refresh while the pane is open
  var open = false;
  var timer = null;

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  }

  function fmt(v) {
    if (v === null || v === undefined) return "—";
    return String(v);
  }

  function fmtDuration(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 90) return Math.round(seconds) + "s";
    return Math.round(seconds / 60) + "m";
  }

  function table(headers, rows) {
    var t = el("table", null, "trends-table");
    var thead = document.createElement("thead");
    var hr = document.createElement("tr");
    headers.forEach(function (h) { hr.appendChild(el("th", h)); });
    thead.appendChild(hr);
    t.appendChild(thead);
    var tbody = document.createElement("tbody");
    rows.forEach(function (cells) {
      var tr = document.createElement("tr");
      cells.forEach(function (c) { tr.appendChild(el("td", c)); });
      tbody.appendChild(tr);
    });
    t.appendChild(tbody);
    return t;
  }

  function render(payload) {
    var empty = document.getElementById("trends-empty");
    var content = document.getElementById("trends-content");
    if (!empty || !content) return;
    content.textContent = "";
    if (!payload || payload.telemetry_available !== true) {
      empty.hidden = false;
      empty.textContent = (payload && payload.message) ||
        "no telemetry recorded for this window";
      // The deny ledger may still carry a trend even with no telemetry.
      if (payload && payload.deny_ledger && payload.deny_ledger.unacked_denies) {
        empty.textContent += " — deny ledger: " +
          payload.deny_ledger.unacked_denies + " unacked entr(ies)";
      }
      return;
    }
    empty.hidden = true;

    content.appendChild(el("div", "Per-run", "trends-subtitle"));
    content.appendChild(table(
      ["Run", "Pipeline", "Fwd cycles", "Meta cycles", "Completions",
       "Cyc/Compl", "Gate refusals", "Containment", "Halts", "Duration"],
      (payload.runs || []).map(function (r) {
        return [r.run_id, fmt(r.pipeline), fmt(r.forward_cycles),
                fmt(r.meta_cycles), fmt(r.completions),
                fmt(r.cycles_per_completion), fmt(r.gate_refusals),
                fmt(r.containment_refusals), fmt(r.halts),
                fmtDuration(r.duration_seconds)];
      })
    ));

    var halts = payload.halts || [];
    if (halts.length) {
      content.appendChild(el("div", "Halt dwell", "trends-subtitle"));
      content.appendChild(table(
        ["Item", "Reason", "Dwell"],
        halts.map(function (h) {
          return [fmt(h.item_id), fmt(h.terminal_reason),
                  h.dwell_seconds === null || h.dwell_seconds === undefined
                    ? "unresolved" : fmtDuration(h.dwell_seconds)];
        })
      ));
    }

    var dl = payload.deny_ledger || {};
    content.appendChild(el("div", "Deny ledger", "trends-subtitle"));
    content.appendChild(table(
      ["Guard denies", "Process friction", "Auto-readmits", "Unacked debt"],
      [[fmt(dl.guard_denies), fmt(dl.process_friction),
        fmt(dl.auto_readmits), fmt(dl.unacked_denies)]]
    ));
  }

  function fetchTrends() {
    fetch("api/trends", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function () {
        var empty = document.getElementById("trends-empty");
        if (empty) {
          empty.hidden = false;
          empty.textContent = "trends unavailable (fetch failed)";
        }
      });
  }

  function toggle() {
    var body = document.getElementById("trends-body");
    var btn = document.getElementById("trends-toggle");
    if (!body || !btn) return;
    open = !open;
    body.hidden = !open;
    btn.textContent = open ? "Hide" : "Show";
    if (open) {
      fetchTrends();
      timer = setInterval(fetchTrends, TRENDS_REFRESH_MS);
    } else if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function bind() {
    var btn = document.getElementById("trends-toggle");
    if (btn) btn.addEventListener("click", toggle);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
