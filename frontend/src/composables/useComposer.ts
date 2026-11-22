/** 合成器前端状态 —— 模块级单例（对齐 toolMetadata.ts 模式）。

持有素材列表与 ffmpeg 探测状态，订阅后端 status-stream SSE 的
composer_asset 事件自动刷新。ComposerPanel / AssetLibrary 等多组件
共享同一份状态，不依赖 provide/inject（浮窗经 Teleport 到 body）。
*/

import { ref } from "vue";
import {
  composerAssetFileUrl,
  deleteComposerAsset,
  getComposerConfig,
  listComposerAssets,
  subscribeComposerEvents,
} from "../api/client";
import {
  COMPOSER_ASSET_RECONNECT_DELAY,
  COMPOSER_SSE_ASSET,
  COMPOSER_SSE_READ_TIMEOUT,
  SSE_DATA_PREFIX,
  SSE_DATA_PREFIX_LEN,
} from "../constants";
import { readWithTimeout } from "../api/client";
import type { ComposerAsset } from "../types/api";

/** 素材列表（后端为唯一权威源） */
export const composerAssets = ref<ComposerAsset[]>([]);

/** 当前类型过滤（all / image / video / audio） */
export const composerKindFilter = ref<string>("all");

/** ffmpeg / ffprobe 探测结果 */
export const composerFfmpegAvailable = ref(false);
export const composerFfmpegError = ref("");

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

/** 拉取 ffmpeg 探测状态。 */
export async function refreshComposerConfig(): Promise<void> {
  try {
    const cfg = await getComposerConfig();
    composerFfmpegAvailable.value = cfg.ffmpeg_available && cfg.ffprobe_available;
    composerFfmpegError.value = cfg.error;
  } catch {
    /* 静默 */
  }
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
