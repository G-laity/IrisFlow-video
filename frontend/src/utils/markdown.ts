/** Markdown 渲染 — 重依赖按需加载（P3）。
 *
 * markdown-it / texmath / katex / highlight.js 全部通过动态 import 加载：
 * 首屏不加载这些包，首次渲染消息时（或空闲预加载时）才请求对应 chunk。
 * 加载失败时抛错，由调用方降级为纯文本。
 */

import type MarkdownIt from "markdown-it";
import { UI_COPY } from "../constants";

let _mdPromise: Promise<MarkdownIt> | null = null;

// ── 媒体类型判定（轻量，保持同步导出）───────────────

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

// ── 懒初始化 ────────────────────────────────────────

async function createMarkdown(): Promise<MarkdownIt> {
  const [
    { default: MarkdownItCtor },
    { default: texmath },
    { default: katex },
    { default: hljs },
  ] = await Promise.all([
    import("markdown-it"),
    import("markdown-it-texmath"),
    import("katex"),
    import("highlight.js"),
  ]);

  const md = new MarkdownItCtor({ html: true, breaks: true, linkify: true }).use(texmath, {
    engine: katex,
    delimiters: ["dollars"],
    katexOptions: { throwOnError: false },
  });

  /** 代码块复制按钮 HTML 片段 */
  const copyBtn = (): string =>
    `<button class="code-copy-btn" title="${UI_COPY}" aria-label="${UI_COPY}"><i class="fa-solid fa-copy"></i></button>`;

  // 覆写代码块渲染：highlight.js 语法高亮 + 语言标签 + 复制按钮
  md.renderer.rules.fence = (tokens, idx, _options, _env, _self) => {
    const token = tokens[idx];
    const lang = token.info?.trim() || "";
    const code = token.content;
    const langTag = lang ? `<span class="code-lang">${md.utils.escapeHtml(lang)}</span>` : "";

    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(code, { language: lang }).value;
        return `<pre data-lang="${lang}"><div class="code-header">${langTag}${copyBtn()}</div><code class="hljs">${highlighted}</code></pre>`;
      } catch { /* fall through */ }
    }

    // 无语言或未知语言 → 仍显示复制按钮
    const escaped = md.utils.escapeHtml(code);
    return `<pre data-lang="${lang || ""}"><div class="code-header">${langTag}${copyBtn()}</div><code>${escaped}</code></pre>`;
  };

  // ── `![alt](url)` → 预览卡片 ──────────────────────

  const escapeAttr = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");

  const filenameFromUrl = (url: string): string => {
    try { return decodeURIComponent(url.split("/").pop() || url); }
    catch { return url; }
  };

  const defaultImage = md.renderer.rules.image!;
  md.renderer.rules.image = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const src = token.attrGet("src") || "";
    const alt = token.content || "";

    if (!src.startsWith("http://") && !src.startsWith("https://")) {
      token.attrSet("loading", "lazy");
      return defaultImage(tokens, idx, options, env, self);
    }

    const kind = mediaKindFromUrl(src);
    const preview =
      kind === "image" ? `<img src="${escapeAttr(src)}" loading="lazy" referrerpolicy="no-referrer">`
      : kind === "video" ? `<video src="${escapeAttr(src)}" preload="metadata" muted disablepictureinpicture disableremoteplayback></video>`
      : `<span class="lc-url">${escapeAttr(src)}</span>`;
    const title = alt || filenameFromUrl(src);
    const barIcon = kind === "image" ? "fa-solid fa-image"
      : kind === "video" ? "fa-solid fa-video" : "fa-solid fa-globe";

    return `<a class="link-card link-card--${kind}" href="${escapeAttr(src)}" target="_blank" rel="noopener noreferrer" data-kind="${kind}">`
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

  const cardPreview = (kind: string, href: string): string => {
    if (kind === "image") return `<img src="${escapeAttr(href)}" loading="lazy" referrerpolicy="no-referrer">`;
    if (kind === "video") return `<video src="${escapeAttr(href)}" preload="metadata" muted disablepictureinpicture disableremoteplayback></video>`;
    return `<span class="lc-url">${escapeAttr(href)}</span>`;
  };
  const cardBarIcon = (kind: string): string => {
    if (kind === "image") return "fa-solid fa-image";
    if (kind === "video") return "fa-solid fa-video";
    return "fa-solid fa-globe";
  };

  const defaultLink =
    md.renderer.rules.link_open ||
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));

  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const href = token.attrGet("href") || "";

    if (!href.startsWith("http://") && !href.startsWith("https://")) {
      token.attrSet("target", "_blank");
      token.attrSet("rel", "noopener noreferrer");
      return defaultLink(tokens, idx, options, env, self);
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

  const defaultLinkClose =
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
    return defaultLinkClose(tokens, idx, options, env, self);
  };

  return md;
}

/** 空闲预加载 Markdown 重依赖（失败静默，下次渲染时重试）。 */
export function preloadMarkdown(): void {
  if (_mdPromise) return;
  _mdPromise = createMarkdown();
  _mdPromise.catch(() => { _mdPromise = null; });
}

/** 渲染 Markdown；加载/渲染失败时抛错，由调用方降级为纯文本。 */
export async function renderMarkdown(text: string): Promise<string> {
  if (!_mdPromise) _mdPromise = createMarkdown();
  try {
    const md = await _mdPromise;
    return md.render(text);
  } catch (e) {
    _mdPromise = null;
    throw e;
  }
}
