"use client";

import { useCallback, useState } from "react";

import { APIError, exportToExcel } from "@/lib/api";
import type { CCCDData } from "@/lib/schemas";

interface UseExportExcelState {
  loading: boolean;
  error: APIError | null;
  successCount: number;
}

interface UseExportExcel extends UseExportExcelState {
  exportData: (data: CCCDData, scanId?: string) => Promise<void>;
  resetError: () => void;
}

/**
 * Hook quản lý thao tác xuất Excel (download). Không lưu data vì thao tác là
 * one-shot side-effect (trigger download browser); chỉ track loading/error.
 */
export function useExportExcel(): UseExportExcel {
  const [state, setState] = useState<UseExportExcelState>({
    loading: false,
    error: null,
    successCount: 0,
  });

  const exportData = useCallback(async (data: CCCDData, scanId?: string) => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      await exportToExcel(data, scanId);
      setState((prev) => ({
        loading: false,
        error: null,
        successCount: prev.successCount + 1,
      }));
    } catch (err) {
      const error =
        err instanceof APIError
          ? err
          : new APIError({
              code: "unknown_error",
              message: "Có lỗi không xác định khi xuất Excel.",
              status: 0,
            });
      setState((prev) => ({ ...prev, loading: false, error }));
    }
  }, []);

  const resetError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return { ...state, exportData, resetError };
}
