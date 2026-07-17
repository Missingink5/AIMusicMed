"use client";

import { useEffect } from "react";

export function PwaRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    // First, actively unregister any existing Service Worker and delete all
    // caches that match the AIMusicMed pattern.  This gives immediate relief
    // to browsers that already installed the broken v1 worker, even before
    // the new self-destructing sw.js activates.
    let cancelled = false;
    void (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(
          keys
            .filter((k) => k.startsWith("aimusicmed-"))
            .map((k) => caches.delete(k)),
        );

        const registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(
          registrations.map((r) => r.unregister()),
        );
      } catch {
        // Best-effort cleanup — never crash the app.
      }
      if (cancelled) return;

      // Register the new v2 worker.  It will self-unregister after cleaning
      // up any remaining cache entries on the next activation.
      try {
        navigator.serviceWorker.register("/sw.js");
      } catch {
        // Registration failed — page still works without SW.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
