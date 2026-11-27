/**
 * Fluid Morph — 胶囊按钮 ⇄ 浮窗面板的高阻尼弹簧变形。
 *
 * 不用 CSS linear()/cubic-bezier：直接把二阶阻尼振子的阶跃响应采样成
 * 逐帧关键帧，交给 WAAPI 以 linear 播放。这样：
 *  - 兼容性好（不依赖 linear() 缓动支持）；
 *  - 尺寸 / 圆角共享同一条物理曲线，收尾有极轻微过冲，像液体表面张力；
 *  - 宽度先到、高度略滞后，形状会先横向拉伸，再纵向填满。
 */

export interface MorphRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface MorphFrameOptions {
  mode: "open" | "close";
  /** 面板最终 / 起始圆角（px） */
  radius: number;
  /** 关键帧采样数，默认 46（≈60fps 下每帧一个） */
  steps?: number;
}

/** 展开时长（ms） */
export const MORPH_OPEN_MS = 400;
/** 收回时长（ms），收回比展开更干脆 */
export const MORPH_CLOSE_MS = 320;

/** 阻尼比：高阻尼，几乎无回弹，收尾约 0.5% 过冲 */
const SPRING_ZETA = 0.86;
/** 归一化角频率（覆盖整段动画） */
const SPRING_OMEGA = 5.9;
/** 变形中途圆角的“液面”鼓起量（px），避免保持胶囊半径而裁切内容 */
const MORPH_RADIUS_BULGE = 8;

/** 二阶阻尼振子阶跃响应（0 → 1）。t ∈ [0, 1]。 */
function springStep(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;

  const z = SPRING_ZETA;
  const w = SPRING_OMEGA;
  const wd = w * Math.sqrt(1 - z * z);
  const envelope = Math.exp(-z * w * t);
  return 1 - envelope * (Math.cos(wd * t) + ((z * w) / wd) * Math.sin(wd * t));
}

function px(value: number): string {
  return `${Math.round(value * 100) / 100}px`;
}

/** 把弹簧轨迹采样成 WAAPI 关键帧。 */
export function buildMorphFrames(
  from: MorphRect,
  to: MorphRect,
  opts: MorphFrameOptions,
): Keyframe[] {
  const steps = opts.steps ?? 46;
  const frames: Keyframe[] = [];

  for (let i = 0; i <= steps; i++) {
    const t = i / steps;

    // 宽度略快、高度略慢 → 液体拉伸感
    const widthProgress = springStep(t);
    const heightProgress = springStep(Math.pow(t, 1.12));

    const fromRight = from.left + from.width;
    const toRight = to.left + to.width;
    const right = fromRight + (toRight - fromRight) * widthProgress;
    const width = from.width + (to.width - from.width) * widthProgress;
    const left = right - width;

    const top = from.top + (to.top - from.top) * heightProgress;
    const height = from.height + (to.height - from.height) * heightProgress;

    // 圆角：胶囊半径 ⇄ 面板圆角，中途带一点「液面」鼓起。
    // 不跟随高度膨胀成大圆球，这样卡片内容可以在变形过程中就可见。
    const startRadius = opts.mode === "open" ? from.height / 2 : opts.radius;
    const endRadius = opts.mode === "open" ? opts.radius : to.height / 2;
    const bulge = MORPH_RADIUS_BULGE * Math.sin(Math.PI * t) ** 2;
    const radius = startRadius + (endRadius - startRadius) * springStep(t) + bulge;

    frames.push({
      left: px(left),
      top: px(top),
      width: px(width),
      height: px(height),
      borderRadius: px(radius),
    });
  }

  return frames;
}

/**
 * 生成内容层的位置补偿关键帧：让卡片内容在视口里保持最终位置不动，
 * 由外壳从按钮位置长出来并逐步把它「揭开」。
 *
 * @param panelFrames buildMorphFrames 的返回值
 * @param contentLeft 内容层最终视口左坐标
 * @param contentTop  内容层最终视口上坐标
 * @param borderLeft  面板左边框宽度
 * @param borderTop   面板上边框宽度
 */
export function buildMorphContentFrames(
  panelFrames: Keyframe[],
  contentLeft: number,
  contentTop: number,
  borderLeft: number,
  borderTop: number,
): Keyframe[] {
  const steps = Math.max(1, panelFrames.length - 1);
  return panelFrames.map((frame, i) => {
    const left = Number.parseFloat(String(frame.left)) || 0;
    const top = Number.parseFloat(String(frame.top)) || 0;
    const tx = contentLeft - (left + borderLeft);
    const ty = contentTop - (top + borderTop);
    return {
      offset: i / steps,
      transform: `translate3d(${Math.round(tx * 100) / 100}px, ${Math.round(ty * 100) / 100}px, 0)`,
    };
  });
}

/** 读取面板当前圆角（可能是动画中的值）。 */
export function panelRadiusOf(el: Element): number {
  const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius);
  return Number.isFinite(radius) ? radius : 12;
}

/** 是否应跳过流体动效（系统减弱动效）。 */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}
