<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { composerProjectSrtUrl } from "../../api/client";
import {
  COMPOSER_PANS,
  COMPOSER_PROJECT_SAVE_DELAY,
  COMPOSER_SUBTITLE_STYLES,
  COMPOSER_TRANSITION_TYPES,
  UI_AUDIO_BGM,
  UI_AUDIO_DUCKING,
  UI_AUDIO_FADE_IN,
  UI_AUDIO_FADE_OUT,
  UI_AUDIO_GAIN,
  UI_AUDIO_LOOP,
  UI_AUDIO_NARRATION,
  UI_AUDIO_NONE,
  UI_AUDIO_TRACKS,
  UI_DELETE,
  UI_DOWNLOAD,
  UI_PROJECT_SAVE_ERROR,
  UI_PROJECT_SAVED,
  UI_PROJECT_SAVING,
  UI_PROJECT_SELECT_HINT,
  UI_RENDER_START,
  UI_RENDER_STARTED,
  UI_RENDER_SUBMIT_FAILED,
  UI_SHOT_ADD,
  UI_SHOT_ASSET,
  UI_SHOT_DURATION,
  UI_SHOT_EMPTY,
  UI_SHOT_LIST,
  UI_SHOT_MOTION,
  UI_SHOT_PAN,
  UI_SHOT_TRANSITION,
  UI_SHOT_TRANSITION_TYPE,
  UI_SHOT_TRIM_IN,
  UI_SHOT_ZOOM_FROM,
  UI_SHOT_ZOOM_TO,
  UI_SUBTITLE_ADD,
  UI_SUBTITLE_END,
  UI_SUBTITLE_LIST,
  UI_SUBTITLE_START,
  UI_SUBTITLE_STYLE,
  UI_SUBTITLE_TEXT,
} from "../../constants";
import {
  activeProject,
  composerAssets,
  composerFileUrl,
  composerPresets,
  composerSaveState,
  composerTimelineErrors,
  parseComposerError,
  saveComposerTimeline,
  startComposerRenderItem,
} from "../../composables/useComposer";
import type {
  ComposerAsset,
  Timeline,
  TimelineAudioTrack,
  TimelineVideoSegment,
} from "../../types/api";

// ── 草稿（编辑中的时间轴副本）──────────────────────

const draft = ref<Timeline | null>(null);
let _saveTimer: ReturnType<typeof setTimeout> | null = null;
let _ownSave = false;

function cloneTimeline(timeline: Timeline): Timeline {
  return JSON.parse(JSON.stringify(timeline)) as Timeline;
}

function resetDraft(): void {
  const project = activeProject.value;
  draft.value = project ? cloneTimeline(project.timeline) : null;
  _ensureTracks();
}

function _ensureTracks(): void {
  if (!draft.value) return;
  const tracks = draft.value.tracks;
  if (!Array.isArray(tracks.video)) tracks.video = [];
  if (!Array.isArray(tracks.audio)) tracks.audio = [];
  if (!Array.isArray(tracks.subtitles)) tracks.subtitles = [];
}

watch(() => activeProject.value?.project_id, resetDraft, { immediate: true });

// Agent 侧更新（外部 SSE）→ 无待保存改动时同步草稿
watch(() => activeProject.value?.updated_at, () => {
  if (_ownSave || _saveTimer) return;
  resetDraft();
});

onUnmounted(() => {
  if (_saveTimer) clearTimeout(_saveTimer);
});

// ── 保存（防抖）──────────────────────────────────

function scheduleSave(): void {
  if (!activeProject.value) return;
  if (_saveTimer) clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => {
    _saveTimer = null;
    void doSave();
  }, COMPOSER_PROJECT_SAVE_DELAY);
}

async function doSave(): Promise<void> {
  const project = activeProject.value;
  if (!project || !draft.value) return;
  _ownSave = true;
  try {
    await saveComposerTimeline(project.project_id, draft.value);
  } finally {
    setTimeout(() => { _ownSave = false; }, 100);
  }
}

