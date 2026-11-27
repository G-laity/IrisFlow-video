/**
 * 生成 Liquid Glass 透镜位移图（纯 Canvas 2D）。
 *
 * 思路来自 shuding/liquid-glass 与 rdev/liquid-glass-react（MIT）：
 * 圆角矩形 SDF + smoothStep 把 UV 向中心压缩，中心保持中性，边缘产生透镜弯曲。
 * 输出贴图：R = x 位移，G/B = y 位移，0.5 为中性。
 *
 * 位移图只生成一次，所有 .glass-card 共用；SVG feImage 会把它拉伸到卡片尺寸。
 */

let cached = "";

function smoothStep(a: number, b: number, t: number): number {
  const x = Math.max(0, Math.min(1, (t - a) / (b - a)));
  return x * x * (3 - 2 * x);
}

function roundedRectSDF(x: number, y: number, w: number, h: number, r: number): number {
  const qx = Math.abs(x) - w + r;
  const qy = Math.abs(y) - h + r;
  const ax = Math.max(qx, 0);
  const ay = Math.max(qy, 0);
  return Math.min(Math.max(qx, qy), 0) + Math.sqrt(ax * ax + ay * ay) - r;
}

export function getGlassLensMap(size = 256): string {
  if (cached) return cached;
  if (typeof document === "undefined") return "";

  const w = size;
  const h = size;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";

  const image = ctx.createImageData(w, h);
  const data = image.data;
  const raw = new Float32Array(w * h * 2);
  let maxScale = 1;
  let index = 0;

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const u = x / w;
      const v = y / h;
      const ix = u - 0.5;
      const iy = v - 0.5;
      const distanceToEdge = roundedRectSDF(ix, iy, 0.3, 0.2, 0.6);
      const displacement = smoothStep(0.8, 0, distanceToEdge - 0.15);
      const scaled = smoothStep(0, 1, displacement);
      const px = ix * scaled + 0.5;
      const py = iy * scaled + 0.5;
      const dx = px * w - x;
      const dy = py * h - y;
      raw[index++] = dx;
      raw[index++] = dy;
      maxScale = Math.max(maxScale, Math.abs(dx), Math.abs(dy));
    }
  }

  index = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const dx = raw[index++];
      const dy = raw[index++];
      // 贴图边缘平滑，避免滤镜边界硬切
      const edgeDistance = Math.min(x, y, w - x - 1, h - y - 1);
      const edgeFactor = Math.min(1, edgeDistance / 2);
      const r = (dx * edgeFactor) / maxScale + 0.5;
      const g = (dy * edgeFactor) / maxScale + 0.5;
      const p = (y * w + x) * 4;
      data[p] = Math.max(0, Math.min(255, r * 255));
      data[p + 1] = Math.max(0, Math.min(255, g * 255));
      data[p + 2] = Math.max(0, Math.min(255, g * 255));
      data[p + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);
  cached = canvas.toDataURL("image/png");
  return cached;
}
