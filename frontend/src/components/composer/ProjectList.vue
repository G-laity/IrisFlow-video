<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  UI_PROJECT_DELETE_CONFIRM,
  UI_PROJECT_NEW,
  UI_PROJECT_NO_PROJECTS,
  UI_PROJECT_SCRIPT_PLACEHOLDER,
  UI_PROJECT_TITLE_PLACEHOLDER,
  UI_DELETE,
} from "../../constants";
import {
  activeProjectId,
  composerProjects,
  createComposerProjectItem,
  parseComposerError,
  refreshComposerProjects,
  removeComposerProjectItem,
  selectComposerProject,
} from "../../composables/useComposer";

const emit = defineEmits<{
  selected: [projectId: string];
}>();

const title = ref("");
const script = ref("");
const creating = ref(false);
const error = ref("");

onMounted(() => {
  refreshComposerProjects();
});

function select(projectId: string): void {
  selectComposerProject(projectId);
  emit("selected", projectId);
}

async function handleCreate(): Promise<void> {
  const t = title.value.trim();
  if (!t || creating.value) return;
  creating.value = true;
  error.value = "";
  try {
    const project = await createComposerProjectItem(t, script.value.trim());
    title.value = "";
    script.value = "";
    emit("selected", project.project_id);
  } catch (e) {
    error.value = parseComposerError(e).join("\n");
  } finally {
    creating.value = false;
  }
}

async function handleDelete(projectId: string): Promise<void> {
  if (!window.confirm(UI_PROJECT_DELETE_CONFIRM)) return;
  try {
    await removeComposerProjectItem(projectId);
  } catch (e) {
    error.value = parseComposerError(e).join("\n");
  }
}
</script>

<template>
  <div class="pl-body">
    <!-- 新建 -->
    <div class="pl-create">
      <input v-model="title" class="pl-input" :placeholder="UI_PROJECT_TITLE_PLACEHOLDER" @keydown.enter="handleCreate" />
      <textarea v-model="script" class="pl-textarea" rows="2" :placeholder="UI_PROJECT_SCRIPT_PLACEHOLDER" />
      <button class="pl-btn pl-btn--primary" :disabled="creating || !title.trim()" @click="handleCreate">
        <i class="fa-solid fa-plus"></i>
        {{ UI_PROJECT_NEW }}
      </button>
    </div>
    <p v-if="error" class="pl-error">{{ error }}</p>

    <!-- 列表 -->
    <div v-if="composerProjects.length" class="pl-list">
      <button
        v-for="project in composerProjects"
        :key="project.project_id"
        class="pl-item"
        :class="{ on: activeProjectId === project.project_id }"
        @click="select(project.project_id)"
      >
        <div class="pl-item-main">
          <span class="pl-item-title">{{ project.title }}</span>
          <span class="pl-item-meta">
            {{ project.timeline?.tracks?.video?.length ?? 0 }} 镜头 ·
            {{ project.timeline?.tracks?.subtitles?.length ?? 0 }} 字幕 ·
            {{ project.asset_ids?.length ?? 0 }} 素材
          </span>
        </div>
        <span class="pl-item-delete" :title="UI_DELETE" @click.stop="handleDelete(project.project_id)">
          <i class="fa-solid fa-trash"></i>
        </span>
      </button>
    </div>
    <div v-else class="pl-empty">
      <i class="fa-solid fa-clapperboard"></i>
      <p>{{ UI_PROJECT_NO_PROJECTS }}</p>
    </div>
  </div>
</template>

<style scoped>
.pl-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pl-create {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pl-input,
.pl-textarea {
  padding: 7px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  outline: none;
  resize: vertical;
}
.pl-input:focus,
.pl-textarea:focus { border-color: var(--accent); }

.pl-btn {
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
  align-self: flex-start;
}
.pl-btn:hover { color: var(--text-primary); background: var(--bg-hover); border-color: var(--text-dim); }
.pl-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pl-btn--primary { color: var(--accent); border-color: var(--accent); background: var(--accent-bg); }
.pl-btn--primary:hover { color: var(--white); background: var(--accent); }

.pl-error {
  margin: 0;
  font-size: 12px;
  color: var(--error);
  white-space: pre-wrap;
}

.pl-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pl-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.pl-item:hover { background: var(--bg-hover); border-color: var(--text-dim); }
.pl-item.on { border-color: var(--accent); background: var(--accent-bg); }

.pl-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pl-item-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pl-item-meta { font-size: 11px; color: var(--text-dim); }

.pl-item-delete {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  color: var(--text-dim);
  font-size: 11px;
  transition: color 0.15s, background 0.15s;
}
.pl-item-delete:hover { color: var(--error); background: var(--error-bg-hover); }

.pl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 30px 0;
  color: var(--text-dim);
  font-size: 13px;
}
.pl-empty i { font-size: 28px; }
.pl-empty p { margin: 0; }
</style>
