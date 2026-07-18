"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  api,
  ApiError,
  Conversation,
  JobEvent,
  Message,
  MusicTrack,
  PlanDraft,
  streamAssistant,
  User,
  VoiceAsset,
  WorkSummary,
} from "../lib/api";
import { Brand } from "./brand";
import { ThemeToggle } from "./theme-toggle";
import { AccountSettings, ApiSettings } from "./app-demo";
import { OperationsAdmin, UserAssets } from "./operations-console";

type View = "chat" | "works" | "assets" | "api" | "account" | "admin";
type JobState = "idle" | "running" | "done" | "failed" | "cancelled";
type PlayerTrack = { workId: string; title: string } | null;

const emptyPlan: PlanDraft = {
  duration_minutes: 5,
  music_source: "library",
  target_emotion: "auto",
  credential_mode: "platform",
  voice_mode: "tts",
  selected_voice_id: "female-chengshu-jingpin",
  selected_music_asset_id: null,
  guidance_style: "auto",
  language_density: "balanced",
};

const prompts = [
  "刚结束一场重要汇报，我还是很紧张。",
  "今天有点低落，想慢慢找回一点力量。",
  "脑子停不下来，想在睡前安静一会儿。",
  "状态不错，想把这份自信稳定下来。",
];

function errorMessage(reason: unknown, fallback: string) {
  return (reason as ApiError)?.message ?? fallback;
}

function unwrapDraft(
  result: PlanDraft | { draft: PlanDraft; summary?: string },
): PlanDraft {
  if ("draft" in result) {
    return {
      ...result.draft,
      summary: result.draft.summary ?? result.summary,
    };
  }
  return result;
}

