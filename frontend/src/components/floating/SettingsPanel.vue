<script setup lang="ts">
import { ref, computed, watch, inject, onUnmounted } from "vue";
import FloatingWindow from "./FloatingWindow.vue";
import { getLLMConfig, getHealth, updateLLMConfig, getConcurrencyConfig, getMCPConfig, updateMCPConfig, getSecrets, updateSecrets, getVersionInfo, getServerUrl, setServerUrl, isConnectionError, getRuntimeStatus, getMCPStatus, getDefaultSessionSettings, updateDefaultSessionSettings } from "../../api/client";
import { DEFAULT_MAX_CONCURRENT, MAX_CONCURRENT_UPPER, FACTORY_SESSION_DEFAULTS, HEALTH_STATUS_LABEL, MCP_STATUS_LABEL, UI_CLEAR, UI_CLOSE, UI_SAVE, UI_SAVING, UI_SAVE_FAILED, UI_DEFAULT, UI_REFRESH, UI_TAB_SERVER, UI_TAB_LLM, UI_TAB_MCP, UI_TAB_SECRETS, UI_TAB_DEFAULTS, UI_TAB_ABOUT, UI_SERVER_ADDRESS, UI_MCP_SERVERS, UI_LLM_GATEWAY, UI_STATUS_LABEL, UI_UNCONFIGURED, UI_FETCH_FAILED, UI_NO_MCP_SERVERS, UI_MCP_CONFIG_DESC, UI_CONCURRENCY_LIMIT, UI_RUNTIME_INFO, UI_GATEWAY_URL, UI_MODEL_LABEL, UI_AUTH_TOKEN, UI_MAX_CONCURRENT_LABEL, UI_SECRETS_VARS, UI_SECRETS_DESC, UI_ADD_VARIABLE, UI_KEEP_UNCHANGED, UI_ENTER_SECRET_VALUE } from "../../constants";
import { ON_CONNECTION_LOST_KEY, REFRESH_DEFAULT_SETTINGS_KEY } from "../../composables/injectionKeys";
import { discoverTools as refreshTools } from "../../composables/toolMetadata";
import type { LLMConfig, HealthResult, VersionInfo, RuntimeStatus, MCPStatusResult } from "../../types/api";

interface SavedSettings {
  base_url?: string;
  model?: string;
  auth_token?: string;
  max_concurrent?: number;
}

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  close: [];
  update: [config: { model: string }];
}>();

const onConnectionLost = inject(ON_CONNECTION_LOST_KEY, () => {});
const refreshDefaultSettings = inject(REFRESH_DEFAULT_SETTINGS_KEY, async () => {});

// ── 标签页 ────────────────────────────────────────

interface Tab { id: string; label: string; icon: string; }

const tabs: Tab[] = [
  { id: "server", label: UI_TAB_SERVER, icon: "fa-solid fa-server" },
  { id: "llm", label: UI_TAB_LLM, icon: "fa-solid fa-microchip" },
  { id: "mcp", label: UI_TAB_MCP, icon: "fa-solid fa-plug" },
  { id: "secrets", label: UI_TAB_SECRETS, icon: "fa-solid fa-key" },
  { id: "defaults", label: UI_TAB_DEFAULTS, icon: "fa-solid fa-sliders" },
  { id: "about", label: UI_TAB_ABOUT, icon: "fa-solid fa-circle-info" },
];

const activeTab = ref("server");

const serverUrl = ref(getServerUrl());

// ── 表单状态 ──────────────────────────────────────

const config = ref<LLMConfig | null>(null);
const health = ref<HealthResult | null>(null);
const verInfo = ref<VersionInfo | null>(null);

