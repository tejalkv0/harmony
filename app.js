/* Harmony front-end: plain JavaScript, no frameworks, no CDN (works offline except translation). */
const $ = s => document.querySelector(s);
const S = {uid: localStorage.uid || "", lang: localStorage.lang || "en", state: null, cfg: null, chat: []};
const t = k => (DICT[S.lang] && DICT[S.lang][k]) || DICT.en[k] || k;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const api = (p, body) => fetch("/api/" + p, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {}).then(r => r.json());
const toast = m => { const e = $("#toast"); e.textContent = m; e.classList.add("show"); setTimeout(() => e.classList.remove("show"), 2200); };

/* ---------- translation (dictionary first, then free online API with cache) ---------- */
const cache = JSON.parse(localStorage.tcache || "{}");
async function translateTexts(texts, target, source = "en") {
  const need = [...new Set(texts)].filter(x => !cache[source + target + x]);
  if (need.length) {
    for (let i = 0; i < need.length; i += 60) {
      const part = need.slice(i, i + 60);
      try {
        const r = await api("translate", {texts: part, target, source});
        part.forEach((x, j) => { if (r.texts[j] !== x) cache[source + target + x] = r.texts[j]; });
      } catch (e) {}
    }
    try { localStorage.tcache = JSON.stringify(cache); } catch (e) {}
  }
  return texts.map(x => cache[source + target + x] || x);
}
async function localize(root) {
  if (S.lang === "en") return;
  const nodes = [], w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const n = w.currentNode, s = n.nodeValue.trim();
    if (s.length < 2 || !/[A-Za-z]{2}/.test(s) || /[^\x00-\x7F]/.test(s.replace(/[\u2000-\u2BFF\u{1F000}-\u{1FFFF}µ·…’]/gu, ""))) continue;
    if (n.parentElement.closest("script,style,[data-keep]")) continue;
    const local = DICT[S.lang] && DICT[S.lang][s];
    if (local) n.nodeValue = n.nodeValue.replace(s, local); else nodes.push([n, s]);
  }
  if (!nodes.length) return;
  const out = await translateTexts(nodes.map(x => x[1]), S.lang);
  let miss = 0;
  nodes.forEach(([n, s], i) => { if (out[i] === s) miss++; else n.nodeValue = n.nodeValue.replace(s, out[i]); });
  if (miss > nodes.length / 2) toast(t("offline"));
}
const view = async html => { const v = $("#view"); v.innerHTML = html; window.scrollTo(0, 0); await localize(v); };

/* ---------- voice (Web Speech API) ---------- */
function listen(btn, onText) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return toast(t("voice_no"));
  if (!window.isSecureContext) return toast("Voice only works on https:// or http://localhost (not on an IP address or file).");
  try { S.rec && S.rec.abort(); } catch (e) {}
  const r = new SR(); S.rec = r; r.lang = LANGS[S.lang][1]; r.interimResults = false; r.maxAlternatives = 1;
  let got = false;
  const msgs = {"not-allowed":"Microphone is blocked. Click the 🔒 icon next to the address bar, allow Microphone, then reload.",
    "service-not-allowed":"Microphone is blocked. Click the 🔒 icon next to the address bar, allow Microphone, then reload.",
    "no-speech":"I didn't hear anything. Tap 🎤 and speak closer to the mic.", "audio-capture":"No microphone found. Plug in or enable a mic.",
    "network":"Voice needs internet (Chrome sends the audio to Google). Please check your connection.",
    "language-not-supported":"This browser can't recognise that language by voice. Try English or Hindi, or type."};
  btn.classList.add("rec"); toast("🎤 Listening… speak now");
  r.onresult = e => { got = true; onText(e.results[0][0].transcript); };
  r.onerror = e => toast(msgs[e.error] || ("Voice error: " + e.error));
  r.onend = () => btn.classList.remove("rec");
  try { r.start(); } catch (e) { btn.classList.remove("rec"); toast("Voice could not start. Reload the page and try again."); }
}
function speak(text) {
  if (!("speechSynthesis" in window)) return toast(t("tts_no"));
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text); u.lang = LANGS[S.lang][1];
  const v = speechSynthesis.getVoices().find(v => v.lang.startsWith(S.lang));
  if (!v && S.lang !== "en") toast(t("tts_no")); else { if (v) u.voice = v; speechSynthesis.speak(u); }
}

