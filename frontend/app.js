// Highveld Air — TechLog frontend (v2). Vanilla JS, no build step.
// Auth: full Cognito account lifecycle via the public Cognito IDP API —
// sign up, email confirmation, sign in (USER_PASSWORD_AUTH), password reset.
// New accounts are added to the Mechanic group by the PostConfirmation
// Lambda; Certifying is admin-assigned only. The IdToken lives in
// sessionStorage and is sent as Bearer to API Gateway.

const CFG = window.TECHLOG_CONFIG || {};
const $ = (id) => document.getElementById(id);

const FLEET = Array.from({ length: 20 }, (_, i) => "ZS-LE" + String.fromCharCode(65 + i)); // ZS-LEA..ZS-LET
const STATUSES = ["OPEN", "DEFERRED", "RECTIFIED", "CLOSED"];

let currentStatus = "OPEN";
let tailFilter = null;
let currentDefect = null;
let cache = { OPEN: [], DEFERRED: [], RECTIFIED: [], CLOSED: [] };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function token() { return sessionStorage.getItem("techlog_id_token"); }

function jwtClaims(jwt) {
  try {
    const part = jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part));
  } catch { return {}; }
}

function myGroups() {
  const g = jwtClaims(token() || "")["cognito:groups"];
  return Array.isArray(g) ? g : [];
}

/* ---------------- Cognito ---------------- */

