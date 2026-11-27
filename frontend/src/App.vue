<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, provide } from "vue";
import { useRoute } from "vue-router";
import ConversationList from "./components/floating/ConversationList.vue";
import ChatPanel from "./components/ChatPanel.vue";
import WorkflowDetail from "./components/floating/WorkflowDetail.vue";
import MediaPreview from "./components/floating/MediaPreview.vue";
import SettingsPanel from "./components/floating/SettingsPanel.vue";
import ComposerPanel from "./components/floating/ComposerPanel.vue";
import GlassFilters from "./components/GlassFilters.vue";
import { getLLMConfig, ping, getServerUrl, setServerUrl } from "./api/client";
import { HEARTBEAT_INTERVAL, TOOL_REFRESH_INTERVAL, WF_THINK, WF_TOOL_CALL, WF_TOOL_RESULT, UI_COMPOSER, UI_CONNECTION_LOST, UI_AUTO_RECOVER, UI_MODIFY_SERVER_URL, UI_SESSION_LIST, UI_SETTINGS } from "./constants";
import { ON_CONNECTION_LOST_KEY, REFRESH_CONVERSATION_LIST_KEY, REMOVE_SESSION_CACHE_KEY } from "./composables/injectionKeys";
import { discoverTools } from "./composables/toolMetadata";
import { preloadMarkdown } from "./utils/markdown";
import { composerToast, clearComposerToast } from "./composables/useComposer";
import type { WorkflowEntry, PreviewPayload } from "./types/api";
import type { MorphRect } from "./utils/fluidMorph";

function onServerUrlInput(e: Event) {
  setServerUrl((e.target as HTMLInputElement).value);
}

const route = useRoute();
const isLanding = computed(() => route.name === "new-chat");

const model = ref("");
const showSettings = ref(false);
const showComposer = ref(false);
const chatPanelRef = ref<InstanceType<typeof ChatPanel> | null>(null);
const conversationListRef = ref<InstanceType<typeof ConversationList> | null>(null);

// ── 浮岛按钮 → 面板流体变形 ──────────────────────

const settingsBtnEl = ref<HTMLButtonElement | null>(null);
const settingsOrigin = ref<MorphRect | null>(null);
const composerBtnEl = ref<HTMLButtonElement | null>(null);
const composerOrigin = ref<MorphRect | null>(null);
const conversationBtnEl = ref<HTMLButtonElement | null>(null);
const conversationOrigin = ref<MorphRect | null>(null);

function captureRect(el: HTMLElement | null): MorphRect | null {
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return {
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
  };
}

function openSettings() {
  settingsOrigin.value = captureRect(settingsBtnEl.value);
  showSettings.value = true;
}

function openComposer() {
  composerOrigin.value = captureRect(composerBtnEl.value);
  showComposer.value = true;
}

// ── 持久浮窗（v-model 驱动，纯内存）───────────

const showConversationList = ref(route.name !== "new-chat");

function openConversations() {
  conversationOrigin.value = captureRect(conversationBtnEl.value);
  showConversationList.value = true;
}

// 开始页保持干净；进入对话时恢复会话列表
watch(
  () => route.name,
  (name, prev) => {
    if (name === "new-chat") showConversationList.value = false;
    else if (name === "chat" && prev === "new-chat") showConversationList.value = true;
  },
);

// ── 动态窗管理体系 ────────────────────────────
// 点击即创建，关闭即销毁。同类可并行多开。

type PanelType = 'tool-call' | 'tool-result' | 'think' | 'media';

interface PanelWindow {
  id: number;
  type: PanelType;
  visible: boolean;
  data: WorkflowEntry | PreviewPayload;
}

let _nextPanelId = 0;
const panels = ref<PanelWindow[]>([]);

function createPanel(type: PanelType, data: WorkflowEntry | PreviewPayload) {
  panels.value.push({ id: ++_nextPanelId, type, visible: true, data });
}

function closePanel(id: number) {
  const p = panels.value.find(p => p.id === id);
  if (!p) return;
  p.visible = false;  // 触发隐藏动画
  setTimeout(() => {
    panels.value = panels.value.filter(p => p.id !== id);
  }, 250);
}

function toPanelType(entry: WorkflowEntry): PanelType {
  if (entry.type === WF_TOOL_CALL) return 'tool-call';
  if (entry.type === WF_TOOL_RESULT) return 'tool-result';
  return 'think';
}

