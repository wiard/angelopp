function nowTs(){
  const d = new Date();
  return d.toLocaleTimeString();
}

function newSessionId(){
  return "WEB" + Date.now();
}

async function postUSSD(sessionId, phoneNumber, text){
  const body = new URLSearchParams();
  body.set("sessionId", sessionId);
  body.set("phoneNumber", phoneNumber);
  body.set("text", text);

  const res = await fetch("/ussd", {
    method: "POST",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: body.toString()
  });

  const t = await res.text();
  return {status: res.status, text: t};
}

function setStatus(el, msg, cls){
  el.className = "status " + (cls || "");
  el.textContent = msg;
}

function addHistory(historyEl, req, resp){
  const wrap = document.createElement("div");
  wrap.className = "item";

  const hdr = document.createElement("div");
  hdr.className = "hdr";
  hdr.innerHTML = `<span>${nowTs()}</span><span>HTTP ${resp.status}</span>`;

  const pre = document.createElement("pre");
  pre.textContent =
`REQ
sessionId=${req.sessionId}
phoneNumber=${req.phoneNumber}
text=${req.text}

RESP
${resp.text}`.trim();

  wrap.appendChild(hdr);
  wrap.appendChild(pre);

  historyEl.prepend(wrap);
}

document.addEventListener("DOMContentLoaded", () => {
  const elSid = document.getElementById("sessionId");
  const elPhone = document.getElementById("phoneNumber");
  const elText = document.getElementById("text");
  const elResp = document.getElementById("response");
  const elHist = document.getElementById("history");
  const elStatus = document.getElementById("status");

  const btnSend = document.getElementById("btnSend");
  const btnNewSid = document.getElementById("btnNewSid");
  const btnClear = document.getElementById("btnClear");
  const btnRoot = document.getElementById("btnRoot");
  const btnBack0 = document.getElementById("btnBack0");
  const btnCopy = document.getElementById("btnCopy");

  elSid.value = newSessionId();

  async function send(textOverride){
    const req = {
      sessionId: (elSid.value || "").trim(),
      phoneNumber: (elPhone.value || "").trim(),
      text: (typeof textOverride === "string") ? textOverride : (elText.value || "")
    };

    if(!req.sessionId) req.sessionId = newSessionId();
    elSid.value = req.sessionId;

    setStatus(elStatus, "Sending…", "warn");
    btnSend.disabled = true;

    try{
      const resp = await postUSSD(req.sessionId, req.phoneNumber, req.text);
      elResp.textContent = resp.text || "";
      addHistory(elHist, req, resp);

      // Heuristic: highlight END/CON
      const head = (resp.text || "").trim().slice(0, 4).toUpperCase();
      if(head === "END ") setStatus(elStatus, "END response", "ok");
      else if(head === "CON ") setStatus(elStatus, "CON response", "ok");
      else setStatus(elStatus, "Response received", "ok");

    } catch(e){
      elResp.textContent = String(e);
      setStatus(elStatus, "Error: " + String(e), "bad");
    } finally {
      btnSend.disabled = false;
      elText.focus();
    }
  }

  btnSend.addEventListener("click", () => send());
  elText.addEventListener("keydown", (e) => {
    if(e.key === "Enter") send();
  });

  btnNewSid.addEventListener("click", () => {
    elSid.value = newSessionId();
    setStatus(elStatus, "New sessionId set", "");
  });

  btnClear.addEventListener("click", () => {
    elHist.innerHTML = "";
    elResp.textContent = "—";
    setStatus(elStatus, "Cleared", "");
  });

  btnRoot.addEventListener("click", () => {
    elText.value = "";
    send("");
  });

  btnBack0.addEventListener("click", () => {
    const t = (elText.value || "").trim();
    if(!t) { elText.value = "0"; return; }
    elText.value = t.endsWith("*0") ? t : (t + "*0");
    send(elText.value);
  });

  btnCopy.addEventListener("click", async () => {
    try{
      await navigator.clipboard.writeText(elResp.textContent || "");
      setStatus(elStatus, "Copied response", "ok");
    } catch(e){
      setStatus(elStatus, "Copy failed", "bad");
    }
  });

  // Quick chips
  document.querySelectorAll(".chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const txt = btn.getAttribute("data-text") || "";
      elText.value = txt;
      send(txt);
    });
  });
});


// START button: send empty text to show the root menu without "Invalid option"
const startBtn = document.getElementById("startBtn");
if (startBtn) {
  startBtn.addEventListener("click", async () => {
    document.getElementById("text").value = "";
    // keep sessionId + phoneNumber as-is, but send empty text
    await sendRequest();
  });
}
