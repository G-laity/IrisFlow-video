<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick, useId } from "vue";
import { UI_CLOSE, UI_PIN, UI_UNPIN } from "../../constants";
import { register, unregister, focusWindow, setVisible } from "../../composables/windowZIndex";
import {
  buildMorphFrames,
  buildMorphContentFrames,
  panelRadiusOf,
  prefersReducedMotion,
  MORPH_OPEN_MS,
  MORPH_CLOSE_MS,
  type MorphRect,
} from "../../utils/fluidMorph";

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
    /** 流体变形起点（通常是入口按钮的视口矩形）。为空时使用默认开合动画。 */
    morphFrom?: MorphRect | null;
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
const contentEl = ref<HTMLElement | null>(null);

function close() {
  emit("update:modelValue", false);
  emit("close");
}

// ── 流体变形（胶囊按钮 → 面板）─────────────────

const morphing = ref(false);

// ── 透镜强度：每个浮窗克隆一份 #glass-lens，用 scale 逐帧淡入/淡出 ──
// 不用 opacity 做交叉淡入：Chromium 在 opacity < 1 时会跳过 backdrop-filter，
// 反而让玻璃在过渡期间消失。

const LENS_FADE_IN_MS = 220;
const LENS_FADE_OUT_MS = 180;
const lensFilterId = `glass-lens-fw-${useId()}`;
const lensFilterUrl = ref("url(#glass-lens)");

let _lensClone: SVGFilterElement | null = null;
let _lensMaps: Element[] = [];
let _lensBaseScales: number[] = [];
let _lensFactor = 0;
let _lensRaf = 0;

function setupLensFilter() {
  if (_lensMaps.length) return;
  const src = document.getElementById("glass-lens");
  if (!src) return;
  const clone = src.cloneNode(true) as SVGFilterElement;
  clone.id = lensFilterId;
  src.parentElement?.append(clone);
  _lensClone = clone;
  _lensMaps = [...clone.querySelectorAll("feDisplacementMap")];
  _lensBaseScales = _lensMaps.map((el) => Number(el.getAttribute("scale")));
  lensFilterUrl.value = `url(#${lensFilterId})`;
  setLensFactor(_lensFactor);
}

function setLensFactor(factor: number) {
  _lensFactor = factor;
  for (let i = 0; i < _lensMaps.length; i++) {
    _lensMaps[i].setAttribute("scale", String(_lensBaseScales[i] * factor));
  }
}

function cancelLensRamp() {
  if (_lensRaf) cancelAnimationFrame(_lensRaf);
  _lensRaf = 0;
}

/** 把透镜位移强度从当前值缓动到 to（0=纯模糊，1=完整透镜） */
function rampLens(to: number, duration: number) {
  cancelLensRamp();
  if (!_lensMaps.length || prefersReducedMotion()) {
    setLensFactor(to);
    return;
  }
  const from = _lensFactor;
  const started = performance.now();
  const easeOutCubic = (x: number) => 1 - Math.pow(1 - x, 3);
  const tick = (now: number) => {
    // rAF 时间戳可能略早于 started，钳到 0 避免第一帧出现负位移
    const p = Math.min(1, Math.max(0, (now - started) / duration));
    setLensFactor(from + (to - from) * easeOutCubic(p));
    _lensRaf = p < 1 ? requestAnimationFrame(tick) : 0;
  };
  _lensRaf = requestAnimationFrame(tick);
}
let _morphAnims: Animation[] = [];
let _morphToken = 0;
let _contentFrozen = false;
let _contentFrame: { left: number; top: number; borderLeft: number; borderTop: number } | null = null;
/** 居中 / 偏置定位用的 inline transform，变形期间临时清掉，结束后恢复 */
let _savedTransform: string | null = null;

function prepareMorphTransform() {
  const el = panelEl.value;
  if (!el || _savedTransform !== null) return;
  _savedTransform = el.style.transform;
  el.style.transform = "none";
}

