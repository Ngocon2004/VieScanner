export interface CompressRequest {
  id: number;
  file: Blob;
  maxSidePx: number;
  minCompressBytes: number;
  jpegQuality: number;
}

export interface CompressResponse {
  id: number;
  blob?: Blob;
  unchanged?: boolean;
  error?: string;
}

export interface CompressionPlan {
  width: number;
  height: number;
  resized: boolean;
}

/** Quyết định có cần nén/resize không; dùng chung cho Web Worker và main thread. */
export function planCompression(
  width: number,
  height: number,
  sizeBytes: number,
  options: { maxSidePx: number; minCompressBytes: number },
): CompressionPlan | null {
  if (width <= 0 || height <= 0) return null;
  const longest = Math.max(width, height);
  const resized = options.maxSidePx > 0 && longest > options.maxSidePx;
  if (!resized && sizeBytes < options.minCompressBytes) return null;
  const scale = resized ? options.maxSidePx / longest : 1;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
    resized,
  };
}

/**
 * Chạy trong Web Worker. Hàm này được chuyển thành chuỗi mã nguồn để dựng worker, nên
 * chỉ được dùng tham số và API toàn cục của worker (không tham chiếu biến/import khác).
 */
export async function runCompression(
  request: CompressRequest,
  plan: typeof planCompression,
): Promise<CompressResponse> {
  const { id, file, maxSidePx, minCompressBytes, jpegQuality } = request;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    try {
      const target = plan(bitmap.width, bitmap.height, file.size, { maxSidePx, minCompressBytes });
      if (!target) return { id, unchanged: true };
      const canvas = new OffscreenCanvas(target.width, target.height);
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, target.width, target.height);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(bitmap, 0, 0, target.width, target.height);
      const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: jpegQuality });
      if (!target.resized && blob.size >= file.size * 0.98) return { id, unchanged: true };
      return { id, blob };
    } finally {
      bitmap.close();
    }
  } catch (err) {
    return { id, error: err instanceof Error ? err.message : String(err) };
  }
}

export function compressWorkerSource(): string {
  return [
    `const plan = (${planCompression.toString()});`,
    `const run = (${runCompression.toString()});`,
    "self.onmessage = async (event) => { self.postMessage(await run(event.data, plan)); };",
  ].join("\n");
}
