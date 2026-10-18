/**
 * Đánh giá nhanh từng khung hình camera (đã thu nhỏ) để hướng dẫn người dùng và tự chụp.
 * Ngưỡng sáng/lóa dùng chung với tiền kiểm upload (`lib/quality.ts`); backend vẫn quyết định cuối.
 */

export const FRAME_SAMPLE_WIDTH = 320;

const DARK = 65;
const BRIGHT = 220;
const GLARE = 0.12;
// Phương sai Laplacian đo trên ảnh 320px; thấp hơn ngưỡng này coi như rung/mờ.
const SHARPNESS = 60;
// Chênh lệch luma trung bình giữa 2 khung liên tiếp; lớn hơn coi như tay đang di chuyển.
const MOTION = 6;

export const CARD_ASPECT = 85.6 / 54;
// Khung hướng dẫn rộng 4/5 khung hình, giữa màn hình (khớp overlay trong CameraScanner).
export const GUIDE_WIDTH_RATIO = 0.8;
// Viền thẻ được tìm trong dải ±12% quanh mỗi cạnh khung: thẻ không cần khớp khung tuyệt đối.
const EDGE_BAND = 0.12;
const EDGE_MIN_STRENGTH = 6;
const EDGE_MIN_CONTRAST = 2.5;
// Cần thấy ít nhất 3/4 cạnh thẻ (ngón tay có thể che 1 cạnh). Bề mặt có hoa văn (bàn phím,
// mặt bàn) không tạo được đường thẳng liên tục dọc cạnh khung nên không làm tự chụp.
const MIN_CARD_SIDES = 3;

export const AUTO_CAPTURE_STABLE_FRAMES = 5;

export type FrameIssue = "too_dark" | "too_bright" | "glare" | "blurry" | "moving" | "no_card";

export interface FrameAssessment {
  luma: Float32Array;
  brightness: number;
  glare: number;
  sharpness: number;
  motion: number;
  cardSides: number;
  issues: FrameIssue[];
  ok: boolean;
}

export const FRAME_ISSUE_MESSAGES: Record<FrameIssue, string> = {
  too_dark: "Thiếu sáng, hãy ra chỗ sáng hơn",
  too_bright: "Quá sáng, tránh chiếu đèn thẳng vào thẻ",
  glare: "Bị lóa, nghiêng nhẹ thẻ",
  blurry: "Ảnh mờ, đưa thẻ gần hơn hoặc giữ yên",
  moving: "Giữ yên điện thoại",
  no_card: "Đưa thẻ vào vừa khung",
};

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function guideRect(width: number, height: number): Rect {
  const w = Math.min(width * GUIDE_WIDTH_RATIO, height * CARD_ASPECT);
  const h = w / CARD_ASPECT;
  return { x: (width - w) / 2, y: (height - h) / 2, width: w, height: h };
}

export function toLuma(data: Uint8ClampedArray): Float32Array {
  const luma = new Float32Array(data.length / 4);
  for (let i = 0, p = 0; i < data.length; i += 4, p += 1) {
    luma[p] = 0.299 * (data[i] ?? 0) + 0.587 * (data[i + 1] ?? 0) + 0.114 * (data[i + 2] ?? 0);
  }
  return luma;
}

/** Phương sai Laplacian 4 lân cận (giống cv2.Laplacian ksize=1), tuỳ chọn chỉ trong `rect`. */
export function laplacianVariance(
  luma: Float32Array,
  width: number,
  height: number,
  rect?: Rect,
): number {
  const x0 = Math.max(1, Math.floor(rect?.x ?? 0));
  const y0 = Math.max(1, Math.floor(rect?.y ?? 0));
  const x1 = Math.min(width - 1, Math.ceil(rect ? rect.x + rect.width : width));
  const y1 = Math.min(height - 1, Math.ceil(rect ? rect.y + rect.height : height));
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const i = y * width + x;
      const v =
        (luma[i - width] ?? 0) + (luma[i + width] ?? 0) + (luma[i - 1] ?? 0) + (luma[i + 1] ?? 0) -
        4 * (luma[i] ?? 0);
      sum += v;
      sumSq += v * v;
      n += 1;
    }
  }
  if (n === 0) return 0;
  const mean = sum / n;
  return sumSq / n - mean * mean;
}

/**
 * Cạnh khung có viền thẻ không: chiếu gradient vuông góc với cạnh lên trục ngang dải tìm kiếm.
 * Một đường thẳng dài cho đỉnh rõ so với nền phía ngoài khung (phía trong là chữ trên thẻ);
 * hoa văn rải rác thì bị trung bình hoá nên không tạo đỉnh.
 */
