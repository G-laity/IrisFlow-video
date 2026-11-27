<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, inject, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import FloatingWindow from "./FloatingWindow.vue";
import {
  listConversations,
  deleteConversation,
  updateConversation,
  subscribeSessionStatus,
  readWithTimeout,
  isConnectionError,
} from "../../api/client";
import {
  DAY_MS,
  FLASH_DURATION,
  GROUP_MONTH_DAYS,
  GROUP_WEEK_DAYS,
  SSE_DATA_PREFIX,
  SSE_DATA_PREFIX_LEN,
  SSE_STATUS,
  STATUS_COMPLETED,
  STATUS_GENERATING,
  STATUS_IDLE,
  STATUS_PENDING,
  STATUS_READ_TIMEOUT,
  STATUS_RECONNECT_INIT,
  STATUS_RECONNECT_MAX,
  STATUS_REPLACED,
  STATUS_UNKNOWN,
  UI_DELETE,
  UI_CLEAR_ALL,
  UI_CANCEL,
  UI_DESELECT_ALL,
  UI_ITEM_UNIT,
  UI_SELECT_ALL,
  UI_SELECTED_PREFIX,
  UI_LOADING,
  UI_MORE,
  UI_NEW_CHAT,
  UI_NO_CONVERSATIONS,
  UI_PIN,
  UI_PINNED_GROUP,
  UI_RENAME,
  UI_SESSION_LIST,
  UI_TODAY,
  UI_UNPIN,
  UI_YESTERDAY,
  UI_STATUS_GENERATING,
  UI_STATUS_IDLE,
  UI_STATUS_PENDING,
  UI_STATUS_UNKNOWN,
  UI_WITHIN_MONTH,
  UI_WITHIN_WEEK,
} from "../../constants";
import { ON_CONNECTION_LOST_KEY, REMOVE_SESSION_CACHE_KEY } from "../../composables/injectionKeys";
import type { ConversationInfo, SessionStatus } from "../../types/api";
import type { MorphRect } from "../../utils/fluidMorph";

const route = useRoute();
const router = useRouter();
const currentSessionId = computed(() => (route.params.sessionId as string) ?? null);

defineProps<{
  modelValue: boolean;
  morphOrigin?: MorphRect | null;
}>();

const removeSessionCache = inject(REMOVE_SESSION_CACHE_KEY, () => {});
const onConnectionLost = inject(ON_CONNECTION_LOST_KEY, () => {});

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  close: [];
}>();

const conversations = ref<ConversationInfo[]>([]);
const loading = ref(false);
const editingId = ref<string | null>(null);
const editTitle = ref("");
const menuOpenId = ref<string | null>(null);
// ── 多选删除模式 ─────────────────────────────────

const selecting = ref(false);
const selectedIds = ref<Set<string>>(new Set());

const selectedCount = computed(() => selectedIds.value.size);
const allSelected = computed(
  () => conversations.value.length > 0 && selectedCount.value === conversations.value.length,
);

function enterSelection() {
  menuOpenId.value = null;
  editingId.value = null;
  selecting.value = true;
  selectedIds.value = new Set(conversations.value.map(c => c.session_id));
}

function exitSelection() {
  selecting.value = false;
  selectedIds.value = new Set();
}

function toggleSelect(id: string) {
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
  // 全部取消后自动收起操作栏并退出选择模式
  if (next.size === 0) exitSelection();
}

function toggleSelectAll() {
  if (allSelected.value) {
    exitSelection();
    return;
  }
  selectedIds.value = new Set(conversations.value.map(c => c.session_id));
}

function onItemClick(conv: ConversationInfo) {
  if (selecting.value) toggleSelect(conv.session_id);
  else router.push("/chat/" + conv.session_id);
}

async function deleteSelected() {
  const ids = [...selectedIds.value];
  if (!ids.length) return;
  for (const id of ids) {
    try { await deleteConversation(id); } catch { /* 忽略单条失败 */ }
    visitedSessionIds.delete(id);
    removeSessionCache(id);
  }
  conversations.value = conversations.value.filter(c => !selectedIds.value.has(c.session_id));
  const removedCurrent = !!currentSessionId.value && selectedIds.value.has(currentSessionId.value);
  exitSelection();
  if (removedCurrent) router.push("/");
}

// ── 列表闪烁 ──────────────────────────────────────

const flashedIds = ref<Set<string>>(new Set());

