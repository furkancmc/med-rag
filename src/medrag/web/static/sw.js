/* medrag service worker.
   - /static/*: önce önbellek (arka planda güncellenir)
   - sayfalar (HTML gezinmeleri): önce ağ, olmazsa önbellek, o da yoksa çevrimdışı sayfası
   - /api/*, /chat, GET dışındaki istekler ve başka kökenler: ASLA önbelleğe alınmaz / yakalanmaz
   Sürüm değişince eski önbellekler silinir. */
const VERSION = "v2";
const STATIC_CACHE = "medrag-static-" + VERSION;
const PAGE_CACHE = "medrag-pages-" + VERSION;
const PRECACHE = [
  "/static/base.css", "/static/common.js", "/static/chat.css", "/static/chat.js",
  "/static/about.css", "/static/about.js", "/static/icons/icon.svg", "/static/icons/icon-192.png",
];
const OFFLINE_HTML =
  '<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
  "<title>Çevrimdışı</title><body style=\"font:16px system-ui;padding:24px;max-width:480px;margin:auto\">" +
  "<h1>Bağlantı yok</h1><p>Sağlık Asistanı için internet bağlantısı gerekir. Bağlanınca tekrar deneyin.</p>" +
  "<p><strong>Acil durumda 112'yi arayın.</strong></p></body></html>";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((c) => Promise.all(PRECACHE.map((u) => c.add(u).catch(() => null)))).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => ![STATIC_CACHE, PAGE_CACHE].includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/chat" || url.pathname === "/health") return;

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const hit = await cache.match(req);
        const refresh = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => null);
        return hit || (await refresh) || Response.error();
      })
    );
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) { const copy = res.clone(); caches.open(PAGE_CACHE).then((c) => c.put(req, copy)); }
          return res;
        })
        .catch(async () => (await caches.match(req)) || new Response(OFFLINE_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } }))
    );
  }
});