/* ---------- chrome ---------- */
const NAV = [["home","🏠","nav_home"],["checkin","📝","nav_checkin"],["usual","📈","nav_usual"],["lab","🧪","nav_lab"],["summary","📋","nav_summary"],["chat","💬","nav_chat"]];
async function chrome() {
  const page = (location.hash || "#home").slice(1);
  $("#top").innerHTML = `<div class="logo" onclick="location.hash='home'"><span data-keep>🌿 Harmony</span><small>${t("tagline")}</small></div>
   <div class="search"><input id="q" placeholder="${t("search_ph")}"><button class="mic" id="qmic" style="width:38px;height:38px;font-size:16px">🎤</button></div>
   <a href="#settings" title="Settings" style="font-size:24px;text-decoration:none">⚙️</a>
   <select class="lang" id="lang">${Object.entries(LANGS).map(([k,v]) => `<option value="${k}" ${k===S.lang?"selected":""}>${v[0]}</option>`).join("")}</select>`;
  $("#nav").innerHTML = NAV.map(([id,ic,k]) => `<a href="#${id}" class="${page===id?"on":""}"><span>${ic}</span>${t(k)}</a>`).join("");
  $("#lang").onchange = async e => { S.lang = localStorage.lang = e.target.value; if (S.uid) api("profile", {...S.state?.profile, uid: S.uid, lang: S.lang}); await chrome(); route(); };
  $("#q").onkeydown = e => { if (e.key === "Enter" && e.target.value.trim()) { const v = e.target.value; e.target.value = ""; ask(v); } };
  $("#qmic").onclick = () => listen($("#qmic"), txt => ask(txt));
  await localize($("#top")); 
}
const ask = txt => { S.pending = txt; if (location.hash === "#chat") route(); else location.hash = "chat"; };

/* ---------- pages ---------- */
async function route() {
  if (!S.uid) return onboarding();
  if (!S.state) { S.state = await api("state?uid=" + S.uid); if (S.state.error) { S.uid = ""; localStorage.removeItem("uid"); return onboarding(); } }
  const p = (location.hash || "#home").slice(1);
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#" + p));
  ({home, checkin, usual, lab, summary, chat, settings}[p] || home)();
}
window.onhashchange = route;

async function onboarding() {
  await view(`<div class="card hero"><div style="font-size:54px">🌿</div><h1>${t("welcome")}</h1><p class="sub">${t("welcome_sub")}</p></div>
  <div class="card"><label class="q">${t("name")}</label><input class="f" id="n" placeholder="Tejal">
  <label class="q">${t("age")}</label><input class="f" id="a" type="number" min="10" max="90">
  <label class="q">${t("sex")}</label><div class="faces" id="sx">${["female","male","other"].map((s,i)=>`<button data-v="${s}" class="${i?"":"on"}" style="font-size:17px">${t(s)}</button>`).join("")}</div>
  <p style="margin-top:22px"><button class="btn" id="go">${t("start")} →</button></p></div><p class="disc">${t("disclaimer")}</p>`);
  let sex = "female";
  document.querySelectorAll("#sx button").forEach(b => b.onclick = () => { document.querySelectorAll("#sx button").forEach(x => x.classList.remove("on")); b.classList.add("on"); sex = b.dataset.v; });
  $("#go").onclick = async () => {
    const r = await api("profile", {name: $("#n").value, age: +$("#a").value || null, sex, lang: S.lang});
    S.uid = localStorage.uid = r.uid; S.state = null; location.hash = "home"; route();
  };
}