function onSelectEntry(entry: WorkflowEntry | null) {
  if (entry) createPanel(toPanelType(entry), entry);
}

function onPreview(payload: PreviewPayload) {
  createPanel('media', payload);
}

// ── 模板内类型窄化辅助 ──────────────────────────

function wfEntry(data: WorkflowEntry | PreviewPayload): WorkflowEntry {
  return data as WorkflowEntry;
}
function mpPayload(data: WorkflowEntry | PreviewPayload): PreviewPayload {
  return data as PreviewPayload;
}

// ── 断联占屏 + 心跳（3s 周期：失败 → 占屏，恢复 → 刷新）──

const connectionLost = ref(false);
let _timer: ReturnType<typeof setInterval> | null = null;
let _toolTimer: ReturnType<typeof setInterval> | null = null;

function onConnectionLost() {
  connectionLost.value = true;
}

async function heartbeatTick() {
  try {
    await ping();
    if (connectionLost.value) window.location.reload();
  } catch {
    onConnectionLost();
  }
}

function startHeartbeat() {
  if (_timer) clearInterval(_timer);
  heartbeatTick();  // 启动时立即检测一次
  _timer = setInterval(heartbeatTick, HEARTBEAT_INTERVAL);
}

// ── 跨组件通信 ────────────────────────────────────

provide(REMOVE_SESSION_CACHE_KEY, (id: string) => {
  chatPanelRef.value?.removeSession(id);
});
provide(REFRESH_CONVERSATION_LIST_KEY, () => {
  conversationListRef.value?.refresh();
});
provide(ON_CONNECTION_LOST_KEY, onConnectionLost);

// ── 初始化 ─────────────────────────────────────────

getLLMConfig().then(cfg => { model.value = cfg.default_model || ""; }).catch(() => { model.value = ""; });

onMounted(() => {
  startHeartbeat();
  // 后台定期刷新 MCP 工具列表（覆盖健康检查自动重连等非手动触发场景）
  _toolTimer = setInterval(discoverTools, TOOL_REFRESH_INTERVAL);
  // 空闲预加载 Markdown 重依赖（首屏不阻塞）
  setTimeout(preloadMarkdown, 1200);
  // 会话列表默认展开；先记下隐藏按钮的矩形，首次关闭也能收成胶囊
  conversationOrigin.value = captureRect(conversationBtnEl.value);
});

onUnmounted(() => {
  if (_timer) clearInterval(_timer);
  if (_toolTimer) clearInterval(_toolTimer);
});

function handleUpdateSettings(cfg: { model: string }) {
  model.value = cfg.model;
}

</script>

