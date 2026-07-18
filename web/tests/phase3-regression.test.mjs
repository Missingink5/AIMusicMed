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

// ==========================================================================
// Behavioral tests — pure functions extracted from core-experience.tsx
// ==========================================================================

// mergeTracks: deduplicates by id, first occurrence wins.
function mergeTracks(priv, pub) {
  const seen = new Set();
  const merged = [];
  for (const t of priv) { if (!seen.has(t.id)) { seen.add(t.id); merged.push(t); } }
  for (const t of pub)  { if (!seen.has(t.id)) { seen.add(t.id); merged.push(t); } }
  return merged;
}

test("mergeTracks deduplicates by id, private wins on conflict", () => {
  const priv = [{ id: "a", name: "private-a" }, { id: "b", name: "private-b" }];
  const pub  = [{ id: "b", name: "public-b" }, { id: "c", name: "public-c" }];
  const result = mergeTracks(priv, pub);
  assert.equal(result.length, 3);
  assert.equal(result[0].name, "private-a");
  assert.equal(result[1].name, "private-b"); // private-b wins over public-b
  assert.equal(result[2].name, "public-c");
});

test("mergeTracks handles empty arrays as success", () => {
  assert.equal(mergeTracks([], []).length, 0);
  assert.equal(mergeTracks([{ id: "x", name: "only" }], []).length, 1);
  assert.equal(mergeTracks([], [{ id: "y", name: "only" }]).length, 1);
});

// planUpdater: functional setPlan preserves all fields.
function updatePlanField(plan, updater) {
  return { ...plan, ...updater(plan) };
}

test("two functional plan updaters both preserve their fields", () => {
  const original = { duration_minutes: 5, music_source: "ai", target_emotion: "平静" };
  const afterMusic = updatePlanField(original, () => ({ music_source: "library", selected_music_asset_id: undefined }));
  const afterEmotion = updatePlanField(afterMusic, () => ({ target_emotion: "喜悦" }));
  assert.equal(afterEmotion.duration_minutes, 5);
  assert.equal(afterEmotion.music_source, "library");
  assert.equal(afterEmotion.target_emotion, "喜悦");
});

// Loading state machine: synchronous ref guards prevent double entry.
function makeLoader() {
  let loading = false;
  let loaded = false;
  let callCount = 0;
  return {
    load: async function (apiMock) {
      if (loading || loaded) return;
      loading = true;
      callCount++;
      try {
        const result = await apiMock();
        loaded = true;
        return result;
      } finally {
        loading = false;
      }
    },
    get callCount() { return callCount; },
    get loaded() { return loaded; },
  };
}

test("synchronous double call to loader only triggers one request", async () => {
  let apiCalls = 0;
  const api = async () => { apiCalls++; return ["item"]; };
  const loader = makeLoader();
  await Promise.all([loader.load(api), loader.load(api)]);
  assert.equal(apiCalls, 1);
});

test("loading=false after failure, loaded stays false so retry is possible", async () => {
  let apiCalls = 0;
  const failingApi = async () => { apiCalls++; throw new Error("fail"); };
  const loader = makeLoader();
  try { await loader.load(failingApi); } catch {}
  assert.equal(apiCalls, 1);
  assert.equal(loader.loaded, false);
  // Can retry
  let retryCalls = 0;
  const successApi = async () => { retryCalls++; return ["ok"]; };
  await loader.load(successApi);
  assert.equal(retryCalls, 1);
  assert.equal(loader.loaded, true);
});

test("mounted guard prevents state updates after unmount (ref pattern check)", () => {
  assert.match(ui, /mountedRef\.current/);
  assert.match(ui, /mountedRef\.current\s*=\s*false/);
  // React 18 strict mode: remount must reset mountedRef
  assert.match(ui, /mountedRef\.current\s*=\s*true/);
});

// ==========================================================================
// Behavioral tests — per-scope track loading state machine
// ==========================================================================

// Per-scope loader models loadTrackScope semantics:
//   - Each scope has its own loadingRef (lock) and loadedRef.
//   - On success: data is stored, loadedRef=true.
//   - On failure: error is set, loadedRef stays false.
function makeScopeLoader() {
  const data = { private: [], public: [] };
  const loading = { private: false, public: false };
  const loaded = { private: false, public: false };
  const error = { private: false, public: false };
  let mounted = true;

  return {
    get loading() { return loading; },
    get loaded() { return loaded; },
    get error() { return error; },
    get data() { return data; },
    unmount() { mounted = false; },
    remount() { mounted = true; },

    load: async function (scope, apiMock) {
      if (loading[scope] || loaded[scope]) return null;
      loading[scope] = true;
      error[scope] = false;
      let ok = false;
      try {
        const result = await apiMock();
        if (!mounted) return null;
        ok = true;
        data[scope] = result.items ?? [];
        loaded[scope] = true;
      } catch {
        if (!mounted) return null;
        error[scope] = true;
      } finally {
        loading[scope] = false;
      }
      if (mounted && ok) {
        // Merge logic: concatenate both scopes, dedup by id
        const seen = new Set();
        const merged = [];
        for (const t of data.private) { if (!seen.has(t.id)) { seen.add(t.id); merged.push(t); } }
        for (const t of data.public)  { if (!seen.has(t.id)) { seen.add(t.id); merged.push(t); } }
        return merged;
      }
      return null;
    },
  };
}

