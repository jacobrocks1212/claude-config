/* Lazy Fleet home page (cross-repo-fleet-view D4-B).
 *
 * Render-only over GET api/fleet (relative URL — the page is served at /):
 * a compact per-repo table + the cross-repo "Needs attention" triage strip.
 * The payload is SHALLOW by design (D5); every link drills into the shipped
 * per-repo three-pane view at repo/<slug>/ for full probe fidelity.
 *
 * Poll interval is strictly greater than the server-side fleet TTL (~5s) so
 * each poll can observe a fresh aggregate without hammering the producer.
 */
(function () {
  "use strict";

  var POLL_MS = 6000; // > fleet_ttl_seconds (5s)

  var rowsEl = document.getElementById("fleet-rows");
  var triageEl = document.getElementById("fleet-triage");
  var triageListEl = document.getElementById("fleet-triage-list");
  var triageCountEl = document.getElementById("fleet-triage-count");
  var refreshEl = document.getElementById("fleet-refresh");
  var connEl = document.getElementById("fleet-conn");
  var lastFetchedAt = null;

  function fmtAge(seconds) {
    if (seconds === null || seconds === undefined) { return "age unknown"; }
    var s = Math.max(0, Math.round(seconds));
    if (s < 60) { return s + "s"; }
    if (s < 3600) { return Math.round(s / 60) + "m"; }
    if (s < 48 * 3600) { return (s / 3600).toFixed(1).replace(/\.0$/, "") + "h"; }
    return Math.round(s / (24 * 3600)) + "d";
  }

  var BADGE_LABEL = {
    "idle": "idle",
    "run-active": "active",
    "run-silent": "silent",
    "stale-marker": "stale marker"
  };

  function badgeCell(marker) {
    var span = document.createElement("span");
    var badge = marker && marker.badge ? marker.badge : "idle";
    span.className = "badge badge-" + badge;
    var label = BADGE_LABEL[badge] || badge;
    if (badge === "idle") {
      span.textContent = label;
    } else {
      span.textContent = label + " (" + fmtAge(marker.age_seconds) + ")";
      var bits = [];
      if (marker.pipeline) { bits.push("pipeline: " + marker.pipeline); }
      if (marker.work_branch) { bits.push("branch: " + marker.work_branch); }
      if (badge === "stale-marker") {
        bits.push("marker ≥24h old — presumed-dead run; reclamation is script-owned (no action here)");
      }
      span.title = bits.join(" · ");
    }
    return span;
  }

  function haltSummary(row) {
    var halts = (row.features.halts || []).concat(row.bugs.halts || []);
    if (!halts.length) { return document.createTextNode("—"); }
    var frag = document.createDocumentFragment();
    halts.forEach(function (h, i) {
      if (i > 0) { frag.appendChild(document.createTextNode(" ")); }
      var s = document.createElement("span");
      s.className = "halt halt-" + h.kind;
      s.textContent = (h.kind === "blocked" ? "⛔" : "⬡") + " " + h.id;
      s.title = h.kind === "blocked" ? "BLOCKED.md present" : "NEEDS_INPUT.md present";
      frag.appendChild(s);
    });
    return frag;
  }

  function render(payload) {
    var repos = payload.repos || [];
    rowsEl.textContent = "";
    if (!repos.length) {
      var tr0 = document.createElement("tr");
      var td0 = document.createElement("td");
      td0.colSpan = 6;
      td0.className = "fleet-empty";
      td0.textContent = "no lazy-enabled repos discovered (~/source/repos glob + ~/.claude/lazy-repos.json + live run markers)";
      tr0.appendChild(td0);
      rowsEl.appendChild(tr0);
    }
    var triage = [];
    repos.forEach(function (row) {
      var tr = document.createElement("tr");
      if (row.error) { tr.className = "fleet-error-row"; }

      var tdName = document.createElement("td");
      var link = document.createElement("a");
      link.href = "repo/" + encodeURIComponent(row.slug) + "/";
      link.textContent = row.name || row.slug;
      link.title = row.repo_root + " — open the per-repo view (full probe)";
      tdName.appendChild(link);
      tr.appendChild(tdName);

      var tdRun = document.createElement("td");
      if (row.error) {
        var err = document.createElement("span");
        err.className = "badge badge-error";
        err.textContent = "error";
        err.title = row.error;
        tdRun.appendChild(err);
        tdRun.appendChild(document.createTextNode(" " + row.error));
      } else {
        tdRun.appendChild(badgeCell(row.marker));
      }
      tr.appendChild(tdRun);

      var tdF = document.createElement("td");
      tdF.className = "num";
      tdF.textContent = String(row.features.depth);
      tr.appendChild(tdF);

      var tdB = document.createElement("td");
      tdB.className = "num";
      tdB.textContent = String(row.bugs.depth);
      tr.appendChild(tdB);

      var tdH = document.createElement("td");
      tdH.appendChild(haltSummary(row));
      tr.appendChild(tdH);

      var tdL = document.createElement("td");
      if (row.lazy_queue_doc && row.lazy_queue_url) {
        var gh = document.createElement("a");
        gh.href = row.lazy_queue_url;
        gh.target = "_blank";
        gh.rel = "noopener";
        gh.textContent = "📱 LAZY_QUEUE.md";
        gh.title = "GitHub-mobile queue doc (peer channel)";
        tdL.appendChild(gh);
      } else {
        tdL.textContent = "—";
      }
      tr.appendChild(tdL);

      rowsEl.appendChild(tr);

      (row.features.halts || []).forEach(function (h) {
        triage.push({ row: row, halt: h });
      });
      (row.bugs.halts || []).forEach(function (h) {
        triage.push({ row: row, halt: h });
      });
    });

    triageListEl.textContent = "";
    if (triage.length) {
      triage.forEach(function (t) {
        var li = document.createElement("li");
        var mark = t.halt.kind === "blocked" ? "⛔" : "⬡";
        var a = document.createElement("a");
        a.href = "repo/" + encodeURIComponent(t.row.slug) + "/";
        a.textContent = t.row.name + " / " + t.halt.id;
        li.appendChild(document.createTextNode(mark + " "));
        li.appendChild(a);
        li.appendChild(document.createTextNode(
          " — " + (t.halt.kind === "blocked" ? "BLOCKED.md" : "NEEDS_INPUT.md") + " present"));
        triageListEl.appendChild(li);
      });
      triageCountEl.textContent = "(" + triage.length + ")";
      triageEl.hidden = false;
    } else {
      triageEl.hidden = true;
    }
  }

  function tickRefreshAge() {
    if (lastFetchedAt === null) { return; }
    var age = Math.round((Date.now() - lastFetchedAt) / 1000);
    refreshEl.textContent = "refreshed " + age + "s ago";
  }

  function poll() {
    fetch("api/fleet", { cache: "no-store" })
      .then(function (resp) {
        if (!resp.ok) { throw new Error("HTTP " + resp.status); }
        return resp.json();
      })
      .then(function (payload) {
        connEl.hidden = true;
        lastFetchedAt = Date.now();
        render(payload);
        tickRefreshAge();
      })
      .catch(function () {
        connEl.hidden = false; // failure honesty: banner, never a blank page
      });
  }

  poll();
  setInterval(poll, POLL_MS);
  setInterval(tickRefreshAge, 1000);
})();
