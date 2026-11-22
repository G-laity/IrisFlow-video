<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { useTabIndicator } from "../composables/useTabIndicator";
import {
  FACTORY_SESSION_DEFAULTS,
  SESSION_PRESETS,
  UI_BASIC,
  UI_ADVANCED,
  UI_CLEAR,
  UI_CLICK_TO_SET,
  UI_DEFAULT,
  UI_SESSION_SETTINGS,
  UI_SYSTEM_PROMPT,
  UI_TEMPERATURE,
  UI_MAX_TOKENS,
  UI_TOP_P,
  UI_TOP_K,
  UI_PRESENCE_PENALTY,
  UI_FREQUENCY_PENALTY,
  UI_REPEAT_PENALTY,
} from "../constants";
import type { SessionSettings } from "../types/api";
import FloatingWindow from "./floating/FloatingWindow.vue";

const props = defineProps<{
  modelValue: boolean;
  settings: SessionSettings;
  defaults: SessionSettings;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  "update:settings": [value: SessionSettings];
  close: [];
}>();

const activeTab = ref("basic");
const { navEl, indicatorEl, indicatorStyle } = useTabIndicator(activeTab);

// ── 预设类型切换框（同会话列表动效）──────────────

const presetListEl = ref<HTMLElement | null>(null);
const presetFrameEl = ref<HTMLElement | null>(null);
const presetFrameStyle = ref<Record<string, string>>({ opacity: "0" });

let _presetReady = false;
let _presetTop = 0;

async function updatePresetFrame(): Promise<void> {
  await nextTick();
  const list = presetListEl.value;
  const el = presetFrameEl.value;
  if (!list || !el) return;

  const active = list.querySelector<HTMLElement>(".preset-chip.active");
  if (!active) {
    presetFrameStyle.value = { opacity: "0" };
    _presetReady = false;
    return;
  }

  const listRect = list.getBoundingClientRect();
  const rect = active.getBoundingClientRect();
  const top = rect.top - listRect.top;
  const left = rect.left - listRect.left;
  const changed = Math.abs(top - _presetTop) > 1;
  const direction = top >= _presetTop ? 1 : -1;

  presetFrameStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    opacity: "1",
  };

  if (!_presetReady) {
    el.classList.add("no-anim");
    requestAnimationFrame(() => el.classList.remove("no-anim"));
  } else if (changed) {
    el.getAnimations().forEach(a => a.cancel());
    el.animate(
      [
        { transform: "scaleY(1)", transformOrigin: direction > 0 ? "top" : "bottom" },
        { transform: "scaleY(1.06)", offset: 0.45 },
        { transform: "scaleY(1)" },
      ],
      { duration: 300, easing: "cubic-bezier(0.22, 1.12, 0.36, 1)" },
    );
  }

  _presetTop = top;
  _presetReady = true;
}

onMounted(() => {
  void updatePresetFrame();
  window.addEventListener("resize", updatePresetFrame);
});

onUnmounted(() => {
  window.removeEventListener("resize", updatePresetFrame);
});

const local = ref<SessionSettings>({ ...props.settings });

watch(() => props.settings, (v) => {
  local.value = { ...v };
}, { deep: true });

/** 应用预设：仅覆盖非 null 字段，其余保持原值 */
function applyPreset(s: SessionSettings) {
  for (const key of Object.keys(s) as (keyof SessionSettings)[]) {
    if (s[key] != null) (local.value as any)[key] = s[key];
  }
  emit("update:settings", { ...local.value });
}

/** 应用会话默认设定：全量替换（包括 null） */
function applyDefaults(s: SessionSettings) {
  local.value = { ...s };
  emit("update:settings", { ...s });
}

function applyChange() {
  emit("update:settings", { ...local.value });
}

function clearField(key: keyof SessionSettings) {
  (local.value as any)[key] = null;
  applyChange();
}

/** 点击设置：取工厂默认值（system_prompt 为 null 时用空字符串） */
function setDefault(key: keyof SessionSettings) {
  const v = (FACTORY_SESSION_DEFAULTS as any)[key];
  (local.value as any)[key] = key === "system_prompt" && v == null ? "" : v;
  applyChange();
}

function handleClose() {
  emit("update:modelValue", false);
  emit("close");
}

