"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Brand } from "../components/brand";
import { ThemeToggle } from "../components/theme-toggle";
import { api } from "../lib/api";

type LoginMode = "code" | "password";
type CodeStep = "request" | "verify";
type ResetStep = "request" | "verify" | "password";

export default function LoginPage() {
  const [mode, setMode] = useState<LoginMode>("code");
  const [codeStep, setCodeStep] = useState<CodeStep>("request");
  const [resetStep, setResetStep] = useState<ResetStep | null>(null);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function switchMode(next: LoginMode) {
    setMode(next);
    setCodeStep("request");
    setResetStep(null);
    setCode("");
    setPassword("");
    setError("");
    setNotice("");
  }

  async function requestCode(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.requestLoginCode(email, resetStep ? "password_reset" : "login");
      setNotice("如果该邮箱可以使用 AIMusicMed，验证码已发送。验证码 15 分钟内有效。");
      if (resetStep) setResetStep("verify");
      else setCodeStep("verify");
    } catch {
      setError("请求暂时无法完成，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.verifyLoginCode(
        email,
        code,
        resetStep ? "password_reset" : "login",
      );
      if (resetStep) {
        if (!result.reset_token) throw new Error("missing reset token");
        setResetToken(result.reset_token);
        setResetStep("password");
        setCode("");
      } else {
        const setup = result.password_setup ?? "none";
        window.location.replace(`/app?password-setup=${setup}`);
      }
    } catch {
      setError("验证码无效、已过期或尝试次数过多");
    } finally {
      setBusy(false);
    }
  }

  async function loginWithPassword(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.loginWithPassword(email, password);
      window.location.replace("/app");
    } catch {
      setError("邮箱或密码不正确，或账号暂不可用");
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(event: FormEvent) {
    event.preventDefault();
    if (password !== passwordConfirmation) {
      setError("两次输入的密码不一致");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.resetPassword({
        reset_token: resetToken,
        password,
        password_confirmation: passwordConfirmation,
      });
      setResetStep(null);
      setMode("password");
      setPassword("");
      setPasswordConfirmation("");
      setNotice("密码已重设，请使用新密码登录。其他设备上的登录已失效。");
    } catch {
      setError("密码重设失败，请重新获取验证码");
    } finally {
      setBusy(false);
    }
  }

  const isReset = resetStep !== null;
  const isCodeVerify = (!isReset && codeStep === "verify") || resetStep === "verify";

  return (
    <main className="auth-page">
      <header>
        <Link href="/"><Brand /></Link>
        <ThemeToggle />
      </header>
      <section className="auth-card">
        <span className="auth-mark"><Brand compact /></span>
        <h1>{isReset ? "重设登录密码" : "欢迎回来"}</h1>
        <p>
          {isReset
            ? "使用受邀邮箱验证身份后设置新密码。"
            : "仅管理员和受邀邮箱可以登录 AIMusicMed。"}
        </p>

        {!isReset && (
          <div className="auth-tabs" role="tablist" aria-label="登录方式">
            <button type="button" role="tab" aria-selected={mode === "code"} className={mode === "code" ? "active" : ""} onClick={() => switchMode("code")}>验证码登录</button>
            <button type="button" role="tab" aria-selected={mode === "password"} className={mode === "password" ? "active" : ""} onClick={() => switchMode("password")}>密码登录</button>
          </div>
        )}

        {notice && <div className="auth-notice" role="status">{notice}</div>}
        {error && <div className="form-error" role="alert">{error}</div>}

        {(!isReset && mode === "code" && codeStep === "request") || resetStep === "request" ? (
          <form onSubmit={requestCode}>
            <label htmlFor="email">邮箱</label>
            <input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required />
            <button className="button" type="submit" disabled={busy}>{busy ? "正在发送…" : "获取 6 位验证码"}</button>
          </form>
        ) : null}

        {isCodeVerify && (
          <form onSubmit={verifyCode}>
            <label htmlFor="code">邮箱中的 6 位验证码</label>
            <input className="code-input" id="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} placeholder="000000" required />
            <button className="button" type="submit" disabled={busy || code.length !== 6}>{busy ? "正在验证…" : resetStep ? "验证并继续" : "登录"}</button>
            <button className="text-button" type="button" onClick={() => { setCode(""); setNotice(""); if (resetStep) setResetStep("request"); else setCodeStep("request"); }}>换一个邮箱或重新获取</button>
          </form>
        )}

        {!isReset && mode === "password" && (
          <form onSubmit={loginWithPassword}>
            <label htmlFor="password-email">邮箱</label>
            <input id="password-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required />
            <label htmlFor="password">密码</label>
            <input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            <button className="button" type="submit" disabled={busy}>{busy ? "正在登录…" : "登录"}</button>
            <button className="text-button" type="button" onClick={() => { setResetStep("request"); setError(""); setNotice(""); }}>忘记密码</button>
          </form>
        )}

        {resetStep === "password" && (
          <form onSubmit={resetPassword}>
            <label htmlFor="new-password">新密码</label>
            <input id="new-password" type="password" autoComplete="new-password" minLength={10} maxLength={72} value={password} onChange={(event) => setPassword(event.target.value)} required />
            <small className="field-help">10–72 个字符，可使用中文、空格或密码短语。</small>
            <label htmlFor="confirm-password">再次输入新密码</label>
            <input id="confirm-password" type="password" autoComplete="new-password" minLength={10} maxLength={72} value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} required />
            <button className="button" type="submit" disabled={busy}>{busy ? "正在保存…" : "重设密码"}</button>
          </form>
        )}

        {isReset && resetStep !== "password" && <button className="text-button" type="button" onClick={() => switchMode("password")}>返回登录</button>}
        <small>登录即表示你已年满 18 岁，并同意<Link href="/legal/terms">用户协议</Link>与<Link href="/legal/privacy">隐私说明</Link>。</small>
      </section>
    </main>
  );
}
