"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  api,
  AdminOpsSnapshot,
  AdminUser,
  ApiError,
  AssetQuota,
  MusicTrack,
  SiteNotification,
  VoiceAsset,
} from "../lib/api";
import { zhCN } from "../lib/copy.zh-CN";

const emptyQuota: AssetQuota = {
  voice_slots_used: 0,
  voice_slots_limit: 3,
  clone_requests_used_30d: 0,
  clone_requests_limit_30d: 3,
  private_music_bytes_used: 0,
  private_music_bytes_limit: 1024 * 1024 * 1024,
};

const message = (reason: unknown, fallback: string) =>
  (reason as ApiError)?.message ?? fallback;

export function UserAssets() {
  const [tab, setTab] = useState<"voices" | "music" | "notifications">(
    "voices",
  );
  const [quota, setQuota] = useState(emptyQuota);
  const [voices, setVoices] = useState<VoiceAsset[]>([]);
  const [tracks, setTracks] = useState<MusicTrack[]>([]);
  const [notifications, setNotifications] = useState<SiteNotification[]>([]);
  const [status, setStatus] = useState("");

  async function refresh() {
    const results = await Promise.allSettled([
      api.assetQuota(),
      api.listVoices(),
      api.listMusicTracks("private"),
      api.notifications(),
    ]);
    if (results[0].status === "fulfilled") setQuota(results[0].value);
    if (results[1].status === "fulfilled") setVoices(results[1].value.items);
    if (results[2].status === "fulfilled") setTracks(results[2].value.items);
    if (results[3].status === "fulfilled")
      setNotifications(results[3].value.items);
  }

  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([
      api.assetQuota(),
      api.listVoices(),
      api.listMusicTracks("private"),
      api.notifications(),
    ]).then((results) => {
      if (cancelled) return;
      if (results[0].status === "fulfilled") setQuota(results[0].value);
      if (results[1].status === "fulfilled") setVoices(results[1].value.items);
      if (results[2].status === "fulfilled") setTracks(results[2].value.items);
      if (results[3].status === "fulfilled")
        setNotifications(results[3].value.items);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="settings-page operations-page">
      <header className="page-heading">
        <p>{zhCN.assets.eyebrow}</p>
        <h1>{zhCN.assets.title}</h1>
        <span>{zhCN.assets.intro}</span>
      </header>
      <AssetQuotaCards quota={quota} />
      <nav className="operations-tabs" aria-label="素材分类">
        {([
          ["voices", zhCN.assets.voices],
          ["music", zhCN.assets.music],
          ["notifications", zhCN.assets.notifications],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
            {id === "notifications" &&
              notifications.some((item) => !item.read_at) && (
                <i className="unread-dot" />
              )}
          </button>
        ))}
      </nav>
      {status && <div className="settings-status">{status}</div>}
      {tab === "voices" && (
        <VoiceManager
          voices={voices}
          quota={quota}
          onChanged={() => void refresh()}
          setStatus={setStatus}
        />
      )}
      {tab === "music" && (
        <MusicManager
          tracks={tracks}
          onChanged={() => void refresh()}
          setStatus={setStatus}
        />
      )}
      {tab === "notifications" && (
        <NotificationCenter
          items={notifications}
          onChanged={() => void refresh()}
        />
      )}
    </section>
  );
}

function AssetQuotaCards({ quota }: { quota: AssetQuota }) {
  const storagePercent = quota.private_music_bytes_limit
    ? Math.min(
        100,
        (quota.private_music_bytes_used / quota.private_music_bytes_limit) * 100,
      )
    : 0;
  return (
    <div className="asset-quota-grid">
      <article>
        <small>私人音色</small>
        <strong>
          {quota.voice_slots_used} / {quota.voice_slots_limit}
        </strong>
        <span>每人最多 3 个</span>
      </article>
      <article>
        <small>近 30 天克隆次数</small>
        <strong>
          {quota.clone_requests_used_30d} / {quota.clone_requests_limit_30d}
        </strong>
        <span>上传后立即创建</span>
      </article>
      <article>
        <small>私人曲库存储</small>
        <strong>{formatBytes(quota.private_music_bytes_used)}</strong>
        <div className="quota-meter">
          <i style={{ width: `${storagePercent}%` }} />
        </div>
      </article>
    </div>
  );
}

function VoiceManager({
  voices,
  quota,
  onChanged,
  setStatus,
}: {
  voices: VoiceAsset[];
  quota: AssetQuota;
  onChanged: () => void;
  setStatus: (value: string) => void;
}) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [uploading, setUploading] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !name.trim() || !consent) return;
    setUploading(true);
    try {
      await api.cloneVoice({ name: name.trim(), recording: file, consent });
      setName("");
      setFile(null);
      setConsent(false);
      setStatus("录音已上传，正在自动创建私人音色。完成后会发送站内通知。");
      onChanged();
    } catch (reason) {
      setStatus(message(reason, "音色创建暂时失败"));
    } finally {
      setUploading(false);
    }
  }
  return (
    <div className="asset-section">
      <form className="asset-upload-card" onSubmit={submit}>
        <header>
          <div>
            <h2>创建私人音色</h2>
            <p>支持清晰、无背景音乐的人声录音。原始录音会保存至你主动删除音色。</p>
          </div>
          <span className="soft-badge">{quota.voice_slots_limit - quota.voice_slots_used} 个空位</span>
        </header>
        <div className="asset-form-grid">
          <label>
            音色名称
            <input
              value={name}
              maxLength={30}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：我的温柔旁白"
            />
          </label>
          <label className="file-picker">
            原始录音
            <input
              type="file"
              accept="audio/wav,audio/mpeg,audio/mp4,audio/x-m4a"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <span>{file?.name ?? "选择 WAV、MP3 或 M4A"}</span>
          </label>
        </div>
        {file && <LocalFileAudio file={file} />}
        <label className="authorization-check">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
          />
          <span>{zhCN.assets.cloneDeclaration}</span>
        </label>
        <button
          className="button"
          disabled={
            uploading ||
            !file ||
            !name.trim() ||
            !consent ||
            quota.voice_slots_used >= quota.voice_slots_limit ||
            quota.clone_requests_used_30d >= quota.clone_requests_limit_30d
          }
        >
          {uploading ? "正在上传…" : "上传后立即创建"}
        </button>
      </form>
      <div className="asset-list">
        {voices.map((voice) => (
          <article key={voice.id}>
            <span className="asset-icon">声</span>
            <div>
              <strong>{voice.name}</strong>
              <small>
                {voice.status === "ready"
                  ? "可使用"
                  : voice.status === "processing"
                    ? "正在创建"
                    : "创建失败"}
                {" · "}授权记录已保存
              </small>
              {voice.status === "ready" && voice.preview_available && (
                <audio
                  className="voice-preview-player"
                  controls
                  preload="none"
                  src={api.voicePreviewUrl(voice.id)}
                >
                  你的浏览器不支持音频试听。
                </audio>
              )}
            </div>
            <button
              onClick={async () => {
                if (!confirm("删除音色将同时永久删除原始录音，确定继续吗？")) return;
                try {
                  await api.deleteVoice(voice.id);
                  setStatus("音色及原始录音已删除。");
                  onChanged();
                } catch (reason) {
                  setStatus(message(reason, "删除失败"));
                }
              }}
            >
              删除
            </button>
          </article>
        ))}
        {!voices.length && <p className="asset-empty">还没有私人音色。默认使用成熟温柔女声（精品）。</p>}
      </div>
    </div>
  );
}

