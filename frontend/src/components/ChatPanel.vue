<script setup lang="ts">
import { ref, nextTick, computed, watch, inject, provide, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import MessageBubble from "./MessageBubble.vue";
import WorkflowLog from "./WorkflowLog.vue";
import ChatInput from "./ChatInput.vue";
import ToolGroupPanel from "./floating/ToolGroupPanel.vue";
import type { UIMessage, WorkflowEntry, FileAttachment, PreviewPayload } from "../types/api";
import { useAgent } from "../composables/useAgent";
import { getConversation, getServerUrl, isConnectionError } from "../api/client";
import { ON_CONNECTION_LOST_KEY, REFRESH_CONVERSATION_LIST_KEY, REFRESH_DEFAULT_SETTINGS_KEY } from "../composables/injectionKeys";
import { parseFileBlocks } from "../utils";
import { toolGroups, discoverTools } from "../composables/toolMetadata";
import {
  DEFAULT_ENABLED_TOOLS,
  DRAFT_NEW,
  FORCE_SCROLL_DELAY,
  HISTORY_SCROLL_DELAY,
  ROLE_ASSISTANT,
  ROLE_TOOL,
  ROLE_USER,
  SCROLL_DEFY_LIMIT,
  SCROLL_THRESHOLD,
  STATUS_COMPLETED,
  STATUS_GENERATING,
  STATUS_PENDING,
  UI_COMPOSER,
  UI_JUMP_BOTTOM,
  UI_LANDING_HINT,
  UI_LANDING_PLACEHOLDER,
  UI_LANDING_PROMPTS,
  UI_LANDING_SUBTITLE,
  UI_LANDING_TITLE,
  UI_LANDING_UPDATE,
  UI_SESSION_LIST,
  UI_SETTINGS,
  UI_WELCOME_SUBTITLE,
  UI_WELCOME_TITLE,
} from "../constants";
import { draftStore } from "../composables/drafts";
import type { MorphRect } from "../utils/fluidMorph";

const props = defineProps<{
  model: string;
}>();

const emit = defineEmits<{
  selectEntry: [entry: WorkflowEntry | null];
  preview: [payload: PreviewPayload];
  openConversations: [origin?: MorphRect];
  openComposer: [origin?: MorphRect];
  openSettings: [origin?: MorphRect];
}>();

/** 把入口按钮的视口矩形交给 App，用作浮窗流体展开的起点 */
function rectOf(e: MouseEvent): MorphRect | undefined {
  const el = e.currentTarget as HTMLElement | null;
  if (!el) return undefined;
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return undefined;
  return { left: r.left, top: r.top, width: r.width, height: r.height };
}

const route = useRoute();
const router = useRouter();
const refreshConversationList = inject(REFRESH_CONVERSATION_LIST_KEY, () => {});
const onConnectionLost = inject(ON_CONNECTION_LOST_KEY, () => {});

const sessionId = computed(() => (route.params.sessionId as string) ?? null);
const isLanding = computed(() => !sessionId.value);
const landingPrompts = UI_LANDING_PROMPTS;
const landingInputRef = ref<{ setText: (text: string) => void } | null>(null);

function useLandingPrompt(prompt: string) {
  landingInputRef.value?.setText(prompt);
}

const enabledBuiltins = ref<string[]>([...DEFAULT_ENABLED_TOOLS]);

// ── 工具组管理浮窗 ─────────────────────────────

const showGroupPanel = ref(false);
const activePanelGroup = ref<string | null>(null);

function handleManageGroup(groupName: string) {
  activePanelGroup.value = groupName;
  showGroupPanel.value = true;
}

// ── 工具开关（仅内存，与 ChatInput 共用 draftStore） ──────
function saveTools(sid: string | null, tools: string[]) {
  const key = sid ?? DRAFT_NEW;
  if (!draftStore[key]) draftStore[key] = {};
  draftStore[key].enabledBuiltins = tools;
}

function loadTools(sid: string | null): string[] {
  // 新会话界面：始终返回默认值
  if (sid === null) return defaultTools();
  const tools = draftStore[sid]?.enabledBuiltins ?? draftStore[DRAFT_NEW]?.enabledBuiltins;
  return tools ?? defaultTools();
}

function handleToggleTool(name: string) {
  const idx = enabledBuiltins.value.indexOf(name);
  if (idx >= 0) enabledBuiltins.value.splice(idx, 1);
  else enabledBuiltins.value.push(name);
  saveTools(sessionId.value, enabledBuiltins.value);
}

function handleToggleGroup(payload: { groupName: string; toolNames: string[] }) {
  const { toolNames } = payload;
  const allOn = toolNames.every(n => enabledBuiltins.value.includes(n));
  if (allOn) {
    enabledBuiltins.value = enabledBuiltins.value.filter(n => !toolNames.includes(n));
  } else {
    for (const n of toolNames) {
      if (!enabledBuiltins.value.includes(n)) enabledBuiltins.value.push(n);
    }
  }
  saveTools(sessionId.value, enabledBuiltins.value);
}

const agent = useAgent({
  model: computed(() => props.model),
  activeSessionId: sessionId,
  onSessionCreated: (sid: string) => {
    router.replace(`/chat/${sid}`);
    refreshConversationList();
  },
  onTitleGenerated: () => {
    refreshConversationList();
  },
  onConnectionLost,
  onSessionNotFound: () => {
    router.push("/");
  },
});

const scrollEl = ref<HTMLElement | null>(null);
const typingAnchor = ref<HTMLElement | null>(null);
/** 仅当前活跃会话在生成时才视为 loading。loading 已按会话保存/恢复，无需额外守卫。 */
const isLoading = computed(() => agent.loading.value);
const pendingCalls = computed(() => agent.pendingToolCalls.value);

function handleSelectEntry(entry: WorkflowEntry) { emit("selectEntry", entry); }

async function handleSend(message: string, files?: FileAttachment[], thinking?: boolean) {
  agent.error.value = null;  // 清除上次错误
  forceScrollToBottom();
  await agent.run(message, enabledBuiltins.value, files, thinking ?? true);
  forceScrollToBottom();
  refreshConversationList();  // 同步元数据（message_count / 自动标题等 SSE 不覆盖的字段）
}

const isAtBottom = ref(true);
let _defyCount = 0;
let _ignoreScroll = false;   // 程序化滚动后忽略紧接着的一个 scroll 事件

function _atEnd(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD;
}

function _scrollToEnd(force: boolean) {
  const el = scrollEl.value;
  if (!el) return;
  el.offsetHeight;
  if (force || _atEnd(el)) {
    _ignoreScroll = true;
    if (typingAnchor.value) {
      typingAnchor.value.scrollIntoView({ block: "center", behavior: "instant" });
    } else {
      el.scrollTop = el.scrollHeight;
    }
    isAtBottom.value = true;
  } else {
    isAtBottom.value = false;
  }
}

function _scheduleScroll(force: boolean) {
  nextTick(() => requestAnimationFrame(() => _scrollToEnd(force)));
}

function forceScrollToBottom() {
  _defyCount = 0;
  _scheduleScroll(true);
  setTimeout(() => _scheduleScroll(true), FORCE_SCROLL_DELAY);
}

function onScroll() {
  if (_ignoreScroll) { _ignoreScroll = false; return; }
  const el = scrollEl.value;
  if (!el) return;
  const wasAtBottom = isAtBottom.value;
  isAtBottom.value = _atEnd(el);
  if (!isAtBottom.value && isLoading.value) {
    _defyCount++;
  } else if (isAtBottom.value && !wasAtBottom) {
    _defyCount = 0;
  }
}

/** 不滚动，仅根据当前视口更新 isAtBottom — 响应窗口 resize / tab 切换等无 scroll 事件的场景。 */
function checkAtBottom() {
  const el = scrollEl.value;
  if (!el) return;
  isAtBottom.value = _atEnd(el);
}

// ── 动态工具发现 ──────────────────────────────




function defaultTools(): string[] {
  // 默认不启用任何工具（内置 + MCP 均需用户手动开启）
  return [...DEFAULT_ENABLED_TOOLS];
}

// ── 暴露给 SettingsPanel ──────────────────────────

provide(REFRESH_DEFAULT_SETTINGS_KEY, agent.refreshDefaultSettings);

onMounted(() => {
  window.addEventListener("resize", checkAtBottom);
  document.addEventListener("visibilitychange", checkAtBottom);
  discoverTools();  // 启动时发现 MCP 工具
  // MCP 连接可能尚未完成，延迟重试
  for (const delay of [2000, 5000, 10000]) {
    setTimeout(() => discoverTools(), delay);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", checkAtBottom);
  document.removeEventListener("visibilitychange", checkAtBottom);
});

// 流式内容变化 → 仅会话进行中且未达违抗上限时跟滚
watch(() => agent.messages.value, () => {
  if (!isLoading.value) return;
  _scheduleScroll(_defyCount < SCROLL_DEFY_LIMIT);
}, { deep: true });

// 流式结束 → 末批 DOM 变更补偿 + 重置违抗
watch(isLoading, (loading, wasLoading) => {
  if (wasLoading && !loading) {
    _defyCount = 0;
    _scheduleScroll(false);
  }
});

// ── 路由驱动的会话加载（从 App.vue 搬入） ────────────
watch(sessionId, async (newId, oldId) => {
  // 保存旧会话的工具开关，恢复新会话的
  saveTools(oldId ?? null, enabledBuiltins.value);
  enabledBuiltins.value = loadTools(newId ?? null);

  if (!newId) return;  // 新建对话，无需加载
  await nextTick();  // 等待 useAgent watch 触发 _activate 完成
  if (agent.hasMessages()) { forceScrollToBottom(); return; }  // 已有缓存（切回生成中/访问过的会话）
  // 刚由 run() 创建的会话（状态为 generating）不触发后端加载，避免与 SSE 流竞态
  if (agent.getSessionStatus(newId) === STATUS_GENERATING || agent.getSessionStatus(newId) === STATUS_PENDING) return;
  try {
    const detail = await getConversation(newId);
    agent.initSession(newId, detail.status ?? STATUS_COMPLETED);
    const history = detail.messages.map((m: any) => {
      const entry: any = {
        role: (m.role === ROLE_TOOL ? ROLE_TOOL : m.role) as "user" | "assistant" | "system" | "tool",
        content: typeof m.content === "string" ? m.content : "",
        reasoning_content: m.reasoning_content,
        tool_calls: m.tool_calls,
        tool_call_id: m.tool_call_id,
        message_status: m.message_status,
        thinking: m.thinking,
      };
      if (Array.isArray(m.content)) {
        const texts: string[] = [];
        const imgs: string[] = [];
        for (const p of m.content as any[]) {
          if (p.type === "text") texts.push(p.text || "");
          else if (p.type === "image_url" && p.image_url?.url) imgs.push(p.image_url.url);
        }
        entry.content = texts.join("\n");
        if (imgs.length) entry.images = imgs;
      }
      if (entry.role === ROLE_USER && typeof entry.content === "string") {
        const parsed = parseFileBlocks(entry.content);
        if (parsed.files.length) {
          entry.files = parsed.files;
          entry.content = parsed.text;
        }
      }
      return entry;
    });
    agent.loadHistory(history, detail.status ?? STATUS_COMPLETED);
    // 从后端恢复会话设定（后端权威）
    if (detail.settings) {
      agent.currentSettings.value = detail.settings;
      agent.syncSessionSettings(newId);
    }
    forceScrollToBottom();
    // 页面刷新时若后端仍在生成或排队中，重连 SSE 流继续上屏/等待调度
    if (detail.status === STATUS_GENERATING || detail.status === STATUS_PENDING) {
      agent.resumeStream(newId);
    }
  } catch (e: any) {
    if (isConnectionError(e)) {
      onConnectionLost();
    } else {
      // HTTP 错误（404 会话不存在 / 500 等）→ 返回首页新建对话
      router.push("/");
    }
  }
}, { immediate: true });

defineExpose({
  clearMessages() { agent.clearMessages(); },
  removeSession(sid: string) { agent.removeSession(sid); },
  loadHistory(msgs: {
    role: UIMessage["role"]; content: string;
    reasoning_content?: string | null;
    tool_calls?: { id: string; type: string; function: { name: string; arguments: string } }[] | null;
    tool_call_id?: string | null;
    images?: string[];
    files?: FileAttachment[];
  }[]) {
    agent.loadHistory(msgs);
    forceScrollToBottom();
    setTimeout(() => forceScrollToBottom(), HISTORY_SCROLL_DELAY);
  },
  initSession(sid: string, status: import("../types/api").SessionStatus) { agent.initSession(sid, status); },
  hasMessages() { return agent.hasMessages(); },
});
</script>

<template>
  <div
    ref="scrollEl"
    class="chat-panel"
    :class="{ 'chat-panel--landing': isLanding }"
    @scroll="onScroll"
  >
    <div v-if="isLanding" class="landing">
      <header class="landing-top">
        <div class="landing-brand">
          <span class="landing-logo"><i class="fa-solid fa-bolt"></i></span>
          <span class="landing-wordmark">IrisFlow</span>
        </div>
        <nav class="landing-nav" aria-label="快捷入口">
          <button type="button" @click="emit('openConversations', rectOf($event))">
            <i class="fa-solid fa-clock-rotate-left"></i><span>{{ UI_SESSION_LIST }}</span>
          </button>
          <button type="button" @click="emit('openComposer', rectOf($event))">
            <i class="fa-solid fa-clapperboard"></i><span>{{ UI_COMPOSER }}</span>
          </button>
          <button type="button" @click="emit('openSettings', rectOf($event))">
            <i class="fa-solid fa-gear"></i><span>{{ UI_SETTINGS }}</span>
          </button>
        </nav>
      </header>

      <main class="landing-main">
        <div class="landing-note">
          <i class="fa-solid fa-diamond"></i>
          <span>{{ UI_LANDING_UPDATE }}</span>
          <i class="fa-solid fa-arrow-right landing-note-arrow"></i>
        </div>
        <h1>{{ UI_LANDING_TITLE }}</h1>
        <p class="landing-sub">{{ UI_LANDING_SUBTITLE }}</p>

        <div class="landing-composer">
          <ChatInput
            ref="landingInputRef"
            hero
            :placeholder="UI_LANDING_PLACEHOLDER"
            :loading="isLoading"
            :disabled="pendingCalls.length > 0"
            :enabled-builtins="enabledBuiltins"
            :tool-groups="toolGroups"
            :session-settings="agent.currentSettings.value"
            :default-settings="agent.defaultSettings.value"
            @send="handleSend"
            @stop="agent.abort()"
            @update:session-settings="agent.currentSettings.value = $event"
            @toggle-tool="handleToggleTool"
            @toggle-group="handleToggleGroup"
            @manage-group="handleManageGroup"
            @preview="(p) => emit('preview', p)"
          />
        </div>

        <div class="landing-prompts">
          <button
            v-for="prompt in landingPrompts"
            :key="prompt"
            type="button"
            @click="useLandingPrompt(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
        <div class="landing-hint">{{ UI_LANDING_HINT }}</div>
      </main>
    </div>

    <div v-else class="chat-center">
      <div class="chat-scroll">
        <div v-if="!agent.messages.value.length && !isLoading" class="welcome">
          <i class="welcome-icon fa-solid fa-bolt"></i>
          <h2>{{ UI_WELCOME_TITLE }}</h2>
          <p>{{ UI_WELCOME_SUBTITLE }}</p>
        </div>

        <template v-for="msg in agent.messages.value" :key="msg.id">
          <WorkflowLog
            v-if="msg.role === ROLE_ASSISTANT && (msg.workflowLog?.length || !!msg.content || !msg.streamDone || msg.aborted || msg.queued)"
            class="msg-enter"
            :entries="msg.workflowLog"
            :stream-done="msg.streamDone"
            :has-content="!!msg.content"
            :aborted="msg.aborted"
            :queued="msg.queued"
            :thinking="msg.thinking"
            @select="handleSelectEntry"
          />
          <MessageBubble
            v-if="msg.role === ROLE_USER || msg.role === ROLE_ASSISTANT"
            class="msg-enter"
            :msg="msg"
            @preview="(p) => emit('preview', p)"
          />
        </template>

        <div ref="typingAnchor" v-if="isLoading && !pendingCalls.length" class="typing">
          <span class="dot" /><span class="dot" /><span class="dot" />
        </div>
      </div>

      <div class="chat-bottom">
        <button v-if="sessionId && !isAtBottom" class="jump-bottom" @click="forceScrollToBottom" :title="UI_JUMP_BOTTOM">
          <i class="fa-solid fa-arrow-down"></i>
        </button>
        <ChatInput
          :loading="isLoading"
          :disabled="pendingCalls.length > 0"
          :enabled-builtins="enabledBuiltins"
          :tool-groups="toolGroups"
          :session-settings="agent.currentSettings.value"
          :default-settings="agent.defaultSettings.value"
          @send="handleSend"
          @stop="agent.abort()"
          @update:session-settings="agent.currentSettings.value = $event"
          @toggle-tool="handleToggleTool"
          @toggle-group="handleToggleGroup"
          @manage-group="handleManageGroup"
          @preview="(p) => emit('preview', p)"
        />
      </div>
    </div>

    <ToolGroupPanel
      v-if="activePanelGroup"
      v-model="showGroupPanel"
      :group-name="activePanelGroup"
      :tool-names="toolGroups[activePanelGroup] ?? []"
      :enabled-builtins="enabledBuiltins"
      @toggle-tool="handleToggleTool"
      @close="activePanelGroup = null"
    />
  </div>
</template>

<style scoped>
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: row;
  justify-content: center;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
}

/* ── 开始页 ─────────────────────────────────────── */

.chat-panel--landing {
  display: block;
  overflow-y: auto;
}

.landing {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  padding: 0 32px;
}

.landing-top {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 4px 10px;
}

.landing-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.landing-logo {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: var(--accent-bg);
  border: 1px solid var(--accent-strong);
  color: var(--accent);
  font-size: 15px;
  box-shadow: inset 0 1px 0 var(--glass-highlight);
}

.landing-wordmark {
  font-size: 17px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.landing-nav {
  display: flex;
  align-items: center;
  gap: 6px;
}

.landing-nav button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg-secondary) 35%, transparent);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}

