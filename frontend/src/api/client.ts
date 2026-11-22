/** API 客户端 — fetch 封装，每个后端端点一个函数 */

import type {
  AgentContinueRequest,
  AgentResponse,
  AppInfo,
  ComposerAsset,
  ComposerAssetListResponse,
  ComposerConfigResponse,
  ComposerImportResponse,
  ComposerMusicResponse,
  ComposerProject,
  ComposerProjectListResponse,
  ComposerRender,
  ComposerRenderListResponse,
  ComposerTTSResponse,
  Timeline,
  ConversationCreateRequest,
  ConversationDetail,
  ConversationListResponse,
  ConversationResponse,
  ConversationUpdateRequest,
  HealthResult,
  LLMConfig,
  MCPConfig,
  MCPStatusResult,
  SessionSettings,
  RuntimeStatus,
  SecretsConfig,
  UploadConfig,
  VersionInfo,
} from "../types/api";
import {
  FETCH_TIMEOUT,
  HTTP_BAD_GATEWAY,
  HTTP_GATEWAY_TIMEOUT,
  HTTP_SERVICE_UNAVAILABLE,
  PING_TIMEOUT,
  SSE_READ_TIMEOUT,
  STATUS_READ_TIMEOUT,
} from "../constants";

const BASE = "/api";
const LS_SERVER_URL = "irisflow_server_url";
const DEFAULT_SERVER_URL = "http://localhost:8000";

/** 获取当前后端服务器地址（客户端维护，localStorage 持久化）。 */
export function getServerUrl(): string {
  return (localStorage.getItem(LS_SERVER_URL) || DEFAULT_SERVER_URL).replace(/\/+$/, "");
}

/** 设置后端服务器地址并持久化到 localStorage。 */
export function setServerUrl(url: string): void {
  localStorage.setItem(LS_SERVER_URL, url.replace(/\/+$/, ""));
}

/** 拼接 API 路径与服务器地址。 */
function apiUrl(path: string): string {
  return getServerUrl() + path;
}

// ── 超时工具 ──────────────────────────────────────

/** 组合用户 AbortSignal 与超时 AbortSignal。
 *  优先使用 AbortSignal.any()，不可用时降级为手动转发。 */
function combineSignal(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  if (!signal) return timeoutSignal;
  // @ts-ignore — AbortSignal.any 在旧浏览器可能不存在
  if (typeof AbortSignal.any === "function") return AbortSignal.any([signal, timeoutSignal]);

  // 降级：手动组合
  const ctrl = new AbortController();
  const onAbort = () => { ctrl.abort(signal.reason); };
  signal.addEventListener("abort", onAbort, { once: true });
  timeoutSignal.addEventListener("abort", () => {
    signal.removeEventListener("abort", onAbort);
    ctrl.abort(timeoutSignal.reason);
  }, { once: true });
  if (signal.aborted) ctrl.abort(signal.reason);
  else if (timeoutSignal.aborted) ctrl.abort(timeoutSignal.reason);
  return ctrl.signal;
}

/** 带超时的 ReadableStream 读取。
 *  超时时取消 reader 并抛出 TimeoutError。
 *  返回 { done, value }，超时则抛 DOMException(name="TimeoutError")。 */
async function readWithTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  timeoutMs: number,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  let timer: ReturnType<typeof setTimeout> | undefined;

  try {
    const result = await Promise.race([
      reader.read(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          reader.cancel().catch(() => {}); // best-effort 取消流
          reject(new DOMException("SSE read timeout", "TimeoutError"));
        }, timeoutMs);
      }),
    ]);
    return result;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

// ── 请求封装 ──────────────────────────────────────

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
    signal: combineSignal(signal, FETCH_TIMEOUT),
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(apiUrl(`${BASE}${path}`), opts);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error");
    const err = new Error(text) as Error & { status: number };
    (err as any).status = resp.status;
    throw err;
  }
  return resp.json();
}

