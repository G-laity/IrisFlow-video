/** 合成器前端状态 —— 模块级单例（对齐 toolMetadata.ts 模式）。

持有素材列表与 ffmpeg 探测状态，订阅后端 status-stream SSE 的
composer_asset 事件自动刷新。ComposerPanel / AssetLibrary 等多组件
共享同一份状态，不依赖 provide/inject（浮窗经 Teleport 到 body）。
*/

import { computed, ref } from "vue";
import {
  cancelComposerRender,
  composerAssetFileUrl,
  createComposerProject,
  deleteComposerAsset,
  deleteComposerProject,
  getComposerConfig,
  listComposerAssets,
  listComposerProjects,
  listComposerRenders,
  startComposerRender,
  subscribeComposerEvents,
  updateComposerProject,
} from "../api/client";
import {
  COMPOSER_ASSET_RECONNECT_DELAY,
  COMPOSER_SSE_ASSET,
  COMPOSER_SSE_PROGRESS,
  COMPOSER_SSE_PROJECT,
  COMPOSER_SSE_READ_TIMEOUT,
  COMPOSER_SSE_RENDER,
  COMPOSER_SSE_WARN,
  SSE_DATA_PREFIX,
  SSE_DATA_PREFIX_LEN,
} from "../constants";
import { readWithTimeout } from "../api/client";
import type { ComposerAsset, ComposerProject, ComposerRender, Timeline } from "../types/api";

/** 素材列表（后端为唯一权威源） */
export const composerAssets = ref<ComposerAsset[]>([]);

/** 当前类型过滤（all / image / video / audio） */
export const composerKindFilter = ref<string>("all");

/** ffmpeg / ffprobe 探测结果 */
export const composerFfmpegAvailable = ref(false);
export const composerFfmpegError = ref("");

// ── 项目 / 时间轴 ──────────────────────────────────

/** 项目列表（后端为唯一权威源） */
export const composerProjects = ref<ComposerProject[]>([]);

/** 当前选中的项目 ID */
export const activeProjectId = ref("");

/** 当前项目（派生） */
export const activeProject = computed<ComposerProject | null>(
  () => composerProjects.value.find(p => p.project_id === activeProjectId.value) ?? null,
);

/** 时间轴保存状态：idle / saving / saved / error */
export const composerSaveState = ref<"idle" | "saving" | "saved" | "error">("idle");

/** 时间轴校验错误（后端逐字段返回） */
export const composerTimelineErrors = ref<string[]>([]);

/** 分辨率预设表（后端配置下发） */
export const composerPresets = ref<Record<string, { width: number; height: number; fps: number }>>({});

/** TTS 命名音色列表与默认音色（后端配置下发） */
export const composerTtsVoices = ref<string[]>([]);
export const composerTtsDefaultVoice = ref("");

/** 渲染任务列表 */
export const composerRenders = ref<ComposerRender[]>([]);

/** 最近一条合成器告警（磁盘水位等） */
export const composerRenderWarn = ref("");

/** provider 探测状态（TTS / 音乐） */
export const composerProviders = ref<{
  ttsPrimaryReachable: boolean;
  ttsFallbackReachable: boolean;
  edgeAvailable: boolean;
  musicReachable: boolean;
}>({ ttsPrimaryReachable: false, ttsFallbackReachable: false, edgeAvailable: false, musicReachable: false });

let _reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
let _abort: AbortController | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _stopped = true;

/** 刷新素材列表（按当前过滤条件）。失败静默（后端未运行时忽略）。 */
export async function refreshComposerAssets(): Promise<void> {
  try {
    const kind = composerKindFilter.value === "all" ? undefined : composerKindFilter.value;
    const resp = await listComposerAssets(kind);
    composerAssets.value = resp.assets;
  } catch {
    /* 后端未运行或接口不存在时静默忽略 */
  }
}

/** 素材预览 / 播放 URL。 */
export function composerFileUrl(asset: ComposerAsset): string {
  return composerAssetFileUrl(asset.asset_id);
}

