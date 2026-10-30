// Sheltie's service worker: lets the installed app open without a connection.
// Pages and built files are cached as they load. The API (/api/...) is never cached: the dashboard
// keeps its own last known snapshot and shows its age, so stale data is never passed off as live.
const CACHE = "sheltie-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

function keep(request, response) {
  if (response.ok) {
    const copy = response.clone();
    caches.open(CACHE).then((cache) => cache.put(request, copy));
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.includes("/api/")) return;

  // Built files have a content hash in their name and never change: cache first.
  if (url.pathname.includes("/_next/static/")) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request).then((response) => keep(request, response))));
    return;
  }

  // Pages, icons and the manifest: network first, so updates show up right away; the cache is the fallback.
  event.respondWith(
    fetch(request)
      .then((response) => keep(request, response))
      .catch(() => caches.match(request).then((hit) => hit || caches.match(new URL("./", self.registration.scope).href))),
  );
});