const activePresetId = computed(() => {
  const s = local.value;
  const keys: (keyof SessionSettings)[] = ["temperature", "top_p", "presence_penalty", "frequency_penalty", "repeat_penalty"];
  for (const p of SESSION_PRESETS) {
    let match = true;
    for (const k of keys) {
      if (p.settings[k] != null && p.settings[k] !== s[k]) { match = false; break; }
    }
    if (match) return p.id;
  }
  return null;
});

const isDefault = computed(() => {
  const s = local.value;
  const d = props.defaults;
  const keys = Object.keys(s) as (keyof SessionSettings)[];
  for (const k of keys) {
    if (s[k] !== (d as any)[k]) return false;
  }
  return true;
});

watch(
  [activePresetId, isDefault],
  () => { void updatePresetFrame(); },
  { flush: "post" },
);

// 可清除的高级字段列表
const clearableFields = [
  { key: "top_p" as const, label: UI_TOP_P, min: 0, max: 1, step: 0.05, fmt: (v: number) => v.toFixed(2) },
  { key: "top_k" as const, label: UI_TOP_K, min: 1, max: 200, step: 1, fmt: (v: number) => String(v) },
  { key: "presence_penalty" as const, label: UI_PRESENCE_PENALTY, min: -2, max: 2, step: 0.1, fmt: (v: number) => v.toFixed(2) },
  { key: "frequency_penalty" as const, label: UI_FREQUENCY_PENALTY, min: -2, max: 2, step: 0.1, fmt: (v: number) => v.toFixed(2) },
  { key: "repeat_penalty" as const, label: UI_REPEAT_PENALTY, min: 0, max: 2, step: 0.1, fmt: (v: number) => v.toFixed(2) },
];

</script>