// ── 素材查找 ─────────────────────────────────────

function videoAssets(): ComposerAsset[] {
  return composerAssets.value.filter(a => a.kind === "video" || a.kind === "image");
}

function audioAssets(): ComposerAsset[] {
  return composerAssets.value.filter(a => a.kind === "audio");
}

function assetById(id: string): ComposerAsset | undefined {
  return composerAssets.value.find(a => a.asset_id === id);
}

function assetLabel(asset: ComposerAsset): string {
  const suffix = asset.kind === "image" ? "图片" : asset.kind === "video" ? "视频" : "音频";
  return `${suffix} · ${asset.sha256.slice(0, 8)}`;
}

// ── 镜头 ─────────────────────────────────────────

const shots = computed<TimelineVideoSegment[]>(() => draft.value?.tracks.video ?? []);

function addShot(): void {
  if (!draft.value) return;
  const first = videoAssets()[0];
  if (!first) return;
  const probeDuration = Number(first.probe?.duration ?? 0);
  draft.value.tracks.video.push({
    asset_id: first.asset_id,
    duration: first.kind === "image" ? 3 : Math.max(1, probeDuration || 3),
    trim_in: 0,
    transition_in: { type: "fade", duration: 0 },
    motion: { type: "static", from_zoom: 1, to_zoom: 1, pan: "none" },
  });
  scheduleSave();
}

function removeShot(index: number): void {
  if (!draft.value) return;
  draft.value.tracks.video.splice(index, 1);
  scheduleSave();
}

function onShotAssetChange(shot: TimelineVideoSegment, assetId: string): void {
  shot.asset_id = assetId;
  const asset = assetById(assetId);
  if (asset && asset.kind === "video") {
    const probeDuration = Number(asset.probe?.duration ?? 0);
    if (probeDuration > 0) {
      shot.duration = Math.min(shot.duration || probeDuration, probeDuration);
      shot.trim_in = 0;
      shot.motion = { type: "static", pan: "none" };
    }
  } else if (asset && asset.kind === "image") {
    if (!shot.duration || shot.duration > 30) shot.duration = 3;
    shot.motion = { type: "kenburns", from_zoom: 1, to_zoom: 1.12, pan: "none" };
  }
  scheduleSave();
}

// ── 音频（旁白 / BGM 各一行）─────────────────────

function findTrack(role: "narration" | "bgm"): TimelineAudioTrack | undefined {
  return draft.value?.tracks.audio.find(t => t.role === role);
}

const narration = computed<TimelineAudioTrack | undefined>(() => findTrack("narration"));
const bgm = computed<TimelineAudioTrack | undefined>(() => findTrack("bgm"));

function setAudioTrack(role: "narration" | "bgm", assetId: string): void {
  if (!draft.value) return;
  const idx = draft.value.tracks.audio.findIndex(t => t.role === role);
  if (!assetId) {
    if (idx >= 0) draft.value.tracks.audio.splice(idx, 1);
    scheduleSave();
    return;
  }
  const asset = assetById(assetId);
  const probeDuration = Number(asset?.probe?.duration ?? 0);
  const totalVideo = shots.value.reduce((sum, s) => sum + (Number(s.duration) || 0), 0);
  const track: TimelineAudioTrack = idx >= 0
    ? draft.value.tracks.audio[idx]
    : {
        role, asset_id: assetId, start: 0,
        duration: role === "bgm" ? Math.max(totalVideo, probeDuration || 11) : (probeDuration || 5),
        gain: role === "bgm" ? 0.35 : 1.0,
        fade_in: role === "bgm" ? 0.5 : 0,
        fade_out: role === "bgm" ? 2.0 : 0,
        loop: role === "bgm",
        ducking: role === "bgm",
      };
  track.asset_id = assetId;
  if (idx < 0) draft.value.tracks.audio.push(track);
  scheduleSave();
}

// ── 字幕 ─────────────────────────────────────────

const subtitles = computed(() => draft.value?.tracks.subtitles ?? []);

