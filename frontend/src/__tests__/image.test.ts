import { batchTimeoutMs } from "@/lib/api";
import { planCompression } from "@/lib/compressPlan";
import { isAcceptedImage, isHeicImage, prepareImageForUpload, uploadKind } from "@/lib/image";

describe("image type helpers", () => {
  it("accepts backend-supported MIME types and rejects others", () => {
    expect(isAcceptedImage(new File([""], "a.jpg", { type: "image/jpeg" }))).toBe(true);
    expect(isAcceptedImage(new File([""], "a.webp", { type: "image/webp" }))).toBe(true);
    expect(isAcceptedImage(new File([""], "a.gif", { type: "image/gif" }))).toBe(false);
    expect(isAcceptedImage(new File([""], "a.heic", { type: "image/heic" }))).toBe(false);
  });

  it("falls back to the file extension when the browser gives no MIME type", () => {
    expect(isAcceptedImage(new File([""], "scan.PNG", { type: "" }))).toBe(true);
    expect(isAcceptedImage(new File([""], "notes.txt", { type: "" }))).toBe(false);
  });

  it("detects HEIC/HEIF by type or extension", () => {
    expect(isHeicImage(new File([""], "x", { type: "image/heif" }))).toBe(true);
    expect(isHeicImage(new File([""], "IMG_1.HEIC", { type: "" }))).toBe(true);
    expect(isHeicImage(new File([""], "a.jpg", { type: "image/jpeg" }))).toBe(false);
  });

  it("classifies upload kinds", () => {
    expect(uploadKind(new File([""], "a.jpg", { type: "image/jpeg" }))).toBe("image");
    expect(uploadKind(new File([""], "a.heic", { type: "" }))).toBe("heic");
    expect(uploadKind(new File([""], "a.PDF", { type: "" }))).toBe("pdf");
    expect(uploadKind(new File([""], "a.zip", { type: "application/zip" }))).toBeNull();
  });

  it("passes HEIC and PDF through untouched for backend conversion", async () => {
    const pdf = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
    expect(await prepareImageForUpload(pdf)).toBe(pdf);
  });
});

describe("planCompression", () => {
  const opts = { maxSidePx: 2000, minCompressBytes: 600 * 1024 };

  it("resizes when the longest side exceeds the limit", () => {
    expect(planCompression(4000, 3000, 100, opts)).toEqual({ width: 2000, height: 1500, resized: true });
  });

  it("recompresses large files without resizing", () => {
    expect(planCompression(1500, 1000, 700 * 1024, opts)).toEqual({ width: 1500, height: 1000, resized: false });
  });

  it("skips small images", () => {
    expect(planCompression(1500, 1000, 100 * 1024, opts)).toBeNull();
  });
});

describe("batchTimeoutMs", () => {
  it("keeps the base timeout for small batches and scales for large ones", () => {
    expect(batchTimeoutMs(1)).toBe(120_000);
    expect(batchTimeoutMs(20)).toBe(600_000);
  });
});

describe("prepareImageForUpload worker fallback", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("abandons a worker that never answers and falls back to the main thread", async () => {
    vi.useFakeTimers();
    const terminate = vi.fn();
    vi.stubGlobal("OffscreenCanvas", class {});
    vi.stubGlobal(
      "Worker",
      class {
        onmessage = null;
        onerror = null;
        postMessage() {}
        terminate = terminate;
      },
    );
    vi.stubGlobal(
      "Image",
      class {
        onerror: (() => void) | null = null;
        set src(_: string) {
          queueMicrotask(() => this.onerror?.());
        }
      },
    );
    const { prepareImageForUpload: prepare } = await import("@/lib/image");
    const file = new File(["x"], "card.jpg", { type: "image/jpeg" });

    const result = prepare(file);
    await vi.advanceTimersByTimeAsync(20_000);

    await expect(result).resolves.toBe(file);
    expect(terminate).toHaveBeenCalledOnce();
  });
});