<template>
  <FloatingWindow
    :model-value="modelValue"
    :title="UI_SESSION_SETTINGS"
    icon="fa-solid fa-sliders"
    position="bottom-right"
    width="560px"
    @update:model-value="$emit('update:modelValue', $event)"
    @close="handleClose"
  >
    <div class="settings-layout">
      <!-- 左侧标签栏 -->
      <nav ref="navEl" class="tab-nav" role="tablist">
        <span ref="indicatorEl" class="tab-indicator" :style="indicatorStyle" aria-hidden="true"></span>
        <button class="tab-btn" :class="{ active: activeTab === 'basic' }" @click="activeTab = 'basic'">
          <i class="fa-solid fa-gear"></i><span>{{ UI_BASIC }}</span>
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'advanced' }" @click="activeTab = 'advanced'">
          <i class="fa-solid fa-microchip"></i><span>{{ UI_ADVANCED }}</span>
        </button>

        <div class="tab-nav-spacer"></div>
        <div class="tab-nav-actions">
          <div ref="presetListEl" class="preset-chips">
            <span
              ref="presetFrameEl"
              class="preset-frame"
              :style="presetFrameStyle"
              aria-hidden="true"
            ></span>
            <button
              v-for="p in SESSION_PRESETS"
              :key="p.id"
              class="preset-chip"
              :class="{ active: activePresetId === p.id }"
              :title="p.description"
              @click="applyPreset(p.settings)"
            >
              <i :class="p.icon"></i>
              <span>{{ p.name }}</span>
            </button>
            <button
              class="preset-chip"
              :class="{ active: isDefault }"
              title="应用会话默认设定"
              @click="applyDefaults(props.defaults)"
            >
              <i class="fa-solid fa-scale-balanced"></i>
              <span>默认</span>
            </button>
          </div>
        </div>
      </nav>

      <!-- 右侧面板 -->
      <div class="tab-content">
        <Transition name="tab-switch" mode="out-in">
        <div :key="activeTab" class="tab-panel" role="tabpanel">
        <!-- 基础 -->
        <template v-if="activeTab === 'basic'">
          <div class="section">
            <label class="label">
              {{ UI_SYSTEM_PROMPT }}
              <button v-if="local.system_prompt != null" class="clear-btn" :title="UI_CLEAR" @click="clearField('system_prompt')">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </label>
            <div v-if="local.system_prompt == null" class="unset-placeholder" @click="setDefault('system_prompt')">点击设置</div>
            <textarea
              v-else
              v-model="local.system_prompt"
              class="input area" rows="4"
              @input="applyChange()"
            />
          </div>
          <div class="section">
            <label class="label">
              {{ UI_TEMPERATURE }} <code>{{ local.temperature != null ? local.temperature.toFixed(2) : '默认' }}</code>
              <button v-if="local.temperature != null" class="clear-btn" :title="UI_CLEAR" @click="clearField('temperature')"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">较高的值（如 0.9）使输出更随机，较低的值（如 0.2）使输出更确定。</p>
            <div v-if="local.temperature == null" class="unset-placeholder" @click="setDefault('temperature')">点击设置</div>
            <input v-else type="range" min="0" max="2" step="0.05" v-model.number="local.temperature" class="range" @input="applyChange()" />
          </div>
          <div class="section">
            <label class="label">
              {{ UI_MAX_TOKENS }} <code>{{ local.max_tokens ?? '默认' }}</code>
              <button v-if="local.max_tokens != null" class="clear-btn" :title="UI_CLEAR" @click="clearField('max_tokens')"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">单次生成允许的最大 token 数，范围 1–32768。</p>
            <div v-if="local.max_tokens == null" class="unset-placeholder" @click="setDefault('max_tokens')">点击设置</div>
            <input v-else type="number" min="1" max="32768" step="256" v-model.number="local.max_tokens" class="input" @input="applyChange()" />
          </div>
        </template>

        <!-- 高级 -->
        <template v-if="activeTab === 'advanced'">
          <div v-for="f in clearableFields" :key="f.key" class="section">
            <label class="label">
              {{ f.label }}
              <code>{{ (local as any)[f.key] != null ? f.fmt((local as any)[f.key]) : "默认" }}</code>
              <button
                v-if="(local as any)[f.key] != null"
                class="clear-btn" :title="UI_CLEAR"
                @click="clearField(f.key)"
              >
                <i class="fa-solid fa-xmark"></i>
              </button>
            </label>
            <p class="desc" v-if="f.key === 'top_p'">核采样阈值，仅考虑概率质量累积到此值内的 token。0 = 不限制。</p>
            <p class="desc" v-else-if="f.key === 'top_k'">仅从概率最高的 K 个 token 中采样。</p>
            <p class="desc" v-else-if="f.key === 'presence_penalty'">正值惩罚已出现过的 token，鼓励模型谈论新话题。</p>
            <p class="desc" v-else-if="f.key === 'frequency_penalty'">正值按 token 出现频率等比惩罚，降低重复词语。</p>
            <p class="desc" v-else-if="f.key === 'repeat_penalty'">惩罚重复的 token 序列，值越高惩罚越强。</p>
            <!-- 滑块（step < 1）：null 时不显示 -->
            <div
              v-if="f.step < 1 && (local as any)[f.key] == null"
              class="unset-placeholder"
              @click="setDefault(f.key)"
            >点击设置</div>
            <input
              v-else-if="f.step < 1"
              type="range"
              :min="f.min" :max="f.max" :step="f.step"
              v-model.number="(local as any)[f.key]"
              class="range"
              @input="applyChange()"
            />
            <!-- 数字输入（step >= 1）: null 时不显示 -->
            <div
              v-else-if="(local as any)[f.key] == null"
              class="unset-placeholder"
              @click="setDefault(f.key)"
            >点击设置</div>
            <input
              v-else
              type="number"
              :min="f.min" :max="f.max" :step="f.step"
              v-model.number="(local as any)[f.key]"
              class="input"
              @input="applyChange()"
            />
          </div>
        </template>
        </div>
        </Transition>
      </div>
    </div>
  </FloatingWindow>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════
   布局
   ═══════════════════════════════════════════════════ */

.settings-layout {
  display: flex;
  height: 440px;
}

/* ═══════════════════════════════════════════════════
   左侧标签栏
   ═══════════════════════════════════════════════════ */

.tab-nav {
  width: 150px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 0;
  border-right: 1px solid var(--border);
  background: var(--bg-primary);
}