function addSubtitle(): void {
  if (!draft.value) return;
  const total = shots.value.reduce((sum, s) => sum + (Number(s.duration) || 0), 0);
  draft.value.tracks.subtitles.push({
    start: 0,
    end: Math.min(2.5, total || 2.5),
    text: "",
    style: "default",
  });
  scheduleSave();
}

function removeSubtitle(index: number): void {
  if (!draft.value) return;
  draft.value.tracks.subtitles.splice(index, 1);
  scheduleSave();
}

// ── 展示辅助 ─────────────────────────────────────

function presetOptions(): string[] {
  return Object.keys(composerPresets.value);
}

function totalDuration(): number {
  return shots.value.reduce((sum, s) => sum + (Number(s.duration) || 0), 0);
}

// ── 提交渲染 ─────────────────────────────────────

const submittingRender = ref(false);
const renderNotice = ref("");
const renderError = ref("");

async function submitRender(): Promise<void> {
  const project = activeProject.value;
  if (!project || submittingRender.value) return;
  submittingRender.value = true;
  renderNotice.value = "";
  renderError.value = "";
  try {
    // 先确保最新编辑已保存
    if (_saveTimer) {
      clearTimeout(_saveTimer);
      _saveTimer = null;
    }
    await doSave();
    await startComposerRenderItem(project.project_id);
    renderNotice.value = UI_RENDER_STARTED;
    setTimeout(() => { renderNotice.value = ""; }, 5000);
  } catch (e) {
    renderError.value = `${UI_RENDER_SUBMIT_FAILED}：${parseComposerError(e).join("；")}`;
  } finally {
    submittingRender.value = false;
  }
}
</script>

