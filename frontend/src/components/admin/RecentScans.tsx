"use client";

import React from "react";

import { formatDuration } from "@/components/admin/AdminPanels";
import { errorLabel, type AdminScan } from "@/lib/admin";

export type ScanFilter = "" | "success" | "failed";

const FILTERS: [ScanFilter, string][] = [
  ["", "Tất cả"],
  ["success", "Thành công"],
  ["failed", "Thất bại"],
];

const dateTimeFmt = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "medium" });

export function ScanFilterTabs({ value, onChange }: { value: ScanFilter; onChange: (v: ScanFilter) => void }) {
  return (
    <div role="tablist" className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5 text-xs">
      {FILTERS.map(([key, label]) => (
        <button
          key={key || "all"}
          type="button"
          role="tab"
          aria-selected={value === key}
          onClick={() => onChange(key)}
          className={`rounded-md px-2.5 py-1 font-medium ${value === key ? "bg-white text-blue-700 shadow" : "text-gray-600"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default function RecentScans({ scans }: { scans: AdminScan[] }) {
  if (scans.length === 0) return <p className="text-sm text-gray-500">Chưa có lượt quét nào.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="py-2 pr-3">Thời gian</th>
            <th className="py-2 pr-3">Người dùng</th>
            <th className="py-2 pr-3">Kết quả</th>
            <th className="py-2 pr-3">Số CCCD</th>
            <th className="py-2 pr-3 text-right" title="Trong 5 trường của danh sách xuất Excel">Trường đọc được</th>
            <th className="py-2 pr-3 text-right">Xử lý</th>
            <th className="py-2">Nguồn</th>
          </tr>
        </thead>
        <tbody>
          {scans.map((s) => {
            const ok = s.status === "success";
            return (
              <tr key={s.id} className="border-t border-gray-100">
                <td className="py-2 pr-3 text-gray-600 tabular-nums">{dateTimeFmt.format(new Date(s.created_at))}</td>
                <td className="py-2 pr-3 text-gray-700">{s.user_email ?? <span className="text-gray-400">Ẩn danh</span>}</td>
                <td className="py-2 pr-3">
                  {ok ? (
                    <span className="text-green-800">✓ Thành công</span>
                  ) : (
                    <span className="text-red-800" title={s.error_code ?? undefined}>
                      ✕ {errorLabel(s.error_code)}
                    </span>
                  )}
                </td>
                <td className="py-2 pr-3 font-mono text-xs text-gray-700">{s.id_number_masked ?? "—"}</td>
                <td className="py-2 pr-3 text-right tabular-nums text-gray-700">
                  {ok ? (
                    <>
                      {s.fields_read}/5
                      {s.low_confidence_fields > 0 && (
                        <span className="ml-1 text-amber-800" title="Số trường có độ tin cậy thấp">· {s.low_confidence_fields} cần xem</span>
                      )}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums text-gray-700">{formatDuration(s.duration_ms)}</td>
                <td className="py-2 text-xs text-gray-500">{s.from_job ? "Job" : "API"} · {s.ocr_engine.split("@")[0]}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
