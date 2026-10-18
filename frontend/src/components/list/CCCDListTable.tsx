"use client";

import React, { useMemo, useState } from "react";

import type { APIError } from "@/lib/api";
import {
  decodeIdNumber,
  LIST_FIELD_LABELS,
  LIST_FIELDS,
  nearDuplicateIds,
  needsReview,
  pendingReviewCount,
  validateList,
  type ListField,
  type ListRow,
} from "@/lib/cccdList";

interface CCCDListTableProps {
  rows: ListRow[];
  onUpdate: (key: string, field: ListField, value: string) => void;
  onMarkReviewed: (key: string) => void;
  onMerge: (sourceKey: string, targetKey: string) => void;
  onRemove: (key: string) => void;
  onAdd: () => void;
  onClear: () => void;
  onExport: () => void | Promise<unknown>;
  isExporting?: boolean;
  exportError?: APIError | null;
}

const PLACEHOLDERS: Record<ListField, string> = {
  full_name: "NGUYỄN VĂN A",
  id_number: "12 chữ số",
  dob: "DD/MM/YYYY",
  gender: "",
  residence: "Số nhà, xã/phường, tỉnh/thành phố",
};

const COLUMN_WIDTHS: Record<ListField, string> = {
  full_name: "w-64",
  id_number: "w-36",
  dob: "w-32",
  gender: "w-24",
  residence: "",
};

function cellClass(error: string | undefined, review: boolean): string {
  const base =
    "w-full rounded-md border px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400";
  if (error) return `${base} border-red-400 bg-red-50`;
  if (review) return `${base} border-amber-400 bg-amber-50`;
  return `${base} border-gray-300 bg-white`;
}

function confidenceTitle(row: ListRow, field: ListField): string | undefined {
  const confidence = row.confidences[field];
  if (row.reviewed[field]) return "Đã kiểm tra";
  if (typeof confidence !== "number") return undefined;
  return `Độ tin cậy OCR: ${Math.round(confidence * 100)}%`;
}