<template>
  <div class="sb-body">
    <!-- 无选中项目 -->
    <div v-if="!activeProject || !draft" class="sb-empty">
      <i class="fa-solid fa-diagram-project"></i>
      <p>{{ UI_PROJECT_SELECT_HINT }}</p>
    </div>

    <template v-else>
      <!-- 头部：标题 / 预设 / 保存状态 / SRT -->
      <div class="sb-header">
        <div class="sb-header-main">
          <span class="sb-title">{{ activeProject.title }}</span>
          <span class="sb-sub">
            总时长 {{ totalDuration().toFixed(1) }}s ·
            {{ shots.length }} 镜头 · {{ subtitles.length }} 字幕
          </span>
        </div>
        <select v-model="draft.preset" class="sb-preset" @change="scheduleSave">
          <option v-for="p in presetOptions()" :key="p" :value="p">{{ p }}</option>
        </select>
        <span class="sb-save" :class="`sb-save--${composerSaveState}`">
          <template v-if="composerSaveState === 'saving'"><i class="fa-solid fa-spinner fa-spin"></i> {{ UI_PROJECT_SAVING }}</template>
          <template v-else-if="composerSaveState === 'saved'"><i class="fa-solid fa-check"></i> {{ UI_PROJECT_SAVED }}</template>
          <template v-else-if="composerSaveState === 'error'"><i class="fa-solid fa-triangle-exclamation"></i> {{ UI_PROJECT_SAVE_ERROR }}</template>
        </span>
        <button class="sb-render" :disabled="submittingRender || !shots.length" @click="submitRender">
          <i v-if="submittingRender" class="fa-solid fa-spinner fa-spin"></i>
          <i v-else class="fa-solid fa-film"></i>
          {{ UI_RENDER_START }}
        </button>
        <a class="sb-srt" :href="composerProjectSrtUrl(activeProject.project_id)" target="_blank" rel="noopener" :title="UI_DOWNLOAD">
          <i class="fa-solid fa-download"></i> SRT
        </a>
      </div>

      <p v-if="renderNotice" class="sb-render-msg">{{ renderNotice }}</p>
      <p v-if="renderError" class="sb-render-msg sb-render-msg--err">{{ renderError }}</p>

      <!-- 校验错误 -->
      <div v-if="composerTimelineErrors.length" class="sb-errors">
        <p v-for="(err, i) in composerTimelineErrors" :key="i">· {{ err }}</p>
      </div>

      <!-- 镜头列表 -->
      <section class="sb-section">
        <div class="sb-section-head">
          <h4><i class="fa-solid fa-video"></i> {{ UI_SHOT_LIST }}（{{ shots.length }}）</h4>
          <button class="sb-add-btn" :disabled="!videoAssets().length" @click="addShot">
            <i class="fa-solid fa-plus"></i> {{ UI_SHOT_ADD }}
          </button>
        </div>
        <p v-if="!shots.length" class="sb-hint">{{ UI_SHOT_EMPTY }}</p>
        <div v-for="(shot, i) in shots" :key="i" class="sb-shot">
          <div class="sb-shot-thumb">
            <img
              v-if="assetById(shot.asset_id)?.kind === 'image'"
              :src="assetById(shot.asset_id) ? composerFileUrl(assetById(shot.asset_id)!) : ''"
              alt=""
              loading="lazy"
            />
            <video
              v-else-if="assetById(shot.asset_id)?.kind === 'video'"
              :src="assetById(shot.asset_id) ? composerFileUrl(assetById(shot.asset_id)!) : ''"
              preload="metadata"
              muted
            ></video>
            <i v-else class="fa-solid fa-image"></i>
            <span class="sb-shot-no">{{ i + 1 }}</span>
          </div>
          <div class="sb-shot-fields">
            <label class="sb-field sb-field--wide">
              <span>{{ UI_SHOT_ASSET }}</span>
              <select :value="shot.asset_id" @change="onShotAssetChange(shot, ($event.target as HTMLSelectElement).value)">
                <option v-for="a in videoAssets()" :key="a.asset_id" :value="a.asset_id">{{ assetLabel(a) }}</option>
              </select>
            </label>
            <label class="sb-field">
              <span>{{ UI_SHOT_DURATION }}</span>
              <input v-model.number="shot.duration" type="number" min="0.5" step="0.5" @change="scheduleSave" />
            </label>
            <label class="sb-field">
              <span>{{ UI_SHOT_TRIM_IN }}</span>
              <input v-model.number="shot.trim_in" type="number" min="0" step="0.5" :disabled="assetById(shot.asset_id)?.kind === 'image'" @change="scheduleSave" />
            </label>
            <label class="sb-field">
              <span>{{ UI_SHOT_TRANSITION_TYPE }}</span>
              <select v-model="shot.transition_in!.type" :disabled="i === 0" @change="scheduleSave">
                <option v-for="t in COMPOSER_TRANSITION_TYPES" :key="t.id" :value="t.id">{{ t.label }}</option>
              </select>
            </label>
            <label class="sb-field">
              <span>{{ UI_SHOT_TRANSITION }}</span>
              <input
                v-model.number="shot.transition_in!.duration"
                type="number" min="0" step="0.1" :disabled="i === 0"
                @change="scheduleSave"
              />
            </label>
            <label class="sb-field">
              <span>{{ UI_SHOT_MOTION }}</span>
              <select v-model="shot.motion!.type" @change="scheduleSave">
                <option value="static">定格</option>
                <option value="kenburns">Ken Burns</option>
              </select>
            </label>
            <template v-if="assetById(shot.asset_id)?.kind === 'image' && shot.motion?.type === 'kenburns'">
              <label class="sb-field">
                <span>{{ UI_SHOT_ZOOM_FROM }}</span>
                <input v-model.number="shot.motion!.from_zoom" type="number" min="0.5" max="3" step="0.05" @change="scheduleSave" />
              </label>
              <label class="sb-field">
                <span>{{ UI_SHOT_ZOOM_TO }}</span>
                <input v-model.number="shot.motion!.to_zoom" type="number" min="0.5" max="3" step="0.05" @change="scheduleSave" />
              </label>
              <label class="sb-field">
                <span>{{ UI_SHOT_PAN }}</span>
                <select v-model="shot.motion!.pan" @change="scheduleSave">
                  <option v-for="p in COMPOSER_PANS" :key="p.id" :value="p.id">{{ p.label }}</option>
                </select>
              </label>
            </template>
            <button class="sb-del" :title="UI_DELETE" @click="removeShot(i)">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      </section>

      <!-- 字幕列表 -->
      <section class="sb-section">
        <div class="sb-section-head">
          <h4><i class="fa-solid fa-closed-captioning"></i> {{ UI_SUBTITLE_LIST }}（{{ subtitles.length }}）</h4>
          <button class="sb-add-btn" @click="addSubtitle">
            <i class="fa-solid fa-plus"></i> {{ UI_SUBTITLE_ADD }}
          </button>
        </div>
        <div v-for="(sub, i) in subtitles" :key="i" class="sb-sub-row">
          <label class="sb-field">
            <span>{{ UI_SUBTITLE_START }}</span>
            <input v-model.number="sub.start" type="number" min="0" step="0.1" @change="scheduleSave" />
          </label>
          <label class="sb-field">
            <span>{{ UI_SUBTITLE_END }}</span>
            <input v-model.number="sub.end" type="number" min="0" step="0.1" @change="scheduleSave" />
          </label>
          <label class="sb-field">
            <span>{{ UI_SUBTITLE_STYLE }}</span>
            <select v-model="sub.style" @change="scheduleSave">
              <option v-for="s in COMPOSER_SUBTITLE_STYLES" :key="s.id" :value="s.id">{{ s.label }}</option>
            </select>
          </label>
          <label class="sb-field sb-field--grow">
            <span>{{ UI_SUBTITLE_TEXT }}</span>
            <input v-model="sub.text" type="text" @change="scheduleSave" />
          </label>
          <button class="sb-del" :title="UI_DELETE" @click="removeSubtitle(i)">
            <i class="fa-solid fa-trash"></i>
          </button>
        </div>
      </section>

      <!-- 音频轨：旁白 / BGM -->
      <section class="sb-section">
        <div class="sb-section-head">
          <h4><i class="fa-solid fa-headphones"></i> {{ UI_AUDIO_TRACKS }}</h4>
        </div>

        <div class="sb-audio-row">
          <span class="sb-audio-label">{{ UI_AUDIO_NARRATION }}</span>
          <select :value="narration?.asset_id ?? ''" @change="setAudioTrack('narration', ($event.target as HTMLSelectElement).value)">
            <option value="">{{ UI_AUDIO_NONE }}</option>
            <option v-for="a in audioAssets()" :key="a.asset_id" :value="a.asset_id">{{ assetLabel(a) }}</option>
          </select>
          <template v-if="narration">
            <label class="sb-field">
              <span>{{ UI_AUDIO_GAIN }}</span>
              <input v-model.number="narration.gain" type="number" min="0" max="2" step="0.05" @change="scheduleSave" />
            </label>
          </template>
        </div>

        <div class="sb-audio-row">
          <span class="sb-audio-label">{{ UI_AUDIO_BGM }}</span>
          <select :value="bgm?.asset_id ?? ''" @change="setAudioTrack('bgm', ($event.target as HTMLSelectElement).value)">
            <option value="">{{ UI_AUDIO_NONE }}</option>
            <option v-for="a in audioAssets()" :key="a.asset_id" :value="a.asset_id">{{ assetLabel(a) }}</option>
          </select>
          <template v-if="bgm">
            <label class="sb-field">
              <span>{{ UI_AUDIO_GAIN }}</span>
              <input v-model.number="bgm.gain" type="number" min="0" max="2" step="0.05" @change="scheduleSave" />
            </label>
            <label class="sb-field">
              <span>{{ UI_AUDIO_FADE_IN }}</span>
              <input v-model.number="bgm.fade_in" type="number" min="0" step="0.5" @change="scheduleSave" />
            </label>
            <label class="sb-field">
              <span>{{ UI_AUDIO_FADE_OUT }}</span>
              <input v-model.number="bgm.fade_out" type="number" min="0" step="0.5" @change="scheduleSave" />
            </label>
            <label class="sb-check">
              <input v-model="bgm.loop" type="checkbox" @change="scheduleSave" />
              {{ UI_AUDIO_LOOP }}
            </label>
            <label class="sb-check">
              <input
                type="checkbox"
                :checked="bgm.ducking !== false"
                @change="bgm.ducking = ($event.target as HTMLInputElement).checked; scheduleSave()"
              />
              {{ UI_AUDIO_DUCKING }}
            </label>
          </template>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.sb-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-dim);
  font-size: 13px;
}
.sb-empty i { font-size: 28px; }
.sb-empty p { margin: 0; }