/** fetch + 连接超时（Promise.race 只作用连接阶段，不污染 body reader）。
 *  与 combineSignal 的关键区别：AbortSignal.timeout() 挂到 fetch 上会持续到头，
 *  在 SSE 长连接中一旦超时就会 abort body reader → 流中断。 */
async function fetchWithConnTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const resp = await Promise.race([
      fetch(url, init),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new DOMException("Connection timeout", "TimeoutError")), timeoutMs);
      }),
    ]);
    return resp;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

// ── Agent ─────────────────────────────────────────

export function agentContinue(
  body: AgentContinueRequest,
): Promise<AgentResponse> {
  return request<AgentResponse>("POST", "/agent/chat/continue", body);
}

// ── 会话管理 ──────────────────────────────────────

export function createConversation(
  body: ConversationCreateRequest,
): Promise<ConversationResponse> {
  return request<ConversationResponse>("POST", "/conversations", body);
}

export function getConversation(
  sessionId: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    "GET",
    `/conversations/${sessionId}`,
  );
}

export function listConversations(): Promise<ConversationListResponse> {
  return request<ConversationListResponse>("GET", "/conversations");
}

export function deleteConversation(
  sessionId: string,
): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(
    "DELETE",
    `/conversations/${sessionId}`,
  );
}

export function updateConversation(
  sessionId: string,
  body: ConversationUpdateRequest,
): Promise<{ session_id: string; title: string | null; pinned: boolean | null }> {
  return request<{ session_id: string; title: string | null; pinned: boolean | null }>(
    "PATCH",
    `/conversations/${sessionId}`,
    body,
  );
}

// ── 配置与健康 ────────────────────────────────────

export function getLLMConfig(): Promise<LLMConfig> {
  return request<LLMConfig>("GET", "/llm/config");
}

// ── 会话设定 ──────────────────────────────────────

export function getDefaultSessionSettings(): Promise<SessionSettings> {
  return request<SessionSettings>("GET", "/session-settings/default");
}

export function updateDefaultSessionSettings(
  body: Partial<SessionSettings>,
): Promise<SessionSettings> {
  return request<SessionSettings>("PUT", "/session-settings/default", body);
}

export function updateLLMConfig(body: {
  base_url?: string | null;
  auth_token?: string | null;
  model?: string | null;
  max_concurrent?: number | null;
}): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("PUT", "/llm/config", body);
}

export function getHealth(): Promise<HealthResult> {
  return request<HealthResult>("GET", "/health");
}

/** 轻量心跳检查 — 5s 超时，仅确认服务可达。
 *  校验响应体 {ok:true}，防止 Vite 代理返回 SPA fallback / 代理错误 JSON 导致误判。 */
export async function ping(): Promise<{ ok: boolean }> {
  const resp = await fetch(apiUrl("/api/ping"), {
    signal: AbortSignal.timeout(PING_TIMEOUT),
  });
  if (!resp.ok) throw new Error("ping failed");
  const data: unknown = await resp.json();
  if (data && typeof data === "object" && "ok" in data && (data as any).ok === true) {
    return data as { ok: boolean };
  }
  throw new Error("invalid ping response");
}

/** 获取终端点下的 API（不在 /api 下）。 */
async function rootFetch<T>(path: string): Promise<T> {
  const resp = await fetchWithConnTimeout(apiUrl(path), {
    signal: combineSignal(undefined, FETCH_TIMEOUT),
  }, FETCH_TIMEOUT);
  if (!resp.ok) throw new Error(`${path} fetch failed`);
  return resp.json();
}

/** 获取应用基本信息（GET /）。 */
export function getAppInfo(): Promise<AppInfo> {
  return rootFetch<AppInfo>("/");
}

/** 获取后端详细版本信息（GET /version）。 */
export function getVersionInfo(): Promise<VersionInfo> {
  return rootFetch<VersionInfo>("/version");
}

/** 获取服务器运行时状态（GET /status）：uptime、Python 版本、平台。 */
export function getRuntimeStatus(): Promise<RuntimeStatus> {
  return rootFetch<RuntimeStatus>("/status");
}