type MusicForm = {
  name: string;
  primaryEmotion: MusicTrack["primary_emotion"];
  tags: string;
  loudness: MusicTrack["loudness"];
  trimStart: number;
  trimEnd: number;
  fadeIn: number;
  fadeOut: number;
};

const initialMusicForm: MusicForm = {
  name: "",
  primaryEmotion: "平静",
  tags: "舒缓,自然",
  loudness: "auto",
  trimStart: 0,
  trimEnd: 0,
  fadeIn: 2,
  fadeOut: 3,
};

function MusicManager({
  tracks,
  onChanged,
  setStatus,
}: {
  tracks: MusicTrack[];
  onChanged: () => void;
  setStatus: (value: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState(initialMusicForm);
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !form.name.trim() || !consent) return;
    setSaving(true);
    try {
      await api.uploadMusicTrack({
        file,
        name: form.name.trim(),
        primary_emotion: form.primaryEmotion,
        tags: form.tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean),
        loudness: form.loudness,
        trim_start_ms: Math.round(form.trimStart * 1000),
        trim_end_ms: form.trimEnd ? Math.round(form.trimEnd * 1000) : null,
        fade_in_ms: Math.round(form.fadeIn * 1000),
        fade_out_ms: Math.round(form.fadeOut * 1000),
        consent_confirmed: consent,
      });
      setFile(null);
      setForm(initialMusicForm);
      setConsent(false);
      setStatus("音乐已加入私人曲库，编辑参数会在生成时无损应用。");
      onChanged();
    } catch (reason) {
      setStatus(message(reason, "音乐上传暂时失败"));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="asset-section">
      <form className="asset-upload-card" onSubmit={submit}>
        <header>
          <div>
            <h2>上传背景音乐</h2>
            <p>平台不推断音乐情绪；请由你指定一个主要情绪，可同时添加多个标签。</p>
          </div>
          <span className="soft-badge">私人可见</span>
        </header>
        <label className="file-picker wide">
          音频文件
          <input
            type="file"
            accept="audio/wav,audio/flac,audio/mpeg,audio/mp4,audio/x-m4a"
            onChange={(event) => {
              const selected = event.target.files?.[0] ?? null;
              setFile(selected);
              if (selected && !form.name)
                setForm((current) => ({ ...current, name: selected.name.replace(/\.[^.]+$/, "") }));
            }}
          />
          <span>{file?.name ?? "选择 WAV、FLAC、MP3 或 M4A"}</span>
        </label>
        {file && (
          <WaveformEditor
            file={file}
            trimStart={form.trimStart}
            trimEnd={form.trimEnd}
            setTrim={(trimStart, trimEnd) =>
              setForm((current) => ({ ...current, trimStart, trimEnd }))
            }
          />
        )}
        <div className="asset-form-grid music-fields">
          <label>曲名<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
          <label>主要情绪<select value={form.primaryEmotion} onChange={(event) => setForm({ ...form, primaryEmotion: event.target.value as MusicTrack["primary_emotion"] })}>{["敌意", "忧郁", "焦虑", "平静", "喜悦", "自信", "友爱"].map((emotion) => <option key={emotion}>{emotion}</option>)}</select></label>
          <label>其他标签<input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="用逗号分隔" /></label>
          <label>响度<select value={form.loudness} onChange={(event) => setForm({ ...form, loudness: event.target.value as MusicTrack["loudness"] })}><option value="auto">自动</option><option value="light">较轻</option><option value="standard">标准</option><option value="strong">较强</option></select></label>
          <label>淡入（秒）<input type="number" min="0" max="30" value={form.fadeIn} onChange={(event) => setForm({ ...form, fadeIn: Number(event.target.value) })} /></label>
          <label>淡出（秒）<input type="number" min="0" max="30" value={form.fadeOut} onChange={(event) => setForm({ ...form, fadeOut: Number(event.target.value) })} /></label>
        </div>
        <label className="authorization-check"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>{zhCN.assets.musicDeclaration}</span></label>
        <button className="button" disabled={!file || !form.name.trim() || !consent || saving}>{saving ? "正在上传…" : "保存到私人曲库"}</button>
      </form>
      <div className="asset-list music-list">
        {tracks.map((track) => (
          <article key={track.id}>
            <span className="asset-icon">♫</span><div><strong>{track.name}</strong><small>{track.primary_emotion} · {track.tags.join(" · ")} · {loudnessLabel(track.loudness)}</small><audio controls preload="none" src={api.musicTrackAudioUrl(track.id)} /></div>
            <TrackEditor track={track} onChanged={onChanged} setStatus={setStatus} />
            <button onClick={async () => { if (!confirm("确定从私人曲库删除这首音乐吗？")) return; try { await api.deleteMusicTrack(track.id); onChanged(); } catch (reason) { setStatus(message(reason, "删除失败")); } }}>删除</button>
          </article>
        ))}
        {!tracks.length && <p className="asset-empty">私人曲库为空。生成时仍可使用管理员公共曲库。</p>}
      </div>
    </div>
  );
}

