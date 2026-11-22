<script setup lang="ts">
import { ref, computed, watch } from "vue";
import hljs from "highlight.js/lib/core";
import jsonLang from "highlight.js/lib/languages/json";

hljs.registerLanguage("json", jsonLang);
import FloatingWindow from "./FloatingWindow.vue";
import type { WorkflowEntry } from "../../types/api";
import { renderMarkdown } from "../../utils/markdown";
import { importComposerAssetUrl } from "../../api/client";
import { parseComposerError } from "../../composables/useComposer";
import { WF_THINK, WF_TOOL_CALL, WF_TOOL_RESULT, UI_CALL_PARAMS, UI_NO_TEXT_CONTENT, UI_RAW_DATA, UI_RETURN_RESULT, UI_SEARCH_RESULTS, UI_SEND_FAILED, UI_SEND_TO_COMPOSER, UI_SENT_DEDUP, UI_SENT_OK, UI_THOUGHT_CONTENT, UI_THOUGHT_PROCESS, UI_TOOL_CALL, UI_TOOL_LABEL, UI_TOOL_RESULT } from "../../constants";

// ── props / emits ────────────────────────────

const props = defineProps<{
  modelValue: boolean;
  entry: WorkflowEntry;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  close: [];
}>();

// ── 发送到合成器（M5）────────────────────────

