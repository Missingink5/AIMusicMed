import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import test from "node:test";

const requiredArtifacts = [
  "dist/server/index.js",
  "dist/client/manifest.webmanifest",
  "dist/client/sw.js",
  "dist/client/og.png",
  "dist/.openai/hosting.json",
];

test("production build contains the server and public PWA artifacts", () => {
  for (const path of requiredArtifacts) {
    assert.ok(statSync(path).size > 0, `${path} should be non-empty`);
  }
});

test("PWA manifest keeps the AIMusicMed identity and standalone mode", () => {
  const manifest = JSON.parse(
    readFileSync("dist/client/manifest.webmanifest", "utf8"),
  );
  assert.equal(manifest.name, "AIMusicMed 音乐冥想");
  assert.equal(manifest.short_name, "AIMusicMed");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.lang, "zh-CN");
});
