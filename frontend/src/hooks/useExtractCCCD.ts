"use client";

import { useCallback, useRef, useState } from "react";

import { APIError, extractCCCD } from "@/lib/api";
import type { CCCDData, FieldConfidences } from "@/lib/schemas";

interface UseExtractCCCDState {
  data: CCCDData | null;
  scan_id: string | null;
  confidences: FieldConfidences;
  loading: boolean;
  error: APIError | null;
}

interface UseExtractCCCD extends UseExtractCCCDState {
  /** Trigger extract trên file vừa upload. */
  extract: (file: File) => Promise<void>;
  /** Reset state về ban đầu (xóa data + error). */
  reset: () => void;
}

/**
 * Hook quản lý lifecycle của thao tác trích xuất CCCD.
 *
 * Tách logic khỏi UI giúp:
 *  - Dễ test bằng `@testing-library/react-hooks` hoặc `renderHook`.
 *  - Tránh lặp lại state machine ở nhiều page.
 *  - Cancel race conditions khi user upload liên tiếp.
 */
export function useExtractCCCD(): UseExtractCCCD {
  const [state, setState] = useState<UseExtractCCCDState>({
    data: null,
    scan_id: null,
    confidences: {},
    loading: false,
    error: null,
  });

  // Đếm số lần extract để bỏ qua kết quả của request cũ khi user upload lại.
  const requestIdRef = useRef(0);

  const extract = useCallback(async (file: File) => {
    const currentId = ++requestIdRef.current;
    setState({ data: null, scan_id: null, confidences: {}, loading: true, error: null });

    try {
      const result = await extractCCCD(file);
      if (currentId !== requestIdRef.current) return; // outdated → bỏ qua
      setState({
        data: result.data,
        scan_id: result.scan_id ?? null,
        confidences: result.confidences,
        loading: false,
        error: null,
      });
    } catch (err) {
      if (currentId !== requestIdRef.current) return;
      const error =
        err instanceof APIError
          ? err
          : new APIError({
              code: "unknown_error",
              message: "Có lỗi không xác định khi gọi server.",
              status: 0,
            });
      setState({ data: null, scan_id: null, confidences: {}, loading: false, error });
    }
  }, []);

  const reset = useCallback(() => {
    requestIdRef.current++;
    setState({ data: null, scan_id: null, confidences: {}, loading: false, error: null });
  }, []);

  return { ...state, extract, reset };
}