async function cognito(target, body) {
  const res = await fetch(`https://cognito-idp.${CFG.REGION}.amazonaws.com/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityProviderService." + target
    },
    body: JSON.stringify(body)
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.message || ("Cognito error (" + res.status + ")"));
    err.name = data.__type || "";
    throw err;
  }
  return data;
}

const signUp = (name, email, password) => cognito("SignUp", {
  ClientId: CFG.USER_POOL_CLIENT_ID, Username: email, Password: password,
  UserAttributes: [{ Name: "email", Value: email }, { Name: "name", Value: name }]
});

const confirmSignUp = (email, code) => cognito("ConfirmSignUp", {
  ClientId: CFG.USER_POOL_CLIENT_ID, Username: email, ConfirmationCode: code
});

const resendCode = (email) => cognito("ResendConfirmationCode", {
  ClientId: CFG.USER_POOL_CLIENT_ID, Username: email
});

const forgotPassword = (email) => cognito("ForgotPassword", {
  ClientId: CFG.USER_POOL_CLIENT_ID, Username: email
});

const confirmForgot = (email, code, password) => cognito("ConfirmForgotPassword", {
  ClientId: CFG.USER_POOL_CLIENT_ID, Username: email, ConfirmationCode: code, Password: password
});

async function login(email, password) {
  const data = await cognito("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: CFG.USER_POOL_CLIENT_ID,
    AuthParameters: { USERNAME: email, PASSWORD: password }
  });
  if (!data.AuthenticationResult) throw new Error("Sign-in failed");
  sessionStorage.setItem("techlog_id_token", data.AuthenticationResult.IdToken);
  sessionStorage.setItem("techlog_email", email);
}

/* ---------------- API ---------------- */

async function api(path, options = {}) {
  const res = await fetch(CFG.API_BASE + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + token(),
      ...(options.headers || {})
    }
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
  return data;
}

/* ---------------- Views ---------------- */

function showAuthCard(id) {
  for (const c of ["signin-card", "register-card", "confirm-card", "forgot-card"]) {
    $(c).classList.toggle("hidden", c !== id);
  }
}

function showApp() {
  $("auth-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  const groups = myGroups();
  $("who").textContent = sessionStorage.getItem("techlog_email") || "";
  $("role-chip").textContent = groups.includes("Certifying") ? "Certifying staff"
    : groups.includes("Mechanic") ? "Mechanic" : "No role assigned";
  refreshAll();
}

/* ---------------- Fleet + board ---------------- */

async function refreshAll() {
  const results = await Promise.all(
    STATUSES.map((s) => api(`/defects?status=${s}`).then((d) => [s, d.defects])));
  cache = Object.fromEntries(results);
  renderStats();
  renderFleet();
  renderBoard();
}

function tailState(tail) {
  const open = cache.OPEN.filter((d) => d.tail === tail);
  const deferred = cache.DEFERRED.filter((d) => d.tail === tail);
  if (open.some((d) => d.category === "AOG")) return ["red", "AOG"];
  if (open.length) return ["amber", open.length + " open defect" + (open.length > 1 ? "s" : "")];
  if (deferred.length) return ["grey", deferred.length + " deferred"];
  return ["", "In service"];
}

function renderStats() {
  const grounded = new Set(cache.OPEN.filter((d) => d.category === "AOG").map((d) => d.tail));
  $("st-serviceable").textContent = (FLEET.length - grounded.size) + " / " + FLEET.length;
  $("st-open").textContent = cache.OPEN.length;
  $("st-aog").textContent = cache.OPEN.filter((d) => d.category === "AOG").length;
  $("st-deferred").textContent = cache.DEFERRED.length;
}

function renderFleet() {
  const grid = $("fleet-grid");
  grid.innerHTML = "";
  for (const tail of FLEET) {
    const [dot, label] = tailState(tail);
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tail-card" + (tailFilter === tail ? " selected" : "");
    b.innerHTML = `<span class="tail-reg"><span class="dot ${dot}"></span>${tail}</span>
                   <span class="tail-state">A320 · ${esc(label)}</span>`;
    b.addEventListener("click", () => {
      tailFilter = tailFilter === tail ? null : tail;
      renderFleet(); renderBoard();
      document.querySelector(".tabs").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    grid.appendChild(b);
  }
}

function renderBoard() {
  const chip = $("tail-filter");
  if (tailFilter) {
    chip.textContent = "Filtered: " + tailFilter + " ✕";
    chip.classList.remove("hidden");
    chip.classList.add("clickable");
  } else chip.classList.add("hidden");

  let rows = cache[currentStatus];
  if (tailFilter) rows = rows.filter((d) => d.tail === tailFilter);
  const body = $("board-body");
  body.innerHTML = "";
  $("board-empty").classList.toggle("hidden", rows.length > 0);
  for (const d of rows) {
    const tr = document.createElement("tr");
    tr.className = d.category === "AOG" ? "aog" : "";
    tr.innerHTML = `<td><b>${esc(d.tail)}</b></td><td>${esc(d.ataChapter)}</td><td>${esc(d.station)}</td>
      <td>${esc(d.category)}</td><td>${esc(d.description)}</td><td>${esc((d.createdAt || "").slice(0, 10))}</td>`;
    tr.addEventListener("click", () => openDefect(d.defectId));
    body.appendChild(tr);
  }
}

/* ---------------- Defect detail ---------------- */

async function openDefect(id) {
  const data = await api(`/defects/${id}`);
  currentDefect = data.defect;
  const d = data.defect;
  $("detail-card").classList.remove("hidden");
  $("detail-body").innerHTML =
    `<p><b>${esc(d.tail)}</b> (${esc(d.fleetType)}) · ATA ${esc(d.ataChapter)} · ${esc(d.station)} ·
     <span class="badge">${esc(d.status)}</span>
     <span class="badge ${d.category === "AOG" ? "aog" : d.status === "DEFERRED" ? "def" : ""}">${esc(d.category)}</span></p>
     <p>${esc(d.description)}</p>
     ${d.melRef ? `<p>MEL ref: <b>${esc(d.melRef)}</b></p>` : ""}
     ${d.rectificationNote ? `<p>Rectification: ${esc(d.rectificationNote)}</p>` : ""}
     <p class="hint">Raised by ${esc(d.raisedBy)} at ${esc(d.createdAt)}</p>`;

  const actions = {
    OPEN: [["defer", "Defer (MEL ref)"], ["rectify", "Rectify (note)"]],
    DEFERRED: [["rectify", "Rectify (note)"]],
    RECTIFIED: [["close", "Close"]],
    CLOSED: [["reopen", "Reopen (reason)"]]
  }[d.status] || [];
  const box = $("detail-actions");
  box.innerHTML = "";
  for (const [action, label] of actions) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.addEventListener("click", () => doAction(action));
    box.appendChild(btn);
  }

  const list = $("history-list");
  list.innerHTML = "";
  for (const h of data.history) {
    const li = document.createElement("li");
    li.textContent = `${h.at} — ${h.event} by ${h.actor}${h.detail ? " · " + h.detail : ""}`;
    list.appendChild(li);
  }
  $("detail-card").scrollIntoView({ behavior: "smooth" });
}

async function doAction(action) {
  const field = { defer: "melRef", rectify: "rectificationNote", reopen: "reason" }[action];
  const body = { action };
  if (field) {
    const value = prompt(`Enter ${field}:`);
    if (!value) return;
    body[field] = value;
  }
  try {
    await api(`/defects/${currentDefect.defectId}/status`, {
      method: "PATCH", body: JSON.stringify(body)
    });
    await refreshAll();
    await openDefect(currentDefect.defectId);
  } catch (e) { alert(e.message); }
}

/* ---------------- Wiring ---------------- */

document.addEventListener("DOMContentLoaded", () => {
  // auth tabs + links
  document.querySelectorAll("[data-authtab]").forEach((el) =>
    el.addEventListener("click", () =>
      showAuthCard(el.dataset.authtab === "register" ? "register-card" : "signin-card")));
  $("goto-confirm").addEventListener("click", () => showAuthCard("confirm-card"));
  $("goto-forgot").addEventListener("click", () => showAuthCard("forgot-card"));

  // sign in
  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("login-error").textContent = "";
    const email = $("login-email").value.trim();
    try {
      await login(email, $("login-password").value);
      showApp();
    } catch (err) {
      if ((err.name || "").includes("UserNotConfirmedException")) {
        $("conf-email").value = email;
        showAuthCard("confirm-card");
        $("confirm-error").textContent = "This account is not confirmed yet — enter the code from your email.";
      } else $("login-error").textContent = err.message;
    }
  });

  // register
  $("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("register-error").textContent = "";
    const email = $("reg-email").value.trim();
    const pw = $("reg-password").value;
    if (pw !== $("reg-password2").value) {
      $("register-error").textContent = "The two passwords do not match.";
      return;
    }
    try {
      await signUp($("reg-name").value.trim(), email, pw);
      $("conf-email").value = email;
      showAuthCard("confirm-card");
      $("confirm-ok").textContent = "Account created — your confirmation code is on its way to " + email + ".";
    } catch (err) { $("register-error").textContent = err.message; }
  });

  // confirm
  $("confirm-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("confirm-error").textContent = ""; $("confirm-ok").textContent = "";
    try {
      await confirmSignUp($("conf-email").value.trim(), $("conf-code").value.trim());
      $("confirm-ok").textContent = "Email confirmed — your Mechanic access is active. You can sign in now.";
    } catch (err) { $("confirm-error").textContent = err.message; }
  });
  $("resend-code").addEventListener("click", async () => {
    $("confirm-error").textContent = ""; $("confirm-ok").textContent = "";
    try {
      await resendCode($("conf-email").value.trim());
      $("confirm-ok").textContent = "A fresh code is on its way.";
    } catch (err) { $("confirm-error").textContent = err.message; }
  });

  // forgot password
  $("forgot-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("forgot-error").textContent = "";
    const email = $("fp-email").value.trim();
    try {
      await forgotPassword(email);
      $("forgot2-form").classList.remove("hidden");
      $("forgot-error").textContent = "";
      $("forgot2-ok").textContent = "Reset code sent to " + email + ".";
    } catch (err) { $("forgot-error").textContent = err.message; }
  });
  $("forgot2-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("forgot2-error").textContent = ""; $("forgot2-ok").textContent = "";
    try {
      await confirmForgot($("fp-email").value.trim(), $("fp-code").value.trim(), $("fp-password").value);
      $("forgot2-ok").textContent = "Password updated — sign in with the new password.";
    } catch (err) { $("forgot2-error").textContent = err.message; }
  });

  // session
  $("logout").addEventListener("click", () => { sessionStorage.clear(); location.reload(); });

  // board
  $("status-tabs").addEventListener("click", (e) => {
    if (e.target.dataset.status) {
      currentStatus = e.target.dataset.status;
      document.querySelectorAll("#status-tabs button").forEach(
        (b) => b.classList.toggle("active", b.dataset.status === currentStatus));
      renderBoard();
    }
  });
  $("tail-filter").addEventListener("click", () => { tailFilter = null; renderFleet(); renderBoard(); });

  // raise
  const tailSel = $("f-tail");
  for (const tail of FLEET) {
    const opt = document.createElement("option");
    opt.textContent = tail + " — A320"; opt.value = tail;
    tailSel.appendChild(opt);
  }
  $("raise-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const created = await api("/defects", {
        method: "POST",
        body: JSON.stringify({
          tail: $("f-tail").value, fleetType: "A320",
          ataChapter: $("f-ata").value.trim(), station: $("f-station").value,
          category: $("f-category").value, description: $("f-desc").value.trim()
        })
      });
      $("raise-msg").textContent = "Raised: " + created.defectId;
      $("f-desc").value = "";
      currentStatus = "OPEN";
      document.querySelectorAll("#status-tabs button").forEach(
        (b) => b.classList.toggle("active", b.dataset.status === "OPEN"));
      await refreshAll();
    } catch (err) { $("raise-msg").textContent = err.message; }
  });

  // photo
  $("photo-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file || !currentDefect) return;
    try {
      const { uploadUrl } = await api(`/defects/${currentDefect.defectId}/photo-url`, {
        method: "POST", body: JSON.stringify({ contentType: file.type || "image/jpeg" })
      });
      await fetch(uploadUrl, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
      $("photo-msg").textContent = "Photo uploaded to the versioned documents bucket.";
    } catch (err) { $("photo-msg").textContent = err.message; }
  });

  if (token()) showApp();
});
