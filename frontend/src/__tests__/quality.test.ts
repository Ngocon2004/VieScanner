import { precheckImageQuality, summarizeHardIssues } from "@/lib/quality";

function imageFile(name = "card.png"): File {
  return new File(["mock"], name, { type: "image/png" });
}

function makePixels(width: number, height: number, rgba: [number, number, number, number]) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = rgba[0];
    data[i + 1] = rgba[1];
    data[i + 2] = rgba[2];
    data[i + 3] = rgba[3];
  }
  return data;
}

function mockImageAnalysis(
  width: number,
  height: number,
  rgba: [number, number, number, number] = [128, 128, 128, 255],
) {
  const close = vi.fn();
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn().mockResolvedValue({ width, height, close }),
  );

  const realCreateElement = document.createElement.bind(document);
  vi.spyOn(document, "createElement").mockImplementation(
    ((tagName: string, options?: ElementCreationOptions) => {
      if (tagName.toLowerCase() !== "canvas") {
        return realCreateElement(tagName, options);
      }

      const canvas = {
        width: 0,
        height: 0,
        getContext: vi.fn(() => ({
          drawImage: vi.fn(),
          getImageData: () => ({
            data: makePixels(
              Math.max(1, canvas.width),
              Math.max(1, canvas.height),
              rgba,
            ),
          }),
        })),
      };
      return canvas as unknown as HTMLCanvasElement;
    }) as typeof document.createElement,
  );
}

describe("precheckImageQuality", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("hard-rejects non-image files before upload", async () => {
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });

    const report = await precheckImageQuality(file);

    expect(report.accepted).toBe(false);
    expect(report.score).toBe(0);
    expect(report.issues).toEqual([
      expect.objectContaining({ code: "not_image", severity: "hard" }),
    ]);
    expect(summarizeHardIssues(report)).toContain("Tệp không phải ảnh");
  });

  it("passes through when browser-side image analysis fails", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockRejectedValue(new Error("decode failed")),
    );

    const report = await precheckImageQuality(imageFile());

    expect(report.accepted).toBe(true);
    expect(report.issues).toEqual([]);
    expect(report.metrics).toEqual({});
  });

  it("hard-rejects images with very low resolution", async () => {
    mockImageAnalysis(120, 90);

    const report = await precheckImageQuality(imageFile());

    expect(report.accepted).toBe(false);
    expect(report.metrics.min_side_px).toBe(90);
    expect(report.issues).toEqual([
      expect.objectContaining({ code: "low_resolution", severity: "hard" }),
    ]);
  });

  it("keeps bright/glare findings as soft warnings", async () => {
    mockImageAnalysis(1200, 760, [255, 255, 255, 255]);

    const report = await precheckImageQuality(imageFile());

    expect(report.accepted).toBe(true);
    expect(report.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "too_bright", severity: "soft" }),
        expect.objectContaining({ code: "glare", severity: "soft" }),
      ]),
    );
  });

  it("warns (soft) about blurry images measured at backend resolution", async () => {
    mockImageAnalysis(1200, 760);

    const report = await precheckImageQuality(imageFile());

    expect(report.accepted).toBe(true);
    expect(report.metrics.blur_var).toBe(0);
    expect(report.issues).toEqual([expect.objectContaining({ code: "blur", severity: "soft" })]);
  });
});