// ── 服务器状态监控 ────────────────────────────────
const runtime = ref<RuntimeStatus | null>(null);
const mcpStatus = ref<MCPStatusResult | null>(null);
const baseUrl = ref("");
const model = ref("");
const authToken = ref("");
const maxConcurrent = ref(DEFAULT_MAX_CONCURRENT);
const mcpJson = ref("");
const mcpJsonError = computed(() => {
  const t = mcpJson.value.trim();
  if (!t) return null;
  try {
    const data = JSON.parse(t);
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      return "配置必须是 JSON 对象";
    }
    if (!data.mcpServers || typeof data.mcpServers !== "object" || Array.isArray(data.mcpServers)) {
      return "缺少 \"mcpServers\" 对象";
    }
    return null;
  } catch (e) {
    const msg = e instanceof SyntaxError ? e.message : String(e);
    return `JSON 语法错误: ${msg}`;
  }
});

interface SecretRow { key: string; value: string; _show?: boolean }
const secretRows = ref<SecretRow[]>([]);
const secretExisting = ref<Set<string>>(new Set());  // 加载时已存在的 key 集合

const saving = ref(false);

// ── 会话默认设定 ──────────────────────────────────

const defaultSettings = ref<Record<string, any>>({});
const defaultSettingsLoaded = ref(false);

async function loadDefaultSettings() {
  try {
    defaultSettings.value = await getDefaultSessionSettings() as any;
    defaultSettingsLoaded.value = true;
  } catch { /* ignore */ }
}

const _DEF_RANGES: Record<string, { min: number; max: number }> = {
  temperature: { min: 0, max: 2 },
  max_tokens: { min: 1, max: 32768 },
  top_p: { min: 0, max: 1 },
  top_k: { min: 1, max: 200 },
  presence_penalty: { min: -2, max: 2 },
  frequency_penalty: { min: -2, max: 2 },
  repeat_penalty: { min: 0, max: 2 },
};

function validateDefaultSettings(): string | null {
  const s = defaultSettings.value;
  for (const [key, r] of Object.entries(_DEF_RANGES)) {
    const v = s[key];
    if (v != null && (typeof v !== "number" || isNaN(v) || v < r.min || v > r.max)) {
      return `${key} 值须在 ${r.min}–${r.max} 之间`;
    }
  }
  return null;
}

async function saveDefaultSettings() {
  const err = validateDefaultSettings();
  if (err) { saveError.value = err; return; }
  try {
    const result = await updateDefaultSessionSettings(defaultSettings.value);
    defaultSettings.value = result as any;
  } catch { /* ignore */ }
}

function defSet(key: string) {
  defaultSettings.value[key] = (FACTORY_SESSION_DEFAULTS as any)[key] ?? "";
}

const saveError = ref("");

// ── MCP 热重载轮询 ──────────────────────────────

const MCP_POLL_MS = 1000;
const MCP_POLL_MAX = 20;           // 最多 20s
const MCP_STABLE_COUNT = 2;        // 连续 N 次状态不变即认为稳定

const mcpReloading = ref(false);
let mcpPollTimer: ReturnType<typeof setInterval> | null = null;

function stopMCPPolling() {
  if (mcpPollTimer !== null) {
    clearInterval(mcpPollTimer);
    mcpPollTimer = null;
  }
  mcpReloading.value = false;
}

/** 后台轮询 MCP 服务器状态，待稳定后刷新工具列表。 */
function startMCPReloadPolling() {
  // 无配置 → 直接刷新工具（清空旧 MCP 工具）
  const trimmed = mcpJson.value.trim();
  if (!trimmed) {
    refreshTools();
    return;
  }

  stopMCPPolling();
  mcpReloading.value = true;

  let polls = 0;
  let lastSnapshot = "";

  mcpPollTimer = setInterval(async () => {
    polls++;
    try {
      const status = await getMCPStatus();
      mcpStatus.value = status;

      const snapshot = JSON.stringify(status.servers);

      // 稳定性检测：连续 N 次不变 → 重载完成
      if (snapshot === lastSnapshot) {
        if (polls >= MCP_STABLE_COUNT + 1) {
          // 已稳定 N 次
          stopMCPPolling();
          refreshTools();
          return;
        }
      } else {
        lastSnapshot = snapshot;
        polls = 1;  // 重置，从当前状态开始计数
      }

      if (polls >= MCP_POLL_MAX) {
        stopMCPPolling();
        refreshTools();
      }
    } catch {
      // 单次轮询失败不影响大局，继续直到上限
      if (polls >= MCP_POLL_MAX) {
        stopMCPPolling();
        refreshTools();
      }
    }
  }, MCP_POLL_MS);
}

