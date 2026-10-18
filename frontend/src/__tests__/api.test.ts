import {
  APIError,
  exportListToExcel,
  extractBatch,
  extractCCCD,
  AUTH_EXPIRED_EVENT,
  TOKEN_STORAGE_KEY,
  getScans,
  isAbortError,
} from "@/lib/api";
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
    vi.useRealTimers();
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

  it("extractBatch posts multiple files and parses per-item quality", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        total: 2,
        accepted_count: 1,
        rejected_count: 1,
        results: [
          {
            index: 0,
            filename: "ok.png",
            accepted: true,
            status: "extracted",
            quality: { accepted: true, score: 1, issues: [], metrics: { min_side_px: 760 } },
            data: VALID_DATA,
            confidences: { id_number: 0.99 },
            scan_id: "scan-ok",
            error_code: null,
            error_message: null,
          },
          {
            index: 1,
            filename: "bad.png",
            accepted: false,
            status: "rejected",
            quality: {
              accepted: false,
              score: 0.65,
              issues: [
                {
                  code: "low_resolution",
                  severity: "hard",
                  message: "Ảnh quá nhỏ.",
                  metric: 90,
                  threshold: 320,
                },
              ],
              metrics: { min_side_px: 90 },
            },
            data: null,
            confidences: {},
            scan_id: null,
            error_code: "image_quality_low",
            error_message: "Ảnh không đạt tiêu chuẩn.",
          },
        ],
      }),
    );

    const result = await extractBatch([
      new File(["a"], "ok.png", { type: "image/png" }),
      new File(["b"], "bad.png", { type: "image/png" }),
    ]);

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/extract-batch"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.total).toBe(2);
    expect(result.results[0]?.quality?.accepted).toBe(true);
    expect(result.results[1]?.quality?.issues[0]?.code).toBe("low_resolution");
  });

  const LIST_ROWS = [
    {
      full_name: "NGUYEN VAN A",
      id_number: "001202000123",
      dob: "01/01/2002",
      gender: "Nam",
      residence: "Hà Nội",
      scan_ids: ["scan-1"],
    },
  ];

  it("exportListToExcel posts all rows to /export-list", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("excel-bytes", { status: 200 }),
    );
    vi.spyOn(global.URL, "createObjectURL").mockReturnValue("blob:mock");
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    await exportListToExcel(LIST_ROWS);

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain("/export-list");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ rows: LIST_ROWS });
  });

  it("exportListToExcel uses filename from Content-Disposition header", async () => {
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

    const timeoutSpy = vi.spyOn(globalThis, "setTimeout");
    await exportListToExcel(LIST_ROWS);

    const anchor = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("CCCD_ảnh.xlsx");
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(removeSpy).toHaveBeenCalledTimes(1);
    expect(revokeSpy).not.toHaveBeenCalled();
    const revokeLater = timeoutSpy.mock.calls.at(-1)?.[0] as () => void;
    revokeLater();
    expect(revokeSpy).toHaveBeenCalledWith("blob:mock");
  });

  it("exportListToExcel falls back to default filename when header is missing", async () => {
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

    await exportListToExcel(LIST_ROWS);

    const anchor = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("DanhSach_CCCD.xlsx");
  });

  it("exportListToExcel throws APIError on failed export request", async () => {
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

    await expect(exportListToExcel(LIST_ROWS)).rejects.toBeInstanceOf(APIError);
  });

  // Fetch giả: không bao giờ resolve, chỉ reject AbortError khi signal bị abort
  // (mô phỏng đúng hành vi của fetch thật với AbortController).
  function mockAbortableFetch(): void {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url: string | URL | Request, opts?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = opts?.signal ?? undefined;
          const abort = () =>
            reject(new DOMException("The operation was aborted.", "AbortError"));
          if (signal?.aborted) {
            abort();
            return;
          }
          signal?.addEventListener("abort", abort);
        }),
    );
  }

  it("request throws APIError code 'timeout' when the server never responds", async () => {
    vi.useFakeTimers();
    mockAbortableFetch();

    const promise = getScans();
    const assertion = expect(promise).rejects.toMatchObject({
      name: "APIError",
      code: "timeout",
      status: 0,
    });
    // Đẩy quá ngưỡng timeout mặc định (30s) -> timeout controller abort.
    await vi.advanceTimersByTimeAsync(30_000);
    await assertion;
  });

  it("propagates caller abort as AbortError (not timeout)", async () => {
    mockAbortableFetch();

    const controller = new AbortController();
    const promise = getScans(50, 0, controller.signal);
    controller.abort();

    let caught: unknown;
    try {
      await promise;
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeDefined();
    expect(isAbortError(caught)).toBe(true);
    // Không được biến thành lỗi timeout.
    expect((caught as { code?: string }).code).not.toBe("timeout");
  });

  it("drops an expired token and retries the request anonymously", async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "expired");
    const onExpired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(
          { code: "auth_token_invalid", message: "Phiên đăng nhập đã hết hạn.", request_id: "r" },
          401,
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ data: VALID_DATA, confidences: {} }));

    const result = await extractCCCD(new File(["x"], "a.jpg", { type: "image/jpeg" }));

    expect(result.data.id_number).toBe(VALID_DATA.id_number);
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(onExpired).toHaveBeenCalledTimes(1);
    const retryHeaders = fetchSpy.mock.calls[1]?.[1]?.headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBeUndefined();
    window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  });

  it("keeps the token when login credentials are wrong", async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "valid");
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ code: "auth_invalid", message: "Sai mật khẩu", request_id: "r" }, 401),
    );
    await expect(getScans()).rejects.toBeInstanceOf(APIError);
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBe("valid");
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  });
});
