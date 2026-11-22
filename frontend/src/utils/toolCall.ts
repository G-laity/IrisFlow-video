/** 工具调用文本兜底。
 *
 * 部分模型在未收到 tools 定义时会按训练格式在正文输出
 * `<tool_call>{...}</tool_call>`。后端只执行结构化 tool_calls，
 * 这里把文本标记替换为可读提示，避免把 XML 原样展示给用户。
 */

import { UI_TOOL_CALL_FALLBACK } from "../constants";

const COMPLETE = /<tool_call>[\s\S]*?<\/tool_call>/gi;
// 流式过程中可能只收到开标签，先隐藏剩余内容，避免标签闪烁
const PARTIAL = /<tool_call>[\s\S]*$/i;

export function sanitizeToolCallMarkup(text: string): string {
  if (!text || !text.includes("<tool_call>")) return text;
  const hint = `\n\n${UI_TOOL_CALL_FALLBACK}\n\n`;
  return text.replace(COMPLETE, hint).replace(PARTIAL, hint);
}