onUnmounted(() => stopMCPPolling());

function applyConfig(cfg: LLMConfig | null) {
  baseUrl.value = cfg?.base_url || "";
  model.value = cfg?.default_model || "";
  authToken.value = cfg?.auth_token || "";
}

/** 格式化秒数为可读的运行时间。 */
function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join(" ");
}

/** 拉取服务器状态数据（仅面板打开时手动触发）。每个端点独立 try/catch，互不影响。 */
async function refreshServerStatus() {
  try { runtime.value = await getRuntimeStatus(); } catch { /* ignore */ }
  try { health.value = await getHealth(); } catch { /* ignore */ }
  try { mcpStatus.value = await getMCPStatus(); } catch { /* ignore */ }
}

async function refresh() {
  saveError.value = "";
  try { config.value = await getLLMConfig(); applyConfig(config.value); } catch { /* ignore */ }
  try { const cc = await getConcurrencyConfig(); maxConcurrent.value = cc.max_concurrent; } catch { /* ignore */ }
  try { verInfo.value = await getVersionInfo(); } catch { /* ignore */ }
  try { const mc = await getMCPConfig(); mcpJson.value = mc.config ?? ""; } catch { /* ignore */ }
  try {
    const s = await getSecrets();
    secretRows.value = s.keys.map(k => ({ key: k, value: "", _show: false }));
    secretExisting.value = new Set(s.keys);
  } catch { /* ignore */ }
  loadDefaultSettings();
  // 服务器标签页状态一并拉取
  if (activeTab.value === "server") refreshServerStatus();
}

// FloatingWindow 只隐藏不销毁 → 每次打开时刷新数据
watch(() => props.modelValue, (v) => { if (v) refresh(); });

