"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { APIError, cancelJob, createJob, getJob, isAbortError, type JobSource } from "@/lib/api";
import { maxRequestBytes, uploadKind } from "@/lib/image";
import { precheckImageQuality, summarizeHardIssues } from "@/lib/quality";
import {
  JOB_TERMINAL_STATUSES,
  type CCCDData,
  type FieldConfidences,
  type Job,
  type JobItem,
  type QualityReport,
} from "@/lib/schemas";

export type BatchItemStatus =
  | "queued"
  | "processing"
  | "extracted"
  | "rejected"
  | "ocr_failed"
  | "cancelled";

export interface BatchUIItem {
  originalIndex: number;
  filename: string;
  previewUrl: string | null;
  pageNumber: number | null;
  accepted: boolean;
  status: BatchItemStatus;
  quality: QualityReport | null;
  data: CCCDData | null;
  confidences: FieldConfidences;
  scanId: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  /** Nơi đưa ra quyết định loại ảnh: client (tiền kiểm) hay server (BE). */
  source: "client" | "server";
}

export interface BatchProgress {
  processed: number;
  total: number;
}

interface UseBatchExtractState {
  jobId: string | null;
  items: BatchUIItem[];
  loading: boolean;
  error: APIError | null;
  progress: BatchProgress | null;
}

interface UseBatchExtract extends UseBatchExtractState {
  acceptedCount: number;
  rejectedCount: number;
  run: (files: File[], source?: JobSource) => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

export const JOB_POLL_INTERVAL_MS = 1500;
const MAX_POLL_FAILURES = 3;
// Item lỗi ở client không có seq phía server: đặt chỉ số riêng để không trùng key.
const CLIENT_INDEX_OFFSET = 100_000;

const STATUS_BY_JOB_ITEM: Record<string, BatchItemStatus> = {
  queued: "queued",
  processing: "processing",
  done: "extracted",
  rejected: "rejected",
  failed: "ocr_failed",
  cancelled: "cancelled",
};

function isTerminal(job: Job): boolean {
  return (JOB_TERMINAL_STATUSES as readonly string[]).includes(job.status);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

function toUIItem(item: JobItem, previewUrl: string | null): BatchUIItem {
  const result = item.result ?? null;
  return {
    originalIndex: item.seq,
    filename: item.filename ?? `Ảnh ${item.seq + 1}`,
    previewUrl,
    pageNumber: item.page_number ?? null,
    accepted: result?.accepted ?? true,
    status: STATUS_BY_JOB_ITEM[item.status] ?? "queued",
    quality: result?.quality ?? null,
    data: result?.data ?? null,
    confidences: (result?.confidences ?? {}) as FieldConfidences,
    scanId: result?.scan_id ?? item.scan_id ?? null,
    errorCode: result?.error_code ?? null,
    errorMessage: result?.error_message ?? null,
    source: "server",
  };
}

function toAPIError(err: unknown): APIError {
  return err instanceof APIError
    ? err
    : new APIError({
        code: "unknown_error",
        message: "Có lỗi không xác định khi xử lý ảnh.",
        status: 0,
      });
}

export function useBatchExtract(): UseBatchExtract {
  const [state, setState] = useState<UseBatchExtractState>({
    jobId: null,
    items: [],
    loading: false,
    error: null,
    progress: null,
  });
  const runIdRef = useRef(0);
  const previewUrlsRef = useRef<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const activeJobRef = useRef<string | null>(null);

  const revokePreviews = useCallback(() => {
    for (const url of previewUrlsRef.current) URL.revokeObjectURL(url);
    previewUrlsRef.current = [];
  }, []);

  // Dừng theo dõi job cũ và hủy phía server để không OCR tiếp các ảnh không còn ai xem.
  const stopActiveJob = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    const jobId = activeJobRef.current;
    activeJobRef.current = null;
    if (jobId) void cancelJob(jobId).catch(() => undefined);
  }, []);

