import { act, renderHook, waitFor } from "@testing-library/react";

import { JOB_POLL_INTERVAL_MS, useBatchExtract } from "@/hooks/useBatchExtract";
import * as api from "@/lib/api";
import * as quality from "@/lib/quality";
import type { CCCDData, Job, JobItem, QualityReport } from "@/lib/schemas";

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

const ACCEPTED: QualityReport = { accepted: true, score: 1, issues: [], metrics: {} };
const REJECTED: QualityReport = {
  accepted: false,
  score: 0.65,
  issues: [
    { code: "low_resolution", severity: "hard", message: "Ảnh quá nhỏ.", metric: 90, threshold: 320 },
  ],
  metrics: {},
};

function item(seq: number, status: string, extra: Partial<JobItem> = {}): JobItem {
  return {
    id: `item-${seq}`,
    seq,
    upload_index: seq,
    filename: `f${seq}.png`,
    container_filename: null,
    page_number: null,
    status,
    scan_id: null,
    result: null,
    ...extra,
  };
}

function job(status: string, items: JobItem[]): Job {
  const done = items.filter((i) => !["queued", "processing"].includes(i.status)).length;
  return {
    id: "job-1",
    source: "upload",
    status,
    total_items: items.length,
    processed_items: done,
    succeeded_items: items.filter((i) => i.status === "done").length,
    failed_items: 0,
    created_at: "2026-10-10T00:00:00Z",
    items,
  };
}

const DONE_RESULT = {
  index: 0,
  filename: "f0.png",
  accepted: true,
  status: "extracted",
  quality: ACCEPTED,
  data: VALID_DATA,
  confidences: { id_number: 0.99 },
  scan_id: "scan-1",
  error_code: null,
  error_message: null,
};

describe("useBatchExtract (job flow)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(api, "cancelJob").mockResolvedValue(job("cancelled", []));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("uploads only client-accepted files and polls until the job finishes", async () => {
    vi.spyOn(quality, "precheckImageQuality")
      .mockResolvedValueOnce(ACCEPTED)
      .mockResolvedValueOnce(REJECTED);
    const create = vi.spyOn(api, "createJob").mockResolvedValue(job("queued", [item(0, "queued")]));
    vi.spyOn(api, "getJob").mockResolvedValue(
      job("completed", [item(0, "done", { result: DONE_RESULT, scan_id: "scan-1" })]),
    );

    const good = new File(["g"], "good.png", { type: "image/png" });
    const bad = new File(["b"], "bad.png", { type: "image/png" });
    const { result } = renderHook(() => useBatchExtract());

    act(() => {
      void result.current.run([good, bad]);
    });
    await waitFor(() => expect(result.current.items[0]?.status).toBe("queued"));
    expect(create).toHaveBeenCalledWith([good], "upload", expect.any(AbortSignal));
    expect(result.current.loading).toBe(true);
    expect(result.current.progress).toEqual({ processed: 0, total: 1 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS);
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(2);
    expect(result.current.items[0]).toMatchObject({
      status: "extracted",
      scanId: "scan-1",
      source: "server",
    });
    expect(result.current.items[1]).toMatchObject({
      filename: "bad.png",
      status: "rejected",
      source: "client",
    });
    expect(result.current.acceptedCount).toBe(1);
    expect(result.current.rejectedCount).toBe(1);
  });

  it("skips client precheck for PDF/HEIC and has no local preview for them", async () => {
    const precheck = vi.spyOn(quality, "precheckImageQuality");
    vi.spyOn(api, "createJob").mockResolvedValue(
      job("completed", [
        item(0, "done", { result: DONE_RESULT, page_number: 1, filename: "a.pdf - trang 1" }),
      ]),
    );
    const { result } = renderHook(() => useBatchExtract());

    await act(async () => {
      await result.current.run([new File(["%PDF"], "a.pdf", { type: "application/pdf" })]);
    });

    expect(precheck).not.toHaveBeenCalled();
    expect(result.current.items[0]).toMatchObject({ previewUrl: null, pageNumber: 1 });
  });

  it("rejects uploads over the request size limit without calling the server", async () => {
    vi.stubEnv("NEXT_PUBLIC_MAX_REQUEST_MB", "1");
    const create = vi.spyOn(api, "createJob");
    const { result } = renderHook(() => useBatchExtract());
    const pdf = new File([new Uint8Array(1024 * 1024 + 1)], "a.pdf", { type: "application/pdf" });

    await act(async () => {
      await result.current.run([pdf]);
    });
    vi.unstubAllEnvs();

    expect(create).not.toHaveBeenCalled();
    expect(result.current.error).toMatchObject({ code: "request_too_large", status: 413 });
    expect(result.current.error?.message).toContain("1MB");
    expect(result.current.loading).toBe(false);
  });

  it("cancels the server job and stops polling on reset", async () => {
    vi.spyOn(quality, "precheckImageQuality").mockResolvedValue(ACCEPTED);
    vi.spyOn(api, "createJob").mockResolvedValue(job("queued", [item(0, "queued")]));
    const poll = vi.spyOn(api, "getJob").mockResolvedValue(job("processing", [item(0, "processing")]));

    const { result } = renderHook(() => useBatchExtract());
    act(() => {
      void result.current.run([new File(["x"], "x.png", { type: "image/png" })]);
    });
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    act(() => {
      result.current.reset();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS * 3);
    });

    expect(api.cancelJob).toHaveBeenCalledWith("job-1");
    expect(poll).not.toHaveBeenCalled();
    expect(result.current.items).toHaveLength(0);
    expect(result.current.error).toBeNull();
  });

  it("surfaces an error after repeated polling failures", async () => {
    vi.spyOn(quality, "precheckImageQuality").mockResolvedValue(ACCEPTED);
    vi.spyOn(api, "createJob").mockResolvedValue(job("queued", [item(0, "queued")]));
    vi.spyOn(api, "getJob").mockRejectedValue(
      new api.APIError({ code: "timeout", message: "Hết thời gian", status: 0 }),
    );

    const { result } = renderHook(() => useBatchExtract());
    act(() => {
      void result.current.run([new File(["x"], "x.png", { type: "image/png" })]);
    });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS * 4);
    });

    await waitFor(() => expect(result.current.error?.code).toBe("timeout"));
    expect(result.current.loading).toBe(false);
  });
});
