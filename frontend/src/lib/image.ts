const DEFAULT_MAX_SIDE_PX = 2000;
const DEFAULT_MIN_COMPRESS_BYTES = 600 * 1024;
const DEFAULT_JPEG_QUALITY = 0.9;

function getEnvNumber(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
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

export async function prepareImageForUpload(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) return file;

  const maxSidePx = Math.max(
    0,
    Math.round(getEnvNumber("NEXT_PUBLIC_MAX_UPLOAD_SIDE_PX", DEFAULT_MAX_SIDE_PX)),
  );
  const minCompressBytes = Math.max(
    0,
    Math.round(
      getEnvNumber("NEXT_PUBLIC_MIN_COMPRESS_BYTES", DEFAULT_MIN_COMPRESS_BYTES),
    ),
  );
  const jpegQuality = clamp(
    getEnvNumber("NEXT_PUBLIC_UPLOAD_JPEG_QUALITY", DEFAULT_JPEG_QUALITY),
    0.5,
    0.98,
  );

  if (maxSidePx <= 0 && file.size < minCompressBytes) return file;

  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await loadImage(objectUrl);
    const sourceW = img.naturalWidth || img.width;
    const sourceH = img.naturalHeight || img.height;
    if (sourceW <= 0 || sourceH <= 0) return file;

    const longest = Math.max(sourceW, sourceH);
    const shouldResize = maxSidePx > 0 && longest > maxSidePx;
    const shouldCompress = shouldResize || file.size >= minCompressBytes;
    if (!shouldCompress) return file;

    const scale = shouldResize ? maxSidePx / longest : 1;
    const targetW = Math.max(1, Math.round(sourceW * scale));
    const targetH = Math.max(1, Math.round(sourceH * scale));

    const canvas = document.createElement("canvas");
    canvas.width = targetW;
    canvas.height = targetH;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, targetW, targetH);

    const preferJpeg = file.type === "image/jpeg" || file.type === "image/jpg";
    const outType = preferJpeg ? "image/jpeg" : file.type;
    const blob = await canvasToBlob(canvas, outType, jpegQuality);
    if (!blob) return file;

    if (!shouldResize && blob.size >= file.size * 0.98) return file;

    const outExt = outType === "image/png" ? "png" : outType === "image/webp" ? "webp" : "jpg";
    const outName = renameWithExt(file.name, outExt);
    return new File([blob], outName, {
      type: outType,
      lastModified: file.lastModified,
    });
  } catch {
    return file;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
