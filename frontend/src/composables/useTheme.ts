/** 明暗主题管理（P2）。
 *
 * - 模式：dark / light / system，持久化到 localStorage
 * - 应用方式：<html data-theme="..."> + CSS 变量
 * - 代码高亮：highlight.js 的亮/暗主题 CSS 通过 <link> 动态切换
 */

import { computed, ref } from "vue";
import hljsDarkUrl from "highlight.js/styles/github-dark.min.css?url";
import hljsLightUrl from "highlight.js/styles/github.min.css?url";
import { LS_THEME, THEME_DARK, THEME_LIGHT, THEME_SYSTEM } from "../constants";
import type { ThemeMode } from "../constants";

export const themeMode = ref<ThemeMode>(THEME_DARK);

interface ViewTransitionLike {
  ready: Promise<void>;
  finished: Promise<void>;
}

type TransitionDocument = Document & {
  startViewTransition?: (callback: () => void) => ViewTransitionLike;
};

const _systemDark = ref(false);
let _media: MediaQueryList | null = null;

export const effectiveTheme = computed<"dark" | "light">(() =>
  themeMode.value === THEME_SYSTEM
    ? (_systemDark.value ? "dark" : "light")
    : themeMode.value === THEME_LIGHT ? "light" : "dark",
);

function _apply(): void {
  const effective = effectiveTheme.value;
  document.documentElement.dataset.theme = effective;

  let link = document.getElementById("hljs-theme") as HTMLLinkElement | null;
  if (!link) {
    link = document.createElement("link");
    link.id = "hljs-theme";
    link.rel = "stylesheet";
    document.head.appendChild(link);
  }
  const href = effective === "dark" ? hljsDarkUrl : hljsLightUrl;
  if (link.getAttribute("href") !== href) link.setAttribute("href", href);
}

/** 启动时调用：读取持久化设置、监听系统主题并应用。 */
export function initTheme(): void {
  try {
    const saved = localStorage.getItem(LS_THEME);
    if (saved === THEME_DARK || saved === THEME_LIGHT || saved === THEME_SYSTEM) {
      themeMode.value = saved;
    }
  } catch {
    /* localStorage 不可用时保持默认 */
  }

  _media = window.matchMedia("(prefers-color-scheme: dark)");
  _systemDark.value = _media.matches;
  _media.addEventListener("change", (e) => {
    _systemDark.value = e.matches;
    if (themeMode.value === THEME_SYSTEM) _apply();
  });

  _apply();
}

/** 切换主题模式并持久化。
 *
 * 传入鼠标事件时，使用 View Transitions API 以按钮为圆心做圆形扩散切换；
 * 浏览器不支持或用户开启「减弱动效」时直接切换。
 */
export function setTheme(mode: ThemeMode, event?: MouseEvent): void {
  if (mode === themeMode.value) return;

  const apply = (): void => {
    themeMode.value = mode;
    try {
      localStorage.setItem(LS_THEME, mode);
    } catch {
      /* 忽略持久化失败 */
    }
    _apply();
  };

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const doc = document as TransitionDocument;
  if (!doc.startViewTransition || !event || event.detail === 0 || reduceMotion) {
    apply();
    return;
  }

  const x = event.clientX;
  const y = event.clientY;
  const radius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y),
  );
  const transition = doc.startViewTransition(apply);
  transition.ready
    .then(() => {
      const options = {
        duration: 480,
        easing: "ease-in-out",
        pseudoElement: "::view-transition-new(root)",
      };
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${radius}px at ${x}px ${y}px)`,
          ],
        },
        options as KeyframeAnimationOptions,
      );
    })
    .catch(() => {
      /* ready 失败时主题已在回调中应用 */
    });
}