function restoreMorphTransform() {
  const el = panelEl.value;
  if (!el || _savedTransform === null) return;
  el.style.transform = _savedTransform;
  _savedTransform = null;
}

function canMorph(): boolean {
  return !!props.morphFrom && !prefersReducedMotion();
}

function cancelMorphAnims() {
  for (const anim of _morphAnims) {
    try { anim.cancel(); } catch { /* already finished */ }
  }
  _morphAnims = [];
}

/**
 * 把内容层冻结为「最终尺寸 + 右上角锚定」。
 * 外层尺寸/圆角变形时，卡片内容只被裁切，不会重新排版。
 * 正常状态内容层是 display:contents（与直接挂在面板下等价），
 * 冻结时切换为绝对定位的 flex 列，尺寸取面板内容盒。
 */
function freezeContent(visualLeft: number, visualTop: number): boolean {
  const content = contentEl.value;
  const panel = panelEl.value;
  if (!content || !panel) return false;
  if (_contentFrozen) return true;

  // 必须在切换为绝对定位之前读取，否则内容移出文档流会让面板高度先塌成 0
  const width = panel.clientWidth;
  const height = panel.clientHeight;
  _contentFrame = {
    left: visualLeft + panel.clientLeft,
    top: visualTop + panel.clientTop,
    borderLeft: panel.clientLeft,
    borderTop: panel.clientTop,
  };

  content.style.display = "flex";
  content.style.flexDirection = "column";
  content.style.position = "absolute";
  content.style.left = "0";
  content.style.top = "0";
  content.style.right = "auto";
  content.style.bottom = "auto";
  content.style.width = `${width}px`;
  content.style.height = `${height}px`;
  _contentFrozen = true;
  return true;
}

function unfreezeContent() {
  const content = contentEl.value;
  if (!content) {
    _contentFrozen = false;
    return;
  }
  content.style.display = "";
  content.style.flexDirection = "";
  content.style.position = "";
  content.style.top = "";
  content.style.right = "";
  content.style.left = "";
  content.style.bottom = "";
  content.style.width = "";
  content.style.height = "";
  content.style.transform = "";
  _contentFrozen = false;
  _contentFrame = null;
}

/** 内容层的透明度轨迹：展开时在尺寸到位前就露面，收起时先淡出。 */
function contentOpacityFrames(mode: "open" | "close"): Keyframe[] {
  return mode === "open"
    ? [
        { opacity: 0, offset: 0 },
        { opacity: 0, offset: 0.08 },
        { opacity: 1, offset: 0.55 },
        { opacity: 1, offset: 1 },
      ]
    : [
        { opacity: 1, offset: 0 },
        { opacity: 1, offset: 0.12 },
        { opacity: 0, offset: 0.45 },
        { opacity: 0, offset: 1 },
      ];
}

/** 清掉旧动画并恢复自然内容布局，但保留 morphing 状态。 */
function resetMorphState() {
  _morphToken++;
  cancelMorphAnims();
  unfreezeContent();
  restoreMorphTransform();
}

/** 终止变形并把面板恢复到自然布局。 */
function stopMorph() {
  resetMorphState();
  morphing.value = false;
}

