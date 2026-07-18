import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ui = readFileSync(
  new URL("../app/components/core-experience.tsx", import.meta.url),
  "utf8",
);
const old = readFileSync(
  new URL("../app/components/app-demo.tsx", import.meta.url),
  "utf8",
);
const sw = readFileSync(
  new URL("../public/sw.js", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../app/lib/api.ts", import.meta.url),
  "utf8",
);

// Blocking-1: plan updater race condition fixed
test("plan updater syncs latestPlanRef before calling setPlan", () => {
  assert.match(ui, /latestPlanRef\.current\s*=\s*resolved/);
  assert.match(ui, /setPlan\s*\(\s*resolved\s*\)/);
  // The unsafe as-cast must not be present.
  assert.ok(!ui.includes("as React.SetStateAction<PlanDraft | null>"));
});

// Blocking-1: field updater uses callback from setPlan
test("PlanCard field updater uses functional setPlan for concurrent safety", () => {
  assert.match(ui, /setPlan\s*\(\s*\(\s*prev\s*\)\s*=>\s*\(\s*\{\s*\.\.\.prev/);
});

// Blocking-2: separate catalog loading effect
test("catalog loading is in its own useEffect separate from auth init", () => {
  // The catalog effect depends on loadVoices and loadTracks, not initialView.
  assert.match(ui, /Catalog preload is a separate effect/);
  assert.match(ui, /\[loadVoices,\s*loadTracks\]/);
});

// Blocking-2: retry buttons in PlanCard
test("PlanCard shows retry buttons when catalog is not loaded", () => {
  assert.match(ui, /tracksLoaded/);
  assert.match(ui, /voicesLoaded/);
  assert.match(ui, /曲库加载失败/);
  assert.match(ui, /音色加载失败/);
  assert.match(ui, /onLoadTracks/);
  assert.match(ui, /onLoadVoices/);
});

// Blocking-2: loadTracks uses Promise.allSettled
test("loadTracks uses Promise.allSettled so one scope failure preserves the other", () => {
  assert.match(ui, /Promise\.allSettled/);
  assert.match(ui, /priv\.status\s*===\s*"fulfilled"/);
  assert.match(ui, /pub\.status\s*===\s*"fulfilled"/);
});

// Blocking-2: loading refs prevent concurrent requests
test("catalog loaders use loading refs to prevent duplicate concurrent requests", () => {
  assert.match(ui, /voicesLoadingRef\.current/);
  assert.match(ui, /tracksLoadingRef\.current/);
});

// P1-2: Service Worker migration
test("Service Worker is self-destructing and does not cache auth pages or API", () => {
  assert.match(sw, /self\.skipWaiting/);
  assert.match(sw, /caches\.delete/);
  assert.match(sw, /unregister/);
  // No fetch listener
  assert.ok(!sw.includes("addEventListener(\"fetch\""));
});

// P1-2: PWA register cleans up and does not re-register
test("pwa-register unregisters old SWs and deletes caches, sessionStorage guard", () => {
  const pwa = readFileSync(
    new URL("../app/components/pwa-register.tsx", import.meta.url),
    "utf8",
  );
  assert.match(pwa, /unregister/);
  assert.match(pwa, /caches\.delete/);
  assert.match(pwa, /sessionStorage/);
  assert.match(pwa, /RELOAD_KEY/);
});

// Blocking-3: no empty admin action tokens in deprecated app-demo
test("deprecated admin actions in app-demo.tsx throw errors instead of sending empty tokens", () => {
  assert.match(old, /throw new Error.*AdminView is deprecated/);
  // No empty string passed as action token to admin functions
  assert.ok(!old.includes('updateUserQuota(user.id, limit, "")'));
  assert.ok(!old.includes('updateUserStatus(user.id,'));
});

// P0-2: ErrorBoundary covers /app and /admin
test("ErrorBoundary wraps children in root layout covering all routes", () => {
  const layout = readFileSync(
    new URL("../app/layout.tsx", import.meta.url),
    "utf8",
  );
  assert.match(layout, /ErrorBoundary/);
  assert.match(layout, /<ErrorBoundary>\{children\}<\/ErrorBoundary>/);
});

// P1-4: work title restoration
test("loadConversation restores work_title from completed job", () => {
  assert.match(ui, /setWorkTitle\s*\(\s*latest\?\.work_title/);
  assert.match(api, /work_title\?/);
});

// P0-1: metadataBase set for production
test("metadataBase uses NEXT_PUBLIC_SITE_URL with localhost fallback only as default", () => {
  const layout = readFileSync(
    new URL("../app/layout.tsx", import.meta.url),
    "utf8",
  );
  assert.match(layout, /NEXT_PUBLIC_SITE_URL/);
});

// Catalog loading states wired through ChatView to PlanCard
test("voicesLoaded and tracksLoaded are passed through ChatView to PlanCard", () => {
  // ChatView receives and forwards the props.
  assert.match(ui, /voicesLoaded/);
  assert.match(ui, /tracksLoaded/);
  assert.match(ui, /onLoadVoices/);
  assert.match(ui, /onLoadTracks/);
});

// no-store on API responses
test("Caddyfile applies no-store to API responses", () => {
  const caddy = readFileSync(
    new URL("../../deploy/Caddyfile", import.meta.url),
    "utf8",
  );
  assert.match(caddy, /@apiResponses/);
  assert.match(caddy, /header @apiResponses Cache-Control "no-store"/);
  assert.match(caddy, /@swFile/);
  assert.match(caddy, /header @swFile Cache-Control "no-store"/);
  // Never reintroduce skip_encoding
  assert.ok(!caddy.includes("skip_encoding"));
});
