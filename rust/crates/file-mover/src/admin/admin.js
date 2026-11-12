"use strict";
(function () {
  var csrf = null;
  var view = "history";
  var cursors = [null];   // cursor stack: index = page number - 1
  var page = 0;
  var descending = false;
  var openJob = null;     // job ID whose inline detail is open
  var rowsById = {};      // list rows on the current page, by job ID
  // At most one read of each kind in flight; a new read aborts the old one.
  var ctl = { page: null, detail: null, storage: null, settings: null };
  var gen = { page: 0, detail: 0, storage: 0, settings: 0 };
  var refreshing = false;

  function $(id) { return document.getElementById(id); }
  function el(tag, text, cls, title) {
    var e = document.createElement(tag);
    if (text !== undefined && text !== null) { e.textContent = String(text); }
    if (cls) { e.className = cls; }
    if (title) { e.title = title; }
    return e;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

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

  function request(path, deliberate, kind) {
    if (ctl[kind]) { ctl[kind].abort(); }
    ctl[kind] = new AbortController();
    var mine = ++gen[kind];
    var headers = {};
    if (deliberate && csrf) {
      headers["Mover-Admin-Activity"] = "interaction";
      headers["Mover-CSRF-Token"] = csrf;
    }
    return fetch(path, { credentials: "same-origin", cache: "no-store", headers: headers, signal: ctl[kind].signal })
      .then(function (r) {
        if (r.status === 401) { show(false); throw new Error("signed out"); }
        return r.text().then(function (text) {
          var body = null;
          try { body = text ? parseJSON(text) : null; } catch (e) { body = null; }
          return { status: r.status, body: body, headers: r.headers, current: mine === gen[kind] };
        });
      });
  }
  function quiet(e) { return e.name === "AbortError" || e.message === "signed out"; }

  function bytes(value) {
    if (value === null || value === undefined) { return "—"; }
    var n = BigInt(value);
    var units = ["bytes", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"];
    var u = 0, scale = 1n;
    while (u < units.length - 1 && n >= scale * 1024n) { scale *= 1024n; u++; }
    if (u === 0) { return n.toString() + " bytes"; }
    var hundredths = (n * 100n) / scale;
    var whole = hundredths / 100n, frac = (hundredths % 100n).toString().padStart(2, "0");
    return whole.toString() + "." + frac + " " + units[u] + " (" + n.toString() + " bytes)";
  }
  function short(value) { return bytes(value).split(" (")[0]; }
  function time(seconds) {
    if (seconds === null || seconds === undefined) { return "—"; }
    var n = Number(seconds);
    if (!Number.isSafeInteger(n)) { return String(seconds); }
    return new Date(n * 1000).toISOString().replace("T", " ").replace(".000Z", " UTC");
  }

  // ---- Plain-language vocabulary (technical value kept in hover text) ----
  var ATTENTION = {
    AwaitingClaims: ["Waiting for files", "blue"], Ready: ["Ready to deliver", "blue"],
    Retrying: ["Retrying delivery", "blue"], ReviewRequired: ["Needs review", "amber"]
  };
  var ACTIVITY = {
    Committed: "Delivered", AwaitingClaims: "Waiting for the source files",
    Ready: "Ready to deliver", Retrying: "Retrying delivery", ReviewRequired: "Needs review"
  };
  var FILE_STATUS = {
    Pending: "Waiting", Claimed: "Acquired", Verified: "Verified",
    Published: "Delivered", SourceRemoved: "Delivered, source removed"
  };
  function identityLabel(item) {
    return item.recording_id !== undefined ? ["Request ID", item.recording_id] : ["Legacy submission", item.submission_id];
  }
  function finalStep(mode) { return mode === "Move" ? "Moved" : "Copied"; }
  function progress(item, mode) {
    var wrap = el("span", null, "steps");
    var done = [true, item.source_paths_released, item.state === "Committed"];
    var labels = ["Received", "Acquired", finalStep(mode)];
    var tips = ["The mover accepted the request", "The mover has taken over the source files; the sender may let go",
      "All files are at the destination (" + (mode === "Move" ? "source removed" : "source kept") + ")"];
    labels.forEach(function (label, i) {
      wrap.appendChild(el("span", label, "step" + (done[i] ? " done" : ""), tips[i]));
      if (i < 2) { wrap.appendChild(el("span", "›", "arrow")); }
    });
    var attention = ATTENTION[item.condition];
    if (attention) {
      wrap.appendChild(el("span", attention[0], "badge " + attention[1], "condition: " + item.condition));
    }
    return wrap;
  }

  // ---- Views ----
  function setView(next) {
    view = next;
    ["history", "storage", "settings"].forEach(function (name) {
      $(name + "-view").hidden = name !== next;
      var tab = $("tab-" + name);
      tab.classList.toggle("active", name === next);
      tab.setAttribute("aria-pressed", String(name === next));
    });
    $("view-title").textContent = { history: "Job history", storage: "Storage", settings: "Settings" }[next];
  }

  // ---- Job history ----
  function pagePath() {
    var q = "?limit=50" + (descending ? "&order=desc" : "");
    if (cursors[page]) { q += "&cursor=" + encodeURIComponent(cursors[page]); }
    return "/api/v2/admin/jobs" + q;
  }
  function loadPage(deliberate) {
    $("history-status").textContent = "Loading…";
    $("prev").disabled = true; $("next").disabled = true;
    return request(pagePath(), deliberate, "page").then(function (r) {
      if (!r.current) { return false; }
      if (r.status !== 200 || !r.body) {
        $("history-status").textContent = "Job history is unavailable (" + r.status + "). Try Refresh.";
        $("prev").disabled = page === 0;
        return false;
      }
      renderPage(r.body);
      return true;
    }).catch(function (e) {
      if (!quiet(e)) { $("history-status").textContent = "The service could not be reached."; }
      return false;
    });
  }
  function renderPage(body) {
    var rows = $("history-rows");
    clear(rows);
    rowsById = {};
    var items = body.items;
    $("history-status").textContent = items.length === 0
      ? (page === 0 ? "No jobs are kept." : "No jobs on this page.")
      : "Page " + (page + 1) + " · " + items.length + " job" + (items.length === 1 ? "" : "s");
    items.forEach(function (item) {
      rowsById[item.job_id] = item;
      var tr = el("tr", null, "job-row");
      tr.dataset.job = item.job_id;
      var cell = el("td");
      var open = el("button", "Job #" + item.job_id, "link", "Show or hide this job's details");
      open.type = "button";
      open.setAttribute("aria-expanded", "false");
      open.addEventListener("click", function () { toggleDetail(item.job_id, tr, open); });
      cell.appendChild(open);
      var id = identityLabel(item);
      cell.appendChild(el("span", id[0] + " " + id[1], "sub mono"));
      tr.appendChild(cell);
      var p = el("td"); p.appendChild(progress(item, item.transfer_mode)); tr.appendChild(p);
      tr.appendChild(el("td", item.files_delivered + " of " + item.files_total));
      var size = item.unmeasured_files > 0n
        ? short(item.measured_bytes) + " + " + item.unmeasured_files + " unmeasured"
        : short(item.measured_bytes);
      tr.appendChild(el("td", size, null, BigInt(item.measured_bytes).toString() + " bytes measured"));
      tr.appendChild(el("td", item.source_folder + "/", "mono"));
      tr.appendChild(el("td", item.destination_folder + "/", "mono"));
      rows.appendChild(tr);
    });
    $("prev").disabled = page === 0;
    $("next").disabled = body.next_cursor === null;
    if (body.next_cursor !== null) { cursors[page + 1] = body.next_cursor; cursors.length = page + 2; }
    if (openJob && rowsById[openJob]) {
      var row = rows.querySelector('tr[data-job="' + CSS.escape(openJob) + '"]');
      if (row) { insertDetail(openJob, row, row.querySelector("button"), false); }
    } else {
      openJob = null;
    }
  }

  function closeDetail() {
    if (ctl.detail) { ctl.detail.abort(); }
    gen.detail++;
    var existing = document.querySelector("tr.detail-row");
    if (existing) {
      var prev = existing.previousSibling;
      if (prev) { var b = prev.querySelector("button"); if (b) { b.setAttribute("aria-expanded", "false"); } }
      existing.remove();
    }
  }
  function toggleDetail(jobId, row, button) {
    var wasOpen = openJob === jobId;
    closeDetail();
    openJob = null;
    if (!wasOpen) { insertDetail(jobId, row, button, true); }
  }
  function insertDetail(jobId, row, button, deliberate) {
    closeDetail();
    openJob = jobId;
    button.setAttribute("aria-expanded", "true");
    var tr = el("tr", null, "detail-row");
    var td = el("td"); td.colSpan = 6;
    var box = el("div", null, "detail");
    box.appendChild(el("p", "Loading…", "muted"));
    td.appendChild(box); tr.appendChild(td);
    row.after(tr);
    // Sequential reads: detail, then this job's reservations.
    request("/api/v2/jobs/" + encodeURIComponent(jobId), deliberate, "detail").then(function (r) {
      if (!r.current) { return; }
      clear(box);
      if (r.status === 404) { box.appendChild(el("p", "This job is no longer tracked. Refresh the history.", "notice")); return; }
      if (r.status !== 200 || !r.body) { box.appendChild(el("p", "Job details are unavailable (" + r.status + ").", "notice")); return; }
      var reserved = renderDetail(box, r.body, rowsById[jobId] || {});
      return request("/api/v2/jobs/" + encodeURIComponent(jobId) + "/retention", false, "detail").then(function (rr) {
        if (!rr.current) { return; }
        clear(reserved);
        if (rr.status === 200 && rr.body) { renderJobStorage(reserved, rr.body.details); }
        else { reserved.appendChild(el("p", "Reservations unavailable (" + rr.status + ").", "muted")); }
      });
    }).catch(function (e) { if (!quiet(e)) { clear(box); box.appendChild(el("p", "The service could not be reached.", "notice")); } });
  }

  function fact(list, name, value, hover) {
    list.appendChild(el("dt", name, null, hover));
    list.appendChild(el("dd", value, null, hover));
  }
  function section(parent, title) {
    var s = el("div", null, "panel");
    s.appendChild(el("h3", title));
    parent.appendChild(s);
    return s;
  }

  function renderDetail(box, job, row) {
    var d = job.details;
    var mode = row.transfer_mode || (d.source_cleanup_enabled ? "Move" : "Copy");
    var grid = el("div", null, "detail-grid");
    box.appendChild(grid);

    var facts = el("dl", null, "facts");
    var steps = ["Received", job.source_paths_released ? "Acquired" : null, job.state === "Committed" ? finalStep(mode) : null]
      .filter(Boolean).join(" › ");
    fact(facts, "Progress", steps, "state: " + job.state);
    fact(facts, "Current activity", ACTIVITY[d.condition] || d.condition, "condition: " + d.condition);
    var id = identityLabel(d);
    fact(facts, id[0], id[1], d.recording_id !== undefined ? "recording_id" : "submission_id");
    if (row.source_folder !== undefined) {
      fact(facts, "Source folder", row.source_folder + "/", "Relative to the configured source root (see Settings)");
      fact(facts, "Destination folder", row.destination_folder + "/", "Relative to the configured destination root (see Settings)");
    }
    fact(facts, "Transfer mode", mode, mode === "Move" ? "Source files are removed after delivery" : "Source files are kept after delivery");
    fact(facts, "Source files", job.source_paths_released ? "Taken over by the mover" : "Sender must keep them",
      "source_paths_released: " + job.source_paths_released);
    fact(facts, "Sender", d.generator_id, "generator_id: the system that submitted this job");
    fact(facts, "Delivery record", d.manifest_phase === null ? "Not started" : "Step " + d.manifest_phase + " of 4",
      "manifest_phase: " + (d.manifest_phase === null ? "null" : d.manifest_phase));
    fact(facts, "Delivery reviews", String(d.review_epoch), "review_epoch: count of recorded delivery-retry reviews");
    fact(facts, "Missing-file reviews", String(d.missing_review_epoch), "missing_review_epoch");
    fact(facts, "Automatic source cleanup", d.source_cleanup_enabled ? "On" : "Off", "source_cleanup_enabled");
    section(grid, "Job").appendChild(facts);

    var activity = section(grid, "Activity");
    var quietJob = true;
    if (d.delivery_retry) {
      quietJob = false;
      activity.appendChild(el("p", d.delivery_retry.failures.toString() + " delivery failure(s); next attempt after " +
        time(d.delivery_retry.retry_after), "notice", "code: " + d.delivery_retry.code));
    }
    d.missing.forEach(function (m) {
      quietJob = false;
      activity.appendChild(el("p", "File " + m.file_id + " missing at the source; deadline " + time(m.deadline) +
        (m.blocked ? " (blocked)" : "") + (m.deadline_elapsed ? " (deadline passed)" : ""), "notice"));
    });
    if (d.latest_resume) {
      quietJob = false;
      activity.appendChild(el("p", "Delivery resumed " + time(d.latest_resume.recorded_at) + " by " + d.latest_resume.actor +
        ": " + d.latest_resume.reason, null, "latest_resume"));
    }
    if (d.latest_missing_reset) {
      quietJob = false;
      activity.appendChild(el("p", "Missing-file deadline reset " + time(d.latest_missing_reset.recorded_at) + " by " +
        d.latest_missing_reset.actor + ": " + d.latest_missing_reset.reason, null, "latest_missing_reset"));
    }
    if (quietJob) { activity.appendChild(el("p", "No problems recorded.", "muted")); }

    var reserved = section(grid, "Storage reserved");
    var placeholder = el("div");
    placeholder.appendChild(el("p", "Loading…", "muted"));
    reserved.appendChild(placeholder);

    var delivered = 0, known = 0n, unknown = 0;
    d.files.forEach(function (f) {
      if (f.phase === "Published" || f.phase === "SourceRemoved") { delivered++; }
      if (f.size_bytes === null) { unknown++; } else { known += BigInt(f.size_bytes); }
    });
    var files = el("div", null, "panel wide");
    files.appendChild(el("h3", "Files · " + delivered + " of " + d.files.length + " delivered · " +
      (unknown ? short(known) + " + " + unknown + " unmeasured" : short(known))));
    var table = el("table");
    var head = el("tr");
    [["File", "Path relative to the job's source folder"], ["Status", "Where this file is in the transfer"],
     ["Size", "Measured size; hover a value for exact bytes"], ["Attempts", "Copy attempts to the destination"]]
      .forEach(function (h) { head.appendChild(el("th", h[0], null, h[1])); });
    var thead = el("thead"); thead.appendChild(head); table.appendChild(thead);
    var tbody = el("tbody");
    d.files.forEach(function (f) {
      var tr = el("tr");
      tr.appendChild(el("td", f.name, "mono"));
      tr.appendChild(el("td", FILE_STATUS[f.phase] || f.phase, null,
        "phase: " + f.phase + "; transfer: " + (f.transfer_phase === null ? "none" : f.transfer_phase)));
      tr.appendChild(el("td", f.size_bytes === null ? "Not measured" : short(f.size_bytes), null,
        f.size_bytes === null ? "Size unknown; not counted as zero" : f.size_bytes.toString() + " bytes"));
      tr.appendChild(el("td", f.attempt === null ? "—" : f.attempt.toString()));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    var scroll = el("div", null, "scroll"); scroll.appendChild(table); files.appendChild(scroll);
    box.appendChild(files);
    return placeholder;
  }

  function renderJobStorage(target, d) {
    var facts = el("dl", null, "facts");
    fact(facts, "At source", short(d.source_reserved_bytes), BigInt(d.source_reserved_bytes).toString() + " bytes; source_reserved_bytes");
    fact(facts, "At destination", short(d.destination_reserved_bytes), BigInt(d.destination_reserved_bytes).toString() + " bytes; destination_reserved_bytes");
    fact(facts, "Files with unknown size", d.unmeasured_files.toString(), "unmeasured_files");
    var a = d.destination_attempts_by_phase;
    fact(facts, "Destination attempts", "Started " + a.Intent + " · Copied " + a.Copied + " · Verified " + a.Verified +
      " · Publishing " + a.PublishIntent + " · Delivered " + a.Published, "destination_attempts_by_phase");
    target.appendChild(facts);
  }

  // ---- Storage ----
  function stat(parent, name, value, note, hover) {
    var box = el("div", null, "stat", hover);
    box.appendChild(el("small", name));
    box.appendChild(el("strong", value));
    if (note) { box.appendChild(el("small", note)); }
    parent.appendChild(box);
    return box;
  }
  function meter(box, used, limit) {
    var u = BigInt(used), l = BigInt(limit);
    var p = el("progress");
    p.max = 1000;
    p.value = l === 0n ? 1000 : Number(u * 1000n / l > 1000n ? 1000n : u * 1000n / l);
    box.appendChild(p);
    if (u > l) { box.appendChild(el("small", "Over the configured limit", "over")); }
  }
  function loadStorage(deliberate) {
    $("storage-status").textContent = "Loading…";
    return request("/api/v2/retention", deliberate, "storage").then(function (r) {
      if (!r.current) { return; }
      if (r.status !== 200 || !r.body) { $("storage-status").textContent = "Storage is unavailable (" + r.status + "). Try Refresh."; return; }
      $("storage-status").textContent = "";
      renderStorage(r.body.details);
    }).catch(function (e) { if (!quiet(e)) { $("storage-status").textContent = "The service could not be reached."; } });
  }
  function renderStorage(d) {
    var target = $("storage-body");
    clear(target);
    var limits = d.configured_limits;
    var grid = el("div", null, "stats");
    var src = stat(grid, "Reserved at source", short(d.source_reserved_bytes), BigInt(d.source_reserved_bytes).toString() + " bytes",
      "Space the mover has reserved for files it holds at the source");
    var dst = stat(grid, "Reserved at destination", short(d.destination_reserved_bytes), BigInt(d.destination_reserved_bytes).toString() + " bytes",
      "Space reserved at the destination, including every kept delivery attempt");
    var jobs = stat(grid, "Jobs kept", d.retained_jobs.toString(), d.committed_jobs.toString() + " delivered",
      "Jobs the mover still tracks; history is kept until explicitly cleared");
    if (limits) {
      meter(src, d.source_reserved_bytes, limits.max_reserved_bytes);
      meter(dst, d.destination_reserved_bytes, limits.max_reserved_bytes);
      meter(jobs, d.retained_jobs, limits.max_retained_jobs);
    }
    stat(grid, "Files with unknown size", d.unmeasured_files.toString(), "Not counted as zero",
      "Files whose size has not been measured yet");
    target.appendChild(grid);

    var facts = el("dl", null, "facts");
    fact(facts, "Configured limits", limits
      ? limits.max_retained_jobs.toString() + " jobs · " + bytes(limits.max_reserved_bytes) + " per side" : "No limits configured",
      "configured_limits");
    var h = d.global_headroom;
    fact(facts, "Room left before limits", h
      ? h.new_job_slots.toString() + " more jobs · source " + bytes(h.source_bytes) + " · destination " + bytes(h.destination_bytes) +
        (h.over_limit ? " · OVER LIMIT" : "")
      : "Not applicable without limits", "global_headroom");
    fact(facts, "Files acquired", d.confirmed_claims.toString() + " confirmed of " + d.source_claims.toString() + " recorded",
      "confirmed_claims / source_claims: per-file acquisitions the mover recorded and confirmed");
    var a = d.destination_attempts_by_phase;
    fact(facts, "Destination attempts", "Started " + a.Intent + " · Copied " + a.Copied + " · Verified " + a.Verified +
      " · Publishing " + a.PublishIntent + " · Delivered " + a.Published, "destination_attempts_by_phase");
    fact(facts, "Automatic space reclamation", d.automatic_reclamation_enabled ? "On" : "Off", "automatic_reclamation_enabled");
    var s = d.source_space_admission;
    if (s) {
      fact(facts, "Source free-space check", s.policy.enabled ? s.state : "Disabled", "source_space_admission.state");
      if (s.policy.enabled) {
        fact(facts, "Last free-space reading", "Available " + bytes(s.observed_available_bytes) + " · required " + bytes(s.required_available_bytes) +
          (s.sample_age_ms === null ? "" : " · " + s.sample_age_ms.toString() + " ms old") + (s.reason ? " · " + s.reason : ""),
          "Cached observation; this page does not start a disk check");
      }
    }
    target.appendChild(facts);
    target.appendChild(el("p", "Totals of space the mover has reserved, not physical free disk space.", "muted small"));
  }

  // ---- Settings ----
  function loadSettings(deliberate) {
    $("settings-status").textContent = "Loading…";
    return request("/api/v2/admin/settings", deliberate, "settings").then(function (r) {
      if (!r.current) { return; }
      if (r.status !== 200 || !r.body) { $("settings-status").textContent = "Settings are unavailable (" + r.status + ")."; return; }
      $("settings-status").textContent = "";
      renderSettings(r.body);
    }).catch(function (e) { if (!quiet(e)) { $("settings-status").textContent = "The service could not be reached."; } });
  }
  function card(parent, title) {
    var c = el("section", null, "card");
    c.appendChild(el("h2", title));
    var dl = el("dl", null, "facts");
    c.appendChild(dl);
    parent.appendChild(c);
    return dl;
  }
  function yesNo(v) { return v ? "Yes" : "No"; }
  function certRows(parent, certs) {
    var now = Date.now();
    certs.forEach(function (c) {
      var value = c.path;
      var dd = el("dd", null, null, c.subject ? "Subject: " + c.subject : null);
      dd.appendChild(el("span", value, "mono block"));
      if (c.not_after) {
        var expires = Date.parse(c.not_after);
        var days = Math.floor((expires - now) / 86400000);
        var text = (c.subject ? c.subject + " · " : "") + "expires " + c.not_after.slice(0, 10);
        var cls = days < 0 ? "badge red" : days < 30 ? "badge amber" : "muted small";
        if (days < 0) { text += " (EXPIRED)"; } else if (days < 30) { text += " (in " + days + " days)"; }
        dd.appendChild(el("span", text, cls));
      }
      parent.appendChild(el("dt", c.role));
      parent.appendChild(dd);
    });
  }
  function renderSettings(s) {
    var target = $("settings-body");
    clear(target);
    var loaded = new Date(Number(s.loaded_at) * 1000).toISOString().replace("T", " ").replace(".000Z", " UTC");
    target.appendChild(el("p", "Loaded " + (s.config_file ? "from " + s.config_file + " " : "") + "at " + loaded +
      ". Changes take effect after a restart (producer certificates can be reloaded live).", "muted"));
    var grid = el("div", null, "settings-grid");
    target.appendChild(grid);
    var t = s.transfers;
    var dl = card(grid, "Transfers");
    fact(dl, "Source root", t.source_root, "source_root");
    fact(dl, "Destination root", t.destination_root, "destination_root");
    fact(dl, "Sender (generator ID)", t.generator_id, "generator_id");
    fact(dl, "Transfer mode", t.transfer_mode, "Copy keeps source files after delivery");
    fact(dl, "Check expected sizes", yesNo(t.check_expected_sizes), "check_expected_sizes");
    fact(dl, "Missing-file retry window", t.missing_file_retry_window_seconds.toString() + " s", "missing_file_retry_window_seconds");
    fact(dl, "Shutdown wait", t.shutdown_wait_seconds.toString() + " s", "shutdown_wait_seconds");
    var st = s.storage;
    dl = card(grid, "Storage limits");
    fact(dl, "Maximum jobs kept", st.max_retained_jobs.toString(), "max_retained_jobs");
    fact(dl, "Maximum reserved bytes", bytes(st.max_retained_bytes), "max_retained_bytes, per side");
    var sp = st.source_space_admission;
    fact(dl, "Source free-space check", sp.enabled ? "On" : "Off", "source_space_admission.enabled");
    if (sp.enabled) {
      fact(dl, "Minimum free space", bytes(sp.min_available_bytes) + " or " + sp.min_available_percent + "%", "min_available_bytes / min_available_percent");
    }
    if (s.producer) {
      var p = s.producer;
      dl = card(grid, "Producer connection");
      fact(dl, "Transport", p.transport, "native_ingress.transport");
      fact(dl, "Listening on", p.bind, "bind");
      if (p.authority) { fact(dl, "Authority", p.authority, "native_ingress.authority"); }
      fact(dl, "Operator socket", p.operator_socket, "native_ingress.operator_socket");
      fact(dl, "Approved senders", p.approved_clients.length ? "" : "None (HTTP mode)", "Client certificate fingerprints allowed to submit");
      p.approved_clients.forEach(function (c) {
        dl.appendChild(el("dt", c.generator_id, null, "generator_id"));
        dl.appendChild(el("dd", c.sha256, "mono", "SHA-256 fingerprint of the approved client certificate"));
      });
    }
    var db = s.dashboard;
    dl = card(grid, "Dashboard");
    fact(dl, "Listening on", db.bind, "admin_ingress.bind");
    fact(dl, "Address", location.protocol + "//" + db.authority + "/", "admin_ingress.authority");
    fact(dl, "Sign out after inactivity", Math.round(Number(db.inactivity_timeout_seconds) / 60) + " minutes", "inactivity_timeout_seconds");
    fact(dl, "Account directory", db.account_directory, "admin_ingress.account_directory");
    dl = card(grid, "Certificates and keys");
    if (s.producer && s.producer.certificates.length) {
      dl.appendChild(el("dt", "Producer", "group"));
      dl.appendChild(el("dd", ""));
      certRows(dl, s.producer.certificates);
    }
    dl.appendChild(el("dt", "Dashboard", "group"));
    dl.appendChild(el("dd", ""));
    certRows(dl, db.certificates);
    var i = s.internal;
    dl = card(grid, "Internal");
    fact(dl, "State database", i.state_database, "state_database");
    fact(dl, "Source binding", i.source_binding.root_id + " · " + i.source_binding.filesystem, "source_binding");
    fact(dl, "Destination binding", i.destination_binding.root_id + " · " + i.destination_binding.filesystem, "destination_binding");
    fact(dl, "Protected ingress", i.protected_ingress ? "Configured" : "Not used", "protected_ingress");
  }

  // ---- Session ----
  function show(signedIn) {
    $("signin").hidden = signedIn;
    $("shell").hidden = !signedIn;
    if (!signedIn) {
      Object.keys(ctl).forEach(function (k) { if (ctl[k]) { ctl[k].abort(); } gen[k]++; });
      csrf = null; cursors = [null]; page = 0; openJob = null; descending = false;
      setView("history");
      $("password").value = "";
      $("username").focus();
    }
  }
  function loadSession() {
    return fetch("/api/v2/admin/session", { credentials: "same-origin", cache: "no-store" }).then(function (r) {
      if (r.status !== 200) {
        show(false);
        return;
      }
      csrf = r.headers.get("Mover-CSRF-Token");
      show(true);
      return loadPage(false);
    }).catch(function () { show(false); $("signin-error").textContent = "The service could not be reached."; });
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
      if (r.status !== 200) { $("signin-error").textContent = messages[r.status] || "Sign-in failed. Try again."; return; }
      return fetch("/api/v2/admin/session", { credentials: "same-origin", cache: "no-store" }).then(function (s) {
        if (s.status !== 200) {
          // Login succeeded but the browser did not keep the session cookie.
          $("signin-error").textContent = "Signed in, but this browser did not keep the session. Check that cookies are allowed for this site.";
          return;
        }
        csrf = s.headers.get("Mover-CSRF-Token");
        show(true);
        return loadPage(false);
      });
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
    if (refreshing) { return; }
    refreshing = true;
    $("refresh").disabled = true;
    var done = function () { refreshing = false; $("refresh").disabled = false; };
    var work = view === "storage" ? loadStorage(true) : view === "settings" ? loadSettings(true) : loadPage(true);
    work.then(done, done);
  });
  $("sort").addEventListener("click", function () {
    descending = !descending;
    $("sort").textContent = descending ? "Job ▼" : "Job ▲";
    $("sort").title = descending ? "Newest first; click for oldest first" : "Oldest first; click for newest first";
    cursors = [null]; page = 0; openJob = null;
    loadPage(true);
  });
  $("prev").addEventListener("click", function () { if (page > 0) { page--; loadPage(true); } });
  $("next").addEventListener("click", function () { if (cursors[page + 1]) { page++; loadPage(true); } });
  $("tab-history").addEventListener("click", function () { setView("history"); });
  $("tab-storage").addEventListener("click", function () { setView("storage"); loadStorage(true); });
  $("tab-settings").addEventListener("click", function () { setView("settings"); loadSettings(true); });
  loadSession();
})();
