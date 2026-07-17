/* Self-destructing Service Worker — v2.
   This worker exists only to clean up the broken v1 worker that cached
   authenticated pages and cloned already-used response bodies.
   Once old caches are deleted, it unregisters itself so no worker
   intercepts fetch until a proper caching strategy is designed. */

const LEGACY_CACHES = ["aimusicmed-shell-v1"];

self.addEventListener("install", function () {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys
            .filter(function (key) {
              return LEGACY_CACHES.includes(key) || key.startsWith("aimusicmed-");
            })
            .map(function (key) {
              return caches.delete(key);
            }),
        );
      })
      .then(function () {
        return self.registration.unregister();
      }),
  );
});

/* Do NOT intercept any fetch requests. */
