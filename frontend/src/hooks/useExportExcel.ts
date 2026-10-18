"use client";

import { useCallback, useState } from "react";

import { APIError, exportListToExcel } from "@/lib/api";
import type { ExportListRow } from "@/lib/cccdList";

interface UseExportExcelState {
  loading: boolean;
  error: APIError | null;
  successCount: number;
}

interface UseExportExcel extends UseExportExcelState {
  exportRows: (rows: ExportListRow[]) => Promise<boolean>;
  resetError: () => void;
}

export function useExportExcel(): UseExportExcel {
  const [state, setState] = useState<UseExportExcelState>({
    loading: false,
    error: null,
    successCount: 0,
  });

  const exportRows = useCallback(async (rows: ExportListRow[]) => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      await exportListToExcel(rows);
      setState((prev) => ({
        loading: false,
        error: null,
        successCount: prev.successCount + 1,
      }));
      return true;
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
      return false;
    }
  }, []);

  const resetError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return { ...state, exportRows, resetError };
}