async function home() {
  const s = S.state, b = s.baseline, areas = Object.values(s.areas), n = s.checkins.length;
  let h = `<h1>${t("hi")} <span data-keep>${esc(s.profile.name)}</span> 👋</h1><p class="sub">${t("home_sub")}</p>`;
  if (!n) h += `<div class="card hero"><div style="font-size:50px">📝</div><p>${t("none_yet")}</p><a class="btn" href="#checkin">${t("start_checkin")}</a> <button class="btn alt" id="demo">${t("try_demo")}</button></div>`;
  else h += `<p><a class="btn" href="#checkin">📝 ${t("start_checkin")}</a></p>`;
  if (n && !b.ready) h += `<div class="card"><b>🌱 ${t("learning")}</b><div class="bar" style="margin:10px 0"><i style="width:${n/b.needed*100}%"></i></div>${n} / ${b.needed} ${t("days")}</div>`;
  if (b.drifts?.length) h += `<div class="card alert"><h3>⚠️ ${t("early")}</h3>${b.drifts.map(d => `<p style="margin:6px 0">• ${esc(d.text)}${d.maybe_because.length ? `<br><small style="color:var(--soft)">Maybe because: ${d.maybe_because.map(esc).join(", ")}</small>` : ""}</p>`).join("")}</div>`;
  if (b.good?.length) h += `<div class="card ok"><h3>💚 ${t("good_news")}</h3>${b.good.map(g => `<p style="margin:4px 0">• ${esc(g)}</p>`).join("")}</div>`;
  if (n) h += `<h2>${t("body_areas")}</h2><div class="grid">${areas.map(a => `<div class="card area l${a.level}"><span class="ic">${a.icon}</span> <b>${esc(a.name)}</b><br><span class="pill">${esc(a.status)}</span>${a.reasons.length ? `<ul>${a.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}</div>`).join("")}</div>`;
  h += `<p class="disc">${t("disclaimer")}</p>`;
  await view(h);
  if ($("#demo")) $("#demo").onclick = async () => { S.state = await api("demo", {uid: S.uid}); toast("✅"); home(); };
}

async function checkin() {
  const c = S.state.checkins.find(r => r.date === new Date().toISOString().slice(0, 10)) || {};
  const sel = {energy: c.energy || 3, mood: c.mood || 3, stress: c.stress || 3};
  const sym = new Set(c.symptoms || []), ctx = new Set(c.context || []); let period = false;
  const faces = {energy:["😩","😕","😐","🙂","🤩"], mood:["😢","😟","😐","🙂","😄"], stress:["😌","🙂","😐","😣","🤯"]};
  const row = (k, q) => `<label class="q">${t(q)}</label><div class="faces" data-k="${k}">${faces[k].map((f,i) => `<button data-v="${i+1}" class="${sel[k]===i+1?"on":""}">${f}</button>`).join("")}</div>`;
  const chips = (obj, id) => `<div class="chips" id="${id}">${Object.entries(obj).map(([k,v]) => `<button class="chip" data-k="${k}">${v.emoji} ${esc(v.label)}</button>`).join("")}</div>`;
  await view(`<h1>📝 ${t("nav_checkin")}</h1><div class="card">
   <label class="q">${t("sleep_q")} <span class="big" id="sv">${c.sleep || 7}</span> h</label><input type="range" id="sl" min="2" max="12" step="0.5" value="${c.sleep || 7}">
   ${row("energy","energy_q")}${row("mood","mood_q")}${row("stress","stress_q")}
   <label class="q">${t("sym_q")}</label>${chips(S.cfg.symptoms,"sy")}
   <label class="q">${t("ctx_q")}</label>${chips(S.cfg.context,"cx")}
   ${S.state.profile.sex === "female" ? `<label class="q"><input type="checkbox" id="pd" style="width:20px;height:20px"> 🩸 ${t("period_q")}</label>` : ""}
   <p><button class="btn coral" id="save">${t("save_checkin")}</button></p></div>`);
  $("#sl").oninput = e => $("#sv").textContent = e.target.value;
  document.querySelectorAll(".faces").forEach(f => f.querySelectorAll("button").forEach(b => b.onclick = () => { f.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); sel[f.dataset.k] = +b.dataset.v; }));
  const wire = (id, set) => document.querySelectorAll(`#${id} .chip`).forEach(b => { if (set.has(b.dataset.k)) b.classList.add("on"); b.onclick = () => { b.classList.toggle("on"); set.has(b.dataset.k) ? set.delete(b.dataset.k) : set.add(b.dataset.k); }; });
  wire("sy", sym); wire("cx", ctx);
  $("#save").onclick = async () => {
    S.state = await api("checkin", {uid: S.uid, sleep: +$("#sl").value, ...sel, symptoms: [...sym], context: [...ctx], period_started: $("#pd")?.checked});
    toast(t("saved")); location.hash = "home";
  };
}

