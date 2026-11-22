<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import {
  UI_TRACK_NO_PREVIEW,
  UI_TRACK_PREVIEW,
} from "../../constants";
import {
  composerAssets,
  composerFileUrl,
} from "../../composables/useComposer";
import type { ComposerAsset, Timeline, TimelineVideoSegment } from "../../types/api";

const props = defineProps<{
  timeline: Timeline;
}>();

const emit = defineEmits<{
  changed: [];
}>();

// ── 基础数据 ─────────────────────────────────────

const segments = computed<TimelineVideoSegment[]>(() => props.timeline.tracks.video ?? []);

const starts = computed<number[]>(() => {
  const result: number[] = [];
  let acc = 0;
  for (const seg of segments.value) {
    result.push(acc);
    acc += Number(seg.duration) || 0;
  }
  return result;
});

const total = computed(() => {
  const sum = segments.value.reduce((s, seg) => s + (Number(seg.duration) || 0), 0);
  return Math.max(0.1, sum);
});

const innerWidth = computed(() => Math.max(420, Math.round(total.value * 36)));

function pct(seconds: number): string {
  return `${Math.max(0, Math.min(100, (seconds / total.value) * 100))}%`;
}

const ticks = computed(() => {
  const step = total.value <= 20 ? 1 : total.value <= 60 ? 5 : 10;
  const list: number[] = [];
  for (let t = 0; t <= total.value + 0.001; t += step) list.push(Math.round(t * 10) / 10);
  if (list[list.length - 1] < total.value) list.push(Math.round(total.value * 10) / 10);
  return list;
});

function assetById(id: string): ComposerAsset | undefined {
  return composerAssets.value.find(a => a.asset_id === id);
}

// ── 播放头与预览 ─────────────────────────────────

const playhead = ref(0);

const currentIndex = computed(() => {
  const t = playhead.value;
  for (let i = 0; i < segments.value.length; i++) {
    const start = starts.value[i] ?? 0;
    const dur = Number(segments.value[i].duration) || 0;
    if (t >= start && t < start + dur) return i;
  }
  return segments.value.length > 0 ? segments.value.length - 1 : -1;
});

const currentSeg = computed(() => (currentIndex.value >= 0 ? segments.value[currentIndex.value] : null));
const currentAsset = computed(() => {
  const seg = currentSeg.value;
  return seg ? assetById(seg.asset_id) : undefined;
});

const previewVideo = ref<HTMLVideoElement | null>(null);

function seekPreview(): void {
  const seg = currentSeg.value;
  const asset = currentAsset.value;
  if (!seg || !asset || asset.kind !== "video" || !previewVideo.value) return;
  const within = Math.max(0, playhead.value - (starts.value[currentIndex.value] ?? 0));
  const target = Number(seg.trim_in ?? 0) + within;
  try {
    previewVideo.value.currentTime = Math.min(target, Number(asset.probe?.duration ?? target));
  } catch {
    /* metadata 尚未就绪，忽略 */
  }
}

watch([playhead, currentIndex], () => { void nextTick(seekPreview); });

function onRulerClick(e: MouseEvent): void {
  const el = e.currentTarget as HTMLElement;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0) return;
  const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
  playhead.value = ratio * total.value;
}

function selectSegment(index: number): void {
  playhead.value = starts.value[index] ?? 0;
}

// ── 拖拽重排 ─────────────────────────────────────

const dragIndex = ref<number | null>(null);
const dragOverIndex = ref<number | null>(null);

function onDragStart(index: number, e: DragEvent): void {
  dragIndex.value = index;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(index));
  }
}

function onDragOver(index: number, e: DragEvent): void {
  e.preventDefault();
  dragOverIndex.value = index;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}

function onDrop(index: number): void {
  const from = dragIndex.value;
  dragIndex.value = null;
  dragOverIndex.value = null;
  if (from === null || from === index) return;
  const list = props.timeline.tracks.video;
  const [moved] = list.splice(from, 1);
  list.splice(index, 0, moved);
  emit("changed");
}

function onDragEnd(): void {
  dragIndex.value = null;
  dragOverIndex.value = null;
}

// ── 音频 / 字幕 ──────────────────────────────────

function audioTracks(role: "narration" | "bgm") {
  return (props.timeline.tracks.audio ?? []).filter(t => t.role === role);
}

function audioLeft(start: number): string {
  return pct(start);
}

function audioWidth(start: number, duration: number, loop: boolean): string {
  const end = loop ? total.value : Math.min(total.value, start + duration);
  return pct(Math.max(0.1, end - start));
}

const subtitles = computed(() => props.timeline.tracks.subtitles ?? []);
</script>