const MEDIA_URL_RE = /https?:\/\/[^\s"'<>]+\.(?:mp4|mov|webm|mkv|avi|png|jpe?g|webp|gif|bmp|mp3|wav|m4a|aac|flac|ogg)(?:\?[^\s"'<>]*)?/i;

const mediaUrl = computed<string>(() => {
  if (props.entry.type !== WF_TOOL_RESULT || !props.entry.rawResult) return "";
  return props.entry.rawResult.match(MEDIA_URL_RE)?.[0] ?? "";
});

const sending = ref(false);
const sendMessage = ref("");

async function sendToComposer(): Promise<void> {
  if (!mediaUrl.value || sending.value) return;
  sending.value = true;
  sendMessage.value = "";
  try {
    const resp = await importComposerAssetUrl(mediaUrl.value);
    sendMessage.value = resp.duplicated ? UI_SENT_DEDUP : UI_SENT_OK;
  } catch (e) {
    sendMessage.value = `${UI_SEND_FAILED}：${parseComposerError(e).join("；")}`;
  } finally {
    sending.value = false;
  }
}

const showRaw = ref(false);

// ── 字段解析 ──────────────────────────────────

interface ParsedField {
  key: string;
  value: string;
  isLong: boolean;  // 长文本 / 含换行 → pre 块展示
}

function formatFieldValue(val: unknown): { text: string; isLong: boolean } {
  if (val === null || val === undefined) return { text: "—", isLong: false };
  if (typeof val === "string") {
    return { text: val, isLong: val.length > 80 || val.includes("\n") };
  }
  if (typeof val === "number" || typeof val === "boolean") {
    return { text: String(val), isLong: false };
  }
  const json = JSON.stringify(val, null, 2);
  return { text: json, isLong: json.length > 80 || json.includes("\n") };
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** JSON → hljs 高亮；非 JSON → HTML 转义 */
function highlightJsonOrEscape(text: string): string {
  if (!text) return "";
  try {
    JSON.parse(text);
    return hljs.highlight(text, { language: "json" }).value;
  } catch {
    return escapeHtml(text);
  }
}

/** 对字段值应用语法高亮：JSON → hljs；纯文本 → HTML 转义 */
function highlightFieldValue(text: string): string {
  return highlightJsonOrEscape(text);
}

function parseFields(obj: Record<string, unknown> | undefined): ParsedField[] {
  if (!obj || Object.keys(obj).length === 0) return [];
  return Object.entries(obj).map(([key, val]) => {
    const { text, isLong } = formatFieldValue(val);
    return { key, value: text, isLong };
  });
}

// ── 结果解析 ──────────────────────────────────

interface ParsedResult {
  isJson: boolean;
  isError: boolean;
  /** MCP content 文本提取结果 (text parts joined) */
  contentText: string | null;
  /** 通用 JSON 时展示为字段列表 */
  fields: ParsedField[];
  /** 非 JSON 时的原始文本 */
  rawText: string;
  /** 原始 JSON 字符串 (供折叠区展示) */
  rawJson: string;
}

function parseResult(raw: string | undefined): ParsedResult {
  const empty: ParsedResult = {
    isJson: false, isError: false, contentText: null,
    fields: [], rawText: "", rawJson: "",
  };
  if (!raw) return empty;

  // 1) 尝试 JSON 解析
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {
      ...empty,
      isError: false,  // 非 JSON 文本不存在结构化错误标志
      rawText: raw,
      rawJson: raw,
    };
  }

  // 2) JSON 解析成功 — 检查结构
  const rawJson = JSON.stringify(parsed, null, 2);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ...empty, isJson: true, rawText: raw, rawJson };
  }

  const obj = parsed as Record<string, unknown>;

  // JSON-RPC 错误检测
  const isError = !!(
    ("error" in obj && typeof obj.error === "object") ||
    "error" in obj ||  // 包括字符串 error
    obj.isError === true
  );

  // 3) MCP content 数组 → 提取文本
  if ("content" in obj && Array.isArray(obj.content)) {
    const parts: string[] = [];
    for (const item of obj.content) {
      if (!item || typeof item !== "object") continue;
      const ci = item as Record<string, unknown>;
      if (ci.type === "text" && typeof ci.text === "string") {
        parts.push(ci.text);
      } else if (ci.type === "resource" && ci.resource && typeof ci.resource === "object") {
        const res = ci.resource as Record<string, unknown>;
        if (typeof res.text === "string") parts.push(res.text);
      }
    }
    return { isJson: true, isError, contentText: parts.join("\n\n") || raw, fields: [], rawText: raw, rawJson };
  }

  // 4) JSON-RPC 响应 — 提取 result 或 error
  if ("result" in obj && obj.result && typeof obj.result === "object") {
    const resultObj = obj.result as Record<string, unknown>;
    // 如果 result 包含 content 数组 (MCP 嵌套)
    if ("content" in resultObj && Array.isArray(resultObj.content)) {
      const parts: string[] = [];
      for (const item of resultObj.content) {
        if (!item || typeof item !== "object") continue;
        const ci = item as Record<string, unknown>;
        if (ci.type === "text" && typeof ci.text === "string") parts.push(ci.text);
      }
      return { isJson: true, isError, contentText: parts.join("\n\n") || JSON.stringify(resultObj), fields: [], rawText: raw, rawJson };
    }
    // 通用 result 对象 → 字段列表
    return { isJson: true, isError, contentText: null, fields: parseFields(resultObj), rawText: raw, rawJson };
  }

  if ("error" in obj && typeof obj.error === "object") {
    const errObj = obj.error as Record<string, unknown>;
    const msg = `JSON-RPC 错误 ${errObj.code ?? "?"}: ${errObj.message ?? "未知错误"}`;
    return { isJson: true, isError: true, contentText: msg, fields: [], rawText: raw, rawJson };
  }

  // JSON-RPC 错误为字符串时 → 提取为 Markdown 文本
  if ("error" in obj && typeof obj.error === "string") {
    const { error: _err, ...rest } = obj;
    const fields = parseFields(rest as Record<string, unknown>);
    return { isJson: true, isError: true, contentText: obj.error as string, fields, rawText: raw, rawJson };
  }

  // 5) 通用 JSON — 字段列表 + 原始文本（可用于 Markdown 回退）
  const fields = parseFields(obj);
  return { isJson: true, isError, contentText: null, fields, rawText: raw, rawJson };
}

// ── computed ─────────────────────────────────

const parsedArgs = computed(() => parseFields(props.entry.rawArgs));
const parsedResult = computed(() => parseResult(props.entry.rawResult));

/** 合并错误信号：后端 SSE is_error 权威字段 + 结果体内的 JSON-RPC/MCP 错误结构 */
const hasError = computed(() => !!props.entry.isError || parsedResult.value.isError);

/** 结果展示文本（优先 MCP content，其次纯文本） */
const resultDisplay = computed(() => {
  const pr = parsedResult.value;
  if (pr.contentText !== null) return pr.contentText;
  if (pr.rawText) return pr.rawText;
  return "";
});

/** 结果文本的 Markdown 渲染。
 *  原始数据中不再包含 "[错误]" 前缀（后端通过 is_error 字段传递错误状态），
 *  Markdown 块级语法（###/``` 等）自然位于行首，无需额外处理。 */
const renderedResult = ref("");

watch(
  resultDisplay,
  async (text) => {
    if (!text) {
      renderedResult.value = "";
      return;
    }
    try {
      renderedResult.value = await renderMarkdown(text);
    } catch {
      renderedResult.value = escapeHtml(text); // 降级为纯文本
    }
  },
  { immediate: true },
);

