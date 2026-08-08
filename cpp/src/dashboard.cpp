// C7: the operator dashboard page (L2-DASH-001..003).
//
// The page is a C++11 raw string literal. Held here rather than in a .html file
// converted at build time because L1-SYS-002 ships one executable: a generated
// header would put the page in the build system's hands, and the thing an
// auditor needs to read for L2-DASH-003 is the text that actually ships.
//
// The delimiter is )DASHBOARD" rather than )" -- the page contains )" inside
// its JavaScript, and the default delimiter would end the literal there.

#include "filemover/dashboard.hpp"

#include <string>

namespace filemover {
namespace {

const char kPage[] = R"DASHBOARD(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Background File Mover</title>
<style>
:root { color-scheme: light dark; }
body { font: 14px/1.5 system-ui, sans-serif; margin: 0; padding: 1.5rem; }
h1 { font-size: 1.1rem; margin: 0 0 1rem; }
#state { font-weight: 600; }
.bad { color: #b00020; }
.counts { display: flex; flex-wrap: wrap; gap: 1rem; margin: 0 0 1.25rem; padding: 0; list-style: none; }
.counts li { border: 1px solid rgba(128,128,128,.4); border-radius: 6px; padding: .5rem .75rem; min-width: 6rem; }
.counts .n { display: block; font-size: 1.5rem; font-weight: 600; }
.counts .k { font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; opacity: .75; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid rgba(128,128,128,.25); vertical-align: top; }
th { font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; opacity: .75; }
td.path { font-family: ui-monospace, monospace; font-size: .8rem; word-break: break-all; }
td.err { color: #b00020; font-size: .8rem; }
footer { margin-top: 1.5rem; font-size: .75rem; opacity: .7; }
</style>
</head>
<body>
<h1>Background File Mover</h1>
<p>Service: <span id="state">connecting</span> · <span id="live"></span></p>
<ul class="counts" id="counts"></ul>
<table>
<thead><tr><th>Job</th><th>State</th><th>Source</th><th>Destination</th><th>Updated</th></tr></thead>
<tbody id="rows"></tbody>
</table>
<footer id="foot"></footer>
<script>
"use strict";

// L2-DASH-003. EVERY dynamic value in this page goes through one of these two
// functions, and neither can produce markup: textContent and createTextNode
// insert a text node, so a filename containing <script> renders as the
// characters "<script>" and nothing is parsed as HTML.
//
// There is deliberately no escaping helper anywhere in this file. An escaper is
// a function that can be forgotten at one call site, or applied twice, or
// applied to the wrong context (an attribute is not a text node). Removing the
// parse instead of neutralising the input leaves nothing to forget.
function setText(node, value) {
  node.textContent = value === null || value === undefined ? "" : String(value);
}

function cell(row, value, className) {
  var td = document.createElement("td");
  if (className) { td.className = className; }
  td.appendChild(document.createTextNode(
    value === null || value === undefined ? "" : String(value)));
  row.appendChild(td);
  return td;
}

function clear(node) {
  // removeChild in a loop. Emptying a node by assigning "" to the markup
  // property is genuinely harmless, and is still not done here: allowing it
  // would mean the gate has to tell safe assignments from unsafe ones, which
  // it cannot do from a pattern. The rule is that the property is never
  // written, and this is three lines.
  while (node.firstChild) { node.removeChild(node.firstChild); }
}

function stamp(ms) {
  if (!ms) { return ""; }
  var d = new Date(ms);
  if (isNaN(d.getTime())) { return ""; }
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

var STATES = ["QUEUED", "RENAMING", "TRANSFERRING", "DONE", "FAILED"];

function renderCounts(counts) {
  var list = document.getElementById("counts");
  clear(list);
  for (var i = 0; i < STATES.length; i++) {
    var key = STATES[i];
    var li = document.createElement("li");
    var n = document.createElement("span");
    n.className = "n";
    setText(n, counts && counts[key] !== undefined ? counts[key] : 0);
    var k = document.createElement("span");
    k.className = "k";
    setText(k, key);
    li.appendChild(n);
    li.appendChild(k);
    list.appendChild(li);
  }
}

function renderRows(jobs) {
  var body = document.getElementById("rows");
  clear(body);
  if (!jobs || !jobs.length) {
    var empty = document.createElement("tr");
    var td = cell(empty, "No jobs recorded.");
    td.colSpan = 5;
    body.appendChild(empty);
    return;
  }
  for (var i = 0; i < jobs.length; i++) {
    var job = jobs[i];
    var row = document.createElement("tr");
    cell(row, job.id);
    cell(row, job.state);
    cell(row, job.source, "path");
    cell(row, job.dest, "path");
    cell(row, stamp(job.updated_at_ms));
    body.appendChild(row);
    if (job.error) {
      var errRow = document.createElement("tr");
      var errCell = cell(errRow, job.error, "err");
      errCell.colSpan = 5;
      body.appendChild(errRow);
    }
  }
}

function poll() {
  var req = new XMLHttpRequest();
  req.open("GET", "/api/status", true);
  req.onreadystatechange = function () {
    if (req.readyState !== 4) { return; }
    var state = document.getElementById("state");
    if (req.status !== 200) {
      state.className = "bad";
      setText(state, req.status === 0 ? "unreachable" : "unavailable (" + req.status + ")");
      return;
    }
    var data;
    try { data = JSON.parse(req.responseText); }
    catch (e) {
      state.className = "bad";
      setText(state, "unreadable response");
      return;
    }
    state.className = "";
    setText(state, data.running ? "running" : "stopped");
    setText(document.getElementById("live"),
            "queued " + (data.runnable || 0) + " · in flight " + (data.active || 0));
    renderCounts(data.counts);
    renderRows(data.jobs);
    setText(document.getElementById("foot"), "Updated " + stamp(Date.now()));
  };
  req.send(null);
}

// L2-DASH-001: a fixed interval. Deliberately not adaptive -- a dashboard that
// polls faster when things are busy adds load exactly when the service has
// least to spare, and the control plane's handler pool is bounded (ADR-0013).
poll();
setInterval(poll, 2000);
</script>
</body>
</html>
)DASHBOARD";

}  // namespace

const std::string& dashboard_html() {
    // A function-local static, not a namespace-scope one. Constructing a
    // std::string at namespace scope runs before main and can throw where
    // nothing is able to catch it -- the process dies during dynamic
    // initialisation, with no log line, before the service exists to report it
    // (cert-err58-cpp). A local static is constructed on first use instead, and
    // C++11 guarantees that initialisation is thread-safe, which matters
    // because this is first reached from a request handler thread.
    static const std::string page(kPage);
    return page;
}

const char* dashboard_content_type() { return "text/html; charset=utf-8"; }

}  // namespace filemover
