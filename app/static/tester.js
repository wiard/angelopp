"use strict";

const $ = (id) => document.getElementById(id);

function nowId() { return "WEB" + Date.now(); }
function escapeHtml(s) {
  return (s ?? "").toString()
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#039;");
}

function setText(t) { $("text").value = t ?? ""; }
function appendText(s) { $("text").value = ($("text").value || "") + (s || ""); }
function setPhone(p) { if (p) $("phoneNumber").value = p; }

async function postUssd() {
  const base = $("baseUrl").value.trim() || "/ussd";
  const sid = $("sessionId").value.trim() || nowId();
  const phone = $("phoneNumber").value.trim();
  const text = $("text").value;

  $("sessionId").value = sid;

  const body = new URLSearchParams();
  body.set("sessionId", sid);
  body.set("phoneNumber", phone);
  body.set("text", text);

  const r = await fetch(base, { method:"POST", body });
  const resp = await r.text();
  $("resp").textContent = resp;  renderClickableOptions(resp);
  try { await loadPanels(); } catch (e) {
    console.warn("loadPanels failed", e);
  }
}

function renderClickableOptions(respText) {
  const clicks = $("clicks");
  clicks.innerHTML = "";
  const lines = (respText || "").split("\n").map(l => l.trim()).filter(Boolean);

  // Parse menu lines like: "1. Foo" or "2) Foo" or "0. Back"
  const opts = [];
  for (const l of lines) {
    let m = l.match(/^(\d+)\s*[\.\)]\s*(.+)$/);
    if (m) opts.push({ n: m[1], label: m[2] });
  }

  if (!opts.length) return;

  for (const o of opts) {
    const b = document.createElement("button");
    b.className = "btn small";
    b.textContent = `${o.n} → ${o.label}`;
    b.onclick = () => {
      const cur = $("text").value || "";
      if (!cur) setText(o.n);
      else appendText("*" + o.n);
      postUssd();
    };
    clicks.appendChild(b);
  }
}

async function whoami() {
  const phone = $("phoneNumber").value.trim();
  const r = await fetch(`/api/whoami?phone=${encodeURIComponent(phone)}`);
  const j = await r.json();
  $("dbg").textContent = JSON.stringify(j, null, 2);
  $("role").textContent = j.role ?? "?";
  $("village").textContent = j.village ?? "?";
  return j;
}

async function health() {
  const r = await fetch("/health");
  const t = await r.text();
  $("dbg").textContent = t;
  $("serverOk").textContent = t.trim() === "OK" || t.trim() === "ok" ? "ok" : t.trim();
}

async function seedDemo() {
  const phone = $("phoneNumber").value.trim();
  const village = $("village").textContent?.trim() || "Church";
  const r = await fetch(`/api/seed_demo?phone=${encodeURIComponent(phone)}&village=${encodeURIComponent(village)}`, { method:"POST" });
  const j = await r.json();
  $("dbg").textContent = JSON.stringify(j, null, 2);
  await loadPanels();
}

async function clearDemo() {
  const phone = $("phoneNumber").value.trim();
  const village = $("village").textContent?.trim() || "Church";
  const r = await fetch(`/api/clear_demo?phone=${encodeURIComponent(phone)}&village=${encodeURIComponent(village)}`, { method:"POST" });
  const j = await r.json();
  $("dbg").textContent = JSON.stringify(j, null, 2);
  await loadPanels();
}

