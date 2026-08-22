/**
 * Find service worker.
 *
 * Scope is deliberately narrow. This exists to make the app shell survive a
 * dropped connection and to satisfy the installability requirement -- not to
 * cache user data.
 *
 * Hard rule: nothing under /api/ is ever cached, and cross-origin requests are
 * never intercepted. Photos, captions, OCR text, embeddings, and face data are
 * exactly what a local-first tool must not leave lying in a browser cache, and
 * media is served from object storage on another origin.
 */

const VERSION = "find-sw-v1";
const SHELL_CACHE = `${VERSION}-shell`;
const STATIC_CACHE = `${VERSION}-static`;
const OFFLINE_URL = "/offline.html";

// Only assets that exist regardless of the build output. Next.js hashes its
// chunk filenames, so those are cached at runtime instead of precached -- a
// hardcoded chunk list would go stale on the next build and fail the install.
const PRECACHE_URLS = [
  OFFLINE_URL,
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => !key.startsWith(VERSION))
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isStaticAsset(url) {
  return (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname === "/manifest.json" ||
    /\.(?:png|svg|ico|webp|woff2?)$/.test(url.pathname)
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  // Same-origin only. Media comes from object storage on another origin and
  // must not be intercepted, let alone stored.
  if (url.origin !== self.location.origin) {
    return;
  }

  // Never cache the API. A stale gallery or a cached search response is both a
  // correctness bug and a privacy leak.
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(handleNavigation(request));
    return;
  }

  if (isStaticAsset(url)) {
    event.respondWith(handleStaticAsset(request));
  }
});

/**
 * Cache key for a navigation: origin + pathname, query string discarded.
 *
 * Caching the request as-is would key entries by their full URL, and this app
 * puts user input in the query string -- /search?q=<whatever they typed>. That
 * would persist a searchable history of queries in Cache Storage, which is
 * exactly the kind of trace a local-first tool must not leave behind. The
 * pathname is all the offline shell needs, and every route's real data comes
 * from /api/, which is never cached at all.
 */
function navigationCacheKey(request) {
  const url = new URL(request.url);
  return new Request(`${url.origin}${url.pathname}`, { method: "GET" });
}

/**
 * Network-first: the app must never be served a stale shell while online,
 * because the shell is what tells the user whether the backend is reachable.
 */
async function handleNavigation(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(navigationCacheKey(request), response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(navigationCacheKey(request));
    if (cached) {
      return cached;
    }
    const offline = await caches.match(OFFLINE_URL);
    if (offline) {
      return offline;
    }
    return new Response("Offline", {
      status: 503,
      headers: { "Content-Type": "text/plain" },
    });
  }
}

/** Cache-first: Next.js static chunk URLs are content-hashed, so they are immutable. */
async function handleStaticAsset(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response("", { status: 504 });
  }
}