/** 原始数据文本 — 后端返回的原始字符串，不做任何加工 */
const rawDataText = computed(() => {
  if (props.entry.type === WF_TOOL_CALL && props.entry.rawArgs) {
    return JSON.stringify(props.entry.rawArgs, null, 2);
  }
  return props.entry.rawResult || "";
});

const hasRawData = computed(() => {
  if (props.entry.type === WF_TOOL_CALL && parsedArgs.value.length > 0) return true;
  if (props.entry.type === WF_TOOL_RESULT && props.entry.rawResult) return true;
  return false;
});

/** 原始数据高亮渲染（JSON → hljs） */
const highlightedRaw = computed(() => {
  return highlightJsonOrEscape(rawDataText.value);
});

// ── 搜索链接 ──────────────────────────────────

const searchLinks = computed(() => {
  if (props.entry.type !== WF_TOOL_RESULT || !props.entry.rawResult) return [];
  const text = props.entry.rawResult;
  const links: { title: string; snippet: string; url: string }[] = [];
  const re = /•\s*\*\*(.+?)\*\*\s*\n\s*(.+?)\n\s*(https?:\/\/\S+)/g;
  for (const m of text.matchAll(re)) {
    links.push({ title: m[1], snippet: m[2].trim(), url: m[3] });
  }
  const re2 = /📌\s*(.+?)\n\s*来源:\s*(https?:\/\/\S+)/g;
  for (const m of text.matchAll(re2)) {
    links.push({ title: m[1], snippet: "", url: m[2] });
  }
  return links;
});

// ── 浮窗头部 ──────────────────────────────────

const headerTitle = computed(() => {
  if (props.entry.type === WF_TOOL_CALL) return UI_TOOL_CALL;
  if (props.entry.type === WF_TOOL_RESULT) return UI_TOOL_RESULT;
  return UI_THOUGHT_PROCESS;
});

const headerIcon = computed(() => {
  if (props.entry.type === WF_TOOL_CALL) return "fa-solid fa-screwdriver-wrench";
  if (props.entry.type === WF_TOOL_RESULT) return "fa-solid fa-inbox";
  return "fa-solid fa-brain";
});
</script>

<template>
  <FloatingWindow
    width="460px"
    :title="headerTitle"
    :icon="headerIcon"
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('close')"
  >
    <template v-if="mediaUrl" #actions>
      <button class="btn-icon" :title="UI_SEND_TO_COMPOSER" :aria-label="UI_SEND_TO_COMPOSER" :disabled="sending" @click.stop="sendToComposer">
        <i :class="sending ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-clapperboard'"></i>
      </button>
    </template>
    <div class="wd-body">
      <p v-if="sendMessage" class="wd-send-msg">{{ sendMessage }}</p>
      <!-- ── 工具名 ──────────────────────────── -->
      <div class="info-block">
        <div class="info-label">{{ UI_TOOL_LABEL }}</div>
        <div class="info-value" :class="{ 'info-value--error': hasError }">
          <i v-if="hasError" class="fa-solid fa-circle-exclamation error-icon" />
          {{ entry.toolName || '—' }}
        </div>
      </div>

      <!-- ── 思考文本 ────────────────────────── -->
      <div v-if="entry.type === WF_THINK" class="info-block">
        <div class="info-label">{{ UI_THOUGHT_CONTENT }}</div>
        <div class="info-text">{{ entry.text }}</div>
      </div>

      <!-- ── 调用参数 (tool_call) ─────────────── -->
      <div v-if="parsedArgs.length" class="info-block">
        <div class="info-label">{{ UI_CALL_PARAMS }}</div>
        <div class="arg-list">
          <div v-for="f in parsedArgs" :key="f.key" class="arg-item">
            <span class="arg-key">{{ f.key }}</span>
            <pre v-if="f.isLong" class="arg-value-long" v-html="highlightFieldValue(f.value)" />
            <span v-else class="arg-value" v-html="highlightFieldValue(f.value)" />
          </div>
        </div>
      </div>

      <!-- ── 返回结果 (tool_result) ───────────── -->
      <div v-if="entry.type === WF_TOOL_RESULT" class="info-block">
        <div class="info-label" :class="{ 'info-label--error': hasError }">
          <i v-if="hasError" class="fa-solid fa-triangle-exclamation" />
          {{ UI_RETURN_RESULT }}
        </div>
        <!-- JSON 字段列表 -->
        <div v-if="parsedResult.fields.length" class="arg-list">
          <div v-for="f in parsedResult.fields" :key="f.key" class="arg-item">
            <span class="arg-key">{{ f.key }}</span>
            <pre v-if="f.isLong" class="arg-value-long" v-html="highlightFieldValue(f.value)" />
            <span v-else class="arg-value" v-html="highlightFieldValue(f.value)" />
          </div>
        </div>
        <!-- 文本内容（Markdown 渲染，可与字段列表同时出现） -->
        <div v-if="resultDisplay" class="result-markdown markdown-content" v-html="renderedResult" />
        <div v-if="!parsedResult.fields.length && !resultDisplay" class="info-text dim">{{ UI_NO_TEXT_CONTENT }}</div>
      </div>

      <!-- ── 原始数据 ─────────────────────────── -->
      <div v-if="hasRawData" class="info-block">
        <button class="raw-toggle" :aria-expanded="showRaw" @click="showRaw = !showRaw">
          <i class="fa-solid" :class="showRaw ? 'fa-chevron-down' : 'fa-chevron-right'" />
          {{ UI_RAW_DATA }}
        </button>
        <pre v-if="showRaw" class="info-code" v-html="highlightedRaw" />
      </div>

      <!-- ── 搜索链接 ─────────────────────────── -->
      <div v-if="searchLinks.length" class="info-block">
        <div class="info-label">搜索到 {{ searchLinks.length }} 个网页</div>
        <a
          v-for="(link, i) in searchLinks" :key="i"
          class="search-link-item" :href="link.url" target="_blank" rel="noopener"
        >
          <span class="link-title">{{ link.title }}</span>
          <span v-if="link.snippet" class="link-snippet">{{ link.snippet }}</span>
          <span class="link-url">{{ link.url }}</span>
        </a>
      </div>
    </div>
  </FloatingWindow>
