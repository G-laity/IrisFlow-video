<script setup lang="ts">
import { ref } from "vue";
import {
  generateComposerMusic,
  generateComposerTts,
  importComposerAssetUrl,
  uploadComposerAsset,
} from "../../api/client";
import {
  COMPOSER_DELETE_CONFIRM,
  COMPOSER_KIND_ICONS,
  COMPOSER_KINDS,
  COMPOSER_KIND_ALL,
  COMPOSER_MAX_UPLOAD_MB,
  UI_ASSET_DEDUP_HIT,
  UI_ASSET_IMPORTING,
  UI_ASSET_IMPORT_URL,
  UI_ASSET_NO_ASSETS,
  UI_ASSET_UPLOAD,
  UI_ASSET_URL_PLACEHOLDER,
  UI_BGM_GENERATE,
  UI_BGM_PANEL,
  UI_BGM_STYLE_PLACEHOLDER,
  UI_COMPOSER_FFMPEG_MISSING,
  UI_DELETE,
  UI_GENERATING,
  UI_OPEN_IN_NEW_TAB,
  UI_TTS_GENERATE,
  UI_TTS_PANEL,
  UI_TTS_SPLIT,
  UI_TTS_TEXT_PLACEHOLDER,
  UI_TTS_VOICE,
} from "../../constants";
import {
  composerAssets,
  composerFileUrl,
  composerFfmpegAvailable,
  composerFfmpegError,
  composerKindFilter,
  composerTtsDefaultVoice,
  composerTtsVoices,
  parseComposerError,
  refreshComposerAssets,
  removeComposerAsset,
} from "../../composables/useComposer";
import type { ComposerAsset, PreviewPayload } from "../../types/api";

const emit = defineEmits<{
  preview: [payload: PreviewPayload];
}>();

// ── 类型过滤 ──────────────────────────────────────

const KIND_LABELS: Record<string, string> = {
  [COMPOSER_KIND_ALL]: "全部",
  image: "图片",
  video: "视频",
  audio: "音频",
};

async function setKindFilter(kind: string): Promise<void> {
  composerKindFilter.value = kind;
  await refreshComposerAssets();
}

// ── URL 导入 ──────────────────────────────────────

const urlInput = ref("");
const importing = ref(false);
const importNotice = ref("");
const importError = ref("");

async function handleImportUrl(): Promise<void> {
  const url = urlInput.value.trim();
  if (!url || importing.value) return;
  importing.value = true;
  importNotice.value = "";
  importError.value = "";
  try {
    const resp = await importComposerAssetUrl(url);
    importNotice.value = resp.duplicated ? UI_ASSET_DEDUP_HIT : "";
    urlInput.value = "";
    await refreshComposerAssets();
  } catch (e) {
    importError.value = e instanceof Error ? e.message : String(e);
  } finally {
    importing.value = false;
  }
}

// ── 本地上传 ──────────────────────────────────────

const fileInput = ref<HTMLInputElement | null>(null);
const uploading = ref(false);

function pickFile(): void {
  fileInput.value?.click();
}

async function handleUpload(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || uploading.value) return;
  if (file.size > COMPOSER_MAX_UPLOAD_MB * 1024 * 1024) {
    importError.value = `文件过大，上限 ${COMPOSER_MAX_UPLOAD_MB} MB`;
    return;
  }
  uploading.value = true;
  importNotice.value = "";
  importError.value = "";
  try {
    const resp = await uploadComposerAsset(file);
    importNotice.value = resp.duplicated ? UI_ASSET_DEDUP_HIT : "";
    await refreshComposerAssets();
  } catch (e) {
    importError.value = e instanceof Error ? e.message : String(e);
  } finally {
    uploading.value = false;
  }
}

// ── TTS / BGM 快捷生成 ────────────────────────────

const ttsOpen = ref(false);
const bgmOpen = ref(false);
const ttsText = ref("");
const ttsVoice = ref("");
const ttsSplit = ref(true);
const ttsBusy = ref(false);
const bgmStyle = ref("");
const bgmDuration = ref(11);
const bgmBusy = ref(false);
const genNotice = ref("");
const genError = ref("");