function LocalFileAudio({ file }: { file: File }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(() => {
    const url = URL.createObjectURL(file);
    if (audio.current) audio.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return <audio ref={audio} controls preload="metadata" />;
}

function TrackEditor({ track, onChanged, setStatus }: { track: MusicTrack; onChanged: () => void; setStatus: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: track.name, primary_emotion: track.primary_emotion, tags: track.tags.join(","), loudness: track.loudness, trim_start_ms: track.trim_start_ms, trim_end_ms: track.trim_end_ms, fade_in_ms: track.fade_in_ms, fade_out_ms: track.fade_out_ms });
  async function save() {
    try {
      await api.updateMusicTrack(track.id, { ...form, tags: form.tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean) });
      setStatus("曲库信息与编辑参数已保存。");
      setOpen(false);
      onChanged();
    } catch (reason) { setStatus(message(reason, "编辑失败")); }
  }
  return <details className="track-editor" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}><summary>编辑</summary><div><label>曲名<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>主要情绪<select value={form.primary_emotion} onChange={(event) => setForm({ ...form, primary_emotion: event.target.value as MusicTrack["primary_emotion"] })}>{["敌意", "忧郁", "焦虑", "平静", "喜悦", "自信", "友爱"].map((emotion) => <option key={emotion}>{emotion}</option>)}</select></label><label>标签<input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} /></label><label>响度<select value={form.loudness} onChange={(event) => setForm({ ...form, loudness: event.target.value as MusicTrack["loudness"] })}><option value="auto">自动</option><option value="light">较轻</option><option value="standard">标准</option><option value="strong">较强</option></select></label><label>裁剪开始（秒）<input type="number" min="0" step="0.1" value={form.trim_start_ms / 1000} onChange={(event) => setForm({ ...form, trim_start_ms: Math.round(Number(event.target.value) * 1000) })} /></label><label>裁剪结束（秒）<input type="number" min="0" step="0.1" value={(form.trim_end_ms ?? 0) / 1000} onChange={(event) => setForm({ ...form, trim_end_ms: Math.round(Number(event.target.value) * 1000) || null })} /></label><label>淡入（秒）<input type="number" min="0" max="30" step="0.1" value={form.fade_in_ms / 1000} onChange={(event) => setForm({ ...form, fade_in_ms: Math.round(Number(event.target.value) * 1000) })} /></label><label>淡出（秒）<input type="number" min="0" max="30" step="0.1" value={form.fade_out_ms / 1000} onChange={(event) => setForm({ ...form, fade_out_ms: Math.round(Number(event.target.value) * 1000) })} /></label><button className="button" type="button" onClick={() => void save()}>保存编辑</button></div></details>;
}