/** 删除素材（后端校验引用计数）。 */
export async function removeComposerAsset(assetId: string): Promise<void> {
  await deleteComposerAsset(assetId);
}

/** 拉取 ffmpeg / provider 探测状态。 */
export async function refreshComposerConfig(): Promise<void> {
  try {
    const cfg = await getComposerConfig();
    composerFfmpegAvailable.value = cfg.ffmpeg_available && cfg.ffprobe_available;
    composerFfmpegError.value = cfg.error;
    composerPresets.value = cfg.config.presets;
    const ttsCfg = (cfg.config as unknown as { tts?: { voices?: Record<string, string>; default_voice?: string } }).tts;
    if (ttsCfg?.voices) composerTtsVoices.value = Object.keys(ttsCfg.voices);
    composerTtsDefaultVoice.value = ttsCfg?.default_voice ?? "";
    const providers = cfg.providers;
    if (providers) {
      composerProviders.value = {
        ttsPrimaryReachable: providers.tts.primary.reachable,
        ttsFallbackReachable: providers.tts.fallback?.reachable ?? false,
        edgeAvailable: providers.tts.edge_available,
        musicReachable: providers.music.reachable,
      };
    }
  } catch {
    /* 静默 */
  }
}

// ── 项目操作 ───────────────────────────────────────

/** 刷新项目列表。 */
export async function refreshComposerProjects(): Promise<void> {
  try {
    const resp = await listComposerProjects();
    composerProjects.value = resp.projects;
  } catch {
    /* 静默 */
  }
}

export function selectComposerProject(projectId: string): void {
  activeProjectId.value = projectId;
  composerTimelineErrors.value = [];
  composerSaveState.value = "idle";
}

/** 新建项目并选中。 */
export async function createComposerProjectItem(title: string, script = ""): Promise<ComposerProject> {
  const project = await createComposerProject({ title, script });
  await refreshComposerProjects();
  selectComposerProject(project.project_id);
  return project;
}

/** 删除项目；若删除的是当前项目则清空选中。 */
export async function removeComposerProjectItem(projectId: string): Promise<void> {
  await deleteComposerProject(projectId);
  if (activeProjectId.value === projectId) activeProjectId.value = "";
  await refreshComposerProjects();
}

/** 保存时间轴（PATCH）；失败时解析后端逐字段错误。 */
export async function saveComposerTimeline(projectId: string, timeline: Timeline): Promise<boolean> {
  composerSaveState.value = "saving";
  composerTimelineErrors.value = [];
  try {
    const updated = await updateComposerProject(projectId, { timeline });
    const idx = composerProjects.value.findIndex(p => p.project_id === projectId);
    if (idx >= 0) composerProjects.value[idx] = updated;
    composerSaveState.value = "saved";
    return true;
  } catch (e) {
    composerSaveState.value = "error";
    composerTimelineErrors.value = parseComposerError(e);
    return false;
  }
}

// ── 渲染任务 ───────────────────────────────────────

/** 刷新渲染列表（projectId 空 = 全部）。 */
export async function refreshComposerRenders(projectId?: string): Promise<void> {
  try {
    const resp = await listComposerRenders(projectId);
    composerRenders.value = resp.renders;
  } catch {
    /* 静默 */
  }
}

/** 提交渲染并 upsert 到列表。 */
export async function startComposerRenderItem(projectId: string): Promise<ComposerRender> {
  const render = await startComposerRender(projectId);
  _upsertRender(render);
  return render;
}

/** 取消渲染并更新列表。 */
export async function cancelComposerRenderItem(renderId: string): Promise<ComposerRender> {
  const render = await cancelComposerRender(renderId);
  _upsertRender(render);
  return render;
}

function _upsertRender(render: ComposerRender): void {
  const idx = composerRenders.value.findIndex(r => r.render_id === render.render_id);
  if (idx >= 0) composerRenders.value[idx] = { ...composerRenders.value[idx], ...render };
  else composerRenders.value.unshift(render);
}

