// TechLog Cloud frontend - vanilla JS, no build step.
// Auth: Cognito USER_PASSWORD_AUTH via the public InitiateAuth API.
// The IdToken is kept in sessionStorage and sent as Bearer to API Gateway.

const CFG = window.TECHLOG_CONFIG || {};
const $ = (id) => document.getElementById(id);

const FLEET = [
  ["ZS-SXA", "B737-800"], ["ZS-SXB", "B737-800"], ["ZS-SXC", "B737-800"],
  ["ZS-ZWA", "A320"], ["ZS-ZWB", "A320"], ["ZS-ZWC", "A320"]
];

let currentStatus = "OPEN";
let currentDefect = null;

function token() { return sessionStorage.getItem("techlog_id_token"); }

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

async function login(email, password) {
  const res = await fetch(`https://cognito-idp.${CFG.REGION}.amazonaws.com/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"
    },
    body: JSON.stringify({
      AuthFlow: "USER_PASSWORD_AUTH",
      ClientId: CFG.USER_POOL_CLIENT_ID,
      AuthParameters: { USERNAME: email, PASSWORD: password }
    })
  });
  const data = await res.json();
  if (!res.ok || !data.AuthenticationResult) {
    throw new Error(data.message || "Login failed");
  }
  sessionStorage.setItem("techlog_id_token", data.AuthenticationResult.IdToken);
  sessionStorage.setItem("techlog_email", email);
}

function showApp() {
  $("login-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  $("userbar").classList.remove("hidden");
  $("who").textContent = sessionStorage.getItem("techlog_email") || "";
  loadBoard();
}

async function loadBoard() {
  const data = await api(`/defects?status=${currentStatus}`);
  const body = $("board-body");
  body.innerHTML = "";
  $("board-empty").classList.toggle("hidden", data.defects.length > 0);
  for (const d of data.defects) {
    const tr = document.createElement("tr");
    tr.className = d.category === "AOG" ? "aog" : "";
    tr.innerHTML = `<td>${d.tail}</td><td>${d.ataChapter}</td><td>${d.station}</td>
      <td>${d.category}</td><td>${d.description}</td><td>${(d.createdAt || "").slice(0, 10)}</td>`;
    tr.addEventListener("click", () => openDefect(d.defectId));
    body.appendChild(tr);
  }
}

async function openDefect(id) {
  const data = await api(`/defects/${id}`);
  currentDefect = data.defect;
  $("detail-card").classList.remove("hidden");
  const d = data.defect;
  $("detail-body").innerHTML =
    `<p><b>${d.tail}</b> (${d.fleetType}) · ATA ${d.ataChapter} · ${d.station} ·
     <span class="badge">${d.status}</span> <span class="badge">${d.category}</span></p>
     <p>${d.description}</p>
     ${d.melRef ? `<p>MEL ref: <b>${d.melRef}</b></p>` : ""}
     ${d.rectificationNote ? `<p>Rectification: ${d.rectificationNote}</p>` : ""}
     <p class="hint">Raised by ${d.raisedBy} at ${d.createdAt}</p>`;

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
    await openDefect(currentDefect.defectId);
    loadBoard();
  } catch (e) { alert(e.message); }
}

// --- wiring ---
document.addEventListener("DOMContentLoaded", () => {
  const tailSel = $("f-tail");
  for (const [tail] of FLEET) {
    const opt = document.createElement("option");
    opt.textContent = tail; opt.value = tail;
    tailSel.appendChild(opt);
  }

  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await login($("login-email").value, $("login-password").value);
      showApp();
    } catch (err) { $("login-error").textContent = err.message; }
  });

  $("logout").addEventListener("click", () => {
    sessionStorage.clear();
    location.reload();
  });

  $("status-tabs").addEventListener("click", (e) => {
    if (e.target.dataset.status) {
      currentStatus = e.target.dataset.status;
      document.querySelectorAll("#status-tabs button").forEach(
        (b) => b.classList.toggle("active", b.dataset.status === currentStatus));
      loadBoard();
    }
  });

  $("raise-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const tail = $("f-tail").value;
    const fleet = FLEET.find(([t]) => t === tail);
    try {
      const created = await api("/defects", {
        method: "POST",
        body: JSON.stringify({
          tail, fleetType: $("f-fleet").value,
          ataChapter: $("f-ata").value, station: $("f-station").value.toUpperCase(),
          category: $("f-category").value, description: $("f-desc").value
        })
      });
      $("raise-msg").textContent = "Raised: " + created.defectId +
        (fleet ? "" : "");
      $("f-desc").value = "";
      currentStatus = "OPEN";
      loadBoard();
    } catch (err) { $("raise-msg").textContent = err.message; }
  });

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