function WaveformEditor({ file, trimStart, trimEnd, setTrim }: { file: File; trimStart: number; trimEnd: number; setTrim: (start: number, end: number) => void }) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [duration, setDuration] = useState(0);
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    if (audio.current) audio.current.src = objectUrl;
    let cancelled = false;
    void file.arrayBuffer().then(async (buffer) => {
      const context = new AudioContext();
      try {
        const decoded = await context.decodeAudioData(buffer.slice(0));
        if (cancelled || !canvas.current) return;
        setDuration(decoded.duration);
        const data = decoded.getChannelData(0);
        const ctx = canvas.current.getContext("2d");
        if (!ctx) return;
        const { width, height } = canvas.current;
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = "#6f9f8e";
        const step = Math.max(1, Math.floor(data.length / width));
        for (let x = 0; x < width; x++) {
          let peak = 0;
          for (let i = 0; i < step; i++) peak = Math.max(peak, Math.abs(data[x * step + i] ?? 0));
          const bar = Math.max(2, peak * height);
          ctx.fillRect(x, (height - bar) / 2, 1, bar);
        }
      } finally {
        await context.close();
      }
    }).catch(() => undefined);
    return () => { cancelled = true; URL.revokeObjectURL(objectUrl); };
  }, [file]); // The selected file owns this local preview lifecycle.
  return <div className="waveform-editor"><canvas ref={canvas} width="760" height="90" aria-label="本地波形预览" /><audio ref={audio} controls /><div><label>从<input type="number" min="0" max={duration} step="0.1" value={trimStart} onChange={(event) => setTrim(Number(event.target.value), trimEnd)} />秒</label><label>到<input type="number" min={trimStart} max={duration} step="0.1" value={trimEnd} placeholder={duration ? String(duration.toFixed(1)) : undefined} onChange={(event) => setTrim(trimStart, Number(event.target.value))} />秒</label><span>仅在本地绘制波形，不分析音乐情绪；原文件不转码。</span></div></div>;
}