/** 从入口按钮的矩形展开到面板自然尺寸。 */
async function playMorphOpen() {
  const el = panelEl.value;
  const from = props.morphFrom;
  if (!el || !from) return;

  resetMorphState();
  const token = _morphToken;

  // watcher 已在 show 之前打开 morphing（transition:none），
  // 因此这里测量到的是 show 状态下的最终几何，而不是淡入 transform 的中间值。
  morphing.value = true;
  const target = el.getBoundingClientRect();
  const radius = panelRadiusOf(el);
  // 居中 / 偏置定位会带 inline transform；变形改为直接动画 left/top，
  // 先清掉 transform，否则会叠加偏移（居中面板会飞出去）
  prepareMorphTransform();

  await nextTick();
  if (token !== _morphToken) return;

  if (!freezeContent(target.left, target.top)) {
    stopMorph();
    rampLens(1, LENS_FADE_IN_MS);
    return;
  }

  const frames = buildMorphFrames(
    from,
    { left: target.left, top: target.top, width: target.width, height: target.height },
    { mode: "open", radius },
  );
  const duration = MORPH_OPEN_MS;
  const anim = el.animate(frames, {
    duration,
    easing: "linear",
    fill: "both",
  });
  _morphAnims.push(anim);

  const contentAnim = contentEl.value?.animate(contentOpacityFrames("open"), {
    duration,
    easing: "linear",
    fill: "both",
  });
  if (contentAnim) _morphAnims.push(contentAnim);

  const contentMoveAnim = _contentFrame && contentEl.value?.animate(
    buildMorphContentFrames(frames, _contentFrame.left, _contentFrame.top, _contentFrame.borderLeft, _contentFrame.borderTop),
    { duration, easing: "linear", fill: "both" },
  );
  if (contentMoveAnim) _morphAnims.push(contentMoveAnim);

  anim.finished
    .then(() => {
      if (token !== _morphToken) return;
      unfreezeContent();
      contentAnim?.cancel();
      contentMoveAnim?.cancel();
      anim.cancel();
      restoreMorphTransform();
      morphing.value = false;
      // 形变完成后把透镜位移从 0 缓动到满强度，避免突然出现
      rampLens(1, LENS_FADE_IN_MS);
      _morphAnims = [];
    })
    .catch(() => { /* cancelled */ });
}

/** 从当前几何收回入口按钮的矩形。 */
async function playMorphClose() {
  const el = panelEl.value;
  const from = props.morphFrom;
  if (!el || !from) {
    show.value = false;
    return;
  }

  const token = ++_morphToken;

  // 先读当前（可能正处于展开动画中）的几何，再清掉旧动画
  const current = el.getBoundingClientRect();
  const radius = panelRadiusOf(el);
  cancelMorphAnims();
  morphing.value = true;

  // 内容冻结为当前（视觉）尺寸与位置；展开动画中已冻结则直接复用
  freezeContent(current.left, current.top);
  prepareMorphTransform();

  await nextTick();
  if (token !== _morphToken) return;

  const frames = buildMorphFrames(
    { left: current.left, top: current.top, width: current.width, height: current.height },
    { left: from.left, top: from.top, width: from.width, height: from.height },
    { mode: "close", radius },
  );
  const duration = MORPH_CLOSE_MS;
  const anim = el.animate(frames, {
    duration,
    easing: "linear",
    fill: "both",
  });
  _morphAnims = [anim];

  const contentAnim = contentEl.value?.animate(contentOpacityFrames("close"), {
    duration,
    easing: "linear",
    fill: "both",
  });
  if (contentAnim) _morphAnims.push(contentAnim);

  const contentMoveAnim = _contentFrame && contentEl.value?.animate(
    buildMorphContentFrames(frames, _contentFrame.left, _contentFrame.top, _contentFrame.borderLeft, _contentFrame.borderTop),
    { duration, easing: "linear", fill: "both" },
  );
  if (contentMoveAnim) _morphAnims.push(contentMoveAnim);

  try {
    await anim.finished;
  } catch {
    return; // 被新的展开 / 收起打断
  }
  if (token !== _morphToken) return;

  // 用 morphing 的 transition:none 瞬间隐藏。
  // 注意：必须在同一帧内强制提交「隐藏且无过渡」的状态，
  // 否则移除 morphing 会让浏览器从 opacity:1 + 自然尺寸重新开始过渡 → 整面板闪一下。
  show.value = false;
  await nextTick();
  if (el) {
    el.style.transition = "none";
    el.style.opacity = "0";
    void el.offsetWidth;
    el.style.transition = "";
    el.style.opacity = "";
  }
  morphing.value = false;
  unfreezeContent();
  contentAnim?.cancel();
  contentMoveAnim?.cancel();
  anim.cancel();
  restoreMorphTransform();
  _morphAnims = [];
}

