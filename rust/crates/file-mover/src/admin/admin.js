"use strict";
(function () {
  var csrf = null;
  var deletionEnabled = false;  // admin_ingress.allow_data_deletion, from the session
  function noteSession(response) {
    return response.text().then(function (text) {
      try { deletionEnabled = parseJSON(text).data_deletion_enabled === true; } catch (e) { deletionEnabled = false; }
    });
  }
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
    Retrying: ["Retrying delivery", "blue"], ReviewRequired: ["Needs review", "amber"],
    CancellationPending: ["Cancelling", "amber"], Cancelled: ["Cancelled", "grey"]
  };
  var ACTIVITY = {
    Committed: "Delivered", AwaitingClaims: "Waiting for the source files",
    Ready: "Ready to deliver", Retrying: "Retrying delivery", ReviewRequired: "Needs review",
    CancellationPending: "Cancelling: stopping work on this job",
    Cancelled: "Cancelled: no further work; files stay where they are"
  };
  var FILE_STATUS = {
    Pending: "Waiting", Claimed: "Acquired", Verified: "Verified",
    Published: "Delivered", SourceRemoved: "Delivered, source removed"
  };
  function identityLabel(item) {
    return item.recording_id !== undefined ? ["Request ID", item.recording_id] : ["Legacy submission", item.submission_id];
  }
  // Folders are relative to the roots recorded with each job when it was
  // accepted. Settings shows today's roots, which may differ for older jobs.
  var FOLDER_HINT = "Relative to the root recorded with this job. If the configured root has changed since, " +
    "this job's files are still under the earlier root, not the one shown in Settings.";
  function folder(value, side) { return value === "" ? "(" + side + " root)" : value + "/"; }
  function finalStep(mode) { return mode === "Move" ? "Moved" : "Copied"; }
  function progress(item, mode) {
    var wrap = el("span", null, "steps");
    var done = [true, item.source_paths_released, item.state === "Committed"];
    var labels = ["Received", "Acquired", finalStep(mode)];
    var tips = ["The mover accepted the request", "The mover has taken over the source files; the sender may let go",
      "All files are at the destination (" + (mode === "Move" ? "source removed" : "source kept") + ")"];
    labels.forEach(function (label, i) {
      // Each reached step is a colored pill; unreached steps are outlined grey.
      wrap.appendChild(el("span", label, "step step-" + i + (done[i] ? " done" : ""),
        (done[i] ? "" : "Not yet: ") + tips[i]));
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
  function loadPage(deliberate, live) {
    if (!live) {
      $("history-status").textContent = "Loading…";
      $("prev").disabled = true; $("next").disabled = true;
    }
    return request(pagePath(), deliberate, "page").then(function (r) {
      if (!r.current) { return false; }
      if (r.status !== 200 || !r.body) {
        $("history-status").textContent = "Job history is unavailable (" + r.status + "). Try Refresh.";
        $("prev").disabled = page === 0;
        return false;
      }
      return renderPage(r.body, live).then(function () { return true; });
    }).catch(function (e) {
      if (!quiet(e)) { $("history-status").textContent = "The service could not be reached."; }
      return false;
    });
  }
  function renderPage(body, live) {
    var rows = $("history-rows");
    // A live refresh keeps the open detail panel and refreshes it in place.
    var kept = live ? document.querySelector("tr.detail-row") : null;
    if (kept) { kept.remove(); }
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
      tr.appendChild(el("td", folder(item.source_folder, "source"), "mono", FOLDER_HINT));
      tr.appendChild(el("td", folder(item.destination_folder, "destination"), "mono", FOLDER_HINT));
      rows.appendChild(tr);
    });
    $("prev").disabled = page === 0;
    $("next").disabled = body.next_cursor === null;
    if (body.next_cursor !== null) { cursors[page + 1] = body.next_cursor; cursors.length = page + 2; }
    if (openJob && rowsById[openJob]) {
      var row = rows.querySelector('tr[data-job="' + CSS.escape(openJob) + '"]');
      if (row && kept) {
        row.after(kept);
        row.querySelector("button").setAttribute("aria-expanded", "true");
        return loadDetailInto(kept.querySelector(".detail"), openJob, false, true);
      } else if (row) {
        return insertDetail(openJob, row, row.querySelector("button"), false);
      }
    } else {
      openJob = null;
    }
    return Promise.resolve();
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
    return loadDetailInto(box, jobId, deliberate, false);
  }

  // Sequential reads: detail, then this job's reservations. With keep=true the
  // current content stays until the new detail arrives (live refresh).
  function loadDetailInto(box, jobId, deliberate, keep) {
    return request("/api/v2/jobs/" + encodeURIComponent(jobId), deliberate, "detail").then(function (r) {
      if (!r.current) { return; }
      var fresh = el("div");
      if (r.status === 404) {
        fresh.appendChild(el("p", "This job is no longer tracked. Refresh the history.", "notice"));
        box.replaceChildren.apply(box, Array.prototype.slice.call(fresh.childNodes));
        return;
      }
      if (r.status !== 200 || !r.body) {
        if (keep) { return; }
        fresh.appendChild(el("p", "Job details are unavailable (" + r.status + ").", "notice"));
        box.replaceChildren.apply(box, Array.prototype.slice.call(fresh.childNodes));
        return;
      }
      var reserved = renderDetail(fresh, r.body, rowsById[jobId] || {});
      box.replaceChildren.apply(box, Array.prototype.slice.call(fresh.childNodes));
      return request("/api/v2/jobs/" + encodeURIComponent(jobId) + "/retention", false, "detail").then(function (rr) {
        if (!rr.current) { return; }
        clear(reserved);
        if (rr.status === 200 && rr.body) { renderJobStorage(reserved, rr.body.details); }
        else { reserved.appendChild(el("p", "Reservations unavailable (" + rr.status + ").", "muted")); }
      });
    }).catch(function (e) {
      if (!quiet(e) && !keep) { clear(box); box.appendChild(el("p", "The service could not be reached.", "notice")); }
    });
  }

  // Plain-language view of the job's last recorded problem (last_problem).
  // The service records only a bounded, path-free diagnostic; folder names come
  // from the job itself.
  var ERRNO = {
    1: ["Operation not permitted", "access"], 2: ["Not found", "missing"], 5: ["Storage I/O error", "io"],
    13: ["Permission denied", "access"], 16: ["Busy", "busy"], 17: ["Something is already there", "exists"],
    18: ["Crosses file systems", "layout"], 20: ["Not a folder", "layout"], 21: ["Is a folder", "layout"],
    28: ["No space left", "space"], 30: ["Read-only storage", "readonly"], 36: ["Name too long", "layout"],
    39: ["Folder not empty", "exists"], 40: ["Link refused", "layout"], 95: ["Not supported by this storage", "layout"],
    110: ["Storage timed out", "io"], 116: ["Stale network file handle", "io"], 122: ["Storage quota exceeded", "space"]
  };
  var STEPS = [
    ["payload_source_read", "reading the source file", "source"],
    ["relocate.", "taking over the source file", "source"],
    ["payload_copy_write", "writing the copy", "destination"],
    ["payload_verification_read", "verifying the copy", "destination"],
    ["staging_", "creating the staging folder", "destination"],
    ["payload_publication", "publishing the delivered file", "destination"],
    ["payload_copy", "saving the copy to disk", "destination"],
    ["enrollment_", "recording the source folder's identity", "source"]
  ];
  var SPECIAL = {
    destination_binding_refused: ["Destination changed", "The destination folder no longer matches the one this job was set up with (for example a different mount). Check the destination mount."],
    blocked_or_uncertain: ["Result could not be confirmed", "A step stopped without a confirmed result. Check the service log, fix the cause, then retry."],
    missing_source: ["Source file missing", "A source file is not where the sender said it would be."],
    expected_size_mismatch: ["Size differs", "A source file's size differs from what the sender declared."],
    worker_outcome_uncertain: ["Result could not be confirmed", "A worker stopped without a confirmed result. Check the service log, then retry."],
    store_error: ["State database problem", "The mover could not update its state database. Check the service log."]
  };
  function describeProblem(p, folders) {
    var step = null;
    STEPS.forEach(function (s) { if (!step && p.operation.indexOf(s[0]) === 0) { step = s; } });
    var side = step ? step[2] : (p.stage === "claim" ? "source" : "destination");
    var place = side === "source" ? folders.source : folders.destination;
    var where = side + " folder" + (place ? " " + place : "");
    var errno = p.errno !== null && p.errno !== undefined ? Number(p.errno) : null;
    var known = errno !== null ? ERRNO[errno] : null;
    var special = SPECIAL[p.operation];
    var title, advice;
    if (special) {
      title = special[0]; advice = special[1];
    } else if (p.operation.indexOf("blocked: ") === 0) {
      title = "Stopped for safety"; advice = "The mover refused to continue: " + p.operation.slice(9) + ".";
    } else if (known) {
      title = known[0];
      advice = {
        access: "Give the mover's service account permission in the " + where + ", then retry.",
        missing: "Something the mover expected in the " + where + " is missing. Check that it is mounted and intact.",
        io: "The " + side + " storage reported an error. Check the disk or network storage, then retry.",
        busy: "The " + where + " is in use by something else. Try again shortly.",
        // A collision says nothing about ownership: never suggest moving mover-owned data.
        exists: "Something is already in the " + where + " where the mover needs to write. Find out what it is first: " +
          "if it is the mover's own (an earlier delivery or retained copy), leave it in place and check the job history. " +
          "Only move an item you know is not the mover's, then retry.",
        layout: "The " + where + " has an unexpected layout for this step. Check it, then retry.",
        space: "The " + side + " storage is full. Free space, then retry.",
        readonly: "The " + side + " storage is read-only. Make it writable, then retry."
      }[known[1]];
    } else {
      title = errno !== null ? "System error " + errno : "Problem";
      advice = "Check the service log for details.";
    }
    var during = step ? step[1] : (p.stage === "claim" ? "taking over the source files" : "delivering to the destination");
    return { title: title, during: during, advice: advice, side: side };
  }
  function problemPanel(job, d, row) {
    var p = d.last_problem;
    var names = {};
    d.files.forEach(function (f) { names[f.file_id] = f.name; });
    var info = describeProblem(p, { source: row.source_folder, destination: row.destination_folder });
    var resolved = job.state === "Committed";
    var box = el("div", null, resolved ? "problem resolved" : "problem");
    box.appendChild(el("strong", (resolved ? "Earlier problem (resolved): " : "Problem: ") + info.title));
    box.appendChild(el("p", "While " + info.during + (p.file_id !== null && names[p.file_id] !== undefined ? " · file " + names[p.file_id] : "") +
      " · " + time(p.recorded_at), "muted"));
    if (!resolved) { box.appendChild(el("p", info.advice)); }
    box.appendChild(el("p", p.diagnostic, "mono muted", "Technical detail recorded by the service (last_problem.diagnostic)"));
    return box;
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
      fact(facts, "Source folder", folder(row.source_folder, "source"), FOLDER_HINT);
      fact(facts, "Destination folder", folder(row.destination_folder, "destination"), FOLDER_HINT);
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
    if (d.last_problem) {
      quietJob = false;
      activity.appendChild(problemPanel(job, d, row));
    }
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
    // A frozen, unreconciled retry stays resendable whatever the job's current state.
    var retry = retryState[job.job_id];
    if (retry && retry.frozen) {
      quietJob = false;
      activity.appendChild(retryForm(job.job_id));
    } else if (retryEligible(d, row.retry_review, job.job_id)) {
      quietJob = false;
      retryState[job.job_id] = retry = retry || {};
      retry.review = row.retry_review;
      activity.appendChild(retryForm(job.job_id));
    } else if (retry && retry.message) {
      activity.appendChild(el("p", retry.message, "muted"));
    }
    var cancellation = d.cancellation || { state: "NotRequested" };
    if (cancellation.state === "Pending") {
      quietJob = false;
      activity.appendChild(el("p", "Cancellation requested " + time(cancellation.requested_at) +
        ". The mover is stopping work on this job.", "notice", "cancellation.state: Pending"));
    } else if (cancellation.state === "Cancelled") {
      quietJob = false;
      activity.appendChild(el("p", "Cancelled " + time(cancellation.stopped_at) +
        ". No further work. Files already taken over stay where they are (see Storage).", "notice", "cancellation.state: Cancelled"));
    }
    var cst = actionState["cancel:" + job.job_id];
    if (actionPending("cancel", job.job_id) ||
        (job.state !== "Committed" && cancellation.state === "NotRequested")) {
      activity.appendChild(actionForm("cancel", job.job_id, job));
    } else if (cst && cst.message) {
      activity.appendChild(el("p", cst.message, "muted"));
    }
    if (d.deletion) {
      quietJob = false;
      activity.appendChild(el("p", deleteOutcome(d.deletion), d.deletion.completion_pending ? "notice" : "muted",
        "deletion: latest pass"));
    }
    var stopped = job.state === "Committed" || cancellation.state === "Cancelled";
    if (actionPending("delete-data", job.job_id) ||
        (deletionEnabled && stopped && !(d.deletion && d.deletion.completion_pending))) {
      quietJob = false;
      activity.appendChild(actionForm("delete-data", job.job_id, job));
    }
    // Delivered jobs and completed cancellations can be removed from history.
    if (actionPending("clear-history", job.job_id) ||
        job.state === "Committed" || cancellation.state === "Cancelled") {
      quietJob = false;
      activity.appendChild(actionForm("clear-history", job.job_id, job));
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

  // Reviewed delivery retry. The context (instance, exact job ID, review epoch
  // and reason) is frozen when Retry is first clicked. Until a readable final
  // reply reconciles it, the identical request stays resendable, so a lost
  // reply is answered by the service's stored outcome instead of a second retry.
  var retryState = {};   // job ID -> {review, draft, frozen, sending, message}
  var liveDeferred = false;
  var CONTROL = /[\u0000-\u001f\u007f-\u009f]/;
  var LONE = /[\ud800-\udbff](?![\udc00-\udfff])|(?:^|[^\ud800-\udbff])[\udc00-\udfff]/;
  function base64url(bytes) {
    var bin = "";
    bytes.forEach(function (b) { bin += String.fromCharCode(b); });
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function hex(buffer) {
    return Array.prototype.map.call(new Uint8Array(buffer), function (b) { return b.toString(16).padStart(2, "0"); }).join("");
  }
  function freezeRetry(review, reason) {
    var prefix = new TextEncoder().encode("BFM-RETRY-SELECTION\u0000v1\u0000");
    var frame = new Uint8Array(prefix.length + 10);
    frame.set(prefix);
    var data = new DataView(frame.buffer);
    data.setUint16(prefix.length, 1);
    data.setBigInt64(prefix.length + 2, BigInt(review.job_id));
    return crypto.subtle.digest("SHA-256", frame).then(function (digest) {
      // Canonical form: fixed key order; only quote and backslash are escaped.
      var escaped = reason.replace(/["\\]/g, function (c) { return "\\" + c; });
      var payload = '{"version":1,"instance_id":"' + review.instance_id + '","selection_sha256":"' + hex(digest) +
        '","review_epochs":[' + review.review_epoch + '],"reason":"' + escaped + '"}';
      return { header: "v1." + base64url(new TextEncoder().encode(payload)), body: '{"job_ids":[' + review.job_id + "]}", reason: reason };
    });
  }
  function retryProblem(reason) {
    if (!reason.trim()) { return "Explain what you checked before retrying."; }
    if (CONTROL.test(reason) || LONE.test(reason)) { return "Use a single line of plain text."; }
    if (new TextEncoder().encode(reason).length > 512) { return "Keep the explanation under 512 bytes."; }
    return null;
  }
  // Integers arrive from the lossless parser as BigInt.
  function retryEligible(d, review, jobId) {
    return d.condition === "ReviewRequired" && !!d.delivery_retry && String(d.delivery_retry.failures) === "3" &&
      !!review && review.review_epoch !== null && review.job_id === jobId;
  }
  function retryOutcome(counts) {
    if (String(counts.accepted_count) !== "0") { return "Retry scheduled. Delivery will be attempted again shortly."; }
    if (String(counts.failed_count) !== "0") { return "Not retried: the job changed after you reviewed it. Check the details and try again."; }
    return "Nothing to retry: the job already finished or is no longer tracked.";
  }
  function redrawRetry(jobId) {
    var old = document.getElementById("retry-" + jobId);
    if (old) { old.replaceWith(retryForm(jobId)); }
  }
  function sendRetry(jobId) {
    var st = retryState[jobId];
    if (st.sending) { return; }
    var problem = st.frozen ? null : retryProblem(st.draft || "");
    if (problem) { st.message = problem; redrawRetry(jobId); return; }
    st.sending = true;
    st.message = "Sending…";
    var ready = st.frozen ? Promise.resolve(st.frozen) : freezeRetry(st.review, st.draft).then(function (f) {
      st.frozen = f;
      return f;
    });
    redrawRetry(jobId);
    function uncertain(text) {
      st.sending = false;
      st.message = text;
      redrawRetry(jobId);
    }
    ready.then(function (f) {
      return fetch("/api/v2/admin/jobs/retry", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json", "Mover-CSRF-Token": csrf || "", "Mover-Retry-Context": f.header },
        body: f.body
      });
    }).then(function (r) {
      return r.text().then(function (text) {
        var body = null;
        try { body = text ? parseJSON(text) : null; } catch (e) { body = null; }
        return { status: r.status, body: body };
      });
    }).then(function (r) {
      if (r.status === 401) { delete retryState[jobId]; show(false); return; }
      if (r.status === 503) { uncertain("The service is busy. Click again to resend the same request."); return; }
      if (r.status === 202 && !(r.body && r.body.accepted_count !== undefined)) {
        uncertain("The reply could not be read. Click again to resend the same request.");
        return;
      }
      // Final answer: the frozen request is reconciled.
      st.frozen = null;
      st.sending = false;
      st.draft = "";
      if (r.status === 202) {
        st.message = retryOutcome(r.body);
      } else if (r.status === 409) {
        st.message = "This page belongs to a different mover installation. Reload the page.";
      } else if (r.status === 403) {
        st.message = "The session security check failed. Reload the page and try again.";
      } else {
        st.message = "The retry was refused (" + ((r.body && r.body.error) || r.status) + "). Reload and review again.";
      }
      redrawRetry(jobId);
      resumeLive(true);
    }).catch(function () {
      uncertain("No reply from the service. Click again to resend the same request.");
    });
  }
  function retryForm(jobId) {
    var st = retryState[jobId];
    var box = el("div", null, "retry");
    box.id = "retry-" + jobId;
    box.appendChild(el("p", st.frozen
      ? "A retry request is waiting for a confirmed reply. Resending it cannot retry twice."
      : "Delivery stopped after 3 failed attempts. Fix the cause (for example destination space or permissions), then retry."));
    var label = el("label", "What did you check or fix? (required, kept in the audit record)");
    label.htmlFor = "retry-reason-" + jobId;
    var input = el("textarea");
    input.id = label.htmlFor;
    input.rows = 2;
    input.value = st.frozen ? st.frozen.reason : (st.draft || "");
    input.disabled = !!st.frozen || !!st.sending;
    var button = el("button", st.sending ? "Sending…" : st.frozen ? "Send retry again" : "Retry delivery", "secondary",
      st.frozen ? "Resends the identical request" : "Schedules one more delivery attempt for this job");
    button.type = "button";
    button.disabled = !!st.sending;
    var status = el("p", st.message || "", "error");
    status.setAttribute("role", "status");
    input.addEventListener("input", function () { st.draft = input.value; });
    input.addEventListener("blur", function () { if (!input.value.trim()) { resumeLive(false); } });
    button.addEventListener("click", function () { sendRetry(jobId); });
    box.appendChild(label);
    box.appendChild(input);
    box.appendChild(button);
    box.appendChild(status);
    return box;
  }
  // Live refresh re-renders the page; do not pull the field away mid-typing.
  function retryInUse() {
    var input = document.querySelector(".retry textarea");
    return !!input && !input.disabled && (document.activeElement === input || input.value.trim() !== "");
  }
  function resumeLive(force) {
    if (liveDeferred || force) { liveDeferred = false; refreshVisible(); }
  }

  // Confirmed actions (cancel, clear history): a confirmation preview first (a
  // short-lived service proof bound to this account, session and exact job),
  // then the action with that proof. After a lost reply the identical request
  // may be resent until the proof expires; a repeat cannot act twice.
  var actionState = {};  // "<action>:<job ID>" -> {proof, expires_at, sending, message}
  function cancelOutcome(counts) {
    if (String(counts.accepted_count) !== "0") { return "Cancelling: the mover is stopping work on this job."; }
    if (String(counts.failed_count) !== "0") { return "A cancellation is already in progress for this job."; }
    return "Nothing to cancel: the job is already delivered, cancelled or no longer tracked.";
  }
  function deleteOutcome(body) {
    if (body.completion_pending === true) { return "Deleting retained copies…"; }
    if (String(body.deleted_count) === "0" && String(body.failed_count) === "0") { return "Nothing was deleted: no retained copies remain."; }
    return "Retained copies: " + body.deleted_count + " deleted" +
      (String(body.failed_count) !== "0" ? ", " + body.failed_count + " could not be deleted (see the service log)" : "") + ".";
  }
  function clearOutcome(body) {
    return String(body.cleared_count) !== "0" ? "Removed from history."
      : "Nothing was removed: the job is still in progress, already removed, or busy. Try again shortly.";
  }
  var ACTIONS = {
    cancel: {
      route: "/api/v2/admin/jobs/cancel", ask: "Cancel job…", confirm: "Cancel job", keep: "Keep job",
      hover: "Stop all work on this job. You will be asked to confirm.",
      question: function (jobId) {
        return "Cancel job #" + jobId + "? The mover stops working on it and will not deliver it. " +
          "Files it already took over, and any partly delivered files, stay where they are (see Storage). " +
          "This cannot be undone.";
      },
      done: function (b) { return b && b.accepted_count !== undefined; }, outcome: cancelOutcome
    },
    "delete-data": {
      route: "/api/v2/admin/jobs/delete-data", ask: "Delete retained data…", confirm: "Delete files", keep: "Keep files",
      hover: "Permanently delete the copies the mover keeps for this job. You will be asked to confirm.",
      question: function (jobId, job, st) {
        var targets = (st && st.targets) || [];
        if (!targets.length) { return "Nothing to delete: the mover holds no retained copies for job #" + jobId + "."; }
        var total = 0n;
        targets.forEach(function (t) { total += BigInt(t.size_bytes); });
        var names = targets.slice(0, 5).map(function (t) { return t.relative_path; }).join(", ") +
          (targets.length > 5 ? " and " + (targets.length - 5) + " more" : "");
        return "Permanently delete the mover's retained copies for job #" + jobId + "? " + targets.length +
          " file(s), " + bytes(total) + ": " + names + ". " + (job.state === "Committed"
            ? "The delivered files at the destination are not touched."
            : "WARNING: this job was never delivered. These are the only copies of the recording and will be permanently destroyed.") +
          " This cannot be undone.";
      },
      blocked: function (st) { return !st || !st.targets || !st.targets.length; },
      done: function (b) { return b && b.completion_pending !== undefined; }, outcome: deleteOutcome
    },
    "clear-history": {
      route: "/api/v2/admin/jobs/clear-history", ask: "Clear from history…", confirm: "Clear from history", keep: "Keep in history",
      hover: "Forget this job's record. Files are not touched. You will be asked to confirm.",
      question: function (jobId, job) {
        return "Remove job #" + jobId + " from the history? The mover forgets this job completely: its record, " +
          "activity, storage accounting and its recording ID. If the sender submits the same recording again, " +
          "it is treated as a new recording. No files are touched, but they leave mover management: " +
          (job.state === "Committed"
            ? "delivered files stay at the destination, and the source files the mover took over stay where they are, untracked."
            : "files the mover took over stay where they are, untracked and no longer counted on the Storage page.") +
          " This cannot be undone.";
      },
      done: function (b) { return b && b.cleared_count !== undefined; }, outcome: clearOutcome
    }
  };
  function readReply(r) {
    return r.text().then(function (text) {
      var body = null;
      try { body = text ? parseJSON(text) : null; } catch (e) { body = null; }
      return { status: r.status, body: body };
    });
  }
  function redrawAction(action, jobId, job) {
    var old = document.getElementById(action + "-" + jobId);
    if (old) { old.replaceWith(actionForm(action, jobId, job)); }
  }
  function askAction(action, jobId, job) {
    var key = action + ":" + jobId;
    var st = actionState[key] = actionState[key] || {};
    st.sending = true; st.message = "Preparing confirmation…";
    redrawAction(action, jobId, job);
    fetch("/api/v2/admin/jobs?confirm_action=" + action + "&job_ids=" + encodeURIComponent(jobId), {
      credentials: "same-origin", cache: "no-store",
      headers: { "Mover-Admin-Activity": "interaction", "Mover-CSRF-Token": csrf || "" }
    }).then(readReply).then(function (r) {
      st.sending = false;
      if (r.status === 401) { delete actionState[key]; show(false); return; }
      var c = r.body && r.body.confirmation;
      if (r.status !== 200 || !c || c.action !== action) {
        st.message = "Could not prepare the confirmation (" + ((r.body && r.body.error) || r.status) + ").";
      } else {
        st.proof = c.token; st.expires_at = Number(c.expires_at); st.message = "";
        st.targets = c.deletion_targets || [];
      }
      redrawAction(action, jobId, job);
    }).catch(function () {
      st.sending = false; st.message = "The service could not be reached.";
      redrawAction(action, jobId, job);
    });
  }
  function sendAction(action, jobId, job) {
    var cfg = ACTIONS[action], st = actionState[action + ":" + jobId];
    if (!st || !st.proof || st.sending) { return; }
    if (Date.now() / 1000 >= st.expires_at) {
      st.proof = null; st.message = "The confirmation expired. Start again.";
      redrawAction(action, jobId, job); return;
    }
    st.sending = true; st.message = "Sending…";
    redrawAction(action, jobId, job);
    fetch(cfg.route, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "Mover-CSRF-Token": csrf || "", "Mover-Confirmation": st.proof },
      body: '{"job_ids":[' + jobId + "]}"
    }).then(readReply).then(function (r) {
      st.sending = false;
      if (r.status === 401) { delete actionState[action + ":" + jobId]; show(false); return; }
      var ok = r.status === 200 || r.status === 202;
      if (r.status === 503 || (ok && !cfg.done(r.body))) {
        st.message = "No confirmed reply. Click " + cfg.confirm + " again to resend the same request.";
        redrawAction(action, jobId, job); return;
      }
      st.proof = null;
      if (ok) {
        st.message = cfg.outcome(r.body);
      } else if (r.body && r.body.error === "invalid_confirmation") {
        st.message = "The confirmation expired or no longer matches. Start again.";
      } else if (r.body && r.body.error === "stale_confirmation") {
        st.message = "The files changed since you confirmed. Nothing was deleted. Start again.";
      } else {
        st.message = "The request was refused (" + ((r.body && r.body.error) || r.status) + ").";
      }
      redrawAction(action, jobId, job);
      refreshVisible();
    }).catch(function () {
      st.sending = false;
      st.message = "No reply from the service. Click " + cfg.confirm + " again to resend the same request.";
      redrawAction(action, jobId, job);
    });
  }
  function actionForm(action, jobId, job) {
    var cfg = ACTIONS[action], st = actionState[action + ":" + jobId] || {};
    var box = el("div", null, "cancel");
    box.id = action + "-" + jobId;
    if (st.proof) {
      box.appendChild(el("p", cfg.question(jobId, job, st), "notice"));
      var yes = el("button", st.sending ? "Sending…" : cfg.confirm, "secondary danger", "Confirm");
      yes.type = "button"; yes.disabled = !!st.sending || (!!cfg.blocked && cfg.blocked(st));
      yes.addEventListener("click", function () { sendAction(action, jobId, job); });
      var no = el("button", cfg.keep, "secondary", "Close without changing anything");
      no.type = "button"; no.disabled = !!st.sending;
      no.addEventListener("click", function () { st.proof = null; st.message = ""; redrawAction(action, jobId, job); });
      box.appendChild(yes); box.appendChild(document.createTextNode(" ")); box.appendChild(no);
    } else {
      var ask = el("button", st.sending ? "Preparing…" : cfg.ask, "secondary danger", cfg.hover);
      ask.type = "button"; ask.disabled = !!st.sending;
      ask.addEventListener("click", function () { askAction(action, jobId, job); });
      box.appendChild(ask);
    }
    var status = el("p", st.message || "", "error");
    status.setAttribute("role", "status");
    box.appendChild(status);
    return box;
  }
  function actionPending(action, jobId) {
    var st = actionState[action + ":" + jobId];
    return !!st && !!(st.proof || st.sending);
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
  function loadStorage(deliberate, live) {
    if (!live) { $("storage-status").textContent = "Loading…"; }
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
    fact(dl, "Delete retained data", db.allow_data_deletion ? "Allowed" : "Off (default)", "admin_ingress.allow_data_deletion");
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

  // ---- Live updates (Server-Sent Events; no polling) ----
  var events = null, liveRetry = null, liveBusy = false, livePending = false, liveConnected = false;
  function setLive(text, cls, hover) {
    var e = $("live");
    e.textContent = text;
    e.className = "live " + cls;
    e.title = hover;
  }
  function refreshVisible() {
    if (retryInUse()) { liveDeferred = true; return; }
    if (liveBusy) { livePending = true; return; }
    liveBusy = true;
    var work = view === "history" ? loadPage(false, true)
      : view === "storage" ? loadStorage(false, true) : Promise.resolve();
    var done = function () {
      liveBusy = false;
      if (livePending) { livePending = false; refreshVisible(); }
    };
    work.then(done, done);
  }
  function stopLive() {
    if (events) { events.close(); events = null; }
    if (liveRetry) { clearTimeout(liveRetry); liveRetry = null; }
    liveConnected = false;
  }
  function startLive() {
    stopLive();
    if (typeof EventSource === "undefined") {
      setLive("Live updates unavailable", "off", "This browser does not support live updates; use Refresh.");
      return;
    }
    setLive("Connecting…", "wait", "Connecting to live updates");
    events = new EventSource("/api/v2/admin/events");
    events.addEventListener("ready", function () {
      setLive("Live", "on", "This page updates automatically when jobs change.");
      // Any change between the last read and this subscription would otherwise
      // be lost: re-read what is visible on every (re)connect.
      liveConnected = true;
      refreshVisible();
    });
    events.addEventListener("changed", function () { refreshVisible(); });
    events.addEventListener("signed-out", function () { stopLive(); show(false); });
    events.onerror = function () {
      if (!events) { return; }
      if (events.readyState === EventSource.CONNECTING) {
        setLive("Reconnecting…", "wait", "Live updates paused; reconnecting");
        return;
      }
      // Closed for good: EventSource hides the status, so ask the session.
      stopLive();
      fetch("/api/v2/admin/session", { credentials: "same-origin", cache: "no-store" }).then(function (r) {
        if (r.status === 401) { show(false); return; }
        setLive("Live updates unavailable", "off", "Live updates are unavailable right now; use Refresh. Retrying in 30 seconds.");
        liveRetry = setTimeout(startLive, 30000);
      }).catch(function () {
        setLive("Live updates unavailable", "off", "The service could not be reached.");
        liveRetry = setTimeout(startLive, 30000);
      });
    };
  }

  // ---- Session ----
  function show(signedIn) {
    $("signin").hidden = signedIn;
    $("shell").hidden = !signedIn;
    if (signedIn) { if (!events) { startLive(); } } else { stopLive(); }
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
      return noteSession(r).then(function () { show(true); return loadPage(false); });
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
        return noteSession(s).then(function () { show(true); return loadPage(false); });
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