function NotificationCenter({ items, onChanged }: { items: SiteNotification[]; onChanged: () => void }) {
  return <div className="notification-list">{items.map((item) => <article className={item.read_at ? "" : "unread"} key={item.id}><span>{item.kind === "success" ? "✓" : item.kind === "warning" ? "!" : "i"}</span><div><strong>{item.title}</strong><p>{item.body}</p><small>{new Date(item.created_at * 1000).toLocaleString("zh-CN")}</small></div>{!item.read_at && <button onClick={async () => { await api.markNotificationRead(item.id); onChanged(); }}>标为已读</button>}</article>)}{!items.length && <p className="asset-empty">暂时没有新通知。</p>}</div>;
}

type AdminTab = "users" | "voices" | "music" | "jobs" | "works" | "stats" | "backups" | "system" | "audit";
type SensitiveRequest = {
  action: string;
  label: string;
  execute: (token: string) => Promise<void>;
};
export function OperationsAdmin() {
  const [tab, setTab] = useState<AdminTab>("users");
  const [snapshot, setSnapshot] = useState<AdminOpsSnapshot | null>(null);
  const [status, setStatus] = useState("");
  const [sensitive, setSensitive] = useState<SensitiveRequest | null>(null);
  useEffect(() => { void api.adminOps().then(setSnapshot).catch((reason) => setStatus(message(reason, "部分运营数据接口尚未启用"))); }, [setStatus]);
  const tabs: Array<[AdminTab, string]> = [["users", "用户与额度"], ["voices", "音色"], ["music", "公共曲库"], ["jobs", "任务"], ["works", "作品"], ["stats", "匿名统计"], ["backups", "备份恢复"], ["system", "系统状态"], ["audit", "审计日志"]];
  return <section className="admin-page operations-admin"><header className="page-heading"><p>{zhCN.admin.eyebrow}</p><h1>{zhCN.admin.title}</h1><span>{zhCN.admin.intro}</span></header><nav className="admin-ops-tabs">{tabs.map(([id, label]) => <button className={tab === id ? "active" : ""} onClick={() => setTab(id)} key={id}>{label}</button>)}</nav>{status && <div className="settings-status">{status}</div>}{tab === "users" ? <AdminUsersOps requestSensitive={setSensitive} setStatus={setStatus} /> : <AdminDataPanel tab={tab} snapshot={snapshot} requestSensitive={setSensitive} />}{sensitive && <SensitiveActionDialog request={sensitive} onClose={() => setSensitive(null)} onStatus={setStatus} />}</section>;
}