function triggerFlash(sid: string) {
  const next = new Set(flashedIds.value);
  next.add(sid);
  flashedIds.value = next;
  setTimeout(() => {
    const after = new Set(flashedIds.value);
    after.delete(sid);
    flashedIds.value = after;
  }, FLASH_DURATION);
}

// ── 置顶（后端维护 pinned 字段）────────────────────

async function togglePin(id: string) {
  menuOpenId.value = null;
  const conv = conversations.value.find(c => c.session_id === id);
  if (!conv) return;
  try {
    await updateConversation(id, { pinned: !conv.pinned });
    conv.pinned = !conv.pinned;
  } catch {
    // 更新失败，忽略
  }
}

// ── 状态灯颜色映射 ─────────────────────────────────

function statusColor(status: string): string {
  switch (status) {
    case STATUS_GENERATING:  return STATUS_GENERATING;   // 黄色 + 脉冲
    case STATUS_PENDING:     return STATUS_PENDING;      // 红色
    case STATUS_UNKNOWN:     return STATUS_UNKNOWN;      // 灰色
    default:                 return STATUS_IDLE;         // 绿色（completed / idle）
  }
}

function statusTitle(status: string): string {
  switch (status) {
    case STATUS_GENERATING:  return UI_STATUS_GENERATING;
    case STATUS_PENDING:     return UI_STATUS_PENDING;
    case STATUS_UNKNOWN:     return UI_STATUS_UNKNOWN;
    default:                 return UI_STATUS_IDLE;
  }
}

// ── 菜单操作 ─────────────────────────────────────────

function openMenu(id: string) {
  menuOpenId.value = menuOpenId.value === id ? null : id;
}

function closeMenu() {
  menuOpenId.value = null;
}

// ── 会话列表 ─────────────────────────────────────────

async function loadConversations() {
  loading.value = true;
  try {
    const data = await listConversations();
    // 列表不含状态 — 新建/未知会话初始化为 unknown（灰色），等待 SSE 订阅点亮。
    // 已有点亮状态的会话保留现有状态，防止并发 refreshConversationList() 覆盖 SSE 实时推送。
    const existingStatuses = new Map(
      conversations.value.map(c => [c.session_id, c.status])
    );
    conversations.value = data.conversations.map(item => ({
      ...item,
      status: (existingStatuses.get(item.session_id) as SessionStatus) ?? (STATUS_UNKNOWN as SessionStatus),
    }));
  } catch (e) {
    if (isConnectionError(e)) onConnectionLost();
  } finally {
    loading.value = false;
  }
}

async function handleDelete(id: string) {
  menuOpenId.value = null;
  try {
    await deleteConversation(id);
  } catch {
    // 后端删除失败（如 404）时前端仍然清除
  }
  conversations.value = conversations.value.filter((c) => c.session_id !== id);
  // 清理已访问记录（停止 SSE 订阅已删除会话）
  visitedSessionIds.delete(id);
  // 清理本地缓存（useAgent states + draftStore）
  removeSessionCache(id);
  if (currentSessionId.value === id) {
    router.push("/");
  }
}

// ── 内联重命名 ─────────────────────────────────────

function startRename(conv: ConversationInfo) {
  menuOpenId.value = null;
  editingId.value = conv.session_id;
  editTitle.value = conv.title;
}

async function finishRename(conv: ConversationInfo) {
  const newTitle = editTitle.value.trim();
  if (newTitle && newTitle !== conv.title) {
    try {
      await updateConversation(conv.session_id, { title: newTitle });
      conv.title = newTitle;
    } catch {
      // 更新失败，保持原标题
    }
  }
  editingId.value = null;
}

function cancelRename() {
  editingId.value = null;
}

// ── 全局点击关闭菜单 ────────────────────────────────

function onWindowClick(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (!target.closest(".conv-menu-area")) {
    closeMenu();
  }
}

// ── SSE 状态订阅（替代轮询）────────────────────────

const visitedSessionIds = new Set<string>();
let _statusAbort: AbortController | null = null;
let _statusReconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _statusConnectionId = 0;  // 递增版本号，旧连接的回调忽略自身