</template>

<style scoped>
/* ── Body ────────────────────────────────────── */

.wd-body {
  padding: 14px;
  max-height: 62vh;
  overflow-y: auto;
}

/* ── 通用扩展 ───────────────────────────────── */

.info-label--error {
  color: var(--error);
}

.info-value {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
}

.info-value--error {
  color: var(--error);
}

.error-icon {
  font-size: 14px;
}

.info-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.info-text.dim {
  color: var(--text-dim);
  font-style: italic;
}

/* ── 参数 / 字段列表 ────────────────────────── */

.arg-list {
  background: var(--bg-primary);
  border-radius: var(--radius);
  padding: 6px 10px;
}

.arg-item {
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
}
.arg-item:last-child { border-bottom: none; }

.arg-key {
  display: block;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  margin-bottom: 2px;
}

.arg-value {
  font-size: 14px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  word-break: break-all;
}

.arg-value-long {
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-tertiary, var(--white-04));
  border-radius: var(--radius-sm, 4px);
  padding: 6px 8px;
  margin: 4px 0 0;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

/* ── 搜索链接 ───────────────────────────────── */

.search-link-item {
  display: block;
  padding: 8px 10px;
  border-radius: var(--radius);
  text-decoration: none;
  margin-bottom: 4px;
  background: var(--bg-primary);
  border: 1px solid transparent;
}
.search-link-item:hover { border-color: var(--border); }

.link-title { display: block; font-weight: 600; color: var(--accent); font-size: 14px; margin-bottom: 2px; }
.link-snippet { display: block; color: var(--text-dim); font-size: 14px; line-height: 1.4; margin-bottom: 2px; }
.link-url { display: block; color: var(--text-dim); font-size: 12px; word-break: break-all; }

/* ── 返回结果 Markdown 渲染 ──────────────────── */

.result-markdown {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  word-break: break-word;
}

/* 全局 .markdown-content 提供基础规则，此处仅保留 WorkflowDetail 特有样式 */

.result-markdown :deep(h1),
.result-markdown :deep(h2),
.result-markdown :deep(h3),
.result-markdown :deep(h4) {
  margin: 8px 0 4px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
}
.result-markdown :deep(h1) { font-size: 18px; }
.result-markdown :deep(h2) { font-size: 16px; }
.result-markdown :deep(h3) { font-size: 15px; }
.result-markdown :deep(h4) { font-size: 14px; }

.result-markdown :deep(ul),
.result-markdown :deep(ol) {
  padding-left: 18px;
}
.result-markdown :deep(table) { font-size: 13px; }
.result-markdown :deep(th),
.result-markdown :deep(td) {
  padding: 3px 7px;
}
.result-markdown :deep(th) { font-weight: 600; }

.result-markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 8px 0;
}
.wd-send-msg {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--success);
}
</style>