/** 解析后端错误：{detail: {message, errors[]}} → 错误列表。 */
export function parseComposerError(e: unknown): string[] {
  if (e instanceof Error) {
    try {
      const parsed = JSON.parse(e.message);
      const detail = parsed?.detail;
      if (detail && typeof detail === "object") {
        if (Array.isArray(detail.errors)) return detail.errors.map(String);
        if (detail.message) return [String(detail.message)];
      }
      if (typeof detail === "string") return [detail];
    } catch {
      /* 非 JSON 错误体 */
    }
    return [e.message];
  }
  return [String(e)];
}

/** 启动 composer SSE 订阅（断线自动重连）。 */
export function startComposerEvents(): void {
  if (!_stopped) return;
  _stopped = false;
  _connect();
}

/** 停止 composer SSE 订阅（不再重连）。 */
export function stopComposerEvents(): void {
  _stopped = true;
  _abort?.abort();
  _abort = null;
  _reader = null;
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
}

/** 应用渲染进度事件（轻量字段更新，不替换整条记录）。 */
function _applyRenderProgress(event: Record<string, unknown>): void {
  const renderId = String(event.render_id ?? "");
  if (!renderId) return;
  const idx = composerRenders.value.findIndex(r => r.render_id === renderId);
  if (idx < 0) return;
  const current = composerRenders.value[idx];
  composerRenders.value[idx] = {
    ...current,
    progress: Number(event.progress ?? current.progress) || 0,
    state: (event.state as ComposerRender["state"]) ?? current.state,
    stage_detail: (event.stage_detail as ComposerRender["stage_detail"]) ?? current.stage_detail,
  };
}

/** 应用 SSE 项目事件：本地 upsert / 移除，避免额外全量刷新。 */
function _applyProjectEvent(event: Record<string, unknown>): void {
  const action = event.event;
  const data = event.project;
  if (!data || typeof data !== "object") return;
  const project = data as ComposerProject;
  if (action === "deleted") {
    const id = String((data as { project_id?: string }).project_id ?? "");
    if (!id) return;
    composerProjects.value = composerProjects.value.filter(p => p.project_id !== id);
    if (activeProjectId.value === id) activeProjectId.value = "";
    return;
  }
  if (!project.project_id) return;
  const idx = composerProjects.value.findIndex(p => p.project_id === project.project_id);
  if (idx >= 0) composerProjects.value[idx] = project;
  else composerProjects.value.unshift(project);
}

async function _connect(): Promise<void> {
  _abort = new AbortController();
  try {
    const reader = await subscribeComposerEvents(_abort.signal);
    _reader = reader;
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value } = await readWithTimeout(reader, COMPOSER_SSE_READ_TIMEOUT);
      if (value !== undefined) {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith(SSE_DATA_PREFIX)) continue;
          try {
            const event = JSON.parse(line.slice(SSE_DATA_PREFIX_LEN).trim());
            if (event.type === COMPOSER_SSE_ASSET) {
              // 素材变更：全量刷新列表（简单可靠，素材量级小）
              await refreshComposerAssets();
            } else if (event.type === COMPOSER_SSE_PROJECT) {
              _applyProjectEvent(event);
            } else if (event.type === COMPOSER_SSE_RENDER) {
              if (event.render) _upsertRender(event.render as ComposerRender);
            } else if (event.type === COMPOSER_SSE_PROGRESS) {
              _applyRenderProgress(event);
            } else if (event.type === COMPOSER_SSE_WARN) {
              composerRenderWarn.value = String(event.message ?? "");
            }
          } catch {
            /* 心跳注释行或解析失败，忽略 */
          }
        }
      }
    }
  } catch {
    /* 断线 → 延迟重连 */
  } finally {
    _reader = null;
    _abort = null;
    if (!_stopped && _reconnectTimer === null) {
      _reconnectTimer = setTimeout(() => {
        _reconnectTimer = null;
        _connect();
      }, COMPOSER_ASSET_RECONNECT_DELAY);
    }
  }
}
