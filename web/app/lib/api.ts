export type ApiError = { code: string; message: string; request_id?: string };
export type User = {
  id: string;
  email: string;
  role: "user" | "admin";
  daily_limit: number;
  status?: "pending" | "active" | "disabled";
  password_configured?: boolean;
  password_setup?: "required" | "optional" | "none";
};
export type Conversation = {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  deleted_at?: number | null;
};
export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  risk_level: "normal" | "crisis";
  created_at: number;
};
export type PlanInput = {
  draft_id?: string;
  message_id: string;
  duration_minutes: number;
  music_source: "library" | "ai";
  target_emotion: "auto" | "平静" | "喜悦" | "友爱" | "自信";
  credential_mode: "platform" | "byok";
  voice_mode: "tts" | "pure_music";
  selected_voice_id?: string | null;
  selected_music_asset_id?: string | null;
  guidance_style?: string;
  language_density?: string;
};
export type PlanDraft = {
  id?: string;
  summary?: string;
  duration_minutes: number;
  music_source: "library" | "ai";
  target_emotion: "auto" | "平静" | "喜悦" | "友爱" | "自信";
  credential_mode: "platform" | "byok";
  voice_mode: "tts" | "pure_music";
  selected_voice_id?: string | null;
  selected_music_asset_id?: string | null;
  guidance_style?: string;
  language_density?: string;
  updated_at?: number;
};
export type StoredPlan = PlanInput & {
  id: string;
  status: string;
  created_at: number;
};
export type ConversationJob = {
  id: string;
  plan_id: string;
  status: string;
  progress_stage: string | null;
  created_at: number;
  finished_at: number | null;
  work_id: string | null;
  work_title?: string | null;
  is_favorite?: boolean | number | null;
};
export type ConversationDetail = {
  conversation: Conversation;
  messages: Message[];
  plans: StoredPlan[];
  jobs: ConversationJob[];
  draft?: PlanDraft | null;
};
export type JobEvent = {
  id: number;
  event_type: string;
  stage: string;
  current: number | null;
  total: number | null;
  message: string;
  created_at: number;
};
export type JobResult = {
  job: {
    id: string;
    status: string;
    progress_stage: string | null;
    created_at: number;
    finished_at: number | null;
    error_code: string | null;
  };
  events: JobEvent[];
};
export type AdminUser = {
  id: string;
  email: string;
  role: "user" | "admin";
  status: string;
  daily_limit: number;
  created_at: number;
};
export type WorkSummary = {
  id: string;
  job_id: string;
  title: string;
  expires_at: number | null;
  is_favorite: boolean;
  created_at: number;
  audio_available: boolean;
};
export type AssetQuota = {
  voice_slots_used: number;
  voice_slots_limit: number;
  clone_requests_used_30d: number;
  clone_requests_limit_30d: number;
  private_music_bytes_used: number;
  private_music_bytes_limit: number;
};
export type VoiceAsset = {
  id: string;
  name: string;
  provider_voice_id: string | null;
  status: "processing" | "ready" | "failed";
  created_at: number;
  recording_retained: boolean;
  consent_recorded_at: number;
  preview_available?: boolean;
};
export type MusicTrack = {
  id: string;
  name: string;
  scope: "private" | "public";
  primary_emotion:
    | "敌意"
    | "忧郁"
    | "焦虑"
    | "平静"
    | "喜悦"
    | "自信"
    | "友爱";
  tags: string[];
  loudness: "auto" | "light" | "standard" | "strong";
  trim_start_ms: number;
  trim_end_ms: number | null;
  fade_in_ms: number;
  fade_out_ms: number;
  duration_ms: number | null;
  created_at: number;
};
export type SiteNotification = {
  id: string;
  title: string;
  body: string;
  kind: "info" | "success" | "warning";
  read_at: number | null;
  created_at: number;
};
export type AdminOpsSnapshot = {
  voices: Array<Record<string, unknown>>;
  tracks: Array<Record<string, unknown>>;
  jobs: Array<Record<string, unknown>>;
  works: Array<Record<string, unknown>>;
  stats: Array<Record<string, unknown>>;
  backups: Array<Record<string, unknown>>;
  system: Record<string, unknown>;
  audit: Array<Record<string, unknown>>;
};

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