<template>
  <div class="tt-body">
    <!-- 播放头预览 -->
    <div class="tt-preview">
      <span class="tt-preview-label">{{ UI_TRACK_PREVIEW }} · {{ playhead.toFixed(1) }}s</span>
      <div v-if="currentAsset" class="tt-preview-media">
        <img
          v-if="currentAsset.kind === 'image'"
          :src="composerFileUrl(currentAsset)"
          alt=""
        />
        <video
          v-else-if="currentAsset.kind === 'video'"
          :key="currentAsset.asset_id"
          ref="previewVideo"
          :src="composerFileUrl(currentAsset)"
          preload="metadata"
          muted
          @loadedmetadata="seekPreview"
        ></video>
        <div v-else class="tt-preview-empty">{{ currentAsset.kind }}</div>
      </div>
      <div v-else class="tt-preview-empty">{{ UI_TRACK_NO_PREVIEW }}</div>
    </div>

    <!-- 时间轴 -->
    <div class="tt-scroll">
      <div class="tt-inner" :style="{ width: `${innerWidth}px` }">
        <!-- 标尺 -->
        <div class="tt-ruler" @click="onRulerClick">
          <span v-for="t in ticks" :key="t" class="tt-tick" :style="{ left: pct(t) }">{{ t }}s</span>
        </div>

        <!-- 视频轨 -->
        <div class="tt-lane">
          <div class="tt-lane-label">视频</div>
          <div class="tt-track tt-track--video" @click="onRulerClick">
            <div
              v-for="(seg, i) in segments"
              :key="`${seg.asset_id}-${i}`"
              class="tt-block"
              :class="{ 'tt-block--active': i === currentIndex, 'tt-block--over': i === dragOverIndex }"
              :style="{ left: pct(starts[i] ?? 0), width: pct(Number(seg.duration) || 0) }"
              draggable="true"
              @dragstart="onDragStart(i, $event)"
              @dragover="onDragOver(i, $event)"
              @drop.stop.prevent="onDrop(i)"
              @dragend="onDragEnd"
              @click.stop="selectSegment(i)"
            >
              <img
                v-if="assetById(seg.asset_id)?.kind === 'image'"
                :src="composerFileUrl(assetById(seg.asset_id)!)"
                alt=""
                loading="lazy"
              />
              <div class="tt-block-meta">
                <span>{{ i + 1 }} · {{ Number(seg.duration).toFixed(1) }}s</span>
                <span v-if="seg.motion?.type === 'kenburns'" class="tt-badge">KB</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 旁白轨 -->
        <div class="tt-lane">
          <div class="tt-lane-label">旁白</div>
          <div class="tt-track tt-track--narration">
            <div
              v-for="(trk, i) in audioTracks('narration')"
              :key="`n-${i}`"
              class="tt-audio-bar"
              :style="{ left: audioLeft(trk.start), width: audioWidth(trk.start, trk.duration, false) }"
            ></div>
          </div>
        </div>

        <!-- BGM 轨 -->
        <div class="tt-lane">
          <div class="tt-lane-label">BGM</div>
          <div class="tt-track tt-track--bgm">
            <div
              v-for="(trk, i) in audioTracks('bgm')"
              :key="`b-${i}`"
              class="tt-audio-bar"
              :style="{ left: audioLeft(trk.start), width: audioWidth(trk.start, trk.duration, !!trk.loop) }"
            ></div>
          </div>
        </div>

        <!-- 字幕轨 -->
        <div class="tt-lane">
          <div class="tt-lane-label">字幕</div>
          <div class="tt-track tt-track--subs">
            <span
              v-for="(sub, i) in subtitles"
              :key="`s-${i}`"
              class="tt-sub"
              :title="sub.text"
              :style="{ left: pct(sub.start), width: pct(Math.max(0.15, sub.end - sub.start)) }"
            ></span>
          </div>
        </div>

        <!-- 播放头 -->
        <div class="tt-playhead" :style="{ left: pct(playhead) }"></div>
      </div>
    </div>

    <p class="tt-hint">拖动视频块可调整镜头顺序；点击标尺定位播放头。</p>
  </div>
</template>

<style scoped>
.tt-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── 预览 ── */

.tt-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tt-preview-label { font-size: 11px; color: var(--text-dim); }
.tt-preview-media {
  height: 120px;
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
}
.tt-preview-media img,
.tt-preview-media video {
  max-width: 100%;
  max-height: 120px;
  object-fit: contain;
}
.tt-preview-empty {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  color: var(--text-dim);
  font-size: 12px;
}

/* ── 时间轴 ── */

.tt-scroll {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-primary);
}
.tt-inner {
  position: relative;
  padding: 6px 8px 10px;
  min-width: 100%;
}

.tt-ruler {
  position: relative;
  height: 20px;
  margin-left: 52px;
  cursor: pointer;
  border-bottom: 1px solid var(--border);
}
.tt-tick {
  position: absolute;
  top: 2px;
  transform: translateX(-50%);
  font-size: 10px;
  color: var(--text-dim);
  white-space: nowrap;
}
.tt-tick::before {
  content: "";
  position: absolute;
  left: 50%;
  top: 14px;
  width: 1px;
  height: 5px;
  background: var(--border);
}

.tt-lane {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.tt-lane-label {
  width: 46px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-dim);
  text-align: right;
}
.tt-track {
  position: relative;
  flex: 1;
  height: 40px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.tt-track--narration,
.tt-track--bgm { height: 20px; }
.tt-track--subs { height: 16px; }

.tt-block {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--bg-tertiary);
  cursor: grab;
  min-width: 10px;
}
.tt-block:active { cursor: grabbing; }
.tt-block img { width: 100%; height: 100%; object-fit: cover; opacity: 0.7; }
.tt-block--active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.tt-block--over { border-color: var(--success); }
.tt-block-meta {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1px 4px;
  font-size: 9px;
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.55);
}
.tt-badge { color: var(--warning); font-weight: 700; }

.tt-audio-bar {
  position: absolute;
  top: 3px;
  bottom: 3px;
  border-radius: 2px;
  background: var(--accent-bg-mid);
  border: 1px solid var(--accent-strong);
  min-width: 3px;
}
.tt-track--bgm .tt-audio-bar {
  background: rgba(245, 165, 36, 0.12);
  border-color: rgba(245, 165, 36, 0.4);
}

.tt-sub {
  position: absolute;
  top: 4px;
  bottom: 4px;
  border-radius: 2px;
  background: var(--success);
  opacity: 0.7;
}

.tt-playhead {
  position: absolute;
  top: 26px;
  bottom: 10px;
  width: 2px;
  background: var(--error);
  pointer-events: none;
  transform: translateX(-1px);
}

.tt-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-dim);
}
</style>
