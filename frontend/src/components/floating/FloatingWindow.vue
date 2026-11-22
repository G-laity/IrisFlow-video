<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from "vue";
import { UI_CLOSE, UI_PIN, UI_UNPIN } from "../../constants";
import { register, unregister, focusWindow, setVisible } from "../../composables/windowZIndex";

type Position = "center" | "top" | "bottom" | "left" | "right"
  | "top-left" | "top-right" | "bottom-left" | "bottom-right";

const GAP = "16px";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    width?: string;
    title?: string;
    icon?: string;
    position?: Position;
  }>(),
  {
    modelValue: false,
    width: "420px",
    title: "",
    icon: "",
    position: "center",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  close: [];
}>();

// ── z-index / 置顶 ────────────────────────────

const myKey = Symbol();
const PINNED_Z = 9999;
const pinned = ref(false);
const zIndex = ref(200);

function setZ(z: number) {
  if (!pinned.value) zIndex.value = z;
}

function bringToFront() {
  if (pinned.value) return;
  focusWindow(myKey);
}

function togglePin() {
  pinned.value = !pinned.value;
  if (pinned.value) {
    zIndex.value = PINNED_Z;
  } else {
    focusWindow(myKey);
  }
}

// ── 初始位置 ──────────────────────────────────

const posStyle = computed<Record<string, string>>(() => {
  const s: Record<string, string> = {};
  switch (props.position) {
    case "center":      s.left = "50%"; s.top = "50%"; s.transform = "translate(-50%, -50%)"; break;
    case "top":         s.left = "50%"; s.top = GAP;   s.transform = "translateX(-50%)"; break;
    case "bottom":      s.left = "50%"; s.bottom = GAP; s.transform = "translateX(-50%)"; break;
    case "left":        s.left = GAP;   s.top = "50%"; s.transform = "translateY(-50%)"; break;
    case "right":       s.right = GAP;  s.top = "50%"; s.transform = "translateY(-50%)"; break;
    case "top-left":    s.left = GAP;   s.top = GAP;   break;
    case "top-right":   s.right = GAP;  s.top = GAP;   break;
    case "bottom-left": s.left = GAP;   s.bottom = GAP; break;
    case "bottom-right":s.right = GAP;  s.bottom = GAP; break;
  }
  return s;
});

function applyPosStyle(el: HTMLElement) {
  const s = posStyle.value;
  el.style.left = s.left ?? "";
  el.style.top = s.top ?? "";
  el.style.right = s.right ?? "";
  el.style.bottom = s.bottom ?? "";
  el.style.transform = s.transform ?? "";
}

// ── 显示/隐藏 ──────────────────────────────────

const show = ref(false);
const panelEl = ref<HTMLElement | null>(null);

function close() {
  emit("update:modelValue", false);
  emit("close");
}

watch(
  () => props.modelValue,
  async (val) => {
    setVisible(myKey, val);
    if (val) {
      bringToFront();
      show.value = true;
      await nextTick();
      clampToViewport();
    } else {
      show.value = false;
    }
  },
);

// ── 初始定位（onMounted 时 panelEl 已就绪）────

onMounted(() => {
  register(myKey, setZ, close);
  if (props.modelValue) setVisible(myKey, true);
  applyPosStyle(panelEl.value!);
  if (props.modelValue) {
    show.value = true;
    bringToFront();
  }
  window.addEventListener("resize", clampToViewport);
  document.addEventListener("mousedown", onDocMouseDown);
});

onUnmounted(() => {
  unregister(myKey);
  window.removeEventListener("resize", clampToViewport);
  document.removeEventListener("mousedown", onDocMouseDown);
  document.removeEventListener("mousemove", onMouseMove);
  document.removeEventListener("mouseup", onMouseUp);
});

// ── 聚焦置顶（document mousedown + contains）───

function onDocMouseDown(e: MouseEvent) {
  if (show.value && panelEl.value?.contains(e.target as HTMLElement)) {
    bringToFront();
  }
}

// ── 拖动 ───────────────────────────────────────

const dragging = ref(false);

interface DragState {
  startMouseX: number;
  startMouseY: number;
  startPanelX: number;
  startPanelY: number;
}

let _drag: DragState | null = null;