watch(
  () => props.modelValue,
  async (val) => {
    setVisible(myKey, val);
    if (val) {
      bringToFront();
      const morph = canMorph();
      // 先关掉默认过渡再显示，保证测量到的是 show 的最终几何
      if (morph) {
        // 形变期间透镜强度归零（只有模糊）；结束后 playMorphOpen 再缓动到满强度
        cancelLensRamp();
        setLensFactor(0);
        morphing.value = true;
      } else {
        cancelLensRamp();
        setLensFactor(1);
      }
      show.value = true;
      await nextTick();
      clampToViewport();
      if (morph) void playMorphOpen();
    } else if (canMorph() && show.value) {
      // 收起时先把透镜强度缓动到 0，形变期间保持模糊
      rampLens(0, LENS_FADE_OUT_MS);
      void playMorphClose();
    } else {
      cancelLensRamp();
      stopMorph();
      show.value = false;
    }
  },
);

// ── 初始定位（onMounted 时 panelEl 已就绪）────

onMounted(() => {
  setupLensFilter();
  if (!_lensMaps.length) requestAnimationFrame(() => setupLensFilter());
  register(myKey, setZ, close);
  if (props.modelValue) setVisible(myKey, true);
  applyPosStyle(panelEl.value!);
  if (props.modelValue) {
    show.value = true;
    setLensFactor(1);
    bringToFront();
  }
  window.addEventListener("resize", clampToViewport);
  document.addEventListener("mousedown", onDocMouseDown);
});

onUnmounted(() => {
  stopMorph();
  cancelLensRamp();
  _lensClone?.remove();
  _lensClone = null;
  _lensMaps = [];
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
  if (morphing.value) stopMorph(); // 抓住正在变形的面板 → 立即定形
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
      class="fw-panel glass-card"
      role="dialog"
      aria-modal="true"
      :aria-label="title || undefined"
      :class="{
        'fw-panel--show': show,
        'fw-panel--pinned': pinned,
        'fw-panel--dragging': dragging,
        'fw-panel--morphing': morphing,
      }"
      :style="{ width, zIndex }"
    >
      <!-- REFRACT：独立 warp 层，backdrop 模糊 + 透镜位移；
           透镜强度由当前实例的滤镜 scale 逐帧控制，内容不在其中。 -->
      <span
        class="glass-card__warp"
        :style="{ filter: lensFilterUrl }"
        aria-hidden="true"
      ></span>

      <!-- 内容层：变形时冻结为最终尺寸并从右上角被外壳裁切，避免内容重排 -->
      <div ref="contentEl" class="fw-content glass-card__body">
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
  &.fw-panel--pinned {
    box-shadow:
      var(--fw-shadow),
      var(--fw-glow);
  }
  &.fw-panel--dragging { transition: none; }
}

/* ── 内容层：正常状态与直接挂在面板下等价，变形时由脚本冻结尺寸 ── */

.fw-content {
  display: contents;
}

/* 内容保持在玻璃层之上 */
.fw-content > .fw-header,
.fw-content > .fw-body,
.fw-content > .fw-footer {
  position: relative;
  z-index: 4;
}

/* ── 流体变形：尺寸 / 圆角由 WAAPI 逐帧驱动 ────────── */

.fw-panel.fw-panel--morphing {
  /* 关闭默认的 opacity / translate / scale 开合动画 */
  transition: none;
  /* 变形中不响应指针（避免误拖拽 / 误关闭） */
  pointer-events: none;
}

/* 变形期间 warp 的实例滤镜 scale 归零（只保留 backdrop 模糊），
   动画结束后再缓动到满强度。filter 始终保持为非 none 的 url()，
   否则 Chromium 在几何动画期间会跳过 backdrop-filter。 */

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
