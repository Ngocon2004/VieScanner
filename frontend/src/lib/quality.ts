"use client";

import { laplacianVariance, toLuma } from "@/lib/frameQuality";
import type { QualityIssue, QualityReport } from "@/lib/schemas";

/**
 * Kiểm tra nhanh chất lượng ảnh phía client để phản hồi tức thì + tránh upload
 * ảnh chắc chắn không đạt. Đây CHỈ là tiền kiểm; backend mới là nguồn quyết định
 * cuối cùng (gồm cả kiểm tra "có phải thẻ CCCD" bằng YOLO – không chạy được ở FE).
 *
 * Quan điểm: chỉ HARD-reject khi rất chắc chắn (không phải ảnh / độ phân giải quá
 * nhỏ). Các yếu tố phụ thuộc điều kiện chụp (sáng/tối/lóa) chỉ cảnh báo (soft) và
 * vẫn upload để backend quyết định.
 */

// Ngưỡng đồng bộ với backend defaults (backend/app/core/config.py).
const MIN_SIDE_HARD = 320;
const MIN_SIDE_SOFT = 640;
const DARK_SOFT = 65;
const BRIGHT_SOFT = 220;
const GLARE_SOFT = 0.12;

// Mẫu nhỏ để tính brightness/glare nhanh (không cần full-res).
const SAMPLE_MAX_SIDE = 256;
// Độ nét phải đo ở đúng độ phân giải backend xử lý (OCR_MAX_IMAGE_SIDE_PX): thu nhỏ ảnh làm
// ảnh mờ trông nét. Trên 63 ảnh thật, Laplacian vùng giữa 60% tương quan hạng 0.91 với
// blur_var của backend và ngưỡng 100 không cảnh báo oan ảnh nào.
const BLUR_MAX_SIDE = 2000;
const BLUR_CENTER_CROP = 0.6;
const BLUR_SOFT = 100;

interface LoadedImage {
  source: CanvasImageSource;
  width: number;
  height: number;
  close: () => void;
}

async function loadImageSource(file: File): Promise<LoadedImage> {
  if (typeof createImageBitmap === "function") {
    const bmp = await createImageBitmap(file);
    return { source: bmp, width: bmp.width, height: bmp.height, close: () => bmp.close() };
  }
  const url = URL.createObjectURL(file);
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const im = new Image();
    im.onload = () => resolve(im);
    im.onerror = () => reject(new Error("image load failed"));
    im.src = url;
  });
  return {
    source: img,
    width: img.naturalWidth,
    height: img.naturalHeight,
    close: () => URL.revokeObjectURL(url),
  };
}

interface ImageStats {
  width: number;
  height: number;
  brightness: number;
  glare: number;
  sharpness: number | null;
}

function centerSharpness(source: CanvasImageSource, width: number, height: number): number | null {
  const scale = Math.min(1, BLUR_MAX_SIDE / Math.max(width, height, 1));
  const sw = width * BLUR_CENTER_CROP;
  const sh = height * BLUR_CENTER_CROP;
  const dw = Math.max(3, Math.round(sw * scale));
  const dh = Math.max(3, Math.round(sh * scale));
  const canvas = document.createElement("canvas");
  canvas.width = dw;
  canvas.height = dh;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(source, (width - sw) / 2, (height - sh) / 2, sw, sh, 0, 0, dw, dh);
  return laplacianVariance(toLuma(ctx.getImageData(0, 0, dw, dh).data), dw, dh);
}

