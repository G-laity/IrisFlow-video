/**
 * A2 — 指针驱动的液态玻璃折射。
 *
 * 指针悬停在 .glass-card 上时，以 ~12fps 节流微调 SVG feTurbulence 的
 * baseFrequency，让折射纹理随指针缓慢流动；停止移动 600ms 后回到静态值。
 * 触摸设备、prefers-reduced-motion、不支持 backdrop-filter url() 时完全跳过。
 *
 * 边界：这是 DOM 能做到的近似折射，不是 WebGL 屏幕空间折射。
 */
import { onMounted, onUnmounted } from "vue";

/** 12fps 更新节奏，避免 SVG 滤镜重算拖帧 */
const UPDATE_MS = 83;
/** 静态基准频率（与 index.html 初始值一致） */
const BASE_X = 0.008;
const BASE_Y = 0.016;
/** 指针位置带来的最大频率偏移 */
const SWAY_X = 0.0016;
const SWAY_Y = 0.0016;
/** 停止移动后回到静态值的延迟 */
const IDLE_MS = 600;

export function useGlassPointer() {
  let turbulence: Element | null = null;
  let raf = 0;
  let last = 0;
  let active = false;
  let px = 0.5;
  let py = 0.5;
  let idleTimer: ReturnType<typeof setTimeout> | null = null;
  /** 性能看门狗：连续掉帧时停用指针折射，保留静态玻璃 */
  let frames = 0;
  let slowFrames = 0;
  let lastFrame = 0;
  let disabled = false;

  function supported(): boolean {
    if (typeof window === "undefined" || typeof CSS === "undefined") return false;
    if (window.matchMedia("(pointer: coarse)").matches) return false;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
    return (
      CSS.supports("backdrop-filter", "url(#liquid-glass-refraction)") ||
      CSS.supports("-webkit-backdrop-filter", "url(#liquid-glass-refraction)")
    );
  }

  function apply() {
    if (!turbulence) return;
    const bx = BASE_X + (px - 0.5) * SWAY_X;
    const by = BASE_Y + (py - 0.5) * SWAY_Y;
    turbulence.setAttribute("baseFrequency", `${bx.toFixed(4)} ${by.toFixed(4)}`);
  }

  function reset() {
    if (!turbulence) return;
    turbulence.setAttribute("baseFrequency", `${BASE_X} ${BASE_Y}`);
  }

  function tick(now: number) {
    raf = 0;
    if (!active || disabled) return;

    // 掉帧看门狗：30 帧内超过 60% 慢帧则永久停用指针折射
    if (lastFrame) {
      if (now - lastFrame > 20) slowFrames++;
      frames++;
      if (frames >= 30) {
        if (slowFrames >= 18) {
          disabled = true;
          stop();
          return;
        }
        frames = 0;
        slowFrames = 0;
      }
    }
    lastFrame = now;

    if (now - last >= UPDATE_MS) {
      last = now;
      apply();
    }
    raf = requestAnimationFrame(tick);
  }

  function stop() {
    active = false;
    frames = 0;
    slowFrames = 0;
    lastFrame = 0;
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    reset();
  }

  function onMove(e: PointerEvent) {
    const target = e.target as Element | null;
    if (!target?.closest?.(".glass-card")) {
      stop();
      return;
    }
    px = e.clientX / Math.max(1, window.innerWidth);
    py = e.clientY / Math.max(1, window.innerHeight);
    active = true;
    if (!raf) {
      last = 0;
      raf = requestAnimationFrame(tick);
    }
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(stop, IDLE_MS);
  }

  function onLeave(e: PointerEvent) {
    const target = e.target as Element | null;
    if (target?.closest?.(".glass-card")) stop();
  }

  onMounted(() => {
    if (!supported()) return;
    turbulence = document.getElementById("glass-turbulence");
    if (!turbulence) return;
    document.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave, true);
    document.addEventListener("pointercancel", stop);
  });

  onUnmounted(() => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerleave", onLeave, true);
    document.removeEventListener("pointercancel", stop);
    stop();
    turbulence = null;
  });
}
