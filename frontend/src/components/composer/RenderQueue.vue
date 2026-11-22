<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { cleanupComposerStorage, composerRenderFileUrl } from "../../api/client";
import {
  COMPOSER_RENDER_ACTIVE_STATES,
  COMPOSER_RENDER_STATE_ICONS,
  COMPOSER_RENDER_STATE_LABELS,
  UI_CLEANUP_DISK,
  UI_RENDER_CANCEL,
  UI_RENDER_DOWNLOAD,
  UI_RENDER_ERROR,
  UI_RENDER_NONE,
  UI_RENDER_PREVIEW,
  UI_RENDER_START,
  UI_RENDER_SUBMIT_FAILED,
  UI_RENDER_WARN,
} from "../../constants";
import {
  cancelComposerRenderItem,
  composerRenderWarn,
  composerRenders,
  parseComposerError,
  refreshComposerRenders,
  startComposerRenderItem,
} from "../../composables/useComposer";
import type { ComposerRender, ComposerRenderState, PreviewPayload } from "../../types/api";

const props = defineProps<{
  projectId?: string;
}>();

const emit = defineEmits<{
  preview: [payload: PreviewPayload];
}>();

const submitting = ref(false);
const actionError = ref("");
const cleaning = ref(false);
const cleanupMsg = ref("");

const renders = computed<ComposerRender[]>(() => {
  if (!props.projectId) return composerRenders.value;
  return composerRenders.value.filter(r => r.project_id === props.projectId);
});

function isActive(state: ComposerRenderState): boolean {
  return (COMPOSER_RENDER_ACTIVE_STATES as readonly string[]).includes(state);
}

function stateLabel(state: ComposerRenderState): string {
  return COMPOSER_RENDER_STATE_LABELS[state] ?? state;
}

function stateIcon(state: ComposerRenderState): string {
  return COMPOSER_RENDER_STATE_ICONS[state] ?? "fa-solid fa-circle";
}

function stageText(render: ComposerRender): string {
  const stage = render.stage_detail ?? {};
  if (stage.current) return String(stage.current);
  return stateLabel(render.state);
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
}

function handlePreview(render: ComposerRender): void {
  emit("preview", {
    kind: "video",
    src: composerRenderFileUrl(render.render_id),
    filename: `${render.render_id}.mp4`,
  });
}

async function handleStart(): Promise<void> {
  if (!props.projectId || submitting.value) return;
  submitting.value = true;
  actionError.value = "";
  try {
    await startComposerRenderItem(props.projectId);
    await refreshComposerRenders(props.projectId);
  } catch (e) {
    actionError.value = parseComposerError(e).join("\n");
  } finally {
    submitting.value = false;
  }
}

async function handleCancel(render: ComposerRender): Promise<void> {
  actionError.value = "";
  try {
    await cancelComposerRenderItem(render.render_id);
  } catch (e) {
    actionError.value = parseComposerError(e).join("\n");
  }
}

function refresh(): void {
  refreshComposerRenders(props.projectId);
}

async function handleCleanup(): Promise<void> {
  if (cleaning.value) return;
  cleaning.value = true;
  cleanupMsg.value = "";
  try {
    const resp = await cleanupComposerStorage();
    cleanupMsg.value = resp.message || "";
    await refreshComposerRenders(props.projectId);
  } catch (e) {
    actionError.value = parseComposerError(e).join("；");
  } finally {
    cleaning.value = false;
  }
}

onMounted(refresh);
watch(() => props.projectId, refresh);
</script>