/** 获取 MCP 服务器连接状态（GET /api/mcp/status）。 */
export function getMCPStatus(): Promise<MCPStatusResult> {
  return request<MCPStatusResult>("GET", "/mcp/status");
}

// ── 并发配置 ────────────────────────────────────

export function getConcurrencyConfig(): Promise<{ max_concurrent: number }> {
  return request<{ max_concurrent: number }>("GET", "/llm/concurrency");
}

// ── MCP 配置 ──────────────────────────────────────

export function getMCPConfig(): Promise<MCPConfig> {
  return request<MCPConfig>("GET", "/mcp/config");
}

export function updateMCPConfig(config: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("PUT", "/mcp/config", { config });
}

// ── 密钥管理 ─────────────────────────────────────

export function getSecrets(): Promise<SecretsConfig> {
  return request<SecretsConfig>("GET", "/secrets");
}

export function updateSecrets(secrets: Record<string, string | null>): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("PUT", "/secrets", { secrets });
}

// ── 上传配置 ────────────────────────────────────

export function getUploadConfig(): Promise<UploadConfig> {
  return request<UploadConfig>("GET", "/upload/config");
}

// ── 视频合成器（/api/composer）────────────────────

export function listComposerAssets(kind?: string): Promise<ComposerAssetListResponse> {
  const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  return request<ComposerAssetListResponse>("GET", `/composer/assets${q}`);
}

export function importComposerAssetUrl(url: string, kind?: string): Promise<ComposerImportResponse> {
  return request<ComposerImportResponse>("POST", "/composer/assets", { url, kind: kind ?? null });
}

export function uploadComposerAsset(file: File): Promise<ComposerImportResponse> {
  return uploadComposerFile<ComposerImportResponse>("/composer/assets/upload", file);
}

export function deleteComposerAsset(assetId: string): Promise<{ ok: boolean; deleted: string }> {
  return request<{ ok: boolean; deleted: string }>("DELETE", `/composer/assets/${assetId}`);
}

export function getComposerConfig(): Promise<ComposerConfigResponse> {
  return request<ComposerConfigResponse>("GET", "/composer/config");
}

export function updateComposerConfig(
  updates: Partial<Record<string, unknown>>,
): Promise<ComposerConfigResponse> {
  return request<ComposerConfigResponse>("PUT", "/composer/config", updates);
}

/** 素材文件流地址（图片 / 视频 / 音频播放，后端支持 Range）。 */
export function composerAssetFileUrl(assetId: string): string {
  return apiUrl(`${BASE}/composer/assets/${assetId}/file`);
}

// ── 合成器项目（/api/composer/projects）────────────

export function listComposerProjects(): Promise<ComposerProjectListResponse> {
  return request<ComposerProjectListResponse>("GET", "/composer/projects");
}

export function getComposerProject(projectId: string): Promise<ComposerProject> {
  return request<ComposerProject>("GET", `/composer/projects/${projectId}`);
}

export function createComposerProject(body: {
  title?: string;
  script?: string;
}): Promise<ComposerProject> {
  return request<ComposerProject>("POST", "/composer/projects", body);
}

export function updateComposerProject(
  projectId: string,
  body: { title?: string; script?: string; timeline?: Timeline },
): Promise<ComposerProject> {
  return request<ComposerProject>("PATCH", `/composer/projects/${projectId}`, body);
}

export function deleteComposerProject(projectId: string): Promise<{ ok: boolean; deleted: string }> {
  return request<{ ok: boolean; deleted: string }>("DELETE", `/composer/projects/${projectId}`);
}

/** 项目当前时间轴字幕 SRT 下载地址。 */
export function composerProjectSrtUrl(projectId: string): string {
  return apiUrl(`${BASE}/composer/projects/${projectId}/srt`);
}

// ── 合成器生成（TTS / BGM）────────────────────────

export function generateComposerTts(body: {
  text: string;
  voice?: string;
  speed?: number;
}): Promise<ComposerTTSResponse> {
  return request<ComposerTTSResponse>("POST", "/composer/assets/tts", body);
}

