/** 映射后端 Pydantic 模型的 TypeScript 接口 */

// ── 聊天消息 ──────────────────────────────────────

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_call_id?: string | null;
  tool_calls?: ToolCallRaw[] | null;
  reasoning_content?: string | null;
  /** 本轮对话状态（后端权威）：queued / generating / completed / aborted */
  message_status?: string | null;
  /** 本轮对话是否启用了思考模式 */
  thinking?: boolean;
}

// ── 工具相关 ──────────────────────────────────────

/** 工具元数据（来自 GET /api/tools，后端权威） */
export interface ToolInfo {
  name: string;
  icon: string;
  label: string;
  order: number;
  description: string;
}

export interface ToolCallRaw {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: string; // JSON string from API
  };
}

export interface ToolCallRecord {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string | null;
  /** 工具执行结果是否为错误（后端权威，持久化在 tool 消息中） */
  isError?: boolean;
}

export interface ToolResult {
  id: string;
  name: string;
  result: string;
}

// ── API 请求体 ────────────────────────────────────

export interface AgentContinueRequest {
  session_id: string;
  model: string;
  tool_results: ToolResult[];
}

export interface SessionSettings {
  system_prompt: string | null;
  temperature: number | null;
  max_tokens: number | null;
  top_p: number | null;
  top_k: number | null;
  presence_penalty: number | null;
  frequency_penalty: number | null;
  repeat_penalty: number | null;
}

export interface SessionSettingsPreset {
  id: string;
  name: string;
  icon: string;
  description: string;
  settings: SessionSettings;
}

export interface ConversationCreateRequest {
  model: string;
  system_prompt?: string | null;
  title?: string;
  mode?: "chat" | "agent";
  settings?: SessionSettings | null;
}

// ── API 响应体 ────────────────────────────────────

export interface AgentResponse {
  model: string;
  content: string;
  session_id?: string | null;
  tool_calls: ToolCallRecord[];
  iterations: number;
  finish_reason?: string | null;
  usage?: Record<string, unknown>;
}

export interface ConversationResponse {
  session_id: string;
  model: string;
  content: string;
  usage?: Record<string, unknown>;
}

export type SessionStatus = 'idle' | 'generating' | 'completed' | 'pending' | 'unknown';
export type ThinkState = 'none' | 'thinking' | 'done';

export interface ConversationInfo {
  session_id: string;
  model: string;
  title: string;
  mode: "chat" | "agent";
  message_count: number;
  status: SessionStatus;
  pinned: boolean;
  created_at: string;
  last_access: string;
}

/** 会话列表项（不含状态 — 状态通过 SSE 订阅获取） */
export interface ConversationListItem {
  session_id: string;
  model: string;
  title: string;
  mode: "chat" | "agent";
  message_count: number;
  pinned: boolean;
  created_at: string;
  last_access: string;
}

export interface ConversationDetail {
  session_id: string;
  model: string;
  messages: ChatMessage[];
  status: SessionStatus;
  created_at: string;
  settings?: SessionSettings | null;
}

export interface ConversationUpdateRequest {
  title?: string | null;
  pinned?: boolean | null;
}

export interface ConversationListResponse {
  conversations: ConversationListItem[];
}

export interface LLMConfig {
  base_url: string;
  default_model: string;
  auth_token: string;
}

export interface HealthResult {
  status: string;
  base_url: string;
  default_model: string;
  error?: string;
}

// ── 前端 UI 类型 ───────────────────────────────────

