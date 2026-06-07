"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { APIError, extractBatch } from "@/lib/api";
import { precheckImageQuality, summarizeHardIssues } from "@/lib/quality";
import type { CCCDData, FieldConfidences, QualityReport } from "@/lib/schemas";

export interface BatchUIItem {
  originalIndex: number;
  filename: string;
  previewUrl: string;
  accepted: boolean;
  status: "extracted" | "rejected" | "ocr_failed";
  quality: QualityReport | null;
  data: CCCDData | null;
  confidences: FieldConfidences;
  scanId: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  /** Nơi đưa ra quyết định loại ảnh: client (tiền kiểm) hay server (BE). */
  source: "client" | "server";
}

interface UseBatchExtractState {
  items: BatchUIItem[];
  loading: boolean;
  error: APIError | null;
}

interface UseBatchExtract extends UseBatchExtractState {
  acceptedCount: number;
  rejectedCount: number;
  run: (files: File[]) => Promise<void>;
  reset: () => void;
}

export function useBatchExtract(): UseBatchExtract {
  const [state, setState] = useState<UseBatchExtractState>({
    items: [],
    loading: false,
    error: null,
  });
  // Bỏ qua kết quả của lần chạy cũ khi user upload lại liên tiếp.
  const runIdRef = useRef(0);
  // Theo dõi object URL để revoke, tránh leak bộ nhớ.
  const previewUrlsRef = useRef<string[]>([]);

  const revokePreviews = useCallback(() => {
    for (const url of previewUrlsRef.current) URL.revokeObjectURL(url);
    previewUrlsRef.current = [];
  }, []);

  const run = useCallback(
    async (files: File[]) => {
      const currentRun = ++runIdRef.current;
      revokePreviews();
      setState({ items: [], loading: true, error: null });

      if (files.length === 0) {
        setState({ items: [], loading: false, error: null });
        return;
      }

      try {
        // 1) Tiền kiểm phía client (song song).
        const prechecks = await Promise.all(files.map((f) => precheckImageQuality(f)));
        if (currentRun !== runIdRef.current) return;

        // 2) Chỉ upload ảnh qua được tiền kiểm.
        const uploadList: { file: File; originalIndex: number }[] = [];
        files.forEach((file, i) => {
          if (prechecks[i]?.accepted) uploadList.push({ file, originalIndex: i });
        });

        const serverResults =
          uploadList.length > 0
            ? (await extractBatch(uploadList.map((u) => u.file))).results
            : [];
        if (currentRun !== runIdRef.current) return;

        // 3) Gộp kết quả theo đúng thứ tự ảnh upload.
        const items: BatchUIItem[] = files.map((file, i) => {
          const previewUrl = URL.createObjectURL(file);
          previewUrlsRef.current.push(previewUrl);
          const precheck = prechecks[i] ?? null;

          if (!precheck?.accepted) {
            return {
              originalIndex: i,
              filename: file.name,
              previewUrl,
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
            };
          }

          const pos = uploadList.findIndex((u) => u.originalIndex === i);
          const sr = pos >= 0 ? serverResults[pos] : undefined;
          return {
            originalIndex: i,
            filename: file.name,
            previewUrl,
            accepted: sr?.accepted ?? false,
            status: (sr?.status as BatchUIItem["status"]) ?? "ocr_failed",
            quality: sr?.quality ?? precheck,
            data: sr?.data ?? null,
            confidences: (sr?.confidences ?? {}) as FieldConfidences,
            scanId: sr?.scan_id ?? null,
            errorCode: sr?.error_code ?? null,
            errorMessage: sr?.error_message ?? null,
            source: "server",
          };
        });

        setState({ items, loading: false, error: null });
      } catch (err) {
        if (currentRun !== runIdRef.current) return;
        revokePreviews();
        const error =
          err instanceof APIError
            ? err
            : new APIError({
                code: "unknown_error",
                message: "Có lỗi không xác định khi xử lý ảnh.",
                status: 0,
              });
        setState({ items: [], loading: false, error });
      }
    },
    [revokePreviews],
  );

  const reset = useCallback(() => {
    runIdRef.current++;
    revokePreviews();
    setState({ items: [], loading: false, error: null });
  }, [revokePreviews]);

  // Revoke previews khi unmount.
  useEffect(() => () => revokePreviews(), [revokePreviews]);

  const acceptedCount = state.items.filter((i) => i.accepted).length;
  const rejectedCount = state.items.length - acceptedCount;

  return { ...state, acceptedCount, rejectedCount, run, reset };
}