async function save() {
  saving.value = true;
  saveError.value = "";

  // 持久化服务器地址
  setServerUrl(serverUrl.value);

  const settings: SavedSettings = {
    base_url: baseUrl.value.trim() || undefined,
    model: model.value.trim() || undefined,
    auth_token: authToken.value || undefined,
    max_concurrent: maxConcurrent.value,
  };

  try {
    await updateLLMConfig({
      base_url: settings.base_url || null,
      model: settings.model || null,
      auth_token: settings.auth_token || null,
      max_concurrent: settings.max_concurrent ?? null,
    });
    await updateMCPConfig(mcpJson.value);
    // 后台轮询 MCP 状态，稳定后自动刷新工具列表
    startMCPReloadPolling();

    // 保存密钥
    const secretMap: Record<string, string | null> = {};
    const currentKeys = new Set<string>();
    for (const r of secretRows.value) {
      const k = r.key.trim();
      if (!k) continue;
      currentKeys.add(k);
      if (r.value) {
        secretMap[k] = r.value;           // 非空 → 更新
      }
      // 空值 + existing → 省略，保持原值
    }
    // 被用户删除的 key（存在于旧列表但不在新列表中）
    for (const k of secretExisting.value) {
      if (!currentKeys.has(k)) secretMap[k] = null;
    }
    await updateSecrets(secretMap);
    secretExisting.value = currentKeys;

    // 保存默认会话设定
    try { await saveDefaultSettings(); } catch { /* ignore */ }
    refreshDefaultSettings();  // 通知 useAgent 刷新默认设定

    // 保存后从后端拉取实际值（后端是唯一权威源）
    try {
      config.value = await getLLMConfig();
      applyConfig(config.value);
      emit("update", { model: model.value });
    } catch { /* ignore */ }
    try { await refreshServerStatus(); } catch { /* ignore */ }
  } catch (e) {
    if (isConnectionError(e)) {
      onConnectionLost();
    } else {
      saveError.value = (e as Error).message || "保存失败";
    }
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <FloatingWindow
    width="540px"
    position="top-right"
    title="设置"
    icon="fa-solid fa-gear"
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <div class="settings-layout">
      <!-- 左侧标签栏 -->
      <nav class="tab-nav">
        <button
          v-for="tab in tabs" :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <i :class="tab.icon"></i>
          <span>{{ tab.label }}</span>
        </button>
        <div class="tab-nav-spacer"></div>
        <div class="tab-nav-actions">
          <div v-if="saveError" class="save-error">{{ saveError }}</div>
          <button class="tab-nav-save" :disabled="saving" @click="save">
            {{ saving ? "保存中…" : "保存" }}
          </button>
        </div>
      </nav>

      <!-- 右侧设置面板 -->
      <div class="tab-content">
        <!-- 服务器 -->
        <template v-if="activeTab === 'server'">
          <!-- 服务器地址 -->
          <div class="section">
            <label class="label">服务器地址</label>
            <div class="server-url-row">
              <input v-model="serverUrl" class="input" placeholder="http://localhost:8000" />
              <button class="btn-refresh" @click="refreshServerStatus" title="刷新状态">
                <i class="fa-solid fa-rotate"></i>
              </button>
            </div>
          </div>

          <!-- MCP 服务器 -->
          <div v-if="mcpStatus" class="section status-list">
            <div class="label-row">
              <label class="label">MCP 服务器</label>
              <span v-if="mcpReloading" class="reloading-indicator">
                <i class="fa-solid fa-spinner fa-spin-pulse"></i> 重连中…
              </span>
            </div>
            <template v-if="Object.keys(mcpStatus.servers).length">
              <div v-for="(status, name) in mcpStatus.servers" :key="name" class="info-row">
                <span class="info-key">{{ name }}</span>
                <span class="info-value" :class="status === 'running' ? 'ok' : status === 'stopped' ? 'warn' : 'err'">
                  <i class="fa-solid fa-circle"></i> {{ MCP_STATUS_LABEL[status] || status }}
                </span>
              </div>
            </template>
            <p v-else class="status-na">未配置 MCP 服务器</p>
          </div>
          <div v-else class="section status-list">
            <label class="label">MCP 服务器</label>
            <p class="status-na">获取失败</p>
          </div>

          <!-- LLM 网关 -->
          <div v-if="health" class="section status-list">
            <label class="label">LLM 网关</label>
            <div class="info-row">
              <span class="info-key">状态</span>
              <span class="info-value" :class="health.status === 'healthy' ? 'ok' : health.status === 'no_default_model' ? 'warn' : 'err'">
                <i :class="health.status === 'healthy' ? 'fa-solid fa-circle' : 'fa-solid fa-circle-exclamation'"></i>
                {{ HEALTH_STATUS_LABEL[health.status] || health.status }}
              </span>
            </div>
            <div class="info-row"><span class="info-key">地址</span><span class="info-value mono">{{ health.base_url }}</span></div>
            <div class="info-row"><span class="info-key">模型</span><span class="info-value mono">{{ health.default_model || UI_UNCONFIGURED }}</span></div>
            <div v-if="health.error" class="info-row">
              <span class="info-key">错误</span><span class="info-value err">{{ health.error }}</span>
            </div>
          </div>
          <div v-else class="section status-list">
            <label class="label">LLM 网关</label>
            <p class="status-na">获取失败</p>
          </div>

          <!-- 并发限制 -->
          <div class="section status-list">
            <label class="label">并发限制</label>
            <div class="info-row"><span class="info-key">最大并发生成</span><span class="info-value mono">{{ maxConcurrent }}</span></div>
          </div>

          <!-- 运行信息 -->
          <div v-if="runtime" class="section status-list">
            <label class="label">运行信息</label>
            <div class="info-row"><span class="info-key">运行时间</span><span class="info-value">{{ formatUptime(runtime.uptime_seconds) }}</span></div>
            <div class="info-row"><span class="info-key">Python</span><span class="info-value mono">{{ runtime.python_version }}</span></div>
            <div class="info-row"><span class="info-key">平台</span><span class="info-value mono">{{ runtime.platform }}</span></div>
          </div>
          <div v-else class="section status-list">
            <label class="label">运行信息</label>
            <p class="status-na">获取失败</p>
          </div>
        </template>

        <!-- LLM -->
        <template v-if="activeTab === 'llm'">
          <div class="section">
            <label class="label">网关地址 (base_url)</label>
            <input v-model="baseUrl" class="input" placeholder="http://127.0.0.1:1234" />
          </div>
          <div class="section">
            <label class="label">模型 (model)</label>
            <input v-model="model" class="input" placeholder="model-id" />
          </div>
          <div class="section">
            <label class="label">认证令牌 (auth_token)</label>
            <input v-model="authToken" class="input" placeholder="支持 ${变量名}" />
          </div>
          <div class="section">
            <label class="label">最大并发生成</label>
            <p class="desc">同一时间最多允许的 LLM 生成任务数（{{ DEFAULT_MAX_CONCURRENT }}–{{ MAX_CONCURRENT_UPPER }}）。</p>
            <input
              v-model.number="maxConcurrent" class="input"
              type="number" :min="DEFAULT_MAX_CONCURRENT" :max="MAX_CONCURRENT_UPPER"
            />
          </div>
        </template>

        <!-- MCP -->
        <template v-if="activeTab === 'mcp'">
          <div class="section">
            <label class="label">MCP 服务器配置</label>
            <p class="desc">
              标准 MCP 协议（JSON 格式），支持 stdio 子进程和 HTTP 远程连接。
              使用 <code>${"${变量名}"}</code> 引用 <a href="#" @click.prevent="activeTab = 'secrets'">密钥变量</a>。
            </p>
          </div>
          <div class="section mcp-editor-section">
            <textarea
              v-model="mcpJson"
              class="mcp-editor"
              :class="{ 'has-error': mcpJsonError }"
              spellcheck="false"
              autocomplete="off"
              placeholder='{"mcpServers": {}}'
            ></textarea>
            <p v-if="mcpJsonError" class="mcp-error">
              <i class="fa-solid fa-circle-exclamation"></i> {{ mcpJsonError }}
            </p>
          </div>
        </template>

        <!-- 密钥 -->
        <template v-if="activeTab === 'secrets'">
          <div class="section">
            <label class="label">密钥变量</label>
            <p class="desc">
              在 LLM、MCP 配置中使用 <code>${变量名}</code> 引用密钥，实际请求时将自动替换。
            </p>
          </div>
          <div class="section secrets-list">
            <div v-for="(r, i) in secretRows" :key="i" class="secrets-row">
              <input v-model="r.key" class="input secrets-key" placeholder="变量名" />
              <div class="secrets-value-wrap">
                <input
                  v-model="r.value"
                  class="input secrets-value"
                  :type="r._show ? 'text' : 'password'"
                  :placeholder="secretExisting.has(r.key.trim()) ? '留空保持不变' : '输入密钥值'"
                />
                <button class="secrets-toggle" @click="r._show = !r._show">
                  <i :class="r._show ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye'"></i>
                </button>
              </div>
              <button class="secrets-remove" @click="secretRows.splice(i, 1)">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
            <button class="secrets-add" @click="secretRows.push({ key: '', value: '', _show: false })">
              <i class="fa-solid fa-plus"></i> 添加变量
            </button>
          </div>
        </template>

        <!-- 会话默认设定 -->
        <template v-if="activeTab === 'defaults'">
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              系统提示词
              <button v-if="defaultSettings.system_prompt != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.system_prompt = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <div v-if="defaultSettings.system_prompt == null" class="unset-placeholder" @click="defSet('system_prompt')">点击设置</div>
            <textarea v-else v-model="defaultSettings.system_prompt" class="input area" rows="4" />
          </div>
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              温度 <code>{{ defaultSettings.temperature != null ? defaultSettings.temperature.toFixed(2) : '默认' }}</code>
              <button v-if="defaultSettings.temperature != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.temperature = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">较高的值（如 0.9）使输出更随机，较低的值（如 0.2）使输出更确定。</p>
            <div v-if="defaultSettings.temperature == null" class="unset-placeholder" @click="defSet('temperature')">点击设置</div>
            <input v-else type="range" min="0" max="2" step="0.05" v-model.number="defaultSettings.temperature" class="range" />
          </div>
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              最大输出 Token <code>{{ defaultSettings.max_tokens ?? '默认' }}</code>
              <button v-if="defaultSettings.max_tokens != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.max_tokens = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">单次生成允许的最大 token 数，范围 1–32768。</p>
            <div v-if="defaultSettings.max_tokens == null" class="unset-placeholder" @click="defSet('max_tokens')">点击设置</div>
            <input v-else type="number" min="1" max="32768" step="256" v-model.number="defaultSettings.max_tokens" class="input" />
          </div>
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              核采样 Top-P <code>{{ defaultSettings.top_p != null ? defaultSettings.top_p.toFixed(2) : '默认' }}</code>
              <button v-if="defaultSettings.top_p != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.top_p = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">仅考虑概率质量累积到此值内的 token，0 = 不限制。</p>
            <div v-if="defaultSettings.top_p == null" class="unset-placeholder" @click="defSet('top_p')">点击设置</div>
            <input v-else type="range" min="0" max="1" step="0.05" v-model.number="defaultSettings.top_p" class="range" />
          </div>
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              Top-K <code>{{ defaultSettings.top_k ?? '默认' }}</code>
              <button v-if="defaultSettings.top_k != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.top_k = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">仅从概率最高的 K 个 token 中采样，空白 = 不限制。</p>
            <div v-if="defaultSettings.top_k == null" class="unset-placeholder" @click="defSet('top_k')">点击设置</div>
            <input v-else type="number" min="1" max="200" step="1" v-model.number="defaultSettings.top_k" class="input" />
          </div>
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              存在惩罚 <code>{{ defaultSettings.presence_penalty != null ? defaultSettings.presence_penalty.toFixed(2) : '默认' }}</code>
              <button v-if="defaultSettings.presence_penalty != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.presence_penalty = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">正值惩罚已出现过的 token，鼓励模型谈论新话题。</p>
            <div v-if="defaultSettings.presence_penalty == null" class="unset-placeholder" @click="defSet('presence_penalty')">点击设置</div>
            <input v-else type="range" min="-2" max="2" step="0.1" v-model.number="defaultSettings.presence_penalty" class="range" />
          </div>
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              频率惩罚 <code>{{ defaultSettings.frequency_penalty != null ? defaultSettings.frequency_penalty.toFixed(2) : '默认' }}</code>
              <button v-if="defaultSettings.frequency_penalty != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.frequency_penalty = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">正值按 token 频率等比惩罚，降低重复词语。</p>
            <div v-if="defaultSettings.frequency_penalty == null" class="unset-placeholder" @click="defSet('frequency_penalty')">点击设置</div>
            <input v-else type="range" min="-2" max="2" step="0.1" v-model.number="defaultSettings.frequency_penalty" class="range" />
          </div>
          <div v-if="defaultSettingsLoaded" class="section">
            <label class="label">
              重复惩罚 <code>{{ defaultSettings.repeat_penalty != null ? defaultSettings.repeat_penalty.toFixed(2) : '默认' }}</code>
              <button v-if="defaultSettings.repeat_penalty != null" class="clear-btn" :title="UI_CLEAR" @click="defaultSettings.repeat_penalty = null"><i class="fa-solid fa-xmark"></i></button>
            </label>
            <p class="desc">惩罚重复的 token 序列，值越高惩罚越强。</p>
            <div v-if="defaultSettings.repeat_penalty == null" class="unset-placeholder" @click="defSet('repeat_penalty')">点击设置</div>
            <input v-else type="range" min="0" max="2" step="0.1" v-model.number="defaultSettings.repeat_penalty" class="range" />
          </div>
        </template>

        <!-- 关于 -->
        <template v-if="activeTab === 'about'">
          <div v-if="verInfo" class="section about-section">
            <i class="fa-solid fa-bolt about-icon"></i>
            <h2 class="about-name">{{ verInfo.app }}</h2>
            <p class="about-desc">{{ verInfo.description }}</p>
            <div class="about-meta">
              <div class="about-meta-item">
                <span class="about-meta-label">版本</span>
                <span class="about-meta-value">{{ verInfo.app_version }}</span>
              </div>
              <div class="about-meta-item">
                <span class="about-meta-label">Python</span>
                <span class="about-meta-value">{{ verInfo.python }}</span>
              </div>
              <div class="about-meta-item">
                <span class="about-meta-label">平台</span>
                <span class="about-meta-value">{{ verInfo.platform }}</span>
              </div>
              <div class="about-meta-item">
                <span class="about-meta-label">架构</span>
                <span class="about-meta-value">{{ verInfo.arch }}</span>
              </div>
              <div class="about-meta-item">
                <span class="about-meta-label">FastAPI</span>
                <span class="about-meta-value">{{ verInfo.fastapi }}</span>
              </div>
            </div>
          </div>
          <div v-else class="section about-section">
            <p class="about-loading">加载中…</p>
          </div>
        </template>
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
  height: 400px;
}

/* ═══════════════════════════════════════════════════
   左侧标签栏
   ═══════════════════════════════════════════════════ */

.tab-nav {
  width: 140px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 0;
  border-right: 1px solid var(--border);
  background: var(--bg-primary);
}

.tab-nav-actions {
  padding: 12px 12px 12px;
  border-top: 1px solid var(--border);
  margin: 0 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tab-nav-save {
  padding: 7px 0;
  background: var(--accent);
  color: var(--white);
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 600;
  text-align: center;
}

.save-error {
  padding: 6px 8px;
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--error);
  text-align: center;
  word-break: break-all;
}

.tab-nav-save:hover { background: var(--accent-hover); }
.tab-nav-save:disabled { opacity: 0.5; cursor: not-allowed; }

/* ═══════════════════════════════════════════════════
   右侧设置面板
   ═══════════════════════════════════════════════════ */

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  min-width: 0;
}