export function generateComposerMusic(body: {
  style: string;
  duration?: number;
}): Promise<ComposerMusicResponse> {
  return request<ComposerMusicResponse>("POST", "/composer/assets/music", body);
}

// ── 渲染任务（/api/composer/renders）──────────────

export function listComposerRenders(projectId?: string): Promise<ComposerRenderListResponse> {
  const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return request<ComposerRenderListResponse>("GET", `/composer/renders${q}`);
}

export function startComposerRender(projectId: string): Promise<ComposerRender> {
  return request<ComposerRender>("POST", `/composer/projects/${projectId}/render`);
}

export function getComposerRender(renderId: string): Promise<ComposerRender> {
  return request<ComposerRender>("GET", `/composer/renders/${renderId}`);
}

export function cancelComposerRender(renderId: string): Promise<ComposerRender> {
  return request<ComposerRender>("POST", `/composer/renders/${renderId}/cancel`);
}

/** 成品 MP4 播放 / 下载地址。 */
export function composerRenderFileUrl(renderId: string, download = false): string {
  return apiUrl(`${BASE}/composer/renders/${renderId}/file${download ? "?download=1" : ""}`);
}

/** multipart 文件上传（合成器素材等非 JSON 请求）。 */
async function uploadComposerFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(apiUrl(`${BASE}${path}`), {
    method: "POST",
    body: form,
    signal: AbortSignal.timeout(15 * 60_000), // 大文件上传需要长超时
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error");
    const err = new Error(text) as Error & { status: number };
    (err as any).status = resp.status;
    throw err;
  }
  return resp.json();
}

/** 订阅合成器事件流（SSE）：素材入库 / 删除实时推送。 */
export async function subscribeComposerEvents(
  signal?: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const resp = await fetchWithConnTimeout(apiUrl(`${BASE}/composer/status-stream`), {
    signal,
  }, FETCH_TIMEOUT);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error");
    throw new Error(text);
  }
  if (!resp.body) throw new Error("Response body is null");
  return resp.body.getReader();
}

// ── 生成流重连 ──────────────────────────────────────

/** 订阅正在进行的生成流（用于页面刷新后重连 SSE）。*/
export async function subscribeGenerationStream(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const resp = await fetchWithConnTimeout(apiUrl(`${BASE}/conversations/${sessionId}/stream`), {
    signal,
  }, FETCH_TIMEOUT);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error");
    throw new Error(text);
  }
  if (!resp.body) throw new Error("Response body is null");
  return resp.body.getReader();
}

/** 订阅会话状态变更 SSE（替代轮询）。传入关注的会话 ID 列表。 */
export async function subscribeSessionStatus(
  sessionIds: string[],
  signal?: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const ids = sessionIds.join(",");
  const resp = await fetchWithConnTimeout(apiUrl(`${BASE}/sessions/status-stream?session_ids=${encodeURIComponent(ids)}`), {
    signal,
  }, FETCH_TIMEOUT);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "Unknown error");
    throw new Error(text);
  }
  if (!resp.body) throw new Error("Response body is null");
  return resp.body.getReader();
}

/** 检查错误是否表示与后端的连接失败。
 *  原生 fetch 网络失败抛 TypeError；Vite 代理不可达返回 502/503/504；
 *  超时为 DOMException(name="TimeoutError")。 */
export function isConnectionError(e: unknown): boolean {
  if (e instanceof TypeError) return true;
  if (e instanceof DOMException && e.name === "TimeoutError") return true;
  const status = (e as any)?.status;
  if (typeof status === "number" && (status === HTTP_BAD_GATEWAY || status === HTTP_SERVICE_UNAVAILABLE || status === HTTP_GATEWAY_TIMEOUT)) return true;
  return false;
}

export { readWithTimeout };

/** 终止正在进行的生成（用户点击停止按钮时调用）。 */
export async function abortGeneration(
  sessionId: string,
): Promise<{ ok: boolean; session_id: string }> {
  return request<{ ok: boolean; session_id: string }>(
    "POST",
    `/conversations/${sessionId}/abort`,
  );
}
