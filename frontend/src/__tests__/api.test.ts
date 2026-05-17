import { APIError, exportToExcel, extractCCCD } from "@/lib/api";
import type { CCCDData } from "@/lib/schemas";

const VALID_DATA: CCCDData = {
  id_number: "001202000123",
  full_name: "NGUYEN VAN A",
  dob: "01/01/2002",
  gender: "Nam",
  nationality: "Viet Nam",
  origin: "Quan 1, TP HCM",
  residence: "123 Le Loi, Quan 1, TP HCM",
  expiry_date: "01/01/2030",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("extractCCCD returns parsed payload on success", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({ data: VALID_DATA, confidences: { id_number: 0.93 } }),
      );

    const file = new File(["mock"], "card.png", { type: "image/png" });
    const result = await extractCCCD(file);

    expect(result.data.id_number).toBe("001202000123");
    expect(result.confidences.id_number).toBe(0.93);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/extract"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("extractCCCD throws APIError with backend details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(
        {
          code: "image_invalid",
          message: "Bad image",
          request_id: "req-1",
          details: [],
        },
        400,
      ),
    );

    const file = new File(["mock"], "card.png", { type: "image/png" });
    await expect(extractCCCD(file)).rejects.toMatchObject({
      name: "APIError",
      code: "image_invalid",
      requestId: "req-1",
      status: 400,
    });
  });

  it("extractCCCD throws invalid_response when body shape is wrong", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ unexpected: true }, 200),
    );

    const file = new File(["mock"], "card.png", { type: "image/png" });
    await expect(extractCCCD(file)).rejects.toMatchObject({
      name: "APIError",
      code: "invalid_response",
      status: 200,
    });
  });

  it("exportToExcel uses filename from Content-Disposition header", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("excel-bytes", {
        status: 200,
        headers: {
          "Content-Type":
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition":
            "attachment; filename*=UTF-8''CCCD_%E1%BA%A3nh.xlsx",
        },
      }),
    );

    vi.spyOn(global.URL, "createObjectURL").mockReturnValue("blob:mock");
    const revokeSpy = vi
      .spyOn(global.URL, "revokeObjectURL")
      .mockImplementation(() => {});
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    const appendSpy = vi.spyOn(document.body, "appendChild");
    const removeSpy = vi.spyOn(document.body, "removeChild");

    await exportToExcel(VALID_DATA);

    const anchor = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("CCCD_ảnh.xlsx");
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(removeSpy).toHaveBeenCalledTimes(1);
    expect(revokeSpy).toHaveBeenCalledWith("blob:mock");
  });

  it("exportToExcel falls back to generated filename when header is missing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("excel-bytes", {
        status: 200,
        headers: {
          "Content-Type":
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
      }),
    );

    vi.spyOn(global.URL, "createObjectURL").mockReturnValue("blob:mock");
    vi.spyOn(global.URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const appendSpy = vi.spyOn(document.body, "appendChild");

    await exportToExcel(VALID_DATA);

    const anchor = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("CCCD_NGUYEN_VAN_A.xlsx");
  });

  it("exportToExcel throws APIError on failed export request", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(
        {
          code: "excel_failed",
          message: "Cannot generate",
          request_id: "req-export",
        },
        500,
      ),
    );

    await expect(exportToExcel(VALID_DATA)).rejects.toBeInstanceOf(APIError);
  });
});