.section {
  margin-bottom: 16px;
}

.section:last-child {
  margin-bottom: 0;
}

.label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
}

.label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0;
}

.reloading-indicator {
  font-size: 12px;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: 4px;
}

.desc {
  font-size: 13px;
  color: var(--text-dim);
  margin: 0 0 8px;
  line-height: 1.4;
}

.input {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  font-family: var(--font-mono);
}

.input:focus {
  border-color: var(--accent);
}

/* ── Textarea ──────────────────────────────────── */

.area {
  resize: vertical;
  line-height: 1.4;
  min-height: 64px;
}

/* ── 滑块 ──────────────────────────────────────── */

.range {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 5px;
  border-radius: var(--radius-sm);
  background: var(--border);
  outline: none;
  cursor: pointer;
}
.range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg-primary);
  cursor: pointer;
  box-shadow: 0 1px 3px var(--shadow-sm);
}

.label code {
  font-size: 12px;
  font-weight: 400;
  color: var(--accent);
  background: var(--accent-bg);
  padding: 1px 6px;
  border-radius: var(--radius);
  text-transform: none;
  letter-spacing: 0;
  font-family: var(--font-mono);
}

.clear-btn {
  width: 18px; height: 18px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: 1px solid var(--border);
  color: var(--text-dim); font-size: 10px; cursor: pointer;
  flex-shrink: 0; margin-left: auto;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.clear-btn:hover { color: var(--error); border-color: var(--error); background: var(--error-bg); }

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

/* ── 网关状态 ──────────────────────────────────── */

.health-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0 0;
}