function AdminUsersOps({ requestSensitive, setStatus }: { requestSensitive: (request: SensitiveRequest) => void; setStatus: (value: string) => void }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const load = () => void api.adminUsers().then((result) => setUsers(result.items)).catch((reason) => setStatus(message(reason, "用户列表加载失败")));
  useEffect(() => {
    let cancelled = false;
    void api.adminUsers().then((result) => {
      if (!cancelled) setUsers(result.items);
    }).catch((reason) => setStatus(message(reason, "用户列表加载失败")));
    return () => { cancelled = true; };
  }, [setStatus]);
  return <div className="admin-panel"><header><div><h2>邀请用户与额度</h2><p>额度调整和停用账号需要管理员邮箱二次验证码。</p></div><form className="invite-form" onSubmit={async (event) => { event.preventDefault(); try { await api.inviteUser(inviteEmail); setInviteEmail(""); setStatus("邀请验证码已发送。"); load(); } catch (reason) { setStatus(message(reason, "邀请失败")); } }}><input type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="受邀邮箱" required /><button className="button">邀请</button></form></header><div className="table-wrap"><table><thead><tr><th>邮箱</th><th>状态</th><th>每日额度</th><th>操作</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.email}</td><td>{user.status}</td><td>{user.daily_limit}</td><td><div className="admin-actions"><button onClick={() => { const value = Number(prompt("新的每日完整生成额度", String(user.daily_limit))); if (!Number.isInteger(value) || value < 0) return; requestSensitive({ action: "adjust_user_quota", label: `调整 ${user.email} 的每日额度`, execute: async (token) => { await api.updateUserQuota(user.id, value, token); load(); } }); }}>调整额度</button><button onClick={() => requestSensitive({ action: "change_user_status", label: `${user.status === "disabled" ? "启用" : "停用"} ${user.email}`, execute: async (token) => { await api.updateUserStatus(user.id, user.status === "disabled" ? "active" : "disabled", token); load(); } })}>{user.status === "disabled" ? "启用" : "停用"}</button></div></td></tr>)}</tbody></table></div></div>;
}

function SensitiveActionDialog({ request, onClose, onStatus }: { request: SensitiveRequest; onClose: () => void; onStatus: (value: string) => void }) {
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  async function sendCode() { setBusy(true); try { await api.requestAdminActionCode(request.action); setSent(true); } catch (reason) { onStatus(message(reason, "验证码发送失败")); } finally { setBusy(false); } }
  async function confirmAction() { if (!/^\d{6}$/.test(code)) return; setBusy(true); try { const verified = await api.verifyAdminActionCode(request.action, code); await request.execute(verified.action_token); onStatus(`${request.label}已完成，并写入审计日志。`); onClose(); } catch (reason) { onStatus(message(reason, "敏感操作未能完成")); } finally { setBusy(false); } }
  return <div className="sensitive-dialog-backdrop" role="presentation"><section className="sensitive-dialog" role="dialog" aria-modal="true" aria-labelledby="sensitive-title"><button className="dialog-close" onClick={onClose} aria-label="关闭">×</button><small>管理员二次验证</small><h2 id="sensitive-title">{request.label}</h2><p>为了保护用户数据，此操作需要发送到管理员邮箱的 6 位验证码。验证码 15 分钟内有效。</p>{!sent ? <button className="button" disabled={busy} onClick={() => void sendCode()}>{busy ? "正在发送…" : "发送邮箱验证码"}</button> : <><input inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} placeholder="6 位验证码" aria-label="管理员邮箱验证码" /><button className="button" disabled={busy || code.length !== 6} onClick={() => void confirmAction()}>{busy ? "正在验证…" : "验证并继续"}</button></>}</section></div>;
}