export function AppDemo({ initialView = "chat" }: { initialView?: View }) {
  const [view, setView] = useState<View>(initialView);
  const [drawer, setDrawer] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [passwordSetupRequired, setPasswordSetupRequired] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [trash, setTrash] = useState<Conversation[]>([]);
  const [showTrash, setShowTrash] = useState(false);
  const [search, setSearch] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageId, setMessageId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [stream, setStream] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState<PlanDraft | null>(null);
  const [planning, setPlanning] = useState(false);
  const [starting, setStarting] = useState(false);
  const [jobState, setJobState] = useState<JobState>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobCreatedAt, setJobCreatedAt] = useState<number | null>(null);
  const [jobEvents, setJobEvents] = useState<JobEvent[]>([]);
  const [workId, setWorkId] = useState<string | null>(null);
  const [workTitle, setWorkTitle] = useState("我的音乐冥想");
  const [workFavorite, setWorkFavorite] = useState(false);
  const [failure, setFailure] = useState("");
  const [notifyOnComplete, setNotifyOnComplete] = useState(false);
  const [completionUnread, setCompletionUnread] = useState(false);
  const [track, setTrack] = useState<PlayerTrack>(null);
  const [favoriteWorks, setFavoriteWorks] = useState<WorkSummary[]>([]);
  const [availableVoices, setAvailableVoices] = useState<VoiceAsset[]>([]);
  const [availableTracks, setAvailableTracks] = useState<MusicTrack[]>([]);
  const [voicesLoaded, setVoicesLoaded] = useState(false);
  const [tracksLoaded, setTracksLoaded] = useState(false);
  const voicesLoadingRef = useRef(false);
  const tracksLoadingRef = useRef(false);
  const latestPlanRef = useRef<PlanDraft | null>(plan);
  latestPlanRef.current = plan;
  const polling = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollNow = useRef<(() => void) | null>(null);
  const pollingBusy = useRef(false);
  const pollGeneration = useRef(0);
  const planSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const jobStarting = useRef(false);
  const completionAudio = useRef<AudioContext | null>(null);

  const refreshHistory = useCallback(async () => {
    const [active, deleted] = await Promise.all([
      api.listConversations(),
      api.listConversations(true),
    ]);
    const activeItems = active.items.filter((item) => !item.deleted_at);
    setConversations(activeItems);
    setTrash(deleted.items.filter((item) => Boolean(item.deleted_at)));
    return activeItems;
  }, []);

  const notifyComplete = useCallback(() => {
    if (notifyOnComplete && completionAudio.current) {
      const context = completionAudio.current;
      void context.resume().then(() => {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.frequency.setValueAtTime(660, context.currentTime);
        oscillator.frequency.linearRampToValueAtTime(
          880,
          context.currentTime + 0.18,
        );
        gain.gain.setValueAtTime(0.035, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(
          0.001,
          context.currentTime + 0.24,
        );
        oscillator.start();
        oscillator.stop(context.currentTime + 0.24);
      });
    }
    if (
      notifyOnComplete &&
      typeof Notification !== "undefined" &&
      Notification.permission === "granted" &&
      document.hidden
    ) {
      new Notification("音乐冥想已完成", {
        body: "回到 AIMusicMed 即可播放。",
      });
    }
  }, [notifyOnComplete]);

  const loadVoices = useCallback(async () => {
    if (voicesLoadingRef.current || voicesLoaded) return;
    voicesLoadingRef.current = true;
    try {
      const result = await api.listVoices();
      setAvailableVoices(result.items.filter((voice) => voice.status === "ready"));
      setVoicesLoaded(true);
    } catch {
      // Keep voicesLoaded=false so retry is possible.
    } finally {
      voicesLoadingRef.current = false;
    }
  }, [voicesLoaded]);

  const loadTracks = useCallback(async () => {
    if (tracksLoadingRef.current || tracksLoaded) return;
    tracksLoadingRef.current = true;
    try {
      const [priv, pub] = await Promise.all([
        api.listMusicTracks("private"),
        api.listMusicTracks("public"),
      ]);
      setAvailableTracks([...priv.items, ...pub.items]);
      setTracksLoaded(true);
    } catch {
      // Keep tracksLoaded=false so retry is possible.
    } finally {
      tracksLoadingRef.current = false;
    }
  }, [tracksLoaded]);

  const pollJob = useCallback(
    (id: string, ownerConversationId: string) => {
      const generation = ++pollGeneration.current;
      setJobId(id);
      if (polling.current) clearInterval(polling.current);
      let retryDelay = 2000;
      const check = async () => {
        if (pollingBusy.current) return;
        pollingBusy.current = true;
        let terminal = false;
        try {
          const result = await api.getJob(id);
          if (generation !== pollGeneration.current) return;
          retryDelay = 2000;
          setJobEvents(result.events);
          setJobCreatedAt(result.job.created_at);
          if (result.job.status === "succeeded") {
            terminal = true;
            pollNow.current = null;
            setJobState("done");
            setCompletionUnread(true);
            const detail = await api.getConversation(ownerConversationId);
            const completed = detail.jobs.find((item) => item.id === id);
            setWorkId(completed?.work_id ?? null);
            setWorkTitle(completed?.work_title || "我的音乐冥想");
            setWorkFavorite(Boolean(completed?.is_favorite));
            notifyComplete();
            await refreshHistory();
          } else if (["failed", "cancelled"].includes(result.job.status)) {
            terminal = true;
            pollNow.current = null;
            setJobState(
              result.job.status === "failed" ? "failed" : "cancelled",
            );
            setFailure(
              result.job.status === "cancelled"
                ? "任务已取消，你可以修改方案后重新开始。"
                : "这次生成没有完成，额度不会被扣除。你可以按原方案重试，或先修改方案。",
            );
          } else {
            setJobState("running");
          }
        } catch (reason) {
          if (generation === pollGeneration.current) {
            setError(errorMessage(reason, "连接暂时波动，正在自动恢复进度"));
            retryDelay = Math.min(retryDelay * 2, 15000);
          }
        } finally {
          pollingBusy.current = false;
          if (!terminal && generation === pollGeneration.current)
            polling.current = setTimeout(check, retryDelay);
        }
      };
      pollNow.current = () => {
        if (polling.current) clearTimeout(polling.current);
        void check();
      };
      void check();
    },
    [notifyComplete, refreshHistory],
  );

  const loadConversation = useCallback(
    async (id: string) => {
      setError("");
      pollGeneration.current += 1;
      pollNow.current = null;
      pollingBusy.current = false;
      if (polling.current) clearTimeout(polling.current);
      try {
        const detail = await api.getConversation(id);
        setConversationId(id);
        setMessages(detail.messages);
        setMessageId(
          [...detail.messages].reverse().find((item) => item.role === "user")
            ?.id ?? null,
        );
        setPlan(detail.draft ?? null);
        setStream("");
        setFailure("");
        const latest = detail.jobs.at(-1);
        setJobId(latest?.id ?? null);
        setWorkId(latest?.work_id ?? null);
        setWorkTitle(latest?.work_title || "我的音乐冥想");
        setWorkFavorite(Boolean(latest?.is_favorite));
        setJobCreatedAt(latest?.created_at ?? null);
        if (latest?.status === "succeeded") {
          setJobState("done");
          const lastSeen = Number(
            window.localStorage.getItem("aimusicmed:last-completion-seen") ?? 0,
          );
          if ((latest.finished_at ?? 0) > lastSeen) setCompletionUnread(true);
        }
        else if (
          ["queued", "running", "cancel_requested"].includes(
            latest?.status ?? "",
          )
        ) {
          setJobState("running");
          pollJob(latest!.id, id);
        } else if (latest?.status === "failed") {
          setJobState("failed");
          setFailure(
            "这次生成没有完成，额度不会被扣除。你可以按原方案重试，或先修改方案。",
          );
        } else if (latest?.status === "cancelled") {
          setJobState("cancelled");
          setFailure("任务已取消，你可以修改方案后重新开始。");
        }
        else setJobState("idle");
        setDrawer(false);
      } catch (reason) {
        setError(errorMessage(reason, "无法恢复这段会话"));
      }
    },
    [pollJob],
  );

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
        const active = await refreshHistory();
        if (active[0]) await loadConversation(active[0].id);
        if (setup === "optional") setView("account");
        // Preload voice and track catalogues once after login.
        if (!cancelled) { void loadVoices(); void loadTracks(); }
      } catch (reason) {
        const apiError = reason as ApiError;
        if (apiError.code === "authentication_required")
          window.location.replace("/login");
        else setError(errorMessage(reason, "暂时无法加载账号数据"));
      }
    })();
    return () => {
      cancelled = true;
      if (polling.current) clearInterval(polling.current);
      if (planSaveTimer.current) clearTimeout(planSaveTimer.current);
    };
  }, [initialView, loadConversation, refreshHistory]);

  useEffect(() => {
    const resumePolling = () => {
      if (document.visibilityState === "visible" && jobState === "running")
        pollNow.current?.();
    };
    document.addEventListener("visibilitychange", resumePolling);
    return () =>
      document.removeEventListener("visibilitychange", resumePolling);
  }, [jobState]);

  async function updatePlanDraft(id: string, latestMessageId: string) {
    setPlanning(true);
    try {
      const result = await api.createPlanDraft(id, {
        message_id: latestMessageId,
        credential_mode: plan?.credential_mode ?? "platform",
      });
      setPlan({ ...emptyPlan, ...unwrapDraft(result) });
    } finally {
      setPlanning(false);
    }
  }

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (!draft.trim() || streaming) return;
    const content = draft.trim();
    setDraft("");
    setError("");
    setMessages((current) => [
      ...current,
      {
        id: `pending-${Date.now()}`,
        role: "user",
        content,
        risk_level: "normal",
        created_at: Date.now() / 1000,
      },
    ]);
    setStreaming(true);
    setStream("");
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
        plan?.credential_mode ?? "platform",
        (delta) => setStream((current) => current + delta),
      );
      const detail = await api.getConversation(id);
      setMessages(detail.messages);
      setStream("");
      if (plan) await updatePlanDraft(id, message.id);
      await refreshHistory();
    } catch (reason) {
      setError(errorMessage(reason, "消息未能发送，请重试"));
    } finally {
      setStreaming(false);
    }
  }

  async function finishVenting() {
    if (!conversationId || !messageId) return;
    setError("");
    try {
      await updatePlanDraft(conversationId, messageId);
    } catch (reason) {
      setError(errorMessage(reason, "暂时无法规划，请稍后重试"));
    }
  }

  async function startJob() {
    if (!conversationId || !messageId || !plan || jobStarting.current) return;
    jobStarting.current = true;
    setStarting(true);
    setError("");
    setFailure("");
    try {
      if (planSaveTimer.current) clearTimeout(planSaveTimer.current);
      if (plan.id) {
        await api.updatePlanDraft(conversationId, {
          duration_minutes: plan.duration_minutes,
          music_source: plan.music_source,
          target_emotion: plan.target_emotion,
          credential_mode: plan.credential_mode,
          voice_mode: plan.voice_mode,
          selected_voice_id: plan.selected_voice_id,
          selected_music_asset_id: plan.selected_music_asset_id,
          guidance_style: plan.guidance_style,
          language_density: plan.language_density,
        });
      }
      const createdPlan = await api.createPlan(conversationId, {
        draft_id: plan.id,
        message_id: messageId,
        duration_minutes: plan.duration_minutes,
        music_source: plan.music_source,
        target_emotion: plan.target_emotion,
        credential_mode: plan.credential_mode,
        voice_mode: plan.voice_mode,
        selected_voice_id: plan.selected_voice_id,
        selected_music_asset_id: plan.selected_music_asset_id,
        guidance_style: plan.guidance_style,
        language_density: plan.language_density,
      });
      const createdJob = await api.createJob(createdPlan.id);
      setJobState("running");
      setJobEvents([]);
      pollJob(createdJob.id, conversationId);
    } catch (reason) {
      setError(errorMessage(reason, "无法开始生成"));
    } finally {
      jobStarting.current = false;
      setStarting(false);
    }
  }

  async function retryJob() {
    if (!jobId || !conversationId) return;
    setError("");
    try {
      const retried = await api.retryJob(jobId);
      setJobState("running");
      setJobEvents([]);
      pollJob(retried.id, conversationId);
    } catch (reason) {
      setError(errorMessage(reason, "暂时无法重试"));
    }
  }

  async function cancelJob() {
    if (!jobId) return;
    try {
      await api.cancelJob(jobId);
      setError("已请求取消任务，正在等待当前步骤安全停止。");
    } catch (reason) {
      setError(errorMessage(reason, "当前任务无法取消"));
    }
  }

  async function editFailedJob() {
    if (!jobId) return;
    setError("");
    try {
      const result = await api.createEditableDraftFromJob(jobId);
      setPlan({ ...emptyPlan, ...unwrapDraft(result) });
      setJobState("idle");
      setFailure("");
    } catch (reason) {
      setError(
        errorMessage(
          reason,
          "暂时无法恢复这个方案，你仍可按原方案重试。",
        ),
      );
    }
  }

  async function renameConversation(item: Conversation) {
    const title = window.prompt("为这段会话重新命名", item.title)?.trim();
    if (!title || title === item.title) return;
    try {
      await api.updateConversation(item.id, title);
      await refreshHistory();
    } catch (reason) {
      setError(errorMessage(reason, "重命名失败"));
    }
  }

  async function deleteConversation(item: Conversation) {
    if (
      !window.confirm(
        "删除后会话进入回收站，30 天内可恢复。收藏作品不会被删除，未收藏音频仍按原规则清理。",
      )
    )
      return;
    try {
      await api.deleteConversation(item.id);
      if (conversationId === item.id) newConversation();
      await refreshHistory();
    } catch (reason) {
      setError(errorMessage(reason, "删除失败"));
    }
  }

  async function restoreConversation(item: Conversation) {
    try {
      await api.restoreConversation(item.id);
      await refreshHistory();
    } catch (reason) {
      setError(errorMessage(reason, "恢复失败"));
    }
  }

  async function openFavoriteWorks() {
    setError("");
    setView("works");
    setDrawer(false);
    try {
      const result = await api.listWorks(true);
      setFavoriteWorks(result.items);
    } catch (reason) {
      setError(errorMessage(reason, "暂时无法加载收藏作品"));
    }
  }

  async function copyPlanToNewConversation() {
    if (!plan) return;
    setError("");
    try {
      const created = await api.createConversation("复制的音乐冥想");
      const message = await api.sendMessage(
        created.id,
        "我想沿用上一段音乐冥想的设置，在这里继续说说我此刻的感受。",
      );
      await api.createPlanDraft(created.id, {
        message_id: message.id,
        credential_mode: plan.credential_mode,
      });
      await api.updatePlanDraft(created.id, {
        duration_minutes: plan.duration_minutes,
        music_source: plan.music_source,
        target_emotion: plan.target_emotion,
        credential_mode: plan.credential_mode,
        voice_mode: plan.voice_mode,
        selected_voice_id: plan.selected_voice_id,
        selected_music_asset_id: plan.selected_music_asset_id,
        guidance_style: plan.guidance_style,
        language_density: plan.language_density,
      });
      setView("chat");
      await refreshHistory();
      await loadConversation(created.id);
    } catch (reason) {
      setError(errorMessage(reason, "暂时无法复制设置"));
    }
  }

  function newConversation() {
    pollGeneration.current += 1;
    pollNow.current = null;
    if (polling.current) clearTimeout(polling.current);
    setView("chat");
    setConversationId(null);
    setMessages([]);
    setMessageId(null);
    setDraft("");
    setStream("");
    setPlan(null);
    setJobState("idle");
    setJobId(null);
    setJobEvents([]);
    setWorkId(null);
    setWorkTitle("我的音乐冥想");
    setWorkFavorite(false);
    setFailure("");
    setError("");
    setDrawer(false);
  }

  const visibleHistory = (showTrash ? trash : conversations).filter((item) =>
    item.title.toLocaleLowerCase("zh-CN").includes(search.toLocaleLowerCase("zh-CN")),
  );

  function updateEditablePlan(next: React.SetStateAction<PlanDraft>) {
    const previous = latestPlanRef.current;
    if (!previous) return;
    const resolved = typeof next === "function" ? next(previous) : next;
    latestPlanRef.current = resolved;
    setPlan(resolved);
    if (!conversationId || !resolved.id) return;
    if (planSaveTimer.current) clearTimeout(planSaveTimer.current);
    planSaveTimer.current = setTimeout(() => {
      void api.updatePlanDraft(conversationId, {
        duration_minutes: resolved.duration_minutes,
        music_source: resolved.music_source,
        target_emotion: resolved.target_emotion,
        credential_mode: resolved.credential_mode,
        voice_mode: resolved.voice_mode,
        selected_voice_id: resolved.selected_voice_id,
        selected_music_asset_id: resolved.selected_music_asset_id,
        guidance_style: resolved.guidance_style,
        language_density: resolved.language_density,
      });
    }, 300);
  }

  return (
    <div className={`app-shell ${track ? "has-global-player" : ""}`}>
      <HistorySidebar
        open={drawer}
        onClose={() => setDrawer(false)}
        items={visibleHistory}
        selectedId={conversationId}
        search={search}
        setSearch={setSearch}
        showTrash={showTrash}
        setShowTrash={setShowTrash}
        onNew={newConversation}
        onLoad={(id) => {
          setView("chat");
          void loadConversation(id);
        }}
        onRename={renameConversation}
        onDelete={deleteConversation}
        onRestore={restoreConversation}
        onWorks={() => void openFavoriteWorks()}
        onAssets={() => {
          setView("assets");
          setDrawer(false);
        }}
        onLogout={async () => {
          window.dispatchEvent(new Event("aimusicmed:logout"));
          for (let index = window.localStorage.length - 1; index >= 0; index--) {
            const key = window.localStorage.key(index);
            if (key?.startsWith("aimusicmed:position:"))
              window.localStorage.removeItem(key);
          }
          setTrack(null);
          await api.logout().catch(() => undefined);
          window.location.replace("/login");
        }}
        user={user}
      />
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
              aria-label="打开历史会话"
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
              onClick={() => {
                setView("chat");
                setCompletionUnread(false);
                window.localStorage.setItem(
                  "aimusicmed:last-completion-seen",
                  String(Math.floor(Date.now() / 1000)),
                );
              }}
            >
              冥想 {completionUnread && <i className="unread-dot" />}
            </button>
            <button
              className={view === "api" ? "active" : ""}
              onClick={() => setView("api")}
            >
              我的 API
            </button>
            <button
              className={view === "assets" ? "active" : ""}
              onClick={() => setView("assets")}
            >
              我的素材
            </button>
            <button
              className={view === "works" ? "active" : ""}
              onClick={() => void openFavoriteWorks()}
            >
              收藏作品
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
            messages={messages}
            draft={draft}
            setDraft={setDraft}
            stream={stream}
            streaming={streaming}
            error={error}
            send={send}
            canPlan={Boolean(messageId)}
            plan={plan}
            setPlan={updateEditablePlan}
            planning={planning}
            finishVenting={finishVenting}
            jobState={jobState}
            jobEvents={jobEvents}
            jobCreatedAt={jobCreatedAt}
            startJob={startJob}
            starting={starting}
            cancelJob={cancelJob}
            retryJob={retryJob}
            copyPlanToNewConversation={copyPlanToNewConversation}
            editAfterFailure={() => void editFailedJob()}
            failure={failure}
            workId={workId}
            workFavorite={workFavorite}
            onPlay={(id) => {
              setCompletionUnread(false);
              window.localStorage.setItem(
                "aimusicmed:last-completion-seen",
                String(Math.floor(Date.now() / 1000)),
              );
              setTrack({ workId: id, title: workTitle });
            }}
            notifyOnComplete={notifyOnComplete}
            setNotifyOnComplete={async (enabled) => {
              setNotifyOnComplete(enabled);
              if (!enabled) return;
              completionAudio.current ??= new AudioContext();
              await completionAudio.current.resume().catch(() => undefined);
              if (
                typeof Notification !== "undefined" &&
                Notification.permission === "default"
              ) {
                await Notification.requestPermission();
              }
            }}
            voiceCache={availableVoices}
            trackCache={availableTracks}
          />
        )}
        {view === "api" && <ApiSettings />}
        {view === "assets" && <UserAssets />}
        {view === "works" && (
          <FavoriteWorksView
            works={favoriteWorks}
            error={error}
            onPlay={(item) =>
              setTrack({ workId: item.id, title: item.title || "我的音乐冥想" })
            }
            onUnfavorite={async (item) => {
              await api.favoriteWork(item.id, false);
              const result = await api.listWorks(true);
              setFavoriteWorks(result.items);
            }}
          />
        )}
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
              void refreshHistory();
            }}
            onSkip={() => {
              setView("chat");
              window.history.replaceState({}, "", "/app");
            }}
          />
        )}
        {view === "admin" && user?.role === "admin" && <OperationsAdmin />}
      </main>
      <GlobalPlayer track={track} onClose={() => setTrack(null)} />
    </div>
  );
}