.landing-nav button:hover {
  color: var(--text-secondary);
  border-color: var(--text-dim);
  background: var(--bg-hover);
}

.landing-nav i { font-size: 12px; }

.landing-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 0 0 6vh;
}

.landing-note {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg-secondary) 38%, transparent);
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.4;
}

.landing-note i:first-child {
  color: var(--accent);
  font-size: 9px;
}

.landing-note-arrow {
  font-size: 9px;
  opacity: 0.55;
}

.landing-main h1 {
  margin: 26px 0 12px;
  font-size: clamp(38px, 6vw, 66px);
  line-height: 1.06;
  letter-spacing: 0.08em;
  font-weight: 650;
  color: var(--text-primary);
}

.landing-sub {
  margin: 0 0 30px;
  max-width: 540px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.landing-composer {
  width: min(780px, 100%);
  text-align: left;
}

.landing-prompts {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 16px;
}

.landing-prompts button {
  padding: 9px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg-secondary) 30%, transparent);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}

.landing-prompts button:hover {
  color: var(--text-secondary);
  border-color: var(--text-dim);
  background: var(--bg-hover);
}

.landing-hint {
  margin-top: 18px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  opacity: 0.7;
}

@media (max-width: 760px) {
  .landing { padding: 0 18px; }
  .landing-top { padding: 18px 0 8px; }
  .landing-nav button { padding: 9px; }
  .landing-nav button span { display: none; }
  .landing-main h1 { letter-spacing: 0.05em; }
  .landing-sub { font-size: 13px; }
  .landing-note { font-size: 10px; }
}

.chat-center {
  width: 100%;
  max-width: 780px;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.msg-enter {
  animation: msg-in 0.22s ease both;
}

@keyframes msg-in {
  from { opacity: 0; translate: 0 4px; }
  to   { opacity: 1; translate: 0 0; }
}

.chat-scroll {
  flex: 1;
  padding: 16px 48px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-bottom {
  position: sticky;
  bottom: 0;
  background: linear-gradient(to top, var(--bg-primary) 70%, transparent);
  padding: 8px 0 12px;
}

.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  text-align: center;
}

.welcome-icon { font-size: 48px; margin-bottom: 12px; }
.welcome h2 { font-size: 21px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.welcome p { font-size: 14px; max-width: 320px; line-height: 1.6; }

.typing { display: flex; gap: 4px; padding: 12px 16px; }

.dot {
  width: 6px; height: 6px;
  background: var(--accent);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}
.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }

.jump-bottom {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 8px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
}
.jump-bottom:hover { background: var(--bg-hover); color: var(--text-primary); }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}
</style>