export interface UIMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  thinkContent?: string;
  /** 思考过程是否已完成（完成后默认折叠，流式时展开） */
  thinkComplete?: boolean;
  toolCalls?: ToolCallRecord[];
  /** 是否为自动执行中的内置工具（不可手动操作） */
  autoExecuting?: boolean;
  /** 工作流日志：Agent 每一步的行为记录 */
  workflowLog?: WorkflowEntry[];
  /** 本轮对话是否启用了思考模式（后端权威）。用于 WorkflowLog 区分"思考/已思考"与"处理/已完成"。 */
  thinking?: boolean;
  /** 流式生成是否完成（完成前不展示复制按钮） */
  streamDone?: boolean;
  /** 生成是否被终止（用户手动终止 或 LLM 错误终止） */
  aborted?: boolean;
  /** 是否在排队等待调度（并发满时入队） */
  queued?: boolean;
  /** 用户消息附带的图片 data URLs */
  images?: string[];
  /** 用户消息附带的文件（图片 + 文档），用于展示文件卡片 */
  files?: FileAttachment[];
  /** 助手消息附带的本地视频（来自 composer_list_videos） */
  media?: UIMediaItem[];
  timestamp: number;
}

/** 助手消息中直接展示的素材 / 成片条目 */
export interface UIMediaItem {
  kind: "video" | "image" | "audio";
  /** 播放 / 查看地址（后端 file_url 已解析为绝对地址） */
  src: string;
  title: string;
  source: "render" | "asset";
  downloadUrl?: string;
  duration?: number;
}

/** 工作流日志条目 */
export interface WorkflowEntry {
  type: "think" | "tool_call" | "tool_result";
  text: string;
  toolName?: string;
  /** 原始调用参数（tool_call 时） */
  rawArgs?: Record<string, unknown>;
  /** 原始返回结果（tool_result 时） */
  rawResult?: string;
  /** 是否为错误结果（后端 SSE is_error 字段权威） */
  isError?: boolean;
}

/** 文件附件 */
export interface FileAttachment {
  filename: string;
  data_url?: string;       // 图片
  text_content?: string;   // 文本/文档
  download_suffix?: string; // 后端指定下载扩展名（.md / .py 等）
}

/** 预览浮窗载荷 */
export type PreviewPayload =
  | { kind: "image"; src: string; filename?: string }
  | { kind: "file"; filename: string; text_content?: string; download_suffix?: string }
  | { kind: "video"; src: string; filename?: string }
  | { kind: "webpage"; url: string; title?: string };

// ── 视频合成器（/api/composer）──────────────────────

/** 素材类型 */
export type ComposerAssetKind = "image" | "video" | "audio" | "unknown";

/** 素材探测元数据（ffprobe） */
export interface ComposerAssetProbe {
  duration?: number;
  width?: number;
  height?: number;
  fps?: number;
  vcodec?: string;
  acodec?: string;
  has_audio?: boolean;
}

/** 素材记录 */
export interface ComposerAsset {
  asset_id: string;
  kind: ComposerAssetKind;
  source: "upload" | "url" | string;
  url: string;
  file_path: string;
  sha256: string;
  size_bytes: number;
  probe: ComposerAssetProbe;
  meta: Record<string, unknown>;
  ref_count: number;
  created_at: string;
}

export interface ComposerAssetListResponse {
  assets: ComposerAsset[];
}

export interface ComposerImportResponse {
  asset: ComposerAsset;
  duplicated: boolean;
  warnings: string[];
}

export interface ComposerPreset {
  width: number;
  height: number;
  fps: number;
}

/** 合成器配置快照 */
export interface ComposerConfig {
  ffmpeg_path: string;
  disk_limit_bytes: number;
  render_concurrency: number;
  presets: Record<string, ComposerPreset>;
}

export interface ComposerConfigResponse {
  config: ComposerConfig;
  ffmpeg_available: boolean;
  ffprobe_available: boolean;
  ffmpeg_path: string;
  ffprobe_path: string;
  error: string;
  providers?: {
    tts: { primary: { provider: string; base_url: string; reachable: boolean }; fallback: { provider: string; base_url: string; reachable: boolean } | null; edge_available: boolean };
    music: { provider: string; base_url: string; reachable: boolean };
  };
}