function chart(m) {
  const W = 620, H = 190, P = 34, pts = m.series; if (pts.length < 2) return "";
  const vals = pts.map(p => p.v).concat(m.band); let lo = Math.min(...vals) - .4, hi = Math.max(...vals) + .4;
  const x = i => P + i * (W - P * 1.5) / (pts.length - 1), y = v => H - 24 - (v - lo) / (hi - lo) * (H - 44);
  const worse = v => m.label === "Stress" ? v > m.band[1] : v < m.band[0];
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" data-keep>
   <rect x="${P}" y="${y(m.band[1])}" width="${W-P*1.5}" height="${y(m.band[0])-y(m.band[1])}" fill="#3fb67a" opacity=".18" rx="8"/>
   <line x1="${P}" x2="${W-P/2}" y1="${y(m.usual)}" y2="${y(m.usual)}" stroke="#3fb67a" stroke-dasharray="5 4"/>
   <polyline fill="none" stroke="#2a9d8f" stroke-width="3" stroke-linejoin="round" points="${pts.map((p,i) => x(i)+","+y(p.v)).join(" ")}"/>
   ${pts.map((p,i) => `<circle cx="${x(i)}" cy="${y(p.v)}" r="${worse(p.v)?6:3.5}" fill="${worse(p.v)?"#e5584b":"#2a9d8f"}"><title>${p.d}: ${p.v}</title></circle>`).join("")}
   <text x="${P}" y="${H-5}">${pts[0].d.slice(5)}</text><text x="${W-P*1.5}" y="${H-5}">${pts.at(-1).d.slice(5)}</text></svg>`;
}
async function usual() {
  const b = S.state.baseline; let h = `<h1>📈 ${t("usual_title")}</h1><div class="card"><p>${t("usual_what")}</p></div>`;
  if (!b.ready) h += `<div class="card"><p>${t("usual_wait")}</p><div class="bar"><i style="width:${b.days/b.needed*100}%"></i></div><p>${b.days} / ${b.needed} ${t("days")}</p></div>`;
  else for (const m of Object.values(b.metrics)) {
    const d = m.worse >= 1.5 ? "🔴" : m.worse <= -1.5 ? "💚" : "🟢";
    h += `<div class="card"><b>${d} ${m.label}</b> <span style="color:var(--soft)">· usual ${m.usual}${m.unit} · now ${m.now}${m.unit}</span>${chart(m)}</div>`;
  }
  const c = b.cycle;
  if (c) h += `<div class="card"><b>🌸 ${t("cycle")}</b><p>Last period: ${c.last} (${c.days_since} days ago)${c.usual ? `<br>Your usual cycle: about ${c.usual} days` : ""}${c.late ? `<br>⚠️ Later than your usual.` : ""}</p></div>`;
  await view(h);
}

async function lab() {
  const L = S.cfg.labs, sex = S.state.profile.sex;
  const cb = (k, key) => `<label style="display:flex;gap:10px;margin:8px 0;align-items:flex-start"><input type="checkbox" id="c_${k}" ${k==="fasting"?"checked":""} style="width:20px;height:20px;flex:none;margin-top:3px"><span>${t(key)}</span></label>`;
  const hist = S.state.labs.slice().reverse().map(l => `<div class="card"><b>${esc(l.name)}</b>: ${l.value} ${esc(l.unit)} <span class="pill ${l.status==="normal"?"":"y"}">${t(l.status)}</span> · ${l.date}<br><small>${esc(l.trust)}</small></div>`).join("");
  await view(`<h1>🧪 ${t("lab_title")}</h1><p class="sub">${t("lab_sub")}</p><div class="card">
   <label class="q">${t("which_test")}</label><select class="f" id="test">${Object.entries(L).map(([k,v]) => `<option value="${k}">${esc(v.name)}</option>`).join("")}</select>
   <label class="q">${t("value")} <small id="rng" style="color:var(--soft);font-weight:600"></small></label><input class="f" id="val" type="number" step="0.01" inputmode="decimal">
   <label class="q">${t("how_taken")}</label>
   ${cb("fasting","c_fasting")}${cb("poor_sleep","c_poor_sleep")}${cb("biotin","c_biotin")}${cb("thyroid_med","c_thyroid_med")}${sex==="female"?cb("pill","c_pill")+cb("pregnant","c_pregnant"):""}${cb("exercise","c_exercise")}${cb("sick","c_sick")}${cb("caffeine","c_caffeine")}${cb("stress_day","c_stress_day")}
   <label class="q">${t("c_time")}</label><input class="f" type="time" id="tm" value="08:00" style="max-width:180px">
   ${sex==="female"?`<label class="q">${t("c_cycle_day")}</label><input class="f" type="number" id="cd" min="1" max="60" style="max-width:140px">`:""}
   <p><button class="btn coral" id="chk">${t("check_result")}</button></p></div><div id="res"></div>${hist ? `<h2>${t("past_results")}</h2>${hist}` : ""}`);
  const setR = () => { const v = L[$("#test").value]; $("#rng").textContent = `(${t("normal_range")}: ${v.ref[0]}–${v.ref[1]} ${v.unit})`; };
  $("#test").onchange = setR; setR();
  $("#chk").onclick = async () => {
    const v = parseFloat($("#val").value); if (isNaN(v)) return $("#val").focus();
    const g = k => !!$("#c_" + k)?.checked, ctx = {};
    ["fasting","poor_sleep","biotin","thyroid_med","pill","pregnant","exercise","sick","caffeine","stress_day"].forEach(k => ctx[k] = g(k));
    ctx.hour = parseInt(($("#tm").value || "08:00").split(":")[0]); if ($("#cd")?.value) ctx.cycle_day = +$("#cd").value;
    const r = await api("labs", {uid: S.uid, test: $("#test").value, value: v, ctx}); S.state = r.state; const x = r.result;
    const col = x.trust_score >= 80 ? "var(--g)" : x.trust_score >= 50 ? "var(--y)" : "var(--r)";
    const el = $("#res"); el.innerHTML = `<div class="card"><b>${esc(x.name)}</b><div class="big">${x.value} <small style="font-size:16px">${esc(x.unit)}</small></div>
      <span class="pill ${x.status==="normal"?"":"y"}">${t(x.status)}</span> ${esc(x.meaning)}<br><small>${t("normal_range")}: ${x.ref[0]}–${x.ref[1]}${x.personal ? ` · ${t("your_usual")}: ${x.personal.low}–${x.personal.high}` : ""}</small>
      <label class="q">${t("trust")}</label><div class="meter"><i style="width:${x.trust_score}%;background:${col}"></i></div><b>${esc(x.trust)}</b></div>
      ${x.conflicts.map(c => `<div class="conf ${c.severity}"><b>${c.severity==="warn"?"⚠️":"ℹ️"} ${esc(c.title)}</b>${esc(c.why)}<small><b style="display:inline">${t("todo")}:</b> ${esc(c.todo)}</small></div>`).join("")}`;
    await localize(el); el.scrollIntoView({behavior:"smooth"});
  };
}

async function summary() {
  await view(`<h1>📋 ${t("sum_title")}</h1><p class="sub">${t("sum_sub")}</p><div id="sm" class="skel">…</div>`);
  const r = await api("summary", {uid: S.uid}), p = r.plan;
  const h = `<div class="card" id="smcard">${r.summary.map(([h,b]) => `<div class="sumsec"><h3>${esc(h)}</h3><p>${esc(b)}</p></div>`).join("")}</div>
   <h2>🌿 ${t("plan_title")}</h2>${p.items.map(i => `<div class="card"><b>${i.icon} ${esc(i.title)}</b><ul>${i.tips.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`).join("")}
   <div class="card alert"><b>🩺 ${t("see_doctor")}</b><ul>${p.see_doctor_if.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div><p class="disc">${esc(p.note)}</p>
   <p class="noprint"><button class="btn" onclick="window.print()">🖨️ ${t("print")}</button> <button class="btn alt" id="rd">🔊 ${t("read")}</button> <button class="btn alt" id="cp">📋 ${t("copy")}</button></p>`;
  $("#sm").outerHTML = `<div id="sm">${h}</div>`; await localize($("#sm"));
  $("#rd").onclick = () => speak($("#sm").innerText); $("#cp").onclick = () => navigator.clipboard.writeText($("#sm").innerText).then(() => toast(t("copied")));
}

async function chat() {
  const sugg = ["How am I doing?", "What is thyroid?", "Why are my periods late?", "Can I trust my lab result?"];
  await view(`<h1>💬 ${t("chat_title")}</h1><div class="card"><div class="chat" id="log"></div>
   <p class="sub" style="margin:10px 0 4px">${t("try_ask")}</p><div class="chips" id="sg">${sugg.map(s => `<button class="chip">${s}</button>`).join("")}</div>
   <div class="inputrow"><input class="f" id="msg" placeholder="${t("chat_ph")}"><button class="mic" id="mic">🎤</button><button class="btn small" id="snd">${t("send")}</button></div></div><p class="disc">${t("disclaimer")}</p>`);
  const log = $("#log"); if (!S.chat.length) S.chat.push({r:"bot", x:t("chat_hi"), raw:true});
  S.chat.forEach(m => bubble(m));
  document.querySelectorAll("#sg .chip").forEach(c => c.onclick = () => send(c.textContent));
  $("#snd").onclick = () => { const v = $("#msg").value.trim(); if (v) { $("#msg").value = ""; send(v); } };
  $("#msg").onkeydown = e => { if (e.key === "Enter") $("#snd").click(); };
  $("#mic").onclick = () => listen($("#mic"), txt => send(txt));
  if (S.pending) { const q = S.pending; S.pending = null; send(q); }
}
function bubble(m) {
  const d = document.createElement("div"); d.className = "msg " + (m.r === "me" ? "me" : "bot");
  d.innerHTML = esc(m.x) + (m.r === "bot" ? ` <button title="Read aloud">🔊</button>` : "");
  if (m.r === "bot") { d.querySelector("button").onclick = () => speak(d.firstChild.textContent); if (!m.raw && !m.done) localize(d); }
  $("#log").appendChild(d); $("#log").scrollTop = 1e6; return d;
}
async function send(text) {
  S.chat.push({r:"me", x:text}); bubble({r:"me", x:text});
  let en = text;
  if (S.lang !== "en") en = (await translateTexts([text], "en", S.lang))[0];   // user's language -> English for the brain
  const r = await api("chat", {uid: S.uid, message: en});
  const m = {r:"bot", x:r.reply}; S.chat.push(m);
  const d = bubble(m); await localize(d); m.x = d.firstChild.textContent; m.done = true;
}

async function settings() {
  const p = S.state.profile;
  await view(`<h1>⚙️ ${t("set_title")}</h1><div class="card"><label class="q">${t("name")}</label><input class="f" id="n" value="${esc(p.name)}">
   <label class="q">${t("age")}</label><input class="f" id="a" type="number" value="${p.age || ""}"><label class="q">${t("sex")}</label>
   <select class="f" id="sx">${["female","male","other"].map(s => `<option value="${s}" ${p.sex===s?"selected":""}>${t(s)}</option>`).join("")}</select>
   <p><button class="btn" id="sv">${t("save")}</button></p></div>
   <div class="card"><button class="btn alt" id="dm">🧪 ${t("sample")}</button> <button class="btn alt" id="rs">${t("reset")}</button> <button class="btn alt" id="dl" style="color:var(--r)">${t("del")}</button></div>`);
  $("#sv").onclick = async () => { await api("profile", {uid:S.uid, name:$("#n").value, age:+$("#a").value||null, sex:$("#sx").value, lang:S.lang}); S.state = null; toast("✅"); location.hash = "home"; route(); };
  $("#dm").onclick = async () => { S.state = await api("demo", {uid:S.uid}); toast("✅"); location.hash = "home"; };
  $("#rs").onclick = async () => { await api("reset", {uid:S.uid}); S.state = await api("state?uid=" + S.uid); toast("✅"); location.hash = "home"; };
  $("#dl").onclick = async () => { if (confirm("Delete everything?")) { await api("delete", {uid:S.uid}); localStorage.removeItem("uid"); S.uid = ""; S.state = null; route(); } };
}

(async () => { S.cfg = await api("config"); await chrome(); route(); })();
