<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import FloatingWindow from "./FloatingWindow.vue";
import AssetLibrary from "../composer/AssetLibrary.vue";
import {
  UI_COMPOSER,
  UI_TAB_ASSETS,
  UI_TAB_PROJECTS,
  UI_TAB_RENDERS,
  UI_TAB_TIMELINE,
} from "../../constants";
import {
  refreshComposerAssets,
  refreshComposerConfig,
  startComposerEvents,
  stopComposerEvents,
} from "../../composables/useComposer";
import type { PreviewPayload } from "../../types/api";

defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  close: [];
  preview: [payload: PreviewPayload];
}>();

// ── 标签页 ────────────────────────────────────────
// M1 仅素材页启用；项目 / 时间轴 / 渲染随 M2 / M3 里程碑开放。

const activeTab = ref(UI_TAB_ASSETS);

const TABS = [
  { key: UI_TAB_ASSETS, icon: "fa-solid fa-photo-film", available: true },
  { key: UI_TAB_PROJECTS, icon: "fa-solid fa-clapperboard", available: false },
  { key: UI_TAB_TIMELINE, icon: "fa-solid fa-bars-staggered", available: false },
  { key: UI_TAB_RENDERS, icon: "fa-solid fa-film", available: false },
];

// ── 生命周期：状态初始化 + SSE 订阅 ──────────────

onMounted(() => {
  refreshComposerAssets();
  refreshComposerConfig();
  startComposerEvents();
});

onUnmounted(() => {
  stopComposerEvents();
});
</script>

<template>
  <FloatingWindow
    width="640px"
    :title="UI_COMPOSER"
    icon="fa-solid fa-clapperboard"
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <div class="cp-body">
      <!-- 标签页 -->
      <div class="cp-tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="cp-tab"
          :class="{ on: activeTab === tab.key }"
          :disabled="!tab.available"
          :title="tab.available ? tab.key : `${tab.key}（后续里程碑开放）`"
          @click="tab.available && (activeTab = tab.key)"
        >
          <i :class="tab.icon"></i>
          {{ tab.key }}
        </button>
      </div>

      <!-- 素材库（M1 唯一启用的标签页） -->
      <div class="cp-content">
        <AssetLibrary v-if="activeTab === UI_TAB_ASSETS" @preview="payload => emit('preview', payload)" />
      </div>
    </div>
  </FloatingWindow>
</template>

<style scoped>
.cp-body {
  display: flex;
  flex-direction: column;
}

.cp-tabs {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  gap: 2px;
  padding: 8px 10px 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.cp-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.cp-tab:hover { color: var(--text-secondary); }
.cp-tab.on { color: var(--accent); border-bottom-color: var(--accent); }
.cp-tab:disabled { color: var(--text-dim); opacity: 0.45; cursor: not-allowed; }

/* 素材库滚动区（由 FloatingWindow 的 fw-body 统一滚动） */
.cp-content {
  flex: 1;
  min-height: 0;
}
</style>
