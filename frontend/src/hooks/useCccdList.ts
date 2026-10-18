"use client";

import { useCallback, useEffect, useState } from "react";

import {
  applyEdit,
  emptyRow,
  mergeIntoList,
  mergeRowInto,
  normalizeStoredRow,
  type ListField,
  type ListRow,
} from "@/lib/cccdList";

// sessionStorage (không phải localStorage): danh sách chứa dữ liệu CCCD nên tự xóa khi đóng tab,
// nhưng vẫn giữ lại nếu người dùng lỡ tải lại trang giữa chừng.
const STORAGE_KEY = "viescanner.cccd-list.v1";

function loadRows(): ListRow[] {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normalizeStoredRow).filter((row): row is ListRow => row !== null);
  } catch {
    return [];
  }
}

function saveRows(rows: ListRow[]): void {
  try {
    if (rows.length === 0) window.sessionStorage.removeItem(STORAGE_KEY);
    else window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(rows));
  } catch {
    // Bộ nhớ trình duyệt bị chặn/đầy: danh sách vẫn chạy trong bộ nhớ.
  }
}

export interface UseCccdList {
  rows: ListRow[];
  addRows: (incoming: ListRow[]) => void;
  addEmpty: () => string;
  updateField: (key: string, field: ListField, value: string) => void;
  markReviewed: (key: string) => void;
  mergeRows: (sourceKey: string, targetKey: string) => void;
  removeRow: (key: string) => void;
  clear: () => void;
}

export function useCccdList(): UseCccdList {
  const [rows, setRows] = useState<ListRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // Đọc sau khi mount: render phía server không có sessionStorage, đọc trong lúc render sẽ lệch hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRows(loadRows());
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (loaded) saveRows(rows);
  }, [rows, loaded]);

  const addRows = useCallback((incoming: ListRow[]) => {
    setRows((prev) => incoming.reduce(mergeIntoList, prev));
  }, []);

  const addEmpty = useCallback(() => {
    const row = emptyRow();
    setRows((prev) => [...prev, row]);
    return row.key;
  }, []);

  const updateField = useCallback((key: string, field: ListField, value: string) => {
    setRows((prev) =>
      prev.map((row) => (row.key === key ? applyEdit(row, field, value) : row)),
    );
  }, []);

  const markReviewed = useCallback((key: string) => {
    setRows((prev) =>
      prev.map((row) =>
        row.key === key
          ? {
              ...row,
              reviewed: {
                full_name: true,
                id_number: true,
                dob: true,
                gender: true,
                residence: true,
              },
            }
          : row,
      ),
    );
  }, []);

  const mergeRows = useCallback((sourceKey: string, targetKey: string) => {
    setRows((prev) => {
      const source = prev.find((row) => row.key === sourceKey);
      if (!source || sourceKey === targetKey) return prev;
      return prev
        .filter((row) => row.key !== sourceKey)
        .map((row) => (row.key === targetKey ? mergeRowInto(row, source) : row));
    });
  }, []);

  const removeRow = useCallback((key: string) => {
    setRows((prev) => prev.filter((row) => row.key !== key));
  }, []);

  const clear = useCallback(() => setRows([]), []);

  return { rows, addRows, addEmpty, updateField, markReviewed, mergeRows, removeRow, clear };
}