  const run = useCallback(
    async (files: File[], source: JobSource = "upload") => {
      const currentRun = ++runIdRef.current;
      stopActiveJob();
      revokePreviews();
      setState({ jobId: null, items: [], loading: true, error: null, progress: null });
      if (files.length === 0) {
        setState({ jobId: null, items: [], loading: false, error: null, progress: null });
        return;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      const isCurrent = () => currentRun === runIdRef.current;

      try {
        // Tuần tự: tiền kiểm giải mã ảnh ở độ phân giải đầy đủ để đo độ nét.
        const prechecks: (QualityReport | null)[] = [];
        for (const f of files) {
          prechecks.push(uploadKind(f) === "image" ? await precheckImageQuality(f) : null);
          if (!isCurrent()) return;
        }

        const clientRejected: BatchUIItem[] = [];
        const uploads: File[] = [];
        files.forEach((file, i) => {
          const precheck = prechecks[i];
          if (precheck && !precheck.accepted) {
            const previewUrl = URL.createObjectURL(file);
            previewUrlsRef.current.push(previewUrl);
            clientRejected.push({
              originalIndex: CLIENT_INDEX_OFFSET + i,
              filename: file.name,
              previewUrl,
              pageNumber: null,
              accepted: false,
              status: "rejected",
              quality: precheck,
              data: null,
              confidences: {},
              scanId: null,
              errorCode: "image_quality_low",
              errorMessage:
                summarizeHardIssues(precheck) || "Ảnh không đạt tiêu chuẩn (tiền kiểm).",
              source: "client",
            });
          } else {
            uploads.push(file);
          }
        });

        if (uploads.length === 0) {
          setState({ jobId: null, items: clientRejected, loading: false, error: null, progress: null });
          return;
        }

        // Backend từ chối request vượt MAX_REQUEST_MB ngay khi đọc header; chặn trước ở đây vì trình
        // duyệt có thể chỉ báo lỗi mạng khi server cắt kết nối giữa lúc đang tải file lên.
        const totalBytes = uploads.reduce((sum, file) => sum + file.size, 0);
        const limitBytes = maxRequestBytes();
        if (totalBytes > limitBytes) {
          const toMb = (bytes: number) =>
            (bytes / (1024 * 1024)).toLocaleString("vi-VN", { maximumFractionDigits: 1 });
          throw new APIError({
            code: "request_too_large",
            message: `Tổng dung lượng các file (${toMb(totalBytes)}MB) vượt giới hạn ${toMb(limitBytes)}MB mỗi lần gửi. Hãy chia thành nhiều lần, mỗi lần ít file hơn.`,
            status: 413,
          });
        }

        // Chỉ ảnh thường mới xem trước được; HEIC/PDF hiển thị ô thay thế.
        const previewByUpload = uploads.map((file) => {
          if (uploadKind(file) !== "image") return null;
          const url = URL.createObjectURL(file);
          previewUrlsRef.current.push(url);
          return url;
        });
        const render = (job: Job) => {
          setState({
            jobId: job.id,
            items: [
              ...job.items.map((item) => toUIItem(item, previewByUpload[item.upload_index] ?? null)),
              ...clientRejected,
            ],
            loading: !isTerminal(job),
            error: null,
            progress: { processed: job.processed_items, total: job.total_items },
          });
        };

        let job = await createJob(uploads, source, controller.signal);
        if (!isCurrent()) {
          void cancelJob(job.id).catch(() => undefined);
          return;
        }
        activeJobRef.current = job.id;
        render(job);

        let failures = 0;
        while (!isTerminal(job)) {
          await sleep(JOB_POLL_INTERVAL_MS, controller.signal);
          try {
            job = await getJob(job.id, controller.signal);
            failures = 0;
          } catch (err) {
            if (isAbortError(err) || ++failures >= MAX_POLL_FAILURES) throw err;
            continue;
          }
          if (!isCurrent()) return;
          render(job);
        }
        activeJobRef.current = null;
        abortRef.current = null;
      } catch (err) {
        if (!isCurrent() || isAbortError(err)) return;
        activeJobRef.current = null;
        setState((prev) => ({ ...prev, loading: false, error: toAPIError(err) }));
      }
    },
    [revokePreviews, stopActiveJob],
  );

  const cancel = useCallback(() => {
    const jobId = activeJobRef.current;
    if (jobId) void cancelJob(jobId).catch(() => undefined);
  }, []);

  const reset = useCallback(() => {
    runIdRef.current++;
    stopActiveJob();
    revokePreviews();
    setState({ jobId: null, items: [], loading: false, error: null, progress: null });
  }, [revokePreviews, stopActiveJob]);

  useEffect(
    () => () => {
      stopActiveJob();
      revokePreviews();
    },
    [revokePreviews, stopActiveJob],
  );

  const acceptedCount = state.items.filter((i) => i.status === "extracted").length;
  const rejectedCount = state.items.filter(
    (i) => i.status === "rejected" || i.status === "ocr_failed",
  ).length;

  return { ...state, acceptedCount, rejectedCount, run, cancel, reset };
}
