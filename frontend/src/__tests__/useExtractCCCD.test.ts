import { act, renderHook, waitFor } from "@testing-library/react";

import { APIError } from "@/lib/api";
import type { CCCDExtractResponse } from "@/lib/schemas";

import { useExtractCCCD } from "@/hooks/useExtractCCCD";
import * as api from "@/lib/api";

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const EXTRACT_RESULT: CCCDExtractResponse = {
  data: {
    id_number: "001202000123",
    full_name: "NGUYEN VAN A",
    dob: "01/01/2002",
    gender: "Nam",
    nationality: "Viet Nam",
    origin: "Quan 1, TP HCM",
    residence: "123 Le Loi, Quan 1, TP HCM",
    expiry_date: "01/01/2030",
  },
  confidences: { id_number: 0.99, full_name: 0.91 },
};

describe("useExtractCCCD", () => {
  const file = new File(["fake-image"], "card.png", { type: "image/png" });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("updates state on extract success", async () => {
    vi.spyOn(api, "extractCCCD").mockResolvedValue(EXTRACT_RESULT);
    const { result } = renderHook(() => useExtractCCCD());

    await act(async () => {
      await result.current.extract(file);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.data?.id_number).toBe("001202000123");
    expect(result.current.confidences.id_number).toBe(0.99);
  });

  it("stores APIError on extract failure", async () => {
    const apiError = new APIError({
      code: "ocr_failed",
      message: "OCR failed",
      status: 422,
      requestId: "req-123",
    });
    vi.spyOn(api, "extractCCCD").mockRejectedValue(apiError);
    const { result } = renderHook(() => useExtractCCCD());

    await act(async () => {
      await result.current.extract(file);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe(apiError);
    expect(result.current.error?.requestId).toBe("req-123");
  });

  it("ignores outdated request result during rapid uploads", async () => {
    const first = deferred<CCCDExtractResponse>();
    const second = deferred<CCCDExtractResponse>();

    vi.spyOn(api, "extractCCCD")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useExtractCCCD());

    act(() => {
      void result.current.extract(file);
    });
    act(() => {
      void result.current.extract(file);
    });

    second.resolve(EXTRACT_RESULT);
    await waitFor(() => {
      expect(result.current.data?.id_number).toBe("001202000123");
    });

    first.resolve({
      ...EXTRACT_RESULT,
      data: { ...EXTRACT_RESULT.data, id_number: "999999999999" },
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.data?.id_number).toBe("001202000123");
  });
});