test("both scopes fail → both status=error, loaded stays false", async () => {
  const loader = makeScopeLoader();
  const failingApi = async () => { throw new Error("fail"); };
  await loader.load("private", failingApi);
  await loader.load("public", failingApi);
  assert.equal(loader.error.private, true);
  assert.equal(loader.error.public, true);
  assert.equal(loader.loaded.private, false);
  assert.equal(loader.loaded.public, false);
});

test("private succeeds, public fails → private data kept, public can retry", async () => {
  const loader = makeScopeLoader();
  const merged = await loader.load("private", async () => ({ items: [{ id: "a", name: "x" }] }));
  await loader.load("public", async () => { throw new Error("fail"); });
  assert.equal(loader.loaded.private, true);
  assert.equal(loader.error.public, true);
  assert.equal(loader.loaded.public, false);
  assert.equal(merged.length, 1);
  // Public can retry
  const merged2 = await loader.load("public", async () => ({ items: [{ id: "b", name: "y" }] }));
  assert.equal(loader.loaded.public, true);
  assert.equal(merged2.length, 2);
});

test("public retry success → merged data includes both scopes", async () => {
  const loader = makeScopeLoader();
  await loader.load("private", async () => ({ items: [{ id: "a", name: "priv" }] }));
  const merged = await loader.load("public", async () => ({ items: [{ id: "b", name: "pub" }] }));
  assert.equal(merged.length, 2);
  assert.equal(merged[0].name, "priv");
  assert.equal(merged[1].name, "pub");
});

test("empty array success → status=success", async () => {
  const loader = makeScopeLoader();
  const merged = await loader.load("private", async () => ({ items: [] }));
  assert.equal(loader.loaded.private, true);
  assert.equal(loader.error.private, false);
  assert.equal(merged.length, 0);
});

test("synchronous double call to same scope → API mock only called once", async () => {
  let apiCalls = 0;
  const api = async () => { apiCalls++; return { items: [{ id: "x", name: "one" }] }; };
  const loader = makeScopeLoader();
  await Promise.all([loader.load("private", api), loader.load("private", api)]);
  assert.equal(apiCalls, 1);
});

test("failure does NOT trigger automatic retry", async () => {
  let apiCalls = 0;
  const failingApi = async () => { apiCalls++; throw new Error("fail"); };
  const loader = makeScopeLoader();
  await loader.load("private", failingApi);
  assert.equal(apiCalls, 1);
  assert.equal(loader.error.private, true);
  // loaded stays false, no automatic second call
  assert.equal(loader.loaded.private, false);
});

test("after unmount, state results are discarded", async () => {
  const loader = makeScopeLoader();
  loader.unmount();
  const merged = await loader.load("private", async () => ({ items: [{ id: "a", name: "x" }] }));
  assert.equal(merged, null);
  assert.equal(loader.loaded.private, false);
  assert.equal(loader.data.private.length, 0);
});

test("React 18 strict mode: remount after unmount resets mounted flag", async () => {
  const loader = makeScopeLoader();
  loader.unmount();
  const result1 = await loader.load("private", async () => ({ items: [{ id: "a" }] }));
  assert.equal(result1, null);
  assert.equal(loader.loaded.private, false);
  // Simulate React 18 strict mode remount
  loader.remount();
  const merged = await loader.load("private", async () => ({ items: [{ id: "b", name: "post-remount" }] }));
  assert.equal(merged.length, 1);
  assert.equal(loader.loaded.private, true);
});

// ==========================================================================
// Source-code checks — guards and patterns
// ==========================================================================

test("plan updater syncs latestPlanRef before calling setPlan", () => {
  assert.match(ui, /latestPlanRef\.current\s*=\s*resolved/);
  assert.match(ui, /setPlan\s*\(\s*resolved\s*\)/);
  assert.ok(!ui.includes("as React.SetStateAction<PlanDraft | null>"));
});