function HistorySidebar({
  open,
  onClose,
  items,
  selectedId,
  search,
  setSearch,
  showTrash,
  setShowTrash,
  onNew,
  onLoad,
  onRename,
  onDelete,
  onRestore,
  onWorks,
  onAssets,
  onLogout,
  user,
}: {
  open: boolean;
  onClose: () => void;
  items: Conversation[];
  selectedId: string | null;
  search: string;
  setSearch: (value: string) => void;
  showTrash: boolean;
  setShowTrash: (value: boolean) => void;
  onNew: () => void;
  onLoad: (id: string) => void;
  onRename: (item: Conversation) => void;
  onDelete: (item: Conversation) => void;
  onRestore: (item: Conversation) => void;
  onWorks: () => void;
  onAssets: () => void;
  onLogout: () => void;
  user: User | null;
}) {
  const groups = useMemo(() => {
    const today = new Date();
    const key = (item: Conversation) => {
      const date = new Date(item.updated_at * 1000);
      if (date.toDateString() === today.toDateString()) return "今天";
      const yesterday = new Date(today);
      yesterday.setDate(today.getDate() - 1);
      if (date.toDateString() === yesterday.toDateString()) return "昨天";
      if (today.getTime() - date.getTime() < 7 * 86400000) return "最近 7 天";
      return date.toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "long",
      });
    };
    return items.reduce<Record<string, Conversation[]>>((result, item) => {
      (result[key(item)] ??= []).push(item);
      return result;
    }, {});
  }, [items]);

  return (
    <aside className={`sidebar ${open ? "open" : ""}`}>
      <div className="sidebar-head">
        <Brand />
        <button className="drawer-close" onClick={onClose} aria-label="关闭">
          ×
        </button>
      </div>
      <button className="new-chat" onClick={onNew}>
        <span>＋</span> 新建音乐冥想
      </button>
      <button className="works-shortcut" onClick={onWorks}>
        <span>★</span> 收藏作品
      </button>
      <button className="works-shortcut" onClick={onAssets}>
        <span>♫</span> 我的音色与曲库
      </button>
      <label className="search-box">
        <span>⌕</span>
        <input
          aria-label="搜索历史会话"
          placeholder="搜索你的会话"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      <div className="history-mode">
        <button
          className={!showTrash ? "active" : ""}
          onClick={() => setShowTrash(false)}
        >
          会话
        </button>
        <button
          className={showTrash ? "active" : ""}
          onClick={() => setShowTrash(true)}
        >
          回收站
        </button>
      </div>
      <nav className="conversation-list" aria-label="历史会话">
        {Object.entries(groups).map(([label, group]) => (
          <div className="history-group" key={label}>
            <div className="history-label">{label}</div>
            {group.map((item) => (
              <div
                className={`history-item ${selectedId === item.id ? "selected" : ""}`}
                key={item.id}
              >
                {showTrash ? (
                  <div className="history-title">
                    <strong>{item.title}</strong>
                    <small>
                      {new Date(item.updated_at * 1000).toLocaleDateString(
                        "zh-CN",
                      )}
                    </small>
                  </div>
                ) : (
                  <button
                    className="history-title"
                    onClick={() => onLoad(item.id)}
                  >
                    <strong>{item.title}</strong>
                    <small>
                      {new Date(item.updated_at * 1000).toLocaleDateString(
                        "zh-CN",
                      )}
                    </small>
                  </button>
                )}
                <span className="history-actions">
                  {showTrash ? (
                    <button onClick={() => onRestore(item)}>恢复</button>
                  ) : (
                    <>
                      <button
                        aria-label={`重命名 ${item.title}`}
                        onClick={() => onRename(item)}
                      >
                        ✎
                      </button>
                      <button
                        aria-label={`删除 ${item.title}`}
                        onClick={() => onDelete(item)}
                      >
                        ⌫
                      </button>
                    </>
                  )}
                </span>
              </div>
            ))}
          </div>
        ))}
        {!items.length && (
          <p className="history-empty">
            {search ? "没有匹配的会话" : showTrash ? "回收站为空" : "还没有会话"}
          </p>
        )}
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
        <div className="profile">
          <span className="avatar">
            {user?.email.slice(0, 1).toUpperCase() ?? "我"}
          </span>
          <span>
            <strong>{user?.email ?? "正在加载账号…"}</strong>
            <small>{user?.role === "admin" ? "管理员" : "受邀用户"}</small>
          </span>
          <button className="profile-logout" onClick={onLogout}>
            退出
          </button>
        </div>
      </div>
    </aside>
  );
}