function onHeaderMouseDown(e: MouseEvent) {
  if (!panelEl.value) return;
  const rect = panelEl.value.getBoundingClientRect();
  dragging.value = true;
  // 立即锁定像素位置，避免 CSS transition 动画化跳变
  panelEl.value.style.left = `${rect.left}px`;
  panelEl.value.style.top = `${rect.top}px`;
  panelEl.value.style.right = "";
  panelEl.value.style.bottom = "";
  panelEl.value.style.transform = "none";
  _drag = {
    startMouseX: e.clientX,
    startMouseY: e.clientY,
    startPanelX: rect.left,
    startPanelY: rect.top,
  };
  document.addEventListener("mousemove", onMouseMove);
  document.addEventListener("mouseup", onMouseUp);
}

function onMouseMove(e: MouseEvent) {
  if (!_drag || !panelEl.value) return;
  const dx = e.clientX - _drag.startMouseX;
  const dy = e.clientY - _drag.startMouseY;
  panelEl.value.style.left = `${_drag.startPanelX + dx}px`;
  panelEl.value.style.top = `${_drag.startPanelY + dy}px`;
}

function onMouseUp() {
  _drag = null;
  dragging.value = false;
  document.removeEventListener("mousemove", onMouseMove);
  document.removeEventListener("mouseup", onMouseUp);
}

// ── 视口边界约束（窗口 resize 后拉回可见区域）─────

const MIN_VISIBLE = 60; // 至少露出 60px，足够拖拽

function clampToViewport() {
  if (!panelEl.value || !show.value) return;
  const rect = panelEl.value.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let left = rect.left;
  let top = rect.top;

  if (left > vw - MIN_VISIBLE) left = vw - MIN_VISIBLE;
  if (left + rect.width < MIN_VISIBLE) left = MIN_VISIBLE - rect.width;
  if (top > vh - MIN_VISIBLE) top = vh - MIN_VISIBLE;
  if (top + rect.height < MIN_VISIBLE) top = MIN_VISIBLE - rect.height;

  if (left !== rect.left || top !== rect.top) {
    panelEl.value.style.left = `${left}px`;
    panelEl.value.style.top = `${top}px`;
    panelEl.value.style.right = "";
    panelEl.value.style.bottom = "";
    panelEl.value.style.transform = "none";
  }
}

// ── 中键关闭 ────────────────────────────────
</script>

<template>
  <Teleport to="body">
    <div
      ref="panelEl"
      class="fw-panel"
      role="dialog"
      aria-modal="true"
      :aria-label="title || undefined"
      :class="{ 'fw-panel--show': show, 'fw-panel--pinned': pinned, 'fw-panel--dragging': dragging }"
      :style="{ width, zIndex }"
    >
      <!-- 头部（拖动手柄） -->
      <div
        class="fw-header"
        @mousedown="onHeaderMouseDown"
        @mousedown.middle.prevent="close"
      >
        <slot name="header">
          <span class="fw-title">
            <i v-if="icon" :class="[icon, 'fw-title-icon']" />
            {{ title }}
          </span>
        </slot>
        <div class="fw-actions">
          <slot name="actions" />
          <button
            class="btn-icon fw-pin-btn"
            :class="{ on: pinned }"
            @click.stop="togglePin"
            :title="pinned ? UI_UNPIN : UI_PIN"
            :aria-label="pinned ? UI_UNPIN : UI_PIN"
          >
            <i class="fa-solid fa-thumbtack" />
          </button>
          <button class="btn-icon fw-close-btn" @click.stop="close" :title="UI_CLOSE" :aria-label="UI_CLOSE">
            <i class="fa-solid fa-xmark" />
          </button>
        </div>
      </div>

      <!-- 主体 -->
      <div class="fw-body">
        <slot />
      </div>

      <!-- 底部（可选） -->
      <div v-if="$slots.footer" class="fw-footer">
        <slot name="footer" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════
   浮窗面板
   ═══════════════════════════════════════════════════ */

