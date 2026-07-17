import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ui = readFileSync(
  new URL("../app/components/operations-console.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../app/lib/api.ts", import.meta.url),
  "utf8",
);
const copy = readFileSync(
  new URL("../app/lib/copy.zh-CN.ts", import.meta.url),
  "utf8",
);

test("voice cloning enforces quota visibility and an explicit authorization record", () => {
  assert.match(ui, /每人最多 3 个/);
  assert.match(ui, /近 30 天克隆次数/);
  assert.match(ui, /上传后立即创建/);
  assert.match(copy, /删除克隆音色时，原始录音也会一并删除/);
  assert.match(api, /\/voices\/clone/);
});

test("private music editor exposes manual emotion metadata and non-destructive controls", () => {
  assert.match(ui, /主要情绪/);
  assert.match(ui, /其他标签/);
  assert.match(ui, /淡入（秒）/);
  assert.match(ui, /淡出（秒）/);
  assert.match(ui, /自动/);
  assert.match(ui, /较轻/);
  assert.match(ui, /标准/);
  assert.match(ui, /较强/);
  assert.match(ui, /敌意/);
  assert.match(ui, /忧郁/);
  assert.match(ui, /焦虑/);
  assert.match(api, /consent_confirmed/);
  assert.match(ui, /本地绘制波形，不分析音乐情绪；原文件不转码/);
  assert.match(api, /\/music-library\/tracks/);
});

test("meditation plans can select the official voice, a private clone, or pure music", () => {
  const core = readFileSync(
    new URL("../app/components/core-experience.tsx", import.meta.url),
    "utf8",
  );
  assert.match(api, /selected_voice_id/);
  assert.match(core, /female-chengshu-jingpin/);
  assert.match(core, /我的音色/);
  assert.match(core, /pure_music/);
});

test("notifications and admin operations have explicit API contracts", () => {
  assert.match(api, /\/notifications/);
  assert.match(ui, /用户与额度/);
  assert.match(ui, /公共曲库/);
  assert.match(ui, /匿名统计/);
  assert.match(ui, /审计日志/);
  assert.match(ui, /备份与恢复/);
});

test("sensitive admin actions require a second email code", () => {
  assert.match(api, /\/admin\/sensitive-actions\/code\/request/);
  assert.match(api, /\/admin\/sensitive-actions\/code\/verify/);
  assert.match(ui, /发送到管理员邮箱的 6 位验证码/);
  assert.match(ui, /SensitiveActionDialog/);
  assert.match(ui, /adjust_user_quota/);
  assert.match(ui, /change_user_status/);
  assert.match(ui, /delete_public_track/);
  assert.match(ui, /cancel_job/);
  assert.match(ui, /delete_work/);
  assert.match(api, /X-Admin-Action-Token/);
});

test("new Simplified Chinese copy lives in a replaceable dictionary", () => {
  assert.match(copy, /export const zhCN/);
  assert.match(copy, /声音与音乐库/);
  assert.match(copy, /管理员控制台/);
});