function connectStatusSSE() {
  if (_statusAbort) _statusAbort.abort();
  if (_statusReconnectTimer) { clearTimeout(_statusReconnectTimer); _statusReconnectTimer = null; }
  _statusAbort = new AbortController();
  const thisConnectionId = ++_statusConnectionId;

  const ids = [...visitedSessionIds];
  if (!ids.length) return;

  subscribeSessionStatus(ids, _statusAbort.signal)
    .then(reader => {
      const decoder = new TextDecoder();
      let buffer = "";
      async function pump() {
        try {
          while (true) {
            const { done, value } = await readWithTimeout(reader, STATUS_READ_TIMEOUT);
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              if (!line.startsWith(SSE_DATA_PREFIX)) continue;
              try {
                const event = JSON.parse(line.slice(SSE_DATA_PREFIX_LEN));
                if (event.type === SSE_STATUS && event.session_id && event.status) {
                  // 忽略哨兵状态（replaced：旧订阅被新连接接管）
                  if (event.status === STATUS_REPLACED) continue;
                  const conv = conversations.value.find(
                    c => c.session_id === event.session_id
                  );
                  if (conv) {
                    const prevStatus = conv.status;
                    conv.status = event.status;
                    if (event.last_access) conv.last_access = event.last_access;
                    // 状态或时间变化 → 重排列表 + 闪烁
                    if (prevStatus !== event.status || event.last_access) {
                      conversations.value = [...conversations.value].sort(
                        (a, b) => b.last_access.localeCompare(a.last_access)
                      );
                      triggerFlash(event.session_id);
                    }
                  }
                }
              } catch { /* 忽略解析错误 */ }
            }
          }
        } catch { /* 连接断开，稍后重连 */ }
        // 仅当前连接才触发重连（被 abort 的旧连接忽略）
        if (_statusConnectionId === thisConnectionId) {
          scheduleStatusReconnect();
        }
      }
      pump();
    })
    .catch(() => {
      if (_statusConnectionId === thisConnectionId) {
        scheduleStatusReconnect();
      }
    });
}

let _statusReconnectDelay = STATUS_RECONNECT_INIT;
function scheduleStatusReconnect() {
  if (_statusReconnectTimer) clearTimeout(_statusReconnectTimer);
  _statusReconnectTimer = setTimeout(() => {
    _statusReconnectDelay = Math.min(_statusReconnectDelay * 2, STATUS_RECONNECT_MAX);
    connectStatusSSE();
  }, _statusReconnectDelay);
}

function disconnectStatusSSE() {
  if (_statusAbort) { _statusAbort.abort(); _statusAbort = null; }
  if (_statusReconnectTimer) { clearTimeout(_statusReconnectTimer); _statusReconnectTimer = null; }
}

function trackVisitedSession(sid: string | null) {
  if (!sid) return;
  if (!visitedSessionIds.has(sid)) {
    visitedSessionIds.add(sid);
    _statusReconnectDelay = STATUS_RECONNECT_INIT;
    connectStatusSSE();
  }
}

onMounted(() => {
  // 同步会话列表 → 订阅已访问会话的状态 SSE。
  // 若后端不可达 → loadConversations 失败 → onConnectionLost 占屏。
  loadConversations().then(() => {
    // 订阅空序列：仅当用户实际访问会话时才添加到 visited 集合并订阅
    // 当前路由已有会话（如直接访问 /chat/xxx）→ 标记并订阅
    if (currentSessionId.value) {
      visitedSessionIds.add(currentSessionId.value);
      connectStatusSSE();
    }
    // 否则保持空订阅，等待用户点击会话触发 trackVisitedSession
  });
  window.addEventListener("click", onWindowClick);
  window.addEventListener("resize", updateActiveFrame);
});

onUnmounted(() => {
  disconnectStatusSSE();
  window.removeEventListener("resize", updateActiveFrame);
});

// 切换会话时清理 + 标记已访问
watch(() => route.params.sessionId, (sid) => {
  closeMenu();
  if (sid && typeof sid === "string") trackVisitedSession(sid);
});

// ── 按日期分组（置顶优先）───────────────────────────

interface ConvGroup {
  label: string;
  items: ConversationInfo[];
}