.fw-panel {
  --fw-shadow: var(--shadow-md);
  --fw-glow: 0 0 12px var(--accent-strong);

  position: fixed;
  max-height: 80vh;
  /* 液态玻璃：半透明磨砂 + 背景折射（渐进增强）+ 流动高光 */
  background: var(--bg-secondary);
  background: var(--glass-bg);
  backdrop-filter: blur(22px) saturate(1.75) brightness(1.04);
  /* 支持 url() backdrop 的浏览器叠加 SVG 折射；不支持的会忽略整条声明，保留上一行 */
  backdrop-filter: blur(18px) saturate(1.75) brightness(1.04) url(#liquid-glass-refraction);
  -webkit-backdrop-filter: blur(22px) saturate(1.75) brightness(1.04);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow:
    var(--fw-shadow),
    inset 0 1px 0 var(--glass-highlight),
    inset 0 -1px 0 rgba(255, 255, 255, 0.05);
  isolation: isolate;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
  /* 独立 transform 属性：与定位用 inline transform 叠加，不冲突 */
  translate: 0 8px;
  scale: 0.98;
  transition: opacity 0.2s ease, translate 0.2s ease, scale 0.2s ease;

  /* 状态 */
  &.fw-panel--show { opacity: 1; pointer-events: auto; translate: 0 0; scale: 1; }
  &.fw-panel--pinned { border-color: var(--accent); box-shadow: var(--fw-shadow), var(--fw-glow), inset 0 1px 0 var(--glass-highlight), inset 0 -1px 0 rgba(255, 255, 255, 0.05); }
  &.fw-panel--dragging { transition: none; }
}

/* 液态高光：缓慢漂移的环境光 */
.fw-panel::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(120% 90% at 15% -10%, var(--glass-sheen-strong), transparent 46%),
    radial-gradient(90% 70% at 85% 110%, var(--glass-sheen), transparent 52%);
  mix-blend-mode: screen;
  opacity: 0.9;
  animation: liquid-glass-flow 18s ease-in-out infinite alternate;
}

/* 扫过表面的镜面反光 */
.fw-panel::after {
  content: "";
  position: absolute;
  top: -60%;
  bottom: -60%;
  left: -40%;
  right: -40%;
  z-index: 0;
  pointer-events: none;
  background: linear-gradient(
    115deg,
    transparent 40%,
    var(--glass-sheen) 48%,
    transparent 56%
  );
  mix-blend-mode: screen;
  opacity: 0;
  animation: liquid-glass-sheen 12s ease-in-out infinite;
}

/* 内容保持在玻璃高光之上 */
.fw-panel > * {
  position: relative;
  z-index: 1;
}

@keyframes liquid-glass-flow {
  from { transform: translate3d(-1.5%, -1%, 0) scale(1.02); }
  to   { transform: translate3d(1.5%, 1.5%, 0) scale(1.05); }
}

@keyframes liquid-glass-sheen {
  0%   { transform: translateX(-45%) rotate(0.001deg); opacity: 0; }
  8%   { opacity: 0.55; }
  55%  { transform: translateX(45%) rotate(0.001deg); opacity: 0; }
  100% { transform: translateX(45%) rotate(0.001deg); opacity: 0; }
}

/* 不支持 backdrop-filter 的浏览器回退为实色，避免半透明看不清 */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .fw-panel {
    background: var(--bg-secondary);
  }
}

/* ═══════════════════════════════════════════════════
   头部
   ═══════════════════════════════════════════════════ */

.fw-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px 8px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  cursor: grab;
  user-select: none;

  &:active { cursor: grabbing; }
}

.fw-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.fw-title-icon {
  font-size: 14px;
  color: var(--accent);
}

/* ═══════════════════════════════════════════════════
   头部操作按钮
   ═══════════════════════════════════════════════════ */

.fw-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* 置顶 — 主题色 */
.fw-pin-btn {
  &.on {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-bg);
  }
  &:hover {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-bg);
  }
  &:active {
    color: var(--white);
    background: var(--accent);
    border-color: var(--accent);
  }
}

/* 关闭 — 红色系 */
.fw-close-btn {
  &:hover {
    color: var(--error);
    border-color: var(--error);
    background: var(--error-bg-hover);
  }
  &:active {
    color: var(--white);
    background: var(--error);
    border-color: var(--error);
  }
}

/* ═══════════════════════════════════════════════════
   主体 & 底部
   ═══════════════════════════════════════════════════ */

.fw-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.fw-footer {
  padding: 10px 14px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

</style>