.preset-chips {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 预设类型高亮框：滑动 + 拉伸回弹 + 细高光边 */
.preset-frame {
  position: absolute;
  z-index: 0;
  pointer-events: none;
  border-radius: 16px;
  background: var(--accent-bg);
  border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
  box-shadow:
    inset 0 0 0 1px var(--glass-highlight),
    0 0 12px var(--accent-shadow);
  transition:
    top 0.32s cubic-bezier(0.22, 1.12, 0.36, 1),
    left 0.32s cubic-bezier(0.22, 1.12, 0.36, 1),
    width 0.32s cubic-bezier(0.22, 1.12, 0.36, 1),
    height 0.32s cubic-bezier(0.22, 1.12, 0.36, 1),
    opacity 0.15s ease;
}

.preset-frame.no-anim {
  transition: none !important;
}

.preset-chip {
  position: relative;
  z-index: 1;
  height: 32px;
  border-radius: 16px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-dim);
  background: transparent;
  border: 1px solid var(--border);
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.preset-chip i { font-size: 13px; width: 16px; text-align: center; }
.preset-chip:hover { color: var(--text-secondary); background: var(--bg-hover); border-color: var(--text-dim); }
.preset-chip.active {
  /* 背景与描边由 .preset-frame 统一绘制 */
  color: var(--accent);
  border-color: transparent;
  background: transparent;
}

.tab-nav-actions {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 10px;
}

/* ═══════════════════════════════════════════════════
   右侧面板
   ═══════════════════════════════════════════════════ */

.tab-content {
  flex: 1; overflow-y: auto; padding: 20px 24px; min-width: 0;
}

/* 标签页切换：淡入 + 轻微侧滑 */
.tab-panel {
  min-height: 100%;
}
/* 标签选中框：滑动指示器 */
.tab-nav {
  position: relative;
}

.tab-btn {
  position: relative;
  z-index: 1;
}

.tab-btn.active {
  background: transparent;
  box-shadow: none;
}

.tab-indicator {
  position: absolute;
  z-index: 0;
  pointer-events: none;
  border-radius: 0;
  background: var(--accent-bg-mid);
  box-shadow: inset 2px 0 0 var(--accent);
  transition:
    top 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    left 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    width 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    height 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.15s ease;
}

.tab-indicator.no-anim {
  transition: none !important;
}

/* 内容从左侧进入 */
.tab-switch-enter-from {
  opacity: 0;
  transform: translateX(-8px);
}

.tab-switch-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}


.tab-switch-enter-active,
.tab-switch-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.tab-switch-enter-from {
  opacity: 0;
  transform: translateX(8px);
}

.tab-switch-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

.section { margin-bottom: 16px; }
.section:last-child { margin-bottom: 0; }

/* ── 标签 ──────────────────────────────────────── */

.label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px; font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.05em;
  margin-bottom: 5px;
}

.label code {
  font-size: 12px; font-weight: 400;
  color: var(--accent); background: var(--accent-bg);
  padding: 1px 6px; border-radius: var(--radius);
  text-transform: none; letter-spacing: 0;
  font-family: var(--font-mono);
}

.desc {
  font-size: 13px; color: var(--text-dim); margin: 0 0 8px; line-height: 1.4;
}

/* ── 清除按钮 ──────────────────────────────────── */

.clear-btn {
  width: 18px; height: 18px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: 1px solid var(--border);
  color: var(--text-dim); font-size: 10px; cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
  margin-left: auto;
}
.clear-btn:hover { color: var(--error); border-color: var(--error); background: var(--error-bg); }

/* ── 输入控件 ──────────────────────────────────── */

.input {
  width: 100%;
  background: var(--bg-primary); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 8px 12px;
  color: var(--text-primary); font-size: 14px;
  outline: none; font-family: var(--font-mono);
}
.input:focus { border-color: var(--accent); }

.area { resize: vertical; line-height: 1.4; min-height: 72px; }

.range {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 5px; border-radius: var(--radius-sm);
  background: var(--border); outline: none; cursor: pointer;
}
.range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg-primary);
  cursor: pointer;
  box-shadow: 0 1px 3px var(--shadow-sm);
}

.unset-placeholder {
  font-size: 13px;
  color: var(--text-dim);
  padding: 7px 12px;
  background: var(--bg-primary);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  text-align: center;
  transition: color 0.15s, border-color 0.15s;
}
.unset-placeholder:hover { color: var(--text-secondary); border-color: var(--text-dim); }
</style>
