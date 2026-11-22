import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./style.css";
import "@fortawesome/fontawesome-free/css/all.min.css";
import "katex/dist/katex.min.css";
import { initTheme } from "./composables/useTheme";
import { COPY_FEEDBACK_DURATION, UI_COPIED } from "./constants";

// ── 全局代码块复制 ──────────────────────────────

const _copyTimers = new WeakMap<HTMLElement, ReturnType<typeof setTimeout>>();
let _toastEl: HTMLDivElement | null = null;
let _toastTimer: ReturnType<typeof setTimeout> | null = null;

function showCopyToast(anchor: HTMLElement): void {
  if (_toastEl) _toastEl.remove();
  if (_toastTimer) clearTimeout(_toastTimer);

  const rect = anchor.getBoundingClientRect();
  const el = document.createElement("div");
  el.className = "copy-toast-fixed";
  el.textContent = UI_COPIED;
  el.style.left = `${rect.left + rect.width / 2}px`;
  el.style.top = `${rect.top}px`;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  _toastEl = el;

  _toastTimer = setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 150);
    if (_toastEl === el) _toastEl = null;
  }, COPY_FEEDBACK_DURATION);
}

document.addEventListener("click", (e) => {
  const btn = (e.target as HTMLElement).closest<HTMLElement>(".code-copy-btn");
  if (!btn) return;
  const pre = btn.closest("pre");
  const code = pre?.querySelector("code");
  if (!code) return;
  navigator.clipboard.writeText(code.textContent || "").then(() => {
    const icon = btn.querySelector<HTMLElement>("i");
    if (icon && !btn.dataset.originalIcon) btn.dataset.originalIcon = icon.className;
    btn.classList.add("copied");
    if (icon) icon.className = "fa-solid fa-check";
    showCopyToast(btn);

    const existing = _copyTimers.get(btn);
    if (existing) clearTimeout(existing);
    _copyTimers.set(btn, setTimeout(() => {
      btn.classList.remove("copied");
      if (icon) icon.className = btn.dataset.originalIcon || "fa-solid fa-copy";
      delete btn.dataset.originalIcon;
      _copyTimers.delete(btn);
    }, COPY_FEEDBACK_DURATION));
  }).catch(() => { /* 忽略复制失败 */ });
});

initTheme();
createApp(App).use(router).mount("#app");