const groupedConversations = computed<ConvGroup[]>(() => {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - DAY_MS);
  const weekAgo = new Date(today.getTime() - GROUP_WEEK_DAYS * DAY_MS);
  const monthAgo = new Date(today.getTime() - GROUP_MONTH_DAYS * DAY_MS);

  const groups: Record<string, ConvGroup> = {};
  const pinned: ConversationInfo[] = [];
  const normal: ConversationInfo[] = [];

  for (const c of conversations.value) {
    if (c.pinned) {
      pinned.push(c);
    } else {
      normal.push(c);
    }
  }

  // 非置顶按日期分组
  for (const c of normal) {
    const d = new Date(c.last_access || c.created_at);
    let key: string;
    if (d >= today) {
      key = UI_TODAY;
    } else if (d >= yesterday) {
      key = UI_YESTERDAY;
    } else if (d >= weekAgo) {
      key = UI_WITHIN_WEEK;
    } else if (d >= monthAgo) {
      key = UI_WITHIN_MONTH;
    } else {
      key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    }
    if (!groups[key]) groups[key] = { label: key, items: [] };
    groups[key].items.push(c);
  }

  // 排序：今天 → 昨天 → 7天内 → 30天内 → 月份降序
  const order = Object.entries(groups).sort((a, b) => {
    const aIsMonth = /^\d{4}-\d{2}$/.test(a[0]);
    const bIsMonth = /^\d{4}-\d{2}$/.test(b[0]);
    if (aIsMonth && bIsMonth) return b[0].localeCompare(a[0]);
    if (aIsMonth) return 1;
    if (bIsMonth) return -1;
    const keys = [UI_TODAY, UI_YESTERDAY, UI_WITHIN_WEEK, UI_WITHIN_MONTH];
    return keys.indexOf(a[0]) - keys.indexOf(b[0]);
  });

  const result: ConvGroup[] = [];

  // 置顶组放最前面
  if (pinned.length) {
    result.push({ label: UI_PINNED_GROUP, items: pinned });
  }

  for (const [, g] of order) {
    result.push(g);
  }

  return result;
});

defineExpose({ refresh: loadConversations });

// ── 清空 / 清理 ─────────────────────────────────────

/** 仅当存在至少一条会话时显示"清空"（进入多选删除模式） */
const showClearAll = computed(() => conversations.value.length > 0);

// ── 活动会话高亮滑动框 ───────────────────────────

const listEl = ref<HTMLElement | null>(null);
const frameEl = ref<HTMLElement | null>(null);
const frameStyle = ref<Record<string, string>>({ opacity: "0" });

let _frameReady = false;
let _frameTop = 0;

async function updateActiveFrame(): Promise<void> {
  await nextTick();
  const list = listEl.value;
  const el = frameEl.value;
  if (!list || !el) return;

  const active = list.querySelector<HTMLElement>(".conv-item.active");
  if (!active) {
    frameStyle.value = { opacity: "0" };
    _frameReady = false;
    return;
  }

  const listRect = list.getBoundingClientRect();
  const rect = active.getBoundingClientRect();
  const top = rect.top - listRect.top;
  const left = rect.left - listRect.left;
  const changed = Math.abs(top - _frameTop) > 1;
  const direction = top >= _frameTop ? 1 : -1;

  frameStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    opacity: "1",
  };

  if (!_frameReady) {
    // 首次定位不做动画，避免从 0,0 滑入
    el.classList.add("no-anim");
    requestAnimationFrame(() => el.classList.remove("no-anim"));
  } else if (changed) {
    // 移动中沿方向拉伸，到位弹性回弹
    el.getAnimations().forEach(a => a.cancel());
    el.animate(
      [
        { transform: "scaleY(1)", transformOrigin: direction > 0 ? "top" : "bottom" },
        { transform: "scaleY(1.06)", offset: 0.45 },
        { transform: "scaleY(1)" },
      ],
      { duration: 320, easing: "cubic-bezier(0.22, 1.12, 0.36, 1)" },
    );
  }

  _frameTop = top;
  _frameReady = true;
}

watch(
  [currentSessionId, () => conversations.value.length, () => groupedConversations.value],
  () => { void updateActiveFrame(); },
  { flush: "post" },
);

</script>