async function parseError(response: Response): Promise<ApiError> {
  const payload = (await response.json().catch(() => null)) as {
    error?: ApiError;
  } | null;
  return (
    payload?.error ?? {
      code: "HTTP_ERROR",
      message: `请求暂时未能完成（${response.status}）`,
    }
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function upload<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    body,
  });
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/me"),
  requestLoginCode: (
    email: string,
    purpose: "login" | "password_reset" = "login",
  ) =>
    request<{ sent: true; expires_in: number }>("/auth/code/request", {
      method: "POST",
      body: JSON.stringify({ email, purpose }),
    }),
  verifyLoginCode: (
    email: string,
    code: string,
    purpose: "login" | "password_reset" = "login",
  ) =>
    request<{
      authenticated?: true;
      password_setup?: "required" | "optional" | "none";
      reset_token?: string;
    }>("/auth/code/verify", {
      method: "POST",
      body: JSON.stringify({ email, code, purpose }),
    }),
  loginWithPassword: (email: string, password: string) =>
    request<{ authenticated: true }>("/auth/password/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  setPassword: (input: {
    password: string;
    password_confirmation: string;
    current_password?: string;
  }) =>
    request<{ password_configured: true }>("/account/password", {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  resetPassword: (input: {
    reset_token: string;
    password: string;
    password_confirmation: string;
  }) =>
    request<{ password_reset: true }>("/auth/password/reset", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  listConversations: (includeDeleted = false) =>
    request<{ items: Conversation[] }>(
      `/conversations${includeDeleted ? "?trash=true" : ""}`,
    ),
  getConversation: (id: string) =>
    request<ConversationDetail>(`/conversations/${id}`),
  createConversation: (title = "新对话") =>
    request<{ id: string; title: string }>("/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  updateConversation: (id: string, title: string) =>
    request<{ id: string; title: string }>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: string) =>
    request<{ deleted: true; purge_at?: number }>(`/conversations/${id}`, {
      method: "DELETE",
    }),
  restoreConversation: (id: string) =>
    request<{ restored: true }>(`/conversations/${id}/restore`, {
      method: "POST",
    }),
  sendMessage: (conversationId: string, content: string) =>
    request<{
      id: string;
      risk_level: "normal" | "crisis";
      crisis_help?: {
        title: string;
        message: string;
        emergency_numbers: string[];
      };
    }>(`/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  createPlan: (conversationId: string, plan: PlanInput) =>
    request<{ id: string; status: string }>(
      `/conversations/${conversationId}/plans`,
      { method: "POST", body: JSON.stringify(plan) },
    ),
  createPlanDraft: (
    conversationId: string,
    input: { message_id: string; credential_mode: "platform" | "byok" },
  ) =>
    request<PlanDraft | { draft: PlanDraft; summary?: string }>(
      `/conversations/${conversationId}/plan-draft`,
      { method: "POST", body: JSON.stringify(input) },
    ),
  updatePlanDraft: (
    conversationId: string,
    patch: Partial<
      Pick<
        PlanDraft,
        | "duration_minutes"
        | "music_source"
        | "target_emotion"
        | "credential_mode"
        | "voice_mode"
        | "selected_voice_id"
        | "selected_music_asset_id"
        | "guidance_style"
        | "language_density"
      >
    >,
  ) =>
    request<{ draft: PlanDraft }>(
      `/conversations/${conversationId}/plan-draft`,
      { method: "PATCH", body: JSON.stringify(patch) },
    ),
  createJob: (planId: string) =>
    request<{ id: string; status: string }>(`/plans/${planId}/jobs`, {
      method: "POST",
    }),
  getJob: (jobId: string) => request<JobResult>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) =>
    request<{ status: string }>(`/jobs/${jobId}/cancel`, { method: "POST" }),
  retryJob: (jobId: string) =>
    request<{ id: string; status: string }>(`/jobs/${jobId}/retry`, {
      method: "POST",
    }),
  createEditableDraftFromJob: (jobId: string) =>
    request<PlanDraft | { draft: PlanDraft }>(
      `/jobs/${jobId}/editable-draft`,
      { method: "POST" },
    ),
  saveCredentials: (credentials: {
    deepseek_api_key: string;
    minimax_api_key: string;
    elevenlabs_api_key?: string;
  }) =>
    request<{ configured: Record<string, boolean> }>("/settings/credentials", {
      method: "PUT",
      body: JSON.stringify(credentials),
    }),
  deleteCredentials: () =>
    request<void>("/settings/credentials", { method: "DELETE" }),
  favoriteWork: (workId: string, favorite: boolean) =>
    request<{ is_favorite: boolean }>(`/works/${workId}/favorite`, {
      method: favorite ? "POST" : "DELETE",
    }),
  listWorks: (favoritesOnly = false) =>
    request<{ items: WorkSummary[] }>(
      `/works${favoritesOnly ? "?favorites_only=true" : ""}`,
    ),
  assetQuota: () => request<AssetQuota>("/assets/quota"),
  listVoices: () => request<{ items: VoiceAsset[] }>("/voices"),
  cloneVoice: (input: { name: string; recording: File; consent: boolean }) => {
    const body = new FormData();
    body.set("name", input.name);
    body.set("recording", input.recording);
    body.set("consent_confirmed", String(input.consent));
    return upload<{ item: VoiceAsset }>("/voices/clone", body);
  },
  deleteVoice: (voiceId: string) =>
    request<void>(`/voices/${voiceId}`, { method: "DELETE" }),
  voicePreviewUrl: (voiceId: string) =>
    `${API_BASE}/voices/${encodeURIComponent(voiceId)}/preview`,
  listMusicTracks: (scope: "private" | "public" = "private") =>
    request<{ items: MusicTrack[] }>(`/music-library?scope=${scope}`),
  uploadMusicTrack: (input: {
    file: File;
    name: string;
    primary_emotion: MusicTrack["primary_emotion"];
    tags: string[];
    loudness: MusicTrack["loudness"];
    trim_start_ms: number;
    trim_end_ms: number | null;
    fade_in_ms: number;
    fade_out_ms: number;
    consent_confirmed: boolean;
  }) => {
    const body = new FormData();
    body.set("file", input.file);
    body.set("name", input.name);
    body.set("primary_emotion", input.primary_emotion);
    body.set("tags", JSON.stringify(input.tags));
    body.set("loudness", input.loudness);
    body.set("trim_start_ms", String(input.trim_start_ms));
    if (input.trim_end_ms != null)
      body.set("trim_end_ms", String(input.trim_end_ms));
    body.set("fade_in_ms", String(input.fade_in_ms));
    body.set("fade_out_ms", String(input.fade_out_ms));
    body.set("consent_confirmed", String(input.consent_confirmed));
    return upload<{ item: MusicTrack }>("/music-library/tracks", body);
  },
  updateMusicTrack: (trackId: string, patch: Partial<MusicTrack>) =>
    request<{ item: MusicTrack }>(`/music-library/tracks/${trackId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteMusicTrack: (trackId: string) =>
    request<void>(`/music-library/tracks/${trackId}`, { method: "DELETE" }),
  musicTrackAudioUrl: (trackId: string) =>
    `${API_BASE}/music-library/tracks/${trackId}/audio`,
  notifications: () =>
    request<{ items: SiteNotification[] }>("/notifications"),
  markNotificationRead: (notificationId: string) =>
    request<void>(`/notifications/${notificationId}/read`, { method: "POST" }),
  adminOps: async (): Promise<AdminOpsSnapshot> => {
    const [voices, tracks, jobs, works, stats, backups, system, audit] =
      await Promise.all([
        request<{ items: Array<Record<string, unknown>> }>("/admin/voices"),
        request<{ items: Array<Record<string, unknown>> }>("/admin/music-library"),
        request<{ items: Array<Record<string, unknown>> }>("/admin/jobs"),
        request<{ items: Array<Record<string, unknown>> }>("/admin/works"),
        request<{ items: Array<Record<string, unknown>> }>("/admin/stats/anonymous"),
        request<{ items: Array<Record<string, unknown>> }>("/admin/backups"),
        request<Record<string, unknown>>("/admin/system/status"),
        request<{ items: Array<Record<string, unknown>> }>("/admin/audit-log"),
      ]);
    return {
      voices: voices.items,
      tracks: tracks.items,
      jobs: jobs.items,
      works: works.items,
      stats: stats.items,
      backups: backups.items,
      system,
      audit: audit.items,
    };
  },
  requestAdminActionCode: (action: string) =>
    request<{ sent: true; expires_in: number }>(
      "/admin/sensitive-actions/code/request",
      { method: "POST", body: JSON.stringify({ action }) },
    ),
  verifyAdminActionCode: (action: string, code: string) =>
    request<{ action_token: string }>("/admin/sensitive-actions/code/verify", {
      method: "POST",
      body: JSON.stringify({ action, code }),
    }),
  createBackup: (actionToken: string) =>
    request<{ id: string; status: string }>("/admin/backups", {
      method: "POST",
      headers: { "X-Admin-Action-Token": actionToken },
    }),
  uploadBackup: async (file: File, actionToken: string) => {
    const body = new FormData();
    body.set("file", file);
    const response = await fetch(`${API_BASE}/admin/backups/upload`, {
      method: "POST",
      credentials: "include",
      headers: { "X-Admin-Action-Token": actionToken },
      body,
    });
    if (!response.ok) throw await parseError(response);
    return response.json() as Promise<{ id: string; status: string; package_id: string }>;
  },
  verifyBackup: (backupId: string, actionToken: string) =>
    request<{ id: string; status: string }>(`/admin/backups/${encodeURIComponent(backupId)}/verify`, {
      method: "POST",
      headers: { "X-Admin-Action-Token": actionToken },
    }),
  downloadBackup: async (backupId: string, actionToken: string) => {
    const response = await fetch(
      `${API_BASE}/admin/backups/${encodeURIComponent(backupId)}/download`,
      { credentials: "include", headers: { "X-Admin-Action-Token": actionToken } },
    );
    if (!response.ok) throw await parseError(response);
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = backupId;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
  },
  restoreBackup: (backupId: string, actionToken: string) =>
    request<{ id: string; status: string }>(`/admin/backups/${encodeURIComponent(backupId)}/restore`, {
      method: "POST",
      headers: { "X-Admin-Action-Token": actionToken },
    }),
  adminUpdateVoiceStatus: (
    voiceId: string,
    status: "active" | "disabled",
    actionToken: string,
  ) =>
    request<void>(`/admin/voices/${voiceId}/status`, {
      method: "PATCH",
      headers: { "X-Admin-Action-Token": actionToken },
      body: JSON.stringify({ status }),
    }),
  adminDeleteMusicTrack: (trackId: string, actionToken: string) =>
    request<void>(`/admin/music-library/tracks/${trackId}`, {
      method: "DELETE",
      headers: { "X-Admin-Action-Token": actionToken },
    }),
  adminCancelJob: (jobId: string, actionToken: string) =>
    request<void>(`/admin/jobs/${jobId}/cancel`, {
      method: "POST",
      headers: { "X-Admin-Action-Token": actionToken },
    }),
  adminDeleteWork: (workId: string, actionToken: string) =>
    request<void>(`/admin/works/${workId}`, {
      method: "DELETE",
      headers: { "X-Admin-Action-Token": actionToken },
    }),
  downloadUrl: (workId: string, format: "mp3" | "wav" | "txt") =>
    `${API_BASE}/works/${workId}/download?format=${format}`,
  adminUsers: () => request<{ items: AdminUser[] }>("/admin/users"),
  inviteUser: (email: string) =>
    request<{ invited: true; status: "pending"; expires_in: number }>(
      "/admin/invitations",
      { method: "POST", body: JSON.stringify({ email }) },
    ),
  resendUserCode: (userId: string) =>
    request<{ sent: true; expires_in: number }>(
      `/admin/users/${userId}/code/resend`,
      { method: "POST" },
    ),
  updateUserStatus: (
    userId: string,
    status: "active" | "disabled",
    actionToken: string,
  ) =>
    request<{ status: "active" | "disabled" }>(
      `/admin/users/${userId}/status`,
      {
        method: "PATCH",
        headers: { "X-Admin-Action-Token": actionToken },
        body: JSON.stringify({ status }),
      },
    ),
  updateUserQuota: (
    userId: string,
    dailyLimit: number,
    actionToken: string,
  ) =>
    request<{ daily_limit: number }>(`/admin/users/${userId}/quota`, {
      method: "PATCH",
      headers: { "X-Admin-Action-Token": actionToken },
      body: JSON.stringify({ daily_limit: dailyLimit }),
    }),
};

export async function streamAssistant(
  conversationId: string,
  messageId: string,
  credentialMode: "platform" | "byok",
  onDelta: (delta: string) => void,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/conversations/${conversationId}/assistant-stream`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        message_id: messageId,
        credential_mode: credentialMode,
      }),
    },
  );
  if (!response.ok) throw await parseError(response);
  if (!response.body)
    throw {
      code: "assistant_unavailable",
      message: "浏览器未收到助手回复流",
    } satisfies ApiError;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event =
        frame
          .split("\n")
          .find((line) => line.startsWith("event:"))
          ?.slice(6)
          .trim() ?? "message";
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (event === "error")
        throw {
          code: "assistant_unavailable",
          message: "助手暂时无法回复，请稍后重试",
        } satisfies ApiError;
      if (event === "done") {
        completed = true;
        return;
      }
      if (data) {
        const payload = JSON.parse(data) as { delta?: string };
        if (payload.delta) onDelta(payload.delta);
      }
    }
    if (done) break;
  }
  if (!completed)
    throw {
      code: "assistant_stream_interrupted",
      message: "回复连接意外中断，请重试",
    } satisfies ApiError;
}