async function analyzeImage(file: File): Promise<ImageStats> {
  const loaded = await loadImageSource(file);
  try {
    const { width, height } = loaded;
    const scale = Math.min(1, SAMPLE_MAX_SIDE / Math.max(width, height, 1));
    const sw = Math.max(1, Math.round(width * scale));
    const sh = Math.max(1, Math.round(height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = sw;
    canvas.height = sh;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no 2d context");
    ctx.drawImage(loaded.source, 0, 0, sw, sh);

    const { data } = ctx.getImageData(0, 0, sw, sh);
    const pixels = sw * sh;
    let lumaSum = 0;
    let nearWhite = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      const luma = 0.299 * r + 0.587 * g + 0.114 * b;
      lumaSum += luma;
      if (luma >= 250) nearWhite += 1;
    }
    const tooSmall = Math.min(width, height) < MIN_SIDE_HARD;
    return {
      width,
      height,
      brightness: pixels > 0 ? lumaSum / pixels : 0,
      glare: pixels > 0 ? nearWhite / pixels : 0,
      sharpness: tooSmall ? null : centerSharpness(loaded.source, width, height),
    };
  } finally {
    loaded.close();
  }
}

function scoreFromIssues(issues: QualityIssue[]): number {
  let score = 1;
  for (const issue of issues) score -= issue.severity === "hard" ? 0.35 : 0.12;
  return Math.max(0, Math.min(1, Number(score.toFixed(3))));
}

export async function precheckImageQuality(file: File): Promise<QualityReport> {
  if (!file.type.startsWith("image/")) {
    return {
      accepted: false,
      score: 0,
      issues: [
        { code: "not_image", severity: "hard", message: "Tệp không phải ảnh hợp lệ.", metric: null, threshold: null },
      ],
      metrics: {},
    };
  }

  let stats: ImageStats;
  try {
    stats = await analyzeImage(file);
  } catch {
    // Không phân tích được ở client -> nhường backend quyết định (coi như đạt).
    return { accepted: true, score: 1, issues: [], metrics: {} };
  }

  const issues: QualityIssue[] = [];
  const minSide = Math.min(stats.width, stats.height);

  if (minSide < MIN_SIDE_HARD) {
    issues.push({
      code: "low_resolution", severity: "hard",
      message: `Ảnh quá nhỏ (cạnh ngắn ${minSide}px). Hãy dùng ảnh nét và lớn hơn.`,
      metric: minSide, threshold: MIN_SIDE_HARD,
    });
  } else if (minSide < MIN_SIDE_SOFT) {
    issues.push({
      code: "low_resolution", severity: "soft",
      message: `Độ phân giải hơi thấp (cạnh ngắn ${minSide}px).`,
      metric: minSide, threshold: MIN_SIDE_SOFT,
    });
  }

  if (stats.brightness < DARK_SOFT) {
    issues.push({
      code: "too_dark", severity: "soft",
      message: "Ảnh hơi tối, nên chụp ở nơi đủ sáng.",
      metric: Math.round(stats.brightness), threshold: DARK_SOFT,
    });
  } else if (stats.brightness > BRIGHT_SOFT) {
    issues.push({
      code: "too_bright", severity: "soft",
      message: "Ảnh hơi sáng/chói, có thể mất chi tiết vùng chữ.",
      metric: Math.round(stats.brightness), threshold: BRIGHT_SOFT,
    });
  }

  if (stats.glare > GLARE_SOFT) {
    issues.push({
      code: "glare", severity: "soft",
      message: "Có thể bị lóa/chói trên bề mặt thẻ.",
      metric: Number(stats.glare.toFixed(3)), threshold: GLARE_SOFT,
    });
  }

  if (stats.sharpness !== null && stats.sharpness < BLUR_SOFT) {
    issues.push({
      code: "blur", severity: "soft",
      message: "Ảnh có thể bị mờ, chữ trên thẻ có thể đọc sai.",
      metric: Math.round(stats.sharpness), threshold: BLUR_SOFT,
    });
  }

  const accepted = !issues.some((i) => i.severity === "hard");
  return {
    accepted,
    score: scoreFromIssues(issues),
    issues,
    metrics: {
      min_side_px: minSide,
      brightness: Math.round(stats.brightness),
      glare_ratio: Number(stats.glare.toFixed(4)),
      ...(stats.sharpness !== null ? { blur_var: Math.round(stats.sharpness) } : {}),
    },
  };
}

export function summarizeHardIssues(report: QualityReport | null | undefined): string {
  if (!report) return "";
  return report.issues
    .filter((i) => i.severity === "hard")
    .map((i) => i.message)
    .join(" ");
}