<template>
  <div class="rq-body">
    <!-- 告警 -->
    <div v-if="composerRenderWarn" class="rq-warn">
      <i class="fa-solid fa-triangle-exclamation"></i>
      <span><strong>{{ UI_RENDER_WARN }}：</strong>{{ composerRenderWarn }}</span>
    </div>

    <!-- 头部操作 -->
    <div class="rq-header">
      <span class="rq-title">渲染任务（{{ renders.length }}）</span>
      <button class="rq-btn rq-btn--primary" :disabled="!projectId || submitting" @click="handleStart">
        <i v-if="submitting" class="fa-solid fa-spinner fa-spin"></i>
        <i v-else class="fa-solid fa-play"></i>
        {{ UI_RENDER_START }}
      </button>
      <button class="rq-btn" :disabled="cleaning" @click="handleCleanup" title="删除未引用素材与旧渲染产物">
        <i :class="cleaning ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-broom'"></i>
        {{ UI_CLEANUP_DISK }}
      </button>
      <button class="rq-btn" @click="refresh">
        <i class="fa-solid fa-rotate"></i>
      </button>
    </div>
    <p v-if="actionError" class="rq-error">{{ UI_RENDER_SUBMIT_FAILED }}：{{ actionError }}</p>
    <p v-if="cleanupMsg" class="rq-cleanup">{{ cleanupMsg }}</p>

    <!-- 列表 -->
    <div v-if="renders.length" class="rq-list">
      <div v-for="render in renders" :key="render.render_id" class="rq-item" :class="`rq-item--${render.state}`">
        <div class="rq-item-head">
          <span class="rq-state">
            <i :class="stateIcon(render.state)"></i>
            {{ stateLabel(render.state) }}
          </span>
          <span class="rq-time">{{ formatTime(render.created_at) }}</span>
        </div>

        <div class="rq-progress">
          <div class="rq-progress-bar" :style="{ width: `${Math.round(render.progress * 100)}%` }"></div>
        </div>
        <div class="rq-meta">
          <span class="rq-stage">{{ stageText(render) }}</span>
          <span class="rq-pct">{{ Math.round(render.progress * 100) }}%</span>
        </div>

        <div class="rq-actions">
          <button
            v-if="isActive(render.state)"
            class="rq-btn rq-btn--danger"
            @click="handleCancel(render)"
          >
            <i class="fa-solid fa-stop"></i>
            {{ UI_RENDER_CANCEL }}
          </button>
          <template v-if="render.state === 'completed'">
            <button class="rq-btn" @click="handlePreview(render)">
              <i class="fa-solid fa-play"></i>
              {{ UI_RENDER_PREVIEW }}
            </button>
            <a class="rq-btn" :href="composerRenderFileUrl(render.render_id, true)" target="_blank" rel="noopener">
              <i class="fa-solid fa-download"></i>
              {{ UI_RENDER_DOWNLOAD }}
            </a>
          </template>
        </div>

        <details v-if="render.state === 'failed' && render.error" class="rq-detail">
          <summary>{{ UI_RENDER_ERROR }}</summary>
          <pre>{{ render.error }}</pre>
        </details>
      </div>
    </div>
    <div v-else class="rq-empty">
      <i class="fa-solid fa-film"></i>
      <p>{{ UI_RENDER_NONE }}</p>
    </div>
  </div>
</template>

<style scoped>
.rq-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rq-warn {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  background: rgba(245, 165, 36, 0.08);
  border: 1px solid rgba(245, 165, 36, 0.25);
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--warning);
}
.rq-warn strong { font-weight: 600; }

.rq-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rq-title { flex: 1; font-size: 13px; color: var(--text-secondary); }

.rq-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.rq-btn:hover { color: var(--text-primary); background: var(--bg-hover); border-color: var(--text-dim); }
.rq-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.rq-btn--primary { color: var(--accent); border-color: var(--accent); background: var(--accent-bg); }
.rq-btn--primary:hover { color: var(--white); background: var(--accent); }
.rq-btn--danger:hover { color: var(--error); border-color: var(--error); background: var(--error-bg-hover); }

.rq-error { margin: 0; font-size: 12px; color: var(--error); white-space: pre-wrap; }
.rq-cleanup { margin: 0; font-size: 12px; color: var(--success); }

.rq-list { display: flex; flex-direction: column; gap: 8px; }

.rq-item {
  padding: 9px 11px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rq-item--completed { border-color: rgba(74, 222, 128, 0.35); }
.rq-item--failed { border-color: rgba(248, 113, 113, 0.35); }
.rq-item--canceled { opacity: 0.7; }

.rq-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.rq-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.rq-item--completed .rq-state { color: var(--success); }
.rq-item--failed .rq-state { color: var(--error); }
.rq-item--preparing .rq-state,
.rq-item--rendering .rq-state,
.rq-item--muxing .rq-state { color: var(--warning); }

.rq-time { font-size: 11px; color: var(--text-dim); }

.rq-progress {
  height: 5px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}
.rq-progress-bar {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.4s ease;
}
.rq-item--completed .rq-progress-bar { background: var(--success); }
.rq-item--failed .rq-progress-bar { background: var(--error); }

.rq-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-dim);
}

.rq-actions { display: flex; gap: 6px; flex-wrap: wrap; }

.rq-detail summary {
  font-size: 11px;
  color: var(--text-dim);
  cursor: pointer;
}
.rq-detail pre {
  margin: 6px 0 0;
  padding: 8px;
  max-height: 140px;
  overflow: auto;
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}

.rq-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--text-dim);
  font-size: 13px;
}
.rq-empty i { font-size: 28px; }
.rq-empty p { margin: 0; }
</style>