async function handleTts(): Promise<void> {
  const text = ttsText.value.trim();
  if (!text || ttsBusy.value) return;
  ttsBusy.value = true;
  genNotice.value = "";
  genError.value = "";
  try {
    const resp = await generateComposerTts({
      text,
      voice: ttsVoice.value || composerTtsDefaultVoice.value || undefined,
      split: ttsSplit.value,
    });
    genNotice.value = resp.duplicated ? UI_ASSET_DEDUP_HIT : `旁白已入库（${resp.provider}）`;
    ttsText.value = "";
    await refreshComposerAssets();
  } catch (e) {
    genError.value = parseComposerError(e).join("\n");
  } finally {
    ttsBusy.value = false;
  }
}

async function handleBgm(): Promise<void> {
  const style = bgmStyle.value.trim();
  if (!style || bgmBusy.value) return;
  bgmBusy.value = true;
  genNotice.value = "";
  genError.value = "";
  try {
    const resp = await generateComposerMusic({ style, duration: bgmDuration.value });
    genNotice.value = resp.duplicated ? UI_ASSET_DEDUP_HIT : "背景音乐已入库";
    bgmStyle.value = "";
    await refreshComposerAssets();
  } catch (e) {
    genError.value = parseComposerError(e).join("\n");
  } finally {
    bgmBusy.value = false;
  }
}

// ── 删除 ──────────────────────────────────────────

async function handleDelete(asset: ComposerAsset): Promise<void> {
  if (!window.confirm(COMPOSER_DELETE_CONFIRM)) return;
  try {
    await removeComposerAsset(asset.asset_id);
    await refreshComposerAssets();
  } catch (e) {
    importError.value = e instanceof Error ? e.message : String(e);
  }
}

// ── 预览 ──────────────────────────────────────────

function handlePreview(asset: ComposerAsset): void {
  const src = composerFileUrl(asset);
  if (asset.kind === "image") {
    emit("preview", { kind: "image", src, filename: asset.sha256.slice(0, 8) });
  } else if (asset.kind === "video") {
    emit("preview", { kind: "video", src, filename: asset.sha256.slice(0, 8) });
  } else if (asset.kind === "audio") {
    window.open(src, "_blank", "noopener");
  }
}

// ── 展示辅助 ──────────────────────────────────────

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null) return "";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function probeSummary(asset: ComposerAsset): string {
  const p = asset.probe ?? {};
  const parts: string[] = [];
  if (p.width && p.height) parts.push(`${p.width}×${p.height}`);
  if (asset.kind === "video" && p.fps) parts.push(`${p.fps}fps`);
  if (p.duration !== undefined) parts.push(formatDuration(p.duration));
  if (!parts.length) return formatSize(asset.size_bytes);
  return `${parts.join(" · ")} · ${formatSize(asset.size_bytes)}`;
}
</script>