function hasStraightEdge(
  luma: Float32Array,
  width: number,
  height: number,
  vertical: boolean,
  at: number,
  outward: -1 | 1,
  band: number,
  from: number,
  to: number,
): boolean {
  const limit = vertical ? width : height;
  const lo = Math.max(1, Math.round(at - band));
  const hi = Math.min(limit - 2, Math.round(at + band));
  const start = Math.max(0, Math.round(from));
  const end = Math.min(vertical ? height : width, Math.round(to));
  if (hi - lo < 3 || end - start < 4) return false;
  const profile: number[] = [];
  for (let p = lo; p <= hi; p += 1) {
    let total = 0;
    for (let q = start; q < end; q += 1) {
      const i = vertical ? q * width + p : p * width + q;
      const step = vertical ? 1 : width;
      total += Math.abs((luma[i + step] ?? 0) - (luma[i - step] ?? 0)) / 2;
    }
    profile.push(total / (end - start));
  }
  // Làm mượt 3 điểm để thẻ hơi nghiêng (viền trải qua vài cột) vẫn cho đỉnh.
  const smooth = profile.map(
    (v, k) => (v + (profile[k - 1] ?? v) + (profile[k + 1] ?? v)) / 3,
  );
  const outside = smooth.filter((_, k) => (lo + k - at) * outward > 0);
  const baseline = outside.length >= 3 ? outside : smooth;
  const median = [...baseline].sort((a, b) => a - b)[Math.floor(baseline.length / 2)] ?? 0;
  const peak = Math.max(...smooth);
  return peak >= EDGE_MIN_STRENGTH && peak >= EDGE_MIN_CONTRAST * Math.max(median, 1);
}

export function countCardSides(luma: Float32Array, width: number, height: number): number {
  const g = guideRect(width, height);
  const bandX = g.width * EDGE_BAND;
  const bandY = g.height * EDGE_BAND;
  const sides = [
    hasStraightEdge(luma, width, height, true, g.x, -1, bandX, g.y + 0.15 * g.height, g.y + 0.85 * g.height),
    hasStraightEdge(luma, width, height, true, g.x + g.width, 1, bandX, g.y + 0.15 * g.height, g.y + 0.85 * g.height),
    hasStraightEdge(luma, width, height, false, g.y, -1, bandY, g.x + 0.15 * g.width, g.x + 0.85 * g.width),
    hasStraightEdge(luma, width, height, false, g.y + g.height, 1, bandY, g.x + 0.15 * g.width, g.x + 0.85 * g.width),
  ];
  return sides.filter(Boolean).length;
}

function meanAbsDiff(a: Float32Array, b: Float32Array): number {
  if (a.length !== b.length || a.length === 0) return Number.POSITIVE_INFINITY;
  let total = 0;
  for (let i = 0; i < a.length; i += 1) total += Math.abs((a[i] ?? 0) - (b[i] ?? 0));
  return total / a.length;
}

export function assessFrame(
  data: Uint8ClampedArray,
  width: number,
  height: number,
  previous: Float32Array | null,
): FrameAssessment {
  const luma = toLuma(data);
  let total = 0;
  let nearWhite = 0;
  for (const v of luma) {
    total += v;
    if (v >= 250) nearWhite += 1;
  }
  const brightness = luma.length ? total / luma.length : 0;
  const glare = luma.length ? nearWhite / luma.length : 0;
  // Độ nét đo trong khung thẻ: nền mờ (xoá phông) không được kéo tụt điểm của thẻ.
  const sharpness = laplacianVariance(luma, width, height, guideRect(width, height));
  const cardSides = countCardSides(luma, width, height);
  const motion = previous ? meanAbsDiff(luma, previous) : Number.POSITIVE_INFINITY;

  // "no_card" đứng đầu: đây là thông báo hướng dẫn hữu ích nhất khi chưa có thẻ trong khung.
  const issues: FrameIssue[] = cardSides < MIN_CARD_SIDES ? ["no_card"] : [];
  if (brightness < DARK) issues.push("too_dark");
  else if (brightness > BRIGHT) issues.push("too_bright");
  if (glare > GLARE) issues.push("glare");
  if (sharpness < SHARPNESS) issues.push("blurry");
  if (motion > MOTION) issues.push("moving");

  return { luma, brightness, glare, sharpness, motion, cardSides, issues, ok: issues.length === 0 };
}