function AdminDataPanel({ tab, snapshot, requestSensitive }: { tab: Exclude<AdminTab, "users">; snapshot: AdminOpsSnapshot | null; requestSensitive: (request: SensitiveRequest) => void }) {
  const [backupFile, setBackupFile] = useState<File | null>(null);
  const values = tab === "stats" ? snapshot?.stats ?? [] : tab === "system" ? Object.entries(snapshot?.system ?? {}).map(([name, value]) => ({ name, value: String(value) })) : (snapshot?.[tab] as Array<Record<string, unknown>> | undefined) ?? [];
  const sensitive = tab === "backups";
  const backupRequest = (action: "create_backup" | "restore_backup" | "verify_backup" | "download_backup", backupId?: string) => requestSensitive({ action, label: action === "create_backup" ? "创建并导出系统备份" : action === "verify_backup" ? `完整校验备份 ${backupId}` : action === "download_backup" ? `下载加密备份包 ${backupId}` : `恢复备份 ${backupId}`, execute: async (token) => { if (action === "create_backup") await api.createBackup(token); else if (action === "download_backup" && backupId) await api.downloadBackup(backupId, token); else if (action === "verify_backup" && backupId) await api.verifyBackup(backupId, token); else if (backupId) await api.restoreBackup(backupId, token); } });
  const uploadRequest = () => {
    if (!backupFile) return;
    requestSensitive({ action: "upload_backup", label: `上传并校验 ${backupFile.name}`, execute: async (token) => { await api.uploadBackup(backupFile, token); setBackupFile(null); } });
  };
  return <div className="admin-panel ops-data-panel"><header><div><h2>{adminPanelTitle(tab)}</h2><p>{sensitive ? "创建、上传、完整校验和恢复均进入宿主安全队列；恢复需管理员邮箱二次验证码，API 不接触 Docker。" : "这里只显示运营所需信息，不展示用户聊天正文。所有删除、停用和批量操作统一使用二次验证弹窗。"}</p></div>{tab === "backups" && <div className="admin-actions"><button className="button" onClick={() => backupRequest("create_backup")}>创建并导出备份</button><label className="button secondary">选择离线包<input hidden type="file" accept=".tar.gz,application/gzip" onChange={(event) => setBackupFile(event.target.files?.[0] ?? null)} /></label><button disabled={!backupFile} onClick={uploadRequest}>{backupFile ? "上传并校验" : "尚未选择文件"}</button></div>}</header><div className="ops-records">{values.map((item, index) => { const isPackage = tab === "backups" && item.kind === "package" && item.status === "ready"; return <article key={String(item.id ?? item.name ?? index)}>{Object.entries(item).slice(0, 7).map(([key, value]) => <span key={key}><small>{key}</small><strong>{formatAdminValue(value)}</strong></span>)}{isPackage && item.id != null && <div className="admin-actions"><button onClick={() => backupRequest("download_backup", String(item.id))}>下载加密包</button><button onClick={() => backupRequest("verify_backup", String(item.id))}>完整校验</button><button onClick={() => backupRequest("restore_backup", String(item.id))}>验证并恢复</button></div>}<AdminRecordAction tab={tab} item={item} requestSensitive={requestSensitive} /></article>; })}{!values.length && <p className="asset-empty">暂无数据，或对应后端接口尚未启用。</p>}</div></div>;
}

function AdminRecordAction({ tab, item, requestSensitive }: { tab: Exclude<AdminTab, "users">; item: Record<string, unknown>; requestSensitive: (request: SensitiveRequest) => void }) {
  if (item.id == null) return null;
  const id = String(item.id);
  const actions = {
    voices: item.status === "disabled"
      ? { action: "enable_voice", label: "启用音色", execute: (token: string) => api.adminUpdateVoiceStatus(id, "active", token) }
      : { action: "disable_voice", label: "停用音色", execute: (token: string) => api.adminUpdateVoiceStatus(id, "disabled", token) },
    music: { action: "delete_public_track", label: "删除公共曲库素材", execute: (token: string) => api.adminDeleteMusicTrack(id, token) },
    jobs: { action: "cancel_job", label: "取消任务", execute: (token: string) => api.adminCancelJob(id, token) },
    works: { action: "delete_work", label: "删除作品", execute: (token: string) => api.adminDeleteWork(id, token) },
  } as const;
  const selected = tab in actions ? actions[tab as keyof typeof actions] : null;
  if (!selected) return null;
  return <button onClick={() => requestSensitive({ action: selected.action, label: `${selected.label} ${id}`, execute: selected.execute })}>{selected.label}</button>;
}

function adminPanelTitle(tab: Exclude<AdminTab, "users">) { return ({ voices: "用户音色与授权", music: "管理员公共曲库", jobs: "生成任务", works: "作品与到期状态", stats: "匿名运营统计", backups: "备份与恢复", system: "系统与供应商状态", audit: "安全审计日志" } as const)[tab]; }
function formatAdminValue(value: unknown) { if (value == null) return "—"; if (typeof value === "object") return JSON.stringify(value); return String(value); }
function formatBytes(bytes: number) { if (!bytes) return "0 MB"; return `${(bytes / 1024 / 1024).toFixed(bytes > 1024 * 1024 * 100 ? 0 : 1)} MB`; }
function loudnessLabel(value: MusicTrack["loudness"]) { return ({ auto: "自动", light: "较轻", standard: "标准", strong: "较强" } as const)[value]; }
