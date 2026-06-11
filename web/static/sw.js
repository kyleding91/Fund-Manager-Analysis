/* Value Flow service worker — makes the site installable and usable offline.
   The CACHE name below is a placeholder: build_site.py stamps a unique version
   into the deployed copy on every build, so each deploy discards old caches. */
const CACHE = "valueflow-v1";

// Core shell precached on install. Relative to the SW location (site root).
const CORE = [
  "index.html",
  "moves.html",
  "funds.html",
  "stocks.html",
  "methodology.html",
  "manifest.webmanifest",
  "assets/style.css",
  "assets/app.js",
  "assets/icon-192.png",
  "assets/icon-512.png",
  "assets/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) {
    return; // let the browser handle non-GET / cross-origin (e.g. fonts, CDN)
  }

  // Page navigations: network first, and REVALIDATE with the server
  // (cache: "no-cache") so a CDN/browser HTTP-cached copy from minutes ago
  // can't serve a stale page right after a deploy. Falls back to the offline
  // cache only when the network is unreachable.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req, { cache: "no-cache" })
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() =>
          caches.match(req).then((hit) => hit || caches.match("index.html"))
        )
    );
    return;
  }

  // Everything else (css/js/icons/csv): cache-first, then fill the cache.
  event.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ||
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
    )
  );
});
