import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ui = readFileSync(
  new URL("../app/components/core-experience.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../app/lib/api.ts", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("../app/globals.css", import.meta.url),
  "utf8",
);

test("conversation stays in a venting phase until the user asks for a plan", () => {
  assert.match(ui, /我说完了，为我规划音乐冥想/);
  assert.match(ui, /开始生成音乐冥想/);
  assert.match(ui, /if \(plan\) await updatePlanDraft/);
  assert.match(api, /\/conversations\/\$\{conversationId\}\/plan-draft/);
});

test("composer sends on Enter and keeps Shift Enter for a new line", () => {
  assert.match(ui, /event\.key === "Enter"/);
  assert.match(ui, /!event\.shiftKey/);
  assert.match(ui, /!event\.nativeEvent\.isComposing/);
  assert.match(ui, /event\.preventDefault\(\)/);
});

test("job progress uses real events and supports both recovery paths", () => {
  assert.match(ui, /latest\?\.current/);
  assert.match(ui, /latest\.total/);
  assert.match(ui, /已用时/);
  assert.match(ui, /按原方案重试/);
  assert.match(ui, /修改方案后重试/);
  assert.doesNotMatch(ui, /预计剩余/);
});

test("history has search, date groups, soft delete, restore and rename", () => {
  assert.match(ui, /搜索你的会话/);
  assert.match(ui, /最近 7 天/);
  assert.match(ui, /updateConversation/);
  assert.match(ui, /deleteConversation/);
  assert.match(ui, /restoreConversation/);
  assert.match(api, /\?trash=true/);
  assert.match(ui, /收藏作品/);
  assert.match(api, /\?favorites_only=true/);
});

test("one global audio element provides real seeking and persistent position", () => {
  const audioElements = ui.match(/<audio/g) ?? [];
  assert.equal(audioElements.length, 1);
  assert.match(ui, /type="range"/);
  assert.match(ui, /audio\.currentTime = value/);
  assert.match(ui, /onPointerCancel/);
  assert.match(ui, /onTouchEnd/);
  assert.match(ui, /aimusicmed:position:/);
  assert.match(ui, /后退 15 秒/);
  assert.match(ui, /前进 15 秒/);
  assert.match(css, /height: 44px/);
  assert.match(ui, /aria-label="播放音乐冥想"/);
});

test("iPhone audio and browser lifecycle have explicit safe fallbacks", () => {
  assert.match(css, /-webkit-touch-callout/);
  assert.match(ui, /iPhone 请使用机身音量键/);
  assert.match(ui, /visibilitychange/);
  assert.match(ui, /aimusicmed:logout/);
  assert.match(ui, /audio\.removeAttribute\("src"\)/);
});

test("locked settings can be copied and guidance values use canonical names", () => {
  assert.match(ui, /copyPlanToNewConversation/);
  assert.match(ui, /onClick=\{onCopy\}/);
  assert.match(ui, /breath_awareness/);
  assert.match(ui, /gentle_companionship/);
  assert.match(ui, /positive_imagery/);
  assert.doesNotMatch(ui, /value="breathing"/);
  assert.doesNotMatch(ui, /value="companion"/);
});

test("logout clears all saved positions and favorite state comes from the job", () => {
  assert.match(ui, /startsWith\("aimusicmed:position:"\)/);
  assert.match(ui, /setWorkFavorite\(Boolean\(latest\?\.is_favorite\)\)/);
  assert.match(ui, /useState\(initialFavorite\)/);
});
