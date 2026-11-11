"use strict";
(function () {
  var csrf = null;
  function $(id) { return document.getElementById(id); }
  function show(signedIn) {
    $("signin").hidden = signedIn;
    $("shell").hidden = !signedIn;
    if (!signedIn) { csrf = null; $("password").value = ""; $("username").focus(); }
  }
  function signedIn(response) {
    csrf = response.headers.get("Mover-CSRF-Token");
    return response.json().then(function (body) {
      var minutes = Math.round(body.inactivity_timeout_seconds / 60);
      $("idle").textContent = "This session ends after " + minutes + " minutes without activity.";
      $("shell-error").textContent = "";
      show(true);
      $("signout").focus();
    });
  }
  function loadSession() {
    return fetch("/api/v2/admin/session", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        if (r.status === 200) { return signedIn(r); }
        show(false);
      })
      .catch(function () { show(false); $("signin-error").textContent = "The service could not be reached."; });
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
      if (r.status === 200) {
        csrf = r.headers.get("Mover-CSRF-Token");
        return loadSession();
      }
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
  loadSession();
})();