function renderPanels(p) {
  const root = $("panels");
  root.innerHTML = "";

  const mk = (title) => {
    const d = document.createElement("div");
    d.className = "panel";
    const h = document.createElement("div");
    h.className = "panelTitle";
    h.textContent = title;
    const c = document.createElement("div");
    c.className = "panelBody";
    d.appendChild(h); d.appendChild(c);
    root.appendChild(d);
    return c;
  };

  // Riders: use USSD flow "1" and click 1/2/3 etc
  const riders = mk("Nearest riders (USSD: 1)");
  const ridersHint = document.createElement("div");
  ridersHint.className = "muted";
  ridersHint.innerHTML = `Click: set <code>text=1</code> then choose 1/2/3.`;
  riders.appendChild(ridersHint);
  const bR = document.createElement("button");
  bR.className = "btn small";
  bR.textContent = "Go → 1 (Nearest riders)";
  bR.onclick = () => { setText("1"); postUssd(); };
  riders.appendChild(bR);

  // Deliveries
  const del = mk("Deliveries (Provider inbox: 4*2)");
  const delBtns = document.createElement("div");
  delBtns.className = "row";
  const bIn = document.createElement("button");
  bIn.className = "btn small";
  bIn.textContent = "Open inbox as Provider (+254700000002)";
  bIn.onclick = () => { setPhone("+254700000002"); setText("4*2"); postUssd(); };
  delBtns.appendChild(bIn);
  del.appendChild(delBtns);

  const latest = p?.deliveries?.latest || [];
  const open = p?.deliveries?.open || [];
  const list = [...open, ...latest].slice(0, 10);

  if (!list.length) {
    const e = document.createElement("div");
    e.className = "muted";
    e.textContent = "No deliveries in panels.";
    del.appendChild(e);
  } else {
    for (const d of list) {
      const row = document.createElement("div");
      row.className = "item";
      const id = d.id ?? d[0];
      const pickup = d.pickup_landmark ?? d[4] ?? "Unknown";
      const drop = d.dropoff_landmark ?? d[6] ?? "";
      const status = d.status ?? d[8] ?? "";
      const assigned = d.assigned_rider_phone ?? d[9] ?? "";

      row.innerHTML = `<b>#${escapeHtml(id)}</b> ${escapeHtml(pickup)} → ${escapeHtml(drop)} <span class="tag">${escapeHtml(status)}</span> ${assigned ? `<span class="tag">assigned: ${escapeHtml(assigned)}</span>` : ""}`;
      const actions = document.createElement("div");
      actions.className = "row";

      // provider action path: 4*2*<n>*X is index-based in inbox; we don't know index here.
      // But we CAN jump to inbox and user clicks item number.
      const go = document.createElement("button");
      go.className = "btn small";
      go.textContent = "Go inbox";
      go.onclick = () => { setPhone("+254700000002"); setText("4*2"); postUssd(); };
      actions.appendChild(go);

      const note = document.createElement("div");
      note.className = "muted";
      note.textContent = "Then choose item number (1/2/3...) to view details, then Accept/Picked up/Delivered.";
      row.appendChild(actions);
      row.appendChild(note);
      del.appendChild(row);
    }
  }

  // Shops: USSD path currently "2"
  const shops = mk("Shops (USSD: 2)");
  const bS = document.createElement("button");
  bS.className = "btn small";
  bS.textContent = "Go → 2 (Local Businesses)";
  bS.onclick = () => { setText("2"); postUssd(); };
  shops.appendChild(bS);

  const biz = p?.businesses || [];
  if (biz.length) {
    const ul = document.createElement("div");
    ul.className = "muted";
    ul.textContent = `Known businesses in DB (panels): ${biz.length}`;
    shops.appendChild(ul);
  }

  // Channels: show list + USSD path "6" and "7"
  const ch = mk("Channels (USSD: 6 listen / 7 my channel)");
  const row = document.createElement("div");
  row.className = "row";
  const b6 = document.createElement("button");
  b6.className = "btn small";
  b6.textContent = "Go → 6 (Listen)";
  b6.onclick = () => { setText("6"); postUssd(); };
  const b7 = document.createElement("button");
  b7.className = "btn small";
  b7.textContent = "Go → 7 (My channel)";
  b7.onclick = () => { setText("7"); postUssd(); };
  row.appendChild(b6); row.appendChild(b7);
  ch.appendChild(row);

  const chans = p?.channels || [];
  if (chans.length) {
    for (const c of chans.slice(0, 10)) {
      const it = document.createElement("div");
      it.className = "item";
      it.innerHTML = `<b>${escapeHtml(c.name ?? "Channel")}</b> <span class="tag">#${escapeHtml(c.id ?? "")}</span> <span class="muted">${escapeHtml(c.created_at ?? "")}</span>`;
      ch.appendChild(it);
    }
  } else {
    const e = document.createElement("div");
    e.className = "muted";
    e.textContent = "No channels found in panels.";
    ch.appendChild(e);
  }
}

async function loadPanels() {
  const phone = $("phoneNumber").value.trim();
  const village = $("village").textContent?.trim() || "Church";
  const r = await fetch(`/api/panels?phone=${encodeURIComponent(phone)}&village=${encodeURIComponent(village)}`);
  const j = await r.json();
  $("panelsJson").textContent = JSON.stringify(j, null, 2);
  renderPanels(j);
  return j;
}

function bind() {
  $("btnStart").onclick = async () => { setText(""); await postUssd(); };
  $("btnSend").onclick = postUssd;
  $("btnReset").onclick = () => { $("sessionId").value = nowId(); $("dbg").textContent=""; $("resp").textContent=""; $("clicks").innerHTML=""; };
  $("btnSeed").onclick = seedDemo;
  $("btnClear").onclick = clearDemo;
  $("btnPanels").onclick = loadPanels;

  $("btnWhoami").onclick = whoami;
  $("btnHealth").onclick = health;

  // chips (settext + optional phone)
  document.querySelectorAll("[data-settext]").forEach((b) => {
    b.addEventListener("click", () => {
      const t = b.getAttribute("data-settext");
      const p = b.getAttribute("data-phone");
      if (p) setPhone(p);
      setText(t);
      postUssd();
    });
  });

  // small appenders
  document.querySelectorAll("[data-append]").forEach((b) => {
    b.addEventListener("click", () => {
      appendText(b.getAttribute("data-append"));
      postUssd();
    });
  });
}

(async function init(){
  $("sessionId").value = nowId();
  bind();
  await health();
  await whoami();
  await loadPanels();
})();
