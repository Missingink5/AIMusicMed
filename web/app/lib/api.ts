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
};
export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  risk_level: "normal" | "crisis";
  created_at: number;
};
export type PlanInput = {
  message_id: string;
  duration_minutes: number;
  music_source: "library" | "ai";
  target_emotion: "auto" | "平静" | "喜悦" | "友爱" | "自信";
  credential_mode: "platform" | "byok";
  voice_mode: "tts" | "pure_music";
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
};
export type ConversationDetail = {
  conversation: Conversation;
  messages: Message[];
  plans: StoredPlan[];
  jobs: ConversationJob[];
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
  listConversations: () => request<{ items: Conversation[] }>("/conversations"),
  getConversation: (id: string) =>
    request<ConversationDetail>(`/conversations/${id}`),
  createConversation: (title = "新对话") =>
    request<{ id: string; title: string }>("/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
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
  createJob: (planId: string) =>
    request<{ id: string; status: string }>(`/plans/${planId}/jobs`, {
      method: "POST",
    }),
  getJob: (jobId: string) => request<JobResult>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) =>
    request<{ status: string }>(`/jobs/${jobId}/cancel`, { method: "POST" }),
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
  updateUserStatus: (userId: string, status: "active" | "disabled") =>
    request<{ status: "active" | "disabled" }>(
      `/admin/users/${userId}/status`,
      { method: "PATCH", body: JSON.stringify({ status }) },
    ),
  updateUserQuota: (userId: string, dailyLimit: number) =>
    request<{ daily_limit: number }>(`/admin/users/${userId}/quota`, {
      method: "PATCH",
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
      if (event === "done") return;
      if (data) {
        const payload = JSON.parse(data) as { delta?: string };
        if (payload.delta) onDelta(payload.delta);
      }
    }
    if (done) break;
  }
}