<template>
  <!-- 全局玻璃滤镜定义：透镜位移图 + 边缘 mask + RGB 色散 -->
  <GlassFilters />

  <!-- 环境光：给玻璃边缘提供可折射的结构（静态，不抢文字） -->
  <div class="app-ambient" aria-hidden="true"></div>

  <div class="app-layout">
    <main class="main-area">
      <ChatPanel
        ref="chatPanelRef"
        :model="model"
        @select-entry="onSelectEntry"
        @preview="onPreview"
        @open-conversations="openConversations"
        @open-composer="openComposer"
        @open-settings="openSettings"
      />
    </main>

    <SettingsPanel
      v-model="showSettings"
      :morph-origin="settingsOrigin"
      @update="handleUpdateSettings"
    />
  </div>

  <!-- 合成器浮窗（素材库 M1；项目/时间轴/渲染随 M2/M3 开放） -->
  <ComposerPanel
    v-model="showComposer"
    :morph-origin="composerOrigin"
    @preview="onPreview"
  />

  <!-- 会话浮岛（持久：关闭仅隐藏不销毁，默认显示） -->
  <ConversationList
    ref="conversationListRef"
    v-model="showConversationList"
    :morph-origin="conversationOrigin"
  />

  <!-- 动态窗（点击即创建，可并行多开） -->
  <template v-for="panel in panels" :key="panel.id">
    <WorkflowDetail
      v-if="panel.type === 'tool-call' || panel.type === 'tool-result' || panel.type === 'think'"
      v-model="panel.visible"
      :entry="wfEntry(panel.data)"
      @close="closePanel(panel.id)"
    />
    <MediaPreview
      v-else-if="panel.type === 'media'"
      v-model="panel.visible"
      :payload="mpPayload(panel.data)"
      @close="closePanel(panel.id)"
    />
  </template>

  <!-- 会话列表按钮（左上角，胶囊 → 流体展开为面板） -->
  <button
    v-if="!isLanding"
    ref="conversationBtnEl"
    class="floating-toggle floating-toggle--tl floating-toggle--capsule"
    :class="{ 'is-morphed': showConversationList }"
    @click="openConversations"
    :title="UI_SESSION_LIST"
    :aria-label="UI_SESSION_LIST"
    :aria-expanded="showConversationList"
    :tabindex="showConversationList ? -1 : undefined"
    aria-haspopup="dialog"
  >
    <i class="fa-solid fa-bars"></i>
  </button>

  <!-- 合成器按钮（右上角，设置按钮下方，胶囊 → 流体展开为面板） -->
  <button
    v-if="!isLanding"
    ref="composerBtnEl"
    class="floating-toggle floating-toggle--tr2 floating-toggle--capsule"
    :class="{ 'is-morphed': showComposer || showSettings }"
    @click="openComposer"
    :title="UI_COMPOSER"
    :aria-label="UI_COMPOSER"
    :aria-expanded="showComposer"
    :tabindex="showComposer ? -1 : undefined"
    aria-haspopup="dialog"
  >
    <i class="fa-solid fa-clapperboard"></i>
  </button>

  <!-- 设置按钮（右上角，胶囊 → 流体展开为面板） -->
  <button
    v-if="!isLanding"
    ref="settingsBtnEl"
    class="floating-toggle floating-toggle--tr floating-toggle--capsule"
    :class="{ 'is-morphed': showSettings }"
    @click="openSettings"
    :title="UI_SETTINGS"
    :aria-label="UI_SETTINGS"
    :aria-expanded="showSettings"
    :tabindex="showSettings ? -1 : undefined"
    aria-haspopup="dialog"
  >
    <i class="fa-solid fa-gear"></i>
  </button>

  <!-- 渲染完成 toast（点击打开合成器） -->
  <Transition name="app-toast">
    <button
      v-if="composerToast"
      class="app-toast"
      role="status"
      aria-live="polite"
      @click="showComposer = true; clearComposerToast()"
    >
      <i class="fa-solid fa-circle-check"></i>
      {{ composerToast }}
    </button>
  </Transition>

  <!-- 断联占屏：心跳每 3s 自动重试，恢复后自动刷新 -->
  <div v-if="connectionLost" class="conn-lost-overlay">
    <div class="conn-lost-card">
      <i class="fa-solid fa-plug-circle-xmark conn-lost-icon"></i>
      <p class="conn-lost-msg">{{ UI_CONNECTION_LOST }}</p>
      <p class="conn-lost-hint">{{ UI_AUTO_RECOVER }}</p>
      <p class="conn-lost-hint">{{ UI_MODIFY_SERVER_URL }}</p>
      <input
        class="conn-lost-input"
        :value="getServerUrl()"
        placeholder="http://localhost:8000"
        @input="onServerUrlInput"
      />
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════
   布局
   ═══════════════════════════════════════════════════ */

.app-ambient {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  background:
    radial-gradient(58% 54% at 73% 16%, rgba(84, 126, 255, 0.20), transparent 66%),
    radial-gradient(52% 46% at 22% 80%, rgba(255, 84, 168, 0.14), transparent 66%),
    radial-gradient(40% 38% at 86% 82%, rgba(52, 210, 190, 0.10), transparent 64%),
    var(--bg-primary);
}

.app-ambient::before {
  content: "";
  position: absolute;
  inset: -18% -12%;
  background: linear-gradient(112deg, transparent 37%, rgba(128, 178, 255, 0.14) 48%, transparent 58%);
  filter: blur(32px);
  transform: rotate(-9deg);
}

