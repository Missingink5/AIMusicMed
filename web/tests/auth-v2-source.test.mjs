import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const login = readFileSync("app/login/page.tsx", "utf8");
const api = readFileSync("app/lib/api.ts", "utf8");
const app = readFileSync("app/components/app-demo.tsx", "utf8");

test("login offers email code and password without legacy link or TOTP flows", () => {
  assert.match(login, /验证码登录/);
  assert.match(login, /密码登录/);
  assert.match(login, /忘记密码/);
  assert.match(login, /15 分钟内有效/);
  assert.doesNotMatch(login, /magic|totp|身份验证器|登录链接/i);
});

test("API client exposes the authentication V2 contract", () => {
  assert.match(api, /\/auth\/code\/request/);
  assert.match(api, /\/auth\/code\/verify/);
  assert.match(api, /\/auth\/password\/login/);
  assert.match(api, /\/auth\/password\/reset/);
  assert.match(api, /\/account\/password/);
  assert.match(api, /password_configured/);
  assert.match(api, /password_setup/);
});

test("account and admin views include password and whitelist controls", () => {
  assert.match(app, /onClick=\{\(\) => setView\("account"\)\}/);
  assert.match(app, />\s*账号\s*<\/button>/);
  assert.match(app, /暂时跳过/);
  assert.match(app, /重发验证码/);
  assert.match(
    app,
    /item\.status === "pending"[\s\S]*?resendCode\(item\)[\s\S]*?item\.status !== "pending"[\s\S]*?toggleUser\(item\)/,
  );
  assert.match(app, /已停用/);
  assert.match(app, /加入并发送验证码/);
  assert.doesNotMatch(app, /邀请链接|accept-invite/);
});

test("admin user table keeps quota before actions", () => {
  const body = app.slice(app.indexOf("<tbody>"), app.indexOf("</tbody>"));
  assert.ok(body.indexOf('className="quota-button"') < body.indexOf('className="admin-actions"'));
});

test("new meditation plans use the premium mature voice while keeping pure music", () => {
  assert.match(app, /value="female-chengshu-jingpin"/);
  assert.match(app, /成熟温柔女声（精品）/);
  assert.match(app, /纯音乐，不要语音/);
  assert.doesNotMatch(app, /female-chengshu(?!-jingpin)/);
});
