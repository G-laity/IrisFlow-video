/** 标签页选中框滑动指示器。
 *
 * 在 `.tab-nav` 内放置一个绝对定位的 `.tab-indicator`，
 * 根据当前 `.tab-btn.active` 的位置平滑滑动。
 */

import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import type { Ref } from "vue";

export function useTabIndicator(activeKey: Ref<string>, activeSelector = ".tab-btn.active") {
  const navEl = ref<HTMLElement | null>(null);
  const indicatorEl = ref<HTMLElement | null>(null);
  const indicatorStyle = ref<Record<string, string>>({ opacity: "0" });

  let ready = false;

  async function update(): Promise<void> {
    await nextTick();
    const nav = navEl.value;
    const el = indicatorEl.value;
    if (!nav || !el) return;

    const active = nav.querySelector<HTMLElement>(activeSelector);
    if (!active) {
      indicatorStyle.value = { opacity: "0" };
      ready = false;
      return;
    }

    const navRect = nav.getBoundingClientRect();
    const rect = active.getBoundingClientRect();
    indicatorStyle.value = {
      top: `${rect.top - navRect.top}px`,
      left: `${rect.left - navRect.left}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      opacity: "1",
    };

    if (!ready) {
      el.classList.add("no-anim");
      requestAnimationFrame(() => el.classList.remove("no-anim"));
      ready = true;
    }
  }

  watch(activeKey, () => { void update(); }, { flush: "post" });

  onMounted(() => {
    void update();
    window.addEventListener("resize", update);
  });

  onUnmounted(() => {
    window.removeEventListener("resize", update);
  });

  return { navEl, indicatorEl, indicatorStyle };
}
