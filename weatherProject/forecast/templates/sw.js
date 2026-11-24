/* Service worker: installable app + fast repeat visits + a usable offline page.
   Cache name carries a build version (from the file timestamps), so a deploy can never leave old JavaScript being served. */
const VERSION = "{{ version }}";
const SHELL = "wx-shell-" + VERSION, IMAGES = "wx-img-v1", API = "wx-api-" + VERSION;

self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== SHELL && k !== IMAGES && k !== API) await caches.delete(k);
    await self.clients.claim();
  })());
});

const withTimeout = (p, ms) => new Promise((res, rej) => { const t = setTimeout(() => rej(new Error("timeout")), ms); p.then((v) => { clearTimeout(t); res(v); }, (e) => { clearTimeout(t); rej(e); }); });

async function networkFirst(req, cacheName, ms) {
  const cache = await caches.open(cacheName);
  try {
    const res = await withTimeout(fetch(req), ms);
    if (res && res.ok) cache.put(req, res.clone());   // never cache error responses
    return res;
  } catch (e) {
    const hit = await cache.match(req);
    if (hit) return hit;
    throw e;
  }
}
async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res && res.ok) cache.put(req, res.clone());
  return res;
}
async function staleWhileRevalidate(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  const net = fetch(req).then((res) => { if (res && res.ok) cache.put(req, res.clone()); return res; }).catch(() => hit);
  return hit || net;
}

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname === "/sw.js") return;
  if (req.mode === "navigate") { e.respondWith(networkFirst(req, SHELL, 4000)); return; }          // HTML: fresh when online, last copy offline
  if (url.pathname.startsWith("/api/")) { e.respondWith(networkFirst(req, API, 12000)); return; }   // data: fresh, stale only if offline
  if (/\.(webp|png|jpe?g|svg|ico)$/.test(url.pathname)) { e.respondWith(cacheFirst(req, IMAGES)); return; }
  if (url.pathname.startsWith("/static/")) { e.respondWith(staleWhileRevalidate(req, SHELL)); return; }
});