<template>
  <FloatingWindow
    width="320px"
    position="top-left"
    :title="UI_SESSION_LIST"
    icon="fa-solid fa-bars"
    :morph-from="morphOrigin"
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <template #actions>
      <button
        v-if="showClearAll && !selecting"
        class="btn-action danger"
        :title="UI_CLEAR_ALL"
        :aria-label="UI_CLEAR_ALL"
        @click.stop="enterSelection"
      >
        <i class="fa-solid fa-trash-can"></i>
      </button>
    </template>

    <template v-if="selecting" #footer>
      <div class="selection-bar">
        <span class="selection-count">{{ UI_SELECTED_PREFIX }} {{ selectedCount }} {{ UI_ITEM_UNIT }}</span>
        <button class="selection-btn" @click="toggleSelectAll">
          {{ allSelected ? UI_DESELECT_ALL : UI_SELECT_ALL }}
        </button>
        <button class="selection-btn" @click="exitSelection">{{ UI_CANCEL }}</button>
        <button
          class="selection-btn danger"
          :disabled="selectedCount === 0"
          @click="deleteSelected"
        >
          <i class="fa-solid fa-trash"></i> {{ UI_DELETE }}
        </button>
      </div>
    </template>

    <!-- Conversations -->
    <div class="cl-section">
      <button class="btn-new-chat" @click="router.push('/')">
        <i class="fa-solid fa-plus"></i> {{ UI_NEW_CHAT }}
      </button>
      <div ref="listEl" class="conv-list">
        <span
          v-if="!selecting"
          ref="frameEl"
          class="conv-active-frame"
          :style="frameStyle"
          aria-hidden="true"
        ></span>
        <!-- 加载中 -->
        <div v-if="loading" class="empty">{{ UI_LOADING }}</div>

        <!-- 按日期分组 -->
        <template v-for="group in groupedConversations" :key="group.label">
          <div class="group-label">{{ group.label }}</div>
          <div
            v-for="(conv, idx) in group.items"
            :key="conv.session_id"
            class="conv-item"
            :style="{ '--i': idx }"
            :class="{ active: conv.session_id === currentSessionId, flash: flashedIds.has(conv.session_id), selecting }"
            @click="onItemClick(conv)"
            @mousedown.middle.prevent="!selecting && handleDelete(conv.session_id)"
          >
            <template v-if="editingId === conv.session_id">
              <input
                v-model="editTitle"
                class="rename-input"
                @keyup.enter="finishRename(conv)"
                @keyup.escape="cancelRename"
                @blur="finishRename(conv)"
                @click.stop
                autofocus
              />
            </template>
            <template v-else>
              <div class="conv-info">
                <span v-if="selecting" class="conv-check" :class="{ on: selectedIds.has(conv.session_id) }" aria-hidden="true">
                  <i class="fa-solid fa-check"></i>
                </span>
                <i
                  class="conv-status-dot"
                  :class="statusColor(conv.status)"
                  :title="statusTitle(conv.status)"
                  role="img"
                  :aria-label="statusTitle(conv.status)"
                ></i>
                <i v-if="conv.pinned" class="pin-indicator fa-solid fa-thumbtack"></i>
                <span class="conv-title" @dblclick.stop="!selecting && startRename(conv)">
                  {{ conv.title }}
                </span>
              </div>
              <div v-if="!selecting" class="conv-menu-area">
                <button
                  class="btn-menu"
                  :class="{ open: menuOpenId === conv.session_id }"
                  @click.stop="openMenu(conv.session_id)"
                  :title="UI_MORE"
                  :aria-label="UI_MORE"
                  aria-haspopup="menu"
                  :aria-expanded="menuOpenId === conv.session_id"
                >
                  <i class="fa-solid fa-ellipsis"></i>
                </button>
                <div v-if="menuOpenId === conv.session_id" class="context-menu" @click.stop>
                  <button class="context-item" @click="togglePin(conv.session_id)">
                    <i class="fa-solid fa-thumbtack"></i>
                    {{ conv.pinned ? UI_UNPIN : UI_PIN }}
                  </button>
                  <button class="context-item" @click="startRename(conv)">
                    <i class="fa-solid fa-pen"></i> {{ UI_RENAME }}
                  </button>
                  <button class="context-item danger" @click="handleDelete(conv.session_id)">
                    <i class="fa-solid fa-trash"></i> {{ UI_DELETE }}
                  </button>
                </div>
              </div>
            </template>
          </div>
        </template>

        <div v-if="!loading && !conversations.length" class="empty">
          {{ UI_NO_CONVERSATIONS }}
        </div>
      </div>
    </div>
  </FloatingWindow>
</template>

<style scoped>
/* ── 会话列表浮窗 ──────────────────────────────── */

.cl-section {
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: 60vh;
  overflow-y: auto;
}

.btn-new-chat {
  width: 100%;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--accent);
  color: var(--white);
  border: none;
  border-radius: var(--radius);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 8px;
}

.btn-new-chat:hover {
  background: var(--accent-hover);
}

.conv-list {
  position: relative;
}