<template>
  <div class="al-body">
    <!-- 导入区 -->
    <div class="al-import">
      <div class="al-url-row">
        <input
          v-model="urlInput"
          class="al-url-input"
          :placeholder="UI_ASSET_URL_PLACEHOLDER"
          @keydown.enter="handleImportUrl"
        />
        <button class="al-btn al-btn--primary" :disabled="importing || !urlInput.trim()" @click="handleImportUrl">
          <i v-if="importing" class="fa-solid fa-spinner fa-spin"></i>
          {{ importing ? UI_ASSET_IMPORTING : UI_ASSET_IMPORT_URL }}
        </button>
      </div>
      <div class="al-upload-row">
        <button class="al-btn" :disabled="uploading" @click="pickFile">
          <i v-if="uploading" class="fa-solid fa-spinner fa-spin"></i>
          <i v-else class="fa-solid fa-upload"></i>
          {{ uploading ? UI_ASSET_IMPORTING : UI_ASSET_UPLOAD }}
          <span class="al-upload-limit">≤ {{ COMPOSER_MAX_UPLOAD_MB }} MB</span>
        </button>
        <input
          ref="fileInput"
          type="file"
          class="al-file-input"
          accept="image/*,video/*,audio/*"
          @change="handleUpload"
        />
      </div>
      <p v-if="importError" class="al-msg al-msg--error">{{ importError }}</p>
      <p v-else-if="importNotice" class="al-msg">{{ importNotice }}</p>
      <p v-if="!composerFfmpegAvailable" class="al-msg al-msg--warn" :title="composerFfmpegError">
        <i class="fa-solid fa-triangle-exclamation"></i>
        {{ UI_COMPOSER_FFMPEG_MISSING }}
      </p>
    </div>

    <!-- TTS / BGM 快捷生成 -->
    <div class="al-gen">
      <div class="al-gen-item">
        <button class="al-gen-head" :aria-expanded="ttsOpen" @click="ttsOpen = !ttsOpen">
          <i class="fa-solid fa-microphone"></i>
          {{ UI_TTS_PANEL }}
          <i class="fa-solid fa-chevron-down al-gen-chevron" :class="{ 'is-open': ttsOpen }"></i>
        </button>
        <div class="al-gen-collapse" :class="{ open: ttsOpen }" :inert="!ttsOpen">
          <div class="al-gen-collapse-inner">
            <div class="al-gen-body">
              <textarea v-model="ttsText" class="al-gen-textarea" rows="2" :placeholder="UI_TTS_TEXT_PLACEHOLDER" />
              <div class="al-gen-row">
                <label class="al-gen-voice">
                  <span>{{ UI_TTS_VOICE }}</span>
                  <select v-model="ttsVoice">
                    <option value="">{{ composerTtsDefaultVoice || "默认" }}</option>
                    <option v-for="v in composerTtsVoices" :key="v" :value="v">{{ v }}</option>
                  </select>
                </label>
                <button class="al-btn al-btn--primary" :disabled="ttsBusy || !ttsText.trim()" @click="handleTts">
                  <i v-if="ttsBusy" class="fa-solid fa-spinner fa-spin"></i>
                  {{ ttsBusy ? UI_GENERATING : UI_TTS_GENERATE }}
                </button>
              </div>
              <label class="al-check">
                <input v-model="ttsSplit" type="checkbox" />
                {{ UI_TTS_SPLIT }}
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="al-gen-item">
        <button class="al-gen-head" :aria-expanded="bgmOpen" @click="bgmOpen = !bgmOpen">
          <i class="fa-solid fa-music"></i>
          {{ UI_BGM_PANEL }}
          <i class="fa-solid fa-chevron-down al-gen-chevron" :class="{ 'is-open': bgmOpen }"></i>
        </button>
        <div class="al-gen-collapse" :class="{ open: bgmOpen }" :inert="!bgmOpen">
          <div class="al-gen-collapse-inner">
            <div class="al-gen-body">
              <input v-model="bgmStyle" class="al-url-input al-gen-style" :placeholder="UI_BGM_STYLE_PLACEHOLDER" @keydown.enter="handleBgm" />
              <div class="al-gen-row">
                <label class="al-gen-voice">
                  <span>时长（秒）</span>
                  <input v-model.number="bgmDuration" type="number" min="1" max="60" />
                </label>
                <button class="al-btn al-btn--primary" :disabled="bgmBusy || !bgmStyle.trim()" @click="handleBgm">
                  <i v-if="bgmBusy" class="fa-solid fa-spinner fa-spin"></i>
                  {{ bgmBusy ? UI_GENERATING : UI_BGM_GENERATE }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p v-if="genError" class="al-msg al-msg--error al-gen-msg">{{ genError }}</p>
      <p v-else-if="genNotice" class="al-msg al-gen-msg">{{ genNotice }}</p>
    </div>

    <!-- 类型过滤 -->
    <div class="al-filters">
      <button
        v-for="kind in COMPOSER_KINDS"
        :key="kind"
        class="al-filter-btn"
        :class="{ on: composerKindFilter === kind }"
        @click="setKindFilter(kind)"
      >
        <i v-if="kind !== 'all'" :class="COMPOSER_KIND_ICONS[kind]"></i>
        <i v-else class="fa-solid fa-layer-group"></i>
        {{ KIND_LABELS[kind] }}
      </button>
    </div>

    <!-- 素材网格 -->
    <div v-if="composerAssets.length" class="al-grid">
      <div v-for="asset in composerAssets" :key="asset.asset_id" class="al-card">
        <div class="al-thumb" @click="handlePreview(asset)">
          <img
            v-if="asset.kind === 'image'"
            :src="composerFileUrl(asset)"
            :alt="asset.sha256.slice(0, 8)"
            loading="lazy"
          />
          <video
            v-else-if="asset.kind === 'video'"
            :src="composerFileUrl(asset)"
            preload="metadata"
            muted
            playsinline
          ></video>
          <div v-else class="al-thumb--audio">
            <i class="fa-solid fa-music"></i>
          </div>
          <span class="al-kind-badge">
            <i :class="COMPOSER_KIND_ICONS[asset.kind] ?? 'fa-solid fa-file'"></i>
          </span>
        </div>
        <div class="al-card-info">
          <div class="al-card-meta" :title="probeSummary(asset)">{{ probeSummary(asset) }}</div>
          <div class="al-card-hash">{{ asset.sha256.slice(0, 12) }}</div>
          <div class="al-card-actions">
            <button
              class="al-card-btn"
              :title="UI_OPEN_IN_NEW_TAB"
              @click="handlePreview(asset)"
            >
              <i class="fa-solid fa-play"></i>
            </button>
            <button class="al-card-btn al-card-btn--danger" :title="UI_DELETE" @click="handleDelete(asset)">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="al-empty">
      <i class="fa-solid fa-photo-film al-empty-icon"></i>
      <p>{{ UI_ASSET_NO_ASSETS }}</p>
    </div>
  </div>
</template>

<style scoped>
.al-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── 导入区 ── */

.al-url-row {
  display: flex;
  gap: 8px;
}

.al-url-input {
  flex: 1;
  min-width: 0;
  padding: 7px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-mono);
  outline: none;
}
.al-url-input:focus { border-color: var(--accent); }

