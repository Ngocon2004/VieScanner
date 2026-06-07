"use client";

import React from "react";

import type { BatchUIItem } from "@/hooks/useBatchExtract";

interface BatchResultPanelProps {
  items: BatchUIItem[];
  selectedIndex: number | null;
  onSelect: (item: BatchUIItem) => void;
}

function StatusBadge({ status }: { status: BatchUIItem["status"] }) {
  const meta =
    status === "extracted"
      ? { label: "Đạt", className: "border-emerald-200 bg-emerald-50 text-emerald-700" }
      : status === "rejected"
        ? { label: "Không đạt", className: "border-red-200 bg-red-50 text-red-700" }
        : { label: "Không đọc được", className: "border-amber-200 bg-amber-50 text-amber-700" };
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold sm:text-xs ${meta.className}`}>
      {meta.label}
    </span>
  );
}

function ItemReasons({ item }: { item: BatchUIItem }) {
  const issues = item.quality?.issues ?? [];
  const hard = issues.filter((i) => i.severity === "hard");
  const soft = issues.filter((i) => i.severity === "soft");
  return (
    <ul className="mt-1 space-y-0.5 text-xs">
      {hard.map((i, idx) => (
        <li key={`h-${idx}`} className="text-red-600">• {i.message}</li>
      ))}
      {soft.map((i, idx) => (
        <li key={`s-${idx}`} className="text-amber-600">• {i.message}</li>
      ))}
      {item.status === "ocr_failed" && item.errorMessage && (
        <li className="text-amber-700">• {item.errorMessage}</li>
      )}
      {hard.length === 0 && soft.length === 0 && item.status === "rejected" && item.errorMessage && (
        <li className="text-red-600">• {item.errorMessage}</li>
      )}
    </ul>
  );
}

export default function BatchResultPanel({ items, selectedIndex, onSelect }: BatchResultPanelProps) {
  if (items.length === 0) return null;

  const rejected = items.filter((i) => i.status !== "extracted");
  const extracted = items.filter((i) => i.status === "extracted");

  return (
    <section className="space-y-5">
      {/* Tổng quan */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <span className="text-sm font-semibold text-gray-700">
          Đã xử lý {items.length} ảnh:
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700">
          {extracted.length} đã trích xuất
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-sm font-semibold text-red-700">
          {rejected.length} cần xem lại
        </span>
      </div>

      {/* Ảnh không đạt / cần xem lại */}
      {rejected.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50/60 p-4">
          <h3 className="mb-3 text-sm font-bold text-red-800 sm:text-base">
            Ảnh không đủ tiêu chuẩn ({rejected.length})
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {rejected.map((item) => (
              <div
                key={item.originalIndex}
                className="flex gap-3 rounded-md border border-red-200 bg-white p-3"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.previewUrl}
                  alt={item.filename}
                  className="h-16 w-24 shrink-0 rounded object-cover"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-gray-700" title={item.filename}>
                      {item.filename}
                    </span>
                    <StatusBadge status={item.status} />
                  </div>
                  <ItemReasons item={item} />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs italic text-red-700">
            Hãy chụp lại các ảnh trên rõ nét, đủ sáng, thấy đủ 4 góc thẻ rồi tải lại.
          </p>
        </div>
      )}

      {/* Ảnh đạt -> chọn để xem & xuất */}
      {extracted.length > 0 && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4">
          <h3 className="mb-3 text-sm font-bold text-emerald-800 sm:text-base">
            Ảnh đã trích xuất ({extracted.length}) — chọn 1 ảnh để kiểm tra & xuất Excel
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {extracted.map((item) => {
              const isSelected = item.originalIndex === selectedIndex;
              const softCount = (item.quality?.issues ?? []).filter((i) => i.severity === "soft").length;
              return (
                <button
                  key={item.originalIndex}
                  type="button"
                  onClick={() => onSelect(item)}
                  className={`flex gap-3 rounded-md border bg-white p-3 text-left transition-colors ${
                    isSelected
                      ? "border-emerald-500 ring-2 ring-emerald-400"
                      : "border-emerald-200 hover:border-emerald-400"
                  }`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={item.previewUrl}
                    alt={item.filename}
                    className="h-16 w-24 shrink-0 rounded object-cover"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-gray-700" title={item.filename}>
                        {item.filename}
                      </span>
                      <StatusBadge status={item.status} />
                    </div>
                    {item.data && (
                      <div className="mt-1 truncate text-xs text-gray-600">
                        {item.data.id_number} — {item.data.full_name}
                      </div>
                    )}
                    {softCount > 0 && (
                      <div className="mt-1 text-xs text-amber-600">
                        {softCount} cảnh báo chất lượng (nên kiểm tra kỹ)
                      </div>
                    )}
                    <span className="mt-1 inline-block text-xs font-medium text-emerald-700 underline">
                      {isSelected ? "Đang chọn" : "Xem & xuất Excel"}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
