import {
  compressWorkerSource,
  planCompression,
  type CompressRequest,
  type CompressResponse,
} from "@/lib/compressPlan";

const DEFAULT_MAX_SIDE_PX = 2000;
const DEFAULT_MIN_COMPRESS_BYTES = 600 * 1024;
const DEFAULT_JPEG_QUALITY = 0.9;
const DEFAULT_MAX_REQUEST_MB = 100;

// Phải khớp ALLOWED_MIME_TYPES_RAW ở backend: các định dạng ảnh nén được trên trình duyệt.
export const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

// Định dạng Job API nhận: ảnh thường + HEIC (iPhone) + PDF; backend tự chuyển HEIC/PDF.
export const UPLOAD_ACCEPT = [
  ...ACCEPTED_IMAGE_TYPES,
  "image/heic",
  "image/heif",
  ".heic",
  ".heif",
  "application/pdf",
  ".pdf",
].join(",");

export type UploadKind = "image" | "heic" | "pdf";

const EXTENSION_TO_TYPE: Record<string, (typeof ACCEPTED_IMAGE_TYPES)[number]> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
};

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot + 1).toLowerCase() : "";
}

export function isAcceptedImage(file: File): boolean {
  if (file.type) return (ACCEPTED_IMAGE_TYPES as readonly string[]).includes(file.type);
  return extensionOf(file.name) in EXTENSION_TO_TYPE;
}

export function isHeicImage(file: File): boolean {
  return /^image\/hei[cf]$/.test(file.type) || ["heic", "heif"].includes(extensionOf(file.name));
}

export function isPdfFile(file: File): boolean {
  return file.type === "application/pdf" || extensionOf(file.name) === "pdf";
}

export function uploadKind(file: File): UploadKind | null {
  if (isAcceptedImage(file)) return "image";
  if (isHeicImage(file)) return "heic";
  if (isPdfFile(file)) return "pdf";
  return null;
}

// Gọi với `process.env.NEXT_PUBLIC_X` viết nguyên văn: Next.js chỉ nhúng giá trị vào bundle trình duyệt
// khi tên biến viết thẳng; `process.env[name]` luôn ra undefined ở client nên env bị bỏ qua.
function envNumber(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback;
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}

/** Tổng dung lượng tối đa của 1 lần gửi; phải khớp MAX_REQUEST_MB ở backend. */
export function maxRequestBytes(): number {
  const mb = envNumber(process.env.NEXT_PUBLIC_MAX_REQUEST_MB, DEFAULT_MAX_REQUEST_MB);
  return Math.max(1, mb) * 1024 * 1024;
}

function clamp(num: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, num));
}

function renameWithExt(filename: string, ext: string): string {
  const dot = filename.lastIndexOf(".");
  const base = dot > 0 ? filename.slice(0, dot) : filename;
  return `${base}.${ext}`;
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Cannot decode image"));
    img.src = url;
  });
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), type, quality);
  });
}

// File kéo-thả đôi khi không có `type`; tiền kiểm và nén dựa vào type nên gán lại theo đuôi.
function withImageType(file: File): File {
  const inferred = EXTENSION_TO_TYPE[extensionOf(file.name)];
  if (file.type || !inferred) return file;
  return new File([file], file.name, { type: inferred, lastModified: file.lastModified });
}

function compressionOptions(): Omit<CompressRequest, "id" | "file"> {
  return {
    maxSidePx: Math.max(
      0,
      Math.round(envNumber(process.env.NEXT_PUBLIC_MAX_UPLOAD_SIDE_PX, DEFAULT_MAX_SIDE_PX)),
    ),
    minCompressBytes: Math.max(
      0,
      Math.round(envNumber(process.env.NEXT_PUBLIC_MIN_COMPRESS_BYTES, DEFAULT_MIN_COMPRESS_BYTES)),
    ),
    jpegQuality: clamp(
      envNumber(process.env.NEXT_PUBLIC_UPLOAD_JPEG_QUALITY, DEFAULT_JPEG_QUALITY),
      0.5,
      0.98,
    ),
  };
}