// ── 时间轴（PLAN §4.3）──────────────────────────────

export interface TimelineTransition {
  type: string;
  duration: number;
}

export interface TimelineMotion {
  type: "kenburns" | "static";
  from_zoom?: number;
  to_zoom?: number;
  pan?: "none" | "left" | "right" | "up" | "down";
}

export interface TimelineVideoSegment {
  asset_id: string;
  duration: number;
  trim_in?: number;
  transition_in?: TimelineTransition;
  motion?: TimelineMotion;
}

export interface TimelineAudioTrack {
  role: "narration" | "bgm";
  asset_id: string;
  start: number;
  duration: number;
  gain?: number;
  fade_in?: number;
  fade_out?: number;
  loop?: boolean;
  /** BGM 是否在旁白出现时侧链压低（默认 true） */
  ducking?: boolean;
}

export interface TimelineSubtitle {
  start: number;
  end: number;
  text: string;
  style?: string;
}

export interface Timeline {
  version: number;
  preset: string;
  tracks: {
    video: TimelineVideoSegment[];
    audio: TimelineAudioTrack[];
    subtitles: TimelineSubtitle[];
  };
}

export interface ComposerProject {
  project_id: string;
  title: string;
  script: string;
  timeline: Timeline;
  asset_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ComposerProjectListResponse {
  projects: ComposerProject[];
}

export interface ComposerTTSResponse {
  asset: ComposerAsset;
  duplicated: boolean;
  provider: string;
}

export interface ComposerMusicResponse {
  asset: ComposerAsset;
  duplicated: boolean;
}

// ── 渲染任务（M3）──────────────────────────────────

export type ComposerRenderState =
  | "queued"
  | "preparing"
  | "rendering"
  | "muxing"
  | "completed"
  | "failed"
  | "canceled";

export interface ComposerRenderStage {
  total_segments?: number;
  done_segments?: number;
  current?: string;
}

export interface ComposerRender {
  render_id: string;
  project_id: string;
  state: ComposerRenderState;
  progress: number;
  stage_detail: ComposerRenderStage;
  output_path: string;
  error: string;
  created_at: string;
  finished_at: string | null;
}

export interface ComposerRenderListResponse {
  renders: ComposerRender[];
}

// ── 模板 / 磁盘维护（M5）──────────────────────────

export interface ComposerProjectTemplate {
  id: string;
  name: string;
  description: string;
  preset: string;
  script: string;
}

export interface ComposerTemplateListResponse {
  templates: ComposerProjectTemplate[];
}

export interface ComposerCleanupResult {
  skipped?: boolean;
  reason?: string;
  freed_bytes: number;
  deleted_assets: number;
  deleted_renders: number;
  used_bytes?: number;
  limit_bytes?: number;
  target_bytes?: number;
  message?: string;
}

/** 应用基本信息（来自 GET /） */
export interface AppInfo {
  name: string;
  version: string;
  description: string;
  docs: string;
}

/** 版本信息（来自 GET /version） */
export interface VersionInfo {
  app: string;
  app_version: string;
  description: string;
  python: string;
  platform: string;
  arch: string;
  fastapi: string;
}

/** 运行时状态（来自 GET /status） */
export interface RuntimeStatus {
  uptime_seconds: number;
  python_version: string;
  platform: string;
}

/** MCP 服务器状态（来自 GET /api/mcp/status，状态 ID 由前端映射为展示文案） */
export interface MCPStatusResult {
  servers: Record<string, "running" | "stopped" | "error">;
}

/** 上传配置（来自 GET /api/upload/config） */
export interface UploadConfig {
  images: string[];
  text: string[];
  documents: string[];
  max_size_mb: number;
}

/** MCP 配置（来自 GET/PUT /api/mcp/config） */
export interface MCPConfig {
  config: string;
}

/** 密钥配置（来自 GET /api/secrets） */
export interface SecretsConfig {
  keys: string[];
}