.info-key {
  font-size: 14px;
  color: var(--text-secondary);
}

.info-value {
  font-size: 14px;
  color: var(--text-primary);
}

.info-value.ok { color: var(--success); }
.info-value.warn { color: var(--warning); }

/* ── MCP JSON 编辑器 ─────────────────────────── */

.mcp-editor-section {
  margin-bottom: 0;
}

.mcp-editor {
  width: 100%;
  min-height: 240px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  resize: vertical;
  tab-size: 2;
  white-space: pre;
  overflow: auto;
}

.mcp-editor:focus {
  border-color: var(--accent);
}

.mcp-editor.has-error {
  border-color: var(--error);
}

.mcp-error {
  margin: 6px 0 0;
  padding: 6px 10px;
  background: var(--error-bg);
  border-radius: var(--radius);
  color: var(--error);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}

.mcp-error i {
  margin-right: 4px;
}

/* ── 密钥 ──────────────────────────────────────── */

.secrets-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.secrets-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.secrets-key { width: 120px; flex-shrink: 0; }

.secrets-value-wrap {
  flex: 1;
  min-width: 0;
  position: relative;
}

.secrets-value {
  padding-right: 32px;
}

.secrets-value-wrap .input,
.secrets-row .input {
  margin-bottom: 0;
}