function toJpegFile(blob: Blob, original: File): File {
  return new File([blob], renameWithExt(original.name, "jpg"), {
    type: "image/jpeg",
    lastModified: original.lastModified,
  });
}

// Worker treo (không trả lời, không báo lỗi) thì bỏ hẳn, nén trên main thread.
const WORKER_TIMEOUT_MS = 20_000;

let worker: Worker | null = null;
let workerBroken = false;
let nextRequestId = 0;
const pending = new Map<number, (response: CompressResponse) => void>();

function abandonWorker(reason: string): void {
  workerBroken = true;
  worker?.terminate();
  worker = null;
  for (const [id, resolve] of pending) resolve({ id, error: reason });
  pending.clear();
}

function getWorker(): Worker | null {
  if (workerBroken || typeof Worker === "undefined" || typeof OffscreenCanvas === "undefined") {
    return null;
  }
  if (!worker) {
    try {
      // Dựng worker từ Blob URL: Turbopack hiện chép nguyên file `.ts` của
      // `new Worker(new URL(...))` thành asset thay vì biên dịch, nên worker sẽ không chạy.
      const url = URL.createObjectURL(
        new Blob([compressWorkerSource()], { type: "text/javascript" }),
      );
      worker = new Worker(url);
      worker.onmessage = (event: MessageEvent<CompressResponse>) => {
        pending.get(event.data.id)?.(event.data);
        pending.delete(event.data.id);
      };
      worker.onerror = () => abandonWorker("worker crashed");
    } catch {
      workerBroken = true;
      return null;
    }
  }
  return worker;
}

function compressInWorker(file: File): Promise<CompressResponse> | null {
  const w = getWorker();
  if (!w) return null;
  const id = ++nextRequestId;
  return new Promise((resolve) => {
    const timer = setTimeout(() => abandonWorker("worker timeout"), WORKER_TIMEOUT_MS);
    pending.set(id, (response) => {
      clearTimeout(timer);
      resolve(response);
    });
    w.postMessage({ id, file, ...compressionOptions() } satisfies CompressRequest);
  });
}

async function compressOnMainThread(file: File): Promise<File> {
  const { maxSidePx, minCompressBytes, jpegQuality } = compressionOptions();
  if (maxSidePx <= 0 && file.size < minCompressBytes) return file;

  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await loadImage(objectUrl);
    const plan = planCompression(
      img.naturalWidth || img.width,
      img.naturalHeight || img.height,
      file.size,
      { maxSidePx, minCompressBytes },
    );
    if (!plan) return file;

    const canvas = document.createElement("canvas");
    canvas.width = plan.width;
    canvas.height = plan.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    // Luôn xuất JPEG: PNG lớn sau resize vẫn có thể vượt MAX_UPLOAD_SIZE_MB của backend,
    // còn Safari không encode được WebP. Nền trắng để vùng trong suốt không thành đen.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, plan.width, plan.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, plan.width, plan.height);

    const blob = await canvasToBlob(canvas, "image/jpeg", jpegQuality);
    if (!blob) return file;
    if (!plan.resized && blob.size >= file.size * 0.98) return file;
    return toJpegFile(blob, file);
  } catch {
    return file;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

/** Resize/nén ảnh trước khi upload. HEIC/PDF giữ nguyên để backend chuyển đổi. */
export async function prepareImageForUpload(input: File): Promise<File> {
  const file = withImageType(input);
  if (!isAcceptedImage(file)) return file;

  // Ưu tiên Web Worker để giải mã/nén ảnh lớn không làm đứng giao diện.
  const fromWorker = compressInWorker(file);
  if (fromWorker) {
    const response = await fromWorker;
    if (response.blob) return toJpegFile(response.blob, file);
    if (response.unchanged) return file;
  }
  return compressOnMainThread(file);
}
