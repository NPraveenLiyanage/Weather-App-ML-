(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const shell = $("shell");
  const STATIC = shell.dataset.static || "/static/";
  const cities = JSON.parse($("cities-data").textContent);
  const track = JSON.parse($("track-data").textContent);
  const store = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v); }
    n.append(...kids);
    return n;
  };
  const pct = (p) => Math.round(p * 100);
  const dayName = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  const clock12 = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };

  let place = store.get("wx-place", { name: "Colombo", lat: 6.9271, lon: 79.8612 });
  let data = null, token = 0, island = null;

  // ------------------------------------------------------------------ background photo (blurred preview, then sharp WebP)
  let manifest = null;
  const manifestReady = fetch(STATIC + "img/sky/manifest.json").then((r) => r.json()).then((m) => { manifest = m; }).catch(() => {});
  let skyKey = "";
  async function setSky(scene, night, previewOnly) {
    await manifestReady;
    shell.classList.toggle("night", !!night);
    const m = manifest && manifest[scene];
    if (!m || skyKey === scene) return;
    skyKey = scene;
    const img = $("sky-img");
    $("sky").style.backgroundImage = `url(${m.lqip})`;
    if (previewOnly) { skyKey = ""; return; }
    img.classList.remove("on");
    const phone = window.matchMedia("(max-width: 700px)").matches;
    const next = new Image();
    next.decoding = "async";
    next.onload = () => { img.src = next.src; requestAnimationFrame(() => img.classList.add("on")); };
    next.src = STATIC + (phone ? m.p : m.l);
  }
  setSky("overcast", false, true); // blurred preview only (no download) while the first forecast loads

  // ------------------------------------------------------------------ status + loading
  let statusTimer;
  function say(msg, err) {
    const s = $("status");
    s.textContent = msg; s.classList.toggle("err", !!err); s.classList.add("show");
    clearTimeout(statusTimer); statusTimer = setTimeout(() => s.classList.remove("show"), err ? 6000 : 2500);
  }

  // ------------------------------------------------------------------ tabs
  const tabs = [...document.querySelectorAll(".tabs [role=tab]")];
  function openTab(name) {
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
    document.querySelectorAll(".view").forEach((v) => { v.hidden = v.id !== "v-" + name; });
    if (name === "island") loadIsland();
    if (name === "now") requestAnimationFrame(drawCurve);
  }
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => openTab(t.dataset.tab));
    t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      n.focus(); openTab(n.dataset.tab);
    });
  });

  // ------------------------------------------------------------------ hourly strip with the orange curve
  let curvePts = [];
  function renderStrip(d) {
    const rows = d.hourly.filter((_, i) => i % 3 === 0).slice(0, 8);
    const list = $("strip-list");
    list.replaceChildren(...rows.map((r) => el("li", {},
      el("p", { class: "f-time", text: r.time }),
      el("p", { class: "f-temp", text: `${r.temp.toFixed(1)}°` }),
      el("span", { class: "f-pop", text: `${r.pop ?? 0}% chance of rain` }),
      el("p", { class: "f-hum", text: `Humidity: ${r.humidity}` }),
      el("p", { class: "f-desc", text: r.text }))));
    curvePts = rows.map((r) => r.temp);
    requestAnimationFrame(drawCurve);
  }
  function drawCurve() {
    const wrap = $("strip"), cv = $("curve"), items = [...document.querySelectorAll("#strip-list li")];
    if (!items.length || wrap.closest(".view").hidden) return;
    const inner = $("strip-list"), w = inner.offsetWidth, h = 64, dpr = Math.min(2, devicePixelRatio || 1);
    cv.style.width = w + "px"; cv.style.height = h + "px"; cv.width = w * dpr; cv.height = h * dpr;
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
    const lo = Math.min(...curvePts), hi = Math.max(...curvePts), span = Math.max(1.5, hi - lo);
    const pts = items.map((li, i) => [li.offsetLeft + li.offsetWidth / 2, h - 10 - ((curvePts[i] - lo) / span) * (h - 24)]);
    c.strokeStyle = "#ffa726"; c.lineWidth = 3; c.lineCap = "round"; c.beginPath();
    pts.forEach((p, i) => {
      if (i === 0) { c.moveTo(p[0], p[1]); return; }
      const q = pts[i - 1], mx = (q[0] + p[0]) / 2; c.bezierCurveTo(mx, q[1], mx, p[1], p[0], p[1]);
    });
    c.stroke();
    c.fillStyle = "#ffa726"; pts.forEach((p) => { c.beginPath(); c.arc(p[0], p[1], 3.5, 0, 7); c.fill(); });
  }
  window.addEventListener("resize", () => requestAnimationFrame(drawCurve));

  // ------------------------------------------------------------------ main render
  function headline(p) {
    if (p >= 0.75) return "Rain is very likely tomorrow";
    if (p >= 0.5) return "Rain is likely tomorrow";
    if (p >= 0.3) return "A chance of rain tomorrow";
    if (p >= 0.12) return "Probably dry tomorrow";
    return "Dry tomorrow";
  }
  function render(d) {
    data = d;
    const n = d.now, r = d.rain;
    shell.classList.remove("is-loading");
    $("title").textContent = n.description;
    $("where").textContent = `${d.location.name} LK ${clock12(n.time)}`;
    $("sunrise").textContent = clock12(d.sun.sunrise); $("sunset").textContent = clock12(d.sun.sunset);
    $("facts").textContent = `Wind ${n.wind_kmh} kilometers per hour. Pressure is ${n.pressure} mb. Visibility is ${n.visibility_km} km. Maximum temperature is ${n.high_today}°. Minimum temperature is ${n.low_today}°.`;
    $("n-temp").textContent = n.temp; $("n-feels").textContent = n.feels; $("n-hum").textContent = n.humidity; $("n-cloud").textContent = n.clouds; $("n-wind").textContent = Math.round(n.wind_kmh);
    const s = $("season"); s.replaceChildren(el("b", { text: d.season.name }), document.createTextNode(d.season.text));
    document.title = `${pct(r.probability)}% rain tomorrow · ${d.location.name}`;
    setSky(n.scene, n.night);

    // Next 24 hours
    const out = $("outlook-line");
    out.replaceChildren(document.createTextNode("Rain outlook for tomorrow: "), el("b", { text: `${pct(r.probability)}% chance` }), document.createTextNode(` (${r.certainty}). Hourly chances below are the raw weather-service numbers.`));
    renderStrip(d);

    // Tomorrow
    $("ring").style.setProperty("--p", pct(r.probability));
    $("ring").style.setProperty("--c", r.probability >= 0.5 ? "var(--blue)" : "var(--orange)");
    $("ring").setAttribute("aria-label", `${pct(r.probability)} percent chance of rain tomorrow`);
    $("ring-p").textContent = pct(r.probability) + "%";
    const head = $("tom-head"); head.replaceChildren(document.createTextNode(headline(r.probability)), el("span", { class: "tag", text: r.certainty }));
    $("tom-sub").textContent = `${dayName(d.date)}. In 100 days like this one, ${pct(r.probability)} bring 2.5 mm or more of rain. ${r.models_agree} of ${r.models_total} weather models agree on rain.`;
    $("kv").replaceChildren(
      el("div", {}, el("small", { text: "Heavy rain (10 mm or more)" }), el("b", { text: pct(r.heavy_probability) + "%" }), el("span", { text: `about ${r.expected_mm} mm expected` })),
      el("div", {}, el("small", { text: "Daytime high" }), el("b", { text: `${d.high.value}°C` }), el("span", { text: `likely ${d.high.low}° to ${d.high.high}°` })),
      el("div", {}, el("small", { text: "Overnight low" }), el("b", { text: `${d.low.value}°C` }), el("span", { text: `likely ${d.low.low}° to ${d.low.high}°` })));
    $("why").replaceChildren(...r.why.map((w) => el("li", {}, el("span", { class: "a " + w.pushes, text: w.pushes === "up" ? "▲" : w.pushes === "down" ? "▼" : "•", "aria-label": w.pushes === "up" ? "raises the rain chance" : w.pushes === "down" ? "lowers the rain chance" : "neutral" }), el("span", { text: w.text }))));
    const label = { ecmwf_ifs025: "European", gfs_global: "American", icon_global: "German", jma_gsm: "Japanese", gem_global: "Canadian", meteofrance_arpege_world: "French", cma_grapes_global: "Chinese", bom_access_global: "Australian" };
    const mm = Object.entries(r.model_mm), mx = Math.max(5, ...mm.map((x) => x[1]));
    $("models-n").textContent = `(${mm.length})`;
    $("models").replaceChildren(...mm.map(([k, v]) => el("div", { class: "m" }, el("span", { text: label[k] || k }), el("div", { class: "bar" }, el("i", { style: `width:${Math.min(100, (v / mx) * 100)}%` })), el("b", { text: v + " mm", style: "font-weight:400" }))));

    // 4 days
    $("week").replaceChildren(...d.outlook.map((o) => el("div", { class: "d" }, el("small", { text: dayName(o.date) }), el("b", { text: `${o.high ?? "–"}° / ${o.low ?? "–"}°` }), el("span", { text: `${o.expected_mm} mm of rain` }), el("em", { text: `${o.models_agree} of ${o.models} models say rain` }))));
    renderProof();
    maybeAlert(d);
    renderFavs();
  }

  // ------------------------------------------------------------------ proof
  function renderProof() {
    const t = track, stat = (b, s) => el("div", { class: "stat" }, el("b", { text: b }), el("small", { text: s }));
    $("stats").replaceChildren(
      stat(`${Math.round(t.skill * 100)}% better`, `rain forecasts beat "the usual weather for this month" (error score ${t.rain_brier} vs ${t.rain_brier_climatology}, lower is better). Tested on the newest months, ${t.rain_holdout}, ${t.rain_holdout_days.toLocaleString()} place-days the model never saw.`),
      stat(`${t.rain_brier} vs ${t.rain_brier_v1}`, `error score with all ${t.rain_models} weather models weighed separately vs the earlier 3-model version, same test days (the 95% range of the gain excludes zero: ${t.rain_gain_ci[0]} to ${t.rain_gain_ci[1]})`),
      stat(`${t.high_mae}°C vs ${t.high_mae_raw}°C`, `average error of tomorrow's high: ours vs the raw weather models. Tested over ${t.temp_holdout_days.toLocaleString()} place-days from ${t.cities} places, ${t.temp_holdout}.`),
      stat(`${t.low_mae}°C vs ${t.low_mae_raw}°C`, "average error of tomorrow's low: ours vs the raw weather models, same 14-month test."));
    const bars = [];
    t.reliability.forEach((r) => { bars.push(el("i", { style: `height:${Math.max(3, r.said * 100)}%`, "data-l": `${pct(r.said)}%` }), el("i", { class: "t", style: `height:${Math.max(3, r.happened * 100)}%`, "data-l": "" })); });
    $("rel").replaceChildren(...bars);
    $("rel").setAttribute("role", "img"); $("rel").setAttribute("aria-label", "Predicted versus actual rain frequency; the bars match closely");
  }
  $("load-score").addEventListener("click", async () => {
    const box = $("score"), btn = $("load-score");
    btn.disabled = true; btn.textContent = "Checking the last 30 days…";
    try {
      const r = await fetch(`/api/scorecard/?lat=${place.lat}&lon=${place.lon}`), d = await r.json();
      if (!r.ok) throw new Error(d.error || "Scorecard unavailable");
      const dots = el("div", { class: "dots", role: "list" }, ...d.rows.map((x) => {
        const hit = (x.p_rain >= 0.5) === x.rained;
        return el("div", { class: `dotd ${x.rained ? "r" : ""} ${hit ? "hit" : "miss"}`, role: "listitem", title: `${dayName(x.date)}: we said ${pct(x.p_rain)}% rain, ${x.rained ? "it rained" : "it stayed dry"} (${x.mm} mm). High forecast ${x.high_pred}°, actual ${x.high_actual}°.`, text: String(new Date(x.date + "T12:00:00").getDate()) });
      }));
      box.replaceChildren(el("p", { text: `For ${place.name}, over the last ${d.days} days with a known outcome, "rain or no rain" was called right on ${d.right_calls} days. Average error of the high: ${d.high_mae}°C.` }), dots, el("p", { class: "fine", text: "Filled blue = it rained 2.5 mm or more. Green outline = right call, red outline = missed. Hover a day for details. " + d.note }));
      box.hidden = false;
    } catch (e) { box.replaceChildren(el("p", { class: "fine", text: e.message })); box.hidden = false; }
    finally { btn.disabled = false; btn.textContent = "Refresh the last 30 days"; }
  });

  // ------------------------------------------------------------------ island map
  const COAST = [[80.23, 9.83], [80.52, 9.66], [80.82, 9.27], [81.0, 8.98], [81.23, 8.57], [81.38, 8.15], [81.7, 7.72], [81.82, 7.4], [81.83, 6.87], [81.68, 6.5], [81.33, 6.2], [81.12, 6.1], [80.8, 6.03], [80.59, 5.92], [80.2, 6.03], [79.96, 6.58], [79.85, 6.93], [79.83, 7.21], [79.8, 7.57], [79.83, 8.03], [79.73, 8.25], [79.88, 8.6], [79.92, 9.0], [79.95, 9.3], [80.2, 9.5], [80.05, 9.82]];
  const X = (lon) => (lon - 79.45) * 100, Y = (lat) => (9.95 - lat) * 100;
  function smoothPath(pts) {
    const p = pts.map(([lo, la]) => [X(lo), Y(la)]), n = p.length; let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
    for (let i = 0; i < n; i++) {
      const p0 = p[(i - 1 + n) % n], p1 = p[i], p2 = p[(i + 1) % n], p3 = p[(i + 2) % n];
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
    }
    return d + "Z";
  }
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const wetColor = (p) => `rgb(${mix([255, 211, 138], [62, 156, 255], Math.min(1, p)).join(",")})`;
  const NS = "http://www.w3.org/2000/svg";
  async function loadIsland() {
    if (!island) {
      $("rank").replaceChildren(el("li", { text: "Forecasting all 16 places…" }));
      try { const r = await fetch("/api/island/"); island = await r.json(); if (!r.ok) throw new Error(island.error); } catch (e) { island = null; $("rank").replaceChildren(el("li", { text: "The island view is unavailable right now." })); return; }
    }
    const svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", "0 0 255 415"); svg.setAttribute("role", "group");
    const land = document.createElementNS(NS, "path"); land.setAttribute("d", smoothPath(COAST)); land.setAttribute("class", "land"); svg.append(land);
    island.cities.forEach((c) => {
      const g = document.createElementNS(NS, "g"); g.setAttribute("tabindex", "0"); g.setAttribute("role", "button"); g.setAttribute("aria-label", `${c.name}: ${pct(c.p)} percent chance of rain tomorrow`);
      const dot = document.createElementNS(NS, "circle"); dot.setAttribute("class", "dot"); dot.setAttribute("cx", X(c.lon)); dot.setAttribute("cy", Y(c.lat)); dot.setAttribute("r", 7); dot.setAttribute("fill", wetColor(c.p));
      const t = document.createElementNS(NS, "text"); t.setAttribute("class", "dotl"); t.setAttribute("x", X(c.lon) + 12); t.setAttribute("y", Y(c.lat) + 4); t.textContent = c.name;
      g.append(dot, t);
      const go = () => { openTab("now"); load({ name: c.name, lat: c.lat, lon: c.lon }); };
      g.addEventListener("click", go); g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
      svg.append(g);
    });
    $("map").replaceChildren(svg);
    const sorted = [...island.cities].sort((a, b) => b.p - a.p);
    $("rank").replaceChildren(...sorted.map((c) => {
      const li = el("li", { class: c.name === place.name ? "cur" : "", tabindex: "0" }, el("span", { text: c.name }), el("b", { text: pct(c.p) + "%", style: "font-weight:400" }), el("div", { class: "bar" }, el("i", { style: `width:${pct(c.p)}%;background:${wetColor(c.p)}` })));
      const go = () => { openTab("now"); load({ name: c.name, lat: c.lat, lon: c.lon }); };
      li.addEventListener("click", go); li.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
      return li;
    }));
  }

  // ------------------------------------------------------------------ search, location, favourites, alerts
  const q = $("q"), sug = $("suggest");
  let timer, items = [];
  const hideSug = () => { sug.hidden = true; sug.replaceChildren(); items = []; };
  q.addEventListener("input", () => {
    clearTimeout(timer);
    const v = q.value.trim();
    if (v.length < 2) return hideSug();
    timer = setTimeout(async () => {
      try {
        const d = await (await fetch("/api/search/?q=" + encodeURIComponent(v))).json();
        items = d.results || [];
        sug.replaceChildren(...items.map((it, i) => { const li = el("li", { role: "option", class: i === 0 ? "on" : "" }, el("span", { text: it.name + " " }), el("small", { text: it.region || "" })); li.addEventListener("mousedown", (e) => { e.preventDefault(); pick(it); }); return li; }));
        sug.hidden = !items.length;
      } catch (e) { hideSug(); }
    }, 250);
  });
  const pick = (it) => { hideSug(); q.value = ""; load({ name: it.name, lat: it.lat, lon: it.lon }); };
  $("search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (items[0]) return pick(items[0]);
    const c = cities.find((x) => x.name.toLowerCase() === q.value.trim().toLowerCase());
    if (c) { q.value = ""; load({ name: c.name, lat: c.lat, lon: c.lon }); } else say("Pick a place from the suggestions.", true);
  });
  q.addEventListener("blur", () => setTimeout(hideSug, 150));
  $("btn-locate").addEventListener("click", () => {
    if (!navigator.geolocation) return say("Your browser can't share a location.", true);
    navigator.geolocation.getCurrentPosition((p) => load({ name: "Your location", lat: +p.coords.latitude.toFixed(3), lon: +p.coords.longitude.toFixed(3) }), () => say("Location permission was not given. Search for a place instead.", true), { timeout: 8000, maximumAge: 600000 });
  });

  const favs = () => store.get("wx-favs", []);
  function renderFavs() {
    const list = favs();
    $("favs").replaceChildren(...(list.length ? list.map((f, i) => {
      const go = el("button", { type: "button", text: f.name }), x = el("button", { type: "button", class: "x", text: "✕", "aria-label": "Remove " + f.name });
      go.addEventListener("click", () => { closeDrawer(); load(f); });
      x.addEventListener("click", () => { const l = favs(); l.splice(i, 1); store.set("wx-favs", l); renderFavs(); });
      return el("li", {}, go, x);
    }) : [el("li", { text: "No saved places yet." })]));
  }
  function saveCurrent() {
    const l = favs();
    if (!l.some((f) => f.name === place.name)) { l.push({ name: place.name, lat: place.lat, lon: place.lon }); store.set("wx-favs", l); say(`Saved ${place.name}`); }
    else say(`${place.name} is already saved.`);
    renderFavs();
  }
  $("btn-save").addEventListener("click", saveCurrent); $("fav-add").addEventListener("click", saveCurrent);
  function openDrawer() { $("drawer").classList.add("open"); $("drawer").setAttribute("aria-hidden", "false"); $("shade").hidden = false; $("btn-settings").setAttribute("aria-expanded", "true"); }
  function closeDrawer() { $("drawer").classList.remove("open"); $("drawer").setAttribute("aria-hidden", "true"); $("shade").hidden = true; $("btn-settings").setAttribute("aria-expanded", "false"); }
  $("btn-settings").addEventListener("click", openDrawer); $("drawer-close").addEventListener("click", closeDrawer); $("shade").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  const al = store.get("wx-alert", { on: false, th: 60 });
  $("alert-on").checked = al.on; $("alert-th").value = String(al.th);
  const saveAlert = () => store.set("wx-alert", { on: $("alert-on").checked, th: +$("alert-th").value });
  $("alert-on").addEventListener("change", async () => { if ($("alert-on").checked && "Notification" in window && Notification.permission === "default") await Notification.requestPermission(); saveAlert(); });
  $("alert-th").addEventListener("change", saveAlert);
  function maybeAlert(d) {
    const a = store.get("wx-alert", null), first = favs()[0];
    if (!a || !a.on || !first || first.name !== d.location.name || !("Notification" in window) || Notification.permission !== "granted") return;
    if (d.rain.probability * 100 >= a.th) new Notification(`Rain likely tomorrow in ${d.location.name}`, { body: `${pct(d.rain.probability)}% chance of rain (2.5 mm or more).` });
  }

  // ------------------------------------------------------------------ share as a picture
  $("btn-share").addEventListener("click", () => {
    if (!data) return;
    const W = 1080, H = 1350, cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    const c = cv.getContext("2d"), img = $("sky-img");
    const paint = () => {
      if (img.complete && img.naturalWidth) { const r = Math.max(W / img.naturalWidth, H / img.naturalHeight), w = img.naturalWidth * r, h = img.naturalHeight * r; c.drawImage(img, (W - w) / 2, (H - h) / 2, w, h); } else { c.fillStyle = "#10181c"; c.fillRect(0, 0, W, H); }
      c.fillStyle = "rgba(0,0,0,.45)"; c.fillRect(0, 0, W, H);
      const r = data.rain; c.fillStyle = "#fff"; c.textAlign = "left";
      c.font = "300 40px Poppins, sans-serif"; c.fillText(`${data.location.name} · ${dayName(data.date)}`, 80, 150);
      c.font = "400 150px Poppins, sans-serif"; c.fillText(`${pct(r.probability)}%`, 80, 400);
      c.font = "300 54px Poppins, sans-serif"; c.fillText("chance of rain tomorrow", 80, 480);
      c.font = "400 68px Poppins, sans-serif"; c.fillText(`${data.high.value}° high · ${data.low.value}° low`, 80, 660);
      c.font = "300 40px Poppins, sans-serif"; c.fillStyle = "rgba(255,255,255,.85)";
      c.fillText(`Heavy rain: ${pct(r.heavy_probability)}%  ·  ${r.certainty}`, 80, 740);
      r.why.forEach((w, i) => c.fillText("• " + w.text, 80, 860 + i * 70));
      c.font = "300 30px Poppins, sans-serif"; c.fillStyle = "rgba(255,255,255,.7)";
      c.fillText("Weather data by Open-Meteo.com (CC BY 4.0), corrected by a machine-learning model.", 80, H - 70);
      cv.toBlob((b) => { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `forecast-${data.location.name.toLowerCase().replace(/\W+/g, "-")}-${data.date}.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); });
    };
    paint();
  });

  // ------------------------------------------------------------------ load
  async function load(p) {
    place = p; store.set("wx-place", p); const my = ++token;
    shell.classList.add("is-loading");
    $("title").textContent = `Forecasting ${p.name}…`;
    try {
      const r = await fetch(`/api/forecast/?lat=${p.lat}&lon=${p.lon}&name=${encodeURIComponent(p.name)}`), d = await r.json();
      if (my !== token) return;
      if (!r.ok) throw new Error(d.error || "Forecast unavailable");
      render(d);
    } catch (e) { if (my !== token) return; shell.classList.remove("is-loading"); $("title").textContent = "Forecast unavailable"; say(e.message, true); }
  }
  renderFavs(); renderProof(); load(place);
})();
