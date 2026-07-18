"use client";

import { useEffect } from "react";

export function PwaRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    // One-shot migration: delete all AIMusicMed caches, unregister any
    // existing Service Worker, then reload the page exactly once if it was
    // still under SW control (e.g. the old broken v1 worker).
    //
    // We do NOT register a replacement worker.  A proper caching strategy
    // will be designed and tested separately.
    const RELOAD_KEY = "aimusicmed:sw-migrated";
    let cancelled = false;

    void (async () => {
      try {
        // 1. Delete aimusicmed-* Cache Storage entries.
        const keys = await caches.keys();
        await Promise.all(
          keys
            .filter((k) => k.startsWith("aimusicmed-"))
            .map((k) => caches.delete(k)),
        );

        // 2. Unregister all existing workers for our origin.
        const registrations =
          await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.map((r) => r.unregister()));
      } catch {
        // Best-effort cleanup — never crash the page.
      }
      if (cancelled) return;

      // 3. If the page is still controlled by an old worker, reload once
      //    so the new worker-less page takes over.  Use sessionStorage to
      //    prevent an infinite reload loop.
      if (
        navigator.serviceWorker.controller &&
        !sessionStorage.getItem(RELOAD_KEY)
      ) {
        sessionStorage.setItem(RELOAD_KEY, "1");
        window.location.reload();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
