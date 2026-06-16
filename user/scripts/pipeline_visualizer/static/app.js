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
      ],
    });
    cy.fit(undefined, 30);
    layoutReady = true;
  }

  // ---- Token mapping -----------------------------------------------------
  // Map a curated_stage -> the track node it sits on. Side-states snap to the
  // nearest workflow anchor on that track (offset visually via Y in Phase 3).
  function anchorStageFor(track, curated) {
    var stages = track === "bug" ? BUG_STAGES : FEATURE_STAGES;
    if (stages.indexOf(curated) !== -1) return curated;
    // Side-states have no dedicated column in Phase 2 — anchor near Implement so
    // the token is visible; the triage strip is the authoritative side-state surface.
    if (SIDE_STAGES.indexOf(curated) !== -1) return "Implement";
    return "Pending";
  }

  function tokenVisual(item, track) {
    var stage = item.curated_stage || "Pending";
    var color = STAGE_COLOR[stage] || STAGE_COLOR.Pending;
    var shapeMap = {
      "Needs-input": "hexagon",
      "Blocked": "octagon",
    };
    var baseShape = track === "bug" ? "rectangle" : "ellipse";
    var shape = shapeMap[stage] || (stage === "Deferred" ? baseShape : baseShape);
    return {
      color: color,
      shape: shape,
      hollow: stage === "Pending" ? "1" : "0",
      ghost: stage === "Deferred" ? "1" : "0",
    };
  }

  function renderGraphTokens(state) {
    if (!cy) return;
    cy.nodes('[kind="token"]').remove();   // full re-render per poll (Phase 2)
    var batch = [];
    function place(items, track) {
      var perStageCount = {};
      (items || []).forEach(function (item, i) {
        var id = (item.feature_id || item.bug_id || ("item-" + i));
        var stage = item.curated_stage || "Pending";
        var anchor = anchorStageFor(track, stage);
        var anchorId = trackNodeId(track, anchor);
        var base = stageCoords[anchorId] || { x: 0, y: 0 };
        // Micro-grid offset so multiple tokens on one stage don't fully overlap.
        var k = perStageCount[anchorId] || 0;
        perStageCount[anchorId] = k + 1;
        var dx = (k % 3) * 8 - 8;
        var dy = Math.floor(k / 3) * 14 + (track === "bug" ? 22 : -22);
        var vis = tokenVisual(item, track);
        batch.push({
          group: "nodes",
          data: {
            id: "tok:" + track + ":" + id, kind: "token", label: "",
            color: vis.color, shape: vis.shape, hollow: vis.hollow, ghost: vis.ghost,
            itemId: id, stage: stage, track: track,
          },
          position: { x: base.x + dx, y: base.y + dy },
        });
      });
    }
    place(state.features, "feature");
    place(state.bugs, "bug");
    if (batch.length) cy.add(batch);
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

  function renderQueues(state) {
    renderQueueCol("queue-features", state.features, "feature");
    renderQueueCol("queue-bugs", state.bugs, "bug");
  }

  function renderQueueCol(elId, items, track) {
    var list = document.getElementById(elId);
    list.innerHTML = "";
    if (!items || !items.length) {
      list.appendChild(el("li", "queue-empty", "empty"));
      return;
    }
    items.forEach(function (item) {
      var id = item.feature_id || item.bug_id || "?";
      var stage = item.curated_stage || "Pending";
      var row = el("li", "queue-row");
      row.appendChild(chip(track, stage));
      row.appendChild(el("span", "queue-id", id));
      var meta = item.queue_meta || {};
      if (meta.tier != null) row.appendChild(el("span", "badge badge--tier", "T" + meta.tier));
      if (meta.adhoc) row.appendChild(el("span", "badge badge--adhoc", "ad-hoc"));
      if (meta.stub) row.appendChild(el("span", "badge badge--stub", "stub"));
      if (meta.severity) row.appendChild(el("span", "badge", meta.severity));
      list.appendChild(row);
    });
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
    return fetch("/api/state", { signal: controller.signal, cache: "no-store" })
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

  // Expose internals for Phase 3 / manual debugging.
  window.PV = {
    get cy() { return cy; },
    get stageCoords() { return stageCoords; },
    get layoutReady() { return layoutReady; },
    poll: poll,
  };
})();