export default function CCCDListTable({
  rows,
  onUpdate,
  onMarkReviewed,
  onMerge,
  onRemove,
  onAdd,
  onClear,
  onExport,
  isExporting = false,
  exportError = null,
}: CCCDListTableProps) {
  const errors = useMemo(() => validateList(rows), [rows]);
  const nearDuplicates = useMemo(() => nearDuplicateIds(rows), [rows]);
  const pending = pendingReviewCount(rows);
  const [confirmClear, setConfirmClear] = useState(false);
  // Lưu số ô vàng lúc hỏi xác nhận: số này đổi (sửa, xác nhận, thêm ảnh) thì phải hỏi lại.
  const [confirmedPending, setConfirmedPending] = useState<number | null>(null);

  const canExport = rows.length > 0 && errors.size === 0 && !isExporting;
  const showConfirm = pending > 0 && confirmedPending === pending;

  const handleExport = () => {
    if (!canExport) return;
    // Còn ô độ tin cậy thấp chưa kiểm tra: bắt người dùng bấm xác nhận lần 2 thay vì xuất âm thầm.
    if (pending > 0 && !showConfirm) {
      setConfirmedPending(pending);
      return;
    }
    setConfirmedPending(null);
    void onExport();
  };

  const handleClear = () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    setConfirmClear(false);
    onClear();
  };

  return (
    <div className="space-y-4 rounded-lg bg-white p-4 shadow-md sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold text-gray-700">{rows.length} người</span>
          {errors.size > 0 && (
            <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-0.5 font-semibold text-red-700">
              {errors.size} dòng có lỗi
            </span>
          )}
          {pending > 0 && (
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 font-semibold text-amber-700">
              {pending} ô cần kiểm tra
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onAdd}
            className="rounded-md border border-blue-600 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50"
          >
            + Thêm dòng
          </button>
          {rows.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              onBlur={() => setConfirmClear(false)}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50"
            >
              {confirmClear ? "Bấm lần nữa để xóa hết" : "Xóa tất cả"}
            </button>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
          Chưa có ai trong danh sách. Quét ảnh CCCD ở Bước 1 hoặc bấm &quot;Thêm dòng&quot; để nhập tay.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] table-fixed border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-xs uppercase text-gray-500">
                <th className="w-10 px-2 py-2">STT</th>
                {LIST_FIELDS.map((field) => (
                  <th key={field} className={`px-2 py-2 ${COLUMN_WIDTHS[field]}`}>
                    {LIST_FIELD_LABELS[field]}
                  </th>
                ))}
                <th className="w-28 px-2 py-2" aria-label="Thao tác" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const rowErrors = errors.get(row.key) ?? {};
                const rowPending = LIST_FIELDS.some((field) => needsReview(row, field, nearDuplicates));
                const idInfo = decodeIdNumber(row.id_number);
                const nearRow = nearDuplicates.get(row.key);
                return (
                  <tr key={row.key} className="border-b border-gray-100 align-top">
                    <td className="px-2 py-2 pt-3.5 text-gray-500">{index + 1}</td>
                    {LIST_FIELDS.map((field) => {
                      const error = rowErrors[field];
                      const label = `${LIST_FIELD_LABELS[field]} dòng ${index + 1}`;
                      const className = cellClass(error, needsReview(row, field, nearDuplicates));
                      return (
                        <td key={field} className="px-2 py-2">
                          {field === "gender" ? (
                            <select
                              aria-label={label}
                              value={row.gender}
                              onChange={(e) => onUpdate(row.key, field, e.target.value)}
                              className={className}
                              title={confidenceTitle(row, field)}
                            >
                              <option value="">--</option>
                              <option value="Nam">Nam</option>
                              <option value="Nữ">Nữ</option>
                            </select>
                          ) : field === "residence" ? (
                            <textarea
                              aria-label={label}
                              rows={2}
                              value={row.residence}
                              placeholder={PLACEHOLDERS[field]}
                              onChange={(e) => onUpdate(row.key, field, e.target.value)}
                              className={`${className} resize-y`}
                              title={confidenceTitle(row, field)}
                            />
                          ) : (
                            <input
                              aria-label={label}
                              value={row[field]}
                              placeholder={PLACEHOLDERS[field]}
                              inputMode={field === "id_number" ? "numeric" : "text"}
                              onChange={(e) => onUpdate(row.key, field, e.target.value)}
                              className={className}
                              title={confidenceTitle(row, field)}
                            />
                          )}
                          {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
                          {field === "gender" && idInfo && row.gender !== idInfo.gender && (
                            <button
                              type="button"
                              onClick={() => onUpdate(row.key, "gender", idInfo.gender)}
                              className="mt-1 text-xs font-medium text-blue-700 underline"
                            >
                              Theo số CCCD: {idInfo.gender}
                            </button>
                          )}
                          {field === "id_number" && !error && nearRow !== undefined && !row.reviewed.id_number && (
                            <div className="mt-1 text-xs text-amber-800">
                              <p>Gần giống số CCCD dòng {nearRow}: có thể cùng 1 thẻ bị đọc lệch.</p>
                              <button
                                type="button"
                                onClick={() => onMerge(row.key, rows[nearRow - 1]!.key)}
                                className="font-medium text-blue-700 underline"
                              >
                                Gộp vào dòng {nearRow}
                              </button>
                            </div>
                          )}
                        </td>
                      );
                    })}
                    <td className="space-y-1 px-2 py-2">
                      {rowPending && (
                        <button
                          type="button"
                          onClick={() => onMarkReviewed(row.key)}
                          className="block w-full rounded-md border border-amber-300 px-2 py-1 text-xs font-medium text-amber-800 hover:bg-amber-50"
                        >
                          Đã kiểm tra
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onRemove(row.key)}
                        aria-label={`Xóa dòng ${index + 1}`}
                        className="block w-full rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:border-red-300 hover:text-red-700"
                      >
                        Xóa
                      </button>
                      {row.sources.length > 0 && (
                        <p className="truncate text-[11px] text-gray-400" title={row.sources.join(", ")}>
                          {row.sources.join(", ")}
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-col items-stretch gap-2 border-t border-gray-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-xs text-gray-500">
          <span className="mr-3 inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm border border-amber-400 bg-amber-50" /> Cần kiểm tra lại
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm border border-red-400 bg-red-50" /> Thiếu hoặc sai
          </span>
        </div>
        <button
          type="button"
          onClick={handleExport}
          disabled={!canExport}
          className="rounded-md bg-emerald-600 px-5 py-2 font-semibold text-white hover:bg-emerald-700 disabled:bg-gray-400"
        >
          {isExporting
            ? "Đang xuất..."
            : showConfirm
              ? `Vẫn xuất Excel (${rows.length} người)`
              : `Xuất Excel (${rows.length} người)`}
        </button>
      </div>

      {errors.size > 0 && (
        <p className="text-sm text-red-700">
          Còn {errors.size} dòng thiếu hoặc sai dữ liệu (ô đỏ). Sửa xong mới xuất được Excel.
        </p>
      )}
      {showConfirm && errors.size === 0 && (
        <p className="text-sm text-amber-800">
          Còn {pending} ô OCR chưa chắc chắn (ô vàng) chưa được kiểm tra. Đối chiếu với thẻ rồi bấm
          &quot;Đã kiểm tra&quot;, hoặc bấm nút xuất lần nữa nếu chắc chắn dữ liệu đúng.
        </p>
      )}
      {exportError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <div className="font-semibold">{exportError.message}</div>
          {exportError.requestId && (
            <div className="mt-1 break-all text-xs text-red-500">request_id: {exportError.requestId}</div>
          )}
        </div>
      )}
    </div>
  );
}
