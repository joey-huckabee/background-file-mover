"use strict";
(function () {
  var csrf = null;
  var cursors = [null];   // cursor stack: index = page number - 1
  var page = 0;
  var selected = null;
  var pageGen = 0, detailGen = 0;   // ignore superseded replies

  function $(id) { return document.getElementById(id); }
  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text !== undefined && text !== null) { e.textContent = String(text); }
    if (cls) { e.className = cls; }
    return e;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  // Lossless JSON: integers become BigInt so u64/i64 values never pass through
  // binary64. Strict RFC 8259 grammar; throws on anything else.
  function parseJSON(text) {
    var i = 0;
    function ws() { while (i < text.length && " \t\n\r".indexOf(text[i]) >= 0) { i++; } }
    function fail() { throw new Error("invalid JSON"); }
    function value() {
      ws();
      var c = text[i];
      if (c === "{") {
        i++; var obj = {}; ws();
        if (text[i] === "}") { i++; return obj; }
        for (;;) {
          ws(); if (text[i] !== "\"") { fail(); }
          var key = string(); ws(); if (text[i++] !== ":") { fail(); }
          obj[key] = value(); ws();
          if (text[i] === ",") { i++; continue; }
          if (text[i] === "}") { i++; return obj; }
          fail();
        }
      }
      if (c === "[") {
        i++; var arr = []; ws();
        if (text[i] === "]") { i++; return arr; }
        for (;;) {
          arr.push(value()); ws();
          if (text[i] === ",") { i++; continue; }
          if (text[i] === "]") { i++; return arr; }
          fail();
        }
      }
      if (c === "\"") { return string(); }
      if (text.startsWith("true", i)) { i += 4; return true; }
      if (text.startsWith("false", i)) { i += 5; return false; }
      if (text.startsWith("null", i)) { i += 4; return null; }
      var m = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/.exec(text.slice(i));
      if (!m) { fail(); }
      i += m[0].length;
      return (m[2] || m[3]) ? Number(m[0]) : BigInt(m[0]);
    }
    function string() {
      var m = /^"(?:[^"\\\u0000-\u001f]|\\(?:["\\\/bfnrt]|u[0-9a-fA-F]{4}))*"/.exec(text.slice(i));
      if (!m) { fail(); }
      i += m[0].length;
      return JSON.parse(m[0]);
    }
    var result = value(); ws();
    if (i !== text.length) { fail(); }
    return result;
  }

  function request(path, deliberate, init) {
    init = init || {};
    init.credentials = "same-origin";
    init.cache = "no-store";
    init.headers = init.headers || {};
    if (deliberate && csrf) {
      init.headers["Mover-Admin-Activity"] = "interaction";
      init.headers["Mover-CSRF-Token"] = csrf;
    }
    return fetch(path, init).then(function (r) {
      if (r.status === 401) { show(false); throw new Error("signed out"); }
      return r.text().then(function (text) {
        var body = null;
        try { body = text ? parseJSON(text) : null; } catch (e) { body = null; }
        return { status: r.status, body: body, headers: r.headers };
      });
    });
  }

  function show(signedIn) {
    $("signin").hidden = signedIn;
    $("shell").hidden = !signedIn;
    if (!signedIn) {
      csrf = null; cursors = [null]; page = 0; selected = null; pageGen++; detailGen++;
      $("detail").hidden = true;
      $("password").value = "";
      $("username").focus();
    }
  }

  var STATE = { Accepted: "Accepted", Claimed: "Claimed", Committed: "Committed" };
  var CONDITION = {
    Committed: "Committed", ReviewRequired: "Needs review", AwaitingClaims: "Awaiting claims",
    Retrying: "Retrying delivery", Ready: "Ready for delivery"
  };
  function label(map, value) { return map[value] || String(value); }
  function badge(condition) {
    var cls = condition === "Committed" ? "badge green" : condition === "ReviewRequired" ? "badge amber" : "badge blue";
    return el("span", label(CONDITION, condition), cls);
  }
  function identity(item) {
    return item.recording_id !== undefined ? "Recording " + item.recording_id : "Legacy submission " + item.submission_id;
  }
  function time(seconds) {
    if (seconds === null || seconds === undefined) { return "—"; }
    var n = Number(seconds);
    if (!Number.isSafeInteger(n)) { return String(seconds); }
    return new Date(n * 1000).toISOString().replace("T", " ").replace(".000Z", " UTC");
  }

  function loadPage(deliberate) {
    var mine = ++pageGen;
    var path = "/api/v2/admin/jobs?limit=50" + (cursors[page] ? "&cursor=" + encodeURIComponent(cursors[page]) : "");
    $("history-status").textContent = "Loading…";
    return request(path, deliberate).then(function (r) {
      if (mine !== pageGen) { return; }
      if (r.status !== 200 || !r.body) { $("history-status").textContent = "Job history is unavailable (" + r.status + "). Try Refresh."; return; }
      renderPage(r.body);
    }).catch(function (e) {
      if (mine === pageGen && e.message !== "signed out") { $("history-status").textContent = "The service could not be reached."; }
    });
  }

  function renderPage(body) {
    var rows = $("history-rows");
    clear(rows);
    var items = body.items;
    if (items.length === 0) {
      $("history-status").textContent = page === 0 ? "No jobs are retained." : "No jobs on this page.";
    } else {
      $("history-status").textContent = "Page " + (page + 1) + " · " + items.length + " job" + (items.length === 1 ? "" : "s") + " · ascending job ID";
    }
    items.forEach(function (item) {
      var tr = el("tr");
      var cell = el("td");
      var open = el("button", "Job #" + item.job_id, "link");
      open.type = "button";
      open.addEventListener("click", function () { openDetail(item.job_id); });
      cell.appendChild(open);
      cell.appendChild(el("span", identity(item), "sub mono"));
      tr.appendChild(cell);
      tr.appendChild(el("td", item.generator_id));
      tr.appendChild(el("td", label(STATE, item.state)));
      var c = el("td"); c.appendChild(badge(item.condition)); tr.appendChild(c);
      tr.appendChild(el("td", item.source_paths_released ? "Released" : "Producer must keep"));
      rows.appendChild(tr);
    });
    $("prev").disabled = page === 0;
    $("next").disabled = body.next_cursor === null;
    if (body.next_cursor !== null) { cursors[page + 1] = body.next_cursor; cursors.length = page + 2; }
  }

  function openDetail(jobId) {
    selected = String(jobId);
    var mine = ++detailGen;
    $("detail").hidden = false;
    $("detail-title").textContent = "Job #" + selected;
    clear($("detail-body"));
    $("detail-body").appendChild(el("p", "Loading…", "muted"));
    return request("/api/v2/jobs/" + encodeURIComponent(selected), true).then(function (r) {
      if (mine !== detailGen) { return; }
      clear($("detail-body"));
      if (r.status === 404) {
        $("detail-body").appendChild(el("p", "This job is no longer tracked. Refresh the history.", "notice"));
        return;
      }
      if (r.status !== 200 || !r.body) {
        $("detail-body").appendChild(el("p", "Job details are unavailable (" + r.status + ").", "notice"));
        return;
      }
      renderDetail(r.body);
      $("detail-title").focus();
    }).catch(function () {});
  }

  function fact(list, name, value) {
    list.appendChild(el("dt", name));
    list.appendChild(el("dd", value));
  }

  function renderDetail(job) {
    var d = job.details;
    var body = $("detail-body");
    var facts = el("dl", null, "facts");
    fact(facts, "State", label(STATE, job.state));
    fact(facts, "Condition", label(CONDITION, d.condition));
    fact(facts, "Identity", identity(d));
    fact(facts, "Generator", d.generator_id);
    fact(facts, "Source custody", job.source_paths_released ? "Released to the mover" : "Producer must keep source paths");
    fact(facts, "Manifest phase", d.manifest_phase === null ? "Not started" : String(d.manifest_phase));
    fact(facts, "Automatic source cleanup", d.source_cleanup_enabled ? "On" : "Off");
    fact(facts, "Review epoch", String(d.review_epoch));
    body.appendChild(facts);

    var published = 0, known = 0n, unknown = 0;
    d.files.forEach(function (f) {
      if (f.phase === "Published" || f.phase === "SourceRemoved") { published++; }
      if (f.size_bytes === null) { unknown++; } else { known += BigInt(f.size_bytes); }
    });
    body.appendChild(el("h3", "Files · " + published + " of " + d.files.length + " published"));
    body.appendChild(el("p", unknown === 0
      ? "Measured size: " + known.toString() + " bytes"
      : "Known bytes: " + known.toString() + " + " + unknown + " unmeasured file" + (unknown === 1 ? "" : "s"), "muted"));
    var table = el("table");
    var head = el("tr");
    ["File", "Phase", "Size (bytes)", "Transfer", "Attempt"].forEach(function (h) { head.appendChild(el("th", h)); });
    var thead = el("thead"); thead.appendChild(head); table.appendChild(thead);
    var tbody = el("tbody");
    d.files.forEach(function (f) {
      var tr = el("tr");
      tr.appendChild(el("td", f.name, "mono"));
      tr.appendChild(el("td", f.phase));
      tr.appendChild(el("td", f.size_bytes === null ? "Not measured" : f.size_bytes.toString()));
      tr.appendChild(el("td", f.transfer_phase === null ? "—" : f.transfer_phase));
      tr.appendChild(el("td", f.attempt === null ? "—" : f.attempt.toString()));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    var wrap = el("div", null, "scroll"); wrap.appendChild(table); body.appendChild(wrap);

    if (d.missing.length) {
      body.appendChild(el("h3", "Missing source files"));
      d.missing.forEach(function (m) {
        body.appendChild(el("p", "File " + m.file_id + ": deadline " + time(m.deadline) +
          (m.blocked ? " · blocked" : "") + (m.deadline_elapsed ? " · deadline elapsed" : ""), "notice"));
      });
    }
    if (d.delivery_retry) {
      body.appendChild(el("h3", "Delivery retry"));
      body.appendChild(el("p", d.delivery_retry.failures.toString() + " failure(s) · next attempt after " +
        time(d.delivery_retry.retry_after) + " · code " + d.delivery_retry.code, "notice"));
    }
    if (d.latest_resume) {
      body.appendChild(el("h3", "Latest delivery resume"));
      body.appendChild(el("p", time(d.latest_resume.recorded_at) + " · " + d.latest_resume.actor + " · " + d.latest_resume.reason));
    }
    if (d.latest_missing_reset) {
      body.appendChild(el("h3", "Latest missing-file reset"));
      body.appendChild(el("p", time(d.latest_missing_reset.recorded_at) + " · " + d.latest_missing_reset.actor + " · " + d.latest_missing_reset.reason));
    }
  }

  function signedIn(r) {
    csrf = r.headers.get("Mover-CSRF-Token");
    var minutes = Math.round(Number(r.body.inactivity_timeout_seconds) / 60);
    $("idle").textContent = "Session ends after " + minutes + " minutes without activity.";
    $("shell-error").textContent = "";
    show(true);
    return loadPage(false);
  }

  function loadSession() {
    return request("/api/v2/admin/session", false).then(function (r) {
      if (r.status === 200 && r.body) { return signedIn(r); }
      show(false);
    }).catch(function (e) {
      if (e.message !== "signed out") { show(false); $("signin-error").textContent = "The service could not be reached."; }
    });
  }

  var messages = {
    401: "Invalid username or password.",
    429: "Too many sign-in attempts. Try again in a minute.",
    503: "The service is busy. Try again shortly."
  };
  $("signin-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var username = $("username").value, password = $("password").value;
    if (!username || !password) { $("signin-error").textContent = "Enter your username and password."; return; }
    $("signin-button").disabled = true;
    $("signin-error").textContent = "";
    fetch("/api/v2/admin/login", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username, password: password })
    }).then(function (r) {
      $("password").value = "";
      if (r.status === 200) { return loadSession(); }
      $("signin-error").textContent = messages[r.status] || "Sign-in failed. Try again.";
    }).catch(function () {
      $("signin-error").textContent = "The service could not be reached.";
    }).then(function () { $("signin-button").disabled = false; });
  });
  $("signout").addEventListener("click", function () {
    $("signout").disabled = true;
    fetch("/api/v2/admin/logout", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Mover-CSRF-Token": csrf || "" }
    }).then(function (r) {
      if (r.status === 204 || r.status === 401) { show(false); return; }
      $("shell-error").textContent = "Sign-out failed. Try again.";
    }).catch(function () {
      $("shell-error").textContent = "The service could not be reached.";
    }).then(function () { $("signout").disabled = false; });
  });
  $("refresh").addEventListener("click", function () {
    loadPage(true).then(function () { if (selected) { openDetail(selected); } });
  });
  $("prev").addEventListener("click", function () { if (page > 0) { page--; loadPage(true); } });
  $("next").addEventListener("click", function () { if (cursors[page + 1]) { page++; loadPage(true); } });
  $("close-detail").addEventListener("click", function () { selected = null; $("detail").hidden = true; });
  loadSession();
})();