.app-ambient::after {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 52px 52px;
  mask-image: radial-gradient(110% 100% at 50% 46%, #000 36%, transparent 96%);
  -webkit-mask-image: radial-gradient(110% 100% at 50% 46%, #000 36%, transparent 96%);
}

:root[data-theme="light"] .app-ambient {
  background:
    radial-gradient(58% 54% at 73% 16%, rgba(75, 91, 214, 0.12), transparent 66%),
    radial-gradient(52% 46% at 22% 80%, rgba(214, 75, 150, 0.09), transparent 66%),
    radial-gradient(40% 38% at 86% 82%, rgba(20, 160, 140, 0.08), transparent 64%),
    var(--bg-primary);
}

:root[data-theme="light"] .app-ambient::before {
  background: linear-gradient(112deg, transparent 37%, rgba(120, 150, 255, 0.16) 48%, transparent 58%);
}

:root[data-theme="light"] .app-ambient::after {
  background-image:
    linear-gradient(rgba(24, 35, 70, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(24, 35, 70, 0.055) 1px, transparent 1px);
}

.app-layout {
  position: relative;
  z-index: 1;
  display: flex;
  height: 100%;
  overflow-x: hidden;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}

/* ═══════════════════════════════════════════════════
   浮动切换按钮
   ═══════════════════════════════════════════════════ */

.floating-toggle {
  position: fixed;
  z-index: 150;
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  font-size: 14px;
  cursor: pointer;
  color: var(--text-dim);
  background: transparent;
  border: 1px solid var(--border);
  transition: color 0.15s, background 0.15s, border-color 0.15s;

  &:hover {
    color: var(--text-secondary);
    background: var(--bg-hover);
    border-color: var(--text-dim);
  }
  &:active {
    color: var(--text-primary);
    background: var(--bg-tertiary);
    border-color: var(--accent);
  }

  &.floating-toggle--tl { top: 12px; left: 12px; }
  &.floating-toggle--bl { bottom: 12px; left: 12px; }
  &.floating-toggle--tr { top: 12px; right: 12px; }
  &.floating-toggle--tr2 { top: 50px; right: 12px; }
}

/* ── 统一胶囊按钮：浮窗的“折叠态” ─────────────── */

.floating-toggle--capsule {
  width: 56px;
  height: 32px;
  min-width: 56px;
  padding: 0;
  gap: 0;
  border-radius: 999px;
  /* Tint 玻璃：只叠色不叠模糊 */
  background: var(--bg-secondary);
  background: var(--glass-bg);
  border-color: var(--glass-border);
  box-shadow:
    inset 0 1px 0 var(--glass-highlight),
    inset 0 0 0 1px var(--glass-rim-inner),
    inset 0 -1px 0 var(--glass-tint);
  /* 收起时延迟现身：面板缩回按钮位置的过程中再淡入，避免透过玻璃看见重影 */
  transition:
    color 0.15s,
    background 0.15s,
    border-color 0.15s,
    box-shadow 0.2s,
    opacity 0.1s ease 0.16s,
    transform 0.18s ease 0.16s;
}

.floating-toggle--capsule i {
  font-size: 13px;
}

.floating-toggle--capsule:hover {
  background: var(--glass-bg);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow:
    inset 0 1px 0 var(--glass-highlight),
    0 0 14px var(--accent-strong);
}

/* 打开时让位给从同一矩形长出的面板；关闭时面板最后正好盖住按钮 */
.floating-toggle--capsule.is-morphed {
  opacity: 0;
  pointer-events: none;
  transform: scale(0.94);
  /* 展开时立即让位，不等收起延迟 */
  transition:
    color 0.15s,
    background 0.15s,
    border-color 0.15s,
    box-shadow 0.2s,
    opacity 0.12s ease,
    transform 0.18s ease;
}

@media (prefers-reduced-motion: reduce) {
  .floating-toggle--capsule { transition-delay: 0s !important; }
}

/* ═══════════════════════════════════════════════════
   断联占屏
   ═══════════════════════════════════════════════════ */

.conn-lost-overlay {
  position: fixed; inset: 0; z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-primary) 92%, transparent);
  backdrop-filter: blur(4px);
}

.conn-lost-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.conn-lost-icon {
  font-size: 56px;
  color: var(--error);
  margin-bottom: 20px;
}

.conn-lost-msg {
  font-size: 18px; font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.conn-lost-hint {
  font-size: 14px;
  color: var(--text-dim);
}

.conn-lost-input {
  width: 280px;
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-mono);
  text-align: center;
  outline: none;
}
.conn-lost-input:focus { border-color: var(--accent); }

/* ═══════════════════════════════════════════════════
   渲染完成 toast
   ═══════════════════════════════════════════════════ */

.app-toast {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 9000;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 22px;
  border: 1px solid var(--accent);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  box-shadow: var(--shadow-md), 0 0 16px var(--accent-strong);
}
.app-toast i { color: var(--success); }

.app-toast-enter-active,
.app-toast-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.app-toast-enter-from,
.app-toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }
</style>