/* ── 头部 ── */

.sb-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.sb-header-main { flex: 1; min-width: 140px; display: flex; flex-direction: column; gap: 2px; }
.sb-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.sb-sub { font-size: 11px; color: var(--text-dim); }

.sb-preset,
.sb-audio-row select {
  padding: 5px 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 12px;
  outline: none;
}
.sb-preset:focus,
.sb-audio-row select:focus { border-color: var(--accent); }

.sb-save { font-size: 11px; color: var(--text-dim); display: inline-flex; align-items: center; gap: 4px; }
.sb-save--saved { color: var(--success); }
.sb-save--error { color: var(--error); }

.sb-srt {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-dim);
  font-size: 12px;
  text-decoration: none;
}
.sb-srt:hover { color: var(--accent); border-color: var(--accent); }

.sb-render {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-bg);
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.sb-render:hover { color: var(--white); background: var(--accent); }
.sb-render:disabled { opacity: 0.45; cursor: not-allowed; }

.sb-render-msg { margin: 0; font-size: 12px; color: var(--success); }
.sb-render-msg--err { color: var(--error); }

/* ── 错误 ── */

.sb-errors {
  padding: 8px 10px;
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  border-radius: var(--radius);
}
.sb-errors p { margin: 0; font-size: 12px; color: var(--error); line-height: 1.6; }

