"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  AdminUser,
  Conversation,
  Message,
  streamAssistant,
  User,
} from "../lib/api";
import { Brand } from "./brand";
import { ThemeToggle } from "./theme-toggle";

type View = "chat" | "api" | "account" | "admin";
type Plan = {
  emotion: string;
  target: string;
  duration: number;
  source: string;
  voice: string;
  mode: string;
};
const prompts = [
  "刚结束一场重要汇报，我还是很紧张。",
  "今天有点低落，想慢慢找回一点力量。",
  "脑子停不下来，想在睡前安静一会儿。",
  "状态不错，想把这份自信稳定下来。",
];

export function LegacyAppDemo({ initialView = "chat" }: { initialView?: View }) {
  const [view, setView] = useState<View>(initialView);
  const [drawer, setDrawer] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [passwordSetupRequired, setPasswordSetupRequired] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [draft, setDraft] = useState("");
  const [stream, setStream] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageId, setMessageId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [workId, setWorkId] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan>({
    emotion: "焦虑",
    target: "自信",
    duration: 5,
    source: "音乐库",
    voice: "female-chengshu-jingpin",
    mode: "platform",
  });
  const [job, setJob] = useState<"idle" | "running" | "done">("idle");
  const [progress, setProgress] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeJob = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me);
        if (initialView === "admin" && me.role !== "admin") setView("chat");
        const setup = new URLSearchParams(window.location.search).get(
          "password-setup",
        );
        if (me.password_setup === "required" || setup === "required") {
          setPasswordSetupRequired(true);
          setView("account");
          return;
        }
        const history = await api.listConversations();
        if (cancelled) return;
        setConversations(history.items);
        if (history.items[0]) await loadConversation(history.items[0].id);
        if (setup === "optional") setView("account");
      } catch (reason) {
        const apiError = reason as ApiError;
        if (apiError.code === "authentication_required")
          window.location.replace("/login");
        else setError(apiError.message ?? "暂时无法加载账号数据");
      }
    })();
    return () => {
      cancelled = true;
      if (timer.current) clearInterval(timer.current);
    };
    // Initial authenticated bootstrap only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshHistory() {
    const history = await api.listConversations();
    setConversations(history.items);
  }

  async function loadConversation(id: string) {
    setError("");
    try {
      const detail = await api.getConversation(id);
      setConversationId(id);
      const lastUser = [...detail.messages]
        .reverse()
        .find((item) => item.role === "user");
      setMessages(detail.messages);
      setMessageId(lastUser?.id ?? null);
      setStream("");
      setSent(detail.messages.length > 0);
      const latestJob = detail.jobs.at(-1);
      setWorkId(latestJob?.work_id ?? null);
      if (latestJob?.status === "succeeded") setJob("done");
      else if (
        ["queued", "running", "cancel_requested"].includes(
          latestJob?.status ?? "",
        )
      ) {
        setJob("running");
        pollJob(latestJob!.id, id);
      } else setJob("idle");
      setDrawer(false);
    } catch (reason) {
      setError((reason as ApiError).message ?? "无法恢复这段会话");
    }
  }

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (!draft.trim()) return;
    const content = draft.trim();
    setDraft("");
    setError("");
    setSent(true);
    setMessages((current) => [
      ...current,
      {
        id: `pending-${Date.now()}`,
        role: "user",
        content,
        risk_level: "normal",
        created_at: Math.floor(Date.now() / 1000),
      },
    ]);
    setStream("");
    setStreaming(true);
    setJob("idle");
    setWorkId(null);
    try {
      let id = conversationId;
      if (!id) {
        const created = await api.createConversation(content.slice(0, 30));
        id = created.id;
        setConversationId(id);
      }
      const message = await api.sendMessage(id, content);
      setMessageId(message.id);
      if (message.risk_level === "crisis") {
        const numbers =
          message.crisis_help?.emergency_numbers.join(" / ") ?? "110 / 120";
        setError(
          `生成已暂停。${message.crisis_help?.message ?? "如果你正处于立即危险中，请联系可信任的人或当地急救。"} 紧急电话：${numbers}`,
        );
        return;
      }
      await streamAssistant(
        id,
        message.id,
        plan.mode === "byok" ? "byok" : "platform",
        (delta) => setStream((current) => current + delta),
      );
      const detail = await api.getConversation(id);
      setMessages(detail.messages);
      setStream("");
      await refreshHistory();
    } catch (reason) {
      const apiError = reason as ApiError;
      if (apiError.code === "authentication_required")
        window.location.replace("/login");
      else setError(apiError.message ?? "消息未能发送，请重试");
    } finally {
      setStreaming(false);
    }
  }

  function pollJob(jobId: string, ownerConversationId: string) {
    activeJob.current = jobId;
    if (timer.current) clearInterval(timer.current);
    const check = async () => {
      try {
        const result = await api.getJob(jobId);
        const stages: Record<string, number> = {
          queued: 0,
          understanding: 0,
          music: 0,
          guidance: 1,
          speech: 2,
          mixing: 3,
          exporting: 3,
          complete: 4,
        };
        setProgress(
          stages[result.job.progress_stage ?? result.job.status] ?? 0,
        );
        if (result.job.status === "succeeded") {
          if (timer.current) clearInterval(timer.current);
          setJob("done");
          const detail = await api.getConversation(ownerConversationId);
          setWorkId(
            detail.jobs.find((item) => item.id === jobId)?.work_id ?? null,
          );
          await refreshHistory();
        } else if (["failed", "cancelled"].includes(result.job.status)) {
          if (timer.current) clearInterval(timer.current);
          setJob("idle");
          setError(
            result.job.status === "cancelled"
              ? "生成任务已取消"
              : `生成失败：${result.job.error_code ?? "请稍后重试"}`,
          );
        }
      } catch (reason) {
        if (timer.current) clearInterval(timer.current);
        setError((reason as ApiError).message ?? "无法获取任务进度");
      }
    };
    void check();
    timer.current = setInterval(check, 2000);
  }

  async function startJob() {
    if (!conversationId || !messageId) return;
    setError("");
    try {
      const createdPlan = await api.createPlan(conversationId, {
        message_id: messageId,
        duration_minutes: plan.duration,
        music_source: plan.source === "AI 生成" ? "ai" : "library",
        target_emotion:
          plan.target === "自动推荐"
            ? "auto"
            : (plan.target as "平静" | "喜悦" | "友爱" | "自信"),
        credential_mode: plan.mode === "byok" ? "byok" : "platform",
        voice_mode: plan.voice === "none" ? "pure_music" : "tts",
      });
      const createdJob = await api.createJob(createdPlan.id);
      setJob("running");
      setProgress(0);
      pollJob(createdJob.id, conversationId);
    } catch (reason) {
      setError((reason as ApiError).message ?? "无法开始生成");
    }
  }

  async function cancelJob() {
    if (!activeJob.current) return;
    try {
      await api.cancelJob(activeJob.current);
      setError("已请求取消任务，正在等待当前步骤停止。");
    } catch (reason) {
      setError((reason as ApiError).message ?? "当前任务无法取消");
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${drawer ? "open" : ""}`}>
        <div className="sidebar-head">
          <Brand />
          <button
            className="drawer-close"
            onClick={() => setDrawer(false)}
            aria-label="关闭历史记录"
          >
            ×
          </button>
        </div>
        <button
          className="new-chat"
          onClick={() => {
            setView("chat");
            setConversationId(null);
            setSent(false);
            setJob("idle");
            setStream("");
            setMessages([]);
            setMessageId(null);
            setWorkId(null);
            setError("");
            setDrawer(false);
          }}
        >
          <span>＋</span> 新建音乐冥想
        </button>
        <label className="search-box">
          <span>⌕</span>
          <input aria-label="搜索历史会话" placeholder="搜索你的会话" />
        </label>
        <div className="history-label">最近</div>
        <nav className="conversation-list" aria-label="历史会话">
          {conversations.map((conversation) => (
            <button
              className={conversationId === conversation.id ? "selected" : ""}
              key={conversation.id}
              onClick={() => {
                setView("chat");
                void loadConversation(conversation.id);
              }}
            >
              <span>
                <strong>{conversation.title}</strong>
                <small>
                  {new Date(conversation.updated_at * 1000).toLocaleDateString(
                    "zh-CN",
                  )}
                </small>
              </span>
              <b aria-label="更多选项">•••</b>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="quota">
            <span>
              <i style={{ width: "80%" }} />
            </span>
            <div>
              <strong>每日上限 {user?.daily_limit ?? 10} 次</strong>
              <small>平台额度 · 个人 API 不计入</small>
            </div>
          </div>
          <button className="profile">
            <span className="avatar">
              {user?.email.slice(0, 1).toUpperCase() ?? "我"}
            </span>
            <span>
              <strong>{user?.email ?? "正在加载账号…"}</strong>
              <small>{user?.role === "admin" ? "管理员" : "受邀用户"}</small>
            </span>
            <b>⌄</b>
          </button>
        </div>
      </aside>
      {drawer && (
        <button
          className="scrim"
          aria-label="关闭菜单"
          onClick={() => setDrawer(false)}
        />
      )}
      <main className="app-main">
        <header className="app-topbar">
          <div>
            <button
              className="mobile-menu"
              onClick={() => setDrawer(true)}
              aria-label="打开历史记录"
            >
              ☰
            </button>
            <span className="mobile-brand">
              <Brand />
            </span>
          </div>
          <nav>
            <button
              className={view === "chat" ? "active" : ""}
              onClick={() => setView("chat")}
            >
              冥想
            </button>
            <button
              className={view === "api" ? "active" : ""}
              onClick={() => setView("api")}
            >
              我的 API
            </button>
            <button
              className={view === "account" ? "active" : ""}
              onClick={() => setView("account")}
            >
              账号
            </button>
            {user?.role === "admin" && (
              <button
                className={view === "admin" ? "active" : ""}
                onClick={() => setView("admin")}
              >
                管理
              </button>
            )}
            <ThemeToggle />
          </nav>
        </header>
        {view === "chat" && (
          <ChatView
            sent={sent}
            draft={draft}
            setDraft={setDraft}
            send={send}
            stream={stream}
            messages={messages}
            streaming={streaming}
            error={error}
            plan={plan}
            setPlan={setPlan}
            job={job}
            progress={progress}
            startJob={startJob}
            cancelJob={cancelJob}
            workId={workId}
          />
        )}
        {view === "api" && <ApiSettings />}
        {view === "account" && user && (
          <AccountSettings
            user={user}
            required={passwordSetupRequired}
            onComplete={() => {
              setUser({
                ...user,
                password_configured: true,
                password_setup: "none",
              });
              setPasswordSetupRequired(false);
              setView("chat");
              window.history.replaceState({}, "", "/app");
              void (async () => {
                const history = await api.listConversations();
                setConversations(history.items);
                if (history.items[0]) await loadConversation(history.items[0].id);
              })();
            }}
            onSkip={() => {
              setView("chat");
              window.history.replaceState({}, "", "/app");
            }}
          />
        )}
        {view === "admin" && user?.role === "admin" && <AdminView />}
      </main>
    </div>
  );
}

function ChatView({
  sent,
  draft,
  setDraft,
  send,
  stream,
  messages,
  streaming,
  error,
  plan,
  setPlan,
  job,
  progress,
  startJob,
  cancelJob,
  workId,
}: {
  sent: boolean;
  draft: string;
  setDraft: (v: string) => void;
  send: (e?: FormEvent) => void;
  stream: string;
  messages: Message[];
  streaming: boolean;
  error: string;
  plan: Plan;
  setPlan: (p: Plan) => void;
  job: string;
  progress: number;
  startJob: () => void;
  cancelJob: () => void;
  workId: string | null;
}) {
  return (
    <div className="chat-layout">
      <div className="chat-scroll">
        <div className="chat-column">
          {!sent ? (
            <section className="empty-chat">
              <div className="breathing-logo">
                <Brand compact />
              </div>
              <p className="overline">欢迎回来</p>
              <h1>此刻，你的心情怎么样？</h1>
              <p>不必组织得很完整，像和熟悉的人说话一样就好。</p>
              <div className="prompt-grid">
                {prompts.map((p, i) => (
                  <button key={p} onClick={() => setDraft(p)}>
                    <span className={`prompt-icon p${i}`}>
                      {["⌁", "↗", "☾", "✦"][i]}
                    </span>
                    {p}
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <>
              {messages.map((message) =>
                message.role === "user" ? (
                  <div className="message user-message" key={message.id}>
                    <p>{message.content}</p>
                    <span className="message-avatar">我</span>
                  </div>
                ) : (
                  <div className="message assistant-message" key={message.id}>
                    <span className="assistant-avatar">
                      <Brand compact />
                    </span>
                    <div>
                      <p>{message.content}</p>
                    </div>
                  </div>
                ),
              )}
              {streaming && (
                <div className="message assistant-message">
                  <span className="assistant-avatar">
                    <Brand compact />
                  </span>
                  <div>
                    <p>
                      {stream || "正在理解你的感受…"}
                      <i className="typing-caret" />
                    </p>
                  </div>
                </div>
              )}
              {error && (
                <div className="chat-error" role="alert">
                  {error}
                </div>
              )}
              {!streaming &&
                messages.some((message) => message.role === "assistant") && (
                  <PlanCard
                    plan={plan}
                    setPlan={setPlan}
                    onStart={startJob}
                    disabled={job !== "idle"}
                  />
                )}
              {job === "running" && (
                <ProgressCard progress={progress} onCancel={cancelJob} />
              )}
              {job === "done" && workId && <WorkCard workId={workId} />}
            </>
          )}
        </div>
      </div>
      <form className="composer" onSubmit={send}>
        <div className="composer-inner">
          <textarea
            value={draft}
            maxLength={2000}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="说说你现在的感受……"
            aria-label="描述你现在的感受"
          />
          <div className="composer-tools">
            <div>
              <button type="button" className="chip active">
                5 分钟⌄
              </button>
              <button type="button" className="chip">
                ♫ 音乐库
              </button>
              <button type="button" className="chip desktop-only">
                ⚙ 高级设置
              </button>
            </div>
            <button
              className="send-button"
              disabled={!draft.trim() || streaming}
              aria-label="发送"
            >
              ↑
            </button>
          </div>
        </div>
        <small>AI 可能会出错；这是一款情绪调节工具，不能替代专业诊疗。</small>
      </form>
    </div>
  );
}

function PlanCard({
  plan,
  setPlan,
  onStart,
  disabled,
}: {
  plan: Plan;
  setPlan: (p: Plan) => void;
  onStart: () => void;
  disabled: boolean;
}) {
  const field = (key: keyof Plan, value: string | number) =>
    setPlan({ ...plan, [key]: value });
  return (
    <section className="plan-card">
      <header>
        <div>
          <span className="card-icon">⌁</span>
          <span>
            <small>为你规划的音乐冥想</small>
            <strong>从紧绷中，慢慢找回安定</strong>
          </span>
        </div>
        <span className="soft-badge">可调整</span>
      </header>
      <div className="emotion-path">
        <div className="emotion-node warm">
          <span>01</span>
          <b>自动识别</b>
          <small>先被听见</small>
        </div>
        <i>→</i>
        <div className="emotion-node calm">
          <span>02</span>
          <b>平静</b>
          <small>松开呼吸</small>
        </div>
        <i>→</i>
        <div className="emotion-node bright">
          <span>03</span>
          <b>{plan.target}</b>
          <small>重新站稳</small>
        </div>
      </div>
      <div className="plan-fields">
        <label>
          当前主要情绪
          <span className="readonly-field">系统将在生成时自动识别</span>
        </label>
        <label>
          希望抵达
          <select
            value={plan.target}
            onChange={(e) => field("target", e.target.value)}
          >
            <option>自动推荐</option>
            <option>平静</option>
            <option>喜悦</option>
            <option>友爱</option>
            <option>自信</option>
          </select>
        </label>
        <label>
          时长
          <select
            value={plan.duration}
            onChange={(e) => field("duration", Number(e.target.value))}
          >
            <option value="3">3 分钟</option>
            <option value="5">5 分钟</option>
            <option value="10">10 分钟</option>
            <option value="15">15 分钟</option>
          </select>
        </label>
        <label>
          音乐
          <select
            value={plan.source}
            onChange={(e) => field("source", e.target.value)}
          >
            <option>音乐库</option>
            <option>AI 生成</option>
          </select>
        </label>
      </div>
      <details>
        <summary>
          更多设置 <span>引导音色、语速与冥想方式</span>
        </summary>
        <div className="detail-fields">
          <label>
            引导声音
            <select
              value={plan.voice}
              onChange={(e) => field("voice", e.target.value)}
            >
              <option value="female-chengshu-jingpin">
                成熟温柔女声（精品）
              </option>
              <option value="none">纯音乐，不要语音</option>
            </select>
          </label>
          <label>
            引导方式
            <select>
              <option>自动推荐</option>
              <option>呼吸觉察</option>
              <option>身体扫描</option>
              <option>温柔陪伴</option>
              <option>积极意象</option>
            </select>
          </label>
          <label>
            API 模式
            <select
              value={plan.mode}
              onChange={(e) => field("mode", e.target.value)}
            >
              <option value="platform">平台额度</option>
              <option value="byok">使用我的 API</option>
            </select>
          </label>
        </div>
      </details>
      <footer>
        <span>
          <b>{plan.mode === "byok" ? "个人 API" : "平台额度"}</b>
          <small>
            {plan.mode === "byok" ? "费用由服务商收取" : "每日生成额度以内可用"}
          </small>
        </span>
        <button className="button" disabled={disabled} onClick={onStart}>
          {disabled ? "已开始生成" : "开始生成"} <span>→</span>
        </button>
      </footer>
    </section>
  );
}

function ProgressCard({
  progress,
  onCancel,
}: {
  progress: number;
  onCancel: () => void;
}) {
  const steps = ["准备三阶段音乐", "生成冥想引导", "生成语音", "混音并导出"];
  return (
    <section className="progress-card">
      <div className="progress-orb">
        <i />
        <span>♫</span>
      </div>
      <div className="progress-content">
        <header>
          <div>
            <small>正在生成你的音乐冥想</small>
            <strong>{steps[Math.min(progress, 3)]}</strong>
          </div>
          <span>可关闭页面</span>
        </header>
        <ol>
          {steps.map((s, i) => (
            <li
              className={
                i < progress ? "done" : i === progress ? "current" : ""
              }
              key={s}
            >
              <i>{i < progress ? "✓" : i + 1}</i>
              <span>
                {s}
                {i === 0 && progress === 0 && (
                  <small>第 2 / 3 段音乐正在准备</small>
                )}
              </span>
            </li>
          ))}
        </ol>
        <p>
          任务会继续在后台进行，完成后可在历史记录中找到。{" "}
          <button className="cancel-link" onClick={onCancel}>
            取消生成
          </button>
        </p>
      </div>
    </section>
  );
}

function WorkCard({ workId }: { workId: string }) {
  const [playing, setPlaying] = useState(false);
  const [favorite, setFavorite] = useState(false);
  const [error, setError] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const audio = useRef<HTMLAudioElement | null>(null);
  const formatTime = (seconds: number) =>
    `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
      .toString()
      .padStart(2, "0")}`;
  async function togglePlayback() {
    if (!audio.current) return;
    try {
      if (audio.current.paused) {
        await audio.current.play();
        setPlaying(true);
      } else {
        audio.current.pause();
        setPlaying(false);
      }
    } catch {
      setError("音频暂时无法播放，请尝试下载后收听。");
    }
  }
  async function toggleFavorite() {
    try {
      const result = await api.favoriteWork(workId, !favorite);
      setFavorite(result.is_favorite);
      setError("");
    } catch (reason) {
      setError((reason as ApiError).message ?? "收藏操作失败");
    }
  }
  return (
    <section className="work-card">
      <audio
        ref={audio}
        src={api.downloadUrl(workId, "mp3")}
        preload="metadata"
        onLoadedMetadata={(event) =>
          setDuration(event.currentTarget.duration || 0)
        }
        onTimeUpdate={(event) =>
          setCurrentTime(event.currentTarget.currentTime)
        }
        onEnded={() => setPlaying(false)}
      />
      <header>
        <div>
          <span className="success-mark">✓</span>
          <span>
            <small>音乐冥想已完成</small>
            <strong>
              {duration ? `音乐冥想 · ${formatTime(duration)}` : "你的音乐冥想"}
            </strong>
          </span>
        </div>
        <button className="icon-button" aria-label="更多操作">
          •••
        </button>
      </header>
      <div className="player">
        <button
          className="player-button"
          onClick={() => void togglePlayback()}
          aria-label={playing ? "暂停" : "播放"}
        >
          {playing ? "Ⅱ" : "▶"}
        </button>
        <div className="player-main">
          <div className="player-timeline">
            <span
              style={{
                width: `${duration ? Math.min(100, (currentTime / duration) * 100) : 0}%`,
              }}
            />
            <i
              style={{
                left: `${duration ? Math.min(100, (currentTime / duration) * 100) : 0}%`,
              }}
            />
          </div>
          <div className="player-times">
            <span>{formatTime(currentTime)}</span>
            <span>{duration ? formatTime(duration) : "--:--"}</span>
          </div>
        </div>
        <button className="volume" aria-label="音量">
          ◖))
        </button>
      </div>
      <div className="stage-track">
        <button className="current">
          <i />
          阶段一<small>承接当下</small>
        </button>
        <button>
          <i />
          阶段二<small>逐步过渡</small>
        </button>
        <button>
          <i />
          阶段三<small>抵达目标</small>
        </button>
      </div>
      <div className="work-actions">
        <button onClick={() => void toggleFavorite()}>
          {favorite ? "★ 已收藏" : "☆ 收藏"}
        </button>
        <a href={api.downloadUrl(workId, "mp3")} download>
          ⇩ MP3
        </a>
        <a href={api.downloadUrl(workId, "wav")} download>
          ⇩ WAV
        </a>
        <a href={api.downloadUrl(workId, "txt")} download>
          ▤ 下载引导词
        </a>
      </div>
      {error && (
        <div className="work-error" role="alert">
          {error}
        </div>
      )}
      <footer>
        <span>这段音乐冥想适合你吗？</span>
        <div>
          <button aria-label="喜欢">♡</button>
          <button aria-label="不喜欢">♧</button>
        </div>
        <button>复制设置到新会话 →</button>
      </footer>
    </section>
  );
}

export function ApiSettings() {
  const [personal, setPersonal] = useState(true);
  const [keys, setKeys] = useState({
    deepseek_api_key: "",
    minimax_api_key: "",
    elevenlabs_api_key: "",
  });
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault();
    setStatus("");
    setSaving(true);
    try {
      const result = await api.saveCredentials({
        deepseek_api_key: keys.deepseek_api_key,
        minimax_api_key: keys.minimax_api_key,
        ...(keys.elevenlabs_api_key
          ? { elevenlabs_api_key: keys.elevenlabs_api_key }
          : {}),
      });
      setStatus(
        `已安全保存。DeepSeek 与 MiniMax 已配置${result.configured.elevenlabs ? "，ElevenLabs 已启用" : ""}。`,
      );
      setKeys({
        deepseek_api_key: "",
        minimax_api_key: "",
        elevenlabs_api_key: "",
      });
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "API Key 保存失败");
    } finally {
      setSaving(false);
    }
  }
  async function remove() {
    if (!window.confirm("确定删除账号下保存的全部个人 API Key 吗？")) return;
    try {
      await api.deleteCredentials();
      setStatus("个人 API Key 已全部删除。");
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "删除失败");
    }
  }
  return (
    <form className="settings-page" onSubmit={save}>
      <div className="page-heading">
        <p>设置</p>
        <h1>使用我的 API</h1>
        <span>密钥将加密保存在服务器，网页和日志中不会显示完整内容。</span>
      </div>
      <section className="mode-card">
        <div>
          <span className="settings-icon">⌁</span>
          <span>
            <strong>个人 API 模式</strong>
            <small>不受每日 10 次平台额度限制，同时只能生成 1 个任务。</small>
          </span>
        </div>
        <button
          className={`switch ${personal ? "on" : ""}`}
          onClick={() => setPersonal(!personal)}
          aria-pressed={personal}
        >
          <i />
        </button>
      </section>
      <div className="notice">
        费用由 DeepSeek、MiniMax 或 ElevenLabs
        直接向你的账户收取。实际生成会调用对应服务并产生费用。
      </div>
      {status && (
        <div className="settings-status" role="status">
          {status}
        </div>
      )}
      <Credential
        name="DeepSeek"
        required
        hint="对话、情绪识别与引导词"
        value={keys.deepseek_api_key}
        onChange={(value) => setKeys({ ...keys, deepseek_api_key: value })}
      />
      <Credential
        name="MiniMax"
        required
        hint="音乐生成与中文语音"
        value={keys.minimax_api_key}
        onChange={(value) => setKeys({ ...keys, minimax_api_key: value })}
      />
      <Credential
        name="ElevenLabs"
        hint="可选的 AI 音乐备用服务"
        optional
        value={keys.elevenlabs_api_key}
        onChange={(value) => setKeys({ ...keys, elevenlabs_api_key: value })}
      />
      <div className="credential-actions">
        <button type="button" onClick={() => void remove()}>
          删除已保存的密钥
        </button>
        <button
          className="button"
          type="submit"
          disabled={saving || !keys.deepseek_api_key || !keys.minimax_api_key}
        >
          {saving ? "正在加密保存…" : "保存个人 API"}
        </button>
      </div>
      <p className="settings-foot">
        个人 API 模式需要 DeepSeek 与 MiniMax 均已保存。ElevenLabs
        未配置时不会启用备用服务。
      </p>
    </form>
  );
}

function Credential({
  name,
  required,
  hint,
  optional,
  value,
  onChange,
}: {
  name: string;
  required?: boolean;
  hint: string;
  optional?: boolean;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <section className="credential-card">
      <header>
        <div>
          <span className={`provider-logo ${name.toLowerCase()}`}>
            {name[0]}
          </span>
          <span>
            <strong>
              {name} {required && <em>必填</em>}
            </strong>
            <small>{hint}</small>
          </span>
        </div>
        <span className="verified">服务器端加密</span>
      </header>
      <div className="key-row">
        <label>
          API Key
          <input
            type="password"
            autoComplete="off"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={optional ? "可留空" : "输入新的 API Key"}
            required={!optional}
            minLength={8}
          />
        </label>
      </div>
    </section>
  );
}

export function AccountSettings({
  user,
  required,
  onComplete,
  onSkip,
}: {
  user: User;
  required: boolean;
  onComplete: () => void;
  onSkip: () => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const isFirstPassword = !user.password_configured;

  async function savePassword(event: FormEvent) {
    event.preventDefault();
    setStatus("");
    if (password !== confirmation) {
      setStatus("两次输入的密码不一致。");
      return;
    }
    setSaving(true);
    try {
      await api.setPassword({
        password,
        password_confirmation: confirmation,
        ...(!isFirstPassword && currentPassword
          ? { current_password: currentPassword }
          : {}),
      });
      setStatus("登录密码已安全保存。");
      setCurrentPassword("");
      setPassword("");
      setConfirmation("");
      onComplete();
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "密码保存失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="settings-page account-settings" onSubmit={savePassword}>
      <div className="page-heading">
        <p>账号设置</p>
        <h1>{isFirstPassword ? "设置登录密码" : "修改登录密码"}</h1>
        <span>
          设置后仍可随时选择邮箱验证码登录。密码会经过安全哈希处理，不会保存明文。
        </span>
      </div>
      {isFirstPassword && (
        <div className="notice">
          {required
            ? "首次登录需要先设置密码，保存后即可进入 AIMusicMed。"
            : "你可以现在设置密码，也可以暂时跳过，以后在账号设置中完成。"}
        </div>
      )}
      {status && <div className="settings-status" role="status">{status}</div>}
      <section className="credential-card password-card">
        {!isFirstPassword && (
          <label>
            当前密码
            <input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
          </label>
        )}
        <label>
          {isFirstPassword ? "登录密码" : "新密码"}
          <input type="password" autoComplete="new-password" minLength={10} maxLength={72} value={password} onChange={(event) => setPassword(event.target.value)} required />
          <small>10–72 个字符，可使用中文、空格或密码短语。</small>
        </label>
        <label>
          再次输入密码
          <input type="password" autoComplete="new-password" minLength={10} maxLength={72} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required />
        </label>
      </section>
      <div className="credential-actions">
        {isFirstPassword && !required && (
          <button type="button" onClick={onSkip}>暂时跳过</button>
        )}
        <button className="button" type="submit" disabled={saving}>
          {saving ? "正在安全保存…" : "保存密码"}
        </button>
      </div>
    </form>
  );
}

export function AdminView() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("");
  async function loadUsers() {
    try {
      const result = await api.adminUsers();
      setUsers(result.items);
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "无法加载用户列表");
    }
  }
  useEffect(() => {
    const frame = requestAnimationFrame(() => void loadUsers());
    return () => cancelAnimationFrame(frame);
  }, []);
  async function invite(event: FormEvent) {
    event.preventDefault();
    setStatus("");
    try {
      await api.inviteUser(email);
      setStatus("邮箱已加入白名单，6 位登录验证码已发送，15 分钟内有效。");
      setEmail("");
      await loadUsers();
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "邀请失败");
    }
  }
  async function resendCode(user: AdminUser) {
    try {
      await api.resendUserCode(user.id);
      setStatus(`已向 ${user.email} 重新发送 6 位登录验证码。`);
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "验证码发送失败");
    }
  }
  async function toggleUser(user: AdminUser) {
    const disabling = user.status !== "disabled";
    if (
      disabling &&
      !window.confirm(
        `停用 ${user.email} 后，该账号的所有会话会立即注销，确定继续吗？`,
      )
    )
      return;
    try {
      await api.updateUserStatus(user.id, disabling ? "disabled" : "active");
      setStatus(disabling ? "用户已停用，历史内容仍保留。" : "用户已重新启用。");
      await loadUsers();
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "用户状态更新失败");
    }
  }
  async function editQuota(user: AdminUser) {
    const value = window.prompt(
      `设置 ${user.email} 的每日生成额度`,
      String(user.daily_limit),
    );
    if (value === null) return;
    const limit = Number(value);
    if (!Number.isInteger(limit) || limit < 0 || limit > 1000) {
      setStatus("请输入 0–1000 的整数额度");
      return;
    }
    try {
      await api.updateUserQuota(user.id, limit);
      setStatus("额度已更新。");
      await loadUsers();
    } catch (reason) {
      setStatus((reason as ApiError).message ?? "额度更新失败");
    }
  }
  return (
    <div className="admin-page">
      <div className="page-heading">
        <p>管理后台</p>
        <h1>受邀用户</h1>
        <span>仅显示必要的运行信息，不展示用户倾诉或个人 API Key。</span>
      </div>
      <div className="stat-grid">
        <article>
          <span>账号总数</span>
          <strong>{users.length}</strong>
          <small>包含管理员</small>
        </article>
        <article>
          <span>活跃用户</span>
          <strong>
            {users.filter((item) => item.status === "active").length}
          </strong>
          <small>已接受邀请</small>
        </article>
        <article>
          <span>待接受</span>
          <strong>
            {users.filter((item) => item.status === "pending").length}
          </strong>
          <small>已在白名单，尚未激活</small>
        </article>
        <article>
          <span>普通用户</span>
          <strong>{users.filter((item) => item.role === "user").length}</strong>
          <small>管理员不计入</small>
        </article>
      </div>
      {status && (
        <div className="settings-status" role="status">
          {status}
        </div>
      )}
      <section className="admin-panel">
        <header>
          <div>
            <h2>用户与额度</h2>
            <p>点击额度可为单个普通用户调整</p>
          </div>
        </header>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>邮箱</th>
                <th>角色</th>
                <th>状态</th>
                <th>每日额度</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.id}>
                  <td>{item.email}</td>
                  <td>{item.role === "admin" ? "管理员" : "用户"}</td>
                  <td>
                    <span
                      className={`status ${item.status === "active" ? "success" : item.status === "disabled" ? "disabled" : "running"}`}
                    >
                      {item.status === "active"
                        ? "已激活"
                        : item.status === "disabled"
                          ? "已停用"
                          : "待激活"}
                    </span>
                  </td>
                  <td>
                    {item.role === "user" ? (
                      <button
                        className="quota-button"
                        onClick={() => void editQuota(item)}
                      >
                        {item.daily_limit} 次 / 日
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {item.role === "user" && (
                      <div className="admin-actions">
                        {item.status === "pending" && (
                          <button type="button" onClick={() => void resendCode(item)}>重发验证码</button>
                        )}
                        {item.status !== "pending" && (
                          <button type="button" onClick={() => void toggleUser(item)}>
                            {item.status === "disabled" ? "启用" : "停用"}
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="admin-panel compact">
        <header>
          <div>
            <h2>邀请新用户</h2>
            <p>加入邮箱白名单，并发送 15 分钟有效的 6 位登录验证码</p>
          </div>
          <form className="invite-form" onSubmit={invite}>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@example.com"
              required
            />
            <button className="button small" type="submit">
              加入并发送验证码
            </button>
          </form>
        </header>
      </section>
    </div>
  );
}
