(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const cities = JSON.parse($("cities-data").textContent);
  const track = JSON.parse($("track-data").textContent);
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  let place = store.get("wf-place") || { name: "Colombo", lat: 6.9271, lon: 79.8612 };
  let current = place;

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v);
    }
    for (const c of kids) n.append(c);
    return n;
  }
  const pct = (p) => Math.round(p * 100);
  const day = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });

  // ---------- chips
  function renderChips() {
    const box = $("chips");
    box.replaceChildren(...cities.map((c) => {
      const b = el("button", { class: "chip", type: "button", text: c.name, "aria-pressed": String(c.name === current.name) });
      b.addEventListener("click", () => load({ name: c.name, lat: c.lat, lon: c.lon }));
      return b;
    }));
  }

  // ---------- search
  let timer, items = [];
  const q = $("q"), sug = $("suggest");
  function hideSug() { sug.hidden = true; sug.replaceChildren(); items = []; }
  q.addEventListener("input", () => {
    clearTimeout(timer);
    const v = q.value.trim();
    if (v.length < 2) return hideSug();
    timer = setTimeout(async () => {
      try {
        const r = await fetch("/api/search/?q=" + encodeURIComponent(v));
        const d = await r.json();
        items = d.results || [];
        sug.replaceChildren(...items.map((it, i) => {
          const li = el("li", { role: "option", "aria-selected": String(i === 0) }, el("span", { text: it.name + " " }), el("small", { text: it.region || "" }));
          li.addEventListener("mousedown", (e) => { e.preventDefault(); pick(it); });
          return li;
        }));
        sug.hidden = items.length === 0;
      } catch (e) { hideSug(); }
    }, 250);
  });
  function pick(it) { hideSug(); q.value = ""; load({ name: it.name, lat: it.lat, lon: it.lon }); }
  $("search-form").addEventListener("submit", (e) => { e.preventDefault(); if (items[0]) pick(items[0]); });
  q.addEventListener("blur", () => setTimeout(hideSug, 150));

  $("locate").addEventListener("click", () => {
    if (!navigator.geolocation) return showError("Your browser can't share a location. Search for a place instead.");
    navigator.geolocation.getCurrentPosition(
      (p) => load({ name: "Your location", lat: +p.coords.latitude.toFixed(3), lon: +p.coords.longitude.toFixed(3) }),
      () => showError("Location permission was not given. Search for a place instead."),
      { timeout: 8000, maximumAge: 600000 });
  });

  // ---------- rendering
  function showError(msg) {
    const h = $("hero");
    h.setAttribute("aria-busy", "false");
    h.replaceChildren(el("div", { class: "err", role: "alert", text: msg }));
    $("detail").hidden = true;
  }
  function headline(p) {
    if (p >= 0.75) return "Rain is very likely tomorrow";
    if (p >= 0.5) return "Rain is likely tomorrow";
    if (p >= 0.3) return "A chance of rain tomorrow";
    if (p >= 0.12) return "Probably dry tomorrow";
    return "Dry tomorrow";
  }
  function render(d) {
    const p = d.rain.probability, h = d.rain.heavy_probability;
    const ring = el("div", { class: "ring", style: `--p:${pct(p)};--c:${p >= 0.5 ? "var(--rain)" : "var(--accent)"}`, role: "img", "aria-label": `${pct(p)} percent chance of rain` },
      el("div", {}, el("b", { text: pct(p) + "%" }), el("span", { text: "chance of rain" })));
    const kv = el("div", { class: "kv" },
      el("div", {}, el("small", { text: "Heavy rain (10 mm or more)" }), el("b", { text: pct(h) + "%" }), el("span", { text: `about ${d.rain.expected_mm} mm expected` })),
      el("div", {}, el("small", { text: "Daytime high" }), el("b", { text: `${d.high.value}°C` }), el("span", { text: `likely ${d.high.low}° to ${d.high.high}°` })),
      el("div", {}, el("small", { text: "Overnight low" }), el("b", { text: `${d.low.value}°C` }), el("span", { text: `likely ${d.low.low}° to ${d.low.high}°` })));
    const save = el("button", { class: "ghost", type: "button", text: "★ Save as my place" });
    save.addEventListener("click", () => { place = { name: d.location.name, lat: d.location.lat, lon: d.location.lon }; store.set("wf-place", place); save.textContent = "★ Saved"; });
    const text = el("div", {},
      el("div", { class: "eyebrow", text: `${day(d.date)} · ${d.location.name} · ${d.location.elevation} m` }),
      el("div", { class: "headline" }, document.createTextNode(headline(p)), el("span", { class: "pill", text: d.rain.certainty })),
      el("p", { class: "sub", text: `${pct(p)} in 100 days like this one, it rains 2.5 mm or more. ${d.rain.models_agree} of 3 weather models agree on rain.` }),
      kv, el("div", { class: "actions" }, save));
    $("hero").setAttribute("aria-busy", "false");
    $("hero").replaceChildren(ring, text);

    $("why").replaceChildren(...d.rain.why.map((w) => el("li", {}, el("span", { class: "a " + w.pushes, text: w.pushes === "up" ? "▲" : w.pushes === "down" ? "▼" : "•", "aria-label": w.pushes === "up" ? "raises the rain chance" : w.pushes === "down" ? "lowers the rain chance" : "neutral" }), el("span", { text: w.text }))));
    const labels = { ecmwf_ifs025: "European (ECMWF)", gfs_global: "American (GFS)", icon_global: "German (ICON)" };
    const max = Math.max(5, ...Object.values(d.rain.model_mm));
    $("models").replaceChildren(...Object.entries(d.rain.model_mm).map(([k, v]) =>
      el("div", { class: "m" }, el("span", { text: labels[k] || k }), el("div", { class: "bar" }, el("i", { style: `width:${Math.min(100, (v / max) * 100)}%` })), el("b", { text: v + " mm" }))));
    $("outlook").replaceChildren(...d.outlook.map((o) => el("div", { class: "day" },
      el("small", { text: day(o.date) }), el("b", { text: `${o.high ?? "–"}° / ${o.low ?? "–"}°` }), el("span", { text: `${o.expected_mm} mm` }), el("small", { text: `${o.models_agree} of ${o.models} models say rain` }))));
    $("detail").hidden = false;
    $("proof").hidden = false;
    $("score").hidden = true;
    document.title = `${pct(p)}% rain tomorrow in ${d.location.name}`;
    maybeAlert(d);
  }

  function renderTrack() {
    const t = track;
    const stat = (big, small) => el("div", { class: "stat" }, el("b", { text: big }), el("small", { text: small }));
    $("stats").replaceChildren(
      stat(`${Math.round(t.skill * 100)}% better`, `rain forecasts beat the "usual weather for this month" baseline (Brier ${t.rain_brier} vs ${t.rain_brier_climatology}, lower is better)`),
      stat(`${t.high_mae}°C vs ${t.high_mae_raw}°C`, "average error of tomorrow's high: ours vs the raw weather models"),
      stat(`${t.low_mae}°C vs ${t.low_mae_raw}°C`, "average error of tomorrow's low: ours vs the raw weather models"),
      stat(`${t.holdout_days.toLocaleString()} test days`, `from ${t.cities} places, ${t.holdout}. The model never saw these days in training.`));
    const rel = el("div", { class: "stat", style: "grid-column:1/-1" }, el("small", { text: 'When we said X% chance of rain, how often did it rain? (blue = what we said, green = what happened)' }));
    const bars = el("div", { class: "rel", style: "margin-bottom:22px", role: "img", "aria-label": "Calibration chart: predicted versus actual rain frequency" });
    t.reliability.forEach((r) => { bars.append(el("i", { style: `height:${Math.max(3, r.said * 100)}%`, "data-l": `${pct(r.said)}%` }), el("i", { class: "truth", style: `height:${Math.max(3, r.happened * 100)}%`, "data-l": "" })); });
    rel.append(bars);
    $("stats").append(rel);
  }

  $("load-score").addEventListener("click", async () => {
    const box = $("score"), btn = $("load-score");
    btn.disabled = true; btn.textContent = "Checking the last 30 days…";
    try {
      const r = await fetch(`/api/scorecard/?lat=${current.lat}&lon=${current.lon}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Scorecard unavailable");
      const dots = el("div", { class: "dots", role: "list" }, ...d.rows.map((x) => {
        const hit = (x.p_rain >= 0.5) === x.rained;
        return el("div", { class: `dot ${x.rained ? "rain" : ""} ${hit ? "hit" : "miss"}`, role: "listitem", title: `${day(x.date)}: we said ${pct(x.p_rain)}% rain, ${x.rained ? "it rained" : "it stayed dry"} (${x.mm} mm). High forecast ${x.high_pred}°, actual ${x.high_actual}°.`, text: String(new Date(x.date + "T12:00:00").getDate()) });
      }));
      box.replaceChildren(
        el("p", { text: `For ${current.name}, over the last ${d.days} days with a known outcome, the call "rain or no rain" was right on ${d.right_calls} days. Average error of the daytime high: ${d.high_mae}°C.` }),
        dots,
        el("p", { class: "fine", text: "Filled blue day = it rained 2.5 mm or more. Green outline = our call was right, red outline = we missed it. Hover or tap a day for details. " + d.note }));
      box.hidden = false;
    } catch (e) {
      box.replaceChildren(el("div", { class: "err", text: e.message })); box.hidden = false;
    } finally { btn.disabled = false; btn.textContent = "Refresh the last 30 days"; }
  });

  // ---------- alerts (browser-only)
  const aOn = $("alert-on"), aTh = $("alert-th");
  const al = store.get("wf-alert") || { on: false, th: 60 };
  aOn.checked = al.on; aTh.value = String(al.th);
  function saveAlert() { store.set("wf-alert", { on: aOn.checked, th: +aTh.value }); }
  aOn.addEventListener("change", async () => {
    if (aOn.checked && "Notification" in window && Notification.permission === "default") await Notification.requestPermission();
    saveAlert();
  });
  aTh.addEventListener("change", saveAlert);
  function maybeAlert(d) {
    const a = store.get("wf-alert");
    if (!a || !a.on || !("Notification" in window) || Notification.permission !== "granted") return;
    const saved = store.get("wf-place");
    if (!saved || saved.name !== d.location.name) return;
    if (d.rain.probability * 100 >= a.th) new Notification(`Rain likely tomorrow in ${d.location.name}`, { body: `${pct(d.rain.probability)}% chance of rain (2.5 mm or more).` });
  }

  // ---------- load
  async function load(p) {
    current = p;
    renderChips();
    $("hero").setAttribute("aria-busy", "true");
    $("hero").replaceChildren(el("div", { class: "skeleton", text: `Forecasting ${p.name}…` }));
    try {
      const r = await fetch(`/api/forecast/?lat=${p.lat}&lon=${p.lon}&name=${encodeURIComponent(p.name)}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Forecast unavailable");
      render(d);
    } catch (e) { showError(e.message); }
  }

  renderChips(); renderTrack(); load(place);
})();
