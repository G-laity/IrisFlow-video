/** 共享 markdown-it 实例 — MessageBubble、MediaPreview 共用。
 *  模块级单例，避免重复创建 parser + hljs 覆写。 */

import MarkdownIt from "markdown-it";
import texmath from "markdown-it-texmath";
import katex from "katex";
import hljs from "highlight.js";

export const md = MarkdownIt({ html: true, breaks: true, linkify: true })
  .use(texmath, {
    engine: katex,
    delimiters: ["dollars"],
    katexOptions: { throwOnError: false },
  });

/** 代码块复制按钮 HTML 片段 */
function _copyBtn(): string {
  return `<button class="code-copy-btn" title="复制"><i class="fa-solid fa-copy"></i></button>`;
}

/** 覆写代码块渲染：highlight.js 语法高亮 + 语言标签 + 复制按钮 */
md.renderer.rules.fence = (tokens, idx, _options, _env, _self) => {
  const token = tokens[idx];
  const lang = token.info?.trim() || "";
  const code = token.content;
  const langTag = lang ? `<span class="code-lang">${md.utils.escapeHtml(lang)}</span>` : "";

  if (lang && hljs.getLanguage(lang)) {
    try {
      const highlighted = hljs.highlight(code, { language: lang }).value;
      return `<pre data-lang="${lang}"><div class="code-header">${langTag}${_copyBtn()}</div><code class="hljs">${highlighted}</code></pre>`;
    } catch { /* fall through */ }
  }

  // 无语言或未知语言 → 仍显示复制按钮
  const escaped = md.utils.escapeHtml(code);
  return `<pre data-lang="${lang || ''}"><div class="code-header">${langTag}${_copyBtn()}</div><code>${escaped}</code></pre>`;
};

// ── 媒体类型判定 ──────────────────────────────────

export const IMG_EXTS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
  ".bmp", ".ico", ".avif", ".apng", ".tif", ".tiff",
]);
export const VID_EXTS = new Set([
  ".mp4", ".webm", ".ogg", ".mov", ".avi", ".mkv", ".wmv", ".flv",
]);

export function mediaKindFromUrl(url: string): "image" | "video" | "webpage" {
  try {
    const path = new URL(url).pathname.toLowerCase();
    const ext = path.slice(path.lastIndexOf("."));
    if (IMG_EXTS.has(ext)) return "image";
    if (VID_EXTS.has(ext)) return "video";
  } catch { /* invalid URL */ }
  return "webpage";
}

function escAttr(s: string) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function filenameFromUrl(url: string): string {
  try { return decodeURIComponent(url.split("/").pop() || url); }
  catch { return url; }
}

// ── `![alt](url)` → 预览卡片 ──────────────────────

const _defaultImage = md.renderer.rules.image!;
md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const src = token.attrGet("src") || "";
  const alt = token.content || "";

  if (!src.startsWith("http://") && !src.startsWith("https://")) {
    token.attrSet("loading", "lazy");
    return _defaultImage(tokens, idx, options, env, self);
  }

  const kind = mediaKindFromUrl(src);
  const preview =
    kind === "image" ? `<img src="${escAttr(src)}" loading="lazy" referrerpolicy="no-referrer">`
    : kind === "video" ? `<video src="${escAttr(src)}" preload="metadata" muted disablepictureinpicture disableremoteplayback></video>`
    : `<span class="lc-url">${escAttr(src)}</span>`;
  const title = alt || filenameFromUrl(src);
  const barIcon = kind === "image" ? "fa-solid fa-image"
    : kind === "video" ? "fa-solid fa-video" : "fa-solid fa-globe";

  return `<a class="link-card link-card--${kind}" href="${escAttr(src)}" target="_blank" rel="noopener noreferrer" data-kind="${kind}">`
    + `<span class="lc-preview">${preview}</span>`
    + `<span class="lc-bar"><i class="${barIcon} lc-bar-icon"></i><span class="lc-title">${title}</span></span>`
    + `</a>`;
};

// ── Core：独立成行的 `[]()` 标记为块级卡片 ────────

md.core.ruler.push("link_blocks", (state) => {
  for (const token of state.tokens) {
    if (token.type !== "inline" || !token.children?.length) continue;
    const kids = token.children;
    // 按 softbreak / hardbreak 分行检测，每行内独立判断
    let segStart = 0;
    for (let i = 0; i <= kids.length; i++) {
      if (i < kids.length && kids[i].type !== "softbreak" && kids[i].type !== "hardbreak") continue;
      const seg = kids.slice(segStart, i).filter(
        k => k.type !== "text" || (k.content || "").trim()
      );
      if (seg.length >= 2 && seg[0].type === "link_open" && seg[seg.length - 1].type === "link_close") {
        seg[0].attrSet("data-block", "1");
      }
      segStart = i + 1; // 跳过 break token
    }
  }
});

// ── `[]()` 渲染：独立行 → 卡片，行内 → 徽章 ──────

function cardPreview(kind: string, href: string): string {
  if (kind === "image") return `<img src="${escAttr(href)}" loading="lazy" referrerpolicy="no-referrer">`;
  if (kind === "video") return `<video src="${escAttr(href)}" preload="metadata" muted disablepictureinpicture disableremoteplayback></video>`;
  return `<span class="lc-url">${escAttr(href)}</span>`;
}
function cardBarIcon(kind: string): string {
  if (kind === "image") return "fa-solid fa-image";
  if (kind === "video") return "fa-solid fa-video";
  return "fa-solid fa-globe";
}

const _defaultLink =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const href = token.attrGet("href") || "";

  if (!href.startsWith("http://") && !href.startsWith("https://")) {
    token.attrSet("target", "_blank");
    token.attrSet("rel", "noopener noreferrer");
    return _defaultLink(tokens, idx, options, env, self);
  }

  const kind = mediaKindFromUrl(href);
  token.attrSet("target", "_blank");
  token.attrSet("rel", "noopener noreferrer");
  token.attrSet("data-kind", kind);

  if (token.attrGet("data-block") === "1") {
    // 独立行 → 卡片（与 ![]() 相同结构）
    token.attrSet("class", `link-card link-card--${kind}`);
    return `<a${self.renderAttrs(token)}>`
      + `<span class="lc-preview">${cardPreview(kind, href)}</span>`
      + `<span class="lc-bar"><i class="${cardBarIcon(kind)} lc-bar-icon"></i><span class="lc-title">`;
  }

  // 行内 → 徽章（图标与卡片统一）
  token.attrSet("class", `link-badge link-badge--${kind}`);
  return `<a${self.renderAttrs(token)}><i class="${cardBarIcon(kind)} lb-icon"></i>`;
};

const _defaultLinkClose =
  md.renderer.rules.link_close ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));

md.renderer.rules.link_close = (tokens, idx, options, env, self) => {
  let openToken: any = null;
  for (let i = idx - 1; i >= 0; i--) {
    if (tokens[i].type === "link_open" && tokens[i].level === tokens[idx].level) {
      openToken = tokens[i]; break;
    }
    if (tokens[i].level < tokens[idx].level) break;
  }
  const cls: string = openToken?.attrGet?.("class") || "";
  if (cls.includes("link-badge")) return `</a>`;
  // 块级卡片：lc-title 仍开启，闭合 lc-title + lc-bar
  if (cls.includes("link-card")) return `</span></span></a>`;
  return _defaultLinkClose(tokens, idx, options, env, self);
};