/* ── 通用 section ── */

.sb-section { display: flex; flex-direction: column; gap: 8px; }

.sb-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.sb-section-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.sb-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
}
.sb-add-btn:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-bg-subtle); }
.sb-add-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.sb-hint { margin: 0; font-size: 12px; color: var(--text-dim); }

/* ── 镜头卡片 ── */

.sb-shot {
  display: flex;
  gap: 10px;
  padding: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.sb-shot-thumb {
  position: relative;
  width: 92px;
  height: 60px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
}
.sb-shot-thumb img,
.sb-shot-thumb video { width: 100%; height: 100%; object-fit: cover; }
.sb-shot-no {
  position: absolute;
  top: 3px;
  left: 3px;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.6);
  color: var(--text-primary);
  font-size: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.sb-shot-fields {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 8px;
  align-items: flex-end;
}

.sb-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 64px;
}
.sb-field--wide { flex: 1; min-width: 120px; }
.sb-field--grow { flex: 1; min-width: 120px; }
.sb-field span { font-size: 10px; color: var(--text-dim); }
.sb-field input,
.sb-field select {
  padding: 4px 7px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  font-family: inherit;
  outline: none;
  width: 100%;
}
.sb-field input:focus,
.sb-field select:focus { border-color: var(--accent); }
.sb-field input:disabled { opacity: 0.45; }

.sb-del {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  align-self: flex-end;
}
.sb-del:hover { color: var(--error); border-color: var(--error); background: var(--error-bg-hover); }

/* ── 字幕 ── */

.sb-sub-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 6px 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

/* ── 音频 ── */

.sb-audio-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.sb-audio-label {
  width: 62px;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-secondary);
  padding-bottom: 5px;
}
.sb-audio-row select { min-width: 160px; }

.sb-check {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-secondary);
  padding-bottom: 5px;
  cursor: pointer;
}
</style>
