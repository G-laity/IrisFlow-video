/** 把 `composer_list_videos` 的工具结果转换成聊天里可直接播放的视频条目。 */

import { getServerUrl } from "../api/client";
import { UI_MEDIA_ASSET, UI_MEDIA_RENDER } from "../constants";
import type { UIMediaItem } from "../types/api";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

/** file_url / download_url 是相对后端路径；转成当前配置的后端绝对地址。 */
function absoluteUrl(path: string): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return getServerUrl() + (path.startsWith("/") ? path : `/${path}`);
}

/** 解析工具 JSON（兼容直接对象与 { result: {...} } 包装）。 */
export function parseComposerVideos(raw: string | undefined): UIMediaItem[] {
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  const root = asRecord(parsed);
  if (!root) return [];
  const payload = asRecord(root.result) ?? root;

  const items: UIMediaItem[] = [];
  const seen = new Set<string>();
  const push = (item: UIMediaItem): void => {
    if (!item.src || seen.has(item.src)) return;
    seen.add(item.src);
    items.push(item);
  };

  const renders = Array.isArray(payload.renders) ? payload.renders : [];
  for (const rawItem of renders) {
    const item = asRecord(rawItem);
    if (!item) continue;
    const src = absoluteUrl(String(item.file_url || ""));
    if (!src) continue;
    const renderId = String(item.render_id || "");
    push({
      kind: "video",
      src,
      title: String(item.project_title || (renderId ? `${UI_MEDIA_RENDER} ${renderId}` : UI_MEDIA_RENDER)),
      source: "render",
      downloadUrl: absoluteUrl(String(item.download_url || "")) || undefined,
    });
  }

  const assets = Array.isArray(payload.assets) ? payload.assets : [];
  for (const rawItem of assets) {
    const item = asRecord(rawItem);
    if (!item) continue;
    const src = absoluteUrl(String(item.file_url || ""));
    if (!src) continue;
    const kind = String(item.kind || "");
    if (kind !== "image" && kind !== "audio" && kind !== "video") continue;
    const assetId = String(item.asset_id || "");
    const duration = typeof item.duration === "number" && Number.isFinite(item.duration)
      ? item.duration
      : undefined;
    push({
      kind,
      src,
      title: String(item.name || assetId || UI_MEDIA_ASSET),
      source: "asset",
      duration,
    });
  }

  return items;
}

/** 合并视频条目并去重（同一轮多次调用 composer_list_videos 时使用）。 */
export function appendMedia(
  existing: UIMediaItem[] | undefined,
  incoming: UIMediaItem[],
): UIMediaItem[] {
  const result = [...(existing ?? [])];
  const seen = new Set(result.map((item) => item.src));
  for (const item of incoming) {
    if (!item.src || seen.has(item.src)) continue;
    seen.add(item.src);
    result.push(item);
  }
  return result;
}