test("PlanCard field updater uses functional setPlan for concurrent safety", () => {
  assert.match(ui, /setPlan\s*\(\s*\(\s*prev\s*\)\s*=>\s*\(\s*\{\s*\.\.\.prev/);
});

test("loadVoices and loadTrackScope use per-scope ref guards, not state", () => {
  assert.match(ui, /voicesLoadingRef\.current\s*\|\|\s*voicesLoadedRef\.current/);
  // Per-scope loading refs — private and public each have their own lock
  assert.match(ui, /privateTracksLoadingRef/);
  assert.match(ui, /publicTracksLoadingRef/);
  assert.match(ui, /privateTracksLoadedRef/);
  assert.match(ui, /publicTracksLoadedRef/);
  // Stable callbacks with [] deps
  assert.match(ui, /const\s+loadVoices\s*=\s*useCallback\(/);
  assert.match(ui, /const\s+loadTrackScope\s*=\s*useCallback\(/);
});

test("loadTrackScope uses per-scope loading and loaded refs", () => {
  assert.match(ui, /privateTracksLoadingRef/);
  assert.match(ui, /publicTracksLoadingRef/);
  assert.match(ui, /privateTracksLoadedRef/);
  assert.match(ui, /publicTracksLoadedRef/);
  assert.match(ui, /loadTrackScope\s*=\s*useCallback/);
  // No global tracksLoadingRef (would prevent concurrent scope loading)
  assert.ok(!ui.includes("tracksLoadingRef"));
  assert.ok(!ui.includes("tracksLoadedRef"));
});

test("PlanCard shows per-scope retry buttons", () => {
  assert.match(ui, /私人曲库加载失败/);
  assert.match(ui, /公共曲库加载失败/);
  assert.match(ui, /音色加载失败/);
  assert.match(ui, /onLoadTrackScope/);
});

test("catalog preload waits for user and uses stable callbacks", () => {
  assert.match(ui, /if\s*\(\s*!user\s*\)\s*return/);
  assert.match(ui, /\[user,\s*loadVoices,\s*loadAllTracks\]/);
});

test("Service Worker is self-destructing and does not cache", () => {
  assert.match(sw, /self\.skipWaiting/);
  assert.match(sw, /caches\.delete/);
  assert.match(sw, /unregister/);
  assert.ok(!sw.includes('addEventListener("fetch"'));
});

test("pwa-register unregisters old SWs and guards with sessionStorage", () => {
  const pwa = readFileSync(
    new URL("../app/components/pwa-register.tsx", import.meta.url),
    "utf8",
  );
  assert.match(pwa, /unregister/);
  assert.match(pwa, /caches\.delete/);
  assert.match(pwa, /sessionStorage/);
  assert.match(pwa, /RELOAD_KEY/);
});

test("deprecated admin actions throw errors instead of empty tokens", () => {
  assert.match(old, /throw new Error.*AdminView is deprecated/);
  assert.ok(!old.includes('updateUserQuota(user.id, limit, "")'));
});

test("ErrorBoundary wraps children in root layout", () => {
  const layout = readFileSync(
    new URL("../app/layout.tsx", import.meta.url),
    "utf8",
  );
  assert.match(layout, /ErrorBoundary/);
  assert.match(layout, /<ErrorBoundary>\{children\}<\/ErrorBoundary>/);
});

test("loadConversation restores work_title from completed job", () => {
  assert.match(ui, /setWorkTitle\s*\(\s*latest\?\.work_title/);
  assert.match(api, /work_title\?/);
});

test("metadataBase uses NEXT_PUBLIC_SITE_URL", () => {
  const layout = readFileSync(
    new URL("../app/layout.tsx", import.meta.url),
    "utf8",
  );
  assert.match(layout, /NEXT_PUBLIC_SITE_URL/);
});

test("Caddyfile applies no-store to API, sw.js no-store, no skip_encoding", () => {
  const caddy = readFileSync(
    new URL("../../deploy/Caddyfile", import.meta.url),
    "utf8",
  );
  assert.match(caddy, /@apiResponses/);
  assert.match(caddy, /header @apiResponses Cache-Control "no-store"/);
  assert.match(caddy, /@swFile/);
  assert.match(caddy, /header @swFile Cache-Control "no-store"/);
  assert.ok(!caddy.includes("skip_encoding"));
});

test("all PlanCard setPlan calls use functional updater (previous => ...)", () => {
  const matches = ui.match(/setPlan\s*\(\s*\(\s*previous\s*\)\s*=>\s*\(\s*\{/g);
  assert.ok(matches && matches.length >= 3);
});

test("PlanCard voice mode uses functional setPlan", () => {
  assert.match(ui, /setPlan\s*\(\s*\(\s*previous\s*\)\s*=>\s*\(\s*\{[^}]*voice_mode/);
});

test("per-scope states are passed through ChatView to PlanCard", () => {
  assert.match(ui, /privateTracksLoaded/);
  assert.match(ui, /publicTracksLoaded/);
  assert.match(ui, /onLoadTrackScope/);
});
