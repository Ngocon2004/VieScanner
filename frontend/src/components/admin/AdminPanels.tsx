"use client";

import React from "react";

import { errorLabel, FIELD_LABELS, type AdminOverview, type AdminSystem } from "@/lib/admin";

const BAR_COLOR = "#2a78d6";
const nf = new Intl.NumberFormat("vi-VN");
const pct = (value: number) => `${Math.round(value * 100)}%`;

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "--";
  return ms >= 1000 ? `${(ms / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} s` : `${ms} ms`;
}

export function Panel({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-gray-800">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-gray-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

export function StatTiles({ overview }: { overview: AdminOverview }) {
  const t = overview.totals;
  const successRate = t.scans ? t.succeeded / t.scans : 0;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatTile label="Lượt quét" value={nf.format(t.scans)} sub={`${nf.format(t.failed)} thất bại`} />
      <StatTile label="Tỉ lệ thành công" value={t.scans ? pct(successRate) : "--"} sub={`${nf.format(t.succeeded)} ảnh đọc được`} />
      <StatTile
        label="Thời gian xử lý"
        value={formatDuration(t.median_duration_ms)}
        sub={`trung vị · p90 ${formatDuration(t.p90_duration_ms)}`}
      />
      <StatTile label="Lượt quét đã xuất" value={nf.format(t.exported_scans)} sub={`${nf.format(t.corrections)} ô người dùng phải sửa`} />
      <StatTile label="Người dùng" value={nf.format(t.users)} sub={`+${nf.format(t.new_users)} trong kỳ`} />
      <StatTile label="Job đang chạy" value={nf.format(t.active_jobs)} sub="đang chờ hoặc đang xử lý" />
    </div>
  );
}

export function ErrorBars({ errors }: { errors: AdminOverview["errors"] }) {
  if (errors.length === 0) return <p className="text-sm text-gray-500">Không có lượt quét thất bại trong kỳ.</p>;
  const max = Math.max(...errors.map((e) => e.count));
  return (
    <ul className="space-y-2">
      {errors.map((e) => (
        <li key={e.code} title={e.code}>
          <div className="flex justify-between text-sm text-gray-700">
            <span>{errorLabel(e.code)}</span>
            <span className="font-semibold tabular-nums text-gray-900">{nf.format(e.count)}</span>
          </div>
          <div className="mt-1 h-2 rounded-r bg-gray-100">
            <div className="h-2 rounded-r" style={{ width: `${(e.count / max) * 100}%`, background: BAR_COLOR }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Mỗi trường: đọc được bao nhiêu, bao nhiêu cần kiểm tra, người dùng phải sửa bao nhiêu (đo độ chính xác thực tế). */
export function FieldQualityTable({ overview }: { overview: AdminOverview }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="text-xs uppercase text-gray-500">
          <tr>
            <th className="py-2 pr-3">Trường</th>
            <th className="py-2 pr-3">Đọc được</th>
            <th className="py-2 pr-3">Độ tin cậy thấp</th>
            <th className="py-2">Bị sửa khi xuất</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {overview.fields.map((f) => (
            <tr key={f.field} className="border-t border-gray-100">
              <td className="py-2 pr-3 font-medium text-gray-800">{FIELD_LABELS[f.field] ?? f.field}</td>
              <td className="py-2 pr-3">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-20 rounded bg-gray-100">
                    <div className="h-1.5 rounded" style={{ width: pct(f.read_rate), background: BAR_COLOR }} />
                  </div>
                  <span className="text-gray-700">{pct(f.read_rate)}</span>
                </div>
              </td>
              <td className="py-2 pr-3 text-gray-700">{nf.format(f.low_confidence)}</td>
              <td className="py-2 text-gray-700">
                {nf.format(f.corrected)}
                {overview.totals.exported_scans > 0 && <span className="text-gray-500"> ({pct(f.corrected_rate)})</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-gray-500">
        &quot;Bị sửa khi xuất&quot; tính trên {nf.format(overview.totals.exported_scans)} lượt quét đã được xuất Excel: đây là tỉ lệ
        OCR sai thực tế mà người dùng phát hiện.
      </p>
    </div>
  );
}

const JOB_LABELS: Record<string, string> = {
  queued: "Đang chờ",
  processing: "Đang xử lý",
  completed: "Hoàn tất",
  partial: "Một phần",
  failed: "Thất bại",
  cancelled: "Đã hủy",
};

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className={ok ? "text-green-700" : "text-red-700"}>{ok ? "●" : "▲"}</span>
      {label}
    </span>
  );
}

export function SystemPanel({ system, jobs }: { system: AdminSystem | null; jobs: AdminOverview["jobs"] }) {
  if (!system) return <p className="text-sm text-gray-500">Đang tải...</p>;
  const rows: [string, React.ReactNode][] = [
    ["Engine OCR", <StatusDot key="e" ok={system.engine_ready} label={`${system.ocr_engine} · ${system.engine_ready ? "sẵn sàng" : "chưa nạp model"}`} />],
    ["Hàng đợi", `${system.queue_size} ảnh · xử lý song song ${system.concurrency}`],
    ["Đọc QR", system.qr_enabled ? "Bật" : "Tắt"],
    ["Cache kết quả", system.cache_enabled ? `Bật · ${system.cache_ttl_hours} giờ` : "Tắt"],
    ["Giữ lượt quét", system.scan_retention_days > 0 ? `${system.scan_retention_days} ngày` : "Không tự xóa"],
    ["Giữ job", `${system.job_retention_days} ngày`],
    ["Bắt buộc đăng nhập", system.auth_required ? "Có" : "Không"],
    ["Phiên bản pipeline", <code key="v" className="text-xs">{system.pipeline_version.slice(0, 16)}</code>],
  ];
  return (
    <div className="space-y-3 text-sm">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
        {rows.map(([k, v]) => (
          <React.Fragment key={k}>
            <dt className="text-gray-500">{k}</dt>
            <dd className="text-gray-800">{v}</dd>
          </React.Fragment>
        ))}
      </dl>
      {Object.keys(jobs).length > 0 && (
        <div className="flex flex-wrap gap-2 border-t border-gray-100 pt-3">
          {Object.entries(jobs).map(([status, count]) => (
            <span key={status} className="rounded-full border border-gray-200 px-2.5 py-0.5 text-xs text-gray-700">
              Job {JOB_LABELS[status] ?? status}: <b className="tabular-nums">{count}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