/* 活动会话高亮框：滑动 + 拉伸回弹 + 细高光边 */
.conv-active-frame {
  position: absolute;
  z-index: 0;
  pointer-events: none;
  border-radius: var(--radius);
  /* Tint 玻璃：活动会话条目 = 彩色玻璃卡片 */
  background: color-mix(in srgb, var(--accent-bg) 72%, var(--glass-bg));
  border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
  box-shadow:
    inset 0 1px 0 var(--glass-highlight),
    inset 0 0 0 1px var(--glass-rim-inner),
    0 0 14px var(--accent-shadow);
  transition:
    top 0.34s cubic-bezier(0.22, 1.12, 0.36, 1),
    left 0.34s cubic-bezier(0.22, 1.12, 0.36, 1),
    width 0.34s cubic-bezier(0.22, 1.12, 0.36, 1),
    height 0.34s cubic-bezier(0.22, 1.12, 0.36, 1),
    opacity 0.18s ease;
}

.conv-active-frame.no-anim {
  transition: none !important;
}

.group-label {
  position: relative;
  z-index: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-dim);
  padding: 10px 4px 4px;
}

.conv-item {
  position: relative;
  z-index: 1;
  animation: conv-in 0.25s ease both;
  animation-delay: calc(min(var(--i, 0), 12) * 30ms);
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  margin-bottom: 2px;
}

.conv-item:hover {
  background: var(--bg-hover);
}

.conv-item.active {
  /* 背景与描边由 .conv-active-frame 统一绘制 */
  background: transparent;
  border: 1px solid transparent;
}

.conv-item.flash {
  animation: flash-highlight 0.8s ease;
}
@keyframes flash-highlight {
  0%, 100% { background: transparent; }
  50% { background: var(--accent-shadow); }
}

.conv-check {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: transparent;
  font-size: 9px;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}

.conv-check.on {
  color: var(--white);
  background: var(--accent);
  border-color: var(--accent);
}

.selection-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selection-count {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.selection-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}

.selection-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--text-dim);
}

.selection-btn.danger {
  color: var(--error);
  border-color: var(--error);
}

.selection-btn.danger:hover {
  background: var(--error-bg-hover);
}

.selection-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.conv-info {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.conv-status-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  background: var(--success);
}
.conv-status-dot.idle        { background: var(--success); }                              /* 绿色 — 可发送 */
.conv-status-dot.generating  {
  background: var(--status-generating);
  animation: pulse-dot 1.2s infinite;
  box-shadow: 0 0 6px var(--status-generating);
}

@keyframes conv-in {
  from { opacity: 0; translate: 0 4px; }
  to   { opacity: 1; translate: 0 0; }
}
.conv-status-dot.pending     { background: var(--status-pending); }
.conv-status-dot.unknown     { background: var(--status-unknown); }
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.pin-indicator {
  font-size: 12px;
  color: var(--accent);
  flex-shrink: 0;
}

.conv-title {
  display: block;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* ── 三点菜单按钮 ────────────────────────────────── */

.conv-menu-area {
  position: relative;
  flex-shrink: 0;
}

.btn-menu {
  background: none;
  color: var(--text-dim);
  font-size: 14px;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  opacity: 0;
  padding: 0;
}

.conv-item:hover .btn-menu,
.btn-menu.open {
  opacity: 1;
}

.btn-menu:hover,
.btn-menu.open {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* ── 右键下拉菜单 ────────────────────────────────── */

.context-menu {
  position: absolute;
  bottom: 0;
  right: 100%;
  z-index: 100;
  min-width: 130px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 16px var(--shadow-sm);
  padding: 4px;
  margin-right: 4px;
}

.context-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-align: left;
}

.context-item:hover {
  background: var(--bg-hover);
}

.context-item.danger {
  color: var(--error);
}

.context-item.danger:hover {
  background: var(--error-bg-hover);
}

/* ── 内联重命名输入框 ────────────────────────────── */

.rename-input {
  flex: 1;
  background: var(--bg-primary);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

/* ── 空状态 / 加载 ───────────────────────────────── */

.empty {
  font-size: 14px;
  color: var(--text-dim);
  text-align: center;
  padding: 12px;
}

/* ── 头部操作按钮 ───────────────────────────────── */

.btn-action {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: var(--radius-sm);
  color: var(--text-dim); font-size: 13px; cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.btn-action:hover { color: var(--text-secondary); background: var(--bg-hover); }
.btn-action.confirm { color: var(--accent); background: var(--accent-bg); }
.btn-action.danger.confirm { color: var(--error); background: var(--error-bg); }

</style>