.secrets-toggle {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none;
  color: var(--text-dim); font-size: 13px; cursor: pointer;
}
.secrets-toggle:hover { color: var(--text-primary); }

.secrets-remove {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: 1px solid var(--border);
  color: var(--text-dim); font-size: 13px; cursor: pointer;
  flex-shrink: 0;
}
.secrets-remove:hover { color: var(--error); border-color: var(--error); }

.secrets-add {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  background: var(--bg-primary); border: 1px dashed var(--border);
  border-radius: var(--radius);
  color: var(--text-dim); font-size: 13px; cursor: pointer;
}
.secrets-add:hover { color: var(--accent); border-color: var(--accent); }

.secrets-list code {
  font-family: var(--font-mono);
  font-size: 13px;
  padding: 1px 4px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}

/* ── 关于 ──────────────────────────────────────── */

.about-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding-top: 10px;
}

.about-icon {
  font-size: 36px;
  color: var(--accent);
  margin-bottom: 12px;
}

.about-name {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 8px;
}

.about-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 20px;
  max-width: 280px;
}

.about-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 24px;
}

.about-loading {
  font-size: 14px;
  color: var(--text-dim);
}

.about-meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.about-meta-label {
  font-size: 12px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.about-meta-value {
  font-size: 14px;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

/* ═══════════════════════════════════════════════════
   服务器状态仪表盘
   ═══════════════════════════════════════════════════ */

/* ── 服务器地址行 ───────────────────────────────── */
.server-url-row {
  display: flex;
  gap: 6px;
}
.server-url-row .input { flex: 1; }
.btn-refresh {
  flex-shrink: 0;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.btn-refresh:hover { color: var(--text-primary); border-color: var(--text-dim); }

/* ── 状态列表 ───────────────────────────────────── */
.status-list {
  margin-bottom: 12px;
}
.status-list .label {
  margin-bottom: 4px;
}
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
  font-size: 14px;
}
.info-key {
  color: var(--text-dim);
  flex-shrink: 0;
  margin-right: 16px;
}
.info-value {
  color: var(--text-primary);
  font-size: 13px;
  text-align: right;
  word-break: break-all;
}
.info-value.mono {
  font-family: var(--font-mono);
}
.info-value.ok { color: var(--success); }
.info-value.warn { color: var(--warning); }
.info-value.err { color: var(--error); }
.info-value i { font-size: 8px; margin-right: 4px; vertical-align: middle; }

.status-na {
  margin: 0;
  font-size: 13px;
  color: var(--text-dim);
  font-style: italic;
}

</style>