.al-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
  white-space: nowrap;
}
.al-btn:hover { color: var(--text-primary); background: var(--bg-hover); border-color: var(--text-dim); }
.al-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.al-btn--primary { color: var(--accent); border-color: var(--accent); background: var(--accent-bg); }
.al-btn--primary:hover { color: var(--white); background: var(--accent); }

.al-upload-row { display: flex; }
.al-upload-limit { font-size: 11px; color: var(--text-dim); }
.al-file-input { display: none; }

.al-msg { margin: 0; font-size: 12px; color: var(--success); white-space: pre-wrap; }
.al-msg--error { color: var(--error); }
.al-msg--warn { color: var(--warning); }

/* ── TTS / BGM 快捷生成 ── */

.al-gen {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.al-gen-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 3px 2px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}
.al-gen-head:hover { color: var(--text-primary); }
.al-gen-chevron {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-dim);
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}
.al-gen-chevron.is-open { transform: rotate(180deg); }

.al-gen-item { display: flex; flex-direction: column; }

/* 平滑展开：0fr → 1fr 的网格行高动画，无需测量内容高度 */
.al-gen-collapse {
  display: grid;
  grid-template-rows: 0fr;
  opacity: 0;
  transition:
    grid-template-rows 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.2s ease;
}
.al-gen-collapse.open { grid-template-rows: 1fr; opacity: 1; }
.al-gen-collapse-inner { min-height: 0; overflow: hidden; }

.al-gen-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 0 2px;
}

.al-gen-textarea {
  padding: 6px 9px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  font-family: inherit;
  resize: vertical;
  outline: none;
}
.al-gen-textarea:focus { border-color: var(--accent); }

.al-gen-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.al-gen-voice {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 10px;
  color: var(--text-dim);
}
.al-gen-voice select,
.al-gen-voice input {
  padding: 5px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
}
.al-gen-voice select:focus,
.al-gen-voice input:focus { border-color: var(--accent); }

.al-gen-style { flex: 1; }
.al-gen-msg { font-size: 11px; }

.al-check {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
}

/* ── 过滤 ── */

.al-filters { display: flex; gap: 6px; }

.al-filter-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 14px;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.al-filter-btn:hover { color: var(--text-secondary); background: var(--bg-hover); }
.al-filter-btn.on { color: var(--accent); border-color: var(--accent); background: var(--accent-bg); }

/* ── 网格 ── */

.al-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.al-card {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 0.15s;
}
.al-card:hover { border-color: var(--text-dim); }

.al-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  background: var(--bg-tertiary);
  cursor: pointer;
  overflow: hidden;
}
.al-thumb img,
.al-thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.al-thumb--audio {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: var(--text-dim);
}

.al-kind-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.55);
}

.al-card-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
}

.al-card-meta {
  font-size: 11px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.al-card-hash {
  font-size: 10px;
  color: var(--text-dim);
  font-family: var(--font-mono);
}

.al-card-actions {
  display: flex;
  gap: 4px;
  margin-top: 3px;
}

.al-card-btn {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.al-card-btn:hover { color: var(--text-primary); background: var(--bg-hover); border-color: var(--border); }
.al-card-btn--danger:hover { color: var(--error); border-color: var(--error); background: var(--error-bg-hover); }

/* ── 空态 ── */

.al-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 36px 0;
  color: var(--text-dim);
  font-size: 13px;
}
.al-empty-icon { font-size: 30px; }
.al-empty p { margin: 0; }
</style>