function ChatView({
  messages,
  draft,
  setDraft,
  stream,
  streaming,
  error,
  send,
  canPlan,
  plan,
  setPlan,
  planning,
  finishVenting,
  jobState,
  jobEvents,
  jobCreatedAt,
  startJob,
  starting,
  cancelJob,
  retryJob,
  copyPlanToNewConversation,
  editAfterFailure,
  failure,
  workId,
  workFavorite,
  onPlay,
  notifyOnComplete,
  setNotifyOnComplete,
  voiceCache,
  trackCache,
}: {
  messages: Message[];
  draft: string;
  setDraft: (value: string) => void;
  stream: string;
  streaming: boolean;
  error: string;
  send: (event?: FormEvent) => void;
  canPlan: boolean;
  plan: PlanDraft | null;
  setPlan: React.Dispatch<React.SetStateAction<PlanDraft>>;
  planning: boolean;
  finishVenting: () => void;
  jobState: JobState;
  jobEvents: JobEvent[];
  jobCreatedAt: number | null;
  startJob: () => void;
  starting: boolean;
  cancelJob: () => void;
  retryJob: () => void;
  copyPlanToNewConversation: () => void;
  editAfterFailure: () => void;
  failure: string;
  workId: string | null;
  workFavorite: boolean;
  onPlay: (workId: string) => void;
  notifyOnComplete: boolean;
  setNotifyOnComplete: (enabled: boolean) => void;
  voiceCache: VoiceAsset[];
  trackCache: MusicTrack[];
}) {
  const hasMessages = messages.length > 0;
  return (
    <div className="chat-layout">
      <div className="chat-scroll">
        <div className="chat-column">
          {!hasMessages ? (
            <section className="empty-chat">
              <div className="breathing-logo">
                <Brand compact />
              </div>
              <p className="overline">欢迎回来</p>
              <h1>此刻，你的心情怎么样？</h1>
              <p>不必急着得出结论。先说说发生了什么，我会陪你慢慢梳理。</p>
              <div className="prompt-grid">
                {prompts.map((prompt, index) => (
                  <button key={prompt} onClick={() => setDraft(prompt)}>
                    <span className={`prompt-icon p${index}`}>○</span>
                    {prompt}
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
                <div className="message assistant-message" aria-live="polite">
                  <span className="assistant-avatar">
                    <Brand compact />
                  </span>
                  <div>
                    <p>
                      {stream || "我在听…"}
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
              {!plan && jobState === "idle" && !streaming && (
                <section className="finish-venting">
                  <p>如果还有想说的，可以继续。等你觉得表达完整了，再开始规划。</p>
                  <button
                    className="button"
                    disabled={!canPlan || planning}
                    onClick={finishVenting}
                  >
                    {planning ? "正在为你规划…" : "我说完了，为我规划音乐冥想"}
                  </button>
                </section>
              )}
              {plan && jobState === "idle" && (
                <PlanCard
                  plan={plan}
                  setPlan={setPlan}
                  onStart={startJob}
                  starting={starting}
                  voiceCache={voiceCache}
                  trackCache={trackCache}
                />
              )}
              {jobState === "running" && (
                <ProgressCard
                  events={jobEvents}
                  createdAt={jobCreatedAt}
                  onCancel={cancelJob}
                  notifyOnComplete={notifyOnComplete}
                  setNotifyOnComplete={setNotifyOnComplete}
                />
              )}
              {(jobState === "failed" || jobState === "cancelled") && (
                <FailureCard
                  message={failure}
                  onRetry={retryJob}
                  onEdit={editAfterFailure}
                />
              )}
              {jobState === "done" && workId && (
                <WorkCard
                  workId={workId}
                  initialFavorite={workFavorite}
                  onPlay={onPlay}
                  onCopy={copyPlanToNewConversation}
                />
              )}
            </>
          )}
        </div>
      </div>
      <form className="composer" onSubmit={send}>
        <div className="composer-inner">
          <textarea
            value={draft}
            maxLength={2000}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                if (draft.trim() && !streaming) send();
              }
            }}
            placeholder={
              plan
                ? "继续对话也可以修改方案，例如“改成 10 分钟，少一点语言”…"
                : "慢慢说，我在听…"
            }
            aria-label="描述你现在的感受"
          />
          <div className="composer-tools">
            <span className="conversation-phase">
              {plan ? "可用对话或控件修改方案" : "倾诉阶段 · 暂不生成"}
            </span>
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
  starting,
  voiceCache,
  trackCache,
}: {
  plan: PlanDraft;
  setPlan: React.Dispatch<React.SetStateAction<PlanDraft>>;
  onStart: () => void;
  starting: boolean;
  voiceCache: VoiceAsset[];
  trackCache: MusicTrack[];
}) {
  const availableVoices = voiceCache;
  const availableTracks = trackCache;
  const field = <K extends keyof PlanDraft>(key: K, value: PlanDraft[K]) =>
    setPlan((prev) => ({ ...prev, [key]: value }));
  return (
    <section className="plan-card phase-two-plan">
      <header>
        <div>
          <span className="card-icon">⌁</span>
          <span>
            <small>根据这段对话为你规划</small>
            <strong>{plan.summary ?? "从此刻出发，慢慢抵达想去的情绪"}</strong>
          </span>
        </div>
        <span className="soft-badge">对话与控件同步</span>
      </header>
      <div className="plan-fields">
        <label>
          希望抵达
          <select
            value={plan.target_emotion}
            onChange={(event) =>
              field(
                "target_emotion",
                event.target.value as PlanDraft["target_emotion"],
              )
            }
          >
            <option value="auto">自动推荐</option>
            <option>平静</option>
            <option>喜悦</option>
            <option>友爱</option>
            <option>自信</option>
          </select>
        </label>
        <label>
          时长
          <select
            value={plan.duration_minutes}
            onChange={(event) =>
              field("duration_minutes", Number(event.target.value))
            }
          >
            {[3, 5, 10, 15].map((minutes) => (
              <option value={minutes} key={minutes}>
                {minutes} 分钟
              </option>
            ))}
          </select>
        </label>
        <label>
          音乐
          <select
            value={plan.music_source}
            onChange={(event) => {
              const musicSource =
                event.target.value as PlanDraft["music_source"];
              setPlan({
                ...plan,
                music_source: musicSource,
                selected_music_asset_id:
                  musicSource === "library"
                    ? plan.selected_music_asset_id
                    : null,
              });
            }}
          >
            <option value="library">内置曲库</option>
            <option value="ai">AI 生成</option>
          </select>
        </label>
        {plan.music_source === "library" && (
          <label>
            曲目
            <select
              value={plan.selected_music_asset_id ?? ""}
              onChange={(event) =>
                field("selected_music_asset_id", event.target.value || null)
              }
            >
              <option value="">系统自动选择（优先私人曲库）</option>
              {availableTracks.map((track) => (
                <option value={track.id} key={track.id}>
                  {track.name}（{track.scope === "private" ? "私人" : "公共"} ·{" "}
                  {track.primary_emotion}）
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          引导声音
          <select
            value={
              plan.voice_mode === "pure_music"
                ? "pure_music"
                : plan.selected_voice_id ?? "female-chengshu-jingpin"
            }
            onChange={(event) => {
              if (event.target.value === "pure_music")
                setPlan({
                  ...plan,
                  voice_mode: "pure_music",
                  selected_voice_id: null,
                });
              else
                setPlan({
                  ...plan,
                  voice_mode: "tts",
                  selected_voice_id: event.target.value,
                });
            }}
          >
            <option value="female-chengshu-jingpin">
              成熟温柔女声（精品）
            </option>
            {availableVoices.map((voice) => (
              <option value={voice.id} key={voice.id}>
                {voice.name}（我的音色）
              </option>
            ))}
            <option value="pure_music">纯音乐，不要语音</option>
          </select>
        </label>
        <label>
          引导方式
          <select
            value={plan.guidance_style ?? "auto"}
            onChange={(event) => field("guidance_style", event.target.value)}
          >
            <option value="auto">自动推荐</option>
            <option value="breath_awareness">呼吸觉察</option>
            <option value="body_scan">身体扫描</option>
            <option value="gentle_companionship">温柔陪伴</option>
            <option value="positive_imagery">积极意象</option>
          </select>
        </label>
        <label>
          语言密度
          <select
            value={plan.language_density ?? "balanced"}
            onChange={(event) => field("language_density", event.target.value)}
          >
            <option value="balanced">平衡语言与音乐</option>
            <option value="less_language">减少语言、留更多纯音乐空间</option>
          </select>
        </label>
      </div>
      <details>
        <summary>高级设置</summary>
        <div className="detail-fields">
          <label>
            自定义时长（3–15 分钟）
            <input
              type="number"
              min="3"
              max="15"
              step="1"
              value={plan.duration_minutes}
              onChange={(event) =>
                field(
                  "duration_minutes",
                  Math.max(3, Math.min(15, Number(event.target.value))),
                )
              }
            />
          </label>
          <label>
            API 模式
            <select
              value={plan.credential_mode}
              onChange={(event) =>
                field(
                  "credential_mode",
                  event.target.value as PlanDraft["credential_mode"],
                )
              }
            >
              <option value="platform">平台额度</option>
              <option value="byok">使用我的 API</option>
            </select>
          </label>
        </div>
      </details>
      <footer>
        <span>
          <b>方案尚未生成</b>
          <small>点击后方案锁定并启动后台任务</small>
        </span>
        <button className="button" disabled={starting} onClick={onStart}>
          {starting ? "正在启动…" : "开始生成音乐冥想"} <span>→</span>
        </button>
      </footer>
    </section>
  );
}

function ProgressCard({
  events,
  createdAt,
  onCancel,
  notifyOnComplete,
  setNotifyOnComplete,
}: {
  events: JobEvent[];
  createdAt: number | null;
  onCancel: () => void;
  notifyOnComplete: boolean;
  setNotifyOnComplete: (enabled: boolean) => void;
}) {
  const [now, setNow] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const latest = events.at(-1);
  const elapsed = createdAt
    ? Math.max(0, Math.floor(now / 1000 - createdAt))
    : 0;
  const percent =
    latest?.current != null && latest.total
      ? Math.round((latest.current / latest.total) * 100)
      : null;
  const stages = Array.from(
    new Map(events.map((event) => [event.stage, event])).values(),
  ).slice(-5);
  return (
    <section className="progress-card phase-two-progress" aria-live="polite">
      <div className="progress-orb">
        <i />
        <span>♫</span>
      </div>
      <div className="progress-content">
        <header>
          <div>
            <small>正在生成你的音乐冥想</small>
            <strong>{latest?.message || stageLabel(latest?.stage)}</strong>
          </div>
          <span>已用时 {formatTime(elapsed)}</span>
        </header>
        {percent != null && (
          <div className="real-progress">
            <span style={{ width: `${percent}%` }} />
            <small>
              第 {latest?.current} / {latest?.total} 项 · {percent}%
            </small>
          </div>
        )}
        <ol className="event-stages">
          {stages.map((event, index) => (
            <li
              className={index === stages.length - 1 ? "current" : "done"}
              key={event.id}
            >
              <i>{index === stages.length - 1 ? "•" : "✓"}</i>
              <span>{stageLabel(event.stage)}</span>
            </li>
          ))}
        </ol>
        <p>
          可以关闭网页，任务会继续。重新打开后会从服务器恢复真实状态。
          <button className="cancel-link" onClick={onCancel}>
            取消生成
          </button>
        </p>
        <label className="notification-option">
          <input
            type="checkbox"
            checked={notifyOnComplete}
            onChange={(event) => setNotifyOnComplete(event.target.checked)}
          />
          完成提醒（轻提示音；允许通知后，页面在后台也会提醒）
        </label>
      </div>
    </section>
  );
}

function FailureCard({
  message,
  onRetry,
  onEdit,
}: {
  message: string;
  onRetry: () => void;
  onEdit: () => void;
}) {
  return (
    <section className="failure-card" role="alert">
      <span className="failure-icon">↻</span>
      <div>
        <small>生成未完成</small>
        <h3>这次没有顺利完成，但你的方案还在</h3>
        <p>{message}</p>
        <div>
          <button className="button" onClick={onRetry}>
            按原方案重试
          </button>
          <button className="secondary-button" onClick={onEdit}>
            修改方案后重试
          </button>
        </div>
      </div>
    </section>
  );
}

function WorkCard({
  workId,
  initialFavorite,
  onPlay,
  onCopy,
}: {
  workId: string;
  initialFavorite: boolean;
  onPlay: (workId: string) => void;
  onCopy: () => void;
}) {
  const [favorite, setFavorite] = useState(initialFavorite);
  const [error, setError] = useState("");
  async function toggleFavorite() {
    try {
      const result = await api.favoriteWork(workId, !favorite);
      setFavorite(result.is_favorite);
      setError("");
    } catch (reason) {
      setError(errorMessage(reason, "收藏操作失败"));
    }
  }
  return (
    <section className="work-card">
      <header>
        <div>
          <span className="success-mark">✓</span>
          <span>
            <small>音乐冥想已完成</small>
            <strong>你的音乐冥想</strong>
          </span>
        </div>
      </header>
      <div className="completed-play">
        <button
          className="player-button"
          aria-label="播放音乐冥想"
          onClick={() => onPlay(workId)}
        >
          ▶
        </button>
        <span>
          <strong>开始聆听</strong>
          <small>播放器会在切换页面时继续播放</small>
        </span>
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
      {error && <div className="work-error">{error}</div>}
      <footer>
        <span>普通作品音频保存 30 天，收藏后长期保留。</span>
        <button onClick={onCopy}>复制设置到新会话 →</button>
      </footer>
    </section>
  );
}

function FavoriteWorksView({
  works,
  error,
  onPlay,
  onUnfavorite,
}: {
  works: WorkSummary[];
  error: string;
  onPlay: (work: WorkSummary) => void;
  onUnfavorite: (work: WorkSummary) => Promise<void>;
}) {
  return (
    <section className="settings-page favorite-works-page">
      <header className="page-heading">
        <p>长期保留</p>
        <h1>收藏作品</h1>
        <span>即使原会话进入回收站，你收藏的音乐冥想仍可在这里播放。</span>
      </header>
      {error && <div className="settings-status">{error}</div>}
      <div className="favorite-work-grid">
        {works.map((work) => (
          <article key={work.id}>
            <span className="favorite-work-cover">♫</span>
            <div>
              <strong>{work.title || "我的音乐冥想"}</strong>
              <small>
                {new Date(work.created_at * 1000).toLocaleDateString("zh-CN")}
                {" · "}
                {work.audio_available ? "可播放" : "音频已过期"}
              </small>
            </div>
            <button
              className="player-button"
              disabled={!work.audio_available}
              onClick={() => onPlay(work)}
              aria-label={`播放 ${work.title}`}
            >
              ▶
            </button>
            <button
              className="unfavorite-button"
              onClick={() => void onUnfavorite(work)}
            >
              取消收藏
            </button>
          </article>
        ))}
      </div>
      {!works.length && (
        <div className="favorite-empty">
          <span>☆</span>
          <strong>还没有收藏作品</strong>
          <p>完成音乐冥想后点击收藏，它会长期保留在这里。</p>
        </div>
      )}
    </section>
  );
}

function GlobalPlayer({
  track,
  onClose,
}: {
  track: PlayerTrack;
  onClose: () => void;
}) {
  if (!track) return null;
  return (
    <ActiveGlobalPlayer
      key={track.workId}
      track={track}
      onClose={onClose}
    />
  );
}

function ActiveGlobalPlayer({
  track,
  onClose,
}: {
  track: NonNullable<PlayerTrack>;
  onClose: () => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentTimeRef = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [muted, setMuted] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [seeking, setSeeking] = useState(false);
  const [seekTime, setSeekTime] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let lastWritten = -1;
    const id = setInterval(() => {
      const audio = audioRef.current;
      if (!audio || audio.paused) return;
      const pos = Math.floor(audio.currentTime);
      if (pos === lastWritten) return;
      lastWritten = pos;
      window.localStorage.setItem(
        `aimusicmed:position:${track.workId}`,
        String(audio.currentTime),
      );
    }, 3000);
    return () => clearInterval(id);
  }, [track.workId]);

  useEffect(() => {
    const audioNode = audioRef.current;
    const clearForLogout = () => {
      const audio = audioNode;
      if (!audio) return;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    };
    window.addEventListener("aimusicmed:logout", clearForLogout);
    return () => {
      window.removeEventListener("aimusicmed:logout", clearForLogout);
      audioNode?.pause();
    };
  }, []);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);

  async function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    try {
      if (audio.paused) {
        await audio.play();
      } else {
        audio.pause();
      }
    } catch {
      setError("音频暂时无法播放，请稍后重试或下载收听。");
    }
  }

  function jump(delta: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(
      0,
      Math.min(duration || Number.MAX_SAFE_INTEGER, audio.currentTime + delta),
    );
  }

  function commitSeek(value: number) {
    const audio = audioRef.current;
    if (!audio) return;
    const resume = !audio.paused;
    audio.currentTime = value;
    currentTimeRef.current = value;
    setCurrentTime(value);
    setSeeking(false);
    if (resume) void audio.play();
  }

  return (
    <section className={`global-player ${expanded ? "expanded" : ""}`}>
      <audio
        ref={audioRef}
        src={api.downloadUrl(track.workId, "mp3")}
        preload="metadata"
        muted={muted}
        onLoadedMetadata={(event) => {
          const media = event.currentTarget;
          setDuration(media.duration || 0);
          const stored = Number(
            window.localStorage.getItem(
              `aimusicmed:position:${track.workId}`,
            ) ?? 0,
          );
          const restored = Number.isFinite(stored) ? stored : 0;
          const saved = Math.min(restored, media.duration || restored);
          media.currentTime = saved;
          currentTimeRef.current = saved;
          setCurrentTime(saved);
          setSeekTime(saved);
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(event) => {
          if (!seeking) {
            currentTimeRef.current = event.currentTarget.currentTime;
            setCurrentTime(event.currentTarget.currentTime);
            setSeekTime(event.currentTarget.currentTime);
          }
        }}
      />
      <button
        className="mobile-player-expand"
        aria-label={expanded ? "收起播放器" : "展开播放器"}
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? "⌄" : "⌃"}
      </button>
      <div className="global-track">
        <span className="global-cover">♫</span>
        <span>
          <strong>{track.title}</strong>
          <small>{playing ? "正在播放" : "已暂停"}</small>
        </span>
      </div>
      <div className="global-controls">
        <button onClick={() => jump(-15)} aria-label="后退 15 秒">
          ↶<small>15</small>
        </button>
        <button className="global-play" onClick={() => void toggle()}>
          {playing ? "Ⅱ" : "▶"}
        </button>
        <button onClick={() => jump(15)} aria-label="前进 15 秒">
          ↷<small>15</small>
        </button>
      </div>
      <div className="global-timeline">
        <span>{formatTime(seeking ? seekTime : currentTime)}</span>
        <input
          type="range"
          min="0"
          max={duration || 0}
          step="0.1"
          value={Math.min(seekTime, duration || 0)}
          aria-label="播放进度"
          aria-valuetext={`${formatTime(seekTime)} / ${formatTime(duration)}`}
          onPointerDown={() => setSeeking(true)}
          onChange={(event) => {
            setSeeking(true);
            setSeekTime(Number(event.target.value));
          }}
          onPointerUp={(event) =>
            commitSeek(Number(event.currentTarget.value))
          }
          onPointerCancel={(event) =>
            commitSeek(Number(event.currentTarget.value))
          }
          onTouchEnd={(event) =>
            commitSeek(Number(event.currentTarget.value))
          }
          onBlur={(event) => {
            if (seeking) commitSeek(Number(event.currentTarget.value));
          }}
          onKeyUp={(event) => {
            if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
              commitSeek(Number(event.currentTarget.value));
          }}
          style={{
            background: `linear-gradient(to right, var(--primary) ${duration ? (seekTime / duration) * 100 : 0}%, var(--line) 0)`,
            backgroundSize: "100% 4px",
            backgroundPosition: "center",
            backgroundRepeat: "no-repeat",
          }}
        />
        <span>{duration ? formatTime(duration) : "--:--"}</span>
      </div>
      <div className="global-volume">
        <button onClick={() => setMuted(!muted)} aria-label="静音">
          {muted || volume === 0 ? "🔇" : "◖))"}
        </button>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={volume}
          aria-label="音量"
          onChange={(event) => {
            setVolume(Number(event.target.value));
            setMuted(false);
          }}
        />
        <small className="ios-volume-note">iPhone 请使用机身音量键</small>
      </div>
      <button
        className="global-close"
        aria-label="关闭播放器"
        onClick={() => {
          audioRef.current?.pause();
          onClose();
        }}
      >
        ×
      </button>
      {error && <div className="global-player-error">{error}</div>}
    </section>
  );
}

function stageLabel(stage?: string) {
  const labels: Record<string, string> = {
    queued: "等待开始",
    understanding: "理解你的表达",
    music: "准备三阶段音乐",
    guidance: "生成冥想引导",
    speech: "生成引导语音",
    mixing: "混合音乐与语音",
    exporting: "导出作品",
    complete: "生成完成",
  };
  return labels[stage ?? ""] ?? stage ?? "正在准备";
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds)) return "0:00";
  return `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
}
