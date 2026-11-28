<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import FloatingWindow from "./FloatingWindow.vue";
import AssetLibrary from "../composer/AssetLibrary.vue";
import ProjectList from "../composer/ProjectList.vue";
import RenderQueue from "../composer/RenderQueue.vue";
import StoryboardEditor from "../composer/StoryboardEditor.vue";
import {
  UI_COMPOSER,
  UI_TAB_ASSETS,
  UI_TAB_PROJECTS,
  UI_TAB_RENDERS,
  UI_TAB_TIMELINE,
} from "../../constants";
import {
  activeProjectId,
  refreshComposerConfig,
  startComposerEvents,
  stopComposerEvents,
} from "../../composables/useComposer";
import { useTabIndicator } from "../../composables/useTabIndicator";
import type { PreviewPayload } from "../../types/api";
import type { MorphRect } from "../../utils/fluidMorph";

defineProps<{
  modelValue: boolean;
  morphOrigin?: MorphRect | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  close: [];
  preview: [payload: PreviewPayload];
}>();

// ── 标签页 ────────────────────────────────────────
// M3：四个标签页全部启用。

const activeTab = ref(UI_TAB_ASSETS);
const { navEl, indicatorEl, indicatorStyle } = useTabIndicator(activeTab, ".cp-tab.on");

const TABS = [
  { key: UI_TAB_ASSETS, icon: "fa-solid fa-photo-film", available: true },
  { key: UI_TAB_PROJECTS, icon: "fa-solid fa-clapperboard", available: true },
  { key: UI_TAB_TIMELINE, icon: "fa-solid fa-bars-staggered", available: true },
  { key: UI_TAB_RENDERS, icon: "fa-solid fa-film", available: true },
];

function onProjectSelected(): void {
  activeTab.value = UI_TAB_TIMELINE;
}

// ── 生命周期：状态初始化 + SSE 订阅 ──────────────

onMounted(() => {
  // 各标签页组件常驻挂载并各自预取；这里只拉取共享配置和订阅事件
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
    :morph-from="morphOrigin"
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <div class="cp-body">
      <!-- 标签页 -->
      <div ref="navEl" class="cp-tabs">
        <span ref="indicatorEl" class="cp-tab-indicator" :style="indicatorStyle" aria-hidden="true"></span>
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

      <div class="cp-content">
        <!-- 四个标签页常驻挂载（v-show）：数据在启动时预取，切换不再等待首次挂载 -->
        <AssetLibrary v-show="activeTab === UI_TAB_ASSETS" @preview="payload => emit('preview', payload)" />
        <ProjectList v-show="activeTab === UI_TAB_PROJECTS" @selected="onProjectSelected" />
        <StoryboardEditor v-show="activeTab === UI_TAB_TIMELINE" />
        <RenderQueue
          v-show="activeTab === UI_TAB_RENDERS"
          :project-id="activeProjectId || undefined"
          @preview="payload => emit('preview', payload)"
        />
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
  position: relative;
  z-index: 1;
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
  transition: color 0.15s;
}
.cp-tab:hover { color: var(--text-secondary); }
.cp-tab.on { color: var(--accent); border-bottom-color: transparent; }
.cp-tab:disabled { color: var(--text-dim); opacity: 0.45; cursor: not-allowed; }

/* 选中框：与设置面板同款滑动指示器 */
.cp-tab-indicator {
  position: absolute;
  z-index: 0;
  pointer-events: none;
  border-radius: 8px 8px 0 0;
  background: var(--accent-bg-mid);
  box-shadow: inset 0 -2px 0 var(--accent);
  transition:
    top 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    left 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    width 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    height 0.28s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.15s ease;
}
.cp-tab-indicator.no-anim { transition: none !important; }

/* 素材库滚动区（由 FloatingWindow 的 fw-body 统一滚动） */
.cp-content {
  position: relative;
  flex: 1;
  min-height: 0;
}

/* 常驻面板切换时只做淡入，不再重新挂载；display:none → block 会重新触发动画 */
.cp-content > * { animation: cp-tab-in 0.18s ease; }

@keyframes cp-tab-in {
  from { opacity: 0; transform: translateX(8px); }
  to { opacity: 1; transform: translateX(0); }
}

@media (prefers-reduced-motion: reduce) {
  .cp-content > * { animation: none; }
}
</style>
